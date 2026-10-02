"""Offline v05c budget and historical-failure binding; never starts SITL."""

import copy
import json
import unittest
from pathlib import Path

from scripts.run_v05c_validation import (
    CASE_ORDER, EXPECTED_BUNDLE, EXPECTED_PROFILE, EXPECTED_REVIEW,
    HISTORY_CONTROL, MAX_ATTEMPTS, MAX_EXTRA_RETRIES, TOTAL_SITL_BUDGET,
    VERSION, _bound_inputs, assert_historical_binding,
    bind_failed_v05b_attempt, next_case, preflight_retry_reason,
)


class V05cValidationControllerTests(unittest.TestCase):
    def control(self):
        return dict(version=VERSION, max_attempts=MAX_ATTEMPTS,
                    total_sitl_budget=TOTAL_SITL_BUDGET,
                    historical_attempts_consumed=1,
                    max_extra_retries=MAX_EXTRA_RETRIES,
                    stopped_reason=None, completed=False,
                    active_attempt=None, records=[], aggregate_av1={})

    def test_history_is_one_real_nonretryable_attempt_and_hash_bound(self):
        history = bind_failed_v05b_attempt()
        self.assertEqual(history["source_control"], str(HISTORY_CONTROL.resolve()))
        self.assertEqual(history["sitl_attempts_consumed"], 1)
        self.assertIs(history["retryable"], False)
        self.assertIs(history["flight_epoch_present"], False)
        self.assertEqual(history["source_record"]["case_id"], "VP1")
        self.assertGreaterEqual(len(history["source_evidence_sha256"]), 7)
        control = self.control()
        control["historical_failed_attempt"] = history
        assert_historical_binding(control)
        corrupted = copy.deepcopy(control)
        corrupted["historical_failed_attempt"]["source_evidence_sha256"][
            str(HISTORY_CONTROL.resolve())] = "0" * 64
        with self.assertRaisesRegex(ValueError, "frozen validation input/evidence changed"):
            assert_historical_binding(corrupted)
        corrupted = copy.deepcopy(control)
        corrupted["historical_failed_attempt"]["retryable"] = True
        with self.assertRaisesRegex(ValueError, "not charged"):
            assert_historical_binding(corrupted)

    def test_historical_parameter_difference_cannot_be_retried(self):
        ledger = json.loads(HISTORY_CONTROL.read_text(encoding="utf-8"))
        run = Path(ledger["records"][0]["run_directory"])
        metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
        parameters = json.loads((run / "firmware_parameters.json").read_text(encoding="utf-8"))
        events = [json.loads(line) for line in (run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertIsNone(preflight_retry_reason(metadata, parameters, events))

    def test_budget_is_eight_total_seven_new_one_possible_retry(self):
        self.assertEqual(TOTAL_SITL_BUDGET, 8)
        self.assertEqual(MAX_ATTEMPTS, 7)
        self.assertEqual(MAX_EXTRA_RETRIES, 1)
        control = self.control()
        self.assertEqual(next_case(control), ("VP1", 0))
        control["records"].append(dict(case_id="VP1", retryable_pre_takeoff=True,
                                       individual_pass=False))
        self.assertEqual(next_case(control), ("VP1", 1))
        control["records"].append(dict(case_id="VP1", retryable_pre_takeoff=False,
                                       individual_pass=True))
        self.assertEqual(next_case(control), ("VP2", 0))
        control["active_attempt"] = {"case_id": "VP2"}
        with self.assertRaisesRegex(ValueError, "manual audit"):
            next_case(control)
        control["active_attempt"] = None
        for case in CASE_ORDER[1:]:
            control["records"].append(dict(case_id=case,
                                           retryable_pre_takeoff=False,
                                           individual_pass=True))
            if case == "VP4":
                control["aggregate_av1"]["patrol"] = {"pass": True}
            if case != "VR2":
                self.assertEqual(next_case(control), (CASE_ORDER[CASE_ORDER.index(case) + 1], 0))
        self.assertEqual(len(control["records"]), 7)
        with self.assertRaisesRegex(ValueError, "eight-attempt total SITL budget"):
            next_case(control)

    def test_invalid_budget_and_previous_failure_fail_closed(self):
        control = self.control()
        control["total_sitl_budget"] = 9
        with self.assertRaisesRegex(ValueError, "version/budget"):
            next_case(control)
        control = self.control()
        control["records"].append(dict(case_id="VP1", retryable_pre_takeoff=False,
                                       individual_pass=False))
        with self.assertRaisesRegex(ValueError, "previous validation case failed"):
            next_case(control)

    def test_old_v05b_bundle_is_not_accepted_as_v05c_input(self):
        with self.assertRaisesRegex(ValueError, "new formal bundle"):
            _bound_inputs(EXPECTED_BUNDLE.parent / "old_v05b_bundle",
                          EXPECTED_REVIEW, EXPECTED_PROFILE)


if __name__ == "__main__":
    unittest.main()
