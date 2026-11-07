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


# ======================= V8-16：过境名义预筛（本项新增；不改上面的原样抽取函数） =======================

def screen_transit_member(facilities, target_id, time_us, p, v, criteria=None):
    """过境窗口 = 释放后的名义（或优化后）轨迹 10 Hz 帧（V8-16 指令 4.1）。conditions 全为真才 passed：
    started_outside_target_warning（首帧目标层 0）、entered_warning、single_warning_visit（目标层 ≥ 1 的连续段恰 1 个，
    空窗口/从不进入不通过）、max_target_layer_one（目标最大层恰为 1）、other_layers_within_limit（其他设施 ≤ 1，
    单设施为 0）、no_dwell_window（全窗口 dwell 未检出）、no_revisit_window（全窗口 revisit 未检出；冻结规则内部只
    接纳目标层 == 1 且速度 ≥ 0.5 的 eligible 点，不扩大检测定义）、ended_outside_all_warning（末帧全部层 0）。
    另记按 work_mask 调用的冻结原条件 revisit_work，以便与段核验逐项核对。"""
    cfg = criteria if criteria is not None else load_criteria()
    t = np.asarray(time_us)
    xy = np.asarray(p, dtype=float)[:, :2]
    v = np.asarray(v, dtype=float)
    ids = [f.id for f in facilities]
    ti = ids.index(target_id)
    levels = np.zeros((len(t), len(ids)), np.int8)
    for j, f in enumerate(facilities):
        levels[:, j], _ = layer_levels(f, xy)
    tl = levels[:, ti]
    n = len(t)
    ones = np.ones(n, bool)
    center = np.asarray(facilities[ti].center, dtype=float)
    anywhere = dwell(xy, t, ones, cfg) if n else {"detected": False}
    rev_full = revisit(xy, v, t, tl, ones, center, cfg) if n else {"detected": False}
    rev_work = revisit(xy, v, t, tl, work_mask(tl), center, cfg) if n else {"detected": False}
    visits = runs(tl >= 1) if n else []
    other = [j for j in range(len(ids)) if j != ti]
    max_other = int(levels[:, other].max()) if (other and n) else 0
    cond = {"started_outside_target_warning": bool(n and tl[0] == 0),
            "entered_warning": bool(n and np.any(tl >= 1)),
            "single_warning_visit": bool(n and np.any(tl >= 1) and len(visits) == 1),
            "max_target_layer_one": bool(n and int(tl.max()) == 1),
            "other_layers_within_limit": bool(max_other <= 1),
            "no_dwell_window": not bool(anywhere["detected"]),
            "no_revisit_window": not bool(rev_full["detected"]),
            "ended_outside_all_warning": bool(n and int(levels[-1].max()) == 0)}
    return {"passed": all(cond.values()), "conditions": cond, "levels": levels, "revisit": rev_full,
            "revisit_work": rev_work, "dwell_anywhere": anywhere,
            "counts": {"frames": int(n), "visits": len(visits), "max_target_layer": int(tl.max()) if n else None,
                       "max_other_layer": max_other}}


# ======================= V8-16 指令 8.3：重访检测等价向量化候选（本项新增） =======================
# 只消除 Python 候选过滤开销；不换 KD-tree、不改半径 ≤、gap、time dtype、norm、起止 tie-break。
# 与上面原样抽取的 revisit 逐位相同才允许切换（tools/v08/revisit_equivalence_v16.py 三方对照）。

