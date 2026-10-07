"""Offline continuation checks: immutable history, bounded runs and explicit export."""

import copy
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_v05_r12b_pp as pp


def assessment(reasons=()):
    return dict(version=pp.POLICY_VERSION, stage="pilot", aggregate_anomaly=bool(reasons),
                aggregate_anomaly_reasons=list(reasons), hard_checks={}, hard_failures=[],
                soft_flags=[], individual_pass=True, episode_quality_eligible=True)


def row(index, reasons=(), qualified=True):
    return dict(logical_index=index, attempt_index=0, run_id=f"run_{index:02d}",
                mission_id=f"mission_{index:02d}", base_index=index // 2,
                intent=pp.INTENT_ORDER[index % 2], retryable_pre_takeoff=False,
                qualified=qualified, accepted_for_pp=qualified,
                episode_quality_eligible=qualified, mission_success=not bool(reasons),
                mission_success_observation=True, semantic_consistency="agree",
                assessment=assessment(reasons), hard_failures=[], soft_flags=[],
                evidence_sha256={}, run_directory=f"source/run_{index:02d}",
                analysis_directory=f"external/analysis_{index:02d}",
                runner_status="succeeded", run_status="completed")


def control(count=8):
    records = [row(i) for i in range(count)]
    inherited = copy.deepcopy(records[:8])
    inherited[-1]["hard_failures"] = ["known_consistent_labels"]
    for derived, source in zip(records, inherited):
        derived["source_record"] = copy.deepcopy(source)
    return dict(version=pp.VERSION, stage="pilot", acceptance_policy=pp.POLICY_VERSION,
                max_attempts=22, max_extra_retries=2, rolling_start_logical_index=8,
                hold_s=0, progress_mapping_version=pp.PROGRESS_VERSION,
                patrol_validator_version=pp.PATROL_VERSION,
                bundle=str(pp.ROOT_OUTPUT / "bundle"),
                planned_missions=[f"mission_{i:02d}" for i in range(20)],
                records=records, inherited_records=inherited, stopped_reason=None,
                completed=False, finalized=False, active_attempt=None,
                binary="binary", parameters="parameters", quality_policy={},
                storage_estimate=dict(max_run_bytes=100, max_analysis_bytes=20))


