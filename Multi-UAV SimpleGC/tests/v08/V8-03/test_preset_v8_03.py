"""V8-03 预置测试（规划审查方编写，实现方不得修改或删除）。

运行（在 Multi-UAV SimpleGC 目录下）:
    python -B -m unittest discover -s tests/v08/V8-03 -p "test_preset_*.py" -v

独立预期的来源：
- 划分：冻结规则 task_v07/s3/split.py（main@bb262b3）的定义，由规划审查方在云端另行计算；
- 排序键、抽样键：SHA256 的定义值，由规划审查方在云端另行计算；
- 成员对照：人工构造的数组，预期值按构造方式手算得到。
"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "scripts", "v08"))
sys.path.insert(0, SCRIPTS)

import v8_03_offline_check as m  # noqa: E402

STEP = 100000


def grid(n):
    return np.arange(n, dtype=np.int64) * STEP


def solo_track(n):
    k = np.arange(n, dtype=float)
    p = np.stack([k, 2.0 * k, np.full(n, 0.5)], axis=1)          # (n, 3)
    v = np.stack([np.ones(n), 2.0 * np.ones(n), np.zeros(n)], axis=1)
    return grid(n), p, v


class TestSplitAndKeys(unittest.TestCase):
    def test_family_split_known_values(self):
        # u 值（规划审查方计算）：0.36510 / 0.28827 / 0.81367 / 0.80440；test 一例
        self.assertEqual(m.family_split("family_s15_9b1a9f5a704a5a43"), "train")
        self.assertEqual(m.family_split("family_s15_38bedc9d791d547b"), "train")
        self.assertEqual(m.family_split("family_s15_1b876e6b8b6f70c6"), "val")
        self.assertEqual(m.family_split("family_s15_3de8b14ca62da9ba"), "val")
        self.assertEqual(m.family_split("family_s15_000c023ef4f18b63"), "test")

    def test_devset_order_key(self):
        self.assertEqual(m.devset_order_key("fam_a")[:8], "0b368a7c")
        self.assertEqual(m.devset_order_key("fam_b")[:8], "d2bfb485")

    def test_select_devset_takes_smallest_keys(self):
        fake = ["fam_b", "fam_d", "fam_e", "fam_c", "fam_a"]
        self.assertEqual(m.select_devset(fake, k=3), ["fam_a", "fam_c", "fam_e"])

    def test_select_devset_rejects_duplicates_and_short_lists(self):
        with self.assertRaises(ValueError):
            m.select_devset(["fam_a", "fam_a", "fam_b"], k=2)
        with self.assertRaises(ValueError):
            m.select_devset(["fam_a"], k=2)

    def test_sample_key(self):
        self.assertEqual(
            m.sample_key("family_s15_1547cdeafffd4a5a_ext_005_regular_synchronous"),
            "01015670136e8f079730716dec3186ba91df2cd181c35f640f4cccbb3d656542")


class TestCompareMember(unittest.TestCase):
    def setUp(self):
        self.n = 50
        self.st, self.sp, self.sv = solo_track(self.n)

    def joint_from_solo(self, shift_frames, tail_frames, tail_offset=(0.0, 0.0, 0.0)):
        """按定义构造联合轨迹：t 时刻 = 单机 (t − 延迟) 时刻；单机记录结束后附加 tail_frames 帧。"""
        n_in = self.n + shift_frames
        idx = np.maximum(0, np.arange(n_in) - shift_frames)
        p = self.sp[idx].copy()
        v = self.sv[idx].copy()
        tail_p = np.repeat(self.sp[-1:] + np.asarray(tail_offset), tail_frames, axis=0)
        tail_v = np.zeros((tail_frames, 3))
        return grid(n_in + tail_frames), np.vstack([p, tail_p]), np.vstack([v, tail_v])

    def test_zero_delay_identical(self):
        jt, jp, jv = self.joint_from_solo(0, 0)
        r = m.compare_member(jt, jp, jv, self.st, self.sp, self.sv, 0.0)
        self.assertEqual(r["in_window_frames"], self.n)
        self.assertEqual(r["post_end_frames"], 0)
        self.assertEqual(r["pos_err_max_m"], 0.0)
        self.assertEqual(r["vel_err_max_m_s"], 0.0)
        self.assertEqual(r["full_pos_err_max_m"], 0.0)
        self.assertIsNone(r["post_end_disp_max_m"])

    def test_shift_and_post_end(self):
        # 延迟 3.0 s = 30 帧；单机结束后再 10 帧，位置偏 0.3 m
        jt, jp, jv = self.joint_from_solo(30, 10, (0.3, 0.0, 0.0))
        r = m.compare_member(jt, jp, jv, self.st, self.sp, self.sv, 3.0)
        self.assertEqual(r["in_window_frames"], self.n + 30)
        self.assertEqual(r["pos_err_max_m"], 0.0)
        self.assertEqual(r["post_end_frames"], 10)
        self.assertAlmostEqual(r["post_end_disp_max_m"], 0.3, places=12)
        self.assertAlmostEqual(r["full_pos_err_max_m"], 0.3, places=12)

    def test_frames_before_release_use_first_solo_sample(self):
        jt, jp, jv = self.joint_from_solo(30, 0)
        jp[5] = jp[5] + np.array([0.0, 0.0, 0.2])     # 释放前的第 5 帧，应与单机第 0 帧比较
        r = m.compare_member(jt, jp, jv, self.st, self.sp, self.sv, 3.0)
        self.assertAlmostEqual(r["pos_err_max_m"], 0.2, places=12)

    def test_in_window_perturbation(self):
        jt, jp, jv = self.joint_from_solo(30, 10)
        jp[35] = jp[35] + np.array([0.0, 0.1, 0.0])
        jv[40] = jv[40] + np.array([0.0, 0.0, 0.05])
        r = m.compare_member(jt, jp, jv, self.st, self.sp, self.sv, 3.0)
        self.assertAlmostEqual(r["pos_err_max_m"], 0.1, places=12)
        self.assertAlmostEqual(r["vel_err_max_m_s"], 0.05, places=12)
        self.assertEqual(r["post_end_disp_max_m"], 0.0)

    def test_full_error_matches_clamped_interpolation(self):
        # full_pos_err_max_m 必须等于冻结代码 solo_spacing.prediction_error 的口径：
        # 对全部联合帧，用 np.interp(t − 延迟, 单机时间, 单机位置) 两端截断后求误差最大值
        jt, jp, jv = self.joint_from_solo(30, 10, (0.0, 0.4, 0.0))
        jp[12] = jp[12] + np.array([0.05, 0.0, 0.0])
        r = m.compare_member(jt, jp, jv, self.st, self.sp, self.sv, 3.0)
        ref = np.stack([np.interp(jt - 3000000, self.st, self.sp[:, k]) for k in range(3)], axis=1)
        expected = float(np.linalg.norm(jp - ref, axis=1).max())
        self.assertAlmostEqual(r["full_pos_err_max_m"], expected, places=12)
        self.assertAlmostEqual(expected, 0.4, places=12)

    def test_delay_off_grid_raises(self):
        jt, jp, jv = self.joint_from_solo(0, 0)
        with self.assertRaises(ValueError):
            m.compare_member(jt, jp, jv, self.st, self.sp, self.sv, 0.05)

    def test_bad_time_axis_raises(self):
        jt, jp, jv = self.joint_from_solo(0, 0)
        with self.assertRaises(ValueError):
            m.compare_member(jt + STEP, jp, jv, self.st, self.sp, self.sv, 0.0)
        bad = jt.copy()
        bad[7] += 1
        with self.assertRaises(ValueError):
            m.compare_member(bad, jp, jv, self.st, self.sp, self.sv, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
