"""Versioned route metadata, independent pattern draws, and strict feasibility."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from swarm_sim.generation_v2 import (apply_flight_pattern, flight_pattern_choice,
    generate_v2, normalize_profile)
from swarm_sim.mission_v3 import normalize_v3
from swarm_sim.registry import FLIGHT_PATTERNS, SEMANTIC_ROLES, component_versions, get_intent, get_planner
from swarm_sim.route_planning import time_aware_phase_clearance
from swarm_sim.tasks import compile_task

ROOT = Path(__file__).parents[1]


def template(name):
    return json.loads((ROOT / "missions/v3" / name).read_text(encoding="utf-8-sig"))


class V06PlanningTests(unittest.TestCase):
    def test_direct_v06_templates_have_metadata_without_changing_generated_task(self):
        from swarm_sim.protocol import task_metadata
        from swarm_sim.generation_v2 import semantic_template_id
        for filename in ("recon_route_v06.json", "patrol_route_v06.json", "rapid_passage_route_v06.json"):
            source = template(filename)
            intent = source["mission"]["intent"]
            self.assertEqual(source["flight_pattern"], FLIGHT_PATTERNS[intent][0])
            self.assertEqual(task_metadata(normalize_v3(source)), dict(protocol_version="v0.6",
                flight_pattern=source["flight_pattern"], component_versions=component_versions(intent, source["flight_pattern"])))
            previous = copy.deepcopy(source)
            previous.pop("flight_pattern")
            previous.pop("component_versions")
            self.assertEqual(semantic_template_id(source), semantic_template_id(previous))
            for pattern in FLIGHT_PATTERNS[intent]:
                self.assertEqual(apply_flight_pattern(source, pattern), apply_flight_pattern(previous, pattern))

    def test_all_six_patterns_register_versions_and_roles(self):
        files = dict(reconnaissance="recon_route_v06.json", patrol="patrol_route_v06.json",
                     rapid_passage="rapid_passage_route_v06.json")
        for intent, patterns in FLIGHT_PATTERNS.items():
            self.assertTrue(set(get_intent(intent).semantic_phases) <= SEMANTIC_ROLES)
            for pattern in patterns:
                spec = normalize_v3(apply_flight_pattern(template(files[intent]), pattern))
                self.assertEqual(spec["component_versions"], component_versions(intent, pattern))
                self.assertEqual(spec["planner"]["name"], pattern+"_v1")
                self.assertIn(spec["planner"]["name"], get_intent(intent).allowed_planners)

    def test_v05_omits_new_fields_and_still_compiles(self):
        source = template("recon_route_v05.json")
        spec = normalize_v3(source)
        self.assertNotIn("flight_pattern", spec)
        self.assertNotIn("component_versions", spec)
        self.assertNotIn("final_hold_s", spec["execution"])
        self.assertNotIn("start_delays_s", compile_task(spec)["phases"][0])

    def test_component_versions_cannot_lie(self):
        spec = apply_flight_pattern(template("recon_route_v06.json"), "equal_strip_lawnmower")
        spec["component_versions"]["planner"] = "column_v1"
        with self.assertRaisesRegex(ValueError, "component_versions"):
            normalize_v3(spec)

    def test_pattern_random_substream_is_balanced_and_stable(self):
        for intent, patterns in FLIGHT_PATTERNS.items():
            draws = [flight_pattern_choice(2026100812, i, intent, 0) for i in range(1000)]
            self.assertEqual(set(draws), set(patterns))
            self.assertTrue(400 < draws.count(patterns[0]) < 600)
            self.assertEqual(draws, [flight_pattern_choice(2026100812, i, intent, 0) for i in range(1000)])
            self.assertEqual(flight_pattern_choice(2026100812, 1, intent, 0, "first"), patterns[0])

    def test_fixed_vs_random_keeps_family_shared_seed_and_split_identity(self):
        from swarm_sim.dataset import family_split
        profile = normalize_profile(ROOT / "generation_profiles/tri_intent_v06_pilot.json")
        profile["base_scene_count"] = 2
        with tempfile.TemporaryDirectory() as tmp:
            listings = []
            for mode in ("first", "random"):
                current = copy.deepcopy(profile)
                current["flight_pattern_mode"] = mode
                result = generate_v2(current, Path(tmp)/mode)
                listing = json.loads(Path(result["mission_list"]).read_text(encoding="utf-8"))["missions"]
                listings.append([{key: entry[key] for key in ("mission_id", "family_id", "base_index",
                    "candidate_id", "scene_seed", "task_seed", "shared_mission_params", "sampled_parameters")}
                    for entry in listing])
            self.assertEqual(listings[0], listings[1])
            self.assertEqual(len(listings[0]), 6)
            # The dataset split function receives this unchanged family ID.
            self.assertEqual([family_split(row["family_id"]) for row in listings[0]],
                             [family_split(row["family_id"]) for row in listings[1]])

    def test_interleaved_allocation_i_plus_n_and_no_fallback(self):
        spec = normalize_v3(apply_flight_pattern(template("recon_route_v06.json"), "interleaved_lanes"))
        plan = get_planner(spec["planner"]["name"]).plan_routes(spec)
        n = len(spec["scenario"]["vehicles"])
        for assignment in plan.assignments.values():
            indices = list(map(int, assignment.removeprefix("interleaved_").split("_")))
            self.assertGreaterEqual(len(indices), 2)
            self.assertTrue(all(b-a == n for a, b in zip(indices, indices[1:])))
        with self.assertRaisesRegex(ValueError, "too close"):
            compile_task(spec)

    def test_column_delays_and_endpoints_are_explicit(self):
        spec = normalize_v3(apply_flight_pattern(template("rapid_passage_route_v06.json"), "column"))
        plan = get_planner("column_v1").plan_routes(spec)
        delays = plan.diagnostics["phase_start_delays_s"]["transit"]
        self.assertEqual(sorted(delays.values()), [0., 1., 2.])
        endpoints = [route["transit"][-1] for route in plan.routes.values()]
        self.assertEqual(len({p["east_m"] for p in endpoints}), 1)
        self.assertEqual(len({p["north_m"] for p in endpoints}), 3)

    def test_start_delays_account_for_waiting_occupancy(self):
        starts = {"a": dict(east_m=0., north_m=0., up_m=8.), "b": dict(east_m=20., north_m=0., up_m=8.)}
        routes = {"a": [dict(east_m=30., north_m=0., up_m=8.)], "b": [dict(east_m=50., north_m=0., up_m=8.)]}
        timing = dict(min_s=0., fraction_of_phase=0.)
        with self.assertRaisesRegex(ValueError, "too close"):
            time_aware_phase_clearance(starts, routes, 2., 5., timing, start_delays_s={"a": 0., "b": 20.})

    def test_existing_validators_ignore_pattern_and_missing_pattern(self):
        from swarm_sim.route_planning import sample_route
        for intent, filename, semantic in (("reconnaissance", "recon_route_v06.json", "observe"),
                                           ("patrol", "patrol_route_v06.json", "patrol")):
            source = template(filename)
            source["mission"]["return_required"] = False
            source = apply_flight_pattern(source, FLIGHT_PATTERNS[intent][0])
            scene = compile_task(source)
            phase = next(p for p in scene["phases"] if p["semantic_phase"] == semantic)
            traces, windows = {}, []
            for agent, route in phase["routes"].items():
                start = scene["semantic_plan"]["execution_phases"][phase["name"]]["agents"][agent]["start_point"]
                traces[agent], _, _ = sample_route(start, route, phase["speed_m_s"], .25)
                windows.append(dict(agent_id=agent, phase=phase["name"], role=semantic, semantic_phase=semantic,
                    service_enabled=True, start_s=0., end_s=traces[agent][-1][0], complete_execution_window=True))
            evaluator = get_intent(intent).evaluate_channel
            if intent == "patrol":
                from functools import partial
                evaluator = partial(evaluator, validator_version="perimeter_revisit_v2",
                                    progress_mapping_version="ordered_route_progress_v2")
            baseline = evaluator(scene, traces, windows, {})
            if intent == "patrol":
                self.assertEqual(baseline["metrics"]["perimeter_revisit"]["version"], "perimeter_revisit_v2")
            for pattern in (*FLIGHT_PATTERNS[intent], None):
                changed = copy.deepcopy(scene)
                if pattern is None:
                    changed["task_spec"].pop("flight_pattern", None)
                else:
                    changed["task_spec"]["flight_pattern"] = pattern
                self.assertEqual(evaluator(changed, traces, windows, {}), baseline)
            truncated = {a: rows[:max(2, len(rows)//6)] for a, rows in traces.items()}
            interrupted_windows = copy.deepcopy(windows)
            for window in interrupted_windows:
                window["end_s"] = truncated[window["agent_id"]][-1][0]
                window["complete_execution_window"] = False
            interrupted = evaluator(scene, truncated, interrupted_windows, {})
            self.assertFalse(all(value is True for value in interrupted["conditions"].values()))


if __name__ == "__main__":
    unittest.main()
