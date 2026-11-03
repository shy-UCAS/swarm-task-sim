"""执行方自加测试（第 2 部分）：用 shapely 和暴力采样交叉验证精确几何；真实场景上检验保守性。
这些测试不属于预置测试；独立预期来自 shapely 的距离与逐点采样。"""
import json
import math
import os
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Point, Polygon

from v08.scene.context import load_context
from v08.scene.exact import (chord_sdf_range, clearance_values, expand, inset_convex, polygon_centroid,
                             polyline_clearance, signed_distance)
from v08.scene.field import Clearance, build_distance_field, conservative_cells


def convex_polygon(rng, n):
    ang = np.sort(rng.uniform(0, 2 * np.pi, n))
    r = rng.uniform(50, 120)
    v = np.c_[r * np.cos(ang), r * np.sin(ang)] + rng.uniform(-30, 30, 2)
    return Polygon(v).convex_hull


def sh_sdf(poly, b, p):
    pt = Point(p)
    d = poly.exterior.distance(pt)
    inside = poly.contains(pt)
    return (-d if inside else poly.distance(pt)) - b


class TestExactAgainstShapely(unittest.TestCase):
    def test_sdf_matches_shapely(self):
        rng = np.random.default_rng(1)
        for _ in range(30):
            poly = convex_polygon(rng, int(rng.integers(3, 8)))
            if poly.geom_type != "Polygon" or len(poly.exterior.coords) < 4:
                continue
            verts = [list(c) for c in poly.exterior.coords][:-1]
            b = float(rng.choice([0.0, 25.0]))
            geom = {"type": "BufferedPolygon" if b else "Polygon", "vertices_m": verts}
            if b:
                geom["buffer_m"] = b
            pts = rng.uniform(-300, 300, (40, 2))
            got = signed_distance(geom, pts)
            want = np.array([sh_sdf(poly, b, p) for p in pts])
            np.testing.assert_allclose(got, want, atol=1e-9)

    def test_chord_range_matches_sampling(self):
        rng = np.random.default_rng(2)
        t = np.linspace(0, 1, 4001)
        for _ in range(40):
            poly = convex_polygon(rng, int(rng.integers(3, 8)))
            if poly.geom_type != "Polygon":
                continue
            verts = [list(c) for c in poly.exterior.coords][:-1]
            geom = {"type": "BufferedPolygon", "vertices_m": verts, "buffer_m": 10.0}
            a, b = rng.uniform(-250, 250, 2), rng.uniform(-250, 250, 2)
            pts = a[None] + t[:, None] * (b - a)[None]
            s = signed_distance(geom, pts)
            lo, hi, exact = chord_sdf_range(geom, a[None], b[None])
            self.assertAlmostEqual(float(hi[0]), float(s.max()), delta=1e-9, msg="最大值在端点，必须精确")
            if exact[0]:
                self.assertAlmostEqual(float(lo[0]), float(s.min()), delta=0.05, msg="不相交时最小值精确")
            else:
                self.assertLessEqual(float(lo[0]), 0.0 - 10.0 + 1e-9, "相交时下界必须落在形状内部一侧")
            circ = {"type": "Circle", "center_m": list(rng.uniform(-100, 100, 2)), "radius_m": float(rng.uniform(20, 90))}
            s = signed_distance(circ, pts)
            lo, hi, exact = chord_sdf_range(circ, a[None], b[None])
            self.assertTrue(exact[0])
            self.assertAlmostEqual(float(lo[0]), float(s.min()), delta=0.05)
            self.assertAlmostEqual(float(hi[0]), float(s.max()), delta=1e-9)

    def test_polyline_clearance_detects_grazing(self):
        # 圆心(0,0)、半径 100 的外部约束 >= 30：直线从(-200,120)到(200,120)最近距离恰为 120-100=20 < 30
        circle = {"type": "Circle", "center_m": [0.0, 0.0], "radius_m": 100.0}
        xy = np.array([[-200.0, 120.0], [200.0, 120.0]])
        m = polyline_clearance(circle, xy, sense=1, minimum_m=30.0)
        self.assertAlmostEqual(float(m[0]), -10.0, delta=1e-9, msg="两端点都远，但弦中点最近：不能只验节点")

    def test_inset_and_centroid(self):
        sq = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        inner = inset_convex(sq, 35.0)
        np.testing.assert_allclose(sorted(map(tuple, inner)), sorted([(35.0, 35.0), (65.0, 35.0), (65.0, 65.0), (35.0, 65.0)]), atol=1e-9)
        self.assertEqual(polygon_centroid(sq), (50.0, 50.0))
        tri = [[0.0, 0.0], [6.0, 0.0], [0.0, 3.0]]
        np.testing.assert_allclose(polygon_centroid(tri), (2.0, 1.0), atol=1e-12)


