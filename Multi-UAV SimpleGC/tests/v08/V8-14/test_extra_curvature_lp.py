"""V8-14b 执行方自加测试（裁定 V8-14b 第 4 节 1）：曲率约束线性规划在夹具上满足约束；精确曲率复核；
选队形（可行性 LP）与构造（带目标 LP）是同一约束集。不是预置测试；预期由解析夹具独立给出。"""
import math
import unittest

import numpy as np

from v08.motion.monitoring_band import (LP_CONTROLS, _lp_basis, construct_band_lp, exact_curvature_review,
                                        kappa_max, lp_feasible_pairs, lp_targets, shape_lp)
from v08.motion.path import periodic_radius_derivs

KSTAR = .95 * .2 / .5          # path.kappa_limit(0.5, 0.2)
RTURN = 1.05 * 15.0            # buffer_turn_factor × turn_u_min_m
TOL = 1e-6                     # HiGHS 原始可行性容差 1e-7 量级；仅合成数值比较


def stepped_band():
    """台阶夹具：A 在 60°–64° 处从 400 m 突升到 500 m（V8-14 第 6 节诊断的台阶形态），B = A + 300。"""
    A = np.full(360, 400.0)
    A[60:65] = 500.0
    return A, A + 300.0


def sample(c, phis):
    c = np.asarray(c, float)
    r, d1, d2 = periodic_radius_derivs(phis, float(np.mean(c)), c - np.mean(c))
    return r, d1, d2


