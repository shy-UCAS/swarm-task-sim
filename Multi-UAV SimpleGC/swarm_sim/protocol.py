"""Semantic protocol identity, independent of numerical quality-policy versions."""

import json
from pathlib import Path

SHARED_SEMANTIC_VERSION = "shared_coverage_v2"
SHARED_CONSTRAINT_VERSION = "execution_limits_v2"
SHARED_LABEL_SCHEMA_VERSION = 2

PROTOCOL_FIELDS = ("task_kind", "ontology_version", "label_schema_version", "semantic_validation_version",
                   "eligibility_protocol_version", "execution_constraints_version")


def semantic_protocol(scene):
    if scene.get("task_spec", {}).get("schema_version") == 2:
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
