"""Terminal-interval proof must cover actual phase boundaries and no-op motion."""
import copy
import unittest

from scripts.verify_ac4_v2 import terminal_hover_evidence


def fixture(no_op=False, channel="observation"):
    target = dict(east_m=3., north_m=0., up_m=2.)
    scene = dict(phases=[dict(name="observe", routes={"a": [] if no_op else [target]})],
        record_hz=10., max_gap_s=.5,
        task_spec=dict(execution=dict(arrival_tolerance_m=1.)),
        semantic_plan=dict(execution_phases=dict(observe=dict(agents=dict(a=dict(start_point=target))))))
    traces = {"a": []}
    for tick in range(-1, 22):
        t = tick/10.
        stopped = no_op or t >= .7
        xyz = [3. if stopped else 1., 0., 2.]
        values = xyz+[.1 if stopped else 1., 0., 0.] if channel == "observation" else xyz
        traces["a"].append((t, values))
    events = [dict(event="phase_release_scheduled", phase="observe", release_t=0.)]
    metadata = dict(run_epoch_monotonic_s=100., mission_end_monotonic_s=102.05)
    return scene, traces, events, metadata


class HoverEvidenceTests(unittest.TestCase):
    def evaluate(self, inputs, channel="observation"):
        return terminal_hover_evidence(*inputs, 100., channel, {})

    def test_supported_terminal_hover_uses_measured_suffix_without_mutation(self):
        inputs = fixture()
        original = copy.deepcopy(inputs)
        starts, evidence = self.evaluate(inputs)
        self.assertEqual(starts["observe"]["a"], .7)
        self.assertTrue(evidence[0]["terminal_suffix_supported_through_end"])
        self.assertTrue(evidence[0]["established"])
        self.assertEqual(inputs, original)

    def test_last_low_speed_sample_before_end_does_not_prove_end_hover(self):
        inputs = fixture()
        inputs[1]["a"].pop()  # Last record is 2.0, phase ends at 2.05.
        starts, evidence = self.evaluate(inputs)
        self.assertEqual(starts["observe"], {})
        self.assertFalse(evidence[0]["terminal_suffix_supported_through_end"])
        self.assertFalse(evidence[0]["established"])

    def test_post_end_support_must_remain_slow_and_close(self):
        for values in ([3.,0.,2.,1.,0.,0.], [5.,0.,2.,0.,0.,0.], None):
            with self.subTest(values=values):
                inputs = fixture()
                inputs[1]["a"][-1] = (2.1, values)
                starts, evidence = self.evaluate(inputs)
                self.assertEqual(starts["observe"], {})
                self.assertFalse(evidence[0]["terminal_suffix_supported_through_end"])

    def test_whole_phase_no_op_gets_release_interval_for_both_channels(self):
        for channel in ("truth", "observation"):
            with self.subTest(channel=channel):
                starts, evidence = self.evaluate(fixture(no_op=True, channel=channel), channel)
                self.assertEqual(starts["observe"]["a"], 0.)
                self.assertTrue(evidence[0]["established"])

    def test_no_op_motion_inside_phase_cannot_be_hidden_by_terminal_suffix(self):
        inputs = fixture(no_op=True)
        inputs[1]["a"][10] = (.9, [3.,0.,2.,.6,0.,0.])
        starts, evidence = self.evaluate(inputs)
        self.assertEqual(starts["observe"], {})
        self.assertFalse(evidence[0]["established"])
        self.assertGreater(evidence[0]["measured_duration_s"], .2)

    def test_no_op_missing_release_support_does_not_grant_full_phase_interval(self):
        inputs = fixture(no_op=True)
        inputs[1]["a"] = [r for r in inputs[1]["a"] if r[0] >= .1]
        starts, evidence = self.evaluate(inputs)
        self.assertEqual(starts["observe"], {})
        self.assertFalse(evidence[0]["established"])


if __name__ == "__main__":
    unittest.main()
