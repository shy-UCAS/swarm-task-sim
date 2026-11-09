"""过境 200 合同只骨架检查点（V8-16 指令第 5 部分、附录裁定 1；本项新增）。

40 族 × 5 draw 同键公共抽签、意图 transit；主进程派发前预建弦集合（各族一个预建任务、写各自文件），之后按合同派发
（第 0 编组人数 × 地图边长降序，原业务键破平局），worker 只读。每个合同最多 20 个骨架 attempt（本阶段独立测量的预算，
不从全链路扣），不调用优化/跟踪。统计复用 skeleton_monitoring.skeleton_checkpoint（不调用其写死监视的构造函数）；
附录裁定 1 增加止损项：成功骨架中直线回退比例 > 1/2 即触发（恰为 1/2 不触发，分母 = 成功骨架合同数）。
V8-17 指令 4.3：机械提取 run_intent_skeleton_contract / run_intent_skeleton_batch（intent 参数），旧
run_transit_skeleton_contract / run_transit_skeleton_batch 保留为 transit 包装；intrusion 运行前做确定性圆形证书
（成立则 proven_infeasible、attempts=0），检查点用 intrusion_report.skeleton_checkpoint（名单只影响率/档差）。
"""
import json
import time
import traceback
from fractions import Fraction
from pathlib import Path

from .monitoring import jsonable, write_json
from .runtime_defaults import DEFAULT_WORKERS

BUDGET = 20
DRAWS = 5
FALLBACK_MAX = Fraction(1, 2)        # 附录裁定 1：> 50% 停在检查点


def _attempt_row(a, plan, timing, exc_text=None):
    if exc_text is not None:
        return {"attempt": a, "ok": False, "stage": "exception", "code": "implementation_error", "reason": exc_text,
                "shape_audit_failed": False, "timing": timing}
    f = plan.failure
    w = (f.witness or {}) if f is not None else (plan.witnesses or {})
    P = plan.proposal or {}
    rec = {"attempt": a, "ok": f is None, "stage": "skeleton_ok" if f is None else w.get("stage", f.feasible_set),
           "code": None if f is None else f.code, "reason": None if f is None else f.reason,
           "feasible_set": None if f is None else f.feasible_set,
           "shape_audit_failed": bool(w.get("shape_audit_failed", False)) if f is not None else False,
           "draw": w.get("draw") if f is not None else None,
           "formation_steps": [{k: st.get(k) for k in ("formation", "lateral_step_m", "feasible_cells", "n_cells",
                                                       "query_id", "reasons")}
                               for st in (P.get("formation_steps") or (w.get("formations") or []))],
           "timing": timing}
    if P.get("intent") == "intrusion":
        rec["intrusion"] = {"sigma": P.get("sigma"), "x_e": P.get("x_e"), "sigmas_feasible": P.get("sigmas_feasible"),
                            "endpoint_quantile": P.get("endpoint_quantile"), "lp_calls": P.get("lp_calls"),
                            "shape_draws": 1 if P.get("cell_index") is not None else 0}
    if P.get("intent") == "feint":                  # V8-18：佯动掉头选择（确定性业务数据）
        rec["feint"] = {"turn": P.get("turn"), "nonempty_combos": P.get("nonempty_combos"),
                        "combos_found": P.get("combos_found"), "collect_D_m": P.get("collect_D_m"),
                        "L_m": P.get("L_m"), "l_star_m": P.get("l_star_m"), "lp_calls": P.get("lp_calls")}
    if P.get("intent") == "close_observation":
        from ..motion.intents import close_observation as close
        w = plan.witnesses or {}
        rec["dwell"] = close.project(P.get("dwell"), close.DWELL, "skeleton_attempt.dwell")
        rec["dwell_diagnostics"] = close.project(w.get("dwell_diagnostics"), close.DWELL_DIAGNOSTICS, "skeleton_attempt.dwell_diagnostics")
        rec["nominal_screen"] = close.project(w.get("screen"), close.MAP(close.SCREEN), "skeleton_attempt.nominal_screen")
    if f is None:
        cor = P.get("corridor") or {}
        lp = P.get("lp") or {}
        rec.update(curved=bool(P.get("curved")), fallback_reason=P.get("fallback_reason"),
                   corridor={k: cor.get(k) for k in ("certified_length_m", "inset_length_m", "rows_total",
                                                     "certified_rows", "D")},
                   lp={k: lp.get(k) for k in ("lp_status", "objective", "max_residual", "n_controls")},
                   curve_audit={k: (P.get("curve_audit") or {}).get(k) for k in ("ok", "kappa_max_abs", "slope_max",
                                                                                "min_den")},
                   theta_deg=P.get("theta_deg"), h_m=P.get("h_m"), cells_feasible=P.get("cells_feasible"),
                   collect_D_m=P.get("collect_D_m"), K=P.get("K"),
                   lateral_deviation_m=_lateral_deviation(P), repairs=jsonable(list(plan.repairs)))
    return jsonable(rec)


