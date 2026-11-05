"""V8-14 第 2 部分：监视环带的局部证书与环带内直接构造（指令第 2 节；附录裁定 1、2、3、5、8）。

坐标：以抽到的圈心 c 为原点，φ_j = 2πj/360，半径网格 2 m。对每个方位，沿射线在 2 m 网格上用**完整巡逻约束**
（monitoring_constraints 的 base + patrol）逐点求精确余量，并用 segment_clearance 逐弦核对相邻采样点之间的径向弦；
任何形状都按多区间处理（裁定 2：只有目标警戒/预警层才有"射线只交一次"，这里不依赖它）。

局部证书（裁定 1，取代指令 2.2 的全局 e 与 2.3 的宽度判定）：
  1. 原始区间：先按跨方位相邻重叠合并成极坐标连通分量（V8-13 `_components` 同一规则），选定**同一分量**，
     每行取该分量在本行的最长段 [lo_j, hi_j]（同长取较小 lo）。
  2. 管区间：给定车道半跨 D，在 [lo_j, hi_j] 内取逐点与逐弦余量都 ≥ D + q + η 的最长连续子段 [L⁺_j, U⁺_j]
     （q = Δr/2 + 2R*·sin(Δφ/4)，η = 2ε_f，ε_f 为组合栅格双线性保守量）；不要求包含父区间中点。
  3. A_j = max_{k∈N(j)} L⁺_k，B_j = min_{k∈N(j)} U⁺_k，N(j) = {j−2,…,j+2}（周期；弧在弧端夹取）。
  4. 唯一可行判定：所有 j 都有 A_j ≤ B_j（选队形与构造共用）。
  5. 取值 r_j = A_j + u(φ_j)(B_j − A_j)，360 个 r_j 直接作三次周期 B 样条控制值（正基函数平均，不插值）。
证明：方位 φ 的最近行为 j 时，三次 B 样条在 φ 处激活的控制点 k 都在 N(j) 内（periodic_radius_derivs 的支撑
floor(φN/2π)−1…+2），平滑值是这些 r_k 的凸组合；r_k ∈ [A_k, B_k] ⊂ [L⁺_j, U⁺_j]（因 j ∈ N(k)）。故参考线落在
[L⁺_j, U⁺_j]；射线 φ 与 φ_j 的弦距 ≤ 2R* sin(Δφ/4)，射线 j 上 [L⁺_j, U⁺_j] 内任一点（含网格点之间，已由逐弦核对）
余量 ≥ D + q + η，于是参考点余量 ≥ D + Δr/2 + η，偏移不超过 D 的任一车道点余量 ≥ η = 2ε_f，覆盖组合栅格复核的保守损失。
全局 e_g、e_s、e 只作诊断字段保留（指令 2.2 的定义），不参与判定和取值。

纯数值函数导入时不加载 shapely；场景几何（scene.exact）只在 radial_* / build_band_query 内惰性导入。
"""
import math

import numpy as np

PHI_ROWS = 360
R_STEP_M = 2.0
NEIGHBOR_HALF = 2          # N(j) = {j−2, …, j+2}：三次 B 样条最近网格点两侧半格支撑的并集


# ---------------------------------------------------------------- 纯数值

def grid_error_m(r_max_m, *, phi_rows=PHI_ROWS, radial_step_m=R_STEP_M):
    """q = Δr/2 + 2R*·sin(Δφ/4)：半径最近网格误差 + 任意方位到最近 1° 采样射线的弦距上界。"""
    dphi = 2.0 * math.pi / float(phi_rows)
    return 0.5 * float(radial_step_m) + 2.0 * float(r_max_m) * math.sin(dphi / 4.0)


def cubic_blend(x):
    """三次控制值 (0,0,1,1) 的形变 H(x) = 3x² − 2x³，输入先截至 [0,1]；H'(0)=H'(1)=0，max H' = 3/2。"""
    x = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    return 3.0 * x * x - 2.0 * x * x * x


def _windows(n, periodic):
    """每行 j 的邻域索引（n×5）；非周期时在两端夹取到 [0, n−1]。"""
    off = np.arange(-NEIGHBOR_HALF, NEIGHBOR_HALF + 1)
    idx = np.arange(n)[:, None] + off[None, :]
    return np.mod(idx, n) if periodic else np.clip(idx, 0, n - 1)


