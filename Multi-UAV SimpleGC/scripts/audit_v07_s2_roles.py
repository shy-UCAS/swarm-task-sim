"""Independent audit of S2 expansion role episodes (phase 1: transit task groups).

Imports nothing from task_v07: layers use original-contour GEOS distance or the
analytic circle; transit facts are recomputed with separate formulas from the
exported truth NPZ (checked row-for-row against truth.csv).
"""
from itertools import combinations
from pathlib import Path
import csv
import hashlib

import numpy as np

from scripts.audit_v07_s2_exact import _read, _signed_distance

LAYERS = (("warning", 1), ("alert", 2), ("protected", 3))
FLOAT_TOLERANCE = 1e-6   # labels round chord/azimuth/turn facts to 6 decimals


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


def audit_transit_episode(root):
    root = Path(root)
    scene, labels, task = (_read(root / n) for n in ("public_scene.json", "labels.json", "task.json"))
    with np.load(root / "truth_10hz.npz", allow_pickle=False) as data:
        ids = data["agent_ids"].tolist(); t = data["time_us"]; p = data["p"]; v = data["v"]
    with np.load(root / "frame_labels.npz", allow_pickle=False) as data:
        fids = data["facility_ids"].tolist(); stored = data["region_all_facilities"]
        target_stored = data["region_assigned_target"]; phase_stored = data["phase"]
        if data["agent_ids"].tolist() != ids or not np.array_equal(data["time_us"], t):
            raise ValueError("P0: frame labels and truth axes differ")
    columns = ("east_m", "north_m", "up_m", "ve_m_s", "vn_m_s", "vu_m_s")
    with (root / "truth.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != len(t) * len(ids):
        raise ValueError("P0: truth CSV row count")
    for count, row in enumerate(rows):
        k, i = divmod(count, len(ids))
        if row["agent_id"] != ids[i] or row["valid"] != "1" or float(row["t_s"]) != t[k] / 1e6:
            raise ValueError("P0: truth CSV time/ID mismatch")
        if not np.array_equal([float(row[c]) for c in columns], np.r_[p[k, i], v[k, i]]):
            raise ValueError("P0: truth CSV/NPZ state mismatch")
    xy = p[:, :, :2]
    expected = np.zeros_like(stored)
    for j, fid in enumerate(fids):
        facility = next(e for e in scene["entities"] if e["id"] == fid)
        distance = _signed_distance(facility["geometry"], xy)
        for name, code in LAYERS:
            zone = next(e for e in scene["entities"] if e.get("facility_id") == fid and e.get("layer") == name)
            expected[:, :, j][distance <= zone["offset_m"]] = code
    region_differences = int(np.count_nonzero(expected != stored))
    target_j = fids.index(task["target_id"])
    target_differences = int(np.count_nonzero(expected[:, :, target_j] != target_stored))
    center = _center(next(e for e in scene["entities"] if e["id"] == task["target_id"])["geometry"])
    criteria = task["transit"]
    errors, facts = [], {}
    for i, a in enumerate(ids):
        observed = labels["agents"][a]["observed"]; contribution = observed["contribution"]
        conditions = labels["agents"][a]["result"]["conditions"]
        for j, fid in enumerate(fids):
            for name, code in LAYERS:
                hits = np.flatnonzero(expected[:, i, j] >= code)
                saved = observed["regions_by_facility"][fid][name]
                if saved["first_entry_s"] != (float(t[hits[0]] / 1e6) if len(hits) else None) or saved["sample_count"] != len(hits):
                    errors.append({"agent_id": a, "facility_id": fid, "layer": name})
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
        distance = np.sqrt(np.sum((p[:, i] - np.asarray(ref["endpoint_enu_m"])) ** 2, axis=1))
        after = np.zeros(len(t), bool) if exit_s is None else t / 1e6 >= exit_s
        arrivals = np.flatnonzero((distance <= task["terminal_radius_m"]) & after)
        arrival = float(t[arrivals[0]] / 1e6) if len(arrivals) else None
        hold = _longest((distance <= task["terminal_radius_m"]) & (speed <= task["terminal_speed_m_s"]) & after)
        forbidden = np.zeros(len(t), bool)
        for fid, layer in task["exclusion_policy"][a].items():
            forbidden |= expected[:, i, fids.index(fid)] >= dict(LAYERS)[layer]
        core_s = None if first is None else float(t[first] / 1e6)
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
            if not (_close(value, independent[key]) if isinstance(value, float) or isinstance(independent[key], float)
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
    azimuths = [facts[a]["entry_azimuth_deg"] for a in ids]
    for a in ids:
        if not _close(group["observed"]["entry_azimuths_deg"][a], facts[a]["entry_azimuth_deg"]):
            errors.append({"agent_id": a, "field": "group_entry_azimuth"})
    if not np.allclose(group["observed"]["work_area_center_m"], center, rtol=0, atol=FLOAT_TOLERANCE):
        errors.append({"field": "work_area_center_m"})
    if task["approach_mode"] == "multi_direction" and all(x is not None for x in azimuths):
        ordered = sorted(x % 360 for x in azimuths)
        gaps = [b - a for a, b in zip(ordered, ordered[1:] + [ordered[0] + 360])]
        span = 360 - max(gaps)
        if group["result"]["conditions"].get("multi_direction_span") != (span >= 90):
            errors.append({"field": "multi_direction_span", "independent_span_deg": span})
        if not _close(group["observed"]["approach_span_deg"], span):
            errors.append({"field": "approach_span_deg", "label": group["observed"]["approach_span_deg"], "independent": span})
    minimum = min(float(np.sqrt(np.sum((p[:, i] - p[:, j]) ** 2, axis=1)).min()) for i, j in combinations(range(len(ids)), 2))
    if minimum != labels["cluster"]["observed"]["minimum_separation_m"]:
        errors.append({"field": "minimum_separation_m"})
    if labels["generation_quality"]["retained"] != (minimum >= 2):
        errors.append({"field": "separation_quality_policy"})
    status = "PASS" if not (region_differences or target_differences or errors) else "P0_STOP"
    return {"directory": str(root), "status": status, "frames": len(t), "agents": len(ids), "facilities": len(fids),
            "all_facility_frame_comparisons": int(expected.size),
            "assigned_target_frame_comparisons": int(target_stored.size),
            "region_difference_count": region_differences, "target_difference_count": target_differences,
            "event_or_metric_difference_count": len(errors), "event_or_metric_witnesses": errors[:20],
            "independent_transit_facts": facts, "float_tolerance": FLOAT_TOLERANCE,
            "method": "GEOS original contour / analytic circle; shoelace centroid; complex-exponential heading wrap",
            "truth_csv_sha256": hashlib.sha256((root / "truth.csv").read_bytes()).hexdigest()}


def audit_role_episode(root):
    task = _read(Path(root) / "task.json")
    if task.get("role") == "transit":
        return audit_transit_episode(root)
    raise ValueError(f"No independent role audit implemented for {task.get('role')}")
