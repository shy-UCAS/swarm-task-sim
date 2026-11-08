"""V8-19 预置测试，未经运行；全部保留轨迹、失败合同、字节门禁。"""
import ast
import hashlib
import json
import os
import re
import unittest
from pathlib import Path
import numpy as np
import shapely

from v08.scene.context import load_context
from v08.scene.exact import signed_distance
from v08.sim.types import MemberTrack
from v08.criteria.segment import SegmentTask,verify_segments
from v08.criteria.validity import check_validity,visible_track

QUICK={f"o{o:02d}_d{d}" for o in (1,2,3,4,5,6,7,8,9,11) for d in (0,1)}
FULL={f"o{o:02d}_d{d}" for o in range(1,41) for d in range(5)}
DIV={f"o{o:02d}_d0_b{b}" for o in range(1,11) for b in range(10)}
BAD={"seconds","wall_s","wall_time","elapsed_s","elapsed_seconds","cpu_s","prepare_s","solve_s",
     "check_s","optimization_s","timing","stage_timing","skeleton_detail","build_seconds","attempt_wall_s",
     "attempt_s","skeleton_s","optimize_s","simulation_s","verify_s","lp_s","chord_set_s","chord_exact_s",
     "corridor_s","route_s","candidate_s","prewarm_s","cache_hits","cache_misses_computed","cache_hit",
     "cache_miss","traceback","tracebacks","pid","path","filepath","filename","directory"}


def read(p): return json.loads(Path(p).read_text(encoding="utf-8"))


def tree(p):
    return {f.relative_to(p).as_posix():f.read_bytes() for f in p.rglob("*") if f.is_file()}


def nodes(x,where=""):
    if isinstance(x,dict):
        for k,v in x.items():
            yield k,v,where+"/"+k
            yield from nodes(v,where+"/"+k)
    elif isinstance(x,list):
        for i,v in enumerate(x): yield from nodes(v,where+"/"+str(i))


def strings(x):
    if isinstance(x,str): yield x
    elif isinstance(x,dict):
        for v in x.values(): yield from strings(v)
    elif isinstance(x,list):
        for v in x: yield from strings(v)


