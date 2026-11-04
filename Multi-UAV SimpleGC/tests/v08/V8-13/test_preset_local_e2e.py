import json
import os
from pathlib import Path
import unittest
import numpy as np
import shapely  # 此文件明确依赖；不得与numeric文件合并
from v08.scene.context import load_context
from v08.sim.types import MemberTrack
from v08.criteria.segment import SegmentTask, verify_segments
from v08.criteria.validity import visible_track, check_validity


class LocalEndToEndPreset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(os.environ["V8_13_RUN_OUT"]).resolve()
        cls.data = Path(os.environ["V8_13_DATA_ROOT"]).resolve()
        cls.cache = Path(os.environ["V8_13_TEST_CACHE"]).resolve()
        entries = json.loads(Path(os.environ["V8_13_DEVSET"]).read_text(encoding="utf-8"))
        cls.entries = {e["family_id"]: e for e in entries}
        cls.summary = json.loads((cls.out/"summary.json").read_text(encoding="utf-8"))
        cls.records = json.loads((cls.out/"records.json").read_text(encoding="utf-8"))

    def test_keys_and_attempt_budget(self):
        stage = self.summary["stage"]
        expected = {"quick": 20, "full": 200}[stage]
        self.assertEqual(len(self.records), expected,
                         "U D.3/D.4：这是已完成合同数，不是成功配额")
        ids = [r["contract_id"] for r in self.records]
        self.assertEqual(len(set(ids)), expected, "业务key不得重复覆盖")
        for r in self.records:
            self.assertGreaterEqual(r["attempts"], 0, "精确证书可在随机尝试前拒绝")
            self.assertLessEqual(r["attempts"], 20, "全链路预算20")
            if r["success"]:
                self.assertGreaterEqual(r["attempts"], 1, "成功须实际执行一次全链路")
            else:
                self.assertIsNotNone(r["failure"], "失败种子也须留最终失败证据")


    def test_quick_coverage_or_full_draws(self):
        by_family = {}
        for r in self.records:
            by_family.setdefault(r["family_id"], []).append(r)
        if self.summary["stage"] == "quick":
            self.assertEqual(len(by_family), 10, "U D.3：快速10族")
            self.assertTrue(all(len(v) == 2 for v in by_family.values()),
                            "U D.3：每族恰2合同，失败不替换")
            for k in (1, 2, 3):
                self.assertGreaterEqual(sum(r["facility_count"] == k for r in self.records),
                                        2, "U D.3：每个设施数档至少2合同")
            largest = min(self.entries.values(),
                          key=lambda e: (-e["vehicle_count"], e["order"]))
            self.assertIn(largest["family_id"], by_family, "U D.3：机数最大族")
            self.assertGreaterEqual(sum(r["initial_speed_m_s"] < 5.5
                                        for r in self.records), 2,
                                    "U D.3：至少2个低于5.5的原公共抽签")
        else:
            self.assertEqual(set(by_family), set(self.entries), "U D.4：登记40族不删难族")
            for values in by_family.values():
                self.assertEqual(sorted(r["draw_index"] for r in values), list(range(5)),
                                 "U D.4：每族draw0..4，成败都计入")

    def test_every_retained_contract_with_frozen_verifiers(self):
        for r in self.records:
            if not r["success"]:
                continue
            with self.subTest(contract=r["contract_id"]):
                ctx = load_context(self.entries[r["family_id"]],
                                   data_root=self.data, cache_dir=self.cache)
                tracks = {}
                for m in sorted(r["member_ids"]):
                    root = self.out/"contracts"/r["contract_id"]/"tracks"/m
                    a = {n: np.load(root/(n+".npy"), allow_pickle=False)
                         for n in ("tau_us", "p", "v", "a", "segment_index")}
                    # 来源：r4 8.4、整数微秒统一时钟，检查输出原始数组。
                    self.assertEqual(int(a["tau_us"][0]), 0, "首段保留预释放帧")
                    np.testing.assert_array_equal(np.diff(a["tau_us"]),
                                                  np.full(len(a["tau_us"])-1, 100000))
                    np.testing.assert_array_equal(a["segment_index"],
                                                  np.zeros(len(a["tau_us"]), dtype=int))
                    for name in ("p", "v", "a"):
                        self.assertTrue(np.isfinite(a[name]).all(), "输出必须有限："+name)
                    tracks[m] = MemberTrack(m, a["tau_us"], a["p"], a["v"], a["a"],
                                            a["segment_index"], ())
                tasks = [SegmentTask(0, "monitoring", r["target_id"])]
                verdicts = verify_segments(ctx.scene, tracks, r["release_us"], tasks)
                self.assertTrue(all(v.passed for v in verdicts),
                                "冻结V8-11：每个保留段的标签/圈层/无驻留门禁")
                visible = [visible_track(tracks[m], r["release_us"][m])
                           for m in sorted(tracks)]
                valid = check_validity(ctx.scene, visible)
                self.assertTrue(valid.passed, "冻结V8-11：2m采样间距和限制区")
                if valid.min_separation_m is not None:
                    self.assertGreaterEqual(valid.min_separation_m, 2.,
                                            "criteria quality：不允许数值放宽2m")



if __name__ == "__main__":
    unittest.main()
