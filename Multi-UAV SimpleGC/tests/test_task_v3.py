"""G04-G07: strict new schema, frozen legacy mechanics and isolated dispatch."""

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import test_mission_evaluation as legacy_evidence
from swarm_sim.families import scene_family_id
from swarm_sim.mission_evaluation import evaluate_mission
from swarm_sim.mission_v3 import from_v2, normalize_v3
from swarm_sim.registry import (IntentSpec, PlannerSpec, PlanResult, get_intent, get_planner,
                                registered_intents, registered_planners, temporary_registration)
from swarm_sim.tasks import compile_task, validate_task_binding


ROOT = Path(__file__).parents[1]


def demo():
    return json.loads((ROOT / "missions/recon_shared_3uav.json").read_text(encoding="utf-8"))


def fixture_intent(evaluator=None):
    def normalize(params):
        if params != {"objective": "fixture_objective"}:
            raise ValueError("unsupported fixture intent_params")
        return dict(params)

    def labels(scene, truth):
        return dict(planned_behaviors=["fixture_planned"], observed_behaviors=[dict(
            name="fixture_observed", status="verified", rule_version="fixture_rule_v1")])

    return IntentSpec("fixture_intent", ("fixture_objective",), ("fixture_service", "return"),
        frozenset({"fixture_service"}), normalize, ("fixture_planner",),
        evaluator or (lambda *args: {"conditions": {"fixture_condition": True}, "metrics": {"fixture_metric": 17}}),
        "fixture_rule_v1", labels, ("fixture_metric",))


def fixture_planner():
    def normalize(params, spec):
        if params:
            raise ValueError("unsupported fixture planner params")
        return {}

    def routes(spec):
        points = {v["id"]: {"fixture_service": [{"east_m": v["east_m"], "north_m": v["north_m"] + 2}],
                            "return": [{"east_m": v["east_m"], "north_m": v["north_m"]}]
                            if spec["mission"]["return_required"] else []} for v in spec["scenario"]["vehicles"]}
        return PlanResult(points, {v["id"]: None for v in spec["scenario"]["vehicles"]}, {"fixture": True})

    return PlannerSpec("fixture_planner", "fixture_plan_v1", normalize, routes)


