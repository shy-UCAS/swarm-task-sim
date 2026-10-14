"""Annular survey scale, exact clipping, withdrawal evidence and runtime budget."""
from copy import deepcopy
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np

from scene_v07 import sample_family, canonical_json
from task_v07.geometry import geometry_facts, offset_geometry
from task_v07.planning import build_skeleton, scene_parts
from task_v07.survey import sector_area, sector_clear, survey_grid
from task_v07.execution import completion_budget, execute
from task_v07.labels import measure
from task_v07.io import save_json, write_csv
from scripts.audit_v07_s2_exact import audit_episode
from test_v07_s2 import fixture


def circular_sector():
    return {"type":"ContourAnnularSector","base_geometry":{"type":"Circle","center_m":[2000,2000],"radius_m":20},
            "center_m":[2000,2000],"inner_offset_m":315,"outer_offset_m":645,
            "start_angle_rad":-.5,"angle_span_rad":1.0,"bounding_radius_m":665}


def scanned_fixture():
    scene,sk,_=fixture()
    sk.update(base_intent="reconnaissance",role="reconnaissance",execution_method="annular_sector_lawnmower",
              members=["a"],agent_ids=["a"])
    region=circular_sector()
    sk["survey"]={"geometry":region,"bounds_m":[1335,1335,2665,2665],"model":"disk","assumptions":"test",
                  "grid_spacing_m":20,"footprint_radius_m":50,"required_group_coverage":.9,
                  "effective_speed_min_m_s":.5,"lane_endpoint_radius_m":5}
    points=[[2420,1960],[2460,1960],[2460,2000],[2420,2000],[2420,2040],[2460,2040]]
    sk["references"]={"a":{"endpoint_enu_m":[2900,2040,100],"scan_geometry":region,
                          "scan_lane_endpoints_m":points,"scan_strip_count":3,
                          "retreat_required":True,"retreat_warning_clearance_m":200}}
    t=np.arange(101,dtype=np.int64)*100000
    p=np.zeros((101,1,3));p[:,:,2]=100;p[:,:,:2]=[2400,1920]
    v=np.zeros_like(p)
    for j,point in enumerate(points):
        p[10+j*10:20+j*10,0,:2]=point
    v[10:70,0,0]=1
    p[70:,0]=sk["references"]["a"]["endpoint_enu_m"]
    run={"agent_ids":["a"],"time_us":t,"p":p,"v":v,"execution_status":"completed","end_us":10100000}
    return scene,sk,run


class SectorGeometryTests(unittest.TestCase):
    def test_circle_sector_exact_area_and_micro_boundaries(self):
        sector=circular_sector()
        expected=(665**2-335**2)/2
        self.assertAlmostEqual(sector_area(sector),expected,places=6)
        for radius in (335,665):
            for epsilon in (-1e-6,1e-6):
                point=np.array([2000+radius+epsilon,2000])
                expected_inside=(radius==335 and epsilon>0) or (radius==665 and epsilon<0)
                self.assertEqual(bool(geometry_facts(sector,point)["inside"]),expected_inside)

    def test_analytic_offset_polygon_line_endpoints(self):
        polygon={"type":"BufferedPolygon","vertices_m":[[-10,-20],[10,-20],[10,20],[-10,20]],"buffer_m":5}
        for reverse in (False,True):
            g={**polygon,"vertices_m":polygon["vertices_m"][::-1] if reverse else polygon["vertices_m"]}
            interval=geometry_facts(g,[0,23],line_direction=[1,0])["line_intervals_m"]
            np.testing.assert_allclose(interval,[[-14,14]],atol=1e-10)
            for endpoint,sign in ((-14,-1),(14,1)):
                self.assertFalse(geometry_facts(g,[endpoint+sign*1e-6,23])["inside"])
                self.assertTrue(geometry_facts(g,[endpoint-sign*1e-6,23])["inside"])

    def test_sector_line_is_clipped_to_outer_inner_and_angle(self):
        sector=circular_sector()
        intervals=geometry_facts(sector,[2000,2000],line_direction=[1,0])["line_intervals_m"]
        np.testing.assert_allclose(intervals,[[335,665]],atol=1e-9)
        points=np.array([[2000+x,2000] for x in [334,336,664,666]])
        np.testing.assert_array_equal(geometry_facts(sector,points)["inside"],[False,True,True,False])

    def test_clearance_proof_rejects_obstacle_inside_sector(self):
        scene,_,_=fixture();sector=circular_sector()
        self.assertTrue(sector_clear(scene,sector,"f",35))
        scene["entities"].append({"type":"hard_constraint_obstacle","geometry":{"type":"Circle","center_m":[2450,2000],"radius_m":30}})
        self.assertFalse(sector_clear(scene,sector,"f",35))

    def test_two_maps_survey_scale_pitch_grid_and_exact_withdrawal(self):
        for seed in (int("f8174c26e85978ef",16),int("b0c036776dcaff71",16)):
            scene,family=sample_family(seed,revision="s1.2");original=canonical_json(scene)
            sk=build_skeleton(scene,family,"reconnaissance",1,"facility_01")
            survey=sk["survey"];base,zones=scene_parts(scene,"facility_01")
            self.assertTrue(200000<=survey["area_m2"]<=600000)
            self.assertTrue(30<=survey["angle_span_deg"]<=90)
            self.assertAlmostEqual(survey["footprint_radius_m"],.5*family["task_altitude_m"])
            self.assertAlmostEqual(survey["strip_spacing_m"],2*survey["footprint_radius_m"]*.8)
            self.assertGreaterEqual(survey["strip_count"],4)
            grid=survey_grid(survey);self.assertGreater(len(grid),1000)
            distances=geometry_facts(base["geometry"],grid)["signed_distance_m"]
            self.assertGreaterEqual(distances.min(),zones["alert"]["offset_m"]+35)
            self.assertLessEqual(distances.max(),zones["warning"]["offset_m"]-35)
            self.assertEqual(sum(r["scan_strip_count"] for r in sk["references"].values()),survey["strip_count"])
            for reference in sk["references"].values():
                clearance=geometry_facts(zones["warning"]["geometry"],reference["endpoint_enu_m"][:2])["signed_distance_m"]
                self.assertAlmostEqual(float(clearance),200,places=6)
                self.assertGreaterEqual(np.linalg.norm(np.diff(reference["points_enu_m"],axis=0),axis=1).min(),1)
                for point in reference["scan_lane_endpoints_m"]:
                    self.assertTrue(geometry_facts(reference["scan_geometry"],point)["inside"])
            self.assertEqual(canonical_json(scene),original)
            self.assertEqual(canonical_json(sk),canonical_json(build_skeleton(scene,family,"reconnaissance",1,"facility_01")))


