"""V8-16 预置；未经运行。场景几何/分派文件，与纯数值测试分开。"""
import math
import unittest
from dataclasses import asdict, replace
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import shapely  # 明确本文件属于本地几何测试层。

from v08.config import load_config
from v08.contract.monitoring import (
    CommonDraw, GroupSpec, SpeedProfilePrior, TaskSpec, monitoring_mission)
from v08.contract.single_intent import transit_mission
from v08.motion.layer_limits import layer_limits, constraints_for_task
from v08.motion.intents.monitoring import monitoring_constraints
from v08.motion.transit_chords import assess_straight_bundle
from v08.motion.nominal_checks import screen_transit_member
from v08.scene.field import Clearance


def circle(radius, center=(0.0, 0.0)):
    return dict(type="Circle", center_m=list(center), radius_m=float(radius))


def facility(fid, center=(0.0, 0.0)):
    return NS(id=fid, center=center, geometry=circle(20.0, center),
              offsets=dict(warning=180.0, alert=30.0, protected=0.0),
              layers=dict(warning=circle(200.0, center),
                          alert=circle(50.0, center), protected=circle(20.0, center)))


def context():
    fs = [facility("z"), facility("a", (800.0, 0.0))]
    return NS(facilities=fs, facility_by_id={f.id: f for f in fs},
              world=circle(2000.0), obstacles=[("ob", circle(20.0, (0.0, 800.0)))],
              params=dict(world_margin_m=35.0, obstacle_margin_m=35.0,
                          forbidden_margin_m=10.0, pre_entry_warning_clearance_m=10.0,
                          monitoring=dict(alert_clearance_m=30.0, warning_inset_m=35.0)),
              family=NS(initial_states={"u1": {}, "u2": {}}), inputs={"sha256": {}})


