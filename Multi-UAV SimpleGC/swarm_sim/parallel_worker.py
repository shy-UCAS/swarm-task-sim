"""One v0.6 attempt and independent evidence verification; no implicit resume.

The controller owns budgets, retries and ledgers. This adapter writes only the
reserved attempt directory and never launches more than one selected mission.
"""

import json
from pathlib import Path

from .generation import canonical_hash, checked_path, file_hash, verify_generation
from .protocol import manifest_protocol, semantic_protocol, validate_artifact_protocol
from .quality import policy_hash
from .validation_policy import finite
from .validation_policy_r12b import VERSION as POLICY_VERSION, assess_run


PROGRESS_VERSION = "ordered_route_progress_v2"
PATROL_VERSION = "perimeter_revisit_v2"
ARTIFACTS = ("quality", "labels", "execution_metrics", "ac4_timing_v3",
             "onboard_mission_param_check", "semantic_validation")
IDENTITY_FIELDS = ("attempt_id", "global_index", "shard_id", "attempt_index")


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _tree(path):
    root = Path(path).resolve()
    return {str(p.resolve()): file_hash(p) for p in sorted(root.rglob("*")) if p.is_file()}


def _inside(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError("worker evidence path escapes its reserved directory")
    return path


def _inputs(plan, attempt):
    tasks = [task for task in plan["tasks"] if task["global_index"] == attempt["global_index"]]
    if len(tasks) != 1:
        raise ValueError("attempt does not select exactly one frozen task")
    task = tasks[0]
    if (task["shard_id"] != attempt["shard_id"]
            or attempt["base_port"] != 19100 + 100 * attempt["shard_id"]
            or any(attempt.get(key, task[key]) != task[key] for key in ("mission_id", "family_id"))):
        raise ValueError("attempt mission, family, shard or port binding differs")
    bundle = Path(plan["bundle"]).resolve()
    listing, manifest = verify_generation(bundle / "mission_list.json")
    entries = [entry for entry in listing["missions"] if entry["mission_id"] == task["mission_id"]]
    if len(entries) != 1 or entries[0] != task["entry"] or entries[0].get("status") != "planned":
        raise ValueError("attempt entry differs from the complete frozen generation bundle")
    entry = entries[0]
    scene = _read(checked_path(bundle, entry["scene"]))
    protocol = semantic_protocol(scene, patrol_validator_version=PATROL_VERSION)
    if (plan.get("protocol", protocol) != protocol
            or plan.get("progress_mapping_version", PROGRESS_VERSION) != PROGRESS_VERSION
            or plan.get("patrol_validator_version", PATROL_VERSION) != PATROL_VERSION
            or plan.get("acceptance_policy", POLICY_VERSION) != POLICY_VERSION
            or policy_hash(plan["quality_policy"]) != plan["quality_policy_sha256"]):
        raise ValueError("frozen analysis protocol or quality policy differs")
    if (file_hash(plan["binary"]) != plan["firmware"]["sha256"]
            or file_hash(plan["parameters"]) != plan["parameters_sha256"]):
        raise ValueError("frozen firmware or parameters changed")
    binding = dict(mission_id=task["mission_id"], family_id=task["family_id"],
        task_sha256=entry["task_sha256"], scene_sha256=entry["scene_sha256"],
        generation_entry_sha256=canonical_hash(entry),
        mission_list_sha256=file_hash(bundle / "mission_list.json"),
        generation_manifest_sha256=file_hash(bundle / "generation_manifest.json"),
        quality_policy_sha256=plan["quality_policy_sha256"], semantic_protocol=protocol,
        progress_mapping_version=PROGRESS_VERSION, patrol_validator_version=PATROL_VERSION,
        acceptance_policy_version=POLICY_VERSION)
    generation = dict(generation_profile=_read(bundle / "generation_profile.json"),
        generation_manifest=manifest, generation_entry=entry)
    return task, scene, binding, generation


def assess_artifacts(scene, metadata, artifacts, plan, *, retry_reason=None):
    """B098 checks: failed execution alone is an ineligible retained episode.

Unknown separation/onboard evidence remains unknown. The original assessment
is preserved for global rolling accounting; confirmed violations still stop.
"""
    quality, labels = artifacts["quality"], artifacts["labels"]
    assessment = assess_run(scene, metadata, quality, labels, artifacts["execution_metrics"],
        artifacts["ac4_timing_v3"], artifacts["onboard_mission_param_check"], stage="batch")
    if assessment != quality.get("validation_policy"):
        raise ValueError("stored assessment differs from independent r1.2b recomputation")
    separation = quality.get("truth_separation", {})
    minimum, required = separation.get("minimum_m"), scene.get("min_separation_m")
    separation_check = None
    if finite(minimum) and finite(required):
        if minimum < required:
            separation_check = False
        elif separation.get("status") == "clear_observed":
            separation_check = True
    onboard = artifacts["onboard_mission_param_check"]
    mismatches = onboard.get("counts", {}).get("mismatch_count")
    onboard_check = None
    if onboard.get("status") == "mismatch" or finite(mismatches) and mismatches > 0:
        onboard_check = False
    elif onboard.get("pass_gate") is True and onboard.get("status") == "pass":
        onboard_check = True
    agents = {vehicle["id"] for vehicle in scene["vehicles"]}
    cleanup, firmware = metadata.get("cleanup", {}), metadata.get("binary_firmware", {})
    checks = dict(assessment["hard_checks"], truth_separation=separation_check,
        onboard_mission_parameters=onboard_check,
        frozen_firmware_and_parameters=firmware.get("sha256") == plan["firmware"]["sha256"]
            and firmware.get("version_string") == plan["firmware"]["version_string"]
            and metadata.get("parameters_sha256") == plan["parameters_sha256"],
        infrastructure_cleanup_complete=bool(agents) and set(cleanup) == agents
            and all(type(cleanup[agent]) is int for agent in agents),
        infrastructure_execution_completed=not quality.get("analysis_error"))
    # The inherited whitelist proves a transient pre-arm failure, including
    # incomplete readback, rather than a confirmed firmware/parameter mismatch.
    # Its stored r1.2b assessment remains unchanged. A mismatch never whitelists.
    if retry_reason and checks["parameter_firmware"] is False:
        checks["parameter_firmware"] = None
    if metadata.get("status") != "completed" and quality.get("episode_quality_eligible") is not False:
        raise ValueError("failed execution must retain its quality-ineligible verdict")
    infrastructure = []
    if quality.get("analysis_error"):
        infrastructure.append("analysis_error: " + str(quality["analysis_error"]))
    if not checks["infrastructure_cleanup_complete"]:
        infrastructure.append("process cleanup is incomplete or unverifiable")
    if metadata.get("status") == "interrupted":
        infrastructure.append("interrupted attempt requires manual review; never retry automatically")
    return dict(qualified=quality.get("episode_quality_eligible") is True,
        episode_quality_eligible=quality.get("episode_quality_eligible"),
        mission_success=labels.get("mission_success"),
        mission_success_observation=labels.get("mission_success_observation"),
        semantic_consistency=labels.get("semantic_consistency"), run_status=metadata.get("status"),
        batch_hard_checks=checks, hard_failures=[key for key, value in checks.items() if value is False],
        soft_flags=assessment["soft_flags"], semantic_flags=assessment.get("semantic_flags", []),
        new_anomalies=assessment.get("new_anomalies", []), assessment=assessment,
        infrastructure_error="; ".join(infrastructure) or None)


def _validated_evidence(plan, attempt, result, scene, generation):
    from scripts.run_v05c_validation import preflight_retry_reason

    root = Path(attempt["attempt_directory"]).resolve()
    directory = _inside(result["run_directory"], root / "run")
    analysis = Path(result["analysis_directory"]).resolve()
    if analysis != root / "analysis":
        raise ValueError("formal analysis is outside this attempt's analysis directory")
    runner_ledger = _read(root / "run" / "attempt_ledger.json")
    context, missions = runner_ledger.get("execution_context", {}), runner_ledger.get("missions", [])
    required_context = dict(selected_mission_ids=[result["mission_id"]],
        base_port=attempt["base_port"], max_environment_retries=0, retryable_errors=[],
        mission_list_sha256=result["mission_list_sha256"],
        generation_manifest_sha256=result["generation_manifest_sha256"],
        quality_policy_sha256=plan["quality_policy_sha256"],
        binary_sha256=plan["firmware"]["sha256"], parameters_sha256=plan["parameters_sha256"])
    if (any(context.get(key) != value for key, value in required_context.items())
            or len(missions) != 1 or missions[0].get("mission_id") != result["mission_id"]
            or len(missions[0].get("attempts", [])) != 1
            or Path(missions[0]["attempts"][0].get("run_directory", "")).resolve() != directory):
        raise ValueError("runner ledger mission, input or single-attempt binding differs")
    metadata, manifest = _read(directory / "metadata.json"), _read(analysis / "manifest.json")
    if (canonical_hash(metadata.get("scenario")) != canonical_hash(scene)
            or _read(directory / "scenario.json") != scene
            or not isinstance(metadata.get("run_id"), str) or not metadata["run_id"]
            or metadata["run_id"] != manifest.get("run_id")
            or Path(manifest.get("run_directory", "")).resolve() != directory
            or manifest.get("run_status") != metadata.get("status")
            or metadata.get("quality_policy_sha256") != plan["quality_policy_sha256"]
            or manifest.get("quality_policy_sha256") != plan["quality_policy_sha256"]
            or policy_hash(manifest["quality_policy"]) != plan["quality_policy_sha256"]
            or manifest.get("route_progress_version") != PROGRESS_VERSION
            or manifest_protocol(manifest) != semantic_protocol(scene, patrol_validator_version=PATROL_VERSION)
            or manifest.get("acceptance_policy_version") != POLICY_VERSION):
        raise ValueError("selected analysis source, scenario, protocol or policy mismatch")
    sources, artifacts = manifest["source_sha256"], manifest["artifact_sha256"]
    required_sources = {"metadata.json", "scenario.json", "events.jsonl", "firmware_parameters.json"}
    required_sources.update(name + ".json" for name in generation)
    if (not required_sources <= set(sources)
            or not {name + ".json" for name in ARTIFACTS} <= set(artifacts)):
        raise ValueError("formal analysis is missing required source or artifact bindings")
    for base, hashes in ((directory, sources), (analysis, artifacts)):
        for name, expected in hashes.items():
            if file_hash(checked_path(base, name)) != expected:
                raise ValueError("analysis source or artifact hash changed: " + name)
    for name, expected in generation.items():
        if _read(directory / (name + ".json")) != expected:
            raise ValueError("run generation provenance differs from the frozen full bundle")
    expected_code = {p.name: file_hash(p) for p in sorted((Path(plan["project_root"]) / "swarm_sim").glob("*.py"))}
    if not expected_code or manifest.get("analysis_source_sha256") != expected_code:
        raise ValueError("formal analysis source code binding differs")
    validate_artifact_protocol(manifest, analysis)
    values = {name: _read(analysis / (name + ".json")) for name in ARTIFACTS}
    if values["quality"].get("validation_policy", {}).get("stage") != "batch":
        raise ValueError("formal analysis acceptance stage differs")
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()
              if line.strip()]
    reason = preflight_retry_reason(metadata, _read(directory / "firmware_parameters.json"), events)
    assessed = assess_artifacts(scene, metadata, values, plan, retry_reason=reason)
    assessed.update(run_id=metadata["run_id"], retryable_pre_takeoff=reason is not None,
        retry_reason=reason, flight_epoch_present="flight_epoch_monotonic_s" in metadata)
    return assessed