def _lateral_deviation(P):
    """曲线相对原弦的最大横向偏离 max|δ(x) − h|（直线为 0）。"""
    c = P.get("curve")
    if not c:
        return 0.0
    import numpy as np
    from scipy.interpolate import BSpline
    sp = BSpline(np.asarray(c["knots_m"], float), np.asarray(c["controls_m"], float), 3, extrapolate=False)
    xs = np.linspace(c["x_range"][0], c["x_range"][1], 2001)
    return float(np.max(np.abs(sp(xs) - float(P["h_m"]))))


def run_transit_skeleton_contract(ctx, entry, draw, *, out_dir=None):
    return run_intent_skeleton_contract(ctx, entry, draw, intent="transit", out_dir=out_dir)


def _skeleton_modules(intent):
    if intent == "area_search":
        from ..motion import transit_chords as TC
        from ..motion.intents import area_search as mod
    elif intent == "intrusion":
        from ..motion import intrusion_chords as TC
        from ..motion.intents import intrusion as mod
    elif intent == "feint":
        from ..motion import feint_chords as TC
        from ..motion.intents import feint as mod
    elif intent == "close_observation":
        from ..motion import transit_chords as TC
        from ..motion.intents import close_observation as mod
    else:
        from ..motion import transit_chords as TC
        from ..motion.intents import transit as mod
    return TC, mod


