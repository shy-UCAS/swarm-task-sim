"""Run the registered 12 M2 development tasks and four physical-state negatives.

All episodes and logs go to a new external directory. This is local development
verification, not calibration, a blind evaluation, or a production benchmark.
"""
from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path
import statistics
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scripts.run_fast_dynamics import main as run_pipeline
from swarm_sim.fast_dynamics.output_policy import (
    OutputPolicyError, assert_created_within, assert_new_attempt_path,
    new_attempt_path, resolve_output_root,
)


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8")


def registered_cases():
    matrix = json.loads((PROJECT / "verification/fast_dynamics_m2/coverage_matrix.json").read_text(encoding="utf-8-sig"))
    cases = []
    for item in matrix["registered_inputs"]:
        intent, pattern, count = item["cell_id"].split("__")
        case = dict(case_id=item["cell_id"] + "__positive", input=item["path"],
                    intent=intent, flight_pattern=pattern, agents=int(count[1:]),
                    expected_success=True, config={}, test_harness=None)
        cases.append(case)
        # Exactly one negative per pattern, paired with its registered two-agent task.
        if case["agents"] == 2:
            negative = dict(case, case_id=item["cell_id"] + "__negative", expected_success=False)
            if intent == "reconnaissance":
                negative["test_harness"] = {"kind": "recon_altitude_excursion"}
            elif intent == "patrol":
                negative["test_harness"] = {"kind": "patrol_slowdown"}
            else:
                negative["config"] = {"vehicle_profile": {"max_speed_xy_m_s": .3}}
            cases.append(negative)
    if len(cases) != 16 or sum(case["expected_success"] for case in cases) != 12:
        raise ValueError("M2 acceptance is restricted to 12 registered positives and four negatives")
    return cases


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case", action="append", help="run only this registered case ID (development diagnosis)")
    parser.add_argument("--no-semantic-reuse", action="store_true", help="measure the unoptimized data-pipeline baseline")
    args = parser.parse_args(argv)
    cases = registered_cases()
    if args.case:
        unknown = set(args.case) - {case["case_id"] for case in cases}
        if unknown:
            parser.error("unregistered case IDs: " + ", ".join(sorted(unknown)))
        cases = [case for case in cases if case["case_id"] in args.case]
    try:
        root = resolve_output_root(args.output_root)
        output = assert_new_attempt_path(args.output or new_attempt_path(root["root"], "verify_m2"),
                                         root["root"], kind="M2 verification")
    except OutputPolicyError as exc:
        parser.error(str(exc))
    output.mkdir(parents=True, exist_ok=False)
    assert_created_within(output, root["root"])
    report = dict(scope="registered development tasks only; no holdout or SITL execution",
                  complete_acceptance=len(cases) == 16, semantic_reuse=not args.no_semantic_reuse,
                  status="RUNNING", rows=[])
    save(output / "cases.json", cases)
    for case in cases:
        name = case["case_id"]
        attempt = output / name
        argv = [str(PROJECT / case["input"]), "--output-root", str(root["root"]),
                "--output", str(attempt), "--run-id", name]
        if args.no_semantic_reuse:
            argv.append("--no-semantic-reuse")
        if case["config"]:
            path = output / (name + "_config.json")
            save(path, case["config"])
            argv.extend(["--config", str(path)])
        if case["test_harness"]:
            path = output / (name + "_harness.json")
            save(path, case["test_harness"])
            argv.extend(["--test-harness", str(path)])
        print("RUN " + name, flush=True)
        started = time.perf_counter()
        try:
            with (output / (name + ".log")).open("x", encoding="utf-8") as log:
                with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                    run_pipeline(argv)
            elapsed = time.perf_counter() - started
            result = json.loads((attempt / "report.json").read_text(encoding="utf-8"))
            analysis = result["analysis"]
            episode = attempt / "dataset" / "episodes" / name
            labels = json.loads((episode / "labels.json").read_text(encoding="utf-8"))
            compiled = json.loads((episode / "compiled_scene.json").read_text(encoding="utf-8"))
            # Independent of adapter helpers: actual compiled phase records are the oracle.
            planned = list(dict.fromkeys(phase["semantic_phase"] for phase in compiled["phases"]))
            if labels["planned_phases"] != planned:
                raise ValueError("P0: exported planned_phases disagrees with actual compiled phases")
            row = dict(case_id=name, flight_pattern=case["flight_pattern"], agents=case["agents"],
                       expected_success=case["expected_success"],
                       mission_success=analysis["mission_success"],
                       quality_eligible=analysis["episode_quality_eligible"],
                       execution_status=result["execution_status"], frames=result["frames"],
                       simulated_s=result["end_us"] / 1e6, full_pipeline_wall_s=elapsed,
                       simulation_wall_s=result["simulation_wall_s"],
                       descriptions=result["language"]["descriptions"], attempt=str(attempt))
            row["planned_phases"] = labels["planned_phases"]
            row["passed"] = (row["execution_status"] == "complete" and row["quality_eligible"] is True
                             and row["mission_success"] is case["expected_success"]
                             and row["descriptions"] > 0 and not result["audit"].get("issues"))
            report["rows"].append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        except Exception as exc:
            # Retain the partial batch; a pipeline failure needs diagnosis before more data is made.
            report.update(status="PIPELINE_ERROR", failed_case=name,
                          error_type=type(exc).__name__, error=str(exc))
            save(output / "verification.json", report)
            raise
        save(output / "verification.json", report)
    report["passed"] = sum(row["passed"] for row in report["rows"])
    report["status"] = "PASS" if report["passed"] == len(cases) else "FIX_REQUIRED"
    report["timing"] = []
    for pattern in sorted({row["flight_pattern"] for row in report["rows"]}):
        rows = [row for row in report["rows"] if row["flight_pattern"] == pattern and row["expected_success"]]
        if rows:
            values = [row["full_pipeline_wall_s"] for row in rows]
            report["timing"].append(dict(flight_pattern=pattern, tasks=len(rows),
                                         minimum_s=min(values), median_s=statistics.median(values), maximum_s=max(values)))
    report["timing_scope"] = "serial in-process task/config read, simulation, analysis, export, audit, descriptions, loading, final writes; process startup excluded"
    save(output / "verification.json", report)
    print(json.dumps({"status": report["status"], "passed": report["passed"], "cases": len(cases),
                      "output": str(output)}, ensure_ascii=False), flush=True)
    return int(report["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
