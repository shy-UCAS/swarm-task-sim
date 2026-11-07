"""佯动单段：一次提案、参考装配、成员映射、finish、失败分类与遥测（V8-18 指令 3.4–3.5、4.1；本项新增）。

一个 attempt 的 RNG 顺序（指令 3.4，全部用现有键）：
  1. formation 流确定槽位序，全部 probe 共用；
  2. shape 流在非空格列表上 integers(0, len(cells)) 一次；
  3. connect 流按 MT 种类/侧向顺序，对每组完整 (A, R) 网格 permutation(n) 一次，依排列认证、取首个通过记录
     （feint_turn.sample_turn_grid；无候选的组合不调用 RNG）；
  4. 直接调用 MT.choose_joint_turn 在非空组合中等概率选一个（组内仍保留其自身 RNG 调用）；
  5. shape 流在选中记录兼容的 D_c 中均匀选一个，再抽 K 与原 logit 分位数；connect 流随后用于路由；speed 流沿用
     原 Poisson 事件（transit.build_candidate）。
预建只存存在性；生产抽到的格若在同谓词下六组合全空，属于实现/缓存一致性问题，留证结束该 attempt，不换格。
任何下游失败原样结束 attempt；唯一 20 次预算由 run_attempts 管理。

队形：retreat_chain(mapped_start(prior))，loose 按 abreast；梯形照 transit._echelon_payload 二分。宽度可行 = 该队形
存在至少一格完整佯动掉头（feint_chords.load_chord_set 非空）；只有它触发退让。
共享步骤直接调用：TransitSetup（feint base 与 cg_route）、corridor_rows（intrusion/feint 同一入口范围）、curve_lp /
exact_curve_audit、plan_starts + transit._transit_route、preentry_clearance_ok、transit.build_candidate（feint 回调：
build_reference / member_lanes / finish_candidate；速度事件按 s_group 映射）。
"""
import math
import time
from dataclasses import replace

import numpy as np

from ...contract.monitoring import Failure, SegmentPlan
from ...sampler.keys import RngKey
from ...scene.exact import signed_distance
from .. import feint_chords as FC
from .. import feint_turn as FT
from .. import intrusion_numeric as IN
from .. import monitoring_turn as MT
from .. import transit_chords as TC
from ..connect import crossing_analysis
from ..formation import formation_slots, make_reference, mapped_start, retreat_chain
from ..nominal import sample_nominal
from ..path import PathError, Sampled, sample_primitives
from ..shared_routes import plan_starts
from ..skeleton import width_then_build
from ..transit_numeric import curve_lp, exact_curve_audit
from . import transit as T
from .monitoring import TURN_MIN_KEYS, _key_dict

_LAST_TIMING = {}


def last_attempt_timing():
    """本进程最近一次佯动 propose_and_build 的分阶段墙钟（遥测，不进入确定性载荷）。"""
    return dict(_LAST_TIMING)


# ---------------------------------------------------------------- 失败、摘要

def final_failure(ctx, group, task, attempt_records):
    """沿 S：全部 attempt 都在所有队形离散格为空的 feint_chord_set 阶段失败 → approx_empty（有限网格为空不证明连续域
    为空）；其余用完预算 → budget_exhausted。本项没有精确不可行证书，不输出 proven_infeasible。"""
    stages = {r["stage"] for r in attempt_records}
    n = len(attempt_records)
    if n and stages == {"feint_chord_set"}:
        return Failure("approx_empty", "全部 attempt 在所有队形下佯动离散格（航向×偏移×A×种类×侧向×R）均无完整可行掉头；"
                                       "不证明连续可行域为空", "feint_chord_set", {"attempts": n}, None)
    return Failure("budget_exhausted", f"{n} 次随机构造用完预算", "random_construction",
                   {"attempts": n, "stages": sorted(str(s) for s in stages)}, None)


