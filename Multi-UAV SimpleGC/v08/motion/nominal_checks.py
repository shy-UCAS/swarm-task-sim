"""名义判据预筛选（V8-12 第 3 部分）。不导入 shapely，也不导入 task_v07.detectors / geometry（后者依赖 shapely）。

下面标记为"原样抽取"的五个函数逐字取自固定提交 4d2cf5df48187671f0dd9aa0018a69adac829911 的
Multi-UAV SimpleGC/task_v07/detectors.py（runs 第11–13行, work_mask 第16–21行, azimuth_coverage 第24–29行, dwell 第32–64行, revisit 第67–129行），运算、tie-break 与阈值读取不变；
抽取块的 SHA256（UTF-8、LF、函数间两个空行）为 d08052579868ebd284952edb5bc1879ee577b48ec9d8b45345e0a3441f74b8d6。
圈层由本项精确几何（v08.scene.exact）给出，规则与 task_v07/geometry.py:geometry_facts 相同：
signed ≤ offset 取最内层（protected=3 > alert=2 > warning=1）。
最终权威仍是 V8-11 的窗口版判据与仿真后核验；本模块只是生成时的筛选，不是标签。
"""
from collections import defaultdict
from itertools import product

import numpy as np

from task_v07.criteria import load_criteria
from ..scene.exact import signed_distance

# ======================= 原样抽取开始 =======================


def runs(mask):
    edges = np.flatnonzero(np.diff(np.r_[False, mask, False].astype(np.int8)))
    return list(zip(edges[::2].tolist(), edges[1::2].tolist()))


def work_mask(levels):
    selected = np.flatnonzero(np.asarray(levels) >= 1)
    result = np.zeros(len(levels), bool)
    if len(selected):
        result[selected[0]:selected[-1] + 1] = True
    return result


def azimuth_coverage(xy, center):
    if not len(xy):
        return 0.0
    delta = np.asarray(xy) - center
    angles = np.sort(np.mod(np.arctan2(delta[:, 1], delta[:, 0]), 2 * np.pi))
    return float(np.degrees(2 * np.pi - np.diff(np.r_[angles, angles[0] + 2 * np.pi]).max()))


def dwell(xy, time_us, frames, criteria=None):
    rules = (criteria or load_criteria())["detectors"]["dwell"]
    xy = np.asarray(xy, float)
    size = round(rules["window_s"] * 10) + 1
    accepted = []
    for begin, stop in runs(frames):
        if stop - begin < size:
            continue
        starts = np.arange(begin, stop - size + 1)
        ends = starts + size - 1
        starts = starts[np.linalg.norm(xy[ends] - xy[starts], axis=1) <= rules["max_start_end_m"]]
        # Bound memory independently of trajectory length. Mean is computed
        # locally, avoiding cumulative-sum cancellation at large coordinates.
        for offset in range(0, len(starts), 512):
            block = starts[offset:offset + 512]
            windows = xy[block[:, None] + np.arange(size)]
            delta = windows - windows.mean(axis=1, keepdims=True)
            valid = np.max(np.sum(delta * delta, axis=2), axis=1) <= rules["radius_m"] ** 2
            accepted.extend(block[valid].tolist())
    intervals = []
    for begin in accepted:
        end = begin + size - 1
        if intervals and begin <= intervals[-1][1]:
            intervals[-1][1] = max(end, intervals[-1][1])
        else:
            intervals.append([begin, end])
    first = accepted[0] if accepted else None
    confirm = None if first is None else first + size - 1
    return {"detected": first is not None, "frame_index": first, "confirm_frame_index": confirm,
            "t_s": None if first is None else float(time_us[first] / 1e6),
            "t_confirm": None if confirm is None else float(time_us[confirm] / 1e6),
            "total_duration_s": sum(float(time_us[e] - time_us[b]) / 1e6 for b, e in intervals),
            "union_frame_intervals": intervals}


