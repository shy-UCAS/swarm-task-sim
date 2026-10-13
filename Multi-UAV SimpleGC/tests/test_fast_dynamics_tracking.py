"""Actual plant/controller tests; expected node visits use independent geometry."""
import unittest
import copy

import numpy as np

from swarm_sim.fast_dynamics.contracts import EngineConfig, FastDynamicsConfig, PlantState
from swarm_sim.fast_dynamics.engine import SynchronousEngine
from swarm_sim.fast_dynamics.route_tracker import ReferenceConfig, RouteTracker


def fly(points, step_us=20_000, speed=3., initial=None, limit_s=300.):
    points = np.asarray(points, dtype=float)
    initial = np.asarray(initial if initial is not None else points[0], dtype=float)
    state = PlantState(initial[None, :], np.zeros((1, 3)), np.zeros((1, 3)))
    engine = SynchronousEngine(FastDynamicsConfig(engine=EngineConfig(step_us=step_us)), state)
    tracker = RouteTracker(points, speed, step_us=step_us)
    states = [initial.copy()]
    max_accel = max_jerk = 0.
    stop_events = []
    engine.committed_test_segments = []
    cycle_end = 0
    while engine.time_us < int(limit_s*1e6):
        if engine.time_us == cycle_end:
            cycle_end += step_us
        previous_tracker = copy.deepcopy(tracker)
        desired = tracker.command(engine.state.p[0], engine.state.v[0], engine.state.a[0])
        engine.step(desired[None, :], dt_us=cycle_end-engine.time_us)
        events = tracker.observe_segment(engine.last_segment)
        control_events = [e for e in events if e["event"] in ("route_primitive_advanced", "route_corner_stopped", "route_completed")
                          or e["event"] == "route_node_witnessed" and e["node_index"] == 0]
        if control_events:
            boundary = min(e["t_us"] for e in control_events)
            if boundary < engine.time_us:
                engine.truncate_last_step(boundary)
                tracker = previous_tracker
                events = tracker.observe_segment(engine.last_segment)
        stop_events.extend(e for e in events if e["event"] == "route_corner_stopped")
        engine.committed_test_segments.append(engine.last_segment)
        states.append(engine.state.p[0].copy())
        max_accel = max(max_accel, float(np.linalg.norm(engine.state.a[0, :2])))
        max_jerk = max(max_jerk, float(np.linalg.norm(engine.last_jerk[0])))
        if tracker.complete and np.linalg.norm(engine.state.p[0]-points[-1]) <= .1 and np.linalg.norm(engine.state.v[0]) <= .05:
            break
    return tracker, engine, np.array(states), max_accel, max_jerk, stop_events


