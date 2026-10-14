"""Generic infrastructure regression tests, not acceptance of missing role planners."""
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

import numpy as np

from scene_v07.contract import SCHEMA_VERSION, UNITS, canonical_json
from task_v07.expansion.sampling import (INTENTS, ROLES, sample_common, build_descriptor,
                                        merge_units, derive_intent, sample_family_descriptors)
from task_v07.expansion.contracts import (P0ContractError, RouteBundle, UnimplementedRolePlanner,
                                         PlannerUnavailable, validate_route_bundle, validate_pair,
                                         validate_family_conditions, validate_model_input, permute_input)
from task_v07.expansion.geometry_checks import exact_frame_geometry, check_polyline, check_retreat_point
from task_v07.expansion.evaluation import (Evaluation, exported_evidence, evaluate,
                                         truncation_check, cross_negation)
from task_v07.expansion.views import make_views, diagnostic_summary
from scripts.audit_v07_s2_infrastructure import audit_geometry
from scripts.run_v07_s2_infrastructure import requests_for


def fixture(n=8, seed=27, facilities=3):
    scene = {"schema_version": SCHEMA_VERSION, "coordinate_system": "ENU", "units": dict(UNITS),
             "world": {"id": "world", "geometry": {"type": "Polygon", "vertices_m":
                       [[0, 0], [4000, 0], [4000, 4000], [0, 4000]]}},
             "entry_zones": [{"id": "entry_01", "geometry": {"type": "Polygon", "vertices_m":
                             [[40, 40], [300, 40], [300, 80], [40, 80]]}}], "entities": []}
    for i in range(facilities):
        center = [1000 + i * 900, 2000]
        base = {"type": "Circle", "center_m": center, "radius_m": 20.0} if i != 1 else {
            "type": "Polygon", "vertices_m": [[1880, 1980], [1920, 1980], [1920, 2020], [1880, 2020]]}
        fid = f"facility_{i+1:02d}"
        scene["entities"].append({"id": fid, "type": "facility", "geometry": base})
        for layer, offset in (("protected", 100), ("alert", 200), ("warning", 500)):
            zone = {**base, "radius_m": 20 + offset} if base["type"] == "Circle" else {
                **base, "type": "BufferedPolygon", "buffer_m": offset}
            scene["entities"].append({"id": fid + "_" + layer, "type": "protection_zone",
                                     "facility_id": fid, "layer": layer, "offset_m": offset, "geometry": zone})
    scene["entities"] += [{"id": "obstacle_01", "type": "hard_constraint_obstacle",
                           "geometry": {"type": "Circle", "center_m": [3000, 500], "radius_m": 70}},
                          {"id": "radar_01", "type": "radar", "geometry": {"type": "Point", "position_m": [500, 500]}}]
    family = {"family_id": f"family_{seed}", "map_id": f"map_{seed}", "sampling_seed": seed,
              "vehicle_count": n, "cruise_speed_m_s": 8.5, "task_altitude_m": 110.,
              "initial_states": [{"agent_id": f"uav_{i+1:02d}", "position_enu_m": [100+i*30, 50, 110],
                                  "velocity_enu_m_s": [0, 0, 0], "acceleration_enu_m_s2": [0, 0, 0]} for i in range(n)]}
    return scene, family


def toy_run(ids=("a", "b"), frames=31):
    t = np.arange(frames, dtype=np.int64) * 100000
    p = np.zeros((frames, len(ids), 3))
    for i in range(len(ids)):
        p[:, i] = np.c_[np.linspace(400, 600, frames), np.full(frames, 400+i*20), np.full(frames, 110)]
    return {"time_us": t, "p": p, "v": np.zeros_like(p), "agent_ids": list(ids), "execution_status": "completed"}