def revisit(xy, velocity, time_us, levels, frames, center, criteria=None):
    rules = (criteria or load_criteria())["detectors"]["revisit"]
    xy, velocity = np.asarray(xy, float), np.asarray(velocity, float)
    empty = {"detected": False, "frame_index": None, "confirm_frame_index": None,
             "t1": None, "t2": None, "t_confirm": None, "distance_m": None,
             "departure_m": None, "heading_difference_deg": None, "azimuth_coverage_deg": None}
    speed = np.linalg.norm(velocity, axis=1)
    horizontal = np.linalg.norm(velocity[:, :2], axis=1)
    eligible = np.asarray(frames, bool) & (np.asarray(levels) == 1)
    eligible &= (speed >= rules["min_speed_m_s"]) & (horizontal > 0)
    indexes = np.flatnonzero(eligible)
    if not len(indexes):
        return empty
    if azimuth_coverage(xy[indexes[0]:indexes[-1] + 1], center) < rules["min_azimuth_coverage_deg"]:
        return empty
    radius = rules["radius_m"]
    gap_us = 2 * (rules["min_departure_m"] - radius) / float(speed.max()) * 1e6
    buckets = defaultdict(list)
    neighbours = tuple(product((-1, 0, 1), repeat=2))
    relative = xy - center
    unwrapped = np.unwrap(np.arctan2(relative[:, 1], relative[:, 0]))
    minimums, maximums = [unwrapped], [unwrapped]
    block = 1
    while block * 2 <= len(xy):
        minimums.append(np.minimum(minimums[-1][:-block], minimums[-1][block:]))
        maximums.append(np.maximum(maximums[-1][:-block], maximums[-1][block:]))
        block *= 2
    for end in indexes:
        cell = tuple(np.floor(xy[end] / radius).astype(np.int64))
        candidates = [start for dx, dy in neighbours for start in buckets[(cell[0] + dx, cell[1] + dy)]
                      if time_us[end] - time_us[start] >= gap_us]
        # Endpoints processed chronologically; sorted starts implement the tie break.
        if candidates:
            candidates = np.array(sorted(candidates), dtype=int)
            distances = np.linalg.norm(xy[candidates] - xy[end], axis=1)
            candidates = candidates[distances <= radius]
            if len(candidates):
                cosine = (velocity[candidates, :2] @ velocity[end, :2]) / (horizontal[candidates] * horizontal[end])
                angles = np.degrees(np.arccos(np.clip(cosine, -1, 1)))
                for start, angle in zip(candidates, angles):
                    if not (angle <= rules["parallel_max_deg"] or angle >= rules["antiparallel_min_deg"]):
                        continue
                    width = int(end - start + 1); power = width.bit_length() - 1
                    tail = end - (1 << power) + 1
                    extent_bound = max(maximums[power][start], maximums[power][tail]) - min(minimums[power][start], minimums[power][tail])
                    # An unwrapped range is an upper bound, never a replacement
                    # for the exact largest-circular-gap test below.
                    if np.degrees(extent_bound) < rules["min_azimuth_coverage_deg"]:
                        continue
                    segment = xy[start:end + 1]
                    departure = float(np.linalg.norm(segment - xy[start], axis=1).max())
                    if departure < rules["min_departure_m"]:
                        continue
                    coverage_deg = azimuth_coverage(segment, center)
                    if coverage_deg < rules["min_azimuth_coverage_deg"]:
                        continue
                    return {"detected": True, "frame_index": int(start), "confirm_frame_index": int(end),
                            "t1": float(time_us[start] / 1e6), "t2": float(time_us[end] / 1e6),
                            "t_confirm": float(time_us[end] / 1e6),
                            "distance_m": float(np.linalg.norm(xy[start] - xy[end])), "departure_m": departure,
                            "heading_difference_deg": float(angle), "azimuth_coverage_deg": coverage_deg}
        buckets[cell].append(int(end))
    return empty


# ======================= 原样抽取结束 =======================

_LAYER_CODES = (("warning", 1), ("alert", 2), ("protected", 3))


def layer_levels(facility, xy):
    """设施 facility（v08.scene.context.Facility）在各点的圈层 0–3，以及到设施轮廓的有符号距离。"""
    signed = signed_distance(facility.geometry, xy)
    level = np.zeros(np.shape(signed), np.int8)
    for name, code in _LAYER_CODES:
        level = np.where(signed <= facility.offsets[name], code, level)
    return level, signed


def screen_member(facilities, target_id, time_us, p, v, criteria=None):
    """窗口 = 释放后的名义轨迹（10 Hz）。返回与 V8-11 对应的监视判据原始值。"""
    cfg = criteria if criteria is not None else load_criteria()
    t = np.asarray(time_us)
    xy = np.asarray(p, dtype=float)[:, :2]
    v = np.asarray(v, dtype=float)
    ids = [f.id for f in facilities]
    ti = ids.index(target_id)
    levels = np.zeros((len(t), len(ids)), np.int8)
    signed_t = None
    for j, f in enumerate(facilities):
        levels[:, j], s = layer_levels(f, xy)
        if j == ti:
            signed_t = s
    tl = levels[:, ti]
    work = work_mask(tl)
    anywhere = dwell(xy, t, np.ones(len(t), bool), cfg)
    revisiting = revisit(xy, v, t, tl, work, np.asarray(facilities[ti].center, dtype=float), cfg)
    other = [j for j in range(len(ids)) if j != ti]
    return {"patrol_revisit": bool(revisiting["detected"]), "revisit": revisiting,
            "dwell_anywhere": anywhere, "max_target_layer": int(tl.max()),
            "max_other_layer": int(levels[:, other].max()) if other else 0,
            "levels": levels, "target_signed_m": signed_t}
