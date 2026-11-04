"""V8-13c 裁定 2 的执行方自加测试：检查点 2 尝试次数项改为"成功合同中进入优化之后失败的尝试次数中位数 > 0"。
同时补上预置 test_quick_exact_boundaries 因其第 3 条断言（旧口径）失败而未执行到的优化耗时与 P0 两项边界。"""
import unittest

import numpy as np

from v08.runner.joint_report import quick_checkpoint, skeleton_bias, ks_statistic, cramers_v


def row(i, success=True, post=0, skel=0, opt=60.0):
    return dict(contract_id=str(i), facility_count=1 + i % 3, initial_speed_m_s=8.0, group_size=6, success=success,
                attempts=1 + post + skel if success else 20, optimization_s=opt, retained_p0_ok=True,
                post_optimization_failures=post if success else 3, skeleton_failures=skel)


class CheckpointV13c(unittest.TestCase):
    def test_skeleton_retries_do_not_trigger(self):
        rs = [row(i, skel=3) for i in range(20)]        # 旧口径尝试中位数 4 > 1
        got = quick_checkpoint(rs)
        self.assertNotIn("attempts", got["triggered"], "V8-13c 2：骨架构造失败只作诊断")
        self.assertEqual(got["metrics"]["success_attempts_median_diagnostic"], 4)

    def test_post_optimization_median_strict(self):
        rs = [row(i, post=1 if i < 10 else 0) for i in range(20)]   # 中位数 (0+1)/2 = 0.5 > 0
        self.assertIn("attempts", quick_checkpoint(rs)["triggered"])
        rs = [row(i, post=1 if i < 9 else 0) for i in range(20)]    # 中位数 0，不触发
        self.assertNotIn("attempts", quick_checkpoint(rs)["triggered"])

    def test_failed_contracts_not_in_median(self):
        rs = [row(i) for i in range(16)] + [row(16 + i, success=False) for i in range(4)]
        self.assertEqual(quick_checkpoint(rs)["triggered"], [], "16/20 与中位数 0 都不触发")

    def test_missing_field_is_undetermined_not_pass(self):
        rs = [row(i) for i in range(20)]
        del rs[0]["post_optimization_failures"]
        got = quick_checkpoint(rs)
        self.assertTrue(got["metrics"]["attempts_undetermined"])
        self.assertIsNone(got["metrics"]["post_optimization_failures_median"])

    def test_optimization_time_and_p0_boundaries(self):
        # 预置测试中未执行到的两条：60 s 本身不触发、严格大于触发；任何误收触发
        rs = [row(i) for i in range(20)]
        self.assertNotIn("optimization_time", quick_checkpoint(rs)["triggered"])
        for r in rs:
            r["optimization_s"] = np.nextafter(60.0, np.inf)
        self.assertIn("optimization_time", quick_checkpoint(rs)["triggered"])
        rs[0]["retained_p0_ok"] = False
        self.assertIn("retained_p0", quick_checkpoint(rs)["triggered"])

    def test_bias_statistics(self):
        self.assertEqual(ks_statistic([1, 2, 3], [1, 2, 3]), 0.0)
        self.assertEqual(ks_statistic([0, 0], [1, 1]), 1.0)
        self.assertAlmostEqual(cramers_v(["a", "a", "b", "b"], ["a", "a", "b", "b"]), 0.0)
        self.assertAlmostEqual(cramers_v(["a", "a"], ["b", "b"]), 1.0)
        d = {"topology": "loop", "rho0_m": 100.0, "laps": 2.0, "traversals": None, "formation": "column"}
        rs = [dict(row(0), draws=[None, d]), dict(row(1, success=False), draws=[d, d])]
        b = skeleton_bias(rs)
        self.assertEqual(b["counts"]["drawn"], 3)
        self.assertEqual(b["counts"]["kept"], 1)
        self.assertEqual(b["counts"]["attempts_without_draw"], 1)


if __name__ == "__main__":
    unittest.main()
