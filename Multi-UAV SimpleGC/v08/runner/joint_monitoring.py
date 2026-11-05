"""V8-13 运行器（指令 4.2–4.4、5.1）：唯一 20 次全链路预算、快速集选择、端到端、进程调度、确定性输出。

一个合同：固定一次 sample_common(family, draw)、一次 monitoring_mission(ctx, common)；每个 attempt 只递增
RngKey.attempt（没有进程号、墙钟、hash() 或完成顺序参与）。attempt 顺序：
plan_attempt（随机骨架）→ optimize_segment（全体成员固定时间联合求解一次 + 全部语义硬检查）→
每编组 run_tracking_group 一次（V8-14c；与逐成员 run_tracking_segment 逐位相同；任一超时拒收）→ stitch → verify_segments → visible_track + check_validity。
全部通过才 success；否则记失败码与原始对象进入下一 attempt。20 次预算贯穿上述全链路；不调用 plan_segment，
不嵌套第二层预算，不在优化器内多次求解择优。

本模块导入时不读数据、不建目录、不启动批量任务。
"""
import hashlib
import json
import math
import os
import time
import traceback
from dataclasses import replace
from itertools import combinations
from pathlib import Path

import numpy as np

from . import joint_report as JR
from .monitoring import canonical_json, guard_path, jsonable, load_entries, write_json
from .runtime_defaults import DEFAULT_WORKERS

BUDGET = 20                 # U D.3.2；geometry.shape_attempts
QUICK_FAMILIES = 10         # U D.3.3
QUICK_PER_FAMILY = 2        # U D.3.3
LOW_SPEED_M_S = 5.5         # U D.3.3：初始指令速度 < 5.5 的合同至少 2 个
DRAWS = 5


# ---------------------------------------------------------------- 唯一预算

def run_attempts(key, attempt_fn, *, budget=BUDGET, should_stop=None):
    """attempt_fn(key_with_attempt) -> {"ok":bool, "stage":str, ...}
    返回 {"success":bool, "attempts":int, "records":list, "result":object}；首次成功报告 attempts=1。
    should_stop()（第 5 部分墙钟预算）为真时在下一 attempt 前合作退出，返回 incomplete=True（不是成功也不是预算耗尽）。"""
    records = []
    for a in range(int(budget)):
        if should_stop is not None and should_stop():
            return {"success": False, "attempts": len(records), "records": records, "result": None,
                    "incomplete": True}
        rec = attempt_fn(replace(key, attempt=a))
        records.append(rec)
        if rec.get("ok"):
            return {"success": True, "attempts": a + 1, "records": records, "result": rec}
    return {"success": False, "attempts": len(records), "records": records, "result": None}


# ---------------------------------------------------------------- 快速集（公共抽签元数据，不规划选样）

def common_metadata(ctx, entry, draw):
    from ..contract.monitoring import monitoring_mission
    from ..sampler.common import sample_common
    common = sample_common(ctx.family, draw)
    mission = monitoring_mission(ctx, common)
    group = mission.groups[0]
    return {"family_id": entry["family_id"], "order": int(entry["order"]), "draw_index": int(draw),
            "facility_count": int(entry["facility_count"]), "vehicle_count": int(entry["vehicle_count"]),
            "initial_speed_m_s": float(group.speed_profile.initial_speed_m_s),
            "group_size": len(group.member_ids), "target_id": mission.tasks[0].target_id}


def select_quick(entries, common_records):
    """10 族、每族恰 2 个 draw；设施数 1/2/3 各 ≥ 2 合同、含 vehicle_count 最大族（并列取 order 最小）、
    初始指令速度 < 5.5 的合同 ≥ 2。按 order 动态规划，状态（已选族数, 三个设施档合同数各截到 2, 低速数截到 2,
    最大族是否入选），每状态只留 (order, draw) 列表字典序最小者；返回第一个可行列表或 None（覆盖不可满足）。"""
    ordered = sorted(entries, key=lambda e: e["order"])
    largest = min(ordered, key=lambda e: (-e["vehicle_count"], e["order"]))["family_id"]
    by_fam = {}
    for r in common_records:
        by_fam.setdefault(r["family_id"], {})[int(r["draw_index"])] = r
    states = {(0, 0, 0, 0, 0, False): []}
    for e in ordered:
        fid = e["family_id"]
        draws = by_fam.get(fid, {})
        new = dict(states)
        for st, lst in states.items():
            n, f1, f2, f3, low, big = st
            if n >= QUICK_FAMILIES:
                continue
            for a, b in combinations(sorted(draws), QUICK_PER_FAMILY):
                ra, rb = draws[a], draws[b]
                fc = [f1, f2, f3]
                k = int(e["facility_count"]) - 1
                if 0 <= k < 3:
                    fc[k] = min(2, fc[k] + 2)
                lw = min(2, low + sum(float(r["initial_speed_m_s"]) < LOW_SPEED_M_S for r in (ra, rb)))
                ns = (n + 1, fc[0], fc[1], fc[2], lw, big or fid == largest)
                cand = lst + [(int(e["order"]), a), (int(e["order"]), b)]
                if ns not in new or cand < new[ns]:
                    new[ns] = cand
        states = new
    goal = (QUICK_FAMILIES, 2, 2, 2, 2, True)
    return states.get(goal)


# ---------------------------------------------------------------- 单个 attempt

def _member_reference(tr):
    from ..sim.tracking import TimeReference
    return TimeReference(tr.member_id, float(tr.release_s), float(tr.end_s), float(tr.altitude_m), tr.pva)


def _fail(stage, t, **kw):
    return {"ok": False, "stage": stage, "timing": t, **kw}


