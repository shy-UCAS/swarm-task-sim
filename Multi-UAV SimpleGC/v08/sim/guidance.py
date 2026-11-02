"""新引导层的纯函数（V8-07；V8-08 第 2 部分）：加密曲线、速度剖面、投影与引导律。

参数一律由调用方传入，本模块不读配置；输入违反约定时抛 SimContractError。
"""
import math
from dataclasses import dataclass

import numpy as np

from .types import SimContractError

NODE_TOL_M = 1e-6
MIN_CHORD_M = 1e-9
KAPPA_FLOOR = 1e-12


def _readonly(a):
    a = np.array(a, dtype=float)
    a.setflags(write=False)
    return a


def _wrap(a):
    return (a + math.pi) % (2.0 * math.pi) - math.pi


# ---------------------------------------------------------------- 2.1 曲线

@dataclass(frozen=True)
class Curve:
    """加密曲线：xy (N, 2)、累计弦长 s (N,)、弦长 chord (N−1,)、弦单位方向 tangent (N−1, 2)、
    有符号曲率 kappa (N,)（逆时针为正）。"""
    xy: np.ndarray
    s: np.ndarray
    chord: np.ndarray
    tangent: np.ndarray
    kappa: np.ndarray

    @property
    def length(self):
        return float(self.s[-1])


def make_curve(xy, *, max_chord_m, max_turn_rad):
    try:
        P = np.asarray(xy, dtype=float)
    except (TypeError, ValueError) as exc:
        raise SimContractError(f"曲线点无法转换为数组：{exc}") from None
    if P.ndim != 2 or P.shape[1] != 2 or P.shape[0] < 2:
        raise SimContractError(f"曲线点形状应为 (N ≥ 2, 2)，实际 {P.shape}")
    if not np.all(np.isfinite(P)):
        raise SimContractError("曲线点含非有限值")
    d = np.diff(P, axis=0)
    chord = np.hypot(d[:, 0], d[:, 1])
    if np.any(chord <= MIN_CHORD_M):
        i = int(np.argmax(chord <= MIN_CHORD_M))
        raise SimContractError(f"第 {i} 条弦长度 {float(chord[i])} m ≤ {MIN_CHORD_M} m")
    if np.any(chord > max_chord_m):
        i = int(np.argmax(chord > max_chord_m))
        raise SimContractError(f"第 {i} 条弦长度 {float(chord[i])} m > {max_chord_m} m")
    tangent = d / chord[:, None]
    n = P.shape[0]
    kappa = np.zeros(n)
    if n >= 3:
        theta = np.arctan2(tangent[:, 1], tangent[:, 0])
        dtheta = _wrap(np.diff(theta))
        if np.any(np.abs(dtheta) > max_turn_rad):
            i = int(np.argmax(np.abs(dtheta) > max_turn_rad)) + 1
            raise SimContractError(f"第 {i} 条弦与前一条方向差 {float(dtheta[i - 1])} rad 超过 {max_turn_rad} rad")
        kappa[1:-1] = dtheta / ((chord[:-1] + chord[1:]) / 2.0)
        kappa[0] = kappa[1]
        kappa[-1] = kappa[-2]
    s = np.r_[0.0, np.cumsum(chord)]
    return Curve(_readonly(P), _readonly(s), _readonly(chord), _readonly(tangent), _readonly(kappa))


# ---------------------------------------------------------------- 2.2 节点定位

def node_index(curve, s_value):
    i = int(np.argmin(np.abs(curve.s - float(s_value))))
    if abs(float(curve.s[i]) - float(s_value)) > NODE_TOL_M:
        raise SimContractError(f"弧长 {s_value} m 不在节点上（最近节点 {i}，s = {float(curve.s[i])} m）")
    return i


# ---------------------------------------------------------------- 2.3 速度剖面

