"""Deterministic regressions for the approved pre-entry construction repairs."""
import random
import unittest

import numpy as np

from v07_m3_fixtures import request
from task_v07.geometry import geometry_facts, offset_geometry
from task_v07.unified.spec import build_spec
from task_v07.unified.free_space import free_space
from task_v07.unified.route import line_interval, route_group
from task_v07.unified.checks import formal_entry_segment, plan_checks, warning_visits


class EntryRepairTests(unittest.TestCase):
    def test_F1_exterior_detour_has_ten_metre_clearance_and_one_visit(self):
        scene, descriptor, group = request(count=2)
        spec = build_spec(descriptor, group); free = free_space(scene, spec)
        warning = offset_geometry(free.target["geometry"], free.offsets["warning"])
        # Start west of the facility, but enter from its east side: the
        # exterior connection must go around the target warning contour.
        heading = np.array([-1., 0.]); slots = []
        for i in range(2):
            origin = np.array([0., 600.+20*i])
            low, high = line_interval(warning, origin, heading)
            entry, finish = origin+low*heading, origin+high*heading
            slots.append({"split_index": 0, "slot_id": f"0:{i}", "direction": heading.tolist(),
                "entry": entry.tolist(), "work": [entry.tolist(), finish.tolist()],
                "exit_direction": heading.tolist()})
        bundle, template = route_group(scene, spec, {"slots": slots, "draw": {}}, free,
            descriptor["family_conditions"]["initial_states"], random.Random(73))
        points = np.asarray(bundle.waypoints_by_agent["a0"])[:, :2]
        boundary_segment = formal_entry_segment(points, template["references"]["a0"])
        self.assertGreater(boundary_segment, 1)
        self.assertEqual(len(warning_visits(points, warning)[0]), 1)
        for a, b in zip(points[:boundary_segment], points[1:boundary_segment+1]):
            self.assertGreaterEqual(geometry_facts(warning, np.asarray([a, b]), footprint=True)["clearance_m"], 10.-1e-6)
        check = plan_checks(scene, spec, bundle, template, free,
                            descriptor["family_conditions"]["initial_states"])
        self.assertEqual(check["status"], "PASS", check["issues"])

    def test_F1_formal_entry_uses_anchor_even_after_an_earlier_visit(self):
        points = np.array([[-20., 0.], [0., 0.], [-20., 0.], [-20., 20.], [20., 20.], [20., 0.], [0., 0.]])
        warning = {"type": "Circle", "center_m": [0., 0.], "radius_m": 10.}
        visits, first = warning_visits(points, warning)
        self.assertEqual(len(visits), 2)
        self.assertEqual(first["segment"], 0)
        reference = {"warning_entry_enu_m": [10., 0., 120.], "ingress_direction": [-1., 0.]}
        self.assertEqual(formal_entry_segment(points, reference), 5)

    def test_F1_missing_anchor_cannot_bypass_production_check(self):
        scene, descriptor, group = request(count=2)
        spec = build_spec(descriptor, group)
        from task_v07.expansion.contracts import RouteBundle
        route = [[-1500., 600., 120.], [1500., 600., 120.]]
        bundle = RouteBundle({a: route for a in group["members"]}, {a: 0. for a in group["members"]})
        result = plan_checks(scene, spec, bundle,
            {"references": {a: {"endpoint_enu_m": route[-1], "split_index": 0} for a in group["members"]}})
        self.assertIn("formal_warning_entry_missing", {issue["code"] for issue in result["issues"]})


if __name__ == "__main__":
    unittest.main()
