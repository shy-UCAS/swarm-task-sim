"""V8-15 预置；未经运行。对新压力装配器核对未授权字段不变、全员组及随机键隔离。
不加载真实开发场景，不跑骨架/优化；完整项目导入依赖与纯数值测试分离。
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

PROJECT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "tools" / "v08"))

from v08.contract.monitoring import Family, monitoring_mission, validate_mission
from v08.sampler.common import sample_common
from v08.sampler.keys import RngKey, key_words
from run_separation_v15 import make_stress_case


class StressCasePreset(unittest.TestCase):
    def test_all_members_original_fields_and_disjoint_keys(self):
        ids = tuple(f"u{i:02d}" for i in range(12))
        initial = {m: {"position_enu_m": [float(i), 0., 120.]}
                   for i, m in enumerate(ids)}
        family = Family("fixture-v15-stress", initial, 12, 120., 20.)
        ctx = NS(family=family, facilities=[NS(id="fac_a"), NS(id="fac_b")], inputs={})
        original = sample_common(family, 0)
        source = monitoring_mission(ctx, original)
        original_words = tuple(key_words(RngKey(family.family_id, 0, "shape", mission=0,
                                                branch=2, group=source.groups[0].group_id, segment=0)))
        cases = []
        for prior in ("abreast", "column", "echelon"):
            case = make_stress_case(ctx, {"order": 7}, prior=prior, seed=2)
            mission, key = case["mission"], case["key"]
            self.assertTrue(validate_mission(mission, ctx),
                            "现有合同验证器接受单组、单段、无组内差异")
            self.assertEqual(len(mission.groups), 1, "U D.5只有一个压力编组")
            self.assertEqual(len(mission.common.groups), 1, "压力CommonDraw副本也只含全员组")
            self.assertEqual(mission.groups[0].member_ids, ids,
                             "U D.5：压力组恰含族全部12架，不丢难成员")
            self.assertEqual(mission.groups[0].speed_profile, source.groups[0].speed_profile,
                             "初速/变速频率来自生产draw0第0组，未经覆盖")
            self.assertEqual(mission.tasks, source.tasks, "目标/意图/最终段标志均沿用原生产任务")
            self.assertEqual(mission.groups[0].formation_prior, prior, "只覆盖指定的队形倾向")
            self.assertEqual(key.draw, 0, "本稿6.1沿用生产diversity：common draw固定0")
            self.assertEqual(key.branch, 2, "压力种子使用branch，非成员差异")
            self.assertEqual(key.group, "stress_v15/" + source.groups[0].group_id + "/" + prior,
                             "压力键隔离在合法group字段，不新增purpose")
            self.assertNotEqual(tuple(key_words(key)), original_words,
                                "完整键字段不同，实际SHA派生词不得等于生产键")
            self.assertEqual(case["contract_id"], "stress_o07_" + prior + "_s2",
                             "压力产物不与生产o07_d0重名")
            cases.append(tuple(key_words(key)))
        self.assertEqual(len(set(cases)), 3, "三个倾向的压力命名空间彼此隔离")
        self.assertEqual(sample_common(family, 0), original,
                         "压力装配前后生产公共抽签保持dataclass逐字段相同")


if __name__ == "__main__":
    unittest.main()
