"""M1 airborne two-vehicle rapid-passage executor on a shared integer clock.

No simulator, wall-clock waits, telemetry, takeoff, or landing are involved.
Only the explicitly supported single-segment phases are accepted. M2 extends
route tracking and mission coverage after the M1 data contract is verified.
"""

from dataclasses import dataclass
import numpy as np

from ..mission_v3 import compile_mission_v3
from ..tasks import target_confirmation
from .contracts import FastDynamicsConfig, PlantState
from .engine import SynchronousEngine
from .references import endpoint_velocity, arrival_intervals, region_crossings, REFERENCE_VERSION
from .provenance import source_snapshot


EXECUTOR_VERSION = "airborne_rapid_passage_m1"


@dataclass
class MissionResult:
    task: dict
    scene: dict
    config: dict
    agent_ids: list
    time_us: np.ndarray
    positions: np.ndarray
    velocities: np.ndarray
    accelerations: np.ndarray
    support_time_us: np.ndarray
    support_positions: np.ndarray
    support_velocities: np.ndarray
    support_accelerations: np.ndarray
    events: list
    end_us: int
    status: str
    diagnostics: dict


def _us(seconds):
    return int(round(seconds * 1_000_000))


def run_mission(task, config=None):
    execution_sources = source_snapshot()
    config = config or FastDynamicsConfig()
    if isinstance(config, dict):
        config = FastDynamicsConfig.from_dict(config)
    scene = compile_mission_v3(task)
    spec = scene["task_spec"]
    if (spec["mission"]["intent"] != "rapid_passage" or len(scene["vehicles"]) != 2
            or spec["execution"]["control_mode"] != "semantic_phase_route_v1"
            or spec["planner"]["name"] != "line_abreast_v1"):
        raise ValueError("M1 supports only two-vehicle line_abreast rapid_passage semantic routes")
    if any(len(route) > 1 for phase in scene["phases"] for route in phase["routes"].values()):
        raise ValueError("M1 accepts single-segment phases only; multi-waypoint tracking requires M2")
    ids = sorted(v["id"] for v in scene["vehicles"])
    vehicles = {v["id"]: v for v in scene["vehicles"]}
    p = np.array([[vehicles[a]["east_m"], vehicles[a]["north_m"], scene["takeoff_alt_m"]] for a in ids])
    engine = SynchronousEngine(config, PlantState(p, np.zeros_like(p), np.zeros_like(p)))
    events, support = [], {0: engine.state}
    region = next(r for r in spec["scenario"]["regions"] if r["id"] == spec["mission"]["target_region_id"])
    deadline_us = _us(min(config.execution.max_duration_s, spec["execution"]["timeout_s"]))

    def emit(name, stamp, phase=None, agent=None, **evidence):
        row = dict(event=name, t_us=int(stamp), t_s=stamp / 1_000_000,
                   source="engine_state", **evidence)
        if phase is not None:
            row["phase"] = phase
        if agent is not None:
            row["agent_id"] = agent
        events.append(row)

    emit("airborne_mission_started", 0, lifecycle_scope="airborne_mission")
    status = "complete"
    for phase_index, phase in enumerate(scene["phases"]):
        if engine.time_us >= deadline_us:
            status = "timeout"
            break
        name = phase["name"]
        roles = scene["semantic_plan"]["execution_phases"][name]["agents"]
        targets = np.array([[roles[a]["terminal_point"][k] for k in ("east_m", "north_m", "up_m")] for a in ids])
        released = engine.time_us
        delays = phase.get("start_delays_s", {})
        starts = [released + _us(delays.get(a, 0.)) for a in ids]
        requirements = [target_confirmation(scene, phase, a) for a in ids]
        inside_since, arrived, done, started = [None] * len(ids), [False] * len(ids), [False] * len(ids), [False] * len(ids)
        finished_at = [None] * len(ids)
        hold = max(phase.get("terminal_hold_s", 0.), config.execution.terminal_hold_s)
        if phase_index == len(scene["phases"]) - 1:
            hold += spec["execution"].get("final_hold_s", 0.)
        emit("phase_ready", released, name)
        emit("phase_released", released, name, semantic_phase=scene["semantic_plan"]["execution_phases"][name]["semantic_phase"])
        phase_start_state = engine.state
        while not all(done) and engine.time_us < deadline_us:
            now = engine.time_us
            for i, a in enumerate(ids):
                if not started[i] and now >= starts[i]:
                    started[i] = True
                    emit("phase_started", now, name, a, role=roles[a]["role"])
            desired = endpoint_velocity(engine.state.p, targets, phase["speed_m_s"],
                                        config.controller.velocity_response_time_s + config.vehicle_profile.response_time_s)
            for i in range(len(ids)):
                if not started[i]:
                    desired[i] = endpoint_velocity(engine.state.p[i:i+1], phase_start_state.p[i:i+1],
                                                  phase["speed_m_s"], 2.)[0]
            step_us = min(config.engine.step_us, deadline_us - now)
            for start in starts:
                if now < start < now + step_us:
                    step_us = start - now
            before = engine.state
            engine.step(desired, dt_us=step_us)
            segment = engine.last_segment
            after = engine.state
            support[engine.time_us] = after
            duration = step_us / 1_000_000
            for offset in region_crossings(before, engine.last_jerk, region, duration):
                stamp = min(engine.time_us, max(now, now + _us(offset)))
                support[stamp] = segment.at(stamp)
            for i, a in enumerate(ids):
                if not started[i]:
                    continue
                radius = min(requirements[i]["tolerance_m"], config.execution.arrival_radius_m)
                intervals = arrival_intervals(before, engine.last_jerk, i, targets[i], radius,
                                              config.execution.arrival_speed_m_s, duration)
                last_end = now
                for left, right in intervals:
                    begin, end = now + _us(left), now + _us(right)
                    if inside_since[i] is None or begin > last_end + 1:
                        if arrived[i] or done[i]:
                            emit("phase_confirmation_reset", last_end, name, a,
                                 reason="left_arrival_region_or_speed_limit_while_waiting")
                        arrived[i], done[i], finished_at[i] = False, False, None
                        inside_since[i] = begin
                    arrival_us = inside_since[i] + _us(requirements[i]["dwell_s"])
                    ready_us = arrival_us + _us(hold)
                    if end >= arrival_us and not arrived[i]:
                        arrived[i] = True
                        emit("phase_arrived", arrival_us, name, a, radius_m=radius,
                             confirmation_dwell_s=requirements[i]["dwell_s"], speed_limit_m_s=config.execution.arrival_speed_m_s)
                        support[arrival_us] = segment.at(arrival_us)
                    if end >= ready_us and not done[i]:
                        done[i] = True
                        finished_at[i] = ready_us
                        emit("phase_hold_ended", ready_us, name, a, hold_s=hold)
                        support[ready_us] = segment.at(ready_us)
                    last_end = end
                if last_end < engine.time_us:
                    if arrived[i] or done[i]:
                        emit("phase_confirmation_reset", last_end, name, a,
                             reason="left_arrival_region_or_speed_limit_while_waiting")
                    arrived[i], done[i], finished_at[i] = False, False, None
                    inside_since[i] = None
            # The barrier is an actual continuous-state event. Split the last
            # cubic step there so h/h2 do not get different release rounding.
            if all(done):
                barrier_us = max(finished_at)
                engine.truncate_last_step(barrier_us)
                support = {t: value for t, value in support.items() if t <= barrier_us}
                support[barrier_us] = engine.state
        if not all(done):
            status = "timeout"
            emit("phase_timeout", engine.time_us, name)
            break
    emit("airborne_mission_completed" if status == "complete" else "airborne_mission_timeout", engine.time_us)
    samples = engine.samples
    support.update({s.t_us: s for s in samples})
    support_times = sorted(support)
    support_v = np.stack([support[t].v for t in support_times])
    support_a = np.stack([support[t].a for t in support_times])
    support_j = np.diff(support_a, axis=0) / (np.diff(support_times)[:, None, None] / 1e6)
    # Dense insertion order never determines output or event ordering.
    events.sort(key=lambda e: (e["t_us"], e.get("phase", ""), e.get("agent_id", ""), e["event"]))
    if source_snapshot() != execution_sources:
        raise RuntimeError("source files changed during simulation; retain attempt and run with a stable source tree")
    shape = (0, len(ids), 3)
    return MissionResult(spec, scene, config.to_dict(), ids,
        np.array([s.t_us for s in samples], dtype=np.int64),
        np.stack([s.p for s in samples]) if samples else np.empty(shape),
        np.stack([s.v for s in samples]) if samples else np.empty(shape),
        np.stack([s.a for s in samples]) if samples else np.empty(shape),
        np.array(support_times, dtype=np.int64),
        np.stack([support[t].p for t in support_times]), support_v,
        support_a, events, engine.time_us, status,
        dict(executor_version=EXECUTOR_VERSION, reference_version=REFERENCE_VERSION,
             executed_source_sha256=execution_sources,
             numerical_finite=True, peak_speed_m_s=float(np.linalg.norm(support_v, axis=2).max()),
             peak_acceleration_m_s2=float(np.linalg.norm(support_a, axis=2).max()),
             peak_jerk_m_s3=float(np.linalg.norm(support_j, axis=2).max()) if len(support_j) else 0.,
             peak_scope="retained support samples, jerk constant within each support interval",
             phase_release_policy="dense common-time barrier after all actual holds",
             support_policy="all integrator endpoints plus cubic region intersections and arrival/hold boundaries",
             lifecycle_scope="airborne_mission", supported_scope="two-agent single-segment rapid_passage"))
