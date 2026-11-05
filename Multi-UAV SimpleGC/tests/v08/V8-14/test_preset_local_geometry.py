import math
import unittest
import numpy as np
import shapely  # 明确本文件属于几何依赖组；没有时失败，不skip。

from v08.scene.field import Clearance
from v08.motion.monitoring_band import (
    radial_intervals, grid_error_m, band_certificate, construct_band,
)
from v08.motion.path import periodic_radius_derivs

TOL = math.sqrt(np.finfo(float).eps)


def circle(radius):
    return {"type": "Circle", "center_m": [0., 0.], "radius_m": float(radius)}


class LocalGeometryPreset(unittest.TestCase):
    def test_eccentric_band_and_true_normal_offsets(self):
        center = np.array([80., 0.])
        cons = [
            Clearance("alert", circle(100.), 1, 30.),
            Clearance("warning", circle(300.), -1, 35.),
            Clearance("world", circle(500.), -1, 35.),
        ]
        radii = np.arange(2., 502., 2.)
        lo, hi = radial_intervals(cons, center, radii)
        self.assertEqual((lo[0], hi[0]), (50., 184.),
                         "解析有效同心半径130..265，向右相对偏心80是50..185；2m网格上184")
        self.assertEqual((lo[180], hi[180]), (210., 344.),
                         "向左交点210..345，2m网格保守取344")
        self.assertLess(float(np.min(hi)-np.max(lo)), 0.,
                        "解析偏心圆没有同心半径交集，不能压成圆")
        q = grid_error_m(math.hypot(380., 300.))
        D = 15.
        tlo, thi = radial_intervals(cons, center, radii, extra_margin_m=D+q)
        cert = band_certificate(lo, hi, tlo, thi, (-D, 0., D))
        self.assertTrue(cert["feasible"],
                        "解析圆环宽135m，偏心80<内半径130；该30m车道夹具有充足管余量")
        curve = construct_band(cert, np.array([-1., 0., 1., .5]))
        phi = np.linspace(0., 2*math.pi, 10001)
        rho, dr, _ = periodic_radius_derivs(
            phi, curve.rho0_m, curve.coefficients_m)
        er = np.column_stack((np.cos(phi), np.sin(phi)))
        ep = np.column_stack((-np.sin(phi), np.cos(phi)))
        xy = center + rho[:, None]*er
        tangent = dr[:, None]*er + rho[:, None]*ep
        tangent /= np.linalg.norm(tangent, axis=1)[:, None]
        normal = np.column_stack((-tangent[:, 1], tangent[:, 0]))
        for d in (-D, 0., D):
            radius = np.linalg.norm(xy+d*normal, axis=1)
            # 来源：所有真实法向车道均须在独立解析有效圆环130..265内。
            self.assertGreaterEqual(float(radius.min()), 130.-300*TOL,
                                    "法向并非径向；用欧氏范数独立核对内边界")
            self.assertLessEqual(float(radius.max()), 265.+300*TOL,
                                 "管证书应覆盖采样角之间及法向偏移")
        # 上面容差只覆盖合成圆/样条浮点运算；生产硬检查仍严格非负。


if __name__ == "__main__":
    unittest.main()
