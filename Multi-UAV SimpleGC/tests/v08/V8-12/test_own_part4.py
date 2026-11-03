"""自加测试（不属于预置测试）：第 4 部分运行器的纯函数——路径守卫、ρ 的 CV、多样性选族、汇总。"""
import json
import math
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from v08.runner import monitoring as run
from v08.runner import monitoring_report as R


class TestPathGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v812guard_")).resolve()
        self.repo = self.tmp / "repo"
        self.frozen = self.tmp / "Simulation-fe-s3"
        self.data = self.tmp / "SwarmData"
        for p in (self.repo, self.frozen, self.data, self.tmp / "ok"):
            p.mkdir()

    def guard(self, path, **kw):
        return run.guard_path(path, label="输出", repo_root=self.repo, frozen_roots=[self.frozen],
                              data_root=self.data, **kw)

    def test_allowed_outside(self):
        self.guard(self.tmp / "ok" / "out" / "plan", must_not_exist=True)

    def test_rejects_repo_frozen_data(self):
        for bad in (self.repo / "x", self.frozen / "y" / "z", self.data / "cache", self.repo):
            with self.assertRaises(run.PathRejected, msg=str(bad)):
                self.guard(bad)

    def test_rejects_v07_component(self):
        with self.assertRaises(run.PathRejected):
            self.guard(self.tmp / "ok" / "v07_first_edition" / "out")

    def test_rejects_existing_output(self):
        (self.tmp / "ok" / "exists").mkdir()
        with self.assertRaises(run.PathRejected):
            self.guard(self.tmp / "ok" / "exists", must_not_exist=True)

    def test_rejects_junction_into_forbidden(self):
        link = self.tmp / "ok" / "link"
        try:
            if os.name == "nt":
                subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(self.repo)], check=True,
                               capture_output=True)
            else:
                os.symlink(self.repo, link)
        except Exception as exc:
            self.skipTest(f"无法创建联接：{exc!r}")
        with self.assertRaises(run.PathRejected):
            self.guard(link / "out")

    def test_rejects_junction_to_v07_target(self):
        target = self.tmp / "elsewhere" / "v07_scene"
        target.mkdir(parents=True)
        link = self.tmp / "ok" / "lnk"
        try:
            if os.name == "nt":
                subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
            else:
                os.symlink(target, link)
        except Exception as exc:
            self.skipTest(f"无法创建联接：{exc!r}")
        with self.assertRaises(run.PathRejected):
            self.guard(link / "out")


class TestRhoCv(unittest.TestCase):
    def test_exact_matches_dense_quadrature(self):
        rng = np.random.default_rng(7)
        for K in (4, 5, 8):
            coef = rng.normal(0.0, 20.0, K)
            rho0 = 300.0
            for lo, hi in ((0.0, 2 * math.pi), (0.7, 3.9), (5.5, 9.0)):
                mean, var, _ = R.rho_moments(rho0, coef, lo, hi)
                from v08.motion.path import periodic_radius
                phi = np.linspace(lo, hi, 400001)
                r = periodic_radius(phi, rho0, coef)
                m2 = np.trapezoid(r, phi) / (hi - lo)
                v2 = np.trapezoid(r * r, phi) / (hi - lo) - m2 * m2
                self.assertAlmostEqual(mean, m2, places=6)
                self.assertAlmostEqual(var, v2, places=4)

    def test_constant_radius_has_zero_cv(self):
        self.assertAlmostEqual(R.rho_cv(250.0, [0, 0, 0, 0], 0.0, 2 * math.pi)["cv"], 0.0, places=12)

    def test_discrete_close_to_exact(self):
        coef = [10.0, -8.0, 5.0, -7.0, 3.0]
        exact = R.rho_cv(400.0, coef, 0.0, 2 * math.pi)["cv"]
        self.assertAlmostEqual(R.rho_cv_discrete(400.0, coef, 0.0, 2 * math.pi), exact, places=4)


class TestSelectionAndSerialization(unittest.TestCase):
    def entries(self):
        fac = [2, 2, 1, 3, 1, 1, 2, 3, 1, 2, 2, 1, 3]
        return [{"order": i + 1, "facility_count": f, "family_id": f"f{i}"} for i, f in enumerate(fac)]

    def test_diversity_selection_covers_and_is_by_order(self):
        sel = run.select_diversity_families(self.entries())
        self.assertEqual(len(sel), 10)
        orders = [e["order"] for e in sel]
        self.assertEqual(orders, sorted(orders))
        self.assertEqual({e["facility_count"] for e in sel}, {1, 2, 3})
        # 1/2/3 设施各自最早的一族：order 1（2）、3（1）、4（3）必在其中
        self.assertTrue({1, 3, 4} <= set(orders))
        self.assertEqual(orders, list(range(1, 11)))   # 其余按 order 补足

    def test_canonical_json_is_stable_and_total(self):
        a = {"b": np.float64(1.5), "a": np.array([1.0, math.nan]), "c": (1, 2), 3: float("inf")}
        x = run.canonical_json(a)
        y = run.canonical_json({"c": [1, 2], "a": [1.0, "nan"], "b": 1.5, 3: "inf"})
        self.assertEqual(x, y)
        json.loads(x)


class TestSummary(unittest.TestCase):
    def rec(self, order, draw, fac, ok, net, n=2):
        r = {"contract_id": f"o{order:02d}_d{draw}", "family_id": f"f{order}", "order": order, "draw_index": draw,
             "facility_count": fac, "group_size": n, "group_id": "g0", "target_id": "facility_01", "success": ok,
             "attempts": 1 if ok else 20,
             "attempt_log": [{"attempt": 0, "ok": ok, "stage": None if ok else "separation", "repairs": [],
                              "witness": None, "built_candidate": True}],
             "planning": {"prewarm_s": 0.1, "total_s": net, "cold_in_planning_s": 0.0, "net_s": net}}
        if ok:
            r["failure"] = None
            r["metrics"] = {"nontarget_warning_entered": False, "nontarget_facilities": fac - 1,
                            "nontarget_warning_by_facility": {}, "formation_prior": "column",
                            "formation_realized": "column", "formation_start": "column",
                            "formation_differs_from_prior": False, "formation_retreated": False, "retreat_chain": ["column"],
                            "repair_kinds": [], "boundary_crossings_per_member": {"u1": 0}, "topology": "loop",
                            "topology_prior_draw": "loop", "topology_forced": False, "nominal_duration_s": 1000.0}
        else:
            r["failure"] = {"code": "budget_exhausted", "reason": "x", "feasible_set": "random_construction",
                            "witness": {}, "exact_nonempty": None}
        return r

    def test_denominators_include_failures_and_missing(self):
        recs = [self.rec(i, d, 1 + (i % 3), (i + d) % 4 != 0, 10.0 + i) for i in range(1, 5) for d in range(5)]
        s = R.build_summary(recs, [], families=[], expected_contracts=25, expected_families=5, diversity_expected=True)
        self.assertEqual(s["contracts"], 25)
        self.assertEqual(s["missing"], 5)
        self.assertFalse(s["completed"])
        self.assertEqual(s["successes"], sum(1 for r in recs if r["success"]))
        self.assertEqual(sum(v["contracts"] for v in s["by_facilities"].values()), 20)
        chk = R.checkpoint(s)
        self.assertFalse(chk.complete)
        self.assertTrue(chk.incomplete_reasons)


if __name__ == "__main__":
    unittest.main()
