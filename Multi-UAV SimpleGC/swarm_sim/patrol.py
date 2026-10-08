"""Versioned perimeter-patrol intent and its one supported route strategy."""

import copy
import itertools
import math
import random
from collections import Counter

from .generation import canonical_hash
from .mission_schema import _enum, _numeric, _object
from .registry import IntentSpec, PlannerSpec, PlanResult
from .route_planning import (ZERO_LENGTH_EPSILON_M, clean_route, patrol_spacing_prefilter,
                             time_aware_phase_clearance)


PLANNER_VERSION = "staggered_same_loop_v1"
VALIDATOR_VERSION = "perimeter_revisit_v1"
_EPS = 1e-9


def normalize_params(params):
    result = copy.deepcopy(params)
    _object(result, "patrol intent_params", ("objective", "laps", "standoff_m",
        "segment_length_m", "visit_radius_m", "max_revisit_gap_factor"))
    _enum(result, "objective", "patrol intent_params", ("perimeter_patrol",))
    if type(result["laps"]) is not int or result["laps"] not in (2, 3):
        raise ValueError("patrol intent_params.laps must be integer 2 or 3")
    for key, expected in (("standoff_m", 0.), ("segment_length_m", 5.),
                          ("visit_radius_m", 3.), ("max_revisit_gap_factor", 2.)):
        _numeric(result, key, "patrol intent_params", 0, 100)
        if result[key] != expected:
            raise ValueError(f"patrol intent_params.{key} must be {expected:g} in v0.5")
    return result


def normalize_planner(params, spec):
    result = copy.deepcopy(params)
    _object(result, "patrol planner.params", ("tracking_margin_m",), optional=("tracking_margin_m",))
    result.setdefault("tracking_margin_m", 0.)
    _numeric(result, "tracking_margin_m", "patrol planner.params", 0, 100)
    if spec["execution"].get("control_mode") != "semantic_phase_route_v1":
        raise ValueError("patrol requires semantic_phase_route_v1")
    return result


def _perimeter(region):
    return 2. * (region["width_m"] + region["height_m"])


def _ring(region, direction):
    west, south = region["min_east_m"], region["min_north_m"]
    east, north = west + region["width_m"], south + region["height_m"]
    corners = ([(west, south), (west, north), (east, north), (east, south)]
               if direction == "cw" else
               [(west, south), (east, south), (east, north), (west, north)])
    lengths = [math.dist(corners[index], corners[(index + 1) % 4]) for index in range(4)]
    marks = [0.]
    for length in lengths:
        marks.append(marks[-1] + length)
    return corners, marks


def _ring_point(corners, marks, arc):
    perimeter = marks[-1]
    value = arc % perimeter
    for index in range(4):
        if value <= marks[index + 1] + _EPS:
            fraction = min(1., max(0., (value - marks[index]) / (marks[index + 1] - marks[index])))
            first, second = corners[index], corners[(index + 1) % 4]
            return dict(east_m=first[0] + fraction * (second[0] - first[0]),
                        north_m=first[1] + fraction * (second[1] - first[1]))
    raise AssertionError("invalid perimeter arc")


def _entry_arcs(rng, marks, count):
    """Draw one reference; keep its P/N offsets away from sub-epsilon legs."""
    perimeter = marks[-1]
    for _ in range(100):
        reference = rng.random() * perimeter
        arcs = [(reference + index * perimeter / count) % perimeter for index in range(count)]
        if all(min(min(abs(arc - corner), perimeter - abs(arc - corner)) for corner in marks[:-1])
               >= ZERO_LENGTH_EPSILON_M + _EPS for arc in arcs):
            return reference, arcs
    raise ValueError("patrol_entry_reference_sampling_exhausted")


def _lap_route(corners, marks, entry_arc, laps):
    perimeter = marks[-1]
    entry = _ring_point(corners, marks, entry_arc)
    # Each full circuit ends exactly at the entry, including a non-corner entry.
    route = []
    for lap in range(laps):
        low, high = entry_arc + lap * perimeter, entry_arc + (lap + 1) * perimeter
        route.extend(_ring_point(corners, marks, mark) for mark in sorted(
            mark + turn * perimeter for turn in range(laps + 1) for mark in marks[1:]
            if low + _EPS < mark + turn * perimeter < high - _EPS))
        route.append(dict(entry))
    return route


def _required_clearance(spec):
    return (spec["execution"]["min_separation_m"]
            + 2 * spec["planner"]["params"]["tracking_margin_m"])


def _patrol_tau(spec, perimeter, laps):
    execution = spec["execution"]
    duration = (laps * perimeter / execution["speed_m_s"]
                + execution["terminal_hold_s"] + execution["confirmation_dwell_s"])
    timing = execution["async_timing_tolerance"]
    proportional = timing["fraction_of_phase"] * duration
    if "max_s" in timing:
        proportional = min(proportional, timing["max_s"])
    return max(timing["min_s"], proportional), duration