class ContinuousRouteTests(unittest.TestCase):
    def assert_flight(self, points, **kwargs):
        result = fly(points, **kwargs)
        tracker, engine, positions, acceleration, jerk, _ = result
        self.assertTrue(tracker.complete, (tracker.diagnostics, engine.state.to_dict()))
        self.assertLess(np.linalg.norm(engine.state.p[0]-points[-1]), .101)
        self.assertLess(np.linalg.norm(engine.state.v[0]), .051)
        self.assertLessEqual(acceleration, 3+1e-10)
        self.assertLessEqual(jerk, 8+1e-10)
        # Independent ordered original-node check on physics-step endpoints.
        # The tiny-node test below adds a tighter interpolation witness check.
        cursor = 0
        for point in points:
            found = np.flatnonzero(np.linalg.norm(positions[cursor:, :2]-np.asarray(point)[:2], axis=1) <= .5)
            self.assertTrue(len(found), (point, cursor))
            cursor += int(found[0])
        return result

    def test_straight_stops_without_editing_plant(self):
        _, _, positions, *_ = self.assert_flight([[0, 0, 8], [60, 0, 8]])
        self.assertLess(np.abs(positions[:, 1]).max(), 1e-12)

    def test_right_angle_continuously_tracks(self):
        _, engine, positions, *_ = self.assert_flight([[0, 0, 8], [30, 0, 8], [30, 30, 8]])
        distances = np.minimum(np.abs(positions[:, 1]), np.abs(positions[:, 0]-30))
        self.assertLess(distances.max(), 1.)
        corner_samples = [s for s in engine.samples if np.linalg.norm(s.p[0, :2]-[30, 0]) < .5]
        self.assertTrue(corner_samples)
        self.assertGreater(min(np.linalg.norm(s.v[0]) for s in corner_samples), .001)

    def test_short_leg_visits_distinct_gates(self):
        points = [[0, 0, 8], [30, 0, 8], [30, .106227234, 8], [60, .106227234, 8]]
        tracker, _, positions, *_ = self.assert_flight(points)
        gate = .2*.106227234
        visits = []
        cursor = 0
        for point in points[1:3]:
            found = np.flatnonzero(np.linalg.norm(positions[cursor:, :2]-np.asarray(point)[:2], axis=1) <= gate)
            self.assertTrue(len(found), point)
            cursor += int(found[0])
            visits.append(cursor)
        self.assertGreater(visits[1], visits[0])
        self.assertGreater(np.linalg.norm(positions[visits[1], :2]-positions[visits[0], :2]), .0637)
        self.assertEqual(tracker.next_node, 4)

    def test_closed_two_laps_not_complete_at_origin(self):
        points = [[0, 0, 8], [10, 0, 8], [10, 10, 8], [0, 10, 8], [0, 0, 8],
                  [10, 0, 8], [10, 10, 8], [0, 10, 8], [0, 0, 8]]
        tracker = RouteTracker(points, 3.)
        self.assertFalse(tracker.complete)
        tracker, _, positions, *_ = self.assert_flight(points)
        self.assertEqual(len(tracker.witnesses), 9)
        self.assertGreater(sum(np.linalg.norm(np.diff(positions[:, :2], axis=0), axis=1)), 75)

    def test_reversal_stops_with_physical_state(self):
        _, engine, positions, _, _, stops = self.assert_flight([[0, 0, 8], [20, 0, 8], [2, 0, 8]])
        self.assertEqual(len(stops), 1)
        self.assertGreater(stops[0]["t_us"], 0)
        self.assertLess(np.abs(positions[:, 1]).max(), .25)
        event_time = stops[0]["t_us"]
        # Independently evaluate the actual committed polynomials over the
        # full 50 ms physical stopping interval, rather than trusting an event.
        for tick in range(event_time-50_000, event_time+1, 1_000):
            segment = next(s for s in engine.committed_test_segments if s.start_us <= tick <= s.end_us)
            state = segment.at(tick)
            self.assertLessEqual(np.linalg.norm(state.p[0, :2]-[20, 0]), .25+1e-10)
            self.assertLessEqual(np.linalg.norm(state.v[0]), .001+1e-9)
            self.assertLessEqual(np.linalg.norm(state.a[0]), .01+1e-9)

    def test_half_step_trajectory_and_event_convergence(self):
        for points in ([[0, 0, 8], [30, 0, 8], [30, 30, 8]],
                       [[0, 0, 8], [20, 0, 8], [2, 0, 8]]):
            with self.subTest(points=points):
                tracker, coarse, *_ = self.assert_flight(points)
                fine_tracker, fine, *_ = self.assert_flight(points, step_us=10_000)
                n = min(len(coarse.samples), len(fine.samples))
                for field in ("p", "v"):
                    differences = [np.linalg.norm(getattr(a, field)-getattr(b, field))
                                   for a, b in zip(coarse.samples[:n], fine.samples[:n])]
                    self.assertLessEqual(np.percentile(differences, 99), .02)
                self.assertLessEqual(abs(coarse.time_us-fine.time_us), 20_000)
                for a, b in zip(tracker.witnesses, fine_tracker.witnesses):
                    self.assertLessEqual(abs(a["t_us"]-b["t_us"]), 20_000)

    def test_general_angle_curves_use_real_arclength(self):
        for angle in (150., 174.9):
            radians = np.radians(angle)
            points = [[0, 0, 8], [30, 0, 8], [30+30*np.cos(radians), 30*np.sin(radians), 8]]
            with self.subTest(angle=angle):
                tracker, _, positions, *_ = self.assert_flight(points)
                curve = next(p for p in tracker.primitives if p.control is not None)
                self.assertLess(curve.length, .5)
                self.assertGreater(curve.length, 0.)
                for primitive in tracker.primitives:
                    np.testing.assert_allclose(primitive.point(0)[0], primitive.start, atol=1e-9)
                    np.testing.assert_allclose(primitive.point(primitive.length)[0], primitive.end, atol=1e-9)

    def test_offset_start_acquires_original_start(self):
        self.assert_flight([[0, 0, 8], [10, 0, 8]], initial=[-1, .4, 8])

    def test_far_cross_track_does_not_grant_completion(self):
        from swarm_sim.fast_dynamics.engine import StepSegment
        tracker = RouteTracker([[0, 0, 8], [30, 0, 8]], 3.)
        state = PlantState([[30, 100, 8]], [[0, 0, 0]], [[0, 0, 0]])
        tracker.observe_segment(StepSegment(0, 20_000, state, np.zeros((1, 3))))
        self.assertFalse(tracker.complete)
        self.assertEqual(tracker.next_node, 0)

    def test_noop_and_raw_positive_short_leg(self):
        self.assertTrue(RouteTracker([[0, 0, 8]], 3.).complete)
        self.assert_flight([[0, 0, 8], [.001, 0, 8]])
        with self.assertRaises(ValueError):
            RouteTracker([[0, 0, 8], [0, 0, 8]], 3.)

    def test_reference_rejects_invalid_fields(self):
        for values in ({"corner_leg_fraction": .2}, {"corner_cut_max_m": 1.},
                       {"tracking_tube_m": 1.}, {"preview_time_s": 0.},
                       {"velocity_damping": float("nan")}):
            with self.assertRaises(ValueError):
                ReferenceConfig(**values)


if __name__ == "__main__":
    unittest.main()
