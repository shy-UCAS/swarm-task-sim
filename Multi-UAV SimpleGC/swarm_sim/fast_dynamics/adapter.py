"""Adapt actual common-clock trajectories to the existing geometric validators.

The TaskSpec remains frozen. Only source metadata and execution windows change;
registered intent geometry and its three-valued outcomes are reused unchanged.
"""

import copy
from contextlib import contextmanager
from contextvars import ContextVar
import json
import math

import numpy as np

from ..mission_evaluation import tri_and, window_evidence
from ..mission_evaluation_v3 import _channel
from ..protocol import fast_dynamics_m2_protocol as fast_dynamics_protocol
from ..registry import get_intent
from ..route_windows import service_window_view

ADAPTER_VERSION = "fast_dynamics_semantic_adapter_v2"
_SEMANTIC_REUSE = ContextVar("fast_dynamics_semantic_reuse", default=None)


@contextmanager
def reuse_semantics(*, enabled=True):
    """Reuse one pure result within one data pipeline; never cache file validation.

    Exact serialized input bytes are the key (not paths, mtimes or a digest).
    A single entry bounds retained memory. Copies isolate callers from mutation;
    the context token also restores an enclosing scope after errors.
    """
    cache = dict(key=None, value=None, hits=0, misses=0) if enabled else None
    token = _SEMANTIC_REUSE.set(cache)
    try:
        yield cache
    finally:
        _SEMANTIC_REUSE.reset(token)


def result_value(result, key):
    return result[key] if isinstance(result, dict) else getattr(result, key)


def checked_samples(result):
    """Reject malformed engine output rather than converting it to task failure."""
    agents = list(result_value(result, "agent_ids"))
    if not agents or agents != sorted(set(agents)) or any(not isinstance(a, str) or not a for a in agents):
        raise ValueError("engine agent IDs must be unique, sorted, nonempty strings")
    end = result_value(result, "end_us")
    if isinstance(end, bool) or not isinstance(end, (int, np.integer)) or end < 0:
        raise ValueError("end_us must be a nonnegative integer")
    end = int(end)
    streams = {}
    for prefix in ("", "support_"):
        raw_times = np.asarray(result_value(result, prefix + "time_us"))
        if raw_times.ndim != 1 or raw_times.dtype.kind not in "iu":
            raise ValueError("sample clocks must be one-dimensional integer microseconds")
        times = raw_times.astype(np.int64)
        p = np.asarray(result_value(result, prefix + "positions"), dtype=float)
        v = np.asarray(result_value(result, prefix + "velocities"), dtype=float)
        if p.shape != (len(times), len(agents), 3) or v.shape != p.shape:
            raise ValueError("state arrays must have shape (time, agent, 3)")
        if not np.isfinite(p).all() or not np.isfinite(v).all():
            raise ValueError("nonfinite numerical state is an engine error")
        if len(times) and (times[0] < 0 or times[-1] > end or np.any(np.diff(times) <= 0)):
            raise ValueError("sample clocks must increase within the episode")
        if not prefix:
            if not np.array_equal(times, np.arange(0, end, 100_000, dtype=np.int64)):
                raise ValueError("output must follow the 10 Hz half-open simulation grid")
        elif end > 0 and (len(times) < 2 or times[0] != 0 or times[-1] != end):
            raise ValueError("support trajectory must include both mission boundaries")
        streams[prefix] = (times, p, v)
    times, p, v = streams[""]
    support_t, support_p, support_v = streams["support_"]
    if len(times):
        indices = np.searchsorted(support_t, times)
        if (np.any(indices >= len(support_t)) or not np.array_equal(support_t[indices], times)
                or not np.array_equal(support_p[indices], p) or not np.array_equal(support_v[indices], v)):
            raise ValueError("output states must match their support samples")
    return agents, end, streams


def traces_from_samples(agents, times, positions, velocities):
    return {agent: [(int(t) / 1e6, [*positions[k, i].tolist(), *velocities[k, i].tolist()])
                    for k, t in enumerate(times)] for i, agent in enumerate(agents)}


def _events(events, kind, phase, agent=None):
    selected = [e for e in events if e.get("event") == kind and e.get("phase") == phase
                and (agent is None or e.get("agent_id") == agent)]
    if kind in ("phase_arrived", "phase_hold_ended"):
        resets = [int(e["t_us"]) for e in events if e.get("event") == "phase_confirmation_reset"
                  and e.get("phase") == phase and e.get("agent_id") == agent]
        if resets:
            selected = [e for e in selected if int(e["t_us"]) >= max(resets)]
    return sorted(int(e["t_us"]) / 1e6 for e in selected)


def valid_epoch_events(events, phase, agent):
    """A same-tick reset revokes the prior epoch, even when times coincide."""
    selected = [e for e in events if e.get("phase") == phase and e.get("agent_id") == agent]
    epoch = max((e.get("epoch", 0) for e in selected), default=0)
    return [e for e in selected if e.get("epoch", 0) == epoch]


