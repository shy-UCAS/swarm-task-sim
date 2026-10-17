import copy
import unittest
import numpy as np
from scripts.revalidate_m3_r3_r1 import parse_log,regression,array_diff,normalized,OLD

class R1GateTests(unittest.TestCase):
    def setUp(self):
        self.base=parse_log((OLD/'R1_fixed_base_attribution.txt').read_text())
        self.current=parse_log((OLD/'unit_tests.txt').read_text())
        self.white=list(self.base['failures'])
    def test_exact_known_failures_are_not_passes(self):
        r=regression(self.current,self.base,self.white)
        self.assertEqual((r['status'],r['executed'],r['passed'],r['baseline_known_failure']),('PASS',209,205,4))
    def test_changed_failure_location_is_new_regression(self):
        key=self.white[0]
        self.current['failures'][key]['traceback']+='\nnew frame'
        self.assertEqual(regression(self.current,self.base,self.white)['status'],'FAIL')
    def test_changed_exception_is_new_regression(self):
        self.current['failures'][self.white[0]]['kind']='FAIL'
        self.assertEqual(regression(self.current,self.base,self.white)['status'],'FAIL')
    def test_unexpected_skip_blocks(self):
        key=next(k for k,v in self.current['outcomes'].items() if v=='ok')
        self.current['outcomes'][key]="skipped 'unexpected'"
        self.assertEqual(regression(self.current,self.base,self.white)['status'],'FAIL')
    def test_missing_test_blocks(self):
        del self.current['outcomes'][next(iter(self.base['outcomes']))]
        self.assertEqual(regression(self.current,self.base,self.white)['status'],'FAIL')
    def test_signed_zero_difference_is_not_hidden(self):
        diff=array_diff(np.array([0.]),np.array([-0.]))
        self.assertEqual(diff['index'],[0])
        self.assertNotEqual(diff['actual_bytes'],diff['historical_bytes'])
    def test_incomplete_log_rejected(self):
        with self.assertRaises(ValueError):parse_log('test_one (a.b.test_one) ... ok\nRan 2 tests in 0.1s\nOK\n')

    def test_end_to_end_startup_dry_run_validates_locked_inputs(self):
        import json,subprocess,sys
        from scripts.revalidate_m3_r3_r1 import PROJECT
        run=subprocess.run([sys.executable,'-B',str(PROJECT/'scripts/revalidate_m3_r3_r1.py'),'--dry-run'],
                           cwd=PROJECT,capture_output=True,text=True,timeout=120)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        result=json.loads(run.stdout)
        self.assertEqual(result['status'],'DRY_RUN_PASS')
        self.assertEqual(result['input_files'],8608)
        self.assertEqual({p.replace('\\','/').rsplit('/',1)[-1] for p in result['mutable_paths']},{'route_tracker.py','contracts.py'})
