"""边界穿越检查、释放延迟与连接规划（V8-12 第 3 部分；指令 3.5）。只用 NumPy。

边界规则（r4 6.3，指令 3.5）：
- 每个设施的 warning 边界两侧各 band_m（10 m）内的路径，必须构成一次完整、严格单次的直线穿越：
  从外 +10 到内 −10（或反向）整段共线；切触后退回同侧不合法；未穿越的部分离边界 ≥ 10 m。
- 每次进入目标 warning 前须有连续 align_m（100 m）直线：交点之前 100 m 的路径整段共线。
- alert/protected 层由静态约束（外侧 ≥ 10 m）保证不会靠近，不在这里重复。
"""
import math
from dataclasses import dataclass

import numpy as np

from ..scene.exact import chord_sdf_range, signed_distance

NODE_TOL_M = 1e-6


@dataclass(frozen=True)
class Crossing:
    facility_id: str
    direction: str            # "in" / "out"
    s_m: float                # 交点处的累计弧长
    chord_index: int
    straight_band: bool
    straight_align: bool | None


def _cum(xy):
    return np.r_[0.0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]


def _collinear(points, tol):
    a, b = points[0], points[-1]
    d = b - a
    L = float(np.hypot(*d))
    if L <= 0.0 or len(points) < 3:
        return True
    cross = np.abs((points[:, 0] - a[0]) * d[1] - (points[:, 1] - a[1]) * d[0]) / L
    return bool(cross.max() <= tol)


def crossing_analysis(xy, warnings, target_id, *, band_m, align_m, tol_m=NODE_TOL_M, skip_ranges=()):
    """逐设施分析 warning 边界穿越；返回 (violations, crossings)。violations 是 dict 列表，
    含 facility、kind、弧长和数值，作为失败见证。skip_ranges 是弧长区间，用于不检查某段（不用）。"""
    P = np.asarray(xy, dtype=float)[:, :2]
    N = len(P)
    s = _cum(P)
    violations, crossings = [], []
    for fid, geom in warnings.items():
        sv = signed_distance(geom, P)
        lo, hi, _ = chord_sdf_range(geom, P[:-1], P[1:])
        band = (lo < band_m) & (hi > -band_m)
        edges = np.flatnonzero(np.diff(np.r_[False, band, False].astype(np.int8)))
        for a, b in zip(edges[::2].tolist(), edges[1::2].tolist()):
            sa, sb = float(sv[a]), float(sv[b])
            if abs(sa) < band_m or abs(sb) < band_m:
                violations.append({"facility": fid, "kind": "path_endpoint_in_band", "s_m": float(s[a]),
                                   "signed_start_m": sa, "signed_end_m": sb})
                continue
            if not (abs(sa) >= band_m and abs(sb) >= band_m and sa * sb < 0.0):
                violations.append({"facility": fid, "kind": "graze_or_touch_band", "s_m": float(s[a]),
                                   "signed_start_m": sa, "signed_end_m": sb})
                continue
            straight = _collinear(P[a:b + 1], tol_m)
            if not straight:
                seg = P[a:b + 1]
                dd = seg[-1] - seg[0]
                dev = float((np.abs((seg[:, 0] - seg[0, 0]) * dd[1] - (seg[:, 1] - seg[0, 1]) * dd[0])
                             / max(float(np.hypot(*dd)), 1e-12)).max())
                violations.append({"facility": fid, "kind": "band_not_straight", "s_m": float(s[a]),
                                   "signed_start_m": sa, "signed_end_m": sb, "vertex_range": (int(a), int(b)),
                                   "max_deviation_m": dev, "point_start": tuple(map(float, P[a])),
                                   "point_end": tuple(map(float, P[b]))})
            k = a
            while k < b - 1 and sv[k] * sv[k + 1] > 0.0:
                k += 1
            frac = 0.0 if sv[k] == sv[k + 1] else float(sv[k] / (sv[k] - sv[k + 1]))
            s_c = float(s[k] + frac * (s[k + 1] - s[k]))
            direction = "in" if sa > 0 else "out"
            aligned = None
            if direction == "in" and fid == target_id:
                aligned = True
                if s_c < align_m - tol_m:
                    aligned = False
                else:
                    s0 = s_c - align_m
                    pa = np.array([np.interp(s0, s, P[:, 0]), np.interp(s0, s, P[:, 1])])
                    pb = np.array([np.interp(s_c, s, P[:, 0]), np.interp(s_c, s, P[:, 1])])
                    sel = P[(s > s0) & (s < s_c)]
                    block = np.vstack([pa, sel, pb])
                    aligned = abs(float(np.hypot(*(pb - pa))) - align_m) <= tol_m and _collinear(block, tol_m)
                if not aligned:
                    violations.append({"facility": fid, "kind": "align_100m_not_straight", "s_m": s_c,
                                       "signed_start_m": sa, "signed_end_m": sb})
            crossings.append(Crossing(fid, direction, s_c, int(k), straight, aligned))
    return violations, crossings


