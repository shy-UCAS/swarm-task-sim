"""E01/E02/E03/E04/E09: independently expected continuous execution contracts."""

import copy
import json
import math
import unittest
from pathlib import Path

from swarm_sim.mission_v3 import from_v2, normalize_v3
from swarm_sim.registry import PlanResult, get_intent
from swarm_sim.route_planning import (clean_route, compile_route_phases, sample_route,
                                     time_aware_phase_clearance)
from swarm_sim.scenario import enu_to_geo, mission_for, route_mission_for, validate
from swarm_sim.tasks import compile_task, validate_task_binding


ROOT = Path(__file__).resolve().parents[1]


def demo():
    return json.loads((ROOT / "missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8"))


def point(e, n=0):
    return dict(east_m=float(e), north_m=float(n), up_m=8.0)


class RoutePlanningTests(unittest.TestCase):
    def test_E01_three_semantic_phases_zero_segments_removed_and_original_indices(self):
        scene = compile_task(demo())
        self.assertEqual(len(scene["phases"]), 3)
        self.assertEqual(scene["schema_version"], 2)
        self.assertEqual([len(p["routes"]["uav_01"]) for p in scene["phases"]], [1, 9, 1])
        for vehicle in scene["vehicles"]:
            agent = vehicle["id"]
            previous = point(vehicle["east_m"], vehicle["north_m"])
            for phase in scene["phases"]:
                role = scene["semantic_plan"]["execution_phases"][phase["name"]]["agents"][agent]
                self.assertEqual(role["start_point"], previous)
                for target in phase["routes"][agent]:
                    self.assertGreaterEqual(math.dist(tuple(previous.values()), tuple(target.values())), .05)
                    previous = target
                self.assertEqual(role["terminal_point"], previous)
            observe = scene["semantic_plan"]["execution_phases"]["p01_observe"]["agents"][agent]
            self.assertEqual(observe["waypoint_planner_indices"], list(range(1, 10)))
            self.assertTrue(observe["service_enabled"])
            self.assertEqual(scene["planning"]["removed_planner_waypoint_indices"]["p01_observe"][agent], [0])
        self.assertEqual(scene["planning"]["nominal_global_coverage"]["covered_cells"], 1620)

    def test_E01_epsilon_chain_keeps_first_and_filters_internal_duplicates(self):
        raw = [dict(east_m=e, north_m=0) for e in (0, .01, .06, .07, .2)]
        route, indices, removed = clean_route(point(0), raw, 8)
        self.assertEqual([p["east_m"] for p in route], [.06, .2])
        self.assertEqual(indices, [2, 4])
        self.assertEqual(removed, [0, 1, 3])
        self.assertEqual(clean_route(point(0), [dict(east_m=.05, north_m=0)], 8)[1], [0])

    def test_E01_empty_route_has_explicit_noop_terminal_and_service_false(self):
        spec = demo()
        routes = {v["id"]: {semantic: [dict(east_m=v["east_m"], north_m=v["north_m"])]
                            for semantic in ("approach", "observe", "return")} for v in spec["scenario"]["vehicles"]}
        plan = PlanResult(routes, {agent: None for agent in routes}, {})
        phases, semantic, _, noops, _ = compile_route_phases(spec, plan, get_intent("reconnaissance"))
        self.assertEqual(len(phases), 3)
        self.assertEqual(set(noops.values()), {3})
        for phase in phases:
            for agent, route in phase["routes"].items():
                self.assertEqual(route, [])
                role = semantic["execution_phases"][phase["name"]]["agents"][agent]
                self.assertEqual(role["role"], "hold_no_op")
                self.assertFalse(role["service_enabled"])
                self.assertEqual(role["terminal_point"], role["start_point"])

    def test_E01_return_false_omits_return_phase(self):
        spec = demo()
        spec["mission"]["return_required"] = False
        scene = compile_task(spec)
        self.assertEqual([p["semantic_phase"] for p in scene["phases"]], ["approach", "observe"])

    def test_E01_full_compile_and_validate_noop_approach(self):
        spec = demo()
        spec.pop("family_id")
        for index, vehicle in enumerate(spec["scenario"]["vehicles"]):
            vehicle.update(east_m=1.8 + 18 * index, north_m=0.0)
        scene = compile_task(spec)
        self.assertTrue(all(not route for route in scene["phases"][0]["routes"].values()))
        self.assertEqual(scene["planning"]["nominal_phase_timing"]["p00_approach"]["duration_s"], .5)
        self.assertEqual(validate(scene), scene)
        validate_task_binding(scene)

    def test_E02_mission_item_order_params_and_final_hold(self):
        scene = compile_task(demo())
        vehicle, origin = scene["vehicles"][0], scene["origin"]
        route = [point(10, 3), point(10, 5), point(12, 5)]
        actual = route_mission_for(vehicle, route, 2.5, .75, origin)
        self.assertEqual(len(actual), 5)
        self.assertEqual([m["command"] for m in actual], [16, 178, 16, 16, 16])
        self.assertEqual(actual[1]["params"], [1, 2.5, -1, 0])
        self.assertEqual([m["params"][0] for m in actual[2:]], [0, 0, .75])
        self.assertEqual([m["params"][1:3] for m in actual[2:]], [[1, 0]] * 3)
        self.assertTrue(all(math.isnan(m["params"][3]) for m in actual[2:]))
        self.assertEqual((actual[2]["lat"], actual[2]["lon"]), enu_to_geo(10, 3, origin))
        single = mission_for(vehicle, dict(route[0], speed_m_s=2.5, hold_s=.75), origin)
        self.assertEqual(actual[:2], single[:2])
        for malformed in ([], [point(0)] * 101):
            with self.assertRaises(ValueError):
                route_mission_for(vehicle, malformed, 2.5, .75, origin)

    def test_E03_same_time_crossing_rejected(self):
        starts = {"a": point(-10), "b": point(0, -10)}
        routes = {"a": [point(10)], "b": [point(0, 10)]}
        with self.assertRaisesRegex(ValueError, "time-aware nominal routes too close"):
            time_aware_phase_clearance(starts, routes, 1, 1, dict(min_s=3, fraction_of_phase=.2))

    def test_E03_same_place_outside_tau_accepted(self):
        starts = {"a": point(-10), "b": point(0, -30)}
        routes = {"a": [point(10)], "b": [point(0, 10)]}
        report = time_aware_phase_clearance(starts, routes, 1, 1, dict(min_s=3, fraction_of_phase=.2))
        self.assertEqual(report["duration_s"], 40)
        self.assertEqual(report["tau_s"], 8)
        self.assertEqual(report["per_agent_arrival_s"], {"a": 20, "b": 40})
        self.assertGreater(report["nominal_min_clearance_m"], 1)

    def test_E03_terminal_hold_and_noop_participate_after_nominal_arrival(self):
        for start, route in ((point(-10), [point(0)]), (point(0), [])):
            with self.subTest(no_op=not route):
                with self.assertRaisesRegex(ValueError, "terminal_or_no_op_interval"):
                    time_aware_phase_clearance({"a": start, "b": point(0, -30)},
                        {"a": route, "b": [point(0, 10)]}, 1, 1, dict(min_s=3, fraction_of_phase=.2))

    def test_E03_shared_demo_passes_original_clearance_and_tau(self):
        scene = compile_task(demo())
        self.assertAlmostEqual(scene["planning"]["nominal_min_clearance_m"], 14.4)
        report = scene["planning"]["nominal_phase_timing"]["p01_observe"]
        self.assertEqual(report["required_clearance_m"], 7)
        self.assertAlmostEqual(report["motion_duration_s"], 54.8)
        self.assertAlmostEqual(report["duration_s"], 55.8)
        self.assertAlmostEqual(report["tau_s"], 11.16)
        self.assertEqual(len(report["per_agent_waypoint_arrival_s"]["uav_01"]), 9)
        self.assertAlmostEqual(report["per_agent_waypoint_arrival_s"]["uav_01"][0], 10)

    def test_E03_arc_length_discretization_at_most_half_meter(self):
        samples, arrivals, length = sample_route(point(0), [point(1.2), point(1.2, .8)], 2)
        self.assertAlmostEqual(length, 2)
        self.assertEqual(arrivals, [.6, 1])
        self.assertTrue(all(math.dist(a[1], b[1]) <= .5 + 1e-12 for a, b in zip(samples, samples[1:])))
        self.assertEqual(samples[0], (0, (0, 0, 8)))

    def test_E04_exact_100_waypoints_allowed_101_rejected(self):
        route = [dict(east_m=(i + 1) / 10, north_m=0) for i in range(100)]
        self.assertEqual(len(clean_route(point(0), route, 8)[0]), 100)
        with self.assertRaisesRegex(ValueError, "100 waypoints"):
            clean_route(point(0), route + [dict(east_m=10.1, north_m=0)], 8)
        spec = demo()
        spec["planner"]["params"]["lane_spacing_m"] = .35
        with self.assertRaisesRegex(ValueError, "100 waypoints"):
            compile_task(spec)

    def test_E09_binding_rejects_route_metadata_and_timing_tampering(self):
        scene = compile_task(demo())
        validate_task_binding(scene)
        for mutation in (lambda s: s["phases"][1]["routes"]["uav_01"][0].update(north_m=29.9),
                         lambda s: s["semantic_plan"]["execution_phases"]["p01_observe"]["agents"]["uav_01"]["waypoint_planner_indices"].__setitem__(0, 99),
                         lambda s: s["planning"]["nominal_phase_timing"]["p01_observe"].update(tau_s=500)):
            altered = copy.deepcopy(scene)
            mutation(altered)
            with self.assertRaisesRegex(ValueError, "differs"):
                validate_task_binding(altered)

    def test_schema2_rejects_unknown_bool_nonfinite_and_route_shape(self):
        scene = compile_task(demo())
        mutations = [lambda s: s.update(extra=1), lambda s: s["phases"][0].update(extra=1),
                     lambda s: s["phases"][0]["routes"]["uav_01"][0].update(extra=1),
                     lambda s: s["vehicles"][0].update(sysid=True),
                     lambda s: s["phases"][0].update(speed_m_s=True),
                     lambda s: s["phases"][0]["routes"]["uav_01"][0].update(east_m=float("nan")),
                     lambda s: s["phases"][0]["routes"].pop("uav_01"),
                     lambda s: s["phases"][1]["routes"]["uav_01"].insert(0, copy.deepcopy(s["phases"][0]["routes"]["uav_01"][-1]))]
        for mutation in mutations:
            altered = copy.deepcopy(scene)
            mutation(altered)
            with self.assertRaises(ValueError):
                validate(altered)
        self.assertEqual(validate(scene), scene)

    def test_v3_controlled_failure_timeout_is_bound_and_strictly_positive(self):
        spec = demo()
        spec["execution"]["phase_timeout_override_s"] = .01
        scene = compile_task(spec)
        validate_task_binding(scene)
        self.assertEqual(scene["task_spec"]["execution"]["phase_timeout_override_s"], .01)
        for value in (True, 0, -1, float("nan"), float("inf")):
            spec["execution"]["phase_timeout_override_s"] = value
            with self.assertRaises(ValueError):
                normalize_v3(spec)


if __name__ == "__main__":
    unittest.main()
