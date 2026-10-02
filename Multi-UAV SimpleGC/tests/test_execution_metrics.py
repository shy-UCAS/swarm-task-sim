"""E10 hand-calculated diagnostics plus missing-evidence and grouping guards."""

import copy
import unittest

from swarm_sim.execution_metrics import compute_execution_metrics, stop_segments, synchronized_stops


def fixture():
    scene = dict(record_hz=8, vehicles=[dict(id="a"), dict(id="b")], planning=dict(
        partition_axis="east", per_agent_reference_routes={agent: {
            "approach": [dict(east_m=offset, north_m=0)],
            "observe": [dict(east_m=offset, north_m=0), dict(east_m=offset, north_m=10),
                        dict(east_m=offset + 2, north_m=10), dict(east_m=offset + 2, north_m=0)], "return": []}
        for agent, offset in (("a", 0), ("b", 20))}))
    traces = {"a": [(i / 8, [0, 10, 8, 0 if i <= 4 else 1, 0, 0]) for i in range(9)],
              "b": [(i / 8, [22, 0, 8, 0 if 2 <= i <= 6 else 1, 0, 0]) for i in range(9)]}
    windows = [dict(agent_id=agent, phase="observe_0", semantic_phase="observe", start_s=0, end_s=1,
                    complete_execution_window=True) for agent in ("a", "b")]
    return scene, traces, windows


class ExecutionMetricsTests(unittest.TestCase):
    def test_E10_stop_counts_stationary_and_synchronization_hand_calculation(self):
        result = compute_execution_metrics(*fixture())
        report = result["thresholds"]["0.3"]
        self.assertEqual([r["stop_count"] for r in report["per_agent"].values()], [1, 1])
        self.assertEqual(report["stationary_time_s"], 1)
        self.assertEqual(report["stationary_time_fraction"], .5)
        self.assertEqual(report["synchronized_grid_points"], 3)
        self.assertEqual(report["grid_points"], 9)
        self.assertEqual(report["synchronized_time_fraction"], 3 / 9)
        self.assertEqual(report["fleet_stop_event_count"], 1)
        self.assertEqual(report["common_overlap_event_count"], 1)
        self.assertEqual(report["common_overlap_event_fraction"], 1)

    def test_E10_stop_location_categories_are_disjoint(self):
        result = compute_execution_metrics(*fixture())["thresholds"]["0.3"]["per_agent"]
        self.assertEqual(result["a"]["counts_by_location"], dict(intermediate_waypoint=1, semantic_endpoint=0, other=0))
        self.assertEqual(result["b"]["counts_by_location"], dict(intermediate_waypoint=0, semantic_endpoint=1, other=0))
        scene, traces, windows = fixture()
        for row in traces["a"]:
            row[1][0] = 100
        self.assertEqual(compute_execution_metrics(scene, traces, windows)["thresholds"]["0.3"]["per_agent"]["a"]["counts_by_location"]["other"], 1)

    def test_E10_threshold_duration_gap_and_missing_speed(self):
        self.assertEqual(stop_segments([(0, .3), (.1, .3), (.2, .3)]), [])
        self.assertEqual(stop_segments([(0, .29), (.1, .29), (.2, .29)]), [(0, .2)])
        self.assertEqual(stop_segments([(0, 0), (.1, None), (.2, 0)]), [])
        self.assertEqual(stop_segments([(0, 0), (.2, 0)]), [])
        self.assertEqual(stop_segments([(0, .4), (.1, .4), (.2, .4)], threshold=.5), [(0, .2)])
        for samples in ([(0, 0), (0, 0)], [(1, 0), (0, 0)], [(float("nan"), 0)]):
            with self.assertRaisesRegex(ValueError, "strict"):
                stop_segments(samples)

    def test_E10_exact_intersection_avoids_audit_envelope_false_positive(self):
        # A's separated intervals bridge via B; C is present only between A's.
        intervals = {"a": [(0, 1), (3, 4)], "b": [(0, 4)], "c": [(1.5, 2.5)]}
        result = synchronized_stops(intervals, 0, 4, .5)
        self.assertEqual(result["synchronized_time_fraction"], 0)
        self.assertEqual(result["common_overlap_event_count"], 0)
        self.assertEqual(result["audit_envelope_common_event_count"], 1)

    def test_E10_missing_aircraft_or_timeline_unknown_not_zero(self):
        for malformed in ([], [(0, None)], [(0, [0, 0, 8, 0, 0]), (0, [0, 0, 8, 0, 0])]):
            scene, traces, windows = fixture()
            traces["a"] = malformed
            result = compute_execution_metrics(scene, traces, windows)
            self.assertIsNone(result["thresholds"]["0.3"]["per_agent"]["a"]["stop_count"])
            self.assertIsNone(result["thresholds"]["0.3"]["synchronized_time_fraction"])
            self.assertIsNone(result["thresholds"]["0.3"]["stationary_time_fraction"])

    def test_scan_line_group_uses_10m_sweeps_not_2m_lane_changes(self):
        result = compute_execution_metrics(*fixture())["intermediate_waypoints"]
        self.assertEqual(set(result["by_scan_line_length_m"]), {"10.000000"})
        self.assertEqual(result["by_scan_line_length_m"]["10.000000"]["waypoint_count"], 6)
        self.assertEqual({r["scan_line_length_m"] for r in result["records"]}, {10})
        actual = next(r for r in result["records"] if r["agent_id"] == "a" and r["waypoint_index"] == 1)
        self.assertEqual(actual["minimum_passing_speed_m_s"], 0)
        self.assertTrue(actual["stopped"])

    def test_missing_window_and_partial_evidence_never_claim_complete_fleet_fraction(self):
        scene, traces, windows = fixture()
        result = compute_execution_metrics(scene, traces, [])
        self.assertIsNone(result["thresholds"]["0.3"]["per_agent"]["a"]["stop_count"])
        self.assertFalse(result["evidence_complete"])
        traces["a"][3] = (3 / 8, None)
        result = compute_execution_metrics(scene, traces, windows)
        self.assertIsNone(result["thresholds"]["0.3"]["synchronized_time_fraction"])
        self.assertTrue(result["thresholds"]["0.3"]["per_agent"]["a"]["stop_count_is_lower_bound"])

    def test_timing_requires_actual_new_evidence_and_converts_event_epoch(self):
        scene, traces, windows = fixture()
        unknown = compute_execution_metrics(scene, traces, windows)
        self.assertFalse(unknown["arrival_lag_s"]["available"])
        self.assertFalse(unknown["nominal_timing_deviation_s"]["available"])
        windows[0].update(arrival_s=.75)
        event = dict(event="waypoint_reached", agent_id="a", phase="observe_0", terminal=True, t=1)
        result = compute_execution_metrics(scene, traces, windows, events=[event],
            metadata=dict(run_epoch_monotonic_s=100), time_epoch=100,
            nominal_arrivals=[dict(agent_id="a", actual_s=.75, nominal_s=.5)])
        self.assertEqual(result["arrival_lag_s"]["distribution"]["median"], .25)
        self.assertEqual(result["barrier_wait_s"]["distribution"]["median"], .25)
        self.assertEqual(result["nominal_timing_deviation_s"]["max_abs_s"], .25)

    def test_inputs_unchanged_and_metrics_excluded_from_features(self):
        data = fixture()
        before = copy.deepcopy(data)
        result = compute_execution_metrics(*data)
        self.assertEqual(data, before)
        self.assertTrue(result["diagnostic_only"])
        self.assertFalse(result["model_feature_eligible"])


if __name__ == "__main__":
    unittest.main()
