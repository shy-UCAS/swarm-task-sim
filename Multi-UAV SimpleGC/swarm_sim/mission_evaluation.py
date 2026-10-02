"""Independent shared-area evidence, never inferred from planned coverage."""

import math

from .observations import finite_number
from .truth import clock_to_host
from .protocol import SHARED_LABEL_SCHEMA_VERSION, SHARED_SEMANTIC_VERSION


SEMANTIC_RULE_VERSION = SHARED_SEMANTIC_VERSION
LABEL_SCHEMA_VERSION = SHARED_LABEL_SCHEMA_VERSION
EPS = 1e-8


def tri_and(values):
    values = list(values)
    return False if False in values else (None if None in values else True)


def position_valid(value):
    return value is not None and len(value) >= 3 and all(finite_number(x) for x in value[:3])


def source_time(host, model):
    """Invert an audited passive model; do not extrapolate at either boundary."""
    if not model or not model.get("available"):
        return None
    knots = model.get("knots", [])
    if len(knots) < 2 or not knots[0][1] <= host <= knots[-1][1]:
        return None
    return clock_to_host(host, {"knots": [(h, s) for s, h in knots]})


def window_evidence(rows, start, end, max_gap, edge_allowance=0.0):
    """Clip only valid adjacent evidence; invalid points remain segment barriers.

    The optional edge allowance is for sampled lifecycle bounds, never for
    connecting an internal gap. Mission geometry uses the exact boundaries.
    """
    if end < start or any(not finite_number(t) for t, _ in rows):
        return dict(points=[], segments=[], complete=False, invalid_timeline=True)
    if any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        return dict(points=[], segments=[], complete=False, invalid_timeline=True)
    points = [(t, p[:3]) for t, p in rows if start <= t <= end and position_valid(p)]
    segments = []
    for (ta, a), (tb, b) in zip(rows, rows[1:]):
        if tb < start or ta > end or tb - ta > max_gap + EPS:
            continue
        if not position_valid(a) or not position_valid(b):
            continue
        left, right = max(start, ta), min(end, tb)
        if right < left:
            continue
        pa = [a[k] + (b[k] - a[k]) * (left - ta) / (tb - ta) for k in range(3)]
        pb = [a[k] + (b[k] - a[k]) * (right - ta) / (tb - ta) for k in range(3)]
        segments.append((left, right, pa, pb))
        points.extend(((left, pa), (right, pb)))
    covered = start
    complete = bool(points) and not any(start <= t <= end and not position_valid(p) for t, p in rows)
    for left, right, _, _ in segments:
        allowance = edge_allowance if covered == start else 0.0
        if left > covered + allowance + EPS:
            complete = False
        covered = max(covered, right)
    complete = complete and covered >= end - edge_allowance - EPS
    if abs(end - start) <= EPS:
        complete = any(abs(t - start) <= EPS for t, _ in points)
    return dict(points=points, segments=segments, complete=complete, invalid_timeline=False)


def _event_times(events, kind, agent, phase, shift):
    return sorted(e["t"] + shift for e in events if e.get("event") == kind
                  and e.get("agent_id") == agent and e.get("phase") == phase
                  and finite_number(e.get("t")))


def execution_windows(scene, events, metadata, time_epoch):
    shift = metadata["run_epoch_monotonic_s"] - time_epoch
    run_end = metadata.get("elapsed_s", 0) + shift
    mapping = scene["semantic_plan"]["execution_phases"]
    windows = []
    for phase in scene["phases"]:
        name = phase["name"]
        planned = mapping[name]
        for vehicle in scene["vehicles"]:
            agent = vehicle["id"]
            role = planned["agents"][agent]
            confirmed = _event_times(events, "phase_auto_confirmed", agent, name, shift)
            sent = _event_times(events, "phase_start_sent", agent, name, shift)
            starts = confirmed or sent
            ends = _event_times(events, "task_target_verified", agent, name, shift)
            start = starts[0] if starts else None
            later = [e["t"] + shift for e in events if e.get("event") == "phase_start_sent"
                     and e.get("agent_id") == agent and e.get("phase") != name
                     and finite_number(e.get("t")) and start is not None and e["t"] + shift > start]
            completed = start is not None and bool(ends) and ends[-1] >= start
            end = ends[-1] if completed else (min([run_end, *later]) if start is not None else None)
            if end is not None and end < start:
                end = start
                completed = False
            finished = _event_times(events, "phase_finished", agent, name, shift)
            all_finished = [_event_times(events, "phase_finished", other["id"], name, shift)
                            for other in scene["vehicles"]]
            barrier_wait = (max(group[-1] for group in all_finished) - finished[-1]
                            if finished and all(all_finished) else None)
            scheduling_wait = min(later) - end if completed and later else None
            windows.append(dict(agent_id=agent, phase=name, semantic_phase=planned["semantic_phase"],
                                role=role["role"], service_enabled=role["service_enabled"] is True,
                                partition_id=role.get("partition_id"), start_s=start, end_s=end,
                                complete_execution_window=completed,
                                start_event="phase_auto_confirmed" if confirmed else "phase_start_sent",
                                end_event="task_target_verified" if completed else "next_phase_or_run_end",
                                barrier_wait_host_s=barrier_wait, scheduling_wait_host_s=scheduling_wait,
                                source="execution_events + compiled_semantic_plan"))
    return windows


