"""平面 ENU 精确有符号距离（V8-12 第 2 部分；NumPy，不导入 shapely）。

内部为负、边界为零。支持 Circle、凸 Polygon、BufferedPolygon（凸多边形的 Minkowski 和，保留圆角）。
凸形状的有符号距离是凸函数：沿线段的最大值在端点，最小值在投影点（外部）或不超过 0（穿过内部）。
这里只做数学计算，不含任何业务阈值。
"""
import math
from functools import lru_cache

import numpy as np

SENSES = (-1, 0, 1)   # +1 要在外部；-1 要在内部；0 要离边界至少 minimum_m（内外皆可）
_CHUNK = 1 << 17


class GeometryError(ValueError):
    """输入几何退化、非凸或含非有限值。"""


def _points(xy):
    a = np.asarray(xy, dtype=float)
    if a.ndim == 1:
        if a.shape[0] < 2:
            raise GeometryError("点至少需要两个坐标")
        return a[None, :2], ()
    if a.ndim < 2 or a.shape[-1] < 2:
        raise GeometryError("点数组的最后一维至少为 2")
    shape = a.shape[:-1]
    return a.reshape(-1, a.shape[-1])[:, :2], shape


@lru_cache(maxsize=4096)
def _convex(vertices):
    """校验并规整为逆时针顶点；返回 (a, d, len2, length)。"""
    v = np.array(vertices, dtype=float)
    if v.ndim != 2 or v.shape[1] != 2 or v.shape[0] < 3 or not np.all(np.isfinite(v)):
        raise GeometryError("多边形至少 3 个有限顶点")
    d = np.roll(v, -1, axis=0) - v
    length = np.hypot(d[:, 0], d[:, 1])
    if np.any(length <= 0.0):
        raise GeometryError("多边形含零长度边")
    area2 = float(np.sum(v[:, 0] * np.roll(v[:, 1], -1) - np.roll(v[:, 0], -1) * v[:, 1]))
    if area2 == 0.0:
        raise GeometryError("多边形面积为 0")
    if area2 < 0.0:
        v = v[::-1].copy()
        d = np.roll(v, -1, axis=0) - v
        length = np.hypot(d[:, 0], d[:, 1])
    cross = d[:, 0] * np.roll(d[:, 1], -1) - d[:, 1] * np.roll(d[:, 0], -1)
    scale = length * np.roll(length, -1)
    if np.any(cross < -1e-9 * scale):
        raise GeometryError("多边形不是凸的")
    for arr in (v, d, length):
        arr.setflags(write=False)
    return v, d, length * length, length


