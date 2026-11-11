"""V8-21 六意图快批逐字节门禁（指令 2.4、4.6）：沿用 V8-20 run_old_intent_gate.py 的比较方式，登记六个显式意图与
V8-22 新监视路径；固定 20 键（orders 1..9,11 × draws 0,1），排除清单 []，失败合同也比较，合同外计时不比较。

用法（代码工作目录）：python -B ../docs/v08/V8-21/run_old_intent_gate.py <phase 2|4> <round> [intent ...]
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
CODE = REPO / "Multi-UAV SimpleGC"
RUN = BASE / "_handoff/2026-11-10_V8-21_detour/run"
DEVSET = REPO / "docs/v08/V8-03/devset_v08.json"
DATA = BASE / "SwarmData"
CACHE = RUN / "cache"
PY = Path(r"C:\Users\shy\anaconda3\envs\llm\python.exe")
OLD = ("monitoring", "transit", "intrusion", "feint", "close_observation", "area_search")
QUICK = [f"o{o:02d}_d{d}" for o in (*range(1, 10), 11) for d in (0, 1)]
BASELINES = {
    "monitoring": BASE / "_handoff/2026-11-10_V8-22_monitoring_entry/run/full",
    "transit": BASE / "_handoff/2026-11-05_V8-16_transit/run/out/full_transit_r2",
    "intrusion": BASE / "_handoff/2026-11-06_V8-17_intrusion/run/out/full/full_r1",
    "feint": BASE / "_handoff/2026-11-06_V8-18_feint/run/out/full_lazy_r1",
    "close_observation": BASE / "_handoff/2026-11-08_V8-19_close_observation/run/out/full_r1",
    "area_search": BASE / "_handoff/2026-11-09_V8-20_area_search/run/full/area_cost_ruling_r1",
}
SPECS = {
    "monitoring": ("tools/v08/run_separation_v15.py", ["--mode", "production-quick"], "run"),
    "transit": ("tools/v08/run_transit_v16.py", ["--stage", "quick"], ""),
    "intrusion": ("tools/v08/run_intrusion_v17.py", ["--stage", "quick"], ""),
    "feint": ("tools/v08/run_feint_v18.py", ["--stage", "quick"], ""),
    "close_observation": ("tools/v08/run_close_observation_v19.py", ["--stage", "quick"], ""),
    "area_search": ("tools/v08/run_area_search_v20.py", ["--stage", "quick"], ""),
}


def dump(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")
        f.flush()
        os.fsync(f.fileno())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def area_prewarm():
    """V8-22 同法：复制 V8-20 正式预建登记，只把 cache_root 换成本任务缓存副本（缓存本身由 V8-22 副本复制而来）。"""
    dst = RUN / "inputs" / "area_prewarm.json"
    if not dst.exists():
        src = BASE / "_handoff/2026-11-10_V8-22_monitoring_entry/run/inputs/area_prewarm.json"
        doc = json.loads(src.read_text(encoding="utf-8"))
        doc["cache_root"] = str(CACHE.resolve())
        dump(dst, doc)
        dump(RUN / "inputs" / "area_prewarm_copy.json", {"source": str(src), "source_sha256": sha(src),
                                                          "change": "cache_root path only", "destination": str(dst)})
    return dst


def compare(left, right):
    a = {p.relative_to(left).as_posix(): p for p in left.rglob("*") if p.is_file()} if left.is_dir() else {}
    b = {p.relative_to(right).as_posix(): p for p in right.rglob("*") if p.is_file()} if right.is_dir() else {}
    diff = sorted(n for n in set(a) & set(b) if a[n].read_bytes() != b[n].read_bytes())
    return {"files": len(a), "file_sets_equal": set(a) == set(b), "only_baseline": sorted(set(a) - set(b)),
            "only_actual": sorted(set(b) - set(a)), "differing": diff,
            "equal": bool(a) and set(a) == set(b) and not diff}


def run_one(intent, phase, rnd):
    out = RUN / f"gate_p{phase}" / intent / rnd
    diag = RUN / f"gate_p{phase}" / intent / f"diagnostics_{rnd}"
    assert not out.exists() and not diag.exists()
    diag.mkdir(parents=True)
    script, stage, suffix = SPECS[intent]
    base = BASELINES[intent]
    argv = [str(PY), "-B", script, *stage, "--workers", "24", "--devset", str(DEVSET), "--data-root", str(DATA),
            "--cache", str(CACHE), "--out", str(out)]
    if intent == "monitoring":
        argv += ["--baseline", str(base)]
    if intent == "area_search":
        argv += ["--prewarm-from", str(area_prewarm())]
    env = dict(os.environ)
    env.update(dict.fromkeys(("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
                              "PYTHONDONTWRITEBYTECODE"), "1"))
    src = {str(p.relative_to(CODE)): sha(p) for root in (CODE / "v08", CODE / "tools/v08") for p in root.rglob("*.py")}
    begin = time.perf_counter()
    rec = {"intent": intent, "phase": phase, "round": rnd, "workers": 24, "command": argv, "start_epoch_s": time.time(),
           "source_sha256": src, "baseline": str(base), "repeat": str(out / suffix), "exclusions": [], "status": "running"}
    dump(diag / "watchdog.json", rec)
    print(f"START gate_p{phase} {intent} workers=24", flush=True)
    with (diag / "stdout.log").open("w", encoding="utf-8") as so, (diag / "stderr.log").open("w", encoding="utf-8") as se:
        proc = subprocess.Popen(argv, cwd=CODE, env=env, stdout=so, stderr=se)
        proc.wait()
    rec.update(exit_code=proc.returncode, wall_s=time.perf_counter() - begin, end_epoch_s=time.time(), status="finished")
    dump(diag / "watchdog.json", rec)
    repeat = out / suffix if suffix else out
    comps = []
    for cid in QUICK:
        c = compare(base / "contracts" / cid, repeat / "contracts" / cid)
        comps.append({"contract_id": cid, **c})
    actual = sorted(p.name for p in (repeat / "contracts").iterdir() if p.is_dir()) if (repeat / "contracts").is_dir() else []
    res = {"intent": intent, "phase": phase, "round": rnd, "baseline": str(base), "actual": str(repeat),
           "exit_code": proc.returncode, "wall_s": rec["wall_s"], "keys": QUICK, "actual_contract_ids": actual,
           "actual_ids_equal_quick": actual == QUICK, "comparisons": comps,
           "equal_count": sum(c["equal"] for c in comps), "files": sum(c["files"] for c in comps),
           "differing_files": sum(len(c["differing"]) + len(c["only_baseline"]) + len(c["only_actual"]) for c in comps),
           "exclusions": []}
    res["passed"] = bool(res["equal_count"] == len(QUICK) and res["actual_ids_equal_quick"])
    dump(RUN / f"gate_p{phase}" / intent / f"gate_{rnd}.json", res)
    print(f"END gate_p{phase} {intent}: {res['equal_count']}/20 equal files={res['files']} "
          f"diff={res['differing_files']} exit={proc.returncode} wall={rec['wall_s']:.1f}s", flush=True)
    return res


def main():
    phase, rnd = int(sys.argv[1]), sys.argv[2]
    assert phase in (2, 4) and rnd.isalnum()
    intents = sys.argv[3:] or list(OLD)
    rows = [run_one(i, phase, rnd) for i in intents]
    summary = {"phase": phase, "round": rnd, "intents": intents, "passed": all(r["passed"] for r in rows),
               "equal": sum(r["equal_count"] for r in rows), "total": 20 * len(rows),
               "files": sum(r["files"] for r in rows), "differing_files": sum(r["differing_files"] for r in rows),
               "exclusions": [], "rows": [{k: r[k] for k in ("intent", "equal_count", "files", "differing_files",
                                                            "exit_code", "wall_s", "actual", "baseline", "passed")}
                                          for r in rows]}
    dump(RUN / f"gate_p{phase}" / f"summary_{rnd}.json", summary)
    print(json.dumps({k: summary[k] for k in ("passed", "equal", "total", "files", "differing_files")}), flush=True)
    return 0 if summary["passed"] else 4


if __name__ == "__main__":
    sys.exit(main())
