import unittest

from scripts.build_v05_batch_report import patrol_timing, primary_distribution


class BatchTimingReportTests(unittest.TestCase):
    def test_unknowns_excluded_from_known_denominator_and_equality_passes(self):
        values = [dict(D_s=5., tau_s=5., complete=True), dict(D_s=7., tau_s=5., complete=True),
                  dict(D_s=100., tau_s=5., complete=False), dict(D_s=None, tau_s=5., complete=True),
                  dict(D_s=1., tau_s=None, complete=True), dict(D_s=float("nan"), tau_s=5., complete=True)]
        actual = primary_distribution(values)
        self.assertEqual((actual["expected"], actual["known"], actual["unknown"]), (6, 2, 4))
        self.assertEqual((actual["median_s"], actual["max_s"]), (6., 7.))
        self.assertEqual(actual["exceeded"], dict(numerator=1, denominator=2, fraction=.5))

    def test_all_unknown_does_not_report_zero_or_pass(self):
        actual = primary_distribution([dict(D_s=None, tau_s=5., complete=False)])
        self.assertIsNone(actual["median_s"])
        self.assertIsNone(actual["max_s"])
        self.assertIsNone(actual["exceeded"]["fraction"])
        self.assertEqual(actual["exceeded"]["denominator"], 0)

    def test_only_patrol_primary_one_per_group_and_channel_separate(self):
        def row(stage, name, truth, observation):
            return dict(stage=stage, intent="patrol", run_id=name, case_id=name,
                semantic_plan=dict(execution_phases={"p00": dict(semantic_phase="approach"), "p01": dict(semantic_phase="patrol")}),
                ac4=dict(channels={channel: dict(per_phase={
                    "p00": dict(primary=dict(D_s=999, tau_s=5, complete=True)),
                    "p01": dict(primary=dict(D_s=value, tau_s=5, complete=True),
                                crosscheck=dict(D_s=999, tau_s=5, complete=True))})
                    for channel, value in (("truth", truth), ("observation", observation))}))
        report = patrol_timing([row("pilot", "PP02", 1., 4.), row("batch", "B02", 7., 5.),
                                dict(stage="batch", intent="reconnaissance")])
        groups = {(g["scope"], g["channel"]): g for g in report["groups"]}
        self.assertEqual(len(report["records"]), 4)
        self.assertEqual(groups["batch", "truth"]["median_s"], 7.)
        self.assertEqual(groups["batch", "observation"]["exceeded"]["numerator"], 0)
        self.assertEqual(groups["pilot_and_batch", "truth"]["median_s"], 4.)
        self.assertEqual(groups["pilot_and_batch", "truth"]["known"], 2)

    def test_missing_stopped_analysis_counts_unknown_in_both_channels(self):
        report = patrol_timing([dict(stage="batch", intent="patrol", run_id="stopped", case_id="B02")])
        for group in report["groups"]:
            self.assertEqual((group["expected"], group["known"], group["unknown"]), (1, 0, 1))


if __name__ == "__main__":
    unittest.main()
