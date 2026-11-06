"""V8-16 预置；未经运行。冻结检测器依赖本地环境，独立于numeric文件。"""
import math
import struct
import unittest

import numpy as np
import shapely
from task_v07.detectors import revisit as frozen_revisit
from v08.motion.nominal_checks import revisit as candidate_revisit
from v08.motion.skeleton import width_then_build


def bits(value):
    if isinstance(value, dict):
        return tuple((k, bits(value[k])) for k in sorted(value))
    if isinstance(value, (list, tuple)):
        return tuple(bits(x) for x in value)
    if isinstance(value, (float, np.floating)):
        return ("f64", struct.pack(">d", float(value)))
    if isinstance(value, (int, np.integer, bool, np.bool_)):
        return (type(value).__name__, int(value))
    return value


class RevisitPreset(unittest.TestCase):
    def check_case(self, xy, velocity, center, detected):
        n = len(xy)
        t = np.arange(n, dtype=np.int64) * 100_000
        levels = np.ones(n, dtype=np.int8)
        frames = np.ones(n, dtype=bool)
        args = (xy, velocity, t, levels, frames, np.asarray(center, float))
        old = frozen_revisit(*args)
        new = candidate_revisit(*args)
        # 独立预期：v0.7冻结代码的完整结果，包含float原始64位和tie-break。
        self.assertEqual(bits(new), bits(old))
        # 下面的真假另外由手工轨迹几何给出，不以待测输出作答案。
        self.assertEqual(old["detected"], detected)

    def test_positive_circle_and_negative_small_circle(self):
        theta = np.arange(0.0, 3.0 * math.pi, 0.004)
        unit = np.c_[np.cos(theta), np.sin(theta)]
        tangent = np.c_[-np.sin(theta), np.cos(theta)]
        # R=200、1.5圈，远离可达400>150且扫角足够、回到30m内：解析正例。
        self.check_case(200.0 * unit, np.c_[8.0 * tangent, np.zeros(len(theta))],
                        (0.0, 0.0), True)
        # R=30，任两点距离≤60<150，不可能满足departure：解析负例。
        self.check_case(30.0 * unit, np.c_[1.2 * tangent, np.zeros(len(theta))],
                        (0.0, 0.0), False)

    def test_straight_and_stationary(self):
        x = np.arange(-300.0, 300.1, 1.0)
        xy = np.c_[x, np.full(len(x), 100.0)]
        v = np.c_[np.full(len(x), 10.0), np.zeros((len(x), 2))]
        # 单调直线不返回、零速不eligible，分别为冻结判据的解析负例。
        self.check_case(xy, v, (0.0, 0.0), False)
        self.check_case(xy, np.zeros_like(v), (0.0, 0.0), False)

    def test_boundary_inputs_match_frozen_bits(self):
        # 浮点邻点由nextafter定义，不引入生产判据容差。
        theta = np.arange(0.0, 3.0 * math.pi, 0.004)
        for radius in (np.nextafter(75.0, 0.0), 75.0, np.nextafter(75.0, np.inf)):
            xy = radius * np.c_[np.cos(theta), np.sin(theta)]
            v = np.c_[-3.0 * np.sin(theta), 3.0 * np.cos(theta), np.zeros(len(theta))]
            n = len(xy)
            args = (xy, v, np.arange(n, dtype=np.int64) * 100_000,
                    np.ones(n, np.int8), np.ones(n, bool), np.zeros(2))
            # 独立预期：150m departure边界附近全部字段必须和冻结实现同位。
            self.assertEqual(bits(candidate_revisit(*args)), bits(frozen_revisit(*args)))

    def test_width_selection_cannot_fallback_after_build_failure(self):
        events = []
        sentinel = {"ok": False, "reason": "route_blocked"}
        def probe(name):
            events.append(("probe", name))
            return {"feasible": True}
        def build(name, payload):
            events.append(("build", name))
            return sentinel
        got = width_then_build(("abreast", "echelon", "column"), probe, build)
        # 独立预期：U D.3.3/旧机制，只构造首个可行队形一次，下游失败原样返回。
        self.assertIs(got, sentinel)
        self.assertEqual(events, [("probe", "abreast"), ("build", "abreast")])


if __name__ == "__main__":
    unittest.main()
