"""FE-P1 shared-tail retreat, outward fallback and endpoint spacing regressions."""
from collections import defaultdict
from copy import deepcopy
from itertools import combinations
import random
import unittest
from unittest.mock import patch
import numpy as np

from test_v07_m3b_geometry import role_request
from task_v07.unified.spec import build_spec
from task_v07.unified.free_space import free_space, work_region
from task_v07.unified.shapes import draw_shape
from task_v07.unified.route import route_group, GeometryRejected
from task_v07.unified.checks import plan_checks
from task_v07.unified.patrol_shape import patrol_shape
from task_v07.unified.construction import retreat_endpoint


class MonitoringRetreatTests(unittest.TestCase):
    def check_patrol(self, form, multi=False, count=3, traversals=None):
        scene, descriptor, group = role_request("monitoring", multi=multi, count=count)
        spec = build_spec(descriptor, group)
        if traversals is not None:
            spec["params"]["traversals"] = [traversals]
        free = free_space(scene, spec)
        try:
            shape = patrol_shape(spec, free, random.Random(4), {"direction_deg": 37.}, force_form=form)
        except GeometryRejected as exc:
            if form == "arc" and exc.reason == "patrol_arc_too_short" and not multi:
                return self.check_patrol(form, multi=True, count=4, traversals=traversals)
            raise
        stocks = defaultdict(list)
        for slot in shape["slots"]:
            stocks[slot["split_index"]].append(slot)
        for slots in stocks.values():
            first = next(slot for slot in slots if slot["slot_id"].endswith(":0"))
            work = np.asarray(first["work"])
            tail = work[-1]-work[-2]
            expected = tail/np.linalg.norm(tail)
            ends, evidences = [], []
            for slot in slots:
                np.testing.assert_array_equal(slot["exit_direction"], first["exit_direction"])
                np.testing.assert_allclose(slot["exit_direction"], expected, atol=1e-12, rtol=0)
                self.assertGreaterEqual(float(np.dot(slot["exit_direction"], slot["exit_outward_normal"])), -1e-9)
                end, evidence = retreat_endpoint(free, slot, 100.)
                ends.append(end)
                evidences.append(evidence)
            for a, b in combinations(ends, 2):
                self.assertGreaterEqual(float(np.linalg.norm(a-b)), 2.)
                if all(e["rotation_deg"] == 0 for e in evidences):
                    self.assertGreaterEqual(float(np.linalg.norm(a-b)), .99*spec["family"]["lateral_spacing_m"])

    def test_T1_full_single_stock_three_lanes(self):
        self.check_patrol("full")

    def test_T2_arc_even_and_odd_reversals(self):
        for traversals in (2, 3):
            with self.subTest(traversals=traversals):
                self.check_patrol("arc", traversals=traversals)

    def test_T3_full_multiple_stocks(self):
        self.check_patrol("full", multi=True, count=4)

    def test_T4_terminal_spacing_one_metre_reject_two_metres_accept(self):
        scene, descriptor, group = role_request("feint", count=2)
        spec = build_spec(descriptor, group)
        free = free_space(scene, spec)
        rng = random.Random(3)
        initial = descriptor["family_conditions"]["initial_states"]
        shape = draw_shape(spec, work_region(scene, spec, free), rng, free)
        bundle, template = route_group(scene, spec, shape, free, initial, rng)
        baseline = plan_checks(scene, spec, bundle, template, free, initial)
        self.assertEqual(baseline["status"], "PASS", baseline["issues"])
        a, b = sorted(spec["members"])
        for distance in (1., 2.):
            with self.subTest(distance=distance):
                changed_bundle, changed_template = deepcopy(bundle), deepcopy(template)
                endpoint = (np.asarray(template["references"][a]["endpoint_enu_m"])+[distance, 0., 0.]).tolist()
                changed_bundle.waypoints_by_agent[b][-1] = endpoint
                changed_template["references"][b]["endpoint_enu_m"] = endpoint
                check = plan_checks(scene, spec, changed_bundle, changed_template, free, initial)
                issues = [i for i in check["issues"] if i["code"] == "terminal_endpoint_spacing"]
                self.assertEqual(bool(issues), distance < 2.)
                if issues:
                    self.assertEqual(issues[0]["required_m"], 2.)
                    self.assertAlmostEqual(issues[0]["measured_m"], distance)

    def test_inward_fallback_is_skipped_only_with_outward_reference(self):
        scene, descriptor, group = role_request("monitoring", count=3)
        free = free_space(scene, build_spec(descriptor, group))
        slot = {"slot_id": "0:0", "work": [[0., 0.]], "exit_direction": [1., 0.],
                "exit_outward_normal": [0., 1.]}
        # All geometrically tried rays fail: verify the attempted directions,
        # including the zero-dot tangent, and the recorded inward skips.
        for monitoring in (True, False):
            candidate = deepcopy(slot)
            if not monitoring:
                candidate.pop("exit_outward_normal")
            with patch("task_v07.unified.construction.line_interval", return_value=None) as ray:
                with self.assertRaises(GeometryRejected) as raised:
                    retreat_endpoint(free, candidate, 100.)
                directions = [call.args[2] for call in ray.call_args_list]
                self.assertEqual(len(directions), 4 if monitoring else 7)
                if monitoring:
                    self.assertTrue(all(direction[1] >= -1e-9 for direction in directions))
                self.assertEqual(raised.exception.reason, "retreat_endpoint_invalid")
                skipped = [e["rotation_deg"] for e in raised.exception.evidence
                           if e.get("reason") == "inward_rotation_skipped"]
                self.assertEqual(skipped, [-30., -60., -90.] if monitoring else [])

    def test_degenerate_tail_rejected_before_indexing(self):
        scene, descriptor, group = role_request("monitoring", count=3)
        spec = build_spec(descriptor, group)
        free = free_space(scene, spec)
        for path in ([np.array([100., 0.])], [np.array([100., 0.]), np.array([100., 0.])]):
            with self.subTest(points=len(path)):
                with patch("task_v07.unified.patrol_shape.parallel_paths",
                           return_value=([path]*3, np.array([1., 0.]), np.array([1., 0.]))):
                    with self.assertRaisesRegex(GeometryRejected, "patrol_tail_undefined"):
                        patrol_shape(spec, free, random.Random(4), {"direction_deg": 37.}, force_form="full")


if __name__ == "__main__":
    unittest.main()
