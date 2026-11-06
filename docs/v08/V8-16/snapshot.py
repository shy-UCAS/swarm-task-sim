"""V8-16 冻结/输入/基线快照（只读）。用法：python -B snapshot.py <out.json> [--baseline]
沿用 V8-15 snapshot.py 的五项（160 输入、模块全部文件、v07_* 目录统计、两冻结工作树、full_v14c 全部文件），并加指令第 1 节
要求的细粒度不变量：check_monitoring 函数体、solve_joint/Prepared 数值代码、monitoring_constraints、nominal_checks.revisit
的源码 SHA256（按 AST 精确取段），以及 V8-11 至 V8-15 旧预置测试文件 SHA256（已含在 modules 内，另列便于对照）。"""
import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = ROOT / "Simulation-v08"
PROJ = REPO / "Multi-UAV SimpleGC"
DATA = ROOT / "SwarmData"
BASE = ROOT / "_handoff" / "2026-11-04_V8-14_skeleton" / "out" / "full_v14c"
REF = REPO / "docs" / "v08" / "V8-14" / "v14c" / "snapshot_v14c_end.json"
FINE = [("v08/motion/optimize_checks.py", "check_monitoring"), ("v08/motion/optimize.py", "solve_joint"),
        ("v08/motion/optimize.py", "Prepared"), ("v08/motion/optimize.py", "prepare_problem"),
        ("v08/motion/intents/monitoring.py", "monitoring_constraints"), ("v08/motion/nominal_checks.py", "revisit"),
        ("v08/motion/nominal_checks.py", "screen_member")]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def ident(p):
    st = p.stat()
    return [sha(p), st.st_size, st.st_mtime_ns]


def fine(rel, name):
    src = (PROJ / rel).read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
            seg = ast.get_source_segment(src, node)
            return {"lines": [node.lineno, node.end_lineno], "sha256": hashlib.sha256(seg.encode("utf-8")).hexdigest()}
    return None


def main():
    out = Path(sys.argv[1])
    doc = {}
    ref = json.loads(REF.read_text(encoding="utf-8"))
    doc["inputs"] = {k: ident(DATA / k) for k in sorted(ref["inputs"])}
    doc["inputs_equal_v14c_end"] = doc["inputs"] == ref["inputs"]
    mods = {}
    for sub in ("configs", "v08", "tools/v08", "tests/v08", "scripts/v08", "task_v07"):
        for p in sorted((PROJ / sub).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                mods[p.relative_to(PROJ).as_posix()] = sha(p)
    doc["modules"] = mods
    doc["fine_invariants"] = {f"{r}::{n}": fine(r, n) for r, n in FINE}
    doc["old_preset_tests"] = {k: v for k, v in mods.items()
                               if k.startswith("tests/v08/V8-1") and "/test_preset_" in k and "/V8-16/" not in k}
    v07 = {}
    for d in sorted(DATA.glob("v07_*")):
        n = size = mt = 0
        for dp, _, fs in os.walk(d):
            for f in fs:
                st = os.stat(os.path.join(dp, f))
                n += 1
                size += st.st_size
                mt = max(mt, st.st_mtime_ns)
        v07[d.name] = [n, size, mt, d.stat().st_mtime_ns]
    doc["v07_dirs"] = v07
    fw = {}
    for w in ("Simulation-fe-prod-r3", "Simulation-fe-s3"):
        head = subprocess.run(["git", "-C", str(ROOT / w), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        st = subprocess.run(["git", "-C", str(ROOT / w), "status", "--porcelain"], capture_output=True, text=True).stdout
        fw[w] = {"head": head, "clean": st.strip() == ""}
    doc["frozen_worktrees"] = fw
    if "--baseline" in sys.argv:
        doc["baseline_root"] = str(BASE)
        doc["baseline"] = {p.relative_to(BASE).as_posix(): ident(p) for p in sorted(BASE.rglob("*")) if p.is_file()}
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"inputs={len(doc['inputs'])} equal_v14c_end={doc['inputs_equal_v14c_end']} modules={len(mods)} "
          f"fine={sum(v is not None for v in doc['fine_invariants'].values())}/{len(FINE)} "
          f"old_presets={len(doc['old_preset_tests'])} v07_dirs={len(v07)} frozen={fw} "
          f"baseline_files={len(doc.get('baseline', {}))}")


if __name__ == "__main__":
    main()