def verify_result(plan, attempt, result):
    """Reopen source evidence before registration, recovery or merge.

An infrastructure-error result can be retained for reporting, but never made
mergeable or retryable. All successful claims are independently recomputed.
"""
    _, scene, binding, generation = _inputs(plan, attempt)
    if (any(result.get(key) != attempt[key] for key in IDENTITY_FIELDS)
            or any(result.get(key) != value for key, value in binding.items())):
        raise ValueError("result identity or frozen input binding differs")
    root = Path(attempt["attempt_directory"]).resolve()
    evidence = dict(_tree(root / "run"), **_tree(root / "analysis"))
    if result.get("evidence_sha256") != evidence:
        raise ValueError("result evidence hashes are changed, missing or incomplete")
    # Unverified errors are retained only as stop records. A normal analyzed
    # result, even with an analysis_error flag, still follows full verification.
    if result.get("verification_error"):
        if (not result.get("infrastructure_error") or result.get("retryable_pre_takeoff")
                or result.get("qualified") or result.get("episode_quality_eligible") is not False):
            raise ValueError("unverified worker error must stop and cannot claim eligibility or retry")
        return dict(result)
    derived = _validated_evidence(plan, attempt, result, scene, generation)
    if any(result.get(key) != value for key, value in derived.items()):
        raise ValueError("stored worker outcome differs from independent evidence verification")
    return dict(result)


