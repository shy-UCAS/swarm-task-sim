import copy
import hashlib
import json
import math
import os
from pathlib import Path
import unittest
import numpy as np

from task_v07.criteria import load_criteria
from task_v07.detectors import dwell, revisit
from task_v07.geometry import geometry_facts
from v08.config import load_config
from v08.criteria.validity import check_validity, visible_track
from v08.scene.exact import center_of_geometry
from v08.sim.types import MemberTrack
from v08.runner.detour_serialization import assert_contract_payload

OLD = ("monitoring","transit","intrusion","feint","close_observation","area_search")
QUICK = tuple(f"o{o:02d}_d{d}" for o in (*range(1,10),11) for d in (0,1))
RERUN = tuple(f"o01_d{d}" for d in range(5))
ATOL = 1e-9  # 存储浮点与独立重算对照；候选比较不使用此容差。


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def tree(p):
    p=Path(p)
    return {f.relative_to(p).as_posix():f.read_bytes() for f in sorted(p.rglob("*")) if f.is_file()}


def independent_sweep(t,xy,warning,center,D):
    # 独立逐帧状态机；不导入detour_numeric，也不使用保存的事实。
    sd=np.asarray(geometry_facts(warning,xy)["signed_distance_m"],float)
    angle=np.unwrap(np.arctan2(xy[:,1]-center[1],xy[:,0]-center[0]))
    active=False; begin=None; intervals=[]; entries=[]; exits=[]
    for k in range(len(t)):
        inside=bool(0 < sd[k] <= D)
        if inside and not active:
            begin=k; entries.append(int(t[k]))
        if active and not inside:
            a=angle[begin:k]
            intervals.append((float(np.degrees(a.max()-a.min())),float(np.degrees(abs(a[-1]-a[0])))))
            exits.append(int(t[k]))
        active=inside
    if active:
        a=angle[begin:]
        intervals.append((float(np.degrees(a.max()-a.min())),float(np.degrees(abs(a[-1]-a[0])))))
    best=max(range(len(intervals)),key=lambda j:intervals[j][0]) if intervals else None
    return {"sd":sd,"spans":[x[0] for x in intervals],"span":0.0 if best is None else intervals[best][0],
            "net":0.0 if best is None else intervals[best][1],"entries":entries,"exits":exits}


