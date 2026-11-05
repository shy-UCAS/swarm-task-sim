"""V8-14 第 6 部分：只构造骨架的批次与 U D.5 止损检查点（指令 6.1–6.3）。

每合同沿用 joint_monitoring.run_attempts（唯一预算 20），attempt_fn 只调用一次 plan_attempt：不优化、不仿真，
不以名义判据、间距或时长拒绝。骨架成功 = 完整 SegmentPlan.failure is None（起点路由、入/出圈、变队形与完整几何
构造全部完成）。同族 5 合同在同一 worker 顺序执行，跨族并行（沿用 V8-13 的同族串行修复）。

检查点阈值（U D.5，严格比较，Fraction）：骨架合同成功率 < 95%；任一人数档成功率比总体低 > 10 个百分点；
成功合同骨架尝试次数中位数 > 1；形状复核失败率（分母为全部骨架 attempt）> 5%。
本模块导入时不读数据、不建目录。
"""
import json
import time
import traceback
from fractions import Fraction
from pathlib import Path
from statistics import median

from .runtime_defaults import DEFAULT_WORKERS

SUCCESS_FLOOR = Fraction(95, 100)        # U D.5
GROUP_GAP = Fraction(10, 100)            # U D.5：10 个百分点
ATTEMPT_MEDIAN = 1                       # U D.5
SHAPE_AUDIT_RATE = Fraction(5, 100)      # U D.5
TRIGGERS = ("success_rate", "group_gap", "attempts", "shape_audit")
EXPECTED = 200


def _group_bin(n):
    from .joint_report import group_bin
    return group_bin(n)


def skeleton_checkpoint(records, *, expected_count=EXPECTED):
    """records 每行至少含 contract_id, success, attempts, group_size, facility_count, initial_speed_m_s,
    shape_audit_failed_attempts。返回 {"complete", "triggered", "metrics"}；未完成/缺记录/实现异常保留在 complete。"""
    from .joint_report import group_bin, speed_bin
    rows = list(records)
    ids = [r.get("contract_id") for r in rows]
    incomplete = [r.get("contract_id") for r in rows if r.get("incomplete") or r.get("error")]
    complete = (len(rows) == int(expected_count) and len(set(ids)) == len(ids) and not incomplete)
    n = len(rows)
    succ = [r for r in rows if r.get("success")]
    trig = []
    metrics = {"contracts": n, "expected": int(expected_count), "successes": len(succ), "incomplete": incomplete}
    if n:
        rate = Fraction(len(succ), n)
        metrics["success_rate"] = float(rate)
        metrics["success_rate_fraction"] = f"{rate.numerator}/{rate.denominator}"
        if rate < SUCCESS_FLOOR:
            trig.append("success_rate")
        for name, key in (("group", lambda r: group_bin(r["group_size"])),
                          ("facility", lambda r: int(r["facility_count"])),
                          ("speed", lambda r: speed_bin(r["initial_speed_m_s"]))):
            bins = {}
            for r in rows:
                bins.setdefault(key(r), []).append(r)
            out, worst = {}, None
            for b, rs in sorted(bins.items()):
                br = Fraction(sum(bool(x.get("success")) for x in rs), len(rs))
                gap = rate - br
                att = [x["attempts"] for x in rs if x.get("success")]
                out[str(b)] = {"n": len(rs), "successes": sum(bool(x.get("success")) for x in rs),
                               "rate": float(br), "gap": float(gap),
                               "success_attempts_median": median(att) if att else None,
                               "attempts_total": sum(int(x.get("attempts") or 0) for x in rs)}
                worst = gap if worst is None or gap > worst else worst
            metrics[f"{name}_bins"] = out
            if name == "group" and worst is not None and worst > GROUP_GAP:
                trig.append("group_gap")
    att = [r["attempts"] for r in succ]
    med = median(att) if att else None
    metrics["success_attempts_median"] = med
    if med is not None and med > ATTEMPT_MEDIAN:
        trig.append("attempts")
    total_attempts = sum(int(r.get("attempts") or 0) for r in rows)
    shape = sum(int(r.get("shape_audit_failed_attempts") or 0) for r in rows)
    metrics["skeleton_attempts_total"] = total_attempts
    metrics["shape_audit_failed_attempts"] = shape
    if total_attempts:
        sr = Fraction(shape, total_attempts)
        metrics["shape_audit_rate"] = float(sr)
        if sr > SHAPE_AUDIT_RATE:
            trig.append("shape_audit")
    else:
        metrics["shape_audit_rate"] = None
    return {"complete": bool(complete), "triggered": trig, "metrics": metrics}


