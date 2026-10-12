"""Analytic and behavioral checks for the uncalibrated deterministic M1 core."""
import unittest

import numpy as np

from swarm_sim.fast_dynamics import (
    AccelerationENU, ControllerConfig, EngineConfig,
    FastDynamicsConfig, IdealObserver, PlantState, PointMassJerkPlant,
    SynchronousEngine, VehicleProfile, capabilities, dense_state,
    integer_output_grid, output_frame_count, seconds_to_us,
)


def state(p=((0, 0, 15),), v=None, a=None):
    p = np.asarray(p, dtype=float)
    return PlantState(p, np.zeros_like(p) if v is None else v,
                      np.zeros_like(p) if a is None else a)


class AnalyticDynamicsTests(unittest.TestCase):
    def test_constant_velocity(self):
        initial = state(v=((2, -3, .5),))
        actual = dense_state(initial, np.zeros((1, 3)), 4)
        np.testing.assert_allclose(actual.p, [[8, -12, 17]])
        np.testing.assert_array_equal(actual.v, initial.v)

    def test_constant_acceleration(self):
        initial = state(v=((2, -1, 0),), a=((1, 0, -.5),))
        plant = PointMassJerkPlant()
        actual = plant.step(initial, AccelerationENU(initial.a), 2)
        np.testing.assert_allclose(actual.p, [[6, -2, 14]])
        np.testing.assert_allclose(actual.v, [[4, -1, -1]])
        np.testing.assert_array_equal(plant.last_jerk, np.zeros((1, 3)))

    def test_constant_jerk_and_dense_boundary(self):
        plant = PointMassJerkPlant(VehicleProfile(max_jerk_m_s3=2))
        initial = state()
        actual = plant.step(initial, np.array([[3, 0, 0]]), .2)
        np.testing.assert_allclose(plant.last_jerk, [[2, 0, 0]])
        np.testing.assert_allclose(actual.a, [[.4, 0, 0]])
        np.testing.assert_allclose(actual.v, [[.04, 0, 0]])
        np.testing.assert_allclose(actual.p, [[.2**3 / 3, 0, 15]])
        midway = dense_state(initial, plant.last_jerk, .1)
        np.testing.assert_allclose(midway.p, [[.1**3 / 3, 0, 15]])

    def test_jerk_and_acceleration_feasible_throughout_each_step(self):
        plant = PointMassJerkPlant()
        current = state(p=((0, 0, 15), (1, 2, 20)))
        for k in range(300):
            request = np.array([[30 * np.cos(k), 30 * np.sin(k), (-1)**k * 20],
                                [-50, 50, (-1)**(k // 30) * 100]])
            previous = current
            current = plant.step(previous, request, .02)
            self.assertLessEqual(float(np.linalg.norm(plant.last_jerk, axis=1).max()), 8 + 1e-12)
            for fraction in (0, .5, 1):
                sample = dense_state(previous, plant.last_jerk, .02 * fraction)
                self.assertLessEqual(float(np.linalg.norm(sample.a[:, :2], axis=1).max()), 3 + 1e-12)
                self.assertLessEqual(float(sample.a[:, 2].max()), 2 + 1e-12)
                self.assertGreaterEqual(float(sample.a[:, 2].min()), -2 - 1e-12)
            np.testing.assert_allclose(current.v - previous.v,
                                       (previous.a + current.a) * .02 / 2, atol=1e-14)

    def test_long_step_does_not_overshoot_acceleration_target(self):
        actual = PointMassJerkPlant().step(state(), np.array([[3, 0, -2]]), 1)
        np.testing.assert_allclose(actual.a, [[3, 0, -2]])

    def test_actual_velocity_is_not_clipped(self):
        initial = state(v=((20, 0, 0),))
        actual = SynchronousEngine(FastDynamicsConfig(), initial).step(np.zeros((1, 3)))
        self.assertGreater(actual.v[0, 0], 19.9)
        self.assertLess(actual.v[0, 0], 20)

    def test_invalid_states_and_control_capabilities_rejected(self):
        for kwargs in ({"p": [[np.nan, 0, 0]], "v": [[0, 0, 0]], "a": [[0, 0, 0]]},
                       {"p": [[0, 0, 0]], "v": [[0, 0, 0], [0, 0, 0]], "a": [[0, 0, 0]]}):
            with self.assertRaises(ValueError):
                PlantState(**kwargs)
        with self.assertRaises(ValueError):
            PointMassJerkPlant().step(state(a=((4, 0, 0),)), np.zeros((1, 3)), .02)
        with self.assertRaises(ValueError):
            PointMassJerkPlant().step(state(), np.zeros((1, 3)), 0)
        with self.assertRaises(ValueError):
            ControllerConfig(control_type="BodyWrench")


class TimeAndContractTests(unittest.TestCase):
    def test_half_open_integer_grid_boundaries(self):
        for duration_us, expected in ((0, 0), (1, 1), (100_000, 1), (100_001, 2),
                                      (60_000_000, 600), (60_030_000, 601)):
            with self.subTest(duration_us=duration_us):
                self.assertEqual(output_frame_count(duration_us), expected)
                grid = integer_output_grid(duration_us)
                self.assertEqual(len(grid), expected)
                self.assertTrue(np.all(grid < duration_us))
        self.assertEqual(seconds_to_us(60.03), 60_030_000)
        for value in (True, -1, 10.5):
            with self.assertRaises(ValueError):
                output_frame_count(value)
        with self.assertRaises(ValueError):
            seconds_to_us(.0000001)

    def test_noncommensurate_output_uses_step_polynomial(self):
        engine = SynchronousEngine(FastDynamicsConfig(engine=EngineConfig(step_us=30_000)), state())
        self.assertEqual(engine.samples, [])
        for _ in range(3):
            engine.step(np.array([[4, 0, 0]]))
        initial = engine.state
        engine.step(np.array([[4, 0, 0]]))
        self.assertEqual([frame.t_us for frame in engine.samples], [0, 100_000])
        expected = dense_state(initial, engine.last_jerk, .01)
        np.testing.assert_array_equal(engine.samples[1].p, expected.p)
        self.assertEqual(engine.time_us, 120_000)
        with self.assertRaises(ValueError):
            engine.last_segment.at(120_001)

    def test_configuration_roundtrip_and_all_unknown_fields_rejected(self):
        default = FastDynamicsConfig()
        self.assertEqual(FastDynamicsConfig.from_dict(default.to_dict()), default)
        with self.assertRaises(ValueError):
            FastDynamicsConfig.from_dict({"speedup": 100})
        for group in default.to_dict():
            with self.subTest(group=group), self.assertRaises(ValueError):
                FastDynamicsConfig.from_dict({group: {"unexpected": 0}})
        for invalid in ({"engine": {"step_us": True}}, {"controller": {"state_source": "estimate"}},
                        {"observation": {"mode": "noise"}}, {"environment": {"mode": "wind"}},
                        {"vehicle_profile": {"max_jerk_m_s3": np.inf}},
                        {"execution": {"lifecycle_scope": "takeoff_to_landing"}}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                FastDynamicsConfig.from_dict(invalid)

    def test_dense_event_truncation_preserves_prefix_and_half_open_grid(self):
        engine = SynchronousEngine(FastDynamicsConfig(engine=EngineConfig(step_us=30_000)), state())
        with self.assertRaises(ValueError):
            engine.truncate_last_step(0)
        desired = np.array([[4, 0, 0]])
        for _ in range(4):
            engine.step(desired)
        expected = engine.last_segment.at(100_000)
        self.assertEqual([s.t_us for s in engine.samples], [0, 100_000])
        engine.truncate_last_step(100_000)
        self.assertEqual(engine.time_us, 100_000)
        self.assertEqual(engine.last_segment.end_us, 100_000)
        np.testing.assert_array_equal(engine.state.p, expected.p)
        np.testing.assert_array_equal(engine.state.v, expected.v)
        self.assertEqual([s.t_us for s in engine.samples], [0])
        for invalid in (89_999, 100_001):
            with self.assertRaises(ValueError):
                engine.truncate_last_step(invalid)
        engine.step(np.zeros((1, 3)))
        self.assertEqual([s.t_us for s in engine.samples], [0, 100_000])
        np.testing.assert_array_equal(engine.samples[-1].p, expected.p)
        self.assertEqual(engine.time_us, 130_000)

    def test_state_snapshot_serialization_and_observer(self):
        original = state()
        with self.assertRaises(ValueError):
            original.p[0, 0] = 2
        restored = PlantState.from_dict(original.to_dict())
        np.testing.assert_array_equal(restored.p, original.p)
        measurement = IdealObserver().sample(original, 123)
        np.testing.assert_array_equal(measurement.p, original.p)
        self.assertTrue(measurement.valid.all())
        self.assertEqual(measurement.measurement_time_us, measurement.delivery_time_us)
        self.assertIn("specific_force", capabilities()["unsupported_state_fields"])

    def test_agents_update_atomically_and_are_permutation_invariant(self):
        initial = state(p=((-2, 0, 15), (2, 0, 15)))
        engine = SynchronousEngine(FastDynamicsConfig(), initial)
        reverse = SynchronousEngine(FastDynamicsConfig(),
                                    PlantState(initial.p[::-1], initial.v[::-1], initial.a[::-1]))
        def towards_other(_time_us, snapshot):
            return snapshot.p[::-1] - snapshot.p
        for _ in range(100):
            engine.step(towards_other)
            reverse.step(towards_other)
        np.testing.assert_array_equal(engine.state.p, reverse.state.p[::-1])
        np.testing.assert_array_equal(engine.state.v, reverse.state.v[::-1])
        np.testing.assert_allclose(engine.state.p[:, 0].sum(), 0, atol=1e-14)
        np.testing.assert_array_equal(initial.p, [[-2, 0, 15], [2, 0, 15]])


class ResponseAndConvergenceTests(unittest.TestCase):
    @staticmethod
    def simulate(step_us):
        config = FastDynamicsConfig(engine=EngineConfig(step_us=step_us))
        engine = SynchronousEngine(config, state())
        checkpoints = {}
        while engine.time_us < 24_000_000:
            time_us = engine.time_us
            desired = [[5, 0, 0]] if time_us < 8_000_000 else (
                [[0, 5, 0]] if time_us < 16_000_000 else [[0, 0, 0]])
            engine.step(np.array(desired))
            if engine.time_us in (20_000, 8_000_000, 8_020_000, 16_000_000, 22_000_000, 24_000_000):
                checkpoints[engine.time_us] = engine.state
        return engine, checkpoints

    def test_start_turn_stop_and_terminal_dwell_are_dynamic(self):
        engine, checks = self.simulate(20_000)
        self.assertGreater(checks[20_000].v[0, 0], 0)
        self.assertLess(checks[20_000].v[0, 0], .01)
        # A ninety-degree reference switch cannot rotate actual velocity instantly.
        self.assertGreater(checks[8_020_000].v[0, 0], 4.9)
        self.assertLess(checks[8_020_000].v[0, 1], .01)
        # The corner is traversed on a finite-radius path, not by teleporting.
        turning = [s for s in engine.samples if 8.1 < s.t_s < 11]
        speeds = np.array([np.linalg.norm(s.v[0, :2]) for s in turning])
        rates = np.array([abs(np.cross(s.v[0], s.a[0])[2]) /
                          max(np.linalg.norm(s.v[0, :2]) ** 2, 1e-12) for s in turning])
        self.assertGreater(float(speeds.min()), 2)
        self.assertGreater(float(rates.max()), .1)
        self.assertLess(float(rates.max()), 2)
        self.assertLess(float(np.linalg.norm(engine.state.v)), .002)
        self.assertLess(float(np.linalg.norm(engine.state.p - checks[22_000_000].p)), .01)

    def test_repeatability_and_step_halving_convergence(self):
        coarse, _ = self.simulate(20_000)
        repeated, _ = self.simulate(20_000)
        fine, _ = self.simulate(10_000)
        reference, _ = self.simulate(5_000)
        np.testing.assert_array_equal(coarse.state.p, repeated.state.p)
        coarse_path = np.array([frame.p for frame in coarse.samples])
        fine_path = np.array([frame.p for frame in fine.samples])
        ref_path = np.array([frame.p for frame in reference.samples])
        coarse_error = np.linalg.norm(coarse_path - ref_path, axis=2).max()
        fine_error = np.linalg.norm(fine_path - ref_path, axis=2).max()
        self.assertLess(coarse_error, .15)
        self.assertLess(fine_error, coarse_error * .6)
        self.assertEqual(len(coarse.samples), 240)


if __name__ == "__main__":
    unittest.main()
