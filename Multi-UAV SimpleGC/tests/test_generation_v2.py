"""G01/G02/G03/G11/G12: scene identity, atomic sampling and frozen v1 output."""

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from swarm_sim.dataset import family_split
from swarm_sim.families import FAMILY_SCHEME, scene_content, scene_content_hash, scene_family_id
from swarm_sim.generation import canonical_hash, file_hash, generate, verify_generation
from swarm_sim.generation_v2 import mission_seed, normalize_profile, scene_seed
from swarm_sim.mission_v3 import from_v2
from swarm_sim.registry import get_intent, registered_intents, temporary_registration
from swarm_sim.scene_samplers import SamplerSpec, get_sampler, registered_samplers, temporary_sampler


ROOT = Path(__file__).resolve().parents[1]


def v3_template():
    return from_v2(json.loads((ROOT / "missions/recon_shared_3uav.json").read_text(encoding="utf-8")))


def profile(count=2):
    return dict(schema_version=2, master_seed=927, base_scene_count=count, max_candidates_per_base=2,
        scene_sampler=dict(name="strip_aligned_v1", params=dict(vehicle_counts=[2], partition_axes=["east"],
            strip_width_m=[12, 12], sweep_length_m=[8, 8], region_east_m=[-20, 0], region_north_m=[-20, 0],
            entry_distance_m=[10, 10], entry_sides=["low"])),
        shared_mission_params=dict(speeds_m_s=[2, 2.5], return_required=[True, False]),
        missions=[dict(intent="reconnaissance", template_spec=v3_template(), variant_speed_factors=[1.0])],
        require_all_missions_feasible=True)


def fixture_sampler():
    # Test-only fixed physical scene: does not depend on the intent or its routes.
    return SamplerSpec("fixture_fixed_scene", True, lambda p: dict(p),
                       lambda scene, params, rng: (copy.deepcopy(scene), {"fixture": True}))


def add_fixture(data):
    template = v3_template()
    template["mission"]["intent"] = "fixture_scan"
    data["missions"].append(dict(intent="fixture_scan", template_spec=template, variant_speed_factors=[1.0]))
    return data


