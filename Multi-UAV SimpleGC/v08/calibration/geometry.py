"""标定用的合成几何（V8-06 2.2）：直线、圆弧、掉头形状、极坐标闭合曲线，以及点到几何的距离。

几何元素用元组表示：("line", p0, p1) 与 ("arc", center, R, theta0, dtheta)。只在平面上计算。
"""
import math

import numpy as np

TWO_PI = 2.0 * math.pi
DEDUP_TOL_M = 1e-9


def line(p0, p1):
    return ("line", (float(p0[0]), float(p0[1])), (float(p1[0]), float(p1[1])))


def arc(center, R, theta0, dtheta):
    return ("arc", (float(center[0]), float(center[1])), float(R), float(theta0), float(dtheta))


def arc_points(center, R, theta0, dtheta, spacing):
    n = max(1, math.ceil(R * abs(dtheta) / spacing - 1e-9))
    th = theta0 + dtheta * np.arange(n + 1) / n
    return np.c_[center[0] + R * np.cos(th), center[1] + R * np.sin(th)]


def _arc_end(center, R, theta):
    return (center[0] + R * math.cos(theta), center[1] + R * math.sin(theta))


def build_waypoints(prims, spacing, alt):
    pts = []
    for prim in prims:
        if prim[0] == "line":
            seg = [prim[1], prim[2]]
        elif prim[0] == "arc":
            _, c, R, th0, dth = prim
            seg = arc_points(c, R, th0, dth, spacing).tolist()
        else:
            raise ValueError(f"未知几何元素 {prim[0]!r}")
        for q in seg:
            q = (float(q[0]), float(q[1]))
            if pts and math.hypot(q[0] - pts[-1][0], q[1] - pts[-1][1]) <= DEDUP_TOL_M:
                continue
            pts.append(q)
    W = np.empty((len(pts), 3))
    W[:, :2] = pts
    W[:, 2] = float(alt)
    return W


def shape_turn(R, dtheta_deg, leg_in, leg_out):
    dth = math.radians(dtheta_deg)
    th_end = -math.pi / 2 + dth
    E = _arc_end((0.0, R), R, th_end)
    t = (-math.sin(th_end), math.cos(th_end))          # 逆时针方向的单位切向
    return [line((-leg_in, 0.0), (0.0, 0.0)),
            arc((0.0, R), R, -math.pi / 2, dth),
            line(E, (E[0] + leg_out * t[0], E[1] + leg_out * t[1]))]


def shape_teardrop(R, leg):
    return [line((-leg, 0.0), (0.0, 0.0)),
            arc((0.0, -R), R, math.pi / 2, -math.pi / 2),
            arc((2 * R, -R), R, math.pi, 1.5 * math.pi),
            line((2 * R, 0.0), (2 * R - leg, 0.0))]


def path_length(prims):
    total = 0.0
    for prim in prims:
        if prim[0] == "line":
            total += math.hypot(prim[2][0] - prim[1][0], prim[2][1] - prim[1][1])
        else:
            total += prim[2] * abs(prim[4])
    return total


def _xy(points):
    a = np.asarray(points, dtype=float)
    if a.ndim == 1:
        a = a[None, :]
    return a[:, :2]


def _segment_distance(xy, a, b):
    a = np.asarray(a, dtype=float)
    d = np.asarray(b, dtype=float) - a
    dd = float(d @ d)
    rel = xy - a
    if dd == 0.0:
        return np.linalg.norm(rel, axis=1)
    t = np.clip(rel @ d / dd, 0.0, 1.0)
    return np.linalg.norm(rel - t[:, None] * d, axis=1)


def arc_relative_angle(xy, center, theta0, dtheta):
    """点相对圆心的方位，沿圆弧扫过方向从 theta0 量起，取值 [0, 2π)。"""
    ang = np.arctan2(xy[:, 1] - center[1], xy[:, 0] - center[0])
    rel = (ang - theta0) if dtheta >= 0 else (theta0 - ang)
    return np.mod(rel, TWO_PI)


def _arc_distance(xy, prim):
    _, c, R, th0, dth = prim
    inside = arc_relative_angle(xy, c, th0, dth) <= abs(dth)
    radial = np.abs(np.linalg.norm(xy - np.asarray(c), axis=1) - R)
    e0 = np.asarray(_arc_end(c, R, th0))
    e1 = np.asarray(_arc_end(c, R, th0 + dth))
    ends = np.minimum(np.linalg.norm(xy - e0, axis=1), np.linalg.norm(xy - e1, axis=1))
    return np.where(inside, radial, ends)


