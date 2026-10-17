"""Deterministic synthetic D0b contracts; no dataset replay in unit tests."""
import math
import unittest
from unittest.mock import patch
import numpy as np
from scripts import probe_v07_fe_corner_fillet as probe
from scripts import probe_v07_fe_corner_cap as d0
from task_v07.execution import frozen_config
from swarm_sim.fast_dynamics.route_tracker import RouteTracker


class CornerFilletTests(unittest.TestCase):
    def route(self, angle, before=100., after=100.):
        a=math.radians(angle)
        return np.array([[-before,0.,30.],[0.,0.,30.],[after*math.cos(a),after*math.sin(a),30.]])

    def tracker(self, points, builder=None):
        cfg=frozen_config()
        if builder:
            with patch.object(RouteTracker,'_build',builder):
                return RouteTracker(points,4.,cfg.vehicle_profile,cfg.controller,cfg.reference,cfg.engine.step_us)
        return RouteTracker(points,4.,cfg.vehicle_profile,cfg.controller,cfg.reference,cfg.engine.step_us)

    def assert_nested_equal(self, left, right):
        if isinstance(left,np.ndarray):
            self.assertEqual(left.dtype,right.dtype);self.assertTrue(np.array_equal(left,right))
        elif isinstance(left,dict):
            self.assertEqual(left.keys(),right.keys())
            for k in left:self.assert_nested_equal(left[k],right[k])
        elif isinstance(left,(list,tuple)):
            self.assertEqual(len(left),len(right))
            for a,b in zip(left,right):self.assert_nested_equal(a,b)
        else:self.assertEqual(left,right)

    def test_normalized_formula_all_six_angles(self):
        rows=probe.validate_formula();self.assertEqual(len(rows),6)
        for row in rows:self.assertLessEqual(row['error'],row['tolerance'])

    def test_small_medium_near_stop_curves(self):
        for angle in (.55,2.6,11.25,45.,90.,174.9):
            with self.subTest(angle=angle):
                t=self.tracker(self.route(angle),probe.adaptive_build)
                curves=[q for q in t.primitives if q.control is not None]
                self.assertEqual(len(curves),1)
                self.assertEqual(probe.BUILD_AUDIT[id(t)]['status'],'PASS')
                self.assertLessEqual(curves[0].project(t.points[1,:2])[1],.25+1e-9)

    def test_175_and_180_explicit_stop(self):
        for angle in (175.,180.):
            original=self.tracker(self.route(angle));trial=self.tracker(self.route(angle),probe.adaptive_build)
            self.assertEqual(probe.structure(original),probe.structure(trial))
            self.assertFalse(any(q.control is not None for q in trial.primitives))
            self.assertTrue(trial.primitives[0].stop);self.assertEqual(trial.primitives[0].exit_cap,0.)

    def test_straight_and_single_node_unchanged(self):
        for points in (self.route(0.),np.array([[0.,0.,30.]])):
            a=self.tracker(points);b=self.tracker(points,probe.adaptive_build)
            self.assertEqual(d0.tracker_geometry(a),d0.tracker_geometry(b))

    def test_d_formula_not_original_cut_limit(self):
        self.assertAlmostEqual(probe.cut_distance(.5,math.radians(.55),100,100),45.)
        self.assertAlmostEqual(probe.cut_distance(.5,math.radians(90),100,100),.25/((23/48)*math.sin(math.pi/4)))
        self.assertGreater(probe.cut_distance(.5,math.radians(45),100,100),.25)

    def test_d_uses_gate_and_both_leg_limits(self):
        angle=math.radians(2.6)
        self.assertEqual(probe.cut_distance(.5,angle,2.,100.),.9)
        self.assertEqual(probe.cut_distance(.5,angle,100.,2.),.9)
        self.assertAlmostEqual(probe.cut_distance(.002,angle,100.,100.),.001/((23/48)*math.sin(angle/2)))

    def test_equivalent_clone_exact_all_primitive_data(self):
        routes=[self.route(a) for a in (0.,.55,2.6,11.25,45.,90.,174.9,175.,180.)]
        routes += [np.array([[0,0,30],[10,0,30],[10,.01,30],[10,.02,30],[12,.02,30]],float),np.array([[0.,0.,30.]])]
        for points in routes:
            a=self.tracker(points);b=self.tracker(points,probe.build_original_equivalent)
            self.assertEqual(d0.tracker_geometry(a),d0.tracker_geometry(b))
            self.assertEqual(a.short_continuations,b.short_continuations)
            for x,y in zip(a.primitives,b.primitives):self.assert_nested_equal(vars(x),vars(y))

    def test_adjacent_curves_leave_positive_line(self):
        points=np.array([[0,0,30],[100,0,30],[200,.5,30],[300,1.1,30],[400,2,30]],float)
        t=self.tracker(points,probe.adaptive_build)
        self.assertTrue(all(x>0 for x in probe.BUILD_AUDIT[id(t)]['residual_raw_leg_lengths_m']))
        self.assertTrue(all(q.length>0 for q in t.primitives))

    def test_exit_caps_recomputed(self):
        t=self.tracker(self.route(11.25),probe.adaptive_build)
        self.assertEqual(t.primitives[0].exit_cap,t.primitives[1].cap)
        self.assertEqual(t.primitives[1].exit_cap,t.primitives[1].cap)
        self.assertEqual(t.primitives[-1].exit_cap,0.)

    def test_structure_indices_gates_and_short_continuations(self):
        points=np.array([[0,0,30],[10,0,30],[10,.01,30],[10,.02,30],[10,10,30],[10,.02,30]],float)
        a=self.tracker(points);b=self.tracker(points,probe.adaptive_build)
        self.assertEqual(probe.structure(a),probe.structure(b))
        self.assertTrue(np.array_equal(a.gates,b.gates));self.assertEqual(a.short_continuations,b.short_continuations)
        self.assertTrue(np.array_equal(a.points,b.points))

    def test_patch_restored_after_exception(self):
        with patch.object(probe,'execute',side_effect=RuntimeError('synthetic')):
            with self.assertRaisesRegex(RuntimeError,'synthetic'):
                probe.replay_with_capture({'members':['u']},'u','B2')
        self.assertIs(RouteTracker._build,probe.ORIGINAL_BUILD)

    def test_A_has_no_patch_and_B1_reuses_exact_D0_function(self):
        for arm,expected in [('A',probe.ORIGINAL_BUILD),('B1',d0.experimental_build),('B2',probe.adaptive_build)]:
            def execute(*args,**kwargs):
                self.assertIs(RouteTracker._build,expected)
                raise RuntimeError('capture')
            with patch.object(probe,'execute',side_effect=execute):
                with self.assertRaisesRegex(RuntimeError,'capture'):probe.replay_with_capture({'members':['u']},'u',arm)
            self.assertIs(RouteTracker._build,probe.ORIGINAL_BUILD)

    def stop_case(self, speed=.159):
        group=dict(terminal_radius_m=1.,terminal_speed_m_s=.15,terminal_hold_s=.2,
                   stop_radius_m=15.,stop_speed_m_s=1.5,stop_hold_s=.2,initial_settle_s=0.,
                   references={'u':{'points_enu_m':[[0.,0.,0.],[1.,0.,0.]]}})
        run=dict(time_us=np.arange(4)*100000,p=np.tile([1.,0.,0.],(4,1,1)),
                 v=np.tile([speed,0.,0.],(4,1,1)),execution_status='completed')
        return run,group

    def test_effective_stop_accepts_historical_0159(self):
        run,group=self.stop_case();d=probe.stop_diagnostics(run,group,'u')
        self.assertTrue(d['effective_stop_satisfied']);self.assertEqual(d['effective_stop_speed_m_s'],1.5)
        self.assertEqual(d['effective_required_hold_frames'],3)

    def test_terminal_is_diagnostic_and_retained(self):
        run,group=self.stop_case();d=probe.stop_diagnostics(run,group,'u')
        self.assertFalse(d['terminal_final_conditions']);self.assertFalse(d['terminal_hold_satisfied'])
        self.assertTrue(d['terminal_is_diagnostic_only']);self.assertTrue(d['effective_stop_satisfied'])

    def test_stop_fallback_and_hold_reset(self):
        run,group=self.stop_case(.1)
        for k in ('stop_radius_m','stop_speed_m_s','stop_hold_s'):group.pop(k)
        run['v'][-2,0,0]=.2;d=probe.stop_diagnostics(run,group,'u')
        self.assertEqual(d['effective_stop_speed_m_s'],.15);self.assertEqual(d['effective_hold_frames'],1)
        self.assertFalse(d['effective_stop_satisfied'])

    def test_missing_waypoint_degrades(self):
        d=probe.ordered_witnesses([{'node_index':1},{'node_index':3}],5)
        self.assertFalse(d['all_waypoints_witnessed']);self.assertEqual(d['missing_waypoint_indices'],[2])

    def test_duplicate_waypoint_degrades(self):
        d=probe.ordered_witnesses([{'node_index':i} for i in [1,2,2,3]],5)
        self.assertFalse(d['all_waypoints_witnessed']);self.assertEqual(d['duplicate_waypoint_indices'],[2])

    def test_unordered_waypoint_degrades(self):
        d=probe.ordered_witnesses([{'node_index':i} for i in [1,3,2]],5)
        self.assertFalse(d['all_waypoints_witnessed']);self.assertEqual(d['ordered_prefix_count'],1)

    def test_complete_order_and_endpoints(self):
        d=probe.ordered_witnesses([{'node_index':i} for i in range(5)],5)
        self.assertTrue(d['all_waypoints_witnessed']);self.assertEqual(d['ordered_prefix_count'],3)

    def test_B2_cap_keeps_horizon_and_physical_bounds(self):
        t=self.tracker(self.route(45.),probe.adaptive_build);rows=probe.curve_facts(t,'B2',0)
        self.assertEqual(rows[0]['removed_limits'],[])
        self.assertEqual(rows[0]['cap_m_s'],min(rows[0]['limits_m_s'].values()))
        self.assertGreater(rows[0]['d_m'],rows[0]['original_d_m'])


    def test_failed_arm_deviation_is_not_hidden_by_valid_denominator(self):
        manifest=dict(arms=['A','B1','B2'],order=['probe_01'],probes=[dict(probe_id='probe_01',probe_kind='feint')],selection_sha256='locked')
        failed=dict(probe_id='probe_01',arm='B2',physical_status='FAIL',tracking=dict(classification='TRACKING_ACCURACY_DEGRADED',all_waypoints_witnessed=False,max_lateral_deviation_m=2.0))
        result=probe.summarize([failed],manifest,None,1.)
        self.assertEqual(result['summary']['B2']['valid_probes'],0)
        self.assertEqual(result['summary']['B2']['maximum_lateral_deviation_m'],2.0)
        self.assertEqual(result['summary']['B2']['physical_or_scene_violation_count'],1)
        self.assertEqual(result['outcomes']['B2']['completed_tracking_degraded'],['probe_01'])
        self.assertEqual(result['outcomes']['B2']['tracking'],'INCOMPLETE')


if __name__ == '__main__':
    unittest.main()
