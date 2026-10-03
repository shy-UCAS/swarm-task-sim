"""Execution diagnostics, never model features or quality-gate replacements.

Stop segmentation and sampled synchronization reproduce audit_v04/A4_final.py
at the default 10 Hz (including its exact >= duration comparison). Inputs are
the exported task observation grid. They must not include analysis-only support
samples or be silently repaired/reordered in this diagnostic module.
"""

import math

from .observations import finite_number


VERSION = "execution_artifacts_v1"
VERSION_V2 = "execution_artifacts_v2"


def distribution(values):
    values = sorted(v for v in values if finite_number(v))
    def quantile(q):
        if not values:
            return None
        x = (len(values) - 1) * q
        i = int(x)
        return values[i] + (values[min(i + 1, len(values) - 1)] - values[i]) * (x - i)
    return dict(count=len(values), min=min(values) if values else None, p10=quantile(.1), median=quantile(.5),
                p90=quantile(.9), max=max(values) if values else None)


def stop_segments(samples, threshold=.3, minimum_s=.2, dt=.1):
    """Maximal sampled runs; missing speed and gaps > 1.5 ticks are barriers.

    Invalid timestamps invalidate the entire supplied stream. Exact-duplicate
    processing belongs upstream to the separately versioned v3 processor.
    """
    if (not finite_number(threshold) or threshold <= 0 or not finite_number(minimum_s) or minimum_s < 0
            or not finite_number(dt) or dt <= 0):
        raise ValueError("invalid stop detector parameters")
    if (any(not finite_number(t) for t, _ in samples)
            or any(b[0] <= a[0] for a, b in zip(samples, samples[1:]))):
        raise ValueError("stop detector requires a strict finite timeline")
    segments, run = [], []
    for stamp, speed in samples:
        if finite_number(speed) and 0 <= speed < threshold:
            if run and stamp - run[-1][0] > 1.5 * dt:
                segments.append(run)
                run = []
            run.append((stamp, speed))
        elif run:
            segments.append(run)
            run = []
    if run:
        segments.append(run)
    return [(run[0][0], run[-1][0]) for run in segments if run[-1][0] - run[0][0] >= minimum_s]


def synchronized_stops(intervals, start, end, dt=.1):
    """A4 sampled time fraction plus exact common-overlap event intersections.

    The legacy audit event formula uses per-agent bounding envelopes inside a
    fleet event. Retain that value separately to expose rather than conceal the
    difference for multi-stop bridged events. Time fraction is unchanged.
    """
    agents = sorted(intervals)
    if not agents or not finite_number(start) or not finite_number(end) or end < start:
        return dict(synchronized_time_fraction=None, synchronized_grid_points=None, grid_points=None,
                    fleet_stop_event_count=None, common_overlap_event_count=None, common_overlap_event_fraction=None,
                    audit_envelope_common_event_count=None)
    n = int(round((end - start) / dt)) + 1
    both = sum(all(any(a <= start + index * dt <= b for a, b in intervals[agent]) for agent in agents) for index in range(n))
    merged = []
    for left, right in sorted(interval for agent in agents for interval in intervals[agent]):
        if merged and left <= merged[-1][1] + 1e-9:
            merged[-1][1] = max(merged[-1][1], right)
        else:
            merged.append([left, right])
    exact, envelope = 0, 0
    for lo, hi in merged:
        intersections = [(lo, hi)]
        ilo, ihi, legacy_ok = lo, hi, True
        for agent in agents:
            hit = [(max(a, lo), min(b, hi)) for a, b in intervals[agent] if min(b, hi) > max(a, lo)]
            if not hit:
                intersections, legacy_ok = [], False
                break
            intersections = [(max(a, c), min(b, d)) for a, b in intersections for c, d in hit if min(b, d) > max(a, c)]
            ilo, ihi = max(ilo, min(a for a, _ in hit)), min(ihi, max(b for _, b in hit))
        exact += bool(intersections)
        envelope += legacy_ok and ihi > ilo
    return dict(synchronized_time_fraction=both / n if n else None, synchronized_grid_points=both, grid_points=n,
                fleet_stop_event_count=len(merged), common_overlap_event_count=exact,
                common_overlap_event_fraction=exact / len(merged) if merged else None,
                audit_envelope_common_event_count=envelope)


