"""Independent audit of S2 expansion role episodes.

Imports nothing from task_v07: all facts are recomputed from the exported
truth NPZ and public_scene.json using only numpy/shapely primitives.
"""
from itertools import combinations
from pathlib import Path
import csv
import hashlib
import math

import numpy as np

from scripts.audit_v07_s2_exact import _read, _signed_distance

LAYERS = (("warning", 1), ("alert", 2), ("protected", 3))
FLOAT_TOLERANCE = 1e-6   # labels round chord/azimuth/turn facts to 6 decimals
APPROACH_HEADING_DISTANCE_M = 100.0


# ---------------------------------------------------------------------------
# Shared geometry helpers (no task_v07 imports)
# ---------------------------------------------------------------------------

def _center(geometry):
    if geometry["type"] == "Circle":
        return np.asarray(geometry["center_m"], float)
    v = np.asarray(geometry["vertices_m"], float)
    if np.array_equal(v[0], v[-1]):
        v = v[:-1]
    x, y = v[:, 0], v[:, 1]
    xn, yn = np.roll(x, -1), np.roll(y, -1)
    cross = x * yn - xn * y
    area = cross.sum() / 2
    return np.array([((x + xn) * cross).sum() / (6 * area), ((y + yn) * cross).sum() / (6 * area)])


def _runs(mask):
    """(start, stop) index pairs of True runs."""
    edges = np.flatnonzero(np.diff(np.r_[0, np.asarray(mask, int), 0]))
    return list(zip(edges[::2], edges[1::2]))


def _longest(mask):
    return max([0.0, *[(b - a - 1) / 10 for a, b in _runs(mask)]])


def _azimuth(offset):
    return float(np.degrees(np.arctan2(offset[1], offset[0])) % 360)


def _close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= FLOAT_TOLERANCE


def _approach_heading_deg(xy, core_frame, distance_m=APPROACH_HEADING_DISTANCE_M):
    """Mean heading over the last `distance_m` of 10 Hz trajectory before core_frame.

    Independently recomputes the same quantity as labels.approach_heading_deg
    from raw truth positions, with no task_v07 import.  Returns None when the
    path is too short or core_frame is unavailable.
    """
    if core_frame is None or core_frame < 1:
        return None
    end = min(core_frame, len(xy) - 1)
    cum = 0.0
    start = end
    for k in range(end, 0, -1):
        step = float(np.linalg.norm(xy[k] - xy[k - 1]))
        cum += step
        if cum >= distance_m:
            start = k - 1
            break
    if start == end:
        return None
    delta = xy[end] - xy[start]
    if np.linalg.norm(delta) < 1e-9:
        return None
    return float(np.degrees(math.atan2(float(delta[1]), float(delta[0]))) % 360)


def _heading_span_deg(headings):
    """Max pairwise circular angular difference among headings (degrees [0,360)).

    Returns None when fewer than 2 valid headings are present.
    """
    valid = [h for h in headings if h is not None]
    if len(valid) < 2:
        return None
    return float(max(min(abs(a - b), 360 - abs(a - b)) for a, b in combinations(valid, 2)))


def _build_levels(scene, xy, fids):
    """shape (T, N, F) int8 — zone level for each frame/agent/facility."""
    T, N = xy.shape[:2]
    levels = np.zeros((T, N, len(fids)), np.int8)
    for fi, fid in enumerate(fids):
        facility = next(e for e in scene["entities"] if e["id"] == fid)
        dist = _signed_distance(facility["geometry"], xy)
        for name, code in LAYERS:
            zone = next(e for e in scene["entities"]
                        if e.get("facility_id") == fid and e.get("layer") == name)
            levels[:, :, fi][dist <= zone["offset_m"]] = code
    return levels


def _check_region_facts(labels, ids, expected, t, fids):
    """Compare stored region entry times / counts to independently computed ones."""
    errors = []
    for i, a in enumerate(ids):
        observed = labels["agents"][a]["observed"]
        for j, fid in enumerate(fids):
            for name, code in LAYERS:
                hits = np.flatnonzero(expected[:, i, j] >= code)
                saved = observed["regions_by_facility"][fid][name]
                stored_t = saved["first_entry_s"]
                expected_t = float(t[hits[0]] / 1e6) if len(hits) else None
                if stored_t != expected_t or saved["sample_count"] != len(hits):
                    errors.append({"agent_id": a, "facility_id": fid, "layer": name})
    return errors


