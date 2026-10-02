"""Channel-independent continuous-route windows; never infer arrival from a plan.

All exported times are host-monotonic seconds relative to time_epoch. SIM has
positions only: its horizontal speed is a backward difference of adjacent valid
positions, preferably over mapped source time. Invalid rows and gaps are barriers.
"""

import copy
import math

from .mission_evaluation import position_valid, source_time, window_evidence
from .observations import finite_number
from .registry import get_intent

WINDOW_VERSION = "semantic_route_windows_v1"
OBSERVATION_SPEED_VERSION = "fcu_horizontal_velocity_v1"
SIM_SOURCE_SPEED_VERSION = "sim_horizontal_backward_difference_source_v1"
SIM_HOST_SPEED_VERSION = "sim_horizontal_backward_difference_host_v1"
EPS = 1e-8


def _event_times(events, kind, agent, phase, shift):
    return sorted(event["t"] + shift for event in events
                  if event.get("event") == kind and event.get("agent_id") == agent
                  and event.get("phase") == phase and finite_number(event.get("t")))


def _release_times(events, phase, shift):
    return sorted(event["release_t"] + shift for event in events
                  if event.get("event") == "phase_release_scheduled" and event.get("phase") == phase
                  and finite_number(event.get("release_t")))


def _speed_rows(rows, channel, model, max_gap):
    """No interpolation through invalid/gapped rows, no SIM/FCU cross-substitution."""
    source_based = channel == "truth" and bool(model and model.get("available"))
    version = (OBSERVATION_SPEED_VERSION if channel == "observation" else
               SIM_SOURCE_SPEED_VERSION if source_based else SIM_HOST_SPEED_VERSION)
    timeline_valid = (all(finite_number(t) for t, _ in rows)
                      and all(b[0] > a[0] for a, b in zip(rows, rows[1:])))
    result, previous = [], None
    for stamp, values in rows:
        speed, reason = None, "invalid_position_or_timeline"
        valid = timeline_valid and position_valid(values)
        if valid and channel == "observation":
            if len(values) >= 5 and all(finite_number(v) for v in values[3:5]):
                speed, reason = math.hypot(values[3], values[4]), None
            else:
                reason = "missing_fcu_horizontal_velocity"
        elif valid:
            reason = "no_adjacent_valid_position"
            if previous is not None:
                before, last = previous
                host_delta = stamp - before
                if EPS < host_delta <= max_gap + EPS:
                    left = source_time(before, model) if source_based else before
                    right = source_time(stamp, model) if source_based else stamp
                    if finite_number(left) and finite_number(right) and EPS < right - left <= max_gap + EPS:
                        speed, reason = math.dist(values[:2], last[:2]) / (right - left), None
                    else:
                        reason = "source_time_unavailable_or_gap"
                else:
                    reason = "position_sample_gap"
        result.append((stamp, values if valid else None, speed, reason))
        previous = (stamp, values) if valid else None
    return result, version, timeline_valid


def _waypoint_events(events, agent, phase, route, planner_indices, shift, start, end):
    result = []
    for event in events:
        if (event.get("event") != "waypoint_reached" or event.get("agent_id") != agent
                or event.get("phase") != phase or not finite_number(event.get("t"))):
            continue
        seq = event.get("seq")
        if isinstance(seq, bool) or not isinstance(seq, int) or not 2 <= seq < len(route) + 2:
            continue
        stamp = event["t"] + shift
        index = seq - 2
        result.append(dict(seq=seq, route_index=index,
                           planner_index=planner_indices[index] if index < len(planner_indices) else None,
                           terminal=index == len(route) - 1, t_s=stamp,
                           within_window=finite_number(start) and finite_number(end) and start <= stamp <= end,
                           source="waypoint_reached_raw_receive_event"))
    return sorted(result, key=lambda item: item["t_s"])


