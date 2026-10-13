"""S1 contract/geometry tests, independent of fastsim and matplotlib."""
import ast
from copy import deepcopy
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import unittest

from shapely.geometry import LineString, Point, Polygon

from scene_v07 import SceneConfig, canonical_json, check_family, family_seed, sample_family, validate_public_scene
from scene_v07.checks import angle_arcs, max_span
from scene_v07.contract import schema_path
from scene_v07.geometry import VisibilityPlanner, expand_geometry, polyline_length, to_shape


def rectangle(x0, y0, x1, y1):
    return {"type": "Polygon", "vertices_m": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}


def planner_scene(*geometries):
    return {"world": {"geometry": rectangle(0, 0, 10, 10)},
            "entities": [{"id": f"x{i}", "type": "hard_constraint_obstacle", "geometry": g}
                         for i, g in enumerate(geometries)]}


class BufferTests(unittest.TestCase):
    def test_circle_expansion_adds_distance_to_contour(self):
        circle = {"type": "Circle", "center_m": [80, 140], "radius_m": 40}
        self.assertEqual(expand_geometry(circle, 75),
                         {"type": "Circle", "center_m": [80, 140], "radius_m": 115})
        self.assertEqual(circle["radius_m"], 40)

    def test_polygon_expansion_is_round_euclidean_offset(self):
        contour = rectangle(-50, -50, 50, 50)
        expanded = expand_geometry(contour, 30)
        self.assertEqual(expanded["vertices_m"], contour["vertices_m"])
        shape = to_shape(expanded, quad_segs=128)
        self.assertEqual(shape.bounds, (-80, -80, 80, 80))
        self.assertAlmostEqual(shape.area, 10000 + 400 * 30 + math.pi * 30**2, delta=.1)
        self.assertTrue(shape.covers(Point(79, 0)))
        self.assertFalse(shape.covers(Point(75, 75)))
        self.assertLess(shape.hausdorff_distance(Polygon(contour["vertices_m"]).buffer(30, quad_segs=128)), 1e-9)

    def test_expansions_are_nested_and_compose(self):
        contour = rectangle(0, 0, 200, 80)
        a, b, c = [expand_geometry(contour, distance) for distance in (75, 300, 800)]
        self.assertTrue(to_shape(b).covers(to_shape(a)))
        self.assertTrue(to_shape(c).covers(to_shape(b)))
        self.assertEqual(expand_geometry(a, 225), b)

    def test_enclosing_tessellation_covers_finer_true_contour(self):
        for geometry in [{"type": "Circle", "center_m": [0, 0], "radius_m": 430},
                         expand_geometry(rectangle(-80, -50, 80, 50), 30)]:
            fine = to_shape(geometry, quad_segs=512)
            conservative = to_shape(geometry, quad_segs=8, conservative=True)
            self.assertTrue(conservative.buffer(1e-8).covers(fine))

    def test_oblique_convex_offset_encloses_exact_round_corners(self):
        contour = {"type": "Polygon", "vertices_m": [
            [1078.428684543277, 1964.7369766117422],
            [779.2393267081508, 1998.5837581321723],
            [613.0459179319539, 2269.81430385656],
            [726.3450256203635, 2548.6781347203423],
            [982.3677457454933, 2639.8147494116793],
            [1267.889675549004, 2472.337692980773],
            [1298.9248863446896, 2179.3639740837757]]}
        raw = to_shape(contour)
        enclosed = to_shape(expand_geometry(contour, 30), 8, True)
        self.assertGreaterEqual(enclosed.exterior.distance(raw), 30 - 1e-7)
        self.assertTrue(enclosed.buffer(1e-8).covers(raw.buffer(30, quad_segs=512)))

    def test_random_convex_offset_boundaries_preserve_analytic_margin(self):
        for seed in range(30):
            scene, _ = sample_family(seed)
            for entity in scene["entities"]:
                geometry = entity["geometry"]
                if entity["type"] == "hard_constraint_obstacle" and geometry["type"] == "Polygon":
                    raw = to_shape(geometry)
                    enclosed = to_shape(expand_geometry(geometry, 30), 8, True)
                    self.assertGreaterEqual(enclosed.exterior.distance(raw), 30 - 1e-7)

    def test_expansion_rejects_invalid_distances_and_points(self):
        for distance in (0, -1, math.inf, math.nan):
            with self.assertRaises(ValueError):
                expand_geometry(rectangle(0, 0, 1, 1), distance)
        with self.assertRaises(ValueError):
            expand_geometry({"type": "Point", "position_m": [0, 0]}, 1)


