import unittest
import numpy as np
from v08.runner.joint_report import (
    quick_checkpoint, full_checkpoint, pooled_frechet, speed_bin, group_bin,
)


def row(i, success=True, speed=8., size=6):
    return dict(contract_id=str(i), facility_count=1+i % 3,
                initial_speed_m_s=speed, group_size=size, success=success,
                attempts=1 if success else 20, optimization_s=60.,
                retained_p0_ok=True)


class CheckpointPreset(unittest.TestCase):
    def test_quick_exact_boundaries(self):
        rs = [row(i, i < 16) for i in range(20)]
        for r in rs:
            r["post_optimization_failures"] = 0
        self.assertEqual(quick_checkpoint(rs)["triggered"], [],
                         "U14 D.4/C13：16/20、post失败median=0、60s均不触发")
        rs[15]["success"] = False
        self.assertIn("success_rate", quick_checkpoint(rs)["triggered"],
                      "独立计数15/20严格小于16/20")
        rs = [row(i) for i in range(20)]
        for r in rs:
            r["attempts"] = 2
            r["post_optimization_failures"] = 0
        self.assertNotIn("attempts", quick_checkpoint(rs)["triggered"],
                         "U14授权修订：总尝试2但首次进入优化成功，不触发")
        for r in rs:
            r["post_optimization_failures"] = 1
        self.assertIn("attempts", quick_checkpoint(rs)["triggered"],
                      "C13独立计数：成功合同post失败median=1>0")
        for r in rs:
            r["post_optimization_failures"] = 0
            r["optimization_s"] = np.nextafter(60., np.inf)
        self.assertIn("optimization_time", quick_checkpoint(rs)["triggered"],
                      "原阈值不变：最小可表示的严格大于60")
        rs[0]["retained_p0_ok"] = False
        self.assertIn("retained_p0", quick_checkpoint(rs)["triggered"],
                      "原P0门禁不变：任何误收段")

    def test_pooled_not_per_family_and_no_success_quota(self):
        blocks = [
            dict(spacing_m=10., distances_m=[5.], attempted=10, success=2),
            dict(spacing_m=20., distances_m=[40.]*36, attempted=10, success=9),
        ]
        self.assertEqual(pooled_frechet(blocks), 2.,
                         "C12：合并37个归一配对的中位数，不按最差族")
        rs = [row(i) for i in range(200)]
        self.assertNotIn("frechet", full_checkpoint(rs, blocks)["triggered"],
                         "U A.3：9/10成功照常统计，不要求凑满N")
        low = [dict(spacing_m=10., distances_m=[5.]*36, attempted=10, success=9)]
        self.assertIn("frechet", full_checkpoint(rs, low)["triggered"],
                      "归一合并中位数0.5<1")
        edge = [dict(spacing_m=10., distances_m=[10.], attempted=10, success=2)]
        self.assertNotIn("frechet", full_checkpoint(rs, edge)["triggered"],
                         "恰好1不触发")
        self.assertIsNone(pooled_frechet([]), "无配对报告N/A，不编造0或强制补种子")

    def test_speed_and_size_bin_edges(self):
        for v, b in [(4., 0), (6., 1), (8., 2), (10., 2)]:
            self.assertEqual(speed_bin(v), b, "U D.4：[4,6)、[6,8)、[8,10]")
        for n, b in [(1, 0), (4, 0), (5, 1), (8, 1), (9, 2), (12, 2)]:
            self.assertEqual(group_bin(n), b, "U D.4：1–4、5–8、9–12")

    def test_twenty_percentage_points_is_strict(self):
        # 手算：总160/200=.8；低速/小组6/10=.6，恰差.2。
        rs = [row(i, i < 6, speed=4., size=1) for i in range(10)]
        rs += [row(10+i, i < 154, speed=8., size=9) for i in range(190)]
        got = full_checkpoint(rs, [])["triggered"]
        self.assertNotIn("success_rate", got, "160/200恰为80%")
        self.assertNotIn("speed_gap", got, "Fraction比较：差20个百分点本身不触发")
        self.assertNotIn("group_gap", got, "同上，按实际编组人数")
        rs[0]["success"] = False
        rs[-1]["success"] = True  # 总数仍160，低速/小组降到5/10
        got = full_checkpoint(rs, [])["triggered"]
        self.assertIn("speed_gap", got, ".8-.5=.3>.2")
        self.assertIn("group_gap", got, ".8-.5=.3>.2")

    def test_failed_contracts_count_in_denominator(self):
        rs = [row(i, i < 159) for i in range(200)]
        self.assertIn("success_rate", full_checkpoint(rs, [])["triggered"],
                      "最终159/200<80%，不能只在优化成功子集中算")


if __name__ == "__main__":
    unittest.main()
