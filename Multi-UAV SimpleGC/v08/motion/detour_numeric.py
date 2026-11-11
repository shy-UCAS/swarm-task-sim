"""V8-21 迂回：扫角/事件、方向与抽签序列、解析圆角与弧端点等纯数值函数（指令 3.2–3.4、4.1；裁定 1–3）。

导入时不读配置、不读场景、不导入 shapely。
"""
import math

import numpy as np

FRAME_US = 100_000


def _values(candidate):
    return candidate.values if hasattr(candidate, "values") and not isinstance(candidate, dict) else candidate


# ---------------------------------------------------------------- 扫角与事件（指令 4.1）

def sweep_series(time_us, signed_warning_m, angle_rad, near_band_width_m):
    """单成员、单设施在一个实测/名义窗口上的近距离带扫角与事件。

    输入同长、非空、有限；time_us 为整数且严格按 100000 μs 递增（10 Hz）。angle_rad 是原始 atan2 方位，本函数在
    整个窗口上 unwrap（不先过滤带内帧，不跨离带帧拼接区间）。带内 b = (0 < sd ≤ D)。区间 [a, b) 的 span 为
    (max − min) 度、net 为 |α[b−1] − α[a]| 度；单帧区间均为 0。entry 计首帧在带内；退出时刻取第一个带外帧，
    窗口末仍在带内则该区间 exit 为 None。"""
    t = np.asarray(time_us)
    sd = np.asarray(signed_warning_m, dtype=float)
    ang = np.asarray(angle_rad, dtype=float)
    D = float(near_band_width_m)
    if t.ndim != 1 or sd.shape != t.shape or ang.shape != t.shape:
        raise ValueError("time_us、signed_warning_m、angle_rad 必须是同长一维数组")
    if len(t) == 0:
        raise ValueError("空窗口（结构错误，不能当作通过）")
    if not np.issubdtype(t.dtype, np.integer):
        raise ValueError("time_us 必须是整数微秒")
    if len(t) > 1 and not np.all(np.diff(t) == FRAME_US):
        raise ValueError("time_us 必须严格 10 Hz 递增")
    if not (np.all(np.isfinite(sd)) and np.all(np.isfinite(ang))):
        raise ValueError("有符号距离或方位含 NaN/Inf")
    if not (math.isfinite(D) and D > 0.0):
        raise ValueError("near_band_width_m 必须为正有限数")
    alpha = np.unwrap(ang)
    b = (sd > 0.0) & (sd <= D)
    prev = np.r_[False, b[:-1]]
    entries = np.flatnonzero(b & ~prev)
    exits = np.flatnonzero(~b & prev)
    edges = np.flatnonzero(np.diff(np.r_[False, b, False].astype(np.int8)))
    runs = []
    for a, e in zip(edges[::2].tolist(), edges[1::2].tolist()):
        seg = alpha[a:e]
        span = float(np.degrees(seg.max() - seg.min()))
        net = float(np.degrees(abs(seg[-1] - seg[0])))
        runs.append({"start_index": int(a), "stop_index": int(e), "entry_us": int(t[a]),
                     "exit_us": int(t[e]) if e < len(t) else None, "span_deg": span, "net_deg": net})
    best = None
    for i, r in enumerate(runs):
        if best is None or r["span_deg"] > runs[best]["span_deg"]:
            best = i
    return {"runs": runs,
            "max_span_deg": 0.0 if best is None else runs[best]["span_deg"],
            "best_net_deg": 0.0 if best is None else runs[best]["net_deg"],
            "best_run": best,
            "entry_count": int(len(entries)), "exit_count": int(len(exits)),
            "first_entry_us": int(t[entries[0]]) if len(entries) else None,
            "last_exit_us": int(t[exits[-1]]) if len(exits) else None,
            "starts_in_band": bool(b[0]), "ends_in_band": bool(b[-1])}


