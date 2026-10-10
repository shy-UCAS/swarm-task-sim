"""Offline finalization contract and real export over synthetic flight evidence."""

import copy
import io
import os
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_parallel_batch as cli
from swarm_sim import parallel_batch as batch
from swarm_sim import parallel_worker as worker
from swarm_sim.dataset import build_dataset, family_split
from swarm_sim.generation import canonical_hash, file_hash, save_json
from swarm_sim.tasks import compile_task
from test_parallel_worker import fixture, synthetic_runner


class ParallelFinalizeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def mock_batch(self):
        plan = dict(root=str(self.root), version=batch.VERSION, split_salt="explicit-salt",
                    bundle=str(self.root / "bundle"), max_attempts=2,
                    protocol={"version": "frozen-protocol"}, quality_policy_sha256="quality-hash",
                    tasks=[dict(global_index=i, shard_id=i, mission_id=f"m{i}", family_id=f"f{i}",
                                split=family_split(f"f{i}", "explicit-salt")) for i in range(2)])
        state = batch.new_state(plan)
        for i in range(2):
            directory = self.root / "shards" / f"shard_{i:02d}" / "attempts" / f"a{i:06d}"
            (directory / "analysis").mkdir(parents=True)
            save_json(directory / "analysis/manifest.json", dict(run_id=f"r{i}"))
            result = dict(run_id=f"r{i}", run_directory=str(directory / "run"),
                          analysis_directory=str(directory / "analysis"),
                          semantic_protocol=plan["protocol"], quality_policy_sha256="quality-hash",
                          run_status="failed" if i == 0 else "completed",
                          episode_quality_eligible=i != 0, infrastructure_error=None,
                          hard_failures=[], retryable_pre_takeoff=False)
            state["attempts"].append(dict(attempt_id=f"a{i:06d}", attempt_index=0,
                global_index=i, shard_id=i, mission_id=f"m{i}", family_id=f"f{i}",
                base_port=19100 + 100*i, attempt_directory=str(directory), status="running"))
            state["attempts"][-1]["fixture_result"] = result
            save_json(directory / "result.json", result)
            state["attempts"][-1]["result_sha256"] = file_hash(directory / "result.json")
        # Register the higher global index first to model out-of-order completion.
        for attempt in reversed(state["attempts"]):
            batch.register_completion(state, attempt, attempt.pop("fixture_result"))
        state["completed"] = True
        batch._save_state(self.root, state)
        return plan, state

    def finalizer_inputs(self, plan):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(batch, "load_plan", return_value=plan))
        stack.enter_context(patch.object(batch, "integrity"))
        return stack

    def test_global_order_split_bindings_and_unified_pipeline_keep_quality_failure(self):
        plan, state = self.mock_batch()
        stack = self.finalizer_inputs(plan)
        stack.enter_context(patch.object(batch, "_default_verifier", side_effect=lambda p, a, r: r))
        events = []
        rows = [a["result"] for a in state["attempts"]]

        def export(paths, output, *, salt, analysis_selections):
            events.append("export")
            self.assertEqual(paths, [r["run_directory"] for r in rows])
            self.assertEqual(salt, "explicit-salt")
            self.assertEqual(analysis_selections, {r["run_directory"]: dict(
                directory=r["analysis_directory"], manifest_sha256=file_hash(
                    Path(r["analysis_directory"]) / "manifest.json")) for r in rows})
            output.mkdir()
            manifest = dict(episodes=[dict(run_id=r["run_id"], directory=f"episodes/{r['run_id']}",
                split=plan["tasks"][i]["split"], episode_quality_eligible=r["episode_quality_eligible"])
                for i, r in enumerate(rows)])
            save_json(output / "dataset_manifest.json", manifest)
            return manifest

        def audit(path, *, generation_manifest, attempt_ledger):
            events.append("audit")
            self.assertEqual(path, self.root / "dataset")
            self.assertEqual(generation_manifest, self.root / "bundle/generation_manifest.json")
            recorded = batch.read(attempt_ledger)
            self.assertEqual([m["mission_id"] for m in recorded["missions"]], ["m0", "m1"])
            self.assertEqual(recorded["missions"][0]["attempts"][0]["run_status"], "failed")
            return dict(issues=["nonblocking diagnostic"], family_split_leaks={})

        def describe(dataset, language):
            events.append("describe")
            self.assertEqual(dataset, self.root / "dataset")
            language.mkdir()
            save_json(language / "language_manifest.json", dict(
                dataset_manifest_sha256=file_hash(dataset / "dataset_manifest.json")))

        def load(path, *, verify_hashes):
            events.append("load:" + path.name)
            self.assertTrue(verify_hashes)
            return dict(t_s=[0], agent_ids=["uav_01"])

        stack.enter_context(patch("swarm_sim.dataset.build_dataset", side_effect=export))
        stack.enter_context(patch("swarm_sim.dataset_audit.audit_dataset", side_effect=audit))
        language = stack.enter_context(patch("swarm_sim.language_v0.describe_dataset", side_effect=describe))
        stack.enter_context(patch("scripts.run_v05c_pp._description_gate", side_effect=lambda *a:
            (events.append("description_gate") or dict(consistency_pass=True))))
        stack.enter_context(patch("swarm_sim.episode_loader.load_episode", side_effect=load))
        stack.enter_context(patch("swarm_sim.episode_loader.load_public_scene", return_value=[0]*4))
        diagnostics = stack.enter_context(patch.object(batch, "patrol_diagnostics", return_value={"groups": []}))
        report = batch.finalize(self.root)
        self.assertEqual(events, ["export", "audit", "describe", "description_gate", "load:r0", "load:r1"])
        language.assert_called_once()
        self.assertEqual(report["total"], 2)
        self.assertEqual([r["global_index"] for r in batch.read(self.root / "merged_records.json")], [0, 1])
        exported = batch.read(self.root / "dataset/dataset_manifest.json")["episodes"]
        self.assertEqual([r["episode_quality_eligible"] for r in exported], [False, True])
        self.assertEqual(batch.read(self.root / "control.json")["completion_order"], ["a000001", "a000000"])
        self.assertTrue(batch.read(self.root / "control.json")["finalized"])
        diagnostics.assert_called_once()
        self.assertEqual(report["patrol_timing"], {"groups": []})
        self.assertEqual(report["audit_issues"], ["nonblocking diagnostic"])

    def test_family_split_leakage_stops_finalization_before_descriptions_and_keeps_audit(self):
        plan, state = self.mock_batch()
        stack = self.finalizer_inputs(plan)
        stack.enter_context(patch.object(batch, "_default_verifier", side_effect=lambda p, a, r: r))
        manifest = dict(episodes=[dict(run_id=a["result"]["run_id"], directory=f"episodes/r{i}",
            split=plan["tasks"][i]["split"]) for i, a in enumerate(state["attempts"])])
        stack.enter_context(patch("swarm_sim.dataset.build_dataset", return_value=manifest))
        audit = dict(issues=["family appears in train and test"], family_split_leaks={"shared_family": ["train", "test"]})
        stack.enter_context(patch("swarm_sim.dataset_audit.audit_dataset", return_value=audit))
        language = stack.enter_context(patch("swarm_sim.language_v0.describe_dataset"))
        with self.assertRaisesRegex(ValueError, "family split leakage"):
            batch.finalize(self.root)
        language.assert_not_called()
        self.assertEqual(batch.read(self.root / "dataset_audit.json"), audit)
        stopped = batch.read(self.root / "control.json")
        self.assertFalse(stopped["finalized"])
        self.assertIn("P0 family split leakage", stopped["stopped_reason"])
        self.assertIn("invalidating generalization results", batch.read(self.root / "stop_report.json")["research_impact"])
        self.assertFalse((self.root / "final_report.json").exists())

    def test_missing_task_refuses_merge_before_any_export(self):
        plan, state = self.mock_batch()
        state["attempts"] = [state["attempts"][1]]
        state["completion_order"] = ["a000001"]
        batch._save_state(self.root, state)
        stack = self.finalizer_inputs(plan)
        stack.enter_context(patch.object(batch, "_default_verifier", side_effect=lambda p, a, r: r))
        exporter = stack.enter_context(patch("swarm_sim.dataset.build_dataset"))
        with self.assertRaisesRegex(ValueError, "missing tasks"):
            batch.finalize(self.root)
        exporter.assert_not_called()
        self.assertFalse((self.root / "dataset").exists())
        self.assertIn("missing tasks", batch.read(self.root / "control.json")["stopped_reason"])

    def test_export_error_preserves_partial_evidence_and_stopped_state(self):
        plan, _ = self.mock_batch()
        stack = self.finalizer_inputs(plan)
        stack.enter_context(patch.object(batch, "_default_verifier", side_effect=lambda p, a, r: r))

        def fail_export(paths, output, **kwargs):
            output.mkdir()
            (output / "partial-evidence.txt").write_text("retained", encoding="utf-8")
            raise OSError("disk full during export")

        stack.enter_context(patch("swarm_sim.dataset.build_dataset", side_effect=fail_export))
        language = stack.enter_context(patch("swarm_sim.language_v0.describe_dataset"))
        with self.assertRaisesRegex(OSError, "disk full"):
            batch.finalize(self.root)
        language.assert_not_called()
        state = batch.read(self.root / "control.json")
        self.assertFalse(state["finalized"])
        self.assertIn("finalization infrastructure", state["stopped_reason"])
        self.assertTrue((self.root / "dataset/partial-evidence.txt").is_file())
        self.assertTrue((self.root / "merged_records.json").is_file())
        self.assertFalse((self.root / "final_report.json").exists())

    def test_real_synthetic_analysis_exports_audits_describes_and_loads_failed_run(self):
        plan, attempt, scene = fixture(self.root)
        plan.update(root=str(self.root), max_attempts=1, split_salt="integration-salt")
        plan["tasks"][0].update(global_index=0, shard_id=0,
            split=family_split(plan["tasks"][0]["family_id"], "integration-salt"))
        attempt.update(global_index=0, shard_id=0, attempt_id="a000000", base_port=19100,
                       attempt_directory=str(self.root / "shards/shard_00/attempts/a000000"))
        with patch("scripts.run_mission_list.run_mission_list", side_effect=synthetic_runner(plan, scene)):
            result = worker.execute_attempt(plan, attempt)
        self.assertIsNone(result["infrastructure_error"])
        plan["protocol"] = result["semantic_protocol"]
        result_path = Path(attempt["attempt_directory"]) / "result.json"
        save_json(result_path, result)
        attempt["result_sha256"] = file_hash(result_path)
        state = batch.new_state(plan)
        state["attempts"].append(attempt)
        batch.register_completion(state, attempt, result)
        state["completed"] = True
        batch._save_state(self.root, state)
        self.finalizer_inputs(plan)
        report = batch.finalize(self.root)
        dataset = batch.read(self.root / "dataset/dataset_manifest.json")
        self.assertEqual(dataset["counts"]["total"], 1)
        self.assertEqual(dataset["counts"]["failed_runs"], 1)
        episode = dataset["episodes"][0]
        self.assertFalse(episode["episode_quality_eligible"])
        self.assertEqual(episode["split"], plan["tasks"][0]["split"])
        self.assertEqual(episode["analysis_selection_mode"], "explicit_manifest_binding")
        self.assertEqual(episode["source_analysis_path"], result["analysis_directory"])
        self.assertEqual(batch.read(self.root / "dataset_audit.json")["counts"]["episodes"], 1)
        language = batch.read(self.root / "language/language_manifest.json")
        self.assertEqual(language["skipped_episodes"], 1)
        self.assertEqual(language["descriptions"], 0)
        self.assertEqual(language["dataset_manifest_sha256"], file_hash(self.root / "dataset/dataset_manifest.json"))
        self.assertTrue(report["description_check"]["consistency_pass"])
        self.assertEqual([r["run_id"] for r in report["loaded"]], [result["run_id"]])
        self.assertEqual(report["loaded"][0]["corners"], 4)
        self.assertTrue(batch.read(self.root / "control.json")["finalized"])

    def test_out_of_order_completion_preserves_export_order_and_manifest_hash(self):
        plan, _, first_scene = fixture(self.root)
        plan.update(root=str(self.root), max_attempts=2, split_salt="completion-order-salt")
        bundle = Path(plan["bundle"])
        second_task = batch.read(bundle / "task.json")
        second_task.pop("family_id")
        second_task.pop("family_scheme")
        second_task["task_id"] += "_second_family"
        second_task["scenario"]["world"]["east_bounds_m"][1] += 1
        second_scene = compile_task(second_task)
        self.assertNotEqual(first_scene["family_id"], second_scene["family_id"])
        save_json(bundle / "task_second.json", second_task)
        save_json(bundle / "scene_second.json", second_scene)
        first_entry = plan["tasks"][0]["entry"]
        second_entry = dict(first_entry, mission_id="second_frozen_mission",
            family_id=second_scene["family_id"], task="task_second.json", scene="scene_second.json",
            task_sha256=file_hash(bundle / "task_second.json"),
            scene_sha256=file_hash(bundle / "scene_second.json"))
        listing = batch.read(bundle / "mission_list.json")
        listing["missions"].append(second_entry)
        save_json(bundle / "mission_list.json", listing)
        save_json(bundle / "generation_manifest.json", dict(artifact_sha256={
            path.name: file_hash(path) for path in bundle.glob("*.json")
            if path.name != "generation_manifest.json"}))
        plan["tasks"] = [dict(global_index=i, shard_id=i, mission_id=entry["mission_id"],
            family_id=entry["family_id"], split=family_split(entry["family_id"], plan["split_salt"]),
            entry=entry) for i, entry in enumerate((first_entry, second_entry))]
        attempts, results = [], []
        # Deliberately oppose lexical run-id order to the frozen global order.
        expected_run_ids = ["z_global_first", "a_global_second"]
        for i, scene in enumerate((first_scene, second_scene)):
            task = plan["tasks"][i]
            attempt = dict(attempt_id=f"a{i:06d}", attempt_index=0, global_index=i, shard_id=i,
                mission_id=task["mission_id"], family_id=task["family_id"], base_port=19100+100*i,
                attempt_directory=str(self.root / "shards" / f"shard_{i:02d}" / "attempts" / f"a{i:06d}"))
            runner = synthetic_runner(dict(plan, tasks=[task]), scene)

            def identified_runner(path, **kwargs):
                ledger = runner(path, **kwargs)
                run = Path(ledger["missions"][0]["attempts"][0]["run_directory"])
                metadata = batch.read(run / "metadata.json")
                metadata["run_id"] = expected_run_ids[i]
                save_json(run / "metadata.json", metadata)
                return ledger

            # Only the simulator boundary is replaced; production analysis,
            # result verification, merging and dataset export all execute.
            with patch("scripts.run_mission_list.run_mission_list", side_effect=identified_runner):
                result = worker.execute_attempt(plan, attempt)
            self.assertIsNone(result["infrastructure_error"])
            plan["protocol"] = result["semantic_protocol"]
            result_path = Path(attempt["attempt_directory"]) / "result.json"
            save_json(result_path, result)
            attempt["result_sha256"] = file_hash(result_path)
            attempts.append(attempt)
            results.append(result)

        frozen_plan_hash = canonical_hash(plan)
        manifests = []
        for name, order in (("ordered", [0, 1]), ("reversed", [1, 0])):
            state = batch.new_state(plan)
            state["attempts"] = [copy.deepcopy(attempts[i]) for i in order]
            for attempt in state["attempts"]:
                batch.register_completion(state, attempt, results[attempt["global_index"]])
            state["completed"] = True
            control_path = self.root / f"{name}_control.json"
            save_json(control_path, state)
            persisted = batch.read(control_path)
            self.assertEqual(persisted["completion_order"], [f"a{i:06d}" for i in order])
            self.assertEqual([a["completion_seq"] for a in persisted["attempts"]], [1, 2])
            self.assertIsNone(persisted["stopped_reason"])
            rows = batch.merge_records(plan, persisted)
            self.assertEqual([r["global_index"] for r in rows], [0, 1])
            self.assertEqual([r["run_id"] for r in rows], expected_run_ids)
            output = self.root / f"dataset_{name}"
            exported = build_dataset([r["run_directory"] for r in rows], output,
                salt=plan["split_salt"], analysis_selections={r["run_directory"]: dict(
                    directory=r["analysis_directory"], manifest_sha256=file_hash(
                        Path(r["analysis_directory"]) / "manifest.json")) for r in rows})
            self.assertEqual([e["run_id"] for e in exported["episodes"]], expected_run_ids)
            self.assertEqual([e["split"] for e in exported["episodes"]],
                             [task["split"] for task in plan["tasks"]])
            manifests.append(output / "dataset_manifest.json")

        # Export roots do not enter the manifest. Both exports read exactly the
        # same immutable run/analysis paths, so only completion order can differ.
        self.assertEqual(manifests[0].read_bytes(), manifests[1].read_bytes())
        self.assertEqual(file_hash(manifests[0]), file_hash(manifests[1]))
        self.assertEqual(canonical_hash(plan), frozen_plan_hash)
        for result in results:
            self.assertTrue(all(file_hash(Path(path)) == digest
                                for path, digest in result["evidence_sha256"].items()))

    def test_patrol_timing_uses_primary_phase_and_separates_unknown_denominators(self):
        bundle = self.root / "bundle"
        bundle.mkdir()
        save_json(bundle / "scene.json", dict(task_spec=dict(mission=dict(intent="patrol")),
            semantic_plan=dict(execution_phases=dict(survey=dict(semantic_phase="patrol")))))
        tasks, rows = [], []
        for i, value in enumerate((10, 30, None)):
            analysis = self.root / f"analysis{i}"
            analysis.mkdir()
            primary = dict(D_s=value, tau_s=15, complete=value is not None)
            save_json(analysis / "ac4_timing_v3.json", dict(channels={channel: dict(
                per_phase=dict(survey=dict(primary=primary, per_agent=dict(ignored=dict(D_s=9999)))))
                for channel in ("truth", "observation")}))
            tasks.append(dict(global_index=i, entry=dict(scene="scene.json")))
            rows.append(dict(run_id=f"r{i}", analysis_directory=str(analysis)))
        report = batch.patrol_diagnostics(dict(tasks=tasks, bundle=str(bundle)), rows)
        self.assertEqual(len(report["records"]), 6)
        self.assertEqual(len(report["groups"]), 2)
        for group in report["groups"]:
            self.assertEqual(group["scope"], "batch")
            self.assertEqual((group["expected"], group["known"], group["unknown"]), (3, 2, 1))
            self.assertEqual((group["median_s"], group["max_s"]), (20, 30))
            self.assertEqual(group["exceeded"], dict(numerator=1, denominator=2, fraction=0.5))

    def test_cli_missing_sim_data_root_exits_without_creating_output(self):
        output, error = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(output), redirect_stderr(error), \
                patch.object(cli, "batch_directory") as directory, patch.object(cli, "prepare") as prepare:
            with self.assertRaises(SystemExit) as raised:
                cli.main(["prepare", "--profile", "unused.json", "--batch-id", "unused",
                          "--max-attempts", "1", "--storage-bytes-per-attempt", "1", "--export-reserve-bytes", "1"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("SIM_DATA_ROOT", error.getvalue())
        self.assertEqual(output.getvalue(), "")
        directory.assert_not_called()
        prepare.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_duplicate_worker_started_marker_prevents_reflight_after_lock_release(self):
        plan, state = self.mock_batch()
        attempt = state["attempts"][0]
        attempt.update(status="running")
        for key in ("result", "completion_seq", "finished_utc", "completed_after_stop"):
            attempt.pop(key, None)
        (Path(attempt["attempt_directory"]) / "result.json").unlink()
        attempt.pop("result_sha256", None)
        state.update(completed=False, completion_order=["a000001"])
        marker = Path(attempt["attempt_directory"]) / "started.json"
        save_json(marker, dict(attempt_id=attempt["attempt_id"]))
        batch._save_state(self.root, state)
        # Workers read their per-attempt assignment, never control.json.
        plan.update(shards=2, batch_id="offline")
        batch.write_assignment(plan, attempt)
        with patch.object(cli, "load_plan", return_value=plan), \
                patch("swarm_sim.parallel_worker.execute_attempt") as execute:
            with self.assertRaises(FileExistsError):
                cli.worker(self.root, attempt["attempt_id"])
        execute.assert_not_called()
        self.assertTrue(marker.is_file())
        self.assertFalse((marker.parent / "result.json").exists())


if __name__ == "__main__":
    unittest.main()
