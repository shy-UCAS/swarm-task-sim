"""Additional independent V8-19 reference checks; preset files remain verbatim."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np

from v08.contract.monitoring import MemberPlan
from v08.motion.dwell_nominal import compose_dwell, member_nominal_with_dwell, references_with_dwell
from v08.motion.nominal import Nominal


def leg(start, release=20.0):
    curve = NS(xy=np.array([[start, 0.], [start+2., 0.], [start+4., 0.]]),
               s=np.array([0., 2., 4.]), chord=np.array([2., 2.]),
               tangent=np.array([[1., 0.], [1., 0.]]), kappa=np.zeros(3), length=4.)
    return Nominal(curve, np.array([0., 2., 0.]), np.array([0., 2., 4.]), 4., release, 2., 100.)


class ExtraDwellReference(unittest.TestCase):
    def test_internal_split_keeps_original_arrival_station(self):
        points = tuple((4000.1 + .3 * i, 4000.2 + .1 * i) for i in range(8))
        mp = MemberPlan("m", 0, points, 100., 3., .14, ((0., 2.),), ())
        nom = member_nominal_with_dwell(mp, (.53, 20.))
        self.assertEqual(sum(nom.curve.s == .53), 1)
        self.assertEqual(nom.time_at_s(.53), nom.arrival_s)
        self.assertEqual(float(np.interp(.53, nom.curve.s, nom.t_nodes)) + nom.release_s, nom.arrival_s)
        self.assertEqual(nom.end_s, nom.release_s + (nom.end_s - nom.release_s))

    def test_incoming_length_mismatch_is_rejected(self):
        from dataclasses import replace
        incoming = leg(0)
        stations = incoming.curve.s.copy()
        stations[-1] = 4.0 + 1e-6
        bad_curve = NS(**vars(incoming.curve))
        bad_curve.s = stations
        incoming = replace(incoming, curve=bad_curve)
        plan = MemberPlan("m", 0, ((0., 0.), (2., 0.), (4., 0.), (6., 0.), (8., 0.)),
                          100., 8., 0., ((0., 2.),), ())
        with patch("v08.motion.dwell_nominal.member_nominal", side_effect=[incoming, leg(4)]):
            with self.assertRaises(ValueError):
                member_nominal_with_dwell(plan, (4.0, 20.0))
        self.assertEqual(incoming.curve.s[-1], 4.0 + 1e-6)

    def test_reference_checks_complete_member_table(self):
        sk = NS(members={"a": NS(), "b": NS()}, witnesses={"dwell_windows": {"a": (4., 20., (4., 0.))}})
        with self.assertRaises(ValueError):
            references_with_dwell(sk)

    def test_outgoing_semantic_line_uses_full_station_and_shift(self):
        nom = compose_dwell(leg(0), leg(4, 20.1), 20.)
        sk = NS(members={"m": NS()}, witnesses={"dwell_windows": {"m": (4., 20., (4., 0.))}})
        incoming = ("m", 21., 22., (1., 0.), (1., 0.), {"s_from_m": 1., "s_to_m": 2., "s_cross_m": 1.5})
        outgoing = ("m", 21.1, 22.1, (5., 0.), (1., 0.), {"s_from_m": 1., "s_to_m": 2., "s_cross_m": 1.5})
        with patch("v08.motion.dwell_nominal.member_nominal_with_dwell", return_value=nom), \
             patch("v08.motion.skeleton.semantic_lines", side_effect=[(incoming,), (outgoing,)]):
            refs, lines, maps = references_with_dwell(sk, warnings={}, target_id="t", band_m=10., align_m=100.)
        self.assertEqual(lines[0], incoming)
        self.assertEqual(lines[1][1:3], (45., 46.))
        self.assertEqual(lines[1][5], {"s_from_m": 5., "s_to_m": 6., "s_cross_m": 5.5})
        self.assertIs(maps["m"]["dwell_reference"], nom)
        self.assertEqual((refs[0].release_s, refs[0].end_s), (20., 48.))

    def test_duration_endpoints_and_outside_domain(self):
        for duration in (20., 120.):
            nom = compose_dwell(leg(0), leg(4), duration)
            self.assertEqual(nom.departure_s - nom.arrival_s, duration)
        for duration in (19.9, 120.1, 20.01, float("nan"), float("inf")):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                compose_dwell(leg(0), leg(4), duration)


if __name__ == "__main__":
    unittest.main()
