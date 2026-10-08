"""Offline v0.6 acceptance: real frozen inputs and fake execution processes.

No test launches SITL. Generated inputs and runtime evidence stay in temporary
directories outside the repositories; only process ownership uses mocked Popen.
"""

import copy
import io
import json
import os
import socket
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from swarm_sim import parallel_batch as batch
from swarm_sim.dataset import family_split
from swarm_sim.generation import canonical_hash, file_hash, generate, save_json, verify_generation
from swarm_sim.generation_v2 import normalize_profile
from swarm_sim.processes import SITLProcesses
from swarm_sim.validation_policy_r12b import VERSION as POLICY_VERSION


ROOT = Path(__file__).resolve().parents[1]


def small_profile(count=4):
    profile = normalize_profile(ROOT / "generation_profiles/dual_intent_v05c.json")
    profile["base_scene_count"] = count
    return profile


def assessment(reasons=()):
    return dict(version=POLICY_VERSION, stage="batch", aggregate_anomaly=bool(reasons),
                aggregate_anomaly_reasons=list(reasons), hard_checks={}, hard_failures=[],
                soft_flags=[], new_anomalies=[], semantic_flags=[], individual_pass=True,
                episode_quality_eligible=not bool(reasons))


class FrozenAssignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.bundle = Path(cls.temporary.name) / "bundle"
        generate(small_profile(), cls.bundle)
        cls.listing, _ = verify_generation(cls.bundle / "mission_list.json")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def assignments(self, shards):
        return batch.assign_tasks(self.listing, self.bundle, shards, "simplegc-v02")

    def test_shards_cover_all_tasks_disjoint_and_keep_families_round_robin(self):
        expected = {entry["mission_id"] for entry in self.listing["missions"]}
        for shards in (1, 2, 4):
            with self.subTest(shards=shards):
                tasks = self.assignments(shards)
                self.assertEqual(len(tasks), len(expected))
                self.assertEqual({task["mission_id"] for task in tasks}, expected)
                self.assertEqual([task["global_index"] for task in tasks], list(range(len(tasks))))
                families = {}
                for task in tasks:
                    families.setdefault(task["family_id"], []).append(task)
                for index, family in enumerate(families.values()):
                    self.assertEqual({task["shard_id"] for task in family}, {index % shards})
                    self.assertEqual({task["entry"]["intent"] for task in family},
                                     {"patrol", "reconnaissance"})
                partitions = [{task["mission_id"] for task in tasks if task["shard_id"] == shard}
                              for shard in range(shards)]
                self.assertEqual(set.union(*partitions), expected)
                for left in range(shards):
                    for right in range(left + 1, shards):
                        self.assertFalse(partitions[left] & partitions[right])

    def test_serial_and_sharded_seed_family_scene_and_split_are_identical(self):
        baseline = self.assignments(1)
        for shards in (2, 4):
            with self.subTest(shards=shards):
                divided = self.assignments(shards)
                for serial, parallel in zip(baseline, divided):
                    for field in ("global_index", "mission_id", "family_id", "seed", "split", "entry"):
                        self.assertEqual(serial[field], parallel[field])
                    self.assertEqual(parallel["split"], family_split(parallel["family_id"],
                                                                    salt="simplegc-v02"))
                    source = json.loads((self.bundle / parallel["entry"]["task"]).read_text())
                    self.assertEqual(parallel["seed"], source["seed"])


