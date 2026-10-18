"""Known-answer 10 Hz evidence tests for the two confirmed P0 repairs."""
import math
import unittest
import numpy as np
from task_v07.labels import measure
from task_v07.expansion.pipeline import COMMON_CONSTANTS, exclusion_policy
from test_v07_s2_expansion import scene, CENTER


class P0FactRepairTests(unittest.TestCase):
    def build(self, role, positions, velocities, extra, reference):
        sk={'base_intent':'feint' if role=='feint' else 'monitoring',
            'role':role,'execution_method':role,'target_id':'f','group_id':'g',
            'members':['a'],'agent_ids':['a'],'approach_mode':'same_direction',
            'cruise_speed_m_s':5.,**COMMON_CONSTANTS,**extra,
            'references':{'a':reference},
            'exclusion_policy':exclusion_policy(scene(),role,'f',['a'])}
        p=np.zeros((len(positions),1,3));p[:,0,:2]=positions;p[:,:,2]=100.
        v=np.zeros_like(p);v[:,0,:2]=velocities
        return sk,{'agent_ids':['a'],'time_us':np.arange(len(p),dtype=np.int64)*100000,
                   'p':p,'v':v,'execution_status':'completed'}

    def test_feint_exact_contour_depth_and_fraction(self):
        # Facility radius 20; alert offset 280, protected 130.
        # Deepest point at centre+225 => s=205, depth=75 => 50% of 150m band.
        inbound=np.c_[np.linspace(3000.,2225.,1551),np.full(1551,2000.)]
        outbound=np.c_[np.linspace(2225.,2910.,1371)[1:],np.full(1370,2000.)]
        positions=np.vstack([inbound,outbound,np.repeat(outbound[-1:],30,axis=0)])
        velocities=np.zeros_like(positions);velocities[:1550,0]=-5.;velocities[1550:2920,0]=5.
        reference={'endpoint_enu_m':[2910.,2000.,100.],'retreat_required':True,
                   'retreat_warning_clearance_m':210.}
        sk,run=self.build('feint',positions,velocities,
            {'feint':{'retreat_distance_tolerance_m':5.,'retreat_drop_fraction_max':.1}},reference)
        labels,_=measure(scene(),sk,run,'synchronous')
        result=labels['agents']['a'];facts=result['observed']['contribution']
        self.assertEqual(facts['max_depth_in_alert_m'],75.)
        self.assertEqual(facts['depth_fraction_in_alert_band'],.5)
        self.assertEqual(facts['turnaway_s'],155.)
        self.assertEqual(result['observed']['work_end_s'],250.1)
        # criteria-r1: depth and retreat direction are measured diagnostics, not gates.
        self.assertTrue(facts['retreat_ok'])
        self.assertEqual(facts['maximum_retreat_drop_m'], 0.)
        self.assertEqual(facts['retreat_descending_fraction'], 0.)

    def test_monitoring_measured_end_does_not_erase_terminal_hold(self):
        approach=np.c_[np.linspace(3000.,2500.,1001),np.full(1001,2000.)]
        count=12566
        angles=np.linspace(0.,4*math.pi,count+1)
        ring=CENTER+500*np.c_[np.cos(angles),np.sin(angles)]
        departure=np.c_[np.linspace(2500.,2910.,821)[1:],np.full(820,2000.)]
        positions=np.vstack([approach[:-1],ring,departure,np.repeat(departure[-1:],30,axis=0)])
        velocities=np.zeros_like(positions);velocities[:1000,0]=-5.
        velocities[1000:1000+len(ring),:]=5*np.c_[-np.sin(angles),np.cos(angles)]
        velocities[1000+len(ring):1000+len(ring)+819,0]=5.
        reference={'endpoint_enu_m':[2910.,2000.,100.],'retreat_required':True,
                   'retreat_warning_clearance_m':210.}
        rules={'orbit_center_enu_m':CENTER.tolist(),'orbit_radius_m':500.,
               'track_tolerance_m':30.,'effective_speed_min_m_s':.5,
               'min_loop_duration_s':5.,'planned_laps':2.}
        sk,run=self.build('monitoring',positions,velocities,{'monitoring':rules},reference)
        labels,_=measure(scene(),sk,run,'synchronous')
        result=labels['agents']['a']
        # Warning radius is 700 m. After the radius-500 ring, 400 samples
        # of 0.5 m reach its boundary; sample 401 is the first outside.
        # Work ends there, rather than at the end of the two patrol laps.
        self.assertEqual(result['observed']['work_end_s'],(1000+count+401)/10.)
        self.assertEqual(result['observed']['endpoint_hold_s'],3.0)
        self.assertEqual(result['observed']['retreat_event']['status'], 'known')
        self.assertEqual(result['observed']['retreat_event']['minimum_observed_endpoint_distance_m'], 0.)
        self.assertTrue(result['result']['conditions']['ended_outside_warning'])
        self.assertAlmostEqual(result['observed']['contribution']['lap_count_observed'],2.,places=3)


class FullRouteGateTests(unittest.TestCase):
    def test_crossing_routes_with_distinct_endpoints_never_reach_paired_flight(self):
        from unittest.mock import patch
        from pathlib import Path
        import tempfile
        from task_v07.expansion.contracts import RouteBundle
        from test_v07_s2_expansion import PlanningIntervalInterceptTests
        from scripts.run_v07_s2_expansion import run_skeleton_job
        descriptor=PlanningIntervalInterceptTests()._make_overlapping_descriptor()
        agents=descriptor['agent_ids']
        routes={agents[0]:[[100.,100.,100.],[300.,300.,100.]],
                agents[1]:[[100.,300.,100.],[300.,100.,100.]],
                agents[2]:[[100.,500.,100.],[300.,500.,100.]]}
        bundle=RouteBundle(routes,{a:0. for a in agents})
        sk={'members':agents,'role':'reconnaissance'}
        pre={'status':'PASS','policy':{}}
        plans={mode:{'departure_delays_s':{a:0. for a in agents}}
               for mode in ('synchronous','sequential')}
        solo={a:{'wall_s':0.,'time_us':np.array([0,100000]),'p':np.zeros((2,1,3)),
                 'v':np.zeros((2,1,3)),'agent_ids':[a]} for a in agents}
        with tempfile.TemporaryDirectory() as temp:
            payload={'scene':scene(),'descriptor':descriptor,'planner':('role',),
                     'out':temp,'scope':'test'}
            with patch('scripts.run_v07_s2_expansion.plan_group',return_value=(sk,bundle,pre)), \
                 patch('scripts.run_v07_s2_expansion.single_agent_timing',return_value=({a:10. for a in agents},{a:20. for a in agents},solo)), \
                 patch('scripts.run_v07_s2_expansion.timing_plans',return_value=plans), \
                 patch('scripts.run_v07_s2_expansion.paired_run') as fly:
                result=run_skeleton_job(payload)
            fly.assert_not_called()
            self.assertTrue(all(row['reason']=='planning_interval_too_close:full_route' for row in result))
            self.assertTrue(all(row['path'] is None for row in result))


if __name__=='__main__': unittest.main()
