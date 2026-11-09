"""V8-20 纯数值预置测试。未经运行；不导入 shapely，不读取场景。"""
import math
import unittest
import numpy as np
from v08.motion.area_search_numeric import (
    strip_angles, circle_strip_geometry, scan_vertices, assign_blocks,
    entry_beta_ok, draw_hierarchy, skeleton_checkpoint_values,
)


class IntegerRng:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = []

    def integers(self, high):
        self.calls.append(int(high))
        value = next(self.answers)
        if not 0 <= value < high:
            raise AssertionError("invalid scripted draw")
        return value


class NumericPreset(unittest.TestCase):
    def test_circle_strip_angles_endpoints_and_gap(self):
        # 解析圆：K=4，角步长7.5°，条带角为扇区各小格中心。
        angles = np.radians([-11.25, -3.75, 3.75, 11.25])
        eps = np.finfo(float).eps  # S gamma_8：有限次角度加减乘除的表示界。
        np.testing.assert_allclose(strip_angles(0., 30., 2, 2), angles,
                                   rtol=0., atol=8*eps/(1-8*eps))
        # 合成夹具：基础半径100，外offset400，内下界150；不是新增生产阈值。
        g = circle_strip_geometry(100., 400., 150., 0., 30., 2, 2)
        radius = 100. + 150. + .5*math.ceil((40. / (2. * math.sin(math.radians(3.75))) - 100. - 150.)/.5)
        expected_i = radius * np.c_[np.cos(angles), np.sin(angles)]
        expected_o = 500. * np.c_[np.cos(angles), np.sin(angles)]
        # 独立预期：圆弦d=2Rsin(Δ/2)；容差仅解析结果浮点表示。
        self.assertAlmostEqual(g["inner_offset_m"], radius - 100., delta=1e-9)
        np.testing.assert_allclose(g["inner_xy"], expected_i, rtol=0., atol=1e-9)
        np.testing.assert_allclose(g["outer_xy"], expected_o, rtol=0., atol=1e-9)
        np.testing.assert_allclose(np.linalg.norm(np.diff(g["inner_xy"], axis=0), axis=1),
                                   np.full(3, 2.*radius*math.sin(math.radians(3.75))), rtol=0., atol=1e-9)
        np.testing.assert_allclose(np.linalg.norm(np.diff(g["outer_xy"], axis=0), axis=1),
                                   np.full(3, 1000.*math.sin(math.radians(3.75))),
                                   rtol=0., atol=1e-9)
        # 解析长度500-R，必须超过U的60m；本夹具的rf50给外距上限80m。
        self.assertGreater(500.-radius, 60.)
        self.assertLess(1000.*math.sin(math.radians(3.75)), 80.)

    def test_circle_infeasible_and_odd_counts(self):
        # K=8时R_in=40/(2sin1.875°)>500，必无60m长条带。
        with self.assertRaises(ValueError):
            circle_strip_geometry(100., 400., 150., 0., 30., 2, 4)
        # U C.2：c只能是偶数且至少2；不能静默取整成合法c。
        for c in (0, 1, 3):
            with self.assertRaises(ValueError):
                strip_angles(0., 30., 2, c)

    def test_even_scan_vertices(self):
        inner = np.array([[0., 0.], [10., 0.], [20., 0.], [30., 0.]])
        outer = inner + [0., 100.]
        # 独立穷举两对：O0 I0 I1 O1 O2 I2 I3 O3。
        expected = np.array([[0.,100.],[0.,0.],[10.,0.],[10.,100.],
                             [20.,100.],[20.,0.],[30.,0.],[30.,100.]])
        np.testing.assert_array_equal(scan_vertices(inner, outer, [0,1,2,3]), expected)
        np.testing.assert_array_equal(scan_vertices(inner, outer, [2,3]), expected[4:])

    def test_assignment_abreast_column_and_echelon(self):
        # u=(1,0),n=(0,1)，块0横投影+20、块1为-20，所以块顺序1,0。
        first = np.array([[50.,20.],[50.,-20.]])
        u = (1.,0.)
        self.assertEqual(assign_blocks({"a":(0.,-10.),"b":(0.,10.)},
                                       ("a","b"), first, u, "abreast"), {"a":1,"b":0})
        # 纵列前到后：b在+10最前，a在-10后方；不按成员字符串排序。
        self.assertEqual(assign_blocks({"a":(-10.,0.),"b":(10.,0.)},
                                       ("a","b"), first, u, "column"), {"b":1,"a":0})
        # 梯形仍按横向槽位，U F.2明确该规则。
        self.assertEqual(assign_blocks({"a":(10.,-5.),"b":(-10.,5.)},
                                       ("a","b"), first, u, "echelon"), {"a":1,"b":0})

    def test_beta_filter(self):
        # q=(-cosβ,sinβ)，u向+x，向内径向与u夹角绝对值β。
        for deg, expected in ((0.,True),(44.,True),(46.,False),(-46.,False)):
            q = (-math.cos(math.radians(deg)), math.sin(math.radians(deg)))
            self.assertEqual(bool(entry_beta_ok(q,(0.,0.),(1.,0.))), expected)

    def test_three_conditional_uniform_draws(self):
        # 两弦的后续组合数不同；抽样仍第一层各1/2，不能展平为三元组。
        entries = [("A", [("A0",(2,4)),("A1",(2,))]),
                   ("B", [("B0",(2,4,6,8))])]
        r = IntegerRng([0,1,0])
        self.assertEqual(draw_hierarchy(entries,r), ("A","A1",2))
        self.assertEqual(r.calls,[2,2,1])  # 条件集合基数独立手数。
        r = IntegerRng([1,0,3])
        self.assertEqual(draw_hierarchy(entries,r), ("B","B0",8))
        self.assertEqual(r.calls,[2,1,4])
        r = IntegerRng([])
        with self.assertRaises(ValueError):
            draw_hierarchy([],r)
        self.assertEqual(r.calls,[])  # 空集不抽、不重开流。

    def test_checkpoint_strict_boundaries(self):
        # U D.5：190/200恰95%，中位数1、1800s均不触发。
        success = [True]*190+[False]*10
        got = skeleton_checkpoint_values(success,[2]*200,[1]*200,1800.)
        self.assertEqual(got["triggered"],[])
        got = skeleton_checkpoint_values([True]*189+[False]*11,[2]*200,[1]*200,1800.)
        self.assertIn("success_rate",got["triggered"])
        got = skeleton_checkpoint_values([True]*200,[2]*200,[2]*200,1801.)
        self.assertEqual(set(got["triggered"]),{"attempt_median","wall"})
        # 100人档合同全成功，另一100合同80成功：总体90%，低档恰差10pp。
        success = [True]*100+[True]*80+[False]*20
        got = skeleton_checkpoint_values(success,[2]*100+[12]*100,[1]*200,1.)
        self.assertNotIn("group_gap",got["triggered"])
        success = [True]*100+[True]*79+[False]*21
        got = skeleton_checkpoint_values(success,[2]*100+[12]*100,[1]*200,1.)
        self.assertIn("group_gap",got["triggered"])

    def test_centered_column_is_a_design_counterexample(self):
        # 独立几何反例，不是生产正例：R_warning500、R_outer447.5、h315、N12、b24。
        q = np.array([-math.sqrt(447.5**2-315.**2),315.])
        rear = q-np.array([132.,0.])  # 原居中纵列后槽位-(12-1)*24/2。
        self.assertLess(math.degrees(math.asin(315./447.5)),45.)
        self.assertTrue(entry_beta_ok(q,(0.,0.),(1.,0.)))
        self.assertLess(np.linalg.norm(q),500.)
        self.assertGreater(np.linalg.norm(rear),500.)  # Q内不保证所有槽位已入圈。


if __name__ == "__main__":
    unittest.main()
