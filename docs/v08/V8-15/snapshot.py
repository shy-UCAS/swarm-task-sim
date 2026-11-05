"""V8-15 第 1 部分：冻结/输入/基线快照（只读）。用法：python -B snapshot.py <out.json> [--baseline]
- inputs：V8-14 快照登记的 160 个开发集输入（SwarmData 相对路径）SHA256/大小/mtime_ns；
- modules：Multi-UAV SimpleGC 下 configs/、v08/、tools/v08/、tests/v08/ 全部文件 SHA256；
- v07_dirs：SwarmData\\v07_* 每目录文件数、总字节、最大 mtime_ns（不读内容）；
- frozen_worktrees：两个冻结工作树 HEAD 与是否干净；
- baseline（--baseline）：full_v14c 全部文件 SHA256/大小/mtime_ns（只读）。
"""
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


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def ident(p):
    st = p.stat()
    return [sha(p), st.st_size, st.st_mtime_ns]


def main():
    out = Path(sys.argv[1])
    doc = {}
    ref = json.loads(REF.read_text(encoding="utf-8"))
    doc["inputs"] = {k: ident(DATA / k) for k in sorted(ref["inputs"])}
    doc["inputs_equal_v14c_end"] = doc["inputs"] == ref["inputs"]
    mods = {}
    for sub in ("configs", "v08", "tools/v08", "tests/v08"):
        for p in sorted((PROJ / sub).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                mods[p.relative_to(PROJ).as_posix()] = sha(p)
    doc["modules"] = mods
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
          f"v07_dirs={len(v07)} frozen={fw} baseline_files={len(doc.get('baseline', {}))}")


if __name__ == "__main__":
    main()
