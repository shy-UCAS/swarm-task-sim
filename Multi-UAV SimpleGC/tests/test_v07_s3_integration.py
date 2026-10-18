"""T13–T14: read only the explicitly permitted completed first pilot."""
import json
from pathlib import Path
import unittest

from scripts.run_v07_s3_export import export_runs
from task_v07.s3._common import DATA_ROOT, EXPORT_ROOT, inside, read_json, read_run, verify_episode_manifest
from task_v07.s3.describe import render_description
from task_v07.s3.facts import extract_facts
from task_v07.s3.loader import load_inputs
from task_v07.s3.verify import verify_description


class S3IntegrationTests(unittest.TestCase):
    def require_pilot(self):
        if not (DATA_ROOT / "pilot_f000_005").is_dir():
            self.skipTest("External completed pilot_f000_005 is unavailable")
        return read_run(DATA_ROOT, "pilot_f000_005")

    def test_T13_byte_identical_exports(self):
        self.require_pilot()
        primary = EXPORT_ROOT / "s3_dev_f000_005"
        if not primary.exists():
            export_runs(["pilot_f000_005"], primary.name)
        self.assertTrue((primary / "export_manifest.json").is_file(), "Primary export must have completed")
        repeat = EXPORT_ROOT / "s3_dev_f000_005_repro01"
        export_runs(["pilot_f000_005"], repeat.name)
        for name in ("episodes.jsonl", "descriptions.jsonl"):
            self.assertEqual((primary / name).read_bytes(), (repeat / name).read_bytes(), name)
        with (primary / "episodes.jsonl").open(encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        self.assertEqual(len(rows), 60)
        self.assertEqual(sum(r["split"] == "train" for r in rows), 10)
        self.assertEqual(sum(r["split"] == "val" for r in rows), 30)
        self.assertEqual(sum(r["split"] == "test" for r in rows), 20)
        samples = (primary / "samples_for_review.md").read_text(encoding="utf-8")
        for skeleton in ("family_s15_79c93b22d09e8a7a_ext_001_regular",
                         "family_s15_38bedc9d791d547b_ext_009_regular"):
            self.assertIn(skeleton + "_sequential", samples)

    def test_T14_real_multigroup_penetration(self):
        run, manifest = self.require_pilot()
        entry = next(e for e in manifest["retained_episodes"]
                     if e["skeleton_id"] == "family_s15_38bedc9d791d547b_ext_009_regular" and e["mode"] == "sequential")
        root = inside(run, entry["path"])
        verify_episode_manifest(root, entry["episode_manifest_sha256"])
        row = {"episode_key": "pilot_f000_005/" + entry["episode_id"],
               "path": root.relative_to(DATA_ROOT).as_posix(),
               "episode_manifest_sha256": entry["episode_manifest_sha256"]}
        load_inputs(row, DATA_ROOT, "raw")
        labels, scene = read_json(root / "labels.json"), read_json(root / "public_scene.json")
        facts = extract_facts(labels, scene)["facts"]
        self.assertGreater(facts["n_groups"], 1)
        for group in ("A", "B"):
            record = render_description(facts, row["episode_key"], group)
            self.assertTrue(verify_description(record, labels, scene))
            seen = []
            for sentence in record["sentences"]:
                gid = sentence["group_id"]
                if gid and gid not in seen:
                    seen.append(gid)
                    self.assertTrue(sentence["text"].startswith(f"第{len(seen)}编组（"))
            self.assertEqual(seen, sorted(labels["task_groups"]))
            self.assertIn("该编组", record["text"])


if __name__ == "__main__":
    unittest.main()
