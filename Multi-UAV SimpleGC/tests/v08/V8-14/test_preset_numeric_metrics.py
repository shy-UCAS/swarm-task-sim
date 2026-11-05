import unittest
import numpy as np

from v08.runner.joint_report import (
    attempt_counters, quick_checkpoint, full_checkpoint, pooled_frechet,
)
from v08.runner.skeleton_monitoring import skeleton_checkpoint
from v08.diagnostics.monitoring_skeleton import patrol_resample, phase_metrics


def row(i, success=True, attempts=1, size=6):
    return dict(contract_id=str(i), success=success, attempts=attempts,
                group_size=size, facility_count=1, initial_speed_m_s=8.,
                shape_audit_failed_attempts=0, optimization_s=60.,
                retained_p0_ok=True, post_optimization_failures=0,
                skeleton_failures=max(0, attempts-1))


class MetricsPreset(unittest.TestCase):
    def test_postoptimization_counts_entry_event_not_stage_or_walltime(self):
        records = [
            dict(ok=False, stage="skeleton", optimization_entered=False),
            dict(ok=False, stage="exception", optimization_entered=False),
            dict(ok=False, stage="optimize", optimization_entered=True),
            dict(ok=False, stage="simulation", optimization_entered=True),
            dict(ok=False, stage="verify_segments", optimization_entered=True),
            dict(ok=True, stage="verified", optimization_entered=True),
        ]
        got = attempt_counters(records)
        self.assertEqual(got["post_optimization_failures"], 3,
                         "C13/U D.4：仅3个已进入优化的失败，成功不计")
        self.assertEqual(got["skeleton_failures"], 1,
                         "只有明确skeleton失败，不能把未知异常伪装成随机失败")
        self.assertEqual(got["unknown_attempts"], 1,
                         "未入优化的exception需另报，不能由stage!=skeleton误计")

    def test_quick_and_full_use_same_post_count(self):
        rs = [row(i, attempts=20) for i in range(200)]
        self.assertNotIn("attempts", quick_checkpoint(rs[:20])["triggered"],
                         "骨架19次失败、首次进入优化成功，中位数post=0")
        self.assertNotIn("attempts", full_checkpoint(rs, [])["triggered"],
                         "全量必须同步，不再用总attempts>1")
        for r in rs:
            r["post_optimization_failures"] = 1
        self.assertIn("attempts", quick_checkpoint(rs[:20])["triggered"],
                      "成功合同post失败中位数1>0")
        self.assertIn("attempts", full_checkpoint(rs, [])["triggered"],
                      "同一口径必须传递到全量")
        missing = [row(i) for i in range(20)]
        del missing[0]["post_optimization_failures"]
        self.assertTrue(quick_checkpoint(missing)["metrics"]["attempts_undetermined"],
                        "缺字段是未完成，不以0冒充正确实现")
        self.assertTrue(full_checkpoint(missing, [])["metrics"]["attempts_undetermined"],
                        "U D.4所有出现处同步：全量也不能把缺测当0")

    def test_skeleton_success_and_group_strict_boundaries(self):
        rs = [row(i, i < 190) for i in range(200)]
        self.assertNotIn("success_rate", skeleton_checkpoint(rs)["triggered"],
                         "U D.5：190/200恰95%")
        rs[189]["success"] = False
        self.assertIn("success_rate", skeleton_checkpoint(rs)["triggered"],
                      "189/200低于95%，失败合同仍在分母")
        # 独立手算：低档17/20=.85，其他173/180，总190/200=.95。
        rs = [row(i, i < 17, size=3) for i in range(20)]
        rs += [row(20+i, i < 173, size=10) for i in range(180)]
        self.assertNotIn("group_gap", skeleton_checkpoint(rs)["triggered"],
                         "95%-85%恰10个百分点不触发")
        rs[0]["success"] = False
        rs[-1]["success"] = True
        self.assertIn("group_gap", skeleton_checkpoint(rs)["triggered"],
                      "总率仍95%，低档16/20=80%，差15个百分点")

    def test_skeleton_attempt_and_shape_denominators(self):
        rs = [row(i) for i in range(200)]
        self.assertEqual(skeleton_checkpoint(rs)["triggered"], [],
                         "正确合成场景：200成功、首次即成、shape失败0")
        for r in rs[100:]:
            r["attempts"] = 2
        self.assertIn("attempts", skeleton_checkpoint(rs)["triggered"],
                      "成功骨架中位数(1+2)/2=1.5>1")
        rs = [row(i, attempts=10) for i in range(200)]
        for r in rs[:100]:
            r["shape_audit_failed_attempts"] = 1
        self.assertNotIn("shape_audit", skeleton_checkpoint(rs)["triggered"],
                         "100/2000恰5%；分母不是200合同或复核数")
        rs[100]["shape_audit_failed_attempts"] = 1
        self.assertIn("shape_audit", skeleton_checkpoint(rs)["triggered"],
                      "101/2000>5%，仍每attempt至多计一次")
        self.assertFalse(skeleton_checkpoint(rs[:-1])["complete"],
                         "199条不能冒充U的200合同完成")

    def test_patrol_clipping_excludes_extreme_endpoints(self):
        s = np.array([0., 100., 110., 120., 220.])
        a = np.array([[-100., 0.], [0., 0.], [10., 0.], [20., 0.], [120., 0.]])
        b = a.copy()
        b[0] = [-1000., 700.]
        b[-1] = [900., -700.]
        pa = patrol_resample(s, a, 100., 120., spacing_m=5.)
        pb = patrol_resample(s, b, 100., 120., spacing_m=5.)
        expected = np.column_stack((np.arange(0., 21., 5.), np.zeros(5)))
        np.testing.assert_array_equal(pa, expected,
                                      err_msg="直线解析裁切[0,20]、5m采样含两端")
        np.testing.assert_array_equal(pb, expected,
                                      err_msg="修改巡逻外起终点不得改变巡逻路径")
        stretched = a.copy()
        stretched[1:4, 0] = [0., 20., 40.]
        ps = patrol_resample(s, stretched, 100., 120., spacing_m=5.)
        np.testing.assert_array_equal(ps[:, 0], np.arange(0., 41., 5.),
                                      err_msg="优化后长度40m，应按自己的弧长有9点，不能沿用before的5点")
        # 合并不是分族中位数，且无需10/10成功。
        blocks = [dict(spacing_m=10., distances_m=[5.], success=2, attempted=10),
                  dict(spacing_m=20., distances_m=[40.]*36, success=9, attempted=10)]
        self.assertEqual(pooled_frechet(blocks), 2.,
                         "独立排序：37对中第19个为2，不按最差族")
        self.assertIsNone(pooled_frechet([]), "无配对为N/A，不造零")

    def test_phase_ratio_and_along_projection(self):
        t = np.arange(3, dtype=float)
        p = np.column_stack((2*t, np.zeros(3)))
        v = np.tile([2., 0.], (3, 1))
        tangent = np.tile([1., 0.], (3, 1))
        got = phase_metrics(t, p, v, p+[3., 4.], v,
                            p+[-2., 100.], v/2, {"patrol": (0., 2.)}, tangent)["patrol"]
        self.assertEqual(got["measured_ratio"], .5, "独立解析：1m/s÷2m/s")
        self.assertEqual(got["optimized_ratio"], 1., "独立解析：参考与优化速度相同")
        self.assertEqual(got["optimized_along_max_m"], 3.,
                         "沿迹为x投影3，不是欧氏距离5")
        self.assertEqual(got["measured_along_max_m"], 2.,
                         "横向100m不混入沿迹诊断")
        v[-1] = 0.
        zero = phase_metrics(t, p, v, p, v, p, v,
                             {"patrol": (0., 2.)}, tangent)["patrol"]
        self.assertEqual(zero["measured_ratio"], 1.0,
                         "V8-14b 3.3/裁定7：只统计参考速度≥0.5m/s的样本，端点停车不计，比值1.0")
        self.assertIsNone(zero["ratio_reason"],
                          "V8-14b 3.3/裁定7：有移动样本时原因字段为None")


if __name__ == "__main__":
    unittest.main()
