"""Hand-computable shared coverage and lifecycle evidence, independent of planner."""

import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from swarm_sim.execution_constraints import evaluate_execution_constraints
from swarm_sim.mission_evaluation import evaluate_mission, tri_and, window_evidence


def fixture(agents=2, radius=0.1, grid=1.0, return_required=False):
    vehicles = [dict(id=f"uav_{i + 1:02}", east_m=i + 0.5, north_m=-1) for i in range(agents)]
    ids = [v["id"] for v in vehicles]
    spec = dict(schema_version=2, scenario=dict(regions=[dict(id="R", min_east_m=0, min_north_m=0, width_m=2, height_m=1)],
               world=dict(east_bounds_m=[-10, 10], north_bounds_m=[-10, 10], flight_up_bounds_m=[3, 20])),
               mission=dict(intent="reconnaissance", objective="area_coverage", target_region_id="R", coverage_required=1,
                   return_required=return_required, observation_model=dict(radius_m=radius, height_tolerance_m=1, grid_m=grid)),
               execution=dict(takeoff_alt_m=8, max_gap_s=1.1, confirmation_dwell_s=0.5, arrival_tolerance_m=0.1, record_hz=10, min_separation_m=1),
               platform=dict(max_path_length_m=100, max_airborne_time_s=100, reserve_time_s=10,
                             max_speed_m_s=6, max_climb_rate_m_s=2, max_horizontal_accel_m_s2=3))
    phases = [dict(name="observe_0")]
    mapping = {"observe_0": dict(semantic_phase="observe", agents={a: dict(role="observe", service_enabled=True, partition_id=a) for a in ids})}
    events = [dict(event=kind, phase="observe_0", agent_id=a, t=t) for a in ids
              for kind, t in [("phase_start_sent", 0), ("phase_auto_confirmed", 0), ("task_target_verified", 1)]]
    if return_required:
        phases.append(dict(name="return_0"))
        mapping["return_0"] = dict(semantic_phase="return", agents={a: dict(role="return", service_enabled=False, partition_id=a) for a in ids})
        events.extend(dict(event=kind, phase="return_0", agent_id=a, t=t) for a in ids
                      for kind, t in [("phase_start_sent", 2), ("task_target_verified", 3)])
    scene = dict(task_spec=spec, vehicles=vehicles, phases=phases, semantic_plan=dict(execution_phases=mapping))
    metadata = dict(run_epoch_monotonic_s=100, elapsed_s=4, status="completed")
    clocks = {a: dict(available=True, knots=[(0, 0), (10, 10)]) for a in ids}
    traces = {a: [(0, [i + 0.5, 0.5, 8, 0, 0, 0]), (1, [i + 0.5, 0.5, 8, 0, 0, 0])] for i, a in enumerate(ids)}
    return scene, traces, events, metadata, clocks


def evaluate(data, truth=None):
    scene, traces, events, metadata, clocks = data
    return evaluate_mission(scene, traces, traces if truth is None else truth, events, metadata, 100, clocks)