def ceil_tenth(x):
    """向上取整到 0.1 s 网格（扣掉浮点噪声，避免 0.3000000000000001 变成 0.4）。"""
    return math.ceil(round(x * 10.0, 6)) / 10.0


def release_delays(member_curves, collection_s, speed_breaks, *, return_nominals=False):
    """用完整成员曲线的速度剖面算到汇合槽位节点的名义用时 T_i，δ_i = ceil_0.1s(max T − T_i) ≥ 0。

    member_curves: {成员: curve_xy}；collection_s: {成员: 汇合槽位处的累计弦长}；
    speed_breaks: {成员: speed_breaks}。返回 ({成员: δ_i}, {成员: T_i})；
    return_nominals=True 时再返回 {成员: Nominal}（release_s 按零延迟，调用方按 δ_i 换成实际释放时刻，
    避免对同一条曲线重复做 make_curve / speed_profile）。"""
    from ..contract.monitoring import MemberPlan
    from .nominal import member_nominal

    times, noms = {}, {}
    for m, xy in member_curves.items():
        plan = MemberPlan(m, 0, tuple(map(tuple, xy)), 0.0, 0.0, 0.0, tuple(speed_breaks[m]))
        nom = member_nominal(plan)
        noms[m] = nom
        times[m] = nom.time_at_s(collection_s[m])
    top = max(times.values())
    delays = {m: ceil_tenth(top - t) for m, t in times.items()}
    if return_nominals:
        return delays, times, noms
    return delays, times


# ---------------------------------------------------------------- 折线 + 圆角过渡

MIN_STRAIGHT_M = 6.0   # = max(5, 0.6 × 速度上限 10 m/s)：不连续异号曲率之间的直线（r4 6.6），取上界覆盖所有期望速度


def unit(v):
    v = np.asarray(v, dtype=float)
    n = float(np.hypot(*v))
    if n <= 0.0:
        raise ValueError("零向量")
    return v / n


def left_normal(u):
    return np.array([-u[1], u[0]])


