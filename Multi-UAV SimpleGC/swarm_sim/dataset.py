"""Auditable export with deterministic, whole-family splits and retained failures."""

import hashlib
import json
import re
import shutil
from pathlib import Path

from .analysis import digest
from .recording import write_json
from .quality import policy_hash, resolve_policy
from .protocol import manifest_protocol, validate_artifact_protocol


def family_split(family_id, salt="simplegc-v02"):
    bucket = int(hashlib.sha256((salt + ":" + family_id).encode()).hexdigest()[:16], 16) % 100
    return "train" if bucket < 70 else ("validation" if bucket < 85 else "test")


def build_dataset(run_paths, output, salt="simplegc-v02", *, allow_mixed_control_modes=False,
                  analysis_selections=None):
    if not isinstance(allow_mixed_control_modes, bool):
        raise ValueError("allow_mixed_control_modes must be boolean")
    output = Path(output).resolve()
    run_paths = [Path(path).resolve() for path in run_paths]
    if analysis_selections is not None and not isinstance(analysis_selections, dict):
        raise ValueError("analysis_selections must be a run-path mapping")
    selections = {}
    for name, selection in (analysis_selections or {}).items():
        if not isinstance(name, str) or not name:
            raise ValueError("analysis selection requires a run path")
        selected_run = Path(name).resolve()
        if selected_run not in run_paths or selected_run in selections:
            raise ValueError("unknown or duplicate run in analysis_selections")
        if (not isinstance(selection, dict) or set(selection) != {"directory", "manifest_sha256"}
                or not isinstance(selection["directory"], str) or not selection["directory"]
                or not isinstance(selection["manifest_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", selection["manifest_sha256"])):
            raise ValueError("analysis selection requires a directory and SHA256 binding")
        selections[selected_run] = selection
    # Validate all inputs before making an export; source runs are never re-evaluated silently.
    entries = []
    seen = set()
    policies = {}
    protocols = {}
    control_modes = set()
    for path in run_paths:
        root = Path(path).resolve()
        explicit = root in selections
        pointer = selections[root] if explicit else json.loads((root / "analysis_latest.json").read_text(encoding="utf-8"))
        analysis = (Path(pointer["directory"]).resolve() if explicit else (root / pointer["directory"]).resolve())
        if not explicit and analysis.parent != root:
            raise ValueError("analysis pointer must reference a direct child of the run")
        if explicit and output.is_relative_to(analysis):
            raise ValueError("dataset output must be outside its selected analysis")
        manifest_path = analysis / "manifest.json"
        if digest(manifest_path) != pointer["manifest_sha256"]:
            raise ValueError(f"analysis manifest changed: {analysis}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if explicit and (not isinstance(manifest.get("run_directory"), str)
                         or Path(manifest["run_directory"]).resolve() != root):
            raise ValueError("explicit analysis is bound to a different source run")
        if explicit:
            if "metadata.json" not in manifest.get("source_sha256", {}):
                raise ValueError("explicit analysis requires hashed source metadata")
            source_metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
            if manifest.get("run_id") != source_metadata.get("run_id"):
                raise ValueError("explicit analysis run_id differs from source metadata")
        protocol = manifest_protocol(manifest)
        protocols[json.dumps(protocol, sort_keys=True)] = protocol
        if len(protocols) > 1:
            raise ValueError("incompatible semantic/eligibility protocols: export separate datasets")
        if "quality_policy" not in manifest or "quality_policy_sha256" not in manifest:
            raise ValueError(f"analysis has no quality policy; reanalyze legacy run: {root}")
        policy = resolve_policy(manifest["quality_policy"])
        fingerprint = policy_hash(policy)
        if fingerprint != manifest["quality_policy_sha256"]:
            raise ValueError("quality policy hash does not match policy contents")
        policies[fingerprint] = policy
        if len(policies) > 1:
            raise ValueError("mixed quality policies: reanalyze runs with one policy or export separate datasets")
        if manifest.get("strict_benchmark_eligible") and not manifest["benchmark_eligible"]:
            raise ValueError("strict eligibility must be a subset of benchmark eligibility")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", manifest["run_id"]):
            raise ValueError("invalid run_id in analysis manifest")
        if output.is_relative_to(root):
            raise ValueError("dataset output must be outside its source run directories")
        if manifest["run_id"] in seen:
            raise ValueError("duplicate run_id in dataset inputs")
        seen.add(manifest["run_id"])
        for name, expected in manifest["artifact_sha256"].items():
            candidate = (analysis / name).resolve()
            if candidate.parent != analysis or digest(candidate) != expected:
                raise ValueError(f"analysis artifact changed: {name}")
        validate_artifact_protocol(manifest, analysis)
        if protocol["task_kind"] == "mission_v3":
            control_modes.add(manifest["control_mode"])
            if len(control_modes) > 1 and not allow_mixed_control_modes:
                raise ValueError("mixed control_mode requires explicit allow_mixed_control_modes")
        for name, expected in manifest["source_sha256"].items():
            candidate = (root / name).resolve()
            if not candidate.is_relative_to(root) or digest(candidate) != expected:
                raise ValueError(f"run source changed since analysis: {name}")
        family = manifest.get("family_id")
        entries.append((analysis, dict(run_id=manifest["run_id"], scenario_id=manifest["scenario_id"],
            semantic_protocol=protocol, agent_ids=manifest.get("agent_ids"), source_analysis_directory=analysis.name,
            family_id=family, split=family_split(family, salt) if family else None,
            benchmark_eligible=bool(family) and manifest["benchmark_eligible"],
            strict_benchmark_eligible=bool(family) and manifest.get("strict_benchmark_eligible", False),
            quality_policy_sha256=fingerprint, clock_quality=manifest["clock_quality"],
            analysis_version=manifest["analysis_version"], simulator_version=manifest.get("simulator_version"),
            evaluation_context=manifest.get("evaluation_context"),
            run_status=manifest["run_status"], source_run=str(root),
            analysis_manifest_sha256=digest(manifest_path))))
        if protocol["task_kind"] == "mission_v3":
            entries[-1][1].update({key: manifest.get(key) for key in ("family_scheme", "control_mode", "episode_quality_eligible",
                                  "mission_success", "semantic_consistency", "intent")})
            if manifest.get("protocol_version") == "v0.6":
                entries[-1][1].update({key: manifest[key] for key in
                                      ("protocol_version", "flight_pattern", "component_versions")})
        if explicit:
            entries[-1][1].update(source_analysis_path=str(analysis),
                                  analysis_selection_mode="explicit_manifest_binding")
    if not entries:
        raise ValueError("provide at least one analyzed run")
    output.mkdir(parents=True, exist_ok=False)
    for analysis, entry in entries:
        relative = Path("episodes") / entry["run_id"]
        destination = output / relative
        destination.mkdir(parents=True)
        manifest = json.loads((analysis / "manifest.json").read_text(encoding="utf-8"))
        for filename in ["manifest.json", *manifest["artifact_sha256"]]:
            shutil.copy2(analysis / filename, destination / filename)
        entry["directory"] = relative.as_posix()
    fingerprint, policy = next(iter(policies.items()))
    result = dict(schema_version=2, quality_policy=policy, quality_policy_sha256=fingerprint,
        semantic_protocol=next(iter(protocols.values())), mixed_semantic_protocols=False,
        mixed_quality_policies=False, split_salt=salt, split_method="SHA256 of family_id; target proportions 70/15/15, not balanced on small sets",
        identity_policy="all derived variants/retries/windows must inherit the originating family_id before splitting",
        missing_family_policy="retained, unassigned, ineligible; never infer family from run_id",
        training_input="episodes/<run_id>/observations.csv only: ENU position/velocity and valid mask; group by t_s and agent_id",
        privileged_outputs="task, reference, truth, labels and metadata must not be fed as observation features",
        episodes=[entry for _, entry in entries],
        counts=dict(total=len(entries), eligible=sum(e["benchmark_eligible"] for _, e in entries),
                    strict_eligible=sum(e["strict_benchmark_eligible"] for _, e in entries),
                    failed_runs=sum(e["run_status"] != "completed" for _, e in entries)),
        limitation="no automatic task-family discovery, sliding windows, text generation or sensor simulation")
    if result["semantic_protocol"]["task_kind"] == "mission_v3":
        result.update(family_scheme="scene_content_v1", control_modes=sorted(control_modes),
                      allow_mixed_control_modes=allow_mixed_control_modes, mixed_control_modes=len(control_modes)>1)
        result["counts"].update(episode_quality_eligible=sum(e["episode_quality_eligible"] for _,e in entries),
                               mission_success=sum(e["mission_success"] is True for _,e in entries),
                               semantic_agree=sum(e["semantic_consistency"] == "agree" for _,e in entries))
    write_json(output / "dataset_manifest.json", result)
    return result
