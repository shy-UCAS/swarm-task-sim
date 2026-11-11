"""V8-21 第 1 部分：登记、冻结快照、六意图基线索引（只读；写本任务外部 run/snapshot/<round> 与本目录 manifest.json）。

用法（代码工作目录 Multi-UAV SimpleGC，llm 环境）：python -B ../docs/v08/V8-21/part1_snapshot.py <round>
"""
import ast
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
CODE = REPO / "Multi-UAV SimpleGC"
DOCS = BASE / "traj2language_docs"
RUN = BASE / "_handoff/2026-11-10_V8-21_detour/run"
DOC = REPO / "docs/v08/V8-21"
S = "44186688316035ac11ce2dfbcd38417ebb613398"

BASELINES = {
    "monitoring": BASE / "_handoff/2026-11-10_V8-22_monitoring_entry/run/full",
    "transit": BASE / "_handoff/2026-11-05_V8-16_transit/run/out/full_transit_r2",
    "intrusion": BASE / "_handoff/2026-11-06_V8-17_intrusion/run/out/full/full_r1",
    "feint": BASE / "_handoff/2026-11-06_V8-18_feint/run/out/full_lazy_r1",
    "close_observation": BASE / "_handoff/2026-11-08_V8-19_close_observation/run/out/full_r1",
    "area_search": BASE / "_handoff/2026-11-09_V8-20_area_search/run/full/area_cost_ruling_r1",
}
EXPECTED_SUCCESS = {"monitoring": 198, "transit": 200, "intrusion": 199, "feint": 200, "close_observation": 200,
                    "area_search": 194}
QUICK = [f"o{o:02d}_d{d}" for o in (*range(1, 10), 11) for d in (0, 1)]
MAIN = [f"o{o:02d}_d{d}" for o in range(1, 41) for d in range(5)]
DIVERSITY = [f"o{o:02d}_d0_b{b}" for o in range(1, 11) for b in range(10)]
RERUN = [f"o01_d{d}" for d in range(5)]
FROZEN_DIRS = ("task_v07", "scene_v07", "v08/criteria", "v08/sampler", "v08/scene", "v08/sim", "swarm_sim")
FROZEN_FILES = ("configs/v08/criteria_segment.json", "configs/v08/guidance.json", "configs/v08/joint_opt.json",
                "configs/v08/monitoring.json", "configs/v08/sim.json", "v08/config.py",
                "v08/motion/monitoring_band.py", "v08/motion/path.py", "v08/motion/connect.py",
                "v08/motion/shared_routes.py", "v08/motion/formation.py", "v08/motion/layer_limits.py",
                "v08/motion/transit_chords.py", "v08/motion/nominal.py", "v08/motion/skeleton.py",
                "v08/motion/intents/monitoring.py", "v08/motion/nominal_checks.py", "v08/motion/speed.py",
                "v08/runner/monitoring.py", "v08/runner/joint_report.py", "v08/runner/transit_report.py",
                "v08/runner/area_search_report.py", "v08/runner/close_observation_report.py",
                "v08/motion/intents/close_observation.py", "v08/runner/skeleton_transit.py")
# 获准追加 detour 分支的共享文件：只对冻结符号做源码对照（不对整文件 hash 误报）
FROZEN_SYMBOLS = {
    "v08/runner/joint_monitoring.py": ("run_attempts", "monitoring_entry_counts", "_attempt_summary", "run_contract",
                                       "_retained_p0", "save_contract", "compare_dirs", "member_deviation",
                                       "tracking_stats", "full_stage", "rerun_stage", "run_batch"),
    "v08/motion/optimize.py": ("solve_joint", "JointProblem", "optimize_segment", "turns_from_skeleton",
                               "load_settings", "physical_limits", "prepare_problem"),
    "v08/runner/joint_intent.py": ("_intent_attempt_summary", "_dispatch", "_cost_order", "_prewarm_family",
                                   "prewarm_all", "rerun_stage"),
    "v08/contract/single_intent.py": ("transit_mission", "intrusion_mission",
                                      "feint_mission", "close_observation_mission", "area_search_mission"),
    "v08/motion/intent_dispatch.py": ("skeleton_intent", "_unsupported"),
}
# 白名单明确允许修改的共享符号（指令 0.2：single_intent 的“显式单段校验和分派”）；只记录差异，不算冻结违例
ALLOWED_MODIFIED = {"v08/contract/single_intent.py": ("validate_single_mission", "mission_for_intent")}
V22_BLOCK = '''    if task.intent == "monitoring":
        # V8-22：冻结监视判据不查预警进入次数；保留前按每成员释放后实测 10 Hz 帧复算目标预警进入次数，
        # 非 1 为普通失败（P0：首次入圈事件时刻；同 V8-17–V8-20 的做法）
        meas = monitoring_entry_counts(ctx, tracks, release, task.target_id)
        out["measured_monitoring"] = meas
        if not meas["all_single"]:
            return {"ok": False, "stage": "measured_monitoring_entries", "code": "candidate_rejected",
                    "reason": "measured_monitoring_entries", **out}
'''


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha(p):
    return sha_bytes(Path(p).read_bytes())


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, check=True).stdout


