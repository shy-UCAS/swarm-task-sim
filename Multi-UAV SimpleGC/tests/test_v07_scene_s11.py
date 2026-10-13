"""S1.1 sampling and diagnostic tests; no plotting or fastsim imports."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import random
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from shapely.geometry import LineString, Point

from scene_v07 import SceneConfig, canonical_json, check_family, sample_family, validate_public_scene
from scene_v07.batch import generate_attempt, representative_coverage, select_representatives
from scene_v07.diagnostics import blocks_straight, max_lateral_deviation, route_diagnostics
from scene_v07.geometry import VisibilityPlanner, center_of, to_shape
from scene_v07.sampling import sample_family_s1
from scene_v07.sampling_s11 import MAP_SIDES_M, SamplingPolicy, SamplingRejected, facility_count, place_obstacles


def complete_family(config=None):
    for seed in range(30):
        try:
            return sample_family(seed, config)
        except SamplingRejected:
            continue
    raise AssertionError("No complete family in fixed test stream")


class SamplingS11Tests(unittest.TestCase):
    def test_weighted_facility_count_distribution(self):
        rng = random.Random(821)
        counts = Counter(facility_count(rng) for _ in range(20000))
        for count, proportion in [(1,.4),(2,.35),(3,.25)]:
            self.assertAlmostEqual(counts[count]/20000,proportion,delta=.02)

    def test_complete_contours_entries_and_layout_constraints(self):
        seen = set()
        for seed in range(45):
            try:
                scene,family = sample_family(seed,SceneConfig(angle_step_deg=30))
            except SamplingRejected:
                continue
            validate_public_scene(scene)
            facilities = [e for e in scene["entities"] if e["type"]=="facility"]
            seen.add(len(facilities))
            self.assertEqual(family["config"]["map_side_m"],MAP_SIDES_M[len(facilities)])
            world = to_shape(scene["world"]["geometry"])
            self.assertEqual(world.bounds,(0,0,MAP_SIDES_M[len(facilities)],MAP_SIDES_M[len(facilities)]))
            q = family["config"]["checking_quad_segs"]
            warnings = [to_shape(e["geometry"],q,True) for e in scene["entities"] if e.get("layer")=="warning"]
            alerts = [to_shape(e["geometry"],q,True) for e in scene["entities"] if e.get("layer")=="alert"]
            for warning in warnings:
                self.assertTrue(world.covers(warning))
                for entry in scene["entry_zones"]:
                    self.assertGreater(warning.distance(to_shape(entry["geometry"])),30)
            for i,a in enumerate(alerts):
                self.assertFalse(any(a.intersects(b) for b in alerts[:i]))
            checked = check_family(scene,family)
            self.assertFalse(any(issue["category"]=="geometry" for issue in checked["issues"]))
        self.assertEqual(seen,{1,2,3})

    def test_same_seed_policy_reconstructs_bytes(self):
        policy = SamplingPolicy(obstacle_attempts=24)
        a,b = sample_family(1,policy=policy)
        c,d = sample_family(1,SceneConfig(**b["config"]),policy=SamplingPolicy(**b["sampling_policy"]))
        self.assertEqual(canonical_json(a),canonical_json(c))
        self.assertEqual(canonical_json(b),canonical_json(d))
        self.assertEqual(b["sampling_revision"],"s1.1")

    def test_original_s1_revision_remains_byte_reproducible(self):
        expected = sample_family_s1(4443110635622324325)
        actual = sample_family(4443110635622324325,revision="s1")
        self.assertEqual(canonical_json(expected),canonical_json(actual))
        self.assertEqual(actual[1]["generator_version"],"traj2language.scene_sampler/0.7-s1.2")

    def test_entry_blockers_between_entry_and_warning_actually_block(self):
        blocker_count = 0
        for seed in range(35):
            try:
                scene,family = sample_family(seed)
            except SamplingRejected:
                continue
            entities = {e["id"]: e for e in scene["entities"]}
            entries = {e["id"]: e for e in scene["entry_zones"]}
            for placement in family["obstacle_placements"]:
                if placement["placement"]!="entry_blocking":
                    continue
                obstacle = entities[placement["obstacle_id"]]
                facility = entities[placement["reference_facility_id"]]
                line = LineString([center_of(entries[placement["entry_id"]]["geometry"]),center_of(facility["geometry"])])
                self.assertTrue(blocks_straight(obstacle["geometry"],line))
                warning = next(e for e in scene["entities"] if e.get("facility_id")==facility["id"] and e.get("layer")=="warning")
                self.assertFalse(to_shape(obstacle["geometry"],64,True).intersects(to_shape(warning["geometry"],64,True)))
                blocker_count += 1
        self.assertGreaterEqual(blocker_count,10)

    def test_skip_budget_does_not_resample_successful_obstacles(self):
        rng=Mock()
        rng.choice.side_effect=["entry_blocking","facility_side","entry_blocking"]
        geometry={"type":"Circle","center_m":[1000,1000],"radius_m":100}
        def candidate(rng,placement,*args):
            return deepcopy(geometry),{"placement":placement},None
        def problem(geometry,record,*args):
            return "forced_local_failure" if record["placement"]=="facility_side" else None
        with patch("scene_v07.sampling_s11.obstacle_candidate",side_effect=candidate) as calls, patch(
                "scene_v07.sampling_s11._obstacle_problem",side_effect=problem):
            obstacles,placements,sampling=place_obstacles(rng,[{},{}],{},[],None,SceneConfig(),SamplingPolicy(obstacle_attempts=3),requested=3)
        self.assertEqual([e["id"] for e in obstacles],["obstacle_01","obstacle_03"])
        self.assertEqual(calls.call_count,5)
        self.assertEqual(sampling["skipped_count"],1)
        self.assertEqual([s["attempts"] for s in sampling["slots"]],[1,3,1])
        self.assertEqual(sampling["slots"][1]["rejected_attempt_reasons"],{"forced_local_failure":3})
        self.assertEqual(obstacles[0]["geometry"],geometry)

    def test_radars_are_legal_and_initial_conditions_stay_common(self):
        for seed in range(25):
            try:
                scene,family=sample_family(seed)
            except SamplingRejected:
                continue
            world=to_shape(scene["world"]["geometry"])
            for entity in scene["entities"]:
                if entity["type"]=="radar":
                    self.assertTrue(world.covers(Point(entity["geometry"]["position_m"])))
            self.assertTrue(4<=family["vehicle_count"]<=12)
            self.assertTrue(4<=family["cruise_speed_m_s"]<=10)
            self.assertTrue(all(s["position_enu_m"][2]==family["task_altitude_m"] for s in family["initial_states"]))

    def test_new_sampling_metadata_stays_out_of_public_scene(self):
        scene,family=complete_family()
        self.assertEqual(set(scene),{"schema_version","coordinate_system","units","world","entry_zones","entities"})
        self.assertEqual(scene["schema_version"],"traj2language.public_scene/0.7-s1.1")
        self.assertIn("obstacle_sampling",family)
        self.assertNotIn("sampling_policy",scene)
        self.assertNotIn("sampling_seed",scene)

    def test_no_obstacles_is_recorded_as_sampling_rejection_not_public_json(self):
        scene,family=complete_family()
        scene["entities"]=[e for e in scene["entities"] if e["type"]!="hard_constraint_obstacle"]
        family["obstacle_placements"]=[]
        family["obstacle_sampling"]={"requested_count":1,"placed_count":0,"skipped_count":1,"slots":[]}
        with tempfile.TemporaryDirectory() as root, patch("scene_v07.batch.sample_family",side_effect=SamplingRejected("sampling_no_obstacle_placed",scene,family)):
            summary=generate_attempt(1,output_root=root)
            directory=Path(summary["attempt_directory"])/family["family_id"]
            self.assertFalse((directory/"public_scene.json").exists())
            self.assertTrue((directory/"candidate_geometry.json").exists())
            self.assertEqual(summary["accepted_count"],0)
            self.assertEqual(summary["sampling_rejected_count"],1)

    def test_original_geometry_gates_reject_intruding_obstacle(self):
        scene,family=complete_family(SceneConfig(angle_step_deg=30))
        facility=next(e for e in scene["entities"] if e["type"]=="facility")
        obstacle=next(e for e in scene["entities"] if e["type"]=="hard_constraint_obstacle")
        obstacle["geometry"]={"type":"Circle","center_m":center_of(facility["geometry"]),"radius_m":100}
        checked=check_family(scene,family)
        self.assertFalse(checked["accepted"])
        self.assertIn("obstacle_intersects_alert",{i["code"] for i in checked["issues"]})

    def test_new_attempt_saved_bytes_rebuild_and_maps_match_facility_counts(self):
        with tempfile.TemporaryDirectory() as root:
            summary=generate_attempt(8,output_root=root,config=SceneConfig(angle_step_deg=30))
            records=json.loads((Path(summary["attempt_directory"])/"candidates.json").read_text(encoding="utf-8"))
            self.assertEqual(len(records),8)
            for record in records:
                directory=Path(record["directory"])
                saved=json.loads((directory/"family_initial.json").read_text(encoding="utf-8"))
                self.assertEqual(record["map_side_m"],MAP_SIDES_M[record["facility_count"]])
                try:
                    scene,family=sample_family(saved["sampling_seed"],SceneConfig(**saved["config"]),policy=SamplingPolicy(**saved["sampling_policy"]))
                except SamplingRejected as failure:
                    self.assertFalse(record["public_scene_published"])
                    scene,family=failure.scene,failure.family
                else:
                    self.assertTrue(record["public_scene_published"])
                    self.assertEqual((directory/"public_scene.json").read_bytes(),canonical_json(scene))
                self.assertEqual((directory/"family_initial.json").read_bytes(),canonical_json(family))
            self.assertFalse(summary["route_diagnostic_used_as_rejection_gate"])

    def test_invalid_budgets_and_revision_rejected(self):
        for limit in (0,-1,True,2.5):
            with self.assertRaises(ValueError):
                SamplingPolicy(obstacle_attempts=limit)
        with self.assertRaises(ValueError):
            sample_family(1,revision="unknown")


class RouteDiagnosticTests(unittest.TestCase):
    def test_cross_track_distance_is_maximum_over_polyline(self):
        self.assertEqual(max_lateral_deviation([[0,0],[4,6],[10,0]],[0,0],[10,0]),6)
        self.assertEqual(max_lateral_deviation([[0,0],[12,5],[10,0]],[0,0],[10,0]),5)
        self.assertEqual(max_lateral_deviation([[0,0],[10,0]],[0,0],[10,0]),0)
        self.assertIsNone(max_lateral_deviation(None,[0,0],[10,0]))

    def test_cross_track_distance_is_rotation_translation_invariant(self):
        transform=lambda p:[70-p[1],20+p[0]]
        path=[[0,0],[4,6],[10,0]]
        self.assertEqual(max_lateral_deviation(list(map(transform,path)),transform(path[0]),transform(path[-1])),6)

    def test_raw_obstacle_and_safety_margin_blockers_are_distinct(self):
        scene={"world":{"geometry":{"type":"Polygon","vertices_m":[[0,-10],[10,-10],[10,10],[0,10]]}},
               "entities":[{"id":"x","type":"hard_constraint_obstacle","geometry":{"type":"Circle","center_m":[5,1.5],"radius_m":1}}]}
        family={"obstacle_placements":[{"obstacle_id":"x","placement":"entry_blocking"}]}
        planner=VisibilityPlanner(scene,1)
        start,finish=[0,0],[10,0]
        result=route_diagnostics(scene,family,planner,start,finish,planner.path(start,finish))
        self.assertFalse(result["straight_blocked_by_obstacle"])
        self.assertTrue(result["straight_blocked_with_margin"])
        self.assertFalse(result["straight_blocked_by_entry_blocker"])
        self.assertGreater(result["max_lateral_deviation_m"],0)

    def test_diagnostics_are_not_acceptance_gates(self):
        scene,family=complete_family(SceneConfig(angle_step_deg=30))
        baseline=check_family(scene,family)
        fake={"straight_blocked_by_obstacle":True,"blocking_obstacle_ids":[],"straight_blocked_with_margin":True,
              "straight_blocked_by_entry_blocker":True,"max_lateral_deviation_m":1000000}
        with patch("scene_v07.checks.route_diagnostics",return_value=fake):
            changed=check_family(scene,family)
        self.assertEqual(changed["accepted"],baseline["accepted"])
        self.assertEqual(changed["issues"],baseline["issues"])
        self.assertEqual(changed["approaches"],baseline["approaches"])

    def test_blocked_fraction_and_detour_deviation_ignore_rejected_routes(self):
        from scene_v07.batch import summarize
        row={"detour_ratio":1.1,"straight_blocked_by_obstacle":True,"straight_blocked_with_margin":True,
             "straight_blocked_by_entry_blocker":True,"max_lateral_deviation_m":80}
        direct={**row,"detour_ratio":1.0,"straight_blocked_by_obstacle":False,
                "straight_blocked_by_entry_blocker":False,"max_lateral_deviation_m":0}
        record={"accepted":True,"issue_codes":[],"geometry_issue_codes":[],"connectivity_issue_codes":[],
                "detour_ratios":[1.1,1.0],"approach_spans_deg":[360],"facility_count":1,"layout":"single",
                "facility_shapes":["Circle"],"obstacle_count":1,"obstacle_placements":["entry_blocking"],
                "radar_count":1,"vehicle_count":4,"route_diagnostics":[row,direct]}
        rejected={**record,"accepted":False,"route_diagnostics":[{**row,"max_lateral_deviation_m":999}]}
        result=summarize([record,rejected])
        self.assertEqual(result["accepted_straight_blocked_fraction"],{"blocked":1,"routes":2,"fraction":.5})
        self.assertEqual(result["accepted_straight_margin_blocked_fraction"]["fraction"],1.0)
        self.assertEqual(result["accepted_detour_max_lateral_deviation_m"]["max"],80)
        self.assertEqual(result["accepted_entry_blocker_blocked_route_count"],1)

    def test_gallery_quota_selects_multi_facility_and_entry_blockers(self):
        records=[]
        for i in range(24):
            count=i%3+1
            records.append({"candidate_index":i,"accepted":True,"facility_count":count,
                            "layout":"single" if count==1 else ("clustered" if count==2 else "linear"),
                            "route_diagnostics":[{"straight_blocked_by_entry_blocker":i%2==0,"max_lateral_deviation_m":i}]})
        selected=select_representatives(records,16)
        covered=representative_coverage(selected)
        self.assertEqual(covered["count"],16)
        self.assertGreaterEqual(covered["two_facility_accepted"],3)
        self.assertGreaterEqual(covered["three_facility_accepted"],3)
        self.assertGreaterEqual(covered["entry_blocker_straight_blocked_accepted"],3)
        self.assertEqual(len({r["candidate_index"] for r in selected}),16)


if __name__=="__main__":
    unittest.main()
