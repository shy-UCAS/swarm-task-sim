"""Execute registered single-group area-search skeletons after planning smoke."""
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
from scripts.run_v07_s2_expansion import INFRA_ATTEMPT, descriptor_jobs, new_attempt, run_jobs
from task_v07.io import read_json, save_json


def main():
    descriptors = read_json(INFRA_ATTEMPT / "private_skeleton_descriptors.json")
    selected = [d["skeleton_id"] for d in descriptors if d["subset"] == "regular" and len(d["task_groups"]) == 1
                and d["task_groups"][0]["execution_method"] == "area_search"]
    out = new_attempt("attempt_s2x_area_pilot")
    print(f"OUTPUT {out}", flush=True)
    save_json(out / "registration.json", {"scope": "area-search phase; all registered single-group area-search skeletons",
                                         "workers": 6, "skeleton_ids": selected, "source": str(INFRA_ATTEMPT)})
    start = time.perf_counter()
    rows = run_jobs(descriptor_jobs(INFRA_ATTEMPT, selected, out), 6)
    save_json(out / "summary.json", {"episodes": rows, "wall_s": time.perf_counter() - start})
    for row in rows:
        print({key: row.get(key) for key in ("episode_id", "state", "reason", "task_result", "approach_span_deg",
                                            "minimum_separation_m", "coordination_matches")}, flush=True)


if __name__ == "__main__":
    main()
