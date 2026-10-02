"""WP-S contracts checked without launching a SITL process."""

import copy
import json
import math
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import spike_continuous_route as spike
from swarm_sim.scenario import enu_to_geo
from swarm_sim.tasks import compile_task


ROOT = Path(__file__).resolve().parents[1]
MISSION = ROOT / "missions" / "recon_shared_3uav.json"


def canonical_scene():
    return compile_task(json.loads(MISSION.read_text(encoding="utf-8")))


class SpikePlanTests(unittest.TestCase):
    def test_canonical_geometry_preserves_frozen_input(self):
        scene = canonical_scene()
        original = copy.deepcopy(scene)
        plan = spike.build_spike_plan(scene)
        self.assertEqual(scene, original)
        self.assertEqual([phase["semantic_phase"] for phase in plan["phases"]],
                         ["approach", "observe", "return"])
        self.assertEqual(len(scene["phases"]), 12)
        approach, observe, returning = plan["phases"]
        for index, vehicle in enumerate(scene["vehicles"]):
            agent = vehicle["id"]
            with self.subTest(agent=agent):
                # Five lanes in each 18 m strip, spaced 3.6 m apart.
                expected = []
                for lane in range(5):
                    east = index * 18 + (lane + .5) * 3.6
                    norths = (0., 30.) if lane % 2 == 0 else (30., 0.)
                    expected.extend(dict(east_m=east, north_m=north, up_m=8.)
                                    for north in norths)
                self.assertEqual(len(approach["routes"][agent]), 1)
                self.assertEqual(len(observe["routes"][agent]), 9)
                self.assertEqual(len(returning["routes"][agent]), 1)
                for actual, reference in zip(approach["routes"][agent] + observe["routes"][agent], expected):
                    for coordinate in ("east_m", "north_m", "up_m"):
                        self.assertAlmostEqual(actual[coordinate], reference[coordinate])
                self.assertEqual(observe["start_positions"][agent], approach["routes"][agent][-1])
                self.assertEqual(returning["start_positions"][agent], observe["routes"][agent][-1])
                self.assertEqual(returning["routes"][agent][-1],
                                 dict(east_m=vehicle["east_m"], north_m=vehicle["north_m"], up_m=8.))

    def test_observe_drops_only_the_repeated_start(self):
        scene = canonical_scene()
        phase = spike.build_spike_plan(scene)["phases"][1]
        for agent, route in phase["routes"].items():
            self.assertEqual(len(route), 9)
            positions = [phase["start_positions"][agent]] + route
            for before, after in zip(positions, positions[1:]):
                self.assertGreater(math.dist([before[k] for k in ("east_m", "north_m", "up_m")],
                                             [after[k] for k in ("east_m", "north_m", "up_m")]), .05)

    def test_upload_items_hold_only_the_terminal_waypoint(self):
        scene = canonical_scene()
        phase = spike.build_spike_plan(scene)["phases"][1]
        vehicle = scene["vehicles"][0]
        route = phase["routes"][vehicle["id"]]
        mission = spike.route_mission_for(vehicle, route, 3., .5, scene["origin"])
        self.assertEqual(len(mission), 11)
        self.assertEqual([item["command"] for item in mission], [16, 178] + [16] * 9)
        self.assertEqual([item["frame"] for item in mission], [3, 2] + [3] * 9)
        self.assertEqual(mission[1]["params"], [1, 3., -1, 0])
        self.assertEqual([item["params"][0] for item in mission[2:]], [0.] * 8 + [.5])
        for point, item in zip(route, mission[2:]):
            latitude, longitude = enu_to_geo(point["east_m"], point["north_m"], scene["origin"])
            self.assertAlmostEqual(item["lat"], latitude)
            self.assertAlmostEqual(item["lon"], longitude)
            self.assertEqual(item["alt"], 8.)

    def test_approach_and_return_are_single_waypoint_missions(self):
        scene = canonical_scene()
        plan = spike.build_spike_plan(scene)
        for phase in (plan["phases"][0], plan["phases"][2]):
            for vehicle in scene["vehicles"]:
                with self.subTest(phase=phase["semantic_phase"], agent=vehicle["id"]):
                    mission = spike.route_mission_for(vehicle, phase["routes"][vehicle["id"]],
                                                     phase["speed_m_s"], phase["terminal_hold_s"], scene["origin"])
                    self.assertEqual(len(mission), 3)
                    self.assertEqual(mission[-1]["params"][0], .5)

    def test_overshoot_rejects_nonfinite_bool_negative_or_excess(self):
        scene = canonical_scene()
        for value in (True, float("nan"), float("inf"), -0.1, 4.0001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                spike.build_spike_plan(scene, lane_end_overshoot_m=value)

    def test_overshoot_extends_sweep_ends_without_moving_lanes_or_return(self):
        scene = canonical_scene()
        plan = spike.build_spike_plan(scene, lane_end_overshoot_m=4.)
        for agent in plan["phases"][1]["routes"]:
            scan = plan["phases"][0]["routes"][agent] + plan["phases"][1]["routes"][agent]
            self.assertEqual({point["north_m"] for point in scan}, {-4., 34.})
            self.assertEqual(len({round(point["east_m"], 8) for point in scan}), 5)
            self.assertEqual(plan["phases"][2]["routes"][agent][-1]["north_m"], -15.)

    def test_overshoot_cannot_leave_declared_world(self):
        spec = json.loads(MISSION.read_text(encoding="utf-8"))
        spec["scenario"]["world"]["north_bounds_m"] = [-20., 30.]
        scene = compile_task(spec)
        with self.assertRaises(ValueError):
            spike.build_spike_plan(scene, lane_end_overshoot_m=1.)


class ParameterReadbackTests(unittest.TestCase):
    @staticmethod
    def parameter(index, count=3, name=None, value=1.):
        return SimpleNamespace(param_index=index, param_count=count,
                               param_id=name or f"PARAM_{index}", param_value=value, param_type=9)

    @staticmethod
    def client(messages):
        client = SimpleNamespace(id="uav_01", sysid=1, target_component=1,
                                 condition=threading.Condition(), sequence=0, inbox=[],
                                 check=Mock(), cancel=Mock(), cursor=Mock(return_value=0))
        version = SimpleNamespace(flight_sw_version=(4 << 24) | (5 << 16) | 255,
                                  to_dict=lambda: {"flight_sw_version": (4 << 24) | (5 << 16) | 255})
        client.wait_message = Mock(return_value=version)

        def send(method, *args):
            if method == "param_request_list_send":
                for message in messages:
                    client.sequence += 1
                    client.inbox.append((client.sequence, "PARAM_VALUE", message))

        client.send = Mock(side_effect=send)
        return client

    def test_readback_requires_full_table_and_records_actual_wpnav_values(self):
        client = self.client([self.parameter(2),
                              self.parameter(0, name=b"WPNAV_SPEED\x00", value=500.),
                              self.parameter(0, name="WPNAV_SPEED", value=500.),
                              self.parameter(1, name="WPNAV_ACCEL", value=250.)])
        result = spike.read_firmware_parameters(client, timeout=1)
        self.assertTrue(result["complete"])
        self.assertEqual(result["parameter_count"], 3)
        self.assertEqual(result["received_count"], 3)
        self.assertEqual(result["wpnav"], {"WPNAV_SPEED": 500., "WPNAV_ACCEL": 250.})
        self.assertEqual(result["firmware"]["version_string"], "4.5.0 (type 255)")
        self.assertEqual([call.args[0] for call in client.send.call_args_list],
                         ["command_long_send", "param_request_list_send"])
        self.assertEqual(client.send.call_args_list[0].args[3], 520)

    def test_incomplete_readback_fails_instead_of_claiming_all_wpnav_read(self):
        client = self.client([self.parameter(0, name="WPNAV_SPEED")])
        with self.assertRaisesRegex(TimeoutError, "incomplete parameter readback"):
            spike.read_firmware_parameters(client, timeout=.01)

    def test_invalid_or_inconsistent_parameter_tables_fail_closed(self):
        invalid_tables = [
            [self.parameter(0, count=2, name="WPNAV_SPEED"), self.parameter(1, count=3)],
            [self.parameter(3, count=3, name="WPNAV_SPEED")],
            [self.parameter(0, name="WPNAV_SPEED", value=float("nan"))],
            [self.parameter(0, count=2, name="WPNAV_SPEED"),
             self.parameter(1, count=2, name="WPNAV_SPEED")],
            [self.parameter(0, count=1, name="OTHER_SPEED")],
        ]
        for messages in invalid_tables:
            with self.subTest(messages=messages), self.assertRaises(ValueError):
                spike.read_firmware_parameters(self.client(messages), timeout=.1)

    def test_missing_firmware_does_not_silently_use_an_invented_version(self):
        client = self.client([])
        client.wait_message.side_effect = TimeoutError("no firmware version")
        with self.assertRaisesRegex(TimeoutError, "no firmware version"):
            spike.read_firmware_parameters(client, timeout=.1)
        self.assertEqual([call.args[0] for call in client.send.call_args_list], ["command_long_send"])

    def test_binary_firmware_fallback_is_explicit_and_keeps_provenance(self):
        client = self.client([self.parameter(0, count=1, name="WPNAV_SPEED", value=300.)])
        client.wait_message.side_effect = TimeoutError("old firmware does not report version")
        binary_evidence = dict(version_string="ArduCopter V4.0.4-dev (fixture)",
                               offset=128, sha256="fixture-sha")
        result = spike.read_firmware_parameters(client, timeout=.1, binary_firmware=binary_evidence)
        self.assertFalse(result["firmware"]["autopilot_version_available"])
        self.assertEqual(result["firmware"]["binary_metadata"], binary_evidence)
        self.assertEqual(result["firmware"]["version_string"], binary_evidence["version_string"])
        self.assertEqual(result["wpnav"], {"WPNAV_SPEED": 300.})

    def test_lost_parameter_index_is_requested_without_setting_parameters(self):
        client = self.client([self.parameter(0, name="WPNAV_SPEED"), self.parameter(2)])
        initial_send = client.send.side_effect

        def send(method, *args):
            if method == "param_request_read_send":
                self.assertEqual(args[-1], 1)
                client.sequence += 1
                client.inbox.append((client.sequence, "PARAM_VALUE", self.parameter(1, name="WPNAV_ACCEL")))
            else:
                initial_send(method, *args)

        client.send.side_effect = send
        elapsed = [0.]
        client.cancel.wait.side_effect = lambda _: elapsed.__setitem__(0, elapsed[0] + 6.)
        with patch.object(spike.time, "perf_counter", side_effect=lambda: elapsed[0]):
            result = spike.read_firmware_parameters(client, timeout=30)
        self.assertTrue(result["complete"])
        self.assertEqual([call.args[0] for call in client.send.call_args_list],
                         ["command_long_send", "param_request_list_send", "param_request_read_send"])


class SpikeOwnershipTests(unittest.TestCase):
    def test_failures_keep_evidence_and_close_every_owned_resource(self):
        # These cover independent failure boundaries of a managed flight, with
        # real files but no subprocesses, receiver threads, or network access.
        for failure in ("start", "connect", "prepare_airborne", "upload", "execute", "confirm_target", "land",
                        "client_close", "recorder_close"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                parameters = root / "defaults.parm"
                parameters.write_text("WPNAV_SPEED 300\n", encoding="utf-8")
                (root / "mock.exe").write_bytes(b"mock binary; never executable")
                previous = root / "spike_v04_previous"
                previous.mkdir()
                sentinel = previous / "metadata.json"
                sentinel.write_bytes(b'{"status":"completed","preserve":true}')
                frozen = sentinel.read_bytes()
                instances = [dict(id=f"uav_{i:02d}", sysid=i) for i in range(1, 4)]
                manager = Mock(instances=instances, processes=[Mock(poll=Mock(return_value=0)) for _ in instances])
                manager.start.return_value = instances
                manager.metadata.return_value = {"sha256": "mock-only", "instances": instances}
                if failure == "start":
                    manager.start.side_effect = RuntimeError("injected start failure")
                recorder = Mock(error=None)
                if failure == "recorder_close":
                    recorder.close.side_effect = RuntimeError("injected recorder cleanup failure")
                clients, cancellations = [], []

                def make_vehicle(instance, raw_path, cancel, event, record_lifecycle=False):
                    self.assertTrue(record_lifecycle)
                    self.assertEqual(raw_path.parent.name, "raw")
                    vehicle = Mock(id=instance["id"])
                    if failure != "start":
                        method = "upload" if failure in ("client_close", "recorder_close") else failure
                        getattr(vehicle, method).side_effect = TimeoutError(f"injected {failure} failure")
                    if failure == "client_close" and not clients:
                        vehicle.close.side_effect = RuntimeError("injected client cleanup failure")
                    clients.append(vehicle)
                    cancellations.append(cancel)
                    return vehicle

                readback = dict(parameter_count=1, wpnav={"WPNAV_SPEED": 300.},
                                firmware={"version_string": "mock firmware"})
                with patch.object(spike, "SITLProcesses", return_value=manager), \
                     patch.object(spike, "Vehicle", side_effect=make_vehicle), \
                     patch.object(spike, "Recorder", return_value=recorder) as recorder_class, \
                     patch.object(spike, "read_firmware_parameters", return_value=readback), \
                     patch("builtins.print"):
                    directory, metadata = spike.run_spike(MISSION, root, root / "mock.exe", parameters)
                self.assertEqual(metadata["status"], "failed")
                self.assertIn(f"injected {failure} failure", metadata["error"])
                self.assertEqual(json.loads((directory / "metadata.json").read_text(encoding="utf-8")), metadata)
                self.assertTrue((directory / "spike_plan.json").is_file())
                self.assertEqual(sentinel.read_bytes(), frozen)
                manager.close.assert_called_once()
                for client, cancel in zip(clients, cancellations):
                    client.close.assert_called_once()
                    self.assertTrue(cancel.is_set())
                if recorder_class.called:
                    recorder.close.assert_called_once()
                if failure in ("client_close", "recorder_close"):
                    self.assertTrue(metadata["cleanup_errors"])

    def test_run_budget_rejected_before_launch_or_artifact_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(3):
                directory = root / f"spike_v04_{index}"
                directory.mkdir()
                (directory / "metadata.json").write_text("{}", encoding="utf-8")
            original = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            with patch.object(spike, "SITLProcesses") as manager, self.assertRaisesRegex(ValueError, "maximum of 3"):
                spike.run_spike(MISSION, root, root / "unused.exe", root / "unused.parm")
            manager.assert_not_called()
            self.assertEqual(sorted(str(path.relative_to(root)) for path in root.rglob("*")), original)

    def test_colliding_directory_is_never_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = root / "spike_v04_fixed_stamp_deadbeef"
            directory.mkdir()
            sentinel = directory / "keep.txt"
            sentinel.write_text("do not replace", encoding="utf-8")
            with patch.object(spike, "datetime") as clock, \
                 patch.object(spike.uuid, "uuid4", return_value=SimpleNamespace(hex="deadbeef")), \
                 patch.object(spike, "SITLProcesses") as manager:
                clock.now.return_value.strftime.return_value = "fixed_stamp"
                with self.assertRaises(FileExistsError):
                    spike.run_spike(MISSION, root, root / "unused.exe", root / "unused.parm")
            manager.assert_not_called()
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not replace")


if __name__ == "__main__":
    unittest.main()