class ContinuationBoundaryTests(unittest.TestCase):
    def test_first_next_is_pp09_and_original_stop_is_retained(self):
        data = control()
        before = copy.deepcopy(data["inherited_records"])
        self.assertEqual(pp.next_mission(data), (8, 0))
        self.assertEqual(len(data["records"]), 8)
        self.assertEqual(data["inherited_records"], before)
        self.assertEqual(before[7]["hard_failures"], ["known_consistent_labels"])

    def test_binding_rejects_rewritten_source_record_or_mission_order(self):
        data = control()
        old = dict(records=copy.deepcopy(data["inherited_records"]),
                   planned_missions=copy.deepcopy(data["planned_missions"]))
        with patch.object(pp, "read", return_value=old):
            pp.assert_binding(data, pp.ROOT_OUTPUT)
            data["records"][7]["source_record"]["hard_failures"] = []
            with self.assertRaisesRegex(ValueError, "original evidence"):
                pp.assert_binding(data, pp.ROOT_OUTPUT)
            data["records"][7]["source_record"] = copy.deepcopy(old["records"][7])
            data["planned_missions"][8:10] = reversed(data["planned_missions"][8:10])
            with self.assertRaisesRegex(ValueError, "mission order"):
                pp.assert_binding(data, pp.ROOT_OUTPUT)

    def test_no_automatic_retry_or_unresolved_attempt_resume(self):
        for change in (dict(stopped_reason="infrastructure"), dict(active_attempt={"index": 8}),
                       dict(completed=True)):
            data = control()
            data.update(change)
            with self.assertRaises(ValueError):
                pp.next_mission(data)
        data = control(9)
        data["records"][-1]["retryable_pre_takeoff"] = True
        with self.assertRaisesRegex(ValueError, "explicit recovery"):
            pp.next_mission(data)

    def test_bad_order_budget_and_twenty_completed_are_rejected(self):
        data = control()
        data["records"][3]["logical_index"] = 4
        with self.assertRaisesRegex(ValueError, "order"):
            pp.next_mission(data)
        with self.assertRaisesRegex(ValueError, "all twenty"):
            pp.next_mission(control(20))
        with self.assertRaisesRegex(ValueError, "22-attempt"):
            pp.next_mission(control(22))
        data = control()
        data["max_attempts"] = 23
        with self.assertRaisesRegex(ValueError, "budget"):
            pp.next_mission(data)

    def test_rolling_excludes_inherited_and_deduplicates_three_conditions(self):
        data = control()
        for record in data["records"]:
            record["assessment"] = assessment(["task_failure_truth"])
        self.assertEqual(pp.rolling_status(data)["window_count"], 0)
        reasons = ["task_failure_truth", "label_disagreement", "episode_quality_ineligible"]
        for i in range(8, 12):
            pp.complete_record(data, row(i, reasons, qualified=False))
        result = pp.rolling_status(data)
        self.assertEqual((result["window_count"], result["anomaly_count"]), (4, 4))
        self.assertFalse(result["stop"])
        self.assertIsNone(data["stopped_reason"])
        pp.complete_record(data, row(12, reasons, qualified=False))
        self.assertEqual(data["rolling"]["anomaly_count"], 5)
        self.assertEqual(data["stopped_reason"], "rolling_anomalous_runs_at_least_5")

    def test_quality_or_paired_acceptance_unattainable_does_not_stop_early(self):
        data = control()
        for i in range(8, 13):
            bad = i in (8, 10, 12)
            pp.complete_record(data, row(i, ["episode_quality_ineligible"] if bad else (), not bad))
        self.assertEqual(data["aggregate"]["logical_completed"] - data["aggregate"]["qualified"], 3)
        self.assertEqual(data["rolling"]["anomaly_count"], 3)
        self.assertIsNone(data["stopped_reason"])
        self.assertEqual(pp.next_mission(data), (13, 0))

    def test_four_anomalies_finish_then_final_acceptance_fails(self):
        data = control()
        for i in range(8, 20):
            bad = i in (8, 10, 12, 14)
            pp.complete_record(data, row(i, ["episode_quality_ineligible"] if bad else (), not bad))
        self.assertTrue(data["completed"])
        self.assertIsNone(data["stopped_reason"])
        gates = pp.pilot_acceptance_gates(data["aggregate"], {"episodes": [{}] * 20},
            {"issues": []}, {"consistency_pass": True},
            [{"corner_count": 4, "corner_dimensions": [2] * 4}] * 20)
        self.assertFalse(gates["episode_quality_18_of_20"])
        self.assertFalse(gates["pass"])

    def test_hard_failure_takes_priority_over_rolling(self):
        data = control()
        record = row(8)
        record["hard_failures"] = ["truth_separation"]
        pp.complete_record(data, record)
        self.assertEqual(data["stopped_reason"], "truth_separation")
        with self.assertRaises(ValueError):
            pp.next_mission(data)

    def test_disk_estimate_has_remaining_runs_and_twenty_exports(self):
        data = control()
        required = 12 * 120 + 20 * 20
        with patch.object(pp.shutil, "disk_usage", return_value=SimpleNamespace(free=required)):
            result = pp.disk_status(data)
        self.assertEqual(result["required_remaining_bytes"], required)
        self.assertTrue(result["pass_gate"])
        with patch.object(pp.shutil, "disk_usage", return_value=SimpleNamespace(free=required - 1)):
            self.assertFalse(pp.disk_status(data)["pass_gate"])

    def test_postflight_document_updates_do_not_bypass_archived_source_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, archive = Path(tmp) / "rules.md", Path(tmp) / "snapshot.md"
            live.write_text("frozen", encoding="utf-8")
            archive.write_text("frozen", encoding="utf-8")
            data = dict(historical_sha256={}, bundle_sha256={}, records=[],
                        runtime_sha256={str(live): pp.file_hash(live)},
                        runtime_archive_sha256={str(archive): pp.file_hash(archive)})
            with patch.object(pp, "assert_protected"):
                pp.integrity(data)
                live.write_text("final budget", encoding="utf-8")
                with self.assertRaises(ValueError):
                    pp.integrity(data)
                pp.integrity(data, include_runtime=False)
                archive.write_text("rewritten history", encoding="utf-8")
                with self.assertRaises(ValueError):
                    pp.integrity(data, include_runtime=False)


