"""V8-13 合成标定（指令 2.2 与 3.4）：跟踪参考测量与优化器数值标定。不读真实场景、不导入 shapely。

第 2 部分（make_tracking_cases / measure_tracking_cases）：
- 直线（静止加速 → 匀速 → 刹停 → 2 s 保持）：解析七段 S 曲线（A=2、请求 V、扫描 J），转三次 B 样条
  （两端钳制、内部单节点），Greville 点带状插值求系数，再复核各段多项式；时间 ×α=A/J、空间 ×β=A³/J²。
- 近圆：θ = 2πK·S(t/T)，S 为五次 smoothstep。法向目标按附录裁定 9.1 取 a_n = min(3, √(J·V))；
  a_n < 3 的格点标 jerk_limited。均匀三次 B 样条带端点 p/v/a 等式的最小二乘拟合（20 ms 点），
  再按 α = V·A_nb/(a_n·V_b)、β = V·α/V_b 缩放；切向 > 2 或 jerk > J 时 K 倍增。
- U 形：θ = π·S(t/T)、R=15，V ∈ {4, 6, min(10, √45)}；先按最小曲率半径归一到 15 m，
  再 α = max(V_b/V, √(A_nb/3), √(A_tb/2), ∛(J_b/J)) 缩放时间。
所有峰值均从最终系数按区间多项式求连续极值（optimize_checks.dynamic_extrema）。
"""
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

from ..motion.optimize_checks import curvature_radius_min, dynamic_extrema
from ..sim.tracking import TimeReference, run_tracking_segment, select_jerk_plan
from ..sim.types import MemberBoundaryState

EPS = float(np.finfo(np.float64).eps)
JERK_SCAN = (2.0, 4.0, 6.0, 8.0, 10.0, 14.0)        # U D.1.3；r4 6.6、6.8
SPEEDS = (4.0, 6.0, 8.0, 10.0)                      # U D.1 范围与 D.4 分档边界
A_N_CAP = 3.0                                       # guidance.a_lat_m_s2
A_T_CAP = 2.0                                       # guidance.a_lon_m_s2
UTURN_R = 15.0                                      # r4 6.3.5 U 形掉头半径
TUBE_M = 0.5                                        # U D.1.4 管半径（只用于检查点 1）
# 合成夹具：起点、高度、释放（initial_settle 20 s + 延迟 0）。不是业务配置。
FIX_START = (0.0, 0.0)
FIX_ALT = 100.0
FIX_RELEASE = 20.0
FIT_DT = 0.02                                       # 冻结积分步 20 ms（拟合采样点）
PROTO_KNOT_S = 1.0                                  # 原型拟合节点间隔：U D.2.1 的 1 s 表示（缩放后记录实际值）


# ---------------------------------------------------------------- 参考对象

class SplineRef:
    """局部秒样条 → 绝对时钟 pva；域外 p 保持端点、导数为零（不外推最后多项式）。"""

    def __init__(self, knots, controls, T, release_s=FIX_RELEASE, start=FIX_START):
        from scipy.interpolate import BSpline
        self.knots = np.asarray(knots, float)
        self.controls = np.asarray(controls, float)
        self.T = float(T)
        self.release = float(release_s)
        self.offset = np.asarray(start, float)
        self._b = BSpline(self.knots, self.controls, 3, extrapolate=False)
        self._d = [self._b.derivative(k) for k in (1, 2)]
        self.p0 = self._b(0.0) + self.offset
        self.p1 = self._b(self.T) + self.offset

    def pva(self, t_abs):
        t = np.asarray(t_abs, float) - self.release
        scalar = t.ndim == 0
        t = np.atleast_1d(t)
        inside = (t >= 0.0) & (t <= self.T)
        tc = np.clip(t, 0.0, self.T)
        p = self._b(tc) + self.offset
        v = np.where(inside[:, None], self._d[0](tc), 0.0)
        a = np.where(inside[:, None], self._d[1](tc), 0.0)
        p = np.where((t < 0.0)[:, None], self.p0, p)
        p = np.where((t > self.T)[:, None], self.p1, p)
        if scalar:
            return p[0], v[0], a[0]
        return p, v, a

    def reference(self, member="m"):
        return TimeReference(member, self.release, self.release + self.T, FIX_ALT, self.pva)


def _peaks(knots, controls, T):
    d = dynamic_extrema(knots, controls, 0.0, T)
    return {k: d[k]["value"] for k in ("speed", "tangential", "normal", "jerk", "accel")}


def _hash(knots, controls):
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(knots, dtype="<f8").tobytes())
    h.update(np.ascontiguousarray(controls, dtype="<f8").tobytes())
    return h.hexdigest()


