"""Regression checks for the mandatory-metric R0 stop, using synthetic pairs."""
import unittest
from scripts.audit_m3_r3_r0 import gate_status, required_metric_availability
from scripts.tune_fast_dynamics_m3 import tiers


def pair(name, pattern, reference, candidate):
    return dict(mission_id=name, family_id=name, agents=2, flight_pattern=pattern,
        candidate_quality=True, candidate_status='completed',
        success_agreement=True, observation_success_agreement=True,
        motion_slots={c:dict(reference=reference,candidate=candidate,agree=None if reference=='unclear' else reference==candidate)
                      for c in ('truth','observation')},
        duration_relative_error=0., phase_duration_relative_error={'p01_observe':0.},
        lateral_m=dict(p95=0.,matched_fraction=1.), truth_minimum_separation_difference_m=0.,
        cruise_speed_m_s=[2.,2.], turn_minimum_speed_m_s=[1.,1.],
        condition_pairs={'truth':{},'observation':{}})


class R0MandatoryMetricTests(unittest.TestCase):
    def test_historical_hard_pass_does_not_prove_unknown_pattern_passed(self):
        rows=[pair('known','line_abreast','straight','straight'),
              pair('unknown','equal_strip_rectangular_spiral','unclear','unclear')]
        self.assertTrue(tiers(rows,2)['hard']['passed'])
        by_pattern, missing=required_metric_availability(rows)
        self.assertEqual(len(missing),2)
        self.assertTrue(all(v['reference_known']==0 and v['rate'] is None for v in missing))
        self.assertEqual(gate_status({'identity':True,'required_metric_availability':None},missing),'BLOCKED')
        self.assertEqual(by_pattern['equal_strip_rectangular_spiral']['tasks'],1)

    def test_candidate_unknown_is_a_failure_not_a_reduced_denominator(self):
        rows=[pair('one','line_abreast','straight','unclear')]
        by_pattern,missing=required_metric_availability(rows)
        self.assertEqual(missing,[])
        rate=by_pattern['line_abreast']['motion_reference_known']['truth']
        self.assertEqual((rate['total'],rate['agree'],rate['all_task_rate']),(1,0,0.))
        self.assertFalse(tiers(rows,1)['hard']['passed'])

    def test_complete_known_metrics_are_available(self):
        rows=[pair('one','line_abreast','straight','straight')]
        _,missing=required_metric_availability(rows)
        self.assertEqual(missing,[])
        self.assertEqual(gate_status({'complete':True},missing),'PASS')

    def test_false_gate_or_incomplete_registration_cannot_advance(self):
        self.assertEqual(gate_status({'contract':False},[]),'FAIL')
        self.assertEqual(gate_status({'registration':None},[]),'BLOCKED')

if __name__ == '__main__':
    unittest.main()
