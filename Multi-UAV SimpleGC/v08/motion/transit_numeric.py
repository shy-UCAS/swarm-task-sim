"""过境单段的纯数值部分（V8-16 指令 3.4–3.5；本项新增）。不导入 shapely，不读场景。

一、离散误差（grid_error_m）
    field_eps_m = hypot(Δ, Δ)/2：DistanceField.lower_clearance 已经扣除的双线性误差，调用方不得重复扣；
    sampling_q_m = hypot(dx/2, dy/2)：采样格到连续点的覆盖半径（1-Lipschitz 余量函数据此保证格内连续成立）。

二、夹持三次 B 样条曲线 LP（curve_lp）
    δ(x) = Σ_j c_j B_j(x)，x ∈ [x0, x1]（行中心首末）。内部节点自左端每 20 m 一个，右端不足 20 m 的最后一跨保留，
    两端节点各重复 4 次。先减左端 x0、再减 h，以 20 m 同时归一 x 与 y：ξ = (x − x0)/20、a_j = (c_j − h)/20；统一正缩放
    不改变最优解与物理约束。
    约束（连续区间成立）：
      端点 δ = h、δ' = 0：固定首尾控制值及相邻值 a_0 = a_1 = a_{n−2} = a_{n−1} = 0；
      走廊：控制点 j 的取值区间 = 其 B 样条支撑所交全部 x 条带（行中心 ±2.5 m）的 lo 最大值、hi 最小值；
            基函数非负、和为 1，因此任意 x 处 δ(x) 都在该点所在条带的区间内，不只在采样行成立；
      斜率：一阶导数 B 样条控制系数 p'_j = 3(a_{j+1} − a_j)/(t_{j+4} − t_{j+1})（归一节点）满足 |p'_j| ≤ tan 75°；
      曲率：二阶导数控制系数 q_j = 2(p'_{j+1} − p'_j)/(t_{j+4} − t_{j+2}) 满足 |q_j| ≤ 20·κ_max（物理 δ'' = q/20）；
            κ_max = min(0.38/(1 + 0.38 D), 1/(15.75 + D))，15.75 = 1.05 × 15。
      真实曲率 κ = δ''/(1 + δ'²)^{3/2} 的绝对值不超过 |δ''|；偏移车道曲率 κ/(1 − dκ) 由上式保证 |κ_i| ≤ 0.38、
      内侧半径 ≥ 15.75 m、1 − dκ > 0（V8-14b 同一推导）。非均匀末跨与重复端节点用通用 B 样条导数公式，
      不统一除以 20。
    目标：Σ_r e_r（每项权重 1），−e_r ≤ B_r a − (t_r − h)/20 ≤ e_r，t_r = lo_r + u(x_r)(hi_r − lo_r)，
      u = expit(Σ_k z_k N_k(φ))，φ = 2π(x − x0)/(x1 − x0)（K 基周期正 B 样条，与监视 lp_targets 同源）。
    求解：scipy.optimize.linprog(method="highs")，不传 maxiter/容差覆盖项；一次 LP，不重试。
    无解或无有效区间：返回原 h 的直线 BSpline（feasible=False、fallback_reason 非空），不重抽弦与 logits。

三、无重访的斜率证明（只覆盖图形穿越段）
    若 |x_B − x_A| ≤ 30 m 且 |δ'| ≤ s，则对 x ∈ [x_A, x_B]：
        ‖p(x) − p(x_A)‖ ≤ 30·sqrt(1 + s²)，且 s < sqrt(24) ⇒ 30·sqrt(1 + s²) < 150 m。
    取 s = tan 75° ≈ 3.732，上界约 115.91 m，达不到冻结重访"先离开至少 150 m 再回到 30 m 内"。偏移车道
    1 − dκ > 0 保证沿 x 单调、切线方向相同，证明对各车道同样成立。该证明不覆盖可视图进场与优化后的任意曲线，
    全窗口预筛与冻结核验不能省。

四、精确曲率复核（exact_curve_audit）
    每个三次多项式跨上 κ = δ''/(1 + δ'²)^{3/2} 的极值在跨端点与
        δ'''(1 + δ'²) − 3 δ' (δ'')² = 0
    的实根中取得；δ'' = 0 处也纳入。用同一组位置以 κ/(1 − dκ) 核查各车道；这些是解析驻点上的值，不是有限采样。
"""
import math
import time

import numpy as np