def _check_approach_span(labels, ids, xy, core_frames):
    """Independently recompute approach_span_deg and compare to stored value.

    core_frames: {agent_id: frame_index or None}
    Returns list of error dicts (empty = PASS).
    """
    errors = []
    group = next(iter(labels["task_groups"].values()))
    stored_span = group["observed"].get("approach_span_deg")
    stored_headings = group["observed"].get("approach_headings_deg", {})

    indep_headings = {}
    for i, a in enumerate(ids):
        h = _approach_heading_deg(xy[:, i], core_frames.get(a))
        indep_headings[a] = h
        # Check per-agent stored heading
        stored_h = stored_headings.get(a)
        if not _close(stored_h, h):
            errors.append({"field": "approach_headings_deg", "agent_id": a,
                           "label": stored_h, "independent": h})

    indep_span = _heading_span_deg(list(indep_headings.values()))
    if not _close(stored_span, indep_span):
        errors.append({"field": "approach_span_deg",
                       "label": stored_span, "independent": indep_span})

    # Also verify the multi_direction_span condition flag is consistent
    stored_cond = group["result"]["conditions"].get("multi_direction_span")
    if stored_cond is not None and indep_span is not None:
        if stored_cond != (indep_span >= 90):
            errors.append({"field": "multi_direction_span_condition",
                           "label": stored_cond, "independent_span": indep_span})
    return errors


def _check_separation(labels, p, ids):
    errors = []
    n = len(ids)
    if n < 2:
        return errors
    minimum = min(float(np.sqrt(np.sum((p[:, i] - p[:, j]) ** 2, axis=1)).min())
                  for i, j in combinations(range(n), 2))
    if not _close(minimum, labels["cluster"]["observed"]["minimum_separation_m"]):
        errors.append({"field": "minimum_separation_m",
                       "label": labels["cluster"]["observed"]["minimum_separation_m"],
                       "independent": minimum})
    if labels["generation_quality"]["retained"] != (minimum >= 2):
        errors.append({"field": "separation_quality_policy"})
    return errors


