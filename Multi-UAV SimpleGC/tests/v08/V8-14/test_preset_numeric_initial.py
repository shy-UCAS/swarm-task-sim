import math
import unittest
import numpy as np
from scipy.interpolate import BSpline

from v08.motion.optimize import JointProblem, load_settings, prepare_problem
from v08.motion.skeleton import merge_semantic_lines
from v08.sim.tracking import TimeReference

TOL = math.sqrt(np.finfo(float).eps)


def line(mid, a, b, point=(0., 0.), tangent=(1., 0.), tag="x"):
    return (mid, a, b, point, tangent, {"source": tag})


class InitialPreset(unittest.TestCase):
    def test_gap_strict_four_knots_and_member_identity(self):
        merged = merge_semantic_lines([
            line("a", 0., 1., tag="first"),
            line("a", 3.09, 4., tangent=(-1., 0.), tag="second"),
            line("b", 0., 4., tag="other-member"),
        ], knot_s=1.)
        a = [v for v in merged if v[0] == "a"]
        self.assertEqual(len(a), 1, "U C.1/D.3：2.09s<4s，反向切向仍是同一支撑线")
        self.assertEqual(tuple(a[0][1:3]), (0., 4.), "等式覆盖整个合并时间区间")
        self.assertEqual(len([v for v in merged if v[0] == "b"]), 1,
                         "不能把不同成员的等式合并")
        edge = merge_semantic_lines([line("a", 0., 1.), line("a", 5., 6.)],
                                    knot_s=1.)
        self.assertEqual(len(edge), 2, "间隙恰4h不满足严格<")
        short_h = merge_semantic_lines(
            [line("a", 0., 1.), line("a", 3.09, 4.)], knot_s=.5)
        self.assertEqual(len(short_h), 2, "4h=2s，2.09s不能沿用生产4s常数")

    def test_parallel_distinct_and_nonadjacent_lines_do_not_merge(self):
        got = merge_semantic_lines([
            line("a", 0., 1.),
            line("a", 2., 3., point=(0., 10.)),
            line("a", 3.1, 4.),
        ], knot_s=1.)
        self.assertEqual(len(got), 3,
                         "平行不等于共线；中间有不同直线，不能跨越它合并首尾")

    def test_initial_matches_independent_dense_kkt(self):
        # 独立预期：直接用SciPy BSpline构造完整坐标的稠密KKT系统，
        # 不使用被测 _gram/_ls_grad_c/_eliminate/预条件矩阵生成预期。
        T = 8.
        def pva(t):
            t = np.asarray(t, dtype=float)
            p = np.stack((t, np.zeros_like(t)), axis=-1)
            v = np.stack((np.ones_like(t), np.zeros_like(t)), axis=-1)
            return p, v, np.zeros_like(p)
        ref = TimeReference("a", 0., T, 100., pva)
        settings = load_settings()
        self.assertEqual(settings["weight_smooth"], 1.,
                         "B13裁定权重固定1，不允许本项重新标定")
        self.assertEqual(settings["jerk_plan_m_s3"], 14.,
                         "固定提交测量配置J_plan=14")
        prep = prepare_problem(JointProblem((ref,)), settings, knot_s=1.)
        M, n = 8, 11
        knots = np.arange(-3, M+4, dtype=float)
        basis = BSpline(knots, np.eye(n), 3, extrapolate=False)
        ts = np.arange(81, dtype=float)/10.
        weights = np.full(81, .1)
        weights[[0, -1]] = .05
        B = basis(ts)
        D = basis(np.arange(M, dtype=float)+.5, nu=3)
        H = 2./T * ((B.T*weights) @ B / 9. + D.T @ D / 196.)
        rhs = 2./T * B.T @ (weights*ts) / 9.
        A = np.vstack([basis(0., nu=o) for o in (0, 1, 2)] +
                      [basis(T, nu=o) for o in (0, 1, 2)])
        target = np.array([0., 0., 0., T, 0., 0.])
        kkt = np.block([[H, A.T], [A, np.zeros((6, 6))]])
        expected = np.linalg.solve(kkt, np.r_[rhs, target])[:n]
        actual = prep.coeffs(prep.x_ls)[0]  # 破对称前；保留该诊断属性
        scale = max(1., float(np.max(np.abs(expected))))
        np.testing.assert_allclose(actual[:, 0], expected, rtol=TOL,
                                   atol=TOL*scale,
                                   err_msg="解析二次型等式约束唯一极小值，包含jerk项")
        np.testing.assert_allclose(actual[:, 1], 0., rtol=0, atol=TOL*scale,
                                   err_msg="直线夹具关于y反射对称，唯一最优y为0")
        np.testing.assert_allclose(A @ actual[:, 0], target, rtol=TOL,
                                   atol=TOL*scale,
                                   err_msg="端点p/v/a等式应保持，不能用平滑初值破坏它")


if __name__ == "__main__":
    unittest.main()
