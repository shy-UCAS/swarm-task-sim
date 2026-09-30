"""Bounded sequential SITL execution with frozen inputs and verified resume evidence."""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from swarm_sim.generation import canonical_hash, checked_path, file_hash, verify_generation
from swarm_sim.quality import policy_hash, resolve_policy
from swarm_sim.protocol import manifest_protocol, semantic_protocol, validate_artifact_protocol
from swarm_sim.runner import run_scene
from swarm_sim.tasks import validate_task_binding

LEDGER_VERSION = "bounded_mission_runner_v1"
RETRYABLE_ENVIRONMENT_FAILURES = {"port_unavailable", "sitl_process_exit", "connection_failure"}


def _save_atomic(path, value):
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    temp.replace(path)


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _environment_code(error):
    error = str(error).lower()
    if "address already in use" in error or "winerror 10048" in error:
        return "port_unavailable"
    if "sitl exited (" in error:
        return "sitl_process_exit"
    if "connection refused" in error or "winerror 10061" in error:
        return "connection_failure"
    return None


def _classify(metadata, quality):
    if metadata.get("status") == "interrupted":
        return "interrupted"
    if metadata.get("status") != "completed":
        return "execution_failed"
    if quality.get("analysis_error"):
        return "analysis_failed"
    if quality.get("mission_success") is False:
        return "semantic_failed"
    if quality.get("mission_success") is None:
        return "semantic_unknown"
    if not quality.get("benchmark_eligible", quality.get("usable", False)):
        return "quality_failed"
    return "succeeded"


def _verify_result(run_path, expected_scene, policy_fingerprint, selected=None, generation_context=None):
    """Verify the exact selected analysis, all artifacts and immutable run sources."""
    root = Path(run_path).resolve()
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    if canonical_hash(metadata["scenario"]) != canonical_hash(expected_scene):
        raise ValueError("resume run scenario does not match current frozen input")
    if metadata.get("quality_policy_sha256") != policy_fingerprint:
        raise ValueError("resume run quality policy differs from current policy")
    selected = selected or json.loads((root / "analysis_latest.json").read_text(encoding="utf-8"))
    analysis = checked_path(root, selected["directory"])
    if analysis.parent != root or file_hash(analysis / "manifest.json") != selected["manifest_sha256"]:
        raise ValueError("resume selected analysis manifest changed")
    manifest = json.loads((analysis / "manifest.json").read_text(encoding="utf-8"))
    if manifest_protocol(manifest) != semantic_protocol(expected_scene):
        raise ValueError("resume analysis semantic protocol differs from current execution protocol")
    if manifest.get("quality_policy_sha256") != policy_fingerprint:
        raise ValueError("resume analysis quality policy differs from current policy")
    for name, expected in manifest["artifact_sha256"].items():
        if file_hash(checked_path(analysis, name)) != expected:
            raise ValueError(f"resume analysis artifact changed: {name}")
    validate_artifact_protocol(manifest, analysis)
    for name, expected in manifest["source_sha256"].items():
        if file_hash(checked_path(root, name)) != expected:
            raise ValueError(f"resume run source changed: {name}")
    if generation_context:
        for name, expected in generation_context.items():
            filename = name + ".json"
            if filename not in manifest["source_sha256"]:
                raise ValueError(f"generation source is absent from run analysis: {filename}")
            if canonical_hash(json.loads((root / filename).read_text(encoding="utf-8"))) != canonical_hash(expected):
                raise ValueError(f"run generation provenance differs from current input: {filename}")
    quality = json.loads((analysis / "quality.json").read_text(encoding="utf-8"))
    labels = json.loads((analysis / "labels.json").read_text(encoding="utf-8"))
    quality["mission_success"] = labels.get("mission_success")
    return metadata, quality, selected


