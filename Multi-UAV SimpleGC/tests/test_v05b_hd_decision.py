"""Offline checks for the SIM-truth terminal dwell definition."""

import unittest

from scripts.decide_v05b_hd import (same_terminal_denominator,
    stable_terminal_window, terminal_fraction)


class TerminalDwellTests(unittest.TestCase):
    def test_contiguous_low_speed_near_terminal_proves_dwell(self):
        rows = [(index / 10, (0.0, 0.0, 5.0)) for index in range(6)]
        window = dict(terminal_waypoint_reached_s=.1, end_s=.5,
                      terminal_point=dict(east_m=0.0, north_m=0.0, up_m=5.0))
        result = stable_terminal_window(rows, window, .5)
        self.assertTrue(result["stopped"])
        self.assertTrue(result["evidence_complete"])
        self.assertGreaterEqual(result["best_stable_duration_s"], .2)

    def test_gap_speed_and_missing_event_never_prove_stop(self):
        window = dict(terminal_waypoint_reached_s=.1, end_s=.5,
                      terminal_point=dict(east_m=0.0, north_m=0.0, up_m=5.0))
        rows = [(0.0, (0.0, 0.0, 5.0)), (.1, (0.0, 0.0, 5.0)),
                (.2, (2.0, 0.0, 5.0)), (.3, (0.0, 0.0, 5.0)),
                (.4, (0.0, 0.0, 5.0)), (.5, (0.0, 0.0, 5.0))]
        self.assertFalse(stable_terminal_window(rows, window, .5)["stopped"])
        self.assertFalse(stable_terminal_window(rows, dict(window,
            terminal_waypoint_reached_s=None), .5)["evidence_complete"])
        gap = [(0.0, (0.0, 0.0, 5.0)), (.1, (0.0, 0.0, 5.0)),
               (.4, (0.0, 0.0, 5.0)), (.5, (0.0, 0.0, 5.0))]
        self.assertFalse(stable_terminal_window(gap, window, .15)["stopped"])

    def test_altitude_and_missing_samples_cannot_prove_terminal_dwell(self):
        window = dict(terminal_waypoint_reached_s=.1, end_s=.5,
                      terminal_point=dict(east_m=0.0, north_m=0.0, up_m=5.0))
        high = [(index / 10, (0.0, 0.0, 6.2)) for index in range(6)]
        self.assertFalse(stable_terminal_window(high, window, .5, .1)["stopped"])
        invalid = [(index / 10, None if index == 3 else (0.0, 0.0, 5.0))
                   for index in range(6)]
        self.assertFalse(stable_terminal_window(invalid, window, .5, .1)["evidence_complete"])
        missing_edge = [(index / 10, (0.0, 0.0, 5.0)) for index in range(3, 6)]
        self.assertFalse(stable_terminal_window(missing_edge, window, .5, .1)["evidence_complete"])
        gap = [(0.0, (0.0, 0.0, 5.0)), (.1, (0.0, 0.0, 5.0)),
               (.4, (0.0, 0.0, 5.0)), (.5, (0.0, 0.0, 5.0))]
        self.assertFalse(stable_terminal_window(gap, window, .15, .1)["evidence_complete"])

    def test_denominator_is_non_no_op_terminal_windows(self):
        scene = dict(max_gap_s=.5, record_hz=10, phases=[dict(name="observe", semantic_phase="observe",
            routes={"uav_01": [dict(east_m=0)], "uav_02": []})])
        window = dict(phase="observe", agent_id="uav_01",
            terminal_waypoint_reached_s=.1, end_s=.5,
            terminal_point=dict(east_m=0.0, north_m=0.0, up_m=5.0))
        rows = [(index / 10, (0.0, 0.0, 5.0)) for index in range(6)]
        result = terminal_fraction(scene, dict(channels=dict(truth=[window])),
                                   {"uav_01": rows, "uav_02": rows})
        self.assertEqual(result["window_count"], 1)
        self.assertEqual(result["stopped_count"], 1)
        self.assertEqual(result["fraction"], 1.0)

    def test_vp1_vp4_require_identical_phase_agent_denominator(self):
        a = dict(window_count=2, windows=[dict(phase="patrol", agent_id="uav_01"),
                                          dict(phase="return", agent_id="uav_01")])
        b = dict(window_count=2, windows=[dict(phase="return", agent_id="uav_01"),
                                          dict(phase="patrol", agent_id="uav_01")])
        self.assertTrue(same_terminal_denominator(a, b))
        b["windows"][1]["agent_id"] = "uav_02"
        self.assertFalse(same_terminal_denominator(a, b))


if __name__ == "__main__":
    unittest.main()
