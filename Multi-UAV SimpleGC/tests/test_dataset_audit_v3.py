"""G10: hand-calculable, manifest-bound synthetic audit; no live flights."""

import json
import tempfile
import unittest
from pathlib import Path

from swarm_sim.dataset import build_dataset
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.dataset_audit_v3 import COMMON_METRICS, id_position_order
from swarm_sim.families import scene_family_id
from swarm_sim.mission_v3 import normalize_v3
from swarm_sim.observation_processing import processing_versions
from swarm_sim.recording import write_json
from swarm_sim.registry import temporary_registration
from swarm_sim.tasks import compile_task
from v3_artifact_fixture import fixture_intent, make_run, rehash


def attach_evidence(run, analysis):
    task = json.loads((analysis/"task.json").read_text())
    agents = [v["id"] for v in task["scenario"]["vehicles"]]
    write_json(analysis/"allocation.json", compile_task(task)["planning"])
    constraints = json.loads((analysis/"execution_constraints.json").read_text())
    constraints["per_agent"] = {agent: dict(truth=dict(path_length_m=100+10*i), armed_to_landed_source_s=60)
                                for i, agent in enumerate(agents)}
    write_json(analysis/"execution_constraints.json", constraints)
    write_json(analysis/"phase_windows.json", dict(**processing_versions(), windows=[dict(phase=name, barrier_wait_host_s=value)
        for name, value in (("approach", .5), ("observe", .4), ("return", .3))]))
    threshold = dict(per_agent={a: dict(stop_count=2+i, counts_by_location=dict(
        intermediate_waypoint=1, semantic_endpoint=1, other=i)) for i, a in enumerate(agents)},
        stationary_time_fraction=.25, synchronized_time_fraction=.1, common_overlap_event_fraction=.2,
        fleet_stop_event_count=5, common_overlap_event_count=1)
    write_json(analysis/"execution_metrics.json", dict(version="execution_artifacts_v1", **processing_versions(),
        thresholds={"0.3": threshold, "0.5": threshold},
        intermediate_waypoints=dict(stop_rate=.125),
        arrival_lag_s=dict(distribution=dict(median=.6)), barrier_wait_s=dict(distribution=dict(median=.4)),
        nominal_timing_deviation_s=dict(max_abs_s=2)))
    rehash(run)


def translate_scene(run, analysis, shift):
    task = json.loads((analysis/"task.json").read_text())
    for vehicle in task["scenario"]["vehicles"]:
        vehicle["east_m"] += shift
    task["scenario"]["regions"][0]["min_east_m"] += shift
    task["family_id"] = scene_family_id(task)
    task = normalize_v3(task)
    write_json(analysis/"task.json", task)
    manifest = json.loads((analysis/"manifest.json").read_text())
    manifest["family_id"] = task["family_id"]
    write_json(analysis/"manifest.json", manifest)
    rehash(run)