def draw_summary(P, formation):
    P = P or {}
    turn = P.get("turn") or {}
    return {"intent": "feint", "formation": formation, "theta_deg": P.get("theta_deg"), "h_m": P.get("h_m"),
            "cell_index": P.get("cell_index"), "cells_feasible": P.get("cells_feasible"),
            "turn_kind": turn.get("kind"), "turn_side": turn.get("side"), "radius_m": turn.get("radius_m"),
            "A_m": turn.get("A_m"), "nonempty_combos": P.get("nonempty_combos"), "collect_D_m": P.get("collect_D_m"),
            "collect_candidates": P.get("collect_candidates"), "K": P.get("K"),
            "logit_quantiles": P.get("logit_quantiles"), "curved": P.get("curved"),
            "fallback_reason": P.get("fallback_reason")}


# ---------------------------------------------------------------- 队形 probe

def formation_probe_sequence(ctx, group, task, key):
    """确定性选队形 probe 序列（主进程预建与 worker 共用）：[(formation, lateral_step, offsets, spacing)]，
    按 width_then_build 的实际调用次序，直到第一个非空集合为止。"""
    fam = ctx.family
    chain = retreat_chain(mapped_start(group.formation_prior))
    b = float(fam.lateral_spacing_m)
    fkey = RngKey(key.family_id, key.draw, "formation", mission=key.mission, branch=key.branch, group=key.group,
                  segment=key.segment, attempt=key.attempt)
    order = formation_slots(group, fam, fkey, formation=chain[0]).order
    seq = []

    def probe(name, step):
        slots = formation_slots(group, fam, fkey, formation=name, lateral_step_m=step, order=order)
        offs, spacing = FC.request_for(slots)
        seq.append((name, step, offs, spacing))
        doc = FC.load_chord_set(ctx, task.target_id, slots, ctx.cache_dir)
        return {"slots": slots, "doc": doc} if doc["cells"] else None

    def width_probe(name):
        if name == "echelon":
            return T._echelon_payload(probe, group, b, [])
        return probe(name, None)

    width_then_build(chain, width_probe, lambda name, payload: payload)
    return seq


# ---------------------------------------------------------------- 一次 attempt

def propose_and_build(ctx, group, task, states, key):
    """一次随机构造：宽度先定队形 → 格 → 各组合排列认证 → 非空组合等概率 → D_c、K、logit → 走廊与一次 LP（不可用即
    同格直线）→ 曲线精确复核 → 初始可视图路由 → 进场精确检查 → 共享候选构造（feint 回调）。下游失败原样返回。"""
    S = T.TransitSetup(ctx, group, task, states, key)
    _LAST_TIMING.clear()
    t_all = time.perf_counter()
    try:
        rng, crng = S.rng("shape"), S.rng("connect")
        fam = ctx.family
        chain = retreat_chain(mapped_start(group.formation_prior))
        b = float(fam.lateral_spacing_m)
        fkey = RngKey(key.family_id, key.draw, "formation", mission=key.mission, branch=key.branch, group=key.group,
                      segment=key.segment, attempt=key.attempt)
        order = formation_slots(group, fam, fkey, formation=chain[0]).order
        steps_log = []

        def probe(name, step):
            t0 = time.perf_counter()
            slots = formation_slots(group, fam, fkey, formation=name, lateral_step_m=step, order=order)
            doc = FC.load_chord_set(ctx, task.target_id, slots, ctx.cache_dir)
            T._tick(S, "chord_set_s", time.perf_counter() - t0)
            steps_log.append({"formation": name, "lateral_step_m": step, "feasible_cells": len(doc["cells"]),
                              "n_cells": doc["n_cells"], "query_id": doc.get("query_id"),
                              "reasons": doc.get("reasons")})
            return {"slots": slots, "doc": doc, "lateral_step_m": step} if doc["cells"] else None

        def width_probe(name):
            if name == "echelon":
                return T._echelon_payload(probe, group, b, steps_log)
            return probe(name, None)

        def build(name, payload):
            return _build_with_cells(S, ctx, group, task, states, key, payload, b, steps_log, rng, crng)

        plan = width_then_build(chain, width_probe, build)
        if plan is not None:
            return plan
        return T._stage_fail("feint_chord_set", "所有队形下佯动离散格均无完整可行掉头（approx_empty 查询）", None, key,
                             {"formations": steps_log, "shape_audit_failed": False})
    finally:
        S.timing["attempt_s"] = time.perf_counter() - t_all
        S.timing["route_queries"] = dict(S.stats)
        _LAST_TIMING.update(S.timing)


