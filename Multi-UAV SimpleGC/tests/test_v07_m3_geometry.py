"""M3a G1-G6/G8/G10: geometry is a prefilter, not a replacement for M1."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import numpy as np
import random

from v07_m3_fixtures import request
from task_v07.expansion.contracts import P0ContractError
from task_v07.unified.spec import build_spec, validate_spec, proposal_seed
from task_v07.unified.free_space import free_space, work_region, offset_curve, chord_intervals, quantile_interval
from task_v07.geometry import geometry_facts
from task_v07.unified.assign import assign
from task_v07.unified.route import clean_joints, offset_lane, route_group, line_interval, GeometryRejected
from task_v07.geometry import offset_geometry
from task_v07.expansion.contracts import validate_route_bundle
from task_v07.expansion.contracts import RouteBundle
from task_v07.unified.checks import plan_checks, warning_visits


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


class AssignmentTests(unittest.TestCase):
    def test_G2_physical_slots_survive_column_and_slot_permutation(self):
        _, d, g = request(multi=True)
        spec = build_spec(d, g)
        starts = {s["agent_id"]: s["position_enu_m"] for s in d["family_conditions"]["initial_states"]}
        slots = [{"slot_id": f"{i}:{j}", "split_index": i, "direction": [1., 0.], "entry": [0., 20.*j]}
                 for i, stock in enumerate(spec["public_split"]["members"]) for j in range(len(stock))]
        mapping = assign(g["members"], starts, slots, spec["public_split"])
        self.assertEqual(mapping, assign(list(reversed(g["members"])), starts, list(reversed(slots)), spec["public_split"]))
        for i, stock in enumerate(spec["public_split"]["members"]):
            self.assertEqual(set(stock), {a for a, s in mapping.items() if s["split_index"] == i})
        with self.assertRaises(P0ContractError):
            assign(g["members"], starts, slots[:-1], spec["public_split"])


class ConnectionTests(unittest.TestCase):
    def test_G10_clean_forward_joins_preserves_bends_and_endpoint(self):
        points = clean_joints([[0., 0.], [0., 0.], [.5, 0.], [5., 0.], [5., 5.]])
        np.testing.assert_allclose(points, [[0., 0.], [5., 0.], [5., 5.]])
        with self.assertRaises(GeometryRejected):
            clean_joints([[0., 0.], [.5, .2], [5., 5.]])
        lane = offset_lane([[0., 0.], [100., 0.], [100., 100.]], -20.)
        np.testing.assert_allclose(lane[-1], [120., 100.])
        self.assertTrue(all(np.linalg.norm(b-a) >= 1. for a, b in zip(lane, lane[1:])))

    def test_G7_shared_connection_has_truthful_metadata(self):
        scene, d, g = request(); spec = build_spec(d, g); free = free_space(scene, spec)
        warning = offset_geometry(free.target["geometry"], free.offsets["warning"])
        slots = []
        for i in range(len(g["members"])):
            origin = np.array([0., 600.+20*i]); direction = np.array([1., 0.])
            lo, hi = line_interval(warning, origin, direction)
            entry, end = origin+lo*direction, origin+hi*direction
            slots.append({"split_index": 0, "slot_id": str(i), "direction": direction.tolist(),
                          "entry": entry.tolist(), "work": [entry.tolist(), end.tolist()], "exit_direction": direction.tolist()})
        bundle, template = route_group(scene, spec, {"slots": slots, "draw": {"test": "straight"}}, free,
                                       d["family_conditions"]["initial_states"], random.Random(73))
        validate_route_bundle(bundle, g["members"])
        self.assertEqual(template["retreat_warning_minimum_m"], 50.)
        for agent, points in bundle.waypoints_by_agent.items():
            self.assertEqual(points[-1], template["references"][agent]["endpoint_enu_m"])
            self.assertEqual(points[0], next(s["position_enu_m"] for s in d["family_conditions"]["initial_states"] if s["agent_id"] == agent))
        self.assertGreater(template["approach_length_m"], 0)
        checks = plan_checks(scene, spec, bundle, template, free, d["family_conditions"]["initial_states"])
        self.assertEqual(checks["status"], "PASS", checks["issues"])

    def test_G4_G5_full_route_witnesses(self):
        scene, d, g = request(count=2); spec = build_spec(d, g)
        for route, entity in (([[-600., 0., 120.], [600., 0., 120.]], "F1_alert"),
                              ([[-1600., -1200., 120.], [-800., -1200., 120.]], "R1"),
                              ([[2900., 2500., 120.], [3050., 2500., 120.]], "world")):
            bundle = RouteBundle({a: route for a in g["members"]}, {a: 0. for a in g["members"]})
            template = {"references": {a: {"endpoint_enu_m": route[-1], "split_index": 0} for a in g["members"]}}
            result = plan_checks(scene, spec, bundle, template)
            self.assertEqual(result["status"], "REJECT")
            self.assertTrue(any(i.get("entity_id") == entity and i["segment"] == 0 for i in result["issues"]))

    def test_G6_multiple_visits_and_same_boundary_join(self):
        warning = {"type": "Circle", "center_m": [0., 0.], "radius_m": 10.}
        visits, _ = warning_visits(np.array([[-20., 0.], [0., 0.], [20., 0.]]), warning)
        self.assertEqual(len(visits), 1)
        visits, _ = warning_visits(np.array([[-20., 0.], [20., 0.], [-20., 0.]]), warning)
        self.assertEqual(len(visits), 2)


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
