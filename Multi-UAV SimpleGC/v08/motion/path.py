"""路径图元与采样（V8-12 第 3 部分）。只用 NumPy，不导入 shapely。

图元（元组）：
  ("line", 起点, 终点)
  ("arc", 圆心, 半径, 起始角, 有符号扫角)           扫角 > 0 逆时针
  ("bezier5", (P0, …, P5))                           五次 Bézier，端点曲率为零的姿态连接
  ("spline_arc", 圆心, rho0, 系数, 起始相位, 终止相位) 周期三次 B 样条半径曲线 ρ(φ) 上的一段，φ 递减即顺时针
相邻图元共用同一个接点坐标，采样时后一个图元不重复插入接点，也不让 sin/cos 舍入产生极短伪弦。
"""
import math
from dataclasses import dataclass

import numpy as np

from ..scene.exact import polyline_clearance

TWO_PI = 2.0 * math.pi
CONTINUITY_TOL_M = 1e-6


class PathError(ValueError):
    """图元非法或接点不连续。"""


# ---------------------------------------------------------------- 周期三次 B 样条半径

def _basis(u):
    return (((1 - u) ** 3) / 6.0, (3 * u ** 3 - 6 * u ** 2 + 4) / 6.0,
            (-3 * u ** 3 + 3 * u ** 2 + 3 * u + 1) / 6.0, (u ** 3) / 6.0)


def _basis1(u):
    return (-((1 - u) ** 2) / 2.0, (3 * u ** 2 - 4 * u) / 2.0, (-3 * u ** 2 + 2 * u + 1) / 2.0, (u ** 2) / 2.0)


def _basis2(u):
    return (1 - u, 3 * u - 2, -3 * u + 1, u)


def periodic_radius_derivs(phi, rho0_m, coefficients_m):
    """ρ(φ) 及其对 φ 的一、二阶导数。均匀周期节点 φ_j = 2πj/K，K = len(coefficients)。"""
    a = np.asarray(coefficients_m, dtype=float)
    K = len(a)
    if K < 3:
        raise PathError("周期三次 B 样条至少需要 3 个系数")
    phi = np.asarray(phi, dtype=float)
    t = np.mod(phi, TWO_PI) * K / TWO_PI
    i = np.floor(t).astype(np.int64)
    i = np.minimum(i, K - 1)
    u = t - i
    idx = [(i - 1 + m) % K for m in range(4)]
    scale = K / TWO_PI
    rho = rho0_m + sum(w * a[j] for w, j in zip(_basis(u), idx))
    d1 = scale * sum(w * a[j] for w, j in zip(_basis1(u), idx))
    d2 = scale * scale * sum(w * a[j] for w, j in zip(_basis2(u), idx))
    return rho, d1, d2


def periodic_radius(phi, rho0_m, coefficients_m):
    return periodic_radius_derivs(phi, rho0_m, coefficients_m)[0]


def interpolating_coefficients(radii):
    """使 ρ(φ_j) = radii[j] 的周期样条系数（含均值）：(c_{j−1} + 4c_j + c_{j+1})/6 = r_j。"""
    r = np.asarray(radii, dtype=float)
    K = len(r)
    M = np.zeros((K, K))
    for j in range(K):
        M[j, (j - 1) % K] += 1.0 / 6.0
        M[j, j] += 4.0 / 6.0
        M[j, (j + 1) % K] += 1.0 / 6.0
    return np.linalg.solve(M, r)


# ---------------------------------------------------------------- 解析原语

def circle_offsets(radius_m, offsets_m, theta):
    """逆时针圆上各车道的位置，形状 (成员, 采样点, 2)。逆时针左法向向内，车道半径 R − d。"""
    th = np.asarray(theta, dtype=float)
    d = np.atleast_1d(np.asarray(offsets_m, dtype=float))
    r = radius_m - d
    if np.any(r <= 0.0):
        raise PathError("车道半径非正：偏移大于圆半径")
    return np.stack([r[:, None] * np.cos(th)[None], r[:, None] * np.sin(th)[None]], axis=2)


@dataclass(frozen=True)
class Primitive:
    kind: str
    length_m: float
    start_tangent: tuple
    end_tangent: tuple


@dataclass(frozen=True)
class Joined:
    xy: np.ndarray
    primitives: tuple


