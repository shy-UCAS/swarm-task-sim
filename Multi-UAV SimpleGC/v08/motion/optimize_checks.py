"""优化结果的硬检查（V8-13 指令 3.6，附录第 4 节简化）：一律从最终样条系数重算，不读求解器的"满足"结论。

- 动力学：每个节点区间 p 为三次多项式，v 二次、a 一次、j 常量。|v|²、(v·a)²/|v|²、cross(v,a)²/|v|² 的极值
  取区间端点与导数分子多项式的根（所有根的实部落在区间内都作候选：多取候选点只会多算真实函数值，不会高估
  极大值，也不会因近重根带小虚部而漏峰值）；v=0 处按单侧极限 a_t=|a|、a_n=0。比较直接用 float64 与原上限，
  不加容差（附录 4.1、4.3）。
- 几何：在绝对 0.1 s 时刻点（含移动端点）形成折线，用冻结 polyline_clearance 求每条弦的精确余量，再减弦高上界
  a_max·Δt²/8（a_max 为该弦所在时间区间内样条加速度范数的上界）；≥ 0 即满足原余量（附录 4.2）。
- 间距：成员两两在共同可见的整数微秒 10 Hz 帧上算距离，最小值 ≥ 原阈值。

本模块导入时只依赖 NumPy/SciPy 与纯 NumPy 的 scene.exact，不加载 shapely、不读场景。
"""
import math

import numpy as np
from numpy.polynomial import Polynomial

US = 1_000_000


# ---------------------------------------------------------------- 分段多项式

def interval_polys(knots, controls, lo, hi):
    """返回 [(a, b, x(τ), y(τ))]：节点区间与 [lo,hi] 的交集 [a,b]，多项式变量 τ = t − 区间左节点。
    knots 为局部秒（以 release 为原点），controls 为 (n,2) 实际米值。"""
    from scipy.interpolate import PPoly
    knots = np.asarray(knots, float)
    c = np.asarray(controls, float)
    px = PPoly.from_spline((knots, c[:, 0], 3))
    py = PPoly.from_spline((knots, c[:, 1], 3))
    out = []
    for k in range(len(px.x) - 1):
        a, b = float(px.x[k]), float(px.x[k + 1])
        A, B = max(a, lo), min(b, hi)
        if B <= A:
            continue
        x = Polynomial(px.c[:, k][::-1])
        y = Polynomial(py.c[:, k][::-1])
        out.append((A, B, a, x, y))
    return out


def _cands(polys, lo, hi):
    cands = [lo, hi]
    for poly in polys:
        if poly.degree() < 1 or not np.any(poly.coef):
            continue
        for r in poly.roots():
            rr = float(np.real(r))
            if lo < rr < hi:
                cands.append(rr)
    return cands


def _eval_dyn(x, y, tau):
    vx, vy = x.deriv()(tau), y.deriv()(tau)
    ax, ay = x.deriv(2)(tau), y.deriv(2)(tau)
    speed = math.hypot(vx, vy)
    if speed > 0.0:
        at = (vx * ax + vy * ay) / speed
        an = abs(vx * ay - vy * ax) / speed
    else:
        at = math.hypot(ax, ay)
        an = 0.0
    return speed, at, an


def dynamic_extrema_loop(knots, controls, lo, hi):
    """[lo,hi]（局部秒）上 |v|、|a_t|、a_n、|j| 的连续时间峰值及其时刻。"""
    worst = {"speed": (0.0, lo), "tangential": (0.0, lo), "normal": (0.0, lo), "jerk": (0.0, lo),
             "accel": (0.0, lo)}
    for A, B, a0, x, y in interval_polys(knots, controls, lo, hi):
        tlo, thi = A - a0, B - a0
        vx, vy, ax, ay = x.deriv(), y.deriv(), x.deriv(2), y.deriv(2)
        s2 = vx * vx + vy * vy
        dot, cross = vx * ax + vy * ay, vx * ay - vy * ax
        polys = [s2.deriv(), (dot * dot).deriv() * s2 - (dot * dot) * s2.deriv(),
                 (cross * cross).deriv() * s2 - (cross * cross) * s2.deriv(), s2]
        jerk = math.hypot(float(x.deriv(3)(0.0)), float(y.deriv(3)(0.0)))
        if jerk > worst["jerk"][0]:
            worst["jerk"] = (jerk, A)
        for tau in (tlo, thi):
            acc = math.hypot(ax(tau), ay(tau))
            if acc > worst["accel"][0]:
                worst["accel"] = (acc, tau + a0)
        for tau in _cands(polys, tlo, thi):
            sp, at, an = _eval_dyn(x, y, tau)
            for name, val in (("speed", sp), ("tangential", abs(at)), ("normal", an)):
                if val > worst[name][0]:
                    worst[name] = (val, tau + a0)
    return {k: {"value": float(v), "t_local_s": float(t)} for k, (v, t) in worst.items()}


# ---- 向量化版本（与 dynamic_extrema_loop 同一数学：端点 + 导数分子多项式全部根的实部作候选）

def _pmul(a, b):
    """逐行多项式乘法，系数升幂 (N, da+1) × (N, db+1)。"""
    out = np.zeros((a.shape[0], a.shape[1] + b.shape[1] - 1))
    for i in range(a.shape[1]):
        out[:, i:i + b.shape[1]] += a[:, i:i + 1] * b
    return out