def toy_completion(scene, template, evidence):
    # Deliberately generic endpoint witness, not any production role criterion.
    found = np.flatnonzero(evidence.p[:, 0, 0] == template["marker"])
    return Evaluation("yes" if len(found) else "no" if evidence.complete else "unknown", {},
                      {"witness": int(found[0]) if len(found) else None})


def successful_record(family, intent, index, mode):
    skeleton = f"{family}_{intent}_{index}"
    return {"episode_id": f"{skeleton}_{mode}", "family_id": family, "skeleton_id": skeleton,
            "intent": intent, "mode": mode, "state": "generated", "path": f"{skeleton}/{mode}",
            "quality_valid": True, "audit_passed": True, "task_result": "success",
            "coordination_by_group": {"g1": mode, "g2": mode}, "condition_digest": skeleton,
            "scene_digest": family, "agent_ids": ["b", "a"], "aborted": False}


class SamplingTests(unittest.TestCase):
    def test_common_draws_equal_across_intents_and_family_speed_immutable(self):
        scene, family = fixture()
        for slot in range(12):
            descriptors = [build_descriptor(scene, family, intent, slot) for intent in INTENTS]
            self.assertTrue(all(d["common_draw"] == descriptors[0]["common_draw"] for d in descriptors))
            for d in descriptors:
                validate_family_conditions(d, family)
                self.assertEqual(derive_intent(d["task_groups"]), d["base_intent"])
                self.assertEqual(d["cruise_speed_m_s"], 8.5)
                self.assertEqual(sorted(a for g in d["task_groups"] for a in g["members"]),
                                 sorted(d["agent_ids"]))
                self.assertTrue(all(len(g["members"]) >= 2 for g in d["task_groups"]))
        self.assertEqual(family, fixture()[1])

    def test_requested_units_capped_at_two_members_per_unit(self):
        scene, family = fixture(n=3)
        draws = [sample_common(scene, family, i) for i in range(30)]
        self.assertTrue(any(d["unit_count_capped"] for d in draws))
        self.assertTrue(all(d["actual_unit_count"] == 1 and len(d["units"][0]["members"]) == 3 for d in draws))
        with self.assertRaises(ValueError):
            sample_common(scene, fixture(n=1)[1], 0)

    def test_both_approaches_and_unit_counts_are_sampled(self):
        scene, family = fixture()
        draws = [sample_common(scene, family, i) for i in range(80)]
        self.assertEqual({d["approach_mode"] for d in draws}, {"same_direction", "multi_direction"})
        self.assertEqual({d["actual_unit_count"] for d in draws}, {1, 2, 3})
        self.assertTrue(all(d["multi_direction_min_span_deg"] == 90 for d in draws))

    def test_merge_keeps_first_method_and_does_not_split_temporal_batches(self):
        units = [{"unit_id": f"u{i}", "members": [f"a{i}", f"b{i}"], "target_id": "f",
                  "role": "reconnaissance", "execution_method": method, "batch": i,
                  "between_group_offset_s": i * 60} for i, method in enumerate(("area_search", "close_observation"))]
        groups = merge_units(units)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["execution_method"], "area_search")
        self.assertEqual(groups[0]["between_group_offset_s"], 0)
        self.assertEqual(groups[0]["members"], ["a0", "a1", "b0", "b1"])
        units[1]["role"] = "transit"
        self.assertEqual(len(merge_units(units)), 2)

    def test_merge_rejects_duplicate_member(self):
        units = [{"unit_id": "u", "members": ["a", "a"], "target_id": "f",
                  "role": "transit", "execution_method": "transit"}]
        with self.assertRaises(ValueError):
            merge_units(units)

    def test_columns_do_not_follow_group_order_and_are_reproducible(self):
        scene, family = fixture(n=12)
        seen = set()
        for intent in INTENTS:
            d = build_descriptor(scene, family, intent, 0)
            self.assertEqual(canonical_json(d), canonical_json(build_descriptor(scene, family, intent, 0)))
            seen.add(tuple(d["agent_ids"]))
            self.assertNotEqual(d["agent_ids"], sorted(d["agent_ids"]))
        self.assertGreater(len(seen), 1)

    def test_worker_count_and_result_order_do_not_change_bytes(self):
        payloads = [(*fixture(seed=seed), 2) for seed in (7, 8)]
        serial = list(map(sample_family_descriptors, payloads))
        with ProcessPoolExecutor(max_workers=2) as pool:
            parallel = list(pool.map(sample_family_descriptors, payloads))
        self.assertEqual(canonical_json(serial), canonical_json(parallel))

    def test_all_descriptors_are_private_and_unexecuted(self):
        scene, family = fixture()
        records = sample_family_descriptors((scene, family, 2))
        self.assertEqual(len(records), 11)
        self.assertTrue(all(d["status"] == "awaiting_role_planner" and d["planned_geometry"] is None for d in records))
        self.assertEqual(len(requests_for(records)), 21)
        self.assertTrue(all(r["state"] == "pending" for r in requests_for(records)))


