"""v3 semantic routes and sampled time-aware nominal clearance.

The old barrier compiler/capability functions are not called or modified here.
Nominal timing is a uniform-speed proxy, not a flight dynamics guarantee.
"""

import bisect
import copy
import math
from itertools import combinations

from .mission_schema import within_world
from .scenario import number, validate


ROUTE_COMPILER_VERSION = "semantic_phase_route_v1"
CAPABILITY_VERSION = "time_aware_route_capability_v1"
ZERO_LENGTH_EPSILON_M = .05
MAX_SAMPLE_STEP_M = .5
MAX_ROUTE_WAYPOINTS = 100


def _xyz(point):
    return (point["east_m"], point["north_m"], point["up_m"])


def clean_route(start, points, altitude):
    """Keep the first point in each sub-epsilon cluster and original indices."""
    previous, route, indices, removed = start, [], [], []
    for index, point in enumerate(points):
        point = dict(east_m=float(point["east_m"]), north_m=float(point["north_m"]), up_m=float(altitude))
        if math.dist(_xyz(previous), _xyz(point)) < ZERO_LENGTH_EPSILON_M:
            removed.append(index)
            continue
        route.append(point)
        indices.append(index)
        previous = point
    if len(route) > MAX_ROUTE_WAYPOINTS:
        raise ValueError("continuous route exceeds limit of 100 waypoints per agent per phase")
    return route, indices, removed


def sample_route(start, route, speed, step=MAX_SAMPLE_STEP_M):
    """Return arc-length samples plus exact waypoint arrival times.

    Every segment endpoint is retained; subdivisions have length <= step.
    A no-op has one sample at t=0 and a separate stationary time interval.
    """
    number(speed, "nominal speed", .01, 100)
    number(step, "sampling step", .001, MAX_SAMPLE_STEP_M)
    samples, waypoint_times, total = [(0.0, _xyz(start))], [], 0.0
    previous = start
    for point in route:
        distance = math.dist(_xyz(previous), _xyz(point))
        if distance < ZERO_LENGTH_EPSILON_M:
            raise ValueError("continuous route contains a segment below epsilon 0.05 m")
        pieces = max(1, math.ceil(distance / step))
        for index in range(1, pieces + 1):
            fraction = index / pieces
            position = tuple(a + fraction * (b - a) for a, b in zip(_xyz(previous), _xyz(point)))
            samples.append(((total + distance * fraction) / speed, position))
        total += distance
        waypoint_times.append(total / speed)
        previous = point
    return samples, waypoint_times, total


