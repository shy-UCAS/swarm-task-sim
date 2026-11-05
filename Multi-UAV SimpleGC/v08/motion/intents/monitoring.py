"""监视单段：具体构造与候选检查（V8-12 第 3 部分；指令 3.3–3.8）。

build_candidate 不重抽任何已给提案：先验抽样在外层完成（plan.py）。给定完整提案，它做确定性的构造：
参考路径（汇合点 → 入圈直线 → 巡逻 → 出圈直线 → 终点）→ 队形槽位 → 成员车道 + 各自的起点连接 →
速度剖面 → 释放延迟 → 逐成员精确几何、边界穿越与终点撤离。任一检查不过，返回带 Failure 的
SegmentPlan（candidate_rejected，保留原始数值见证），不放宽任何余量。

V8-13（指令 4.1、决定 50）：名义总时长只记录不拒绝；连续时间间距与名义重访/驻留/圈层筛查不再拒绝骨架
（间距与物理约束交给联合优化，名义判据移到优化后的硬检查）；速度事件按真实参考曲线的名义用时上界生成，
不再按 1800 s 截断；队形只由走廊宽度确定（skeleton.width_then_build），下游失败不退让；一个 attempt 只抽
一套形状、圈数与穿行次数按原抽样一次构造。

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
import time
from dataclasses import replace

import numpy as np

from ...config import load_config
from ...contract.monitoring import Failure, MemberPlan, SegmentPlan
from ...scene.exact import polyline_clearance, signed_distance
from ...scene.field import Clearance
from ...sim.guidance import make_curve, nominal_time, speed_profile
from ...sim.kernel import member_config
from ...sim.types import SimContractError
from ..connect import crossing_analysis
from ..formation import derive_members, formation_slots, make_reference, retreat_chain
from ..nominal import member_nominal, release_us, sample_nominal
from ..nominal_checks import screen_member
from ..path import PathError, periodic_radius_derivs, sample_primitives
from ..skeleton import reference_guidance, width_then_build
from ..speed import draw_speed_events, map_speed_events
from ..monitoring_band import (arc_certificate, build_band_query, construct_band,  # noqa: E402  V8-14
                               logit_from_quantiles)
from ..monitoring_turn import (TurnSetup, choose_joint_turn, collapse_length_m, column_offsets,  # V8-14
                               derive_deforming_members, sample_joint_turn)

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

def build_reference_parts(P, ext_m, spacing):
    """build_reference 加上各图元在采样上的区间与巡逻首图元下标（V8-14：掉头收拢/核心/接回/展开的参考站点）。"""
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
    return ref, {k: int(v) for k, v in marks.items()}, {"intervals": iv, "patrol_first": h + n_i}


def build_reference(P, ext_m, spacing):
    ref, marks, _ = build_reference_parts(P, ext_m, spacing)
    return ref, marks


def turn_schedule(P, ref, pinfo):
    """V8-14：每次掉头的参考站点 s_A（收拢起点）、s_B（核心起点）、s_D（展开起点）、s_E（接回点）与收拢长度 L。
    旧提案（无 turn_parts）返回空表：成员按常数槽位派生。"""
    if P.get("topology") != "retrace" or not P.get("turn_parts"):
        return []
    iv = pinfo["intervals"]
    idx = pinfo["patrol_first"]
    out = []
    n_pass = len(P["passes"])
    for k in range(n_pass):
        idx += 1
        if k == n_pass - 1:
            break
        pt = P["turn_parts"][k]
        n_tot = pt["collapse"] + pt["core"] + pt["connector"] + pt["expand"]
        first = idx
        s_A = float(ref.s[iv[first][0]])
        s_B = float(ref.s[iv[first + pt["collapse"]][0]])
        s_E = float(ref.s[iv[first + n_tot - 1][1]])
        s_D = float(ref.s[iv[first + n_tot - 1][0]]) if pt["expand"] else s_E
        out.append({"s_A": s_A, "s_B": s_B, "s_D": s_D, "s_E": s_E, "L": float(P["turn_L_m"])})
        idx += n_tot
    return out


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


def build_candidate(ctx, group, task, states, occupied, key, proposal):
    """给定完整提案，确定性地构造一次完整骨架。提案未显式给 speed_events 时，按真实参考曲线（汇合→终点）
    在恒定最小指令速度下的名义用时上界 T_upper 一次生成速度事件（draw_speed_events 原接口），再顺序映射。"""
    P = proposal
    cfg_m = load_config("monitoring").values
    G = load_config("guidance").values
    G_ref_cfg = reference_guidance()          # V8-13b 裁定 2.5：名义时间的加速度参数取 0.9 倍
    G_ref = G_ref_cfg.values
    spacing = ctx.params["curve_spacing_m"]
    target = task.target_id
    cons = monitoring_constraints(ctx, target)
    base_fail = dict(proposal=P, business_key=_key_dict(key))
    try:
        slots = formation_slots(group, ctx.family, key, formation=P.get("formation"),
                                lateral_step_m=P.get("lateral_step_m"), order=P.get("member_slot_order"))
        ext = slots.max_longitudinal_m
        ref, mark_idx, pinfo = build_reference_parts(P, 0.0 if ext == 0.0 else ext + 1.0, spacing)
        s_c, s_t = ref.marks["collect"], ref.marks["terminal"]
        # V8-14 指令 3.3：变队形成员（收拢/单车道/展开），对应表贯穿速度事件、巡逻时间、掉头区间与成员映射
        schedule = turn_schedule(P, ref, pinfo)
        lanes, scheds, _l_star = derive_deforming_members(
            ref, slots, schedule, (s_c, s_t), spacing_m=spacing,
            marks=(ref.marks["patrol_start"], ref.marks["patrol_end"]))
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

    # 速度剖面：T_upper = 恒定最小指令速度（冻结 4 m/s）、v0=v_end=0 的名义用时；4–10 m/s 事件逐点不低于该剖面，
    # 故 T_upper 是有限的名义用时上界，只作事件时域，不作拒绝阈值。
    v0 = float(group.speed_profile.initial_speed_m_s)
    try:
        ref_curve = make_curve(ref.xy[mark_idx["collect"]:mark_idx["terminal"] + 1],
                               max_chord_m=G["max_chord_m"], max_turn_rad=G["max_turn_per_chord_rad"])
    except SimContractError as exc:
        return _plan(_reject(f"参考曲线不满足引导接口：{exc}", "reference/speed", {"error": str(exc)}), **base_fail)
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
            return _plan(_reject(f"参考曲线不满足引导接口：{exc}", "reference/speed", {"error": str(exc)}), **base_fail)
        breaks_ref = smap.breaks
        speed_info.update(errors_s=smap.errors_s, dropped=smap.dropped)
    breaks = {}
    for m in slots.order:
        lane = lanes[m]
        lane_cum = np.r_[0.0, np.cumsum(np.hypot(*np.diff(lane.xy, axis=0).T))]
        base_s = cum[m][coll_idx[m]]
        out = [(0.0, v0)]
        for s_rel, v in breaks_ref[1:]:
            s_member = base_s + float(np.interp(float(scheds[m].q(s_c + s_rel)), lane.s_ref, lane_cum))
            if s_member > out[-1][0] + 1e-9:
                out.append((s_member, float(v)))
            else:
                out[-1] = (out[-1][0], float(v))
        breaks[m] = tuple(out)

    # 释放延迟（同时拿到各成员的名义运动，避免对同一条曲线重复做 make_curve / speed_profile）
    try:
        delays, travel_to_coll, nom0 = _release_delays_ref(
            curves, {m: float(cum[m][coll_idx[m]]) for m in curves}, breaks, G_ref_cfg)
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
    # 名义总时长：自首名成员释放到最后成员停止保持结束，不含共同的 20 s 预保持。只记录（决定 50），不拒绝。
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
    wit["target_id"] = target
    wit["turn_ranges"] = (_turn_ranges_v14(P, schedule, slots, coll_idx, lanes, cum) if schedule
                          else _turn_ranges(P, ref, slots, coll_idx, lanes, cum, spacing))
    wit["member_map_v14"] = _member_map(slots, lanes, coll_idx, cum, ref)
    wit["turn_schedule_v14"] = schedule

    # 名义判据预筛选（冻结检测器的纯 NumPy 函数体）：逐成员只记录；V8-13 在优化后的曲线上硬检查（check_monitoring）
    for m in slots.order:
        smp = sample_nominal(members[m], include_prerelease=False, nominal=nominals[m])
        scr = screen_member(ctx.facilities, target, smp.time_us, smp.p, smp.v)
        wit["screen"][m] = {"patrol_revisit": scr["patrol_revisit"], "dwell_anywhere": bool(scr["dwell_anywhere"]["detected"]),
                            "max_target_layer": scr["max_target_layer"], "max_other_layer": scr["max_other_layer"],
                            "revisit": {k: scr["revisit"][k] for k in ("detected", "t1", "t2", "distance_m",
                                                                      "departure_m", "azimuth_coverage_deg")}}
    ref_xy = tuple((float(a), float(b)) for a, b in ref.xy[mark_idx["collect"]:mark_idx["terminal"] + 1])
    wit["required_separation_m"] = None    # V8-13：间距不在骨架上判定，交给联合优化与实测门禁
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


TURN_MIN_KEYS = {"u": "turn_u_min_m", "oblique": "turn_oblique_min_m", "teardrop": "turn_teardrop_min_m"}


def _turn_ranges(P, ref, slots, coll_idx, lanes, cum, spacing):
    """折返掉头的圆弧图元在参考上的站点区间 → 各成员曲线上的弧长区间（V8-13 优化后曲率复核用）。
    {成员: [(掉头类型, s_from_m, s_to_m, 下界配置键)]}；绕圈为空。"""
    if P.get("topology") != "retrace" or not P.get("turns"):
        return {}
    infos = (P.get("topology_info") or {}).get("turns") or []
    pat = patrol_primitives(P)
    smp = sample_primitives(pat, spacing)
    s_loc = np.r_[0.0, np.cumsum(np.hypot(*np.diff(smp.xy, axis=0).T))]
    base = float(ref.marks["patrol_start"])
    stations = []
    k_prim = 0
    for k, (a, b) in enumerate(P["passes"]):
        k_prim += 1
        if k < len(P["passes"]) - 1:
            kind = infos[k]["kind"] if k < len(infos) else None
            for prim in P["turns"][k]:
                lo, hi = smp.intervals[k_prim]
                if prim[0] == "arc":
                    stations.append((kind, base + float(s_loc[lo]), base + float(s_loc[hi])))
                k_prim += 1
    out = {}
    for m in slots.order:
        sref = np.concatenate([np.full(coll_idx[m], -1.0), lanes[m].s_ref])
        rows = []
        for kind, ta, tb in stations:
            idx = np.flatnonzero((sref >= ta - 1e-9) & (sref <= tb + 1e-9))
            if len(idx):
                rows.append((kind, float(cum[m][idx[0]]), float(cum[m][idx[-1]]), TURN_MIN_KEYS.get(kind)))
        out[m] = rows
    return out


def _turn_ranges_v14(P, schedule, slots, coll_idx, lanes, cum):
    """V8-14：掉头核心与接回连接（q ∈ [s_B, s_D]）在各成员曲线上的弧长区间；不含收拢/展开直线。"""
    infos = (P.get("topology_info") or {}).get("turns") or []
    out = {}
    for m in slots.order:
        ln = lanes[m]
        rows = []
        for k, ev in enumerate(schedule):
            kind = infos[k]["kind"] if k < len(infos) else None
            idx = np.flatnonzero((ln.s_ref >= ev["s_B"] - 1e-9) & (ln.s_ref <= ev["s_D"] + 1e-9))
            if len(idx):
                rows.append((kind, float(cum[m][coll_idx[m] + idx[0]]), float(cum[m][coll_idx[m] + idx[-1]]),
                             TURN_MIN_KEYS.get(kind)))
        out[m] = rows
    return out


def _member_map(slots, lanes, coll_idx, cum, ref):
    """member-map-v14：逐成员 (reference_s, shifted_reference_s, member_s, lateral_m, turn_mask) 与巡逻起止成员弧长。
    member_s 含起点连接长度；巡逻站点按成员几何点所在参考站点 q（与候选检查的巡逻范围同一口径）。"""
    out = {}
    for m in slots.order:
        ln = lanes[m]
        ms = np.asarray(cum[m][coll_idx[m]:coll_idx[m] + len(ln.xy)], float)
        pa = float(np.interp(ref.marks["patrol_start"], ln.s_ref, ms))
        pb = float(np.interp(ref.marks["patrol_end"], ln.s_ref, ms))
        out[m] = {"reference_s": ln.s_group.tolist(), "shifted_reference_s": ln.s_ref.tolist(), "member_s": ms.tolist(),
                  "lateral_m": ln.lateral_m.tolist(), "turn_mask": [bool(x) for x in ln.turn_mask],
                  "patrol_member_s": [pa, pb]}
    return {"schema": "member-map-v14", "members": out}


def _release_delays_ref(member_curves, collection_s, speed_breaks, guidance):
    """与冻结 connect.release_delays 同一算法（到汇合槽位名义用时 T_i，δ_i = ceil_0.1s(max T − T_i)），
    只把名义运动的 guidance 换成裁定 2.5 的参考加速度参数。返回 ({δ_i}, {T_i}, {Nominal})。"""
    from ...contract.monitoring import MemberPlan
    from ..connect import ceil_tenth
    times, noms = {}, {}
    for m, xy in member_curves.items():
        plan = MemberPlan(m, 0, tuple(map(tuple, xy)), 0.0, 0.0, 0.0, tuple(speed_breaks[m]))
        nom = member_nominal(plan, guidance=guidance)
        noms[m] = nom
        times[m] = nom.time_at_s(collection_s[m])
    top = max(times.values())
    return {m: ceil_tenth(top - t) for m, t in times.items()}, times, noms


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

PHI_ROWS = 360
R_STEP_M = 2.0
N_CENTERS = 6
N_ENTRIES = 12
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
        self.v0 = float(group.speed_profile.initial_speed_m_s)

    def warning_bbox(self):
        return _warning_bbox(self)

    def polar_mask_single(self, center, rs):
        """V8-13 单车道极坐标掩码 _polar_mask(..., shifts=[0])：宽相位筛选（保守），精确复核只收缩。"""
        return _polar_mask(self, np.asarray(center, float), 1, [0.0], rs)

    def band_geometry(self, center):
        """同一 attempt、同一圈心的射线余量与原始分量只算一次，供各队形宽度查询与构造共用。"""
        from ..monitoring_band import BandGeometry
        cache = self.__dict__.setdefault("_bands", {})
        k = (float(center[0]), float(center[1]))
        if k not in cache:
            t0 = time.perf_counter()
            cache[k] = BandGeometry(self, center)
            _tick(self, "band_geometry_s", time.perf_counter() - t0)
        return cache[k]

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


def _ring_audit(S, center, rho0, coef, phi0, phi1, shifts):
    """只读诊断：按 _ring_ok 同一数据与阈值分别标出三项原因（不改布尔判定）。"""
    out = {"reasons": []}
    try:
        xy, th, kp, ph = sample_loop(center, rho0, coef, phi0, phi1, 1.0)
    except PathError as exc:
        out["reasons"].append("sample_error")
        out["error"] = str(exc)
        return out
    from ..path import kappa_limit, lane_curvature_ok
    limit = kappa_limit(S.ctx.params["curve_spacing_m"], S.G["max_turn_per_chord_rad"])
    kpos, kneg = float(max(kp.max(), 0.0)), float(min(kp.min(), 0.0))
    out.update(kpos=kpos, kneg=kneg, limit=limit)
    lanes_bad = []
    for d in shifts:
        if not lane_curvature_ok(kpos, kneg, d, limit):
            lanes_bad.append({"d_m": float(d), "check": "curvature"})
            continue
        pts = _lane_points(xy, th, d)
        ok = S.cg_patrol.ok(pts)
        if not np.all(ok):
            val = S.cg_patrol.value(pts) - S.cg_patrol.field.eps
            k = int(np.argmin(val))
            lanes_bad.append({"d_m": float(d), "check": "grid", "worst_value_m": float(val[k]),
                              "worst_phi_rad": float(ph[k]), "n_bad": int((~ok).sum())})
    if any(b["check"] == "curvature" for b in lanes_bad):
        out["reasons"].append("curvature")
    if any(b["check"] == "grid" for b in lanes_bad):
        out["reasons"].append("lane_geometry")
    out["lanes"] = lanes_bad
    v_low = S.M["speed_min_m_s"]
    inner = max(shifts, key=lambda d: d * (1.0 if kpos >= -kneg else -1.0)) if shifts else 0.0
    lane = _lane_points(xy, th, inner)
    kl = kp / np.maximum(np.abs(1.0 - kp * inner), 1e-9)
    if _polyline_dwell(S, lane, kl, v_low):
        out["reasons"].append("dwell")
    return out


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


def _warning_bbox(S):
    key = ("warning_bbox", S.target)
    if key not in S.ctx.extra:
        from ...scene.exact import bounding_box
        S.ctx.extra[key] = bounding_box(S.tgt.layers["warning"])
    return S.ctx.extra[key]


def _band_probe(S, slots, centers, prior_topology, sigma):
    """V8-14（裁定 1）：同一批圈心候选上，按局部证书判定该队形能否放下巡逻形状；只由几何与重访覆盖决定。
    先查先验拓扑，不行再查另一拓扑（forced）；第一个通过的圈心即用。"""
    shifts = sorted({d for _, d in slots.offsets.values()})
    info = {"centers_tried": 0, "per_center": []}
    for center in centers:
        info["centers_tried"] += 1
        t0 = time.perf_counter()
        q1 = build_band_query(S, center, slots, topology=prior_topology)
        if q1["feasible"]:
            query, topo, forced = q1, prior_topology, False
        else:
            other = "retrace" if prior_topology == "loop" else "loop"
            q2 = build_band_query(S, center, slots, topology=other)
            query, topo, forced = (q2, other, True) if q2["feasible"] else (None, None, None)
        G = q1["geometry"]
        _tick(S, "band_query_s", time.perf_counter() - t0)
        rec = {"D_m": q1["D"], "q_m": G.q, "eta_m": G.eta, "r_star_m": G.r_star, "components": len(G.components),
               "wrapping_components": sum(bool(c["wrapping"]) for c in G.components), "feasible": query is not None,
               "topology": topo}
        if query is not None:
            rec["candidates"] = len(query["loops"]) if topo == "loop" else len(query["arcs"])
        info["per_center"].append(rec)
        if query is None:
            continue
        return {"center": np.asarray(center, float), "query": query, "topology": topo, "forced": forced,
                "forced_reason": "geometry" if forced else None, "shifts": shifts, "sigma": sigma, "info": info}
    return {"empty": True, "info": info}


def _band_record(G, comp, cert, *, rows=None):
    """证书摘要（入提案）：q、η、阈值、D、诊断 e_g/e_s/e、最小余量与制约方位、所选分量、完整约束名、区间数组（全局 360 行）。"""
    P = 360

    def full(a):
        out = np.full(P, np.nan)
        if rows is None:
            out[:] = a
        else:
            out[np.asarray(rows) % P] = a
        return [None if not np.isfinite(x) else float(x) for x in out]

    return {"component": int(comp["id"]), "component_rows": int(comp["n_rows"]), "wrapping": bool(comp["wrapping"]),
            "q_m": float(G.q), "eta_m": float(G.eta), "r_star_m": float(G.r_star),
            "threshold_m": float(cert["threshold_m"]), "half_span_m": float(cert["half_span_m"]),
            "e_geom_m": cert["e_geom_m"], "e_smooth_m": cert["e_smooth_m"], "e_m": cert["e_m"],
            "min_slack_m": cert["min_slack_m"], "worst": cert["worst"], "constraints": [c.name for c in G.cons],
            "periodic": bool(cert["periodic"]), "row_start": int(cert["row_start"]),
            "lo_m": full(cert["lo"]), "hi_m": full(cert["hi"]), "lower_m": full(cert["lower_m"]),
            "upper_m": full(cert["upper_m"]), "A_m": full(cert["A_m"]), "B_m": full(cert["B_m"])}


def _draw_shape(S, ring, rng):
    """队形与圈心确定后只抽一次：分量/弧端点对 → K ~ U{4..8} → K 个均匀分位数 → logit → 环带内直接构造；
    之后只运行一次原 _ring_ok 三项复核（不重抽、不缩向正圆）。返回 (spec, ok, audit)。"""
    q = ring["query"]
    G = q["geometry"]
    sg = int(ring["sigma"])
    kmin, kmax = int(S.M["spline_basis_min"]), int(S.M["spline_basis_max"])
    step = 2.0 * math.pi / 360.0
    if ring["topology"] == "loop":
        loops = q["loops"]
        w = np.array([c["n_rows"] for c, _ in loops], float)
        comp, cert = loops[int(rng.choice(len(loops), p=w / w.sum()))]
        K = int(rng.integers(kmin, kmax + 1))
        v = rng.random(K)
        z = logit_from_quantiles(v)
        curve = construct_band(cert, z)
        laps = float(rng.uniform(*S.ctx.params["monitoring"]["laps"]))
        phase = float(rng.uniform(0.0, 2 * np.pi))
        spec = {"topology": "loop", "center_xy": tuple(map(float, ring["center"])), "rho0_m": curve.rho0_m,
                "coefficients_m": tuple(float(x) for x in curve.coefficients_m), "phase_rad": phase, "direction": sg,
                "laps": laps, "K": K, "logit_quantiles": tuple(map(float, v)),
                "logit_coefficients": tuple(map(float, z)), "band": _band_record(G, comp, cert),
                "candidates_certified": len(loops)}
        phi0, phi1 = 0.0, sg * 2 * np.pi
    else:
        arcs = q["arcs"]
        comp, ids, rows_mod, (s0, e0, cov), (lo, hi, tl, tu, thr) = arcs[int(rng.integers(0, len(arcs)))]
        K = int(rng.integers(kmin, kmax + 1))
        v = rng.random(K)
        z = logit_from_quantiles(v)
        cert = arc_certificate(lo[rows_mod], hi[rows_mod], tl[rows_mod], tu[rows_mod], s0, e0, q["offsets"],
                               int(ids[s0]))
        cert["threshold_m"] = thr
        curve = construct_band(cert, z)
        phi_a, phi_b = float(ids[s0]) * step, float(ids[e0]) * step
        trav = int(rng.choice(np.array(S.ctx.params["monitoring"]["traversals"], dtype=int)))
        spec = {"topology": "retrace", "center_xy": tuple(map(float, ring["center"])), "rho0_m": curve.rho0_m,
                "coefficients_m": tuple(float(x) for x in curve.coefficients_m), "phi_a": phi_a, "phi_b": phi_b,
                "direction": sg, "traversals": trav, "arc_span_rad": phi_b - phi_a, "K": K,
                "logit_quantiles": tuple(map(float, v)), "logit_coefficients": tuple(map(float, z)),
                "arc_rows": (int(ids[s0]), int(ids[e0])), "param_span_deg": float(e0 - s0),
                "coverage_lower_bound_deg": float(cov), "candidates_certified": len(arcs),
                "band": _band_record(G, comp, cert, rows=ids[s0:e0 + 1])}
        phi0, phi1 = phi_a, phi_b
    shifts = ring["shifts"]
    c = np.asarray(ring["center"], float)
    ok = _ring_ok(S, c, spec["rho0_m"], spec["coefficients_m"], phi0, phi1, shifts)
    audit = None if ok else _ring_audit(S, c, spec["rho0_m"], spec["coefficients_m"], phi0, phi1, shifts)
    return spec, bool(ok), audit


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


def _turns_v14(S, spec, slots, crng):
    """V8-14 第 3 部分：为 traversals 次单向穿行生成相邻两次之间的整体掉头（收拢—单车道核心—接回—展开）。
    返回 ((passes, turns, infos, parts, L), None) 或 (None, 失败见证)。"""
    from ...sim.kernel import member_config as _mc
    from ..path import kappa_limit
    c = np.asarray(spec["center_xy"], float)
    rho0, coef = spec["rho0_m"], np.asarray(spec["coefficients_m"], float)
    phi_a, phi_b = spec["phi_a"], spec["phi_b"]
    ends = (phi_a, phi_b)
    cur_from, cur_to = (phi_a, phi_b) if spec["direction"] > 0 else (phi_b, phi_a)
    offs = np.array([slots.offsets[m] for m in slots.order], float)
    kap = kappa_limit(S.ctx.params["curve_spacing_m"], S.G["max_turn_per_chord_rad"])
    vmax = float(_mc().vehicle_profile.max_speed_xy_m_s)
    fdyn = float(load_config("joint_opt").values["buffer_dynamic_factor"])
    L = collapse_length_m(offs, spacing_m=slots.spacing_m, speed_max_m_s=vmax, command_max_m_s=S.M["speed_max_m_s"],
                          dynamic_factor=fdyn, curvature_limit=kap)
    lcol = column_offsets(len(offs), slots.spacing_m)
    l_star = float(max(np.max(np.abs(offs[:, 0])), np.max(np.abs(lcol)))) if len(offs) else 0.0
    band_lo, band_hi = spec["band"]["lo_m"], spec["band"]["hi_m"]
    rmin = {"u": S.M["turn_u_min_m"], "oblique": S.M["turn_oblique_min_m"], "teardrop": S.M["turn_teardrop_min_m"]}
    step = 2.0 * math.pi / 360.0
    passes, turns, infos, parts = [], [], [], []
    for k in range(spec["traversals"]):
        passes.append((cur_from, cur_to))
        if k == spec["traversals"] - 1:
            break
        dir_k = 1.0 if cur_to > cur_from else -1.0
        other = ends[0] if abs(cur_to - ends[1]) < 1e-9 else ends[1]
        row = int(round(cur_to / step)) % 360
        W = float(band_hi[row] - band_lo[row])
        T = TurnSetup(center=c, rho0=rho0, coef=coef, phi_end=cur_to, direction=dir_k, phi_other=other, L=L,
                      width_m=W, lateral_offsets=offs[:, 1], cons=S.cons["base"] + S.cons["patrol"], r_min=rmin,
                      spacing_m=S.ctx.params["curve_spacing_m"], facility_center=S.tgt.center,
                      min_true_deg=S.criteria["min_azimuth_coverage_deg"], l_star=l_star, kappa_guidance=kap)
        records, stats = sample_joint_turn(T, crng)
        _tick(S, "turn_query_s", float(stats.pop("seconds", 0.0)))
        chosen = choose_joint_turn(records, crng)
        summary = {"L_m": L, "width_m": W, "l_star_m": l_star, "merge_points": stats.get("merge_points"),
                   "collapse_ok": stats.get("collapse_ok"), "nonempty_combos": len(records), "combos": stats["combos"]}
        if chosen is None:
            return None, {"turn_index": k, "query": summary}
        turns.append(tuple(chosen["primitives"]))
        parts.append(dict(chosen["parts"]))
        infos.append({"kind": chosen["kind"], "side": chosen["side"], "radius_m": chosen["radius_m"],
                      "merge_phi": chosen["merge_phi"], "merge_row": chosen["merge_row"],
                      "merge_distance_m": chosen["merge_distance_m"], "h0_m": chosen["h0_m"], "h1_m": chosen["h1_m"],
                      "schedule": chosen["schedule"], "certificate": chosen["certificate"], "query": summary})
        cur_from, cur_to = chosen["merge_phi"], other
    return (tuple(passes), tuple(turns), infos, tuple(parts), L), None


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




# ---------------------------------------------------------------- 形状确定之后的构造链

class _Build:
    """一个 attempt 内、形状确定之后的构造链：转弯 → 入圈 → 起点 → 出圈 → 候选检查。只构造一次。"""

    def __init__(self, S, ctx, group, task, states, key, slots, ring, repairs, steps_log, prior_topology, sigma):
        self.S, self.ctx, self.group, self.task, self.states, self.key = S, ctx, group, task, states, key
        self.slots, self.ring, self.repairs, self.steps_log = slots, ring, repairs, steps_log
        self.prior_topology, self.sigma = prior_topology, sigma

    def prepare(self, spec, rng, crng):
        S, slots, key = self.S, self.slots, self.key
        spec = dict(spec)
        passes = turn_info = None
        if spec["topology"] == "retrace":
            got, fail = _turns_v14(S, spec, slots, crng)
            if got is None:
                self.turn_failure = fail
                return None, _stage_fail("turns", "turn_joint_set_empty：收拢—掉头—接回—展开整体可行集合为空", None, key,
                                         {"traversals": spec["traversals"], "turn_joint_set_empty": True,
                                          "turn_query": fail})
            passes, turns, turn_info, parts, L = got
            spec["passes"], spec["turns"], spec["turn_parts"], spec["turn_L_m"] = passes, turns, parts, L
        S0, _ = _patrol_poses(spec, passes)
        ing = _plan_ingress(S, slots, S0, rng, crng)
        if ing is None:
            return None, _stage_fail("ingress", "没有可用的入圈直线与连接", None, key)
        starts, meta = _plan_starts(S, slots, ing["C"], ing["u"], crng)
        if starts is None:
            return None, _stage_fail("start_route", f"成员 {meta} 没有可用的起点路由", None, key,
                                     {"route_stats": dict(S.stats)})
        return {"spec": spec, "passes": passes, "turn_info": turn_info, "ing": ing, "starts": starts, "meta": meta}, None

    def assemble(self, prep, spec_now, rng, crng, extra_repairs=()):
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
             "repairs": tuple(self.repairs) + tuple(extra_repairs),
             "topology_info": {"prior_draw": self.prior_topology, "forced": ring["forced"],
                               "forced_reason": ring.get("forced_reason"), "ring": ring["info"],
                               "formation_steps": self.steps_log, "turns": prep["turn_info"], "sigma": self.sigma,
                               "entry": {k: ing[k] for k in ("D", "t_in", "depth_min", "tried")},
                               "exit": {k: eg[k] for k in ("D", "t_out", "depth_min", "tried")},
                               "starts": prep["meta"]}}
        return P, build_candidate(self.ctx, self.group, self.task, self.states, (), key, P)


def _finish_loop(B, ring, spec, rng, crng):
    """用原 spec 抽到的圈数一次 prepare/assemble。"""
    prep, fail = B.prepare(spec, rng, crng)
    if fail is not None:
        return fail
    _, plan = B.assemble(prep, prep["spec"], rng, crng)
    return plan


def _finish_retrace(B, ring, spec, rng, crng):
    """用原 spec 抽到的穿行次数一次 prepare/assemble。"""
    prep, fail = B.prepare(spec, rng, crng)
    if fail is not None:
        return fail
    _, plan = B.assemble(prep, prep["spec"], rng, crng)
    return plan


def _tick(S, name, seconds):
    t = S.__dict__.setdefault("timing", {})
    t[name] = t.get(name, 0.0) + float(seconds)


_LAST_TIMING = {}


def last_attempt_timing():
    """本进程最近一次 propose_and_build 的分阶段墙钟（遥测，不进入任何确定性载荷）。"""
    return dict(_LAST_TIMING)


def _skeleton_diag(S, slots, ring, steps_log, spec=None, audit=None, turn_failure=None):
    """每个 attempt 的骨架诊断（只记录，不参与决定）：队形探测、圈心、证书、形状复核、掉头集合与耗时。"""
    band = (spec or {}).get("band") or {}
    out = {"formation": slots.realized if slots is not None else None,
           "lateral_step_m": slots.lateral_step_m if slots is not None and slots.realized == "echelon" else None,
           "formation_steps": [{k: v for k, v in st.items() if k != "info"} | {"centers": st["info"]["per_center"]}
                               for st in steps_log],
           "shape_audit_entered": spec is not None, "shape_audit_failed": audit is not None,
           "shape_audit": audit,
           "certificate": {k: band.get(k) for k in ("component", "component_rows", "wrapping", "q_m", "eta_m",
                                                   "r_star_m", "threshold_m", "half_span_m", "e_geom_m",
                                                   "e_smooth_m", "e_m", "min_slack_m", "worst")} if band else None,
           "candidates_certified": (spec or {}).get("candidates_certified"),
           "topology": (ring or {}).get("topology"), "forced": (ring or {}).get("forced"),
           "turn_failure": turn_failure}
    return out


def _build_with_ring(S, ctx, group, task, states, key, slots, ring, used, b, steps_log, prior_topology, sigma, rng, crng):
    """给定队形与已认证的环带，环带内直接构造一次形状并完成构造；返回 SegmentPlan（失败时 failure 非空）。
    V8-14：删除 α 扫描；形状复核失败原样返回（patrol_shape_audit），由外层唯一预算决定是否进入下一 attempt。"""
    repairs = []
    if slots.realized != slots.start:
        repairs.append({"kind": "formation_retreat", "from": slots.start, "to": slots.realized, "forced_by": "width"})
    if used is not None and used < b - 1e-9:
        repairs.append({"kind": "echelon_lateral_step", "from_m": b, "to_m": used})
    spec, ok, audit = _draw_shape(S, ring, rng)
    if not ok:
        diag = _skeleton_diag(S, slots, ring, steps_log, spec, audit)
        return _stage_fail("patrol_shape_audit", "环带内直接构造的形状未通过原 _ring_ok 三项复核", None, key,
                           {"topology": ring["topology"], "audit": audit, "shape_audit_failed": True,
                            "draw": draw_summary(spec, slots.realized), "skeleton_diag": diag})
    B = _Build(S, ctx, group, task, states, key, slots, ring, repairs, steps_log, prior_topology, sigma)
    if spec["topology"] == "loop":
        plan = _finish_loop(B, ring, spec, rng, crng)
    else:
        plan = _finish_retrace(B, ring, spec, rng, crng)
    diag = _skeleton_diag(S, slots, ring, steps_log, spec, None, getattr(B, "turn_failure", None))
    if plan.failure is not None:
        # V8-13c 裁定 3：记下本次抽到的形状（只作骨架重试偏差诊断，不参与任何构造决定）
        w = dict(plan.failure.witness or {})
        w["draw"] = draw_summary(spec, slots.realized)
        w["skeleton_diag"] = diag
        w.setdefault("shape_audit_failed", False)
        plan = replace(plan, failure=replace(plan.failure, witness=w))
    else:
        plan = replace(plan, witnesses={**plan.witnesses, "skeleton_diag": diag})
    return plan


def draw_summary(spec, formation):
    """骨架抽样摘要：拓扑、巡逻平均半径（周期 B 样条系数均值 ρ0）、圈数或往返次数、实际队形；
    V8-14 另记首次确定的随机量：圈心、K、logit 分位数、弧端点。"""
    return {"topology": spec.get("topology"), "rho0_m": spec.get("rho0_m"), "laps": spec.get("laps"),
            "traversals": spec.get("traversals"), "formation": formation, "center_xy": spec.get("center_xy"),
            "K": spec.get("K"), "logit_quantiles": spec.get("logit_quantiles"), "arc_rows": spec.get("arc_rows"),
            "direction": spec.get("direction")}


def _echelon_payload(S, group, fam, fkey, order, centers, prior_topology, sigma, b, steps_log):
    """梯形（指令 2.3）：在 [3, b] 内求同一局部证书可容纳的最大横向步长。先试 b，再试 3；3 通过而 b 不通过时对
    步长确定性二分，直到区间宽 ≤ 2/(n−1) m（2 m 径向网格映射到车道跨度），返回已认证通过的下端。
    管集合随 D 嵌套，所有探测用同一批圈心与同一份射线余量。不用下游失败缩步长。"""
    def probe(st):
        slots = formation_slots(group, fam, fkey, formation="echelon", lateral_step_m=st, order=order)
        r = _band_probe(S, slots, centers, prior_topology, sigma)
        steps_log.append({"formation": "echelon", "lateral_step_m": st, "found": "empty" not in r, "info": r["info"]})
        return None if "empty" in r else {"slots": slots, "ring": r, "lateral_step_m": st}

    got = probe(b)
    if got is not None:
        return got
    n = len(group.member_ids)
    if n < 2:
        return None
    best = probe(MIN_LATERAL_STEP_M)
    if best is None:
        return None
    lo, hi = MIN_LATERAL_STEP_M, b
    tol = 2.0 / (n - 1)
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        res = probe(mid)
        if res is not None:
            lo, best = mid, res
        else:
            hi = mid
    return best


def propose_and_build(ctx, group, task, states, key):
    """一次随机构造（一个 attempt）：宽度先定队形（skeleton.width_then_build）→ 环带局部证书 → 环带内直接构造 →
    折返整体掉头 → 入圈/出圈 → 起点路由 → 速度 → 骨架几何检查。队形只由同一局部证书选择（abreast → echelon →
    column；echelon 先求最大可容纳横向步长）；选定后只构造一次，下游任何失败原样返回，不改队形。"""
    S = _Setup(ctx, group, task, states, key)
    S.timing = {}
    _LAST_TIMING.clear()
    t_all = time.perf_counter()
    try:
        rng, crng = S.rng("shape"), S.rng("connect")
        fam = ctx.family
        full_p = ctx.params["monitoring"]["full_probability"]
        prior_topology = "loop" if float(rng.random()) < full_p else "retrace"
        sigma = 1 if float(rng.random()) < 0.5 else -1
        chain = retreat_chain(mapped_start(group.formation_prior))
        b = float(fam.lateral_spacing_m)
        fkey = RngKey(key.family_id, key.draw, "formation", mission=key.mission, branch=key.branch, group=key.group,
                      segment=key.segment, attempt=key.attempt)
        order = formation_slots(group, fam, fkey, formation=chain[0]).order
        centers = _center_candidates(S, rng, N_CENTERS)
        steps_log = []

        def width_probe(name):
            if name == "echelon":
                return _echelon_payload(S, group, fam, fkey, order, centers, prior_topology, sigma, b, steps_log)
            slots = formation_slots(group, fam, fkey, formation=name, order=order)
            r = _band_probe(S, slots, centers, prior_topology, sigma)
            steps_log.append({"formation": name, "lateral_step_m": None, "found": "empty" not in r, "info": r["info"]})
            return None if "empty" in r else {"slots": slots, "ring": r, "lateral_step_m": None}

        def build(name, payload):
            return _build_with_ring(S, ctx, group, task, states, key, payload["slots"], payload["ring"],
                                    payload["lateral_step_m"], b, steps_log, prior_topology, sigma, rng, crng)

        plan = width_then_build(chain, width_probe, build)
        if plan is not None:
            return plan
        diag = _skeleton_diag(S, None, None, steps_log)
        return _stage_fail("patrol_region", "所有队形下目标环带都没有满足局部证书的环/弧（approx_empty 查询）", None, key,
                           {"formations": [{k: v for k, v in st.items() if k != "info"} for st in steps_log],
                            "shape_audit_failed": False, "skeleton_diag": diag})
    finally:
        S.timing["attempt_s"] = time.perf_counter() - t_all
        _LAST_TIMING.update(S.timing)


def replace_repairs(plan, extra):
    from dataclasses import replace
    return replace(plan, repairs=tuple(plan.repairs) + tuple(extra))
