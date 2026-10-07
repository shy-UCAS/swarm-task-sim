"""r1.2b: version isolation, explicit semantic records and rolling run counts."""

import copy
import tempfile
import unittest
from pathlib import Path

from swarm_sim.analysis_v3 import analyze_run_v3
from swarm_sim.episode_loader import load_episode
from swarm_sim.validation_policy_r12b import VERSION, assess_recent_runs, assess_run
import test_validation_policy_r12 as historical
from test_wp_p_protocol import _analyzed_failed_run


class R12bPolicyTests(unittest.TestCase):
    def setUp(self):
        historical.R12PolicyTests.setUp(self)

    def assess(self):
        return assess_run(self.scene, self.metadata, **self.artifacts, stage="pilot")

    def test_soft_flags_keep_original_values_and_quality_is_untouched(self):
        original = copy.deepcopy(self.artifacts)
        old = historical.R12PolicyTests.assess(self, stage="pilot")
        result = self.assess()
        self.assertTrue(result["individual_pass"])
        self.assertEqual(result["soft_flags"], old["soft_flags"])
        self.assertEqual(self.artifacts, original)

    def test_semantic_failure_disagreement_quality_and_geometry_do_not_individually_stop(self):
        self.artifacts["labels"].update(mission_success=False, mission_success_observation=False,
                                       semantic_consistency="disagree")
        self.artifacts["quality"]["episode_quality_eligible"] = False
        self.artifacts["labels"]["mission_metrics"]["truth"]["per_agent_laps_observed"]["uav_01"] = 1
        phase = self.scene["phases"][0]
        phase["routes"]["uav_01"].insert(0, copy.deepcopy(
            self.scene["semantic_plan"]["execution_phases"][phase["name"]]["agents"]["uav_01"]["start_point"]))
        result = self.assess()
        self.assertTrue(result["individual_pass"], result["hard_failures"])
        self.assertTrue(result["aggregate_anomaly"])
        self.assertEqual(set(result["aggregate_anomaly_reasons"]),
                         {"task_failure_truth", "task_failure_observation", "label_disagreement", "episode_quality_ineligible"})
        self.assertIn("patrol_laps_mismatch", {r["code"] for r in result["semantic_flags"]})
        self.assertIn("zero_length_segments", {r["code"] for r in result["new_anomalies"]})

    def test_unknown_outcomes_are_recorded_without_inventing_failures(self):
        self.artifacts["labels"].update(mission_success=None, mission_success_observation=None,
                                       semantic_consistency="unknown")
        self.artifacts["quality"].update(episode_quality_eligible=None,
                                         truth_separation={"status": "unknown", "minimum_m": None})
        result = self.assess()
        self.assertTrue(result["individual_pass"])
        self.assertFalse(result["aggregate_anomaly"])
        self.assertEqual(result["aggregate_anomaly_reasons"], [])
        self.assertTrue({"truth_separation_unknown", "task_result_unknown", "label_consistency_unknown",
                         "episode_quality_unknown"} <= {r["code"] for r in result["new_anomalies"]})

    def test_parameter_onboard_and_known_spacing_failures_still_stop(self):
        self.metadata["run_provenance"]["status"] = "failed"
        self.artifacts["onboard"]["status"] = "mismatch"
        self.artifacts["quality"]["truth_separation"]["minimum_m"] = 4.99
        self.assertEqual(set(self.assess()["hard_failures"]),
                         {"parameter_firmware", "onboard_mission_parameters", "truth_separation"})

    def test_new_policy_analysis_requires_new_semantic_version_and_loads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run, _ = _analyzed_failed_run(root / "fixture", v05=True)
            with self.assertRaisesRegex(ValueError, "perimeter_revisit_v2"):
                analyze_run_v3(run, progress_mapping_version="ordered_route_progress_v2",
                               acceptance_policy=VERSION, acceptance_stage="pilot")
            output, quality, _ = analyze_run_v3(run, progress_mapping_version="ordered_route_progress_v2",
                patrol_validator_version="perimeter_revisit_v2", acceptance_policy=VERSION,
                acceptance_stage="pilot", output_directory=root / "external", update_latest=False)
            self.assertEqual(quality["validation_policy"]["version"], VERSION)
            self.assertEqual(load_episode(output)["metadata"]["semantic_validation_version"], "multi_intent_validation_v3")


def _row(run_id, reasons=(), stage="pilot"):
    return dict(run_id=run_id, stage=stage, assessment=dict(version=VERSION, stage=stage,
        aggregate_anomaly=bool(reasons), aggregate_anomaly_reasons=list(reasons)))


class R12bRollingTests(unittest.TestCase):
    def test_four_allowed_fifth_stops_before_full_window(self):
        records = [_row(str(i), ["task_failure_truth"]) for i in range(4)]
        self.assertFalse(assess_recent_runs(records)["stop"])
        records.append(_row("4", ["episode_quality_ineligible"]))
        result = assess_recent_runs(records)
        self.assertTrue(result["stop"])
        self.assertEqual((result["anomaly_count"], result["window_count"]), (5, 5))

    def test_multiple_reasons_and_duplicate_run_count_once(self):
        rows = [_row("a", ["task_failure_truth", "label_disagreement"]),
                _row("a", ["episode_quality_ineligible"]), _row("b")]
        result = assess_recent_runs(rows)
        self.assertEqual((result["anomaly_count"], result["window_count"]), (1, 2))
        self.assertEqual(len(result["runs"][0]["reasons"]), 3)

    def test_window_eviction_and_independent_batch_reset(self):
        rows = [_row(str(i), ["task_failure_truth"] if i < 5 else []) for i in range(22)]
        result = assess_recent_runs(rows)
        self.assertEqual((result["anomaly_count"], result["window_count"]), (3, 20))
        self.assertFalse(result["stop"])
        self.assertEqual(assess_recent_runs(rows, stage="batch")["window_count"], 0)
        rows.append(_row("batch_1", ["label_disagreement"], stage="batch"))
        self.assertEqual(assess_recent_runs(rows, stage="batch")["anomaly_count"], 1)


if __name__ == "__main__":
    unittest.main()
