"""队形槽位与成员曲线派生（V8-12 第 3 部分；r4 6.7、附录裁定 1、5）。

成员槽位先按 formation 键随机排列，与机号、起点无关。令居中槽位 j_i = i − (n−1)/2，b = family.lateral_spacing_m：
  abreast: l_i = 0, d_i = j_i b        column: l_i = j_i b, d_i = 0        echelon: l_i = j_i b, d_i = j_i·b_lat
纵列 d = 0（不为满足"相邻横向差 ≥ 3 m"改成横排；纵列用连续时间间距检查）。
成员路径 p_i(s) = c(s + l_i) + d_i n(s + l_i)，n 为参考曲线的左法向。本版队形在整条路径上取常数偏移
（恒定偏移是 r4 允许的特例）；退让是整条路径换队形，不在路径内形变。
"""
import math
from dataclasses import dataclass

import numpy as np

from ..sampler.keys import RngKey, rng_for

FORMATIONS = ("abreast", "echelon", "column")
PRIORS = ("abreast", "column", "echelon", "loose")
MIN_LATERAL_STEP_M = 3.0   # r4 6.7.1 / 指令 3.4：梯形横向步长缩到不小于 3 m


def mapped_start(prior):
    """监视段的起点队形：loose 按横排处理（附录裁定 5），之后走 横排 → 梯形 → 纵列 的退让链。"""
    return "abreast" if prior == "loose" else prior


def retreat_chain(start):
    chain = {"abreast": ("abreast", "echelon", "column"), "echelon": ("echelon", "column"), "column": ("column",)}
    return chain[start]


@dataclass(frozen=True)
class Slots:
    order: tuple
    offsets: dict               # 成员 -> (l, d)
    prior: str
    start: str
    realized: str
    mapped_from_loose: bool
    spacing_m: float
    lateral_step_m: float

    @property
    def footprint_m(self):
        return max((math.hypot(l, d) for l, d in self.offsets.values()), default=0.0)

    @property
    def max_longitudinal_m(self):
        return max((abs(l) for l, _ in self.offsets.values()), default=0.0)

    @property
    def max_lateral_m(self):
        return max((abs(d) for _, d in self.offsets.values()), default=0.0)


def formation_key(key):
    return key if key.purpose == "formation" else RngKey(key.family_id, key.draw, "formation", mission=key.mission,
                                                         branch=key.branch, group=key.group, segment=key.segment,
                                                         attempt=key.attempt)


def formation_slots(group, family, key, *, formation=None, lateral_step_m=None, order=None):
    members = tuple(sorted(group.member_ids))
    n = len(members)
    if order is None:
        perm = rng_for(formation_key(key)).permutation(n)
        order = tuple(members[int(k)] for k in perm)
    if sorted(order) != list(members):
        raise ValueError("槽位顺序必须恰好包含全体成员")
    start = mapped_start(group.formation_prior)
    realized = formation or start
    if realized not in FORMATIONS:
        raise ValueError(f"未知队形：{realized!r}")
    b = float(family.lateral_spacing_m)
    step = b if lateral_step_m is None else float(lateral_step_m)
    offsets = {}
    for i, m in enumerate(order):
        j = i - (n - 1) / 2.0
        if realized == "abreast":
            offsets[m] = (0.0, j * b)
        elif realized == "column":
            offsets[m] = (j * b, 0.0)
        else:
            offsets[m] = (j * b, j * step)
    return Slots(tuple(order), offsets, group.formation_prior, start, realized, group.formation_prior == "loose", b,
                 step if realized == "echelon" else b)


@dataclass(frozen=True)
class Reference:
    xy: np.ndarray
    theta: np.ndarray
    kappa: np.ndarray
    s: np.ndarray
    marks: dict               # 名称 -> 参考弧长
    segments: tuple           # ((名称, s_lo, s_hi), ...)


def make_reference(sampled, marks_by_index, segments_by_index):
    xy = sampled.xy
    s = np.r_[0.0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
    marks = {k: float(s[i]) for k, i in marks_by_index.items()}
    segs = tuple((name, float(s[a]), float(s[b])) for name, a, b in segments_by_index)
    return Reference(xy, np.unwrap(sampled.theta), sampled.kappa, s, marks, segs)


@dataclass(frozen=True)
class Lane:
    member_id: str
    xy: np.ndarray            # (N, 2) 加密后的成员曲线（尚不含起点连接）
    s_ref: np.ndarray         # 每点对应的参考弧长（用于把参考站点映射到成员弧长）
    d_m: float
    l_m: float


def _densify(xy, s_ref, limit):
    """把超过 limit 的弦均分，保持折线几何不变。"""
    ch = np.hypot(*np.diff(xy, axis=0).T)
    if not np.any(ch > limit):
        return xy, s_ref
    out_xy, out_s = [xy[0]], [s_ref[0]]
    for i in range(len(ch)):
        k = int(math.ceil(ch[i] / limit))
        if k > 1:
            f = np.arange(1, k) / k
            out_xy.extend(xy[i] + f[:, None] * (xy[i + 1] - xy[i]))
            out_s.extend(s_ref[i] + f * (s_ref[i + 1] - s_ref[i]))
        out_xy.append(xy[i + 1])
        out_s.append(s_ref[i + 1])
    return np.array(out_xy), np.array(out_s)


def derive_members(reference, slots, station_offsets, *, spacing_m, max_chord_m=0.9):
    """每个成员沿参考的偏移车道。station_offsets = (s_lo, s_hi)：编组站点范围，成员 i 实际走
    [s_lo + l_i, s_hi + l_i]（参考须覆盖该范围，否则抛 ValueError，不做端点 clamp）。"""
    s_lo, s_hi = station_offsets
    R = reference
    out = {}
    for m in slots.order:
        l, d = slots.offsets[m]
        a, b = s_lo + l, s_hi + l
        if a < -1e-9 or b > R.s[-1] + 1e-9:
            raise ValueError(f"成员 {m} 的站点范围 [{a}, {b}] 超出参考 [0, {R.s[-1]}]")
        a, b = max(a, 0.0), min(b, float(R.s[-1]))
        inner = R.s[(R.s > a + 1e-9) & (R.s < b - 1e-9)]
        st = np.r_[a, inner, b]
        cx, cy = np.interp(st, R.s, R.xy[:, 0]), np.interp(st, R.s, R.xy[:, 1])
        th = np.interp(st, R.s, R.theta)
        n = np.stack([-np.sin(th), np.cos(th)], axis=1)
        xy = np.stack([cx, cy], axis=1) + d * n
        xy, st = _densify(xy, st, max_chord_m)
        out[m] = Lane(m, xy, st, d, l)
    return out