def band_certificate(lo, hi, tube_lo, tube_hi, offsets_m, *, periodic=True, row_start=0):
    """局部证书（附录裁定 1）。offsets_m 为真实左偏移；D = max|d|（当前三种槽位居中对称）。
    lower_m/upper_m 为管区间 [L⁺, U⁺]；A_m/B_m 为局部交集；feasible ⇔ 全部有限、L⁺≤U⁺、A≤B。
    e_geom_m/e_smooth_m/e_m 为指令 2.2 的全局诊断量，不参与判定。"""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    tl, tu = np.asarray(tube_lo, float), np.asarray(tube_hi, float)
    n = len(lo)
    if not (len(hi) == len(tl) == len(tu) == n) or n == 0:
        raise ValueError("区间数组须同长且非空")
    if periodic and n != PHI_ROWS:
        raise ValueError("周期证书须为完整 360 行")
    offs = np.asarray(offsets_m, float).reshape(-1)
    D = float(np.max(np.abs(offs))) if len(offs) else 0.0
    finite = bool(np.all(np.isfinite(lo) & np.isfinite(hi) & np.isfinite(tl) & np.isfinite(tu)))
    W = _windows(n, periodic)
    with np.errstate(invalid="ignore"):
        A = np.max(tl[W], axis=1) if finite else np.full(n, np.nan)
        B = np.min(tu[W], axis=1) if finite else np.full(n, np.nan)
    ordered = finite and bool(np.all(lo <= hi)) and bool(np.all(tl <= tu))
    slack = B - A
    feasible = bool(ordered and np.all(slack >= 0.0))
    if finite:
        e_geom = float(max(0.0, np.max(tl - lo - D), np.max(hi - D - tu)))
        e_smooth = float(max(0.0, np.max(lo[W] - lo[:, None]), np.max(hi[:, None] - hi[W])))
        k = int(np.argmin(slack))
        worst = {"row": int(row_start + k), "slack_m": float(slack[k])}
    else:
        e_geom = e_smooth = math.nan
        bad = np.flatnonzero(~(np.isfinite(lo) & np.isfinite(hi) & np.isfinite(tl) & np.isfinite(tu)))
        worst = {"row": int(row_start + bad[0]) if len(bad) else None, "slack_m": None, "reason": "missing_interval"}
    return {"feasible": feasible, "e_geom_m": e_geom, "e_smooth_m": e_smooth, "e_m": e_geom + e_smooth,
            "half_span_m": D, "lo": lo, "hi": hi, "lower_m": tl, "upper_m": tu, "A_m": A, "B_m": B,
            "periodic": bool(periodic), "row_start": int(row_start), "worst": worst,
            "min_slack_m": float(np.min(slack)) if finite else None}


class BandCurve:
    """环带内构造出的周期半径曲线（360 个控制值）。radius(φ) 接收全局方位。"""

    def __init__(self, rho0_m, coefficients_m, raw_knots_m, u_knots, logit_coefficients):
        self.rho0_m = float(rho0_m)
        self.coefficients_m = np.asarray(coefficients_m, float)
        self.raw_knots_m = np.asarray(raw_knots_m, float)
        self.u_knots = np.asarray(u_knots, float)
        self.logit_coefficients = np.asarray(logit_coefficients, float)

    def radius(self, phi):
        from .path import periodic_radius_derivs
        return periodic_radius_derivs(np.asarray(phi, float), self.rho0_m, self.coefficients_m)[0]


def _expit(x):
    x = np.asarray(x, float)
    out = np.empty_like(x)
    pos = x >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-x[pos]))
    ex = np.exp(x[~pos])
    out[~pos] = ex / (1.0 + ex)
    return out


def logit_from_quantiles(v):
    """均匀分位数 v → z = log v − log(1−v)（裁定 5）；只把 RNG 端点 0/1 移到 nextafter。"""
    v = np.clip(np.asarray(v, float), np.nextafter(0.0, 1.0), np.nextafter(1.0, 0.0))
    return np.log(v) - np.log1p(-v)


