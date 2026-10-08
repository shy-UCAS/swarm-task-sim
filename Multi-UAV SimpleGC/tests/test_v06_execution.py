"""v0.6 endpoint/firmware contracts, using synthetic clients only (no SITL)."""

import copy
import json
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from swarm_sim import runner_v3 as runner
from swarm_sim.quality import resolve_policy
from swarm_sim.run_provenance import read_firmware_parameters, verify_preflight_files
from swarm_sim.tasks import compile_task
from test_run_provenance import InboxClient, baseline_files


ROOT = Path(__file__).resolve().parents[1]


def scene():
    return compile_task(json.loads((ROOT / "missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8")))


class FinalHoldTests(unittest.TestCase):
    def exercise(self, scenario, fail=False):
        clients = [Mock(id=v["id"]) for v in scenario["vehicles"]]
        if fail:
            clients[0].confirm_target.side_effect = TimeoutError("no continuous final position")
        metadata = {"quality_policy": resolve_policy()}
        events = []
        def parallel(function, **kwargs):
            for client, vehicle in zip(clients, scenario["vehicles"]):
                function(client, vehicle)
        def event(kind, **fields):
            events.append(dict(event=kind, **fields))
        call = lambda: runner.execute_final_hold(scenario, clients, parallel, event, metadata,
                                                  time.perf_counter() + 60, lambda: None)
        return clients, metadata, events, call

    def test_final_hold_only_final_endpoint_for_returning_and_nonreturning_tasks(self):
        for returning in (True, False):
            with self.subTest(returning=returning):
                scenario = scene()
                if not returning:
                    scenario["phases"] = scenario["phases"][:-1]
                scenario["task_spec"]["execution"]["final_hold_s"] = 2.0
                original = copy.deepcopy(scenario)
                clients, metadata, events, call = self.exercise(scenario)
                call()
                final = scenario["phases"][-1]
                roles = scenario["semantic_plan"]["execution_phases"][final["name"]]["agents"]
                for client in clients:
                    client.confirm_target.assert_called_once()
                    args = client.confirm_target.call_args.args
                    self.assertEqual(args[0], roles[client.id]["terminal_point"])
                    self.assertEqual(args[3:5], (2.0, final["name"]))
                self.assertEqual(metadata["final_hold"]["status"], "completed")
                self.assertEqual([e["event"] for e in events], ["final_hold_started", "final_hold_complete"])
                self.assertEqual(scenario, original)  # NAV holds and confirmation_dwell_s unchanged.

    def test_v05_absence_does_not_add_a_hold_or_change_evidence(self):
        clients, metadata, events, call = self.exercise(scene())
        before = copy.deepcopy(metadata)
        call()
        for client in clients:
            client.confirm_target.assert_not_called()
        self.assertEqual(metadata, before)
        self.assertEqual(events, [])

    def test_missing_or_truncated_hold_evidence_cannot_complete_final_hold(self):
        scenario = scene()
        scenario["task_spec"]["execution"]["final_hold_s"] = 2.0
        _, metadata, events, call = self.exercise(scenario, fail=True)
        with self.assertRaisesRegex(TimeoutError, "no continuous final position"):
            call()
        self.assertEqual(metadata["final_hold"]["status"], "failed")
        self.assertFalse(any(e["event"] == "final_hold_complete" for e in events))

    def test_column_release_offsets_apply_per_agent_after_common_upload(self):
        scenario = scene()
        phase = scenario["phases"][1]
        scenario["phases"] = [phase]
        phase["start_delays_s"] = {v["id"]: 3.5 * i for i, v in enumerate(scenario["vehicles"])}
        clients, calls = [Mock(id=v["id"]) for v in scenario["vehicles"]], []
        def parallel(function, **kwargs):
            calls.append(kwargs["context"])
            for client, vehicle in zip(clients, scenario["vehicles"]):
                function(client, vehicle)
        metadata = {"quality_policy": resolve_policy()}
        runner.execute_phases(scenario, clients, parallel, Mock(), metadata,
                              time.perf_counter(), time.perf_counter()+100, lambda: None)
        releases = [client.execute.call_args.args[0] for client in clients]
        self.assertEqual([value-releases[0] for value in releases], [0.0, 3.5, 7.0])
        self.assertEqual(calls, [f"phase {phase['name']} {name}" for name in ("upload", "execute", "confirm")])
        self.assertTrue(all(client.confirm_target.call_args.args[3] == .5 for client in clients))


