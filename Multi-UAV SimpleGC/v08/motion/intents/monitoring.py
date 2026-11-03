"""监视单段：具体构造与候选检查（V8-12 第 3 部分；指令 3.3–3.8）。

build_candidate 不重抽任何已给提案：先验抽样在外层完成（plan.py）。给定完整提案，它做确定性的构造：
参考路径（汇合点 → 入圈直线 → 巡逻 → 出圈直线 → 终点）→ 队形槽位 → 成员车道 + 各自的起点连接 →
速度剖面 → 释放延迟 → 逐成员精确几何、边界穿越、名义判据预筛选 → 连续时间间距 → 1800 s 预算。
任一检查不过，返回带 Failure 的 SegmentPlan（candidate_rejected，保留原始数值见证），不放宽任何余量。

提案字典的键（单位 m、rad、m/s）：
  topology: "loop" | "retrace"；center_xy、rho0_m、coefficients_m、phase_rad、direction(±1)；
  loop: laps；retrace: passes ((φ_from, φ_to), ...)、turns (每次掉头的图元元组)、traversals、arc_span_rad、
        turn_kind、turn_radius_m；
  collection_xy、entry_point_xy、exit_point_xy、terminal_xy（编组参考锚点）；
  member_slot_order、formation、lateral_step_m（可选）；
  collection_bezier_controls {成员: 6 个控制点}；reference_ingress、reference_egress（图元元组）；
  speed_events {"times_s", "speeds_m_s"}（可选）。
"""
import math
from dataclasses import replace

import numpy as np

from ...config import load_config
from ...contract.monitoring import Failure, MemberPlan, SegmentPlan
from ...scene.exact import polyline_clearance, signed_distance
from ...scene.field import Clearance
from ...sim.guidance import make_curve
from ...sim.types import SimContractError
from ..connect import crossing_analysis, release_delays
from ..formation import derive_members, formation_slots, make_reference, retreat_chain
from ..nominal import (continuous_minimum, member_nominal, piece_arrays, release_us, sample_nominal)
from ..nominal_checks import screen_member
from ..path import PathError, periodic_radius_derivs, sample_primitives
from ..speed import map_speed_events

NODE_TOL_M = 1e-6
FAR_M = 5.0   # polyline_clearance 快速路径：真实余量小于它的弦仍精确


# ---------------------------------------------------------------- 约束集合

def monitoring_constraints(ctx, target_id):
    """本项各阶段的精确约束（余量来自冻结几何配置；35/10/35 的含义见附录裁定 8）。"""
    P = ctx.params
    mon = P["monitoring"]
    fac = ctx.facility_by_id
    tgt = fac[target_id]
    base = [Clearance("world", ctx.world, -1, P["world_margin_m"])]
    base += [Clearance("obstacle:" + i, g, 1, P["obstacle_margin_m"]) for i, g in ctx.obstacles]
    base += [Clearance("alert:" + f.id, f.layers["alert"], 1, P["forbidden_margin_m"]) for f in ctx.facilities]
    patrol = [Clearance("target_alert_clearance", tgt.layers["alert"], 1, mon["alert_clearance_m"]),
              Clearance("target_warning_inset", tgt.layers["warning"], -1, mon["warning_inset_m"])]
    patrol += [Clearance("warning_edge:" + f.id, f.layers["warning"], 0, P["pre_entry_warning_clearance_m"])
               for f in ctx.facilities if f.id != target_id]
    warnings = {f.id: f.layers["warning"] for f in ctx.facilities}
    return {"base": base, "patrol": patrol, "warnings": warnings}


# ---------------------------------------------------------------- 图元位姿

def _loop_pose(c, rho0, coef, phi, direction):
    rho, d1, _ = periodic_radius_derivs(np.array([phi]), rho0, coef)
    rho, d1 = float(rho[0]), float(d1[0])
    x = c[0] + rho * math.cos(phi)
    y = c[1] + rho * math.sin(phi)
    vx = d1 * math.cos(phi) - rho * math.sin(phi)
    vy = d1 * math.sin(phi) + rho * math.cos(phi)
    return np.array([x, y]), math.atan2(direction * vy, direction * vx)


def prim_start_pose(prim):
    k = prim[0]
    if k == "line":
        p0, p1 = np.asarray(prim[1], float), np.asarray(prim[2], float)
        return p0, math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    if k == "arc":
        c, r, a0, sw = np.asarray(prim[1], float), float(prim[2]), float(prim[3]), float(prim[4])
        return c + r * np.array([math.cos(a0), math.sin(a0)]), a0 + math.copysign(math.pi / 2, sw)
    if k == "bezier5":
        P = np.asarray(prim[1], float)
        return P[0], math.atan2(P[1][1] - P[0][1], P[1][0] - P[0][0])
    if k == "spline_arc":
        return _loop_pose(np.asarray(prim[1], float), prim[2], prim[3], prim[4], 1.0 if prim[5] > prim[4] else -1.0)
    raise PathError(f"未知图元：{k!r}")


def prim_end_pose(prim):
    k = prim[0]
    if k == "line":
        p0, p1 = np.asarray(prim[1], float), np.asarray(prim[2], float)
        return p1, math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    if k == "arc":
        c, r, a0, sw = np.asarray(prim[1], float), float(prim[2]), float(prim[3]), float(prim[4])
        a1 = a0 + sw
        return c + r * np.array([math.cos(a1), math.sin(a1)]), a1 + math.copysign(math.pi / 2, sw)
    if k == "bezier5":
        P = np.asarray(prim[1], float)
        return P[5], math.atan2(P[5][1] - P[4][1], P[5][0] - P[4][0])
    if k == "spline_arc":
        return _loop_pose(np.asarray(prim[1], float), prim[2], prim[3], prim[5], 1.0 if prim[5] > prim[4] else -1.0)
    raise PathError(f"未知图元：{k!r}")


def patrol_primitives(P):
    c = tuple(P["center_xy"])
    rho0, coef = float(P["rho0_m"]), tuple(float(x) for x in P["coefficients_m"])
    if P["topology"] == "loop":
        d = 1.0 if P["direction"] >= 0 else -1.0
        phi0 = float(P["phase_rad"])
        return [("spline_arc", c, rho0, coef, phi0, phi0 + d * float(P["laps"]) * 2.0 * math.pi)]
    if P["topology"] == "retrace":
        out = []
        passes, turns = P["passes"], P["turns"]
        for k, (a, b) in enumerate(passes):
            out.append(("spline_arc", c, rho0, coef, float(a), float(b)))
            if k < len(passes) - 1:
                out.extend(turns[k])
        return out
    raise PathError(f"未知拓扑：{P['topology']!r}")


# ---------------------------------------------------------------- 参考路径

def build_reference(P, ext_m, spacing):
    ing = list(P["reference_ingress"])
    eg = list(P["reference_egress"])
    pat = patrol_primitives(P)
    head, tail = [], []
    if ext_m > 0.0:
        p0, th = prim_start_pose(ing[0])
        u = np.array([math.cos(th), math.sin(th)])
        head = [("line", tuple(p0 - ext_m * u), tuple(p0))]
        p1, th1 = prim_end_pose(eg[-1])
        u1 = np.array([math.cos(th1), math.sin(th1)])
        tail = [("line", tuple(p1), tuple(p1 + ext_m * u1))]
    prims = head + ing + pat + eg + tail
    s = sample_primitives(prims, spacing)
    iv = s.intervals
    h, n_i, n_p = len(head), len(ing), len(pat)
    i_collect = iv[h][0]
    i_pat0 = iv[h + n_i][0]
    i_pat1 = iv[h + n_i + n_p - 1][1]
    i_term = iv[h + n_i + n_p + len(eg) - 1][1]
    marks = {"collect": i_collect, "patrol_start": i_pat0, "patrol_end": i_pat1, "terminal": i_term}
    segs = [("ingress", i_collect, i_pat0), ("patrol", i_pat0, i_pat1), ("egress", i_pat1, i_term)]
    ref = make_reference(s, marks, segs)
    return ref, {k: int(v) for k, v in marks.items()}


# ---------------------------------------------------------------- 检查

def _min_margins(xy, cons, indices=None):
    pts = xy if indices is None else xy[indices[0]:indices[1] + 1]
    out = {}
    for c in cons:
        if len(pts) < 2:
            continue
        m = polyline_clearance(c.geometry, pts, sense=c.sense, minimum_m=c.minimum_m, fast_far_m=FAR_M)
        k = int(np.argmin(m))
        out[c.name] = (float(m[k]), k if indices is None else k + indices[0])
    return out


def _reject(reason, feasible_set, witness):
    return Failure("candidate_rejected", reason, feasible_set, witness, None)


def _plan(failure, **kw):
    return SegmentPlan(members={}, reference_xy=(), nominal_duration_s=math.nan, anchors={}, repairs=(),
                       failure=failure, **kw)


