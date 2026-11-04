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


def dynamic_extrema(knots, controls, lo, hi):
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
            "dynamic_extrema": dyn, "endpoints": endpoints, "lines": line_res, "limits": lim}
