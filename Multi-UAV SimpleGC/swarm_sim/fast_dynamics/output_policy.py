"""Output-location policy for the fast dynamics entry points.

Samples, datasets, raw logs, benchmark results and failure evidence belong outside
the repository, inside a fresh attempt directory under one selected external output
root. This module resolves that root and refuses, before any artefact is created:

* a root inside the repository, or one that resolves into it through a link;
* an output target inside the repository, outside the selected root, already
  existing, or reaching its position through a junction / symlink escape;
* an attempt prefix (``--run-id``) carrying path fragments that would escape the root.

No machine absolute path is hardcoded: the default root is a sibling
``SwarmData/fast_dynamics`` directory next to the repository root, and
``FAST_DYNAMICS_OUTPUT_ROOT`` overrides it for other layouts. The generic library
APIs (``write_episode``, ``build_dataset``, ...) keep their previous permissive
contract; only the entry points apply this policy.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

ENV_VAR = "FAST_DYNAMICS_OUTPUT_ROOT"
DEFAULT_PARENT = "SwarmData"
DEFAULT_LEAF = "fast_dynamics"
_RESERVED_CHARS = ("/", "\\", ":", "*", "?", '"', "<", ">", "|")
_RESERVED_NAMES = {"con", "prn", "aux", "nul",
                   *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class OutputPolicyError(ValueError):
    """A requested output location violates the external-output policy."""


def project_root() -> Path:
    """The project directory that contains ``swarm_sim`` and ``scripts``."""
    return Path(__file__).resolve().parents[2]


def repository_root() -> Path:
    """The Git repository root: the project's parent when it holds ``.git``."""
    project = project_root()
    parent = project.parent
    if (parent / ".git").exists():
        return parent
    return project


def default_output_root() -> Path:
    """Portable default: a ``SwarmData/fast_dynamics`` directory **beside** the repository root.

    The repository root itself is ``Simulation-dev``; the evidence root must be its
    sibling under the same parent directory, never a subdirectory of the repository.
    """
    return repository_root().parent / DEFAULT_PARENT / DEFAULT_LEAF


def _resolved(path) -> Path:
    return Path(os.path.realpath(str(path)))


def is_inside_repository(path) -> bool:
    """True when the resolved path lies inside the repository (links followed)."""
    return is_within(_resolved(path), _resolved(repository_root()))


def is_within(candidate, parent) -> bool:
    """True when the resolved candidate lies at or under the resolved parent."""
    return _within(_resolved(candidate), _resolved(parent))


def _within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False


def _nearest_existing(path: Path) -> Path:
    ancestor = path
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    return ancestor


def assert_usable_root(root, *, source: str = "output root") -> Path:
    """Validate the selected root: outside the repository, a directory, no link escape."""
    resolved = _resolved(root)
    if is_within(resolved, _resolved(repository_root())):
        raise OutputPolicyError(
            f"{source} must stay outside the repository: {resolved}")
    if resolved.exists() and not resolved.is_dir():
        raise OutputPolicyError(f"{source} is not a directory: {resolved}")
    if is_within(_nearest_existing(resolved), _resolved(repository_root())):
        raise OutputPolicyError(
            f"{source} resolves through a link into the repository: {resolved}")
    return resolved


def resolve_output_root(explicit=None, env=None) -> dict:
    """Resolve the effective external output root: explicit argument > env var > default.

    An unusable root (inside the repository, a file, or link-escaped into it) raises
    :class:`OutputPolicyError`, so entry points refuse the configuration before any
    directory or file is created instead of silently writing somewhere unexpected.
    """
    environ = os.environ if env is None else env
    if explicit is not None:
        root, source = Path(explicit).expanduser(), "argument --output-root"
    elif environ.get(ENV_VAR):
        root, source = Path(environ[ENV_VAR]).expanduser(), f"environment {ENV_VAR}"
    else:
        root, source = default_output_root(), "default sibling SwarmData/fast_dynamics"
    resolved = assert_usable_root(root, source=source)
    return {"root": resolved, "source": source, "exists": resolved.exists(),
            "repository_root": repository_root(), "environment_variable": ENV_VAR,
            "inside_repository": False, "default_root": default_output_root()}


