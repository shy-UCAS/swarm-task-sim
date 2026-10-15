import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from task_v07.expansion.search_diagnostics import rejection, summarize


class SearchEvidenceTests(unittest.TestCase):
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