@unittest.skipUnless(os.environ.get("V8_12_DATA_ROOT"), "需要 V8_12_DATA_ROOT")
class TestFieldOnRealScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo = Path.cwd().parent
        cls.entries = json.loads((repo / "docs/v08/V8-03/devset_v08.json").read_text(encoding="utf-8"))
        cls.root = Path(os.environ["V8_12_DATA_ROOT"])

    def constraints(self, ctx):
        P = ctx.params
        out = [Clearance("world", ctx.world, -1, P["world_margin_m"])]
        out += [Clearance("obs:" + i, g, 1, P["obstacle_margin_m"]) for i, g in ctx.obstacles]
        out += [Clearance("alert:" + f.id, f.layers["alert"], 1, P["forbidden_margin_m"]) for f in ctx.facilities]
        return tuple(out)

    def test_feasible_points_satisfy_exact_constraints(self):
        biggest = max(self.entries, key=lambda e: e["map_side_m"])
        smallest = min(self.entries, key=lambda e: (e["facility_count"], e["map_side_m"]))
        with tempfile.TemporaryDirectory() as cache:
            for entry in (biggest, smallest):
                ctx = load_context(entry, data_root=self.root, cache_dir=cache)
                cons = self.constraints(ctx)
                t0 = time.perf_counter()
                field = ctx.field("static", cons)
                [field.values[c.name] for c in cons]
                cold = time.perf_counter() - t0
                ctx2 = load_context(entry, data_root=self.root, cache_dir=cache)
                t0 = time.perf_counter()
                ctx2.field("static", cons)
                warm = time.perf_counter() - t0
                print(f"\n[{entry['family_id']} 边长{entry['map_side_m']} m 栅格{field.nx}x{field.ny}] 冷 {cold:.2f} s 热 {warm:.2f} s "
                      f"缓存 {ctx.cache_stats()} / {ctx2.cache_stats()}")
                rng = np.random.default_rng(3)
                x0, y0, x1, y1 = ctx.bounds
                pts = np.c_[rng.uniform(x0, x1, 20000), rng.uniform(y0, y1, 20000)]
                ok = field.feasible(pts)
                self.assertGreater(int(ok.sum()), 100)
                for c in cons:
                    exact = clearance_values(c.geometry, pts[ok], sense=c.sense, minimum_m=c.minimum_m)
                    self.assertGreaterEqual(float(exact.min()), 0.0, f"{c.name}: 保守下界不得放过精确不可行点")
                cells = conservative_cells(field)
                self.assertGreater(len(cells), 0)
                samp = cells.sample(np.random.default_rng(4), 3000)
                for c in cons:
                    exact = clearance_values(c.geometry, samp, sense=c.sense, minimum_m=c.minimum_m)
                    self.assertGreaterEqual(float(exact.min()), 0.0, f"{c.name}: 保守单元内的点必须精确可行")
                # 保守集合的面积不应大于精确可行面积的估计（蒙特卡洛，容许 3σ）
                ex = np.ones(20000, bool)
                for c in cons:
                    ex &= clearance_values(c.geometry, pts, sense=c.sense, minimum_m=c.minimum_m) >= 0
                total = (x1 - x0) * (y1 - y0)
                est, sig = ex.mean() * total, math.sqrt(max(ex.mean() * (1 - ex.mean()), 1e-12) / 20000) * total
                self.assertLessEqual(cells.area, est + 3 * sig + 1.0, "保守集合面积不得超过精确可行面积")
                self.assertGreater(cells.area, 0.5 * est, "保守集合不应丢掉一半以上的可行面积")


if __name__ == "__main__":
    unittest.main()