def observed_route_complete(trace, start_point, route, start, end):
    """Check ordered original-node visits from actual EN support chords.

    U is retained as a true state; service-height validity belongs to the
    registered intent rule, not to this execution progress condition.
    """
    if start is None or end is None or end < start:
        return False
    if not route:
        return True
    nodes = [start_point, *route]
    xy = [[point["east_m"], point["north_m"]] for point in nodes]
    xy = np.array([point for i, point in enumerate(xy) if i == 0 or point != xy[i-1]], dtype=float)
    if len(xy) == 1:
        return True
    lengths = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    if np.any(lengths <= 0):
        return False
    rows = [(t, np.asarray(values[:2], dtype=float)) for t, values in trace
            if start - 1e-9 <= t <= end + 1e-9 and values is not None]
    if not rows:
        return False
    cursor = float(start)
    for index, target in enumerate(xy):
        adjacent = lengths[max(0, index-1):min(len(lengths), index+1)]
        radius = min(.5, .2 * float(np.min(adjacent)))
        found = None
        for (ta, pa), (tb, pb) in zip(rows, rows[1:]):
            if tb < cursor - 1e-9:
                continue
            lower = max(0., (cursor-ta)/(tb-ta))
            if lower > 1.:
                continue
            delta = pb-pa
            q = pa + lower*delta - target
            if float(q @ q) <= radius**2 + 1e-12:
                found = ta + lower*(tb-ta)
                break
            a = float(delta @ delta)
            b = 2*float((pa-target) @ delta)
            c = float((pa-target) @ (pa-target))-radius**2
            disc = b*b-4*a*c
            if a > 0 and disc >= 0:
                hit = (-b-math.sqrt(max(0., disc)))/(2*a)
                if lower-1e-10 <= hit <= 1.+1e-10:
                    found = ta+max(lower, min(1., hit))*(tb-ta)
                    break
        if found is None:
            return False
        cursor = found
    return True


def build_windows(scene, traces, events, end_s, channel):
    """Use actual starts and measured arrivals, never nominal route timing.

    A reported arrival is only a search anchor. It is independently verified
    with the frozen route-window distance and 0.3 m/s horizontal-speed rule.
    """
    spec = scene["task_spec"]
    intent = get_intent(spec["mission"]["intent"])
    windows = []
    for index, phase in enumerate(scene["phases"]):
        name = phase["name"]
        plan = scene["semantic_plan"]["execution_phases"][name]
        releases = _events(events, "phase_released", name)
        next_releases = (_events(events, "phase_released", scene["phases"][index + 1]["name"])
                         if index + 1 < len(scene["phases"]) else [])
        barriers = _events(events, "phase_completed", name)
        end = barriers[0] if len(barriers) == 1 else (next_releases[0] if len(next_releases) == 1 else end_s)
        for vehicle in scene["vehicles"]:
            agent = vehicle["id"]
            role = plan["agents"][agent]
            route = phase["routes"][agent]
            starts = _events(events, "phase_started", name, agent)
            epoch_events = valid_epoch_events(events, name, agent)
            arrivals = _events(epoch_events, "phase_arrived", name, agent)
            holds = _events(epoch_events, "phase_hold_ended", name, agent)
            route_done = _events(events, "route_completed", name, agent)
            start = starts[0] if len(starts) == 1 else None
            target = role.get("terminal_point", route[-1] if route else role["start_point"])
            xyz = [target[k] for k in ("east_m", "north_m", "up_m")]
            anchor = arrivals[0] if len(arrivals) == 1 else None
            valid = start is not None and anchor is not None and 0 <= start <= anchor <= end
            candidates = [(t, values) for t, values in traces.get(agent, [])
                          if valid and anchor <= t <= end and values is not None]
            stops = [(t, values) for t, values in candidates
                     if math.dist(values[:3], xyz) <= spec["execution"]["arrival_tolerance_m"] + 1e-8
                     and math.hypot(*values[3:5]) <= .3 + 1e-8]
            arrival = stops[0][0] if stops else None
            ordered = observed_route_complete(traces.get(agent, []), role["start_point"], route, start, anchor)
            complete = bool(valid and arrival is not None and len(holds) == 1 and arrival <= holds[0] <= end
                            and len(barriers) == 1 and len(route_done) == 1 and route_done[0] <= anchor
                            and ordered)
            evidence = window_evidence(traces.get(agent, []), start, end, spec["execution"]["max_gap_s"]) if start is not None else {"complete": False}
            windows.append(dict(agent_id=agent, phase=name, semantic_phase=plan["semantic_phase"],
                role=role["role"] if route else "hold_no_op", service_enabled=bool(route) and
                    plan["semantic_phase"] in intent.service_phases and role.get("service_enabled") is True,
                partition_id=role.get("partition_id"), channel=channel, start_s=start, arrival_s=arrival,
                end_s=end, phase_release_s=releases[0] if len(releases) == 1 else None,
                start_event="phase_started", end_event="phase_completed_or_actual_end",
                arrival_source="support_trajectory_stop" if arrival is not None else "unverified",
                arrival_reason="frozen_distance_and_horizontal_speed_rule" if arrival is not None else "missing_or_unverified_actual_arrival",
                arrival_verified=arrival is not None, chronology_valid=valid,
                terminal_point=copy.deepcopy(target), complete_execution_window=complete,
                trajectory_evidence_complete=evidence["complete"], route_complete_verified=ordered,
                confirmation_epoch=max((e.get("epoch", 0) for e in epoch_events), default=0), source=ADAPTER_VERSION,
                speed_time_basis="sim_clock_seconds", speed_processing_version="ideal_state_velocity_v1",
                barrier_wait_sim_s=end - arrival if arrival is not None else None))
    return windows


