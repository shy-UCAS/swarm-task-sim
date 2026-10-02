"""M01-M03: visit-ordered progress, failure evidence and AC4 v3 behavior."""

import copy
import math
import unittest

from swarm_sim.ac4_timing import (AC4_TIMING_V3_VERSION, ORDERED_ROUTE_PROGRESS_VERSION,
                                  closest_waypoint_nodes, evaluate_ac4_timing,
                                  evaluate_ac4_timing_v3, ordered_route_progress)


def point(east, north=0):
    return dict(east_m=float(east), north_m=float(north), up_m=8.0)


def loop(start, direction, laps):
    corners = [(0, 0), (10, 0), (10, 8), (0, 8)]
    if start == (5, 0):
        one = ([(10, 0), (10, 8), (0, 8), (0, 0), start] if direction == "cw"
               else [(0, 0), (0, 8), (10, 8), (10, 0), start])
    else:
        index = corners.index(start)
        step = 1 if direction == "cw" else -1
        one = [corners[(index + step * k) % 4] for k in range(1, 5)]
    route = [point(*xy) for _ in range(laps) for xy in one]
    return route, [index for index, xy in enumerate([xy for _ in range(laps) for xy in one]) if xy == start]


def perfect_trace(start, route, step=.5):
    rows = [(0., [float(start[0]), float(start[1]), 8.])]
    previous, stamp, arrivals = point(*start), 0., []
    for target in route:
        distance = math.dist([previous[k] for k in ("east_m", "north_m", "up_m")],
                             [target[k] for k in ("east_m", "north_m", "up_m")])
        count = int(round(distance / step))
        for index in range(1, count + 1):
            fraction = index / count
            rows.append((stamp + distance * fraction,
                         [previous[k] + fraction * (target[k] - previous[k])
                          for k in ("east_m", "north_m", "up_m")]))
        stamp += distance
        arrivals.append(stamp)
        previous = target
    rows.append((stamp + 1., rows[-1][1]))
    return rows, arrivals


