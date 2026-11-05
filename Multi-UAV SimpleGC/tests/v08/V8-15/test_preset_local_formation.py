"""V8-15 预置；未经运行。使用真实生产选队形、局部证书及曲率LP。
人工区间[400,400+w]，三成员居中，管区间[400+D,400+w-D]。
其余场景/最终构造是测试替身；本文件单独依赖项目几何导入和SciPy。
"""
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT))
from v08.motion import monitoring_band as MB, plan as PLAN
from v08.motion.intents import monitoring as MON
from v08.sampler.keys import RngKey


class FormationPreset(unittest.TestCase):
    def exercise(self, width):
        members = ("a", "b", "c")
        group = NS(member_ids=members, formation_prior="abreast")
        fam = NS(lateral_spacing_m=10.)
        ctx = NS(family=fam, params={"monitoring": {"full_probability": 1.}})
        task = NS(target_id="target")
        key = RngKey("fixture-v15", 0, "shape", mission=0, group="g0", segment=0)

        class Geometry:
            q, eta, r_star = 0., 0., 500.
            components = [{"id": 0, "wrapping": True, "n_rows": 360}]
            def tubes(self, comp, D):
                lo = np.full(360, 400.)
                hi = np.full(360, 400. + width)
                return lo, hi, lo + D, hi - D, D

        class Setup:
            def __init__(self, *args):
                self.timing = {}
                self.criteria = {"min_azimuth_coverage_deg": 120.}
            def rng(self, purpose):
                return np.random.default_rng(0)
            def band_geometry(self, center):
                return Geometry()
            def kappa_star(self):
                return .38
            def r_turn_m(self):
                return 15.75

        def build(S, ctx, group, task, states, key, slots, ring,
                  used, spacing, steps, *rest):
            return NS(realized=slots.realized, step=used,
                      steps=[(r["formation"], r["lateral_step_m"], r["found"]) for r in steps])

        # 常数管区间空时，任意非空弧同样为空；因此替代折返查询为空有独立依据。
        # 可行候选先走loop并立即返回，实际band_certificate/shape_lp没有被替换。
        with patch.object(MON, "_Setup", Setup), \
             patch.object(MON, "_center_candidates", return_value=[np.zeros(2)]), \
             patch.object(MON, "_build_with_ring", side_effect=build) as built, \
             patch.object(MB, "retrace_query", return_value=[]), \
             patch.object(MB, "shape_lp", wraps=MB.shape_lp) as lp:
            got = MON.propose_and_build(ctx, group, task, {}, key)
            return got, built.call_count, lp.call_count, (ctx, group, task)

    def test_abreast_is_first_feasible(self):
        got, nbuild, nlp, _ = self.exercise(30.)
        self.assertEqual(got.realized, "abreast", "手算2D=20<=30，首项横排可行")
        self.assertEqual(nbuild, 1, "选到后只构造一次；生产width_then_build合同")
        self.assertGreater(nlp, 0, "U D.1要求真实曲率可行性LP参与，不只布尔宽度替身")

    def test_echelon_uses_certified_bisection_lower_end(self):
        got, nbuild, nlp, _ = self.exercise(10.)
        self.assertEqual(got.realized, "echelon", "横排20>10；梯形步长<=5可行")
        self.assertEqual(got.step, 4.75,
                         "手算二分10失败,3通过,6.5失败,4.75通过,5.625失败；宽0.875<=1")
        steps = [(s, ok) for name, s, ok in got.steps if name == "echelon"]
        self.assertEqual(steps, [(10., False), (3., True), (6.5, False),
                                 (4.75, True), (5.625, False)],
                         "固定_echelon_payload顺序；容差2/(3-1)=1，返回认证下端")
        self.assertEqual(nbuild, 1, "不是每试一个步长就生成一遍骨架")
        self.assertGreater(nlp, 0, "通过的区间实际求解了LP")

    def test_column_only(self):
        got, nbuild, nlp, _ = self.exercise(4.)
        self.assertEqual(got.realized, "column",
                         "横排20>4，最小梯形全宽6>4，纵列D=0可行")
        self.assertEqual(nbuild, 1, "只生成最终选定纵列")
        self.assertGreater(nlp, 0, "纵列仍要通过真实LP")

    def test_all_empty_attempt_and_final_are_different_levels(self):
        got, nbuild, _, (ctx, group, task) = self.exercise(-1.)
        self.assertEqual(nbuild, 0, "手工上界399<下界400，所有队形均不能生成")
        self.assertEqual(got.failure.code, "candidate_rejected",
                         "2dbb2a4 _stage_fail：单次候选失败码")
        self.assertEqual(got.failure.feasible_set, "patrol_region",
                         "全空位于巡逻集合查询阶段")
        # 这里明确给出“没有精确证明”的查询替身，不冒充测试精确几何证书。
        with patch.object(PLAN, "empty_query", return_value=({"field_empty": False}, None)):
            final = PLAN.final_failure(ctx, group, task, [{"stage": "patrol_region"}] * 20)
        self.assertEqual(final.code, "approx_empty",
                         "固定_final_failure：全部patrol_region且无精确证书不能报proven_infeasible")


if __name__ == "__main__":
    unittest.main()
