import unittest
from task_v07.expansion.contracts import RouteBundle
from task_v07.expansion.episode_pipeline import episode_interval_check
from task_v07.expansion.geometry_checks import planning_layer_interval_check


class RevisionIntervalTests(unittest.TestCase):
    def test_ten_metre_threshold_applies_to_both_plans_and_old_default_stays_six(self):
        bundle=RouteBundle({'a':[[0,0,50],[100,0,50]],'b':[[0,8,50],[100,8,50]]},{'a':0.,'b':0.})
        plans={m:{'departure_delays_s':{'a':0.,'b':0.}} for m in ('synchronous','sequential')}
        old=planning_layer_interval_check(bundle,plans,5.)
        new=episode_interval_check({'initial_settle_s':20.,'cruise_speed_m_s':5.,'planning_interval_warning_m':10.},bundle,plans)
        self.assertEqual(old['warning_threshold_m'],6.)
        self.assertEqual(new['warning_threshold_m'],10.)
        for mode in plans:
            self.assertFalse(old[mode]['below_warning'])
            self.assertTrue(new[mode]['below_warning'])
            self.assertEqual(new[mode]['minimum_m'],8.)


if __name__=='__main__':unittest.main()