def _pder(a):
    if a.shape[1] <= 1:
        return np.zeros((a.shape[0], 1))
    return a[:, 1:] * np.arange(1, a.shape[1])[None, :]


def _psub(a, b):
    n = max(a.shape[1], b.shape[1])
    out = np.zeros((a.shape[0], n))
    out[:, :a.shape[1]] += a
    out[:, :b.shape[1]] -= b
    return out


def _batched_roots(c):
    """逐行求升幂多项式全部根的实部；返回 (N, d) 数组，无根处为 nan。有效次数逐行确定（相对 ε 截去首项）。"""
    N, n = c.shape
    d = n - 1
    out = np.full((N, max(d, 1)), np.nan)
    if d < 1:
        return out
    scale = np.max(np.abs(c), axis=1)
    eps = float(np.finfo(float).eps)
    eff = np.zeros(N, dtype=np.int64)
    for k in range(d, 0, -1):
        mask = (eff == 0) & (np.abs(c[:, k]) > eps * scale)
        eff[mask] = k
    for k in range(1, d + 1):
        rows = np.flatnonzero(eff == k)
        if not len(rows):
            continue
        cc = c[rows, :k + 1] / c[rows, k:k + 1]
        comp = np.zeros((len(rows), k, k))
        if k > 1:
            comp[:, 1:, :-1] = np.eye(k - 1)[None]
        comp[:, :, -1] = -cc[:, :k]
        ev = np.linalg.eigvals(comp)
        out[rows, :k] = np.real(ev)
    return out


def _coeffs(knots, controls):
    from scipy.interpolate import PPoly
    knots = np.asarray(knots, float)
    c = np.asarray(controls, float)
    px = PPoly.from_spline((knots, c[:, 0], 3))
    py = PPoly.from_spline((knots, c[:, 1], 3))
    return px.x, px.c[::-1].T, py.c[::-1].T          # 升幂 (nint, 4)


def dynamic_extrema(knots, controls, lo, hi):
    """[lo,hi]（局部秒）上 |v|、|a_t|、a_n、|j|、|a| 的连续时间峰值及其时刻（向量化）。"""
    xs, X, Y = _coeffs(knots, controls)
    a0, a1 = xs[:-1], xs[1:]
    A, B = np.maximum(a0, lo), np.minimum(a1, hi)
    keep = B > A
    a0, A, B, X, Y = a0[keep], A[keep], B[keep], X[keep], Y[keep]
    tlo, thi = A - a0, B - a0
    worst = {k: (0.0, float(lo)) for k in ("speed", "tangential", "normal", "jerk", "accel")}
    if not len(a0):
        return {k: {"value": v, "t_local_s": t} for k, (v, t) in worst.items()}
    vx, vy = _pder(X), _pder(Y)
    ax, ay = _pder(vx), _pder(vy)
    jx, jy = 6.0 * X[:, 3], 6.0 * Y[:, 3]
    jn = np.hypot(jx, jy)
    k = int(np.argmax(jn))
    worst["jerk"] = (float(jn[k]), float(A[k]))
    s2 = _psub(_pmul(vx, vx), -_pmul(vy, vy))
    dot = _psub(_pmul(vx, ax), -_pmul(vy, ay))
    cross = _psub(_pmul(vx, ay), _pmul(vy, ax))
    s2d = _pder(s2)
    polys = [s2d, _psub(_pmul(_pder(_pmul(dot, dot)), s2), _pmul(_pmul(dot, dot), s2d)),
             _psub(_pmul(_pder(_pmul(cross, cross)), s2), _pmul(_pmul(cross, cross), s2d)), s2]
    cand = [tlo[:, None], thi[:, None]]
    for poly in polys:
        r = _batched_roots(poly)
        r = np.where((r > tlo[:, None]) & (r < thi[:, None]), r, np.nan)
        cand.append(r)
    T = np.concatenate(cand, axis=1)
    rows = np.broadcast_to(np.arange(len(a0))[:, None], T.shape)
    ok = ~np.isnan(T)
    t = T[ok]
    i = rows[ok]

    def ev(c, tt, ii):
        out = np.zeros_like(tt)
        for p in range(c.shape[1] - 1, -1, -1):
            out = out * tt + c[ii, p]
        return out
    Vx, Vy, Ax, Ay = ev(vx, t, i), ev(vy, t, i), ev(ax, t, i), ev(ay, t, i)
    sp = np.hypot(Vx, Vy)
    pos = sp > 0
    ssafe = np.where(pos, sp, 1.0)
    at = np.where(pos, np.abs(Vx * Ax + Vy * Ay) / ssafe, np.hypot(Ax, Ay))
    an = np.where(pos, np.abs(Vx * Ay - Vy * Ax) / ssafe, 0.0)
    acc = np.hypot(Ax, Ay)
    for name, val in (("speed", sp), ("tangential", at), ("normal", an), ("accel", acc)):
        k = int(np.argmax(val))
        if val[k] > worst[name][0]:
            worst[name] = (float(val[k]), float(t[k] + a0[i[k]]))
    return {k: {"value": float(v), "t_local_s": float(tt)} for k, (v, tt) in worst.items()}


