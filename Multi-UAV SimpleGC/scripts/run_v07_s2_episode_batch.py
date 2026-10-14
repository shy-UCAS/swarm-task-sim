"""Full-clock S2 episode execution; all task groups share geometry and one clock."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from copy import deepcopy
import json
import subprocess
import sys
import time
import traceback
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scripts.run_v07_s2_expansion import (INFRA_ATTEMPT, new_attempt, descriptor_jobs, EXPANSION_SCOPE,
                                        scene_digest, compare_episode_dirs)
from task_v07.expansion.contracts import P0ContractError, condition_digest, validate_model_input
from task_v07.expansion.episode_pipeline import plan_episode, calibrate_episode, episode_interval_check
from task_v07.expansion.role_planners import PlanningInfeasible
from task_v07.expansion.geometry_checks import exact_frame_geometry
from task_v07.expansion.evaluation import truncation_check
from task_v07.expansion.role_evaluation import group_evaluator
from task_v07.execution import execute, completion_budget, FROZEN_SHA256
from task_v07.labels import measure
from task_v07.io import read_json, save_json, write_episode, load_episode, load_pair
from scripts.audit_v07_s2_groups import audit_groups
from scripts.audit_v07_s2_infrastructure import audit_geometry


def rejected(descriptor, history):
    final = history[-1]
    return [{"episode_id": f"{descriptor['skeleton_id']}_{mode}", "skeleton_id": descriptor["skeleton_id"],
             "family_id": descriptor["family_id"], "intent": descriptor["base_intent"], "mode": mode,
             "common_slot": descriptor["common_draw"]["slot"], "aborted": False, "diagnostic_only": False,
             "state": "infeasible", "path": None, "task_result": None, "quality_valid": None, "audit_passed": None,
             "reason": final["category"], "rejection_detail": final["detail"], "geometry_attempts": history,
             "coordination_by_group": {}, "group_count": len(descriptor["task_groups"]),
             "approach_mode": descriptor["common_draw"]["approach_mode"]}
            for mode in ("synchronous", "sequential")]


def audit_episode(scene, skeleton, run, labels, mode, plan, root):
    with np.load(root / "truth_10hz.npz", allow_pickle=False) as saved:
        exported = {**run, **{key: saved[key].copy() for key in ("time_us", "p", "v", "a")},
                    "agent_ids": saved["agent_ids"].tolist()}
    recomputed, _ = measure(scene, skeleton, exported, mode, timing_plan=plan)
    if recomputed != labels:
        raise P0ContractError("Full episode labels disagree with exported truth")
    reverse = list(reversed(range(len(run["agent_ids"]))))
    alternate = {**exported, "agent_ids": [exported["agent_ids"][i] for i in reverse],
                 **{key: exported[key][:, reverse] for key in ("p", "v", "a")}}
    permuted, _ = measure(scene, skeleton, alternate, mode, timing_plan=plan)
    for key in ("agents", "task_groups", "cluster"):
        if permuted[key] != labels[key]:
            raise P0ContractError("Full episode labels change under physical-ID column permutation")
    model = load_episode(root)
    validate_model_input(model)
    check = load_episode(root, agent_ids=alternate["agent_ids"])
    if not np.array_equal(check["x"], model["x"][:, reverse]):
        raise P0ContractError("Model columns do not preserve identity")
    known = [a["observed"]["core_event"]["t_s"] for a in labels["agents"].values()
             if a["observed"]["core_event"]["t_s"] is not None]
    cutoff = min(known) - .1 if known and min(known) > .2 else 1.
    prefix, _ = measure(scene, skeleton, exported, mode, cutoff_s=cutoff, timing_plan=plan)
    if any(a["observed"]["core_event"]["t_s"] is not None for a in prefix["agents"].values()):
        raise P0ContractError("Prefix claims future core events")
    save_json(root / "prefix_labels.json", prefix)
    independent = audit_groups(root)
    save_json(root / "independent_exact_audit.json", independent)
    if independent["status"] != "PASS":
        raise P0ContractError(f"Independent full episode audit failed: {root}")
    targets = {a: group["target_id"] for group in skeleton["group_skeletons"].values() for a in group["members"]}
    frame, report = exact_frame_geometry(scene, exported, targets, forbidden_layers=skeleton["exclusion_policy"])
    generic = audit_geometry(scene, exported, frame, report, targets, forbidden_layers=skeleton["exclusion_policy"])
    save_json(root / "policy_geometry_audit.json", {"infrastructure_report": report, "independent": generic})
    if generic["status"] != "PASS":
        raise P0ContractError("Independent full-clock geometry audit failed")
    return {"independent_status": independent["status"], "region_difference_count": independent["region_difference_count"],
            "target_difference_count": independent["target_difference_count"],
            "event_or_metric_difference_count": independent["event_or_metric_difference_count"],
            "uncovered_conditions": independent["uncovered_conditions"], "input_whitelist_passed": True,
            "id_aligned_permutation_invariant": True}


def group_truncations(scene, skeleton, run, labels):
    checks = {}
    for gid, group in skeleton["group_skeletons"].items():
        observed = [labels["agents"][a]["observed"] for a in group["members"]]
        starts = [a["core_event"]["t_s"] for a in observed]
        ends = [a['work_end_s'] for a in observed]
        if group['role'] == 'intrusion':
            ends=[]
            for a,core in zip(group['members'],starts):
                column=run['agent_ids'].index(a)
                hold=(np.linalg.norm(run['p'][:,column]-group['references'][a]['endpoint_enu_m'],axis=1)<=group['terminal_radius_m'])
                hold&=np.linalg.norm(run['v'][:,column],axis=1)<=group['terminal_speed_m_s']
                hold&=False if core is None else run['time_us']/1e6>=core
                needed=round(group['terminal_hold_s']*10)+1
                windows=np.convolve(hold.astype(int),np.ones(needed,dtype=int),mode='valid') if len(hold)>=needed else np.array([])
                hits=np.flatnonzero(windows==needed)
                ends.append(None if not len(hits) else float(run['time_us'][int(hits[0])+needed-1]/1e6))
        if None in starts + ends:
            checks[gid] = {"status": "not_run", "reason": "work interval not observed"}
        else:
            cutoff = round((min(starts) + max(ends)) / 2, 1)
            checks[gid] = truncation_check(group_evaluator, scene, group, run, cutoff)
            checks[gid]['measured_work_interval_s']=[min(starts),max(ends)]
            if checks[gid]["status"] == "FAIL":
                raise P0ContractError(f"Half-work prefix claims group success: {gid}")
    return checks


def write_result(scene, descriptor, skeleton, bundle, run, plan, measured, mode, out, setup_s, *, extra_metrics=None):
    started = time.perf_counter()
    labels, frame = measure(scene, skeleton, run, mode, timing_plan=plan)
    dest = out / descriptor["skeleton_id"] / mode
    write_episode(dest, scene, descriptor["family_conditions"], skeleton, run, labels, frame,
                  plan["departure_delays_s"], mode, measured, timing_plan=plan, scope=EXPANSION_SCOPE)
    audit = audit_episode(scene, skeleton, run, labels, mode, plan, dest)
    truncation = group_truncations(scene, skeleton, run, labels)
    save_json(dest / "truncation_check.json", truncation)
    groups = labels["task_groups"]
    group_rows = {gid: {"role": skeleton["group_skeletons"][gid]["role"],
                       "execution_method": skeleton["group_skeletons"][gid]["execution_method"],
                       "target_id": skeleton["group_skeletons"][gid]["target_id"],
                       "members": skeleton["group_skeletons"][gid]["members"],
                       "formation_split_count": len(skeleton["group_skeletons"][gid].get("formation_split", {}).get("members", [])) or
                                                (2 if skeleton["approach_mode"] == "multi_direction" else 1),
                       "approach_span_deg": group["observed"]["approach_span_deg"],
                       "coordination": group["observed"]["coordination"],
                       "timing_diagnostics": group["observed"]["timing_diagnostics"], "result": group["result"]}
                  for gid, group in groups.items()}
    quality = labels["generation_quality"]["retained"]
    events = {a: value["observed"]["core_event"]["t_s"] for a, value in labels["agents"].items()}
    row = {"episode_id": f"{descriptor['skeleton_id']}_{mode}", "family_id": descriptor["family_id"],
           "skeleton_id": descriptor["skeleton_id"], "intent": descriptor["base_intent"], "mode": mode,
           "aborted": descriptor.get("subset") == "aborted", "diagnostic_only": False,
           "common_slot": descriptor["common_draw"]["slot"], "state": "generated" if quality else "generation_error",
           "reason": None if quality else "minimum_separation_below_2m", "path": dest.relative_to(out).as_posix(),
           "quality_valid": quality, "audit_passed": True, "task_result": labels["cluster"]["result"]["status"],
           "agent_ids": skeleton["agent_ids"], "condition_digest": condition_digest(descriptor, bundle),
           "scene_digest": scene_digest(scene), "group_count": len(groups), "groups": group_rows,
           "coordination_by_group": {gid: group["observed"]["coordination"]["classification"] for gid, group in groups.items()},
           "approach_mode": skeleton["approach_mode"], "duration_s": run["end_us"] / 1e6,
           "minimum_separation_m": labels["cluster"]["observed"]["minimum_separation_m"],
           "execution_status": run["execution_status"], "time_budget": run["time_budget"],
           "coordination_matches": all(g["observed"]["timing_diagnostics"]["coordination_matches_assignment"] is True for g in groups.values()),
           "batch_members_match": all(g["observed"]["timing_diagnostics"]["batch_members_match_assignment"] is True for g in groups.values()),
           "audit": audit, "truncation": truncation, "event_times_s": events,
           "simulation_wall_s": run["wall_s"], "amortized_skeleton_setup_s": setup_s / 2,
           "episode_postprocess_wall_s": time.perf_counter() - started}
    if extra_metrics:
        row.update(extra_metrics)
    if skeleton.get('abort_observation'):
        main=labels['task_groups'][skeleton['main_group_id']]
        row['abort_observation_valid']=main['result']['conditions']['abort_group_withdrawal_observed'] is True
        row['main_group_observed_coordination']=main['observed']['coordination']['classification']
    save_json(dest / "metrics.json", row)
    print(json.dumps({"stage": "episode_complete", **{k: row[k] for k in ("episode_id", "state", "task_result", "coordination_matches", "minimum_separation_m")}}, ensure_ascii=False), flush=True)
    return row


def run_episode_job(payload):
    scene, descriptor, out = payload["scene"], payload["descriptor"], Path(payload["out"])
    skroot = out / descriptor["skeleton_id"]
    skroot.mkdir()
    started = time.perf_counter()
    history = []
    for variant in range(3):
        attempt = skroot / f"geometry_{variant:02d}"
        attempt.mkdir()
        try:
            sk, bundle, pre = plan_episode(scene, descriptor, variant)
            save_json(attempt / "skeleton.json", sk)
            save_json(attempt / "planning_checks.json", pre)
            print(json.dumps({"stage": "calibration", "skeleton": descriptor["skeleton_id"], "geometry_variant": variant}, ensure_ascii=False), flush=True)
            measured, finished, solo, plans = calibrate_episode(scene, sk)
            for a, flight in solo.items():
                np.savez_compressed(attempt / f"single_agent_{a}.npz", time_us=flight["time_us"], p=flight["p"], v=flight["v"], agent_ids=np.array(flight["agent_ids"]))
            calibration = {"core_times_s": measured, "completed_hold_times_s": finished, "timing_plans": plans}
            save_json(attempt / "timing_calibration.json", calibration)
            if plans is None:
                raise PlanningInfeasible("kinematic_infeasible", "single-agent core event or completed hold unobserved")
            interval = episode_interval_check(sk, bundle, plans)
            save_json(attempt / "planning_layer_interval.json", interval)
            if any(interval[mode]["below_warning"] for mode in ("synchronous", "sequential")):
                raise PlanningInfeasible("planning_spacing_rejection", "whole episode actual-delay constant-speed estimate below 6m")
        except PlanningInfeasible as exc:
            item = {"geometry_variant": variant, "category": exc.category, "detail": exc.detail}
            history.append(item)
            save_json(attempt / "planning_rejection.json", item)
            print(json.dumps({"stage": "geometry_rejected", "skeleton": descriptor["skeleton_id"], **item}, ensure_ascii=False), flush=True)
            continue
        save_json(skroot / "skeleton.json", sk)
        save_json(skroot / "planning_checks.json", pre)
        save_json(skroot / "timing_calibration.json", calibration)
        save_json(skroot / "planning_layer_interval.json", interval)
        save_json(skroot / "geometry_history.json", history)
        setup_s = time.perf_counter() - started
        rows = []
        for mode, plan in plans.items():
            run = execute(sk, plan["departure_delays_s"], time_budget=completion_budget(sk, plan["departure_delays_s"], finished))
            rows.append(write_result(scene, descriptor, sk, bundle, run, plan, measured, mode, out, setup_s))
        load_pair(*(skroot / mode for mode in ("synchronous", "sequential")))
        return rows
    save_json(skroot / "planning_rejection.json", {"history": history, "finite_geometry_budget": 3})
    return rejected(descriptor, history)


def run_jobs(jobs, workers):
    if workers == 1:
        return sorted([r for job in jobs for r in run_episode_job(job)], key=lambda r: r["episode_id"])
    pool = ProcessPoolExecutor(max_workers=workers)
    futures = [pool.submit(run_episode_job, job) for job in jobs]
    rows = []
    try:
        for future in as_completed(futures):
            rows.extend(future.result())
    except BaseException:
        for future in futures:
            future.cancel()
        # Only the workers owned by this local batch are terminated on a stop.
        for process in list(pool._processes.values()):
            process.terminate()
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    return sorted(rows, key=lambda r: r["episode_id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--skeletons", nargs="+", required=True)
    args = parser.parse_args()
    out = new_attempt("attempt_s2x_groups_pilot")
    print(f"OUTPUT {out}", flush=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()
    save_json(out / "registration.json", {"commit": commit, "scope": "multi-group development pilot", "workers": args.workers,
                                         "source": str(INFRA_ATTEMPT), "skeleton_ids": args.skeletons, "config_sha256": FROZEN_SHA256})
    start = time.perf_counter()
    try:
        rows = run_jobs(descriptor_jobs(INFRA_ATTEMPT, args.skeletons, out), args.workers)
    except P0ContractError as exc:
        save_json(out / "P0_STOP.json", {"reason": str(exc), "traceback": traceback.format_exc()})
        raise
    save_json(out / "episode_records.json", rows)
    save_json(out / "summary.json", {"episodes": rows, "wall_s": time.perf_counter() - start})


if __name__ == "__main__":
    main()