def attempt_chain(ctx, group, task, states, key, settings, entry_flag=None):
    """一次全链路 attempt；返回 dict（ok/stage/timing/各阶段原始对象）。未捕获异常由调用方记录 traceback。
    V8-14 指令 5.2：在实际调用 optimize_segment 之前把 optimization_entered 置 True（entry_flag 同步记录，
    以便异常路径也携带该标记）。"""
    entry_flag = {} if entry_flag is None else entry_flag
    entry_flag["optimization_entered"] = False
    from ..criteria.segment import SegmentTask, verify_segments
    from ..criteria.validity import check_validity, visible_track
    from ..motion.optimize import optimize_segment
    from ..motion.plan import plan_attempt
    from ..sim.stitch import stitch
    from ..sim.tracking_batch import LAST_GROUP_STATS, run_tracking_group
    t = {"skeleton_s": 0.0, "optimize_s": 0.0, "simulation_s": 0.0, "verify_s": 0.0}
    t0 = time.perf_counter()
    plan = plan_attempt(ctx, group, task, states, (), key)
    t["skeleton_s"] = time.perf_counter() - t0
    try:
        from ..motion.intents.monitoring import last_attempt_timing
        t["skeleton_detail"] = last_attempt_timing()
    except ImportError:
        pass
    if plan.failure is not None:
        f = plan.failure
        return _fail("skeleton", t, plan=plan, code=f.code, reason=f.reason, feasible_set=f.feasible_set,
                     witness=f.witness, optimization_entered=False)
    t0 = time.perf_counter()
    entry_flag["optimization_entered"] = True
    opt = optimize_segment(ctx, plan, key, settings)
    t["optimize_s"] = time.perf_counter() - t0
    diag = opt["solution"].diagnostics
    t["nit"], t["nfev"] = diag.get("nit"), diag.get("nfev")
    if not opt["ok"]:
        return _fail(opt["stage"], t, plan=plan, opt=opt, code="candidate_rejected", reason=opt["reason"],
                     optimization_entered=True)
    t0 = time.perf_counter()
    # V8-14c 3.3：每个编组一次批量跟踪（与逐成员 run_tracking_segment 逐位相同，门禁 1–3）
    members_sorted = sorted(opt["solution"].references)
    results = run_tracking_group([_member_reference(opt["solution"].references[m]) for m in members_sorted],
                                 [states[m] for m in members_sorted], final=True)
    timeouts = [m for m, res in zip(members_sorted, results) if res.status != "ok"]
    t["simulation_s"] = time.perf_counter() - t0
    t["simulation_detail"] = dict(LAST_GROUP_STATS)
    if timeouts:
        return _fail("simulation", t, plan=plan, opt=opt, results=results, code="candidate_rejected",
                     reason="sim_timeout", members=timeouts, optimization_entered=True)
    t0 = time.perf_counter()
    tracks = stitch(results)
    release = {m: int(r.pieces[0].release_us) for m, r in zip(sorted(opt["solution"].references), results)}
    verdicts = verify_segments(ctx.scene, tracks, release, [SegmentTask(0, "monitoring", task.target_id)])
    seg_ok = all(v.passed for v in verdicts)
    visible = [visible_track(tracks[m], release[m]) for m in sorted(tracks)]
    valid = check_validity(ctx.scene, visible)
    t["verify_s"] = time.perf_counter() - t0
    out = {"plan": plan, "opt": opt, "results": results, "tracks": tracks, "release_us": release,
           "verdicts": verdicts, "validity": valid, "timing": t, "optimization_entered": True}
    if not seg_ok:
        return {"ok": False, "stage": "verify_segments", "code": "candidate_rejected",
                "reason": "segment_verification", **out}
    if not valid.passed:
        return {"ok": False, "stage": "validity", "code": "candidate_rejected", "reason": "validity", **out}
    return {"ok": True, "stage": "verified", **out}


def _attempt_summary(rec, key):
    t = rec.get("timing", {})
    s = {"attempt": key.attempt, "ok": bool(rec["ok"]), "stage": rec["stage"], "code": rec.get("code"),
         "reason": rec.get("reason"), "timing": t, "optimization_entered": rec.get("optimization_entered")}
    w = rec.get("witness") if isinstance(rec.get("witness"), dict) else {}
    s["skeleton_stage"] = w.get("stage", rec.get("feasible_set")) if rec["stage"] == "skeleton" else None
    s["shape_audit_failed"] = bool(w.get("shape_audit_failed", False)) if rec["stage"] == "skeleton" else False
    if "feasible_set" in rec:
        s["feasible_set"] = rec["feasible_set"]
        s["witness"] = jsonable(rec.get("witness"))
    plan = rec.get("plan")
    if plan is not None and plan.failure is None:
        from ..motion.intents.monitoring import draw_summary
        s["draw"] = jsonable(draw_summary(plan.proposal or {}, (plan.formation or {}).get("realized")))
    elif isinstance(rec.get("witness"), dict) and rec["witness"].get("draw") is not None:
        s["draw"] = jsonable(rec["witness"]["draw"])
    else:
        s["draw"] = None
    opt = rec.get("opt")
    if opt is not None:
        d = opt["solution"].diagnostics
        s["optimize"] = {k: jsonable(d.get(k)) for k in ("nit", "nfev", "message", "success", "value", "terms",
                                                       "max_abs_grad", "reference_deviation", "settings_sha256")}
        s["optimize"]["physical_failures"] = jsonable((d.get("physical") or {}).get("failures"))
        if opt.get("monitoring") is not None:
            s["optimize"]["monitoring_failures"] = jsonable(opt["monitoring"]["failures"])
    if rec.get("verdicts") is not None:
        s["segment_failures"] = jsonable([v.failures for v in rec["verdicts"]])
    if rec.get("validity") is not None:
        v = rec["validity"]
        s["validity"] = {"passed": v.passed, "codes": jsonable(v.codes), "min_separation_m": v.min_separation_m}
    if rec.get("traceback"):
        s["traceback"] = rec["traceback"]
    return s


# ---------------------------------------------------------------- 单合同

def contract_id(entry, draw, branch=None):
    return f"o{int(entry['order']):02d}_d{int(draw)}" + ("" if branch is None else f"_b{int(branch)}")


