"""Synthetic metadata tests: never generate or execute held-out missions."""
import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swarm_sim.fast_dynamics import holdout as h


def fid(i):
    return "scene_" + f"{i:020x}"


def view(x=0, width=20, height=30, points=None):
    return [dict(width=width, height=height,
                 points=points if points is not None else [(x - 4, -20), (x + 4, -20)])]


def row(i, x=0, bases=None):
    return dict(family_id=fid(i), scene_content_sha256=f"{i:064x}", geometry=view(x),
                bases=[i] if bases is None else bases)


def task(i):
    return dict(family_id=fid(i), mission_id=f"t{i}")


class GeometryTests(unittest.TestCase):
    def test_order_invariance(self):
        a = view()
        b = copy.deepcopy(a)
        b[0]["points"].reverse()
        self.assertTrue(h.near(a, b))

    def test_d4(self):
        a = view(points=[(3, 7), (9, 11)], width=20, height=30)
        for swap in (False, True):
            for sx in (-1, 1):
                for sy in (-1, 1):
                    b = view(width=30 if swap else 20, height=20 if swap else 30,
                             points=[(sx * (y if swap else x), sy * (x if swap else y))
                                     for x, y in a[0]["points"]])
                    self.assertTrue(h.near(a, b))

    def test_translation_ids_heading_ignored(self):
        spec = dict(schema_version=3, scenario=dict(regions=[dict(type="rectangle", width_m=20,
                    height_m=30, min_east_m=0, min_north_m=0)], vehicles=[
                    dict(east_m=6, north_m=-5, id="a", heading_deg=0),
                    dict(east_m=14, north_m=-5, id="b", heading_deg=0)]))
        shifted = copy.deepcopy(spec)
        r = shifted["scenario"]["regions"][0]
        r.update(min_east_m=100, min_north_m=-90)
        for v in shifted["scenario"]["vehicles"]:
            v.update(east_m=v["east_m"]+100, north_m=v["north_m"]-90, id="renamed", heading_deg=91)
        self.assertEqual(h.geometry(spec), h.geometry(shifted))

    def test_tolerance_closed_boundary(self):
        self.assertTrue(h.near(view(), view(1)))
        self.assertFalse(h.near(view(), view(1.00001)))
        self.assertTrue(h.near(view(), view(width=21)))
        self.assertFalse(h.near(view(), view(width=21.00001)))

    def test_euclidean_not_coordinatewise(self):
        self.assertFalse(h.matching_within([(0, 0)], [(0.8, 0.8)], 1))

    def test_matching_does_not_reuse_vehicle(self):
        self.assertFalse(h.matching_within([(0, 0), (0.1, 0)], [(0, 0), (5, 0)], 1))

    def test_matching_requires_augmenting_path(self):
        self.assertTrue(h.matching_within([(0.5, 0), (0, 0)], [(0, 0), (1, 0)], 0.6))

    def test_count_is_significant(self):
        self.assertFalse(h.near(view(), view(points=[(0, -20)])))

    def test_unsupported_geometry_refused(self):
        with self.assertRaises(ValueError):
            h.geometry(dict(scenario=dict(vehicles=[{}], regions=[dict(type="circle")])))

    def test_v2_platform_projection(self):
        spec = dict(schema_version=2, scenario=dict(vehicles=[]), platform=dict(id="old"))
        self.assertEqual(h.task_scenario(spec)["platform"], {"id": "old"})
        self.assertNotIn("platform", spec["scenario"])


