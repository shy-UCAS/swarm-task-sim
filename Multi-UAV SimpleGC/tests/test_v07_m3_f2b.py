"""F2b checks the constructed reserved ingress, without the excess 50 metres."""
from copy import deepcopy
import random
import unittest

import numpy as np

from test_v07_m3b_geometry import role_request
from task_v07.geometry import geometry_facts, offset_geometry
from task_v07.unified.spec import build_spec
from task_v07.unified.free_space import free_space
from task_v07.unified.route import line_interval, route_group
from task_v07.unified.construction import ingress_issues
from task_v07.unified.checks import formal_entry_segment, plan_checks

F2B_TEST_EVIDENCE = {}


def observation_case(obstacle_distance=None):
    scene, descriptor, group = role_request("close_observation", count=2)
    spec = build_spec(descriptor, group); initial_free = free_space(scene, spec)
    warning = offset_geometry(initial_free.target["geometry"], initial_free.offsets["warning"])
    station = offset_geometry(initial_free.target["geometry"], initial_free.offsets["alert"]+80.)
    direction = np.array([1., 0.]); slots = []
    for i, y in enumerate((-10., 10.)):
        origin = np.array([0., y])
        entry = origin+line_interval(warning, origin, direction)[0]*direction
        work = origin+line_interval(station, origin, direction)[0]*direction
        slots.append({"split_index": 0, "slot_id": f"0:{i}", "entry": entry.tolist(),
            "direction": direction.tolist(), "work": [work.tolist()], "exit_direction": (-direction).tolist(),
            "dwell_s": 50., "reference_fields": {"observation_point_enu_m": [*work.tolist(), 120.]}})
    if obstacle_distance is not None:
        # Its projection lies in the excess interval (110,160) for the A-1
        # case. The lateral displacement leaves the actual reserved line clear.
        scene["entities"].append({"id": "extra_ingress_blocker", "type": "hard_constraint_obstacle",
            "geometry": {"type": "Circle", "center_m": [slots[0]["entry"][0]-obstacle_distance, 30.], "radius_m": 5.}})
        # Approach from south of this obstacle; the finite exterior planner can
        # reach the reserved line without using the blocked extra extension.
        for i, state in enumerate(descriptor["family_conditions"]["initial_states"]):
            state["position_enu_m"] = [-1090.-20*i, -1500., 120.]
    free = free_space(scene, spec)
    shape = {"kind": "close_observation", "slots": slots, "draw": {"test_case": "F2b"}}
    return scene, descriptor, group, spec, free, shape


class F2bRegressionTests(unittest.TestCase):
    def test_A1_extra_fifty_metres_can_be_blocked_while_final_route_is_legal(self):
        scene, descriptor, group, spec, free, shape = observation_case(159.)
        self.assertEqual(ingress_issues(spec, free, shape["slots"]), [])
        old_issues = []
        for slot in shape["slots"]:
            gate = np.asarray(slot["entry"]); old_start = gate-160.*np.asarray(slot["direction"])
            old_issues.extend(free.segment_issues(old_start, gate))
        self.assertTrue(any(i.get("entity_id") == "extra_ingress_blocker" for i in old_issues))
        bundle, template = route_group(scene, spec, shape, free,
            descriptor["family_conditions"]["initial_states"], random.Random(4))
        result = plan_checks(scene, spec, bundle, template, free, descriptor["family_conditions"]["initial_states"])
        self.assertEqual(result["status"], "PASS", result["issues"])
        F2B_TEST_EVIDENCE["A1"] = {"old_excess_range_issues": old_issues, "new_ingress_issues": [],
            "obstacle": scene["entities"][-1], "half_width_m": 10., "obstacle_projection_before_gate_m": 159.,
            "waypoints_by_agent": bundle.waypoints_by_agent, "references": template["references"], "final_plan_checks": result}

    def test_A2_obstacle_in_required_ingress_is_still_rejected(self):
        _, _, _, spec, free, shape = observation_case(75.)
        issues = ingress_issues(spec, free, shape["slots"])
        self.assertTrue(any(i.get("entity_id") == "extra_ingress_blocker"
                            and i["phase"] == "ingress_line_outside_entry" for i in issues))
        F2B_TEST_EVIDENCE["A2"] = {"new_ingress_issues": issues}

    def test_A3_existing_route_and_ingress_constraints_are_preserved(self):
        scene, descriptor, group, spec, free, shape = observation_case()
        self.assertEqual(ingress_issues(spec, free, shape["slots"]), [])
        bundle, template = route_group(scene, spec, shape, free,
            descriptor["family_conditions"]["initial_states"], random.Random(1))
        baseline = plan_checks(scene, spec, bundle, template, free, descriptor["family_conditions"]["initial_states"])
        self.assertEqual(baseline["status"], "PASS", baseline["issues"])
        early = deepcopy(bundle); agent = group["members"][0]; original = early.waypoints_by_agent[agent]
        early.waypoints_by_agent[agent] = [original[0], [0., 600., 120.], original[0], *original[1:]]
        early_template = deepcopy(template)
        early_template["references"][agent]["intermediate_dwell"]["waypoint_index"] += 2
        early_check = plan_checks(scene, spec, early, early_template, free)
        early_codes = {i["code"] for i in early_check["issues"]}
        self.assertIn("warning_visit_count", early_codes)
        self.assertIn("pre_entry_warning_clearance", early_codes)

        short = deepcopy(bundle); points = np.asarray(short.waypoints_by_agent[agent])
        reference = template["references"][agent]; index = formal_entry_segment(points[:, :2], reference)
        self.assertGreater(index, 0)
        gate = np.asarray(reference["warning_entry_enu_m"])
        points[index, :2] = gate[:2]-90.*np.asarray(reference["ingress_direction"])
        short.waypoints_by_agent[agent] = points.tolist()
        short_check = plan_checks(scene, spec, short, template, free)
        lengths = [i["measured_m"] for i in short_check["issues"] if i["code"] == "alignment_length"]
        self.assertTrue(lengths)
        self.assertAlmostEqual(lengths[0], 90., places=6)

        forbidden = deepcopy(shape["slots"])
        forbidden[0]["work"] = [[0., 0.]]
        forbidden_issues = ingress_issues(spec, free, forbidden)
        self.assertTrue(any(i["phase"] == "entry_to_work_start" and i.get("entity_id") == "F1_alert"
                            for i in forbidden_issues))
        F2B_TEST_EVIDENCE["A3"] = {"normal_plan_checks": baseline,
            "early_visit_plan_checks": early_check, "short_alignment_plan_checks": short_check,
            "forbidden_entry_to_work_issues": forbidden_issues}


if __name__ == "__main__":
    unittest.main()
