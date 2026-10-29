"""Frozen dataset component identity, independent of the generation registry."""
import json
from pathlib import Path
import tempfile
import unittest

from swarm_sim.dataset import build_dataset
from swarm_sim.episode_loader import load_episode
from swarm_sim.generation import file_hash
from swarm_sim.protocol import task_metadata
from swarm_sim.recording import write_json
from test_v06_data_contract import _v06_run


class EpisodeComponentVersionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        runs = [_v06_run(self.root / name)[0] for name in ("first", "second")]
        self.directory = self.root / "dataset"
        self.dataset = build_dataset(runs, self.directory)
        self.episodes = [self.directory / e["directory"] for e in self.dataset["episodes"]]

    def save_dataset(self):
        write_json(self.directory / "dataset_manifest.json", self.dataset)

    def freeze_versions(self, index, **changes):
        """Only synthetic temporary data is rewritten, with valid hash bindings."""
        episode = self.episodes[index]
        task = json.loads((episode / "task.json").read_text(encoding="utf-8"))
        manifest = json.loads((episode / "manifest.json").read_text(encoding="utf-8"))
        task["component_versions"].update(changes)
        manifest["component_versions"].update(changes)
        write_json(episode / "task.json", task)
        if "validator" in changes:
            labels = json.loads((episode / "labels.json").read_text(encoding="utf-8"))
            labels["label_provenance"]["validator_versions"] = {task["mission"]["intent"]: changes["validator"]}
            for behavior in labels["observed_behaviors"]:
                behavior["rule_version"] = changes["validator"]
            write_json(episode / "labels.json", labels)
        for name in manifest["artifact_sha256"]:
            manifest["artifact_sha256"][name] = file_hash(episode / name)
        write_json(episode / "manifest.json", manifest)
        entry = self.dataset["episodes"][index]
        entry["component_versions"].update(changes)
        entry["analysis_manifest_sha256"] = file_hash(episode / "manifest.json")
        self.save_dataset()

    def test_historical_components_load_and_return_own_metadata(self):
        before = load_episode(self.episodes[0])
        versions = dict(planner="equal_strip_lawnmower_v0", validator="shared_coverage_v1",
                        facts="observer_facts_v06", templates="templates_zh_v05")
        for index in range(2):
            self.freeze_versions(index, **versions)
        loaded = load_episode(self.episodes[0])
        self.assertEqual(loaded["metadata"]["component_versions"], versions)
        self.assertEqual(loaded["metadata"].keys(), before["metadata"].keys())
        for key in ("x", "mask", "t_s", "agent_ids"):
            self.assertEqual(loaded[key], before[key])
        # Stored labels are returned as-is, including their historical provenance.
        self.assertEqual(loaded["targets"], json.loads((self.episodes[0] / "labels.json").read_text()))

    def test_facts_only_change_preserves_features_masks_and_targets(self):
        before = load_episode(self.episodes[0])
        for index in range(2):
            self.freeze_versions(index, facts="observer_facts_v06")
        loaded = load_episode(self.episodes[0])
        for key in ("x", "mask", "targets"):
            self.assertEqual(loaded[key], before[key])

    def test_episode_disagrees_with_own_dataset_entry_rejected(self):
        self.dataset["episodes"][0]["component_versions"]["facts"] = "observer_facts_v06"
        self.save_dataset()
        with self.assertRaisesRegex(ValueError, "dataset and v3 episode metadata disagree"):
            load_episode(self.episodes[0])

    def test_same_validator_with_two_versions_anywhere_in_dataset_rejected(self):
        self.freeze_versions(1, validator="shared_coverage_v3")
        # Both episodes still match their own entries and every artifact hash.
        for episode in self.episodes:
            with self.subTest(episode=episode.name):
                with self.assertRaisesRegex(ValueError, "dataset mixes component versions: shared_coverage"):
                    load_episode(episode)

    def test_distinct_named_components_coexist_without_scope_mapping(self):
        self.freeze_versions(1, validator="another_coverage_v1", planner="another_planner_v3")
        # Same intent/pattern, different component names: no intent/pattern mapping.
        for episode in self.episodes:
            self.assertEqual(len(load_episode(episode)["x"]), 3)

    def test_artifact_and_manifest_hash_bindings_remain_enforced(self):
        episode = self.episodes[0]
        csv = episode / "observations.csv"
        original = csv.read_bytes()
        csv.write_bytes(original + b"\n")
        with self.assertRaisesRegex(ValueError, "episode artifact changed: observations.csv"):
            load_episode(episode)
        csv.write_bytes(original)
        manifest = episode / "manifest.json"
        manifest.write_bytes(manifest.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "episode manifest differs from frozen dataset selection"):
            load_episode(episode)

    def test_generation_default_still_checks_current_registry(self):
        self.freeze_versions(0, facts="observer_facts_v06")
        task = json.loads((self.episodes[0] / "task.json").read_text())
        with self.assertRaisesRegex(ValueError, "component versions differ"):
            task_metadata(task)


if __name__ == "__main__":
    unittest.main()
