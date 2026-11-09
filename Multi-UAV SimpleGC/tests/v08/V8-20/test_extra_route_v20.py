"""Placement-only head selection and exact frozen-route argument observation."""
import math
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np

from v08.motion.intents.area_search import _head,_route_with_vertices
from v08.motion.connect import fillet_route
from v08.motion.path import sample_primitives
from v08.motion.area_search_geometry import arc_extreme_points
from v08.scene.exact import signed_distance


class RouteTests(unittest.TestCase):
    def test_head_fit_only_omits_first_outer_when_short(self):
        a=np.radians([148.75,156.25])
        outer=800.*np.c_[np.cos(a),np.sin(a)]
        inner=500.*np.c_[np.cos(a),np.sin(a)]
        split=np.array([-math.sqrt(800.**2-420.**2),420.])
        head=_head((-1200.,420.),split,inner,outer,[0,1],outer[-1]+200.*np.array([math.cos(a[-1]),math.sin(a[-1])]))
        self.assertEqual(head["kind"],"omit_first_outer")
        self.assertTrue(head["omitted"])
        self.assertEqual(head["indices"],[0,1])
        self.assertTrue({"scan1","scan2"}<=head["mapping"].keys())
        sampled=sample_primitives(head["primitives"],.5)
        self.assertTrue(np.isfinite(sampled.xy).all())
        for label in ("scan1","scan2"):
            primitive=head["primitives"][head["mapping"][label]]
            self.assertGreaterEqual(primitive[2],15.)

    def test_arc_extrema_include_interior_worst_point(self):
        primitive=("arc",(0.,0.),100.,-.4,1.1)
        geometry={"type":"Circle","center_m":[200.,0.],"radius_m":50.}
        points=arc_extreme_points(primitive,geometry)
        # Independent nearest point: (100,0), distance to the other disk boundary 50.
        self.assertAlmostEqual(float(np.min(signed_distance(geometry,points))),50.,delta=1e-9)
        self.assertGreater(min(signed_distance(geometry,points[:2])),50.)

    def test_route_observer_restores_profile_and_keeps_original_arguments(self):
        before=sys.getprofile()
        points=[np.array([0.,0.]),np.array([100.,0.]),np.array([100.,100.])]
        radii=[30.]
        def frozen_route(*args,**kwargs):
            return fillet_route(points,radii),None
        capture=[]
        with patch("v08.motion.intents.area_search.route_to_slot",side_effect=frozen_route):
            primitives,_=_route_with_vertices(NS(),points[0],points[-1],np.array([1.,0.]),None,"f",capture)
        self.assertIs(sys.getprofile(),before)
        self.assertIs(capture[0]["primitives"],primitives)
        np.testing.assert_array_equal(capture[0]["vertices"],points)
        self.assertEqual(capture[0]["radii"],radii)


if __name__=="__main__":
    unittest.main()
