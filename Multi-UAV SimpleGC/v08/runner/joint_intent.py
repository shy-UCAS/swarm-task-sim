"""通用意图运行器（V8-16 指令 2.1、5–7；本项新增）。

monitoring 分支委托旧 joint_monitoring.run_contract（字节不变）。transit 分支沿用其操作顺序与唯一 20 次预算：
同一 run_attempts、同一 attempt_chain（骨架 → 优化 → 批量跟踪 → 拼接 → 段核验 → 可见轨迹有效性；段核验按
SegmentTask(0, task.intent, target)），optimization_entered 在调用优化之前写入、异常保留 traceback。
过境输出用独立运行根：contract.json 明确 intent="transit"；result/attempt_log 保存过境语义字段（semantic_failures）；
其他确定性文件与旧布局一致。监视专用的 draw_summary/topology/phase_metrics/final_failure 全部按意图分派。
V8-17：intrusion 走同一 run_attempts/attempt_chain（attempt_chain 在返回 ok 前复算实测三层进入次数），运行前先做确定性
圆形证书（成立则 proven_infeasible、attempts=0）；预建/保存/阶段诊断/多样性按 intent 分派；过境默认与包装不变。
"""
import math
import time
import traceback
from pathlib import Path

import numpy as np

from . import joint_monitoring as JM
from . import joint_report as JR
from .monitoring import jsonable, write_json
from .runtime_defaults import DEFAULT_WORKERS

INTENTS = ("monitoring", "transit", "intrusion", "feint")


# ---------------------------------------------------------------- 单合同

def _transit_attempt_summary(rec, key):
    return _intent_attempt_summary(rec, key, "transit")


def _intent_module(intent):
    if intent == "intrusion":
        from ..motion.intents import intrusion as mod
    elif intent == "feint":
        from ..motion.intents import feint as mod
    else:
        from ..motion.intents import transit as mod
    return mod


def _intent_attempt_summary(rec, key, intent):
    s = JM._attempt_summary(rec, key)
    draw_summary = _intent_module(intent).draw_summary
    plan = rec.get("plan")
    if plan is not None:
        if plan.failure is None:
            s["draw"] = jsonable(draw_summary(plan.proposal or {}, (plan.formation or {}).get("realized")))
        else:
            w = plan.failure.witness or {}
            s["draw"] = jsonable(w.get("draw"))
    opt = rec.get("opt")
    if opt is not None and opt.get("semantic") is not None:
        s["optimize"]["semantic_failures"] = jsonable(opt["semantic"]["failures"])
    if intent == "intrusion" and rec.get("measured_intrusion") is not None:
        s["measured_intrusion_entries"] = {m: v["entry_counts"]
                                           for m, v in sorted(rec["measured_intrusion"]["members"].items())}
    if intent == "feint" and rec.get("measured_feint") is not None:
        s["measured_feint_entries"] = {m: v["entry_counts"] for m, v in sorted(rec["measured_feint"]["members"].items())}
    return s