def time_aware_phase_clearance(starts, routes, speed_m_s, required_clearance_m, timing_tolerance,
                             terminal_hold_s=0.0, confirmation_dwell_s=0.0):
    """Check all sampled point pairs within tau, including stationary intervals.

    Endpoint/no-op occupancy extends until the slowest agent finishes motion,
    terminal hold and confirmation. Interval comparisons account for every
    possible endpoint time, rather than assigning the endpoint only its arrival.
    """
    if not starts or set(starts) != set(routes):
        raise ValueError("time-aware routes and starts must identify all agents")
    number(required_clearance_m, "required clearance", .1, 2000)
    number(terminal_hold_s, "terminal_hold_s", 0, 60)
    number(confirmation_dwell_s, "confirmation_dwell_s", 0, 60)
    number(timing_tolerance["min_s"], "async_timing_tolerance.min_s", 0, 3600)
    number(timing_tolerance["fraction_of_phase"], "async_timing_tolerance.fraction_of_phase", 0, 1)
    sampled, arrivals, lengths = {}, {}, {}
    for agent in starts:
        sampled[agent], arrivals[agent], lengths[agent] = sample_route(starts[agent], routes[agent], speed_m_s)
    motion = {agent: lengths[agent] / speed_m_s for agent in starts}
    completion = {agent: motion[agent] + (terminal_hold_s if routes[agent] else 0) + confirmation_dwell_s for agent in starts}
    motion_duration, duration = max(motion.values()), max(completion.values())
    tau = max(timing_tolerance["min_s"], timing_tolerance["fraction_of_phase"] * duration)
    minimum, closest, checked_pairs = None, None, 0

    def consider(left, right, ta, pa, tb, pb, kind):
        nonlocal minimum, closest, checked_pairs
        checked_pairs += 1
        distance = math.dist(pa, pb)
        if minimum is None or distance < minimum:
            minimum = distance
            closest = dict(agents=[left, right], nominal_times_s=[ta, tb], distance_m=distance, kind=kind)
        if distance + 1e-9 < required_clearance_m:
            raise ValueError(f"time-aware nominal routes too close: {left}/{right} {distance:.3f} m < "
                             f"{required_clearance_m:.3f} m; times {ta:.3f}/{tb:.3f}s, tau={tau:.3f}s ({kind})")

    for left, right in combinations(sorted(starts), 2):
        right_times = [t for t, _ in sampled[right]]
        for ta, pa in sampled[left]:
            lo = bisect.bisect_left(right_times, ta - tau - 1e-12)
            hi = bisect.bisect_right(right_times, ta + tau + 1e-12)
            for tb, pb in sampled[right][lo:hi]:
                consider(left, right, ta, pa, tb, pb, "moving_sample_pair")
        for stationary, moving in ((left, right), (right, left)):
            begin, endpoint = sampled[stationary][-1]
            for stamp, position in sampled[moving]:
                if begin - tau - 1e-12 <= stamp <= duration + tau + 1e-12:
                    occupied_time = min(duration, max(begin, stamp))
                    consider(stationary, moving, occupied_time, endpoint, stamp, position, "terminal_or_no_op_interval")
        # Both agents remain at their terminal point through the common barrier.
        consider(left, right, duration, sampled[left][-1][1], duration, sampled[right][-1][1], "both_stationary")
    return dict(duration_s=duration, motion_duration_s=motion_duration,
        per_agent_arrival_s=motion, per_agent_waypoint_arrival_s=arrivals,
        per_agent_completion_s=completion, per_agent_path_length_m=lengths,
        tau_s=tau, tau_basis="max(min_s, fraction_of_phase * duration_s); duration includes terminal hold and confirmation",
        timing_tolerance=copy.deepcopy(timing_tolerance),
        terminal_hold_s=terminal_hold_s, confirmation_dwell_s=confirmation_dwell_s,
        max_sample_step_m=MAX_SAMPLE_STEP_M, sample_counts={a: len(v) for a, v in sampled.items()},
        required_clearance_m=required_clearance_m, nominal_min_clearance_m=minimum,
        closest_pair=closest, checked_point_pairs=checked_pairs,
        endpoint_occupancy="[per_agent_arrival_s, duration_s]; no-op occupies start point throughout phase")


def compile_route_phases(spec, plan, intent):
    execution = spec["execution"]
    previous = {v["id"]: dict(east_m=v["east_m"], north_m=v["north_m"], up_m=execution["takeoff_alt_m"])
                for v in spec["scenario"]["vehicles"]}
    phases, mapping, by_semantic, removed = [], {}, {}, {}
    no_ops = {agent: 0 for agent in previous}
    semantics = [phase for phase in intent.semantic_phases if phase != "return" or spec["mission"]["return_required"]]
    for index, semantic in enumerate(semantics):
        name = f"p{index:02d}_{semantic}"
        routes, roles = {}, {}
        removed[name] = {}
        for agent in previous:
            start = copy.deepcopy(previous[agent])
            route, indices, discarded = clean_route(start, plan.routes[agent][semantic], execution["takeoff_alt_m"])
            routes[agent] = route
            terminal = copy.deepcopy(route[-1] if route else start)
            roles[agent] = dict(role=semantic if route else "hold_no_op", service_enabled=bool(route) and semantic in intent.service_phases,
                partition_id=plan.assignments[agent], waypoint_planner_indices=indices, start_point=start, terminal_point=terminal)
            removed[name][agent] = discarded
            no_ops[agent] += not bool(route)
            previous[agent] = terminal
        phases.append(dict(name=name, semantic_phase=semantic, routes=routes, speed_m_s=execution["speed_m_s"],
                           terminal_hold_s=execution["terminal_hold_s"]))
        mapping[name] = dict(semantic_phase=semantic, agents=roles)
        by_semantic[semantic] = [name]
    return phases, dict(version="semantic_route_plan_v1", execution_phases=mapping,
        service_activation="registered service phases and nonempty routes only; no-op disabled",
        window_source="execution_events + trajectory_arrival + compiled_semantic_plan", zero_length_epsilon_m=ZERO_LENGTH_EPSILON_M), by_semantic, no_ops, removed


