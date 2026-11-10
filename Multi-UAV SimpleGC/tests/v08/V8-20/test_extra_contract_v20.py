"""Independent event, frozen restricted-mask, ownership and deep-schema checks."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np

from task_v07 import detectors
from v08.motion.area_search_checks import screen_area_search
from v08.runner.area_search_report import _formed_survey,quick_checkpoint
from v08.runner.area_search_serialization import assert_contract_payload,project,PROPOSAL_SCHEMA,WITNESSES_SCHEMA
from test_preset_local_geometry_v20 import fixture


class ContractChecks(unittest.TestCase):
    def test_exit_is_first_false_frame_after_entry(self):
        scene,facilities=fixture()
        xy=np.array([[250.,0.],[150.,0.],[150.,0.],[250.,0.]])
        sample={"time_us":np.arange(4,dtype=np.int64)*100000,"p":np.c_[xy,np.full(4,100.)],
                "v":np.tile([1.,0.,0.],(4,1))}
        survey={"geometry":{"type":"Circle","center_m":[0.,0.],"radius_m":300.},
                "bounds_m":[-300.,-300.,300.,300.],"footprint_radius_m":50.,"grid_spacing_m":25.}
        result=screen_area_search(scene,facilities,"f",{"m":sample},survey)
        facts=result["member_facts"]["m"]
        self.assertEqual(facts["visits"],1)
        self.assertEqual(facts["first_warning_entry_us"],100000)
        self.assertEqual(facts["first_warning_exit_us"],300000)
        self.assertTrue(all(type(v) is bool for v in result["member_conditions"]["m"].values()))

    def test_coverage_restricted_is_obstacles_only(self):
        scene,facilities=fixture()
        scene["world"]["geometry"]={"type":"Circle","center_m":[0.,0.],"radius_m":1.}
        sample={"time_us":np.array([0],dtype=np.int64),"p":np.array([[100.,0.,100.]]),"v":np.array([[1.,0.,0.]])}
        survey={"geometry":{"type":"Circle","center_m":[0.,0.],"radius_m":200.},
                "bounds_m":[-200.,-200.,200.,200.],"footprint_radius_m":50.,"grid_spacing_m":25.}
        with patch.object(detectors,"coverage",wraps=detectors.coverage) as frozen:
            result=screen_area_search(scene,facilities,"f",{"m":sample},survey)
        self.assertEqual(frozen.call_count,1)
        np.testing.assert_array_equal(frozen.call_args.args[3],[False])
        self.assertEqual(result["member_facts"]["m"]["effective_frame_count"],1)

    def test_deep_unknown_fields_and_data_dictionaries_rejected(self):
        with self.assertRaises(ValueError):
            project({"speed_events":{"times_s":[],"speeds_m_s":[],"cache_hits":0}},PROPOSAL_SCHEMA,"p")
        with self.assertRaises(ValueError):
            project({"independent_members":{"m":{"primitives":{"arbitrary":[]}}}},WITNESSES_SCHEMA,"w")
        with self.assertRaises(ValueError):
            project({"bone_nominal_screen":{"group_facts":{"coverage_fraction":1.,"wall_s":1.}}},WITNESSES_SCHEMA,"w")
        with self.assertRaises(ValueError):
            assert_contract_payload({"contract_id":"x","intent":"area_search","member_ids":[],"survey":None,"survey_attempt":3})
        with self.assertRaises(ValueError):
            project({"independent_members":{"../bad":{"curve_s":[]}}},WITNESSES_SCHEMA,"w")

    def test_optimizer_turn_table_is_required_and_four_element(self):
        for turns in (None,[["m",1.,2.]],[["m",2.,1.,15.]]):
            with self.assertRaises(ValueError):
                assert_contract_payload({"members":{},"lines":[],"diagnostics":{},"turns":turns})

    def test_last_formed_survey_ownership_survives_later_early_failures(self):
        a,b={"tag":"attempt0"},{"tag":"attempt2"}
        records=[{"plan":NS(witnesses={"survey":a})},{"plan":NS(witnesses=None)},
                 {"plan":NS(witnesses={"survey":b})},{"plan":NS(witnesses={})}]
        self.assertEqual(_formed_survey(records),(b,2))
        self.assertEqual(_formed_survey([{"plan":NS(witnesses=None)}]),(None,None))

    def test_failed_contract_is_not_a_retained_p0(self):
        rows=[{"contract_id":"failed","success":False,"attempts":20,"optimization_s":0.,"retained_p0_ok":False,
               "skeleton_failures":20,"post_optimization_failures":0}]
        result=quick_checkpoint(rows)
        self.assertEqual(result["metrics"]["contracts"],1)
        self.assertIn("success_rate",result["triggered"])
        self.assertNotIn("retained_p0",result["triggered"])
        self.assertEqual(result["metrics"]["retained_p0_violations"],[])


if __name__=="__main__":
    unittest.main()
