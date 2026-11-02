"""V8-06 预置测试（规划审查方编写，实现方不得修改或删除）。

运行（在 Multi-UAV SimpleGC 目录下，conda 环境 llm）:
    python -B -m unittest discover -s tests/v08/V8-06 -p "test_preset_*.py" -v

前三类只测纯函数，不跑仿真；TestSimProperties 跑 4 次短仿真（约 20–40 s）。
独立预期的来源：
- 手算几何：圆弧端点、点到线段与圆弧的距离、极坐标曲线曲率公式在 r'=0 处的值；
- 冻结驻留判据 criteria/0.7-r1 的定义（20 s 窗口、30 m 半径、首尾 30 m）：静止点必判驻留，4 m/s 直线必不判；
- 数学性质：对数插值在节点处取表值、端点外取端值；仿真的确定性；
- 冻结仿真器的已知行为（规划审查方在云端用冻结 fastsim 实测，作回归基准，见各测试注释）。
"""
import math
import os
import sys
import types
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from v08.calibration.geometry import (arc, arc_points, build_waypoints, distance_to_path,  # noqa: E402
                                      distance_to_polyline, interp_log, line, path_length,
                                      polar_curvature, polar_loop_points, polar_loop_points_adaptive,
                                      shape_teardrop, shape_turn)
from v08.calibration.metrics import (arc_steady_mask, away_from, dwell_detected, overshoot_along,  # noqa: E402
                                     polar_progress, speed_xy)
from v08.calibration import runner  # noqa: E402
import v08.sim.adapter as AD  # noqa: E402
from v08.sim.types import MemberBoundaryState, MemberPiece, MemberSegmentPlan, SimContractError  # noqa: E402


