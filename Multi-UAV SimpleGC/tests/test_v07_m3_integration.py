"""M3a output integration and fail-closed default backend regression tests."""
from copy import deepcopy
import random
import unittest
from unittest.mock import patch

from v07_m3_fixtures import request
from v07_m1_fixtures import trajectory, polyline, hold
from task_v07.expansion.contracts import PlannerUnavailable, P0ContractError
from task_v07.expansion.group_candidate_pool import build_group_pool
from task_v07.expansion.pipeline import COMMON_CONSTANTS
from task_v07.unified.rehearsal import evaluate_solos
from task_v07.unified.spec import build_spec
from task_v07.unified.free_space import free_space, work_region
from task_v07.unified.shapes import draw_shape
from task_v07.unified.route import GeometryRejected


class UnifiedIntegrationTests(unittest.TestCase):
    def test_G11_default_dispatch_is_unified_and_legacy_is_explicit(self):
        with patch("task_v07.unified.adapter.build_unified_pool", return_value=([], {})) as new, \
             patch("task_v07.expansion.group_candidate_pool._build_legacy_group_pool", return_value=([], {})) as old:
            build_group_pool({}, {}, {})
            new.assert_called_once_with({}, {}, {}, 200)
            old.assert_not_called()
            build_group_pool({}, {}, {}, backend="legacy")
            old.assert_called_once()
            with self.assertRaises(ValueError):
                build_group_pool({}, {}, {}, backend="automatic")

    def test_G11_unsupported_and_P0_are_not_swallowed(self):
        scene, d, g = request()
        g["role"] = g["execution_method"] = "unsupported_method"
        with patch("task_v07.expansion.group_candidate_pool.Context", side_effect=AssertionError("legacy Context")), \
             patch("task_v07.expansion.continuous_geometry.draw_role", side_effect=AssertionError("legacy draw")):
            with self.assertRaises(PlannerUnavailable):
                build_group_pool(scene, d, g)
        scene, d, g = request()
        with patch("task_v07.unified.adapter.build_spec", side_effect=P0ContractError("identity changed")):
            with self.assertRaises(P0ContractError):
                build_group_pool(scene, d, g)

    def test_G2_G7_G8_transit_routes_survive_column_permutation_and_feed_M2(self):
        scene, d, g = request(count=2)
        with patch("task_v07.expansion.group_candidate_pool.Context", side_effect=AssertionError("legacy Context")), \
             patch("task_v07.expansion.group_candidate_pool.draw_role", side_effect=AssertionError("legacy draw")):
            pool, report = build_group_pool(scene, d, g, budget=6)
            self.assertTrue(pool, report["rejection_reasons"])
            changed = deepcopy(d); changed["agent_ids"].reverse(); changed["column_seed"] += 1
            other, _ = build_group_pool(scene, changed, changed["task_groups"][0], budget=6)
        self.assertEqual([c["index"] for c in pool], [c["index"] for c in other])
        for a, b in zip(pool, other):
            self.assertEqual(a["bundle"].waypoints_by_agent, b["bundle"].waypoints_by_agent)
            self.assertEqual(b["skeleton"]["agent_ids"], changed["agent_ids"])
        chosen = pool[0]; sk = chosen["skeleton"]
        for field in ("terminal_radius_m", "terminal_speed_m_s", "terminal_hold_s"):
            self.assertEqual(sk[field], COMMON_CONSTANTS[field])
        solos = {}
        for agent, points in chosen["bundle"].waypoints_by_agent.items():
            xy = [p[:2] for p in points]
            solos[agent] = trajectory([*polyline(xy, d["cruise_speed_m_s"]), hold(xy[-1], 3.)], agent)
        rehearsal = evaluate_solos(scene, sk, solos)
        self.assertEqual(rehearsal["status"], "passed", rehearsal["failures"])

    def test_G8_straight_bend_and_multi_are_real_shapes(self):
        seen = set()
        for multi in (False, True):
            scene, d, g = request(multi=multi, count=4)
            spec = build_spec(d, g); free = free_space(scene, spec)
            for seed in range(12):
                try:
                    shape = draw_shape(spec, work_region(scene, spec, free), random.Random(seed), free)
                except GeometryRejected:
                    continue
                seen.add((multi, shape["draw"]["bend"]))
                self.assertTrue(all(len(s["work"]) == (3 if shape["draw"]["bend"] else 2) for s in shape["slots"]))
        self.assertEqual(seen, {(False, False), (False, True), (True, False), (True, True)})


if __name__ == "__main__":
    unittest.main()
