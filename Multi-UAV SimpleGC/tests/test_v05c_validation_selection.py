"""Offline selection and VP4 derivation checks; no SITL is started."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.select_v05c_validation import (accepted_views, choose_case, choose_cases, derive_vp4,
                                           validate_dr_review, write_bundle)
from swarm_sim.generation import canonical_hash, file_hash, verify_generation
from swarm_sim.generation_v2 import normalize_profile
from swarm_sim.tasks import compile_task, validate_task_binding


ROOT = Path(__file__).resolve().parents[1]


def row(base, n, side="north", laps=2, returning=True, margin=10.0):
    return dict(base_index=base, candidate_id=f"candidate_{base}", vehicle_count=n,
        entry_side=side, laps=laps, return_required=returning,
        patrol_prefilter_margin_m=margin,
        entries={intent: dict(mission_id=f"{intent}_{base}")
                 for intent in ("patrol", "reconnaissance")})


class V05cSelectionTests(unittest.TestCase):
    def test_strict_selection_vp2_prefilter_margin_and_vp4_source(self):
        rows = [row(0, 2, laps=3, returning=False),
                row(1, 3, side="east", laps=2, returning=True),
                row(2, 4, margin=3.0), row(5, 4, margin=0.4)]
        selected = choose_cases(rows)
        self.assertEqual(selected["VP1"]["selected_base_index"], 1)
        self.assertEqual(selected["VP2"]["selected_base_index"], 5)
        self.assertEqual(selected["VP3"]["selected_base_index"], 0)
        self.assertEqual(selected["VR1"]["selected_base_index"], 1)
        self.assertEqual(selected["VR2"]["selected_base_index"], 2)
        self.assertEqual(selected["VP4"]["selected_base_index"], 1)
        self.assertTrue(all(not value["relaxed"] for value in selected.values()))

    def test_relax_direction_then_k_then_return_without_changing_n(self):
        # VR1 relaxes direction only. VP1 relaxes K then return.
        rows = [row(1, 3, side="north", laps=3, returning=False),
                row(2, 4, side="west", laps=2, returning=True)]
        vr = choose_case(rows, "VR1")
        vp = choose_case(rows, "VP1")
        self.assertEqual([item["criterion"] for item in vr["relaxed"]], ["entry_sides"])
        self.assertEqual([item["criterion"] for item in vp["relaxed"]],
                         ["laps", "return_required"])
        self.assertEqual([item["eligible_count"] for item in vp["filter_trace"]], [0, 0, 1])
        with self.assertRaisesRegex(ValueError, "no accepted N=2"):
            choose_case(rows, "VP3")

    def test_vp4_only_changes_hold_and_compiles(self):
        original = json.loads((ROOT / "missions/v3/patrol_route_v05.json").read_text(encoding="utf-8"))
        snapshot = copy.deepcopy(original)
        derived, scene = derive_vp4(original)
        self.assertEqual(original, snapshot)
        self.assertEqual(derived["seed"], original["seed"])
        self.assertEqual(derived["scenario"], original["scenario"])
        self.assertEqual(derived["mission"], original["mission"])
        self.assertEqual(derived["planner"], original["planner"])
        self.assertEqual(derived["execution"]["terminal_hold_s"], 1)
        self.assertEqual(scene["task_spec"], derived)
        with self.assertRaisesRegex(ValueError, "terminal_hold_s=0"):
            derive_vp4(derived)

    def test_old_profile_cannot_be_used_for_v05c_validation(self):
        with self.assertRaisesRegex(ValueError, "random_spawn_v2"):
            accepted_views(ROOT / "generation_profiles/dual_intent_v05.json",
                           ROOT / "unused_generated", ROOT / "unused_review.json")

    def test_dr_review_all_gates_and_exact_source_binding_required(self):
        profile_path = ROOT / "generation_profiles/dual_intent_v05.json"
        profile = normalize_profile(profile_path)
        with tempfile.TemporaryDirectory() as temp:
            generated = Path(temp) / "generated"
            generated.mkdir()
            (generated / "generation_manifest.json").write_text("{}", encoding="utf-8")
            review = dict(gate={"pass": True, "joint": True, "strata": True,
                                "observe": True, "v05c_v05b_invariant": True},
                generation_manifest_file_sha256=file_hash(generated / "generation_manifest.json"),
                profile_file_sha256=file_hash(profile_path),
                profile_canonical_sha256=canonical_hash(profile))
            path = Path(temp) / "review.json"
            def save():
                path.write_text(json.dumps(review), encoding="utf-8")
            save()
            self.assertEqual(validate_dr_review(path, profile_path, profile, generated), review)
            review["gate"]["v05c_v05b_invariant"] = False
            save()
            with self.assertRaisesRegex(ValueError, "failed or incomplete gate"):
                validate_dr_review(path, profile_path, profile, generated)
            review["gate"]["v05c_v05b_invariant"] = True
            save()
            review["gate"]["observe"] = False
            save()
            with self.assertRaisesRegex(ValueError, "failed or incomplete gate"):
                validate_dr_review(path, profile_path, profile, generated)
            review["gate"]["observe"] = True
            review["generation_manifest_file_sha256"] = "wrong"
            save()
            with self.assertRaisesRegex(ValueError, "does not bind"):
                validate_dr_review(path, profile_path, profile, generated)
            path.unlink()
            with self.assertRaises(FileNotFoundError):
                validate_dr_review(path, profile_path, profile, generated)

    def test_separate_bundle_is_hash_bound_and_runnable_without_sitl(self):
        profile = normalize_profile(ROOT / "generation_profiles/dual_intent_v05.json")
        with tempfile.TemporaryDirectory() as temp:
            generated = Path(temp) / "source"
            (generated / "missions").mkdir(parents=True)
            (generated / "scenes").mkdir()
            (generated / "generation_profile.json").write_text(json.dumps(profile), encoding="utf-8")
            rows, all_entries = [], []
            specs = ((0, 2, "north", 3, False), (1, 3, "east", 2, True),
                     (2, 4, "south", 2, True))
            for base, n, side, laps, returning in specs:
                entries = {}
                for intent, template_name in (("patrol", "patrol_route_v05.json"),
                                              ("reconnaissance", "recon_route_v05.json")):
                    task = json.loads((ROOT / "missions/v3" / template_name).read_text(encoding="utf-8"))
                    task.pop("family_id", None)
                    task.pop("family_scheme", None)
                    task["task_id"] = f"fixture_{intent}_{base}"
                    width = 80.0 if n == 4 else 54.0
                    if n == 4:
                        task["scenario"]["regions"][0].update(width_m=80.0, height_m=80.0)
                    task["scenario"]["vehicles"] = [dict(id=f"uav_{i+1:02d}", sysid=i+1,
                        east_m=width * (i + .5) / n, north_m=-20. if n == 4 else -15.,
                        heading_deg=0.) for i in range(n)]
                    task["mission"]["return_required"] = returning
                    if intent == "patrol":
                        task["mission"]["intent_params"]["laps"] = laps
                    scene = compile_task(task)
                    mission_id = f"{intent}_{base}"
                    task_path, scene_path = f"missions/{mission_id}.json", f"scenes/{mission_id}.json"
                    (generated / task_path).write_text(json.dumps(scene["task_spec"]), encoding="utf-8")
                    (generated / scene_path).write_text(json.dumps(scene), encoding="utf-8")
                    entry = dict(mission_id=mission_id, intent=intent,
                        family_id=scene["family_id"], task=task_path, scene=scene_path,
                        task_sha256=file_hash(generated / task_path),
                        scene_sha256=file_hash(generated / scene_path))
                    entries[intent] = entry
                    all_entries.append(entry)
                rows.append(row(base, n, side, laps, returning, margin=2.0 if n == 4 else 10.0)
                            | {"entries": entries})
            listing = dict(generation_profile_sha256=file_hash(generated / "generation_profile.json"),
                           missions=all_entries)
            (generated / "mission_list.json").write_text(json.dumps(listing), encoding="utf-8")
            manifest = {"candidates": [{"status": "accepted"}] * 3}
            (generated / "generation_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            review_path = Path(temp) / "review.json"
            review_path.write_text('{"gate":{"pass":true}}', encoding="utf-8")
            with patch("scripts.select_v05c_validation.accepted_views",
                       return_value=(profile, listing, manifest, rows, {"gate": {"pass": True}})):
                destination = Path(temp) / "validation_bundle"
                selection = write_bundle(ROOT / "generation_profiles/dual_intent_v05.json",
                                         generated, review_path, destination)
                selected_list, selected_manifest = verify_generation(destination / "mission_list.json")
                self.assertEqual(len(selected_list["missions"]), 6)
                self.assertEqual(selected_manifest["selection_version"], selection["version"])
                self.assertEqual(selected_manifest["source_review_sha256"], file_hash(review_path))
                self.assertEqual([entry["validation_case_id"] for entry in selected_list["missions"]],
                                 ["VP1", "VP2", "VP3", "VP4", "VR1", "VR2"])
                for entry in selected_list["missions"]:
                    validate_task_binding(json.loads((destination / entry["scene"]).read_text(encoding="utf-8")))
                vp1, vp4 = selected_list["missions"][0], selected_list["missions"][3]
                self.assertEqual(vp1["family_id"], vp4["family_id"])
                a = json.loads((destination / vp1["task"]).read_text(encoding="utf-8"))
                b = json.loads((destination / vp4["task"]).read_text(encoding="utf-8"))
                b["execution"]["terminal_hold_s"] = 0
                self.assertEqual(a, b)
                with self.assertRaisesRegex(ValueError, "already exists"):
                    write_bundle(ROOT / "generation_profiles/dual_intent_v05.json",
                                 generated, review_path, destination)


if __name__ == "__main__":
    unittest.main()