STRIP_HALF_M = 2.5            # x 行 5 m：每行代表 [x − 2.5, x + 2.5] 条带
KNOT_SPACING_M = 20.0
KAPPA_STAR = 0.38
R_TURN_M = 15.75
SLOPE_MAX = math.tan(math.radians(75.0))


def grid_error_m(field_spacing_m, x_step_m, y_step_m=0.0):
    return {"field_eps_m": math.hypot(field_spacing_m, field_spacing_m) / 2.0,
            "sampling_q_m": math.hypot(x_step_m / 2.0, y_step_m / 2.0)}


def kappa_cap(D_m, kappa_star=KAPPA_STAR, r_turn_m=R_TURN_M):
    D = float(D_m)
    return min(float(kappa_star) / (1.0 + float(kappa_star) * D), 1.0 / (float(r_turn_m) + D))


def clamped_knots(x0, x1, spacing=KNOT_SPACING_M):
    """归一节点（单位 = spacing）：[0]*4 + 内部 1, 2, …（严格小于右端）+ [L]*4，L = (x1 − x0)/spacing。"""
    L = (float(x1) - float(x0)) / float(spacing)
    if not L > 0.0:
        raise ValueError("曲线范围长度须为正")
    inner = np.arange(1.0, L, 1.0)
    inner = inner[inner < L - 1e-12]
    return np.r_[np.zeros(4), inner, np.full(4, L)]


def _basis_matrix(t, xi, deriv=0):
    """归一节点 t 的三次 B 样条基在 xi 处的值（或导数）矩阵 (len(xi), n)。"""
    from scipy.interpolate import BSpline
    n = len(t) - 4
    xi = np.asarray(xi, float)
    out = np.empty((len(xi), n))
    for j in range(n):
        c = np.zeros(n)
        c[j] = 1.0
        out[:, j] = BSpline(t, c, 3, extrapolate=False)(xi, nu=deriv)
    out[~np.isfinite(out)] = 0.0
    return out


def derivative_operators(t):
    """返回 (D1, D2)：p' = D1 a（n−1 个一阶导数控制系数）、q = D2 a（n−2 个二阶导数控制系数），归一坐标。"""
    n = len(t) - 4
    D1 = np.zeros((n - 1, n))
    for j in range(n - 1):
        den = t[j + 4] - t[j + 1]
        if den > 0:
            D1[j, j + 1] = 3.0 / den
            D1[j, j] = -3.0 / den
    D2 = np.zeros((n - 2, n))
    for j in range(n - 2):
        den = t[j + 4] - t[j + 2]
        if den > 0:
            D2[j] = 2.0 * (D1[j + 1] - D1[j]) / den
    return D1, D2


def lp_targets_x(x_m, lo_m, hi_m, logit_coefficients):
    """t_r = lo_r + u(x_r)(hi_r − lo_r)；u = expit(K 基周期样条)，沿 x 的归一进度映射到 [0, 2π]。"""
    from .monitoring_band import _expit
    from .path import periodic_radius_derivs
    x = np.asarray(x_m, float)
    span = float(x[-1] - x[0])
    phi = 2.0 * math.pi * (x - x[0]) / span if span > 0 else np.zeros_like(x)
    u = _expit(periodic_radius_derivs(phi, 0.0, np.asarray(logit_coefficients, float))[0])
    return np.asarray(lo_m, float) + u * (np.asarray(hi_m, float) - np.asarray(lo_m, float)), u


def _line_spline(x0, x1, h, t):
    from scipy.interpolate import BSpline
    n = len(t) - 4
    return BSpline(x0 + KNOT_SPACING_M * t, np.full(n, float(h)), 3, extrapolate=False)