def _crosses(a, b, c, d):
    def turn(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    ab_c, ab_d, cd_a, cd_b = turn(a, b, c), turn(a, b, d), turn(c, d, a), turn(c, d, b)
    if abs(ab_c) <= _EPS and abs(ab_d) <= _EPS:
        return (max(min(a[0], b[0]), min(c[0], d[0])) <= min(max(a[0], b[0]), max(c[0], d[0])) + _EPS
                and max(min(a[1], b[1]), min(c[1], d[1])) <= min(max(a[1], b[1]), max(c[1], d[1])) + _EPS)
    return ab_c * ab_d <= _EPS and cd_a * cd_b <= _EPS


def _approach_crossings(vehicles, assignment, entries):
    segments = [((vehicle["east_m"], vehicle["north_m"]),
                 (entries[index]["east_m"], entries[index]["north_m"]))
                for vehicle, index in zip(vehicles, assignment)]
    return sum(_crosses(*left, *right) for left, right in itertools.combinations(segments, 2))


def _phase_check(starts, routes, execution, clearance):
    return time_aware_phase_clearance(starts, routes, execution["speed_m_s"], clearance,
        execution["async_timing_tolerance"], execution["terminal_hold_s"],
        execution["confirmation_dwell_s"])


def plan_routes(spec):
    mission, scenario, execution = spec["mission"], spec["scenario"], spec["execution"]
    vehicles = sorted(scenario["vehicles"], key=lambda vehicle: vehicle["id"])
    count = len(vehicles)
    if not 2 <= count <= 4:
        raise ValueError("patrol supports 2 to 4 active vehicles")
    region = next(region for region in scenario["regions"] if region["id"] == mission["target_region_id"])
    laps = mission["intent_params"]["laps"]
    perimeter = _perimeter(region)
    speed = execution["speed_m_s"]
    if laps == 3 and 3 * perimeter / speed > 180 + _EPS:
        raise ValueError("patrol_laps_nominal_duration_exceeds_180s: select 2 laps before compiling TaskSpec")
    # Domain separation keeps direction/reference independent of the laps draw
    # performed by the generation profile with this same task seed.
    rng = random.Random(int(canonical_hash(["patrol_ring_geometry_v1", spec["seed"]])[:16], 16))
    direction = rng.choice(("cw", "ccw"))
    corners, marks = _ring(region, direction)
    reference, entry_arcs = _entry_arcs(rng, marks, count)
    entries = [_ring_point(corners, marks, arc) for arc in entry_arcs]
    tau, patrol_duration = _patrol_tau(spec, perimeter, laps)
    clearance = _required_clearance(spec)
    prefilter = patrol_spacing_prefilter(perimeter, count, speed, tau, clearance)
    if not prefilter["passed"]:
        raise ValueError("patrol_spacing_prefilter: arc spacing below v*tau + required clearance + 2 m; "
                         f"P/N={prefilter['nominal_spacing_m']:.6f}, "
                         f"required={prefilter['minimum_spacing_m']:.6f}")
    altitude = execution["takeoff_alt_m"]
    homes = {vehicle["id"]: dict(east_m=vehicle["east_m"], north_m=vehicle["north_m"], up_m=altitude)
             for vehicle in vehicles}
    lap_routes = [_lap_route(corners, marks, arc, laps) for arc in entry_arcs]
    rejection_counts = Counter()
    feasible = []
    # A cleaned no-op approach leaves the vehicle at its home, not at its
    # assigned entry. In that case patrol starts are assignment-dependent and
    # each assignment must retain its own full checker call.
    patrol_cache_eligible = all(
        math.dist((vehicle["east_m"], vehicle["north_m"]),
                  (entry["east_m"], entry["north_m"])) >= ZERO_LENGTH_EPSILON_M
        for vehicle in vehicles for entry in entries)
    patrol_cache = None
    patrol_full_checks = patrol_cache_reuses = patrol_selected_rechecks = 0
    for assignment in itertools.permutations(range(count)):
        routes = {}
        for vehicle, entry_index in zip(vehicles, assignment):
            agent = vehicle["id"]
            approach, _, _ = clean_route(homes[agent], [entries[entry_index]], altitude)
            patrol, _, _ = clean_route(approach[-1] if approach else homes[agent],
                                      lap_routes[entry_index], altitude)
            terminal = patrol[-1] if patrol else (approach[-1] if approach else homes[agent])
            returning, _, _ = clean_route(terminal, [homes[agent]], altitude) if mission["return_required"] else ([], [], [])
            routes[agent] = {"approach": approach, "patrol": patrol, "return": returning}
        starts = dict(homes)
        reports = {}
        for phase_name in ("approach", "patrol", "return"):
            if phase_name == "return" and not mission["return_required"]:
                continue
            phase_routes = {agent: route[phase_name] for agent, route in routes.items()}
            if phase_name == "patrol" and patrol_cache_eligible and patrol_cache is not None:
                patrol_cache_reuses += 1
                if patrol_cache["failure"] is not None:
                    rejection_counts[f"patrol:{patrol_cache['failure']}"] += 1
                    break
                reports[phase_name] = patrol_cache["report"]
                starts = {agent: (points[-1] if points else starts[agent])
                          for agent, points in phase_routes.items()}
                continue
            try:
                if phase_name == "patrol":
                    patrol_full_checks += 1
                reports[phase_name] = _phase_check(starts, phase_routes, execution, clearance)
            except ValueError as exc:
                reason = str(exc).split(":", 1)[0]
                if phase_name == "patrol" and patrol_cache_eligible:
                    patrol_cache = dict(assignment=assignment, failure=reason, report=None)
                rejection_counts[f"{phase_name}:{reason}"] += 1
                break
            if phase_name == "patrol" and patrol_cache_eligible:
                patrol_cache = dict(assignment=assignment, failure=None,
                                    report=reports[phase_name])
            starts = {agent: (points[-1] if points else starts[agent]) for agent, points in phase_routes.items()}
        else:
            approach_distance = sum(math.dist((vehicle["east_m"], vehicle["north_m"]),
                                             (entries[index]["east_m"], entries[index]["north_m"]))
                                    for vehicle, index in zip(vehicles, assignment))
            feasible.append((approach_distance, assignment, routes, reports))
    if not feasible:
        detail = ", ".join(f"{key}={count}" for key, count in sorted(rejection_counts.items()))
        raise ValueError(f"patrol_assignment_infeasible: full time-aware clearance rejected all {math.factorial(count)} "
                         f"assignments ({detail})")
    distance, assignment, routes, reports = min(feasible, key=lambda item: (item[0], item[1]))
    if patrol_cache_eligible and assignment != patrol_cache["assignment"]:
        # The shared clearance decision is invariant under agent renaming;
        # selected diagnostics still need their actual agent names.
        patrol_starts = {agent: (phases["approach"][-1] if phases["approach"] else homes[agent])
                         for agent, phases in routes.items()}
        reports["patrol"] = _phase_check(patrol_starts,
            {agent: phases["patrol"] for agent, phases in routes.items()}, execution, clearance)
        patrol_selected_rechecks += 1
    assignments = {vehicle["id"]: f"entry_{index:02d}" for vehicle, index in zip(vehicles, assignment)}
    diagnostics = dict(allocation_method="full_time_aware_clearance_then_minimum_approach_v1",
        perimeter_m=perimeter, patrol_direction=direction, laps=laps,
        entry_reference_arc_m=reference, entry_spacing_arc_m=perimeter / count,
        entry_arcs_m=entry_arcs, entry_points=entries,
        nominal_revisit_interval_s=perimeter / (count * speed),
        patrol_nominal_motion_duration_s=laps * perimeter / speed,
        patrol_prefilter_duration_s=patrol_duration, patrol_prefilter_tau_s=tau,
        patrol_spacing_prefilter=prefilter,
        candidate_assignment_count=math.factorial(count), feasible_assignment_count=len(feasible),
        patrol_checker_cache=dict(version="patrol_permutation_cache_v1",
            eligible=patrol_cache_eligible, patrol_full_checks=patrol_full_checks,
            patrol_cache_reuses=patrol_cache_reuses,
            selected_diagnostic_rechecks=patrol_selected_rechecks),
        rejected_assignment_reasons=dict(sorted(rejection_counts.items())),
        chosen_assignment_entry_indices={vehicle["id"]: index for vehicle, index in zip(vehicles, assignment)},
        chosen_approach_distance_m=distance,
        chosen_approach_intersection_count=_approach_crossings(vehicles, assignment, entries),
        selected_assignment_phase_clearance=reports)
    # The planner contract carries horizontal coordinates only. The route
    # compiler adds the common altitude after the same zero-length cleaning.
    horizontal_routes = {agent: {phase: [{key: point[key] for key in ("east_m", "north_m")}
                                          for point in points]
                                 for phase, points in phases.items()}
                         for agent, phases in routes.items()}
    return PlanResult(horizontal_routes, assignments, diagnostics)


def evaluate_channel(scene, traces, windows, clocks, *, progress_mapping_version="ordered_route_progress_v1",
                     validator_version=VALIDATOR_VERSION):
    from .patrol_validation import evaluate_channel as implementation
    return implementation(scene, traces, windows, clocks, progress_mapping_version=progress_mapping_version,
                          validator_version=validator_version)


def behavior_labels(scene, truth):
    from .patrol_validation import behavior_labels as implementation
    return implementation(scene, truth)


def topology_signature(spec, planning):
    return (len(spec["scenario"]["vehicles"]), spec["mission"]["intent_params"]["laps"],
            planning["patrol_direction"], spec["mission"]["return_required"])


intent_spec = IntentSpec("patrol", ("perimeter_patrol",), ("approach", "patrol", "return"),
    frozenset({"patrol"}), normalize_params, (PLANNER_VERSION, "bidirectional_lanes_v1"), evaluate_channel,
    VALIDATOR_VERSION, behavior_labels,
    ("min_segment_visits", "max_revisit_gap_s", "loop_segment_coverage"), topology_signature)
planner_spec = PlannerSpec(PLANNER_VERSION, PLANNER_VERSION, normalize_planner, plan_routes)
