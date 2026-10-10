"""Offline r2 persistence fixes: replace retries, worker assignment, progress snapshot.

No test launches SITL; files live in temporary directories and only the
Windows sharing violation and the simulator boundary are injected.
"""

import builtins
import copy
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_parallel_batch as cli
from swarm_sim import parallel_batch as batch
from test_parallel_batch import ControllerFixture, FakeWorker, fake_attempt, fake_result


def sharing_violation(code):
    class Denied(PermissionError):
        winerror = code
    return Denied(13, f"injected WinError {code}")


class FlakyReplace:
    """Fail Path.replace for chosen temporary names, then defer to the real call."""
    def __init__(self, names, code=5, failures=2):
        self.names, self.code, self.remaining, self.calls = set(names), code, failures, 0
        self.original = Path.replace

    def __get__(this, instance, owner):
        # Bind like a method so patch.object(Path, "replace", flaky) works.
        return lambda target: this(instance, target)

    def __call__(this, self, target):
        if self.name in this.names and this.remaining != 0:
            this.remaining -= 1
            this.calls += 1
            raise sharing_violation(this.code)
        return this.original(self, target)


class ReplaceRetryTests(ControllerFixture):
    def test_transient_sharing_violation_is_retried_and_batch_completes(self):
        for code in (5, 32):
            with self.subTest(winerror=code):
                for path in self.root.rglob("*"):
                    if path.is_file():
                        path.unlink()
                for k in range(self.plan["shards"]):
                    for directory in (self.root / "shards" / f"shard_{k:02d}" / "attempts").iterdir():
                        directory.rmdir()
                self.launches.clear()
                self.persist(batch.new_state(self.plan))
                flaky = FlakyReplace({"control.json.tmp", "ledger.json.tmp"}, code, failures=4)
                errors = io.StringIO()
                with patch.object(Path, "replace", flaky), patch.object(batch.sys, "stderr", errors):
                    state = self.run_controller()
                self.assertEqual(flaky.calls, 4)
                self.assertIsNone(state["stopped_reason"])
                self.assertTrue(state["completed"])
                self.assertEqual(batch.read(self.root / "control.json"), state)
                for shard in range(2):
                    ledger = batch.read(self.root / "shards" / f"shard_{shard:02d}" / "ledger.json")
                    self.assertEqual(ledger["attempts"], [a for a in state["attempts"] if a["shard_id"] == shard])
                self.assertEqual(errors.getvalue().count("save_atomic retry"), 4)
                self.assertIn(f"WinError {code}", errors.getvalue())
                self.assertNotIn("save_atomic", json.dumps(state))  # retries stay out of the ledger

    def test_exhausted_retries_keep_original_persistence_stop_format(self):
        state = batch.new_state(self.plan)
        self.persist(state)
        before = (self.root / "control.json").read_bytes()
        state["status"] = "running"
        unsaved = copy.deepcopy(state)
        flaky = FlakyReplace({"control.json.tmp"}, 5, failures=-1)
        sleeps, errors = [], io.StringIO()
        controller = batch.Controller(self.root, launcher=self.launch, verifier=lambda p, a, r: r)
        with patch.object(Path, "replace", flaky), patch.object(batch.time, "sleep", side_effect=sleeps.append), \
                patch.object(batch.sys, "stderr", errors):
            self.assertFalse(controller._persist(state))
        exc = sharing_violation(5)
        self.assertEqual(state["stopped_reason"], f"state persistence failed: {type(exc).__name__}: {exc}")
        self.assertTrue(state["stopped_reason"].startswith("state persistence failed: "))
        self.assertEqual(sleeps[0], batch.REPLACE_RETRY_FIRST)
        self.assertLessEqual(max(sleeps), batch.REPLACE_RETRY_CAP)
        self.assertTrue(5 <= sum(sleeps) <= 10, sum(sleeps))
        self.assertEqual(flaky.calls, len(sleeps) + 1)
        self.assertIn("save_atomic gave up", errors.getvalue())
        self.assertIn("active workers will still drain", errors.getvalue())
        self.assertEqual((self.root / "control.json").read_bytes(), before)
        self.assertEqual(batch.read(self.root / "control.json.tmp"), unsaved)  # unsaved value kept

    def test_other_errors_are_not_retried(self):
        for error in (PermissionError(13, "plain"), sharing_violation(2), OSError("disk")):
            with self.subTest(error=repr(error)):
                sleeps = []

                def fail(self, target):
                    raise error

                with patch.object(Path, "replace", fail), patch.object(batch.time, "sleep", side_effect=sleeps.append), \
                        patch.object(batch.sys, "stderr", io.StringIO()):
                    with self.assertRaises(type(error)):
                        batch.save_atomic(self.root / "control.json", {"x": 1})
                self.assertEqual(sleeps, [])