class DatasetAuditV3Tests(unittest.TestCase):
    def test_g10_common_and_registered_intent_metrics_are_separate(self):
        with tempfile.TemporaryDirectory() as temp, temporary_registration(fixture_intent()):
            root = Path(temp)
            a, ae = make_run(root/"recon")
            b, be = make_run(root/"fixture", intent="test_fixture")
            attach_evidence(a, ae)
            attach_evidence(b, be)
            build_dataset([a, b], root/"dataset")
            result = audit_dataset(root/"dataset")
            groups = {g["intent"]: g for g in result["groups"]}
            fixture = groups["test_fixture"]
            recon = groups["reconnaissance"]
            self.assertEqual(set(fixture["metrics"]), set(COMMON_METRICS))
            self.assertEqual(fixture["missing_common_metrics"], [])
            self.assertEqual(fixture["required_audit_metrics"], ["fixture_marker"])
            self.assertEqual(fixture["missing_intent_metrics"], [])
            self.assertNotIn("global_coverage_ratio", fixture["intent_metrics"])
            self.assertEqual(fixture["intent_metrics"]["fixture_marker"]["median"], 1)
            self.assertEqual(recon["intent_metrics"]["global_coverage_ratio"]["median"], .5)
            self.assertEqual(recon["missing_intent_metrics"], ["leave_one_out_coverage_drop"])
            self.assertEqual(result["metrics"]["execution_stop_count"]["count"], 6)
            self.assertEqual(result["metrics"]["execution_stop_count"]["median"], 3)
            self.assertEqual(result["metrics"]["execution_stationary_time_fraction"]["median"], .25)
            self.assertEqual(result["metrics"]["execution_intermediate_stop_count"]["median"], 1)
            self.assertEqual(result["metrics"]["execution_fleet_stop_event_count"]["median"], 5)
            self.assertEqual(result["metrics"]["executed_stage_count"]["median"], 3)
            self.assertEqual(result["metrics"]["executed_path_length_m"]["median"], 110)

    def test_g10_counterfactual_uses_quality_eligibility_not_mission_success(self):
        with tempfile.TemporaryDirectory() as temp, temporary_registration(fixture_intent()):
            root = Path(temp)
            a, _ = make_run(root/"recon", success=False)
            b, _ = make_run(root/"fixture", intent="test_fixture", success=False)
            data = build_dataset([a, b], root/"dataset")
            report = audit_dataset(root/"dataset")
            family = data["episodes"][0]["family_id"]
            self.assertTrue(report["counterfactual_completeness"]["complete"])
            self.assertEqual(report["counterfactual_completeness"]["missing"], [])
            self.assertEqual(report["counterfactual_completeness"]["matrix"][family]["test_fixture"]["quality_eligible"], 1)
            self.assertEqual(report["rates"]["semantic_pass"]["fraction"], 0)
            self.assertEqual(report["rates"]["episode_quality_eligible"]["fraction"], 1)
            self.assertEqual(report["family_split_leaks"], {})

    def test_g10_missing_intent_or_only_bad_quality_episode_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp, temporary_registration(fixture_intent()):
            root = Path(temp)
            a, _ = make_run(root/"recon")
            b, be = make_run(root/"fixture", intent="test_fixture")
            c, ce = make_run(root/"other_scene")
            translate_scene(c, ce, 1)
            for filename in ("quality.json", "manifest.json"):
                value = json.loads((be/filename).read_text())
                value["episode_quality_eligible"] = False
                if filename == "quality.json":
                    value["data_quality_pass"] = False
                write_json(be/filename, value)
            rehash(b)
            build_dataset([a, b, c], root/"dataset")
            report = audit_dataset(root/"dataset")
            missing = report["counterfactual_completeness"]["missing"]
            self.assertEqual(len(missing), 2)
            self.assertEqual({m["intent"] for m in missing}, {"test_fixture"})
            self.assertFalse(report["counterfactual_completeness"]["complete"])

    def test_g10_missing_evidence_remains_null_with_explicit_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, _ = make_run(root/"run")
            build_dataset([run], root/"dataset")
            result = audit_dataset(root/"dataset")
            metric = result["metrics"]["execution_stop_count"]
            self.assertEqual(metric["count"], 0)
            self.assertEqual(metric["expected_values"], 3)
            self.assertEqual(metric["missing_values"], 3)
            self.assertIsNone(metric["median"])
            self.assertIn("execution_stop_count", result["missing_metrics"])
            self.assertIsNone(result["rates"]["planning"]["numerator"])
            self.assertIsNone(result["counts"]["attempts"])
            self.assertIsNone(result["groups"][0]["topology"]["test_signature_seen_in_train"]["fraction"])

    def test_g10_order_agreement_excludes_ties_and_reports_reverse_order(self):
        points = [dict(id="a", east_m=0, north_m=1), dict(id="b", east_m=2, north_m=1),
                  dict(id="c", east_m=1, north_m=1)]
        result = id_position_order(points)
        self.assertEqual(result["east"], dict(agree_pairs=2, comparable_pairs=3, tied_pairs=0, fully_ordered=False))
        self.assertEqual(result["north"], dict(agree_pairs=0, comparable_pairs=0, tied_pairs=3, fully_ordered=None))

    def test_g10_topology_overlap_is_episode_weighted_with_known_denominator(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a, ae = make_run(root/"train")
            b, be = make_run(root/"test")
            translate_scene(b, be, 1)
            attach_evidence(a, ae)
            attach_evidence(b, be)
            dataset = build_dataset([a, b], root/"dataset")
            # Audit fixture assigns two distinct families to controlled splits.
            dataset["episodes"][0]["split"] = "train"
            dataset["episodes"][1]["split"] = "test"
            write_json(root/"dataset/dataset_manifest.json", dataset)
            report = audit_dataset(root/"dataset")
            topology = report["groups"][0]["topology"]
            self.assertEqual(topology["test_signature_seen_in_train"]["numerator"], 1)
            self.assertEqual(topology["test_signature_seen_in_train"]["denominator"], 1)
            self.assertEqual(topology["test_signature_seen_in_train"]["fraction"], 1)
            self.assertEqual(report["family_split_leaks"], {})
            self.assertEqual(report["id_position_order"]["east"]["pairwise"]["fraction"], 1)
            self.assertIsNone(report["id_position_order"]["north"]["pairwise"]["fraction"])

    def test_g10_mixed_modes_are_separate_groups_and_duplicates_and_leaks_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a, _ = make_run(root/"a")
            b, _ = make_run(root/"b")
            c, _ = make_run(root/"c", mode="semantic_phase_route_v1")
            data = build_dataset([a, b, c], root/"dataset", allow_mixed_control_modes=True)
            data["episodes"][0]["split"] = "train"
            data["episodes"][1]["split"] = "test"
            write_json(root/"dataset/dataset_manifest.json", data)
            report = audit_dataset(root/"dataset")
            self.assertEqual({g["control_mode"] for g in report["groups"]}, {"waypoint_barrier_v1", "semantic_phase_route_v1"})
            self.assertEqual(list(report["duplicates"]["normalized_input_groups"].values()), [2])
            self.assertEqual(len(report["family_split_leaks"]), 1)
            self.assertIn("families cross dataset splits", report["issues"])

    def test_unbound_optional_file_is_ignored_bound_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a, ae = make_run(root/"a")
            data = build_dataset([a], root/"dataset")
            episode = root/"dataset"/data["episodes"][0]["directory"]
            write_json(episode/"execution_metrics.json", dict(version="forged", thresholds={"0.3": {"stationary_time_fraction": 0}}))
            report = audit_dataset(root/"dataset")
            self.assertFalse(report["episodes"][0]["execution_metrics_available"])
            self.assertIsNone(report["metrics"]["execution_stationary_time_fraction"]["median"])
            write_json(episode/"phase_windows.json", dict(windows=[]))
            with self.assertRaisesRegex(ValueError, "artifact changed"):
                audit_dataset(root/"dataset")

    def test_partial_stop_counts_remain_lower_bounds_not_complete_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a, ae = make_run(root/"a")
            attach_evidence(a, ae)
            value = json.loads((ae/"execution_metrics.json").read_text())
            value["thresholds"]["0.3"]["per_agent"]["uav_01"]["stop_count_is_lower_bound"] = True
            write_json(ae/"execution_metrics.json", value)
            rehash(a)
            build_dataset([a], root/"dataset")
            report = audit_dataset(root/"dataset")
            self.assertEqual(report["metrics"]["execution_stop_count"]["count"], 2)
            self.assertEqual(report["metrics"]["execution_stop_count"]["missing_values"], 1)
            self.assertEqual(report["episodes"][0]["execution_lower_bound_stop_counts"]["0.3"], {"uav_01": 2})

    def test_generation_evidence_can_name_missing_counterfactual_intent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a, _ = make_run(root/"a")
            data = build_dataset([a], root/"dataset")
            family = data["episodes"][0]["family_id"]
            write_json(root/"generation.json", dict(counts=dict(accepted_candidates=1, candidates=2, base_scenes=1),
                bases=[dict(status="accepted", family_id=family)], candidates=[dict(attempts=[dict(intent="reconnaissance"), dict(intent="not_exported")])]))
            report = audit_dataset(root/"dataset", generation_manifest=root/"generation.json")
            self.assertEqual(report["rates"]["planning"]["fraction"], .5)
            self.assertEqual(report["counterfactual_completeness"]["missing"][0]["intent"], "not_exported")


if __name__ == "__main__":
    unittest.main()