def curvature_radius_min(knots, controls, lo, hi):
    """连续时间最小曲率半径 ρ = |v|³/|cross(v,a)|（取 κ² = cross²/|v|⁶ 的极大）。v=0 处跳过。"""
    best = 0.0
    where = lo
    for A, B, a0, x, y in interval_polys(knots, controls, lo, hi):
        tlo, thi = A - a0, B - a0
        vx, vy, ax, ay = x.deriv(), y.deriv(), x.deriv(2), y.deriv(2)
        s2 = vx * vx + vy * vy
        cr = vx * ay - vy * ax
        poly = 2 * cr * cr.deriv() * s2 - 3 * cr * cr * s2.deriv()
        for tau in _cands([poly], tlo, thi):
            s = float(s2(tau))
            if s <= 0.0:
                continue
            k2 = float(cr(tau)) ** 2 / s ** 3
            if k2 > best:
                best, where = k2, tau + a0
    return (math.inf if best == 0.0 else 1.0 / math.sqrt(best)), float(where)


# ---------------------------------------------------------------- 物理硬检查（solve_joint 负责）

def _grid_times(tr):
    """绝对 0.1 s 网格 ∪ 移动端点（局部秒）。"""
    r, e = float(tr.release_s), float(tr.end_s)
    g0, g1 = math.ceil(r * 10 - 1e-9), math.floor(e * 10 + 1e-9)
    grid = np.arange(g0, g1 + 1, dtype=np.int64) / 10.0 - r
    T = e - r
    return np.unique(np.concatenate([grid[(grid >= 0.0) & (grid <= T)], [0.0, T]]))


def _frames(tr, hold_s):
    """成员可见的整数 10 Hz 帧号（释放起，至移动结束 + 末端保持）。"""
    f0 = math.ceil(float(tr.release_s) * 10 - 1e-9)
    f1 = math.floor((float(tr.end_s) + hold_s) * 10 + 1e-9)
    return f0, f1


def equality_bound(tr):
    """等式残差的数值比较界（与预置测试同口径）：√ε·max(1, max|控制点|)。只用于等式，不放宽任何不等式阈值。"""
    return math.sqrt(float(np.finfo(float).eps)) * max(1.0, float(np.max(np.abs(tr.controls))))


def check_physical(problem, trajectories, settings):
    """dict: passed, failures, separation, clearances, dynamic_extrema, endpoints。从最终系数重算。"""
    from ..scene.exact import polyline_clearance
    from .optimize import physical_limits
    lim = physical_limits(settings)
    failures = []
    refs = {r.member_id: r for r in problem.references}
    order = sorted(refs)
    # 端点与语义直线等式
    endpoints = {}
    for m in order:
        ref, tr = refs[m], trajectories[m]
        bound = equality_bound(tr)
        p0 = np.asarray(ref.pva(ref.release_s)[0], float).reshape(2)
        p1 = np.asarray(ref.pva(ref.end_s)[0], float).reshape(2)
        errs = {}
        for name, t, want in (("start", tr.release_s, p0), ("end", tr.end_s, p1)):
            # 端点导数取域内单侧值：在域内点 t（=端点本身）上求多项式，不用域外零值
            errs[name + "_p"] = float(np.max(np.abs(tr.evaluate(t, 0) - want)))
            errs[name + "_v"] = float(np.max(np.abs(tr.evaluate(t, 1))))
            errs[name + "_a"] = float(np.max(np.abs(tr.evaluate(t, 2))))
        same_time = (float(tr.release_s) == float(ref.release_s)) and (float(tr.end_s) == float(ref.end_s))
        endpoints[m] = {"errors": errs, "bound": bound, "fixed_time": same_time}
        if not same_time or any(v > bound for v in errs.values()):
            failures.append({"kind": "endpoint", "member": m, "errors": errs, "bound": bound})
    line_res = []
    for (mid, t0, t1, q, tg) in problem.lines:
        tr = trajectories[mid]
        tg = np.asarray(tg, float) / math.hypot(*tg)
        nrm = np.array([-tg[1], tg[0]])
        h = tr.h
        a, b = float(t0) - tr.release_s, float(t1) - tr.release_s
        worst = 0.0
        for j in range(len(tr.controls)):
            if (j - 3) * h < b and (j + 1) * h > a:
                worst = max(worst, abs(float(nrm @ (np.asarray(tr.controls[j]) - np.asarray(q, float)))))
        bound = equality_bound(tr)
        line_res.append({"member": mid, "max_normal_residual_m": worst, "bound": bound})
        if worst > bound:
            failures.append({"kind": "line_equality", "member": mid, "residual": worst, "bound": bound})
    # 动力学连续极值（原上限，不加容差）
    dyn = {}
    for m in order:
        tr = trajectories[m]
        d = dynamic_extrema(tr.knots, tr.controls, 0.0, tr.duration)
        dyn[m] = d
        for key, cap in (("speed", lim["v_max"]), ("tangential", lim["a_t"]), ("normal", lim["a_n"]),
                         ("jerk", lim["jerk"])):
            if not d[key]["value"] <= cap:
                failures.append({"kind": "dynamic", "member": m, "quantity": key, "value": d[key]["value"],
                                 "cap": cap, "t_abs_s": d[key]["t_local_s"] + tr.release_s})
    # 几何：弦精确余量 − 弦高上界 a_max·Δt²/8 ≥ 0（polyline_clearance 已减 minimum_m）
    clear = {}
    for m in order:
        tr = trajectories[m]
        ts = _grid_times(tr)
        xy = tr.evaluate(ts + tr.release_s, 0)
        acc = tr.evaluate(ts + tr.release_s, 2)
        an = np.hypot(acc[:, 0], acc[:, 1])
        dt = np.diff(ts)
        sag = np.maximum(an[:-1], an[1:]) * dt ** 2 / 8.0
        per = {}
        for c in problem.clearances:
            if len(xy) < 2:
                vals = np.array([])
            else:
                vals = polyline_clearance(c.geometry, xy, sense=c.sense, minimum_m=c.minimum_m, fast_far_m=1.0)
            margin = vals - sag
            k = int(np.argmin(margin)) if len(margin) else None
            per[c.name] = {"min_margin_m": float(margin[k]) if k is not None else None,
                           "t_abs_s": float(ts[k] + tr.release_s) if k is not None else None,
                           "max_sag_m": float(sag.max()) if len(sag) else 0.0}
            if k is not None and not margin[k] >= 0.0:
                failures.append({"kind": "clearance", "member": m, "constraint": c.name,
                                 "margin_m": float(margin[k]), "t_abs_s": float(ts[k] + tr.release_s)})
        clear[m] = per
    # 掉头曲率（V8-13c 裁定 1；硬检查用原下界 15/8/25 m，连续区间极值）
    turns = []
    for (mid, t0, t1, rmin) in getattr(problem, "turns", ()):
        tr = trajectories[mid]
        lo, hi = max(float(t0) - tr.release_s, 0.0), min(float(t1) - tr.release_s, tr.duration)
        if hi <= lo:
            continue
        rho, where = curvature_radius_min(tr.knots, tr.controls, lo, hi)
        turns.append({"member": mid, "t_abs": (float(t0), float(t1)), "min_radius_m": rho, "required_m": float(rmin),
                      "at_abs_s": where + tr.release_s})
        if not rho >= float(rmin):
            failures.append({"kind": "turn_radius", "member": mid, "min_radius_m": rho, "required_m": float(rmin),
                             "t_abs_s": where + tr.release_s})
    # 间距：共同可见整数 10 Hz 帧
    sep = {"min_m": None, "pair": None, "t_s": None, "pairs_without_common_frames": []}
    frames = {m: _frames(trajectories[m], lim["hold_s"]) for m in order}
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            a, b = order[i], order[j]
            lo, hi = max(frames[a][0], frames[b][0]), min(frames[a][1], frames[b][1])
            if hi < lo:
                sep["pairs_without_common_frames"].append((a, b))
                continue
            t = np.arange(lo, hi + 1, dtype=np.int64) / 10.0
            d = np.hypot(*(trajectories[a].evaluate(t) - trajectories[b].evaluate(t)).T)
            k = int(np.argmin(d))
            if sep["min_m"] is None or d[k] < sep["min_m"]:
                sep.update(min_m=float(d[k]), pair=(a, b), t_s=float(t[k]))
    sep["required_m"] = lim["d_lane"]
    if sep["min_m"] is not None and not sep["min_m"] >= lim["d_lane"]:
        failures.append({"kind": "separation", "pair": sep["pair"], "min_m": sep["min_m"], "t_s": sep["t_s"]})
    return {"passed": not failures, "failures": failures, "separation": sep, "clearances": clear,
            "dynamic_extrema": dyn, "endpoints": endpoints, "lines": line_res, "limits": lim, "turns": turns}


