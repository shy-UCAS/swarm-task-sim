"""突入单段的纯数值部分（V8-17 指令 3.2、3.4、3.6、3.7；本项新增）。

模块导入只依赖 NumPy 与标准库；场景几何（scene.exact、transit_chords、formation）一律在函数内部惰性导入，
使纯数值预置测试不被 shapely/真实场景绑住。

终点的三个条件（逐车道，车道 p0 + x u）：
  I_p = {x : SDF_protected ≤ −10}      U D.3.2：终点在保护层内至少 10 m；
  I_c = {x : SDF_contour ≤ 45}         U D.3.2：45 = 50 − 5（优化后终点阈值 50 的骨架工程余量）；
  x ≤ x_*（该车道 contour SDF 的全局最小点）  U D.3.2：不越过车道最深点。
E_i = I_p ∩ I_c ∩ (−∞, x_*]。不加任何 contour 距离下界（负距离合法），不沿用 r4 的 [−10, 25] m 旧约定。
"""
import math
from fractions import Fraction

import numpy as np

SIGMA_DEN = 20                    # U D.3.4：σ = k/20，k = 20, …, 1
SIGMA_MIN_SPACING_M = 6.0         # U D.3.4 / r5 6.8：σ·b ≥ 2 D_lane，D_lane = 3 m
PROTECTED_DEPTH_M = 10.0          # U D.3.2：终点 protected SDF ≤ −10
CONTOUR_SKELETON_M = 45.0         # U D.3.2：骨架终点 contour SDF ≤ 45（= 50 − 5）
PREENTRY_MARGIN_M = 10.0          # U D.3.1：进场全程在目标 warning 外 10 m


# ---------------------------------------------------------------- 精确最深点

def _poly_parts(geometry):
    from ..scene.exact import _poly
    a, d, _len2, length = _poly(geometry)
    return np.asarray(a, float), np.asarray(d, float), np.asarray(length, float)


def deepest_station(geometry, p0, u):
    """单位方向直线 p0+x*u 上 SDF 的全局最小点；并列取最小 x。

    圆：x_* = uᵀ(c − p0)。凸多边形（含 BufferedPolygon：SDF = 原多边形 SDF − buffer，argmin 不变）：
    直线穿过原多边形时，内部到边界距离 = min_j (a_j x + b_j)（a_j = cross(e_j, u)/|e_j|，
    b_j = cross(e_j, p0 − v_j)/|e_j|），在交区间两端及所有斜率不同的两条仿射式交点中枚举该凹分段线性函数的最大值，
    等值取最小 x（一维精确极值枚举，无迭代容差）。不穿过时逐边求"无限直线到线段"的最近点（非平行取解析解并裁到
    [0, 1]；平行取投影 x 较小的端点），距离最小者并列取最小 x。"""
    from ..scene.exact import _circle, kind_of
    p0 = np.asarray(p0, float)[:2]
    u = np.asarray(u, float)[:2]
    t = kind_of(geometry)
    if t == "Circle":
        c, _r = _circle(geometry)
        return float(u[0] * (c[0] - p0[0]) + u[1] * (c[1] - p0[1]))
    from .transit_chords import _halfplanes_many
    a, d, length = _poly_parts(geometry)
    lo, hi = _halfplanes_many(p0[None], u, a, d, length, 0.0)
    if not np.isnan(lo[0]):
        lo, hi = float(lo[0]), float(hi[0])
        slope = (d[:, 0] * u[1] - d[:, 1] * u[0]) / length
        icpt = (d[:, 0] * (p0[1] - a[:, 1]) - d[:, 1] * (p0[0] - a[:, 0])) / length
        J, K = np.triu_indices(len(slope), 1)
        ds = slope[J] - slope[K]
        ok = ds != 0.0
        xs = (icpt[K][ok] - icpt[J][ok]) / ds[ok]
        xs = xs[(lo <= xs) & (xs <= hi)]
        cands = np.unique(np.r_[lo, hi, xs])                    # 升序；逐点包络值与逐个计算同一浮点运算
        vals = np.min(slope[:, None] * cands[None, :] + icpt[:, None], axis=0)
        return float(cands[int(np.argmax(vals))])               # argmax 取第一个最大值 ⇒ 并列取最小 x
    nrm = np.array([-u[1], u[0]])
    best = None
    for j in range(len(a)):
        v, e = a[j], d[j]
        ne = float(nrm @ e)
        w = v - p0
        if ne != 0.0:
            tt = min(1.0, max(0.0, -float(nrm @ w) / ne))
            pts = [v + tt * e]
        else:
            pts = [v, v + e]
        for q in pts:
            dist = abs(float(nrm @ (q - p0)))
            x = float(u @ (q - p0))
            if best is None or dist < best[0] or (dist == best[0] and x < best[1]):
                best = (dist, x)
    return float(best[1])


