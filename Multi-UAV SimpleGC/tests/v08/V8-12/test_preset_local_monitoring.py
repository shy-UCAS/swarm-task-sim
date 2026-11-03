"""本地：完整生成路径交给V8-11独立预言机；不运行完整动力学。"""
import math
import unittest
from unittest import mock
import numpy as np

from synth_v8_12 import fixture_plan
from v08.contract.monitoring import to_guided
from v08.motion.nominal import sample_nominal
from v08.criteria.window import scene_geometry, measure_member_window
from v08.sim.guided import GuidedSegmentPlan, run_guided_segment
from v08.sim.guidance import make_curve, NODE_TOL_M
from v08.config import load_config


class EntryAccepted(Exception):
    """仅在真正run_guided_segment完成入口检查后，阻止动力学运行。"""


def runs(mask):
    # 独立测试辅助：连续True区间，半开。
    edge = np.flatnonzero(np.diff(np.r_[False, mask, False].astype(int)))
    return list(zip(edge[::2], edge[1::2]))


def circle_crossings(xy, radius):
    """用解析二次方程求每条弦与原点圆的交点；不是调用待测几何。"""
    length = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    s = np.r_[0.0, np.cumsum(length)]
    out = []
    for i, (a, b) in enumerate(zip(xy, xy[1:])):
        d = b - a
        aa = float(d @ d)
        bb = float(2 * (a @ d))
        cc = float(a @ a - radius * radius)
        disc = bb * bb - 4 * aa * cc
        if aa == 0 or disc < 0:
            continue
        for u in sorted(((-bb - math.sqrt(disc)) / (2 * aa),
                         (-bb + math.sqrt(disc)) / (2 * aa))):
            if 0 <= u < 1:  # 半开弦避免节点重复计数
                value = s[i] + u * length[i]
                if not out or abs(value - out[-1]) > NODE_TOL_M:
                    out.append(value)
    return s, out


def at_s(xy, s, where):
    return np.array([np.interp(where, s, xy[:, j]) for j in range(2)])


