"""Read-only diagnostic boundaries: no bridged gaps or inferred mode-send times."""
import unittest
from scripts.diagnose_arrival_brake import entry, slow_spans, position_stage, transition_evidence


class ArrivalBrakeDiagnosticTests(unittest.TestCase):
    def row(self, t, speed=.2, distance=.5):
        return dict(t_s=t, horizontal_speed_m_s=speed, vertical_speed_m_s=0,
                    horizontal_distance_m=distance, distance_3d_m=distance)

    def test_single_sample_does_not_prove_continuous_stop(self):
        self.assertEqual(slow_spans([self.row(0)], 0, 1), [])

    def test_gap_splits_stationary_samples(self):
        self.assertEqual(slow_spans([self.row(0), self.row(.1), self.row(.3), self.row(.4)], 0, 1), [])

    def test_low_speed_threshold_and_minimum_span_are_inclusive(self):
        spans = slow_spans([self.row(0, .3), self.row(.1, .3), self.row(.2, .3)], 0, .2)
        self.assertEqual(len(spans), 1)
        self.assertAlmostEqual(spans[0]["duration_s"], .2)

    def test_entry_bracket_and_left_censor(self):
        rows = [self.row(0, distance=2.1), self.row(.1, distance=1.9)]
        self.assertEqual(entry(rows, 0, 1, 2)["crossing_bracket_s"], [0, .1])
        self.assertTrue(entry(rows, .1, 1, 2)["entry_left_censored"])

    def test_heartbeat_is_bound_not_exact_tx(self):
        events = [dict(event="landing_started", agent_id="a", t=5)]
        heartbeat = [dict(t_s=5.1, custom_mode=9)]
        row = transition_evidence(events, heartbeat, "return", None, "a", 20)
        self.assertFalse(row["exact_SET_MODE_TX_available"])
        self.assertEqual(row["SET_MODE_TX_bound_s"], [5, 5.1])
        self.assertEqual(position_stage(5.05, row), "operation_started_before_mode_heartbeat")
        self.assertEqual(position_stage(5.2, row), "after_LAND_heartbeat_horizontal_only")


if __name__ == "__main__":
    unittest.main()
