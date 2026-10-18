"""Observed abort facts cannot use a future turn or a private branch timestamp."""
import unittest
import tempfile
from pathlib import Path
import numpy as np
from task_v07.expansion.abort_measurement import observed_abort
from task_v07.expansion.abort_planning import verify_abort_prefix
from task_v07.expansion.contracts import P0ContractError


class AbortEvidenceTests(unittest.TestCase):
    def test_full_abort_labels_and_independent_audit(self):
        from test_v07_s2_expansion import scene
        from task_v07.expansion.pipeline import COMMON_CONSTANTS, exclusion_policy
        from task_v07.labels import measure
        from task_v07.io import save_json, write_csv
        from scripts.audit_v07_s2_conditions import audit_conditions
        x=np.r_[np.linspace(3000.,2225.,1551),np.linspace(2225.,2910.,1371)[1:],np.full(30,2910.)]
        p=np.zeros((len(x),2,3));p[:,:,0]=x[:,None];p[:,:,1]=[1950.,2050.];p[:,:,2]=100.
        v=np.zeros_like(p);v[:1550,:,0]=-5.;v[1550:2920,:,0]=5.
        ids=['a','b'];t=np.arange(len(x),dtype=np.int64)*100000
        sk={**COMMON_CONSTANTS,'role':'intrusion','execution_method':'intrusion','base_intent':'penetration',
            'target_id':'f','group_id':'g','members':ids,'agent_ids':ids,'approach_mode':'same_direction',
            'required_intrusion_depth_m':20.,'abort_observation':{'branch_time_us':12345600},
            'references':{a:{'endpoint_enu_m':p[-1,i].tolist(),'retreat_required':True,'retreat_warning_clearance_m':200.}
                          for i,a in enumerate(ids)},'exclusion_policy':exclusion_policy(scene(),'feint','f',ids)}
        run={'agent_ids':ids,'time_us':t,'p':p,'v':v,'execution_status':'completed'}
        labels,frame=measure(scene(),sk,run,'synchronous')
        self.assertEqual(labels['task_groups']['g']['observed']['coordination']['classification'],'unknown')
        self.assertEqual(labels['cluster']['result']['status'],'failure')
        self.assertTrue(labels['task_groups']['g']['result']['conditions']['abort_group_withdrawal_observed'])
        for a in ids:
            self.assertIsNone(labels['agents'][a]['observed']['core_event']['t_s'])
            for condition in ('abort_entered_alert', 'abort_no_protected_entry',
                              'abort_left_warning_after_turn', 'abort_ended_outside_warning'):
                self.assertTrue(labels['agents'][a]['result']['conditions'][condition], condition)
            self.assertIn('approached_then_withdrew',labels['agents'][a]['observed']['behaviors'])
        prefix,_=measure(scene(),sk,run,'synchronous',cutoff_s=160.)
        self.assertNotIn('approached_then_withdrew',prefix['task_groups']['g']['observed']['behaviors'])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name,value in [('public_scene.json',scene()),('task.json',sk),('labels.json',labels),
                               ('source.json', {'execution_status': run['execution_status']})]:
                save_json(root/name,value)
            write_csv(root/'truth.csv',ids,t,p,v)
            np.savez_compressed(root/'truth_10hz.npz',agent_ids=np.array(ids),time_us=t,p=p,v=v)
            np.savez_compressed(root/'frame_labels.npz',**frame)
            report=audit_conditions(root)
        self.assertEqual(report['status'],'PASS',report)
        self.assertEqual(report['uncovered_conditions'],[])

    def test_frozen_engine_route_switch_preserves_exact_prefix(self):
        from copy import deepcopy
        from task_v07.execution import execute
        from task_v07.expansion.pipeline import COMMON_CONSTANTS
        ids=['a','b'];starts=[[0.,0.,100.],[0.,40.,100.]];ends=[[160.,0.,100.],[160.,40.,100.]]
        sk={**COMMON_CONSTANTS,'members':ids,'agent_ids':ids,'cruise_speed_m_s':5.,
            'initial_states':[{'agent_id':a,'position_enu_m':p,'velocity_enu_m_s':[0.,0.,0.],
                               'acceleration_enu_m_s2':[0.,0.,0.]} for a,p in zip(ids,starts)],
            'references':{a:{'points_enu_m':[p,e],'endpoint_enu_m':e} for a,p,e in zip(ids,starts,ends)}}
        delays={'a':0.,'b':4.}
        source=execute(sk,delays)
        frame=int(np.flatnonzero(source['time_us']==35000000)[0])
        point=source['p'][frame,0].tolist()
        changed=deepcopy(sk)
        changed['references']['a'].update(points_enu_m=[starts[0],point,starts[0]],endpoint_enu_m=starts[0])
        branch={'time_us':35000000,'routes_by_agent':{'a':[point,starts[0]]},
                'initial_routes_by_agent':{a:sk['references'][a]['points_enu_m'] for a in ids}}
        aborted=execute(changed,delays,route_switch=branch)
        self.assertTrue(aborted['route_switch_applied'])
        self.assertEqual(aborted['execution_status'],'completed')
        self.assertEqual(verify_abort_prefix(source,aborted,35000000)['status'],'PASS')
        self.assertLessEqual(np.linalg.norm(aborted['p'][-1,0]-starts[0]),1.)

    def trace(self):
        # Exact 10 Hz synthetic radial approach, turn in alert band, then exit.
        distance = np.r_[np.linspace(300., 150., 101), np.linspace(151., 400., 150)]
        t = np.arange(len(distance), dtype=np.int64) * 100000
        p = np.c_[distance, np.zeros((len(t), 2))]
        levels = np.where(distance <= 100., 3, np.where(distance <= 200., 2, np.where(distance <= 250., 1, 0)))
        return t, p, distance, levels

    def test_complete_approach_withdrawal_is_observed_and_prefix_cannot_claim_it(self):
        from scripts.audit_v07_abort_facts import independent_abort
        t, p, d, levels = self.trace()
        facts, conditions = observed_abort(t, p, d, levels, p[-1], 1., True)
        self.assertEqual((facts, conditions), independent_abort(t, p, d, levels, p[-1], 1., True))
        self.assertTrue(facts['approached_then_withdrew'])
        self.assertTrue(all(v is True for v in conditions.values()))
        self.assertEqual(facts['turn_frame'], 100)
        prefix, checks = observed_abort(t[:90], p[:90], d[:90], levels[:90], p[-1], 1., False)
        self.assertFalse(prefix['approached_then_withdrew'])
        self.assertIsNone(prefix['warning_exit_after_turn_s'])
        self.assertIsNone(checks['abort_no_protected_entry'])

    def test_protected_entry_cannot_be_called_abort_withdrawal(self):
        t, p, d, levels = self.trace()
        levels[100] = 3
        facts, checks = observed_abort(t, p, d, levels, p[-1], 1., True)
        self.assertFalse(checks['abort_no_protected_entry'])
        self.assertFalse(facts['approached_then_withdrew'])

    def test_prefix_requires_bit_exact_state_and_identity(self):
        t, p, _, _ = self.trace()
        run = {'agent_ids': ['a'], 'time_us': t, 'p': p[:, None], 'v': p[:, None] * 0., 'a': p[:, None] * 0.}
        changed = {**run, 'p': run['p'].copy()}
        changed['p'][101, 0, 0] += 1.
        self.assertEqual(verify_abort_prefix(run, changed, t[100])['status'], 'PASS')
        changed['p'][1, 0, 0] += 1e-10
        with self.assertRaises(P0ContractError):
            verify_abort_prefix(run, changed, t[100])


if __name__ == '__main__':
    unittest.main()