def distance_to_path(xy, prims):
    xy = _xy(xy)
    out = np.full(len(xy), np.inf)
    for prim in prims:
        d = _segment_distance(xy, prim[1], prim[2]) if prim[0] == "line" else _arc_distance(xy, prim)
        np.minimum(out, d, out=out)
    return out


def distance_to_polyline(xy, W):
    xy = _xy(xy)
    w = np.asarray(W, dtype=float)[:, :2]
    out = np.full(len(xy), np.inf)
    if len(xy) == 0:
        return out
    # 按腿分块向量化：每块 (点, 腿) 的距离矩阵不超过约 4e6 个元素
    a, d = w[:-1], np.diff(w, axis=0)
    dd = np.einsum("ij,ij->i", d, d)
    safe = np.where(dd > 0.0, dd, 1.0)
    step = max(1, 4_000_000 // len(xy))
    for k in range(0, len(a), step):
        rel = xy[:, None, :] - a[None, k:k + step]
        t = np.clip(np.einsum("pkj,kj->pk", rel, d[k:k + step]) / safe[k:k + step], 0.0, 1.0)
        t = np.where(dd[k:k + step] > 0.0, t, 0.0)
        dist = np.linalg.norm(rel - t[..., None] * d[None, k:k + step], axis=2)
        np.minimum(out, dist.min(axis=1), out=out)
    return out


# ---------------------------------------------------------------- 极坐标闭合曲线

def _polar_terms(rho0, harmonics, phi):
    phi = np.asarray(phi, dtype=float)
    r = np.full_like(phi, float(rho0))
    r1 = np.zeros_like(phi)
    r2 = np.zeros_like(phi)
    for a, k, psi in harmonics:
        arg = k * phi + psi
        r = r + a * np.cos(arg)
        r1 = r1 - a * k * np.sin(arg)
        r2 = r2 - a * k * k * np.cos(arg)
    return r, r1, r2


def polar_radius(rho0, harmonics, phi):
    return _polar_terms(rho0, harmonics, phi)[0]


def polar_curvature(rho0, harmonics, phi):
    r, r1, r2 = _polar_terms(rho0, harmonics, phi)
    return (r * r + 2.0 * r1 * r1 - r * r2) / (r * r + r1 * r1) ** 1.5


def _polar_xy(rho0, harmonics, phi):
    r = polar_radius(rho0, harmonics, phi)
    return np.c_[r * np.cos(phi), r * np.sin(phi)]


def _polar_dense(rho0, harmonics, phi0, dphi, dense_per_rad):
    m = max(2, math.ceil(abs(dphi) * dense_per_rad) + 1)
    phis = np.linspace(phi0, phi0 + dphi, m)
    P = _polar_xy(rho0, harmonics, phis)
    s = np.concatenate(([0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))))
    return phis, s


def polar_loop_points(rho0, harmonics, phi0, dphi, spacing, dense_per_rad=4000):
    phis_d, s_d = _polar_dense(rho0, harmonics, phi0, dphi, dense_per_rad)
    L = float(s_d[-1])
    targets = []
    k = 0
    while k * spacing < L - 1e-9:
        targets.append(k * spacing)
        k += 1
    if not targets or L - targets[-1] > 1e-9:
        targets.append(L)
    phis = np.interp(targets, s_d, phis_d)
    return _polar_xy(rho0, harmonics, phis), phis


def polar_loop_points_adaptive(rho0, harmonics, phi0, dphi, spacing_fn, dense_per_rad=4000):
    phis_d, s_d = _polar_dense(rho0, harmonics, phi0, dphi, dense_per_rad)
    L = float(s_d[-1])
    targets = []
    s = 0.0
    while True:
        targets.append(s)
        phi = float(np.interp(s, s_d, phis_d))
        R = 1.0 / max(abs(float(polar_curvature(rho0, harmonics, phi))), 1e-12)
        s = s + float(spacing_fn(R))
        if s >= L - 1e-9:
            break
    if L - targets[-1] > 1e-9:
        targets.append(L)
    phis = np.interp(targets, s_d, phis_d)
    return _polar_xy(rho0, harmonics, phis), phis


def interp_log(R, table_R, table_v):
    return np.interp(np.log(R), np.log(table_R), table_v)