class CurvatureLPExtra(unittest.TestCase):
    def test_kappa_max_formula(self):
        self.assertAlmostEqual(kappa_max(0.0, KSTAR, RTURN), 1.0 / RTURN, places=15, msg="D=0：第二项 1/15.75 更小")
        D = 60.0
        expect = min(KSTAR / (1 + KSTAR * D), 1.0 / (RTURN + D))
        self.assertEqual(kappa_max(D, KSTAR, RTURN), expect)
        self.assertLess(kappa_max(80.0, KSTAR, RTURN), kappa_max(20.0, KSTAR, RTURN), "D 越大曲率上限越小")

    def test_lp_solution_satisfies_constraints_on_step_fixture(self):
        A, B = stepped_band()
        D = 30.0
        km = kappa_max(D, KSTAR, RTURN)
        rows = np.arange(360)
        t, _ = lp_targets(rows, A, B, np.array([2., -2., 1., 0.]))
        lp = shape_lp(rows, A, B, A, kmax=km, periodic=True, target=t)
        self.assertTrue(lp["feasible"], lp["message"])
        self.assertEqual(len(lp["controls"]), LP_CONTROLS)
        phis = np.radians(np.arange(720) * .5)
        r, _, d2 = sample(lp["controls"], phis)
        lo = np.r_[A, np.maximum(A, np.roll(A, -1))]
        hi = np.r_[B, np.minimum(B, np.roll(B, -1))]
        ac = np.r_[A, np.maximum(A, np.roll(A, -1))]
        rr = np.r_[r[0::2], r[1::2]]
        dd = np.r_[d2[0::2], d2[1::2]]
        self.assertTrue(np.all(rr >= lo - TOL * lo) and np.all(rr <= hi + TOL * hi), "行与中点区间约束")
        lin = rr - dd
        self.assertTrue(np.all(np.abs(lin) <= km * ac * ac * (1 + TOL)), "线性化曲率约束")

    def test_exact_review_on_lp_and_rejects_step_following_curve(self):
        A, B = stepped_band()
        D = 30.0
        km = kappa_max(D, KSTAR, RTURN)
        rows = np.arange(360)
        t, _ = lp_targets(rows, A, B, np.zeros(4))
        lp = shape_lp(rows, A, B, A, kmax=km, periodic=True, target=t)
        cur = construct_band_lp(lp, np.zeros(4))
        rev = exact_curvature_review(cur.rho0_m, cur.coefficients_m, 0., 2 * math.pi, D, kappa_star=KSTAR,
                                     r_turn_m=RTURN)
        self.assertTrue(rev["ok"], f"LP 解精确复核：最小曲率半径 {rev['min_radius_m']}")
        # 反例：120 控制点紧跟台阶的曲线（无曲率约束）应被精确复核拒绝
        W0, _ = _lp_basis()
        c_bad = np.linalg.lstsq(W0[0::2], A + 150.0, rcond=None)[0]
        bad = exact_curvature_review(float(np.mean(c_bad)), c_bad - np.mean(c_bad), 0., 2 * math.pi, D,
                                     kappa_star=KSTAR, r_turn_m=RTURN)
        self.assertFalse(bad["ok"], "跟随 100 m 台阶的曲线曲率超限，复核必须拒绝")

    def test_exact_curvature_formula_on_circle(self):
        R = 200.0
        rev = exact_curvature_review(R, np.zeros(120), 0., 2 * math.pi, 0., kappa_star=KSTAR, r_turn_m=RTURN)
        self.assertAlmostEqual(rev["kappa_max_abs"], 1.0 / R, places=12, msg="圆 κ = 1/R")
        D_edge = R - RTURN                      # κ(D + 15.75) = 1 恰好成立
        self.assertTrue(exact_curvature_review(R, np.zeros(120), 0., 1., D_edge, kappa_star=KSTAR,
                                               r_turn_m=RTURN)["ok"], "边界取 ≤")
        self.assertFalse(exact_curvature_review(R, np.zeros(120), 0., 1., D_edge + 1e-6, kappa_star=KSTAR,
                                                r_turn_m=RTURN)["ok"], "越界拒绝")

    def test_selection_and_construction_share_constraint_set(self):
        """同一 (A, B, κ_max)：可行性 LP（选队形）有解 ⇔ 带目标 LP（构造）有解。窄带夹具随 D 增大由可行变不可行。"""
        A = 300.0 + 40.0 * np.sin(np.radians(np.arange(360)) * 3)
        B = A + 60.0
        rows = np.arange(360)
        t, _ = lp_targets(rows, A, B, np.array([1., -1., .5, 0., 2.]))
        seen = set()
        for D in (0.0, 20.0, 60.0, 120.0, 400.0):   # D=400：κ_max=1/415.75，而半径 ≤400 m 内的闭合星形曲线必有 κ ≥ 1/400 处
            km = kappa_max(D, KSTAR, RTURN)
            f = shape_lp(rows, A, B, A, kmax=km, periodic=True)["feasible"]
            g = shape_lp(rows, A, B, A, kmax=km, periodic=True, target=t)["feasible"]
            self.assertEqual(f, g, f"D={D}：选队形与构造必须同判")
            seen.add(f)
        self.assertEqual(seen, {True, False}, "夹具覆盖可行与不可行两种情形")

    def test_arc_feasibility_sweep_matches_bruteforce(self):
        """lp_feasible_pairs 的单调扫描结果与逐对求解一致（小规模穷举）。"""
        n = 40
        ids = np.arange(100, 100 + n)
        tl = np.full(n, 300.0)
        tl[25:28] = 360.0
        tu = tl + 30.0
        Ac = tl.copy()
        km = kappa_max(10.0, KSTAR, RTURN)
        pairs = [(s, e, 0.0) for s in range(n - 1) for e in range(s + 6, n)]
        from v08.motion.monitoring_band import _arc_feasible
        brute = [p for p in pairs if _arc_feasible(ids, tl, tu, Ac, p[0], p[1], km)]
        fast = lp_feasible_pairs(pairs, ids, tl, tu, Ac, km)
        self.assertEqual(sorted(fast), sorted(brute), "单调扫描不改变可行集合")
        self.assertTrue(0 < len(brute) < len(pairs), "夹具含可行与不可行弧")


if __name__ == "__main__":
    unittest.main()