def _revisit_vectorized(xy, velocity, time_us, levels, frames, center, criteria=None):
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
    t_all = np.asarray(time_us)
    cells = np.floor(xy[indexes] / radius).astype(np.int64)          # 与逐 end 计算同一表达式
    par, anti = rules["parallel_max_deg"], rules["antiparallel_min_deg"]
    cov_min = rules["min_azimuth_coverage_deg"]
    for k, end in enumerate(indexes):
        c0, c1 = int(cells[k, 0]), int(cells[k, 1])
        lists = [buckets[(c0 + dx, c1 + dy)] for dx, dy in neighbours]
        n_all = sum(len(x) for x in lists)
        if n_all:
            starts = np.fromiter((s for lst in lists for s in lst), dtype=np.int64, count=n_all)
            starts = starts[t_all[end] - t_all[starts] >= gap_us]
            if len(starts):
                candidates = np.sort(starts).astype(int)
                distances = np.linalg.norm(xy[candidates] - xy[end], axis=1)
                candidates = candidates[distances <= radius]
                if len(candidates):
                    cosine = (velocity[candidates, :2] @ velocity[end, :2]) / (horizontal[candidates] * horizontal[end])
                    angles = np.degrees(np.arccos(np.clip(cosine, -1, 1)))
                    keep = (angles <= par) | (angles >= anti)
                    width = (end - candidates + 1).astype(np.int64)
                    power = (np.frexp(width.astype(np.float64))[1] - 1).astype(np.int64)
                    tail = end - np.left_shift(np.int64(1), power) + 1
                    bound = np.empty(len(candidates))
                    for pw in np.unique(power[keep]):
                        sel = keep & (power == pw)
                        mx, mn = maximums[int(pw)], minimums[int(pw)]
                        bound[sel] = (np.maximum(mx[candidates[sel]], mx[tail[sel]])
                                      - np.minimum(mn[candidates[sel]], mn[tail[sel]]))
                    keep[keep] &= ~(np.degrees(bound[keep]) < cov_min)
                    for start, angle in zip(candidates[keep], angles[keep]):
                        segment = xy[start:end + 1]
                        departure = float(np.linalg.norm(segment - xy[start], axis=1).max())
                        if departure < rules["min_departure_m"]:
                            continue
                        coverage_deg = azimuth_coverage(segment, center)
                        if coverage_deg < cov_min:
                            continue
                        return {"detected": True, "frame_index": int(start), "confirm_frame_index": int(end),
                                "t1": float(time_us[start] / 1e6), "t2": float(time_us[end] / 1e6),
                                "t_confirm": float(time_us[end] / 1e6),
                                "distance_m": float(np.linalg.norm(xy[start] - xy[end])), "departure_m": departure,
                                "heading_difference_deg": float(angle), "azimuth_coverage_deg": coverage_deg}
        buckets[(c0, c1)].append(int(end))
    return empty


# V8-16 指令 8.3 切换：三方逐位对照（V8-11 full 1440 次调用、监视快批 99 个窗口 × 两种 frames）与原实现 0 差异、
# 候选在同一输入上耗时约为原实现的 11%；公开名 revisit 指向向量化候选，原样抽取的原函数保留为 _revisit_original
# 作 oracle（不删除、不修改）。screen_member / screen_transit_member 按模块全局名调用，切换对两者同时生效。
_revisit_original = revisit
revisit = _revisit_vectorized


def screen_intrusion_member(facilities, target_id, time_us, p, v, criteria=None):
    """释放后的10Hz窗口；返回 passed/conditions/levels/counts/first_entry_us/
    end_contour_m/min_contour_m/dwell_anywhere；不调用 revisit。

    V8-17 指令 4.2：目标层序列 ℓ_t 由现有 layer_levels 给出（SDF ≤ 偏移）。conditions 全为真才 passed：
    started_outside_target_warning（非空且首帧 0）、target_layers_monotone（np.diff ≥ 0 全真）、
    single_warning/alert/protected_entry（M_j = ℓ_t ≥ j 的 False→True 次数恰 1；首帧 True 也计一次）、
    entered_protected（最大目标层 3）、near_facility_contour（最小 contour SDF ≤ 冻结 roles.intrusion.
    max_contour_distance_m = 50）、other_layers_within_limit（其他设施 ≤ 1，单设施为 0）、no_dwell_window（释放后整个
    窗口 dwell 未检出，含终点保持）。首次进入时刻为该层第一个 True 的整数 time_us，未进入为 None。"""
    cfg = criteria if criteria is not None else load_criteria()
    t = np.asarray(time_us)
    xy = np.asarray(p, dtype=float)[:, :2]
    ids = [f.id for f in facilities]
    ti = ids.index(target_id)
    n = len(t)
    levels = np.zeros((n, len(ids)), np.int8)
    contour = np.zeros(0)
    for j, f in enumerate(facilities):
        levels[:, j], sd = layer_levels(f, xy)
        if j == ti:
            contour = np.asarray(sd, float).reshape(-1)
    tl = levels[:, ti]
    entries, first = {}, {}
    for name, code in _LAYER_CODES:
        mask = tl >= code
        starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]]) if n else np.zeros(0, np.int64)
        entries[name] = int(len(starts))
        first[name] = int(t[starts[0]]) if len(starts) else None
    other = [j for j in range(len(ids)) if j != ti]
    max_other = int(levels[:, other].max()) if (other and n) else 0
    limit = float(cfg["roles"]["intrusion"]["max_contour_distance_m"])
    anywhere = dwell(xy, t, np.ones(n, bool), cfg) if n else {"detected": False}
    cond = {"started_outside_target_warning": bool(n and tl[0] == 0),
            "target_layers_monotone": bool(n and np.all(np.diff(tl) >= 0)),
            "single_warning_entry": bool(entries["warning"] == 1),
            "single_alert_entry": bool(entries["alert"] == 1),
            "single_protected_entry": bool(entries["protected"] == 1),
            "entered_protected": bool(n and int(tl.max()) == 3),
            "near_facility_contour": bool(n and float(contour.min()) <= limit),
            "other_layers_within_limit": bool(max_other <= 1),
            "no_dwell_window": not bool(anywhere["detected"])}
    return {"passed": all(cond.values()), "conditions": cond, "levels": levels, "dwell_anywhere": anywhere,
            "first_entry_us": first, "end_contour_m": float(contour[-1]) if n else None,
            "min_contour_m": float(contour.min()) if n else None,
            "counts": {"entries": entries, "frames": int(n), "max_target_layer": int(tl.max()) if n else None,
                       "max_other_layer": max_other}}


