"""Independent C/P expectations for the shared mission schema and reference plan."""

import copy
import json
import unittest
from pathlib import Path

from swarm_sim.capability import nominal_capability
from swarm_sim.mission_planning import compile_execution_phases, compile_shared_mission_v2, partition_region
from swarm_sim.mission_schema import normalize_mission


def demo():
    return json.loads((Path(__file__).parents[1] / "missions" / "recon_shared_3uav.json").read_text(encoding="utf-8"))


def layout(count, axis="east"):
    spec = demo()
    spec["planner"]["partition_axis"] = axis
    region = spec["scenario"]["regions"][0]
    region["width_m"], region["height_m"] = ((12.0 * count, 18.0) if axis == "east" else (18.0, 12.0 * count))
    spec["scenario"]["vehicles"] = [
        {"id": f"uav_{i + 1:02d}", "sysid": i + 1,
         "east_m": 6.0 + 12.0 * i if axis == "east" else -12.0,
         "north_m": -12.0 if axis == "east" else 6.0 + 12.0 * i, "heading_deg": 0.0}
        for i in range(count)]
    return spec


class MissionSchemaTests(unittest.TestCase):
    def test_c03_c07_canonical_compile_and_input_unchanged(self):
        source = demo()
        original = copy.deepcopy(source)
        normalized = normalize_mission(source)
        self.assertEqual(source, original)
        self.assertEqual(normalize_mission(normalized), normalized)
        self.assertEqual(compile_shared_mission_v2(source), compile_shared_mission_v2(source))
        reversed_keys = json.loads(json.dumps(source, sort_keys=True))
        reversed_keys["scenario"]["vehicles"].reverse()
        self.assertEqual(normalize_mission(reversed_keys), normalized)
        scene = compile_shared_mission_v2(source)
        self.assertEqual(compile_shared_mission_v2(reversed_keys), scene)
        self.assertEqual(scene["schema_version"], 1)
        self.assertEqual(scene["task_spec"]["schema_version"], 2)
        self.assertEqual(scene["family_id"], "recon_base_scene_demo_001")
        self.assertEqual(len(scene["phases"]), 12)
        self.assertEqual(scene["planning"]["nominal_global_coverage"]["covered_cells"], 1620)
        self.assertAlmostEqual(scene["planning"]["nominal_min_clearance_m"], 14.4)

    def test_c04_unknown_fields_at_every_object_layer(self):
        paths = [(), ("scenario",), ("scenario", "origin"), ("scenario", "world"),
                 ("scenario", "regions", 0), ("scenario", "vehicles", 0),
                 ("mission",), ("mission", "observation_model"), ("planner",), ("platform",), ("execution",)]
        for path in paths:
            with self.subTest(path=path):
                spec = demo()
                node = spec
                for key in path:
                    node = node[key]
                node["unsupported"] = 1
                with self.assertRaisesRegex(ValueError, "unsupported"):
                    normalize_mission(spec)

    def test_c04_every_numeric_leaf_rejects_bool_and_nonfinite(self):
        def numeric_paths(node, path=()):
            if isinstance(node, dict):
                for key, child in node.items():
                    yield from numeric_paths(child, path + (key,))
            elif isinstance(node, list):
                for index, child in enumerate(node):
                    yield from numeric_paths(child, path + (index,))
            elif type(node) in (int, float):
                yield path
        for path in numeric_paths(demo()):
            for invalid in (True, float("nan"), float("inf")):
                with self.subTest(path=path, invalid=invalid):
                    spec = demo()
                    node = spec
                    for key in path[:-1]:
                        node = node[key]
                    node[path[-1]] = invalid
                    with self.assertRaises(ValueError):
                        normalize_mission(spec)

    def test_c04_nonfinite_bool_enums_missing_and_wrong_shapes(self):
        for section, key in (("execution", "speed_m_s"), ("planner", "lane_spacing_m"),
                             ("platform", "max_horizontal_accel_m_s2"), ("mission", "coverage_required")):
            for value in (float("nan"), float("inf"), -float("inf"), True, "3"):
                with self.subTest(section=section, key=key, value=value):
                    spec = demo()
                    spec[section][key] = value
                    with self.assertRaises(ValueError):
                        normalize_mission(spec)
        for section, key, value in (("mission", "return_required", 1), ("mission", "intent", "attack"),
                                    ("mission", "objective", "tracking"), ("planner", "partition_axis", "diagonal"),
                                    ("execution", "backend", "GUIDED"),
                                    ("platform", "dynamics_validation", "strict_proof")):
            spec = demo()
            spec[section][key] = value
            with self.assertRaises(ValueError):
                normalize_mission(spec)
        for value in (True, 2.0, 1):
            spec = demo()
            spec["schema_version"] = value
            with self.assertRaises(ValueError):
                normalize_mission(spec)
        for section in ("scenario", "mission", "planner", "platform", "execution"):
            spec = demo()
            spec[section] = []
            with self.assertRaises(ValueError):
                normalize_mission(spec)
        spec = demo()
        del spec["mission"]["observation_model"]
        with self.assertRaisesRegex(ValueError, "missing"):
            normalize_mission(spec)

    def test_c05_unsupported_regions_identities_and_world_bounds(self):
        mutations = [
            lambda s: s["scenario"].update(restricted_regions=[{"id": "obstacle"}]),
            lambda s: s["mission"].update(target_region_id="unknown"),
            lambda s: s["scenario"]["vehicles"][1].update(id="uav_01"),
            lambda s: s["scenario"]["vehicles"][1].update(sysid=1),
            lambda s: s["scenario"]["vehicles"][1].update(sysid=True),
            lambda s: s["scenario"].update(vehicles=[]),
            lambda s: s["scenario"]["regions"][0].update(width_m=0),
            lambda s: s["scenario"]["regions"][0].update(min_east_m=90),
            lambda s: s["scenario"]["vehicles"][0].update(east_m=-101),
            lambda s: s["scenario"]["world"].update(east_bounds_m=[-2001, 100]),
            lambda s: s["execution"].update(takeoff_alt_m=45),
            lambda s: s["scenario"]["origin"].update(lat=float("nan")),
        ]
        for mutate in mutations:
            spec = demo()
            mutate(spec)
            with self.assertRaises(ValueError):
                normalize_mission(spec)
        # The 3 m minimum flight altitude does not exclude a ground spawn.
        self.assertEqual(normalize_mission(demo())["scenario"]["world"]["flight_up_bounds_m"], [3.0, 40.0])


