"""Offline r1.2 controller acceptance/budget/integrity tests; no SITL."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_v05_r12_validation as validation
from scripts import run_v05_r12_pp as pp
from swarm_sim.generation import file_hash


class R12ValidationTests(unittest.TestCase):
    def control(self):
        return dict(version=validation.VERSION, max_attempts=6, total_sitl_budget=8,
            historical_attempts_consumed=2, max_extra_retries=2,
            planned_cases=list(validation.CASE_ORDER), planned_new_cases=list(validation.NEW_CASE_ORDER),
            stopped_reason=None, completed=False, active_attempt=None, records=[],
            vp1_reassessment={"individual_pass": True})

    def row(self, case, attempt=0, retry=False):
        return dict(case_id=case, attempt_index=attempt, retryable_pre_takeoff=retry,
            individual_pass=not retry, run_status="failed" if retry else "completed",
            flight_epoch_present=not retry)

    def test_fixed_selection_four_flights_and_two_historical_charges(self):
        control = self.control()
        self.assertEqual(validation.CASE_ORDER, ("VP1", "VP2", "VP3", "VR1", "VR2"))
        for case in validation.NEW_CASE_ORDER:
            self.assertEqual(validation.next_case(control), (case, 0))
            control["records"].append(self.row(case))
        self.assertTrue(validation.validation_attempts_clean(control))
        self.assertEqual(len(control["records"]) + control["historical_attempts_consumed"], 6)
        with self.assertRaisesRegex(ValueError, "all four"):
            validation.next_case(control)

    def test_two_proven_preflight_retries_allow_total_eight(self):
        control = self.control()
        for case in ("VP2", "VP3"):
            control["records"].append(self.row(case, retry=True))
            self.assertEqual(validation.next_case(control), (case, 1))
            control["records"].append(self.row(case, 1))
        for case in ("VR1", "VR2"):
            control["records"].append(self.row(case))
        self.assertTrue(validation.validation_attempts_clean(control))
        with self.assertRaisesRegex(ValueError, "eight-attempt"):
            validation.next_case(control)

    def test_third_or_repeated_retry_never_allowed(self):
        control = self.control()
        control["records"] = [self.row("VP2", retry=True), self.row("VP2", 1, True)]
        with self.assertRaisesRegex(ValueError, "one proven"):
            validation.next_case(control)
        control["records"] = [self.row(c, retry=True) if a == 0 else self.row(c, 1)
                              for c in ("VP2", "VP3") for a in (0, 1)]
        control["records"].append(self.row("VR1", retry=True))
        with self.assertRaisesRegex(ValueError, "retry budget"):
            validation.next_case(control)

    def test_failed_gate_missing_reassessment_or_changed_order_blocks(self):
        control = self.control()
        failed = self.row("VP2")
        failed["individual_pass"] = False
        control["records"] = [failed]
        with self.assertRaisesRegex(ValueError, "hard gates"):
            validation.next_case(control)
        control = self.control()
        control["vp1_reassessment"]["individual_pass"] = False
        with self.assertRaisesRegex(ValueError, "VP1"):
            validation.next_case(control)
        control = self.control()
        control["records"] = [self.row("VP3")]
        with self.assertRaisesRegex(ValueError, "frozen order"):
            validation.next_case(control)

    def test_failed_m03_refuses_prepare_without_ledger_or_sitl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "validation"
            report = Path(tmp) / "offline_readiness.json"
            report.write_text(json.dumps(dict(version="v05_r12_offline_readiness_v1",
                route_progress_version=validation.PROGRESS_VERSION,
                gates=dict(M01=True, M02=True, M03=False))), encoding="utf-8")
            before = file_hash(report)
            with (patch.object(validation, "EXPECTED_ROOT", root),
                  patch.object(validation, "OFFLINE_READINESS", report),
                  patch.object(validation, "run_mission_list") as runner):
                with self.assertRaisesRegex(ValueError, "M01/M02/M03"):
                    validation.prepare(root, Path(tmp) / "analysis", "binary", "params", "quality")
                runner.assert_not_called()
            self.assertFalse(root.exists())
            self.assertEqual(file_hash(report), before)

    def test_readiness_evidence_and_current_source_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence, source, report = [root / name for name in ("tests.txt", "ac4.py", "ready.json")]
            evidence.write_text("passed", encoding="utf-8")
            source.write_text("source v2", encoding="utf-8")
            data = dict(version="v05_r12_offline_readiness_v1", route_progress_version=validation.PROGRESS_VERSION,
                gates=dict(M01=True, M02=True, M03=True),
                evidence_sha256={str(evidence): file_hash(evidence)},
                analysis_source_sha256={str(source): file_hash(source)})
            report.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(validation, "OFFLINE_READINESS", report):
                binding = validation.offline_readiness()
                self.assertEqual(len(binding["evidence_sha256"]), 3)
                source.write_text("source altered", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "changed"):
                    validation.offline_readiness()

    def test_history_preserves_original_fail_and_charges_two(self):
        history = validation.bind_history()
        self.assertEqual(history["sitl_attempts_consumed"], 2)
        self.assertEqual(history["v05c"]["original_r1_disposition"], "FAIL")
        self.assertFalse(history["v05c"]["source_record"]["individual_pass"])
        self.assertEqual(history["v05c"]["source_record"]["case_id"], "VP1")
        validation.assert_historical_binding({"history": history})


class R12PilotTests(unittest.TestCase):
    def control(self, rows=None):
        return dict(version=pp.VERSION, max_attempts=22, max_extra_retries=2,
            records=rows or [], completed=False, stopped_reason=None, active_attempt=None)

    def test_soft_flags_never_reduce_pilot_quality_or_acceptance(self):
        flags = [dict(code=code, status="unknown") for code in ("AV-1", "AV-2", "AC4", "AV-8")]
        artifacts = {"quality": {"episode_quality_eligible": True},
                     "labels": {"mission_success": True, "mission_success_observation": True,
                                "semantic_consistency": "agree"}}
        assessment = dict(hard_failures=[], soft_flags=flags, individual_pass=True)
        with patch.object(pp, "assess_artifacts", return_value=assessment):
            result = pp.assess_run({}, {"status": "completed"}, artifacts, {})
        self.assertTrue(result["qualified"])
        self.assertTrue(result["accepted_for_pp"])
        self.assertEqual(result["soft_flags"], flags)
        self.assertEqual(result["hard_failures"], [])

    def test_unknown_analysis_is_hard_failure(self):
        result = pp.assess_run({}, {"status": "completed"}, None, {})
        self.assertFalse(result["qualified"])
        self.assertTrue(result["hard_failures"])

    def test_acceptance_only_uses_r1_11_3_quality_not_strict_timing(self):
        aggregate = dict(logical_completed=20, qualified=18, pair_qualified=9,
            accepted_for_pp=0, pair_accepted_for_pp=0,
            by_intent={intent: {"success_fraction_given_quality": .9} for intent in pp.INTENT_ORDER})
        gates = pp.pilot_acceptance_gates(aggregate, {"episodes": [{}] * 20}, {"issues": []},
            {"consistency_pass": True}, [{"corner_count": 4, "corner_dimensions": [2] * 4}] * 20)
        self.assertTrue(gates["pass"])
        self.assertFalse(any("strict" in key or "timing" in key for key in gates))
        aggregate["qualified"] = 17
        self.assertFalse(pp.pilot_acceptance_gates(aggregate, {"episodes": [{}] * 20}, {"issues": []},
            {"consistency_pass": True}, [{"corner_count": 4, "corner_dimensions": [2] * 4}] * 20)["pass"])

    def test_pilot_retry_order_and_hard_failure(self):
        control = self.control()
        self.assertEqual(pp.next_mission(control), (0, 0))
        control["records"].append(dict(logical_index=0, attempt_index=0, retryable_pre_takeoff=True,
                                       hard_failures=[]))
        self.assertEqual(pp.next_mission(control), (0, 1))
        control["records"].append(dict(logical_index=0, attempt_index=1, retryable_pre_takeoff=False,
                                       hard_failures=[]))
        self.assertEqual(pp.next_mission(control), (1, 0))
        control["records"][-1]["hard_failures"] = ["parameter mismatch"]
        with self.assertRaisesRegex(ValueError, "hard gate"):
            pp.next_mission(control)

    def test_frozen_firmware_mismatch_remains_hard(self):
        artifacts = {key: {} for key in validation.ARTIFACTS}
        assessment = dict(hard_checks={}, hard_failures=[], individual_pass=True)
        with patch.object(validation, "assess_run", return_value=assessment):
            result = validation.assess_artifacts({}, {"binary_firmware": {"sha256": "different"}},
                artifacts, {"firmware": {"sha256": "frozen", "version_string": "v1"},
                            "parameters_sha256": "params", "stage": "pilot"})
        self.assertFalse(result["individual_pass"])
        self.assertIn("frozen_firmware_and_parameters", result["hard_failures"])

    def test_original_v05c_profile_remains_fixed_zero_hold_zero(self):
        profile = pp.normalize_profile(pp.DR_PROFILE)
        self.assertEqual(profile["scene_sampler"]["params"]["heading_policy"], "fixed_zero")
        self.assertTrue(all(m["template_spec"]["execution"]["terminal_hold_s"] == 0 for m in profile["missions"]))

    def test_missing_or_invalid_cleanup_remains_hard_infrastructure_stop(self):
        scene = {"vehicles": [{"id": "uav_01"}, {"id": "uav_02"}]}
        control = {"firmware": {"sha256": "frozen", "version_string": "v1"},
                   "parameters_sha256": "params", "stage": "pilot"}
        metadata = {"binary_firmware": control["firmware"], "parameters_sha256": "params"}
        artifacts = {key: {} for key in validation.ARTIFACTS}
        for cleanup, expected in (({}, False), ({"uav_01": 0}, False),
                ({"uav_01": 0, "uav_02": None}, False),
                ({"uav_01": 0, "uav_02": True}, False),
                ({"uav_01": 0, "uav_02": 0}, True)):
            with self.subTest(cleanup=cleanup):
                metadata["cleanup"] = cleanup
                assessment = dict(hard_checks={}, hard_failures=[], individual_pass=True)
                with patch.object(validation, "assess_run", return_value=assessment):
                    result = validation.assess_artifacts(scene, metadata, artifacts, control)
                self.assertEqual(result["individual_pass"], expected)
                self.assertEqual(result["hard_checks"]["infrastructure_cleanup_complete"], expected)


if __name__ == "__main__":
    unittest.main()
