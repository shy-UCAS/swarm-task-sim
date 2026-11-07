"""V8-18 第 1 部分：manifest.json（只读）。沿用 V8-17 make_manifest 的结构，增加：突入基线 full_r1、
V8-18 预置测试 SHA256（作者静态记录）、空的佯动不可行名单、新运行根与 V8_18_* 测试环境变量。名单算法沿用现有运行器。
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
IFULL = ROOT / "_handoff" / "2026-11-06_V8-17_intrusion" / "run" / "out" / "full" / "full_r1"
V17M = REPO / "docs" / "v08" / "V8-17" / "manifest.json"
V17H = REPO / "docs" / "v08" / "V8-17" / "part7" / "full_hashes.txt"
QSEL = REPO / "docs" / "v08" / "V8-16" / "part6" / "quick_selection.json"
HANDOFF = ROOT / "_handoff" / "2026-11-06_V8-18_feint"
RUN = HANDOFF / "run"
TESTS = PROJ / "tests" / "v08" / "V8-18"
INSTR = HANDOFF / "V8-18_佯动单段_执行指令_20261106.md"
APPX = HANDOFF / "V8-18_GPT指令评价与裁定_20261107.md"
PRESET_SHA = {"test_preset_numeric_v18.py": "37e0f99b805755a14fbc04ae10a5d19c8ac753401d014e2c6d2929dfca4f914c",
              "test_preset_local_geometry_v18.py": "df210a76922abd28e7ac66f5af5f8a64b8b53e04e11663fcac6b5895c0bf0c39",
              "test_preset_local_artifacts_v18.py": "028620ee13f136efec275f2925ae7e8948b46e75d2c7fd91c58b3c9c86eeea52"}
EXPECTED_DEVSET_SHA = "223e0e0d0745c3f72290da8e7260fa995a1ea18b37706f85ab8e5e99ea9f36e0"
QUICK_EXPECTED = ("o01_d0,o01_d1,o02_d0,o02_d1,o03_d0,o03_d1,o04_d0,o04_d1,o05_d0,o05_d1,o06_d0,o06_d1,o07_d0,o07_d1,"
                  "o08_d0,o08_d1,o09_d0,o09_d1,o11_d0,o11_d1").split(",")
SUBDIRS = ("cache", "out/gates_2", "out/gates_4", "out/smoke", "out/skeleton", "out/quick", "out/full", "out/rerun",
           "diagnostics")


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


def v17_hash(name):
    for line in V17H.read_text(encoding="utf-8").splitlines():
        h, p = line.split(" *", 1)
        if p.endswith("full/full_r1/" + name):
            return h
    return None


def main():
    import numpy, scipy, shapely
    from v08.runner.monitoring import load_entries, select_diversity_families
    from v08.runner.joint_monitoring import DRAWS, contract_id
    from v08.runner.runtime_defaults import DEFAULT_WORKERS
    entries = load_entries(str(DEVSET))
    ordered = sorted(entries, key=lambda e: e["order"])
    full = [(int(e["order"]), d) for e in ordered for d in range(DRAWS)]
    quick = [tuple(k) for k in json.loads(QSEL.read_text(encoding="utf-8"))["selection"]]
    recs = {k: json.loads((p / "records.json").read_text(encoding="utf-8")) for k, p in
            (("m", FULL), ("t", TFULL), ("i", IFULL))}
    div = select_diversity_families(entries)
    head = git("rev-parse", "HEAD")
    quick_ids = [contract_id({"order": o}, d) for o, d in quick]
    v17 = json.loads(V17M.read_text(encoding="utf-8"))
    inputs = {e["family_id"]: {k: v for k, v in e.items() if k.endswith("sha256") or k in (
        "order", "facility_count", "vehicle_count", "map_side_m")} for e in ordered}
    configs = {p.name: sha(p) for p in sorted((PROJ / "configs" / "v08").glob("*.json"))}
    full_ids = [contract_id({"order": o}, d) for o, d in full]
    doc = {
        "commit": head, "base_commit": git("rev-parse", "6dba0bc^{commit}"), "branch": git("branch", "--show-current"),
        "devset": {"path": str(DEVSET), "sha256": sha(DEVSET), "families": len(entries),
                   "sha256_equals_expected": sha(DEVSET) == EXPECTED_DEVSET_SHA,
                   "sha256_equals_v17_manifest": sha(DEVSET) == v17["devset"]["sha256"]},
        "inputs": inputs, "inputs_equal_v17_manifest": inputs == v17["inputs"],
        "configs": configs, "configs_equal_v17_manifest": configs == v17["configs"],
        "environment": {"python": sys.version.split()[0], "numpy": numpy.__version__, "scipy": scipy.__version__,
                        "shapely": shapely.__version__, "platform": platform.platform(),
                        "default_workers": DEFAULT_WORKERS, "rerun_workers": 1,
                        "threads": "OMP/OPENBLAS/MKL/NUMEXPR = 1（见 part1/env.txt）"},
        "baselines": {
            "monitor_full_v14c": tree_digest(FULL) | {"records_sha256": sha(FULL / "records.json"),
                                                     "contracts": len(recs["m"]),
                                                     "retained": sum(bool(r.get("success")) for r in recs["m"]),
                                                     "source": "V8-14 c 轮全量；V8-16/V8-17 门禁基线"},
            "transit_full_transit_r2": tree_digest(TFULL) | {"records_sha256": sha(TFULL / "records.json"),
                                                            "contracts": len(recs["t"]),
                                                            "retained": sum(bool(r.get("success")) for r in recs["t"]),
                                                            "source": "V8-16 REPORT §7（r2）；V8-17 门禁基线"},
            "intrusion_full_r1": tree_digest(IFULL) | {"records_sha256": sha(IFULL / "records.json"),
                                                      "records_sha256_v17_part7": v17_hash("records.json"),
                                                      "summary_sha256": sha(IFULL / "summary.json"),
                                                      "summary_sha256_v17_part7": v17_hash("summary.json"),
                                                      "contracts": len(recs["i"]),
                                                      "retained": sum(bool(r.get("success")) for r in recs["i"]),
                                                      "source": "V8-17 REPORT §7.1（full_r1，part7/full_hashes.txt）"},
        },
        "keys": {
            "quick20": quick_ids, "full200": full_ids,
            "diversity100": [contract_id(e, 0, b) for e in div for b in range(10)],
            "diversity_families": [{"order": int(e["order"]), "family_id": e["family_id"],
                                    "facility_count": int(e["facility_count"])} for e in div],
            "rerun5": full_ids[:5], "prototype3": ["o01_d0", "o02_d0", "o11_d1"], "edge": ["o17_d1", "o17_d4"],
        },
        "selection": {"quick20": "joint_monitoring.select_quick 既有确定性协议；读取 V8-16 已登记 part6/quick_selection.json",
                      "quick20_source_sha256": sha(QSEL), "full200": "40 族按 order 升序 × draw 0..4",
                      "diversity100": "monitoring.select_diversity_families 取 10 族 × draw 0 × branch 0..9",
                      "rerun5": "全量开始前按 (order, draw) 字典序前 5 键，不按结果重选"},
        "known_infeasible": [],
        "known_infeasible_note": "佯动预登记不可行名单为空（指令 1.6）；o17_d1、o17_d4 正常计数并单列；突入 o34_d3 证书不迁移",
        "checks": {"quick20_equals_instruction": quick_ids == QUICK_EXPECTED,
                   "full200_equals_monitor_keys": full_ids == sorted(r["contract_id"] for r in recs["m"]),
                   "full200_equals_transit_keys": sorted(full_ids) == sorted(r["contract_id"] for r in recs["t"]),
                   "full200_equals_intrusion_keys": sorted(full_ids) == sorted(r["contract_id"] for r in recs["i"]),
                   "intrusion_records_equal_v17_part7": sha(IFULL / "records.json") == v17_hash("records.json"),
                   "monitor_tree_equals_v17_manifest":
                       tree_digest(FULL)["tree_sha256"] == v17["baselines"]["monitor_full_v14c"]["tree_sha256"],
                   "transit_tree_equals_v17_manifest":
                       tree_digest(TFULL)["tree_sha256"] == v17["baselines"]["transit_full_transit_r2"]["tree_sha256"]},
        "tests": {name: {"sha256": sha(TESTS / name), "author_static_sha256": h, "equal": sha(TESTS / name) == h,
                         "status": "作者未经运行；执行方运行日志另列"} for name, h in PRESET_SHA.items()},
        "instruction": {"path": str(INSTR), "sha256": sha(INSTR)},
        "appendix": {"path": str(APPX), "sha256": sha(APPX)},
        "run_root": {k: str(RUN / k) for k in SUBDIRS},
        "data_root": str(DATA),
        "test_env": {"V8_18_DATA_ROOT": str(DATA), "V8_18_CACHE": str(RUN / "cache"), "V8_18_DEVSET": str(DEVSET),
                     "V8_18_ACCEPTANCE": str(REPO / "docs" / "v08" / "V8-18" / "acceptance.json")},
    }
    Path(sys.argv[1]).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"commit": head, "checks": doc["checks"], "devset": doc["devset"]["sha256_equals_expected"],
                      "inputs_equal_v17": doc["inputs_equal_v17_manifest"],
                      "configs_equal_v17": doc["configs_equal_v17_manifest"],
                      "tests": {k: v["equal"] for k, v in doc["tests"].items()},
                      "n": {k: len(v) for k, v in doc["keys"].items()},
                      "retained": {k: v.get("retained") for k, v in doc["baselines"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