def assert_new_external_path(path, *, kind="attempt", allow_existing=False) -> Path:
    """Repository-outside check only, for callers that hold no selected root.

    ``os.path.realpath`` resolves symlinks and junctions in every existing path
    component, so a resolved-path comparison already covers link escapes.
    """
    resolved = _resolved(path)
    if is_inside_repository(resolved):
        raise OutputPolicyError(f"{kind} path must stay outside the repository: {resolved}")
    if not allow_existing and resolved.exists():
        raise OutputPolicyError(f"{kind} path already exists; choose a new {kind}: {resolved}")
    return resolved


def assert_new_attempt_path(path, root, *, kind="attempt", allow_existing=False) -> Path:
    """Validate a fresh target against the selected root.

    Rejects, in order: an unusable root (inside the repository or link-escaped into
    it); a target inside the repository; a target outside ``root`` (including one
    that only escapes through ``..`` or a junction); and an existing target. All
    comparisons use resolved paths, so the selected root does not have to exist yet.
    """
    resolved_root = assert_usable_root(root)
    resolved = _resolved(path)
    if is_inside_repository(resolved):
        raise OutputPolicyError(f"{kind} path must stay outside the repository: {resolved}")
    if not _within(resolved, resolved_root):
        raise OutputPolicyError(
            f"{kind} path must stay under the selected output root {resolved_root}: {resolved}")
    if not allow_existing and resolved.exists():
        raise OutputPolicyError(f"{kind} path already exists; choose a new {kind}: {resolved}")
    return resolved


def assert_created_within(path, root) -> Path:
    """Re-check a path after creation: a link could still have redirected it."""
    resolved = _resolved(path)
    resolved_root = assert_usable_root(root)
    if is_inside_repository(resolved):
        raise OutputPolicyError(f"created output path resolved inside the repository: {resolved}")
    if not _within(resolved, resolved_root):
        raise OutputPolicyError(
            f"created output path resolved outside the selected output root {resolved_root}: {resolved}")
    return resolved


def sanitize_component(value, *, kind="attempt prefix") -> str:
    """Reject attempt prefixes that carry path fragments or unsafe characters."""
    text = str(value)
    if not text:
        raise OutputPolicyError(f"{kind} must not be empty")
    if text != text.strip():
        raise OutputPolicyError(f"{kind} must not have leading or trailing whitespace: {text!r}")
    if text in (".", ".."):
        raise OutputPolicyError(f"{kind} must not be a path fragment: {text!r}")
    if any(character in text for character in _RESERVED_CHARS):
        raise OutputPolicyError(
            f"{kind} must not contain path separators, drive letters or reserved characters: {text!r}")
    if text.startswith(".") or text.endswith("."):
        raise OutputPolicyError(f"{kind} must not start or end with a dot: {text!r}")
    if text.split(".")[0].lower() in _RESERVED_NAMES:
        raise OutputPolicyError(f"{kind} must not be a reserved device name: {text!r}")
    return text


def timestamped_name(prefix: str, *, now=None) -> str:
    """Fresh attempt name: UTC timestamp plus a sanitized caller prefix."""
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{sanitize_component(prefix)}"


def validate_run_id(value) -> str:
    """Validate a CLI run ID before any path or simulation work.

    Match the existing write_episode/dataset ID contract while retaining Windows
    filename checks. This is distinct from generic prefixes such as benchmark JSON
    filenames, which legitimately contain dots.
    """
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise OutputPolicyError("run-id must contain 1-100 ASCII letters, digits, underscores or hyphens")
    return sanitize_component(value, kind="run-id")


def new_attempt_path(output_root, prefix) -> Path:
    """A new attempt directory under ``output_root``; existence is checked by the caller."""
    return _resolved(output_root) / timestamped_name(prefix)
