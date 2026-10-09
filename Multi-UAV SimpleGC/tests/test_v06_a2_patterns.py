"""A2 strip-local scans and a deliberately scoped echelon candidate."""

import copy
import json
import math
import unittest
from pathlib import Path

from swarm_sim.generation_v2 import apply_flight_pattern
from swarm_sim.mission_v3 import normalize_v3
from swarm_sim.rapid_passage import ECHELON_OFFSET_M, echelon_candidate_registration
from swarm_sim.registry import FLIGHT_PATTERNS, get_intent, get_planner, registered_planners
from swarm_sim.tasks import compile_task


ROOT = Path(__file__).resolve().parents[1]


def template(name):
    return json.loads((ROOT / "missions/v3" / name).read_text(encoding="utf-8-sig"))


class V06A2PatternTests(unittest.TestCase):
    def test_retired_patterns_are_not_available(self):
        retired = {"interleaved_lanes", "bidirectional_lanes", "column"}
        self.assertFalse(retired & {p for values in FLIGHT_PATTERNS.values() for p in values})
        for pattern in retired:
            with self.assertRaisesRegex(ValueError, "unregistered planner"):
                get_planner(pattern+"_v1")
        self.assertEqual(FLIGHT_PATTERNS["patrol"], ("staggered_same_loop",))
        self.assertEqual(get_intent("patrol").allowed_planners, ("staggered_same_loop_v1",))

    def test_spiral_preserves_lawnmower_partition_assignment_and_validator(self):
        source = template("recon_route_v06.json")
        base = normalize_v3(source)
        spiral = normalize_v3(apply_flight_pattern(source, "equal_strip_rectangular_spiral"))
        old_plan = get_planner(base["planner"]["name"]).plan_routes(base)
        new_plan = get_planner(spiral["planner"]["name"]).plan_routes(spiral)
        self.assertEqual(new_plan.assignments, old_plan.assignments)
        self.assertEqual(new_plan.diagnostics["region_partitions"], old_plan.diagnostics["region_partitions"])
        self.assertEqual(new_plan.diagnostics["partition_axis"], old_plan.diagnostics["partition_axis"])
        self.assertEqual(spiral["component_versions"]["validator"], base["component_versions"]["validator"])
        self.assertNotEqual(new_plan.routes, old_plan.routes)
        for agent in old_plan.routes:
            self.assertEqual(new_plan.routes[agent]["return"], old_plan.routes[agent]["return"])

    def test_spiral_coverage_world_and_strip_clearance_on_fixed_geometry_grid(self):
        for count in (2, 3, 4):
            for width in (11., 16.):
                for axis in ("east", "north"):
                    with self.subTest(count=count, width=width, axis=axis):
                        source = template("recon_route_v06.json")
                        region = source["scenario"]["regions"][0]
                        region.update(width_m=count*width if axis == "east" else 30.,
                                      height_m=30. if axis == "east" else count*width)
                        source["scenario"]["vehicles"] = [dict(id=f"uav_{i+1:02d}", sysid=i+1,
                            east_m=(i+.5)*width if axis == "east" else -15.,
                            north_m=-15. if axis == "east" else (i+.5)*width, heading_deg=0.) for i in range(count)]
                        source["planner"]["params"]["partition_axis"] = axis
                        source.pop("family_id", None)
                        task = normalize_v3(apply_flight_pattern(source, "equal_strip_rectangular_spiral"))
                        plan = get_planner(task["planner"]["name"]).plan_routes(task)
                        self.assertGreaterEqual(plan.diagnostics["nominal_global_coverage"]["ratio"], .9)
                        strips = {p["id"]: p for p in plan.diagnostics["region_partitions"]}
                        for agent, route in plan.routes.items():
                            strip = strips[plan.assignments[agent]]
                            for point in route["observe"]:
                                self.assertLessEqual(strip["min_east_m"], point["east_m"])
                                self.assertLessEqual(point["east_m"], strip["min_east_m"]+strip["width_m"])
                                self.assertLessEqual(strip["min_north_m"], point["north_m"])
                                self.assertLessEqual(point["north_m"], strip["min_north_m"]+strip["height_m"])
                            self.assertTrue(all(a["east_m"] == b["east_m"] or a["north_m"] == b["north_m"]
                                                for a, b in zip(route["observe"], route["observe"][1:])))
                        scene = compile_task(task)
                        self.assertGreaterEqual(scene["planning"]["nominal_min_clearance_m"], 7.-1e-9)
                        self.assertTrue(scene["planning"]["feasibility_checks"]["command_limits"]["world_bounds_pass"])

    def test_actual_spiral_trajectory_main_and_return_truncation(self):
        from swarm_sim.mission_evaluation import execution_windows
        from swarm_sim.mission_evaluation_v3 import _channel
        from swarm_sim.route_planning import sample_route

        scene = compile_task(apply_flight_pattern(template("recon_route_v06.json"), "equal_strip_rectangular_spiral"))
        traces = {vehicle["id"]: [] for vehicle in scene["vehicles"]}
        events, bounds, phase_start = [], {}, 0.0
        for phase in scene["phases"]:
            local = {}
            for agent, route in phase["routes"].items():
                start = scene["semantic_plan"]["execution_phases"][phase["name"]]["agents"][agent]["start_point"]
                local[agent], _, _ = sample_route(start, route, phase["speed_m_s"], .25)
            # Ideal evidence includes a real one-second endpoint dwell, sampled
            # at 10 Hz. The .5-second return criterion itself is unchanged.
            motion_end = max(rows[-1][0] for rows in local.values())
            phase_end = phase_start + motion_end + 1.0
            bounds[phase["semantic_phase"]] = (phase_start, phase_start+motion_end, phase_end)
            for agent, rows in local.items():
                absolute = [(phase_start+stamp, xyz) for stamp, xyz in rows]
                arrival, endpoint = absolute[-1]
                count = math.ceil((phase_end-arrival)/.1)
                absolute.extend((arrival+(phase_end-arrival)*i/count, endpoint) for i in range(1, count+1))
                traces[agent].extend(absolute if not traces[agent] else absolute[1:])
                events.extend(dict(event=kind, agent_id=agent, phase=phase["name"], t=stamp)
                              for kind, stamp in (("phase_auto_confirmed", phase_start),
                                                  ("task_target_verified", phase_end), ("phase_finished", phase_end)))
            phase_start = phase_end
        metadata = dict(run_epoch_monotonic_s=0., elapsed_s=phase_start, status="completed")
        clocks = {agent: dict(available=True, knots=[(0., 0.), (phase_start+1., phase_start+1.)]) for agent in traces}

        def evaluate_at(end):
            measured = {agent: [(stamp, xyz) for stamp, xyz in rows if stamp <= end] for agent, rows in traces.items()}
            evidence_events = [event for event in events if event["t"] <= end]
            meta = dict(metadata, elapsed_s=end, status="completed" if end == phase_start else "interrupted")
            windows = execution_windows(scene, evidence_events, meta, 0.)
            return _channel(scene, measured, windows, clocks, get_intent("reconnaissance"))

        complete, conditions = evaluate_at(phase_start)
        self.assertTrue(conditions["coverage"])
        self.assertTrue(conditions["return_to_launch"])
        self.assertTrue(complete["mission_success"])
        self.assertGreaterEqual(complete["coverage"]["global_coverage_ratio"], .9)

        observe_start, observe_arrival, _ = bounds["observe"]
        for fraction in (.15, .30):
            with self.subTest(main_fraction=fraction):
                interrupted, conditions = evaluate_at(observe_start+fraction*(observe_arrival-observe_start))
                self.assertLess(interrupted["coverage"]["global_coverage_ratio"], .9)
                self.assertIsNot(conditions["coverage"], True)
                self.assertIsNot(interrupted["mission_success"], True)

        return_start, return_arrival, _ = bounds["return"]
        interrupted, conditions = evaluate_at(return_start+.5*(return_arrival-return_start))
        self.assertTrue(conditions["coverage"])
        self.assertIsNot(conditions["return_to_launch"], True)
        self.assertIsNot(interrupted["mission_success"], True)
        for evidence in interrupted["return_to_launch"]["per_agent"].values():
            self.assertGreater(evidence["nearest_m"], scene["task_spec"]["execution"]["arrival_tolerance_m"])

    def test_echelon_candidate_preserves_lateral_lanes_and_original_return(self):
        source = template("rapid_passage_route_v06.json")
        before = tuple(registered_planners())
        self.assertNotIn("echelon", FLIGHT_PATTERNS["rapid_passage"])
        with echelon_candidate_registration():
            for side in ("south", "north", "west", "east"):
                source["planner"]["params"]["entry_side"] = side
                base = normalize_v3(source)
                candidate = normalize_v3(apply_flight_pattern(source, "echelon"))
                baseline = get_planner("line_abreast_v1").plan_routes(base)
                echelon = get_planner("echelon_v1").plan_routes(candidate)
                longitudinal, lateral = ("north_m", "east_m") if side in ("north", "south") else ("east_m", "north_m")
                sign = -1 if side in ("north", "east") else 1
                agents = sorted(echelon.routes, key=lambda a: echelon.routes[a]["approach"][0][lateral])
                lengths = []
                for agent in agents:
                    for phase in ("approach", "transit"):
                        self.assertEqual(echelon.routes[agent][phase][0][lateral], baseline.routes[agent][phase][0][lateral])
                    self.assertEqual(echelon.routes[agent]["return"], baseline.routes[agent]["return"])
                    start, end = echelon.routes[agent]["approach"][0], echelon.routes[agent]["transit"][0]
                    lengths.append(math.dist(tuple(start[k] for k in ("east_m", "north_m")), tuple(end[k] for k in ("east_m", "north_m"))))
                self.assertLess(max(lengths)-min(lengths), 1e-9)
                for left, right in zip(agents, agents[1:]):
                    for phase in ("approach", "transit"):
                        self.assertAlmostEqual(sign*(echelon.routes[right][phase][0][longitudinal]-echelon.routes[left][phase][0][longitudinal]), ECHELON_OFFSET_M)
                self.assertNotIn("phase_start_delays_s", echelon.diagnostics)
        self.assertEqual(tuple(registered_planners()), before)
        self.assertNotIn("echelon", FLIGHT_PATTERNS["rapid_passage"])

    def test_echelon_candidate_compiles_only_inside_context_and_restores_on_error(self):
        source = template("rapid_passage_route_v06.json")
        with echelon_candidate_registration():
            candidate = apply_flight_pattern(source, "echelon")
            scene = compile_task(candidate)
            self.assertEqual(scene["planning"]["planner_name"], "echelon_v1")
            self.assertGreaterEqual(scene["planning"]["nominal_min_clearance_m"], 7.)
        with self.assertRaisesRegex(ValueError, "unregistered planner"):
            compile_task(candidate)
        with self.assertRaisesRegex(RuntimeError, "diagnostic stopped"):
            with echelon_candidate_registration():
                raise RuntimeError("diagnostic stopped")
        self.assertNotIn("echelon", FLIGHT_PATTERNS["rapid_passage"])


if __name__ == "__main__":
    unittest.main()
