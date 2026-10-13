"""Independent examples for the user-approved three-tier calibration gates."""
import copy
import unittest

from scripts.tune_fast_dynamics_m3 import configured, config_values, rank, select_subset, tiers, classify_evaluation
from swarm_sim.fast_dynamics.contracts import M2Config


def pair(name="m", family="f", pattern="parallel_strips", flight="equal_strip_lawnmower"):
    return dict(mission_id=name, family_id=family, agents=2, flight_pattern=flight,
        candidate_status="completed", candidate_quality=True, success_agreement=True,
        observation_success_agreement=True,
        motion_slots={c: dict(reference=pattern, candidate=pattern, agree=True)
                      for c in ("truth", "observation")},
        duration_relative_error=.02, phase_duration_relative_error={"p": .02},
        lateral_m=dict(p95=.2, matched_fraction=.95), truth_minimum_separation_difference_m=.1,
        cruise_speed_m_s=[2.5, 2.5], turn_minimum_speed_m_s=[1.2, .4],
        condition_pairs={c: dict(coverage=dict(agree=True)) for c in ("truth", "observation")})


class SearchGateTests(unittest.TestCase):
    def test_rejected_candidate_does_not_stop_but_contract_error_does(self):
        bad=pair();bad["candidate_quality"]=False
        self.assertEqual(classify_evaluation([dict(status="COMPLETE",paired=bad)],1)["status"],"REJECTED")
        self.assertEqual(classify_evaluation([dict(status="COMPLETE",paired=pair())],1)["status"],"ELIGIBLE")
        self.assertEqual(classify_evaluation([dict(status="P0_STOP")],1)["status"],"P0_STOP")

    def test_condition_metrics_are_reported_without_an_extra_rejection_rule(self):
        row=pair();row["condition_pairs"]["truth"]["coverage"]["agree"]=False
        self.assertTrue(tiers([row],1)["hard"]["passed"])
        self.assertEqual(tiers([row],1)["aggregate"]["conditions"]["truth"]["coverage"]["disagree"],1)

    def test_new_ranking_uses_total_then_observe_then_turn(self):
        values=config_values(M2Config().to_dict())
        def score(total,observe,turn):
            row=pair();row.update(duration_relative_error=total,
                phase_duration_relative_error={"p01_observe":observe},turn_minimum_speed_m_s=[1.,1.+turn])
            return rank(dict(tiers=tiers([row],1)),values)
        self.assertLess(score(.03,.9,10.),score(.04,.01,.01))
        self.assertLess(score(.03,.05,10.),score(.03,.06,.01))
        self.assertLess(score(.03,.05,.2),score(.03,.05,.4))

    def test_quality_cannot_drop_a_timeout_from_the_denominator(self):
        rows=[pair("a"),pair("b")]
        rows[1].update(candidate_status="timeout", candidate_quality=False)
        self.assertFalse(tiers(rows, 2)["hard"]["passed"])
        self.assertFalse(tiers(rows[:1], 2)["hard"]["passed"])

    def test_judgment_boundary_is_99_point_5_percent(self):
        rows=[pair(str(i)) for i in range(200)]
        rows[0]["success_agreement"]=False
        self.assertTrue(tiers(rows, 200)["hard"]["passed"])
        rows[1]["success_agreement"]=None
        self.assertFalse(tiers(rows, 200)["hard"]["passed"])

    def test_motion_denominator_is_reference_known_and_candidate_unknown_fails(self):
        rows=[pair("known"),pair("reference_unknown",pattern="unclear",flight="spiral")]
        value=tiers(rows,2)
        self.assertTrue(value["hard"]["passed"])
        self.assertEqual(value["aggregate"]["motion_reference_known"]["truth"]["total"],1)
        rows[0]["motion_slots"]["truth"].update(candidate="unclear",agree=None)
        self.assertFalse(tiers(rows,2)["hard"]["passed"])
        self.assertFalse(tiers(rows[1:],1)["hard"]["passed"])

    def test_per_pattern_threshold_is_not_hidden_by_overall_accuracy(self):
        rows=[pair(str(i)) for i in range(100)]
        rows[-1]["flight_pattern"]="patrol"
        rows[-1]["motion_slots"]["truth"].update(candidate="unclear",agree=None)
        result=tiers(rows,100)
        self.assertEqual(result["aggregate"]["motion_reference_known"]["truth"]["all_task_rate"],.99)
        self.assertFalse(result["hard"]["passed"])

    def test_time_targets_and_diagnostics_do_not_become_hard_gates(self):
        row=pair();row["duration_relative_error"]=2.
        row["phase_duration_relative_error"]={"p":2.}
        row["turn_minimum_speed_m_s"]=[1.,10.]
        row["lateral_m"]["p95"]=100.
        result=tiers([row],1)
        self.assertTrue(result["hard"]["passed"])
        self.assertFalse(all(t["passed"] for t in result["targets"]))

    def test_subset_uses_identities_and_frozen_rank_not_measurements(self):
        families=[f"f{i}" for i in range(30)]
        rows=[pair(str(i),f) for i,f in enumerate(families)]
        for i in range(3):rows[i].update(agents=i+2,flight_pattern=f"pattern{i}")
        a=select_subset(rows,families)
        altered=copy.deepcopy(rows[::-1])
        for row in altered:row.update(duration_relative_error=999.,candidate_quality=False)
        self.assertEqual(a,select_subset(altered,families))
        self.assertEqual(a["families"],families[:24])

    def test_bounds_and_default_distance_break_exact_metric_ties(self):
        values=config_values(M2Config().to_dict());result=dict(tiers=tiers([pair()],1))
        self.assertLess(rank(result,values),rank(result,(4.5,*values[1:])))
        self.assertEqual(configured(values),M2Config().to_dict())
        with self.assertRaises(ValueError):configured((4.6,*values[1:]))


if __name__=="__main__":unittest.main()
