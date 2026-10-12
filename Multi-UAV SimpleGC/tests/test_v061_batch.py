"""Frozen runtime overrides and first-dispatch staggering; all workers are fakes."""
import copy
import os
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from swarm_sim import parallel_batch as batch
from swarm_sim import parallel_subset as subset
from swarm_sim.generation import file_hash, generate, verify_generation
from swarm_sim.generation_v2 import normalize_profile
from swarm_sim.protocol import apply_execution_override, semantic_protocol
from swarm_sim.parallel_worker import _inputs, execute_attempt
from test_parallel_batch import ControllerFixture, FakeWorker, fake_result

PROJECT = Path(__file__).resolve().parents[1]


class ExecutionPrepareTests(unittest.TestCase):
    def test_legacy_defaults_unchanged_and_settings_reject_invalid_values(self):
        self.assertEqual(batch.execution_settings(), {})
        self.assertEqual(batch.execution_settings("v0.6.1", 2), dict(
            execution_override=dict(protocol_version="v0.6.1", sim_speedup=2.0), startup_stagger_host_s=30.0))
        for options in (("v0.6", 2, None), (None, 2, None), ("v0.6.1", 0, None),
                        ("v0.6.1", float("nan"), None), ("v0.6.1", 1, -1), (None, None, True)):
            with self.subTest(options=options), self.assertRaises(ValueError):
                batch.execution_settings(*options)

    def test_subset_new_execution_keeps_source_bundle_and_generation_entries_identical(self):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            root = Path(temp).resolve()
            profile = normalize_profile(PROJECT / "generation_profiles/tri_intent_v06_production.json")
            profile["base_scene_count"] = 1
            source = root / "source"
            generate(profile, source)
            listing, _ = verify_generation(source / "mission_list.json")
            before = subset.tree_hashes(source)
            ids = [e["mission_id"] for e in listing["missions"]]
            binary, parameters = root / "firmware.bin", root / "parameters.parm"
            binary.write_bytes(b"ArduCopter V4.5.7\x00")
            parameters.write_bytes(b"TEST=1\n")
            stack.enter_context(patch.dict(os.environ, SIM_DATA_ROOT=str(root / "data")))
            stack.enter_context(patch.object(batch, "verify_preflight_files", return_value={"actual": dict(
                firmware=dict(sha256=file_hash(binary), version_string="ArduCopter V4.5.7"),
                parameters_sha256=file_hash(parameters))}))
            stack.enter_context(patch.object(batch, "_protected_files", return_value={}))
            stack.enter_context(patch.object(batch, "probe_ports"))
            plan = subset.prepare_subset(source, ids, "v061", shards=2, max_attempts=6,
                storage_bytes_per_attempt=1, export_reserve_bytes=1, base_port=20100,
                protocol_version="v0.6.1", sim_speedup=2, binary=binary, parameters=parameters)
            self.assertEqual(plan["startup_stagger_host_s"], 30.0)
            self.assertEqual(plan["execution_override"], dict(protocol_version="v0.6.1", sim_speedup=2.0))
            self.assertEqual(subset.tree_hashes(source), before)
            self.assertEqual(subset.tree_hashes(plan["bundle"]), before)
            self.assertEqual([t["entry"] for t in plan["tasks"]], listing["missions"])
            self.assertEqual(plan["purpose"], "pilot")
            self.assertIs(plan["training_data"], False)
            scene = batch.read(source / listing["missions"][0]["scene"])
            runtime = apply_execution_override(scene, plan["execution_override"])
            self.assertEqual(plan["protocol"], semantic_protocol(runtime, patrol_validator_version=batch.PATROL_VERSION))
            self.assertEqual({k: v for k, v in runtime.items() if k != "task_spec"},
                             {k: v for k, v in scene.items() if k != "task_spec"})
            batch.integrity(plan)
            task = plan["tasks"][0]
            attempt = dict(task, attempt_id="a000000", attempt_index=0, base_port=20100,
                           attempt_directory=str(Path(plan["root"]) / "shards/shard_00/attempts/a000000"))
            _, actual_scene, binding, generation = _inputs(plan, attempt)
            self.assertEqual(actual_scene, runtime)
            self.assertEqual(binding["execution_override"], plan["execution_override"])
            self.assertEqual(generation["generation_entry"], listing["missions"][0])
            with patch("scripts.run_mission_list.run_mission_list", side_effect=RuntimeError("fake runner boundary")) as runner:
                execute_attempt(plan, attempt)
            self.assertEqual(runner.call_args.kwargs["execution_override"], plan["execution_override"])
            self.assertEqual(subset.tree_hashes(plan["bundle"]), before)


class StartupStaggerTests(ControllerFixture):
    def setUp(self):
        super().setUp()
        self.plan["startup_stagger_host_s"] = 30.0
        self.now = 0.0
        self.launch_times = []
        self.stack.enter_context(patch.object(batch.time, "monotonic", side_effect=lambda: self.now))
        self.stack.enter_context(patch.object(batch.time, "sleep", side_effect=self.advance))

    def advance(self, seconds):
        self.now += max(1.0, seconds)

    def launch(self, plan, attempt):
        self.launch_times.append((attempt["shard_id"], self.now))
        return super().launch(plan, attempt)

    def test_first_shard_dispatch_stagger_and_followups_without_delay(self):
        self.plan["shards"] = 4
        self.plan["ports"] = batch.port_blocks(4, 2)
        for task in self.plan["tasks"]:
            task["shard_id"] = task["global_index"] % 4
        for k in (2, 3):
            (self.root / "shards" / f"shard_{k:02d}" / "attempts").mkdir(parents=True)
        state = self.run_controller(batch.new_state(self.plan))
        self.assertTrue(state["completed"])
        first = {k: next(t for shard, t in self.launch_times if shard == k) for k in range(4)}
        self.assertEqual(first, {0: 0.0, 1: 30.0, 2: 60.0, 3: 90.0})
        for k in range(4):
            times = [t for shard, t in self.launch_times if shard == k]
            self.assertEqual(times[1]-times[0], 1.0)

    def test_pause_resume_preserves_epoch_and_never_restarts_stagger(self):
        calls = 0
        def pause_once(seconds):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise KeyboardInterrupt
            self.advance(seconds)
        with patch.object(batch.time, "sleep", side_effect=pause_once):
            paused = self.run_controller(batch.new_state(self.plan))
        self.assertTrue(paused["paused"])
        epoch = paused["dispatch_epoch_utc"]
        # Resume a minute after the durable start: shard 1's initial delay has
        # expired and shard 0's already-dispatched status bypasses staggering.
        future = datetime.fromisoformat(epoch) + timedelta(seconds=60)
        with patch.object(batch, "datetime") as clock:
            clock.fromisoformat.side_effect = datetime.fromisoformat
            clock.now.return_value = future
            resumed = self.run_controller(resume=True)
        self.assertTrue(resumed["completed"])
        self.assertEqual(resumed["dispatch_epoch_utc"], epoch)
        self.assertEqual(next(t for k, t in self.launch_times if k == 1), 0)


if __name__ == "__main__":
    unittest.main()
