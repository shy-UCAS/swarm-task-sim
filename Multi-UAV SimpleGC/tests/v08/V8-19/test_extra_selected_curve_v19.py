"""Executor-added V8-19 tests: selected-curve domain, empty-set RNG, exact joins and nested payloads."""
import unittest
from dataclasses import replace
from types import SimpleNamespace as NS

import numpy as np

from v08.contract.monitoring import MemberPlan, SegmentPlan
from v08.motion.intents import close_observation as C
from v08.motion.skeleton import references_from_skeleton, semantic_lines


def circle(radius):
    return {"type": "Circle", "center_m": [0.0, 0.0], "radius_m": float(radius)}


def fixture():
    target = NS(id="t", center=(0., 0.), geometry=circle(20), offsets={"warning": 280., "alert": 140., "protected": 80.},
                layers={"warning": circle(300), "alert": circle(160), "protected": circle(100)})
    ctx = NS(facilities=[target], facility_by_id={"t": target}, world=circle(2000), obstacles=[], extra={},
             params={"world_margin_m": 35., "obstacle_margin_m": 35., "forbidden_margin_m": 10.,
                     "pre_entry_warning_clearance_m": 10., "alignment_length_m": 100.})
    xy = tuple((float(x), 0.) for x in np.arange(-450., 450.5, .5))
    mp = MemberPlan("m", 0, xy, 100., 900., 0., ((0., 8.),), ())
    mapping = {"schema": "member-map-transit-v16", "members": {"m": {"reference_s": [0., 900.], "member_s": [0., 900.]}}}
    plan = SegmentPlan({"m": mp}, xy, 0., {"collect_s": 0., "terminal_s": 900.}, (), proposal={"intent": C.INTENT},
                       formation={"realized": "abreast"}, topology={"final": "transit"},
                       witnesses={"intent": C.INTENT, "target_id": "t", "member_map_transit": mapping})
    return ctx, plan


class FirstChoice:
    def __init__(self):
        self.calls = []

    def integers(self, lower, upper):
        self.calls.append((lower, upper))
        return lower


class SelectedCurve(unittest.TestCase):
    def test_analytic_selected_point_and_two_tail_draws(self):
        ctx, plan = fixture()
        rng = FirstChoice()
        result = C.add_dwell(ctx, plan, rng)
        self.assertIsNone(result.failure)
        # Warning band ends at x=-287.5; 5 m grid's first eligible point is x=-285.
        self.assertEqual(result.witnesses["dwell_windows"]["m"], (165., 20., (-285., 0.)))
        choice = result.proposal["dwell"]
        self.assertEqual(rng.calls, [(0, choice["set_size"]), (200, 1201)])
        self.assertEqual(choice["reference_station_m"], 165.)
        member = result.witnesses["dwell_diagnostics"]["members"]["m"]
        self.assertEqual(member["warning_sdf_m"], -15.)
        self.assertEqual(member["alert_sdf_m"], 125.)
        self.assertEqual(member["endpoint_distance_m"], 735.)
        # This fixture crosses the deep layers; the whole-path screen must reject it.
        self.assertFalse(result.witnesses["screen"]["m"]["passed"])
        self.assertFalse(result.witnesses["screen"]["m"]["conditions"]["max_target_layer_one"])
        self.assertEqual(result.witnesses["screen"]["m"]["counts"]["max_target_layer"], 3)
        self.assertTrue(result.witnesses["screen"]["m"]["conditions"]["observation_dwell"])
        self.assertEqual(result.members, plan.members)
        self.assertEqual(result.witnesses["member_map_transit"], plan.witnesses["member_map_transit"])

    def test_offset_chord_stays_outside_alert_and_passes_screen(self):
        ctx, plan = fixture()
        # The line y=225 has minimum alert SDF 225-160=65 m, exceeding the existing 10 m margin.
        xy = tuple((x, 225.) for x, _ in plan.members["m"].curve_xy)
        member = replace(plan.members["m"], curve_xy=xy)
        plan = replace(plan, members={"m": member}, reference_xy=xy)
        result = C.add_dwell(ctx, plan, FirstChoice())
        self.assertIsNone(result.failure)
        self.assertGreaterEqual(min(C._margins(C.TC.transit_base(ctx, "t", intent=C.INTENT)["base"],
                                              np.asarray(xy))["alert:t"]), 10.)
        self.assertTrue(result.witnesses["screen"]["m"]["passed"])
        self.assertEqual(result.witnesses["screen"]["m"]["counts"]["max_target_layer"], 1)

    def test_empty_set_does_not_consume_rng_or_change_geometry(self):
        ctx, plan = fixture()
        ctx.facility_by_id["t"].layers["alert"] = circle(300)
        rng = FirstChoice()
        result = C.add_dwell(ctx, plan, rng)
        self.assertEqual(result.failure.feasible_set, "close_obs_dwell_set")
        self.assertEqual(rng.calls, [])
        self.assertFalse(result.failure.witness["shape_audit_failed"])
        self.assertEqual(result.proposal, plan.proposal)
        self.assertEqual(result.members, plan.members)
        self.assertEqual(result.formation, plan.formation)

    def test_mapping_domain_is_not_interp_endpoint_clamping(self):
        ctx, plan = fixture()
        mapping = {"schema": "member-map-transit-v16", "members": {"m": {"reference_s": [200., 700.], "member_s": [0., 500.]}}}
        plan = replace(plan, witnesses={**plan.witnesses, "member_map_transit": mapping})
        candidates = C.dwell_candidates(ctx, plan)
        ss = candidates["stations"]
        np.testing.assert_array_equal(candidates["masks"]["mapping_domain"], (ss >= 200.) & (ss <= 700.))
        self.assertFalse(candidates["mask"][ss < 200.].any())
        self.assertFalse(candidates["mask"][ss > 700.].any())

    def test_outgoing_semantic_times_and_stations_are_shifted_once(self):
        ctx, plan = fixture()
        plan = C.add_dwell(ctx, plan, FirstChoice())
        refs, lines, maps = references_from_skeleton(plan, warnings={"t": ctx.facility_by_id["t"].layers["warning"]},
                                                    target_id="t", band_m=10., align_m=100.)
        nom = maps["m"]["dwell_reference"]
        local = semantic_lines("m", nom.outgoing, {"t": ctx.facility_by_id["t"].layers["warning"]}, "t", band_m=10., align_m=100.)
        outgoing = [line for line in lines if line[5]["direction"] == "out"]
        self.assertEqual(len(outgoing), 1)
        self.assertEqual(len(local), 1)
        shift = nom.departure_s - nom.outgoing.release_s
        self.assertEqual(outgoing[0][1], local[0][1] + shift)
        self.assertEqual(outgoing[0][2], local[0][2] + shift)
        self.assertEqual(outgoing[0][5]["s_cross_m"], 750.)
        self.assertEqual(nom.time_at_s(165.), nom.arrival_s)
        self.assertEqual(refs[0].end_s, nom.release_s + (nom.end_s - nom.release_s))

    def test_unknown_nested_fields_are_reported_with_location(self):
        _, plan = fixture()
        bad = replace(plan, proposal={"intent": C.INTENT, "lp": {"cache_hit": 1}})
        with self.assertRaisesRegex(ValueError, r"plan\.proposal\.lp\.cache_hit"):
            C.project_plan(bad)
        with self.assertRaisesRegex(ValueError, "filesystem string"):
            C.assert_no_runtime({"nested": {"value": r"F:\cache\source.json"}})


if __name__ == "__main__":
    unittest.main()
