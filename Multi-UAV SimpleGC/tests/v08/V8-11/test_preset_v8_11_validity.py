"""V8-11 第 2 部分预置测试：实测有效性检查（规划审查方编写，实现方不得修改或删除）。

运行（在 Multi-UAV SimpleGC 目录下，conda 环境 llm）:
    python -B -m unittest discover -s tests/v08/V8-11 -p "test_preset_v8_11_validity.py" -v

独立预期的来源：
- 手算：平行航线的间距恒为横向偏移；对向而过的两机，相对位置在相邻两帧为 (∓0.7, 1.9)，
  采样距离 √(0.7² + 1.9²) ≈ 2.025 m，帧间直线插值的最小距离为 1.9 m（中点）；
- 数学性质：帧间插值最小距离 ≤ 采样最小距离（插值包含两端帧）；
- v0.7 冻结代码的输出：measure_criteria 的 cluster.observed.minimum_separation_m 与
  generation_quality.hard_obstacle_sample_count（所有成员全程可见时应相同）；
- 冻结几何的闭边界约定（task_v07/geometry.py：signed ≤ 0 即在内，不加容差）。
"""
import os
import sys
import unittest
from collections import namedtuple

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from task_v07.criteria_labels import measure_criteria  # noqa: E402
from v08.criteria.validity import VisibleTrack, check_validity, visible_track  # noqa: E402
import synth_v8_11 as syn  # noqa: E402

SCENE = syn.scene()
F = syn.FRAME_US
SV, CV = "separation_violation", "constraint_violation"
Track = namedtuple("Track", "member_id tau_us p")


def straight(member, y, n=50, x0=-500.0, dx=0.8, t0=0):
    x = x0 + dx * np.arange(n)
    return VisibleTrack(member, t0 + np.arange(n, dtype=np.int64) * F, np.c_[x, np.full(n, y), np.full(n, syn.ALT)])


