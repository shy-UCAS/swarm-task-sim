"""V8-16 预置；未经运行。纯数值/文件协议，不导入 shapely 或真实场景。"""
import copy
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from v08.motion.transit_numeric import grid_error_m, curve_lp
from v08.runner.joint_report import quick_checkpoint, full_checkpoint, attempt_counters
from v08.runner.skeleton_monitoring import skeleton_checkpoint
from v08.runner.joint_monitoring import compare_dirs

# HiGHS 默认 primal feasibility=1e-7（已核对 _linprog_highs.py）。
# LP 的 x/y 同除20m，故原单位位置容差20e-7；这是测试容差，不是物理门禁容差。
LP_TOL = 1e-7
LENGTH = 20.0


def row(i, ok=True, attempts=1):
    return dict(contract_id=f"c{i:03d}", success=ok, attempts=attempts,
                group_size=2, facility_count=1, initial_speed_m_s=5.0,
                shape_audit_failed_attempts=0, optimization_s=60.0,
                post_optimization_failures=0, skeleton_failures=0,
                retained_p0_ok=True)


class NumericPreset(unittest.TestCase):
    def test_grid_error(self):
        e = grid_error_m(5.0, 5.0, 2.0)
        # 独立预期：5m方格半对角线与5x2m矩形半对角线的勾股公式。
        self.assertEqual(e["field_eps_m"], math.hypot(5.0, 5.0) / 2.0)
        self.assertEqual(e["sampling_q_m"], math.hypot(2.5, 1.0))
        # 独立预期：弦上相邻5m点的最近点距离上界=2.5m。
        self.assertEqual(grid_error_m(5.0, 5.0)["sampling_q_m"], 2.5)

    def test_lp_constant_corridor(self):
        x = np.arange(0.0, 205.0, 5.0)
        bound = np.full(x.shape, 7.0)
        got = curve_lp(x, bound, bound, 7.0, np.zeros(4), D_m=0.0)
        # 独立预期：lo=hi=h使唯一可行函数为常数7，解析可行，不来自待测输出。
        self.assertTrue(got["feasible"])
        sp = got["spline"]
        np.testing.assert_allclose(sp(x), 7.0, rtol=0, atol=LENGTH * LP_TOL)
        np.testing.assert_allclose(sp(x, 1), 0.0, rtol=0, atol=LP_TOL)
        np.testing.assert_allclose(sp(x, 2), 0.0, rtol=0, atol=LP_TOL / LENGTH)

    def test_lp_corridor_slope_curvature_and_nontrivial_target(self):
        x = np.arange(0.0, 205.0, 5.0)
        lo, hi = np.full(x.shape, -40.0), np.full(x.shape, 40.0)
        D = 20.0  # 手工夹具车道半跨，不是生产新增参数。
        got = curve_lp(x, lo, hi, 0.0, np.full(4, 2.0), D_m=D)
        # 独立预期：常数0满足全部约束，故LP可行。
        self.assertTrue(got["feasible"])
        sp = got["spline"]
        q = np.linspace(0.0, 200.0, 401)  # 0.5m测试点距，来源既有curve_spacing_m。
        y, dy, ddy = sp(q), sp(q, 1), sp(q, 2)
        # 独立预期：手工常宽走廊、U D.3.5四条线性约束及其曲率推导。
        self.assertLessEqual(float(np.max(y)), 40.0 + LENGTH * LP_TOL)
        self.assertGreaterEqual(float(np.min(y)), -40.0 - LENGTH * LP_TOL)
        np.testing.assert_allclose(sp([0.0, 200.0]), 0.0,
                                   rtol=0, atol=LENGTH * LP_TOL)
        np.testing.assert_allclose(sp([0.0, 200.0], 1), 0.0,
                                   rtol=0, atol=LP_TOL)
        self.assertLessEqual(float(np.max(np.abs(dy))),
                             math.tan(math.radians(75)) + LP_TOL)
        cap = min(0.38 / (1 + 0.38 * D), 1 / (15.75 + D))
        self.assertLessEqual(float(np.max(np.abs(ddy))), cap + LP_TOL / LENGTH)
        k = ddy / (1 + dy * dy) ** 1.5
        self.assertLessEqual(float(np.max(np.abs(k))), cap + LP_TOL / LENGTH)
        # 常数logit=2经过正基和=1，目标解析为-40+80/(1+exp(-2))。
        target = -40.0 + 80.0 / (1.0 + math.exp(-2.0))
        np.testing.assert_allclose(got["target_m"], target,
                                   rtol=0, atol=LENGTH * LP_TOL)
        # 独立预期：两端0、内部很小正控制值是可行改进方向，L1必小于全零直线。
        self.assertLess(float(np.abs(sp(x) - target).sum()),
                        float(np.full(x.shape, abs(target)).sum()))

    def test_lp_infeasible_returns_same_line(self):
        x = np.arange(0.0, 45.0, 5.0)
        got = curve_lp(x, np.full(x.shape, 2.0), np.full(x.shape, 1.0),
                       0.0, np.zeros(4), D_m=0.0)
        # 独立预期：lo>hi无解；U D.3.5只允许本弦h=0回退，不重抽。
        self.assertFalse(got["feasible"])
        self.assertIsNotNone(got["fallback_reason"])
        np.testing.assert_array_equal(got["spline"](x), np.zeros_like(x))

    def test_no_revisit_slope_proof(self):
        # 手算：同高、x跨度30m的最坏V形折线，两边斜率为±3.73。
        s = 3.73
        x = np.linspace(0.0, 30.0, 61)
        y = s * np.minimum(x, 30.0 - x)
        farthest = float(np.linalg.norm(np.c_[x, y], axis=1).max())
        bound = 30.0 * math.sqrt(1.0 + s * s)
        # 独立预期：U D.3.5重访必要条件150m与解析Lipschitz上界。
        self.assertLess(s, math.sqrt(24.0))
        self.assertLess(bound, 150.0)
        self.assertLessEqual(farthest, bound)
        self.assertLess(farthest, 150.0)
        self.assertEqual(float(np.hypot(x[-1], y[-1])), 30.0)
        self.assertLess(30.0 / math.cos(math.radians(75.0)), 150.0)

    def test_checkpoint_boundaries(self):
        sk = [row(i, ok=i < 190) for i in range(200)]
        # 独立预期：190/200=95%，严格小于才触发U D.5。
        self.assertNotIn("success_rate", skeleton_checkpoint(sk)["triggered"])
        sk[189]["success"] = False
        self.assertIn("success_rate", skeleton_checkpoint(sk)["triggered"])
        sk = [row(i) for i in range(200)]
        for r in sk[:10]:
            r["shape_audit_failed_attempts"] = 1
        # 独立预期：10/200=5%不触发，11/200>5%触发。
        self.assertNotIn("shape_audit", skeleton_checkpoint(sk)["triggered"])
        sk[10]["shape_audit_failed_attempts"] = 1
        self.assertIn("shape_audit", skeleton_checkpoint(sk)["triggered"])
        q = [row(i, ok=i < 16) for i in range(20)]
        # 独立预期：16/20且优化中位数恰60均不触发U D.6。
        self.assertEqual(quick_checkpoint(q)["triggered"], [])
        q[15]["success"] = False
        self.assertIn("success_rate", quick_checkpoint(q)["triggered"])
        for r in q:
            r["optimization_s"] = np.nextafter(60.0, np.inf)
        self.assertIn("optimization_time", quick_checkpoint(q)["triggered"])

    def test_gap_and_attempt_objects(self):
        rs = [row(i, ok=i >= 2) for i in range(20)]
        for r in rs[10:]:
            r["group_size"] = 8
        # 独立预期：总体90%，第一档80%，差恰10pp不触发；改成3失败则差15pp。
        self.assertNotIn("group_gap", skeleton_checkpoint(rs, expected_count=20)["triggered"])
        rs[2]["success"] = False
        self.assertIn("group_gap", skeleton_checkpoint(rs, expected_count=20)["triggered"])
        # 独立预期：U明确只统计失败且已经进入优化的attempt。
        cnt = attempt_counters([
            {"ok": False, "stage": "skeleton", "optimization_entered": False},
            {"ok": False, "stage": "exception", "optimization_entered": True},
            {"ok": True, "stage": "verified", "optimization_entered": True},
            {"ok": False, "stage": "exception", "optimization_entered": None},
        ])
        self.assertEqual(cnt, dict(post_optimization_failures=1,
                                   skeleton_failures=1, unknown_attempts=1))
        q = [row(i, attempts=20) for i in range(20)]
        # 骨架曾重做但post=0：不能误用总attempts中位数当quick止损。
        self.assertNotIn("attempts", quick_checkpoint(q)["triggered"])
        for r in q:
            r["post_optimization_failures"] = 1
        self.assertIn("attempts", quick_checkpoint(q)["triggered"])

    def test_full_frechet_boundaries(self):
        rs = [row(i, ok=i < 160) for i in range(200)]
        blocks = [{"spacing_m": 10.0, "distances_m": [10.0]}]
        # 独立预期：80%与归一Fréchet=1在严格边界上均不触发。
        self.assertEqual(full_checkpoint(rs, blocks)["triggered"], [])
        blocks[0]["distances_m"] = [np.nextafter(10.0, 0.0)]
        self.assertIn("frechet", full_checkpoint(rs, blocks)["triggered"])
        rs[159]["success"] = False
        self.assertIn("success_rate", full_checkpoint(rs, blocks)["triggered"])

    def test_contract_comparison_excludes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a", Path(d) / "b"
            a.mkdir()
            b.mkdir()
            for root in (a, b):
                (root / "result.json").write_bytes(b'{"success":true}\n')
                (root / "failure_witness.json").write_bytes(b'{"x":1}\n')
            # 独立预期：原始bytes恒等；失败见证也是合同载荷，不得排除。
            self.assertTrue(compare_dirs(a, b)["bytes_equal"])
            (b / "failure_witness.json").write_bytes(b'{"x":2}\n')
            self.assertFalse(compare_dirs(a, b)["bytes_equal"])
            self.assertEqual(compare_dirs(a, b)["differing"], ["failure_witness.json"])
            (b / "extra.txt").write_bytes(b"x")
            self.assertFalse(compare_dirs(a, b)["file_sets_equal"])


if __name__ == "__main__":
    unittest.main()
