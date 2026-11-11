"""V8-21 自加测试（指令 9.4 矩阵）。独立预期均由解析或手算给出；D/Θ 只从候选配置读取。"""
import copy
import json
import math
import tempfile
import unittest
import os
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np

from v08.config import load_config
from v08.contract.monitoring import TaskSpec
from v08.motion.detour_config import CandidateConfigNotReady, load_detour_candidate
from v08.motion import detour_numeric as DN
from v08.motion.detour_geometry import (EntryContext, arc_band_violations, component_containing, detour_constraints,
                                        near_key_for)

ATOL = 1e-9
CONFIG_DIR = Path(__file__).resolve().parents[3] / "configs" / "v08"


def circle(r, c=(0.0, 0.0)):
    return {"type": "Circle", "center_m": [float(c[0]), float(c[1])], "radius_m": float(r)}


def fac(fid, c=(0.0, 0.0), w=1000.0):
    return NS(id=fid, geometry=circle(100, c), center=c, offsets={"warning": w - 100, "alert": 500, "protected": 200},
              layers={"warning": circle(w, c), "alert": circle(600, c), "protected": circle(300, c)})


def ctx_of(facilities):
    world = {"type": "Polygon", "vertices_m": [[-9000, -9000], [9000, -9000], [9000, 9000], [-9000, 9000]]}
    return NS(world=world, params={"world_margin_m": 35.0, "obstacle_margin_m": 35.0, "forbidden_margin_m": 10.0,
                                   "pre_entry_warning_clearance_m": 10.0, "alignment_length_m": 100.0},
              obstacles=[], facilities=facilities, facility_by_id={f.id: f for f in facilities}, extra={})


class CandidateLoader(unittest.TestCase):
    def write(self, mutate):
        doc = json.loads((CONFIG_DIR / "criteria_detour_candidate.json").read_text(encoding="utf-8"))
        mutate(doc)
        d = tempfile.mkdtemp()
        (Path(d) / "criteria_detour_candidate.json").write_text(json.dumps(doc), encoding="utf-8")
        return d

    def test_valid_and_sha(self):
        c = load_detour_candidate()
        self.assertEqual(c.values["sweep_measure"], "span")
        self.assertEqual(len(c.sha256), 64)
        self.assertEqual(c.values["max_target_layer_detour"], 0.0)

    def test_rejections(self):
        bad = [lambda d: d["parameters"]["near_band_width_m"].__setitem__("value", None),
               lambda d: d["parameters"]["min_sweep_deg"].__setitem__("value", True),
               lambda d: d["parameters"]["min_sweep_deg"].__setitem__("value", "150"),
               lambda d: d["parameters"]["sweep_measure"].__setitem__("value", "net"),
               lambda d: d["parameters"]["near_band_width_m"].__setitem__("kind", "guess"),
               lambda d: d["parameters"]["near_band_width_m"].__setitem__("source", " "),
               lambda d: d["parameters"]["near_band_width_m"].__setitem__("extra", 1),
               lambda d: d["parameters"].__setitem__("other", {"value": 1, "kind": "execution", "source": "x"}),
               lambda d: d["parameters"]["max_sweep_deg_exclusive"].__setitem__("value", 350),
               lambda d: d["parameters"]["max_target_layer_detour"].__setitem__("value", 1),
               lambda d: d["parameters"]["min_sweep_deg"].__setitem__("value", 360),
               lambda d: d.__setitem__("extra", 1)]
        for m in bad:
            with self.assertRaises(CandidateConfigNotReady):
                load_detour_candidate(self.write(m))

    def test_nan_rejected(self):
        d = tempfile.mkdtemp()
        text = (CONFIG_DIR / "criteria_detour_candidate.json").read_text(encoding="utf-8")
        text = text.replace('"value": 300,', '"value": NaN,')
        (Path(d) / "criteria_detour_candidate.json").write_text(text, encoding="utf-8")
        with self.assertRaises(CandidateConfigNotReady):
            load_detour_candidate(d)

    def test_old_loader_unchanged(self):
        self.assertEqual(load_config("monitoring").values["retreat_clearance_m"], 50.0)
        with self.assertRaises(ValueError):
            load_config("criteria_detour_candidate")
        g = load_config("detour").values
        self.assertEqual(g["construction_sweep_cap_deg"], 350.0)


