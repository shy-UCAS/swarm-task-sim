"""V8-13 骨架辅助（指令 4.1）：仅走廊宽度的队形选择、骨架时间参考与语义直线时间区间提取。

width_then_build 是生产 propose_and_build 唯一的队形选择/构造控制函数：按固定顺序只用宽度查询选队形，
选定后只构造一次并原样返回结果（含失败），不存在下游失败后的退让分支。

本模块导入时不读场景、不建目录；不导入 shapely。
"""
import math

import numpy as np


def width_then_build(candidates, width_probe, build):
    """candidates 固定顺序；width_probe(c)->payload 或 None。
    选到第一个 payload 后只调用一次 build(c,payload)，原样返回包括失败的结果；全为空返回 None。"""
    for c in candidates:
        payload = width_probe(c)
        if payload is None:
            continue
        return build(c, payload)
    return None


# ---------------------------------------------------------------- 骨架 → 时间参考

class NominalPVA:
    """名义分段匀加速运动（member_nominal 的弦内公式）在绝对时刻上的 p/v/a。
    释放前为起点、移动结束后为终点，v=a=0；只在 [release, release+travel] 内按弦内公式求值。"""

    def __init__(self, nominal):
        self.nom = nominal
        c, v = nominal.curve, nominal.v
        self.xy = np.asarray(c.xy, float)
        self.tan = np.asarray(c.tangent, float)
        self.v = np.asarray(v, float)
        self.tn = np.asarray(nominal.t_nodes, float)
        self.acc = (self.v[1:] ** 2 - self.v[:-1] ** 2) / (2.0 * np.asarray(c.chord, float))
        self.r = float(nominal.release_s)
        self.T = float(nominal.travel_s)

    def __call__(self, t_abs):
        t = np.asarray(t_abs, float)
        scalar = t.ndim == 0
        t = np.atleast_1d(t) - self.r
        moving = (t >= 0.0) & (t <= self.T)
        idx = np.clip(np.searchsorted(self.tn, t, side="right") - 1, 0, len(self.acc) - 1)
        u = np.clip(t - self.tn[idx], 0.0, None)
        a = self.acc[idx]
        ell = self.v[idx] * u + 0.5 * a * u * u
        along = self.xy[idx] + ell[:, None] * self.tan[idx]
        speed = self.v[idx] + a * u
        p = np.where(moving[:, None], along, np.where((t < 0.0)[:, None], self.xy[0], self.xy[-1]))
        vv = np.where(moving[:, None], speed[:, None] * self.tan[idx], 0.0)
        aa = np.where(moving[:, None], a[:, None] * self.tan[idx], 0.0)
        # 端点处精确取起终点（弦内公式在 t=T 落在最后一弦末端，舍入可能差 1 ulp）
        p = np.where((t == 0.0)[:, None], self.xy[0], p)
        p = np.where((t == self.T)[:, None], self.xy[-1], p)
        if scalar:
            return p[0], vv[0], aa[0]
        return p, vv, aa

    def time_at_s(self, s):
        return float(np.interp(float(s), self.nom.curve.s, self.tn)) + self.r


def _band_ranges(xy, geom, band_m):
    from ..scene.exact import chord_sdf_range
    lo, hi, _ = chord_sdf_range(geom, xy[:-1], xy[1:])
    band = (lo < band_m) & (hi > -band_m)
    edges = np.flatnonzero(np.diff(np.r_[False, band, False].astype(np.int8)))
    return list(zip(edges[::2].tolist(), edges[1::2].tolist()))


def semantic_lines(member_id, nominal, warnings, target_id, *, band_m, align_m):
    """该成员骨架上的语义直线：每个设施实际穿越段的带（外 +10 至内 −10，按顶点区间），目标每次入圈并入前 align_m。
    返回 [(member_id, t0, t1, point_xy, unit_tangent_xy, meta)]，时间按该成员名义 t_nodes/s 映射。"""
    from ..motion.connect import crossing_analysis
    xy = np.asarray(nominal.curve.xy, float)
    s = np.asarray(nominal.curve.s, float)
    f = NominalPVA(nominal)
    _, crossings = crossing_analysis(xy, warnings, target_id, band_m=band_m, align_m=align_m)
    out = []
    for c in crossings:
        runs = _band_ranges(xy, warnings[c.facility_id], band_m)
        run = next(((a, b) for a, b in runs if a <= c.chord_index < b), None)
        if run is None:
            continue
        a, b = run
        s0, s1 = float(s[a]), float(s[b])
        if c.direction == "in" and c.facility_id == target_id:
            s0 = min(s0, c.s_m - align_m)
        s0 = max(s0, 0.0)
        p0 = np.array([np.interp(s0, s, xy[:, 0]), np.interp(s0, s, xy[:, 1])])
        p1 = np.array([np.interp(s1, s, xy[:, 0]), np.interp(s1, s, xy[:, 1])])
        d = p1 - p0
        L = math.hypot(d[0], d[1])
        if L <= 0.0:
            continue
        pc = np.array([np.interp(c.s_m, s, xy[:, 0]), np.interp(c.s_m, s, xy[:, 1])])
        out.append((member_id, f.time_at_s(s0), f.time_at_s(s1), tuple(map(float, pc)), (d[0] / L, d[1] / L),
                    {"facility": c.facility_id, "direction": c.direction, "s_from_m": s0, "s_to_m": s1,
                     "s_cross_m": float(c.s_m)}))
    return out


def references_from_skeleton(skeleton, *, warnings=None, target_id=None, band_m=None, align_m=None):
    """返回 (TimeReference 元组, 语义直线区间, 成员站点→时间映射)。
    移动参考 = 名义分段匀加速运动，[release, release + travel]（不含末端保持；附录裁定 9.4）。"""
    from ..sim.tracking import TimeReference
    from .nominal import member_nominal
    refs, lines, maps = [], [], {}
    for m in sorted(skeleton.members):
        mp = skeleton.members[m]
        nom = member_nominal(mp)
        f = NominalPVA(nom)
        refs.append(TimeReference(m, float(nom.release_s), float(nom.release_s + nom.travel_s),
                                  float(nom.altitude_m), f))
        maps[m] = {"curve_s": np.asarray(nom.curve.s, float), "t_abs": f.tn + f.r, "nominal": nom}
        if warnings is not None:
            lines.extend(semantic_lines(m, nom, warnings, target_id, band_m=band_m, align_m=align_m))
    return tuple(refs), tuple(lines), maps
