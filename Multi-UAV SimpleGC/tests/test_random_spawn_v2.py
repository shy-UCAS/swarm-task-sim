"""r1.1: stratified, intent-independent line-spawn sampling (no SITL)."""

import copy
import json
import math
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from swarm_sim.generation_v2 import generate_v2, normalize_profile, scene_seed
from swarm_sim.scene_samplers import get_sampler


ROOT = Path(__file__).resolve().parents[1]
RECON = ROOT / "missions/v3/recon_route_v05.json"
PATROL = ROOT / "missions/v3/patrol_route_v05.json"
PROFILE = ROOT / "generation_profiles/dual_intent_v05b.json"


class RandomSpawnV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sampler = get_sampler("random_spawn_v2")
        cls.params = cls.sampler.normalize_params({})
        cls.scenario = json.loads(RECON.read_text(encoding="utf-8"))["scenario"]
        cls.samples = []
        for base_index in range(130):
            for candidate_index in (0, 1, 19):
                seed = scene_seed(2026100205, base_index, candidate_index)
                result = cls.sampler.sample_scene(
                    cls.scenario, cls.params, random.Random(seed), base_index=base_index)
                cls.samples.append((base_index, candidate_index, seed, *result))

    def test_cycle_is_fixed_by_base_index_across_candidates(self):
        self.assertTrue(self.sampler.intent_agnostic)
        self.assertTrue(self.sampler.base_index_dependent)
        counts = Counter()
        for base_index, _, _, scenario, sampled in self.samples:
            expected = [2, 3, 4][base_index % 3]
            self.assertEqual(sampled["base_index"], base_index)
            self.assertEqual(sampled["vehicle_count"], expected)
            self.assertEqual(len(scenario["vehicles"]), expected)
            self.assertEqual(sampled["formation"], "line")
            counts[expected] += 1
        self.assertEqual(counts, {2: 44 * 3, 3: 43 * 3, 4: 43 * 3})

    def test_independent_unit_draws_scale_both_region_dimensions(self):
        for base_index, _, seed, scenario, sampled in self.samples:
            probe = random.Random(seed)
            expected_x = probe.uniform(11.0, 16.0)
            expected_y = probe.uniform(11.0, 16.0)
            self.assertEqual(sampled["region_unit_width_m"], expected_x)
            self.assertEqual(sampled["region_unit_height_m"], expected_y)
            count = [2, 3, 4][base_index % 3]
            region = scenario["regions"][0]
            self.assertEqual(region["width_m"], count * expected_x)
            self.assertEqual(region["height_m"], count * expected_y)
            self.assertEqual(sampled["region_width_m"], region["width_m"])
            self.assertEqual(sampled["region_height_m"], region["height_m"])

    def test_geometry_world_bounds_and_numbering(self):
        world = self.scenario["world"]
        observed_sides = set()
        shuffled_numbering = 0
        for _, _, _, scenario, sampled in self.samples:
            vehicles = scenario["vehicles"]
            region = scenario["regions"][0]
            count = len(vehicles)
            width, height = region["width_m"], region["height_m"]
            center_east = region["min_east_m"] + width / 2
            center_north = region["min_north_m"] + height / 2
            self.assertLessEqual(abs(center_east), 10.0 + 1e-9)
            self.assertLessEqual(abs(center_north), 10.0 + 1e-9)
            self.assertLessEqual(world["east_bounds_m"][0], region["min_east_m"])
            self.assertLessEqual(region["min_east_m"] + width, world["east_bounds_m"][1])
            self.assertLessEqual(world["north_bounds_m"][0], region["min_north_m"])
            self.assertLessEqual(region["min_north_m"] + height, world["north_bounds_m"][1])
            self.assertEqual([v["id"] for v in vehicles], [f"uav_{i:02d}" for i in range(1, count + 1)])
            self.assertEqual([v["sysid"] for v in vehicles], list(range(1, count + 1)))

            side = sampled["entry_side"]
            observed_sides.add(side)
            fc = (sampled["formation_center_east_m"], sampled["formation_center_north_m"])
            if side in ("north", "south"):
                normal = (fc[1] - (center_north + height / 2) if side == "north"
                          else center_north - height / 2 - fc[1])
                lateral = fc[0] - center_east
                side_length = width
            else:
                normal = (fc[0] - (center_east + width / 2) if side == "east"
                          else center_east - width / 2 - fc[0])
                lateral = fc[1] - center_north
                side_length = height
            self.assertAlmostEqual(normal, sampled["entry_distance_m"])
            self.assertTrue(10 <= normal <= 20)
            self.assertAlmostEqual(lateral, sampled["entry_lateral_offset_m"])
            self.assertLessEqual(abs(lateral), 0.3 * side_length + 1e-9)
            self.assertTrue(8 <= sampled["line_spacing_m"] <= 12)
            self.assertTrue(-20 <= sampled["line_rotation_deg"] <= 20)
            slots = sampled["spatial_slots"]
            shuffled_numbering += [slot["id"] for slot in slots] != [
                f"uav_{i:02d}" for i in range(1, count + 1)]
            for left, right in zip(slots, slots[1:]):
                dx = right["east_m"] - left["east_m"]
                dy = right["north_m"] - left["north_m"]
                distance = math.hypot(dx, dy)
                self.assertAlmostEqual(distance, sampled["line_spacing_m"])
                actual_angle = (math.degrees(math.atan2(dy, dx)) if side in ("north", "south")
                                else math.degrees(math.atan2(-dx, dy)))
                self.assertAlmostEqual(actual_angle, sampled["line_rotation_deg"])
            for vehicle in vehicles:
                self.assertTrue(0 <= vehicle["heading_deg"] < 360)
                self.assertTrue(world["east_bounds_m"][0] <= vehicle["east_m"] <= world["east_bounds_m"][1])
                self.assertTrue(world["north_bounds_m"][0] <= vehicle["north_m"] <= world["north_bounds_m"][1])
        self.assertEqual(observed_sides, {"north", "east", "south", "west"})
        self.assertGreater(shuffled_numbering, 0)

    def test_deterministic_intent_independent_and_version_locked(self):
        patrol_scenario = json.loads(PATROL.read_text(encoding="utf-8"))["scenario"]
        seed = scene_seed(2026100205, 7, 3)
        a = self.sampler.sample_scene(self.scenario, self.params, random.Random(seed), base_index=7)
        b = self.sampler.sample_scene(self.scenario, self.params, random.Random(seed), base_index=7)
        c = self.sampler.sample_scene(patrol_scenario, self.params, random.Random(seed), base_index=7)
        self.assertEqual(a, b)
        self.assertEqual(a, c)
        for mutation in (dict(vehicle_counts=[3, 2, 4]), dict(formations=["line", "cluster"]),
                         dict(region_unit_width_m=[10, 16]), dict(line_spacing_m=[8, True]),
                         dict(cluster_radius_m=[8, 15])):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.sampler.normalize_params(mutation)
        for bad in (-1, True, 1.5, None):
            with self.subTest(base_index=bad), self.assertRaises(ValueError):
                self.sampler.sample_scene(self.scenario, self.params, random.Random(seed), base_index=bad)
        self.assertEqual(get_sampler("random_spawn_v1").normalize_params({})["formations"],
                         ["line", "cluster"])

    def test_rejects_region_or_vehicle_outside_world(self):
        seed = scene_seed(2026100205, 0, 0)
        tiny_region_world = copy.deepcopy(self.scenario)
        tiny_region_world["world"]["east_bounds_m"] = [-1, 1]
        with self.assertRaisesRegex(ValueError, "region outside world bounds"):
            self.sampler.sample_scene(tiny_region_world, self.params, random.Random(seed), base_index=0)
        tiny_spawn_world = copy.deepcopy(self.scenario)
        tiny_spawn_world["world"]["east_bounds_m"] = [-20, 20]
        tiny_spawn_world["world"]["north_bounds_m"] = [-50, 50]
        with self.assertRaisesRegex(ValueError, "vehicle outside world bounds"):
            self.sampler.sample_scene(tiny_spawn_world, self.params, random.Random(seed), base_index=0)

    def test_new_profile_preserves_other_generation_settings(self):
        old = json.loads((ROOT / "generation_profiles/dual_intent_v05.json").read_text(encoding="utf-8"))
        new = json.loads(PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(new["max_candidates_per_base"], 20)
        self.assertEqual(new["scene_sampler"]["name"], "random_spawn_v2")
        old.pop("max_candidates_per_base")
        new.pop("max_candidates_per_base")
        old.pop("scene_sampler")
        new.pop("scene_sampler")
        self.assertEqual(old, new)
        normalized = normalize_profile(PROFILE)
        self.assertEqual(normalized["max_candidates_per_base"], 20)
        self.assertEqual(normalized["scene_sampler"]["params"], self.params)

    def test_generator_passes_base_index_into_candidate_audit(self):
        profile = normalize_profile(PROFILE)
        profile["base_scene_count"] = 3
        profile["max_candidates_per_base"] = 1
        with tempfile.TemporaryDirectory() as temp:
            result = generate_v2(profile, Path(temp) / "generation")
        self.assertEqual([candidate["sampled_parameters"]["vehicle_count"]
                          for candidate in result["candidates"]], [2, 3, 4])
        self.assertTrue(all(candidate["sampled_parameters"]["formation"] == "line"
                            for candidate in result["candidates"]))


if __name__ == "__main__":
    unittest.main()
