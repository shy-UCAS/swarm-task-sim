"""V8-18预置测试，未经运行；磁盘输出与冻结核验。"""
import hashlib
import json
import os
import unittest
from pathlib import Path
import numpy as np
import shapely

from v08.scene.context import load_context
from v08.scene.exact import signed_distance
from v08.sim.types import MemberTrack
from v08.criteria.segment import SegmentTask, verify_segments
from v08.criteria.validity import check_validity, visible_track

QUICK = {f"o{o:02d}_d{d}" for o in (1,2,3,4,5,6,7,8,9,11) for d in (0,1)}
FULL = {f"o{o:02d}_d{d}" for o in range(1,41) for d in range(5)}
BAD_KEYS = {
    "seconds", "wall_s", "wall_time", "elapsed_s", "elapsed_seconds", "cpu_s",
    "prepare_s", "solve_s", "check_s", "optimization_s", "timing", "stage_timing",
    "skeleton_detail", "build_seconds", "attempt_wall_s", "attempt_s",
    "skeleton_s", "optimize_s", "simulation_s", "verify_s", "lp_s", "chord_set_s",
    "chord_exact_s", "corridor_s", "route_s", "candidate_s", "prewarm_s",
    "cache_hits", "cache_misses_computed", "traceback", "tracebacks", "pid"
}


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def keys(v, at=""):
    if isinstance(v, dict):
        for k, x in v.items():
            yield k, at + "/" + k
            yield from keys(x, at + "/" + k)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from keys(x, at + "/" + str(i))


def files(p):
    return {f.relative_to(p).as_posix(): f for f in p.rglob("*") if f.is_file()}


