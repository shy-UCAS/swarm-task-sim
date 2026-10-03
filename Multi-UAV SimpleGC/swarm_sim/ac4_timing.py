"""Offline AC4 relative-progress timing, independent of the execution controller.

No timing, route, arrival or flight-control configuration is changed here.  Each
vehicle has a piecewise-linear actual-time -> nominal-time map.  A *proved*
terminal hover can widen its nominal time to [arrival, nominal phase end].
At a common actual time the smallest simultaneous fleet span is
max(0, max(lower bounds) - min(upper bounds)); separate pairwise choices are not
used.  Its exact supremum is attained at a piecewise-linear knot or a one-sided
limit of a hover transition.  There is no time-grid approximation to this max.

The public high-level adapter consumes the same (time, xyz...) traces as route
windows. Times use ``time_epoch``. Traces must bracket both exact phase bounds;
truncated CSV grids must not be extrapolated to manufacture that support.
"""

import bisect
import math

from .route_timing import nominal_arrival_evidence
from .route_windows import _speed_rows


AC4_TIMING_VERSION = "ac4_relative_progress_timing_v2"
MAPPING_VERSION = "waypoint_closest_piecewise_linear_v1"
INTERVAL_VERSION = "simultaneous_terminal_interval_min_span_v1"
EVENT_MAPPING_VERSION = "raw_waypoint_event_piecewise_linear_v1"
ORDERED_ROUTE_PROGRESS_VERSION = "ordered_route_progress_v1"
ORDERED_ROUTE_PROGRESS_V2_VERSION = "ordered_route_progress_v2"
AC4_TIMING_V3_VERSION = "ac4_relative_progress_timing_v3"
MATCH_TOLERANCE_M = 3.0
VISIT_EXIT_TOLERANCE_M = 3.5
BACKTRACK_TOLERANCE_M = .5
EPS = 1e-9


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _conjunction(values):
    values = list(values)
    return False if False in values else True if values and all(v is True for v in values) else None


def minimum_fleet_span(intervals):
    """Return an attainable fleet-wide minimizer, not incompatible pair choices."""
    if not intervals:
        raise ValueError("at least one nominal-time interval is required")
    if any(len(v) != 2 or not all(_finite(x) for x in v) or v[0] > v[1]
           for v in intervals.values()):
        raise ValueError("nominal-time intervals must be finite and ordered")
    greatest_lower = max(v[0] for v in intervals.values())
    least_upper = min(v[1] for v in intervals.values())
    selected = {agent: min(greatest_lower, bounds[1]) for agent, bounds in intervals.items()}
    return dict(span_s=max(0., greatest_lower - least_upper),
                selected_nominal_s=selected, nominal_intervals_s=intervals)


def _nominal_at(nodes, stamp):
    times = [node["actual_s"] for node in nodes]
    right = bisect.bisect_right(times, stamp)
    if right == len(nodes):
        # Beyond the last waypoint, a non-proved hover stays a singleton. This
        # is a conservative upper bound on the result with interval relaxation.
        return nodes[-1]["nominal_s"]
    if not right:
        return nodes[0]["nominal_s"]
    a, b = nodes[right - 1], nodes[right]
    fraction = (stamp - a["actual_s"]) / (b["actual_s"] - a["actual_s"])
    return a["nominal_s"] + fraction * (b["nominal_s"] - a["nominal_s"])


def evaluate_phase_timing(mappings, *, start_s, end_s, tau_s, nominal_end_s):
    """Evaluate exact relative progress for a common, fully observed phase.

    ``mappings[agent]`` has ``nodes=[{actual_s, nominal_s}, ...]`` beginning at
    (start_s, 0), ``evidence_complete=True``, and optionally a proved
    ``terminal_hover_start_s``. A hover must start at/after the final node.
    A missing hover is deliberately *not* evidence failure: the terminal
    singleton computes a conservative upper bound, labelled in the result.
    Missing coverage, malformed/nonmonotone nodes and missing agents are UNKNOWN.
    Nodes are never sorted or repaired. Tau uses the user-authorized inclusive
    boundary D <= tau, unlike the retained strict AC4 v1 diagnostic.
    """
    issues = []
    if not all(_finite(v) for v in (start_s, end_s, tau_s, nominal_end_s)):
        issues.append("nonfinite_phase_bounds_or_model")
    elif not (end_s > start_s and tau_s >= 0 and nominal_end_s >= 0):
        issues.append("invalid_phase_bounds_or_model")
    if not mappings:
        issues.append("missing_agent_mappings")
    for agent, mapping in mappings.items():
        nodes = mapping.get("nodes", [])
        if mapping.get("evidence_complete") is not True:
            issues.append(f"{agent}:incomplete_evidence")
        if not nodes or any(not _finite(n.get("actual_s")) or not _finite(n.get("nominal_s")) for n in nodes):
            issues.append(f"{agent}:missing_or_nonfinite_nodes")
            continue
        if issues and not all(_finite(v) for v in (start_s, end_s, nominal_end_s)):
            continue
        if abs(nodes[0]["actual_s"] - start_s) > EPS or abs(nodes[0]["nominal_s"]) > EPS:
            issues.append(f"{agent}:missing_release_zero_anchor")
        if any(b["actual_s"] <= a["actual_s"] or b["nominal_s"] < a["nominal_s"]
               for a, b in zip(nodes, nodes[1:])):
            issues.append(f"{agent}:nonmonotonic_nodes")
        if any(n["actual_s"] < start_s or n["actual_s"] > end_s
               or n["nominal_s"] < 0 or n["nominal_s"] > nominal_end_s for n in nodes):
            issues.append(f"{agent}:node_outside_phase")
        hover = mapping.get("terminal_hover_start_s")
        if hover is not None and (not _finite(hover) or hover < nodes[-1]["actual_s"] or hover > end_s):
            issues.append(f"{agent}:invalid_terminal_hover_start")
    result = dict(version=AC4_TIMING_VERSION, interval_version=INTERVAL_VERSION,
                  common_actual_domain_s=[start_s, end_s], nominal_end_s=nominal_end_s,
                  tau_s=tau_s, complete=not issues, within_tau=None, D_s=None,
                  issues=issues, criterion="D <= tau", mappings=mappings,
                  conservative_terminal_singletons=[agent for agent, m in mappings.items()
                                                   if m.get("terminal_hover_start_s") is None])
    if issues:
        return result
    knots = {start_s, end_s}
    for mapping in mappings.values():
        knots.update(node["actual_s"] for node in mapping["nodes"])
        if mapping.get("terminal_hover_start_s") is not None:
            knots.add(mapping["terminal_hover_start_s"])
    worst, count = None, 0
    for stamp in sorted(knots):
        # The left limit preserves a possible maximum immediately before an
        # interval widens. Point and right limit coincide for this convention.
        for side in (["point"] if stamp == start_s else ["left_limit", "point"]):
            intervals = {}
            for agent, mapping in mappings.items():
                hover = mapping.get("terminal_hover_start_s")
                active = hover is not None and (stamp > hover or (stamp == hover and side == "point"))
                nominal = _nominal_at(mapping["nodes"], stamp)
                intervals[agent] = ([mapping["nodes"][-1]["nominal_s"], nominal_end_s]
                                    if active else [nominal, nominal])
            candidate = minimum_fleet_span(intervals)
            candidate.update(actual_s=stamp, side=side)
            count += 1
            if worst is None or candidate["span_s"] > worst["span_s"]:
                worst = candidate
    result.update(D_s=worst["span_s"], within_tau=worst["span_s"] <= tau_s,
                  worst=worst, evaluated_limits=count, knots_s=sorted(knots),
                  maximum_method="exact union of affine knots and hover-transition one-sided limits")
    return result