class SharedPlanningTests(unittest.TestCase):
    def test_smoke_examples_keep_demo_thresholds_and_compile(self):
        original = demo()
        missions = Path(__file__).parents[1] / "missions"
        for filename, count, axis, cells in (("recon_smoke_3uav.json", 3, "east", 288),
                                             ("recon_smoke_2uav_north.json", 2, "north", 192),
                                             ("recon_smoke_6uav.json", 6, "east", 576)):
            with self.subTest(filename=filename):
                source = json.loads((missions / filename).read_text(encoding="utf-8"))
                scene = compile_shared_mission_v2(source)
                self.assertEqual(len(scene["vehicles"]), count)
                self.assertEqual(scene["planning"]["partition_axis"], axis)
                self.assertEqual(len(scene["phases"]), 8)
                self.assertEqual(scene["planning"]["nominal_global_coverage"]["covered_cells"], cells)
                self.assertGreaterEqual(scene["planning"]["nominal_min_clearance_m"], 7)
                for key in ("takeoff_alt_m", "speed_m_s", "arrival_tolerance_m", "confirmation_dwell_s", "min_separation_m"):
                    self.assertEqual(source["execution"][key], original["execution"][key])
                self.assertEqual(source["mission"], original["mission"])

    def test_p01_partition_union_positive_no_interior_overlap(self):
        for count in (1, 2, 3, 6):
            for axis in ("east", "north"):
                with self.subTest(count=count, axis=axis):
                    spec = layout(count, axis)
                    region = spec["scenario"]["regions"][0]
                    strips = partition_region(region, count, axis)
                    self.assertEqual(len(strips), count)
                    self.assertTrue(all(r["width_m"] > 0 and r["height_m"] > 0 for r in strips))
                    self.assertAlmostEqual(sum(r["width_m"] * r["height_m"] for r in strips), region["width_m"] * region["height_m"])
                    coordinate, size = (("min_east_m", "width_m") if axis == "east" else ("min_north_m", "height_m"))
                    for left, right in zip(strips, strips[1:]):
                        self.assertAlmostEqual(left[coordinate] + left[size], right[coordinate])
                    self.assertAlmostEqual(strips[0][coordinate], region[coordinate])
                    self.assertAlmostEqual(strips[-1][coordinate] + strips[-1][size], region[coordinate] + region[size])
                    scene = compile_shared_mission_v2(spec)
                    self.assertEqual(scene["planning"]["nominal_global_coverage"]["ratio"], 1.0)

    def test_p02_shared_region_translation_and_p03_spawn_independence(self):
        spec = demo()
        original = compile_shared_mission_v2(spec)
        shifted = copy.deepcopy(spec)
        shifted["scenario"]["regions"][0]["min_east_m"] += 7
        shifted["scenario"]["regions"][0]["min_north_m"] += 5
        changed = compile_shared_mission_v2(shifted)
        for agent, route in original["planning"]["per_agent_reference_routes"].items():
            for before, after in zip(route["observe"], changed["planning"]["per_agent_reference_routes"][agent]["observe"]):
                self.assertAlmostEqual(after["east_m"] - before["east_m"], 7)
                self.assertAlmostEqual(after["north_m"] - before["north_m"], 5)
        moved_spawn = copy.deepcopy(spec)
        moved_spawn["scenario"]["vehicles"][0]["north_m"] -= 5
        changed = compile_shared_mission_v2(moved_spawn)
        self.assertEqual(changed["planning"]["region_partitions"], original["planning"]["region_partitions"])
        for agent, route in original["planning"]["per_agent_reference_routes"].items():
            self.assertEqual(changed["planning"]["per_agent_reference_routes"][agent]["observe"], route["observe"])

    def test_p04_assignment_order_and_stable_id_tie_break(self):
        spec = demo()
        original = compile_shared_mission_v2(spec)
        spec["scenario"]["vehicles"] = list(reversed(spec["scenario"]["vehicles"]))
        self.assertEqual(compile_shared_mission_v2(spec), original)
        self.assertEqual(original["planning"]["agent_to_partition"],
                         {"uav_01": "R1_strip_01", "uav_02": "R1_strip_02", "uav_03": "R1_strip_03"})
        # ID changes follow the physical ordering, not lexicographic ordering.
        spec = demo()
        spec["scenario"]["vehicles"][0]["id"] = "zzz"
        self.assertEqual(compile_shared_mission_v2(spec)["planning"]["agent_to_partition"]["zzz"], "R1_strip_01")

    def test_p05_sweep_axis_and_optional_return(self):
        for axis in ("east", "north"):
            spec = layout(2, axis)
            scene = compile_shared_mission_v2(spec)
            route = scene["planning"]["per_agent_reference_routes"]["uav_01"]["observe"]
            constant = "east_m" if axis == "east" else "north_m"
            changing = "north_m" if axis == "east" else "east_m"
            self.assertEqual(route[0][constant], route[1][constant])
            self.assertGreater(route[1][changing], route[0][changing])
            self.assertEqual(scene["task_spec"]["mission"]["intent"], "reconnaissance")
            spec["mission"]["return_required"] = False
            no_return = compile_shared_mission_v2(spec)
            self.assertEqual(no_return["planning"]["semantic_to_execution_phase_map"]["return"], [])
            self.assertEqual(len(scene["phases"]) - len(no_return["phases"]), 1)

    def test_p06_padding_is_safe_stationary_and_not_service(self):
        spec = normalize_mission(layout(2))
        scene = compile_shared_mission_v2(spec)
        routes = copy.deepcopy(scene["planning"]["per_agent_reference_routes"])
        routes["uav_01"]["observe"] = routes["uav_01"]["observe"][:2]
        phases, semantic, _, idle = compile_execution_phases(spec, routes, scene["planning"]["agent_to_partition"])
        nominal_capability(spec, phases)
        self.assertEqual(idle["uav_01"], 4)
        self.assertEqual(idle["uav_02"], 0)
        padded = [phase for phase in phases if semantic["execution_phases"][phase["name"]]["agents"]["uav_01"]["role"] == "idle_padding"]
        for phase in padded:
            self.assertEqual(set(phase["targets"]), {"uav_01", "uav_02"})
            self.assertFalse(semantic["execution_phases"][phase["name"]]["agents"]["uav_01"]["service_enabled"])
            self.assertEqual(phase["targets"]["uav_01"]["east_m"], routes["uav_01"]["observe"][-1]["east_m"])
            self.assertEqual(phase["targets"]["uav_01"]["north_m"], routes["uav_01"]["observe"][-1]["north_m"])

    def test_p07_crossing_approach_return_and_active_vs_wait_rejected(self):
        spec = normalize_mission(layout(2))
        scene = compile_shared_mission_v2(spec)
        for phase_index in (0, -1):
            phases = copy.deepcopy(scene["phases"])
            targets = phases[phase_index]["targets"]
            targets["uav_01"], targets["uav_02"] = targets["uav_02"], targets["uav_01"]
            with self.assertRaisesRegex(ValueError, "paths too close"):
                nominal_capability(spec, phases)
        # A long active path passes a stationary peer, independent of stage timing.
        target = lambda e, n: {"east_m": e, "north_m": n, "up_m": 8.0}
        phases = [{"name": "unsafe_wait", "targets": {"uav_01": target(30, -12), "uav_02": target(18, -12)}}]
        with self.assertRaisesRegex(ValueError, "paths too close"):
            nominal_capability(spec, phases)
        close = layout(2)
        close["scenario"]["vehicles"][1]["east_m"] = 12
        with self.assertRaisesRegex(ValueError, "spawn clearance"):
            compile_shared_mission_v2(close)

    def test_p08_small_strips_and_phase_explosion_rejected(self):
        spec = layout(6)
        spec["scenario"]["regions"][0]["width_m"] = 12
        with self.assertRaisesRegex(ValueError, "strip too small"):
            compile_shared_mission_v2(spec)
        spec = demo()
        spec["planner"]["lane_spacing_m"] = 0.1
        with self.assertRaisesRegex(ValueError, "100 execution phases"):
            compile_shared_mission_v2(spec)

    def test_p09_speed_path_airborne_and_timeout_budgets(self):
        for section, key, value, message in (
                ("execution", "speed_m_s", 7, "max_speed"),
                ("execution", "speed_m_s", 16, "speed_m_s"),
                ("platform", "max_path_length_m", 100, "max_path_length"),
                ("platform", "max_airborne_time_s", 100, "max_airborne"),
                ("execution", "timeout_s", 100, "timeout_s")):
            spec = demo()
            spec[section][key] = value
            with self.assertRaisesRegex(ValueError, message):
                compile_shared_mission_v2(spec)
        scene = compile_shared_mission_v2(layout(2))
        report = scene["planning"]["feasibility_checks"]
        budget = report["nominal_budget"]
        self.assertAlmostEqual(budget["total_time_estimate_s"], budget["stage_time_estimate_s"] + 4 + 30 + 30 + 90)
        for agent, distance in budget["per_agent_path_length_m"].items():
            self.assertAlmostEqual(distance, budget["per_agent_horizontal_path_length_m"][agent] + 16)
        # Each phase counts both backend hold and extra confirmation dwell.
        for phase in budget["stage_estimates"]:
            self.assertAlmostEqual(phase["estimated_s"], max(phase["per_agent_motion_m"].values()) / 3 + 0.5 + 0.5)

    def test_p10_capability_does_not_claim_dynamics_proof(self):
        report = compile_shared_mission_v2(demo())["planning"]["feasibility_checks"]
        self.assertTrue(report["command_limits"]["pass"])
        self.assertEqual(report["executed_limits"]["status"], "not_verified")
        self.assertEqual(report["proxy_dynamics"]["status"], "not_verified")
        self.assertFalse(report["proxy_dynamics"]["hard_gate"])
        self.assertTrue(any("acceleration" in text for text in report["unverified_constraints"]))
        self.assertNotIn("fully_feasible", report)


if __name__ == "__main__":
    unittest.main()