# ---------------------------------------------------------------- 监视语义硬检查（生产 optimize_segment 负责）

def check_monitoring(ctx, skeleton, trajectories, settings):
    """dict: passed, failures, boundaries, turns, nominal_members。均在优化后的曲线上重算：
    1) 冻结 crossing_analysis 重查单次直线穿越、两侧 10 m、目标入圈前 100 m、未穿越部分离边界 10 m（不传 skip_ranges）；
       折线取绝对 0.1 s 时刻点 ∪ 端点（带内由法向等式保证真共线）；
    2) 掉头区间（骨架折返掉头的圆弧图元，按骨架名义时间映射到优化曲线）的连续最小曲率半径 ≥ 15/8/25 m；
       优化样条 C²，速度非零处曲率连续，没有"不连续异号曲率接点"，C12 连续曲率变号豁免适用；
    3) 终点离所有 warning ≥ retreat_clearance_m；
    4) 名义判据：释放起至移动结束 + 末端保持的 10 Hz p/v 调 screen_member：patrol_revisit、无驻留、圈层 ≤ 1。"""
    from ..config import load_config
    from ..scene.exact import signed_distance
    from .connect import crossing_analysis
    from .intents.monitoring import monitoring_constraints
    from .nominal import member_nominal
    from .nominal_checks import screen_member
    from .optimize import physical_limits
    lim = physical_limits(settings)
    M = load_config("monitoring").values
    target = skeleton.witnesses["target_id"]
    cons = monitoring_constraints(ctx, target)
    failures = []
    boundaries, turns, nominal_members = {}, {}, {}
    turn_ranges = skeleton.witnesses.get("turn_ranges") or {}
    from .skeleton import reference_guidance
    G_ref = reference_guidance()
    for m in sorted(trajectories):
        tr = trajectories[m]
        ts = _grid_times(tr)
        xy = tr.evaluate(ts + tr.release_s, 0)
        viol, cross = crossing_analysis(xy, cons["warnings"], target, band_m=ctx.params["pre_entry_warning_clearance_m"],
                                        align_m=ctx.params["alignment_length_m"])
        boundaries[m] = {"violations": viol, "crossings": [(c.facility_id, c.direction, float(c.s_m)) for c in cross]}
        if viol:
            failures.append({"kind": "boundary_crossing", "member": m, "first": viol[0], "count": len(viol)})
        # 掉头曲率
        nom = member_nominal(skeleton.members[m], guidance=G_ref)
        rows = []
        for kind, s_a, s_b, key in turn_ranges.get(m, []):
            ta = float(np.interp(s_a, nom.curve.s, nom.t_nodes))
            tb = float(np.interp(s_b, nom.curve.s, nom.t_nodes))
            need = float(M[key]) if key else None
            rho, where = curvature_radius_min(tr.knots, tr.controls, max(ta, 0.0), min(tb, tr.duration))
            rows.append({"kind": kind, "t_local_s": (ta, tb), "min_radius_m": rho, "required_m": need,
                         "at_local_s": where})
            if need is not None and not rho >= need:
                failures.append({"kind": "turn_radius", "member": m, "turn": kind, "min_radius_m": rho,
                                 "required_m": need})
        turns[m] = rows
        # 终点撤离
        end = tr.evaluate(tr.end_s, 0)
        for fid, geom in cons["warnings"].items():
            sd = float(signed_distance(geom, end))
            if not sd >= M["retreat_clearance_m"]:
                failures.append({"kind": "terminal_clearance", "member": m, "facility": fid, "signed_m": sd})
        # 名义判据
        r_us = int(round(tr.release_s * 10)) * 100_000
        e_us = int(math.floor((tr.end_s + lim["hold_s"]) * 10 + 1e-9)) * 100_000
        t_us = np.arange(r_us, e_us + 1, 100_000, dtype=np.int64)
        tt = t_us / US
        p = np.zeros((len(tt), 3))
        v = np.zeros((len(tt), 3))
        p[:, :2] = tr.evaluate(tt, 0)
        v[:, :2] = tr.evaluate(tt, 1)
        p[:, 2] = tr.altitude_m
        scr = screen_member(ctx.facilities, target, t_us, p, v)
        nominal_members[m] = {"patrol_revisit": scr["patrol_revisit"],
                              "dwell_anywhere": bool(scr["dwell_anywhere"]["detected"]),
                              "max_target_layer": scr["max_target_layer"], "max_other_layer": scr["max_other_layer"]}
        if not scr["patrol_revisit"]:
            failures.append({"kind": "nominal_revisit", "member": m})
        if scr["dwell_anywhere"]["detected"]:
            failures.append({"kind": "nominal_dwell", "member": m})
        if scr["max_target_layer"] > 1 or scr["max_other_layer"] > 1:
            failures.append({"kind": "nominal_layers", "member": m, **{k: nominal_members[m][k]
                                                                       for k in ("max_target_layer", "max_other_layer")}})
    return {"passed": not failures, "failures": failures, "boundaries": boundaries, "turns": turns,
            "nominal_members": nominal_members}