class ArtifactPreset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("V8_19_ACCEPTANCE"):
            raise unittest.SkipTest("V8_19_ACCEPTANCE未设置，验收未执行")
        cls.a=read(os.environ["V8_19_ACCEPTANCE"])
        es=read(cls.a["devset"])
        if isinstance(es,dict): es=es["families"]
        cls.entries={e["family_id"]:e for e in es}

    def same(self,a,b):
        aa,bb=tree(a),tree(b)
        self.assertTrue(aa,a)  # 非空证据，不能空目录“相同”。
        self.assertEqual(set(aa),set(bb),(a,b))  # U F.1，全文件，排除[]。
        for n in sorted(aa): self.assertEqual(aa[n],bb[n],n)

    def test_eight_gates_and_frozen_objects(self):
        gs=self.a["gates"]
        # U D.2.4：四意图两轮=8组，不能用一轮替代。
        self.assertEqual(len(gs),8)
        self.assertEqual({(g["intent"],g["phase"]) for g in gs},
                         {(i,p) for i in ("monitoring","transit","intrusion","feint") for p in (2,4)})
        for g in gs:
            root=Path(g["repeat"])
            rows=read(root/"records.json")
            self.assertEqual(len(rows),20)
            self.assertEqual({r["contract_id"] for r in rows},QUICK)
            for cid in sorted(QUICK): self.same(Path(g["baseline"])/"contracts"/cid,root/"contracts"/cid)
        self.assertTrue(self.a["frozen_files"])
        for p,h in self.a["frozen_files"].items():
            self.assertEqual(hashlib.sha256(Path(p).read_bytes()).hexdigest(),h,p)
        fs=self.a["frozen_symbols"]
        self.assertTrue({"member_nominal","NominalPVA","Prepared","_eliminate","solve_joint"}
                        <= {r["qualname"] for r in fs})
        for r in fs:
            text=Path(r["path"]).read_text(encoding="utf-8")
            node=next(n for n in ast.parse(text).body if getattr(n,"name",None)==r["qualname"])
            raw=ast.get_source_segment(text,node).encode("utf-8")
            self.assertEqual(hashlib.sha256(raw).hexdigest(),r["sha256"],r["qualname"])

    def test_all_outputs_and_independent_frozen_verification(self):
        outputs=self.a["outputs"]
        self.assertEqual(len(outputs),2)
        self.assertEqual({o["stage"] for o in outputs},{"quick","full"})
        for o in outputs:
            jobs=[(Path(o["path"]),QUICK if o["stage"]=="quick" else FULL)]
            if o["stage"]=="full": jobs.append((Path(o["path"])/"diversity",DIV))
            for root,expected in jobs:
                rows=read(root/"records.json")
                # U D.1固定名单，失败也在；多样性并非只验主批。
                self.assertEqual(len(rows),len(expected))
                self.assertEqual({r["contract_id"] for r in rows},expected)
                self.assertTrue(any(r["success"] for r in rows))
                for r in rows:
                    folder=root/"contracts"/r["contract_id"]
                    for f in folder.rglob("*.json"):
                        doc=read(f)
                        for k,v,where in nodes(doc):
                            self.assertNotIn(k.lower(),BAD,(f,where))
                            self.assertFalse(k.lower().endswith(("_path","_dir")),(f,where))
                        for value in strings(doc):
                            self.assertIsNone(re.search(r"^[A-Za-z]:[\\/]|^\\\\|^/(home|tmp|mnt|Users|workspace)/",value),
                                              (f,value))
                    saved=read(folder/"result.json")
                    self.assertEqual(saved["success"],r["success"])
                    if not r["success"]: continue
                    ctx=load_context(self.entries[r["family_id"]],data_root=Path(self.a["data_root"]),
                                     cache_dir=Path(self.a["cache"]))
                    tgt=ctx.facility_by_id[r["target_id"]]
                    tracks={}
                    block=saved["close_observation"]
                    ticks=block["duration_ticks"]
                    self.assertIsInstance(ticks,int)
                    self.assertTrue(200<=ticks<=1200)  # U的整数抽样域。
                    opt=read(folder/"optimized.json")
                    for mid in r["member_ids"]:
                        td=folder/"tracks"/mid
                        a={k:np.load(td/(k+".npy"),allow_pickle=False)
                           for k in ("tau_us","p","v","a","segment_index")}
                        self.assertTrue(np.issubdtype(a["tau_us"].dtype,np.integer))
                        np.testing.assert_array_equal(np.diff(a["tau_us"]),np.full(len(a["tau_us"])-1,100_000))
                        np.testing.assert_array_equal(a["segment_index"],np.zeros(len(a["tau_us"]),int))
                        for k in ("p","v","a"): self.assertTrue(np.isfinite(a[k]).all())
                        tr=MemberTrack(mid,a["tau_us"],a["p"],a["v"],a["a"],a["segment_index"],())
                        tracks[mid]=tr
                        mask=(tr.tau_us>=saved["release_us"][mid])&(tr.segment_index==0)
                        tt,xy=tr.tau_us[mask],tr.p[mask,:2]
                        self.assertTrue(len(tt)>0)
                        sd=np.asarray(signed_distance(tgt.geometry,xy))
                        inside=sd<=tgt.offsets["warning"]
                        starts=np.flatnonzero(inside & ~np.r_[False,inside[:-1]])
                        ends=np.flatnonzero(~inside & np.r_[False,inside[:-1]])
                        # U D.4额外条件的独立几何复算，不调新measured函数自证。
                        self.assertEqual((len(starts),len(ends)),(1,1))
                        info=block["members"][mid]
                        self.assertEqual(info["warning_entry_count"],1)
                        self.assertEqual(info["first_warning_entry_us"],int(tt[starts[0]]))
                        self.assertEqual(info["first_warning_exit_us"],int(tt[ends[0]]))
                        self.assertTrue(np.all(sd>tgt.offsets["alert"]))
                        self.assertEqual(info["duration_s"],ticks/10.)
                        pd=np.asarray(info["point_xy"])
                        self.assertEqual(info["warning_sdf_m"],float(signed_distance(tgt.layers["warning"],pd)))
                        self.assertEqual(info["alert_sdf_m"],float(signed_distance(tgt.layers["alert"],pd)))
                        self.assertLessEqual(info["warning_sdf_m"],-12.5)
                        self.assertGreaterEqual(info["alert_sdf_m"],12.5)
                        for fac in ctx.facilities:
                            self.assertGreater(float(signed_distance(fac.geometry,xy[-1])),fac.offsets["warning"])
                        self.assertTrue(info["ended_outside_all_warning"])
                        dl=[x for x in opt["lines"] if x[0]==mid and x[5].get("kind")=="dwell"]
                        self.assertEqual(len(dl),2)  # U D.2，不合并掉其中一条。
                        self.assertEqual({tuple(x[4]) for x in dl},{(1.,0.),(0.,1.)})
                        trj=opt["members"][mid]
                        controls=np.asarray(trj["controls"],float)
                        h=trj["knots"][4]-trj["knots"][3]
                        bound=np.sqrt(np.finfo(float).eps)*max(1.,float(np.abs(controls).max()))
                        for line in dl:
                            self.assertEqual(line[1],info["nominal_arrival_s"])
                            self.assertEqual(line[2],line[1]+info["duration_s"])
                            js=np.arange(len(controls))
                            selected=((js-3)*h<line[2]-trj["release_s"])&((js+1)*h>line[1]-trj["release_s"])
                            # S line_equality独立控制点复算，界为冻结等式界，不放宽业务约束。
                            self.assertTrue(selected.any())
                            self.assertLessEqual(float(np.abs(controls[selected]-pd).max()),bound)
                    vs=verify_segments(ctx.scene,tracks,saved["release_us"],
                                       [SegmentTask(0,"close_observation",r["target_id"])])
                    valid=check_validity(ctx.scene,[visible_track(tracks[m],saved["release_us"][m])
                                                   for m in sorted(tracks)])
                    self.assertTrue(all(v.passed for v in vs))
                    self.assertTrue(valid.passed)
                    self.assertTrue(saved["retained_p0_ok"])
                    for mid in tracks:
                        w=vs[0].windows[mid]; dw=w.observation_dwell
                        self.assertTrue(dw["detected"])
                        info=block["members"][mid]
                        self.assertEqual(info["observation_first_start_us"],int(w.time_us[dw["frame_index"]]))
                        self.assertEqual(info["observation_first_confirm_us"],int(w.time_us[dw["confirm_frame_index"]]))
                    if valid.min_separation_m is not None:
                        self.assertGreaterEqual(valid.min_separation_m,2.)  # 冻结quality门槛。

    def test_predeclared_five_serial(self):
        full=Path(next(o["path"] for o in self.a["outputs"] if o["stage"]=="full"))
        repeat=Path(self.a["rerun"])
        expected={f"o01_d{d}" for d in range(5)}
        rows=read(repeat/"records.json")
        self.assertEqual(len(rows),5)
        self.assertEqual({r["contract_id"] for r in rows},expected)
        for cid in sorted(expected): self.same(full/"contracts"/cid,repeat/"contracts"/cid)


if __name__ == "__main__":
    unittest.main()
