"""多样性度量（r3 14.3）：折线等弧长重采样、离散 Fréchet 距离与变异系数。

均为纯函数；Fréchet 用逐行动态规划迭代，不递归。
"""
import math

import numpy as np

_EPS = 1e-9


def _as_points(points, name="points"):
    try:
        a = np.asarray(points, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 无法转成浮点数组：{exc}") from None
    if a.ndim != 2:
        raise ValueError(f"{name} 必须是二维数组，实际 ndim={a.ndim}")
    if a.shape[0] < 1:
        raise ValueError(f"{name} 至少要有 1 个点")
    if a.shape[1] not in (2, 3):
        raise ValueError(f"{name} 列数必须是 2 或 3，实际 {a.shape[1]}")
    if not np.all(np.isfinite(a)):
        raise ValueError(f"{name} 含 NaN 或无穷")
    return a


def resample_polyline(points, spacing_m):
    p = _as_points(points)
    if p.shape[0] < 2:
        raise ValueError(f"折线至少要有 2 个点，实际 {p.shape[0]}")
    if isinstance(spacing_m, bool):
        raise ValueError("spacing_m 不得为布尔值")
    try:
        spacing = float(spacing_m)
    except (TypeError, ValueError):
        raise ValueError(f"spacing_m 不是数：{spacing_m!r}") from None
    if not math.isfinite(spacing) or spacing <= 0:
        raise ValueError(f"spacing_m 必须是有限正数：{spacing_m!r}")

    lens = np.linalg.norm(np.diff(p, axis=0), axis=1)
    cum = np.concatenate(([0.0], np.cumsum(lens)))
    total = float(cum[-1])
    if total == 0:
        return p[:1].copy()

    n = math.floor(total / spacing + _EPS)
    s_list = [min(k * spacing, total) for k in range(n + 1)]
    if total - s_list[-1] > _EPS:
        s_list.append(total)

    legs = np.flatnonzero(lens > 0)          # 跳过零长度腿
    leg_ends = cum[legs + 1]
    out = np.empty((len(s_list), p.shape[1]))
    for r, s in enumerate(s_list):
        j = min(int(np.searchsorted(leg_ends, s, side="left")), len(legs) - 1)
        i = legs[j]
        t = min(max((s - cum[i]) / lens[i], 0.0), 1.0)
        out[r] = p[i] + t * (p[i + 1] - p[i])
    return out


def discrete_frechet(P, Q):
    a = _as_points(P, "P")
    b = _as_points(Q, "Q")
    if a.shape[1] != b.shape[1]:
        raise ValueError(f"P、Q 维数不同：{a.shape[1]} 与 {b.shape[1]}")
    d = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)).tolist()
    n, m = len(d), len(d[0])

    prev = [0.0] * m
    prev[0] = d[0][0]
    for j in range(1, m):
        prev[j] = max(prev[j - 1], d[0][j])
    for i in range(1, n):
        row = d[i]
        cur = [0.0] * m
        cur[0] = max(prev[0], row[0])
        for j in range(1, m):
            cur[j] = max(min(prev[j], prev[j - 1], cur[j - 1]), row[j])
        prev = cur
    return float(prev[m - 1])


def pairwise_discrete_frechet(paths):
    paths = list(paths)
    if not paths:
        raise ValueError("paths 不能为空")
    arrs = [_as_points(x, f"paths[{i}]") for i, x in enumerate(paths)]
    k = len(arrs)
    out = np.zeros((k, k))
    for i in range(k):
        for j in range(i + 1, k):
            out[i, j] = out[j, i] = discrete_frechet(arrs[i], arrs[j])
    return out


def coefficient_of_variation(values):
    try:
        v = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"values 无法转成浮点数组：{exc}") from None
    if v.ndim != 1:
        raise ValueError(f"values 必须是一维数组，实际 ndim={v.ndim}")
    if v.size == 0:
        raise ValueError("values 不能为空")
    if not np.all(np.isfinite(v)):
        raise ValueError("values 含 NaN 或无穷")
    mean = float(np.mean(v))
    if mean <= 0:
        raise ValueError(f"均值必须为正，实际 {mean}")
    return float(np.std(v, ddof=0) / mean)