def run_contract(ctx, entry, draw, *, settings, branch=None, out_dir=None, should_stop=None, keep=None):
    """一个合同的完整链路与唯一 20 次预算。out_dir 给出时写 contracts/<id>/ 的确定性载荷。返回记录 dict。"""
    from ..contract.monitoring import initial_states, monitoring_mission
    from ..motion.plan import final_failure
    from ..sampler.common import sample_common
    from ..sampler.keys import RngKey
    common = sample_common(ctx.family, draw)
    mission = monitoring_mission(ctx, common)
    group, task = mission.groups[0], mission.tasks[0]
    states = initial_states(ctx.family, group.member_ids)
    key0 = RngKey(ctx.family.family_id, int(draw), "shape", mission=0, branch=branch, group=group.group_id, segment=0)
    summaries = []

    def attempt_fn(k):
        flag = {}
        try:
            rec = attempt_chain(ctx, group, task, states, k, settings, entry_flag=flag)
        except Exception as exc:                    # 实现异常不伪装成正常随机失败：保存 traceback
            rec = {"ok": False, "stage": "exception", "code": "implementation_error", "reason": repr(exc),
                   "traceback": traceback.format_exc(), "timing": {},
                   "optimization_entered": flag.get("optimization_entered")}
        summaries.append(_attempt_summary(rec, k))
        return rec

    out = run_attempts(key0, attempt_fn, should_stop=should_stop)
    opt_s = float(sum((s["timing"] or {}).get("optimize_s", 0.0) for s in summaries))
    cid = contract_id(entry, draw, branch)
    failure = None
    if out.get("incomplete"):
        failure = {"code": "incomplete_deadline", "reason": "第 5 部分 2 h 墙钟预算到期，合作退出",
                   "feasible_set": None, "witness": {"attempts_done": out["attempts"]}}
    elif not out["success"]:
        log = []
        for s in summaries:
            stage = s["stage"]
            if stage == "skeleton":
                w = s.get("witness") if isinstance(s.get("witness"), dict) else {}
                stage = w.get("stage", s.get("feasible_set"))
            log.append({"stage": stage})
        f = final_failure(ctx, group, task, log)
        failure = {"code": f.code, "reason": f.reason, "feasible_set": f.feasible_set, "witness": jsonable(f.witness)}
    rec = {"contract_id": cid, "family_id": ctx.family.family_id, "order": int(entry["order"]),
           "draw_index": int(draw), "branch": branch, "facility_count": int(entry["facility_count"]),
           "vehicle_count": int(ctx.family.vehicle_count), "lateral_spacing_m": float(ctx.family.lateral_spacing_m),
           "group_id": group.group_id, "member_ids": sorted(group.member_ids), "group_size": len(group.member_ids),
           "target_id": task.target_id, "initial_speed_m_s": float(group.speed_profile.initial_speed_m_s),
           "formation_prior": group.formation_prior, "success": bool(out["success"]), "attempts": out["attempts"],
           "optimization_s": opt_s, "failure": failure, "attempt_log": summaries,
           "settings_sha256": settings.get("_sha256"),
           "release_us": None, "retained_p0_ok": True}
    rec["incomplete"] = bool(out.get("incomplete", False))
    # V8-14 指令 5.2：按每个 attempt 的 optimization_entered 事件计数（不再由 stage != "skeleton" 推断）
    cnt = JR.attempt_counters(summaries)
    missing_flag = any(not s["ok"] and not isinstance(s.get("optimization_entered"), bool) for s in summaries)
    rec["post_optimization_failures"] = None if missing_flag else cnt["post_optimization_failures"]
    rec["skeleton_failures"] = cnt["skeleton_failures"]
    rec["unknown_attempts"] = cnt["unknown_attempts"]
    rec["shape_audit_failed_attempts"] = sum(1 for s in summaries if s.get("shape_audit_failed"))
    rec["draws"] = [s.get("draw") for s in summaries]
    rec["stage_timing"] = {k: float(sum((s["timing"] or {}).get(k, 0.0) for s in summaries))
                           for k in ("skeleton_s", "optimize_s", "simulation_s", "verify_s")}
    if out["success"]:
        res = out["result"]
        rec["release_us"] = {m: int(v) for m, v in sorted(res["release_us"].items())}
        rec["retained_p0_ok"] = _retained_p0(res)
        rec["deviation"] = member_deviation(res)
        rec["tracking"] = tracking_stats(res)
        try:                                        # V8-14 指令 4.3：只诊断；异常如实记录，不影响成功判定
            rec["phase_metrics"] = phase_diagnostics(res)
        except Exception:
            rec["phase_metrics"] = {"error": traceback.format_exc()}
        plan = res["plan"]
        rec["nominal_duration_s"] = float(plan.nominal_duration_s)
        rec["formation"] = {k: plan.formation.get(k) for k in ("prior", "start", "realized", "mapped_from_loose",
                                                                "lateral_step_m")}
        rec["topology"] = {k: plan.topology.get(k) for k in ("final", "laps", "traversals", "turn_kind", "prior_draw",
                                                              "forced", "forced_reason")}
        if keep is not None:
            keep["result"] = res
    if out_dir is not None:
        last = out["records"][-1] if (out["records"] and not out["success"]) else None
        save_contract(Path(out_dir), rec, out["result"], last_failed=last)
    return rec


def _retained_p0(res):
    """保留段 P0 门禁（指令 5.2）：段核验通过、实测间距 ≥ 2 m 与限制区（check_validity）、时间线无重复/空洞。"""
    if not all(v.passed for v in res["verdicts"]):
        return False
    if not res["validity"].passed:
        return False
    for tr in res["tracks"].values():
        d = np.diff(np.asarray(tr.tau_us, np.int64))
        if len(d) and not np.all(d == 100_000):
            return False
    return True


# ---------------------------------------------------------------- 确定性输出

def _json_bytes(obj):
    return canonical_json(obj) + b"\n"