def _position(values):
    return isinstance(values, (list, tuple)) and len(values) >= 3 and all(_finite(v) for v in values[:3])


def _clipped_trace(rows, start_s, end_s, max_gap_s):
    if not rows or any(not _finite(t) for t, _ in rows):
        raise ValueError("missing_or_nonfinite_trajectory")
    if any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise ValueError("nonmonotonic_trajectory")
    if rows[0][0] > start_s or rows[-1][0] < end_s:
        raise ValueError("trajectory_does_not_cover_common_domain")
    clipped = []
    for (a, xyz_a), (b, xyz_b) in zip(rows, rows[1:]):
        if b < start_s or a > end_s:
            continue
        if b == start_s or a == end_s:
            continue
        if not _position(xyz_a) or not _position(xyz_b):
            raise ValueError("invalid_trajectory_in_common_domain")
        if b - a > max_gap_s + EPS:
            raise ValueError("trajectory_gap_in_common_domain")
        low, high = max(a, start_s), min(b, end_s)
        for t in (low, high):
            fraction = (t - a) / (b - a)
            xyz = [x + fraction * (y - x) for x, y in zip(xyz_a[:3], xyz_b[:3])]
            if not clipped or t > clipped[-1][0]:
                clipped.append((t, xyz))
    if not clipped or clipped[0][0] != start_s or clipped[-1][0] != end_s:
        raise ValueError("trajectory_cannot_bracket_common_domain")
    return clipped


def closest_waypoint_nodes(rows, targets, nominal_times, *, start_s, end_s, max_gap_s):
    """Closest position on the observed linear trajectory over the whole phase.

    Exact line-segment projection uses all three position coordinates. Distinct
    equally closest visits are ambiguous and rejected; a single contiguous
    closest plateau uses its first instant. All waypoint minima are selected
    independently, then their original route order must be strictly increasing.
    No greedy restriction, sorting, or event-centred search manufactures order.
    """
    if len(targets) != len(nominal_times) or not _finite(max_gap_s) or max_gap_s <= 0:
        raise ValueError("invalid_waypoint_model_or_max_gap")
    clipped = _clipped_trace(rows, start_s, end_s, max_gap_s)
    nodes = [dict(actual_s=start_s, nominal_s=0., source="scheduled_phase_release")]
    for index, (target, nominal) in enumerate(zip(targets, nominal_times)):
        xyz = [target.get(k) for k in ("east_m", "north_m", "up_m")]
        if not _position(xyz) or not _finite(nominal):
            raise ValueError("invalid_waypoint_target_or_nominal_time")
        candidates = []
        for (a, xyz_a), (b, xyz_b) in zip(clipped, clipped[1:]):
            delta = [y - x for x, y in zip(xyz_a, xyz_b)]
            norm = sum(d * d for d in delta)
            fraction = min(1., max(0., sum((z - x) * d for z, x, d in zip(xyz, xyz_a, delta)) / norm)) if norm else 0.
            position = [x + fraction * d for x, d in zip(xyz_a, delta)]
            t = a + fraction * (b - a)
            candidates.append((math.dist(position, xyz), t, b if not norm else t))
        minimum = min(item[0] for item in candidates)
        hits = sorted((a, b) for distance, a, b in candidates if abs(distance - minimum) <= EPS)
        visits = []
        for low, high in hits:
            if visits and low <= visits[-1][1] + EPS:
                visits[-1][1] = max(visits[-1][1], high)
            else:
                visits.append([low, high])
        if len(visits) != 1:
            raise ValueError(f"ambiguous_distinct_closest_visits:route_index={index}")
        stamp = visits[0][0]
        if stamp <= nodes[-1]["actual_s"]:
            raise ValueError(f"nonmonotonic_closest_nodes:route_index={index}")
        nodes.append(dict(actual_s=stamp, nominal_s=nominal, route_index=index, seq=index + 2,
                          minimum_distance_m=minimum, closest_time_interval_s=visits[0],
                          search_domain_s=[start_s, end_s], source=MAPPING_VERSION))
    return nodes


def _planned_xyz(point):
    if isinstance(point, dict):
        value = [point.get(key) for key in ("east_m", "north_m", "up_m")]
    else:
        value = point
    if not _position(value):
        raise ValueError("invalid_planned_route_point")
    return value[:3]


def _projection(a, b, target, low=0., high=1.):
    delta = [y - x for x, y in zip(a, b)]
    norm = sum(d * d for d in delta)
    fraction = min(high, max(low, sum((z - x) * d for z, x, d in zip(target, a, delta)) / norm)) if norm else low
    position = [x + fraction * d for x, d in zip(a, delta)]
    return fraction, math.dist(position, target)