class ContractTests(unittest.TestCase):
    def test_route_interface_never_silently_returns_placeholder(self):
        with self.assertRaises(PlannerUnavailable):
            UnimplementedRolePlanner().plan({}, {}, {})

    def test_route_contract_and_paired_non_time_invariance(self):
        scene, family = fixture(n=2)
        d = build_descriptor(scene, family, "transit", 0)
        points = {a: [[100, 100, 110], [200, 100, 110]] for a in d["agent_ids"]}
        a = RouteBundle(points, {i: 0.0 for i in points})
        b = RouteBundle(deepcopy(points), {i: 41.3 for i in points})
        validate_route_bundle(a, d["agent_ids"])
        validate_pair(d, deepcopy(d), a, b)
        for key, value in (("cruise_speed_m_s", 2), ("agent_ids", list(reversed(d["agent_ids"])))):
            changed = {**deepcopy(d), key: value}
            with self.assertRaises(P0ContractError):
                validate_pair(d, changed, a, b)
        moved = deepcopy(points)
        moved[d["agent_ids"][0]][1][0] += 1
        with self.assertRaises(P0ContractError):
            validate_pair(d, d, a, RouteBundle(moved, b.departure_delays_s))

    def test_bad_waypoints_and_delays_rejected(self):
        for points, delay in (([[0, 0, 0], [.5, 0, 0]], 0), ([[0, 0, 0], [1, 0, 0]], .01),
                              ([[0, 0, 0], [1, 0, 0]], -1), ([[0, 0, 0], [np.nan, 1, 0]], 0)):
            with self.assertRaises(ValueError):
                validate_route_bundle(RouteBundle({"a": points}, {"a": delay}), ["a"])

    def test_family_mutation_is_p0(self):
        scene, family = fixture()
        d = build_descriptor(scene, family, "monitoring", 0)
        d["family_conditions"]["initial_states"][0]["position_enu_m"][0] += 1
        with self.assertRaises(P0ContractError):
            validate_family_conditions(d, family)

    def test_model_input_whitelist_nested_scene_and_permutation(self):
        scene, _ = fixture()
        run = toy_run()
        model = {"scene": scene, "x": np.concatenate([run["p"], run["v"]], axis=2),
                 "mask": np.ones((31, 2), bool), "t_s": run["time_us"]/1e6, "agent_ids": run["agent_ids"]}
        validate_model_input(model)
        other = permute_input(model, ["b", "a"])
        np.testing.assert_array_equal(other["x"], model["x"][:, [1, 0]])
        self.assertEqual(other["agent_ids"], ["b", "a"])
        for key in ("labels", "target", "role", "groups", "sampling_seed", "planned_route"):
            with self.subTest(key=key), self.assertRaises(P0ContractError):
                validate_model_input({**model, key: 1})
        changed = deepcopy(model)
        changed["scene"]["entities"][0]["assigned_target"] = True
        with self.assertRaises(P0ContractError):
            validate_model_input(changed)
        changed = deepcopy(model)
        changed["t_s"] += .1
        with self.assertRaises(P0ContractError):
            validate_model_input(changed)


