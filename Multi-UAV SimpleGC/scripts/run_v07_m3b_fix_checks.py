"""Rerun the original M3a/M3b short checks and repair tests without replacing historical evidence."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys
import time
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.run_v07_m3_checks import EVIDENCE
from scripts.run_v07_m3_trial import atomic, frozen_check
from scripts.run_v07_m3b_trial import runtime_hashes
from task_v07.expansion.contracts import P0ContractError
from task_v07.io import read_json, sha


def test_ids(suite):
    result = []
    for child in suite:
        result.extend(test_ids(child) if isinstance(child, unittest.TestSuite) else [child.id()])
    return result


def execute(label, entries, expected_count=None):
    suite = unittest.defaultTestLoader.loadTestsFromNames(entries)
    ids = test_ids(suite)
    started = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.wasSuccessful() and not result.skipped
    if expected_count is not None:
        passed &= result.testsRun == expected_count
    return {"suite": label, "status": "PASS" if passed else "FAIL", "test_entries": entries,
            "test_ids": ids, "tests_run": result.testsRun, "expected_test_count": expected_count,
            "failures": [(str(t), msg) for t, msg in result.failures],
            "errors": [(str(t), msg) for t, msg in result.errors], "skipped": result.skipped,
            "wall_s": time.perf_counter() - started}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    sys.path.insert(0, str(PROJECT / "tests"))
    reg = read_json(EVIDENCE / "m3b_inputs.json")
    if len(reg["frozen_sha256"]) != 39:
        raise P0ContractError("Expected the unchanged 39-file frozen manifest")
    frozen = frozen_check(reg)
    runtime = runtime_hashes()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()
    sources = {name: {"sha256": sha(EVIDENCE / name), "record": read_json(EVIDENCE / name)}
               for name in ("m3a_checks.json", "m3b_checks.json")}
    started = time.perf_counter(); stamp = datetime.now(timezone.utc).isoformat()
    rows = []
    for name, count in (("m3a_checks.json", 38), ("m3b_checks.json", 47)):
        source = sources[name]
        if source["record"]["tests_run"] != count:
            raise ValueError(f"Unexpected historical test denominator: {name}")
        rows.append(execute(name.removesuffix(".json"), source["record"]["test_entries"], count))
    rows.append(execute("repair_deterministic_checks", ["test_v07_m3_fix_entry", "test_v07_m3_fix_connections", "test_v07_m3_fix_patrol_entry"]))
    frozen_after = frozen_check(reg)
    if runtime_hashes() != runtime: raise P0ContractError("Runtime changed during repair regression tests")
    if any(sha(EVIDENCE / name) != value["sha256"] for name, value in sources.items()):
        raise P0ContractError("Historical checks evidence changed during repair tests")
    record = {"status": "PASS" if all(r["status"] == "PASS" for r in rows) else "FAIL",
              "started_utc": stamp, "finished_utc": datetime.now(timezone.utc).isoformat(),
              "entry_commit": head, "runtime_sha256": runtime,
              "geometry_config_sha256": sha(PROJECT / "configs/generator/geometry_v07_r1.json"),
              "wall_s": time.perf_counter() - started, "suites": rows,
              "tests_run_including_intentional_original_suite_overlap": sum(r["tests_run"] for r in rows),
              "source_evidence": {name: value["sha256"] for name, value in sources.items()},
              "frozen_check_before": frozen, "frozen_check": frozen_after,
              "method": "The original 38-test M3a and 47-test M3b entry lists run separately, unchanged, including their overlapping tests. Three repair test modules run additionally. Skips and count mismatches fail this runner; historical check files are preserved."}
    atomic(EVIDENCE / "m3b_fix_checks.json", record)
    print(json.dumps({"status": record["status"], "suites": [{k: r[k] for k in ("suite", "status", "tests_run")} for r in rows],
                      "wall_s": record["wall_s"]}, ensure_ascii=False), flush=True)
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
