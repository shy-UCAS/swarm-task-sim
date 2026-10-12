"""Actual-state phase execution and dense boundary regressions, no SITL."""

import copy
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from swarm_sim.fast_dynamics.contracts import PlantState
from swarm_sim.fast_dynamics.engine import SynchronousEngine
from swarm_sim.fast_dynamics.mission_executor import run_mission
from swarm_sim.fast_dynamics.references import arrival_intervals, region_crossings


FIXTURE = Path(__file__).parent / "fixtures" / "fast_dynamics" / "rapid_passage_0000_v00.json"


def _run_fingerprint(arguments):
    task, config = arguments
    result = run_mission(task, config)
    digest = hashlib.sha256()
    for name in ("time_us", "positions", "velocities", "accelerations"):
        digest.update(getattr(result, name).tobytes())
    digest.update(json.dumps(result.events, sort_keys=True).encode())
    return digest.hexdigest()


class DenseEventsTests(unittest.TestCase):
    def test_short_arrival_crossing_between_output_frames(self):
        state = PlantState([[-.05, 0, 8]], [[1, 0, 0]], [[0, 0, 0]])
        intervals = arrival_intervals(state, np.zeros((1, 3)), 0, np.array([0, 0, 8]), .01, 2., .1)
        np.testing.assert_allclose(intervals, [[.04, .06]], atol=1e-12)
        region = dict(min_east_m=0., min_north_m=-1., width_m=.02, height_m=2.)
        np.testing.assert_allclose(region_crossings(state, np.zeros((1, 3)), region, .1), [.05, .07])

    def test_near_endpoint_at_high_speed_is_not_arrival(self):
        state = PlantState([[0, 0, 8]], [[1, 0, 0]], [[0, 0, 0]])
        self.assertEqual(arrival_intervals(state, np.zeros((1, 3)), 0, np.array([0, 0, 8]), 1., .15, .02), [])

    def test_cli_retains_engine_failure_and_rejects_attempt_reuse(self):
        from scripts.run_fast_dynamics import main
        with tempfile.TemporaryDirectory() as temp:
            # The CLI now requires the target under an explicitly selected external root.
            output = Path(temp) / "attempt"
            with patch("scripts.run_fast_dynamics.run_mission", side_effect=ArithmeticError("numerical failure")):
                with self.assertRaises(ArithmeticError):
                    main([str(FIXTURE), "--output", str(output), "--output-root", temp])
            self.assertEqual((output / "input_task.json").read_bytes(), FIXTURE.read_bytes())
            self.assertEqual(json.loads((output / "failure.json").read_text())["error_type"], "ArithmeticError")
            self.assertTrue((output / "config.json").is_file())
            self.assertFalse((output / "completion.json").exists())
            with self.assertRaises(SystemExit):
                main([str(FIXTURE), "--output", str(output), "--output-root", temp])


class MissionExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.result = run_mission(cls.task)

    def test_frozen_input_and_successful_actual_execution(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                         "dd5beb91f5388991487aab15c07493f74075e5ea17d99225db7313b2412ee318")
        result = self.result
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.positions.shape, (int(np.ceil(result.end_us / 100000)), 2, 3))
        np.testing.assert_array_equal(result.time_us, np.arange(len(result.time_us)) * 100000)
        self.assertLess(result.time_us[-1], result.end_us)
        self.assertEqual(result.support_time_us[-1], result.end_us)
        self.assertTrue(np.all(np.diff(result.support_time_us) > 0))
        arrivals = [e for e in result.events if e["event"] == "phase_arrived"]
        self.assertEqual(len(arrivals), 4)
        for event in arrivals:
            index = int(np.searchsorted(result.support_time_us, event["t_us"]))
            agent_index = result.agent_ids.index(event["agent_id"])
            self.assertLessEqual(np.linalg.norm(result.support_velocities[index, agent_index]), .15 + 1e-5)
        for phase in result.scene["phases"][1:]:
            release = next(e["t_us"] for e in result.events if e["event"] == "phase_released" and e["phase"] == phase["name"])
            previous = result.scene["phases"][result.scene["phases"].index(phase) - 1]["name"]
            self.assertGreaterEqual(release, max(e["t_us"] for e in result.events
                if e["event"] == "phase_hold_ended" and e["phase"] == previous))
        self.assertEqual(self.task, json.loads(FIXTURE.read_text(encoding="utf-8")))

    def test_repeatability_and_agent_permutation(self):
        task = copy.deepcopy(self.task)
        task["scenario"]["vehicles"].reverse()
        alternate = run_mission(task)
        for name in ("positions", "velocities", "accelerations", "time_us", "support_positions"):
            np.testing.assert_array_equal(getattr(self.result, name), getattr(alternate, name))
        self.assertEqual(self.result.events, alternate.events)

    def test_worker_count_and_dispatch_order_do_not_change_trajectory(self):
        jobs = [(self.task, {}), (self.task, {"execution": {"max_duration_s": .03}})]
        sequential = [_run_fingerprint(job) for job in jobs]
        with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn")) as workers:
            parallel = list(workers.map(_run_fingerprint, reversed(jobs)))
        self.assertEqual(sequential, list(reversed(parallel)))

    def test_half_step_on_common_axis_and_actual_events(self):
        fine = run_mission(self.task, {"engine": {"step_us": 10000}})
        count = min(len(fine.time_us), len(self.result.time_us))
        for name in ("positions", "velocities"):
            errors = np.linalg.norm(getattr(fine, name)[:count] - getattr(self.result, name)[:count], axis=2)
            self.assertLessEqual(float(np.quantile(errors, .99)), .02, (name, float(errors.max())))
        index = lambda r: {(e["event"], e.get("phase"), e.get("agent_id")): e["t_us"] for e in r.events}
        coarse_events, fine_events = index(self.result), index(fine)
        self.assertEqual(coarse_events.keys(), fine_events.keys())
        self.assertLessEqual(max(abs(t - fine_events[k]) for k, t in coarse_events.items()), 100000)

    def test_timeout_is_real_truncation_not_label_rewrite(self):
        result = run_mission(self.task, {"execution": {"max_duration_s": .03}})
        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.end_us, 30000)
        self.assertEqual(len(result.time_us), 1)
        self.assertFalse(any(e["event"] == "phase_arrived" for e in result.events))
        self.assertFalse(any(e.get("phase") == "p01_transit" for e in result.events))

    def test_waiting_agent_must_reconfirm_after_losing_arrival(self):
        original = SynchronousEngine.step

        def disturbed(engine, desired, dt_us=None):
            desired = desired.copy()
            if 7_400_000 <= engine.time_us < 8_400_000:
                desired[0, 0] = 2.5
            return original(engine, desired, dt_us)

        with patch.object(SynchronousEngine, "step", disturbed):
            result = run_mission(self.task)
        resets = [e for e in result.events if e["event"] == "phase_confirmation_reset"]
        self.assertTrue(resets)
        release = next(e["t_us"] for e in result.events if e["event"] == "phase_released" and e["phase"] == "p01_transit")
        self.assertGreater(release, max(e["t_us"] for e in resets))
        index = np.searchsorted(result.support_time_us, release)
        self.assertTrue(np.all(np.linalg.norm(result.support_velocities[index], axis=1) <= .15 + 1e-5))

    def test_unimplemented_scope_rejected(self):
        task = json.loads((FIXTURE.parents[3] / "missions/v3/rapid_passage_route_v06.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "two-vehicle"):
            run_mission(task)


if __name__ == "__main__":
    unittest.main()