# ================================================================ 只骨架批次（指令 6.1、6.3）

DRAWS = 5
BUDGET = 20


def _cid(entry, draw):
    from .joint_monitoring import contract_id
    return contract_id(entry, draw)


def _summarize_attempt(a, plan, timing, exc_text=None):
    """一个骨架 attempt 的记录（确定性部分；timing 遥测另存，不进确定性载荷）。"""
    from .monitoring import jsonable
    if exc_text is not None:
        return {"attempt": a, "ok": False, "stage": "exception", "code": "implementation_error", "reason": exc_text,
                "shape_audit_failed": False, "shape_audit_entered": None, "formation": None, "timing": timing}
    f = plan.failure
    w = (f.witness or {}) if f is not None else (plan.witnesses or {})
    diag = w.get("skeleton_diag") or {}
    rec = {"attempt": a, "ok": f is None,
           "stage": "skeleton_ok" if f is None else w.get("stage", f.feasible_set),
           "code": None if f is None else f.code, "reason": None if f is None else f.reason,
           "feasible_set": None if f is None else f.feasible_set,
           "shape_audit_entered": bool(diag.get("shape_audit_entered", False)),
           "shape_audit_failed": bool(diag.get("shape_audit_failed", False) or w.get("shape_audit_failed", False)),
           "shape_audit_reasons": ((w.get("audit") or {}).get("reasons")),
           "shape_audit_kappa": None if not w.get("audit") else {k: w["audit"].get(k) for k in ("kpos", "kneg", "limit")},
           "formation": diag.get("formation"), "lateral_step_m": diag.get("lateral_step_m"),
           "topology": diag.get("topology"), "forced": diag.get("forced"),
           "formation_steps": [{k: st.get(k) for k in ("formation", "lateral_step_m", "found")}
                               for st in diag.get("formation_steps") or []],
           "certificate": diag.get("certificate"), "candidates_certified": diag.get("candidates_certified"),
           "lp": diag.get("lp"), "exact_curvature": diag.get("exact_curvature"),
           "draw": w.get("draw"), "timing": timing}
    if f is None:
        turns = (plan.proposal.get("topology_info") or {}).get("turns") or []
        rec["turns"] = [{"kind": t["kind"], "side": t["side"], "radius_m": t["radius_m"],
                         "merge_distance_m": t["merge_distance_m"], "nonempty_combos": t["query"]["nonempty_combos"],
                         "grid": [[c["kind"], c["side"], c["grid_total"], c["visited"], c["full_certified"],
                                   c["feasible_found"]] for c in t["query"]["combos"]]} for t in turns]
        rec["repairs"] = jsonable(list(plan.repairs))
    else:
        tq = w.get("turn_query")
        if tq:
            q = tq.get("query") or {}
            rec["turn_query"] = {"turn_index": tq.get("turn_index"), "nonempty_combos": q.get("nonempty_combos"),
                                 "collapse_ok": q.get("collapse_ok"), "merge_points": q.get("merge_points"),
                                 "L_m": q.get("L_m"), "width_m": q.get("width_m"),
                                 "grid": [[c["kind"], c["side"], c["grid_total"], c["visited"], c["full_certified"]]
                                          for c in q.get("combos") or []]}
    return jsonable(rec)


