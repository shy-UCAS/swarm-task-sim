"""Read-only reporting checks; no process creation and no SITL execution."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.report_v06_pilot import (audit_coverage, check_exported_episode, check_loaded, grouped_distributions,
    passing_speed_groups, selected_execution_copy, summary)
from swarm_sim.dataset_audit_v3 import COMMON_METRICS
from swarm_sim.episode_loader import FEATURE_COLUMNS
from swarm_sim.generation import file_hash


def episode():
    return dict(t_s=[0., .1], agent_ids=["a", "b"],
                x=[[[1., 2., 3., 4., 5., 6.], [0.]*6], [[2.]*6, [3.]*6]],
                mask=[[True, False], [True, True]], metadata=dict(feature_columns=list(FEATURE_COLUMNS)))


def audit_fixture():
    group = dict(intent="reconnaissance", control_mode="semantic_phase_route_v1",
                 metrics={name: dict(count=1, expected_values=1, missing_values=0) for name in COMMON_METRICS},
                 intent_metrics=dict(coverage=dict(count=1)), required_audit_metrics=["coverage"],
                 missing_common_metrics=[], missing_intent_metrics=[], episode_count=1, rates={}, clock_grades={},
                 id_position_order=dict(east={}, north={}), topology=dict(signature_counts={},
                    test_signature_seen_in_train={}, distinct_test_signatures_seen_in_train={}))
    return dict(counts={}, rates={}, clock_grades={}, counterfactual_completeness={},
                id_position_order={}, duplicates={}, family_split_leaks={}, groups=[group])


def metric_row(stops=(2, 4), unknown=0):
    return dict(intent="reconnaissance", control_mode="semantic_phase_route_v1",
                stop_counts={key: dict(zip(("a", "b"), stops)) for key in ("0.3", "0.5")},
                thresholds={key: dict(stationary_time_fraction=.2, synchronized_time_fraction=.1) for key in ("0.3", "0.5")},
                task_span_s=10, elapsed_s=70, truth_coverage=1., observation_coverage=.9,
                upload_release_confirmation_fraction=None, agents=2, speed_m_s=3., execution_stage_count=2,
                intermediate_waypoints=dict(total_count=4, stopped_count=1, unknown_count=unknown))


class V06PilotReportTests(unittest.TestCase):
    def test_complete_loader_shape_and_mask(self):
        result = check_loaded(episode())
        self.assertTrue(result["passed"])
        self.assertEqual(result["x_shape"], [2, 2, 6])
        self.assertEqual(result["mask_shape"], [2, 2])
        self.assertEqual(result["valid_agent_frames"], 3)

    def test_later_malformed_feature_row_is_detected(self):
        value = episode()
        value["x"][1][1] = [3.]*5
        self.assertFalse(check_loaded(value)["passed"])

    def test_failed_ineligible_empty_export_is_loadable_but_not_valid_data(self):
        value = episode()
        value.update(t_s=[], x=[], mask=[])
        result = check_exported_episode(dict(run_status="failed", episode_quality_eligible=False), value)
        self.assertTrue(result["passed"])
        self.assertEqual(result["x_shape"], [0, 2, 6])
        self.assertEqual(result["mask_shape"], [0, 2])
        self.assertFalse(result["has_valid_observations"])
        self.assertFalse(result["has_observation_frames"])

    def test_completed_or_eligible_empty_export_is_rejected(self):
        value = episode()
        value.update(t_s=[], x=[], mask=[])
        for entry in (dict(run_status="completed", episode_quality_eligible=False),
                      dict(run_status="completed", episode_quality_eligible=True),
                      dict(run_status="failed", episode_quality_eligible=True),
                      dict(run_status="failed", episode_quality_eligible=None)):
            self.assertFalse(check_exported_episode(entry, value)["passed"])

    def test_empty_export_does_not_relax_agent_or_feature_schema_checks(self):
        value = episode()
        value.update(t_s=[], x=[], mask=[])
        entry = dict(run_status="failed", episode_quality_eligible=False)
        value["agent_ids"] = []
        self.assertFalse(check_exported_episode(entry, value)["passed"])
        value["agent_ids"] = ["a", "b"]
        value["metadata"]["feature_columns"] = ["wrong"]
        self.assertFalse(check_exported_episode(entry, value)["passed"])

    def test_missing_agent_mask_row_is_detected(self):
        value = episode()
        value["mask"][1] = [True]
        self.assertFalse(check_loaded(value)["checks"]["full_shape"])

    def test_invalid_mask_requires_zero_features(self):
        value = episode()
        value["x"][0][1][0] = 9
        self.assertFalse(check_loaded(value)["checks"]["invalid_zero_filled"])

    def test_numeric_masks_rejected(self):
        value = episode()
        value["mask"][1][0] = 1
        self.assertFalse(check_loaded(value)["checks"]["boolean_mask"])

    def test_all_69_fields_required_in_each_group(self):
        value = audit_fixture()
        self.assertTrue(audit_coverage(value)["passed"])
        value["groups"].append(copy.deepcopy(value["groups"][0]))
        value["groups"][1]["metrics"].pop("execution_synchronized_time_fraction")
        self.assertFalse(audit_coverage(value)["passed"])

    def test_topology_overlap_and_missing_metrics_not_omitted(self):
        value = audit_fixture()
        value["groups"][0]["topology"].pop("test_signature_seen_in_train")
        self.assertFalse(audit_coverage(value)["passed"])
        value = audit_fixture()
        value["groups"][0].pop("missing_intent_metrics")
        self.assertFalse(audit_coverage(value)["passed"])

    def test_quantiles_exclude_unknown_without_changing_denominator(self):
        result = summary([0, 10, None, float("nan"), True], "s", "episodes")
        self.assertEqual((result["count"], result["expected_count"], result["unknown_count"]), (2, 5, 3))
        self.assertEqual((result["p10"], result["median"], result["p90"]), (1, 5, 9))

    def test_distributions_distinguish_episode_and_aircraft_weights(self):
        rows = [metric_row(), metric_row((6, None))]
        rows[1]["elapsed_s"] = 90
        report = grouped_distributions(rows)[0]
        stops = report["metrics"]["speed_lt_0.3_m_s:stop_count_per_aircraft"]
        self.assertEqual((stops["median"], stops["count"], stops["unknown_count"]), (4, 3, 1))
        self.assertEqual(report["metrics"]["elapsed_s"]["median"], 80)
        self.assertEqual(report["intermediate_stop"]["rate"], .25)

    def test_unknown_intermediate_point_does_not_lower_stop_rate(self):
        report = grouped_distributions([metric_row(unknown=1)])[0]
        self.assertIsNone(report["intermediate_stop"]["rate"])
        self.assertEqual(report["intermediate_stop"]["unknown_count"], 1)

    def test_scan_length_groups_preserve_missing_speeds_and_lengths(self):
        row = metric_row()
        row["run_id"] = "test"
        row["intermediate_waypoints"]["records"] = [
            dict(scan_line_length_m=8, minimum_passing_speed_m_s=1.),
            dict(scan_line_length_m=8, minimum_passing_speed_m_s=None),
            dict(scan_line_length_m=12, minimum_passing_speed_m_s=2.),
            dict(scan_line_length_m=None, minimum_passing_speed_m_s=3.)]
        groups = {r["scan_line_length_m"]: r for r in passing_speed_groups([row])}
        self.assertEqual((groups[8]["valid_waypoints"], groups[8]["total_waypoints"], groups[8]["unknown_waypoints"]), (1, 2, 1))
        self.assertIn(None, groups)
        self.assertEqual(groups[12]["minimum_passing_speed"]["median"], 2.)

    def test_legacy_copy_cannot_substitute_different_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            copied, frozen = root/"copies/run", root/"frozen"
            analysis = copied/"analysis"
            analysis.mkdir(parents=True)
            frozen.mkdir()
            def write(path, value):
                path.write_text(json.dumps(value), encoding="utf-8")
            write(copied/"metadata.json", dict(run_id="test"))
            for name in ("execution_metrics.json", "task.json", "observations.csv"):
                (analysis/name).write_text("{}", encoding="utf-8")
                (frozen/name).write_text("{}", encoding="utf-8")
            write(analysis/"manifest.json", dict(run_id="test", artifact_sha256={p.name:file_hash(p) for p in analysis.iterdir()}))
            write(copied/"analysis_latest.json", dict(directory="analysis", manifest_sha256=file_hash(analysis/"manifest.json")))
            entry = dict(run_id="test", source_run="run")
            selected_execution_copy(entry, frozen, {}, root/"copies")
            (frozen/"observations.csv").write_text("different", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs from frozen pilot"):
                selected_execution_copy(entry, frozen, {}, root/"copies")


if __name__ == "__main__":
    unittest.main()
