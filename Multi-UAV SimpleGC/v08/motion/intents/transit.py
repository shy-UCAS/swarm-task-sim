"""过境单段：一次骨架构造、转接、成员映射、失败见证（V8-16 指令 3.1–3.5、附录裁定 1；本项新增）。

一个 attempt 的随机来源（全部用现有键）：formation → 槽位排列；shape → 可行格索引、集合站点候选、K、logistic 分位数；
connect → 初始可视图路由（沿用监视 _route 的有限候选：4 类 Δ、每类 ≤ 6 个）；speed → 原 Poisson 事件。
一次 attempt 中形状只有一次格点抽取和一次目标 LP；精确弦检查、曲线复核或任何下游检查失败都原样结束本 attempt，
不换格、不重抽 logits、不换队形；下一次 attempt 由运行器统一增加键（唯一 20 次预算，r5 6.5）。

队形：retreat_chain(mapped_start(prior))（loose → abreast），梯形照旧二分协议；选定后只构造一次（width_then_build）。
曲线：弯曲范围 = 中心线目标 warning 内缩 (10 + D) 区间内"已认证行"组成的最长连续段（附录裁定 1），夹持三次样条
LP 一次；LP 无解、走廊不可用或段长 < 80 m 时本 attempt 用原格直线 δ = h，记录原因（不重抽）。
"""
import math
import time
from dataclasses import replace

import numpy as np

from ...config import load_config
from ...contract.monitoring import Failure, MemberPlan, SegmentPlan
from ...sampler.keys import RngKey, rng_for
from ...scene.exact import polyline_clearance, signed_distance
from ...sim.guidance import make_curve, nominal_time, speed_profile
from ...sim.kernel import member_config
from ...sim.types import SimContractError
from .. import transit_chords as TC
from ..connect import crossing_analysis
from ..formation import MIN_LATERAL_STEP_M, derive_members, formation_slots, make_reference, mapped_start, \
    retreat_chain
from ..nominal import release_us, sample_nominal
from ..path import PathError, Sampled, sample_primitives
from ..shared_routes import plan_starts, route_to_slot
from ..skeleton import reference_guidance, width_then_build
from ..speed import draw_speed_events, map_speed_events
from ..transit_numeric import curve_lp, exact_curve_audit
from .monitoring import _key_dict, _release_delays_ref

NODE_TOL_M = 1e-6
FAR_M = 5.0
CURVE_SPACING_FINE_M = 0.05


def _logit(v):
    from ..monitoring_band import logit_from_quantiles
    return logit_from_quantiles(v)


# ---------------------------------------------------------------- 设置

class TransitSetup:
    """路由复用所需的最小对象（指令 3.1）：ctx、states、G、v_cap、cg_route（base + 首次入圈前目标 warning 外 10 m）、
    warn（全部 warning）、band、stats；不调用会建立巡逻带的监视 _Setup。"""

    def __init__(self, ctx, group, task, states, key):
        from ...scene.field import Clearance
        from ..layer_limits import constraints_identity
        self.ctx, self.group, self.task, self.states, self.key = ctx, group, task, states, key
        self.target = task.target_id
        self.tgt = ctx.facility_by_id[self.target]
        cons = TC.transit_base(ctx, self.target)
        self.base, self.warn = list(cons["base"]), dict(cons["warnings"])
        P = ctx.params
        self.M = load_config("monitoring").values
        self.G = load_config("guidance").values
        self.v_cap = self.M["speed_max_m_s"]
        self.band = P["pre_entry_warning_clearance_m"]
        self.align = P["alignment_length_m"]
        pre = Clearance("preentry_warning:" + self.target, self.tgt.layers["warning"], 1,
                        P["pre_entry_warning_clearance_m"])
        route = self.base + [pre]
        self.cg_route = ctx.combined(("route", "transit_preentry", constraints_identity(route)), route)
        self.stats = {}
        self.timing = {}

    def rng(self, purpose):
        k = self.key
        return rng_for(RngKey(k.family_id, k.draw, purpose, mission=k.mission, branch=k.branch, group=k.group,
                              segment=k.segment, attempt=k.attempt))


