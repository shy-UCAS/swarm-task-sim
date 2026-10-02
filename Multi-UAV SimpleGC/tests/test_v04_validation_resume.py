"""Bounded V1 resume ledger contracts. All flight calls are mocked."""

import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from scripts import run_v04_v1 as runner


class ValidationResumeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.previous = self.root / "previous"
        self.previous.mkdir()
        self.run = self.previous / "failed_run"
        self.run.mkdir()
        self.save(self.run / "metadata.json", {"status": "failed", "run_id": "failed_v01"})
        self.save(self.run / "quality.json", {"usable": False})
        record = dict(validation_id="V01", repeat=1, state="finished", run_status="failed",
                      run_id="failed_v01", run_directory=str(self.run), exit_code=1,
                      metadata_sha256=runner.digest(self.run / "metadata.json"),
                      quality_sha256=runner.digest(self.run / "quality.json"))
        self.history = self.previous / "records.json"
        self.save(self.history, dict(attempts_started=1, new_sitl_runs=1, records=[record],
                                     stopped_reason="STAT_RESET mismatch"))
        self.originals = {p: p.read_bytes() for p in self.previous.rglob("*") if p.is_file()}

    @staticmethod
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")

    def preserved(self):
        for path, original in self.originals.items():
            self.assertEqual(path.read_bytes(), original, str(path))

    def ledger(self, index=0):
        root = self.root / "resume"
        root.mkdir(exist_ok=True)
        task, scene = root / "task.json", root / "scene.json"
        self.save(task, {})
        self.save(scene, {})
        jobs = [dict(key=f"{name}_r{repeat}", validation_id=name, repeat=repeat,
                     task=str(task), scene=str(scene), task_sha256=runner.digest(task),
                     scene_sha256=runner.digest(scene)) for name, repeat, _ in runner.JOBS]
        ledger = dict(budget=7, historical_evidence=runner.historical_evidence(self.history),
                      attempts_started=index, new_sitl_runs=index, records=[], jobs=jobs,
                      offline_gate=str(root / "offline.json"))
        self.save(root / "records.json", ledger)
        return root, ledger

    def guards(self, stack):
        stack.enter_context(patch.object(runner, "check_offline_gate", return_value={"status": "PASS"}))
        return stack.enter_context(patch("swarm_sim.runner.run_scene"))

    @staticmethod
    def review_row(name, expected=None):
        return dict(validation_id=name, run_id=name + "_mock", run_status="completed",
                    exit_code=0, cleanup={"complete": True}, evidence_integrity_pass=True,
                    issues=[], criteria={f"AC{i}": True for i in range(1, 7)},
                    expected_failure=expected)

    @staticmethod
    def review(rows):
        return dict(source_files_unchanged=True, records=rows,
                    ac1_pooled={"matrix_complete": True}, observed_route_criteria={"AC1": True})

    def test_historical_failed_attempt_is_bound_without_reclassification(self):
        evidence = runner.historical_evidence(self.history, runner.digest(self.history))
        self.assertEqual(evidence["attempts_started"], 1)
        self.assertEqual(evidence["new_sitl_runs"], 1)
        self.assertEqual(evidence["status"], "preserved_failed_not_reclassified")
        self.assertEqual(evidence["run_ids"], ["failed_v01"])
        self.preserved()

    def test_historical_ledger_hash_change_is_rejected(self):
        expected = runner.digest(self.history)
        data = runner.read(self.history)
        data["records"][0]["exit_code"] = 0
        self.save(self.history, data)
        with self.assertRaisesRegex(ValueError, "historical failed ledger changed"):
            runner.historical_evidence(self.history, expected)

    def test_historical_run_and_quality_hash_changes_are_rejected(self):
        for name in ("metadata", "quality"):
            with self.subTest(name=name):
                path = self.run / (name + ".json")
                saved = path.read_bytes()
                self.save(path, {"changed": True})
                with self.assertRaisesRegex(ValueError, "historical failed run changed"):
                    runner.historical_evidence(self.history)
                path.write_bytes(saved)
        self.preserved()

    def test_success_or_multiple_historical_attempts_cannot_be_resume_basis(self):
        original = runner.read(self.history)
        for updates in ({"attempts_started": 2}, {"new_sitl_runs": 0},
                        {"records": [dict(original["records"][0], run_status="completed")]}):
            with self.subTest(updates=updates):
                self.save(self.history, dict(original, **updates))
                with self.assertRaisesRegex(ValueError, "exactly the preserved failed V01"):
                    runner.historical_evidence(self.history)
        self.history.write_bytes(self.originals[self.history])

    def test_prepare_produces_six_new_jobs_with_seven_total_budget(self):
        root = self.root / "prepared"
        # Compile real small v3 fixtures offline; no runner or SITL is involved.
        with patch("builtins.print"), patch("swarm_sim.runner.run_scene") as flight:
            runner.prepare(root, self.history, root / "offline.json")
            flight.assert_not_called()
        ledger = runner.read(root / "records.json")
        self.assertEqual(ledger["budget"], 7)
        self.assertEqual(ledger["attempts_started"], 0)
        self.assertEqual(ledger["historical_evidence"]["attempts_started"], 1)
        self.assertEqual([job["key"] for job in ledger["jobs"]],
                         ["V01_r1", "V02_r1", "V02_r2", "V03_r1", "V04_r1", "V05_r1"])
        last = runner.read(Path(ledger["jobs"][-1]["scene"]))
        self.assertEqual(last["task_spec"]["execution"]["phase_timeout_override_s"], .01)
        self.preserved()

    def test_budget_sequence_stopped_and_unfinished_guards_never_launch(self):
        cases = [(6, {}, "V06_r1", "budget exhausted"),
                 (0, {}, "V02_r1", "next authorized"),
                 (0, {"stopped_reason": "AC4 failed"}, "V01_r1", "validation stopped"),
                 (0, {"budget": 8}, "V01_r1", "exactly seven"),
                 (0, {"records": [{"state": "started"}]}, "V01_r1", "no finished evidence")]
        for index, changes, key, message in cases:
            with self.subTest(message=message):
                root, ledger = self.ledger(index)
                ledger.update(changes)
                self.save(root / "records.json", ledger)
                with ExitStack() as stack:
                    flight = self.guards(stack)
                    with self.assertRaisesRegex(ValueError, message):
                        runner.run_one(root, key)
                    flight.assert_not_called()
        self.preserved()

    def test_unknown_prior_route_criterion_stops_before_next_flight(self):
        root, ledger = self.ledger(2)
        ledger["records"] = [{"state": "finished"}, {"state": "finished"}]
        self.save(root / "records.json", ledger)
        rows = [self.review_row("V01"), self.review_row("V02")]
        rows[-1]["criteria"]["AC4"] = None
        with ExitStack() as stack:
            flight = self.guards(stack)
            stack.enter_context(patch("scripts.verify_v04_v1.verify_records", return_value=self.review(rows)))
            with self.assertRaisesRegex(ValueError, "AC4=None"):
                runner.run_one(root, "V02_r2")
            flight.assert_not_called()
        self.assertIn("AC4=None", runner.read(root / "records.json")["stopped_reason"])
        self.preserved()

    def test_V05_expected_failure_completes_sixth_new_attempt_without_stop_misclassification(self):
        root, ledger = self.ledger(5)
        ledger["records"] = [{"state": "finished"} for _ in range(5)]
        self.save(root / "records.json", ledger)
        prior_rows = [self.review_row(name) for name in ("V01", "V02", "V02", "V03", "V04")]
        last = self.review_row("V05", {"as_expected": True})
        last.update(run_status="failed", exit_code=1)
        directory = root / "mock_v05"
        metadata = dict(run_id="v05_mock", status="failed", sitl={"instances": [{"pid": 123}]})
        quality = {"usable": False}
        self.save(directory / "metadata.json", metadata)
        self.save(directory / "quality.json", quality)
        with ExitStack() as stack:
            flight = self.guards(stack)
            flight.return_value = (directory, metadata, quality)
            stack.enter_context(patch.object(runner, "validate_task_binding"))
            stack.enter_context(patch("builtins.print"))
            stack.enter_context(patch("scripts.verify_v04_v1.verify_records",
                                      side_effect=[self.review(prior_rows), self.review(prior_rows + [last])]))
            self.assertEqual(runner.run_one(root, "V05_r1"), 1)
            flight.assert_called_once()
        updated = runner.read(root / "records.json")
        self.assertEqual(updated["attempts_started"], 6)
        self.assertEqual(updated["new_sitl_runs"] + updated["historical_evidence"]["new_sitl_runs"], 7)
        self.assertNotIn("stopped_reason", updated)
        self.assertEqual(updated["records"][-1]["run_status"], "failed")
        self.assertEqual(updated["records"][-1]["exit_code"], 1)
        with ExitStack() as stack:
            flight = self.guards(stack)
            with self.assertRaisesRegex(ValueError, "budget exhausted"):
                runner.run_one(root, "V06_r1")
            flight.assert_not_called()
        self.preserved()

    def test_post_run_evidence_change_stops_even_when_flight_quality_passed(self):
        root, _ = self.ledger()
        directory = root / "mock_v01"
        metadata = dict(run_id="v01_mock", status="completed", sitl={"instances": [{"pid": 123}]})
        quality = {"usable": True}
        self.save(directory / "metadata.json", metadata)
        self.save(directory / "quality.json", quality)
        report = self.review([self.review_row("V01")])
        report["source_files_unchanged"] = False
        with ExitStack() as stack:
            flight = self.guards(stack)
            flight.return_value = (directory, metadata, quality)
            stack.enter_context(patch.object(runner, "validate_task_binding"))
            stack.enter_context(patch("builtins.print"))
            stack.enter_context(patch("scripts.verify_v04_v1.verify_records", return_value=report))
            self.assertEqual(runner.run_one(root, "V01_r1"), 1)
            flight.assert_called_once()
        updated = runner.read(root / "records.json")
        self.assertIn("evidence integrity", updated["stopped_reason"])
        self.assertEqual(updated["records"][-1]["exit_code"], 0)
        self.assertEqual(updated["records"][-1]["run_status"], "completed")
        self.preserved()

    def test_AC1_single_run_is_reported_but_only_complete_pooled_matrix_gates(self):
        for complete, pooled, expected_calls in ((False, False, 1), (True, False, 0)):
            with self.subTest(route_matrix_complete=complete):
                root, ledger = self.ledger(2)
                ledger["records"] = [{"state": "finished"}, {"state": "finished"}]
                self.save(root / "records.json", ledger)
                rows = [self.review_row("V01"), self.review_row("V02")]
                rows[-1]["criteria"]["AC1"] = False
                report = self.review(rows)
                report["ac1_pooled"]["matrix_complete"] = complete
                report["observed_route_criteria"]["AC1"] = pooled
                with ExitStack() as stack:
                    flight = self.guards(stack)
                    # Stop at the mocked call, so this test never produces a flight result.
                    flight.side_effect = RuntimeError("mock flight reached")
                    stack.enter_context(patch.object(runner, "validate_task_binding"))
                    stack.enter_context(patch("scripts.verify_v04_v1.verify_records", return_value=report))
                    error, message = (ValueError, "pooled AC1") if complete else (RuntimeError, "mock flight reached")
                    with self.assertRaisesRegex(error, message):
                        runner.run_one(root, "V02_r2")
                    self.assertEqual(flight.call_count, expected_calls)
        self.preserved()


if __name__ == "__main__":
    unittest.main()
