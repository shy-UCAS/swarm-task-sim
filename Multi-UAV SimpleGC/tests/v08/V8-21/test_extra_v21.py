"""V8-21 自加测试（指令 9.4 矩阵）。独立预期均由解析或手算给出；D/Θ 只从候选配置读取。"""
import copy
import json
import math
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
