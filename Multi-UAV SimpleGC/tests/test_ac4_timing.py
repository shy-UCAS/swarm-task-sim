"""Hand-computable AC4 v2 geometry, simultaneous intervals and fail-closed cases."""

import copy
import unittest

from swarm_sim.ac4_timing import (AC4_TIMING_VERSION, closest_waypoint_nodes,
                                  evaluate_ac4_timing, evaluate_phase_timing,
                                  minimum_fleet_span)


def mapping(pairs, hover=None, complete=True):
    return dict(nodes=[dict(actual_s=a, nominal_s=b) for a, b in pairs],
                terminal_hover_start_s=hover, evidence_complete=complete)


def point(x, y=0.):
    return dict(east_m=x, north_m=y, up_m=2.)


def fixture():
    routes = {agent: [point(5, y), point(10, y)] for agent, y in (("a", 0.), ("b", 10.))}
    scene = dict(vehicles=[dict(id="a"), dict(id="b")], phases=[dict(name="observe", routes=routes)],
                 max_gap_s=1., planning=dict(nominal_phase_timing=dict(observe=dict(
                     duration_s=12., tau_s=1., per_agent_waypoint_arrival_s={"a": [5., 10.], "b": [5., 10.]}))))
    traces = {agent: [(float(t), [min(t / 2., 10.), y, 2.]) for t in range(23)]
              for agent, y in (("a", 0.), ("b", 10.))}
    events = [dict(event="phase_release_scheduled", phase="observe", release_t=0., t=0.)]
    for agent in ("a", "b"):
        events.extend(dict(event="waypoint_reached", phase="observe", agent_id=agent, seq=seq, t=stamp)
                      for seq, stamp in ((2, 10.), (3, 20.)))
    metadata = dict(run_epoch_monotonic_s=100., mission_end_monotonic_s=122., elapsed_s=25.)
    return scene, traces, events, metadata


