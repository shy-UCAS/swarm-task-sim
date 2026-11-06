"""V8-17 预置测试；未经运行。本地几何/接口层，依赖项目环境。"""
import math
import unittest
from contextlib import nullcontext
from dataclasses import asdict, replace
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import shapely  # 明确与纯数值文件分开。

from v08.contract.monitoring import (
    CommonDraw, GroupSpec, SpeedProfilePrior, TaskSpec, monitoring_mission)
from v08.contract.single_intent import intrusion_mission, transit_mission
from v08.motion.layer_limits import constraints_for_task
from v08.motion.intrusion_numeric import preentry_clearance_ok
from v08.motion.nominal_checks import screen_intrusion_member
from v08.motion.optimize import load_settings
from v08.motion.optimize_checks import check_intrusion
from v08.motion.transit_chords import entry_planner


def circle(r, c=(0.0, 0.0)):
    return dict(type="Circle", center_m=list(c), radius_m=float(r))


def facility(fid, c=(0.0, 0.0)):
    return NS(id=fid, center=c, geometry=circle(20, c),
              offsets=dict(warning=280.0, alert=140.0, protected=80.0),
              layers=dict(warning=circle(300, c), alert=circle(160, c),
                          protected=circle(100, c)))


def context(collision=False):
    fs = [facility("t"), facility("__crossing__t::alert" if collision else "z",
                                 (2000.0, 0.0))]
    return NS(facilities=fs, facility_by_id={f.id: f for f in fs},
              world=circle(4000), obstacles=[], extra={}, cold_build=nullcontext,
              params=dict(world_margin_m=35.0, obstacle_margin_m=35.0,
                          forbidden_margin_m=10.0,
                          pre_entry_warning_clearance_m=10.0,
                          alignment_length_m=100.0),
              family=NS(initial_states={"u1": {}, "u2": {}}),
              inputs={"sha256": {}})


def trace(xs):
    x = np.asarray(xs, float)
    p = np.c_[x, np.zeros(len(x)), np.full(len(x), 100.0)]
    v = np.c_[np.gradient(x) * 10.0, np.zeros((len(x), 2))]
    return np.arange(len(x), dtype=np.int64) * 100_000, p, v


class Line:
    # 只测语义检查，不冒充通过动力学硬检查的优化样条。
    release_s = 0.0
    end_s = 40.0
    altitude_m = 100.0

    def __init__(self, endpoint):
        self.endpoint = float(endpoint)

    def evaluate(self, t, derivative=0):
        a = np.asarray(t, float)
        if derivative == 0:
            x = -500.0 + (self.endpoint + 500.0) * np.clip(a / 40.0, 0.0, 1.0)
        elif derivative == 1:
            x = np.where((a >= 0) & (a < 40), (self.endpoint + 500.0) / 40.0, 0.0)
        else:
            x = np.zeros_like(a)
        return np.stack([x, np.zeros_like(x)], axis=-1)


