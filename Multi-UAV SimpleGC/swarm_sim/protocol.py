"""Semantic protocol identity, independent of numerical quality-policy versions."""

import json
from pathlib import Path

SHARED_SEMANTIC_VERSION = "shared_coverage_v2"
SHARED_CONSTRAINT_VERSION = "execution_limits_v2"
SHARED_LABEL_SCHEMA_VERSION = 2
V3_SEMANTIC_VERSION = "multi_intent_validation_v1"
V3_CONSTRAINT_VERSION = "multi_intent_execution_limits_v1"
V05_SEMANTIC_VERSION = "multi_intent_validation_v2"
V05_CONSTRAINT_VERSION = "multi_intent_execution_limits_v2"
V05_ROUTE_PROGRESS_VERSION = "ordered_route_progress_v1"
V05_AC4_TIMING_VERSION = "ac4_relative_progress_timing_v3"
V05_EXECUTION_ARTIFACTS_VERSION = "execution_artifacts_v2"

PROTOCOL_FIELDS = ("task_kind", "ontology_version", "label_schema_version", "semantic_validation_version",
                   "eligibility_protocol_version", "execution_constraints_version")


def is_v05_task_spec(task):
    """Select the new contract from explicit TaskSpec features, never a run date."""
    if not isinstance(task, dict) or task.get("schema_version") != 3:
        return False
    mission = task.get("mission", {})
    execution = task.get("execution", {})
    if not isinstance(mission, dict) or not isinstance(execution, dict):
        return False
    timing = execution.get("async_timing_tolerance", {})
    return (mission.get("intent") == "patrol" or "hold_semantics" in execution or
            isinstance(timing, dict) and "max_s" in timing)


def semantic_protocol(scene):
    task = scene.get("task_spec", {})
    if task.get("schema_version") == 3:
        new_contract = is_v05_task_spec(task)
        return dict(task_kind="mission_v3", ontology_version="multi_intent_mission_v1", label_schema_version=3,
                    semantic_validation_version=V05_SEMANTIC_VERSION if new_contract else V3_SEMANTIC_VERSION,
                    eligibility_protocol_version="multi_intent_quality_v1",
                    execution_constraints_version=V05_CONSTRAINT_VERSION if new_contract else V3_CONSTRAINT_VERSION)
    if task.get("schema_version") == 2:
        return dict(task_kind="mission_v2", ontology_version="shared_mission_v1", label_schema_version=SHARED_LABEL_SCHEMA_VERSION,
                    semantic_validation_version=SHARED_SEMANTIC_VERSION, eligibility_protocol_version="shared_quality_v1",
                    execution_constraints_version=SHARED_CONSTRAINT_VERSION)
    return dict(task_kind="primitive_v1", ontology_version="primitives_v1", label_schema_version=1,
                semantic_validation_version="fcu_geometric_v1", eligibility_protocol_version="primitive_quality_v022",
                execution_constraints_version="not_applicable")


def manifest_protocol(manifest):
    defaults = semantic_protocol({})
    present = [key in manifest for key in PROTOCOL_FIELDS]
    if any(present) and not all(present):
        raise ValueError("incomplete semantic protocol in analysis manifest")
    # v0.2.2 manifests did not carry these fields; their unchanged v1 meaning is explicit.
    if not any(present):
        if manifest.get("analysis_version") not in ("0.2.0", "0.2.1", "0.2.2"):
            raise ValueError("analysis is missing semantic protocol; reanalyze the run")
        return defaults
    protocol = {key: manifest[key] for key in PROTOCOL_FIELDS}
    if any(isinstance(value, bool) or not isinstance(value, (str, int)) or value == "" for value in protocol.values()):
        raise ValueError("invalid semantic protocol value")
    return protocol


def validate_artifact_protocol(manifest, root):
    """Reject inconsistent version claims even when each file's hash is valid."""
    protocol = manifest_protocol(manifest)
    if protocol["task_kind"] == "mission_v3":
        return _validate_v3_artifacts(manifest, Path(root), protocol)
    if protocol["task_kind"] != "mission_v2":
        return
    artifacts = {}
    for name in ("labels.json", "quality.json", "semantic_validation.json", "execution_constraints.json"):
        if name not in manifest.get("artifact_sha256", {}):
            raise ValueError(f"semantic protocol artifact is not hashed: {name}")
        artifacts[name] = json.loads((Path(root) / name).read_text(encoding="utf-8"))
    labels = artifacts["labels.json"]
    version = protocol["semantic_validation_version"]
    behavior_versions = [behavior.get("rule_version") for behavior in labels.get("observed_behaviors", [])]
    if (manifest_protocol(artifacts["quality.json"]) != protocol
            or labels.get("schema_version") != protocol["label_schema_version"]
            or labels.get("task_kind") != protocol["task_kind"]
            or labels.get("label_provenance", {}).get("semantic_validation_version") != version
            or not behavior_versions or any(value != version for value in behavior_versions)
            or artifacts["semantic_validation.json"].get("semantic_validation_version") != version
            or artifacts["execution_constraints.json"].get("constraint_validation_version") != protocol["execution_constraints_version"]):
        raise ValueError("inconsistent semantic protocol across analysis artifacts")