class VisibilityTests(unittest.TestCase):
    def assert_clear(self, planner, path):
        self.assertIsNotNone(path)
        self.assertTrue(planner.world.covers(LineString(path)))
        for a, b in zip(path, path[1:]):
            self.assertTrue(planner.visible(a, b))
            self.assertFalse(planner.interior.intersects(LineString([a, b])))

    def test_empty_map_returns_straight_shortest_path(self):
        planner = VisibilityPlanner(planner_scene(), 0)
        self.assertEqual(planner.path([1, 1], [9, 9]), [[1, 1], [9, 9]])
        self.assertEqual(planner.path([1, 1], [1, 1]), [[1, 1]])

    def test_rectangle_path_is_the_analytic_shortest_path(self):
        planner = VisibilityPlanner(planner_scene(rectangle(4, 4, 6, 6)), 0)
        path = planner.path([1, 5], [9, 5])
        self.assert_clear(planner, path)
        self.assertAlmostEqual(polyline_length(path), 2 * math.sqrt(10) + 2, places=8)

    def test_circle_path_never_cuts_the_exact_safety_buffer(self):
        scene = {"world": {"geometry": rectangle(0, 0, 1000, 1000)}, "entities": [
            {"type": "hard_constraint_obstacle", "geometry": {"type": "Circle", "center_m": [500, 500], "radius_m": 100}}]}
        planner = VisibilityPlanner(scene, 30)
        path = planner.path([50, 500], [950, 500])
        self.assert_clear(planner, path)
        self.assertGreater(polyline_length(path), 900)
        for a, b in zip(path, path[1:]):
            self.assertGreaterEqual(LineString([a, b]).distance(Point(500, 500)), 130 - 1e-7)

    def test_polygon_path_respects_thirty_meter_margin(self):
        raw = rectangle(400, 400, 600, 600)
        scene = {"world": {"geometry": rectangle(0, 0, 1000, 1000)},
                 "entities": [{"type": "hard_constraint_obstacle", "geometry": raw}]}
        planner = VisibilityPlanner(scene, 30)
        path = planner.path([50, 500], [950, 500])
        self.assert_clear(planner, path)
        self.assertGreaterEqual(LineString(path).distance(to_shape(raw)), 30 - 1e-7)

    def test_overlapping_obstacles_use_union_boundary(self):
        planner = VisibilityPlanner(planner_scene(rectangle(3, 3, 6, 6), rectangle(5, 4, 7, 7)), .2)
        path = planner.path([1, 5], [9, 5])
        self.assert_clear(planner, path)
        for raw in [rectangle(3, 3, 6, 6), rectangle(5, 4, 7, 7)]:
            self.assertGreaterEqual(LineString(path).distance(to_shape(raw)), .2 - 1e-7)

    def test_world_spanning_wall_cannot_be_bypassed_at_boundary(self):
        planner = VisibilityPlanner(planner_scene(rectangle(4, -1, 6, 11)), 0)
        self.assertIsNone(planner.path([1, 5], [9, 5]))

    def test_boundary_crossing_obstacle_detours_inside_world(self):
        planner = VisibilityPlanner(planner_scene(rectangle(-2, -2, 5, 5)), 0)
        self.assert_clear(planner, planner.path([6, 1], [1, 6]))

    def test_invalid_endpoints_have_no_route(self):
        planner = VisibilityPlanner(planner_scene(rectangle(4, 4, 6, 6)), 0)
        self.assertIsNone(planner.path([5, 5], [9, 9]))
        self.assertIsNone(planner.path([1, 1], [-1, 9]))

    def test_protection_zones_never_become_obstacles(self):
        scene = planner_scene()
        scene["entities"] = [{"type": "protection_zone", "geometry": rectangle(4, -1, 6, 11)},
                             {"type": "facility", "geometry": rectangle(3, 3, 7, 7)}]
        planner = VisibilityPlanner(scene, 30)
        self.assertEqual(planner.path([1, 5], [9, 5]), [[1, 5], [9, 5]])

    def test_random_endpoint_paths_are_clear(self):
        rng = random.Random(271)
        planner = VisibilityPlanner(planner_scene(rectangle(3, 2, 5, 7), rectangle(6, 4, 8, 9)), .1)
        for _ in range(60):
            start, end = [rng.uniform(.1, 9.9), rng.uniform(.1, 9.9)], [rng.uniform(.1, 9.9), rng.uniform(.1, 9.9)]
            if planner.free(start) and planner.free(end):
                self.assert_clear(planner, planner.path(start, end))


