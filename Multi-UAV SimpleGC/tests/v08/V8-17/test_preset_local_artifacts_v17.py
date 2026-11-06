"""V8-17 预置测试；未经运行。真实输出/冻结核验层，缺输入skip不算通过。"""
import json
import os
import unittest
from pathlib import Path
import numpy as np
import shapely

from v08.scene.context import load_context
from v08.scene.exact import signed_distance
from v08.sim.types import MemberTrack
from v08.criteria.segment import SegmentTask, verify_segments
from v08.criteria.validity import check_validity, visible_track
from v08.runner.joint_monitoring import compare_dirs

QUICK = tuple(f"o{o:02d}_d{d}" for o in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11)
              for d in (0, 1))
TIMER_KEYS = {
    "seconds", "wall_s", "wall_time", "elapsed_s", "elapsed_seconds",
    "prepare_s", "solve_s", "check_s", "optimization_s", "timing",
    "stage_timing", "skeleton_detail", "build_seconds", "attempt_wall_s",
    "skeleton_s", "optimize_s", "simulation_s", "verify_s", "lp_s",
    "chord_set_s", "chord_exact_s", "corridor_s", "route_s", "candidate_s",
    "cache_hits", "cache_misses_computed", "traceback", "tracebacks", "pid"
}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def pathenv(name):
    value = os.environ.get(name)
    if not value:
        raise unittest.SkipTest(f"{name}未设置；该验收未执行")
    return Path(value).resolve()