def _tick(S, name, seconds):
    S.timing[name] = S.timing.get(name, 0.0) + float(seconds)


_LAST_TIMING = {}


def last_attempt_timing():
    """本进程最近一次过境 propose_and_build 的分阶段墙钟（遥测，不进入确定性载荷）。"""
    return dict(_LAST_TIMING)


def _transit_route(target_id):
    def planner_factory(ctx, delta):
        return TC.entry_planner(ctx, target_id, delta)

    def route_fn(S, p0, slot, u, rng):
        return route_to_slot(S, p0, slot, u, rng, planner_factory=planner_factory)
    return route_fn


# ---------------------------------------------------------------- 失败

def _reject(reason, feasible_set, witness):
    return Failure("candidate_rejected", reason, feasible_set, witness, None)


def _plan(failure, **kw):
    return SegmentPlan(members={}, reference_xy=(), nominal_duration_s=math.nan, anchors={}, repairs=(),
                       failure=failure, **kw)


def _stage_fail(stage, reason, P=None, key=None, extra=None):
    return _plan(_reject(reason, stage, {"stage": stage, **(extra or {})}), proposal=P,
                 business_key=None if key is None else _key_dict(key))


def final_failure(ctx, group, task, attempt_records):
    """r4 13.4 口径：全部 attempt 都是可行弦集合为空（且无精确不可能证书）→ approx_empty；有完整精确几何必要条件
    证书才 proven_infeasible（本项没有该证书，不报）；其余 budget_exhausted。有限网格为空不证明连续可行域为空。"""
    stages = {r["stage"] for r in attempt_records}
    n = len(attempt_records)
    if stages == {"transit_chord_set"}:
        return Failure("approx_empty", "全部 attempt 在所有队形下离散弦集合均为空（有限航向×偏移网格与保守证书）；"
                                       "不证明连续可行域为空", "transit_chord_set", {"attempts": n}, None)
    return Failure("budget_exhausted", f"{n} 次随机构造用完预算", "random_construction",
                   {"attempts": n, "stages": sorted(str(s) for s in stages)}, None)


def draw_summary(P, formation):
    P = P or {}
    return {"intent": "transit", "formation": formation, "theta_deg": P.get("theta_deg"), "h_m": P.get("h_m"),
            "cell_index": P.get("cell_index"), "cells_feasible": P.get("cells_feasible"),
            "collect_D_m": P.get("collect_D_m"), "K": P.get("K"), "logit_quantiles": P.get("logit_quantiles"),
            "curved": P.get("curved"), "fallback_reason": P.get("fallback_reason")}


# ---------------------------------------------------------------- 参考曲线

def _curve_samples(spline, xa, xb, o, u, n, spacing):
    """样条 δ(x) 在 [xa, xb] 上按弧长 ≤ spacing 采样（保留端点与节点），返回 (xy, theta, kappa, x)。"""
    xf = np.linspace(xa, xb, max(64, int(math.ceil((xb - xa) / CURVE_SPACING_FINE_M)) + 1))
    d1 = spline(xf, 1)
    seg = np.sqrt(1.0 + 0.25 * (d1[1:] + d1[:-1]) ** 2) * np.diff(xf)
    cum = np.r_[0.0, np.cumsum(seg)]
    L = float(cum[-1])
    k = max(1, int(math.ceil(L / spacing - 1e-9)))
    xs = np.interp(np.linspace(0.0, L, k + 1), cum, xf)
    knots = np.asarray(spline.t, float)
    inner = knots[(knots > xa) & (knots < xb)]
    xs = np.unique(np.r_[xa, xs, inner, xb])
    xs = xs[(xs >= xa) & (xs <= xb)]
    dl, dd1, dd2 = spline(xs), spline(xs, 1), spline(xs, 2)
    xy = o[None] + xs[:, None] * u[None] + dl[:, None] * n[None]
    tang = u[None] + dd1[:, None] * n[None]
    th = np.arctan2(tang[:, 1], tang[:, 0])
    kap = dd2 / np.power(1.0 + dd1 * dd1, 1.5)
    return xy, th, kap, xs