def _visit_intervals(clipped, target, tolerance):
    """Maximal continuous visits to a 3D waypoint ball, including crossings between samples."""
    intervals = []
    for (a, pa), (b, pb) in zip(clipped, clipped[1:]):
        delta = [y - x for x, y in zip(pa, pb)]
        offset = [x - z for x, z in zip(pa, target)]
        quadratic = sum(d * d for d in delta)
        if quadratic <= EPS:
            if math.dist(pa, target) > tolerance + EPS:
                continue
            lo, hi = a, b
        else:
            linear = 2 * sum(x * d for x, d in zip(offset, delta))
            constant = sum(x * x for x in offset) - tolerance * tolerance
            discriminant = linear * linear - 4 * quadratic * constant
            if discriminant < -EPS:
                continue
            root = math.sqrt(max(0., discriminant))
            lower = max(0., (-linear - root) / (2 * quadratic))
            upper = min(1., (-linear + root) / (2 * quadratic))
            if lower > upper + EPS:
                continue
            lo, hi = a + lower * (b - a), a + upper * (b - a)
        if intervals and lo <= intervals[-1][1] + EPS:
            intervals[-1][1] = max(intervals[-1][1], hi)
        else:
            intervals.append([lo, hi])
    return intervals


def _closest_during(clipped, target, low, high):
    best = None
    for (a, pa), (b, pb) in zip(clipped, clipped[1:]):
        if b < low or a > high:
            continue
        minimum = max(0., (low - a) / (b - a))
        maximum = min(1., (high - a) / (b - a))
        if minimum > maximum + EPS:
            continue
        fraction, distance = _projection(pa, pb, target, minimum, maximum)
        stamp = a + fraction * (b - a)
        if best is None or (distance, stamp) < best:
            best = (distance, stamp)
    return best


def _point_along_segment(point, start, end, arc_start, length):
    fraction, distance = _projection(start, end, point)
    return arc_start + fraction * length, distance


def _backtracking_evidence(clipped, planned, arcs, nodes, tolerance):
    """Check raw ordered progress before any small jitter is tolerated.

    Only the current or just-completed route segment is considered, so a later
    pass through the same coordinate cannot be mistaken for the present lap.
    """
    if len(planned) < 2 or len(nodes) < 2:
        return dict(detected=False, maximum_reversal_m=0., tolerance_m=tolerance, samples_checked=0)
    stamps = [node["actual_s"] for node in nodes]
    maximum, peak, witness, checked = 0., 0., None, 0
    for stamp, position in clipped:
        if stamp > stamps[-1] and len(nodes) < len(planned):
            break
        reached = bisect.bisect_right(stamps, stamp) - 1
        candidates = []
        for segment in (reached - 1, reached):
            if 0 <= segment < len(planned) - 1:
                progress, distance = _point_along_segment(position, planned[segment], planned[segment + 1],
                                                           arcs[segment], arcs[segment + 1] - arcs[segment])
                candidates.append((distance, abs(progress - arcs[min(reached, len(arcs) - 1)]), progress))
        if not candidates:
            continue
        distance, _, progress = min(candidates)
        if distance > MATCH_TOLERANCE_M + EPS:
            continue
        checked += 1
        peak = max(peak, progress)
        reversal = peak - progress
        if reversal > maximum:
            maximum, witness = reversal, dict(actual_s=stamp, observed_progress_m=progress,
                                                previous_max_progress_m=peak, route_distance_m=distance)
    return dict(detected=maximum > tolerance + EPS, maximum_reversal_m=maximum,
                tolerance_m=tolerance, samples_checked=checked, witness=witness)