def run_mission_list(mission_list_path, max_runs=3, resume=False, output_root=None, binary=None,
                     parameters=None, base_port=19100, quality_policy=None, max_environment_retries=0,
                     retryable_errors=(), mission_ids=None):
    """Run at most max_runs attempts, including retries; never parallelize scenes.

    Resume skips only terminal attempts backed by a verified frozen analysis.
    Failed attempts remain terminal unless an explicitly enabled environment
    retry applies. Interrupted/incomplete attempts get a new unique directory.
    """
    if isinstance(max_runs, bool) or not isinstance(max_runs, int) or not 1 <= max_runs <= 10:
        raise ValueError("max_runs must be an integer in [1, 10]")
    if (isinstance(max_environment_retries, bool) or not isinstance(max_environment_retries, int)
            or not 0 <= max_environment_retries <= 2):
        raise ValueError("max_environment_retries must be an integer in [0, 2]")
    if set(retryable_errors) - RETRYABLE_ENVIRONMENT_FAILURES:
        raise ValueError("only explicit transient environment failure categories may be retried")
    list_path = Path(mission_list_path).resolve()
    listing, generation_manifest = verify_generation(list_path)
    known_ids = [entry["mission_id"] for entry in listing["missions"]]
    if mission_ids is not None:
        if (not isinstance(mission_ids, (list, tuple)) or not mission_ids
                or any(not isinstance(value, str) or not value for value in mission_ids)):
            raise ValueError("mission_ids must be a nonempty list of mission IDs")
        if len(set(mission_ids)) != len(mission_ids):
            raise ValueError("duplicate mission IDs in selection")
        if set(mission_ids) - set(known_ids):
            raise ValueError("unknown mission IDs in selection")
    selected_ids = [value for value in known_ids if mission_ids is None or value in mission_ids]
    selected_entries = [entry for entry in listing["missions"] if entry["mission_id"] in selected_ids]
    generation_profile = json.loads((list_path.parent / "generation_profile.json").read_text(encoding="utf-8"))
    policy = resolve_policy(quality_policy)
    binary = Path(binary or PROJECT / "ArducopterSITL/arducopter.exe").resolve()
    parameters = Path(parameters or PROJECT / "ArducopterSITL/copter.parm").resolve()
    output = Path(output_root or list_path.parent / "execution").resolve()
    ledger_path = output / "attempt_ledger.json"
    context = dict(runner_version=LEDGER_VERSION, mission_list_sha256=file_hash(list_path),
                   selected_mission_ids=selected_ids,
                   generation_manifest_sha256=file_hash(list_path.parent / "generation_manifest.json"),
                   quality_policy_sha256=policy_hash(policy), base_port=base_port,
                   binary_sha256=file_hash(binary), parameters_sha256=file_hash(parameters),
                   code_sha256={p.name: file_hash(p) for p in sorted((PROJECT / "swarm_sim").glob("*.py"))},
                   runner_script_sha256=file_hash(__file__), max_environment_retries=max_environment_retries,
                   retryable_errors=sorted(set(retryable_errors)))
    scenes, generation_contexts = {}, {}
    for entry in selected_entries:
        if entry["status"] == "planned":
            scene = json.loads(checked_path(list_path.parent, entry["scene"]).read_text(encoding="utf-8"))
            validate_task_binding(scene)
            scenes[entry["mission_id"]] = scene
            generation_contexts[entry["mission_id"]] = dict(generation_profile=generation_profile,
                generation_manifest=generation_manifest, generation_entry=entry)
    if ledger_path.exists():
        if not resume:
            raise ValueError("attempt ledger exists; use --resume or select a new output root")
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        if ledger["execution_context"] != context:
            raise ValueError("resume input/code/protocol/quality/execution configuration changed; use a new output root")
    else:
        if resume:
            raise ValueError("no attempt ledger exists to resume")
        output.mkdir(parents=True, exist_ok=False)
        ledger = dict(schema_version=1, execution_context=context, created_utc=_utc(),
                      generation_directory=str(list_path.parent), missions=[dict(mission_id=e["mission_id"],
                          family_id=e["family_id"], base_scene_id=e["base_scene_id"], variant_id=e["variant_id"],
                          task_sha256=e["task_sha256"], scene_sha256=e.get("scene_sha256"),
                          status="pending" if e["status"] == "planned" else "planning_rejected",
                          reason=e.get("reason"), attempts=[]) for e in selected_entries])
        _save_atomic(ledger_path, ledger)
    # Validate every recorded terminal analysis before launching any new processes.
    for item in ledger["missions"]:
        for attempt in item["attempts"]:
            if attempt.get("selected_analysis"):
                metadata, quality, _ = _verify_result(attempt["run_directory"], scenes[item["mission_id"]],
                    context["quality_policy_sha256"], attempt["selected_analysis"], generation_contexts[item["mission_id"]])
                if _classify(metadata, quality) != attempt["status"]:
                    raise ValueError("resume attempt status differs from its immutable analysis evidence")
            elif attempt["status"] == "succeeded":
                raise ValueError("recorded success lacks a verified analysis")
            elif attempt["status"] == "running":
                # A crash after run_scene returned may leave a complete run not yet in the ledger.
                runs = list(Path(attempt["attempt_directory"]).glob("*/metadata.json"))
                if len(runs) > 1:
                    raise ValueError("interrupted attempt contains multiple unexpected runs")
                if runs and (runs[0].parent / "analysis_latest.json").is_file():
                    metadata, quality, selected = _verify_result(runs[0].parent, scenes[item["mission_id"]],
                        context["quality_policy_sha256"], generation_context=generation_contexts[item["mission_id"]])
                    attempt.update(status=_classify(metadata, quality), run_directory=str(runs[0].parent),
                                   selected_analysis=selected, recovered=True, run_status=metadata.get("status"),
                                   mission_success=quality.get("mission_success"),
                                   benchmark_eligible=quality.get("benchmark_eligible", False),
                                   strict_benchmark_eligible=quality.get("strict_benchmark_eligible", False))
                else:
                    attempt.update(status="interrupted", recovered=True,
                                   reason="previous process ended before a complete analysis was recorded")
                item["status"] = attempt["status"]
    _save_atomic(ledger_path, ledger)
    launched = 0
    stop = False
    for item in ledger["missions"]:
        if launched >= max_runs or stop:
            break
        while launched < max_runs:
            previous = item["attempts"][-1] if item["attempts"] else None
            retry = (previous and previous.get("environment_failure") in retryable_errors
                     and sum(a.get("environment_failure") in retryable_errors for a in item["attempts"])
                     <= max_environment_retries)
            if item["status"] not in ("pending", "interrupted") and not retry:
                break
            attempt_id = uuid.uuid4().hex
            attempt_dir = output / "attempts" / attempt_id
            attempt_dir.mkdir(parents=True, exist_ok=False)
            attempt = dict(attempt_id=attempt_id, attempt_index=len(item["attempts"]),
                           family_id=item["family_id"], task_sha256=item["task_sha256"],
                           status="running", started_utc=_utc(), attempt_directory=str(attempt_dir))
            item["attempts"].append(attempt)
            item["status"] = "running"
            _save_atomic(ledger_path, ledger)
            launched += 1
            try:
                directory, metadata, quality = run_scene(scenes[item["mission_id"]], attempt_dir, binary,
                    parameters, base_port, policy, generation_context=generation_contexts[item["mission_id"]])
                attempt.update(run_directory=str(Path(directory).resolve()), status=_classify(metadata, quality),
                               run_status=metadata.get("status"), mission_success=quality.get("mission_success"),
                               benchmark_eligible=quality.get("benchmark_eligible", False),
                               strict_benchmark_eligible=quality.get("strict_benchmark_eligible", False),
                               error=metadata.get("error") or quality.get("analysis_error"),
                               environment_failure=_environment_code(metadata.get("error", "")))
                if (Path(directory) / "analysis_latest.json").is_file():
                    _, _, selected = _verify_result(directory, scenes[item["mission_id"]], context["quality_policy_sha256"],
                        generation_context=generation_contexts[item["mission_id"]])
                    attempt["selected_analysis"] = selected
                elif attempt["status"] == "succeeded":
                    raise ValueError("run reported success without complete analysis evidence")
                stop = attempt["status"] == "interrupted"
            except KeyboardInterrupt:
                attempt.update(status="interrupted", error="KeyboardInterrupt")
                stop = True
            except Exception as exc:
                attempt.update(status="runner_exception", error=f"{type(exc).__name__}: {exc}")
                stop = True
            attempt["finished_utc"] = _utc()
            item["status"] = attempt["status"]
            _save_atomic(ledger_path, ledger)
            if stop or not attempt.get("environment_failure") in retryable_errors:
                break
    ledger["last_invocation"] = dict(launched_attempts=launched, max_runs=max_runs, stopped_early=stop, finished_utc=_utc())
    _save_atomic(ledger_path, ledger)
    return ledger


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mission_list", type=Path)
    parser.add_argument("--max-runs", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--mission-id", action="append", dest="mission_ids",
                        help="Select a known mission; repeat for a subset. List order is retained; repeat the same selection on resume.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sitl", type=Path)
    parser.add_argument("--parameters", type=Path)
    parser.add_argument("--base-port", type=int, default=19100)
    parser.add_argument("--quality-policy", type=Path)
    parser.add_argument("--max-environment-retries", type=int, default=0)
    parser.add_argument("--retry-environment", action="append", choices=sorted(RETRYABLE_ENVIRONMENT_FAILURES), default=[])
    args = parser.parse_args(argv)
    try:
        policy = json.loads(args.quality_policy.read_text(encoding="utf-8-sig")) if args.quality_policy else None
        result = run_mission_list(args.mission_list, args.max_runs, args.resume, args.output, args.sitl,
            args.parameters, args.base_port, policy, args.max_environment_retries, args.retry_environment, args.mission_ids)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    print(json.dumps(dict(last_invocation=result["last_invocation"],
        statuses={m["mission_id"]: m["status"] for m in result["missions"]}), indent=2))
    terminal_failures = {"execution_failed", "semantic_failed", "semantic_unknown", "quality_failed",
                         "analysis_failed", "runner_exception", "interrupted"}
    return int(any(m["status"] in terminal_failures for m in result["missions"]))


if __name__ == "__main__":
    raise SystemExit(main())
