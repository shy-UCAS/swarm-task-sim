"""Batch-only hard gates, immutable pilot inclusion and bounded offline execution."""
import copy
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_v05_batch as batch


def assessment(reasons=()):
    return dict(version=batch.POLICY_VERSION, stage="batch", aggregate_anomaly=bool(reasons),
        aggregate_anomaly_reasons=list(reasons), hard_checks=dict(parameter_firmware=True,
        onboard_mission_parameters=True, truth_separation=True), hard_failures=[],
        soft_flags=[dict(code="AC4", status="exceeded", value=50)], semantic_flags=[],
        new_anomalies=[], individual_pass=True, episode_quality_eligible=True)


def row(index, *, pilot=False, reasons=()):
    base = index // 2 + (0 if pilot else 10)
    return dict(logical_index=index, attempt_index=0, run_id=f"run_{base:03d}_{index % 2}",
        mission_id=f"mission_{base:03d}_{index % 2}", base_index=base,
        intent=batch.INTENT_ORDER[index % 2], retryable_pre_takeoff=False, qualified=True,
        episode_quality_eligible=True, mission_success=not bool(reasons),
        mission_success_observation=True, semantic_consistency="agree",
        assessment=assessment(reasons), hard_failures=[], soft_flags=[], evidence_sha256={},
        run_directory=f"source/{base:03d}_{index % 2}", analysis_directory=f"external/{base:03d}_{index % 2}",
        runner_status="succeeded", run_status="completed")


def control(count=0):
    return dict(version=batch.VERSION, stage="batch", acceptance_policy=batch.POLICY_VERSION,
        max_attempts=264, max_extra_retries=24, hold_s=0,
        progress_mapping_version=batch.PROGRESS_VERSION, patrol_validator_version=batch.PATROL_VERSION,
        bundle=str(batch.ROOT_OUTPUT / "bundle"), pilot_control=str(batch.PILOT_CONTROL),
        planned_missions=[row(i)["mission_id"] for i in range(240)],
        records=[row(i) for i in range(count)], pilot_records=[row(i, pilot=True) for i in range(20)],
        active_attempt=None, stopped_reason=None, completed=False, finalized=False,
        binary="binary", parameters="parameters", quality_policy={},
        firmware=dict(sha256="firmware", version_string="version"), parameters_sha256="parameters",
        storage_estimate=dict(max_run_bytes=100, max_analysis_bytes=20,
            max_episode_bytes=30, language_bytes_per_episode=1))


