"""Manifest-bound, separate Chinese description export for v0.5 datasets.

This module never modifies the source dataset.  Eligibility is a filter, not
an outcome label: eligible failures receive descriptions when both semantic
channels agree.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .episode_loader import load_episode
from .generation import file_hash
from .protocol import V05_SEMANTIC_VERSION, V05_R12B_SEMANTIC_VERSION
from .recording import write_json


DESCRIPTION_VERSION = "language_zh_v0"
TEMPLATES_VERSION = "templates_zh_v0"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _episode_path(root: Path, entry: dict) -> Path:
    relative = entry.get("directory")
    if not isinstance(relative, str):
        raise ValueError("dataset episode directory is missing")
    episode = (root / relative).resolve()
    if episode.parent != root / "episodes" or not episode.is_dir():
        raise ValueError("dataset episode must be a direct child of episodes/")
    return episode


def _verify_existing_output(output: Path, input_hash: str) -> None:
    if not output.exists():
        return
    old = output / "language_manifest.json"
    if old.is_file() and _read_json(old).get("dataset_manifest_sha256") != input_hash:
        raise ValueError("dataset manifest changed since existing description export")
    raise ValueError("description output already exists; choose a new directory")


def describe_dataset(dataset_directory, output=None, templates="zh_v0") -> dict:
    """Describe one frozen dataset, generating 3 train and 1 test texts per eligible episode.

    The template split and family split are independent.  This function only
    records both dimensions; consumers enforce train-family x train-template.
    """
    if templates != "zh_v0":
        raise ValueError("only zh_v0 templates are supported")
    root = Path(dataset_directory).resolve()
    manifest_path = root / "dataset_manifest.json"
    if not manifest_path.is_file():
        raise ValueError("dataset_manifest.json is required")
    manifest_hash = file_hash(manifest_path)
    manifest = _read_json(manifest_path)
    semantic_version = manifest.get("semantic_protocol", {}).get("semantic_validation_version")
    if semantic_version not in (V05_SEMANTIC_VERSION, V05_R12B_SEMANTIC_VERSION):
        raise ValueError("zh_v0 descriptions require the v0.5 multi-intent semantic protocol")
    entries = manifest.get("episodes")
    if not isinstance(entries, list) or not entries:
        raise ValueError("dataset has no episodes")
    output = Path(output).resolve() if output is not None else root.with_name(root.name + "_language_zh_v0")
    if output == root or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("description output must be a separate sibling directory")
    _verify_existing_output(output, manifest_hash)

    # The imports are delayed so a dataset may be inspected without loading
    # the language modules.  Every source episode is checked before output.
    from .observer_facts_v0 import extract_observer_facts
    from .language_templates_v0 import generate_descriptions, validate_description

    all_descriptions, skipped, facts_by_episode = [], [], {}
    seen_ids = set()
    for entry in entries:
        episode = _episode_path(root, entry)
        run_id = entry.get("run_id")
        if not isinstance(run_id, str) or not run_id or run_id in seen_ids or episode.name != run_id:
            raise ValueError("duplicate or invalid dataset episode id")
        seen_ids.add(run_id)
        loaded = load_episode(episode, verify_hashes=True)
        metadata = loaded["metadata"]
        if (metadata.get("semantic_validation_version") != semantic_version
                or metadata.get("episode_quality_eligible") is not entry.get("episode_quality_eligible")
                or metadata.get("semantic_consistency") != entry.get("semantic_consistency")):
            raise ValueError("dataset episode eligibility or protocol disagrees with manifest")
        reason = None
        if entry.get("episode_quality_eligible") is not True:
            reason = "episode_quality_ineligible"
        elif entry.get("semantic_consistency") != "agree":
            reason = "semantic_channels_disagree_or_unknown"
        if reason:
            skipped.append(dict(episode_id=run_id, episode_split=entry.get("split"), reason=reason))
            continue
        facts = extract_observer_facts(episode, manifest_hash)
        if facts.get("facts_version") != "observer_facts_v0":
            raise ValueError("unsupported observer facts version")
        facts_by_episode[run_id] = facts
        seed = int(hashlib.sha256((manifest_hash + ":" + run_id + ":" + TEMPLATES_VERSION).encode("utf-8")).hexdigest()[:16], 16)
        descriptions = generate_descriptions(facts, run_id, entry.get("split"), seed)
        if len(descriptions) != 4 or sum(d.get("template_partition") == "train" for d in descriptions) != 3 or sum(d.get("template_partition") == "test" for d in descriptions) != 1:
            raise ValueError("template generator did not produce 3 train and 1 test descriptions")
        for description in descriptions:
            valid, errors = validate_description(description, facts)
            if not valid:
                raise ValueError(f"description consistency failed for {run_id}: {errors}")
            if description.get("episode_id") != run_id or description.get("episode_split") != entry.get("split"):
                raise ValueError("description identity or episode split mismatch")
            all_descriptions.append(description)

    if len(all_descriptions) != 4 * len(facts_by_episode) or len(facts_by_episode) + len(skipped) != len(entries):
        raise ValueError("description completeness check failed")
    if file_hash(manifest_path) != manifest_hash:
        raise ValueError("dataset manifest changed during description export")
    output.mkdir(parents=True, exist_ok=False)
    facts_root = output / "facts"
    facts_root.mkdir()
    hashes = {}
    for run_id, facts in facts_by_episode.items():
        path = facts_root / (run_id + ".json")
        write_json(path, facts)
        hashes[path.relative_to(output).as_posix()] = file_hash(path)
    description_path = output / "descriptions.json"
    write_json(description_path, dict(schema_version=1, language_version=DESCRIPTION_VERSION,
        templates_version=TEMPLATES_VERSION, dataset_manifest_sha256=manifest_hash,
        descriptions=all_descriptions, skipped=skipped))
    hashes[description_path.name] = file_hash(description_path)
    result = dict(schema_version=1, language_version=DESCRIPTION_VERSION,
        templates_version=TEMPLATES_VERSION, facts_version="observer_facts_v0",
        semantic_validation_version=semantic_version,
        dataset_manifest_sha256=manifest_hash, dataset_directory=str(root),
        input_episodes=len(entries), eligible_agree_episodes=len(facts_by_episode),
        skipped_episodes=len(skipped), descriptions=len(all_descriptions),
        artifact_sha256=hashes)
    write_json(output / "language_manifest.json", result)
    return result