class SharedMissionEvidenceTests(unittest.TestCase):
    def test_V01_complementary_halves_union(self):
        result = evaluate(fixture())["semantic_validation"]
        coverage = result["truth"]["coverage"]
        self.assertEqual(coverage["global_coverage_ratio"], 1)
        self.assertEqual([v["coverage_ratio"] for v in coverage["per_agent"].values()], [0.5, 0.5])
        self.assertEqual([v["leave_one_out_coverage_drop"] for v in coverage["per_agent"].values()], [0.5, 0.5])
        self.assertTrue(result["pass_for_eligibility"])

    def test_V02_duplicate_half_not_double_counted(self):
        data = fixture()
        data[1]["uav_02"] = copy.deepcopy(data[1]["uav_01"])
        result = evaluate(data)["semantic_validation"]
        coverage = result["truth"]["coverage"]
        self.assertEqual(coverage["global_coverage_ratio"], 0.5)
        self.assertEqual(coverage["repeated_coverage_cell_ratio"], 0.5)
        self.assertEqual([v["leave_one_out_coverage_drop"] for v in coverage["per_agent"].values()], [0, 0])
        self.assertIs(result["mission_success"], False)

    def test_V03_one_agent_compensates_for_other(self):
        data = fixture()
        data[1]["uav_01"][-1] = (1, [1.5, 0.5, 8, 0, 0, 0])
        data[1]["uav_02"] = [(0, [9, 9, 8]), (1, [9, 9, 8])]
        result = evaluate(data)["semantic_validation"]["truth"]
        self.assertTrue(result["mission_success"])
        self.assertEqual(result["coverage"]["per_agent"]["uav_02"]["coverage_ratio"], 0)

    def test_V04_only_planned_geometry_is_unknown(self):
        data = fixture()
        data[0]["planning"] = dict(nominal_global_coverage=1)
        data[1].clear()
        data[2].clear()
        result = evaluate(data)["labels"]
        self.assertIsNone(result["mission_success"])
        self.assertEqual(result["requested_intent"], "reconnaissance")
        self.assertEqual(result["unverified_behaviors"]["split"], "not_evaluated")

    def test_V05_completed_run_with_insufficient_coverage_fails(self):
        data = fixture(agents=1)
        result = evaluate(data)["labels"]
        self.assertEqual(result["run_status"], "completed")
        self.assertIs(result["mission_success"], False)

    def test_V06_missing_evidence_prevents_negative_conclusion(self):
        data = fixture(agents=1)
        data[1]["uav_01"].insert(1, (0.5, None))
        result = evaluate(data)["semantic_validation"]["truth"]
        self.assertEqual(result["coverage"]["global_coverage_ratio"], 0.5)
        self.assertIsNone(result["mission_success"])

    def test_V07_coverage_monotonic_despite_missing_data(self):
        data = fixture()
        data[1]["uav_01"].insert(1, (0.5, None))
        result = evaluate(data)["semantic_validation"]["truth"]
        self.assertTrue(result["mission_success"])
        self.assertFalse(result["coverage"]["evidence_complete"])

    def test_V08_height_disabled_service_idle_excluded(self):
        for variant in ("height", "disabled", "idle"):
            data = fixture()
            if variant == "height":
                data[1]["uav_02"] = [(0, [1.5, 0.5, 10]), (1, [1.5, 0.5, 10])]
            elif variant == "disabled":
                data[0]["semantic_plan"]["execution_phases"]["observe_0"]["agents"]["uav_02"]["service_enabled"] = False
            else:
                data[0]["semantic_plan"]["execution_phases"]["observe_0"]["agents"]["uav_02"]["role"] = "idle_padding"
            with self.subTest(variant=variant):
                coverage = evaluate(data)["semantic_validation"]["truth"]["coverage"]
                self.assertEqual(coverage["global_coverage_ratio"], 0.5)

    def test_V09_gaps_barriers_and_service_boundary(self):
        # A disk with radius .1 at x=0 or x=2 cannot cover either x=.5/1.5 center.
        for rows in [[(0, [0, .5, 8]), (.05, None), (.1, [2, .5, 8])],
                     [(0, [0, .5, 8]), (2, [2, .5, 8])]]:
            data = fixture(agents=1)
            data[1]["uav_01"] = rows
            data[0]["task_spec"]["execution"]["max_gap_s"] = .5
            self.assertEqual(evaluate(data)["semantic_validation"]["truth"]["coverage"]["covered_cells"], 0)
        data = fixture(agents=1)
        data[1]["uav_01"] = [(0, [0, .5, 8]), (1, [2, .5, 8])]
        # Observe only the center part x=.8..1.2: it must not borrow outside-window coverage.
        for event in data[2]:
            event["t"] = .6 if event["event"] == "task_target_verified" else .4
        self.assertEqual(evaluate(data)["semantic_validation"]["truth"]["coverage"]["covered_cells"], 0)
        self.assertFalse(window_evidence([(0, [0, 0, 8]), (0, [1, 0, 8])], 0, 1, 1)["complete"])

    def test_V10_return_requires_geometry_and_dwell(self):
        data = fixture(return_required=True)
        for vehicle in data[0]["vehicles"]:
            data[1][vehicle["id"]].extend([(2, [vehicle["east_m"], -1, 8]), (3, [vehicle["east_m"], -1, 8])])
        self.assertTrue(evaluate(data)["labels"]["mission_success"])
        data[1]["uav_02"][-2:] = [(2, [9, 9, 8]), (3, [9, 9, 8])]
        self.assertIs(evaluate(data)["labels"]["mission_success"], False)
        data[1]["uav_02"][-2:] = [(2, None), (3, None)]
        self.assertIsNone(evaluate(data)["labels"]["mission_success"])

    def test_V11_events_without_positions_do_not_validate(self):
        data = fixture()
        data[1].clear()
        self.assertIsNone(evaluate(data)["labels"]["mission_success"])

    def test_V12_truth_observation_disagreement(self):
        data = fixture()
        truth = copy.deepcopy(data[1])
        truth["uav_02"] = copy.deepcopy(truth["uav_01"])
        result = evaluate(data, truth)["semantic_validation"]
        self.assertIs(result["mission_success"], False)
        self.assertTrue(result["mission_success_observation"])
        self.assertEqual(result["semantic_consistency"], "disagree")
        self.assertFalse(result["pass_for_eligibility"])

    def test_V13_missing_truth_never_falls_back_to_fcu(self):
        result = evaluate(fixture(), {})["semantic_validation"]
        self.assertIsNone(result["mission_success"])
        self.assertTrue(result["mission_success_observation"])
        self.assertEqual(result["semantic_consistency"], "unknown")

    def test_V14_declared_discrete_grid_resolution(self):
        coarse = evaluate(fixture(radius=.1, grid=1))["semantic_validation"]["truth"]["coverage"]
        fine = evaluate(fixture(radius=.1, grid=.5))["semantic_validation"]["truth"]["coverage"]
        self.assertEqual((coarse["cells"], coarse["global_coverage_ratio"]), (2, 1))
        self.assertEqual((fine["cells"], fine["global_coverage_ratio"]), (8, 0))

    def test_false_dominates_unknown_and_source_time_no_extrapolation(self):
        self.assertIs(tri_and([False, None]), False)
        data = fixture(return_required=True)
        data[1]["uav_02"] = copy.deepcopy(data[1]["uav_01"])
        self.assertIs(evaluate(data)["labels"]["mission_success"], False)

    def test_wait_metrics_have_distinct_event_definitions(self):
        data = fixture(return_required=True)
        data[2].extend([dict(event="phase_finished", phase="observe_0", agent_id="uav_01", t=.5),
                        dict(event="phase_finished", phase="observe_0", agent_id="uav_02", t=.8)])
        windows = evaluate(data)["phase_windows"]
        first = windows["windows"][0]
        self.assertAlmostEqual(first["barrier_wait_host_s"], .3)
        self.assertEqual(first["scheduling_wait_host_s"], 1)
        self.assertAlmostEqual(windows["per_agent_wait"]["uav_01"]["barrier_wait_host_s"], .3)


