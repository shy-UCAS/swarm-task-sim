"""V8-20 产物预置测试。未经运行；不启动仿真，独立读取全部落盘产物。"""
import ast
import hashlib
import json
import os
import re
import unittest
from pathlib import Path
import numpy as np
import shapely
from task_v07.detectors import azimuth_coverage
from v08.scene.context import load_context
from v08.scene.exact import signed_distance
from v08.sim.types import MemberTrack
from v08.criteria.segment import SegmentTask,verify_segments
from v08.criteria.validity import check_validity,visible_track
from v08.runner.area_search_serialization import assert_contract_payload

OLD = ("monitoring","transit","intrusion","feint","close_observation")
QUICK = {f"o{o:02d}_d{d}" for o in (1,2,3,4,5,6,7,8,9,11) for d in (0,1)}
FULL = {f"o{o:02d}_d{d}" for o in range(1,41) for d in range(5)}
DIV = {f"o{o:02d}_d0_b{b}" for o in range(1,11) for b in range(10)}
BAD = {"seconds","wall_s","wall_time","elapsed_s","elapsed_seconds","cpu_s","prepare_s",
       "solve_s","check_s","optimization_s","timing","stage_timing","skeleton_detail",
       "build_seconds","attempt_wall_s","attempt_s","skeleton_s","optimize_s","simulation_s",
       "verify_s","lp_s","chord_set_s","chord_exact_s","corridor_s","route_s","candidate_s",
       "prewarm_s","sector_set_s","coverage_s","reference_solve_s","cache_hits","cache_miss",
       "cache_misses_computed","cache_hit","cache_path","traceback","tracebacks","pid",
       "path","filepath","filename","directory"}


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def tree(p):
    return {f.relative_to(p).as_posix():f.read_bytes() for f in p.rglob("*") if f.is_file()}


def nodes(x):
    if isinstance(x,dict):
        for k,v in x.items():
            yield k,v
            yield from nodes(v)
    elif isinstance(x,list):
        for v in x:
            yield from nodes(v)


def strings(x):
    if isinstance(x,str):
        yield x
    elif isinstance(x,dict):
        for v in x.values():
            yield from strings(v)
    elif isinstance(x,list):
        for v in x:
            yield from strings(v)