# ---------------------------------------------------------------- 过境语义硬检查（V8-16 指令 4.1；本项新增）

TRANSIT_FAILURE_KIND = {"started_outside_target_warning": "nominal_start_inside",
                        "entered_warning": "nominal_not_entered",
                        "single_warning_visit": "nominal_multiple_visits",
                        "max_target_layer_one": "nominal_layers", "other_layers_within_limit": "nominal_layers",
                        "no_dwell_window": "nominal_dwell", "no_revisit_window": "nominal_revisit",
                        "ended_outside_all_warning": "nominal_end_inside"}


def check_transit(ctx, skeleton, trajectories, settings):
    """dict: passed, failures, boundaries, nominal_members。均在优化后的曲线上重算（时间网格照录 check_monitoring）：
    1) 冻结 crossing_analysis 查全部 warning（完整曲线、不传 skip_ranges）：单次直线穿越、两侧 10 m、目标入圈前 100 m、
       未穿越部分离边界 10 m；目标恰一入一出；
    2) 终点离所有 warning ≥ retreat_clearance_m；
    3) 名义判据：释放起至移动结束 + 末端保持的 10 Hz p/v 调 screen_transit_member，全部条件成立。
    过境没有掉头区间，不调用监视"必须重访"。成功由这些检查与 solve_joint 原阈值物理检查共同决定。"""
    from ..config import load_config
    from ..scene.exact import signed_distance
    from .connect import crossing_analysis
    from .nominal_checks import screen_transit_member
    from .optimize import physical_limits
    from .transit_chords import transit_base
    lim = physical_limits(settings)
    M = load_config("monitoring").values
    target = skeleton.witnesses["target_id"]
    cons = transit_base(ctx, target)
    failures = []
    boundaries, nominal_members = {}, {}
    for m in sorted(trajectories):
        tr = trajectories[m]
        ts = _grid_times(tr)
        xy = tr.evaluate(ts + tr.release_s, 0)
        viol, cross = crossing_analysis(xy, cons["warnings"], target, band_m=ctx.params["pre_entry_warning_clearance_m"],
                                        align_m=ctx.params["alignment_length_m"])
        boundaries[m] = {"violations": viol, "crossings": [(c.facility_id, c.direction, float(c.s_m)) for c in cross]}
        if viol:
            failures.append({"kind": "boundary_crossing", "member": m, "first": viol[0], "count": len(viol)})
        dirs = [c.direction for c in cross if c.facility_id == target]
        if dirs != ["in", "out"]:
            failures.append({"kind": "target_single_crossing", "member": m, "directions": dirs})
        end = tr.evaluate(tr.end_s, 0)
        for fid, geom in cons["warnings"].items():
            sd = float(signed_distance(geom, end))
            if not sd >= M["retreat_clearance_m"]:
                failures.append({"kind": "terminal_clearance", "member": m, "facility": fid, "signed_m": sd})
        r_us = int(round(tr.release_s * 10)) * 100_000
        e_us = int(math.floor((tr.end_s + lim["hold_s"]) * 10 + 1e-9)) * 100_000
        t_us = np.arange(r_us, e_us + 1, 100_000, dtype=np.int64)
        tt = t_us / US
        p = np.zeros((len(tt), 3))
        v = np.zeros((len(tt), 3))
        p[:, :2] = tr.evaluate(tt, 0)
        v[:, :2] = tr.evaluate(tt, 1)
        p[:, 2] = tr.altitude_m
        scr = screen_transit_member(ctx.facilities, target, t_us, p, v)
        nominal_members[m] = {"conditions": scr["conditions"], "counts": scr["counts"],
                              "revisit_work_detected": bool(scr["revisit_work"]["detected"])}
        kinds = []
        for k, ok in scr["conditions"].items():
            if not ok and TRANSIT_FAILURE_KIND[k] not in kinds:
                kinds.append(TRANSIT_FAILURE_KIND[k])
        for kind in kinds:
            failures.append({"kind": kind, "member": m,
                             "conditions": [k for k, ok in scr["conditions"].items() if not ok]})
    return {"passed": not failures, "failures": failures, "boundaries": boundaries, "nominal_members": nominal_members}


