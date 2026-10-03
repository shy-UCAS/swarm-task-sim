"""r1.2 passage/sample regression, with the retained M01/M02/M03 cases."""

import copy
import functools
import unittest
from unittest import mock

from swarm_sim.ac4_timing import (MATCH_TOLERANCE_M, ORDERED_ROUTE_PROGRESS_VERSION,
    ORDERED_ROUTE_PROGRESS_V2_VERSION, VISIT_EXIT_TOLERANCE_M, evaluate_ac4_timing_v3,
    ordered_route_progress, ordered_route_progress_v2)
import test_wp_m_progress as original


class OriginalProgressCasesV2(original.OrderedProgressTests):
    """Apply the unchanged M01/M02/M03 fixtures and assertions to the new API."""

    def setUp(self):
        for name, replacement in (
                ("ordered_route_progress", ordered_route_progress_v2),
                ("ORDERED_ROUTE_PROGRESS_VERSION", ORDERED_ROUTE_PROGRESS_V2_VERSION),
                ("evaluate_ac4_timing_v3", functools.partial(evaluate_ac4_timing_v3,
                    progress_mapping_version=ORDERED_ROUTE_PROGRESS_V2_VERSION))):
            patcher = mock.patch.object(original, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)


class FirstPassageV2Tests(unittest.TestCase):
    def test_later_lap_closer_corner_never_steals_first_lap(self):
        route, lap_indices = original.loop((0, 0), "cw", 2)
        rows, nominal = original.perfect_trace((0, 0), route)
        # The first corner's closest *sample* now misses by 0.5 m; the
        # second lap hits it exactly. A global minimum would steal lap two.
        rows = [(stamp, [position[0], .8, position[2]]) if stamp == 10. else (stamp, position)
                for stamp, position in rows]
        result = ordered_route_progress_v2(rows, route, nominal, start_s=0.,
            end_s=rows[-1][0], max_gap_s=1., start_point=original.point(0, 0),
            lap_node_indices=lap_indices)
        self.assertTrue(result["evidence_complete"], result["issues"])
        self.assertEqual(result["nodes"][1]["actual_s"], 9.5)
        self.assertEqual(result["nodes"][5]["actual_s"], 46.)
        self.assertEqual(result["per_agent_laps_observed"], 2)
        self.assertEqual(result["nodes"][1]["minimum_distance_m"], .5)
        self.assertEqual(result["nodes"][5]["minimum_distance_m"], 0.)

    def test_overlapping_corner_and_entry_passage_uses_current_lap(self):
        # Release is only 2 m past a corner. Return to the release coordinate
        # enters its 3 m ball before the corner matches, exactly the VP1 bug.
        route = [original.point(*xy) for _ in range(2)
                 for xy in ((10, 0), (10, 8), (0, 8), (0, 0), (2, 0))]
        rows, nominal = original.perfect_trace((2, 0), route)
        kwargs = dict(start_s=0., end_s=rows[-1][0], max_gap_s=1.,
                      start_point=original.point(2, 0), lap_node_indices=[4, 9])
        retained_v1 = ordered_route_progress(rows, route, nominal, **kwargs)
        result = ordered_route_progress_v2(rows, route, nominal, **kwargs)
        self.assertFalse(retained_v1["evidence_complete"])
        self.assertEqual(retained_v1["version"], ORDERED_ROUTE_PROGRESS_VERSION)
        self.assertTrue(result["evidence_complete"], result["issues"])
        self.assertEqual(result["nodes"][5]["actual_s"], 36.)
        self.assertLess(result["node_evidence"][4]["visit_interval_s"][0],
                        result["nodes"][4]["actual_s"])
        self.assertEqual(result["per_agent_laps_observed"], 2)

    def test_exit_hysteresis_keeps_boundary_jitter_in_one_passage(self):
        rows = [(float(t), [x, 0., 8.]) for t, x in enumerate((0, 8, 6.8, 9.5, 6, 10))]
        result = ordered_route_progress_v2(rows, [original.point(10)], [5.],
            start_s=0., end_s=5., max_gap_s=1., start_point=original.point(0))
        self.assertEqual(result["nodes"][1]["actual_s"], 3.)
        self.assertEqual(result["node_evidence"][0]["visit_interval_s"], [1., 3.])
        self.assertEqual(result["match_tolerance_m"], 3.)
        self.assertEqual(result["visit_exit_tolerance_m"], 3.5)
        self.assertEqual(VISIT_EXIT_TOLERANCE_M, 3.5)

    def test_closest_sample_not_line_projection_or_synthetic_bound(self):
        rows = [(0., [0., 0., 8.]), (2., [2., 0., 8.]), (4., [4., 0., 8.])]
        result = ordered_route_progress_v2(rows, [original.point(1)], [1.],
            start_s=.5, end_s=3.5, max_gap_s=2., start_point=original.point(.5))
        self.assertEqual(result["nodes"][1]["actual_s"], 2.)
        self.assertEqual(result["nodes"][1]["minimum_distance_m"], 1.)
        self.assertEqual(result["nodes"][1]["closest_time_interval_s"], [2., 2.])

    def test_tolerance_is_fixed_and_inputs_are_not_mutated(self):
        route, lap_indices = original.loop((0, 0), "cw", 2)
        rows, nominal = original.perfect_trace((0, 0), route)
        before = copy.deepcopy((rows, route, nominal))
        for tolerance in (2.5, 3.1, float("nan")):
            with self.subTest(tolerance=tolerance), self.assertRaises(ValueError):
                ordered_route_progress_v2(rows, route, nominal, start_s=0.,
                    end_s=rows[-1][0], max_gap_s=1., match_tolerance_m=tolerance)
        ordered_route_progress_v2(rows, route, nominal, start_s=0.,
            end_s=rows[-1][0], max_gap_s=1., lap_node_indices=lap_indices)
        self.assertEqual((rows, route, nominal), before)
        self.assertEqual(MATCH_TOLERANCE_M, 3.)

    def test_unknown_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported_progress_mapping_version"):
            evaluate_ac4_timing_v3({}, {}, [], {}, 0., progress_mapping_version="unknown")


if __name__ == "__main__":
    unittest.main()
