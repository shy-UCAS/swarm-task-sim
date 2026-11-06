"""突入单段：一次提案、共享曲线/路由/候选构造、失败分类与遥测（V8-17 指令 3.4–3.7；本项新增）。

一个 attempt 的随机来源（全部用现有键）：formation → 槽位排列；shape → 可行格、σ、终点（按长度均匀）、相容 D_c，
之后才按既有顺序抽 K 与 logistic 分位数；connect → 初始可视图路由（沿用 4 类 Δ、每类 ≤ 6 个有限候选）；speed →
原 Poisson 事件。一次 attempt 只有一次格/σ/终点抽取和至多一次 LP；精确弦、曲线复核、进场精确检查或任何下游
检查失败都原样返回 candidate_rejected，不换格、不重抽、不退队形；唯一 20 次预算由现有 run_attempts 管理。

队形：retreat_chain(mapped_start(prior))，梯形沿用 transit._echelon_payload 二分；probe 的"可行"= 该队形全部真实
车道存在一个 (格, σ, x_e)。共享步骤直接调用：TransitSetup（按 task.intent 选 base 与 cg_route）、corridor_rows
（intrusion 上界）、curve_lp / exact_curve_audit、plan_starts + transit._transit_route（entry_planner 绕开目标 warning
外 10 + Δ）、transit.build_candidate（终点、成员域、语义与见证按 intent 分支，见 finish_candidate）。
"""
import math
import time
from dataclasses import replace

import numpy as np

from ...contract.monitoring import Failure, SegmentPlan
from ...sampler.keys import RngKey
from ...scene.exact import signed_distance
from .. import intrusion_chords as IC
from .. import intrusion_numeric as IN
from .. import transit_chords as TC
from ..connect import crossing_analysis
from ..formation import formation_slots, mapped_start, retreat_chain
from ..nominal import sample_nominal
from ..path import PathError, sample_primitives
from ..shared_routes import plan_starts
from ..skeleton import width_then_build
from ..transit_numeric import curve_lp, exact_curve_audit
from . import transit as T
from .monitoring import _key_dict

LAYERS = ("warning", "alert", "protected")
_LAST_TIMING = {}


def last_attempt_timing():
    """本进程最近一次突入 propose_and_build 的分阶段墙钟（遥测，不进入确定性载荷）。"""
    return dict(_LAST_TIMING)


# ---------------------------------------------------------------- 失败、证书、摘要

def final_failure(ctx, group, task, attempt_records):
    """r4 13.4 口径：全部 attempt 都是突入有限集合为空 → approx_empty（有限网格为空不证明连续可行域为空）；
    其余用完预算为 budget_exhausted。确定性证书（proven_infeasible）在运行前由 infeasibility_certificate 给出。"""
    stages = {r["stage"] for r in attempt_records}
    n = len(attempt_records)
    if n and stages == {"intrusion_chord_set"}:
        return Failure("approx_empty", "全部 attempt 在所有队形下突入离散终点集合均为空（有限航向×偏移×σ 网格）；"
                                       "不证明连续可行域为空", "intrusion_chord_set", {"attempts": n}, None)
    return Failure("budget_exhausted", f"{n} 次随机构造用完预算", "random_construction",
                   {"attempts": n, "stages": sorted(str(s) for s in stages)}, None)


def infeasibility_certificate(ctx, group, task):
    """指令 3.7：运行前的确定性检查。只在目标 contour/protected 为同心圆时可能成立；成立返回 Failure
    （proven_infeasible，attempts=0），否则 None。不按合同 ID 判断。"""
    tgt = ctx.facility_by_id[task.target_id]
    cert = IN.circle_infeasibility_certificate(tgt.geometry, tgt.layers["protected"], len(group.member_ids),
                                               float(ctx.family.lateral_spacing_m))
    if cert is None:
        return None
    cert = {**cert, "target_id": task.target_id, "group_size": len(group.member_ids),
            "formation_prior": group.formation_prior,
            "retreat_chain": list(retreat_chain(mapped_start(group.formation_prior)))}
    return Failure("proven_infeasible", "同心圆终点必要条件证书：规定 σ 网格下横排、纵列、梯形三种队形的终点跨度均超过"
                                        "可用范围", "intrusion_endpoint_certificate", cert, False)


