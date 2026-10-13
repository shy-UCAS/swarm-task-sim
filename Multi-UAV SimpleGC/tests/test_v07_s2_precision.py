"""Regression evidence for exact circle/convex-polygon semantics and timing v2."""
import ast
from copy import deepcopy
import json
import tempfile
from pathlib import Path
import unittest

import numpy as np

from task_v07.geometry import geometry_facts, radial_boundary_exact
from task_v07.execution import departure_delays
from task_v07.labels import measure
from task_v07.visibility import ExactVisibilityPlanner
from task_v07.io import save_json,write_csv
from scripts.audit_v07_s2_exact import audit_episode
from test_v07_s2 import fixture

ROOT=Path(__file__).resolve().parents[1]


class ExactGeometryTests(unittest.TestCase):
    def test_two_frozen_p0_witness_frames(self):
        data=json.loads((ROOT/"tests/fixtures/v07_boundary_witnesses.json").read_text(encoding="utf-8"))
        self.assertEqual([(w["t_s"],w["agent_id"]) for w in data["witnesses"]],
                         [(336.9,"uav_03"),(479.3,"uav_04")])
        for witness in data["witnesses"]:
            result=geometry_facts(data["facility"]["geometry"],witness["position_enu_m"][:2],
                                  layer_offsets=data["offsets_m"])
            self.assertEqual(int(result["layer"]),1)
            self.assertEqual(int(result["layer"]),witness["exact_region_code"])

    def test_circle_each_layer_one_micrometre_inside_outside(self):
        geometry={"type":"Circle","center_m":[1400,2200],"radius_m":50.}
        offsets={"protected":80.,"alert":240.,"warning":700.}
        for name,inner_code,outer_code in [("protected",3,2),("alert",2,1),("warning",1,0)]:
            for theta in np.arange(0,360,15)*np.pi/180:
                unit=np.array([np.cos(theta),np.sin(theta)])
                for delta,code in [(-1e-6,inner_code),(1e-6,outer_code)]:
                    point=np.array(geometry["center_m"])+(50+offsets[name]+delta)*unit
                    result=geometry_facts(geometry,point,layer_offsets=offsets)
                    self.assertEqual(int(result["layer"]),code,(name,theta,delta))
            point=[1450+offsets[name],2200]
            self.assertEqual(int(geometry_facts(geometry,point,layer_offsets=offsets)["layer"]),inner_code)

    def test_convex_polygon_flat_and_round_boundaries_both_windings(self):
        vertices=np.array([[-50,-40],[50,-40],[50,40],[-50,40]],float)
        offsets={"protected":80.,"alert":240.,"warning":700.}
        angle=.381;c,s=np.cos(angle),np.sin(angle)
        rotation=np.array([[c,-s],[s,c]]);origin=np.array([1400.,2200.])
        for reverse in (False,True):
            v=vertices[::-1] if reverse else vertices
            geometry={"type":"Polygon","vertices_m":(v@rotation.T+origin).tolist()}
            for layer,code_in,code_out in [("protected",3,2),("alert",2,1),("warning",1,0)]:
                for edge_base,unit in [(np.array([50.,0.]),np.array([1.,0.])),
                                       (np.array([50.,40.]),np.array([1.,1.])/np.sqrt(2))]:
                    for delta,expected in [(-1e-6,code_in),(1e-6,code_out)]:
                        point=(edge_base+(offsets[layer]+delta)*unit)@rotation.T+origin
                        facts=geometry_facts(geometry,point,layer_offsets=offsets)
                        self.assertEqual(int(facts["layer"]),expected,(reverse,layer,delta))

    def test_depth_is_exact_inside_and_outside_source_contour(self):
        offsets={"protected":50.,"alert":100.,"warning":200.}
        square={"type":"Polygon","vertices_m":[[-10,-10],[10,-10],[10,10],[-10,10]]}
        p=np.array([[0,0],[20,0],[10+30/np.sqrt(2),10+30/np.sqrt(2)]])
        result=geometry_facts(square,p,layer_offsets=offsets)
        np.testing.assert_allclose(result["protected_depth_m"],[60,40,20],atol=1e-12)
        circle={"type":"Circle","center_m":[0,0],"radius_m":10}
        np.testing.assert_allclose(geometry_facts(circle,[[0,0],[20,0]],layer_offsets=offsets)["protected_depth_m"],[60,40])

    def test_point_strip_obstacle_and_world_queries_share_authority(self):
        circle={"type":"Circle","center_m":[0,0],"radius_m":20}
        self.assertAlmostEqual(geometry_facts(circle,[[25,-5],[25,5]],footprint=True)["clearance_m"],5)
        poly={"type":"BufferedPolygon","vertices_m":[[-5,-5],[5,-5],[5,5],[-5,5]],"buffer_m":10}
        self.assertAlmostEqual(geometry_facts(poly,[[20,-5],[20,5]],footprint=True)["clearance_m"],5)
        boundary=radial_boundary_exact(poly,[0,0],np.pi/4)
        self.assertAlmostEqual(float(geometry_facts(poly,boundary)["signed_distance_m"]),0,places=10)

    def test_frame_and_event_facts_use_exact_layers(self):
        data=json.loads((ROOT/"tests/fixtures/v07_boundary_witnesses.json").read_text())
        scene,sk,run=fixture()
        scene["entities"]=[{"id":"f","type":"facility","geometry":data["facility"]["geometry"]}]
        from scene_v07.geometry import expand_geometry
        for name,offset in data["offsets_m"].items():
            scene["entities"].append({"id":name,"type":"protection_zone","facility_id":"f","layer":name,
                                     "offset_m":offset,"geometry":expand_geometry(data["facility"]["geometry"],offset)})
        run["p"][:,:,:2]=[3500,3500]
        for i,w in enumerate(data["witnesses"]):
            run["p"][10:,i,:2]=w["position_enu_m"][:2]
        labels,frames=measure(scene,sk,run,"synchronous")
        for i,a in enumerate(run["agent_ids"][:2]):
            self.assertEqual(int(frames["region_all_facilities"][10,i,0]),1)
            self.assertEqual(labels["agents"][a]["observed"]["regions_by_facility"]["f"]["warning"]["first_entry_s"],1.)
            self.assertIsNone(labels["agents"][a]["observed"]["core_event"]["t_s"])

    def test_exact_visibility_never_cuts_analytic_offset(self):
        scene={"world":{"geometry":{"type":"Polygon","vertices_m":[[0,0],[1000,0],[1000,1000],[0,1000]]}},
               "entities":[{"type":"hard_constraint_obstacle","geometry":{"type":"Circle","center_m":[500,500],"radius_m":100}}]}
        planner=ExactVisibilityPlanner(scene,30)
        route=planner.path([50,500],[950,500])
        self.assertIsNotNone(route)
        self.assertGreater(len(route),2)
        for a,b in zip(route,route[1:]):
            self.assertGreaterEqual(geometry_facts(scene["entities"][0]["geometry"],[a,b],footprint=True)["clearance_m"],30-1e-8)

    def test_task_predicates_do_not_import_tessellated_shapes(self):
        for path in (ROOT/"task_v07").glob("*.py"):
            tree=ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom):
                    self.assertFalse(any(n.name in {"to_shape","VisibilityPlanner","radial_boundary"} for n in node.names),str(path))
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                    self.assertNotEqual(node.func.attr,"buffer",str(path))