def _build_with_cells(S, ctx, group, task, states, key, payload, b, steps_log, rng, crng):
    slots, doc = payload["slots"], payload["doc"]
    cells = doc["cells"]
    tgt = S.tgt
    repairs = []
    if slots.realized != slots.start:
        repairs.append({"kind": "formation_retreat", "from": slots.start, "to": slots.realized, "forced_by": "width"})
    used = payload.get("lateral_step_m")
    if used is not None and used < b - 1e-9:
        repairs.append({"kind": "echelon_lateral_step", "from_m": b, "to_m": used})
    ci = int(rng.integers(0, len(cells)))                                      # 2. 格
    cell = {k: cells[ci][k] for k in ("theta_idx", "h_m", "x_in", "collect_D_candidates")}
    ti, h, x_in = int(cell["theta_idx"]), float(cell["h_m"]), float(cell["x_in"])
    th = TC.thetas()[ti]
    u, n = TC.frame(th)
    o = np.asarray(tgt.center, float)
    P = {"intent": "feint", "theta_idx": ti, "theta_deg": float(TC.THETA_STEP_DEG * ti), "h_m": h,
         "origin_xy": tuple(map(float, o)), "u": tuple(map(float, u)), "n": tuple(map(float, n)),
         "cell_index": ci, "cells_feasible": len(cells), "chord_query_id": doc.get("query_id"), "x_in": x_in,
         "member_slot_order": slots.order, "formation": slots.realized,
         "lateral_step_m": slots.lateral_step_m if slots.realized == "echelon" else None,
         "repairs": tuple(repairs), "formation_steps": steps_log}
    # 3–4. 各组合排列认证 → 非空组合等概率（同一谓词：screened + 剪枝，与预建相同）
    t0 = time.perf_counter()
    grids = FT.candidate_grid(ctx, task, slots, cell)
    found = []

    def certify(c):
        got = FT.certify_candidate(ctx, task, slots, cell, c, mode=FC.CERT_MODE, prune=FC.CERT_PRUNE)
        if got["feasible"]:
            found.append((got["record"]["kind"], got["record"]["side"]))
            return got["record"]
        return None
    rec = FT.sample_turn_grid(grids, certify, crng)
    T._tick(S, "turn_sample_s", time.perf_counter() - t0)
    P["grid_sizes"] = {f"{k}:{s}": len(v) for (k, s), v in grids.items()}
    P["nonempty_combos"] = len(found)
    P["combos_found"] = [[k, int(s)] for k, s in found]
    if rec is None:
        return T._stage_fail("feint_turn_consistency", "预建为可行格，但同谓词下六组合全空（实现/缓存一致性问题，不换格）",
                             P, key, {"cell": cell, "shape_audit_failed": False, "draw": draw_summary(P, slots.realized)})
    Ds = list(rec["collect_D_compatible"])
    D_c = float(Ds[int(rng.integers(0, len(Ds)))])                              # 5. D_c、K、logit
    kmin, kmax = int(S.M["spline_basis_min"]), int(S.M["spline_basis_max"])
    K = int(rng.integers(kmin, kmax + 1))
    v = rng.random(K)
    z = T._logit(v)
    xc = x_in - D_c
    P.update({"turn": {"A_m": rec["A_m"], "kind": rec["kind"], "side": int(rec["side"]), "radius_m": rec["radius_m"]},
              "turn_primitives": rec["primitives"], "landmarks_xy": rec["landmarks_xy"],
              "exit_heading_rad": rec["exit_heading_rad"], "terminal_x": rec["terminal_x"],
              "L_m": rec["L_m"], "l_star_m": rec["l_star_m"], "turn_schedule_certificate": rec["schedule"],
              "collect_D_m": D_c, "collect_candidates": len(Ds), "x_c": xc, "K": K,
              "logit_quantiles": tuple(map(float, v)), "logit_coefficients": tuple(map(float, z))})
    ent = TC.line_sublevel(tgt.layers["warning"], o + h * n, u, 0.0)
    P["x_entry_ref"] = float(ent[0]) if ent is not None else None
    E = np.asarray(rec["landmarks_xy"]["E"], float)
    u_out = np.array([math.cos(rec["exit_heading_rad"]), math.sin(rec["exit_heading_rad"])])
    ext_iv = TC.line_sublevel(tgt.layers["warning"], E, u_out, 0.0)
    P["x_exit_ref"] = float(ext_iv[1]) if ext_iv is not None else None
    # 走廊与一次 LP（corridor_rows 在 intent ∈ {intrusion, feint} 时用 alert 正次水平集作上界）
    t0 = time.perf_counter()
    cor = TC.corridor_rows(ctx, task, {"theta_idx": ti, "h": h}, slots)
    T._tick(S, "corridor_s", time.perf_counter() - t0)
    P["corridor"] = {k: cor[k] for k in ("available", "reason", "D", "inset_interval", "rows_total", "certified_rows",
                                         "run", "certified_length_m", "inset_length_m")}
    P["corridor"]["alert_interval"] = cor.get("alert_interval")
    P["curve"] = None
    P["curved"] = False
    P["fallback_reason"] = None
    P["lp"] = None
    P["lp_calls"] = 0
    if not cor["available"]:
        P["fallback_reason"] = cor["reason"]
    else:
        t0 = time.perf_counter()
        lp = curve_lp(np.asarray(cor["x"]), np.asarray(cor["lo"]), np.asarray(cor["hi"]), h, z, D_m=cor["D"])
        T._tick(S, "lp_s", time.perf_counter() - t0)
        P["lp_calls"] = 1
        P["lp"] = {k: lp.get(k) for k in ("feasible", "fallback_reason", "lp_status", "lp_message", "lp_nit",
                                          "objective", "max_residual", "kappa_max", "slope_max", "n_controls")}
        if not lp["feasible"]:
            P["fallback_reason"] = lp["fallback_reason"] or "lp_infeasible"
        else:
            sp = lp["spline"]
            offsets = [slots.offsets[m] for m in slots.order]
            ca = exact_curve_audit(sp, [d for _, d in offsets])
            P["curve_audit"] = ca
            P["curve"] = {"knots_m": [float(x) for x in sp.t], "controls_m": [float(c) for c in sp.c],
                          "x_range": [float(cor["x"][0]), float(cor["x"][-1])],
                          "target_m": [float(t) for t in lp["target_m"]]}
            P["curved"] = True
            if not ca["ok"]:
                return T._stage_fail("feint_shape_audit", "LP 曲线未通过精确曲率/斜率复核（不重抽）", P, key,
                                     {"curve_audit": ca, "shape_audit_failed": True,
                                      "draw": draw_summary(P, slots.realized)})
    # 初始可视图路由（集合槽位；entry_planner 把目标 warning 外扩 10 + Δ 作障碍；cg_route = feint base + 目标 warning 外 10）
    C = o + xc * u + h * n
    P["collection_xy"] = tuple(map(float, C))
    P["terminal_xy"] = tuple(map(float, rec["terminal_xy"]))
    t0 = time.perf_counter()
    starts, meta = plan_starts(S, slots, C, u, crng, route_fn=T._transit_route(task.target_id))
    T._tick(S, "route_s", time.perf_counter() - t0)
    if starts is None:
        return T._stage_fail("start_route", f"成员 {meta} 没有可用的起点路由", P, key,
                             {"route_stats": dict(S.stats), "shape_audit_failed": False,
                              "draw": draw_summary(P, slots.realized)})
    spacing = ctx.params["curve_spacing_m"]
    pre = {}
    for m in slots.order:
        try:
            xy = sample_primitives(list(starts[m]), spacing).xy
        except PathError as exc:
            return T._stage_fail("preentry_exact", f"成员 {m} 进场图元采样失败：{exc}", P, key,
                                 {"member": m, "shape_audit_failed": False, "draw": draw_summary(P, slots.realized)})
        ok = IN.preentry_clearance_ok(tgt.layers["warning"], xy, S.band)
        pre[m] = ok
        if not ok:
            from ...scene.exact import polyline_clearance
            mar = polyline_clearance(tgt.layers["warning"], xy, sense=1, minimum_m=S.band, fast_far_m=None)
            k = int(np.argmin(mar))
            return T._stage_fail("preentry_exact", f"成员 {m} 进场折线距目标 warning 不足 {S.band} m（提前入圈）", P,
                                 key, {"member": m, "margin_m": float(mar[k]), "chord_index": k,
                                       "shape_audit_failed": False, "draw": draw_summary(P, slots.realized)})
    P["start_connections"] = starts
    P["starts"] = meta
    P["preentry_ok"] = pre
    t0 = time.perf_counter()
    plan = T.build_candidate(ctx, group, task, states, key, P)
    T._tick(S, "candidate_s", time.perf_counter() - t0)
    if plan.failure is not None:
        w = dict(plan.failure.witness or {})
        w["draw"] = draw_summary(plan.proposal or P, slots.realized)
        w.setdefault("shape_audit_failed", False)
        plan = replace(plan, failure=replace(plan.failure, witness=w))
    return plan