class TestGeometry(unittest.TestCase):
    def test_arc_points(self):
        p = arc_points((0.0, 0.0), 10.0, 0.0, math.pi / 2, 5.0)      # 弧长 15.708 → ceil(3.14)=4 段
        self.assertEqual(p.shape, (5, 2))
        np.testing.assert_allclose(p[0], [10.0, 0.0], atol=1e-12)
        np.testing.assert_allclose(p[-1], [0.0, 10.0], atol=1e-12)
        np.testing.assert_allclose(np.linalg.norm(p, axis=1), 10.0, atol=1e-12)
        q = arc_points((0.0, 0.0), 10.0, 0.0, -math.pi / 2, 100.0)   # 间距大于弧长时至少 1 段；负角为顺时针
        np.testing.assert_allclose(q, [[10.0, 0.0], [0.0, -10.0]], atol=1e-12)

    def test_shape_turn_and_waypoints(self):
        prims = shape_turn(20.0, 90.0, 50.0, 30.0)
        # 圆心 (0,20)，从 -90° 逆时针转 90° 到 (20,20)，出口沿 +y 走 30 m 到 (20,50)
        np.testing.assert_allclose(prims[2][1], [20.0, 20.0], atol=1e-12)
        np.testing.assert_allclose(prims[2][2], [20.0, 50.0], atol=1e-12)
        W = build_waypoints(prims, 10.0, 120.0)
        self.assertEqual(W.shape, (7, 3))                              # 2 + 4 + 1（圆弧起点与直线终点去重）
        np.testing.assert_allclose(W[0], [-50.0, 0.0, 120.0], atol=1e-12)
        np.testing.assert_allclose(W[-1], [20.0, 50.0, 120.0], atol=1e-12)
        self.assertTrue(np.all(np.linalg.norm(np.diff(W[:, :2], axis=0), axis=1) > 1e-9))
        self.assertTrue(np.all(W[:, 2] == 120.0))
        self.assertAlmostEqual(path_length(prims), 50.0 + 10.0 * math.pi + 30.0, places=9)

    def test_shape_turn_u(self):
        prims = shape_turn(15.0, 180.0, 100.0, 100.0)
        np.testing.assert_allclose(prims[2][1], [0.0, 30.0], atol=1e-12)    # 平行出口，间隔 2R
        np.testing.assert_allclose(prims[2][2], [-100.0, 30.0], atol=1e-9)

    def test_shape_teardrop(self):
        prims = shape_teardrop(10.0, 50.0)
        self.assertEqual(len(prims), 4)
        np.testing.assert_allclose(prims[3][1], [20.0, 0.0], atol=1e-12)    # 回到 y=0 线，朝 -x
        np.testing.assert_allclose(prims[3][2], [-30.0, 0.0], atol=1e-12)
        d = distance_to_path([[10.0, -10.0], [20.0, -20.0], [30.0, -10.0], [-30.0, 0.0]], prims)
        np.testing.assert_allclose(d, 0.0, atol=1e-9)
        self.assertAlmostEqual(path_length(prims), 2 * 50.0 + 10.0 * (math.pi / 2 + 1.5 * math.pi), places=9)

    def test_distance_to_path(self):
        d = distance_to_path([[5.0, 3.0], [13.0, 4.0]], [line((0, 0), (10, 0))])
        np.testing.assert_allclose(d, [3.0, 5.0], atol=1e-12)
        a = [arc((0.0, 0.0), 10.0, 0.0, math.pi / 2)]
        d = distance_to_path([[20.0, 0.0], [-10.0, -10.0], [3.0, 4.0]], a)
        np.testing.assert_allclose(d, [10.0, math.sqrt(500.0), 5.0], atol=1e-9)

    def test_distance_to_polyline(self):
        W = [[0.0, 0.0, 1.0], [10.0, 0.0, 1.0], [10.0, 10.0, 1.0]]
        d = distance_to_polyline([[5.0, 3.0], [13.0, 4.0], [10.0, -2.0], [-3.0, -4.0]], W)
        np.testing.assert_allclose(d, [3.0, 3.0, 2.0, 5.0], atol=1e-12)

    def test_polar(self):
        self.assertAlmostEqual(float(polar_curvature(100.0, [], 0.7)), 0.01, places=15)
        # r'=0 处：κ = (r + a k²) / r²，r = ρ0 + a
        self.assertAlmostEqual(float(polar_curvature(100.0, [(10.0, 2, 0.0)], 0.0)), 150.0 / 12100.0, places=12)
        # 两个谐波在 φ=0 处 r'=0：r = 100+10+5 = 115，r'' = -(10·4 + 5·9) = -85，κ = (115² + 115·85)/115³
        self.assertAlmostEqual(float(polar_curvature(100.0, [(10.0, 2, 0.0), (5.0, 3, 0.0)], 0.0)),
                               (115.0 ** 2 + 115.0 * 85.0) / 115.0 ** 3, places=12)
        P, phis = polar_loop_points(200.0, [], 0.0, math.pi, 20.0)
        np.testing.assert_allclose(np.linalg.norm(P, axis=1), 200.0, atol=1e-9)
        steps = np.linalg.norm(np.diff(P, axis=0), axis=1)
        chord = 2 * 200.0 * math.sin(20.0 / 400.0)
        np.testing.assert_allclose(steps[:-1], chord, rtol=1e-3)       # 末段可短于间距
        self.assertLessEqual(steps[-1], chord * (1 + 1e-3))
        np.testing.assert_allclose(P[-1], [-200.0, 0.0], atol=1e-6)
        self.assertAlmostEqual(phis[0], 0.0)

    def test_polar_adaptive(self):
        # 圆上曲率半径处处为 200：自适应间距与固定间距 20 m 逐点相同
        P, _ = polar_loop_points(200.0, [], 0.0, math.pi, 20.0)
        Q, _ = polar_loop_points_adaptive(200.0, [], 0.0, math.pi, lambda R: 20.0)
        np.testing.assert_allclose(P, Q, atol=1e-9)
        seen = []
        polar_loop_points_adaptive(200.0, [], 0.0, math.pi / 2, lambda R: seen.append(R) or 50.0)
        np.testing.assert_allclose(seen, 200.0, rtol=1e-9)              # 传给间距函数的是局部曲率半径
        H = [(20.0, 3, 0.4)]                                               # 凸曲线，曲率半径约 205–784 m
        Q, ph = polar_loop_points_adaptive(300.0, H, 0.0, 2 * math.pi, lambda R: 0.1 * R)
        steps = np.linalg.norm(np.diff(Q, axis=0), axis=1)
        Rloc = 1.0 / np.abs(polar_curvature(300.0, H, ph[:-1]))
        np.testing.assert_allclose(steps[:-1], 0.1 * Rloc[:-1], rtol=2e-2)  # 弦长≈弧长（间距/半径 = 0.1）

    def test_interp_log(self):
        v = interp_log([10.0, 20.0, 40.0, 5.0, 100.0], [10.0, 40.0], [1.0, 3.0])
        np.testing.assert_allclose(v, [1.0, 2.0, 3.0, 1.0, 3.0], atol=1e-12)   # 20 是 10 与 40 的对数中点