def _segment_distance(point, a, b):
    delta = [b[i] - a[i] for i in range(2)]
    length2 = sum(x * x for x in delta)
    weight = max(0.0, min(1.0, sum((point[i] - a[i]) * delta[i] for i in range(2)) / length2)) if length2 else 0
    return math.hypot(*(point[i] - a[i] - weight * delta[i] for i in range(2)))


def _grid(region, resolution):
    nx, ny = math.ceil(region["width_m"] / resolution), math.ceil(region["height_m"] / resolution)
    centers = [(region["min_east_m"] + (ix + 0.5) * region["width_m"] / nx,
                region["min_north_m"] + (iy + 0.5) * region["height_m"] / ny)
               for ix in range(nx) for iy in range(ny)]
    return centers, dict(requested_grid_m=resolution, cells=nx * ny, nx=nx, ny=ny,
                         cell_width_m=region["width_m"] / nx, cell_height_m=region["height_m"] / ny,
                         discretization="equal_area_cell_centers", area_weighting="uniform")


def _return_result(scene, traces, windows, clocks):
    spec = scene["task_spec"]
    if not spec["mission"]["return_required"]:
        return dict(required=False, success=True, per_agent={})
    execution = spec["execution"]
    per_agent = {}
    for vehicle in scene["vehicles"]:
        agent = vehicle["id"]
        selected = [w for w in windows if w["agent_id"] == agent and w["role"] == "return"]
        result = dict(success=None, longest_dwell_s=0.0, nearest_m=None,
                      target=[vehicle["east_m"], vehicle["north_m"], execution["takeoff_alt_m"]],
                      required_dwell_s=execution["confirmation_dwell_s"],
                      dwell_allowance_s=1 / execution["record_hz"], time_basis="FCU_source_seconds")
        if not selected or selected[-1]["start_s"] is None:
            result["reason"] = "return_window_missing"
            per_agent[agent] = result
            continue
        window = selected[-1]
        mapped_end = source_time(window["end_s"], clocks.get(agent))
        mapped_previous_tick = source_time(window["end_s"] - 1 / execution["record_hz"], clocks.get(agent))
        if mapped_end is not None and mapped_previous_tick is not None:
            result["dwell_allowance_s"] = mapped_end - mapped_previous_tick
        else:
            result["dwell_allowance_s"] = 0.0
        evidence = window_evidence(traces.get(agent, []), window["start_s"], window["end_s"], execution["max_gap_s"])
        target, tolerance = result["target"], execution["arrival_tolerance_m"]
        distances = [math.dist(p, target) for _, p in evidence["points"]]
        result["nearest_m"] = min(distances) if distances else None
        inside_intervals = []
        time_known = True
        for left, right, a, b in evidence["segments"]:
            if max(math.dist(a, target), math.dist(b, target)) > tolerance + EPS:
                continue
            source_left, source_right = source_time(left, clocks.get(agent)), source_time(right, clocks.get(agent))
            if source_left is None or source_right is None:
                time_known = False
                continue
            if inside_intervals and left <= inside_intervals[-1][1] + EPS:
                inside_intervals[-1] = (inside_intervals[-1][0], right, inside_intervals[-1][2], source_right)
            else:
                inside_intervals.append((left, right, source_left, source_right))
        result["longest_dwell_s"] = max((b - a for _, _, a, b in inside_intervals), default=0.0)
        visited = result["nearest_m"] is not None and result["nearest_m"] <= tolerance + EPS
        passed = visited and (execution["confirmation_dwell_s"] == 0 or (
            bool(inside_intervals) and result["longest_dwell_s"] + result["dwell_allowance_s"] + EPS >= execution["confirmation_dwell_s"]))
        complete = window["complete_execution_window"] and evidence["complete"]
        result["success"] = True if passed else (False if complete and (not visited or time_known) else None)
        result.update(evidence_complete=complete, source_duration_available=time_known and bool(inside_intervals),
                      reason="return_satisfied" if passed else "return_not_satisfied_or_incomplete")
        per_agent[agent] = result
    return dict(required=True, success=tri_and(r["success"] for r in per_agent.values()), per_agent=per_agent)