def run_contract(ctx, entry, draw, *, intent, settings, branch=None, out_dir=None, should_stop=None, keep=None):
    if intent == "monitoring":
        return JM.run_contract(ctx, entry, draw, settings=settings, branch=branch, out_dir=out_dir,
                               should_stop=should_stop, keep=keep)
    if intent not in ("transit", "intrusion", "feint"):
        raise ValueError(f"本项只支持 {INTENTS}：{intent!r}")
    from ..contract.monitoring import initial_states
    from ..contract.single_intent import mission_for_intent
    from ..sampler.common import sample_common
    from ..sampler.keys import RngKey
    from .transit_report import phase_diagnostics, phase_durations
    final_failure = _intent_module(intent).final_failure
    common = sample_common(ctx.family, draw)
    mission = mission_for_intent(ctx, common, intent)
    group, task = mission.groups[0], mission.tasks[0]
    states = initial_states(ctx.family, group.member_ids)
    key0 = RngKey(ctx.family.family_id, int(draw), "shape", mission=0, branch=branch, group=group.group_id, segment=0)
    summaries = []

    def attempt_fn(k):
        flag = {}
        try:
            rec = JM.attempt_chain(ctx, group, task, states, k, settings, entry_flag=flag)
        except Exception as exc:
            rec = {"ok": False, "stage": "exception", "code": "implementation_error", "reason": repr(exc),
                   "traceback": traceback.format_exc(), "timing": {},
                   "optimization_entered": flag.get("optimization_entered")}
        summaries.append(_intent_attempt_summary(rec, k, intent))
        return rec

    cert = None
    if intent == "intrusion":                       # V8-17 指令 3.7：运行前确定性证书；成立则 attempts=0
        cert = _intent_module(intent).infeasibility_certificate(ctx, group, task)
    if cert is not None:
        out = {"success": False, "attempts": 0, "records": [], "result": None}
    else:
        out = JM.run_attempts(key0, attempt_fn, should_stop=should_stop)
    opt_s = float(sum((s["timing"] or {}).get("optimize_s", 0.0) for s in summaries))
    cid = JM.contract_id(entry, draw, branch)
    failure = None
    if cert is not None:
        failure = {"code": cert.code, "reason": cert.reason, "feasible_set": cert.feasible_set,
                   "witness": jsonable(cert.witness)}
    elif out.get("incomplete"):
        failure = {"code": "incomplete_deadline", "reason": "全量合作退出预算（joint_monitoring.WALL_BUDGET_S）到期",
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
    rec = {"contract_id": cid, "intent": intent, "family_id": ctx.family.family_id, "order": int(entry["order"]),
           "draw_index": int(draw), "branch": branch, "facility_count": int(entry["facility_count"]),
           "vehicle_count": int(ctx.family.vehicle_count), "lateral_spacing_m": float(ctx.family.lateral_spacing_m),
           "group_id": group.group_id, "member_ids": sorted(group.member_ids), "group_size": len(group.member_ids),
           "target_id": task.target_id, "initial_speed_m_s": float(group.speed_profile.initial_speed_m_s),
           "formation_prior": group.formation_prior, "success": bool(out["success"]), "attempts": out["attempts"],
           "optimization_s": opt_s, "failure": failure, "attempt_log": summaries,
           "settings_sha256": settings.get("_sha256"), "release_us": None, "retained_p0_ok": True}
    rec["incomplete"] = bool(out.get("incomplete", False))
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
        rec["retained_p0_ok"] = JM._retained_p0(res)
        if intent == "intrusion":
            # V8-17 指令 4.3：保留 P0 = 原保留门禁 ∧ 全体实测成员三层进入次数均为 1（attempt_chain 已在返回 ok 前查过，
            # 此处由实测释放后窗口重新生成确定性成员事件，不依赖该次结果对象）
            from .intrusion_report import measured_members
            meas = measured_members(ctx, res["tracks"], res["release_us"], task.target_id)
            P = res["plan"].proposal or {}
            rec["intrusion"] = {"sigma": float(P["sigma"]), "x_e": float(P["x_e"]),
                                "members": {m: {k: v[k] for k in ("entry_counts", "first_entry_us", "end_contour_m",
                                                                  "min_contour_m")}
                                            for m, v in sorted(meas["members"].items())}}
            rec["retained_p0_ok"] = bool(rec["retained_p0_ok"] and meas["all_single"])
        if intent == "feint":
            # V8-18 指令 4.2–4.3：保留 P0 = 原保留门禁 ∧ 全体实测成员 warning/alert 进入、退出均为 1（attempt_chain 已在
            # 返回 ok 前查过；此处由实测释放后窗口重新生成确定性成员事件）；result.json["feint"] 走字段白名单
            from .feint_report import formation_block, measured_members, result_block
            meas = measured_members(ctx, res["tracks"], res["release_us"], task.target_id)
            plan_ = res["plan"]
            blk = {**result_block(plan_.proposal or {}, meas),
                   "formation": formation_block(plan_.formation or {}, plan_.repairs)}
            rec["feint"] = {k: blk[k] for k in ("turn", "formation", "members")}
            rec["retained_p0_ok"] = bool(rec["retained_p0_ok"] and meas["all_single"])
        rec["deviation"] = JM.member_deviation(res)
        rec["tracking"] = JM.tracking_stats(res)
        try:
            rec["phase_metrics"] = phase_diagnostics(res, intent=intent, ctx=ctx)
        except Exception:
            rec["phase_metrics"] = {"error": traceback.format_exc()}
        try:
            rec["phase_durations"] = phase_durations(res, intent=intent)
        except Exception:
            rec["phase_durations"] = {"error": traceback.format_exc()}
        plan = res["plan"]
        rec["nominal_duration_s"] = float(plan.nominal_duration_s)
        rec["formation"] = {k: plan.formation.get(k) for k in ("prior", "start", "realized", "mapped_from_loose",
                                                                "lateral_step_m")}
        tkeys = ("final", "curved", "fallback_reason") + (("sigma", "x_e") if intent == "intrusion" else
                                                          ("turn_kind", "turn_side", "radius_m") if intent == "feint"
                                                          else ())
        rec["topology"] = {k: plan.topology.get(k) for k in tkeys}
        if keep is not None:
            keep["result"] = res
    elif intent == "intrusion":
        rec["intrusion"] = None
    elif intent == "feint":
        rec["feint"] = None
    if out_dir is not None:
        last = out["records"][-1] if (out["records"] and not out["success"]) else None
        save_intent_contract(Path(out_dir), rec, out["result"], last_failed=last)
    return rec


def save_transit_contract(out, rec, result, last_failed=None):
    """与 joint_monitoring.save_contract 同布局；contract.json 多 intent 字段，result.json 多过境语义字段，
    失败见证用 semantic_failures。遥测写在合同目录外。V8-17：机械提取为 save_intent_contract 的包装。"""
    return save_intent_contract(out, rec, result, last_failed=last_failed)


def save_intent_contract(out, rec, result, last_failed=None):
    """共享序列化（明确字段白名单）：用 rec["intent"] 选择附加块。过境保持原文件 bytes（不补 intrusion:null、crossing
    表、版本号或新默认字段）；intrusion 的 result.json 增加 "intrusion" 块（σ、x_e 来自保留提案，成员事件来自实测释放后
    窗口；失败为 None），失败见证另含实测三层进入次数。墙钟、缓存命中、traceback 只进合同目录外的 telemetry。"""
    _json_bytes = JM._json_bytes
    intent = rec.get("intent", "transit")
    d = out / "contracts" / rec["contract_id"]
    d.mkdir(parents=True, exist_ok=False)
    contract = {k: rec[k] for k in ("contract_id", "intent", "family_id", "order", "draw_index", "branch",
                                    "facility_count", "vehicle_count", "group_id", "member_ids", "group_size",
                                    "target_id", "initial_speed_m_s", "formation_prior")}
    (d / "contract.json").write_bytes(_json_bytes(contract))
    det_attempts = [{k: v for k, v in s.items() if k not in ("timing", "traceback")} for s in rec["attempt_log"]]
    result_doc = {"intent": intent, "success": rec["success"], "attempts": rec["attempts"], "failure": rec["failure"],
                  "attempt_log": det_attempts, "release_us": rec["release_us"], "settings_sha256": rec["settings_sha256"],
                  "retained_p0_ok": rec["retained_p0_ok"], "incomplete": rec.get("incomplete", False),
                  "post_optimization_failures": rec["post_optimization_failures"],
                  "skeleton_failures": rec["skeleton_failures"], "unknown_attempts": rec["unknown_attempts"],
                  "shape_audit_failed_attempts": rec["shape_audit_failed_attempts"],
                  "deviation": rec.get("deviation"), "tracking": rec.get("tracking"),
                  "nominal_duration_s": rec.get("nominal_duration_s"), "formation": rec.get("formation"),
                  "topology": rec.get("topology"), "phase_metrics": rec.get("phase_metrics"),
                  "phase_durations": rec.get("phase_durations")}
    if intent == "intrusion":
        result_doc["intrusion"] = rec.get("intrusion")
    if intent == "feint":
        result_doc["feint"] = rec.get("feint")
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
        plan = last_failed["plan"]
        doc = {"stage": last_failed.get("stage"), "reason": last_failed.get("reason"),
               "skeleton_members": {m: np.asarray(mp.curve_xy, float).tolist() for m, mp in sorted(plan.members.items())}}
        opt = last_failed.get("opt")
        if opt is not None:
            sol = opt["solution"]
            doc["optimized"] = {m: {"release_s": t.release_s, "end_s": t.end_s, "knots": t.knots, "controls": t.controls}
                                for m, t in sorted(sol.references.items())}
            doc["physical_failures"] = jsonable((sol.diagnostics.get("physical") or {}).get("failures"))
            if opt.get("semantic") is not None:
                doc["semantic_failures"] = jsonable(opt["semantic"]["failures"])
        if last_failed.get("tracks") is not None:
            doc["tracks_p"] = {m: np.asarray(tr.p, float)[:, :2].tolist() for m, tr in sorted(last_failed["tracks"].items())}
        if last_failed.get("validity") is not None:
            doc["validity_codes"] = jsonable(last_failed["validity"].codes)
        if last_failed.get("verdicts") is not None:
            doc["segment_failures"] = jsonable([v.failures for v in last_failed["verdicts"]])
        if intent == "intrusion" and last_failed.get("measured_intrusion") is not None:
            doc["measured_intrusion"] = jsonable(last_failed["measured_intrusion"])
        if intent == "feint" and last_failed.get("measured_feint") is not None:
            doc["measured_feint"] = jsonable(last_failed["measured_feint"])
        (d / "failure_witness.json").write_bytes(_json_bytes(doc))
    tele = out / "telemetry"
    tele.mkdir(exist_ok=True)
    (tele / f"{rec['contract_id']}.json").write_bytes(_json_bytes(
        {"timing": [s.get("timing") for s in rec["attempt_log"]], "optimization_s": rec["optimization_s"],
         "tracebacks": [s.get("traceback") for s in rec["attempt_log"] if s.get("traceback")]}))


def record_row(rec):
    row = JM._record_row(rec)
    row["intent"] = rec.get("intent", "monitoring")
    row["phase_durations"] = rec.get("phase_durations")
    row["nominal_duration_s"] = rec.get("nominal_duration_s")
    row["lateral_spacing_m"] = rec.get("lateral_spacing_m")
    return row


# ---------------------------------------------------------------- 进程池（spawn；顶层函数）

def _pool_task(task):
    """(kind, entry, draw, branch, data_root, cache_dir, out_dir, deadline, intent)。上下文按最近使用保留 3 个；
    缓存在派发前预建，worker 只读（过境弦集合缺失时进程内计算，不写回）。"""
    import time as _t
    from ..motion.optimize import load_settings
    from ..scene.context import load_context
    kind, entry, draw, branch, data_root, cache_dir, out_dir, deadline, intent = task
    g = globals().setdefault("_WCTX", {})
    if entry["order"] not in g:
        while len(g) >= 3:
            g.pop(next(iter(g)))
        g[entry["order"]] = load_context(entry, data_root=Path(data_root), cache_dir=Path(cache_dir))
    else:
        g[entry["order"]] = g.pop(entry["order"])
    ctx = g[entry["order"]]
    settings = load_settings()
    t0 = _t.perf_counter()
    try:
        if intent == "intrusion":
            from ..motion import intrusion_chords as TC
        elif intent == "feint":
            from ..motion import feint_chords as TC
        else:
            from ..motion import transit_chords as TC
        before = dict(TC.STATS)
        holder = {}
        rec = run_contract(ctx, entry, draw, intent=intent, settings=settings, branch=branch, out_dir=Path(out_dir),
                           should_stop=(lambda: _t.time() > deadline) if deadline is not None else None, keep=holder)
        row = record_row(rec)
        row.update(kind=kind, wall_s=_t.perf_counter() - t0, stage_timing=rec.get("stage_timing"),
                   attempt_stages=[a["stage"] for a in rec["attempt_log"]],
                   skeleton_detail=[((a.get("timing") or {}).get("skeleton_detail") or {}) for a in rec["attempt_log"]],
                   nit=[(a.get("timing") or {}).get("nit") for a in rec["attempt_log"]],
                   chord_cache={k: TC.STATS[k] - before.get(k, 0) for k in TC.STATS})
        if kind == "diversity" and rec["success"] and intent in ("transit", "intrusion", "feint"):
            from .transit_report import group_reference_curves
            from ..contract.single_intent import mission_for_intent
            from ..sampler.common import sample_common
            group = mission_for_intent(ctx, sample_common(ctx.family, draw), intent).groups[0]
            got = group_reference_curves(ctx, group, holder["result"], intent=intent)
            row["curve_before"] = None if got["before"] is None else got["before"].tolist()
            row["curve_after"] = None if got["after"] is None else got["after"].tolist()
            row["frechet_info"] = got["info"]
            if got["after"] is None:
                row["frechet_na"] = (got["info"].get("after") or {}).get("na_reason")
        return row
    except Exception as exc:
        return {"contract_id": JM.contract_id(entry, draw, branch), "family_id": entry["family_id"], "kind": kind,
                "draw_index": draw, "branch": branch, "success": False, "attempts": None,
                "error": repr(exc), "traceback": traceback.format_exc()}


def _dispatch(tasks, *, workers, deadline, log=print):
    """单合同动态派发（一次提交一个）；deadline 为 None 表示不设合作退出。返回 (rows, 未派发)。"""
    import multiprocessing as mp
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
    rows, pending, unsent = [], set(), []
    it = iter(tasks)
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
        def submit_next():
            for t in it:
                if deadline is not None and time.time() > deadline:
                    unsent.append(JM.contract_id(t[1], t[2], t[3]))
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
                    f"wall={row.get('wall_s', 0) or 0:.0f}s err={row.get('error')}", flush=True)
                submit_next()
    return rows, unsent


