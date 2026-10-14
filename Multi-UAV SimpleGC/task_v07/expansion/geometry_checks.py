"""Generic exact geometry checks on the exported 10 Hz grid only."""
from itertools import combinations

import numpy as np

from task_v07.geometry import geometry_facts, GEOMETRY_VERSION
from task_v07.labels import validate_grid
from .contracts import P0ContractError


def facility_axes(scene):
    facilities = sorted((e for e in scene["entities"] if e["type"] == "facility"), key=lambda e: e["id"])
    offsets = {f["id"]: {e["layer"]: e["offset_m"] for e in scene["entities"]
                         if e.get("facility_id") == f["id"]} for f in facilities}
    return facilities, offsets


def exact_frame_geometry(scene, run, targets=None, forbidden_layers=None):
    """No role inference. Callers supply an explicit per-ID facility/layer policy.

    The output is privileged audit data, never part of the default model input.
    Separation <2 m is a generation error, not a mission-result condition.
    """
    ids = list(run["agent_ids"])
    t, p, v = (np.asarray(run[k]) for k in ("time_us", "p", "v"))
    validate_grid(t, p, v, ids)
    facilities, offsets = facility_axes(scene)
    fids = [f["id"] for f in facilities]
    levels = np.stack([geometry_facts(f["geometry"], p[..., :2],
                                     layer_offsets=offsets[f["id"]])["layer"] for f in facilities], axis=-1)
    obstacles = np.zeros(p.shape[:2], dtype=bool)
    for e in scene["entities"]:
        if e["type"] == "hard_constraint_obstacle":
            obstacles |= geometry_facts(e["geometry"], p[..., :2])["inside"]
    outside = ~geometry_facts(scene["world"]["geometry"], p[..., :2])["inside"]
    violation = np.zeros_like(obstacles)
    if forbidden_layers is not None:
        if set(forbidden_layers) != set(ids):
            raise P0ContractError("Forbidden-region policy must explicitly cover every agent")
        for i, agent in enumerate(ids):
            for fid, layer in forbidden_layers[agent].items():
                if fid not in fids or layer not in ("warning", "alert", "protected"):
                    raise ValueError("Unknown facility/layer constraint")
                violation[:, i] |= levels[:, i, fids.index(fid)] >= {"warning": 1, "alert": 2, "protected": 3}[layer]
    minimum = None
    closest = None
    for a, b in combinations(sorted(ids), 2):
        d = np.linalg.norm(p[:, ids.index(a)] - p[:, ids.index(b)], axis=1)
        k = int(d.argmin())
        if minimum is None or float(d[k]) < minimum:
            minimum = float(d[k])
            closest = {"agents": [a, b], "frame_index": k, "t_s": float(t[k] / 1e6)}
    frame = {"time_us": t.copy(), "agent_ids": np.array(ids), "facility_ids": np.array(fids),
             "region_all_facilities": levels, "inside_hard_obstacle": obstacles,
             "outside_world": outside, "forbidden_region": violation}
    if targets is not None:
        if set(targets) != set(ids) or any(f not in fids for f in targets.values()):
            raise P0ContractError("Target mapping must explicitly cover every ID")
        frame["region_assigned_target"] = np.stack(
            [levels[:, i, fids.index(targets[a])] for i, a in enumerate(ids)], axis=1)
    return frame, {"geometry_version": GEOMETRY_VERSION, "evidence_grid_hz": 10,
                   "frame_count": len(t), "agent_count": len(ids),
                   "facility_frame_comparisons": int(levels.size),
                   "minimum_separation_m": minimum, "closest_pair": closest,
                   "generation_error": minimum is not None and minimum < 2.0,
                   "separation_affects_task_result": False,
                   "hard_obstacle_sample_count": int(obstacles.sum()),
                   "outside_world_sample_count": int(outside.sum()),
                   "forbidden_region_sample_count": int(violation.sum()),
                   "forbidden_policy_checked": forbidden_layers is not None}


def check_polyline(scene, points_enu_m, *, forbidden_regions=(), margin_m=35.0):
    """Validate supplied segments; does not construct, improve or reroute them."""
    points = np.asarray(points_enu_m, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 2 or not np.isfinite(points).all():
        raise ValueError("Expected finite [K>=2,3] route")
    if margin_m < 0 or not np.isfinite(margin_m):
        raise ValueError("Finite nonnegative margin required")
    constraints = [e for e in scene["entities"] if e["type"] == "hard_constraint_obstacle"]
    entities = {e["id"]: e for e in scene["entities"]}
    constraints += [entities[key] for key in forbidden_regions]
    issues = []
    for i, (a, b) in enumerate(zip(points, points[1:])):
        if np.linalg.norm(b - a) < 1.0:
            issues.append({"segment": i, "code": "sub_metre_waypoint"})
        if np.any(geometry_facts(scene["world"]["geometry"], np.array([a[:2], b[:2]]))["signed_distance_m"] > -margin_m):
            issues.append({"segment": i, "code": "world_margin"})
        for entity in constraints:
            d = geometry_facts(entity["geometry"], np.array([a[:2], b[:2]]), footprint=True)["clearance_m"]
            if d <= 0 or d < margin_m:
                issues.append({"segment": i, "code": "constraint_clearance", "entity_id": entity["id"],
                               "clearance_m": d})
    return {"valid": not issues, "issues": issues}


def check_retreat_point(scene, xy, warning_clearance_m=200.0, obstacle_margin_m=35.0):
    if any(not np.isfinite(v) or v < 0 for v in (warning_clearance_m, obstacle_margin_m)):
        raise ValueError("Finite nonnegative clearances required")
    clearances = {}
    for e in scene["entities"]:
        if e.get("layer") == "warning" or e["type"] == "hard_constraint_obstacle":
            minimum = warning_clearance_m if e.get("layer") == "warning" else obstacle_margin_m
            distance = float(geometry_facts(e["geometry"], xy)["signed_distance_m"])
            clearances[e["id"]] = {"clearance_m": distance, "required_m": minimum,
                                   "valid": distance > 0 and distance >= minimum}
    world = float(geometry_facts(scene["world"]["geometry"], xy)["signed_distance_m"])
    return {"valid": world <= -obstacle_margin_m and all(c["valid"] for c in clearances.values()),
            "world_inward_clearance_m": -world, "clearances": clearances}