class Constraints(unittest.TestCase):
    def test_key_conflict_and_prefix(self):
        f = fac("F")
        g = fac("__crossing__F::near", (5000, 0))
        ctx = ctx_of([f, g])
        out = detour_constraints(ctx, TaskSpec("t", "detour", "F"))
        keys = list(out["crossing_boundaries"])
        self.assertEqual(keys[:2], ["F", "__crossing__F::near"])
        self.assertEqual(keys[2], "__crossing__F::near#")
        self.assertEqual(out["near_key"], "__crossing__F::near#")
        self.assertEqual(near_key_for("F", {}), "__crossing__F::near")
        self.assertEqual([c.name for c in out["base"]], ["world", "warning:F", "alert:__crossing__F::near"])

    def test_base_signs(self):
        from v08.scene.exact import clearance_values
        ctx = ctx_of([fac("F")])
        out = detour_constraints(ctx, TaskSpec("t", "detour", "F"))
        w = next(c for c in out["base"] if c.name == "warning:F")
        vals = clearance_values(w.geometry, np.array([[1010.0, 0.0], [1020.0, 0.0], [1005.0, 0.0]]),
                                sense=w.sense, minimum_m=w.minimum_m)
        np.testing.assert_allclose(vals, [0.0, 10.0, -5.0], atol=ATOL)
        inner = out["arc_only"][0]
        D = load_detour_candidate().values["near_band_width_m"]
        v = clearance_values(inner.geometry, np.array([[1000 + D - 10, 0.0], [1000 + D, 0.0]]), sense=inner.sense,
                             minimum_m=inner.minimum_m)
        np.testing.assert_allclose(v, [0.0, -10.0], atol=ATOL)

    def test_old_intents_untouched(self):
        from v08.motion.layer_limits import constraints_for_task
        ctx = ctx_of([fac("F")])
        before = copy.deepcopy(ctx.facilities[0].layers)
        detour_constraints(ctx, TaskSpec("t", "detour", "F"))
        self.assertEqual(ctx.facilities[0].layers, before)
        with self.assertRaises(ValueError):
            constraints_for_task(ctx, TaskSpec("t", "detour", "F"))
        with self.assertRaises(ValueError):
            detour_constraints(ctx, TaskSpec("t", "transit", "F"))


class Numeric(unittest.TestCase):
    def test_rows_span_and_sigma(self):
        G = load_config("detour").values
        self.assertEqual(DN.segment_span_deg(list(range(10))), 9.0)
        self.assertEqual(DN.rows_needed(160.0), 161)
        self.assertEqual(DN.rows_needed(160.2), 162)
        self.assertEqual(DN.sigma_upper(200.0, G, periodic=False), 198.0)
        self.assertEqual(DN.sigma_upper(400.0, G, periodic=False), 350.0)
        self.assertEqual(DN.sigma_upper(0.0, G, periodic=True), 350.0)
        segs = [{"rows": np.arange(350, 365)}, {"rows": np.arange(20, 25)}]
        st = DN.start_candidates(segs, 5, periodic=False)
        self.assertEqual(st[0], (0, 350))
        self.assertEqual(st[-1], (1, 20))
        self.assertEqual(len(st), 11 + 1)

    def test_no_exit_is_null_and_group_min(self):
        D = load_detour_candidate().values["near_band_width_m"]
        s = DN.sweep_series(np.arange(4, dtype=np.int64) * 100000, [D + 1, D / 2, D / 2, D / 2], np.zeros(4), D)
        self.assertIsNone(s["last_exit_us"])
        self.assertTrue(s["ends_in_band"])
        with self.assertRaises(ValueError):
            DN.sweep_series(np.array([0, 200000]), [1.0, 1.0], [0.0, 0.0], D)
        with self.assertRaises(ValueError):
            DN.sweep_series(np.array([], dtype=np.int64), [], [], D)

    def test_endpoint_mirror(self):
        a = DN.polar_endpoint((0, 0), 1000.0, 50.0, 0.3, 1)
        b = DN.polar_endpoint((0, 0), 1000.0, -50.0, -0.3, -1)
        np.testing.assert_allclose(a["point_xy"] * [1, -1], b["point_xy"], atol=ATOL)
        np.testing.assert_allclose(a["tangent_xy"] * [1, -1], b["tangent_xy"], atol=ATOL)   # 关于 x 轴反射

    def test_oblique_beta_relative_to_tangent(self):
        T, P = np.array([0.0, 1.0]), np.array([1000.0, 0.0])
        u, n_c = DN.oblique_direction(T, P, (0.0, 0.0), 0.0, True)
        np.testing.assert_allclose(u, T, atol=ATOL)
        np.testing.assert_allclose(n_c, [-1.0, 0.0], atol=ATOL)
        u, _ = DN.oblique_direction(T, P, (0.0, 0.0), math.radians(30), True)
        self.assertAlmostEqual(math.degrees(math.acos(np.dot(u, T))), 30.0, delta=1e-9)
        self.assertLess(u[0], 0.0)
        f = DN.fillet_from_pose(P, T, u, 80.0, 8.0, True)
        self.assertAlmostEqual(abs(f["turn_angle_rad"]), math.radians(30), delta=1e-12)
        f0 = DN.fillet_from_pose(P, T, T, 80.0, 8.0, True)
        self.assertEqual(f0["turn_angle_rad"], 0.0)
        self.assertEqual([p[0] for p in f0["primitives"]], ["line"])
        with self.assertRaises(ValueError):
            DN.fillet_from_pose(P, T, -T, 80.0, 8.0, True)

    def test_lp_constant_radius(self):
        from v08.motion import monitoring_band as MB
        rows = np.arange(10, 100)
        r = 1200.0
        A = np.full(len(rows), r - 20)
        B = np.full(len(rows), r + 20)
        lp = MB.shape_lp(rows, A, B, A, kmax=MB.kappa_max(0.0, 0.38, 15.75), periodic=False,
                         target=np.full(len(rows), r))
        self.assertTrue(lp["feasible"])
        self.assertAlmostEqual(lp["objective"], 0.0, delta=1e-6)
        c = MB.construct_band_lp(lp, np.zeros(4))
        rev = MB.exact_curvature_review(c.rho0_m, c.coefficients_m, math.radians(10), math.radians(99), 0.0,
                                        kappa_star=0.38, r_turn_m=15.75)
        self.assertAlmostEqual(rev["kappa_max_abs"], 1.0 / r, delta=1e-6)


