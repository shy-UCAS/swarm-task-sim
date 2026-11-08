"""V8-19 预置测试，未经运行；本地接口及冻结几何依赖单列。"""
import unittest
from contextlib import nullcontext
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import shapely

from v08.motion import optimize as O
from v08.motion.layer_limits import constraints_for_task
from v08.motion.transit_chords import query_identity
from v08.contract.monitoring import TaskSpec
from v08.sim.tracking import TimeReference


def circle(r):
    return dict(type="Circle",center_m=[0.,0.],radius_m=float(r))


def context():
    f=NS(id="t",geometry=circle(20),center=(0.,0.),
         layers={"warning":circle(300),"alert":circle(160),"protected":circle(100)},
         offsets={"warning":280.,"alert":140.,"protected":80.})
    return NS(facilities=[f],facility_by_id={"t":f},world=circle(4000),obstacles=[],
              params={"world_margin_m":35.,"obstacle_margin_m":35.,"forbidden_margin_m":10.,
                      "pre_entry_warning_clearance_m":10.,"alignment_length_m":100.,"curve_spacing_m":.5},
              extra={},inputs={"sha256":{}},cache_key="fixture",cold_build=nullcontext,
              family=NS(initial_states={"m":{}}),field=lambda *a,**k:None)


class InterfacePreset(unittest.TestCase):
    def test_exact_control_indices_and_elimination(self):
        pd=np.array([4.,7.])
        def pva(t):
            shape=np.asarray(t).shape+(2,)
            return np.broadcast_to(pd,shape).copy(),np.zeros(shape),np.zeros(shape)
        ref=TimeReference("m",20.,30.,100.,pva)
        lines=(("m",24.,26.,tuple(pd),(1.,0.)),("m",24.,26.,tuple(pd),(0.,1.)))
        mem=O.Prepared._member(NS(knot_s=1.,hold=2.),ref,lines)
        # 手算：j-3<6且j+1>4，即4<=j<=8；每轴一行。
        self.assertEqual([j for j,_,_ in mem.line_rows],[4,5,6,7,8]*2)
        self.assertEqual(len(mem.line_rows),10)
        ids=np.array([4,5,6,7,8])
        np.testing.assert_allclose(mem.c_star.reshape(-1,2)[ids]+mem.p0,
                                   np.tile(pd,(5,1)),rtol=0,atol=32*np.finfo(float).eps*7)
        self.assertEqual(mem.Z[np.ravel(np.c_[2*ids,2*ids+1])].nnz,0)
        self.assertGreater(mem.Z[[6,7,18,19]].nnz,0)  # j=3、9不是驻留固定点。

    def test_outer_appends_after_merge_and_legacy_empty(self):
        raw=(("m",20.,21.,(0.,0.),(1.,0.),{"kind":"crossing"}),)
        nom=NS(curve=NS(s=np.array([0.,4.,8.])),t_nodes=np.array([0.,4.,28.]),release_s=20.)
        maps={"m":{"nominal":nom}}
        for intent in ("close_observation","transit","intrusion","feint"):
            with self.subTest(intent=intent):
                w={"target_id":"t","intent":intent,"turn_ranges":{}}
                if intent=="close_observation": w["dwell_windows"]={"m":(4.,20.,(4.,0.))}
                sol=NS(ok=False,reason="fixture",references={},diagnostics={})
                with patch("v08.motion.skeleton.references_from_skeleton",return_value=((),raw,maps)), \
                     patch("v08.motion.skeleton.merge_semantic_lines",return_value=raw) as merge, \
                     patch.object(O,"solve_joint",return_value=sol) as solve:
                    out=O._optimize_segment_intent(context(),NS(witnesses=w,members={}),None,{"knot_s":1.},intent)
                # 原merge只收到raw且仅一次；驻留两条只追加，旧意图0条。
                merge.assert_called_once_with(raw,knot_s=1.)
                lines=solve.call_args.args[0].lines
                want=(tuple(raw[0][:5]),)
                if intent=="close_observation":
                    want+=(("m",24.,44.,(4.,0.),(1.,0.)),("m",24.,44.,(4.,0.),(0.,1.)))
                self.assertEqual(lines,want)
                self.assertIs(out["problem"],solve.call_args.args[0])

    def test_layer_table_and_intent_cache_identity(self):
        ctx=context()
        cons=constraints_for_task(ctx,TaskSpec("task0","close_observation","t"))
        # S冻结上限1：world内35、目标alert外10；穿越表只有warning。
        self.assertEqual([(c.name,c.sense,c.minimum_m) for c in cons["base"]],
                         [("world",-1,35.),("alert:t",1,10.)])
        self.assertEqual(list(cons["crossing_boundaries"]),["t"])
        old=query_identity(ctx,"t",[(0.,0.)])
        explicit=query_identity(ctx,"t",[(0.,0.)],intent="transit")
        new=query_identity(ctx,"t",[(0.,0.)],intent="close_observation")
        self.assertEqual(old,explicit)  # 默认旧身份原样，不给旧identity补intent。
        self.assertNotIn("intent",old[1])
        self.assertEqual(new[1]["intent"],"close_observation")
        self.assertNotEqual(old[0],new[0])


if __name__ == "__main__":
    unittest.main()
