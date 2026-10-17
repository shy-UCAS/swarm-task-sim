import unittest
from scripts.run_m3_r3_r3 import function_scope
class R3ScopeTests(unittest.TestCase):
    def test_allowed_function_only(self):
        self.assertEqual(function_scope('x=1\ndef ingress_issues(): return 1\n','x=1\ndef ingress_issues(): return 2\n'),dict(outside_function_unchanged=True,function_changed=True))
    def test_extra_algorithm_change_rejected(self):
        self.assertFalse(function_scope('x=1\ndef ingress_issues(): return 1\n','x=2\ndef ingress_issues(): return 2\n')['outside_function_unchanged'])
    def test_missing_function_is_not_scope_pass(self):
        with self.assertRaises(ValueError):function_scope('x=1','x=2')

class R3VerboseParserTests(unittest.TestCase):
    def test_docstring_description_on_second_line(self):
        from scripts.revalidate_m3_r3_r1 import parse_log
        text="test_a (module.Class.test_a)\nA description ... ok\ntest_b (module.Class.test_b) ... ok\n\nRan 2 tests in 0.001s\n\nOK\n"
        result=parse_log(text)
        self.assertEqual(result['count'],2)
        self.assertEqual(result['outcomes'],{'module.Class.test_a':'ok','module.Class.test_b':'ok'})
    def test_complete_failed_attempt_log_dryrun(self):
        from scripts.revalidate_m3_r3_r1 import parse_log
        from scripts.run_m3_r3_r3 import DATA
        log=DATA/'fast_dynamics/m3/m3_r3_r3_attempt01/baseline_tests.txt'
        result=parse_log(log.read_text())
        self.assertEqual(result['count'],476)
        self.assertEqual(sum(v=='ok' for v in result['outcomes'].values()),458)
        self.assertEqual(sum(v=='FAIL' for v in result['outcomes'].values()),6)
        self.assertEqual(sum(v=='ERROR' for v in result['outcomes'].values()),12)
        self.assertEqual(len(result['failures']),18)
