"""Source-second clock and episode gates, using synthetic evidence only."""
import copy
import unittest

from swarm_sim import parallel_batch as batch
from swarm_sim.parallel_worker import assess_artifacts
from swarm_sim.quality import clock_grade, episode_quality_eligibility, resolve_policy, summarize_clocks, v3_eligibility
from swarm_sim.run_provenance import PARAMETER_COMPARISON_VERSION, compare_parameter_readback
from test_parameter_comparison_v2 import fixture as parameter_fixture, STARTED
from swarm_sim.truth import fit_clock
from swarm_sim.validation_policy import frozen_identity_check, parameter_firmware_check
from swarm_sim.validation_policy_r12b import assess_run


def evidence(minimum=7.0):
    scene = dict(vehicles=[dict(id="uav_01"), dict(id="uav_02")], min_separation_m=5.0,
                 task_spec=dict(execution=dict(protocol_version="v0.6.1", sim_speedup=1)))
    metadata = dict(status="completed", cleanup=dict(uav_01=0, uav_02=0),
        parameter_comparison_version=PARAMETER_COMPARISON_VERSION,
        binary_firmware=dict(sha256="firmware", version_string="ArduCopter V4.5.7"), parameters_sha256="params",
        run_provenance=dict(status="verified_before_takeoff", parameter_comparison_version=PARAMETER_COMPARISON_VERSION,
            parameter_evidence=dict(per_agent={agent: dict(complete=True, status="complete", received_count=2,
                parameter_count=2, missing_indices=[], parameter_comparison=dict(status="evaluated", collection_complete=True, **{"pass": True}))
                for agent in ("uav_01", "uav_02")})))
    quality = dict(time_base="sim_source", parameter_firmware_check=True,
        run_completed=True, data_quality_pass=True, truth_available_pass=True,
        timing_diagnostic_pass=True, execution_constraints_pass=True, clock_quality=dict(overall="acceptable"),
        separation_status="clear_observed" if minimum >= 2 else "risk",
        truth_separation=dict(minimum_m=minimum, status="clear_observed" if minimum >= 2 else "risk"))
    quality["episode_quality_eligible"] = episode_quality_eligibility(quality)
    artifacts = dict(quality=quality, labels=dict(mission_success=True, mission_success_observation=True,
        semantic_consistency="agree"), execution_metrics={}, ac4_timing_v3={},
        onboard_mission_param_check=dict(status="pass", pass_gate=True))
    plan = dict(firmware=metadata["binary_firmware"], parameters_sha256="params")
    return scene, metadata, artifacts, plan


def assess(scene, metadata, artifacts, plan):
    artifacts["quality"]["parameter_firmware_check"] = parameter_firmware_check(scene, metadata)
    artifacts["quality"]["episode_quality_eligible"] = episode_quality_eligibility(artifacts["quality"])
    artifacts["quality"]["validation_policy"] = assess_run(scene, metadata, artifacts["quality"], artifacts["labels"],
        artifacts["execution_metrics"], artifacts["ac4_timing_v3"], artifacts["onboard_mission_param_check"], stage="batch")
    return assess_artifacts(scene, metadata, artifacts, plan)


class SourceClockGates(unittest.TestCase):
    def test_residual_threshold_in_simulation_seconds_at_1_2_4(self):
        policy = resolve_policy()
        for speed in (1, 2, 4):
            scene = dict(execution=dict(protocol_version="v0.6.1", sim_speedup=speed))
            for residual, expected in ((0.02, "strict"), (0.15, "acceptable"), (0.2, "acceptable"), (0.2001, "failed")):
                model = dict(available=True, receive_residual_abs_p95_s=residual/speed)
                self.assertEqual(clock_grade(model, policy, scene), expected)
            summary = summarize_clocks({"uav_01": dict(available=True, receive_residual_abs_p95_s=.1/speed)}, policy, scene)
            self.assertTrue(summary["strict_is_diagnostic_only"])
            self.assertEqual(summary["per_agent_residual_sim_s"]["uav_01"], .1)
            self.assertEqual(clock_grade(dict(available=False, receive_residual_abs_p95_s=0), policy, scene), "unknown")
        self.assertEqual(clock_grade(dict(available=True, receive_residual_abs_p95_s=.1), policy), "failed")

    def test_clock_rate_window_scales_but_insufficient_evidence_stays_invalid(self):
        for speed in (1, 2, 4):
            for factor, available in ((.6, True), (1.8, True), (.4, False), (2.1, False)):
                pairs = [(i/10, factor*i/10/speed) for i in range(500)]
                model = fit_clock(pairs, sim_speedup=speed, source_time_contract=True)
                self.assertIs(model["available"], available, (speed, factor, model))
            self.assertFalse(fit_clock([(0, 0), (1, 1/speed)], sim_speedup=speed, source_time_contract=True)["available"])


