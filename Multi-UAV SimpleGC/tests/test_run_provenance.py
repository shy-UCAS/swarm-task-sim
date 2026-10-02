"""Read-only preflight contracts exercised without a socket or SITL process."""

import copy
import json
import tempfile
import threading
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace

from swarm_sim.recording import write_json
from swarm_sim.run_provenance import (binary_identity, compare_parameter_readback, digest,
                                     read_firmware_parameters, verify_preflight_files)


def baseline_files(root):
    root = Path(root)
    (root / "docs").mkdir()
    binary, template = root / "copter.exe", root / "copter.parm"
    binary.write_bytes(b"fixture\0ArduCopter V4.0.4-dev (test)\0end")
    template.write_text("WPNAV_SPEED 500\n", encoding="utf-8")
    firmware = binary_identity(binary)
    reports = []
    for index in range(2):
        run = root / f"run{index}"
        run.mkdir()
        write_json(run / "metadata.json", dict(binary_firmware=firmware, parameters_sha256=digest(template)))
        write_json(run / "firmware_parameters.json", dict(uav_01=dict(complete=True,
            all_parameters={"WPNAV_SPEED": 500.0, "SYSID_THISMAV": 1.0, "SIM_PLD_LAT": 30.0,
                            "STAT_RESET": 339262368.0, "STAT_BOOTCNT": 1., "STAT_FLTTIME": 0., "STAT_RUNTIME": 0.})))
        write_json(run / "spike_metrics.json", dict(source_sha256={name: digest(run / name)
            for name in ("metadata.json", "firmware_parameters.json")}))
        reports.append(dict(path=f"run{index}/spike_metrics.json", sha256=digest(run / "spike_metrics.json")))
    document = root / "docs/report.md"
    document.write_text("confirmed review", encoding="utf-8")
    write_json(root / "docs/v04_spike_go_confirmation.json", dict(milestone="WP-S", decision="GO",
        accepted_duplicate_policy="exact_duplicate_drop_v1", original_unknown_reports=reports,
        evidence=[dict(path="docs/report.md", sha256=digest(document))]))
    return binary, template


class InboxClient:
    def __init__(self, rows, first_indices=None, send_error=False, drop_missing=False):
        self.id, self.sysid, self.target_component = "uav_01", 1, 1
        self.condition, self.cancel = threading.Condition(), threading.Event()
        self.inbox, self.sequence = deque(), 0
        self.rows, self.first_indices = rows, first_indices
        self.send_error, self.drop_missing = send_error, drop_missing
        self.events, self.sent = [], []

    def cursor(self): return self.sequence
    def check(self): pass
    def wait_message(self, *args, **kwargs): raise TimeoutError("firmware lacks AUTOPILOT_VERSION")
    def event(self, *args, **kwargs): self.events.append((args, kwargs))

    def publish(self, index):
        name, value = self.rows[index]
        message = SimpleNamespace(param_count=len(self.rows), param_index=index,
                                  param_id=name, param_value=value, param_type=9)
        self.sequence += 1
        self.inbox.append((self.sequence, "PARAM_VALUE", message))

    def send(self, method, *args):
        self.sent.append((method, args))
        if method == "param_request_list_send":
            if self.send_error: raise OSError("send disconnected")
            for index in (range(len(self.rows)) if self.first_indices is None else self.first_indices):
                self.publish(index)
        elif method == "param_request_read_send" and not self.drop_missing:
            self.publish(args[-1])


