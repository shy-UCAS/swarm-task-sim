"""Default-parameter M3 replay of eligible r2 tuning references only.

No parameter search, internal-holdout evaluation, M2-02B access or SITL launch.
Writes run-level state/label evidence and paired metrics, not a production dataset.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import contextlib
import json
from pathlib import Path
import sys
import time
import traceback

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from swarm_sim.fast_dynamics.calibration import (
    aggregate_pairs, fast_summary, final_tuning_attempts, paired_metrics, read_json, reference_summary, sha256, tuning_tasks,
)
from swarm_sim.fast_dynamics.contracts import M2Config
from swarm_sim.fast_dynamics.output_policy import assert_created_within, assert_new_attempt_path, resolve_output_root


def save(path, value):
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def execute_one(job):
    from swarm_sim.fast_dynamics.mission_executor import run_mission
    from swarm_sim.fast_dynamics.artifacts import write_episode
    from swarm_sim.fast_dynamics.adapter import reuse_semantics
    split, row, r1_row, output = job
    name = row["task"]["mission_id"]
    output = Path(output) / name
    output.mkdir(exist_ok=False)
    started = time.perf_counter()
    with (output / "commands.log").open("x", encoding="utf-8") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        try:
            r2 = Path(split["source_roots"]["r2"])
            reference, scene, task_path = reference_summary(row, split, r2)
            save(output / "sitl_r2.json", reference)
            if reference["status"] != "COMPLETE":
                outcome = dict(mission_id=name, family_id=row["task"]["family_id"], status="REFERENCE_NOT_COMPARABLE",
                               reason=reference["status"])
            else:
                task = read_json(task_path)
                config = M2Config()
                save(output / "default_config.json", config.to_dict())
                (output / "input_task.json").write_bytes(task_path.read_bytes())
                with reuse_semantics():
                    result = run_mission(task, config)
                    if result.scene != scene:
                        raise ValueError("P0: fast and SITL did not execute the same compiled planning")
                    write_episode(scene, result, output / "run", run_id=name,
                                  input_hashes={str(task_path): sha256(task_path)}, config=config.to_dict(), seed=task["seed"])
                fast = fast_summary(output / "run", name)
                save(output / "fast.json", fast)
                paired = paired_metrics(reference, fast)
                paired.update(intent=row["task"]["intent"], flight_pattern=row["task"]["flight_pattern"])
                save(output / "paired.json", paired)
                natural = None
                if r1_row is not None:
                    r1 = r2.parent / "v06_production900_seed2026100812"
                    repeat, repeated_scene, _ = reference_summary(r1_row, split, r1)
                    save(output / "sitl_r1.json", repeat)
                    if repeat["status"] == "COMPLETE":
                        if repeated_scene != scene:
                            raise ValueError("P0: repeated SITL planning differs")
                        natural = paired_metrics(reference, repeat)
                        natural.update(intent=row["task"]["intent"], flight_pattern=row["task"]["flight_pattern"])
                        save(output / "natural_variation.json", natural)
                outcome = dict(mission_id=name, family_id=row["task"]["family_id"], status="COMPLETE",
                               paired=paired, natural_variation=natural,
                               config=config.to_dict(), simulation_status=result.status)
            outcome["elapsed_wall_s"] = time.perf_counter() - started
            save(output / "outcome.json", outcome)
            return outcome
        except BaseException as exc:
            failure = dict(mission_id=name, family_id=row["task"]["family_id"], status="P0_STOP",
                           error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
            save(output / "failure.json", failure)
            return failure


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--split-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--mission", action="append", help="optional tuning-only diagnostic subset")
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 4:
        parser.error("workers must be 1..4")
    if sha256(args.split) != args.split_sha256:
        parser.error("frozen split hash mismatch")
    split = read_json(args.split)
    allowed = tuning_tasks(split)
    if args.mission and set(args.mission) - {r["mission_id"] for r in allowed}:
        parser.error("mission is not in the tuning allow-list; leave holdouts sealed")
    root = resolve_output_root(args.output_root)["root"]
    output = assert_new_attempt_path(args.output, root, kind="M3 baseline")
    r2 = Path(split["source_roots"]["r2"])
    if sha256(r2 / "plan.json") != split["plan_sha256"]["r2"]:
        parser.error("reference plan changed")
    selected = final_tuning_attempts(split, r2)
    repeated = final_tuning_attempts(split, r2.parent / "v06_production900_seed2026100812")
    r1 = {(r["task"]["family_id"], r["task"]["mission_id"]): r for r in repeated if r["status"] == "ELIGIBLE"}
    eligible = [r for r in selected if r["status"] == "ELIGIBLE" and
                (not args.mission or r["task"]["mission_id"] in args.mission)]
    output.mkdir(parents=True, exist_ok=False)
    assert_created_within(output, root)
    save(output / "reference_selection.json", selected)
    save(output / "repeat_selection.json", repeated)
    save(output / "default_config.json", M2Config().to_dict())
    report = dict(status="RUNNING", split_id=split["split_id"], split_sha256=args.split_sha256,
                  tuning_tasks=len(allowed), eligible_references=len(eligible), workers=args.workers,
                  is_diagnostic_subset=bool(args.mission), rows=[], parameters_fitted=False,
                  internal_holdout_executed=False, m2_02b_accessed=False, sitl_launched=False)
    save(output / "baseline.json", report)
    jobs = [(split, r, r1.get((r["task"]["family_id"], r["task"]["mission_id"])), str(output)) for r in eligible]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(execute_one, job) for job in jobs]
        for future in as_completed(futures):
            if future.cancelled():
                continue
            outcome = future.result()
            report["rows"].append(outcome)
            report["rows"].sort(key=lambda r: r["mission_id"])
            if outcome["status"] == "P0_STOP":
                report["status"] = "P0_STOP"
                for pending in futures:
                    pending.cancel()
            save(output / "baseline.json", report)
            print(json.dumps(dict(done=len(report["rows"]), total=len(jobs), mission_id=outcome["mission_id"],
                                  status=outcome["status"])), flush=True)
    if report["status"] != "P0_STOP":
        report["status"] = "BASELINE_COMPLETE_AWAITING_PROPOSAL"
    save(output / "baseline.json", report)
    pairs = [r['paired'] for r in report['rows'] if r['status']=='COMPLETE']
    natural = [r['natural_variation'] for r in report['rows'] if r.get('natural_variation') is not None]
    summary = dict(status=report['status'], overall=aggregate_pairs(pairs), natural_variation=aggregate_pairs(natural),
                   by_pattern={key: aggregate_pairs([r for r in pairs if r['flight_pattern']==key])
                               for key in sorted({r['flight_pattern'] for r in pairs})},
                   by_agents={str(key): aggregate_pairs([r for r in pairs if r['agents']==key])
                              for key in sorted({r['agents'] for r in pairs})},
                   natural_by_pattern={key: aggregate_pairs([r for r in natural if r['flight_pattern']==key])
                                       for key in sorted({r['flight_pattern'] for r in natural})})
    save(output / "aggregate.json", summary)
    return int(report["status"] == "P0_STOP")


if __name__ == "__main__":
    raise SystemExit(main())
