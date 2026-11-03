"""窗口版判据（V8-02 r4 9.1；V8-11 第 2 部分）。

在调用方切好的任意一段连续 10 Hz 帧（窗口）上，复用 v0.7 冻结检测器计算原子判据。
各条件的计算与 task_v07/criteria_labels.py:measure_criteria（冻结 641a9b3）逐行对应，
差别只有三处：不要求时间从 0 开始；complete 改由调用方给出的 settled 决定；
禁入层上限由调用方给出。帧号为窗口内帧号（首帧为 0），时刻为 time_us / 1e6。
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np

from scene_v07.geometry import center_of
from task_v07.criteria import load_criteria
from task_v07.detectors import coverage, dwell, revisit, runs, work_mask
from task_v07.geometry import geometry_facts
from task_v07.labels import approach_heading_deg, bounded, event, measurable, observed_conditions_result

KINDS = ("transit", "area_search", "close_observation", "monitoring", "feint", "intrusion")
FRAME_US = 100_000
_LAYERS = (("warning", 1), ("alert", 2), ("protected", 3))


@dataclass(frozen=True)
class SceneGeometry:
    facility_ids: tuple
    facilities: tuple
    layer_offsets: tuple
    centers: tuple
    obstacles: tuple
    world: dict


@dataclass(frozen=True)
class MemberWindow:
    member_id: str
    kind: str
    target_id: str
    settled: bool
    time_us: np.ndarray
    levels: np.ndarray
    target_signed_m: np.ndarray
    obstacle: np.ndarray
    outside_world: np.ndarray
    conditions: dict
    status: str
    core_event: dict
    dwell: dict
    revisit: dict
    observation_dwell: Optional[dict]
    coverage: Optional[dict]
    work_end_s: Optional[float]
    regions_by_facility: dict
    approach_heading_deg: Optional[float]
    dwell_anywhere: dict


def scene_geometry(scene) -> SceneGeometry:
    facilities = sorted((e for e in scene["entities"] if e["type"] == "facility"), key=lambda e: e["id"])
    offsets = []
    for f in facilities:
        layer = {e["layer"]: e["offset_m"] for e in scene["entities"] if e.get("facility_id") == f["id"]}
        offsets.append(layer)
    return SceneGeometry(
        facility_ids=tuple(f["id"] for f in facilities),
        facilities=tuple(f["geometry"] for f in facilities),
        layer_offsets=tuple(offsets),
        centers=tuple(np.asarray(center_of(f["geometry"]), dtype=float) for f in facilities),
        obstacles=tuple(e["geometry"] for e in scene["entities"] if e["type"] == "hard_constraint_obstacle"),
        world=scene["world"]["geometry"],
    )


def _check_window(time_us, p, v):
    t = np.asarray(time_us)
    if t.ndim != 1 or len(t) < 1 or not np.issubdtype(t.dtype, np.integer):
        raise ValueError("time_us 须为非空一维整数数组")
    if len(t) > 1 and np.any(np.diff(t) != FRAME_US):
        raise ValueError("time_us 须为 10 Hz 等间隔（相邻差 100000 µs）")
    p = np.asarray(p, dtype=float)
    v = np.asarray(v, dtype=float)
    if p.shape != (len(t), 3) or v.shape != (len(t), 3):
        raise ValueError("p、v 形状须为 (T, 3)")
    if not np.isfinite(p).all() or not np.isfinite(v).all():
        raise ValueError("p、v 含非有限值")
    return t, p, v


def measure_member_window(geom, member_id, time_us, p, v, *, kind, target_id, settled,
                          max_target_layer, max_other_layer, survey=None, criteria=None) -> MemberWindow:
    if kind not in KINDS:
        raise ValueError(f"kind {kind!r} 不在 {KINDS} 中")
    if target_id not in geom.facility_ids:
        raise ValueError(f"目标 {target_id!r} 不是场景中的设施")
    if (kind == "area_search") != (survey is not None):
        raise ValueError("survey 只用于且必须用于 area_search")
    t, p, v = _check_window(time_us, p, v)
    cfg = criteria if criteria is not None else load_criteria()
    xy = p[:, :2]
    speed = np.linalg.norm(v, axis=1)
    n = len(t)
    levels = np.zeros((n, len(geom.facility_ids)), np.int8)
    signed = []
    for j, g in enumerate(geom.facilities):
        facts = geometry_facts(g, xy, layer_offsets=geom.layer_offsets[j])
        levels[:, j] = facts["layer"]
        signed.append(facts["signed_distance_m"])
    obstacle = np.zeros(n, bool)
    for g in geom.obstacles:
        obstacle |= geometry_facts(g, xy)["inside"]
    outside = ~geometry_facts(geom.world, xy)["inside"]
    ti = geom.facility_ids.index(target_id)
    tl = levels[:, ti]
    distance = signed[ti]
    center = geom.centers[ti]

    work = work_mask(tl)
    dwelling = dwell(xy, t, work, cfg)
    observation = dwell(xy, t, tl == 1, cfg) if kind == "close_observation" else None
    revisiting = revisit(xy, v, t, tl, work, center, cfg)
    warning = event(tl >= 1, t, "enter_warning_zone")
    heading = approach_heading_deg(xy, warning["frame_index"], cfg["approach"]["heading_distance_m"])
    cov = None
    if kind == "transit":
        core = warning
        visits = runs(tl >= 1)
        checks = {"entered_warning": measurable(bool(visits), settled),
                  "single_warning_visit": False if len(visits) > 1 else measurable(len(visits) == 1, settled),
                  "no_dwell": bounded(dwelling["detected"], settled),
                  "no_revisit": bounded(revisiting["detected"], settled)}
    elif kind == "area_search":
        cov = coverage(xy, speed, tl, obstacle, survey, cfg)
        effective = cov["effective_mask"]
        core = event(effective, t, "scan_start")
        checks = {"effective_observation": measurable(bool(effective.any()), settled),
                  "no_revisit": bounded(revisiting["detected"], settled)}
    elif kind == "close_observation":
        mask = np.zeros(n, bool)
        if observation["detected"]:
            mask[observation["frame_index"]] = True
        core = event(mask, t, "observation_point_arrival")
        checks = {"observation_dwell": measurable(observation["detected"], settled),
                  "no_revisit": bounded(revisiting["detected"], settled)}
    elif kind == "monitoring":
        core = warning
        checks = {"patrol_revisit": measurable(revisiting["detected"], settled)}
    elif kind == "feint":
        core = event(tl >= 2, t, "enter_alert_zone")
        visits = runs(tl >= 2)
        checks = {"entered_alert": measurable(bool((tl == 2).any()), settled),
                  "single_alert_visit": False if len(visits) > 1 else measurable(len(visits) == 1, settled)}
    else:
        core = event(tl == 3, t, "enter_protected_zone")
        checks = {"entered_protected": measurable(bool((tl == 3).any()), settled),
                  "near_facility_contour": measurable(
                      float(distance.min()) <= cfg["roles"]["intrusion"]["max_contour_distance_m"], settled)}
    if kind != "intrusion":
        checks["ended_outside_warning"] = bool(tl[-1] == 0) if settled else None
    if kind == "close_observation":
        core["t_confirm"] = observation["t_confirm"]
        core["confirm_frame_index"] = observation["confirm_frame_index"]
    else:
        core["t_confirm"] = core["t_s"]
        core["confirm_frame_index"] = core["frame_index"]
    forbidden = tl > max_target_layer
    for j in range(len(geom.facility_ids)):
        if j != ti:
            forbidden |= levels[:, j] > max_other_layer
    checks["exclusion_policy_respected"] = bounded(bool(forbidden.any()), settled)

    regions = {}
    for j, fid in enumerate(geom.facility_ids):
        regions[fid] = {}
        for name, code in _LAYERS:
            hit = event(levels[:, j] >= code, t, "enter_" + name + "_zone")
            regions[fid][name] = {"entered_observed": hit["t_s"] is not None,
                                  "first_entry_s": hit["t_s"], "sample_count": int((levels[:, j] >= code).sum())}
    inside_frames = np.flatnonzero(tl >= 1)
    end = (int(inside_frames[-1]) + 1 if len(inside_frames) and inside_frames[-1] < n - 1 else None)
    work_end = None if end is None else float(t[end] / 1e6)

    return MemberWindow(
        member_id=member_id, kind=kind, target_id=target_id, settled=bool(settled), time_us=t,
        levels=levels, target_signed_m=distance, obstacle=obstacle, outside_world=outside,
        conditions=checks, status=observed_conditions_result(checks, settled), core_event=core,
        dwell=dwelling, revisit=revisiting, observation_dwell=observation, coverage=cov,
        work_end_s=work_end, regions_by_facility=regions, approach_heading_deg=heading,
        dwell_anywhere=dwell(xy, t, np.ones(n, bool), cfg),
    )


def group_window(members, *, settled, criteria=None) -> dict:
    if not members:
        raise ValueError("members 为空")
    kinds = {m.kind for m in members}
    if len(kinds) != 1:
        raise ValueError("同一编组的成员窗口须为同一意图")
    cfg = criteria if criteria is not None else load_criteria()
    statuses = [m.status for m in members]
    checks = {"member_contributions_complete":
              False if "failure" in statuses else None if "unknown" in statuses else True}
    shared = None
    if kinds == {"area_search"}:
        union = np.logical_or.reduce([m.coverage["covered_mask"] for m in members])
        required = cfg["detectors"]["coverage"]["min_group_fraction"]
        shared = {"grid_point_count": len(union), "covered_grid_point_count": int(union.sum()),
                  "coverage_fraction": float(union.mean()) if len(union) else 0.,
                  "required_fraction": required}
        checks["shared_coverage"] = measurable(shared["coverage_fraction"] >= required, settled)
    return {"conditions": checks, "status": observed_conditions_result(checks, settled), "shared_coverage": shared}
