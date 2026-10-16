"""Deterministic construction regressions; no simulator or threshold changes."""
from copy import deepcopy
import random
import unittest
from unittest.mock import patch
import numpy as np
from test_v07_m3b_geometry import role_request
from task_v07.unified.spec import build_spec
from task_v07.unified.free_space import free_space, work_region
from task_v07.unified.route import GeometryRejected
from task_v07.unified.construction import ingress_issues, retreat_endpoint, precheck_operation
from task_v07.unified.operation_shapes import draw_operation


class ShapeConnectionRegressionTests(unittest.TestCase):
    def fixture(self):
        scene,d,g=role_request("close_observation",count=2)
        spec=build_spec(d,g); free=free_space(scene,spec)
        return spec,free

    def test_F2_whole_ingress_checked_on_both_sides_of_gate(self):
        spec,free=self.fixture()
        slot={"split_index":0,"slot_id":"0:0","entry":[0.,0.],"direction":[1.,0.],"work":[[200.,0.]]}
        with patch.object(free,"segment_issues",side_effect=[[],[{"code":"constraint_clearance","entity_id":"neighbor_alert"}]]) as check:
            issues=ingress_issues(spec,free,[slot])
        np.testing.assert_array_equal(check.call_args_list[0].args[0],[-150.,0.])
        np.testing.assert_array_equal(check.call_args_list[1].args[1],[200.,0.])
        self.assertEqual(issues[0]["phase"],"entry_to_work_start")

    def test_F2_neighbor_warning_rejects_radial_endpoint_during_shape_precheck(self):
        spec,free=self.fixture()
        free.target["geometry"]={"type":"Circle","center_m":[0.,0.],"radius_m":10.}
        free.offsets["warning"]=100.
        free.warning_geometries={"target":{"type":"Circle","center_m":[0.,0.],"radius_m":110.},
            "neighbor":{"type":"Circle","center_m":[160.,0.],"radius_m":200.}}
        slot={"split_index":0,"slot_id":"0:0","entry":[110.,0.],"direction":[-1.,0.],"work":[[90.,0.]],"exit_direction":[1.,0.]}
        free.cfg["retreat_clearance_max_m"]=50.
        with patch.object(free,"point_valid",return_value=True),patch.object(free,"segment_issues",return_value=[]):
            with self.assertRaisesRegex(GeometryRejected,"retreat_endpoint_invalid"):
                precheck_operation(spec,free,{"slots":[slot],"draw":{}},random.Random(3))

    def test_F2_precheck_does_not_consume_connection_random_draws(self):
        spec,free=self.fixture(); rng=random.Random(13)
        slot={"split_index":0,"slot_id":"0:0","entry":[0.,0.],"direction":[1.,0.],"work":[[200.,0.]],"exit_direction":[1.,0.]}
        shape={"slots":[slot],"draw":{}}; before=rng.getstate()
        with patch("task_v07.unified.construction.ingress_issues",return_value=[]),patch("task_v07.unified.construction.retreat_endpoint",return_value=(None,{"valid":True})):
            precheck_operation(spec,free,shape,rng)
        self.assertEqual(before,rng.getstate())
        preview=deepcopy(rng); preview.uniform(*free.cfg["collection_clearance_m"])
        self.assertEqual(shape["draw"]["connection_precheck"]["retreat_clearance_m"],preview.uniform(50.,free.cfg["retreat_clearance_max_m"]))

    def test_F2_rejected_ingress_stays_in_twenty_shape_attempt_budget(self):
        spec,free=self.fixture()
        fake={"kind":"close_observation","draw":{},"slots":[]}
        with patch("task_v07.unified.operation_shapes.observation_shape",return_value=fake),patch("task_v07.unified.construction.precheck_operation",side_effect=GeometryRejected("ingress_line_blocked")) as check:
            with self.assertRaisesRegex(GeometryRejected,"shape_search_budget_exhausted") as result:
                draw_operation(spec,work_region({},spec,free),random.Random(3),free)
        self.assertEqual(check.call_count,20)
        self.assertEqual({r["reason"] for r in result.exception.evidence},{"ingress_line_blocked"})


if __name__ == "__main__": unittest.main()
