"""S2 expansion runner (phase 1): vertical-slice regression and transit pilot.

Step order mirrors scripts/run_v07_s2_minimal.py and calls the same functions;
outputs go only to new attempts under external SwarmData/v07_dataset.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sys
import time
import uuid

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scene_v07.contract import canonical_json
from task_v07.execution import FROZEN_SHA256
from task_v07.io import read_json, save_json, write_episode, load_episode, load_pair, sha
from task_v07.labels import measure
from task_v07.planning import seed_for
from task_v07.expansion.contracts import P0ContractError, condition_digest, permute_input, validate_model_input
from task_v07.expansion.evaluation import truncation_check
from task_v07.expansion.geometry_checks import exact_frame_geometry
from task_v07.expansion.pipeline import plan_group, single_agent_timing, paired_run, timing_plans, PIPELINE_VERSION
from task_v07.expansion.role_evaluation import group_evaluator
from task_v07.expansion.role_planners import PlanningInfeasible, VerticalSliceAdapter, planner_for
from task_v07.expansion.views import make_views
from scripts.audit_v07_s2_exact import audit_episode as vertical_independent_audit
from scripts.audit_v07_s2_infrastructure import audit_geometry
from scripts.audit_v07_s2_roles import audit_role_episode
from scripts.v07_s2_plotting import plot_episode, plot_pair
from scripts.v07_s2x_plotting import plot_role_episode

DEFAULT_DATA = PROJECT.parent.parent / "SwarmData" / "v07_dataset"
REFERENCE_SLICE = DEFAULT_DATA / "attempt_20261014T014017Z_15a6bf38"
INFRA_ATTEMPT = DEFAULT_DATA / "attempt_s2infra_20261014T023604Z_d2566191"
EXPANSION_SCOPE = "S2 expansion development data; fastsim M3 frozen config, 4–10 m/s synthetic extrapolation, no SITL qualification"
PILOT_SKELETONS = ("family_s12_4d13d93f9171c446_ext_000_regular", "family_s12_aa4c66be8e85d64d_ext_000_regular")
WALL_KEYS = {"simulation_wall_s", "single_flight_wall_s", "geometry_and_single_flights_wall_s", "wall_s"}


def new_attempt(prefix):
    out = DEFAULT_DATA / f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    out.mkdir(parents=True, exist_ok=False)
    return out


def scene_digest(scene):
    return hashlib.sha256(canonical_json(scene)).hexdigest()


def episode_audit(scene, sk, run, labels, mode, batches, root, plan, legacy, policy):
    """Same checks as the vertical-slice audit, plus explicit policy geometry."""
    with np.load(root / "truth_10hz.npz", allow_pickle=False) as data:
        reloaded = {**run, **{k: data[k] for k in ("time_us", "p", "v", "a")}, "agent_ids": data["agent_ids"].tolist()}
    observed, _ = measure(scene, sk, reloaded, mode, batches, timing_plan=plan)
    if observed != labels:
        raise P0ContractError("labels disagree with exported truth")
    order = list(reversed(range(len(run["agent_ids"]))))
    alternate = {**reloaded, "agent_ids": [run["agent_ids"][i] for i in order],
                 "p": run["p"][:, order], "v": run["v"][:, order], "a": run["a"][:, order]}
    aligned, _ = measure(scene, sk, alternate, mode, batches, timing_plan=plan)
    for key in ("agents", "task_groups", "cluster"):
        if aligned[key] != labels[key]:
            raise P0ContractError("ID-aligned labels changed under column permutation")
    model = load_episode(root)
    validate_model_input(model)
    permuted = permute_input(model, alternate["agent_ids"])
    if not np.array_equal(permuted["x"], model["x"][:, order]) or not np.array_equal(
            load_episode(root, agent_ids=alternate["agent_ids"])["x"], model["x"][:, order]):
        raise P0ContractError("model columns do not follow physical agent IDs")
    times = [a["observed"]["core_event"]["t_s"] for a in labels["agents"].values()]
    known = [x for x in times if x is not None and x > .2]
    cutoff = min(known) - .1 if known else 1.0
    prefix, _ = measure(scene, sk, reloaded, mode, batches, cutoff_s=cutoff, timing_plan=plan)
    if any(a["observed"]["core_event"]["t_s"] is not None for a in prefix["agents"].values()):
        raise P0ContractError("truncated prefix claims a future core event")
    save_json(root / "prefix_labels.json", prefix)
    minimum_waypoint = min(np.linalg.norm(np.diff(r["points_enu_m"], axis=0), axis=1).min() for r in sk["references"].values())
    if minimum_waypoint < 1:
        raise P0ContractError("sub-metre adjacent waypoint")
    independent = vertical_independent_audit(root) if legacy else audit_role_episode(root)
    save_json(root / "independent_exact_audit.json", independent)
    if independent["status"] != "PASS":
        raise P0ContractError(f"independent full-frame audit failed: {root}")
    targets = {a: sk["target_id"] for a in run["agent_ids"]}
    frame, report = exact_frame_geometry(scene, reloaded, targets, forbidden_layers=policy)
    generic = audit_geometry(scene, reloaded, frame, report, targets, forbidden_layers=policy)
    if generic["status"] != "PASS" or report["minimum_separation_m"] != labels["cluster"]["observed"]["minimum_separation_m"]:
        raise P0ContractError(f"generic policy geometry audit failed: {generic}")
    policy_report = {"policy": policy, "infrastructure_report": report, "independent": generic,
                     "forbidden_region_sample_count": report["forbidden_region_sample_count"]}
    save_json(root / "policy_geometry_audit.json", policy_report)
    return {"independent_status": independent["status"], "region_difference_count": independent["region_difference_count"],
            "target_difference_count": independent["target_difference_count"],
            "event_or_metric_difference_count": independent["event_or_metric_difference_count"],
            "policy_forbidden_samples": report["forbidden_region_sample_count"],
            "generic_geometry_audit": generic["status"], "labels_recomputed_from_saved_10hz": True,
            "id_aligned_permutation_invariant": True, "input_whitelist_passed": True,
            "prefix_without_future_core_events": True, "minimum_adjacent_waypoint_m": float(minimum_waypoint)}


def half_work_truncation(scene, sk, run, labels):
    """Offline test: cutoff at midpoint of measured [first core start, last work end]."""
    starts = [a["observed"]["core_event"]["t_s"] for a in labels["agents"].values()]
    if sk["role"] == "transit":
        ends = [a["observed"]["contribution"]["warning_exit_s"] for a in labels["agents"].values()]
    else:
        return {"status": "not_run", "reason": "half-work truncation for legacy roles is covered by the vertical slice"}
    if any(x is None for x in starts + ends):
        return {"status": "not_run", "reason": "work interval not observed"}
    cutoff = round((min(starts) + max(ends)) / 2, 1)
    result = truncation_check(group_evaluator, scene, sk, {**run, "execution_status": run["execution_status"]}, cutoff)
    result["work_interval_s"] = [min(starts), max(ends)]
    result["full_matches_labels"] = {"success": "yes", "failure": "no"}.get(
        next(iter(labels["task_groups"].values()))["result"]["status"], "unknown") == result["full_verdict"]
    return result


def failed_rows(descriptor, state, reason, out):
    return [{"episode_id": f"{descriptor['skeleton_id']}_{mode}", "family_id": descriptor["family_id"],
             "skeleton_id": descriptor["skeleton_id"], "intent": descriptor["base_intent"], "mode": mode,
             "aborted": descriptor.get("subset") == "aborted", "state": state, "path": None, "reason": reason,
             "quality_valid": None, "audit_passed": None, "task_result": None,
             "condition_digest": condition_digest(descriptor), "agent_ids": descriptor["agent_ids"],
             "scene_digest": None, "coordination_by_group": {}} for mode in ("synchronous", "sequential")]


def run_skeleton_job(payload):
    scene, descriptor, spec, out, scope = (payload[k] for k in ("scene", "descriptor", "planner", "out", "scope"))
    out = Path(out)
    started = time.perf_counter()
    if len(descriptor["task_groups"]) != 1:
        return failed_rows(descriptor, "infeasible", "multi_group_not_in_phase_1", out)
    group = descriptor["task_groups"][0]
    planner = VerticalSliceAdapter(*spec[1:]) if spec[0] == "vertical_slice" else planner_for(group["role"], group["execution_method"])
    legacy = getattr(planner, "legacy_vertical_slice", False)
    skroot = out / descriptor["skeleton_id"]
    skroot.mkdir()
    try:
        sk, bundle, pre = plan_group(scene, descriptor, group, planner)
    except PlanningInfeasible as exc:
        save_json(skroot / "planning_rejection.json", {"category": exc.category, "detail": exc.detail})
        return failed_rows(descriptor, "infeasible", exc.category, out)
    save_json(skroot / "skeleton.json", sk)
    save_json(skroot / "planning_checks.json", pre)
    # Regression reproduces the vertical slice as-is: checks are recorded, not enforced.
    if pre["status"] != "PASS" and payload.get("enforce_precheck", True):
        return failed_rows(descriptor, "infeasible", "planning_check:" + ";".join(pre["failures"][:5]), out)
    planning_s = time.perf_counter() - started
    measured, finished, solo = single_agent_timing(scene, sk)
    drywall = 0.0
    for a, run in solo.items():
        drywall += run["wall_s"]
        np.savez_compressed(skroot / f"single_agent_{a}.npz", time_us=run["time_us"], p=run["p"], v=run["v"],
                            agent_ids=np.array(run["agent_ids"]))
    if any(x is None for x in measured.values()) or any(x is None for x in finished.values()):
        save_json(skroot / "timing_calibration.json", {"core_times_s": measured, "completed_hold_times_s": finished})
        reason = ("single_agent_core_event_unobserved" if any(x is None for x in measured.values())
                  else "kinematic_infeasible:single_agent_not_completed")
        return failed_rows(descriptor, "infeasible", reason, out)
    plans = timing_plans(sk, measured)
    preflight_s = time.perf_counter() - started
    save_json(skroot / "timing_calibration.json", {"source": "single-agent independent fastsim execution, exported 10 Hz",
              "core_times_s": measured, "completed_hold_times_s": finished, "timing_plans": plans,
              "single_flight_wall_s": drywall, "geometry_and_single_flights_wall_s": preflight_s})
    family = descriptor["family_conditions"]
    rows = []
    for mode in ("synchronous", "sequential"):
        episode_started = time.perf_counter()
        plan = plans[mode]
        run, labels, frame = paired_run(scene, sk, plan, finished, mode)
        dest = skroot / mode
        write_episode(dest, scene, family, sk, run, labels, frame, plan["departure_delays_s"], mode, measured,
                      timing_plan=plan, **({} if scope is None else {"scope": scope}))
        audit = episode_audit(scene, sk, run, labels, mode, plan["batch_by_agent"], dest, plan, legacy, pre["policy"])
        truncation = half_work_truncation(scene, sk, run, labels)
        save_json(dest / "truncation_check.json", truncation)
        if truncation["status"] == "FAIL":
            raise P0ContractError(f"half-work prefix claimed success: {dest}")
        title = f"{descriptor['base_intent']} | {sk.get('approach_mode', 'vertical slice')} | assigned {mode}"
        if legacy:
            plot_episode(scene, run, labels, dest / "topdown.png", title, skeleton=sk)
        else:
            plot_role_episode(scene, run, labels, sk, dest / "topdown.png", title)
        group_label = labels["task_groups"][sk["group_id"]]
        coord = group_label["observed"]["coordination"]
        row = {"episode_id": f"{descriptor['skeleton_id']}_{mode}", "family_id": descriptor["family_id"],
               "skeleton_id": descriptor["skeleton_id"], "intent": descriptor["base_intent"], "mode": mode,
               "aborted": False, "state": "generated" if labels["generation_quality"]["retained"] else "generation_error",
               "path": dest.relative_to(out).as_posix(), "reason": None if labels["generation_quality"]["retained"] else "minimum_separation_below_2m",
               "quality_valid": labels["generation_quality"]["retained"], "audit_passed": audit["independent_status"] == "PASS",
               "task_result": group_label["result"]["status"], "condition_digest": condition_digest(descriptor, bundle),
               "agent_ids": sk["agent_ids"], "scene_digest": scene_digest(scene),
               "coordination_by_group": {sk["group_id"]: coord["classification"]},
               "role": sk["role"], "approach_mode": sk.get("approach_mode"), "member_count": len(sk["members"]),
               "cruise_speed_m_s": sk["cruise_speed_m_s"], "execution_status": run["execution_status"],
               "observed_coordination": coord["classification"], "event_times_s": coord["event_times_s"],
               "event_range_s": coord["event_range_s"], "observed_batches": coord["batches"],
               "coordination_matches": group_label["observed"]["timing_diagnostics"]["coordination_matches_assignment"],
               "batch_members_match": group_label["observed"]["timing_diagnostics"]["batch_members_match_assignment"],
               "assigned_batches": plan["batch_by_agent"], "task_conditions": group_label["result"]["conditions"],
               "approach_span_deg": group_label["observed"]["approach_span_deg"],
               "minimum_separation_m": labels["cluster"]["observed"]["minimum_separation_m"],
               "duration_s": run["end_us"] / 1e6, "time_budget": run["time_budget"], "audit": audit,
               "truncation": {k: truncation.get(k) for k in ("status", "full_verdict", "prefix_verdict", "cutoff_s")},
               "episode_wall_s": time.perf_counter() - episode_started, "amortized_skeleton_setup_s": preflight_s / 2,
               "planning_wall_s": planning_s}
        row["end_to_end_wall_s"] = row["episode_wall_s"] + preflight_s / 2
        save_json(dest / "metrics.json", row)
        rows.append(row)
    load_pair(*(skroot / m for m in ("synchronous", "sequential")))
    plot_pair(rows, skroot / "timing_pair.png", f"{descriptor['base_intent']} / {sk.get('approach_mode', 'vertical slice')} / {descriptor['skeleton_id'][-22:]}")
    return rows


def run_jobs(jobs, workers):
    if workers == 1:
        blocks = list(map(run_skeleton_job, jobs))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            blocks = list(pool.map(run_skeleton_job, jobs))
    return sorted((r for block in blocks for r in block), key=lambda r: r["episode_id"])


# ---------------------------------------------------------------- comparisons

def deep_diff(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for key in sorted(set(a) | set(b)):
            sub = f"{path}.{key}" if path else key
            if key not in a or key not in b:
                out.append({"path": sub, "reference": a.get(key, "<absent>"), "new": b.get(key, "<absent>")})
            else:
                out.extend(deep_diff(a[key], b[key], sub))
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in deep_diff(x, y, f"{path}[{i}]")]
    return [] if a == b and type(a) == type(b) else [{"path": path, "reference": a, "new": b}]


def npz_diff(left, right):
    with np.load(left, allow_pickle=False) as x, np.load(right, allow_pickle=False) as y:
        keys = sorted(set(x.files) | set(y.files))
        return [k for k in keys if k not in x.files or k not in y.files or not np.array_equal(x[k], y[k])]


def classify(path):
    leaf = path.split(".")[-1].split("[")[0]
    if leaf in WALL_KEYS:
        return "metadata:wall_clock"
    if path.startswith("artifact_sha256.source.json"):
        return "metadata:hash_of_file_with_wall_clock"
    if leaf in ("scope",):
        return "metadata:text"
    return "content"


def compare_episode_dirs(reference, new, files_json, files_npz, files_csv):
    rows = []
    for name in files_json:
        for d in deep_diff(read_json(reference / name), read_json(new / name)):
            rows.append({"file": name, **d, "class": classify(d["path"])})
    for name in files_npz:
        for key in npz_diff(reference / name, new / name):
            rows.append({"file": name, "path": key, "class": "content"})
    for name in files_csv:
        if sha(reference / name) != sha(new / name):
            rows.append({"file": name, "path": "<sha256>", "class": "content"})
    return rows


def vertical_request(scene, family, intent, index, target):
    """Request record for one vertical-slice skeleton, as an expansion descriptor."""
    ids = sorted(s["agent_id"] for s in family["initial_states"])
    column_seed = seed_for(family["sampling_seed"], f"column:{index}")
    order = ids[:]
    random.Random(column_seed).shuffle(order)
    role, method = (("intrusion", "polygon_visit") if intent == "penetration" else ("reconnaissance", "annular_sector_lawnmower"))
    return {"schema_version": "traj2language.s2x_vertical_request/0.7.1",
            "skeleton_id": f"{family['family_id']}_s2r3_sk{index:02d}", "family_id": family["family_id"],
            "map_id": family["map_id"], "base_intent": intent, "subset": "regular",
            "common_draw": {"approach_mode": "vertical_slice_fixed"},
            "task_groups": [{"group_id": "task_group_01", "target_id": target, "role": role,
                             "execution_method": method, "members": ids, "source_units": ["unit_01"],
                             "between_group_offset_s": 0.0}],
            "agent_ids": order, "column_seed": column_seed, "role_seed": 0,
            "cruise_speed_m_s": family["cruise_speed_m_s"], "task_altitude_m": family["task_altitude_m"],
            "family_conditions": family}


def regression(args):
    reference = Path(args.reference)
    registration = read_json(reference / "registration.json")
    candidates = read_json(Path(registration["scene_attempt"]) / "candidates.json")
    out = new_attempt("attempt_s2x_regress")
    print(f"OUTPUT {out}", flush=True)
    started = time.perf_counter()
    jobs = []
    for index_candidate in registration["candidates"]:
        source = Path(candidates[index_candidate]["directory"])
        scene = read_json(source / "public_scene.json"); family = read_json(source / "family_initial.json")
        target = random.Random(seed_for(family["sampling_seed"], "task_unit_target")).choice(
            sorted(e["id"] for e in scene["entities"] if e["type"] == "facility"))
        for index, intent in enumerate(("penetration", "reconnaissance")):
            jobs.append({"scene": scene, "descriptor": vertical_request(scene, family, intent, index, target),
                         "planner": ("vertical_slice", intent, index), "out": str(out), "scope": None,
                         "enforce_precheck": False})
    save_json(out / "registration.json", {"scope": "S2 expansion phase 1: vertical-slice regression through the new pipeline",
              "reference_attempt": str(reference), "scene_attempt": registration["scene_attempt"],
              "candidates": registration["candidates"], "workers": args.workers, "pipeline_version": PIPELINE_VERSION,
              "config_sha256": FROZEN_SHA256})
    rows = run_jobs(jobs, args.workers)
    missing = [r["episode_id"] for r in rows if r["path"] is None]
    if missing:
        save_json(out / "regression_comparison.json", {"status": "FAIL", "not_executed": missing, "rows": rows})
        print(f"FAIL not executed: {missing}", flush=True)
        return 1
    comparisons = []
    for row in rows:
        ref_dir = reference / row["skeleton_id"] / row["mode"]; new_dir = out / row["path"]
        diffs = compare_episode_dirs(ref_dir, new_dir,
                                     ["labels.json", "prefix_labels.json", "task.json", "source.json", "manifest.json",
                                      "public_scene.json", "independent_exact_audit.json"],
                                     ["truth_10hz.npz", "model_input.npz", "frame_labels.npz"],
                                     ["truth.csv", "observations.csv"])
        diffs = [d for d in diffs if not (d["file"] == "independent_exact_audit.json" and d["path"] == "directory")] + \
                [{"file": "independent_exact_audit.json", "path": "directory", "class": "metadata:path"}]
        checks = read_json(out / row["skeleton_id"] / "planning_checks.json")
        rule5 = {a: {fid: c for fid, c in r["clearances"].items() if not c["valid"]}
                 for a, r in checks["retreat_points"].items() if not r["valid"]}
        comparisons.append({"episode": f"{row['skeleton_id']}/{row['mode']}", "differences": diffs,
                            "content_differences": sum(d["class"] == "content" for d in diffs),
                            "labels_json_identical": not any(d["file"] == "labels.json" for d in diffs),
                            "rule5_retreat_point_check": {
                                "applies": bool(checks["retreat_points"]), "violations": rule5,
                                "status": "not_applicable" if not checks["retreat_points"] else "VIOLATION" if rule5 else "PASS",
                                "note": ("Vertical-slice development sample kept as-is (not regenerated): its survey "
                                         "retreat point was checked only against the target warning zone.") if rule5 else None}})
    skeletons = []
    for skeleton_id in sorted({r["skeleton_id"] for r in rows}):
        diffs = compare_episode_dirs(reference / skeleton_id, out / skeleton_id, ["skeleton.json", "timing_calibration.json"],
                                     [p.name for p in sorted((reference / skeleton_id).glob("single_agent_*.npz"))], [])
        skeletons.append({"skeleton_id": skeleton_id, "differences": diffs,
                          "content_differences": sum(d["class"] == "content" for d in diffs)})
    content = sum(c["content_differences"] for c in comparisons) + sum(s["content_differences"] for s in skeletons)
    summary = {"status": "PASS" if content == 0 and len(comparisons) == 8 else "FAIL", "episodes": len(comparisons),
               "labels_identical": sum(c["labels_json_identical"] for c in comparisons),
               "content_difference_count": content,
               "planning_checks_recorded_not_enforced": {s: read_json(out / s / "planning_checks.json")["failures"]
                                                          for s in sorted({r["skeleton_id"] for r in rows})},
               "metadata_differences": sorted({(d["file"], d["path"].split("[")[0], d["class"]) for c in comparisons + skeletons
                                               for d in c["differences"] if d["class"] != "content"}),
               "episode_comparisons": comparisons, "skeleton_comparisons": skeletons,
               "rows": rows, "total_wall_s": time.perf_counter() - started}
    save_json(out / "regression_comparison.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k in ("status", "episodes", "labels_identical", "content_difference_count", "metadata_differences", "total_wall_s")}, ensure_ascii=False, indent=1), flush=True)
    return 0 if summary["status"] == "PASS" else 1


def descriptor_jobs(infra, skeleton_ids, out):
    descriptors = {d["skeleton_id"]: d for d in read_json(Path(infra) / "private_skeleton_descriptors.json")}
    registration = read_json(Path(infra) / "registration.json")
    candidates = {c["candidate_index"]: c for c in read_json(Path(registration["source_attempt"]) / "candidates.json")}
    scenes = {}
    for row in registration["selected"]:
        directory = Path(candidates[row["candidate_index"]]["directory"])
        for name, digest in row["source_sha256"].items():
            if sha(directory / name) != digest:
                raise P0ContractError(f"Source map changed since descriptor sampling: {directory / name}")
        scenes[row["family_id"]] = read_json(directory / "public_scene.json")
    return [{"scene": scenes[descriptors[s]["family_id"]], "descriptor": descriptors[s], "planner": ("role",),
             "out": str(out), "scope": EXPANSION_SCOPE} for s in skeleton_ids]


def pilot(args):
    out = new_attempt("attempt_s2x_p1")
    print(f"OUTPUT {out}", flush=True)
    started = time.perf_counter()
    save_json(out / "registration.json", {"scope": "S2 expansion phase 1: transit pilot (2 skeletons x 2 timing versions)",
              "descriptor_attempt": str(args.descriptors), "skeleton_ids": list(args.skeletons),
              "selection": "first single-group transit descriptor in skeleton_id order per approach mode; no feasibility filtering",
              "workers": args.workers, "process_check_workers": 1, "pipeline_version": PIPELINE_VERSION,
              "config_sha256": FROZEN_SHA256})
    rows = run_jobs(descriptor_jobs(args.descriptors, args.skeletons, out), args.workers)
    pilot_s = time.perf_counter() - started
    check_root = out / "process_check_workers1"
    check_root.mkdir()
    check_started = time.perf_counter()
    check_rows = run_jobs(descriptor_jobs(args.descriptors, args.skeletons, check_root), 1)
    process = []
    for left, right in zip(rows, check_rows):
        if left["episode_id"] != right["episode_id"]:
            raise P0ContractError("Process check episode order mismatch")
        if left["path"] is None:
            process.append({"episode": left["episode_id"], "differences": [] if left["reason"] == right["reason"] else ["reason"]})
            continue
        diffs = compare_episode_dirs(out / left["path"], check_root / right["path"],
                                     ["labels.json", "task.json", "prefix_labels.json", "truncation_check.json",
                                      "independent_exact_audit.json", "policy_geometry_audit.json"],
                                     ["truth_10hz.npz", "model_input.npz", "frame_labels.npz"], ["truth.csv", "observations.csv"])
        diffs = [d for d in diffs if d["class"] == "content" and d["path"] != "directory"]
        process.append({"episode": left["episode_id"], "differences": diffs})
    for skeleton_id in sorted({r["skeleton_id"] for r in rows}):
        diffs = compare_episode_dirs(out / skeleton_id, check_root / skeleton_id, ["skeleton.json", "timing_calibration.json"], [], [])
        process.append({"skeleton": skeleton_id, "differences": [d for d in diffs if d["class"] == "content"]})
    process_status = "PASS" if all(not p["differences"] for p in process) else "FAIL"
    save_json(out / "episode_records.json", rows)
    save_json(out / "views.json", make_views([{k: r.get(k) for k in ("episode_id", "family_id", "skeleton_id", "intent", "mode",
              "aborted", "state", "path", "reason", "quality_valid", "audit_passed", "task_result", "condition_digest",
              "agent_ids", "scene_digest", "coordination_by_group")} for r in rows]))
    summary = {"status": "completed", "process_count_check": {"status": process_status, "workers": [args.workers, 1],
               "items": process, "process_check_wall_s": time.perf_counter() - check_started},
               "episodes": rows, "pilot_wall_s": pilot_s, "total_wall_s": time.perf_counter() - started}
    save_json(out / "summary.json", summary)
    print(json.dumps({"process_check": process_status, "pilot_wall_s": pilot_s,
                      "episodes": [{k: r.get(k) for k in ("episode_id", "state", "task_result", "observed_coordination",
                                                          "coordination_matches", "batch_members_match", "approach_span_deg",
                                                          "minimum_separation_m", "end_to_end_wall_s", "reason")} for r in rows]},
                     ensure_ascii=False, indent=1), flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("regression")
    reg.add_argument("--reference", type=Path, default=REFERENCE_SLICE)
    reg.add_argument("--workers", type=int, default=2)
    pil = sub.add_parser("pilot")
    pil.add_argument("--descriptors", type=Path, default=INFRA_ATTEMPT)
    pil.add_argument("--skeletons", nargs="+", default=list(PILOT_SKELETONS))
    pil.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    return regression(args) if args.command == "regression" else pilot(args)


if __name__ == "__main__":
    raise SystemExit(main())