class GeometryTests(unittest.TestCase):
    def test_independent_all_frame_audit_and_corruption(self):
        scene, _ = fixture()
        run = toy_run()
        targets = {"a": "facility_01", "b": "facility_02"}
        frame, report = exact_frame_geometry(scene, run, targets)
        self.assertEqual(audit_geometry(scene, run, frame, report, targets)["status"], "PASS")
        bad = deepcopy(frame)
        bad["region_all_facilities"][5, 0, 0] = 3
        audited = audit_geometry(scene, run, bad, report, targets)
        self.assertEqual(audited["differences"], 1)
        self.assertEqual(audited["status"], "FAIL")
        bad = deepcopy(frame)
        bad["agent_ids"] = np.array(["b", "a"])
        self.assertEqual(audit_geometry(scene, run, bad, report, targets)["status"], "FAIL")

    def test_circle_and_polygon_each_layer_micrometre_inside_outside(self):
        scene, _ = fixture()
        for fid, cx in (("facility_01", 1000), ("facility_02", 1900)):
            for offset, code in ((100, 3), (200, 2), (500, 1)):
                run = toy_run(ids=("a",))
                run["p"][..., 0] = cx + 20 + offset
                run["p"][..., 1] = 2000
                for delta, expected in ((-1e-6, code), (1e-6, code-1)):
                    run["p"][..., 0] = cx + 20 + offset + delta
                    frame, report = exact_frame_geometry(scene, run)
                    fi = frame["facility_ids"].tolist().index(fid)
                    self.assertTrue(np.all(frame["region_all_facilities"][:, 0, fi] == expected))
                    self.assertEqual(audit_geometry(scene, run, frame, report)["status"], "PASS")

    def test_geometry_id_alignment_and_separation_not_task_result(self):
        scene, _ = fixture()
        run = toy_run()
        run["p"][8, 1] = run["p"][8, 0] + [1.9, 0, 0]
        frame, report = exact_frame_geometry(scene, run)
        self.assertTrue(report["generation_error"])
        self.assertFalse(report["separation_affects_task_result"])
        other = {**run, "agent_ids": ["b", "a"], "p": run["p"][:, ::-1], "v": run["v"][:, ::-1]}
        changed, observed = exact_frame_geometry(scene, other)
        self.assertEqual(observed, report)
        np.testing.assert_array_equal(changed["region_all_facilities"], frame["region_all_facilities"][:, ::-1])
        run["p"][8, 1] = run["p"][8, 0] + [2, 0, 0]
        self.assertFalse(exact_frame_geometry(scene, run)[1]["generation_error"])

    def test_generic_forbidden_layer_policy_uses_all_facilities(self):
        scene, _ = fixture()
        run = toy_run()
        run["p"][:, 0, :2] = [2100, 2000]
        policy = {"a": {"facility_02": "alert"}, "b": {}}
        frame, report = exact_frame_geometry(scene, run, forbidden_layers=policy)
        self.assertEqual(report["forbidden_region_sample_count"], len(run["time_us"]))
        self.assertEqual(audit_geometry(scene, run, frame, report, forbidden_layers=policy)["status"], "PASS")

    def test_supplied_polyline_crossing_and_retreat_clearance(self):
        scene, _ = fixture()
        self.assertFalse(check_polyline(scene, [[2800, 500, 110], [3200, 500, 110]])["valid"])
        self.assertTrue(check_polyline(scene, [[2800, 700, 110], [3200, 700, 110]])["valid"])
        self.assertFalse(check_polyline(scene, [[800, 2000, 110], [1300, 2000, 110]],
                                        forbidden_regions=["facility_01_alert"])["valid"])
        self.assertTrue(check_retreat_point(scene, [700, 700])["valid"])
        self.assertFalse(check_retreat_point(scene, [2100, 2000])["valid"])

    def test_independent_audit_rejects_missing_fields_and_bad_grid(self):
        scene, _ = fixture()
        run = toy_run()
        frame, report = exact_frame_geometry(scene, run)
        missing = dict(frame)
        del missing["inside_hard_obstacle"]
        self.assertEqual(audit_geometry(scene, run, missing, report)["status"], "FAIL")
        run["time_us"] = run["time_us"] // 5
        self.assertEqual(audit_geometry(scene, run, frame, report)["status"], "FAIL")

    def test_zero_margin_polygon_intersection_still_rejected(self):
        scene, _ = fixture()
        scene["entities"][-2]["geometry"] = {"type": "Polygon", "vertices_m":
                                             [[2950, 450], [3050, 450], [3050, 550], [2950, 550]]}
        self.assertFalse(check_polyline(scene, [[2800, 500, 110], [3200, 500, 110]], margin_m=0)["valid"])
        with self.assertRaises(ValueError):
            check_retreat_point(scene, [500, 500], obstacle_margin_m=-1)

    def test_high_frequency_input_rejected(self):
        scene, _ = fixture()
        run = toy_run()
        run["time_us"] //= 5
        with self.assertRaises(ValueError):
            exact_frame_geometry(scene, run)

    def test_independent_auditor_cannot_import_authority(self):
        path = Path(importlib.util.find_spec("scripts.audit_v07_s2_infrastructure").origin)
        import ast
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any(name and name.startswith("task_v07") for name in imported))


