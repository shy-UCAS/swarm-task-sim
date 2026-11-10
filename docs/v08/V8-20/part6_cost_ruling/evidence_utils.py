"""Read-only evidence helpers; no production geometry or acceptance changes."""
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
CODE = REPO / "Multi-UAV SimpleGC"
DOC = REPO / "docs/v08/V8-20"
TASK = BASE / "_handoff/2026-11-09_V8-20_area_search"
ROOT = TASK / "run"
sys.path.insert(0, str(CODE))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def dump(path, value, *, exclusive=False):
    path = Path(path)
    with path.open("x" if exclusive else "w", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=1, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def index(folder):
    return [{"path": str(p), "bytes": p.stat().st_size, "sha256": sha(p)}
            for p in sorted(Path(folder).rglob("*")) if p.is_file()]


def audit():
    spec = importlib.util.spec_from_file_location("v20_gate_audit", DOC / "run_old_intent_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    changes = module.audit(read(DOC / "manifest.json"))
    for name, fact in read(ROOT / "snapshot/part1_r1/inputs.json").items():
        p = Path(name)
        if sha(p) != fact["sha256"] or p.stat().st_mtime_ns != fact["mtime_ns"]:
            changes.append(name)
    for name, digest in read(DOC / "part3/final_audit.json")["supplemental_all_config_baseline_sha256"].items():
        if sha(name) != digest:
            changes.append(name)
    sources = {str(p.relative_to(CODE)): sha(p)
               for root in (CODE / "v08", CODE / "tools/v08") for p in root.rglob("*.py")}
    expected = read(ROOT / "part5_source_binding.json")["source_sha256"]
    if sources != expected:
        changes.append("source_binding_vs_part4_gate")
    return changes


def quantiles(values):
    import numpy as np
    values = [float(x) for x in values]
    if not values:
        return {"count": 0, "quantiles": None}
    return {"count": len(values), "quantiles": dict(zip(
        ("min", "q25", "median", "q75", "max"),
        map(float, np.quantile(values, [0., .25, .5, .75, 1.]))))}
