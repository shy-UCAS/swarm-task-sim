"""Read-only four-threshold geometry experiment; never starts Q2 or simulation.

Only in-memory config copies differ. The production functions return unchanged
results; observational wrappers record local draws and the original episode
combiner receives the already-checked fixed/experimental pools.
"""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.run_v07_m3_trial import atomic, frozen_check
from scripts.run_v07_s2_expansion import descriptor_jobs
from task_v07.io import read_json, sha
from task_v07.expansion.contracts import P0ContractError
from task_v07.expansion.pipeline import assemble_skeleton, exclusion_policy, precheck
from task_v07.expansion.search_diagnostics import rejection
from task_v07.expansion.group_candidate_pool import independent_episode_pool
from task_v07.unified.geometry_config import load_geometry
from task_v07.unified.spec import build_spec, proposal_seed
from task_v07.unified.free_space import free_space, work_region
from task_v07.unified.shapes import draw_shape
from task_v07.unified.route import route_group, GeometryRejected
from task_v07.unified.checks import plan_checks

EVIDENCE = PROJECT / "docs/v07/evidence/m3"
SID = "family_s12_4d13d93f9171c446_ext_007_regular"
GID = "task_group_02"
THRESHOLDS = (150, 145, 140, 135)
BASELINE = "7e67fa232c1a3c2a2540dd612d85797bb56276c9"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def distribution(values):
    values = [float(v) for v in values if v is not None]
    return {"count": len(values), "min": min(values) if values else None,
            "median": statistics.median(values) if values else None,
            "max": max(values) if values else None}


class ObservedRandom:
    """Delegate to an ordinary Random; subclassing it would change choice's RNG."""
    def __init__(self, seed=None, *, original=None):
        self.original = random.Random(seed) if original is None else original
        self.events = []

    def __deepcopy__(self, memo):
        result = type(self)(original=deepcopy(self.original, memo))
        result.events = deepcopy(self.events, memo)
        return result

    def uniform(self, a, b):
        value = self.original.uniform(a, b)
        self.events.append({"method": "uniform", "bounds": [a, b], "value": value})
        return value

    def choice(self, sequence):
        value = self.original.choice(sequence)
        self.events.append({"method": "choice", "choices": list(sequence), "value": value})
        return value

    def random(self):
        value = self.original.random()
        self.events.append({"method": "random", "value": value})
        return value

    def __getattr__(self, name):
        return getattr(self.original, name)


def compact_evidence(evidence):
    """Keep counts and representative locations, avoiding duplicate full routes."""
    issues = [e for e in evidence if isinstance(e, dict)]
    return {"issue_count": len(evidence),
            "entity_counts": dict(Counter(e.get("entity_id", "unspecified") for e in issues)),
            "phase_counts": dict(Counter(e.get("phase", "unspecified") for e in issues)),
            "first_issue": deepcopy(evidence[0]) if evidence else None}


