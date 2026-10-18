"""Input-only loading stays separate from privileged language targets."""
import json
from pathlib import Path

from task_v07.io import INPUT_KEYS, load_episode
from ._common import P0ContractError, inside, read_json, verify_episode_manifest
from .normalize import normalized_view


def load_index(export_dir):
    with (Path(export_dir) / "episodes.jsonl").open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def load_inputs(row, data_root, view="normalized"):
    root = inside(data_root, row["path"])
    verify_episode_manifest(root, row["episode_manifest_sha256"])
    try:
        raw = load_episode(root)
    except (ValueError, KeyError, OSError) as exc:
        raise P0ContractError(f"Original episode loader rejected {row['episode_key']}: {exc}") from exc
    if set(raw) != INPUT_KEYS:
        raise P0ContractError("Raw input whitelist violation")
    if view == "raw":
        result = raw
    elif view == "normalized":
        result = normalized_view(raw, row["anchors"])
    else:
        raise ValueError("view must be raw or normalized")
    if set(result) != INPUT_KEYS:
        raise P0ContractError("Normalized input whitelist violation")
    return result


def load_targets(row, export_dir, template_group, variant):
    matches = []
    with (Path(export_dir) / "descriptions.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if (record["episode_key"] == row["episode_key"]
                    and record["template_group"] == template_group and record["variant"] == variant):
                matches.append(record)
    if len(matches) != 1:
        raise P0ContractError("Target selection must identify exactly one description")
    record = matches[0]
    if record["split"] != row["split"]:
        raise P0ContractError("Target/index split differs")
    return {"text": record["text"], "slots": row["slots"], "intent": row["intent"],
            "family_id": row["family_id"], "split": row["split"]}
