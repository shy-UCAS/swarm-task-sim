"""Minimal S2 semantics and S1.2 regression tests; no plotting import."""
from copy import deepcopy
from itertools import combinations
from pathlib import Path
import json
import random
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scene_v07 import sample_family, canonical_json, check_family, SceneConfig
from scene_v07.geometry import to_shape
from scene_v07.sampling_s11 import SamplingPolicy, place_obstacles_s12
from task_v07.labels import measure, coordination
from task_v07.execution import departure_delays, frozen_config, execute
from task_v07.planning import clean_route, seed_for, build_skeleton
from task_v07.io import load_episode, write_episode, load_pair, read_json, INPUT_KEYS


def fixture():
    scene={"world":{"geometry":{"type":"Polygon","vertices_m":[[0,0],[4000,0],[4000,4000],[0,4000]]}},
           "entities":[{"id":"f","type":"facility","geometry":{"type":"Circle","center_m":[2000,2000],"radius_m":20}}]}
    for name,r in [("warning",700),("alert",300),("protected",150)]:
        scene["entities"].append({"id":name,"type":"protection_zone","facility_id":"f","layer":name,
                                 "geometry":{"type":"Circle","center_m":[2000,2000],"radius_m":r}})
    ids=["a","b","c","d"];ends=[[1950,1950,100],[2050,1950,100],[2050,2050,100],[1950,2050,100]]
    sk={"base_intent":"penetration","role":"intrusion","target_id":"f","group_id":"g","members":ids,
        "agent_ids":ids,"execution_method":"polygon_visit","planning_min_separation_m":15,
        "required_intrusion_depth_m":20,"terminal_radius_m":1,"terminal_speed_m_s":.15,
        "terminal_hold_s":2,"sync_window_s":10,"batch_split_gap_s":20,"initial_settle_s":20,
        "sequential_gap_s":60,"column_seed":54321,
        "references":{a:{"endpoint_enu_m":e} for a,e in zip(ids,ends)}}
    n=61;t=np.arange(n,dtype=np.int64)*100000
    p=np.array([[e for e in ends] for _ in t],float)
    p[:20,:,:2]=np.array(ends)[:,:2]+np.array([[-300,-300],[300,-300],[300,300],[-300,300]])
    run={"agent_ids":ids,"time_us":t,"p":p,"v":np.zeros_like(p),"execution_status":"completed","end_us":6100000}
    return scene,sk,run


class S12Tests(unittest.TestCase):
    def test_nonoverlap_and_reproducibility(self):
        for seed in range(20):
            scene,family=sample_family(seed,revision="s1.2")
            again=sample_family(seed,revision="s1.2")
            self.assertEqual(canonical_json([scene,family]),canonical_json(list(again)))
            obs=[to_shape(e["geometry"],64,True) for e in scene["entities"] if e["type"]=="hard_constraint_obstacle"]
            self.assertFalse(any(a.intersects(b) for a,b in combinations(obs,2)))
            self.assertTrue(check_family(scene,family)["accepted"])

    def test_failed_type_falls_back_before_skip(self):
        def candidate(rng,placement,*args):
            return {"type":"Circle","center_m":[1000,1000],"radius_m":100},{"placement":placement},None
        seen=[]
        def problem(geometry,record,*args):
            seen.append(record["placement"])
            return "force_first_type" if record["placement"]==seen[0] else None
        with patch("scene_v07.sampling_s11.obstacle_candidate",side_effect=candidate), patch(
                "scene_v07.sampling_s11._obstacle_problem",side_effect=problem):
            obs,_,audit=place_obstacles_s12(random.Random(2),[{},{}],{},[],None,SceneConfig(),SamplingPolicy(obstacle_attempts=2))
        self.assertEqual(audit["requested_count"],1)
        self.assertEqual(len(obs),1)
        self.assertEqual(len(audit["slots"][0]["tried_types"]),2)
        self.assertEqual(audit["slots"][0]["attempts"],3)

    def test_all_types_fail_then_skip(self):
        with patch("scene_v07.sampling_s11.obstacle_candidate",return_value=(None,{},"forced")):
            obs,_,audit=place_obstacles_s12(random.Random(2),[{},{}],{},[],None,SceneConfig(),SamplingPolicy(obstacle_attempts=2))
        self.assertEqual(obs,[])
        self.assertEqual(audit["slots"][0]["attempts"],6)
        self.assertEqual(len(audit["slots"][0]["tried_types"]),3)

    def test_new_checker_rejects_overlap(self):
        scene,family=sample_family(1,revision="s1.2")
        obstacle=next(e for e in scene["entities"] if e["type"]=="hard_constraint_obstacle")
        scene["entities"].append({**deepcopy(obstacle),"id":"obstacle_99"})
        family["obstacle_placements"].append({**deepcopy(family["obstacle_placements"][0]),"obstacle_id":"obstacle_99"})
        result=check_family(scene,family)
        self.assertIn("independent_obstacles_overlap",[i["code"] for i in result["issues"]])


