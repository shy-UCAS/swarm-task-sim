"""r1.2 policy tests use immutable VP1 evidence; no SITL or file writes."""
import copy
import json
import unittest
from pathlib import Path

from swarm_sim.validation_policy import assess_run

ROOT = Path(__file__).resolve().parents[1]


class R12PolicyTests(unittest.TestCase):
    def setUp(self):
        read = lambda path: json.loads(path.read_text(encoding="utf-8"))
        control = read(ROOT / "verification/v05c_validation_20261002/control.json")
        run = Path(control["records"][0]["run_directory"])
        self.metadata = read(run / "metadata.json")
        self.scene = self.metadata["scenario"]
        analysis = run / read(run / "analysis_latest.json")["directory"]
        self.artifacts = {key: read(analysis / (name + ".json")) for key, name in (
            ("quality", "quality"), ("labels", "labels"), ("metrics", "execution_metrics"),
            ("ac4", "ac4_timing_v3"), ("onboard", "onboard_mission_param_check"))}

    def assess(self, stage="validation"):
        return assess_run(self.scene, self.metadata, **self.artifacts, stage=stage)

    def test_original_vp1_unknown_laps_and_timing_are_soft_without_quality_mutation(self):
        before = copy.deepcopy(self.artifacts)
        result = self.assess()
        self.assertTrue(result["individual_pass"], result["hard_failures"])
        self.assertEqual({f["code"] for f in result["soft_flags"]}, {"AV-1", "AV-2", "AC4", "AV-8"})
        self.assertTrue(result["episode_quality_eligible"])
        self.assertEqual(self.artifacts, before)

    def test_complete_proof_of_wrong_laps_stops_every_stage(self):
        for channel in ("truth", "observation"):
            self.artifacts["labels"]["mission_metrics"][channel]["per_agent_laps_observed"]["uav_01"] = 1
        for stage in ("validation", "pilot", "batch"):
            self.assertIn("known_patrol_laps_match", self.assess(stage)["hard_failures"])

    def test_incomplete_numeric_lap_claim_cannot_be_accepted(self):
        self.artifacts["labels"]["mission_metrics"]["truth"]["per_agent_laps_observed"]["uav_03"] = 2
        self.assertIn("patrol_lap_evidence_consistent", self.assess()["hard_failures"])

    def test_parameter_or_onboard_or_separation_failure_stops(self):
        self.metadata["run_provenance"]["status"] = "failed"
        self.artifacts["onboard"]["status"] = "mismatch"
        self.artifacts["quality"]["truth_separation"]["minimum_m"] = 4.99
        result = self.assess()
        self.assertTrue({"parameter_firmware", "onboard_mission_parameters", "truth_separation"}
                        <= set(result["hard_failures"]))

    def test_known_task_failure_retained_in_pilot_but_stops_validation(self):
        self.artifacts["labels"].update(mission_success=False, mission_success_observation=False)
        self.assertIn("dual_channel_mission_success", self.assess()["hard_failures"])
        self.assertTrue(self.assess("pilot")["individual_pass"])
        self.artifacts["labels"]["semantic_consistency"] = "disagree"
        self.assertIn("known_consistent_labels", self.assess("pilot")["hard_failures"])

    def test_zero_length_route_stops(self):
        phase = self.scene["phases"][0]
        agent = self.scene["vehicles"][0]["id"]
        phase["routes"][agent].insert(0, copy.deepcopy(
            self.scene["semantic_plan"]["execution_phases"][phase["name"]]["agents"][agent]["start_point"]))
        self.assertIn("no_zero_length_segments", self.assess()["hard_failures"])


if __name__ == "__main__":
    unittest.main()