def draw_summary(P, formation):
    P = P or {}
    return {"intent": "intrusion", "formation": formation, "theta_deg": P.get("theta_deg"), "h_m": P.get("h_m"),
            "cell_index": P.get("cell_index"), "cells_feasible": P.get("cells_feasible"),
            "sigma": P.get("sigma"), "sigmas_feasible": P.get("sigmas_feasible"), "x_e": P.get("x_e"),
            "endpoint_quantile": P.get("endpoint_quantile"), "collect_D_m": P.get("collect_D_m"),
            "collect_candidates": P.get("collect_candidates"), "K": P.get("K"),
            "logit_quantiles": P.get("logit_quantiles"), "curved": P.get("curved"),
            "fallback_reason": P.get("fallback_reason")}


# ---------------------------------------------------------------- 队形 probe

def formation_probe_sequence(ctx, group, task, key):
    """确定性的选队形 probe 序列（主进程预建与 worker 共用）：[(formation, lateral_step, offsets, sigmas)]，
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
        offs, sig = IC.request_for(slots)
        seq.append((name, step, offs, sig))
        doc = IC.load_chord_set(ctx, task.target_id, slots, ctx.cache_dir)
        return {"slots": slots, "doc": doc} if doc["cells"] else None

    def width_probe(name):
        if name == "echelon":
            return T._echelon_payload(probe, group, b, [])
        return probe(name, None)

    width_then_build(chain, width_probe, lambda name, payload: payload)
    return seq


# ---------------------------------------------------------------- 一次 attempt

def propose_and_build(ctx, group, task, states, key):
    """一次随机构造（一个 attempt）：宽度先定队形 → 可行格/σ/终点/D_c 各抽一次 → 精确弦检查 → 走廊与一次 LP（不可用
    即同格直线）→ 曲线精确复核 → 初始可视图路由 → 进场精确检查 → 共享候选构造。下游失败原样返回。"""
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
            doc = IC.load_chord_set(ctx, task.target_id, slots, ctx.cache_dir)
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
        return T._stage_fail("intrusion_chord_set", "所有队形下突入离散终点集合为空（approx_empty 查询）", None, key,
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
    dr = IN.draw_feasible(cells, rng)                          # 格 → σ → 终点（长度均匀）→ 相容 D_c，各一次
    kmin, kmax = int(S.M["spline_basis_min"]), int(S.M["spline_basis_max"])
    K = int(rng.integers(kmin, kmax + 1))
    v = rng.random(K)
    z = T._logit(v)
    ti, h, x_in = int(dr["theta_idx"]), float(dr["h_m"]), float(dr["x_in"])
    sigma, x_e, D_c = float(dr["sigma"]), float(dr["x_e"]), float(dr["collect_D_m"])
    xc = x_in - D_c
    th = TC.thetas()[ti]
    u, n = TC.frame(th)
    o = np.asarray(tgt.center, float)
    offsets = [slots.offsets[m] for m in slots.order]
    P = {"intent": "intrusion", "theta_idx": ti, "theta_deg": float(TC.THETA_STEP_DEG * ti), "h_m": h,
         "origin_xy": tuple(map(float, o)), "u": tuple(map(float, u)), "n": tuple(map(float, n)),
         "cell_index": int(dr["cell_index"]), "cells_feasible": len(cells), "chord_query_id": doc.get("query_id"),
         "sigma": sigma, "sigma_index": int(dr["sigma_index"]), "sigmas_feasible": int(dr["sigmas_feasible"]),
         "x_e": x_e, "endpoint_quantile": float(dr["endpoint_quantile"]),
         "endpoint_total_length_m": float(dr["endpoint_total_length_m"]),
         "x_c": xc, "x_t": x_e, "x_in": x_in, "collect_D_m": D_c, "collect_candidates": int(dr["collect_candidates"]),
         "K": K, "logit_quantiles": tuple(map(float, v)), "logit_coefficients": tuple(map(float, z)),
         "member_slot_order": slots.order, "formation": slots.realized,
         "lateral_step_m": slots.lateral_step_m if slots.realized == "echelon" else None,
         "repairs": tuple(repairs), "formation_steps": steps_log}
    # 精确弦检查（抽中的唯一格，一次）
    t0 = time.perf_counter()
    audit = IC.assess_intrusion_bundle(ctx, S.base, task.target_id, o + h * n, u, offsets, xc, x_e, sigma,
                                       band_m=S.band, align_m=S.align)
    T._tick(S, "chord_exact_s", time.perf_counter() - t0)
    P["chord_audit"] = {"feasible": audit["feasible"], "first_error": audit["first_error"],
                        "margins": {k: float(val) for k, val in audit["margins"].items()},
                        "terminal": audit["terminal"]}
    if not audit["feasible"]:
        return T._stage_fail("chord_exact_audit", "抽中的离散弦未通过精确弦检查（不换格）", P, key,
                             {"audit": P["chord_audit"], "shape_audit_failed": True,
                              "draw": draw_summary(P, slots.realized)})
    ent = TC.line_sublevel(tgt.layers["warning"], o + h * n, u, 0.0)
    P["x_entry_ref"] = float(ent[0]) if ent is not None else None
    P["x_exit_ref"] = None                                        # 突入没有出圈锚点
    # 走廊与一次 LP（corridor_rows 在 task.intent == "intrusion" 时用 alert 正次水平集作上界）
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
        # LP 墙钟（lp["seconds"]）只进遥测 S.timing["lp_s"]（合同目录外），不写入提案/见证
        if not lp["feasible"]:
            P["fallback_reason"] = lp["fallback_reason"] or "lp_infeasible"
        else:
            sp = lp["spline"]
            ca = exact_curve_audit(sp, [d for _, d in offsets])
            P["curve_audit"] = ca
            P["curve"] = {"knots_m": [float(x) for x in sp.t], "controls_m": [float(c) for c in sp.c],
                          "x_range": [float(cor["x"][0]), float(cor["x"][-1])],
                          "target_m": [float(t) for t in lp["target_m"]]}
            P["curved"] = True
            if not ca["ok"]:
                return T._stage_fail("intrusion_shape_audit", "LP 曲线未通过精确曲率/斜率复核（不重抽）", P, key,
                                     {"curve_audit": ca, "shape_audit_failed": True,
                                      "draw": draw_summary(P, slots.realized)})
    # 初始可视图路由（集合槽位；entry_planner 把目标 warning 外扩 10 + Δ 作障碍；cg_route = intrusion base + 目标
    # warning 外 10 m，direct 路由同样过 cg_route）
    C = o + xc * u + h * n
    P["collection_xy"] = tuple(map(float, C))
    P["terminal_xy"] = tuple(map(float, o + x_e * u + h * n))
    t0 = time.perf_counter()
    starts, meta = plan_starts(S, slots, C, u, crng, route_fn=T._transit_route(task.target_id))
    T._tick(S, "route_s", time.perf_counter() - t0)
    if starts is None:
        return T._stage_fail("start_route", f"成员 {meta} 没有可用的起点路由", P, key,
                             {"route_stats": dict(S.stats), "shape_audit_failed": False,
                              "draw": draw_summary(P, slots.realized)})
    # 进场精确检查：初始点至集合槽位（含圆角采样弦）逐弦在目标 warning 外 ≥ 10 m
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


# ---------------------------------------------------------------- 共享 build_candidate 的突入分支

def member_lanes(ref, slots, s_c, s_t, P, spacing):
    """3.6 第 2 步：按成员给不同终止站点，成员域 [s_c + l_i, s_e + σ l_i]（intrusion_numeric.clip_lanes）。"""
    return IN.clip_lanes(ref, slots, s_c, s_t, float(P["sigma"]), spacing_m=spacing)


def finish_candidate(ctx, task, key, P, slots, lanes, curves, cum, coll_idx, members, nominals, wit, anchors,
                     duration, cons, ref_xy):
    """build_candidate 的 intrusion 分支（逐成员检查、成员映射、名义预筛、见证）。只读取目标 ["in"] 与终点；
    没有出圈、撤离与 retreat 条件，不生成假出圈事件。任一检查不过返回 candidate_rejected（保留原始见证）。"""
    from ..layer_limits import crossing_layer_keys
    from ..nominal_checks import screen_intrusion_member
    target = task.target_id
    tgt = ctx.facility_by_id[target]
    band, align = ctx.params["pre_entry_warning_clearance_m"], ctx.params["alignment_length_m"]
    lk = crossing_layer_keys(cons)
    layer_key = {"warning": target, **{layer: k for k, layer in lk.items()}}
    wit["crossing_layer_keys"] = dict(layer_key)
    wit["sigma"], wit["x_e"] = float(P["sigma"]), float(P["x_e"])
    wit["terminal"] = {}
    o = np.asarray(P["origin_xy"], float)
    u, n = np.asarray(P["u"], float), np.asarray(P["n"], float)
    h = float(P["h_m"])
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
            if dirs != ["in"]:
                return T._fail_with(P, key, f"成员 {m} 目标 {layer} 穿越次序 {dirs}（应恰为一次进入）",
                                    "target_layer_crossing", {"member": m, "layer": layer, "boundary_key": k,
                                                              "directions": dirs}, wit)
            layer_s[m][layer] = float(next(c.s_m for c in cross if c.facility_id == k))
        l_m, d_m = slots.offsets[m]
        end = xy[-1]
        sd_p = float(signed_distance(tgt.layers["protected"], end))
        sd_c = float(signed_distance(tgt.geometry, end))
        p0 = o + (h + float(d_m)) * n
        xs = IN.deepest_station(tgt.geometry, p0, u)
        x_design = float(P["x_e"]) + float(P["sigma"]) * float(l_m)
        x_actual = float(u @ (end - p0))
        wit["terminal"][m] = {"protected_sdf_m": sd_p, "contour_sdf_m": sd_c, "deepest_x": xs,
                              "terminal_x": x_design, "terminal_x_actual": x_actual}
        if not sd_p <= -IN.PROTECTED_DEPTH_M:
            return T._fail_with(P, key, f"成员 {m} 终点 protected SDF {sd_p:.3f} m（> −10）", "terminal_protected",
                                {"member": m, "signed_m": sd_p}, wit)
        if not sd_c <= IN.CONTOUR_SKELETON_M:
            return T._fail_with(P, key, f"成员 {m} 终点 contour SDF {sd_c:.3f} m（> 45）", "terminal_contour",
                                {"member": m, "signed_m": sd_c}, wit)
        if not x_design <= xs:
            return T._fail_with(P, key, f"成员 {m} 终点越过车道最深点", "terminal_beyond_deepest",
                                {"member": m, "terminal_x": x_design, "deepest_x": xs}, wit)
    mm = {}
    for m in order:
        ln = lanes[m]
        l_m = slots.offsets[m][0]
        ms = np.asarray(cum[m][coll_idx[m]:coll_idx[m] + len(ln.xy)], float)
        mm[m] = {"reference_s": (ln.s_ref - l_m).tolist(), "shifted_reference_s": ln.s_ref.tolist(),
                 "member_s": ms.tolist(), "lateral_m": float(ln.d_m), "longitudinal_m": float(l_m),
                 "entry_member_s": layer_s[m]["warning"],
                 "layer_entry_member_s": {k: layer_s[m][k] for k in LAYERS},
                 "terminal_member_s": float(cum[m][-1]), "terminal_x": wit["terminal"][m]["terminal_x"],
                 "collect_member_s": float(cum[m][coll_idx[m]])}
    wit["member_map_intrusion"] = {"schema": "member-map-intrusion-v17", "members": mm}
    wit["endpoint_distances_m"] = IN.endpoint_distances(slots, float(P["sigma"]))
    for m in order:
        smp = sample_nominal(members[m], include_prerelease=False, nominal=nominals[m])
        scr = screen_intrusion_member(ctx.facilities, target, smp.time_us, smp.p, smp.v)
        wit["screen"][m] = {"passed": scr["passed"], "conditions": scr["conditions"],
                            "entries": scr["counts"]["entries"]}
    formation = {"prior": slots.prior, "start": slots.start, "realized": slots.realized,
                 "mapped_from_loose": slots.mapped_from_loose, "retreat_chain": list(retreat_chain(slots.start)),
                 "order": list(slots.order), "offsets": {m: list(v) for m, v in slots.offsets.items()},
                 "lateral_step_m": slots.lateral_step_m}
    topology = {"final": "intrusion", "curved": bool(P.get("curved")), "fallback_reason": P.get("fallback_reason"),
                "sigma": float(P["sigma"]), "x_e": float(P["x_e"])}
    return SegmentPlan(members=members, reference_xy=ref_xy, nominal_duration_s=duration, anchors=anchors,
                       repairs=tuple(P.get("repairs", ())), failure=None, proposal=P, formation=formation,
                       topology=topology, business_key=_key_dict(key),
                       member_nominal_s={m: float(nominals[m].travel_s) for m in order}, witnesses=wit)