INTRUSION_FAILURE_KIND = {"started_outside_target_warning": "nominal_start_inside",
                          "target_layers_monotone": "nominal_layer_regression",
                          "entered_protected": "nominal_not_entered",
                          "near_facility_contour": "nominal_layers", "other_layers_within_limit": "nominal_layers",
                          "no_dwell_window": "nominal_dwell"}
INTRUSION_ENTRY_CONDITIONS = {"single_warning_entry": "warning", "single_alert_entry": "alert",
                              "single_protected_entry": "protected"}


def check_intrusion(ctx, skeleton, trajectories, settings):
    """dict: passed, failures, boundaries, nominal_members, terminal（结构照 check_transit；V8-17 指令 4.1）。
    均在优化后的实际样条上重算（时间网格复用 _grid_times）：
    1) intrusion 约束的 crossing_boundaries 对每成员完整轨迹调用冻结 crossing_analysis（不传 skip_ranges），
       目标 warning/alert/protected 每层方向必须恰为 ["in"]；边界检查本身的擦边、带内终点、共线与对齐失败照报；
    2) tr.evaluate(tr.end_s, 0)：contour SDF ≤ 冻结 roles.intrusion.max_contour_distance_m（50，不是骨架 45；
       负距离合法）、protected SDF ≤ −10；
    3) 名义判据：释放起至移动结束 + 末端保持的 10 Hz p/v 调 screen_intrusion_member，全部条件成立。
    不检查所有 warning 外 50 m、不要求出圈、不调用重访检测。物理硬检查仍由 solve_joint 负责，本函数不重新求解。"""
    from task_v07.criteria import load_criteria
    from ..scene.exact import signed_distance
    from .connect import crossing_analysis
    from .layer_limits import crossing_layer_keys
    from .nominal_checks import screen_intrusion_member
    from .optimize import physical_limits
    from .transit_chords import transit_base
    lim = physical_limits(settings)
    cfg = load_criteria()
    contour_max = float(cfg["roles"]["intrusion"]["max_contour_distance_m"])
    target = skeleton.witnesses["target_id"]
    tgt = ctx.facility_by_id[target]
    cons = transit_base(ctx, target, intent="intrusion")
    layer_key = {"warning": target, **{layer: k for k, layer in crossing_layer_keys(cons).items()}}
    failures = []
    boundaries, nominal_members, terminal = {}, {}, {}
    for m in sorted(trajectories):
        tr = trajectories[m]
        ts = _grid_times(tr)
        xy = tr.evaluate(ts + tr.release_s, 0)
        viol, cross = crossing_analysis(xy, cons["crossing_boundaries"], target,
                                        band_m=ctx.params["pre_entry_warning_clearance_m"],
                                        align_m=ctx.params["alignment_length_m"])
        boundaries[m] = {"violations": viol, "crossings": [(c.facility_id, c.direction, float(c.s_m)) for c in cross]}
        if viol:
            failures.append({"kind": "boundary_crossing", "member": m, "first": viol[0], "count": len(viol)})
        for layer, k in layer_key.items():
            dirs = [c.direction for c in cross if c.facility_id == k]
            if dirs != ["in"]:
                failures.append({"kind": "target_layer_crossing", "member": m, "layer": layer, "boundary_key": k,
                                 "directions": dirs})
        end = tr.evaluate(tr.end_s, 0)
        sd_c = float(signed_distance(tgt.geometry, end))
        sd_p = float(signed_distance(tgt.layers["protected"], end))
        terminal[m] = {"contour_sdf_m": sd_c, "protected_sdf_m": sd_p, "contour_limit_m": contour_max}
        if not sd_c <= contour_max:
            failures.append({"kind": "terminal_contour", "member": m, "signed_m": sd_c, "limit_m": contour_max})
        if not sd_p <= -10.0:
            failures.append({"kind": "terminal_protected", "member": m, "signed_m": sd_p, "limit_m": -10.0})
        r_us = int(round(tr.release_s * 10)) * 100_000
        e_us = int(math.floor((tr.end_s + lim["hold_s"]) * 10 + 1e-9)) * 100_000
        t_us = np.arange(r_us, e_us + 1, 100_000, dtype=np.int64)
        tt = t_us / US
        p = np.zeros((len(tt), 3))
        v = np.zeros((len(tt), 3))
        p[:, :2] = tr.evaluate(tt, 0)
        v[:, :2] = tr.evaluate(tt, 1)
        p[:, 2] = tr.altitude_m
        scr = screen_intrusion_member(ctx.facilities, target, t_us, p, v, criteria=cfg)
        nominal_members[m] = {"conditions": scr["conditions"], "counts": scr["counts"],
                              "first_entry_us": scr["first_entry_us"], "end_contour_m": scr["end_contour_m"],
                              "min_contour_m": scr["min_contour_m"]}
        kinds = []
        for k, ok in scr["conditions"].items():
            if ok:
                continue
            if k in INTRUSION_ENTRY_CONDITIONS:
                cnt = scr["counts"]["entries"][INTRUSION_ENTRY_CONDITIONS[k]]
                kind = "nominal_not_entered" if cnt == 0 else "nominal_multiple_visits"
            else:
                kind = INTRUSION_FAILURE_KIND[k]
            if kind not in kinds:
                kinds.append(kind)
        for kind in kinds:
            failures.append({"kind": kind, "member": m,
                             "conditions": [k for k, ok in scr["conditions"].items() if not ok],
                             "entries": scr["counts"]["entries"]})
    return {"passed": not failures, "failures": failures, "boundaries": boundaries,
            "nominal_members": nominal_members, "terminal": terminal}


