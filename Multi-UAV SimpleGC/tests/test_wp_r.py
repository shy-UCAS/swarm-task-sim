"""WP-R: intent-independent physical sampling and task-semantic seeds."""

import copy
import json
import math
import random
import tempfile
import unittest
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from statistics import NormalDist

from swarm_sim.families import scene_family_id
from swarm_sim.generation import file_hash, generate
from swarm_sim.generation_v2 import (TASK_SEMANTICS_SEED_SCHEME, mission_seed,
                                     normalize_profile, scene_seed, semantic_template_id)
from swarm_sim.mission_v3 import normalize_v3
from swarm_sim.reconnaissance import plan_routes
from swarm_sim.registry import get_intent, temporary_registration
from swarm_sim.scene_samplers import get_sampler, registered_samplers


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "missions/v3/recon_shared_3uav_route.json"
V06_PROFILE = ROOT / "generation_profiles/recon_pilot_v04_v06.json"
V06_GOLDEN = ROOT / "generated/recon_pilot_v04_v06_20261002"
AUDIT_SAMPLE_COUNT = 1000


def template():
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def random_profile():
    return dict(schema_version=2, seed_scheme=TASK_SEMANTICS_SEED_SCHEME,
        master_seed=2026100205, base_scene_count=1, max_candidates_per_base=2,
        scene_sampler=dict(name="random_spawn_v1", params={}),
        shared_mission_params=dict(speeds_m_s=[2.0], return_required=[False]),
        missions=[dict(intent="reconnaissance", template_spec=template(),
                       variant_speed_factors=[1.0])],
        require_all_missions_feasible=True)


def wilson_interval(successes, count, z):
    fraction = successes / count
    denominator = 1 + z * z / count
    center = (fraction + z * z / (2 * count)) / denominator
    half_width = z * math.sqrt(fraction * (1 - fraction) / count + z * z / (4 * count * count)) / denominator
    return [max(0.0, center - half_width), min(1.0, center + half_width)]


class RandomSpawnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = template()
        cls.sampler = get_sampler("random_spawn_v1")
        cls.params = cls.sampler.normalize_params({})
        cls.samples = []
        for index in range(AUDIT_SAMPLE_COUNT):
            seed = scene_seed(2026100205, index, 0)
            # A sampling failure is an R02/R03 failure; never drop the sample.
            scenario, sampled = cls.sampler.sample_scene(
                cls.source["scenario"], cls.params, random.Random(seed))
            cls.samples.append((seed, scenario, sampled))

    def test_r01_same_seed_produces_identical_scene_and_candidate_audit(self):
        seed = scene_seed(2026100205, 31, 0)
        left = self.sampler.sample_scene(self.source["scenario"], self.params, random.Random(seed))
        right = self.sampler.sample_scene(self.source["scenario"], self.params, random.Random(seed))
        self.assertEqual(left, right)
        self.assertTrue(self.sampler.intent_agnostic)
        for key in ("vehicle_count", "formation", "entry_side", "sampler_params", "spatial_slots"):
            self.assertIn(key, left[1])

    def test_r02_1000_unfiltered_scenes_show_random_numbering_and_family_invariance(self):
        by_count = defaultdict(lambda: dict(n=0, one=0, permutation=0))
        # Six simultaneous tests: 99.17% two-sided Wilson intervals give a
        # family-wise false-rejection probability of at most 5% by Bonferroni.
        z = NormalDist().inv_cdf(1 - 0.05 / (2 * 6))
        for _, scenario, sampled in self.samples:
            count = len(scenario["vehicles"])
            side = sampled["entry_side"]
            if side in ("north", "south"):
                rank = lambda v: (v["east_m"], v["north_m"], v["heading_deg"])
            else:
                rank = lambda v: (v["north_m"], v["east_m"], v["heading_deg"])
            spatial = sorted(scenario["vehicles"], key=rank)
            row = by_count[count]
            row["n"] += 1
            row["one"] += int(spatial[0]["id"] == "uav_01")
            row["permutation"] += int([v["id"] for v in spatial] ==
                                      [f"uav_{i:02d}" for i in range(1, count + 1)])
            renumbered = copy.deepcopy(scenario)
            for vehicle in renumbered["vehicles"]:
                index = int(vehicle["id"].split("_")[1])
                new_id = count + 1 - index
                vehicle.update(id=f"uav_{new_id:02d}", sysid=new_id)
            self.assertEqual(scene_family_id(scenario), scene_family_id(renumbered))
        self.assertEqual(sum(row["n"] for row in by_count.values()), AUDIT_SAMPLE_COUNT)
        self.assertEqual(set(by_count), {2, 3, 4})
        report = []
        for count in sorted(by_count):
            row = by_count[count]
            for metric, baseline in (("one", 1 / count), ("permutation", 1 / math.factorial(count))):
                interval = wilson_interval(row[metric], row["n"], z)
                report.append(dict(vehicle_count=count, metric=metric, samples=row["n"],
                                   matches=row[metric], observed=row[metric] / row["n"],
                                   baseline=baseline, confidence_level=1 - 0.05 / 6,
                                   interval=interval))
                self.assertLessEqual(interval[0], baseline, (count, metric, interval))
                self.assertGreaterEqual(interval[1], baseline, (count, metric, interval))
        print("R02_NUMBERING_AUDIT=" + json.dumps(report, sort_keys=True))

    def test_r03_all_1000_scenes_respect_declared_geometry_and_world(self):
        categories = Counter()
        minimum_distance = float("inf")
        world = self.source["scenario"]["world"]
        required = max(8.0, self.source["execution"]["min_separation_m"])
        for _, scenario, sampled in self.samples:
            vehicles = scenario["vehicles"]
            region = scenario["regions"][0]
            width, height = region["width_m"], region["height_m"]
            center_east = region["min_east_m"] + width / 2
            center_north = region["min_north_m"] + height / 2
            self.assertTrue(30 <= width <= 50 and 20 <= height <= 35)
            self.assertTrue(-10 <= center_east <= 10 and -10 <= center_north <= 10)
            self.assertTrue(world["east_bounds_m"][0] <= region["min_east_m"])
            self.assertTrue(region["min_east_m"] + width <= world["east_bounds_m"][1])
            self.assertTrue(world["north_bounds_m"][0] <= region["min_north_m"])
            self.assertTrue(region["min_north_m"] + height <= world["north_bounds_m"][1])
            self.assertEqual(sorted(v["sysid"] for v in vehicles), list(range(1, len(vehicles) + 1)))
            self.assertEqual(sorted(v["id"] for v in vehicles),
                             [f"uav_{i:02d}" for i in range(1, len(vehicles) + 1)])
            side, formation = sampled["entry_side"], sampled["formation"]
            categories[(len(vehicles), side, formation)] += 1
            formation_center = (sampled["formation_center_east_m"],
                                sampled["formation_center_north_m"])
            if side in ("north", "south"):
                normal = ((formation_center[1] - (center_north + height / 2)) if side == "north"
                          else ((center_north - height / 2) - formation_center[1]))
                lateral = formation_center[0] - center_east
                side_length = width
            else:
                normal = ((formation_center[0] - (center_east + width / 2)) if side == "east"
                          else ((center_east - width / 2) - formation_center[0]))
                lateral = formation_center[1] - center_north
                side_length = height
            self.assertTrue(10 <= normal <= 20)
            self.assertLessEqual(abs(lateral), 0.3 * side_length + 1e-9)
            positions = [(slot["east_m"], slot["north_m"]) for slot in sampled["spatial_slots"]]
            if formation == "line":
                deltas = [(b[0] - a[0], b[1] - a[1]) for a, b in zip(positions, positions[1:])]
                spacing = math.hypot(*deltas[0])
                self.assertTrue(8 <= spacing <= 12)
                self.assertTrue(all(abs(math.hypot(*delta) - spacing) < 1e-8 for delta in deltas))
                angle = math.degrees(math.atan2(deltas[0][1], deltas[0][0])) if side in ("north", "south") else (
                    math.degrees(math.atan2(-deltas[0][0], deltas[0][1])))
                self.assertLessEqual(abs(angle), 20 + 1e-8)
            else:
                radius = sampled["cluster_radius_m"]
                self.assertTrue(8 <= radius <= 15)
                self.assertTrue(all(math.dist(position, formation_center) <= radius + 1e-9
                                    for position in positions))
            for vehicle in vehicles:
                self.assertTrue(world["east_bounds_m"][0] <= vehicle["east_m"] <= world["east_bounds_m"][1])
                self.assertTrue(world["north_bounds_m"][0] <= vehicle["north_m"] <= world["north_bounds_m"][1])
                self.assertTrue(0 <= vehicle["heading_deg"] < 360)
                self.assertEqual(vehicle["sysid"], int(vehicle["id"].split("_")[1]))
            for index, left in enumerate(vehicles):
                for right in vehicles[index + 1:]:
                    distance = math.dist((left["east_m"], left["north_m"]),
                                         (right["east_m"], right["north_m"]))
                    minimum_distance = min(minimum_distance, distance)
                    self.assertGreaterEqual(distance + 1e-9, required)
        self.assertEqual(len(self.samples), AUDIT_SAMPLE_COUNT)
        print("R03_SAMPLING_AUDIT=" + json.dumps(dict(samples=len(self.samples),
            category_counts={str(key): value for key, value in sorted(categories.items())},
            minimum_initial_separation_m=minimum_distance), sort_keys=True))

    def test_r03_sampler_configuration_is_version_locked(self):
        for mutation in (dict(vehicle_counts=[2, 3]), dict(entry_sides=["south", "north", "east", "west"]),
                         dict(region_width_m=[30, 51]), dict(cluster_radius_m=[8, True]),
                         dict(extra=1)):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.sampler.normalize_params(mutation)