def _evaluate_channel(scene, traces, windows, centers, grid_info, clocks):
    spec = scene["task_spec"]
    model, execution = spec["mission"]["observation_model"], spec["execution"]
    per_agent, sets, complete = {}, {}, True
    all_service = [w for w in windows if w["role"] == "observe" and w["service_enabled"]]
    if not all_service:
        complete = False
    for vehicle in scene["vehicles"]:
        agent = vehicle["id"]
        service = [w for w in all_service if w["agent_id"] == agent]
        points, segments, agent_complete, missing = [], [], True, 0
        for window in service:
            if window["start_s"] is None:
                agent_complete = False
                missing += 1
                continue
            evidence = window_evidence(traces.get(agent, []), window["start_s"], window["end_s"], execution["max_gap_s"])
            agent_complete &= window["complete_execution_window"] and evidence["complete"]
            allowed = lambda p: abs(p[2] - execution["takeoff_alt_m"]) <= model["height_tolerance_m"] + EPS
            height_rows = [(stamp, values if position_valid(values) and allowed(values) else None)
                           for stamp, values in traces.get(agent, [])]
            height_evidence = window_evidence(height_rows, window["start_s"], window["end_s"], execution["max_gap_s"])
            points.extend(p[:2] for _, p in height_evidence["points"])
            # Entire clipped segment must remain inside the height band. An
            # out-of-height endpoint breaks service, even with finite position.
            segments.extend((a[:2], b[:2]) for _, _, a, b in height_evidence["segments"])
        covered = {index for index, center in enumerate(centers) if
                   any(math.dist(center, p) <= model["radius_m"] + EPS for p in points) or
                   any(_segment_distance(center, a, b) <= model["radius_m"] + EPS for a, b in segments)}
        sets[agent] = covered
        complete &= agent_complete
        per_agent[agent] = dict(covered_cells=len(covered), coverage_ratio=len(covered) / len(centers),
                               evidence_complete=agent_complete, service_windows=len(service),
                               missing_service_windows=missing, valid_service_points=len(points))
    union = set().union(*sets.values())
    repeats = {cell for cell in union if sum(cell in cells for cells in sets.values()) > 1}
    for agent, covered in sets.items():
        without = set().union(*(cells for other, cells in sets.items() if other != agent))
        per_agent[agent]["leave_one_out_coverage_drop"] = (len(union) - len(without)) / len(centers)
    ratio = len(union) / len(centers)
    success = True if ratio + EPS >= spec["mission"]["coverage_required"] else (False if complete else None)
    coverage = dict(grid_info, model="ideal_horizontal_disk", model_version="ideal_horizontal_disk_v1",
                    covered_cells=len(union), global_coverage_ratio=ratio,
                    required_ratio=spec["mission"]["coverage_required"], success=success,
                    evidence_complete=complete, repeated_cells=len(repeats),
                    repeated_coverage_cell_ratio=len(repeats) / len(centers),
                    repeated_fraction_of_covered=len(repeats) / len(union) if union else 0.0,
                    observing_agents=sum(bool(cells) for cells in sets.values()), per_agent=per_agent)
    returned = _return_result(scene, traces, windows, clocks)
    return dict(coverage=coverage, return_to_launch=returned,
                mission_success=tri_and([coverage["success"], returned["success"]]))


