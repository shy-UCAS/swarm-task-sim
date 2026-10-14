"""Planning smoke of registered area-search groups before any new execution."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import sys
import json
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))

from scripts.run_v07_s2_expansion import descriptor_jobs, INFRA_ATTEMPT, new_attempt
from task_v07.io import read_json, save_json
from task_v07.expansion.area_search import AreaSearchPlanner
from task_v07.expansion.pipeline import plan_group
from task_v07.expansion.role_planners import PlanningInfeasible
from task_v07.expansion.geometry_checks import planning_layer_interval_check
from task_v07.execution import departure_delays


def worker(job):
    desc, scene = job["descriptor"], job["scene"]
    output = Path(job["out"]) / desc["skeleton_id"]
    output.mkdir(exist_ok=True)
    rows = []
    for group in desc["task_groups"]:
        if group["execution_method"] != "area_search":
            continue
        started = time.perf_counter()
        root = output / group["group_id"]
        root.mkdir()
        try:
            sk, bundle, pre = plan_group(scene, desc, group, AreaSearchPlanner())
            nominal = {a: sk["initial_settle_s"] + r["planned_core_distance_m"] / sk["cruise_speed_m_s"]
                       for a, r in sk["references"].items()}
            interval = planning_layer_interval_check(bundle, departure_delays(sk, nominal), sk["cruise_speed_m_s"])
            save_json(root / "skeleton.json", sk)
            save_json(root / "planning_checks.json", pre)
            row = {"skeleton_id": desc["skeleton_id"], "group_id": group["group_id"], "status": pre["status"],
                   "approach_mode": sk["approach_mode"], "planned_approach_span_deg": sk["planned_approach_span_deg"],
                   "area_m2": sk["survey"]["area_m2"], "angle_span_deg": sk["survey"]["angle_span_deg"],
                   "scan_lengths_m": {a: r["assigned_scan_length_m"] for a, r in sk["references"].items()},
                   "interval": interval, "precheck_failures": pre["failures"],
                   "timing_basis": "nominal lengths only; actual-delay gate is still required before paired execution"}
        except PlanningInfeasible as exc:
            row = {"skeleton_id": desc["skeleton_id"], "group_id": group["group_id"], "status": "REJECT",
                   "category": exc.category, "reason": exc.detail}
        row["wall_s"] = time.perf_counter() - started
        save_json(root / "planning_smoke.json", row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    ids = [d["skeleton_id"] for d in read_json(INFRA_ATTEMPT / "private_skeleton_descriptors.json")
           if d["subset"] == "regular" and any(g["execution_method"] == "area_search" for g in d["task_groups"])]
    out = new_attempt("attempt_s2x_area_planning")
    print(f"OUTPUT {out}", flush=True)
    jobs = descriptor_jobs(INFRA_ATTEMPT, ids, out)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = [row for block in pool.map(worker, jobs) for row in block]
    save_json(out / "summary.json", {"scope": "planning only; group probes, not formal episodes", "rows": rows})


if __name__ == "__main__":
    main()
