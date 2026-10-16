"""Q-B: replay the fixed saved solo rounds without any simulation."""
from collections import Counter
import csv
import json
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from task_v07.io import read_json, sha
from task_v07.unified.rehearsal import evaluate_solos, load_saved_rehearsal
from task_v07.unified.timing import select_timing
from task_v07.unified.outcome import FAILURE_CATEGORIES
from scripts.run_v07_s2_expansion import descriptor_jobs

SOURCE = PROJECT.parent.parent / "SwarmData/v07_dataset/attempt_s2_search_quick_b_20261015T090658Z_5ac915b5"
MISSING = frozenset(("family_s12_4d13d93f9171c446_ext_006_regular/geometry_02",
                     "family_s12_4d13d93f9171c446_ext_007_regular/geometry_01",
                     "family_s12_5024cb2ccea653ae_ext_002_regular/geometry_00"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def write_rows(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def main():
    started = time.perf_counter()
    registration = read_json(SOURCE / "registration.json")
    selected = [r["skeleton_id"] for r in registration["selected"]]
    if len(selected) != 10 or len(set(selected)) != 10: raise ValueError("Fixed quick B selection must contain ten unique skeletons")
    evidence = PROJECT / "docs/v07/evidence/m2"; evidence.mkdir(parents=True, exist_ok=True)
    jobs = {j["descriptor"]["skeleton_id"]: j for j in descriptor_jobs(Path(registration["source_attempt"]), selected, evidence)}
    rows, details, missing = [], [], set()
    for sid in selected:
        for directory in sorted(p for p in (SOURCE / sid).glob("geometry_[0-9][0-9]") if p.is_dir()):
            relative = directory.relative_to(SOURCE).as_posix()
            sk = read_json(directory / "skeleton.json")
            old = read_json(directory / "planning_rejection.json")["category"] if (directory / "planning_rejection.json").exists() else "passed"
            row = {"skeleton_id": sid, "intent": jobs[sid]["descriptor"]["base_intent"], "approach_mode": sk["approach_mode"],
                   "round": int(directory.name.split("_")[-1]) + 1, "status": None, "rehearsal_status": None,
                   "failed_members_and_conditions": "[]",
                   "synchronous_accepted_draw": None, "sequential_accepted_draw": None,
                   "synchronous_minimum_m": None, "sequential_minimum_m": None, "category": None, "old_category": old}
            absent = [a for a in sk["members"] if not (directory / f"single_agent_{a}.npz").exists()]
            if absent:
                if relative not in MISSING: raise ValueError("Unexpected missing solo input: " + relative)
                missing.add(relative); row.update(status="input_missing", old_category="interrupted")
                details.append({"directory": relative, "missing_agents": absent, "status": "input_missing"})
            else:
                files = [directory / "skeleton.json", directory / "timing_calibration.json", *sorted(directory.glob("single_agent_*.npz"))]
                hashes = {p.name: sha(p) for p in files}
                solos = load_saved_rehearsal(directory, sk)
                rehearsal = evaluate_solos(jobs[sid]["scene"], sk, solos)
                row.update(status=rehearsal["status"], rehearsal_status=rehearsal["status"], category=rehearsal["category"],
                           failed_members_and_conditions=json.dumps(rehearsal["failures"], ensure_ascii=False, separators=(",", ":")))
                timing = None
                if rehearsal["status"] == "passed":
                    timing = select_timing(sk, rehearsal["core_times_s"], solos)
                    row.update(status=timing["status"], category=timing["category"])
                    for mode, version in timing["versions"].items():
                        row[mode + "_accepted_draw"] = version["accepted_draw"]
                        row[mode + "_minimum_m"] = version["attempts"][-1]["minimum_m"]
                if any(sha(p) != hashes[p.name] for p in files): raise ValueError("Source round changed during read-only replay")
                details.append({"directory": relative, "source_sha256": hashes, "rehearsal": rehearsal, "timing": timing})
            if row["status"] not in ("passed", "rejected", "input_missing"):
                raise ValueError("Invalid replay status")
            if row["status"] == "rejected" and row["category"] not in FAILURE_CATEGORIES:
                raise ValueError("Invalid failure category")
            if row["status"] != "rejected" and row["category"] is not None:
                raise ValueError("Passed/missing rounds must have a null category")
            rows.append(row)
            write_rows(evidence / "qb_offline_replay.csv", rows)
            print(json.dumps({**{k: row[k] for k in ("skeleton_id", "round", "status", "category")},
                              "wall_s": round(time.perf_counter() - started, 2)}), flush=True)
    if len(rows) != 23 or missing != MISSING or sum(r["status"] != "input_missing" for r in rows) != 20:
        raise ValueError("Replay inventory differs from the approved 20 complete plus three missing rounds")
    summary = {"status": "PASS", "source_attempt": str(SOURCE), "wall_s": time.perf_counter() - started,
               "complete_rounds": 20, "missing_rounds": sorted(missing), "counts": dict(Counter(r["status"] for r in rows)),
               "categories": dict(Counter(r["category"] for r in rows if r["category"])),
               "simulation_count": 0, "old_stop_conditions": True,
               "by_intent": {intent: dict(Counter(r["status"] for r in rows if r["intent"] == intent)) for intent in sorted({r["intent"] for r in rows})},
               "multi_direction_feint_first_four": [r for r in rows if "ext_008_regular" in r["skeleton_id"] and r["round"] <= 4]}
    write_json(evidence / "qb_summary.json", summary); write_json(evidence / "qb_details.json", details)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