class TaskV3Tests(unittest.TestCase):
    def test_G04_normalization_idempotent_deterministic_input_untouched(self):
        spec = from_v2(demo())
        original = copy.deepcopy(spec)
        self.assertEqual(normalize_v3(spec), spec)
        self.assertEqual(spec, original)
        self.assertEqual(spec["planner"]["params"]["lane_end_overshoot_m"], 0)
        self.assertEqual(spec["family_id"], scene_family_id(spec))
        spec["scenario"]["vehicles"].reverse()
        self.assertEqual(normalize_v3(spec), original)

    def test_G04_unknown_fields_rejected_at_every_layer(self):
        paths = [(), ("scenario",), ("scenario", "origin"), ("scenario", "world"),
                 ("scenario", "regions", 0), ("scenario", "vehicles", 0), ("scenario", "platform"),
                 ("mission",), ("mission", "intent_params"), ("mission", "intent_params", "observation_model"),
                 ("planner",), ("planner", "params"), ("execution",)]
        for path in paths:
            with self.subTest(path=path):
                spec = from_v2(demo())
                node = spec
                for key in path:
                    node = node[key]
                node["unsupported"] = 42
                with self.assertRaisesRegex(ValueError, "unsupported"):
                    normalize_v3(spec)

    def test_G04_all_numeric_leaves_reject_bool_and_nonfinite(self):
        def paths(node, path=()):
            if isinstance(node, dict):
                for key, child in node.items():
                    yield from paths(child, path + (key,))
            elif isinstance(node, list):
                for index, child in enumerate(node):
                    yield from paths(child, path + (index,))
            elif type(node) in (float, int):
                yield path
        for mode in ("waypoint_barrier_v1", "semantic_phase_route_v1"):
            base = from_v2(demo(), mode)
            for path in paths(base):
                for value in (True, float("nan"), float("inf"), -float("inf")):
                    with self.subTest(mode=mode, path=path, value=value):
                        spec = copy.deepcopy(base)
                        node = spec
                        for key in path[:-1]:
                            node = node[key]
                        node[path[-1]] = value
                        with self.assertRaises(ValueError):
                            normalize_v3(spec)

    def test_G04_unregistered_intent_and_planner(self):
        for section, key in (("mission", "intent"), ("planner", "name")):
            spec = from_v2(demo())
            spec[section][key] = "unregistered"
            with self.assertRaisesRegex(ValueError, "unregistered"):
                compile_task(spec)

    def test_G04_incompatible_planner(self):
        with temporary_registration(fixture_intent(), (fixture_planner(),)):
            spec = from_v2(demo())
            spec["planner"] = dict(name="fixture_planner", params={})
            with self.assertRaisesRegex(ValueError, "intent and planner mismatch"):
                normalize_v3(spec)

    def test_G04_mode_specific_fields_are_not_silently_ignored(self):
        cases = [("waypoint_barrier_v1", "terminal_hold_s", .5),
                 ("waypoint_barrier_v1", "async_timing_tolerance", {"min_s": 3, "fraction_of_phase": .2}),
                 ("semantic_phase_route_v1", "waypoint_hold_s", .5)]
        for mode, key, value in cases:
            with self.subTest(mode=mode, key=key):
                spec = from_v2(demo(), mode)
                spec["execution"][key] = value
                with self.assertRaisesRegex(ValueError, "unsupported execution"):
                    normalize_v3(spec)
        spec = from_v2(demo(), "semantic_phase_route_v1")
        spec["execution"]["async_timing_tolerance"]["extra"] = 1
        with self.assertRaisesRegex(ValueError, "unsupported"):
            normalize_v3(spec)

    def test_G04_family_mismatch_or_scheme_mismatch_rejected(self):
        for key, value in (("family_id", "scene_00000000000000000000"), ("family_scheme", "legacy")):
            spec = from_v2(demo())
            spec[key] = value
            with self.assertRaisesRegex(ValueError, key):
                normalize_v3(spec)

    def test_G04_restricted_regions_and_grid_overshoot_guards(self):
        for mutate in (lambda s: s["scenario"].update(restricted_regions=[{}]),
                       lambda s: s["mission"]["intent_params"]["observation_model"].update(grid_m=.01),
                       lambda s: s["planner"]["params"].update(lane_end_overshoot_m=.1)):
            spec = from_v2(demo())
            mutate(spec)
            with self.assertRaises(ValueError):
                normalize_v3(spec)

    def test_G05_recon_barrier_targets_semantics_and_planning_equal_v2(self):
        for filename in ("recon_shared_3uav.json", "recon_smoke_2uav_north.json", "recon_smoke_6uav.json"):
            for required in (False, True):
                with self.subTest(filename=filename, return_required=required):
                    spec = json.loads((ROOT / "missions" / filename).read_text(encoding="utf-8"))
                    spec["mission"]["return_required"] = required
                    old, new = compile_task(spec), compile_task(from_v2(spec))
                    self.assertEqual(new["schema_version"], 1)
                    self.assertEqual(new["phases"], old["phases"])
                    self.assertEqual(new["semantic_plan"], old["semantic_plan"])
                    self.assertEqual(new["planning"], old["planning"])
                    self.assertEqual(new["phases"][0]["targets"], new["phases"][1]["targets"])
                    validate_task_binding(new)

    def test_G05_binding_detects_mutated_target(self):
        scene = compile_task(from_v2(demo()))
        scene["phases"][0]["targets"]["uav_01"]["north_m"] += 1
        with self.assertRaisesRegex(ValueError, "differs"):
            validate_task_binding(scene)

    def test_continuous_mode_normalizes_and_compiles_schema2(self):
        spec = from_v2(demo(), "semantic_phase_route_v1")
        self.assertEqual(normalize_v3(spec), spec)
        scene = compile_task(spec)
        self.assertEqual(scene["schema_version"], 2)
        self.assertEqual([p["name"] for p in scene["phases"]], ["p00_approach", "p01_observe", "p02_return"])

    def test_G06_production_registry_and_exception_cleanup(self):
        self.assertEqual(registered_intents(), ("reconnaissance",))
        self.assertEqual(registered_planners(), ("equal_strip_lawnmower_v1",))
        with self.assertRaisesRegex(RuntimeError, "deliberate"):
            with temporary_registration(fixture_intent(), (fixture_planner(),)):
                self.assertIn("fixture_intent", registered_intents())
                self.assertEqual(get_planner("fixture_planner").version, "fixture_plan_v1")
                raise RuntimeError("deliberate")
        self.assertEqual(registered_intents(), ("reconnaissance",))
        self.assertEqual(registered_planners(), ("equal_strip_lawnmower_v1",))
        with self.assertRaisesRegex(ValueError, "unregistered"):
            get_intent("fixture_intent")

    def test_G06_duplicates_cannot_replace_existing_registry(self):
        with self.assertRaisesRegex(ValueError, "new IntentSpec"):
            with temporary_registration(get_intent("reconnaissance")):
                self.fail("production replacement should be impossible")
        with self.assertRaisesRegex(ValueError, "already exists"):
            with temporary_registration(fixture_intent(), (get_planner("equal_strip_lawnmower_v1"),)):
                self.fail("production planner replacement should be impossible")

    def test_G06_fixture_compiler_supports_own_semantic_phases(self):
        with temporary_registration(fixture_intent(), (fixture_planner(),)):
            spec = from_v2(demo())
            spec["mission"].update(intent="fixture_intent", intent_params={"objective": "fixture_objective"})
            spec["planner"] = dict(name="fixture_planner", params={})
            scene = compile_task(spec)
            self.assertEqual(len(scene["phases"]), 2)
            mapping = scene["semantic_plan"]["execution_phases"]
            self.assertEqual(mapping["leg_000"]["semantic_phase"], "fixture_service")
            self.assertTrue(mapping["leg_000"]["agents"]["uav_01"]["service_enabled"])
            self.assertFalse(mapping["leg_001"]["agents"]["uav_01"]["service_enabled"])

    def test_G06_planner_route_contract_rejects_missing_agents(self):
        invalid = replace(fixture_planner(), plan_routes=lambda spec: PlanResult({}, {}, {}))
        with temporary_registration(fixture_intent(), (invalid,)):
            spec = from_v2(demo())
            spec["mission"].update(intent="fixture_intent", intent_params={"objective": "fixture_objective"})
            spec["planner"] = dict(name="fixture_planner", params={})
            with self.assertRaisesRegex(ValueError, "every agent"):
                compile_task(spec)