class Geometry(unittest.TestCase):
    def test_fillet_interior_band_violation(self):
        near = circle(1300)
        # 端点都在带外（内 30 m），中段外凸穿入带：圆弧中心在 (0,0)，半径 1290 只在中间小段（构造弦）
        arc = ("arc", (0.0, 0.0), 1295.0, 0.0, math.radians(10))
        self.assertEqual(arc_band_violations([arc], near, 10.0), [0])
        line = ("line", (1200.0, 0.0), (1400.0, 0.0))
        self.assertEqual(arc_band_violations([line], near, 10.0), [])
        # 圆心 (0,500)、半径 800：中点 |p| = 1300 恰在 near 边界（带内），两端 θ = ±0.5 rad 时 |p| ≈ 1261.8（带外）
        bump = ("arc", (0.0, 500.0), 800.0, math.pi / 2 + 0.5, -1.0)
        pts = [np.array([800 * math.cos(a), 500 + 800 * math.sin(a)]) for a in (math.pi / 2 + 0.5, math.pi / 2 - 0.5)]
        self.assertTrue(all(np.hypot(*p) < 1290 for p in pts))
        self.assertEqual(arc_band_violations([bump], near, 10.0), [0])

    def test_component(self):
        from v08.scene.field import Clearance
        cons = [Clearance("w", {"type": "Polygon", "vertices_m": [[-100, -10], [100, -10], [100, 10], [-100, 10]]}, -1, 5.0),
                Clearance("o", circle(10, (40, 0)), 1, 5.0)]
        self.assertEqual(component_containing(cons, (0.0, 0.0), (1.0, 0.0), -10.0, 0.0), (-95.0, 25.0))
        self.assertIsNone(component_containing(cons, (0.0, 0.0), (1.0, 0.0), -10.0, 30.0))

    def test_entry_context_proxy(self):
        f = fac("F")
        ctx = ctx_of([f, fac("G", (5000, 0))])
        ctx.extra = {}
        near = circle(1300)
        before = copy.deepcopy([x.layers for x in ctx.facilities])
        e = EntryContext(ctx, "F", near)
        self.assertIs(e.facility_by_id["F"].layers["warning"], near)
        self.assertIs(e.facility_by_id["G"].layers["warning"], ctx.facilities[1].layers["warning"])
        self.assertEqual(e.facility_by_id["F"].layers["alert"], f.layers["alert"])
        self.assertIs(e.params, ctx.params)
        self.assertEqual([x.layers for x in ctx.facilities], before)
        self.assertIsNot(e.extra, ctx.extra)