def target_sweep_conditions(series, candidate, nominal=False, generation=None):
    """仅目标扫角/次数三项子条件（不冒充完整核验）：single_near_visit、min_sweep、max_sweep。
    候选：下限 Θ（含等号）、上限 < max_sweep_deg_exclusive；名义：下限 Θ + nominal_sweep_margin_deg、
    上限 < nominal_max_sweep_deg_exclusive。上限检查全部区间，不只读获胜区间。未舍入 float64 比较。"""
    C = _values(candidate)
    if nominal:
        if generation is None:
            raise ValueError("名义口径需要生成配置")
        G = _values(generation)
        lo = float(C["min_sweep_deg"]) + float(G["nominal_sweep_margin_deg"])
        hi = float(G["nominal_max_sweep_deg_exclusive"])
    else:
        lo = float(C["min_sweep_deg"])
        hi = float(C["max_sweep_deg_exclusive"])
    spans = [float(r["span_deg"]) for r in series["runs"]]
    return {"single_near_visit": int(series["entry_count"]) == 1,
            "min_sweep": bool(float(series["max_span_deg"]) >= lo),
            "max_sweep": bool(all(s < hi for s in spans))}


def group_sweep(member_maxima):
    """member_maxima[成员][设施] = 该成员对该设施的最大 span。G_f = min_i，S_all = max_f G_f。
    成员集非空、每成员设施集合相同且非空；缺失直接 ValueError（不能用空集得到通过）。"""
    if not member_maxima:
        raise ValueError("成员集为空")
    facilities = None
    for mid, row in member_maxima.items():
        keys = set(row)
        if not keys:
            raise ValueError(f"成员 {mid} 没有设施扫角")
        if facilities is None:
            facilities = keys
        elif keys != facilities:
            raise ValueError("各成员的设施集合不同")
    by_fac = {f: float(min(float(member_maxima[m][f]) for m in member_maxima)) for f in sorted(facilities)}
    return {"by_facility": by_fac, "S_all": float(max(by_fac.values()))}


# ---------------------------------------------------------------- 弧端点与解析圆角（指令 3.3–3.4；裁定 2）

def J(v):
    v = np.asarray(v, float)
    return np.array([-v[1], v[0]])


def polar_endpoint(center, rho, drho, phi, sigma):
    """p = c + ρ e_r；T_σ = σ(ρ' e_r + ρ e_φ)/√(ρ'² + ρ²)。"""
    c = np.asarray(center, float)
    er = np.array([math.cos(phi), math.sin(phi)])
    ep = np.array([-math.sin(phi), math.cos(phi)])
    t = float(sigma) * (float(drho) * er + float(rho) * ep)
    return {"point_xy": c + float(rho) * er, "tangent_xy": t / float(np.hypot(*t))}


def fillet_from_pose(P, T, U, R, straight_m, entering):
    """圆角+直线接到已知位姿。entering=True：直线沿 U 到 A，圆弧 A→B，直线 B→P（方向 T）；False：P→A 沿 T，
    圆弧 A→B，再沿 U 离开。δ 为 incoming→outgoing 的有符号最短转角；δ=0 时 A=B、无圆弧；平行反向抛 ValueError。"""
    P, T, U = (np.asarray(x, float) for x in (P, T, U))
    T, U = T / np.hypot(*T), U / np.hypot(*U)
    R, L = float(R), float(straight_m)
    cross = lambda a, b: float(a[0] * b[1] - a[1] * b[0])     # noqa: E731
    if entering:
        B = P - L * T
        delta = math.atan2(cross(U, T), float(np.dot(U, T)))
    else:
        A = P + L * T
        delta = math.atan2(cross(T, U), float(np.dot(T, U)))
    if abs(abs(delta) - math.pi) < 1e-12:
        raise ValueError("平行反向，不能构造有限圆角")
    a = R * math.tan(abs(delta) / 2.0)
    eps = 1.0 if delta > 0 else (-1.0 if delta < 0 else 0.0)
    if entering:
        A = B - a * (T + U)
        V = B - a * T
        O = B + eps * R * J(T)
        incoming, outgoing = U, T
    else:
        B = A + a * (T + U)
        V = A + a * T
        O = A + eps * R * J(T)
        incoming, outgoing = T, U
    prims = []
    if eps != 0.0:
        a0 = math.atan2(A[1] - O[1], A[0] - O[0])
        prims.append(("arc", (float(O[0]), float(O[1])), R, float(a0), float(delta)))
    if entering:
        prims.append(("line", (float(B[0]), float(B[1])), (float(P[0]), float(P[1]))))
    else:
        prims.insert(0, ("line", (float(P[0]), float(P[1])), (float(A[0]), float(A[1]))))
    return {"point_xy": P, "tangent_xy": T, "line_direction_xy": U, "fillet_center_xy": O if eps else None,
            "fillet_start_xy": A, "fillet_end_xy": B, "vertex_xy": V, "turn_angle_rad": float(delta),
            "tangent_length_m": float(a), "straight_m": L, "radius_m": R, "incoming_xy": incoming,
            "outgoing_xy": outgoing, "primitives": tuple(prims)}


