"""Integrated multi-agent scheduling, reset and boundary tests (no SITL)."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from swarm_sim.fast_dynamics.contracts import M2Config, ExecutionConfig, EngineConfig, FastDynamicsConfig
from swarm_sim.fast_dynamics.engine import SynchronousEngine
from swarm_sim.fast_dynamics.mission_executor import run_mission, _Confirmation, _first_common_time, normalize_test_harness
from swarm_sim.mission_v3 import compile_mission_v3

FIXTURE = Path(__file__).parent / "fixtures/fast_dynamics/rapid_passage_0000_v00.json"


def small_scene(count=2, distances=None, delays=None, no_op=False, return_phase=True):
    task = json.loads(FIXTURE.read_text(encoding="utf-8"))
    scene = compile_mission_v3(task)
    ids = [f"uav_{i+1:02d}" for i in range(count)]
    scene["vehicles"] = [dict(scene["vehicles"][0], id=a, sysid=i+1, east_m=0., north_m=i*20.) for i, a in enumerate(ids)]
    scene["task_spec"]["execution"].update(confirmation_dwell_s=.1, final_hold_s=.2)
    distances = distances or [2.] * count
    phases, mappings = [], {}
    for phase_index in range(2 if return_phase else 1):
        semantic = "assemble" if phase_index == 0 else "transit"
        name = f"p{phase_index:02d}_{semantic}"
        routes, agents = {}, {}
        for i, a in enumerate(ids):
            start = dict(east_m=0. if phase_index == 0 else distances[i], north_m=i*20., up_m=8.)
            end = dict(start, east_m=distances[i] if phase_index == 0 else 0.)
            routes[a] = [] if no_op or distances[i] == 0 else [end]
            if not routes[a]:
                end = start
            agents[a] = dict(start_point=start, terminal_point=end, role=semantic if routes[a] else "hold_no_op", service_enabled=bool(routes[a]), partition_id=a, waypoint_planner_indices=[0])
        phase = dict(name=name, semantic_phase=semantic, routes=routes, speed_m_s=2., terminal_hold_s=.1)
        if delays is not None and phase_index == 0:
            phase["start_delays_s"] = delays
        phases.append(phase)
        mappings[name] = dict(semantic_phase=semantic, agents=agents)
    scene["phases"] = phases
    scene["semantic_plan"]["execution_phases"] = mappings
    return task, scene


def execute_scene(task, scene, config=None, **kwargs):
    with patch("swarm_sim.fast_dynamics.mission_executor.compile_mission_v3", return_value=scene), patch("swarm_sim.fast_dynamics.mission_executor.source_snapshot", return_value={"unit_test": "stable"}):
        return run_mission(task, config or M2Config(), **kwargs)


class ConfirmationTests(unittest.TestCase):
    def test_disjoint_done_intervals_do_not_release_barrier(self):
        self.assertIsNone(_first_common_time([[(0, 10)], [(11, 20)]]))
        self.assertEqual(_first_common_time([[(0, 10), (20, 30)], [(11, 25)]]), 20)

    def test_confirmed_exit_revokes_epoch_then_reconfirms(self):
        state = _Confirmation()
        rows, spans = state.advance([(0, 50)], 0, 50, 10, 20)
        self.assertTrue(state.done)
        self.assertEqual(spans, [(30, 50)])
        rows, spans = state.advance([(60, 100)], 50, 100, 10, 20)
        self.assertEqual([row[0] for row in rows], ["phase_confirmation_reset", "phase_arrival_entered", "phase_arrived", "phase_hold_ended"])
        self.assertEqual(state.epoch, 1)
        self.assertEqual(spans, [(90, 100)])

    def test_short_valid_island_does_not_gain_missing_dwell(self):
        state = _Confirmation()
        rows, spans = state.advance([(3, 5), (8, 9)], 0, 20, 3, 0)
        self.assertEqual(spans, [])
        self.assertFalse(state.done)
        self.assertFalse(any(row[0] == "phase_arrived" for row in rows))


class ExecutionM2Tests(unittest.TestCase):
    def test_real_plant_two_three_four_agents_phase_and_final_hold(self):
        for count in (2, 3, 4):
            with self.subTest(count=count):
                task, scene = small_scene(count)
                result = execute_scene(task, scene)
                self.assertEqual(result.status, "complete")
                self.assertEqual(result.positions.shape[1:], (count, 3))
                np.testing.assert_array_equal(result.time_us, np.arange(len(result.time_us)) * 100000)
                self.assertLess(result.time_us[-1], result.end_us)
                self.assertEqual(result.support_time_us[-1], result.end_us)
                self.assertTrue(np.all(np.diff(result.support_time_us) > 0))
                first_end = next(e["t_us"] for e in result.events if e["event"] == "phase_end")
                second_release = next(e["t_us"] for e in result.events if e["event"] == "phase_released" and e["phase"] == "p01_transit")
                self.assertEqual(first_end, second_release)
                for agent in result.agent_ids:
                    arrival = next(e for e in result.events if e["event"] == "phase_arrived" and e["phase"] == "p01_transit" and e["agent_id"] == agent)
                    held = next(e for e in result.events if e["event"] == "phase_hold_ended" and e["phase"] == "p01_transit" and e["agent_id"] == agent)
                    self.assertEqual(held["t_us"] - arrival["t_us"], 300000)
                self.assertLessEqual(result.diagnostics["peak_jerk_m_s3"], 8.00001)

    def test_nonintegral_stagger_is_exact_and_waiting_state_keeps_integrating(self):
        task, scene = small_scene(delays={"uav_02": .135}, return_phase=False)
        result = execute_scene(task, scene)
        start = next(e for e in result.events if e["event"] == "phase_started" and e["agent_id"] == "uav_02")
        self.assertEqual(start["t_us"], 135000)
        self.assertEqual(start["requested_start_us"], 135000)
        motion = next(e for e in result.events if e["event"] == "motion_started" and e["agent_id"] == "uav_02")
        self.assertGreater(motion["t_us"], start["t_us"])
        self.assertIn(135000, result.support_time_us)
        self.assertTrue(np.any(result.positions[:2, 0, 0] != result.positions[:2, 1, 0]))

    def test_timeout_applies_while_personal_done_waits_for_delayed_peer(self):
        task, scene = small_scene(distances=[0, 0], delays={"uav_02": 4.}, no_op=True, return_phase=False)
        result = execute_scene(task, scene, M2Config(execution=ExecutionConfig(max_duration_s=.7)))
        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.end_us, 700000)
        timeout = next(e for e in result.events if e["event"] == "phase_timeout")
        self.assertEqual(timeout["agent_states"], {"uav_01": "done", "uav_02": "waiting_delay"})
        self.assertFalse(any(e["event"] == "phase_completed" for e in result.events))

    def test_done_agent_actual_departure_invalidates_and_recovers(self):
        task, scene = small_scene(distances=[0, 8], return_phase=False)
        original = SynchronousEngine.step
        def disturbed(engine, desired, dt_us=None):
            desired = desired.copy()
            if 1000000 <= engine.time_us < 2000000:
                desired[0, 0] = 2.5
            return original(engine, desired, dt_us)
        with patch.object(SynchronousEngine, "step", disturbed):
            result = execute_scene(task, scene)
        self.assertEqual(result.status, "complete")
        resets = [e for e in result.events if e["event"] == "phase_confirmation_reset" and e["agent_id"] == "uav_01"]
        self.assertTrue(resets)
        final = next(e for e in result.events if e["event"] == "phase_completed")
        self.assertGreater(final["confirmed_epochs"]["uav_01"], 0)
        self.assertTrue(np.max(result.positions[:, 0, 0]) > .3)
        self.assertLess(np.linalg.norm(result.support_velocities[-1, 0]), .15 + 1e-7)

    def test_noop_zero_dwell_and_hold_finishes_without_motion_or_extra_frame(self):
        task, scene = small_scene(distances=[0, 0], no_op=True, return_phase=False)
        scene["task_spec"]["execution"].update(confirmation_dwell_s=0., final_hold_s=0.)
        scene["phases"][0]["terminal_hold_s"] = 0.
        result = execute_scene(task, scene)
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.end_us, 0)
        self.assertEqual(len(result.time_us), 0)
        self.assertFalse(any(e["event"] == "motion_started" for e in result.events))
        self.assertEqual(len([e for e in result.events if e["event"] == "route_completed"]), 2)

    def test_half_step_preserves_phase_semantics_and_close_actual_trajectory(self):
        task, scene = small_scene(delays={"uav_02": .135})
        coarse = execute_scene(task, scene)
        fine = execute_scene(task, scene, M2Config(engine=EngineConfig(step_us=10000)))
        self.assertEqual(coarse.status, fine.status)
        self.assertLess(abs(coarse.end_us - fine.end_us), 100000)
        count = min(len(coarse.time_us), len(fine.time_us))
        error = np.linalg.norm(coarse.positions[:count] - fine.positions[:count], axis=2)
        self.assertLess(float(np.max(error)), .05)
        for result in (coarse, fine):
            self.assertEqual([e["event_seq"] for e in result.events], list(range(len(result.events))))
            self.assertEqual([e["t_us"] for e in result.events], sorted(e["t_us"] for e in result.events))

    def test_harness_descriptor_rejects_unknown_state_or_label_fields(self):
        self.assertEqual(normalize_test_harness({"kind": "patrol_slowdown"})["speed_factor"], .4)
        for value in ({"kind": "set_position"}, {"kind": "patrol_slowdown", "success": False}, {"kind": "patrol_slowdown", "speed_factor": 2}, {"kind": "recon_altitude_excursion", "altitude_offset_m": float("nan")}):
            with self.assertRaises(ValueError):
                normalize_test_harness(value)

    def test_exact_adjacent_repeats_do_not_remove_tiny_legs_or_loop_return(self):
        from swarm_sim.fast_dynamics.mission_executor import _route_points
        start = [0., 0., 8.]
        tiny = [.001, 0., 8.]
        self.assertEqual(_route_points(start, [start, tiny, tiny, start]), [start, tiny, start])
        task, scene = small_scene(return_phase=False)
        for route in scene["phases"][0]["routes"].values():
            route.append(dict(route[-1]))
        result = execute_scene(task, scene)
        self.assertEqual(result.status, "complete")

    def test_recon_fault_flies_altitude_excursion_then_recovers_original_target(self):
        task, scene = small_scene(return_phase=False)
        scene["task_spec"]["mission"]["intent"] = "reconnaissance"
        phase = scene["phases"][0]
        old = phase["name"]
        phase.update(name="p00_observe", semantic_phase="observe")
        mapping = scene["semantic_plan"]["execution_phases"].pop(old)
        mapping["semantic_phase"] = "observe"
        scene["semantic_plan"]["execution_phases"][phase["name"]] = mapping
        result = execute_scene(task, scene, test_harness={"kind": "recon_altitude_excursion"})
        self.assertEqual(result.status, "complete")
        transitions = {e["state"]: e["t_us"] for e in result.events if e["event"] == "test_reference_transition"}
        self.assertEqual(set(transitions), {"tracking", "lowering", "restored"})
        before_route = result.support_time_us < transitions["tracking"]
        self.assertLess(float(np.max(np.abs(result.support_positions[before_route, :, 0]))), 1e-10)
        self.assertGreater(float(np.min(result.support_positions[np.searchsorted(result.support_time_us, transitions["tracking"]), :, 2])), 9.15)
        for event in result.events:
            if event["event"] == "phase_arrived":
                self.assertGreaterEqual(event["t_us"], transitions["restored"])
        self.assertLess(float(np.max(np.abs(result.support_positions[-1, :, 2] - 8))), .3)

    def test_timeout_wins_when_hold_would_finish_exactly_at_deadline(self):
        task, scene = small_scene(distances=[0, 0], no_op=True, return_phase=False)
        result = execute_scene(task, scene, M2Config(execution=ExecutionConfig(max_duration_s=.4)))
        self.assertEqual(result.end_us, 400000)
        self.assertEqual(result.status, "timeout")
        self.assertFalse(any(e["event"] in ("phase_completed", "airborne_mission_completed") for e in result.events))
    def test_explicit_legacy_config_dispatches_m1(self):
        task = json.loads(FIXTURE.read_text(encoding="utf-8"))
        with patch("swarm_sim.fast_dynamics.mission_executor.run_mission_m1", return_value="legacy") as legacy:
            self.assertEqual(run_mission(task, FastDynamicsConfig()), "legacy")
            self.assertEqual(run_mission(task, {}), "legacy")
        self.assertEqual(legacy.call_count, 2)


if __name__ == "__main__":
    unittest.main()