class LifecycleConstraintsTests(unittest.TestCase):
    def context(self):
        scene, _, _, metadata, clocks = fixture(agents=1)
        events = [dict(event=k, agent_id="uav_01", t=t) for k, t in
                  [("armed_confirmed", 0), ("airborne_ready", 1), ("landing_started", 2), ("landed", 3)]]
        rows = {"uav_01": [(0, [0, 0, 0, 0, 0, 0]), (1, [0, 0, 8, 0, 0, 0]),
                            (2, [0, 0, 8, 0, 0, 0]), (3, [0, 0, 0, 0, 0, 0])]}
        return scene, rows, events, metadata, clocks

    def check(self, data, truth=None):
        scene, traces, events, metadata, clocks = data
        return evaluate_execution_constraints(scene, traces, traces if truth is None else truth,
                                              events, metadata, 100, clocks)

    def pair_context(self):
        scene, rows, events, metadata, clocks = self.context()
        scene["vehicles"].append(dict(id="uav_02", east_m=2, north_m=0))
        rows["uav_02"] = [(stamp, [2, *values[1:]]) for stamp, values in rows["uav_01"]]
        rows["uav_01"] = [(stamp, [-2, *values[1:]]) for stamp, values in rows["uav_01"]]
        events.extend(dict(event, agent_id="uav_02") for event in events[:])
        clocks["uav_02"] = copy.deepcopy(clocks["uav_01"])
        return scene, rows, events, metadata, clocks

    def test_lifecycle_separation_clear_and_between_sample_crossing(self):
        data = self.pair_context()
        result = self.check(data)
        self.assertTrue(result["lifecycle_separation_pass"])
        self.assertEqual(result["lifecycle_separation"]["truth"]["minimum_m"], 4)
        # Endpoint distances are 4m; relative motion crosses at the midpoint.
        data[1]["uav_01"][1] = (1, [2, 0, 8, 0, 0, 0])
        data[1]["uav_02"][1] = (1, [-2, 0, 8, 0, 0, 0])
        result = self.check(data)
        self.assertIs(result["hard_constraints_pass"], False)
        self.assertEqual(result["lifecycle_separation"]["truth"]["minimum_m"], 0)

    def test_ground_and_landing_pair_risks_not_hidden_by_cruise(self):
        for index in (0, 3):
            data = self.pair_context()
            stamp = data[1]["uav_01"][index][0]
            data[1]["uav_01"][index] = (stamp, [0, 0, 0, 0, 0, 0])
            data[1]["uav_02"][index] = (stamp, [0, 0, 0, 0, 0, 0])
            with self.subTest(index=index):
                self.assertIs(self.check(data)["lifecycle_separation_pass"], False)

    def test_pair_unknown_on_missing_evidence_and_false_dominates(self):
        data = self.pair_context()
        truth = copy.deepcopy(data[1])
        truth["uav_02"][1] = (1, None)
        result = self.check(data, truth)
        self.assertIsNone(result["lifecycle_separation_pass"])
        self.assertTrue(result["lifecycle_separation"]["observation"]["passed"])
        # A valid coincident point proves risk even with broken neighbouring segments.
        truth["uav_02"][2] = (2, [-2, 0, 8])
        result = self.check(data, truth)
        self.assertIs(result["lifecycle_separation_pass"], False)
        data[2][:] = [event for event in data[2] if event["event"] != "landed"]
        self.assertIs(self.check(data, truth)["lifecycle_separation_pass"], False)

    def test_pair_uses_fleet_window_after_neighbour_lands(self):
        data = self.pair_context()
        for event in data[2]:
            if event["agent_id"] == "uav_01" and event["event"] == "landed":
                event["t"] = 2
        data[1]["uav_02"][-1] = (3, [-2, 0, 0, 0, 0, 0])
        result = self.check(data)
        self.assertIs(result["lifecycle_separation_pass"], False)
        self.assertEqual(result["lifecycle_separation"]["truth"]["fleet_window_s"], [0, 3])

    def test_ground_transition_full_path_and_source_duration(self):
        result = self.check(self.context())
        self.assertTrue(result["hard_constraints_pass"])
        agent = result["per_agent"]["uav_01"]
        self.assertEqual(agent["truth"]["path_length_m"], 16)
        self.assertEqual(agent["armed_to_landed_source_s"], 3)

    def test_missing_trace_and_missing_lifecycle_unknown(self):
        data = self.context()
        self.assertIsNone(self.check(data, {})["hard_constraints_pass"])
        data[2].pop()
        self.assertIsNone(self.check(data)["hard_constraints_pass"])
        self.assertFalse(window_evidence([(0, None), (.1, [0, 0, 0]), (1, [0, 0, 0])],
                                         0, 1, 1, edge_allowance=.1)["complete"])

    def test_known_violation_dominates_missing_path(self):
        data = self.context()
        data[1]["uav_01"][1] = (1, [20, 0, 8, 0, 0, 0])
        data[1]["uav_01"][2] = (2, None)
        result = self.check(data)
        self.assertIs(result["hard_constraints_pass"], False)
        self.assertIs(result["per_agent"]["uav_01"]["world_bounds_pass"], False)
        data[2].pop()
        self.assertIs(self.check(data)["hard_constraints_pass"], False)

    def test_transition_lower_bound_not_a_cruise_constraint(self):
        data = self.context()
        data[1]["uav_01"][0] = (0, [0, 0, -.1, 0, 0, 0])
        self.assertTrue(self.check(data)["hard_constraints_pass"])
        data[1]["uav_01"][0] = (0, [0, 0, 21, 0, 0, 0])
        self.assertIs(self.check(data)["hard_constraints_pass"], False)

    def test_low_cruise_altitude_rejected_and_time_reserve(self):
        data = self.context()
        data[1]["uav_01"][1] = (1, [0, 0, 2, 0, 0, 0])
        self.assertIs(self.check(data)["hard_constraints_pass"], False)
        data = self.context()
        data[0]["task_spec"]["platform"].update(max_airborne_time_s=12, reserve_time_s=10)
        self.assertIs(self.check(data)["per_agent"]["uav_01"]["airborne_time_pass"], False)

    def test_acceleration_proxy_not_hard_gate_and_gap_barrier(self):
        data = self.context()
        data[1]["uav_01"][1] = (1, [0, 0, 8, 20, 0, 0])
        result = self.check(data)
        self.assertTrue(result["hard_constraints_pass"])
        proxy = result["per_agent"]["uav_01"]["proxy_dynamics"]
        self.assertTrue(proxy["horizontal_acceleration_exceeds_nominal"])
        self.assertFalse(proxy["hard_gate"])
        data[1]["uav_01"].insert(1, (.5, None))
        self.assertEqual(self.check(data)["per_agent"]["uav_01"]["proxy_dynamics"]["valid_difference_intervals"], 2)

    def test_missing_source_mapping_does_not_claim_time_pass(self):
        data = self.context()
        data[4].clear()
        self.assertIsNone(self.check(data)["per_agent"]["uav_01"]["airborne_time_pass"])


