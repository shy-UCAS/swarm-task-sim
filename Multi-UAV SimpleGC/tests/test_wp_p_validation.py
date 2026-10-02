"""P04-P07: channel-local perimeter visits, interval ends and progress facts."""

import math
import unittest

from swarm_sim.patrol_validation import (VERSION, behavior_labels,
                                         evaluate_channel, segment_visits)
from swarm_sim.mission_evaluation_v3 import evaluate_mission_v3


def _point(x, y):
    return dict(east_m=float(x), north_m=float(y), up_m=8.)


def _route(start, laps=2):
    corners = [(0, 0), (20, 0), (20, 20), (0, 20)]
    index = corners.index(start)
    return [_point(*corners[(index+step) % 4])
            for _ in range(laps) for step in range(1, 5)]


def _trace(start, laps=2, end=None):
    rows = [(0., [float(start[0]), float(start[1]), 8.])]
    previous, stamp = start, 0.
    for target in _route(start, laps):
        xy = (target["east_m"], target["north_m"])
        for step in range(1, 41):
            fraction = step/40
            rows.append((stamp + step*.25,
                         [previous[0]+fraction*(xy[0]-previous[0]),
                          previous[1]+fraction*(xy[1]-previous[1]), 8.]))
        previous, stamp = xy, stamp+10.
    if end is not None:
        while stamp + .25 <= end + 1e-8:
            stamp += .25
            rows.append((stamp, [float(previous[0]), float(previous[1]), 8.]))
    return rows


def _case(*, actual_laps=(2, 2), end=80., missing_gap=False):
    starts = {"uav_01": (0, 0), "uav_02": (20, 20)}
    phase = "p01_patrol"
    routes = {agent: _route(xy) for agent, xy in starts.items()}
    arrivals = {agent: [10.*(index+1) for index in range(8)] for agent in starts}
    scene = dict(max_gap_s=1., vehicles=[dict(id=agent) for agent in starts],
        phases=[dict(name=phase, semantic_phase="patrol", routes=routes, speed_m_s=2.)],
        task_spec=dict(mission=dict(target_region_id="target", intent_params=dict(
            objective="perimeter_patrol", laps=2, standoff_m=0., segment_length_m=5.,
            visit_radius_m=3., max_revisit_gap_factor=2.)),
            scenario=dict(regions=[dict(id="target", min_east_m=0., min_north_m=0.,
                                        width_m=20., height_m=20.)]),
            execution=dict(speed_m_s=2.)),
        semantic_plan=dict(execution_phases={phase: dict(agents={agent: dict(start_point=_point(*xy))
                                                          for agent, xy in starts.items()})}),
        planning=dict(nominal_phase_timing={phase: dict(per_agent_waypoint_arrival_s=arrivals)}))
    traces = {agent: _trace(starts[agent], laps, end) for agent, laps in zip(starts, actual_laps)}
    if missing_gap:
        traces["uav_01"] = [(t, p) for t, p in traces["uav_01"] if not 20. <= t <= 30.]
    windows = [dict(agent_id=agent, phase=phase, semantic_phase="patrol",
                    service_enabled=True, start_s=0., end_s=end, complete_execution_window=True)
               for agent in starts]
    return scene, traces, windows