def oblique_direction(T, P, center, beta_rad, entering):
    """裁定 2：β 相对弧端点实际切向 T；n_c 为 T 的两个单位法向中指向设施中心一侧者。
    进场 u_in = cos β T + sin β n_c；离开 u_out = cos β T − sin β n_c。"""
    T = np.asarray(T, float)
    T = T / np.hypot(*T)
    jt = J(T)
    s = float(np.dot(np.asarray(center, float) - np.asarray(P, float), jt))
    n_c = (1.0 if s >= 0.0 else -1.0) * jt
    if entering:
        return math.cos(beta_rad) * T + math.sin(beta_rad) * n_c, n_c
    return math.cos(beta_rad) * T - math.sin(beta_rad) * n_c, n_c


def fillet_radius(H, G, turn_u_min_m):
    """R_f = max(fillet_floor_m, fillet_span_factor (H + turn_u_min_m))。"""
    return max(float(G["fillet_floor_m"]), float(G["fillet_span_factor"]) * (float(H) + float(turn_u_min_m)))


# ---------------------------------------------------------------- 方位段（裁定 3）与 Σ 区间（裁定 1）

def segment_span_deg(rows):
    """n 个连续 1° 行的几何跨度为 n − 1 度。"""
    return float(len(rows) - 1)


def sigma_upper(span_deg, G, *, periodic):
    """裁定 1：Σ_hi = min(方位段跨度 − arc_edge_guard_deg, construction_sweep_cap_deg)；全 360 行时为 350。"""
    cap = float(G["construction_sweep_cap_deg"])
    if periodic:
        return cap
    return min(float(span_deg) - float(G["arc_edge_guard_deg"]), cap)


def rows_needed(sigma_deg):
    """裁定 3：Σ 需要 ⌈Σ⌉ + 1 行。"""
    return int(math.ceil(float(sigma_deg) - 1e-12)) + 1


def start_candidates(segments, n_rows, *, periodic):
    """全部 (段, 起始行) 对（稳定排序）。非周期段 rows 为展开递增整数行；起始行 k 使 [k, k+n_rows−1] 落在段内。
    周期（全 360 行）时为 360 个起始行。"""
    out = []
    if periodic:
        return [(0, k) for k in range(360)]
    for sid, seg in enumerate(segments):
        rows = seg["rows"]
        for i in range(len(rows) - n_rows + 1):
            out.append((sid, int(rows[i])))
    return out


def lp_start_candidates(query, n_rows):
    """Ruling 2/6: each certified (parent,start) once, never weight by endpoint count."""
    out = []
    for parent in query["parents"]:
        for s, end in enumerate(parent["max_end"]):
            if int(end) - s >= int(n_rows) - 1:
                out.append((int(parent["id"]), int(parent["ids"][s])))
    return sorted(out)


# ---------------------------------------------------------------- 检查点数值（指令 5；裁定 5）

def _median(values):
    v = sorted(values)
    n = len(v)
    if n == 0:
        return None
    return float(v[n // 2]) if n % 2 else 0.5 * (float(v[n // 2 - 1]) + float(v[n // 2]))


def size_band(n):
    return "1-4" if n <= 4 else ("5-8" if n <= 8 else "9-12")


class TraceRng:
    """测试与审计用 RNG 记录器：透传 numpy Generator，按调用次序记录 (purpose, method, 参数)。"""

    def __init__(self, rng, purpose, log=None):
        self._rng, self.purpose = rng, purpose
        self.log = [] if log is None else log

    def _call(self, name, *args, **kw):
        self.log.append((self.purpose, name, tuple(args), tuple(sorted(kw.items()))))
        return getattr(self._rng, name)(*args, **kw)

    def integers(self, *a, **k):
        return self._call("integers", *a, **k)

    def uniform(self, *a, **k):
        return self._call("uniform", *a, **k)

    def random(self, *a, **k):
        return self._call("random", *a, **k)

    def permutation(self, *a, **k):
        return self._call("permutation", *a, **k)

    def choice(self, *a, **k):
        return self._call("choice", *a, **k)

    def shuffle(self, *a, **k):
        return self._call("shuffle", *a, **k)
