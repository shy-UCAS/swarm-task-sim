"""WP-T: optional timing cap and the patrol arc-length prefilter boundary."""

import copy
import json
import math
import unittest
from pathlib import Path

from swarm_sim.generation import canonical_hash
from swarm_sim.mission_v3 import normalize_v3
from swarm_sim.route_planning import patrol_spacing_prefilter, time_aware_phase_clearance
from swarm_sim.tasks import compile_task


ROOT = Path(__file__).resolve().parents[1]


def point(east, north=0):
    return dict(east_m=float(east), north_m=float(north), up_m=8.0)


def separated_routes():
    return {"a": point(0), "b": point(100)}, {"a": [point(10)], "b": []}


class TimingCapTests(unittest.TestCase):
    def test_T01_cap_floor_and_uncapped_legacy_report(self):
        starts, routes = separated_routes()
        old = time_aware_phase_clearance(starts, routes, 1, 5,
                                         dict(min_s=3, fraction_of_phase=.5), 2, 1)
        capped = time_aware_phase_clearance(starts, routes, 1, 5,
                                            dict(min_s=3, fraction_of_phase=.5, max_s=5), 2, 1)
        self.assertEqual((old["duration_s"], old["tau_s"]), (13, 6.5))
        self.assertEqual((capped["duration_s"], capped["tau_s"]), (13, 5))
        self.assertEqual(capped["timing_tolerance"], dict(min_s=3, fraction_of_phase=.5, max_s=5))
        self.assertIn("max_s", capped["tau_basis"])
        self.assertEqual(old["tau_basis"],
                         "max(min_s, fraction_of_phase * duration_s); duration includes terminal hold and confirmation")
        floor = time_aware_phase_clearance(starts, routes, 1, 5,
                                           dict(min_s=7, fraction_of_phase=.5, max_s=5), 2, 1)
        self.assertEqual(floor["tau_s"], 7)

    def test_T01_schema_is_optional_and_planning_metadata_is_bound(self):
        spec = json.loads((ROOT / "missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8"))
        original = copy.deepcopy(spec)
        old = compile_task(spec)
        self.assertEqual(spec, original)
        self.assertNotIn("max_s", normalize_v3(spec)["execution"]["async_timing_tolerance"])
        capped = copy.deepcopy(spec)
        capped["execution"]["async_timing_tolerance"]["max_s"] = 5
        normalized = normalize_v3(capped)
        self.assertEqual(normalized["execution"]["async_timing_tolerance"]["max_s"], 5.0)
        new = compile_task(capped)
        self.assertEqual(new["planning"]["nominal_phase_timing"]["p01_observe"]["tau_s"], 5)
        self.assertAlmostEqual(old["planning"]["nominal_phase_timing"]["p01_observe"]["tau_s"], 11.16)
        for phase in old["planning"]["nominal_phase_timing"]:
            self.assertEqual(old["planning"]["nominal_phase_timing"][phase]["duration_s"],
                             new["planning"]["nominal_phase_timing"][phase]["duration_s"])
            self.assertEqual(new["planning"]["nominal_phase_timing"][phase]["timing_tolerance"],
                             normalized["execution"]["async_timing_tolerance"])

    def test_T01_invalid_cap_rejected_without_weakening_unknown_field_rules(self):
        spec = json.loads((ROOT / "missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8"))
        for value in (True, None, "5", float("nan"), float("inf"), -1, 3601):
            with self.subTest(value=value):
                altered = copy.deepcopy(spec)
                altered["execution"]["async_timing_tolerance"]["max_s"] = value
                with self.assertRaises(ValueError):
                    normalize_v3(altered)
        altered = copy.deepcopy(spec)
        altered["execution"]["async_timing_tolerance"]["extra"] = 5
        with self.assertRaisesRegex(ValueError, "unsupported async_timing_tolerance"):
            normalize_v3(altered)

    def test_T01_all_frozen_v04_v3_normalization_hashes(self):
        baseline = json.loads((ROOT / "tmp_v05/m0/v04_compatibility_baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(baseline["normalization_count"], 16)
        for name, expected in baseline["normalized_task_sha256"].items():
            with self.subTest(task=name):
                source = json.loads((ROOT / name).read_text(encoding="utf-8-sig"))
                self.assertEqual(canonical_hash(normalize_v3(source)), expected)

    def test_T02_prefilter_can_pass_while_corner_chord_breaks_clearance(self):
        # Four equal offsets around a 20 m square start 20 m apart. At t=10 s,
        # adjacent aircraft straddle a corner by 10 m each: chord sqrt(200).
        corners = [(0, 0), (20, 0), (20, 20), (0, 20)]
        starts = {f"uav_{i + 1:02d}": point(*corners[i]) for i in range(4)}
        routes = {f"uav_{i + 1:02d}": [point(*corners[(i + k) % 4]) for k in range(1, 5)]
                  for i in range(4)}
        required = 14.5
        self.assertEqual(min(math.dist(tuple(starts[a].values()), tuple(starts[b].values()))
                             for a in starts for b in starts if a < b), 20)
        self.assertLess(math.sqrt(10**2 + 10**2), required)
        screen = patrol_spacing_prefilter(80, 4, 1, 3, required)
        self.assertTrue(screen["passed"])
        self.assertIsNone(screen["rejection_reason"])
        self.assertEqual((screen["nominal_spacing_m"], screen["minimum_spacing_m"]), (20, 19.5))
        with self.assertRaisesRegex(ValueError, "time-aware nominal routes too close"):
            time_aware_phase_clearance(starts, routes, 1, required,
                                       dict(min_s=3, fraction_of_phase=0, max_s=5))
        screen_fail = patrol_spacing_prefilter(80, 4, 1, 3, 16)
        self.assertFalse(screen_fail["passed"])
        self.assertEqual(screen_fail["rejection_reason"], "patrol_spacing_prefilter")


if __name__ == "__main__":
    unittest.main()