class ThreeValueAndSeparationGates(unittest.TestCase):
    def test_missing_parameter_proof_cannot_qualify_even_when_run_says_completed(self):
        scene, metadata, artifacts, plan = evidence()
        metadata["run_provenance"]["parameter_evidence"]["per_agent"] = {}
        result = assess(scene, metadata, artifacts, plan)
        self.assertFalse(result["qualified"])
        self.assertEqual(result["hard_failures"], [])
        self.assertTrue(all(value is False for value in v3_eligibility(artifacts["quality"], artifacts["labels"]).values()))

    def test_empty_partial_failed_readback_is_unknown_but_complete_pass_succeeds(self):
        scene, metadata, artifacts, plan = evidence()
        self.assertTrue(parameter_firmware_check(scene, metadata))
        for row in ({}, dict(complete=False, status="failed", received_count=0, parameter_count=None),
                    dict(complete=False, status="failed", received_count=0, parameter_count=None,
                         firmware=None, parameter_comparison=None),
                    dict(complete=False, status="reading", received_count=1, parameter_count=2, missing_indices=[1])):
            trial = copy.deepcopy(metadata)
            trial.update(status="failed")
            trial["run_provenance"]["status"] = "failed"
            trial["run_provenance"]["parameter_evidence"]["per_agent"]["uav_01"] = row
            artifacts["quality"].update(run_completed=False, episode_quality_eligible=False)
            result = assess(scene, trial, artifacts, plan)
            self.assertIsNone(result["batch_hard_checks"]["parameter_firmware"])
            self.assertFalse(result["qualified"])
            self.assertEqual(result["hard_failures"], [])
            self.assertTrue(result["assessment"]["aggregate_anomaly"])

    def test_confirmed_full_mismatch_survives_missing_other_aircraft_and_stops(self):
        scene, metadata, artifacts, plan = evidence()
        rows = metadata["run_provenance"]["parameter_evidence"]["per_agent"]
        rows["uav_01"]["parameter_comparison"]["pass"] = False
        rows["uav_02"] = dict(complete=False, status="failed", received_count=0)
        metadata["run_provenance"]["status"] = "failed"
        result = assess(scene, metadata, artifacts, plan)
        self.assertIn("parameter_firmware", result["hard_failures"])
        state = batch.new_state({})
        attempt = dict(attempt_id="a000000")
        state["attempts"].append(attempt)
        batch.register_completion(state, attempt, dict(result, run_id="confirmed_mismatch"))
        self.assertIn("confirmed violation", state["stopped_reason"])

    def test_confirmed_firmware_mismatch_and_missing_frozen_identity(self):
        scene, metadata, _, plan = evidence()
        metadata["run_provenance"]["parameter_evidence"]["per_agent"]["uav_01"] = dict(
            complete=False, firmware=dict(confirmed_mismatch=True))
        self.assertIs(parameter_firmware_check(scene, metadata), False)
        missing = copy.deepcopy(metadata)
        missing.pop("binary_firmware")
        self.assertIsNone(frozen_identity_check(missing, plan))
        missing["parameters_sha256"] = "confirmed_conflict"
        self.assertIs(frozen_identity_check(missing, plan), False)

    def test_complete_changed_parameter_names_reach_confirmed_batch_stop(self):
        for change in ("added", "removed", "renamed"):
            row, baseline = parameter_fixture()
            baseline["baselines"][0]["agents"]["uav_01"]["all_parameters"]["SIM_SPEEDUP"] = 1.0
            actual = row["all_parameters"]
            actual["SIM_SPEEDUP"] = 1.0
            if change in ("removed", "renamed"):
                actual.pop("WPNAV_ACCEL")
            if change in ("added", "renamed"):
                actual["UNEXPECTED_PARAMETER"] = 100.0
            row.update(parameter_count=len(actual), received_count=len(actual))
            with self.assertRaises(ValueError):
                compare_parameter_readback(row, baseline, 1, run_started_utc=STARTED, expected_sim_speedup=1)
            scene, metadata, artifacts, plan = evidence()
            metadata["run_provenance"]["parameter_evidence"]["per_agent"]["uav_01"] = row
            metadata["run_provenance"]["status"] = "failed"
            result = assess(scene, metadata, artifacts, plan)
            self.assertIn("parameter_firmware", result["hard_failures"], change)

    def test_null_identity_or_provenance_stays_unknown_in_full_assessment(self):
        for field in ("binary_firmware", "run_provenance"):
            scene, metadata, artifacts, plan = evidence()
            metadata[field] = None
            result = assess(scene, metadata, artifacts, plan)
            self.assertIsNone(result["batch_hard_checks"]["parameter_firmware"])
            if field == "binary_firmware":
                self.assertIsNone(result["batch_hard_checks"]["frozen_firmware_and_parameters"])
            self.assertFalse(result["qualified"])
            self.assertEqual(result["hard_failures"], [])
            self.assertIsNone(result["infrastructure_error"])

    def test_under_2m_excluded_and_rolling_pause_not_batch_stop(self):
        state = batch.new_state({})
        for i in range(5):
            scene, metadata, artifacts, plan = evidence(1.99)
            result = assess(scene, metadata, artifacts, plan)
            self.assertFalse(result["qualified"])
            self.assertNotIn("truth_separation", result["hard_failures"])
            attempt = dict(attempt_id=f"a{i:06d}")
            state["attempts"].append(attempt)
            batch.register_completion(state, attempt, dict(result, run_id=f"close_{i}"))
            self.assertIsNone(state["stopped_reason"])
        self.assertEqual(state["rolling"]["anomaly_count"], 5)
        self.assertEqual(state["pause_kind"], "rule")

    def test_2m_through_5m_remains_qualified_with_minimum_diagnostic(self):
        for minimum in (2.0, 3.5, 4.999, 5.0):
            scene, metadata, artifacts, plan = evidence(minimum)
            result = assess(scene, metadata, artifacts, plan)
            self.assertTrue(result["qualified"])
            self.assertEqual(result["hard_failures"], [])
            self.assertFalse(result["assessment"]["aggregate_anomaly"])
            self.assertEqual(artifacts["quality"]["truth_separation"]["minimum_m"], minimum)


if __name__ == "__main__":
    unittest.main()
