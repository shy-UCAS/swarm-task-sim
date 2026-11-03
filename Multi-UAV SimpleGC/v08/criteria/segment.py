"""段核验（V8-02 r4 9.2；V8-11 第 3 部分）。

对一个编组的每个执行段，在各成员自己的段窗口上用窗口版判据核验本段意图。
成员 m 第 k 段的窗口 = 拼接轨迹中 segment_index == k 的帧；第 0 段另去掉释放前的帧
（tau_us < release_us[m]）。全部条件都在窗口已结束（settled=True）时下结论。
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np

from task_v07.criteria import load_criteria

from ..config import load_config
from .window import KINDS, group_window, measure_member_window, scene_geometry

SEMANTIC_FAILED = "segment_semantic_failed"
SEMANTIC_AMBIGUOUS = "semantic_ambiguous"
CONSTRAINT_VIOLATION = "constraint_violation"

# 各意图沿用的 v0.7 条件（窗口版 conditions 中的键）
_V07_KEYS = {
    "transit": ("entered_warning", "single_warning_visit", "no_dwell", "no_revisit"),
    "area_search": ("effective_observation", "no_revisit"),
    "close_observation": ("observation_dwell", "no_revisit"),
    "monitoring": ("patrol_revisit",),
    "feint": ("entered_alert", "single_alert_visit"),
    "intrusion": ("entered_protected", "near_facility_contour"),
}
_CODES = {"no_dwell_window": SEMANTIC_AMBIGUOUS, "other_facilities_within_limit": CONSTRAINT_VIOLATION}


@dataclass(frozen=True)
class SegmentTask:
    index: int
    intent: str
    target_id: str
    survey: Optional[dict] = None


@dataclass(frozen=True)
class SegmentVerdict:
    index: int
    intent: str
    target_id: str
    final: bool
    window_frames: dict
    member_conditions: dict
    group_conditions: dict
    failures: tuple
    codes: tuple
    passed: bool
    windows: dict
    group: dict


def segment_frames(track, release_us, count):
    seg = np.asarray(track.segment_index)
    tau = np.asarray(track.tau_us)
    if not len(seg) or int(seg.min()) != 0 or int(seg.max()) != count - 1:
        raise ValueError(f"成员 {track.member_id} 的段号应为 0..{count - 1}")
    out = []
    for k in range(count):
        idx = np.flatnonzero(seg == k)
        if not len(idx):
            raise ValueError(f"成员 {track.member_id} 没有第 {k} 段的帧")
        lo, hi = int(idx[0]), int(idx[-1]) + 1
        if hi - lo != len(idx):
            raise ValueError(f"成员 {track.member_id} 第 {k} 段的帧不连续")
        if k == 0:
            lo = max(lo, int(np.searchsorted(tau, int(release_us), side="left")))
            if lo >= hi:
                raise ValueError(f"成员 {track.member_id} 释放时刻不在第 0 段内")
        out.append((lo, hi))
    return out


def verify_segments(scene, tracks, release_us, tasks, *, criteria=None, segment_config=None):
    cfg = criteria if criteria is not None else load_criteria()
    S = (segment_config if segment_config is not None else load_config("criteria_segment")).values
    geom = scene_geometry(scene)
    tasks = list(tasks)
    if [t.index for t in tasks] != list(range(len(tasks))):
        raise ValueError("tasks 的 index 须依次为 0..K-1")
    for t in tasks:
        if t.intent not in KINDS:
            raise ValueError(f"意图 {t.intent!r} 暂不支持（迂回判据在 ④ 定稿）")
        if t.intent == "intrusion" and t.index != len(tasks) - 1:
            raise ValueError("突入只能是最后一段")
    if set(tracks) != set(release_us):
        raise ValueError("tracks 与 release_us 的成员不一致")
    members = sorted(tracks)
    frames = {m: segment_frames(tracks[m], release_us[m], len(tasks)) for m in members}
    verdicts = []
    for task in tasks:
        final = task.index == len(tasks) - 1
        ti = geom.facility_ids.index(task.target_id) if task.target_id in geom.facility_ids else None
        if ti is None:
            raise ValueError(f"目标 {task.target_id!r} 不是场景中的设施")
        windows, conds, failures = {}, {}, []
        win_frames = {}
        for m in members:
            lo, hi = frames[m][task.index]
            tr = tracks[m]
            w = measure_member_window(
                geom, m, np.asarray(tr.tau_us)[lo:hi], np.asarray(tr.p)[lo:hi], np.asarray(tr.v)[lo:hi],
                kind=task.intent, target_id=task.target_id, settled=True,
                max_target_layer=S[f"max_target_layer_{task.intent}"], max_other_layer=S["max_other_facility_layer"],
                survey=task.survey if task.intent == "area_search" else None, criteria=cfg)
            lv = w.levels
            others = [j for j in range(lv.shape[1]) if j != ti]
            c = {"start_layers_within_limit": bool(lv[0].max() <= S["start_max_layer_any_facility"]),
                 "target_within_limit": bool(lv[:, ti].max() <= S[f"max_target_layer_{task.intent}"]),
                 "other_facilities_within_limit": bool(not others or lv[:, others].max() <= S["max_other_facility_layer"])}
            for key in _V07_KEYS[task.intent]:
                c[key] = w.conditions[key]
            if task.intent == "transit":
                c["started_outside_target_warning"] = bool(lv[0, ti] == 0)
                c["ended_outside_target_warning"] = bool(lv[-1, ti] == 0)
            if task.intent == "feint":
                c["ended_below_alert"] = bool(lv[-1, ti] <= S["feint_end_max_target_layer"])
            if task.intent != "close_observation":
                c["no_dwell_window"] = not w.dwell_anywhere["detected"]
            if final and task.intent != "intrusion":
                c["ended_outside_all_warning"] = bool(lv[-1].max() == 0)
            windows[m], conds[m], win_frames[m] = w, c, (lo, hi)
            failures += [(m, k, _CODES.get(k, SEMANTIC_FAILED)) for k, ok in c.items() if ok is not True]
        g = group_window([windows[m] for m in members], settled=True, criteria=cfg)
        gc = {}
        if task.intent == "area_search":
            gc["shared_coverage"] = g["conditions"]["shared_coverage"]
        failures += [("group", k, SEMANTIC_FAILED) for k, ok in gc.items() if ok is not True]
        failures = tuple(sorted(failures))
        verdicts.append(SegmentVerdict(
            index=task.index, intent=task.intent, target_id=task.target_id, final=final,
            window_frames=win_frames, member_conditions=conds, group_conditions=gc, failures=failures,
            codes=tuple(sorted({f[2] for f in failures})), passed=not failures, windows=windows, group=g))
    return verdicts