def execute_attempt(plan, attempt):
    """Execute one already reserved attempt. Only an explicit caller launches.

No automatic restart/resume is requested from the old runner. The caller writes
result.json atomically after this function returns, then verifies and registers.
"""
    from scripts.run_mission_list import run_mission_list
    from .analysis_v3 import analyze_run_v3

    task, scene, binding, generation = _inputs(plan, attempt)
    root = Path(attempt["attempt_directory"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / "run").exists() or (root / "analysis").exists() or (root / "result.json").exists():
        raise ValueError("attempt already has execution evidence; never automatically rerun")
    result = dict({key: attempt[key] for key in IDENTITY_FIELDS}, **binding,
        run_directory=None, analysis_directory=None, evidence_sha256={},
        assessment=None, hard_failures=[], retryable_pre_takeoff=False, retry_reason=None,
        infrastructure_error=None, run_status=None, episode_quality_eligible=False, qualified=False)
    try:
        ledger = run_mission_list(Path(plan["bundle"]) / "mission_list.json", max_runs=1,
            resume=False, output_root=root / "run", mission_ids=[task["mission_id"]],
            binary=plan["binary"], parameters=plan["parameters"], base_port=attempt["base_port"],
            quality_policy=plan["quality_policy"], max_environment_retries=0, retryable_errors=())
        missions = ledger.get("missions", [])
        if (len(missions) != 1 or missions[0].get("mission_id") != task["mission_id"]
                or len(missions[0].get("attempts", [])) != 1):
            raise ValueError("single-attempt runner returned an unexpected mission or attempt count")
        executed = missions[0]["attempts"][0]
        result.update(runner_status=executed.get("status"), runner_error=executed.get("error"),
            run_directory=executed.get("run_directory"))
        if not result["run_directory"]:
            raise ValueError("runner returned no run directory")
        directory = _inside(result["run_directory"], root / "run")
        metadata = _read(directory / "metadata.json")
        result.update(run_id=metadata.get("run_id"), run_status=metadata.get("status"))
        result["analysis_directory"] = str(root / "analysis")
        analyze_run_v3(directory, plan["quality_policy"], progress_mapping_version=PROGRESS_VERSION,
            patrol_validator_version=PATROL_VERSION, acceptance_policy=POLICY_VERSION,
            acceptance_stage="batch", output_directory=root / "analysis", update_latest=False)
        result.update(_validated_evidence(plan, attempt, result, scene, generation))
        result["evidence_sha256"] = dict(_tree(root / "run"), **_tree(root / "analysis"))
        return verify_result(plan, attempt, result)
    except (Exception, KeyboardInterrupt) as exc:
        error = f"{type(exc).__name__}: {exc}"
        result.update(infrastructure_error=error, verification_error=error,
            hard_failures=["infrastructure_or_integrity_failure"], qualified=False,
            episode_quality_eligible=False, retryable_pre_takeoff=False, retry_reason=None,
            evidence_sha256=dict(_tree(root / "run"), **_tree(root / "analysis")))
        return result
