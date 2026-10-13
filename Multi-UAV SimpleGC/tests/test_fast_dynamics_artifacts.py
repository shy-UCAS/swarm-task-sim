"""Real offline execution through the public data and language interfaces."""

import copy
import csv
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from swarm_sim.dataset import build_dataset
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.episode_loader import load_episode, load_public_scene
from swarm_sim.fast_dynamics.artifacts import FACTS_VERSION, write_episode
from swarm_sim.fast_dynamics.adapter import _events
from swarm_sim.fast_dynamics.contracts import FastDynamicsConfig, EngineConfig, ExecutionConfig, VehicleProfile
from swarm_sim.fast_dynamics.mission_executor import run_mission
from swarm_sim.generation import file_hash
from swarm_sim.language_v0 import describe_dataset
from swarm_sim.mission_evaluation import source_time
from swarm_sim.recording import write_json
from swarm_sim.tasks import compile_task


FIXTURE = Path(__file__).parent / "fixtures" / "fast_dynamics" / "rapid_passage_0000_v00.json"


class FastDynamicsArtifactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.result = run_mission(cls.task, FastDynamicsConfig())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, result=None, name="run"):
        result = result or self.result
        path = self.root / name
        manifest = write_episode(result.scene, result, path, run_id=name,
            input_hashes={FIXTURE.name: file_hash(FIXTURE)}, config=result.config, seed=20261012)
        return path, manifest

    def test_complete_public_chain_and_source_identity(self):
        run, manifest = self.write()
        dataset = self.root / "dataset"
        exported = build_dataset([run], dataset)
        episode = dataset / "episodes" / "run"
        loaded = load_episode(episode)
        self.assertTrue(manifest["mission_success"])
        self.assertTrue(manifest["episode_quality_eligible"])
        self.assertFalse(manifest["training_eligible"])
        self.assertFalse(manifest["strict_benchmark_eligible"])
        self.assertEqual(len(loaded["t_s"]), (self.result.end_us + 99_999) // 100_000)
        self.assertLess(loaded["t_s"][-1], self.result.end_us / 1e6)
        self.assertEqual(loaded["metadata"]["time_base"], "sim_clock")
        self.assertEqual(np.asarray(loaded["x"]).shape, (manifest["frames"], 2, 6))
        self.assertEqual(len(load_public_scene(episode)), 4)
        source = json.loads((episode / "source.json").read_text(encoding="utf-8"))
        self.assertIn("swarm_sim/fast_dynamics/artifacts.py", source["source_sha256"])
        self.assertEqual(source["input_sha256"][FIXTURE.name], file_hash(FIXTURE))
        self.assertFalse(source["capabilities"]["imu"])
        self.assertFalse((episode / "clock_models.json").exists())
        report = audit_dataset(dataset)
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["episodes"][0]["time_base"], "sim_clock")
        language_root = self.root / "language"
        language = describe_dataset(dataset, language_root)
        self.assertEqual(language["descriptions"], 4)
        facts = json.loads((language_root / "facts" / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(facts["facts_version"], FACTS_VERSION)
        self.assertEqual(facts["channel_check"]["primary_channel"], "fast_dynamics_truth")
        self.assertEqual(facts["channel_check"]["crosscheck_channel"], "ideal_kinematics_observation")
        self.assertEqual(exported["time_base"], "sim_clock")

    def test_short_timeout_stays_unknown_and_retained(self):
        result = run_mission(self.task, FastDynamicsConfig(execution=ExecutionConfig(max_duration_s=.03)))
        run, manifest = self.write(result)
        self.assertEqual(manifest["frames"], 1)
        self.assertEqual(manifest["end_us"], 30_000)
        self.assertIsNone(manifest["mission_success"])
        self.assertEqual(manifest["semantic_consistency"], "unknown")
        self.assertFalse(manifest["episode_quality_eligible"])
        dataset = self.root / "dataset"
        build_dataset([run], dataset)
        language = describe_dataset(dataset, self.root / "language")
        self.assertEqual(language["skipped_episodes"], 1)
        self.assertEqual(language["descriptions"], 0)
        self.assertEqual(audit_dataset(dataset)["counts"]["semantic_unknown"], 1)

    def test_timeout_cannot_be_relabeled_as_completed(self):
        result = run_mission(self.task, FastDynamicsConfig(execution=ExecutionConfig(max_duration_s=.03)))
        with self.assertRaisesRegex(ValueError, "actual terminal event"):
            self.write(replace(result, status="complete"))
        self.assertFalse((self.root / "run" / "analysis_latest.json").exists())

    def test_real_slow_crossing_is_eligible_semantic_failure(self):
        result = run_mission(self.task, FastDynamicsConfig(
            vehicle_profile=VehicleProfile(max_speed_xy_m_s=.3)))
        run, manifest = self.write(result)
        self.assertEqual(manifest["run_status"], "completed")
        self.assertIs(manifest["mission_success"], False)
        self.assertTrue(manifest["episode_quality_eligible"])
        self.assertFalse(manifest["benchmark_eligible"])
        semantic = json.loads((run / "analysis" / "semantic_validation.json").read_text(encoding="utf-8"))
        self.assertIs(semantic["condition_results"]["truth"]["no_dwell"], False)
        dataset = self.root / "dataset"
        build_dataset([run], dataset)
        self.assertEqual(describe_dataset(dataset, self.root / "language")["descriptions"], 4)

    def test_zero_duration_never_qualified(self):
        empty = np.empty((0, 2, 3))
        result = replace(self.result, time_us=np.empty(0, dtype=np.int64), positions=empty, velocities=empty,
            accelerations=empty, support_time_us=np.empty(0, dtype=np.int64), support_positions=empty,
            support_velocities=empty, support_accelerations=empty, end_us=0, events=[], status="timeout")
        run, manifest = self.write(result)
        self.assertEqual(manifest["frames"], 0)
        self.assertFalse(manifest["episode_quality_eligible"])
        loaded = load_episode(run / "analysis")
        self.assertEqual(loaded["x"], [])
        self.assertEqual(loaded["t_s"], [])

    def test_numerical_error_is_not_exported_as_task_failure(self):
        velocity = self.result.support_velocities.copy()
        velocity[10, 0, 0] += 1.0
        result = replace(self.result, support_velocities=velocity)
        with self.assertRaisesRegex(ValueError, "support samples|integration contract"):
            self.write(result)
        self.assertFalse((self.root / "run" / "analysis_latest.json").exists())

    def test_grid_error_rejected_without_completion_marker(self):
        ticks = self.result.time_us.copy()
        ticks[-1] += 1
        with self.assertRaisesRegex(ValueError, "half-open"):
            self.write(replace(self.result, time_us=ticks))
        self.assertFalse((self.root / "run" / "analysis_latest.json").exists())

    def test_runtime_configuration_cannot_be_relabeled(self):
        config = copy.deepcopy(self.result.config)
        config["controller"]["velocity_response_time_s"] *= 2
        with self.assertRaisesRegex(ValueError, "actual runtime configuration"):
            write_episode(self.result.scene, self.result, self.root / "wrong", run_id="wrong",
                input_hashes={FIXTURE.name: file_hash(FIXTURE)}, config=config, seed=1)

    def test_runtime_task_cannot_be_relabeled(self):
        task = copy.deepcopy(self.result.task)
        task["task_id"] += "_other"
        with self.assertRaisesRegex(ValueError, "actual runtime input"):
            write_episode(compile_task(task), self.result, self.root / "wrong", run_id="wrong",
                input_hashes={FIXTURE.name: file_hash(FIXTURE)}, config=self.result.config, seed=1)

    def test_unsupported_capability_cannot_be_rehashed_into_source(self):
        run, manifest = self.write()
        episode = run / "analysis"
        source = json.loads((episode / "source.json").read_text(encoding="utf-8"))
        source["capabilities"]["imu"] = True
        write_json(episode / "source.json", source)
        manifest["artifact_sha256"]["source.json"] = file_hash(episode / "source.json")
        write_json(episode / "manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "source capabilities"):
            load_episode(episode)

    def test_rehashed_export_velocity_cannot_disagree_with_support(self):
        run, manifest = self.write()
        episode = run / "analysis"
        path = episode / "observations.csv"
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            names, rows = reader.fieldnames, list(reader)
        rows[0]["ve_m_s"] = "123.0"
        for name in ("observations.csv", "truth.csv"):
            with (episode / name).open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=names)
                writer.writeheader()
                writer.writerows(rows)
            manifest["artifact_sha256"][name] = file_hash(episode / name)
        write_json(episode / "manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "velocities disagree"):
            load_episode(episode)

    def test_rehashed_semantic_claim_cannot_replace_measured_outcome(self):
        run, manifest = self.write()
        episode = run / "analysis"
        for name in ("labels.json", "semantic_validation.json"):
            value = json.loads((episode / name).read_text(encoding="utf-8"))
            value["mission_success"] = False
            value["mission_success_observation"] = False
            write_json(episode / name, value)
            manifest["artifact_sha256"][name] = file_hash(episode / name)
        manifest["mission_success"] = False
        manifest["benchmark_eligible"] = False
        quality = json.loads((episode / "quality.json").read_text(encoding="utf-8"))
        quality["benchmark_eligible"] = False
        write_json(episode / "quality.json", quality)
        manifest["artifact_sha256"]["quality.json"] = file_hash(episode / "quality.json")
        write_json(episode / "manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "semantic claims disagree"):
            load_episode(episode)

    def test_simulation_clock_is_explicit_bounded_and_old_mapping_unchanged(self):
        self.assertIsNone(source_time(1., None))
        self.assertIsNone(source_time(1., {}))
        clock = dict(kind="simulation_clock", start_s=0., end_s=2.)
        self.assertEqual(source_time(1., clock), 1.)
        self.assertIsNone(source_time(3., clock))
        old = dict(available=True, knots=[(0., 10.), (2., 12.)])
        self.assertEqual(source_time(11., old), 1.)

    def test_reconfirmation_discards_only_revoked_arrival_evidence(self):
        events = [dict(event=kind, phase="transit", agent_id="a", t_us=tick) for kind, tick in (
            ("phase_arrived", 1_000_000), ("phase_hold_ended", 2_000_000),
            ("phase_confirmation_reset", 3_000_000), ("phase_arrived", 4_000_000),
            ("phase_hold_ended", 5_000_000))]
        self.assertEqual(_events(events, "phase_arrived", "transit", "a"), [4.])
        self.assertEqual(_events(events, "phase_hold_ended", "transit", "a"), [5.])
        self.assertEqual(len(events), 5)


if __name__ == "__main__":
    unittest.main()