FEINT_FAILURE_KIND = {"started_outside_target_warning": "nominal_start_inside",
                      "other_layers_within_limit": "nominal_layers", "no_dwell_window": "nominal_dwell",
                      "ended_outside_all_warning": "nominal_end_inside"}


def _feint_nominal_kinds(scr):
    kinds = []
    cond = scr["conditions"]
    for k, ok in cond.items():
        if ok:
            continue
        if k in ("single_warning_entry", "single_alert_entry"):
            layer = "warning" if k == "single_warning_entry" else "alert"
            kind = "nominal_not_entered" if scr["counts"]["entries"][layer] == 0 else "nominal_multiple_visits"
        elif k == "max_target_layer_two":
            mx = scr["counts"]["max_target_layer"]
            kind = "nominal_not_entered" if (mx is None or mx < 2) else "nominal_layers"
        else:
            kind = FEINT_FAILURE_KIND[k]
        if kind not in kinds:
            kinds.append(kind)
    return kinds


def check_feint(ctx, skeleton, trajectories, settings):
    """V8-18 指令 4.1：照 check_transit 的 _grid_times、10 Hz 含末端保持采样与返回结构，在优化后的曲线上重算：
    1) 实际 feint crossing_boundaries 完整曲线上 crossing_analysis（不传 skip_ranges），目标 warning / alert 各
       ["in", "out"]，保留原违规明细；
    2) 每成员 tr.evaluate(tr.end_s, 0) 到全部 warning ≥ retreat_clearance_m（50 m）；
    3) screen_feint_member（释放起至移动结束 + 末端保持的 10 Hz p/v），任一条件失败为语义失败。
    不重新求解；掉头半径由 JointProblem.turns 进入 AL 与 check_physical，不另设更松的检查。失败子类见
    boundary_crossing / target_layer_crossing / terminal_clearance / nominal_*。"""
    from ..config import load_config
    from ..scene.exact import signed_distance
    from .connect import crossing_analysis
    from .layer_limits import crossing_layer_keys
    from .nominal_checks import screen_feint_member
    from .optimize import physical_limits
    from .transit_chords import transit_base
    lim = physical_limits(settings)
    M = load_config("monitoring").values
    target = skeleton.witnesses["target_id"]
    cons = transit_base(ctx, target, intent="feint")
    keys = [target] + [k for k, layer in crossing_layer_keys(cons).items() if layer == "alert"]
    failures = []
    boundaries, nominal_members = {}, {}
    for m in sorted(trajectories):
        tr = trajectories[m]
        ts = _grid_times(tr)
        xy = tr.evaluate(ts + tr.release_s, 0)
        viol, cross = crossing_analysis(xy, cons["crossing_boundaries"], target,
                                        band_m=ctx.params["pre_entry_warning_clearance_m"],
                                        align_m=ctx.params["alignment_length_m"])
        boundaries[m] = {"violations": viol, "crossings": [(c.facility_id, c.direction, float(c.s_m)) for c in cross]}
        if viol:
            failures.append({"kind": "boundary_crossing", "member": m, "first": viol[0], "count": len(viol)})
        for k in keys:
            dirs = [c.direction for c in cross if c.facility_id == k]
            if dirs != ["in", "out"]:
                failures.append({"kind": "target_layer_crossing", "member": m, "boundary": k, "directions": dirs})
        end = tr.evaluate(tr.end_s, 0)
        for fid, geom in cons["warnings"].items():
            sd = float(signed_distance(geom, end))
            if not sd >= M["retreat_clearance_m"]:
                failures.append({"kind": "terminal_clearance", "member": m, "facility": fid, "signed_m": sd})
        r_us = int(round(tr.release_s * 10)) * 100_000
        e_us = int(math.floor((tr.end_s + lim["hold_s"]) * 10 + 1e-9)) * 100_000
        t_us = np.arange(r_us, e_us + 1, 100_000, dtype=np.int64)
        tt = t_us / US
        p = np.zeros((len(tt), 3))
        v = np.zeros((len(tt), 3))
        p[:, :2] = tr.evaluate(tt, 0)
        v[:, :2] = tr.evaluate(tt, 1)
        p[:, 2] = tr.altitude_m
        scr = screen_feint_member(ctx.facilities, target, t_us, p, v)
        nominal_members[m] = {"conditions": scr["conditions"], "counts": scr["counts"],
                              "first_entry_us": scr["first_entry_us"], "first_exit_us": scr["first_exit_us"],
                              "min_protected_sdf_m": scr["min_protected_sdf_m"]}
        for kind in _feint_nominal_kinds(scr):
            failures.append({"kind": kind, "member": m,
                             "conditions": [k for k, ok in scr["conditions"].items() if not ok]})
    return {"passed": not failures, "failures": failures, "boundaries": boundaries, "nominal_members": nominal_members}


