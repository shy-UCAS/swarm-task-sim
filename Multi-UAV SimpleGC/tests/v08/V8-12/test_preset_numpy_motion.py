"""预置纯测试：解析圆偏移、反向圆弧连接、连续时间、随机键和静止初态。"""
import dataclasses
import inspect
import math
import subprocess
import sys
import unittest
import numpy as np

from synth_v8_12 import scene_and_family
from v08.contract.monitoring import initial_states
from v08.sampler.common import sample_common
from v08.sampler.keys import RngKey, rng_for, key_words
from v08.motion.path import circle_offsets, opposite_arc_join, periodic_radius
from v08.motion.nominal import KinematicPiece, continuous_minimum
from v08.sim.guidance import NODE_TOL_M


class TestMotionPure(unittest.TestCase):
    def test_periodic_radius_is_not_constant(self):
        coefficients = (10.0, -10.0, 10.0, -10.0)
        phi = np.array([0.0, math.pi / 2, math.pi, 3 * math.pi / 2])
        rho = np.asarray(periodic_radius(phi, 500.0, coefficients))
        repeated = np.asarray(periodic_radius(phi + 2 * math.pi, 500.0, coefficients))
        np.testing.assert_allclose(
            repeated, rho, rtol=0, atol=NODE_TOL_M,
            err_msg="周期B样条数学不变量：phi加2pi不变")
        self.assertAlmostEqual(abs(float(rho[0] - rho[1])), 20.0 / 3.0,
                               delta=NODE_TOL_M,
                               msg="解析解：均匀三次周期样条在节点的权重1/6,4/6,1/6；交替±10得到相邻差20/3")

    def test_circle_offset_distance(self):
        # 同心圆解析最近距离=半径差=偏移差。360个角度仅为测试采样集。
        theta = np.linspace(0.0, 2 * math.pi, 360, endpoint=False)
        curves = np.asarray(circle_offsets(100.0, (0.0, 3.0), theta))
        self.assertEqual(curves.shape, (2, 360, 2),
                         "接口约定：成员、角度、平面坐标三维数组")
        np.testing.assert_allclose(
            np.linalg.norm(curves[0], axis=1), 100.0, rtol=0, atol=NODE_TOL_M,
            err_msg="解析圆：第一车道半径100")
        np.testing.assert_allclose(
            np.linalg.norm(curves[1], axis=1), 97.0, rtol=0, atol=NODE_TOL_M,
            err_msg="逆时针左法向向内，半径100-3=97")
        pair = np.linalg.norm(curves[0][:, None] - curves[1][None, :], axis=2)
        self.assertAlmostEqual(float(pair.min()), 3.0, delta=NODE_TOL_M,
                               msg="解析解：同心圆最近点同方位，最小距离恰为3")

    def test_opposite_curvature_has_straight(self):
        for speed, expected in ((4.0, 5.0), (10.0, 6.0)):
            with self.subTest(speed=speed):
                joined = opposite_arc_join(
                    radius_m=30.0, angle_rad=math.pi / 2,
                    speed_m_s=speed, chord_m=0.5)
                parts = joined.primitives
                self.assertEqual(tuple(x.kind for x in parts), ("arc", "line", "arc"),
                                 "r4 6.6：反向圆弧中间必须实际插入直线")
                self.assertGreaterEqual(parts[1].length_m, expected,
                                        "r4 6.6：max(5,0.6v)，4m/s为5，10m/s为6")
                for first, second in zip(parts, parts[1:]):
                    np.testing.assert_allclose(
                        first.end_tangent, second.start_tangent,
                        rtol=0, atol=NODE_TOL_M,
                        err_msg="r4 6.6：primitive接点切向连续")
                xy = np.asarray(joined.xy)
                self.assertTrue(np.all(np.linalg.norm(np.diff(xy, axis=0), axis=1) > 0),
                                "引导接口：不得有重复点形成零长度弦")

    def test_continuous_time_catches_between_nodes(self):
        a = (KinematicPiece(0.0, 1.0, (-2.0, 0.0), (4.0, 0.0), (0.0, 0.0)),)
        b = (KinematicPiece(0.0, 1.0, (2.0, 0.0), (-4.0, 0.0), (0.0, 0.0)),)
        found = continuous_minimum(a, b)
        self.assertAlmostEqual(found.min_distance_m, 0.0, delta=NODE_TOL_M,
                               msg="手算：两端距离4，在t=0.5交会；不能只验节点")
        self.assertAlmostEqual(found.time_s, 0.5, delta=NODE_TOL_M,
                               msg="手算：-2+4t=2-4t => t=1/2")
        parallel = (KinematicPiece(0.0, 1.0, (2.0, 3.0), (-4.0, 0.0), (0.0, 0.0)),)
        found = continuous_minimum(a, parallel)
        self.assertAlmostEqual(found.min_distance_m, 3.0, delta=NODE_TOL_M,
                               msg="解析解：垂直偏移3，x相同处距离最小=3")
        # 二次运动会使相对距离平方为四次；需要导数的区间内根。
        accelerating = (KinematicPiece(0.0, 2.0, (0.0, 0.0), (0.0, 0.0), (2.0, 0.0)),)
        fixed = (KinematicPiece(0.0, 2.0, (1.0, 3.0), (0.0, 0.0), (0.0, 0.0)),)
        found = continuous_minimum(accelerating, fixed)
        self.assertAlmostEqual(found.min_distance_m, 3.0, delta=NODE_TOL_M,
                               msg="解析解：位置x=t²，到(1,3)在t=1最近")
        self.assertAlmostEqual(found.time_s, 1.0, delta=NODE_TOL_M,
                               msg="解析解：(t²-1)²+9在[0,2]的最小点t=1")

    def test_common_draw_and_rng_isolation(self):
        _, family = scene_and_family()
        sig = inspect.signature(sample_common)
        self.assertEqual(list(sig.parameters), ["family", "draw_index"],
                         "r4 5.1：公共抽签只收family和draw_index，无意图/任务/目标/kwargs")
        first = sample_common(family, 0)
        same = sample_common(family, 0)
        self.assertEqual(dataclasses.asdict(first), dataclasses.asdict(same),
                         "r4 13.5：同业务键同结果")
        all_members = [m for g in first.groups for m in g.member_ids]
        self.assertEqual(sorted(all_members), ["a", "b"],
                         "r4 5.1：全体成员恰好分配一次，无重复无遗漏")
        self.assertTrue(all(len(g.member_ids) >= 1 for g in first.groups),
                        "r4 5.1：先给每组1人")
        for g in first.groups:
            self.assertEqual((g.approach_mode, g.member_variations, g.variation_probability),
                             ("single", (), 0.0),
                             "上层D.2：③同向、组内差异关闭并记录p=0")
            self.assertTrue(4.0 <= g.speed_profile.initial_speed_m_s <= 10.0,
                            "r4 5.1：初始期望速度U[4,10]")
            self.assertTrue(0.0 <= g.speed_profile.change_rate_per_min <= 1.0,
                            "r4 5.1：lambda初值U[0,1]")
        base = RngKey(family.family_id, 0, "shape", mission=0, group="g0", segment=0)
        other = dataclasses.replace(base, purpose="connect")
        before = rng_for(other).integers(0, 2**31, size=32)
        rng_for(dataclasses.replace(base, attempt=1)).random(32)
        after = rng_for(other).integers(0, 2**31, size=32)
        np.testing.assert_array_equal(
            before, after, err_msg="r4 13.5数学不变量：另一个键的流不受attempt调用影响")
        self.assertNotEqual(key_words(base), key_words(dataclasses.replace(base, attempt=1)),
                            "既有键协议：attempt参与规范SHA256输入")
        self.assertEqual(dataclasses.asdict(first), dataclasses.asdict(sample_common(family, 0)),
                         "r4 13.5：形态重试不影响公共抽签")

    def test_initial_states_are_stationary(self):
        _, family = scene_and_family()
        states = initial_states(family, ("a", "b"))
        for m, y in (("a", -20.0), ("b", 20.0)):
            self.assertEqual(states[m].p, (-1500.0, y, 120.0),
                             "夹具手算与上层D.2：位置取family_initial，不作平移")
            self.assertEqual((states[m].v, states[m].a),
                             ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
                             "上层D.2第6条：忽略夹具特意设置的非零v/a")
            self.assertEqual((states[m].segment_index, states[m].tau_us), (0, 0),
                             "既有V8-08第0段入口协议")

    def test_core_imports_without_shapely(self):
        program = """
import importlib
import importlib.abc
import sys
class NoShapely(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "shapely" or fullname.startswith("shapely."):
            raise RuntimeError("core imported shapely: " + fullname)
sys.meta_path.insert(0, NoShapely())
for module in (
    "v08.scene.exact", "v08.scene.field", "v08.scene.context",
    "v08.contract.monitoring", "v08.sampler.common",
    "v08.motion.path", "v08.motion.formation", "v08.motion.feasible",
    "v08.motion.connect", "v08.motion.speed", "v08.motion.nominal",
    "v08.motion.nominal_checks", "v08.motion.plan",
    "v08.motion.intents.monitoring",
):
    importlib.import_module(module)
"""
        result = subprocess.run([sys.executable, "-B", "-c", program],
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0,
                         "上层C.4：核心模块无直接或间接shapely导入\n" + result.stderr)


if __name__ == "__main__":
    unittest.main()