def build_reference(P, ext_m, spacing):
    """参考 = 直线（含首尾 ext）+ 可选曲线段。特殊站点（集合、中心线入/出圈、曲线端、终点）精确插入为顶点。
    返回 (Reference, 标记下标 dict)。"""
    o = np.asarray(P["origin_xy"], float)
    u, n = np.asarray(P["u"], float), np.asarray(P["n"], float)
    h = float(P["h_m"])
    xc, xt = float(P["x_c"]), float(P["x_t"])
    x_lo, x_hi = xc - ext_m, xt + ext_m
    curve = P.get("curve")
    spline = None
    if curve is not None:
        from scipy.interpolate import BSpline
        spline = BSpline(np.asarray(curve["knots_m"], float), np.asarray(curve["controls_m"], float), 3,
                         extrapolate=False)
        xa, xb = float(curve["x_range"][0]), float(curve["x_range"][1])
    stations = {"lo": x_lo, "collect": xc, "terminal": xt, "hi": x_hi}
    for k in ("x_entry_ref", "x_exit_ref"):
        v = P.get(k)
        if v is not None and x_lo < float(v) < x_hi and not (spline is not None and xa < float(v) < xb):
            stations[k] = float(v)
    if spline is not None:
        stations["curve_a"], stations["curve_b"] = xa, xb
    order = sorted(stations.items(), key=lambda kv: kv[1])
    xs_parts, th_parts, k_parts = [], [], []
    idx = {}
    count = 0

    def add(xy, th, kp):
        nonlocal count
        if xs_parts:
            xy, th, kp = xy[1:], th[1:], kp[1:]
        xs_parts.append(xy), th_parts.append(th), k_parts.append(kp)
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
            xy, th, kp, _ = _curve_samples(spline, xa, xb, o, u, n, spacing)
            add(xy, th, kp)
        else:
            s = sample_primitives([("line", tuple(line_pt(prev_x)), tuple(line_pt(x)))], spacing)
            add(s.xy, s.theta, s.kappa)
        idx[name] = count - 1
        prev_name, prev_x = name, x
    if not xs_parts:
        raise PathError("参考为空")
    smp = Sampled(np.vstack(xs_parts), np.concatenate(th_parts), np.concatenate(k_parts), ())
    marks = {"collect": idx["collect"], "terminal": idx["terminal"]}
    if "x_entry_ref" in idx:
        marks["transit_entry"] = idx["x_entry_ref"]
    if "x_exit_ref" in idx:
        marks["transit_exit"] = idx["x_exit_ref"]
    if spline is not None:
        marks["curve_start"], marks["curve_end"] = idx["curve_a"], idx["curve_b"]
    ref = make_reference(smp, marks, (("transit", marks["collect"], marks["terminal"]),))
    return ref, marks


# ---------------------------------------------------------------- 候选构造（确定性）

def _min_margins(xy, cons):
    out = {}
    for c in cons:
        if len(xy) < 2:
            continue
        m = polyline_clearance(c.geometry, xy, sense=c.sense, minimum_m=c.minimum_m, fast_far_m=FAR_M)
        k = int(np.argmin(m))
        out[c.name] = (float(m[k]), k)
    return out


def _fail_with(P, key, reason, feasible_set, witness, wit, shape_audit=False):
    w = dict(witness)
    w["shape_audit_failed"] = bool(shape_audit)
    return _plan(_reject(reason, feasible_set, w), proposal=P, business_key=_key_dict(key), witnesses=wit)