def build_route_windows(scene, traces, events, metadata, time_epoch, channel, clocks=None):
    """Build full windows separately for one channel; service end is arrival_s.

    This function does not change raw evidence, clocks, traces or event packets.
    Missing terminal events cannot establish a search anchor or a service window.
    A valid terminal event without subsequent trajectory retains an explicitly
    unverified event fallback. Closest-point fallback is sampled, never a proof
    that the vehicle stopped. Independent return geometry owns return success.
    """
    if channel not in ("truth", "observation"):
        raise ValueError("route window channel must be truth or observation")
    if scene.get("schema_version") != 2 or scene["task_spec"]["execution"]["control_mode"] != "semantic_phase_route_v1":
        raise ValueError("continuous route windows require schema 2 and semantic_phase_route_v1")
    spec = scene["task_spec"]
    execution = spec["execution"]
    intent = get_intent(spec["mission"]["intent"])
    clocks = clocks or {}
    shift = metadata["run_epoch_monotonic_s"] - time_epoch
    run_end = metadata.get("elapsed_s", 0) + shift
    mission_end = metadata.get("mission_end_monotonic_s")
    mission_end = mission_end - time_epoch if finite_number(mission_end) else None
    phases = scene["phases"]
    windows = []
    for phase_index, phase in enumerate(phases):
        name = phase["name"]
        planned = scene["semantic_plan"]["execution_phases"][name]
        semantic = planned["semantic_phase"]
        releases = _release_times(events, name, shift)
        release = releases[0] if len(releases) == 1 else None
        next_releases = (_release_times(events, phases[phase_index + 1]["name"], shift)
                         if phase_index + 1 < len(phases) else [])
        end_known = (len(next_releases) == 1 if phase_index + 1 < len(phases) else mission_end is not None)
        end = next_releases[0] if len(next_releases) == 1 else mission_end if mission_end is not None else run_end
        end_source = ("next_phase_release" if len(next_releases) == 1 else
                      "mission_end" if phase_index + 1 == len(phases) and mission_end is not None else "incomplete_run_end_fallback")
        for vehicle in scene["vehicles"]:
            agent = vehicle["id"]
            role = planned["agents"][agent]
            route = phase["routes"][agent]
            no_op = not route
            start_event = "phase_no_op_started" if no_op else "phase_auto_confirmed"
            starts = _event_times(events, start_event, agent, name, shift)
            start = starts[0] if len(starts) == 1 else None
            bounds_valid = start is not None and finite_number(end) and end >= start
            rows = traces.get(agent, [])
            speed_rows, speed_version, timeline_valid = _speed_rows(rows, channel, clocks.get(agent), execution["max_gap_s"])
            target = role.get("terminal_point", route[-1] if route else role.get("start_point"))
            if not isinstance(target, dict) or any(not finite_number(target.get(k)) for k in ("east_m", "north_m", "up_m")):
                raise ValueError("route window requires finite compiled terminal_point for every agent")
            xyz = [target[key] for key in ("east_m", "north_m", "up_m")]
            subevents = _waypoint_events(events, agent, name, route, role.get("waypoint_planner_indices", []), shift, start, end)
            # A short route may finish before mode(AUTO)'s confirming heartbeat
            # reaches the control thread. The release, not that delayed start
            # proxy, bounds the terminal anchor. The 7.5 forward search itself
            # remains unchanged and may therefore reveal arrival < start.
            for event in subevents:
                event["within_phase_release_bounds"] = (release is not None and finite_number(end)
                    and release <= event["t_s"] <= end)
            terminal_events = [event for event in subevents if event["terminal"] and event["within_phase_release_bounds"]]
            terminal = terminal_events[0]["t_s"] if terminal_events else None
            arrival, arrival_source, arrival_reason = None, "event_fallback", "missing_terminal_waypoint_event"
            arrival_verified = False
            if no_op:
                ready = _event_times(events, "phase_no_op_ready", agent, name, shift)
                no_op_confirmed = bounds_valid and len(ready) == 1 and start <= ready[0] <= end
                arrival = start if no_op_confirmed else None
                arrival_source, arrival_reason = "no_op_ready", "compiled_hold_no_op" if no_op_confirmed else "missing_no_op_ready"
                arrival_verified = no_op_confirmed
            elif bounds_valid and terminal is not None:
                candidates = [(t, values, speed) for t, values, speed, _ in speed_rows
                              if finite_number(t) and terminal <= t <= end and values is not None]
                stops = [(t, values, speed) for t, values, speed in candidates
                         if speed is not None and speed <= .3 + EPS
                         and math.dist(values[:3], xyz) <= execution["arrival_tolerance_m"] + EPS]
                if stops:
                    arrival, arrival_source, arrival_reason = stops[0][0], "trajectory_stop", "first_sample_meeting_distance_and_speed"
                    arrival_verified = True
                elif candidates:
                    arrival = min(candidates, key=lambda row: (math.dist(row[1][:3], xyz), row[0]))[0]
                    arrival_source, arrival_reason = "trajectory_min_distance", "no_post_event_sample_meets_distance_and_speed"
                else:
                    arrival, arrival_source, arrival_reason = terminal, "event_fallback", "no_valid_post_event_position"
            elif not bounds_valid:
                arrival_reason = "missing_or_invalid_phase_bounds"
            evidence = (window_evidence(rows, start, end, execution["max_gap_s"])
                        if bounds_valid else dict(complete=False))
            chronology_valid = not (arrival is not None and start is not None and arrival < start)
            chronology_reason = None if chronology_valid else "trajectory_arrival_precedes_phase_start"
            complete = bool(bounds_valid and end_known and timeline_valid and arrival is not None
                            and (arrival_source != "event_fallback") and chronology_valid)
            service = not no_op and semantic in intent.service_phases and role.get("service_enabled") is True
            windows.append(dict(agent_id=agent, phase=name, semantic_phase=semantic,
                role="hold_no_op" if no_op else role["role"], service_enabled=service,
                partition_id=role.get("partition_id"), channel=channel,
                start_s=start, arrival_s=arrival, end_s=end, start_event=start_event, end_event=end_source,
                arrival_source=arrival_source, arrival_reason=arrival_reason, arrival_verified=arrival_verified,
                chronology_valid=chronology_valid, chronology_reason=chronology_reason, phase_release_s=release,
                terminal_point=copy.deepcopy(target), terminal_waypoint_reached_s=terminal,
                terminal_waypoint_event_count=len(terminal_events), waypoint_events=subevents,
                intermediate_waypoints=[event for event in subevents if not event["terminal"]],
                complete_execution_window=complete, trajectory_evidence_complete=evidence["complete"],
                speed_processing_version=speed_version,
                speed_time_basis="FCU_reported_velocity" if channel == "observation" else
                    "mapped_FCU_source_seconds" if speed_version == SIM_SOURCE_SPEED_VERSION else "host_aligned_seconds",
                speed_limitation=None if channel == "observation" else
                    "SIM position backward difference is interval-average horizontal speed, not an instantaneous sensor velocity; no gap bridging",
                barrier_wait_host_s=end - arrival if arrival is not None and bounds_valid and arrival <= end else None,
                scheduling_wait_host_s=None,
                source=WINDOW_VERSION))
    return windows


