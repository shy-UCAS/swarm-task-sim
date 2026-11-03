"""实测有效性检查（V8-02 r4 6.8、14.2；V8-11 第 2 部分，回归门禁也用到它）。

只看可见帧：成员释放之后、轨迹结束之前。所有时刻为绝对时刻（编组出发时刻 + 编组时钟），
须在 10 Hz 网格上。成员对只在两者都可见的公共帧上比较。
"""
from dataclasses import dataclass
from itertools import combinations
from typing import Optional

import numpy as np

from task_v07.criteria import load_criteria
from task_v07.geometry import geometry_facts

FRAME_US = 100_000
SEPARATION_VIOLATION = "separation_violation"
CONSTRAINT_VIOLATION = "constraint_violation"


@dataclass(frozen=True)
class VisibleTrack:
    member_id: str
    time_us: np.ndarray
    p: np.ndarray


@dataclass(frozen=True)
class ValidityReport:
    min_separation_m: Optional[float]
    closest_pair: Optional[tuple]
    member_min_separation_m: dict
    separation_ok: bool
    interp_min_separation_m: Optional[float]
    interp_closest_pair: Optional[tuple]
    restricted_frames: dict
    restricted_ok: bool
    outside_world_frames: dict
    failures: tuple
    codes: tuple
    passed: bool


def visible_track(track, release_us, offset_us=0) -> VisibleTrack:
    tau = np.asarray(track.tau_us, dtype=np.int64)
    keep = tau >= int(release_us)
    if not keep.any():
        raise ValueError(f"成员 {track.member_id} 释放后没有帧")
    return VisibleTrack(track.member_id, tau[keep] + int(offset_us), np.asarray(track.p, dtype=float)[keep])


def _check(track):
    t = np.asarray(track.time_us)
    if t.ndim != 1 or not len(t) or not np.issubdtype(t.dtype, np.integer):
        raise ValueError(f"{track.member_id}: time_us 须为非空一维整数数组")
    if np.any(t % FRAME_US) or (len(t) > 1 and np.any(np.diff(t) != FRAME_US)):
        raise ValueError(f"{track.member_id}: time_us 须在 10 Hz 网格上且等间隔")
    p = np.asarray(track.p, dtype=float)
    if p.shape != (len(t), 3) or not np.isfinite(p).all():
        raise ValueError(f"{track.member_id}: p 形状须为 (T, 3) 且有限")
    return t, p


def _interp_min(r0, r1):
    dr = r1 - r0
    dd = np.sum(dr * dr, axis=1)
    s = np.zeros(len(r0))
    nz = dd > 0
    s[nz] = np.clip(-np.sum(r0[nz] * dr[nz], axis=1) / dd[nz], 0.0, 1.0)
    return np.linalg.norm(r0 + s[:, None] * dr, axis=1)


def check_validity(scene, tracks, *, criteria=None) -> ValidityReport:
    cfg = criteria if criteria is not None else load_criteria()
    limit = cfg["quality"]["min_separation_error_m"]
    data = {}
    for tr in tracks:
        if tr.member_id in data:
            raise ValueError(f"成员 {tr.member_id} 重复")
        data[tr.member_id] = _check(tr)
    ids = sorted(data)
    member_min = {m: None for m in ids}
    best = best_pair = ibest = ibest_pair = None
    for a, b in combinations(ids, 2):
        ta, pa = data[a]
        tb, pb = data[b]
        common, ia, ib = np.intersect1d(ta, tb, assume_unique=True, return_indices=True)
        if not len(common):
            continue
        d = np.linalg.norm(pa[ia] - pb[ib], axis=1)
        k = int(np.argmin(d))
        value = float(d[k])
        if best is None or value < best:
            best, best_pair = value, (a, b, int(common[k]))
        for m in (a, b):
            member_min[m] = value if member_min[m] is None else min(member_min[m], value)
        nxt = np.flatnonzero(np.diff(common) == FRAME_US)
        if len(nxt):
            r = pa[ia] - pb[ib]
            di = _interp_min(r[nxt], r[nxt + 1])
            j = int(np.argmin(di))
            if ibest is None or float(di[j]) < ibest:
                ibest, ibest_pair = float(di[j]), (a, b, int(common[nxt[j]]))
    restricted, outside = {}, {}
    for m in ids:
        xy = data[m][1][:, :2]
        inside = np.zeros(len(xy), bool)
        for e in scene["entities"]:
            if e["type"] == "hard_constraint_obstacle":
                inside |= geometry_facts(e["geometry"], xy)["inside"]
        restricted[m] = int(inside.sum())
        outside[m] = int((~geometry_facts(scene["world"]["geometry"], xy)["inside"]).sum())
    failures = []
    if best is not None and best < limit:
        failures.append((f"{best_pair[0]}|{best_pair[1]}", "min_separation", SEPARATION_VIOLATION))
    failures += [(m, "restricted_zone", CONSTRAINT_VIOLATION) for m in ids if restricted[m]]
    failures = tuple(sorted(failures))
    return ValidityReport(
        min_separation_m=best, closest_pair=best_pair, member_min_separation_m=member_min,
        separation_ok=best is None or best >= limit, interp_min_separation_m=ibest, interp_closest_pair=ibest_pair,
        restricted_frames=restricted, restricted_ok=not any(restricted.values()), outside_world_frames=outside,
        failures=failures, codes=tuple(sorted({f[2] for f in failures})), passed=not failures)