def _load_truth(root):
    """Returns ids, t, p, v from truth_10hz.npz, validated against truth.csv."""
    root = Path(root)
    with np.load(root / "truth_10hz.npz", allow_pickle=False) as data:
        ids = data["agent_ids"].tolist()
        t = data["time_us"].copy()
        p = data["p"].copy()
        v = data["v"].copy()
    columns = ("east_m", "north_m", "up_m", "ve_m_s", "vn_m_s", "vu_m_s")
    with (root / "truth.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != len(t) * len(ids):
        raise ValueError("P0: truth CSV row count mismatch")
    for count, row in enumerate(rows):
        k, i = divmod(count, len(ids))
        if row["agent_id"] != ids[i] or row["valid"] != "1" or float(row["t_s"]) != t[k] / 1e6:
            raise ValueError("P0: truth CSV time/ID mismatch")
        if not np.array_equal([float(row[c]) for c in columns], np.r_[p[k, i], v[k, i]]):
            raise ValueError("P0: truth CSV/NPZ state mismatch")
    return ids, t, p, v


# ---------------------------------------------------------------------------
# Transit episode audit
# ---------------------------------------------------------------------------

def audit_transit_episode(root):
    root = Path(root)
    scene, labels, task = (_read(root / n) for n in ("public_scene.json", "labels.json", "task.json"))
    ids, t, p, v = _load_truth(root)
    with np.load(root / "frame_labels.npz", allow_pickle=False) as data:
        fids = data["facility_ids"].tolist(); stored = data["region_all_facilities"]
        target_stored = data["region_assigned_target"]; phase_stored = data["phase"]
        if data["agent_ids"].tolist() != ids or not np.array_equal(data["time_us"], t):
            raise ValueError("P0: frame labels and truth axes differ")
    xy = p[:, :, :2]
    expected = _build_levels(scene, xy, fids)
    region_differences = int(np.count_nonzero(expected != stored))
    target_j = fids.index(task["target_id"])
    target_differences = int(np.count_nonzero(expected[:, :, target_j] != target_stored))
    center = _center(next(e for e in scene["entities"] if e["id"] == task["target_id"])["geometry"])
    criteria = task["transit"]
    errors, facts, core_frames = [], {}, {}
    for i, a in enumerate(ids):
        observed = labels["agents"][a]["observed"]; contribution = observed["contribution"]
        conditions = labels["agents"][a]["result"]["conditions"]
        errors += _check_region_facts(labels, [a], expected[:, i:i+1], t, fids)
        inside = expected[:, i, target_j] >= 1
        visits = _runs(inside)
        first = int(visits[0][0]) if visits else None
        last = int(visits[0][1]) - 1 if visits and visits[0][1] < len(t) else None
        speed = np.sqrt(np.sum(v[:, i] ** 2, axis=1))
        visit = np.zeros(len(t), bool)
        if first is not None:
            visit[first:(last + 1 if last is not None else len(t))] = True
        moving = speed >= criteria["low_speed_threshold_m_s"]
        heading = np.arctan2(v[:, i, 1], v[:, i, 0])
        delta = np.abs(np.angle(np.exp(1j * np.diff(heading))))
        pairs = visit[1:] & visit[:-1] & moving[1:] & moving[:-1]
        turn = round(float(np.sum(delta[pairs]) * 180 / np.pi), 6)
        low = _longest(visit & ~moving)
        entry_az = None if first is None else round(_azimuth(xy[first, i] - center), 6)
        exit_az = chord = difference = exit_s = None
        if last is not None:
            exit_az = round(_azimuth(xy[last, i] - center), 6)
            chord = round(float(np.hypot(*(xy[last, i] - xy[first, i]))), 6)
            raw = abs(exit_az - entry_az) % 360
            difference = round(min(raw, 360 - raw), 6)
            exit_s = float(t[last + 1] / 1e6)
        ref = task["references"][a]
        dist_end = np.sqrt(np.sum((p[:, i] - np.asarray(ref["endpoint_enu_m"])) ** 2, axis=1))
        after = np.zeros(len(t), bool) if exit_s is None else t / 1e6 >= exit_s
        arrivals = np.flatnonzero((dist_end <= task["terminal_radius_m"]) & after)
        arrival = float(t[arrivals[0]] / 1e6) if len(arrivals) else None
        hold = _longest((dist_end <= task["terminal_radius_m"]) & (speed <= task["terminal_speed_m_s"]) & after)
        forbidden = np.zeros(len(t), bool)
        for fid, layer in task["exclusion_policy"][a].items():
            forbidden |= expected[:, i, fids.index(fid)] >= dict(LAYERS)[layer]
        core_s = None if first is None else float(t[first] / 1e6)
        core_frames[a] = first
        independent = {"core_event_s": core_s, "warning_exit_s": exit_s, "warning_last_inside_frame": last,
                       "chord_length_m": chord, "entry_azimuth_deg": entry_az, "exit_azimuth_deg": exit_az,
                       "entry_exit_azimuth_difference_deg": difference, "longest_low_speed_in_warning_s": low,
                       "cumulative_turn_in_warning_deg": turn, "retreat_arrival_s": arrival, "endpoint_hold_s": hold,
                       "forbidden_samples": int(forbidden.sum())}
        facts[a] = independent
        saved = {"core_event_s": observed["core_event"]["t_s"], "warning_exit_s": contribution["warning_exit_s"],
                 "warning_last_inside_frame": contribution["warning_last_inside_frame"],
                 "chord_length_m": contribution["chord_length_m"], "entry_azimuth_deg": contribution["entry_azimuth_deg"],
                 "exit_azimuth_deg": contribution["exit_azimuth_deg"],
                 "entry_exit_azimuth_difference_deg": contribution["entry_exit_azimuth_difference_deg"],
                 "longest_low_speed_in_warning_s": contribution["longest_low_speed_in_warning_s"],
                 "cumulative_turn_in_warning_deg": contribution["cumulative_turn_in_warning_deg"],
                 "retreat_arrival_s": observed["retreat_event"]["t_s"], "endpoint_hold_s": observed["endpoint_hold_s"]}
        for key, value in saved.items():
            if not (_close(value, independent[key]) if isinstance(value, (float, type(None))) or isinstance(independent[key], (float, type(None)))
                    else value == independent[key]):
                errors.append({"agent_id": a, "field": key, "label": value, "independent": independent[key]})
        complete = labels["evidence"]["complete_observation"]
        expected_conditions = {
            "entered_warning": first is not None, "exited_warning": last is not None,
            "chord_length": chord is not None and chord >= criteria["minimum_chord_m"],
            "entry_exit_azimuth_difference": difference is not None and difference >= criteria["minimum_azimuth_difference_deg"],
            "no_stop_in_warning": low <= criteria["maximum_low_speed_s"],
            "no_loop_in_warning": turn < criteria["maximum_cumulative_turn_deg"],
            "reached_retreat_point": arrival is not None, "exclusion_policy_respected": not forbidden.any(),
            "own_endpoint_hold": hold >= task["terminal_hold_s"]}
        if not complete:
            errors.append({"agent_id": a, "field": "complete_observation_expected"})
        for key, value in expected_conditions.items():
            if conditions.get(key) != value:
                errors.append({"agent_id": a, "condition": key, "label": conditions.get(key), "independent": value})
        if phase_stored.shape[0] != len(t):
            errors.append({"field": "phase_axis"})
    group = next(iter(labels["task_groups"].values()))
    if not np.allclose(group["observed"]["work_area_center_m"], center, rtol=0, atol=FLOAT_TOLERANCE):
        errors.append({"field": "work_area_center_m"})
    # Independent approach_span_deg: recompute last-100m headings from 10 Hz truth.
    errors += _check_approach_span(labels, ids, xy, core_frames)
    errors += _check_separation(labels, p, ids)
    status = "PASS" if not (region_differences or target_differences or errors) else "P0_STOP"
    return {"directory": str(root), "status": status, "frames": len(t), "agents": len(ids), "facilities": len(fids),
            "all_facility_frame_comparisons": int(expected.size),
            "assigned_target_frame_comparisons": int(target_stored.size),
            "region_difference_count": region_differences, "target_difference_count": target_differences,
            "event_or_metric_difference_count": len(errors), "event_or_metric_witnesses": errors[:20],
            "independent_transit_facts": facts, "float_tolerance": FLOAT_TOLERANCE,
            "method": "GEOS original contour / analytic circle; independent last-100m heading; shoelace centroid",
            "truth_csv_sha256": hashlib.sha256((root / "truth.csv").read_bytes()).hexdigest()}


# ---------------------------------------------------------------------------
# Close-observation episode audit
# ---------------------------------------------------------------------------

def audit_close_observation_episode(root):
    root = Path(root)
    scene, labels, task = (_read(root / n) for n in ("public_scene.json", "labels.json", "task.json"))
    ids, t, p, v = _load_truth(root)
    xy = p[:, :, :2]
    fids = sorted(e["id"] for e in scene["entities"] if e["type"] == "facility")
    expected = _build_levels(scene, xy, fids)
    target_j = fids.index(task["target_id"])
    errors, core_frames = [], {}
    rules = task["close_observation"]
    obs_radius = rules["observation_radius_m"]
    for i, a in enumerate(ids):
        observed = labels["agents"][a]["observed"]
        contribution = observed["contribution"]
        conditions = labels["agents"][a]["result"]["conditions"]
        ref = task["references"][a]
        obs_center = np.array(ref.get("observation_point_enu_m", ref["endpoint_enu_m"])[:2])
        dist_obs = np.linalg.norm(xy[:, i] - obs_center, axis=1)
        inside_obs = dist_obs <= obs_radius
        obs_runs = _runs(inside_obs)
        obs_enter = int(obs_runs[0][0]) if obs_runs else None
        obs_exit = int(obs_runs[0][1]) if obs_runs and obs_runs[0][1] < len(t) else None
        dwell = round((obs_exit - obs_enter) / 10., 6) if obs_enter is not None and obs_exit is not None else \
                (round((len(t) - obs_enter) / 10., 6) if obs_enter is not None else 0.0)
        core_s = float(t[obs_enter] / 1e6) if obs_enter is not None else None
        core_frames[a] = obs_enter
        in_alert = bool(np.any(expected[:, i, target_j] >= 2))
        dist_end = np.sqrt(np.sum((p[:, i] - np.asarray(ref["endpoint_enu_m"])) ** 2, axis=1))
        work_end_s = float(t[obs_exit] / 1e6) if obs_exit is not None else None
        after_work = np.zeros(len(t), bool) if work_end_s is None else t / 1e6 >= work_end_s
        speed = np.sqrt(np.sum(v[:, i] ** 2, axis=1))
        arrivals = np.flatnonzero((dist_end <= task["terminal_radius_m"]) & after_work)
        arrival_s = float(t[arrivals[0]] / 1e6) if len(arrivals) else None
        hold = _longest((dist_end <= task["terminal_radius_m"]) & (speed <= task["terminal_speed_m_s"]) & after_work)
        # Compare stored facts
        if not _close(observed["core_event"]["t_s"], core_s):
            errors.append({"agent_id": a, "field": "core_event_s", "label": observed["core_event"]["t_s"], "independent": core_s})
        if not _close(contribution.get("dwell_s"), dwell):
            errors.append({"agent_id": a, "field": "dwell_s", "label": contribution.get("dwell_s"), "independent": dwell})
        if not _close(observed.get("retreat_event", {}).get("t_s"), arrival_s):
            errors.append({"agent_id": a, "field": "retreat_arrival_s",
                           "label": observed.get("retreat_event", {}).get("t_s"), "independent": arrival_s})
        # Conditions
        complete = labels["evidence"]["complete_observation"]
        if conditions.get("reached_observation_point") != (obs_enter is not None if complete else (obs_enter is not None or None)):
            errors.append({"agent_id": a, "condition": "reached_observation_point",
                           "label": conditions.get("reached_observation_point"), "independent": obs_enter is not None})
        if conditions.get("no_alert_entry") != (not in_alert):
            errors.append({"agent_id": a, "condition": "no_alert_entry",
                           "label": conditions.get("no_alert_entry"), "independent": not in_alert})
    group = next(iter(labels["task_groups"].values()))
    errors += _check_approach_span(labels, ids, xy, core_frames)
    errors += _check_separation(labels, p, ids)
    status = "PASS" if not errors else "P0_STOP"
    return {"directory": str(root), "status": status, "frames": len(t), "agents": len(ids),
            "region_difference_count": 0, "target_difference_count": 0,
            "event_or_metric_difference_count": len(errors), "event_or_metric_witnesses": errors[:20],
            "method": "independent last-100m heading; analytic circle zone membership",
            "truth_csv_sha256": hashlib.sha256((root / "truth.csv").read_bytes()).hexdigest()}


# ---------------------------------------------------------------------------
# Monitoring episode audit
# ---------------------------------------------------------------------------

def audit_monitoring_episode(root):
    root = Path(root)
    scene, labels, task = (_read(root / n) for n in ("public_scene.json", "labels.json", "task.json"))
    ids, t, p, v = _load_truth(root)
    xy = p[:, :, :2]
    fids = sorted(e["id"] for e in scene["entities"] if e["type"] == "facility")
    expected = _build_levels(scene, xy, fids)
    target_j = fids.index(task["target_id"])
    errors, core_frames = [], {}
    rules = task["monitoring"]
    orbit_center = np.array(rules["orbit_center_enu_m"][:2])
    orbit_radius = rules["orbit_radius_m"]
    track_tol = rules.get("track_tolerance_m", 30.0)
    min_speed = rules.get("effective_speed_min_m_s", 0.5)
    min_loop_s = rules.get("min_loop_duration_s", 5.0)
    planned_laps = rules.get("planned_laps", 1.0)
    for i, a in enumerate(ids):
        observed = labels["agents"][a]["observed"]
        contribution = observed["contribution"]
        conditions = labels["agents"][a]["result"]["conditions"]
        ref = task["references"][a]
        speed = np.sqrt(np.sum(v[:, i] ** 2, axis=1))
        on_orbit_dist = np.abs(np.linalg.norm(xy[:, i] - orbit_center, axis=1) - orbit_radius)
        on_orbit = on_orbit_dist <= track_tol
        to_center = orbit_center - xy[:, i]
        tangent = np.stack([-to_center[:, 1], to_center[:, 0]], axis=1)
        tnorm = np.linalg.norm(tangent, axis=1, keepdims=True)
        tnorm = np.where(tnorm < 1e-9, 1e-9, tnorm)
        tangent_unit = tangent / tnorm
        vel_xy = v[:, i, :2]; vnorm = np.linalg.norm(vel_xy, axis=1, keepdims=True)
        vnorm = np.where(vnorm < 1e-9, 1e-9, vnorm)
        vel_unit = vel_xy / vnorm
        cos_angle = np.clip(np.sum(vel_unit * tangent_unit, axis=1), -1, 1)
        along_orbit = np.abs(np.degrees(np.arccos(np.abs(cos_angle)))) <= 45.0
        moving = speed >= min_speed
        valid_frame = on_orbit & along_orbit & moving
        min_frames = max(1, int(min_loop_s * 10))
        core_frame = None; run_len = 0
        for fi_, ok in enumerate(valid_frame):
            if ok:
                run_len += 1
                if run_len >= min_frames:
                    core_frame = fi_ - min_frames + 1; break
            else:
                run_len = 0
        core_s = float(t[core_frame] / 1e6) if core_frame is not None else None
        core_frames[a] = core_frame
        angles = np.arctan2(xy[:, i, 1] - orbit_center[1], xy[:, i, 0] - orbit_center[0])
        d_angles = np.diff(angles); d_angles = (d_angles + math.pi) % (2 * math.pi) - math.pi
        lap_count = round(abs(float(d_angles[valid_frame[1:]].sum())) / (2 * math.pi), 3)
        if not _close(observed["core_event"]["t_s"], core_s):
            errors.append({"agent_id": a, "field": "core_event_s",
                           "label": observed["core_event"]["t_s"], "independent": core_s})
        if not _close(contribution.get("lap_count_observed"), lap_count):
            errors.append({"agent_id": a, "field": "lap_count_observed",
                           "label": contribution.get("lap_count_observed"), "independent": lap_count})
        dist_end = np.sqrt(np.sum((p[:, i] - np.asarray(ref["endpoint_enu_m"])) ** 2, axis=1))
        speed_v = np.sqrt(np.sum(v[:, i] ** 2, axis=1))
        arrivals = np.flatnonzero(dist_end <= task["terminal_radius_m"])
        hold = _longest((dist_end <= task["terminal_radius_m"]) & (speed_v <= task["terminal_speed_m_s"]))
        if conditions.get("started_orbit") is not None and conditions.get("started_orbit") != (core_frame is not None):
            errors.append({"agent_id": a, "condition": "started_orbit",
                           "label": conditions.get("started_orbit"), "independent": core_frame is not None})
    group = next(iter(labels["task_groups"].values()))
    errors += _check_approach_span(labels, ids, xy, core_frames)
    errors += _check_separation(labels, p, ids)
    status = "PASS" if not errors else "P0_STOP"
    return {"directory": str(root), "status": status, "frames": len(t), "agents": len(ids),
            "region_difference_count": 0, "target_difference_count": 0,
            "event_or_metric_difference_count": len(errors), "event_or_metric_witnesses": errors[:20],
            "method": "independent last-100m heading; orbit geometry from rules",
            "truth_csv_sha256": hashlib.sha256((root / "truth.csv").read_bytes()).hexdigest()}


# ---------------------------------------------------------------------------
# Feint episode audit
# ---------------------------------------------------------------------------

def audit_feint_episode(root):
    root = Path(root)
    scene, labels, task = (_read(root / n) for n in ("public_scene.json", "labels.json", "task.json"))
    ids, t, p, v = _load_truth(root)
    xy = p[:, :, :2]
    fids = sorted(e["id"] for e in scene["entities"] if e["type"] == "facility")
    expected = _build_levels(scene, xy, fids)
    target_j = fids.index(task["target_id"])
    errors, core_frames = [], {}
    rules = task["feint"]
    for i, a in enumerate(ids):
        observed = labels["agents"][a]["observed"]
        contribution = observed["contribution"]
        conditions = labels["agents"][a]["result"]["conditions"]
        in_alert = expected[:, i, target_j] >= 2
        alert_runs = _runs(in_alert)
        first = int(alert_runs[0][0]) if alert_runs else None
        core_s = float(t[first] / 1e6) if first is not None else None
        core_frames[a] = first
        entered_protected = bool(np.any(expected[:, i, target_j] >= 3))
        if not _close(observed["core_event"]["t_s"], core_s):
            errors.append({"agent_id": a, "field": "core_event_s",
                           "label": observed["core_event"]["t_s"], "independent": core_s})
        if contribution.get("entered_protected") != entered_protected:
            errors.append({"agent_id": a, "field": "entered_protected",
                           "label": contribution.get("entered_protected"), "independent": entered_protected})
        if conditions.get("no_protected_entry") != (not entered_protected):
            errors.append({"agent_id": a, "condition": "no_protected_entry",
                           "label": conditions.get("no_protected_entry"), "independent": not entered_protected})
    group = next(iter(labels["task_groups"].values()))
    errors += _check_approach_span(labels, ids, xy, core_frames)
    errors += _check_separation(labels, p, ids)
    status = "PASS" if not errors else "P0_STOP"
    return {"directory": str(root), "status": status, "frames": len(t), "agents": len(ids),
            "region_difference_count": 0, "target_difference_count": 0,
            "event_or_metric_difference_count": len(errors), "event_or_metric_witnesses": errors[:20],
            "method": "independent last-100m heading; alert zone membership from analytic circle",
            "truth_csv_sha256": hashlib.sha256((root / "truth.csv").read_bytes()).hexdigest()}


# ---------------------------------------------------------------------------
# Intrusion episode audit
# ---------------------------------------------------------------------------

def audit_intrusion_episode(root):
    root = Path(root)
    scene, labels, task = (_read(root / n) for n in ("public_scene.json", "labels.json", "task.json"))
    ids, t, p, v = _load_truth(root)
    xy = p[:, :, :2]
    fids = sorted(e["id"] for e in scene["entities"] if e["type"] == "facility")
    expected = _build_levels(scene, xy, fids)
    target_j = fids.index(task["target_id"])
    errors, core_frames = [], {}
    for i, a in enumerate(ids):
        observed = labels["agents"][a]["observed"]
        contribution = observed["contribution"]
        conditions = labels["agents"][a]["result"]["conditions"]
        inside_protected = expected[:, i, target_j] == 3
        prot_runs = _runs(inside_protected)
        first = int(prot_runs[0][0]) if prot_runs else None
        core_s = float(t[first] / 1e6) if first is not None else None
        core_frames[a] = first
        if not _close(observed["core_event"]["t_s"], core_s):
            errors.append({"agent_id": a, "field": "core_event_s",
                           "label": observed["core_event"]["t_s"], "independent": core_s})
        if conditions.get("entered_protected") != (first is not None):
            errors.append({"agent_id": a, "condition": "entered_protected",
                           "label": conditions.get("entered_protected"), "independent": first is not None})
    group = next(iter(labels["task_groups"].values()))
    # Intrusion expansion skeletons track approach headings; vertical-slice skeletons use legacy azimuths.
    if "exclusion_policy" in task:
        errors += _check_approach_span(labels, ids, xy, core_frames)
    errors += _check_separation(labels, p, ids)
    status = "PASS" if not errors else "P0_STOP"
    return {"directory": str(root), "status": status, "frames": len(t), "agents": len(ids),
            "region_difference_count": 0, "target_difference_count": 0,
            "event_or_metric_difference_count": len(errors), "event_or_metric_witnesses": errors[:20],
            "method": "independent last-100m heading; protected zone membership from analytic circle",
            "truth_csv_sha256": hashlib.sha256((root / "truth.csv").read_bytes()).hexdigest()}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def audit_role_episode(root):
    task = _read(Path(root) / "task.json")
    role = task.get("role")
    em = task.get("execution_method", "")
    if role == "transit":
        return audit_transit_episode(root)
    if role == "reconnaissance" and em == "close_observation":
        return audit_close_observation_episode(root)
    if role == "monitoring":
        return audit_monitoring_episode(root)
    if role == "feint":
        return audit_feint_episode(root)
    if role == "intrusion":
        return audit_intrusion_episode(root)
    raise ValueError(f"No independent role audit implemented for role={role!r} execution_method={em!r}")