# ---------------------------------------------------------------- 直线 S 曲线

def _scurve_pieces(V, J, A=A_T_CAP):
    """无量纲七段：jerk [1,0,-1,0,-1,0,1]，段长 [1,c,1,b,1,c,1]，b = V·J/A²，c = b − 1。"""
    b = V * J / A ** 2
    c = b - 1.0
    if c < 0.0:
        return None
    jerks = [1.0, 0.0, -1.0, 0.0, -1.0, 0.0, 1.0]
    durs = [1.0, c, 1.0, b, 1.0, c, 1.0]
    pieces, t, p, v, a = [], 0.0, 0.0, 0.0, 0.0
    for j, d in zip(jerks, durs):
        pieces.append((t, d, p, v, a, j))
        p, v, a = p + v * d + a * d * d / 2 + j * d ** 3 / 6, v + a * d + j * d * d / 2, a + j * d
        t += d
    return pieces, t


def _piece_eval(pieces, t):
    out = np.empty_like(t)
    for k, (t0, d, p, v, a, j) in enumerate(pieces):
        last = k == len(pieces) - 1
        m = (t >= t0) & ((t < t0 + d) | last)
        u = t[m] - t0
        out[m] = p + v * u + a * u * u / 2 + j * u ** 3 / 6
    return out


def make_line_case(V, J, A=A_T_CAP):
    from scipy.interpolate import BSpline
    from scipy.linalg import solve_banded
    built = _scurve_pieces(V, J, A)
    if built is None:
        return {"kind": "line", "requested_speed": V, "jerk_cap": J, "valid": False,
                "reason": "c<0：平台段为负"}
    pieces, Tn = built
    bps = sorted({p[0] for p in pieces[1:] if p[1] > 0.0} | {p[0] + p[1] for p in pieces[:-1] if p[1] > 0.0})
    bps = [b for b in bps if 0.0 < b < Tn]
    knots = np.r_[[0.0] * 4, bps, [Tn] * 4]
    n = len(knots) - 4
    grev = np.array([knots[i + 1:i + 4].mean() for i in range(n)])
    Bm = BSpline.design_matrix(grev, knots, 3).toarray()
    ab = np.zeros((7, n))
    for i in range(n):
        for jcol in range(max(0, i - 3), min(n, i + 4)):
            ab[3 + i - jcol, jcol] = Bm[i, jcol]
    coef = solve_banded((3, 3), ab, _piece_eval(pieces, grev))
    # 复核：各段多项式一致（在每段内取多点）
    chk_t = np.concatenate([p[0] + np.linspace(0.0, p[1], 9) for p in pieces if p[1] > 0.0])
    resid = float(np.max(np.abs(BSpline(knots, coef, 3)(chk_t) - _piece_eval(pieces, chk_t))))
    alpha, beta = A / J, A ** 3 / J ** 2
    knots_s = knots * alpha
    ctrl = np.column_stack([coef * beta, np.zeros(n)])
    T = Tn * alpha
    bounds = np.cumsum([0.0] + [p[1] for p in pieces]) * alpha
    pk = _peaks(knots_s, ctrl, T)
    return {"kind": "line", "requested_speed": V, "jerk_cap": J, "valid": True, "knots": knots_s,
            "controls": ctrl, "T": T, "alpha": alpha, "beta": beta, "K": None,
            "piecewise_residual_dimless": resid, "peaks": pk,
            "windows": {"accel": [0.0, bounds[3]], "cruise": [bounds[3], bounds[4]], "brake": [bounds[4], T]},
            "requested_normal": 0.0, "jerk_limited": False}


# ---------------------------------------------------------------- 均匀样条带端点等式的最小二乘