def build_candidate(ctx, group, task, states, occupied, key, proposal, duration_only=False):
    """duration_only=True 时，名义总时长检查通过就返回一个没有成员曲线的占位计划（只供预算修复的搜索使用）。"""
    P = proposal
    cfg_m = load_config("monitoring").values
    G = load_config("guidance").values
    spacing = ctx.params["curve_spacing_m"]
    target = task.target_id
    cons = monitoring_constraints(ctx, target)
    base_fail = dict(proposal=P, business_key=_key_dict(key))
    try:
        slots = formation_slots(group, ctx.family, key, formation=P.get("formation"),
                                lateral_step_m=P.get("lateral_step_m"), order=P.get("member_slot_order"))
        ext = slots.max_longitudinal_m
        ref, mark_idx = build_reference(P, 0.0 if ext == 0.0 else ext + 1.0, spacing)
        s_c, s_t = ref.marks["collect"], ref.marks["terminal"]
        lanes = derive_members(ref, slots, (s_c, s_t), spacing_m=spacing)
    except (PathError, ValueError) as exc:
        return _plan(_reject(f"构造失败：{exc}", "reference/lanes", {"error": str(exc)}), **base_fail)

    # 成员完整曲线 = 起点连接 + 车道
    curves, coll_idx, lane_off = {}, {}, {}
    for m in slots.order:
        prims = P["start_connections"][m] if "start_connections" in P else [("bezier5", P["collection_bezier_controls"][m])]
        p_init = np.asarray(states[m].p[:2], float)
        try:
            sb = sample_primitives(list(prims), spacing)
        except PathError as exc:
            return _plan(_reject(f"成员 {m} 起点连接图元非法：{exc}", f"start:{m}", {"member": m, "error": str(exc)}),
                         **base_fail)
        if float(np.hypot(*(sb.xy[0] - p_init))) > NODE_TOL_M:
            return _plan(_reject("起点连接的第一个点不是成员初始位置", f"start:{m}",
                                 {"member": m, "start": tuple(sb.xy[0]), "initial": tuple(p_init)}), **base_fail)
        lane = lanes[m]
        if float(np.hypot(*(sb.xy[-1] - lane.xy[0]))) > NODE_TOL_M:
            return _plan(_reject("起点连接末端与槽位不符", f"slot:{m}",
                                 {"member": m, "bezier_end": tuple(sb.xy[-1]), "slot": tuple(lane.xy[0])}), **base_fail)
        curves[m] = np.vstack([sb.xy, lane.xy[1:]])
        coll_idx[m] = len(sb.xy) - 1
        lane_off[m] = len(sb.xy) - 1
    cum = {m: np.r_[0.0, np.cumsum(np.hypot(*np.diff(curves[m], axis=0).T))] for m in curves}

    # 速度剖面
    v0 = float(group.speed_profile.initial_speed_m_s)
    ev = P.get("speed_events") or {"times_s": (), "speeds_m_s": ()}
    speed_info = {"errors_s": (), "dropped": (), "events": len(ev["times_s"])}
    breaks_ref = ((0.0, v0),)
    if len(ev["times_s"]):
        try:
            ref_curve = make_curve(ref.xy[mark_idx["collect"]:mark_idx["terminal"] + 1],
                                   max_chord_m=G["max_chord_m"], max_turn_rad=G["max_turn_per_chord_rad"])
            smap = map_speed_events(ref_curve, ev["times_s"], ev["speeds_m_s"], (), None, initial_speed_m_s=v0)
        except SimContractError as exc:
            return _plan(_reject(f"参考曲线不满足引导接口：{exc}", "reference/speed", {"error": str(exc)}), **base_fail)
        breaks_ref = smap.breaks
        speed_info = {"errors_s": smap.errors_s, "dropped": smap.dropped, "events": len(ev["times_s"])}
    breaks = {}
    for m in slots.order:
        lane = lanes[m]
        l = slots.offsets[m][0]
        lane_cum = np.r_[0.0, np.cumsum(np.hypot(*np.diff(lane.xy, axis=0).T))]
        base_s = cum[m][coll_idx[m]]
        out = [(0.0, v0)]
        for s_rel, v in breaks_ref[1:]:
            s_member = base_s + float(np.interp(s_c + s_rel + l, lane.s_ref, lane_cum))
            if s_member > out[-1][0] + 1e-9:
                out.append((s_member, float(v)))
            else:
                out[-1] = (out[-1][0], float(v))
        breaks[m] = tuple(out)

    # 释放延迟（同时拿到各成员的名义运动，避免对同一条曲线重复做 make_curve / speed_profile）
    try:
        delays, travel_to_coll, nom0 = release_delays(
            curves, {m: float(cum[m][coll_idx[m]]) for m in curves}, breaks, return_nominals=True)
    except SimContractError as exc:
        return _plan(_reject(f"曲线不满足引导接口：{exc}", "guidance", {"error": str(exc)}), **base_fail)

    members, nominals = {}, {}
    for m in slots.order:
        xy = curves[m]
        members[m] = MemberPlan(m, 0, tuple((float(a), float(b)) for a, b in xy), float(states[m].p[2]),
                                float(nom0[m].curve.length), float(delays[m]), breaks[m], ())
        nominals[m] = replace(nom0[m], release_s=release_us(members[m]) / 1e6)

    wit = {"constraints": {}, "crossings": {}, "screen": {}, "separation": None, "speed": speed_info,
           "delays_s": dict(delays), "travel_to_collection_s": dict(travel_to_coll)}
    anchors = {"collect_s": s_c, "patrol_start_s": ref.marks["patrol_start"], "patrol_end_s": ref.marks["patrol_end"],
               "terminal_s": s_t}
    p_lo, p_hi = ref.marks["patrol_start"], ref.marks["patrol_end"]
    # 名义总时长与 1800 s 预算：自首名成员释放到最后成员停止保持结束，不含共同的 20 s 预保持。
    # 它只依赖名义时钟，比几何、判据和间距检查便宜得多，所以先查（失败的原因链仍记录第一个失败阶段）。
    order = list(slots.order)
    wit["patrol_time_s"] = {}
    for m in order:
        sref = np.concatenate([np.full(coll_idx[m], -1.0), lanes[m].s_ref])
        pidx = np.flatnonzero((sref >= p_lo - 1e-9) & (sref <= p_hi + 1e-9))
        if len(pidx) >= 2:
            tn = nominals[m].t_nodes
            wit["patrol_time_s"][m] = float(tn[min(int(pidx[-1]), len(tn) - 1)] - tn[int(pidx[0])])
    t0 = min(nominals[m].release_s for m in order)
    t1 = max(nominals[m].end_s for m in order)
    duration = float(t1 - t0)
    wit["nominal_duration_s"] = duration
    if duration > cfg_m["nominal_budget_s"]:
        return _fail_with(P, key, f"名义总时长 {duration:.1f} s 超过预算 {cfg_m['nominal_budget_s']} s", "duration_budget",
                          {"duration_s": duration, "budget_s": cfg_m["nominal_budget_s"],
                           "patrol_time_s": dict(wit["patrol_time_s"])}, wit)
    if duration_only:
        return SegmentPlan(members={}, reference_xy=(), nominal_duration_s=duration, anchors=anchors, repairs=(),
                           failure=None, proposal=P, business_key=_key_dict(key), witnesses=wit)
    crossing_log = {}
    for m in slots.order:
        xy = curves[m]
        lane = lanes[m]
        sref = np.concatenate([np.full(coll_idx[m], -1.0), lane.s_ref])
        pidx = np.flatnonzero((sref >= p_lo - 1e-9) & (sref <= p_hi + 1e-9))
        mar = _min_margins(xy, cons["base"])
        if len(pidx) >= 2:
            mar.update(_min_margins(xy, cons["patrol"], (int(pidx[0]), int(pidx[-1]))))
        wit["constraints"][m] = {k: v for k, v in mar.items()}
        bad = {k: v for k, v in mar.items() if v[0] < 0.0}
        if bad:
            name, (val, idx) = min(bad.items(), key=lambda kv: kv[1][0])
            return _fail_with(P, key, f"成员 {m} 违反约束 {name}（余量 {val:.3f} m，弦 {idx}）", name,
                              {"member": m, "constraint": name, "margin_m": val, "chord_index": idx,
                               "point": tuple(map(float, xy[idx])), "all_violations": {k: v[0] for k, v in bad.items()}},
                              wit)
        viol, cross = crossing_analysis(xy, cons["warnings"], target, band_m=ctx.params["pre_entry_warning_clearance_m"],
                                        align_m=ctx.params["alignment_length_m"])
        crossing_log[m] = [(c.facility_id, c.direction, round(c.s_m, 3)) for c in cross]
        if viol:
            v = viol[0]
            return _fail_with(P, key, f"成员 {m} 边界穿越不合规：{v['kind']}（设施 {v['facility']}）", "boundary_crossing",
                              {"member": m, **v, "n_violations": len(viol)}, wit)
        retreat = cfg_m["retreat_clearance_m"]
        for fid, geom in cons["warnings"].items():
            sd = float(signed_distance(geom, xy[-1]))
            if sd < retreat:
                return _fail_with(P, key, f"成员 {m} 终点离设施 {fid} 的预警圈只有 {sd:.3f} m（< {retreat} m）",
                                  "terminal_clearance", {"member": m, "facility": fid, "signed_m": sd,
                                                         "required_m": retreat}, wit)
    wit["crossings"] = crossing_log

    # 名义判据预筛选（冻结检测器的纯 NumPy 函数体）：逐成员
    for m in slots.order:
        smp = sample_nominal(members[m], include_prerelease=False, nominal=nominals[m])
        scr = screen_member(ctx.facilities, target, smp.time_us, smp.p, smp.v)
        wit["screen"][m] = {"patrol_revisit": scr["patrol_revisit"], "dwell_anywhere": bool(scr["dwell_anywhere"]["detected"]),
                            "max_target_layer": scr["max_target_layer"], "max_other_layer": scr["max_other_layer"],
                            "revisit": {k: scr["revisit"][k] for k in ("detected", "t1", "t2", "distance_m",
                                                                      "departure_m", "azimuth_coverage_deg")}}
        if not scr["patrol_revisit"]:
            return _fail_with(P, key, f"成员 {m} 的名义轨迹没有取得合格重访", "nominal_revisit", {"member": m}, wit)
        if scr["dwell_anywhere"]["detected"]:
            return _fail_with(P, key, f"成员 {m} 的名义轨迹在全窗口上检出驻留", "nominal_dwell",
                              {"member": m, "dwell": {k: scr["dwell_anywhere"][k] for k in ("frame_index", "t_s")}}, wit)
        if scr["max_target_layer"] > 1 or scr["max_other_layer"] > 1:
            return _fail_with(P, key, f"成员 {m} 进入了不允许的圈层", "nominal_layers",
                              {"member": m, "max_target_layer": scr["max_target_layer"],
                               "max_other_layer": scr["max_other_layer"]}, wit)

    # 连续时间间距：D_lane = 冻结的 2 m + 2 × 跟踪管 0.5 m
    d_lane = 2.0 + 2.0 * cfg_m["tracking_tube_m"]
    arrays = {m: piece_arrays(nominal=nominals[m]) for m in slots.order}
    worst = None
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            r = continuous_minimum(arrays[order[i]], arrays[order[j]])
            if worst is None or r.min_distance_m < worst["min_distance_m"]:
                worst = {"min_distance_m": r.min_distance_m, "time_s": r.time_s, "pair": (order[i], order[j]),
                         "relative": r.r0}
    wit["separation"] = worst
    wit["required_separation_m"] = d_lane
    if worst is not None and not worst["min_distance_m"] >= d_lane:
        return _fail_with(P, key, f"成员对 {worst['pair']} 的连续时间最小间距 {worst['min_distance_m']:.3f} m < {d_lane} m",
                          "separation", worst, wit)

    ref_xy = tuple((float(a), float(b)) for a, b in ref.xy[mark_idx["collect"]:mark_idx["terminal"] + 1])
    formation = {"prior": slots.prior, "start": slots.start, "realized": slots.realized,
                 "mapped_from_loose": slots.mapped_from_loose, "retreat_chain": list(retreat_chain(slots.start)),
                 "order": list(slots.order), "offsets": {m: list(v) for m, v in slots.offsets.items()},
                 "lateral_step_m": slots.lateral_step_m}
    topology = {"final": P["topology"], "laps": P.get("laps"), "traversals": P.get("traversals"),
                "turn_kind": P.get("turn_kind"), "arc_span_rad": P.get("arc_span_rad"),
                **(P.get("topology_info") or {})}
    return SegmentPlan(members=members, reference_xy=ref_xy, nominal_duration_s=duration, anchors=anchors,
                       repairs=tuple(P.get("repairs", ())), failure=None, proposal=P, formation=formation,
                       topology=topology, business_key=_key_dict(key),
                       member_nominal_s={m: float(nominals[m].travel_s) for m in order}, witnesses=wit)