def at_s(rel):
    try:
        return git("show", f"{S}:Multi-UAV SimpleGC/{rel}")
    except subprocess.CalledProcessError:
        return None


def symbol_hash(text, name):
    tree = ast.parse(text)
    for node in tree.body:
        if getattr(node, "name", None) == name:
            return sha_bytes(ast.get_source_segment(text, node).encode("utf-8"))
    return None


def dump(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


def main():
    rnd = sys.argv[1]
    assert rnd.isalnum()
    out = RUN / "snapshot" / rnd
    assert not out.exists()
    t0 = time.perf_counter()
    sys.path.insert(0, str(CODE))
    import numpy, scipy, shapely
    files = {}
    for d in FROZEN_DIRS:
        for p in sorted((CODE / d).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                files[p.relative_to(CODE).as_posix()] = p
    for rel in FROZEN_FILES:
        files[rel] = CODE / rel
    frozen = {}
    for rel, p in sorted(files.items()):
        s_bytes = at_s(rel)
        cur = sha(p)
        frozen[rel] = {"sha256": cur, "s_sha256": None if s_bytes is None else sha_bytes(s_bytes),
                       "equal_to_s": s_bytes is not None and sha_bytes(s_bytes) == cur}
    symbols = []
    for rel, names in FROZEN_SYMBOLS.items():
        cur = (CODE / rel).read_text(encoding="utf-8")
        old = at_s(rel).decode("utf-8")
        for n in names:
            a, b = symbol_hash(old, n), symbol_hash(cur, n)
            symbols.append({"path": rel, "qualname": n, "s_sha256": a, "sha256": b, "equal_to_s": a is not None and a == b})
    allowed = []
    for rel, names in ALLOWED_MODIFIED.items():
        cur = (CODE / rel).read_text(encoding="utf-8")
        old = at_s(rel).decode("utf-8")
        for n in names:
            allowed.append({"path": rel, "qualname": n, "s_sha256": symbol_hash(old, n), "sha256": symbol_hash(cur, n)})
    jm = (CODE / "v08/runner/joint_monitoring.py").read_text(encoding="utf-8")
    v22_block = {"present_verbatim": V22_BLOCK in jm, "in_s": V22_BLOCK in at_s("v08/runner/joint_monitoring.py").decode("utf-8")}
    docs = {name: sha(p) for name, p in {
        "instruction": DOCS / "计划/V8-21_迂回单段_执行指令_20261110.md",
        "ruling_gpt": DOCS / "审计/V8-21_GPT指令评价与裁定_20261110.md",
        "ruling_candidate": DOCS / "审计/V8-21_候选取值补充裁定_20261111.md",
        "upper_requirements": DOCS / "计划/V8-21_迂回单段_上层任务要求_20261110.md",
        "v21a_summary": BASE / "_handoff/2026-11-11_DOCS-V8_sync/out/V8-21a_summary.json",
        "v21a_summary_original": BASE / "_handoff/2026-11-10_V8-21a_sweep/out/full/summary.json",
        "v21a_script": BASE / "_handoff/2026-11-10_V8-21a_sweep/sweep_stats_v21.py",
        "handoff_instruction_copy": BASE / "_handoff/2026-11-10_V8-21_detour/V8-21_迂回单段_执行指令_20261110.md"}.items()}
    presets = {p.name: sha(p) for p in sorted((CODE / "tests/v08/V8-21").glob("test_preset_*_v21.py"))}
    configs = {n: sha(CODE / "configs/v08" / f"{n}.json") for n in ("criteria_detour_candidate", "detour")}
    devset = REPO / "docs/v08/V8-03/devset_v08.json"
    entries = json.loads(devset.read_text(encoding="utf-8"))
    data_root = BASE / "SwarmData"
    scenes, missing = {}, []
    for e in entries:
        d = data_root / e["directory_rel"]
        row = {"family_id": e["family_id"], "path": str(d / "public_scene.json")}
        for name, key in (("public_scene.json", "public_scene_sha256"), ("family_initial.json", "family_initial_sha256")):
            p = d / name
            if not p.is_file():
                missing.append(str(p))
                continue
            h = sha(p)
            row[name] = {"sha256": h, "registered": e[key], "equal": h == e[key]}
        row["sha256"] = row.get("public_scene.json", {}).get("sha256")
        scenes[str(e["order"])] = row
    baselines = {}
    for intent, root in BASELINES.items():
        rows = json.loads((root / "records.json").read_text(encoding="utf-8"))
        ids = sorted(r["contract_id"] for r in rows)
        quick = {}
        for cid in QUICK:
            folder = root / "contracts" / cid
            fl = sorted(p for p in folder.rglob("*") if p.is_file()) if folder.is_dir() else []
            readable = bool(fl) and all(p.stat().st_size >= 0 for p in fl)
            if not readable:
                missing.append(str(folder))
            quick[cid] = {"files": len(fl), "bytes": sum(p.stat().st_size for p in fl),
                          "manifest_sha256": sha_bytes("\n".join(f"{p.relative_to(folder).as_posix()} {sha(p)}" for p in fl).encode())}
        baselines[intent] = {"path": str(root), "records": len(rows), "main_ids_equal": ids == MAIN,
                             "successes": sum(bool(r["success"]) for r in rows),
                             "expected_successes": EXPECTED_SUCCESS[intent], "records_sha256": sha(root / "records.json"),
                             "quick_contracts": quick}
    div = BASELINES["monitoring"] / "diversity"
    status = git("status", "--porcelain").decode("utf-8").splitlines()
    owners = {f"docs/v08/V8-{k}/owner_rerun.json": sha(REPO / f"docs/v08/V8-{k}/owner_rerun.json") for k in (17, 18, 19, 20)}
    doc = {"round": rnd, "baseline_commit": S, "branch": git("rev-parse", "--abbrev-ref", "HEAD").decode().strip(),
           "head": git("rev-parse", "HEAD").decode().strip(), "git_status": status, "owners_untracked": owners,
           "docs_sha256": docs, "preset_sha256": presets, "config_sha256": configs,
           "frozen_files": frozen, "frozen_files_changed": [k for k, v in frozen.items() if not v["equal_to_s"]],
           "frozen_symbols": symbols, "frozen_symbols_changed": [f"{s['path']}:{s['qualname']}" for s in symbols if not s["equal_to_s"]],
           "v22_monitoring_block": v22_block, "allowed_modified_symbols": allowed,
           "environment": {"python": sys.version, "numpy": numpy.__version__, "scipy": scipy.__version__,
                           "shapely": shapely.__version__, "os": platform.platform(), "executable": sys.executable,
                           "thread_env": {k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                                                                           "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")},
                           "workers": 24, "rerun_workers": 1},
           "devset": {"path": str(devset), "sha256": sha(devset), "families": len(entries)},
           "data_root": str(data_root), "cache": str(RUN / "cache"), "scenes_by_order": scenes,
           "lists": {"quick": QUICK, "main": MAIN, "diversity": DIVERSITY, "rerun": RERUN,
                     "preregistered_infeasible": []},
           "baselines": baselines, "monitoring_diversity": {"path": str(div), "is_dir": div.is_dir()},
           "missing": missing, "wall_s": time.perf_counter() - t0}
    doc["status"] = "passed" if (not missing and not doc["frozen_files_changed"] and not doc["frozen_symbols_changed"]
                                 and v22_block["present_verbatim"] and all(b["records"] == 200 and b["main_ids_equal"]
                                                                            for b in baselines.values())) else "attention"
    dump(out / "snapshot.json", doc)
    print(json.dumps({"status": doc["status"], "missing": len(missing), "frozen_changed": doc["frozen_files_changed"],
                      "symbols_changed": doc["frozen_symbols_changed"], "v22": v22_block,
                      "baselines": {k: (v["records"], v["successes"], v["main_ids_equal"]) for k, v in baselines.items()},
                      "wall_s": doc["wall_s"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
