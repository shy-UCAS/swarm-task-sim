"""Hand-computable WP-S evidence; these tests never launch a simulator."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.spike_route_metrics import (analyze_spike, assign_waypoint_events, phase_windows,
                                        stop_intervals, summarize_spikes, waypoint_metrics)
from swarm_sim.scenario import enu_to_geo


def point(x, y=0.5):
    return dict(east_m=x, north_m=y, up_m=8)


def plan_fixture():
    return dict(schema_version=1, phases=[dict(name="observe", semantic_phase="observe",
        start_positions={"a": point(0)}, routes={"a": [point(1), point(2)]}, speed_m_s=1, terminal_hold_s=0.5)])


class SpikeMetricsTests(unittest.TestCase):
    def test_stop_duration_is_timestamp_span_not_sample_count(self):
        rows = [(t, [1, 0.5, 8, 0.1, 0, 0]) for t in (0, 0.1, 0.2)]
        self.assertEqual(stop_intervals(rows, [1, 0.5, 8], 0.15), [[0, 0.2]])
        self.assertEqual(stop_intervals(rows[:2], [1, 0.5, 8], 0.15), [])

    def test_gap_invalid_and_radius_each_break_stop(self):
        self.assertEqual(stop_intervals([(0, [1, 0.5, 8, 0, 0]), (0.3, [1, 0.5, 8, 0, 0])], [1, 0.5, 8], 0.15), [])
        self.assertEqual(stop_intervals([(0, [1, 0.5, 8, 0, 0]), (0.1, None), (0.2, [1, 0.5, 8, 0, 0])], [1, 0.5, 8], 0.15), [])
        rows = [(i/10, [3, 0.5, 8, 0, 0]) for i in range(4)]
        self.assertEqual(stop_intervals(rows, [1, 0.5, 8], 0.15), [])
        rows = [(i/10, [1, 0.5, 8, 0.3, 0]) for i in range(4)]
        self.assertEqual(stop_intervals(rows, [1, 0.5, 8], 0.15), [])

    def test_phase_sequence_identity_and_raw_receive_time(self):
        phases = [dict(name="one"), dict(name="two")]
        events = [dict(agent_id="a", phase=p, event=e, t=t) for p, e, t in [
            ("one", "spike_phase_upload_start", 0), ("one", "phase_start_sent", 1),
            ("one", "phase_auto_confirmed", 1.5), ("two", "spike_phase_upload_start", 3),
            ("two", "phase_start_sent", 4)]]
        packets = {"a": [dict(recv_monotonic_s=100+t, message=dict(mavpackettype="MISSION_ITEM_REACHED", seq=seq))
                          for t, seq in [(0.5, 0), (1.2, 2), (1.2, 2), (3.5, 2), (4.2, 2), (4.3, 1)]]}
        result = assign_waypoint_events(packets, events, phases, 100, 6)
        self.assertEqual([r["phase"] for r in result], [None, "one", "one", None, "two", "two"])
        self.assertAlmostEqual(result[1]["t_s"], 1.2)
        self.assertEqual(result[-1]["seq"], 1)

    def test_closest_point_uses_segment_and_event_lag(self):
        plan = plan_fixture()
        windows = [dict(phase="observe", agent_id="a", start_s=0, end_s=2, complete_execution_window=True)]
        traces = {"a": [(0, [0, 0.5, 8, 1, 0]), (1, [0.8, 0.5, 8, 1, 0]), (2, [2, 0.5, 8, 1, 0])]}
        reached = [dict(agent_id="a", phase="observe", seq=2, t_s=1.4)]
        result = waypoint_metrics(plan, windows, traces, reached, 10, 1.1)
        first = result["waypoints"][0]
        self.assertAlmostEqual(first["nearest_horizontal_m"], 0)
        self.assertAlmostEqual(first["nearest_t_s"], 1+1/6)
        self.assertAlmostEqual(first["event_lag_s"], 1.4-1-1/6)
        self.assertEqual(result["S_a"]["intermediate_count"], 1)
        self.assertEqual(result["S_a"]["stop_rate"], 0)

    def test_missing_route_evidence_is_unknown_not_zero_stops(self):
        windows = [dict(phase="observe", agent_id="a", start_s=0, end_s=2, complete_execution_window=True)]
        result = waypoint_metrics(plan_fixture(), windows, {"a": []}, [], 10, 0.5)
        self.assertEqual(result["S_a"]["unknown_count"], 1)
        self.assertIsNone(result["S_a"]["stop_rate"])

    def test_terminal_stop_excluded_and_cross_track_measured(self):
        windows = [dict(phase="observe", agent_id="a", start_s=0, end_s=0.3, complete_execution_window=True)]
        traces = {"a": [(i/10, [2.5, 1, 8, 0, 0]) for i in range(4)]}
        result = waypoint_metrics(plan_fixture(), windows, traces, [], 10, 0.5)
        self.assertIs(result["waypoints"][1]["stopped"], True)
        self.assertEqual(result["S_a"]["stopped_count"], 0)
        self.assertAlmostEqual(result["S_c"]["maximum_cross_track_m"]["maximum"], 2**-0.5)

    def test_incomplete_phase_window_cannot_be_certified(self):
        events = [dict(agent_id="a", phase="observe", event="phase_auto_confirmed", t=1)]
        windows = phase_windows(plan_fixture(), events, 5)
        self.assertFalse(windows[0]["complete_execution_window"])
        self.assertEqual(windows[0]["end_s"], 5)

    def test_confirmation_does_not_truncate_physical_or_service_evidence(self):
        plan = plan_fixture()
        events = [dict(agent_id="a", phase=p, event=e, t=t) for p, e, t in [
            ("observe", "phase_auto_confirmed", 0), ("observe", "task_target_verified", 1),
            ("return", "spike_phase_upload_start", 1.2), ("return", "phase_start_sent", 2)]]
        windows = phase_windows(plan, events, 3)
        self.assertEqual(windows[0]["end_s"], 1.2)
        self.assertEqual(windows[0]["diagnostic_end_s"], 2)
        traces = {"a": [(i/10, [i/10, 0.5, 8, 1, 0]) for i in range(21)]}
        result = waypoint_metrics(plan, windows, traces, [], 10, 0.5)
        self.assertEqual(result["waypoints"][-1]["nearest_t_s"], 2)
        self.assertEqual(result["waypoints"][-1]["nearest_horizontal_m"], 0)

    def test_two_run_gate_pools_counts_not_percentages(self):
        def result(stops, total):
            return dict(S_a=dict(stopped_count=stops, intermediate_count=total, unknown_count=0),
                        criteria=dict(dual_channel_coverage=True, truth_separation=True, execution_completed=True))
        report = summarize_spikes([result(1, 2), result(0, 18)])
        self.assertEqual(report["pooled_stop_rate"], 0.05)
        self.assertEqual(report["verdict"], "GO")
        self.assertEqual(summarize_spikes([result(0, 20)])["verdict"], "NO-GO")
        unknown = result(0, 20)
        unknown["S_a"]["unknown_count"] = 1
        self.assertEqual(summarize_spikes([result(0, 20), unknown])["verdict"], "UNKNOWN")

    def _write_fixture(self, root):
        origin = dict(lat=30., lon=120., alt_msl_m=12.)
        vehicles = [dict(id="a", east_m=0.5, north_m=0.5), dict(id="b", east_m=1.5, north_m=0.5)]
        scene = dict(origin=origin, vehicles=vehicles, record_hz=10, max_gap_s=0.5, min_separation_m=0.9,
            task_spec=dict(schema_version=2,
                scenario=dict(regions=[dict(id="R", min_east_m=0, min_north_m=0, width_m=2, height_m=1)]),
                mission=dict(target_region_id="R", coverage_required=0.9, return_required=False,
                             observation_model=dict(radius_m=0.1, height_tolerance_m=1, grid_m=1)),
                execution=dict(takeoff_alt_m=8, max_gap_s=0.5)))
        plan = dict(schema_version=1, phases=[dict(name="observe", semantic_phase="observe",
                    start_positions={v["id"]: point(v["east_m"]) for v in vehicles},
                    routes={v["id"]: [point(v["east_m"]), point(v["east_m"]+1)] for v in vehicles})])
        metadata = dict(scenario=scene, run_epoch_monotonic_s=100, flight_epoch_monotonic_s=102,
                        mission_end_monotonic_s=110, elapsed_s=12, status="completed")
        events = []
        (root/"raw").mkdir()
        for v in vehicles:
            a = v["id"]
            events.extend(dict(agent_id=a, phase="observe", event=e, t=t, duration_s=0.1, mission_item_count=4)
                          for e, t in [("spike_phase_upload_start", 1), ("spike_phase_upload_end", 1.1),
                                       ("phase_start_sent", 1.9), ("phase_auto_confirmed", 2), ("task_target_verified", 10)])
            lat, lon = enu_to_geo(v["east_m"], v["north_m"], origin)
            packets = []
            for i in range(121):
                packets.append(dict(recv_monotonic_s=100+i/10, message=dict(mavpackettype="SYSTEM_TIME", time_boot_ms=100*i)))
                packets.append(dict(recv_monotonic_s=100+i/10, message=dict(mavpackettype="GLOBAL_POSITION_INT", time_boot_ms=100*i,
                        lat=round(lat*1e7), lon=round(lon*1e7), alt=20000, vx=0, vy=0, vz=0)))
            packets.extend(dict(recv_monotonic_s=100+t, message=dict(mavpackettype="MISSION_ITEM_REACHED", seq=s))
                           for t, s in [(3, 2), (9, 3)])
            (root/"raw"/f"{a}.jsonl").write_text("\n".join(json.dumps(p) for p in packets), encoding="utf-8")
        for name, value in (("scenario.json", scene), ("spike_plan.json", plan), ("metadata.json", metadata)):
            (root/name).write_text(json.dumps(value), encoding="utf-8")
        (root/"events.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
        return scene

    def test_analyze_reuses_coverage_and_independent_truth_without_dataset_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            def actual(directory, agent, origin, preserve_invalid=False):
                x = 0.5 if agent == "a" else 1.5
                return [(i/10, [x, 0.5, 8, 1, 0, 0, 0]) for i in range(121)], {}, dict(available=True)
            with patch("scripts.spike_route_metrics.read_truth", side_effect=actual):
                result = analyze_spike(root)
            self.assertEqual(result["S_e"]["channels"]["truth"]["global_coverage_ratio"], 1)
            self.assertEqual(result["S_e"]["channels"]["observation"]["global_coverage_ratio"], 1)
            self.assertAlmostEqual(result["S_f"]["truth_separation"]["minimum_m"], 1)
            self.assertIs(result["criteria"]["truth_separation"], True)
            self.assertEqual(result["S_a"]["stop_rate"], 1)
            self.assertEqual(result["verdict"], "NO-GO")
            self.assertTrue((root/"spike_metrics.json").is_file())
            self.assertTrue((root/"waypoint_events.csv").is_file())
            self.assertFalse((root/"analysis_latest.json").exists())
            self.assertFalse((root/"labels.json").exists())

    def test_missing_bin_never_substitutes_fcu_as_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            with patch("scripts.spike_route_metrics.read_truth", return_value=([], {}, dict(available=False, reason="missing BIN"))):
                result = analyze_spike(root)
            self.assertIsNone(result["criteria"]["truth_separation"])
            self.assertIsNone(result["criteria"]["dual_channel_coverage"])
            self.assertIsNone(result["S_f"]["truth_separation"]["minimum_m"])
            self.assertTrue(result["errors"])

    def test_missing_sim_segment_marks_coverage_unknown_even_when_ratio_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            def actual(directory, agent, origin, preserve_invalid=False):
                x = 0.5 if agent == "a" else 1.5
                rows = [(i/10, [x, 0.5, 8, 1, 0, 0, 0] if i != 50 else None) for i in range(121)]
                return rows, {}, dict(available=True)
            with patch("scripts.spike_route_metrics.read_truth", side_effect=actual):
                result = analyze_spike(root)
            self.assertEqual(result["S_e"]["channels"]["truth"]["global_coverage_ratio"], 1)
            self.assertIsNone(result["criteria"]["dual_channel_coverage"])

    def test_raw_gaps_are_not_filled_to_certify_zero_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            for path in (root/"raw").glob("*.jsonl"):
                packets = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                kept = []
                for p in packets:
                    if p["message"]["mavpackettype"] == "GLOBAL_POSITION_INT":
                        p["message"]["vx"] = 100
                        if p["message"]["time_boot_ms"] in (5000, 5100):
                            continue
                    kept.append(p)
                path.write_text("\n".join(json.dumps(p) for p in kept), encoding="utf-8")
            with patch("scripts.spike_route_metrics.read_truth", return_value=([], {}, dict(available=False, reason="missing"))):
                result = analyze_spike(root)
            self.assertEqual(result["S_a"]["stopped_count"], 0)
            self.assertEqual(result["S_a"]["unknown_count"], 2)
            self.assertIsNone(result["S_a"]["stop_rate"])

    def test_identical_ground_packets_keep_strict_timeline_failure_and_raw_evidence(self):
        # Regression for both real WP-S runs: a same-tick telemetry repeat
        # occurred BEFORE flight, but the frozen ObservationStream contract
        # invalidates the whole timeline. Neither deduplication nor cropping
        # to the later flight window may silently turn this case into GO.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            paths = sorted((root/"raw").glob("*.jsonl"))
            for path in paths:
                packets = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                for packet in packets:
                    if packet["message"]["mavpackettype"] == "GLOBAL_POSITION_INT":
                        packet["message"]["vx"] = 100
                path.write_text("\n".join(json.dumps(p) for p in packets), encoding="utf-8")
            def actual(directory, agent, origin, preserve_invalid=False):
                x = 0.5 if agent == "a" else 1.5
                return [(i/10, [x, 0.5, 8, 1, 0, 0, 0]) for i in range(121)], {}, dict(available=True)
            with patch("scripts.spike_route_metrics.read_truth", side_effect=actual):
                clean = analyze_spike(root)
                self.assertEqual(clean["verdict"], "GO")
                for path in paths:
                    packets = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                    index = next(i for i, p in enumerate(packets) if p["message"]["mavpackettype"] == "GLOBAL_POSITION_INT"
                                 and p["message"]["time_boot_ms"] == 500)
                    original = packets[index]
                    repeat = dict(original, recv_monotonic_s=original["recv_monotonic_s"]+0.001)
                    self.assertEqual(original["message"], repeat["message"])
                    packets.insert(index+1, repeat)
                    path.write_text("\n".join(json.dumps(p) for p in packets), encoding="utf-8")
                raw_before = {path: path.read_bytes() for path in paths}
                result = analyze_spike(root)
            self.assertEqual(result["verdict"], "UNKNOWN")
            self.assertEqual(result["S_a"]["unknown_count"], 2)
            self.assertIsNone(result["S_a"]["stop_rate"])
            self.assertIsNone(result["criteria"]["dual_channel_coverage"])
            self.assertIsNone(result["S_e"]["channels"]["observation"]["success"])
            self.assertEqual(result["S_e"]["channels"]["truth"]["global_coverage_ratio"], 1)
            for agent in ("a", "b"):
                self.assertEqual(result["truth_provenance"][agent]["observation_timeline_error"],
                                 "duplicate/nonmonotonic observation timestamps")
            self.assertEqual(raw_before, {path: path.read_bytes() for path in paths})


if __name__ == "__main__":
    unittest.main()
