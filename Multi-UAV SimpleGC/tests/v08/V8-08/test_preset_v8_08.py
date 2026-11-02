"""V8-08 预置测试（规划审查方编写，实现方不得修改或删除）。

运行（在 Multi-UAV SimpleGC 目录下，conda 环境 llm）:
    python -B -m unittest discover -s tests/v08/V8-08 -p "test_preset_*.py" -v

前四类是纯函数（不跑仿真）；TestGuidedRun 跑约 12 次短仿真（约 20–40 s）。
独立预期的来源：
- 手算与解析解：圆上等距点的离散曲率 α/c；匀加减速的速度 √(2·a·s) 与梯形用时 L/v + v/a；
  恒定扰动加速度 d 下的稳态横向偏移 d·τ/k_pos（控制器 (v_des − v)/τ 与纠偏 k_pos·e 平衡）；
- 数学性质：速度已等于参考速度时控制器请求恰为向心加速度（控制器逆）；扰动为空时与冻结引擎逐位相同；
- 冻结动力学核心的限制：水平加速度 ≤ 3.75 m/s²（r3 配置）；跟踪管 0.5 m（r3 6.6）；停止判定半径 1 m、速度 0.15 m/s（sim.json）；
- 规划审查方 11-02 原型实测（作回归基准，容差远大于实测值，见各条注释）。
"""
import dataclasses
import math
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from swarm_sim.fast_dynamics.contracts import PlantState  # noqa: E402
from swarm_sim.fast_dynamics.controllers import VelocityController  # noqa: E402
from swarm_sim.fast_dynamics.engine import SynchronousEngine  # noqa: E402
from swarm_sim.fast_dynamics.reference_r3 import candidate_config  # noqa: E402
from v08.config import load_config  # noqa: E402
from v08.sim.types import MemberBoundaryState, SimContractError  # noqa: E402
from v08.sim.stitch import stitch  # noqa: E402
from v08.sim.guidance import desired_velocity, make_curve, nominal_time, project, speed_profile  # noqa: E402
from v08.sim.kernel import InjectableEngine, member_config  # noqa: E402
from v08.sim.guided import GuidedSegmentPlan, run_guided_segment  # noqa: E402

G = load_config("guidance").values
TAU = candidate_config().controller.velocity_response_time_s          # 0.475 s
ALT = 120.0


def dense_turn(R, ang_deg, lin, lout, ds=0.5):
    """沿 +x 进入原点，绕 (0, R) 逆时针转 ang_deg，再沿终点切向直飞 lout；点距约 ds。"""
    P = [(x, 0.0) for x in np.arange(-lin, 0, ds)]
    n = max(1, math.ceil(R * math.radians(ang_deg) / ds))
    P += [(R * math.sin(a), R - R * math.cos(a)) for a in np.linspace(0, math.radians(ang_deg), n + 1)]
    a = math.radians(ang_deg)
    E = np.array([R * math.sin(a), R - R * math.cos(a)]); t = np.array([math.cos(a), math.sin(a)])
    m = max(1, math.ceil(lout / ds))
    P += [tuple(E + t * x) for x in np.linspace(0, lout, m + 1)[1:]]
    return np.array(P)


def line_pts(x0, x1, ds=0.5):
    n = int(round((x1 - x0) / ds))
    return np.c_[np.linspace(x0, x1, n + 1), np.zeros(n + 1)]


def arclen(P):
    return np.r_[0.0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]


def curve(P):
    return make_curve(P, max_chord_m=G["max_chord_m"], max_turn_rad=G["max_turn_per_chord_rad"])


