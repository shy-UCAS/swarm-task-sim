"""速度剖面：泊松变速事件与它到离散参考曲线的映射（V8-12 第 3 部分；r4 6.10，附录裁定 6）。

事件按时间先后逐个处理：第 k 个事件用"只含前 k−1 个变速点"的速度剖面（冻结 speed_profile）算名义时间表，
映射到名义时间不早于事件时刻的第一个参考节点，再把该变速点加入剖面。顺序确定，没有不动点迭代，
也没有循环。映射误差（节点名义时间 − 事件时间）只作诊断报告。
"""
from dataclasses import dataclass

import numpy as np

from ..config import load_config
from ..sampler.keys import rng_for
from ..sim.guidance import speed_profile
from ..sim.kernel import member_config


@dataclass(frozen=True)
class SpeedEvents:
    times_s: tuple
    speeds_m_s: tuple


@dataclass(frozen=True)
class SpeedMap:
    breaks: tuple               # ((s, v), ...)，第一个 s 为 0
    errors_s: tuple             # 每个已映射事件的 节点名义时间 − 事件时间
    dropped: tuple              # 被删除的事件时间（过渡区间内或超出路径名义总时长）


def draw_speed_events(prior, key, *, horizon_s):
    """时间上的泊松过程：间隔 Exp(λ/60)，λ 为每分钟次数；新速度 U[speed_min, speed_max]。事件序列与意图无关。"""
    M = load_config("monitoring").values
    rng = rng_for(key)
    lam = float(prior.change_rate_per_min) / 60.0
    times, speeds = [], []
    t = 0.0
    while lam > 0.0:
        t += float(rng.exponential(1.0 / lam))
        if t > horizon_s:
            break
        times.append(t)
        speeds.append(float(rng.uniform(M["speed_min_m_s"], M["speed_max_m_s"])))
    return SpeedEvents(tuple(times), tuple(speeds))


def node_times(curve, v):
    dt = 2.0 * curve.chord / (v[:-1] + v[1:])
    return np.r_[0.0, np.cumsum(dt)]


def map_speed_events(reference_curve, event_times_s, new_speeds, anchors, guidance, *, initial_speed_m_s):
    """把事件映射到参考曲线节点。anchors 是 [(t_lo, t_hi)]：落在其中的事件删除、不顺延
    （单段首段没有跨任务过渡，传空）。"""
    G = (guidance if guidance is not None else load_config("guidance")).values
    v_max = member_config().vehicle_profile.max_speed_xy_m_s
    curve = reference_curve
    L = curve.length
    breaks = [(0.0, float(initial_speed_m_s))]
    errors, dropped = [], []
    for t_k, v_k in zip(event_times_s, new_speeds):
        if any(lo <= t_k <= hi for lo, hi in anchors):
            dropped.append(float(t_k))
            continue
        vp = speed_profile(curve, tuple(breaks), a_lat=G["a_lat_m_s2"], a_lon=G["a_lon_m_s2"], v_max=v_max,
                           v0=0.0, v_end=0.0, stops=(L,))
        T = node_times(curve, vp)
        hit = np.flatnonzero(T >= t_k)
        if not len(hit):
            dropped.append(float(t_k))
            continue
        i = int(hit[0])
        s_i = float(curve.s[i])
        if s_i >= L - 1e-9:                      # 终点停车节点之后改速度没有意义
            dropped.append(float(t_k))
            continue
        errors.append(float(T[i] - t_k))
        if s_i <= breaks[-1][0]:                 # 同一节点上的后一个事件覆盖前一个
            breaks[-1] = (breaks[-1][0], float(v_k))
        else:
            breaks.append((s_i, float(v_k)))
    return SpeedMap(tuple(breaks), tuple(errors), tuple(dropped))
