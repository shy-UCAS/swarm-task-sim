"""Offline rule-pause acceptance; all workers and batches are temporary fakes."""
import copy
import io
import itertools
import json
from pathlib import Path
from unittest.mock import patch

from swarm_sim import parallel_batch as batch
from scripts import run_parallel_batch as cli
from test_parallel_batch import ControllerFixture, FakeWorker, fake_attempt, fake_plan, fake_result


class RulePauseTests(ControllerFixture):
    def pause_at_fifth(self):
        self.make_worker = lambda p, a: FakeWorker(a, fake_result(p, a,
            ["episode_quality_ineligible", "label_disagreement"] if a["global_index"] < 5 else ()),
            polls=4 if a["global_index"] == 5 else 1)
        return self.run_controller(batch.new_state(self.plan))

    def test_rule_pause_records_trigger_window_and_drain_without_stopping(self):
        paused = self.pause_at_fifth()
        self.assertTrue(paused["paused"])
        self.assertIsNone(paused["stopped_reason"])
        self.assertEqual(paused["rule_pause_count"], 1)
        event, = paused["pause_events"]
        self.assertEqual(event["kind"], "rule")
        self.assertEqual(event["trigger_attempt_id"], "a000004")
        self.assertEqual(event["registered_completion_count"], 5)
        self.assertEqual(event["reserved_attempt_count"], 6)
        self.assertEqual(event["completed_after_pause"], ["a000005"])
        self.assertTrue(event["utc"] and event["drained_utc"])
        self.assertEqual(event["pause_reason"]["anomalous_runs"],
                         [row for row in paused["rolling"]["runs"] if row["reasons"]])
        self.assertEqual(len(event["pause_reason"]["anomalous_runs"]), 5)
        self.assertTrue(all(row["reasons"] == ["episode_quality_ineligible", "label_disagreement"]
                            for row in event["pause_reason"]["anomalous_runs"]))
        self.assertEqual(len(self.launches), 6)
        self.assertTrue(all(a["status"] == "finished" for a in paused["attempts"]))
        self.assertFalse(any(a["completed_after_stop"] for a in paused["attempts"]))
        self.assertFalse((self.root / "stop_report.json").exists())
        for worker in self.workers:
            worker.terminate.assert_not_called()
            worker.kill.assert_not_called()

    def test_resume_normal_then_anomaly_repauses_and_counts_two_without_losing_budget(self):
        self.plan = fake_plan(self.root, count=30)
        paused = self.pause_at_fifth()
        before = copy.deepcopy(paused)
        with self.assertRaisesRegex(ValueError, "resume"):
            self.run_controller()
        snapshots = []
        save = batch._save_state

        def capture(root, state):
            snapshots.append(copy.deepcopy(state))
            save(root, state)

        self.make_worker = lambda p, a: FakeWorker(a, fake_result(p, a,
            ["task_failure_truth"] if a["global_index"] == 7 else ()),
            polls=3 if a["global_index"] == 7 else 1)
        with patch.object(batch, "_save_state", side_effect=capture):
            again = self.run_controller(resume=True)
        normal = next(s for s in snapshots if len(s["completion_order"]) == 7)
        self.assertFalse(normal["paused"])
        self.assertEqual(normal["rolling"]["anomaly_count"], 5)
        self.assertTrue(again["paused"])
        self.assertEqual(again["rule_pause_count"], 2)
        self.assertEqual(again["pause_events"][1]["trigger_attempt_id"], "a000007")
        self.assertEqual(again["attempts"][:6], before["attempts"])
        self.assertEqual(again["completion_order"][:6], before["completion_order"])
        self.assertEqual(again["pause_events"][0], before["pause_events"][0])
        self.make_worker = lambda p, a: FakeWorker(a, fake_result(p, a))
        completed = self.run_controller(resume=True)
        self.assertTrue(completed["completed"])
        self.assertEqual(sorted(a["global_index"] for a in completed["attempts"]), list(range(30)))
        self.assertEqual(len(self.launches), 30)
        self.assertEqual(completed["plan_sha256"], before["plan_sha256"])
        self.assertEqual(completed["rule_pause_count"], 2)
        self.assertEqual([e["kind"] for e in completed["resume_events"]], ["rule", "rule"])
        self.assertEqual([e["pause_event_index"] for e in completed["resume_events"]], [0, 1])
        self.assertEqual(completed["rolling"]["window_count"], 20)
        ordered = sorted(completed["attempts"], key=lambda a: a["completion_seq"])
        self.assertEqual([r["run_id"] for r in completed["rolling"]["runs"]],
                         [a["result"]["run_id"] for a in ordered[-20:]])
        batch._validate_state(self.plan, completed)

    def test_new_anomaly_below_threshold_after_old_anomalies_expire_does_not_pause(self):
        self.plan = fake_plan(self.root, count=30)
        self.pause_at_fifth()
        self.make_worker = lambda p, a: FakeWorker(a, fake_result(p, a,
            ["task_failure_truth"] if a["global_index"] == 27 else ()))
        completed = self.run_controller(resume=True)
        self.assertTrue(completed["completed"])
        self.assertEqual(completed["rule_pause_count"], 1)
        self.assertEqual(completed["rolling"]["anomaly_count"], 1)

    def test_rule_pause_on_last_task_still_requires_review_before_completion(self):
        self.plan = fake_plan(self.root, count=6)
        paused = self.pause_at_fifth()
        self.assertTrue(paused["paused"])
        self.assertFalse(paused["completed"])
        self.assertEqual(len(paused["attempts"]), 6)
        completed = self.run_controller(resume=True)
        self.assertTrue(completed["completed"])
        self.assertEqual(len(self.launches), 6)

    def test_rule_pause_count_has_no_fixed_limit(self):
        self.plan = fake_plan(self.root, count=9, shards=1)
        self.make_worker = lambda p, a: FakeWorker(a, fake_result(p, a, ["label_disagreement"]))
        state = self.run_controller(batch.new_state(self.plan))
        for expected in range(1, 6):
            self.assertTrue(state["paused"])
            self.assertIsNone(state["stopped_reason"])
            self.assertEqual(state["rule_pause_count"], expected)
            state = self.run_controller(resume=True)
        self.assertTrue(state["completed"])
        self.assertEqual(len(state["resume_events"]), 5)
        self.assertEqual(len(self.launches), 9)

    def test_hard_violation_during_rule_drain_overrides_pause_and_resume_is_rejected(self):
        self.make_worker = lambda p, a: FakeWorker(a, fake_result(p, a,
            ["episode_quality_ineligible"],
            hard_failures=["truth_separation"] if a["global_index"] == 5 else []),
            polls=4 if a["global_index"] == 5 else 1)
        stopped = self.run_controller(batch.new_state(self.plan))
        self.assertFalse(stopped["paused"])
        self.assertEqual(stopped["rule_pause_count"], 1)
        self.assertIn("confirmed violation", stopped["stopped_reason"])
        self.assertEqual(stopped["pause_events"][0]["completed_after_pause"], ["a000005"])
        with self.assertRaisesRegex(ValueError, "rule-stopped batch cannot resume"):
            self.run_controller(resume=True)

    def test_all_confirmed_violations_and_infrastructure_remain_irrecoverable(self):
        failures = [dict(hard_failures=[key]) for key in
                    ("truth_separation", "onboard_mission_parameters", "parameter_firmware")]
        failures += [dict(infrastructure_error="protected file hash changed")]
        for failure in failures:
            with self.subTest(failure=failure):
                state = batch.new_state(self.plan)
                attempt = fake_attempt(self.plan, 0)
                state["attempts"].append(attempt)
                batch.register_completion(state, attempt, fake_result(self.plan, attempt, **failure))
                self.persist(state)
                self.assertFalse(state["paused"])
                self.assertEqual(state["rule_pause_count"], 0)
                with self.assertRaisesRegex(ValueError, "rule-stopped batch cannot resume"):
                    self.run_controller(resume=True)
                # Clearing the stop and its events cannot hide hard evidence.
                state.update(stopped_reason=None, stop_events=[])
                with self.assertRaisesRegex(ValueError, "historical stop"):
                    batch._validate_state(self.plan, state)
        self.assertEqual(self.launches, [])

    def test_legacy_rolling_stop_remains_irrecoverable_even_if_reason_cleared(self):
        state = batch.new_state(self.plan)
        for i in range(5):
            attempt = fake_attempt(self.plan, i)
            state["attempts"].append(attempt)
            batch.register_completion(state, attempt, fake_result(self.plan, attempt, ["label_disagreement"]))
        # Model the old format rather than migrating an existing batch.
        for key in ("pause_kind", "pause_reason", "pause_events", "rule_pause_count"):
            state.pop(key)
        state.update(paused=False)
        batch._stop(state, "global rolling anomalies reached 5 in the latest 20 runs", "a000004")
        self.persist(state)
        with self.assertRaisesRegex(ValueError, "rule-stopped batch cannot resume"):
            self.run_controller(resume=True)
        state.update(stopped_reason=None, stop_events=[])
        with self.assertRaisesRegex(ValueError, "historical stop"):
            batch._validate_state(self.plan, state)

    def test_recovery_discovered_rule_pause_is_not_consumed_by_same_resume(self):
        state = batch.new_state(self.plan)
        for i in range(5):
            attempt = fake_attempt(self.plan, i)
            state["attempts"].append(attempt)
            result = fake_result(self.plan, attempt, ["label_disagreement"])
            if i < 4:
                batch.register_completion(state, attempt, result)
            else:
                directory = Path(attempt["attempt_directory"])
                directory.mkdir()
                batch.save_atomic(directory / "result.json", result)
        paused = self.run_controller(state, resume=True)
        self.assertTrue(paused["paused"])
        self.assertEqual(paused["pause_kind"], "rule")
        self.assertEqual(paused.get("resume_events", []), [])
        self.assertEqual(self.launches, [])

    def test_manual_pause_can_be_superseded_by_rule_while_draining(self):
        state = batch.new_state(self.plan)
        for i in range(6):
            attempt = fake_attempt(self.plan, i)
            state["attempts"].append(attempt)
            if i == 4:
                batch._pause(state, "manual", dict(summary="Ctrl+C"))
            batch.register_completion(state, attempt, fake_result(self.plan, attempt, ["label_disagreement"]))
        self.assertEqual([e["kind"] for e in state["pause_events"]], ["manual", "rule"])
        self.assertEqual(state["rule_pause_count"], 1)
        self.assertEqual(state["pause_events"][0]["completed_after_pause"], ["a000004"])
        self.assertEqual(state["pause_events"][1]["completed_after_pause"], ["a000005"])
        batch._validate_state(self.plan, state)

    def test_progress_and_status_distinguish_manual_rule_and_stop(self):
        rule = self.pause_at_fifth()
        manual = batch.new_state(self.plan)
        batch._pause(manual, "manual", dict(summary="Ctrl+C"))
        stopped = copy.deepcopy(rule)
        batch._stop(stopped, "dispatch infrastructure: injected")
        for state, kind in ((manual, "manual"), (rule, "rule"), (stopped, None)):
            with self.subTest(kind=kind):
                self.persist(state)
                stdout = io.StringIO()
                with patch.object(cli, "load_plan", return_value=self.plan), \
                        patch.object(cli, "resolve_data_root", return_value=self.root.parent), \
                        patch.object(cli, "batch_directory", return_value=self.root), \
                        patch("sys.stdout", stdout):
                    code = cli.main(["status", "--batch-id", "offline"])
                shown = json.loads(stdout.getvalue())
                progress = batch.read(self.root / "progress.json")
                for value in (shown, progress):
                    self.assertEqual(value["pause_kind"], kind)
                    self.assertEqual(value["rule_pause_count"], state["rule_pause_count"])
                    self.assertEqual(value["status"], state["status"])
                    self.assertEqual(value["stopped_reason"], state["stopped_reason"])
                    self.assertEqual(value["pause_reason"], state["pause_reason"]["summary"] if kind else None)
                self.assertEqual(code, int(bool(state["stopped_reason"])))

    def test_first_trigger_equivalence_for_normal_and_anomalous_registrations(self):
        # Exhaust all ten-run tails after a twenty-run prefix, including expiry.
        for tail in itertools.product((False, True), repeat=10):
            sequence = [True, False, False, False, False] * 4 + list(tail)
            first_old = first_new = None
            for index, abnormal in enumerate(sequence):
                exceeded = sum(sequence[max(0, index-19):index+1]) >= 5
                if exceeded and first_old is None:
                    first_old = index
                if exceeded and abnormal and first_new is None:
                    first_new = index
            self.assertEqual(first_old, first_new, sequence)
