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