class SemanticTests(unittest.TestCase):
    def test_missing_event_unknown_not_planned(self):
        scene,sk,run=fixture()
        labels,_=measure(scene,sk,run,"synchronous",cutoff_s=1.)
        self.assertEqual(labels["task_groups"]["g"]["observed"]["coordination"]["classification"],"unknown")
        self.assertIsNone(labels["cluster"]["observed"]["primary_target"])
        for a in labels["agents"].values():
            self.assertIsNone(a["observed"]["core_event"]["t_s"])
            self.assertNotIn("entered_protected_zone",a["observed"]["behaviors"])
            self.assertEqual(a["result"]["status"],"unknown")

    def test_prefix_does_not_inherit_future_success(self):
        scene,sk,run=fixture()
        full,_=measure(scene,sk,run,"synchronous")
        early,_=measure(scene,sk,run,"synchronous",cutoff_s=2.5)
        self.assertEqual(full["cluster"]["result"]["status"],"success")
        self.assertEqual(early["agents"]["a"]["result"]["status"],"unknown")
        self.assertLess(early["agents"]["a"]["observed"]["endpoint_hold_s"],2)
        self.assertTrue(all(a["observed"]["core_event"]["t_s"]<=2.4 for a in early["agents"].values()))

    def test_column_permutation_preserves_id_labels_and_separation(self):
        scene,sk,run=fixture()
        a,_=measure(scene,sk,run,"synchronous")
        permutation=[2,0,3,1]
        other={**run,"agent_ids":[run["agent_ids"][i] for i in permutation],
               "p":run["p"][:,permutation],"v":run["v"][:,permutation]}
        b,_=measure(scene,sk,other,"synchronous")
        for key in ("agents","task_groups","cluster"):
            self.assertEqual(a[key],b[key])

    def test_chain_does_not_form_synchronous_batch(self):
        events={a:{"t_s":t} for a,t in zip("abcd",[0,9,18,27])}
        self.assertEqual(coordination(events)["classification"],"other")
        events={a:{"t_s":t} for a,t in zip("abcd",[0,2,60,62])}
        self.assertEqual(coordination(events)["classification"],"sequential")
        self.assertEqual(len(coordination(events)["batches"]),2)

    def test_assigned_and_observed_are_independent(self):
        scene,sk,run=fixture()
        labels,_=measure(scene,sk,run,"sequential")
        group=labels["task_groups"]["g"]
        self.assertEqual(group["assigned"]["planned_coordination"],"sequential")
        self.assertEqual(group["observed"]["coordination"]["classification"],"synchronous")
        self.assertFalse(group["result"]["conditions"]["coordination_matches_assignment"])

    def test_one_incomplete_agent_not_copied_group_success(self):
        scene,sk,run=fixture()
        run["p"][:,0,0]=1700
        labels,_=measure(scene,sk,run,"synchronous")
        self.assertEqual(labels["agents"]["a"]["result"]["status"],"failure")
        self.assertEqual(labels["agents"]["b"]["result"]["status"],"success")
        self.assertNotEqual(labels["task_groups"]["g"]["result"]["status"],"success")

    def test_measured_minimum_uses_actual_state_not_endpoints(self):
        scene,sk,run=fixture()
        run["p"][5,1]=run["p"][5,0]+[2,0,0]
        labels,_=measure(scene,sk,run,"synchronous")
        self.assertAlmostEqual(labels["cluster"]["observed"]["minimum_separation_m"],2)
        self.assertFalse(labels["agents"]["a"]["result"]["conditions"]["separation_clear"])

    def test_highfrequency_grid_rejected(self):
        scene,sk,run=fixture()
        run["time_us"]=np.arange(61)*20000
        with self.assertRaisesRegex(ValueError,"10 Hz"):
            measure(scene,sk,run,"synchronous")

    def test_delays_come_from_measured_times(self):
        _,sk,_=fixture()
        times=dict(zip("abcd",[100.,120.,150.,170.]))
        schedules,batches=departure_delays(sk,times)
        self.assertEqual({round(times[a]+schedules["synchronous"][a],6) for a in times},{175.})
        self.assertEqual({round(times[a]+schedules["sequential"][a],6) for a in times},{175.,235.})
        self.assertEqual(len({v for v in batches.values()}),2)
        with self.assertRaises(ValueError):
            departure_delays(sk,{**times,"a":None})

    def test_no_matplotlib_dependency(self):
        import sys
        self.assertNotIn("matplotlib",sys.modules)


