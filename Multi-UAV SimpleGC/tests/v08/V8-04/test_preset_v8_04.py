"""V8-04 预置测试（规划审查方编写，实现方不得修改或删除）。

运行（在 Multi-UAV SimpleGC 目录下，conda 环境 llm）:
    python -B -m unittest discover -s tests/v08/V8-04 -p "test_preset_*.py" -v
全部约需 1–2 分钟（含十余次单机 fastsim 运行）。

独立预期的来源：
- 配置：本指令第 3 节给出的 configs/v08/sim.json 全文；
- 记录跟踪器：与冻结 execute 输出逐位相同（恒等性质）；
- 单段单小段：与冻结 execute(only_agent=...) 的输出逐位相同；
- 直线上切段：续跑时从 (p, v, a) 精确接续，且延伸段使跟踪器在段末点前不减速，
  因此与不切段的整条航线相比只剩数值误差。规划审查方在云端实测为 3e-11 m（6 m/s）、
  4e-7 m（10 m/s）；断言取 1e-3 m，远小于跟踪管 0.5 m；
- 越过判定：按定义（第 4.3 节）手工构造的回环航线，预期越过点在段末点附近而不是更早经过的同侧位置；
- 拼接：人工构造的数组，预期按定义（第 5 节）得到。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

import task_v07.execution as frozen_execution  # noqa: E402
from swarm_sim.fast_dynamics.route_tracker import RouteTracker as FrozenRouteTracker  # noqa: E402
from v08.config import load_config  # noqa: E402
from v08.sim.types import (FRAME_US, MemberBoundaryState, MemberPiece, MemberSegmentPlan,  # noqa: E402
                           MemberSegmentResult, SimContractError, TimelineInconsistent)
from v08.sim.adapter import (append_extension, execute_recorded, run_member_segment)  # noqa: E402
from v08.sim.stitch import stitch  # noqa: E402

ALT = 120.0
SIM = load_config("sim")


def rest_state(member="m", xy=(0.0, 0.0)):
    return MemberBoundaryState(member, 0, 0, (float(xy[0]), float(xy[1]), ALT), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


def plan(member, k, pieces, delay=0.0):
    return MemberSegmentPlan(member, k, tuple(pieces), delay)


# 一条带 90° 转角的航线；(200, 75) 是直线腿上的共线中间点
ROUTE = ((0.0, 0.0, ALT), (200.0, 0.0, ALT), (200.0, 75.0, ALT), (200.0, 150.0, ALT), (400.0, 150.0, ALT))


def frozen_solo(route, speed, delay=0.0):
    sk = {"agent_ids": ["m"],
          "initial_states": [{"agent_id": "m", "position_enu_m": list(route[0]), "velocity_enu_m_s": [0.0, 0.0, 0.0],
                              "acceleration_enu_m_s2": [0.0, 0.0, 0.0]}],
          "references": {"m": {"points_enu_m": [list(p) for p in route]}},
          "cruise_speed_m_s": speed, "initial_settle_s": 20.0, "terminal_radius_m": 1.0,
          "terminal_speed_m_s": 0.15, "terminal_hold_s": 2.0}
    return sk, frozen_execution.execute(sk, {"m": delay}, only_agent="m", reference_version="r3")


class TestConfig(unittest.TestCase):
    def test_sim_config_values_and_kinds(self):
        self.assertEqual(SIM.values["initial_settle_s"], 20.0)
        self.assertEqual(SIM.values["terminal_hold_s"], 2.0)
        self.assertEqual(SIM.values["extension_length_m"], 30.0)
        self.assertEqual(SIM.kinds["extension_length_m"], "pending_measurement")
        self.assertEqual(SIM.values["join_max_distance_m"], 2.0)
        self.assertEqual(len(SIM.sha256), 64)

    def test_config_rejects_bad_kind_and_missing_source(self):
        good = json.loads(Path(SIM.path).read_text(encoding="utf-8"))
        for mutate in ("kind", "source"):
            bad = json.loads(json.dumps(good))
            if mutate == "kind":
                bad["parameters"]["terminal_hold_s"]["kind"] = "tuned"
            else:
                bad["parameters"]["terminal_hold_s"]["source"] = " "
            with tempfile.TemporaryDirectory() as d:
                Path(d, "sim.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_config("sim", config_dir=d)


class TestRecordedExecute(unittest.TestCase):
    def test_recording_is_bitwise_identity_and_witnesses_all_nodes(self):
        sk, ref = frozen_solo(ROUTE, 8.0)
        run, witnesses = execute_recorded(sk, {"m": 0.0}, only_agent="m")
        for key in ("time_us", "p", "v", "a"):
            self.assertTrue(np.array_equal(np.asarray(run[key]), np.asarray(ref[key])), key)
        self.assertEqual([w["node_index"] for w in witnesses], list(range(len(ROUTE))))
        self.assertIs(frozen_execution.RouteTracker, FrozenRouteTracker)  # 运行结束后已还原


class TestRunMemberSegment(unittest.TestCase):
    def test_single_final_piece_equals_frozen_execute(self):
        _, ref = frozen_solo(ROUTE, 8.0, delay=3.0)
        r = run_member_segment(plan("m", 0, [MemberPiece(ROUTE, 4, 8.0)], delay=3.0), rest_state(), final=True)
        self.assertEqual(r.status, "ok")
        self.assertIsNone(r.end_state)
        self.assertIsNone(r.executed_switch_tau_us)
        self.assertTrue(np.array_equal(r.tau_us, np.asarray(ref["time_us"])))
        self.assertTrue(np.array_equal(r.p, np.asarray(ref["p"])[:, 0]))
        # 释放前（τ < 23 s）保持在起点不动
        pre = r.tau_us < 23_000_000
        self.assertTrue(np.all(r.p[pre] == np.array([0.0, 0.0, ALT])))
        self.assertGreater(np.linalg.norm(r.p[r.tau_us == 25_000_000][0, :2]), 0.0)

    def test_split_on_straight_leg_matches_unsplit_and_does_not_brake(self):
        for speed in (6.0, 10.0):
            whole = run_member_segment(plan("m", 0, [MemberPiece(ROUTE, 4, speed)]), rest_state(), final=True)
            first = append_extension(ROUTE[:3], SIM.values["extension_length_m"])
            r1 = run_member_segment(plan("m", 0, [MemberPiece(first, 2, speed)]), rest_state(), final=False)
            r2 = run_member_segment(plan("m", 1, [MemberPiece(ROUTE[2:], 2, speed)]), r1.end_state, final=True)
            self.assertEqual((r1.status, r2.status), ("ok", "ok"))
            g = stitch([r1, r2])["m"]
            self.assertTrue(np.array_equal(g.tau_us, whole.tau_us))
            self.assertLess(float(np.linalg.norm(g.p - whole.p, axis=1).max()), 1e-3)
            # 越过帧：速度未下降（延伸段的作用），位置在段末点之后不超过一帧行程
            self.assertGreater(float(np.linalg.norm(r1.end_state.v[:2])), 0.99 * speed)
            along = r1.end_state.p[1] - 75.0
            self.assertGreaterEqual(along, 0.0)
            self.assertLessEqual(along, speed * 0.1 + 1e-9)
            self.assertEqual(r1.end_state.segment_index, 1)
            self.assertEqual(r1.end_state.tau_us, r1.executed_switch_tau_us)
            self.assertEqual(int(r2.tau_us[0]), r1.executed_switch_tau_us)

    def test_crossing_uses_route_progress_not_first_half_plane_hit(self):
        # 第一条腿 y=0 上 x>150 的部分也满足"越过 (150,50) 沿 +x 的法平面"，但段末点在之后的 y=50 腿上
        loop = ((0.0, 0.0, ALT), (300.0, 0.0, ALT), (300.0, 100.0, ALT), (0.0, 100.0, ALT),
                (0.0, 50.0, ALT), (150.0, 50.0, ALT))
        pts = append_extension(loop, SIM.values["extension_length_m"])
        r = run_member_segment(plan("m", 0, [MemberPiece(pts, 5, 8.0)]), rest_state(), final=False)
        self.assertEqual(r.status, "ok")
        end = np.asarray(r.end_state.p[:2])
        self.assertLess(float(np.linalg.norm(end - np.array([150.0, 50.0]))), 0.5 + 8.0 * 0.1)
        self.assertGreaterEqual(float(end[0]), 150.0)
        self.assertGreater(len(r.tau_us), 1500)  # 走完了前面的回环（约 1000 m）

    def test_speed_change_pieces_in_one_segment(self):
        first = append_extension(ROUTE[:3], SIM.values["extension_length_m"])
        r = run_member_segment(plan("m", 0, [MemberPiece(first, 2, 6.0), MemberPiece(ROUTE[2:], 2, 10.0)]),
                               rest_state(), final=True)
        self.assertEqual(r.status, "ok")
        self.assertEqual(len(r.pieces), 2)
        t_change = r.pieces[1].tau_start_us
        self.assertEqual(r.pieces[0].tau_end_us, t_change)
        self.assertTrue(np.all(np.diff(r.tau_us) == FRAME_US))
        speed = np.linalg.norm(r.v[:, :2], axis=1)
        self.assertLess(float(speed[r.tau_us < t_change].max()), 6.0 + 0.05)
        self.assertGreater(float(speed[r.tau_us >= t_change].max()), 9.9)

    def test_contract_violations_raise(self):
        no_ext = ROUTE[:3]
        with self.assertRaises(SimContractError):     # 非最后一段缺延伸段
            run_member_segment(plan("m", 0, [MemberPiece(no_ext, 2, 8.0)]), rest_state(), final=False)
        with self.assertRaises(SimContractError):     # 出发延迟不在 10 Hz 网格
            run_member_segment(plan("m", 0, [MemberPiece(ROUTE, 4, 8.0)], delay=0.05), rest_state(), final=True)
        with self.assertRaises(SimContractError):     # 高度不恒定
            bad = ((0.0, 0.0, ALT), (100.0, 0.0, ALT + 1.0))
            run_member_segment(plan("m", 0, [MemberPiece(bad, 1, 8.0)]), rest_state(), final=True)
        far = MemberBoundaryState("m", 1, 50_000_000, (0.0, 3.0, ALT), (8.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        with self.assertRaises(SimContractError):     # 续跑起点与计划起点相距 3 m > 2 m
            run_member_segment(plan("m", 1, [MemberPiece(((0.0, 0.0, ALT), (100.0, 0.0, ALT)), 1, 8.0)]), far, final=True)
        with self.assertRaises(SimContractError):     # 非第 0 段不得有出发延迟
            ok_state = MemberBoundaryState("m", 1, 50_000_000, (0.0, 0.0, ALT), (8.0, 0.0, 0.0), (0.0, 0.0, 0.0))
            run_member_segment(plan("m", 1, [MemberPiece(((0.0, 0.0, ALT), (100.0, 0.0, ALT)), 1, 8.0)], delay=1.0),
                               ok_state, final=True)


def seg(member, k, tau0, n, final, *, start_xy=0.0, switch=True):
    tau = tau0 + np.arange(n, dtype=np.int64) * FRAME_US
    p = np.stack([start_xy + np.arange(n, dtype=float), np.zeros(n), np.full(n, ALT)], axis=1)
    v = np.tile([10.0, 0.0, 0.0], (n, 1))
    a = np.zeros((n, 3))
    end = None
    sw = None
    if not final and switch:
        sw = int(tau0 + n * FRAME_US)
        end = MemberBoundaryState(member, k + 1, sw, (start_xy + n, 0.0, ALT), (10.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    return MemberSegmentResult(member, k, final, "ok", tau, p, v, a, end, sw, ())


class TestStitch(unittest.TestCase):
    def test_async_switch_two_members(self):
        # 成员 a 在 τ=3 s 切换，成员 b 在 τ=5 s 切换
        rs = [seg("a", 0, 0, 30, False), seg("a", 1, 3_000_000, 40, True, start_xy=30.0),
              seg("b", 1, 5_000_000, 20, True, start_xy=50.0), seg("b", 0, 0, 50, False)]
        out = stitch(rs)
        self.assertEqual(sorted(out), ["a", "b"])
        a, b = out["a"], out["b"]
        self.assertEqual(len(a.tau_us), 70)
        self.assertEqual(len(b.tau_us), 70)
        self.assertEqual(a.executed_switch_tau_us, (3_000_000,))
        self.assertEqual(b.executed_switch_tau_us, (5_000_000,))
        self.assertEqual(int(a.segment_index[29]), 0)
        self.assertEqual(int(a.segment_index[30]), 1)
        self.assertEqual(int(b.segment_index[49]), 0)
        self.assertEqual(int(b.segment_index[50]), 1)
        self.assertTrue(np.all(np.diff(a.tau_us) == FRAME_US))

    def test_duplicate_gap_and_state_mismatch_raise(self):
        s0 = seg("a", 0, 0, 30, False)
        dup = seg("a", 1, 2_900_000, 40, True, start_xy=29.0)
        gap = seg("a", 1, 3_100_000, 40, True, start_xy=31.0)
        for bad in (dup, gap):
            with self.assertRaises(TimelineInconsistent):
                stitch([s0, bad])
        moved = seg("a", 1, 3_000_000, 40, True, start_xy=30.0)
        moved.p[0, 1] = 1e-6
        with self.assertRaises(TimelineInconsistent):
            stitch([s0, moved])

    def test_structure_errors_raise(self):
        with self.assertRaises(TimelineInconsistent):   # 段序号不连续
            stitch([seg("a", 0, 0, 30, False), seg("a", 2, 3_000_000, 40, True, start_xy=30.0)])
        with self.assertRaises(TimelineInconsistent):   # 最后一段不是 final
            stitch([seg("a", 0, 0, 30, False)])
        with self.assertRaises(TimelineInconsistent):   # final 段后面还有段
            stitch([seg("a", 0, 0, 30, True), seg("a", 1, 3_000_000, 40, True, start_xy=30.0)])
        with self.assertRaises(TimelineInconsistent):   # 成员段数不同
            stitch([seg("a", 0, 0, 30, False), seg("a", 1, 3_000_000, 40, True, start_xy=30.0),
                    seg("b", 0, 0, 30, True)])
        with self.assertRaises(TimelineInconsistent):   # 第 0 段不从 τ=0 开始
            stitch([seg("a", 0, 100_000, 30, True)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
