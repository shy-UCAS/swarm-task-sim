"""V8-19 预置测试，未经运行；不依赖 shapely，独立解析预期。"""
import unittest
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np

from v08.contract.monitoring import MemberPlan
from v08.motion.nominal import Nominal
from v08.motion.skeleton import references_from_skeleton
from v08.motion.dwell_nominal import (compose_dwell, normalized_end,
    split_member_plan, member_nominal_with_dwell, dwell_lines_from_skeleton)
from v08.motion.close_observation_numeric import (dwell_grid,
    admissible_dwell_mask, draw_dwell)
from v08.motion.nominal_checks import screen_close_observation_member
from v08.runner.joint_report import attempt_counters, quick_checkpoint
from v08.runner.skeleton_monitoring import skeleton_checkpoint


def circle(r, x=0.0):
    return {"type": "Circle", "center_m": [x, 0.0], "radius_m": float(r)}


def leg(x0, r=20.0):
    # 手算：两条2m弦，速度0,2,0，匀加/减速各2s，总4s。
    curve = NS(xy=np.array([[x0, 0.], [x0+2., 0.], [x0+4., 0.]]),
               s=np.array([0., 2., 4.]), chord=np.array([2., 2.]),
               tangent=np.array([[1., 0.], [1., 0.]]), kappa=np.zeros(3), length=4.)
    return Nominal(curve, np.array([0., 2., 0.]), np.array([0., 2., 4.]),
                   4., r, 2., 100.)