class AutoAxisAndSeedTests(unittest.TestCase):
    def test_r04_four_entry_directions_and_explicit_axes(self):
        for side, positions, expected in (
            ("north", [(9, 55), (27, 55), (45, 55)], "east"),
            ("south", [(9, -25), (27, -25), (45, -25)], "east"),
            ("east", [(80, 5), (80, 15), (80, 25)], "north"),
            ("west", [(-26, 5), (-26, 15), (-26, 25)], "north"),
        ):
            with self.subTest(side=side):
                spec = template()
                spec.pop("family_id")
                spec["planner"]["params"]["partition_axis"] = "auto"
                for vehicle, (east, north) in zip(spec["scenario"]["vehicles"], positions):
                    vehicle.update(east_m=east, north_m=north)
                plan = plan_routes(normalize_v3(spec))
                self.assertEqual(plan.diagnostics["partition_axis"], expected)
                resolution = plan.diagnostics["partition_axis_resolution"]
                self.assertEqual(resolution["inferred_entry_side"], side)
                self.assertEqual(resolution["resolved_axis"], expected)
        for axis in ("east", "north"):
            spec = template()
            spec["planner"]["params"]["partition_axis"] = axis
            plan = plan_routes(normalize_v3(spec))
            self.assertEqual(plan.diagnostics["partition_axis"], axis)
            self.assertNotIn("partition_axis_resolution", plan.diagnostics)

    def test_r05_multi_intent_sampler_protection(self):
        fixture = replace(get_intent("reconnaissance"), name="fixture_scan")
        data = random_profile()
        copied = template()
        copied["mission"]["intent"] = "fixture_scan"
        data["missions"].append(dict(intent="fixture_scan", template_spec=copied,
                                     variant_speed_factors=[1.0]))
        with temporary_registration(fixture):
            self.assertTrue(get_sampler("random_spawn_v1").intent_agnostic)
            self.assertIn("random_spawn_v1", registered_samplers())
            normalized = normalize_profile(data)
            self.assertEqual(len(normalized["missions"]), 2)
            data["scene_sampler"]["name"] = "strip_aligned_v1"
            data["scene_sampler"]["params"] = {}
            with self.assertRaisesRegex(ValueError, "non-intent-agnostic"):
                normalize_profile(data)

    def test_r06_semantic_seed_ignores_execution_and_explicit_template_id(self):
        left = random_profile()
        right = copy.deepcopy(left)
        left["missions"][0]["template_id"] = "v05_first_label"
        right["missions"][0]["template_id"] = "v05_second_label"
        right["missions"][0]["template_spec"]["execution"]["record_hz"] = 12.0
        right["missions"][0]["template_spec"]["execution"]["terminal_hold_s"] = 1.0
        left_template = normalize_profile(left)["missions"][0]["template_spec"]
        right_template = normalize_profile(right)["missions"][0]["template_spec"]
        self.assertEqual(semantic_template_id(left_template), semantic_template_id(right_template))
        seed = scene_seed(2026100205, 0, 0)
        self.assertEqual(mission_seed(seed, "reconnaissance", semantic_template_id(left_template), 0,
                                      scheme=TASK_SEMANTICS_SEED_SCHEME),
                         mission_seed(seed, "reconnaissance", semantic_template_id(right_template), 0,
                                      scheme=TASK_SEMANTICS_SEED_SCHEME))
        with tempfile.TemporaryDirectory() as directory:
            left_result = generate(left, Path(directory) / "left")
            right_result = generate(right, Path(directory) / "right")
            self.assertEqual([c["scene_seed"] for c in left_result["candidates"]],
                             [c["scene_seed"] for c in right_result["candidates"]])
            self.assertEqual([c.get("family_id") for c in left_result["candidates"]],
                             [c.get("family_id") for c in right_result["candidates"]])
            self.assertEqual([[a["task_seed"] for a in c["attempts"]] for c in left_result["candidates"]],
                             [[a["task_seed"] for a in c["attempts"]] for c in right_result["candidates"]])
            self.assertEqual(left_result["seed_scheme"], TASK_SEMANTICS_SEED_SCHEME)

    def test_r06_v06_profile_missing_seed_scheme_replays_every_json_byte(self):
        golden_files = {p.relative_to(V06_GOLDEN).as_posix(): file_hash(p)
                        for p in V06_GOLDEN.rglob("*.json")}
        self.assertEqual(len(golden_files), 33)
        self.assertEqual(golden_files["generation_manifest.json"],
                         "1403858ce46f3f827d963dbe691432db7fdc4268b607f35f0c2a530c9e0061b9")
        golden_manifest = json.loads((V06_GOLDEN / "generation_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(golden_manifest["artifact_sha256"]), 32)
        self.assertNotIn("seed_scheme", normalize_profile(V06_PROFILE))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "v06_replay"
            generate(V06_PROFILE, output)
            replay_files = {p.relative_to(output).as_posix(): file_hash(p)
                            for p in output.rglob("*.json")}
            self.assertEqual(replay_files, golden_files)
            self.assertEqual(json.loads((output / "generation_manifest.json").read_text(encoding="utf-8"))
                             ["artifact_sha256"], golden_manifest["artifact_sha256"])


if __name__ == "__main__":
    unittest.main()