# ---------------------------------------------------------------- 参考与成员（共享 build_candidate 的 feint 回调）

def build_reference(P, ext_m, spacing):
    """参考 = 入口（直线 + 可选 LP 曲线段，直接调用 transit._curve_samples）+ 整体掉头图元（sample_primitives）+
    出口直线。特殊站点（集合、中心线入/出圈、曲线端、A/B/D/E、终点）精确插入为顶点。返回 (Reference, 标记下标)。"""
    o = np.asarray(P["origin_xy"], float)
    u, n = np.asarray(P["u"], float), np.asarray(P["n"], float)
    h = float(P["h_m"])
    xc, xA = float(P["x_c"]), float(P["turn"]["A_m"])
    curve = P.get("curve")
    spline = None
    if curve is not None:
        from scipy.interpolate import BSpline
        spline = BSpline(np.asarray(curve["knots_m"], float), np.asarray(curve["controls_m"], float), 3,
                         extrapolate=False)
        xa, xb = float(curve["x_range"][0]), float(curve["x_range"][1])
    stations = {"lo": xc - ext_m, "collect": xc, "feint_A": xA}
    v = P.get("x_entry_ref")
    if v is not None and xc - ext_m < float(v) < xA and not (spline is not None and xa < float(v) < xb):
        stations["x_entry_ref"] = float(v)
    if spline is not None:
        stations["curve_a"], stations["curve_b"] = xa, xb
    order = sorted(stations.items(), key=lambda kv: kv[1])
    parts_xy, parts_th, parts_k = [], [], []
    idx = {}
    count = 0

    def add(xy, th, kp):
        nonlocal count
        if parts_xy:
            xy, th, kp = xy[1:], th[1:], kp[1:]
        parts_xy.append(xy), parts_th.append(th), parts_k.append(kp)
        count += len(xy)

    line_pt = lambda x: o + x * u + h * n                                       # noqa: E731
    prev_name, prev_x = order[0]
    idx[prev_name] = 0
    for name, x in order[1:]:
        if x - prev_x <= 1e-9:
            idx[name] = count - 1 if count else 0
            prev_name, prev_x = name, x
            continue
        if spline is not None and prev_name == "curve_a" and name == "curve_b":
            xy, th, kp, _ = T._curve_samples(spline, xa, xb, o, u, n, spacing)
            add(xy, th, kp)
        else:
            s = sample_primitives([("line", tuple(line_pt(prev_x)), tuple(line_pt(x)))], spacing)
            add(s.xy, s.theta, s.kappa)
        idx[name] = count - 1
        prev_name, prev_x = name, x
    if order[-1][0] != "feint_A":
        raise PathError("入口站点次序异常：A 不是入口最后一站")
    # 整体掉头（收拢、核心、展开），各图元分段采样以取得 B/D/E 下标
    prims = [tuple(p) if p[0] != "arc" else (p[0], tuple(p[1]), float(p[2]), float(p[3]), float(p[4]))
             for p in P["turn_primitives"]]
    prims = [(p[0], tuple(p[1]), tuple(p[2])) if p[0] == "line" else p for p in prims]
    L = float(P["L_m"])
    smp = sample_primitives(prims, spacing)
    iv = smp.intervals
    base = count - 1
    add(smp.xy, smp.theta, smp.kappa)
    nturn = len(prims)
    idx["feint_B"] = base + (iv[0][1] if L > 0.0 else 0)
    idx["feint_E"] = base + iv[nturn - 1][1]
    idx["feint_D"] = base + (iv[nturn - 2][1] if L > 0.0 else iv[nturn - 1][1])
    # 出口直线：E → 中心线出圈 → 终点 → 终点 + ext
    E = np.asarray(P["landmarks_xy"]["E"], float)
    h_out = float(P["exit_heading_rad"])
    u_out = np.array([math.cos(h_out), math.sin(h_out)])
    xt = float(P["terminal_x"])
    ex = {"terminal": xt, "hi": xt + ext_m}
    xo = P.get("x_exit_ref")
    if xo is not None and 0.0 < float(xo) < xt:
        ex["x_exit_ref"] = float(xo)
    prev = 0.0
    for name, x in sorted(ex.items(), key=lambda kv: kv[1]):
        if x - prev <= 1e-9:
            idx[name] = count - 1
            continue
        s = sample_primitives([("line", tuple(E + prev * u_out), tuple(E + x * u_out))], spacing)
        add(s.xy, s.theta, s.kappa)
        idx[name] = count - 1
        prev = x
    smp_all = Sampled(np.vstack(parts_xy), np.concatenate(parts_th), np.concatenate(parts_k), ())
    marks = {"collect": idx["collect"], "terminal": idx["terminal"], "feint_A": idx["feint_A"],
             "feint_B": idx["feint_B"], "feint_D": idx["feint_D"], "feint_E": idx["feint_E"]}
    if "x_entry_ref" in idx:
        marks["transit_entry"] = idx["x_entry_ref"]
    if "x_exit_ref" in idx:
        marks["transit_exit"] = idx["x_exit_ref"]
    if spline is not None:
        marks["curve_start"], marks["curve_end"] = idx["curve_a"], idx["curve_b"]
    ref = make_reference(smp_all, marks, (("feint", marks["collect"], marks["terminal"]),))
    return ref, marks


