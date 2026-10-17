"""R4 harness dispatch and raw-evidence gates; no old tests changed."""
import copy
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import run_m3_r3_r4 as h
from task_v07.expansion.contracts import P0ContractError

class R4HarnessTests(unittest.TestCase):
    def test_both_execution_bindings_select_r3_and_restore(self):
        import scripts.run_v07_s2_episode_batch as batch
        import task_v07.unified.rehearsal as rehearsal
        old=(batch.execute,rehearsal.execute); calls=[]; versions=[]
        def fake(*args,**kwargs):
            versions.append(kwargs['reference_version'])
            return dict(config_sha256=h.CONFIG_SHA256,execution_status='completed')
        with h.r3_execution(calls,fake):
            batch.execute({},{});rehearsal.execute({},{},only_agent='a')
        self.assertEqual(versions,['r3','r3']);self.assertEqual(len(calls),2)
        self.assertEqual((batch.execute,rehearsal.execute),old)
        with h.r3_execution([],fake):
            with self.assertRaises(P0ContractError):batch.execute({},{},reference_version='r2')

    def test_historical_pair_and_physical_audits_use_raw_artifacts(self):
        plan=h.read(h.PLAN)
        item=next(s for s in plan['R4']['skeletons'] if 'FE_INT_30' in s['sources'])
        root=Path(item['historical_attempt']);sid=item['skeleton_id']
        rows=[h.read(root/sid/m/'metrics.json') for m in plan['R4']['modes']]
        result=h.pair_result(root,sid,rows,h.CONFIG_SHA)
        self.assertTrue(result['paired']);self.assertTrue(result['hard_physical_audit_passed'])
        changed=copy.deepcopy(rows);changed[0]['all_groups_complete']=False
        self.assertFalse(h.pair_result(root,sid,changed,h.CONFIG_SHA)['paired'])
        real_read=h.read
        def bad_minimum(path):
            value=real_read(path)
            if Path(path).name=='labels.json':value['generation_quality']['minimum_separation_m']=1.99
            return value
        with patch.object(h,'read',bad_minimum):
            self.assertFalse(h.pair_result(root,sid,rows,h.CONFIG_SHA)['hard_physical_audit_passed'])

    def test_qc_reads_historical_episode_and_preserves_member_count(self):
        item=next(s for s in h.read(h.PLAN)['R4']['skeletons'] if 'FE_INT_30' in s['sources'])
        root=Path(item['historical_attempt'])/item['skeleton_id']/'synchronous'
        qc=h.qc_episode(root,item['skeleton_id'],'synchronous')
        self.assertEqual(len(qc['members']),len(h.read(root/'task.json')['agent_ids']))
        self.assertEqual(sum(r['members'] for r in h.qc_summary([qc])),len(qc['members']))

if __name__=='__main__':unittest.main()