def ordered_route_progress(rows, targets, nominal_times, *, start_s, end_s, max_gap_s,
                           match_tolerance_m=MATCH_TOLERANCE_M, lap_node_indices=None, start_point=None):
    """Match route nodes in visit order and encode an actual-time -> nominal map.

    Unique-node routes retain the v2 continuous global closest point if valid,
    preserving measured v0.4 timing. Revisited positions use the first distinct
    ordered 3D visit, taking the closest point *within that visit*. No target is
    inferred from nominal time or the waypoint receipt events.
    """
    number_ok = all(_finite(value) for value in (start_s, end_s, max_gap_s, match_tolerance_m))
    if (len(targets) != len(nominal_times) or not number_ok or max_gap_s <= 0
            or match_tolerance_m <= 0 or end_s <= start_s):
        raise ValueError("invalid_ordered_route_model_or_bounds")
    if any(not _finite(value) or value < 0 for value in nominal_times) or any(
            later <= earlier for earlier, later in zip(nominal_times, nominal_times[1:])):
        raise ValueError("invalid_ordered_route_nominal_times")
    if lap_node_indices is not None and (not isinstance(lap_node_indices, (list, tuple))
            or any(type(index) is not int or not 0 <= index < len(targets) for index in lap_node_indices)
            or len(set(lap_node_indices)) != len(lap_node_indices)):
        raise ValueError("invalid_lap_node_indices")
    target_xyz = [_planned_xyz(target) for target in targets]
    anchor = dict(actual_s=start_s, nominal_s=0., cumulative_arc_length_m=0.,
                  source="scheduled_phase_release")
    result = dict(version=ORDERED_ROUTE_PROGRESS_VERSION, mapping_version=ORDERED_ROUTE_PROGRESS_VERSION,
                  nodes=[anchor], node_evidence=[], progress_segments=[], issues=[], evidence_complete=False,
                  match_tolerance_m=match_tolerance_m, backtrack_tolerance_m=BACKTRACK_TOLERANCE_M,
                  per_agent_laps_observed=None, laps_evidence_status="unknown", method=None)
    try:
        clipped = _clipped_trace(rows, start_s, end_s, max_gap_s)
        planned_start = _planned_xyz(start_point) if start_point is not None else clipped[0][1][:3]
    except ValueError as exc:
        result["issues"] = [str(exc)]
        return result
    planned = [planned_start, *target_xyz]
    arcs = [0.]
    for a, b in zip(planned, planned[1:]):
        length = math.dist(a, b)
        if length < .05:
            result["issues"] = ["zero_length_planned_segment"]
            return result
        arcs.append(arcs[-1] + length)
    if lap_node_indices is None:
        lap_node_indices = [index for index, target in enumerate(target_xyz)
                            if math.dist(target, planned_start) <= 1e-6]
    else:
        lap_node_indices = list(lap_node_indices)
    result["lap_node_indices"] = lap_node_indices
    repeated = any(math.dist(a, b) <= 1e-6 for i, a in enumerate(planned)
                   for b in planned[:i])
    result["method"] = "first_ordered_visit_then_continuous_closest" if repeated else "unique_nodes_v2_closest_compatible"

    legacy_nodes = None
    if not repeated:
        try:
            legacy_nodes = closest_waypoint_nodes(rows, targets, nominal_times,
                start_s=start_s, end_s=end_s, max_gap_s=max_gap_s)
        except ValueError:
            # The ordered path below can distinguish backtracking from other
            # failures, but never suppresses evidence faults by reordering.
            pass
    if legacy_nodes is not None:
        for index, legacy in enumerate(legacy_nodes[1:]):
            distance = legacy["minimum_distance_m"]
            node = dict(legacy, cumulative_arc_length_m=arcs[index + 1],
                        visit_ordinal=1, evidence_status="matched" if distance <= match_tolerance_m + EPS else "outside_tolerance")
            result["nodes"].append(node)
            result["node_evidence"].append(dict(route_index=index, seq=index + 2, nominal_s=nominal_times[index],
                cumulative_arc_length_m=arcs[index + 1], actual_s=node["actual_s"], match_distance_m=distance,
                evidence_status=node["evidence_status"], visit_ordinal=1))
            if distance > match_tolerance_m + EPS:
                result["issues"].append(f"node_outside_match_tolerance:route_index={index}")
    else:
        for index, (target, nominal) in enumerate(zip(target_xyz, nominal_times)):
            previous = result["nodes"][-1]["actual_s"]
            ordinal = 1 + sum(math.dist(target, prior) <= 1e-6 for prior in planned[:index + 1])
            visits = _visit_intervals(clipped, target, match_tolerance_m)
            selected = None
            for low, high in visits:
                # A repeated coordinate needs a separate departure and re-entry.
                if repeated and any(math.dist(target, prior) <= 1e-6 for prior in planned[:index + 1]) and low <= previous + EPS:
                    continue
                if high <= previous + EPS:
                    continue
                candidate = _closest_during(clipped, target, max(low, previous + EPS), high)
                if candidate is not None:
                    distance, stamp = candidate
                    if stamp > previous + EPS and distance <= match_tolerance_m + EPS:
                        selected = (distance, stamp, low, high)
                        break
            if selected is None:
                issue = f"missing_route_node:route_index={index}"
                result["issues"].append(issue)
                result["node_evidence"].append(dict(route_index=index, seq=index + 2, nominal_s=nominal,
                    cumulative_arc_length_m=arcs[index + 1], actual_s=None, match_distance_m=None,
                    evidence_status="missing", visit_ordinal=ordinal, search_after_s=previous,
                    visit_count=len(visits)))
                for later in range(index + 1, len(targets)):
                    result["node_evidence"].append(dict(route_index=later, seq=later + 2,
                        nominal_s=nominal_times[later], cumulative_arc_length_m=arcs[later + 1],
                        actual_s=None, match_distance_m=None, evidence_status="unknown_after_missing_predecessor"))
                break
            distance, stamp, low, high = selected
            node = dict(actual_s=stamp, nominal_s=nominal, route_index=index, seq=index + 2,
                        minimum_distance_m=distance, cumulative_arc_length_m=arcs[index + 1],
                        closest_time_interval_s=[low, high], search_domain_s=[previous, end_s],
                        source=ORDERED_ROUTE_PROGRESS_VERSION, visit_ordinal=ordinal,
                        evidence_status="matched")
            result["nodes"].append(node)
            result["node_evidence"].append(dict(route_index=index, seq=index + 2, nominal_s=nominal,
                cumulative_arc_length_m=arcs[index + 1], actual_s=stamp, match_distance_m=distance,
                evidence_status="matched", visit_ordinal=ordinal, visit_interval_s=[low, high],
                search_after_s=previous))
    reverse = _backtracking_evidence(clipped, planned[:len(result["nodes"])], arcs[:len(result["nodes"])],
                                     result["nodes"], BACKTRACK_TOLERANCE_M)
    result["backtracking_evidence"] = reverse
    if reverse["detected"]:
        result["issues"].append("backtracking")
    result["progress_segments"] = [dict(actual_interval_s=[a["actual_s"], b["actual_s"]],
        nominal_interval_s=[a["nominal_s"], b["nominal_s"]]) for a, b in zip(result["nodes"], result["nodes"][1:])]
    matched = {node.get("route_index") for node in result["nodes"][1:]}
    laps = sum(index in matched for index in lap_node_indices)
    result["laps_lower_bound"] = laps
    result["evidence_complete"] = not result["issues"] and len(result["nodes"]) == len(targets) + 1
    result["per_agent_laps_observed"] = laps if result["evidence_complete"] else None
    result["laps_evidence_status"] = "exact" if result["evidence_complete"] else "unknown"
    return result


def _sample_visit_intervals(rows, target, entry_tolerance, exit_tolerance):
    """Observed passages: enter at <= entry, leave at > exit (3D metres).

    The wider exit threshold prevents boundary jitter from splitting a passage.
    The input may include interpolated phase bounds solely to establish the
    initial passage. The caller excludes those synthetic bounds from matches.
    """
    visits, active = [], None
    for stamp, position in rows:
        distance = math.dist(position[:3], target)
        if active is None:
            if distance <= entry_tolerance + EPS:
                active = []
        elif distance > exit_tolerance + EPS:
            visits.append(active)
            active = None
        if active is not None:
            active.append((distance, stamp))
    if active is not None:
        visits.append(active)
    return visits


