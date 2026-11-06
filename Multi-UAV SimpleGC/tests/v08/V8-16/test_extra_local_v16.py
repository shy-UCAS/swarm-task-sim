"""V8-16 自加测试（执行方编写，不替代预置测试）：本地几何/构造控制流/语义失败重做。依赖 shapely 导入环境；
最后一项需要真实数据（V8_16_DATA_ROOT、V8_16_TEST_CACHE、V8_16_DEVSET），缺输入明确 skip，不计为通过。"""
import math
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import shapely  # noqa: F401  本文件属于本地几何测试层

from v08.motion import transit_chords as TC


def square_buffer(b):
    return dict(type="BufferedPolygon", vertices_m=[[-10, -10], [10, -10], [10, 10], [-10, 10]], buffer_m=b)


class ExtraLocal(unittest.TestCase):
    def test_buffered_polygon_rounded_corners_exact(self):
        """BufferedPolygon = 凸多边形 ⊕ 圆盘：边带与顶点圆盘的并给出精确交区间（不用 shapely 默认分辨率近似）。"""
        g = square_buffer(5.0)
        lo, hi = TC.line_sublevel(g, (0.0, 12.0), (1.0, 0.0), 0.0)
        self.assertAlmostEqual(lo, -10.0 - math.sqrt(21.0), places=12)
        self.assertAlmostEqual(hi, 10.0 + math.sqrt(21.0), places=12)
        lo, hi = TC.line_sublevel(g, (0.0, 14.5), (1.0, 0.0), 0.0)
        self.assertAlmostEqual(hi, 10.0 + math.sqrt(25.0 - 4.5 ** 2), places=12)
        self.assertIsNone(TC.line_sublevel(g, (0.0, 15.1), (1.0, 0.0), 0.0))
        lo, hi = TC.line_sublevel(g, (0.0, 0.0), (1.0, 0.0), -3.0)       # 内收 3：|x| ≤ 12
        self.assertAlmostEqual(lo, -12.0, places=12)
        self.assertAlmostEqual(hi, 12.0, places=12)
        from v08.scene.exact import signed_distance
        for y in (0.0, 7.0, 12.0, 14.5):
            iv = TC.line_sublevel(g, (0.0, y), (1.0, 0.0), 0.0)
            for x in iv:
                self.assertAlmostEqual(float(signed_distance(g, (x, y))), 0.0, places=9)

    def test_column_reference_covers_longitudinal_offsets(self):
        """纵列端部不 clamp：参考两端延展 max|l| + 1，成员站点范围 [s_c + l, s_t + l] 完整在参考内。"""
        from v08.motion.formation import Slots, derive_members
        from v08.motion.intents.transit import build_reference
        P = dict(origin_xy=(0.0, 0.0), u=(1.0, 0.0), n=(0.0, 1.0), h_m=0.0, x_c=0.0, x_t=100.0, curve=None,
                 x_entry_ref=None, x_exit_ref=None)
        ref, marks = build_reference(P, 21.0, 0.5)
        self.assertAlmostEqual(ref.s[-1], 142.0, places=9)
        slots = Slots(("a", "b"), {"a": (-20.0, 0.0), "b": (20.0, 0.0)}, "column", "column", "column", False, 20.0, 20.0)
        lanes = derive_members(ref, slots, (ref.marks["collect"], ref.marks["terminal"]), spacing_m=0.5)
        np.testing.assert_allclose(lanes["a"].xy[0], [-20.0, 0.0], atol=1e-9)
        np.testing.assert_allclose(lanes["b"].xy[-1], [120.0, 0.0], atol=1e-9)
        with self.assertRaises(ValueError):
            derive_members(ref, slots, (ref.marks["collect"] - 5.0, ref.marks["terminal"]), spacing_m=0.5)

    def _fake(self):
        from v08.motion.formation import formation_slots
        from v08.sampler.keys import RngKey
        fam = NS(lateral_spacing_m=10.0, family_id="fam")
        group = NS(member_ids=("a", "b"), formation_prior="abreast")
        key = RngKey("fam", 0, "shape", mission=0, group="g0", segment=0)
        fk = RngKey("fam", 0, "formation", mission=0, group="g0", segment=0)
        slots = formation_slots(group, fam, fk, formation="abreast")
        S = NS(tgt=NS(center=(0.0, 0.0), layers={"warning": dict(type="Circle", center_m=[0, 0], radius_m=200.0)}),
               M={"spline_basis_min": 4, "spline_basis_max": 8, "retreat_clearance_m": 50.0}, base=[], warn={},
               band=10.0, align=100.0, timing={}, stats={})
        cells = [[k % 18, 5.0 * k, 400.0, -150.0, [100.0, 110.0, 120.0]] for k in range(37)]
        payload = {"slots": slots, "doc": {"cells": cells, "query_id": "q"}, "lateral_step_m": None}
        return S, group, key, payload, cells

    def test_uniform_cell_index_single_draw_and_no_regrid(self):
        """可行格均匀索引只抽一次：精确弦检查失败即结束 attempt，不换格（assess 只调用一次），索引来自 shape 键第一次 integers。"""
        from v08.motion.intents import transit as T
        from v08.sampler.keys import rng_for
        S, group, key, payload, cells = self._fake()
        rng, crng = rng_for(key), rng_for(key)
        expect = int(rng_for(key).integers(0, len(cells)))
        calls = []
        def audit(*a, **k):
            calls.append(1)
            return {"feasible": False, "first_error": {"x": 1}, "margins": {}}
        with patch.object(T.TC, "assess_straight_bundle", side_effect=audit):
            plan = T._build_with_cells(S, None, group, NS(target_id="t"), {}, key, payload, 10.0, [], rng, crng)
        self.assertEqual(len(calls), 1)
        self.assertEqual(plan.failure.feasible_set, "chord_exact_audit")
        self.assertTrue(plan.failure.witness["shape_audit_failed"])
        self.assertEqual(plan.proposal["cell_index"], expect)

    def test_entry_route_failure_keeps_cell_and_formation(self):
        """进场路由失败原样结束 attempt：不换格、不换队形（width_then_build 只 build 一次）。"""
        from v08.motion.intents import transit as T
        from v08.motion.skeleton import width_then_build
        from v08.sampler.keys import rng_for
        S, group, key, payload, cells = self._fake()
        built = []
        def build(name, pl):
            built.append(name)
            with patch.object(T.TC, "assess_straight_bundle",
                              return_value={"feasible": True, "first_error": None, "margins": {}}), \
                    patch.object(T.TC, "corridor_rows", return_value={
                        "available": False, "reason": "corridor_unavailable", "D": 5.0, "inset_interval": None,
                        "rows_total": 0, "certified_rows": 0, "run": None, "certified_length_m": 0.0,
                        "inset_length_m": 0.0, "x": [], "lo": [], "hi": []}), \
                    patch.object(T, "plan_starts", return_value=(None, "a")) as ps:
                plan = T._build_with_cells(S, None, group, NS(target_id="t"), {}, key, pl, 10.0, [],
                                           rng_for(key), rng_for(key))
            self.assertEqual(ps.call_count, 1)
            return plan
        plan = width_then_build(("abreast", "echelon", "column"), lambda n: payload, build)
        self.assertEqual(built, ["abreast"])
        self.assertEqual(plan.failure.feasible_set, "start_route")
        self.assertEqual(plan.proposal["fallback_reason"], "corridor_unavailable")

    def test_transit_screen_multiple_visits_and_start_inside(self):
        """单次进入：离开后再进入不通过；首帧已在目标 warning 内不通过；从不进入不通过。"""
        from v08.motion.nominal_checks import screen_transit_member
        f = NS(id="t", center=(0.0, 0.0), geometry=dict(type="Circle", center_m=[0, 0], radius_m=20.0),
               offsets=dict(warning=180.0, alert=30.0, protected=0.0))
        def run(xs, y=100.0):
            xs = np.asarray(xs, float)
            p = np.c_[xs, np.full(len(xs), y), np.full(len(xs), 80.0)]
            v = np.c_[np.full(len(xs), 10.0), np.zeros((len(xs), 2))]
            t = np.arange(len(xs), dtype=np.int64) * 100_000
            return screen_transit_member([f], "t", t, p, v)
        twice = np.r_[np.arange(-300.0, 300.0, 1.0), np.arange(300.0, -300.0, -1.0)]
        self.assertFalse(run(twice)["conditions"]["single_warning_visit"])
        self.assertFalse(run(np.arange(0.0, 300.0, 1.0))["conditions"]["started_outside_target_warning"])
        never = run(np.arange(-300.0, 300.0, 1.0), y=400.0)
        self.assertFalse(never["conditions"]["entered_warning"])
        self.assertFalse(never["passed"])

    def test_frechet_cut_before_resample(self):
        """先精确截出单次穿越段，再按自身弧长 5 m 重采样（末端不足 5 m 保留）。"""
        from v08.runner.transit_report import _cut_resample, _exact_crossings
        g = dict(type="Circle", center_m=[0.0, 0.0], radius_m=200.0)
        xy = np.c_[np.linspace(-300.0, 302.0, 7), np.zeros(7)]
        cr, cum = _exact_crossings(xy, g)
        self.assertEqual([d for _, d in cr], ["in", "out"])
        self.assertAlmostEqual(cr[0][0], 100.0, places=9)
        self.assertAlmostEqual(cr[1][0], 500.0, places=9)
        seg = _cut_resample(xy, cr[0][0], cr[1][0], 5.0)
        self.assertEqual(len(seg), 81)
        np.testing.assert_allclose(seg[[0, -1]], [[-200.0, 0.0], [200.0, 0.0]], atol=1e-9)

    def test_semantic_failure_next_attempt_and_clean_save(self):
        """真实 o01_d0：第一次优化后语义检查强制失败 → 下一 attempt；保存的是干净 attempt，磁盘轨迹过冻结核验。"""
        need = ("V8_16_DATA_ROOT", "V8_16_TEST_CACHE", "V8_16_DEVSET")
        if not all(os.environ.get(k) for k in need):
            raise unittest.SkipTest(f"{need} 未全部设置；该项未执行，不是通过")
        import json
        from v08.criteria.segment import SegmentTask, verify_segments
        from v08.criteria.validity import check_validity, visible_track
        from v08.motion import optimize_checks as OC
        from v08.motion.optimize import load_settings
        from v08.runner.joint_intent import run_contract
        from v08.runner.monitoring import load_entries
        from v08.scene.context import load_context
        from v08.sim.types import MemberTrack
        e = {int(x["order"]): x for x in load_entries(os.environ["V8_16_DEVSET"])}[1]
        ctx = load_context(e, data_root=Path(os.environ["V8_16_DATA_ROOT"]), cache_dir=Path(os.environ["V8_16_TEST_CACHE"]))
        ctx.cache_dir = None
        real = OC.check_transit
        n = {"k": 0}
        def first_fails(*a, **k):
            out = real(*a, **k)
            n["k"] += 1
            if n["k"] == 1:
                return {**out, "passed": False, "failures": [{"kind": "injected_semantic", "member": None}]}
            return out
        with tempfile.TemporaryDirectory() as tmp, patch.object(OC, "check_transit", side_effect=first_fails):
            rec = run_contract(ctx, e, 0, intent="transit", settings=load_settings(), out_dir=Path(tmp))
            self.assertTrue(rec["success"])
            self.assertEqual(rec["attempts"], 2)
            self.assertEqual(rec["attempt_log"][0]["stage"], "optimize_transit")
            self.assertEqual(rec["post_optimization_failures"], 1)
            d = Path(tmp) / "contracts" / rec["contract_id"]
            saved = json.loads((d / "result.json").read_text(encoding="utf-8"))
            self.assertTrue(saved["success"])
            self.assertEqual(json.loads((d / "contract.json").read_text(encoding="utf-8"))["intent"], "transit")
            tracks = {}
            for m in rec["member_ids"]:
                a = {k: np.load(d / "tracks" / m / f"{k}.npy") for k in ("tau_us", "p", "v", "a", "segment_index")}
                tracks[m] = MemberTrack(m, a["tau_us"], a["p"], a["v"], a["a"], a["segment_index"], ())
            v = verify_segments(ctx.scene, tracks, saved["release_us"], [SegmentTask(0, "transit", rec["target_id"])])
            self.assertTrue(all(x.passed for x in v))
            self.assertTrue(check_validity(ctx.scene, [visible_track(tracks[m], saved["release_us"][m])
                                                       for m in sorted(tracks)]).passed)


if __name__ == "__main__":
    unittest.main()
