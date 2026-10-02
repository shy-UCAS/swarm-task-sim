"""Authorization and failure policy checks; never launch SITL."""
import copy
import unittest
from scripts.run_v06_pilot import VERSION, assess, continuation


class V06PolicyTests(unittest.TestCase):
    def setUp(self):
        self.control = dict(version=VERSION, budget=10, records=[], active_attempt=None)
        self.metadata = dict(status="completed", scenario=dict(vehicles=[dict(id="uav_01")]),
            cleanup=dict(uav_01=0), run_provenance=dict(status="verified_before_takeoff",
            parameter_comparison_version="wp_s_parameter_comparison_v2", parameter_evidence=dict(per_agent=dict(
                uav_01=dict(complete=True, parameter_count=1202, received_count=1202, missing_indices=[])))))
        self.quality = dict(episode_quality_eligible=True, mission_success=False, benchmark_eligible=False)
        self.attempt = dict(status="semantic_failed", selected_analysis={"directory": "analysis"})

    def test_quality_eligible_mission_failure_is_qualified(self):
        result = assess(self.metadata, self.quality, self.attempt)
        self.assertTrue(result["qualified"])
        self.assertEqual(result["hard_failures"], [])

    def test_ordinary_quality_failure_can_continue(self):
        self.quality["episode_quality_eligible"] = False
        result = assess(self.metadata, self.quality, self.attempt)
        self.assertFalse(result["qualified"])
        self.assertEqual(result["hard_failures"], [])
        self.control["records"] = [dict(qualified=False)] * 2
        continuation(self.control, 2)

    def test_third_failure_stops(self):
        self.control["records"] = [dict(qualified=False)] * 3
        with self.assertRaisesRegex(ValueError, "no longer attainable"):
            continuation(self.control, 3)

    def test_total_budget_counts_all_attempts(self):
        self.control["records"] = [dict(qualified=True)] * 10
        with self.assertRaisesRegex(ValueError, "budget exhausted"):
            continuation(self.control, 10)

    def test_crash_reservation_cannot_retry(self):
        self.control["active_attempt"] = dict(index=0)
        with self.assertRaisesRegex(ValueError, "unfinished reserved"):
            continuation(self.control, 0)

    def test_provenance_partial_cleanup_and_missing_evidence_stop(self):
        for mutate, expected in (
            (lambda m, a: m["run_provenance"].update(status="failed"), "provenance gate"),
            (lambda m, a: m["cleanup"].update(uav_01=None), "cleanup incomplete"),
            (lambda m, a: a.pop("selected_analysis"), "evidence incomplete"),
            (lambda m, a: m["run_provenance"]["parameter_evidence"]["per_agent"]["uav_01"].update(received_count=1105), "partial parameter"),
        ):
            with self.subTest(expected=expected):
                metadata, attempt = copy.deepcopy(self.metadata), copy.deepcopy(self.attempt)
                mutate(metadata, attempt)
                self.assertTrue(any(expected in s for s in assess(metadata, self.quality, attempt)["hard_failures"]))

    def test_frozen_stop_and_ledger_disagreement(self):
        with self.assertRaisesRegex(ValueError, "mismatch"):
            continuation(self.control, 1)
        self.control["stopped_reason"] = "integrity"
        with self.assertRaisesRegex(ValueError, "stopped"):
            continuation(self.control, 0)


if __name__ == "__main__":
    unittest.main()
