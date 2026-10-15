"""Generic exact geometry checks on the exported 10 Hz grid only."""
from itertools import combinations

import numpy as np

from task_v07.geometry import geometry_facts, GEOMETRY_VERSION
from task_v07.labels import validate_grid
from .contracts import P0ContractError

# Exact-tangent planner edges and boundary placements compute to within ~1e-13 m.
NUMERICAL_TOLERANCE_M = 1e-6

# Planning-layer interval check: minimum separation that triggers a warning.
PLANNING_INTERVAL_WARNING_M = 6.0
# Sampling rate for constant-speed interpolation (frames per second).
PLANNING_INTERVAL_SAMPLE_HZ = 10.0


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
    """Validate supplied segments; does not construct, improve or reroute them.

    Planner edges are exactly tangent to the inflated constraints, so a margin
    is met within NUMERICAL_TOLERANCE_M; zero-margin contact is still rejected.
    """
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
        if np.any(geometry_facts(scene["world"]["geometry"], np.array([a[:2], b[:2]]))["signed_distance_m"] > -margin_m + NUMERICAL_TOLERANCE_M):
            issues.append({"segment": i, "code": "world_margin"})
        for entity in constraints:
            d = geometry_facts(entity["geometry"], np.array([a[:2], b[:2]]), footprint=True)["clearance_m"]
            if d <= 0 or d < margin_m - NUMERICAL_TOLERANCE_M:
                issues.append({"segment": i, "code": "constraint_clearance", "entity_id": entity["id"],
                               "clearance_m": d})
    return {"valid": not issues, "issues": issues, "numerical_tolerance_m": NUMERICAL_TOLERANCE_M}


def check_endpoint_spacing(bundle, members, warning_m=PLANNING_INTERVAL_WARNING_M):
    """Check that all agents' final waypoints are at least warning_m apart.

    Returns {"valid": bool, "minimum_m": float, "below_warning": bool}.
    This catches the degenerate case where the planner assigns the same or nearly
    identical endpoints to multiple agents, which causes collisions at the hold
    regardless of departure timing.
    """
    endpoints = [np.array(bundle.waypoints_by_agent[a][-1][:2]) for a in members]
    if len(endpoints) < 2:
        return {"valid": True, "minimum_m": None, "below_warning": False}
    minimum = min(float(np.linalg.norm(endpoints[i] - endpoints[j]))
                  for i in range(len(endpoints))
                  for j in range(i + 1, len(endpoints)))
    return {"valid": minimum >= warning_m, "minimum_m": round(minimum, 4),
            "below_warning": minimum < warning_m}


def check_retreat_point(scene, xy, warning_clearance_m=200.0, obstacle_margin_m=35.0):
    if any(not np.isfinite(v) or v < 0 for v in (warning_clearance_m, obstacle_margin_m)):
        raise ValueError("Finite nonnegative clearances required")
    clearances = {}
    for e in scene["entities"]:
        if e.get("layer") == "warning" or e["type"] == "hard_constraint_obstacle":
            minimum = warning_clearance_m if e.get("layer") == "warning" else obstacle_margin_m
            distance = float(geometry_facts(e["geometry"], xy)["signed_distance_m"])
            clearances[e["id"]] = {"clearance_m": distance, "required_m": minimum,
                                   "valid": distance > 0 and distance >= minimum - NUMERICAL_TOLERANCE_M}
    world = float(geometry_facts(scene["world"]["geometry"], xy)["signed_distance_m"])
    return {"valid": world <= -obstacle_margin_m + NUMERICAL_TOLERANCE_M and all(c["valid"] for c in clearances.values()),
            "world_inward_clearance_m": -world, "clearances": clearances,
            "numerical_tolerance_m": NUMERICAL_TOLERANCE_M}


def _interpolate_route_at_speed(waypoints_3d, speed_m_s, sample_hz=PLANNING_INTERVAL_SAMPLE_HZ):
    """Constant-speed interpolation of a 3-D waypoint route at sample_hz.

    Returns an (N, 3) float array of positions sampled at 1/sample_hz second intervals
    starting at t=0.  The route ends when the last waypoint is reached; the final
    position is held for two extra samples so agents that finish early are not
    excluded from separation checks.
    """
    pts = np.asarray(waypoints_3d, float)
    if len(pts) < 2:
        return pts[:1] if len(pts) else np.zeros((1, 3))
    segs = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    total = float(segs.sum())
    if total < 1e-9 or speed_m_s <= 0:
        return np.tile(pts[0], (3, 1))
    dt = 1.0 / sample_hz
    n_frames = int(np.ceil(total / speed_m_s / dt)) + 3  # +3 for hold
    cum=np.r_[0.,np.cumsum(segs)]
    distances=np.minimum(np.arange(n_frames,dtype=float)*dt*speed_m_s,total)
    indices=np.clip(np.searchsorted(cum,distances,side="right")-1,0,len(pts)-2)
    fractions=np.divide(distances-cum[indices],segs[indices],out=np.zeros(n_frames),where=segs[indices]>1e-12)
    return pts[indices]+fractions[:,None]*(pts[indices+1]-pts[indices])



