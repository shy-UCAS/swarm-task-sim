"""V8-22：监视实测预警进入次数门禁（独立预期：解析圆形预警圈上的手算进入次数）。"""
import unittest
from types import SimpleNamespace as NS

import numpy as np

from v08.runner.joint_monitoring import monitoring_entry_counts


def _track(xs, ys):
    n = len(xs)
    return NS(tau_us=np.arange(n, dtype=np.int64) * 100_000, p=np.c_[xs, ys, np.full(n, 120.0)],
              segment_index=np.zeros(n, np.int64))


class MonitoringEntryCounts(unittest.TestCase):
    def setUp(self):
        W = {"type": "Circle", "center_m": [0.0, 0.0], "radius_m": 1000.0}
        self.ctx = NS(scene={"entities": [{"type": "protection_zone", "facility_id": "f", "layer": "warning",
                                           "geometry": W}]})

    def test_single_entry(self):
        x = np.linspace(-2000, 0, 401)
        r = monitoring_entry_counts(self.ctx, {"a": _track(x, np.zeros_like(x))}, {"a": 0}, "f")
        self.assertEqual(r["members"]["a"]["warning_entry_count"], 1)
        self.assertTrue(r["all_single"])

    def test_cross_then_reenter_counts_two(self):
        # 先横穿预警圈（y = 500 的弦，进 1 次出 1 次），再从外面进入：手算 2 次
        x1 = np.linspace(-2000, 2000, 801)
        x2 = np.linspace(2000, 0, 401)
        xs = np.r_[x1, x2]
        ys = np.r_[np.full_like(x1, 500.0), np.zeros_like(x2)]
        r = monitoring_entry_counts(self.ctx, {"a": _track(xs, ys)}, {"a": 0}, "f")
        self.assertEqual(r["members"]["a"]["warning_entry_count"], 2)
        self.assertFalse(r["all_single"])

    def test_frames_before_release_ignored(self):
        x = np.r_[np.zeros(10), np.linspace(-2000, 0, 401)]       # 释放前停在圈内（中心）
        r = monitoring_entry_counts(self.ctx, {"a": _track(x, np.zeros_like(x))}, {"a": 10 * 100_000}, "f")
        self.assertEqual(r["members"]["a"]["warning_entry_count"], 1)


if __name__ == "__main__":
    unittest.main()
