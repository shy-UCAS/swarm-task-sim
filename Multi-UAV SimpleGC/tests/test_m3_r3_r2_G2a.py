import copy,unittest
from scripts.run_m3_r3_r2 import read,BASE_PAIRS,gate_from_pairs,numerical_report
class R2G2aTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.base=read(BASE_PAIRS)
    def test_frozen_r2_self_comparison_passes_with_all_282(self):
        r=gate_from_pairs(self.base,self.base)
        self.assertEqual(r['status'],'PASS');self.assertEqual(r['completed_pairs'],282)
        self.assertEqual(sum(p['task_count'] for p in r['patterns'] if p['channel']=='truth'),282)
    def test_numerical_deterioration_is_reported_not_hard_gate(self):
        rows=copy.deepcopy(self.base)
        for i,r in enumerate(rows):r['duration_relative_error']=1.+i
        result=gate_from_pairs(rows,self.base)
        self.assertEqual(result['status'],'PASS')
        details=result['numerical_diagnostics']['total_duration_abs_relative_median']
        self.assertEqual(details['worsened_count'],282);self.assertEqual(len(details['worst10']),10)
    def test_missing_task_cannot_pass(self):
        self.assertEqual(gate_from_pairs(self.base[:-1],self.base)['status'],'FAIL')
    def test_physical_quality_failure_cannot_be_downgraded(self):
        rows=copy.deepcopy(self.base);rows[0]['candidate_quality']=False
        self.assertEqual(gate_from_pairs(rows,self.base)['status'],'FAIL')
    def test_known_reference_disappearance_is_not_na(self):
        rows=copy.deepcopy(self.base)
        for r in rows:
            if r['flight_pattern']=='staggered_same_loop':
                for c in ('truth','observation'):r['motion_slots'][c]['reference']='unclear'
        self.assertEqual(gate_from_pairs(rows,self.base)['status'],'FAIL')
