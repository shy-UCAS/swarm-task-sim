import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from swarm_sim.recording import export_dataset, interpolate, segment_distance
from swarm_sim.scenario import enu_to_geo, geo_to_enu, load, mission_for, validate
from swarm_sim.vehicle import ManagedTCP, Vehicle
from swarm_sim.runner import run_scene
import flyControl

ROOT = Path(__file__).resolve().parents[1]


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.scenario = load(ROOT / "scenarios/demo_2uav.json")

    def test_duplicate_identity_and_path_injection_rejected(self):
        for key, value in (("sysid", 1), ("id", "uav_01"), ("id", "../escape")):
            scenario = copy.deepcopy(self.scenario)
            scenario["vehicles"][1][key] = value
            with self.assertRaises(ValueError):
                validate(scenario)

    def test_incomplete_phase_and_impossible_speed_rejected(self):
        broken = copy.deepcopy(self.scenario)
        del broken["phases"][0]["targets"]["uav_02"]
        with self.assertRaises(ValueError):
            validate(broken)
        for value in (float("nan"), float("inf"), 100, "5", True):
            broken = copy.deepcopy(self.scenario)
            broken["phases"][0]["targets"]["uav_01"]["speed_m_s"] = value
            with self.assertRaises(ValueError):
                validate(broken)

    def test_spawn_separation_checked(self):
        self.scenario["vehicles"][1]["east_m"] = 1
        with self.assertRaisesRegex(ValueError, "separation"):
            validate(self.scenario)

    def test_common_projection_roundtrip_and_height_datum(self):
        origin = self.scenario["origin"]
        lat, lon = enu_to_geo(100, -150, origin)
        east, north, up = geo_to_enu(lat, lon, origin["alt_msl_m"] + 12, origin)
        self.assertAlmostEqual(east, 100, places=6)
        self.assertAlmostEqual(north, -150, places=6)
        self.assertEqual(up, 12)

    def test_speed_and_hold_are_real_mission_parameters(self):
        target = self.scenario["phases"][0]["targets"]["uav_01"]
        plan = mission_for(self.scenario["vehicles"][0], target, self.scenario["origin"])
        self.assertEqual((plan[1]["command"], plan[1]["params"][1]), (178, 4))
        self.assertEqual(plan[-1]["params"][0], 2)


