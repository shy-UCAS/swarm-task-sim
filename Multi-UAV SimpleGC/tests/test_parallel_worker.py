"""Offline v0.6 adapter tests: real analysis over synthetic source evidence."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swarm_sim import parallel_worker as worker
from swarm_sim.generation import file_hash, save_json
from swarm_sim.quality import policy_hash, resolve_policy
from swarm_sim.run_provenance import PARAMETER_COMPARISON_VERSION
from swarm_sim.tasks import compile_task
from swarm_sim.validation_policy_r12b import assess_recent_runs


PROJECT = Path(__file__).resolve().parents[1]


def fixture(root):
    """Freeze one real compiled TaskSpec; write no simulator output."""
    bundle = root / "bundle"
    bundle.mkdir()
    task = json.loads((PROJECT / "missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8"))
    task["execution"]["async_timing_tolerance"]["max_s"] = 30.0
    scene = compile_task(task)
    save_json(bundle / "task.json", task)
    save_json(bundle / "scene.json", scene)
    save_json(bundle / "generation_profile.json", dict(master_seed=73))
    entry = dict(mission_id="frozen_mission", family_id=task["family_id"], status="planned",
        task="task.json", scene="scene.json", task_sha256=file_hash(bundle / "task.json"),
        scene_sha256=file_hash(bundle / "scene.json"))
    save_json(bundle / "mission_list.json", dict(missions=[entry],
        generation_profile_sha256=file_hash(bundle / "generation_profile.json")))
    save_json(bundle / "generation_manifest.json", dict(artifact_sha256={
        path.name: file_hash(path) for path in bundle.glob("*.json")}))
    binary, parameters = root / "firmware.bin", root / "parameters.parm"
    binary.write_bytes(b"ArduCopter V4.5.7\x00")
    parameters.write_text("TEST=1\n", encoding="utf-8")
    plan = dict(project_root=str(PROJECT), bundle=str(bundle), quality_policy=resolve_policy(),
        quality_policy_sha256=policy_hash(resolve_policy()), binary=str(binary), parameters=str(parameters),
        firmware=dict(sha256=file_hash(binary), version_string="ArduCopter V4.5.7"),
        parameters_sha256=file_hash(parameters), tasks=[dict(global_index=7, shard_id=1,
            mission_id=entry["mission_id"], family_id=entry["family_id"], entry=entry)])
    attempt = dict(attempt_id="attempt_007_0", attempt_index=0, global_index=7, shard_id=1,
        mission_id=entry["mission_id"], family_id=entry["family_id"], base_port=19200,
        attempt_directory=str(root / "shards/shard_01/attempts/attempt_007_0"))
    return plan, attempt, scene


def synthetic_runner(plan, scene, *, status="failed", preflight=False, mismatch=False):
    """Fake only the flight runner. Formal production analysis remains real."""
    def run(path, **kwargs):
        output = Path(kwargs["output_root"])
        directory = output / "attempts/inner/run_evidence"
        directory.mkdir(parents=True)
        agents = [vehicle["id"] for vehicle in scene["vehicles"]]
        metadata = dict(version="0.5.0-dev", run_id="synthetic_run_7", scenario=scene,
            status=status, run_epoch_monotonic_s=100.0, elapsed_s=0.1,
            quality_policy_sha256=plan["quality_policy_sha256"],
            binary_firmware=plan["firmware"], parameters_sha256=plan["parameters_sha256"],
            cleanup={agent: 0 for agent in agents}, parameter_comparison_version=PARAMETER_COMPARISON_VERSION,
            error="connection refused" if preflight else "mission execution failed after takeoff")
        if mismatch:
            metadata["error"] = "unexplained parameter readback differences require review/new WP-S GO"
        if preflight:
            metadata["run_provenance"] = dict(status="files_verified")
            parameters = {agent: dict(status="not_started", complete=False, received_count=0,
                parameter_comparison=dict(status="not_evaluated")) for agent in agents}
        else:
            metadata["flight_epoch_monotonic_s"] = 100.0
            readback = {agent: dict(complete=True, status="complete", received_count=1,
                parameter_count=1, missing_indices=[]) for agent in agents}
            metadata["run_provenance"] = dict(status="verified_before_takeoff",
                parameter_comparison_version=PARAMETER_COMPARISON_VERSION,
                parameter_evidence=dict(per_agent=readback))
            parameters = {agent: dict(status="complete", complete=True,
                parameter_comparison=dict(status="evaluated", collection_complete=True, **{"pass": True}))
                for agent in agents}
        save_json(directory / "metadata.json", metadata)
        save_json(directory / "scenario.json", scene)
        save_json(directory / "firmware_parameters.json", parameters)
        (directory / "events.jsonl").write_text(json.dumps(dict(event="run_failed")) + "\n", encoding="utf-8")
        bundle = Path(plan["bundle"])
        for name in ("generation_profile", "generation_manifest"):
            save_json(directory / (name + ".json"), worker._read(bundle / (name + ".json")))
        save_json(directory / "generation_entry.json", plan["tasks"][0]["entry"])
        context = dict(selected_mission_ids=kwargs["mission_ids"], base_port=kwargs["base_port"],
            max_environment_retries=kwargs["max_environment_retries"], retryable_errors=list(kwargs["retryable_errors"]),
            mission_list_sha256=file_hash(bundle / "mission_list.json"),
            generation_manifest_sha256=file_hash(bundle / "generation_manifest.json"),
            quality_policy_sha256=plan["quality_policy_sha256"], binary_sha256=plan["firmware"]["sha256"],
            parameters_sha256=plan["parameters_sha256"])
        ledger = dict(execution_context=context, missions=[dict(mission_id=kwargs["mission_ids"][0],
            attempts=[dict(status="execution_failed", run_directory=str(directory))])])
        save_json(output / "attempt_ledger.json", ledger)
        return ledger
    return run


class ParallelWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.plan, self.attempt, self.scene = fixture(Path(self.temporary.name))

    def execute(self, **kwargs):
        with patch("scripts.run_mission_list.run_mission_list",
                   side_effect=synthetic_runner(self.plan, self.scene, **kwargs)) as runner:
            result = worker.execute_attempt(self.plan, self.attempt)
        return result, runner

    def test_selected_single_attempt_has_isolated_directory_and_formal_versions(self):
        result, runner = self.execute()
        self.assertIsNone(result["infrastructure_error"])
        runner.assert_called_once()
        arguments = runner.call_args.kwargs
        self.assertEqual(arguments["mission_ids"], ["frozen_mission"])
        self.assertEqual(arguments["max_runs"], 1)
        self.assertFalse(arguments["resume"])
        self.assertEqual(arguments["max_environment_retries"], 0)
        self.assertEqual(arguments["retryable_errors"], ())
        self.assertEqual(arguments["base_port"], 19200)
        self.assertEqual(arguments["output_root"], Path(self.attempt["attempt_directory"]) / "run")
        self.assertEqual(result["analysis_directory"], str(Path(self.attempt["attempt_directory"]) / "analysis"))
        self.assertEqual(result["semantic_protocol"]["semantic_validation_version"], "multi_intent_validation_v3")
        self.assertEqual(result["progress_mapping_version"], worker.PROGRESS_VERSION)
        self.assertEqual(result["patrol_validator_version"], worker.PATROL_VERSION)
        self.assertEqual(result["acceptance_policy_version"], worker.POLICY_VERSION)
        self.assertEqual(worker.verify_result(self.plan, self.attempt, result), result)

    def test_failed_run_complete_analysis_is_retained_as_one_quality_anomaly(self):
        result, _ = self.execute()
        self.assertEqual(result["run_status"], "failed")
        self.assertEqual(result["hard_failures"], [])
        self.assertIsNone(result["infrastructure_error"])
        self.assertFalse(result["episode_quality_eligible"])
        self.assertTrue(Path(result["analysis_directory"], "quality.json").is_file())
        rolling = assess_recent_runs([result], stage="batch")
        self.assertEqual(rolling["anomaly_count"], 1)
        self.assertFalse(rolling["stop"])

    def test_analysis_error_or_missing_artifact_is_infrastructure_stop(self):
        with patch("scripts.run_mission_list.run_mission_list", side_effect=synthetic_runner(self.plan, self.scene)), \
                patch("swarm_sim.analysis_v3.analyze_run_v3", side_effect=ValueError("analysis failed")):
            result = worker.execute_attempt(self.plan, self.attempt)
        self.assertIn("analysis failed", result["infrastructure_error"])
        self.assertFalse(result["retryable_pre_takeoff"])
        self.assertTrue(result["evidence_sha256"])
        self.assertEqual(worker.verify_result(self.plan, self.attempt, result), result)
        # A missing formal artifact after a normal result is never accepted.
        with tempfile.TemporaryDirectory() as temp:
            plan, attempt, scene = fixture(Path(temp))
            with patch("scripts.run_mission_list.run_mission_list", side_effect=synthetic_runner(plan, scene)):
                normal = worker.execute_attempt(plan, attempt)
            Path(normal["analysis_directory"], "quality.json").unlink()
            with self.assertRaisesRegex(ValueError, "evidence hashes"):
                worker.verify_result(plan, attempt, normal)

    def test_source_mutation_and_omitted_evidence_hash_are_rejected(self):
        result, _ = self.execute()
        omitted = copy.deepcopy(result)
        omitted["evidence_sha256"].pop(next(iter(omitted["evidence_sha256"])))
        with self.assertRaisesRegex(ValueError, "evidence hashes"):
            worker.verify_result(self.plan, self.attempt, omitted)
        Path(result["run_directory"], "events.jsonl").write_text("\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "evidence hashes"):
            worker.verify_result(self.plan, self.attempt, result)

    def test_forged_outcome_and_cross_shard_path_are_rejected(self):
        result, _ = self.execute()
        forged = copy.deepcopy(result)
        forged["assessment"]["aggregate_anomaly"] = False
        with self.assertRaisesRegex(ValueError, "independent evidence"):
            worker.verify_result(self.plan, self.attempt, forged)
        forged = dict(result, run_directory=str(Path(self.temporary.name) / "shards/shard_00/run"))
        with self.assertRaisesRegex(ValueError, "escapes"):
            worker.verify_result(self.plan, self.attempt, forged)

    def test_only_proven_pre_takeoff_transient_failure_is_retryable(self):
        result, _ = self.execute(preflight=True)
        self.assertIsNone(result["infrastructure_error"])
        self.assertEqual(result["hard_failures"], [])
        self.assertTrue(result["retryable_pre_takeoff"])
        self.assertEqual(result["retry_reason"], "connection_failure_before_takeoff")
        self.assertFalse(result["flight_epoch_present"])
        # Stored acceptance stays unchanged; absence of a completed readback is
        # not silently rewritten to a pass by the controller-facing assessment.
        self.assertFalse(result["assessment"]["hard_checks"]["parameter_firmware"])
        self.assertIsNone(result["batch_hard_checks"]["parameter_firmware"])

    def test_confirmed_preflight_parameter_mismatch_is_not_retried(self):
        result, _ = self.execute(preflight=True, mismatch=True)
        self.assertIsNone(result["infrastructure_error"])
        self.assertFalse(result["retryable_pre_takeoff"])
        self.assertIn("parameter_firmware", result["hard_failures"])

    def test_interrupted_attempt_cannot_automatically_relaunch(self):
        result, _ = self.execute(status="interrupted")
        self.assertIn("interrupted attempt", result["infrastructure_error"])
        self.assertFalse(result["retryable_pre_takeoff"])
        with patch("scripts.run_mission_list.run_mission_list") as runner:
            with self.assertRaisesRegex(ValueError, "never automatically rerun"):
                worker.execute_attempt(self.plan, self.attempt)
        runner.assert_not_called()

    def test_frozen_firmware_and_task_changes_prevent_launch(self):
        for mutation in (lambda p: p["tasks"][0]["entry"].update(scene_sha256="0" * 64),
                         lambda p: p["firmware"].update(sha256="0" * 64)):
            plan = copy.deepcopy(self.plan)
            mutation(plan)
            with patch("scripts.run_mission_list.run_mission_list") as runner, self.assertRaises(ValueError):
                worker.execute_attempt(plan, self.attempt)
            runner.assert_not_called()

    def test_wrong_formal_protocol_is_rejected_even_after_rehash(self):
        result, _ = self.execute()
        path = Path(result["analysis_directory"]) / "manifest.json"
        manifest = worker._read(path)
        manifest["route_progress_version"] = "ordered_route_progress_v1"
        save_json(path, manifest)
        result["evidence_sha256"][str(path)] = file_hash(path)
        with self.assertRaisesRegex(ValueError, "protocol or policy"):
            worker.verify_result(self.plan, self.attempt, result)

    def test_rehashed_generation_provenance_is_checked_against_full_bundle(self):
        result, _ = self.execute()
        path = Path(result["run_directory"]) / "generation_entry.json"
        changed = worker._read(path)
        changed["seed"] = 987
        save_json(path, changed)
        manifest_path = Path(result["analysis_directory"]) / "manifest.json"
        manifest = worker._read(manifest_path)
        manifest["source_sha256"][path.name] = file_hash(path)
        save_json(manifest_path, manifest)
        result["evidence_sha256"].update({str(p): file_hash(p) for p in (path, manifest_path)})
        with self.assertRaisesRegex(ValueError, "generation provenance"):
            worker.verify_result(self.plan, self.attempt, result)

    def test_confirmed_hard_failures_and_analysis_error_are_distinct_from_unknown(self):
        result, _ = self.execute()
        metadata = worker._read(Path(result["run_directory"]) / "metadata.json")
        artifacts = {name: worker._read(Path(result["analysis_directory"]) / (name + ".json"))
                     for name in worker.ARTIFACTS}

        def assessed(changed):
            changed["quality"]["validation_policy"] = worker.assess_run(self.scene, metadata,
                changed["quality"], changed["labels"], changed["execution_metrics"], changed["ac4_timing_v3"],
                changed["onboard_mission_param_check"], stage="batch")
            return worker.assess_artifacts(self.scene, metadata, changed, self.plan)

        for minimum, expected in ((4.99, False), (None, None), (9.0, None)):
            changed = copy.deepcopy(artifacts)
            changed["quality"]["truth_separation"] = dict(status="risk", minimum_m=minimum)
            checked = assessed(changed)
            self.assertIs(checked["batch_hard_checks"]["truth_separation"], expected)
            self.assertEqual("truth_separation" in checked["hard_failures"], expected is False)
        changed = copy.deepcopy(artifacts)
        changed["onboard_mission_param_check"].update(status="mismatch", counts=dict(mismatch_count=1))
        self.assertIn("onboard_mission_parameters", assessed(changed)["hard_failures"])
        changed = copy.deepcopy(artifacts)
        changed["quality"]["analysis_error"] = "synthetic structured analysis error"
        checked = assessed(changed)
        self.assertIn("analysis_error", checked["infrastructure_error"])
        self.assertIn("infrastructure_execution_completed", checked["hard_failures"])

    def test_quality_failure_and_unknown_do_not_stop_but_confirmed_violation_does(self):
        from scripts.run_v05_batch import assess_artifacts as v05_assess_artifacts
        from swarm_sim.parallel_batch import new_state, register_completion

        result, _ = self.execute()
        metadata = worker._read(Path(result["run_directory"]) / "metadata.json")
        artifacts = {name: worker._read(Path(result["analysis_directory"]) / (name + ".json"))
                     for name in worker.ARTIFACTS}
        cases = (
            ("quality_only", "clear_observed", 9.0, "pass", 0, True, None),
            ("unknown", "risk", None, "unknown", 0, None, None),
            ("confirmed_separation", "risk", 4.99, "unknown", 0, False, "truth_separation"),
            ("confirmed_onboard", "clear_observed", 9.0, "mismatch", 1, True, "onboard_mission_parameters"),
        )
        for name, status, minimum, onboard, mismatches, separation_check, stop_key in cases:
            with self.subTest(case=name):
                changed = copy.deepcopy(artifacts)
                changed["quality"].update(episode_quality_eligible=False,
                    truth_separation=dict(status=status, minimum_m=minimum))
                changed["onboard_mission_param_check"].update(status=onboard,
                    pass_gate=onboard == "pass", counts=dict(mismatch_count=mismatches))
                changed["quality"]["validation_policy"] = worker.assess_run(self.scene, metadata,
                    changed["quality"], changed["labels"], changed["execution_metrics"],
                    changed["ac4_timing_v3"], changed["onboard_mission_param_check"], stage="batch")
                checked = worker.assess_artifacts(self.scene, metadata, changed, self.plan)
                legacy = v05_assess_artifacts(self.scene, metadata, changed, self.plan)
                for key in ("batch_hard_checks", "hard_failures", "assessment"):
                    self.assertEqual(checked[key], legacy[key])
                self.assertIs(checked["batch_hard_checks"]["truth_separation"], separation_check)
                if onboard == "unknown":
                    self.assertIsNone(checked["batch_hard_checks"]["onboard_mission_parameters"])
                self.assertIsNone(checked["infrastructure_error"])
                state, attempt = new_state(self.plan), copy.deepcopy(self.attempt)
                state["attempts"].append(attempt)
                register_completion(state, attempt, dict(checked, run_id=result["run_id"]))
                self.assertEqual(state["rolling"]["window_count"], 1)
                self.assertEqual(state["rolling"]["anomaly_count"], 1)
                self.assertFalse(state["rolling"]["stop"])
                if stop_key:
                    self.assertIn(stop_key, state["stopped_reason"])
                    self.assertEqual(state["stop_attempt_id"], attempt["attempt_id"])
                else:
                    self.assertEqual(checked["hard_failures"], [])
                    self.assertIsNone(state["stopped_reason"])
                    self.assertIsNone(state["stop_attempt_id"])


if __name__ == "__main__":
    unittest.main()
