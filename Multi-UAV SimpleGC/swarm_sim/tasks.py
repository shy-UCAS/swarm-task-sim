"""Explicit geometric tasks compiled to the existing event-driven AUTO backend."""

import copy
import math
import re
from itertools import combinations

from .scenario import number, validate


def point_segment(point, start, end):
    delta = [b - a for a, b in zip(start, end)]
    norm = sum(x * x for x in delta)
    u = max(0, min(1, sum((p - a) * d for p, a, d in zip(point, start, delta)) / norm)) if norm else 0
    return math.dist(point, [a + u * d for a, d in zip(start, delta)])


def segment_clearance(a, b, c, d):
    """Exact 2-D segment distance, allowing independent progress on each segment."""
    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    # Collinear disjoint segments are handled by endpoint distances.
    if cross(a, b, c) * cross(a, b, d) < 0 and cross(c, d, a) * cross(c, d, b) < 0:
        return 0.0
    return min(point_segment(a, c, d), point_segment(b, c, d),
               point_segment(c, a, b), point_segment(d, a, b))


def compile_task(spec):
    if not isinstance(spec, dict) or isinstance(spec.get("schema_version"), bool):
        raise ValueError("TaskSpec must be an object with an integer schema_version")
    if spec.get("schema_version") == 2:
        from .mission_planning import compile_shared_mission_v2
        return compile_shared_mission_v2(spec)
    return compile_task_v1(spec)