def _cost_order(entries, keys, sizes):
    """派发顺序：第 0 编组人数 × 地图边长降序，原业务键破平局（顺序不进入 RNG，输出按业务键）。"""
    by = {int(e["order"]): e for e in entries}
    rows = []
    for kind, o, d, b in keys:
        e = by[o]
        rows.append((sizes[(o, d)] * float(e["map_side_m"]), kind != "full", o, d, -1 if b is None else b, (kind, e, d, b)))
    rows.sort(key=lambda x: (-x[0], x[1], x[2], x[3], x[4]))
    return rows


# ---------------------------------------------------------------- 预建（弦集合 + 原始距离场）

def _prewarm_family(task):
    """一族在一个进程内：上下文与原始距离场（同 joint_monitoring.prewarm_cache 的几何集合）、该族全部合同的确定性
    选队形 probe 序列对应的弦集合文件（已存在不覆盖）。各族写不同文件。task 第 5 项为 intent（缺省 transit）。"""
    if len(task) > 4 and task[4] == "intrusion":
        return _prewarm_family_intrusion(task)
    if len(task) > 4 and task[4] == "feint":
        return _prewarm_family_feint(task)
    import time as _t
    from ..contract.single_intent import transit_mission
    from ..motion import transit_chords as TC
    from ..motion.intents.transit import formation_probe_sequence
    from ..sampler.common import sample_common
    from ..sampler.keys import RngKey
    from ..scene.context import load_context
    entry, draws, data_root, cache_dir = task[:4]
    t0 = _t.perf_counter()
    ctx = load_context(entry, data_root=Path(data_root), cache_dir=Path(cache_dir))
    # 构造 probe 序列时只读已有弦集合文件（load_chord_set 不写）；缺失的在内存计算，之后由 prewarm_transit 统一写出
    rows, sizes = [], {}
    for d in draws:
        m = transit_mission(ctx, sample_common(ctx.family, d))
        g, task_ = m.groups[0], m.tasks[0]
        sizes[f"{int(entry['order'])}:{d}"] = len(g.member_ids)
        key = RngKey(ctx.family.family_id, d, "shape", mission=0, branch=None, group=g.group_id, segment=0)
        seq = formation_probe_sequence(ctx, g, task_, key)
        rows.append({"draw": d, "target": task_.target_id, "probes": [[n, s, None] for n, s, _ in seq],
                     "requests": [(task_.target_id, offs) for _, _, offs in seq]})
    reqs, seen = [], set()
    for r in rows:
        for t, offs in r["requests"]:
            qid, _ = TC.query_identity(ctx, t, offs)
            if qid not in seen:
                seen.add(qid)
                reqs.append((t, offs))
    written = TC.prewarm_transit(ctx, reqs, cache_dir)
    st = ctx.cache_stats()
    return {"order": int(entry["order"]), "family_id": entry["family_id"], "wall_s": _t.perf_counter() - t0,
            "queries": written, "raw_cache": st, "sizes": sizes,
            "probes": {r["draw"]: {"target": r["target"], "probes": r["probes"]} for r in rows}}