def run_intent_skeleton_contract(ctx, entry, draw, *, intent, out_dir=None):
    """共享单段骨架运行；旧 run_transit_skeleton_contract 保留为 transit 包装。"""
    from ..contract.monitoring import initial_states
    from ..contract.single_intent import mission_for_intent
    from ..motion.plan import plan_attempt
    from ..sampler.common import sample_common
    from ..sampler.keys import RngKey
    from .joint_monitoring import _json_bytes, contract_id, run_attempts
    TC, mod = _skeleton_modules(intent)
    def contract_bytes(value):
        if intent == "close_observation":
            from .close_observation_report import assert_contract_payload
            assert_contract_payload(jsonable(value))
        return _json_bytes(value)
    final_failure, last_attempt_timing = mod.final_failure, mod.last_attempt_timing
    common = sample_common(ctx.family, draw)
    mission = mission_for_intent(ctx, common, intent)
    group, task = mission.groups[0], mission.tasks[0]
    states = initial_states(ctx.family, group.member_ids)
    key0 = RngKey(ctx.family.family_id, int(draw), "shape", mission=0, branch=None, group=group.group_id, segment=0)
    logs, plans = [], {}
    before = dict(TC.STATS)

    def attempt_fn(k):
        t0 = time.perf_counter()
        try:
            plan = plan_attempt(ctx, group, task, states, (), k)
        except Exception:
            rec = _attempt_row(k.attempt, None, {"attempt_wall_s": time.perf_counter() - t0},
                               exc_text=traceback.format_exc())
            logs.append(rec)
            return {"ok": False, "stage": "exception"}
        timing = {"attempt_wall_s": time.perf_counter() - t0, **last_attempt_timing()}
        rec = _attempt_row(k.attempt, plan, timing)
        logs.append(rec)
        if plan.failure is None:
            plans["ok"] = plan
        return {"ok": plan.failure is None, "stage": rec["stage"]}

    cert = mod.infeasibility_certificate(ctx, group, task) if intent == "intrusion" else None
    out = ({"success": False, "attempts": 0, "records": [], "result": None} if cert is not None
           else run_attempts(key0, attempt_fn, budget=BUDGET))
    failure = None
    if cert is not None:
        failure = {"code": cert.code, "reason": cert.reason, "feasible_set": cert.feasible_set,
                   "witness": jsonable(cert.witness)}
    elif not out["success"]:
        f = final_failure(ctx, group, task, [{"stage": r["stage"]} for r in logs])
        failure = {"code": f.code, "reason": f.reason, "feasible_set": f.feasible_set, "witness": jsonable(f.witness)}
    rec = {"contract_id": contract_id(entry, draw), "intent": intent, "family_id": ctx.family.family_id,
           "order": int(entry["order"]), "draw_index": int(draw), "branch": None,
           "facility_count": int(entry["facility_count"]), "vehicle_count": int(ctx.family.vehicle_count),
           "lateral_spacing_m": float(ctx.family.lateral_spacing_m), "group_id": group.group_id,
           "member_ids": sorted(group.member_ids), "group_size": len(group.member_ids), "target_id": task.target_id,
           "initial_speed_m_s": float(group.speed_profile.initial_speed_m_s), "formation_prior": group.formation_prior,
           "success": bool(out["success"]), "attempts": int(out["attempts"]),
           "shape_audit_failed_attempts": sum(1 for r in logs if r["shape_audit_failed"]),
           "exceptions": sum(1 for r in logs if r["stage"] == "exception"), "failure": failure,
           "attempt_log": [{k: v for k, v in r.items() if k != "timing"} for r in logs],
           "chord_cache": {k: TC.STATS[k] - before.get(k, 0) for k in TC.STATS}}
    if out["success"]:
        plan = plans["ok"]
        last = logs[-1]
        rec["formation"] = {k: plan.formation.get(k) for k in ("prior", "start", "realized", "mapped_from_loose",
                                                               "lateral_step_m")}
        rec["topology"] = dict(plan.topology)
        rec["curved"] = bool(last.get("curved"))
        rec["fallback_reason"] = last.get("fallback_reason")
        rec["lateral_deviation_m"] = last.get("lateral_deviation_m")
        rec["nominal_duration_s"] = float(plan.nominal_duration_s)
        if intent == "intrusion":
            w = plan.witnesses or {}
            rec["sigma"], rec["x_e"] = w.get("sigma"), w.get("x_e")
            rec["terminal"] = jsonable(w.get("terminal"))
            rec["endpoint_distances_m"] = jsonable(w.get("endpoint_distances_m"))
            rec["nominal_screen"] = jsonable({m: v for m, v in sorted((w.get("screen") or {}).items())})
        if intent == "feint":
            w = plan.witnesses or {}
            P = plan.proposal or {}
            rec["feint_turn"] = jsonable({"turn": P.get("turn"), "L_m": P.get("L_m"), "l_star_m": P.get("l_star_m"),
                                          "nonempty_combos": P.get("nonempty_combos"),
                                          "collect_D_m": P.get("collect_D_m"), "schedule": w.get("schedule_feint")})
            rec["nominal_screen"] = jsonable({m: v for m, v in sorted((w.get("screen") or {}).items())})
    if intent == "close_observation" and out["success"]:
        rec["dwell"] = jsonable(plans["ok"].proposal["dwell"])
        rec["dwell_diagnostics"] = jsonable(plans["ok"].witnesses["dwell_diagnostics"])
        rec["nominal_screen"] = jsonable(plans["ok"].witnesses["screen"])
    tele = {"timing": [r.get("timing") for r in logs]}
    if out_dir is not None:
        from .monitoring import plan_to_record
        import numpy as np
        d = Path(out_dir) / "contracts" / rec["contract_id"]
        d.mkdir(parents=True, exist_ok=False)
        (d / "contract.json").write_bytes(contract_bytes({k: rec[k] for k in (
            "contract_id", "intent", "family_id", "order", "draw_index", "facility_count", "vehicle_count", "group_id",
            "member_ids", "group_size", "target_id", "initial_speed_m_s", "formation_prior")}))
        extra = (("dwell", "dwell_diagnostics", "nominal_screen") if intent == "close_observation" else
                 ("sigma", "x_e", "terminal", "endpoint_distances_m", "nominal_screen") if intent == "intrusion" else
                 ("feint_turn", "nominal_screen") if intent == "feint" else ())
        (d / "result.json").write_bytes(contract_bytes({k: rec.get(k) for k in (
            "intent", "success", "attempts", "shape_audit_failed_attempts", "exceptions", "failure", "attempt_log",
            "formation", "topology", "curved", "fallback_reason", "lateral_deviation_m", "nominal_duration_s") + extra}))
        if plans.get("ok") is not None:
            prec, arrays = plan_to_record(plans["ok"])
            prec["arrays"] = {k: np.asarray(v).tolist() for k, v in sorted(arrays.items())}
            (d / "skeleton.json").write_bytes(contract_bytes(prec))
        tdir = Path(out_dir) / "telemetry"
        tdir.mkdir(exist_ok=True)
        (tdir / f"{rec['contract_id']}.json").write_bytes(_json_bytes(tele))
    rec["_timing"] = tele["timing"]
    return rec