class FleetSpanTests(unittest.TestCase):
    def test_simultaneous_minimizer_for_three_intervals(self):
        result = minimum_fleet_span({"a": [0., 10.], "b": [9., 20.], "c": [19., 30.]})
        self.assertEqual(result["span_s"], 9.)
        chosen = result["selected_nominal_s"]
        self.assertEqual(max(chosen.values()) - min(chosen.values()), 9.)
        for agent, value in chosen.items():
            low, high = result["nominal_intervals_s"][agent]
            self.assertLessEqual(low, value)
            self.assertLessEqual(value, high)

    def test_overlapping_intervals_have_one_common_fleet_choice(self):
        result = minimum_fleet_span({"a": [0., 10.], "b": [9., 20.], "c": [8., 9.5]})
        self.assertEqual(result["span_s"], 0.)
        self.assertEqual(set(result["selected_nominal_s"].values()), {9.})

    def test_empty_reversed_nonfinite_intervals_rejected(self):
        for invalid in ({}, {"a": [2., 1.]}, {"a": [0., float("nan")]}, {"a": [False, 1.]}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                minimum_fleet_span(invalid)


class PhaseTimingTests(unittest.TestCase):
    def evaluate(self, mappings, tau=2., end=10., nominal_end=12.):
        return evaluate_phase_timing(mappings, start_s=0., end_s=end, tau_s=tau, nominal_end_s=nominal_end)

    def test_common_slowdown_does_not_count_as_relative_desynchronization(self):
        result = self.evaluate({agent: mapping([(0., 0.), (10., 5.)]) for agent in ("a", "b", "c")})
        self.assertTrue(result["complete"])
        self.assertTrue(result["within_tau"])
        self.assertEqual(result["D_s"], 0.)
        self.assertEqual(result["version"], AC4_TIMING_VERSION)

    def test_max_at_internal_waypoint_knot_and_inclusive_tau(self):
        mappings = {"a": mapping([(0., 0.), (3., 6.), (10., 10.)]),
                    "b": mapping([(0., 0.), (10., 10.)])}
        result = self.evaluate(mappings, tau=3.)
        self.assertEqual(result["D_s"], 3.)
        self.assertEqual(result["worst"]["actual_s"], 3.)
        self.assertTrue(result["within_tau"])
        self.assertFalse(self.evaluate(mappings, tau=2.999)["within_tau"])

    def test_hover_transition_left_limit_is_not_lost(self):
        result = self.evaluate({"a": mapping([(0., 0.), (2., 5.)], hover=5.),
                                "b": mapping([(0., 0.), (5., 10.)])}, tau=4.)
        self.assertEqual(result["D_s"], 5.)
        self.assertEqual(result["worst"]["actual_s"], 5.)
        self.assertEqual(result["worst"]["side"], "left_limit")
        self.assertFalse(result["within_tau"])

    def test_unproved_hover_stays_singleton_and_is_conservative(self):
        a = mapping([(0., 0.), (2., 5.)])
        b = mapping([(0., 0.), (5., 10.)])
        conservative = self.evaluate({"a": a, "b": b})
        relaxed = self.evaluate({"a": mapping([(0., 0.), (2., 5.)], hover=2.), "b": b})
        self.assertEqual(conservative["D_s"], 5.)
        self.assertLessEqual(relaxed["D_s"], conservative["D_s"])
        self.assertEqual(conservative["conservative_terminal_singletons"], ["a", "b"])

    def test_no_op_is_release_only_with_proved_full_phase_hover(self):
        result = self.evaluate({"a": mapping([(0., 0.)], hover=0.),
                                "b": mapping([(0., 0.), (10., 10.)])}, tau=0.)
        self.assertEqual(result["D_s"], 0.)
        self.assertTrue(result["within_tau"])

    def test_nonmonotonic_and_missing_release_nodes_are_not_sorted_or_repaired(self):
        invalid = ([(0., 0.), (5., 8.), (4., 10.)], [(0., 0.), (5., 8.), (5., 10.)],
                   [(0., 0.), (5., 8.), (6., 7.)], [(1., 0.), (5., 8.)])
        for pairs in invalid:
            with self.subTest(pairs=pairs):
                result = self.evaluate({"a": mapping(pairs)})
                self.assertFalse(result["complete"])
                self.assertIsNone(result["within_tau"])
                self.assertIsNone(result["D_s"])

    def test_missing_coverage_nonfinite_and_invalid_hover_fail_closed(self):
        cases = [mapping([(0., 0.), (5., 5.)], complete=False),
                 mapping([(0., 0.), (float("nan"), 5.)]),
                 mapping([(0., 0.), (5., 5.)], hover=4.),
                 mapping([(0., 0.), (5., 5.)], hover=11.)]
        for item in cases:
            with self.subTest(item=item):
                self.assertFalse(self.evaluate({"a": item})["complete"])
        self.assertFalse(self.evaluate({})["complete"])


class ClosestNodeTests(unittest.TestCase):
    def closest(self, rows, targets=None, times=None, end=4., gap=2.):
        return closest_waypoint_nodes(rows, targets or [point(1)], times or [1.],
                                      start_s=0., end_s=end, max_gap_s=gap)

    def test_exact_3d_segment_projection_not_nearest_sample(self):
        nodes = self.closest([(0., [0., 0., 2.]), (2., [2., 0., 2.]), (4., [4., 0., 2.])])
        self.assertEqual(nodes[1]["actual_s"], 1.)
        self.assertEqual(nodes[1]["minimum_distance_m"], 0.)
        self.assertEqual(nodes[1]["search_domain_s"], [0., 4.])

    def test_3d_not_only_horizontal_distance_is_minimized(self):
        nodes = self.closest([(0., [0., 0., 0.]), (2., [2., 0., 2.]), (4., [4., 0., 2.])])
        self.assertEqual(nodes[1]["actual_s"], 1.5)
        self.assertAlmostEqual(nodes[1]["minimum_distance_m"], 2 ** -.5)

    def test_contiguous_closest_plateau_uses_earliest_instant(self):
        rows = [(0., [0., 0., 2.]), (1., [1., 0., 2.]), (2., [1., 0., 2.]), (4., [1., 0., 2.])]
        node = self.closest(rows)[1]
        self.assertEqual(node["actual_s"], 1.)
        self.assertEqual(node["closest_time_interval_s"], [1., 4.])

    def test_distinct_repeated_visits_are_ambiguous(self):
        rows = [(float(t), [float(x), 0., 2.]) for t, x in enumerate([0, 1, 0, 1, 2])]
        with self.assertRaisesRegex(ValueError, "ambiguous_distinct_closest_visits"):
            self.closest(rows)

    def test_route_order_and_release_collision_fail_closed(self):
        rows = [(0., [0., 0., 2.]), (2., [2., 0., 2.]), (4., [4., 0., 2.])]
        for targets, times in (([point(2), point(1)], [1., 2.]), ([point(0)], [1.])):
            with self.assertRaisesRegex(ValueError, "nonmonotonic_closest_nodes"):
                self.closest(rows, targets, times)

    def test_missing_boundary_gap_invalid_row_and_timeline_fail_closed(self):
        cases = [[(.1, [0., 0., 2.]), (4., [4., 0., 2.])],
                 [(0., [0., 0., 2.]), (3.9, [4., 0., 2.])],
                 [(0., [0., 0., 2.]), (4., [4., 0., 2.])],
                 [(0., [0., 0., 2.]), (2., None), (4., [4., 0., 2.])],
                 [(0., [0., 0., 2.]), (2., [2., 0., 2.]), (2., [2., 0., 2.]), (4., [4., 0., 2.])]]
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.closest(rows)


class HighLevelTimingTests(unittest.TestCase):
    def test_v1_common_absolute_delay_fails_but_v2_passes(self):
        scene, traces, events, metadata = fixture()
        result = evaluate_ac4_timing(scene, traces, events, metadata, 100.)
        self.assertTrue(result["complete"])
        self.assertTrue(result["within_tau"])
        self.assertTrue(result["crosscheck_within_tau"])
        self.assertFalse(result["v1_diagnostic"]["within_tau"])
        self.assertFalse(result["v1_is_gate"])
        self.assertEqual(result["per_phase"]["observe"]["primary"]["D_s"], 0.)

    def test_primary_closest_mapping_is_independent_of_event_times(self):
        scene, traces, events, metadata = fixture()
        original = evaluate_ac4_timing(scene, traces, events, metadata, 100.)
        events[1]["t"] = 12.
        changed = evaluate_ac4_timing(scene, traces, events, metadata, 100.)
        self.assertEqual(original["per_phase"]["observe"]["primary"], changed["per_phase"]["observe"]["primary"])
        self.assertNotEqual(original["per_phase"]["observe"]["crosscheck"], changed["per_phase"]["observe"]["crosscheck"])

    def test_missing_duplicate_or_out_of_order_raw_event_is_unknown(self):
        scene, traces, events, metadata = fixture()
        missing, duplicate, backwards = events[:-1], events + [copy.deepcopy(events[1])], copy.deepcopy(events)
        backwards[1]["t"] = 21.
        for bad in (missing, duplicate, backwards):
            with self.subTest(events=bad):
                result = evaluate_ac4_timing(scene, traces, bad, metadata, 100.)
                self.assertFalse(result["complete"])
                self.assertIsNone(result["within_tau"])

    def test_nominal_agent_mismatch_and_unbracketed_final_grid_are_unknown(self):
        scene, traces, events, metadata = fixture()
        short = {agent: rows[:-1] for agent, rows in traces.items()}
        self.assertIsNone(evaluate_ac4_timing(scene, short, events, metadata, 100.)["within_tau"])
        scene["planning"]["nominal_phase_timing"]["observe"]["per_agent_waypoint_arrival_s"].pop("b")
        self.assertIsNone(evaluate_ac4_timing(scene, traces, events, metadata, 100.)["within_tau"])

    def test_does_not_mutate_input_or_arrival_definitions(self):
        inputs = fixture()
        original = copy.deepcopy(inputs)
        evaluate_ac4_timing(*inputs, 100., terminal_hover_starts={"observe": {"a": 20., "b": 20.}})
        self.assertEqual(inputs, original)

    def test_no_op_requires_start_ready_and_full_trace_before_interval_relaxation(self):
        scene, traces, events, metadata = fixture()
        scene["phases"][0]["routes"]["a"] = []
        scene["planning"]["nominal_phase_timing"]["observe"]["per_agent_waypoint_arrival_s"]["a"] = []
        traces["a"] = [(t, [0., 0., 2.]) for t, _ in traces["a"]]
        events = [event for event in events if event.get("agent_id") != "a"]
        kwargs = dict(terminal_hover_starts={"observe": {"a": 0.}})
        self.assertIsNone(evaluate_ac4_timing(scene, traces, events, metadata, 100., **kwargs)["within_tau"])
        events.extend([dict(event="phase_no_op_started", phase="observe", agent_id="a", t=.1),
                       dict(event="phase_no_op_ready", phase="observe", agent_id="a", t=.2)])
        result = evaluate_ac4_timing(scene, traces, events, metadata, 100., **kwargs)
        self.assertTrue(result["within_tau"])
        self.assertEqual(result["per_phase"]["observe"]["primary"]["D_s"], 0.)
        traces["a"][4] = (4., None)
        self.assertIsNone(evaluate_ac4_timing(scene, traces, events, metadata, 100., **kwargs)["within_tau"])

    def test_invalid_supplied_hover_time_is_not_clamped_into_acceptance(self):
        for hover in (-1., 23., float("nan"), "20"):
            scene, traces, events, metadata = fixture()
            with self.subTest(hover=hover):
                result = evaluate_ac4_timing(scene, traces, events, metadata, 100.,
                                             terminal_hover_starts={"observe": {"a": hover}})
                self.assertFalse(result["complete"])
                self.assertIsNone(result["within_tau"])


if __name__ == "__main__":
    unittest.main()
