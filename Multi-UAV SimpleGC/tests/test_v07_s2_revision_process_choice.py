import unittest
from scripts.v07_s2_revision_process_comparison import choose


class RevisionProcessChoiceTests(unittest.TestCase):
    def test_prefer_retained_multi_but_always_compare_registered_multi_if_none_survives(self):
        descriptors=[{'skeleton_id':sid,'subset':'regular','task_groups':[{}]*n} for sid,n in [('a',2),('b',1),('c',3)]]
        retained=[{'skeleton_id':sid,'state':'generated','quality_valid':True,'audit_passed':True}
                  for sid in ('b','c') for _ in range(2)]
        self.assertEqual(choose(descriptors,retained),['c','b'])
        self.assertEqual(choose(descriptors,[]),['a','b'])


if __name__=='__main__':unittest.main()
