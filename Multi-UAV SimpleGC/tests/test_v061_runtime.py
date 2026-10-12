"""v0.6.1 execution contracts with fake clocks/transports; never launch SITL."""

import csv
import json
import tempfile
import struct
import threading
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from swarm_sim import processes, runner_v3
from swarm_sim.quality import resolve_policy
from swarm_sim.recording import Recorder
from swarm_sim.run_provenance import STAT_RESET_EPOCH, compare_parameter_readback, read_firmware_parameters
from swarm_sim.tasks import compile_task
from swarm_sim.vehicle import Vehicle
from test_parameter_comparison_v2 import STARTED, fixture
from test_run_provenance import InboxClient


ROOT = Path(__file__).resolve().parents[1]


def contract(speed):
    return {"execution": {"protocol_version": "v0.6.1", "sim_speedup": speed}}


def scene(speed):
    spec = json.loads((ROOT / "missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8"))
    result = compile_task(spec)
    result["task_spec"]["execution"].update(contract(speed)["execution"])
    return result


class SpeedupLaunchTests(unittest.TestCase):
    def test_launch_and_effective_parameter_file_use_declared_speedup_only_for_new_protocol(self):
        for protocol, speed in (("v0.5", 4), ("v0.6.1", 1), ("v0.6.1", 2), ("v0.6.1", 4)):
            with self.subTest(protocol=protocol, speed=speed), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                binary, params = root / "fake.exe", root / "frozen.parm"
                binary.write_bytes(b"synthetic binary: must never execute")
                params.write_text("SIM_SPEEDUP 1\nWPNAV_SPEED 500\n", encoding="utf-8")
                before = params.read_bytes()
                scenario = scene(speed)
                scenario["task_spec"]["execution"]["protocol_version"] = protocol
                owner = processes.SITLProcesses(binary, params, root / "run", scenario, 20100)
                process = Mock(pid=123, poll=Mock(return_value=0))
                with patch.object(processes.socket, "socket"), patch.object(processes.subprocess, "Popen", return_value=process) as launch:
                    owner.start()
                    owner.close()
                expected = speed if protocol == "v0.6.1" else 1
                for call in launch.call_args_list:
                    argv = call.args[0]
                    self.assertEqual(argv[argv.index("--speedup") + 1], str(expected))
                self.assertEqual(owner.metadata()["speedup"], expected)
                self.assertEqual(params.read_bytes(), before)
                for instance in owner.instances:
                    effective = Path(instance["directory"], "defaults.parm").read_text()
                    if protocol == "v0.6.1":
                        self.assertTrue(effective.endswith(f"SIM_SPEEDUP {expected}\n"))
                        self.assertEqual(instance["dynamic_parameter_overrides"], {"SIM_SPEEDUP": expected})
                        self.assertEqual(len(instance["defaults_sha256"]), 64)
                    else:
                        self.assertNotIn("dynamic_parameter_overrides", instance)
                        self.assertEqual(effective.count("SIM_SPEEDUP"), 1)

    def test_complete_speedup_mismatch_and_other_parameter_differences_still_reject(self):
        for declared, actual, other in ((1, 1, False), (2, 2, False), (4, 4, False),
                                        (2, 1, False), (4, 4, True)):
            evidence, baseline = fixture()
            baseline["baselines"][0]["agents"]["uav_01"]["all_parameters"]["SIM_SPEEDUP"] = 1.
            evidence["all_parameters"]["SIM_SPEEDUP"] = actual
            evidence["parameter_count"] += 1
            evidence["received_count"] += 1
            if other:
                evidence["all_parameters"]["WPNAV_SPEED"] += 1
            call = lambda: compare_parameter_readback(evidence, baseline, 1, run_started_utc=STARTED,
                                                       expected_sim_speedup=declared)
            if declared != actual or other:
                with self.assertRaises(ValueError):
                    call()
                self.assertIs(evidence["parameter_comparison"]["pass"], False)
            else:
                call()
                self.assertIs(evidence["parameter_comparison"]["pass"], True)
            self.assertTrue(evidence["parameter_comparison"]["collection_complete"])

    def test_incomplete_readback_is_unknown_in_new_protocol(self):
        evidence, baseline = fixture()
        evidence.update(complete=False, status="failed", parameter_count=None, received_count=0, all_parameters={})
        with self.assertRaises(ValueError):
            compare_parameter_readback(evidence, baseline, 1, run_started_utc=STARTED, expected_sim_speedup=2)
        self.assertIsNone(evidence["parameter_comparison"]["pass"])

    def test_physically_complete_but_changed_parameter_collection_is_confirmed_conflict(self):
        for change in ("added", "removed", "renamed"):
            evidence, baseline = fixture()
            baseline["baselines"][0]["agents"]["uav_01"]["all_parameters"]["SIM_SPEEDUP"] = 1.
            actual = evidence["all_parameters"]
            actual["SIM_SPEEDUP"] = 1.
            if change in ("removed", "renamed"):
                actual.pop("WPNAV_ACCEL")
            if change in ("added", "renamed"):
                actual["UNEXPECTED_PARAMETER"] = 100.
            evidence.update(parameter_count=len(actual), received_count=len(actual))
            with self.subTest(change=change), self.assertRaises(ValueError):
                compare_parameter_readback(evidence, baseline, 1, run_started_utc=STARTED, expected_sim_speedup=1)
            comparison = evidence["parameter_comparison"]
            self.assertIs(comparison["collection_complete"], True)
            self.assertIs(comparison["collection_matches_frozen"], False)
            self.assertIs(comparison["pass"], False)

    def test_fractional_speedup_compares_exact_mavlink_float32_without_tolerance(self):
        evidence, baseline = fixture()
        wire = struct.unpack("f", struct.pack("f", 1.2))[0]
        self.assertNotEqual(wire, 1.2)
        baseline["baselines"][0]["agents"]["uav_01"]["all_parameters"]["SIM_SPEEDUP"] = 1.
        evidence["all_parameters"]["SIM_SPEEDUP"] = wire
        evidence["parameter_count"] += 1
        evidence["received_count"] += 1
        compare_parameter_readback(evidence, baseline, 1, run_started_utc=STARTED, expected_sim_speedup=1.2)
        self.assertIs(evidence["parameter_comparison"]["pass"], True)
        self.assertEqual(evidence["parameter_comparison"]["sim_speedup"]["expected_parameter_float32"], wire)
        evidence["all_parameters"]["SIM_SPEEDUP"] = wire + 1e-7
        with self.assertRaisesRegex(ValueError, "SIM_SPEEDUP"):
            compare_parameter_readback(evidence, baseline, 1, run_started_utc=STARTED, expected_sim_speedup=1.2)

    def test_runtime_firmware_conflict_has_explicit_evidence_before_readback(self):
        client = InboxClient([])
        client.wait_message = Mock(return_value=SimpleNamespace(flight_sw_version=(4 << 24) + (5 << 8),
                                                               to_dict=lambda: {}))
        evidence = {}
        with self.assertRaisesRegex(ValueError, "AUTOPILOT_VERSION differs"):
            read_firmware_parameters(client, {"version_string": "ArduCopter V4.0.4-dev (hash)"}, evidence, sim_time=True)
        self.assertIs(evidence["firmware"]["confirmed_mismatch"], True)
        self.assertEqual(evidence["received_count"], 0)

    def test_runner_forwards_declared_speed_and_readback_mismatch_prevents_all_takeoff(self):
        scenario = scene(2)
        _, baseline = fixture()
        reference = baseline["baselines"][0]["agents"]["uav_01"]["all_parameters"]
        reference["SIM_SPEEDUP"] = 1.
        process = Mock()
        process.instances = [dict(id=v["id"], sysid=v["sysid"]) for v in scenario["vehicles"]]
        process.processes = [Mock(poll=Mock(return_value=0)) for _ in process.instances]
        process.start.return_value = process.instances
        process.metadata.return_value = {"sha256": "binary", "speedup": 2}
        clients = []
        def make_client(instance, *args, **kwargs):
            self.assertEqual(kwargs["time_contract"], scenario)
            client = Mock(id=instance["id"], sysid=instance["sysid"])
            clients.append(client)
            return client
        def read(client, firmware, evidence, **kwargs):
            self.assertIs(kwargs["sim_time"], True)
            actual = dict(reference, SYSID_THISMAV=client.sysid,
                          STAT_RESET=(datetime.now(timezone.utc)-STAT_RESET_EPOCH).total_seconds())
            evidence.update(complete=True, status="complete", all_parameters=actual,
                            parameter_count=len(actual), received_count=len(actual), missing_indices=[])
            return evidence
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            stack.enter_context(patch.object(runner_v3, "validate", return_value=scenario))
            stack.enter_context(patch.object(runner_v3, "validate_task_binding"))
            stack.enter_context(patch.object(runner_v3, "verify_preflight_files", return_value=dict(
                status="files_verified", actual=dict(firmware={"sha256": "binary"}, parameters_sha256="params"),
                baseline=baseline)))
            stack.enter_context(patch.object(runner_v3, "digest", return_value="params"))
            stack.enter_context(patch.object(runner_v3, "SITLProcesses", return_value=process))
            stack.enter_context(patch.object(runner_v3, "Vehicle", side_effect=make_client))
            recorder = stack.enter_context(patch.object(runner_v3, "Recorder"))
            recorder.return_value.error = None
            recorder.return_value.source_clock = {"reference_agent_id": None, "status": "awaiting_source"}
            stack.enter_context(patch.object(runner_v3, "read_firmware_parameters", side_effect=read))
            stack.enter_context(patch("swarm_sim.analysis.analyze_run", side_effect=ValueError("synthetic no flight")))
            stack.enter_context(patch("builtins.print"))
            _, metadata, quality = runner_v3.run_scene_v3(scenario, temp, "binary", "params")
        self.assertEqual(metadata["status"], "failed")
        self.assertIn("SIM_SPEEDUP", metadata["error"])
        self.assertEqual(metadata["time_base"], "sim_source")
        self.assertEqual(metadata["sim_speedup"], 2)
        self.assertFalse(quality["episode_quality_eligible"])
        per_agent = metadata["run_provenance"]["parameter_evidence"]["per_agent"]
        self.assertTrue(any(row["parameter_comparison"].get("pass") is False and
                            row["parameter_comparison"].get("collection_complete") is True for row in per_agent.values()))
        for client in clients:
            client.prepare_airborne.assert_not_called()
        process.close.assert_called_once()