def nominal_route_capability(spec, phases, semantic):
    execution, scenario = spec["execution"], spec["scenario"]
    platform, world = scenario["platform"], scenario["world"]
    required = execution["min_separation_m"] + 2 * spec["planner"]["params"].get("tracking_margin_m", 0)
    previous = {v["id"]: dict(east_m=v["east_m"], north_m=v["north_m"], up_m=execution["takeoff_alt_m"])
                for v in scenario["vehicles"]}
    distances = {agent: 0.0 for agent in previous}
    # Reject nominal resource violations before expanding the sampled routes.
    for phase in phases:
        for agent, route in phase["routes"].items():
            for point in route:
                if not within_world(point["east_m"], point["north_m"], world):
                    raise ValueError(f"planned target outside world: {phase['name']} {agent}")
                if not world["flight_up_bounds_m"][0] <= point["up_m"] <= world["flight_up_bounds_m"][1]:
                    raise ValueError("planned altitude outside world bounds")
                distances[agent] += math.dist(_xyz(previous[agent]), _xyz(point))
                previous[agent] = point
    path_lengths = {agent: value + 2 * execution["takeoff_alt_m"] for agent, value in distances.items()}
    if any(value > platform["max_path_length_m"] for value in path_lengths.values()):
        raise ValueError("nominal full lifecycle route exceeds max_path_length_m")
    timing, minimum, stage_estimates = {}, None, []
    barrier = {agent: 0.0 for agent in previous}
    for phase in phases:
        starts = {agent: role["start_point"] for agent, role in semantic["execution_phases"][phase["name"]]["agents"].items()}
        report = time_aware_phase_clearance(starts, phase["routes"], phase["speed_m_s"], required,
            execution["async_timing_tolerance"], phase["terminal_hold_s"], execution["confirmation_dwell_s"])
        timing[phase["name"]] = report
        if report["nominal_min_clearance_m"] is not None:
            minimum = report["nominal_min_clearance_m"] if minimum is None else min(minimum, report["nominal_min_clearance_m"])
        waits = {agent: report["duration_s"] - finish for agent, finish in report["per_agent_completion_s"].items()}
        for agent, delay in waits.items():
            barrier[agent] += delay
        stage_estimates.append(dict(phase=phase["name"], estimated_s=report["duration_s"],
                                   per_agent_motion_m=report["per_agent_path_length_m"], barrier_wait_s=waits))
    stage_time = sum(item["estimated_s"] for item in stage_estimates)
    climb = execution["takeoff_alt_m"] / platform["max_climb_rate_m_s"]
    airborne, total = stage_time + climb + 60, stage_time + climb + 60 + execution["ready_timeout_s"]
    if airborne + platform["reserve_time_s"] > platform["max_airborne_time_s"]:
        raise ValueError("nominal airborne estimate plus reserve exceeds max_airborne_time_s")
    if total > execution["timeout_s"]:
        raise ValueError("timeout_s below nominal task and lifecycle estimate")
    return dict(version=CAPABILITY_VERSION,
        command_limits=dict(pass_=True, speed_m_s=execution["speed_m_s"], max_speed_m_s=platform["max_speed_m_s"],
            world_bounds_pass=True, required_clearance_m=required, clearance_scope="sampled points within per-phase tau plus endpoint/no-op intervals"),
        nominal_budget=dict(pass_=True, per_agent_path_length_m=path_lengths, per_agent_horizontal_path_length_m=distances,
            per_agent_nominal_barrier_wait_s=barrier, stage_estimates=stage_estimates, stage_time_estimate_s=stage_time,
            lifecycle_estimate=dict(takeoff_lower_bound_s=climb, takeoff_stabilization_allowance_s=30.0,
                landing_allowance_s=30.0, ground_ready_allowance_s=execution["ready_timeout_s"],
                allowance_basis="fixed uncalibrated engineering allowances; not strict upper bounds"),
            airborne_time_estimate_s=airborne, total_time_estimate_s=total, reserve_time_s=platform["reserve_time_s"],
            time_semantics="uniform-speed per-phase model plus terminal hold/confirmation; not a flight guarantee"),
        nominal_min_clearance_m=minimum, nominal_phase_timing=timing,
        executed_limits=dict(status="not_verified"), proxy_dynamics=dict(status="not_verified", hard_gate=False),
        unverified_constraints=["uniform-speed timing versus actual acceleration and cornering", "actual timing deviation bounded by tau",
            "continuous paths between 0.5 m samples", "tracking error bounded by tracking_margin_m", "physical collision/battery model",
            "actual climb rate and flight duration; execution evidence required"])