def _task(task):
    from ..scene.context import load_context
    entry, d, data_root, cache_dir, out_dir = task[:5]
    intent = task[5] if len(task) > 5 else "transit"
    t0 = time.perf_counter()
    g = globals().setdefault("_WCTX", {})
    try:
        if entry["order"] not in g:
            while len(g) >= 3:
                g.pop(next(iter(g)))
            g[entry["order"]] = load_context(entry, data_root=Path(data_root), cache_dir=Path(cache_dir))
        else:
            g[entry["order"]] = g.pop(entry["order"])
        rec = run_intent_skeleton_contract(g[entry["order"]], entry, d, intent=intent, out_dir=out_dir)
    except Exception:
        from .joint_monitoring import contract_id
        rec = {"contract_id": contract_id(entry, d), "family_id": entry["family_id"], "order": int(entry["order"]),
               "draw_index": d, "success": False, "attempts": 0, "error": traceback.format_exc(), "group_size": None,
               "facility_count": entry["facility_count"], "initial_speed_m_s": None,
               "shape_audit_failed_attempts": 0, "attempt_log": []}
    rec["wall_s"] = time.perf_counter() - t0
    return rec


def fallback_checkpoint(rows):
    succ = [r for r in rows if r.get("success")]
    straight = [r for r in succ if not r.get("curved")]
    reasons = {}
    for r in straight:
        reasons[str(r.get("fallback_reason"))] = reasons.get(str(r.get("fallback_reason")), 0) + 1
    out = {"successes": len(succ), "straight": len(straight), "reasons": dict(sorted(reasons.items())),
           "rate": None, "rate_fraction": None, "triggered": False}
    if succ:
        fr = Fraction(len(straight), len(succ))
        out.update(rate=float(fr), rate_fraction=f"{fr.numerator}/{fr.denominator}", triggered=bool(fr > FALLBACK_MAX))
    return out


def run_transit_skeleton_batch(entries, *, data_root, cache_dir, out_dir, workers=DEFAULT_WORKERS, log=print):
    return run_intent_skeleton_batch(entries, intent="transit", data_root=data_root, cache_dir=cache_dir,
                                     out_dir=out_dir, workers=workers, log=log)


