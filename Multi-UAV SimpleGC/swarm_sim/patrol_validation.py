"""Independent, channel-local evidence for perimeter patrol.

The service interval is fixed by the route-window producer.  Planned routes
provide geometry and visit order, never evidence that a segment was visited.
"""

import math

from .ac4_timing import ordered_route_progress
from .mission_evaluation import window_evidence
from .observations import finite_number


VERSION = "perimeter_revisit_v1"
EPS = 1e-8


def perimeter_segments(region, max_length_m, standoff_m=0.0):
    """Split each side into equal pieces of at most ``max_length_m``."""
    east = region["min_east_m"]
    north = region["min_north_m"]
    width = region["width_m"]
    height = region["height_m"]
    corners = ((east-standoff_m, north-standoff_m),
               (east+width+standoff_m, north-standoff_m),
               (east+width+standoff_m, north+height+standoff_m),
               (east-standoff_m, north+height+standoff_m))
    result = []
    for side in range(4):
        a, b = corners[side], corners[(side+1) % 4]
        count = math.ceil(math.dist(a, b) / max_length_m)
        for piece in range(count):
            lo, hi = piece/count, (piece+1)/count
            start = [a[k] + lo*(b[k]-a[k]) for k in range(2)]
            end = [a[k] + hi*(b[k]-a[k]) for k in range(2)]
            result.append(dict(segment_id=f"side_{side:02d}_part_{piece:03d}", side=side,
                               piece=piece, start_xy_m=start, end_xy_m=end,
                               length_m=math.dist(start, end)))
    return result


