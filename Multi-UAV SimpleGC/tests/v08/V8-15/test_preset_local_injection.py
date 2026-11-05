"""V8-15 预置；未经运行。仅规划/优化/仿真供给和非门禁遥测用替身。
预算、阶段控制、拼接、冻结段核验/有效性、摘要、保存均用实际生产函数。
独立夹具：V8-11圆场景；425m半径绕1.5圈后撤出；两机全程相差10m。
"""
import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np

PROJECT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "tests" / "v08" / "V8-11"))
import synth_v8_11 as syn
from v08.contract.monitoring import (GroupSpec, SpeedProfilePrior, TaskSpec, MemberPlan, SegmentPlan)
from v08.criteria.segment import SegmentTask, verify_segments
from v08.criteria.validity import check_validity, visible_track
from v08.motion.optimize import SplineTrajectory
from v08.runner import joint_monitoring as JM
from v08.sim.stitch import stitch
from v08.sim.types import MemberSegmentResult


class InjectionPreset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t, p, v = syn.sample_path((-1000., 0.),
                                 [("line", (-425., 0.)), ("arc", (0., 0.), -540.),
                                  ("line", (1000., 0.))], 8.)
        cls.t, cls.pa, cls.va = t, p, v
        cls.pb = p + np.array([0., 10., 0.])
        cls.scene = syn.scene()
        cls.group = GroupSpec("g0", ("a", "b"), SpeedProfilePrior(8., 0.), "abreast")
        cls.task = TaskSpec("task0", "monitoring", "fac_a")
        initial = {m: {"position_enu_m": list(q[0])}
                   for m, q in (("a", cls.pa), ("b", cls.pb))}
        cls.family = NS(family_id="fixture-v15-injection", vehicle_count=2,
                        lateral_spacing_m=10., initial_states=initial)
        cls.ctx = NS(family=cls.family, scene=cls.scene)
        end = float(t[-1]) / 1e6
        members = {}
        for m, q in (("a", cls.pa), ("b", cls.pb)):
            length = float(np.linalg.norm(np.diff(q[:, :2], axis=0), axis=1).sum())
            members[m] = MemberPlan(m, 0, tuple(map(tuple, q[:, :2])), syn.ALT,
                                    length, 0., ((0., 8.),))
        cls.plan = SegmentPlan(
            members, tuple(map(tuple, p[:, :2])), end, {}, (),
            proposal={"topology": "loop"},
            formation={"prior": "abreast", "start": "abreast", "realized": "abreast",
                       "mapped_from_loose": False, "lateral_step_m": 10.},
            topology={"final": "loop"}, witnesses={"target_id": "fac_a"})
        # 仅供优化器替身的接口对象，绝不当作实际优化成功的数值证据。
        refs = {m: SplineTrajectory(m, 0., end, syn.ALT, end * np.arange(-3, 5, dtype=float),
                                    np.zeros((4, 2))) for m in ("a", "b")}
        cls.opt = {"ok": True, "stage": "optimized", "reason": None,
                   "solution": NS(references=refs, diagnostics={"nit": 0, "nfev": 0}),
                   "monitoring": {"passed": True, "failures": []}, "lines": (), "lines_raw": ()}

    def results(self, kind=None):
        qa, qb = self.pa.copy(), self.pb.copy()
        if kind == "separation":
            qb[-1] = qa[-1] + np.array([1., 0., 0.])
        elif kind == "other_alert":
            # fac_b中心(1600,0)，到中心200m：120<200<230，恰在警戒层而非保护层。
            qb[-2] = (1800., 0., syn.ALT)
        elif kind == "restricted":
            qb[-2] = (0., -1500., syn.ALT)  # 限制区圆心，半径100m。
        return [MemberSegmentResult(
                    m, 0, True, "ok", self.t.copy(), q, self.va.copy(), np.zeros_like(q),
                    None, None, (NS(release_us=0),))
                for m, q in (("a", qa), ("b", qb))]

    def exercise(self, kind, expected_stage, expected_reason, low_code):
        clean = stitch(self.results())
        verdict = verify_segments(self.scene, clean, {"a": 0, "b": 0},
                                  [SegmentTask(0, "monitoring", "fac_a")])
        self.assertTrue(all(x.passed for x in verdict),
                        "独立夹具：警戒外425m圆绕1.5圈，再撤出所有预警层")
        valid = check_validity(self.scene, [visible_track(clean[m], 0) for m in sorted(clean)])
        self.assertTrue(valid.passed, "独立夹具：两机同一时刻相差10m且未入限制区")
        self.assertAlmostEqual(valid.min_separation_m, 10., places=10,
                               msg="手算两条轨迹恒相差向量(0,10,0)")

        seen = []
        def planning(ctx, group, task, states, occupied, key):
            seen.append(key.attempt)
            return self.plan
        supplied = iter([self.results(kind), self.results()])
        def simulation(refs, states, *, final):
            self.assertTrue(final, "③监视单段是最终段，不能改变保持/拼接口径")
            return next(supplied)

        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            stack.enter_context(patch("v08.sampler.common.sample_common", return_value=NS()))
            stack.enter_context(patch("v08.contract.monitoring.monitoring_mission",
                                      return_value=NS(groups=(self.group,), tasks=(self.task,))))
            stack.enter_context(patch("v08.motion.plan.plan_attempt", side_effect=planning))
            stack.enter_context(patch("v08.motion.optimize.optimize_segment", return_value=self.opt))
            stack.enter_context(patch("v08.sim.tracking_batch.run_tracking_group", side_effect=simulation))
            # 这些不是保留门禁；避免把合成优化器对象误当成真实性能遥测。
            for name in ("member_deviation", "tracking_stats", "phase_diagnostics"):
                stack.enter_context(patch.object(JM, name, return_value={}))
            vv = stack.enter_context(patch("v08.criteria.validity.check_validity", wraps=check_validity))
            sv = stack.enter_context(patch("v08.criteria.segment.verify_segments", wraps=verify_segments))
            keep = {}
            rec = JM.run_contract(self.ctx, {"order": 1, "facility_count": 2}, 0,
                                  settings={"_sha256": "synthetic-test-only"},
                                  out_dir=Path(tmp), keep=keep)
            self.assertEqual(seen, [0, 1], "唯一预算只进入两次；失败后仅attempt递增")
            self.assertEqual(vv.call_count, 2, "固定attempt_chain：即使段核验失败，validity仍执行")
            self.assertEqual(sv.call_count, 2, "两次实际冻结段核验，不得用替身让它总通过")
            self.assertTrue(rec["success"], "第二次干净结果实际核验通过")
            self.assertEqual(rec["attempts"], 2, "首次失败+第二次成功，报告次数从1计")
            self.assertEqual(rec["post_optimization_failures"], 1,
                             "实际进入优化后的注入失败恰一次")
            self.assertEqual(rec["skeleton_failures"], 0, "没有骨架失败")
            self.assertEqual(rec["unknown_attempts"], 0, "两个attempt的入口标记都已知")
            first = rec["attempt_log"][0]
            self.assertFalse(first["ok"], "P0-2：被注入的尝试必须拒绝")
            self.assertEqual(first["stage"], expected_stage, "固定attempt_chain的失败优先级")
            self.assertEqual(first["reason"], expected_reason, "固定attempt_chain顶层reason")
            self.assertEqual(first["code"], "candidate_rejected", "顶层包装码不冒充底层有效性码")
            if kind == "other_alert":
                failures = [tuple(x) for segment in first["segment_failures"] for x in segment]
                self.assertIn(("b", "other_facilities_within_limit", low_code), failures,
                              "V8-11冻结段核验：非目标警戒层对应constraint_violation")
            else:
                self.assertIn(low_code, first["validity"]["codes"],
                              "V8-11冻结有效性核验：分别检查采样间距/限制区")

            self.assertTrue(keep["result"]["ok"], "最终保留对象来自核验通过的attempt")
            disk = Path(tmp) / "contracts" / "o01_d0"
            result_doc = json.loads((disk / "result.json").read_text(encoding="utf-8"))
            self.assertEqual([x["ok"] for x in result_doc["attempt_log"]], [False, True],
                             "落盘保留失败历史但只接纳第二次结果")
            for m, expected in (("a", self.pa), ("b", self.pb)):
                saved = np.load(disk / "tracks" / m / "p.npy", allow_pickle=False)
                self.assertTrue(np.array_equal(saved, expected),
                                "P0-2：最终载荷逐值等于独立干净轨迹，绝不混入注入帧")
                self.assertTrue(np.array_equal(keep["result"]["tracks"][m].p, expected),
                                "内存保留与磁盘保留都来自第二次干净结果")

    def test_separation_rejected_then_retry_saved(self):
        self.exercise("separation", "validity", "validity", "separation_violation")

    def test_other_alert_rejected_then_retry_saved(self):
        self.exercise("other_alert", "verify_segments", "segment_verification", "constraint_violation")

    def test_restricted_rejected_then_retry_saved(self):
        self.exercise("restricted", "validity", "validity", "constraint_violation")


if __name__ == "__main__":
    unittest.main()
