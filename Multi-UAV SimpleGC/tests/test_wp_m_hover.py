"""M: the production hover proof preserves the frozen AC4 v2 evidence rule."""

import copy
import unittest

from scripts.verify_ac4_v2 import terminal_hover_evidence as offline_v2_hover
from swarm_sim.ac4_timing import terminal_hover_evidence_v3


def fixture(*, no_op=False, channel="observation"):
    target = dict(east_m=3., north_m=0., up_m=2.)
    scene = dict(phases=[dict(name="observe", routes={"a": [] if no_op else [target]})],
        record_hz=10., max_gap_s=.5,
        task_spec=dict(execution=dict(arrival_tolerance_m=1.)),
        semantic_plan=dict(execution_phases=dict(observe=dict(agents=dict(a=dict(start_point=target))))))
    traces = {"a": []}
    for tick in range(-1, 22):
        t = tick / 10.
        stopped = no_op or t >= .7
        xyz = [3. if stopped else 1., 0., 2.]
        values = xyz + [.1 if stopped else 1., 0., 0.] if channel == "observation" else xyz
        traces["a"].append((t, values))
    events = [dict(event="phase_release_scheduled", phase="observe", release_t=0.)]
    metadata = dict(run_epoch_monotonic_s=100., mission_end_monotonic_s=102.05)
    return scene, traces, events, metadata


class ProductionHoverEvidenceTests(unittest.TestCase):
    def check_same(self, inputs, channel):
        original = copy.deepcopy(inputs)
        args = (*inputs, 100., channel, {})
        current = terminal_hover_evidence_v3(*args)
        self.assertEqual(current, offline_v2_hover(*args))
        self.assertEqual(inputs, original)
        return current

    def test_route_suffix_matches_v2_for_both_channels(self):
        for channel in ("observation", "truth"):
            with self.subTest(channel=channel):
                starts, evidence = self.check_same(fixture(channel=channel), channel)
                self.assertEqual(starts["observe"]["a"], .8 if channel == "truth" else .7)
                self.assertTrue(evidence[0]["established"])
                self.assertEqual(evidence[0]["version"], "terminal_hover_measured_suffix_v1")

    def test_no_op_full_phase_and_missing_boundary_support(self):
        inputs = fixture(no_op=True)
        starts, evidence = self.check_same(inputs, "observation")
        self.assertEqual(starts["observe"]["a"], 0.)
        self.assertTrue(evidence[0]["established"])
        inputs[1]["a"] = [row for row in inputs[1]["a"] if row[0] >= .1]
        starts, evidence = self.check_same(inputs, "observation")
        self.assertEqual(starts["observe"], {})
        self.assertFalse(evidence[0]["established"])

    def test_terminal_gap_and_motion_keep_conservative_singleton(self):
        for variant in ("missing_post_end", "moving_post_end", "moving_inside_no_op"):
            with self.subTest(variant=variant):
                inputs = fixture(no_op=variant == "moving_inside_no_op")
                if variant == "missing_post_end":
                    inputs[1]["a"].pop()
                elif variant == "moving_post_end":
                    inputs[1]["a"][-1] = (2.1, [3., 0., 2., 1., 0., 0.])
                else:
                    inputs[1]["a"][10] = (.9, [3., 0., 2., .6, 0., 0.])
                starts, evidence = self.check_same(inputs, "observation")
                self.assertEqual(starts["observe"], {})
                self.assertFalse(evidence[0]["established"])
                self.assertIsNone(evidence[0]["start_s"])


if __name__ == "__main__":
    unittest.main()
