"""Scoped command, geometry and nominal resource checks; no dynamics proof."""

import math
from itertools import combinations

from .mission_schema import within_world


CAPABILITY_VERSION = "nominal_capability_v1"


def nominal_capability(spec, phases):
    """Check all independent-progress stage paths, including stationary padding.

    Time estimates explicitly include synchronized stages and lifecycle costs.
    The declared climb-rate limit supplies a lower bound, not an enforced climb
    command. The fixed allowances are uncalibrated engineering allowances, not
    a proof that the mission will finish within its budget.
    """
    from .tasks import segment_clearance

    execution, platform = spec["execution"], spec["platform"]
    world, vehicles = spec["scenario"]["world"], spec["scenario"]["vehicles"]
    previous = {v["id"]: (v["east_m"], v["north_m"]) for v in vehicles}
    speed = execution["speed_m_s"]
    required_clearance = execution["min_separation_m"] + 2 * spec["planner"]["tracking_margin_m"]
    clearance = None
    for left, right in combinations(previous, 2):
        distance = math.dist(previous[left], previous[right])
        clearance = distance if clearance is None else min(clearance, distance)
        if distance + 1e-9 < required_clearance:
            raise ValueError(f"spawn clearance {left}/{right}: {distance:.3f} m < {required_clearance:.3f} m")
    horizontal = {agent: 0.0 for agent in previous}
    barrier_wait = {agent: 0.0 for agent in previous}
    stage_estimates = []
    for phase in phases:
        current = {agent: (target["east_m"], target["north_m"])
                   for agent, target in phase["targets"].items()}
        if set(current) != set(previous):
            raise ValueError("every execution phase must contain exactly all agents")
        for agent, target in phase["targets"].items():
            if not within_world(*current[agent], world):
                raise ValueError(f"planned target outside world: {phase['name']} {agent}")
            if not world["flight_up_bounds_m"][0] <= target["up_m"] <= world["flight_up_bounds_m"][1]:
                raise ValueError("planned altitude outside world bounds")
        lengths = {agent: math.dist(previous[agent], current[agent]) for agent in current}
        for agent, length in lengths.items():
            horizontal[agent] += length
        nominal_times = {agent: length / speed + execution["waypoint_hold_s"]
                         + execution["confirmation_dwell_s"] for agent, length in lengths.items()}
        stage_time = max(nominal_times.values())
        for agent in current:
            barrier_wait[agent] += stage_time - nominal_times[agent]
        stage_estimates.append({"phase": phase["name"], "estimated_s": stage_time,
                                "per_agent_motion_m": lengths,
                                "barrier_wait_s": {agent: stage_time - value for agent, value in nominal_times.items()}})
        for left, right in combinations(current, 2):
            distance = segment_clearance(previous[left], current[left], previous[right], current[right])
            clearance = distance if clearance is None else min(clearance, distance)
            if distance + 1e-9 < required_clearance:
                raise ValueError(f"nominal phase paths too close: {phase['name']} {left}/{right}: "
                                 f"{distance:.3f} m < {required_clearance:.3f} m")
        previous = current
    # Add nominal vertical takeoff and landing distances even without a return leg.
    path_lengths = {agent: distance + 2 * execution["takeoff_alt_m"] for agent, distance in horizontal.items()}
    if any(length > platform["max_path_length_m"] for length in path_lengths.values()):
        raise ValueError("nominal full lifecycle route exceeds max_path_length_m")
    stages_s = sum(stage["estimated_s"] for stage in stage_estimates)
    takeoff_lower_bound = execution["takeoff_alt_m"] / platform["max_climb_rate_m_s"]
    lifecycle = {"takeoff_lower_bound_s": takeoff_lower_bound,
                 "takeoff_stabilization_allowance_s": 30.0, "landing_allowance_s": 30.0,
                 "ground_ready_allowance_s": execution["ready_timeout_s"],
                 "allowance_basis": "fixed uncalibrated engineering allowances; not strict upper bounds"}
    airborne_s = stages_s + takeoff_lower_bound + 60.0
    total_s = airborne_s + execution["ready_timeout_s"]
    if airborne_s + platform["reserve_time_s"] > platform["max_airborne_time_s"]:
        raise ValueError("nominal airborne estimate plus reserve exceeds max_airborne_time_s")
    if total_s > execution["timeout_s"]:
        raise ValueError("timeout_s below nominal task and lifecycle estimate")
    unverified = ["continuous-time acceleration and turn dynamics (no timed reference)",
                  "actual tracking error bounded by tracking_margin_m", "physical collision and battery model",
                  "actual climb rate and flight duration; execution evidence required"]
    return {"version": CAPABILITY_VERSION,
            "command_limits": {"pass": True, "speed_m_s": speed, "max_speed_m_s": platform["max_speed_m_s"],
                               "world_bounds_pass": True, "required_clearance_m": required_clearance,
                               "clearance_scope": "independent progress on same-phase line segments, including padding"},
            "nominal_budget": {"pass": True, "per_agent_path_length_m": path_lengths,
                               "per_agent_horizontal_path_length_m": horizontal,
                               "per_agent_nominal_barrier_wait_s": barrier_wait,
                               "stage_estimates": stage_estimates, "stage_time_estimate_s": stages_s,
                               "lifecycle_estimate": lifecycle, "airborne_time_estimate_s": airborne_s,
                               "total_time_estimate_s": total_s, "reserve_time_s": platform["reserve_time_s"],
                               "time_semantics": "nominal estimate, not an execution guarantee"},
            "nominal_min_clearance_m": clearance,
            "executed_limits": {"status": "not_verified"},
            "proxy_dynamics": {"status": "not_verified", "hard_gate": False},
            "unverified_constraints": unverified}
