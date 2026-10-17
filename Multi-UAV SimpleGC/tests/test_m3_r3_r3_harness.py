import unittest
from scripts.run_m3_r3_r3 import function_scope
class R3ScopeTests(unittest.TestCase):
    def test_allowed_function_only(self):
        self.assertEqual(function_scope('x=1\ndef ingress_issues(): return 1\n','x=1\ndef ingress_issues(): return 2\n'),dict(outside_function_unchanged=True,function_changed=True))
    def test_extra_algorithm_change_rejected(self):
        self.assertFalse(function_scope('x=1\ndef ingress_issues(): return 1\n','x=2\ndef ingress_issues(): return 2\n')['outside_function_unchanged'])
    def test_missing_function_is_not_scope_pass(self):
        with self.assertRaises(ValueError):function_scope('x=1','x=2')
