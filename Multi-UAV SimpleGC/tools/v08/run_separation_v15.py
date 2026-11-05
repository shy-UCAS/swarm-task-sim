"""V8-15 实验入口（指令 4、6、7）：workers / production-quick / stress-skeleton / stress-checkpoint / stress-rest。

五种显式模式，不会隐式调用 full_stage（不执行 --stage full/diversity）。任务一律通过生产 run_pool_singles 单合同
动态派发（spawn、chunksize 1）；合同仍由未修改的 joint_monitoring._pool_task / run_contract / attempt_chain /
run_attempts / save_contract 执行。测量探针只在本入口进程内、调用 run_pool_singles 的作用域里临时把
joint_monitoring._pool_task 绑定到本模块的顶层函数（finally 恢复）；子进程不执行该绑定。生产入口不导入本模块。

用法（Multi-UAV SimpleGC 目录，conda llm；入口自己为子进程设 OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1）：
    python -B tools/v08/run_separation_v15.py --mode workers --select-to <selection.json> --baseline <full_v14c>
        --devset ... --data-root ... --cache ... --out <unused>
    python -B tools/v08/run_separation_v15.py --mode workers --keys <selection.json> --workers 8|16|24
        --baseline <full_v14c> --devset ... --data-root ... --cache ... --out <不存在的新目录>
    python -B tools/v08/run_separation_v15.py --mode production-quick [--workers N] --baseline ... --devset ...
        --data-root ... --cache ... --out <新目录>
    python -B tools/v08/run_separation_v15.py --mode stress-skeleton|stress-checkpoint|stress-rest [--workers N]
        [--stress-root <压力运行根>] --devset ... --data-root ... --cache ... --out <新目录> --baseline <unused>
--workers 未给时读 v08.runner.runtime_defaults.DEFAULT_WORKERS（尚未生成时为 None，须显式给出）。
退出码：0 完成；4 P0（逐字节比较不一致）；3 前提缺失/未完成；1 参数或路径错误。
"""
import argparse
import json
import math
import os
import sys
import time
import traceback
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

MODES = ("workers", "production-quick", "stress-skeleton", "stress-checkpoint", "stress-rest")
THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")
TIMING_COUNT = 40                 # U D.3
STRESS_PRIORS = ("abreast", "column", "echelon")       # U D.5（不另列 loose）
STRESS_SEEDS = (0, 1, 2)          # 生产 diversity 约定：common draw 固定 0，branch 作种子
STRESS_FAMILIES = 4               # U D.5
STRESS_BUDGET_S = 3600.0          # U D.5.3：60 × 60
EFFICIENCY = 0.9                  # U D.3.6
CHECKPOINT_MAX_WORKERS = 3        # 指令 6.3.3：检查点最多 3 个


def _default_workers():
    try:
        from v08.runner.runtime_defaults import DEFAULT_WORKERS
    except ImportError:
        return None
    return int(DEFAULT_WORKERS)


def build_parser():
    """无执行副作用的解析器（指令 8.1）。"""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=MODES, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--devset", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--workers", type=int, default=_default_workers())
    ap.add_argument("--keys", help="workers 模式：part4 selection.json")
    ap.add_argument("--select-to", help="workers 模式：只计算 40 合同名单写到该文件后退出")
    ap.add_argument("--stress-root", help="压力运行根（其下 skeleton/checkpoint/rest 子目录）")
    return ap


def _log(msg, flush=True):
    print(msg, flush=True)


# ---------------------------------------------------------------- spawn 下的测量探针（顶层可 pickle）

def measured_pool_task(task):
    """在子进程调用未修改的 joint_monitoring._pool_task，然后给返回 row 附 PID/峰值工作集（合同目录外）。"""
    for k in THREAD_VARS:
        os.environ.setdefault(k, "1")
    from v08.runner import joint_monitoring as JM
    import v15_memory as VM
    row = JM._pool_task(task)
    mem = VM.process_memory()
    row["pid"] = mem["pid"]
    row["peak_working_set_bytes"] = mem.get("peak_working_set_bytes")
    row["working_set_bytes"] = mem.get("working_set_bytes")
    row["memory_source"] = mem.get("source")
    return row


