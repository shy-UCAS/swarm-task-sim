import unittest
from task_v07.expansion.abort_references import select_abort_reference


class AbortReferenceTests(unittest.TestCase):
    def fixtures(self):
        descriptors={sid:{'descriptor':{'family_id':family,'map_id':map_id,'base_intent':'penetration'}}
            for sid,family,map_id in [('p1','f1','m1'),('p2','f2','m1'),('p3','f1','m1'),('p4','f1','m2')]}
        records={sid+'_synchronous':{'state':'generated','path':sid,'reason':None} for sid in descriptors}
        requested={'family_id':'f1','reference_skeleton_id':'p1'}
        return requested,descriptors,records

    def test_existing_reference_kept(self):
        requested,jobs,records=self.fixtures()
        sid,receipt=select_abort_reference(requested,jobs,records)
        self.assertEqual(sid,'p1')
        self.assertFalse(receipt['replaced'])
        self.assertEqual(len(receipt['attempts']),1)

    def test_planning_failure_falls_back_in_same_map_id_order_including_other_family(self):
        requested,jobs,records=self.fixtures()
        records['p1_synchronous'].update(state='infeasible',path=None,reason='geometry_infeasible')
        sid,receipt=select_abort_reference(requested,jobs,records)
        self.assertEqual(sid,'p2')
        self.assertTrue(receipt['replaced'])
        self.assertEqual([x['skeleton_id'] for x in receipt['attempts']],['p1','p2'])

    def test_all_same_map_plans_failed_records_not_run_mapping(self):
        requested,jobs,records=self.fixtures()
        for sid in ('p1','p2','p3'):
            records[sid+'_synchronous'].update(state='infeasible',path=None,reason='planning_spacing_rejection')
        sid,receipt=select_abort_reference(requested,jobs,records)
        self.assertEqual(sid,'p1')
        self.assertTrue(receipt['all_planning_failed'])
        self.assertIsNone(receipt['selected_reference_skeleton_id'])
        self.assertEqual([x['skeleton_id'] for x in receipt['attempts']],['p1','p2','p3'])

    def test_generation_error_is_not_a_planning_fallback_trigger(self):
        requested,jobs,records=self.fixtures()
        records['p1_synchronous'].update(state='generation_error',reason='minimum_separation_below_2m')
        self.assertEqual(select_abort_reference(requested,jobs,records)[0],'p1')


if __name__=='__main__':unittest.main()
