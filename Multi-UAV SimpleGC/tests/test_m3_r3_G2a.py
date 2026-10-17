import copy,unittest
from scripts.audit_m3_r3_G2a import ATTEMPT,classify_probe,read
class G2aTests(unittest.TestCase):
    def test_probe05_previous_research_fail_is_diagnostic_only(self):
        original=read(ATTEMPT/'probe_05/r3/result.json');result=classify_probe(original)
        self.assertEqual(original['status'],'FAIL')
        self.assertFalse(original['checks']['precision'])
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['diagnostics']['absolute_precision'],'FAIL')
        self.assertFalse(result['diagnostics']['relative_by_phase']['approach']['passed'])
    def test_physical_failure_still_blocks_probe05(self):
        original=read(ATTEMPT/'probe_05/r3/result.json');original['checks']['physical']=False
        self.assertEqual(classify_probe(original)['status'],'FAIL')
    def test_b2_bitwise_failure_still_blocks_probe05(self):
        original=read(ATTEMPT/'probe_05/r3/result.json');original['checks']['bitwise_arrays']=False
        self.assertEqual(classify_probe(original)['status'],'FAIL')
    def test_other_probe_absolute_tube_contract_is_unchanged(self):
        original=read(ATTEMPT/'probe_01/r3/result.json');original['checks']['precision']=False
        self.assertEqual(classify_probe(original)['status'],'FAIL')
