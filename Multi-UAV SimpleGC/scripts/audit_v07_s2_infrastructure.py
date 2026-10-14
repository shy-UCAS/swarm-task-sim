"""Independent generic all-frame audit using original GEOS contours.

Deliberately does not import task_v07.geometry or any label implementation.
This module validates saved frame facts, not role-specific mission predicates.
"""
from itertools import combinations

import numpy as np
import shapely
from shapely.geometry import Polygon


def _distance(geometry, xy):
    if geometry["type"] == "Circle":
        delta = xy - np.asarray(geometry["center_m"])
        return np.hypot(delta[..., 0], delta[..., 1]) - geometry["radius_m"]
    polygon = Polygon(geometry["vertices_m"])
    points = shapely.points(xy)
    inside = shapely.covers(polygon, points)
    magnitude = shapely.distance(polygon.boundary, points)
    return np.where(inside, -magnitude, magnitude) - geometry.get("buffer_m", 0.0)


def audit_geometry(scene, run, frame, report, targets=None, forbidden_layers=None):
    ids = list(run["agent_ids"])
    times, positions = np.asarray(run["time_us"]), np.asarray(run["p"])
    facilities = sorted((e for e in scene["entities"] if e["type"] == "facility"), key=lambda e: e["id"])
    fids = [f["id"] for f in facilities]
    errors = []
    required = {"time_us", "agent_ids", "facility_ids", "region_all_facilities",
                "inside_hard_obstacle", "outside_world", "forbidden_region"}
    if not required <= set(frame):
        return {"status": "FAIL", "errors": ["missing_frame_fields"], "differences": None}
    if (times.ndim != 1 or not len(times) or times[0] != 0 or np.any(np.diff(times) != 100000)
            or len(set(ids)) != len(ids) or positions.shape != (len(times), len(ids), 3)
            or not np.isfinite(positions).all()):
        return {"status": "FAIL", "errors": ["invalid_truth_grid"], "differences": None}
    if frame["agent_ids"].tolist() != ids or frame["facility_ids"].tolist() != fids or not np.array_equal(frame["time_us"], times):
        return {"status": "FAIL", "errors": ["frame_axes_mismatch"], "differences": None}
    independent = np.zeros((*positions.shape[:2], len(fids)), dtype=np.int8)
    for fi, f in enumerate(facilities):
        distance = _distance(f["geometry"], positions[..., :2])
        offsets = {e["layer"]: e["offset_m"] for e in scene["entities"] if e.get("facility_id") == f["id"]}
        for code, layer in enumerate(("warning", "alert", "protected"), 1):
            independent[..., fi][distance <= offsets[layer]] = code
    if frame["region_all_facilities"].shape != independent.shape:
        return {"status": "FAIL", "errors": ["region_shape_mismatch"], "differences": None}
    differences = int(np.count_nonzero(independent != frame["region_all_facilities"]))
    if differences:
        errors.append("region_all_facilities")
    target_differences = 0
    if targets is not None:
        expected = np.stack([independent[:, i, fids.index(targets[a])] for i, a in enumerate(ids)], axis=1)
        if "region_assigned_target" not in frame or frame["region_assigned_target"].shape != expected.shape:
            errors.append("assigned_target_shape")
        else:
            target_differences = int(np.count_nonzero(expected != frame["region_assigned_target"]))
            if target_differences:
                errors.append("region_assigned_target")
    obstacle = np.zeros(positions.shape[:2], bool)
    for e in scene["entities"]:
        if e["type"] == "hard_constraint_obstacle":
            obstacle |= _distance(e["geometry"], positions[..., :2]) <= 0
    outside = _distance(scene["world"]["geometry"], positions[..., :2]) > 0
    forbidden = np.zeros_like(obstacle)
    if forbidden_layers is not None:
        for i, agent in enumerate(ids):
            for fid, layer in forbidden_layers[agent].items():
                forbidden[:, i] |= independent[:, i, fids.index(fid)] >= {"warning": 1, "alert": 2, "protected": 3}[layer]
    for key, expected in (("inside_hard_obstacle", obstacle), ("outside_world", outside), ("forbidden_region", forbidden)):
        if key in frame and not np.array_equal(frame[key], expected):
            errors.append(key)
    distances = [float(np.sqrt(np.sum((positions[:, ids.index(a)] - positions[:, ids.index(b)])**2, axis=1)).min())
                 for a, b in combinations(sorted(ids), 2)]
    minimum = min(distances) if distances else None
    stored = report.get("minimum_separation_m")
    if (stored is None) != (minimum is None) or (minimum is not None and abs(stored - minimum) > 1e-9):
        errors.append("minimum_separation_m")
    if report.get("generation_error") != (minimum is not None and minimum < 2):
        errors.append("separation_generation_error")
    for key, mask in (("hard_obstacle_sample_count", obstacle), ("outside_world_sample_count", outside),
                      ("forbidden_region_sample_count", forbidden)):
        if key in report and report[key] != int(mask.sum()):
            errors.append(key)
    return {"status": "FAIL" if errors else "PASS", "errors": errors,
            "differences": differences, "target_differences": target_differences,
            "facility_frame_comparisons": int(independent.size), "minimum_separation_m": minimum,
            "source": "exported 10 Hz grid; independent GEOS original contours / analytic circles"}
