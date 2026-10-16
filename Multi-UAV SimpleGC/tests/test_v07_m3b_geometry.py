"""M3b work-shape and shared-policy contracts, independent of runtime samples."""
import random
import unittest
from v07_m3_fixtures import request
from task_v07.expansion.pipeline import exclusion_policy, forbidden_zone_ids
from task_v07.unified.spec import build_spec
from task_v07.unified.free_space import free_space, work_region
from task_v07.unified.shapes import draw_shape
from task_v07.unified.route import route_group, GeometryRejected
from task_v07.unified.checks import plan_checks


def role_request(method, multi=False, count=2):
    scene, descriptor, group = request(multi, count)
    group["execution_method"] = method
    group["role"] = "reconnaissance" if method in ("area_search", "close_observation") else method
    descriptor["base_intent"] = "penetration" if method == "intrusion" else group["role"]
    return scene, descriptor, group


class M3bGeometryTests(unittest.TestCase):
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
