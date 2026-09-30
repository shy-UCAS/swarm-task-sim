"""Deterministic shared-rectangle allocation compiled to existing AUTO phases."""

import copy
import math

from .capability import nominal_capability
from .mission_schema import normalize_mission
from .scenario import validate


PLANNER_VERSION = "equal_strip_lawnmower_v1"
SEMANTIC_PLAN_VERSION = "shared_semantics_v1"


def partition_region(region, count, axis):
    """Equal positive strips in global ENU; adjacent boundaries share one value."""
    if type(count) is not int or not 1 <= count <= 6 or axis not in ("east", "north"):
        raise ValueError("partition requires 1..6 agents and east/north axis")
    dimension = "width_m" if axis == "east" else "height_m"
    coordinate = "min_east_m" if axis == "east" else "min_north_m"
    if region[dimension] <= 0:
        raise ValueError("partition requires positive region area")
    boundaries = [region[coordinate] + region[dimension] * index / count for index in range(count + 1)]
    result = []
    for index in range(count):
        strip = {key: region[key] for key in ("min_east_m", "min_north_m", "width_m", "height_m")}
        strip.update(id=f"{region['id']}_strip_{index + 1:02d}", type="rectangle")
        strip[coordinate] = boundaries[index]
        strip[dimension] = boundaries[index + 1] - boundaries[index]
        result.append(strip)
    return result


def lawnmower_route(partition, axis, lanes):
    """Center lanes avoid coincident border paths without hiding uncovered gaps."""
    route = []
    for index in range(lanes):
        if axis == "east":
            cross = partition["min_east_m"] + partition["width_m"] * (index + 0.5) / lanes
            low = (cross, partition["min_north_m"])
            high = (cross, partition["min_north_m"] + partition["height_m"])
        else:
            cross = partition["min_north_m"] + partition["height_m"] * (index + 0.5) / lanes
            low = (partition["min_east_m"], cross)
            high = (partition["min_east_m"] + partition["width_m"], cross)
        route.extend((low, high) if index % 2 == 0 else (high, low))
    return [{"east_m": east, "north_m": north} for east, north in route]


def compile_execution_phases(spec, routes, assignments):
    """Compile semantic routes with explicit stationary non-service padding."""
    execution = spec["execution"]
    agents = [v["id"] for v in spec["scenario"]["vehicles"]]
    if set(routes) != set(agents) or set(assignments) != set(agents):
        raise ValueError("routes and assignments must identify every agent")
    previous = {v["id"]: {"east_m": v["east_m"], "north_m": v["north_m"]}
                for v in spec["scenario"]["vehicles"]}
    phases, mapping, by_semantic = [], {}, {}
    idle = {agent: 0 for agent in agents}
    for semantic in ("approach", "observe", "return"):
        by_semantic[semantic] = []
        length = max(len(routes[agent][semantic]) for agent in agents)
        for index in range(length):
            name = f"leg_{len(phases):03d}"
            targets, roles = {}, {}
            for agent in agents:
                active = index < len(routes[agent][semantic])
                point = routes[agent][semantic][index] if active else previous[agent]
                targets[agent] = {"east_m": point["east_m"], "north_m": point["north_m"],
                                  "up_m": execution["takeoff_alt_m"], "speed_m_s": execution["speed_m_s"],
                                  "hold_s": execution["waypoint_hold_s"]}
                role = semantic if active else "idle_padding"
                roles[agent] = {"role": role, "service_enabled": role == "observe",
                                "partition_id": assignments[agent]}
                idle[agent] += int(not active)
                previous[agent] = point
            phases.append({"name": name, "targets": targets})
            mapping[name] = {"semantic_phase": semantic, "agents": roles}
            by_semantic[semantic].append(name)
    if not 1 <= len(phases) <= 100:
        raise ValueError("shared route exceeds backend limit of 1 to 100 execution phases")
    return phases, {"version": SEMANTIC_PLAN_VERSION, "execution_phases": mapping,
                    "service_activation": "each agent observe execution phase only; padding disabled",
                    "window_source": "execution_events + compiled_semantic_plan"}, by_semantic, idle


