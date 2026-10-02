"""Offline compatibility and random-stream checks for fixed-zero v0.5 headings."""

import copy
import json
import random
import tempfile
import unittest
from pathlib import Path

from swarm_sim.families import scene_family_id
from swarm_sim.generation import canonical_hash
from swarm_sim.generation_v2 import generate_v2, normalize_profile, scene_seed
from swarm_sim.scene_samplers import get_sampler


ROOT = Path(__file__).resolve().parents[1]
PROFILE_B = ROOT / "generation_profiles/dual_intent_v05b.json"
PROFILE_C = ROOT / "generation_profiles/dual_intent_v05c.json"
TEMPLATE = ROOT / "missions/v3/recon_route_v05.json"


class FixedHeadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sampler = get_sampler("random_spawn_v2")
        cls.scenario = json.loads(TEMPLATE.read_text(encoding="utf-8"))["scenario"]
        cls.params_b = cls.sampler.normalize_params({})
        cls.params_c = cls.sampler.normalize_params({"heading_policy": "fixed_zero"})

    def test_optional_policy_preserves_v05b_normalization_and_fingerprint(self):
        raw_b = json.loads(PROFILE_B.read_text(encoding="utf-8"))
        raw_c = json.loads(PROFILE_C.read_text(encoding="utf-8"))
        normalized_b = normalize_profile(PROFILE_B)
        normalized_c = normalize_profile(PROFILE_C)
        self.assertEqual(normalized_b["scene_sampler"]["params"], self.params_b)
        self.assertNotIn("heading_policy", self.params_b)
        self.assertEqual(normalized_c["scene_sampler"]["params"], self.params_c)
        self.assertEqual(self.params_c["heading_policy"], "fixed_zero")
        self.assertEqual(canonical_hash(normalized_b),
                         "6253d7cf568e6e8665d6cc8baadd061e3ccd850cc5b25b723ee23da2f78a096c")
        del raw_c["scene_sampler"]["params"]["heading_policy"]
        self.assertEqual(raw_c, raw_b)

    def test_rejects_unsupported_heading_policies(self):
        for value in (None, "uniform", "zero", 0, True, ["fixed_zero"]):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "heading_policy"):
                self.sampler.normalize_params({"heading_policy": value})

    def test_fixed_zero_consumes_same_random_stream_and_preserves_other_draws(self):
        saw_nonzero_baseline_heading = False
        for base_index in range(130):
            for candidate_index in (0, 1, 19):
                seed = scene_seed(2026100205, base_index, candidate_index)
                baseline_rng = random.Random(seed)
                fixed_rng = random.Random(seed)
                baseline_scenario, baseline_sampled = self.sampler.sample_scene(
                    self.scenario, self.params_b, baseline_rng, base_index=base_index)
                fixed_scenario, fixed_sampled = self.sampler.sample_scene(
                    self.scenario, self.params_c, fixed_rng, base_index=base_index)
                self.assertEqual(baseline_rng.getstate(), fixed_rng.getstate())

                baseline_no_heading = copy.deepcopy(baseline_scenario)
                fixed_no_heading = copy.deepcopy(fixed_scenario)
                for scenario in (baseline_no_heading, fixed_no_heading):
                    for vehicle in scenario["vehicles"]:
                        vehicle.pop("heading_deg")
                self.assertEqual(baseline_no_heading, fixed_no_heading)

                baseline_sampled = copy.deepcopy(baseline_sampled)
                fixed_sampled = copy.deepcopy(fixed_sampled)
                self.assertTrue(all(slot["heading_deg"] == 0.0
                                    for slot in fixed_sampled["spatial_slots"]))
                fixed_sampled["sampler_params"].pop("heading_policy")
                for sampled in (baseline_sampled, fixed_sampled):
                    for slot in sampled["spatial_slots"]:
                        slot.pop("heading_deg")
                self.assertEqual(baseline_sampled, fixed_sampled)
                saw_nonzero_baseline_heading |= any(
                    vehicle["heading_deg"] != 0.0 for vehicle in baseline_scenario["vehicles"])
                self.assertTrue(all(vehicle["heading_deg"] == 0.0
                                    for vehicle in fixed_scenario["vehicles"]))
        self.assertTrue(saw_nonzero_baseline_heading)

    def test_v05b_known_scene_identity_remains_unchanged(self):
        seed = scene_seed(2026100205, 0, 0)
        scenario, sampled = self.sampler.sample_scene(
            self.scenario, self.params_b, random.Random(seed), base_index=0)
        self.assertEqual(scene_family_id(scenario), "scene_dd9d028e6626fbf8986e")
        self.assertNotIn("heading_policy", sampled["sampler_params"])

    def test_generation_keeps_v05b_shared_choices_and_routes(self):
        profile_b = normalize_profile(PROFILE_B)
        profile_c = normalize_profile(PROFILE_C)
        for profile in (profile_b, profile_c):
            profile["base_scene_count"] = 3
        with tempfile.TemporaryDirectory() as temp:
            output_b, output_c = Path(temp) / "b", Path(temp) / "c"
            result_b = generate_v2(profile_b, output_b)
            result_c = generate_v2(profile_c, output_c)
            entries_b = json.loads((output_b / "mission_list.json").read_text(encoding="utf-8"))["missions"]
            entries_c = json.loads((output_c / "mission_list.json").read_text(encoding="utf-8"))["missions"]
            self.assertEqual(len(result_b["candidates"]), len(result_c["candidates"]))
            self.assertEqual([base["selected_candidate"] for base in result_b["bases"]],
                             [base["selected_candidate"] for base in result_c["bases"]])
            for baseline, fixed in zip(result_b["candidates"], result_c["candidates"]):
                self.assertEqual((baseline["candidate_id"], baseline["scene_seed"], baseline["status"]),
                                 (fixed["candidate_id"], fixed["scene_seed"], fixed["status"]))
                self.assertEqual(baseline["shared_mission_params"], fixed["shared_mission_params"])
                self.assertNotEqual(baseline["family_id"], fixed["family_id"])
                for old_attempt, new_attempt in zip(baseline["attempts"], fixed["attempts"]):
                    for key in ("status", "task_seed", "lap_sampling"):
                        self.assertEqual(old_attempt.get(key), new_attempt.get(key))
            self.assertEqual([entry["mission_id"] for entry in entries_b],
                             [entry["mission_id"] for entry in entries_c])
            for baseline, fixed in zip(entries_b, entries_c):
                self.assertEqual(baseline["shared_mission_params"], fixed["shared_mission_params"])
                self.assertEqual(baseline["task_seed"], fixed["task_seed"])
                old_task = json.loads((output_b / baseline["task"]).read_text(encoding="utf-8"))
                new_task = json.loads((output_c / fixed["task"]).read_text(encoding="utf-8"))
                old_task.pop("family_id")
                new_task.pop("family_id")
                for task in (old_task, new_task):
                    for vehicle in task["scenario"]["vehicles"]:
                        vehicle.pop("heading_deg")
                self.assertEqual(old_task, new_task)
                old_scene = json.loads((output_b / baseline["scene"]).read_text(encoding="utf-8"))
                new_scene = json.loads((output_c / fixed["scene"]).read_text(encoding="utf-8"))
                self.assertEqual(old_scene["phases"], new_scene["phases"])


if __name__ == "__main__":
    unittest.main()