def _distance_to_segment(xyz, segment):
    x, y = xyz[:2]
    a, b = segment["start_xy_m"], segment["end_xy_m"]
    dx, dy = b[0]-a[0], b[1]-a[1]
    weight = max(0.0, min(1.0, ((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(x-a[0]-weight*dx, y-a[1]-weight*dy)


def _service_points(rows, start, end, max_gap):
    if not all(finite_number(value) for value in (start, end)) or end < start:
        return None, "missing_or_invalid_service_bounds"
    evidence = window_evidence(rows, start, end, max_gap)
    if not evidence["complete"]:
        return None, "incomplete_service_trajectory"
    # window_evidence adds interpolated boundary points after its raw samples.
    # Preserve one position per instant in chronological order.
    points = sorted(evidence["points"], key=lambda row: row[0])
    distinct = []
    for stamp, xyz in points:
        if not distinct or stamp > distinct[-1][0] + EPS:
            distinct.append((stamp, xyz))
    if not distinct or distinct[0][0] > start + EPS or distinct[-1][0] < end - EPS:
        return None, "service_trajectory_does_not_bracket_bounds"
    return distinct, None


def segment_visits(points, segment, visit_radius_m, agent):
    """Count returns after leaving the 1 m hysteresis band.

    Any segment containing the aircraft at the fixed service start has an
    initial occupancy, not a completed visit.  This also handles the two
    neighboring subsegments when an entry point is at a shared corner.
    """
    leave_radius = visit_radius_m + 1.0
    initial = _distance_to_segment(points[0][1], segment) <= visit_radius_m + EPS
    active, counted = initial, False
    begun, last_inside = None, None
    visits = []
    for stamp, xyz in points:
        distance = _distance_to_segment(xyz, segment)
        if active:
            if distance > leave_radius + EPS:
                if counted:
                    visits.append(dict(agent_id=agent, start_s=begun, end_s=last_inside))
                active, counted, begun, last_inside = False, False, None, None
            elif distance <= visit_radius_m + EPS:
                last_inside = stamp
        elif distance <= visit_radius_m + EPS:
            active, counted, begun, last_inside = True, True, stamp, stamp
    if active and counted:
        visits.append(dict(agent_id=agent, start_s=begun, end_s=last_inside))
    return visits, initial


def _progress(scene, traces, window):
    agent = window["agent_id"]
    phase = window["phase"]
    phase_data = next(p for p in scene["phases"] if p["name"] == phase)
    route = phase_data["routes"][agent]
    model = scene["planning"]["nominal_phase_timing"][phase]
    nominal = model["per_agent_waypoint_arrival_s"][agent]
    start_point = scene["semantic_plan"]["execution_phases"][phase]["agents"][agent]["start_point"]
    lap_nodes = [index for index, point in enumerate(route)
                 if math.dist([point[k] for k in ("east_m", "north_m", "up_m")],
                              [start_point[k] for k in ("east_m", "north_m", "up_m")]) <= 1e-6]
    try:
        result = ordered_route_progress(traces.get(agent, []), route, nominal,
            start_s=window["start_s"], end_s=window["end_s"],
            max_gap_s=scene["max_gap_s"], start_point=start_point,
            lap_node_indices=lap_nodes)
    except (ValueError, KeyError, TypeError) as exc:
        return dict(per_agent_laps_observed=None, first_complete_lap_time_s=None,
                    evidence_complete=False, issues=[f"{type(exc).__name__}: {exc}"])
    first_lap = None
    if lap_nodes:
        first_index = lap_nodes[0]
        prefix = result["node_evidence"][:first_index+1]
        if (len(prefix) == first_index+1 and
                all(item.get("route_index") == index and item.get("evidence_status") == "matched"
                    for index, item in enumerate(prefix))):
            first_lap = prefix[-1]["actual_s"]
            reversal = result.get("backtracking_evidence", {}).get("witness")
            if reversal and reversal.get("actual_s", float("inf")) <= first_lap + EPS:
                first_lap = None
    return dict(per_agent_laps_observed=result["per_agent_laps_observed"],
                first_complete_lap_time_s=first_lap,
                evidence_complete=result["evidence_complete"], issues=result["issues"],
                node_evidence=result.get("node_evidence", []))


def evaluate_channel(scene, traces, windows, clocks):
    """Evaluate visits and three gap types on one channel, without substitution."""
    del clocks  # Positions already belong to the caller's selected channel.
    spec = scene["task_spec"]
    params = spec["mission"]["intent_params"]
    region = next(r for r in spec["scenario"]["regions"]
                  if r["id"] == spec["mission"]["target_region_id"])
    segments = perimeter_segments(region, params["segment_length_m"], params["standoff_m"])
    service = [w for w in windows if w["semantic_phase"] == "patrol" and w["service_enabled"]]
    agents = sorted(v["id"] for v in scene["vehicles"])
    selected = {w["agent_id"]: w for w in service}
    failures = []
    if len(selected) != len(service) or set(selected) != set(agents):
        failures.append("missing_or_duplicate_patrol_service_window")
    bounds = [w.get("start_s") for w in service] + [w.get("end_s") for w in service]
    if not bounds or any(not finite_number(v) for v in bounds):
        failures.append("missing_service_bounds")
    start = min((w["start_s"] for w in service if finite_number(w.get("start_s"))), default=None)
    end = max((w["end_s"] for w in service if finite_number(w.get("end_s"))), default=None)
    points_by_agent, progress = {}, {}
    for agent in agents:
        window = selected.get(agent)
        if window is None:
            progress[agent] = dict(per_agent_laps_observed=None, first_complete_lap_time_s=None,
                                   evidence_complete=False, issues=["missing_service_window"])
            continue
        if window.get("complete_execution_window") is not True:
            failures.append(f"{agent}:truncated_or_unverified_patrol_window")
        points, reason = _service_points(traces.get(agent, []), window.get("start_s"),
                                         window.get("end_s"), scene["max_gap_s"])
        if reason:
            failures.append(f"{agent}:{reason}")
        else:
            points_by_agent[agent] = points
        progress[agent] = _progress(scene, traces, window)
    complete = not failures
    n = len(agents)
    phase = next((p for p in scene["phases"] if p["semantic_phase"] == "patrol"), None)
    speed = phase["speed_m_s"] if phase else spec["execution"]["speed_m_s"]
    perimeter = 2*(region["width_m"]+region["height_m"]+4*params["standoff_m"])
    nominal_interval = perimeter/(n*speed)
    allowed_gap = params["max_revisit_gap_factor"]*nominal_interval
    required_count = params["laps"]*n
    table = []
    for segment in segments:
        visits, initial_occupants = [], []
        for agent, points in points_by_agent.items():
            agent_visits, initial = segment_visits(points, segment, params["visit_radius_m"], agent)
            visits.extend(agent_visits)
            if initial:
                initial_occupants.append(agent)
        visits.sort(key=lambda item: (item["start_s"], item["agent_id"]))
        gaps = []
        if complete:
            if visits:
                gaps.append(dict(kind="initial", duration_s=visits[0]["start_s"]-start,
                                 from_s=start, to_s=visits[0]["start_s"]))
                for before, after in zip(visits, visits[1:]):
                    gaps.append(dict(kind="internal", duration_s=after["start_s"]-before["start_s"],
                                     from_s=before["start_s"], to_s=after["start_s"]))
                gaps.append(dict(kind="terminal", duration_s=end-visits[-1]["end_s"],
                                 from_s=visits[-1]["end_s"], to_s=end))
            else:
                gaps.append(dict(kind="initial_and_terminal", duration_s=end-start,
                                 from_s=start, to_s=end))
        maximum = max((gap["duration_s"] for gap in gaps), default=None)
        table.append(dict(**segment, count=len(visits) if complete else None, observed_lower_bound=len(visits),
                          visits=visits, initially_occupied_by=initial_occupants,
                          max_gap_s=maximum, max_gap_types=[g["kind"] for g in gaps
                              if maximum is not None and abs(g["duration_s"]-maximum) <= EPS], gaps=gaps))
    count_values = [s["count"] for s in table] if complete else []
    gap_values = [s["max_gap_s"] for s in table] if complete else []
    min_visits = min(count_values) if count_values else None
    max_gap = max(gap_values) if gap_values else None
    coverage = sum(bool(s["visits"]) for s in table)/len(table) if complete else None
    first_coverage = max(s["visits"][0]["start_s"] for s in table) if complete and all(s["visits"] for s in table) else None
    first_lap = min((p["first_complete_lap_time_s"] for p in progress.values()
                     if p["first_complete_lap_time_s"] is not None), default=None)
    visits_pass = None if not complete else min_visits >= required_count
    gap_pass = None if not complete else max_gap <= allowed_gap + EPS
    patrol_success = (False if False in (visits_pass, gap_pass) else
                      True if visits_pass is True and gap_pass is True else None)
    details = dict(version=VERSION, service_window_s=[start, end], evidence_complete=complete,
                   evidence_issues=failures, segment_count=len(segments), required_visits_per_segment=required_count,
                   nominal_revisit_interval_s=nominal_interval, allowed_gap_s=allowed_gap,
                   group_segment_visit_counts={s["segment_id"]: s["count"] for s in table},
                   segments=table, per_agent_progress=progress,
                   per_agent_laps_observed={a: p["per_agent_laps_observed"] for a, p in progress.items()},
                   first_boundary_coverage_time_s=first_coverage,
                   first_complete_lap_time_s=first_lap,
                   min_segment_visits=min_visits, max_revisit_gap_s=max_gap,
                   loop_segment_coverage=coverage, visits_pass=visits_pass,
                   max_gap_pass=gap_pass, patrol_success=patrol_success)
    return dict(conditions=dict(visits=visits_pass, max_gap=gap_pass),
                metrics=dict(perimeter_revisit=details,
                             per_agent_laps_observed=details["per_agent_laps_observed"],
                             first_boundary_coverage_time_s=first_coverage,
                             first_complete_lap_time_s=first_lap))


def behavior_labels(scene, truth):
    result = truth.get("perimeter_revisit", {})
    observed = result.get("patrol_success")
    return dict(planned_behaviors=["perimeter_loop"], observed_behaviors=[dict(
        name="perimeter_loop", agent_ids=[v["id"] for v in scene["vehicles"]],
        status="verified" if observed is True else "failed" if observed is False else "unknown",
        evidence_basis="SIM_truth_positions_perimeter_revisit", rule_version=VERSION,
        min_segment_visits=result.get("min_segment_visits"),
        max_revisit_gap_s=result.get("max_revisit_gap_s"))])
