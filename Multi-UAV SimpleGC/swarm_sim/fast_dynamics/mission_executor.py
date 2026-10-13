"""M2 continuous routes and actual-state phase barriers on one simulation clock.

An explicitly supplied legacy configuration dispatches to the frozen M1 driver.
References can change; the plant state, trajectory and semantic labels cannot.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import math
from collections.abc import Mapping

import numpy as np

from ..mission_v3 import compile_mission_v3
from ..tasks import target_confirmation
from .contracts import FastDynamicsConfig, M2Config, PlantState, config_from_dict
from .engine import SynchronousEngine, StepSegment
from .mission_executor_m1 import MissionResult, run_mission as run_mission_m1
from .provenance import source_snapshot
from .references import endpoint_velocity, arrival_intervals, region_crossings, _roots

EXECUTOR_VERSION = "airborne_multi_intent_m2"
REFERENCE_VERSION = "continuous_route_v2"
BEHAVIOR_VERSION = "m2_continuous_v2"


def _us(seconds):
    return int(round(float(seconds) * 1_000_000))


def normalize_test_harness(value):
    """Strict, recorded test reference changes; never state or semantic edits."""
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("test_harness must be an object")
    kind = value.get("kind")
    defaults = {
        "recon_altitude_excursion": dict(semantic_phase="observe", altitude_offset_m=1.25,
            ramp_s=7.0, settle_s=.5, height_margin_m=.1, vertical_speed_m_s=.05),
        "patrol_slowdown": dict(semantic_phase="patrol", speed_factor=.4),
    }
    if kind not in defaults or set(value) - {"kind", *defaults.get(kind, {})}:
        raise ValueError("unsupported test_harness kind or fields")
    result = dict(kind=kind, **defaults[kind])
    result.update(value)
    if result["semantic_phase"] != defaults[kind]["semantic_phase"]:
        raise ValueError("test_harness has an unsupported service phase")
    for key, number in result.items():
        if key in ("kind", "semantic_phase"):
            continue
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number <= 0:
            raise ValueError(f"test_harness.{key} must be finite and positive")
    if kind == "patrol_slowdown" and result["speed_factor"] >= 1:
        raise ValueError("patrol_slowdown requires speed_factor < 1")
    if kind == "recon_altitude_excursion" and result["height_margin_m"] >= result["altitude_offset_m"]:
        raise ValueError("height margin must be smaller than the altitude excursion")
    return result


@dataclass
class _Confirmation:
    inside_since: int | None = None
    confirmed: bool = False
    done: bool = False
    epoch: int = 0

    def advance(self, intervals, start_us, end_us, dwell_us, hold_us):
        """Consume closed valid intervals and return causal events + done spans.

        All calculations belong to the already computed cubic step. A later
        barrier truncation replays this method on its exact committed prefix.
        """
        rows, done_spans = [], []

        def reset(stamp):
            if self.inside_since is not None or self.confirmed or self.done:
                old = self.epoch
                self.epoch += 1
                rows.append(("phase_confirmation_reset", stamp,
                             dict(epoch=self.epoch, revoked_epoch=old,
                                  reason="left_arrival_region_or_speed_limit_while_waiting")))
            self.inside_since, self.confirmed, self.done = None, False, False

        cursor = start_us
        for left, right in intervals:
            left, right = max(start_us, int(left)), min(end_us, int(right))
            if right < left:
                continue
            if left > cursor:
                reset(cursor)
            if self.inside_since is None:
                self.inside_since = left
                rows.append(("phase_arrival_entered", left, dict(epoch=self.epoch)))
            confirmed_at = self.inside_since + dwell_us
            ready_at = confirmed_at + hold_us
            if confirmed_at <= right and not self.confirmed:
                self.confirmed = True
                rows.append(("phase_arrived", max(left, confirmed_at), dict(epoch=self.epoch)))
            if ready_at <= right:
                if not self.done:
                    self.done = True
                    rows.append(("phase_hold_ended", max(left, ready_at), dict(epoch=self.epoch)))
                done_spans.append((max(left, ready_at), right))
            cursor = right
        if cursor < end_us or not intervals:
            reset(cursor)
        return rows, done_spans


def _first_common_time(intervals_by_agent):
    if not intervals_by_agent or any(not intervals for intervals in intervals_by_agent):
        return None
    pointers = [0] * len(intervals_by_agent)
    while all(pointers[i] < len(v) for i, v in enumerate(intervals_by_agent)):
        current = [v[pointers[i]] for i, v in enumerate(intervals_by_agent)]
        left, right = max(x[0] for x in current), min(x[1] for x in current)
        if left <= right:
            return left
        earliest = min(x[1] for x in current)
        for i, interval in enumerate(current):
            if interval[1] == earliest:
                pointers[i] += 1
    return None


def _arrival_integer_intervals(segment, agent, target, radius, speed, not_before):
    duration = (segment.end_us - segment.start_us) / 1e6
    if duration == 0:
        valid = np.linalg.norm(segment.state.p[agent] - target) <= radius and np.linalg.norm(segment.state.v[agent]) <= speed
        return [(segment.start_us, segment.end_us)] if valid and segment.start_us >= not_before else []
    raw = arrival_intervals(segment.state, segment.jerk, agent, target, radius, speed, duration)
    result = []
    for left, right in raw:
        # Quantize toward the valid interior. Never credit time before entry.
        begin = max(not_before, segment.start_us + int(math.ceil(left * 1e6 - 1e-7)))
        end = segment.start_us + int(math.floor(right * 1e6 + 1e-7))
        if begin <= end:
            result.append((begin, end))
    return result


def _motion_time(segment, index, threshold=.001):
    from numpy.polynomial import polynomial as poly
    velocity = np.stack((segment.state.v[index], segment.state.a[index], segment.jerk[index] / 2))
    speed = np.zeros(5)
    for axis in range(3):
        speed = poly.polyadd(speed, poly.polymul(velocity[:, axis], velocity[:, axis]))
    speed[0] -= threshold ** 2
    duration = (segment.end_us - segment.start_us) / 1e6
    boundaries = [0., *_roots(speed, duration), duration]
    for left, right in zip(boundaries, boundaries[1:]):
        if poly.polyval((left + right) / 2, speed) > 0:
            return min(segment.end_us, segment.start_us + int(math.ceil(left * 1e6)))
    return None


class _AltitudeExcursion:
    """Common smooth UP reference, advanced only from actual integrated state."""
    def __init__(self, config, baseline, released):
        self.config = config
        self.baseline = np.asarray(baseline, dtype=float)
        self.state = "raising"
        self.transition_us = released
        self.stable_since = None
        self.route_enabled = False
        self.arrival_enabled = False

    @staticmethod
    def blend(u):
        u = np.clip(u, 0., 1.)
        return 10 * u ** 3 - 15 * u ** 4 + 6 * u ** 5

    def height(self, now):
        delta = self.config["altitude_offset_m"]
        u = (now - self.transition_us) / 1e6 / self.config["ramp_s"]
        if self.state == "raising":
            return self.baseline + delta * self.blend(u)
        if self.state == "lowering":
            return self.baseline + delta * (1 - self.blend(u))
        return self.baseline + (delta if self.state == "tracking" else 0.)

    def update(self, now, state, trackers):
        old = self.state
        if self.state == "raising":
            threshold = self.baseline + self.config["altitude_offset_m"] - self.config["height_margin_m"]
            valid = np.all(state.p[:, 2] >= threshold) and np.all(np.abs(state.v[:, 2]) <= self.config["vertical_speed_m_s"])
            self.stable_since = (now if self.stable_since is None else self.stable_since) if valid else None
            if self.stable_since is not None and now - self.stable_since >= _us(self.config["settle_s"]):
                self.state, self.route_enabled = "tracking", True
        elif self.state == "tracking" and all(tracker.complete for tracker in trackers):
            self.state, self.transition_us = "lowering", now
        elif self.state == "lowering" and now - self.transition_us >= _us(self.config["ramp_s"]):
            self.state, self.arrival_enabled = "restored", True
        return self.state if old != self.state else None


def _route_points(start, route):
    """Drop exact adjacent repeats only; unfolded lap identities stay intact."""
    points = [start]
    for point in route:
        if not np.array_equal(point, points[-1]):
            points.append(point)
    return points


def run_mission(task, config=None, *, test_harness=None):
    if isinstance(config, dict):
        config = config_from_dict(config)
    if config is None:
        config = M2Config()
    if not isinstance(config, M2Config):
        if test_harness is not None:
            raise ValueError("test_harness requires an M2 configuration")
        if not isinstance(config, FastDynamicsConfig):
            raise TypeError("config must be a FastDynamicsConfig or M2Config")
        return run_mission_m1(task, config)
    from .route_tracker import RouteTracker

    execution_sources = source_snapshot()
    harness = normalize_test_harness(test_harness)
    scene = compile_mission_v3(task)
    spec = scene["task_spec"]
    if (len(scene["vehicles"]) not in (2, 3, 4)
            or spec["execution"]["control_mode"] != "semantic_phase_route_v1"
            or spec["mission"]["intent"] not in ("rapid_passage", "reconnaissance", "patrol")):
        raise ValueError("M2 supports semantic routes for 2/3/4-agent reconnaissance, patrol and rapid_passage")
    if harness is not None:
        expected = "reconnaissance" if harness["kind"] == "recon_altitude_excursion" else "patrol"
        if spec["mission"]["intent"] != expected:
            raise ValueError("test_harness does not match task intent")
    ids = sorted(v["id"] for v in scene["vehicles"])
    vehicles = {v["id"]: v for v in scene["vehicles"]}
    positions = np.array([[vehicles[a]["east_m"], vehicles[a]["north_m"], scene["takeoff_alt_m"]] for a in ids])
    engine = SynchronousEngine(config, PlantState(positions, np.zeros_like(positions), np.zeros_like(positions)))
    events, support = [], {0: engine.state}
    region = next(r for r in spec["scenario"]["regions"] if r["id"] == spec["mission"]["target_region_id"])
    deadline = _us(min(config.execution.max_duration_s, spec["execution"]["timeout_s"]))
    phase_index = -1
    tracker_diagnostics = {}

    def emit(event, stamp, phase=None, agent=None, **evidence):
        row = dict(event=event, t_us=int(stamp), t_s=int(stamp) / 1e6,
                   source="engine_state", phase_index=phase_index,
                   _sequence=len(events), epoch=evidence.pop("epoch", 0), **evidence)
        if phase is not None:
            row["phase"] = phase
        if agent is not None:
            row["agent_id"] = agent
        events.append(row)

    emit("airborne_mission_started", 0, lifecycle_scope="airborne_mission")
    status = "complete"
    for phase_index, phase in enumerate(scene["phases"]):
        name = phase["name"]
        if engine.time_us >= deadline:
            status = "timeout"
            emit("phase_timeout", engine.time_us, name, deadline_us=deadline)
            break
        roles = scene["semantic_plan"]["execution_phases"][name]["agents"]
        xyz = lambda point: [point[k] for k in ("east_m", "north_m", "up_m")]
        starts_xyz = np.array([xyz(roles[a]["start_point"]) for a in ids])
        targets = np.array([xyz(roles[a]["terminal_point"]) for a in ids])
        speed = phase["speed_m_s"]
        active_harness = harness is not None and phase["semantic_phase"] == harness["semantic_phase"]
        if active_harness and harness["kind"] == "patrol_slowdown":
            speed *= harness["speed_factor"]
        trackers = [RouteTracker(_route_points(xyz(roles[a]["start_point"]), [xyz(p) for p in phase["routes"][a]]),
                                 speed, config.vehicle_profile, config.controller, config.reference, step_us=config.engine.step_us) for a in ids]
        released = engine.time_us
        delays = phase.get("start_delays_s", {})
        if set(delays) - set(ids) or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in delays.values()):
            raise ValueError("invalid per-agent start delay")
        starts = [released + _us(delays.get(a, 0)) for a in ids]
        requirements = [target_confirmation(scene, phase, a) for a in ids]
        radii = [min(requirements[i]["tolerance_m"], config.execution.arrival_radius_m) for i in range(len(ids))]
        dwell = [_us(r["dwell_s"]) for r in requirements]
        hold_s = max(phase.get("terminal_hold_s", 0), config.execution.terminal_hold_s)
        if phase_index == len(scene["phases"]) - 1:
            hold_s += spec["execution"].get("final_hold_s", 0)
        hold_us = _us(hold_s)
        confirmations = [_Confirmation() for _ in ids]
        started, moved = [False] * len(ids), [False] * len(ids)
        completed_at = [None] * len(ids)
        phase_start_state = engine.state
        altitude = _AltitudeExcursion(harness, targets[:, 2], released) if active_harness and harness["kind"] == "recon_altitude_excursion" else None
        if altitude is not None:
            upper = spec["scenario"]["world"]["flight_up_bounds_m"][1]
            if np.any(targets[:, 2] + harness["altitude_offset_m"] > upper):
                raise ValueError("test altitude excursion leaves world bounds")
        emit("phase_ready", released, name, requested_release_us=released)
        emit("phase_released", released, name, requested_release_us=released, actual_release_us=released,
             semantic_phase=phase["semantic_phase"])
        if active_harness:
            emit("test_reference_started", released, name, descriptor=harness)
        phase_finished = False
        cycle_end_us = released + config.engine.step_us
        while engine.time_us < deadline:
            now = engine.time_us
            for i, a in enumerate(ids):
                if not started[i] and now >= starts[i]:
                    started[i] = True
                    emit("phase_started", now, name, a, role=roles[a]["role"], requested_start_us=starts[i], actual_start_us=now)
                    if np.linalg.norm(engine.state.v[i]) > .001:
                        moved[i] = True
                        emit("motion_started", now, name, a, origin="already_moving_at_start")
                    if trackers[i].complete:
                        completed_at[i] = now
                        emit("route_completed", now, name, a, no_op=not bool(phase["routes"][a]))
            if altitude is not None:
                transition = altitude.update(now, engine.state, trackers)
                if transition:
                    emit("test_reference_transition", now, name, state=transition, kind=harness["kind"])
            desired = np.zeros_like(engine.state.p)
            for i in range(len(ids)):
                if not started[i]:
                    desired[i] = endpoint_velocity(engine.state.p[i:i+1], phase_start_state.p[i:i+1], speed, 2.)[0]
                elif altitude is not None and not altitude.route_enabled:
                    desired[i] = endpoint_velocity(engine.state.p[i:i+1], starts_xyz[i:i+1], speed, 1.)[0]
                else:
                    desired[i] = trackers[i].command(engine.state.p[i], engine.state.v[i], engine.state.a[i])
            if altitude is not None:
                altitude_target = altitude.height(now)
                desired[:, 2] = np.clip((altitude_target - engine.state.p[:, 2]) / 2.,
                                       -config.vehicle_profile.max_speed_down_m_s,
                                       config.vehicle_profile.max_speed_up_m_s)
            if now >= cycle_end_us:
                cycle_end_us = now + config.engine.step_us
            step = min(cycle_end_us - now, deadline - now)
            for start in starts:
                if now < start < now + step:
                    step = start - now
            previous_trackers = copy.deepcopy(trackers)
            previous_confirmations = copy.deepcopy(confirmations)
            previous_completed = list(completed_at)
            engine.step(desired, dt_us=step)
            segment = engine.last_segment

            def evaluate(candidate):
                local_trackers = copy.deepcopy(previous_trackers)
                local_confirmations = copy.deepcopy(previous_confirmations)
                local_complete = list(previous_completed)
                local_events, all_spans = [], []
                for i, a in enumerate(ids):
                    if not started[i]:
                        all_spans.append([])
                        continue
                    if altitude is None or altitude.route_enabled:
                        was_complete = local_trackers[i].complete
                        observed = local_trackers[i].observe_segment(candidate, i)
                        for event in observed:
                            local_events.append((event["event"], event["t_us"], a,
                                {k: v for k, v in event.items() if k not in ("event", "t_us")}))
                        if local_trackers[i].complete and not was_complete:
                            stamps = [e["t_us"] for e in observed if e["event"] in ("route_completed", "route_complete")]
                            local_complete[i] = max(candidate.start_us, min(stamps, default=candidate.end_us))
                            if not any(e["event"] == "route_completed" for e in observed):
                                local_events.append(("route_completed", local_complete[i], a, dict(no_op=False)))
                    available = (local_complete[i] is not None and (altitude is None or altitude.arrival_enabled))
                    intervals = _arrival_integer_intervals(candidate, i, targets[i], radii[i],
                        config.execution.arrival_speed_m_s, max(candidate.start_us, local_complete[i])) if available else []
                    rows, spans = local_confirmations[i].advance(intervals, candidate.start_us, candidate.end_us, dwell[i], hold_us)
                    for event, stamp, details in rows:
                        if event == "phase_arrived":
                            details.update(radius_m=radii[i], confirmation_dwell_s=requirements[i]["dwell_s"],
                                           speed_limit_m_s=config.execution.arrival_speed_m_s)
                        elif event == "phase_hold_ended":
                            details["hold_s"] = hold_s
                        local_events.append((event, stamp, a, details))
                    all_spans.append(spans)
                return local_trackers, local_confirmations, local_complete, local_events, all_spans

            evaluated = evaluate(segment)
            barrier = _first_common_time(evaluated[-1])
            transitions = [stamp for event, stamp, _agent, detail in evaluated[-2]
                if event in ("route_primitive_advanced", "route_corner_stopped", "route_completed")
                or event == "route_node_witnessed" and detail.get("node_index") == 0]
            cut = min([segment.end_us] + transitions + ([barrier] if barrier is not None and barrier < deadline else []))
            if cut < segment.end_us:
                engine.truncate_last_step(cut)
                segment = engine.last_segment
                evaluated = evaluate(segment)
            phase_finished = barrier is not None and barrier == cut and barrier < deadline
            trackers, confirmations, completed_at, pending, _ = evaluated
            support[engine.time_us] = engine.state
            for event, stamp, agent, details in pending:
                if stamp <= engine.time_us:
                    emit(event, stamp, name, agent, **details)
                    support[stamp] = segment.at(stamp)
            for i, a in enumerate(ids):
                if started[i] and not moved[i]:
                    stamp = _motion_time(segment, i)
                    if stamp is not None:
                        moved[i] = True
                        emit("motion_started", stamp, name, a, origin="observed_speed_crossing", speed_threshold_m_s=.001)
                        support[stamp] = segment.at(stamp)
            duration = (segment.end_us - segment.start_us) / 1e6
            if duration > 0:
                for offset in region_crossings(segment.state, segment.jerk, region, duration):
                    stamp = max(segment.start_us, min(segment.end_us, segment.start_us + _us(offset)))
                    support[stamp] = segment.at(stamp)
            if phase_finished:
                emit("phase_completed", engine.time_us, name, confirmed_epochs={a: confirmations[i].epoch for i, a in enumerate(ids)})
                emit("phase_end", engine.time_us, name)
                break
        tracker_diagnostics[name] = {a: trackers[i].diagnostics for i, a in enumerate(ids)}
        if not phase_finished:
            status = "timeout"
            emit("phase_timeout", engine.time_us, name, deadline_us=deadline,
                 agent_states={a: "done" if confirmations[i].done else "waiting_delay" if not started[i] else "executing" for i, a in enumerate(ids)})
            break
    emit("airborne_mission_completed" if status == "complete" else "airborne_mission_timeout", engine.time_us)
    samples = engine.samples
    support.update({sample.t_us: sample for sample in samples})
    support_times = sorted(support)
    support_v = np.stack([support[t].v for t in support_times])
    support_a = np.stack([support[t].a for t in support_times])
    support_j = np.diff(support_a, axis=0) / (np.diff(support_times)[:, None, None] / 1e6)
    events.sort(key=lambda row: (row["t_us"], row["phase_index"], row["_sequence"]))
    for sequence, row in enumerate(events):
        row["event_seq"] = sequence
        del row["_sequence"]
    if source_snapshot() != execution_sources:
        raise RuntimeError("source files changed during simulation; retain attempt and run with a stable source tree")
    shape = (0, len(ids), 3)
    return MissionResult(spec, scene, config.to_dict(), ids,
        np.array([sample.t_us for sample in samples], dtype=np.int64),
        np.stack([sample.p for sample in samples]) if samples else np.empty(shape),
        np.stack([sample.v for sample in samples]) if samples else np.empty(shape),
        np.stack([sample.a for sample in samples]) if samples else np.empty(shape),
        np.array(support_times, dtype=np.int64), np.stack([support[t].p for t in support_times]), support_v,
        support_a, events, engine.time_us, status,
        dict(executor_version=EXECUTOR_VERSION, reference_version=REFERENCE_VERSION, behavior_version=BEHAVIOR_VERSION,
             executed_source_sha256=execution_sources, test_harness=harness,
             numerical_finite=bool(np.all(np.isfinite(support_v)) and np.all(np.isfinite(support_a))),
             peak_speed_m_s=float(np.linalg.norm(support_v, axis=2).max()),
             peak_acceleration_m_s2=float(np.linalg.norm(support_a, axis=2).max()),
             peak_jerk_m_s3=float(np.linalg.norm(support_j, axis=2).max()) if len(support_j) else 0.,
             peak_scope="retained support samples; jerk constant within each support interval",
             phase_release_policy="dense common-time barrier after all currently valid holds",
             support_policy="integrator endpoints, route witnesses, motion, region and confirmation boundaries",
             lifecycle_scope="airborne_mission", supported_scope="three intents, four planners, 2/3/4 agents",
             route_tracking=tracker_diagnostics))
