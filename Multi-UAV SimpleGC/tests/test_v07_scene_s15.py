"""S15 instruction tests: prescribed constants, tolerances and fixed seeds."""
import math
import random
import unittest

from scene_v07.layout_s15 import base_distance, bisect_t, load_layout_config, signed_gap
from scene_v07.sampling import _contour, _move


def circle(x, y, radius):
    return {"type": "Circle", "center_m": [x, y], "radius_m": radius}


def square(x, y, half):
    return {"type": "Polygon", "vertices_m": [[x-half, y-half], [x+half, y-half],
                                                [x+half, y+half], [x-half, y+half]]}


class ExactLayoutTests(unittest.TestCase):
    def test_hand_calculated_distances(self):
        cases = [(circle(0, 0, 2), circle(10, 0, 3), 5),
                 (circle(10, 0, 2), square(0, 0, 1), 7),
                 (square(0, 0, 1), square(5, 6, 1), 5)]
        for a, b, expected in cases:
            self.assertAlmostEqual(base_distance(a, b), expected, delta=1e-9)
            self.assertAlmostEqual(base_distance(b, a), expected, delta=1e-9)
        self.assertEqual(base_distance(circle(0, 0, 2), square(0, 0, 1)), 0)

    def test_200_bisections_attain_minimal_translation(self):
        rng, cfg = random.Random(15002), load_layout_config()[0]
        for _ in range(200):
            a, b = _contour(rng, True), _contour(rng, True)
            theta, target = rng.uniform(0, 2*math.pi), rng.uniform(1, 4000)
            t = bisect_t(a, b, theta, target, cfg)
            move = lambda distance: _move(b, [distance*math.cos(theta), distance*math.sin(theta)])
            self.assertAlmostEqual(base_distance(a, move(t)), target, delta=1e-3)
            self.assertLess(base_distance(a, move(t-.01)), target)

    def test_1000_r2_pairs_imply_ordered_r1_lower_bound(self):
        rng = random.Random(15004)
        for _ in range(1000):
            wi, wj = rng.uniform(300, 800), rng.uniform(300, 800)
            d2i, d2j = rng.uniform(200, 550), rng.uniform(200, 550)
            d1i, d1j = d2i+wi, d2j+wj
            g = rng.uniform(-.2*min(wi, wj), 1000)
            a, b = circle(0, 0, 40), circle(d1i+d1j+g+100, 0, 60)
            self.assertGreaterEqual(signed_gap(a, d2i, b, d1j), .8*wi-1e-6)
            self.assertGreaterEqual(signed_gap(b, d2j, a, d1i), .8*wj-1e-6)

    def test_r2_boundary_independent_checker(self):
        # Integration assertion is run after the S15-3 checker commit.
        from scene_v07.checks import check_layout_s15
        for delta, expected in ((.01, False), (-.01, True)):
            facilities = [{"id": "a", "geometry": circle(1500, 1500, 40)},
                          {"id": "b", "geometry": circle(1500+80+1400-100+delta, 1500, 40)}]
            layers = {f["id"]: {"alert": {"offset_m": 200}, "warning": {"offset_m": 700}} for f in facilities}
            codes = [i["code"] for i in check_layout_s15(facilities, layers, "linear", (0, 0, 5000, 5000))]
            self.assertEqual("s15_warning_overlap_exceeds_bound" in codes, expected)
            if not expected:
                self.assertEqual(codes, [])


if __name__ == "__main__":
    unittest.main()