def ordered_route_progress_v2(rows, targets, nominal_times, *, start_s, end_s, max_gap_s,
                              match_tolerance_m=MATCH_TOLERANCE_M,
                              lap_node_indices=None, start_point=None):
    """First eligible passage after each predecessor, closest actual sample.

    A passage already entered before the preceding *different* node matched is
    still eligible: only its samples after that match may be used. A passage
    used for the same coordinate (including the release anchor) cannot prove a
    later lap. There is no global-closest fallback for unique or repeated nodes.
    V1 remains available, including its original continuous-point behavior.
    """
    number_ok = all(_finite(value) for value in (start_s, end_s, max_gap_s, match_tolerance_m))
    if (len(targets) != len(nominal_times) or not number_ok or max_gap_s <= 0
            or match_tolerance_m != MATCH_TOLERANCE_M or end_s <= start_s):
        raise ValueError("invalid_ordered_route_v2_model_or_bounds")
    if any(not _finite(value) or value < 0 for value in nominal_times) or any(
            later <= earlier for earlier, later in zip(nominal_times, nominal_times[1:])):
        raise ValueError("invalid_ordered_route_nominal_times")
    if lap_node_indices is not None and (not isinstance(lap_node_indices, (list, tuple))
            or any(type(index) is not int or not 0 <= index < len(targets) for index in lap_node_indices)
            or len(set(lap_node_indices)) != len(lap_node_indices)):
        raise ValueError("invalid_lap_node_indices")
    target_xyz = [_planned_xyz(target) for target in targets]
    anchor = dict(actual_s=start_s, nominal_s=0., cumulative_arc_length_m=0.,
                  source="scheduled_phase_release")
    result = dict(version=ORDERED_ROUTE_PROGRESS_V2_VERSION, mapping_version=ORDERED_ROUTE_PROGRESS_V2_VERSION,
        nodes=[anchor], node_evidence=[], progress_segments=[], issues=[], evidence_complete=False,
        match_tolerance_m=MATCH_TOLERANCE_M, visit_exit_tolerance_m=VISIT_EXIT_TOLERANCE_M,
        backtrack_tolerance_m=BACKTRACK_TOLERANCE_M, per_agent_laps_observed=None,
        laps_evidence_status="unknown", method="first_ordered_hysteresis_passage_then_closest_sample")
    try:
        clipped = _clipped_trace(rows, start_s, end_s, max_gap_s)
        planned_start = _planned_xyz(start_point) if start_point is not None else clipped[0][1][:3]
    except ValueError as exc:
        result["issues"] = [str(exc)]
        return result
    actual_sample_times = {stamp for stamp, _ in rows if start_s <= stamp <= end_s}
    planned, arcs = [planned_start, *target_xyz], [0.]
    for a, b in zip(planned, planned[1:]):
        length = math.dist(a, b)
        if length < .05:
            result["issues"] = ["zero_length_planned_segment"]
            return result
        arcs.append(arcs[-1] + length)
    lap_indices = ([index for index, target in enumerate(target_xyz)
                    if math.dist(target, planned_start) <= 1e-6]
                   if lap_node_indices is None else list(lap_node_indices))
    result["lap_node_indices"] = lap_indices
    for index, (target, nominal) in enumerate(zip(target_xyz, nominal_times)):
        previous = result["nodes"][-1]["actual_s"]
        visits = _sample_visit_intervals(clipped, target, MATCH_TOLERANCE_M, VISIT_EXIT_TOLERANCE_M)
        prior_same_coordinate = [node["actual_s"] for node, coordinate in zip(result["nodes"], planned)
                                 if math.dist(target, coordinate) <= 1e-6]
        selected = None
        for visit_index, visit in enumerate(visits):
            low, high = visit[0][1], visit[-1][1]
            if high <= previous + EPS:
                continue
            # The phase may begin within this ball without an original sample
            # exactly at release. In that case the initial passage is consumed.
            initial_passage = (visit_index == 0 and low <= start_s + EPS
                               and math.dist(planned_start, target) <= 1e-6)
            if initial_passage or any(low - EPS <= stamp <= high + EPS for stamp in prior_same_coordinate):
                continue
            candidates = [(distance, stamp) for distance, stamp in visit
                          if stamp in actual_sample_times and stamp > previous + EPS
                          and distance <= MATCH_TOLERANCE_M + EPS]
            if candidates:
                distance, stamp = min(candidates)
                selected = distance, stamp, low, high, visit_index + 1
                break
        if selected is None:
            result["issues"].append(f"missing_route_node:route_index={index}")
            result["node_evidence"].append(dict(route_index=index, seq=index + 2, nominal_s=nominal,
                cumulative_arc_length_m=arcs[index + 1], actual_s=None, match_distance_m=None,
                evidence_status="missing", search_after_s=previous, visit_count=len(visits)))
            for later in range(index + 1, len(targets)):
                result["node_evidence"].append(dict(route_index=later, seq=later + 2,
                    nominal_s=nominal_times[later], cumulative_arc_length_m=arcs[later + 1],
                    actual_s=None, match_distance_m=None, evidence_status="unknown_after_missing_predecessor"))
            break
        distance, stamp, low, high, visit_ordinal = selected
        node = dict(actual_s=stamp, nominal_s=nominal, route_index=index, seq=index + 2,
            minimum_distance_m=distance, cumulative_arc_length_m=arcs[index + 1],
            closest_time_interval_s=[stamp, stamp], visit_interval_s=[low, high],
            search_domain_s=[previous, high], source=ORDERED_ROUTE_PROGRESS_V2_VERSION,
            visit_ordinal=visit_ordinal, evidence_status="matched")
        result["nodes"].append(node)
        result["node_evidence"].append(dict(route_index=index, seq=index + 2, nominal_s=nominal,
            cumulative_arc_length_m=arcs[index + 1], actual_s=stamp, match_distance_m=distance,
            evidence_status="matched", visit_ordinal=visit_ordinal, visit_interval_s=[low, high],
            search_after_s=previous, sample_only=True))
    reverse = _backtracking_evidence(clipped, planned[:len(result["nodes"])], arcs[:len(result["nodes"])],
                                     result["nodes"], BACKTRACK_TOLERANCE_M)
    result["backtracking_evidence"] = reverse
    if reverse["detected"]:
        result["issues"].append("backtracking")
    result["progress_segments"] = [dict(actual_interval_s=[a["actual_s"], b["actual_s"]],
        nominal_interval_s=[a["nominal_s"], b["nominal_s"]]) for a, b in zip(result["nodes"], result["nodes"][1:])]
    matched = {node.get("route_index") for node in result["nodes"][1:]}
    laps = sum(index in matched for index in lap_indices)
    result["laps_lower_bound"] = laps
    result["evidence_complete"] = not result["issues"] and len(result["nodes"]) == len(targets) + 1
    result["per_agent_laps_observed"] = laps if result["evidence_complete"] else None
    result["laps_evidence_status"] = "exact" if result["evidence_complete"] else "unknown"
    return result