def _prewarm_family_intrusion(task):
    """突入：同一族一个进程；先读已有文件（load_chord_set 只读），再由 prewarm_intrusion 统一写出缺失文件。
    运行前圆形证书成立的合同不发起任何 probe 请求（attempts=0），因此也不预建。"""
    import time as _t
    from ..contract.single_intent import intrusion_mission
    from ..motion import intrusion_chords as IC
    from ..motion.intents.intrusion import formation_probe_sequence, infeasibility_certificate
    from ..sampler.common import sample_common
    from ..sampler.keys import RngKey
    from ..scene.context import load_context
    entry, draws, data_root, cache_dir = task[:4]
    t0 = _t.perf_counter()
    ctx = load_context(entry, data_root=Path(data_root), cache_dir=Path(cache_dir))
    rows, sizes = [], {}
    for d in draws:
        m = intrusion_mission(ctx, sample_common(ctx.family, d))
        g, task_ = m.groups[0], m.tasks[0]
        sizes[f"{int(entry['order'])}:{d}"] = len(g.member_ids)
        if infeasibility_certificate(ctx, g, task_) is not None:
            rows.append({"draw": d, "target": task_.target_id, "probes": [], "requests": [], "certificate": True})
            continue
        key = RngKey(ctx.family.family_id, d, "shape", mission=0, branch=None, group=g.group_id, segment=0)
        seq = formation_probe_sequence(ctx, g, task_, key)
        rows.append({"draw": d, "target": task_.target_id, "probes": [[n, s, None] for n, s, _, _ in seq],
                     "requests": [(task_.target_id, offs, sig) for _, _, offs, sig in seq], "certificate": False})
    reqs, seen = [], set()
    for r in rows:
        for t, offs, sig in r["requests"]:
            qid, _ = IC.query_identity(ctx, t, offs, sig)
            if qid not in seen:
                seen.add(qid)
                reqs.append((t, offs, sig))
    written = IC.prewarm_intrusion(ctx, reqs, cache_dir)
    st = ctx.cache_stats()
    return {"order": int(entry["order"]), "family_id": entry["family_id"], "wall_s": _t.perf_counter() - t0,
            "queries": written, "raw_cache": st, "sizes": sizes, "lane_stats": dict(IC.STATS),
            "probes": {r["draw"]: {"target": r["target"], "probes": r["probes"], "certificate": r["certificate"]}
                       for r in rows}}


