"""Small fixed synthetic D0 analysis tests; never reads the 60-episode dataset."""
import math
import unittest
from unittest.mock import patch
import numpy as np
from scripts import qc_v07_fe_corner_dwell as audit
from scripts import probe_v07_fe_corner_cap as probe
from task_v07.detectors import dwell
from task_v07.execution import frozen_config
from swarm_sim.fast_dynamics.route_tracker import RouteTracker

class CornerDwellAnalysisTests(unittest.TestCase):
    def curve(self,degrees):
        a=math.radians(degrees)
        return np.array([[0.,0.,30.],[10.,0.,30.],[10.+10*math.cos(a),10*math.sin(a),30.]])
    def tracker(self,points):
        c=frozen_config();return RouteTracker(points,4.,c.vehicle_profile,c.controller,c.reference,c.engine.step_us)
    def test_closed_201_frame_witness(self):
        t=np.arange(201,dtype=np.int64)*100000;xy=np.zeros((201,2));v=np.zeros((201,3));levels=np.ones(201,int)
        saved=dwell(xy,t,np.ones(201,bool));f=audit.witness_facts(xy,v,t,levels,saved)
        self.assertEqual((f['begin'],f['end'],f['frames'],f['duration_s']),(0,200,201,20.))
        self.assertEqual(f['low_total_duration_s'],20.1)
        self.assertEqual(saved['total_duration_s'],20.)
    def test_spatial_dwell_does_not_require_low_speed(self):
        t=np.arange(201,dtype=np.int64)*100000;angles=np.arange(201)*.1
        circle=10*np.c_[np.cos(angles),np.sin(angles)]
        self.assertTrue(dwell(circle,t,np.ones(201,bool))['detected'])
        straight=np.c_[np.arange(201)*.5,np.zeros(201)]
        self.assertFalse(dwell(straight,t,np.ones(201,bool))['detected'])
    def test_classification_boundaries(self):
        for a,k in [(0.,'STRAIGHT'),(1e-8,'STRAIGHT'),(1.0001e-8,'CURVE'),(math.radians(45),'CURVE'),(math.radians(90),'CURVE'),(math.radians(174.99),'CURVE'),(math.radians(175),'EXPLICIT_STOP'),(math.pi,'EXPLICIT_STOP')]:
            self.assertEqual(audit.corner_kind(a),k)
    def test_original_curve_horizon_bound(self):
        for angle in (10,45,90,170):
            row=audit.static_route(self.curve(angle),4.)[0]
            self.assertLessEqual(row['actual_curve_cap_m_s'],row['horizon_cap_m_s']+1e-9)
            self.assertLessEqual(row['horizon_cap_m_s'],.435)
    def test_R1_intervenes_on_all_curve_angles(self):
        for angle in (10,45,90,174):
            with self.subTest(angle=angle):
                original=self.tracker(self.curve(angle))
                with patch.object(RouteTracker,'_build',probe.experimental_build):trial=self.tracker(self.curve(angle))
                self.assertEqual(probe.tracker_geometry(original),probe.tracker_geometry(trial))
                changed=probe.CAP_LOG[id(trial)];self.assertEqual(len(changed),1)
                curve=next(q for q in trial.primitives if q.control is not None);k,ks=probe._curvature_bounds(curve.derivatives)
                expected=min(trial.speed,math.sqrt(trial.profile.max_accel_xy_m_s2/(2*k)),(trial.profile.max_jerk_m_s3/(2*(k*k+ks)))**(1/3))
                self.assertEqual(curve.cap,expected);self.assertGreaterEqual(curve.cap,changed[0]['old_cap_m_s'])
    def test_straight_and_explicit_stop_unchanged(self):
        for angle in (0,175,180):
            original=self.tracker(self.curve(angle))
            with patch.object(RouteTracker,'_build',probe.experimental_build):trial=self.tracker(self.curve(angle))
            self.assertEqual(probe.tracker_geometry(original),probe.tracker_geometry(trial));self.assertEqual(probe.CAP_LOG[id(trial)],[])
            self.assertEqual([(q.cap,q.exit_cap) for q in original.primitives],[(q.cap,q.exit_cap) for q in trial.primitives])
    def test_exit_caps_match_original_rule(self):
        points=np.array([[0,0,30],[10,0,30],[10,10,30],[20,10,30],[10,10,30]],float)
        with patch.object(RouteTracker,'_build',probe.experimental_build):t=self.tracker(points)
        for i,q in enumerate(t.primitives):
            expected=(0. if q.stop or i==len(t.primitives)-1 else t.primitives[i+1].cap if t.primitives[i+1].control is not None else t.speed) if q.control is None else q.cap
            self.assertEqual(q.exit_cap,expected)
    def test_patch_restores_even_on_exception(self):
        original=RouteTracker._build
        with self.assertRaises(RuntimeError):
            with patch.object(RouteTracker,'_build',probe.experimental_build):raise RuntimeError('synthetic')
        self.assertIs(RouteTracker._build,original)
    def test_missing_fields_fail_explicitly(self):
        with self.assertRaisesRegex(audit.AuditError,'missing truth field'):audit.validate_arrays({}, {}, {}, {}, 'fixture')
    def test_out_of_range_witness_fails(self):
        t=np.arange(201,dtype=np.int64)*100000;z=np.zeros((201,2));v=np.zeros((201,3));saved=dwell(z,t,np.ones(201,bool));saved['confirm_frame_index']=201
        with self.assertRaisesRegex(audit.AuditError,'Invalid witness indices'):audit.witness_facts(z,v,t,np.ones(201,int),saved)
    def test_multiple_vertex_matches_retained(self):
        xy=np.zeros((201,2));v=np.zeros((201,3));rows=[{'node_index':i,'point_xy':[0.,0.],'angle_deg':90.,'kind':'CURVE','angle_bin':'CURVE_90_TO_175','actual_curve_cap_m_s':.4,'horizon_cap_m_s':.4348} for i in (1,3)]
        r=audit.match_window(xy,v,{'begin':0,'end':200},rows)
        self.assertEqual([x['node_index'] for x in r['all_frame_matches']],[1,3]);self.assertTrue(r['multiple_vertex_matches']);self.assertEqual(r['eligible_curve_low_frame_score'],201)
    def test_polyline_distance_uses_segments(self):
        points=np.array([[0,0,30],[10,0,30],[10,10,30]],float);xy=np.array([[5,.25],[10.3,8],[0,0]],float)
        distances,segments=probe.polyline_deviations(xy,points)
        np.testing.assert_allclose(distances,[.25,.3,0],atol=1e-14);np.testing.assert_array_equal(segments,[0,1,0])
    def test_QC_motion_window_and_single_frame_event(self):
        group={'group_id':'g','cruise_speed_m_s':2.,'role':'transit','execution_method':'transit','references':{'a':{'points_enu_m':[[0,0,30],[10,0,30]]}}}
        velocity=np.zeros((5,1,3));velocity[:,0,0]=[0,2,.5,2,0];position=np.zeros((5,1,3));position[:,0,0]=np.arange(5)*.1
        run={'agent_ids':['a'],'p':position,'v':velocity,'time_us':np.arange(5,dtype=np.int64)*100000}
        r=probe.analyse_member(group,run,'a','s','solo_probe',{'a':('g',group)})
        self.assertEqual((r['motion_window_start_frame'],r['motion_window_end_frame']),(1,3));self.assertEqual(r['low_speed_event_count'],1);self.assertAlmostEqual(r['low_speed_time_share'],1/3);self.assertEqual(r['events'][0]['duration_s'],.1)
    def test_route_identity_deduplicates_modes(self):
        common={'role':'transit','execution_method':'transit','witness':None,'vertex_attribution':None}
        rows=[dict(common,skeleton_id='s1',agent_id='a',mode=m) for m in ('synchronous','sequential')]+[dict(common,skeleton_id='s2',agent_id='a',mode='synchronous')]
        actual=audit.summarize_members(rows)[0]
        self.assertEqual(actual['agent_episodes'],3)
        self.assertEqual(actual['unique_route_members'],2)
        self.assertEqual(actual['M1_positive'],0)
    def test_scalar_serialization(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as d:
            target=Path(d)/'values.json';audit.save(target,{'flag':np.bool_(True),'value':np.float64(1.5)})
            self.assertEqual(audit.read(target),{'flag':True,'value':1.5})
    def test_readonly_tracker_capture_without_A_patch(self):
        points=self.curve(30);group={'references':{'a':{'points_enu_m':points.tolist()}},'members':['a']}
        def fake_execute(group,delays,only_agent):
            tracker=self.tracker(points)
            tracker.witnesses.extend({'event':'route_node_witnessed','node_index':i,'t_us':i*100000} for i in range(3))
            return {'synthetic':True}
        original=RouteTracker._build
        with patch.object(probe,'execute',fake_execute):
            run,snapshots,witnesses=probe.replay_with_capture(group,'a','A')
        self.assertIs(RouteTracker._build,original)
        self.assertEqual(len(snapshots),1);self.assertEqual([v['node_index'] for v in witnesses],[0,1,2])
