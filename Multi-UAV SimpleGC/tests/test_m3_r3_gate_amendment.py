"""Approved N/A semantics without dropping tasks or weakening other gates."""
import copy,unittest
from test_m3_r3_r0_audit import pair
from scripts.m3_r3_gates import evaluate

class AmendmentTests(unittest.TestCase):
    def setUp(self):
        self.rows=[pair('known','line_abreast','straight','straight'),
                   pair('unknown','equal_strip_rectangular_spiral','unclear','unclear')]
    def test_zero_reference_is_na_not_success_percentage(self):
        r=evaluate(self.rows,self.rows)
        self.assertEqual(r['status'],'PASS')
        na=[x for x in r['patterns'] if x['flight_pattern']=='equal_strip_rectangular_spiral']
        self.assertEqual(len(na),2)
        for x in na:
            self.assertEqual(x['status'],'N/A');self.assertFalse(x['applicable'])
            self.assertIsNone(x['passed_check']);self.assertIsNone(x['all_task_rate'])
    def test_known_reference_disagreement_fails_both_channels(self):
        rows=copy.deepcopy(self.rows)
        for c in ('truth','observation'):rows[0]['motion_slots'][c].update(candidate='unclear',agree=False)
        r=evaluate(rows,self.rows)
        self.assertEqual(r['status'],'FAIL')
        self.assertTrue(all(x['status']=='FAIL' for x in r['patterns'] if x['flight_pattern']=='line_abreast'))
    def test_na_tasks_remain_in_full_success_and_execution_denominators(self):
        r=evaluate(self.rows,self.rows)
        self.assertEqual(r['aggregate']['tasks'],2)
        self.assertEqual(r['aggregate']['success']['total'],2)
        self.assertEqual(r['aggregate']['motion_reference_known']['truth']['total'],1)
        self.assertEqual(evaluate(self.rows[:1],self.rows)['status'],'FAIL')
    def test_missing_formerly_known_pattern_cannot_become_na(self):
        r=evaluate(self.rows[1:],self.rows)
        self.assertEqual(r['status'],'FAIL')
        self.assertTrue(all(x['status']=='FAIL' for x in r['patterns'] if x['flight_pattern']=='line_abreast'))
    def test_candidate_cannot_change_reference_labels(self):
        rows=copy.deepcopy(self.rows)
        for c in ('truth','observation'):rows[0]['motion_slots'][c]['reference']='unclear'
        self.assertFalse(evaluate(rows,self.rows)['required_checks']['reference_identity_preserved'])
    def test_na_does_not_relax_numerical_nonregression(self):
        rows=copy.deepcopy(self.rows)
        for x in rows:x['duration_relative_error']=1e-5
        self.assertFalse(evaluate(rows,self.rows)['required_checks']['total_duration_abs_relative_median'])
