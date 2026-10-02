"""E07: hand-computable continuous windows, independent channels and failures."""

import copy
import unittest

from swarm_sim.mission_evaluation_v3 import evaluate_mission_v3
from swarm_sim.route_windows import (SIM_HOST_SPEED_VERSION, SIM_SOURCE_SPEED_VERSION,
                                     build_route_windows, service_window_view)


def point(x):
    return dict(east_m=x, north_m=.5, up_m=1.)


def row(t, x, speed=0.):
    return (t, [x, .5, 1., speed, 0., 0.])


def fixture(two_phases=False, no_op=False):
    names = [("p0_observe", "observe"), ("p1_return", "return")] if two_phases else [("p0_observe", "observe")]
    phases, mapping = [], {}
    for name, semantic in names:
        route = [] if no_op else [point(1), point(2)] if semantic == "observe" else [point(0)]
        target = route[-1] if route else point(0)
        phases.append(dict(name=name, semantic_phase=semantic, routes={"a": route}, speed_m_s=1, terminal_hold_s=.5))
        mapping[name] = dict(semantic_phase=semantic, agents={"a": dict(
            role="hold_no_op" if no_op else semantic, service_enabled=semantic == "observe" and not no_op,
            partition_id="R", waypoint_planner_indices=list(range(1, len(route) + 1)),
            start_point=point(0), terminal_point=target)})
    spec = dict(schema_version=3, mission=dict(intent="reconnaissance", return_required=False, target_region_id="R",
        intent_params=dict(objective="area_coverage", coverage_required=.9,
            observation_model=dict(type="ideal_horizontal_disk", radius_m=.2, height_tolerance_m=.1, grid_m=1,
                                   activation="observe_phase_only"))),
        scenario=dict(regions=[dict(id="R", min_east_m=0, min_north_m=0, width_m=2, height_m=1)], platform={}),
        planner=dict(name="equal_strip_lawnmower_v1", params={}),
        execution=dict(control_mode="semantic_phase_route_v1", arrival_tolerance_m=.2, max_gap_s=1,
                       takeoff_alt_m=1, record_hz=10, confirmation_dwell_s=.5))
    scene = dict(schema_version=2, vehicles=[dict(id="a", east_m=0., north_m=.5)], task_spec=spec,
                 phases=phases, semantic_plan=dict(execution_phases=mapping))
    events = [dict(event="phase_release_scheduled", phase=names[0][0], release_t=.8, t=.6),
              dict(event="phase_auto_confirmed", agent_id="a", phase=names[0][0], t=1.),
              dict(event="waypoint_reached", agent_id="a", phase=names[0][0], seq=2, t=1.5),
              dict(event="waypoint_reached", agent_id="a", phase=names[0][0], seq=3, t=2.)]
    if two_phases:
        events += [dict(event="phase_release_scheduled", phase=names[1][0], release_t=4., t=3.7),
                   dict(event="phase_auto_confirmed", agent_id="a", phase=names[1][0], t=4.1),
                   dict(event="waypoint_reached", agent_id="a", phase=names[1][0], seq=2, t=5.)]
    metadata = dict(run_epoch_monotonic_s=100., mission_end_monotonic_s=106., elapsed_s=8., status="completed")
    return scene, events, metadata