def stress_pool_task(task):
    """("stress"|"stress_skeleton", entry, 0, seed, data_root, cache_dir, out_dir, deadline, prior)：
    在 worker 内加载上下文、调用压力装配器与 run_stress_contract（不让生产 _pool_task 重抽普通 g0 合同）。"""
    for k in THREAD_VARS:
        os.environ.setdefault(k, "1")
    import v15_memory as VM
    from v08.motion.optimize import load_settings
    from v08.scene.context import load_context
    kind, entry, draw, seed, data_root, cache_dir, out_dir, deadline, prior = task[:9]
    cid = f"stress_o{int(entry['order']):02d}_{prior}_s{int(seed)}"
    g = globals().setdefault("_WCTX", {})
    t0 = time.perf_counter()
    try:
        if entry["order"] not in g:
            while len(g) >= 3:
                g.pop(next(iter(g)))
            g[entry["order"]] = load_context(entry, data_root=Path(data_root), cache_dir=Path(cache_dir))
        ctx = g[entry["order"]]
        case = make_stress_case(ctx, entry, prior=prior, seed=seed)
        rec = run_stress_contract(ctx, entry, case, settings=load_settings(), out_dir=Path(out_dir),
                                  skeleton_only=(kind == "stress_skeleton"))
        row = _stress_row(rec)
    except Exception as exc:
        row = {"contract_id": cid, "kind": kind, "success": False, "attempts": None, "error": repr(exc),
               "traceback": traceback.format_exc()}
    row.update(kind=kind, prior=prior, seed=int(seed), order=int(entry["order"]), wall_s=time.perf_counter() - t0)
    mem = VM.process_memory()
    row.update(pid=mem["pid"], peak_working_set_bytes=mem.get("peak_working_set_bytes"))
    return row


class _BoundPoolTask:
    """只在 with 作用域内把 joint_monitoring._pool_task 换成本模块顶层函数；finally 恢复。"""

    def __init__(self, fn):
        self.fn = fn

    def __enter__(self):
        from v08.runner import joint_monitoring as JM
        self.JM, self.orig = JM, JM._pool_task
        JM._pool_task = self.fn
        return self

    def __exit__(self, *exc):
        self.JM._pool_task = self.orig
        return False


# ---------------------------------------------------------------- 缓存只读核对

def cache_state(cache_dir):
    """缓存目录全部文件 (大小, mtime_ns)；worker 阶段不得更新已建缓存文件。"""
    root = Path(cache_dir)
    return {p.relative_to(root).as_posix(): [p.stat().st_size, p.stat().st_mtime_ns]
            for p in sorted(root.rglob("*")) if p.is_file()}


def cache_diff(before, after):
    return {"added": sorted(set(after) - set(before)), "removed": sorted(set(before) - set(after)),
            "changed": sorted(k for k in set(before) & set(after) if before[k] != after[k])}


# ---------------------------------------------------------------- 名单派发（第 4.1 节）