class BatchGatesTests(unittest.TestCase):
    def artifacts(self):
        scene = dict(vehicles=[dict(id="uav_01")], min_separation_m=8)
        metadata = dict(binary_firmware=dict(sha256="firmware", version_string="version"),
            parameters_sha256="parameters", cleanup=dict(uav_01=0), status="completed")
        artifacts = dict(quality=dict(episode_quality_eligible=True,
            truth_separation=dict(status="clear_observed", minimum_m=9), validation_policy=assessment()),
            labels=dict(mission_success=True, mission_success_observation=True, semantic_consistency="agree"),
            execution_metrics={}, ac4_timing_v3={},
            onboard_mission_param_check=dict(status="pass", pass_gate=True, counts=dict(mismatch_count=0)))
        return scene, metadata, artifacts

    def assess(self, scene, metadata, artifacts):
        stored = copy.deepcopy(artifacts["quality"]["validation_policy"])
        with patch.object(batch, "assess_run", return_value=copy.deepcopy(stored)):
            result = batch.assess_artifacts(scene, metadata, artifacts, control())
        self.assertEqual(artifacts["quality"]["validation_policy"], stored)
        self.assertEqual(result["assessment"], stored)
        return result

    def test_execution_soft_flags_never_stop_or_change_stored_policy(self):
        result = self.assess(*self.artifacts())
        self.assertEqual(result["hard_failures"], [])
        self.assertTrue(result["episode_quality_eligible"])
        self.assertEqual(result["soft_flags"][0]["code"], "AC4")

    def test_quality_false_or_unknown_is_preserved_without_single_run_stop(self):
        for value in (False, None):
            scene, metadata, artifacts = self.artifacts()
            artifacts["quality"]["episode_quality_eligible"] = value
            result = self.assess(scene, metadata, artifacts)
            self.assertEqual(result["hard_failures"], [])
            self.assertIs(result["episode_quality_eligible"], value)

    def test_failed_run_with_complete_analysis_does_not_stop_and_counts_once(self):
        # 2026-10-03 authorized rule: an incomplete run with complete analysis
        # evidence is kept as an ineligible episode and counted by the rolling
        # rule instead of stopping the batch (B098 disposition).
        scene, metadata, artifacts = self.artifacts()
        metadata["status"] = "failed"
        artifacts["quality"]["episode_quality_eligible"] = False
        artifacts["quality"]["validation_policy"] = assessment(["episode_quality_ineligible"])
        result = self.assess(scene, metadata, artifacts)
        self.assertEqual(result["hard_failures"], [])
        self.assertEqual(result["run_status"], "failed")
        self.assertTrue(result["batch_hard_checks"]["infrastructure_execution_completed"])
        self.assertIs(result["episode_quality_eligible"], False)
        data, record = control(), row(0, reasons=["episode_quality_ineligible"])
        record.update(result, qualified=False, episode_quality_eligible=False)
        with tempfile.TemporaryDirectory() as tmp:
            batch.complete_record(data, record, tmp)
            self.assertFalse((Path(tmp) / "stop_report.md").exists())
        self.assertIsNone(data["stopped_reason"])
        self.assertEqual(data["rolling"]["anomaly_count"], 1)
        self.assertEqual(batch.next_mission(data), (1, 0))

    def test_analysis_error_still_stops_immediately(self):
        for status in ("completed", "failed"):
            scene, metadata, artifacts = self.artifacts()
            metadata["status"] = status
            artifacts["quality"]["analysis_error"] = "ValueError: analysis failed"
            result = self.assess(scene, metadata, artifacts)
            self.assertEqual(result["hard_failures"], ["infrastructure_execution_completed"])
            data, record = control(), row(0)
            record.update(result)
            with tempfile.TemporaryDirectory() as tmp:
                batch.complete_record(data, record, tmp)
            self.assertEqual(data["stopped_reason"], "infrastructure_execution_completed")

    def test_unknown_separation_is_not_a_pass_or_a_confirmed_violation(self):
        for separation in (dict(status="unknown", minimum_m=9), dict(status="clear_observed", minimum_m=None),
                           dict(status="risk", minimum_m=None), dict(status="risk", minimum_m=9)):
            scene, metadata, artifacts = self.artifacts()
            artifacts["quality"]["truth_separation"] = separation
            result = self.assess(scene, metadata, artifacts)
            self.assertIsNone(result["batch_hard_checks"]["truth_separation"])
            self.assertEqual(result["hard_failures"], [])

    def test_confirmed_separation_violation_stops_immediately(self):
        for status in ("risk", "unknown", "clear_observed"):
            scene, metadata, artifacts = self.artifacts()
            scene["min_separation_m"] = 5.0
            artifacts["quality"]["truth_separation"] = dict(status=status, minimum_m=4.99)
            result = self.assess(scene, metadata, artifacts)
            self.assertEqual(result["hard_failures"], ["truth_separation"])
            data, record = control(), row(0)
            record.update(result)
            with tempfile.TemporaryDirectory() as tmp:
                batch.complete_record(data, record, tmp)
            self.assertEqual(data["stopped_reason"], "truth_separation")

    def test_onboard_unknown_stays_unknown_and_confirmed_mismatch_stops(self):
        for status, count, expected in (("unknown", 0, None), ("mismatch", 1, False)):
            scene, metadata, artifacts = self.artifacts()
            artifacts["onboard_mission_param_check"] = dict(status=status, pass_gate=False,
                counts=dict(mismatch_count=count, unknown_count=24 if status == "unknown" else 0))
            artifacts["quality"]["validation_policy"]["hard_checks"]["onboard_mission_parameters"] = False
            result = self.assess(scene, metadata, artifacts)
            self.assertIs(result["batch_hard_checks"]["onboard_mission_parameters"], expected)
            data, record = control(), row(0)
            record.update(result)
            with tempfile.TemporaryDirectory() as tmp:
                batch.complete_record(data, record, tmp)
            self.assertEqual(data["stopped_reason"], "onboard_mission_parameters" if expected is False else None)

    def test_firmware_onboard_and_cleanup_are_independent_hard_checks(self):
        scene, metadata, artifacts = self.artifacts()
        metadata["binary_firmware"]["sha256"] = "different"
        metadata["cleanup"] = {}
        artifacts["quality"]["validation_policy"]["hard_checks"]["onboard_mission_parameters"] = False
        artifacts["onboard_mission_param_check"] = dict(status="mismatch", pass_gate=False,
            counts=dict(mismatch_count=1))
        result = self.assess(scene, metadata, artifacts)
        self.assertEqual(set(result["hard_failures"]), {
            "frozen_firmware_and_parameters", "infrastructure_cleanup_complete", "onboard_mission_parameters"})

    def test_preflight_parameter_firmware_failure_remains_immediate(self):
        scene, metadata, artifacts = self.artifacts()
        artifacts["quality"]["validation_policy"]["hard_checks"]["parameter_firmware"] = False
        data, record = control(), row(0)
        record.update(self.assess(scene, metadata, artifacts))
        with tempfile.TemporaryDirectory() as tmp:
            batch.complete_record(data, record, tmp)
        self.assertEqual(data["stopped_reason"], "parameter_firmware")

    def test_batch_window_starts_empty_and_fifth_unique_anomaly_stops(self):
        data = control()
        for record in data["pilot_records"]:
            record["assessment"] = assessment(["task_failure_truth"])
        self.assertEqual(batch.rolling_status(data)["window_count"], 0)
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(4):
                batch.complete_record(data, row(i, reasons=["task_failure_truth", "label_disagreement"]), tmp)
            self.assertIsNone(data["stopped_reason"])
            batch.complete_record(data, row(4, reasons=["task_failure_truth"]), tmp)
            self.assertTrue((Path(tmp) / "stop_report.md").is_file())
        self.assertEqual(data["rolling"]["anomaly_count"], 5)
        self.assertEqual(data["stopped_reason"], "rolling_anomalous_runs_at_least_5")

    def test_single_quality_failure_counts_once_without_stopping(self):
        data, record = control(), row(0, reasons=["episode_quality_ineligible"])
        record.update(episode_quality_eligible=False, qualified=False, mission_success=True)
        with tempfile.TemporaryDirectory() as tmp:
            batch.complete_record(data, record, tmp)
            self.assertFalse((Path(tmp) / "stop_report.md").exists())
        self.assertIsNone(data["stopped_reason"])
        self.assertEqual(data["rolling"]["anomaly_count"], 1)
        self.assertEqual(batch.next_mission(data), (1, 0))

    def test_recent_twenty_counts_quality_failure_and_deduplicates_multiple_conditions(self):
        data = control(20)
        # The old anomaly at index 0 leaves the window when index 20 arrives.
        for index in (0, 5, 10, 15, 19):
            data["records"][index]["assessment"] = assessment(["episode_quality_ineligible"])
        with tempfile.TemporaryDirectory() as tmp:
            batch.complete_record(data, row(20), tmp)
            self.assertEqual(data["rolling"]["anomaly_count"], 4)
            self.assertIsNone(data["stopped_reason"])
            record = row(21, reasons=["task_failure_truth", "label_disagreement", "episode_quality_ineligible"])
            batch.complete_record(data, record, tmp)
        self.assertEqual(data["rolling"]["window_count"], 20)
        self.assertEqual(data["rolling"]["anomaly_count"], 5)
        self.assertEqual(data["stopped_reason"], "rolling_anomalous_runs_at_least_5")

    def test_missing_output_directory_is_not_misclassified_as_integrity_failure(self):
        data = control()
        with tempfile.TemporaryDirectory() as tmp:
            batch.stop(data, tmp, "infrastructure_or_integrity_failure: FileNotFoundError: missing analyses directory")
        self.assertNotIn("冻结核对", data["research_impact"])
        self.assertIn("本次未完成", data["research_impact"])

    def test_next_cannot_retry_stop_or_exceed_mission_budget(self):
        self.assertEqual(batch.next_mission(control()), (0, 0))
        self.assertEqual(batch.next_mission(control(239)), (239, 0))
        for change in (dict(stopped_reason="failure"), dict(active_attempt={}), dict(completed=True),
                       dict(max_attempts=265)):
            data = control()
            data.update(change)
            with self.assertRaises(ValueError):
                batch.next_mission(data)
        for count in (240, 264):
            with self.assertRaises(ValueError):
                batch.next_mission(control(count))
        data = control(1)
        data["records"][0]["retryable_pre_takeoff"] = True
        with self.assertRaisesRegex(ValueError, "explicit recovery"):
            batch.next_mission(data)

    def test_disk_margins_are_two_before_batch_and_one_point_five_during(self):
        data = control(1)
        needed = 239 * 120 + 260 * 31
        with patch.object(batch.shutil, "disk_usage", return_value=SimpleNamespace(free=needed * 1.5)):
            self.assertTrue(batch.disk_status(data)["pass_gate"])
            self.assertFalse(batch.disk_status(data, initial=True)["pass_gate"])
        with patch.object(batch.shutil, "disk_usage", return_value=SimpleNamespace(free=needed * 2)):
            self.assertTrue(batch.disk_status(data, initial=True)["pass_gate"])

    def test_combined_records_include_130_pairs_without_rewriting_pilot(self):
        data = control(240)
        before = copy.deepcopy(data)
        combined = batch.combined_records(data)
        aggregate = batch.aggregate_status(combined)
        self.assertEqual(data, before)
        self.assertEqual([r["logical_index"] for r in combined], list(range(260)))
        self.assertEqual(aggregate["logical_completed"], 260)
        self.assertEqual(aggregate["pair_qualified"], 130)
        self.assertEqual(aggregate["by_intent"]["patrol"]["attempted"], 130)

    def test_final_acceptance_uses_full_dataset_denominators(self):
        aggregate = batch.aggregate_status(batch.combined_records(control(240)))
        manifest, audit = dict(episodes=[{}] * 260), dict(issues=[])
        descriptions, loaded = dict(consistency_pass=True), [dict(corner_count=4, corner_dimensions=[2] * 4)] * 260
        self.assertTrue(batch.acceptance_gates(aggregate, manifest, audit, descriptions, loaded)["pass"])
        aggregate.update(qualified=234, pair_qualified=111)
        self.assertTrue(batch.acceptance_gates(aggregate, manifest, audit, descriptions, loaded)["pass"])
        aggregate["pair_qualified"] = 110
        self.assertFalse(batch.acceptance_gates(aggregate, manifest, audit, descriptions, loaded)["pass"])