class FamilyContentTests(unittest.TestCase):
    def test_g01_family_ignores_all_nonphysical_sections(self):
        original = v3_template()
        changed = copy.deepcopy(original)
        changed.update(task_id="renamed", seed=999)
        changed["scenario"]["scene_id"] = "renamed_scene"
        changed["mission"] = {"different_intent": True}
        changed["planner"] = {"different_planner": 99}
        changed["execution"] = {"speed_m_s": 15, "takeoff_alt_m": 50}
        self.assertEqual(scene_family_id(original), scene_family_id(changed))

    def test_g02_geometry_position_heading_origin_world_and_platform_change_identity(self):
        original = v3_template()
        mutators = [lambda s: s["regions"][0].update(width_m=53),
                    lambda s: s["vehicles"][0].update(east_m=10),
                    lambda s: s["vehicles"][0].update(heading_deg=90),
                    lambda s: s["origin"].update(lat=31),
                    lambda s: s["world"].update(east_bounds_m=[-90, 100]),
                    lambda s: s["platform"].update(id="other_platform"),
                    lambda s: s["restricted_regions"].append(dict(id="avoid", type="rectangle",
                        min_east_m=1, min_north_m=1, width_m=1, height_m=1))]
        for mutate in mutators:
            changed = copy.deepcopy(original)
            mutate(changed["scenario"])
            self.assertNotEqual(scene_family_id(original), scene_family_id(changed))

    def test_g02_renumbering_region_ids_and_tied_vehicle_order_do_not_change_identity(self):
        original = v3_template()
        original["scenario"]["vehicles"][1].update(east_m=9, north_m=-15, heading_deg=90)
        changed = copy.deepcopy(original)
        changed["scenario"]["regions"][0]["id"] = "renamed"
        changed["scenario"]["vehicles"].reverse()
        for index, vehicle in enumerate(changed["scenario"]["vehicles"]):
            vehicle.update(id=f"renamed_{index}", sysid=100+index)
        self.assertEqual(scene_family_id(original), scene_family_id(changed))

    def test_canonical_rounding_numeric_equivalence_and_known_projection(self):
        scenario = dict(origin=dict(lat=30, lon=120, alt_msl_m=-0.0),
            world=dict(east_bounds_m=[-10, 10], north_bounds_m=[-10, 10], flight_up_bounds_m=[3, 20]),
            regions=[dict(id="R", type="rectangle", min_east_m=0, min_north_m=0, width_m=2.0000005, height_m=4)],
            restricted_regions=[], vehicles=[dict(id="a", sysid=1, east_m=0, north_m=-2, heading_deg=360)],
            platform=dict(id="p", ignored_limit=999), scene_id="ignored")
        expected = dict(origin=dict(lat=30.0, lon=120.0, alt_msl_m=0.0),
            world=dict(east_bounds_m=[-10.0, 10.0], north_bounds_m=[-10.0, 10.0], flight_up_bounds_m=[3.0, 20.0]),
            regions=[dict(type="rectangle", min_east_m=0.0, min_north_m=0.0, width_m=2.000001, height_m=4.0)],
            restricted_regions=[], vehicles=[dict(east_m=0.0, north_m=-2.0, heading_deg=0.0)], platform_id="p")
        self.assertEqual(scene_content(scenario), expected)
        self.assertEqual(scene_content_hash(scenario), canonical_hash(expected))
        changed = copy.deepcopy(scenario)
        changed["vehicles"][0].update(east_m=-0.0, heading_deg=0)
        changed["regions"][0]["width_m"] = 2.000001
        self.assertEqual(scene_family_id(scenario), scene_family_id(changed))
        for invalid in (True, float("nan"), float("inf")):
            changed["vehicles"][0]["heading_deg"] = invalid
            with self.assertRaises(ValueError):
                scene_content(changed)


