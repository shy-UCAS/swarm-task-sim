"""Only the selected patrol entrance must be usable; the full work loop stays clear."""
from copy import deepcopy
import random
import unittest

import numpy as np

from test_v07_m3b_geometry import role_request
from task_v07.geometry import offset_geometry
from task_v07.unified.spec import build_spec
from task_v07.unified.free_space import free_space
from task_v07.unified.route import line_interval
from task_v07.unified.construction import ingress_issues
from task_v07.unified.patrol_shape import common_arcs, patrol_shape


class PatrolEntryRegressionTests(unittest.TestCase):
    def test_F2_blocked_unused_entrance_does_not_reject_clear_full_patrol(self):
        scene, descriptor, group = role_request("monitoring", count=2)
        # Both directions of the north-side tangent entrance are blocked far
        # outside the patrol lines. The selected east-side entrance is clear.
        for index, x in enumerate((-900., 900.)):
            scene["entities"].append({"id": f"unused_entry_blocker_{index}", "type": "hard_constraint_obstacle",
                "geometry": {"type": "Circle", "center_m": [x, 530.], "radius_m": 70.}})
        spec = build_spec(descriptor, group); free = free_space(scene, spec)
        shape = patrol_shape(spec, free, random.Random(4), {"direction_deg": 0.}, force_form="full")
        self.assertEqual(shape["draw"]["patrol_form"], "full")
        self.assertEqual(shape["draw"]["accepted_start_direction_deg"], 0.)
        self.assertTrue(common_arcs(spec, free, shape["draw"]["member_offsets_by_split_m"])[1])
        self.assertEqual(ingress_issues(spec, free, shape["slots"]), [])
        for slot in shape["slots"]:
            self.assertFalse([issue for a, b in zip(slot["work"], slot["work"][1:])
                              for issue in free.segment_issues(a, b)])

        warning = offset_geometry(free.target["geometry"], free.offsets["warning"])
        north_slots = deepcopy(shape["slots"])
        rotation = np.array([[0., -1.], [1., 0.]])
        for slot in north_slots:
            point = rotation @ np.asarray(slot["work"][0])
            heading = rotation @ np.asarray(slot["direction"])
            hit = line_interval(warning, point, heading)
            slot.update(entry=(point+hit[0]*heading).tolist(), direction=heading.tolist(), work=[point.tolist()])
        issues = ingress_issues(spec, free, north_slots)
        self.assertTrue(issues)
        self.assertTrue(any(issue.get("entity_id", "").startswith("unused_entry_blocker_") for issue in issues))


if __name__ == "__main__":
    unittest.main()