class RouteWindowTests(unittest.TestCase):
    def test_E07_arrival_is_first_post_event_joint_condition(self):
        scene, events, metadata = fixture()
        traces = {"a": [row(1, 0), row(2, 1.6, .1), row(2.5, 1.9, .31), row(3, 1.9, .3), row(4, 2), row(5, 2), row(6, 2)]}
        window = build_route_windows(scene, traces, events, metadata, 100, "observation")[0]
        self.assertEqual((window["start_s"], window["arrival_s"], window["end_s"]), (1., 3., 6.))
        self.assertEqual(window["arrival_source"], "trajectory_stop")
        self.assertTrue(window["arrival_verified"])
        self.assertEqual(window["barrier_wait_host_s"], 3.)
        self.assertEqual(window["intermediate_waypoints"][0]["seq"], 2)
        self.assertEqual(window["intermediate_waypoints"][0]["planner_index"], 1)

    def test_E07_late_terminal_event_cannot_search_back_to_earlier_stop(self):
        scene, events, metadata = fixture()
        events[-1]["t"] = 4.
        traces = {"a": [row(1, 0), row(2, 2), row(3, 2), row(4, 2, .5), row(5, 2), row(6, 2)]}
        window = build_route_windows(scene, traces, events, metadata, 100, "observation")[0]
        self.assertEqual(window["arrival_s"], 5.)

    def test_E07_terminal_before_auto_confirmation_can_anchor_later_trajectory_arrival(self):
        scene, events, metadata = fixture()
        events[1]["t"] = 3.
        traces = {"a": [row(1, 0, 1), row(2, 1.6, .5), row(2.5, 1.9, .4),
                         row(3, 1.9, .2), row(4, 2), row(5, 2), row(6, 2)]}
        for channel in ("observation", "truth"):
            window = build_route_windows(scene, traces, events, metadata, 100, channel)[0]
            self.assertEqual(window["terminal_waypoint_reached_s"], 2.)
            self.assertEqual((window["start_s"], window["arrival_s"]), (3., 3.))
            self.assertTrue(window["arrival_verified"])
            self.assertTrue(window["chronology_valid"])
            self.assertTrue(window["complete_execution_window"])
            terminal = next(e for e in window["waypoint_events"] if e["terminal"])
            self.assertFalse(terminal["within_window"])
            self.assertTrue(terminal["within_phase_release_bounds"])

    def test_E07_arrival_before_auto_confirmation_keeps_earliest_definition_but_disables_inverted_service(self):
        scene, events, metadata = fixture()
        events[1]["t"] = 3.
        traces = {"a": [row(1, 1.8), row(1.5, 1.9), row(2, 2, .2), row(3, 2), row(4, 2), row(5, 2), row(6, 2)]}
        for channel in ("observation", "truth"):
            window = build_route_windows(scene, traces, events, metadata, 100, channel)[0]
            self.assertEqual((window["start_s"], window["arrival_s"]), (3., 2.))
            self.assertEqual(window["arrival_source"], "trajectory_stop")
            self.assertTrue(window["arrival_verified"])
            self.assertFalse(window["chronology_valid"])
            self.assertEqual(window["chronology_reason"], "trajectory_arrival_precedes_phase_start")
            self.assertFalse(window["complete_execution_window"])
            service = service_window_view([window])[0]
            self.assertIsNone(service["start_s"])
            self.assertIsNone(service["end_s"])
            self.assertEqual(service["arrival_s"], 2.)

    def test_E07_release_bounded_terminal_does_not_recover_an_invalid_timeline(self):
        scene, events, metadata = fixture()
        events[1]["t"] = 3.
        traces = {"a": [row(1, 1.8), row(2, 2), row(2, 2), row(3, 2), row(4, 2), row(5, 2), row(6, 2)]}
        for channel in ("observation", "truth"):
            window = build_route_windows(scene, traces, events, metadata, 100, channel)[0]
            self.assertEqual(window["arrival_source"], "event_fallback")
            self.assertFalse(window["arrival_verified"])
            self.assertFalse(window["complete_execution_window"])
            self.assertFalse(window["trajectory_evidence_complete"])

    def test_E07_channels_derive_different_arrivals_from_own_evidence(self):
        scene, events, metadata = fixture()
        observed = {"a": [row(1, 0), row(2, 1.9, .2), row(3, 2), row(4, 2), row(5, 2), row(6, 2)]}
        truth = {"a": [(t, [x, .5, 1.]) for t, x in [(1, 0), (2, 1.9), (3, 2), (4, 2), (5, 2), (6, 2)]]}
        observation = build_route_windows(scene, observed, events, metadata, 100, "observation")[0]
        actual = build_route_windows(scene, truth, events, metadata, 100, "truth")[0]
        self.assertEqual(observation["arrival_s"], 2.)
        self.assertEqual(actual["arrival_s"], 3.)
        self.assertEqual(actual["speed_processing_version"], SIM_HOST_SPEED_VERSION)

    def test_E07_sim_derivative_uses_source_seconds_when_clock_available(self):
        scene, events, metadata = fixture()
        scene["task_spec"]["execution"]["arrival_tolerance_m"] = 1.
        traces = {"a": [(t, [x, .5, 1.]) for t, x in [(1, 0), (2, 1), (3, 1.5), (4, 1.7), (5, 1.7), (6, 1.7)]]}
        clock = {"a": dict(available=True, knots=[(0., 0.), (3., 6.)])}
        source = build_route_windows(scene, traces, events, metadata, 100, "truth", clock)[0]
        host = build_route_windows(scene, traces, events, metadata, 100, "truth")[0]
        self.assertEqual(source["arrival_s"], 5.)
        self.assertEqual(host["arrival_s"], 4.)
        self.assertEqual(source["speed_processing_version"], SIM_SOURCE_SPEED_VERSION)
        self.assertEqual(source["speed_time_basis"], "mapped_FCU_source_seconds")

    def test_E07_sim_does_not_use_fcu_velocity_or_bridge_invalid_rows(self):
        scene, events, metadata = fixture()
        # Extra zero velocity fields are deliberately untrustworthy for SIM.
        traces = {"a": [row(1, 0), row(2, 1.9), (2.5, None), row(3, 2), row(4, 2), row(5, 2), row(6, 2)]}
        window = build_route_windows(scene, traces, events, metadata, 100, "truth")[0]
        self.assertEqual(window["arrival_s"], 4.)
        self.assertFalse(window["trajectory_evidence_complete"])

    def test_E07_sim_gap_breaks_derivative_and_first_sample_has_no_speed(self):
        scene, events, metadata = fixture()
        traces = {"a": [(1., [0, .5, 1]), (2., [1.9, .5, 1]), (4., [2, .5, 1]), (5., [2, .5, 1]), (6., [2, .5, 1])]}
        window = build_route_windows(scene, traces, events, metadata, 100, "truth")[0]
        self.assertEqual(window["arrival_s"], 5.)

    def test_E07_closest_fallback_is_post_event_and_unverified(self):
        scene, events, metadata = fixture()
        traces = {"a": [row(1, 2), row(2, 1., 1), row(3, 1.5, 1), row(4, 1.9, 1), row(5, 1.8, 1), row(6, 1.7, 1)]}
        window = build_route_windows(scene, traces, events, metadata, 100, "observation")[0]
        self.assertEqual(window["arrival_s"], 4.)
        self.assertEqual(window["arrival_source"], "trajectory_min_distance")
        self.assertFalse(window["arrival_verified"])

    def test_E07_missing_terminal_event_cannot_manufacture_service_window(self):
        scene, events, metadata = fixture()
        traces = {"a": [row(t, 2) for t in range(1, 7)]}
        windows = build_route_windows(scene, traces, events[:-1], metadata, 100, "observation")
        self.assertIsNone(windows[0]["arrival_s"])
        self.assertFalse(windows[0]["complete_execution_window"])
        self.assertIsNone(service_window_view(windows)[0]["start_s"])
        self.assertEqual(windows[0]["start_s"], 1.)

    def test_E07_missing_trajectory_retains_explicit_unverified_event_fallback(self):
        scene, events, metadata = fixture()
        window = build_route_windows(scene, {}, events, metadata, 100, "truth")[0]
        self.assertEqual(window["arrival_s"], 2.)
        self.assertEqual(window["arrival_source"], "event_fallback")
        self.assertFalse(window["arrival_verified"])
        self.assertFalse(window["complete_execution_window"])

    def test_E07_release_timestamp_not_logging_timestamp_ends_phase(self):
        scene, events, metadata = fixture(two_phases=True)
        traces = {"a": [row(t, 2) for t in range(1, 7)]}
        windows = build_route_windows(scene, traces, events, metadata, 100, "observation")
        self.assertEqual(windows[0]["end_s"], 4.)
        self.assertEqual(windows[1]["start_s"], 4.1)
        self.assertEqual(windows[1]["end_s"], 6.)
        self.assertEqual(windows[0]["end_event"], "next_phase_release")

    def test_E07_no_op_uses_explicit_events_and_never_activates_service(self):
        scene, _, metadata = fixture(no_op=True)
        events = [dict(event=kind, agent_id="a", phase="p0_observe", t=1.)
                  for kind in ("phase_no_op_started", "phase_no_op_ready")]
        window = build_route_windows(scene, {"a": [row(t, 0) for t in range(1, 7)]}, events, metadata, 100, "observation")[0]
        self.assertEqual(window["start_event"], "phase_no_op_started")
        self.assertEqual(window["start_s"], window["arrival_s"])
        self.assertEqual(window["role"], "hold_no_op")
        self.assertFalse(window["service_enabled"])
        self.assertEqual(window["waypoint_events"], [])
        missing = build_route_windows(scene, {}, events[:1], metadata, 100, "truth")[0]
        self.assertIsNone(missing["arrival_s"])

    def test_E07_epoch_shift_and_failed_missing_events_remain_unknown(self):
        scene, events, metadata = fixture()
        traces = {"a": [row(t + 10, 2) for t in range(1, 7)]}
        window = build_route_windows(scene, traces, events, metadata, 90, "observation")[0]
        self.assertEqual((window["start_s"], window["arrival_s"], window["end_s"]), (11., 12., 16.))
        metadata.pop("mission_end_monotonic_s")
        metadata["status"] = "failed"
        result = evaluate_mission_v3(scene, {}, {}, [], metadata, 100)
        self.assertIsNone(result["labels"]["mission_success"])
        self.assertIsNone(result["labels"]["mission_success_observation"])
        self.assertEqual(result["labels"]["semantic_consistency"], "unknown")

    def test_E07_registry_coverage_excludes_barrier_wait_and_channels_stay_independent(self):
        scene, events, metadata = fixture()
        phase = scene["phases"][0]
        phase["routes"]["a"] = [point(.5)]
        role = scene["semantic_plan"]["execution_phases"][phase["name"]]["agents"]["a"]
        role.update(terminal_point=point(.5), waypoint_planner_indices=[0])
        events = [events[0], events[1], dict(event="waypoint_reached", agent_id="a", phase=phase["name"], seq=2, t=2.)]
        observed = {"a": [row(1, .5), row(2, .5), row(3, 1.5), row(4, 1.5), row(5, 1.5), row(6, 1.5)]}
        truth = {"a": [(t, values[:3]) for t, values in observed["a"]]}
        original = copy.deepcopy((scene, observed, truth, events, metadata))
        result = evaluate_mission_v3(scene, observed, truth, events, metadata, 100)
        for channel in ("truth", "observation"):
            self.assertEqual(result["semantic_validation"][channel]["coverage"]["global_coverage_ratio"], .5)
            window = result["phase_windows"]["channels"][channel][0]
            self.assertEqual((window["arrival_s"], window["end_s"]), (2., 6.))
        self.assertEqual(result["phase_windows"]["schema_version"], 2)
        self.assertEqual(result["phase_windows"]["window_channel"], "observation")
        self.assertEqual((scene, observed, truth, events, metadata), original)

    def test_E07_return_dwell_uses_full_return_window_after_arrival(self):
        scene, events, metadata = fixture(two_phases=True)
        scene["task_spec"]["mission"]["return_required"] = True
        traces = {"a": [row(1, 2), row(2, 2), row(3, 2), row(4, 2), row(4.5, 1), row(5, 0), row(5.5, 0), row(6, 0)]}
        clocks = {"a": dict(available=True, knots=[(0., 0.), (7., 7.)])}
        result = evaluate_mission_v3(scene, traces, {"a": [(t, values[:3]) for t, values in traces["a"]]},
                                     events, metadata, 100, clocks)
        self.assertTrue(result["semantic_validation"]["observation"]["return_to_launch"]["success"])
        self.assertTrue(result["semantic_validation"]["truth"]["return_to_launch"]["success"])
        self.assertEqual(result["phase_windows"]["channels"]["observation"][1]["arrival_s"], 5.)
        self.assertEqual(result["phase_windows"]["channels"]["truth"][1]["arrival_s"], 5.5)


if __name__ == "__main__":
    unittest.main()
