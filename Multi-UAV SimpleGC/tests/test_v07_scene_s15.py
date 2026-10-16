"""S15 instruction tests: prescribed constants, tolerances and fixed seeds."""
import math
import random
import unittest
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from shapely.geometry import LineString, Point, Polygon

from scene_v07.layout_s15 import base_distance, bisect_t, load_layout_config, signed_gap
from scene_v07.sampling import _contour, _move, sample_family
from scene_v07.contract import SceneConfig, canonical_json
from scene_v07.geometry import center_of
from scene_v07.sampling_s11 import MAP_SIDES_M, SamplingPolicy, SamplingRejected, facility_count


def circle(x, y, radius):
    return {"type": "Circle", "center_m": [x, y], "radius_m": radius}


def square(x, y, half):
    return {"type": "Polygon", "vertices_m": [[x-half, y-half], [x+half, y-half],
                                                [x+half, y+half], [x-half, y+half]]}


class ExactLayoutTests(unittest.TestCase):
    def test_hand_calculated_distances(self):
        cases = [(circle(0, 0, 2), circle(10, 0, 3), 5),
                 (circle(10, 0, 2), square(0, 0, 1), 7),
                 (square(0, 0, 1), square(5, 6, 1), 5)]
        for a, b, expected in cases:
            self.assertAlmostEqual(base_distance(a, b), expected, delta=1e-9)
            self.assertAlmostEqual(base_distance(b, a), expected, delta=1e-9)
        self.assertEqual(base_distance(circle(0, 0, 2), square(0, 0, 1)), 0)

    def test_200_bisections_attain_minimal_translation(self):
        rng, cfg = random.Random(15002), load_layout_config()[0]
        for _ in range(200):
            a, b = _contour(rng, True), _contour(rng, True)
            theta, target = rng.uniform(0, 2*math.pi), rng.uniform(1, 4000)
            t = bisect_t(a, b, theta, target, cfg)
            move = lambda distance: _move(b, [distance*math.cos(theta), distance*math.sin(theta)])
            self.assertAlmostEqual(base_distance(a, move(t)), target, delta=1e-3)
            self.assertLess(base_distance(a, move(t-.01)), target)

    def test_1000_r2_pairs_imply_ordered_r1_lower_bound(self):
        rng = random.Random(15004)
        for _ in range(1000):
            wi, wj = rng.uniform(300, 800), rng.uniform(300, 800)
            d2i, d2j = rng.uniform(200, 550), rng.uniform(200, 550)
            d1i, d1j = d2i+wi, d2j+wj
            g = rng.uniform(-.2*min(wi, wj), 1000)
            a, b = circle(0, 0, 40), circle(d1i+d1j+g+100, 0, 60)
            self.assertGreaterEqual(signed_gap(a, d2i, b, d1j), .8*wi-1e-6)
            self.assertGreaterEqual(signed_gap(b, d2j, a, d1i), .8*wj-1e-6)

    def test_r2_boundary_independent_checker(self):
        # Integration assertion is run after the S15-3 checker commit.
        from scene_v07.checks import check_layout_s15
        for delta, expected in ((.01, False), (-.01, True)):
            facilities = [{"id": "a", "geometry": circle(1500, 1500, 40)},
                          {"id": "b", "geometry": circle(1500+80+1400-100+delta, 1500, 40)}]
            layers = {f["id"]: {"alert": {"offset_m": 200}, "warning": {"offset_m": 700}} for f in facilities}
            codes = [i["code"] for i in check_layout_s15(facilities, layers, "linear", (0, 0, 5000, 5000))]
            self.assertEqual("s15_warning_overlap_exceeds_bound" in codes, expected)
            if not expected:
                self.assertEqual(codes, [])


def components(scene):
    facilities = [e for e in scene["entities"] if e["type"] == "facility"]
    layers = {f["id"]: {e["layer"]: e for e in scene["entities"]
                         if e.get("facility_id") == f["id"]} for f in facilities}
    return facilities, layers


