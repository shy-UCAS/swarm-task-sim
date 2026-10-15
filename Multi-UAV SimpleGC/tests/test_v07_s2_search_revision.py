import unittest
from task_v07.expansion.search_diagnostics import rejection, summarize


class SearchEvidenceTests(unittest.TestCase):
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