class DataRootAndIsolationTests(unittest.TestCase):
    def test_short_name_expansion_is_accepted_for_atomic_output_and_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            real = base / "runner administrator"
            real.mkdir()
            alias = base / "RUNNER~1"
            resolve = Path.resolve

            def expanded(path, *args, **kwargs):
                path = path.absolute()
                if path.is_relative_to(alias):
                    path = real / path.relative_to(alias)
                return resolve(path, *args, **kwargs)

            # Model 8.3 expansion on platforms/volumes without short names.
            # Only resolution is mocked; writes and OS locks remain real.
            with patch.object(Path, "resolve", expanded):
                self.assertNotEqual(alias.resolve(), alias.absolute())
                batch.save_atomic(alias / "control.json", {"accepted": True})
                with batch.FileLock(alias / "writer.lock"):
                    with self.assertRaisesRegex(ValueError, "writer already active"):
                        with batch.FileLock(real / "writer.lock"):
                            self.fail("short and long paths acquired separate locks")
            self.assertEqual(batch.read(real / "control.json"), {"accepted": True})
            self.assertFalse((real / "control.json.tmp").exists())

    @unittest.skipUnless(os.name == "nt", "Windows 8.3 paths")
    def test_native_windows_short_name_is_accepted(self):
        import ctypes
        with tempfile.TemporaryDirectory(prefix="parallel short name ") as temp:
            get_short = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
            get_short.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
            get_short.restype = ctypes.c_uint
            size = get_short(temp, None, 0)
            if not size:
                self.skipTest("Windows could not obtain an 8.3 name; mocked coverage remains")
            buffer = ctypes.create_unicode_buffer(size)
            length = get_short(temp, buffer, size)
            self.assertTrue(0 < length < size)
            short = Path(buffer.value)
            if short.absolute() == short.resolve():
                self.skipTest("8.3 aliases unavailable on this volume; mocked coverage remains")
            self.assertTrue(short.samefile(temp))
            batch.save_atomic(short / "control.json", {"accepted": True})
            with batch.FileLock(short / "writer.lock"):
                pass
            self.assertEqual(batch.read(Path(temp) / "control.json"), {"accepted": True})

    def test_links_into_repositories_and_archive_are_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            repository, worktree, archive = (base / name for name in
                                            ("repository", "worktree", "archive"))
            for target in (repository, worktree, archive):
                target.mkdir()
            (repository / ".git").mkdir()
            (worktree / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
            resolve = Path.resolve
            for kind in ("symlink", "junction"):
                for target in (repository, worktree, archive):
                    link = base / f"{kind}_{target.name}"
                    with self.subTest(kind=kind, target=target.name), ExitStack() as stack:
                        try:
                            if kind == "junction" and os.name == "nt":
                                import _winapi
                                _winapi.CreateJunction(str(target), str(link))
                            elif kind == "symlink":
                                link.symlink_to(target, target_is_directory=True)
                            else:
                                raise NotImplementedError("junctions require Windows")
                        except (OSError, NotImplementedError) as exc:
                            # CI may lack symlink privileges or junction support.
                            # Model the resolved destination without mocking I/O.
                            print(f"{kind} to {target.name}: mocked resolution ({exc})")
                            def redirected(path, *args, **kwargs):
                                path = path.absolute()
                                if path.is_relative_to(link):
                                    path = target / path.relative_to(link)
                                return resolve(path, *args, **kwargs)
                            stack.enter_context(patch.object(Path, "resolve", redirected))
                        else:
                            print(f"{kind} to {target.name}: real filesystem link")
                        stack.enter_context(patch.object(batch, "ARCHIVE", archive))
                        with self.assertRaisesRegex(ValueError, "repository|archive"):
                            batch.save_atomic(link / "control.json", {"forbidden": True})
                        with self.assertRaisesRegex(ValueError, "repository|archive"):
                            with batch.FileLock(link / "writer.lock"):
                                self.fail("protected destination acquired a lock")
                        for name in ("control.json", "control.json.tmp", "writer.lock"):
                            self.assertFalse((target / name).exists())

    def test_redirected_output_or_temporary_file_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            protected = base / "repository"
            protected.mkdir()
            (protected / ".git").mkdir()
            sentinel = protected / "sentinel.json"
            sentinel.write_text("frozen evidence", encoding="utf-8")
            resolve = Path.resolve
            for suffix in ("", ".tmp"):
                output = base / "control.json"
                redirected_path = output.with_name(output.name + suffix)

                def redirected(path, *args, **kwargs):
                    actual = resolve(path, *args, **kwargs)
                    return sentinel if actual == redirected_path else actual

                with self.subTest(suffix=suffix), patch.object(Path, "resolve", redirected):
                    with self.assertRaisesRegex(ValueError, "repository"):
                        batch.save_atomic(output, {"forbidden": True})
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "frozen evidence")
                self.assertFalse(output.exists())
                self.assertFalse(output.with_name(output.name + ".tmp").exists())

    def test_missing_or_blank_data_root_has_no_default_and_creates_nothing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "SIM_DATA_ROOT"):
                batch.resolve_data_root()
        with patch.dict(os.environ, {"SIM_DATA_ROOT": "  "}):
            with self.assertRaises(ValueError):
                batch.resolve_data_root()

    def test_data_root_rejects_git_repository_relative_path_and_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            repository = Path(temp) / "repository"
            repository.mkdir()
            (repository / ".git").mkdir()
            for candidate in (repository, repository / "new" / "data", ROOT,
                              ROOT.parent.parent / "Simulation" / "data", Path("relative-data")):
                with self.subTest(path=str(candidate)), self.assertRaises(ValueError):
                    batch.resolve_data_root(candidate)
            # Linked worktrees have a .git file, not a directory.
            worktree = Path(temp) / "worktree"
            worktree.mkdir()
            (worktree / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
            with self.assertRaises(ValueError):
                batch.resolve_data_root(worktree / "data")
            data = Path(temp) / "data"
            with patch.dict(os.environ, {"SIM_DATA_ROOT": str(data)}):
                self.assertEqual(batch.resolve_data_root(), data.resolve())
                self.assertEqual(batch.batch_directory(data, "offline"),
                                 data.resolve() / "parallel_batch" / "offline")

    def test_port_blocks_disjoint_and_reject_vehicle_overflow(self):
        blocks = batch.port_blocks(4, 4)
        self.assertEqual([block["base_port"] for block in blocks], [19100, 19200, 19300, 19400])
        for left, right in zip(blocks, blocks[1:]):
            self.assertLess(left["end_port"], right["base_port"])
        with self.assertRaises(ValueError):
            batch.port_blocks(2, 11)

    def test_port_probe_detects_both_tcp_and_udp_occupancy(self):
        for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            with self.subTest(kind=kind), socket.socket(socket.AF_INET, kind) as occupied:
                if os.name == "nt":
                    occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                occupied.bind(("127.0.0.1", 0))
                port = occupied.getsockname()[1]
                block = dict(shard_id=0, base_port=port, end_port=port)
                with self.assertRaises((ValueError, OSError)):
                    batch.probe_ports([block])

    def test_duplicate_shard_writer_is_rejected_and_lock_is_reusable(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "shard_00.lock"
            with batch.FileLock(path):
                with self.assertRaises(ValueError):
                    with batch.FileLock(path):
                        self.fail("duplicate writer acquired lock")
            with batch.FileLock(path):
                pass

    def test_work_directories_parameters_and_process_cleanup_are_isolated(self):
        scene = json.loads((ROOT / "missions/v3/recon_route_v05.json").read_text())["scenario"]
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            base = Path(temp)
            binary, template = base / "fake.exe", base / "template.parm"
            binary.write_bytes(b"offline fake binary")
            template.write_text("LOG_DISARMED 1\n", encoding="utf-8")
            handles = []

            def fake_popen(*args, **kwargs):
                handle = Mock(pid=100 + len(handles))
                handle.poll.return_value = None
                handle.wait.return_value = 0
                handles.append(handle)
                return handle

            launch = stack.enter_context(patch("swarm_sim.processes.subprocess.Popen", side_effect=fake_popen))
            stack.enter_context(patch("swarm_sim.processes.socket.socket"))
            owners = [SITLProcesses(binary, template, base / f"shard_{shard:02d}" / "run", scene,
                                   base_port=19100 + 100 * shard) for shard in range(2)]
            try:
                left, right = owners[0].start(), owners[1].start()
                self.assertFalse({item["directory"] for item in left} &
                                 {item["directory"] for item in right})
                self.assertFalse({item["url"] for item in left} & {item["url"] for item in right})
                self.assertEqual(launch.call_count, 2 * len(scene["vehicles"]))
                for instance in left + right:
                    self.assertTrue((Path(instance["directory"]) / "defaults.parm").is_file())
                    self.assertTrue((Path(instance["directory"]) / "console.log").is_file())
                owners[0].close()
                for handle in owners[0].processes:
                    handle.terminate.assert_called_once()
                    handle.wait.assert_called_once()
                for handle in owners[1].processes:
                    handle.terminate.assert_not_called()
                    handle.kill.assert_not_called()
                    handle.wait.assert_not_called()
            finally:
                owners[1].close()


def fake_plan(root, count=8, shards=2, max_attempts=None):
    """Controller-only fixture; frozen-input verification is tested separately."""
    return dict(version=batch.VERSION, root=str(root), batch_id="offline", shards=shards,
                max_attempts=max_attempts or count, ports=batch.port_blocks(shards, 2),
                quality_policy_sha256="quality-policy", protocol={"version": "frozen-test-protocol"},
                storage_bytes_per_attempt=100, export_reserve_bytes=50,
                tasks=[dict(global_index=i, mission_id=f"mission_{i:02d}", family_id=f"family_{i:02d}",
                            shard_id=i % shards, seed=i, split="train", entry={}) for i in range(count)])


def fake_attempt(plan, index, sequence=None, retry=0):
    task = plan["tasks"][index]
    number = index if sequence is None else sequence
    attempt_id = f"a{number:06d}"
    directory = Path(plan["root"]) / "shards" / f"shard_{task['shard_id']:02d}" / "attempts" / attempt_id
    return dict(attempt_id=attempt_id, global_index=index, mission_id=task["mission_id"],
                family_id=task["family_id"], shard_id=task["shard_id"], attempt_index=retry,
                attempt_directory=str(directory), base_port=19100 + 100 * task["shard_id"], status="running")


def fake_result(plan, attempt, reasons=(), **updates):
    result = dict({key: attempt[key] for key in ("attempt_id", "global_index", "shard_id", "attempt_index",
                                               "mission_id", "family_id")},
                  run_id=f"run_{attempt['attempt_id']}", assessment=assessment(reasons),
                  hard_failures=[], retryable_pre_takeoff=False, run_status="completed",
                  semantic_protocol=copy.deepcopy(plan["protocol"]),
                  quality_policy_sha256=plan["quality_policy_sha256"],
                  episode_quality_eligible=not bool(reasons),
                  completed_utc=f"2099-01-{30 - attempt['global_index']:02d}T00:00:00Z")
    result.update(updates)
    return result


class FakeWorker:
    def __init__(self, attempt, result, polls=1):
        self.attempt, self.result, self.remaining = attempt, result, polls
        self.terminate, self.kill = Mock(), Mock()

    def poll(self):
        self.remaining -= 1
        if self.remaining > 0:
            return None
        path = Path(self.attempt["attempt_directory"]) / "result.json"
        if not path.exists():
            save_json(path, self.result)
        return 0


class ControllerFixture(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.temp = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.root = Path(self.temp).resolve() / "batch"
        self.root.mkdir()
        self.plan = fake_plan(self.root)
        for k in range(self.plan["shards"]):
            (self.root / "shards" / f"shard_{k:02d}" / "attempts").mkdir(parents=True)
        self.stack.enter_context(patch.object(batch, "load_plan", side_effect=lambda _: self.plan))
        self.stack.enter_context(patch.object(batch, "integrity"))
        self.stack.enter_context(patch.object(batch, "probe_ports"))
        self.stack.enter_context(patch.object(batch.time, "sleep"))
        self.workers, self.launches = [], []

    def persist(self, state):
        batch._save_state(self.root, state)

    def launch(self, plan, attempt):
        # A worker may start only after its globally budgeted attempt is durable.
        durable = batch.read(self.root / "control.json")
        self.assertEqual(durable["attempts"][-1]["attempt_id"], attempt["attempt_id"])
        self.assertLessEqual(len(durable["attempts"]), plan["max_attempts"])
        self.launches.append(copy.deepcopy(attempt))
        worker = self.make_worker(plan, attempt)
        self.workers.append(worker)
        return worker

    def make_worker(self, plan, attempt):
        return FakeWorker(attempt, fake_result(plan, attempt))

    def run_controller(self, state=None, resume=False):
        if state is not None:
            self.persist(state)
        controller = batch.Controller(self.root, launcher=self.launch, verifier=lambda p, a, r: r)
        return controller.run(resume=resume, poll_seconds=0)


class GlobalControllerTests(ControllerFixture):
    def test_redirected_attempt_parent_refuses_dispatch_and_worker_log_before_writes(self):
        attempts = self.root / "shards/shard_00/attempts"
        external = Path(self.temp) / "outside_reserved_batch"
        external.mkdir()
        resolve = Path.resolve

        def redirected(path, *args, **kwargs):
            actual = resolve(path, *args, **kwargs)
            return external / actual.relative_to(attempts) if actual.is_relative_to(attempts) else actual

        # Simulate a junction without relying on Windows symlink privileges.
        # Only resolve is replaced; every mutation remains a real file operation.
        self.persist(batch.new_state(self.plan))
        with patch.object(Path, "resolve", redirected):
            state = self.run_controller()
        self.assertIn("output path escapes", state["stopped_reason"])
        self.assertEqual(state["attempts"], [])
        self.assertEqual(self.launches, [])
        self.assertEqual(list(attempts.iterdir()), [])
        self.assertEqual(list(external.iterdir()), [])

        # Independently exercise the native launcher; it must reject before
        # opening worker.log or constructing a process, even if called directly.
        attempt = fake_attempt(self.plan, 0)
        directory = Path(attempt["attempt_directory"])
        directory.mkdir()
        controller = batch.Controller(self.root)
        with patch.object(Path, "resolve", redirected), patch.object(batch.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(ValueError, "worker output path"):
                controller._launch(self.plan, attempt)
        popen.assert_not_called()
        self.assertEqual(list(directory.iterdir()), [])
        self.assertEqual(list(external.iterdir()), [])

    def test_completion_persistence_failure_stops_dispatch_but_drains_existing_workers(self):
        self.make_worker = lambda p, a: FakeWorker(a, fake_result(p, a),
                                                 polls=1 if a["global_index"] == 0 else 4)
        save_state = batch._save_state

        def fail_after_completion(root, state):
            if any(attempt["status"] == "finished" for attempt in state["attempts"]):
                raise OSError("offline injected full disk")
            return save_state(root, state)

        errors = io.StringIO()
        with patch.object(batch, "_save_state", side_effect=fail_after_completion), \
                patch.object(batch.sys, "stderr", errors):
            state = self.run_controller(batch.new_state(self.plan))
        self.assertIn("completion registration failed", state["stopped_reason"])
        self.assertIn("offline injected full disk", state["stopped_reason"])
        self.assertIn("active workers will still drain", errors.getvalue())
        self.assertFalse(state["completed"])
        self.assertEqual(len(self.launches), 2)
        self.assertEqual(len(state["completion_order"]), 2)
        self.assertTrue(all(attempt["status"] == "finished" for attempt in state["attempts"]))
        self.assertTrue(state["attempts"][1]["completed_after_stop"])
        for worker in self.workers:
            self.assertLessEqual(worker.remaining, 0)
            worker.terminate.assert_not_called()
            worker.kill.assert_not_called()
            self.assertTrue((Path(worker.attempt["attempt_directory"]) / "result.json").is_file())

    def test_out_of_order_completions_use_persisted_sequence_and_rebuild_shard_ledgers(self):
        self.plan = fake_plan(self.root, count=4)
        self.make_worker = lambda p, a: FakeWorker(a, fake_result(p, a),
                                                 polls=5 if a["global_index"] == 0 else 1)
        state = self.run_controller(batch.new_state(self.plan))
        self.assertTrue(state["completed"])
        order = sorted(state["attempts"], key=lambda a: a["completion_seq"])
        self.assertEqual([a["global_index"] for a in order], [1, 3, 0, 2])
        self.assertEqual([a["completion_seq"] for a in order], [1, 2, 3, 4])
        self.assertEqual(state["completion_order"], [a["attempt_id"] for a in order])
        self.assertEqual([r["run_id"] for r in state["rolling"]["runs"]],
                         [a["result"]["run_id"] for a in order])
        self.assertEqual(batch.read(self.root / "control.json"), state)
        for shard in range(2):
            ledger = batch.read(self.root / "shards" / f"shard_{shard:02d}" / "ledger.json")
            self.assertEqual(ledger["attempts"], [a for a in state["attempts"] if a["shard_id"] == shard])

    def test_fifth_global_anomaly_stops_dispatch_and_drains_other_shard(self):
        reasons = ["task_failure_truth", "label_disagreement", "episode_quality_ineligible"]
        self.make_worker = lambda p, a: FakeWorker(a, fake_result(p, a,
            reasons if a["global_index"] < 5 else ()), polls=4 if a["global_index"] == 5 else 1)
        state = self.run_controller(batch.new_state(self.plan))
        self.assertEqual(len(self.launches), 6)
        self.assertFalse(state["completed"])
        self.assertIn("rolling", state["stopped_reason"])
        self.assertEqual(state["rolling"]["anomaly_count"], 5)
        self.assertEqual(state["rolling"]["window_count"], 6)
        self.assertEqual({a["shard_id"] for a in state["attempts"][:5]}, {0, 1})
        self.assertTrue(all(a["status"] == "finished" for a in state["attempts"]))
        self.assertEqual(state["stop_attempt_id"], state["attempts"][4]["attempt_id"])
        self.assertTrue(state["attempts"][5]["completed_after_stop"])
        for worker in self.workers:
            worker.terminate.assert_not_called()
            worker.kill.assert_not_called()

    def test_retry_budget_is_global_reserved_before_launch_and_at_most_once(self):
        self.plan = fake_plan(self.root, count=4, max_attempts=4)
        self.make_worker = lambda p, a: FakeWorker(a, fake_result(p, a,
            retryable_pre_takeoff=a["global_index"] == 0))
        state = self.run_controller(batch.new_state(self.plan))
        self.assertEqual(len(self.launches), 4)
        self.assertIn("budget", state["stopped_reason"])
        retries = [a for a in state["attempts"] if a["global_index"] == 0]
        self.assertEqual([a["attempt_index"] for a in retries], [0, 1])
        self.assertFalse(any(a["attempt_index"] > 1 for a in state["attempts"]))

    def test_failed_run_with_complete_analysis_is_retained_and_dispatch_continues(self):
        self.plan = fake_plan(self.root, count=4)
        self.make_worker = lambda p, a: FakeWorker(a, fake_result(p, a,
            ["episode_quality_ineligible"] if a["global_index"] == 0 else (),
            run_status="failed" if a["global_index"] == 0 else "completed"))
        state = self.run_controller(batch.new_state(self.plan))
        self.assertTrue(state["completed"])
        self.assertIsNone(state["stopped_reason"])
        self.assertEqual(state["rolling"]["anomaly_count"], 1)
        self.assertEqual(state["attempts"][0]["result"]["run_status"], "failed")
        self.assertFalse(state["attempts"][0]["result"]["episode_quality_eligible"])
        self.assertEqual(len(self.launches), 4)

    def test_analysis_error_or_missing_evidence_stops_dispatch_with_reason(self):
        self.make_worker = lambda p, a: FakeWorker(a, fake_result(p, a,
            infrastructure_error="analysis failed: missing quality.json") if a["global_index"] == 0
            else fake_result(p, a), polls=3 if a["global_index"] == 1 else 1)
        state = self.run_controller(batch.new_state(self.plan))
        self.assertEqual(len(self.launches), 2)
        self.assertIn("missing quality.json", state["stopped_reason"])
        self.assertTrue(state["attempts"][1]["completed_after_stop"])

    def test_missing_result_file_is_integrity_failure_not_retry(self):
        self.make_worker = lambda p, a: SimpleNamespace(poll=lambda: 1)
        state = self.run_controller(batch.new_state(self.plan))
        self.assertEqual(len(self.launches), 2)
        self.assertIn("result verification failed", state["stopped_reason"])
        self.assertTrue(all(not a["result"]["retryable_pre_takeoff"] for a in state["attempts"]))

    def test_keyboard_interrupt_stops_dispatch_but_drains_launched_workers(self):
        self.make_worker = lambda p, a: FakeWorker(a, fake_result(p, a), polls=3)
        with patch.object(batch.time, "sleep", side_effect=[KeyboardInterrupt(), None, None, None]):
            state = self.run_controller(batch.new_state(self.plan))
        self.assertEqual(len(self.launches), 2)
        self.assertIn("interrupted", state["stopped_reason"])
        self.assertTrue(all(a["status"] == "finished" for a in state["attempts"]))
        self.assertTrue(all(a["completed_after_stop"] for a in state["attempts"]))
        for worker in self.workers:
            worker.terminate.assert_not_called()
            worker.kill.assert_not_called()

    def test_disk_budget_counts_all_shards_and_export_reserve_before_launch(self):
        required = self.plan["max_attempts"] * self.plan["storage_bytes_per_attempt"] + 50
        with patch.object(batch.shutil, "disk_usage", return_value=SimpleNamespace(free=required - 1)):
            state = self.run_controller(batch.new_state(self.plan))
        self.assertEqual(self.launches, [])
        self.assertEqual(state["attempts"], [])
        self.assertIn("insufficient disk", state["stopped_reason"])
        with patch.object(batch.shutil, "disk_usage", return_value=SimpleNamespace(free=required)):
            self.assertEqual(batch.disk_status(self.plan, 0)["required_bytes"], required)

    def test_protected_file_change_during_execution_stops_dispatch_and_keeps_other_worker(self):
        changed = False

        def make_worker(plan, attempt):
            worker = FakeWorker(attempt, fake_result(plan, attempt), polls=1 if attempt["global_index"] == 0 else 3)
            poll = worker.poll

            def finish_and_change():
                nonlocal changed
                code = poll()
                if code is not None and attempt["global_index"] == 0:
                    changed = True
                return code

            worker.poll = finish_and_change
            return worker

        def integrity(plan):
            if changed:
                raise ValueError("protected file hash changed")

        self.make_worker = make_worker
        with patch.object(batch, "integrity", side_effect=integrity):
            state = self.run_controller(batch.new_state(self.plan))
        self.assertEqual(len(self.launches), 2)
        self.assertIn("protected file hash", state["stopped_reason"])
        self.assertTrue(all(a["status"] == "finished" for a in state["attempts"]))
        for worker in self.workers:
            worker.terminate.assert_not_called()
            worker.kill.assert_not_called()


class CompletionAndRecoveryTests(ControllerFixture):
    def completed_state(self, *, hard_failure=False):
        state = batch.new_state(self.plan)
        attempt = fake_attempt(self.plan, 0)
        state["attempts"].append(attempt)
        directory = Path(attempt["attempt_directory"])
        directory.mkdir(exist_ok=True)
        result = fake_result(self.plan, attempt, hard_failures=["truth_separation"] if hard_failure else [])
        save_json(directory / "result.json", result)
        attempt["result_sha256"] = file_hash(directory / "result.json")
        batch.register_completion(state, attempt, result)
        return state

    def test_window_uses_last_twenty_registrations_and_stop_is_sticky(self):
        self.plan = fake_plan(self.root, count=30)
        state = batch.new_state(self.plan)
        for i in range(26):
            attempt = fake_attempt(self.plan, i)
            state["attempts"].append(attempt)
            reasons = ["task_failure_truth"] if i in (0, 5, 10, 15, 19) else ()
            batch.register_completion(state, attempt, fake_result(self.plan, attempt, reasons))
            if i == 19:
                self.assertEqual(state["rolling"]["anomaly_count"], 5)
                trigger = state["stop_attempt_id"]
        self.assertEqual(state["rolling"]["window_count"], 20)
        self.assertEqual(state["rolling"]["anomaly_count"], 3)
        self.assertEqual(state["stop_attempt_id"], trigger)
        self.assertIsNotNone(state["stopped_reason"])
        self.assertTrue(state["attempts"][-1]["completed_after_stop"])

    def test_registration_is_idempotent_and_rejects_changed_result(self):
        state = batch.new_state(self.plan)
        attempt = fake_attempt(self.plan, 0)
        state["attempts"].append(attempt)
        result = fake_result(self.plan, attempt)
        batch.register_completion(state, attempt, result)
        before = copy.deepcopy(state)
        batch.register_completion(state, attempt, result)
        self.assertEqual(state, before)
        with self.assertRaises(ValueError):
            batch.register_completion(state, attempt, dict(result, run_status="rewritten"))

    def test_interrupted_attempt_never_automatically_reflies(self):
        for phase in ("budget_reserved", "partial_execution"):
            with self.subTest(phase=phase):
                state = batch.new_state(self.plan)
                attempt = fake_attempt(self.plan, 0)
                directory = Path(attempt["attempt_directory"])
                directory.mkdir(exist_ok=True)
                if phase == "partial_execution":
                    (directory / "partial.log").write_text("incomplete", encoding="utf-8")
                state["attempts"].append(attempt)
                self.persist(state)
                with self.assertRaisesRegex(ValueError, "resume"):
                    self.run_controller()
                recovered = self.run_controller(resume=True)
                self.assertEqual(self.launches, [])
                self.assertEqual(len(recovered["attempts"]), 1)
                self.assertIn("no automatic reflight", recovered["stopped_reason"])

    def test_completed_result_before_registration_recovers_once_without_reflight(self):
        self.plan = fake_plan(self.root, count=1)
        state = batch.new_state(self.plan)
        attempt = fake_attempt(self.plan, 0)
        Path(attempt["attempt_directory"]).mkdir()
        save_json(Path(attempt["attempt_directory"]) / "result.json", fake_result(self.plan, attempt))
        state["attempts"].append(attempt)
        recovered = self.run_controller(state, resume=True)
        self.assertTrue(recovered["completed"])
        self.assertEqual(recovered["completion_order"], [attempt["attempt_id"]])
        self.assertEqual(recovered["rolling"]["window_count"], 1)
        self.assertEqual(self.launches, [])
        # A crash between control.json and a shard view is repaired from control.
        (self.root / "shards/shard_00/ledger.json").write_text("{}", encoding="utf-8")
        again = self.run_controller(resume=True)
        self.assertEqual(again["completion_order"], recovered["completion_order"])
        self.assertEqual(batch.read(self.root / "shards/shard_00/ledger.json")["attempts"],
                         again["attempts"])
        self.assertEqual(self.launches, [])

    def test_active_worker_lock_prevents_recovery_duplicate_launch(self):
        state = batch.new_state(self.plan)
        attempt = fake_attempt(self.plan, 0)
        Path(attempt["attempt_directory"]).mkdir()
        state["attempts"].append(attempt)
        with batch.FileLock(self.root / "shards/shard_00/writer.lock"):
            recovered = self.run_controller(state, resume=True)
        self.assertEqual(self.launches, [])
        self.assertIn("worker still active", recovered["stopped_reason"])

    def test_duplicate_controller_is_rejected(self):
        self.persist(batch.new_state(self.plan))
        with batch.FileLock(self.root / "controller.lock"):
            with self.assertRaisesRegex(ValueError, "writer already active"):
                self.run_controller()
        self.assertEqual(self.launches, [])

    def test_corrupt_finished_state_sequence_budget_and_retry_chain_are_rejected(self):
        def remove_sequence(state):
            del state["attempts"][0]["completion_seq"]
            state["completion_order"] = []

        def alter_rolling(state):
            state["rolling"]["window_count"] = 0

        def orphan_retry(state):
            state["attempts"][0]["attempt_index"] = 1

        for mutate in (remove_sequence, alter_rolling, orphan_retry):
            with self.subTest(case=mutate.__name__):
                state = self.completed_state()
                mutate(state)
                self.persist(state)
                with self.assertRaises(ValueError):
                    self.run_controller(resume=True)
                self.assertEqual(self.launches, [])

    def test_changed_registered_identity_stops_recovery_before_dispatch(self):
        state = self.completed_state()
        state["attempts"][0]["result"]["mission_id"] = "alien-task"
        recovered = self.run_controller(state, resume=True)
        self.assertIn("registered assessment changed", recovered["stopped_reason"])
        self.assertEqual(self.launches, [])

    def test_cleared_historical_stop_is_detected_before_dispatch(self):
        state = self.completed_state(hard_failure=True)
        state.update(stopped_reason=None, stop_attempt_id=None)
        self.persist(state)
        with self.assertRaises(ValueError):
            self.run_controller(resume=True)
        self.assertEqual(self.launches, [])

    def test_attempts_above_global_budget_are_rejected_before_recovery(self):
        state = self.completed_state()
        self.plan["max_attempts"] = 0
        state["plan_sha256"] = canonical_hash(self.plan)
        self.persist(state)
        with self.assertRaisesRegex(ValueError, "budget"):
            self.run_controller(resume=True)
        self.assertEqual(self.launches, [])

    def test_registered_result_rewrite_stops_recovery_before_launch(self):
        state = self.completed_state()
        result_path = Path(state["attempts"][0]["attempt_directory"]) / "result.json"
        changed = copy.deepcopy(state["attempts"][0]["result"])
        changed["run_status"] = "rewritten"
        save_json(result_path, changed)
        recovered = self.run_controller(state, resume=True)
        self.assertIn("result file changed", recovered["stopped_reason"])
        self.assertEqual(self.launches, [])

    def test_resume_disk_reserves_remaining_and_inflight_not_finished_attempts(self):
        self.plan = fake_plan(self.root, count=2)
        state = self.completed_state()
        # One completed attempt occupies disk already; only one future attempt
        # plus the unified export reserve remains to be reserved from free space.
        with patch.object(batch.shutil, "disk_usage", return_value=SimpleNamespace(free=150)):
            resumed = self.run_controller(state, resume=True)
        self.assertTrue(resumed["completed"])
        self.assertEqual([a["global_index"] for a in self.launches], [1])


class MergeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def fixture(self, root):
        plan = fake_plan(self.root, count=4)
        state = batch.new_state(plan)
        for index in range(4):
            attempt = fake_attempt(plan, index)
            state["attempts"].append(attempt)
        for index in (2, 0, 3, 1):
            attempt = state["attempts"][index]
            result = fake_result(plan, attempt)
            path = Path(attempt["attempt_directory"]) / "result.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            save_json(path, result)
            attempt["result_sha256"] = file_hash(path)
            batch.register_completion(state, attempt, result)
        return plan, state

    def merge(self, plan, state):
        return batch.merge_records(plan, state, verifier=lambda p, a, r: r)

    def test_merge_uses_global_order_not_completion_order(self):
        plan, state = self.fixture(Path("offline"))
        merged = self.merge(plan, state)
        self.assertEqual([r["global_index"] for r in merged], [0, 1, 2, 3])
        self.assertEqual([r["mission_id"] for r in merged], [t["mission_id"] for t in plan["tasks"]])
        self.assertEqual(state["completion_order"], ["a000002", "a000000", "a000003", "a000001"])

    def test_merge_rejects_duplicate_missing_protocol_and_quality_mismatch(self):
        def missing(plan, state):
            state["attempts"].pop()
            state["completion_order"].pop()

        def duplicate(plan, state):
            state["attempts"][1]["result"]["run_id"] = state["attempts"][0]["result"]["run_id"]

        def protocol(plan, state):
            state["attempts"][0]["result"]["semantic_protocol"] = {"version": "wrong"}

        def policy(plan, state):
            state["attempts"][0]["result"]["quality_policy_sha256"] = "wrong"

        def unfinished(plan, state):
            state["attempts"][0]["status"] = "running"

        for mutate in (missing, duplicate, protocol, policy, unfinished):
            with self.subTest(case=mutate.__name__):
                plan, state = self.fixture(Path("offline"))
                mutate(plan, state)
                with self.assertRaises(ValueError):
                    self.merge(plan, state)

    def test_merge_rejects_duplicate_task_and_evidence_verifier_failure(self):
        plan, state = self.fixture(Path("offline"))
        state["attempts"].append(copy.deepcopy(state["attempts"][0]))
        with self.assertRaises(ValueError):
            self.merge(plan, state)
        plan, state = self.fixture(Path("offline"))
        with self.assertRaisesRegex(ValueError, "evidence hash"):
            batch.merge_records(plan, state, verifier=Mock(side_effect=ValueError("evidence hash changed")))

    def test_merge_rejects_changed_registered_result_file(self):
        plan, state = self.fixture(self.root)
        path = Path(state["attempts"][0]["attempt_directory"]) / "result.json"
        result = batch.read(path)
        result["run_status"] = "changed after registration"
        save_json(path, result)
        with self.assertRaisesRegex(ValueError, "result"):
            self.merge(plan, state)

    def test_merge_retains_retry_evidence_and_selects_only_terminal_run(self):
        plan = fake_plan(self.root, count=1, max_attempts=2)
        state = batch.new_state(plan)
        for number in range(2):
            attempt = fake_attempt(plan, 0, sequence=number, retry=number)
            state["attempts"].append(attempt)
            result = fake_result(plan, attempt, retryable_pre_takeoff=number == 0)
            path = Path(attempt["attempt_directory"]) / "result.json"
            path.parent.mkdir(parents=True)
            save_json(path, result)
            attempt["result_sha256"] = file_hash(path)
            batch.register_completion(state, attempt, result)
        merged = self.merge(plan, state)
        self.assertEqual([row["run_id"] for row in merged], ["run_a000001"])
        self.assertEqual(len(state["attempts"]), 2)
        self.assertTrue((Path(state["attempts"][0]["attempt_directory"]) / "result.json").is_file())


class FrozenPlanTests(unittest.TestCase):
    def test_prepare_generates_once_freezes_hashes_and_refuses_existing_batch(self):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            data = Path(temp) / "data"
            source = Path(temp) / "protected.py"
            source.write_text("frozen configuration", encoding="utf-8")
            stack.enter_context(patch.dict(os.environ, {"SIM_DATA_ROOT": str(data)}))
            stack.enter_context(patch.object(batch, "verify_preflight_files", return_value={"actual": {}}))
            stack.enter_context(patch.object(batch, "_protected_files",
                                            side_effect=lambda *args: {str(source): file_hash(source)}))
            stack.enter_context(patch.object(batch, "probe_ports"))
            generator = stack.enter_context(patch.object(batch, "generate", wraps=generate))
            plan = batch.prepare(small_profile(2), "offline", max_attempts=6,
                                 storage_bytes_per_attempt=1, export_reserve_bytes=1)
            root = Path(plan["root"])
            self.assertEqual(generator.call_count, 1)
            self.assertEqual(root, data.resolve() / "parallel_batch/offline")
            self.assertEqual(batch.load_plan(root), plan)
            self.assertEqual((root / "plan.sha256").read_text().strip(), file_hash(root / "plan.json"))
            self.assertIn(str(root / "bundle/mission_list.json"), plan["bundle_sha256"])
            batch.integrity(plan)
            with self.assertRaisesRegex(ValueError, "already exists"):
                batch.prepare(small_profile(2), "offline", max_attempts=6,
                              storage_bytes_per_attempt=1, export_reserve_bytes=1)
            self.assertEqual(generator.call_count, 1)
            source.write_text("changed configuration", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "protected .*hash"):
                batch.integrity(plan)
            changed = copy.deepcopy(plan)
            changed["tasks"][0]["seed"] += 1
            save_json(root / "plan.json", changed)
            with self.assertRaisesRegex(ValueError, "plan hash"):
                batch.load_plan(root)


if __name__ == "__main__":
    unittest.main()