def _key_dict(key):
    return {"family_id": key.family_id, "draw": key.draw, "mission": key.mission, "branch": key.branch,
            "group": key.group, "segment": key.segment, "attempt": key.attempt}


def _fail_with(P, key, reason, feasible_set, witness, wit):
    return _plan(_reject(reason, feasible_set, witness), proposal=P, business_key=_key_dict(key), witnesses=wit)


# ======================================================================================================
# 提案采样（指令 3.3–3.6）：先求可行域、再抽曲线。
# 分辨率常量只是数值扫描的精细度（不是业务阈值）：极坐标 360 行、径向步长 2 m、参考加密 0.5 m。
# 内部搜索预算（候选圆心数、入口候选数）是采样器的搜索宽度，随结果一起记录。
# ======================================================================================================

from ...sampler.keys import RngKey, rng_for  # noqa: E402
from ..connect import (MIN_STRAIGHT_M, corner_radius_bounds, fillet_route, left_normal, skeleton_planner,  # noqa: E402
                       unit)
from ..formation import MIN_LATERAL_STEP_M, formation_key, mapped_start  # noqa: E402
from ..path import connect_poses, interpolating_coefficients, sample_loop  # noqa: E402
from ..speed import draw_speed_events  # noqa: E402

PHI_ROWS = 360
R_STEP_M = 2.0
N_CENTERS = 6
N_ENTRIES = 12
N_REDRAWS = 6
ALPHA_SCAN = tuple(float(x) for x in np.round(np.linspace(1.0, 0.0, 21), 3))
CURV_DERATE = 0.98


class _Setup:
    """一次规划所用的约束、组合栅格与随机流（同一族同一目标共享栅格）。"""

    def __init__(self, ctx, group, task, states, key):
        self.ctx, self.group, self.task, self.states, self.key = ctx, group, task, states, key
        self.target = task.target_id
        self.cons = monitoring_constraints(ctx, self.target)
        P = ctx.params
        fac = ctx.facility_by_id
        self.tgt = fac[self.target]
        self.others = [f for f in ctx.facilities if f.id != self.target]
        base, patrol = self.cons["base"], self.cons["patrol"]
        edge_others = [Clearance("warning_edge:" + f.id, f.layers["warning"], 0, P["pre_entry_warning_clearance_m"])
                       for f in self.others]
        self.M = load_config("monitoring").values
        retreat = self.M["retreat_clearance_m"]
        coll_lo, coll_hi = P["collection_clearance_m"]
        self.cg_route = ctx.combined("route", base)
        self.cg_patrol = ctx.combined(("patrol", self.target), base + patrol)
        inside_target = [Clearance("target_warning_inside_band", self.tgt.layers["warning"], -1,
                                   P["pre_entry_warning_clearance_m"] + 1.0)]
        self.cg_inner = ctx.combined(("inner", self.target), base + edge_others + inside_target)
        # 汇合参考位置在 [50,250] m 带内（指令 2.4）；各成员槽位围绕它展开，只需满足物理余量（世界、限制区、预警圈外），
        # 所以带的两侧不加槽位足迹余量，物理约束加足迹余量。
        phys = base + [Clearance("out_warning:" + f.id, f.layers["warning"], 1, P["pre_entry_warning_clearance_m"])
                       for f in ctx.facilities]
        band = [Clearance("coll_lo", self.tgt.layers["warning"], 1, coll_lo),
                Clearance("coll_hi", self.tgt.layers["warning"], -1, -coll_hi)]
        self.cg_collect_phys = ctx.combined(("collect_phys", self.target), phys)
        self.cg_collect_band = ctx.combined(("collect_band", self.target), band)
        term = base + [Clearance("term_out:" + f.id, f.layers["warning"], 1, retreat) for f in ctx.facilities]
        self.cg_term = ctx.combined("terminal", term)
        self.center = np.asarray(self.tgt.center, float)
        self.warn = {f.id: f.layers["warning"] for f in ctx.facilities}
        self.band = P["pre_entry_warning_clearance_m"]
        self.align = P["alignment_length_m"]
        from task_v07.criteria import load_criteria
        self.criteria = load_criteria()["detectors"]["revisit"]
        self.v_cap = self.M["speed_max_m_s"]
        self.G = load_config("guidance").values
        self.stats = {}
        self.sev = draw_speed_events(group.speed_profile,
                                     RngKey(key.family_id, key.draw, "speed", mission=key.mission, branch=key.branch,
                                            group=key.group, segment=key.segment, attempt=key.attempt),
                                     horizon_s=self.M["nominal_budget_s"])
        self.v0 = float(group.speed_profile.initial_speed_m_s)

    def rng(self, purpose):
        k = self.key
        return rng_for(RngKey(k.family_id, k.draw, purpose, mission=k.mission, branch=k.branch, group=k.group,
                              segment=k.segment, attempt=k.attempt))


def prewarm(ctx, group, task, states, key):
    """建立（或从缓存读入）该目标所需的组合栅格和边界点，不做任何规划。
    运行器在计时规划之前调用，使冷缓存时间与每段规划耗时分开报告。"""
    S = _Setup(ctx, group, task, states, key)
    _boundary_points(S)
    return S


def _bisect_boundary(geom, center, angles, r_hi):
    lo = np.zeros(len(angles))
    hi = np.full(len(angles), float(r_hi))
    e = np.stack([np.cos(angles), np.sin(angles)], axis=1)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        inside = signed_distance(geom, center[None] + mid[:, None] * e) <= 0.0
        lo = np.where(inside, mid, lo)
        hi = np.where(inside, hi, mid)
    return center[None] + hi[:, None] * e


def _boundary_points(S):
    key = ("boundary", S.target)
    if key not in S.ctx.extra:
        from ...scene.exact import bounding_box
        g = S.tgt.layers["warning"]
        x0, y0, x1, y1 = bounding_box(g)
        r_hi = 1.5 * float(np.hypot(x1 - x0, y1 - y0))
        ang = np.linspace(0.0, 2 * np.pi, 720, endpoint=False)
        with S.ctx.cold_build():
            pts = _bisect_boundary(g, S.center, ang, r_hi)
            nxt = np.roll(pts, -1, axis=0)
            prv = np.roll(pts, 1, axis=0)
            w = 0.5 * (np.hypot(*(nxt - pts).T) + np.hypot(*(pts - prv).T))
            S.ctx.extra[key] = (pts, w / w.sum())
    return S.ctx.extra[key]


def _lane_points(xy, theta, d):
    n = np.stack([-np.sin(theta), np.cos(theta)], axis=1)
    return xy + d * n


def _proxy_prims(S, prims, shifts, cg, *, arcs_avoid_bands=False, spacing=1.0):
    """图元在各车道偏移下的保守栅格检查（并要求偏移不翻转曲率）。"""
    try:
        smp = sample_primitives(list(prims), spacing)
    except (PathError, ValueError):
        return False
    from ..path import kappa_limit, lane_curvature_ok
    limit = kappa_limit(S.ctx.params["curve_spacing_m"], S.G["max_turn_per_chord_rad"])
    kpos, kneg = float(max(smp.kappa.max(), 0.0)), float(min(smp.kappa.min(), 0.0))
    for d in shifts:
        if not lane_curvature_ok(kpos, kneg, d, limit):
            return False
        if not np.all(cg.ok(_lane_points(smp.xy, smp.theta, d))):
            return False
    if arcs_avoid_bands:
        for (a, b), prim in zip(smp.intervals, prims):
            if prim[0] == "line":
                continue
            seg = smp.xy[a:b + 1]
            for geom in S.warn.values():
                if np.any(np.abs(signed_distance(geom, seg)) < S.band):
                    return False
    return True


# ---------------------------------------------------------------- 极坐标可行带

def _polar_mask(S, center, sigma, shifts, rs):
    phis = 2 * np.pi * np.arange(PHI_ROWS) / PHI_ROWS
    e = np.stack([np.cos(phis), np.sin(phis)], axis=1)
    mask = np.ones((PHI_ROWS, len(rs)), bool)
    for d in shifts:
        rr = rs - sigma * d                       # 逆时针(σ=+1)时左法向向内：车道半径 r − d
        pts = center[None, None, :] + rr[None, :, None] * e[:, None, :]
        mask &= S.cg_patrol.ok(pts) & (rr > 0.0)[None, :]
    return mask