class PatrolValidationTests(unittest.TestCase):
    def test_P04_complete_two_lap_patrol_counts_and_both_gaps(self):
        scene, traces, windows = _case()
        report = evaluate_channel(scene, traces, windows, {})
        self.assertEqual(report["conditions"], dict(visits=True, max_gap=True))
        metric = report["metrics"]["perimeter_revisit"]
        self.assertEqual(metric["version"], VERSION)
        self.assertEqual(metric["min_segment_visits"], 4)
        self.assertEqual(metric["loop_segment_coverage"], 1.)
        self.assertEqual(metric["per_agent_laps_observed"], {"uav_01": 2, "uav_02": 2})
        self.assertIsNotNone(metric["first_complete_lap_time_s"])
        self.assertTrue(all(s["max_gap_s"] <= metric["allowed_gap_s"] for s in metric["segments"]))
        for agent in ("uav_01", "uav_02"):
            entry_segments = [segment for segment in metric["segments"]
                              if agent in segment["initially_occupied_by"]]
            self.assertTrue(entry_segments)
            self.assertTrue(all(sum(visit["agent_id"] == agent for visit in segment["visits"]) == 2
                                for segment in entry_segments))

    def test_P04_missing_one_lap_is_failed_count_not_fabricated_laps(self):
        scene, traces, windows = _case(actual_laps=(1, 2))
        report = evaluate_channel(scene, traces, windows, {})
        self.assertIs(report["conditions"]["visits"], False)
        self.assertIsNone(report["metrics"]["per_agent_laps_observed"]["uav_01"])
        self.assertEqual(report["metrics"]["per_agent_laps_observed"]["uav_02"], 2)
        self.assertIsNotNone(report["metrics"]["perimeter_revisit"]["per_agent_progress"]
                             ["uav_01"]["first_complete_lap_time_s"])

    def test_P04_terminal_gap_is_checked_against_fixed_service_end(self):
        scene, traces, windows = _case(end=160.)
        report = evaluate_channel(scene, traces, windows, {})
        self.assertIs(report["conditions"]["visits"], True)
        self.assertIs(report["conditions"]["max_gap"], False)
        self.assertTrue(any("terminal" in s["max_gap_types"] for s in
                            report["metrics"]["perimeter_revisit"]["segments"]))

    def test_P04_trajectory_gap_or_truncation_is_unknown(self):
        scene, traces, windows = _case(missing_gap=True)
        report = evaluate_channel(scene, traces, windows, {})
        self.assertEqual(report["conditions"], dict(visits=None, max_gap=None))
        scene, traces, windows = _case()
        windows[0]["complete_execution_window"] = False
        self.assertEqual(evaluate_channel(scene, traces, windows, {})["conditions"],
                         dict(visits=None, max_gap=None))

    def test_P05_P06_initial_occupancy_and_hysteresis(self):
        segment = dict(start_xy_m=[0., 0.], end_xy_m=[5., 0.])
        distances = [0., 3.5, 3.1, 4.1, 2.9, 3.8, 4.2, 2.7]
        points = [(float(index), [2.5, d, 8.]) for index, d in enumerate(distances)]
        visits, initial = segment_visits(points, segment, 3., "a")
        self.assertTrue(initial)
        self.assertEqual([v["start_s"] for v in visits], [4., 7.])
        self.assertEqual([v["end_s"] for v in visits], [4., 7.])
        long_band = [(0., [2.5, 5., 8.]), (1., [2.5, 2.9, 8.]),
                     (9., [2.5, 3.9, 8.]), (10., [2.5, 4.1, 8.])]
        visits, _ = segment_visits(long_band, segment, 3., "a")
        self.assertEqual(visits[0]["end_s"], 1.)

    def test_P07_group_counts_do_not_invent_each_agents_laps(self):
        scene, traces, windows = _case(actual_laps=(1, 3), end=120.)
        report = evaluate_channel(scene, traces, windows, {})
        self.assertIs(report["conditions"]["visits"], True)
        self.assertIsNone(report["metrics"]["per_agent_laps_observed"]["uav_01"])
        self.assertIsNone(report["metrics"]["per_agent_laps_observed"]["uav_02"])
        labels = behavior_labels(scene, dict(report["metrics"], mission_success=True))
        self.assertEqual(labels["planned_behaviors"], ["perimeter_loop"])
        self.assertNotIn("each_agent_completed", str(labels))

    def test_P04_return_failure_does_not_relabel_successful_patrol_loop(self):
        scene, traces, windows = _case()
        metrics = evaluate_channel(scene, traces, windows, {})["metrics"]
        labels = behavior_labels(scene, dict(metrics, mission_success=False))
        self.assertEqual(labels["observed_behaviors"][0]["status"], "verified")

    def test_P04_SIM_FCU_channels_are_independent_on_missing_observations(self):
        scene, truth, _ = _case()
        scene["schema_version"] = 2
        scene["task_spec"]["schema_version"] = 3
        scene["task_spec"]["mission"].update(intent="patrol", return_required=False)
        scene["task_spec"]["execution"].update(control_mode="semantic_phase_route_v1",
            takeoff_alt_m=8., arrival_tolerance_m=1., confirmation_dwell_s=0.,
            record_hz=4., max_gap_s=1.)
        phase = scene["phases"][0]
        phase["terminal_hold_s"] = 0.
        scene["semantic_plan"]["execution_phases"][phase["name"]]["semantic_phase"] = "patrol"
        events = [dict(event="phase_release_scheduled", phase=phase["name"], release_t=0., t=0.)]
        for agent in truth:
            role = scene["semantic_plan"]["execution_phases"][phase["name"]]["agents"][agent]
            role.update(role="patrol", service_enabled=True, partition_id=agent,
                        waypoint_planner_indices=list(range(8)), terminal_point=phase["routes"][agent][-1])
            events.append(dict(event="phase_auto_confirmed", phase=phase["name"], agent_id=agent, t=0.))
            events.extend(dict(event="waypoint_reached", phase=phase["name"], agent_id=agent,
                               seq=index+2, t=10.*(index+1)) for index in range(8))
        observed = {agent: [(t, xyz+[2., 0., 0.]) for t, xyz in rows]
                    for agent, rows in truth.items()}
        observed["uav_01"] = [(t, xyz) for t, xyz in observed["uav_01"]
                              if not 20. <= t <= 30.]
        metadata = dict(run_epoch_monotonic_s=0., mission_end_monotonic_s=80.,
                        elapsed_s=80., status="completed")
        result = evaluate_mission_v3(scene, observed, truth, events, metadata, 0.)
        labels = result["labels"]
        self.assertIs(labels["mission_metrics"]["truth"]["mission_success"], True)
        self.assertIsNone(labels["mission_metrics"]["observation"]["mission_success"])
        self.assertEqual(labels["semantic_consistency"], "unknown")
        self.assertIs(labels["mission_metrics"]["truth"]["perimeter_revisit"]["visits_pass"], True)
        self.assertIsNone(labels["mission_metrics"]["observation"]["perimeter_revisit"]["visits_pass"])


if __name__ == "__main__":
    unittest.main()
