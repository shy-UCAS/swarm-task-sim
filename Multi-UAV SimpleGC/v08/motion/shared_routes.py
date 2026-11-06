"""初始点 → 集合槽位的可视图路由（V8-16 指令 3.1；本项新增，机械抽取）。

函数体逐字来自固定提交 ed44227 的 v08/motion/intents/monitoring.py：_lane_points、_proxy_prims、_inward_start、
_count、_route、_plan_starts（含其依赖的常量与辅助），只把 _route 内部调用的 skeleton_planner 改为参数
planner_factory、_plan_starts 内部调用的 _route 改为参数 route_fn。监视模块保留同名旧包装：传原 skeleton_planner
与原 _route，签名、调用顺序、随机数消耗与返回值不变（第 2.3 节监视字节门禁验证）。
过境传 transit_chords.entry_planner（额外把目标 warning 外扩 10 + Δ 作障碍，见指令 3.1）。

既有 4 类 Δ = (None, 10, 30, 80) 与每类最多 6 个连接候选来自固定源码，原样复用，不增加候选数。
"""
import numpy as np

from ..scene.exact import signed_distance
from .connect import MIN_STRAIGHT_M, corner_radius_bounds, fillet_route, left_normal, unit
from .path import PathError, sample_primitives


def _lane_points(xy, theta, d):
    n = np.stack([-np.sin(theta), np.cos(theta)], axis=1)
    return xy + d * n


def _proxy_prims(S, prims, shifts, cg, *, arcs_avoid_bands=False, spacing=1.0):
    """图元在各车道偏移下的保守栅格检查（并要求偏移不翻转曲率）。"""
    try:
        smp = sample_primitives(list(prims), spacing)
    except (PathError, ValueError):
        return False
    from .path import kappa_limit, lane_curvature_ok
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


def route_to_slot(S, p0, slot, u, rng, *, planner_factory):
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
                pl = planner_factory(ctx, delta)
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


def plan_starts(S, slots, C, u, rng, *, route_fn):
    n_u = left_normal(u)
    out, meta = {}, {}
    for m in slots.order:
        l, d = slots.offsets[m]
        slot = C + l * u + d * n_u
        p0 = np.asarray(S.states[m].p[:2], float)
        prims, delta = route_fn(S, p0, slot, u, rng)
        if prims is None:
            return None, m
        out[m] = prims
        meta[m] = {"skeleton_delta_m": delta, "primitives": len(prims)}
    return out, meta