def opposite_arc_join(radius_m, angle_rad, speed_m_s, chord_m):
    """等半径的正角圆弧、规定直线 L = max(5, 0.6 v)、负角圆弧（局部坐标：原点，沿 +x 出发）。
    只用于局部拼接原语（r4 6.6：不连续异号曲率之间必须插直线）。"""
    if not (radius_m > 0 and angle_rad > 0 and speed_m_s > 0 and chord_m > 0):
        raise PathError("半径、角度、速度、弦长都须为正")
    L = max(5.0, 0.6 * speed_m_s)
    prims = (("arc", (0.0, radius_m), radius_m, -math.pi / 2, angle_rad),)
    p1 = np.array([radius_m * math.sin(angle_rad), radius_m * (1 - math.cos(angle_rad))])
    t = np.array([math.cos(angle_rad), math.sin(angle_rad)])
    p2 = p1 + L * t
    n = np.array([-t[1], t[0]])
    c2 = p2 - radius_m * n          # 右转：圆心在右侧
    a2 = math.atan2(p2[1] - c2[1], p2[0] - c2[0])
    prims = prims + (("line", tuple(p1), tuple(p2)), ("arc", tuple(c2), radius_m, a2, -angle_rad))
    s = sample_primitives(prims, chord_m)
    t0 = (1.0, 0.0)
    t1 = (math.cos(angle_rad), math.sin(angle_rad))
    info = (Primitive("arc", radius_m * angle_rad, t0, t1), Primitive("line", L, t1, t1),
            Primitive("arc", radius_m * angle_rad, t1, t0))
    return Joined(s.xy, info)


# ---------------------------------------------------------------- 图元采样

@dataclass(frozen=True)
class Sampled:
    xy: np.ndarray            # (N, 2)
    theta: np.ndarray         # (N,) 前进方向角
    kappa: np.ndarray         # (N,) 有符号曲率（逆时针为正）
    intervals: tuple = ()     # 每个图元的 (起始下标, 结束下标)，闭区间，接点下标共用


def _line(p0, p1, spacing):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    L = float(np.hypot(*(p1 - p0)))
    if L <= 0.0:
        raise PathError("直线长度为 0")
    n = max(1, int(math.ceil(L / spacing - 1e-9)))
    t = np.linspace(0.0, 1.0, n + 1)
    xy = p0[None] + t[:, None] * (p1 - p0)[None]
    th = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    return xy, np.full(n + 1, th), np.zeros(n + 1)


def _arc(c, r, a0, sweep, spacing):
    c = np.asarray(c, float)
    if r <= 0 or sweep == 0.0:
        raise PathError("圆弧半径须为正、扫角非零")
    n = max(1, int(math.ceil(abs(sweep) * r / spacing - 1e-9)))
    phi = a0 + sweep * np.linspace(0.0, 1.0, n + 1)
    sg = 1.0 if sweep > 0 else -1.0
    xy = c[None] + r * np.stack([np.cos(phi), np.sin(phi)], axis=1)
    return xy, phi + sg * math.pi / 2, np.full(n + 1, sg / r)


def _bezier_eval(P, t):
    P = np.asarray(P, float)
    b = np.array([1, 5, 10, 10, 5, 1], float)
    t = np.asarray(t, float)[:, None]
    k = np.arange(6)[None]
    B = b[None] * t ** k * (1 - t) ** (5 - k)
    d1 = 5 * (P[1:] - P[:-1])
    b4 = np.array([1, 4, 6, 4, 1], float)
    k4 = np.arange(5)[None]
    B4 = b4[None] * t ** k4 * (1 - t) ** (4 - k4)
    d2 = 4 * (d1[1:] - d1[:-1])
    b3 = np.array([1, 3, 3, 1], float)
    k3 = np.arange(4)[None]
    B3 = b3[None] * t ** k3 * (1 - t) ** (3 - k3)
    return B @ P, B4 @ d1, B3 @ d2


