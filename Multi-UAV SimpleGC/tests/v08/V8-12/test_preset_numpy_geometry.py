"""预置；独立预期来自手算、距离函数1-Lipschitz性质与r4 6.5。"""
import math
import unittest
import numpy as np

from v08.scene.exact import signed_distance
from v08.scene.field import Clearance, build_distance_field
from v08.motion.feasible import classify_empty, prove_concentric_band_empty
from v08.sim.guidance import NODE_TOL_M


def rectangle(x0, y0, x1, y1):
    return {"type": "Polygon",
            "vertices_m": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}


class TestExactGeometry(unittest.TestCase):
    def test_circle_polygon_buffer(self):
        circle = {"type": "Circle", "center_m": [2.0, 3.0], "radius_m": 5.0}
        p = np.array([[2, 3], [5, 7], [2, 10], [2, 8]], float)
        np.testing.assert_allclose(
            signed_distance(circle, p), [-5, 0, 2, 0],
            rtol=0, atol=NODE_TOL_M,
            err_msg="手算：3-4-5三角形；圆SDF=中心距减5")
        square = rectangle(0, 0, 4, 4)
        q = np.array([[2, 2], [5, 2], [5, 5], [0, 2]], float)
        np.testing.assert_allclose(
            signed_distance(square, q), [-2, 1, math.sqrt(2), 0],
            rtol=0, atol=NODE_TOL_M,
            err_msg="手算：最近边或顶点；角外距离sqrt(2)，不是1")
        reverse = {**square, "vertices_m": square["vertices_m"][::-1]}
        np.testing.assert_allclose(
            signed_distance(reverse, q), [-2, 1, math.sqrt(2), 0],
            rtol=0, atol=NODE_TOL_M,
            err_msg="数学性质：凸轮廓反向不改变有符号距离")
        buffered = {**square, "type": "BufferedPolygon", "buffer_m": 1.0}
        np.testing.assert_allclose(
            signed_distance(buffered, q), [-3, 0, math.sqrt(2) - 1, -1],
            rtol=0, atol=NODE_TOL_M,
            err_msg="解析Minkowski和：凸多边形SDF减buffer，保留圆角")

    def test_field_is_conservative(self):
        # 全为合成夹具；-20..20地图、半径5障碍与余量1有手算的非空区域。
        rules = (
            Clearance("world", rectangle(-20, -20, 20, 20), -1, 1.0),
            Clearance("disk", {"type": "Circle", "center_m": [0, 0],
                               "radius_m": 5.0}, 1, 1.0),
        )
        field = build_distance_field(rules, (-20, -20, 20, 20), spacing_m=5.0)
        random = np.random.Generator(np.random.PCG64(0))
        points = np.vstack([random.uniform(-20, 20, (512, 2)), [[12, 12]]])
        feasible = np.asarray(field.feasible(points), bool)
        self.assertTrue(feasible[-1],
                        "手算：(12,12)到地图边8、到圆约11.97，扣1和半对角仍正")
        # 独立解析oracle，不用被测signed_distance给自身作证。
        world_clear = 20 - np.max(np.abs(points), axis=1) - 1
        circle_clear = np.linalg.norm(points, axis=1) - 5 - 1
        self.assertTrue(np.all(world_clear[feasible] >= 0),
                        "数学性质：双线性值减半对角线只能保守收缩内部集合")
        self.assertTrue(np.all(circle_clear[feasible] >= 0),
                        "数学性质：1-Lipschitz下界保证外部距离约束")

    def test_narrow_legal_channel_is_not_proven_empty(self):
        rules = (Clearance("channel", rectangle(0, 0, 4, 20), -1, 0.0),)
        field = build_distance_field(rules, (0, 0, 5, 20), spacing_m=5.0)
        xx, yy = np.meshgrid(np.linspace(0, 4, 9), np.linspace(0, 20, 21))
        points = np.c_[xx.ravel(), yy.ravel()]
        self.assertFalse(np.any(field.feasible(points)),
                         "手算：宽4最大内距2，小于5m栅格半对角；顶点也不在深内部")
        answer = classify_empty(field, rules, exact_witnesses=((2.0, 10.0),))
        self.assertEqual(answer.code, "approx_empty",
                         "r4 6.5：近似空且真实非空不得报proven_infeasible")
        self.assertIs(answer.exact_nonempty, True,
                      "手算见证：(2,10)位于0<x<4、0<y<20内")
        self.assertIsNotNone(answer.witness,
                             "r4 14.1第4条：保留精确非空的对照证据")

    def test_column_band_empty_certificate(self):
        alert = {"type": "Circle", "center_m": [0, 0], "radius_m": 100.0}
        warning = {"type": "Circle", "center_m": [0, 0], "radius_m": 164.0}
        answer = prove_concentric_band_empty(
            alert, warning, alert_clearance_m=30.0, warning_inset_m=35.0,
            member_count=12, formation="column")
        self.assertEqual(answer.code, "proven_infeasible",
                         "手算：最窄单车道也要求r>=130且r<=129，无交集")
        self.assertEqual(answer.witness["inner_required_radius_m"], 130.0,
                         "手算：100+30=130")
        self.assertEqual(answer.witness["outer_allowed_radius_m"], 129.0,
                         "手算：164-35=129")
        self.assertEqual(answer.witness["gap_m"], -1.0,
                         "手算：129-130=-1；见证不是一段文字断言")
        legal = prove_concentric_band_empty(
            alert, {**warning, "radius_m": 166.0},
            alert_clearance_m=30.0, warning_inset_m=35.0,
            member_count=12, formation="column")
        self.assertIsNone(legal,
                          "r4 6.7.1纵列d=0；130..131非空，不能用11*3横向宽度证无解")


if __name__ == "__main__":
    unittest.main()