def _uniform_fit(proto, T, h_target=PROTO_KNOT_S):
    """均匀三次 B 样条，节点 h·(−3..M+3)，h = T/M，M = ceil(T/h_target)；20 ms 点最小二乘。
    两端静止（p 给定、v=a=0）的等式用精确消元：均匀三次样条在节点 0 处 p=(c0+4c1+c2)/6、
    v=(c2−c0)/(2h)、a=(c0−2c1+c2)/h²，故 c0=c1=c2=p(0)；末端同理 c_M=c_{M+1}=c_{M+2}=p(T)。
    其余系数由法方程（带状，半带宽 3）直接求解。返回 (knots, controls, h, T_eff)。"""
    from scipy.interpolate import BSpline
    from scipy.linalg import solveh_banded
    M = max(1, math.ceil(T / h_target - 1e-12))
    h = T / M
    knots = h * np.arange(-3, M + 4, dtype=float)
    T_eff = float(knots[M + 3])
    n = M + 3
    nfit = int(round(T / FIT_DT))
    ts = np.linspace(0.0, T_eff, nfit + 1)
    B = BSpline.design_matrix(ts, knots, 3).toarray()
    P, Vv, Aa = proto(ts * (T / T_eff))
    p0, p1 = P[0], P[-1]
    if np.any(np.abs(Vv[[0, -1]]) > 0) or np.any(np.abs(Aa[[0, -1]]) > 0):
        raise ValueError("原型端点不是静止的")
    coef = np.zeros((n, 2))
    coef[:3] = p0
    coef[M:] = p1
    free = np.arange(3, M)
    if len(free):
        Bf = B[:, free]
        rhs = P - B[:, :3] @ coef[:3] - B[:, M:] @ coef[M:]
        N = Bf.T @ Bf
        k = len(free)
        ab = np.zeros((4, k))
        for d in range(4):
            ab[3 - d, d:] = np.diagonal(N, d)
        coef[free] = solveh_banded(ab, Bf.T @ rhs)
    return knots, coef, h, T_eff


def _smoothstep(u):
    return 10 * u ** 3 - 15 * u ** 4 + 6 * u ** 5, 30 * u ** 2 - 60 * u ** 3 + 30 * u ** 4, \
        60 * u - 180 * u ** 2 + 120 * u ** 3


def _arc_proto(R, theta_total, T):
    def proto(ts):
        u = ts / T
        S, dS, ddS = _smoothstep(u)
        th = theta_total * S
        w = theta_total * dS / T
        al = theta_total * ddS / T ** 2
        er = np.column_stack([np.cos(th), np.sin(th)])
        et = np.column_stack([-np.sin(th), np.cos(th)])
        p = R * (er - np.array([1.0, 0.0]))
        v = R * w[:, None] * et
        a = R * (al[:, None] * et - (w ** 2)[:, None] * er)
        return p, v, a
    return proto


def _scaled(knots, ctrl, time_scale, space_scale):
    return knots * time_scale, ctrl * space_scale


def make_circle_case(V, J, *, k_max_doublings=None):
    a_target = min(A_N_CAP, math.sqrt(J * V))
    limited = a_target < A_N_CAP
    R0 = V * V / a_target
    K = 1
    tried = []
    max_dbl = k_max_doublings if k_max_doublings is not None else int(-math.log2(EPS))
    for _ in range(max_dbl + 1):
        T0 = (15.0 / 8.0) * 2 * math.pi * K * R0 / V
        knots, ctrl, h, T0 = _uniform_fit(_arc_proto(R0, 2 * math.pi * K, T0), T0)
        pb = _peaks(knots, ctrl, T0)
        alpha = V * pb["normal"] / (a_target * pb["speed"])
        beta = V * alpha / pb["speed"]
        kn, cs = _scaled(knots, ctrl, alpha, beta)
        T = T0 * alpha
        pk = _peaks(kn, cs, T)
        tried.append({"K": K, "peaks": pk})
        if pk["tangential"] <= A_T_CAP and (pk["jerk"] <= J or limited):
            break
        K *= 2
    else:
        return {"kind": "circle", "requested_speed": V, "jerk_cap": J, "valid": False,
                "reason": "K 倍增达 float64 上限仍超限", "tried": tried}
    stretch = 1.0
    if limited:
        # 附录 9.1：恒速段 jerk = a_n²/v = J，起止过渡使峰值 jerk 严格大于 J，K 倍增不能终止（与指令 2.2
        # "9/V>J 不做无意义倍增"同理）。保持峰值速度不变，空间与时间同乘 f=√(j_peak/J)，使 jerk ≤ J；
        # 实际法向随之略低于 √(J·V)，如实报告。
        for _ in range(8):
            if pk["jerk"] <= J:
                break
            f = math.sqrt(pk["jerk"] / J) * (1.0 + 4 * EPS)
            kn, cs, T = kn * f, cs * f, T * f
            stretch *= f
            pk = _peaks(kn, cs, T)
    for _ in range(8):
        # 舍入使法向比目标高 1 ulp 时，保持速度、空间与时间同乘 f（法向 ∝ 1/f）。只吸收舍入，不是新阈值。
        if pk["normal"] <= a_target:
            break
        f = pk["normal"] / a_target * (1.0 + 4 * EPS)
        kn, cs, T = kn * f, cs * f, T * f
        stretch *= f
        pk = _peaks(kn, cs, T)
    valid = pk["tangential"] <= A_T_CAP and pk["jerk"] <= J and pk["normal"] <= A_N_CAP and pk["speed"] <= 12.0
    return {"kind": "circle", "requested_speed": V, "jerk_cap": J, "valid": bool(valid),
            "reason": None if valid else "缩放后峰值超限", "knots": kn, "controls": cs, "T": T,
            "alpha": alpha, "beta": beta, "K": K, "stretch_jerk_limited": stretch, "fit_knot_s": h * alpha * stretch,
            "peaks": pk, "requested_normal": a_target, "jerk_limited": limited, "tried": tried,
            "windows": _speed_windows(kn, cs, T)}