class ProvenanceTests(unittest.TestCase):
    def test_confirmed_fingerprint_and_hash_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary, template = baseline_files(root)
            result = verify_preflight_files(binary, template, root)
            self.assertEqual(result["status"], "files_verified")
            for path in (binary, template, root / "docs/report.md", root / "run0/metadata.json",
                         root / "run1/firmware_parameters.json", root / "run1/spike_metrics.json"):
                before = path.read_bytes()
                path.write_bytes(before + b" changed")
                with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, "WP-S"):
                    verify_preflight_files(binary, template, root)
                path.write_bytes(before)

    def test_real_accepted_fingerprint_is_read_only_verifiable(self):
        root = Path(__file__).resolve().parents[1]
        result = verify_preflight_files(root / "ArducopterSITL/arducopter.exe", root / "ArducopterSITL/copter.parm", root)
        self.assertEqual(result["actual"]["firmware"]["version_string"], "ArduCopter V4.0.4-dev (de791682)")
        self.assertEqual(len(result["baseline"]["baselines"]), 2)

    def test_complete_table_uses_single_inbox_and_logs_first_tx_bounds(self):
        client = InboxClient([("SYSID_THISMAV", 1), ("WPNAV_SPEED", 500)])
        result = read_firmware_parameters(client, dict(version_string="binary version"), timeout=.2)
        self.assertTrue(result["complete"])
        self.assertEqual(result["missing_indices"], [])
        self.assertFalse(result["firmware"]["autopilot_version_available"])
        self.assertEqual(result["firmware"]["version_source"], "binary_embedded_ascii_metadata")
        parameter_tx = result["requests"][1]
        self.assertEqual(parameter_tx["request_type"], "PARAM_REQUEST_LIST")
        self.assertEqual(parameter_tx["purpose"], "first")
        self.assertIsNone(parameter_tx["missing_index"])
        self.assertEqual((parameter_tx["target_sysid"], parameter_tx["target_component"]), (1, 1))
        self.assertLessEqual(parameter_tx["send_before_monotonic_s"], parameter_tx["send_after_monotonic_s"])
        self.assertTrue(parameter_tx["success"])
        self.assertEqual(len(client.inbox), 2)  # consumers never drain or receive directly
        self.assertFalse(any("set" in name for name, _ in client.sent))

    def test_missing_index_read_tx_links_exact_requested_index(self):
        client = InboxClient([("SYSID_THISMAV", 1), ("WPNAV_SPEED", 500), ("TEST", 0)], first_indices=[0, 1])
        result = read_firmware_parameters(client, dict(version_string="binary version"), timeout=.3, retry_interval_s=.001)
        reads = [entry for entry in result["requests"] if entry["request_type"] == "PARAM_REQUEST_READ"]
        self.assertEqual([entry["missing_index"] for entry in reads], [2])
        self.assertEqual(reads[0]["purpose"], "missing_read")
        self.assertTrue(result["complete"])
        self.assertEqual(len({r["correlation_id"] for r in result["requests"]}), len(result["requests"]))

    def test_send_failure_and_timeout_retain_partial_evidence(self):
        for fail_send in (True, False):
            client = InboxClient([("SYSID_THISMAV", 1), ("WPNAV_SPEED", 500)], first_indices=[0],
                                 send_error=fail_send, drop_missing=True)
            evidence = {}
            with self.subTest(send_error=fail_send), self.assertRaises((OSError, TimeoutError)):
                read_firmware_parameters(client, dict(version_string="binary version"), evidence, timeout=.07, retry_interval_s=.001)
            self.assertFalse(evidence["complete"])
            self.assertEqual(evidence["status"], "failed")
            self.assertIn("finished_monotonic_s", evidence)
            if fail_send:
                self.assertFalse(evidence["requests"][-1]["success"])
                self.assertIn("OSError", evidence["requests"][-1]["error"])
            else:
                self.assertTrue(evidence["timed_out"])
                self.assertEqual(evidence["missing_indices"], [1])
                self.assertEqual(evidence["received_count"], 1)

    def test_list_retry_is_explicit_and_unknown_count_is_not_zero(self):
        client = InboxClient([("WPNAV_SPEED", 500)], first_indices=[], drop_missing=True)
        evidence = {}
        with self.assertRaises(TimeoutError):
            read_firmware_parameters(client, dict(version_string="binary version"), evidence, timeout=.07, retry_interval_s=.001)
        self.assertIsNone(evidence["parameter_count"])
        self.assertIsNone(evidence["missing_indices"])
        self.assertEqual([r["purpose"] for r in evidence["requests"]], ["autopilot_version", "first", "retry"])

    def test_parameter_differences_are_explained_or_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary, template = baseline_files(tmp)
            baseline = verify_preflight_files(binary, template, tmp)["baseline"]
            evidence = dict(complete=True, parameter_count=7, received_count=7,
                all_parameters={"WPNAV_SPEED": 500., "SYSID_THISMAV": 6., "SIM_PLD_LAT": 31.,
                                "STAT_RESET": 339262368.0, "STAT_BOOTCNT": 1., "STAT_FLTTIME": 0., "STAT_RUNTIME": 0.})
            compare_parameter_readback(evidence, baseline, 6, run_started_utc="2026-10-01T15:32:48+00:00")
            self.assertTrue(evidence["parameter_comparison"]["pass"])
            self.assertEqual({r["name"] for r in evidence["parameter_comparison"]["changes"]}, {"SYSID_THISMAV", "SIM_PLD_LAT"})
            evidence["all_parameters"]["WPNAV_SPEED"] = 600
            with self.assertRaisesRegex(ValueError, "WPNAV_SPEED"):
                compare_parameter_readback(evidence, baseline, 6, run_started_utc="2026-10-01T15:32:48+00:00")
            self.assertFalse(evidence["parameter_comparison"]["pass"])

    def test_conflicting_parameter_values_cannot_be_silently_overwritten(self):
        client = InboxClient([("SYSID_THISMAV", 1), ("WPNAV_SPEED", 500)])
        original_send = client.send
        def send(method, *args):
            original_send(method, *args)
            if method == "param_request_list_send":
                client.rows[1] = ("WPNAV_SPEED", 600)
                client.publish(1)
        client.send = send
        evidence = {}
        with self.assertRaisesRegex(ValueError, "conflicting"):
            read_firmware_parameters(client, dict(version_string="binary version"), evidence, timeout=.2)
        self.assertFalse(evidence["complete"])

    def test_runtime_version_mismatch_refuses_readback_and_records_both_sources(self):
        client = InboxClient([("WPNAV_SPEED", 500)])
        number = (4 << 24) + (1 << 8)
        client.wait_message = lambda *a, **k: SimpleNamespace(flight_sw_version=number,
            to_dict=lambda: dict(mavpackettype="AUTOPILOT_VERSION", flight_sw_version=number))
        evidence = {}
        with self.assertRaisesRegex(ValueError, "AUTOPILOT_VERSION differs"):
            read_firmware_parameters(client, dict(version_string="ArduCopter V4.0.4-dev (hash)"), evidence)
        self.assertTrue(evidence["firmware"]["autopilot_version_available"])
        self.assertEqual(evidence["firmware"]["runtime_version_source"], "AUTOPILOT_VERSION")
        self.assertFalse(any(method == "param_request_list_send" for method, _ in client.sent))