class RelativeTimingTests(unittest.TestCase):
    def test_relative_departures_and_phase_release_are_same_sim_seconds_at_1_2_4(self):
        outputs = []
        for speed in (1, 2, 4):
            scenario = scene(speed)
            phase = scenario["phases"][1]
            scenario["phases"] = [phase]
            phase["start_delays_s"] = {v["id"]: i*3.5 for i, v in enumerate(scenario["vehicles"])}
            clients = [Mock(id=v["id"]) for v in scenario["vehicles"]]
            metadata = {"quality_policy": resolve_policy()}
            clock = [100.]
            def parallel(function, **kwargs):
                for client, vehicle in zip(clients, scenario["vehicles"]):
                    function(client, vehicle)
                clock[0] += .001
            with patch.object(runner_v3.time, "perf_counter", side_effect=lambda: clock[0]):
                runner_v3.execute_phases(scenario, clients, parallel, Mock(), metadata, 100., 1000., lambda: None)
            releases = [client.execute.call_args.args[0] for client in clients]
            offsets = [(value-releases[0])*speed for value in releases]
            for observed, expected in zip(offsets, (0, 3.5, 7.0)):
                self.assertAlmostEqual(observed, expected, places=10)
            self.assertAlmostEqual((releases[0]-100.001)*speed, .3, places=10)
            timing = metadata["phase_timing"][phase["name"]]
            self.assertEqual(timing["agent_start_delays_sim_s"], phase["start_delays_s"])
            outputs.append(runner_v3.phase_time_budget(scenario, phase, 1000.))
        self.assertEqual(outputs[0], outputs[1])  # Pure host deadlines are never shortened.
        self.assertEqual(outputs[0], outputs[2])

    def test_takeoff_stability_is_source_seconds_and_receive_age_is_converted(self):
        for speed in (1, 2, 4):
            clock, decisions = [100.], []
            vehicle = Vehicle(dict(id="uav_01", sysid=1), Path("unused"), threading.Event(), Mock(),
                              time_contract=contract(speed))
            vehicle.command = vehicle.mode = Mock()
            def wait_state(predicate, timeout, description):
                if description == "takeoff did not stabilize":
                    for elapsed in (0, .5, .99, 1.):
                        clock[0] = 100 + elapsed/speed
                        state = {"GLOBAL_POSITION_INT": (clock[0], SimpleNamespace(time_boot_ms=10000+elapsed*1000,
                                                                relative_alt=10000, vz=0))}
                        decisions.append(predicate(state))
                    self.assertTrue(decisions[-1])
                return {}
            vehicle.wait_state = wait_state
            with patch("swarm_sim.vehicle.time.perf_counter", side_effect=lambda: clock[0]):
                vehicle.prepare_airborne(10, 60)
            self.assertEqual(decisions, [False, False, False, True])
            self.assertAlmostEqual(vehicle.evidence_age(100, 100+.4/speed), .4, places=10)

    def test_heartbeat_period_tracks_sim_seconds_without_changing_host_stale_timeout(self):
        for speed in (1, 2, 4):
            with tempfile.TemporaryDirectory() as temp:
                clock, sent = [100.], []
                vehicle = Vehicle(dict(id="uav_01", sysid=1), Path(temp) / "raw.jsonl", threading.Event(), Mock(),
                                  time_contract=contract(speed))
                vehicle.send = lambda method, *args: sent.append((clock[0]-100)*speed)
                def receive(**kwargs):
                    clock[0] += .25/speed
                    if (clock[0]-100)*speed >= 2:
                        vehicle.stop.set()
                    return None
                vehicle.master = SimpleNamespace(recv_match=receive)
                with patch("swarm_sim.vehicle.time.perf_counter", side_effect=lambda: clock[0]):
                    vehicle._receive()
                    self.assertIsNone(vehicle.error)
                    self.assertEqual(sent, [0, 1])
                    vehicle.latest["HEARTBEAT"] = (clock[0]-4.99, object())
                    vehicle.check()
                    vehicle.latest["HEARTBEAT"] = (clock[0]-5.01, object())
                    with self.assertRaisesRegex(TimeoutError, "5 s"):
                        vehicle.check()


