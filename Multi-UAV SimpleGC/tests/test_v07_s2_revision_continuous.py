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
from task_v07.unified.config import load_generator
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

    def test_work_point_spacing_cannot_be_satisfied_by_far_retreat_endpoints(self):
        from task_v07.expansion.operation_parameters import work_point_spacing
        references={a:{'endpoint_enu_m':end,'observation_point_enu_m':point,
                       'planned_depth_point_enu_m':point,'planned_turn_point_enu_m':point}
                    for a,end,point in [('a',[0.,0.,100.],[10.,10.,100.]),
                                        ('b',[1000.,0.,100.],[15.9,10.,100.])]}
        self.assertFalse(work_point_spacing(references,'close_observation',5.)['observation_point']['valid'])
        references['b']['observation_point_enu_m']=[16.,10.,100.]
        self.assertTrue(work_point_spacing(references,'close_observation',8.)['observation_point']['valid'])
        references['b']['planned_depth_point_enu_m']=[24.9,10.,100.]
        references['b']['planned_turn_point_enu_m']=[25.,10.,100.]
        report=work_point_spacing(references,'feint',8.)
        self.assertFalse(report['depth_point']['valid'])
        self.assertTrue(report['turn_point']['valid'])

    def test_one_group_transit_quantile_maps_into_each_feasible_chord_interval(self):
        from task_v07.expansion.continuous_geometry import ContinuousTransit
        from task_v07.expansion.role_planners import _Context
        from test_v07_s2_expansion import scene
        planner=ContinuousTransit();ctx=_Context(scene(),'f',100.)
        for theta in (.3,2.1):
            direction=np.array([math.cos(theta),math.sin(theta)])
            normal=np.array([-direction[1],direction[0]])
            blocks=[planner.offsets(ctx,direction,normal,1.,2,20.,q) for q in (0.,.25,1.)]
            self.assertTrue(all(block is not None for block in blocks))
            self.assertAlmostEqual(blocks[1][0]['offset'],.75*blocks[0][0]['offset']+.25*blocks[2][0]['offset'])
            for block in blocks:
                self.assertAlmostEqual(block[1]['offset']-block[0]['offset'],20.)
                self.assertTrue(all(c['length']>=430. and c['difference']>=95. for c in block))

    def test_115_percent_filter_then_seeded_order(self):
        bound=100*load_generator()['combination']['same_direction_length_ratio_max']
        pool=[{'cost':v,'index':i} for i,v in enumerate((100,bound-.1,bound,bound+.1,200))]
        selected,report=choose_eligible(pool,True,random.Random(8))
        self.assertEqual({c['cost'] for c in selected},{100,bound-.1,bound})
        expected=pool[:3].copy();random.Random(8).shuffle(expected)
        self.assertEqual(selected,expected)
        self.assertEqual(report['feasible_candidates'],5)
        self.assertEqual(choose_eligible(pool,False,random.Random(8))[1]['eligible_candidates'],5)

    def test_every_registered_candidate_is_counted_without_calibration(self):
        from task_v07.expansion.candidate_search import episode_candidate_pool
        descriptor={'base_intent':'transit','role_seed':1,'common_draw':{'approach_mode':'same_direction'},
                    'task_groups':[{'role':'transit','group_id':'g','target_id':'f'}]}
        with patch('task_v07.expansion.group_candidate_pool.Context',return_value=SimpleNamespace()), \
             patch('task_v07.expansion.group_candidate_pool.role_parameters',return_value={}), \
             patch('task_v07.expansion.group_candidate_pool.draw_role',side_effect=lambda c,i:(None,'geometric_failure',{'index':i})) as draw:
            pool,report=episode_candidate_pool({},descriptor,backend='legacy')
            self.assertEqual(pool,[])
            self.assertEqual(draw.call_count,200)
            self.assertEqual(report['attempted_candidates'],200)
            self.assertEqual(report['rejection_reasons'],{'geometric_failure':200})
            self.assertEqual(report['solo_flights_run'],0)
            with self.assertRaises(ValueError):episode_candidate_pool({},descriptor,budget=199,backend='legacy')

    def test_each_group_has_its_own_115_percent_bound(self):
        bound=100*load_generator()['combination']['same_direction_length_ratio_max']
        costs=[(100,200),(200,100),(bound-1,bound-1),(bound+1,100)]
        pool=[{'index':i,'cost':sum(values),'cost_by_group':dict(zip(('g1','g2'),values))}
              for i,values in enumerate(costs)]
        selected,report=choose_eligible(pool,True,random.Random(8))
        self.assertEqual([c['index'] for c in selected],[2])
        self.assertEqual(report['minimum_approach_length_by_group_m'],{'g1':100,'g2':100})
        self.assertEqual(len(choose_eligible(pool,False,random.Random(8))[0]),4)

    def test_variable_observation_dwell_preserves_eighty_percent_criterion(self):
        from task_v07.expansion.formation_role_planners import Context,CloseObservationPlanner
        from task_v07.expansion.pipeline import COMMON_CONSTANTS,exclusion_policy
        from task_v07.labels import measure
        from copy import deepcopy
        from scripts.audit_v07_m1 import audit_episode
        from task_v07.io import save_json, write_csv
        from test_v07_s2_expansion import scene
        ids=['a','b']
        family={'sampling_seed':41,'cruise_speed_m_s':5.,'task_altitude_m':100.,
                'lateral_spacing_m':40.,'initial_states':[{'agent_id':a,'position_enu_m':[60.,1980.+40*i,100.]}
                                                       for i,a in enumerate(ids)]}
        group={'role':'reconnaissance','execution_method':'close_observation','target_id':'f','members':ids}
        ctx=Context(scene(),group,{'family':family,'approach_mode':'same_direction','planning_seed':10})
        minimum_plan=None
        for planned,minimum in ((25.,20.),(55.,44.)):
            ctx.operation_parameters={'observation_alert_clearance_m':50.,'planned_observation_dwell_s':planned,
                                      'observation_dwell_method':'hover'}
            result,reason=CloseObservationPlanner().attempt(ctx,math.pi)
            self.assertIsNotNone(result,reason)
            self.assertEqual(result['template']['close_observation']['minimum_dwell_s'],minimum)
            if minimum_plan is None: minimum_plan=deepcopy(result)
        # operation_parameters.py draws uniformly in [25,55] seconds.
        # Keep the planner 80% assertions above; M1 uses spatial dwell facts.
        result=minimum_plan
        samples=round(result['template']['close_observation']['planned_dwell_s']*10)+1
        sk={**COMMON_CONSTANTS,**result['template'],'base_intent':'reconnaissance','group_id':'g',
            'members':ids,'agent_ids':ids,'approach_mode':'same_direction','cruise_speed_m_s':5.,
            'continuous_geometry_draw':{},'exclusion_policy':exclusion_policy(scene(),'reconnaissance','f',ids)}
        positions=np.repeat(np.asarray([[sk['references'][a]['observation_point_enu_m'] for a in ids]]),samples,axis=0)
        run={'agent_ids':ids,'time_us':np.arange(samples,dtype=np.int64)*100000,'p':positions,
             'v':np.zeros_like(positions),'execution_status':'completed'}
        labels,frame=measure(scene(),sk,run,'synchronous')
        self.assertTrue(labels['agents']['a']['result']['conditions']['observation_dwell'])
        self.assertTrue(labels['agents']['a']['observed']['contribution']['observation_dwell']['detected'])
        with TemporaryDirectory() as directory:
            root=Path(directory)
            for name,value in [('public_scene',scene()),('task',sk),('labels',labels),
                               ('source',{'execution_status':run['execution_status']})]:
                save_json(root/(name+'.json'),value)
            write_csv(root/'truth.csv',ids,run['time_us'],positions,run['v'])
            np.savez_compressed(root/'truth_10hz.npz',**{k:run[k] for k in ('agent_ids','time_us','p','v')})
            np.savez_compressed(root/'frame_labels.npz',**frame)
            self.assertEqual(audit_episode(root)['status'],'PASS')
            for field in ('condition','confirm_frame_index'):
                with self.subTest(tampered_field=field):
                    changed=deepcopy(labels)
                    if field=='condition':
                        changed['agents']['a']['result']['conditions']['observation_dwell']=False
                        witness='a.result.conditions.observation_dwell'
                    else:
                        changed['agents']['a']['observed']['contribution']['observation_dwell'][field]+=11
                        witness='a.contribution.observation_dwell.'+field
                    import json
                    (root/'labels.json').write_text(json.dumps(changed),encoding='utf-8')
                    audit=audit_episode(root)
                    self.assertEqual(audit['status'],'P0_STOP',audit)
                    self.assertTrue(any(w['field']==witness for w in audit['event_or_metric_witnesses']),audit)
                    print('DWELL_TAMPER_REJECTED '+witness,flush=True)

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
        # M2Checks.test_A9_last_failure_and_history covers category history,
        # but not pool exhaustion at five rounds or an empty pool's zero flights.
        from scripts.run_v07_s2_episode_batch import run_episode_job
        descriptor={'skeleton_id':'test','family_id':'family','base_intent':'reconnaissance',
                    'common_draw':{'slot':0,'approach_mode':'same_direction'},'task_groups':[{}]}
        search={'candidate_budget':200,'attempted_candidates':200,'solo_flights_run':0,'rejection_reasons':{}}
        pool=[{'index':i,'skeleton':{'candidate_marker':i},'bundle':None,'checks':{}} for i in range(8)]
        failed={'status':'rejected','core_times_s':{},'completion_times_s':{},
                'failures':[{'agent_id':'a','conditions':['observation_dwell']}]}
        with TemporaryDirectory() as directory, patch('task_v07.expansion.candidate_search.episode_candidate_pool',return_value=(pool,dict(search))), \
             patch('task_v07.unified.rehearsal.rehearse',return_value=(failed,{})) as rehearse, \
             patch('task_v07.unified.timing.select_timing') as timing, \
             patch('scripts.run_v07_s2_episode_batch.execute') as flight, \
             patch('scripts.run_v07_s2_episode_batch.write_result') as export:
            rows=run_episode_job({'scene':{},'descriptor':descriptor,'out':directory})
            self.assertEqual(rehearse.call_count,5)
            self.assertEqual([c.args[1]['candidate_marker'] for c in rehearse.call_args_list],list(range(5)))
            timing.assert_not_called();flight.assert_not_called();export.assert_not_called()
            self.assertTrue(all(row['reason']=='rehearsal_failure' for row in rows))
            self.assertEqual(len(list((Path(directory)/'test').glob('geometry_*'))),5)
        with TemporaryDirectory() as directory, patch('task_v07.expansion.candidate_search.episode_candidate_pool',return_value=([],dict(search))), \
             patch('task_v07.unified.rehearsal.rehearse') as rehearse, \
             patch('task_v07.unified.timing.select_timing') as timing, \
             patch('scripts.run_v07_s2_episode_batch.execute') as flight:
            rows=run_episode_job({'scene':{},'descriptor':descriptor,'out':directory})
            rehearse.assert_not_called();timing.assert_not_called();flight.assert_not_called()
            self.assertTrue(all(row['reason']=='geometry_pool_empty' for row in rows))


if __name__=='__main__':unittest.main()