class EvaluationTests(unittest.TestCase):
    def test_prefix_physically_excludes_future_and_is_read_only(self):
        evidence = exported_evidence(toy_run(), 1.5)
        self.assertEqual(len(evidence.time_us), 15)
        self.assertFalse(evidence.complete)
        self.assertEqual(evidence.time_us[-1], 1400000)
        with self.assertRaises(ValueError):
            evidence.p[0, 0, 0] = 123

    def test_truncation_hook_for_each_role_and_missing_criterion(self):
        scene, _ = fixture()
        for role in ROLES:
            with self.subTest(role=role):
                report = truncation_check(toy_completion, scene, {"role": role, "marker": 600}, toy_run(), 1.5)
                self.assertEqual(report["full_verdict"], "yes")
                self.assertEqual(report["prefix_verdict"], "unknown")
                self.assertEqual(report["status"], "PASS")
        self.assertEqual(truncation_check(None, scene, {}, toy_run(), 1.5)["status"], "not_run")

    def test_missing_event_and_future_claim(self):
        result = evaluate(toy_completion, {}, {"marker": 600}, exported_evidence(toy_run(), 1))
        self.assertIsNone(result.event_frames["witness"])
        self.assertEqual(result.verdict, "unknown")
        with self.assertRaises(P0ContractError):
            evaluate(lambda *args: Evaluation("yes", {}, {"future": 300}), {}, {}, exported_evidence(toy_run()))

    def test_cross_negation_all_ordered_combinations_without_subject_labels(self):
        templates = [{"family_id": "f", "intent": intent, "template_id": f"t{i}", "parameters": {"marker": 1000+i}}
                     for i, intent in enumerate(INTENTS)]
        episodes = []
        for i, intent in enumerate(INTENTS):
            run = toy_run()
            run["p"][:, 0, 0] = 1000+i
            episodes.append({"family_id": "f", "intent": intent, "episode_id": f"e{i}", "scene": {}, "run": run})
        result = cross_negation(templates, episodes, {i: toy_completion for i in INTENTS})
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["rows"]), 20)
        self.assertTrue(all(r["verdict"] == "no" for r in result["rows"]))
        pending = cross_negation(templates, episodes, {})
        self.assertEqual(pending["status"], "pending")
        self.assertTrue(all(c["tested"] == 0 for c in pending["combinations"]))
        bad = cross_negation(templates, episodes, {i: lambda *args: Evaluation("yes", {}, {}) for i in INTENTS})
        self.assertEqual(bad["status"], "FAIL")

    def test_evaluation_id_aligned_column_permutation(self):
        def callback(scene, template, evidence):
            index = evidence.agent_ids.index("a")
            return Evaluation("yes", {"end_x_for_a": float(evidence.p[-1, index, 0])}, {})
        run = toy_run()
        other = {**run, "agent_ids": ["b", "a"], "p": run["p"][:, ::-1], "v": run["v"][:, ::-1]}
        self.assertEqual(evaluate(callback, {}, {}, exported_evidence(run)),
                         evaluate(callback, {}, {}, exported_evidence(other)))


