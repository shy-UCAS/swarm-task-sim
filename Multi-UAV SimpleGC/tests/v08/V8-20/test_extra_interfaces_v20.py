"""Part-2 independent oracles; no production candidate generation."""
import copy
import math
import unittest
from dataclasses import fields, FrozenInstanceError, replace
from types import SimpleNamespace as NS

import numpy as np

from v08.contract.monitoring import TaskSpec, MemberPlan, SegmentPlan, family_from_initial
from v08.contract.single_intent import AreaSearchTaskSpec, area_search_mission, mission_for_intent
from v08.motion import intent_dispatch as D
from v08.motion.area_search_reference import references_area_search
from v08.motion.intents import monitoring, transit, intrusion, feint, close_observation, area_search
from v08.motion.nominal import member_nominal
from v08.motion.skeleton import references_from_skeleton, reference_guidance, NominalPVA
from v08.motion.optimize import turns_from_skeleton
from v08.runner.area_search_serialization import task_record, validate_survey
from v08.sampler.common import sample_common


def survey():
    area = (500.**2-300.**2)*math.pi/12
    return {"geometry":{"type":"ContourAnnularSector","base_geometry":{"type":"Circle","center_m":[0.,0.],"radius_m":100.},
        "center_m":[0.,0.],"inner_offset_m":200.,"outer_offset_m":400.,"start_angle_rad":-math.pi/12,
        "angle_span_rad":math.pi/6,"bounding_radius_m":500.},"bounds_m":[-500.,-500.,500.,500.],
        "footprint_radius_m":50.,"grid_spacing_m":min(25.,math.sqrt(area)/50),"strip_count":4,"strips_per_member":2,"area_m2":area}


class InterfaceTests(unittest.TestCase):
    def test_task_subclass_and_old_exact_field_order(self):
        names = [f.name for f in fields(TaskSpec)]
        self.assertEqual(names,["task_id","intent","target_id","switch_mode","final"])
        self.assertEqual([f.name for f in fields(AreaSearchTaskSpec)],names+["survey"])
        task = AreaSearchTaskSpec("t","area_search","f",survey=survey())
        with self.assertRaises(FrozenInstanceError):
            task.survey = None
        for intent in ("monitoring","transit","intrusion","feint","close_observation"):
            self.assertEqual(list(task_record(TaskSpec("t",intent,"f"))),names)
            with self.assertRaises(ValueError):
                task_record(replace(task,intent=intent))
        base = AreaSearchTaskSpec("t","area_search","f")
        candidate = replace(base,survey=survey())
        self.assertIsNone(base.survey)
        self.assertEqual(task_record(candidate)["survey"],survey())
        self.assertNotIn("survey",task_record(base))

    def test_public_mission_preserves_every_old_field(self):
        family = family_from_initial("fixture",{"vehicle_count":2,"task_altitude_m":100.,"lateral_spacing_m":24.,
            "initial_states":[{"agent_id":"a","position_enu_m":[-900.,-50.,100.]},{"agent_id":"b","position_enu_m":[-900.,50.,100.]}]})
        ctx = NS(family=family,facilities=[NS(id="f"),NS(id="g")],inputs={})
        common = sample_common(family,0)
        old = mission_for_intent(ctx,common,"monitoring")
        new = area_search_mission(ctx,common)
        self.assertEqual(old.common,new.common)
        self.assertEqual(old.groups,new.groups)
        self.assertEqual(old.business_key,new.business_key)
        self.assertEqual(old.policy_version,new.policy_version)
        self.assertEqual(old.tasks[0].target_id,new.tasks[0].target_id)
        self.assertIsNone(new.tasks[0].survey)

    def test_nested_survey_unknown_fields_rejected(self):
        for loc in ((),("geometry",),("geometry","base_geometry")):
            for key in ("wall_s","path","cache_hits","unknown"):
                s = survey()
                current = s
                for name in loc:
                    current = current[name]
                current[key] = 1
                with self.assertRaises(ValueError):
                    validate_survey(s)

    def test_dispatch_old_callable_identity_and_group_screen(self):
        for intent,module in (("monitoring",monitoring),("transit",transit),("intrusion",intrusion),("feint",feint),("close_observation",close_observation)):
            self.assertIs(D.skeleton_builder(intent),module.propose_and_build)
        self.assertIs(D.skeleton_builder("area_search"),area_search.propose_and_build)
        from v08.motion.area_search_checks import screen_area_search
        self.assertIs(D.nominal_screen("area_search"),screen_area_search)
        with self.assertRaises(ValueError):
            area_search.propose_and_build(None,None,TaskSpec("t","transit","f"),None,None)

    def test_independent_references_original_curve_and_turn_mapping(self):
        xs = np.arange(0.,60.5,.5)
        curves = {"a":np.c_[xs[:81],np.zeros(81)],"b":np.c_[np.full(len(xs),10.),xs]}
        members,independent = {},{}
        for i,(mid,xy) in enumerate(curves.items()):
            length = float(np.linalg.norm(np.diff(xy,axis=0),axis=1).sum())
            members[mid] = MemberPlan(mid,0,tuple(map(tuple,xy)),100.,length,i*.3,((0.,4.),))
            independent[mid] = {"collect_s":5.,"split_s":10.,"scan_start_s":10.,"scan_end_s":length-10.,
                                "warning_entry_s":7.,"warning_exit_s":length-5.,"terminal_s":length}
        plan = SegmentPlan(members=members,reference_xy=(),nominal_duration_s=0.,anchors={},repairs=(),
                           witnesses={"intent":"area_search","independent_members":independent,"turn_ranges":{"a":[("u",5.,20.,"turn_u_min_m")]}})
        refs,lines,maps = references_from_skeleton(plan)
        self.assertEqual(len(refs),2)
        self.assertEqual(lines,())
        for ref in refs:
            expected = member_nominal(members[ref.member_id],guidance=reference_guidance())
            np.testing.assert_array_equal(maps[ref.member_id]["curve_s"],expected.curve.s)
            self.assertEqual(ref.end_s,ref.release_s+expected.travel_s)
            np.testing.assert_array_equal(NominalPVA(expected)(ref.release_s)[0],curves[ref.member_id][0])
            np.testing.assert_allclose(NominalPVA(expected)(ref.end_s)[0],curves[ref.member_id][-1],rtol=0.,atol=1e-9)
        mapped = turns_from_skeleton(plan,maps,{"turn_u_min_m":15.})
        nom = maps["a"]["nominal"]
        self.assertEqual(mapped,(("a",float(np.interp(5.,nom.curve.s,nom.t_nodes))+nom.release_s,
                                  float(np.interp(20.,nom.curve.s,nom.t_nodes))+nom.release_s,15.),))


if __name__ == "__main__":
    unittest.main()
