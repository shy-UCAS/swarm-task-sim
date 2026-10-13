"""Adapt actual common-clock trajectories to the existing geometric validators.

The TaskSpec remains frozen. Only source metadata and execution windows change;
registered intent geometry and its three-valued outcomes are reused unchanged.
"""

import copy
import math

import numpy as np

from ..mission_evaluation import tri_and, window_evidence
from ..mission_evaluation_v3 import _channel
from ..protocol import fast_dynamics_protocol
from ..registry import get_intent
from ..route_windows import service_window_view

ADAPTER_VERSION = "fast_dynamics_semantic_adapter_v1"


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
        end = next_releases[0] if len(next_releases) == 1 else end_s
        for vehicle in scene["vehicles"]:
            agent = vehicle["id"]
            role = plan["agents"][agent]
            route = phase["routes"][agent]
            starts = _events(events, "phase_started", name, agent)
            arrivals = _events(events, "phase_arrived", name, agent)
            holds = _events(events, "phase_hold_ended", name, agent)
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
            complete = bool(valid and arrival is not None and len(holds) == 1 and arrival <= holds[0] <= end)
            evidence = window_evidence(traces.get(agent, []), start, end, spec["execution"]["max_gap_s"]) if start is not None else {"complete": False}
            windows.append(dict(agent_id=agent, phase=name, semantic_phase=plan["semantic_phase"],
                role=role["role"] if route else "hold_no_op", service_enabled=bool(route) and
                    plan["semantic_phase"] in intent.service_phases and role.get("service_enabled") is True,
                partition_id=role.get("partition_id"), channel=channel, start_s=start, arrival_s=arrival,
                end_s=end, phase_release_s=releases[0] if len(releases) == 1 else None,
                start_event="phase_started", end_event="next_phase_released_or_actual_end",
                arrival_source="support_trajectory_stop" if arrival is not None else "unverified",
                arrival_reason="frozen_distance_and_horizontal_speed_rule" if arrival is not None else "missing_or_unverified_actual_arrival",
                arrival_verified=arrival is not None, chronology_valid=valid,
                terminal_point=copy.deepcopy(target), complete_execution_window=complete,
                trajectory_evidence_complete=evidence["complete"], source=ADAPTER_VERSION,
                speed_time_basis="sim_clock_seconds", speed_processing_version="ideal_state_velocity_v1",
                barrier_wait_sim_s=end - arrival if arrival is not None else None))
    return windows


def analyze_semantics(scene, traces, events, end_s, status):
    spec = scene["task_spec"]
    if spec["mission"]["intent"] != "rapid_passage" or spec["execution"]["control_mode"] != "semantic_phase_route_v1":
        raise ValueError("M1 semantic adapter supports rapid_passage continuous routes only")
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
        metric, condition = _channel(scene, traces, service_window_view(windows), clocks, intent, returns)
        for value in metric.get("return_to_launch", {}).get("per_agent", {}).values():
            value["time_basis"] = "sim_clock_seconds"
        results[channel], conditions[channel] = metric, condition
    truth, observation = results["truth"], results["observation"]
    left, right = truth["mission_success"], observation["mission_success"]
    consistency = "unknown" if left is None or right is None else "agree" if conditions["truth"] == conditions["observation"] else "disagree"
    protocol = fast_dynamics_protocol()
    behavior = intent.behavior_labels(scene, truth)
    for item in behavior["observed_behaviors"]:
        item["evidence_basis"] = "fast_dynamics_truth_positions_transit_window"
    labels = dict(schema_version=3, task_kind="mission_v3", requested_intent=intent.name,
        assigned_intent=intent.name, objective=spec["mission"]["intent_params"]["objective"],
        planned_phases=list(intent.semantic_phases), **behavior, mission_success=left,
        mission_success_observation=right, semantic_consistency=consistency,
        mission_metrics=results, run_status=status,
        label_provenance=dict(requested_intent="TaskSpec author; not inferred hidden intent",
            mission_success="fast_dynamics plant position support samples",
            mission_success_observation="ideal_state observer; derived from plant, not an independent sensor",
            semantic_validation_version=protocol["semantic_validation_version"],
            semantic_adapter_version=ADAPTER_VERSION, validator_versions={intent.name: intent.validator_version},
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