def run_intent_skeleton_batch(entries, *, intent, data_root, cache_dir, out_dir, workers=DEFAULT_WORKERS, log=print, prewarm_doc=None):
    """共享骨架预建和派发；旧 run_transit_skeleton_batch 保留包装。"""
    import multiprocessing as mp
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
    from .joint_intent import _cost_order, prewarm_all
    out = Path(out_dir)
    t_start = time.time()
    if prewarm_doc is not None and intent != "close_observation":
        raise ValueError("prewarm_doc is supported only for close_observation")
    pw = prewarm_doc if prewarm_doc is not None else prewarm_all(entries, data_root=data_root, cache_dir=cache_dir, workers=workers, log=log, intent=intent)
    if intent == "close_observation" and pw["wall_s"] > 2700.0:
        summary = {"stage": "skeleton", "intent": intent, "complete": False, "checkpoint": {"triggered": ["prewarm_wall"]}, "prewarm": pw}
        write_json(out / "summary.json", summary, indent=1)
        return summary
    write_json(out / "prewarm.json", pw, indent=1)
    sizes = {tuple(map(int, k.split(":"))): v for k, v in pw["group_size"].items()}
    ordered = sorted(entries, key=lambda e: e["order"])
    keys = [("full", int(e["order"]), d, None) for e in ordered for d in range(DRAWS)]
    order = _cost_order(entries, keys, sizes)
    write_json(out / "dispatch_order.json", [{"order": x[2], "draw": x[3], "cost": x[0]} for x in order], indent=1)
    t_disp = time.time()
    tasks = [(e, d, str(data_root), str(cache_dir), str(out)) + ((intent,) if intent != "transit" else ())
             for _, _, _, _, _, (_, e, d, _) in order]
    rows = []
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
        it = iter(tasks)
        pending = set()
        for _ in range(workers):
            t = next(it, None)
            if t is None:
                break
            pending.add(ex.submit(_task, t))
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                pending.discard(fut)
                r = fut.result()
                rows.append(r)
                log(f"[{len(rows)}] {r['contract_id']}: success={r.get('success')} attempts={r.get('attempts')} "
                    f"curved={r.get('curved')} fb={r.get('fallback_reason')} shape={r.get('shape_audit_failed_attempts')} "
                    f"err={'yes' if r.get('error') else 'no'} wall={r.get('wall_s', 0):.0f}s", flush=True)
                t = next(it, None)
                if t is not None:
                    pending.add(ex.submit(_task, t))
    rows.sort(key=lambda r: r["contract_id"])
    return write_outputs(out, rows, expected=len(keys), wall_s=time.time() - t_start,
                         dispatch_wall_s=time.time() - t_disp, workers=workers, prewarm=pw, intent=intent)


def _dist(xs):
    from .skeleton_monitoring import _distribution
    return _distribution(xs)


