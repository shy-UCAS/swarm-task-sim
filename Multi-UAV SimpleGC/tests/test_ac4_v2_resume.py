"""AC4 v2 adoption, immutable predecessors and four-attempt budget contracts.

Every simulator call is mocked; temporary ledgers are the only mutated evidence.
"""
import copy
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from scripts import run_v04_ac4_v2 as runner


class AC4ResumeTests(unittest.TestCase):
    @staticmethod
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")

    @staticmethod
    def row(name, repeat=1, expected=None):
        return dict(validation_id=name, repeat=repeat, run_id=f"{name}_{repeat}",
                    run_status="completed", exit_code=0, cleanup={"complete": True},
                    evidence_integrity_pass=True, issues=[], expected_failure=expected,
                    acceptance_criteria_applicable=name in ("V02", "V03", "V04"),
                    criteria={f"AC{i}": True for i in range(1, 7)})

    @staticmethod
    def review(rows):
        return dict(source_files_unchanged=True, records=rows, issues=[],
                    ac1_pooled={"matrix_complete": False}, observed_route_criteria={"AC1": True})

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.old = self.directory / "old"
        failed = self.old / "failed"
        self.save(failed / "metadata.json", dict(status="failed", run_id="old_failed_v01"))
        self.save(failed / "quality.json", dict(usable=False))
        self.history = self.old / "oldest_records.json"
        self.save(self.history, dict(attempts_started=1, new_sitl_runs=1,
            records=[dict(validation_id="V01", repeat=1, state="finished", run_status="failed",
                          run_id="old_failed_v01", exit_code=1, run_directory=str(failed),
                          metadata_sha256=runner.digest(failed / "metadata.json"),
                          quality_sha256=runner.digest(failed / "quality.json"))],
            stopped_reason="parameter comparison v1 STAT_RESET"))
        jobs = []
        for key in ["V01_r1", "V02_r1", *runner.KEYS]:
            name, repeat = key.split("_r")
            task, scene = self.old / (key + ".task.json"), self.old / (key + ".scene.json")
            self.save(task, {})
            self.save(scene, {})
            jobs.append(dict(key=key, validation_id=name, repeat=int(repeat), task=str(task), scene=str(scene),
                             task_sha256=runner.digest(task), scene_sha256=runner.digest(scene)))
        self.prior = self.old / "records.json"
        old_records = []
        for job in jobs[:2]:
            run = self.old / (job["key"] + "_run")
            self.save(run / "metadata.json", dict(status="completed", run_id=job["key"]))
            self.save(run / "quality.json", dict(usable=True))
            old_records.append(dict(job, state="finished", run_status="completed", exit_code=0,
                run_id=job["key"], run_directory=str(run),
                metadata_sha256=runner.digest(run / "metadata.json"), quality_sha256=runner.digest(run / "quality.json")))
        self.prior_data = dict(budget=7, attempts_started=2, new_sitl_runs=2,
            stopped_reason="V02_r1: AC4=False", historical_evidence=runner.historical_evidence(self.history),
            jobs=jobs, records=old_records)
        self.save(self.prior, self.prior_data)
        self.raw_source = self.old / "raw_source.json"
        self.save(self.raw_source, dict(packet="original"))
        assessment = self.review([self.row("V01"), self.row("V02")])
        assessment.update(acceptance_policy_version=runner.VERSION, input_records_path=str(self.prior),
                          input_sha256={str(self.prior): runner.digest(self.prior), str(self.raw_source): runner.digest(self.raw_source)},
                          wp_s_offline_reviews=[dict(run_id=name, source_files_unchanged=True, input_sha256={})
                              for name in ("20261001T153235Z_5eddb7ae", "20261001T153806Z_42150c31")])
        self.assessment = self.directory / "review.json"
        self.save(self.assessment, assessment)
        self.diagnostics = self.directory / "diagnostics.json"
        self.save(self.diagnostics, dict(inputs_unchanged=True, fallback_windows=[{} for _ in range(11)],
            run_id="V02_r1", fallback_count=dict(truth=7, observation=4), arrival_definition_unchanged=True,
            source_sha256={str(self.raw_source): runner.digest(self.raw_source)}))
        self.gate = self.directory / "gate.json"
        self.save(self.gate, dict(status="PASS"))
        self.originals = {p: p.read_bytes() for p in self.old.rglob("*") if p.is_file()}
        self.root = self.directory / "resume"

    def preserved(self):
        for path, expected in self.originals.items():
            self.assertEqual(path.read_bytes(), expected, str(path))

    def prepare(self):
        with patch.object(runner, "check_offline_gate", return_value={"status": "PASS"}), \
                patch.object(runner, "validate_task_binding"), patch("builtins.print"), \
                patch("swarm_sim.runner.run_scene") as flight:
            runner.prepare(self.root, self.prior, self.assessment, self.gate, self.diagnostics)
            flight.assert_not_called()
        return runner.read(self.root / "records.json")

    def guards(self, stack):
        stack.enter_context(patch.object(runner, "check_offline_gate", return_value={"status": "PASS"}))
        stack.enter_context(patch.object(runner, "validate_task_binding"))
        stack.enter_context(patch("builtins.print"))
        return stack.enter_context(patch("swarm_sim.runner.run_scene"))

    def test_adoption_preserves_original_stop_and_counts_only_three_prior_attempts(self):
        ledger = self.prepare()
        self.assertEqual(ledger["budget"], 7)
        self.assertEqual((ledger["prior_attempts"], ledger["prior_sitl_runs"], ledger["attempts_started"]), (3, 3, 0))
        self.assertEqual([j["key"] for j in ledger["jobs"]], runner.KEYS)
        self.assertEqual([r["key"] for r in ledger["records"]], ["V01_r1", "V02_r1"])
        self.assertEqual(ledger["historical_stopped_reason"], "V02_r1: AC4=False")
        self.assertEqual(ledger["historical_failed_run_ids"], ["old_failed_v01"])
        self.assertNotIn("stopped_reason", ledger)
        self.assertEqual(ledger["acceptance_policy_version"], runner.VERSION)
        self.preserved()

    def test_v2_failed_or_unknown_assessment_cannot_adopt(self):
        original = runner.read(self.assessment)
        for decision in (False, None):
            with self.subTest(decision=decision):
                assessment = copy.deepcopy(original)
                assessment["records"][1]["criteria"]["AC4"] = decision
                self.save(self.assessment, assessment)
                with self.assertRaisesRegex(ValueError, "re-evaluation did not pass"):
                    self.prepare()
                self.assertFalse(self.root.exists())
        self.preserved()

    def test_wrong_predecessor_policy_or_integrity_cannot_adopt(self):
        original = runner.read(self.assessment)
        cases = [dict(acceptance_policy_version="v1"), dict(input_sha256={}),
                 dict(wp_s_offline_reviews=[]), dict(source_files_unchanged=False)]
        for update in cases:
            with self.subTest(update=update):
                self.save(self.assessment, dict(copy.deepcopy(original), **update))
                with self.assertRaises(ValueError):
                    self.prepare()
                self.assertFalse(self.root.exists())
        self.preserved()

    def test_stop_sequence_unfinished_budget_and_authorization_guards_do_not_launch(self):
        original = self.prepare()
        cases = [(dict(stopped_reason="V02_r2: AC4=False"), "V02_r2", "validation stopped"),
                 ({}, "V02_r1", "next authorized"),
                 (dict(attempts_started=4), "V06_r1", "budget exhausted"),
                 (dict(budget=8), "V02_r2", "authorization/budget"),
                 (dict(prior_attempts=2), "V02_r2", "authorization/budget")]
        unfinished = copy.deepcopy(original["records"])
        unfinished[1]["state"] = "started"
        cases.append((dict(records=unfinished), "V02_r2", "unfinished attempt"))
        for update, key, message in cases:
            with self.subTest(key=key, update=update):
                self.save(self.root / "records.json", dict(copy.deepcopy(original), **update))
                with ExitStack() as stack:
                    flight = self.guards(stack)
                    with self.assertRaisesRegex(ValueError, message):
                        runner.run_one(self.root, key)
                    flight.assert_not_called()
        self.preserved()

    def test_supporting_evidence_change_stops_before_flight(self):
        self.prepare()
        self.save(self.diagnostics, dict(inputs_unchanged=True, fallback_windows=[{} for _ in range(11)], changed=True))
        with ExitStack() as stack:
            flight = self.guards(stack)
            with self.assertRaisesRegex(ValueError, "bound evidence changed"):
                runner.run_one(self.root, "V02_r2")
            flight.assert_not_called()
        self.preserved()

    def test_underlying_historical_raw_source_change_stops_before_flight(self):
        self.prepare()
        original = self.raw_source.read_bytes()
        self.save(self.raw_source, dict(packet="edited"))
        with ExitStack() as stack:
            flight = self.guards(stack)
            with self.assertRaisesRegex(ValueError, "bound evidence changed"):
                runner.run_one(self.root, "V02_r2")
            flight.assert_not_called()
        self.raw_source.write_bytes(original)
        self.preserved()

    def test_duplicate_WP_S_identity_and_wrong_diagnostic_run_are_rejected(self):
        assessment = runner.read(self.assessment)
        assessment["wp_s_offline_reviews"][1]["run_id"] = assessment["wp_s_offline_reviews"][0]["run_id"]
        original_assessment = self.assessment.read_bytes()
        self.save(self.assessment, assessment)
        with self.assertRaisesRegex(ValueError, "both read-only WP-S"):
            self.prepare()
        self.assessment.write_bytes(original_assessment)
        diagnostics = runner.read(self.diagnostics)
        diagnostics["run_id"] = "some_other_run"
        self.save(self.diagnostics, diagnostics)
        with self.assertRaisesRegex(ValueError, "arrival/segment offline"):
            self.prepare()
        self.assertFalse(self.root.exists())
        self.preserved()

    def test_unknown_prior_v2_acceptance_records_stop_before_flight(self):
        self.prepare()
        report = self.review([self.row("V01"), self.row("V02")])
        report["records"][1]["criteria"]["AC4"] = None
        with ExitStack() as stack:
            flight = self.guards(stack)
            stack.enter_context(patch.object(runner, "verify_records_v2", return_value=report))
            with self.assertRaisesRegex(ValueError, "AC4=None"):
                runner.run_one(self.root, "V02_r2")
            flight.assert_not_called()
        self.assertIn("AC4=None", runner.read(self.root / "records.json")["stopped_reason"])
        self.preserved()

    def mock_result(self, name, status="completed"):
        directory = self.root / (name + "_run")
        metadata = dict(run_id=name, status=status, sitl={"instances": [{"pid": 100}]})
        quality = dict(usable=status == "completed")
        self.save(directory / "metadata.json", metadata)
        self.save(directory / "quality.json", quality)
        return directory, metadata, quality

    def test_postflight_v2_failure_stops_and_keeps_execution_success(self):
        self.prepare()
        old_rows = [self.row("V01"), self.row("V02")]
        current = self.row("V02", 2)
        current["criteria"]["AC4"] = False
        with ExitStack() as stack:
            flight = self.guards(stack)
            flight.return_value = self.mock_result("new_v02")
            stack.enter_context(patch.object(runner, "verify_records_v2",
                side_effect=[self.review(old_rows), self.review(old_rows + [current])]))
            self.assertEqual(runner.run_one(self.root, "V02_r2"), 1)
            flight.assert_called_once()
        ledger = runner.read(self.root / "records.json")
        self.assertIn("AC4=False", ledger["stopped_reason"])
        self.assertEqual(ledger["attempts_started"] + ledger["prior_attempts"], 4)
        self.assertEqual(ledger["records"][-1]["run_status"], "completed")
        self.assertEqual(ledger["records"][-1]["exit_code"], 0)
        self.assertFalse(ledger["records"][-1]["acceptance_record"]["passed"])
        self.preserved()

    def test_interruption_consumes_attempt_and_forbids_silent_retry(self):
        self.prepare()
        with ExitStack() as stack:
            flight = self.guards(stack)
            flight.side_effect = RuntimeError("mock interruption")
            stack.enter_context(patch.object(runner, "verify_records_v2",
                                             return_value=self.review([self.row("V01"), self.row("V02")])))
            with self.assertRaisesRegex(RuntimeError, "mock interruption"):
                runner.run_one(self.root, "V02_r2")
        ledger = runner.read(self.root / "records.json")
        self.assertEqual(ledger["attempts_started"], 1)
        self.assertEqual(ledger["records"][-1]["state"], "interrupted_without_final_result")
        self.assertIn("budget consumed", ledger["stopped_reason"])
        with patch("swarm_sim.runner.run_scene") as flight:
            with self.assertRaisesRegex(ValueError, "validation stopped"):
                runner.run_one(self.root, "V02_r2")
            flight.assert_not_called()
        self.preserved()

    def test_expected_V05_failure_completes_seventh_attempt_then_forbids_V06(self):
        ledger = self.prepare()
        ledger.update(attempts_started=3, new_sitl_runs=3)
        for job in ledger["jobs"][:3]:
            run, metadata, _ = self.mock_result(job["key"])
            ledger["records"].append(dict(job, state="finished", run_directory=str(run), run_id=metadata["run_id"],
                metadata_sha256=runner.digest(run / "metadata.json"), quality_sha256=runner.digest(run / "quality.json")))
        self.save(self.root / "records.json", ledger)
        prior_rows = [self.row("V01"), self.row("V02"), self.row("V02", 2), self.row("V03"), self.row("V04")]
        final = self.row("V05", expected={"as_expected": True})
        final.update(run_status="failed", exit_code=1)
        with ExitStack() as stack:
            flight = self.guards(stack)
            flight.return_value = self.mock_result("new_v05", "failed")
            stack.enter_context(patch.object(runner, "verify_records_v2",
                side_effect=[self.review(prior_rows), self.review(prior_rows + [final])]))
            self.assertEqual(runner.run_one(self.root, "V05_r1"), 0)
            flight.assert_called_once()
        updated = runner.read(self.root / "records.json")
        self.assertEqual(updated["attempts_started"] + updated["prior_attempts"], 7)
        self.assertEqual(updated["new_sitl_runs"] + updated["prior_sitl_runs"], 7)
        self.assertTrue(updated["completed_authorized_v1"])
        self.assertNotIn("stopped_reason", updated)
        self.assertEqual(updated["records"][-1]["exit_code"], 1)
        self.assertTrue(updated["records"][-1]["acceptance_record"]["passed"])
        with ExitStack() as stack:
            flight = self.guards(stack)
            with self.assertRaisesRegex(ValueError, "budget exhausted"):
                runner.run_one(self.root, "V06_r1")
            flight.assert_not_called()
        self.preserved()


if __name__ == "__main__":
    unittest.main()