def checked_proposal(scene, descriptor, group, cfg, free, region, index):
    """The production adapter's stages, with explicit config and observations."""
    spec = build_spec(descriptor, group, cfg)
    seed = proposal_seed(spec, index)
    rng = ObservedRandom(seed)
    started = time.perf_counter()
    record = {"candidate_index": index, "proposal_seed": seed, "group_id": group["group_id"],
              "stage": "shape", "reason": None, "rejection": None, "local_draws": []}
    patrol = importlib.import_module("task_v07.unified.patrol_shape")
    construction = importlib.import_module("task_v07.unified.construction")
    original_patrol = patrol.patrol_shape
    original_common = patrol.common_arcs
    original_precheck = construction.precheck_operation
    current = [None]

    def observe_common(spec_arg, free_arg, radii, **kwargs):
        row = current[0]
        if row is not None and "entry" not in kwargs:
            row["radii_by_split_m"] = deepcopy(radii)
        try:
            result = original_common(spec_arg, free_arg, radii, **kwargs)
        except GeometryRejected as exc:
            if row is not None and "entry" in kwargs:
                row["sampled_entry"] = {"start_rad": kwargs["entry"][0], "rotation_sign": kwargs["entry"][1],
                                        "status": "REJECT", "reason": exc.reason}
            raise
        if row is not None:
            if "entry" in kwargs:
                row["sampled_entry"] = {"start_rad": kwargs["entry"][0], "rotation_sign": kwargs["entry"][1], "status": "PASS"}
            else:
                arcs, complete = result
                row.update(available_arcs_rad=deepcopy(arcs), full_domain=complete,
                           available_max_deg=math.degrees(max((b-a for a,b in arcs), default=0.)))
        return result

    def observe_patrol(spec_arg, free_arg, rng_arg, draw, **kwargs):
        row = {"shape_attempt": draw["shape_attempt"], "draw": deepcopy(draw),
               "work_and_ingress_pass": False, "shape_accepted": False}
        record["local_draws"].append(row)
        current[0] = row
        offset = max(0, len(rng_arg.events)-1)
        try:
            result = original_patrol(spec_arg, free_arg, rng_arg, draw, **kwargs)
            row["builder_status"] = "PASS"
            row["draw"] = deepcopy(draw)
            return result
        except GeometryRejected as exc:
            row.update(builder_status="REJECT", reason=exc.reason, evidence=compact_evidence(exc.evidence))
            raise
        finally:
            row["random_events"] = deepcopy(rng_arg.events[offset:])
            span_draws = [event["value"] for event in row["random_events"] if event["method"] == "uniform"
                          and abs(event["bounds"][0]-math.radians(spec_arg["params"]["arc_min_deg"])) < 1e-12]
            row["sampled_arc_span_deg"] = math.degrees(span_draws[-1]) if span_draws else None
            row["draw"].update(deepcopy(draw))
            current[0] = None

    def observe_precheck(spec_arg, free_arg, shape, rng_arg):
        row = record["local_draws"][-1]
        try:
            result = original_precheck(spec_arg, free_arg, shape, rng_arg)
        except GeometryRejected as exc:
            row["work_and_ingress_pass"] = exc.reason != "ingress_line_blocked"
            raise
        row["work_and_ingress_pass"] = True
        row["shape_accepted"] = True
        return result

    candidate = None
    try:
        with patch.object(patrol, "common_arcs", observe_common), patch.object(patrol, "patrol_shape", observe_patrol), patch.object(construction, "precheck_operation", observe_precheck):
            shape = draw_shape(spec, region, rng, free)
        local_rejects = shape["draw"].get("rejected_shape_attempts", [])
        record["accepted_shape_draw"] = {k: deepcopy(v) for k,v in shape["draw"].items() if k != "rejected_shape_attempts"}
        record["stage"] = "connection"
        bundle, template = route_group(scene, spec, shape, free, descriptor["family_conditions"]["initial_states"], rng)
        template["task_spec"] = spec
        record["stage"] = "whole_route"
        checks = plan_checks(scene, spec, bundle, template, free, descriptor["family_conditions"]["initial_states"])
        record["whole_route_checks"] = checks
        if checks["status"] != "PASS":
            raise GeometryRejected("whole_route_check", checks["issues"])
        skeleton = assemble_skeleton(descriptor, group, bundle, template, False)
        policy = exclusion_policy(scene, group["role"], group["target_id"], group["members"])
        skeleton["exclusion_policy"] = policy
        existing = precheck(scene, skeleton, bundle, policy)
        if existing["status"] != "PASS":
            raise GeometryRejected("existing_output_precheck", [existing])
        skeleton["agent_ids"] = [a for a in descriptor["agent_ids"] if a in group["members"]]
        skeleton["between_group_offset_s"] = group["between_group_offset_s"]
        checks["existing_precheck"] = existing
        candidate = {"index": index, "cost": template["approach_length_m"], "skeleton": skeleton,
                     "bundle": bundle, "checks": checks, "bearing_deg": template["work_area_bearing_deg"],
                     "target_id": group["target_id"]}
        if set(bundle.waypoints_by_agent) != set(group["members"]):
            raise P0ContractError("Counterfactual route changed group members")
        record.update(stage="group_feasible", approach_length_m=template["approach_length_m"],
                      work_area_bearing_deg=template["work_area_bearing_deg"],
                      geometry_provenance={k: deepcopy(v) for k,v in template.get("geometry_provenance", {}).items() if k != "shape"})
    except GeometryRejected as exc:
        record.update(reason=exc.reason, rejection=rejection(exc.reason, scope="proposal", evidence=exc.evidence,
                                                            exhausted=exc.reason.endswith("budget_exhausted")))
        if exc.reason == "connection_search_budget_exhausted":
            record["connection_rejections"] = [{"attempt": e.get("attempt"), "reason": e.get("reason"),
                                                   "evidence": compact_evidence(e.get("evidence", []))}
                                                  for e in exc.evidence]
        local_rejects = exc.evidence if exc.reason == "shape_search_budget_exhausted" else (
            shape["draw"].get("rejected_shape_attempts", []) if "shape" in locals() else [])
    for local in local_rejects:
        attempt = local.get("draw", {}).get("shape_attempt")
        if attempt is not None and attempt < len(record["local_draws"]):
            row = record["local_draws"][attempt]
            row.update(reason=local["reason"], evidence=compact_evidence(local.get("evidence", [])))
    record.update(wall_s=time.perf_counter()-started, random_events=rng.events)
    # The nested source rejection is duplicated by local_draws; retain its code
    # and summarized evidence rather than storing the same large objects twice.
    if record["rejection"]:
        evidence = record["rejection"].pop("geometric_evidence", [])
        record["rejection"]["geometric_evidence_summary"] = compact_evidence(evidence)
    return candidate, record


