"""Run a development fast-dynamics episode through the complete public data pipeline."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swarm_sim.fast_dynamics.contracts import FastDynamicsConfig, M2Config
from swarm_sim.fast_dynamics.mission_executor import run_mission
from swarm_sim.fast_dynamics.output_policy import (
    OutputPolicyError, assert_created_within, assert_new_attempt_path,
    new_attempt_path, resolve_output_root, validate_run_id,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path, help="TaskSpec v3 JSON")
    parser.add_argument("--output", type=Path,
                        help="new attempt directory outside the repository; "
                             "default: <output-root>/<UTC timestamp>_<run-id>")
    parser.add_argument("--output-root", type=Path,
                        help="external root for attempts; default: FAST_DYNAMICS_OUTPUT_ROOT, "
                             "else the sibling SwarmData/fast_dynamics directory")
    parser.add_argument("--config", type=Path, help="strict fast_dynamics JSON configuration overrides")
    parser.add_argument("--legacy-m1", action="store_true", help="use the frozen M1 executor and data contract")
    parser.add_argument("--test-harness", type=Path, help="development-only reference fault configuration JSON")
    parser.add_argument("--no-semantic-reuse", action="store_true",
                        help="diagnostic: recompute identical M2 semantic inputs at every data-pipeline stage")
    parser.add_argument("--run-id", default="fast_dynamics_m2")
    args = parser.parse_args(argv)

    # Output policy first: a rejected root or target must fail before any artefact exists.
    try:
        args.run_id = validate_run_id(args.run_id)
        root = resolve_output_root(args.output_root)
        requested = args.output if args.output is not None else new_attempt_path(root["root"], args.run_id)
        args.output = assert_new_attempt_path(requested, root["root"], kind="attempt")
    except OutputPolicyError as exc:
        parser.error(str(exc))
    args.output_root_info = root

    pipeline_started = time.perf_counter()
    task_bytes = args.task.read_bytes()
    task = json.loads(task_bytes.decode("utf-8-sig"))
    config_type = FastDynamicsConfig if args.legacy_m1 else M2Config
    config = config_type.from_dict(json.loads(args.config.read_text(encoding="utf-8-sig")) if args.config else {})
    args.test_harness_config = json.loads(args.test_harness.read_text(encoding="utf-8-sig")) if args.test_harness else None
    if args.legacy_m1 and args.test_harness_config is not None:
        parser.error("--test-harness requires M2 execution")
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        assert_created_within(args.output, root["root"])
    except OutputPolicyError:
        args.output.rmdir()  # nothing has been written yet
        raise
    (args.output / "input_task.json").write_bytes(task_bytes)
    (args.output / "config.json").write_text(json.dumps(config.to_dict(), indent=2) + "\n", encoding="utf-8")
    if args.test_harness_config is not None:
        (args.output / "test_harness.json").write_text(json.dumps(args.test_harness_config, indent=2) + "\n", encoding="utf-8")
    attempt = dict(status="running", task_path=str(args.task.resolve()),
                   input_sha256=hashlib.sha256(task_bytes).hexdigest(), run_id=args.run_id,
                   training_eligible=False, purpose="M1 local development integration" if args.legacy_m1 else "M2 local development integration",
                   output_root=str(root["root"]), output_root_source=root["source"],
                   output_path=str(args.output))
    (args.output / "attempt.json").write_text(json.dumps(attempt, indent=2), encoding="utf-8")
    try:
        from swarm_sim.fast_dynamics.adapter import reuse_semantics
        with reuse_semantics(enabled=not args.no_semantic_reuse):
            report = _run_pipeline(args, task, task_bytes, config, pipeline_started)
    except BaseException as exc:
        attempt.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        (args.output / "failure.json").write_text(json.dumps(attempt, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.output / "attempt.json").write_text(json.dumps(attempt, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    print(json.dumps({k: report[k] for k in ("execution_status", "end_us", "frames", "simulation_wall_s", "end_to_end_wall_s")}, indent=2))
    return 0


def _run_pipeline(args, task, task_bytes, config, pipeline_started):
    from swarm_sim.fast_dynamics.artifacts import write_episode
    from swarm_sim.dataset import build_dataset
    from swarm_sim.dataset_audit import audit_dataset
    from swarm_sim.language_v0 import describe_dataset
    from swarm_sim.episode_loader import load_episode

    started = time.perf_counter()
    harness = getattr(args, "test_harness_config", None)
    result = run_mission(task, config, **({"test_harness": harness} if harness is not None else {}))
    simulate_s = time.perf_counter() - started
    # An interrupted/failed attempt is retained without a completion marker.
    analysis = write_episode(result.scene, result, args.output / "run", run_id=args.run_id,
        input_hashes={str(args.task.resolve()): hashlib.sha256(task_bytes).hexdigest()},
        config=config.to_dict(), seed=task["seed"])
    exported = build_dataset([args.output / "run"], args.output / "dataset")
    audit = audit_dataset(args.output / "dataset")
    if audit.get("issues"):
        (args.output / "audit_failed.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        raise ValueError("dataset audit failed; incomplete attempt retained for diagnosis")
    language = describe_dataset(args.output / "dataset", args.output / "language")
    loaded = load_episode(args.output / "dataset" / "episodes" / args.run_id)
    elapsed = time.perf_counter() - pipeline_started
    report = dict(protocol_version="fast_dynamics_v1", task_id=task["task_id"],
        family_id=result.scene["family_id"], input_sha256=hashlib.sha256(task_bytes).hexdigest(),
        execution_status=result.status, end_us=result.end_us, frames=len(result.time_us),
        simulation_wall_s=simulate_s, end_to_end_wall_s=elapsed,
        episode_realtime_factor=result.end_us / 1e6 / simulate_s,
        timing_scope="task/config loading through public loader; final report/completion write excluded; outer benchmark includes them",
        scope=("M2" if isinstance(config, M2Config) else "M1") + " local integration; uncalibrated, development only, not a production throughput benchmark",
        output=dict(path=str(args.output), root=str(args.output_root_info["root"]),
                    root_source=args.output_root_info["source"]),
        analysis=analysis, dataset=exported, audit=audit, language=language,
        loaded_agents=loaded["agent_ids"])
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    attempt_file = args.output / "attempt.json"
    attempt = json.loads(attempt_file.read_text(encoding="utf-8"))
    attempt.update(status="complete", execution_status=result.status)
    attempt_file.write_text(json.dumps(attempt, ensure_ascii=False, indent=2), encoding="utf-8")
    pending = args.output / "completion.json.tmp"
    pending.write_text(json.dumps(dict(status="complete", report_sha256=hashlib.sha256((args.output / "report.json").read_bytes()).hexdigest())), encoding="utf-8")
    pending.replace(args.output / "completion.json")
    return report


if __name__ == "__main__":
    raise SystemExit(main())