class ArtifactPreset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("V8_18_ACCEPTANCE"):
            raise unittest.SkipTest("V8_18_ACCEPTANCE未设置，验收未执行")
        cls.a = read(os.environ["V8_18_ACCEPTANCE"])
        doc = read(cls.a["devset"])
        es = doc["families"] if isinstance(doc, dict) else doc
        cls.entries = {e["family_id"]: e for e in es}

    def assert_same_tree(self, left, right):
        a, b = files(left), files(right)
        # U F.1：比较全部原始文件，不排除失败见证或任意文件。
        self.assertTrue(a, left)
        self.assertEqual(set(a), set(b), (left, right))
        for name in sorted(a):
            self.assertEqual(a[name].read_bytes(), b[name].read_bytes(), name)

    def test_three_intents_two_gates_and_frozen_files(self):
        gs = self.a["gates"]
        # U D.2：3×2=6，不可少一轮。
        self.assertEqual(len(gs), 6)
        self.assertEqual({(g["intent"], g["phase"]) for g in gs},
                         {(i,p) for i in ("monitoring","transit","intrusion") for p in (2,4)})
        for g in gs:
            root = Path(g["repeat"])
            # 固定快批名单独立于运行结果。
            self.assertEqual({r["contract_id"] for r in read(root / "records.json")}, QUICK)
            for cid in sorted(QUICK):
                self.assert_same_tree(Path(g["baseline"]) / "contracts" / cid,
                                      root / "contracts" / cid)
        hashes = self.a["frozen_files"]
        # U D.7：整个monitoring_turn文件只读；其余冻结清单第1部分预登记。
        self.assertTrue(any(Path(p).name == "monitoring_turn.py" for p in hashes))
        for p, digest in hashes.items():
            self.assertEqual(hashlib.sha256(Path(p).read_bytes()).hexdigest(), digest, p)

    def test_disk_events_validity_and_no_timing(self):
        # U D.6：quick/full都验，不只验最终成功子集。
        self.assertEqual({o["stage"] for o in self.a["outputs"]}, {"quick", "full"})
        for o in self.a["outputs"]:
            root = Path(o["path"])
            rows = read(root / "records.json")
            expected = QUICK if o["stage"] == "quick" else FULL
            self.assertEqual(len(rows), len(expected))
            self.assertEqual({r["contract_id"] for r in rows}, expected)
            # U验收成功率门槛蕴含非零成功；无保留者不能让物理核验空循环通过。
            self.assertTrue(any(r["success"] for r in rows))
            if o["stage"] == "full":
                div = read(root / "diversity" / "records.json")
                # U D.1：100个固定尝试，10族各branch0..9；不要求每个种子成功。
                self.assertEqual(len(div), 100)
                self.assertEqual(len({r["contract_id"] for r in div}), 100)
                fams = {r["family_id"] for r in div}
                self.assertEqual(len(fams), 10)
                for fid in fams:
                    self.assertEqual({(r["draw_index"], r["branch"]) for r in div if r["family_id"] == fid},
                                     {(0, b) for b in range(10)})
            for r in rows:
                folder = root / "contracts" / r["contract_id"]
                for file in folder.rglob("*.json"):
                    for key, where in keys(read(file)):
                        # R16教训、U A：递归扫描嵌套字段，不只顶层timing。
                        self.assertNotIn(key, BAD_KEYS, (str(file), where))
                saved = read(folder / "result.json")
                self.assertEqual(saved["success"], r["success"])
                if not r["success"]:
                    continue
                ctx = load_context(self.entries[r["family_id"]],
                                   data_root=Path(self.a["data_root"]), cache_dir=Path(self.a["cache"]))
                target = ctx.facility_by_id[r["target_id"]]
                tracks = {}
                for mid in r["member_ids"]:
                    td = folder / "tracks" / mid
                    a = {k: np.load(td / (k + ".npy"), allow_pickle=False)
                         for k in ("tau_us", "p", "v", "a", "segment_index")}
                    # r5：10Hz整数微秒、有限物理数组、单段0。
                    self.assertTrue(np.issubdtype(a["tau_us"].dtype, np.integer))
                    np.testing.assert_array_equal(np.diff(a["tau_us"]),
                                                  np.full(len(a["tau_us"])-1, 100_000))
                    np.testing.assert_array_equal(a["segment_index"], np.zeros(len(a["tau_us"]), int))
                    for k in ("p","v","a"):
                        self.assertTrue(np.isfinite(a[k]).all())
                    tr = MemberTrack(mid, a["tau_us"], a["p"], a["v"], a["a"], a["segment_index"], ())
                    tracks[mid] = tr
                    mask = (tr.tau_us >= saved["release_us"][mid]) & (tr.segment_index == 0)
                    self.assertTrue(mask.any())  # 保留轨迹定义：必须有释放后窗口。
                    tt, xy = tr.tau_us[mask], tr.p[mask, :2]
                    sd = np.asarray(signed_distance(target.geometry, xy))
                    info = saved["feint"]["members"][mid]
                    for layer in ("warning","alert"):
                        inside = sd <= target.offsets[layer]
                        starts = np.flatnonzero(inside & ~np.r_[False, inside[:-1]])
                        ends = np.flatnonzero(~inside & np.r_[False, inside[:-1]])
                        # U D.4/F.1独立预期：一入一出；直接从磁盘几何帧推导，不调新screen。
                        self.assertEqual((len(starts), len(ends)), (1, 1), (mid, layer))
                        self.assertEqual(info["entry_counts"][layer], 1)
                        self.assertEqual(info["first_entry_us"][layer], int(tt[starts[0]]))
                        self.assertEqual(info["first_exit_us"][layer], int(tt[ends[0]]))
                    sp = np.asarray(signed_distance(target.layers["protected"], xy))
                    self.assertEqual(info["min_protected_sdf_m"], float(sp.min()))
                    # 冻结层码以<=为内，未入protected要求严格在其外；不是骨架10m门槛。
                    self.assertTrue(np.all(sd > target.offsets["protected"]))
                    for f in ctx.facilities:
                        self.assertGreater(float(signed_distance(f.geometry, xy[-1])), f.offsets["warning"])
                verdicts = verify_segments(ctx.scene, tracks, saved["release_us"],
                                           [SegmentTask(0, "feint", r["target_id"])])
                valid = check_validity(ctx.scene, [visible_track(tracks[m], saved["release_us"][m])
                                                   for m in sorted(tracks)])
                # 冻结V8-11/物理代码为独立权威，不以生成器success自证。
                self.assertTrue(all(v.passed for v in verdicts))
                self.assertTrue(valid.passed)
                self.assertTrue(saved["retained_p0_ok"])
                if valid.min_separation_m is not None:
                    self.assertGreaterEqual(valid.min_separation_m, 2.0)

    def test_predeclared_five_serial(self):
        full = Path(next(o["path"] for o in self.a["outputs"] if o["stage"] == "full"))
        repeat = Path(self.a["rerun"])
        expected = {f"o01_d{d}" for d in range(5)}
        # U D.1/D.6：字典序前五键，失败也复跑。
        self.assertEqual({r["contract_id"] for r in read(repeat / "records.json")}, expected)
        for cid in sorted(expected):
            self.assert_same_tree(full / "contracts" / cid, repeat / "contracts" / cid)


if __name__ == "__main__":
    unittest.main()
