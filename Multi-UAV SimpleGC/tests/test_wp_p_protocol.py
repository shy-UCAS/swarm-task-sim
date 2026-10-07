"""WP-P: TaskSpec-bound v0.5 protocol and v0.4 loading/export isolation."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from swarm_sim.analysis import analyze_run, digest
from swarm_sim.dataset import build_dataset
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.episode_loader import load_episode
from swarm_sim.protocol import (PROTOCOL_FIELDS, V05_CONSTRAINT_VERSION, V05_SEMANTIC_VERSION,
                                V3_CONSTRAINT_VERSION, V3_SEMANTIC_VERSION,
                                semantic_protocol, supported_protocols)
from swarm_sim.recording import write_json
from swarm_sim.tasks import compile_task
from swarm_sim.onboard_mission_params import VERSION as ONBOARD_VERSION
from v3_artifact_fixture import make_run, rehash


ROOT = Path(__file__).resolve().parents[1]


def _task(name, *, v05):
    task = json.loads((ROOT / "missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8"))
    task["task_id"] = name
    if v05:
        task["execution"]["async_timing_tolerance"]["max_s"] = 30.
    return task


def _analyzed_failed_run(root, *, v05):
    task = _task(root.name, v05=v05)
    scene = compile_task(task)
    root.mkdir()
    write_json(root / "scenario.json", scene)
    write_json(root / "metadata.json", dict(version="0.5.0-dev", run_id=root.name, scenario=scene,
                                             status="failed", run_epoch_monotonic_s=100., elapsed_s=.1))
    (root / "events.jsonl").write_text("", encoding="utf-8")
    analysis, _, _ = analyze_run(root)
    return root, analysis


def _rehash_analysis_file(analysis, filename):
    manifest_path = analysis / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_sha256"][filename] = digest(analysis / filename)
    write_json(manifest_path, manifest)


class V05ProtocolTests(unittest.TestCase):
    def test_task_features_choose_v2_but_old_schema3_and_other_intents_stay_v1(self):
        old = _task("old", v05=False)
        examples = [copy.deepcopy(old) for _ in range(3)]
        examples[0]["execution"]["hold_semantics"] = "integer_seconds_v1"
        examples[1]["execution"]["async_timing_tolerance"]["max_s"] = 0.
        examples[2]["mission"]["intent"] = "patrol"
        old_protocol = semantic_protocol({"task_spec": old})
        self.assertEqual(old_protocol["semantic_validation_version"], V3_SEMANTIC_VERSION)
        self.assertEqual(old_protocol["execution_constraints_version"], V3_CONSTRAINT_VERSION)
        for task in examples:
            protocol = semantic_protocol({"task_spec": task})
            self.assertEqual(protocol["semantic_validation_version"], V05_SEMANTIC_VERSION)
            self.assertEqual(protocol["execution_constraints_version"], V05_CONSTRAINT_VERSION)
            self.assertEqual({k: protocol[k] for k in PROTOCOL_FIELDS if k not in
                              ("semantic_validation_version", "execution_constraints_version")},
                             {k: old_protocol[k] for k in PROTOCOL_FIELDS if k not in
                              ("semantic_validation_version", "execution_constraints_version")})
        self.assertEqual(len(supported_protocols()), 5)

    def test_real_v04_v06_episode_still_loads(self):
        archive = ROOT / "verification/v04_v06_20261002/dataset/episodes"
        manifest = next(iter(sorted(archive.glob("*/manifest.json"))))
        loaded = load_episode(manifest.parent)
        self.assertEqual(loaded["metadata"]["semantic_validation_version"], V3_SEMANTIC_VERSION)
        self.assertTrue(loaded["t_s"])

    def test_new_analysis_loads_exports_and_audit_accepts_v2_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, analysis = _analyzed_failed_run(root / "new", v05=True)
            manifest = json.loads((analysis / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["semantic_validation_version"], V05_SEMANTIC_VERSION)
            self.assertEqual(manifest["execution_constraints_version"], V05_CONSTRAINT_VERSION)
            self.assertEqual(load_episode(analysis)["metadata"]["semantic_validation_version"], V05_SEMANTIC_VERSION)
            data = build_dataset([run], root / "dataset")
            episode = root / "dataset" / data["episodes"][0]["directory"]
            self.assertEqual(load_episode(episode)["metadata"]["semantic_validation_version"], V05_SEMANTIC_VERSION)
            audit = audit_dataset(root / "dataset")
            self.assertTrue(audit["episodes"][0]["execution_metrics_usable"])
            self.assertEqual(audit["episodes"][0]["execution_metrics_version"], "execution_artifacts_v2")

    def test_new_barrier_contract_does_not_require_route_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            run, analysis = make_run(Path(temp) / "barrier", mode="waypoint_barrier_v1")
            task = json.loads((analysis / "task.json").read_text(encoding="utf-8"))
            task["execution"]["waypoint_hold_s"] = 1.
            task["execution"]["hold_semantics"] = "integer_seconds_v1"
            write_json(analysis / "task.json", task)
            protocol = semantic_protocol({"task_spec": task})
            self.assertEqual(protocol["semantic_validation_version"], V05_SEMANTIC_VERSION)
            self.assertEqual(protocol["execution_constraints_version"], V05_CONSTRAINT_VERSION)
            claims = dict(onboard_mission_param_check_version=ONBOARD_VERSION,
                          onboard_mission_param_check_required=True,
                          onboard_mission_param_check_status="pass", onboard_mission_param_check_pass=True)
            for name in ("manifest.json", "quality.json"):
                value = json.loads((analysis / name).read_text(encoding="utf-8"))
                value.update(protocol, **claims)
                write_json(analysis / name, value)
            labels = json.loads((analysis / "labels.json").read_text(encoding="utf-8"))
            labels["label_provenance"]["semantic_validation_version"] = V05_SEMANTIC_VERSION
            write_json(analysis / "labels.json", labels)
            semantic = json.loads((analysis / "semantic_validation.json").read_text(encoding="utf-8"))
            semantic["semantic_validation_version"] = V05_SEMANTIC_VERSION
            write_json(analysis / "semantic_validation.json", semantic)
            constraints = json.loads((analysis / "execution_constraints.json").read_text(encoding="utf-8"))
            constraints["constraint_validation_version"] = V05_CONSTRAINT_VERSION
            write_json(analysis / "execution_constraints.json", constraints)
            write_json(analysis / "onboard_mission_param_check.json",
                       dict(version=ONBOARD_VERSION, required=True, status="pass", pass_gate=True))
            rehash(run)
            self.assertFalse((analysis / "ac4_timing_v3.json").exists())
            self.assertFalse((analysis / "execution_metrics.json").exists())
            loaded = load_episode(analysis)
            self.assertEqual(loaded["metadata"]["semantic_validation_version"], V05_SEMANTIC_VERSION)

    def test_old_and_new_schema3_cannot_mix_export_in_either_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old, _ = _analyzed_failed_run(root / "old", v05=False)
            new, _ = _analyzed_failed_run(root / "new", v05=True)
            for order, name in (((old, new), "old_first"), ((new, old), "new_first")):
                with self.subTest(order=name):
                    destination = root / name
                    with self.assertRaisesRegex(ValueError, "incompatible semantic"):
                        build_dataset(order, destination)
                    self.assertFalse(destination.exists())

    def test_manifest_protocol_must_match_task_and_v2_evidence_versions(self):
        cases = (
            ("task.json", lambda value: value["execution"]["async_timing_tolerance"].pop("max_s"),
             "TaskSpec semantic protocol mismatch"),
            ("execution_metrics.json", lambda value: value.update(version="execution_artifacts_v1"),
             "inconsistent v0.5 route evidence versions"),
            ("ac4_timing_v3.json", lambda value: value["channels"]["truth"].update(version="wrong"),
             "inconsistent v0.5 route evidence versions"),
        )
        for filename, mutation, expected in cases:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temp:
                _, analysis = _analyzed_failed_run(Path(temp) / "new", v05=True)
                target = analysis / filename
                value = json.loads(target.read_text(encoding="utf-8"))
                mutation(value)
                write_json(target, value)
                _rehash_analysis_file(analysis, filename)
                with self.assertRaisesRegex(ValueError, expected):
                    load_episode(analysis)
        with tempfile.TemporaryDirectory() as temp:
            _, analysis = _analyzed_failed_run(Path(temp) / "old", v05=False)
            target = analysis / "task.json"
            value = json.loads(target.read_text(encoding="utf-8"))
            value["execution"]["async_timing_tolerance"]["max_s"] = 30.
            write_json(target, value)
            _rehash_analysis_file(analysis, "task.json")
            with self.assertRaisesRegex(ValueError, "TaskSpec semantic protocol mismatch"):
                load_episode(analysis)
        with tempfile.TemporaryDirectory() as temp:
            _, analysis = _analyzed_failed_run(Path(temp) / "new", v05=True)
            manifest_path = analysis / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifact_sha256"].pop("ac4_timing_v3.json")
            write_json(manifest_path, manifest)
            with self.assertRaisesRegex(ValueError, "requires versioned route evidence artifacts"):
                load_episode(analysis)


if __name__ == "__main__":
    unittest.main()
