"""Independent criteria-r1 detectors. No task_v07 imports or callbacks."""
import json
from pathlib import Path
import numpy as np
from scripts.audit_v07_s2_exact import _inside


def configuration():
    return json.loads((Path(__file__).resolve().parents[1] / "configs/criteria/criteria_v07_r1.json").read_text(encoding="utf-8"))


def circular_extent(points, center):
    if not len(points): return 0.
    relative = points - center
    bearings = np.sort(np.degrees(np.arctan2(relative[:, 1], relative[:, 0])) % 360)
    gaps = np.diff(np.r_[bearings, bearings[0] + 360])
    return float(360 - max(gaps))


def independent_dwell(points, ticks, selected):
    rule = configuration()["detectors"]["dwell"]
    count = int(round(rule["window_s"] * 10)) + 1
    qualifying = []
    if len(points) >= count:
        allowed = np.convolve(np.asarray(selected, int), np.ones(count, int), mode="valid") == count
        endpoints = np.sum((points[count - 1:] - points[:len(points) - count + 1]) ** 2, axis=1)
        for begin in np.flatnonzero(allowed & (endpoints <= rule["max_start_end_m"] ** 2)):
            sample = points[begin:begin + count]
            mean = np.mean(sample, axis=0)
            if np.all(np.linalg.norm(sample - mean, axis=1) <= rule["radius_m"]):
                qualifying.append(int(begin))
    edges = np.zeros(max(0, len(points) - 1), bool)
    for begin in qualifying: edges[begin:begin + count - 1] = True
    transitions = np.flatnonzero(np.diff(np.r_[0, edges.astype(int), 0]))
    intervals = [[int(b), int(e)] for b, e in zip(transitions[::2], transitions[1::2])]
    first = qualifying[0] if qualifying else None
    end = None if first is None else first + count - 1
    return {"detected": first is not None, "frame_index": first, "confirm_frame_index": end,
            "t_s": None if first is None else float(ticks[first] / 1e6),
            "t_confirm": None if end is None else float(ticks[end] / 1e6),
            "total_duration_s": float(np.diff(ticks)[edges].sum()) / 1e6,
            "union_frame_intervals": intervals}


def independent_revisit(points, velocities, ticks, layers, selected, center):
    rule = configuration()["detectors"]["revisit"]
    missing = dict(detected=False, frame_index=None, confirm_frame_index=None, t1=None, t2=None,
                   t_confirm=None, distance_m=None, departure_m=None, heading_difference_deg=None, azimuth_coverage_deg=None)
    speeds = np.sqrt(np.sum(velocities * velocities, axis=1))
    ground = np.sqrt(np.sum(velocities[:, :2] ** 2, axis=1))
    candidates = np.flatnonzero(selected & (layers == 1) & (speeds >= rule["min_speed_m_s"]) & (ground > 0))
    if not len(candidates) or circular_extent(points[candidates[0]:candidates[-1] + 1], center) < rule["min_azimuth_coverage_deg"]:
        return missing
    cell_index = np.floor(points[candidates] / rule["radius_m"]).astype(int)
    spatial = {}
    for i, key in zip(candidates, cell_index): spatial.setdefault(tuple(key), []).append(int(i))
    spatial = {key: np.asarray(value) for key, value in spatial.items()}
    time_floor = 2 * (rule["min_departure_m"] - rule["radius_m"]) / max(speeds) * 1e6
    relative = points - center
    unwrapped = np.unwrap(np.arctan2(relative[:, 1], relative[:, 0]))
    for end, cell in zip(candidates, cell_index):
        neighbours = [spatial[(x, y)] for x in range(cell[0] - 1, cell[0] + 2) for y in range(cell[1] - 1, cell[1] + 2) if (x, y) in spatial]
        earlier = np.concatenate(neighbours)
        earlier = earlier[(earlier < end) & (ticks[end] - ticks[earlier] >= time_floor)]
        earlier = earlier[np.sum((points[earlier] - points[end]) ** 2, axis=1) <= rule["radius_m"] ** 2]
        for begin in sorted(earlier):
            cosine = np.dot(velocities[begin, :2] / ground[begin], velocities[end, :2] / ground[end])
            angle = float(np.degrees(np.arccos(np.clip(cosine, -1, 1))))
            if rule["parallel_max_deg"] < angle < rule["antiparallel_min_deg"]: continue
            if np.degrees(np.ptp(unwrapped[begin:end + 1])) < rule["min_azimuth_coverage_deg"]: continue
            segment = points[begin:end + 1]
            departure = float(np.sqrt(np.max(np.sum((segment - points[begin]) ** 2, axis=1))))
            if departure < rule["min_departure_m"]: continue
            extent = circular_extent(segment, center)
            if extent < rule["min_azimuth_coverage_deg"]: continue
            return dict(detected=True, frame_index=int(begin), confirm_frame_index=int(end),
                t1=float(ticks[begin] / 1e6), t2=float(ticks[end] / 1e6), t_confirm=float(ticks[end] / 1e6),
                distance_m=float(np.linalg.norm(points[begin] - points[end])), departure_m=departure,
                heading_difference_deg=angle, azimuth_coverage_deg=extent)
    return missing


def independent_coverage(points, speed, layers, blocked, survey):
    rule = configuration()["detectors"]["coverage"]
    geometry = survey.get("geometry", {"type": "Polygon", "vertices_m": survey.get("vertices_m", [])})
    if "bounds_m" in survey: x0, y0, x1, y1 = survey["bounds_m"]
    else:
        vertices = np.asarray(survey["vertices_m"])
        x0, y0 = vertices.min(axis=0); x1, y1 = vertices.max(axis=0)
    step = survey["grid_spacing_m"]
    x, y = np.meshgrid(np.arange(x0 + step / 2, x1, step), np.arange(y0 + step / 2, y1, step))
    grid = np.column_stack([x.ravel(), y.ravel()]); grid = grid[_inside(geometry, grid)]
    valid = _inside(geometry, points) & (speed >= rule["effective_speed_min_m_s"]) & (layers == 1) & ~blocked
    hit = np.zeros(len(grid), bool)
    for start in range(0, len(grid), 64):
        if valid.any():
            squared = np.sum((grid[start:start + 64, None] - points[valid][None]) ** 2, axis=2)
            hit[start:start + 64] = squared.min(axis=1) <= survey["footprint_radius_m"] ** 2
    return {"effective_mask": valid, "covered_mask": hit, "grid_point_count": len(grid)}