def evaluate_ac4_timing(scene, traces, events, metadata, time_epoch, *,
                        channel="observation", terminal_hover_starts=None):
    """Versioned per-phase closest-node primary and raw-event crosscheck.

    Optional ``terminal_hover_starts[phase][agent]`` must come from separately
    verified trailing hover evidence. No default tolerance is introduced here.
    The crosscheck is reported separately; the primary gate never replaces raw
    events with simulated events. Missing raw events make the assessment UNKNOWN.
    """
    models = scene.get("planning", {}).get("nominal_phase_timing", {})
    shift = metadata["run_epoch_monotonic_s"] - time_epoch
    hover_by_phase = terminal_hover_starts or {}
    max_gap = scene.get("task_spec", {}).get("execution", {}).get("max_gap_s", scene.get("max_gap_s"))
    phases, all_issues = {}, []
    for phase_index, phase in enumerate(scene.get("phases", [])):
        name = phase["name"]
        model = models.get(name)
        issues = []
        releases = [e.get("release_t") + shift for e in events if e.get("event") == "phase_release_scheduled"
                    and e.get("phase") == name and _finite(e.get("release_t"))]
        start = releases[0] if len(releases) == 1 else None
        if phase_index + 1 < len(scene["phases"]):
            next_name = scene["phases"][phase_index + 1]["name"]
            ends = [e.get("release_t") + shift for e in events if e.get("event") == "phase_release_scheduled"
                    and e.get("phase") == next_name and _finite(e.get("release_t"))]
            end = ends[0] if len(ends) == 1 else None
        else:
            raw_end = metadata.get("mission_end_monotonic_s")
            end = raw_end - time_epoch if _finite(raw_end) else None
        if not model or start is None or end is None or end <= start:
            phases[name] = dict(complete=False, within_tau=None, issues=["missing_phase_model_or_bounds"])
            all_issues.append(f"{name}:missing_phase_model_or_bounds")
            continue
        agents = [v["id"] for v in scene.get("vehicles", [])]
        if set(model.get("per_agent_waypoint_arrival_s", {})) != set(agents):
            issues.append("nominal_agent_set_mismatch")
        primary, cross = {}, {}
        for agent in agents:
            nominal = model.get("per_agent_waypoint_arrival_s", {}).get(agent, [])
            route = phase.get("routes", {}).get(agent)
            local = []
            raw_nodes = [dict(actual_s=start, nominal_s=0., source="scheduled_phase_release")]
            if route is None or len(route) != len(nominal):
                local.append("route_and_nominal_waypoint_count_mismatch")
            else:
                for index, expected in enumerate(nominal):
                    hits = [e["t"] + shift for e in events if e.get("event") == "waypoint_reached"
                            and e.get("phase") == name and e.get("agent_id") == agent
                            and type(e.get("seq")) is int and e["seq"] == index + 2 and _finite(e.get("t"))
                            and start <= e["t"] + shift <= end]
                    if len(hits) != 1:
                        local.append(f"missing_or_duplicate_waypoint_event:seq={index + 2}")
                    else:
                        raw_nodes.append(dict(actual_s=hits[0], nominal_s=expected, seq=index + 2,
                                              route_index=index, source=EVENT_MAPPING_VERSION))
                if not route:
                    no_op = {}
                    for kind in ("phase_no_op_started", "phase_no_op_ready"):
                        no_op[kind] = [e["t"] + shift for e in events if e.get("event") == kind
                                       and e.get("phase") == name and e.get("agent_id") == agent
                                       and _finite(e.get("t")) and start <= e["t"] + shift <= end]
                    if (any(len(hits) != 1 for hits in no_op.values()) or
                            (all(len(hits) == 1 for hits in no_op.values()) and
                             no_op["phase_no_op_ready"][0] < no_op["phase_no_op_started"][0])):
                        local.append("missing_or_invalid_no_op_start_ready_evidence")
            try:
                closest = closest_waypoint_nodes(traces.get(agent, []), route or [], nominal,
                    start_s=start, end_s=end, max_gap_s=max_gap)
            except ValueError as exc:
                closest = []
                local.append(str(exc))
            hover = hover_by_phase.get(name, {}).get(agent)
            if hover is not None and (not _finite(hover) or hover < start or hover > end):
                local.append("invalid_supplied_terminal_hover_start")
                hover = None
            # A hover proved before the closest/event anchor can only start
            # relaxing this representation once that anchor has been reached.
            def mapping(nodes):
                bound_hover = max(hover, nodes[-1]["actual_s"]) if hover is not None and nodes else hover
                return dict(nodes=nodes, evidence_complete=not local,
                            terminal_hover_start_s=bound_hover,
                            supplied_terminal_hover_start_s=hover)
            primary[agent], cross[agent] = mapping(closest), mapping(raw_nodes)
            issues.extend(f"{agent}:{issue}" for issue in local)
        kwargs = dict(start_s=start, end_s=end, tau_s=model.get("tau_s"), nominal_end_s=model.get("duration_s"))
        a, b = evaluate_phase_timing(primary, **kwargs), evaluate_phase_timing(cross, **kwargs)
        complete = not issues and a["complete"] and b["complete"]
        within = a["within_tau"] if complete else None
        phases[name] = dict(primary=a, crosscheck=b, complete=complete, within_tau=within,
                            crosscheck_within_tau=b["within_tau"],
                            crosscheck_agrees=(a["within_tau"] == b["within_tau"]) if complete else None,
                            issues=issues, channel=channel)
        all_issues.extend(f"{name}:{issue}" for issue in issues)
    return dict(version=AC4_TIMING_VERSION, mapping_version=MAPPING_VERSION,
                event_mapping_version=EVENT_MAPPING_VERSION, interval_version=INTERVAL_VERSION,
                channel=channel, per_phase=phases, complete=bool(phases) and all(p["complete"] for p in phases.values()),
                within_tau=_conjunction(p["within_tau"] for p in phases.values()),
                crosscheck_within_tau=_conjunction(p.get("crosscheck_within_tau") for p in phases.values()),
                issues=all_issues, v1_diagnostic=nominal_arrival_evidence(scene, events, metadata, time_epoch),
                v1_is_gate=False, criterion="per semantic phase max_t min_simultaneous_fleet_span(sigma_i(t)) <= tau",
                no_hover_policy="terminal singleton: conservative upper bound, no unproved interval relaxation")