class ExecutorTests(unittest.TestCase):
    def test_frozen_engine_short_route_and_real_wait(self):
        ids=["a"]
        sk={"agent_ids":ids,"initial_states":[{"agent_id":"a","position_enu_m":[0,0,100],
            "velocity_enu_m_s":[0,0,0],"acceleration_enu_m_s2":[0,0,0]}],
            "references":{"a":{"points_enu_m":[[0,0,100],[20,0,100]]}},"cruise_speed_m_s":4,
            "initial_settle_s":1,"terminal_radius_m":1,"terminal_speed_m_s":.15,"terminal_hold_s":2}
        a=execute(sk,{"a":0})
        b=execute(sk,{"a":2})
        self.assertEqual(a["execution_status"],"completed")
        self.assertEqual(b["execution_status"],"completed")
        self.assertTrue(np.all(b["p"][b["time_us"]<3000000,0,0]==0))
        self.assertTrue(np.all(np.diff(b["time_us"])==100000))
        self.assertEqual(frozen_config().vehicle_profile.max_accel_xy_m_s2,3.75)
        self.assertGreater(b["end_us"],a["end_us"])


class LoaderAndSurveyTests(unittest.TestCase):
    def test_observation_loader_pair_whitelist_and_column_alignment(self):
        scene,family=sample_family(int("f8174c26e85978ef",16),revision="s1.2")
        sk=build_skeleton(scene,family,"penetration",0,"facility_01")
        ids=sk["agent_ids"];states={x["agent_id"]:x for x in family["initial_states"]}
        p=np.array([[states[a]["position_enu_m"] for a in ids]]*3)
        v=np.array([[states[a]["velocity_enu_m_s"] for a in ids]]*3)
        run={"agent_ids":ids,"time_us":np.arange(3,dtype=np.int64)*100000,"p":p,"v":v,"a":np.zeros_like(p),
             "end_us":300000,"execution_status":"timeout","wall_s":0.,"config_sha256":"fixture"}
        with tempfile.TemporaryDirectory() as temp:
            roots=[]
            for mode in ("synchronous","sequential"):
                labels,frame=measure(scene,sk,run,mode)
                root=Path(temp)/mode
                write_episode(root,scene,family,sk,run,labels,frame,{a:0 for a in ids},mode,{a:None for a in ids})
                roots.append(root)
            pair=load_pair(*roots)
            self.assertEqual(pair["inputs"][0]["agent_ids"],pair["inputs"][1]["agent_ids"])
            self.assertEqual(set(pair["inputs"][0]),INPUT_KEYS)
            self.assertNotIn("target_id",pair["inputs"][0]["scene"])
            reverse=load_episode(roots[0],agent_ids=ids[::-1])
            np.testing.assert_array_equal(reverse["x"],pair["inputs"][0]["x"][:,::-1])
            np.testing.assert_array_equal(reverse["mask"],pair["inputs"][0]["mask"][:,::-1])
            self.assertFalse(np.array_equal(pair["inputs"][0]["x"][:,:,:3],p))
            # Manifest hash verification rejects source/label tampering.
            with (roots[0]/"labels.json").open("a") as f:f.write(" ")
            with self.assertRaises(ValueError):load_episode(roots[0])

    def test_independent_endpoint_and_waypoint_contracts(self):
        scene,family=sample_family(int("f8174c26e85978ef",16),revision="s1.2")
        sk=build_skeleton(scene,family,"penetration",0,"facility_01")
        self.assertGreaterEqual(sk["planned_approach_span_deg"],90)
        ends=[r["endpoint_enu_m"] for r in sk["references"].values()]
        self.assertGreaterEqual(min(np.linalg.norm(np.array(a)-b) for a,b in combinations(ends,2)),15)
        for r in sk["references"].values():
            self.assertGreaterEqual(np.linalg.norm(np.diff(r["points_enu_m"],axis=0),axis=1).min(),1)

    def test_scan_start_requires_actual_effective_motion_and_preserves_raw_event(self):
        scene,sk,run=fixture()
        sk.update(base_intent="reconnaissance",role="reconnaissance",execution_method="equal_strip_lawnmower")
        # Sector in the warning ring, outside the alert zone.
        vertices=[[2400,1950],[2460,1950],[2460,2050],[2400,2050]]
        sk["survey"]={"vertices_m":vertices,"model":"ideal_isotropic_horizontal_disk","assumptions":"test proxy",
                      "grid_spacing_m":10.,"footprint_radius_m":35.,"required_group_coverage":.9,
                      "effective_speed_min_m_s":.5,"lane_endpoint_radius_m":5.}
        for a in sk["members"]:
            sk["references"][a].update(scan_vertices_m=vertices,scan_lane_endpoints_m=vertices)
        run["p"][:,:,:2]=[2420,2000]
        run["execution_status"]="timeout"
        labels,_=measure(scene,sk,run,"synchronous")
        self.assertIsNone(labels["agents"]["a"]["observed"]["core_event"]["t_s"])
        run["v"][10:,:,0]=1
        labels,_=measure(scene,sk,run,"synchronous")
        ev=labels["agents"]["a"]["observed"]["core_event"]
        self.assertEqual(ev["raw_event_type"],"scan_start")
        self.assertEqual(ev["role_core_event"],"start_core_operation")
        self.assertEqual(ev["t_s"],1.)
        prefix,_=measure(scene,sk,run,"synchronous",cutoff_s=.9)
        self.assertIsNone(prefix["agents"]["a"]["observed"]["core_event"]["t_s"])


if __name__=="__main__":
    unittest.main()