class ArtifactPreset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("V8_20_ACCEPTANCE"):
            raise unittest.SkipTest("V8_20_ACCEPTANCE未设置，验收未执行")
        cls.a = read(os.environ["V8_20_ACCEPTANCE"])
        es = read(cls.a["devset"])
        if isinstance(es,dict):
            es = es["families"]
        cls.entries = {e["family_id"]:e for e in es}

    def same(self,a,b):
        aa,bb = tree(a),tree(b)
        self.assertTrue(aa,str(a))  # 独立不变量：空目录不能作为字节门禁证据。
        self.assertEqual(set(aa),set(bb))  # U F.1比较完整相对文件集合，无排除。
        for name in sorted(aa):
            self.assertEqual(aa[name],bb[name],name)

    def test_ten_gates_and_frozen_source(self):
        gs = self.a["gates"]
        # U D.2：五意图×两轮，不允许重复一个intent代替漏项。
        self.assertEqual(len(gs),10)
        self.assertEqual({(g["intent"],g["phase"]) for g in gs},{(i,p) for i in OLD for p in (2,4)})
        for g in gs:
            self.assertEqual(g["exclusions"],[])
            root = Path(g["repeat"])
            rows = read(root/"records.json")
            self.assertEqual(len(rows),20)
            self.assertEqual({r["contract_id"] for r in rows},QUICK)
            for cid in sorted(QUICK):
                self.same(Path(g["baseline"])/"contracts"/cid,root/"contracts"/cid)
                for f in (root/"contracts"/cid).rglob("*.json"):
                    # 非新意图任何嵌套层都不出现空或非空survey。
                    self.assertFalse(any(k=="survey" for k,_ in nodes(read(f))),str(f))
        self.assertTrue(self.a["frozen_files"])  # 快照必须有实际冻结对象。
        for path,h in self.a["frozen_files"].items():
            self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(),h,path)
        fs = self.a["frozen_symbols"]
        self.assertTrue({"member_nominal","NominalPVA","Prepared","_eliminate","solve_joint"}
                        <= {r["qualname"] for r in fs})
        for r in fs:
            text = Path(r["path"]).read_text(encoding="utf-8")
            node = next(n for n in ast.parse(text).body if getattr(n,"name",None)==r["qualname"])
            raw = ast.get_source_segment(text,node).encode("utf-8")
            self.assertEqual(hashlib.sha256(raw).hexdigest(),r["sha256"],r["qualname"])
        self.assertEqual(len(self.a["preset_files"]),3)  # 本指令三个原样预置文件。
        for path,h in self.a["preset_files"].items():
            self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(),h,path)

    def test_all_saved_tracks_and_surveys(self):
        outputs = self.a["outputs"]
        self.assertEqual(len(outputs),2)
        self.assertEqual({o["stage"] for o in outputs},{"quick","full"})
        for o in outputs:
            jobs = [(Path(o["path"]),QUICK if o["stage"]=="quick" else FULL)]
            if o["stage"]=="full":
                jobs.append((Path(o["path"])/"diversity",DIV))
            for root,expected in jobs:
                rows = read(root/"records.json")
                # U固定名单，失败也必须有记录，不能验完成子集。
                self.assertEqual(len(rows),len(expected))
                self.assertEqual({r["contract_id"] for r in rows},expected)
                for r in rows:
                    folder = root/"contracts"/r["contract_id"]
                    self.assertTrue((folder/"contract.json").is_file())
                    for f in folder.rglob("*.json"):
                        doc = read(f)
                        assert_contract_payload(doc)  # 固定schema之外还有下面独立禁止字段扫描。
                        for key,value in nodes(doc):
                            self.assertNotIn(key.lower(),BAD,(f,key))
                            self.assertFalse(key.lower().endswith(("_path","_dir")),(f,key))
                        for value in strings(doc):
                            self.assertIsNone(re.search(r"^[A-Za-z]:[\\/]|^\\\\|^/(home|tmp|mnt|Users|workspace)/",value),
                                              (f,value))
                    contract = read(folder/"contract.json")
                    saved = read(folder/"result.json")
                    self.assertEqual(contract["intent"],"area_search")
                    self.assertIn("survey",contract)
                    self.assertEqual(saved["success"],r["success"])
                    if not r["success"]:
                        continue  # 失败合同已扫描；不能要求它有保留轨迹。
                    s = contract["survey"]
                    block = saved["area_search"]
                    self.assertEqual(block["survey"],s)
                    c = s["strips_per_member"]
                    self.assertIsInstance(c,int)
                    self.assertGreaterEqual(c,2)
                    self.assertEqual(c%2,0)  # U C.2偶数条带，外端退出。
                    self.assertEqual(s["strip_count"],len(r["member_ids"])*c)
                    indices = [k for mid in r["member_ids"] for k in block["members"][mid]["strip_indices"]]
                    self.assertEqual(sorted(indices),list(range(s["strip_count"])))
                    ctx = load_context(self.entries[r["family_id"]],data_root=Path(self.a["data_root"]),
                                       cache_dir=Path(self.a["cache"]))
                    tgt = ctx.facility_by_id[r["target_id"]]
                    tracks = {}
                    for mid in r["member_ids"]:
                        td = folder/"tracks"/mid
                        a = {k:np.load(td/(k+".npy"),allow_pickle=False)
                             for k in ("tau_us","p","v","a","segment_index")}
                        self.assertTrue(np.issubdtype(a["tau_us"].dtype,np.integer))
                        np.testing.assert_array_equal(np.diff(a["tau_us"]),np.full(len(a["tau_us"])-1,100000))
                        np.testing.assert_array_equal(a["segment_index"],np.zeros(len(a["tau_us"]),int))
                        for k in ("p","v","a"):
                            self.assertTrue(np.isfinite(a[k]).all())
                        tr = MemberTrack(mid,a["tau_us"],a["p"],a["v"],a["a"],a["segment_index"],())
                        tracks[mid] = tr
                        mask = (tr.tau_us>=saved["release_us"][mid])&(tr.segment_index==0)
                        tt,xy = tr.tau_us[mask],tr.p[mask,:2]
                        self.assertGreater(len(tt),0)
                        sd = np.asarray(signed_distance(tgt.geometry,xy))
                        inside = sd<=tgt.offsets["warning"]
                        starts = np.flatnonzero(inside & ~np.r_[False,inside[:-1]])
                        exits = np.flatnonzero(~inside & np.r_[False,inside[:-1]])
                        info = block["members"][mid]
                        # 独立层几何复算事件，不调用新measured_area_search来验证自己。
                        self.assertEqual((len(starts),len(exits)),(1,1))
                        self.assertFalse(bool(inside[0]))
                        self.assertEqual(info["warning_entry_count"],1)
                        self.assertEqual(info["warning_exit_count"],1)
                        self.assertEqual(info["first_warning_entry_us"],int(tt[starts[0]]))
                        self.assertEqual(info["first_warning_exit_us"],int(tt[exits[0]]))
                        self.assertTrue(np.all(sd>tgt.offsets["alert"]))
                        for fac in ctx.facilities:
                            self.assertGreater(float(signed_distance(fac.geometry,xy[-1])),fac.offsets["warning"])
                        self.assertTrue(info["ended_outside_all_warning"])
                        self.assertEqual(info["strip_count"],c)
                        self.assertEqual(info["azimuth_span_deg"],azimuth_coverage(xy[inside],tgt.center))
                    verdict = verify_segments(ctx.scene,tracks,saved["release_us"],
                                              [SegmentTask(0,"area_search",r["target_id"],survey=s)])[0]
                    valid = check_validity(ctx.scene,[visible_track(tracks[m],saved["release_us"][m])
                                                      for m in sorted(tracks)])
                    self.assertTrue(verdict.passed)  # 冻结判据独立oracle，非新代码回填预期。
                    self.assertTrue(valid.passed)
                    self.assertTrue(saved["retained_p0_ok"])
                    self.assertEqual(block["coverage"],verdict.group["shared_coverage"])
                    self.assertGreaterEqual(block["coverage"]["coverage_fraction"],.80)
                    for mid in tracks:
                        w = verdict.windows[mid]
                        effective = np.flatnonzero(w.coverage["effective_mask"])
                        self.assertGreater(len(effective),0)
                        info = block["members"][mid]
                        self.assertEqual(info["first_effective_frame_index"],int(effective[0]))
                        self.assertEqual(info["first_effective_us"],int(w.time_us[effective[0]]))
                        self.assertEqual(info["effective_frame_count"],len(effective))

    def test_predeclared_serial_five(self):
        full = Path(next(o["path"] for o in self.a["outputs"] if o["stage"]=="full"))
        repeat = Path(self.a["rerun"])
        expected = {f"o01_d{d}" for d in range(5)}
        rows = read(repeat/"records.json")
        self.assertEqual(len(rows),5)
        self.assertEqual({r["contract_id"] for r in rows},expected)
        for cid in sorted(expected):
            self.same(full/"contracts"/cid,repeat/"contracts"/cid)


if __name__ == "__main__":
    unittest.main()
