"""Post-run task evidence; assigned intent is never inferred from flight success."""

import math

from .tasks import point_segment
from .truth import clock_to_host


def longest_dwell(rows, target, tolerance, max_gap):
    longest, start, previous = 0.0, None, None
    nearest = None
    for t, position in rows:
        distance = math.dist(position[:3], target) if position is not None else None
        if distance is not None:
            nearest = distance if nearest is None else min(nearest, distance)
        if distance is None or distance > tolerance:
            start, previous = None, None
            continue
        if start is None or previous is None or t - previous > max_gap + 1e-8:
            start = t
        longest = max(longest, t - start)
        previous = t
    return longest, nearest


def coverage_ratio(rows, vehicle, task, altitude, tolerance, max_gap):
    """Cell-center area fraction under a constant ideal horizontal disk footprint."""
    nx = math.ceil(task["width_m"] / task["grid_m"])
    ny = math.ceil(task["height_m"] / task["grid_m"])
    points = []
    segments = []
    previous = None
    for stamp, values in rows:
        if values is None or abs(values[2] - altitude) > tolerance:
            previous = None
            continue
        xy = [values[0] - vehicle["east_m"], values[1] - vehicle["north_m"]]
        points.append(xy)
        if previous is not None and stamp - previous[0] <= max_gap + 1e-8:
            segments.append((previous[1], xy))
        previous = (stamp, xy)
    hit = 0
    radius = task["footprint_radius_m"]
    for ix in range(nx):
        for iy in range(ny):
            center = [(ix + 0.5) * task["width_m"] / nx, (iy + 0.5) * task["height_m"] / ny]
            hit += int(any(math.dist(center, p) <= radius for p in points) or
                       any(point_segment(center, a, b) <= radius for a, b in segments))
    return dict(covered_cells=hit, cells=nx * ny, ratio=hit / (nx * ny),
                model="constant ideal disk; cell centers; linear segments only across valid samples")


def evaluate_task(scenario, traces, events, metadata, time_epoch, clocks=None):
    spec = scenario.get("task_spec")
    labels = dict(schema_version=1, assigned_intent=spec["task"]["type"] if spec else None,
                  observed_behavior={}, mission_success=None, failure_reason=[],
                  run_status=metadata["status"], label_provenance=dict(
                      assigned_intent="TaskSpec author; not inferred psychological intent",
                      observed_behavior="geometric rules on FCU estimated positions",
                      mission_success="geometric task completion, separate from run/data quality"))
    if not spec:
        labels["failure_reason"] = ["no_task_spec"]
        return labels
    task = spec["task"]
    shift = metadata["run_epoch_monotonic_s"] - time_epoch
    failures, uncertain = [], []
    for vehicle in scenario["vehicles"]:
        agent = vehicle["id"]
        rows = traces[agent]
        phase_metrics = []
        for phase in scenario["phases"]:
            starts = [e["t"] + shift for e in events if e["event"] == "phase_start_sent"
                      and e.get("agent_id") == agent and e.get("phase") == phase["name"]]
            ends = [e["t"] + shift for e in events if e["event"] == "phase_finished"
                    and e.get("agent_id") == agent and e.get("phase") == phase["name"]]
            confirmations = [e["t"] + shift for e in events if e["event"] == "task_target_verified"
                             and e.get("agent_id") == agent and e.get("phase") == phase["name"]]
            if ends and confirmations:
                ends = confirmations
            metric = dict(phase=phase["name"], passed=None)
            if not starts or not ends:
                metric["reason"] = "phase_has_no_complete_execution_window"
                uncertain.append(f"{agent}:{phase['name']}:incomplete_phase")
            else:
                window = [(t, p) for t, p in rows if starts[0] <= t <= ends[-1]]
                model = (clocks or {}).get(agent, {})
                dwell_window = window
                if model.get("available"):
                    inverse = dict(knots=[(host, source) for source, host in model["knots"]])
                    dwell_window = [(clock_to_host(t, inverse), p) for t, p in window
                                    if inverse["knots"][0][0] <= t <= inverse["knots"][-1][0]]
                target = phase["targets"][agent]
                dwell, nearest = longest_dwell(dwell_window, [target[k] for k in ("east_m", "north_m", "up_m")],
                                              task["tolerance_m"], scenario["max_gap_s"])
                # One sample period is the explicitly reported dwell discretization allowance.
                passed = nearest is not None and nearest <= task["tolerance_m"] and dwell + 1 / scenario["record_hz"] + 1e-8 >= task["dwell_s"]
                complete = bool(window) and all(p is not None for _, p in window)
                metric.update(passed=passed if passed or complete else None, nearest_m=nearest,
                              longest_dwell_s=dwell, dwell_allowance_s=1 / scenario["record_hz"],
                              dwell_time_basis="FCU_source_seconds" if model.get("available") else "host_receive_fallback")
                if metric["passed"] is False:
                    failures.append(f"{agent}:{phase['name']}:visit_or_dwell_not_met")
                elif metric["passed"] is None:
                    uncertain.append(f"{agent}:{phase['name']}:missing_evidence")
            phase_metrics.append(metric)
        behavior = dict(ordered_waypoint_checks=phase_metrics,
                        confirmed_visits=sum(p["passed"] is True for p in phase_metrics))
        if task["type"] == "coverage_scan":
            coverage = coverage_ratio(rows, vehicle, task, scenario["takeoff_alt_m"],
                                      task["tolerance_m"], scenario["max_gap_s"])
            behavior["coverage"] = coverage
            # Coverage task succeeds on measured covered area; executing every lane is not required.
            failures = [f for f in failures if not f.startswith(agent + ":")]
            uncertain = [f for f in uncertain if not f.startswith(agent + ":")]
            if coverage["ratio"] < task["coverage_required"]:
                if not rows or any(p is None for _, p in rows) or metadata.get("mission_end_monotonic_s") is None:
                    uncertain.append(f"{agent}:coverage_unknown_with_incomplete_evidence")
                else:
                    failures.append(f"{agent}:coverage_below_threshold")
        elif task["type"] == "rectangle_patrol":
            behavior["completed_cycles"] = sum(all(p["passed"] is True for p in phase_metrics[1 + 4 * i:5 + 4 * i])
                for i in range(task["cycles"])) if phase_metrics[0]["passed"] is True else 0
        labels["observed_behavior"][agent] = behavior
    labels["mission_success"] = False if failures else (None if uncertain else True)
    labels["failure_reason"] = failures + uncertain
    return labels
