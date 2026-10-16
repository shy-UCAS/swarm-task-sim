"""Rerun S15 and original short suites; save evidence only under evidence/s15."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROJECT), str(PROJECT / "tests")]
from scene_v07.contract import canonical_json
from scripts.run_v07_m3b_fix_checks import execute
from scripts.run_v07_m3_trial import frozen_check


def main():
    started = time.perf_counter()
    evidence = PROJECT / "docs/v07/evidence"
    registration = json.loads((evidence / "m3/m3b_inputs.json").read_text(encoding="utf-8"))
    frozen_before = frozen_check(registration)
    rows = [execute("scene_revisions", ["test_v07_scene", "test_v07_scene_batch", "test_v07_scene_s11", "test_v07_scene_s15"])]
    if rows[0]["status"] != "PASS":
        raise RuntimeError("S15 stop: scene/legacy regression failed; no candidates generated")
    for name, count in (("m3a_checks.json", 38), ("m3b_checks.json", 47)):
        original = json.loads((evidence / "m3" / name).read_text(encoding="utf-8"))
        rows.append(execute(name.removesuffix(".json"), original["test_entries"], count))
    rows.append(execute("F0_F4", ["test_v07_m3_fix_entry", "test_v07_m3_fix_connections", "test_v07_m3_fix_patrol_entry"], 10))
    rows.append(execute("F2b", ["test_v07_m3_f2b"], 3))
    passed = all(row["status"] == "PASS" for row in rows)
    record = {"status": "PASS" if passed else "FAIL", "finished_utc": datetime.now(timezone.utc).isoformat(),
              "entry_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip(),
              "suites": rows, "wall_s": time.perf_counter()-started,
              "tests_run_including_original_suite_overlap": sum(row["tests_run"] for row in rows),
              "distinct_test_ids": len({test for row in rows for test in row["test_ids"]}),
              "frozen_check_before": frozen_before, "frozen_check_after": frozen_check(registration),
              "scope": "Original short tests unchanged, including M2 A5-A7 in-memory frozen-runtime regression; no S2/Q2/Q3 or fastsim production batch",
              "test_source_sha256": {str(p.relative_to(PROJECT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in sorted({PROJECT / "tests" / (entry.split('.')[0]+'.py')
                                                      for row in rows for entry in row['test_entries']})}}
    output = evidence / "s15/regression_checks.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json(record))
    print(json.dumps({k: record[k] for k in ("status", "wall_s", "tests_run_including_original_suite_overlap", "distinct_test_ids")}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