def build_candidate(ctx, group, task, states, key, proposal):
    """给定完整提案确定性地构造骨架：参考 → 槽位/成员车道 → 起点连接 → 速度事件 → 释放延迟 → 逐成员精确几何、
    边界穿越（目标恰一次入、一次出）与终点撤离。任一检查不过返回 candidate_rejected（保留原始见证）。"""
    from ..nominal_checks import screen_transit_member
    P = proposal
    cfg_m = load_config("monitoring").values
    G = load_config("guidance").values
    G_ref_cfg = reference_guidance()
    G_ref = G_ref_cfg.values
    spacing = ctx.params["curve_spacing_m"]
    target = task.target_id
    cons = TC.transit_base(ctx, target)
    base_fail = dict(proposal=P, business_key=_key_dict(key))
    try:
        slots = formation_slots(group, ctx.family, key, formation=P.get("formation"),
                                lateral_step_m=P.get("lateral_step_m"), order=P.get("member_slot_order"))
        ext = slots.max_longitudinal_m
        ref, mark_idx = build_reference(P, 0.0 if ext == 0.0 else ext + 1.0, spacing)
        s_c, s_t = ref.marks["collect"], ref.marks["terminal"]
        lanes = derive_members(ref, slots, (s_c, s_t), spacing_m=spacing)
    except (PathError, ValueError) as exc:
        return _plan(_reject(f"构造失败：{exc}", "reference/lanes", {"error": str(exc), "shape_audit_failed": False}),
                     **base_fail)
    curves, coll_idx = {}, {}
    for m in slots.order:
        prims = P["start_connections"][m]
        p_init = np.asarray(states[m].p[:2], float)
        try:
            sb = sample_primitives(list(prims), spacing)
        except PathError as exc:
            return _plan(_reject(f"成员 {m} 起点连接图元非法：{exc}", f"start:{m}",
                                 {"member": m, "error": str(exc), "shape_audit_failed": False}), **base_fail)
        if float(np.hypot(*(sb.xy[0] - p_init))) > NODE_TOL_M:
            return _plan(_reject("起点连接的第一个点不是成员初始位置", f"start:{m}",
                                 {"member": m, "start": tuple(sb.xy[0]), "initial": tuple(p_init),
                                  "shape_audit_failed": False}), **base_fail)
        lane = lanes[m]
        if float(np.hypot(*(sb.xy[-1] - lane.xy[0]))) > NODE_TOL_M:
            return _plan(_reject("起点连接末端与槽位不符", f"slot:{m}",
                                 {"member": m, "route_end": tuple(sb.xy[-1]), "slot": tuple(lane.xy[0]),
                                  "shape_audit_failed": False}), **base_fail)
        curves[m] = np.vstack([sb.xy, lane.xy[1:]])
        coll_idx[m] = len(sb.xy) - 1
    cum = {m: np.r_[0.0, np.cumsum(np.hypot(*np.diff(curves[m], axis=0).T))] for m in curves}

    # 速度：与监视 build_candidate 同一算法（collect → terminal 参考线、恒定 4 m/s、起终速度 0 的名义用时上界只作事件时域）
    v0 = float(group.speed_profile.initial_speed_m_s)
    try:
        ref_curve = make_curve(ref.xy[mark_idx["collect"]:mark_idx["terminal"] + 1],
                               max_chord_m=G["max_chord_m"], max_turn_rad=G["max_turn_per_chord_rad"])
    except SimContractError as exc:
        return _plan(_reject(f"参考曲线不满足引导接口：{exc}", "reference/speed",
                             {"error": str(exc), "shape_audit_failed": False}), **base_fail)
    ev = P.get("speed_events")
    t_upper = None
    if ev is None:
        v_slow = speed_profile(ref_curve, ((0.0, float(cfg_m["speed_min_m_s"])),), a_lat=G_ref["a_lat_m_s2"],
                               a_lon=G_ref["a_lon_m_s2"], v_max=member_config().vehicle_profile.max_speed_xy_m_s,
                               v0=0.0, v_end=0.0, stops=(ref_curve.length,))
        t_upper = float(nominal_time(ref_curve, v_slow, 0.0, ref_curve.length))
        sev = draw_speed_events(group.speed_profile,
                                RngKey(key.family_id, key.draw, "speed", mission=key.mission, branch=key.branch,
                                       group=key.group, segment=key.segment, attempt=key.attempt),
                                horizon_s=t_upper)
        ev = {"times_s": tuple(sev.times_s), "speeds_m_s": tuple(sev.speeds_m_s)}
        P = {**P, "speed_events": ev}
        base_fail = dict(proposal=P, business_key=_key_dict(key))
    speed_info = {"errors_s": (), "dropped": (), "events": len(ev["times_s"]), "T_upper_s": t_upper,
                  "times_s": tuple(ev["times_s"]), "speeds_m_s": tuple(ev["speeds_m_s"])}
    breaks_ref = ((0.0, v0),)
    if len(ev["times_s"]):
        try:
            smap = map_speed_events(ref_curve, ev["times_s"], ev["speeds_m_s"], (), G_ref_cfg, initial_speed_m_s=v0)
        except SimContractError as exc:
            return _plan(_reject(f"参考曲线不满足引导接口：{exc}", "reference/speed",
                                 {"error": str(exc), "shape_audit_failed": False}), **base_fail)
        breaks_ref = smap.breaks
        speed_info.update(errors_s=smap.errors_s, dropped=smap.dropped)
    breaks = {}
    for m in slots.order:
        lane = lanes[m]
        l_m = slots.offsets[m][0]
        lane_cum = np.r_[0.0, np.cumsum(np.hypot(*np.diff(lane.xy, axis=0).T))]
        base_s = cum[m][coll_idx[m]]
        out = [(0.0, v0)]
        for s_rel, v in breaks_ref[1:]:
            s_member = base_s + float(np.interp(s_c + s_rel + l_m, lane.s_ref, lane_cum))
            if s_member > out[-1][0] + 1e-9:
                out.append((s_member, float(v)))
            else:
                out[-1] = (out[-1][0], float(v))
        breaks[m] = tuple(out)
    try:
        delays, travel_to_coll, nom0 = _release_delays_ref(
            curves, {m: float(cum[m][coll_idx[m]]) for m in curves}, breaks, G_ref_cfg)
    except SimContractError as exc:
        return _plan(_reject(f"曲线不满足引导接口：{exc}", "guidance", {"error": str(exc), "shape_audit_failed": False}),
                     **base_fail)
    members, nominals = {}, {}
    for m in slots.order:
        xy = curves[m]
        members[m] = MemberPlan(m, 0, tuple((float(a), float(b)) for a, b in xy), float(states[m].p[2]),
                                float(nom0[m].curve.length), float(delays[m]), breaks[m], ())
        nominals[m] = replace(nom0[m], release_s=release_us(members[m]) / 1e6)
    wit = {"intent": "transit", "target_id": target, "turn_ranges": {}, "constraints": {}, "crossings": {},
           "screen": {}, "speed": speed_info, "delays_s": dict(delays), "travel_to_collection_s": dict(travel_to_coll),
           "chord": P.get("chord_audit"), "corridor": P.get("corridor"), "lp": P.get("lp"),
           "curve_audit": P.get("curve_audit"), "separation": None, "required_separation_m": None}
    anchors = {"collect_s": s_c, "terminal_s": s_t,
               "transit_entry_s": ref.marks.get("transit_entry"), "transit_exit_s": ref.marks.get("transit_exit")}
    order = list(slots.order)
    t0 = min(nominals[m].release_s for m in order)
    t1 = max(nominals[m].end_s for m in order)
    duration = float(t1 - t0)
    wit["nominal_duration_s"] = duration
    retreat = cfg_m["retreat_clearance_m"]
    entry_exit = {}
    for m in order:
        xy = curves[m]
        mar = _min_margins(xy, cons["base"])
        wit["constraints"][m] = dict(mar)
        bad = {k: v for k, v in mar.items() if v[0] < 0.0}
        if bad:
            name, (val, idx) = min(bad.items(), key=lambda kv: kv[1][0])
            return _fail_with(P, key, f"成员 {m} 违反约束 {name}（余量 {val:.3f} m，弦 {idx}）", name,
                              {"member": m, "constraint": name, "margin_m": val, "chord_index": idx,
                               "point": tuple(map(float, xy[idx])), "all_violations": {k: v[0] for k, v in bad.items()}},
                              wit)
        viol, cross = crossing_analysis(xy, cons["warnings"], target, band_m=ctx.params["pre_entry_warning_clearance_m"],
                                        align_m=ctx.params["alignment_length_m"])
        wit["crossings"][m] = [(c.facility_id, c.direction, round(c.s_m, 3)) for c in cross]
        if viol:
            v = viol[0]
            return _fail_with(P, key, f"成员 {m} 边界穿越不合规：{v['kind']}（设施 {v['facility']}）", "boundary_crossing",
                              {"member": m, **v, "n_violations": len(viol)}, wit)
        tc = [c for c in cross if c.facility_id == target]
        if [c.direction for c in tc] != ["in", "out"]:
            return _fail_with(P, key, f"成员 {m} 目标 warning 穿越次序 {[c.direction for c in tc]}（应恰为一入一出）",
                              "target_single_crossing", {"member": m, "directions": [c.direction for c in tc]}, wit)
        entry_exit[m] = (float(tc[0].s_m), float(tc[1].s_m))
        for fid, geom in cons["warnings"].items():
            sd = float(signed_distance(geom, xy[-1]))
            if sd < retreat:
                return _fail_with(P, key, f"成员 {m} 终点离设施 {fid} 的预警圈只有 {sd:.3f} m（< {retreat} m）",
                                  "terminal_clearance", {"member": m, "facility": fid, "signed_m": sd,
                                                         "required_m": retreat}, wit)
    # 成员映射（reference_s → member_s）与各自入/出圈弧长
    mm = {}
    for m in order:
        ln = lanes[m]
        l_m = slots.offsets[m][0]
        ms = np.asarray(cum[m][coll_idx[m]:coll_idx[m] + len(ln.xy)], float)
        mm[m] = {"reference_s": (ln.s_ref - l_m).tolist(), "shifted_reference_s": ln.s_ref.tolist(),
                 "member_s": ms.tolist(), "lateral_m": float(ln.d_m), "longitudinal_m": float(l_m),
                 "entry_member_s": entry_exit[m][0], "exit_member_s": entry_exit[m][1],
                 "collect_member_s": float(cum[m][coll_idx[m]])}
    wit["member_map_transit"] = {"schema": "member-map-transit-v16", "members": mm}
    # 名义预筛（只记录；优化后由 check_transit 硬检查）
    for m in order:
        smp = sample_nominal(members[m], include_prerelease=False, nominal=nominals[m])
        scr = screen_transit_member(ctx.facilities, target, smp.time_us, smp.p, smp.v)
        wit["screen"][m] = {"passed": scr["passed"], "conditions": scr["conditions"]}
    ref_xy = tuple((float(a), float(b)) for a, b in ref.xy[mark_idx["collect"]:mark_idx["terminal"] + 1])
    formation = {"prior": slots.prior, "start": slots.start, "realized": slots.realized,
                 "mapped_from_loose": slots.mapped_from_loose, "retreat_chain": list(retreat_chain(slots.start)),
                 "order": list(slots.order), "offsets": {m: list(v) for m, v in slots.offsets.items()},
                 "lateral_step_m": slots.lateral_step_m}
    topology = {"final": "transit", "curved": bool(P.get("curved")), "fallback_reason": P.get("fallback_reason")}
    return SegmentPlan(members=members, reference_xy=ref_xy, nominal_duration_s=duration, anchors=anchors,
                       repairs=tuple(P.get("repairs", ())), failure=None, proposal=P, formation=formation,
                       topology=topology, business_key=_key_dict(key),
                       member_nominal_s={m: float(nominals[m].travel_s) for m in order}, witnesses=wit)