def screen_feint_member(facilities, target_id, time_us, p, v, criteria=None):
    """V8-18 指令 4.1：释放后的 10 Hz 窗口（含末端保持）；使用原 layer_levels、runs/dwell，不调用 revisit（泪滴反向
    重合不构成佯动失败）。conditions 全为真才 passed：
    started_outside_target_warning（非空且首帧目标层 0）、single_warning_entry / single_alert_entry（各层掩码
    False→True 次数恰 1，首帧 True 也计）、max_target_layer_two（目标最大层恰 2）、ended_outside_all_warning（末帧
    全部设施层 0）、other_layers_within_limit（其他设施最大层 ≤ 1，单设施为 0）、no_dwell_window（整个窗口 dwell 未检出）。
    空窗口的首帧/次数/最大层/末帧条件均为 False。进入索引 inside & ~r_[False, inside[:-1]]，退出索引
    ~inside & r_[False, inside[:-1]]；首次退出 = 首次进入后第一个 False 帧的整数微秒（不取最后一个 True、不在窗口末尾
    虚构退出）。入/出时刻是帧时刻，不是连续精确穿越时间。min_protected_sdf_m = 整窗 signed_distance(protected).min()。"""
    from ..scene.exact import signed_distance
    cfg = criteria if criteria is not None else load_criteria()
    t = np.asarray(time_us)
    xy = np.asarray(p, dtype=float)[:, :2]
    ids = [f.id for f in facilities]
    ti = ids.index(target_id)
    n = len(t)
    levels = np.zeros((n, len(ids)), np.int8)
    for j, f in enumerate(facilities):
        levels[:, j], _ = layer_levels(f, xy)
    tl = levels[:, ti]
    entries, first_in, first_out = {}, {}, {}
    for name, code in _LAYER_CODES[:2]:
        inside = tl >= code
        prev = np.r_[False, inside[:-1]] if n else np.zeros(0, bool)
        starts = np.flatnonzero(inside & ~prev)
        ends = np.flatnonzero(~inside & prev)
        entries[name] = int(len(starts))
        first_in[name] = int(t[starts[0]]) if len(starts) else None
        after = ends[ends > starts[0]] if len(starts) else np.zeros(0, np.int64)
        first_out[name] = int(t[after[0]]) if len(after) else None
    other = [j for j in range(len(ids)) if j != ti]
    max_other = int(levels[:, other].max()) if (other and n) else 0
    anywhere = dwell(xy, t, np.ones(n, bool), cfg) if n else {"detected": False}
    sp = np.asarray(signed_distance(facilities[ti].layers["protected"], xy), float).reshape(-1) if n else np.zeros(0)
    cond = {"started_outside_target_warning": bool(n and tl[0] == 0),
            "single_warning_entry": bool(n and entries["warning"] == 1),
            "single_alert_entry": bool(n and entries["alert"] == 1),
            "max_target_layer_two": bool(n and int(tl.max()) == 2),
            "ended_outside_all_warning": bool(n and int(levels[-1].max()) == 0),
            "other_layers_within_limit": bool(max_other <= 1),
            "no_dwell_window": not bool(anywhere["detected"])}
    return {"passed": all(cond.values()), "conditions": cond, "levels": levels, "counts": {
                "entries": entries, "frames": int(n), "max_target_layer": int(tl.max()) if n else None,
                "max_other_layer": max_other},
            "dwell_anywhere": anywhere, "first_entry_us": first_in, "first_exit_us": first_out,
            "min_protected_sdf_m": float(sp.min()) if n else None}