def analyze_semantics(scene, traces, events, end_s, status):
    cache = _SEMANTIC_REUSE.get()
    if cache is None:
        return _analyze_semantics(scene, traces, events, end_s, status)
    key = json.dumps((scene, traces, events, end_s, status), sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    if key == cache["key"]:
        cache["hits"] += 1
        return copy.deepcopy(cache["value"])
    value = _analyze_semantics(scene, traces, events, end_s, status)
    cache.update(key=key, value=copy.deepcopy(value), misses=cache["misses"] + 1)
    return value


def _analyze_semantics(scene, traces, events, end_s, status):
    spec = scene["task_spec"]
    if spec["execution"]["control_mode"] != "semantic_phase_route_v1":
        raise ValueError("M2 semantic adapter requires continuous routes")
    intent = get_intent(spec["mission"]["intent"])
    clocks = {agent: dict(kind="simulation_clock", start_s=0.0, end_s=end_s) for agent in traces}
    channels, results, conditions = {}, {}, {}
    for channel in ("truth", "observation"):
        windows = build_windows(scene, traces, events, end_s, channel)
        channels[channel] = windows
        returns = copy.deepcopy(windows)
        for window in returns:
            if window["role"] == "hold_no_op" and window["semantic_phase"] == "return":
                window["role"] = "return"
        metric, condition = _channel(scene, traces, service_window_view(windows), clocks, intent, returns, progress_mapping_version="ordered_route_progress_v2", patrol_validator_version="perimeter_revisit_v2")
        for value in metric.get("return_to_launch", {}).get("per_agent", {}).values():
            value["time_basis"] = "sim_clock_seconds"
        results[channel], conditions[channel] = metric, condition
    truth, observation = results["truth"], results["observation"]
    left, right = truth["mission_success"], observation["mission_success"]
    consistency = "unknown" if left is None or right is None else "agree" if conditions["truth"] == conditions["observation"] else "disagree"
    protocol = fast_dynamics_protocol()
    behavior = intent.behavior_labels(scene, truth)
    for item in behavior["observed_behaviors"]:
        item["evidence_basis"] = "fast_dynamics_truth_positions_service_window"
    labels = dict(schema_version=3, task_kind="mission_v3", requested_intent=intent.name,
        assigned_intent=intent.name, objective=spec["mission"]["intent_params"]["objective"],
        planned_phases=list(dict.fromkeys(
            scene["semantic_plan"]["execution_phases"][phase["name"]]["semantic_phase"]
            for phase in scene["phases"])), **behavior, mission_success=left,
        mission_success_observation=right, semantic_consistency=consistency,
        mission_metrics=results, run_status=status,
        label_provenance=dict(requested_intent="TaskSpec author; not inferred hidden intent",
            mission_success="fast_dynamics plant position support samples",
            mission_success_observation="ideal_state observer; derived from plant, not an independent sensor",
            semantic_validation_version=protocol["semantic_validation_version"],
            semantic_adapter_version=ADAPTER_VERSION, validator_versions={intent.name: "perimeter_revisit_v2" if intent.name == "patrol" else intent.validator_version},
            scope="airborne_mission; no takeoff/landing, FCU, IMU or firmware validation"))
    semantic = dict(schema_version=1, semantic_validation_version=protocol["semantic_validation_version"],
        mission_success=left, mission_success_observation=right, semantic_consistency=consistency,
        truth=truth, observation=observation, condition_results=conditions,
        pass_for_eligibility=left is True and right is True and consistency == "agree")
    windows = dict(schema_version=1, window_version=ADAPTER_VERSION, source="actual_simulation_events_and_support_trajectory",
        time_base="sim_clock", channels=channels, windows=channels["observation"],
        boundary_method="internal-step support including actual endpoint; existing piecewise-linear geometry",
        limitation="support sampling bounds event resolution; ideal observation and plant are not independent sensors")
    return labels, semantic, windows