def fillet_route(points, radii):
    """折线 points (n+1, 2)，内部顶点 1..n−1 的圆角半径 radii（长度 n−1，None 表示不倒角）。
    返回 line/arc 图元元组。相邻圆角的切线长之和须不超过所在边长 − MIN_STRAIGHT_M，否则抛 ValueError。
    圆角不改变折线的拓扑；本函数只做几何，是否满足间距由调用方的精确检查负责。"""
    P = [np.asarray(p, dtype=float) for p in points]
    n = len(P) - 1
    if n < 1:
        raise ValueError("折线至少两点")
    if len(radii) != n - 1:
        raise ValueError("radii 长度须等于内部顶点数")
    seg = [P[i + 1] - P[i] for i in range(n)]
    length = [float(np.hypot(*s)) for s in seg]
    if min(length) <= 0.0:
        raise ValueError("折线含零长度边")
    dirs = [s / l for s, l in zip(seg, length)]
    tang = [0.0] * (n - 1)
    ang = [0.0] * (n - 1)
    for k in range(1, n):
        a, b = dirs[k - 1], dirs[k]
        cross = a[0] * b[1] - a[1] * b[0]
        theta = math.atan2(abs(cross), float(a @ b))
        ang[k - 1] = math.copysign(theta, cross)
        r = radii[k - 1]
        tang[k - 1] = 0.0 if (r is None or theta < 1e-9) else float(r) * math.tan(theta / 2.0)
    for i in range(n):
        used = (tang[i - 1] if i >= 1 else 0.0) + (tang[i] if i < n - 1 else 0.0)
        need = MIN_STRAIGHT_M if (i >= 1 and i < n - 1 and tang[i - 1] > 0 and tang[i] > 0) else 0.0
        if used > length[i] - need + 1e-9:
            raise ValueError(f"第 {i} 条边放不下圆角：切线长 {used:.3f} m，边长 {length[i]:.3f} m")
    prims = []
    cur = P[0]
    for k in range(1, n):
        t = tang[k - 1]
        if t == 0.0:
            continue
        a, b = dirs[k - 1], dirs[k]
        t1 = P[k] - a * t
        t2 = P[k] + b * t
        if float(np.hypot(*(t1 - cur))) > 1e-9:
            prims.append(("line", tuple(cur), tuple(t1)))
        side = 1.0 if ang[k - 1] > 0 else -1.0
        r = float(radii[k - 1])
        c = t1 + side * r * left_normal(a)
        a0 = math.atan2(t1[1] - c[1], t1[0] - c[0])
        prims.append(("arc", tuple(c), r, a0, ang[k - 1]))
        cur = t2
    if float(np.hypot(*(P[-1] - cur))) > 1e-9:
        prims.append(("line", tuple(cur), tuple(P[-1])))
    return tuple(prims)


def corner_radius_bounds(points, k, delta_m, avail_m, *, r_floor):
    """顶点 k 处的圆角半径上界：边长够放 + 圆角向内切入量不超过骨架多留的余量 delta_m。"""
    P = [np.asarray(p, dtype=float) for p in points]
    a, b = unit(P[k] - P[k - 1]), unit(P[k + 1] - P[k])
    theta = math.atan2(abs(a[0] * b[1] - a[1] * b[0]), float(a @ b))
    if theta < 1e-9:
        return None
    half = theta / 2.0
    r_len = avail_m / max(math.tan(half), 1e-12)
    sec_minus_1 = 1.0 / max(math.cos(half), 1e-12) - 1.0
    r_cut = max(delta_m - 0.5, 0.0) / max(sec_minus_1, 1e-12) if delta_m is not None else math.inf
    return max(min(r_len, r_cut), 0.0), theta


def skeleton_planner(ctx, delta_m):
    """可视图骨架规划器：world 内缩 35 + Δ，障碍外扩 35 + Δ，所有设施 alert 外扩 10 + Δ。
    Δ 给圆角过渡留出向内切入的余量。同一 Δ 只建一次。"""
    key = ("skeleton", float(delta_m))
    if key not in ctx.extra:
        from ..scene.exact import expand
        from ..scene.visibility import build_planner

        P = ctx.params
        with ctx.cold_build():
            blockers = [("obstacle:" + i, expand(g, P["obstacle_margin_m"] + delta_m)) for i, g in ctx.obstacles]
            blockers += [("alert:" + f.id, expand(f.layers["alert"], P["forbidden_margin_m"] + delta_m))
                         for f in ctx.facilities]
            ctx.extra[key] = build_planner(ctx.world, blockers, world_margin_m=P["world_margin_m"] + delta_m)
    return ctx.extra[key]
