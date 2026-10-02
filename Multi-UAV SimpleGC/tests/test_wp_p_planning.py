"""P01-P03: strict patrol contract and route feasibility selection."""

import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swarm_sim.generation_v2 import generate_v2, sample_patrol_laps
from swarm_sim.analysis import analyze_run
from swarm_sim.dataset import build_dataset
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.mission_v3 import compile_mission_v3, normalize_v3
from swarm_sim.patrol import _lap_route, _phase_check, _ring, plan_routes
from swarm_sim.recording import write_json
from swarm_sim.registry import get_intent, get_planner, registered_intents, registered_planners
from swarm_sim.route_planning import ZERO_LENGTH_EPSILON_M, clean_route


ROOT = Path(__file__).resolve().parents[1]


def patrol_task(count=2):
    spec = json.loads((ROOT / "missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8"))
    spec.pop("family_id", None)
    spec.pop("family_scheme", None)
    spec["scenario"]["regions"][0].update(min_east_m=-20., min_north_m=-15., width_m=40., height_m=30.)
    spec["scenario"]["vehicles"] = [
        dict(id="uav_01", sysid=1, east_m=-35., north_m=-15., heading_deg=0.),
        dict(id="uav_02", sysid=2, east_m=35., north_m=15., heading_deg=0.),
        dict(id="uav_03", sysid=3, east_m=0., north_m=-38., heading_deg=0.),
        dict(id="uav_04", sysid=4, east_m=0., north_m=38., heading_deg=0.),
    ][:count]
    spec["mission"].update(intent="patrol", intent_params=dict(objective="perimeter_patrol",
        laps=2, standoff_m=0., segment_length_m=5., visit_radius_m=3., max_revisit_gap_factor=2.))
    spec["planner"] = dict(name="staggered_same_loop_v1", params=dict(tracking_margin_m=1.))
    spec["execution"].update(speed_m_s=3., terminal_hold_s=0., hold_semantics="integer_seconds_v1",
                             async_timing_tolerance=dict(min_s=3., fraction_of_phase=.2, max_s=5.))
    return spec


