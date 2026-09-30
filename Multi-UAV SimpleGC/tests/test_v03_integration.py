"""Version dispatch, provenance, driver adaptation and SIM evidence regressions."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import swarm
from swarm_sim import __version__
from swarm_sim.analysis import analyze_run, digest
from swarm_sim.dataset import build_dataset
from swarm_sim.recording import resample, write_json
from swarm_sim.runner import run_scene
from swarm_sim.scenario import enu_to_geo
from swarm_sim.tasks import compile_task, target_confirmation, validate_task_binding
from swarm_sim.truth import read_truth
from swarm_sim.vehicle import Vehicle

ROOT = Path(__file__).resolve().parents[1]


def shared_scene():
    return compile_task(json.loads((ROOT / "missions/recon_shared_3uav.json").read_text(encoding="utf-8")))


def failed_evidence(root, scene, run_id):
    root.mkdir()
    (root / "raw").mkdir()
    metadata = dict(version=__version__, run_id=run_id, scenario=scene, status="failed",
                    run_epoch_monotonic_s=100.0, elapsed_s=1.0)
    write_json(root / "metadata.json", metadata)
    write_json(root / "scenario.json", scene)
    (root / "events.jsonl").write_text('', encoding="utf-8")
    return analyze_run(root)


class DispatchTests(unittest.TestCase):
    def test_v2_keeps_auto_target_active_until_geometric_confirmation(self):
        # MISSION_ITEM_REACHED can precede the stricter task tolerance. Never
        # switch to pilot-throttle LOITER before independent evidence arrives.
        for shared, modes in ((True, ["AUTO"]), (False, ["AUTO", "LOITER"])):
            vehicle = Vehicle.__new__(Vehicle)
            vehicle.record_lifecycle = shared
            vehicle.id = "uav_01"
            vehicle.cursor = Mock(return_value=12)
            vehicle.event = Mock()
            vehicle.mode = Mock()
            vehicle.wait_message = Mock()
            vehicle.execute(0, 3, 10, "observe_001")
            self.assertEqual([call.args[0] for call in vehicle.mode.call_args_list], modes)
            predicate = vehicle.wait_message.call_args.args[1]
            self.assertFalse(predicate(SimpleNamespace(seq=1)))
            self.assertTrue(predicate(SimpleNamespace(seq=2)))

    def test_C01_legacy_compilation_matches_frozen_examples(self):
        for path in sorted((ROOT / "tasks").glob("*.json")):
            with self.subTest(task=path.name):
                spec = json.loads(path.read_text(encoding="utf-8"))
                expected = json.loads((ROOT / "scenarios" / ("task_" + path.name)).read_text(encoding="utf-8"))
                self.assertEqual(compile_task(spec), expected)

    def test_C06_binding_protects_v2_execution_and_semantics(self):
        scene = shared_scene()
        validate_task_binding(scene)
        for key in ("phases", "planning", "semantic_plan"):
            changed = copy.deepcopy(scene)
            if key == "phases":
                changed[key][0]["targets"]["uav_01"]["east_m"] += 1
            else:
                changed[key]["tampered"] = True
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "differs"):
                validate_task_binding(changed)

    def test_C06_direct_partition_region_and_service_mutations_rejected(self):
        scene = shared_scene()
        mutations = [
            lambda s: s["planning"]["region_partitions"][0].update(width_m=19.0),
            lambda s: s["task_spec"]["scenario"]["regions"][0].update(min_east_m=1.0),
            lambda s: s["semantic_plan"]["execution_phases"][s["phases"][1]["name"]]["agents"]["uav_01"].update(service_enabled=False),
        ]
        for index, mutate in enumerate(mutations):
            changed = copy.deepcopy(scene)
            mutate(changed)
            with self.subTest(mutation=index), self.assertRaisesRegex(ValueError, "differs"):
                validate_task_binding(changed)

    def test_v2_driver_confirmation_is_numeric_and_idle_does_not_add_service_dwell(self):
        scene = shared_scene()
        phase = scene["phases"][0]
        self.assertEqual(target_confirmation(scene, phase, "uav_01")["tolerance_m"], 1)
        scene["semantic_plan"]["execution_phases"][phase["name"]]["agents"]["uav_01"]["role"] = "idle_padding"
        self.assertEqual(target_confirmation(scene, phase, "uav_01")["dwell_s"], 0)

    def test_v2_plan_validate_and_launch_failure_keep_mission_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            planned = root / "compiled.json"
            with patch("builtins.print"):
                self.assertEqual(swarm.main(["plan", str(ROOT / "missions/recon_shared_3uav.json"), "--output", str(planned)]), 0)
                self.assertEqual(swarm.main(["validate", str(planned)]), 0)
                run, metadata, quality = run_scene(shared_scene(), root / "runs", root / "missing.exe", root / "missing.parm")
            self.assertEqual(metadata["status"], "failed")
            self.assertFalse(quality["usable"])
            self.assertNotIn("analysis_error", quality)
            output = run / json.loads((run / "analysis_latest.json").read_text())["directory"]
            labels = json.loads((output / "labels.json").read_text())
            self.assertEqual(labels["requested_intent"], "reconnaissance")
            self.assertIsNone(labels["mission_success"])


class SemanticExportTests(unittest.TestCase):
    def test_D05_semantic_and_constraint_versions_agree_across_all_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            output, quality, labels = failed_evidence(Path(temp) / "run", shared_scene(), "version_contract")
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            semantic = json.loads((output / "semantic_validation.json").read_text(encoding="utf-8"))
            constraints = json.loads((output / "execution_constraints.json").read_text(encoding="utf-8"))
            expected_semantic = manifest["semantic_validation_version"]
            self.assertEqual(expected_semantic, "shared_coverage_v2")
            semantic_versions = {
                "quality": quality["semantic_validation_version"],
                "semantic_validation": semantic["semantic_validation_version"],
                "label_provenance": labels["label_provenance"]["semantic_validation_version"],
                **{f"observed_behavior_{index}": behavior["rule_version"]
                   for index, behavior in enumerate(labels["observed_behaviors"])},
            }
            self.assertTrue(labels["observed_behaviors"])
            for artifact, version in semantic_versions.items():
                with self.subTest(artifact=artifact):
                    self.assertEqual(version, expected_semantic)
            self.assertEqual(labels["schema_version"], manifest["label_schema_version"])
            self.assertEqual(quality["label_schema_version"], manifest["label_schema_version"])
            self.assertEqual(quality["execution_constraints_version"], manifest["execution_constraints_version"])
            self.assertEqual(constraints["constraint_validation_version"], manifest["execution_constraints_version"])

    def test_D08_manually_supplied_family_groups_failure_retry_variant_and_window(self):
        # This tests the explicit derived-family export contract. It deliberately
        # does not implement or claim to exercise automatic sliding-window extraction.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = shared_scene()["task_spec"]
            run_ids = ["episode_7", "retry_f64", "variant_903", "window_caf"]
            paths = []
            for kind, run_id in zip(("failure", "retry", "variant", "provided_window"), run_ids):
                spec = copy.deepcopy(original)
                if kind == "variant":
                    spec["task_id"] += "_variant"
                    spec["execution"]["speed_m_s"] = 2.5
                scene = compile_task(spec)
                run = root / run_id
                run.mkdir()
                (run / "raw").mkdir()
                metadata = dict(version=__version__, run_id=run_id, scenario=scene, status="failed",
                    run_epoch_monotonic_s=100.0, elapsed_s=.5 if kind == "provided_window" else 1.0,
                    derivation=dict(kind=kind, parent_run_id="episode_7" if kind != "failure" else None,
                                    family_supplied_explicitly=True))
                write_json(run / "metadata.json", metadata)
                write_json(run / "scenario.json", scene)
                (run / "events.jsonl").write_text("", encoding="utf-8")
                analyze_run(run)
                paths.append(run)
            result = build_dataset(paths, root / "export")
            self.assertEqual(result["counts"]["total"], 4)
            self.assertEqual(result["counts"]["failed_runs"], 4)
            self.assertEqual({e["run_id"] for e in result["episodes"]}, set(run_ids))
            self.assertEqual({e["family_id"] for e in result["episodes"]}, {original["family_id"]})
            self.assertEqual(len({e["split"] for e in result["episodes"]}), 1)

    def test_D01_reanalysis_rejects_contradictory_scenario_sources_before_writing(self):
        scenes = [shared_scene(), json.loads((ROOT / "scenarios/task_point_visit_3uav.json").read_text())]
        for scene in scenes:
            with self.subTest(version=scene["task_spec"]["schema_version"]), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "run"
                failed_evidence(root, scene, "contradictory")
                previous_directories = set(root.glob("analysis_*"))
                previous_pointer = (root / "analysis_latest.json").read_bytes()
                changed = copy.deepcopy(scene)
                changed["phases"][0]["targets"]["uav_01"]["east_m"] += 1
                write_json(root / "scenario.json", changed)
                with self.assertRaisesRegex(ValueError, "scenario.json differs from metadata.scenario"):
                    analyze_run(root)
                self.assertEqual(set(root.glob("analysis_*")), previous_directories)
                self.assertEqual((root / "analysis_latest.json").read_bytes(), previous_pointer)

    def test_D01_v2_artifacts_are_hashed_and_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / "run"
            output, quality, labels = failed_evidence(run, shared_scene(), "v2")
            manifest = json.loads((output / "manifest.json").read_text())
            for name in ("mission.json", "shared_scene.json", "allocation.json", "semantic_plan.json",
                         "semantic_validation.json", "execution_constraints.json", "phase_windows.json"):
                self.assertEqual(digest(output / name), manifest["artifact_sha256"][name])
            self.assertFalse(quality["benchmark_eligible"])
            dataset = build_dataset([run], root / "dataset")
            self.assertEqual(dataset["semantic_protocol"]["task_kind"], "mission_v2")
            self.assertEqual(dataset["counts"]["failed_runs"], 1)
            self.assertEqual(dataset["episodes"][0]["source_analysis_directory"], output.name)
            with (output / "semantic_validation.json").open("a", encoding="utf-8") as file:
                file.write(" ")
            with self.assertRaisesRegex(ValueError, "artifact changed"):
                build_dataset([run], root / "corrupted")
            self.assertFalse((root / "corrupted").exists())

    def test_D03_D05_incompatible_semantics_rejected_before_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            legacy = json.loads((ROOT / "scenarios/task_point_visit_3uav.json").read_text())
            runs = [root / "legacy", root / "shared"]
            failed_evidence(runs[0], legacy, "v1")
            output, _, _ = failed_evidence(runs[1], shared_scene(), "v2")
            with self.assertRaisesRegex(ValueError, "incompatible semantic"):
                build_dataset(runs, root / "mixed")
            self.assertFalse((root / "mixed").exists())
            another = root / "shared_new_rule"
            output2, _, _ = failed_evidence(another, shared_scene(), "v2_new")
            manifest = json.loads((output2 / "manifest.json").read_text())
            manifest["semantic_validation_version"] = "shared_coverage_future"
            write_json(output2 / "manifest.json", manifest)
            write_json(another / "analysis_latest.json", dict(directory=output2.name,
                       manifest_sha256=digest(output2 / "manifest.json")))
            with self.assertRaisesRegex(ValueError, "incompatible semantic"):
                build_dataset([runs[1], another], root / "mixed_rule")


class FinalEligibilityTests(unittest.TestCase):
    def analyze_handmade_evidence(self, root, condition):
        # Geometry is hand chosen: one stationary observer at (1.5, 1.5),
        # radius 4, covers all nine centers of the 3m x 3m region. These
        # observations are independent of the planner's reference coordinates.
        spec = json.loads((ROOT / "missions/recon_shared_3uav.json").read_text(encoding="utf-8"))
        spec["scenario"]["regions"][0].update(width_m=3.0, height_m=3.0)
        spec["scenario"]["vehicles"] = [dict(id="uav_01", sysid=1, east_m=1.5, north_m=-2.0, heading_deg=0.0)]
        spec["mission"]["return_required"] = False
        scene = compile_task(spec)
        self.assertEqual(len(scene["phases"]), 3)
        root.mkdir()
        (root / "raw").mkdir()
        metadata = dict(version=__version__, run_id=condition, scenario=scene, status="completed",
            run_epoch_monotonic_s=100.0, flight_epoch_monotonic_s=102.0,
            mission_end_monotonic_s=108.0, elapsed_s=10.0)
        write_json(root / "metadata.json", metadata)
        write_json(root / "scenario.json", scene)
        events = [dict(event=kind, agent_id="uav_01", t=t) for kind, t in
                  (("armed_confirmed", 1.0), ("airborne_ready", 2.0),
                   ("landing_started", 8.0), ("landed", 9.0))]
        for index, phase in enumerate(scene["phases"]):
            start, end = 2.0 + index * 2, 4.0 + index * 2
            events.extend(dict(event=kind, agent_id="uav_01", phase=phase["name"], t=t) for kind, t in
                (("phase_start_sent", start), ("phase_auto_confirmed", start),
                 ("phase_finished", end), ("task_target_verified", end)))
        (root / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
        raw, truth_packets = [], []
        for index in range(101):
            stamp = index / 10
            up = max(0, min(8.0, (stamp - 1) * 8, (9 - stamp) * 8))
            truth_lat, truth_lon = enu_to_geo(1.5, 1.5, scene["origin"])
            obs_lat, obs_lon = enu_to_geo(10.0 if condition == "disagree" else 1.5, 1.5, scene["origin"])
            raw.append(dict(recv_monotonic_s=100 + stamp, message=dict(mavpackettype="SYSTEM_TIME", time_boot_ms=index * 100)))
            raw.append(dict(recv_monotonic_s=100 + stamp, message=dict(mavpackettype="GLOBAL_POSITION_INT",
                time_boot_ms=index * 100, lat=round(obs_lat * 1e7), lon=round(obs_lon * 1e7),
                alt=round((scene["origin"]["alt_msl_m"] + up) * 1000),
                vx=5100 if condition == "missing" and index == 50 else 0, vy=0, vz=0)))
            truth_packets.append(dict(TimeUS=index * 100000, Lat=truth_lat, Lng=truth_lon,
                Alt=scene["origin"]["alt_msl_m"] + up, Q1=1, Q2=0, Q3=0, Q4=0))
        (root / "raw/uav_01.jsonl").write_text("\n".join(json.dumps(p) for p in raw), encoding="utf-8")
        bin_path = root / "sitl/uav_01/logs/synthetic.BIN"
        bin_path.parent.mkdir(parents=True)
        bin_path.write_bytes(b"Synthetic fixture: DFReader packet stream is mocked by the test")

        def reader(_):
            iterator = iter([SimpleNamespace(get_type=lambda: "SIM", to_dict=lambda p=p: p) for p in truth_packets])
            return SimpleNamespace(recv_match=lambda **_: next(iterator, None), close=lambda: None)

        # Decode, clocks, resampling, semantic/constraint evaluation and the
        # final eligibility gate are real. Only the binary reader is replaced.
        with patch("pymavlink.DFReader.DFReader_binary", side_effect=reader):
            output, quality, labels = analyze_run(root)
        return output, quality, labels

    def test_V07_final_analysis_keeps_coverage_success_but_rejects_missing_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, control, _ = self.analyze_handmade_evidence(root / "control", "control")
            self.assertTrue(control["benchmark_eligible"])
            output, quality, labels = self.analyze_handmade_evidence(root / "missing", "missing")
            self.assertTrue(labels["mission_success"])
            self.assertTrue(labels["mission_success_observation"])
            self.assertEqual(labels["semantic_consistency"], "agree")
            self.assertLess(quality["observation_valid_fraction"]["uav_01"], .99)
            self.assertFalse(quality["data_quality_pass"])
            self.assertTrue(quality["truth_available_pass"])
            self.assertTrue(quality["timing_diagnostic_pass"])
            self.assertFalse(quality["benchmark_eligible"])
            self.assertFalse(quality["strict_benchmark_eligible"])
            exported = build_dataset([root / "missing"], root / "export_missing")
            self.assertFalse(exported["episodes"][0]["benchmark_eligible"])
            saved = json.loads((output / "quality.json").read_text(encoding="utf-8"))
            self.assertFalse(saved["benchmark_eligible"])

    def test_V12_final_analysis_rejects_disagreement_despite_other_gates_passing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output, quality, labels = self.analyze_handmade_evidence(root / "disagree", "disagree")
            self.assertTrue(labels["mission_success"])
            self.assertFalse(labels["mission_success_observation"])
            self.assertEqual(labels["semantic_consistency"], "disagree")
            for gate in ("data_quality_pass", "truth_available_pass", "timing_diagnostic_pass",
                         "run_completed", "execution_constraints_pass"):
                self.assertTrue(quality[gate], gate)
            self.assertEqual(quality["separation_status"], "clear_observed")
            self.assertEqual(quality["truth_separation"]["status"], "clear_observed")
            self.assertFalse(quality["benchmark_eligible"])
            self.assertFalse(quality["strict_benchmark_eligible"])
            exported = build_dataset([root / "disagree"], root / "export_disagree")
            self.assertFalse(exported["episodes"][0]["benchmark_eligible"])
            self.assertFalse(json.loads((output / "manifest.json").read_text(encoding="utf-8"))["benchmark_eligible"])


class TruthBarrierTests(unittest.TestCase):
    def test_D01_rejected_SIM_timestamps_still_bind_BIN_source_hash(self):
        cases = {"valid_duplicate": [(100000, 20), (100000, 20)],
                 "valid_reset": [(100000, 20), (50000, 20)],
                 "invalid_timestamp": [(100000, 20), (float("nan"), 20)],
                 "invalid_duplicate": [(100000, 20), (100000, float("nan"))]}
        for case, stamps in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                run = root / "run"
                failed_evidence(run, shared_scene(), "rejected_truth")
                bin_path = run / "sitl/uav_01/logs/test.BIN"
                bin_path.parent.mkdir(parents=True)
                bin_path.write_bytes(b"synthetic BIN source")
                packets = [dict(TimeUS=stamp, Lat=30, Lng=120, Alt=alt, Q1=1, Q2=0, Q3=0, Q4=0)
                           for stamp, alt in stamps]
                def reader(_):
                    messages = [SimpleNamespace(get_type=lambda: "SIM", to_dict=lambda p=p: p) for p in packets]
                    iterator = iter(messages)
                    return SimpleNamespace(recv_match=lambda **_: next(iterator, None), close=lambda: None)
                with patch("pymavlink.DFReader.DFReader_binary", side_effect=reader):
                    output, quality, _ = analyze_run(run)
                manifest = json.loads((output / "manifest.json").read_text())
                info = json.loads((output / "truth_provenance.json").read_text())["uav_01"]
                self.assertFalse(info["available"])
                self.assertFalse(quality["truth_available_pass"])
                self.assertEqual(manifest["source_sha256"][str(bin_path.relative_to(run))], digest(bin_path))
                build_dataset([run], root / "original_export")
                bin_path.write_bytes(b"changed rejected BIN")
                with self.assertRaisesRegex(ValueError, "run source changed"):
                    build_dataset([run], root / "changed_export")
                self.assertFalse((root / "changed_export").exists())

    def test_V09_SIM_invalid_sample_cannot_reconnect_grid_endpoints(self):
        origin = dict(lat=37, lon=122, alt_msl_m=12)
        packets = [dict(TimeUS=stamp, Lat=37, Lng=122, Alt=alt, Q1=1, Q2=0, Q3=0, Q4=0)
                   for stamp, alt in ((0, 20), (50000, float("nan")), (100000, 20))]
        def reader():
            messages = [SimpleNamespace(get_type=lambda: "SIM", to_dict=lambda p=p: p) for p in packets]
            iterator = iter(messages)
            return SimpleNamespace(recv_match=lambda **_: next(iterator, None), close=lambda: None)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            logs = root / "sitl/uav_01/logs"
            logs.mkdir(parents=True)
            (logs / "test.BIN").touch()
            with patch("pymavlink.DFReader.DFReader_binary", side_effect=lambda _: reader()):
                truth, _, info = read_truth(root, "uav_01", origin, preserve_invalid=True)
                legacy, _, _ = read_truth(root, "uav_01", origin)
            self.assertEqual(len(legacy), 2)
            self.assertEqual(len(truth), 3)
            self.assertIsNone(truth[1][1])
            self.assertEqual(info["invalid_sample_policy"], "barrier")
            self.assertIsNone(resample(truth, [0, 0.1], 0.5)[1][1])


if __name__ == "__main__":
    unittest.main()