def _prewarm_family_feint(task):
    """佯动（V8-18 指令 3.2）：同一族一个进程；先按确定性 probe 序列读已有文件（load_chord_set 只读），再由
    prewarm_feint 统一写出缺失文件（原子落盘、按完整查询身份去重、已存在不覆盖）。预建不使用 RNG。"""
    import time as _t
    from ..contract.single_intent import feint_mission
    from ..motion import feint_chords as FC
    from ..motion.intents.feint import formation_probe_sequence
    from ..sampler.common import sample_common
    from ..sampler.keys import RngKey
    from ..scene.context import load_context
    entry, draws, data_root, cache_dir = task[:4]
    t0 = _t.perf_counter()
    ctx = load_context(entry, data_root=Path(data_root), cache_dir=Path(cache_dir))
    rows, sizes = [], {}
    for d in draws:
        m = feint_mission(ctx, sample_common(ctx.family, d))
        g, task_ = m.groups[0], m.tasks[0]
        sizes[f"{int(entry['order'])}:{d}"] = len(g.member_ids)
        key = RngKey(ctx.family.family_id, d, "shape", mission=0, branch=None, group=g.group_id, segment=0)
        tq = _t.perf_counter()
        seq = formation_probe_sequence(ctx, g, task_, key)
        rows.append({"draw": d, "target": task_.target_id, "probes": [[nm, st, None] for nm, st, _, _ in seq],
                     "requests": [(task_.target_id, offs, sp) for _, _, offs, sp in seq],
                     "probe_wall_s": _t.perf_counter() - tq})
    reqs = [r for row in rows for r in row["requests"]]
    written = FC.prewarm_feint(ctx, reqs, cache_dir)
    st = ctx.cache_stats()
    return {"order": int(entry["order"]), "family_id": entry["family_id"], "wall_s": _t.perf_counter() - t0,
            "queries": written, "raw_cache": st, "sizes": sizes,
            "probes": {r["draw"]: {"target": r["target"], "probes": r["probes"], "probe_wall_s": r["probe_wall_s"]}
                       for r in rows}}