class GeometryPreset(unittest.TestCase):
    def test_crossing_table_all_seven_intents(self):
        ctx = context()
        expected = dict(monitoring=(), transit=(), area_search=(),
                        close_observation=(), feint=("alert",),
                        intrusion=("alert", "protected"))
        for intent, deeper in expected.items():
            cons = constraints_for_task(ctx, TaskSpec("task0", intent, "t"))
            # 新返回合同恰三键；原base的顺序、sense和阈值仍取S定义。
            self.assertEqual(set(cons), {"base", "warnings", "crossing_boundaries"})
            target_forbidden = (None if intent == "intrusion" else
                                "protected" if intent == "feint" else "alert")
            expected_base = [("world", -1, 35.0)]
            if target_forbidden:
                expected_base.append((target_forbidden + ":t", 1, 10.0))
            expected_base.append(("alert:z", 1, 10.0))
            self.assertEqual([(v.name, v.sense, v.minimum_m) for v in cons["base"]],
                             expected_base)
            warnings, cross = cons["warnings"], cons["crossing_boundaries"]
            # 独立预期：U D.2，原warning顺序不变；四个上限1意图没有新增边界。
            self.assertEqual(list(warnings), ["t", "z"])
            self.assertEqual(list(cross)[:2], ["t", "z"])
            self.assertEqual(len(cross), 2 + len(deeper))
            self.assertEqual(list(cross.values())[:2], list(warnings.values()))
            self.assertEqual(list(cross.values())[2:],
                             [ctx.facility_by_id["t"].layers[k] for k in deeper])
            if not deeper:
                self.assertEqual(list(cross.items()), list(warnings.items()))
        # 独立预期：S冻结配置不支持detour，不能根据设计文字补0。
        with self.assertRaises(ValueError):
            constraints_for_task(ctx, TaskSpec("task0", "detour", "t"))
        c = constraints_for_task(context(True), TaskSpec("task0", "intrusion", "t"))
        # 手工碰撞反例：原设施ID仍保留，新增alert用追加#转义，不覆盖warning。
        self.assertEqual(list(c["crossing_boundaries"]),
                         ["t", "__crossing__t::alert",
                          "__crossing__t::alert#", "__crossing__t::protected"])

    def test_mission_and_dispatch(self):
        ctx = context()
        g = GroupSpec("g0", ("u2", "u1"), SpeedProfilePrior(7.0, 0.5), "loose")
        common = CommonDraw("fixture_family", 0, (g,))
        mon = monitoring_mission(ctx, common)
        intr = intrusion_mission(ctx, common)
        tr = transit_mission(ctx, common)
        # 独立不变量：只有唯一任务intent变化，公共条件和target不变。
        self.assertEqual(asdict(intr),
                         asdict(replace(mon, tasks=(replace(mon.tasks[0], intent="intrusion"),))))
        self.assertEqual(intr.tasks[0].target_id, tr.tasks[0].target_id)
        from v08.motion.intent_dispatch import skeleton_builder, semantic_checker, nominal_screen
        from v08.motion.intents import intrusion, transit, monitoring
        from v08.motion import optimize_checks
        # 独立预期：U D.2精确分派，不通过名字相似而调用其他意图。
        self.assertIs(skeleton_builder("intrusion"), intrusion.propose_and_build)
        self.assertIs(skeleton_builder("transit"), transit.propose_and_build)
        self.assertIs(skeleton_builder("monitoring"), monitoring.propose_and_build)
        self.assertIs(semantic_checker("intrusion"), optimize_checks.check_intrusion)
        self.assertIs(nominal_screen("intrusion"), screen_intrusion_member)

    def test_preentry_obstacle_and_exact_rejection(self):
        ctx = context()
        with patch("v08.scene.visibility.build_planner", return_value=object()) as build:
            entry_planner(ctx, "t", 10.0)
        blockers = dict(build.call_args.args[1])
        # 独立解析：warning R300，10m余量+本例Delta10，blocker半径320。
        self.assertEqual(blockers["preentry_warning:t"]["radius_m"], 320.0)
        # 反例直线穿过目标中心，途中SDF=-300，必须拒绝；不能只查两端。
        self.assertFalse(preentry_clearance_ok(circle(300),
                                              np.array([[-400., 0.], [400., 0.]])))
        # 直线y=310，最小SDF=10，等号合法，不能自行加严格余量。
        self.assertTrue(preentry_clearance_ok(circle(300),
                                             np.array([[-400., 310.], [400., 310.]])))

    def test_nominal_three_single_entries_and_second_visit(self):
        fs = [facility("t")]
        t, p, v = trace(np.arange(-400., 1.))
        good = screen_intrusion_member(fs, "t", t, p, v)
        # 独立解析：x单调趋0，半径300/160/100各进入一次，负轮廓距离-20合法。
        self.assertTrue(good["passed"])
        self.assertEqual(good["counts"]["entries"],
                         {"warning": 1, "alert": 1, "protected": 1})
        self.assertEqual(good["first_entry_us"],
                         {"warning": 10_000_000, "alert": 24_000_000,
                          "protected": 30_000_000})
        self.assertEqual(good["end_contour_m"], -20.0)
        # 手算：进入中心，再退到x=-200，最后回中心，保护层两次进入。
        t2, p2, v2 = trace(np.r_[np.arange(-400., 1.),
                                 np.arange(-1., -201., -1.), np.arange(-199., 1.)])
        bad = screen_intrusion_member(fs, "t", t2, p2, v2)
        self.assertFalse(bad["passed"])
        self.assertEqual(bad["counts"]["entries"]["protected"], 2)
        self.assertFalse(bad["conditions"]["target_layers_monotone"])
        self.assertFalse(bad["conditions"]["single_protected_entry"])

    def test_optimized_endpoint_50_5_rejected(self):
        ctx = context()
        skel = NS(witnesses={"intent": "intrusion", "target_id": "t"})
        settings = load_settings()
        bad = check_intrusion(ctx, skel, {"u": Line(-70.5)}, settings)
        # 独立解析：圆R20，终点x=-70.5的contour距离50.5>50；
        # protected R100的距离-29.5已满足-10，故必须单独报contour失败。
        self.assertFalse(bad["passed"])
        self.assertIn("terminal_contour", [f["kind"] for f in bad["failures"]])
        # 冻结阈值50等号允许；不能在优化后硬检查偷偷沿用骨架45。
        good = check_intrusion(ctx, skel, {"u": Line(-70.0)}, settings)
        self.assertTrue(good["passed"], good["failures"])


if __name__ == "__main__":
    unittest.main()