def _valid_position(values):
    return isinstance(values, (list, tuple)) and len(values) >= 3 and all(finite_number(v) for v in values[:3])


def _speed(values):
    if not isinstance(values, (list, tuple)) or len(values) < 5 or not all(finite_number(v) for v in values[3:5]):
        return None
    return math.hypot(values[3], values[4])


def _planned_points(scene):
    """Use semantic route points, not the length of lane-change connectors."""
    planning = scene.get("planning", {})
    routes = planning.get("per_agent_reference_routes", {})
    spec = scene.get("task_spec", {})
    continuous = spec.get("execution", {}).get("control_mode") == "semantic_phase_route_v1"
    waypoints, endpoints = [], {}
    for agent, route in routes.items():
        endpoints[agent] = []
        for semantic, points in route.items():
            if points:
                endpoints[agent].append(dict(semantic_phase=semantic, point=points[-1]))
            indices = range(max(0, len(points) - 1))
            for index in indices:
                point = points[index]
                if (continuous and semantic == "observe" and index == 0 and route.get("approach")
                        and point == route["approach"][-1]):
                    continue
                lane_length = None
                if semantic == "observe" and planning.get("partition_axis") in ("east", "north"):
                    pair = 2 * (index // 2)
                    if pair + 1 < len(points):
                        left, right = points[pair:pair + 2]
                        lane_length = math.hypot(right["east_m"] - left["east_m"], right["north_m"] - left["north_m"])
                waypoints.append(dict(agent_id=agent, semantic_phase=semantic, waypoint_index=index,
                                      point=point, scan_line_length_m=lane_length))
    return waypoints, endpoints


def _metric_window(agent, semantic, windows, fallback):
    selected = [w for w in windows if w.get("agent_id") == agent and w.get("semantic_phase") == semantic
                and finite_number(w.get("start_s")) and finite_number(w.get("end_s"))]
    if not selected:
        return None
    start, stop = min(w["start_s"] for w in selected), max(w["end_s"] for w in selected)
    next_starts = [w["start_s"] for w in windows if w.get("agent_id") == agent
                   and w.get("semantic_phase") != semantic and finite_number(w.get("start_s")) and w["start_s"] > stop]
    # Physical passage evidence extends through terminal confirmation to the next
    # semantic release; service windows themselves remain untouched.
    end = min(next_starts) if next_starts else stop
    return start, end, all(w.get("complete_execution_window", False) for w in selected)


def _complete(rows, start, end, dt):
    if not rows or rows[0][0] > start + 1.5 * dt or rows[-1][0] < end - 1.5 * dt:
        return False
    selected = [(t, p) for t, p in rows if start <= t <= end]
    return bool(selected) and all(_valid_position(p) and _speed(p) is not None for _, p in selected) and all(
        b[0] - a[0] <= 1.5 * dt for a, b in zip(selected, selected[1:]))


def _waypoint_metrics(scene, traces, windows, waypoints, bounds, dt, invalid):
    records = []
    for waypoint in waypoints:
        agent, point = waypoint["agent_id"], waypoint["point"]
        window = _metric_window(agent, waypoint["semantic_phase"], windows, bounds)
        record = dict(waypoint, minimum_passing_speed_m_s=None, stopped=None, evidence_complete=False)
        if window and agent not in invalid:
            start, end, execution_complete = window
            rows = [(t, p) for t, p in traces.get(agent, []) if start <= t <= end]
            distance = lambda p: math.hypot(p[0] - point["east_m"], p[1] - point["north_m"])
            candidates = [_speed(p) for _, p in rows if _valid_position(p) and distance(p) <= 2 and _speed(p) is not None]
            record["minimum_passing_speed_m_s"] = min(candidates) if candidates else None
            near = [(t, _speed(p) if _valid_position(p) and distance(p) <= 1 else None) for t, p in rows]
            stops = stop_segments(near, dt=dt)
            complete = execution_complete and _complete(traces.get(agent, []), start, end, dt)
            record.update(stopped=True if stops else (False if complete and candidates else None),
                          evidence_complete=complete, window_s=[start, end], stop_intervals_s=stops)
        records.append(record)
    unknown = sum(row["stopped"] is None for row in records)
    stopped = sum(row["stopped"] is True for row in records)
    by_length = {}
    for record in records:
        value = record["scan_line_length_m"]
        key = f"{value:.6f}" if value is not None else "not_applicable"
        by_length.setdefault(key, []).append(record)
    grouped = {key: dict(waypoint_count=len(group), unknown_count=sum(r["minimum_passing_speed_m_s"] is None for r in group),
                        minimum_passing_speed_m_s=distribution(r["minimum_passing_speed_m_s"] for r in group))
               for key, group in sorted(by_length.items())}
    return dict(total_count=len(records), stopped_count=stopped, unknown_count=unknown,
                stop_rate=stopped / len(records) if records and not unknown else None,
                minimum_passing_speed_m_s=distribution(r["minimum_passing_speed_m_s"] for r in records),
                by_scan_line_length_m=grouped, records=records)


def _timing_metrics(windows, events, metadata, time_epoch, nominal_arrivals):
    shift = metadata.get("run_epoch_monotonic_s", 0) - time_epoch if time_epoch is not None else 0
    arrivals, waits = [], []
    for window in windows:
        arrival = window.get("arrival_s")
        base = {key: window.get(key) for key in ("agent_id", "phase", "semantic_phase")}
        if finite_number(arrival):
            terminal = [e["t"] + shift for e in events if e.get("event") == "waypoint_reached"
                        and e.get("agent_id") == window.get("agent_id") and e.get("phase") == window.get("phase")
                        and e.get("terminal") is True and finite_number(e.get("t"))]
            if finite_number(window.get("terminal_waypoint_reached_s")):
                terminal = [window["terminal_waypoint_reached_s"]]
            if terminal:
                arrivals.append(dict(base, event_s=terminal[-1], arrival_s=arrival, lag_s=terminal[-1] - arrival))
            if finite_number(window.get("end_s")) and window["end_s"] >= arrival:
                waits.append(dict(base, value_s=window["end_s"] - arrival, source="trajectory_arrival_to_next_release"))
        elif finite_number(window.get("barrier_wait_host_s")):
            waits.append(dict(base, value_s=window["barrier_wait_host_s"], source="legacy_phase_finished_event_proxy"))
    deviations = []
    for item in nominal_arrivals or []:
        if finite_number(item.get("actual_s")) and finite_number(item.get("nominal_s")):
            deviations.append(dict(item, deviation_s=item["actual_s"] - item["nominal_s"]))
    return dict(
        arrival_lag_s=dict(available=bool(arrivals), records=arrivals, distribution=distribution(r["lag_s"] for r in arrivals),
                           unavailable_reason=None if arrivals else "trajectory arrival and terminal event pairing unavailable; WP-E E3 required"),
        barrier_wait_s=dict(available=bool(waits), records=waits, distribution=distribution(r["value_s"] for r in waits),
                            unavailable_reason=None if waits else "barrier timing evidence unavailable"),
        nominal_timing_deviation_s=dict(available=bool(deviations), records=deviations,
            distribution=distribution(r["deviation_s"] for r in deviations),
            max_abs_s=max((abs(r["deviation_s"]) for r in deviations), default=None),
            unavailable_reason=None if deviations else "timed reference and paired actual arrivals unavailable; WP-E required"))


def compute_execution_metrics(scene, traces, windows, events=None, metadata=None, time_epoch=None, nominal_arrivals=None):
    """Pure diagnostic interface. Traces use [E,N,U,vE,vN,vU], host grid time.

    A missing/invalid aircraft invalidates fleet fractions, not its neighbours'
    diagnostics. Empty evidence is unknown; unknown is never counted as zero.
    """
    windows = windows.get("windows", []) if isinstance(windows, dict) else windows
    windows = windows or []
    events, metadata = events or [], metadata or {}
    dt = 1 / scene.get("record_hz", scene.get("task_spec", {}).get("execution", {}).get("record_hz", 10))
    agents = [v["id"] for v in scene["vehicles"]]
    spans = [w for w in windows if finite_number(w.get("start_s")) and finite_number(w.get("end_s")) and w["end_s"] >= w["start_s"]]
    bounds = [min(w["start_s"] for w in spans), max(w["end_s"] for w in spans)] if spans else None
    speeds = {agent: [(t, _speed(p)) for t, p in traces.get(agent, [])] for agent in agents}
    invalid = {agent: "missing_velocity_evidence" for agent, values in speeds.items() if not any(s is not None for _, s in values)}
    if bounds is None:
        invalid.update({agent: "semantic_mission_window_missing" for agent in agents})
    for agent, values in speeds.items():
        if any(not finite_number(t) for t, _ in values) or any(b[0] <= a[0] for a, b in zip(values, values[1:])):
            invalid[agent] = "non_strict_timeline"
    complete = {agent: bounds is not None and agent not in invalid and _complete(traces.get(agent, []), *bounds, dt)
                for agent in agents}
    waypoints, endpoints = _planned_points(scene)
    thresholds = {}
    for threshold in (.3, .5):
        intervals, per_agent = {}, {}
        for agent in agents:
            segments = stop_segments(speeds[agent], threshold=threshold, dt=dt) if agent not in invalid else []
            intervals[agent] = segments
            classified = {"intermediate_waypoint": 0, "semantic_endpoint": 0, "other": 0}
            classified_records = []
            for start, end in segments:
                positions = [p for t, p in traces[agent] if start <= t <= end and _valid_position(p)]
                def near(point):
                    return any(math.hypot(p[0] - point["east_m"], p[1] - point["north_m"]) <= 1 for p in positions)
                # Semantic endpoint wins when points coincide (v2 observe starts
                # at approach's endpoint); categories are disjoint and explicit.
                location = ("semantic_endpoint" if any(near(p["point"]) for p in endpoints.get(agent, [])) else
                            "intermediate_waypoint" if any(near(p["point"]) for p in waypoints if p["agent_id"] == agent) else "other")
                classified[location] += 1
                classified_records.append(dict(start_s=start, end_s=end, location=location))
            per_agent[agent] = dict(stop_count=len(segments) if agent not in invalid else None,
                stop_intervals_s=segments if agent not in invalid else None,
                counts_by_location=classified if agent not in invalid else None, stops=classified_records,
                invalid_reason=invalid.get(agent), evidence_complete=complete[agent],
                stop_count_is_lower_bound=agent not in invalid and not complete[agent])
        if bounds and not invalid and all(complete.values()):
            duration = bounds[1] - bounds[0]
            stationary = sum(max(0, min(b, bounds[1]) - max(a, bounds[0])) for values in intervals.values() for a, b in values)
            sync = synchronized_stops(intervals, *bounds, dt=dt)
            fraction = stationary / (duration * len(agents)) if duration > 0 and agents else None
        else:
            stationary, fraction = None, None
            sync = synchronized_stops({}, None, None, dt=dt)
        thresholds[str(threshold)] = dict(per_agent=per_agent, stationary_time_s=stationary,
            stationary_time_fraction=fraction, **sync)
    return dict(version=VERSION, evidence_basis="FCU_horizontal_velocity", diagnostic_only=True,
        model_feature_eligible=False, stop_thresholds_m_s=[.3, .5], minimum_stop_duration_s=.2,
        sampling_dt_s=dt, detection_window="entire exported task observation grid", fraction_window_s=bounds,
        scope_note="counts use exported grid; stationary/sync fractions use semantic event span; gaps > 1.5 ticks break stops",
        synchronized_fraction_definition="A4 sampled grid starting at semantic span start; endpoint-inclusive; denominator round(duration/dt)+1",
        location_priority=["semantic_endpoint", "intermediate_waypoint", "other"], invalid_agents=invalid,
        evidence_complete=bool(agents) and all(complete.values()),
        thresholds=thresholds,
        intermediate_waypoints=_waypoint_metrics(scene, traces, windows, waypoints, bounds, dt, invalid),
        **_timing_metrics(windows, events, metadata, time_epoch, nominal_arrivals))


def _repeated_route_phases(scene):
    """Only a repeated visit *within one phase* needs ordered attribution.

    Phase boundaries may intentionally coincide (approach ends where patrol
    starts). Such a boundary is not a repeated route visit by itself.
    """
    repeated = []
    for phase in scene.get("phases", []):
        name = phase.get("name")
        roles = scene.get("semantic_plan", {}).get("execution_phases", {}).get(name, {}).get("agents", {})
        for agent, route in phase.get("routes", {}).items():
            start = roles.get(agent, {}).get("start_point")
            points = ([start] if isinstance(start, dict) else []) + list(route)
            coordinates = [(p.get("east_m"), p.get("north_m"), p.get("up_m")) for p in points]
            if len(set(coordinates)) < len(coordinates):
                repeated.append((phase, agent, start))
    return repeated


def _phase_window(agent, phase_name, windows):
    selected = [w for w in windows if w.get("agent_id") == agent and w.get("phase") == phase_name
                and finite_number(w.get("start_s")) and finite_number(w.get("end_s"))]
    if not selected:
        return None
    releases = [w["phase_release_s"] for w in selected if finite_number(w.get("phase_release_s"))]
    start = min(releases) if releases else min(w["start_s"] for w in selected)
    stop = max(w["end_s"] for w in selected)
    successors = [w.get("phase_release_s", w.get("start_s")) for w in windows
                  if w.get("agent_id") == agent and w.get("phase") != phase_name
                  and finite_number(w.get("start_s")) and w["start_s"] > stop]
    successors = [value for value in successors if finite_number(value) and value > stop]
    # Some service windows end before terminal confirmation. Extend only to
    # the next scheduled release, never into that phase's AUTO interval.
    return start, min(successors) if successors else stop, all(w.get("complete_execution_window", False) for w in selected)


def _ordered_visits(scene, traces, windows, repeated, dt, progress_mapping_version="ordered_route_progress_v1"):
    """Map repeated route targets to observed visits; never invent missing visits."""
    from .ac4_timing import ordered_route_progress, ordered_route_progress_v2
    mapper = {"ordered_route_progress_v1": ordered_route_progress,
              "ordered_route_progress_v2": ordered_route_progress_v2}[progress_mapping_version]

    by_phase = {}
    for phase, agent, start_point in repeated:
        name = phase["name"]
        route = phase["routes"][agent]
        window = _phase_window(agent, name, windows)
        model = scene.get("planning", {}).get("nominal_phase_timing", {}).get(name, {})
        nominal = model.get("per_agent_waypoint_arrival_s", {}).get(agent)
        key = agent, name
        item = dict(phase=name, semantic_phase=phase["semantic_phase"], agent_id=agent,
                    route=route, window_s=list(window[:2]) if window else None,
                    evidence_complete=False, nodes=[], issues=[])
        if window is None or not isinstance(start_point, dict) or not isinstance(nominal, list) or len(route) != len(nominal):
            item["issues"].append("missing_window_start_or_nominal_route")
        else:
            start, end, execution_complete = window
            if not execution_complete:
                item["issues"].append("incomplete_execution_window")
            try:
                mapped = mapper(traces.get(agent, []), route, nominal,
                    start_s=start, end_s=end,
                    max_gap_s=scene.get("max_gap_s", scene.get("task_spec", {}).get("execution", {}).get("max_gap_s", 1.5 * dt)),
                    start_point=start_point)
            except ValueError as exc:
                item["issues"].append(str(exc))
            else:
                item["nodes"] = mapped.get("nodes", [])
                item["issues"].extend(mapped.get("issues", []))
                item["evidence_complete"] = execution_complete and mapped.get("evidence_complete") is True
        by_phase[key] = item
    return by_phase


def _stop_visit_assignment(interval, rows, phase):
    """A stop may be assigned to at most one ordered node (horizontal <=1 m)."""
    start, end = interval
    positions = [p for t, p in rows if start <= t <= end and _valid_position(p)]
    candidates = []
    for node in phase["nodes"]:
        stamp = node.get("actual_s")
        route_index = node.get("route_index")
        if not finite_number(stamp) or not (start - 2 <= stamp <= end + 2):
            continue
        point = (phase["route"][route_index] if type(route_index) is int and 0 <= route_index < len(phase["route"])
                 else None)
        if point is None:
            continue
        distance = min((math.hypot(p[0] - point["east_m"], p[1] - point["north_m"]) for p in positions), default=None)
        if distance is not None and distance <= 1:
            time_gap = max(start - stamp, stamp - end, 0)
            candidates.append((time_gap, distance, abs((start + end) / 2 - stamp), route_index, stamp))
    if not candidates:
        return None
    time_gap, distance, _, route_index, stamp = min(candidates)
    return dict(phase=phase["phase"], route_index=route_index, matched_visit_s=stamp,
                stop_to_visit_gap_s=time_gap, minimum_stop_distance_m=distance,
                location="semantic_endpoint" if route_index == len(phase["route"]) - 1 else "intermediate_waypoint")


def _summarize_v2_waypoints(records):
    unknown = sum(row["stopped"] is None for row in records)
    stopped = sum(row["stopped"] is True for row in records)
    by_length = {}
    for record in records:
        value = record["scan_line_length_m"]
        key = f"{value:.6f}" if value is not None else "not_applicable"
        by_length.setdefault(key, []).append(record)
    grouped = {key: dict(waypoint_count=len(group), unknown_count=sum(r["minimum_passing_speed_m_s"] is None for r in group),
                         minimum_passing_speed_m_s=distribution(r["minimum_passing_speed_m_s"] for r in group))
               for key, group in sorted(by_length.items())}
    return dict(total_count=len(records), stopped_count=stopped, unknown_count=unknown,
                stop_rate=stopped / len(records) if records and not unknown else None,
                minimum_passing_speed_m_s=distribution(r["minimum_passing_speed_m_s"] for r in records),
                by_scan_line_length_m=grouped, records=records)


def compute_execution_metrics_v2(scene, traces, windows, events=None, metadata=None, time_epoch=None, nominal_arrivals=None,
                                 *, progress_mapping_version="ordered_route_progress_v1"):
    """Versioned visit-aware diagnostics for routes that revisit a position.

    The v1 entry point remains frozen. For routes without a repeated position,
    every v1 metric value and record is preserved, with only the top-level
    version changed. Repeated routes require observed ordered visits; missing
    evidence leaves waypoint stop attribution unknown, never silently spatial.
    """
    result = compute_execution_metrics(scene, traces, windows, events=events, metadata=metadata,
                                       time_epoch=time_epoch, nominal_arrivals=nominal_arrivals)
    result["version"] = VERSION_V2
    repeated = _repeated_route_phases(scene)
    if not repeated:
        return result
    windows = windows.get("windows", []) if isinstance(windows, dict) else windows
    windows = windows or []
    dt = result["sampling_dt_s"]
    phases = _ordered_visits(scene, traces, windows, repeated, dt, progress_mapping_version)
    assignment_by_stop = {}
    for threshold, report in result["thresholds"].items():
        for (agent, phase_name), phase in phases.items():
            per_agent = report["per_agent"].get(agent)
            if per_agent is None or per_agent["stops"] is None or phase["window_s"] is None:
                continue
            phase_start, phase_end = phase["window_s"]
            for stop_index, stop in enumerate(per_agent["stops"]):
                start, end = stop["start_s"], stop["end_s"]
                midpoint = (start + end) / 2
                # A next-phase release belongs to the next phase, even when
                # the preceding passage window ends at the same instant.
                if not phase_start <= midpoint < phase_end:
                    continue
                # Unproved ordering does not justify assigning a repeated
                # corner to any particular lap or waypoint.
                assignment = (_stop_visit_assignment((start, end), traces.get(agent, []), phase)
                              if phase["evidence_complete"] else None)
                stop["location"] = assignment["location"] if assignment else ("other" if phase["evidence_complete"] else None)
                stop["ordered_visit_assignment"] = assignment
                stop["ordered_visit_evidence_complete"] = phase["evidence_complete"]
                assignment_by_stop[threshold, agent, stop_index] = assignment
            per_agent["counts_by_location"] = {location: sum(stop["location"] == location for stop in per_agent["stops"])
                                               for location in ("intermediate_waypoint", "semantic_endpoint", "other")}
            per_agent["unknown_location_count"] = sum(stop["location"] is None for stop in per_agent["stops"])
    records = [record for record in result["intermediate_waypoints"]["records"]
               if (record["agent_id"], record["semantic_phase"]) not in
               {(agent, phase["semantic_phase"]) for (agent, _), phase in phases.items()}]
    for (agent, phase_name), phase in phases.items():
        route = phase["route"]
        if not route:
            continue
        role = scene.get("semantic_plan", {}).get("execution_phases", {}).get(phase_name, {}).get("agents", {}).get(agent, {})
        planner_indices = role.get("waypoint_planner_indices", list(range(len(route))))
        assigned = {}
        stops = result["thresholds"]["0.3"]["per_agent"].get(agent, {}).get("stops") or []
        for index, stop in enumerate(stops):
            item = assignment_by_stop.get(("0.3", agent, index))
            if item and item["phase"] == phase_name and item["location"] == "intermediate_waypoint":
                assigned.setdefault(item["route_index"], []).append([stop["start_s"], stop["end_s"]])
        nodes = {node.get("route_index"): node for node in phase["nodes"] if type(node.get("route_index")) is int}
        rows = traces.get(agent, [])
        for route_index, point in enumerate(route[:-1]):
            node = nodes.get(route_index)
            stamp = node.get("actual_s") if node else None
            candidates = [_speed(p) for t, p in rows if finite_number(stamp) and abs(t - stamp) <= 2
                          and _valid_position(p) and math.hypot(p[0] - point["east_m"], p[1] - point["north_m"]) <= 2
                          and _speed(p) is not None]
            minimum = min(candidates) if candidates else None
            visit_complete = phase["evidence_complete"] and node is not None
            intervals = assigned.get(route_index, [])
            records.append(dict(agent_id=agent, semantic_phase=phase["semantic_phase"],
                waypoint_index=planner_indices[route_index] if route_index < len(planner_indices) else route_index,
                route_index=route_index, point=point, scan_line_length_m=None,
                matched_visit_s=stamp, visit_mapping_version=progress_mapping_version,
                minimum_passing_speed_m_s=minimum,
                stopped=True if intervals else False if visit_complete else None,
                evidence_complete=visit_complete, window_s=phase["window_s"], stop_intervals_s=intervals,
                visit_issues=list(phase["issues"])))
    result["intermediate_waypoints"] = _summarize_v2_waypoints(records)
    result["ordered_visit_attribution"] = dict(version="ordered_stop_attribution_v1",
        time_tolerance_s=2, distance_tolerance_m=1, distance_basis="horizontal_EN",
        phase_evidence={f"{agent}:{name}": dict(
            evidence_complete=phase["evidence_complete"], issues=phase["issues"],
            matched_nodes=len(phase["nodes"])) for (agent, name), phase in phases.items()})
    return result
