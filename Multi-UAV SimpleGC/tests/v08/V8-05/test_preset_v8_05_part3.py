"""V8-05 预置测试 第 3 部分（规划审查方编写，实现方不得修改或删除）。

运行（在仓库根目录下，用试点环境 t2l-pilot 的 Python，NumPy 2.5.3）:
    python -B -m unittest discover -s "Multi-UAV SimpleGC/tests/v08/V8-05" -p "test_preset_v8_05_part3.py" -v

独立预期的来源：
- 随机数键：按第 1 部分规格直接用 hashlib 与 numpy.random.SeedSequence / PCG64 计算（规划审查方在云端算出，
  NumPy 2.5.3），不经过被测代码；
- 重采样、离散 Fréchet 距离、变异系数：手算的小例子与数学性质（对称、平移不变、端点下界）。
"""
import math
import os
import sys
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from v08.diagnostics.diversity import coefficient_of_variation  # noqa: E402


class TestPart3CV(unittest.TestCase):
    def test_values(self):
        self.assertEqual(coefficient_of_variation([2.0, 2.0, 2.0]), 0.0)
        self.assertAlmostEqual(coefficient_of_variation([1.0, 3.0]), 0.5, places=12)   # 总体标准差 1，均值 2
        self.assertAlmostEqual(coefficient_of_variation([5.0]), 0.0, places=12)

    def test_invalid(self):
        for v in ([0.0, 0.0], [-1.0, -3.0], [], [1.0, math.nan], [[1.0, 2.0]], [1.0, math.inf]):
            with self.assertRaises(ValueError, msg=repr(v)):
                coefficient_of_variation(v)


if __name__ == "__main__":
    unittest.main(verbosity=2)