class MockedExecutionTests(unittest.TestCase):
    def context(self, stack, data, root, *, disk_ok=True):
        listing = dict(missions=[dict(mission_id=f"mission_{i:02d}", scene=f"scene_{i}.json",
            base_index=i // 2, intent=pp.INTENT_ORDER[i % 2]) for i in range(20)])
        metadata = dict(run_id="run_08", status="completed")
        def reader(path):
            name = Path(path).name
            if name == "control.json":
                return data
            if name == "metadata.json":
                return metadata
            return {}
        for name, value in (("read", reader), ("assert_binding", lambda *a: None),
                ("integrity", lambda *a, **k: None), ("verify_preflight_files", lambda *a: {}),
                ("disk_status", lambda *a: dict(pass_gate=disk_ok, free_bytes=100, required_remaining_bytes=10)),
                ("verify_generation", lambda *a: (listing, {})),
                ("checked_path", lambda a, b: Path(a) / b), ("_save_atomic", lambda *a: None),
                ("_event_rows", lambda *a: []), ("preflight_retry_reason", lambda *a: None),
                ("hash_tree", lambda *a: {})):
            stack.enter_context(patch.object(pp, name, value))
        return metadata

    def test_disk_failure_stops_before_attempt_reservation(self):
        data = control()
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            self.context(stack, data, Path(tmp), disk_ok=False)
            runner = stack.enter_context(patch.object(pp, "run_mission_list"))
            with self.assertRaisesRegex(OSError, "insufficient_disk"):
                pp.run_next(Path(tmp))
            runner.assert_not_called()
        self.assertEqual(len(data["records"]), 8)
        self.assertIsNone(data["active_attempt"])
        self.assertIn("insufficient_disk", data["stopped_reason"])

    def test_runner_exception_is_recorded_once_and_never_retried(self):
        data = control()
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            self.context(stack, data, Path(tmp))
            runner = stack.enter_context(patch.object(pp, "run_mission_list", side_effect=RuntimeError("connection failure")))
            with self.assertRaisesRegex(RuntimeError, "connection failure"):
                pp.run_next(Path(tmp))
            self.assertEqual(runner.call_count, 1)
            self.assertEqual(runner.call_args.kwargs["max_environment_retries"], 0)
            self.assertEqual(runner.call_args.kwargs["max_runs"], 1)
        self.assertEqual(len(data["records"]), 9)
        self.assertIsNone(data["active_attempt"])
        self.assertIn("infrastructure", data["stopped_reason"])

    def test_legacy_runner_semantic_failure_does_not_replace_new_assessment(self):
        data = control()
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            self.context(stack, data, Path(tmp))
            stack.enter_context(patch.object(pp, "run_mission_list", return_value={"missions": [{"attempts": [
                dict(status="semantic_failed", run_directory=str(Path(tmp) / "raw"))]}]}))
            result = row(8)
            for field in ("logical_index", "mission_id", "intent", "base_index", "runner_status",
                          "run_directory", "analysis_directory", "run_id"):
                result.pop(field)
            stack.enter_context(patch.object(pp, "analyze_selected", return_value=result))
            record, finished = pp.run_next(Path(tmp))
        self.assertEqual(record["runner_status"], "semantic_failed")
        self.assertTrue(record["mission_success"])
        self.assertEqual(finished["rolling"]["anomaly_count"], 0)
        self.assertIsNone(finished["stopped_reason"])

    def test_selected_analysis_rejects_run_mismatch_before_hash_validation(self):
        scene = {"task_spec": {"schema_version": 3, "mission": {"intent": "patrol"}}}
        metadata = dict(scenario=scene, run_id="actual", quality_policy_sha256="q")
        manifest = dict(run_id="different", run_directory=str(Path("source").resolve()),
            quality_policy_sha256="q", route_progress_version=pp.PROGRESS_VERSION,
            acceptance_policy_version=pp.POLICY_VERSION,
            **pp.semantic_protocol(scene, patrol_validator_version=pp.PATROL_VERSION))
        with (patch.object(pp, "read", side_effect=[metadata, manifest]),
              patch.object(pp, "assert_hashes") as hashes):
            with self.assertRaisesRegex(ValueError, "mismatch"):
                pp.selected_artifacts("source", "analysis", scene, {"quality_policy_sha256": "q"})
            hashes.assert_not_called()

    def test_finalize_explicitly_binds_all_twenty_external_analyses(self):
        data = control(20)
        data.update(completed=True, rolling=pp.rolling_status(data))
        manifest = {"episodes": [dict(run_id=r["run_id"], directory=f"episodes/{r['run_id']}")
                                 for r in data["records"]]}
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            for name, value in (("read", lambda *a: data), ("assert_binding", lambda *a: None),
                    ("integrity", lambda *a, **k: None), ("file_hash", lambda *a: "a" * 64),
                    ("_save_atomic", lambda *a: None), ("audit_dataset", lambda *a, **k: {"issues": []}),
                    ("describe_dataset", lambda *a: None),
                    ("_description_gate", lambda *a: {"consistency_pass": True}),
                    ("load_episode", lambda *a, **k: {"t_s": [0], "agent_ids": ["uav_01"]}),
                    ("load_public_scene", lambda *a: [[0, 0]] * 4)):
                stack.enter_context(patch.object(pp, name, value))
            exporter = stack.enter_context(patch.object(pp, "build_dataset", return_value=manifest))
            saved = stack.enter_context(patch.object(pp, "save_json"))
            result = pp.finalize(root)
        self.assertTrue(result["gate"]["pass"])
        selections = exporter.call_args.kwargs["analysis_selections"]
        self.assertEqual(len(selections), 20)
        self.assertEqual(len(exporter.call_args.args[0]), 20)
        for record in data["records"]:
            selection = selections[str(Path(record["run_directory"]).resolve())]
            self.assertEqual(selection["directory"], record["analysis_directory"])
            self.assertEqual(selection["manifest_sha256"], "a" * 64)
        self.assertFalse(any(Path(call.args[0]).name == "analysis_latest.json" for call in saved.call_args_list))
        self.assertTrue(data["finalized"])
        self.assertEqual(data["inherited_records"][7]["hard_failures"], ["known_consistent_labels"])


if __name__ == "__main__":
    unittest.main()