def _poly(geometry):
    try:
        key = tuple((float(x), float(y)) for x, y in geometry["vertices_m"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GeometryError(f"多边形缺少 vertices_m：{exc}") from None
    return _convex(key)


def _buffer(geometry):
    b = float(geometry.get("buffer_m", 0.0)) if geometry["type"] == "BufferedPolygon" else 0.0
    if not math.isfinite(b) or b < 0.0:
        raise GeometryError("buffer_m 须为非负有限数")
    return b


def kind_of(geometry):
    t = geometry.get("type") if isinstance(geometry, dict) else None
    if t not in ("Circle", "Polygon", "BufferedPolygon"):
        raise GeometryError(f"不支持的几何类型：{t!r}")
    return t


def _circle(geometry):
    c = np.asarray(geometry["center_m"], dtype=float)
    r = float(geometry["radius_m"])
    if c.shape != (2,) or not np.all(np.isfinite(c)) or not math.isfinite(r) or r <= 0.0:
        raise GeometryError("圆需要有限圆心和正半径")
    return c, r


# ---------------------------------------------------------------- 点

def _poly_sdf(P, pts):
    a, d, len2, _ = P
    out = np.empty(len(pts))
    for lo in range(0, len(pts), max(1, _CHUNK // max(1, len(a)))):
        q = pts[lo:lo + max(1, _CHUNK // max(1, len(a)))]
        rel = q[:, None, :] - a[None, :, :]
        u = np.clip(np.sum(rel * d[None], axis=2) / len2[None], 0.0, 1.0)
        near = rel - u[..., None] * d[None]
        dist = np.sqrt(np.sum(near * near, axis=2)).min(axis=1)
        cross = d[None, :, 0] * rel[..., 1] - d[None, :, 1] * rel[..., 0]
        inside = np.all(cross >= 0.0, axis=1)
        out[lo:lo + len(q)] = np.where(inside, -dist, dist)
    return out


def signed_distance(geometry, xy):
    """点到轮廓的有符号距离；xy 的形状为 (..., 2 或 3)，返回形状 (...)。"""
    pts, shape = _points(xy)
    t = kind_of(geometry)
    if t == "Circle":
        c, r = _circle(geometry)
        out = np.hypot(pts[:, 0] - c[0], pts[:, 1] - c[1]) - r
    else:
        out = _poly_sdf(_poly(geometry), pts) - _buffer(geometry)
    return out.reshape(shape) if shape else float(out[0])


def polygon_centroid(vertices_m):
    """面积质心（鞋带公式），与顶点方向无关。"""
    v = np.asarray(vertices_m, dtype=float)
    x, y = v[:, 0], v[:, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    w = x * y1 - x1 * y
    area = 0.5 * float(w.sum())
    if area == 0.0:
        raise GeometryError("面积为 0，无面积质心")
    return (float(np.sum((x + x1) * w) / (6.0 * area)), float(np.sum((y + y1) * w) / (6.0 * area)))


def center_of_geometry(geometry):
    if kind_of(geometry) == "Circle":
        c, _ = _circle(geometry)
        return (float(c[0]), float(c[1]))
    return polygon_centroid(geometry["vertices_m"])


def clearance_values(geometry, xy, *, sense, minimum_m):
    """逐点余量：sense*sdf − minimum（sense=0 时为 |sdf| − minimum）；≥ 0 为可行。"""
    s = signed_distance(geometry, xy)
    if sense == 0:
        return np.abs(s) - minimum_m
    if sense not in (-1, 1):
        raise GeometryError(f"sense 须为 -1、0、+1：{sense!r}")
    return sense * s - minimum_m


# ---------------------------------------------------------------- 线段

def _seg_point_dist(p, a, b):
    """点 p (…,2) 到线段 ab (…,2) 的距离（广播）。"""
    ab = b - a
    den = np.sum(ab * ab, axis=-1)
    t = np.where(den > 0, np.sum((p - a) * ab, axis=-1) / np.where(den > 0, den, 1.0), 0.0)
    t = np.clip(t, 0.0, 1.0)
    q = a + t[..., None] * ab
    return np.hypot(p[..., 0] - q[..., 0], p[..., 1] - q[..., 1])


def chord_sdf_range(geometry, a, b):
    """线段 a→b（数组 (S,2)）上 sdf 的取值范围 (lo, hi, lo_exact)。

    hi 总是精确的（凸函数的最大值在端点）。lo 在线段与形状不相交时精确；相交时只给出
    上界 min(端点值, 0)，lo_exact=False，此时线段必然进入形状内部。
    """
    A = np.atleast_2d(np.asarray(a, dtype=float))[:, :2]
    B = np.atleast_2d(np.asarray(b, dtype=float))[:, :2]
    t = kind_of(geometry)
    if t == "Circle":
        c, r = _circle(geometry)
        ab = B - A
        den = np.sum(ab * ab, axis=1)
        u = np.where(den > 0, np.sum((c - A) * ab, axis=1) / np.where(den > 0, den, 1.0), 0.0)
        q = A + np.clip(u, 0.0, 1.0)[:, None] * ab
        dmin = np.hypot(q[:, 0] - c[0], q[:, 1] - c[1])
        dmax = np.maximum(np.hypot(A[:, 0] - c[0], A[:, 1] - c[1]), np.hypot(B[:, 0] - c[0], B[:, 1] - c[1]))
        return dmin - r, dmax - r, np.ones(len(A), bool)
    P = _poly(geometry)
    bf = _buffer(geometry)
    va, d, len2, _ = P
    fa = _poly_sdf(P, A)
    fb = _poly_sdf(P, B)
    hi = np.maximum(fa, fb)
    # Cyrus–Beck 裁剪：线段是否与闭凸多边形相交
    ab = B - A
    num = d[None, :, 0] * (A[:, None, 1] - va[None, :, 1]) - d[None, :, 1] * (A[:, None, 0] - va[None, :, 0])
    den = d[None, :, 0] * ab[:, None, 1] - d[None, :, 1] * ab[:, None, 0]
    with np.errstate(divide="ignore", invalid="ignore"):
        tt = -num / den
    pos, neg, zer = den > 0, den < 0, den == 0
    tlo = np.maximum(0.0, np.max(np.where(pos, tt, -np.inf), axis=1))
    thi = np.minimum(1.0, np.min(np.where(neg, tt, np.inf), axis=1))
    parallel_out = np.any(zer & (num < 0), axis=1)
    inter = (tlo <= thi) & ~parallel_out
    # 不相交时：线段到多边形的距离 = 四类端点到边距离的最小值
    ea, eb = va[None, :, :], (va + d)[None, :, :]
    d1 = _seg_point_dist(A[:, None, :], ea, eb)
    d2 = _seg_point_dist(B[:, None, :], ea, eb)
    d3 = _seg_point_dist(ea, A[:, None, :], B[:, None, :])
    d4 = _seg_point_dist(eb, A[:, None, :], B[:, None, :])
    dist = np.minimum(np.minimum(d1, d2), np.minimum(d3, d4)).min(axis=1)
    lo = np.where(inter, np.minimum(np.minimum(fa, fb), 0.0), dist)
    return lo - bf, hi - bf, ~inter


def margin_from_range(lo, hi, *, sense, minimum_m):
    lo, hi = np.asarray(lo), np.asarray(hi)
    if sense == 1:
        return lo - minimum_m
    if sense == -1:
        return -hi - minimum_m
    if sense != 0:
        raise GeometryError(f"sense 须为 -1、0、+1：{sense!r}")
    return np.where(lo >= 0.0, lo - minimum_m, np.where(hi <= 0.0, -hi - minimum_m, -minimum_m))


def segment_clearance(geometry, a, b, *, sense, minimum_m):
    """整条线段的最小余量 margin（≥ 0 表示整条弦可行）。外部约束在线段与形状相交时只是上界，仍为负。"""
    lo, hi, _ = chord_sdf_range(geometry, np.asarray(a, float)[None], np.asarray(b, float)[None])
    return float(margin_from_range(lo, hi, sense=sense, minimum_m=minimum_m)[0])


def polyline_clearance(geometry, xy, *, sense, minimum_m):
    """折线每条弦的最小余量，形状 (N−1,)。折线本身就是被飞的参考曲线，逐弦检查即检查整条曲线。"""
    P = np.asarray(xy, dtype=float)[:, :2]
    lo, hi, _ = chord_sdf_range(geometry, P[:-1], P[1:])
    return margin_from_range(lo, hi, sense=sense, minimum_m=minimum_m)


def expand(geometry, distance_m):
    """向外膨胀 distance_m（Minkowski 和）；保留圆角。distance_m 为 0 时原样返回。"""
    if not math.isfinite(distance_m) or distance_m < 0.0:
        raise GeometryError("膨胀距离须为非负有限数")
    t = kind_of(geometry)
    if distance_m == 0.0:
        return geometry
    if t == "Circle":
        return {"type": "Circle", "center_m": list(geometry["center_m"]),
                "radius_m": float(geometry["radius_m"]) + distance_m}
    if t == "Polygon":
        return {"type": "BufferedPolygon", "vertices_m": [list(p) for p in geometry["vertices_m"]],
                "buffer_m": distance_m}
    return {**geometry, "buffer_m": float(geometry["buffer_m"]) + distance_m}


def inset_convex(vertices_m, margin_m):
    """凸多边形向内收缩 margin_m：各边内移后相邻直线求交。收缩后退化则抛 GeometryError。"""
    v, d, _, length = _convex(tuple((float(x), float(y)) for x, y in vertices_m))
    n = np.stack([-d[:, 1], d[:, 0]], axis=1) / length[:, None]   # 逆时针时的内法向
    p = v + n * margin_m
    out = []
    E = len(v)
    for i in range(E):
        j = (i - 1) % E
        # 第 j 条边与第 i 条边的内移直线交点
        di, dj = d[i], d[j]
        den = dj[0] * di[1] - dj[1] * di[0]
        if abs(den) < 1e-12 * length[i] * length[j]:
            raise GeometryError("相邻边平行，无法收缩")
        w = p[i] - p[j]
        s = (w[0] * di[1] - w[1] * di[0]) / den
        out.append(p[j] + s * dj)
    out = np.array(out)
    area2 = float(np.sum(out[:, 0] * np.roll(out[:, 1], -1) - np.roll(out[:, 0], -1) * out[:, 1]))
    if area2 <= 0.0:
        raise GeometryError("收缩后多边形退化")
    return [[float(x), float(y)] for x, y in out]


def bounding_box(geometry):
    t = kind_of(geometry)
    if t == "Circle":
        c, r = _circle(geometry)
        return (float(c[0] - r), float(c[1] - r), float(c[0] + r), float(c[1] + r))
    v = np.asarray(geometry["vertices_m"], dtype=float)
    b = _buffer(geometry)
    return (float(v[:, 0].min() - b), float(v[:, 1].min() - b), float(v[:, 0].max() + b), float(v[:, 1].max() + b))