class ArtifactsV21(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.I=read(os.environ["V8_21_ACCEPTANCE"])["artifact_inputs"]
        raw=read(cls.I["candidate_config"])
        cls.C={k:v["value"] for k,v in raw["parameters"].items()}
        cls.cfg=load_criteria()
        cls.retreat=load_config("monitoring").values["retreat_clearance_m"]

    def test_two_six_intent_byte_gates(self):
        self.assertEqual(set(self.I["gates"]),{"gate_p2","gate_p4"})
        for phase,items in self.I["gates"].items():
            self.assertEqual(set(items),set(OLD))
            for intent,roots in items.items():
                a=Path(roots["actual"])/"contracts"; b=Path(roots["baseline"])/"contracts"
                self.assertEqual({p.name for p in a.iterdir() if p.is_dir()},set(QUICK))
                for cid in QUICK:
                    actual,baseline=tree(a/cid),tree(b/cid)
                    self.assertTrue(actual,(phase,intent,cid,"empty actual"))
                    self.assertTrue(baseline,(phase,intent,cid,"missing baseline"))
                    self.assertEqual(actual,baseline,(phase,intent,cid))
                if intent=="monitoring":
                    self.assertIn("2026-11-10_V8-22_monitoring_entry",str(b))

    def test_five_key_single_worker_bytes(self):
        a=Path(self.I["rerun_dir"])/"contracts"; b=Path(self.I["full_dir"])/"contracts"
        self.assertEqual({p.name for p in a.iterdir() if p.is_dir()},set(RERUN))
        for cid in RERUN:
            actual,baseline=tree(a/cid),tree(b/cid)
            self.assertTrue(actual,(cid,"empty rerun"))
            self.assertTrue(baseline,(cid,"missing full contract"))
            self.assertEqual(actual,baseline,cid)

    def test_frozen_files(self):
        self.assertTrue(self.I["frozen_files"])
        for path,expected in self.I["frozen_files"].items():
            self.assertEqual(sha(path),expected,path)

    def test_all_retained_candidates_independently(self):
        root=Path(self.I["full_dir"])/"contracts"
        expected={f"o{o:02d}_d{d}" for o in range(1,41) for d in range(5)}
        self.assertEqual({p.name for p in root.iterdir() if p.is_dir()},expected)
        checked=0
        for cid in sorted(expected):
            p=root/cid; con=read(p/"contract.json"); result=read(p/"result.json")
            self.assertEqual(con["intent"],"detour")
            self.assertNotIn("survey",con)
            self.assertEqual(result["verdict_source"],"detour_candidate")
            assert_contract_payload(result,document="result")
            if not result["success"]:
                continue
            checked+=1
            sb=self.I["scenes_by_order"][str(con["order"])]
            self.assertEqual(sha(sb["path"]),sb["sha256"])
            scene=read(sb["path"])
            entities=scene["entities"]
            fac={e["id"]:e["geometry"] for e in entities if e["type"]=="facility"}
            layers={f:{} for f in fac}
            for e in entities:
                if e["type"]=="protection_zone":
                    layers[e["facility_id"]][e["layer"]]=e["geometry"]
            target=con["target_id"]; D=self.C["near_band_width_m"]
            stats={}; tracks={}; per_fac={f:[] for f in fac}
            for mid in con["member_ids"]:
                arr={k:np.load(p/"tracks"/mid/(k+".npy"),allow_pickle=False)
                     for k in ("tau_us","p","v","a","segment_index")}
                tr=MemberTrack(mid,arr["tau_us"],arr["p"],arr["v"],arr["a"],arr["segment_index"],())
                tracks[mid]=tr
                keep=(tr.tau_us>=result["release_us"][mid]) & (tr.segment_index==0)
                t=tr.tau_us[keep]; xy=tr.p[keep,:2]; vel=tr.v[keep]
                self.assertGreater(len(t),0)
                self.assertTrue(np.all(np.diff(t)==100000))
                levels={}
                sweeps={}
                for f,g in fac.items():
                    lv=np.zeros(len(t),dtype=np.int8)
                    for name,code in (("warning",1),("alert",2),("protected",3)):
                        inside=geometry_facts(layers[f][name],xy)["inside"]
                        lv=np.where(inside,code,lv)
                    levels[f]=lv
                    q=independent_sweep(t,xy,layers[f]["warning"],center_of_geometry(g),D)
                    sweeps[f]=q; per_fac[f].append(q["span"])
                    self.assertEqual(int(lv[0]),0)
                    self.assertEqual(int(lv[-1]),0)
                    self.assertGreaterEqual(float(q["sd"][-1]),self.retreat)
                q=sweeps[target]
                self.assertEqual(int(levels[target].max()),0)
                self.assertEqual(len(q["entries"]),1)
                self.assertGreaterEqual(q["span"],self.C["min_sweep_deg"])
                self.assertTrue(all(s<self.C["max_sweep_deg_exclusive"] for s in q["spans"]))
                self.assertGreater(float(q["sd"][-1]), D)
                for f in fac:
                    if f!=target:
                        self.assertLessEqual(int(levels[f].max()),1)
                ones=np.ones(len(t),dtype=bool)
                self.assertFalse(dwell(xy,t,ones,self.cfg)["detected"])
                self.assertFalse(revisit(xy,vel,t,levels[target],ones,
                                         np.asarray(center_of_geometry(fac[target])),self.cfg)["detected"])
                saved=result["detour"]["members"][mid]
                self.assertEqual(saved["near_entry_count"],len(q["entries"]))
                self.assertEqual(saved["near_exit_count"],len(q["exits"]))
                self.assertEqual(saved["first_near_entry_us"],q["entries"][0])
                self.assertEqual(saved["last_near_exit_us"],q["exits"][-1] if q["exits"] else None)
                self.assertAlmostEqual(saved["max_span_deg"],q["span"],delta=ATOL)
                self.assertAlmostEqual(saved["best_net_deg"],q["net"],delta=ATOL)
                self.assertAlmostEqual(saved["min_target_warning_distance_m"],float(q["sd"].min()),delta=ATOL)
            visible=[visible_track(tracks[m],result["release_us"][m]) for m in sorted(tracks)]
            self.assertTrue(check_validity(scene,visible).passed)
            for f,vals in per_fac.items():
                if f!=target:
                    self.assertLess(min(vals),self.C["min_sweep_deg"])
                    self.assertAlmostEqual(result["detour"]["other_facility_sweep_deg"][f],min(vals),delta=ATOL)
            self.assertTrue(result["retained_p0_ok"])
            self.assertTrue(result["candidate_verdict"]["passed"])
            self.assertEqual(result["detour"]["candidate"]["criteria_sha256"],sha(self.I["candidate_config"]))
            self.assertTrue(all(all(c.values()) for c in result["candidate_verdict"]["member_conditions"].values()))
            self.assertTrue(all(result["candidate_verdict"]["group_conditions"].values()))
            # 任意深度未知字段不得被静默丢掉；不改变实际文件。
            bad=copy.deepcopy(result)
            mid=con["member_ids"][0]
            bad["detour"]["members"][mid]["cache_hit"]=True
            with self.assertRaises(ValueError):
                assert_contract_payload(bad,document="result")
        self.assertGreater(checked,0)  # 防空证据，不要求200合同全部成功。


if __name__ == "__main__":
    unittest.main()