def write_outputs(out, rows, *, expected, wall_s, dispatch_wall_s, workers, prewarm, intent="transit"):
    import csv
    from .skeleton_monitoring import skeleton_checkpoint
    det = [{k: v for k, v in r.items() if k != "_timing"} for r in rows]
    write_json(out / "records.json", det, indent=1)
    with open(out / "attempts.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            log_ = r.get("attempt_log") or []
            tms = r.get("_timing") or [None] * len(log_)
            for a, tm in zip(log_, tms):
                fh.write(json.dumps(jsonable({"contract_id": r["contract_id"], **a, "timing": tm}),
                                    ensure_ascii=False, sort_keys=True) + "\n")
    if intent == "intrusion":
        from .intrusion_report import skeleton_checkpoint as intrusion_skeleton_checkpoint
        chk = intrusion_skeleton_checkpoint(det, expected_count=expected)
        fb = dict(chk["metrics"]["fallback"], triggered="straight_fallback" in chk["triggered"])
        triggered = list(chk["triggered"])
    elif intent == "feint":
        # V8-18 指令 5.2：监视公共检查点（200、无排除）；直线回退只作诊断，不是佯动止损项
        from .feint_report import skeleton_checkpoint as feint_skeleton_checkpoint
        chk = feint_skeleton_checkpoint(det, expected_count=expected)
        fb = dict(fallback_checkpoint(det), triggered=False, diagnostic_only=True)
        triggered = list(chk["triggered"])
    elif intent == "close_observation":
        from .close_observation_report import skeleton_checkpoint as close_skeleton_checkpoint
        chk = close_skeleton_checkpoint(det, expected_count=expected)
        fb = dict(fallback_checkpoint(det), triggered=False, diagnostic_only=True)
        triggered = list(chk["triggered"]) + (["skeleton_wall"] if dispatch_wall_s > 1800.0 else [])
    else:
        chk = skeleton_checkpoint(det, expected_count=expected)
        fb = fallback_checkpoint(det)
        triggered = list(chk["triggered"]) + (["straight_fallback"] if fb["triggered"] else [])
    logs = [a for r in rows for a in (r.get("attempt_log") or [])]
    stages = {}
    for a in logs:
        stages[a["stage"]] = stages.get(a["stage"], 0) + 1
    cross = {}
    for r in rows:
        if r.get("success"):
            f = r.get("formation") or {}
            k = f"{f.get('prior')}->{f.get('realized')}"
            cross[k] = cross.get(k, 0) + 1
    timings = [tm for r in rows for tm in (r.get("_timing") or []) if tm]
    succ = [r for r in rows if r.get("success")]
    cells = {}
    for r in rows:
        for a in r.get("attempt_log") or []:
            for st in a.get("formation_steps") or []:
                key = f"{r['family_id']}|{r['target_id']}|n{r['group_size']}|{st.get('formation')}|{st.get('lateral_step_m')}"
                cells[key] = {"feasible_cells": st.get("feasible_cells"), "n_cells": st.get("n_cells")}
            break
    summary = {"stage": "skeleton", "intent": intent, "expected_count": expected, "completed": len(rows),
               "complete": chk["complete"], "checkpoint": {**chk, "triggered": triggered, "fallback": fb},
               "wall_s": wall_s, "dispatch_wall_s": dispatch_wall_s, "workers": workers,
               "prewarm": {k: prewarm[k] for k in ("families", "wall_s", "queries_total", "queries_written",
                                                   "query_build_s")},
               "errors": [r["contract_id"] for r in rows if r.get("error")],
               "exceptions_attempts": sum(int(r.get("exceptions") or 0) for r in rows),
               "attempts_total": len(logs), "attempt_stages": dict(sorted(stages.items())),
               "prior_to_realized": dict(sorted(cross.items())),
               "lateral_deviation_m": _dist([r.get("lateral_deviation_m") for r in succ]),
               "corridor_certified_ratio": _dist([(a.get("corridor") or {}).get("certified_length_m") /
                                                  (a.get("corridor") or {}).get("inset_length_m")
                                                  for r in succ for a in r["attempt_log"][-1:]
                                                  if (a.get("corridor") or {}).get("inset_length_m")]),
               "corridor_certified_length_m": _dist([(a.get("corridor") or {}).get("certified_length_m")
                                                     for r in succ for a in r["attempt_log"][-1:]]),
               "lp_seconds": _dist([tm.get("lp_s") for tm in timings if tm.get("lp_s") is not None]),
               "timing": {k: _dist([tm.get(k) for tm in timings]) for k in (
                   "attempt_wall_s", "chord_set_s", "chord_exact_s", "corridor_s", "lp_s", "route_s", "candidate_s")},
               "route_queries": _sum_dicts([tm.get("route_queries") or {} for tm in timings]),
               "chord_cache": _sum_dicts([r.get("chord_cache") or {} for r in rows]),
               "feasible_cells": cells,
               "contract_wall_s": _dist([r.get("wall_s") for r in rows])}
    write_json(out / "summary.json", summary, indent=1)
    with open(out / "by_bin.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["axis", "bin", "contracts", "successes", "rate", "gap_vs_overall", "success_attempts_median",
                    "attempts_total"])
        for axis in ("group", "facility", "speed"):
            for b, v in (chk["metrics"].get(f"{axis}_bins") or {}).items():
                w.writerow([axis, b, v["n"], v["successes"], f"{v['rate']:.6f}", f"{v['gap']:.6f}",
                            v["success_attempts_median"], v["attempts_total"]])
    return summary


def _sum_dicts(ds):
    out = {}
    for d in ds:
        for k, v in d.items():
            out[k] = out.get(k, 0) + v
    return dict(sorted(out.items()))