class IndependentAuditTests(unittest.TestCase):
    def test_independent_audit_detects_even_one_corrupt_frame(self):
        scene,sk,run=fixture()
        labels,frame=measure(scene,sk,run,"synchronous")
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            save_json(root/"public_scene.json",scene);save_json(root/"labels.json",labels);save_json(root/"task.json",sk)
            np.savez(root/"truth_10hz.npz",agent_ids=np.array(run["agent_ids"]),time_us=run["time_us"],p=run["p"],v=run["v"])
            write_csv(root/"truth.csv",run["agent_ids"],run["time_us"],run["p"],run["v"])
            np.savez(root/"frame_labels.npz",**frame)
            self.assertEqual(audit_episode(root)["status"],"PASS")
            frame["region_all_facilities"][30,0,0]=0
            np.savez(root/"frame_labels.npz",**frame)
            report=audit_episode(root)
            self.assertEqual(report["status"],"P0_STOP")
            self.assertEqual(report["region_difference_count"],1)

    def test_independent_auditor_does_not_reuse_label_geometry(self):
        tree=ast.parse((ROOT/"scripts/audit_v07_s2_exact.py").read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):
                self.assertNotIn(node.module,{"task_v07.geometry","task_v07.labels"})


class RevisedOutcomeAndTimingTests(unittest.TestCase):
    def test_spacing_two_or_more_is_only_diagnostic(self):
        for distance in (2.,6.488,14.999,15.,30.):
            scene,sk,run=fixture()
            run["p"][5,1]=run["p"][5,0]+[distance,0,0]
            labels,_=measure(scene,sk,run,"synchronous")
            self.assertEqual(labels["generation_quality"]["status"],"valid")
            self.assertTrue(labels["generation_quality"]["retained"])
            self.assertEqual(labels["task_groups"]["g"]["result"]["status"],"success")
            self.assertFalse(labels["generation_quality"]["separation_affects_task_result"])

    def test_below_two_excludes_without_rewriting_role_result(self):
        scene,sk,run=fixture()
        run["p"][5,1]=run["p"][5,0]+[1.999999,0,0]
        labels,_=measure(scene,sk,run,"synchronous")
        self.assertEqual(labels["generation_quality"]["status"],"generation_error")
        self.assertFalse(labels["generation_quality"]["retained"])
        self.assertEqual(labels["task_groups"]["g"]["result"]["status"],"success")

    def test_random_batches_positive_sizes_gaps_jitter_and_replay(self):
        _,sk,_=fixture();seen_counts=set();seen_sizes=set()
        measured=dict(zip("abcd",[100.,120.,150.,170.]))
        for seed in range(100):
            sk["column_seed"]=seed
            plans=departure_delays(sk,measured)
            self.assertEqual(plans,departure_delays(sk,measured))
            sync,seq=plans["synchronous"],plans["sequential"]
            seen_counts.add(seq["batch_count"]);seen_sizes.add(tuple(seq["batch_sizes"]))
            self.assertEqual(sum(seq["batch_sizes"]),4)
            self.assertTrue(all(n>=1 for n in seq["batch_sizes"]))
            self.assertTrue(all(40<=g<=90 for g in seq["inter_batch_gaps_s"]))
            self.assertLessEqual(max(sync["target_event_times_grid_s"].values())-min(sync["target_event_times_grid_s"].values()),10)
            for plan in plans.values():
                self.assertTrue(all(-3<=j<=3 for j in plan["jitter_s"].values()))
                for a in sk["members"]:
                    self.assertGreaterEqual(plan["departure_delays_s"][a],0)
                    self.assertAlmostEqual(measured[a]+plan["departure_delays_s"][a],plan["target_event_times_grid_s"][a])
        self.assertEqual(seen_counts,{2,3,4})
        self.assertIn((1,3),seen_sizes);self.assertIn((3,1),seen_sizes)
        self.assertIn((2,2),seen_sizes)
        self.assertGreater(len(set(plans["synchronous"]["jitter_s"].values())),1)

    def test_timing_assignment_saved_at_all_three_levels(self):
        scene,sk,run=fixture()
        plans=departure_delays(sk,dict(zip("abcd",[100.,120.,150.,170.])))
        plan=plans["sequential"]
        labels,_=measure(scene,sk,run,"sequential",plan["batch_by_agent"],timing_plan=plan)
        self.assertEqual(labels["task_groups"]["g"]["assigned"]["timing"],plan)
        self.assertEqual(labels["cluster"]["assigned"]["timing_by_group"]["g"],plan)
        for a in sk["members"]:
            self.assertEqual(labels["agents"][a]["assigned"]["timing"]["jitter_s"],plan["jitter_s"][a])
        self.assertEqual(labels["task_groups"]["g"]["result"]["status"],"success")
        self.assertFalse(labels["task_groups"]["g"]["observed"]["timing_diagnostics"]["coordination_matches_assignment"])

    def test_timeout_missing_event_unknown_but_role_failure_known(self):
        scene,sk,run=fixture()
        run["p"][:,:,:2]=run["p"][0,:,:2]
        run["execution_status"]="timeout"
        labels,_=measure(scene,sk,run,"synchronous")
        self.assertEqual(labels["task_groups"]["g"]["observed"]["coordination"]["classification"],"unknown")
        self.assertEqual(labels["agents"]["a"]["result"]["status"],"failure")
        prefix,_=measure(scene,sk,run,"synchronous",cutoff_s=1)
        self.assertEqual(prefix["agents"]["a"]["result"]["status"],"unknown")


if __name__=="__main__":
    unittest.main()
