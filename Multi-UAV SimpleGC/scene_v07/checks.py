"""Geometry gates, all-pairs entry access, and diagnostic approach directions."""
import math

from shapely.geometry import LineString, Point

from .contract import SceneConfig, validate_public_scene
from .diagnostics import route_diagnostics
from .geometry import VisibilityPlanner, center_of, expand_geometry, polyline_length, radial_boundary, to_shape


def angle_arcs(mask, step_deg):
    """Non-wrapping bin-edge intervals in [0, 360]; bin centers are half steps."""
    if len(mask) * step_deg != 360:
        raise ValueError("Angular mask must cover exactly one revolution")
    arcs = []
    start = None
    for i, available in enumerate([*mask, False]):
        if available and start is None:
            start = i * step_deg
        elif not available and start is not None:
            arcs.append([start, i * step_deg])
            start = None
    return arcs


def max_span(mask, step_deg):
    if all(mask):
        return 360
    run = best = 0
    for value in mask + mask:
        run = run + 1 if value else 0
        best = max(best, run)
    return min(best, len(mask)) * step_deg


def check_family(scene, family):
    validate_public_scene(scene)
    config = SceneConfig(**family["config"])
    q = config.checking_quad_segs
    world = to_shape(scene["world"]["geometry"], q)
    entities = scene["entities"]
    facilities = [e for e in entities if e["type"] == "facility"]
    obstacles = [e for e in entities if e["type"] == "hard_constraint_obstacle"]
    shapes = {e["id"]: to_shape(e["geometry"], q) for e in entities}
    entries = {e["id"]: to_shape(e["geometry"], q) for e in scene["entry_zones"]}
    layers = {f["id"]: {e["layer"]: e for e in entities
                         if e["type"] == "protection_zone" and e["facility_id"] == f["id"]}
              for f in facilities}
    issues = []

    def issue(code, *ids, category="geometry"):
        issues.append({"code": code, "entity_ids": list(ids), "category": category})

    for e in entities:
        # Use enclosing tessellation for containment; keeps the full contour
        # inside the 4 km map rather than silently clipping protection layers.
        enclosing = to_shape(e["geometry"], q, conservative=True)
        if not world.covers(enclosing):
            issue("protection_outside_world" if e["type"] == "protection_zone" else "entity_outside_world", e["id"])
    for identifier, entry in entries.items():
        if not world.covers(entry):
            issue("entry_outside_world", identifier)
    for facility in facilities:
        fid = facility["id"]
        offsets = [layers[fid][layer]["offset_m"] for layer in ["protected", "alert", "warning"]]
        if not 0 < offsets[0] < offsets[1] < offsets[2]:
            issue("invalid_layer_offsets", fid)
        for layer in ["protected", "alert", "warning"]:
            expected = expand_geometry(facility["geometry"], layers[fid][layer]["offset_m"])
            if layers[fid][layer]["geometry"] != expected:
                issue("layer_not_contour_buffer", layers[fid][layer]["id"])
    for i, a in enumerate(facilities):
        for b in facilities[:i]:
            for layer in ["protected", "alert"]:
                ga, gb = [to_shape(layers[f["id"]][layer]["geometry"], q, True) for f in [a, b]]
                if ga.intersects(gb):
                    issue(f"{layer}_zones_intersect", a["id"], b["id"])
            if family["layout"] == "isolated":
                ga, gb = [to_shape(layers[f["id"]]["warning"]["geometry"], q, True) for f in [a, b]]
                if ga.intersects(gb):
                    issue("isolated_warning_overlap", a["id"], b["id"])
    if family["layout"] == "clustered" and len(facilities) > 1:
        visited = {facilities[0]["id"]}
        for _ in facilities:
            for a in facilities:
                for b in facilities:
                    if a["id"] in visited and shapes[layers[a["id"]]["warning"]["id"]].intersects(
                            shapes[layers[b["id"]]["warning"]["id"]]):
                        visited.add(b["id"])
        if len(visited) != len(facilities):
            issue("cluster_warning_disconnected", *[f["id"] for f in facilities])
    if family["layout"] == "linear" and len(facilities) > 2:
        centers = [center_of(f["geometry"]) for f in facilities]
        corridor = LineString([centers[0], centers[-1]])
        if max(corridor.distance(Point(c)) for c in centers) > 1e-6:
            issue("linear_facilities_not_collinear", *[f["id"] for f in facilities])
    placements = {p["obstacle_id"]: p for p in family["obstacle_placements"]}
    for obstacle in obstacles:
        oid = obstacle["id"]
        enclosed = to_shape(obstacle["geometry"], q, True)
        expanded = to_shape(expand_geometry(obstacle["geometry"], config.safety_margin_m),
                            config.planning_quad_segs, True)
        for facility in facilities:
            for layer in ["protected", "alert"]:
                if enclosed.intersects(to_shape(layers[facility["id"]][layer]["geometry"], q, True)):
                    issue(f"obstacle_intersects_{layer}", oid, facility["id"])
        for eid, entry in entries.items():
            if enclosed.intersects(entry):
                issue("obstacle_covers_entry", oid, eid)
            elif expanded.intersects(entry):
                issue("obstacle_margin_blocks_entry", oid, eid)
        placement = placements[oid]
        if placement["placement"] == "facility_side":
            warning = shapes[layers[placement["reference_facility_id"]]["warning"]["id"]]
            shape = shapes[oid]
            if not (shape.intersection(warning).area > 0 and shape.difference(warning).area > 0
                    and warning.difference(shape).area > 0):
                issue("side_obstacle_not_partial_warning_overlap", oid)
        elif placement["placement"] == "entry_blocking":
            entry = next(e for e in scene["entry_zones"] if e["id"] == placement["entry_id"])
            facility = next(f for f in facilities if f["id"] == placement["reference_facility_id"])
            if not shapes[oid].intersects(LineString([center_of(entry["geometry"]), center_of(facility["geometry"])])):
                issue("entry_blocker_misses_corridor", oid)
        elif placement["placement"] != "between_facilities" or len(facilities) < 2:
            issue("invalid_obstacle_placement", oid)
    for radar in family["radar_placements"]:
        shape = shapes[radar["radar_id"]]
        if radar["placement"] == "facility_side" and not shapes[layers[radar["reference_facility_id"]]["alert"]["id"]].covers(shape):
            issue("radar_outside_alert", radar["radar_id"])
    if len(family["initial_states"]) != family["vehicle_count"]:
        raise ValueError("Family initial-state count contract is corrupt")
    agent_ids = [s["agent_id"] for s in family["initial_states"]]
    if len(set(agent_ids)) != len(agent_ids):
        raise ValueError("Family agent IDs are not unique")
    for state in family["initial_states"]:
        position = state["position_enu_m"]
        if not entries[state["entry_id"]].covers(Point(position[:2])):
            issue("initial_state_outside_entry", state["agent_id"])
        if position[2] != family["task_altitude_m"]:
            raise ValueError("Family altitude contract is corrupt")
    planner = VisibilityPlanner(scene, config.safety_margin_m, config.planning_quad_segs)
    routes = []
    for entry in scene["entry_zones"]:
        source = center_of(entry["geometry"])
        for facility in facilities:
            destination = center_of(facility["geometry"])
            path = planner.path(source, destination)
            if path is None:
                issue("entry_facility_unreachable", entry["id"], facility["id"], category="connectivity")
            direct = math.dist(source, destination)
            routes.append({"entry_id": entry["id"], "facility_id": facility["id"], "points_m": path,
                           "direct_length_m": direct, "length_m": polyline_length(path) if path else None,
                           "detour_ratio": polyline_length(path) / direct if path and direct else None,
                           **route_diagnostics(scene, family, planner, source, destination, path)})
    approaches = []
    for facility in facilities:
        center = center_of(facility["geometry"])
        warning = layers[facility["id"]]["warning"]["geometry"]
        samples, per_entry = [], {e["id"]: [] for e in scene["entry_zones"]}
        for i in range(360 // config.angle_step_deg):
            angle_deg = (i + .5) * config.angle_step_deg
            angle = math.radians(angle_deg)
            boundary = radial_boundary(warning, center, angle)
            point = [boundary[0] + config.approach_standoff_m * math.cos(angle),
                     boundary[1] + config.approach_standoff_m * math.sin(angle)]
            inward_clear = planner.visible(point, center)
            for entry in scene["entry_zones"]:
                possible = inward_clear and planner.path(center_of(entry["geometry"]), point) is not None
                per_entry[entry["id"]].append(possible)
            samples.append({"angle_deg": angle_deg, "point_m": point})
        # Shared mask requires all entries, with per-entry masks also retained.
        mask = [all(values[i] for values in per_entry.values()) for i in range(len(samples))]
        approaches.append({"facility_id": facility["id"], "angle_step_deg": config.angle_step_deg,
                           "samples": samples, "feasible_mask": mask,
                           "arcs_deg": angle_arcs(mask, config.angle_step_deg),
                           "available_span_deg": sum(mask) * config.angle_step_deg,
                           "max_contiguous_span_deg": max_span(mask, config.angle_step_deg),
                           "by_entry": [{"entry_id": eid, "feasible_mask": values,
                                         "arcs_deg": angle_arcs(values, config.angle_step_deg)}
                                        for eid, values in per_entry.items()]})
    return {"schema_version": "traj2language.scene_checks/0.7-s1.2", "accepted": not issues,
            "issues": issues, "routes": routes, "approaches": approaches,
            "approach_interpretation": "Sampled 5-degree bins by default; entry-to-standoff route plus clear radial inward leg; diagnostic only"}