def run_skeleton_contract(ctx, entry, draw, *, out_dir=None):
    """一个合同：唯一 20 次预算，每 attempt 只调用一次 plan_attempt（不优化、不仿真）。返回记录 dict。"""
    from ..contract.monitoring import initial_states, monitoring_mission
    from ..motion.intents.monitoring import last_attempt_timing
    from ..motion.plan import final_failure, plan_attempt
    from ..sampler.common import sample_common
    from ..sampler.keys import RngKey
    from .joint_monitoring import run_attempts
    from .monitoring import jsonable
    common = sample_common(ctx.family, draw)
    mission = monitoring_mission(ctx, common)
    group, task = mission.groups[0], mission.tasks[0]
    states = initial_states(ctx.family, group.member_ids)
    key0 = RngKey(ctx.family.family_id, int(draw), "shape", mission=0, branch=None, group=group.group_id, segment=0)
    logs, plans = [], {}

    def attempt_fn(k):
        t0 = time.perf_counter()
        try:
            plan = plan_attempt(ctx, group, task, states, (), k)
        except Exception:
            rec = _summarize_attempt(k.attempt, None, {"attempt_wall_s": time.perf_counter() - t0},
                                     exc_text=traceback.format_exc())
            logs.append(rec)
            return {"ok": False, "stage": "exception"}
        timing = {"attempt_wall_s": time.perf_counter() - t0, **last_attempt_timing()}
        rec = _summarize_attempt(k.attempt, plan, timing)
        logs.append(rec)
        if plan.failure is None:
            plans["ok"] = plan
        return {"ok": plan.failure is None, "stage": rec["stage"]}

    out = run_attempts(key0, attempt_fn, budget=BUDGET)
    failure = None
    if not out["success"]:
        f = final_failure(ctx, group, task, [{"stage": r["stage"]} for r in logs])
        failure = {"code": f.code, "reason": f.reason, "feasible_set": f.feasible_set, "witness": jsonable(f.witness)}
    rec = {"contract_id": _cid(entry, draw), "family_id": ctx.family.family_id, "order": int(entry["order"]),
           "draw_index": int(draw), "facility_count": int(entry["facility_count"]),
           "vehicle_count": int(ctx.family.vehicle_count), "lateral_spacing_m": float(ctx.family.lateral_spacing_m),
           "group_id": group.group_id, "member_ids": sorted(group.member_ids), "group_size": len(group.member_ids),
           "target_id": task.target_id, "initial_speed_m_s": float(group.speed_profile.initial_speed_m_s),
           "formation_prior": group.formation_prior, "success": bool(out["success"]), "attempts": int(out["attempts"]),
           "shape_audit_failed_attempts": sum(1 for r in logs if r["shape_audit_failed"]),
           "exceptions": sum(1 for r in logs if r["stage"] == "exception"),
           "failure": failure, "attempt_log": [{k: v for k, v in r.items() if k != "timing"} for r in logs]}
    if out["success"]:
        plan = plans["ok"]
        rec["formation"] = {k: plan.formation.get(k) for k in ("prior", "start", "realized", "mapped_from_loose",
                                                               "lateral_step_m")}
        rec["topology"] = {k: plan.topology.get(k) for k in ("final", "laps", "traversals", "prior_draw", "forced",
                                                              "forced_reason")}
        rec["nominal_duration_s"] = float(plan.nominal_duration_s)
    tele = {"timing": [r.get("timing") for r in logs]}
    if out_dir is not None:
        _save(Path(out_dir), rec, plans.get("ok"), tele)
    rec["_timing"] = tele["timing"]
    return rec


def _save(out, rec, plan, tele):
    import numpy as np
    from .joint_monitoring import _json_bytes
    from .monitoring import plan_to_record
    d = out / "contracts" / rec["contract_id"]
    d.mkdir(parents=True, exist_ok=False)
    (d / "contract.json").write_bytes(_json_bytes({k: rec[k] for k in (
        "contract_id", "family_id", "order", "draw_index", "facility_count", "vehicle_count", "group_id",
        "member_ids", "group_size", "target_id", "initial_speed_m_s", "formation_prior")}))
    (d / "result.json").write_bytes(_json_bytes({k: rec.get(k) for k in (
        "success", "attempts", "shape_audit_failed_attempts", "exceptions", "failure", "attempt_log", "formation",
        "topology", "nominal_duration_s")}))
    if plan is not None:
        prec, arrays = plan_to_record(plan)
        prec["arrays"] = {k: np.asarray(v).tolist() for k, v in sorted(arrays.items())}
        (d / "skeleton.json").write_bytes(_json_bytes(prec))
    tdir = out / "telemetry"
    tdir.mkdir(exist_ok=True)
    (tdir / f"{rec['contract_id']}.json").write_bytes(_json_bytes(tele))


def _error_row(entry, d, tb):
    return {"contract_id": _cid(entry, d), "family_id": entry["family_id"], "order": int(entry["order"]),
            "draw_index": d, "success": False, "attempts": 0, "error": tb, "group_size": None,
            "facility_count": entry["facility_count"], "initial_speed_m_s": None, "shape_audit_failed_attempts": 0,
            "attempt_log": []}