class BatchIOTests(unittest.TestCase):
    def test_authorized_resume_reevaluates_historical_b037_without_rewriting_it(self):
        data = batch.read(batch.ROOT_OUTPUT / "control.json")
        data.update(records=data["records"][:37], completed=False, active_attempt=None, stopped_reason=None)
        self.assertEqual(data["records"][36]["logical_index"], 36)
        self.assertEqual(data["records"][36]["hard_failures"],
            ["onboard_mission_parameters", "truth_separation", "episode_quality"])
        original_records = copy.deepcopy(data["records"])
        # Fix the historical boundary independently of later batch progress.
        self.assertEqual(batch.next_mission(data), (37, 0))
        self.assertEqual(data["records"], original_records)

    def test_prepare_then_successful_next_uses_real_analysis(self):
        # Reuse completed B001 raw evidence read-only. Only the SITL runner is
        # replaced; the complete analyze_selected/analyze_run_v3 path is real.
        original = batch.read(batch.ROOT_OUTPUT / "control.json")
        source = Path(original["records"][0]["run_directory"])
        before = batch.hash_tree(source)
        pilot = batch.read(batch.PILOT_CONTROL)
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp) / "batch"
            stack.enter_context(patch.object(batch, "ROOT_OUTPUT", root))
            stack.enter_context(patch.object(batch, "pilot_integrity"))
            stack.enter_context(patch.object(batch, "integrity"))
            stack.enter_context(patch.object(batch, "verify_preflight_files",
                return_value={"actual": {"firmware": pilot["firmware"]}}))
            stack.enter_context(patch.object(batch, "disk_status", return_value={"pass_gate": True}))
            # Avoid rescanning unrelated history; actual source/artifact checks
            # in analyze_selected still verify every B001 input and new output.
            with patch.object(batch, "hash_tree", return_value={}):
                batch.prepare(root, source_commit="a" * 40)
            self.assertTrue((root / "analyses").is_dir())
            self.assertFalse((root / "analyses/B001_attempt_0").exists())
            runner = stack.enter_context(patch.object(batch, "run_mission_list", return_value={"missions": [{
                "attempts": [{"status": "succeeded", "run_directory": str(source)}]}]}))
            record, finished = batch.run_next(root)
            runner.assert_called_once()
            manifest = batch.read(root / "analyses/B001_attempt_0/manifest.json")
            self.assertEqual(manifest["route_progress_version"], "ordered_route_progress_v2")
            self.assertEqual(manifest["semantic_validation_version"], "multi_intent_validation_v3")
            self.assertEqual(record["hard_failures"], [])
            self.assertTrue(record["episode_quality_eligible"])
            self.assertIsNone(finished["stopped_reason"])
            self.assertEqual(len(finished["records"]), 1)
        self.assertEqual(batch.hash_tree(source), before)

    def test_bundle_reuses_exact_accepted_240_missions_without_resampling(self):
        listing, manifest = batch.verify_generation(batch.DR_GENERATED / "mission_list.json")
        by_base = {}
        for entry in listing["missions"]:
            by_base.setdefault(entry["base_index"], {})[entry["intent"]] = entry
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = batch._write_bundle(root, listing, manifest, by_base)
            self.assertEqual(len(plan), 240)
            self.assertEqual([(e["base_index"], e["intent"]) for e in plan],
                [(base, intent) for base in range(10, 130) for intent in batch.INTENT_ORDER])
            for entry in plan:
                original = by_base[entry["base_index"]][entry["intent"]]
                for key in ("task", "scene"):
                    self.assertEqual((root / "bundle" / entry[key]).read_bytes(),
                                     batch.checked_path(batch.DR_GENERATED, original[key]).read_bytes())

    def context(self, stack, data, root, *, disk_ok=True):
        listing = dict(missions=[dict(mission_id=row(i)["mission_id"], scene=f"scene_{i}.json",
            base_index=i // 2 + 10, intent=batch.INTENT_ORDER[i % 2]) for i in range(240)])
        def reader(path):
            if Path(path).name == "control.json":
                return data
            if Path(path).name == "metadata.json":
                return dict(run_id=row(0)["run_id"], status="completed")
            return {}
        for name, value in (("read", reader), ("assert_binding", lambda *a: None),
                ("integrity", lambda *a, **k: None), ("verify_preflight_files", lambda *a: {}),
                ("disk_status", lambda *a: dict(pass_gate=disk_ok)),
                ("verify_generation", lambda *a: (listing, {})),
                ("checked_path", lambda a, b: Path(a) / b), ("_save_atomic", lambda *a: None),
                ("_event_rows", lambda *a: []), ("preflight_retry_reason", lambda *a: None),
                ("hash_tree", lambda *a: {})):
            stack.enter_context(patch.object(batch, name, value))

    def test_disk_failure_does_not_consume_attempt_or_start_sitl(self):
        data = control()
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            self.context(stack, data, tmp, disk_ok=False)
            runner = stack.enter_context(patch.object(batch, "run_mission_list"))
            with self.assertRaisesRegex(OSError, "insufficient_disk"):
                batch.run_next(tmp)
            runner.assert_not_called()
        self.assertEqual(data["records"], [])
        self.assertIsNone(data["active_attempt"])

    def test_runner_error_is_one_attempt_and_cannot_auto_retry(self):
        data = control()
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            self.context(stack, data, tmp)
            runner = stack.enter_context(patch.object(batch, "run_mission_list", side_effect=RuntimeError("connection")))
            with self.assertRaisesRegex(RuntimeError, "connection"):
                batch.run_next(tmp)
            self.assertEqual(runner.call_count, 1)
            self.assertEqual(runner.call_args.kwargs["max_environment_retries"], 0)
            self.assertEqual(runner.call_args.kwargs["max_runs"], 1)
        self.assertEqual(len(data["records"]), 1)
        self.assertIsNone(data["active_attempt"])
        self.assertIsNotNone(data["stopped_reason"])

    def test_finalize_explicitly_exports_pilot20_and_batch240(self):
        data = control(240)
        data.update(completed=True, rolling=batch.rolling_status(data))
        rows = batch.combined_records(data)
        manifest = dict(episodes=[dict(run_id=r["run_id"], directory=f"episodes/{r['run_id']}") for r in rows])
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            for name, value in (("read", lambda *a: data), ("assert_binding", lambda *a: None),
                    ("integrity", lambda *a, **k: None), ("file_hash", lambda *a: "a" * 64),
                    ("_save_atomic", lambda *a: None), ("audit_dataset", lambda *a, **k: {"issues": []}),
                    ("describe_dataset", lambda *a: None), ("_description_gate", lambda *a: {"consistency_pass": True}),
                    ("load_episode", lambda *a, **k: {"t_s": [0], "agent_ids": ["uav_01"]}),
                    ("load_public_scene", lambda *a: [[0, 0]] * 4)):
                stack.enter_context(patch.object(batch, name, value))
            exporter = stack.enter_context(patch.object(batch, "build_dataset", return_value=manifest))
            saved = stack.enter_context(patch.object(batch, "save_json"))
            result = batch.finalize(tmp)
        self.assertTrue(result["gate"]["pass"])
        self.assertEqual(len(exporter.call_args.args[0]), 260)
        self.assertEqual(len(exporter.call_args.kwargs["analysis_selections"]), 260)
        for record in rows:
            selection = exporter.call_args.kwargs["analysis_selections"][str(Path(record["run_directory"]).resolve())]
            self.assertEqual(selection["directory"], record["analysis_directory"])
        self.assertFalse(any(Path(call.args[0]).name == "analysis_latest.json" for call in saved.call_args_list))


if __name__ == "__main__":
    unittest.main()