class TestMetrics(unittest.TestCase):
    def test_speed_and_overshoot(self):
        np.testing.assert_allclose(speed_xy(np.array([[3.0, 4.0, 9.0]])), [5.0])
        xy = np.array([[98.0, 0.0], [99.5, 0.2], [100.8, 0.1], [101.2, 0.0], [101.0, 0.0]])
        self.assertAlmostEqual(overshoot_along(xy, (100.0, 0.0), (1.0, 0.0)), 1.2, places=12)
        self.assertEqual(overshoot_along(xy[:2], (100.0, 0.0), (1.0, 0.0)), 0.0)

    def test_arc_steady_mask(self):
        ang = np.radians([5.0, 20.0, 90.0, 170.0, 179.0])
        xy = np.c_[10 * np.cos(ang), 10 * np.sin(ang)]
        m = arc_steady_mask(xy, (0.0, 0.0), 10.0, 0.0, math.pi, margin_deg=15.0, max_dist=2.0)
        self.assertEqual(m.tolist(), [False, True, True, False, False])
        far = arc_steady_mask(np.array([[0.0, 13.0]]), (0.0, 0.0), 10.0, 0.0, math.pi)
        self.assertEqual(far.tolist(), [False])

    def test_polar_progress_and_away(self):
        ang = np.linspace(0.1, 0.1 + 2.5 * math.pi, 400)                    # 逆时针 1.25 圈
        xy = np.c_[300 * np.cos(ang), 300 * np.sin(ang)]
        pr = polar_progress(xy, 0.0)
        np.testing.assert_allclose(pr, ang, atol=1e-9)
        self.assertEqual(away_from(np.array([[0.0, 0.0], [0.0, 41.0]]), (0.0, 40.0), 40.0).tolist(), [False, False])
        self.assertEqual(away_from(np.array([[0.0, -0.5]]), (0.0, 40.0), 40.0).tolist(), [True])

    def test_dwell_detector_definition(self):
        t = np.arange(0, 600, dtype=np.int64) * 100_000                     # 60 s
        still = np.zeros((600, 2))
        self.assertTrue(dwell_detected(still, t, 0))
        moving = np.c_[4.0 * t / 1e6, np.zeros(600)]                         # 4 m/s 直线
        self.assertFalse(dwell_detected(moving, t, 0))
        pre = np.where((t < 30_000_000)[:, None], 0.0, np.c_[4.0 * (t - 30_000_000) / 1e6, np.zeros(600)])
        self.assertFalse(dwell_detected(pre, t, 30_000_000))                # 释放前静止的帧不计入
        keep = t >= 45_000_000                                               # 只留最后 15 s（不足 20 s 窗口）
        self.assertFalse(dwell_detected(still, t, 0, extra_mask=keep))       # 附加掩码与释放条件取交集
        self.assertTrue(dwell_detected(still, t, 0, extra_mask=t >= 30_000_000))


