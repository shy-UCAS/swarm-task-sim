"""名义运动、统一时钟采样与连续时间最小间距（V8-12 第 3 部分；r4 6.7、6.8、8.2）。

名义运动复用固定提交的 make_curve / speed_profile / nominal_time：v0 = 0、终点停止，
相邻节点按 Δt = 2Δs/(v_i+v_{i+1})、a = (v_{i+1}² − v_i²)/(2Δs) 作匀加速直线运动，
与 nominal_time 一致；不用"总长/初速"或匀速线性插值。预释放 20 s + 延迟单独表示。
只用 NumPy。
"""
import math
from dataclasses import dataclass

import numpy as np

from ..config import load_config
from ..sim.guidance import make_curve, nominal_time, speed_profile
from ..sim.kernel import member_config

FRAME_US = 100_000


@dataclass(frozen=True)
class KinematicPiece:
    t0: float
    t1: float
    p0: tuple
    v0: tuple
    a: tuple


@dataclass(frozen=True)
class Nominal:
    curve: object
    v: np.ndarray               # 节点速度
    t_nodes: np.ndarray         # 自曲线起点算起的名义时间
    travel_s: float
    release_s: float
    hold_s: float
    altitude_m: float

    @property
    def end_s(self):
        """名义结束的绝对时刻（统一时钟）：释放 + 行程 + 终点保持。"""
        return self.release_s + self.travel_s + self.hold_s

    def time_at_s(self, s_value):
        i = int(np.argmin(np.abs(self.curve.s - float(s_value))))
        return float(self.t_nodes[i])


def release_us(member_plan, sim=None):
    S = (sim if sim is not None else load_config("sim")).values
    return int(round((S["initial_settle_s"] + float(member_plan.release_delay_s)) * 10)) * FRAME_US


def member_nominal(member_plan, *, guidance=None, sim=None):
    G = (guidance if guidance is not None else load_config("guidance")).values
    S = (sim if sim is not None else load_config("sim")).values
    curve = make_curve(member_plan.curve_xy, max_chord_m=G["max_chord_m"], max_turn_rad=G["max_turn_per_chord_rad"])
    v_max = member_config().vehicle_profile.max_speed_xy_m_s
    L = curve.length
    v = speed_profile(curve, member_plan.speed_breaks, a_lat=G["a_lat_m_s2"], a_lon=G["a_lon_m_s2"], v_max=v_max,
                      v0=0.0, v_end=0.0, stops=(L,))
    dt = 2.0 * curve.chord / (v[:-1] + v[1:])
    t_nodes = np.r_[0.0, np.cumsum(dt)]
    # 与冻结的 nominal_time 逐位一致（用于自检，不一致说明剖面或节点定位出错）
    if abs(float(t_nodes[-1]) - nominal_time(curve, v, 0.0, L)) > 1e-9 * max(1.0, float(t_nodes[-1])):
        raise RuntimeError('名义时间表与冻结 nominal_time 不一致')
    return Nominal(curve, v, t_nodes, float(t_nodes[-1]), release_us(member_plan, sim) / 1e6, S["terminal_hold_s"],
                   float(member_plan.altitude_m))


def pieces(member_plan, *, include_prerelease=False, nominal=None):
    """分段匀加速运动的列表（绝对时刻，XY 平面）。"""
    nom = nominal or member_nominal(member_plan)
    c, v = nom.curve, nom.v
    out = []
    t_rel = nom.release_s
    if include_prerelease:
        out.append(KinematicPiece(0.0, t_rel, tuple(c.xy[0]), (0.0, 0.0), (0.0, 0.0)))
    for i in range(len(c.chord)):
        a = (v[i + 1] ** 2 - v[i] ** 2) / (2.0 * c.chord[i])
        e = c.tangent[i]
        out.append(KinematicPiece(t_rel + float(nom.t_nodes[i]), t_rel + float(nom.t_nodes[i + 1]), tuple(c.xy[i]),
                                  tuple(v[i] * e), tuple(a * e)))
    t_end = t_rel + nom.travel_s
    out.append(KinematicPiece(t_end, t_end + nom.hold_s, tuple(c.xy[-1]), (0.0, 0.0), (0.0, 0.0)))
    return out