def evaluate_ac4_timing_v3(scene, traces, events, metadata, time_epoch, *,
                           channel="observation", terminal_hover_starts=None,
                           progress_mapping_version=ORDERED_ROUTE_PROGRESS_VERSION):
    """AC4 v3: ordered position visits, unchanged v2 fleet-span calculation.

    Event sequence numbers provide an independent crosscheck. V2 remains a
    separate entry point so frozen historical analyses are never reinterpreted.
    """
    progress_mapper = {ORDERED_ROUTE_PROGRESS_VERSION: ordered_route_progress,
                       ORDERED_ROUTE_PROGRESS_V2_VERSION: ordered_route_progress_v2}.get(progress_mapping_version)
    if progress_mapper is None:
        raise ValueError(f"unsupported_progress_mapping_version:{progress_mapping_version}")
    models = scene.get("planning", {}).get("nominal_phase_timing", {})
    shift = metadata["run_epoch_monotonic_s"] - time_epoch
    hover_by_phase = terminal_hover_starts or {}
    max_gap = scene.get("task_spec", {}).get("execution", {}).get("max_gap_s", scene.get("max_gap_s"))
    phases, all_issues, laps = {}, [], {}
    for phase_index, phase in enumerate(scene.get("phases", [])):
        name = phase["name"]
        model = models.get(name)
        issues = []
        releases = [e.get("release_t") + shift for e in events if e.get("event") == "phase_release_scheduled"
                    and e.get("phase") == name and _finite(e.get("release_t"))]
        start = releases[0] if len(releases) == 1 else None
        if phase_index + 1 < len(scene["phases"]):
            next_name = scene["phases"][phase_index + 1]["name"]
            ends = [e.get("release_t") + shift for e in events if e.get("event") == "phase_release_scheduled"
                    and e.get("phase") == next_name and _finite(e.get("release_t"))]
            end = ends[0] if len(ends) == 1 else None
        else:
            raw_end = metadata.get("mission_end_monotonic_s")
            end = raw_end - time_epoch if _finite(raw_end) else None
        if not model or start is None or end is None or end <= start:
            phases[name] = dict(complete=False, within_tau=None, issues=["missing_phase_model_or_bounds"])
            all_issues.append(f"{name}:missing_phase_model_or_bounds")
            continue
        agents = [v["id"] for v in scene.get("vehicles", [])]
        if set(model.get("per_agent_waypoint_arrival_s", {})) != set(agents):
            issues.append("nominal_agent_set_mismatch")
        primary, cross, laps[name] = {}, {}, {}
        for agent in agents:
            nominal = model.get("per_agent_waypoint_arrival_s", {}).get(agent, [])
            route = phase.get("routes", {}).get(agent)
            common_issues, event_issues, progress_issues = [], [], []
            raw_nodes = [dict(actual_s=start, nominal_s=0., source="scheduled_phase_release")]
            if route is None or len(route) != len(nominal):
                common_issues.append("route_and_nominal_waypoint_count_mismatch")
            else:
                for index, expected in enumerate(nominal):
                    hits = [e["t"] + shift for e in events if e.get("event") == "waypoint_reached"
                            and e.get("phase") == name and e.get("agent_id") == agent
                            and type(e.get("seq")) is int and e["seq"] == index + 2 and _finite(e.get("t"))
                            and start <= e["t"] + shift <= end]
                    if len(hits) != 1:
                        event_issues.append(f"missing_or_duplicate_waypoint_event:seq={index + 2}")
                    else:
                        raw_nodes.append(dict(actual_s=hits[0], nominal_s=expected, seq=index + 2,
                                              route_index=index, source=EVENT_MAPPING_VERSION))
                if not route:
                    no_op = {}
                    for kind in ("phase_no_op_started", "phase_no_op_ready"):
                        no_op[kind] = [e["t"] + shift for e in events if e.get("event") == kind
                                       and e.get("phase") == name and e.get("agent_id") == agent
                                       and _finite(e.get("t")) and start <= e["t"] + shift <= end]
                    if (any(len(hits) != 1 for hits in no_op.values()) or
                            (all(len(hits) == 1 for hits in no_op.values()) and
                             no_op["phase_no_op_ready"][0] < no_op["phase_no_op_started"][0])):
                        event_issues.append("missing_or_invalid_no_op_start_ready_evidence")
            start_point = (scene.get("semantic_plan", {}).get("execution_phases", {}).get(name, {})
                           .get("agents", {}).get(agent, {}).get("start_point"))
            if start_point is None:
                start_point = phase.get("start_positions", {}).get(agent)
            if route is not None and len(route) == len(nominal):
                try:
                    progress = progress_mapper(traces.get(agent, []), route, nominal,
                        start_s=start, end_s=end, max_gap_s=max_gap, start_point=start_point,
                        lap_node_indices=None if phase.get("semantic_phase") == "patrol" else [])
                except ValueError as exc:
                    progress = dict(nodes=[], issues=[str(exc)], evidence_complete=False,
                                    per_agent_laps_observed=None)
            else:
                progress = dict(nodes=[], issues=["route_and_nominal_waypoint_count_mismatch"],
                                evidence_complete=False, per_agent_laps_observed=None)
            progress_issues.extend(progress["issues"])
            laps[name][agent] = progress["per_agent_laps_observed"]
            hover = hover_by_phase.get(name, {}).get(agent)
            if hover is not None and (not _finite(hover) or hover < start or hover > end):
                common_issues.append("invalid_supplied_terminal_hover_start")
                hover = None
            def mapping(nodes, local_issues):
                bound_hover = max(hover, nodes[-1]["actual_s"]) if hover is not None and nodes else hover
                return dict(nodes=nodes, evidence_complete=not (common_issues or local_issues),
                            terminal_hover_start_s=bound_hover,
                            supplied_terminal_hover_start_s=hover)
            primary[agent] = mapping(progress["nodes"], progress_issues)
            cross[agent] = mapping(raw_nodes, event_issues)
            primary[agent]["progress_version"] = progress_mapping_version
            primary[agent]["node_evidence"] = progress.get("node_evidence", [])
            primary[agent]["progress_segments"] = progress.get("progress_segments", [])
            primary[agent]["per_agent_laps_observed"] = progress["per_agent_laps_observed"]
            primary[agent]["backtracking_evidence"] = progress.get("backtracking_evidence")
            issues.extend(f"{agent}:{issue}" for issue in common_issues + event_issues + progress_issues)
        kwargs = dict(start_s=start, end_s=end, tau_s=model.get("tau_s"), nominal_end_s=model.get("duration_s"))
        a, b = evaluate_phase_timing(primary, **kwargs), evaluate_phase_timing(cross, **kwargs)
        a["version"] = b["version"] = AC4_TIMING_V3_VERSION
        complete = not issues and a["complete"] and b["complete"]
        phases[name] = dict(primary=a, crosscheck=b, complete=complete,
                            within_tau=a["within_tau"] if complete else None,
                            crosscheck_within_tau=b["within_tau"],
                            crosscheck_agrees=(a["within_tau"] == b["within_tau"]) if complete else None,
                            issues=issues, channel=channel, per_agent_laps_observed=laps[name])
        all_issues.extend(f"{name}:{issue}" for issue in issues)
    return dict(version=AC4_TIMING_V3_VERSION, mapping_version=progress_mapping_version,
                event_mapping_version=EVENT_MAPPING_VERSION, interval_version=INTERVAL_VERSION,
                channel=channel, per_phase=phases, per_agent_laps_observed=laps,
                complete=bool(phases) and all(p["complete"] for p in phases.values()),
                within_tau=_conjunction(p["within_tau"] for p in phases.values()),
                crosscheck_within_tau=_conjunction(p.get("crosscheck_within_tau") for p in phases.values()),
                issues=all_issues, v1_diagnostic=nominal_arrival_evidence(scene, events, metadata, time_epoch),
                v1_is_gate=False, criterion="per semantic phase max_t min_simultaneous_fleet_span(sigma_i(t)) <= tau",
                no_hover_policy="terminal singleton: conservative upper bound, no unproved interval relaxation")