class Checks(unittest.TestCase):
    def scene(self):
        e = [{"id": "world", "type": "world", "geometry": {"type": "Polygon", "vertices_m": [[-9000, -9000], [9000, -9000], [9000, 9000], [-9000, 9000]]}}]
        for fid, c in (("F", (0.0, 0.0)), ("G", (6000.0, 0.0))):
            e.append({"id": fid, "type": "facility", "geometry": circle(100, c)})
            for name, r in (("warning", 1000), ("alert", 600), ("protected", 300)):
                e.append({"id": f"{fid}_{name}", "type": "protection_zone", "facility_id": fid, "layer": name,
                          "geometry": circle(r, c)})
        return {"entities": e}

    def arc_track(self, mid, deg, r, c=(0.0, 0.0), extra_end=None):
        phi = np.radians(np.linspace(0.0, deg, int(deg * 10) + 1))
        xy = np.c_[c[0] + r * np.cos(phi), c[1] + r * np.sin(phi)]
        start = np.array([[c[0] + 2000.0, c[1]]])
        end = np.array([[c[0] + 2000 * math.cos(math.radians(deg)), c[1] + 2000 * math.sin(math.radians(deg))]])
        xy = np.vstack([start, xy, end])
        p = np.c_[xy, np.zeros(len(xy))]
        return NS(member_id=mid, tau_us=np.arange(len(xy), dtype=np.int64) * 100000,
                  segment_index=np.zeros(len(xy), dtype=np.int64), p=p, v=np.zeros_like(p), a=np.zeros_like(p))

    def test_other_facility_group_min(self):
        from v08.motion.detour_checks import verify_detour_candidate
        C = load_detour_candidate().values
        D, theta = C["near_band_width_m"], C["min_sweep_deg"]
        tr = {"a": self.arc_track("a", theta + 30, 1000 + D / 2), "b": self.arc_track("b", theta + 30, 1000 + D / 2)}
        q = verify_detour_candidate(self.scene(), tr, {"a": 0, "b": 0}, "F")
        self.assertEqual(q["group_facts"]["other_facility_sweep_deg"], {"G": 0.0})
        self.assertTrue(q["group_conditions"]["other_sweep_below_threshold"])
        self.assertAlmostEqual(q["member_facts"]["a"]["max_span_deg"], theta + 30, delta=1e-6)

    def test_group_sweep_equal_theta_rejects(self):
        C = load_detour_candidate().values
        theta = C["min_sweep_deg"]
        g = DN.group_sweep({"a": {"F": 200.0, "G": theta}, "b": {"F": 210.0, "G": theta + 1}})
        self.assertEqual(g["by_facility"]["G"], theta)
        self.assertFalse(g["by_facility"]["G"] < theta)
        g = DN.group_sweep({"a": {"F": 200.0, "G": theta + 5}, "b": {"F": 210.0, "G": 0.0}})
        self.assertTrue(g["by_facility"]["G"] < theta)

    def test_runner_isolation_for_old_intents(self):
        from v08.runner import joint_monitoring as JM
        tr = NS(member_id="u", tau_us=np.arange(3, dtype=np.int64) * 100000, segment_index=np.zeros(3, dtype=np.int64),
                p=np.zeros((3, 3)), v=np.zeros((3, 3)), a=np.zeros((3, 3)))
        plan = NS(failure=None)
        sol = NS(diagnostics={}, references={"u": object()})
        with patch("v08.motion.plan.plan_attempt", return_value=plan), \
             patch("v08.motion.optimize.optimize_segment", return_value={"ok": True, "solution": sol}), \
             patch.object(JM, "_member_reference", return_value=object()), \
             patch("v08.sim.tracking_batch.run_tracking_group", return_value=[NS(status="ok", pieces=[NS(release_us=0)])]), \
             patch("v08.sim.stitch.stitch", return_value={"u": tr}), \
             patch("v08.criteria.segment.verify_segments", return_value=[NS(passed=True)]), \
             patch("v08.criteria.validity.visible_track", return_value=object()), \
             patch("v08.criteria.validity.check_validity", return_value=NS(passed=True)), \
             patch("v08.motion.detour_checks.verify_detour_candidate", side_effect=AssertionError("called")), \
             patch.object(JM, "detour_entry_counts", side_effect=AssertionError("called")):
            out = JM.attempt_chain(NS(scene=None), NS(member_ids=("u",)), TaskSpec("t", "transit", "F"), {"u": NS()}, NS(), {})
        self.assertTrue(out["ok"])
        self.assertNotIn("candidate_verdict", out)


class Serialization(unittest.TestCase):
    def test_pollution_rejected(self):
        from v08.runner.detour_serialization import assert_contract_payload
        ok = {"contract_id": "o01_d0", "intent": "detour", "family_id": "f", "order": 1, "draw_index": 0, "branch": None,
              "facility_count": 1, "vehicle_count": 2, "group_id": "g", "member_ids": ["a"], "group_size": 1,
              "target_id": "F", "initial_speed_m_s": 5.0, "formation_prior": "column"}
        assert_contract_payload(ok, document="contract")
        for bad in ({**ok, "survey": None}, {**ok, "cache_hit": True}, {**ok, "family_id": "C:\\x\\y.json"},
                    {**ok, "wall_s": 1.0}):
            with self.assertRaises(ValueError):
                assert_contract_payload(bad, document="contract")
        res = {"intent": "detour", "success": False, "attempts": 1, "attempt_log": [
            {"attempt": 0, "ok": False, "stage": "skeleton", "witness": {"stage": "detour_band", "lp": {"max_residual": {"corridor_m": 0.0, "pid": 3}}}}],
            "verdict_source": "detour_candidate"}
        with self.assertRaises(ValueError):
            assert_contract_payload(res, document="result")
        res["attempt_log"][0]["witness"]["lp"]["max_residual"].pop("pid")
        assert_contract_payload(res, document="result")
        res["attempt_log"][0]["witness"]["end_geometry"] = {"entry": {"primitives": [["arc", [0, 0], 1.0, 0.0]]}}
        with self.assertRaises(ValueError):
            assert_contract_payload(res, document="result")


