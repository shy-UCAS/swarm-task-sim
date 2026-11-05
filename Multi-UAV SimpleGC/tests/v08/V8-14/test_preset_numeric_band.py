import math
import subprocess
import sys
import unittest
import numpy as np

from v08.motion.monitoring_band import (
    grid_error_m, band_certificate, construct_band, cubic_blend,
    admissible_arcs,
)
from v08.motion.monitoring_turn import collapse_length_m
from v08.motion.skeleton import width_then_build

EPS = np.finfo(float).eps
TOL = math.sqrt(EPS)  # float64 的平方根精度；仅合成数值比较，不改几何门禁。


class BandPreset(unittest.TestCase):
    def test_pure_import_does_not_load_shapely(self):
        code = (
            "import sys; "
            "import v08.motion.monitoring_band; "
            "import v08.motion.monitoring_turn; "
            "import v08.diagnostics.monitoring_skeleton; "
            "raise SystemExit(int(any(k == 'shapely' or k.startswith('shapely.') "
            "for k in sys.modules)))"
        )
        r = subprocess.run([sys.executable, "-B", "-c", code],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                         "纯数值/真实依赖隔离要求；独立子进程检查导入副作用：" + r.stderr)

    def test_grid_error_is_chord_bound(self):
        # 来源：角距离最多半个1度格，弦长=2R*sin(角差/2)，径向半格=1m。
        expected = 1.0 + 400.0 * math.sin(math.pi / 720.0)
        self.assertAlmostEqual(grid_error_m(200.0), expected,
                               delta=TOL * expected,
                               msg="2m与360方位的解析误差上界")
        self.assertGreater(grid_error_m(400.0), grid_error_m(200.0),
                           "弦距随半径严格单调，不能用固定e")

    def test_constant_band_midpoint_and_width_boundary(self):
        lo, hi = np.full(360, 100.), np.full(360, 200.)
        # 解析夹具：半跨度10，欧氏管径向收缩13，故e_g=3、e_s=0。
        c = band_certificate(lo, hi, lo + 13., hi - 13., (-10., 10.))
        self.assertTrue(c["feasible"], "100 >= 20+2*3，解析宽度")
        self.assertEqual(c["e_geom_m"], 3., "13-10=3")
        self.assertEqual(c["e_smooth_m"], 0., "常数边界的支持域变化为0")
        curve = construct_band(c, np.zeros(4))
        # logistic(0)=1/2；100+10+3+(100-20-6)/2=150。
        np.testing.assert_allclose(curve.radius(np.linspace(0, 2*math.pi, 721)),
                                   150., rtol=0, atol=150*TOL,
                                   err_msg="独立解析中点；正基函数保持常数")
        edge = band_certificate(lo, lo+26., lo+13., lo+13., (-10., 10.))
        self.assertTrue(edge["feasible"], "宽度恰20+2*3时使用>=，不拒绝边界")
        bad = band_certificate(lo, lo+25., lo+13., lo+12., (-10., 10.))
        self.assertFalse(bad["feasible"], "管区间倒置，不能声称仍有可行形状")

    def test_support_reserve_and_convex_hull(self):
        # 解析两级边界；相邻最多2m，五索引支持并集的最大变化仍为2m。
        lo = 100. + 2.*(np.arange(360) % 2)
        hi = lo + 100.
        c = band_certificate(lo, hi, lo+13., hi-13., (-10., 10.))
        self.assertEqual(c["e_smooth_m"], 2., "边界差的小规模穷举最大值为2")
        curve = construct_band(c, np.array([-2., -1., 0., 1., 2.]))
        phi = np.linspace(0., 2*math.pi, 3601, endpoint=False)
        nearest = np.floor(phi * 360/(2*math.pi) + .5).astype(int) % 360
        rho = curve.radius(phi)
        self.assertTrue(np.all(rho >= c["lower_m"][nearest] - 202*TOL),
                        "正基函数凸包性质，不能有插值下冲")
        self.assertTrue(np.all(rho <= c["upper_m"][nearest] + 202*TOL),
                        "正基函数凸包性质，不能有插值上冲")
        np.testing.assert_allclose(curve.radius(phi), curve.radius(phi+2*math.pi),
                                   rtol=TOL, atol=202*TOL,
                                   err_msg="周期性数学不变量")

    def test_coverage_counts_intervals_not_points(self):
        rows = np.zeros(360, dtype=bool)
        rows[:120] = True
        self.assertEqual(admissible_arcs(rows), [],
                         "120个点只有119个1度间隔，达不到判据120度")
        rows[120] = True
        self.assertIn((0, 120), admissible_arcs(rows),
                      "121个端点精确覆盖120度")
        wrapped = np.zeros(360, dtype=bool)
        wrapped[np.arange(300, 421) % 360] = True
        self.assertIn((300, 420), admissible_arcs(wrapped),
                      "环状连通性：跨0度不丢掉合法弧")

    def test_four_control_blend_and_collapse_length(self):
        np.testing.assert_allclose(cubic_blend(np.array([0., .5, 1.])),
                                   [0., .5, 1.], rtol=0, atol=TOL,
                                   err_msg="三次控制值(0,0,1,1)的解析值")
        args = dict(spacing_m=15., speed_max_m_s=12., command_max_m_s=10.,
                    dynamic_factor=.95, curvature_limit=.95*.2/.5)
        # 3个横排槽位：D=15，Delta_l=15；L_min约41.1，严格上取2m为42。
        L = collapse_length_m(np.array([[0., -15.], [0., 0.], [0., 15.]]), **args)
        self.assertEqual(L, 42., "由横向速率和三次导数解析推出，不是经验长度")
        self.assertEqual(collapse_length_m(
            np.array([[-15., 0.], [0., 0.], [15., 0.]]), **args), 0.,
            "已经为纵列且无槽位变化，不造多余收拢段")

    def test_width_selection_never_falls_back_after_build_failure(self):
        visited, built = [], []
        def probe(name):
            visited.append(name)
            return {"certificate": "valid"}
        failure = object()
        def build(name, payload):
            built.append(name)
            return failure
        result = width_then_build(("abreast", "echelon", "column"), probe, build)
        self.assertIs(result, failure, "U D.1：下游失败原样返回")
        self.assertEqual(visited, ["abreast"], "不能以下游结果继续探测梯形")
        self.assertEqual(built, ["abreast"], "每个attempt仅一次形状构造")


if __name__ == "__main__":
    unittest.main()