def nominal_coverage(region, routes, model):
    """Reference-only diagnostic on the same declared global cell-center model.

    This result is never an execution success label; the actual-path evaluator
    independently builds and checks the grid from evidence.
    """
    from .tasks import point_segment

    nx = math.ceil(region["width_m"] / model["grid_m"])
    ny = math.ceil(region["height_m"] / model["grid_m"])
    covered = set()
    for route in routes.values():
        points = [(p["east_m"], p["north_m"]) for p in route["observe"]]
        segments = list(zip(points, points[1:])) or [(points[0], points[0])]
        for i in range(nx):
            for j in range(ny):
                cell = (i, j)
                if cell in covered:
                    continue
                point = (region["min_east_m"] + (i + 0.5) * region["width_m"] / nx,
                         region["min_north_m"] + (j + 0.5) * region["height_m"] / ny)
                if any(point_segment(point, a, b) <= model["radius_m"] + 1e-9 for a, b in segments):
                    covered.add(cell)
    return {"ratio": len(covered) / (nx * ny), "covered_cells": len(covered),
            "total_cells": nx * ny, "requested_grid_m": model["grid_m"],
            "cell_width_m": region["width_m"] / nx, "cell_height_m": region["height_m"] / ny,
            "model_version": "ideal_horizontal_disk_v1", "source": "planned_reference_only"}


def compile_shared_mission_v2(spec):
    spec = normalize_mission(spec)
    scenario, mission, planner, execution = (spec[key] for key in ("scenario", "mission", "planner", "execution"))
    region = next(r for r in scenario["regions"] if r["id"] == mission["target_region_id"])
    axis = planner["partition_axis"]
    partitions = partition_region(region, len(scenario["vehicles"]), axis)
    cross_width = region["width_m" if axis == "east" else "height_m"] / len(partitions)
    if cross_width <= 2 * execution["arrival_tolerance_m"]:
        raise ValueError("responsibility strip too small for declared arrival tolerance")
    lanes = max(1, math.ceil(cross_width / planner["lane_spacing_m"]))
    if 1 + 2 * lanes + int(mission["return_required"]) > 100:
        raise ValueError("shared route exceeds backend limit of 100 execution phases")
    ordering = sorted(scenario["vehicles"], key=lambda v: (v[f"{axis}_m"], v["id"]))
    assignments, routes = {}, {}
    for vehicle, partition in zip(ordering, partitions):
        agent = vehicle["id"]
        assignments[agent] = partition["id"]
        scan = lawnmower_route(partition, axis, lanes)
        routes[agent] = {"approach": [copy.deepcopy(scan[0])], "observe": scan,
                         "return": [{"east_m": vehicle["east_m"], "north_m": vehicle["north_m"]}]
                         if mission["return_required"] else []}
    routes = {agent: routes[agent] for agent in sorted(routes)}
    assignments = {agent: assignments[agent] for agent in sorted(assignments)}
    phases, semantic, by_semantic, idle = compile_execution_phases(spec, routes, assignments)
    capability = nominal_capability(spec, phases)
    coverage = nominal_coverage(region, routes, mission["observation_model"])
    if coverage["ratio"] + 1e-12 < mission["coverage_required"]:
        raise ValueError(f"nominal global coverage {coverage['ratio']:.6f} below required coverage")
    scene = {"schema_version": 1, "scenario_id": spec["task_id"],
             "origin": copy.deepcopy(scenario["origin"]), "vehicles": copy.deepcopy(scenario["vehicles"]),
             "phases": phases}
    for key in ("takeoff_alt_m", "record_hz", "max_gap_s", "min_separation_m", "timeout_s", "ready_timeout_s"):
        scene[key] = execution[key]
    scene = validate(scene)
    budget = capability["nominal_budget"]
    scene.update(task_spec=spec, family_id=spec["family_id"], semantic_plan=semantic, planning={
        "planner_name": planner["name"], "planner_version": PLANNER_VERSION,
        "allocation_method": planner["assignment"], "partition_axis": axis,
        "sweep_axis": "north" if axis == "east" else "east", "region_partitions": partitions,
        "agent_to_partition": assignments, "per_agent_reference_routes": routes,
        "semantic_to_execution_phase_map": by_semantic, "nominal_global_coverage": coverage,
        "per_agent_path_length_m": budget["per_agent_path_length_m"],
        "nominal_time_estimate_s": budget["total_time_estimate_s"],
        "nominal_min_clearance_m": capability["nominal_min_clearance_m"],
        "execution_phase_count": len(phases), "idle_padding_steps": idle,
        "feasibility_checks": capability,
        "unverified_constraints": capability["unverified_constraints"],
        "reference_time_semantics": "event_driven_no_prescribed_arrival_times"})
    return scene
