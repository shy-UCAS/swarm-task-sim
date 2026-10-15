import math
import random
from types import SimpleNamespace
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from task_v07.dwell import DwellRouteTracker, timed_route_samples
from task_v07.execution import execute, frozen_config
from task_v07.expansion.operation_parameters import draw_radial_parameters, dwell_circle
from task_v07.expansion.candidate_search import choose_eligible
from task_v07.expansion.contracts import RouteBundle
from task_v07.expansion.geometry_checks import planning_layer_interval_check


class ContinuousRevisionTests(unittest.TestCase):
    def test_uniform_parameters_are_private_reproducible_and_noncollapsed(self):
        def samples():
            ctx=SimpleNamespace(rng=random.Random(761),group={'members':['a','b']})
            observations=[draw_radial_parameters(ctx,0.,'close_observation')[0] for _ in range(200)]
            feints=[draw_radial_parameters(ctx,0.,'feint')[0] for _ in range(200)]
            return observations,feints
        observations,feints=samples()
        self.assertEqual((observations,feints),samples())
        self.assertEqual({v['observation_dwell_method'] for v in observations},{'hover','small_circle'})
        for key,lo,hi in [('observation_alert_clearance_m',40,65),('planned_observation_dwell_s',25,55)]:
            values=[v[key] for v in observations]
            self.assertTrue(all(lo<=v<=hi for v in values))
            self.assertGreater(max(values)-min(values),.8*(hi-lo))
        for value in feints:
            mean=value['feint_group_depth_fraction']
            self.assertTrue(.35<=mean<=.65)
            self.assertTrue(all(abs(v-mean)<=.03 and .32<=v<=.68 for v in value['feint_depth_fraction_by_agent'].values()))

    def test_circle_nominal_duration_and_original_disk(self):
        center=np.array([10.,20.]);outward=np.array([1.,0.])
        for seconds in (25.,39.8,55.):
            ring=dwell_circle(center,outward,22.,6.,seconds)
            points=np.asarray([center+22*outward,*ring])
            self.assertAlmostEqual(np.linalg.norm(np.diff(points,axis=0),axis=1).sum()/6.,seconds)
            self.assertTrue(np.all(np.linalg.norm(points-center,axis=1)<30.))

    def test_115_percent_filter_then_seeded_order(self):
        pool=[{'cost':v,'index':i} for i,v in enumerate((100,114.9,115,115.1,200))]
        selected,report=choose_eligible(pool,True,random.Random(8))
        self.assertEqual({c['cost'] for c in selected},{100,114.9,115})
        self.assertEqual(report['feasible_candidates'],5)
        self.assertEqual(choose_eligible(pool,False,random.Random(8))[1]['eligible_candidates'],5)

    def test_every_registered_candidate_is_counted_without_calibration(self):
        from task_v07.expansion.candidate_search import episode_candidate_pool
        descriptor={'base_intent':'transit','role_seed':1,'common_draw':{'approach_mode':'same_direction'},
                    'task_groups':[{'role':'transit','group_id':'g','target_id':'f'}]}
        with patch('task_v07.expansion.candidate_search.Context'), \
             patch('task_v07.expansion.candidate_search.role_parameters',return_value={}), \
             patch('task_v07.expansion.candidate_search.draw_role',side_effect=lambda c,i:(None,'geometric_failure',{'index':i})) as draw:
            pool,report=episode_candidate_pool({},descriptor)
            self.assertEqual(pool,[])
            self.assertEqual(draw.call_count,200)
            self.assertEqual(report['attempted_candidates'],200)
            self.assertEqual(report['rejection_reasons'],{'geometric_failure':200})
            self.assertEqual(report['solo_flights_run'],0)
            with self.assertRaises(ValueError):episode_candidate_pool({},descriptor,budget=199)

    def test_nominal_spacing_includes_stationary_middle_dwell(self):
        points=[[0.,0.,50.],[100.,0.,50.],[200.,0.,50.]]
        sampled=timed_route_samples(points,10.,10.,{'waypoint_index':1,'duration_s':25.})
        np.testing.assert_array_equal(sampled[100],sampled[350])
        self.assertAlmostEqual(sampled[351,0],101.)
        paths={'a':points,'b':[[100.,-200.,50.],[100.,200.,50.]]}
        plans={m:{'departure_delays_s':{'a':0.,'b':0.}} for m in ('synchronous','sequential')}
        bundle=RouteBundle(paths,{'a':0.,'b':0.})
        baseline=planning_layer_interval_check(bundle,plans,10.)
        held=planning_layer_interval_check(bundle,plans,10.,dwells_by_agent={'a':{'waypoint_index':1,'duration_s':25.}})
        self.assertFalse(baseline['synchronous']['below_warning'])
        self.assertTrue(held['synchronous']['below_warning'])

    def test_hover_uses_exported_samples_and_releases_original_route(self):
        points=np.array([[0.,0.,50.],[100.,0.,50.],[200.,0.,50.]])
        tracker=DwellRouteTracker(points,5.,frozen_config(),{'waypoint_index':1,'duration_s':25.})
        tracker.tracker.complete=True
        sample=lambda t:SimpleNamespace(t_us=t,p=points[1:2],v=np.zeros((1,3)))
        tracker.observe_sample(sample(10000000),0)
        tracker.observe_sample(sample(34900000),0)
        self.assertEqual(tracker.stage,'hold')
        self.assertFalse(tracker.complete)
        tracker.observe_sample(sample(35000000),0)
        self.assertEqual(tracker.stage,'departure')
        np.testing.assert_array_equal(tracker.tracker.points,points[1:])

    def test_real_frozen_plant_hover_has_measured_stationary_interval(self):
        points=[[0.,0.,50.],[60.,0.,50.],[120.,0.,50.]]
        skeleton={'agent_ids':['a'],'initial_states':[{'agent_id':'a','position_enu_m':points[0],
            'velocity_enu_m_s':[0.,0.,0.],'acceleration_enu_m_s2':[0.,0.,0.]}],
            'references':{'a':{'points_enu_m':points,'intermediate_dwell':{'waypoint_index':1,'duration_s':25.}}},
            'cruise_speed_m_s':5.,'initial_settle_s':20.,'terminal_hold_s':2.,
            'terminal_radius_m':1.,'terminal_speed_m_s':.15}
        run=execute(skeleton,{'a':0.})
        self.assertEqual(run['execution_status'],'completed')
        stationary=(np.linalg.norm(run['p'][:,0]-points[1],axis=1)<=1.)&(np.linalg.norm(run['v'][:,0],axis=1)<=.15)
        times=run['time_us'][stationary]/1e6
        self.assertGreaterEqual(times[-1]-times[0],25.)
        self.assertLess(np.linalg.norm(run['p'][-1,0]-points[-1]),1.)

    def test_five_calibration_round_limit_and_zero_flights_for_empty_pool(self):
        from scripts.run_v07_s2_episode_batch import run_episode_job
        descriptor={'skeleton_id':'test','family_id':'family','base_intent':'reconnaissance',
                    'common_draw':{'slot':0,'approach_mode':'same_direction'},'task_groups':[{}]}
        search={'candidate_budget':200,'attempted_candidates':200,'solo_flights_run':0,'rejection_reasons':{}}
        pool=[{'index':i,'skeleton':{},'bundle':None,'checks':{}} for i in range(8)]
        interval={m:{'below_warning':True} for m in ('synchronous','sequential')}
        interval['warning_threshold_m']=6.
        with TemporaryDirectory() as directory, patch('task_v07.expansion.candidate_search.episode_candidate_pool',return_value=(pool,dict(search))), \
             patch('scripts.run_v07_s2_episode_batch.calibrate_episode',return_value=({}, {}, {}, {'synchronous':{},'sequential':{}})) as calibrate, \
             patch('scripts.run_v07_s2_episode_batch.episode_interval_check',return_value=interval), \
             patch('scripts.run_v07_s2_episode_batch.write_result') as flight:
            rows=run_episode_job({'scene':{},'descriptor':descriptor,'out':directory})
            self.assertEqual(calibrate.call_count,5)
            flight.assert_not_called()
            self.assertTrue(all(row['reason']=='planning_spacing_rejection' for row in rows))
            self.assertEqual(len(list((Path(directory)/'test').glob('geometry_*'))),5)
        with TemporaryDirectory() as directory, patch('task_v07.expansion.candidate_search.episode_candidate_pool',return_value=([],dict(search))), \
             patch('scripts.run_v07_s2_episode_batch.calibrate_episode') as calibrate:
            rows=run_episode_job({'scene':{},'descriptor':descriptor,'out':directory})
            calibrate.assert_not_called()
            self.assertTrue(all(row['reason']=='geometry_infeasible' for row in rows))


if __name__=='__main__':unittest.main()
