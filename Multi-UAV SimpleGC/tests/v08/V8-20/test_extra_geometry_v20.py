"""Appendix split examples and independent grid/interval certificates."""
import math
import unittest
from types import SimpleNamespace as NS

import numpy as np

from task_v07.geometry import offset_geometry,radial_points_exact
from v08.motion.area_search_geometry import minimum_inner_offset,member_split_points,legal_ray_intervals,_scan_angle_cells
from v08.scene.exact import signed_distance
from v08.scene.field import Clearance


class GeometryTests(unittest.TestCase):
    def test_appendix_twelve_centered_column(self):
        base={"type":"Circle","center_m":[0.,0.],"radius_m":100.}
        offsets={str(i):((5.5-i)*24.,0.) for i in range(12)}
        got=member_split_points(base,(0.,0.),347.5,(1.,0.),315.,offsets)
        want=np.array([-math.sqrt(447.5**2-315.**2),315.])
        for p in got.values():
            np.testing.assert_allclose(p,want,rtol=0.,atol=1e-9)
            self.assertAlmostEqual(400.-signed_distance(base,p),52.5,delta=1e-9)

    def test_appendix_twelve_abreast_beta_forty(self):
        base={"type":"Circle","center_m":[0.,0.],"radius_m":100.}
        h=447.5*math.sin(math.radians(40.))
        offsets={str(i):(0.,(i-5.5)*24.) for i in range(12)}
        got=member_split_points(base,(0.,0.),347.5,(1.,0.),h,offsets)
        for mid,p in got.items():
            self.assertAlmostEqual(p[1],h+offsets[mid][1],delta=1e-9)
            self.assertLess(p[0],0.)
            self.assertAlmostEqual(400.-signed_distance(base,p),52.5,delta=1e-9)

    def test_split_requires_reach_inside_certified_forward_travel(self):
        base={"type":"Circle","center_m":[0.,0.],"radius_m":100.}
        with self.assertRaises(ValueError):
            member_split_points(base,(0.,0.),347.5,(1.,0.),315.,{"rear":(-132.,0.)},x_min=-1000.,x_max=-300.)
        with self.assertRaises(ValueError):
            member_split_points(base,(0.,0.),347.5,(1.,0.),315.,{"wide":(0.,200.)})

    def test_first_grid_circle_not_continuous_root(self):
        base={"type":"Circle","center_m":[0.,0.],"radius_m":100.}
        angles=np.radians([-11.25,-3.75,3.75,11.25])
        root=40./(2*math.sin(math.radians(3.75)))-100.
        want=150.+.5*math.ceil((root-150.)/.5)
        self.assertEqual(minimum_inner_offset(base,(0.,0.),angles,400.,150.),want)
        self.assertLess(2*(100.+want-.5)*math.sin(math.radians(3.75)),40.)

    def test_vectorized_scan_keeps_each_cells_first_grid_value(self):
        base={"type":"Circle","center_m":[0.,0.],"radius_m":100.}
        choices=_scan_angle_cells(base,(0.,0.),2,2,400.,150.,50.)
        root=40./(2*math.sin(math.radians(3.75)))-100.
        want=150.+.5*math.ceil((root-150.)/.5)
        self.assertEqual(choices[(0,30)]["inner_offset_m"],want)
        self.assertNotIn((0,20),choices)  # Required radius exceeds the 440 m length bound.
        self.assertTrue(all(x>=40. for x in choices[(0,30)]["inner_gaps_m"]))

    def test_polygon_and_buffer_grid_certificate_and_feature_change(self):
        vertices=[[-100.,-100.],[100.,-100.],[100.,100.],[-100.,100.]]
        angles=np.radians([-47.,-40.,-1.,1.,40.,47.])
        for buffer in (0.,10.):
            base={"type":"Polygon","vertices_m":vertices} if not buffer else {"type":"BufferedPolygon","vertices_m":vertices,"buffer_m":buffer}
            # The limiting pair +/-1 degree remains on the vertical flat edge.
            root=40./(2*math.tan(math.radians(1.)))-100.-buffer
            want=1000.+.5*math.ceil((root-1000.)/.5)
            got=minimum_inner_offset(base,(0.,0.),angles,1500.,1000.)
            self.assertEqual(got,want)
            inner=radial_points_exact(offset_geometry(base,got),(0.,0.),angles)
            outer=radial_points_exact(offset_geometry(base,1500.),(0.,0.),angles)
            self.assertTrue(np.all(np.linalg.norm(np.diff(inner,axis=0),axis=1)>=40.))
            self.assertTrue(np.all(np.linalg.norm(outer-inner,axis=1)>=60.))
            # Independent certificate: even the last predecessor fails its central pair;
            # all smaller grid values have a still smaller flat-edge central chord.
            self.assertLess(2*(100.+buffer+got-.5)*math.tan(math.radians(1.)),40.)
            # 40-degree ray changes from the translated edge to the rounded vertex.
            p=radial_points_exact(offset_geometry(base,0.),(0.,0.),np.radians([40.]))[0]
            q=radial_points_exact(offset_geometry(base,30.),(0.,0.),np.radians([40.]))[0]
            self.assertLess(p[1],100.)
            self.assertGreater(q[1],100.)

    def test_legal_ray_retains_both_components(self):
        circle=lambda x,r:{"type":"Circle","center_m":[x,0.],"radius_m":r}
        cons=[Clearance("world",circle(0.,1000.),-1,35.),Clearance("obstacle:x",circle(300.,40.),1,35.)]
        self.assertEqual(legal_ray_intervals(cons,(0.,0.),(1.,0.)),[(0.,225.),(375.,965.)])
        for a,b in legal_ray_intervals(cons,(0.,0.),(1.,0.)):
            for x in (a,(a+b)/2,b):
                self.assertGreaterEqual(1000.-x-35.,0.)
                self.assertGreaterEqual(abs(x-300.)-40.-35.,0.)


if __name__=="__main__":
    unittest.main()