def pool_report(records, pool):
    reasons = Counter(r["reason"] for r in records if r["reason"])
    wall = sum(r["wall_s"] for r in records)
    return {"records": records, "rejection_reasons": dict(reasons), "metrics": {
        "attempts": len(records), "budget": 200, "feasible_candidates": len(pool), "wall_s": wall,
        "geometry_wall_s": wall, "backend": "unified-explicit-memory-config", "phase_search": {"evaluations": 0, "wall_s": 0.}},
        "termination": None if pool else rejection("group_pool_empty_after_registered_budget", scope="group_search", exhausted=True)}


def evaluate_threshold(payload):
    threshold, scene, descriptor, fixed_pools, fixed_reports = payload
    started = time.perf_counter()
    cfg = deepcopy(load_geometry()); cfg["monitoring"]["arc_min_deg"] = threshold
    official = deepcopy(load_geometry()); normalized = deepcopy(cfg); normalized["monitoring"]["arc_min_deg"] = 150
    if normalized != official: raise P0ContractError("Counterfactual changed another geometry parameter")
    group = next(g for g in descriptor["task_groups"] if g["group_id"] == GID)
    spec = build_spec(descriptor, group, cfg); free = free_space(scene, spec, cfg); region = work_region(scene, spec, free)
    descriptor_hash = digest(descriptor); scene_hash = digest(scene)
    records = []; pool = []
    for index in range(200):
        candidate, record = checked_proposal(scene, descriptor, group, cfg, free, region, index)
        records.append(record)
        if candidate is not None: pool.append(candidate)
        if (index+1) % 25 == 0:
            print(json.dumps({"threshold": threshold, "completed_proposals": index+1, "qualified_groups": len(pool), "wall_s": time.perf_counter()-started}), flush=True)
    if digest(descriptor) != descriptor_hash or digest(scene) != scene_hash:
        raise P0ContractError("Counterfactual mutated registered input")
    pools = {**fixed_pools, GID: pool}; reports = {**fixed_reports, GID: pool_report(records, pool)}
    def use_checked_pool(scene_arg, descriptor_arg, group_arg, budget=200, **kwargs):
        if budget != 200 or digest(scene_arg) != scene_hash or digest(descriptor_arg) != descriptor_hash:
            raise P0ContractError("Combination input differs from registered experiment")
        return pools[group_arg["group_id"]], reports[group_arg["group_id"]]
    # Only supply completed pools. The original random Cartesian selection,
    # bearing gate, assemble_episode, identity contracts and eligible filter run.
    with patch("task_v07.expansion.group_candidate_pool.build_group_pool", use_checked_pool):
        eligible, combined = independent_episode_pool(scene, descriptor, budget=200)
    for chosen in eligible:
        if set(chosen["bundle"].waypoints_by_agent) != set(descriptor["agent_ids"]):
            raise P0ContractError("Assembled counterfactual changed skeleton identity")
        if not all(check["status"] == "PASS" for check in chosen["checks"].values()):
            raise P0ContractError("Assembled counterfactual contains a rejected group")
    local = [draw for r in records for draw in r["local_draws"]]
    shape_draws = [r["accepted_shape_draw"] for r in records if "accepted_shape_draw" in r]
    group_draws = [r["accepted_shape_draw"] for r in records if r["stage"] == "group_feasible"]
    local_reasons = Counter(row["reason"] for row in local if row.get("reason"))
    actual_spans = [d["arc_span_deg"] for d in shape_draws if d.get("arc_span_deg") is not None]
    summary = {
        "tested_arc_min_deg": threshold, "type": "official" if threshold == 150 else "unapproved_diagnostic_hypothesis",
        "completed_proposals": len(records), "proposal_indices": list(range(200)), "local_shape_attempts": len(local),
        "layers": {
            "available_arc_at_least_threshold": sum(d.get("available_max_deg", 0) >= threshold for d in local),
            "local_work_and_ingress_pass": sum(d["work_and_ingress_pass"] for d in local),
            "draw_shape_accepted_proposals": len(shape_draws),
            "complete_group_plan_checks_pass": len(pool),
            "complete_eligible_skeleton_combinations": len(eligible)},
        "fixed_group_candidate_counts": {g: len(p) for g,p in fixed_pools.items()},
        "qualified_group_proposal_indices": [p["index"] for p in pool],
        "available_arc_deg": distribution(d.get("available_max_deg") for d in local),
        "accepted_shape_arc_deg": distribution(actual_spans),
        "accepted_shape_nominal_margin_above_120_deg": distribution(v-120 for v in actual_spans),
        "qualified_group_arc_deg": distribution(d.get("arc_span_deg") for d in group_draws),
        "accepted_shape_radius_m": distribution(d.get("innermost_offset_m") for d in shape_draws),
        "accepted_shape_entry_phase_deg": distribution(d.get("accepted_start_direction_deg") for d in shape_draws),
        "qualified_group_entry_phase_deg": distribution(d.get("accepted_start_direction_deg") for d in group_draws),
        "accepted_shape_rotation_counts": dict(Counter(d.get("rotation_sign") for d in shape_draws)),
        "local_rejection_reasons": dict(local_reasons),
        "local_rejection_entity_counts": dict(sum((Counter(d.get("evidence", {}).get("entity_counts", {})) for d in local), Counter())),
        "local_rejection_phase_counts": dict(sum((Counter(d.get("evidence", {}).get("phase_counts", {})) for d in local), Counter())),
        "ingress_rejected_local_shapes": local_reasons.get("ingress_line_blocked", 0),
        "other_rejected_local_shapes": sum(v for k,v in local_reasons.items() if k != "ingress_line_blocked"),
        "proposal_rejection_stages": dict(Counter(r["stage"] for r in records if r["reason"])),
        "proposal_rejection_reasons": dict(Counter(r["reason"] for r in records if r["reason"])),
        "connection_attempt_rejection_reasons": dict(Counter(e["reason"] for r in records for e in r.get("connection_rejections", []))),
        "whole_route_issue_codes": dict(Counter(i.get("code", "unspecified") for r in records for i in r.get("whole_route_checks", {}).get("issues", []))),
        "combination_search": combined["combination_search"],
        "combination_rejection_reasons": combined["combination_rejection_reasons"],
        "combination_records": combined["combination_records"],
        "eligible_candidate_order": combined["eligible_candidate_order"],
        "eligible_group_candidate_indices": [c["group_candidate_indices"] for c in eligible],
        "selection": combined["selection"], "records": records,
        "input_unchanged": True, "wall_s": time.perf_counter()-started}
    return summary