def write_selection(baseline, path):
    """全量 records.json 的 200 条 _pool_task wall_s → 40 合同名单（v15_metrics.selection_detail）。"""
    import hashlib
    from v15_metrics import selection_detail
    rec_path = Path(baseline) / "records.json"
    raw = rec_path.read_bytes()
    rows = json.loads(raw.decode("utf-8"))
    det = selection_detail(rows, count=TIMING_COUNT)
    det.update(records_path=str(rec_path.resolve()), records_sha256=hashlib.sha256(raw).hexdigest(),
               wall_s_all=[{"contract_id": r["contract_id"], "order": r["order"], "draw_index": r["draw_index"],
                            "branch": r.get("branch"), "success": r.get("success"), "wall_s": r.get("wall_s")}
                           for r in rows],
               protocol="p20–p80 闭区间（numpy linear）；按 (wall_s, order, draw_index, branch∅=−1) 排序；"
                        "下标 floor(k(M−1)/39)；失败合同不排除")
    Path(path).write_text(json.dumps(det, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return det


def run_selected(entries, keys, *, data_root, cache_dir, out_dir, workers, baseline=None, log=_log):
    """名单批次：族预热（单列计时）→ 按 group_size × map_side_m 降序、业务键排序派发八元组 ("full", entry, draw, None,
    data_root, cache_dir, out_dir, inf) → run_pool_singles（spawn、单合同动态派发）。deadline=inf，不继承 full 7200 s。
    每份合同与基线同 id 目录逐字节比较（排除清单为空）。返回 summary。"""
    import v15_memory as VM
    from v15_metrics import compare_contracts
    from v08.runner import joint_monitoring as JM
    from v08.runner.monitoring import write_json
    for k in THREAD_VARS:
        os.environ[k] = "1"
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=False)
    by_order = {int(e["order"]): e for e in entries}
    keys = [(int(o), int(d)) for o, d in keys]
    fams = sorted({o for o, _ in keys})
    t_start = time.time()
    pre = JM.prewarm_cache([by_order[o] for o in fams], data_root=data_root, cache_dir=cache_dir, log=log)
    write_json(out / "prewarm.json", pre, indent=1)
    cache_before = cache_state(cache_dir)
    tasks = []
    for o, d in keys:
        e = by_order[o]
        cost = pre["group_size"][f"{o}:{d}"] * float(e["map_side_m"])
        tasks.append((cost, o, d, ("full", e, d, None, str(data_root), str(cache_dir), str(out), float("inf"))))
    tasks.sort(key=lambda x: (-x[0], x[1], x[2]))
    write_json(out / "dispatch_order.json", [{"order": o, "draw": d, "cost": c} for c, o, d, _ in tasks], indent=1)
    sampler = VM.SystemSampler().start()
    sampler.mark("dispatch")

    def logm(msg, flush=True):
        sampler.mark("completion")
        log(msg)

    t_disp = time.time()
    with _BoundPoolTask(measured_pool_task):
        rows, unsent = JM.run_pool_singles([t for *_, t in tasks], workers=workers, deadline=float("inf"), log=logm)
    disp_wall = time.time() - t_disp
    mem = sampler.stop()
    cache_after = cache_state(cache_dir)
    rows.sort(key=lambda r: r["contract_id"])
    comps = []
    if baseline is not None:
        for r in rows:
            cid = r["contract_id"]
            c = compare_contracts(Path(baseline) / "contracts" / cid, out / "contracts" / cid)
            comps.append({"contract_id": cid, "success": r.get("success"), **{k: c[k] for k in (
                "file_sets_equal", "bytes_equal", "differing", "only_source", "only_repeat")}, "files": len(c["files"])})
    want = {JM.contract_id({"order": o}, d) for o, d in keys}
    got = {r["contract_id"] for r in rows}
    peaks = {}
    for r in rows:
        if r.get("pid") is not None and r.get("peak_working_set_bytes") is not None:
            peaks[r["pid"]] = max(peaks.get(r["pid"], 0), int(r["peak_working_set_bytes"]))
    summary = {"workers": workers, "keys": len(keys), "completed": len(rows), "missing": sorted(want - got),
               "unsent": unsent, "errors": [r["contract_id"] for r in rows if r.get("error")],
               "incomplete": [r["contract_id"] for r in rows if r.get("incomplete")],
               "prewarm_s": pre["wall_s"], "dispatch_wall_s": disp_wall, "wall_with_prewarm_s": time.time() - t_start,
               "contract_busy_s": float(sum(r.get("wall_s") or 0.0 for r in rows)),
               "parallel_efficiency": (sum(r.get("wall_s") or 0.0 for r in rows) / (disp_wall * workers)) if disp_wall else None,
               "system_memory": mem, "worker_peak_working_set_bytes": peaks,
               "worker_peak_max_bytes": max(peaks.values()) if peaks else None,
               "cache_write_during_workers": cache_diff(cache_before, cache_after),
               "comparisons_all_bytes_equal": (all(c["bytes_equal"] for c in comps) and len(comps) == len(keys))
               if baseline is not None else None,
               "threads": {k: os.environ.get(k) for k in THREAD_VARS}}
    write_json(out / "records.json", [{k: v for k, v in r.items() if k not in ("curve_before", "curve_after")}
                                      for r in rows], indent=1)
    write_json(out / "comparisons.json", comps, indent=1)
    write_json(out / "summary.json", summary, indent=1)
    return summary


# ---------------------------------------------------------------- 压力合同（第 6 节）

def make_stress_case(ctx, entry, *, prior, seed):
    """用生产draw=0的原始字段构造一个全员组；组ID隔离压力随机键，不改生产采样器。"""
    from v08.contract.monitoring import CommonDraw, Mission, monitoring_mission, validate_mission
    from v08.runner.monitoring import jsonable
    from v08.sampler.common import sample_common
    from v08.sampler.keys import RngKey, key_words
    fam = ctx.family
    common = sample_common(fam, 0)
    source = monitoring_mission(ctx, common)
    g0 = source.groups[0]
    gid = f"stress_v15/{g0.group_id}/{prior}"
    group = replace(g0, member_ids=tuple(sorted(fam.initial_states)), formation_prior=prior, group_id=gid)
    bkey = dict(source.business_key, group=gid, branch=int(seed))
    mission = Mission(source.family_id, 0, source.policy_version, dict(source.input_sha256), bkey,
                      CommonDraw(common.family_id, common.draw_index, (group,)), (group,), source.tasks)
    validate_mission(mission, ctx)
    key = RngKey(fam.family_id, 0, "shape", mission=0, branch=int(seed), group=gid, segment=0, attempt=0)
    parent_key = RngKey(fam.family_id, 0, "shape", mission=0, branch=None, group=g0.group_id, segment=0, attempt=0)
    src = {"order": int(entry["order"]), "draw_index": 0, "group_id": g0.group_id, "member_ids": list(g0.member_ids),
           "target_id": source.tasks[0].target_id, "speed_profile": jsonable(g0.speed_profile.__dict__),
           "formation_prior": g0.formation_prior, "groups_in_common": len(common.groups),
           "parent_shape_key": jsonable(parent_key.__dict__), "parent_shape_key_words": list(key_words(parent_key)),
           "stress_shape_key": jsonable(key.__dict__), "stress_shape_key_words": list(key_words(key))}
    return {"mission": mission, "key": key, "contract_id": f"stress_o{int(entry['order']):02d}_{prior}_s{int(seed)}",
            "source": src}


def _retreat_attempts(summaries, prior):
    from v08.motion.formation import mapped_start
    start = mapped_start(prior)
    n = 0
    for s in summaries:
        f = (s.get("draw") or {}).get("formation") if isinstance(s.get("draw"), dict) else s.get("formation")
        if f is not None and f != start:
            n += 1
    return n


def run_stress_contract(ctx, entry, case, *, settings, out_dir, skeleton_only=False):
    """复用唯一20次预算和真实阶段函数；压力元数据与生产统计隔离。"""
    from v08.contract.monitoring import initial_states
    from v08.motion.formation import mapped_start
    from v08.motion.plan import final_failure
    from v08.runner import joint_monitoring as JM
    from v08.runner import joint_report as JR
    from v08.runner.monitoring import jsonable
    mission = case["mission"]
    group, task = mission.groups[0], mission.tasks[0]
    states = initial_states(ctx.family, group.member_ids)
    key0 = case["key"]
    base = {"contract_id": case["contract_id"], "family_id": ctx.family.family_id, "order": int(entry["order"]),
            "draw_index": 0, "branch": int(key0.branch), "facility_count": int(entry["facility_count"]),
            "vehicle_count": int(ctx.family.vehicle_count), "lateral_spacing_m": float(ctx.family.lateral_spacing_m),
            "group_id": group.group_id, "member_ids": sorted(group.member_ids), "group_size": len(group.member_ids),
            "target_id": task.target_id, "initial_speed_m_s": float(group.speed_profile.initial_speed_m_s),
            "formation_prior": group.formation_prior, "mapped_start": mapped_start(group.formation_prior)}
    if skeleton_only:
        from v08.motion.intents.monitoring import last_attempt_timing
        from v08.motion.plan import plan_attempt
        from v08.runner import skeleton_monitoring as SK
        logs, plans = [], {}

        def attempt_fn(k):
            t0 = time.perf_counter()
            try:
                plan = plan_attempt(ctx, group, task, states, (), k)
            except Exception:
                logs.append(SK._summarize_attempt(k.attempt, None, {"attempt_wall_s": time.perf_counter() - t0},
                                                  exc_text=traceback.format_exc()))
                return {"ok": False, "stage": "exception"}
            rec_ = SK._summarize_attempt(k.attempt, plan, {"attempt_wall_s": time.perf_counter() - t0,
                                                           **last_attempt_timing()})
            logs.append(rec_)
            if plan.failure is None:
                plans["ok"] = plan
            return {"ok": plan.failure is None, "stage": rec_["stage"]}

        out = JM.run_attempts(key0, attempt_fn, budget=JM.BUDGET)
        failure = None
        if not out["success"]:
            f = final_failure(ctx, group, task, [{"stage": r["stage"]} for r in logs])
            failure = {"code": f.code, "reason": f.reason, "feasible_set": f.feasible_set, "witness": jsonable(f.witness)}
        rec = {**base, "success": bool(out["success"]), "attempts": int(out["attempts"]),
               "shape_audit_failed_attempts": sum(1 for r in logs if r["shape_audit_failed"]),
               "exceptions": sum(1 for r in logs if r["stage"] == "exception"), "failure": failure,
               "attempt_log": [{k: v for k, v in r.items() if k != "timing"} for r in logs],
               "retreat_attempts": sum(1 for r in logs if r.get("formation") not in (None, base["mapped_start"]))}
        if out["success"]:
            plan = plans["ok"]
            rec["formation"] = {k: plan.formation.get(k) for k in ("prior", "start", "realized", "mapped_from_loose",
                                                                   "lateral_step_m")}
            rec["topology"] = {k: plan.topology.get(k) for k in ("final", "laps", "traversals", "prior_draw", "forced",
                                                                  "forced_reason")}
            rec["nominal_duration_s"] = float(plan.nominal_duration_s)
        tele = {"timing": [r.get("timing") for r in logs]}
        SK._save(Path(out_dir), rec, plans.get("ok"), tele)
        rec["_timing"] = tele["timing"]
        return rec
    summaries = []

    def attempt_fn(k):
        flag = {}
        try:
            rec_ = JM.attempt_chain(ctx, group, task, states, k, settings, entry_flag=flag)
        except Exception as exc:
            rec_ = {"ok": False, "stage": "exception", "code": "implementation_error", "reason": repr(exc),
                    "traceback": traceback.format_exc(), "timing": {},
                    "optimization_entered": flag.get("optimization_entered")}
        summaries.append(JM._attempt_summary(rec_, k))
        return rec_

    out = JM.run_attempts(key0, attempt_fn)
    failure = None
    if not out["success"]:
        log = []
        for s in summaries:
            stage = s["stage"]
            if stage == "skeleton":
                w = s.get("witness") if isinstance(s.get("witness"), dict) else {}
                stage = w.get("stage", s.get("feasible_set"))
            log.append({"stage": stage})
        f = final_failure(ctx, group, task, log)
        failure = {"code": f.code, "reason": f.reason, "feasible_set": f.feasible_set, "witness": jsonable(f.witness)}
    rec = {**base, "success": bool(out["success"]), "attempts": out["attempts"],
           "optimization_s": float(sum((s["timing"] or {}).get("optimize_s", 0.0) for s in summaries)),
           "failure": failure, "attempt_log": summaries, "settings_sha256": settings.get("_sha256"),
           "release_us": None, "retained_p0_ok": True, "incomplete": bool(out.get("incomplete", False))}
    cnt = JR.attempt_counters(summaries)
    missing_flag = any(not s["ok"] and not isinstance(s.get("optimization_entered"), bool) for s in summaries)
    rec["post_optimization_failures"] = None if missing_flag else cnt["post_optimization_failures"]
    rec["skeleton_failures"] = cnt["skeleton_failures"]
    rec["unknown_attempts"] = cnt["unknown_attempts"]
    rec["shape_audit_failed_attempts"] = sum(1 for s in summaries if s.get("shape_audit_failed"))
    rec["draws"] = [s.get("draw") for s in summaries]
    rec["stage_timing"] = {k: float(sum((s["timing"] or {}).get(k, 0.0) for s in summaries))
                           for k in ("skeleton_s", "optimize_s", "simulation_s", "verify_s")}
    rec["retreat_attempts"] = _retreat_attempts(summaries, group.formation_prior)
    if out["success"]:
        res = out["result"]
        rec["release_us"] = {m: int(v) for m, v in sorted(res["release_us"].items())}
        rec["retained_p0_ok"] = JM._retained_p0(res)
        rec["deviation"] = JM.member_deviation(res)
        rec["tracking"] = JM.tracking_stats(res)
        try:
            rec["phase_metrics"] = JM.phase_diagnostics(res)
        except Exception:
            rec["phase_metrics"] = {"error": traceback.format_exc()}
        plan = res["plan"]
        rec["nominal_duration_s"] = float(plan.nominal_duration_s)
        rec["formation"] = {k: plan.formation.get(k) for k in ("prior", "start", "realized", "mapped_from_loose",
                                                               "lateral_step_m")}
        rec["topology"] = {k: plan.topology.get(k) for k in ("final", "laps", "traversals", "turn_kind", "prior_draw",
                                                             "forced", "forced_reason")}
    last = out["records"][-1] if (out["records"] and not out["success"]) else None
    JM.save_contract(Path(out_dir), rec, out["result"], last_failed=last)
    return rec


def _stress_row(rec):
    keys = ("contract_id", "family_id", "order", "branch", "group_size", "target_id", "formation_prior", "mapped_start",
            "member_ids", "release_us", "facility_count", "vehicle_count", "draw_index",
            "success", "attempts", "failure", "formation", "topology", "retreat_attempts", "shape_audit_failed_attempts",
            "post_optimization_failures", "skeleton_failures", "unknown_attempts", "retained_p0_ok", "stage_timing",
            "nominal_duration_s", "incomplete", "optimization_s", "exceptions")
    row = {k: rec.get(k) for k in keys}
    row["attempt_log"] = [{k: a.get(k) for k in ("attempt", "ok", "stage", "skeleton_stage", "code", "reason",
                                                 "optimization_entered", "shape_audit_failed", "formation")}
                          | ({"draw_formation": (a.get("draw") or {}).get("formation")}
                             if isinstance(a.get("draw"), dict) else {})
                          | ({"validity": a.get("validity")} if a.get("validity") else {})
                          | ({"physical_kinds": sorted({f.get("kind") for f in
                                                        ((a.get("optimize") or {}).get("physical_failures") or [])})}
                             if a.get("optimize") else {})
                          for a in rec.get("attempt_log") or []]
    row["attempt_timing"] = rec.get("_timing") or [a.get("timing") for a in rec.get("attempt_log") or []]
    return row


def narrow_band(ctx, entry):
    """排序诊断（指令 6.1.2）：源目标中心为圆心，复用 _Setup 与 BandGeometry 的 360 行 × 2 m 径向网格及完整
    base+patrol 约束；每行取全部原始可行径向 runs 中最长者（同长取较小 lo，与 raw_interval 一致），宽度为端点半径差；
    无区间宽度为 0；返回 360 行最小宽度与逐行区间。不是可行性检验，不加 D/q/η。"""
    from v08.contract.monitoring import initial_states, monitoring_mission
    from v08.motion.intents.monitoring import _Setup
    from v08.motion.monitoring_band import PHI_ROWS, BandGeometry, _longest, _row_runs_fast
    from v08.sampler.common import sample_common
    from v08.sampler.keys import RngKey
    source = monitoring_mission(ctx, sample_common(ctx.family, 0))
    g0, task = source.groups[0], source.tasks[0]
    key = RngKey(ctx.family.family_id, 0, "shape", mission=0, group=g0.group_id, segment=0)
    S = _Setup(ctx, g0, task, initial_states(ctx.family, g0.member_ids), key)
    G = BandGeometry(S, S.tgt.center)
    rows = []
    for j in range(PHI_ROWS):
        best = _longest(_row_runs_fast(G.pm[j], G.cm[j], 0.0, 0, len(G.rs) - 1))
        rows.append(None if best is None else [float(G.rs[best[0]]), float(G.rs[best[1]])])
    widths = [0.0 if r is None else r[1] - r[0] for r in rows]
    return {"order": int(entry["order"]), "family_id": ctx.family.family_id, "vehicle_count": int(ctx.family.vehicle_count),
            "target_id": task.target_id, "center_xy": [float(x) for x in S.tgt.center],
            "min_width_m": float(min(widths)), "argmin_row": int(widths.index(min(widths))), "rows": rows}


def stress_selection(entries, *, data_root, cache_dir, log=_log):
    from v08.scene.context import load_context
    fams = []
    for e in sorted(entries, key=lambda x: x["order"]):
        ctx = load_context(e, data_root=Path(data_root), cache_dir=Path(cache_dir))
        t0 = time.perf_counter()
        nb = narrow_band(ctx, e)
        nb["wall_s"] = time.perf_counter() - t0
        fams.append(nb)
        log(f"窄带 o{nb['order']:02d} n={nb['vehicle_count']} target={nb['target_id']} min={nb['min_width_m']:.1f} m")
    ranked = sorted(fams, key=lambda f: (-f["vehicle_count"], f["min_width_m"], f["order"]))
    chosen = ranked[:STRESS_FAMILIES]
    cases = [{"order": f["order"], "prior": p, "seed": s,
              "contract_id": f"stress_o{f['order']:02d}_{p}_s{s}"}
             for f in chosen for p in STRESS_PRIORS for s in STRESS_SEEDS]
    return {"rule": "(-vehicle_count, 窄带最小宽度升序, order)；前 4 族 × (abreast, column, echelon) × branch (0,1,2)",
            "families": fams, "ranking": [f["order"] for f in ranked], "chosen": [f["order"] for f in chosen],
            "cases": cases}


def _stress_batch(entries, cases, *, kind, data_root, cache_dir, out_dir, workers, log=_log):
    import v15_memory as VM
    from v08.runner import joint_monitoring as JM
    from v08.runner.monitoring import write_json
    for k in THREAD_VARS:
        os.environ[k] = "1"
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=False)
    by_order = {int(e["order"]): e for e in entries}
    cache_before = cache_state(cache_dir)
    # 派发成本：实际全员人数 × 地图边长；顺序不进入 RNG
    tasks = sorted(cases, key=lambda c: (-by_order[c["order"]]["vehicle_count"] * float(by_order[c["order"]]["map_side_m"]),
                                         c["order"], STRESS_PRIORS.index(c["prior"]), c["seed"]))
    pool = [(kind, by_order[c["order"]], 0, c["seed"], str(data_root), str(cache_dir), str(out), float("inf"), c["prior"])
            for c in tasks]
    write_json(out / "dispatch_order.json", [c["contract_id"] for c in tasks], indent=1)
    sampler = VM.SystemSampler().start()
    t0 = time.time()

    def logm(msg, flush=True):
        sampler.mark("completion")
        log(msg)

    with _BoundPoolTask(stress_pool_task):
        rows, unsent = JM.run_pool_singles(pool, workers=workers, deadline=float("inf"), log=logm)
    wall = time.time() - t0
    mem = sampler.stop()
    rows.sort(key=lambda r: r["contract_id"])
    summary = {"kind": kind, "workers": workers, "cases": len(cases), "completed": len(rows), "unsent": unsent,
               "errors": [r["contract_id"] for r in rows if r.get("error")], "dispatch_wall_s": wall,
               "contract_busy_s": float(sum(r.get("wall_s") or 0.0 for r in rows)), "system_memory": mem,
               "cache_write_during_workers": cache_diff(cache_before, cache_state(cache_dir))}
    write_json(out / "records.json", rows, indent=1)
    write_json(out / "summary.json", summary, indent=1)
    return rows, summary