class SamplingContractTests(unittest.TestCase):
    def test_same_seed_is_byte_identical_including_initial_states(self):
        for seed in (0, 1, 44, family_seed(2026101307, 299)):
            a, b = sample_family(seed)
            c, d = sample_family(seed)
            self.assertEqual(canonical_json(a), canonical_json(c))
            self.assertEqual(canonical_json(b), canonical_json(d))

    def test_reproducibility_in_separate_interpreter(self):
        code = "from scene_v07 import sample_family,canonical_json; import hashlib; a,b=sample_family(20261013); print(hashlib.sha256(canonical_json([a,b])).hexdigest())"
        outputs = [subprocess.check_output([sys.executable, "-B", "-c", code], text=True).strip() for _ in range(2)]
        self.assertEqual(outputs[0], outputs[1])

    def test_seed_stream_is_independent_of_batch_order(self):
        indices = [0, 17, 3, 299, 18]
        seeds = {i: family_seed(2026101307, i) for i in indices}
        self.assertEqual(seeds, {i: family_seed(2026101307, i) for i in reversed(indices)})
        self.assertEqual(len(set(seeds.values())), len(seeds))
        self.assertNotEqual(family_seed(1, 0), family_seed(2, 0))

    def test_sample_ranges_and_family_membership(self):
        layouts, placements = set(), set()
        for seed in range(75):
            public, family = sample_family(seed)
            validate_public_scene(public)
            layouts.add(family["layout"])
            placements.update(p["placement"] for p in family["obstacle_placements"])
            self.assertTrue(4 <= family["vehicle_count"] <= 12)
            self.assertTrue(4 <= family["cruise_speed_m_s"] <= 10)
            self.assertTrue(15 <= family["lateral_spacing_m"] <= 25)
            entry_shapes = {e["id"]: to_shape(e["geometry"]) for e in public["entry_zones"]}
            for state in family["initial_states"]:
                self.assertEqual(len(state["position_enu_m"]), 3)
                self.assertEqual(state["position_enu_m"][2], family["task_altitude_m"])
                self.assertTrue(entry_shapes[state["entry_id"]].covers(Point(state["position_enu_m"][:2])))
            entities = public["entities"]
            for facility in [e for e in entities if e["type"] == "facility"]:
                offsets = {e["layer"]: e["offset_m"] for e in entities if e.get("facility_id") == facility["id"]}
                self.assertTrue(50 <= offsets["protected"] <= 150)
                self.assertTrue(150 <= offsets["alert"] - offsets["protected"] <= 400)
                self.assertTrue(300 <= offsets["warning"] - offsets["alert"] <= 800)
        self.assertEqual(layouts, {"single", "isolated", "clustered", "linear"})
        self.assertEqual(placements, {"entry_blocking", "facility_side", "between_facilities"})

    def test_public_contract_has_no_semantic_or_audit_fields_recursively(self):
        forbidden = {"target", "target_id", "target_facility_id", "groups", "group_id", "members", "role", "roles",
                     "batch", "intent", "planned_path", "routes", "sampling_seed", "family_id", "map_id", "initial_states"}
        def walk(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & forbidden)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        for seed in range(10):
            public, family = sample_family(seed)
            walk(public)
            self.assertEqual(family["sampling_seed"], seed)
            self.assertFalse(set(family) & {"group_count", "group_sizes", "roles", "target_facility_id", "task_units"})

    def test_unknown_fields_rejected_at_all_levels(self):
        public, _ = sample_family(1)
        for location in ((), ("world",), ("units",), ("entities", 0), ("entities", 0, "geometry"), ("entry_zones", 0)):
            modified = deepcopy(public)
            value = modified
            for part in location:
                value = value[part]
            value["target_facility_id"] = "facility_01"
            with self.subTest(location=location), self.assertRaises(ValueError):
                validate_public_scene(modified)

    def test_bad_id_units_and_layer_associations_rejected(self):
        public, _ = sample_family(3)
        for mutation in ("duplicate", "units", "dangling", "missing_layer"):
            modified = deepcopy(public)
            if mutation == "duplicate":
                modified["entities"][1]["id"] = modified["entities"][0]["id"]
            elif mutation == "units":
                modified["units"]["length"] = "km"
            elif mutation == "dangling":
                modified["entities"][1]["facility_id"] = "unknown"
            else:
                modified["entities"].pop(1)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_public_scene(modified)

    def test_json_schema_agrees_with_generated_maps(self):
        # Use the environment's existing optional validator to verify the
        # published consumer schema. Runtime validation has no such dependency.
        import jsonschema
        schema = json.loads(schema_path().read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        validator.check_schema(schema)
        for seed in range(10):
            public, _ = sample_family(seed)
            validator.validate(public)
        public["group_id"] = "hidden"
        self.assertTrue(list(validator.iter_errors(public)))

    def test_nonfinite_geometry_and_nonconvex_contours_rejected(self):
        public, _ = sample_family(1)
        modified = deepcopy(public)
        modified["entities"][0]["geometry"] = {"type": "Circle", "center_m": [math.nan, 0], "radius_m": 40}
        with self.assertRaises(ValueError):
            validate_public_scene(modified)
        modified["entities"][0]["geometry"] = {"type": "Polygon", "vertices_m": [[0, 0], [5, 0], [2, 1], [5, 5], [0, 5]]}
        with self.assertRaises(ValueError):
            validate_public_scene(modified)

    def test_invalid_config_and_seeds_rejected(self):
        for config in ({"angle_step_deg": 7}, {"safety_margin_m": -1}, {"altitude_max_m": 50}, {"map_side_m": math.nan}):
            with self.assertRaises(ValueError):
                SceneConfig(**config)
        for seed in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                sample_family(seed)
            with self.assertRaises(ValueError):
                family_seed(seed, 0)

    def test_core_and_test_modules_do_not_import_matplotlib(self):
        project = Path(__file__).resolve().parents[1]
        for path in [*(project / "scene_v07").glob("*.py"), *project.glob("tests/test_v07_scene*.py")]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            self.assertFalse(any(name.startswith("matplotlib") for name in imports), str(path))
        code = "import scene_v07, scene_v07.batch, sys; assert not any(x.startswith('matplotlib') for x in sys.modules)"
        subprocess.check_call([sys.executable, "-B", "-c", code])


class CheckerTests(unittest.TestCase):
    def test_angular_bins_and_wraparound(self):
        self.assertEqual(angle_arcs([True, False, False, True], 90), [[0, 90], [270, 360]])
        self.assertEqual(max_span([True, False, False, True], 90), 180)
        self.assertEqual(angle_arcs([True] * 4, 90), [[0, 360]])
        self.assertEqual(max_span([False] * 4, 90), 0)

    def test_geometry_rejects_bad_offsets_and_boundary_violations(self):
        public, family = sample_family(9, SceneConfig(angle_step_deg=30))
        public["entities"][1]["geometry"] = expand_geometry(public["entities"][0]["geometry"], 2000)
        checked = check_family(public, family)
        codes = {i["code"] for i in checked["issues"]}
        self.assertIn("layer_not_contour_buffer", codes)
        self.assertIn("protection_outside_world", codes)
        self.assertFalse(checked["accepted"])

    def test_every_entry_facility_pair_and_approach_is_recorded(self):
        public, family = sample_family(42, SceneConfig(angle_step_deg=30))
        checked = check_family(public, family)
        count = sum(e["type"] == "facility" for e in public["entities"])
        self.assertEqual(len(checked["routes"]), len(public["entry_zones"]) * count)
        self.assertEqual(len(checked["approaches"]), count)
        for approach in checked["approaches"]:
            self.assertEqual(len(approach["samples"]), 12)
            self.assertEqual(approach["available_span_deg"], sum(approach["feasible_mask"]) * 30)
            self.assertEqual(len(approach["by_entry"]), len(public["entry_zones"]))
        self.assertEqual(canonical_json(checked), canonical_json(check_family(public, family)))

    def test_oblique_candidate_routes_have_full_thirty_meter_clearance(self):
        public, family = sample_family(4443110635622324325, SceneConfig(angle_step_deg=30))
        checks = check_family(public, family)
        self.assertTrue(checks["accepted"])
        for route in checks["routes"]:
            line = LineString(route["points_m"])
            for entity in public["entities"]:
                if entity["type"] == "hard_constraint_obstacle":
                    geometry = entity["geometry"]
                    if geometry["type"] == "Circle":
                        clearance = line.distance(Point(geometry["center_m"])) - geometry["radius_m"]
                    else:
                        clearance = line.distance(to_shape(geometry))
                    self.assertGreaterEqual(clearance, 30 - 1e-7)

    def test_small_angular_coverage_does_not_create_rejection_reason(self):
        public, family = sample_family(42, SceneConfig(angle_step_deg=30, approach_standoff_m=10000))
        checked = check_family(public, family)
        self.assertTrue(all(a["available_span_deg"] == 0 for a in checked["approaches"]))
        ordinary, same_family = sample_family(42, SceneConfig(angle_step_deg=30))
        standard = check_family(ordinary, same_family)
        self.assertEqual(checked["accepted"], standard["accepted"])
        self.assertEqual(checked["issues"], standard["issues"])


if __name__ == "__main__":
    unittest.main()