def _components(mask):
    P, R = mask.shape
    runs = []
    row_runs = [[] for _ in range(P)]
    for j in range(P):
        edges = np.flatnonzero(np.diff(np.r_[False, mask[j], False].astype(np.int8)))
        for lo, hi in zip(edges[::2].tolist(), edges[1::2].tolist()):
            row_runs[j].append(len(runs))
            runs.append((j, lo, hi - 1))
    parent = list(range(len(runs)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for j in range(P):
        k = (j + 1) % P
        for a in row_runs[j]:
            for b in row_runs[k]:
                if runs[a][1] <= runs[b][2] and runs[b][1] <= runs[a][2]:
                    ra, rb = find(a), find(b)
                    if ra != rb:
                        parent[ra] = rb
    comps = {}
    for i in range(len(runs)):
        comps.setdefault(find(i), []).append(i)
    out = []
    for ids in comps.values():
        rows = {}
        for i in ids:
            rows.setdefault(runs[i][0], []).append((runs[i][1], runs[i][2]))
        out.append({"rows": rows, "wrapping": len(rows) == P, "n_rows": len(rows)})
    return out


def _draw_radius(rng, comp, row, rs, with_run=False):
    runs = comp["rows"][row]
    w = np.array([hi - lo + 1 for lo, hi in runs], float)
    lo, hi = runs[int(rng.choice(len(runs), p=w / w.sum()))]
    r = float(rs[lo]) if hi == lo else float(rs[lo] + rng.random() * (rs[hi] - rs[lo]))
    return (r, (float(rs[lo]), float(rs[hi]))) if with_run else r


def _spline_from_radii(radii, alpha):
    c = interpolating_coefficients(radii)
    rho0 = float(np.mean(c))
    a = (c - rho0) * alpha
    return rho0, tuple(float(x) for x in a)


def _ring_ok(S, center, rho0, coef, phi0, phi1, shifts):
    try:
        xy, th, kp, _ = sample_loop(center, rho0, coef, phi0, phi1, 1.0)
    except PathError:
        return False
    from ..path import kappa_limit, lane_curvature_ok
    limit = kappa_limit(S.ctx.params["curve_spacing_m"], S.G["max_turn_per_chord_rad"])
    kpos, kneg = float(max(kp.max(), 0.0)), float(min(kp.min(), 0.0))
    for d in shifts:
        if not lane_curvature_ok(kpos, kneg, d, limit):
            return False
        if not np.all(S.cg_patrol.ok(_lane_points(xy, th, d))):
            return False
    # 驻留：最坏的期望速度（下限）下，最内侧车道不得出现 20 s 内停留在 30 m 半径内
    v_low = S.M["speed_min_m_s"]
    inner = max(shifts, key=lambda d: d * (1.0 if kpos >= -kneg else -1.0)) if shifts else 0.0
    lane = _lane_points(xy, th, inner)
    kl = kp / np.maximum(np.abs(1.0 - kp * inner), 1e-9)
    if _polyline_dwell(S, lane, kl, v_low):
        return False
    return True


def _polyline_dwell(S, xy, kappa, v_cmd):
    """用冻结的驻留检测器（名义判据预筛选里的原样函数）检查一条折线按 v_cmd、曲率限速走完是否出现驻留。"""
    from ..nominal_checks import dwell as frozen_dwell
    seg = np.hypot(*np.diff(xy, axis=0).T)
    cap = np.minimum(v_cmd, np.sqrt(S.G["a_lat_m_s2"] / np.maximum(np.abs(kappa), 1e-12)))
    t = np.r_[0.0, np.cumsum(2.0 * seg / (cap[:-1] + cap[1:]))]
    frames = np.arange(0.0, t[-1], 0.1)
    s = np.r_[0.0, np.cumsum(seg)]
    sf = np.interp(frames, t, s)
    pts = np.stack([np.interp(sf, s, xy[:, 0]), np.interp(sf, s, xy[:, 1])], axis=1)
    return bool(frozen_dwell(pts, (frames * 1e6).astype(np.int64), np.ones(len(frames), bool))["detected"])


def _scale_alpha(S, center, radii, phi0, phi1, shifts):
    """把全部系数同乘 α∈[0,1]，取最大的可行 α（不假设单调；α=0 即固定圆，如实记录）。"""
    tried = []
    for a in ALPHA_SCAN:
        rho0, coef = _spline_from_radii(radii, a)
        ok = _ring_ok(S, center, rho0, coef, phi0, phi1, shifts)
        tried.append((a, bool(ok)))
        if ok:
            return rho0, coef, a, tried
    return None


def _center_candidates(S, rng, n):
    """圈心取目标 alert 区域内均匀分布的点（凸区域内任一点都是星形中心）。"""
    from ...scene.exact import bounding_box
    g = S.tgt.layers["alert"]
    x0, y0, x1, y1 = bounding_box(g)
    out = []
    while len(out) < n:
        p = np.array([rng.uniform(x0, x1), rng.uniform(y0, y1)])
        if signed_distance(g, p) <= 0.0:
            out.append(p)
    return out


def _time_for_length(sev, v0, length):
    """速度剖面（时间上的分段常数：v0，之后每个事件换一个速度）下走完 length 米所需的时间。"""
    ts = [0.0] + [float(t) for t in sev.times_s]
    vs = [float(v0)] + [float(v) for v in sev.speeds_m_s]
    for k in range(len(ts)):
        t_end = ts[k + 1] if k + 1 < len(ts) else math.inf
        seg = vs[k] * (t_end - ts[k])
        if length <= seg:
            return ts[k] + length / vs[k]
        length -= seg
    return math.inf


BUDGET_SLACK = 1.1       # 屏蔽估计里给样条超出内边界曲线的长度、曲率限速留的余量（只用来筛掉明显不可能的圈心）


def _inner_edge(comp, rs):
    """分量在每个方位行上的最小合法半径（行号 → 米）。"""
    return {row: float(rs[min(lo for lo, _ in runs)]) for row, runs in comp["rows"].items()}


def _budget_ok(S, center, comp, rs, need_rows, *, loop):
    """用该圈心下分量的内边界做名义总时长的粗下界（预算许可集合是否为空，第 3.6 节）：
    绕圈：圈数下限 × ∫ r_in dφ；折返：穿行次数下限 × 最短满足覆盖的弧。汇合段取各成员到圈心的距离减平均内半径。
    这是筛选圈心的廉价估计，不是证明；通过后仍由真实构造和修复核对。"""
    r_in = _inner_edge(comp, rs)
    dphi = 2.0 * math.pi / PHI_ROWS
    if loop:
        length = sum(r_in.values()) * dphi
        n_rows = len(r_in)
        lap_lo = float(S.ctx.params["monitoring"]["laps"][0])
        patrol = lap_lo * length
        rbar = length / (2.0 * math.pi)
    else:
        rows = sorted(r_in)
        best = math.inf
        for k in range(len(rows)):
            win = [(rows[k] + i) % PHI_ROWS for i in range(need_rows)]
            if all(w in r_in for w in win):
                best = min(best, sum(r_in[w] for w in win) * dphi)
        if not math.isfinite(best):
            return False
        t_min = float(min(S.ctx.params["monitoring"]["traversals"]))
        patrol = t_min * best
        rbar = float(np.mean(list(r_in.values())))
    transit = max(float(np.hypot(*(np.asarray(S.states[m].p[:2], float) - center))) - rbar for m in S.group.member_ids)
    total = max(transit, 0.0) + BUDGET_SLACK * patrol + S.M["retreat_clearance_m"]
    return _time_for_length(S.sev, S.v0, total) <= S.M["nominal_budget_s"]


def _warning_bbox(S):
    key = ("warning_bbox", S.target)
    if key not in S.ctx.extra:
        from ...scene.exact import bounding_box
        S.ctx.extra[key] = bounding_box(S.tgt.layers["warning"])
    return S.ctx.extra[key]


def _find_ring(S, slots, rng, prior_topology, sigma):
    shifts = sorted({d for _, d in slots.offsets.values()})
    ctx = S.ctx
    need_rows = int(math.ceil(S.criteria["min_azimuth_coverage_deg"] / 360.0 * PHI_ROWS))
    info = {"centers_tried": 0, "loop_feasible": 0, "retrace_feasible": 0, "loop_budget_rejected": 0,
            "retrace_budget_rejected": 0}
    for center in _center_candidates(S, rng, N_CENTERS):
        info["centers_tried"] += 1
        # 巡逻点都在目标预警圈内，半径超过圈心到预警外接框最远角的部分一定不可行，没必要扫
        wx0, wy0, wx1, wy1 = _warning_bbox(S)
        r_hi = float(max(np.hypot(wx - center[0], wy - center[1]) for wx in (wx0, wx1) for wy in (wy0, wy1)))
        rs = np.arange(R_STEP_M, r_hi + R_STEP_M, R_STEP_M)
        mask = _polar_mask(S, center, sigma, shifts, rs)
        comps = _components(mask)
        loops = [c for c in comps if c["wrapping"]]
        arcs = [c for c in comps if c["n_rows"] >= need_rows]
        n_loops, n_arcs = len(loops), len(arcs)
        loops = [c for c in loops if _budget_ok(S, center, c, rs, need_rows, loop=True)]
        arcs = [c for c in arcs if _budget_ok(S, center, c, rs, need_rows, loop=False)]
        info["loop_budget_rejected"] += n_loops - len(loops)
        info["retrace_budget_rejected"] += n_arcs - len(arcs)
        if loops:
            info["loop_feasible"] += 1
        if arcs:
            info["retrace_feasible"] += 1
        if not loops and not arcs:
            continue
        if loops and arcs:
            topo, forced = prior_topology, False
        elif loops:
            topo, forced = "loop", prior_topology != "loop"
        else:
            topo, forced = "retrace", prior_topology != "retrace"
        reason = None
        if forced:
            reason = "budget" if (n_loops > len(loops) or n_arcs > len(arcs)) else "geometry"
        return {"center": center, "mask_rs": rs, "comps": comps, "loops": loops, "arcs": arcs, "topology": topo,
                "forced": forced, "forced_reason": reason, "shifts": shifts, "sigma": sigma, "info": info,
                "need_rows": need_rows}
    if info["loop_budget_rejected"] or info["retrace_budget_rejected"]:
        return {"empty": True, "budget": True, "info": info}
    return {"empty": True, "info": info}


def _draw_loop(S, ring, rng):
    sizes = np.array([c["n_rows"] for c in ring["loops"]], float)
    sg = ring["sigma"]
    out = None
    for redraw in range(N_REDRAWS):
        K = int(rng.integers(int(S.M["spline_basis_min"]), int(S.M["spline_basis_max"]) + 1))
        comp = ring["loops"][int(rng.choice(len(ring["loops"]), p=sizes / sizes.sum()))]
        got = [_draw_radius(rng, comp, int(round(j * PHI_ROWS / K)) % PHI_ROWS, ring["mask_rs"], True)
               for j in range(K)]
        radii = np.array([g[0] for g in got])
        runs = tuple(g[1] for g in got)
        out = _scale_alpha(S, ring["center"], radii, 0.0, sg * 2 * np.pi, ring["shifts"])
        if out is not None:
            break
    if out is None:
        return None
    rho0, coef, alpha, tried = out
    laps = float(rng.uniform(*S.ctx.params["monitoring"]["laps"]))
    phase = float(rng.uniform(0.0, 2 * np.pi))
    return {"topology": "loop", "center_xy": tuple(map(float, ring["center"])), "rho0_m": rho0,
            "coefficients_m": coef, "phase_rad": phase, "direction": int(sg), "laps": laps, "K": K,
            "sampled_radii_m": tuple(map(float, radii)), "knot_runs": runs, "alpha": alpha, "alpha_tried": tried,
            "redraws": redraw}


def _draw_arc_once(S, ring, rng):
    arcs = ring["arcs"]
    w = np.array([c["n_rows"] for c in arcs], float)
    comp = arcs[int(rng.choice(len(arcs), p=w / w.sum()))]
    rows = sorted(comp["rows"])
    P = PHI_ROWS
    need = ring["need_rows"]
    if comp["wrapping"]:
        start = int(rng.integers(0, P))
        max_span = P - 2
    else:
        rs_set = set(rows)
        first = next(r for r in rows if (r - 1) % P not in rs_set)
        start = (first + int(rng.integers(0, len(rows) - need + 1))) % P
        max_span = len(rows) - ((start - first) % P)
    span = int(rng.integers(need, max(need, max_span) + 1))
    idx = [(start + k) % P for k in range(span)]
    if not all(i in comp["rows"] for i in idx):
        return None
    phi_a = 2 * np.pi * start / P
    phi_b = phi_a + 2 * np.pi * (span - 1) / P
    K = int(rng.integers(int(S.M["spline_basis_min"]), int(S.M["spline_basis_max"]) + 1))
    knots, kruns = [], []
    for j in range(K):
        row = int(round(j * P / K)) % P
        if row in idx:
            r, run = _draw_radius(rng, comp, row, ring["mask_rs"], True)
            knots.append(r)
            kruns.append(run)
        else:
            knots.append(None)
            kruns.append(None)
    inside = [j for j, v in enumerate(knots) if v is not None]
    if not inside:
        row = idx[len(idx) // 2]
        j = int(round(row * K / P)) % K
        knots[j], kruns[j] = _draw_radius(rng, comp, row, ring["mask_rs"], True)
        inside = [j]
    for j in range(K):
        if knots[j] is None:
            near = min(inside, key=lambda i: min((i - j) % K, (j - i) % K))
            knots[j], kruns[j] = knots[near], kruns[near]
    radii = np.array(knots, float)
    out = _scale_alpha(S, ring["center"], radii, phi_a, phi_b, ring["shifts"])
    if out is None:
        return None
    rho0, coef, alpha, tried = out
    trav = int(rng.choice(np.array(S.ctx.params["monitoring"]["traversals"], dtype=int)))
    return {"topology": "retrace", "center_xy": tuple(map(float, ring["center"])), "rho0_m": rho0,
            "coefficients_m": coef, "phi_a": float(phi_a), "phi_b": float(phi_b), "direction": int(ring["sigma"]),
            "traversals": trav, "arc_span_rad": float(phi_b - phi_a), "K": K, "alpha": alpha, "alpha_tried": tried,
            "sampled_radii_m": tuple(map(float, radii)), "knot_runs": tuple(kruns)}


def _draw_arc(S, ring, rng):
    for redraw in range(N_REDRAWS):
        out = _draw_arc_once(S, ring, rng)
        if out is not None:
            out["redraws"] = redraw
            return out
    return None


# ---------------------------------------------------------------- 掉头

def _turn_arcs(pos, h, R, side, angle):
    """从 (pos, h) 起向 side(+1 左 / −1 右) 转 angle 的圆弧图元与终点位姿。"""
    n = left_normal(np.array([math.cos(h), math.sin(h)]))
    c = np.asarray(pos, float) + side * R * n
    a0 = math.atan2(pos[1] - c[1], pos[0] - c[0])
    a1 = a0 + side * angle
    end = c + R * np.array([math.cos(a1), math.sin(a1)])
    return ("arc", tuple(c), float(R), float(a0), float(side * angle)), end, h + side * angle


def teardrop_primitives(pos, h, R, L, side):
    """L–直线–R–直线–L（side=+1 先向左；−1 镜像）：三圆弧转角 θ、−(π+2θ)、θ，
    θ = arccos(R/√(4R²+L²)) − arctan(L/(2R))，满足 2R cosθ − L sinθ = R，零位移、最终切向反向。"""
    th = math.acos(R / math.sqrt(4 * R * R + L * L)) - math.atan(L / (2 * R))
    prims = []
    p = np.asarray(pos, float)
    a1, p, hh = _turn_arcs(p, h, R, side, th)
    prims.append(a1)
    q = p + L * np.array([math.cos(hh), math.sin(hh)])
    prims.append(("line", tuple(p), tuple(q)))
    a2, p, hh = _turn_arcs(q, hh, R, -side, math.pi + 2 * th)
    prims.append(a2)
    q = p + L * np.array([math.cos(hh), math.sin(hh)])
    prims.append(("line", tuple(p), tuple(q)))
    a3, p, hh = _turn_arcs(q, hh, R, side, th)
    prims.append(a3)
    return prims


def _build_turn(S, spec, shifts, phi_e, dir_k, kind, side, R, rng, merge_choices):
    """在 pass 末端 φ_e 做一次掉头；返回 (图元列表, 下一 pass 的起始相位) 或 None。"""
    c, rho0, coef = spec["center"], spec["rho0"], spec["coef"]
    pos, h = _loop_pose(c, rho0, coef, phi_e, dir_k)
    if kind == "teardrop":
        prims = teardrop_primitives(pos, h, R, MIN_STRAIGHT_M, side)
        if _proxy_prims(S, prims, shifts, S.cg_patrol):
            return prims, phi_e
        return None
    if kind == "u":
        arc, end, h2 = _turn_arcs(pos, h, R, side, math.pi)
    else:
        arc, end, h2 = _turn_arcs(pos, h, R, side, 5.0 * math.pi / 6.0)
    if not _proxy_prims(S, [arc], shifts, S.cg_patrol):
        return None
    t0 = np.array([math.cos(h2), math.sin(h2)])
    rho_mean = max(float(rho0), 1.0)
    good = []
    for length in merge_choices:
        phi_m = phi_e - dir_k * length / rho_mean
        pm, hm = _loop_pose(c, rho0, coef, phi_m, -dir_k)
        t1 = np.array([math.cos(hm), math.sin(hm)])

        def corridor(xy, _s=shifts):
            ang = np.arctan2(np.gradient(xy[:, 1]), np.gradient(xy[:, 0]))
            return all(np.all(S.cg_patrol.ok(_lane_points(xy, ang, d))) for d in _s)

        bz = connect_poses(end, t0, pm, t1, corridor, rng, grid=5, lane_shifts=shifts)
        if bz is not None:
            good.append(([arc, bz], phi_m))
    if not good:
        return None
    return good[int(rng.integers(0, len(good)))]


def _draw_retrace_turns(S, spec, shifts, rng):
    """为 traversals 次单向穿行生成相邻两次之间的掉头。返回 (passes, turns, infos) 或 None。"""
    kinds = ["teardrop", "u", "oblique"]
    kmin = {"teardrop": S.M["turn_teardrop_min_m"], "u": S.M["turn_u_min_m"], "oblique": S.M["turn_oblique_min_m"]}
    phi_a, phi_b = spec["phi_a"], spec["phi_b"]
    ends = (phi_a, phi_b)
    cur_from, cur_to = (phi_a, phi_b) if spec["direction"] > 0 else (phi_b, phi_a)
    passes, turns, infos = [], [], []
    d_max = max((abs(d) for d in shifts), default=0.0)
    merge_choices = (30.0, 60.0, 120.0, 240.0, 480.0)
    for k in range(spec["traversals"]):
        passes.append((cur_from, cur_to))
        if k == spec["traversals"] - 1:
            break
        dir_k = 1.0 if cur_to > cur_from else -1.0
        # 掉头形状 × 侧向 共 6 种组合：按随机排列逐个核对，第一个可行者即为在可行组合中等概率的一个；
        # 然后只对它枚举从下界起连续可行的半径（半径等概率）。其余组合不再展开，省去无谓的几何检查。
        combos = [(kd, sd) for kd in kinds for sd in (+1, -1)]
        chosen = None
        tested = 0
        for ci in rng.permutation(len(combos)):
            kd, sd = combos[int(ci)]
            tested += 1
            R_lo = kmin[kd] + d_max
            ok_R = []
            for i in range(10):
                R = R_lo * (1.3 ** i)
                res = _build_turn(S, spec, shifts, cur_to, dir_k, kd, sd, R, rng, merge_choices)
                if res is None:
                    break
                ok_R.append((R, res))
            if ok_R:
                chosen = (kd, sd, ok_R)
                break
        if chosen is None:
            return None
        kd, sd, ok_R = chosen
        R, (prims, phi_next) = ok_R[int(rng.integers(0, len(ok_R)))]
        turns.append(tuple(prims))
        infos.append({"kind": kd, "side": sd, "radius_m": float(R), "min_lane_radius_m": float(R - d_max),
                      "combos_tested": tested, "radii_feasible": len(ok_R)})
        other_end = ends[0] if abs(cur_to - ends[1]) < 1e-9 else ends[1]
        cur_from, cur_to = phi_next, other_end
    return tuple(passes), tuple(turns), infos


# ---------------------------------------------------------------- 入圈直线、出圈直线、起点路由

def _line_lanes_ok(cg, C, u, s_lo, s_hi, shifts, lmax, extra=0.0):
    """沿 C + s·u（s∈[s_lo−lmax, s_hi+lmax]）的各车道偏移点是否都在保守可行集内。"""
    s = np.arange(s_lo - lmax, s_hi + lmax + 1.0, 1.0)
    n = left_normal(u)
    for d in shifts:
        pts = C[None] + s[:, None] * u[None] + d * n[None]
        if not np.all(cg.ok(pts, extra)):
            return False
    return True


def _depth_to_inside(S, X, direction, limit, shifts=(0.0,)):
    """沿 direction 从 X 起，第一次 signed ≤ −(band+1) 的距离；对每条车道偏移（垂直 direction 平移 d）
    分别求，取最大者；limit 内某条车道没有则 None。"""
    t = np.arange(0.0, limit, 1.0)
    n = left_normal(np.asarray(direction, float))
    worst = 0.0
    for d in shifts:
        sd = signed_distance(S.tgt.layers["warning"], (X + d * n)[None] + t[:, None] * np.asarray(direction)[None])
        hit = np.flatnonzero(sd <= -(S.band + 1.0))
        if not len(hit):
            return None
        worst = max(worst, float(t[hit[0]]))
    return worst


def _lane_cross_ok(S, C, u, D, slots):
    """每条车道自己的入圈交点到车道起点（槽位）至少 align_m，其间整段是同一条直线。"""
    n = left_normal(u)
    s = np.arange(0.0, D + 4000.0, 2.0)
    for l, d in slots.offsets.values():
        pts = (C + l * u + d * n)[None] + s[:, None] * u[None]
        sd = signed_distance(S.tgt.layers["warning"], pts)
        hit = np.flatnonzero(sd <= 0.0)
        if not len(hit) or s[hit[0]] < S.align:
            return False
    return True


def _corridor(S, shifts, cg):
    def ok(xy):
        ang = np.arctan2(np.gradient(xy[:, 1]), np.gradient(xy[:, 0]))
        return all(np.all(cg.ok(_lane_points(xy, ang, d))) for d in shifts)
    return ok


def _plan_ingress(S, slots, S0, rng, crng):
    shifts = sorted({d for _, d in slots.offsets.values()})
    lmax = slots.max_longitudinal_m
    foot = slots.footprint_m
    pts, w = _boundary_points(S)
    order = rng.choice(len(pts), size=min(len(pts), 4 * N_ENTRIES), replace=False, p=w)
    p_s, h_s = S0
    t0 = np.array([math.cos(h_s), math.sin(h_s)])
    Ds = np.arange(S.align, 401.0, 10.0)
    tried = 0
    for idx in order:
        if tried >= N_ENTRIES:
            break
        X = pts[idx]
        gap = float(np.hypot(*(p_s - X)))
        if gap < 1.0:
            continue
        u = unit(p_s - X)
        t_min = _depth_to_inside(S, X, u, gap, shifts)
        if t_min is None or t_min > gap - 5.0:
            continue
        tried += 1
        feas = []
        for D in Ds:
            C = X - D * u
            if (S.cg_collect_band.ok(C) and S.cg_collect_phys.ok(C, foot) and _lane_cross_ok(S, C, u, D, slots)
                    and _line_lanes_ok(S.cg_route, C, u, 0.0, D + t_min, shifts, lmax)):
                feas.append(float(D))
        if not feas:
            continue
        D = feas[int(rng.integers(0, len(feas)))]
        C = X - D * u
        cand = [t_min + e for e in (0.0, 20.0, 50.0, 100.0, 200.0) if t_min + e <= gap * 0.8]
        crng.shuffle(cand)
        for t_in in cand:
            Q = X + t_in * u
            bz = connect_poses(Q, u, p_s, t0, _corridor(S, shifts, S.cg_inner), crng, lane_shifts=shifts)
            if bz is None:
                continue
            return {"C": C, "u": u, "X": X, "D": D, "Q": Q, "t_in": float(t_in), "depth_min": t_min,
                    "prims": (("line", tuple(C), tuple(Q)), bz), "tried": tried}
    return None


def _plan_egress(S, slots, E0, rng, crng):
    shifts = sorted({d for _, d in slots.offsets.values()})
    lmax = slots.max_longitudinal_m
    foot = slots.footprint_m
    pts, w = _boundary_points(S)
    order = rng.choice(len(pts), size=min(len(pts), 4 * N_ENTRIES), replace=False, p=w)
    p_e, h_e = E0
    th = np.array([math.cos(h_e), math.sin(h_e)])
    De = np.arange(S.M["retreat_clearance_m"], 3001.0, 25.0)
    tried = 0
    for idx in order:
        if tried >= N_ENTRIES:
            break
        X = pts[idx]
        gap = float(np.hypot(*(p_e - X)))
        if gap < 1.0:
            continue
        u = unit(X - p_e)
        t_min = _depth_to_inside(S, X, -u, gap, shifts)
        if t_min is None or t_min > gap - 5.0:
            continue
        tried += 1
        cand = [t_min + e for e in (0.0, 20.0, 50.0, 100.0, 200.0) if t_min + e <= gap * 0.8]
        crng.shuffle(cand)
        for t_out in cand:
            Q = X - t_out * u
            bz = connect_poses(p_e, th, Q, u, _corridor(S, shifts, S.cg_inner), crng, lane_shifts=shifts)
            if bz is None:
                continue
            feas = []
            for D in De:
                T = X + D * u
                if S.cg_term.ok(T, foot) and _line_lanes_ok(S.cg_route, Q, u, 0.0, t_out + D, shifts, lmax):
                    feas.append(float(D))
            if not feas:
                continue
            D = feas[int(rng.integers(0, len(feas)))]
            T = X + D * u
            return {"X": X, "u": u, "Q": Q, "T": T, "D": D, "t_out": float(t_out), "depth_min": t_min,
                    "prims": (bz, ("line", tuple(Q), tuple(T))), "tried": tried}
    return None


def _inward_start(S, planner, p0):
    """起点距地图边只有几十米时，骨架规划器（world 内缩 35 + Δ）可能认为起点不自由：
    沿朝向地图中心的方向直线走到第一个自由点，这一段是直线，不改变起点。"""
    x0, y0, x1, y1 = S.ctx.bounds
    d = unit(np.array([(x0 + x1) / 2.0, (y0 + y1) / 2.0]) - p0)
    for s in np.arange(0.0, 400.0, 5.0):
        q = p0 + s * d
        if planner.free([float(q[0]), float(q[1])]):
            return q
    return None


def _count(S, name):
    S.stats[name] = S.stats.get(name, 0) + 1


def _route(S, p0, slot, u, rng):
    """起点 → 槽位：折线 + 圆角（直线上才允许穿越边界）。骨架余量 Δ 给圆角向内切入留余地。"""
    G, ctx = S.G, S.ctx
    r_floor = ctx.params["curve_spacing_m"] / G["max_turn_per_chord_rad"] * 1.05
    r_pref = S.v_cap ** 2 / G["a_lat_m_s2"]
    dist = float(np.hypot(*(slot - p0)))
    for delta in (None, 10.0, 30.0, 80.0):
        tag = "direct" if delta is None else f"skel{int(delta)}"
        # 进场直线（沿 −u 向后）在带 Δ 余量的保守集内能延伸多远
        back = np.arange(1.0, min(dist, 3000.0), 1.0)
        okb = S.cg_route.ok(slot[None] - back[:, None] * u[None], delta or 0.0)
        bad = np.flatnonzero(~okb)
        g_max = float(back[bad[0] - 1]) if len(bad) and bad[0] > 0 else (float(back[-1]) if not len(bad) else 0.0)
        if g_max < 2.0 * MIN_STRAIGHT_M:
            _count(S, tag + ":approach_blocked")
            continue
        for _ in range(6):
            g = float(rng.uniform(2.0 * MIN_STRAIGHT_M, g_max))
            A = slot - g * u
            if float(np.hypot(*(A - p0))) < 1.0:
                _count(S, tag + ":A_too_close")
                continue
            lead = []
            if delta is None:
                mids = []
            else:
                pl = skeleton_planner(ctx, delta)
                q = _inward_start(S, pl, p0)
                if q is None:
                    _count(S, tag + ":start_not_free")
                    break
                path = pl.path(q, A)
                if path is None:
                    _count(S, tag + ":no_skeleton_path")
                    continue
                if float(np.hypot(*(q - p0))) > 1e-9:
                    lead = [q]
                mids = [np.asarray(v, float) for v in path[1:-1]]
            pts = [p0] + lead + mids + [A, slot]
            try:
                radii = []
                for k in range(1, len(pts) - 1):
                    seg_in = float(np.hypot(*(pts[k] - pts[k - 1])))
                    seg_out = float(np.hypot(*(pts[k + 1] - pts[k])))
                    avail = 0.5 * (min(seg_in, seg_out) - MIN_STRAIGHT_M)
                    b = corner_radius_bounds(pts, k, delta, avail, r_floor=r_floor)
                    if b is None:
                        radii.append(None)
                        continue
                    r_hi = b[0]
                    if r_hi < r_floor:
                        raise ValueError("圆角放不下")
                    radii.append(float(rng.uniform(min(r_pref, r_hi), r_hi)))
                prims = fillet_route(pts, radii)
            except ValueError:
                _count(S, tag + ":fillet_fit")
                continue
            if _proxy_prims(S, prims, [0.0], S.cg_route, arcs_avoid_bands=True):
                return prims, delta
            _count(S, tag + ":proxy")
    return None, None


def _plan_starts(S, slots, C, u, rng):
    n_u = left_normal(u)
    out, meta = {}, {}
    for m in slots.order:
        l, d = slots.offsets[m]
        slot = C + l * u + d * n_u
        p0 = np.asarray(S.states[m].p[:2], float)
        prims, delta = _route(S, p0, slot, u, rng)
        if prims is None:
            return None, m
        out[m] = prims
        meta[m] = {"skeleton_delta_m": delta, "primitives": len(prims)}
    return out, meta


# ---------------------------------------------------------------- 组装

def _stage_fail(stage, reason, P=None, key=None, extra=None):
    return _plan(_reject(reason, stage, {"stage": stage, **(extra or {})}), proposal=P,
                 business_key=None if key is None else _key_dict(key))


def _patrol_poses(spec, passes=None):
    c = np.asarray(spec["center_xy"], float)
    rho0, coef = spec["rho0_m"], spec["coefficients_m"]
    if spec["topology"] == "loop":
        d = 1.0 if spec["direction"] >= 0 else -1.0
        p0 = float(spec["phase_rad"])
        p1 = p0 + d * float(spec["laps"]) * 2.0 * math.pi
        return _loop_pose(c, rho0, coef, p0, d), _loop_pose(c, rho0, coef, p1, d)
    first, last = passes[0], passes[-1]
    return (_loop_pose(c, rho0, coef, first[0], 1.0 if first[1] > first[0] else -1.0),
            _loop_pose(c, rho0, coef, last[1], 1.0 if last[1] > last[0] else -1.0))




# ---------------------------------------------------------------- 形状确定之后的构造链与预算修复

def _is_budget(plan):
    return plan.failure is not None and plan.failure.feasible_set == "duration_budget"


class _Build:
    """一个 attempt 内、形状确定之后的构造链：转弯 → 入圈 → 起点 → 出圈 → 候选检查。
    同一个对象可以对"形状略有不同"的多个 spec 重复构造（预算修复），每次用各自的随机流。"""

    def __init__(self, S, ctx, group, task, states, key, slots, ring, repairs, steps_log, prior_topology, sigma):
        self.S, self.ctx, self.group, self.task, self.states, self.key = S, ctx, group, task, states, key
        self.slots, self.ring, self.repairs, self.steps_log = slots, ring, repairs, steps_log
        self.prior_topology, self.sigma = prior_topology, sigma
        self.sev = S.sev

    def prepare(self, spec, rng, crng):
        S, slots, key = self.S, self.slots, self.key
        spec = dict(spec)
        passes = turn_info = None
        if spec["topology"] == "retrace":
            pspec = {"center": np.asarray(spec["center_xy"], float), "rho0": spec["rho0_m"],
                     "coef": spec["coefficients_m"], "phi_a": spec["phi_a"], "phi_b": spec["phi_b"],
                     "direction": spec["direction"], "traversals": spec["traversals"]}
            got = _draw_retrace_turns(S, pspec, self.ring["shifts"], crng)
            if got is None:
                return None, _stage_fail("turns", "折返端点没有可放置的掉头", None, key,
                                         {"traversals": spec["traversals"]})
            passes, turns, turn_info = got
            spec["passes"], spec["turns"] = passes, turns
        S0, _ = _patrol_poses(spec, passes)
        ing = _plan_ingress(S, slots, S0, rng, crng)
        if ing is None:
            return None, _stage_fail("ingress", "没有可用的入圈直线与连接", None, key)
        starts, meta = _plan_starts(S, slots, ing["C"], ing["u"], crng)
        if starts is None:
            return None, _stage_fail("start_route", f"成员 {meta} 没有可用的起点路由", None, key,
                                     {"route_stats": dict(S.stats)})
        return {"spec": spec, "passes": passes, "turn_info": turn_info, "ing": ing, "starts": starts, "meta": meta}, None

    def assemble(self, prep, spec_now, rng, crng, extra_repairs=(), duration_only=False):
        S, slots, key, ring = self.S, self.slots, self.key, self.ring
        _, E0 = _patrol_poses(spec_now, prep["passes"])
        eg = _plan_egress(S, slots, E0, rng, crng)
        if eg is None:
            return None, _stage_fail("egress", "没有可用的出圈直线与终点", None, key)
        ing = prep["ing"]
        P = {**spec_now, "collection_xy": tuple(map(float, ing["C"])), "entry_point_xy": tuple(map(float, ing["X"])),
             "exit_point_xy": tuple(map(float, eg["X"])), "terminal_xy": tuple(map(float, eg["T"])),
             "member_slot_order": slots.order, "formation": slots.realized,
             "lateral_step_m": slots.lateral_step_m if slots.realized == "echelon" else None,
             "start_connections": prep["starts"], "reference_ingress": ing["prims"], "reference_egress": eg["prims"],
             "speed_events": {"times_s": self.sev.times_s, "speeds_m_s": self.sev.speeds_m_s},
             "repairs": tuple(self.repairs) + tuple(extra_repairs),
             "topology_info": {"prior_draw": self.prior_topology, "forced": ring["forced"],
                               "forced_reason": ring.get("forced_reason"), "ring": ring["info"],
                               "formation_steps": self.steps_log, "turns": prep["turn_info"], "sigma": self.sigma,
                               "entry": {k: ing[k] for k in ("D", "t_in", "depth_min", "tried")},
                               "exit": {k: eg[k] for k in ("D", "t_out", "depth_min", "tried")},
                               "starts": prep["meta"]}}
        return P, build_candidate(self.ctx, self.group, self.task, self.states, (), key, P, duration_only=duration_only)


def _shift_spec(S, ring, spec, delta):
    """预算修复的唯一自由度：把各结点半径同时向各自合法径向区间的内端移动 delta（并夹在区间内）。
    这是"线性长度约束 + 区间箱约束"下离原抽样欧氏距离最近的点（各结点对长度的权重相同）；
    再按第 3.3 节求最大可行 α。返回新 spec，或 None（该偏移下没有任何可行 α，含 α=0）。"""
    radii = np.asarray(spec["sampled_radii_m"], float)
    new = np.array([min(max(r - delta, lo), hi) for r, (lo, hi) in zip(radii, spec["knot_runs"])])
    if spec["topology"] == "loop":
        p0, p1 = 0.0, ring["sigma"] * 2 * np.pi
    else:
        p0, p1 = spec["phi_a"], spec["phi_b"]
    out = _scale_alpha(S, ring["center"], new, p0, p1, ring["shifts"])
    if out is None:
        return None
    rho0, coef, alpha, tried = out
    return {**spec, "rho0_m": rho0, "coefficients_m": coef, "alpha": alpha, "alpha_tried": tried,
            "repaired_radii_m": tuple(map(float, new))}


REPAIR_ITERS = 4
BUDGET_TARGET = 0.97       # 修复目标：名义总时长落在预算的 97% 以内，吸收线性模型的误差


def _delta_for_mean(radii, runs, target_mean):
    """各结点半径同时内移 delta（夹在各自合法区间内）后均值等于 target_mean 的最小 delta；
    不可达时返回能达到的最大 delta。均值对 delta 单调不增，所以二分是严格的（不涉及随机构造）。"""
    r = np.asarray(radii, float)
    lo = np.array([a for a, _ in runs])
    hi = np.array([b for _, b in runs])

    def mean_at(d):
        return float(np.mean(np.clip(r - d, lo, hi)))

    if mean_at(0.0) <= target_mean:
        return 0.0
    d_hi = float(np.max(r - lo))
    if mean_at(d_hi) > target_mean:
        return d_hi
    a, b = 0.0, d_hi
    for _ in range(60):
        mid = 0.5 * (a + b)
        if mean_at(mid) > target_mean:
            a = mid
        else:
            b = mid
    return b


def _repair_budget(B, ring, spec, make, rng, first_duration_s, first_patrol_s):
    """名义总时长在允许的最小圈数/穿行次数下仍超 1800 s：在已求出的可行集合内做局部修复（第 3.9 节）。

    时间模型：总时长 = 与形状无关的汇合/撤离部分 + 巡逻部分；巡逻部分近似正比于巡逻路径长度。需要的缩短比例
    frac = (D − 0.97 预算)/巡逻用时。折返先缩短弧跨度（不低于覆盖下限），其余由各结点半径同时向各自合法区间内端
    移动补足（"线性长度约束 + 区间箱约束"下离原抽样欧氏距离最近的点），再求最大可行 α。每一轮只用 duration_only
    的廉价构造核对并更新 D 与巡逻用时，随机流固定为同一对种子，所以不同轮之间的差异只来自几何。
    返回 (plan, 记录)。plan 为失败计划表示该 attempt 失败（原因保留）。"""
    S = B.S
    budget = float(S.M["nominal_budget_s"])
    target = BUDGET_TARGET * budget
    seeds = (int(rng.integers(0, 2 ** 62)), int(rng.integers(0, 2 ** 62)))
    radii0 = np.asarray(spec["sampled_radii_m"], float)
    runs = spec["knot_runs"]
    d_cap = float(np.max(radii0 - np.array([a for a, _ in runs])))
    retrace = spec["topology"] == "retrace"
    span0 = (spec["phi_b"] - spec["phi_a"]) if retrace else None
    span_min = 2.0 * math.pi * (ring["need_rows"] - 1) / PHI_ROWS if retrace else None
    D, Tp = float(first_duration_s), float(first_patrol_s)
    cur_mean = float(np.mean(radii0))
    span = span0
    log = [{"step": "start", "duration_s": D, "patrol_s": Tp}]

    def fail(reason, stage):
        return _stage_fail(stage, reason, None, B.key, {"repair_log": log, "max_shift_m": d_cap})

    best = None
    for it in range(REPAIR_ITERS):
        frac = min(max((D - target) / max(Tp, 1.0), 0.0), 0.95)
        keep = 1.0 - frac
        if retrace and span > span_min + 1e-9:
            new_span = max(span_min, span * keep)
            keep = keep / (new_span / span)         # 弧跨度已承担的部分之外，半径还要承担的比例
            span = new_span
        goal_mean = cur_mean * min(keep, 1.0)
        base = {**spec, "phi_b": spec["phi_a"] + span, "arc_span_rad": span} if retrace else spec
        delta = _delta_for_mean(radii0, runs, goal_mean)
        sp = None
        for back in (1.0, 0.8, 0.6, 0.4, 0.2, 0.0):
            sp = _shift_spec(S, ring, base, delta * back)
            if sp is not None:
                delta *= back
                break
        if sp is None:
            log.append({"step": it, "span_rad": span, "result": "no_feasible_alpha"})
            return fail("半径内移后在任何回退量下都没有可行的 α", "budget_repair_shape"), log
        prep, plan = make(sp, seeds, True, ())
        if plan.failure is None:
            kind, D_new, Tp_new = "ok", float(plan.nominal_duration_s), None
        elif _is_budget(plan):
            w = plan.failure.witness
            kind, D_new = "over", float(w["duration_s"])
            Tp_new = float(np.mean(list(w["patrol_time_s"].values()))) if w.get("patrol_time_s") else Tp
        else:
            log.append({"step": it, "span_rad": span, "delta_m": delta, "result": "other",
                        "stage": plan.failure.feasible_set})
            return plan, log
        log.append({"step": it, "span_rad": span, "delta_m": delta, "alpha": sp["alpha"], "duration_s": D_new,
                    "result": kind})
        if kind == "ok":
            best = (sp, delta, D_new)
            break
        if D_new >= D - 1e-6 and delta >= d_cap - 1e-9 and (not retrace or span <= span_min + 1e-9):
            break                                      # 两个自由度都到了尽头
        D, Tp = D_new, Tp_new
        cur_mean = float(np.mean(sp["repaired_radii_m"]))
    if best is None:
        return fail(f"局部修复后名义总时长仍为 {D:.1f} s > {budget} s", "duration_budget"), log
    sp, delta, D_ok = best
    rec = ({"kind": "radius_shift_budget", "delta_m": delta, "max_shift_m": d_cap, "alpha": sp["alpha"],
            "span_rad": span, "span_original_rad": span0, "duration_s": D_ok, "log": log},)
    prep, plan = make(sp, seeds, False, rec)
    return plan, log


def _finish_loop(B, ring, spec, rng, crng):
    S, ctx = B.S, B.ctx
    lap_lo, lap_hi = (float(x) for x in ctx.params["monitoring"]["laps"])
    drawn = float(spec["laps"])

    def make(sp, seeds, duration_only, extra):
        r1, r2 = (np.random.default_rng(x) for x in seeds)
        prep, fail = B.prepare(sp, r1, r2)
        if fail is not None:
            return None, fail
        _, plan = B.assemble(prep, {**prep["spec"], "laps": lap_lo}, r1, r2, extra_repairs=extra,
                             duration_only=duration_only)
        return prep, plan

    prep, fail = B.prepare(spec, rng, crng)
    if fail is not None:
        return fail
    _, plan = B.assemble(prep, {**prep["spec"], "laps": lap_lo}, rng, crng)
    if plan.failure is not None:
        if not _is_budget(plan):
            return plan
        w = plan.failure.witness
        got, _ = _repair_budget(B, ring, spec, make, rng, float(w["duration_s"]),
                                float(np.mean(list(w["patrol_time_s"].values()))))
        return got          # 修复目标是预算的 97%，圈数停在下限；修复记录已在 plan.repairs 里
    budget = S.M["nominal_budget_s"]
    per_lap = float(np.mean(list(plan.witnesses["patrol_time_s"].values()))) / lap_lo
    slack = budget - plan.nominal_duration_s
    cap = min(lap_hi, lap_lo + max(slack, 0.0) / per_lap * 0.98)
    laps = float(rng.uniform(lap_lo, cap)) if cap > lap_lo else lap_lo
    if laps <= lap_lo + 1e-9:
        return plan
    final_spec = {**prep["spec"], "laps": laps}
    carried = tuple(plan.repairs[len(B.repairs):])
    _, plan2 = B.assemble(prep, final_spec, rng, crng, extra_repairs=carried + (
        {"kind": "laps_budget_cap", "drawn": drawn, "cap": cap, "used": laps},))
    if plan2.failure is None:
        return plan2
    return replace_repairs(plan, ({"kind": "laps_fallback_to_min", "tried": laps, "reason": plan2.failure.feasible_set},))


def _finish_retrace(B, ring, spec, rng, crng):
    S, ctx = B.S, B.ctx
    trav_all = sorted(int(t) for t in ctx.params["monitoring"]["traversals"])
    budget = S.M["nominal_budget_s"]

    def make_t(t):
        def make(sp, seeds, duration_only, extra):
            r1, r2 = (np.random.default_rng(x) for x in seeds)
            prep, fail = B.prepare({**sp, "traversals": t}, r1, r2)
            if fail is not None:
                return None, fail
            _, plan = B.assemble(prep, prep["spec"], r1, r2, extra_repairs=extra, duration_only=duration_only)
            return prep, plan
        return make

    t_drawn = int(spec["traversals"])
    prep, fail = B.prepare(spec, rng, crng)
    if fail is not None:
        return fail
    _, plan = B.assemble(prep, prep["spec"], rng, crng)
    if plan.failure is None or not _is_budget(plan):
        return plan
    # 穿行次数：{2,3,4} 与预算许可集合相交后均匀取（许可集合由"每次穿行用时近似相同"的线性估计给出，随后用真实构造核对）
    D0 = float(plan.failure.witness["duration_s"])
    t_pass = float(np.mean(list(plan.failure.witness["patrol_time_s"].values()))) / max(t_drawn, 1)
    allowed = [t for t in trav_all if t != t_drawn and D0 - (t_drawn - t) * t_pass <= budget]
    while allowed:
        t = int(rng.choice(np.array(allowed)))
        seeds = (int(rng.integers(0, 2 ** 62)), int(rng.integers(0, 2 ** 62)))
        rec = ({"kind": "traversals_budget_cap", "drawn": t_drawn, "used": t, "allowed_estimate": list(allowed)},)
        _, plan_t = make_t(t)(spec, seeds, False, rec)
        if plan_t.failure is None or not _is_budget(plan_t):
            return plan_t
        allowed = [a for a in allowed if a < t]
    t_min = trav_all[0]
    d_start = D0 - (t_drawn - t_min) * t_pass if t_min != t_drawn else D0
    got, _ = _repair_budget(B, ring, spec, make_t(t_min), rng, d_start, t_pass * t_min)
    return got


RETREAT_STAGES = frozenset({"turns", "ingress", "start_route", "egress", "separation", "patrol_shape",
                            "budget_repair_shape", "boundary_crossing"})


def _build_with_ring(S, ctx, group, task, states, key, slots, ring, used, b, steps_log, prior_topology, sigma, rng, crng):
    """给定队形与已找到的环带，抽形状并完成构造；返回 SegmentPlan（失败时 failure 非空）。"""
    repairs = []
    if slots.realized != slots.start:
        repairs.append({"kind": "formation_retreat", "from": slots.start, "to": slots.realized,
                        "forced_by": [x.get("downstream_failure") for x in steps_log if x.get("downstream_failure")]})
    if used is not None and used < b - 1e-9:
        repairs.append({"kind": "echelon_lateral_step", "from_m": b, "to_m": used})
    spec = _draw_loop(S, ring, rng) if ring["topology"] == "loop" else _draw_arc(S, ring, rng)
    if spec is None:
        return _stage_fail("patrol_shape", "可行带内抽到的形状在任何 α（含 0）下都不满足精确余量", None, key,
                           {"topology": ring["topology"]})
    if spec["alpha"] < 1.0:
        repairs.append({"kind": "alpha_scaling", "alpha": spec["alpha"], "tried": spec["alpha_tried"]})
    B = _Build(S, ctx, group, task, states, key, slots, ring, repairs, steps_log, prior_topology, sigma)
    if spec["topology"] == "loop":
        return _finish_loop(B, ring, spec, rng, crng)
    return _finish_retrace(B, ring, spec, rng, crng)


def propose_and_build(ctx, group, task, states, key):
    """一次随机构造（一个 attempt）：队形链 → 极坐标可行带 → 形态 → 入圈/出圈 → 起点路由 → 速度 → 候选检查。
    队形退让（abreast → echelon → column；echelon → column）既发生在环带容不下该队形时，也发生在该队形的
    掉头、入圈、起点路由、间距等几何构造失败时（第 3.4 节"失败 → 下一队形"）；预算超限不触发退让。"""
    S = _Setup(ctx, group, task, states, key)
    rng, crng = S.rng("shape"), S.rng("connect")
    fam = ctx.family
    full_p = ctx.params["monitoring"]["full_probability"]
    prior_topology = "loop" if float(rng.random()) < full_p else "retrace"
    sigma = 1 if float(rng.random()) < 0.5 else -1
    chain = retreat_chain(mapped_start(group.formation_prior))
    b = float(fam.lateral_spacing_m)
    fkey = RngKey(key.family_id, key.draw, "formation", mission=key.mission, branch=key.branch, group=key.group,
                  segment=key.segment, attempt=key.attempt)
    order = None
    steps_log = []
    last = None
    for name in chain:
        steps = [None] if name != "echelon" else [b] + [b * f for f in (0.75, 0.5, 0.33)] + [MIN_LATERAL_STEP_M]
        steps = [s for s in steps if s is None or s >= MIN_LATERAL_STEP_M - 1e-9]
        for st in steps:
            slots = formation_slots(group, fam, fkey, formation=name, lateral_step_m=st, order=order)
            order = slots.order
            r = _find_ring(S, slots, rng, prior_topology, sigma)
            steps_log.append({"formation": name, "lateral_step_m": st, "found": "empty" not in r, "info": r["info"],
                              "budget": bool(r.get("budget"))})
            if "empty" in r:
                continue
            plan = _build_with_ring(S, ctx, group, task, states, key, slots, r, st, b, steps_log, prior_topology, sigma,
                                    rng, crng)
            if plan.failure is None:
                return plan
            last = plan
            stage = plan.failure.feasible_set
            steps_log[-1]["downstream_failure"] = str(stage)
            if stage not in RETREAT_STAGES:
                return plan
            break               # 该队形的几何构造失败：直接退到链上的下一个队形，不再逐级缩小横向步长
    if last is not None:
        return last
    stage = "budget_region" if steps_log and all(x.get("budget") for x in steps_log) else "patrol_region"
    text = ("所有队形下，满足几何条件的环/弧都因名义总时长下界超过预算而被排除" if stage == "budget_region"
            else "所有队形下目标环带都没有满足条件的环/弧")
    return _stage_fail(stage, text, None, key, {"formations": steps_log})


def replace_repairs(plan, extra):
    from dataclasses import replace
    return replace(plan, repairs=tuple(plan.repairs) + tuple(extra))