class SourceRecordingTests(unittest.TestCase):
    def test_source_driven_ten_hz_recording_ignores_host_clock_scale(self):
        outputs = []
        for speed in (1, 2, 4):
            with tempfile.TemporaryDirectory() as temp:
                elapsed = [0.]
                scenario = scene(speed)
                origin = scenario["origin"]
                def snapshot():
                    message = SimpleNamespace(time_boot_ms=10000+round(elapsed[0]*1000),
                        lat=round(origin["lat"]*1e7), lon=round(origin["lon"]*1e7),
                        alt=round((origin["alt_msl_m"]+10)*1000), relative_alt=10000, vx=0, vy=0, vz=0)
                    return {"GLOBAL_POSITION_INT": (100+elapsed[0]/speed, message)}
                vehicle = SimpleNamespace(id="uav_01", sysid=1, snapshot=snapshot)
                recorder = Recorder(Path(temp), [vehicle], origin, 100, 10, .5, time_contract=contract(speed))
                recorder.stop = SimpleNamespace(is_set=lambda: elapsed[0] > 1.001,
                                               wait=lambda seconds: elapsed.__setitem__(0, elapsed[0]+.05))
                with patch("swarm_sim.recording.time.perf_counter", side_effect=lambda: 100+elapsed[0]/speed):
                    recorder._run()
                self.assertIsNone(recorder.error)
                with Path(temp, "samples.csv").open(newline="") as file:
                    rows = list(csv.DictReader(file))
                self.assertEqual(len(rows), 11)
                self.assertTrue(all(row["time_base"] == "sim_source" and row["valid_position"] == "1" for row in rows))
                self.assertTrue(all(row["velocity_time_base"] == "agent_source" for row in rows))
                outputs.append([row["t"] for row in rows])
                self.assertEqual(recorder.source_clock["reference_agent_id"], "uav_01")
                self.assertEqual(recorder.source_clock["skipped_ticks"], 0)
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], outputs[2])

    def test_live_sampling_reference_is_fixed_and_missing_source_never_falls_back_to_host(self):
        vehicles = [SimpleNamespace(id=f"uav_0{i}", sysid=i) for i in (3, 1, 2)]
        recorder = Recorder(Path("unused"), vehicles, {}, 100, 10, .5, time_contract=contract(2))
        states = {v.id: {} for v in vehicles}
        self.assertIsNone(recorder._source_stamp(states))
        self.assertIsNone(recorder.source_clock["reference_agent_id"])
        for agent, boot in (("uav_02", 5000), ("uav_03", 9000)):
            states[agent] = {"GLOBAL_POSITION_INT": (100, SimpleNamespace(time_boot_ms=boot))}
        self.assertEqual(recorder._source_stamp(states), 0)
        self.assertEqual(recorder.source_clock["reference_agent_id"], "uav_02")
        states["uav_01"] = {"GLOBAL_POSITION_INT": (100, SimpleNamespace(time_boot_ms=4000))}
        states["uav_02"]["GLOBAL_POSITION_INT"][1].time_boot_ms = 5500
        self.assertEqual(recorder._source_stamp(states), .5)
        states["uav_02"] = {}
        with self.assertRaisesRegex(ValueError, "disappeared or reset"):
            recorder._source_stamp(states)
        self.assertEqual(recorder.source_clock["status"], "invalid_source")


if __name__ == "__main__":
    unittest.main()
