"""V8-16 预置；未经运行。真实数据/全量/监视回归，缺输入明确skip不算通过。"""
import json
import os
import unittest
from pathlib import Path

import numpy as np
import shapely
from v08.scene.context import load_context
from v08.sim.types import MemberTrack
from v08.criteria.segment import SegmentTask, verify_segments
from v08.criteria.validity import check_validity, visible_track
from v08.runner.joint_monitoring import compare_dirs


def jread(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def envpath(name):
    value = os.environ.get(name)
    if not value:
        raise unittest.SkipTest(f"{name}未设置；该验收未执行，不是通过")
    return Path(value).resolve()


class TransitArtifactsPreset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = envpath("V8_16_TRANSIT_OUT")
        cls.baseline = envpath("V8_16_MONITOR_BASELINE")
        cls.data = envpath("V8_16_DATA_ROOT")
        cls.cache = envpath("V8_16_TEST_CACHE")
        cls.entries = {e["family_id"]: e for e in jread(envpath("V8_16_DEVSET"))}
        cls.rows = jread(cls.out / "records.json")
        cls.summary = jread(cls.out / "summary.json")

    def test_completed_keys_and_paired_common_fields(self):
        stage = self.summary["stage"]
        expected = {"quick": 20, "full": 200}[stage]
        # 独立预期：U D.5/D.6统计完成合同数，不要求全部成功。
        self.assertEqual(len(self.rows), expected)
        self.assertEqual(len({r["contract_id"] for r in self.rows}), expected)
        if stage == "full":
            pairs = {(r["family_id"], r["draw_index"]) for r in self.rows}
            self.assertEqual(pairs, {(fid, d) for fid in self.entries for d in range(5)})
        for r in self.rows:
            cid = r["contract_id"]
            tr = jread(self.out / "contracts" / cid / "contract.json")
            mon = jread(self.baseline / "contracts" / cid / "contract.json")
            # 独立预期：同一公共抽签/sequence键的字段不变量，U D.2.4。
            self.assertEqual(tr["intent"], "transit")
            for k in ("family_id", "draw_index", "group_id", "member_ids", "group_size",
                      "target_id", "initial_speed_m_s", "formation_prior"):
                self.assertEqual(tr[k], mon[k], f"{cid}/{k}")
            # 独立预期：r5唯一20次预算；普通失败保留最终分类。
            self.assertGreaterEqual(r["attempts"], 0)
            self.assertLessEqual(r["attempts"], 20)
            if r["success"]:
                self.assertGreaterEqual(r["attempts"], 1)
            else:
                self.assertIsNotNone(r["failure"])

    def test_retained_disk_tracks_with_frozen_verifiers(self):
        for r in self.rows:
            if not r["success"]:
                continue
            with self.subTest(contract=r["contract_id"]):
                ctx = load_context(self.entries[r["family_id"]],
                                   data_root=self.data, cache_dir=self.cache)
                d = self.out / "contracts" / r["contract_id"]
                saved = jread(d / "result.json")
                # 独立预期：保存结果必须与记录一致，不能验内存后写错轨迹。
                self.assertTrue(saved["success"])
                self.assertEqual(saved["release_us"], r["release_us"])
                tracks = {}
                for m in sorted(r["member_ids"]):
                    td = d / "tracks" / m
                    a = {k: np.load(td / f"{k}.npy", allow_pickle=False)
                         for k in ("tau_us", "p", "v", "a", "segment_index")}
                    # 独立预期：固定10Hz整数微秒与单段0编号，r5第8节。
                    np.testing.assert_array_equal(np.diff(a["tau_us"]),
                                                  np.full(len(a["tau_us"]) - 1, 100_000))
                    np.testing.assert_array_equal(a["segment_index"],
                                                  np.zeros(len(a["tau_us"]), dtype=int))
                    for k in ("p", "v", "a"):
                        self.assertTrue(np.isfinite(a[k]).all(), k)
                    tracks[m] = MemberTrack(m, a["tau_us"], a["p"], a["v"], a["a"],
                                            a["segment_index"], ())
                tasks = [SegmentTask(0, "transit", r["target_id"])]
                verdicts = verify_segments(ctx.scene, tracks, saved["release_us"], tasks)
                # 独立预期：冻结V8-11过境行为代理，包括单次穿越与全窗口无驻留。
                self.assertTrue(all(v.passed for v in verdicts))
                valid = check_validity(ctx.scene, [
                    visible_track(tracks[m], saved["release_us"][m]) for m in sorted(tracks)])
                # 独立预期：冻结物理门禁，2m不得放宽。
                self.assertTrue(valid.passed)
                if valid.min_separation_m is not None:
                    self.assertGreaterEqual(valid.min_separation_m, 2.0)

    def test_five_single_process_repeats(self):
        repeat = envpath("V8_16_TRANSIT_RERUN")
        rows = jread(repeat / "records.json")
        expected = sorted(r["contract_id"] for r in self.rows)[:5]
        # 独立预期：U D.6预先固定字典序5键，不能替换失败键。
        self.assertEqual(sorted(r["contract_id"] for r in rows), expected)
        for cid in expected:
            got = compare_dirs(self.out / "contracts" / cid,
                               repeat / "contracts" / cid)
            self.assertTrue(got["file_sets_equal"], cid)
            self.assertTrue(got["bytes_equal"], f"{cid}: {got}")


class MonitoringRegressionPreset(unittest.TestCase):
    def test_twenty_monitoring_directories_byte_equal(self):
        baseline = envpath("V8_16_MONITOR_BASELINE")
        # 此变量指向production-quick输出中的run目录，含records.json/contracts。
        repeat = envpath("V8_16_MONITOR_REPEAT")
        rows = jread(repeat / "records.json")
        # 独立预期：U D.2.5，20个原监视键，不排除任何合同文件。
        self.assertEqual(len(rows), 20)
        self.assertEqual(len({r["contract_id"] for r in rows}), 20)
        for r in rows:
            cid = r["contract_id"]
            got = compare_dirs(baseline / "contracts" / cid, repeat / "contracts" / cid)
            self.assertTrue(got["file_sets_equal"], cid)
            self.assertTrue(got["bytes_equal"], f"{cid}: {got}")


if __name__ == "__main__":
    unittest.main()