def planning_layer_interval_check(bundle, timing_plans, speed_m_s,
                                   warning_m=PLANNING_INTERVAL_WARNING_M,
                                   sample_hz=PLANNING_INTERVAL_SAMPLE_HZ, *, dwells_by_agent=None):
    """Estimate minimum inter-agent separation at the planning layer.

    Uses constant-speed interpolation along each agent's waypoints, shifted by
    the departure delays from both the synchronous and sequential timing plans.
    The check is a planning estimate, not a hard constraint — the actual
    separation is determined from 10 Hz truth in exact_frame_geometry.

    Parameters
    ----------
    bundle : RouteBundle
        Per-agent 3-D waypoints (including the retreat leg).
    timing_plans : dict
        Output of departure_delays(): keys "synchronous" and "sequential", each
        with "departure_delays_s" mapping agent_id → delay.
    speed_m_s : float
        Cruise speed used for constant-speed interpolation.
    warning_m : float
        Separation below this value is flagged as a warning.
    sample_hz : float
        Interpolation sampling rate.

    Returns
    -------
    dict with keys:
        "synchronous" and "sequential": per-mode dicts with
            minimum_m, closest_pair, below_warning, frames_checked.
        "warning_threshold_m": the threshold used.
        "speed_m_s": the speed used.
        "method": description string.
    """
    results = {}
    interpolated={a:_interpolate_route_at_speed(points,speed_m_s,sample_hz)
                  for a,points in bundle.waypoints_by_agent.items()}
    if dwells_by_agent:
        from task_v07.dwell import timed_route_samples
        for a,dwell in dwells_by_agent.items():
            interpolated[a]=timed_route_samples(bundle.waypoints_by_agent[a],speed_m_s,sample_hz,dwell)
    for mode in ("synchronous", "sequential"):
        plan = timing_plans[mode]
        delays = plan["departure_delays_s"]
        agents = sorted(bundle.waypoints_by_agent)
        dt = 1.0 / sample_hz

        # Interpolate each agent's route at constant speed.
        routes = {}
        for a in agents:
            routes[a] = interpolated[a]

        # Apply departure delays: shift each agent's route in time.
        # Build a common time axis covering all agents.
        min_delay = min(delays[a] for a in agents)
        offsets = {a: int(round((delays[a] - min_delay) / dt)) for a in agents}
        total_frames = max(offsets[a] + len(routes[a]) for a in agents)
        total_frames = max(total_frames, 2)

        # Pad routes with their final position for agents that finish early.
        padded = {}
        for a in agents:
            off = offsets[a]
            r = routes[a]
            pad_before = np.tile(r[0], (off, 1)) if off > 0 else np.empty((0, 3))
            pad_after_n = total_frames - off - len(r)
            pad_after = np.tile(r[-1], (max(0, pad_after_n), 1))
            padded[a] = np.concatenate([pad_before, r, pad_after], axis=0)[:total_frames]

        # Find minimum separation across all agent pairs.
        minimum_m = None
        closest_pair = None
        for a, b in combinations(agents, 2):
            diff = padded[a] - padded[b]
            dist = np.linalg.norm(diff, axis=1)
            k = int(dist.argmin())
            d = float(dist[k])
            if minimum_m is None or d < minimum_m:
                minimum_m = d
                closest_pair = {"agents": [a, b], "frame_index": k,
                                "t_s": round((k + int(round(min_delay / dt))) * dt, 3)}

        results[mode] = {
            "minimum_m": round(minimum_m, 4) if minimum_m is not None else None,
            "closest_pair": closest_pair,
            "below_warning": minimum_m is not None and minimum_m < warning_m,
            "frames_checked": total_frames,
        }

    return {
        "synchronous": results["synchronous"],
        "sequential": results["sequential"],
        "warning_threshold_m": warning_m,
        "speed_m_s": speed_m_s,
        "method": "constant-speed interpolation along planned waypoints + departure delays",
    }