# ---------------------------------------------------------------- 一次 attempt

def _echelon_payload(probe, group, b, steps_log):
    """与监视 _echelon_payload 同一协议：先 b，再 3 m；3 通过而 b 不通过时在 [3, b] 二分，直至宽度 ≤ 2/(n−1) m，
    返回已认证的通过端。所有 probe 共用同一组弦格与几何场（单车道缓存），不重抽航向或形状。"""
    got = probe("echelon", b)
    if got is not None:
        return got
    n = len(group.member_ids)
    if n < 2:
        return None
    best = probe("echelon", MIN_LATERAL_STEP_M)
    if best is None:
        return None
    lo, hi = MIN_LATERAL_STEP_M, b
    tol = 2.0 / (n - 1)
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        res = probe("echelon", mid)
        if res is not None:
            lo, best = mid, res
        else:
            hi = mid
    return best


def formation_probe_sequence(ctx, group, task, key):
    """确定性的选队形 probe 序列（主进程预建与 worker 共用）：返回 [(formation, lateral_step, offsets)]，
    按 width_then_build 的实际调用次序，直到第一个非空集合为止。用于 prewarm_transit 的请求清单。"""
    fam = ctx.family
    chain = retreat_chain(mapped_start(group.formation_prior))
    b = float(fam.lateral_spacing_m)
    fkey = RngKey(key.family_id, key.draw, "formation", mission=key.mission, branch=key.branch, group=key.group,
                  segment=key.segment, attempt=key.attempt)
    order = formation_slots(group, fam, fkey, formation=chain[0]).order
    seq = []

    def probe(name, step):
        slots = formation_slots(group, fam, fkey, formation=name, lateral_step_m=step, order=order)
        offs = [slots.offsets[m] for m in slots.order]
        seq.append((name, step, offs))
        doc = TC.load_chord_set(ctx, task.target_id, slots, ctx.cache_dir)
        return {"slots": slots, "doc": doc} if doc["cells"] else None

    def width_probe(name):
        if name == "echelon":
            return _echelon_payload(probe, group, b, [])
        return probe(name, None)

    width_then_build(chain, width_probe, lambda name, payload: payload)
    return seq


