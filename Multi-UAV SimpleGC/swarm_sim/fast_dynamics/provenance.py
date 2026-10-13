"""Content identity for local uncommitted executions; no Git mutation/process."""

import hashlib
from pathlib import Path


def source_snapshot():
    project = Path(__file__).resolve().parents[2]
    files = sorted((project / "swarm_sim").rglob("*.py"))
    files += sorted((project / "scripts").glob("*fast_dynamics*.py"))
    return {path.relative_to(project).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files}
