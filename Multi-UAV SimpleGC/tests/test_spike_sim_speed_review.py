"""Synthetic source-time speed checks; no SITL, production edits or raw writes."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.spike_sim_speed_review import (compute_sim_speed_review, differentiate_sim_positions,
                                             map_sim_speed_samples)


class SimSpeedReviewTests(unittest.TestCase):
    def test_velocity_uses_source_delta_before_nonlinear_host_mapping(self):
        samples = [(0, [0, 0, 8]), (0.1, [0.1, 0.2, 8]), (0.2, [0.2, 0.4, 8])]
        rows, info = differentiate_sim_positions(samples, 0.15)
        mapped = map_sim_speed_samples(rows, dict(available=True, knots=[[0, 10], [0.1, 10.13], [0.2, 10.21]]))
        self.assertEqual(mapped[1][1][3:5], [1, 2])
        self.assertEqual(mapped[2][1][3:5], [1, 2])
        self.assertAlmostEqual(mapped[1][0], 10.13)
        self.assertEqual(info["velocity_samples"], 2)

    def test_duplicate_conflict_and_rollback_all_reject_source_axis(self):
        for second in [(0, [0, 0, 8]), (0, [1, 0, 8]), (-0.1, [0, 0, 8])]:
            rows, info = differentiate_sim_positions([(0, [0, 0, 8]), second], 0.15)
            self.assertEqual(rows, [])
            self.assertTrue(info["source_time_error"])

    def test_gap_or_invalid_pose_never_differentiated_across(self):
        rows, info = differentiate_sim_positions([(0, [0, 0, 8]), (0.1, None),
            (0.2, [0, 0, 8]), (0.3, [0, 0, 8]), (0.6, [0, 0, 8])], 0.15)
        self.assertEqual([v is None for _, v in rows], [True, True, True, False, True])
        self.assertEqual(info["invalid_positions"], 1)
        self.assertEqual(info["gap_count"], 1)

    def test_invalid_timestamp_and_nonfinite_pose_remain_invalid(self):
        rows, info = differentiate_sim_positions([(float("nan"), [0, 0, 8])], 0.15)
        self.assertEqual(rows, [])
        self.assertTrue(info["source_time_error"])
        rows, info = differentiate_sim_positions([(0, [0, 0, 8]), (0.1, [float("nan"), 0, 8])], 0.15)
        self.assertEqual(rows[-1][1], None)
        self.assertEqual(info["invalid_positions"], 1)

    def test_missing_clock_and_extrapolation_never_fallback_to_host_receipt(self):
        samples = [(0, [0, 0, 8, 1, 0, 0]), (1, [1, 0, 8, 1, 0, 0]), (2, None)]
        self.assertEqual(map_sim_speed_samples(samples, {}), [])
        self.assertEqual(map_sim_speed_samples(samples, dict(available=True, knots=[[0.5, 4], [1.5, 5]])),
                         [(4.5, [1, 0, 8, 1, 0, 0])])

    def _run_fixture(self, samples, clock=True):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scene = dict(record_hz=10, max_gap_s=0.5, vehicles=[dict(id="a")],
                origin=dict(lat=30, lon=120, alt_msl_m=12))
            for name, value in [("scenario.json", scene), ("metadata.json", dict(elapsed_s=1.2))]:
                (root/name).write_text(json.dumps(value), encoding="utf-8")
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            point = lambda x: dict(east_m=x, north_m=0, up_m=8)
            plan = dict(phases=[dict(name="observe", semantic_phase="observe",
                start_positions={"a": point(-1)}, routes={"a": [point(0), point(3)]})])
            windows = [dict(phase="observe", agent_id="a", start_s=0.2, end_s=1,
                diagnostic_end_s=1, complete_execution_window=True)]
            clocks = {"a": dict(available=clock, knots=[[0, 0], [1.2, 1.2]])}
            with patch("scripts.spike_sim_speed_review.read_truth", return_value=(samples, {}, dict(available=True))), \
                 patch("scripts.spike_sim_speed_review.inspect_sim_formats", return_value={}):
                result = compute_sim_speed_review(root, plan, windows, clocks)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            return result

    def test_stationary_position_proves_estimated_stop_without_reading_FCU(self):
        result = self._run_fixture([(i/10, [0, 0, 8, 1, 0, 0, 0]) for i in range(13)])
        self.assertEqual(result["S_a"]["stopped_count"], 1)
        self.assertEqual(result["S_a"]["stop_rate"], 1)
        self.assertEqual(result["S_b"]["minimum"], 0)
        self.assertFalse(result["direct_truth_velocity_available"])
        self.assertEqual(result["status"], "auxiliary_estimate_not_FCU_gate")

    def test_fast_sim_motion_and_missing_evidence_are_distinguished(self):
        source = [(i/10, [i/10, 0, 8]) for i in range(13)]
        result = self._run_fixture(source)
        self.assertEqual(result["S_a"]["stop_rate"], 0)
        self.assertAlmostEqual(result["S_b"]["minimum"], 1)
        result = self._run_fixture(source, clock=False)
        self.assertEqual(result["S_a"]["unknown_count"], 1)
        self.assertIsNone(result["S_a"]["stop_rate"])

    def test_gap_in_sim_evidence_prevents_zero_stop_certification(self):
        source = [(i/10, [i/10, 0, 8]) for i in range(13) if i not in (5, 6)]
        result = self._run_fixture(source)
        self.assertEqual(result["S_a"]["stopped_count"], 0)
        self.assertEqual(result["S_a"]["unknown_count"], 1)


if __name__ == "__main__":
    unittest.main()