def compile_continuous_mission(spec, plan, intent, planner):
    phases, semantic, by_semantic, no_ops, removed = compile_route_phases(spec, plan, intent)
    capability = nominal_route_capability(spec, phases, semantic)
    # Match established artifact vocabulary; Python's keyword syntax cannot use pass.
    capability["command_limits"]["pass"] = capability["command_limits"].pop("pass_")
    capability["nominal_budget"]["pass"] = capability["nominal_budget"].pop("pass_")
    budget = capability["nominal_budget"]
    planning = dict(plan.diagnostics)
    if intent.name == "reconnaissance":
        from .mission_planning import nominal_coverage
        observe = next(phase for phase in phases if phase["semantic_phase"] == "observe")
        active_routes = {agent: {"observe": [semantic["execution_phases"][observe["name"]]["agents"][agent]["start_point"], *route]}
                         for agent, route in observe["routes"].items() if route}
        region = next(r for r in spec["scenario"]["regions"] if r["id"] == spec["mission"]["target_region_id"])
        coverage = nominal_coverage(region, active_routes, spec["mission"]["intent_params"]["observation_model"])
        if coverage["ratio"] + 1e-12 < spec["mission"]["intent_params"]["coverage_required"]:
            raise ValueError("cleaned continuous route nominal coverage below required coverage")
        planning["nominal_global_coverage"] = coverage
    planning.update(planner_name=planner.name, planner_version=planner.version, route_compiler_version=ROUTE_COMPILER_VERSION,
        agent_to_partition=plan.assignments, per_agent_reference_routes=plan.routes,
        semantic_to_execution_phase_map=by_semantic, per_agent_path_length_m=budget["per_agent_path_length_m"],
        nominal_time_estimate_s=budget["total_time_estimate_s"], nominal_min_clearance_m=capability["nominal_min_clearance_m"],
        execution_phase_count=len(phases), idle_padding_steps=no_ops, hold_no_op_phases=no_ops,
        removed_planner_waypoint_indices=removed, feasibility_checks=capability,
        nominal_phase_timing=capability["nominal_phase_timing"], unverified_constraints=capability["unverified_constraints"],
        reference_time_semantics="phase-relative uniform-speed arrivals with bounded asynchronous time tolerance")
    scene = dict(schema_version=2, control_mode=ROUTE_COMPILER_VERSION, scenario_id=spec["task_id"],
        origin=copy.deepcopy(spec["scenario"]["origin"]), vehicles=copy.deepcopy(spec["scenario"]["vehicles"]),
        phases=phases, task_spec=spec, family_id=spec["family_id"], family_scheme=spec["family_scheme"],
        semantic_plan=semantic, planning=planning)
    for key in ("takeoff_alt_m", "record_hz", "max_gap_s", "min_separation_m", "timeout_s", "ready_timeout_s"):
        scene[key] = spec["execution"][key]
    return validate(scene)