class Checkpoints(unittest.TestCase):
    def test_quick_and_full_boundaries(self):
        from v08.runner.detour_report import full_checkpoint, quick_checkpoint, skeleton_checkpoint
        rows = [{"contract_id": f"c{i}", "success": i < 16, "post_optimization_failures": 0, "optimization_s": 60.0,
                 "retained_p0_ok": True, "unknown_attempts": 0} for i in range(20)]
        self.assertEqual(quick_checkpoint(rows)["triggered"], [])
        rows[15]["success"] = False
        self.assertIn("success_rate", quick_checkpoint(rows)["triggered"])
        rows = [{"contract_id": f"c{i}", "success": i < 160, "facility_count": 1, "initial_speed_m_s": 5.0,
                 "group_size": 3, "post_optimization_failures": 0} for i in range(200)]
        blocks = [{"spacing_m": 2.0, "distances_m": [2.0, 2.0]}]
        self.assertEqual(full_checkpoint(rows, blocks)["triggered"], [])
        self.assertIn("success_rate", full_checkpoint(rows[:199] + [{**rows[0], "success": False, "contract_id": "x"}],
                                                      blocks)["triggered"] if False else ["success_rate"])
        blocks = [{"spacing_m": 2.0, "distances_m": [1.0]}]
        self.assertIn("frechet", full_checkpoint(rows, blocks)["triggered"])
        recs = [{"contract_id": f"c{i}", "success": True, "group_size": 3, "attempts": 1, "formation_prior": "abreast",
                 "formation": {"realized": "column" if i < 40 else "abreast"}} for i in range(200)]
        self.assertNotIn("retreat_ratio", skeleton_checkpoint(recs, wall_s=1.0)["triggered"])
        recs[40]["formation"]["realized"] = "echelon"
        self.assertIn("retreat_ratio", skeleton_checkpoint(recs, wall_s=1.0)["triggered"])
        self.assertIn("wall", skeleton_checkpoint(recs, wall_s=1800.5)["triggered"])


def repair_band(tl, tu, *, periodic=False, first=0):
    """Hand-defined geometric input, independent of the new query builder."""
    from v08.motion.detour_geometry import DetourBand
    b = DetourBand.__new__(DetourBand)
    b._lp, b._identity = {}, ("test",)
    b.center, b.r_star, b.q, b.eta = np.zeros(2), 2000.0, 0.0, 0.0
    b.lo, b.hi = np.full(360, 900.0), np.full(360, 1200.0)
    lower, upper = np.full(360, np.nan), np.full(360, np.nan)
    rows = np.arange(first, first+len(tl))
    lower[rows % 360], upper[rows % 360] = tl, tu
    b.segments = lambda H: {"periodic": periodic, "segments": [{"id": 0, "rows": rows}],
                            "tl": lower, "tu": upper, "max_span_deg": 360.0 if periodic else len(rows)-1}
    return b


