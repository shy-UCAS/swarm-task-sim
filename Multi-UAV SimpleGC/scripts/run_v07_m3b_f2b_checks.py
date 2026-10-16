"""Run the explicitly authorized F2b regressions; preserve all prior evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.run_v07_m3_checks import EVIDENCE
from scripts.run_v07_m3_trial import atomic, frozen_check
from scripts.run_v07_m3b_fix_checks import execute
from task_v07.expansion.contracts import P0ContractError
from task_v07.io import read_json, sha

BASELINE = "7e67fa232c1a3c2a2540dd612d85797bb56276c9"
OUTPUT = EVIDENCE / "m3b_f2b_recheck.json"
HISTORICAL = ("m3a_checks.json", "m3b_checks.json", "m3b_fix_checks.json", "m3b_fix_q2.json",
              "m3b_q2_repro.json", "m3b_q2_graze_audit.json", "m3b_q2_diagnostics.json")


def production_hashes():
    paths = list((PROJECT/"task_v07").rglob("*.py"))+list((PROJECT/"configs").rglob("*.json"))
    return {p.relative_to(PROJECT).as_posix(): sha(p) for p in paths}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    sys.path.insert(0, str(PROJECT/"tests"))
    registration = read_json(EVIDENCE/"m3b_inputs.json")
    if len(registration["frozen_sha256"]) != 39:
        raise P0ContractError("Expected the original 39-file frozen manifest")
    frozen_before = frozen_check(registration)
    source_hashes = {name: sha(EVIDENCE/name) for name in HISTORICAL}
    runtime = production_hashes()
    started = time.perf_counter(); stamp = datetime.now(timezone.utc).isoformat()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()
    rows = []
    rows.append(execute("F2b_deterministic", ["test_v07_m3_f2b"], 3))
    for name, count in (("m3a_checks.json", 38), ("m3b_checks.json", 47)):
        original = read_json(EVIDENCE/name)
        if original["tests_run"] != count:
            raise ValueError(f"Historical test denominator changed: {name}")
        rows.append(execute(name.removesuffix(".json"), original["test_entries"], count))
    rows.append(execute("F0_F4_regressions", ["test_v07_m3_fix_entry", "test_v07_m3_fix_connections",
                                              "test_v07_m3_fix_patrol_entry"], 10))
    frozen_after = frozen_check(registration)
    if production_hashes() != runtime:
        raise P0ContractError("Production sources changed during F2b tests")
    if any(sha(EVIDENCE/name) != value for name, value in source_hashes.items()):
        raise P0ContractError("Historical evidence changed during F2b tests")
    from test_v07_m3_f2b import F2B_TEST_EVIDENCE
    test_paths = {entry for row in rows for entry in row["test_entries"]}
    test_source_hashes = {f"tests/{name.split('.')[0]}.py": sha(PROJECT/"tests"/(name.split('.')[0]+".py"))
                          for name in test_paths}
    tests = {"status": "PASS" if all(row["status"] == "PASS" for row in rows) else "FAIL",
        "started_utc": stamp, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "entry_commit": head, "production_sha256": runtime, "test_source_sha256": test_source_hashes,
        "runner_sha256": sha(Path(__file__)), "suites": rows, "wall_s": time.perf_counter()-started,
        "tests_run_including_intentional_original_suite_overlap": sum(row["tests_run"] for row in rows),
        "distinct_test_ids_executed": len({identifier for row in rows for identifier in row["test_ids"]}),
        "source_evidence_sha256": source_hashes, "frozen_check_before": frozen_before,
        "frozen_check": frozen_after, "deterministic_geometry_evidence": F2B_TEST_EVIDENCE,
        "fixture_development_errors": [{"scope": "new A1 fixture, not historical regression",
            "attempts": ["seed 1 with original northwest starts", "seed 4 with original northwest starts"],
            "result": "Original plan_checks correctly rejected the generated route: a1 approach segment 4 had obstacle clearance 15 m, below unchanged 35 m.",
            "correction": "The test's synthetic initial positions were moved south so the exterior connector reaches the reserved line without the extra extension. Production geometry and thresholds were not altered.",
            "note": "An initial progress message called this segment retreat; actual waypoint inspection identified it as ingress, and this record corrects that label."}],
        "method": "Original M3a 38 and M3b 47 entry lists run independently, including their overlap; all 10 F0-F4 tests and 3 new F2b tests run. The existing ingress-start assertion is updated only from -150 to -100 to match the explicitly approved new formula. No skips or deleted tests."}
    record = read_json(OUTPUT) if OUTPUT.exists() else {}
    record.update(original_commit=BASELINE, new_commit=record.get("new_commit"),
        precheck_formula_before="gate - (alignment_length_m + half + 50) * direction",
        precheck_formula_after="gate - (alignment_length_m + half) * direction", tests=tests)
    record.setdefault("fixed_proposals", {"status": "NOT_RUN", "reason": "Performed separately after deterministic regressions"})
    atomic(OUTPUT, record)
    print(json.dumps({"status": tests["status"], "tests_run": tests["tests_run_including_intentional_original_suite_overlap"],
        "distinct_test_ids": tests["distinct_test_ids_executed"], "suites": [{k: row[k] for k in ("suite", "status", "tests_run")} for row in rows],
        "wall_s": tests["wall_s"]}, ensure_ascii=False), flush=True)
    return 0 if tests["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