def construct_band(certificate, logit_coefficients):
    """只接受已通过的证书；RNG 已在外部完成。u(φ) = expit(Σ_k B_k^{(K)}(φ) z_k)，r_j = A_j + u(φ_j)(B_j − A_j)。
    弧证书按 row_start 写回全局 360 行，其余行取循环方位距离最近的弧端控制值（同距取起端）——幽灵值，不飞行。"""
    from .path import periodic_radius_derivs
    if not certificate.get("feasible"):
        raise ValueError("证书未通过，不能构造")
    z = np.asarray(logit_coefficients, float).reshape(-1)
    if not (3 <= len(z)):
        raise ValueError("logit 系数至少 3 个（周期三次 B 样条）")
    A, B = np.asarray(certificate["A_m"], float), np.asarray(certificate["B_m"], float)
    n = len(A)
    start = int(certificate["row_start"])
    rows = (start + np.arange(n)) % PHI_ROWS if not certificate["periodic"] else np.arange(PHI_ROWS)
    phis = 2.0 * math.pi * rows / PHI_ROWS
    u = _expit(periodic_radius_derivs(phis, 0.0, z)[0])
    r_local = A + u * (B - A)
    if certificate["periodic"]:
        r = r_local
    else:
        r = np.empty(PHI_ROWS)
        r[rows] = r_local
        if n < PHI_ROWS:
            others = np.setdiff1d(np.arange(PHI_ROWS), rows)
            d_start = np.mod(start - others, PHI_ROWS)          # 到起端的循环距离（向前）
            d_start = np.minimum(d_start, PHI_ROWS - d_start)
            end = (start + n - 1) % PHI_ROWS
            d_end = np.mod(others - end, PHI_ROWS)
            d_end = np.minimum(d_end, PHI_ROWS - d_end)
            r[others] = np.where(d_start <= d_end, r_local[0], r_local[-1])
    rho0 = float(np.mean(r))
    return BandCurve(rho0, r - rho0, r, u, z)


def admissible_arcs(valid_rows, *, min_coverage_deg=120.0):
    """参数方位跨度 ≥ min_coverage_deg 的连续弧 (start_row, end_row)，按展开整数索引排序，end 可 ≥ 360。
    覆盖按末方位减首方位（121 个端点 = 120°）；全圆只列跨度 < 360° 的弧。V8-14 生产中参数跨度只作诊断
    （裁定 8：真实目标方位覆盖另算），本函数不做随机选择。"""
    v = np.asarray(valid_rows, bool)
    P = len(v)
    need = int(math.ceil(float(min_coverage_deg) * P / 360.0 - 1e-12))
    out = []
    if not v.any():
        return out
    if v.all():
        for s in range(P):
            for e in range(s + max(need, 1), s + P):
                out.append((s, e))
        return out
    first_false = int(np.flatnonzero(~v)[0])
    runs = []
    k = first_false
    while k < first_false + P:
        if v[k % P]:
            a = k
            while k < first_false + P and v[k % P]:
                k += 1
            runs.append((a, k - 1))
        else:
            k += 1
    for a, b in runs:
        a0 = a % P
        b0 = a0 + (b - a)
        for s in range(a0, b0 + 1):
            for e in range(s + max(need, 1), b0 + 1):
                out.append((s, e))
    return sorted(out)


# ---------------------------------------------------------------- 射线上的精确余量（几何惰性导入）

def radial_margins(constraints, center, radii, *, phi_rows=PHI_ROWS, allowed_mask=None):
    """返回 (pm, cm)：pm[j, k] = 第 j 方位第 k 半径点对全部约束的最小精确余量（掩码外为 −inf）；
    cm[j, k] = 相邻两点 k→k+1 的径向弦最小精确余量（任一端在掩码外或点余量为负时为 −inf，不计算）。"""
    from ..scene.exact import clearance_values, chord_sdf_range, margin_from_range
    c = np.asarray(center, float)
    rs = np.asarray(radii, float)
    phis = 2.0 * math.pi * np.arange(phi_rows) / phi_rows
    e = np.stack([np.cos(phis), np.sin(phis)], axis=1)
    pts = c[None, None, :] + rs[None, :, None] * e[:, None, :]
    mask = np.ones((phi_rows, len(rs)), bool) if allowed_mask is None else np.asarray(allowed_mask, bool)
    pm = np.full(mask.shape, -np.inf)
    sel = np.flatnonzero(mask.ravel())
    if len(sel):
        flat = pts.reshape(-1, 2)[sel]
        m = np.full(len(sel), np.inf)
        for cn in constraints:
            m = np.minimum(m, clearance_values(cn.geometry, flat, sense=cn.sense, minimum_m=cn.minimum_m))
        pm.ravel()[sel] = m
    cm = np.full((phi_rows, max(len(rs) - 1, 0)), -np.inf)
    if len(rs) >= 2:
        both = (pm[:, :-1] >= 0.0) & (pm[:, 1:] >= 0.0)
        sel = np.flatnonzero(both.ravel())
        if len(sel):
            a = pts[:, :-1, :].reshape(-1, 2)[sel]
            b = pts[:, 1:, :].reshape(-1, 2)[sel]
            m = np.full(len(sel), np.inf)
            for cn in constraints:
                lo, hi, _ = chord_sdf_range(cn.geometry, a, b)
                m = np.minimum(m, margin_from_range(lo, hi, sense=cn.sense, minimum_m=cn.minimum_m))
            cm.ravel()[sel] = m
    return pm, cm


