"""Run the full offline test set and compare it with the locked G-5a baseline."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scripts import v07_fe_production_core as core
from scripts.audit_m3_r3_r0 import read
from scripts.m3_r3_g5a import load_amendment, regression_g5a
from scripts.revalidate_m3_r3_r1 import tests

DEFAULT_ROOT = PROJECT.parent.parent / "SwarmData" / "v07_first_edition_checks"
PLAN_PATH = PROJECT / "docs/v07/evidence/m3_r3/R0_validation_plan_amended.json"
NEW_TEST_MODULE = "test_v07_fe_production"
NEW_TEST_PREFIX = NEW_TEST_MODULE + "."


def _check_dir(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    base = root / f"regression_{core.utc_stamp()}"
    if not base.exists():
        return base
    suffix = 2
    while base.with_name(f"{base.name}_{suffix}").exists():
        suffix += 1
    return base.with_name(f"{base.name}_{suffix}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--timeout-s", type=float, default=3600.)
    parser.add_argument("--require-all-pass", action="store_true",
                        help="after merging the test-debt fix, require zero failures/errors")
    args = parser.parse_args(argv)
    run_dir = _check_dir(args.root)
    run_dir.mkdir()
    log_path = run_dir / "unittest.txt"
    plan = read(PLAN_PATH)
    modules = sorted(set(plan["R3"]["regression_modules"]) | {NEW_TEST_MODULE})
    deadline = time.monotonic() + args.timeout_s
    try:
        amendment = load_amendment()
        baseline = read(amendment["baseline_results_path"])
        candidate = tests(PROJECT, modules, log_path, deadline)
        roots = list(amendment["checkout_roots"]) + [str(PROJECT.parent)]
        regression = regression_g5a(candidate, baseline, amendment["known_signatures"], roots)
        new_tests = {test: outcome for test, outcome in candidate["outcomes"].items()
                     if test.startswith(NEW_TEST_PREFIX)}
        new_tests_ok = bool(new_tests) and all(outcome == "ok" for outcome in new_tests.values())
        all_zero = candidate.get("returncode") == 0 and all(
            outcome == "ok" for outcome in candidate["outcomes"].values())
        signature_changes = list(regression["unexpected_known_passes"])
        if args.require_all_pass:
            status = "PASS" if (all_zero and new_tests_ok
                                and regression["new_failure_count"] == 0) else "FAIL"
        else:
            status = "PASS" if (regression["status"] == "PASS" and new_tests_ok
                                and not signature_changes) else "FAIL"
        result = {
            "status": status,
            "stage": "full_regression",
            "require_all_pass": args.require_all_pass,
            "modules": len(modules),
            "module_source": str(PLAN_PATH) + "::R3.regression_modules",
            "module_names": modules,
            "executed": candidate.get("count"),
            "passed": sum(outcome == "ok" for outcome in candidate["outcomes"].values()),
            "returncode": candidate.get("returncode"),
            "all_tests_zero": all_zero,
            "new_tests": new_tests,
            "new_tests_ok": new_tests_ok,
            "signature_changes": signature_changes,
            "g5a": regression,
            "checkout_roots": roots,
            "log": str(log_path),
            "code_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip(),
        }
        core.atomic_json(run_dir / "regression.json", result)
        print(json.dumps({key: value for key, value in result.items()
                          if key not in ("g5a", "new_tests")}, ensure_ascii=False, indent=1), flush=True)
        return 0 if status == "PASS" else 1
    except Exception:
        result = {"status": "BLOCKED", "stage": "full_regression",
                  "traceback": traceback.format_exc(), "log": str(log_path)}
        core.atomic_json(run_dir / "regression.json", result)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