def make_uturn_case(V, J):
    T0 = (15.0 / 8.0) * math.pi * UTURN_R / V
    knots, ctrl, h, T0 = _uniform_fit(_arc_proto(UTURN_R, math.pi, T0), T0)
    # 首末节点区间由 c0=c1=c2（c_M=c_{M+1}=c_{M+2}）精确消元，数学上是直线段（曲率 0）；
    # 在 v→0 处浮点残差会把 cross²/|v|⁶ 放大成伪曲率，故最小曲率半径只在 [h, T−h] 上求。
    rho, _ = curvature_radius_min(knots, ctrl, h, T0 - h)
    sig = UTURN_R / rho
    ctrl = ctrl * sig
    pb = _peaks(knots, ctrl, T0)
    alpha = max(pb["speed"] / V, math.sqrt(pb["normal"] / A_N_CAP), math.sqrt(pb["tangential"] / A_T_CAP),
                (pb["jerk"] / J) ** (1.0 / 3.0))
    kn, T = knots * alpha, T0 * alpha
    pk = _peaks(kn, ctrl, T)
    for _ in range(8):
        over = max(pk["speed"] / V, pk["normal"] / A_N_CAP, pk["tangential"] / A_T_CAP, pk["jerk"] / J)
        if over <= 1.0:
            break
        f = over * (1.0 + 4 * EPS)
        kn, T = kn * f, T * f
        alpha *= f
        pk = _peaks(kn, ctrl, T)
    rho2, _ = curvature_radius_min(kn, ctrl, h * alpha, T - h * alpha)
    valid = pk["speed"] <= V and pk["normal"] <= A_N_CAP and pk["tangential"] <= A_T_CAP and pk["jerk"] <= J
    return {"kind": "uturn", "requested_speed": V, "jerk_cap": J, "valid": bool(valid),
            "reason": None if valid else "缩放后峰值超限", "knots": kn, "controls": ctrl, "T": T,
            "alpha": alpha, "beta": sig, "K": 0.5, "fit_knot_s": h * alpha, "peaks": pk,
            "min_radius_m": rho2, "requested_normal": None, "jerk_limited": False,
            "windows": _speed_windows(kn, ctrl, T)}


def _speed_windows(knots, ctrl, T):
    d = dynamic_extrema(knots, ctrl, 0.0, T)
    tp = d["speed"]["t_local_s"]
    return {"accel": [0.0, tp], "brake": [tp, T]}


def make_tracking_cases(jerk_cap, *, speeds=SPEEDS):
    """一个 J 的合法格点全集（附录裁定 9.1）：直线 4 速、近圆 4 速（a_n=min(3,√(J·V))）、U 形 3 速。"""
    cases = []
    for V in speeds:
        cases.append(make_line_case(V, jerk_cap))
    for V in speeds:
        cases.append(make_circle_case(V, jerk_cap))
    for V in (4.0, 6.0, min(10.0, math.sqrt(A_N_CAP * UTURN_R))):
        cases.append(make_uturn_case(V, jerk_cap))
    for c in cases:
        if c.get("valid"):
            c["reference_sha256"] = _hash(c["knots"], c["controls"])
    return cases


# ---------------------------------------------------------------- 测量

def _window_max(rec, lo_us, hi_us):
    t = rec.step_t_us
    m = (t >= lo_us) & (t < hi_us)
    if not np.any(m):
        return None
    return {"pos_m": float(rec.step_pos_err_m[m].max()), "vel_m_s": float(rec.step_vel_err_m_s[m].max())}