class OrderedProgressTests(unittest.TestCase):
    def test_M01_two_three_laps_both_directions_and_entry_points(self):
        for start, direction, laps in (((0, 0), "cw", 2), ((10, 8), "ccw", 3),
                                       ((5, 0), "cw", 3), ((5, 0), "ccw", 2)):
            with self.subTest(start=start, direction=direction, laps=laps):
                route, lap_indices = loop(start, direction, laps)
                rows, nominal = perfect_trace(start, route)
                result = ordered_route_progress(rows, route, nominal, start_s=0.,
                    end_s=rows[-1][0], max_gap_s=1., start_point=point(*start),
                    lap_node_indices=lap_indices)
                self.assertEqual(result["version"], ORDERED_ROUTE_PROGRESS_VERSION)
                self.assertTrue(result["evidence_complete"], result["issues"])
                self.assertEqual(len(result["nodes"]), len(route) + 1)
                self.assertEqual(result["per_agent_laps_observed"], laps)
                self.assertEqual(result["laps_evidence_status"], "exact")
                self.assertEqual([node["route_index"] for node in result["nodes"][1:]], list(range(len(route))))
                self.assertTrue(all(a["actual_s"] < b["actual_s"] for a, b in zip(result["nodes"], result["nodes"][1:])))
                self.assertTrue(all(abs(a["actual_s"] - a["nominal_s"]) < 1e-8 for a in result["nodes"]))
                self.assertFalse(result["backtracking_evidence"]["detected"])

    def test_M02_missing_lap_is_unknown_not_fabricated(self):
        route, lap_indices = loop((0, 0), "cw", 2)
        flown, _ = perfect_trace((0, 0), route[:4])
        full_nominal = perfect_trace((0, 0), route)[1]
        flown[-1] = (full_nominal[-1] + 1., flown[-1][1])
        # Regular stationary samples preserve evidence coverage while the
        # second lap is physically absent.
        terminal = flown[-1]
        flown = flown[:-1] + [(t / 2., flown[-2][1]) for t in range(int(flown[-2][0] * 2) + 1,
                                                                     int(terminal[0] * 2) + 1)]
        result = ordered_route_progress(flown, route, full_nominal, start_s=0.,
            end_s=flown[-1][0], max_gap_s=1., start_point=point(0, 0), lap_node_indices=lap_indices)
        self.assertFalse(result["evidence_complete"])
        self.assertTrue(any("missing_route_node" in issue for issue in result["issues"]))
        self.assertIsNone(result["per_agent_laps_observed"])
        self.assertEqual(result["laps_lower_bound"], 1)

    def test_M02_backtracking_and_gap_are_unknown(self):
        route, lap_indices = loop((0, 0), "cw", 2)
        rows, nominal = perfect_trace((0, 0), route)
        # Insert a 5 m reversal after the first corner and shift later samples.
        first = [(t, p) for t, p in rows if t <= 10.]
        suffix = [(t + 10., p) for t, p in rows if t > 10.]
        backtrack = first + [(float(t), [float(20 - t), 0., 8.]) for t in range(11, 16)]
        backtrack += [(float(t), [float(t - 10), 0., 8.]) for t in range(16, 21)] + suffix
        backtrack.sort(key=lambda row: row[0])
        reversed_result = ordered_route_progress(backtrack, route, nominal, start_s=0.,
            end_s=backtrack[-1][0], max_gap_s=1., start_point=point(0, 0), lap_node_indices=lap_indices)
        self.assertIn("backtracking", reversed_result["issues"])
        self.assertIsNone(reversed_result["per_agent_laps_observed"])
        gapped = [row for row in rows if not 8. <= row[0] <= 12.]
        gap_result = ordered_route_progress(gapped, route, nominal, start_s=0.,
            end_s=gapped[-1][0], max_gap_s=1., start_point=point(0, 0), lap_node_indices=lap_indices)
        self.assertIn("trajectory_gap_in_common_domain", gap_result["issues"])
        self.assertIsNone(gap_result["per_agent_laps_observed"])

    def test_M03_unique_route_matches_v2_nodes_and_D(self):
        route = [point(5), point(10)]
        traces = {agent: [(float(t), [min(t / 2., 10.), offset, 8.]) for t in range(23)]
                  for agent, offset in (("a", 0.), ("b", 10.))}
        nominal = [5., 10.]
        old = closest_waypoint_nodes(traces["a"], route, nominal, start_s=0., end_s=22., max_gap_s=1.)
        new = ordered_route_progress(traces["a"], route, nominal, start_s=0., end_s=22., max_gap_s=1.,
                                     start_point=point(0))
        self.assertTrue(new["evidence_complete"])
        self.assertEqual([(n["actual_s"], n["nominal_s"]) for n in old],
                         [(n["actual_s"], n["nominal_s"]) for n in new["nodes"]])
        routes = {agent: [point(5, offset), point(10, offset)] for agent, offset in (("a", 0.), ("b", 10.))}
        scene = dict(vehicles=[dict(id="a"), dict(id="b")],
                     phases=[dict(name="observe", semantic_phase="observe", routes=routes)], max_gap_s=1.,
                     semantic_plan=dict(execution_phases=dict(observe=dict(agents={agent: dict(start_point=point(0, y))
                         for agent, y in (("a", 0.), ("b", 10.))}))),
                     planning=dict(nominal_phase_timing=dict(observe=dict(duration_s=12., tau_s=1.,
                         per_agent_waypoint_arrival_s={"a": nominal, "b": nominal}))))
        events = [dict(event="phase_release_scheduled", phase="observe", release_t=0., t=0.)]
        for agent in traces:
            events += [dict(event="waypoint_reached", phase="observe", agent_id=agent, seq=seq, t=stamp)
                       for seq, stamp in ((2, 10.), (3, 20.))]
        metadata = dict(run_epoch_monotonic_s=100., mission_end_monotonic_s=122.)
        old_result = evaluate_ac4_timing(scene, traces, events, metadata, 100.)
        new_result = evaluate_ac4_timing_v3(scene, traces, events, metadata, 100.)
        self.assertEqual(new_result["version"], AC4_TIMING_V3_VERSION)
        self.assertTrue(new_result["within_tau"])
        self.assertEqual(old_result["per_phase"]["observe"]["primary"]["D_s"],
                         new_result["per_phase"]["observe"]["primary"]["D_s"])
        self.assertEqual(old_result["per_phase"]["observe"]["within_tau"],
                         new_result["per_phase"]["observe"]["within_tau"])
        self.assertEqual(copy.deepcopy(old_result), evaluate_ac4_timing(scene, traces, events, metadata, 100.))

        # An FCU/SIM trajectory gap invalidates only the position mapping.
        # The raw seq event crosscheck remains independent and computable.
        gapped = copy.deepcopy(traces)
        gapped["a"] = [row for row in gapped["a"] if row[0] != 11.]
        degraded = evaluate_ac4_timing_v3(scene, gapped, events, metadata, 100.)
        phase = degraded["per_phase"]["observe"]
        self.assertIsNone(phase["primary"]["D_s"])
        self.assertTrue(phase["crosscheck"]["complete"])
        self.assertIsNotNone(phase["crosscheck"]["D_s"])
        self.assertIsNone(phase["within_tau"])


if __name__ == "__main__":
    unittest.main()