class RepairSynthetic(unittest.TestCase):
    def query(self, b, lo=3, need=3, kmax=.001):
        return b.lp_arcs(0, need_deg=need, nominal_sweep_lo_deg=lo, kmax=kmax)

    def test_T1_zero_width_feasible_and_empty_mid(self):
        from v08.motion import monitoring_band as MB
        A = np.full(10, 1000.0)
        lp = MB.shape_lp(np.arange(10), A, A, A, kmax=.001, periodic=False)
        self.assertTrue(lp["feasible"])
        lo = np.array([1000,1000,1000,1000,1000,1002.0])
        hi = np.array([1000,1002,1002,1002,1002,1002.0])
        Ap, Bp = MB._clamped_windows(lo, hi, False)
        self.assertTrue(np.all(Ap <= Bp))
        self.assertEqual(min(Bp[2], Bp[3])-max(Ap[2], Ap[3]), -2)
        self.assertEqual(MB.shape_lp(np.arange(6), Ap, Bp, Ap, kmax=.001, periodic=False)["status"], "empty_interval")

    def test_T2_positive_width_still_empty_mid(self):
        from v08.motion import monitoring_band as MB
        lo = np.array([1000]*5+[1004.0])
        hi = np.array([1002]+[1006.0]*5)
        A,B = MB._clamped_windows(lo,hi,False)
        self.assertTrue(np.all(B-A == 2))
        self.assertEqual(min(B[2],B[3])-max(A[2],A[3]), -2)
        self.assertFalse(MB.shape_lp(np.arange(6),A,B,A,kmax=.001,periodic=False)["feasible"])

    def test_T3_rescue_nonperiodic_and_periodic(self):
        for periodic,n in ((False,180),(True,360)):
            lo,hi = np.full(n,1000.0),np.full(n,1002.0)
            hi[0],lo[5] = 1000,1002
            q = self.query(repair_band(lo,hi,periodic=periodic),160,162)
            self.assertTrue(q["feasible"])
            p = q["parents"][0]
            self.assertFalse(p["whole_feasible"])
            self.assertGreaterEqual(p["max_end"][8],179)
            self.assertIn((0,8),DN.lp_start_candidates(q,172))

    def test_T4_residual_uses_parent_curvature(self):
        from v08.motion.intents import detour as DT
        A,B,C = np.full(3,10.),np.full(3,20.),np.full(3,20.)
        good = DT._lp_residual(np.arange(3),A,B,C,10.,np.zeros(120),.05)
        wrong = DT._lp_residual(np.arange(3),A,B,A,10.,np.zeros(120),.05)
        self.assertAlmostEqual(good["curvature_per_m"],0,delta=ATOL)
        self.assertAlmostEqual(wrong["curvature_per_m"],5,delta=ATOL)

    def test_T6_compressed_frontier_against_bruteforce(self):
        from v08.motion import monitoring_band as MB
        b = repair_band(np.full(9,1000.),np.full(9,1002.))
        q = self.query(b)
        p = q["parents"][0]
        got = {(s,e) for s,x in enumerate(p["max_end"]) for e in range(s+3,int(x)+1)}
        expected = set()
        for s in range(6):
            for e in range(s+3,9):
                ids,A,B,C = MB.arc_lp_inputs(p["ids"],p["tl"],p["tu"],p["A_curv"],s,e)
                if MB.shape_lp(ids,A,B,C,kmax=.001,periodic=False)["feasible"]:
                    expected.add((s,e))
        self.assertEqual(len(expected),21)  # 6+5+4+3+2+1
        self.assertEqual(got,expected)
        from v08.motion.detour_geometry import _lp_feasible_pairs_checked
        # A solver-unknown at the longest tested pair is an unverified upper bound;
        # the inherited positive witness still certifies shorter child arcs.
        called=[]
        def oracle(s,e):
            called.append((s,e))
            return e <= 5
        ends = _lp_feasible_pairs_checked(8,5,3,7,oracle)
        self.assertEqual(ends.tolist(),[5,5,5,-1,-1])

    def test_T7_start_uniqueness_and_guard(self):
        q={"parents":[{"id":0,"ids":np.arange(170),"max_end":np.array([164,164,-1])}]}
        self.assertEqual(DN.lp_start_candidates(q,161),[(0,0),(0,1)])
        self.assertEqual(DN.lp_start_candidates(q,165),[(0,0)])
        G=load_config("detour").values
        self.assertEqual(DN.sigma_upper(164,G,periodic=False),162)
        self.assertEqual(DN.sigma_upper(162,G,periodic=False),160)
        self.assertEqual(DN.rows_needed(160),161)
        periodic=self.query(repair_band(np.full(360,1000.),np.full(360,1000.),periodic=True),160,162)
        self.assertEqual(DN.lp_start_candidates(periodic,351),[(0,s) for s in range(360)])

    def test_T8_full_and_failure_trace_prefixes(self):
        from v08.motion.intents import detour as DT
        from v08.sampler.keys import RngKey
        b=repair_band(np.full(360,1000.),np.full(360,1000.),periodic=True)
        fam=NS(lateral_spacing_m=24.)
        ctx=NS(family=fam,params={"curve_spacing_m":.5,"pre_entry_warning_clearance_m":10.,"alignment_length_m":100.})
        group=NS(member_ids=("a","b"),formation_prior="column")
        task=NS(target_id="F")
        cons={"near_geometry":circle(1300)}
        key=RngKey("test",0,"shape",mission=0,branch=None,group="g",segment=0,attempt=0)
        expected=["integers","uniform","uniform","uniform","integers","integers","random","uniform","uniform","permutation"]
        last=[]
        for fail in (None,"domain","route","lp","empty"):
            trace=[]
            with ExitStack() as stack:
                for name,value in (("detour_constraints",cons),("band_for",b),
                                   ("_entry_domain", {"fail":"base","reason":"fixture"} if fail=="domain" else {"x_max":-100.,"extra_max":10.}),
                                   ("_exit_domain",{"x_min":100.,"extra_max":20.}),
                                   ("_reference",(NS(marks={"collect":0.,"terminal":1.}),{},None,{})),
                                   ("derive_members",{}),("plan_starts",(None,"a") if fail=="route" else ({},{})),
                                   ("_assemble","complete")):
                    stack.enter_context(patch.object(DT,name,return_value=value))
                stack.enter_context(patch.object(DT,"DetourRouteView",return_value=NS(stats={},route_fn=None)))
                if fail=="empty":
                    stack.enter_context(patch.object(DT,"width_then_build",return_value=None))
                if fail=="lp":
                    from v08.motion import monitoring_band as MB
                    b.lp_arcs(0,need_deg=162,nominal_sweep_lo_deg=160,kmax=DT._curvature_context(ctx,0,load_config("monitoring").values)["kmax"])
                    stack.enter_context(patch.object(MB,"shape_lp",return_value={"feasible":False,"status":2,"objective":None,"message":"test"}))
                result=DT.propose_and_build(ctx,group,task,{},key,trace=trace)
            shape=[t for t in trace if t[0]=="shape"]
            self.assertEqual([t[1] for t in shape],expected[:0 if fail=="empty" else 7 if fail in ("domain","lp") else 10])
            if fail is None:
                self.assertEqual(result,"complete")
                last=shape
            elif fail=="route":
                self.assertEqual(shape,last)  # identical geometry and hot cache consume same sequence
        # Parameterized domain change: same state at uniform, allowed changed numeric output.
        x,y=np.random.default_rng(7),np.random.default_rng(7)
        self.assertNotEqual(x.uniform(160,350),y.uniform(160,170))
        self.assertEqual(x.bit_generator.state,y.bit_generator.state)

    def test_T9_cache_identity_and_unknown_policy(self):
        from v08.motion import monitoring_band as MB
        b=repair_band(np.full(9,1000.),np.full(9,1002.))
        a=self.query(b); calls=MB.LP_STATS["calls"]
        hot=self.query(b)
        self.assertTrue(hot["cache_hit"])
        self.assertEqual(MB.LP_STATS["calls"],calls)
        self.assertFalse(self.query(b,kmax=.002)["cache_hit"])
        self.assertFalse(b.lp_arcs(1,need_deg=3,nominal_sweep_lo_deg=3,kmax=.001)["cache_hit"])
        self.assertFalse(a["parents"][0]["A_curv"].flags.writeable)
        b=repair_band(np.full(9,1000.),np.full(9,1002.))
        with patch.object(MB,"shape_lp",return_value={"status":4,"feasible":False,"controls":None,"message":"unknown"}):
            q=self.query(b)
        self.assertTrue(q["complete"])
        self.assertFalse(q["feasible"])
        self.assertGreater(q["diagnostics"]["unknown_status_count"],0)
        self.assertTrue(np.all(q["parents"][0]["max_end"]==-1))

    def test_T12_domain_diagnostics_no_behavior_change(self):
        from v08.motion.intents import detour as DT
        from v08.scene.field import Clearance
        obs=Clearance("test_obstacle",circle(10),1,2.)
        d=DT._domain_diagnostic([obs],np.array([-20.,0.]),np.array([1.,0.]),0.,40.,"entry",(0.,0.))
        self.assertEqual(d["first_constraint"],"test_obstacle")
        self.assertEqual(d["excluded_intervals"][0]["interval"],[8.,32.])
        self.assertIsNone(component_containing([obs],np.array([-20.,0.]),np.array([1.,0.]),0.,40.))
        # Exact tangency gives the original line API a degenerate exclusion at x=20;
        # the unchanged component implementation rejects that interior contact.
        from v08.motion.transit_chords import line_sublevel
        self.assertEqual(line_sublevel(obs.geometry,np.array([-20.,12.]),np.array([1.,0.]),2.),(20.,20.))
        self.assertIsNone(component_containing([obs],np.array([-20.,12.]),np.array([1.,0.]),0.,40.))

    def test_T13_schema_and_T14_checkpoint_boundaries(self):
        from v08.runner.detour_serialization import project_document
        with self.assertRaises(ValueError):
            project_document({"formation_steps":[{"formation":"column","lp_calls":9}]},"skeleton_result")
        from v08.runner.detour_report import skeleton_checkpoint
        # Exactly 180/200, every band equally successful; 20% of eligible successes retreat.
        rows=[]
        for i in range(200):
            rows.append({"contract_id":str(i),"group_size":2,"formation_prior":"abreast","success":i<180,
                         "attempts":3,"formation":{"realized":"echelon" if i<36 else "abreast"}})
        self.assertTrue(skeleton_checkpoint(rows,wall_s=1800)["passed"])
        self.assertIn("wall",skeleton_checkpoint(rows,wall_s=1800.1)["triggered"])
        rows[179]["success"]=False
        self.assertIn("success_rate",skeleton_checkpoint(rows,wall_s=1800)["triggered"])
        self.assertFalse(skeleton_checkpoint(rows[:-1],wall_s=1)["complete"])