# ---------------------------------------------------------------- 终点区间

def endpoint_interval(contour, protected, p0, u):
    """返回三个条件相交的闭区间 (lo, hi)，空为 None；不设 contour 下界。
    I_p（U D.3.2 保护层内 ≥ 10 m）∩ I_c（U D.3.2 contour ≤ 45）∩ (−∞, x_*]（U D.3.2 不越过最深点）。
    闭区间相交只取左端最大、右端最小；单点集合法（附录裁定 2 切线例）。"""
    from .transit_chords import line_sublevel
    I_p = line_sublevel(protected, p0, u, -PROTECTED_DEPTH_M)
    if I_p is None:
        return None
    I_c = line_sublevel(contour, p0, u, CONTOUR_SKELETON_M)
    if I_c is None:
        return None
    return endpoint_from_parts(I_p, I_c, deepest_station(contour, p0, u))


def endpoint_from_parts(I_p, I_c, x_star):
    """E = I_p ∩ I_c ∩ (−∞, x_*]（三者均非空时）；闭区间相交只取左端最大、右端最小，单点合法，空为 None。"""
    lo = max(I_p[0], I_c[0])
    hi = min(I_p[1], I_c[1], x_star)
    if not lo <= hi:
        return None
    return (float(lo), float(hi))


def sigma_values(spacing_m, formation):
    """降序 tuple；abreast 只有 1.0，其余为 k/20 且 sigma*b >= 6。"""
    if formation == "abreast":
        return (1.0,)
    b = float(spacing_m)
    return tuple(k / SIGMA_DEN for k in range(SIGMA_DEN, 0, -1) if (k / SIGMA_DEN) * b >= SIGMA_MIN_SPACING_M)


def normalize_intervals(intervals):
    """按左端排序并合并重叠（含首尾相接）区间；单点保留；返回 tuple[(lo, hi)]（Python float）。"""
    iv = sorted((float(a), float(b)) for a, b in intervals if a <= b)
    out = []
    for a, b in iv:
        if out and a <= out[-1][1]:
            if b > out[-1][1]:
                out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return tuple(out)


def intersect_two(A, B):
    """两个规范化区间并的交（闭区间）。"""
    out, i, j = [], 0, 0
    while i < len(A) and j < len(B):
        lo, hi = max(A[i][0], B[j][0]), min(A[i][1], B[j][1])
        if lo <= hi:
            out.append((lo, hi))
        if A[i][1] < B[j][1]:
            i += 1
        else:
            j += 1
    return normalize_intervals(out)


def intersect_endpoint_sets(lane_sets, longitudinal_m, sigma):
    """各成员闭区间并先平移 -sigma*l_i 再求交，返回规范化 tuple[(lo,hi),...]。"""
    acc = None
    for sets, l in zip(lane_sets, longitudinal_m):
        shift = float(sigma) * float(l)
        cur = normalize_intervals([(lo - shift, hi - shift) for lo, hi in sets])
        acc = cur if acc is None else intersect_two(acc, cur)
        if not acc:
            return ()
    return () if acc is None else acc


