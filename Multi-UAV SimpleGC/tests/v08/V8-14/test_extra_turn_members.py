"""V8-14 执行方自加测试（第 3 部分）：变队形成员映射、纵向形变单调、排列首通过者的分布。

不是预置测试；预期由解析夹具独立给出。"""
import math
import unittest

import numpy as np

from v08.motion.formation import Reference, formation_slots
from v08.motion.monitoring_turn import (LongitudinalSchedule, choose_joint_turn, collapse_length_m, column_offsets,
                                        derive_deforming_members, longitudinal_schedule)


class _Fam:
    lateral_spacing_m = 15.0


class _Group:
    def __init__(self, n, prior="abreast"):
        self.member_ids = tuple(f"uav_{i:02d}" for i in range(n))
        self.formation_prior = prior


def straight_reference(length, step=0.5):
    s = np.arange(0.0, length + step / 2, step)
    xy = np.stack([s, np.zeros_like(s)], axis=1)
    return Reference(xy, np.zeros_like(s), np.zeros_like(s), s, {}, ())


class MemberMapExtra(unittest.TestCase):
    def setUp(self):
        self.slots = formation_slots(_Group(3), _Fam(), None, formation="abreast", order=("uav_00", "uav_01", "uav_02"))
        self.L = collapse_length_m(np.array([self.slots.offsets[m] for m in self.slots.order]), spacing_m=15.0,
                                   speed_max_m_s=12.0, command_max_m_s=10.0, dynamic_factor=.95,
                                   curvature_limit=.95 * .2 / .5)
        # 解析夹具：直线参考上放一次"掉头"事件（几何无关，只核映射）
        sA = 400.0
        self.ev = {"s_A": sA, "s_B": sA + self.L, "s_D": sA + self.L + 100.0, "s_E": sA + 2 * self.L + 100.0,
                   "L": self.L}
        self.ref = straight_reference(1400.0)

    def test_monotone_maps_and_single_lane_core(self):
        lanes, scheds, l_star = derive_deforming_members(self.ref, self.slots, [self.ev], (50.0, 1300.0),
                                                         spacing_m=0.5, marks=(100.0, 1200.0))
        self.assertEqual(l_star, 15.0, "列队位置 ±15 m、横排 l=0：l* = 15")
        for m, ln in lanes.items():
            self.assertTrue(np.all(np.diff(ln.s_ref) > 0) and np.all(np.diff(ln.s_group) > 0), "对应表严格递增")
            core = (ln.s_ref >= self.ev["s_B"]) & (ln.s_ref <= self.ev["s_D"])
            np.testing.assert_array_equal(ln.lateral_m[core], 0.0, "核心与接回期间横向偏移恰为 0")
            np.testing.assert_array_equal(ln.turn_mask, core, "turn_mask 即 q ∈ [s_B, s_D]")
            np.testing.assert_allclose(ln.xy[core, 1], 0.0, atol=0, err_msg="单车道：所有成员在参考线上")
            far = ln.s_ref < self.ev["s_A"]
            np.testing.assert_allclose(ln.xy[far, 1], ln.d_m, atol=1e-12, err_msg="收拢前保持原横向槽位")

    def test_longitudinal_collapse_done_before_B(self):
        _, scheds, l_star = derive_deforming_members(self.ref, self.slots, [self.ev], (50.0, 1300.0), spacing_m=0.5)
        lcol = column_offsets(3, 15.0)
        for i, m in enumerate(self.slots.order):
            ls = scheds[m]
            s_done = self.ev["s_B"] - l_star
            self.assertAlmostEqual(float(ls(s_done)), lcol[i], places=12, msg="到 B 之前沿迹已收为纵列")
            self.assertLessEqual(float(ls.q(s_done)), self.ev["s_B"] + 1e-9, "任何成员到 B 前完成收拢")
            s = np.linspace(0.0, 1400.0, 28001)
            self.assertTrue(np.all(np.diff(ls.q(s)) > 0), "1 + l'(s) > 0：L ≥ 1.5Δl 严格上取整")

    def test_schedule_inverse(self):
        ls = longitudinal_schedule(0.0, 15.0, [self.ev], 15.0)
        q = np.linspace(10.0, 1300.0, 997)
        s = ls.inverse(q, 30.0)
        np.testing.assert_allclose(ls.q(s), q, rtol=0, atol=1e-9, err_msg="二分反函数")


class PermutationFirstPassExtra(unittest.TestCase):
    def test_first_pass_of_uniform_permutation_is_uniform(self):
        """裁定 4：均匀随机排列中第一个可行元素在可行集合上均匀。小格 20 个元素、可行 {3, 7, 11, 19}。"""
        feas = {3, 7, 11, 19}
        counts = dict.fromkeys(feas, 0)
        rng = np.random.default_rng(20261104)
        n = 40000
        for _ in range(n):
            for idx in rng.permutation(20).tolist():
                if idx in feas:
                    counts[idx] += 1
                    break
        for k, c in counts.items():
            self.assertLess(abs(c / n - .25), .01, f"元素 {k} 频率 {c / n}，应接近 1/4")

    def test_choose_uniform_over_nonempty_combos(self):
        recs = [dict(kind="u", side=1, id=0), dict(kind="u", side=-1, id=1), dict(kind="teardrop", side=1, id=2)]

        class R:
            def __init__(self, seq):
                self.seq = list(seq)

            def integers(self, lo, hi=None, size=None):
                v = self.seq.pop(0)
                assert lo <= v < hi
                return v

        self.assertEqual(choose_joint_turn(recs, R([2, 0]))["id"], 2, "每个非空组合各一条记录：先等概率选组")


if __name__ == "__main__":
    unittest.main()