def save_contract(out, rec, result, last_failed=None):
    """contracts/<id>/{contract.json,result.json}；成功另存 skeleton.json、optimized.json 与 tracks/<m>/*.npy。
    墙钟等遥测写在合同目录外的 telemetry/<id>.json，不参与确定性载荷。"""
    d = out / "contracts" / rec["contract_id"]
    d.mkdir(parents=True, exist_ok=False)
    contract = {k: rec[k] for k in ("contract_id", "family_id", "order", "draw_index", "branch", "facility_count",
                                    "vehicle_count", "group_id", "member_ids", "group_size", "target_id",
                                    "initial_speed_m_s", "formation_prior")}
    (d / "contract.json").write_bytes(_json_bytes(contract))
    det_attempts = []
    for s in rec["attempt_log"]:
        s2 = {k: v for k, v in s.items() if k not in ("timing", "traceback")}
        det_attempts.append(s2)
    result_doc = {"success": rec["success"], "attempts": rec["attempts"], "failure": rec["failure"],
                  "attempt_log": det_attempts, "release_us": rec["release_us"], "settings_sha256": rec["settings_sha256"],
                  "retained_p0_ok": rec["retained_p0_ok"], "incomplete": rec.get("incomplete", False),
                  "post_optimization_failures": rec["post_optimization_failures"],
                  "skeleton_failures": rec["skeleton_failures"], "unknown_attempts": rec["unknown_attempts"],
                  "shape_audit_failed_attempts": rec["shape_audit_failed_attempts"],
                  "deviation": rec.get("deviation"), "tracking": rec.get("tracking"),
                  "nominal_duration_s": rec.get("nominal_duration_s"), "formation": rec.get("formation"),
                  "topology": rec.get("topology"), "phase_metrics": rec.get("phase_metrics")}
    (d / "result.json").write_bytes(_json_bytes(result_doc))
    if result is not None and result.get("ok"):
        plan = result["plan"]
        from .monitoring import plan_to_record
        prec, arrays = plan_to_record(plan)
        prec["arrays"] = {k: np.asarray(v).tolist() for k, v in sorted(arrays.items())}
        (d / "skeleton.json").write_bytes(_json_bytes(prec))
        sol = result["opt"]["solution"]
        opt_doc = {"members": {m: {"release_s": t.release_s, "end_s": t.end_s, "altitude_m": t.altitude_m,
                                   "knots": t.knots, "controls": t.controls}
                               for m, t in sorted(sol.references.items())},
                   "lines": jsonable(result["opt"]["lines"]),
                   "lines_raw": jsonable(result["opt"].get("lines_raw")),
                   "diagnostics": {k: jsonable(sol.diagnostics.get(k)) for k in
                                   ("nit", "nfev", "message", "value", "terms", "max_abs_grad", "reference_deviation",
                                    "symmetry_break", "settings_sha256")}}
        (d / "optimized.json").write_bytes(_json_bytes(opt_doc))
        for m, tr in sorted(result["tracks"].items()):
            td = d / "tracks" / m
            td.mkdir(parents=True, exist_ok=False)
            for name in ("tau_us", "p", "v", "a", "segment_index"):
                np.save(td / f"{name}.npy", np.ascontiguousarray(getattr(tr, name)), allow_pickle=False)
    if last_failed is not None and last_failed.get("plan") is not None and last_failed["plan"].failure is None:
        # 失败合同最后一个 attempt 的骨架/优化曲线与违规见证（供失败示例图；确定性载荷）
        plan = last_failed["plan"]
        doc = {"stage": last_failed.get("stage"), "reason": last_failed.get("reason"),
               "skeleton_members": {m: np.asarray(mp.curve_xy, float).tolist() for m, mp in sorted(plan.members.items())}}
        opt = last_failed.get("opt")
        if opt is not None:
            sol = opt["solution"]
            doc["optimized"] = {m: {"release_s": t.release_s, "end_s": t.end_s, "knots": t.knots, "controls": t.controls}
                                for m, t in sorted(sol.references.items())}
            doc["physical_failures"] = jsonable((sol.diagnostics.get("physical") or {}).get("failures"))
            if opt.get("monitoring") is not None:
                doc["monitoring_failures"] = jsonable(opt["monitoring"]["failures"])
        if last_failed.get("tracks") is not None:
            doc["tracks_p"] = {m: np.asarray(tr.p, float)[:, :2].tolist() for m, tr in sorted(last_failed["tracks"].items())}
        if last_failed.get("validity") is not None:
            doc["validity_codes"] = jsonable(last_failed["validity"].codes)
        if last_failed.get("verdicts") is not None:
            doc["segment_failures"] = jsonable([v.failures for v in last_failed["verdicts"]])
        (d / "failure_witness.json").write_bytes(_json_bytes(doc))
    tele = out / "telemetry"
    tele.mkdir(exist_ok=True)
    (tele / f"{rec['contract_id']}.json").write_bytes(_json_bytes(
        {"timing": [s.get("timing") for s in rec["attempt_log"]], "optimization_s": rec["optimization_s"],
         "tracebacks": [s.get("traceback") for s in rec["attempt_log"] if s.get("traceback")]}))


# ---------------------------------------------------------------- 批次

def _record_row(rec):
    keys = ("contract_id", "family_id", "draw_index", "branch", "facility_count", "initial_speed_m_s", "group_size",
            "success", "attempts", "optimization_s", "retained_p0_ok", "member_ids", "target_id", "release_us",
            "failure", "order", "vehicle_count", "post_optimization_failures", "skeleton_failures", "draws",
            "unknown_attempts", "shape_audit_failed_attempts", "incomplete", "phase_metrics", "formation_prior",
            "formation", "topology", "deviation")
    row = {k: rec.get(k) for k in keys}
    # V8-14 8.7：逐 attempt 的进入事件与形状复核标记（精简，确定性；不含 timing/witness）
    row["attempt_log"] = [{k: a.get(k) for k in ("attempt", "ok", "stage", "skeleton_stage", "code",
                                                  "optimization_entered", "shape_audit_failed")}
                          for a in rec.get("attempt_log") or []]
    return row


def run_batch(entries, *, stage, data_root, cache_dir, out_dir, workers=DEFAULT_WORKERS, keys=None, settings=None,
              log=print):
    """keys: [(order, draw)]（快速集或复跑集）；None 表示全部 entries × draw 0..4。单进程顺序执行
    （workers>1 的进程池由第 5 部分接入）。按业务 key 排序写 records.json 与 summary.json。"""
    from ..motion.optimize import load_settings
    from ..scene.context import load_context
    out = Path(out_dir)
    settings = settings if settings is not None else load_settings()
    by_order = {int(e["order"]): e for e in entries}
    if keys is None:
        keys = [(int(e["order"]), d) for e in sorted(entries, key=lambda x: x["order"]) for d in range(DRAWS)]
    keys = sorted((int(o), int(d)) for o, d in keys)
    records = []
    ctx_cache = {}
    t0 = time.perf_counter()
    for o, d in keys:
        e = by_order[o]
        if o not in ctx_cache:
            ctx_cache.clear()
            ctx_cache[o] = load_context(e, data_root=data_root, cache_dir=cache_dir)
        rec = run_contract(ctx_cache[o], e, d, settings=settings, out_dir=out)
        records.append(rec)
        log(f"{rec['contract_id']}: success={rec['success']} attempts={rec['attempts']} "
            f"opt={rec['optimization_s']:.1f}s fail={(rec['failure'] or {}).get('code')}")
    rows = [_record_row(r) for r in sorted(records, key=lambda r: r["contract_id"])]
    write_json(out / "records.json", rows, indent=1)
    chk = JR.quick_checkpoint(rows) if stage == "quick" else None
    complete = (len(rows) == len(keys) and not any(r.get("incomplete") for r in rows)
                and not any(r.get("unknown_attempts") for r in rows)
                and not (chk or {}).get("metrics", {}).get("attempts_undetermined", False))
    summary = {"stage": stage, "expected_count": len(keys), "completed": len(rows), "complete": complete,
               "wall_s": time.perf_counter() - t0, "checkpoint": chk, "settings_sha256": settings.get("_sha256")}
    write_json(out / "summary.json", summary, indent=1)
    return summary


# ---------------------------------------------------------------- CLI 驱动

