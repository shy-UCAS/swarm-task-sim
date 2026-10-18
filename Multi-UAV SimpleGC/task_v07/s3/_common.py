"""I/O primitives shared by S3; never writes into an input run."""
import hashlib
import json
from pathlib import Path

from task_v07.expansion.contracts import P0ContractError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT.parents[1] / "SwarmData" / "v07_first_edition"
EXPORT_ROOT = DATA_ROOT.parent / "v07_first_edition_s3"
TEMPLATE_PATH = PROJECT_ROOT / "configs" / "s3" / "templates_v07_s3_r1.json"


class RunNotReady(ValueError):
    """Refuse incomplete input or an already existing export (CLI exit 3)."""


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dumps(value):
    # Python's JSON encoder uses float repr; sorting makes every record stable.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(dumps(value) + "\n")


def pointer(*parts):
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def resolve_pointer(document, path):
    if not path.startswith("/"):
        raise P0ContractError(f"Invalid JSON Pointer: {path}")
    value = document
    try:
        for part in path[1:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            value = value[int(part)] if isinstance(value, list) else value[part]
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise P0ContractError(f"Missing fact source: {path}") from exc
    return value


def inside(root, relative):
    root = Path(root).resolve()
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise P0ContractError(f"Unsafe relative path: {relative}")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise P0ContractError(f"Path escaped data root: {relative}")
    return resolved


def read_run(data_root, run_id):
    run = inside(data_root, run_id)
    if (not (run / "manifest.json").is_file()
            or not (run / "progress.json").is_file()
            or (run / "P0_STOP.json").exists()):
        raise RunNotReady(f"Run is not complete: {run_id}")
    progress = read_json(run / "progress.json")
    if (progress.get("completed") is None
            or progress.get("completed") != progress.get("total")
            or progress.get("active") != [] or progress.get("pending") != []):
        raise RunNotReady(f"Run is not complete: {run_id}")
    manifest = read_json(run / "manifest.json")
    if not isinstance(manifest.get("retained_episodes"), list):
        raise P0ContractError(f"Missing retained episode registry: {run_id}")
    return run, manifest


def verify_episode_manifest(root, expected):
    if sha256(Path(root) / "manifest.json") != expected:
        raise P0ContractError(f"Episode manifest SHA256 mismatch: {root}")