class SemanticEndBracketTests(unittest.TestCase):
    def analyze_fractional_return(self, root, condition):
        from swarm_sim.analysis import analyze_run
        from swarm_sim.recording import write_json
        from swarm_sim.scenario import enu_to_geo
        from swarm_sim.tasks import compile_task

        spec_path = Path(__file__).resolve().parents[1] / "missions/recon_shared_3uav.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["scenario"]["regions"][0].update(width_m=3.0, height_m=3.0)
        spec["scenario"]["vehicles"] = [dict(id="uav_01", sysid=1, east_m=1.5, north_m=-2.0, heading_deg=0)]
        scene = compile_task(spec)
        self.assertEqual(len(scene["phases"]), 4)
        root.mkdir()
        (root / "raw").mkdir()
        metadata = dict(version="synthetic-test", run_id=condition, scenario=scene, status="completed",
                        run_epoch_monotonic_s=100.0, flight_epoch_monotonic_s=100.0,
                        mission_end_monotonic_s=108.56, elapsed_s=11.0)
        write_json(root / "metadata.json", metadata)
        write_json(root / "scenario.json", scene)
        events = []
        for phase, (start, end) in zip(scene["phases"], ((0, 2), (2, 4), (4, 6), (6.5, 8.56))):
            events.extend(dict(event=kind, agent_id="uav_01", phase=phase["name"], t=t)
                          for kind, t in (("phase_start_sent", start), ("phase_auto_confirmed", start),
                                          ("phase_finished", end), ("task_target_verified", end)))
        (root / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
        raw, truth_packets = [], []
        for index in range(-20, 101):
            source = index / 10
            host = 100 + source * 1.1
            north = -2.0 if index >= 73 else 2.0
            lat, lon = enu_to_geo(1.5, north, scene["origin"])
            raw.append(dict(recv_monotonic_s=host, message=dict(mavpackettype="SYSTEM_TIME", time_boot_ms=(index + 20) * 100)))
            if condition == "missing_outside" and index >= 79:
                continue
            raw.append(dict(recv_monotonic_s=host, message=dict(mavpackettype="GLOBAL_POSITION_INT",
                       time_boot_ms=(index + 20) * 100, lat=round(lat * 1e7), lon=round(lon * 1e7),
                       alt=20000, vx=5100 if condition == "invalid_outside" and index == 79 else 0, vy=0, vz=0)))
            truth_packets.append(dict(TimeUS=(index + 20) * 100000, Lat=lat, Lng=lon,
                                 Alt=float("nan") if condition == "invalid_outside" and index == 79 else 20.0,
                                 Q1=1, Q2=0, Q3=0, Q4=0))
        (root / "raw/uav_01.jsonl").write_text("\n".join(json.dumps(p) for p in raw), encoding="utf-8")
        bin_path = root / "sitl/uav_01/logs/synthetic.BIN"
        bin_path.parent.mkdir(parents=True)
        bin_path.write_bytes(b"Synthetic SIM packet stream; only DFReader is mocked")

        def reader(_):
            messages = iter(SimpleNamespace(get_type=lambda: "SIM", to_dict=lambda p=p: p) for p in truth_packets)
            return SimpleNamespace(recv_match=lambda **_: next(messages, None), close=lambda: None)

        with patch("pymavlink.DFReader.DFReader_binary", side_effect=reader):
            return analyze_run(root)

    def test_analyze_fractional_return_retains_support_without_exporting_it(self):
        with tempfile.TemporaryDirectory() as temp:
            output, quality, labels = self.analyze_fractional_return(Path(temp) / "valid", "valid")
            self.assertTrue(labels["mission_success"])
            self.assertTrue(labels["mission_success_observation"])
            returned = labels["mission_metrics"]["observation"]["return_to_launch"]["per_agent"]["uav_01"]
            self.assertTrue(returned["evidence_complete"])
            # Host samples 8.1..8.5 yield 0.4/1.1 source seconds, insufficient
            # even with 0.1/1.1 allowance. Clipping the valid 8.6 support at
            # event end 8.56 yields 0.46/1.1, which satisfies the same rule.
            self.assertAlmostEqual(returned["longest_dwell_s"], .46 / 1.1, places=6)
            self.assertLess(.4 / 1.1 + returned["dwell_allowance_s"], .5)
            for filename in ("observations.csv", "truth.csv"):
                with (output / filename).open(encoding="utf-8", newline="") as file:
                    rows = list(csv.DictReader(file))
                self.assertEqual(len(rows), 86)
                self.assertEqual(float(rows[-1]["t_s"]), 8.5)
                self.assertTrue(all(row["valid"] == "1" for row in rows))
            self.assertEqual(quality["frames"], 86)
            support = json.loads((output / "semantic_validation.json").read_text())["evaluation_support"]
            self.assertEqual(support["extra_end_bracket_s"], 8.6)
            self.assertTrue(support["model_input_grid_unchanged"])

    def test_analyze_invalid_or_missing_outside_support_remains_unknown(self):
        for condition in ("invalid_outside", "missing_outside"):
            with self.subTest(condition=condition), tempfile.TemporaryDirectory() as temp:
                output, quality, labels = self.analyze_fractional_return(Path(temp) / condition, condition)
                self.assertIsNone(labels["mission_success"])
                self.assertIsNone(labels["mission_success_observation"])
                self.assertEqual(quality["frames"], 86)
                self.assertEqual(quality["observation_valid_fraction"]["uav_01"], 1)
                returned = labels["mission_metrics"]["observation"]["return_to_launch"]["per_agent"]["uav_01"]
                self.assertFalse(returned["evidence_complete"])


if __name__ == "__main__":
    unittest.main()