def speed_profile(curve, speed_breaks, *, a_lat, a_lon, v_max, v0=None, v_end=None, stops=()):
    try:
        br = np.asarray(speed_breaks, dtype=float)
    except (TypeError, ValueError) as exc:
        raise SimContractError(f"speed_breaks 无法转换为数组：{exc}") from None
    if br.ndim != 2 or br.shape[1] != 2 or br.shape[0] < 1:
        raise SimContractError(f"speed_breaks 应为 (s, v) 序列，实际形状 {br.shape}")
    if not np.all(np.isfinite(br)):
        raise SimContractError("speed_breaks 含非有限值")
    starts, speeds = br[:, 0], br[:, 1]
    if starts[0] != 0.0:
        raise SimContractError(f"speed_breaks 第一个 s 应为 0，实际 {float(starts[0])}")
    if np.any(np.diff(starts) <= 0.0):
        raise SimContractError("speed_breaks 的 s 不严格递增")
    if np.any(speeds <= 0.0) or np.any(speeds > v_max):
        raise SimContractError(f"speed_breaks 的速度须在 (0, {v_max}] 内")
    s = curve.s
    n = len(s)
    v_cmd = speeds[np.searchsorted(starts, s, side="right") - 1]
    cap = np.minimum(v_cmd, np.sqrt(a_lat / np.maximum(np.abs(curve.kappa), KAPPA_FLOOR)))
    for s_stop in stops:
        cap[node_index(curve, s_stop)] = 0.0
    if v_end is not None:
        cap[-1] = min(cap[-1], float(v_end))
    v = cap.copy()
    c = curve.chord
    for i in range(n - 2, -1, -1):
        v[i] = min(cap[i], math.sqrt(v[i + 1] ** 2 + 2.0 * a_lon * c[i]))
    if v0 is not None:
        v[0] = min(v[0], float(v0))
    for i in range(1, n):
        v[i] = min(v[i], math.sqrt(v[i - 1] ** 2 + 2.0 * a_lon * c[i - 1]))
    return _readonly(v)


# ---------------------------------------------------------------- 2.4 名义用时

def nominal_time(curve, v, s_from, s_to):
    i0, i1 = node_index(curve, s_from), node_index(curve, s_to)
    v = np.asarray(v, dtype=float)
    pair = v[i0:i1] + v[i0 + 1:i1 + 1]
    if np.any(pair <= 0.0):
        i = i0 + int(np.argmax(pair <= 0.0))
        raise SimContractError(f"第 {i} 条弦两端速度都为 0，名义用时无界")
    return float(np.sum(2.0 * curve.chord[i0:i1] / pair))


# ---------------------------------------------------------------- 2.5 投影

def project(curve, p_xy, s_prev, window_m):
    s = curve.s
    n = len(s)
    lo = max(0, int(np.searchsorted(s, s_prev - window_m, side="right")) - 1)
    hi = min(n - 1, int(np.searchsorted(s, s_prev + window_m, side="left")) + 1)
    p = np.asarray(p_xy, dtype=float)[:2]
    xy = curve.xy[lo:hi]
    T = curve.tangent[lo:hi]
    t = np.clip(np.sum((p - xy) * T, axis=1), 0.0, curve.chord[lo:hi])
    q = xy + t[:, None] * T
    k = int(np.argmin(np.hypot(q[:, 0] - p[0], q[:, 1] - p[1])))
    j = lo + k
    return j, float(s[j] + t[k]), q[k].copy()


# ---------------------------------------------------------------- 2.6 引导律

def desired_velocity(curve, v, p, s_prev, *, tau, k_pos, lookahead_m, slope_half_m, s_limit, window_m, altitude):
    p = np.asarray(p, dtype=float)
    j, s_p, q = project(curve, p[:2], s_prev, window_m)
    s = curve.s
    L = curve.length
    s_l = min(s_p + lookahead_m, s_limit)
    v_r = float(np.interp(s_l, s, v))
    lo = max(s_l - slope_half_m, 0.0)
    hi = min(s_l + slope_half_m, L)
    dv = (float(np.interp(hi, s, v)) - float(np.interp(lo, s, v))) / (hi - lo)
    T = curve.tangent[j]
    N = np.array([-T[1], T[0]])
    kappa = float(np.interp(s_p, s, curve.kappa))
    a_ff = kappa * v_r * v_r * N + v_r * dv * T
    v_xy = v_r * T + tau * a_ff + k_pos * (q - p[:2])
    return np.array([v_xy[0], v_xy[1], k_pos * (altitude - p[2])]), s_p