CLOSE_FAILURE_KIND = {"started_outside_target_warning": "nominal_start_inside", "single_warning_visit": "nominal_multiple_visits",
    "max_target_layer_one": "nominal_layers", "other_layers_within_limit": "nominal_layers",
    "observation_dwell": "nominal_observation_dwell", "no_revisit_window": "nominal_revisit",
    "ended_outside_all_warning": "nominal_end_inside"}

def check_close_observation(ctx, skeleton, trajectories, settings):
    """dict: passed, failures, boundaries, nominal_members。均在优化后的曲线上重算（时间网格照录 check_monitoring）：
    1) 冻结 crossing_analysis 查全部 warning（完整曲线、不传 skip_ranges）：单次直线穿越、两侧 10 m、目标入圈前 100 m、
       未穿越部分离边界 10 m；目标恰一入一出；
    2) 终点离所有 warning ≥ retreat_clearance_m；
    3) 名义判据：释放起至移动结束 + 末端保持的 10 Hz p/v 调 screen_close_observation_member，全部条件成立。
    过境没有掉头区间，不调用监视"必须重访"。成功由这些检查与 solve_joint 原阈值物理检查共同决定。"""
    from ..config import load_config
    from ..scene.exact import signed_distance
    from .connect import crossing_analysis
    from .nominal_checks import screen_close_observation_member
    from .optimize import physical_limits
    from .transit_chords import transit_base
    lim = physical_limits(settings)
    M = load_config("monitoring").values
    target = skeleton.witnesses["target_id"]
    cons = transit_base(ctx, target, intent="close_observation")
    failures = []
    boundaries, nominal_members = {}, {}
    for m in sorted(trajectories):
        tr = trajectories[m]
        ts = _grid_times(tr)
        xy = tr.evaluate(ts + tr.release_s, 0)
        viol, cross = crossing_analysis(xy, cons["crossing_boundaries"], target, band_m=ctx.params["pre_entry_warning_clearance_m"],
                                        align_m=ctx.params["alignment_length_m"])
        boundaries[m] = {"violations": viol, "crossings": [(c.facility_id, c.direction, float(c.s_m)) for c in cross]}
        if viol:
            failures.append({"kind": "boundary_crossing", "member": m, "first": viol[0], "count": len(viol)})
        dirs = [c.direction for c in cross if c.facility_id == target]
        if dirs != ["in", "out"]:
            failures.append({"kind": "target_single_crossing", "member": m, "directions": dirs})
        end = tr.evaluate(tr.end_s, 0)
        for fid, geom in cons["crossing_boundaries"].items():
            sd = float(signed_distance(geom, end))
            if not sd >= M["retreat_clearance_m"]:
                failures.append({"kind": "terminal_clearance", "member": m, "facility": fid, "signed_m": sd})
        r_us = int(round(tr.release_s * 10)) * 100_000
        e_us = int(math.floor((tr.end_s + lim["hold_s"]) * 10 + 1e-9)) * 100_000
        t_us = np.arange(r_us, e_us + 1, 100_000, dtype=np.int64)
        tt = t_us / US
        p = np.zeros((len(tt), 3))
        v = np.zeros((len(tt), 3))
        p[:, :2] = tr.evaluate(tt, 0)
        v[:, :2] = tr.evaluate(tt, 1)
        p[:, 2] = tr.altitude_m
        scr = screen_close_observation_member(ctx.facilities, target, t_us, p, v)
        nominal_members[m] = {k: scr[k] for k in ("passed", "conditions", "counts", "levels", "observation_dwell", "revisit", "revisit_work")}
        kinds = []
        for k, ok in scr["conditions"].items():
            if not ok:
                kind = CLOSE_FAILURE_KIND[k]
                if k == "single_warning_visit":
                    kind = "nominal_not_entered" if scr["counts"]["visits"] == 0 else "nominal_multiple_visits"
                if kind not in kinds:
                    kinds.append(kind)
        for kind in kinds:
            failures.append({"kind": kind, "member": m,
                             "conditions": [k for k, ok in scr["conditions"].items() if not ok]})
    return {"passed": not failures, "failures": failures, "boundaries": boundaries, "nominal_members": nominal_members}