def _row_runs(pm_row, cm_row, threshold, k_lo=0, k_hi=None):
    """[k_lo, k_hi] 内逐点 ≥ threshold 且相邻弦 ≥ threshold 的连续段 [(a, b)]（半径下标闭区间）。"""
    n = len(pm_row)
    k_hi = n - 1 if k_hi is None else k_hi
    runs = []
    a = None
    for k in range(k_lo, k_hi + 1):
        ok = pm_row[k] >= threshold
        if ok and a is not None and not (cm_row[k - 1] >= threshold):
            runs.append((a, k - 1))
            a = None
        if ok and a is None:
            a = k
        if not ok and a is not None:
            runs.append((a, k - 1))
            a = None
    if a is not None:
        runs.append((a, k_hi))
    return runs


def _row_runs_fast(pm_row, cm_row, threshold, k_lo, k_hi):
    ok = pm_row[k_lo:k_hi + 1] >= threshold
    if not ok.any():
        return []
    link = np.r_[cm_row[k_lo:k_hi] >= threshold, False] if k_hi > k_lo else np.array([False])
    # 段起点：ok 且（第一个或前一点不 ok 或前弦不 ok）
    prev_ok = np.r_[False, ok[:-1]]
    prev_link = np.r_[False, link[:-1]]
    starts = ok & ~(prev_ok & prev_link)
    ends = ok & ~(np.r_[ok[1:], False] & link)
    s = np.flatnonzero(starts)
    e = np.flatnonzero(ends)
    return [(int(a) + k_lo, int(b) + k_lo) for a, b in zip(s, e)]


def _longest(runs):
    if not runs:
        return None
    return max(runs, key=lambda ab: (ab[1] - ab[0], -ab[0]))


def radial_intervals(constraints, center, radii, *, phi_rows=PHI_ROWS, extra_margin_m=0.0, allowed_mask=None,
                     parent_intervals=None):
    """每方位的 (lo, hi) 半径数组（无段为 NaN）。无 parent：最长段（同长取较小 lo）；有 parent：在每行父区间内
    取逐点与逐弦余量都 ≥ extra_margin_m 的最长子段（附录裁定 1 取消"含父区间中点"要求）。"""
    rs = np.asarray(radii, float)
    pm, cm = radial_margins(constraints, center, rs, phi_rows=phi_rows, allowed_mask=allowed_mask)
    return intervals_from_margins(pm, cm, rs, float(extra_margin_m), parent_intervals)


def intervals_from_margins(pm, cm, rs, threshold, parent_intervals=None):
    P = pm.shape[0]
    lo = np.full(P, np.nan)
    hi = np.full(P, np.nan)
    for j in range(P):
        if parent_intervals is None:
            k_lo, k_hi = 0, len(rs) - 1
        else:
            plo, phi_ = parent_intervals[0][j], parent_intervals[1][j]
            if not (np.isfinite(plo) and np.isfinite(phi_)):
                continue
            k_lo = int(round((plo - rs[0]) / (rs[1] - rs[0]))) if len(rs) > 1 else 0
            k_hi = int(round((phi_ - rs[0]) / (rs[1] - rs[0]))) if len(rs) > 1 else 0
        best = _longest(_row_runs_fast(pm[j], cm[j], threshold, k_lo, k_hi))
        if best is not None:
            lo[j], hi[j] = rs[best[0]], rs[best[1]]
    return lo, hi


# ---------------------------------------------------------------- 连通分量（与 V8-13 `_components` 同一规则）