def propose_and_build(ctx, group, task, states, key):
    """一次随机构造（一个 attempt）：宽度先定队形（width_then_build；队形 probe = 该队形全部真实车道的离散弦集合
    是否非空）→ 可行格均匀抽一格 → 集合站点均匀抽一个 → 精确弦检查 → 走廊与一次曲线 LP（不可用即本格直线）→
    曲线精确复核 → 初始可视图路由 → 候选构造与检查。下游任何失败原样返回，不改队形、不换格。"""
    S = TransitSetup(ctx, group, task, states, key)
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
            doc = TC.load_chord_set(ctx, task.target_id, slots, ctx.cache_dir)
            _tick(S, "chord_set_s", time.perf_counter() - t0)
            steps_log.append({"formation": name, "lateral_step_m": step, "feasible_cells": len(doc["cells"]),
                              "n_cells": doc["n_cells"], "query_id": doc.get("query_id"),
                              "reasons": doc.get("reasons")})
            return {"slots": slots, "doc": doc, "lateral_step_m": step} if doc["cells"] else None

        def width_probe(name):
            if name == "echelon":
                return _echelon_payload(probe, group, b, steps_log)
            return probe(name, None)

        def build(name, payload):
            return _build_with_cells(S, ctx, group, task, states, key, payload, b, steps_log, rng, crng)

        plan = width_then_build(chain, width_probe, build)
        if plan is not None:
            return plan
        return _stage_fail("transit_chord_set", "所有队形下离散穿越弦集合为空（approx_empty 查询）", None, key,
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
    ci = int(rng.integers(0, len(cells)))
    ti, h, xt, x_in, Ds = cells[ci]
    D_c = float(Ds[int(rng.integers(0, len(Ds)))])
    xc = float(x_in) - D_c
    kmin, kmax = int(S.M["spline_basis_min"]), int(S.M["spline_basis_max"])
    K = int(rng.integers(kmin, kmax + 1))
    v = rng.random(K)
    z = _logit(v)
    th = TC.thetas()[int(ti)]
    u, n = TC.frame(th)
    o = np.asarray(tgt.center, float)
    offsets = [slots.offsets[m] for m in slots.order]
    P = {"intent": "transit", "theta_idx": int(ti), "theta_deg": float(TC.THETA_STEP_DEG * int(ti)), "h_m": float(h),
         "origin_xy": tuple(map(float, o)), "u": tuple(map(float, u)), "n": tuple(map(float, n)),
         "cell_index": ci, "cells_feasible": len(cells), "chord_query_id": doc.get("query_id"),
         "x_c": xc, "x_t": float(xt), "x_in": float(x_in), "collect_D_m": D_c, "collect_candidates": len(Ds),
         "K": K, "logit_quantiles": tuple(map(float, v)), "logit_coefficients": tuple(map(float, z)),
         "member_slot_order": slots.order, "formation": slots.realized,
         "lateral_step_m": slots.lateral_step_m if slots.realized == "echelon" else None,
         "repairs": tuple(repairs), "formation_steps": steps_log}
    # 精确弦检查（抽中的唯一格，一次）
    t0 = time.perf_counter()
    audit = TC.assess_straight_bundle(S.base, S.warn, task.target_id, o + float(h) * n, u, offsets, xc, float(xt),
                                      band_m=S.band, align_m=S.align, retreat_m=S.M["retreat_clearance_m"])
    _tick(S, "chord_exact_s", time.perf_counter() - t0)
    P["chord_audit"] = {"feasible": audit["feasible"], "first_error": audit["first_error"],
                        "margins": {k: float(v) for k, v in audit["margins"].items()}}
    if not audit["feasible"]:
        return _stage_fail("chord_exact_audit", "抽中的离散弦未通过精确弦检查（不换格）", P, key,
                           {"audit": P["chord_audit"], "shape_audit_failed": True, "draw": draw_summary(P, slots.realized)})
    ent = TC.line_sublevel(tgt.layers["warning"], o + float(h) * n, u, 0.0)
    P["x_entry_ref"], P["x_exit_ref"] = (float(ent[0]), float(ent[1])) if ent is not None else (None, None)
    # 走廊与一次 LP（附录裁定 1）
    t0 = time.perf_counter()
    cor = TC.corridor_rows(ctx, task, {"theta_idx": ti, "h": h}, slots)
    _tick(S, "corridor_s", time.perf_counter() - t0)
    P["corridor"] = {k: cor[k] for k in ("available", "reason", "D", "inset_interval", "rows_total", "certified_rows",
                                         "run", "certified_length_m", "inset_length_m")}
    P["curve"] = None
    P["curved"] = False
    P["fallback_reason"] = None
    P["lp"] = None
    if not cor["available"]:
        P["fallback_reason"] = cor["reason"]
    else:
        t0 = time.perf_counter()
        lp = curve_lp(np.asarray(cor["x"]), np.asarray(cor["lo"]), np.asarray(cor["hi"]), float(h), z, D_m=cor["D"])
        _tick(S, "lp_s", time.perf_counter() - t0)
        P["lp"] = {k: lp.get(k) for k in ("feasible", "fallback_reason", "lp_status", "lp_message", "lp_nit",
                                          "objective", "max_residual", "kappa_max", "slope_max", "n_controls",
                                          "seconds")}
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
                return _stage_fail("transit_shape_audit", "LP 曲线未通过精确曲率/斜率复核（不重抽）", P, key,
                                   {"curve_audit": ca, "shape_audit_failed": True,
                                    "draw": draw_summary(P, slots.realized)})
    # 初始可视图路由（集合槽位；首次入圈前绕开目标 warning）
    C = o + xc * u + float(h) * n
    P["collection_xy"] = tuple(map(float, C))
    P["terminal_xy"] = tuple(map(float, o + float(xt) * u + float(h) * n))
    t0 = time.perf_counter()
    starts, meta = plan_starts(S, slots, C, u, crng, route_fn=_transit_route(task.target_id))
    _tick(S, "route_s", time.perf_counter() - t0)
    if starts is None:
        return _stage_fail("start_route", f"成员 {meta} 没有可用的起点路由", P, key,
                           {"route_stats": dict(S.stats), "shape_audit_failed": False,
                            "draw": draw_summary(P, slots.realized)})
    P["start_connections"] = starts
    P["starts"] = meta
    t0 = time.perf_counter()
    plan = build_candidate(ctx, group, task, states, key, P)
    _tick(S, "candidate_s", time.perf_counter() - t0)
    if plan.failure is not None:
        w = dict(plan.failure.witness or {})
        w["draw"] = draw_summary(plan.proposal or P, slots.realized)
        w.setdefault("shape_audit_failed", False)
        plan = replace(plan, failure=replace(plan.failure, witness=w))
    return plan
