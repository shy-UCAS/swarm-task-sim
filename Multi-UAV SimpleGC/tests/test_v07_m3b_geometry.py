"""M3b work-shape and shared-policy contracts, independent of runtime samples."""
import random
import unittest
from unittest.mock import patch
import numpy as np
from v07_m3_fixtures import request
from task_v07.expansion.pipeline import exclusion_policy, forbidden_zone_ids
from task_v07.unified.spec import build_spec
from task_v07.unified.free_space import free_space, work_region
from task_v07.unified.shapes import draw_shape
from task_v07.unified.route import route_group, GeometryRejected
from task_v07.unified.checks import plan_checks
from task_v07.unified.patrol_shape import patrol_shape, parallel_paths
from task_v07.geometry import geometry_facts


def role_request(method, multi=False, count=2):
    scene, descriptor, group = request(multi, count)
    group["execution_method"] = method
    group["role"] = "reconnaissance" if method in ("area_search", "close_observation") else method
    descriptor["base_intent"] = "penetration" if method == "intrusion" else group["role"]
    return scene, descriptor, group


class M3bGeometryTests(unittest.TestCase):
    def test_feint_continuous_turn_single_alert_visit_no_dwell(self):
        scene,d,g=role_request("feint"); spec=build_spec(d,g); free=free_space(scene,spec); rng=random.Random(3)
        shape=draw_shape(spec,work_region(scene,spec,free),rng,free)
        bundle,template=route_group(scene,spec,shape,free,d["family_conditions"]["initial_states"],rng)
        check=plan_checks(scene,spec,bundle,template,free,d["family_conditions"]["initial_states"])
        self.assertEqual(check["status"],"PASS",check["issues"])
        self.assertGreaterEqual(shape["draw"]["q"],.3)
        self.assertLessEqual(shape["draw"]["q"],.8)
        for ref in template["references"].values():
            self.assertNotIn("intermediate_dwell",ref)
            measured=geometry_facts(free.target["geometry"],np.asarray(ref["work_points_enu_m"])[:,:2],footprint=True)["clearance_m"]
            self.assertAlmostEqual(measured,ref["feint_drawn_contour_clearance_m"],places=6)
    def check_patrol(self, form):
        scene,d,g = role_request("monitoring",multi=True,count=4)
        spec=build_spec(d,g); free=free_space(scene,spec); rng=random.Random(4)
        shape=patrol_shape(spec,free,rng,{"direction_deg":37.},force_form=form)
        offsets=[]
        for slot in shape["slots"]:
            ref=slot["reference_fields"]; rho=ref["patrol_offset_m"]
            points=np.asarray(slot["work"])
            np.testing.assert_allclose(geometry_facts(free.target["geometry"],points)["signed_distance_m"],rho,atol=1e-7)
            incoming=points[0]-slot["entry"]
            self.assertAlmostEqual(float(np.dot(incoming/np.linalg.norm(incoming),slot["direction"])),1.)
            offsets.append(rho)
            if form=="arc":
                forward=np.asarray(ref["patrol_forward_points_m"]); size=len(forward)
                np.testing.assert_array_equal(points[size-1:2*size-1],forward[::-1])
                self.assertGreaterEqual(shape["draw"]["arc_span_deg"],150.)
        self.assertTrue(np.all(np.diff(sorted(offsets)) >= spec["family"]["lateral_spacing_m"]-1e-8))
        bundle,template=route_group(scene,spec,shape,free,d["family_conditions"]["initial_states"],rng)
        check=plan_checks(scene,spec,bundle,template,free,d["family_conditions"]["initial_states"])
        self.assertEqual(check["status"],"PASS",check["issues"])
        for ref in template["references"].values():
            np.testing.assert_allclose(geometry_facts(free.target["geometry"],np.asarray(ref["work_points_enu_m"])[:,:2])["signed_distance_m"],ref["patrol_offset_m"],atol=1e-7)

    def test_patrol_full_preserves_group_unique_continuous_lanes(self): self.check_patrol("full")
    def test_patrol_arc_reversals_preserve_group_unique_lanes(self): self.check_patrol("arc")

    def test_patrol_polygon_offsets_and_finite_short_arc_rejection(self):
        base={"type":"Polygon","vertices_m":[[-100.,-70.],[100.,-70.],[130.,70.],[-100.,70.]]}
        paths,_,_=parallel_paths(base,[200.,220.],210.,.37,9.,1.)
        for rho,points in zip([200.,220.],paths):
            np.testing.assert_allclose(geometry_facts(base,np.asarray(points))["signed_distance_m"],rho,atol=1e-7)
        scene,d,g=role_request("monitoring"); spec=build_spec(d,g); free=free_space(scene,spec)
        with patch("task_v07.unified.patrol_shape.common_arcs",return_value=([(0.,1.)],False)):
            with self.assertRaisesRegex(GeometryRejected,"patrol_arc_too_short"):
                patrol_shape(spec,free,random.Random(4),{"direction_deg":37.},force_form="arc")
        spec["family"]["lateral_spacing_m"]=1000.
        with self.assertRaisesRegex(GeometryRejected,"patrol_band_too_narrow"):
            patrol_shape(spec,free,random.Random(4),{"direction_deg":37.})

    def test_observation_keeps_true_intermediate_dwell_after_join_cleanup(self):
        scene, d, g = role_request("close_observation")
        spec = build_spec(d,g); free = free_space(scene,spec)
        rng = random.Random(3)
        shape = draw_shape(spec,work_region(scene,spec,free),rng,free)
        bundle, template = route_group(scene,spec,shape,free,d["family_conditions"]["initial_states"],rng)
        checks = plan_checks(scene,spec,bundle,template,free,d["family_conditions"]["initial_states"])
        self.assertEqual(checks["status"],"PASS", checks["issues"])
        for agent, ref in template["references"].items():
            dwell = ref["intermediate_dwell"]; points = bundle.waypoints_by_agent[agent]
            self.assertGreater(dwell["waypoint_index"],0)
            self.assertLess(dwell["waypoint_index"],len(points)-1)
            np.testing.assert_array_equal(points[dwell["waypoint_index"]],ref["observation_point_enu_m"])
            self.assertGreaterEqual(dwell["duration_s"],40.)
            self.assertLessEqual(dwell["duration_s"],90.)

    def test_six_execution_methods_use_the_shared_exclusion_policy(self):
        for method in ("transit", "area_search", "close_observation", "monitoring", "feint", "intrusion"):
            with self.subTest(method=method):
                scene, d, g = role_request(method)
                free = free_space(scene, build_spec(d,g))
                expected = exclusion_policy(scene, g["role"], g["target_id"], g["members"])
                self.assertEqual(free.exclusion_policy, expected)
                self.assertEqual({c["id"] for c in free.constraints if c["kind"] == "forbidden_layer"},
                                 set().union(*(set(forbidden_zone_ids(scene,p)) for p in expected.values())))

    def test_search_sector_coverage_and_complete_route(self):
        scene, d, g = role_request("area_search")
        spec = build_spec(d,g); free = free_space(scene,spec); failures = []
        for seed in range(12):
            rng = random.Random(seed)
            try:
                shape = draw_shape(spec,work_region(scene,spec,free),rng,free)
                bundle, template = route_group(scene,spec,shape,free,d["family_conditions"]["initial_states"],rng)
            except GeometryRejected as exc:
                failures.append(exc.reason); continue
            check = plan_checks(scene,spec,bundle,template,free,d["family_conditions"]["initial_states"])
            if check["status"] != "PASS":
                failures.append(check["issues"]); continue
            self.assertGreaterEqual(shape["draw"]["nominal_group_coverage"],.95)
            self.assertGreaterEqual(template["survey"]["area_m2"],150000)
            self.assertLessEqual(template["survey"]["area_m2"],600000)
            self.assertTrue(all(r["scan_strip_count"]>0 for r in template["references"].values()))
            return
        self.fail(str(failures))


if __name__ == "__main__": unittest.main()
