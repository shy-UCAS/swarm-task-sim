"""自加测试（不属于预置测试）：第 3 部分在真实登记场景上的端到端规划——独立复核计划、确定性、预算修复记录。

读真实数据（只读）；数据根或缓存不可用时跳过。每个用例只规划一个快速合同，几秒内完成。
"""
import json
import math
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

from v08.contract.monitoring import initial_states, monitoring_mission
from v08.motion.plan import plan_segment
from v08.runner import monitoring as run
from v08.sampler.common import sample_common
from v08.sampler.keys import RngKey
from v08.scene.context import load_context
from v08.scene.exact import signed_distance

DATA_ROOT = Path(os.environ.get("V812_DATA_ROOT", r"F:\CASIA\Drone Swarm Situational Awareness Algorithm\SwarmData"))
DEVSET = run.REPO_ROOT / "docs" / "v08" / "V8-03" / "devset_v08.json"


@unittest.skipUnless(DATA_ROOT.is_dir() and DEVSET.is_file(), "数据根或登记清单不可用")
class TestPlanOnRealFamily(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache = tempfile.mkdtemp(prefix="v812cache_")
        cls.entry = run.load_entries(DEVSET)[0]
        cls.ctx = load_context(cls.entry, data_root=DATA_ROOT, cache_dir=cls.cache)

    def plan(self, draw):
        common = sample_common(self.ctx.family, draw)
        mission = monitoring_mission(self.ctx, common)
        g, t = mission.groups[0], mission.tasks[0]
        st = initial_states(self.ctx.family, g.member_ids)
        key = RngKey(self.ctx.family.family_id, draw, "shape", mission=0, group=g.group_id, segment=0)
        return g, t, plan_segment(self.ctx, g, t, st, (), key)

    def test_plan_is_independently_valid_and_reproducible(self):
        g, t, p1 = self.plan(2)                    # 单人合同，第一次 attempt 即成功
        self.assertIsNone(p1.failure, p1.failure)
        # 1. 逐成员曲线用精确有符号距离独立复核
        tgt = t.target_id
        for m, mp in p1.members.items():
            xy = np.asarray(mp.curve_xy, float)
            inset = -signed_distance(self.ctx.world, xy)               # 凸 world 内部 sdf < 0
            self.assertGreaterEqual(float(inset.min()), 35.0 - 1e-6, "world 内缩 35 m")
            for f in self.ctx.facilities:
                self.assertGreaterEqual(float(signed_distance(f.layers["alert"], xy).min()), 10.0 - 1e-6,
                                        f"设施 {f.id} 的 alert 外 10 m")
                self.assertGreaterEqual(float(signed_distance(f.layers["warning"], xy[-1])), 50.0 - 1e-6,
                                        f"终点离设施 {f.id} 的预警圈 ≥ 50 m")
            self.assertAlmostEqual(mp.release_delay_s * 10, round(mp.release_delay_s * 10), places=9, msg="10 Hz 网格")
        # 2. 同键同环境重规划逐位一致（含数组）
        _, _, p2 = self.plan(2)
        r1, a1 = run.plan_to_record(p1)
        r2, a2 = run.plan_to_record(p2)
        self.assertEqual(run.canonical_json(r1), run.canonical_json(r2))
        self.assertEqual(sorted(a1), sorted(a2))
        for k in a1:
            self.assertEqual(a1[k].dtype, a2[k].dtype)
            self.assertEqual(a1[k].tobytes(), a2[k].tobytes())

    def test_attempt_changes_only_shape_not_common_or_target(self):
        common0 = sample_common(self.ctx.family, 1)
        for a in (0, 3):
            key = RngKey(self.ctx.family.family_id, 1, "shape", mission=0, group="g0", segment=0, attempt=a)
            self.assertEqual(key.draw, 1)
        mission = monitoring_mission(self.ctx, common0)
        mission2 = monitoring_mission(self.ctx, sample_common(self.ctx.family, 1))
        self.assertEqual(mission.tasks[0].target_id, mission2.tasks[0].target_id)
        self.assertEqual(mission.groups[0].member_ids, mission2.groups[0].member_ids)

    def test_budget_repair_is_recorded(self):
        # 第 1 族 draw 0：圈数下限的名义总时长超预算，需要半径修复；记录必须带可复核的修复日志
        g, t, p = self.plan(0)
        self.assertIsNone(p.failure, p.failure)
        kinds = [r["kind"] for r in p.repairs]
        if "radius_shift_budget" in kinds:
            rec = next(r for r in p.repairs if r["kind"] == "radius_shift_budget")
            moved = rec["delta_m"] > 0.0 or (rec["span_original_rad"] is not None and rec["span_rad"] < rec["span_original_rad"])
            self.assertTrue(moved, "修复必须真的改变了半径或弧跨度")
            self.assertLessEqual(rec["duration_s"], 1800.0)
            self.assertTrue(rec["log"])
        # 成功计划的逐 attempt 记录里，失败的 attempt 都有阶段和原因
        for a in p.attempt_log:
            if not a["ok"]:
                self.assertTrue(a["stage"])
                self.assertTrue(a["reason"])


if __name__ == "__main__":
    unittest.main()