class NumericPreset(unittest.TestCase):
    def test_composite_pv_and_arrival_map(self):
        d = compose_dwell(leg(0), leg(4, 999.9), 20.)
        times = np.array([19.,20.,21.,22.,23.,24.,25.,43.,44.,45.,46.,47.,48.,49.])
        px = [0.,0.,.5,2.,3.5,4.,4.,4.,4.,4.5,6.,7.5,8.,8.]
        vx = [0.,0.,1.,2.,1.,0.,0.,0.,0.,1.,2.,1.,0.,0.]
        p,v,a = d.pva(times)
        # 独立预期：x=.5*t^2及对称减速；平台[24,44]；IEEE误差32eps。
        tol = 32*np.finfo(float).eps*8
        np.testing.assert_allclose(p, np.c_[px,np.zeros(len(px))], rtol=0, atol=tol)
        np.testing.assert_allclose(v, np.c_[vx,np.zeros(len(vx))], rtol=0, atol=tol)
        np.testing.assert_array_equal(a[(times>24)&(times<44)], np.zeros((2,2)))
        self.assertEqual((d.release_s,d.arrival_s,d.departure_s,d.end_s), (20.,24.,44.,48.))
        self.assertEqual(d.end_s-d.release_s, 28.)  # 4+20+4，不加两次hold或999.9。
        self.assertEqual(float(np.interp(4.,d.curve.s,d.t_nodes))+d.release_s,24.)
        self.assertEqual(d.time_at_s(5.),45.)  # 离开第一弦插值，不能把20s摊进该弦。
        self.assertEqual(d.time_at_s(4.),24.)  # 双值站点明确取到达。
        self.assertEqual(sum(np.asarray(d.curve.s)==4.),1)
        for t,x in ((24.,4.),(44.,4.)):
            pp,vv,_ = d.pva(t)
            np.testing.assert_array_equal(pp,[x,0.])
            np.testing.assert_array_equal(vv,[0.,0.])

    def test_float_endpoint_normalization(self):
        # 独立IEEE反例：左结合96.7解码成96.69999999999999；括号总长76.6保持一致。
        e,T = normalized_end(20.1,4.1,20.1,52.4)
        self.assertEqual(e,96.69999999999999)
        self.assertEqual(T,76.6)
        self.assertEqual(e,20.1+(e-20.1))
        naive = ((20.1+4.1)+20.1)+52.4
        self.assertNotEqual(naive,20.1+(naive-20.1))

    def test_split_speed_and_release(self):
        mp = MemberPlan("m",0,((0.,0.),(2.,0.),(4.,0.),(6.,0.),(8.,0.)),
                        100.,8.,.14,((0.,3.),(4.,5.),(6.,7.)),())
        left,right = split_member_plan(mp,4.)
        # 右连续速度分段的独立代数：切点折点只在后段0出现一次。
        self.assertEqual(left.speed_breaks,((0.,3.),))
        self.assertEqual(right.speed_breaks,((0.,5.),(2.,7.)))
        self.assertEqual((left.end_s,right.end_s),(4.,4.))
        self.assertEqual(left.curve_xy[-1],right.curve_xy[0])
        self.assertEqual(left.release_delay_s,.14)
        # 两次member_nominal仅是确定性分段调用；离开release绝不被叠加。
        with patch("v08.motion.dwell_nominal.member_nominal",side_effect=[leg(0,20.1),leg(4,999.9)]):
            d = member_nominal_with_dwell(mp,(4.,20.))
        self.assertEqual(d.release_s,20.1)
        self.assertEqual(d.end_s,20.1+28.)

    def test_grid_actual_members_and_closed_semantic_ranges(self):
        stations = dwell_grid(20.,90.)
        # 网格定义，5m，独立枚举。
        np.testing.assert_array_equal(stations,np.arange(20.,91.,5.))
        pts = {"a":np.c_[stations,np.zeros(len(stations))],
               "b":np.c_[stations+10.,np.zeros(len(stations))]}
        ss = {"a":stations,"b":stations+10.}
        base = [NS(geometry=circle(2.,70.),sense=1,minimum_m=0.)]
        mask = admissible_dwell_mask(stations,ss,pts,{"a":[(60.,65.)],"b":[]},
                                     circle(100.),circle(40.),base)
        # 圆解析：两成员交集s∈[52.5,77.5]，网格55..75；闭区间删60,65；障碍删70。
        np.testing.assert_array_equal(stations[mask],[55.,75.])
        self.assertFalse(bool(mask[np.flatnonzero(stations==90.)[0]]))  # warning SDF=-10，在穿越带。

    def test_discrete_domain_and_draw_count(self):
        class Fake:
            def __init__(self,values): self.values=iter(values); self.calls=[]
            def integers(self,a,b): self.calls.append((a,b)); return next(self.values)
        r=Fake([1,1200])
        self.assertEqual(draw_dwell(np.array([55.,75.]),r),(75.,120.))
        # U D.3.5：追加恰两个抽取；端点1001种值等概率，不用uniform后round。
        self.assertEqual(r.calls,[(0,2),(200,1201)])
        r=Fake([0,200])
        self.assertEqual(draw_dwell(np.array([55.]),r),(55.,20.))
        r=Fake([])
        with self.assertRaises(ValueError): draw_dwell(np.array([]),r)
        self.assertEqual(r.calls,[])  # 空集合不消费RNG、不重抽。
        with self.assertRaises(ValueError): compose_dwell(leg(0),leg(4),19.9)

    def test_dwell_table_time_and_empty_legacy_path(self):
        d=compose_dwell(leg(0),leg(4),20.)
        sk=NS(witnesses={"dwell_windows":{"m":(4.,20.,(4.,0.))}})
        rows=dwell_lines_from_skeleton(sk,{"m":{"nominal":d}})
        # U D.2与解析时间：到达24，离开44，两个正交切向；meta不参与求解。
        self.assertEqual(tuple(tuple(x[:5]) for x in rows),
                         (("m",24.,44.,(4.,0.),(1.,0.)),("m",24.,44.,(4.,0.),(0.,1.))))
        self.assertEqual(dwell_lines_from_skeleton(NS(witnesses={}),{}),())
        mp=MemberPlan("m",0,((0.,0.),(2.,0.),(4.,0.)),100.,4.,0.,((0.,2.),),())
        with patch("v08.motion.nominal.member_nominal",return_value=leg(0)), \
             patch("v08.motion.dwell_nominal.member_nominal_with_dwell",side_effect=AssertionError("legacy entered dwell")):
            refs,lines,maps=references_from_skeleton(NS(members={"m":mp},witnesses={}))
        self.assertEqual(lines,())
        self.assertEqual((refs[0].release_s,refs[0].end_s),(20.,24.))
        np.testing.assert_array_equal(maps["m"]["t_abs"],[20.,22.,24.])

    def test_nominal_dwell_and_second_warning_entry(self):
        f=NS(id="t",geometry=circle(20),center=(0.,0.),
             offsets={"warning":80.,"alert":20.,"protected":10.})
        # 正例：x=110→70，停20s→110；仅在预警层驻留，方位恒定，重访方位覆盖为0。
        x=np.r_[np.linspace(110.,70.,41),np.full(200,70.),np.linspace(71.,110.,40)]
        p=np.c_[x,np.zeros(len(x)),np.zeros(len(x))]
        v=np.zeros_like(p); v[:,0]=np.gradient(x,.1)
        t=np.arange(len(x),dtype=np.int64)*100_000
        a=screen_close_observation_member([f],"t",t,p,v)
        self.assertTrue(a["passed"])
        self.assertEqual(a["counts"]["visits"],1)
        self.assertTrue(a["observation_dwell"]["detected"])
        self.assertNotIn("no_dwell_window",a["conditions"])
        # 第一个外出110后再返回70：两次进入，即使已有足够驻留也必须拒。
        xx=np.r_[x,np.linspace(109.,70.,40),np.linspace(71.,110.,40)]
        pp=np.c_[xx,np.zeros(len(xx)),np.zeros(len(xx))]
        vv=np.zeros_like(pp); vv[:,0]=np.gradient(xx,.1)
        b=screen_close_observation_member([f],"t",np.arange(len(xx),dtype=np.int64)*100_000,pp,vv)
        self.assertEqual(b["counts"]["visits"],2)
        self.assertFalse(b["conditions"]["single_warning_visit"])
        self.assertFalse(b["passed"])

    def test_checkpoint_boundaries_and_counter_objects(self):
        rows=[dict(contract_id=f"c{i}",success=i>=10,attempts=1,group_size=2,
                   facility_count=1,initial_speed_m_s=4.,shape_audit_failed_attempts=0)
              for i in range(200)]
        # U D.5严格<95%，190/200不触发，189/200触发；没有排除名单。
        self.assertEqual(skeleton_checkpoint(rows)["triggered"],[])
        rows[10]["success"]=False
        self.assertIn("success_rate",skeleton_checkpoint(rows)["triggered"])
        c=attempt_counters([{"ok":True,"optimization_entered":True},
                            {"ok":False,"optimization_entered":True,"stage":"optimize"},
                            {"ok":False,"optimization_entered":False,"stage":"skeleton"},
                            {"ok":False,"stage":"exception"}])
        self.assertEqual(c,{"post_optimization_failures":1,"skeleton_failures":1,"unknown_attempts":1})
        q=[dict(contract_id=str(i),success=i<16,attempts=1,post_optimization_failures=0,
                skeleton_failures=0,optimization_s=60.,retained_p0_ok=True) for i in range(20)]
        self.assertEqual(quick_checkpoint(q)["triggered"],[])  # U：16/20、0、60恰等不触发。


if __name__ == "__main__":
    unittest.main()