class FirmwareWaitTests(unittest.TestCase):
    def client(self, version=None):
        client = InboxClient([("WPNAV_SPEED", 500)])
        if version is None:
            client.wait_message = Mock(side_effect=TimeoutError("no version message"))
        else:
            client.wait_message = Mock(return_value=SimpleNamespace(flight_sw_version=version,
                to_dict=lambda: dict(mavpackettype="AUTOPILOT_VERSION", flight_sw_version=version)))
        return client

    def test_two_second_timeout_falls_back_and_legacy_default_stays_ten(self):
        for options, expected in (({}, 10), ({"version_timeout_s": 2.0}, 2.0)):
            client = self.client()
            result = read_firmware_parameters(client, {"version_string": "ArduCopter V4.0.4-dev (hash)"}, **options)
            self.assertEqual(client.wait_message.call_args.kwargs["timeout"], expected)
            self.assertTrue(result["complete"])
            self.assertFalse(result["firmware"]["autopilot_version_available"])
            self.assertEqual(result["firmware"]["version_source"], "binary_embedded_ascii_metadata")

    def test_matching_runtime_version_passes_with_two_second_timeout(self):
        client = self.client((4 << 24) + (4 << 8))
        result = read_firmware_parameters(client, {"version_string": "ArduCopter V4.0.4-dev (hash)"}, version_timeout_s=2.0)
        self.assertTrue(result["complete"])
        self.assertTrue(result["firmware"]["autopilot_version_available"])
        self.assertEqual(client.wait_message.call_args.kwargs["timeout"], 2.0)

    def test_runtime_or_embedded_mismatch_rejects_before_parameter_or_flight_commands(self):
        client = self.client((4 << 24) + (5 << 8))
        with self.assertRaisesRegex(ValueError, "AUTOPILOT_VERSION differs"):
            read_firmware_parameters(client, {"version_string": "ArduCopter V4.0.4-dev (hash)"}, version_timeout_s=2.0)
        self.assertEqual([method for method, _ in client.sent], ["command_long_send"])
        with tempfile.TemporaryDirectory() as temp:
            binary, params = baseline_files(temp)
            binary.write_bytes(b"fixture\0ArduCopter V4.0.5-dev (changed)\0end")
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                verify_preflight_files(binary, params, temp)

    def test_runner_forwards_v06_timeout_and_records_end_only_after_successful_hold(self):
        for fail_hold in (False, True):
            with self.subTest(fail_hold=fail_hold), tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
                scenario = scene()
                scenario["task_spec"]["execution"].update(final_hold_s=2.0, firmware_version_timeout_s=2.0)
                # The integration below isolates lifecycle ordering; task normalization
                # and binding are separately tested against the v0.6 profile.
                stack.enter_context(patch.object(runner, "validate", return_value=scenario))
                stack.enter_context(patch.object(runner, "validate_task_binding"))
                process = Mock()
                process.instances = [dict(id=v["id"], sysid=v["sysid"]) for v in scenario["vehicles"]]
                process.processes = [Mock(poll=Mock(return_value=0)) for _ in scenario["vehicles"]]
                process.start.return_value = process.instances
                process.metadata.return_value = {"sha256": "binary"}
                provenance = dict(actual=dict(firmware={"sha256": "binary"}, parameters_sha256="params"), baseline={})
                stack.enter_context(patch.object(runner, "verify_preflight_files", return_value=provenance))
                stack.enter_context(patch.object(runner, "digest", return_value="params"))
                stack.enter_context(patch.object(runner, "SITLProcesses", return_value=process))
                clients = []
                def make_client(instance, *args, **kwargs):
                    client = Mock(id=instance["id"], sysid=instance["sysid"])
                    if fail_hold:
                        client.confirm_target.side_effect = TimeoutError("truncated hold")
                    clients.append(client)
                    return client
                stack.enter_context(patch.object(runner, "Vehicle", side_effect=make_client))
                recorder = stack.enter_context(patch.object(runner, "Recorder"))
                recorder.return_value.error = None
                read = stack.enter_context(patch.object(runner, "read_firmware_parameters", return_value={}))
                stack.enter_context(patch.object(runner, "compare_parameter_readback"))
                stack.enter_context(patch.object(runner, "execute_phases"))
                stack.enter_context(patch("swarm_sim.analysis.analyze_run", side_effect=ValueError("no synthetic raw data")))
                stack.enter_context(patch("builtins.print"))
                _, metadata, _ = runner.run_scene_v3(scenario, temp, "binary", "params")
                self.assertEqual(read.call_count, len(clients))
                self.assertTrue(all(call.kwargs == {"version_timeout_s": 2.0} for call in read.call_args_list))
                if fail_hold:
                    self.assertEqual(metadata["status"], "failed")
                    self.assertNotIn("mission_end_monotonic_s", metadata)
                    for client in clients:
                        client.land.assert_not_called()
                else:
                    self.assertEqual(metadata["status"], "completed")
                    self.assertGreaterEqual(metadata["mission_end_monotonic_s"], metadata["final_hold"]["finished_monotonic_s"])
                    for client in clients:
                        client.land.assert_called_once()


if __name__ == "__main__":
    unittest.main()
