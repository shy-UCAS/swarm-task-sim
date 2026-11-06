"""V8-16 第 1 部分：manifest.json（只读）。完整 commit、开发集与输入散列、配置散列、源接口 blob、环境、
已有基线目录与散列、快批 20 / 全量 200 / 多样性 10 族×10 branch / 复跑 5 键。名单算法沿用现有运行器。
用法：python -B make_manifest.py <out.json>"""
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = ROOT / "Simulation-v08"
PROJ = REPO / "Multi-UAV SimpleGC"
sys.path.insert(0, str(PROJ))
DEVSET = REPO / "docs" / "v08" / "V8-03" / "devset_v08.json"
DATA = ROOT / "SwarmData"
V14 = ROOT / "_handoff" / "2026-11-04_V8-14_skeleton" / "out"
FULL = V14 / "full_v14c"
SKEL = V14 / "skeleton_v14b"
QUICK15 = REPO / "docs" / "v08" / "V8-15" / "part7" / "quick_selection.json"
RUN = ROOT / "_handoff" / "2026-11-05_V8-16_transit" / "run"
BLOBS = """v08/contract/monitoring.py v08/sampler/common.py v08/motion/plan.py v08/motion/intents/monitoring.py
v08/motion/formation.py v08/motion/skeleton.py v08/scene/exact.py v08/scene/context.py v08/motion/monitoring_band.py
v08/motion/nominal_checks.py v08/motion/optimize.py v08/motion/optimize_checks.py v08/runner/joint_monitoring.py
v08/criteria/segment.py v08/criteria/validity.py tools/v08/v15_artifacts.py v08/sim/tracking_batch.py v08/sim/stitch.py
v08/motion/connect.py v08/motion/speed.py v08/motion/nominal.py v08/runner/skeleton_monitoring.py
v08/runner/joint_report.py v08/scene/field.py configs/v08/criteria_segment.json configs/v08/joint_opt.json
configs/v08/monitoring.json v08/runner/runtime_defaults.py v08/scene/visibility.py""".split()


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*a):
    return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True, check=True).stdout.strip()


def tree_digest(root):
    h = hashlib.sha256()
    n = 0
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode() + b"\0" + sha(p).encode() + b"\n")
            n += 1
    return {"path": str(root), "files": n, "tree_sha256": h.hexdigest()}


def main():
    import numpy, scipy, shapely
    from v08.runner.monitoring import load_entries, select_diversity_families
    from v08.runner.joint_monitoring import DRAWS, contract_id
    from v08.runner.runtime_defaults import DEFAULT_WORKERS
    entries = load_entries(str(DEVSET))
    ordered = sorted(entries, key=lambda e: e["order"])
    full = [(int(e["order"]), d) for e in ordered for d in range(DRAWS)]
    q15 = json.loads(QUICK15.read_text(encoding="utf-8"))
    quick = [tuple(k) for k in q15["selection"]]
    full_rec = json.loads((FULL / "records.json").read_text(encoding="utf-8"))
    base_keys = sorted(r["contract_id"] for r in full_rec)
    div = select_diversity_families(entries)
    head = git("rev-parse", "HEAD")
    doc = {
        "commit": head, "branch": git("branch", "--show-current"),
        "devset": {"path": str(DEVSET), "sha256": sha(DEVSET), "families": len(entries)},
        "inputs": {e["family_id"]: {k: v for k, v in e.items() if k.endswith("sha256") or k in ("order", "facility_count",
                                                                                              "vehicle_count", "map_side_m")}
                   for e in ordered},
        "configs": {p.name: sha(p) for p in sorted((PROJ / "configs" / "v08").glob("*.json"))},
        "source_blobs": {f: git("rev-parse", f"HEAD:Multi-UAV SimpleGC/{f}") for f in BLOBS},
        "environment": {"python": sys.version.split()[0], "numpy": numpy.__version__, "scipy": scipy.__version__,
                        "shapely": shapely.__version__, "platform": platform.platform(),
                        "default_workers": DEFAULT_WORKERS, "threads": "OMP/OPENBLAS/MKL/NUMEXPR = 1（见 env.txt）"},
        "baselines": {
            "monitor_full_v14c": tree_digest(FULL) | {"records_sha256": sha(FULL / "records.json"),
                                                     "summary_sha256": sha(FULL / "summary.json"),
                                                     "contracts": len(full_rec),
                                                     "retained": sum(bool(r.get("success")) for r in full_rec)},
            "monitor_skeleton_v14b": {"path": str(SKEL), "records_sha256": sha(SKEL / "records.json"),
                                      "summary_sha256": sha(SKEL / "summary.json")},
            "v15_quick_selection": {"path": str(QUICK15), "sha256": sha(QUICK15)},
        },
        "keys": {
            "quick20": [contract_id({"order": o}, d) for o, d in quick],
            "full200": [contract_id({"order": o}, d) for o, d in full],
            "diversity100": [contract_id(e, 0, b) for e in div for b in range(10)],
            "diversity_families": [{"order": int(e["order"]), "family_id": e["family_id"],
                                    "facility_count": int(e["facility_count"])} for e in div],
            "rerun5": [contract_id({"order": o}, d) for o, d in full[:5]],
        },
        "checks": {"full200_equals_baseline_keys": [contract_id({"order": o}, d) for o, d in full] == base_keys,
                   "quick20_in_baseline": all(contract_id({"order": o}, d) in set(base_keys) for o, d in quick)},
        "run_root": {k: str(RUN / k) for k in ("cache", "out/monitor_regression_2", "out/skeleton_transit",
                                               "out/quick_transit", "out/full_transit", "out/rerun_transit",
                                               "out/monitor_regression_8", "diagnostics")},
        "data_root": str(DATA),
    }
    Path(sys.argv[1]).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"commit": head, "checks": doc["checks"], "n": {k: len(v) for k, v in doc["keys"].items()},
                      "retained": doc["baselines"]["monitor_full_v14c"]["retained"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