def prewarm_all(entries, *, data_root, cache_dir, workers, draws=range(5), log=print, intent="transit"):
    """派发前预建：各族一个任务、spawn 进程池（每族写自己的文件，无并发写同一文件）；派发阶段 worker 只读。
    V8-17：按 intent 选择 mission、formation_probe_sequence 与 load/prewarm 函数；旧调用（缺省 transit）不变。"""
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor
    t0 = time.time()
    ordered = sorted(entries, key=lambda e: e["order"])
    tasks = [(e, list(draws), str(data_root), str(cache_dir)) + ((intent,) if intent != "transit" else ())
             for e in ordered]
    out = []
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
        for r in ex.map(_prewarm_family, tasks):
            out.append(r)
            log(f"预建 o{r['order']:02d}: {len(r['queries'])} 个查询，{r['wall_s']:.0f}s，"
                f"新写 {sum(not q['existing'] for q in r['queries'])}", flush=True)
    sizes = {}
    for r in out:
        sizes.update(r["sizes"])
    return {"families": len(out), "wall_s": time.time() - t0, "per_family": out, "group_size": sizes,
            "queries_total": sum(len(r["queries"]) for r in out),
            "queries_written": sum(sum(not q["existing"] for q in r["queries"]) for r in out),
            "query_build_s": sum(q["seconds"] for r in out for q in r["queries"])}


# ---------------------------------------------------------------- 批次

