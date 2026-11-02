"""V8-05 预置测试 第 1 部分（规划审查方编写，实现方不得修改或删除）。

运行（在仓库根目录下，用试点环境 t2l-pilot 的 Python，NumPy 2.5.3）:
    python -B -m unittest discover -s "Multi-UAV SimpleGC/tests/v08/V8-05" -p "test_preset_v8_05_part1.py" -v

独立预期的来源：
- 随机数键：按第 1 部分规格直接用 hashlib 与 numpy.random.SeedSequence / PCG64 计算（规划审查方在云端算出，
  NumPy 2.5.3），不经过被测代码；
- 重采样、离散 Fréchet 距离、变异系数：手算的小例子与数学性质（对称、平移不变、端点下界）。
"""
import dataclasses
import os
import sys
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from v08.sampler.keys import (PURPOSES, RngKey, family_entropy, key_words, rng_for,  # noqa: E402
                              seed_sequence, validate_key)

FAM = "family_s15_9b1a9f5a704a5a43"


class TestPart1Keys(unittest.TestCase):
    def setUp(self):
        self.k = RngKey(FAM, 0, "shape", mission=3, branch=1, group="g1", segment=2, attempt=0)
        self.c = RngKey(FAM, 1, "common")

    def test_purposes(self):
        self.assertEqual(PURPOSES, ("common", "sequence", "branch", "formation", "strand", "shape",
                                    "connect", "speed", "offsets"))

    def test_family_entropy(self):
        self.assertEqual(family_entropy(FAM),
                         17033295761951673802192825044867220641126587529257377930564373351471912702236)

    def test_key_words(self):
        self.assertEqual(key_words(self.k), (1944608777, 3390293258, 1759714608, 3723536931,
                                             1107431395, 2457488179, 3482020407, 2985352395))
        self.assertEqual(key_words(self.c), (692552627, 2229909080, 2205390644, 2103597341,
                                             2852305210, 2245495620, 466354900, 2452528412))

    def test_streams(self):
        self.assertEqual(rng_for(self.k).integers(0, 2**32, size=4).tolist(),
                         [820897395, 3126841025, 2932281463, 3959937585])
        self.assertEqual(rng_for(self.c).integers(0, 2**32, size=4).tolist(),
                         [91743645, 3432407307, 3372171254, 2349845860])
        ss = seed_sequence(self.k)
        self.assertEqual(ss.entropy, family_entropy(FAM))
        self.assertEqual(tuple(ss.spawn_key), key_words(self.k))

    def test_attempt_changes_only_its_own_stream_and_order_does_not_matter(self):
        k1 = dataclasses.replace(self.k, attempt=1)
        a = rng_for(self.k).random(3).tolist()
        b = rng_for(k1).random(3).tolist()
        self.assertNotEqual(a, b)
        self.assertEqual(rng_for(k1).random(3).tolist(), b)
        self.assertEqual(rng_for(self.k).random(3).tolist(), a)

    def test_frozen(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.k.attempt = 5

    def test_invalid_keys(self):
        bad = [RngKey(FAM, 0, "common", mission=0),            # 公共抽签不得含任务成分
               RngKey(FAM, 0, "common", group="g1"),
               RngKey(FAM, 0, "shape"),                        # 非公共用途必须给出 mission
               RngKey(FAM, 0, "unknown", mission=0),
               RngKey("", 0, "common"),
               RngKey(FAM, True, "common"),                    # 布尔值不是整数
               RngKey(FAM, -1, "common"),
               RngKey(FAM, 0, "shape", mission=0, attempt=-1),
               RngKey(FAM, 0, "shape", mission=0, group=""),
               RngKey(FAM, 0, "shape", mission=1.0)]
        for k in bad:
            with self.assertRaises(ValueError, msg=repr(k)):
                validate_key(k)
            with self.assertRaises(ValueError, msg=repr(k)):
                rng_for(k)


if __name__ == "__main__":
    unittest.main(verbosity=2)