class TestRunnerPure(unittest.TestCase):
    def test_config_with(self):
        c = runner.config_with(extension_length_m=5)
        self.assertEqual(c.values["extension_length_m"], 5.0)
        self.assertEqual(c.values["join_max_distance_m"], 2.0)               # 其余参数不变
        self.assertEqual(c.name, "sim")

    def test_continuation_piece_waypoints(self):
        W = [(0.0, 0.0, 1.0), (10.0, 0.0, 1.0), (20.0, 0.0, 1.0), (20.0, 10.0, 1.0), (20.0, 30.0, 1.0)]
        out = runner.continuation_piece_waypoints(W, 1, 15.0)    # 从 W[1] 累计 10、20 ≥ 15 → 取到 W[3]
        self.assertEqual(out, tuple(W[:4]))
        out = runner.continuation_piece_waypoints(W, 3, 25.0)    # 后续只有 20 m，不足部分沿末腿直线补 5 m
        self.assertEqual(out[:5], tuple(W))
        np.testing.assert_allclose(out[5], (20.0, 35.0, 1.0), atol=1e-12)

    def test_continuation_check_scoped(self):
        W = ((0.0, 0.0, 1.0), (50.0, 0.0, 1.0), (80.0, 10.0, 1.0), (100.0, 40.0, 1.0))
        cfg = runner.config_with(extension_length_m=30.0)
        st = MemberBoundaryState("m", 0, 0, W[0], (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        plan = MemberSegmentPlan("m", 0, (MemberPiece(W, 1, 6.0), MemberPiece(W[1:], 2, 6.0)))
        orig = AD._check_piece
        with self.assertRaises(SimContractError):                        # 默认：延伸段必须共线
            AD._check_inputs(plan, st, True, cfg.values)
        with runner.allow_continuation_extension():
            AD._check_inputs(plan, st, True, cfg.values)                 # 放开后：沿后续航线的延伸段合法
            short = MemberSegmentPlan("m", 0, (MemberPiece(W[:3], 1, 6.0), MemberPiece(W[1:], 2, 6.0)))
            with self.assertRaises(SimContractError):                    # 后续航线 31.6 m ≥ 30 合法；
                AD._check_inputs(short, st, True, runner.config_with(extension_length_m=40.0).values)  # 不足 40 仍报错
            bad = MemberSegmentPlan("m", 0, (MemberPiece(W, 1, 99.0), MemberPiece(W[1:], 2, 6.0)))
            with self.assertRaises(SimContractError):                    # 其余检查（速度上限）照常
                AD._check_inputs(bad, st, True, cfg.values)
        self.assertIs(AD._check_piece, orig)                             # 结束后还原
        try:
            with runner.allow_continuation_extension():
                raise KeyError("x")
        except KeyError:
            pass
        self.assertIs(AD._check_piece, orig)                             # 异常时也还原

    def test_compare_runs(self):
        t = np.arange(10, dtype=np.int64) * 100_000
        a = types.SimpleNamespace(tau_us=t, p=np.c_[t / 1e5, np.zeros(10), np.zeros(10)], v=np.zeros((10, 3)))
        b = types.SimpleNamespace(tau_us=t[2:], p=np.c_[t[2:] / 1e5, np.full(8, 3.0), np.zeros(8)],
                                  v=np.c_[np.zeros(8), np.full(8, 4.0), np.zeros(8)])
        r = runner.compare_runs(a, b, 0, 500_000)                         # 共同时刻 0.2–0.5 s
        self.assertAlmostEqual(r["dp_max"], 3.0)
        self.assertAlmostEqual(r["dv_max"], 4.0)
        self.assertAlmostEqual(r["dp_first"], 3.0)
        self.assertIsNone(runner.compare_runs(a, b, 0, 100_000))


class TestSimProperties(unittest.TestCase):
    """冻结仿真器上的性质（规划审查方 11-02 云端实测为逐位相同，容差取 1e-6 只为跨平台浮点）。"""

    def test_straight_split_equals_unsplit(self):
        # 直线上共线航点 + 30 m 延伸段：跟踪器只在剩余距离 < 2×0.575 s×v（10 m/s 时 11.5 m）时为终点减速，
        # 越过帧之前看不到延伸段的终点，故分段与整段相同（sim.json extension_length_m 的来源说明）
        W = np.array([[-300.0, 0.0, 120.0], [0.0, 0.0, 120.0], [300.0, 0.0, 120.0]])
        un = runner.fly(W, 10.0)
        sp = runner.fly_split(W, 1, 10.0, 10.0, mode="straight")
        self.assertEqual((un.status, sp.status), ("ok", "ok"))
        te = sp.pieces[0].tau_end_us
        r = runner.compare_runs(sp, un, te - 10_000_000, te + 30_000_000)
        self.assertLessEqual(r["dp_max"], 1e-6)
        self.assertLessEqual(r["dv_max"], 1e-6)

    def test_continuation_split_exact_at_crossing(self):
        # 圆弧中点处分段、延伸段沿后续航线：越过帧之前两次仿真的航线在跟踪器视野内相同，越过时刻状态相同
        W = build_waypoints(shape_turn(60.0, 120.0, 100.0, 60.0), 12.0, 120.0)
        E = 1 + (len(W) - 3) // 2
        un = runner.fly(W, 10.0)
        sp = runner.fly_split(W, E, 10.0, 10.0, mode="continuation")
        te = sp.pieces[0].tau_end_us
        r = runner.compare_runs(sp, un, te, te)
        self.assertLessEqual(r["dp_first"], 1e-6)
        self.assertLessEqual(r["dv_first"], 1e-6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