def prefix_endpoint_set(sub, start):
    """已知起点在其他 warning 外10m；由其±10次水平区间求合法前向终点区间并。

    sub = {10.0: B_{+10} 或 None, -10.0: B_{−10} 或 None}（车道坐标闭区间）。起点在 +10 区间右侧：前向不再遇到它；
    在左侧：(−∞, B+10_lo] ∪ [B−10_lo, B−10_hi] ∪ [B+10_hi, +∞)（后两段仅 B−10 非空时存在：尚未靠近、终点深在圈内、
    已完整穿出），再与 [start, +∞) 相交。+10 区间为空或只有切点时整条线 SDF ≥ 10，不限制。
    返回 tuple[(lo, hi)]，hi 可为 +inf（运算哨兵；调用方与有界 E_i 相交后才写入缓存/合同）。"""
    s = float(start)
    B = sub.get(10.0)
    if B is None or not B[1] > B[0]:
        return ((s, math.inf),)
    if s >= B[1]:
        return ((s, math.inf),)
    if s > B[0]:
        return ()                                         # 起点落在 +10 带内：与前提矛盾，不给合法终点
    parts = [(s, float(B[0]))]
    C = sub.get(-10.0)
    if C is not None:
        parts.append((max(s, float(C[0])), float(C[1])))
        parts.append((float(B[1]), math.inf))
    return normalize_intervals([(a, b) for a, b in parts if a <= b])


# ---------------------------------------------------------------- 抽样（U D.3.4）

def _contains(intervals, x):
    return any(lo <= x <= hi for lo, hi in intervals)


def draw_feasible(cells, rng):
    """只抽一次格、sigma、终点，然后在与该终点相容的 D 中抽一次。

    顺序固定：rng.integers(0, len(cells)) 均匀取格（不按 σ 数或区间长度加权）→ 该格 choices 中均匀取 σ →
    rng.random() 按规范化 J_σ 的总长度映射到区间并（终点的长度均匀分布；总长为 0 时在唯一化孤立点中离散均匀取）→
    在包含 x_e 的 by_collect_D 中均匀取 D_c（空为实现错误，抛 RuntimeError，不重抽终点）。"""
    ci = int(rng.integers(0, len(cells)))
    cell = cells[ci]
    choices = cell["choices"]
    si = int(rng.integers(0, len(choices)))
    ch = choices[si]
    J = normalize_intervals([tuple(iv) for iv in ch["intervals"]])
    if not J:
        raise RuntimeError("可行格的终点区间并为空（实现错误）")
    total = float(sum(hi - lo for lo, hi in J))
    q = float(rng.random())
    if total > 0.0:
        t = q * total
        cum = 0.0
        x_e = None
        pos = [(lo, hi) for lo, hi in J if hi > lo]
        for lo, hi in pos:
            ln = hi - lo
            if t <= cum + ln:
                x_e = min(hi, lo + (t - cum))
                break
            cum += ln
        if x_e is None:
            x_e = pos[-1][1]
    else:
        pts = sorted({lo for lo, _ in J})
        x_e = pts[min(int(q * len(pts)), len(pts) - 1)]
    compat = [(float(D), iv) for D, iv in ch["by_collect_D"] if _contains([tuple(v) for v in iv], x_e)]
    if not compat:
        raise RuntimeError(f"终点 {x_e!r} 不在任何 D_c 子集合中（实现错误）")
    di = int(rng.integers(0, len(compat)))
    return {"cell_index": ci, "theta_idx": cell.get("theta_idx"), "h_m": cell.get("h_m"), "x_in": cell.get("x_in"),
            "sigma_index": si, "sigma": float(ch["sigma"]), "sigmas_feasible": len(choices),
            "x_e": float(x_e), "endpoint_total_length_m": total, "endpoint_quantile": q,
            "collect_D_m": compat[di][0], "collect_candidates": len(compat), "cell": cell}


# ---------------------------------------------------------------- 进场精确检查

def preentry_clearance_ok(warning, xy, margin_m=PREENTRY_MARGIN_M):
    """逐弦精确检查进场折线在目标 warning 外达到给定余量。等号合法；单点直接查 SDF ≥ margin；空路线不合法。"""
    from ..scene.exact import polyline_clearance, signed_distance
    P = np.asarray(xy, float)
    if P.ndim != 2 or len(P) == 0:
        return False
    if len(P) == 1:
        return bool(float(signed_distance(warning, P[0, :2])) >= float(margin_m))
    m = polyline_clearance(warning, P[:, :2], sense=1, minimum_m=float(margin_m), fast_far_m=None)
    return bool(np.all(np.asarray(m, float) >= 0.0))