def _family_task(task):
    """同一族 5 合同在同一进程顺序执行（V8-13 同族串行修复：场景缓存按单进程设计）。"""
    from ..scene.context import load_context
    entry, draws, data_root, cache_dir, out_dir = task
    rows = []
    try:
        ctx = load_context(entry, data_root=Path(data_root), cache_dir=Path(cache_dir))
    except Exception:
        tb = traceback.format_exc()
        return [_error_row(entry, d, tb) for d in draws]
    for d in draws:
        t0 = time.perf_counter()
        try:
            rec = run_skeleton_contract(ctx, entry, d, out_dir=out_dir)
        except Exception:
            rec = _error_row(entry, d, traceback.format_exc())
        rec["wall_s"] = time.perf_counter() - t0
        rows.append(rec)
    return rows


def run_skeleton_batch(entries, *, data_root, cache_dir, out_dir, workers=DEFAULT_WORKERS, draws=DRAWS, log=print):
    """40 族 × draw 0..4，族为单位派发到 workers 个进程（spawn）；按业务键排序写出。返回 summary。"""
    import multiprocessing as mp
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
    out = Path(out_dir)
    ordered = sorted(entries, key=lambda e: e["order"])
    tasks = [(e, list(range(draws)), str(data_root), str(cache_dir), str(out)) for e in ordered]
    t_start = time.time()
    rows = []
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
        it = iter(tasks)
        pending = set()
        for _ in range(workers):
            t = next(it, None)
            if t is None:
                break
            pending.add(ex.submit(_family_task, t))
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                pending.discard(fut)
                for r in fut.result():
                    rows.append(r)
                    log(f"[{len(rows)}] {r['contract_id']}: success={r.get('success')} attempts={r.get('attempts')} "
                        f"shape={r.get('shape_audit_failed_attempts')} err={'yes' if r.get('error') else 'no'} "
                        f"wall={r.get('wall_s', 0):.0f}s", flush=True)
                t = next(it, None)
                if t is not None:
                    pending.add(ex.submit(_family_task, t))
    rows.sort(key=lambda r: r["contract_id"])
    return write_outputs(out, rows, expected=len(ordered) * draws, wall_s=time.time() - t_start, workers=workers)


def _distribution(xs):
    xs = sorted(float(x) for x in xs if x is not None)
    if not xs:
        return None
    pick = lambda p: xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]
    return {"n": len(xs), "min": xs[0], "p10": pick(.1), "p50": pick(.5), "p90": pick(.9), "max": xs[-1]}


