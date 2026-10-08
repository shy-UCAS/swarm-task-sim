"""Trajectory evidence and truncation guards; no simulator dependency."""

import copy
import unittest

from swarm_sim.rapid_passage import measure_passage, evaluate_channel, THRESHOLDS


REGION = dict(id="R1", min_east_m=0., min_north_m=0., width_m=30., height_m=20.)


def trajectory(points, speed=2., step=.1):
    import math
    rows = [(0., [*points[0], 8.])]
    stamp = 0.
    for a, b in zip(points, points[1:]):
        duration = math.dist(a, b)/speed
        count = max(1, math.ceil(duration/step))
        for index in range(1, count+1):
            ratio = index/count
            rows.append((stamp+duration*ratio, [a[0]+ratio*(b[0]-a[0]), a[1]+ratio*(b[1]-a[1]), 8.]))
        stamp += duration
    return rows


class RapidPassageTests(unittest.TestCase):
    def test_measured_straight_crossing_four_sides(self):
        for first, last, side, opposite in (((-6, 10), (36, 10), "west", "east"),
                ((36, 10), (-6, 10), "east", "west"), ((15, -6), (15, 26), "south", "north"),
                ((15, 26), (15, -6), "north", "south")):
            with self.subTest(side=side):
                item = measure_passage(trajectory([first, last]), REGION)
                self.assertTrue(item["success"])
                self.assertEqual((item["entry_side"], item["exit_side"]), (side, opposite))
                self.assertLess(item["max_cross_track_m"], 1e-8)

    def test_completed_window_with_truncated_geometry_cannot_pass(self):
        rows = trajectory([(-6, 10), (36, 10)])
        for end in (20, 100, 150):
            self.assertIsNot(measure_passage(rows[:end], REGION)["success"], True)
        self.assertIsNone(measure_passage(rows, REGION, complete_window=False)["success"])

    def test_incomplete_clock_trajectory_not_planned_success(self):
        rows = trajectory([(-6, 10), (36, 10)])
        missing = rows[:30] + rows[40:]
        self.assertIsNone(measure_passage(missing, REGION)["success"])
        self.assertIsNone(measure_passage([], REGION)["entry_side"])

    def test_region_dwell_and_loop_rejected(self):
        rows = trajectory([(-6, 10), (15, 10)])
        stamp = rows[-1][0]
        rows.extend((stamp+index*.1, [15., 10., 8.]) for index in range(1, 21))
        tail = trajectory([(15, 10), (36, 10)])
        rows.extend((t+stamp+2., p) for t, p in tail[1:])
        result = measure_passage(rows, REGION)
        self.assertFalse(result["conditions"]["no_dwell"])
        self.assertGreater(result["inside_dwell_s"], THRESHOLDS["max_low_speed_duration_s"])
        loop = trajectory([(-6, 10), (10, 10), (20, 10), (20, 15), (10, 15), (10, 10), (36, 10)])
        self.assertFalse(measure_passage(loop, REGION)["conditions"]["no_loop"])

    def test_recon_and_perimeter_synthetic_cross_negatives(self):
        paths = [[(-6, 3), (30, 3), (30, 9), (0, 9), (0, 15), (30, 15), (36, 15)],
                 [(-6, 0), (0, 0), (30, 0), (30, 20), (0, 20), (0, 0), (36, 0)]]
        for path in paths:
            self.assertFalse(measure_passage(trajectory(path), REGION)["success"])

    def test_entry_side_comes_from_actual_crossing_not_earlier_exterior(self):
        region = dict(REGION, width_m=40., height_m=30.)
        rows = trajectory([(-5, 15), (-5, 31.5), (20, 31.5), (20, 30), (45, 11.25)])
        result = measure_passage(rows, region)
        self.assertIsNot(result["success"], True)
        self.assertNotEqual(result["entry_side"], "west")
        # A boundary skim is not evidence of entering the region interior.
        self.assertFalse(measure_passage(trajectory([(-6, 0), (36, 0)]), REGION)["success"])

    def test_validator_ignores_pattern_and_return_crossing(self):
        rows = trajectory([(-6, 10), (36, 10)])
        end = rows[-1][0]
        returning = trajectory([(36, 10), (-6, 10)])
        rows.extend((t+end, p) for t, p in returning[1:])
        scene = dict(vehicles=[{"id": "a"}], max_gap_s=.5, task_spec=dict(
            scenario={"regions": [REGION]}, mission={"target_region_id": "R1"}))
        windows = [dict(agent_id="a", semantic_phase="transit", service_enabled=True,
                        start_s=0., end_s=end, complete_execution_window=True)]
        baseline = evaluate_channel(scene, {"a": rows}, windows, {})
        self.assertTrue(baseline["metrics"]["rapid_passage"]["success"])
        for pattern in ("line_abreast", "column", "invalid-pattern"):
            alternate = copy.deepcopy(scene)
            alternate["task_spec"]["flight_pattern"] = pattern
            self.assertEqual(evaluate_channel(alternate, {"a": rows}, windows, {}), baseline)
        windows[0]["complete_execution_window"] = False
        self.assertIsNone(evaluate_channel(scene, {"a": rows}, windows, {})["metrics"]["rapid_passage"]["success"])


if __name__ == "__main__":
    unittest.main()
