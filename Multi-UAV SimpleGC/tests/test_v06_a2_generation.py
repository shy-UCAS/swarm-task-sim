"""A2 candidate-level selection and atomic family acceptance, without SITL."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swarm_sim.dataset import family_split
from swarm_sim.generation_v2 import flight_pattern_choice, generate_v2, normalize_profile
from swarm_sim.registry import FLIGHT_PATTERNS


ROOT = Path(__file__).resolve().parents[1]


def profile(mode="random", candidates=2):
    result = normalize_profile(ROOT / "generation_profiles/tri_intent_v06_pilot.json")
    result.update(base_scene_count=1, max_candidates_per_base=candidates, flight_pattern_mode=mode)
    return result


def candidate_draws(candidate):
    result = {key: candidate[key] for key in ("candidate_id", "base_index", "candidate_index",
        "scene_seed", "family_id", "sampled_parameters", "shared_mission_params")}
    result["task_seeds"] = [(item["intent"], item["variant_index"], item["task_seed"])
                            for item in candidate["attempts"]]
    return result


class V06A2GenerationTests(unittest.TestCase):
    def setUp(self):
        self.first, self.second = FLIGHT_PATTERNS["reconnaissance"]

    def choice(self, master_seed, base_index, intent, variant_index, mode="random", *, candidate_index=0):
        # Controlled draw makes the first candidate's selected recon fail.
        # Both other intents still compile, preserving all rejection evidence.
        if intent == "reconnaissance" and mode == "random" and candidate_index == 0:
            return self.second
        return FLIGHT_PATTERNS[intent][0]

    def compiler(self, spec):
        if spec["flight_pattern"] == self.second:
            raise ValueError("test-only infeasible selected geometry")
        return {"task_spec": copy.deepcopy(spec)}

    def test_candidate_identity_changes_independent_pattern_substream(self):
        draws = [flight_pattern_choice(2026100812, 0, "reconnaissance", 0, candidate_index=index)
                 for index in range(40)]
        self.assertEqual(set(draws), {self.first, self.second})
        self.assertEqual(draws, [flight_pattern_choice(2026100812, 0, "reconnaissance", 0, candidate_index=index)
                                for index in range(40)])
        self.assertEqual([flight_pattern_choice(2026100812, 0, "reconnaissance", 0, "first", candidate_index=index)
                          for index in range(40)], [self.first] * 40)

    def test_draw_all_selected_patterns_before_compile_and_reject_whole_family(self):
        draws, compiled = [], []

        def choose(*args, **kwargs):
            selected = self.choice(*args, **kwargs)
            draws.append((kwargs["candidate_index"], args[2], selected))
            return selected

        def compile_selected(spec):
            self.assertEqual(len(draws) % 3, 0, "all three draws precede the first compile")
            compiled.append((spec["mission"]["intent"], spec["flight_pattern"]))
            return self.compiler(spec)

        with tempfile.TemporaryDirectory() as temporary, \
                patch("swarm_sim.generation_v2.flight_pattern_choice", side_effect=choose), \
                patch("swarm_sim.tasks.compile_task", side_effect=compile_selected):
            output = Path(temporary) / "generated"
            result = generate_v2(profile(), output)
            self.assertEqual(len(compiled), 6, "compile each selected task once; no first-pattern fallback")
            self.assertEqual(len(result["candidates"]), 2)
            failed, accepted = result["candidates"]
            self.assertEqual(failed["status"], "planning_rejected")
            self.assertEqual(accepted["status"], "accepted")
            self.assertEqual(len(failed["attempts"]), 3)
            rejected = [item for item in failed["attempts"] if item["status"] == "planning_rejected"]
            self.assertEqual(len(rejected), 1)
            self.assertEqual(rejected[0]["selected_flight_pattern"], self.second)
            self.assertIn("test-only infeasible", rejected[0]["reason"])
            self.assertTrue(all(item["status"] == "planned" for item in accepted["attempts"]))
            listing = json.loads((output / "mission_list.json").read_text(encoding="utf-8"))["missions"]
            self.assertEqual(len(listing), 3)
            self.assertEqual({item["candidate_id"] for item in listing}, {accepted["candidate_id"]})
            self.assertEqual({item["family_id"] for item in listing}, {accepted["family_id"]})
            self.assertTrue(all(item["status"] == "planned" and item["scene"] and item["scene_sha256"] for item in listing))
            self.assertEqual(result["counts"]["rejected_candidates"], 1)
            self.assertEqual(result["counts"]["rejected_variants"], 1)
            for item in failed["attempts"]:
                task = json.loads((output / item["task"]).read_text(encoding="utf-8"))
                self.assertEqual(task["flight_pattern"], item["selected_flight_pattern"])
            self.assertEqual(len(list((output / "missions").glob("*.json"))), 3)
            self.assertEqual(len(list((output / "scenes").glob("*.json"))), 3)

    def test_exhausted_candidate_never_publishes_successful_siblings(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch("swarm_sim.generation_v2.flight_pattern_choice", side_effect=self.choice), \
                patch("swarm_sim.tasks.compile_task", side_effect=self.compiler):
            output = Path(temporary) / "generated"
            result = generate_v2(profile(candidates=1), output)
            self.assertEqual(result["bases"][0]["status"], "rejected")
            self.assertEqual(result["counts"]["accepted_bases"], 0)
            self.assertEqual(result["counts"]["planned_missions"], 0)
            self.assertEqual(sum(item["status"] == "planned" for item in result["candidates"][0]["attempts"]), 2)
            self.assertEqual(json.loads((output / "mission_list.json").read_text(encoding="utf-8"))["missions"], [])
            self.assertEqual(list((output / "missions").iterdir()), [])
            self.assertEqual(list((output / "scenes").iterdir()), [])

    def test_unselected_first_pattern_is_never_used_as_acceptance_gate(self):
        compiled = []

        def compile_only_selected(spec):
            compiled.append(spec["flight_pattern"])
            if spec["mission"]["intent"] == "reconnaissance" and spec["flight_pattern"] == self.first:
                raise ValueError("unselected first pattern must not be compiled")
            return {"task_spec": copy.deepcopy(spec)}

        with tempfile.TemporaryDirectory() as temporary, \
                patch("swarm_sim.generation_v2.flight_pattern_choice", side_effect=self.choice), \
                patch("swarm_sim.tasks.compile_task", side_effect=compile_only_selected):
            result = generate_v2(profile(candidates=1), Path(temporary) / "generated")
            self.assertEqual(result["counts"]["accepted_bases"], 1)
            self.assertEqual(result["counts"]["planned_missions"], 3)
            self.assertEqual(len(compiled), 3)
            self.assertIn(self.second, compiled)
            self.assertNotIn(self.first, compiled)

    def test_same_candidate_common_draws_survive_different_acceptance_sets(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch("swarm_sim.generation_v2.flight_pattern_choice", side_effect=self.choice), \
                patch("swarm_sim.tasks.compile_task", side_effect=self.compiler):
            results = {mode: generate_v2(profile(mode), Path(temporary) / mode) for mode in ("first", "random")}
            first_candidate = results["first"]["candidates"][0]
            random_candidate = results["random"]["candidates"][0]
            self.assertEqual(candidate_draws(first_candidate), candidate_draws(random_candidate))
            self.assertEqual(family_split(first_candidate["family_id"]), family_split(random_candidate["family_id"]))
            self.assertEqual(first_candidate["status"], "accepted")
            self.assertEqual(random_candidate["status"], "planning_rejected")
            self.assertNotEqual(results["first"]["bases"][0]["selected_candidate"],
                                results["random"]["bases"][0]["selected_candidate"])


if __name__ == "__main__":
    unittest.main()
