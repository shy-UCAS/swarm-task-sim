import copy
import math
import unittest
import numpy as np

from v08.config import load_config
from v08.motion.detour_config import load_detour_candidate
from v08.motion.detour_numeric import (
    sweep_series, target_sweep_conditions, group_sweep,
    polar_endpoint, fillet_from_pose,
)
from v08.runner.detour_report import skeleton_checkpoint

ATOL = 1e-9  # 仅解析浮点对照，来源：V19/V20 的表示差异授权量级。


class NumericV21(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.C = load_detour_candidate().values
        cls.G = load_config("detour").values
        cls.D = cls.C["near_band_width_m"]

    def series(self, degrees, sd=None):
        angles = np.radians(np.asarray(degrees, float))
        # 还原 atan2 的输入域，要求待测函数自己 unwrap。
        wrapped = np.arctan2(np.sin(angles), np.cos(angles))
        dist = np.full(len(angles), self.D / 2) if sd is None else np.asarray(sd, float)
        return sweep_series(np.arange(len(angles), dtype=np.int64) * 100000,
                            dist, wrapped, self.D)

    def test_arc_150_and_reversal(self):
        # 独立预期：单向弧的 span/net 等于首尾方位差；方向反转不改变二者绝对值。
        for degrees in (np.linspace(350, 500, 1501), np.linspace(500, 350, 1501)):
            s = self.series(degrees)
            self.assertAlmostEqual(s["max_span_deg"], 150.0, delta=ATOL)
            self.assertAlmostEqual(s["best_net_deg"], 150.0, delta=ATOL)
            self.assertEqual(s["entry_count"], 1)
            self.assertIsNone(s["last_exit_us"])
        s = self.series([0, 100, 20])
        self.assertAlmostEqual(s["max_span_deg"], 100.0, delta=ATOL)
        self.assertAlmostEqual(s["best_net_deg"], 20.0, delta=ATOL)

    def test_mask_endpoints_and_real_exit_frame(self):
        # 独立布尔期望：0 不属于带，D 属于；末True后的首False才是退出帧。
        d = [-1, 0, self.D/2, self.D, self.D+1, self.D/2, self.D+1]
        s = self.series(np.arange(len(d)), d)
        self.assertEqual(s["entry_count"], 2)
        self.assertEqual(s["exit_count"], 2)
        self.assertEqual(s["first_entry_us"], 200000)
        self.assertEqual(s["last_exit_us"], 600000)
        self.assertEqual([(r["start_index"], r["stop_index"]) for r in s["runs"]], [(2,4),(5,6)])
        self.assertFalse(s["starts_in_band"])
        self.assertFalse(s["ends_in_band"])
        self.assertEqual(s["runs"][1]["span_deg"], 0.0)

    def test_no_join_across_outside_frame(self):
        # 若先过滤mask再拼角，会错误得到两端的跨段扫角。
        s = self.series([0, 100, 160], [self.D/2, self.D+1, self.D/2])
        self.assertEqual(s["entry_count"], 2)
        self.assertEqual(s["max_span_deg"], 0.0)
        c = target_sweep_conditions(s, self.C)
        self.assertFalse(c["single_near_visit"])

    def test_all_runs_upper_limit_and_threshold_boundaries(self):
        # 直接使用独立构造的统计量，精确比较边界；不靠atan2舍入决定等号。
        theta = self.C["min_sweep_deg"]
        upper = self.C["max_sweep_deg_exclusive"]
        stats = {"entry_count": 1, "max_span_deg": theta, "runs": [{"span_deg": theta}]}
        c = target_sweep_conditions(stats, self.C)
        self.assertEqual(c, {"single_near_visit": True, "min_sweep": True, "max_sweep": True})
        stats["max_span_deg"] = np.nextafter(theta, -math.inf)
        self.assertFalse(target_sweep_conditions(stats, self.C)["min_sweep"])
        stats = {"entry_count": 1, "max_span_deg": upper, "runs": [{"span_deg": upper}]}
        self.assertFalse(target_sweep_conditions(stats, self.C)["max_sweep"])
        # 超过一整圈，unwrap必须保留绕行次数，而非压成最短覆盖弧。
        s = self.series(np.linspace(0, upper + 10, 3701))
        self.assertFalse(target_sweep_conditions(s, self.C)["max_sweep"])
        # 所有区间都查：不能只读一个预先给出的best值。
        stats = {"entry_count": 2, "max_span_deg": theta,
                 "runs": [{"span_deg": theta}, {"span_deg": upper}]}
        self.assertFalse(target_sweep_conditions(stats, self.C)["max_sweep"])
        low = theta + self.G["nominal_sweep_margin_deg"]
        stats = {"entry_count": 1, "max_span_deg": low, "runs": [{"span_deg": low}]}
        self.assertTrue(target_sweep_conditions(stats, self.C, nominal=True, generation=self.G)["min_sweep"])

    def test_group_min_then_facility_max(self):
        # 手算：F0=min(80,120)=80；F1=min(170,40)=40；S_all=80。
        g = group_sweep({"a": {"F0":80.0,"F1":170.0}, "b": {"F0":120.0,"F1":40.0}})
        self.assertEqual(g, {"by_facility":{"F0":80.0,"F1":40.0}, "S_all":80.0})
        g = group_sweep({"a":{"F":180.0},"b":{"F":0.0}})
        self.assertEqual(g["S_all"], 0.0)
        with self.assertRaises(ValueError):
            group_sweep({})
        with self.assertRaises(ValueError):
            group_sweep({"a":{"F":1.0},"b":{}})

    def test_analytic_arc_endpoints(self):
        # 四分之一圆：终点(0,±r)，切向(-1,0)；不使用待测采样器生成期望。
        for sigma in (-1,1):
            e = polar_endpoint((0,0),1000.0,0.0,sigma*math.pi/2,sigma)
            np.testing.assert_allclose(e["point_xy"], [0,sigma*1000], rtol=0, atol=ATOL)
            np.testing.assert_allclose(e["tangent_xy"], [-1,0], rtol=0, atol=ATOL)

    def test_analytic_entry_exit_fillet(self):
        # β=0、圆弧端切向已知，直角圆角的切线长恰为R，独立手算。
        R, L = self.G["fillet_floor_m"], self.G["tangent_straight_m"]
        a = fillet_from_pose((1000,0),(0,1),(-1,0),R,L,True)
        np.testing.assert_allclose(a["fillet_start_xy"],[1000+R,-L-R],rtol=0,atol=ATOL)
        np.testing.assert_allclose(a["fillet_end_xy"],[1000,-L],rtol=0,atol=ATOL)
        np.testing.assert_allclose(a["fillet_center_xy"],[1000+R,-L],rtol=0,atol=ATOL)
        self.assertAlmostEqual(a["turn_angle_rad"],-math.pi/2,delta=ATOL)
        b = fillet_from_pose((0,1000),(-1,0),(0,1),R,L,False)
        np.testing.assert_allclose(b["fillet_start_xy"],[-L,1000],rtol=0,atol=ATOL)
        np.testing.assert_allclose(b["fillet_end_xy"],[-L-R,1000+R],rtol=0,atol=ATOL)
        np.testing.assert_allclose(b["fillet_center_xy"],[-L,1000+R],rtol=0,atol=ATOL)

    def test_skeleton_checkpoint_strict_boundaries(self):
        # 180/200恰90%、成功attempt中位3、墙钟1800s，均不触发。
        records = [{"success":j<180,"group_size":1,"attempts":3,
                    "formation_prior":"column", "formation":{"start":"column","realized":"column"}}
                   for j in range(200)]
        q = skeleton_checkpoint(records,wall_s=1800.0)
        self.assertTrue(q["complete"])
        self.assertEqual(q["triggered"],[])
        records[179]["success"] = False
        self.assertIn("success_rate",skeleton_checkpoint(records,wall_s=1800)["triggered"])
        records[179]["success"] = True
        for r in records:
            r["attempts"] = 4
        self.assertIn("attempt_median",skeleton_checkpoint(records,wall_s=1800)["triggered"])
        records.pop()
        self.assertFalse(skeleton_checkpoint(records,wall_s=1)["complete"])


if __name__ == "__main__":
    unittest.main()
