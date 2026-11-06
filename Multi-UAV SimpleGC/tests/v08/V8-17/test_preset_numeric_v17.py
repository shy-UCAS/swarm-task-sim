"""V8-17 预置测试；未经运行。纯数值层，不导入 shapely/真实场景。"""
import math
import unittest
import numpy as np

from v08.motion.intrusion_numeric import (
    deepest_station, endpoint_interval, sigma_values,
    intersect_endpoint_sets, draw_feasible, prefix_endpoint_set,
    circle_infeasibility_certificate, clip_lanes)
from v08.runner.intrusion_report import skeleton_checkpoint


def circle(r, c=(0.0, 0.0)):
    return {"type": "Circle", "center_m": list(c), "radius_m": float(r)}


class Stream:
    def __init__(self, integers, quantile):
        self.ints = iter(integers)
        self.q = quantile
        self.calls = []

    def integers(self, low, high):
        self.calls.append(("integer", low, high))
        value = next(self.ints)
        if not low <= value < high:
            raise AssertionError("测试流索引越界")
        return value

    def random(self):
        self.calls.append(("random",))
        return self.q


class NumericPreset(unittest.TestCase):
    def test_three_endpoint_conditions(self):
        # 独立解析：contour R20→45次水平半径65；protected R100→内10半径90。
        # 最深点x=0，故E=[-65,0]。含轮廓内部，不得增加距离下界。
        self.assertEqual(endpoint_interval(circle(20), circle(100), (0, 0), (1, 0)),
                         (-65.0, 0.0))
        # 独立解析：protected R60内10半径50更紧，故保护条件决定左端。
        self.assertEqual(endpoint_interval(circle(20), circle(60), (0, 0), (1, 0)),
                         (-50.0, 0.0))
        # 独立解析：p0=(7,0)使最深站点=-7，故第三条件将右端截到-7。
        self.assertEqual(endpoint_interval(circle(20), circle(100), (7, 0), (1, 0)),
                         (-72.0, -7.0))
        # 独立解析：y=64时半弦sqrt(65²-64²)，不是5m/1m栅格端点。
        got = endpoint_interval(circle(20), circle(100), (0, 64), (1, 0))
        want = np.array([-math.sqrt(129.0), 0.0])
        # 4 ULP沿用S V8-16解析圆测试；只用于此良态解析比较，不放宽业务判据。
        np.testing.assert_array_max_ulp(np.asarray(got), want, maxulp=4)
        # 独立解析：y=65仅有切点；y=66与R65次水平圆不相交。
        self.assertEqual(endpoint_interval(circle(20), circle(100), (0, 65), (1, 0)),
                         (0.0, 0.0))
        self.assertIsNone(endpoint_interval(circle(20), circle(100), (0, 66), (1, 0)))

    def test_polygon_plateau_and_external_projection(self):
        rect = {"type": "Polygon",
                "vertices_m": [[-20, -5], [20, -5], [20, 5], [-20, 5]]}
        # 独立解析：y=0内部SDF最小=-5，平台[-15,15]，取最左-15。
        self.assertEqual(deepest_station(rect, (0, 0), (1, 0)), -15.0)
        # 独立解析：y=10外部最近距离5，平台[-20,20]，取最左-20。
        self.assertEqual(deepest_station(rect, (0, 10), (1, 0)), -20.0)
        buffered = dict(rect, type="BufferedPolygon", buffer_m=3.0)
        # 独立不变量：减去常数buffer不改变argmin。
        self.assertEqual(deepest_station(buffered, (0, 0), (1, 0)), -15.0)

    def test_sigma_and_interval_composition(self):
        # 独立来源U D.3.4：b20，sigma>=6/20=.30，降序1到.30，步长.05。
        self.assertEqual(sigma_values(20.0, "column"),
                         tuple(k / 20 for k in range(20, 5, -1)))
        self.assertEqual(sigma_values(20.0, "abreast"), (1.0,))
        # 手算：三车道E=[-20,0]，l=(-20,0,20)；sigma=.5交集只剩{-10}。
        lanes = (((-20.0, 0.0),),) * 3
        self.assertEqual(intersect_endpoint_sets(lanes, (-20, 0, 20), 0.5),
                         ((-10.0, -10.0),))
        # sigma=.55，要求xe>=-9且xe<=-11，空。
        self.assertEqual(intersect_endpoint_sets(lanes, (-20, 0, 20), 0.55), ())
        # 不相连区间须保留，不能把中间禁区补成凸包。
        self.assertEqual(intersect_endpoint_sets((((-5, -4), (4, 5)),), (0,), 1),
                         ((-5.0, -4.0), (4.0, 5.0)))

    def test_other_warning_can_end_deep_inside(self):
        sub = {10.0: (-210.0, 210.0), -10.0: (-190.0, 190.0)}
        # 独立解析：圆R200从-400向前；可停在带前、深内部或完整穿出后。
        self.assertEqual(prefix_endpoint_set(sub, -400.0),
                         ((-400.0, -210.0), (-190.0, 190.0),
                          (210.0, math.inf)))
        # 独立边界例：+10次水平集只有切点，整条线SDF>=10，允许经过该切点。
        self.assertEqual(prefix_endpoint_set({10.0: (0.0, 0.0), -10.0: None}, -20),
                         ((-20.0, math.inf),))
        # 浅穿越没有-10区间时，不能穿过整个带伪装合法。
        self.assertEqual(prefix_endpoint_set({10.0: (-10.0, 10.0), -10.0: None}, -20),
                         ((-20.0, -10.0),))

    def test_sampling_order_and_length_measure(self):
        ranges = ((0.0, 1.0), (10.0, 13.0))
        cells = [
            {"theta_idx": 0, "h_m": 0.0, "choices": [
                {"sigma": 1.0, "intervals": ((0.0, 1.0),),
                 "by_collect_D": [[100.0, ((0.0, 1.0),)]]},
                {"sigma": 0.5, "intervals": ranges,
                 "by_collect_D": [[100.0, ranges], [110.0, ((10.0, 13.0),)]]}]},
            {"theta_idx": 1, "h_m": 5.0, "choices": [
                {"sigma": 0.4, "intervals": ((20.0, 21.0),),
                 "by_collect_D": [[100.0, ((20.0, 21.0),)]]}]}
        ]
        rng = Stream([0, 1, 0], 0.5)
        got = draw_feasible(cells, rng)
        # 手算：总长4，q=.5对应长度2，第二段位置10+(2-1)=11。
        self.assertEqual((got["cell_index"], got["sigma"], got["x_e"],
                          got["collect_D_m"]), (0, 0.5, 11.0, 100.0))
        # U D.3.4：格→sigma→endpoint→相容D；每步一次，不按sigma数给格加权。
        self.assertEqual(rng.calls, [("integer", 0, 2), ("integer", 0, 2),
                                     ("random",), ("integer", 0, 2)])
        rng2 = Stream([1, 0, 0], 0.25)
        got2 = draw_feasible(cells, rng2)
        # 独立解析：第二格一条长度1的区间，四分位点20.25。
        self.assertEqual((got2["cell_index"], got2["sigma"], got2["x_e"]),
                         (1, 0.4, 20.25))

    def test_member_terminal_domains(self):
        from v08.motion.formation import Reference, Slots
        # 独立直线参考：x=-321..11，s=x+321；collect=-300，terminal=-10。
        ref = Reference(np.array([[-321., 0.], [11., 0.]]),
                        np.zeros(2), np.zeros(2), np.array([0., 332.]),
                        {"collect": 21.0, "terminal": 311.0}, ())
        slots = Slots(("a", "b", "c"),
                      {"a": (-20.0, 0.0), "b": (0.0, 0.0), "c": (20.0, 0.0)},
                      "column", "column", "column", False, 20.0, 20.0)
        lanes = clip_lanes(ref, slots, ref.marks["collect"],
                           ref.marks["terminal"], 0.5, spacing_m=0.5)
        # 独立公式：起点xc+l不变；终点xe+sigma*l。整数及二进制精确的0.5。
        for m, start, end in (("a", -320, -20), ("b", -300, -10), ("c", -280, 0)):
            np.testing.assert_array_equal(lanes[m].xy[0], [start, 0.0])
            np.testing.assert_array_equal(lanes[m].xy[-1], [end, 0.0])
        ends = [lanes[m].xy[-1] for m in slots.order]
        # 相邻纵列=sigma*b=10，非相邻为20，不能断言所有两两相等。
        self.assertEqual(float(np.linalg.norm(ends[1] - ends[0])), 10.0)
        self.assertEqual(float(np.linalg.norm(ends[2] - ends[0])), 20.0)
        echelon = Slots(("a", "b", "c"),
                        {"a": (-20., -3.), "b": (0., 0.), "c": (20., 3.)},
                        "echelon", "echelon", "echelon", False, 20., 3.)
        el = clip_lanes(ref, echelon, 21.0, 311.0, 0.5, spacing_m=0.5)
        # 独立解析：实际梯形终点纵向差10、横向差3，相邻距离sqrt109。
        delta = el["b"].xy[-1] - el["a"].xy[-1]
        np.testing.assert_array_equal(delta, [10.0, 3.0])
        np.testing.assert_array_max_ulp(np.linalg.norm(delta),
                                       math.sqrt(109.0), maxulp=4)
        self.assertGreaterEqual(float(np.linalg.norm(delta)), 10.0)

    def test_circle_certificate_grid_not_continuous_sigma(self):
        # 手算：R21+45=66；b16最小sigma=.4；11*.4*16=70.4>66；
        # 横排176>132，三个队形均被必要条件排除。
        cert = circle_infeasibility_certificate(circle(21), circle(100), 12, 16.0)
        self.assertIsNotNone(cert)
        # 11机最小纵向跨度64<=66，不能用同一必要条件证明不可行。
        self.assertIsNone(circle_infeasibility_certificate(circle(21), circle(100), 11, 16.0))

    def test_exclusion_only_changes_rate_and_gap(self):
        rows = []
        for i in range(20):
            rows.append(dict(contract_id=f"fixture_{i:02d}", success=(i != 0),
                             attempts=1, group_size=12, facility_count=2,
                             initial_speed_m_s=6.0, shape_audit_failed_attempts=0,
                             curved=True))
        rows.append(dict(contract_id="o34_d3", success=False, attempts=0,
                         group_size=12, facility_count=2, initial_speed_m_s=6.0,
                         shape_audit_failed_attempts=0,
                         failure={"code": "proven_infeasible"}))
        got = skeleton_checkpoint(rows, expected_count=21)
        # 独立手算：完成21，rate分母20，19/20恰95%不触发；实际attempt仍20。
        self.assertTrue(got["complete"])
        self.assertEqual(got["metrics"]["success_rate_fraction"], "19/20")
        self.assertEqual(got["metrics"]["skeleton_attempts_total"], 20)
        self.assertNotIn("success_rate", got["triggered"])
        rows[1]["success"] = False
        bad = skeleton_checkpoint(rows, expected_count=21)
        # 18/20<95%才触发，不用原始21作率分母。
        self.assertIn("success_rate", bad["triggered"])


if __name__ == "__main__":
    unittest.main()