def curve_lp(x_m, lo_m, hi_m, h_m, logit_coefficients, *, D_m, kappa_star=KAPPA_STAR, r_turn_m=R_TURN_M,
             knot_spacing_m=KNOT_SPACING_M, slope_max=None):
    """见模块说明第二节。x_m 为等距 5 m 行中心（升序），lo_m/hi_m 为每行包含 h 的连续已认证区间（绝对横向坐标）。
    返回 {"feasible", "spline"(物理坐标 BSpline), "target_m", "fallback_reason", "lp_status", "lp_message",
    "lp_nit", "objective", "max_residual", "kappa_max", "slope_max", "n_controls", "seconds"}。"""
    from scipy.interpolate import BSpline
    from scipy.optimize import linprog
    t0 = time.perf_counter()
    if float(knot_spacing_m) != KNOT_SPACING_M:
        raise ValueError("节点间距固定 20 m（U C.2/D.3.5）")
    x = np.asarray(x_m, float)
    lo, hi = np.asarray(lo_m, float), np.asarray(hi_m, float)
    h = float(h_m)
    s_max = SLOPE_MAX if slope_max is None else float(slope_max)
    kmax = kappa_cap(D_m, kappa_star, r_turn_m)
    x0, x1 = float(x[0]), float(x[-1])
    t = clamped_knots(x0, x1)
    n = len(t) - 4
    target, _u = lp_targets_x(x, lo, hi, logit_coefficients)
    out = {"feasible": False, "spline": _line_spline(x0, x1, h, t), "target_m": target, "fallback_reason": None,
           "lp_status": None, "lp_message": None, "lp_nit": None, "objective": None, "max_residual": None,
           "kappa_max": kmax, "slope_max": s_max, "n_controls": n, "knots_m": (x0 + KNOT_SPACING_M * t).tolist()}
    if n < 5:
        out.update(fallback_reason="too_few_controls", seconds=time.perf_counter() - t0)
        return out
    # 控制点区间：支撑 [t_j, t_{j+4}] 所交全部条带
    xi_rows = (x - x0) / KNOT_SPACING_M
    half = STRIP_HALF_M / KNOT_SPACING_M
    a_lo, a_hi = np.empty(n), np.empty(n)
    for j in range(n):
        sel = (xi_rows + half > t[j]) & (xi_rows - half < t[j + 4])
        if not np.any(sel):
            a_lo[j], a_hi[j] = -np.inf, np.inf
            continue
        a_lo[j] = (float(np.max(lo[sel])) - h) / KNOT_SPACING_M
        a_hi[j] = (float(np.min(hi[sel])) - h) / KNOT_SPACING_M
    fixed = [0, 1, n - 2, n - 1]
    for j in fixed:
        a_lo[j], a_hi[j] = max(a_lo[j], 0.0), min(a_hi[j], 0.0)
    if not (np.all(np.isfinite(lo)) and np.all(np.isfinite(hi))) or np.any(a_lo > a_hi):
        out.update(fallback_reason="lp_infeasible", lp_status="empty_control_interval",
                   lp_message="控制点区间（支撑内条带交集）为空", seconds=time.perf_counter() - t0)
        return out
    D1, D2 = derivative_operators(t)
    Bm = _basis_matrix(t, xi_rows)
    m = len(x)
    # 变量 [a (n), e (m)]
    tr = (target - h) / KNOT_SPACING_M
    Z = np.zeros
    A_ub = np.vstack([
        np.hstack([D1, Z((n - 1, m))]), np.hstack([-D1, Z((n - 1, m))]),
        np.hstack([D2, Z((n - 2, m))]), np.hstack([-D2, Z((n - 2, m))]),
        np.hstack([Bm, -np.eye(m)]), np.hstack([-Bm, -np.eye(m)])])
    q_cap = KNOT_SPACING_M * kmax
    b_ub = np.r_[np.full(n - 1, s_max), np.full(n - 1, s_max), np.full(n - 2, q_cap), np.full(n - 2, q_cap), tr, -tr]
    cost = np.r_[np.zeros(n), np.ones(m)]
    bounds = [(float(a_lo[j]), float(a_hi[j])) for j in range(n)] + [(0.0, None)] * m
    res = linprog(cost, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
    out.update(lp_status=int(res.status), lp_message=str(res.message), lp_nit=int(getattr(res, "nit", 0) or 0))
    if res.status != 0:
        out.update(fallback_reason="lp_infeasible", seconds=time.perf_counter() - t0)
        return out
    a = np.asarray(res.x[:n], float)
    # 原单位最大残差（只作数值诊断，不放宽任何物理阈值）
    r_slope = np.max(np.abs(D1 @ a)) - s_max
    r_curv = (np.max(np.abs(D2 @ a)) - q_cap) / KNOT_SPACING_M
    r_corr = KNOT_SPACING_M * max(float(np.max(a_lo - a)), float(np.max(a - a_hi)), 0.0)
    out.update(feasible=True, objective=float(res.fun) * KNOT_SPACING_M,
               spline=BSpline(x0 + KNOT_SPACING_M * t, h + KNOT_SPACING_M * a, 3, extrapolate=False),
               max_residual={"slope": float(max(r_slope, 0.0)), "curvature_per_m": float(max(r_curv, 0.0)),
                             "corridor_m": float(r_corr)},
               controls_m=(h + KNOT_SPACING_M * a).tolist(), seconds=time.perf_counter() - t0)
    return out


def _cubic_roots_real(coef):
    """多项式（高次在前）在实数上的根。"""
    c = np.trim_zeros(np.asarray(coef, float), "f")
    if len(c) <= 1:
        return np.array([])
    r = np.roots(c)
    return np.real(r[np.abs(np.imag(r)) <= 1e-9 * np.maximum(1.0, np.abs(r))])


def exact_curve_audit(spline, offsets_m, *, kappa_star=KAPPA_STAR, r_turn_m=R_TURN_M):
    """模块说明第四节。返回 {"ok", "kappa_max_abs", "at_x", "lane": {d: 最大 |κ/(1−dκ)|}, "min_den", "candidates"}。
    检查：|κ|·(15.75 + D) ≤ 1、各车道 |κ/(1 − dκ)| ≤ κ*、1 − dκ > 0；并要求 |δ'| ≤ tan75°（连续：δ' 在各跨上是二次多项式，
    极值在端点与 δ'' = 0 的根）。"""
    t = np.asarray(spline.t, float)
    c = np.asarray(spline.c, float)
    k = int(spline.k)
    xs = []
    breaks = np.unique(t[k:len(t) - k])
    d1 = spline.derivative(1)
    d2 = spline.derivative(2)
    d3 = spline.derivative(3)
    for a, b in zip(breaks[:-1], breaks[1:]):
        if not b > a:
            continue
        xs.extend([a, b])
        # 在跨内用 4 点拟合 δ', δ'', δ''' 的局部多项式（三次样条在跨内精确为多项式）
        loc = np.linspace(a, b, 5)
        mid = 0.5 * (a + b)
        p1 = np.polyfit(loc - mid, d1(loc), 2)
        p2 = np.polyfit(loc - mid, d2(loc), 1)
        p3 = np.polyfit(loc - mid, d3(np.full(5, mid)), 0)
        # δ'' = 0
        for r in _cubic_roots_real(p2):
            if a <= r + mid <= b:
                xs.append(r + mid)
        # δ'''(1 + δ'²) − 3 δ' δ''² = 0
        poly = np.polysub(np.polymul(p3, np.polyadd([1.0], np.polymul(p1, p1))),
                          3.0 * np.polymul(p1, np.polymul(p2, p2)))
        for r in _cubic_roots_real(poly):
            if a <= r + mid <= b:
                xs.append(r + mid)
    xs = np.unique(np.asarray(xs, float))
    v1, v2 = d1(xs), d2(xs)
    kap = v2 / np.power(1.0 + v1 * v1, 1.5)
    ka = np.abs(kap)
    offs = np.asarray(sorted({float(d) for d in offsets_m}), float) if len(offsets_m) else np.zeros(1)
    D = float(np.max(np.abs(offs)))
    turn_ok = bool(np.all(ka * (R_TURN_M + D) <= 1.0 + 1e-12)) if r_turn_m == R_TURN_M else bool(
        np.all(ka * (float(r_turn_m) + D) <= 1.0 + 1e-12))
    lanes, min_den = {}, math.inf
    lane_ok = True
    for d in offs:
        den = 1.0 - d * kap
        min_den = min(min_den, float(np.min(den)))
        kl = np.abs(kap / den)
        lanes[float(d)] = float(np.max(kl))
        lane_ok = lane_ok and bool(np.all(den > 0.0)) and bool(np.all(kl <= float(kappa_star) + 1e-12))
    slope = float(np.max(np.abs(v1))) if len(v1) else 0.0
    slope_ok = slope <= SLOPE_MAX + 1e-9
    i = int(np.argmax(ka)) if len(ka) else 0
    return {"ok": bool(turn_ok and lane_ok and slope_ok), "kappa_max_abs": float(ka[i]) if len(ka) else 0.0,
            "at_x": float(xs[i]) if len(xs) else None, "lane": lanes, "min_den": min_den, "slope_max": slope,
            "turn_ok": turn_ok, "lane_ok": lane_ok, "slope_ok": slope_ok, "candidates": int(len(xs))}


def no_revisit_bound_m(x_span_m=30.0, slope=SLOPE_MAX):
    """模块说明第三节的上界 30·sqrt(1 + s²)。"""
    return float(x_span_m) * math.sqrt(1.0 + float(slope) ** 2)