class WorkerAssignmentTests(ControllerFixture):
    def launch(self, plan, attempt):
        # Order: durable reservation -> assignment.json -> Popen.
        assignment = batch.read(Path(attempt["attempt_directory"]) / "assignment.json")
        durable = batch.read(self.root / "control.json")["attempts"][-1]
        self.assertEqual({k: assignment[k] for k in batch.ASSIGNMENT_FIELDS},
                         {k: durable[k] for k in batch.ASSIGNMENT_FIELDS})
        self.assertEqual(assignment["plan_sha256"], batch.canonical_hash(plan))
        return super().launch(plan, attempt)

    def test_controller_writes_assignment_after_reservation_before_launch(self):
        state = self.run_controller(batch.new_state(self.plan))
        self.assertTrue(state["completed"])
        self.assertEqual(len(self.launches), len(self.plan["tasks"]))

    def test_failed_reservation_or_assignment_never_launches(self):
        for target in ("_save_state", "write_assignment"):
            with self.subTest(target=target):
                self.launches.clear()
                self.persist(batch.new_state(self.plan))
                original = getattr(batch, target)
                calls = []

                def fail_dispatch(*args):
                    calls.append(args)
                    if target == "write_assignment" or any(a["status"] == "running" for a in args[1]["attempts"]):
                        raise OSError("injected dispatch write failure")
                    return original(*args)

                with patch.object(batch, target, side_effect=fail_dispatch), \
                        patch.object(batch.sys, "stderr", io.StringIO()):
                    state = self.run_controller()
                self.assertIn("dispatch infrastructure", state["stopped_reason"])
                self.assertEqual(self.launches, [])
                for directory in self.root.glob("shards/shard_*/attempts/*"):
                    if target == "_save_state":
                        self.assertFalse((directory / "assignment.json").exists())
                    for path in directory.iterdir():
                        path.unlink()
                    directory.rmdir()
                (self.root / "control.json").unlink()

    def worker_run(self, attempt_id):
        opened = []
        real_builtin, real_io = builtins.open, io.open

        def spy(real):
            def wrapped(file, *args, **kwargs):
                opened.append(Path(file).name if isinstance(file, (str, Path)) else file)
                return real(file, *args, **kwargs)
            return wrapped

        result = dict(attempt_id=attempt_id, run_id="r")
        with patch.object(cli, "load_plan", return_value=self.plan), patch.object(cli, "integrity"), \
                patch("swarm_sim.parallel_worker.execute_attempt", return_value=result) as execute, \
                patch.object(builtins, "open", spy(real_builtin)), patch.object(io, "open", spy(real_io)):
            output = cli.worker(self.root, attempt_id)
        return output, execute, opened

    def test_worker_never_opens_control_json_and_keeps_safety_checks(self):
        state = batch.new_state(self.plan)
        attempt = fake_attempt(self.plan, 3)
        Path(attempt["attempt_directory"]).mkdir()
        state["attempts"].append(attempt)
        self.persist(state)
        batch.write_assignment(self.plan, attempt)
        output, execute, opened = self.worker_run(attempt["attempt_id"])
        self.assertEqual(output["attempt_id"], attempt["attempt_id"])
        self.assertEqual(execute.call_args.args[1], {k: attempt[k] for k in batch.ASSIGNMENT_FIELDS})
        self.assertIn("assignment.json", opened)
        self.assertNotIn("control.json", opened)
        self.assertNotIn("control.json.tmp", opened)

        # Duplicate invocation of an executed attempt is still refused.
        with self.assertRaisesRegex(ValueError, "already executed"):
            self.worker_run(attempt["attempt_id"])

    def test_worker_rejects_mismatched_or_missing_assignment(self):
        cases = dict(mission=dict(mission_id="mission_99"), family=dict(family_id="family_99"),
                     shard=dict(shard_id=0), port=dict(base_port=19100), index=dict(global_index=99),
                     retry=dict(attempt_index=2), plan=dict(plan_sha256="0"*64), batch=dict(batch_id="other"),
                     identity=dict(attempt_id="a000009"),
                     directory=dict(attempt_directory=str(self.root / "elsewhere")))
        for number, (name, change) in enumerate(cases.items()):
            with self.subTest(case=name):
                attempt = fake_attempt(self.plan, 1, sequence=number)  # shard 1
                directory = Path(attempt["attempt_directory"])
                directory.mkdir()
                batch.write_assignment(self.plan, attempt)
                path = directory / "assignment.json"
                data = batch.read(path)
                data.update(change)
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.worker_run(attempt["attempt_id"])
                self.assertFalse((directory / "started.json").exists())
        with self.assertRaisesRegex(ValueError, "controller-reserved"):
            self.worker_run("a000077")
        with self.assertRaisesRegex(ValueError, "controller-reserved"):
            self.worker_run("../a000001")