class TestMonitoringLocal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = fixture_plan("loop")

    def test_nominal_window_matches_frozen_oracle(self):
        ctx, group, task, states, plan = self.bundle
        self.assertIsNone(plan.failure,
                          "手工宽环带夹具给定完整合法提案；应完成构造，非随机挑种子")
        geom = scene_geometry(ctx.scene)
        for m in group.member_ids:
            sample = sample_nominal(plan.members[m], include_prerelease=False)
            w = measure_member_window(
                geom, m, sample.time_us, sample.p, sample.v,
                kind="monitoring", target_id=task.target_id, settled=True,
                max_target_layer=1, max_other_layer=1)
            self.assertIs(w.conditions["patrol_revisit"], True,
                          "独立预言机：已接受V8-11重访检测器；1.5圈回到原周期")
            self.assertFalse(w.dwell_anywhere["detected"],
                             "r4 9.2全窗口不驻留；V8-11真实字段dwell_anywhere")
            self.assertTrue(np.all(w.levels[:, geom.facility_ids.index(task.target_id)] <= 1),
                            "独立预言机：不得进入目标警戒/保护层")
            self.assertTrue(np.all(np.diff(sample.time_us) == 100_000),
                            "V8-11入口要求连续10Hz整数微秒，不插分数秒尾帧")

    def test_boundaries_alignment_and_terminal(self):
        ctx, group, task, states, plan = self.bundle
        self.assertIsNone(plan.failure, "手工夹具应有完整路径才能检查边界")
        for m in group.member_ids:
            xy = np.asarray(plan.members[m].curve_xy, float)
            for radius in (150.0, 300.0, 850.0):
                # 手算夹具的三层半径；与生产signed_distance独立。
                signed = np.linalg.norm(xy, axis=1) - radius
                s, crossings = circle_crossings(xy, radius)
                if radius != 850.0:
                    self.assertGreaterEqual(float(signed.min()), 10.0,
                                            "r4 6.3：未穿越的protected/alert边界距≥10")
                    self.assertEqual(len(crossings), 0,
                                     "手算夹具：监视不会穿越protected或alert")
                    continue
                self.assertGreaterEqual(len(crossings), 2,
                                        "监视完整链：从外进入预警圈并最后撤出")
                for lo, hi in runs(np.abs(signed) < 10.0):
                    self.assertGreater(lo, 0,
                                       "r4 6.3：穿越条带不能从路径首点就缺失外侧")
                    self.assertLess(hi, len(xy),
                                    "r4 6.3：穿越条带不能在终点缺失另一侧")
                    self.assertLess(signed[lo - 1] * signed[hi], 0.0,
                                    "r4 6.3：进入±10条带必须真正穿越，不能贴边掉头")
                    block = xy[lo - 1:hi + 1]
                    axis = block[-1] - block[0]
                    axis = axis / np.linalg.norm(axis)
                    delta = block - block[0]
                    normal_error = np.abs(delta[:, 0] * axis[1] - delta[:, 1] * axis[0])
                    self.assertLessEqual(float(normal_error.max()), NODE_TOL_M,
                                         "r4 6.3：从边界外10到内10是一整段直线")
                for crossing in crossings:
                    # 沿弧长左右各取0.5m判断方向；0.5来源r4曲线加密间距。
                    before = at_s(xy, s, max(0.0, crossing - 0.5))
                    after = at_s(xy, s, min(s[-1], crossing + 0.5))
                    if np.linalg.norm(before) > np.linalg.norm(after):
                        self.assertGreaterEqual(crossing, 100.0,
                                                "r4 6.3：入圈前须存在100m路径")
                        a = at_s(xy, s, crossing - 100.0)
                        b = at_s(xy, s, crossing)
                        self.assertAlmostEqual(float(np.linalg.norm(b - a)), 100.0,
                                               delta=NODE_TOL_M,
                                               msg="直线解析：100m弧长的端点弦长也必须100m")
                        block = np.vstack([a, xy[(s > crossing - 100) & (s < crossing)], b])
                        direction = (b - a) / 100.0
                        delta = block - a
                        cross = np.abs(delta[:, 0] * direction[1] -
                                       delta[:, 1] * direction[0])
                        self.assertLessEqual(float(cross.max()), NODE_TOL_M,
                                             "r4 6.3：不是仅总长100，而是100m全段共线")
            for entity in ctx.scene["entities"]:
                if entity.get("layer") == "warning":
                    g = entity["geometry"]
                    distance = np.linalg.norm(xy[-1] - g["center_m"]) - g["radius_m"]
                    self.assertGreaterEqual(float(distance), 50.0,
                                            "r4 4.4：计划终点离每个预警圈≥50m")

    def test_guided_adapter_reaches_real_entry_checks(self):
        ctx, group, task, states, plan = self.bundle
        self.assertIsNone(plan.failure, "手工夹具应有完整SegmentPlan")
        G = load_config("guidance").values
        for m in group.member_ids:
            member = plan.members[m]
            converted = to_guided(member)
            self.assertIsInstance(converted, GuidedSegmentPlan,
                                  "已接受V8-08接口类型，不能只返回相似字典")
            self.assertEqual(converted.curve_xy, member.curve_xy,
                             "转换契约：不重采样、不改变已验证曲线")
            curve = make_curve(converted.curve_xy, max_chord_m=G["max_chord_m"],
                               max_turn_rad=G["max_turn_per_chord_rad"])
            self.assertEqual(converted.end_s_m, curve.length,
                             "V8-08 final入口：end_s为同一累计弦长的最后节点")
            self.assertEqual(converted.stops, (),
                             "r4监视无内部驻留；终点保持由final接口加入")
            with mock.patch("v08.sim.guided.InjectableEngine", side_effect=EntryAccepted):
                with self.assertRaises(
                    EntryAccepted,
                    msg="固定提交顺序：到引擎构造说明header/曲线/end/stops/start/剖面检查已过",
                ):
                    run_guided_segment(converted, states[m], final=True)


if __name__ == "__main__":
    unittest.main()
