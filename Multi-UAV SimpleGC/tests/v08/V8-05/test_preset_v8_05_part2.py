"""V8-05 预置测试 第 2 部分（规划审查方编写，实现方不得修改或删除）。

运行（在仓库根目录下，用试点环境 t2l-pilot 的 Python，NumPy 2.5.3）:
    python -B -m unittest discover -s "Multi-UAV SimpleGC/tests/v08/V8-05" -p "test_preset_v8_05_part2.py" -v

独立预期的来源：
- 随机数键：按第 1 部分规格直接用 hashlib 与 numpy.random.SeedSequence / PCG64 计算（规划审查方在云端算出，
  NumPy 2.5.3），不经过被测代码；
- 重采样、离散 Fréchet 距离、变异系数：手算的小例子与数学性质（对称、平移不变、端点下界）。
"""
import math
import os
import sys
import time
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from v08.diagnostics.diversity import (discrete_frechet, pairwise_discrete_frechet,  # noqa: E402
                                       resample_polyline)


class TestPart2Frechet(unittest.TestCase):
    def test_resample_straight_and_corner(self):
        r = resample_polyline([(0, 0), (10, 0)], 2.5)
        np.testing.assert_allclose(r, [[0, 0], [2.5, 0], [5, 0], [7.5, 0], [10, 0]], atol=1e-12)
        r = resample_polyline([(0, 0), (10, 0)], 3.0)
        np.testing.assert_allclose(r, [[0, 0], [3, 0], [6, 0], [9, 0], [10, 0]], atol=1e-12)
        r = resample_polyline([(0, 0), (4, 0), (4, 3)], 2.0)
        np.testing.assert_allclose(r, [[0, 0], [2, 0], [4, 0], [4, 2], [4, 3]], atol=1e-12)

    def test_resample_edge_cases(self):
        r = resample_polyline([(0, 0), (0.9, 0)], 0.3)          # 0.9/0.3 有浮点误差，不得多出或少掉终点
        np.testing.assert_allclose(r, [[0, 0], [0.3, 0], [0.6, 0], [0.9, 0]], atol=1e-12)
        r = resample_polyline([(0, 0), (0, 0), (2, 0)], 1.0)     # 零长度腿跳过
        np.testing.assert_allclose(r, [[0, 0], [1, 0], [2, 0]], atol=1e-12)
        r = resample_polyline([(1, 1, 5), (1, 1, 5)], 1.0)       # 总长为 0：只返回一点
        np.testing.assert_allclose(r, [[1, 1, 5]], atol=0)
        r = resample_polyline([(0, 0, 0), (0, 0, 4)], 2.0)       # 三维
        np.testing.assert_allclose(r, [[0, 0, 0], [0, 0, 2], [0, 0, 4]], atol=1e-12)
        for args in (([(0, 0)], 1.0), ([(0, 0), (1, 0)], 0.0), ([(0, 0), (1, 0)], -1.0),
                     ([(0, 0), (math.nan, 0)], 1.0), ([(0, 0), (1, 0)], math.inf), ([0, 1, 2], 1.0)):
            with self.assertRaises(ValueError, msg=repr(args)):
                resample_polyline(*args)

    def test_frechet_known_values(self):
        self.assertEqual(discrete_frechet([(0, 0), (1, 0), (2, 0)], [(0, 0), (1, 0), (2, 0)]), 0.0)
        self.assertAlmostEqual(discrete_frechet([(0, 0), (1, 0), (2, 0)], [(0, 1), (1, 1), (2, 1)]), 1.0, places=12)
        self.assertAlmostEqual(discrete_frechet([(0, 0)], [(3, 4), (0, 0)]), 5.0, places=12)
        # 反向折线：Hausdorff 距离为 0，但 Fréchet 必须从两端配对，结果为 2
        self.assertAlmostEqual(discrete_frechet([(0, 0), (1, 0), (2, 0)], [(2, 0), (1, 0), (0, 0)]), 2.0, places=12)
        self.assertAlmostEqual(discrete_frechet([(0, 0), (2, 0)], [(0, 1), (1, 3), (2, 1)]), math.sqrt(10), places=12)
        self.assertAlmostEqual(discrete_frechet([(0, 0), (1, 0), (2, 0), (3, 0)], [(0, 0), (3, 0)]), 1.0, places=12)

    def test_frechet_properties(self):
        rng = np.random.default_rng(7)
        for _ in range(20):
            P = rng.normal(size=(rng.integers(1, 12), 2)) * 10
            Q = rng.normal(size=(rng.integers(1, 12), 2)) * 10
            f = discrete_frechet(P, Q)
            self.assertAlmostEqual(f, discrete_frechet(Q, P), places=12)
            self.assertAlmostEqual(f, discrete_frechet(P + 37.5, Q + 37.5), places=9)
            self.assertGreaterEqual(f + 1e-12, np.linalg.norm(P[0] - Q[0]))
            self.assertGreaterEqual(f + 1e-12, np.linalg.norm(P[-1] - Q[-1]))
            self.assertEqual(discrete_frechet(P, P), 0.0)

    def test_frechet_invalid_and_large(self):
        for P, Q in (([(0, 0)], [(0, 0, 0)]), ([], [(0, 0)]), ([(0, math.nan)], [(0, 0)])):
            with self.assertRaises(ValueError):
                discrete_frechet(P, Q)
        n = 1500
        P = np.c_[np.linspace(0, 1000, n), np.zeros(n)]
        Q = np.c_[np.linspace(0, 1000, n), np.full(n, 3.0)]
        t0 = time.perf_counter()
        self.assertAlmostEqual(discrete_frechet(P, Q), 3.0, places=9)    # 不得因递归深度出错
        self.assertLess(time.perf_counter() - t0, 30.0)

    def test_pairwise(self):
        paths = [[(0, 0), (1, 0), (2, 0)], [(0, 1), (1, 1), (2, 1)], [(2, 0), (1, 0), (0, 0)]]
        M = pairwise_discrete_frechet(paths)
        self.assertEqual(M.shape, (3, 3))
        np.testing.assert_allclose(np.diag(M), 0.0, atol=0)
        np.testing.assert_allclose(M, M.T, atol=0)
        self.assertAlmostEqual(M[0, 1], 1.0, places=12)
        self.assertAlmostEqual(M[0, 2], 2.0, places=12)
        self.assertAlmostEqual(M[1, 2], discrete_frechet(paths[1], paths[2]), places=12)
        with self.assertRaises(ValueError):
            pairwise_discrete_frechet([])


if __name__ == "__main__":
    unittest.main(verbosity=2)
