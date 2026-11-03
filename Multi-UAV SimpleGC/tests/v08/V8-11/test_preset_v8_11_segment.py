"""V8-11 第 3 部分预置测试：段核验（规划审查方编写，实现方不得修改或删除）。

运行（在 Multi-UAV SimpleGC 目录下，conda 环境 llm）:
    python -B -m unittest discover -s tests/v08/V8-11 -p "test_preset_v8_11_segment.py" -v

独立预期的来源：
- 手算几何：合成场景的圈层半径见 synth_v8_11.py 文件头；每个反例只违反一条条件，
  注释中写明违反哪条、为什么（到设施圆心的距离与圈层半径比较）；
- 驻留检测器的定义（criteria/0.7-r1：20 s 窗口内所有点到均值 ≤ 30 m、首尾 ≤ 30 m）：
  静止 ≥ 20 s 必判驻留，静止 10 s 或以 8 m/s 匀速运动不判；
- r4 9.2 的条件表与 13.4 的失败代码；V8-04 的拼接约定（越过帧是下一段的第一帧）。
"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from v08.config import load_config  # noqa: E402
from v08.criteria.segment import SegmentTask, verify_segments  # noqa: E402
from v08.sim.types import MemberTrack  # noqa: E402
import synth_v8_11 as syn  # noqa: E402

SCENE = syn.scene()
SF, SA, CV = "segment_semantic_failed", "semantic_ambiguous", "constraint_violation"
RING = [("line", (-425, 0)), ("arc", (0, 0), -540)]           # 预警层内绕 1.5 圈，止于 (425, 0)


def track(member, start, segments, speed=8.0):
    t, p, v, a, seg, sw, rel = syn.stitched(member, start, segments, speed)
    return MemberTrack(member, t, p, v, a, seg, sw), rel


def run(members, tasks, *, release_override=None):
    tracks, rel = {}, {}
    for m, start, segs in members:
        tracks[m], rel[m] = track(m, start, segs)
    if release_override is not None:
        rel = {m: release_override for m in rel}
    return verify_segments(SCENE, tracks, rel, tasks), tracks, rel


def T(k, intent, survey=None):
    return SegmentTask(k, intent, "fac_a", survey)


class TestConfig(unittest.TestCase):

    def test_values(self):
        c = load_config("criteria_segment")
        expect = {"max_target_layer_transit": 1, "max_target_layer_area_search": 1,
                  "max_target_layer_close_observation": 1, "max_target_layer_monitoring": 1,
                  "max_target_layer_feint": 2, "max_target_layer_intrusion": 3,
                  "max_other_facility_layer": 1, "start_max_layer_any_facility": 1, "feint_end_max_target_layer": 1}
        self.assertEqual(c.values, {k: float(v) for k, v in expect.items()})
        self.assertEqual(set(c.kinds.values()), {"definitional"})


class TestPass(unittest.TestCase):

    def test_monitoring_then_intrusion(self):
        """圈内切换：监视（绕 1.5 圈）→ 突入（径向进到 (130, 0)：距圆心 130 ≤ 150 保护层，到轮廓 30 ≤ 50）。"""
        vs, tracks, rel = run([("u1", (-1000, 0), [RING, [("line", (130, 0)), ("hold", 2)]])],
                              [T(0, "monitoring"), T(1, "intrusion")])
        self.assertEqual([v.passed for v in vs], [True, True], [v.failures for v in vs])
        self.assertEqual([v.codes for v in vs], [(), ()])
        tr = tracks["u1"]
        sw = int(np.flatnonzero(np.asarray(tr.segment_index) == 1)[0])
        self.assertEqual(vs[0].window_frames["u1"], (rel["u1"] // syn.FRAME_US, sw))   # 第 0 段从释放帧开始
        self.assertEqual(vs[1].window_frames["u1"], (sw, len(tr.tau_us)))             # 越过帧属于下一段
        self.assertTrue(vs[0].member_conditions["u1"]["patrol_revisit"])
        self.assertTrue(vs[1].final and not vs[0].final)
        self.assertNotIn("ended_outside_all_warning", vs[1].member_conditions["u1"])  # 突入不要求撤出

    def test_area_search_group(self):
        """两名成员各扫一条（y = 380、460），全组足迹合并覆盖侦察区域；之后撤到 (±1000, y)，在所有预警圈外。"""
        srv = syn.survey()
        vs, _, _ = run([("u1", (-1000, 380), [[("line", (1000, 380))]]),
                        ("u2", (1000, 460), [[("line", (-1000, 460))]])], [T(0, "area_search", srv)])
        self.assertTrue(vs[0].passed, vs[0].failures)
        self.assertEqual(vs[0].group_conditions, {"shared_coverage": True})

    def test_close_observation_dwell_allowed(self):
        """抵近观察在 (−425, 0)（预警层）停 30 s：驻留是它的定义性证据，不受"全窗口不驻留"约束。"""
        vs, _, _ = run([("u1", (-1000, 0), [[("line", (-425, 0)), ("hold", 30), ("line", (-1000, 0))]])],
                       [T(0, "close_observation")])
        self.assertTrue(vs[0].passed, vs[0].failures)
        self.assertNotIn("no_dwell_window", vs[0].member_conditions["u1"])


class TestCounterexamples(unittest.TestCase):

    def test_pre_release_frames_excluded(self):
        """释放前在起点静止 20 s：若窗口从 0 开始（release = 0），全窗口驻留会误报；按释放时刻切则不报。"""
        segs = [("u1", (-1000, 0), [RING + [("line", (1000, 0))]])]
        ok, _, _ = run(segs, [T(0, "monitoring")])
        self.assertTrue(ok[0].passed, ok[0].failures)
        bad, _, _ = run(segs, [T(0, "monitoring")], release_override=0)
        self.assertEqual(bad[0].failures, (("u1", "no_dwell_window", SA),))

    def test_monitoring_hover(self):
        """监视段中途在 (0, −425)（预警层）悬停 25 s：含抵近观察的定义性证据 → semantic_ambiguous。"""
        segs = [("line", (-425, 0)), ("arc", (0, 0), -270), ("hold", 25), ("arc", (0, 0), -270), ("line", (1000, 0))]
        vs, _, _ = run([("u1", (-1000, 0), [segs])], [T(0, "monitoring")])
        self.assertEqual(vs[0].failures, (("u1", "no_dwell_window", SA),))
        self.assertEqual(vs[0].codes, (SA,))

    def test_other_facility_alert(self):
        """过境 A 后经 (1500, 100)：到 B 圆心 141 ≤ 230，进入 B 的警戒层 → constraint_violation。"""
        segs = [("line", (900, 350)), ("line", (1500, 100)), ("line", (1500, 900))]
        vs, _, _ = run([("u1", (-900, 350), [segs])], [T(0, "transit")])
        self.assertEqual(vs[0].failures, (("u1", "other_facilities_within_limit", CV),))

    def test_target_too_deep(self):
        """监视绕圈半径 280 < 300：进入目标警戒层 → target_within_limit 不满足。"""
        segs = [("line", (-280, 0)), ("arc", (0, 0), -540), ("line", (1000, 0))]
        vs, _, _ = run([("u1", (-1000, 0), [segs])], [T(0, "monitoring")])
        self.assertIn(("u1", "target_within_limit", SF), vs[0].failures)
        self.assertEqual(vs[0].codes, (SF,))

    def test_feint_not_exited(self):
        """佯动段在 (−230, 0)（警戒层，距圆心 230 ≤ 300）结束：未退出警戒层；
        下一段（突入）的首帧仍在警戒层内，违反"段开始时不在警戒层内"。"""
        vs, _, _ = run([("u1", (-1000, 0), [[("line", (-230, 0))], [("line", (-130, 0)), ("hold", 2)]])],
                       [T(0, "feint"), T(1, "intrusion")])
        self.assertEqual(vs[0].failures, (("u1", "ended_below_alert", SF),))
        self.assertEqual(vs[1].failures, (("u1", "start_layers_within_limit", SF),))

    def test_final_not_withdrawn(self):
        """最后一段（抵近观察）停在 (−500, 0)：距圆心 500 ≤ 550，仍在预警圈内 → 未到终止区域。"""
        vs, _, _ = run([("u1", (-1000, 0), [[("line", (-425, 0)), ("hold", 30), ("line", (-500, 0))]])],
                       [T(0, "close_observation")])
        self.assertEqual(vs[0].failures, (("u1", "ended_outside_all_warning", SF),))

    def test_transit_starts_inside(self):
        """监视后直接接过境：过境段首帧在预警层内（距圆心约 425）→ started_outside_target_warning 不满足。"""
        vs, _, _ = run([("u1", (-1000, 0), [RING, [("line", (1000, 0))]])], [T(0, "monitoring"), T(1, "transit")])
        self.assertTrue(vs[0].passed, vs[0].failures)
        self.assertIn(("u1", "started_outside_target_warning", SF), vs[1].failures)
        self.assertEqual(vs[1].codes, (SF,))

    def test_coverage_short(self):
        """两名成员扫同一条 y = 380：足迹只覆盖 y ∈ [320, 440]，侦察区域 y ∈ [340, 500] 的格点不到 80%。"""
        srv = syn.survey()
        vs, _, _ = run([("u1", (-1000, 380), [[("line", (1000, 380))]]),
                        ("u2", (1000, 380), [[("line", (-1000, 380))]])], [T(0, "area_search", srv)])
        self.assertEqual(vs[0].failures, (("group", "shared_coverage", SF),))

    def test_close_observation_too_short(self):
        """只停 10 s，不足 20 s 驻留窗口 → observation_dwell 不满足。"""
        vs, _, _ = run([("u1", (-1000, 0), [[("line", (-425, 0)), ("hold", 10), ("line", (-1000, 0))]])],
                       [T(0, "close_observation")])
        self.assertEqual(vs[0].failures, (("u1", "observation_dwell", SF),))

    def test_contract_errors(self):
        tr, rel = track("u1", (-1000, 0), [RING, [("line", (130, 0)), ("hold", 2)]])
        with self.assertRaises(ValueError):          # 迂回判据未定稿（④）
            verify_segments(SCENE, {"u1": tr}, {"u1": rel}, [T(0, "detour"), T(1, "intrusion")])
        with self.assertRaises(ValueError):          # 突入只能是最后一段
            verify_segments(SCENE, {"u1": tr}, {"u1": rel}, [T(0, "intrusion"), T(1, "monitoring")])
        with self.assertRaises(ValueError):          # 段数与轨迹不符
            verify_segments(SCENE, {"u1": tr}, {"u1": rel}, [T(0, "monitoring")])
        with self.assertRaises(ValueError):          # 释放时刻晚于第 0 段
            verify_segments(SCENE, {"u1": tr}, {"u1": 10 ** 12}, [T(0, "monitoring"), T(1, "intrusion")])


if __name__ == "__main__":
    unittest.main()