def nested_keys(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            here = f"{prefix}/{key}"
            yield key, here
            yield from nested_keys(item, here)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from nested_keys(item, f"{prefix}/{i}")


class RegressionPreset(unittest.TestCase):
    def test_both_intents_both_gates_byte_equal(self):
        # 环境值是manifest导出的4行JSON：intent,phase,baseline,repeat。
        gates = read(pathenv("V8_17_REGRESSION_MANIFEST"))
        # 独立预期：U D.2，两种意图在部分2/4各一道，不漏一次。
        self.assertEqual({(g["intent"], g["phase"]) for g in gates},
                         {("monitoring", 2), ("transit", 2),
                          ("monitoring", 4), ("transit", 4)})
        self.assertEqual(len(gates), 4)
        for gate in gates:
            repeat, baseline = Path(gate["repeat"]), Path(gate["baseline"])
            rows = read(repeat / "records.json")
            # 独立来源：S V8-16已登记quick_selection的20键。
            self.assertEqual(sorted(r["contract_id"] for r in rows), sorted(QUICK))
            for cid in QUICK:
                left, right = baseline / "contracts" / cid, repeat / "contracts" / cid
                # 不允许两边都不存在而得到空集合相等的假通过。
                self.assertTrue((left / "contract.json").is_file())
                self.assertTrue((right / "contract.json").is_file())
                cmp = compare_dirs(left, right)
                # 独立不变量：U F.1，全部文件，排除清单为空。
                self.assertTrue(cmp["file_sets_equal"], (gate, cid, cmp))
                self.assertTrue(cmp["bytes_equal"], (gate, cid, cmp))


class ArtifactsPreset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = pathenv("V8_17_OUT")
        cls.data = pathenv("V8_17_DATA_ROOT")
        cls.cache = pathenv("V8_17_TEST_CACHE")
        cls.entries = {e["family_id"]: e for e in read(pathenv("V8_17_DEVSET"))}
        cls.rows = read(cls.out / "records.json")
        cls.summary = read(cls.out / "summary.json")

    def test_keys_common_conditions_and_no_timers(self):
        stage = self.summary["stage"]
        # 独立预期：U D.1固定20或200，完成数不等于成功数。
        self.assertIn(stage, ("quick", "full"))
        expected_count = {"quick": 20, "full": 200}[stage]
        self.assertEqual(len(self.rows), expected_count)
        self.assertEqual(len({r["contract_id"] for r in self.rows}), expected_count)
        if stage == "quick":
            self.assertEqual(sorted(r["contract_id"] for r in self.rows), sorted(QUICK))
        else:
            # 独立全集：登记40族×draw0..4，不接受漏项后缩分母。
            self.assertEqual({(r["family_id"], r["draw_index"]) for r in self.rows},
                             {(fid, d) for fid in self.entries for d in range(5)})
            div = read(self.out / "diversity" / "records.json")
            self.assertEqual(len(div), 100)
            self.assertEqual(len({r["contract_id"] for r in div}), 100)
            known = [r for r in self.rows if r["contract_id"] == "o34_d3"]
            # 独立证据：本指令3.7解析必要条件，输入身份由load_context校验。
            self.assertEqual(len(known), 1)
            self.assertFalse(known[0]["success"])
            self.assertEqual(known[0]["failure"]["code"], "proven_infeasible")
        mon = pathenv("V8_17_MONITOR_BASELINE")
        transit = pathenv("V8_17_TRANSIT_BASELINE")
        for row in self.rows:
            cid = row["contract_id"]
            folder = self.out / "contracts" / cid
            c = read(folder / "contract.json")
            # 独立预期：只改intent，三意图公共抽签同键同字段。
            self.assertEqual(c["intent"], "intrusion")
            for base in (mon, transit):
                old = read(base / "contracts" / cid / "contract.json")
                for key in ("family_id", "draw_index", "group_id", "member_ids",
                            "group_size", "target_id", "initial_speed_m_s", "formation_prior"):
                    self.assertEqual(c[key], old[key], (cid, key))
            for file in sorted(folder.rglob("*.json")):
                for key, location in nested_keys(read(file)):
                    # R16 P0教训：包括嵌套LP/见证，不能只剔除顶层timing。
                    self.assertNotIn(key, TIMER_KEYS, (file, location))
            # U唯一预算20；证书可0次，普通保留至少1次。
            self.assertGreaterEqual(row["attempts"], 0)
            self.assertLessEqual(row["attempts"], 20)
            if row["success"]:
                self.assertGreaterEqual(row["attempts"], 1)

    def test_disk_tracks_frozen_verification_and_events(self):
        successes = [r for r in self.rows if r["success"]]
        if not successes:
            self.skipTest("没有保留轨迹；保存后核验尚未完成")
        for row in successes:
            with self.subTest(cid=row["contract_id"]):
                ctx = load_context(self.entries[row["family_id"]],
                                   data_root=self.data, cache_dir=self.cache)
                folder = self.out / "contracts" / row["contract_id"]
                saved = read(folder / "result.json")
                target = ctx.facility_by_id[row["target_id"]]
                tracks = {}
                for mid in row["member_ids"]:
                    td = folder / "tracks" / mid
                    a = {k: np.load(td / f"{k}.npy", allow_pickle=False)
                         for k in ("tau_us", "p", "v", "a", "segment_index")}
                    # 独立预期：r5统一10Hz整数微秒，单段编号0，物理数组有限。
                    self.assertTrue(np.issubdtype(a["tau_us"].dtype, np.integer))
                    np.testing.assert_array_equal(np.diff(a["tau_us"]),
                                                  np.full(len(a["tau_us"]) - 1, 100_000))
                    np.testing.assert_array_equal(a["segment_index"],
                                                  np.zeros(len(a["tau_us"]), dtype=int))
                    for key in ("p", "v", "a"):
                        self.assertTrue(np.isfinite(a[key]).all(), key)
                    tr = MemberTrack(mid, a["tau_us"], a["p"], a["v"], a["a"],
                                     a["segment_index"], ())
                    tracks[mid] = tr
                    mask = (tr.tau_us >= saved["release_us"][mid]) & (tr.segment_index == 0)
                    self.assertTrue(mask.any())  # 定义：必须有释放后段窗口。
                    times, xy = tr.tau_us[mask], tr.p[mask, :2]
                    sdf = np.asarray(signed_distance(target.geometry, xy), float)
                    info = saved["intrusion"]["members"][mid]
                    for layer in ("warning", "alert", "protected"):
                        # 独立定义：几何层内为sdf<=offset；False→True计入，不调用待测screen。
                        inside = sdf <= target.offsets[layer]
                        starts = np.flatnonzero(inside & ~np.r_[False, inside[:-1]])
                        # U D.4/F.1固定预期：每层恰一次；事件时刻必须是磁盘实测首帧。
                        self.assertEqual(len(starts), 1, (mid, layer))
                        self.assertEqual(info["entry_counts"][layer], 1)
                        self.assertEqual(info["first_entry_us"][layer], int(times[starts[0]]))
                    # 冻结near_facility_contour是signed最小值≤50，不是abs，也不设下界。
                    self.assertLessEqual(float(sdf.min()), 50.0)
                    self.assertEqual(info["end_contour_m"], float(sdf[-1]))
                    self.assertEqual(info["min_contour_m"], float(sdf.min()))
                verdicts = verify_segments(ctx.scene, tracks, saved["release_us"],
                                           [SegmentTask(0, "intrusion", row["target_id"])])
                valid = check_validity(ctx.scene,
                                       [visible_track(tracks[m], saved["release_us"][m])
                                        for m in sorted(tracks)])
                # 独立权威：冻结V8-11核验和实测物理门禁，不以新实现自证。
                self.assertTrue(all(v.passed for v in verdicts))
                self.assertTrue(valid.passed)
                self.assertTrue(saved["success"])
                self.assertTrue(saved["retained_p0_ok"])
                if valid.min_separation_m is not None:
                    self.assertGreaterEqual(valid.min_separation_m, 2.0)

    def test_five_serial_repeats(self):
        repeat = pathenv("V8_17_RERUN")
        keys = read(self.out / "rerun_keys.json")["keys"]
        # S选择协议：全量开始前字典序前5键，不根据成功结果挑选。
        self.assertEqual(keys, [[1, d] for d in range(5)])
        ids = [f"o01_d{d}" for d in range(5)]
        self.assertEqual(sorted(r["contract_id"] for r in read(repeat / "records.json")), ids)
        for cid in ids:
            left, right = self.out / "contracts" / cid, repeat / "contracts" / cid
            self.assertTrue((left / "contract.json").is_file())
            self.assertTrue((right / "contract.json").is_file())
            cmp = compare_dirs(left, right)
            # U F.1：相同环境、相同输入、全部合同文件逐字节一致。
            self.assertTrue(cmp["file_sets_equal"], cid)
            self.assertTrue(cmp["bytes_equal"], (cid, cmp))


if __name__ == "__main__":
    unittest.main()