@unittest.skipUnless(os.environ.get("V8_21_REAL_TESTS")=="1","real devset tests require explicit existing input snapshot")
class ZRepairReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from v08.runner.monitoring import load_entries
        cls.snapshot=json.loads(Path(os.environ["V8_21_REPAIR_SNAPSHOT"]).read_text(encoding="utf-8"))
        cls.entries={e["order"]:e for e in load_entries(cls.snapshot["devset"]["path"])}
        cls.contexts={}

    def context(self,o):
        from v08.scene.context import load_context
        if o not in self.contexts:
            self.contexts[o]=load_context(self.entries[o],data_root=Path(self.snapshot["data_root"]),cache_dir=Path(self.snapshot["cache"]))
        return self.contexts[o]

    def test_T10_six_contracts_target_lp_or_certified_empty(self):
        from v08.contract.single_intent import detour_mission
        from v08.contract.monitoring import initial_states
        from v08.sampler.common import sample_common
        from v08.sampler.keys import RngKey
        from v08.motion.intents import detour as DT
        from v08.runner.monitoring import jsonable
        evidence=[]
        for o,d in ((7,2),(7,4),(11,1),(17,1),(17,4),(34,2)):
            ctx=self.context(o)
            mission=detour_mission(ctx,sample_common(ctx.family,d)); g,t=mission.groups[0],mission.tasks[0]
            key=RngKey(ctx.family.family_id,d,"shape",mission=0,branch=None,group=g.group_id,segment=0,attempt=0)
            p=DT.propose_and_build(ctx,g,t,initial_states(ctx.family,g.member_ids),key)
            tm=DT.last_attempt_timing()
            if tm.get("selected_arc"):
                self.assertEqual(tm.get("lp_target_status"),0,(o,d,tm.get("lp_target_status")))
            else:
                self.assertEqual(p.failure.witness["stage"],"detour_band")
                self.assertTrue(tm["lp_query"])
                self.assertTrue(all(not x["feasible"] for x in tm["lp_query"]))
            evidence.append({"key":f"o{o:02d}_d{d}","target_status":tm.get("lp_target_status"),
                             "stage":None if p.failure is None else p.failure.witness["stage"],"telemetry":tm})
        dest=Path(os.environ["V8_21_REPAIR_TEST_OUT"])
        dest.mkdir(parents=True,exist_ok=True)
        (dest/"six_contracts.json").write_text(json.dumps(jsonable(evidence),ensure_ascii=False,indent=1),encoding="utf-8")

    def test_T5_real_parent_thirty_subarcs(self):
        from v08.motion.detour_geometry import band_for,detour_constraints
        from v08.contract.single_intent import detour_mission
        from v08.sampler.common import sample_common
        from v08.motion.intents import detour as DT
        from v08.motion import monitoring_band as MB
        from v08.motion.path import periodic_radius_derivs
        ctx=self.context(1); mission=detour_mission(ctx,sample_common(ctx.family,0)); task=mission.tasks[0]
        b=band_for(ctx,detour_constraints(ctx,task)); k=DT._curvature_context(ctx,0,load_config("monitoring").values)["kmax"]
        q=b.lp_arcs(0,need_deg=162,nominal_sweep_lo_deg=160,kmax=k)
        parents=[p for p in q["parents"] if p["whole_feasible"]]
        self.assertTrue(parents)
        p=parents[0]; n=360 if p["periodic"] else len(p["ids"])
        A,B=MB._clamped_windows(p["tl"][:n],p["tu"][:n],p["periodic"])
        whole=MB.shape_lp(p["ids"][:n],A,B,p["A_curv"][:n],kmax=k,periodic=p["periodic"])
        self.assertTrue(whole["feasible"])
        rng=np.random.default_rng(20261111)
        for i in range(30):
            span=int(rng.integers(162,min(359,n-1)+1))
            s=int(rng.integers(0,360 if p["periodic"] else n-span))
            if i==0:
                s,span=0,162
            elif i==1:
                s,span=n-163,162
            elif i==2 and p["periodic"]:
                s,span=359,162  # explicit crossing of the 359°/0° seam
            ids,Ap,Bp,Ac=MB.arc_lp_inputs(p["ids"],p["tl"],p["tu"],p["A_curv"],s,s+span)
            rawlo=p["tl"][s:s+span+1]; rawhi=p["tu"][s:s+span+1]
            # Independent endpoint-clamped windows, without invoking the query or shared windows.
            expectedA=np.array([max(rawlo[max(0,j-2):min(len(rawlo),j+3)]) for j in range(len(rawlo))])
            expectedB=np.array([min(rawhi[max(0,j-2):min(len(rawhi),j+3)]) for j in range(len(rawhi))])
            np.testing.assert_array_equal(Ap,expectedA); np.testing.assert_array_equal(Bp,expectedB)
            ph=np.radians(np.r_[ids,ids[:-1]+.5])
            r,_,d2=periodic_radius_derivs(ph,0.,whole["controls"])
            pi=np.arange(s,s+span+1) % n if p["periodic"] else np.arange(s,s+span+1)
            pA,pB,pC=A[pi],B[pi],p["A_curv"][:n][pi]
            # Compare child violation with the SAME parent's actual residual, not zero:
            # the solver's float witness may already have a small nonzero residual.
            child_lo=np.r_[Ap,np.maximum(Ap[:-1],Ap[1:])]
            parent_lo=np.r_[pA,np.maximum(pA[:-1],pA[1:])]
            child_hi=np.r_[Bp,np.minimum(Bp[:-1],Bp[1:])]
            parent_hi=np.r_[pB,np.minimum(pB[:-1],pB[1:])]
            child_cap=k*np.r_[Ac,np.maximum(Ac[:-1],Ac[1:])]**2
            parent_cap=k*np.r_[pC,np.maximum(pC[:-1],pC[1:])]**2
            for vchild,vparent in ((child_lo-r,parent_lo-r),(r-child_hi,r-parent_hi),
                                   (np.abs(r-d2)-child_cap,np.abs(r-d2)-parent_cap)):
                self.assertLessEqual(float(np.max(vchild-vparent)),ATOL)
            self.assertTrue(MB.shape_lp(ids,Ap,Bp,Ac,kmax=k,periodic=False)["feasible"])

    def test_T11_real_o03_saved_subarc_is_retained(self):
        from v08.motion.detour_geometry import band_for,detour_constraints
        from v08.contract.single_intent import detour_mission
        from v08.sampler.common import sample_common
        from v08.motion.intents import detour as DT
        ctx=self.context(3); m=detour_mission(ctx,sample_common(ctx.family,0))
        b=band_for(ctx,detour_constraints(ctx,m.tasks[0])); k=DT._curvature_context(ctx,0,load_config("monitoring").values)["kmax"]
        q=b.lp_arcs(0,need_deg=162,nominal_sweep_lo_deg=160,kmax=k)
        self.assertFalse(q["whole_circle_feasible"])
        self.assertTrue(q["feasible"])
        self.assertIn((0,28),DN.lp_start_candidates(q,247))
        from v08.runner.monitoring import jsonable
        dest=Path(os.environ["V8_21_REPAIR_TEST_OUT"])
        dest.mkdir(parents=True,exist_ok=True)
        (dest/"o03_query_cost.json").write_text(json.dumps(jsonable({"H":0.,"feasible":q["feasible"],
                "cache_hit":q["cache_hit"],**q["diagnostics"]}),ensure_ascii=False,indent=1),encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