class GeometryPreset(unittest.TestCase):
    def test_six_values_and_seventh_unsupported(self):
        expected = dict(transit=1, monitoring=1, area_search=1,
                        close_observation=1, feint=2, intrusion=3)
        for intent, limit in expected.items():
            with self.subTest(intent=intent):
                # 独立预期：r4 4.4定义、ed44227冻结criteria_segment的六个值。
                self.assertEqual(layer_limits(intent, "z", ["z", "a"]),
                                 {"z": limit, "a": 1})
        # 独立预期：固定配置没有detour键，冻结segment也不支持；不得补造0。
        self.assertNotIn("max_target_layer_detour", load_config("criteria_segment").values)
        with self.assertRaises(ValueError):
            layer_limits("detour", "z", ["z", "a"])

    def test_monitor_constraint_identity_and_counterexamples(self):
        ctx = context()
        old = monitoring_constraints(ctx, "z")["base"]
        got = constraints_for_task(ctx, TaskSpec("t", "monitoring", "z"))["base"]
        pack = lambda cs: [(c.name, c.geometry, c.sense, c.minimum_m) for c in cs]
        # 独立预期：U D.2监视base逐字段/顺序不变量；另列人工预期防共同改错。
        self.assertEqual(pack(got), pack(old))
        # 手工完整列表防止新旧函数共同调用同一个错误构造器。
        self.assertEqual(pack(got),
                         [("world", ctx.world, -1, 35.0),
                          ("obstacle:ob", ctx.obstacles[0][1], 1, 35.0),
                          ("alert:z", ctx.facility_by_id["z"].layers["alert"], 1, 10.0),
                          ("alert:a", ctx.facility_by_id["a"].layers["alert"], 1, 10.0)])
        self.assertEqual([(c.name, c.sense, c.minimum_m) for c in got],
                         [("world", -1, 35.0), ("obstacle:ob", 1, 35.0),
                          ("alert:z", 1, 10.0), ("alert:a", 1, 10.0)])
        for intent, names in [
            ("feint", ["world", "obstacle:ob", "protected:z", "alert:a"]),
            ("intrusion", ["world", "obstacle:ob", "alert:a"]),
        ]:
            cons = constraints_for_task(ctx, TaskSpec("t", intent, "z"))["base"]
            # 独立预期：U D.2反例：目标警戒允许，非目标警戒仍禁止。
            self.assertEqual([c.name for c in cons], names)
            self.assertNotIn("alert:z", [c.name for c in cons])
            self.assertIn("alert:a", [c.name for c in cons])

    def test_paired_mission_only_intent_changes(self):
        ctx = context()
        g = GroupSpec("g0", ("u2", "u1"), SpeedProfilePrior(7.0, 0.5), "loose")
        common = CommonDraw("fixture_family", 0, (g,))
        mon = monitoring_mission(ctx, common)
        tr = transit_mission(ctx, common)
        # 独立预期：U D.2.4，仅TaskSpec.intent不同，序列键与公共抽签不变。
        expected = replace(mon, tasks=(replace(mon.tasks[0], intent="transit"),))
        self.assertEqual(asdict(tr), asdict(expected))
        self.assertEqual(tr.tasks[0].target_id, mon.tasks[0].target_id)

    def test_analytic_circle_chords_and_all_lanes(self):
        base = [Clearance("world", circle(2000.0), -1, 35.0),
                Clearance("alert:t", circle(50.0), 1, 10.0)]
        warnings = {"t": circle(200.0)}
        def check(h, ds=(0.0,)):
            return assess_straight_bundle(
                base, warnings, "t", (0.0, h), (1.0, 0.0),
                tuple((0.0, d) for d in ds), -500.0, 500.0,
                band_m=10.0, align_m=100.0, retreat_m=50.0)
        for h in (59.0, 60.0, 100.0, 190.0, 191.0, 200.0, 201.0):
            # 独立解析：最小警戒外距=|h|-50≥10；预警内深度=200-|h|≥10。
            expected = 60.0 <= abs(h) <= 190.0
            self.assertEqual(bool(check(h)["feasible"]), expected, f"h={h}")
        # 独立解析：中心h=65合法，但左/右偏移中h=55的一条侵犯10m警戒余量。
        self.assertTrue(check(65.0)["feasible"])
        self.assertFalse(check(65.0, (-10.0, 10.0))["feasible"])
        # 独立解析：y=100与R=200圆的交点x=±sqrt(200²-100²)。
        got = check(100.0)
        bounds = got["target_intervals"][0]
        root = math.sqrt(200.0 ** 2 - 100.0 ** 2)
        # 解析根比较只用机器浮点间距，非物理阈值放宽。
        np.testing.assert_array_max_ulp(np.asarray(bounds, float),
                                       np.array([-root, root]), maxulp=4)

    def test_transit_nominal_semantics(self):
        fs = [facility("t")]
        x = np.arange(-300.0, 300.1, 1.0)
        t = np.arange(len(x), dtype=np.int64) * 100_000
        p = np.c_[x, np.full(len(x), 100.0), np.full(len(x), 80.0)]
        v = np.c_[np.full(len(x), 10.0), np.zeros((len(x), 2))]
        got = screen_transit_member(fs, "t", t, p, v)
        # 独立解析：单调直线，目标warning一次，离alert50m；20s移动200m不驻留。
        self.assertTrue(got["passed"])
        self.assertTrue(got["conditions"]["single_warning_visit"])
        self.assertTrue(got["conditions"]["no_dwell_window"])
        # 手工驻留前缀超过20s，虽然在warning外，U D.4仍要求全窗口不得驻留。
        p2 = np.vstack([np.repeat(p[:1], 202, axis=0), p[1:]])
        v2 = np.vstack([np.zeros((202, 3)), v[1:]])
        t2 = np.arange(len(p2), dtype=np.int64) * 100_000
        bad = screen_transit_member(fs, "t", t2, p2, v2)
        self.assertFalse(bad["passed"])
        self.assertFalse(bad["conditions"]["no_dwell_window"])

    def test_builder_and_checker_dispatch(self):
        from v08.motion import plan, optimize_checks
        from v08.motion.intents import transit, monitoring
        from v08.motion.intent_dispatch import skeleton_builder, semantic_checker
        # 独立预期：U D.2，精确意图路由；不把transit交给monitoring。
        self.assertIs(skeleton_builder("monitoring"), monitoring.propose_and_build)
        self.assertIs(skeleton_builder("transit"), transit.propose_and_build)
        self.assertIs(semantic_checker("monitoring"), optimize_checks.check_monitoring)
        self.assertIs(semantic_checker("transit"), optimize_checks.check_transit)
        sentinel = object()
        task = TaskSpec("t", "transit", "z")
        with patch.object(transit, "propose_and_build", return_value=sentinel) as f:
            got = plan.plan_attempt(None, None, task, {}, (), None)
        self.assertIs(got, sentinel)
        f.assert_called_once_with(None, None, task, {}, None)


if __name__ == "__main__":
    unittest.main()