class TestSeparation(unittest.TestCase):

    def test_parallel(self):
        for gap, ok in ((1.9, False), (2.1, True)):
            with self.subTest(gap=gap):
                r = check_validity(SCENE, [straight("a", 500.0), straight("b", 500.0 + gap)])
                self.assertAlmostEqual(r.min_separation_m, gap, places=9)
                self.assertEqual(r.separation_ok, ok)
                self.assertEqual(r.member_min_separation_m, {"a": r.min_separation_m, "b": r.min_separation_m})
                self.assertEqual(r.failures, () if ok else (("a|b", "min_separation", SV),))
                self.assertEqual(r.passed, ok)

    def test_interframe_near_miss(self):
        """采样都 ≥ 2 m、帧间插值 1.9 m：门禁通过（10 Hz 采样口径，r4 6.8），插值只作诊断。"""
        k = np.arange(20)
        xa = 0.35 * (2 * k - 11)
        A = VisibleTrack("a", k.astype(np.int64) * F, np.c_[xa, np.zeros(20), np.full(20, syn.ALT)])
        B = VisibleTrack("b", k.astype(np.int64) * F, np.c_[-xa, np.full(20, 1.9), np.full(20, syn.ALT)])
        r = check_validity(SCENE, [A, B])
        self.assertAlmostEqual(r.min_separation_m, float(np.hypot(0.7, 1.9)), places=9)
        self.assertTrue(r.separation_ok and r.passed)
        self.assertAlmostEqual(r.interp_min_separation_m, 1.9, places=9)
        self.assertEqual(r.interp_closest_pair, ("a", "b", 5 * F))

    def test_interp_not_above_sampled(self):
        rng = np.random.default_rng(20261102)
        for trial in range(20):
            tracks = []
            for m in range(4):
                n = 30
                p = np.cumsum(rng.normal(0, 3, (n, 3)), axis=0) + rng.normal(0, 10, 3)
                tracks.append(VisibleTrack(f"m{m}", (np.arange(n, dtype=np.int64) + int(rng.integers(0, 10))) * F, p))
            r = check_validity(SCENE, tracks)
            self.assertLessEqual(r.interp_min_separation_m, r.min_separation_m + 1e-12)

    def test_visibility_and_offsets(self):
        """未释放的帧不比较；编组出发时刻平移后只在公共帧上比较。"""
        n = 60
        tau = np.arange(n, dtype=np.int64) * F
        pa = np.c_[np.linspace(-20, 20, n), np.zeros(n), np.full(n, syn.ALT)]
        pb = np.c_[np.zeros(n), np.full(n, 1.0), np.full(n, syn.ALT)]       # 静止在 (0, 1)，A 在第 30 帧附近经过
        pb[40:, 1] = 50.0                                                    # 第 40 帧起 B 在 (0, 50)
        A, B = Track("a", tau, pa), Track("b", tau, pb)
        r_all = check_validity(SCENE, [visible_track(A, 0), visible_track(B, 0)])
        self.assertFalse(r_all.separation_ok)                                # B 全程可见：与 A 相距约 1 m
        r_late = check_validity(SCENE, [visible_track(A, 0), visible_track(B, 40 * F)])
        self.assertTrue(r_late.separation_ok)                                # B 第 40 帧才释放
        self.assertEqual(visible_track(B, 40 * F).time_us[0], 40 * F)
        same = straight("a", 0.0, n=50), straight("b", 0.0, n=50, t0=30 * F)
        self.assertAlmostEqual(check_validity(SCENE, list(same)).min_separation_m, 0.8 * 30, places=9)
        apart = straight("a", 0.0, n=50), straight("b", 0.0, n=50, t0=60 * F)
        r = check_validity(SCENE, list(apart))
        self.assertIsNone(r.min_separation_m)
        self.assertTrue(r.separation_ok)
        shifted = visible_track(A, 0, offset_us=7 * F)
        self.assertEqual(int(shifted.time_us[0]), 7 * F)

    def test_matches_v07(self):
        """全员全程可见时，与 v0.7 measure_criteria 的最小间距、限制区帧数相同。"""
        paths = syn.common_grid([syn.sample_path((-900, 350), [("line", (900, 350))], 8.0),
                                 syn.sample_path((-900, 352.5), [("line", (900, 352.5))], 7.9),
                                 syn.sample_path((-300, -1700), [("line", (300, -1400))], 6.0)])
        ids = ["u1", "u2", "u3"]
        t = paths[0][0]
        P = np.stack([p for _, p, _ in paths], axis=1)
        V = np.stack([v for _, _, v in paths], axis=1)
        sk = {"skeleton_id": "syn", "group_id": "g0", "role": "transit", "execution_method": "transit",
              "base_intent": "transit", "target_id": "fac_a", "members": ids,
              "references": {a: {"endpoint_enu_m": [0.0, 0.0, syn.ALT]} for a in ids},
              "terminal_radius_m": 1.0, "terminal_speed_m_s": 0.15}
        labels, _ = measure_criteria(SCENE, sk, {"agent_ids": ids, "time_us": t, "p": P, "v": V,
                                                 "execution_status": "completed"}, "synchronous")
        r = check_validity(SCENE, [VisibleTrack(a, t, P[:, i]) for i, a in enumerate(ids)])
        self.assertEqual(r.min_separation_m, labels["cluster"]["observed"]["minimum_separation_m"])
        for a in ids:
            self.assertEqual(r.member_min_separation_m[a], labels["agents"][a]["observed"]["minimum_separation_m"])
            self.assertEqual(r.restricted_frames[a], labels["agents"][a]["observed"]["hard_obstacle_sample_count"])
        self.assertEqual(sum(r.restricted_frames.values()), labels["generation_quality"]["hard_obstacle_sample_count"])
        self.assertGreater(r.restricted_frames["u3"], 0)                     # u3 穿过限制区
        self.assertEqual(r.codes, (CV,))


class TestRestricted(unittest.TestCase):

    def test_boundary_is_inside(self):
        """恰在限制区边界上（到圆心 100 m）记为进入（闭边界，不加容差）；外 1 cm 不记。"""
        on = VisibleTrack("a", np.array([0], np.int64), np.array([[100.0, -1500.0, syn.ALT]]))
        off = VisibleTrack("b", np.array([0], np.int64), np.array([[100.01, -1500.0, syn.ALT]]))
        r = check_validity(SCENE, [on, off])
        self.assertEqual(r.restricted_frames, {"a": 1, "b": 0})
        self.assertFalse(r.restricted_ok)
        self.assertIn(("a", "restricted_zone", CV), r.failures)

    def test_outside_world_record_only(self):
        far = VisibleTrack("a", np.arange(3, dtype=np.int64) * F, np.array([[3100.0, 0, syn.ALT]] * 3))
        r = check_validity(SCENE, [far])
        self.assertEqual(r.outside_world_frames, {"a": 3})
        self.assertTrue(r.passed)


class TestInputs(unittest.TestCase):

    def test_invalid(self):
        good = straight("a", 0.0)
        with self.assertRaises(ValueError):
            check_validity(SCENE, [good, straight("a", 5.0)])                  # 成员重复
        with self.assertRaises(ValueError):
            check_validity(SCENE, [VisibleTrack("a", good.time_us + 1, good.p)])   # 不在 10 Hz 网格上
        t = good.time_us.copy()
        t[10:] += F
        with self.assertRaises(ValueError):
            check_validity(SCENE, [VisibleTrack("a", t, good.p)])              # 有空洞
        with self.assertRaises(ValueError):
            visible_track(Track("a", good.time_us, good.p), 10 ** 12)          # 释放后没有帧


if __name__ == "__main__":
    unittest.main()