@dataclass(frozen=True)
class NominalSample:
    time_us: np.ndarray
    p: np.ndarray
    v: np.ndarray


def sample_nominal(member_plan, *, include_prerelease=False, nominal=None):
    """10 Hz 整数微秒网格上的名义轨迹。默认从释放帧起，只取名义结束之前的完整帧。"""
    nom = nominal or member_nominal(member_plan)
    r_us = int(round(nom.release_s * 1e6))
    end_us = int(round(nom.end_s * 1e6))
    start_us = 0 if include_prerelease else r_us
    t_us = np.arange(start_us, end_us + 1, FRAME_US, dtype=np.int64)
    t = t_us / 1e6 - nom.release_s            # 相对释放时刻
    c, vv = nom.curve, nom.v
    p = np.zeros((len(t), 3))
    v = np.zeros((len(t), 3))
    p[:, 2] = nom.altitude_m
    travel = nom.travel_s
    moving = (t >= 0.0) & (t < travel)
    idx = np.clip(np.searchsorted(nom.t_nodes, t, side="right") - 1, 0, len(c.chord) - 1)
    u = t - nom.t_nodes[idx]
    a = (vv[idx + 1] ** 2 - vv[idx] ** 2) / (2.0 * c.chord[idx])
    ell = vv[idx] * u + 0.5 * a * u * u
    along = c.xy[idx] + ell[:, None] * c.tangent[idx]
    speed = vv[idx] + a * u
    p[:, :2] = np.where(moving[:, None], along, np.where((t < 0.0)[:, None], c.xy[0], c.xy[-1]))
    v[:, :2] = np.where(moving[:, None], speed[:, None] * c.tangent[idx], 0.0)
    return NominalSample(t_us, p, v)


# ---------------------------------------------------------------- 连续时间最小间距

@dataclass(frozen=True)
class MinDistance:
    min_distance_m: float
    time_s: float
    r0: tuple
    pair: tuple = ()


@dataclass(frozen=True)
class PieceArrays:
    t0: np.ndarray
    t1: np.ndarray
    p0: np.ndarray
    v0: np.ndarray
    a: np.ndarray


def piece_arrays(member_plan=None, *, nominal=None, include_prerelease=False):
    """与 pieces() 相同的分段运动，直接给数组（避免为两万条弦建 Python 对象）。"""
    nom = nominal or member_nominal(member_plan)
    c, v = nom.curve, nom.v
    n = len(c.chord)
    a = (v[1:] ** 2 - v[:-1] ** 2) / (2.0 * c.chord)
    r = nom.release_s
    t0 = r + nom.t_nodes[:-1]
    t1 = r + nom.t_nodes[1:]
    p0 = c.xy[:-1].copy()
    v0 = v[:-1, None] * c.tangent
    acc = a[:, None] * c.tangent
    end = r + nom.travel_s
    t0 = np.r_[t0, end]; t1 = np.r_[t1, end + nom.hold_s]
    p0 = np.vstack([p0, c.xy[-1]]); v0 = np.vstack([v0, [0.0, 0.0]]); acc = np.vstack([acc, [0.0, 0.0]])
    if include_prerelease:
        t0 = np.r_[0.0, t0]; t1 = np.r_[r, t1]
        p0 = np.vstack([c.xy[0], p0]); v0 = np.vstack([[0.0, 0.0], v0]); acc = np.vstack([[0.0, 0.0], acc])
    return PieceArrays(t0, t1, p0, v0, acc)


def _as_arrays(x):
    if isinstance(x, PieceArrays):
        return x
    x = list(x)
    return PieceArrays(np.array([p.t0 for p in x], float), np.array([p.t1 for p in x], float),
                       np.array([p.p0 for p in x], float), np.array([p.v0 for p in x], float),
                       np.array([p.a for p in x], float))