class ProgressSnapshotTests(ControllerFixture):
    def assert_progress_matches(self, state):
        progress = batch.read(self.root / "progress.json")
        finished = [a for a in state["attempts"] if a["status"] == "finished"]
        self.assertEqual(progress["distinct_tasks_finished"], len({a["global_index"] for a in finished}))
        self.assertEqual(progress["attempts"], len(state["attempts"]))
        self.assertEqual(progress["in_flight"], len(state["attempts"]) - len(finished))
        self.assertEqual(progress["rolling_anomaly_count"], state["rolling"]["anomaly_count"])
        for key in ("paused", "completed", "stopped_reason", "status"):
            self.assertEqual(progress[key], state.get(key, False))
        self.assertIn("updated_utc", progress)

    def test_progress_follows_every_ledger_save(self):
        save_atomic, seen = batch.save_atomic, []

        def record(path, value):
            save_atomic(path, value)
            if Path(path).name == "progress.json":
                control = batch.read(self.root / "control.json")
                self.assertEqual(value["attempts"], len(control["attempts"]))
                self.assertEqual(value["stopped_reason"], control["stopped_reason"])
            seen.append(Path(path).name)

        with patch.object(batch, "save_atomic", side_effect=record):
            state = self.run_controller(batch.new_state(self.plan))
        self.assertEqual(seen.count("control.json"), seen.count("progress.json"))
        self.assertEqual(seen[-1], "progress.json")
        self.assert_progress_matches(state)
        self.assertTrue(batch.read(self.root / "progress.json")["completed"])

    def test_missing_or_corrupt_progress_does_not_affect_run_or_resume(self):
        self.make_worker = lambda p, a: FakeWorker(a, fake_result(p, a), polls=2)
        with patch.object(batch.time, "sleep", side_effect=[KeyboardInterrupt(), None]):
            paused = self.run_controller(batch.new_state(self.plan))
        self.assertTrue(paused["paused"])
        self.assert_progress_matches(paused)
        (self.root / "progress.json").write_text("{corrupt", encoding="utf-8")
        resumed = self.run_controller(resume=True)
        self.assertTrue(resumed["completed"])
        self.assert_progress_matches(resumed)

    def test_deleted_progress_is_never_read_and_resume_completes(self):
        self.make_worker = lambda p, a: FakeWorker(a, fake_result(p, a), polls=2)
        reads, real_read = [], batch.read

        def spy(path):
            reads.append(Path(path).name)
            return real_read(path)

        with patch.object(batch, "read", side_effect=spy):
            with patch.object(batch.time, "sleep", side_effect=[KeyboardInterrupt(), None]):
                paused = self.run_controller(batch.new_state(self.plan))
            self.assertTrue(paused["paused"])
            (self.root / "progress.json").unlink()
            resumed = self.run_controller(resume=True)
        self.assertTrue(resumed["completed"])
        self.assert_progress_matches(resumed)
        self.assertIn("control.json", reads)
        self.assertNotIn("progress.json", reads)

    def test_progress_write_failure_is_logged_and_never_stops_batch(self):
        flaky = FlakyReplace({"progress.json.tmp"}, 5, failures=-1)
        errors = io.StringIO()
        with patch.object(Path, "replace", flaky), patch.object(batch.sys, "stderr", errors):
            state = self.run_controller(batch.new_state(self.plan))
        self.assertIsNone(state["stopped_reason"])
        self.assertTrue(state["completed"])
        self.assertEqual(batch.read(self.root / "control.json"), state)
        self.assertFalse((self.root / "progress.json").exists())
        self.assertIn("progress snapshot skipped", errors.getvalue())
        self.assertIn("save_atomic gave up", errors.getvalue())
        self.assertNotIn("state persistence failed", errors.getvalue())

        # Any non-retryable failure is skipped the same way.
        with patch.object(batch, "save_atomic", side_effect=OSError("disk")), \
                patch.object(batch.sys, "stderr", io.StringIO()) as log:
            batch._save_progress(self.root, state)
        self.assertIn("progress snapshot skipped: OSError", log.getvalue())


if __name__ == "__main__":
    unittest.main()