def supported_protocols():
    """Explicit historical and current contracts; TaskSpec chooses between them."""
    return {tuple(semantic_protocol(scene)[key] for key in PROTOCOL_FIELDS)
            for scene in ({}, {"task_spec": {"schema_version": 2}},
                          {"task_spec": {"schema_version": 3}},
                          {"task_spec": {"schema_version": 3, "mission": {"intent": "patrol"}}})}


def _validate_v3_artifacts(manifest, root, protocol):
    from .observation_processing import processing_versions
    from .registry import get_intent
    from .quality import v3_eligibility
    if tuple(protocol[k] for k in PROTOCOL_FIELDS) not in supported_protocols():
        raise ValueError("unsupported v3 semantic protocol")
    files = {}
    for name in ("labels.json", "quality.json", "semantic_validation.json", "execution_constraints.json", "task.json"):
        if name not in manifest.get("artifact_sha256", {}):
            raise ValueError(f"semantic protocol artifact is not hashed: {name}")
        files[name] = json.loads((root/name).read_text(encoding="utf-8"))
    labels, quality, task = files["labels.json"], files["quality.json"], files["task.json"]
    if semantic_protocol({"task_spec": task}) != protocol:
        raise ValueError("v3 TaskSpec semantic protocol mismatch")
    if is_v05_task_spec(task) and task.get("execution", {}).get("control_mode") == "semantic_phase_route_v1":
        required = ("execution_metrics.json", "ac4_timing_v3.json")
        if any(name not in manifest.get("artifact_sha256", {}) for name in required):
            raise ValueError("v0.5 protocol requires versioned route evidence artifacts")
        metrics = json.loads((root / "execution_metrics.json").read_text(encoding="utf-8"))
        ac4 = json.loads((root / "ac4_timing_v3.json").read_text(encoding="utf-8"))
        expected_versions = dict(route_progress_version=V05_ROUTE_PROGRESS_VERSION,
                                 ac4_timing_version=V05_AC4_TIMING_VERSION,
                                 execution_artifacts_version=V05_EXECUTION_ARTIFACTS_VERSION)
        if (any(artifact.get(key) != value for artifact in
                (manifest, quality, labels.get("label_provenance", {}), ac4)
                for key, value in expected_versions.items())
                or metrics.get("version") != V05_EXECUTION_ARTIFACTS_VERSION
                or set(ac4.get("channels", {})) != {"truth", "observation"}
                or any(channel.get("version") != V05_AC4_TIMING_VERSION or
                       channel.get("mapping_version") != V05_ROUTE_PROGRESS_VERSION
                       for channel in ac4["channels"].values())
                or any(ac4.get(key) != value for key, value in processing_versions().items())):
            raise ValueError("inconsistent v0.5 route evidence versions")
    hold_semantics = task.get("execution", {}).get("hold_semantics")
    onboard_name = "onboard_mission_param_check.json"
    if hold_semantics == "integer_seconds_v1" or onboard_name in manifest.get("artifact_sha256", {}):
        from .onboard_mission_params import VERSION as onboard_version

        if onboard_name not in manifest.get("artifact_sha256", {}):
            raise ValueError("integer hold semantics requires hashed onboard mission parameter evidence")
        onboard = json.loads((root / onboard_name).read_text(encoding="utf-8"))
        required = hold_semantics == "integer_seconds_v1"
        status = onboard.get("status")
        passed = onboard.get("pass_gate")
        if (onboard.get("version") != onboard_version or onboard.get("required") is not required
                or status not in ("pass", "mismatch", "unknown")
                or passed is not ((status == "pass") if required else None)
                or any(artifact.get("onboard_mission_param_check_version") != onboard_version
                       or artifact.get("onboard_mission_param_check_status") != status
                       or artifact.get("onboard_mission_param_check_required") is not required
                       or artifact.get("onboard_mission_param_check_pass") is not passed
                       for artifact in (quality, manifest))):
            raise ValueError("inconsistent onboard mission parameter evidence")
    task_agents = [v["id"] for v in task["scenario"]["vehicles"]]
    manifest_agents = manifest.get("agent_ids")
    if (not isinstance(manifest_agents, list) or not manifest_agents
            or any(not isinstance(a, str) or not a for a in manifest_agents + task_agents)
            or len(set(manifest_agents)) != len(manifest_agents) or len(set(task_agents)) != len(task_agents)
            or set(manifest_agents) != set(task_agents)):
        raise ValueError("inconsistent v3 task and manifest agent identities")
    if (not isinstance(manifest.get("run_status"), str) or not manifest["run_status"]
            or type(quality.get("run_completed")) is not bool
            or quality["run_completed"] != (manifest["run_status"] == "completed")):
        raise ValueError("inconsistent v3 run completion evidence")
    if manifest.get("clock_quality") != quality.get("clock_quality"):
        raise ValueError("inconsistent v3 clock quality evidence")
    from .observations import finite_number
    for key in ("observation_valid_fraction", "truth_valid_fraction"):
        fractions = quality.get(key)
        if (not isinstance(fractions, dict) or set(fractions) != set(task_agents)
                or any(not finite_number(v) or not 0 <= v <= 1 for v in fractions.values())):
            raise ValueError(f"inconsistent v3 per-agent quality evidence: {key}")
    intent = get_intent(task["mission"]["intent"])
    validators = {intent.name: intent.validator_version}
    from .families import scene_family_id
    if (task.get("schema_version") != 3 or task.get("family_scheme") != "scene_content_v1"
            or task.get("family_id") != scene_family_id(task["scenario"])
            or manifest.get("family_id") != task["family_id"] or manifest.get("family_scheme") != "scene_content_v1"):
        raise ValueError("inconsistent v3 scene-content family identity")
    mode = task["execution"]["control_mode"]
    if mode not in ("waypoint_barrier_v1", "semantic_phase_route_v1") or manifest.get("control_mode") != mode:
        raise ValueError("inconsistent v3 control_mode")
    if (manifest_protocol(quality) != protocol or labels.get("schema_version") != protocol["label_schema_version"]
            or labels.get("task_kind") != "mission_v3" or labels.get("requested_intent") != intent.name
            or labels.get("label_provenance", {}).get("semantic_validation_version") != protocol["semantic_validation_version"]
            or labels.get("label_provenance", {}).get("validator_versions") != validators
            or not labels.get("observed_behaviors")
            or any(b.get("rule_version") != intent.validator_version for b in labels["observed_behaviors"])
            or files["semantic_validation.json"].get("semantic_validation_version") != protocol["semantic_validation_version"]
            or files["execution_constraints.json"].get("constraint_validation_version") != protocol["execution_constraints_version"]):
        raise ValueError("inconsistent v3 semantic protocol across analysis artifacts")
    for artifact in (manifest, quality):
        if any(artifact.get(k) != v for k,v in processing_versions().items()):
            raise ValueError("inconsistent or unsupported v3 observation processing versions")
        if not isinstance(artifact.get("episode_quality_eligible"), bool):
            raise ValueError("v3 episode_quality_eligible must be boolean")
    versions = processing_versions()
    if any(labels.get("label_provenance", {}).get(k) != v for k, v in versions.items()):
        raise ValueError("inconsistent v3 label observation processing versions")
    for name in ("semantic_validation.json", "phase_windows.json", "execution_constraints.json",
                 "execution_metrics.json", "observation_processing.json"):
        if name in manifest.get("artifact_sha256", {}):
            artifact = files.get(name)
            if artifact is None:
                artifact = json.loads((root/name).read_text(encoding="utf-8"))
            if any(artifact.get(k) != v for k, v in versions.items()):
                raise ValueError(f"inconsistent v3 observation processing versions: {name}")
    if quality["episode_quality_eligible"] != manifest["episode_quality_eligible"]:
        raise ValueError("inconsistent episode_quality_eligible")
    if quality.get("mission_success") != labels.get("mission_success") or quality.get("semantic_consistency") != labels.get("semantic_consistency"):
        raise ValueError("inconsistent mission outcome across v3 artifacts")
    if manifest.get("mission_success") != labels.get("mission_success") or manifest.get("semantic_consistency") != labels.get("semantic_consistency") or manifest.get("intent") != intent.name:
        raise ValueError("inconsistent v3 manifest outcome/intent")
    expected = v3_eligibility(quality,labels)
    if any(type(artifact.get(k)) is not bool or artifact.get(k) != value
           for artifact in (quality,manifest) for k,value in expected.items()):
        raise ValueError("v3 eligibility contradicts evidence")
    intervals = quality.get("invalid_intervals")
    if not isinstance(intervals,dict) or set(intervals) != set(manifest.get("agent_ids",[])):
        raise ValueError("v3 invalid_intervals must cover every agent")
    for rows in intervals.values():
        if not isinstance(rows,list) or any(not isinstance(row,dict) or not finite_number(row.get("start_s"))
            or not finite_number(row.get("end_s")) or row["end_s"] < row["start_s"] or not isinstance(row.get("reason"),str)
            for row in rows):
            raise ValueError("invalid v3 invalid_intervals")
    for name in ("clock_models.json", "lifecycle_clock_models.json"):
        if name in manifest.get("artifact_sha256", {}):
            models=json.loads((root/name).read_text(encoding="utf-8"))
            if (set(models) != set(manifest["agent_ids"])
                    or any(any(model.get(k) != v for k, v in versions.items()) for model in models.values())):
                raise ValueError("inconsistent v3 clock model processing versions")
