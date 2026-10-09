"""The v0.6 A2 strip-local reconnaissance route alternative.

Allocation is exactly the existing equal-strip allocation. Only the scan
within each assigned strip changes, and the original coverage/clearance
checks remain mandatory. Retired crossing-lane strategies are not available.
"""

import copy

from .registry import PlannerSpec, PlanResult


def _axis(spec, region):
    requested = spec["planner"]["params"]["partition_axis"]
    if requested != "auto":
        return requested
    vehicles = spec["scenario"]["vehicles"]
    east = sum(v["east_m"] for v in vehicles)/len(vehicles) - region["min_east_m"] - region["width_m"]/2
    north = sum(v["north_m"] for v in vehicles)/len(vehicles) - region["min_north_m"] - region["height_m"]/2
    return "east" if abs(north) >= abs(east) else "north"


def normalize_spiral(params, spec):
    from .reconnaissance import normalize_planner
    return normalize_planner(params, spec)


def rectangular_spiral_route(partition, axis, spacing_m, cross_inset_m):
    """Walk an axis-aligned rectangle inward; narrow final rings are closed.

    A cross-strip inset of half the required clearance prevents neighboring
    scan paths from becoming too close under arbitrary relative timing.
    Longitudinal inset is half the existing lane spacing. Coverage is checked
    independently against the unchanged sensor footprint and global grid.
    """
    along = "north" if axis == "east" else "east"
    cross_size = partition["width_m" if axis == "east" else "height_m"]
    along_size = partition["height_m" if axis == "east" else "width_m"]
    left, right = cross_inset_m, cross_size-cross_inset_m
    bottom, top = spacing_m/2, along_size-spacing_m/2
    if left >= right or bottom >= top:
        raise ValueError("rectangular spiral has no interior after required clearance/coverage insets")
    points = [(left, bottom)]
    while True:
        points.extend(((left, top), (right, top), (right, bottom)))
        if min(right-left, top-bottom) <= 2*spacing_m:
            points.append((left, bottom))
            break
        points.extend(((left+spacing_m, bottom), (left+spacing_m, bottom+spacing_m)))
        left, right = left+spacing_m, right-spacing_m
        bottom, top = bottom+spacing_m, top-spacing_m
    return [{f"{axis}_m": partition[f"min_{axis}_m"]+cross,
             f"{along}_m": partition[f"min_{along}_m"]+longitudinal}
            for cross, longitudinal in points]


def rectangular_spiral_routes(spec):
    from .mission_planning import partition_region, nominal_coverage
    scenario, mission, execution = spec["scenario"], spec["mission"], spec["execution"]
    params = spec["planner"]["params"]
    region = next(r for r in scenario["regions"] if r["id"] == mission["target_region_id"])
    axis = _axis(spec, region)
    vehicles = sorted(scenario["vehicles"], key=lambda v: (v[f"{axis}_m"], v["id"]))
    partitions = partition_region(region, len(vehicles), axis)
    required = execution["min_separation_m"] + 2*params["tracking_margin_m"]
    routes, assignments = {}, {}
    for vehicle, partition in zip(vehicles, partitions):
        scan = rectangular_spiral_route(partition, axis, params["lane_spacing_m"], required/2)
        agent = vehicle["id"]
        assignments[agent] = partition["id"]
        routes[agent] = dict(approach=[copy.deepcopy(scan[0])], observe=scan,
            **{"return": [dict(east_m=vehicle["east_m"], north_m=vehicle["north_m"])]
               if mission["return_required"] else []})
    coverage = nominal_coverage(region, routes, mission["intent_params"]["observation_model"])
    if coverage["ratio"] + 1e-12 < mission["intent_params"]["coverage_required"]:
        raise ValueError("rectangular spiral nominal coverage below required coverage")
    return PlanResult({agent: routes[agent] for agent in sorted(routes)},
        {agent: assignments[agent] for agent in sorted(assignments)},
        dict(allocation_method=params["assignment"], partition_axis=axis,
             sweep_axis="north" if axis == "east" else "east", region_partitions=partitions,
             scan_geometry="rectangular_spiral_inward", cross_strip_inset_m=required/2,
             along_strip_inset_m=params["lane_spacing_m"]/2, inward_step_m=params["lane_spacing_m"],
             nominal_global_coverage=coverage))


rectangular_spiral_planner = PlannerSpec("equal_strip_rectangular_spiral_v1", "equal_strip_rectangular_spiral_v1",
                                        normalize_spiral, rectangular_spiral_routes)