class SurveyEvidenceAndRuntimeTests(unittest.TestCase):
    def test_variable_lane_count_scan_duration_and_retreat_prefix(self):
        scene,sk,run=scanned_fixture()
        full,_=measure(scene,sk,run,"synchronous")
        agent=full["agents"]["a"]
        self.assertTrue(agent["observed"]["contribution"]["scan_pattern_observed"])
        self.assertEqual(agent["observed"]["contribution"]["expected_lane_endpoint_count"],6)
        self.assertEqual(agent["observed"]["contribution"]["scan_segment_duration_s"],5.)
        self.assertEqual(agent["observed"]["retreat_event"]["t_s"],7.)
        self.assertTrue(agent["result"]["conditions"]["reached_retreat_point"])
        self.assertGreaterEqual(agent["observed"]["endpoint_hold_s"],2.)
        prefix,_=measure(scene,sk,run,"synchronous",cutoff_s=6.5)
        self.assertIsNone(prefix["agents"]["a"]["observed"]["retreat_event"]["t_s"])
        self.assertIsNone(prefix["agents"]["a"]["result"]["conditions"]["reached_retreat_point"])

    def test_scan_finished_without_withdrawal_is_role_failure(self):
        scene,sk,run=scanned_fixture()
        run["p"][70:,0,:2]=[2460,2040]
        labels,_=measure(scene,sk,run,"synchronous")
        agent=labels["agents"]["a"]
        self.assertTrue(agent["observed"]["contribution"]["scan_pattern_observed"])
        self.assertFalse(agent["result"]["conditions"]["reached_retreat_point"])
        self.assertEqual(agent["result"]["status"],"failure")

    def test_independent_audit_detects_corrupt_retreat_event(self):
        scene,sk,run=scanned_fixture()
        sk.update(members=["a","b"],agent_ids=["a","b"])
        reference=deepcopy(sk["references"]["a"])
        reference["endpoint_enu_m"][1]+=15
        reference["scan_lane_endpoints_m"]=[[x,y+15] for x,y in reference["scan_lane_endpoints_m"]]
        sk["references"]["b"]=reference
        run["agent_ids"]=["a","b"]
        run["p"]=np.concatenate((run["p"],run["p"]+np.array([0,15,0])),axis=1)
        run["v"]=np.repeat(run["v"],2,axis=1)
        labels,frame=measure(scene,sk,run,"synchronous")
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name,value in (("public_scene",scene),("task",sk),("labels",labels)):
                save_json(root/(name+".json"),value)
            np.savez(root/"truth_10hz.npz",agent_ids=run["agent_ids"],time_us=run["time_us"],p=run["p"],v=run["v"])
            write_csv(root/"truth.csv",run["agent_ids"],run["time_us"],run["p"],run["v"])
            np.savez(root/"frame_labels.npz",**frame)
            self.assertEqual(audit_episode(root)["status"],"PASS")
            labels["agents"]["a"]["observed"]["retreat_event"]["t_s"]+=.1
            import json
            (root/"labels.json").write_text(json.dumps(labels),encoding="utf-8")
            report=audit_episode(root)
            self.assertEqual(report["status"],"P0_STOP")
            self.assertTrue(any(e.get("field")=="retreat_event" for e in report["event_or_metric_witnesses"]))

    def test_budget_uses_full_measured_finish_plus_delay(self):
        _,sk,_=fixture()
        budget=completion_budget(sk,dict(zip("abcd",[0,10,20,90])),dict(zip("abcd",[300,320,350,720])))
        self.assertEqual(budget["latest_planned_completion_s"],810)
        self.assertEqual(budget["margin_s"],162)
        self.assertEqual(budget["max_duration_s"],972)
        self.assertEqual(completion_budget(sk,{a:0 for a in "abcd"},{a:100 for a in "abcd"})["max_duration_s"],220)
        with self.assertRaises(ValueError):
            completion_budget(sk,{"a":0},{"a":None})

    def test_frozen_plant_can_complete_after_old_600_second_limit(self):
        sk={"agent_ids":["a"],"initial_states":[{"agent_id":"a","position_enu_m":[0,0,100],
            "velocity_enu_m_s":[0,0,0],"acceleration_enu_m_s2":[0,0,0]}],
            "references":{"a":{"points_enu_m":[[0,0,100],[5,0,100]]}},"cruise_speed_m_s":4,
            "initial_settle_s":1,"terminal_radius_m":1,"terminal_speed_m_s":.15,"terminal_hold_s":2}
        run=execute(sk,{"a":605})
        self.assertEqual(run["execution_status"],"completed")
        self.assertGreater(run["time_us"][-1]/1e6,600)
        self.assertLess(run["time_us"][-1]/1e6,run["time_budget"]["max_duration_s"])


if __name__=="__main__":
    unittest.main()
