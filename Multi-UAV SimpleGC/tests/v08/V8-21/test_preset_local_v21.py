import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from v08.config import load_config
from v08.contract.monitoring import TaskSpec
from v08.criteria.segment import SegmentTask, verify_segments
from v08.motion.detour_config import load_detour_candidate
from v08.motion.detour_geometry import detour_constraints, arc_band_violations
from v08.motion.detour_numeric import sweep_series
from v08.motion.detour_checks import verify_detour_candidate
from v08.motion.layer_limits import layer_limits, constraints_for_task
from v08.motion.transit_chords import line_sublevel
from v08.runner import joint_monitoring as JM

ATOL = 1e-9  # 解析表示对照，绝不作为几何包含容差。


class LocalV21(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.C = load_detour_candidate().values
        cls.D = cls.C["near_band_width_m"]

    def ctx(self):
        circle = lambda r: {"type":"Circle","center_m":[0,0],"radius_m":r}
        fac = NS(id="F",geometry=circle(100),center=(0,0),
                 layers={"warning":circle(1000),"alert":circle(600),"protected":circle(300)})
        return NS(world={"type":"Polygon","vertices_m":[[-5000,-5000],[5000,-5000],[5000,5000],[-5000,5000]]},
                  params={"world_margin_m":35.0,"obstacle_margin_m":35.0,"forbidden_margin_m":10.0,
                          "pre_entry_warning_clearance_m":10.0,"alignment_length_m":100.0},
                  obstacles=[],facilities=[fac],facility_by_id={"F":fac},
                  scene={"entities":[{"id":"F","type":"facility","geometry":circle(100)},
                         {"id":"W","type":"protection_zone","facility_id":"F","layer":"warning","geometry":circle(1000)}]})

    def track(self, distances, release=0):
        # 固定径向位置，专测mask/事件；此夹具不声称满足动力学或扫角。
        d = np.asarray(distances,float)
        p = np.c_[1000+d,np.zeros(len(d)),np.zeros(len(d))]
        return NS(member_id="u",tau_us=np.arange(len(d),dtype=np.int64)*100000,
                  segment_index=np.zeros(len(d),dtype=np.int64),p=p,v=np.zeros_like(p),a=np.zeros_like(p))

    def test_frozen_detour_stays_unsupported(self):
        with self.assertRaises(ValueError):
            layer_limits("detour","F",["F"])
        with self.assertRaises(ValueError):
            constraints_for_task(self.ctx(),TaskSpec("task0","detour","F"))
        # 冻结入口在处理tracks前按intent拒绝；不去改KINDS。
        with patch("v08.criteria.segment.scene_geometry",return_value=None):
            with self.assertRaisesRegex(ValueError,"暂不支持"):
                verify_segments(self.ctx().scene,{}, {},[SegmentTask(0,"detour","F")])

    def test_constraints_prefix_and_no_mutation(self):
        ctx = self.ctx()
        before = copy.deepcopy(ctx.facilities[0].layers)
        out = detour_constraints(ctx,TaskSpec("task0","detour","F"))
        self.assertEqual([c.name for c in out["base"]],["world","warning:F"])
        self.assertEqual(list(out["warnings"]),["F"])
        self.assertEqual(list(out["crossing_boundaries"]),["F","__crossing__F::near"])
        self.assertIs(out["crossing_boundaries"]["F"],ctx.facilities[0].layers["warning"])
        self.assertEqual(out["near_geometry"]["radius_m"],1000+self.D)
        self.assertEqual(ctx.facilities[0].layers,before)

    def test_exact_line_near_intersection_and_tangent_sweep(self):
        R, h, D = 1000.0, 10.0, self.D
        self.assertGreater(D,h)  # fixture需放得下10m偏置；候选覆盖要求由下发前确认。
        near = {"type":"Circle","center_m":[0,0],"radius_m":R+D}
        lo,hi = line_sublevel(near,(0,R+h),(1,0),0)
        L = math.sqrt((R+D)**2-(R+h)**2)
        self.assertAlmostEqual(lo,-L,delta=ATOL)
        self.assertAlmostEqual(hi,L,delta=ATOL)
        # 用解析端点，避免0.5m栅格截断误差。sd端点的解析值恰为D。
        x = np.linspace(-L,L,1001)
        sd = np.hypot(x,R+h)-R
        sd[0]=sd[-1]=D
        phi = np.arctan2(np.full_like(x,R+h),x)
        s = sweep_series(np.arange(len(x),dtype=np.int64)*100000,sd,phi,D)
        expected = math.degrees(2*math.acos((R+h)/(R+D)))
        self.assertAlmostEqual(s["max_span_deg"],expected,delta=ATOL)

    def test_arc_at_near_edge_rejected(self):
        near = {"type":"Circle","center_m":[0,0],"radius_m":1000+self.D}
        b = self.ctx().params["pre_entry_warning_clearance_m"]
        arc = ("arc",(0,0),near["radius_m"]-b/2,0,math.pi/2)
        # 全弧距边界b/2，必在带内；与实现采样数无关。
        self.assertEqual(arc_band_violations([arc],near,b),[0])
        safe = ("arc",(0,0),near["radius_m"]-2*b,0,math.pi/2)
        self.assertEqual(arc_band_violations([safe],near,b),[])

    def test_measured_two_visits_and_release_filter(self):
        tr = self.track([self.D+1,self.D/2,self.D+1,self.D/2,self.D+1])
        m = JM.detour_entry_counts(self.ctx(),{"u":tr},{"u":0},"F")
        self.assertEqual(m["members"]["u"]["near_entry_count"],2)
        self.assertFalse(m["all_single"])
        m = JM.detour_entry_counts(self.ctx(),{"u":tr},{"u":200000},"F")
        self.assertEqual(m["members"]["u"]["near_entry_count"],1)
        self.assertEqual(m["members"]["u"]["first_near_entry_us"],300000)
        with self.assertRaises(ValueError):
            JM.detour_entry_counts(self.ctx(),{}, {},"F")

    def test_target_warning_penetration_rejected(self):
        # 独立解析层值：半径999点在warning内、alert外，恰为layer 1。
        # 只断言该候选条件被明确拒绝，不要求短时跳点夹具满足动力学或其他条件。
        ctx=self.ctx()
        scene=copy.deepcopy(ctx.scene)
        scene["entities"].append({"id":"world","type":"world","geometry":ctx.world})
        for name in ("alert","protected"):
            scene["entities"].append({"id":"F_"+name,"type":"protection_zone",
                                      "facility_id":"F","layer":name,
                                      "geometry":ctx.facility_by_id["F"].layers[name]})
        tr=self.track([self.D+1,self.D/2,-1,self.D/2,self.D+1])
        q=verify_detour_candidate(scene,{"u":tr},{"u":0},"F")
        self.assertFalse(q["passed"])
        self.assertFalse(q["member_conditions"]["u"]["target_layer_zero"])
        self.assertEqual(q["member_facts"]["u"]["max_target_layer"],1)

    def test_attempt_chain_keeps_measured_stage(self):
        # 隔离上游，仅检真实attempt_chain的路由；不声称此轨迹满足动力学。
        tr = self.track([self.D+1,self.D/2,self.D+1,self.D/2,self.D+1])
        plan = NS(failure=None)
        sol = NS(diagnostics={},references={"u":object()})
        opt = {"ok":True,"solution":sol}
        result = NS(status="ok",pieces=[NS(release_us=0)])
        with patch("v08.motion.plan.plan_attempt",return_value=plan), \
             patch("v08.motion.optimize.optimize_segment",return_value=opt), \
             patch.object(JM,"_member_reference",return_value=object()), \
             patch("v08.sim.tracking_batch.run_tracking_group",return_value=[result]), \
             patch("v08.sim.stitch.stitch",return_value={"u":tr}), \
             patch("v08.criteria.validity.visible_track",return_value=object()), \
             patch("v08.criteria.validity.check_validity",return_value=NS(passed=True)), \
             patch("v08.motion.detour_checks.verify_detour_candidate",return_value={"passed":True}):
            out = JM.attempt_chain(self.ctx(),NS(member_ids=("u",)),
                                   TaskSpec("task0","detour","F"),{"u":NS()},NS(),{})
        self.assertFalse(out["ok"])
        self.assertEqual(out["code"],"candidate_rejected")
        self.assertEqual(out["stage"],"measured_detour_entries")

    def test_column_terminal_spacing(self):
        # 原成员派生接口独立性质：相同l偏移用于起点与终点，不能在出口丢掉。
        from v08.motion.formation import formation_slots, derive_members, make_reference
        from v08.motion.path import sample_primitives
        group=NS(member_ids=("a","b"),formation_prior="column")
        slots=formation_slots(group,NS(lateral_spacing_m=24.0),None,formation="column",order=("a","b"))
        sampled=sample_primitives([("line",(0,0),(200,0))],0.5)
        ref=make_reference(sampled,{},())
        lanes=derive_members(ref,slots,(40,160),spacing_m=0.5)
        self.assertAlmostEqual(np.linalg.norm(lanes["a"].xy[-1]-lanes["b"].xy[-1]),24.0,delta=ATOL)


if __name__ == "__main__":
    unittest.main()