def cli(args, out):
    """quick：选快速集写 quick_selection.json，再跑完整链路；前提（权重配置）未完成时写前提状态并返回 3。"""
    import sys
    from ..motion.optimize import SettingsIncomplete, load_settings
    from ..scene.context import load_context
    if not (args.devset and args.data_root and args.cache):
        print("quick/full/diversity/rerun 需要 --devset --data-root --cache", file=sys.stderr)
        return 1
    data_root = Path(args.data_root)
    cache = guard_path(args.cache, label="缓存", data_root=data_root)
    entries = load_entries(args.devset)
    out.mkdir(parents=True, exist_ok=False)
    if args.stage == "quick":
        meta = []
        for e in entries:
            ctx = load_context(e, data_root=data_root, cache_dir=cache)
            for d in range(DRAWS):
                meta.append(common_metadata(ctx, e, d))
        sel = select_quick(entries, meta)
        doc = {"selection": sel, "keys": [contract_id({"order": o}, d) for o, d in (sel or [])],
               "common_metadata": meta, "rule": "指令 4.3 动态规划（字典序最小可行列表）"}
        write_json(out / "quick_selection.json", doc, indent=1)
        if sel is None:
            print("登记抽签本身不满足快速集覆盖（不生成第 6 个 draw 补足）", file=sys.stderr)
            return 3
        try:
            settings = load_settings()
        except SettingsIncomplete as exc:
            write_json(out / "summary.json", {"stage": "quick", "expected_count": len(sel), "completed": 0,
                                              "precondition": "incomplete", "reason": str(exc)}, indent=1)
            print(f"前提未完成：{exc}", file=sys.stderr)
            return 3
        summary = run_batch(entries, stage="quick", data_root=data_root, cache_dir=cache, out_dir=out, workers=1,
                            keys=sel, settings=settings)
        chk = summary["checkpoint"]
        print("检查点 2：", json.dumps(chk, ensure_ascii=False))
        if not summary["complete"]:                 # V8-14：缺数据/未知进入标志 = 未完成，不走"triggered 为空即 0"
            return 3
        return 2 if chk["triggered"] else 0
    if args.stage == "full":
        summary = full_stage(entries, data_root=data_root, cache_dir=cache, out_dir=out, workers=args.workers)
        try:
            figs = JR.make_figures(out, entries, data_root=data_root, cache_dir=cache, fig_dir=out / "figures")
            write_json(out / "figures.json", figs, indent=1)
        except Exception:
            (out / "figures_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        chk = summary["checkpoint"]
        print("全量诊断：", json.dumps(chk, ensure_ascii=False))
        if not summary["complete"]:
            return 3
        return 2 if chk["triggered"] else 0
    if args.stage == "rerun":
        if not (args.keys and args.compare_to):
            print("rerun 需要 --keys 与 --compare-to", file=sys.stderr)
            return 1
        doc = rerun_stage(entries, data_root=data_root, cache_dir=cache, out_dir=out, keys_path=args.keys,
                          compare_to=args.compare_to)
        return 0 if doc["all_equal"] else 4
    print("多样性种子在 --stage full 内与全量共用 2 h 预算运行（指令 5.4），不单独运行", file=sys.stderr)
    return 1


# ================================================================ 第 5 部分：全量、复跑、多样性（指令 5.1–5.4）

WALL_BUDGET_S = 7200.0      # U D.6：第 5 部分超过 2 小时在已完成处汇报（monitoring.simulation_wall_budget_s）
DIVERSITY_SEEDS = 10        # U D.4；r4 14.3
FRECHET_SPACING_M = 5.0     # C12 第 7 条


def member_deviation(res):
    """逐成员骨架→优化的水平偏离（同一绝对时刻、10 Hz、移动期 [release, end]）：max/mean；末端保持期按构造为 0。"""
    out = {}
    refs = {r.member_id: r for r in res["opt"]["references"]}
    for m, tr in sorted(res["opt"]["solution"].references.items()):
        r = refs[m]
        f0 = int(math.ceil(tr.release_s * 10 - 1e-9))
        f1 = int(math.floor(tr.end_s * 10 + 1e-9))
        t = np.arange(f0, f1 + 1, dtype=np.int64) / 10.0
        d = np.hypot(*(tr.evaluate(t) - np.asarray(r.pva(t)[0])).T)
        out[m] = {"max_m": float(d.max()) if len(d) else 0.0, "mean_m": float(d.mean()) if len(d) else 0.0}
    return out


def phase_diagnostics(res):
    """V8-14 指令 4.3 / 裁定 7：逐成员 汇合/进入、巡逻、撤离 三阶段的参考/优化/实测速度与沿迹偏离（只诊断）。
    阶段按该成员实际巡逻站点（member_map_v14.patrol_member_s）的名义时间切分；汇合/进入 = [release, 首巡逻站点)、
    巡逻 = [首, 末巡逻站点)、撤离 = [末巡逻站点, 名义运动结束]（最后阶段含终点）。网格为实测 10 Hz 帧
    （tau_us 与 TimeReference 同一时钟；release_us − release_s 的取整差另记），collect 时刻作子标记。"""
    from ..diagnostics.monitoring_skeleton import phase_metrics
    plan, opt = res["plan"], res["opt"]
    mm = (plan.witnesses or {}).get("member_map_v14") or {}
    refs = {r.member_id: r for r in opt["references"]}
    sol = opt["solution"].references
    out = {}
    for m in sorted(sol):
        maps = opt["maps"][m]
        nom = maps["nominal"]
        cs, ta = np.asarray(maps["curve_s"], float), np.asarray(maps["t_abs"], float)
        ref = refs[m]
        mp = (mm.get("members") or {}).get(m)
        if mp is None:
            out[m] = {"error": "missing member_map_v14"}
            continue
        pa, pb = mp["patrol_member_s"]
        t_pa, t_pb = float(np.interp(pa, cs, ta)), float(np.interp(pb, cs, ta))
        t_c = float(np.interp(float(mp["member_s"][0]), cs, ta))
        tr = res["tracks"][m]
        t = np.asarray(tr.tau_us, np.int64) / 1e6
        sel = (t >= ref.release_s - 1e-9) & (t <= ref.end_s + 1e-9)
        t = t[sel]
        rp, rv, _ = ref.pva(t)
        rp, rv = np.asarray(rp, float).reshape(-1, 2), np.asarray(rv, float).reshape(-1, 2)
        s_now = np.interp(t, ta, cs)
        tan_c = np.asarray(nom.curve.tangent, float)
        idx = np.clip(np.searchsorted(cs, s_now, side="right") - 1, 0, len(tan_c) - 1)
        sp = np.hypot(rv[:, 0], rv[:, 1])
        tan = np.where((sp > 0.0)[:, None], rv / np.maximum(sp, np.finfo(float).tiny)[:, None], tan_c[idx])
        op, ov = sol[m].evaluate(t, 0), sol[m].evaluate(t, 1)
        mpv, mvv = np.asarray(tr.p, float)[sel, :2], np.asarray(tr.v, float)[sel, :2]
        bounds = {"collect_ingress": (ref.release_s, t_pa), "patrol": (t_pa, t_pb), "egress": (t_pb, ref.end_s, True)}
        got = phase_metrics(t, rp, rv, op, ov, mpv, mvv, bounds, tan)
        out[m] = {"phases": got, "t_collect_s": t_c, "t_patrol_s": (t_pa, t_pb),
                  "release_offset_s": float(res["release_us"][m]) / 1e6 - float(ref.release_s)}
    return out


def tracking_stats(res):
    out = {}
    for r in res["results"]:
        rec = r.pieces[0]
        d10 = np.diff(np.asarray(r.a)[:, :2], axis=0) / 0.1
        out[r.member_id] = {"max_step_pos_err_m": rec.max_step_pos_err_m, "max_frame_pos_err_m": rec.max_frame_pos_err_m,
                            "max_core_jerk_xy": float(rec.step_jerk_xy.max()) if len(rec.step_jerk_xy) else 0.0,
                            "max_core_accel_xy": float(rec.step_accel_xy.max()) if len(rec.step_accel_xy) else 0.0,
                            "max_10hz_diff_jerk_xy": float(np.linalg.norm(d10, axis=1).max()) if len(d10) else 0.0,
                            "tube_exceeded_0p5": bool(rec.max_step_pos_err_m > 0.5)}
    return out


def group_reference_curves(ctx, group, res):
    """V8-14 指令 5.1：巡逻段编组参考（第一个到最后一个巡逻站点，精确插入两端点）。
    c_after(s) = c_before(s) + (1/N)Σ_i[p_i^opt(t_i(s)) − p_i^ref(t_i(s))]；c_before 为构造时保存的编组参考
    （plan.reference_xy，参考弧长 = collect_s + 累计弧长），t_i(s) 由构造时保存的 member_map_v14
    （reference_s → member_s）与该成员名义弧长—时间给出，不再用常数槽位重建。返回 (before, after) 两条
    分别按自己的几何弧长 5 m 重采样的巡逻段折线。"""
    from ..diagnostics.monitoring_skeleton import patrol_resample
    from ..motion.nominal import member_nominal
    from ..motion.skeleton import NominalPVA, reference_guidance
    plan = res["plan"]
    ref_xy = np.asarray(plan.reference_xy, float)
    a = plan.anchors
    s_ref = float(a["collect_s"]) + np.r_[0.0, np.cumsum(np.hypot(*np.diff(ref_xy, axis=0).T))]
    ps, pe = float(a["patrol_start_s"]), float(a["patrol_end_s"])
    inner = s_ref[(s_ref > ps) & (s_ref < pe)]
    S = np.r_[ps, inner, pe]
    before = np.stack([np.interp(S, s_ref, ref_xy[:, 0]), np.interp(S, s_ref, ref_xy[:, 1])], axis=1)
    mm = plan.witnesses["member_map_v14"]["members"]
    G = reference_guidance()
    disp = np.zeros_like(before)
    opt = res["opt"]["solution"].references
    for m in sorted(plan.members):
        mp = mm[m]
        sm = np.interp(S, np.asarray(mp["reference_s"], float), np.asarray(mp["member_s"], float))
        nom = member_nominal(plan.members[m], guidance=G)
        f = NominalPVA(nom)
        t = np.interp(sm, nom.curve.s, nom.t_nodes) + nom.release_s
        disp += opt[m].evaluate(t) - np.asarray(f(t)[0])
    after = before + disp / len(plan.members)
    return (patrol_resample(S, before, ps, pe, spacing_m=FRECHET_SPACING_M),
            patrol_resample(S, after, ps, pe, spacing_m=FRECHET_SPACING_M))


def _pool_task(task):
    """一个合同（全量或多样性种子）的工作进程入口；按族缓存上下文，不跨进程共享随机流。"""
    import time as _t
    from ..motion.optimize import load_settings
    from ..scene.context import load_context
    from ..diagnostics.diversity import resample_polyline
    kind, entry, draw, branch, data_root, cache_dir, out_dir, deadline = task[:8]
    g = globals().setdefault("_WCTX", {})
    if entry["order"] not in g:
        # V8-14c 3.4：缓存已在派发前由单进程预建，worker 只读；上下文按最近使用保留 3 个（任务不再按族成组）
        while len(g) >= 3:
            g.pop(next(iter(g)))
        g[entry["order"]] = load_context(entry, data_root=Path(data_root), cache_dir=Path(cache_dir))
    else:
        g[entry["order"]] = g.pop(entry["order"])
    ctx = g[entry["order"]]
    settings = load_settings()
    t0 = _t.perf_counter()
    try:
        holder = {}
        rec = run_contract(ctx, entry, draw, settings=settings, branch=branch, out_dir=Path(out_dir),
                           should_stop=lambda: _t.time() > deadline, keep=holder)
        row = _record_row(rec)
        row.update(kind=kind, incomplete=rec.get("incomplete", False), wall_s=_t.perf_counter() - t0,
                   lp_seconds=[((a.get("timing") or {}).get("skeleton_detail") or {}).get("lp_seconds")
                               for a in rec["attempt_log"]],
                   attempt_log_flags=[{"ok": a["ok"], "stage": a["stage"], "optimization_entered": a.get("optimization_entered"),
                                       "shape_audit_failed": a.get("shape_audit_failed")} for a in rec["attempt_log"]],
                   deviation=rec.get("deviation"), tracking=rec.get("tracking"),
                   nominal_duration_s=rec.get("nominal_duration_s"), formation=rec.get("formation"),
                   topology=rec.get("topology"), stage_timing=rec.get("stage_timing"),
                   attempt_stages=[a["stage"] for a in rec["attempt_log"]],
                   nit=[(a.get("timing") or {}).get("nit") for a in rec["attempt_log"]])
        if kind == "diversity" and rec["success"]:
            from ..contract.monitoring import monitoring_mission
            from ..sampler.common import sample_common
            group = monitoring_mission(ctx, sample_common(ctx.family, draw)).groups[0]
            before, after = group_reference_curves(ctx, group, holder["result"])   # 已按各自弧长 5 m 重采样
            row["curve_before"] = before.tolist()
            row["curve_after"] = after.tolist()
        row["lateral_spacing_m"] = float(ctx.family.lateral_spacing_m)
        return row
    except Exception as exc:
        return {"contract_id": contract_id(entry, draw, branch), "family_id": entry["family_id"], "kind": kind,
                "draw_index": draw, "branch": branch, "success": False, "attempts": None,
                "error": repr(exc), "traceback": traceback.format_exc()}


def _pool_family_task(ftask):
    """同一族的全部合同（全量 draw 与多样性种子）在同一进程内顺序执行：V8-12 的场景缓存只按单进程设计，
    不同进程并行处理同一族会在 Windows 上争用同一缓存文件的原子替换（第一次全量的 23 次 PermissionError）。"""
    import time as _t
    rows = []
    for t in ftask:
        if _t.time() > t[-1]:
            rows.append({"contract_id": contract_id(t[1], t[2], t[3]), "family_id": t[1]["family_id"], "kind": t[0],
                         "draw_index": t[2], "branch": t[3], "success": False, "attempts": 0, "unsent": True})
            continue
        rows.append(_pool_task(t))
    return rows


def run_pool(tasks, *, workers, deadline, log=print):
    """固定顺序派发；到 deadline 停止派发，进行中的合同在下一 attempt 前合作退出。返回 (rows, 未派发 keys)。"""
    import multiprocessing as mp
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
    rows, pending, unsent = [], set(), []
    it = iter(tasks)
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
        def submit_next():
            for t in it:
                if time.time() > deadline:
                    unsent.extend(contract_id(x[1], x[2], x[3]) for x in t)
                    continue
                pending.add(ex.submit(_pool_family_task, t))
                return True
            return False
        for _ in range(workers):
            if not submit_next():
                break
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                pending.discard(fut)
                for row in fut.result():
                    if row.get("unsent"):
                        unsent.append(row["contract_id"])
                        continue
                    rows.append(row)
                    log(f"[{len(rows)}] {row['contract_id']} {row.get('kind')}: success={row.get('success')} "
                        f"attempts={row.get('attempts')} incomplete={row.get('incomplete')} "
                        f"wall={row.get('wall_s', 0):.0f}s err={row.get('error')}")
                submit_next()
    return rows, unsent


def compare_dirs(source, repeat):
    src = {p.relative_to(source).as_posix() for p in Path(source).rglob("*") if p.is_file()}
    rep = {p.relative_to(repeat).as_posix() for p in Path(repeat).rglob("*") if p.is_file()}
    same = src == rep and all((Path(source) / n).read_bytes() == (Path(repeat) / n).read_bytes() for n in src)
    diff = sorted(n for n in src & rep if (Path(source) / n).read_bytes() != (Path(repeat) / n).read_bytes())
    return {"files": sorted(src), "file_sets_equal": src == rep, "bytes_equal": same, "differing": diff,
            "only_source": sorted(src - rep), "only_repeat": sorted(rep - src)}


def frechet_blocks(div_rows, key="curve_after"):
    from ..diagnostics.diversity import discrete_frechet
    fam = {}
    for r in div_rows:
        fam.setdefault(r["family_id"], []).append(r)
    blocks = []
    for fid, rs in sorted(fam.items()):
        ok = [np.asarray(r[key], float) for r in sorted(rs, key=lambda x: x["branch"]) if r.get("success") and key in r]
        pairs = [(i, j) for i in range(len(ok)) for j in range(i + 1, len(ok))]
        d = [float(discrete_frechet(ok[i], ok[j])) for i, j in pairs]
        from ..diagnostics.monitoring_skeleton import endpoint_distances
        ends = [endpoint_distances(ok[i], ok[j]) for i, j in pairs]     # 巡逻起/终点距离：单独报告，不从 Fréchet 扣除
        blocks.append({"family_id": fid, "spacing_m": float(rs[0].get("lateral_spacing_m") or 0.0) or 1.0,
                       "distances_m": d, "attempted": len(rs), "success": len(ok), "endpoint_m": ends,
                       "scope": "patrol_segment_v14"})
    return blocks


def prewarm_cache(ordered, *, data_root, cache_dir, log=print):
    """V8-14c 3.4.1：单进程为 40 族建好场景上下文与全部几何的原始距离场（世界、障碍、各设施警戒/预警层；
    以每个设施作目标的完整巡逻约束覆盖），并取各 draw 第 0 编组人数作派发成本。返回统计。"""
    from ..contract.monitoring import monitoring_mission
    from ..motion.intents.monitoring import monitoring_constraints
    from ..sampler.common import sample_common
    from ..scene.context import load_context
    t0 = time.time()
    misses = hits = 0
    sizes = {}
    for e in ordered:
        ctx = load_context(e, data_root=Path(data_root), cache_dir=Path(cache_dir))
        for f in ctx.facilities:
            cons = monitoring_constraints(ctx, f.id)
            ctx.field(("prewarm", f.id), cons["base"] + cons["patrol"])
        ctx.field("route", list(monitoring_constraints(ctx, ctx.facilities[0].id)["base"]))
        st = ctx.cache_stats()
        misses += st["misses"]
        hits += st["hits"]
        for d in range(DRAWS):
            g = monitoring_mission(ctx, sample_common(ctx.family, d)).groups[0]
            sizes[f"{int(e['order'])}:{d}"] = len(g.member_ids)
    out = {"families": len(ordered), "raw_cache_hits": hits, "raw_cache_misses_written": misses,
           "group_size": sizes, "wall_s": time.time() - t0}
    log(f"预建缓存：{len(ordered)} 族，命中 {hits}，新写 {misses}，{out['wall_s']:.0f}s")
    return out


def run_pool_singles(tasks, *, workers, deadline, log=print):
    """V8-14c 3.4.2：单合同任务动态派发（一次提交一个，worker 空闲即取下一个）；到 deadline 停止派发，
    进行中的合同在下一 attempt 前合作退出。返回 (rows, 未派发 contract_id)。"""
    import multiprocessing as mp
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
    rows, pending, unsent = [], set(), []
    it = iter(tasks)
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
        def submit_next():
            for t in it:
                if time.time() > deadline:
                    unsent.append(contract_id(t[1], t[2], t[3]))
                    continue
                pending.add(ex.submit(_pool_task, t))
                return True
            return False
        for _ in range(workers):
            if not submit_next():
                break
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                pending.discard(fut)
                row = fut.result()
                rows.append(row)
                log(f"[{len(rows)}] {row['contract_id']} {row.get('kind')}: success={row.get('success')} "
                    f"attempts={row.get('attempts')} incomplete={row.get('incomplete')} "
                    f"wall={row.get('wall_s', 0):.0f}s err={row.get('error')}", flush=True)
                submit_next()
    return rows, unsent


def full_stage(entries, *, data_root, cache_dir, out_dir, workers, log=print):
    """全量 200 合同 + 多样性 10 族 × 10 种子，共用 2 小时预算；复跑键在开始前写 rerun_keys.json。"""
    from .monitoring import select_diversity_families
    out = Path(out_dir)
    t_start = time.time()
    deadline = t_start + WALL_BUDGET_S
    ordered = sorted(entries, key=lambda e: e["order"])
    keys = [(int(e["order"]), d) for e in ordered for d in range(DRAWS)]
    write_json(out / "rerun_keys.json", {"keys": [list(k) for k in keys[:5]],
                                         "rule": "全量开始前按 (order, draw) 字典序取前 5 个合同"}, indent=1)
    by_order = {int(e["order"]): e for e in entries}
    div_fams = select_diversity_families(entries)
    div_orders = {int(e["order"]) for e in div_fams}
    (out / "diversity").mkdir()
    fam_tasks = []
    for e in ordered:
        o = int(e["order"])
        ft = [("full", e, d, None, str(data_root), str(cache_dir), str(out), deadline) for d in range(DRAWS)]
        if o in div_orders:
            ft += [("diversity", e, 0, b, str(data_root), str(cache_dir), str(out / "diversity"), deadline)
                   for b in range(DIVERSITY_SEEDS)]
        fam_tasks.append(ft)
    # V8-14c 3.4：派发前单进程预建全部场景上下文与距离场缓存（之后 worker 只读）；合同与多样性种子一律单任务、
    # 按预计成本（第 0 编组人数 × 地图边长）降序、动态分配、chunksize = 1。派发顺序与结果无关（输出按业务键）。
    prewarm = prewarm_cache(ordered, data_root=data_root, cache_dir=cache_dir, log=log)
    write_json(out / "prewarm.json", prewarm, indent=1)
    t_dispatch = time.time()
    deadline = t_dispatch + WALL_BUDGET_S
    singles = []
    for ft in fam_tasks:
        for t in ft:
            e, d = t[1], t[2]
            size = prewarm["group_size"][f"{int(e['order'])}:{int(d)}"]
            cost = size * float(e["map_side_m"])
            singles.append((cost, (t[0] != "full"), int(e["order"]), int(d), -1 if t[3] is None else int(t[3]),
                            t[:7] + (deadline,)))
    singles.sort(key=lambda x: (-x[0], x[1], x[2], x[3], x[4]))
    write_json(out / "dispatch_order.json", [{"kind": x[5][0], "order": x[2], "draw": x[3], "branch": x[5][3],
                                             "cost": x[0]} for x in singles], indent=1)
    rows, unsent = run_pool_singles([x[5] for x in singles], workers=workers, deadline=deadline, log=log)
    full_rows = sorted([r for r in rows if r.get("kind") == "full"], key=lambda r: r["contract_id"])
    div_rows = sorted([r for r in rows if r.get("kind") == "diversity"], key=lambda r: r["contract_id"])
    write_json(out / "records.json", [{k: v for k, v in r.items() if k not in ("curve_before", "curve_after")}
                                      for r in full_rows], indent=1)
    write_json(out / "diversity" / "records.json", div_rows, indent=1)
    blocks_after = frechet_blocks(div_rows, "curve_after")
    blocks_before = frechet_blocks(div_rows, "curve_before")
    complete = (len(full_rows) == len(keys) and not unsent
                and not any(r.get("incomplete") or r.get("error") for r in full_rows)
                and not any(r.get("unknown_attempts") or (r.get("success") and r.get("post_optimization_failures") is None)
                            for r in full_rows))
    chk = JR.full_checkpoint([r for r in full_rows if not r.get("error")], blocks_after) if full_rows else None
    summary = {"stage": "full", "expected_count": len(keys), "completed": len(full_rows), "complete": complete,
               "unsent": unsent, "incomplete": [r["contract_id"] for r in full_rows if r.get("incomplete")],
               "errors": [r["contract_id"] for r in rows if r.get("error")],
               "diversity_expected": len(div_fams) * DIVERSITY_SEEDS, "diversity_completed": len(div_rows),
               "checkpoint": chk, "frechet_after_pooled": JR.pooled_frechet(blocks_after),
               "frechet_before_pooled": JR.pooled_frechet(blocks_before),
               "frechet_blocks_after": blocks_after, "frechet_blocks_before": blocks_before,
               "wall_s": time.time() - t_start, "workers": workers}
    good = [r for r in full_rows if not r.get("error")]
    summary["post_optimization_failures_median"] = JR._median_or_none(
        r.get("post_optimization_failures") for r in good if r.get("success"))
    summary["distributions"] = JR.distributions(good, div_rows)
    summary["skeleton_bias"] = JR.skeleton_bias(good)
    summary["formation_vs_prior"] = JR.formation_vs_prior(good)                       # V8-14b 第 4 节
    # V8-14c 第 5 节：分环节 CPU（各进程单线程，合同内各环节墙钟即 CPU 时间）、并行效率
    allr = [r for r in rows if not r.get("error")]
    stage_cpu = {k: float(sum((r.get("stage_timing") or {}).get(k, 0.0) for r in allr))
                 for k in ("skeleton_s", "optimize_s", "simulation_s", "verify_s")}
    busy = float(sum(r.get("wall_s") or 0.0 for r in allr))
    disp_wall = time.time() - t_dispatch
    summary["v14c"] = {"prewarm_s": prewarm["wall_s"], "dispatch_wall_s": disp_wall, "stage_cpu_s": stage_cpu,
                       "contract_busy_s": busy, "parallel_efficiency": busy / (disp_wall * workers) if disp_wall else None,
                       "contracts_run": len(allr)}
    summary["lp_seconds_per_attempt"] = JR._q([x for r in good for x in (r.get("lp_seconds") or []) if x is not None])
    write_json(out / "summary.json", summary, indent=1)
    return summary


def rerun_stage(entries, *, data_root, cache_dir, out_dir, keys_path, compare_to, log=print):
    from ..motion.optimize import load_settings
    from ..scene.context import load_context
    out = Path(out_dir)
    keys = [tuple(k) for k in json.loads(Path(keys_path).read_text(encoding="utf-8"))["keys"]]
    by_order = {int(e["order"]): e for e in entries}
    settings = load_settings()
    comps = []
    ctx = None
    for o, d in keys:
        e = by_order[int(o)]
        if ctx is None or ctx.family.family_id != e["family_id"]:
            ctx = load_context(e, data_root=Path(data_root), cache_dir=Path(cache_dir))
        rec = run_contract(ctx, e, int(d), settings=settings, out_dir=out)
        cid = rec["contract_id"]
        cmp_ = compare_dirs(Path(compare_to) / "contracts" / cid, out / "contracts" / cid)
        comps.append({"contract_id": cid, "success": rec["success"],
                      "source_dir": str((Path(compare_to) / "contracts" / cid).resolve()),
                      "repeat_dir": str((out / "contracts" / cid).resolve()), **cmp_})
        log(f"复跑 {cid}: success={rec['success']} bytes_equal={cmp_['bytes_equal']} files={len(cmp_['files'])}")
    doc = {"comparisons": comps, "all_equal": all(c["bytes_equal"] for c in comps), "workers_source": 8,
           "workers_repeat": 1}
    write_json(out / "reproduction.json", doc, indent=1)
    return doc
