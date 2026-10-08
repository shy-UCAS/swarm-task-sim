"""Additional v0.6 route geometries, retaining existing semantic validators.

The ordinary compiler checks every route and may reject these geometries.
There is no fallback to a different pattern, clearance relaxation or resampling.
"""

import copy
import math
import itertools

from .registry import PlannerSpec, PlanResult
from .mission_schema import _object, _numeric


def _axis(spec, region):
    requested = spec["planner"]["params"]["partition_axis"]
    if requested != "auto":
        return requested
    vehicles = spec["scenario"]["vehicles"]
    east = sum(v["east_m"] for v in vehicles)/len(vehicles) - region["min_east_m"] - region["width_m"]/2
    north = sum(v["north_m"] for v in vehicles)/len(vehicles) - region["min_north_m"] - region["height_m"]/2
    return "east" if abs(north) >= abs(east) else "north"


def normalize_interleaved(params, spec):
    from .reconnaissance import normalize_planner
    return normalize_planner(params, spec)


def interleaved_routes(spec):
    from .mission_planning import lawnmower_route, nominal_coverage
    region = next(r for r in spec["scenario"]["regions"] if r["id"] == spec["mission"]["target_region_id"])
    axis = _axis(spec, region)
    vehicles = sorted(spec["scenario"]["vehicles"], key=lambda v: (v[f"{axis}_m"], v["id"]))
    n = len(vehicles)
    size = region["width_m" if axis == "east" else "height_m"]
    k = max(2, math.ceil(size/(n*spec["planner"]["params"]["lane_spacing_m"])))
    dimension = "width_m" if axis == "east" else "height_m"
    coordinate = f"min_{axis}_m"
    strips = [dict(region, **{coordinate: region[coordinate]+size*index/(n*k),
                             dimension: size/(n*k)}, id=f"{region['id']}_fine_{index:03d}")
              for index in range(n*k)]
    routes, assignments = {}, {}
    for index, vehicle in enumerate(vehicles):
        lanes = list(range(index, n*k, n))
        scan = []
        for ordinal, lane in enumerate(lanes):
            points = lawnmower_route(strips[lane], axis, 1)
            scan.extend(points if ordinal % 2 == 0 else reversed(points))
        agent = vehicle["id"]
        routes[agent] = dict(approach=[copy.deepcopy(scan[0])], observe=scan,
            **{"return": [dict(east_m=vehicle["east_m"], north_m=vehicle["north_m"])]
               if spec["mission"]["return_required"] else []})
        assignments[agent] = "interleaved_" + "_".join(map(str, lanes))
    coverage = nominal_coverage(region, routes, spec["mission"]["intent_params"]["observation_model"])
    if coverage["ratio"] + 1e-12 < spec["mission"]["intent_params"]["coverage_required"]:
        raise ValueError("interleaved nominal coverage below required coverage")
    return PlanResult(routes, assignments, dict(allocation_method="interleaved_i_plus_N", partition_axis=axis,
        sweep_axis="north" if axis == "east" else "east", interleaved_k=k, region_partitions=strips,
        nominal_global_coverage=coverage))


def normalize_bidirectional(params, spec):
    result = copy.deepcopy(params)
    _object(result, "bidirectional planner.params", ("tracking_margin_m", "lane_offset_m"))
    _numeric(result, "tracking_margin_m", "bidirectional planner.params", 0, 100)
    _numeric(result, "lane_offset_m", "bidirectional planner.params", 5, 30)
    if spec["execution"].get("control_mode") != "semantic_phase_route_v1":
        raise ValueError("bidirectional patrol requires semantic_phase_route_v1")
    required = spec["execution"]["min_separation_m"] + 2 * result["tracking_margin_m"]
    if 2 * result["lane_offset_m"] < max(10.0, required):
        raise ValueError("bidirectional lane gap below required clearance or 10 m")
    return result


def bidirectional_routes(spec):
    from .patrol import _ring, _ring_point, _lap_route, _phase_check
    region = next(r for r in spec["scenario"]["regions"] if r["id"] == spec["mission"]["target_region_id"])
    vehicles = sorted(spec["scenario"]["vehicles"], key=lambda v: v["id"])
    count = len(vehicles)
    offset = spec["planner"]["params"]["lane_offset_m"]
    if min(region["width_m"], region["height_m"]) <= 2*offset:
        raise ValueError("bidirectional inner ring has nonpositive width or height")
    entries, loops, lane_ids = [], [], []
    for group, direction, signed_offset in ((0, "cw", -offset), (1, "ccw", offset)):
        ring = dict(region, min_east_m=region["min_east_m"]-signed_offset,
            min_north_m=region["min_north_m"]-signed_offset,
            width_m=region["width_m"]+2*signed_offset, height_m=region["height_m"]+2*signed_offset)
        corners, marks = _ring(ring, direction)
        members = len(range(group, count, 2))
        for index in range(members):
            arc = ((index+.5)/members)*marks[-1]
            entries.append(_ring_point(corners, marks, arc))
            loops.append(_lap_route(corners, marks, arc, spec["mission"]["intent_params"]["laps"]))
            lane_ids.append("inner_cw" if group == 0 else "outer_ccw")
    altitude = spec["execution"]["takeoff_alt_m"]
    homes = {v["id"]: dict(east_m=v["east_m"], north_m=v["north_m"], up_m=altitude) for v in vehicles}
    required = spec["execution"]["min_separation_m"] + 2*spec["planner"]["params"]["tracking_margin_m"]
    feasible, reasons = [], []
    for assignment in itertools.permutations(range(count)):
        routes = {}
        for vehicle, lane in zip(vehicles, assignment):
            routes[vehicle["id"]] = dict(approach=[entries[lane]], patrol=loops[lane],
                **{"return": [{k: vehicle[k] for k in ("east_m", "north_m")}] if spec["mission"]["return_required"] else []})
        starts = homes
        try:
            for phase in ("approach", "patrol", "return"):
                if phase == "return" and not spec["mission"]["return_required"]:
                    continue
                phase_routes = {a: [dict(p, up_m=altitude) for p in route[phase]] for a, route in routes.items()}
                _phase_check(starts, phase_routes, spec["execution"], required)
                starts = {a: points[-1] if points else starts[a] for a, points in phase_routes.items()}
        except ValueError as exc:
            reasons.append(str(exc))
            continue
        cost = sum(math.dist((v["east_m"], v["north_m"]), (entries[i]["east_m"], entries[i]["north_m"]))
                   for v, i in zip(vehicles, assignment))
        feasible.append((cost, assignment, routes))
    if not feasible:
        raise ValueError("bidirectional no clearance-feasible assignment: " + (reasons[0] if reasons else "no agents"))
    _, assignment, routes = min(feasible, key=lambda item: (item[0], item[1]))
    return PlanResult(routes, {v["id"]: lane_ids[i] for v, i in zip(vehicles, assignment)},
        dict(patrol_direction="bidirectional", lane_offset_m=offset, lateral_lane_gap_m=2*offset,
             perimeter_m=2*(region["width_m"]+region["height_m"]),
             semantic_limitation="unchanged 3 m perimeter visit corridor excludes offset lanes; report at pause A"))


interleaved_planner = PlannerSpec("interleaved_lanes_v1", "interleaved_lanes_v1", normalize_interleaved, interleaved_routes)
bidirectional_planner = PlannerSpec("bidirectional_lanes_v1", "bidirectional_lanes_v1", normalize_bidirectional, bidirectional_routes)
