"""Frozen scalar coverage oracle and boundary cases for geometry acceleration."""
import math
from concurrent.futures import ProcessPoolExecutor
import unittest

import numpy as np

from swarm_sim.mission_evaluation import EPS, _covered_cells, _grid


def scalar_covered(centers, points, segments, radius):
    # Deliberately independent of the new helper and its distance routine.
    def distance(c, a, b):
        delta = [b[i] - a[i] for i in range(2)]
        length2 = sum(x * x for x in delta)
        weight = max(0.0, min(1.0, sum((c[i] - a[i]) * delta[i]
                     for i in range(2)) / length2)) if length2 else 0
        return math.hypot(*(c[i] - a[i] - weight * delta[i] for i in range(2)))
    return {i for i, c in enumerate(centers) if
            any(math.dist(c, p) <= radius + EPS for p in points) or
            any(distance(c, a, b) <= radius + EPS for a, b in segments)}


class CoverageGeometryTests(unittest.TestCase):
    def test_empty_evidence_and_grid(self):
        self.assertEqual(_covered_cells([(0, 0)], [], [], 1), set())
        self.assertEqual(_covered_cells([], [(0, 0)], [], 1), set())

    def test_points_inclusive_boundary_and_adjacent_floats(self):
        r = 2.0
        t = r + EPS
        centers = [(math.nextafter(t, 0), 0), (t, 0),
                   (math.nextafter(t, math.inf), 0), (-t, 0), (0, -t)]
        self.assertEqual(_covered_cells(centers, [(0, 0)], [], r), {0, 1, 3, 4})

    def test_segment_boundary_and_endpoint_clamp(self):
        t = 1 + EPS
        centers = [(1, t), (1, math.nextafter(t, math.inf)),
                   (2 + t, 0), (-t, 0), (1, 0)]
        self.assertEqual(_covered_cells(centers, [], [((0, 0), (2, 0))], 1), {0, 2, 3, 4})

    def test_gap_is_not_a_connecting_segment(self):
        self.assertEqual(_covered_cells([(0, 0)], [(-5, 0), (5, 0)], [], .1), set())
        self.assertEqual(_covered_cells([(0, 0)], [], [((-5, 0), (5, 0))], .1), {0})

    def test_zero_length_segments(self):
        centers = [(0, 0), (1, 0), (3, 0)]
        self.assertEqual(_covered_cells(centers, [], [((0, 0), (0, 0))], 1), {0, 1})

    def test_unchanged_nonintegral_grid(self):
        centers, grid = _grid(dict(width_m=2.5, height_m=1.5,
                                   min_east_m=0, min_north_m=0), 1)
        self.assertEqual(centers, [(5/12, .375), (5/12, 1.125), (1.25, .375),
                                   (1.25, 1.125), (25/12, .375), (25/12, 1.125)])
        self.assertEqual((grid['nx'], grid['ny'], grid['cells']), (3, 2, 6))

    def test_random_evidence_matches_frozen_scalar_oracle(self):
        rng = np.random.default_rng(2026101204)
        for scale in (1e-150, 1e-5, 1., 100., 1e10, 1e150):
            for _ in range(8):
                centers = (rng.normal(size=(31, 2)) * scale).tolist()
                points = (rng.normal(size=(23, 2)) * scale).tolist()
                segments = (rng.normal(size=(17, 2, 2)) * scale).tolist()
                radius = .15 * scale
                expected = scalar_covered(centers, points, segments, radius)
                self.assertEqual(_covered_cells(centers, points, segments, radius), expected)

    def test_rotated_tangent_and_translated_near_boundary(self):
        for shift in (0., 1e5, -1e8):
            for angle in np.linspace(0, 2 * math.pi, 19):
                a = (shift, shift)
                d = (math.cos(angle), math.sin(angle))
                b = (shift + 3 * d[0], shift + 3 * d[1])
                centers = [(shift + d[0] - k * d[1], shift + d[1] + k * d[0])
                           for k in (1 + EPS, math.nextafter(1 + EPS, 0),
                                     math.nextafter(1 + EPS, math.inf))]
                self.assertEqual(_covered_cells(centers, [], [(a, b)], 1),
                                 scalar_covered(centers, [], [(a, b)], 1))

    def test_evidence_order_and_duplicates_do_not_change_union(self):
        centers = [(x, y) for x in range(-3, 4) for y in range(-3, 4)]
        points = [(-1, 1), (2, -2)]
        segments = [((-3, -3), (3, 3)), ((0, 1), (0, 1))]
        expected = scalar_covered(centers, points, segments, .5)
        self.assertEqual(_covered_cells(centers, points[::-1] * 3, segments[::-1] * 2, .5), expected)

    def test_one_and_two_processes_match_scalar_results(self):
        centers = [(x / 3, y / 7) for x in range(-9, 10) for y in range(-9, 10)]
        points = [(-1, 1), (2, -2)]
        segments = [((-3, -3), (3, 3)), ((0, 1), (0, 1))]
        radii = [0., .25, 1., 3.]
        expected = [scalar_covered(centers, points, segments, r) for r in radii]
        for workers in (1, 2):
            with ProcessPoolExecutor(max_workers=workers) as pool:
                jobs = [pool.submit(_covered_cells, centers, points, segments, r) for r in radii]
                self.assertEqual([job.result() for job in jobs], expected)


if __name__ == '__main__':
    unittest.main()