# ---------------------------------------------------------------- 必要条件证书（3.7）

def circle_infeasibility_certificate(contour, protected, member_count, spacing_m):
    """仅返回数学必要条件证书；不成立或不适用时为 None。

    只用于同心圆 contour/protected：Q = min(R + 45, R_p − 10)，σ_min = min{σ ∈ Σ : σ b ≥ 6}。全部终点因"不过最深点"
    在 x ∈ [−Q, 0]、y ∈ [−Q, Q]：横排必要条件 (N−1) b ≤ 2Q；纵列、任意横向步长的梯形必要条件 (N−1) σ_min b ≤ Q。
    三种队形全被否定才给证书。这是规定 σ 网格下的几何证书，不是对任意连续 σ 的不可能性证明。"""
    if not (isinstance(contour, dict) and isinstance(protected, dict)):
        return None
    if contour.get("type") != "Circle" or protected.get("type") != "Circle":
        return None
    c0 = [float(v) for v in contour["center_m"]]
    c1 = [float(v) for v in protected["center_m"]]
    if c0 != c1:
        return None
    N = int(member_count)
    if N < 2:
        return None
    R, Rp, b = float(contour["radius_m"]), float(protected["radius_m"]), float(spacing_m)
    Q = min(R + CONTOUR_SKELETON_M, Rp - PROTECTED_DEPTH_M)
    sig = sigma_values(b, "column")
    if not sig:
        sigma_min = None
        long_span = None
        long_ok = False                                  # 没有可用 σ：纵列/梯形在网格下无终点
    else:
        sigma_min = min(sig)
        long_span = (N - 1) * sigma_min * b
        long_ok = long_span <= Q
    lat_span = (N - 1) * b
    lat_ok = lat_span <= 2.0 * Q
    if lat_ok or long_ok:
        return None
    return {"kind": "circle_endpoint_necessary_condition_v17",
            "inputs": {"contour": contour, "protected": protected, "member_count": N, "spacing_m": b},
            "Q_m": Q, "Q_formula": "min(R + 45, R_p - 10)", "R_m": R, "R_p_m": Rp,
            "sigma_grid": [float(s) for s in sig], "sigma_min": sigma_min,
            "formations": {
                "abreast": {"span_m": lat_span, "bound_m": 2.0 * Q, "formula": "(N-1) b <= 2Q", "possible": False},
                "column": {"span_m": long_span, "bound_m": Q, "formula": "(N-1) sigma_min b <= Q", "possible": False},
                "echelon": {"span_m": long_span, "bound_m": Q, "formula": "(N-1) sigma_min b <= Q（任意横向步长）",
                            "possible": False}},
            "scope": "规定 σ 网格（k/20 且 σ b ≥ 6）下的必要条件证书；不证明连续 σ 也不可能"}


# ---------------------------------------------------------------- 成员域（3.6 第 2 步）

def clip_lanes(reference, slots, s_collect, s_end, sigma, *, spacing_m):
    """对每个成员用仅含该成员的 Slots 调用原 derive_members，station_offsets = (s_c, s_e + (σ−1) l_i)：
    成员域 [s_c + l_i, s_e + σ l_i]。不修改 derive_members，不把途中纵向偏移乘 σ。"""
    from dataclasses import replace
    from .formation import derive_members
    out = {}
    for m in slots.order:
        l, _d = slots.offsets[m]
        single = replace(slots, order=(m,), offsets={m: slots.offsets[m]})
        got = derive_members(reference, single, (float(s_collect), float(s_end) + (float(sigma) - 1.0) * float(l)),
                             spacing_m=spacing_m)
        out[m] = got[m]
    return out


def endpoint_distances(slots, sigma):
    """终点两两距离 sqrt([σ(l_i − l_j)]² + (d_i − d_j)²)（构造性质，只记录，不作拒绝）。"""
    order = list(slots.order)
    out = []
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            li, di = slots.offsets[order[i]]
            lj, dj = slots.offsets[order[j]]
            out.append(math.hypot(float(sigma) * (li - lj), di - dj))
    return out


def fraction_str(num, den):
    f = Fraction(num, den)
    return f"{f.numerator}/{f.denominator}"