def _spans(A, B):
    """共同可见区间内按全部分段边界切开的子区间：返回 (t_lo, 相对 r0, vr, ar, T)。"""
    lo = max(A.t0[0], B.t0[0])
    hi = min(A.t1[-1], B.t1[-1])
    if not hi > lo:
        return None
    edges = np.unique(np.concatenate([A.t0, A.t1, B.t0, B.t1]))
    edges = edges[(edges >= lo) & (edges <= hi)]
    if len(edges) < 2:
        return None
    t_lo, t_hi = edges[:-1], edges[1:]
    keep = t_hi > t_lo
    t_lo, t_hi = t_lo[keep], t_hi[keep]
    ia = np.clip(np.searchsorted(A.t0, t_lo, side="right") - 1, 0, len(A.t0) - 1)
    ib = np.clip(np.searchsorted(B.t0, t_lo, side="right") - 1, 0, len(B.t0) - 1)
    ua, ub = (t_lo - A.t0[ia])[:, None], (t_lo - B.t0[ib])[:, None]
    pa = A.p0[ia] + A.v0[ia] * ua + 0.5 * A.a[ia] * ua * ua
    va = A.v0[ia] + A.a[ia] * ua
    pb = B.p0[ib] + B.v0[ib] * ub + 0.5 * B.a[ib] * ub * ub
    vb = B.v0[ib] + B.a[ib] * ub
    return t_lo, pa - pb, va - vb, A.a[ia] - B.a[ib], t_hi - t_lo


def continuous_minimum(pieces_a, pieces_b):
    """两成员全时域（共同可见区间）的精确最小距离。

    每个共同子区间内相对位置 r(u) = r0 + vr u + ½ ar u²；‖r‖² 的导数（去掉公共因子 2）
    的升幂系数为 r0·vr、vr·vr + r0·ar、3/2 vr·ar、1/2 ar·ar。取端点值与区间内全部实根处的值。
    为避免对每个子区间都解三次方程，先用下界 ‖r0‖ − |vr|T − ½|ar|T² 做分支定界：
    只有下界低于当前最优值的子区间才精确求解（结果仍是精确的全时域最小值）。
    """
    sp = _spans(_as_arrays(pieces_a), _as_arrays(pieces_b))
    if sp is None:
        return MinDistance(math.inf, math.nan, (math.nan, math.nan))
    t_lo, r0, vr, ar, T = sp
    d0 = np.hypot(r0[:, 0], r0[:, 1])
    bound = d0 - np.hypot(vr[:, 0], vr[:, 1]) * T - 0.5 * np.hypot(ar[:, 0], ar[:, 1]) * T * T
    best, best_t, best_r = math.inf, math.nan, (math.nan, math.nan)
    for k in np.argsort(bound):
        if bound[k] >= best:
            break
        c = np.array([r0[k] @ vr[k], vr[k] @ vr[k] + r0[k] @ ar[k], 1.5 * (vr[k] @ ar[k]), 0.5 * (ar[k] @ ar[k])])
        us = [0.0, float(T[k])]
        while len(c) > 1 and abs(c[-1]) <= 1e-14 * max(1.0, float(np.max(np.abs(c)))):
            c = c[:-1]
        if len(c) > 1:
            for root in np.roots(c[::-1]):
                if abs(root.imag) <= 1e-9 * max(1.0, abs(root.real)) and 0.0 <= root.real <= T[k]:
                    us.append(float(root.real))
        for u in us:
            r = r0[k] + vr[k] * u + 0.5 * ar[k] * u * u
            dist = float(np.hypot(r[0], r[1]))
            if dist < best:
                best, best_t, best_r = dist, float(t_lo[k] + u), (float(r[0]), float(r[1]))
    return MinDistance(best, best_t, best_r)
