import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from task_v07.expansion.search_diagnostics import rejection, summarize


class SearchEvidenceTests(unittest.TestCase):
    def test_empty_first_group_does_not_censor_other_group_budgets(self):
        from unittest.mock import patch
        from task_v07.expansion.candidate_search import episode_candidate_pool
        groups=[{'role':'transit','group_id':g,'target_id':'f'} for g in ('a','b','c')]
        descriptor={'base_intent':'transit','role_seed':4,'common_draw':{'approach_mode':'multi_direction'},'task_groups':groups}
        with patch('task_v07.expansion.group_candidate_pool.Context',return_value=SimpleNamespace()), \
             patch('task_v07.expansion.group_candidate_pool.role_parameters',return_value={}), \
             patch('task_v07.expansion.group_candidate_pool.draw_role',side_effect=lambda c,i:(None,'local_failure',{'index':i})) as draw:
            pool,report=episode_candidate_pool({},descriptor)
        self.assertEqual(pool,[])
        self.assertEqual(draw.call_count,600)
        self.assertEqual(report['group_attempt_counts'],{'a':200,'b':200,'c':200})
        self.assertEqual(report['combination_search']['attempts'],0)
        self.assertTrue(all(v['classification']=='search_budget_exhausted' for v in report['group_terminations'].values()))
        self.assertTrue(all(v['wall_s']>=v['geometry_wall_s']>=0 for v in report['group_search_metrics'].values()))

    def test_combination_order_is_bounded_unique_and_reproducible(self):
        import random
        from itertools import product
        from task_v07.expansion.group_candidate_pool import combination_indices
        self.assertEqual(set(combination_indices([2,3],1000,random.Random(8))),set(product(range(2),range(3))))
        choices=combination_indices([200,200,200],1000,random.Random(8))
        self.assertEqual(len(set(choices)),1000)
        self.assertEqual(choices,combination_indices([200,200,200],1000,random.Random(8)))
        self.assertNotEqual(choices,combination_indices([200,200,200],1000,random.Random(9)))
        self.assertEqual(combination_indices([2,0,3],1000,random.Random(8)),[])

    def context(self,extra_facility=False):
        from test_v07_s2_expansion import scene
        from task_v07.expansion.formation_role_planners import Context
        source=scene()
        if extra_facility:
            source['entities'].append({'id':'other','type':'facility','geometry':{'type':'Circle','center_m':[3400.,2000.],'radius_m':20.}})
            for layer,radius in [('warning',800.),('alert',250.),('protected',100.)]:
                source['entities'].append({'id':'other_'+layer,'type':'protection_zone','facility_id':'other','layer':layer,
                    'offset_m':radius-20.,'geometry':{'type':'Circle','center_m':[3400.,2000.],'radius_m':radius}})
        ids=['a','b','c']
        family={'sampling_seed':41,'cruise_speed_m_s':5.,'task_altitude_m':100.,'lateral_spacing_m':20.,
                'initial_states':[{'agent_id':a,'position_enu_m':[60.,1980.+20*i,100.]} for i,a in enumerate(ids)]}
        return Context(source,{'role':'monitoring','target_id':'f','members':ids},
                       {'family':family,'approach_mode':'same_direction','planning_seed':10,'geometry_slot':0,'target_warning_only':True})

    def test_collection_may_overlap_other_warning_but_not_alert(self):
        from task_v07.expansion.warning_approach import collection_point_valid
        ctx=self.context(True)
        self.assertTrue(collection_point_valid(ctx,[2800.,2000.],35.))
        self.assertTrue(ctx.planner(35.,warnings=True).free([2800.,2000.]))
        self.assertFalse(collection_point_valid(ctx,[3200.,2000.],35.))
        self.assertFalse(collection_point_valid(ctx,[2500.,2000.],35.))

    def test_near_collection_keeps_exact_clearance_and_hundred_metre_heading(self):
        import math,numpy as np
        from task_v07.expansion.warning_approach import warning_ingress
        from task_v07.expansion.area_search import planned_core_distance,heading_before_distance
        from task_v07.geometry import geometry_facts
        from task_v07.labels import heading_span_deg
        ctx=self.context();ctx.collection_clearance_m=50.
        ingress,reason=warning_ingress(ctx,math.pi)
        self.assertIsNotNone(ingress,reason)
        for block in ingress['blocks']:
            self.assertAlmostEqual(float(geometry_facts(ctx.zones['warning']['geometry'],block['collection_point_enu_m'][:2])['signed_distance_m']),50.)
            self.assertEqual(block['shared_route_margin_m'],35.+1.5*block['half_width_m']+2.)
        headings=[]
        for path in ingress['routes'].values():
            path=np.asarray(path);distance=planned_core_distance(path,ctx.zones['warning']['geometry'])
            headings.append(heading_before_distance(path,distance))
        self.assertLess(heading_span_deg(headings),1e-8)

    def test_six_registered_phase_counterexamples_pass_original_two_mode_gate(self):
        from task_v07.expansion.monitoring_phases import shared_phase_candidates
        rows=json.loads(Path(__file__).with_name('s2_monitoring_phase_witnesses.json').read_text())
        self.assertEqual(len(rows),6)
        for row in rows:
            with self.subTest(skeleton=row['skeleton_id']):
                self.assertGreater(row['original_score_s'],row['allowed_s'])
                ctx=SimpleNamespace(**{k:row[k] for k in ('group','params','family','speed','slot')})
                stats={}
                phases=shared_phase_candidates(ctx,row['radius_m'],staged=True,diagnostics=stats)
                self.assertLessEqual(phases[0]['estimated_max_interval_s'],row['allowed_s'])
                self.assertEqual(set(phases[0]['phases']),set(row['group']['members']))
                self.assertGreater(stats['evaluations'],0)
                self.assertLessEqual(stats['evaluations'],4*192*901)
                self.assertTrue(stats['stages'])

    def test_failed_random_proposal_does_not_prove_geometric_infeasibility(self):
        item = rejection('nominal_revisit_geometry_infeasible')
        self.assertEqual(item['classification'],'local_proposal_failure')
        self.assertFalse(item['global_infeasibility_claimed'])

    def test_geometric_witness_has_limited_scope(self):
        item = rejection('blocked_ring',evidence=[{'constraint':'constraint_clearance','entity_id':'obstacle_01','segment':3}])
        self.assertEqual(item['classification'],'geometric_infeasibility')
        self.assertFalse(item['global_infeasibility_claimed'])
        end = rejection('no_candidate',scope='group_search',exhausted=True)
        self.assertEqual(summarize([{'rejection':item},{'rejection':end}]),
                         {'geometric_infeasibility':1,'search_budget_exhausted':1})


if __name__=='__main__': unittest.main()
