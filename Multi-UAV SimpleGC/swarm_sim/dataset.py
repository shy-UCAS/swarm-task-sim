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


def build_dataset(run_paths, output, salt="simplegc-v02"):
    output = Path(output).resolve()
    # Validate all inputs before making an export; source runs are never re-evaluated silently.
    entries = []
    seen = set()
    policies = {}
    protocols = {}
    for path in run_paths:
        root = Path(path).resolve()
        pointer = json.loads((root / "analysis_latest.json").read_text(encoding="utf-8"))
        analysis = (root / pointer["directory"]).resolve()
        if analysis.parent != root:
            raise ValueError("analysis pointer must reference a direct child of the run")
        manifest_path = analysis / "manifest.json"
        if digest(manifest_path) != pointer["manifest_sha256"]:
            raise ValueError(f"analysis manifest changed: {analysis}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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
    write_json(output / "dataset_manifest.json", result)
    return result