class SplitTests(unittest.TestCase):
    def test_fixed_serialization_and_dedup(self):
        raw = b'["scene_00000000000000000001","scene_00000000000000000002"]'
        self.assertEqual(h.component_id([fid(2), fid(1), fid(1)]), hashlib.sha256(raw).hexdigest())

    def test_full_hash_is_not_family_id(self):
        with self.assertRaises(ValueError):
            h.component_id(["a" * 64])

    def test_order_duplicates_rank_floor(self):
        groups = [[fid(i)] for i in range(5)]
        a = h.split_components(groups)
        b = h.split_components([g + g for g in reversed(groups)])
        self.assertEqual(a, b)
        self.assertEqual(sum(r["split_group"] == "calibration" for r in a), 2)
        self.assertEqual(a, sorted(a, key=lambda r: (r["rank"], r["component_id"])))
        for r in a:
            self.assertEqual(r["rank"], hashlib.sha256(("2026101202|"+r["component_id"]).encode()).hexdigest())

    def test_insufficient_candidates_do_not_freeze(self):
        self.assertIsNone(h.split_components([[fid(1)]])[0]["split_group"])
        self.assertEqual(h.split_components([]), [])

    def test_duplicate_membership_refused(self):
        with self.assertRaises(ValueError):
            h.split_components([[fid(1)], [fid(1)]])

    def test_transitive_near_and_old_contamination(self):
        old = {fid(99): row(99, x=0)}
        new = {fid(i): row(i, x=x) for i, x in [(1, 0.8), (2, 1.6), (3, 2.4), (4, 10), (5, 15)]}
        result = h.build_registry(old, new, [task(i) for i in range(1, 6)])
        by = {t["family_id"]: t for t in result["tasks"]}
        for i in (1, 2, 3):
            self.assertEqual(by[fid(i)]["exclusion_reason"], "historical_contact")
            self.assertIsNone(by[fid(i)]["split_group"])
        self.assertEqual(result["counts"]["eligible_components"], 2)
        self.assertTrue(result["effective_holdout_frozen"])

    def test_rejected_sibling_can_exclude_accepted_task(self):
        old = {fid(99): row(99, x=0)}
        new = {fid(1): row(1, x=0, bases=[1]), fid(2): row(2, x=20, bases=[1])}
        result = h.build_registry(old, new, [task(2)])
        self.assertEqual(result["tasks"][0]["exclusion_reason"], "historical_contact")
        self.assertEqual(result["status"], "BLOCKED")

    def test_rejected_only_component_not_candidate(self):
        result = h.build_registry({}, {fid(1): row(1)}, [])
        self.assertEqual(result["components"][0]["exclusion_reason"], "planning_rejected_only")

    def test_short_id_collision_refused(self):
        old = {fid(1): row(1)}
        new = copy.deepcopy(old)
        new[fid(1)]["scene_content_sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            h.build_registry(old, new, [task(1)])

    def test_task_status_not_execution_claim(self):
        result = h.build_registry({}, {fid(i): row(i, x=10*i) for i in (1, 2)}, [task(1), task(2)])
        for t in result["tasks"]:
            self.assertEqual(t["execution_status"], "NOT_RUN")
            self.assertIsNone(t["actual_result"])
            self.assertFalse(t["reference_episode_available"])


class ArtifactTests(unittest.TestCase):
    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.json"
            h.write_new_json(p, {"a": 1})
            with self.assertRaises(FileExistsError):
                h.write_new_json(p, {"a": 2})
            self.assertEqual(h.read_json(p), {"a": 1})

    def test_changed_registration_refused_before_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "registration.json"
            h.write_new_json(p, {})
            with patch.object(h, "generate_v2") as gen:
                with self.assertRaisesRegex(ValueError, "identity changed"):
                    h.freeze(p, "0" * 64)
                gen.assert_not_called()
            self.assertEqual(list(Path(tmp).iterdir()), [p])

    def test_existing_bundle_refused_before_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "registration.json"
            (Path(tmp) / "bundle").mkdir()
            h.write_new_json(p, dict(output_root=tmp))
            with patch.object(h, "generate_v2") as gen:
                with self.assertRaises(ValueError):
                    h.freeze(p, h.sha256(p))
                gen.assert_not_called()

    def test_changed_bound_source_refused_before_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "registration.json"
            source = Path(tmp) / "source.txt"
            source.write_text("changed", encoding="utf-8")
            h.write_new_json(p, dict(output_root=tmp, bindings=[dict(path=str(source), sha256="0"*64)], inputs=[]))
            with patch.object(h, "generate_v2") as gen:
                with self.assertRaisesRegex(ValueError, "registered source changed"):
                    h.freeze(p, h.sha256(p))
                gen.assert_not_called()
            self.assertFalse((Path(tmp) / "bundle").exists())

    def test_escape_refused_before_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "registration.json"
            h.write_new_json(p, dict(output_root=str(Path(tmp) / "elsewhere")))
            with patch.object(h, "generate_v2") as gen:
                with self.assertRaises(ValueError):
                    h.freeze(p, h.sha256(p))
                gen.assert_not_called()


class IndependentVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(__file__).resolve().parents[1] / "scripts/verify_fast_dynamics_holdout.py"
        spec = importlib.util.spec_from_file_location("independent_holdout_verifier", script)
        cls.verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.verifier)

    def test_permutation_oracle_boundary_and_no_reuse(self):
        oracle = self.verifier.similar
        self.assertTrue(oracle([(20,30,[(0,0),(8,0)])], [(20,30,[(1,0),(9,0)])]))
        self.assertFalse(oracle([(20,30,[(0,0),(8,0)])], [(20,30,[(1.01,0),(9.01,0)])]))
        self.assertFalse(oracle([(20,30,[(0,0),(0.1,0)])], [(20,30,[(0,0),(5,0)])]))

    def test_permutation_oracle_rotation(self):
        self.assertTrue(self.verifier.similar([(20,30,[(3,7),(9,11)])],
                                             [(30,20,[(-11,9),(-7,3)])]))

    def test_identity_verifier_detects_modified_frozen_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            h.write_new_json(base/"registration.json", {})
            h.write_new_json(base/"evaluation_split.json", {})
            h.write_new_json(base/"freeze_manifest.json", {"registration.json":"0"*64})
            with self.assertRaisesRegex(AssertionError, "frozen artifacts unchanged"):
                self.verifier.verify(base)


if __name__ == "__main__":
    unittest.main()
