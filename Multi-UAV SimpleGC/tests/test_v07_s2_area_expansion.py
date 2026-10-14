"""Strip load balance and approach evidence without the frozen slice planner."""
import unittest
import numpy as np
from task_v07.expansion.area_search import balanced_partitions, planned_core_distance, heading_before_distance


class AreaExpansionTests(unittest.TestCase):
    def test_length_balance_does_not_split_by_strip_count(self):
        # Equal strip counts would yield 190 versus 30; minimax is 100 versus 120.
        self.assertEqual(balanced_partitions([100, 90, 10, 20], 2), [[0], [1, 2, 3]])

    def test_all_members_have_work_and_all_strips_covered(self):
        result = balanced_partitions([30, 60, 45, 75, 10, 50, 90], 4)
        self.assertEqual([i for block in result for i in block], list(range(7)))
        self.assertEqual(len(result), 4)
        self.assertTrue(all(result))
        with self.assertRaises(ValueError):
            balanced_partitions([1, 2], 3)

    def test_first_scan_entry_counts_early_approach_crossing(self):
        area = {"type": "Circle", "center_m": [0., 0.], "radius_m": 20.}
        path = np.array([[-200., 0.], [100., 0.], [100., 100.], [0., 0.]])
        length = planned_core_distance(path, area)
        self.assertAlmostEqual(length, 180.)
        self.assertAlmostEqual(heading_before_distance(path, length), 0.)

    def test_opposite_final_approaches_have_opposite_headings(self):
        a = np.array([[-300., 0.], [100., 0.]])
        b = a[::-1]
        self.assertAlmostEqual(heading_before_distance(a, 250.), 0.)
        self.assertAlmostEqual(heading_before_distance(b, 250.), 180.)


if __name__ == "__main__":
    unittest.main()