def start(P, k=0, tau=0):
    return MemberBoundaryState("m", k, tau, (float(P[0, 0]), float(P[0, 1]), ALT), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


def plan(P, breaks, end_s, stops=(), k=0):
    return GuidedSegmentPlan("m", k, tuple(map(tuple, np.asarray(P).tolist())), ALT, breaks, float(end_s), stops)


def speed(r):
    return np.hypot(r.v[:, 0], r.v[:, 1])


class TestCurve(unittest.TestCase):
    def test_circle_curvature(self):
        R, c_ang = 50.0, 0.01                                   # 等角步长 0.01 rad
        a = np.arange(0, 1.0, c_ang)
        P = np.c_[R * np.cos(a), R * np.sin(a)]                 # 逆时针
        cv = curve(P)
        c = 2 * R * math.sin(c_ang / 2)                         # 弦长
        np.testing.assert_allclose(cv.kappa[1:-1], c_ang / c, rtol=1e-9)   # 离散曲率 = 方向差 / 平均弦长
        self.assertAlmostEqual(cv.kappa[0], cv.kappa[1]); self.assertAlmostEqual(cv.kappa[-1], cv.kappa[-2])
        self.assertLess(abs(cv.kappa[5] * R - 1.0), 1e-4)
        cw = curve(P[::-1])
        self.assertTrue(np.all(cw.kappa < 0))                   # 顺时针为负

    def test_straight(self):
        cv = curve(line_pts(0, 10))
        np.testing.assert_allclose(cv.s, np.arange(21) * 0.5, atol=1e-12)
        np.testing.assert_allclose(cv.kappa, 0.0, atol=1e-12)
        self.assertAlmostEqual(cv.length, 10.0)

    def test_rejects(self):
        corner = np.r_[line_pts(0, 5), [[5.0, 0.5], [5.0, 1.0]]]  # 90° 折角
        for bad in (corner, np.array([[0.0, 0.0], [1.5, 0.0]]), np.array([[0.0, 0.0], [0.0, 0.0], [0.5, 0.0]]),
                    np.array([[0.0, 0.0]]), np.array([[0.0, 0.0], [np.nan, 0.0]])):
            with self.assertRaises(SimContractError):
                curve(bad)


class TestSpeedProfile(unittest.TestCase):
    def test_trapezoid(self):
        cv = curve(line_pts(0, 200))
        v = speed_profile(cv, ((0.0, 10.0),), a_lat=2.0, a_lon=1.5, v_max=12.0, v0=0.0, v_end=0.0)
        s = cv.s
        np.testing.assert_allclose(v, np.minimum(10.0, np.minimum(np.sqrt(3 * s), np.sqrt(3 * (200 - s)))), atol=1e-9)
        # 梯形用时 L/v + v/a = 20 + 6.667 s；加速段与匀速段的分界落在一条弦内，误差 ≤ 0.5 m / 10 m/s
        self.assertAlmostEqual(nominal_time(cv, v, 0.0, 200.0), 200 / 10 + 10 / 1.5, delta=0.05)

    def test_curvature_cap(self):
        R = 20.0
        a = np.arange(0, 2.0, 0.5 / R)
        cv = curve(np.c_[R * np.cos(a), R * np.sin(a)])
        v = speed_profile(cv, ((0.0, 10.0),), a_lat=2.0, a_lon=1.5, v_max=12.0)
        np.testing.assert_allclose(v, np.sqrt(2.0 / cv.kappa), rtol=1e-12)      # = √(a_lat/κ)
        self.assertAlmostEqual(float(v[10]), math.sqrt(40.0), delta=1e-3)

    def test_speed_break_and_stop(self):
        cv = curve(line_pts(0, 300))
        s = cv.s
        v = speed_profile(cv, ((0.0, 10.0), (150.0, 4.0)), a_lat=2.0, a_lon=1.5, v_max=12.0)
        exp = np.where(s < 150, np.minimum(10.0, np.sqrt(16 + 3 * np.maximum(150 - s, 0.0))), 4.0)
        np.testing.assert_allclose(v, exp, atol=1e-9)                       # 变速前按 a_lon 提前减速
        v = speed_profile(cv, ((0.0, 8.0),), a_lat=2.0, a_lon=1.5, v_max=12.0, stops=(100.0,))
        np.testing.assert_allclose(v, np.minimum(8.0, np.sqrt(3 * np.abs(s - 100))), atol=1e-9)
        for kw in (dict(speed_breaks=((1.0, 5.0),)), dict(speed_breaks=((0.0, 13.0),)),
                   dict(speed_breaks=((0.0, 5.0), (0.0, 6.0))), dict(speed_breaks=((0.0, 5.0),), stops=(100.2,))):
            with self.assertRaises(SimContractError):
                speed_profile(cv, a_lat=2.0, a_lon=1.5, v_max=12.0, **kw)


class TestGuidanceLaw(unittest.TestCase):
    def test_controller_inverse(self):
        # 速度已等于参考速度、位置在曲线上时，冻结控制器的加速度请求恰为 κ·v²·N（向心加速度）
        R, vr = 50.0, 5.0
        a = np.arange(0, 1.0, 0.01)
        cv = curve(np.c_[R * np.cos(a), R * np.sin(a)])
        v = speed_profile(cv, ((0.0, vr),), a_lat=100.0, a_lon=1.5, v_max=12.0)
        i = 40                                                  # 取第 i 条弦的中点（节点处两条弦等距，按规格取较小下标）
        mid = (cv.xy[i] + cv.xy[i + 1]) / 2
        p = np.array([mid[0], mid[1], ALT])
        T = cv.tangent[i]; N = np.array([-T[1], T[0]])
        s_mid = (cv.s[i] + cv.s[i + 1]) / 2
        vdes, s_p = desired_velocity(cv, v, p, s_mid, tau=TAU, k_pos=1.0, lookahead_m=1.0, slope_half_m=0.5,
                                     s_limit=cv.length, window_m=5.0, altitude=ALT)
        self.assertAlmostEqual(s_p, s_mid, places=9)
        ctrl = VelocityController(candidate_config().vehicle_profile, candidate_config().controller)
        st = PlantState(np.array([p]), np.array([[vr * T[0], vr * T[1], 0.0]]), np.zeros((1, 3)))
        req = ctrl.command(st, vdes[None]).values[0]
        np.testing.assert_allclose(req[:2], cv.kappa[i] * vr * vr * N, atol=1e-9)
        self.assertAlmostEqual(req[2], 0.0, places=12)

    def test_projection_window_on_self_overlap(self):
        # 直线进入 (0,0)，绕 (0,5) 逆时针整圈回到 (0,0)，再沿 +x 离开：(0,0) 在弧长约 20 m 与 51.4 m 处各出现一次
        P1 = line_pts(-20, 0)
        n = math.ceil(2 * math.pi * 5 / 0.5)
        a = np.linspace(0, 2 * math.pi, n + 1)
        circ = np.c_[5 * np.sin(a), 5 - 5 * np.cos(a)]
        P = np.r_[P1, circ[1:], line_pts(0, 20)[1:]]
        cv = curve(P)
        s2 = 20.0 + n * 2 * 5 * math.sin(math.pi / n)
        _, s_a, _ = project(cv, (0.05, 0.01), 20.0, G["projection_window_m"])
        _, s_b, _ = project(cv, (0.05, 0.01), s2 - 0.2, G["projection_window_m"])
        self.assertAlmostEqual(s_a, 20.05, delta=0.02)                       # 仍在第一支
        self.assertAlmostEqual(s_b, s2 + 0.05, delta=0.02)                   # 仍在第二支


class TestKernel(unittest.TestCase):
    def test_injectable_engine_identity(self):
        cfg = candidate_config()
        st = PlantState(np.array([[0.0, 0.0, ALT]]), np.zeros((1, 3)), np.zeros((1, 3)))
        des = lambda t, s: np.array([[3 * math.cos(t / 5e6), 3 * math.sin(t / 5e6), 0.0]])
        a, b = SynchronousEngine(cfg, st), InjectableEngine(cfg, st, None, 0)
        for _ in range(500):
            a.step(des); b.step(des)
        self.assertTrue(np.array_equal(a.state.p, b.state.p) and np.array_equal(a.state.v, b.state.v)
                        and np.array_equal(a.state.a, b.state.a))
        self.assertEqual(len(a.samples), len(b.samples))
        self.assertTrue(all(np.array_equal(x.p, y.p) for x, y in zip(a.samples, b.samples)))

    def test_member_config(self):
        base = candidate_config()
        self.assertEqual(member_config(None), base)
        c = member_config({"response_time_s": 0.2, "velocity_response_time_s": 0.5})
        self.assertEqual(c.vehicle_profile.response_time_s, 0.2)
        self.assertEqual(c.controller.velocity_response_time_s, 0.5)
        self.assertEqual(c.vehicle_profile.max_accel_xy_m_s2, base.vehicle_profile.max_accel_xy_m_s2)
        for bad in ({"wind": 1.0}, {"response_time_s": -0.1}, {"max_jerk_m_s3": float("nan")}):
            with self.assertRaises(ValueError):
                member_config(bad)


class TestGuidedRun(unittest.TestCase):
    def test_straight_final(self):
        P = line_pts(0, 300)
        r = run_guided_segment(plan(P, ((0.0, 8.0),), 300.0), start(P), final=True)
        self.assertEqual(r.status, "ok")
        sp = speed(r); m = (r.p[:, 0] > 100) & (r.p[:, 0] < 200)
        self.assertLess(np.abs(sp[m] - 8.0).max(), 0.05)
        self.assertLess(np.abs(r.p[:, 1]).max(), 0.01)
        self.assertLessEqual(math.hypot(r.p[-1, 0] - 300.0, r.p[-1, 1]), 1.0)     # sim.json terminal_radius_m
        last2 = r.tau_us >= r.tau_us[-1] - 1_900_000
        self.assertLessEqual(sp[last2].max(), 0.15 + 0.05)                     # 终点保持 2 s
        self.assertTrue(np.all(r.tau_us[r.tau_us < 20_000_000] >= 0))
        self.assertLess(np.abs(r.p[r.tau_us < 20_000_000, :2] - P[0]).max(), 1e-9)   # 释放前停在起点

    def test_arc_speed_and_tube(self):
        R = 20.0
        P = dense_turn(R, 120, 100, 100)
        r = run_guided_segment(plan(P, ((0.0, 10.0),), arclen(P)[-1]), start(P), final=True)
        self.assertEqual(r.status, "ok")
        rel = r.p[:, :2] - [0.0, R]; ang = np.arctan2(rel[:, 1], rel[:, 0]); rad = np.hypot(*rel.T)
        on = (rad < R + 2) & (ang > -math.pi / 2 + math.radians(30)) & (ang < -math.pi / 2 + math.radians(90))
        self.assertGreater(on.sum(), 20)
        self.assertLess(np.abs(speed(r)[on] - math.sqrt(G["a_lat_m_s2"] * R)).max(), 0.1)   # 原型实测 +0.035
        self.assertLess(np.abs(rad[on] - R).max(), 0.5)                     # 跟踪管；原型实测 0.026 m
        self.assertLessEqual(np.hypot(r.a[:, 0], r.a[:, 1]).max(), 3.75 + 1e-9)   # 冻结加速度上限

    def test_speed_change_mid_arc(self):
        # 弧中途 10 → 4 m/s，不分段：没有超出两个目标速度之外的鼓包或下陷（旧跟踪器分段重启时为 1.3–3.8 m/s，V8-06）
        R = 60.0
        P = dense_turn(R, 120, 100, 100); s = arclen(P); smid = float(s[200 + 126])
        r = run_guided_segment(plan(P, ((0.0, 10.0), (smid, 4.0)), s[-1]), start(P), final=True)
        rel = r.p[:, :2] - [0.0, R]; ang = np.arctan2(rel[:, 1], rel[:, 0]); rad = np.hypot(*rel.T)
        on = (rad < R + 3) & (ang > -math.pi / 2 + math.radians(10)) & (ang < -math.pi / 2 + math.radians(110))
        sp = speed(r)[on]
        self.assertGreater(sp.min(), 4.0 - 0.3)                             # 原型实测下陷 0.115
        self.assertLess(sp.max(), 10.0 + 0.3)
        self.assertLess(np.abs(rad[on] - R).max(), 0.5)
        late = on & (ang > -math.pi / 2 + math.radians(100))
        self.assertLess(np.abs(speed(r)[late] - 4.0).max(), 0.05)

    def test_split_and_resume(self):
        R = 20.0
        P = dense_turn(R, 120, 100, 150); s = arclen(P)
        iE = 200 + math.ceil(R * math.radians(120) / 0.5)                     # 圆弧终点（接直线）
        sE = float(s[iE])
        un = run_guided_segment(plan(P, ((0.0, 10.0),), s[-1]), start(P), final=True)
        r0 = run_guided_segment(plan(P[:iE + 11], ((0.0, 10.0),), sE), start(P), final=False)   # 尾部 5 m
        self.assertEqual(r0.status, "ok")
        e = r0.end_state
        self.assertEqual(e.tau_us, r0.executed_switch_tau_us)
        self.assertEqual(e.tau_us % 100_000, 0)
        iu = {int(t): i for i, t in enumerate(un.tau_us)}
        j = [iu[int(t)] for t in r0.tau_us]
        self.assertEqual(float(np.abs(r0.p - un.p[j]).max()), 0.0)          # 越过前逐位相同
        r1 = run_guided_segment(plan(P[iE:], ((0.0, 10.0),), s[-1] - sE, k=1), e, final=True)
        self.assertEqual(r1.tau_us[0], e.tau_us)
        k = [(a, iu[int(t)]) for a, t in enumerate(r1.tau_us) if int(t) in iu and t <= e.tau_us + 20_000_000]
        a = [x for x, _ in k]; b = [y for _, y in k]
        # 续跑段的剖面从实测速度起算，与整段的剖面略有差异：位置差在跟踪管内，速度差不超过控制器滞后 τ·a_lon
        self.assertLess(np.abs(r1.p[a, :2] - un.p[b, :2]).max(), 0.5)       # 原型实测 0.26 m
        self.assertLess(np.abs(r1.v[a, :2] - un.v[b, :2]).max(), TAU * G["a_lon_m_s2"])   # 原型实测 0.14 m/s
        track = stitch([r0, r1])["m"]                                        # V8-04 的拼接与连续性检查照常通过
        self.assertTrue(np.all(np.diff(track.tau_us) == 100_000))
        self.assertEqual(track.executed_switch_tau_us, (e.tau_us,))

    def test_stop_and_hold(self):
        P = line_pts(0, 300)
        r = run_guided_segment(plan(P, ((0.0, 8.0),), 300.0, stops=((100.0, 10.0),)), start(P), final=True)
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.pieces[0].stops_done, 2)                          # 中途停止点 + 终点
        held = (np.hypot(r.p[:, 0] - 100.0, r.p[:, 1]) <= 1.0) & (speed(r) <= 0.15)
        t = r.tau_us[held]
        self.assertGreaterEqual((t.max() - t.min()) / 1e6, 10.0 - 0.1)

    def test_disturbance_offset(self):
        P = line_pts(0, 400)
        d = 0.3
        r = run_guided_segment(plan(P, ((0.0, 6.0),), 400.0), start(P), final=True,
                               disturbance=lambda tau, st: np.array([[0.0, d, 0.0]]))
        m = (r.p[:, 0] > 150) & (r.p[:, 0] < 300)
        self.assertAlmostEqual(float(r.p[m, 1].mean()), d * TAU / G["k_pos_per_s"], delta=0.002)   # 0.1425 m

    def test_determinism_and_timeout(self):
        P = dense_turn(30.0, 90, 50, 50)
        x = run_guided_segment(plan(P, ((0.0, 7.0),), arclen(P)[-1]), start(P), final=True)
        y = run_guided_segment(plan(P, ((0.0, 7.0),), arclen(P)[-1]), start(P), final=True)
        self.assertTrue(np.array_equal(x.p, y.p) and np.array_equal(x.tau_us, y.tau_us))
        g = load_config("guidance")
        tight = dataclasses.replace(g, values={**g.values, "budget_factor": -0.9, "budget_const_s": 1.0})
        z = run_guided_segment(plan(P, ((0.0, 7.0),), arclen(P)[-1]), start(P), final=True, guidance=tight)
        self.assertEqual(z.status, "sim_timeout")

    def test_input_checks(self):
        P = line_pts(0, 100)
        with self.assertRaises(SimContractError):                            # 非最后一段缺尾部
            run_guided_segment(plan(P, ((0.0, 5.0),), 98.0), start(P), final=False)
        with self.assertRaises(SimContractError):                            # 起点不在当前位置
            run_guided_segment(plan(P + [0.0, 3.0], ((0.0, 5.0),), 100.0), start(P), final=True)
        with self.assertRaises(SimContractError):                            # 最后一段段末点须为曲线终点
            run_guided_segment(plan(P, ((0.0, 5.0),), 50.0), start(P), final=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