def evidence_v3(scene):
    value = copy.deepcopy(scene)
    spec = value["task_spec"]
    spec["schema_version"] = 3
    spec["scenario"]["platform"] = spec.pop("platform")
    mission = spec["mission"]
    mission["intent_params"] = {key: mission.pop(key) for key in ("objective", "coverage_required", "observation_model")}
    spec["planner"] = dict(name="equal_strip_lawnmower_v1", params={})
    spec["execution"]["control_mode"] = "waypoint_barrier_v1"
    return value


class TaskV3EvaluationTests(unittest.TestCase):
    def test_G07_recon_hand_computable_dual_channel_equivalence(self):
        for variant in ("success", "insufficient", "gap", "missing_truth", "disagree", "return"):
            with self.subTest(variant=variant):
                scene, traces, events, metadata, clocks = legacy_evidence.fixture(return_required=variant == "return")
                truth = copy.deepcopy(traces)
                if variant == "insufficient":
                    traces["uav_02"] = copy.deepcopy(traces["uav_01"])
                    truth = copy.deepcopy(traces)
                elif variant == "gap":
                    traces["uav_01"].insert(1, (.5, None))
                    truth = copy.deepcopy(traces)
                elif variant == "missing_truth":
                    truth = {}
                elif variant == "disagree":
                    truth["uav_02"] = copy.deepcopy(truth["uav_01"])
                old = evaluate_mission(scene, traces, truth, events, metadata, 100, clocks)
                new = evaluate_mission(evidence_v3(scene), traces, truth, events, metadata, 100, clocks)
                self.assertEqual(new["phase_windows"], old["phase_windows"])
                for key in ("truth", "observation", "mission_success", "mission_success_observation", "semantic_consistency", "pass_for_eligibility"):
                    self.assertEqual(new["semantic_validation"][key], old["semantic_validation"][key])
                for key in ("planned_behaviors", "observed_behaviors", "mission_metrics"):
                    self.assertEqual(new["labels"][key], old["labels"][key])
                self.assertEqual(new["labels"]["label_provenance"]["validator_versions"], {"reconnaissance": "shared_coverage_v2"})

    def test_G07_fixture_uses_own_validator_and_behavior_callback(self):
        calls = []
        def own(scene, traces, windows, clocks):
            calls.append(traces)
            return {"conditions": {"own_condition": bool(traces)}, "metrics": {"own_value": 17}}
        with temporary_registration(fixture_intent(own), (fixture_planner(),)):
            scene, traces, events, metadata, clocks = legacy_evidence.fixture()
            scene = evidence_v3(scene)
            scene["task_spec"]["mission"].update(intent="fixture_intent", intent_params={"objective": "fixture_objective"})
            result = evaluate_mission(scene, traces, {}, events, metadata, 100, clocks)
            self.assertEqual(len(calls), 2)
            self.assertIs(result["labels"]["mission_success"], False)
            self.assertIs(result["labels"]["mission_success_observation"], True)
            self.assertEqual(result["labels"]["semantic_consistency"], "disagree")
            self.assertEqual(result["labels"]["planned_behaviors"], ["fixture_planned"])
            self.assertNotIn("coverage", result["semantic_validation"]["truth"])
            self.assertEqual(result["labels"]["label_provenance"]["validator_versions"], {"fixture_intent": "fixture_rule_v1"})

    def test_G07_legacy_v2_bypasses_registry(self):
        with patch("swarm_sim.registry.get_intent", side_effect=AssertionError("legacy must not dispatch")):
            self.assertTrue(legacy_evidence.evaluate(legacy_evidence.fixture())["labels"]["mission_success"])


if __name__ == "__main__":
    unittest.main()