class ViewTests(unittest.TestCase):
    def records(self):
        return [successful_record("f", intent, index, mode) for intent in INTENTS
                for index in range(1 if intent == "transit" else 2) for mode in ("synchronous", "sequential")]

    def test_balanced_minimum_pairs_and_extended_without_copy(self):
        records = self.records()
        result = make_views(records, seed=9)
        self.assertEqual(result["counts"], {"primary": 10, "extended": 8, "aborted": 0, "failed": 0, "pending": 0})
        self.assertEqual(result, make_views(list(reversed(records)), seed=9))
        self.assertTrue(result["index_only"])
        self.assertEqual(result["family_balance"][0]["pairs_per_intent"], 1)

    def test_missing_intent_leaves_all_success_in_extended(self):
        rows = [r for r in self.records() if r["intent"] != "transit"]
        result = make_views(rows)
        self.assertEqual(result["counts"]["primary"], 0)
        self.assertEqual(result["counts"]["extended"], len(rows))

    def test_failure_abort_and_pending_not_in_primary(self):
        scene, family = fixture()
        pending = requests_for(sample_family_descriptors((scene, family, 2)))
        result = make_views(pending)
        self.assertEqual(result["counts"]["pending"], 21)
        self.assertEqual(result["counts"]["aborted"], 0)
        self.assertEqual(result["counts"]["failed"], 0)
        aborted = {**successful_record("f", "penetration", 99, "synchronous"), "aborted": True, "task_result": "failure"}
        failed = {**successful_record("f", "transit", 98, "synchronous"), "task_result": "failure"}
        result = make_views([aborted, failed])
        self.assertEqual(result["counts"]["aborted"], 1)
        self.assertEqual(result["counts"]["failed"], 1)

    def test_task_success_with_wrong_timing_not_pair(self):
        rows = self.records()
        rows[0]["coordination_by_group"]["g1"] = "other"
        result = make_views(rows)
        self.assertEqual(result["counts"]["primary"], 0)
        self.assertEqual(result["counts"]["extended"], 18)

    def test_pair_mismatch_and_escape_paths_are_p0(self):
        rows = self.records()
        rows[0]["agent_ids"] = ["a", "b"]
        with self.assertRaises(P0ContractError):
            make_views(rows)
        for path in ("../other", "C:/outside", "/outside", "a\\b"):
            with self.subTest(path=path), self.assertRaises(P0ContractError):
                make_views([{**self.records()[0], "path": path}])

    def test_pending_metrics_are_null_not_zero_success_rates(self):
        scene, family = fixture()
        descriptors = sample_family_descriptors((scene, family, 2))
        summary = diagnostic_summary(descriptors, requests_for(descriptors))
        self.assertIsNone(summary["execution_metrics"]["nondesigned_failure_fraction"])
        self.assertIsNone(summary["execution_metrics"]["timing_agreement_fraction"])
        self.assertEqual(summary["state_counts"], {"pending": 21})


if __name__ == "__main__":
    unittest.main()