class DatasetTests(unittest.TestCase):
    def test_no_extrapolation_or_interpolation_across_long_gaps(self):
        samples = [(0, [0] * 6), (0.2, [2] * 6), (3, [3] * 6)]
        times = [s[0] for s in samples]
        self.assertEqual(interpolate(samples, times, 0.1, 0.5), [1] * 6)
        for t in (-0.1, 1, 3.1):
            self.assertIsNone(interpolate(samples, times, t, 0.5))

    def test_crossing_between_samples_is_detected(self):
        self.assertEqual(segment_distance([-1, 0, 0], [1, 0, 0], [1, 0, 0], [-1, 0, 0]), 0)
        self.assertEqual(segment_distance([0, 0, 0], [0, 4, 0], [1, 0, 0], [1, 4, 0]), 4)

    def test_raw_export_velocity_axes_masks_and_coverage(self):
        scenario = load(ROOT / "scenarios/demo_1uav.json")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "raw").mkdir()
            packets = []
            for t in (10, 10.2, 11):
                packets.append(dict(recv_monotonic_s=t, message=dict(mavpackettype="GLOBAL_POSITION_INT",
                    lat=round(scenario["origin"]["lat"] * 1e7), lon=round(scenario["origin"]["lon"] * 1e7),
                    alt=20000, vx=100, vy=200, vz=-300)))
            (root / "raw/uav_01.jsonl").write_text("\n".join(json.dumps(p) for p in packets), encoding="utf-8")
            quality = export_dataset(root, dict(scenario=scenario, flight_epoch_monotonic_s=10,
                                                mission_end_monotonic_s=11))
            self.assertEqual(quality["frames"], 11)
            self.assertGreater(quality["missing_by_agent"]["uav_01"], 0)
            self.assertIn(",2.0,1.0,3.0", (root / "processed.csv").read_text())


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.cancel = threading.Event()
        self.vehicle = Vehicle(dict(id="test", sysid=1), Path("unused.jsonl"), self.cancel, lambda *a, **k: None)

    def publish(self, kind, **fields):
        message = SimpleNamespace(get_type=lambda: kind, **fields)
        with self.vehicle.condition:
            self.vehicle.sequence += 1
            self.vehicle.inbox.append((self.vehicle.sequence, kind, message))
            self.vehicle.latest[kind] = (time.perf_counter(), message)
            self.vehicle.condition.notify_all()
        return message

    def test_control_inbox_does_not_consume_other_waiters_messages(self):
        ack = self.publish("COMMAND_ACK", command=400, result=0)
        self.publish("ATTITUDE", roll=0)
        self.assertIs(self.vehicle.wait_message(["COMMAND_ACK"], timeout=0.01), ack)
        self.assertIs(self.vehicle.wait_message(["COMMAND_ACK"], timeout=0.01), ack)

    def test_old_ack_is_not_accepted_for_new_command(self):
        self.publish("COMMAND_ACK", command=400, result=0)
        with patch.object(self.vehicle, "send"):
            with self.assertRaises(TimeoutError):
                self.vehicle.command(400, 1, timeout=0.02)

    def test_command_rejection_is_propagated(self):
        def send(*args):
            self.publish("COMMAND_ACK", command=400, result=4)
        with patch.object(self.vehicle, "send", side_effect=send):
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                self.vehicle.command(400, 1)

    def test_retransmitted_mission_item_does_not_complete_upload_early(self):
        scenario = load(ROOT / "scenarios/demo_1uav.json")
        mission = mission_for(scenario["vehicles"][0], scenario["phases"][0]["targets"]["uav_01"], scenario["origin"])
        requests = iter([0, 0, 1, 2])
        sent = []
        def send(method, *args):
            if method == "mission_clear_all_send":
                self.publish("MISSION_ACK", type=0)
            elif method == "mission_count_send":
                self.publish("MISSION_REQUEST", seq=next(requests))
            elif method == "mission_item_send":
                sent.append(args[2])
                seq = next(requests, None)
                if seq is None:
                    self.publish("MISSION_ACK", type=0)
                else:
                    self.publish("MISSION_REQUEST", seq=seq)
            elif method == "mission_set_current_send":
                self.publish("MISSION_CURRENT", seq=1)
        with patch.object(self.vehicle, "mode"), patch.object(self.vehicle, "send", side_effect=send):
            self.vehicle.upload(mission)
        self.assertEqual(sent, [0, 0, 1, 2])

    def test_cancel_interrupts_wait(self):
        self.cancel.set()
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            self.vehicle.wait_message(["HEARTBEAT"], timeout=30)

    def test_tcp_eof_and_disconnect_fail_immediately(self):
        transport = object.__new__(ManagedTCP)
        with self.assertRaises(ConnectionError):
            transport.handle_eof()
        with self.assertRaises(ConnectionError):
            transport.handle_disconnect()

    def test_legacy_mission_start_uses_param1_not_confirmation(self):
        calls = []
        master = SimpleNamespace(target_system=1, target_component=1,
                                 mav=SimpleNamespace(command_long_send=lambda *args: calls.append(args)))
        flyControl.send_mission_start(master, start_seq=7)
        self.assertEqual(calls[0][3], 0)
        self.assertEqual(calls[0][4], 7)


class LifecycleTests(unittest.TestCase):
    def test_launch_failure_preserves_failure_record_without_overwrite(self):
        scenario = load(ROOT / "scenarios/demo_1uav.json")
        with tempfile.TemporaryDirectory() as temp:
            path1, metadata, quality = run_scene(scenario, temp, Path(temp) / "missing.exe",
                                                 ROOT / "ArducopterSITL/copter.parm")
            self.assertEqual(metadata["status"], "failed")
            self.assertFalse(quality["usable"])
            self.assertTrue((path1 / "metadata.json").exists())
            path2, _, _ = run_scene(scenario, temp, Path(temp) / "missing.exe", ROOT / "ArducopterSITL/copter.parm")
            self.assertNotEqual(path1, path2)


if __name__ == "__main__":
    unittest.main()
