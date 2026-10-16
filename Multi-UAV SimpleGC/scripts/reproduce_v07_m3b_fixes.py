"""Recompute the six registered F0 proposals after repairs; no simulation or source mutation."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import random
import subprocess
import sys
import time

import numpy as np
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.run_v07_m3_checks import EVIDENCE
from scripts.run_v07_m3_trial import atomic, frozen_check
from scripts.run_v07_m3b_trial import runtime_hashes
from scripts.run_v07_s2_expansion import descriptor_jobs
from task_v07.io import read_json, sha
from task_v07.expansion.contracts import P0ContractError
from task_v07.unified.spec import build_spec, proposal_seed
from task_v07.unified.free_space import free_space, work_region
from task_v07.unified.shapes import draw_shape
from task_v07.unified.route import route_group, GeometryRejected
from task_v07.unified.checks import plan_checks


def plain(value):
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, dict): return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [plain(v) for v in value]
    return value


def issue_key(issue):
    return issue.get("agent_id"), issue["code"]


def nested_reasons(value):
    found = set()
    if isinstance(value, dict):
        found.update(value[k] for k in ("reason", "code") if isinstance(value.get(k), str))
        for child in value.values(): found.update(nested_reasons(child))
    elif isinstance(value, list):
        for child in value: found.update(nested_reasons(child))
    return sorted(found)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    path = EVIDENCE / "m3b_q2_repro.json"
    old = read_json(path); before = old["before_fix"]
    if len(before) != 6 or old["diagnosis_verdict"].get("gate") != "continue_to_step_2":
        raise ValueError("Requires the six matching, already-reviewed F0 reproductions")
    reg = read_json(EVIDENCE / "m3b_inputs.json"); frozen_check(reg)
    if sha(Path(reg["descriptor_attempt"]) / "private_skeleton_descriptors.json") != old["descriptor_sha256"]:
        raise P0ContractError("Registered reproduction descriptor changed")
    start = time.perf_counter(); stamp = datetime.now(timezone.utc).isoformat()
    hashes = runtime_hashes()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()
    jobs = descriptor_jobs(Path(reg["descriptor_attempt"]), sorted({r["skeleton_id"] for r in before}), EVIDENCE)
    by_id = {j["descriptor"]["skeleton_id"]: j for j in jobs}
    results = []
    for original in before:
        sid, gid, index = (original[k] for k in ("skeleton_id", "group_id", "candidate_index"))
        job = by_id[sid]; descriptor = job["descriptor"]; scene = job["scene"]
        group = next(g for g in descriptor["task_groups"] if g["group_id"] == gid)
        spec = build_spec(descriptor, group); seed = proposal_seed(spec, index)
        if seed != original["proposal_seed"]: raise P0ContractError("Reproduction proposal seed changed")
        rng = random.Random(seed); free = free_space(scene, spec)
        record = {"skeleton_id": sid, "group_id": gid, "candidate_index": index,
                  "proposal_seed": seed, "role": group["role"], "execution_method": group["execution_method"],
                  "original_issue_categories": sorted({i["code"] for i in original["whole_route_checks"]["issues"]})}
        stage = "shape"
        try:
            shape = draw_shape(spec, work_region(scene, spec, free), rng, free)
            record["shape_draw"] = plain(shape["draw"])
            stage = "connection"
            bundle, template = route_group(scene, spec, shape, free, descriptor["family_conditions"]["initial_states"], rng)
            stage = "whole_route"
            checks = plan_checks(scene, spec, bundle, template, free, descriptor["family_conditions"]["initial_states"])
            before_issues = {issue_key(i) for i in original["whole_route_checks"]["issues"]}
            after_issues = {issue_key(i) for i in checks["issues"]}
            old_codes = set(record["original_issue_categories"])
            new_codes = sorted({i["code"] for i in checks["issues"]} - old_codes)
            record.update(whole_route_checks=plain(checks), waypoints_by_agent=plain(bundle.waypoints_by_agent),
                references=plain(template["references"]), geometry_provenance=plain(template["geometry_provenance"]),
                original_issues_resolved=not (before_issues & after_issues),
                unresolved_original_issue_instances=[{"agent_id": a, "code": c} for a, c in sorted(before_issues & after_issues)],
                new_whole_route_categories=new_codes, construction_rejection=None,
                status="PASS" if checks["status"] == "PASS" else "UNRESOLVED_OR_NEW_WHOLE_ROUTE_ISSUES")
        except GeometryRejected as exc:
            record.update(status="REJECTED_DURING_CONSTRUCTION", construction_rejection={"stage": stage,
                "reason": exc.reason, "evidence": plain(exc.evidence), "nested_reasons": nested_reasons(exc.evidence)},
                original_issues_resolved=None, original_invalid_route_exported=False,
                new_whole_route_categories=[], whole_route_checks=None)
        results.append(record)
        print(json.dumps({k: record[k] for k in ("skeleton_id", "group_id", "candidate_index", "status")}), flush=True)
    if hashes != runtime_hashes(): raise P0ContractError("Runtime changed during six-proposal regression")
    run = {"started_utc": stamp, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "entry_commit": head, "runtime_sha256": hashes, "wall_s": time.perf_counter() - start,
        "geometry_config_sha256": sha(PROJECT / "configs/generator/geometry_v07_r1.json"),
        "simulation_count": 0, "rows": results, "frozen_check": frozen_check(reg),
        "status": "PASS" if all(r["status"] in ("PASS", "REJECTED_DURING_CONSTRUCTION") for r in results) else "REGRESSION_FAILED",
        "comparison_method": "Same descriptor, public scene, group, proposal index and derived seed; original issue instances compared by (agent_id, code). New whole-route issue categories are reported per proposal. Finite construction rejection prevents export and preserves all nested reasons; it is not counted as successful planning."}
    old.setdefault("after_fix", []).append(run)
    atomic(path, old)
    print(json.dumps({k: run[k] for k in ("status", "wall_s", "entry_commit")}), flush=True)
    return 0 if run["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