def _bezier(P, spacing, fine_n=401):
    fine = np.linspace(0.0, 1.0, fine_n)
    pos, _, _ = _bezier_eval(P, fine)
    seg = np.hypot(*np.diff(pos, axis=0).T)
    cum = np.r_[0.0, np.cumsum(seg)]
    L = float(cum[-1])
    if L <= 0.0:
        raise PathError("Bézier 长度为 0")
    n = max(1, int(math.ceil(L / spacing - 1e-9)))
    t = np.interp(np.linspace(0.0, L, n + 1), cum, fine)
    xy, d1, d2 = _bezier_eval(P, t)
    th = np.arctan2(d1[:, 1], d1[:, 0])
    sp = np.hypot(d1[:, 0], d1[:, 1])
    kappa = (d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / np.maximum(sp ** 3, 1e-300)
    xy[0], xy[-1] = np.asarray(P[0], float), np.asarray(P[-1], float)
    return xy, th, kappa


def sample_loop(center, rho0, coefficients, phi0, phi1, spacing, *, fine_per_m=4.0):
    """ρ(φ) 曲线从 φ0 到 φ1（φ1 < φ0 为顺时针）的等弧长采样；返回 (xy, theta, kappa, phi)。"""
    c = np.asarray(center, float)
    span = phi1 - phi0
    if span == 0.0:
        raise PathError("相位跨度为 0")
    sg = 1.0 if span > 0 else -1.0
    rho_ref = float(abs(rho0)) + float(np.max(np.abs(coefficients))) if len(coefficients) else float(abs(rho0))
    nfine = max(64, int(math.ceil(abs(span) * rho_ref * fine_per_m / 1.0)))
    phi = phi0 + span * np.linspace(0.0, 1.0, nfine + 1)
    rho, d1, d2 = periodic_radius_derivs(phi, rho0, coefficients)
    if np.any(rho <= 0):
        raise PathError("半径样条出现非正值")
    cs, sn = np.cos(phi), np.sin(phi)
    pos = c[None] + np.stack([rho * cs, rho * sn], axis=1)
    cum = np.r_[0.0, np.cumsum(np.hypot(*np.diff(pos, axis=0).T))]
    L = float(cum[-1])
    n = max(1, int(math.ceil(L / spacing - 1e-9)))
    ph = np.interp(np.linspace(0.0, L, n + 1), cum, phi)
    rho, d1, d2 = periodic_radius_derivs(ph, rho0, coefficients)
    cs, sn = np.cos(ph), np.sin(ph)
    xy = c[None] + np.stack([rho * cs, rho * sn], axis=1)
    vx = d1 * cs - rho * sn
    vy = d1 * sn + rho * cs
    ax = d2 * cs - 2 * d1 * sn - rho * cs
    ay = d2 * sn + 2 * d1 * cs - rho * sn
    sp = np.hypot(vx, vy)
    th = np.arctan2(sg * vy, sg * vx)
    kappa = sg * (vx * ay - vy * ax) / np.maximum(sp ** 3, 1e-300)
    return xy, th, kappa, ph


def sample_primitives(primitives, spacing_m):
    if not primitives:
        raise PathError("没有图元")
    xs, ths, ks, intervals = [], [], [], []
    count = 0
    prev_end = None
    for prim in primitives:
        kind = prim[0]
        if kind == "line":
            xy, th, kp = _line(prim[1], prim[2], spacing_m)
        elif kind == "arc":
            xy, th, kp = _arc(prim[1], float(prim[2]), float(prim[3]), float(prim[4]), spacing_m)
        elif kind == "bezier5":
            xy, th, kp = _bezier(prim[1], spacing_m)
        elif kind == "spline_arc":
            xy, th, kp, _ = sample_loop(prim[1], prim[2], prim[3], prim[4], prim[5], spacing_m)
        else:
            raise PathError(f"未知图元：{kind!r}")
        if prev_end is not None:
            gap = float(np.hypot(*(xy[0] - prev_end)))
            if gap > CONTINUITY_TOL_M:
                raise PathError(f"图元接点不连续：间隙 {gap} m")
            xy, th, kp = xy[1:], th[1:], kp[1:]
            start = count - 1
        else:
            start = 0
        xs.append(xy), ths.append(th), ks.append(kp)
        count += len(xy)
        intervals.append((start, count - 1))
        prev_end = xy[-1]
    return Sampled(np.vstack(xs), np.concatenate(ths), np.concatenate(ks), tuple(intervals))


# ---------------------------------------------------------------- 证书采样与五次 Bézier 姿态连接

@dataclass(frozen=True)
class Certified:
    xy: np.ndarray
    sampled: Sampled
    witnesses: dict            # 约束名 -> (最小余量, 最坏弦下标)
    ok: bool


def certify_and_sample(primitives, constraints, *, spacing_m):
    """采样图元并逐弦、逐约束做精确余量检查；所有弧长引用同一次采样结果。"""
    s = sample_primitives(primitives, spacing_m)
    wit = {}
    ok = True
    for c in constraints:
        m = polyline_clearance(c.geometry, s.xy, sense=c.sense, minimum_m=c.minimum_m)
        k = int(np.argmin(m))
        wit[c.name] = (float(m[k]), k)
        ok = ok and float(m[k]) >= 0.0
    return Certified(s.xy, s, wit, ok)


def bezier5_controls(p0, tangent0, p1, tangent1, h0, h1):
    """端点切向给定、端点曲率为零：P1 = P0 + h0 t0, P2 = P0 + 2 h0 t0, P3 = P5 − 2 h1 t1, P4 = P5 − h1 t1。"""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    t0, t1 = np.asarray(tangent0, float), np.asarray(tangent1, float)
    return (tuple(p0), tuple(p0 + h0 * t0), tuple(p0 + 2 * h0 * t0), tuple(p1 - 2 * h1 * t1), tuple(p1 - h1 * t1),
            tuple(p1))


def kappa_limit(spacing_m=0.5, max_turn_rad=0.2):
    """引导层 make_curve 的转角上限在 spacing 弦长下对应的曲率上限（留 5% 余量）。"""
    return 0.95 * max_turn_rad / spacing_m


def curvature_ok(kappa, spacing_m, max_turn_rad):
    return bool(np.all(np.abs(kappa) <= kappa_limit(spacing_m, max_turn_rad)))


def lane_curvature_ok(kpos, kneg, d, limit):
    """参考曲线最大正曲率 kpos(≥0)、最小负曲率 kneg(≤0) 下，左偏移 d 的车道曲率
    κ/(1−κd) 是否仍不超过 limit，且偏移不越过曲率中心。"""
    if d >= 0.0:
        if 1.0 - kpos * d <= 0.0:
            return False
        worst = max(kpos / (1.0 - kpos * d) if kpos > 0 else 0.0, -kneg / (1.0 - kneg * d) if kneg < 0 else 0.0)
    else:
        if 1.0 - kneg * d <= 0.0:
            return False
        worst = max(-kneg / (1.0 - kneg * d) if kneg < 0 else 0.0, kpos / (1.0 - kpos * d) if kpos > 0 else 0.0)
    return worst <= limit


def _bezier_batch(Ps, n_t):
    """一批五次 Bézier (G,6,2) 在 n_t 个等分参数上的位置、切向角、曲率。"""
    Ps = np.asarray(Ps, float)
    t = np.linspace(0.0, 1.0, n_t)[:, None]
    k = np.arange(6)[None]
    B = np.array([1, 5, 10, 10, 5, 1], float)[None] * t ** k * (1 - t) ** (5 - k)
    k4 = np.arange(5)[None]
    B4 = np.array([1, 4, 6, 4, 1], float)[None] * t ** k4 * (1 - t) ** (4 - k4)
    k3 = np.arange(4)[None]
    B3 = np.array([1, 3, 3, 1], float)[None] * t ** k3 * (1 - t) ** (3 - k3)
    d1c = 5 * (Ps[:, 1:] - Ps[:, :-1])
    d2c = 4 * (d1c[:, 1:] - d1c[:, :-1])
    pos = np.einsum("tk,gkd->gtd", B, Ps)
    d1 = np.einsum("tk,gkd->gtd", B4, d1c)
    d2 = np.einsum("tk,gkd->gtd", B3, d2c)
    th = np.arctan2(d1[..., 1], d1[..., 0])
    sp = np.hypot(d1[..., 0], d1[..., 1])
    kp = (d1[..., 0] * d2[..., 1] - d1[..., 1] * d2[..., 0]) / np.maximum(sp ** 3, 1e-300)
    return pos, th, kp


def connect_poses(p0, tangent0, p1, tangent1, corridor, key, *, spacing_m=0.5, max_turn_rad=0.2, grid=8,
                  screen_spacing_m=2.0, lane_shifts=(0.0,)):
    """五次 Bézier 姿态连接：h0、h1 在"走廊许可集合"中均匀抽取。

    许可集合 = 在 (0, 2·|P5−P0|] 的 grid×grid 个候选 (h0, h1) 中，曲率（在 2·长度/筛选间距 个等分参数上
    解析求值，含各车道偏移后的内侧曲率）不超过引导层转角上限，且 corridor(xy) 返回 True 的全部者；
    候选格只是搜索分辨率，不是业务长度。最终曲线仍按 spacing_m 加密并由调用方的精确弦检查验收。
    无许可者返回 None。
    """
    from ..sampler.keys import rng_for  # 惰性，避免循环导入

    rng = key if hasattr(key, "random") else rng_for(key)
    p0a, p1a = np.asarray(p0, float), np.asarray(p1, float)
    D = float(np.hypot(*(p1a - p0a)))
    if D <= 0:
        return None
    hs = D * np.linspace(0.0, 2.0, grid + 1)[1:]
    Ps = np.array([bezier5_controls(p0a, tangent0, p1a, tangent1, h0, h1) for h0 in hs for h1 in hs], float)
    n_t = int(min(max(math.ceil(3.0 * D / screen_spacing_m) + 2, 60), 600))
    pos, th, kp = _bezier_batch(Ps, n_t)
    limit = kappa_limit(spacing_m, max_turn_rad)
    good = []
    for g in range(len(Ps)):
        kpos, kneg = float(max(kp[g].max(), 0.0)), float(min(kp[g].min(), 0.0))
        if not all(lane_curvature_ok(kpos, kneg, d, limit) for d in lane_shifts):
            continue
        if corridor(pos[g]):
            good.append(tuple(map(tuple, Ps[g])))
    if not good:
        return None
    return ("bezier5", good[int(rng.integers(0, len(good)))])