def run_selected(entries, keys, *, intent, data_root, cache_dir, out_dir, workers=DEFAULT_WORKERS, settings=None,
                 stage="quick", log=print, prewarm=True):
    """keys：[(order, draw)]。先预建（过境），再按成本降序单合同动态派发到 workers 个进程；写 records/summary。"""
    out = Path(out_dir)
    t0 = time.time()
    pw = (prewarm_all(entries, data_root=data_root, cache_dir=cache_dir, workers=workers, log=log, intent=intent)
          if prewarm else None)
    if pw is not None:
        write_json(out / "prewarm.json", pw, indent=1)
    sizes = {tuple(map(int, k.split(":"))): v for k, v in (pw or {}).get("group_size", {}).items()}
    if not sizes:
        sizes = {(int(o), int(d)): 1 for o, d in keys}
    order = _cost_order(entries, [("full", int(o), int(d), None) for o, d in keys], sizes)
    write_json(out / "dispatch_order.json", [{"order": x[2], "draw": x[3], "cost": x[0]} for x in order], indent=1)
    td = time.time()
    tasks = [(k, e, d, b, str(data_root), str(cache_dir), str(out), None, intent) for _, _, _, _, _, (k, e, d, b) in order]
    rows, _ = _dispatch(tasks, workers=workers, deadline=None, log=log)
    rows.sort(key=lambda r: r["contract_id"])
    write_json(out / "records.json", rows, indent=1)
    good = [r for r in rows if not r.get("error")]
    chk = JR.quick_checkpoint(good) if stage == "quick" else None
    complete = (len(rows) == len(keys) and not any(r.get("error") or r.get("incomplete") for r in rows)
                and not any(r.get("unknown_attempts") for r in good)
                and not (chk or {}).get("metrics", {}).get("attempts_undetermined", False))
    p0 = [r["contract_id"] for r in good if r.get("success") and not r.get("retained_p0_ok")]
    summary = {"stage": stage, "intent": intent, "expected_count": len(keys), "completed": len(rows),
               "complete": complete, "checkpoint": chk, "workers": workers, "wall_s": time.time() - t0,
               "dispatch_wall_s": time.time() - td, "errors": [r["contract_id"] for r in rows if r.get("error")],
               "retained_p0_violations": p0, "prewarm_wall_s": None if pw is None else pw["wall_s"],
               "contract_busy_s": float(sum(r.get("wall_s") or 0.0 for r in good)),
               "stage_cpu_s": {k: float(sum((r.get("stage_timing") or {}).get(k, 0.0) for r in good))
                               for k in ("skeleton_s", "optimize_s", "simulation_s", "verify_s")},
               "chord_cache": {k: int(sum((r.get("chord_cache") or {}).get(k, 0) for r in good))
                               for k in ("cache_hits", "cache_misses_computed")}}
    write_json(out / "summary.json", summary, indent=1)
    return summary


def full_stage(entries, *, data_root, cache_dir, out_dir, workers, intent="transit", log=print):
    """全量 200 + 多样性 10 族 × 10 branch（draw 0），沿用旧 full_stage 的 7200 s 合作退出预算（防卡死，到期为
    incomplete）；复跑 5 键在开始前写 rerun_keys.json。全量成功率与分档只看 200 主合同。"""
    from .monitoring import select_diversity_families
    out = Path(out_dir)
    t_start = time.time()
    ordered = sorted(entries, key=lambda e: e["order"])
    keys = [(int(e["order"]), d) for e in ordered for d in range(JM.DRAWS)]
    write_json(out / "rerun_keys.json", {"keys": [list(k) for k in keys[:5]],
                                         "rule": "全量开始前按 (order, draw) 字典序取前 5 个合同"}, indent=1)
    div_fams = select_diversity_families(entries)
    (out / "diversity").mkdir()
    pw = prewarm_all(entries, data_root=data_root, cache_dir=cache_dir, workers=workers, log=log, intent=intent)
    write_json(out / "prewarm.json", pw, indent=1)
    sizes = {tuple(map(int, k.split(":"))): v for k, v in pw["group_size"].items()}
    klist = [("full", o, d, None) for o, d in keys]
    klist += [("diversity", int(e["order"]), 0, b) for e in div_fams for b in range(JM.DIVERSITY_SEEDS)]
    order = _cost_order(entries, klist, sizes)
    write_json(out / "dispatch_order.json", [{"kind": x[5][0], "order": x[2], "draw": x[3], "branch": x[5][3],
                                             "cost": x[0]} for x in order], indent=1)
    t_dispatch = time.time()
    deadline = t_dispatch + JM.WALL_BUDGET_S
    tasks = []
    for _, _, _, _, _, (k, e, d, b) in order:
        od = str(out) if k == "full" else str(out / "diversity")
        tasks.append((k, e, d, b, str(data_root), str(cache_dir), od, deadline, intent))
    rows, unsent = _dispatch(tasks, workers=workers, deadline=deadline, log=log)
    full_rows = sorted([r for r in rows if r.get("kind") == "full"], key=lambda r: r["contract_id"])
    div_rows = sorted([r for r in rows if r.get("kind") == "diversity"], key=lambda r: r["contract_id"])
    write_json(out / "records.json", [{k: v for k, v in r.items() if k not in ("curve_before", "curve_after")}
                                      for r in full_rows], indent=1)
    write_json(out / "diversity" / "records.json", div_rows, indent=1)
    from .transit_report import frechet_blocks
    blocks_after = frechet_blocks(div_rows, "curve_after", intent=intent)
    blocks_before = frechet_blocks(div_rows, "curve_before", intent=intent)
    good = [r for r in full_rows if not r.get("error")]
    complete = (len(full_rows) == len(keys) and not unsent
                and not any(r.get("incomplete") or r.get("error") for r in full_rows)
                and not any(r.get("unknown_attempts") or (r.get("success") and r.get("post_optimization_failures") is None)
                            for r in full_rows))
    if intent == "intrusion":
        from .intrusion_report import full_checkpoint as intrusion_full_checkpoint
        chk = intrusion_full_checkpoint(good, blocks_after) if full_rows else None
    elif intent == "feint":
        from .feint_report import full_checkpoint as feint_full_checkpoint
        chk = feint_full_checkpoint(good, blocks_after) if full_rows else None
    else:
        chk = JR.full_checkpoint(good, blocks_after) if full_rows else None
    disp_wall = time.time() - t_dispatch
    allr = [r for r in rows if not r.get("error")]
    busy = float(sum(r.get("wall_s") or 0.0 for r in allr))
    summary = {"stage": "full", "intent": intent, "expected_count": len(keys), "completed": len(full_rows),
               "complete": complete, "unsent": unsent,
               "incomplete": [r["contract_id"] for r in full_rows if r.get("incomplete")],
               "errors": [r["contract_id"] for r in rows if r.get("error")],
               "diversity_expected": len(div_fams) * JM.DIVERSITY_SEEDS, "diversity_completed": len(div_rows),
               "diversity_complete": (len(div_rows) == len(div_fams) * JM.DIVERSITY_SEEDS and
                                      len({r["contract_id"] for r in div_rows}) == len(div_rows) and
                                      not any(r.get("incomplete") or r.get("error") for r in div_rows)),
               "checkpoint": chk, "frechet_after_pooled": JR.pooled_frechet(blocks_after),
               "frechet_before_pooled": JR.pooled_frechet(blocks_before),
               "frechet_blocks_after": blocks_after, "frechet_blocks_before": blocks_before,
               "retained_p0_violations": [r["contract_id"] for r in allr if r.get("success") and not r.get("retained_p0_ok")],
               "post_optimization_failures_median": JR._median_or_none(
                   r.get("post_optimization_failures") for r in good if r.get("success")),
               "formation_vs_prior": JR.formation_vs_prior(good), "workers": workers,
               "prewarm_wall_s": pw["wall_s"], "dispatch_wall_s": disp_wall, "wall_s": time.time() - t_start,
               "contract_busy_s": busy, "parallel_efficiency": busy / (disp_wall * workers) if disp_wall else None,
               "stage_cpu_s": {k: float(sum((r.get("stage_timing") or {}).get(k, 0.0) for r in allr))
                               for k in ("skeleton_s", "optimize_s", "simulation_s", "verify_s")},
               "chord_cache": {k: int(sum((r.get("chord_cache") or {}).get(k, 0) for r in allr))
                               for k in ("cache_hits", "cache_misses_computed")},
               "wall_budget_s": JM.WALL_BUDGET_S,
               "wall_budget_source": "joint_monitoring.WALL_BUDGET_S（旧 full_stage 合作退出，防卡死；到期为 incomplete）"}
    write_json(out / "summary.json", summary, indent=1)
    return summary