class GeneratorV2Tests(unittest.TestCase):
    def test_g11_reproducible_files_metadata_and_seeds(self):
        with tempfile.TemporaryDirectory() as temp:
            left, right = Path(temp)/"left", Path(temp)/"right"
            a, b = generate(profile(), left), generate(profile(), right)
            self.assertEqual(a["artifact_sha256"], b["artifact_sha256"])
            self.assertEqual((left/"generation_manifest.json").read_bytes(), (right/"generation_manifest.json").read_bytes())
            listing, _ = verify_generation(left/"mission_list.json")
            self.assertEqual(len(listing["missions"]), 2)
            self.assertFalse(a["scene_sampler"]["intent_agnostic"])
            for entry in listing["missions"]:
                spec = json.loads((left/entry["task"]).read_text())
                self.assertEqual(entry["family_id"], scene_family_id(spec))
                self.assertEqual(entry["family_scheme"], FAMILY_SCHEME)
                self.assertEqual(entry["scene_content_sha256"], scene_content_hash(spec))
                self.assertEqual(entry["control_mode"], "waypoint_barrier_v1")
                self.assertEqual(entry["scene_seed"], scene_seed(927, entry["base_index"], 0))
                self.assertEqual(spec["seed"], mission_seed(entry["scene_seed"], entry["intent"], entry["template_id"], 0))

    def test_g01_generator_geometry_does_not_depend_on_mission_or_execution(self):
        first, second = profile(), profile()
        second["missions"][0]["template_spec"]["mission"]["intent_params"]["coverage_required"] = .8
        second["missions"][0]["template_spec"]["execution"]["takeoff_alt_m"] = 9
        second["shared_mission_params"]["speeds_m_s"] = [3]
        with tempfile.TemporaryDirectory() as temp:
            a = generate(first, Path(temp)/"a")
            b = generate(second, Path(temp)/"b")
            self.assertEqual([x["family_id"] for x in a["bases"]], [x["family_id"] for x in b["bases"]])

    def test_g03_same_scene_two_intents_have_same_family_split_and_shared_variables(self):
        intent = replace(get_intent("reconnaissance"), name="fixture_scan")
        data = add_fixture(profile(1))
        data["scene_sampler"] = dict(name="fixture_fixed_scene", params={})
        with temporary_registration(intent), temporary_sampler(fixture_sampler()), tempfile.TemporaryDirectory() as temp:
            result = generate(data, Path(temp)/"out")
            listing, _ = verify_generation(Path(result["mission_list"]))
            entries = listing["missions"]
            self.assertEqual({e["intent"] for e in entries}, {"reconnaissance", "fixture_scan"})
            self.assertEqual(len({e["family_id"] for e in entries}), 1)
            self.assertEqual(len({family_split(e["family_id"]) for e in entries}), 1)
            self.assertEqual(entries[0]["shared_mission_params"], entries[1]["shared_mission_params"])
            self.assertEqual(result["counts"]["accepted_bases"], 1)
        self.assertEqual(registered_intents(), ("patrol", "rapid_passage", "reconnaissance"))
        self.assertEqual(registered_samplers(), ("random_spawn_v1", "random_spawn_v2", "strip_aligned_v1"))

    def test_v05b_twenty_candidate_budget_does_not_expand_legacy_samplers(self):
        old = profile(1)
        old["max_candidates_per_base"] = 11
        with self.assertRaisesRegex(ValueError, "requires random_spawn_v2"):
            normalize_profile(old)
        updated = normalize_profile(ROOT / "generation_profiles/dual_intent_v05b.json")
        self.assertEqual(updated["max_candidates_per_base"], 20)
        self.assertEqual(updated["scene_sampler"]["name"], "random_spawn_v2")

    def test_g11_non_agnostic_multi_intent_is_rejected_before_output(self):
        with temporary_registration(replace(get_intent("reconnaissance"), name="fixture_scan")), tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/"out"
            with self.assertRaisesRegex(ValueError, "non-intent-agnostic"):
                generate(add_fixture(profile()), out)
            self.assertFalse(out.exists())

    def test_g11_one_intent_failure_rejects_whole_family_with_attributed_reason(self):
        def reject(params):
            raise ValueError("fixture intentionally infeasible")
        intent = replace(get_intent("reconnaissance"), name="fixture_scan", normalize_params=reject)
        data = add_fixture(profile(1))
        data["scene_sampler"] = dict(name="fixture_fixed_scene", params={})
        with temporary_registration(intent), temporary_sampler(fixture_sampler()), tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/"out"
            result = generate(data, out)
            self.assertEqual(result["counts"]["accepted_bases"], 0)
            self.assertEqual(result["counts"]["rejected_candidates"], 2)
            self.assertEqual(result["counts"]["planned_missions"], 0)
            self.assertEqual(list((out/"missions").iterdir()), [])
            self.assertEqual(list((out/"scenes").iterdir()), [])
            self.assertEqual(len(result["rejections"]), 2)
            for rejection in result["rejections"]:
                self.assertEqual(rejection["intent"], "fixture_scan")
                self.assertTrue(rejection["family_id"].startswith("scene_"))
                self.assertIn("intentionally infeasible", rejection["reason"])
            for candidate in result["candidates"]:
                self.assertEqual([a["status"] for a in candidate["attempts"]], ["planning_rejected", "planned"])

    def test_g11_failed_speed_variant_does_not_publish_successful_sibling(self):
        data = profile(1)
        data["missions"][0]["variant_speed_factors"] = [1, 100]
        with tempfile.TemporaryDirectory() as temp:
            result = generate(data, Path(temp)/"out")
            self.assertEqual(result["counts"]["planned_missions"], 0)
            self.assertEqual(result["counts"]["rejected_variants"], 2)
            self.assertTrue(all(r["variant_index"] == 1 for r in result["rejections"]))

    def test_g11_multi_intent_speed_factor_mismatch_is_rejected(self):
        data = add_fixture(profile())
        data["scene_sampler"] = dict(name="fixture_fixed_scene", params={})
        data["missions"][1]["variant_speed_factors"] = [1.2]
        with temporary_registration(replace(get_intent("reconnaissance"), name="fixture_scan")), temporary_sampler(fixture_sampler()):
            with self.assertRaisesRegex(ValueError, "share variant_speed_factors"):
                normalize_profile(data)

    def test_g11_mission_order_does_not_change_generation(self):
        data = add_fixture(profile(1))
        data["scene_sampler"] = dict(name="fixture_fixed_scene", params={})
        reverse = copy.deepcopy(data)
        reverse["missions"].reverse()
        with temporary_registration(replace(get_intent("reconnaissance"), name="fixture_scan")), temporary_sampler(fixture_sampler()), tempfile.TemporaryDirectory() as temp:
            a = generate(data, Path(temp)/"a")
            b = generate(reverse, Path(temp)/"b")
            self.assertEqual(a["artifact_sha256"], b["artifact_sha256"])

    def test_g11_repeated_physical_scene_reuses_family_shared_choices(self):
        data = profile(5)
        data["scene_sampler"] = dict(name="fixture_fixed_scene", params={})
        data["shared_mission_params"]["speeds_m_s"] = [1, 2, 3, 4, 5, 6]
        with temporary_sampler(fixture_sampler()), tempfile.TemporaryDirectory() as temp:
            result = generate(data, Path(temp)/"out")
            self.assertEqual(result["counts"]["accepted_bases"], 5)
            self.assertEqual(len({c["family_id"] for c in result["candidates"]}), 1)
            self.assertEqual(len({canonical_hash(c["shared_mission_params"]) for c in result["candidates"]}), 1)

    def test_profile_bounds_strictness_and_existing_output(self):
        mutations = [lambda p: p.update(master_seed=True), lambda p: p.update(require_all_missions_feasible=False),
                     lambda p: p.update(extra=1), lambda p: p["scene_sampler"]["params"].update(strip_width_m=[True, 12]),
                     lambda p: p["shared_mission_params"].update(speeds_m_s=[float("nan")]),
                     lambda p: p["missions"][0].update(intent="unregistered")]
        for mutate in mutations:
            data = profile()
            mutate(data)
            with self.assertRaises(ValueError):
                normalize_profile(data)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "already exists"):
                generate(profile(), Path(temp))

    def test_sampler_registration_is_restored_after_exception_and_cannot_replace_production(self):
        with self.assertRaisesRegex(RuntimeError, "fixture"):
            with temporary_sampler(fixture_sampler()):
                self.assertTrue(get_sampler("fixture_fixed_scene").intent_agnostic)
                raise RuntimeError("fixture")
        self.assertEqual(registered_samplers(), ("random_spawn_v1", "random_spawn_v2", "strip_aligned_v1"))
        with self.assertRaises(ValueError):
            with temporary_sampler(get_sampler("strip_aligned_v1")):
                self.fail("must not overwrite production")

    def test_g12_all_100_legacy_tasks_match_preexisting_frozen_artifact_hashes(self):
        golden = ROOT/"generated/recon_pilot_v03_20260930"
        expected = json.loads((golden/"generation_manifest.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            result = generate(golden/"generation_profile.json", Path(temp)/"legacy")
            self.assertEqual(result["counts"]["planned_missions"], 100)
            self.assertEqual(result["artifact_sha256"], expected["artifact_sha256"])
            for name, digest in expected["artifact_sha256"].items():
                self.assertEqual(file_hash(golden/name), digest, name)


if __name__ == "__main__":
    unittest.main()