def evaluate_mission(scene, traces, truth_traces, events, metadata, time_epoch, clocks=None):
    """Evaluate v2 independently on SIM truth and cooperative FCU telemetry."""
    spec = scene["task_spec"]
    if spec.get("schema_version") == 3:
        from .mission_evaluation_v3 import evaluate_mission_v3
        return evaluate_mission_v3(scene, traces, truth_traces, events, metadata, time_epoch, clocks)
    if spec.get("schema_version") != 2:
        raise ValueError("shared mission evaluation requires TaskSpec schema_version 2")
    clocks = clocks or {}
    mission = spec["mission"]
    region = next(r for r in spec["scenario"]["regions"] if r["id"] == mission["target_region_id"])
    centers, grid_info = _grid(region, mission["observation_model"]["grid_m"])
    windows = execution_windows(scene, events, metadata, time_epoch)
    truth = _evaluate_channel(scene, truth_traces, windows, centers, grid_info, clocks)
    observation = _evaluate_channel(scene, traces, windows, centers, grid_info, clocks)
    left, right = truth["mission_success"], observation["mission_success"]
    consistency = "unknown" if left is None or right is None else ("agree" if left == right else "disagree")
    # Also expose disagreement of individual known conditions, even if another
    # failed condition gives both channels the same overall false result.
    comparisons = [(truth["coverage"]["success"], observation["coverage"]["success"]),
                   (truth["return_to_launch"]["success"], observation["return_to_launch"]["success"])]
    if any(a is not None and b is not None and a != b for a, b in comparisons):
        consistency = "disagree"
    labels = dict(schema_version=LABEL_SCHEMA_VERSION, task_kind="mission_v2",
                  requested_intent=mission["intent"], assigned_intent=mission["intent"],
                  objective=mission["objective"], planned_behaviors=["area_scan"],
                  planned_phases=list(dict.fromkeys(w["semantic_phase"] for w in windows)),
                  observed_behaviors=[dict(name="coverage", agent_ids=[v["id"] for v in scene["vehicles"]],
                       status="verified" if truth["coverage"]["success"] is True else (
                           "failed" if truth["coverage"]["success"] is False else "unknown"),
                       evidence_basis="SIM_truth_positions", rule_version=SEMANTIC_RULE_VERSION)],
                  unverified_behaviors={"split": "not_evaluated", "merge": "not_evaluated", "formation_change": "not_evaluated"},
                  mission_success=left, mission_success_observation=right, semantic_consistency=consistency,
                  mission_metrics={"truth": truth, "observation": observation}, run_status=metadata.get("status"),
                  label_provenance=dict(requested_intent="TaskSpec author; not inferred hidden intent",
                      mission_success="SIM_truth_positions with passive source-clock alignment",
                      mission_success_observation="FCU estimated positions; independent geometric pass",
                      semantic_windows="execution_events + compiled_semantic_plan",
                      semantic_validation_version=SEMANTIC_RULE_VERSION,
                      scope="ideal geometric area observation; no physical detection or inferred tactical intent"))
    validation = dict(schema_version=1, semantic_validation_version=SEMANTIC_RULE_VERSION,
                      mission_success=left, mission_success_observation=right, semantic_consistency=consistency,
                      truth=truth, observation=observation,
                      pass_for_eligibility=left is True and right is True and consistency == "agree")
    wait_summary = {v["id"]: dict(
        barrier_wait_host_s=sum(w["barrier_wait_host_s"] for w in windows if w["agent_id"] == v["id"] and w["barrier_wait_host_s"] is not None),
        scheduling_wait_host_s=sum(w["scheduling_wait_host_s"] for w in windows if w["agent_id"] == v["id"] and w["scheduling_wait_host_s"] is not None),
        idle_padding_steps=sum(w["agent_id"] == v["id"] and w["role"] == "idle_padding" for w in windows),
        unmeasured_barrier_windows=sum(w["agent_id"] == v["id"] and w["barrier_wait_host_s"] is None for w in windows))
        for v in scene["vehicles"]}
    return dict(labels=labels, semantic_validation=validation,
                phase_windows=dict(schema_version=1, source="execution_events + compiled_semantic_plan",
                                   time_epoch_host_s=time_epoch, windows=windows, per_agent_wait=wait_summary,
                                   wait_definitions=dict(barrier_wait_host_s="latest phase_finished among all agents minus this agent phase_finished",
                                       scheduling_wait_host_s="next phase_start_sent minus this agent task_target_verified; absent at final phase",
                                       caution="host event timing proxies; not inferred coordination or exact stationary time")))