def rerun_stage(entries, *, data_root, cache_dir, out_dir, keys_path, compare_to, intent="transit", log=print):
    """固定单进程，同环境同缓存同参数复跑，与原输出逐字节比较（合同内排除清单为空）。"""
    import json
    from ..motion.optimize import load_settings
    from ..scene.context import load_context
    out = Path(out_dir)
    keys = [tuple(k) for k in json.loads(Path(keys_path).read_text(encoding="utf-8"))["keys"]]
    by_order = {int(e["order"]): e for e in entries}
    settings = load_settings()
    comps, rows = [], []
    ctx = None
    for o, d in keys:
        e = by_order[int(o)]
        if ctx is None or ctx.family.family_id != e["family_id"]:
            ctx = load_context(e, data_root=Path(data_root), cache_dir=Path(cache_dir))
        rec = run_contract(ctx, e, int(d), intent=intent, settings=settings, out_dir=out)
        rows.append(record_row(rec))
        cid = rec["contract_id"]
        cmp_ = JM.compare_dirs(Path(compare_to) / "contracts" / cid, out / "contracts" / cid)
        comps.append({"contract_id": cid, "success": rec["success"],
                      "source_dir": str((Path(compare_to) / "contracts" / cid).resolve()),
                      "repeat_dir": str((out / "contracts" / cid).resolve()), **cmp_})
        log(f"复跑 {cid}: success={rec['success']} bytes_equal={cmp_['bytes_equal']} files={len(cmp_['files'])}")
    write_json(out / "records.json", rows, indent=1)
    doc = {"comparisons": comps, "all_equal": all(c["bytes_equal"] for c in comps), "workers_source": DEFAULT_WORKERS,
           "workers_repeat": 1, "exclusions": []}
    write_json(out / "reproduction.json", doc, indent=1)
    write_json(out / "summary.json", {"stage": "rerun", "intent": intent, "expected_count": len(keys),
                                      "completed": len(rows), "all_equal": doc["all_equal"]}, indent=1)
    return doc
