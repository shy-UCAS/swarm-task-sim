"""V8-16 自加测试（执行方编写，不替代预置测试）：纯数值/协议，不导入 shapely 或真实场景。"""
import math
import unittest
from types import SimpleNamespace as NS

import numpy as np


class ExtraNumeric(unittest.TestCase):
    def test_nonuniform_last_span_derivative_coefficients(self):
        """非均匀末跨与重复端节点：导数控制系数算子与 SciPy BSpline.derivative 的系数逐项一致（通用公式，不统一除以 20）。"""
        from scipy.interpolate import BSpline
        from v08.motion.transit_numeric import clamped_knots, derivative_operators
        t = clamped_knots(0.0, 50.0)                     # L = 2.5：内部节点 1、2，末跨 0.5
        np.testing.assert_array_equal(t, [0, 0, 0, 0, 1, 2, 2.5, 2.5, 2.5, 2.5])
        n = len(t) - 4
        a = np.random.default_rng(7).normal(size=n)
        D1, D2 = derivative_operators(t)
        d1 = BSpline(t, a, 3).derivative(1)
        d2 = BSpline(t, a, 3).derivative(2)
        np.testing.assert_allclose(D1 @ a, d1.c[:n - 1], rtol=0, atol=1e-12)
        np.testing.assert_allclose(D2 @ a, d2.c[:n - 2], rtol=0, atol=1e-12)

    def test_curve_lp_endpoints_and_controls_fixed(self):
        """端点 δ = h、δ' = 0：首尾控制值及相邻值固定为 h。"""
        from v08.motion.transit_numeric import curve_lp
        x = np.arange(0.0, 205.0, 5.0)
        got = curve_lp(x, np.full(x.shape, -30.0), np.full(x.shape, 30.0), 0.0, np.full(5, 1.5), D_m=10.0)
        self.assertTrue(got["feasible"])
        c = np.asarray(got["spline"].c, float)
        np.testing.assert_array_equal(c[[0, 1, -2, -1]], np.zeros(4))

    def test_chord_query_identity_separates_N_and_ignores_order(self):
        """同一网格、不同 N 不串缓存；同一组偏移换顺序（槽位排列）身份相同。"""
        from v08.motion.transit_chords import query_identity
        ctx = NS(cache_key="ctx")
        a, _ = query_identity(ctx, "f1", [(0.0, -10.0), (0.0, 10.0)])
        b, _ = query_identity(ctx, "f1", [(0.0, 10.0), (0.0, -10.0)])
        c, _ = query_identity(ctx, "f1", [(0.0, -20.0), (0.0, 0.0), (0.0, 20.0)])
        d, _ = query_identity(ctx, "f2", [(0.0, -10.0), (0.0, 10.0)])
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertNotEqual(a, d)

    def test_transit_cli_default_and_explicit_workers(self):
        """新增 CLI 默认取共享 DEFAULT_WORKERS（24），显式 --workers 16 只影响本次解析。"""
        import importlib.util
        from pathlib import Path
        from v08.runner.runtime_defaults import DEFAULT_WORKERS
        p = Path(__file__).resolve().parents[3] / "tools" / "v08" / "run_transit_v16.py"
        spec = importlib.util.spec_from_file_location("run_transit_v16", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        base = ["--stage", "skeleton", "--devset", "x", "--data-root", "y", "--cache", "z", "--out", "w"]
        self.assertEqual(DEFAULT_WORKERS, 24)
        self.assertEqual(mod.build_parser().parse_args(base).workers, DEFAULT_WORKERS)
        self.assertEqual(mod.build_parser().parse_args(base + ["--workers", "16"]).workers, 16)
        self.assertEqual(mod.build_parser().parse_args(base).workers, 24)

    def test_paired_rows_outer_join(self):
        """200 键外连接：一侧缺失的键保留，缺字段记 None 并列缺项，不只内连接双方成功者。"""
        from v08.runner.transit_report import four_cell, paired_rows
        row = lambda fid, d, ok, **kw: dict(family_id=fid, draw_index=d, branch=None, contract_id=f"{fid}_{d}",
                                            success=ok, attempts=1, group_size=2, facility_count=1,
                                            initial_speed_m_s=5.0, group_id="g0", member_ids=["a", "b"],
                                            target_id="t", formation_prior="loose", **kw)
        mon = [row("f", 0, True), row("f", 1, False), row("f", 2, True)]
        tra = [row("f", 0, True), row("f", 1, True)]
        rows = paired_rows(mon, tra, mon, tra)
        self.assertEqual([(r["family_id"], r["draw_index"]) for r in rows], [("f", 0), ("f", 1), ("f", 2)])
        self.assertIsNone(rows[2]["transit_full_success"])
        self.assertEqual(rows[0]["common_field_diffs"], [])
        cells = four_cell(rows)["all"]
        self.assertEqual((cells["both"], cells["only_monitor"], cells["only_transit"], cells["unknown"]), (1, 0, 1, 1))

    def test_no_revisit_bound(self):
        """斜率证明的数值上界：tan75° 对应约 115.91 m < 150 m。"""
        from v08.motion.transit_numeric import SLOPE_MAX, no_revisit_bound_m
        self.assertAlmostEqual(no_revisit_bound_m(), 30.0 * math.sqrt(1.0 + SLOPE_MAX ** 2), places=12)
        self.assertLess(no_revisit_bound_m(), 150.0)
        self.assertLess(SLOPE_MAX, math.sqrt(24.0))


if __name__ == "__main__":
    unittest.main()