def main():
    started = time.perf_counter(); stamp = datetime.now(timezone.utc).isoformat()
    output = EVIDENCE / "m3b_arc_counterfactual.json"
    if output.exists(): raise FileExistsError("Counterfactual evidence already exists; do not overwrite an executed experiment")
    cfg_path = PROJECT / "configs/generator/geometry_v07_r1.json"
    production_cfg_hash = sha(cfg_path)
    official = deepcopy(load_geometry())
    observed, ordinary = ObservedRandom(18493), random.Random(18493)
    for _ in range(100):
        if (observed.uniform(2,8), observed.choice((-1,1)), observed.random()) != (
                ordinary.uniform(2,8), ordinary.choice((-1,1)), ordinary.random()):
            raise P0ContractError("Random observation changed the original stream")
    if official["monitoring"]["arc_min_deg"] != 150: raise P0ContractError("Official monitoring minimum changed")
    if (official["shape_attempts"], official["connection_attempts"]) != (20,10): raise P0ContractError("Local budgets changed")
    reg = read_json(EVIDENCE / "m3b_inputs.json"); frozen_before = frozen_check(reg)
    latest = read_json(EVIDENCE / "m3b_fix_q2.json")
    attempt = Path(latest["attempt"]); source_registration = read_json(attempt / "registration.json")
    source_pool_path = attempt / SID / "candidate_pool.json"; source_pool = read_json(source_pool_path)
    job = descriptor_jobs(Path(source_registration["descriptor_attempt"]), [SID], EVIDENCE)[0]
    scene, descriptor = job["scene"], job["descriptor"]
    fixed_pools = {}; fixed_reports = {}; fixed_records = {}
    for group in sorted(descriptor["task_groups"], key=lambda g:g["group_id"]):
        gid = group["group_id"]
        if gid == GID: continue
        indices = source_pool["group_feasible_candidate_indices"][gid]
        if gid != "task_group_01" or indices != [38,66,112,151]: raise P0ContractError("Unexpected registered fixed candidate pool")
        spec = build_spec(descriptor, group, official); free = free_space(scene, spec, official); region = work_region(scene, spec, free)
        fixed_pools[gid] = []; fixed_records[gid] = []
        for index in indices:
            candidate, record = checked_proposal(scene, descriptor, group, official, free, region, index)
            fixed_records[gid].append(record)
            if candidate is None: raise P0ContractError(f"Previously accepted fixed candidate failed after F2b: {gid}/{index}")
            fixed_pools[gid].append(candidate)
        fixed_reports[gid] = pool_report(fixed_records[gid], fixed_pools[gid])
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()
    invariant_hashes = {p.relative_to(PROJECT).as_posix(): sha(p) for p in [*list((PROJECT/"task_v07").rglob("*.py")), *list((PROJECT/"configs").rglob("*.json"))]}
    results = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(evaluate_threshold, (threshold, scene, descriptor, fixed_pools, fixed_reports)) for threshold in THRESHOLDS]
        for future in as_completed(futures):
            result = future.result(); results.append(result)
            print(json.dumps({"threshold_complete": result["tested_arc_min_deg"], "layers": result["layers"]}), flush=True)
    results.sort(key=lambda r:-r["tested_arc_min_deg"])
    if sha(cfg_path) != production_cfg_hash or load_geometry() != official: raise P0ContractError("Production config or its cache changed")
    changed = [path for path,h in invariant_hashes.items() if sha(PROJECT/path) != h]
    if changed: raise P0ContractError(f"Production runtime changed during counterfactual: {changed}")
    if any([r["proposal_seed"] for r in row["records"]] != [r["proposal_seed"] for r in results[0]["records"]] for row in results[1:]):
        raise P0ContractError("Threshold experiments used different derived seeds")
    full = [r["tested_arc_min_deg"] for r in results if r["layers"]["complete_eligible_skeleton_combinations"]]
    interpretation = (
        "T0 has a complete legal geometry candidate after F2b; no parameter change is indicated by this experiment." if 150 in full else
        "Only diagnostic lower thresholds have complete legal geometry combinations in this finite budget; user review and B boundary analysis are required before any parameter decision." if full else
        "None of the four thresholds forms a complete legal skeleton in the registered finite budget; arc length is not sufficient to resolve the remaining geometry constraints.")
    report = {"experiment": "monitoring_arc_counterfactual_geometry_only", "baseline_commit": BASELINE,
        "entry_commit": head, "script_sha256": sha(Path(__file__)), "started_utc": stamp,
        "finished_utc": datetime.now(timezone.utc).isoformat(), "wall_s": time.perf_counter()-started,
        "skeleton_id": SID, "group_id": GID, "official_arc_min_deg": 150,
        "tested_arc_min_deg": list(THRESHOLDS), "production_config_modified": False,
        "production_config_cache_modified": False, "production_config_sha256": production_cfg_hash,
        "source_attempt": str(attempt), "source_registration_sha256": sha(attempt/"registration.json"),
        "source_candidate_pool_sha256": sha(source_pool_path), "source_q2_evidence_sha256": sha(EVIDENCE/"m3b_fix_q2.json"),
        "descriptor_attempt": source_registration["descriptor_attempt"],
        "descriptor_file_sha256": sha(Path(source_registration["descriptor_attempt"])/"private_skeleton_descriptors.json"),
        "scene_canonical_sha256": digest(scene), "descriptor_canonical_sha256": digest(descriptor),
        "public_split": build_spec(descriptor, next(g for g in descriptor["task_groups"] if g["group_id"]==GID), official)["public_split"],
        "frozen_before": frozen_before, "frozen_after": frozen_check(reg),
        "budgets": {"group_proposals":200,"local_shapes_per_proposal":20,"connections_per_proposal":10,"combinations":1000},
        "fixed_group_selection": "All four latest-Q2 accepted g01 proposal IDs, recomputed with official 150-degree config after F2b; identical pool reused for all thresholds.",
        "fixed_group_records": fixed_records, "results": results,
        "production_runtime_unchanged": True, "all_thresholds_same_derived_proposal_seeds": True,
        "rng_observer_equivalence_check": "PASS: 100 cycles of uniform/choice/random equal ordinary Random",
        "simulation_count": 0, "full_Q2_started": False, "Q3_started": False,
        "interpretation": interpretation,
        "least_tested_reduction_with_complete_candidate_deg": 150-max(full) if full else None,
        "parameter_change_recommendation": "No production change authorized; combine these finite-budget results with exact-boundary evidence and submit to user review.",
        "selection_bias_limits": [
            "Lowering the threshold changes accept/reject branches and subsequent RNG consumption; equal original seeds do not imply equal later shapes. Every local draw and realized accepted angle is recorded.",
            "This dense fixed scene can favor smaller radii, particular phases and shorter arcs after geometric rejection; one skeleton does not estimate population-wide bias.",
            "Nominal planned arc minus 120 degrees is only an angular planning diagnostic. It is not M1 monitoring success; no trajectory, revisit detection or M2 rehearsal ran.",
            "Zero candidates in 200 proposals is a finite-budget result, not a proof of mathematical infeasibility."]}
    atomic(output, report)
    print(json.dumps({"output": str(output), "wall_s": report["wall_s"], "results": [{"arc_min_deg":r["tested_arc_min_deg"], **r["layers"]} for r in results]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