def stress_budget(rest, checkpoint_wall, workers):
    """T̂_R = max{Σ T_prior(c) / (W·0.9), max T_prior(c)}；没有对应检查点的项不猜 0，列为未能估计。"""
    est = [c for c in rest if checkpoint_wall.get(c["prior"]) is not None]
    unknown = [c["contract_id"] for c in rest if checkpoint_wall.get(c["prior"]) is None]
    if not est:
        return {"T_R_s": None if not rest else (0.0 if not unknown else None), "estimable": 0, "unestimable": unknown}
    tt = [checkpoint_wall[c["prior"]] for c in est]
    return {"T_R_s": max(sum(tt) / (workers * EFFICIENCY), max(tt)), "estimable": len(est), "unestimable": unknown,
            "sum_s": sum(tt), "max_s": max(tt), "workers": workers}


# ---------------------------------------------------------------- 模式驱动

def main(argv=None):
    args = build_parser().parse_args(argv)
    from v08.runner.monitoring import PathRejected, guard_path, load_entries, write_json
    data_root = Path(args.data_root)
    try:
        cache = guard_path(args.cache, label="缓存", data_root=data_root)
        if not args.select_to:
            out = guard_path(args.out, label="输出", data_root=data_root, must_not_exist=True)
    except PathRejected as exc:
        print(f"路径被拒绝：{exc}", file=sys.stderr)
        return 1
    entries = load_entries(args.devset)
    for k in THREAD_VARS:
        os.environ[k] = "1"
    if args.mode == "workers":
        if args.select_to:
            det = write_selection(args.baseline, args.select_to)
            print(json.dumps({k: det[k] for k in ("n_rows", "n_finite_positive", "p20_s", "p80_s", "keys")}))
            return 0 if det["keys"] else 3
        if not args.keys or args.workers is None:
            print("workers 模式需要 --keys 与显式 --workers", file=sys.stderr)
            return 1
        sel = json.loads(Path(args.keys).read_text(encoding="utf-8"))
        if not sel.get("keys"):
            print("名单前提缺失（不足 40 或缺耗时）", file=sys.stderr)
            return 3
        s = run_selected(entries, sel["keys"], data_root=data_root, cache_dir=cache, out_dir=out, workers=args.workers,
                         baseline=Path(args.baseline))
        print(json.dumps({k: s[k] for k in ("workers", "completed", "missing", "errors", "dispatch_wall_s",
                                            "comparisons_all_bytes_equal")}, ensure_ascii=False))
        return 0 if s["comparisons_all_bytes_equal"] else 4
    if args.workers is None:
        print("未选定默认进程数，须显式 --workers", file=sys.stderr)
        return 1
    if args.mode == "production-quick":
        import hashlib
        from v08.runner import joint_monitoring as JM
        from v08.scene.context import load_context
        meta = []
        for e in entries:
            ctx = load_context(e, data_root=data_root, cache_dir=cache)
            meta += [JM.common_metadata(ctx, e, d) for d in range(JM.DRAWS)]
        sel = JM.select_quick(entries, meta)
        if sel is None:
            print("快速集覆盖不可满足", file=sys.stderr)
            return 3
        base = Path(args.baseline)
        present = [JM.contract_id({"order": o}, d) for o, d in sel if (base / "contracts" / JM.contract_id({"order": o}, d)).is_dir()]
        out.mkdir(parents=True, exist_ok=False)
        write_json(out / "quick_selection.json", {"selection": sel, "keys": [JM.contract_id({"order": o}, d) for o, d in sel],
                                                 "present_in_baseline": present, "common_metadata": meta}, indent=1)
        s = run_selected(entries, sel, data_root=data_root, cache_dir=cache, out_dir=out / "run", workers=args.workers,
                         baseline=base)
        comps = json.loads((out / "run" / "comparisons.json").read_text(encoding="utf-8"))
        hashes = {}
        for side, root in (("source", base), ("repeat", out / "run")):
            for c in comps:
                d = root / "contracts" / c["contract_id"]
                h = hashlib.sha256()
                for p in sorted(d.rglob("*")):
                    if p.is_file():
                        h.update(p.relative_to(d).as_posix().encode("utf-8") + b"\0" + p.read_bytes())
                hashes.setdefault(side, {})[c["contract_id"]] = h.hexdigest()
        doc = {"workers": args.workers, "keys": [JM.contract_id({"order": o}, d) for o, d in sel],
               "baseline": str(base.resolve()), "repeat": str((out / "run").resolve()), "comparisons": comps,
               "all_bytes_equal": s["comparisons_all_bytes_equal"], "dir_digest_sha256": hashes,
               "summary": {k: s[k] for k in ("completed", "missing", "errors", "dispatch_wall_s", "wall_with_prewarm_s",
                                             "cache_write_during_workers")},
               "exclusions": [], "note": "合同内排除清单为空；失败合同也比较"}
        write_json(out / "production_reproduction.json", doc, indent=1)
        print(json.dumps({"all_bytes_equal": doc["all_bytes_equal"], "n": len(comps)}))
        return 0 if doc["all_bytes_equal"] else 4
    sroot = Path(args.stress_root) if args.stress_root else None
    if args.mode == "stress-skeleton":
        from v08.runner import joint_monitoring as JM
        out.mkdir(parents=True, exist_ok=False)
        ordered = sorted(entries, key=lambda e: e["order"])
        pre = JM.prewarm_cache(ordered, data_root=data_root, cache_dir=cache)
        write_json(out / "prewarm.json", pre, indent=1)
        sel = stress_selection(entries, data_root=data_root, cache_dir=cache)
        write_json(out / "stress_selection.json", sel, indent=1)       # 名单在第一次运行前落盘
        manifest = []
        from v08.scene.context import load_context
        for o in sel["chosen"]:
            e = next(x for x in entries if int(x["order"]) == o)
            ctx = load_context(e, data_root=data_root, cache_dir=cache)
            for p in STRESS_PRIORS:
                for sd in STRESS_SEEDS:
                    c = make_stress_case(ctx, e, prior=p, seed=sd)
                    manifest.append({"contract_id": c["contract_id"], "source": c["source"],
                                     "member_ids": list(c["mission"].groups[0].member_ids),
                                     "group_id": c["mission"].groups[0].group_id})
        write_json(out / "stress_manifest.json", manifest, indent=1)
        rows, summ = _stress_batch(entries, sel["cases"], kind="stress_skeleton", data_root=data_root, cache_dir=cache,
                                   out_dir=out / "run", workers=args.workers)
        print(json.dumps({k: summ[k] for k in ("completed", "errors", "dispatch_wall_s")}))
        return 0 if not summ["errors"] else 3
    if args.mode == "stress-checkpoint":
        skel = json.loads((sroot / "skeleton" / "run" / "records.json").read_text(encoding="utf-8"))
        sel = json.loads((sroot / "skeleton" / "stress_selection.json").read_text(encoding="utf-8"))
        by_bucket = {}
        for r in skel:
            by_bucket.setdefault((r["order"], r["prior"]), []).append(r)
        skipped = sorted(f"o{o:02d}/{p}" for (o, p), rs in by_bucket.items() if not any(x.get("success") for x in rs))
        cps = []
        for p in STRESS_PRIORS:
            ok = sorted([r for r in skel if r["prior"] == p and r.get("success")], key=lambda r: (r["order"], r["seed"]))
            if ok:
                r = ok[0]
                cps.append({"order": r["order"], "prior": p, "seed": r["seed"], "contract_id": r["contract_id"]})
        out.mkdir(parents=True, exist_ok=False)
        write_json(out / "checkpoint_plan.json", {"skipped_all_skeleton_failed": skipped, "checkpoints": cps,
                                                  "priors_without_skeleton_success":
                                                      [p for p in STRESS_PRIORS if p not in {c["prior"] for c in cps}]},
                   indent=1)
        w = min(CHECKPOINT_MAX_WORKERS, args.workers, max(1, len(cps)))
        rows, summ = _stress_batch(entries, cps, kind="stress", data_root=data_root, cache_dir=cache,
                                   out_dir=out / "run", workers=w)
        cw = {r["prior"]: r["wall_s"] for r in rows if not r.get("error")}
        skipped_set = set(skipped)
        done = {c["contract_id"] for c in cps}
        rest = [c for c in sel["cases"] if c["contract_id"] not in done
                and f"o{c['order']:02d}/{c['prior']}" not in skipped_set]
        plan = {"checkpoint_workers": w, "checkpoint_wall_s": cw, "W_star": args.workers, "initial_rest": len(rest)}
        b0 = stress_budget(rest, cw, args.workers)
        plan["estimate_initial"] = b0
        reduced = list(rest)
        steps = []
        if b0["T_R_s"] is not None and b0["T_R_s"] > STRESS_BUDGET_S:
            reduced = [c for c in reduced if c["seed"] != 2]
            b1 = stress_budget(reduced, cw, args.workers)
            steps.append({"step": "seeds 3→2", "estimate": b1})
            if b1["T_R_s"] is not None and b1["T_R_s"] > STRESS_BUDGET_S:
                keep = set(sel["chosen"][:3])
                reduced = [c for c in reduced if c["order"] in keep]
                b2 = stress_budget(reduced, cw, args.workers)
                steps.append({"step": "families 4→3", "estimate": b2})
        plan["reduction_steps"] = steps
        plan["rest"] = reduced
        plan["dropped"] = [c["contract_id"] for c in rest if c not in reduced]
        plan["executed_checkpoints_outside_reduced"] = [c["contract_id"] for c in cps
                                                         if steps and ((c["seed"] == 2) or
                                                                       (len(steps) > 1 and c["order"] not in sel["chosen"][:3]))]
        plan["final_estimate"] = stress_budget(reduced, cw, args.workers)
        plan["still_over_budget"] = bool(plan["final_estimate"]["T_R_s"] is not None
                                         and plan["final_estimate"]["T_R_s"] > STRESS_BUDGET_S)
        write_json(out / "rest_plan.json", plan, indent=1)
        print(json.dumps({"checkpoints": [c["contract_id"] for c in cps], "wall": cw, "rest": len(reduced),
                          "estimate": plan["final_estimate"]}, ensure_ascii=False))
        return 0
    if args.mode == "stress-rest":
        plan = json.loads((sroot / "checkpoint" / "rest_plan.json").read_text(encoding="utf-8"))
        out.mkdir(parents=True, exist_ok=False)
        rows, summ = _stress_batch(entries, plan["rest"], kind="stress", data_root=data_root, cache_dir=cache,
                                   out_dir=out / "run", workers=args.workers)
        print(json.dumps({k: summ[k] for k in ("completed", "errors", "dispatch_wall_s")}))
        return 0 if not summ["errors"] else 3
    return 1


if __name__ == "__main__":
    sys.exit(main())
