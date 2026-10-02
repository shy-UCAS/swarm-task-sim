"""Load cooperative FCU observations without privileged feature leakage."""

import csv
import json
import math
from pathlib import Path

from .generation import checked_path, file_hash
from .protocol import PROTOCOL_FIELDS, manifest_protocol, supported_protocols, validate_artifact_protocol
from .quality import policy_hash, resolve_policy

FEATURE_COLUMNS = ("east_m", "north_m", "up_m", "ve_m_s", "vn_m_s", "vu_m_s")


def load_episode(path, agent_ids=None, verify_hashes=True):
    """Return unnormalized nested lists x[T,N,6], mask[T,N], time, targets and metadata.

    Missing agent/time rows are zero-filled with mask=false. Unknown identities,
    duplicate rows, decreasing time within an agent, and malformed numbers fail.
    Invalid rows may contain blanks; supplied numeric values must still be finite.
    """
    root = Path(path).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    protocol = manifest_protocol(manifest)
    if tuple(protocol[k] for k in PROTOCOL_FIELDS) not in supported_protocols():
        raise ValueError("unsupported semantic protocol in episode")
    if ("quality_policy" not in manifest or "quality_policy_sha256" not in manifest
            or policy_hash(resolve_policy(manifest["quality_policy"])) != manifest["quality_policy_sha256"]):
        raise ValueError("missing or inconsistent episode quality policy")
    if verify_hashes:
        if "observations.csv" not in manifest.get("artifact_sha256", {}):
            raise ValueError("observations.csv is not covered by the episode manifest")
        for name, expected in manifest["artifact_sha256"].items():
            if file_hash(checked_path(root, name)) != expected:
                raise ValueError(f"episode artifact changed: {name}")
    validate_artifact_protocol(manifest, root)
    entry = {}
    dataset_file = root.parent.parent / "dataset_manifest.json"
    if dataset_file.is_file():
        dataset = json.loads(dataset_file.read_text(encoding="utf-8"))
        matches = [e for e in dataset["episodes"]
                   if checked_path(dataset_file.parent, e["directory"]) == root]
        if len(matches) != 1:
            raise ValueError("episode is absent or duplicated in dataset manifest")
        entry = matches[0]
        if (entry.get("semantic_protocol", protocol) != protocol
                or dataset.get("semantic_protocol", protocol) != protocol):
            raise ValueError("dataset and episode semantic protocols disagree")
        fingerprint = manifest["quality_policy_sha256"]
        if (entry.get("quality_policy_sha256", fingerprint) != fingerprint
                or dataset.get("quality_policy_sha256", fingerprint) != fingerprint):
            raise ValueError("dataset and episode quality policies disagree")
        if verify_hashes and file_hash(root / "manifest.json") != entry["analysis_manifest_sha256"]:
            raise ValueError("episode manifest differs from frozen dataset selection")
        if entry.get("family_id") != manifest.get("family_id"):
            raise ValueError("dataset and episode family identity disagree")
        if protocol["task_kind"] == "mission_v3":
            v3_keys = ("control_mode", "family_scheme", "episode_quality_eligible", "intent", "mission_success",
                       "semantic_consistency", "run_status", "clock_quality", "agent_ids",
                       "benchmark_eligible", "strict_benchmark_eligible")
            if any(type(entry.get(k)) is not type(manifest.get(k)) or entry.get(k) != manifest.get(k) for k in v3_keys):
                raise ValueError("dataset and v3 episode metadata disagree")
            modes = dataset.get("control_modes", [])
            if manifest["control_mode"] not in modes or (len(modes)>1 and dataset.get("allow_mixed_control_modes") is not True):
                raise ValueError("dataset mixes control_mode without explicit permission")
    expected = agent_ids if agent_ids is not None else manifest.get("agent_ids")
    if expected is None and (root / "task.json").is_file():
        task = json.loads((root / "task.json").read_text(encoding="utf-8"))
        if task:
            vehicles = task.get("scenario", task).get("vehicles", [])
            expected = [v["id"] for v in vehicles]
    if not isinstance(expected, (list, tuple)) or not expected or any(not isinstance(v, str) or not v for v in expected):
        raise ValueError("expected agent identities are required in manifest/task or agent_ids")
    if len(set(expected)) != len(expected):
        raise ValueError("duplicate expected agent identities")
    expected = sorted(expected)
    samples, previous, times = {}, {}, set()
    with (root / "observations.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames or []
        if len(columns) != len(set(columns)) or not set(("t_s", "agent_id", "valid", *FEATURE_COLUMNS)).issubset(columns):
            raise ValueError("missing or duplicate observation feature columns")
        for row_number, row in enumerate(reader, 2):
            agent = row["agent_id"]
            if agent not in expected:
                raise ValueError(f"unknown agent on observation row {row_number}: {agent}")
            try:
                stamp = float(row["t_s"])
            except (ValueError, TypeError) as exc:
                raise ValueError(f"invalid observation time on row {row_number}") from exc
            if not math.isfinite(stamp) or stamp < 0:
                raise ValueError(f"invalid observation time on row {row_number}")
            if (stamp, agent) in samples:
                raise ValueError(f"duplicate observation (time, agent) on row {row_number}")
            if agent in previous and stamp < previous[agent]:
                raise ValueError(f"nonmonotonic observation time for {agent}")
            if row["valid"] not in ("0", "1"):
                raise ValueError(f"invalid observation mask on row {row_number}")
            valid = row["valid"] == "1"
            values = []
            for column in FEATURE_COLUMNS:
                raw = row[column]
                if raw in (None, "") and not valid:
                    values.append(0.0)
                    continue
                try:
                    value = float(raw)
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"invalid {column} on observation row {row_number}") from exc
                if not math.isfinite(value):
                    raise ValueError(f"nonfinite {column} on observation row {row_number}")
                values.append(value)
            samples[stamp, agent] = (values if valid else [0.0] * 6, valid)
            previous[agent] = stamp
            times.add(stamp)
    stamps = sorted(times)
    x, mask = [], []
    for stamp in stamps:
        frame = [samples.get((stamp, agent), ([0.0] * 6, False)) for agent in expected]
        x.append([values[:] for values, _ in frame])
        mask.append([valid for _, valid in frame])
    labels = json.loads((root / "labels.json").read_text(encoding="utf-8")) if (root / "labels.json").is_file() else {}
    metadata = {key: manifest.get(key) for key in ("run_id", "family_id", "analysis_version", "task_kind",
        "ontology_version", "label_schema_version", "semantic_validation_version", "eligibility_protocol_version",
        "quality_policy_sha256", "benchmark_eligible", "strict_benchmark_eligible", "evaluation_context")}
    metadata.update(split=entry.get("split"), feature_columns=list(FEATURE_COLUMNS), normalized=False,
                    missing_row_policy="zero-filled with false mask", source_directory=str(root))
    metadata.update(protocol)
    if protocol["task_kind"] == "mission_v3":
        from .observation_processing import processing_versions
        metadata.update({key: manifest.get(key) for key in ("family_scheme", "control_mode", "episode_quality_eligible",
                        "mission_success", "semantic_consistency", *processing_versions())})
        metadata["invalid_intervals"] = json.loads((root/"quality.json").read_text(encoding="utf-8")).get("invalid_intervals", {})
    return dict(x=x, mask=mask, t_s=stamps, agent_ids=expected, targets=labels, metadata=metadata)
