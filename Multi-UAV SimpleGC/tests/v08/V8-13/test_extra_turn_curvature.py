"""V8-13c 裁定 1 的执行方自加测试：掉头曲率不等式进入增广拉格朗日。

- 曲率约束的解析梯度用中心差分核对（与预置 test_gradient_matches_central_difference 同一判据）；
- 小半径半圆参考在掉头区间内被约束到 R ≥ 8 m（硬检查原下界），不加约束时同一参考达不到。
夹具（半径 5 m、20 s、区间留两端 3 s）是合成数学构造，不是业务配置。
"""
import math
import unittest

import numpy as np

from v08.motion.optimize import JointProblem, load_settings, prepare_problem, solve_joint
from v08.sim.tracking import TimeReference

EPS = np.finfo(float).eps
R_REF, T_REF, REL = 5.0, 20.0, 20.0     # 合成夹具


def semicircle(member="a"):
    def pva(t):
        raw = (np.asarray(t, float) - REL) / T_REF
        u = np.clip(raw, 0.0, 1.0)
        S = 10 * u ** 3 - 15 * u ** 4 + 6 * u ** 5
        dS = (30 * u ** 2 - 60 * u ** 3 + 30 * u ** 4) / T_REF
        ddS = (60 * u - 180 * u ** 2 + 120 * u ** 3) / T_REF ** 2
        act = ((raw >= 0) & (raw <= 1)).astype(float)
        th = math.pi * S
        er = np.stack([np.cos(th), np.sin(th)], -1)
        et = np.stack([-np.sin(th), np.cos(th)], -1)
        w, al = math.pi * dS * act, math.pi * ddS * act
        return R_REF * er, R_REF * w[..., None] * et, R_REF * (al[..., None] * et - (w ** 2)[..., None] * er)
    return TimeReference(member, REL, REL + T_REF, 100.0, pva)


def dense_min_radius(tr, t0, t1):
    t = np.arange(t0, t1, 0.005)
    v, a = tr.evaluate(t, 1), tr.evaluate(t, 2)
    s = np.hypot(v[:, 0], v[:, 1])
    c = np.abs(v[:, 0] * a[:, 1] - v[:, 1] * a[:, 0])
    k = np.where(s > 0, c / np.maximum(s, 1e-300) ** 3, 0.0)
    return 1.0 / k.max()


class TurnCurvature(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = load_settings()
        cls.turns = (("a", REL + 3.0, REL + T_REF - 3.0, 8.0),)

    def test_gradient_with_turn_constraint(self):
        prep = prepare_problem(JointProblem((semicircle(),), turns=self.turns), self.st)
        x = prep.x0 + 0.3 * np.sin(np.arange(len(prep.x0)) + np.sqrt(3.0))   # 合成扰动
        g_turn = prep.constraint_values(x)[("turn", 0, 0)]
        self.assertGreater(float(g_turn.max()), 0.0, "夹具须使曲率约束激活，否则不检验该项梯度")
        _, grad = prep.value_grad(x)
        for k in range(len(x)):
            d = EPS ** (1 / 3) * max(1.0, abs(x[k]))
            xp, xm = x.copy(), x.copy()
            xp[k] += d
            xm[k] -= d
            fd = (prep.value_grad(xp)[0] - prep.value_grad(xm)[0]) / (2 * d)
            self.assertLessEqual(abs(fd - grad[k]), EPS ** (1 / 3) * (1 + abs(fd) + abs(grad[k])),
                                 "中心差分一致性，坐标 %d" % k)

    def test_turn_radius_enforced(self):
        free = solve_joint(JointProblem((semicircle(),)), self.st)
        r_free = dense_min_radius(free.references["a"], REL + 3.0, REL + T_REF - 3.0)
        self.assertLess(r_free, 8.0, "不加约束时贴近 5 m 半圆，掉头区间半径低于 8 m")
        sol = solve_joint(JointProblem((semicircle(),), turns=self.turns), self.st)
        self.assertTrue(sol.ok, sol.reason)
        turns = sol.diagnostics["physical"]["turns"]
        self.assertEqual(len(turns), 1)
        self.assertGreaterEqual(turns[0]["min_radius_m"], 8.0, "硬检查原下界 8 m（连续区间极值）")
        self.assertGreaterEqual(dense_min_radius(sol.references["a"], REL + 3.0, REL + T_REF - 3.0), 8.0,
                                "5 ms 密采样复核（只作旁证）")


if __name__ == "__main__":
    unittest.main()