def run_components(row_runs):
    """row_runs[j] = [(a, b), …]（半径下标闭区间）。相邻方位（含 359→0）下标区间重叠即合并。
    返回 [{"rows": {j: [(a,b),…]}, "wrapping": bool, "n_rows": int, "id": int}]，按 (−n_rows, 最小行) 排序。"""
    P = len(row_runs)
    runs, owner = [], [[] for _ in range(P)]
    for j in range(P):
        for a, b in row_runs[j]:
            owner[j].append(len(runs))
            runs.append((j, a, b))
    parent = list(range(len(runs)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for j in range(P):
        k = (j + 1) % P
        for a in owner[j]:
            for b in owner[k]:
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
    out.sort(key=lambda c: (-c["n_rows"], min(c["rows"])))
    for i, c in enumerate(out):
        c["id"] = i
    return out


# ---------------------------------------------------------------- 真实目标方位覆盖下界（裁定 8）

def _wrap_pi(x):
    return (np.asarray(x, float) + math.pi) % (2.0 * math.pi) - math.pi


def bearing_offset(center, facility_center, phi, radius):
    """α(X) = 设施方位(X) − 圈心方位 φ（主值）。圈心、设施中心都在凸警戒区内、巡逻点在警戒区外，
    故巡逻曲线不穿过两中心连线段，α 沿曲线连续，设施方位的展开增量 = Δφ + α(终) − α(始)。"""
    c, f = np.asarray(center, float), np.asarray(facility_center, float)
    phi = np.asarray(phi, float)
    r = np.asarray(radius, float)
    x = c[0] + r * np.cos(phi) - f[0]
    y = c[1] + r * np.sin(phi) - f[1]
    return _wrap_pi(np.arctan2(y, x) - phi)


def coverage_lower_bound_deg(center, facility_center, phi_s, rng_s, phi_e, rng_e):
    """弧端点只知落在射线段 [L⁺, U⁺] 内时，真实设施方位覆盖的下界（度）。射线上设施方位单调，
    极值在段端点：取 4 种端点组合中最小的展开增量 Δβ = (φ_e − φ_s) + α(Q) − α(P)。"""
    phi_s, phi_e = np.asarray(phi_s, float), np.asarray(phi_e, float)
    best = None
    for rs in rng_s:
        for re in rng_e:
            d = (phi_e - phi_s) + bearing_offset(center, facility_center, phi_e, re) \
                - bearing_offset(center, facility_center, phi_s, rs)
            best = d if best is None else np.minimum(best, d)
    return np.degrees(best)


def coverage_exact_deg(center, facility_center, phi_s, r_s, phi_e, r_e):
    """端点精确已知（构造后）时的展开增量（度）；路径覆盖 ≥ 该值的绝对值。"""
    d = (float(phi_e) - float(phi_s)) + float(bearing_offset(center, facility_center, phi_e, r_e)) \
        - float(bearing_offset(center, facility_center, phi_s, r_s))
    return math.degrees(d)


# ---------------------------------------------------------------- 弧证书的成批核对

def _slow_arc_ok(tl, tu, s, e):
    for j in range(s, e + 1):
        a, b = max(s, j - NEIGHBOR_HALF), min(e, j + NEIGHBOR_HALF)
        if not (np.max(tl[a:b + 1]) <= np.min(tu[a:b + 1])):
            return False
    return True


def certified_arc_pairs(tl, tu, row_ids, unrolled_ok, *, center, facility_center, min_true_deg, s_max=None,
                        max_span=None):
    """一个分量上全部合法弧端点对。tl/tu/row_ids 是展开顺序的连续行（长度 n）；unrolled_ok 为该行管区间有限。
    返回 [(s_idx, e_idx, cov_lb_deg)]（展开下标）。证书规则：行 j∈[s,e] 的邻域夹取到 [s,e]，要求 A_j ≤ B_j；
    再要求真实目标方位覆盖下界 ≥ min_true_deg（裁定 8）。s ≤ s_max、e − s ≤ max_span（全圆展开时用）。"""
    tl, tu = np.asarray(tl, float), np.asarray(tu, float)
    n = len(tl)
    out = []
    if n < 2:
        return out
    s_max = n - 2 if s_max is None else min(int(s_max), n - 2)
    max_span = n - 1 if max_span is None else int(max_span)
    phis = 2.0 * math.pi * np.asarray(row_ids, float) / PHI_ROWS
    good = np.asarray(unrolled_ok, bool)
    tlg = np.where(good, tl, np.inf)
    tug = np.where(good, tu, -np.inf)

    def wmax(a_off, b_off):
        """每个 j 的 max tl[j+a_off … j+b_off]（越界为 +inf，使之不通过）。"""
        out_ = np.full(n, np.inf)
        lo_, hi_ = max(0, -a_off), min(n, n - b_off)
        if hi_ > lo_:
            idx = np.arange(lo_, hi_)[:, None] + np.arange(a_off, b_off + 1)[None, :]
            out_[lo_:hi_] = np.max(tlg[idx], axis=1)
        return out_

    def wmin(a_off, b_off):
        out_ = np.full(n, -np.inf)
        lo_, hi_ = max(0, -a_off), min(n, n - b_off)
        if hi_ > lo_:
            idx = np.arange(lo_, hi_)[:, None] + np.arange(a_off, b_off + 1)[None, :]
            out_[lo_:hi_] = np.min(tug[idx], axis=1)
        return out_

    full = wmax(-2, 2) <= wmin(-2, 2)        # 行 j 的完整邻域
    f3 = wmax(0, 2) <= wmin(0, 2)            # 弧首行：[s, s+2]
    f4 = wmax(-1, 2) <= wmin(-1, 2)          # 次行 s+1：[s, s+3]（以 j=s+1 计）
    b3 = wmax(-2, 0) <= wmin(-2, 0)          # 末行 e：[e−2, e]
    b4 = wmax(-2, 1) <= wmin(-2, 1)          # 倒数第二行 e−1：[e−3, e]（以 j=e−1 计）
    bad_prefix = np.r_[0, np.cumsum(~full)]
    miss_prefix = np.r_[0, np.cumsum(~good)]
    for s in range(0, s_max + 1):
        if not good[s]:
            continue
        es = np.arange(s + 1, min(n - 1, s + max_span) + 1)
        if not len(es):
            continue
        es = es[(miss_prefix[es + 1] - miss_prefix[s]) == 0]
        if not len(es):
            continue
        cov = coverage_lower_bound_deg(center, facility_center, phis[s], (tl[s], tu[s]), phis[es], (tl[es], tu[es]))
        keep = cov >= float(min_true_deg)
        es, cov = es[keep], cov[keep]
        if not len(es):
            continue
        long_ = es - s >= 4
        el, cl = es[long_], cov[long_]
        if len(el) and f3[s] and f4[s + 1]:
            inner = (bad_prefix[el - 1] - bad_prefix[s + 2]) == 0
            ok = inner & b3[el] & b4[el - 1]
            out.extend((s, int(e), float(c)) for e, c in zip(el[ok], cl[ok]))
        for e, c in zip(es[~long_].tolist(), cov[~long_].tolist()):
            if _slow_arc_ok(tl, tu, s, e):
                out.append((s, e, float(c)))
    out.sort()
    return out


def arc_certificate(lo, hi, tl, tu, s, e, offsets_m, row_start):
    """展开下标 [s, e] 的弧证书（非周期，邻域在弧端夹取）。"""
    return band_certificate(lo[s:e + 1], hi[s:e + 1], tl[s:e + 1], tu[s:e + 1], offsets_m, periodic=False,
                            row_start=row_start)


# ---------------------------------------------------------------- 生产查询（场景几何惰性）

class BandGeometry:
    """一个圈心上的射线余量、原始分量与网格误差；同一 attempt 内各队形探测共享（宽度查询不各算一套）。"""

    def __init__(self, S, center):
        self.center = np.asarray(center, float)
        wx0, wy0, wx1, wy1 = S.warning_bbox()
        self.r_star = float(max(math.hypot(wx - center[0], wy - center[1]) for wx in (wx0, wx1) for wy in (wy0, wy1)))
        self.rs = np.arange(R_STEP_M, self.r_star + R_STEP_M, R_STEP_M)
        self.q = grid_error_m(self.r_star)
        self.eta = 2.0 * float(S.cg_patrol.field.eps)
        self.allowed = S.polar_mask_single(self.center, self.rs)
        self.cons = S.cons["base"] + S.cons["patrol"]
        self.pm, self.cm = radial_margins(self.cons, self.center, self.rs, allowed_mask=self.allowed)
        row_runs = [_row_runs_fast(self.pm[j], self.cm[j], 0.0, 0, len(self.rs) - 1) for j in range(PHI_ROWS)]
        self.components = run_components(row_runs)
        self.facility_center = np.asarray(S.tgt.center, float)
        self._tubes = {}

    def raw_interval(self, comp):
        """分量内每行最长段（同长取较小 lo）的半径下标。"""
        out = {}
        for j, runs in comp["rows"].items():
            out[j] = _longest(runs)
        return out

    def tubes(self, comp, D):
        key = (comp["id"], round(float(D), 9))
        if key in self._tubes:
            return self._tubes[key]
        thr = float(D) + self.q + self.eta
        lo = np.full(PHI_ROWS, np.nan)
        hi = np.full(PHI_ROWS, np.nan)
        tl = np.full(PHI_ROWS, np.nan)
        tu = np.full(PHI_ROWS, np.nan)
        for j, (a, b) in self.raw_interval(comp).items():
            lo[j], hi[j] = self.rs[a], self.rs[b]
            best = _longest(_row_runs_fast(self.pm[j], self.cm[j], thr, a, b))
            if best is not None:
                tl[j], tu[j] = self.rs[best[0]], self.rs[best[1]]
        out = (lo, hi, tl, tu, thr)
        self._tubes[key] = out
        return out


def loop_query(G, D, offsets):
    """环绕：每个跨满 360 行的分量各求一次周期证书；返回已通过的 [(分量, 证书)]。"""
    got = []
    for comp in G.components:
        if not comp["wrapping"]:
            continue
        lo, hi, tl, tu, thr = G.tubes(comp, D)
        cert = band_certificate(lo, hi, tl, tu, offsets, periodic=True)
        cert.update(q_m=G.q, eta_m=G.eta, threshold_m=thr, component=comp["id"])
        if cert["feasible"]:
            got.append((comp, cert))
    return got


def _unrolled_rows(comp, tl):
    """分量的行按展开顺序排列（跨 0° 的段展开为递增角）；返回 [(row_ids 展开整数列表)] 的连续段。"""
    rows = sorted(comp["rows"])
    if comp["wrapping"]:
        return [list(range(0, PHI_ROWS))], True
    rs = set(rows)
    segs = []
    for r in rows:
        if (r - 1) % PHI_ROWS in rs:
            continue
        seg = [r]
        k = r + 1
        while k % PHI_ROWS in rs and len(seg) < PHI_ROWS:
            seg.append(k)
            k += 1
        segs.append(seg)
    return segs, False


def retrace_query(G, D, offsets, min_true_deg):
    """折返：每个分量的每个连续方位段上，按真实目标方位覆盖下界 ≥ min_true_deg 与弧证书列出全部合法端点对。
    返回 [(分量, 段展开行, (s, e, cov))]。全圆分量：起点循环，终点在其后 1…359 行（不把整圈当弧）。"""
    out = []
    for comp in G.components:
        lo, hi, tl, tu, thr = G.tubes(comp, D)
        segs, wrap = _unrolled_rows(comp, tl)
        for seg in segs:
            if wrap:
                base = np.arange(PHI_ROWS)
                ids = np.r_[base, base[:-1] + PHI_ROWS]           # 展开两圈减一行：弧长 < 360°
                rows_mod = ids % PHI_ROWS
            else:
                ids = np.asarray(seg)
                rows_mod = ids % PHI_ROWS
            ok = np.isfinite(tl[rows_mod]) & np.isfinite(tu[rows_mod])
            pairs = certified_arc_pairs(tl[rows_mod], tu[rows_mod], ids, ok, center=G.center,
                                        facility_center=G.facility_center, min_true_deg=min_true_deg,
                                        s_max=PHI_ROWS - 1 if wrap else None,
                                        max_span=PHI_ROWS - 1 if wrap else None)
            for p in pairs:
                out.append((comp, ids, rows_mod, p, (lo, hi, tl, tu, thr)))
    return out


def build_band_query(setup, center, slots, *, topology):
    """生产队形探测的唯一入口：给定圈心、槽位与拓扑，返回 {"feasible", ...}。setup 为 monitoring._Setup。"""
    G = setup.band_geometry(center)
    offsets = [d for _, d in slots.offsets.values()]
    D = max((abs(d) for d in offsets), default=0.0)
    if topology == "loop":
        got = loop_query(G, D, offsets)
        return {"feasible": bool(got), "topology": "loop", "loops": got, "geometry": G, "D": D, "offsets": offsets}
    min_true = float(setup.criteria["min_azimuth_coverage_deg"])
    got = retrace_query(G, D, offsets, min_true)
    return {"feasible": bool(got), "topology": "retrace", "arcs": got, "geometry": G, "D": D, "offsets": offsets}