class FeintLanes(dict):
    """{成员: DeformLane}，另带实际 schedule（含 MT 返回的 l*）。MT 对额外字典字段不读取。"""
    schedule = ()


def member_lanes(ref, slots, s_c, s_t, P, spacing):
    """成员由 MT.derive_deforming_members 派生；schedule 弧长从实际完整参考的标记重算。"""
    ev = {"s_A": ref.marks["feint_A"], "s_B": ref.marks["feint_B"], "s_D": ref.marks["feint_D"],
          "s_E": ref.marks["feint_E"], "L": float(P["L_m"])}
    lanes, _scheds, l_star = MT.derive_deforming_members(ref, slots, [ev], (s_c, s_t), spacing_m=spacing)
    out = FeintLanes(lanes)
    out.schedule = [{**ev, "l_star": float(l_star)}]
    return out


def _t_to_member_s(ln, ms, t):
    return float(np.interp(t, np.arange(len(ln.xy), dtype=float), ms))


def finish_candidate(ctx, task, key, P, slots, lanes, curves, cum, coll_idx, members, nominals, wit, anchors,
                     duration, cons, ref_xy):
    """build_candidate 的 feint 分支：逐成员 feint base 精确余量、完整 crossing_analysis（目标 warning、alert 各恰
    ["in", "out"]，其他 warning 整段离带或完整深穿）、实际形变支撑与核心认证、终点全员离所有 warning ≥ 50 m；
    member_map_feint、turn_ranges、名义预筛（只记录）、见证。任一不过返回 candidate_rejected（保留原始见证）。"""
    from ...config import load_config
    from ..layer_limits import crossing_layer_keys
    from ..nominal_checks import screen_feint_member
    target = task.target_id
    tgt = ctx.facility_by_id[target]
    band, align = ctx.params["pre_entry_warning_clearance_m"], ctx.params["alignment_length_m"]
    retreat = float(load_config("monitoring").values["retreat_clearance_m"])
    lk = crossing_layer_keys(cons)
    layer_key = {"warning": target, **{layer: k for k, layer in lk.items()}}
    wit["crossing_layer_keys"] = dict(layer_key)
    sched = [dict(ev) for ev in lanes.schedule]
    wit["schedule_feint"] = sched
    order = list(slots.order)
    layer_s = {}
    for m in order:
        xy = curves[m]
        mar = T._min_margins(xy, cons["base"])
        wit["constraints"][m] = dict(mar)
        bad = {k: val for k, val in mar.items() if val[0] < 0.0}
        if bad:
            name, (val, idx) = min(bad.items(), key=lambda kv: kv[1][0])
            return T._fail_with(P, key, f"成员 {m} 违反约束 {name}（余量 {val:.3f} m，弦 {idx}）", name,
                                {"member": m, "constraint": name, "margin_m": val, "chord_index": idx,
                                 "point": tuple(map(float, xy[idx])), "all_violations": {k: v[0] for k, v in bad.items()}},
                                wit)
        viol, cross = crossing_analysis(xy, cons["crossing_boundaries"], target, band_m=band, align_m=align)
        wit["crossings"][m] = [(c.facility_id, c.direction, round(c.s_m, 3)) for c in cross]
        if viol:
            v = viol[0]
            return T._fail_with(P, key, f"成员 {m} 边界穿越不合规：{v['kind']}（边界 {v['facility']}）",
                                "boundary_crossing", {"member": m, **v, "n_violations": len(viol)}, wit)
        layer_s[m] = {}
        for layer, k in layer_key.items():
            dirs = [c.direction for c in cross if c.facility_id == k]
            if dirs != ["in", "out"]:
                return T._fail_with(P, key, f"成员 {m} 目标 {layer} 穿越次序 {dirs}（应恰为一入一出）",
                                    "target_layer_crossing", {"member": m, "layer": layer, "boundary_key": k,
                                                              "directions": dirs}, wit)
            ss = [float(c.s_m) for c in cross if c.facility_id == k]
            layer_s[m][layer] = (ss[0], ss[1])
        for fid, geom in cons["warnings"].items():
            sd = float(signed_distance(geom, xy[-1]))
            if sd < retreat:
                return T._fail_with(P, key, f"成员 {m} 终点离设施 {fid} 的预警圈只有 {sd:.3f} m（< {retreat} m）",
                                    "terminal_clearance", {"member": m, "facility": fid, "signed_m": sd,
                                                           "required_m": retreat}, wit)
    ok, first = FT.deformation_passes(dict(lanes), sched, tgt.layers["alert"], tgt.layers["protected"],
                                      cons["crossing_boundaries"], band_m=FT.BAND_M, mode="exact", detail=True)
    if not ok:
        return T._fail_with(P, key, f"成员 {first['member']} 的实际形变支撑/核心 {first['piece']} 未在 alert 内 10 m、"
                                    f"protected 外 10 m 或贴近边界带", "deformation_support", dict(first), wit)
    kind = P["turn"]["kind"]
    mm, turn_ranges = {}, {}
    for m in order:
        ln = lanes[m]
        ms = np.asarray(cum[m][coll_idx[m]:coll_idx[m] + len(ln.xy)], float)
        sup = {}
        for k, ev in enumerate(sched):
            ls = float(ev["l_star"])
            for name, ref_iv, grp_iv in (("collapse", (ev["s_A"], ev["s_B"]), (ev["s_A"] - ls, ev["s_B"] - ls)),
                                         ("expand", (ev["s_D"], ev["s_E"]), (ev["s_D"] + ls, ev["s_E"] + ls))):
                ivs = FT._union([FT._t_interval(ln.s_ref, *ref_iv), FT._t_interval(ln.s_group, *grp_iv)])
                if ivs:
                    sup[name] = [_t_to_member_s(ln, ms, ivs[0][0]), _t_to_member_s(ln, ms, ivs[-1][1])]
                ref_part = FT._t_interval(ln.s_ref, *ref_iv)
                grp_part = FT._t_interval(ln.s_group, *grp_iv)
                sup[name + "_lateral"] = None if ref_part is None else [_t_to_member_s(ln, ms, t) for t in ref_part]
                sup[name + "_longitudinal"] = None if grp_part is None else [_t_to_member_s(ln, ms, t) for t in grp_part]
        idx = np.flatnonzero(ln.turn_mask)
        turn_ranges[m] = ([(kind, float(cum[m][coll_idx[m] + idx[0]]), float(cum[m][coll_idx[m] + idx[-1]]),
                            TURN_MIN_KEYS.get(kind))] if len(idx) else [])
        mm[m] = {"reference_s": ln.s_group.tolist(), "shifted_reference_s": ln.s_ref.tolist(), "member_s": ms.tolist(),
                 "lateral_m": ln.lateral_m.tolist(), "turn_mask": [bool(x) for x in ln.turn_mask],
                 "slot_lateral_m": float(ln.d_m), "slot_longitudinal_m": float(ln.l_m),
                 "collect_member_s": float(cum[m][coll_idx[m]]), "terminal_member_s": float(cum[m][-1]),
                 "layer_member_s": {k: list(v) for k, v in layer_s[m].items()}, "support_member_s": sup}
    wit["turn_ranges"] = turn_ranges
    wit["member_map_feint"] = {"schema": "member-map-feint-v18", "members": mm}
    for m in order:
        smp = sample_nominal(members[m], include_prerelease=False, nominal=nominals[m])
        scr = screen_feint_member(ctx.facilities, target, smp.time_us, smp.p, smp.v)
        wit["screen"][m] = {"passed": scr["passed"], "conditions": scr["conditions"],
                            "entries": scr["counts"]["entries"], "min_protected_sdf_m": scr["min_protected_sdf_m"]}
    formation = {"prior": slots.prior, "start": slots.start, "realized": slots.realized,
                 "mapped_from_loose": slots.mapped_from_loose, "retreat_chain": list(retreat_chain(slots.start)),
                 "order": list(slots.order), "offsets": {m: list(v) for m, v in slots.offsets.items()},
                 "lateral_step_m": slots.lateral_step_m}
    topology = {"final": "feint", "curved": bool(P.get("curved")), "fallback_reason": P.get("fallback_reason"),
                "turn_kind": kind, "turn_side": int(P["turn"]["side"]), "radius_m": float(P["turn"]["radius_m"])}
    return SegmentPlan(members=members, reference_xy=ref_xy, nominal_duration_s=duration, anchors=anchors,
                       repairs=tuple(P.get("repairs", ())), failure=None, proposal=P, formation=formation,
                       topology=topology, business_key=_key_dict(key),
                       member_nominal_s={m: float(nominals[m].travel_s) for m in order}, witnesses=wit)
