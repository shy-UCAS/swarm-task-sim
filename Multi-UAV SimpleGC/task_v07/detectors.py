"""Shared behavior facts on the 10 Hz truth grid (no planned motion inputs)."""
from collections import defaultdict
from itertools import product
import numpy as np

from .criteria import load_criteria
from .geometry import geometry_facts
from .survey import survey_grid


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


def coverage(xy, speed, levels, restricted, survey, criteria=None):
    rules = (criteria or load_criteria())["detectors"]["coverage"]
    grid = survey_grid(survey)
    geometry = survey.get("geometry", {"type": "Polygon", "vertices_m": survey.get("vertices_m", [])})
    effective = geometry_facts(geometry, xy)["inside"] & (speed >= rules["effective_speed_min_m_s"])
    effective &= (levels == 1) & ~restricted
    covered = np.zeros(len(grid), bool)
    samples = xy[effective]
    # Footprint union, independent of lane order or a planned completion time.
    for offset in range(0, len(samples), 256):
        remaining = np.flatnonzero(~covered)
        if not len(remaining):
            break
        delta = grid[remaining, None] - samples[None, offset:offset + 256]
        covered[remaining] = np.any(np.sum(delta * delta, axis=2) <= survey["footprint_radius_m"] ** 2, axis=1)
    return {"effective_mask": effective, "covered_mask": covered, "grid_point_count": len(grid)}
