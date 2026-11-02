"""V8-08 实现方自加测试：补充预置测试未覆盖的输入检查与接口约定。

运行（在 Multi-UAV SimpleGC 目录下，conda 环境 llm）:
    python -B -m unittest discover -s tests/v08/V8-08 -p "test_own_*.py" -v
"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from v08.config import load_config  # noqa: E402
from v08.sim.guidance import make_curve  # noqa: E402
from v08.sim.guided import GuidedSegmentPlan, run_guided_segment  # noqa: E402
from v08.sim.types import MemberBoundaryState, SimContractError  # noqa: E402

ALT = 120.0
G = load_config("guidance").values


def line_pts(x0, x1, ds=0.5):
    n = int(round((x1 - x0) / ds))
    return np.c_[np.linspace(x0, x1, n + 1), np.zeros(n + 1)]


def plan(P, end_s, stops=(), k=0, delay=0.0, breaks=((0.0, 5.0),)):
    return GuidedSegmentPlan("m", k, tuple(map(tuple, P.tolist())), ALT, breaks, float(end_s), stops, delay)


def start(P, k=0, tau=0, v=(0.0, 0.0, 0.0)):
    return MemberBoundaryState("m", k, tau, (float(P[0, 0]), float(P[0, 1]), ALT), v, (0.0, 0.0, 0.0))


class TestOwnInputChecks(unittest.TestCase):
    def test_bad_stops(self):
        P = line_pts(0, 100)
        for stops in (((0.0, 1.0),), ((100.0, 1.0),), ((50.0, 1.0), (40.0, 1.0)), ((50.0, 0.0),),
                      ((50.0, 0.05),), ((50.2, 1.0),)):
            with self.assertRaises(SimContractError, msg=str(stops)):
                run_guided_segment(plan(P, 100.0, stops), start(P), final=True)

    def test_header_checks(self):
        P = line_pts(0, 100)
        with self.assertRaises(SimContractError):                         # 非第 0 段不得有出发延迟
            run_guided_segment(plan(P, 100.0, k=1, delay=1.0), start(P, k=1, tau=100_000), final=True)
        with self.assertRaises(SimContractError):                         # 出发延迟不在 0.1 s 网格上
            run_guided_segment(plan(P, 100.0, delay=0.05), start(P), final=True)
        with self.assertRaises(SimContractError):                         # tau 不在 10 Hz 网格上
            run_guided_segment(plan(P, 100.0, k=1), start(P, k=1, tau=150_000), final=True)
        with self.assertRaises(SimContractError):                         # 段号不一致
            run_guided_segment(plan(P, 100.0, k=1), start(P, k=0), final=True)

    def test_curve_readonly(self):
        cv = make_curve(line_pts(0, 5), max_chord_m=1.0, max_turn_rad=0.2)
        with self.assertRaises(ValueError):
            cv.s[0] = 1.0


class TestOwnInterfaces(unittest.TestCase):
    def test_release_delay_and_tau_offset(self):
        P = line_pts(0, 60)
        seen = []

        def dist(tau, st):
            seen.append(tau)
            return np.zeros((1, 3))

        r = run_guided_segment(plan(P, 60.0, delay=1.5), start(P), final=True, disturbance=dist)
        self.assertEqual(r.status, "ok")
        moving = r.tau_us[np.hypot(r.p[:, 0] - P[0, 0], r.p[:, 1] - P[0, 1]) > 1e-9]
        self.assertGreaterEqual(int(moving[0]), 21_500_000)              # 20 s 稳定 + 1.5 s 延迟
        n0 = len(seen)
        k1 = run_guided_segment(plan(P, 60.0, k=1), start(P, k=1, tau=3_000_000), final=True, disturbance=dist)
        self.assertEqual(int(k1.tau_us[0]), 3_000_000)
        self.assertEqual(seen[n0], 3_000_000)                            # 扰动收到统一时钟时刻
        self.assertTrue(all(b - a == 20_000 for a, b in zip(seen[n0:], seen[n0 + 1:])))

    def test_vehicle_overrides_change_result(self):
        P = line_pts(0, 80)
        a = run_guided_segment(plan(P, 80.0), start(P), final=True)
        b = run_guided_segment(plan(P, 80.0), start(P), final=True,
                               vehicle_overrides={"velocity_response_time_s": 0.9})
        self.assertEqual(a.status, "ok"); self.assertEqual(b.status, "ok")
        self.assertFalse(np.array_equal(a.p, b.p))

    def test_record_fields(self):
        P = line_pts(0, 100)
        r = run_guided_segment(plan(P[:191], 90.0), start(P), final=False)
        rec = r.pieces[0]
        self.assertEqual(r.status, "ok")
        self.assertEqual(rec.tau_end_us, r.executed_switch_tau_us)
        self.assertEqual(rec.crossing_local_frame * 100_000, rec.tau_end_us - rec.tau_start_us)
        self.assertGreaterEqual(rec.progress_end_m, 90.0)
        self.assertEqual(int(r.tau_us[-1]) + 100_000, r.executed_switch_tau_us)


if __name__ == "__main__":
    unittest.main(verbosity=2)
