import json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import numpy as np
from task_v07.expansion.contracts import P0ContractError
from task_v07.expansion.solo_spacing import (solo_interval_check,load_saved_solos,prediction_error,shifted_positions)


class SoloSpacingTests(unittest.TestCase):
    def crossing(self):
        t=np.arange(21,dtype=np.int64)*100000
        x=np.linspace(-20.,20.,len(t))
        return {a:{'time_us':t,'p':np.stack((x if a=='a' else np.zeros_like(x),
                x if a=='b' else np.zeros_like(x),np.full_like(x,100.)),axis=1)[:,None,:],
                'v':np.zeros((len(t),1,3)),'agent_ids':[a]} for a in ('a','b')}

    def plans(self):
        return {'synchronous':{'departure_delays_s':{'a':0.,'b':0.}},
                'sequential':{'departure_delays_s':{'a':0.,'b':1.}}}

    def test_real_delay_and_full_route_hold_without_duplicate_settle(self):
        solos=self.crossing();plans=self.plans()
        report=solo_interval_check(solos,plans)
        self.assertTrue(report['synchronous']['below_warning'])
        self.assertEqual(report['synchronous']['closest_pair']['t_s'],1.)
        self.assertEqual(report['synchronous']['minimum_m'],0.)
        self.assertFalse(report['sequential']['below_warning'])
        self.assertEqual(report['sequential']['predicted_end_s'],3.)
        t,p,ids=shifted_positions(solos,plans['sequential']['departure_delays_s'])
        np.testing.assert_array_equal(p[5,1],solos['b']['p'][0,0])
        np.testing.assert_array_equal(p[-1,0],solos['a']['p'][-1,0])

    def test_finished_agents_remain_present_until_last_route_ends(self):
        def solo(agent,x):
            p=np.c_[x,np.zeros(len(x)),np.full(len(x),100.)][:,None,:]
            return {'agent_ids':[agent],'time_us':np.arange(len(x),dtype=np.int64)*100000,'p':p}
        solos={'a':solo('a',np.linspace(0.,20.,11)),'b':solo('b',np.linspace(70.,20.,31))}
        plans={m:{'departure_delays_s':{'a':0.,'b':0.}} for m in ('synchronous','sequential')}
        result=solo_interval_check(solos,plans)
        self.assertEqual(result['sequential']['minimum_m'],0.)
        self.assertEqual(result['sequential']['closest_pair']['t_s'],3.)

    def test_prediction_comparison_aligns_physical_ids(self):
        solos=self.crossing();plans=self.plans()
        t,p,ids=shifted_positions(solos,plans['sequential']['departure_delays_s'])
        actual={'time_us':t,'p':p[:,::-1], 'agent_ids':ids[::-1]}
        prediction=solo_interval_check(solos,plans)['sequential']
        error=prediction_error(solos,plans['sequential'],actual,prediction)
        self.assertEqual(error['minimum_error_predicted_minus_actual_m'],0.)
        self.assertEqual(error['position_error_max_m'],0.)

    def test_quick_b_selection_prefers_multiple_groups_then_identifier(self):
        from scripts.run_v07_s2_search_quick_b import choose_bones
        from scripts.v07_s2_revision_diagnostics import INTENTS
        rows=[]
        for intent in INTENTS:
            for mode in ('same_direction','multi_direction'):
                for sid,groups,success in (('000',1,True),('aaa',3,True),('bbb',2,True),('000_bad',3,False)):
                    rows.append({'skeleton_id':f'{intent}_{mode}_{sid}','intent':intent,
                        'approach_mode':mode,'group_count':str(groups),'success':success})
        self.assertEqual(len(choose_bones({'skeletons':rows})),10)
        self.assertTrue(all(r['skeleton_id'].endswith('_aaa') for r in choose_bones({'skeletons':rows})))
        with self.assertRaises(ValueError):choose_bones({'skeletons':[r for r in rows if r['intent']!=INTENTS[0]]})

    def test_saved_solo_validation_rejects_missing_grid_or_wrong_id(self):
        solos=self.crossing()
        with TemporaryDirectory() as tmp:
            for a,run in solos.items():np.savez(Path(tmp)/f'single_agent_{a}.npz',**run)
            loaded=load_saved_solos(tmp,['a','b'])
            self.assertEqual(solo_interval_check(loaded,self.plans())['synchronous']['minimum_m'],0.)
            wrong=dict(solos['a']);wrong['agent_ids']=['b']
            np.savez(Path(tmp)/'single_agent_a.npz',**wrong)
            with self.assertRaises(P0ContractError):load_saved_solos(tmp,['a','b'])
        solos['a']['time_us'][10]+=1
        with self.assertRaises(P0ContractError):solo_interval_check(solos,self.plans())

    def test_overlay_rejection_changes_combination_and_caps_five_solo_rounds(self):
        from scripts.run_v07_s2_episode_batch import run_episode_job
        descriptor={'skeleton_id':'test','family_id':'family','base_intent':'reconnaissance',
            'common_draw':{'slot':0,'approach_mode':'same_direction'},'task_groups':[{}]}
        search={'candidate_budget':200,'attempted_candidates':200,'solo_flights_run':0,'rejection_reasons':{}}
        pool=[{'index':i,'skeleton':{'agent_ids':['a','b']},'bundle':None,'checks':{}} for i in range(8)]
        interval={m:{'below_warning':False} for m in ('synchronous','sequential')}
        interval['warning_threshold_m']=10.
        with TemporaryDirectory() as tmp, patch('task_v07.expansion.candidate_search.episode_candidate_pool',return_value=(pool,search)), \
             patch('scripts.run_v07_s2_episode_batch.calibrate_episode',return_value=({}, {}, self.crossing(),self.plans())) as calibrate, \
             patch('scripts.run_v07_s2_episode_batch.episode_interval_check',return_value=interval), \
             patch('scripts.run_v07_s2_episode_batch.execute') as joint:
            rows=run_episode_job({'scene':{},'descriptor':descriptor,'out':tmp})
            self.assertEqual(calibrate.call_count,5);joint.assert_not_called()
            self.assertTrue(all(r['reason']=='planning_spacing_rejection' for r in rows))
            saved=json.loads((Path(tmp)/'test/candidate_search.json').read_text())
            self.assertEqual(saved['solo_overlay_rejections'],5)
            self.assertEqual(saved['additional_overlay_rejections'],5)
            self.assertEqual(len(list((Path(tmp)/'test').glob('geometry_*/solo_overlay_interval.json'))),5)


if __name__=='__main__':unittest.main()