def compile_task_v1(spec):
    spec = copy.deepcopy(spec)
    unknown = set(spec) - {"schema_version", "task_id", "family_id", "origin", "vehicles", "task",
                           "takeoff_alt_m", "record_hz", "max_gap_s", "min_separation_m", "timeout_s", "ready_timeout_s"}
    if unknown:
        raise ValueError(f"unsupported TaskSpec fields: {sorted(unknown)}")
    if spec.get("schema_version") != 1:
        raise ValueError("TaskSpec schema_version must be 1")
    for key in ("task_id", "family_id"):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", spec.get(key, "")):
            raise ValueError(f"{key} must be an explicit safe identifier")
    task = spec["task"]
    kind = task["type"]
    if kind not in ("point_visit", "rectangle_patrol", "coverage_scan"):
        raise ValueError("unknown task type")
    allowed = {"type", "speed_m_s", "dwell_s", "tolerance_m"} | {
        "point_visit": {"point"}, "rectangle_patrol": {"width_m", "height_m", "cycles"},
        "coverage_scan": {"width_m", "height_m", "lane_spacing_m", "footprint_radius_m", "grid_m", "coverage_required"}}[kind]
    if set(task) - allowed:
        raise ValueError(f"unsupported task fields: {sorted(set(task) - allowed)}")
    speed = number(task.setdefault("speed_m_s", 3), "speed_m_s", 0.5, 15)
    dwell = number(task.setdefault("dwell_s", 1), "dwell_s", 0, 60)
    tolerance = number(task.setdefault("tolerance_m", 2), "tolerance_m", 0.2, 5)
    altitude = number(spec.setdefault("takeoff_alt_m", 8), "takeoff_alt_m", 3, 100)
    if kind == "point_visit":
        point = task["point"]
        route = [(number(point["east_m"], "point.east_m", -1000, 1000),
                  number(point["north_m"], "point.north_m", -1000, 1000))]
    else:
        width = number(task["width_m"], "width_m", 2 * tolerance + 0.1, 200)
        height = number(task["height_m"], "height_m", 2 * tolerance + 0.1, 200)
        if kind == "rectangle_patrol":
            cycles = number(task.setdefault("cycles", 1), "cycles", 1, 10)
            if not isinstance(cycles, int):
                raise ValueError("cycles must be integer")
            route = [(0, 0)] + [(width, 0), (width, height), (0, height), (0, 0)] * cycles
        else:
            spacing = number(task.setdefault("lane_spacing_m", 3), "lane_spacing_m", 0.5, width)
            footprint = number(task.setdefault("footprint_radius_m", 2.5), "footprint_radius_m", 0.2, 100)
            number(task.setdefault("grid_m", 1), "grid_m", 0.25, min(width, height))
            number(task.setdefault("coverage_required", 0.9), "coverage_required", 0.1, 1)
            if spacing > 2 * footprint:
                raise ValueError("lane spacing exceeds ideal footprint diameter")
            if math.ceil(width / task["grid_m"]) * math.ceil(height / task["grid_m"]) > 10000:
                raise ValueError("coverage grid exceeds 10000 cells per vehicle")
            lanes = math.ceil(width / spacing)
            route = []
            for index in range(lanes + 1):
                x = width * index / lanes
                route.extend([(x, 0), (x, height)] if index % 2 == 0 else [(x, height), (x, 0)])
    scene = {key: copy.deepcopy(value) for key, value in spec.items()
             if key in ("origin", "vehicles", "takeoff_alt_m", "record_hz", "max_gap_s", "min_separation_m",
                        "timeout_s", "ready_timeout_s")}
    scene.update(schema_version=1, scenario_id=spec["task_id"], phases=[])
    for index, (east, north) in enumerate(route):
        scene["phases"].append(dict(name=f"leg_{index:03d}", targets={v["id"]: dict(
            east_m=v["east_m"] + east, north_m=v["north_m"] + north, up_m=altitude,
            speed_m_s=speed, hold_s=dwell) for v in scene["vehicles"]}))
    scene = validate(scene)
    previous = {v["id"]: (v["east_m"], v["north_m"]) for v in scene["vehicles"]}
    distances = {v["id"]: 0.0 for v in scene["vehicles"]}
    lower_bound = 0.0
    min_clearance = None
    for phase in scene["phases"]:
        current = {agent: (t["east_m"], t["north_m"]) for agent, t in phase["targets"].items()}
        lengths = {agent: math.dist(previous[agent], current[agent]) for agent in current}
        for agent, length in lengths.items():
            distances[agent] += length
        lower_bound += max(lengths.values()) / speed + dwell
        for left, right in combinations(current, 2):
            distance = segment_clearance(previous[left], current[left], previous[right], current[right])
            min_clearance = distance if min_clearance is None else min(distance, min_clearance)
            if distance < scene["min_separation_m"]:
                raise ValueError(f"nominal phase paths too close: {phase['name']} {left}/{right}: {distance:.3f} m")
        previous = current
    if scene["timeout_s"] < lower_bound + 60:
        raise ValueError("timeout below nominal mission lower bound plus 60 s lifecycle allowance")
    scene.update(task_spec=spec, family_id=spec["family_id"], planning=dict(
        backend="AUTO", reference_time_semantics="event_driven_no_prescribed_arrival_times",
        path_length_m=distances, mission_time_lower_bound_s=lower_bound,
        nominal_phase_path_clearance_m=min_clearance,
        feasibility_scope="geometry and speed lower bound only; no dynamics, obstacles, endurance or tracking guarantee"))
    return scene


def validate_task_binding(scene):
    if "task_spec" in scene and compile_task(scene["task_spec"]) != scene:
        raise ValueError("compiled scenario differs from task_spec; edit the task and recompile")


def target_confirmation(scene, phase, agent_id):
    """Numerical control requirements; intent semantics stay outside the driver."""
    spec = scene["task_spec"]
    if spec["schema_version"] == 1:
        return dict(tolerance_m=spec["task"]["tolerance_m"], dwell_s=spec["task"]["dwell_s"], role="legacy")
    execution = spec["execution"]
    role = scene["semantic_plan"]["execution_phases"][phase["name"]]["agents"][agent_id]["role"]
    return dict(tolerance_m=execution["arrival_tolerance_m"],
                dwell_s=0 if role == "idle_padding" else execution["confirmation_dwell_s"], role=role)
