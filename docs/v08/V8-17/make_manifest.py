"""V8-17 第 1 部分：manifest.json（只读）。沿用 V8-16 make_manifest 的结构，增加：过境基线 full_transit_r2、
预置测试 SHA256、不可行名单、新运行根、选择算法说明与 V8_17_* 测试环境变量。名单算法沿用现有运行器。
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
FULL = ROOT / "_handoff" / "2026-11-04_V8-14_skeleton" / "out" / "full_v14c"
TFULL = ROOT / "_handoff" / "2026-11-05_V8-16_transit" / "run" / "out" / "full_transit_r2"
TSKEL = ROOT / "_handoff" / "2026-11-05_V8-16_transit" / "run" / "out" / "skeleton_transit_r3"
MSKEL = ROOT / "_handoff" / "2026-11-04_V8-14_skeleton" / "out" / "skeleton_v14b"
V16M = REPO / "docs" / "v08" / "V8-16" / "manifest.json"
QSEL = REPO / "docs" / "v08" / "V8-16" / "part6" / "quick_selection.json"   # 既有 select_quick 名单（V8-16 登记）
HANDOFF = ROOT / "_handoff" / "2026-11-06_V8-17_intrusion"
RUN = HANDOFF / "run"
TESTS = PROJ / "tests" / "v08" / "V8-17"
PRESET_SHA = {"test_preset_numeric_v17.py": "eca9adfc243aad4c74bced8597af1f1e0d4ce4b2a33e6e30704e312051188478",
              "test_preset_local_geometry_v17.py": "5066c4a07d69bd6fcc4dc8b1aaf2bcbdc98e16665a31c037b53cfd1548327c19",
              "test_preset_local_artifacts_v17.py": "cbad45ebb2a23f402b3bf7955e867b40cb0d0e8207f1f9a406e632bdbd90d389"}
EXPECTED_DEVSET_SHA = "223e0e0d0745c3f72290da8e7260fa995a1ea18b37706f85ab8e5e99ea9f36e0"
QUICK_EXPECTED = ("o01_d0,o01_d1,o02_d0,o02_d1,o03_d0,o03_d1,o04_d0,o04_d1,o05_d0,o05_d1,o06_d0,o06_d1,o07_d0,o07_d1,"
                  "o08_d0,o08_d1,o09_d0,o09_d1,o11_d0,o11_d1").split(",")
SUBDIRS = ("cache", "out/monitor_regression_2", "out/transit_regression_2", "out/monitor_regression_4",
           "out/transit_regression_4", "out/smoke", "out/skeleton", "out/quick", "out/full", "out/rerun", "diagnostics")


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


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
    quick = [tuple(k) for k in json.loads(QSEL.read_text(encoding="utf-8"))["selection"]]
    full_rec = json.loads((FULL / "records.json").read_text(encoding="utf-8"))
    tfull_rec = json.loads((TFULL / "records.json").read_text(encoding="utf-8"))
    div = select_diversity_families(entries)
    head = git("rev-parse", "HEAD")
    quick_ids = [contract_id({"order": o}, d) for o, d in quick]
    v16 = json.loads(V16M.read_text(encoding="utf-8"))
    doc = {
        "commit": head, "base_commit": git("rev-parse", "d9a3178^{commit}"), "branch": git("branch", "--show-current"),
        "devset": {"path": str(DEVSET), "sha256": sha(DEVSET), "families": len(entries),
                   "sha256_equals_v16_manifest": sha(DEVSET) == EXPECTED_DEVSET_SHA == v16["devset"]["sha256"]},
        "inputs": {e["family_id"]: {k: v for k, v in e.items() if k.endswith("sha256") or k in ("order", "facility_count",
                                                                                              "vehicle_count", "map_side_m")}
                   for e in ordered},
        "inputs_equal_v16_manifest": {e["family_id"]: {k: v for k, v in e.items() if k.endswith("sha256") or k in (
            "order", "facility_count", "vehicle_count", "map_side_m")} for e in ordered} == v16["inputs"],
        "configs": {p.name: sha(p) for p in sorted((PROJ / "configs" / "v08").glob("*.json"))},
        "configs_equal_v16_manifest": {p.name: sha(p) for p in sorted((PROJ / "configs" / "v08").glob("*.json"))}
        == v16["configs"],
        "environment": {"python": sys.version.split()[0], "numpy": numpy.__version__, "scipy": scipy.__version__,
                        "shapely": shapely.__version__, "platform": platform.platform(),
                        "default_workers": DEFAULT_WORKERS, "threads": "OMP/OPENBLAS/MKL/NUMEXPR = 1（见 part1/env.txt）"},
        "baselines": {
            "monitor_full_v14c": tree_digest(FULL) | {"records_sha256": sha(FULL / "records.json"),
                                                     "summary_sha256": sha(FULL / "summary.json"),
                                                     "contracts": len(full_rec),
                                                     "retained": sum(bool(r.get("success")) for r in full_rec),
                                                     "tree_equals_v16_manifest":
                                                         None},
            "transit_full_transit_r2": tree_digest(TFULL) | {"records_sha256": sha(TFULL / "records.json"),
                                                            "summary_sha256": sha(TFULL / "summary.json"),
                                                            "contracts": len(tfull_rec),
                                                            "retained": sum(bool(r.get("success")) for r in tfull_rec),
                                                            "source": "V8-16 REPORT §7（r2，P0-3 修复后）"},
            "monitor_skeleton_v14b": {"path": str(MSKEL), "records_sha256": sha(MSKEL / "records.json")},
            "transit_skeleton_r3": {"path": str(TSKEL), "records_sha256": sha(TSKEL / "records.json")},
        },
        "keys": {
            "quick20": quick_ids,
            "full200": [contract_id({"order": o}, d) for o, d in full],
            "diversity100": [contract_id(e, 0, b) for e in div for b in range(10)],
            "diversity_families": [{"order": int(e["order"]), "family_id": e["family_id"],
                                    "facility_count": int(e["facility_count"])} for e in div],
            "rerun5": [contract_id({"order": o}, d) for o, d in full[:5]],
            "smoke4": ["o01_d0", "o01_d1", "o02_d0", "o11_d0"],
            "edge": ["o17_d1", "o17_d4"],
        },
        "selection": {"quick20": "joint_monitoring.select_quick 既有确定性协议；读取 V8-16 已登记 part6/quick_selection.json",
                      "quick20_source_sha256": sha(QSEL),
                      "full200": "40 族按 order 升序 × draw 0..4",
                      "diversity100": "monitoring.select_diversity_families 取 10 族 × draw 0 × branch 0..9",
                      "rerun5": "全量开始前按 (order, draw) 字典序前 5 键，不按结果重选"},
        "known_infeasible": [{"contract_id": "o34_d3", "family_id": "family_s15_3968861533cf6dd7",
                              "target_id": "facility_02", "used_for": "仅成功率与档差的分母（199）"}],
        "checks": {"quick20_equals_instruction": quick_ids == QUICK_EXPECTED,
                   "quick20_excludes_o34_d3": "o34_d3" not in quick_ids,
                   "full200_equals_monitor_baseline_keys":
                       [contract_id({"order": o}, d) for o, d in full] == sorted(r["contract_id"] for r in full_rec),
                   "full200_equals_transit_baseline_keys":
                       sorted(contract_id({"order": o}, d) for o, d in full) == sorted(r["contract_id"] for r in tfull_rec)},
        "tests": {name: {"sha256": sha(TESTS / name), "expected": h, "equal": sha(TESTS / name) == h}
                  for name, h in PRESET_SHA.items()},
        "instruction": {"path": str(HANDOFF / "V8-17_突入单段_执行指令_20261106.md"),
                        "sha256": sha(HANDOFF / "V8-17_突入单段_执行指令_20261106.md")},
        "appendix": {"path": str(HANDOFF / "V8-17_GPT指令评价与裁定_20261106.md"),
                     "sha256": sha(HANDOFF / "V8-17_GPT指令评价与裁定_20261106.md")},
        "run_root": {k: str(RUN / k) for k in SUBDIRS},
        "data_root": str(DATA),
        "test_env": {"V8_17_DATA_ROOT": str(DATA), "V8_17_TEST_CACHE": str(RUN / "cache"), "V8_17_DEVSET": str(DEVSET),
                     "V8_17_MONITOR_BASELINE": str(FULL), "V8_17_TRANSIT_BASELINE": str(TFULL),
                     "V8_17_REGRESSION_MANIFEST": str(REPO / "docs" / "v08" / "V8-17" / "regression_gates.json")},
    }
    doc["baselines"]["monitor_full_v14c"]["tree_equals_v16_manifest"] = (
        doc["baselines"]["monitor_full_v14c"]["tree_sha256"] == v16["baselines"]["monitor_full_v14c"]["tree_sha256"])
    Path(sys.argv[1]).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"commit": head, "checks": doc["checks"], "devset_ok": doc["devset"]["sha256_equals_v16_manifest"],
                      "inputs_equal_v16": doc["inputs_equal_v16_manifest"], "configs_equal_v16":
                          doc["configs_equal_v16_manifest"], "tests": {k: v["equal"] for k, v in doc["tests"].items()},
                      "n": {k: len(v) for k, v in doc["keys"].items()},
                      "retained": {k: v.get("retained") for k, v in doc["baselines"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