def service_window_view(windows):
    """Adapt only service windows for existing intent evaluators, without mutation."""
    result = copy.deepcopy(windows)
    for window in result:
        if window["service_enabled"]:
            window["phase_end_s"] = window["end_s"]
            window["end_s"] = window["arrival_s"]
            if window["arrival_s"] is None or window.get("chronology_valid") is False:
                window["start_s"] = None
                window["end_s"] = None
                window["complete_execution_window"] = False
    return result


def route_window_artifact(scene, by_channel, time_epoch):
    """Keep a labelled observation view for existing diagnostic consumers."""
    summaries = {}
    for channel, windows in by_channel.items():
        summaries[channel] = {vehicle["id"]: dict(
            barrier_wait_host_s=sum(window["barrier_wait_host_s"] for window in windows
                                    if window["agent_id"] == vehicle["id"] and window["barrier_wait_host_s"] is not None),
            unmeasured_barrier_windows=sum(window["agent_id"] == vehicle["id"] and window["barrier_wait_host_s"] is None
                                          for window in windows),
            hold_no_op_steps=sum(window["agent_id"] == vehicle["id"] and window["role"] == "hold_no_op" for window in windows))
            for vehicle in scene["vehicles"]}
    return dict(schema_version=2, window_version=WINDOW_VERSION, source=WINDOW_VERSION,
                time_epoch_host_s=time_epoch, window_channel="observation", windows=by_channel["observation"],
                channels=by_channel, per_agent_wait=summaries["observation"], per_channel_wait=summaries,
                arrival_definition="first post-terminal-event sampled position within tolerance with horizontal speed <=0.3m/s; otherwise post-event closest sampled position; no evidence stays explicit",
                service_definition="[start_s, arrival_s] only for registered service phases; hold_no_op excluded",
                wait_definitions=dict(barrier_wait_host_s="(arrival_s, end_s] excluded from service; end is next release or mission end",
                                      caution="passive clock mapping; fallback closest point/event is not verified arrival"))
