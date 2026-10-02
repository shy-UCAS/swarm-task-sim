"""The public scene adapter exposes only target rectangle corners."""

import json
import tempfile
import unittest
from pathlib import Path

from swarm_sim.episode_loader import load_public_scene
from swarm_sim.generation import file_hash


def write_episode(root, task):
    root.mkdir()
    task_file = root / "task.json"
    task_file.write_text(json.dumps(task), encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps({
        "artifact_sha256": {"task.json": file_hash(task_file)}
    }), encoding="utf-8")


class PublicSceneTests(unittest.TestCase):
    def task(self):
        return {
            "scenario": {
                "regions": [
                    {"id": "decoy", "type": "rectangle", "min_east_m": 100,
                     "min_north_m": 200, "width_m": 30, "height_m": 40,
                     "private_marker": "hidden-region"},
                    {"id": "target", "type": "rectangle", "min_east_m": -12.5,
                     "min_north_m": 3.25, "width_m": 30.0, "height_m": 24.0,
                     "private_marker": "hidden-target"}],
                "vehicles": [{"id": "uav_private", "sysid": 7}],
            },
            "mission": {"target_region_id": "target", "intent": "private-intent"},
            "planner": {"secret": "private-plan"},
            "execution": {"secret": "private-execution"},
            "family_id": "private-family",
        }

    def test_only_four_target_enu_corner_pairs_are_returned(self):
        with tempfile.TemporaryDirectory() as temporary:
            episode = Path(temporary) / "episode"
            write_episode(episode, self.task())
            public = load_public_scene(episode)
            self.assertEqual(public, ((-12.5, 3.25), (17.5, 3.25),
                                      (17.5, 27.25), (-12.5, 27.25)))
            self.assertIs(type(public), tuple)
            self.assertTrue(all(type(corner) is tuple and len(corner) == 2
                                and all(type(value) in (int, float) for value in corner)
                                for corner in public))
            self.assertNotIn("private", repr(public))
            self.assertNotIn("uav", repr(public))
            self.assertNotIn("100", repr(public))

    def test_manifest_hash_and_target_reference_are_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            episode = Path(temporary) / "episode"
            task = self.task()
            write_episode(episode, task)
            task["planner"]["secret"] = "modified"
            (episode / "task.json").write_text(json.dumps(task), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact changed"):
                load_public_scene(episode)
            task["mission"]["target_region_id"] = "not-a-region"
            write_episode(Path(temporary) / "bad_target", task)
            with self.assertRaisesRegex(ValueError, "target region"):
                load_public_scene(Path(temporary) / "bad_target")

    def test_invalid_rectangle_dimensions_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            episode = Path(temporary) / "episode"
            task = self.task()
            task["scenario"]["regions"][1]["width_m"] = 0.0
            write_episode(episode, task)
            with self.assertRaisesRegex(ValueError, "positive dimensions"):
                load_public_scene(episode)


if __name__ == "__main__":
    unittest.main()
