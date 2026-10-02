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


AC4_TIMING_VERSION = "ac4_relative_progress_timing_v2"
MAPPING_VERSION = "waypoint_closest_piecewise_linear_v1"
INTERVAL_VERSION = "simultaneous_terminal_interval_min_span_v1"
EVENT_MAPPING_VERSION = "raw_waypoint_event_piecewise_linear_v1"
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