def terminal_hover_evidence_v3(scene, traces, events, metadata, epoch, channel, clocks):
    """Prove a measured stable terminal suffix for optional AC4 v3 relaxation.

    This production adapter retains the v2 offline verifier's exact evidence
    rule. Its output is independent of arrival_s and a missing proof leaves the
    terminal nominal time as a conservative singleton in AC4.
    """
    shift = metadata["run_epoch_monotonic_s"] - epoch
    releases = {e["phase"]: e["release_t"] + shift for e in events if e.get("event") == "phase_release_scheduled"}
    starts, evidence = {}, []
    for index, phase in enumerate(scene["phases"]):
        name = phase["name"]
        end = releases[scene["phases"][index + 1]["name"]] if index + 1 < len(scene["phases"]) else metadata["mission_end_monotonic_s"] - epoch
        starts[name] = {}
        for agent, route in phase["routes"].items():
            role = scene.get("semantic_plan", {}).get("execution_phases", {}).get(name, {}).get("agents", {}).get(agent, {})
            point = route[-1] if route else role.get("start_point", phase.get("start_positions", {}).get(agent))
            if not point:
                continue  # AC4 still requires no-op start/ready and full coverage.
            target = [point[k] for k in ("east_m", "north_m", "up_m")]
            rows, speed_version, _ = _speed_rows(traces[agent], channel, clocks.get(agent), scene["max_gap_s"])
            selected = [r for r in rows if releases[name] <= r[0] <= end]
            after = next((r for r in rows if r[0] >= end), None)
            end_supported = bool(after and after[1] is not None and after[2] is not None
                and after[2] <= .3 + 1e-8 and after[0] - end <= scene["max_gap_s"]
                and math.dist(after[1][:3], target) <= scene["task_spec"]["execution"]["arrival_tolerance_m"] + 1e-8)
            suffix = []
            for row in reversed(selected):
                t, position, speed, _ = row
                if (position is None or speed is None or speed > .3 + 1e-8
                        or math.dist(position[:3], target) > scene["task_spec"]["execution"]["arrival_tolerance_m"] + 1e-8):
                    break
                if suffix and suffix[-1][0] - t > scene["max_gap_s"]:
                    break
                suffix.append(row)
            duration = suffix[0][0] - suffix[-1][0] if suffix else 0.
            established = bool(end_supported and len(suffix) >= 2 and duration >= .2
                               and end - suffix[0][0] <= 1 / scene["record_hz"] + 1e-8)
            if not route:
                before = next((r for r in reversed(rows) if r[0] <= releases[name]), None)
                start_supported = bool(before and before[1] is not None and before[2] is not None
                    and before[2] <= .3 + 1e-8 and releases[name] - before[0] <= scene["max_gap_s"]
                    and math.dist(before[1][:3], target) <= scene["task_spec"]["execution"]["arrival_tolerance_m"] + 1e-8)
                established = bool(established and start_supported and len(suffix) == len(selected))
            if established:
                starts[name][agent] = suffix[-1][0] if route else releases[name]
            evidence.append(dict(phase=name, agent_id=agent, channel=channel,
                version="terminal_hover_measured_suffix_v1", speed_processing_version=speed_version,
                threshold_m_s=.3, distance_tolerance_m=scene["task_spec"]["execution"]["arrival_tolerance_m"],
                minimum_measured_duration_s=.2, measured_duration_s=duration, end_support_error_s=end-selected[-1][0] if selected else None,
                terminal_suffix_supported_through_end=end_supported,
                established=established, start_s=starts[name].get(agent),
                when_not_established="retain conservative terminal singleton; no arrival_s rewrite"))
    return starts, evidence
