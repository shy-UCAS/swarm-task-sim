"""WP-L binding and independent export tests (synthetic run, no SITL)."""

import json
import tempfile
import unittest
from pathlib import Path

from swarm_sim.dataset import build_dataset
from swarm_sim.generation import file_hash
from swarm_sim.language_v0 import describe_dataset
from test_wp_p_protocol import _analyzed_failed_run


class LanguageExportTests(unittest.TestCase):
    def test_l07_frozen_dataset_binding_and_skip_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run, _ = _analyzed_failed_run(root / "synthetic_failed", v05=True)
            dataset = root / "dataset"
            build_dataset([run], dataset)
            original = file_hash(dataset / "dataset_manifest.json")
            result = describe_dataset(dataset)
            language = root / "dataset_language_zh_v0"
            payload = json.loads((language / "descriptions.json").read_text(encoding="utf-8"))
            self.assertEqual(result["dataset_manifest_sha256"], original)
            self.assertEqual(payload["descriptions"], [])
            self.assertEqual(len(payload["skipped"]), 1)
            self.assertEqual(payload["skipped"][0]["reason"], "episode_quality_ineligible")
            self.assertEqual(file_hash(dataset / "dataset_manifest.json"), original)
            document = json.loads((dataset / "dataset_manifest.json").read_text(encoding="utf-8"))
            document["test_only_mutation"] = True
            (dataset / "dataset_manifest.json").write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "dataset manifest changed"):
                describe_dataset(dataset)

    def test_rejects_changed_episode_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run, _ = _analyzed_failed_run(root / "synthetic_failed", v05=True)
            dataset = root / "dataset"
            exported = build_dataset([run], dataset)
            episode = dataset / exported["episodes"][0]["directory"]
            with (episode / "observations.csv").open("a", encoding="utf-8") as stream:
                stream.write("\n")
            output = root / "language"
            with self.assertRaisesRegex(ValueError, "changed|differs|hash"):
                describe_dataset(dataset, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
