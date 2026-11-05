"""V8-14c 等价性门禁 1、2（执行方自加测试；裁定 V8-14c 第 4 节）。批量跟踪与逐成员 run_tracking_segment 逐位相同：
tau_us、p、v、a、status、终态、保持开始时刻 np.array_equal / ==；TrackingRecord 除 wall_s 外全部字段相等。
任何不一致即失败（P0：可复现、数据完整），不设数值容差。"""
import dataclasses
import math
import unittest

import numpy as np

from v08.diagnostics.joint_calibration import (FIX_ALT, FIX_RELEASE, JERK_SCAN, SplineRef, make_tracking_cases)
from v08.sim.tracking import TimeReference, run_tracking_segment
from v08.sim.tracking_batch import LAST_GROUP_STATS, run_tracking_group
from v08.sim.types import MemberBoundaryState


def same_result(tc, a, b, label):
    """逐位比较两个 MemberSegmentResult（wall_s 除外）。"""
    tc.assertEqual(a.member_id, b.member_id, label)
    tc.assertEqual((a.segment_index, a.final, a.status), (b.segment_index, b.final, b.status), label + " status")
    for name in ("tau_us", "p", "v", "a"):
        x, y = getattr(a, name), getattr(b, name)
        tc.assertEqual(x.dtype, y.dtype, f"{label} {name} dtype")
        tc.assertTrue(np.array_equal(x, y), f"{label} {name} 不逐位一致")
    tc.assertEqual((a.end_state, a.executed_switch_tau_us), (b.end_state, b.executed_switch_tau_us), label)
    ra, rb = a.pieces[0], b.pieces[0]
    for f in dataclasses.fields(ra):
        if f.name == "wall_s":
            continue
        x, y = getattr(ra, f.name), getattr(rb, f.name)
        if isinstance(x, np.ndarray):
            tc.assertTrue(np.array_equal(x, y) and x.dtype == y.dtype, f"{label} record.{f.name} 不逐位一致")
        else:
            tc.assertEqual(x, y, f"{label} record.{f.name}")


def state_for(ref, member):
    p0, _, _ = ref.pva(ref.release_s)
    p0 = np.asarray(p0, float).reshape(2)
    return MemberBoundaryState(member, 0, 0, (float(p0[0]), float(p0[1]), float(ref.altitude_m)),
                               (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


class _Runaway:
    """故意不可跟随的参考：30 m/s 直线（超过机体 12 m/s 上限），预算内追不上 → sim_timeout。"""

    def __init__(self, start, release, T):
        self.s, self.r, self.T = np.asarray(start, float), float(release), float(T)

    def pva(self, t_abs):
        t = np.asarray(t_abs, float)
        scalar = t.ndim == 0
        t = np.atleast_1d(t)
        tc = np.clip(t - self.r, 0.0, self.T)
        moving = (t >= self.r) & (t <= self.r + self.T)
        p = self.s[None] + tc[:, None] * np.array([30.0, 0.0])[None]
        v = np.where(moving[:, None], np.array([30.0, 0.0])[None], 0.0)
        a = np.zeros_like(p)
        return (p[0], v[0], a[0]) if scalar else (p, v, a)


def synthetic_group(n):
    """n 个成员：J=14 的直线/近圆/U 形格点轮流取用，释放时刻 20.0 + 0.3k s、起点各隔 500 m；n ≥ 2 时最后一名
    换成必然超时的 _Runaway。返回 (references, states)。"""
    cases = [c for c in make_tracking_cases(14.0) if c.get("valid")]
    refs, sts = [], []
    for k in range(n):
        member = f"m{k:02d}"
        release = FIX_RELEASE + 0.3 * k
        start = (500.0 * k, -300.0 * (k % 3))
        if n >= 2 and k == n - 1:
            rw = _Runaway(start, release, 100.0)
            ref = TimeReference(member, release, release + 100.0, FIX_ALT, rw.pva)
        else:
            c = cases[k % len(cases)]
            ref = SplineRef(c["knots"], c["controls"], c["T"], release_s=release, start=start).reference(member)
        refs.append(ref)
        sts.append(state_for(ref, member))
    return refs, sts


class TrackingBatchGate(unittest.TestCase):
    def test_gate1_calibration_fixtures_single_vs_batch_n1(self):
        """门禁 1：V8-13 第 2 部分跟踪标定夹具（6 个 J × 合法格点），每个案例 N=1 批量对单机。"""
        count = 0
        for J in JERK_SCAN:
            for c in make_tracking_cases(J):
                if not c.get("valid"):
                    continue
                ref = SplineRef(c["knots"], c["controls"], c["T"]).reference()
                st = state_for(ref, "m")
                a = run_tracking_segment(ref, st, final=True)
                b = run_tracking_group([ref], [st], final=True)[0]
                same_result(self, a, b, f"J={J:g} {c['kind']}@{c['requested_speed']:.3f}")
                count += 1
        self.assertEqual(count, 66, "6 个 J × 11 个合法格点")

    def test_gate2_synthetic_groups(self):
        """门禁 2：释放/结束时刻都不同、含一个故意超时成员的合成编组，N ∈ {1, 2, 5, 12}。"""
        for n in (1, 2, 5, 12):
            refs, sts = synthetic_group(n)
            batch = run_tracking_group(refs, sts, final=True)
            self.assertEqual([r.member_id for r in batch], [r.member_id for r in refs], "输出顺序 = 输入顺序")
            statuses = []
            for ref, st, b in zip(refs, sts, batch):
                a = run_tracking_segment(ref, st, final=True)
                same_result(self, a, b, f"N={n} {ref.member_id}")
                statuses.append(a.status)
            if n >= 2:
                self.assertEqual(statuses[-1], "sim_timeout", "夹具含故意超时成员")
                self.assertIn("ok", statuses, "夹具含正常完成成员")

    def test_scalar_reference_mode_also_identical(self):
        """3.2：强制逐点标量参考（不用预计算）也与单机逐位相同；记录两种方式的模式。"""
        refs, sts = synthetic_group(5)
        b1 = run_tracking_group(refs, sts, use_precomputed_reference=False)
        self.assertEqual(LAST_GROUP_STATS["reference_mode"], "scalar")
        b2 = run_tracking_group(refs, sts)
        mode = LAST_GROUP_STATS["reference_mode"]
        for x, y in zip(b1, b2):
            same_result(self, x, y, f"标量/{mode}")


if __name__ == "__main__":
    unittest.main()