class SamplingS15Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Select by the prescribed first RNG draws, never filter rejected output.
        seeds = {layout: [] for layout in ("single", "isolated", "clustered", "linear")}
        for seed in range(1000):
            rng = random.Random(seed)
            layout = "single" if facility_count(rng) == 1 else rng.choice(["isolated", "clustered", "linear"])
            if len(seeds[layout]) < 20:
                seeds[layout].append(seed)
            if all(len(values) == 20 for values in seeds.values()):
                break
        cls.families = {layout: [sample_family(seed, revision="s1.5") for seed in values]
                        for layout, values in seeds.items()}

    def test_each_layout_20_families_pass_all_s15_checks(self):
        from scene_v07.checks import check_layout_s15
        for layout, families in self.families.items():
            self.assertEqual(len(families), 20)
            for scene, family in families:
                facilities, layers = components(scene)
                side = family["map_side_m"]
                self.assertEqual(family["layout"], layout)
                self.assertEqual(check_layout_s15(facilities, layers, layout, (0, 0, side, side)), [])
                if layout == "clustered":
                    seen = {0}
                    for _ in facilities:
                        for i, a in enumerate(facilities):
                            for j, b in enumerate(facilities):
                                if i in seen and signed_gap(a["geometry"], layers[a["id"]]["warning"]["offset_m"],
                                                           b["geometry"], layers[b["id"]]["warning"]["offset_m"]) <= 0:
                                    seen.add(j)
                    self.assertEqual(len(seen), len(facilities))
                if layout == "linear":
                    centers = [center_of(f["geometry"]) for f in facilities]
                    line = LineString([centers[0], centers[-1]])
                    self.assertLessEqual(max(line.distance(Point(c)) for c in centers), 1e-6)

    def test_map_size_and_exact_350m_clearance(self):
        for families in self.families.values():
            for scene, family in families:
                facilities, layers = components(scene)
                side = family["map_side_m"]
                self.assertLessEqual(side, 8000)
                self.assertEqual(side % 250, 0)
                self.assertGreaterEqual(side, MAP_SIDES_M[len(facilities)])
                for f in facilities:
                    g, d1 = f["geometry"], layers[f["id"]]["warning"]["offset_m"]
                    if g["type"] == "Circle":
                        x, y = g["center_m"]
                        r = g["radius_m"]
                        bounds = x-r, y-r, x+r, y+r
                    else:
                        bounds = Polygon(g["vertices_m"]).bounds
                    clearance = min(bounds[0], bounds[1], side-bounds[2], side-bounds[3])-d1
                    self.assertGreaterEqual(clearance, 350-1e-6)

    def test_policy_forwarding_and_reconstruction(self):
        policy = SamplingPolicy(obstacle_attempts=24, radar_attempts=40)
        scene, family = sample_family(0, revision="s1.5", policy=policy)
        rebuilt = sample_family(0, SceneConfig(**family["config"]), revision="s1.5",
                                policy=SamplingPolicy(**family["sampling_policy"]))
        self.assertEqual(canonical_json((scene, family)), canonical_json(rebuilt))
        self.assertEqual(family["sampling_policy"], {"facility_attempts": 128, "obstacle_attempts": 24, "radar_attempts": 40})
        for link in family["layout_s15"]["links"]:
            self.assertLessEqual(abs(link["target_gap_m"]-link["achieved_gap_m"]), 1e-3)

    def test_layout_exhaustion_retains_reason_without_public_schema(self):
        cfg, digest = load_layout_config()
        cfg = {**cfg, "max_map_side_m": 1, "layout_attempts": 2}
        with patch("scene_v07.sampling_s15.load_layout_config", return_value=(cfg, digest)):
            with self.assertRaises(SamplingRejected) as caught:
                sample_family(0, revision="s1.5")
        self.assertEqual(caught.exception.code, "sampling_layout_s15_exhausted")
        self.assertEqual(caught.exception.family["layout_s15"]["rejected_attempt_reasons"]["layout_exceeds_max_map"], 2)
        self.assertNotIn("schema_version", caught.exception.scene)


class LegacyRevisionTests(unittest.TestCase):
    def test_15_prechange_hash_pairs(self):
        baseline = json.loads((Path(__file__).parent / "data/v07_s15_legacy_hashes.json").read_text(encoding="utf-8"))
        self.assertEqual(len(baseline["rows"]), 15)
        for row in baseline["rows"]:
            with self.subTest(revision=row["revision"], seed=row["seed"]):
                try:
                    scene, family = sample_family(row["seed"], revision=row["revision"])
                    rejected = None
                except SamplingRejected as failure:
                    scene, family, rejected = failure.scene, failure.family, failure.code
                self.assertEqual(rejected, row["rejected"])
                self.assertEqual(hashlib.sha256(canonical_json(scene)).hexdigest(), row["public_scene_sha256"])
                self.assertEqual(hashlib.sha256(canonical_json(family)).hexdigest(), row["family_sha256"])


if __name__ == "__main__":
    unittest.main()
