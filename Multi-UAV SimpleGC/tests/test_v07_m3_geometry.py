"""M3a G1-G6/G8/G10: geometry is a prefilter, not a replacement for M1."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import numpy as np

from v07_m3_fixtures import request
from task_v07.expansion.contracts import P0ContractError
from task_v07.unified.spec import build_spec, validate_spec, proposal_seed
from task_v07.unified.free_space import free_space, work_region, offset_curve, chord_intervals, quantile_interval
from task_v07.geometry import geometry_facts


class SpecTests(unittest.TestCase):
    def test_G1_spec_without_geometry_or_execution(self):
        scene, descriptor, group = request()
        with patch("task_v07.geometry.geometry_facts", side_effect=AssertionError("geometry called")), \
             patch("task_v07.execution.execute", side_effect=AssertionError("execution called")):
            spec = build_spec(descriptor, group)
            self.assertEqual(spec, build_spec(descriptor, group))
            self.assertEqual(validate_spec(spec, descriptor, group), spec)
        self.assertNotIn("initial_states", spec)
        self.assertNotIn("references", spec)
        for field, value in (("target_id", "changed"), ("members", ["other"]), ("geometry_seed", 0)):
            changed = deepcopy(spec); changed[field] = value
            with self.assertRaises(P0ContractError):
                validate_spec(changed, descriptor, group)
        self.assertNotEqual(proposal_seed(spec, 0), proposal_seed(spec, 1))

    def test_G1_registered_group_not_reassigned(self):
        _, descriptor, group = request()
        other = {**group, "target_id": "another"}
        with self.assertRaises(P0ContractError):
            build_spec(descriptor, other)

    def test_G2_column_permutation_does_not_change_spec(self):
        _, descriptor, group = request(multi=True)
        changed = deepcopy(descriptor)
        changed["agent_ids"] = list(reversed(changed["agent_ids"]))
        changed["column_seed"] += 1
        self.assertEqual(build_spec(descriptor, group), build_spec(changed, changed["task_groups"][0]))


class FreeSpaceTests(unittest.TestCase):
    def test_G3_exact_circle_and_polygon_offsets(self):
        primitives = [{"type": "Circle", "center_m": [3., -7.], "radius_m": 40.},
                      {"type": "Polygon", "vertices_m": [[-80., -60.], [100., -50.], [60., 90.], [-70., 80.]]}]
        for primitive in primitives:
            with self.subTest(primitive=primitive["type"]):
                points = np.asarray(offset_curve(primitive, 73.))
                np.testing.assert_allclose(geometry_facts(primitive, points)["signed_distance_m"], 73., atol=1e-8)
                mid = (points[:-1]+points[1:])/2
                self.assertGreaterEqual(float(geometry_facts(primitive, mid)["signed_distance_m"].min()), 72.-1e-8)

    def test_G3_feasible_chord_intervals(self):
        scene, d, g = request()
        free = free_space(scene, build_spec(d, g))
        ranges = chord_intervals(free, np.array([1., 0.]), 30.)
        self.assertTrue(ranges)
        for q in (0., .2, .8, 1.):
            value = quantile_interval(ranges, q)
            self.assertTrue(any(a <= value <= b for a, b in ranges))
        self.assertFalse(work_region(scene, build_spec(d, g), free).is_empty)

    def test_G4_full_segment_detects_inner_zone(self):
        scene, d, g = request()
        free = free_space(scene, build_spec(d, g))
        self.assertTrue(free.point_valid([-600., 0.]))
        self.assertTrue(free.point_valid([600., 0.]))
        self.assertTrue(any(i["kind"] == "forbidden_layer" for i in free.segment_issues([-600., 0.], [600., 0.])))

    def test_G5_obstacle_and_world_segment_checks(self):
        scene, d, g = request(); original = deepcopy(scene)
        free = free_space(scene, build_spec(d, g))
        self.assertTrue(free.segment_issues([-1600., -1200.], [-800., -1200.]))
        self.assertTrue(free.segment_issues([2900., 2500.], [3050., 2500.]))
        planner = free.planner()
        self.assertFalse(planner.free([2990., 2500.]))
        self.assertEqual(scene, original)

    def test_G6_empty_domain_and_arcs_are_finite(self):
        scene, d, g = request()
        scene["entities"].append({"id": "blocked", "type": "hard_constraint_obstacle",
                                  "geometry": {"type": "Circle", "center_m": [0., 0.], "radius_m": 5000.}})
        free = free_space(scene, build_spec(d, g))
        self.assertTrue(free.candidate.is_empty)
        self.assertEqual(free.feasible_arcs(500.), [])
        self.assertIsNone(free.planner().path([-2000., 1000.], [2000., 1000.]))


if __name__ == "__main__":
    unittest.main()