def run_case(case):
    ref = SplineRef(case["knots"], case["controls"], case["T"])
    state = MemberBoundaryState("m", 0, 0, (FIX_START[0], FIX_START[1], FIX_ALT), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    res = run_tracking_segment(ref.reference(), state, final=True)
    rec = res.pieces[0]
    r_us = rec.release_us
    end_us = r_us + int(round(case["T"] * 1e6))
    windows = {"prerelease": _window_max(rec, 0, r_us)}
    for name, (a, b) in case["windows"].items():
        windows[name] = _window_max(rec, r_us + int(round(a * 1e6)), r_us + int(round(b * 1e6)))
    windows["after_end"] = _window_max(rec, end_us, rec.tau_end_us + 1)
    if rec.hold_start_us is not None:
        windows["hold"] = _window_max(rec, rec.hold_start_us, rec.tau_end_us + 1)
    d10 = np.diff(res.a[:, :2], axis=0) / 0.1
    return {
        "status": res.status,
        "max_step_pos_err_m": rec.max_step_pos_err_m, "max_step_vel_err_m_s": rec.max_step_vel_err_m_s,
        "max_frame_pos_err_m": rec.max_frame_pos_err_m, "max_frame_vel_err_m_s": rec.max_frame_vel_err_m_s,
        "accel_saturated_fraction": rec.accel_saturated_fraction,
        "jerk_saturated_fraction": rec.jerk_saturated_fraction,
        "max_core_jerk_xy": float(rec.step_jerk_xy.max()), "max_core_accel_xy": float(rec.step_accel_xy.max()),
        "max_10hz_diff_jerk_xy": float(np.linalg.norm(d10, axis=1).max()) if len(d10) else 0.0,
        "end_p": rec.end_p, "end_v": rec.end_v, "hold_start_us": rec.hold_start_us,
        "tau_end_us": rec.tau_end_us, "budget_s": rec.budget_s, "frames": int(len(res.tau_us)),
        "windows": windows, "wall_s": rec.wall_s,
    }


def _case_public(c):
    out = {k: v for k, v in c.items() if k not in ("knots", "controls", "tried")}
    if "tried" in c:
        out["tried"] = c["tried"]
    if c.get("valid"):
        out["knots"] = np.asarray(c["knots"]).tolist()
        out["controls"] = np.asarray(c["controls"]).tolist()
        out["control_count"] = int(len(c["controls"]))
    return out


def measure_tracking_cases(*, out_dir, jerks=JERK_SCAN, log=print):
    """跑全部 J × 合法格点；out_dir 必须由调用方已检查（不存在的新目录）。返回汇总 dict。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=False)
    rows, all_cases = [], []
    t0 = time.perf_counter()
    for J in jerks:
        cases = make_tracking_cases(J)
        complete = True
        worst = {"pos": 0.0, "vel": 0.0, "frame_pos": 0.0, "frame_vel": 0.0}
        worst_case = None
        sat_a = sat_j = 0.0
        for c in cases:
            pub = _case_public(c)
            if not c.get("valid"):
                complete = False
                pub["measurement"] = None
            else:
                m = run_case(c)
                pub["measurement"] = m
                if m["status"] != "ok":
                    complete = False
                if m["max_step_pos_err_m"] > worst["pos"]:
                    worst["pos"] = m["max_step_pos_err_m"]
                    worst_case = f'{c["kind"]}@{c["requested_speed"]:g}'
                worst["vel"] = max(worst["vel"], m["max_step_vel_err_m_s"])
                worst["frame_pos"] = max(worst["frame_pos"], m["max_frame_pos_err_m"])
                worst["frame_vel"] = max(worst["frame_vel"], m["max_frame_vel_err_m_s"])
                sat_a = max(sat_a, m["accel_saturated_fraction"])
                sat_j = max(sat_j, m["jerk_saturated_fraction"])
                log(f"J={J:g} {c['kind']:6s} V={c['requested_speed']:.3f} peaks="
                    f"v{c['peaks']['speed']:.3f}/at{c['peaks']['tangential']:.3f}/an{c['peaks']['normal']:.3f}/"
                    f"j{c['peaks']['jerk']:.3f} T={c['T']:.2f} err={m['max_step_pos_err_m']:.4f} "
                    f"frame={m['max_frame_pos_err_m']:.4f} status={m['status']}")
            pub["jerk_scan"] = J
            all_cases.append(pub)
        rows.append({"jerk": J, "max_error_m": worst["pos"], "complete": complete,
                     "max_frame_error_m": worst["frame_pos"], "max_vel_error_m_s": worst["vel"],
                     "max_frame_vel_error_m_s": worst["frame_vel"], "worst_case": worst_case,
                     "max_accel_saturated_fraction": sat_a, "max_jerk_saturated_fraction": sat_j,
                     "cases": len(cases), "valid_cases": sum(bool(c.get("valid")) for c in cases)})
    choice = select_jerk_plan(rows, tube_m=TUBE_M)
    summary = {"rows": rows, "choice": choice, "tube_m": TUBE_M, "wall_s": time.perf_counter() - t0,
               "coverage_rule": "附录裁定 9.1：每个 J 的测量全集 = 直线 4/6/8/10、近圆 4/6/8/10（a_n=min(3,√(J·V))）、"
                                "U 形 4/6/√45"}
    data = json.dumps(all_cases, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8") + b"\n"
    (out / "cases.json").write_bytes(data)
    summary["cases_sha256"] = hashlib.sha256(data).hexdigest()
    sdata = json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8") + b"\n"
    (out / "summary.json").write_bytes(sdata)
    return summary


# ================================================================ 第 3 部分：优化器数值标定（指令 3.4）
# 合成夹具：与第 6.2 节同一构造（五次 smoothstep 静止到静止），在本模块独立实现，不从测试导入。

def _rest_move(member, start, finish, duration, release=FIX_RELEASE):
    start, finish = np.asarray(start, float), np.asarray(finish, float)
    delta = finish - start

    def pva(t):
        raw = (np.asarray(t, float) - release) / duration
        u = np.clip(raw, 0.0, 1.0)
        f = 10 * u ** 3 - 15 * u ** 4 + 6 * u ** 5
        df = (30 * u ** 2 - 60 * u ** 3 + 30 * u ** 4) / duration
        ddf = (60 * u - 180 * u ** 2 + 120 * u ** 3) / duration ** 2
        active = (raw >= 0.0) & (raw <= 1.0)
        return (start + f[..., None] * delta, (df * active)[..., None] * delta, (ddf * active)[..., None] * delta)
    return TimeReference(member, release, release + duration, FIX_ALT, pva)


def _excess_normal():
    def pva(t):
        t = np.asarray(t, float) - FIX_RELEASE
        u = np.clip(t / 8.0, 0.0, 1.0)
        theta = 80.0 * (10 * u ** 3 - 15 * u ** 4 + 6 * u ** 5)
        w = 10.0 * (30 * u ** 2 - 60 * u ** 3 + 30 * u ** 4)
        aa = (80.0 / 64.0) * (60 * u - 180 * u ** 2 + 120 * u ** 3)
        er = np.stack([np.cos(theta), np.sin(theta)], axis=-1)
        et = np.stack([-np.sin(theta), np.cos(theta)], axis=-1)
        return er, w[..., None] * et, aa[..., None] * et - w[..., None] ** 2 * er
    return TimeReference("a", FIX_RELEASE, FIX_RELEASE + 8.0, FIX_ALT, pva)


def calibration_fixtures(d_lane):
    """(名称, 构造函数, 应成功, 恒定)。大夹具：N 人 = N/2 对互换直线，第 k 对横向平移 k·D_lane，
    时长 1000/2000 s，空间长度 = 4 m/s × 时长（J 第 3 节交叉参考）。"""
    from ..motion.optimize import JointProblem
    from ..scene.field import Clearance, build_distance_field

    def const(T):
        return lambda: JointProblem((_rest_move("a", (6.25, -2.5), (6.25, -2.5), T),))

    def swap():
        return JointProblem((_rest_move("a", (-30.0, 0.0), (30.0, 0.0), 60.3),
                             _rest_move("b", (30.0, 0.0), (-30.0, 0.0), 60.3)))

    def circle():
        cs = (Clearance("obstacle:c", {"type": "Circle", "center_m": [0.0, 0.0], "radius_m": 10.0}, 1, 35.0),)
        field = build_distance_field(cs, (-200.0, -200.0, 200.0, 200.0), spacing_m=5.0)
        return JointProblem((_rest_move("a", (-100.0, 0.0), (100.0, 0.0), 120.3),), cs, field)

    def line():
        ref = _rest_move("a", (0.0, 0.0), (20.0, 0.0), 30.3)
        return JointProblem((ref,), lines=(("a", ref.release_s, ref.end_s, (0.0, 0.0), (1.0, 0.0)),))

    def excess():
        return JointProblem((_excess_normal(),))

    def cross(N, T):
        def build():
            L = 4.0 * T
            refs = []
            for k in range(N // 2):
                y = k * d_lane
                refs.append(_rest_move(f"m{2 * k:02d}", (-L / 2, y), (L / 2, y), T))
                refs.append(_rest_move(f"m{2 * k + 1:02d}", (L / 2, y), (-L / 2, y), T))
            return JointProblem(tuple(refs))
        return build

    return [("constant_8.3s", const(8.3), True, True), ("constant_2000.3s", const(2000.3), True, True),
            ("line_equality", line, True, False), ("head_on_swap", swap, True, False),
            ("circle_obstacle", circle, True, False), ("excess_normal", excess, False, False),
            ("cross_4x1000s", cross(4, 1000.0), True, False), ("cross_4x2000s", cross(4, 2000.0), True, False),
            ("cross_12x1000s", cross(12, 1000.0), True, False), ("cross_12x2000s", cross(12, 2000.0), True, False)]


def _peak_rss():
    try:
        import psutil
        mi = psutil.Process().memory_info()
        return int(getattr(mi, "peak_wset", mi.rss))
    except Exception:
        return None


def _summarize_solution(sol, lim, settings):
    d = sol.diagnostics
    phys = d.get("physical") or {}
    sep = (phys.get("separation") or {}).get("min_m")
    clear = [v["min_margin_m"] for per in (phys.get("clearances") or {}).values() for v in per.values()
             if v["min_margin_m"] is not None]
    dyn = phys.get("dynamic_extrema") or {}
    f = settings["buffer_dynamic_factor"]
    peaks = {}
    for q, cap in (("speed", lim["v_max"]), ("tangential", lim["a_t"]), ("normal", lim["a_n"]), ("jerk", lim["jerk"])):
        vals = [dd[q]["value"] for dd in dyn.values()]
        if vals:
            peaks[q] = {"max": max(vals), "cap": cap, "buffered_cap": f * cap, "ratio_to_cap": max(vals) / cap}
    endp = max((max(e["errors"].values()) for e in (phys.get("endpoints") or {}).values()), default=None)
    return {
        "ok": sol.ok, "reason": sol.reason, "nit": d.get("nit"), "nfev": d.get("nfev"), "message": d.get("message"),
        "lbfgs_success": d.get("success"), "value": d.get("value"), "terms": d.get("terms"),
        "max_abs_projected_grad": d.get("max_abs_grad"), "reference_deviation": d.get("reference_deviation"),
        "residual_vs_original": {"separation_min_minus_3": None if sep is None else sep - lim["d_lane"],
                                 "clearance_min_margin_m": min(clear) if clear else None,
                                 "dynamic": {q: v["max"] - v["cap"] for q, v in peaks.items()}},
        "residual_vs_buffered": {"separation_min_minus_buffer": None if sep is None
                                 else sep - settings["buffer_separation_m"],
                                 "clearance_min_margin_minus_buffer_m": None if not clear
                                 else min(clear) - settings["buffer_geometry_m"],
                                 "dynamic": {q: v["max"] - v["buffered_cap"] for q, v in peaks.items()}},
        "dynamic_peaks": peaks, "endpoint_max_error": endp,
        "physical_failures": phys.get("failures"), "nvar": d.get("nvar"),
        "prepare_s": d.get("prepare_s"), "solve_s": d.get("solve_s"), "wall_s": d.get("wall_s"),
        "symmetry_break": d.get("symmetry_break"), "conditioning": d.get("conditioning"),
        "peak_rss_bytes": _peak_rss(), "witness": d.get("witness"),
    }


def _base_settings(jerk_plan, lam_j, mu):
    from ..motion.optimize import EPS as _E
    return {"jerk_plan_m_s3": float(jerk_plan), "knot_s": 1.0, "weight_smooth": float(lam_j),
            "weight_separation": mu, "weight_geometry": mu, "weight_speed": mu, "weight_normal": mu,
            "weight_tangential": mu, "weight_jerk": mu, "maxiter": 500, "maxls": 20, "maxcor": 10,
            "maxfun": 1 + 500 * 20, "ftol": _E, "gtol": math.sqrt(_E),
            "buffer_separation_m": 3.25, "buffer_geometry_m": 1.0, "buffer_dynamic_factor": 0.95}


def calibrate_optimizer(*, tracking_config=None, out_dir, k_max=None, log=print):
    """λ_j = 所有非恒定夹具 × h∈{1,.5} 的 E/Q 中位数；其余六项共同 μ=2^k，k 从 0 递增，选第一个令全部
    "应成功"夹具在两种 h 下都通过独立硬检查且 L-BFGS-B 正常收敛的 k。每个候选 × 夹具 × h 只求解一次。
    同一 k 下一旦某个应成功夹具失败，该 k 已不合格，其余夹具记为"未运行（同 k 已失败）"（不影响选择）。"""
    from ..config import load_config
    from ..motion.optimize import physical_limits, prepare_problem, solve_joint
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=False)
    cfg = load_config("joint_opt")
    jerk_plan = cfg.values["jerk_plan_m_s3"]
    probe = _base_settings(jerk_plan, 0.0, 1.0)
    lim = physical_limits(probe)
    fixtures = calibration_fixtures(lim["d_lane"])
    t0 = time.perf_counter()
    # ---- λ_j
    lam_rows = []
    for name, build, _, constant in fixtures:
        for h in (1.0, 0.5):
            prep = prepare_problem(build(), probe, knot_s=h)
            _, _, F = prep.value_grad(prep.x_ls, terms=True)
            S2 = sum(float(np.sum(m.w_e * (m.S_e[:, 0] ** 2 + m.S_e[:, 1] ** 2))) for m in prep.members)
            noise = EPS * S2 / prep.L0 ** 2 / prep.sumT
            E, Q = F["ref"], F["smooth"]
            valid = (not constant) and E > noise and Q > 0.0
            lam_rows.append({"fixture": name, "knot_s": h, "E": E, "Q": Q, "rounding_bound_E": noise,
                             "constant": constant, "valid": bool(valid), "ratio": E / Q if Q > 0 else None})
            log(f"λ_j 测量 {name} h={h}: E={E:.3e} Q={Q:.3e} 噪声界={noise:.3e} 有效={valid}")
    ratios = [r["ratio"] for r in lam_rows if r["valid"]]
    lam_j = float(np.median(ratios)) if ratios else None
    result = {"lambda_rows": lam_rows, "lambda_j": lam_j, "candidates": [], "selected": None,
              "limits": lim, "jerk_plan_m_s3": jerk_plan, "joint_opt_sha256_at_start": cfg.sha256}
    if lam_j is None:
        result["status"] = "λ_j 无有效格点：优化设置未确定"
        _dump(out / "numerics.json", result)
        return result
    # ---- μ = 2^k
    kmax = k_max if k_max is not None else int(round(-math.log2(EPS)))
    for k in range(kmax + 1):
        mu = float(2.0 ** k)
        st = _base_settings(jerk_plan, lam_j, mu)
        rows, qualified, failed_at = [], True, None
        for name, build, should, _ in fixtures:
            for h in (1.0, 0.5):
                if failed_at is not None:
                    rows.append({"fixture": name, "knot_s": h, "should_succeed": should,
                                 "not_run": "同 k 已有应成功夹具失败（" + failed_at + "）"})
                    continue
                sol = solve_joint(build(), st, knot_s=h)
                s = _summarize_solution(sol, lim, st)
                s.update({"fixture": name, "knot_s": h, "should_succeed": should})
                rows.append(s)
                log(f"k={k} mu={mu:g} {name} h={h}: ok={sol.ok} {sol.reason} nit={s['nit']} "
                    f"{s['message']} solve={(s['solve_s'] or 0):.2f}s")
                if should and not sol.ok:
                    qualified = False
                    failed_at = f"{name} h={h}"
        result["candidates"].append({"k": k, "mu": mu, "qualified": qualified, "rows": rows})
        _dump(out / "numerics.json", result)
        if qualified:
            result["selected"] = {"k": k, "mu": mu, "lambda_j": lam_j, "settings": st}
            break
    result["status"] = "selected" if result["selected"] else "优化设置未确定"
    result["wall_s"] = time.perf_counter() - t0
    _dump(out / "numerics.json", result)
    return result


def _dump(path, obj):
    from ..runner.monitoring import jsonable
    Path(path).write_bytes(json.dumps(jsonable(obj), ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")
                           + b"\n")


def diagnose_all_fixtures(k_values, lam_j, *, out_dir, log=print):
    """补充诊断（不参与选择、不写配置）：在给定的若干 k 上把全部夹具 × h 都跑一次（不因前面失败而跳过），
    让审查方看到圆障碍与大编组夹具在同一组候选权重下的收敛与残差。"""
    from ..config import load_config
    from ..motion.optimize import physical_limits, solve_joint
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=False)
    jerk_plan = load_config("joint_opt").values["jerk_plan_m_s3"]
    lim = physical_limits(_base_settings(jerk_plan, lam_j, 1.0))
    fixtures = calibration_fixtures(lim["d_lane"])
    res = {"purpose": "补充诊断：不参与 μ 选择", "lambda_j": lam_j, "candidates": []}
    for k in k_values:
        st = _base_settings(jerk_plan, lam_j, float(2.0 ** k))
        rows = []
        for name, build, should, _ in fixtures:
            for h in (1.0, 0.5):
                sol = solve_joint(build(), st, knot_s=h)
                s = _summarize_solution(sol, lim, st)
                s.update({"fixture": name, "knot_s": h, "should_succeed": should})
                rows.append(s)
                log(f"[诊断] k={k} {name} h={h}: ok={sol.ok} {sol.reason} nit={s['nit']} {s['message']} "
                    f"solve={(s['solve_s'] or 0):.1f}s")
        res["candidates"].append({"k": k, "mu": float(2.0 ** k), "rows": rows})
        _dump(out / "diagnostic.json", res)
    return res