class PatrolPlanningTests(unittest.TestCase):
    def test_P01_strict_params_and_planner(self):
        source = patrol_task()
        self.assertEqual(normalize_v3(source)["mission"]["intent_params"]["laps"], 2)
        self.assertEqual(get_intent("patrol").validator_version, "perimeter_revisit_v1")
        self.assertEqual(get_planner("staggered_same_loop_v1").version, "staggered_same_loop_v1")
        self.assertIn("patrol", registered_intents())
        self.assertIn("staggered_same_loop_v1", registered_planners())
        for path, value in (("unknown", 1), ("laps", 4), ("laps", True),
                            ("standoff_m", 1), ("segment_length_m", 6),
                            ("visit_radius_m", 4), ("max_revisit_gap_factor", 3)):
            spec = copy.deepcopy(source)
            spec["mission"]["intent_params"][path] = value
            with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                normalize_v3(spec)
        wrong = copy.deepcopy(source)
        wrong["planner"]["name"] = "equal_strip_lawnmower_v1"
        with self.assertRaisesRegex(ValueError, "intent and planner mismatch"):
            normalize_v3(wrong)
        wrong = copy.deepcopy(source)
        wrong["planner"]["params"]["unlisted"] = 1
        with self.assertRaisesRegex(ValueError, "unsupported patrol planner.params"):
            normalize_v3(wrong)

    def test_P01_seeded_lap_choice_records_180_second_downgrade(self):
        region = patrol_task()["scenario"]["regions"][0]
        seed = next(seed for seed in range(100) if sample_patrol_laps(seed, [2, 3], region, 3.)["sampled_laps"] == 3)
        slow = sample_patrol_laps(seed, [2, 3], region, 2.)
        fast = sample_patrol_laps(seed, [2, 3], region, 3.)
        self.assertEqual((slow["sampled_laps"], slow["selected_laps"]), (3, 2))
        self.assertEqual(slow["reason"], "three_laps_nominal_over_180s")
        self.assertEqual((fast["sampled_laps"], fast["selected_laps"]), (3, 3))
        self.assertEqual(fast["reason"], "seed_sample_retained")
        self.assertEqual(sample_patrol_laps(seed, [2, 3], region, 2.), slow)

    def test_P01_generation_binds_concrete_laps_and_sampling_provenance(self):
        profile = dict(schema_version=2, seed_scheme="task_semantics_only_v1", master_seed=17,
            base_scene_count=1, max_candidates_per_base=1,
            scene_sampler=dict(name="strip_aligned_v1", params=dict(vehicle_counts=[2],
                strip_width_m=[20., 20.], sweep_length_m=[30., 30.])),
            shared_mission_params=dict(speeds_m_s=[2.], return_required=[False]),
            missions=[dict(intent="patrol", template_spec=patrol_task(),
                           sample_laps=[2, 3], variant_speed_factors=[1.])],
            require_all_missions_feasible=True)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "one_candidate"
            report = generate_v2(profile, root)
            attempt = report["candidates"][0]["attempts"][0]
            task = json.loads((root / attempt["task"]).read_text(encoding="utf-8"))
            sample = attempt["lap_sampling"]
            self.assertEqual(task["mission"]["intent_params"]["laps"], sample["selected_laps"])
            self.assertIn(sample["sampled_laps"], (2, 3))
            self.assertEqual(sample["version"], "patrol_laps_sampling_v1")

    def test_P02_equal_arc_entries_full_check_and_clean_routes(self):
        scene = compile_mission_v3(patrol_task())
        planning = scene["planning"]
        self.assertEqual(scene["schema_version"], 2)
        self.assertEqual([phase["semantic_phase"] for phase in scene["phases"]],
                         ["approach", "patrol", "return"])
        self.assertEqual(planning["candidate_assignment_count"], 2)
        self.assertEqual(planning["feasible_assignment_count"], 2)
        self.assertTrue(planning["patrol_checker_cache"]["eligible"])
        self.assertEqual(planning["patrol_checker_cache"]["patrol_cache_reuses"], 1)
        self.assertEqual(planning["patrol_spacing_prefilter"]["passed"], True)
        self.assertEqual(planning["nominal_revisit_interval_s"], planning["perimeter_m"] / 2 / 3)
        arcs = planning["entry_arcs_m"]
        self.assertAlmostEqual((arcs[1] - arcs[0]) % planning["perimeter_m"], planning["perimeter_m"] / 2)
        vehicles = sorted(scene["vehicles"], key=lambda vehicle: vehicle["id"])
        distances = [sum(math.dist((vehicle["east_m"], vehicle["north_m"]),
                                   (planning["entry_points"][index]["east_m"],
                                    planning["entry_points"][index]["north_m"]))
                         for vehicle, index in zip(vehicles, assignment))
                     for assignment in ((0, 1), (1, 0))]
        self.assertEqual(tuple(planning["chosen_assignment_entry_indices"][vehicle["id"]]
                               for vehicle in vehicles),
                         min(((0, 1), (1, 0)), key=lambda assignment:
                             (distances[0 if assignment == (0, 1) else 1], assignment)))
        self.assertAlmostEqual(planning["chosen_approach_distance_m"], min(distances))
        self.assertEqual(set(planning["selected_assignment_phase_clearance"]),
                         {"approach", "patrol", "return"})
        for vehicle in scene["vehicles"]:
            agent = vehicle["id"]
            index = planning["chosen_assignment_entry_indices"][agent]
            entry = planning["entry_points"][index]
            route = planning["per_agent_reference_routes"][agent]
            self.assertEqual(route["approach"][-1], entry)
            self.assertEqual(route["patrol"][-1], entry)
            self.assertLessEqual(len(route["patrol"]), 100)
            previous = entry
            for point in route["patrol"]:
                self.assertGreaterEqual(math.dist(tuple(previous.values()), tuple(point.values())),
                                        ZERO_LENGTH_EPSILON_M)
                previous = point
            self.assertEqual(len(scene["phases"][1]["routes"][agent]), len(route["patrol"]))

    def test_P02_assignment_tie_break_and_patrol_cache_equivalence(self):
        spec = normalize_v3(patrol_task())
        planned = plan_routes(spec).diagnostics
        region = spec["scenario"]["regions"][0]
        corners, marks = _ring(region, planned["patrol_direction"])
        vehicles = sorted(spec["scenario"]["vehicles"], key=lambda vehicle: vehicle["id"])
        altitude = spec["execution"]["takeoff_alt_m"]
        reports = []
        for assignment in ((0, 1), (1, 0)):
            starts, routes = {}, {}
            for vehicle, index in zip(vehicles, assignment):
                entry = dict(planned["entry_points"][index], up_m=altitude)
                starts[vehicle["id"]] = entry
                routes[vehicle["id"]] = clean_route(entry,
                    _lap_route(corners, marks, planned["entry_arcs_m"][index], 2), altitude)[0]
            reports.append(_phase_check(starts, routes, spec["execution"],
                spec["execution"]["min_separation_m"] + 2 * spec["planner"]["params"]["tracking_margin_m"]))
        for key in ("nominal_min_clearance_m", "tau_s", "duration_s", "checked_point_pairs"):
            self.assertEqual(reports[0][key], reports[1][key])
        self.assertEqual(planned["selected_assignment_phase_clearance"]["patrol"]["closest_pair"],
                         reports[0 if tuple(planned["chosen_assignment_entry_indices"].values()) == (0, 1) else 1]["closest_pair"])

        tied = copy.deepcopy(spec)
        tied["scenario"]["vehicles"][1]["east_m"] = tied["scenario"]["vehicles"][0]["east_m"]
        tied["scenario"]["vehicles"][1]["north_m"] = tied["scenario"]["vehicles"][0]["north_m"]
        with patch("swarm_sim.patrol._phase_check", return_value={"tau_s": 5.}):
            tied_plan = plan_routes(tied)
        self.assertEqual(tuple(tied_plan.diagnostics["chosen_assignment_entry_indices"].values()), (0, 1))

        fallback = copy.deepcopy(spec)
        fallback["scenario"]["vehicles"][0]["east_m"] = planned["entry_points"][0]["east_m"] + .01
        fallback["scenario"]["vehicles"][0]["north_m"] = planned["entry_points"][0]["north_m"]
        with patch("swarm_sim.patrol._phase_check", return_value={"tau_s": 5.}):
            fallback_plan = plan_routes(fallback)
        self.assertFalse(fallback_plan.diagnostics["patrol_checker_cache"]["eligible"])
        self.assertEqual(fallback_plan.diagnostics["patrol_checker_cache"]["patrol_full_checks"], 2)
        self.assertEqual(fallback_plan.diagnostics["patrol_checker_cache"]["patrol_cache_reuses"], 0)

    def test_P03_distinct_prefilter_generic_and_all_assignment_reasons(self):
        spec = normalize_v3(patrol_task())
        prefiltered = copy.deepcopy(spec)
        prefiltered["execution"]["min_separation_m"] = 100.
        with self.assertRaisesRegex(ValueError, "^patrol_spacing_prefilter"):
            plan_routes(prefiltered)
        calls = []
        def first_generic_failure(starts, routes, execution, clearance):
            calls.append((starts, routes))
            if len(calls) == 1:
                raise ValueError("time-aware nominal routes too close: synthetic")
            return dict(tau_s=5., nominal_min_clearance_m=10.)
        with patch("swarm_sim.patrol._phase_check", side_effect=first_generic_failure):
            result = plan_routes(spec)
        self.assertEqual(result.diagnostics["candidate_assignment_count"], 2)
        self.assertEqual(result.diagnostics["feasible_assignment_count"], 1)
        self.assertIn("approach:time-aware nominal routes too close",
                      result.diagnostics["rejected_assignment_reasons"])
        self.assertEqual(set(result.diagnostics["selected_assignment_phase_clearance"]),
                         {"approach", "patrol", "return"})
        with patch("swarm_sim.patrol._phase_check",
                   side_effect=ValueError("time-aware nominal routes too close: synthetic")):
            with self.assertRaisesRegex(ValueError, "^patrol_assignment_infeasible:.*time-aware"):
                plan_routes(spec)

    def test_P08_dual_intent_export_and_audit_require_only_own_metrics(self):
        recon = json.loads((ROOT / "missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8"))
        recon["task_id"] = "v05_recon_audit_fixture"
        recon["execution"]["async_timing_tolerance"]["max_s"] = 5.
        patrol = patrol_task()
        patrol["task_id"] = "v05_patrol_audit_fixture"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = []
            for task in (recon, patrol):
                directory = root / task["task_id"]
                scene = compile_mission_v3(task)
                directory.mkdir()
                write_json(directory / "scenario.json", scene)
                write_json(directory / "metadata.json", dict(version="0.5.0-dev", run_id=task["task_id"],
                    scenario=scene, status="failed", run_epoch_monotonic_s=100., elapsed_s=.1))
                (directory / "events.jsonl").write_text("", encoding="utf-8")
                analyze_run(directory)
                runs.append(directory)
            dataset = root / "dataset"
            build_dataset(runs, dataset)
            audited = audit_dataset(dataset)
            by_intent = {item["intent"]: item for item in audited["groups"]}
            self.assertEqual(set(by_intent), {"patrol", "reconnaissance"})
            self.assertEqual(by_intent["patrol"]["required_audit_metrics"],
                ["min_segment_visits", "max_revisit_gap_s", "loop_segment_coverage"])
            self.assertEqual(by_intent["reconnaissance"]["required_audit_metrics"],
                ["global_coverage_ratio", "repeated_coverage_cell_ratio", "leave_one_out_coverage_drop"])
            self.assertNotIn("min_segment_visits", by_intent["reconnaissance"]["intent_metrics"])
            self.assertNotIn("global_coverage_ratio", by_intent["patrol"]["intent_metrics"])
            patrol_episode = next(item for item in audited["episodes"] if item["intent"] == "patrol")
            self.assertIsNotNone(patrol_episode["topology_signature"])


if __name__ == "__main__":
    unittest.main()
