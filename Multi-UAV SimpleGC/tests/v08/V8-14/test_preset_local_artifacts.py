import json
import os
from pathlib import Path
import unittest
import numpy as np
import shapely  # 真实场景组，导入依赖缺失即失败。

from v08.scene.context import load_context
from v08.scene.exact import polyline_clearance
from v08.motion.intents.monitoring import monitoring_constraints


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cut_by_arclength(xy, a, b):
    ds = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    s = np.r_[0., np.cumsum(ds)]
    inner = (s > a) & (s < b)
    start = [np.interp(a, s, xy[:, k]) for k in range(2)]
    end = [np.interp(b, s, xy[:, k]) for k in range(2)]
    return np.vstack([start, xy[inner], end])


class LocalArtifactsPreset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ["V8_14_RUN_OUT"]).resolve()
        cls.data = Path(os.environ["V8_14_DATA_ROOT"]).resolve()
        cls.cache = Path(os.environ["V8_14_TEST_CACHE"]).resolve()
        cls.entries = {e["family_id"]: e
                       for e in read_json(os.environ["V8_14_DEVSET"])}
        cls.records = read_json(cls.root/"records.json")
        cls.summary = read_json(cls.root/"summary.json")

    def test_completed_keys_and_event_counts(self):
        expected = {"skeleton": 200, "quick": 20, "full": 200}[self.summary["stage"]]
        self.assertEqual(len(self.records), expected,
                         "U批次规模是完成合同数，不能删失败合同")
        self.assertEqual(len({r["contract_id"] for r in self.records}), expected,
                         "业务键唯一，不用重试输出覆盖其他合同")
        for r in self.records:
            with self.subTest(contract=r["contract_id"]):
                logs = r["attempt_log"]
                self.assertEqual(len(logs), r["attempts"],
                                 "尝试数来自实际记录，不能用保留条数代替")
                self.assertLessEqual(len(logs), 20, "唯一合同预算20")
                shape = sum(bool(a["shape_audit_failed"]) for a in logs)
                self.assertEqual(shape, r["shape_audit_failed_attempts"],
                                 "每个骨架attempt至多一次shape失败，独立逐条重计")
                if self.summary["stage"] != "skeleton":
                    self.assertTrue(all(isinstance(a["optimization_entered"], bool)
                                        for a in logs),
                                    "不能按非skeleton阶段推测进入优化")
                    post = sum(not a["ok"] and a["optimization_entered"] for a in logs)
                    self.assertEqual(post, r["post_optimization_failures"],
                                     "U D.4逐attempt入口事件独立重算")

    def test_retained_skeleton_geometry_and_actual_maps(self):
        for r in self.records:
            if not r["success"]:
                continue
            with self.subTest(contract=r["contract_id"]):
                sk = read_json(self.root/"contracts"/r["contract_id"]/"skeleton.json")
                ctx = load_context(self.entries[r["family_id"]],
                                   data_root=self.data, cache_dir=self.cache)
                constraints = monitoring_constraints(ctx, r["target_id"])
                mapping = sk["witnesses"]["member_map_v14"]
                self.assertEqual(mapping["schema"], "member-map-v14",
                                 "显式映射版本，防止沿用常数槽位重建")
                self.assertEqual(set(mapping["members"]), set(sk["members"]),
                                 "必须包含每个实际成员，无遗漏")
                for mid, mp in sk["members"].items():
                    xy = np.asarray(sk["arrays"][mp["curve_xy"]["npz"]], float)
                    mm = mapping["members"][mid]
                    lengths = [len(mm[k]) for k in
                               ("reference_s", "shifted_reference_s", "member_s",
                                "lateral_m", "turn_mask")]
                    self.assertEqual(len(set(lengths)), 1,
                                     "位置/形变/站点逐行对应，不能错用另一成员的时间")
                    for key in ("reference_s", "shifted_reference_s", "member_s"):
                        self.assertTrue(np.all(np.diff(mm[key]) > 0.),
                                        "弧长对应必须严格单调："+key)
                    d = np.asarray(mm["lateral_m"], float)
                    mask = np.asarray(mm["turn_mask"], bool)
                    np.testing.assert_array_equal(d[mask], np.zeros(int(mask.sum())),
                                                  err_msg="U D.2：核心与接回期间所有成员真实横向偏移为0")
                    a, b = mm["patrol_member_s"]
                    length = float(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum())
                    self.assertTrue(0. <= a < b <= length,
                                    "巡逻站点是该成员完整曲线中的有效弧长")
                    patrol = cut_by_arclength(xy, a, b)
                    for cs, points in ((constraints["base"], xy),
                                       (constraints["patrol"], patrol)):
                        for c in cs:
                            margins = polyline_clearance(c.geometry, points,
                                                         sense=c.sense,
                                                         minimum_m=c.minimum_m)
                            self.assertGreaterEqual(float(np.min(margins)), 0.,
                                                    "独立冻结精确弦检查，原余量不加容差："+c.name)


if __name__ == "__main__":
    unittest.main()