def write_outputs(out, rows, *, expected, wall_s, workers):
    """records.json、attempts.jsonl、summary.json、by_bin.csv、failures.csv。"""
    import csv
    from .monitoring import jsonable, write_json
    det = [{k: v for k, v in r.items() if k != "_timing"} for r in rows]
    write_json(out / "records.json", det, indent=1)
    with open(out / "attempts.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            log_ = r.get("attempt_log") or []
            tms = r.get("_timing") or [None] * len(log_)
            for a, tm in zip(log_, tms):
                fh.write(json.dumps(jsonable({"contract_id": r["contract_id"], **a, "timing": tm}),
                                    ensure_ascii=False, sort_keys=True) + "\n")
    chk = skeleton_checkpoint(det, expected_count=expected)
    logs = [a for r in rows for a in (r.get("attempt_log") or [])]
    stages, reasons, forms, retreat, steps, topo = {}, {}, {}, {}, [], {}
    for a in logs:
        stages[a["stage"]] = stages.get(a["stage"], 0) + 1
        for x in a.get("shape_audit_reasons") or []:
            reasons[x] = reasons.get(x, 0) + 1
    for r in rows:
        if r.get("success"):
            f = r.get("formation") or {}
            forms[f.get("realized")] = forms.get(f.get("realized"), 0) + 1
            key = f"{f.get('start')}->{f.get('realized')}"
            retreat[key] = retreat.get(key, 0) + 1
            if f.get("realized") == "echelon" and f.get("lateral_step_m") is not None:
                steps.append(f["lateral_step_m"])
            t = (r.get("topology") or {}).get("final")
            topo[t] = topo.get(t, 0) + 1
    timings = [tm for r in rows for tm in (r.get("_timing") or []) if tm]
    cert = [a["certificate"] for a in logs if a.get("certificate")]
    turns = [t for a in logs for t in (a.get("turns") or [])]
    summary = {"stage": "skeleton", "expected_count": expected, "completed": len(rows),
               "complete": chk["complete"], "checkpoint": chk, "wall_s": wall_s, "workers": workers,
               "errors": [r["contract_id"] for r in rows if r.get("error")],
               "exceptions_attempts": sum(int(r.get("exceptions") or 0) for r in rows),
               "attempts_total": len(logs), "attempt_stages": stages, "shape_audit_reasons": reasons,
               "formation_realized": forms, "formation_retreat": retreat, "echelon_steps_m": _distribution(steps),
               "topology_final": topo,
               "certificate": {k: _distribution([c.get(k) for c in cert]) for k in (
                   "q_m", "eta_m", "threshold_m", "half_span_m", "e_geom_m", "e_smooth_m", "e_m", "min_slack_m")},
               "turns": {"count": len(turns),
                         "kinds": {k: sum(1 for t in turns if t["kind"] == k) for k in ("teardrop", "u", "oblique")},
                         "nonempty_combos": _distribution([t["nonempty_combos"] for t in turns]),
                         "grid_total": _distribution([g[2] for t in turns for g in t["grid"]]),
                         "visited": _distribution([g[3] for t in turns for g in t["grid"]])},
               "timing": {k: _distribution([tm.get(k) for tm in timings]) for k in (
                   "attempt_wall_s", "band_geometry_s", "band_query_s", "turn_query_s", "lp_seconds", "lp_calls",
                   "lp_feasibility_calls", "lp_construct_s")},
               "exact_curvature_min_radius_m": _distribution([(a.get("exact_curvature") or {}).get("min_radius_m")
                                                              for a in logs]),
               "contract_wall_s": _distribution([r.get("wall_s") for r in rows])}
    write_json(out / "summary.json", summary, indent=1)
    with open(out / "by_bin.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["axis", "bin", "contracts", "successes", "rate", "gap_vs_overall", "success_attempts_median",
                    "attempts_total"])
        for axis in ("group", "facility", "speed"):
            for b, v in (chk["metrics"].get(f"{axis}_bins") or {}).items():
                w.writerow([axis, b, v["n"], v["successes"], f"{v['rate']:.6f}", f"{v['gap']:.6f}",
                            v["success_attempts_median"], v["attempts_total"]])
    with open(out / "failures.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["contract_id", "group_size", "facility_count", "initial_speed_m_s", "attempts", "final_code",
                    "stages", "shape_audit_failed_attempts", "error"])
        for r in rows:
            if r.get("success"):
                continue
            st = {}
            for a in r.get("attempt_log") or []:
                st[a["stage"]] = st.get(a["stage"], 0) + 1
            w.writerow([r["contract_id"], r.get("group_size"), r.get("facility_count"), r.get("initial_speed_m_s"),
                        r.get("attempts"), (r.get("failure") or {}).get("code"),
                        ";".join(f"{k}:{v}" for k, v in sorted(st.items())), r.get("shape_audit_failed_attempts"),
                        "yes" if r.get("error") else ""])
    return summary


def cli(args, out):
    """--devset --data-root --cache --out --workers。退出码：0 完成且未触发、2 诊断触发、3 未完成、1 参数/路径。"""
    import sys
    from .monitoring import guard_path, load_entries
    data_root = Path(args.data_root)
    cache = guard_path(args.cache, label="缓存", data_root=data_root)
    entries = load_entries(args.devset)
    out.mkdir(parents=True, exist_ok=False)
    summary = run_skeleton_batch(entries, data_root=data_root, cache_dir=cache, out_dir=out, workers=args.workers)
    chk = summary["checkpoint"]
    m = chk["metrics"]
    print("骨架检查点（U D.5）：", json.dumps({"complete": chk["complete"], "triggered": chk["triggered"],
                                           "contracts": m.get("contracts"), "successes": m.get("successes"),
                                           "success_rate": m.get("success_rate_fraction"),
                                           "success_attempts_median": m.get("success_attempts_median"),
                                           "shape_audit": [m.get("shape_audit_failed_attempts"),
                                                           m.get("skeleton_attempts_total")]},
                                          ensure_ascii=False))
    if not chk["complete"]:
        return 3
    return 2 if chk["triggered"] else 0
