"""Freeze local M1 verification evidence in a new directory (never run SITL)."""

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import platform
import re
import sys
import time
import unittest

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "tests"))

from swarm_sim.fast_dynamics.mission_executor import run_mission
from swarm_sim.fast_dynamics.output_policy import (
    OutputPolicyError, assert_created_within, assert_new_attempt_path,
    new_attempt_path, resolve_output_root,
)
from swarm_sim.fast_dynamics.provenance import source_snapshot
from scripts.run_fast_dynamics import main as run_pipeline


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        help="new verification directory outside the repository; "
                             "default: <output-root>/<UTC timestamp>_verify_m01")
    parser.add_argument("--output-root", type=Path,
                        help="external root for verification evidence; default: FAST_DYNAMICS_OUTPUT_ROOT, "
                             "else the sibling SwarmData/fast_dynamics directory")
    args = parser.parse_args()
    try:
        root = resolve_output_root(args.output_root)
        requested = args.output if args.output is not None else new_attempt_path(root["root"], "verify_m01")
        args.output = assert_new_attempt_path(requested, root["root"], kind="verification attempt")
    except OutputPolicyError as exc:
        parser.error(str(exc))
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        assert_created_within(args.output, root["root"])
    except OutputPolicyError:
        args.output.rmdir()  # nothing has been written yet
        raise
    before = source_snapshot()
    workflow = (PROJECT.parent / ".github/workflows/unit-tests.yml").read_text(encoding="utf-8")
    old_modules = list(dict.fromkeys(re.findall(r"'(test_[a-zA-Z0-9_]+)'", workflow)))
    new_modules = ["test_fast_dynamics_core", "test_fast_dynamics_execution", "test_fast_dynamics_artifacts"]
    old_modules = [name for name in old_modules if name not in new_modules]
    tests = {}
    for name, modules in (("legacy", old_modules), ("fast_dynamics", new_modules)):
        started = time.perf_counter()
        with (args.output / (name + "_tests.log")).open("w", encoding="utf-8") as log:
            suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        tests[name] = dict(modules=modules, tests=result.testsRun, failures=len(result.failures),
            errors=len(result.errors), skipped=len(result.skipped), successful=result.wasSuccessful(),
            elapsed_s=time.perf_counter() - started)
        save(args.output / "tests.json", tests)
        if not result.wasSuccessful():
            raise RuntimeError(f"{name} tests failed; see retained test log")

    fixture = PROJECT / "tests/fixtures/fast_dynamics/rapid_passage_0000_v00.json"
    task = json.loads(fixture.read_text(encoding="utf-8"))
    coarse = run_mission(task)
    fine = run_mission(task, {"engine": {"step_us": 10000}})
    count = min(len(coarse.time_us), len(fine.time_us))
    convergence = dict(coarse_step_us=20000, fine_step_us=10000, common_frames=count,
                       end_us=[coarse.end_us, fine.end_us])
    for key in ("positions", "velocities"):
        difference = np.linalg.norm(getattr(coarse, key)[:count] - getattr(fine, key)[:count], axis=2)
        convergence[key] = dict(p99=float(np.quantile(difference, .99)), maximum=float(difference.max()))
    event_map = lambda r: {(e["event"], e.get("phase"), e.get("agent_id")): e["t_us"] for e in r.events}
    left, right = event_map(coarse), event_map(fine)
    convergence["event_max_difference_s"] = max(abs(t - right[k]) / 1e6 for k, t in left.items())
    save(args.output / "mission_convergence.json", convergence)

    outcomes, wall_times = [], []
    for index in range(5):
        destination = args.output / f"success_{index + 1:02d}"
        started = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            run_pipeline([str(fixture), "--output", str(destination),
                          "--output-root", str(root["root"])])
        elapsed = time.perf_counter() - started
        wall_times.append(elapsed)
        report = json.loads((destination / "report.json").read_text(encoding="utf-8"))
        outcomes.append(dict(case=destination.name, execution_status=report["execution_status"],
            mission_success=report["analysis"]["mission_success"],
            quality_eligible=report["analysis"]["episode_quality_eligible"],
            descriptions=report["language"]["descriptions"], frames=report["frames"],
            duration_s=report["end_us"] / 1e6, outer_wall_s=elapsed))
    for name, overrides in (("semantic_failure", {"vehicle_profile": {"max_speed_xy_m_s": .3}}),
                            ("unknown_timeout", {"execution": {"max_duration_s": .03}})):
        config_path = args.output / (name + "_config.json")
        save(config_path, overrides)
        destination = args.output / name
        with contextlib.redirect_stdout(io.StringIO()):
            run_pipeline([str(fixture), "--output", str(destination), "--config", str(config_path),
                          "--output-root", str(root["root"])])
        report = json.loads((destination / "report.json").read_text(encoding="utf-8"))
        outcomes.append(dict(case=name, execution_status=report["execution_status"],
            mission_success=report["analysis"]["mission_success"],
            quality_eligible=report["analysis"]["episode_quality_eligible"],
            descriptions=report["language"]["descriptions"], frames=report["frames"],
            duration_s=report["end_us"] / 1e6))
    if source_snapshot() != before:
        raise RuntimeError("verification source changed during run; do not qualify this attempt")
    benchmark = dict(repeats=5, workers=1, exclusive_host=False, outer_wall_s=wall_times,
        first_run_s=wall_times[0], warm_median_s=float(np.median(wall_times[1:])),
        warm_p95_s=float(np.quantile(wall_times[1:], .95)),
        warm_qualified_episodes_per_hour=3600 / float(np.median(wall_times[1:])),
        scope="one fixed two-agent M1 development task, ideal observations; all pipeline stages and final writes included",
        excluded="Python process startup/import; broad task composition, calibration, production and independent qualification",
        comparison_to_T4="not a same-quality production comparison; cannot claim the planned 10x full production target")
    report = dict(tests=tests, convergence=convergence, outcomes=outcomes, benchmark=benchmark,
        python=platform.python_version(), numpy=np.__version__, platform=platform.platform(),
        input_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(), source_sha256=before,
        output=dict(path=str(args.output), root=str(root["root"]), root_source=root["source"]),
        purpose="local_development_uncalibrated_M1", training_eligible=False)
    save(args.output / "verification.json", report)
    save(args.output / "completion.json", dict(status="complete", verification_sha256=hashlib.sha256(
        (args.output / "verification.json").read_bytes()).hexdigest()))
    print(json.dumps(dict(tests=tests, outcomes=outcomes, benchmark=benchmark), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
