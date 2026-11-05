"""V8-15 预置；未经运行。预期来自U D.2/D.3/F.1及手算小数组。
只导入标准库/NumPy和新的纯分析模块，不依赖shapely或真实数据。
"""
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT / "tools" / "v08"))
from v15_metrics import pair_minima, select_timing_keys, choose_workers, compare_contracts


class ProtocolPreset(unittest.TestCase):
    def test_analytic_distance_dimension_and_time(self):
        t = np.array([0, 100000], dtype=np.int64)
        a = np.array([[-1., 0., 3.], [1., 0., 3.]])
        b = np.zeros((2, 3))
        r = pair_minima(t, a, b)
        self.assertAlmostEqual(r["sample_min_m"], math.sqrt(10), places=12,
                               msg="手算三维端点距离sqrt(1+9)，不能误用XY")
        self.assertEqual(r["sample_time_us"], 0,
                         "等距两端取最早帧；本稿3.1平局协议")
        self.assertEqual(r["interp_min_m"], 3.,
                         "相对轨迹x=-1到1，z=3，中点距离恰3")
        self.assertEqual(r["fraction"], .5,
                         "二次函数极小在区间中点")
        self.assertEqual(r["interval_start_us"], 0,
                         "冻结validity保留区间起点；精确时刻另存")
        self.assertEqual(r["t_s"], .05,
                         "100000微秒区间的中点为0.05秒")

    def test_no_interpolation_across_missing_frame(self):
        a = np.array([[-1., 0., 3.], [1., 0., 3.]])
        r = pair_minima(np.array([0, 200000], np.int64), a, np.zeros((2, 3)))
        self.assertAlmostEqual(r["interp_min_m"], math.sqrt(10), places=12,
                               msg="中间缺10Hz帧，不允许跨空洞插值；仅端点候选")
        e = pair_minima(np.empty(0, np.int64), np.empty((0, 3)), np.empty((0, 3)))
        self.assertIsNone(e["sample_min_m"], "无共同帧是N/A，不是0")
        self.assertIsNone(e["interp_min_m"], "无共同帧没有可插值区间")
        self.assertEqual(e["reason"], "no_common_frames", "本稿3.1缺测schema")

    def test_trimmed_equally_spaced_selection(self):
        rows = [{"order": k, "draw_index": 0, "branch": None,
                 "wall_s": float(k), "success": k != 5}
                for k in range(1, 12)]
        got = select_timing_keys(rows, count=4)
        self.assertEqual(got, [(3, 0), (5, 0), (7, 0), (9, 0)],
                         "1..11的p20=3,p80=9；七项等距取四项为3,5,7,9；失败5仍保留")
        self.assertEqual(select_timing_keys(list(reversed(rows)), count=4), got,
                         "U D.3：名单不依赖JSON输入顺序")

    def test_worker_preference_and_memory(self):
        def row(w, ratio, mem=.5):
            return {"workers": w, "inflation_median": ratio,
                    "peak_memory_fraction": mem}
        self.assertEqual(choose_workers([row(8, 1), row(16, 1), row(24, 1.5)])["selected"], 16,
                         "吞吐量8,16,16，平局选小档；24相对16增益不足10%")
        self.assertEqual(choose_workers([row(8, 1), row(16, 1), row(24, 1)])["selected"], 24,
                         "吞吐量24比16高50%，且内存合格")
        self.assertEqual(choose_workers([row(8, 1), row(16, 1), row(24, 1, .61)])["selected"], 16,
                         "U D.3：全机内存61%超过60%，不可选24")
        self.assertEqual(choose_workers([row(8, 1, .6)])["selected"], 8,
                         "U D.3内存边界为<=60%，恰60%合格")
        self.assertIsNone(choose_workers([row(8, 1, .61), row(16, 1, .7)])["selected"],
                          "没有合格档不能猜默认值")

    def test_complete_contract_bytes_no_exclusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = root / "baseline" / "contracts" / "c", root / "repeat" / "contracts" / "c"
            a.mkdir(parents=True)
            b.mkdir(parents=True)
            for p in (a, b):
                (p / "contract.json").write_bytes(b"{}")
                (p / "skeleton.json").write_bytes(b'{"x":1}')
            (root / "baseline" / "telemetry").mkdir()
            (root / "repeat" / "telemetry").mkdir()
            (root / "baseline" / "telemetry" / "c.json").write_bytes(b"1")
            (root / "repeat" / "telemetry" / "c.json").write_bytes(b"2")
            self.assertTrue(compare_contracts(a, b)["bytes_equal"],
                            "U F.1：合同外遥测不在比较根中")
            (b / "skeleton.json").write_bytes(b'{"x":2}')
            diff = compare_contracts(a, b)
            self.assertFalse(diff["bytes_equal"],
                             "P0-3/4：skeleton必须逐字节比较，不能被排除")
            self.assertEqual(diff["differing"], ["skeleton.json"],
                             "仅手工改动该文件")
            (b / "skeleton.json").write_bytes((a / "skeleton.json").read_bytes())
            (b / "timing.json").write_bytes(b"unexpected")
            self.assertFalse(compare_contracts(a, b)["file_sets_equal"],
                             "合同内排除清单为空，未知timing.json也必须发现")


if __name__ == "__main__":
    unittest.main()
