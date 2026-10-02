"""Synthetic timestamp/causality checks; no simulator, ports or production writes."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_spike_timestamps import audit, audit_packets, parameter_alignment, read_packets


def packet(source, value=1, host=100.0, kind="GLOBAL_POSITION_INT"):
    return dict(recv_monotonic_s=host, sysid=1,
                message=dict(mavpackettype=kind, time_boot_ms=source, value=value))


class TimestampAuditTests(unittest.TestCase):
    def test_full_payload_equality_host_receipts_can_differ(self):
        rows = [packet(10), packet(10, host=101), packet(10, value=2, host=102)]
        counts, events = audit_packets(rows, 90)
        self.assertEqual(counts["GLOBAL_POSITION_INT"]["exact_duplicate"], 1)
        self.assertEqual(counts["GLOBAL_POSITION_INT"]["timestamp_conflict"], 1)
        self.assertEqual(events[0]["recv_run_relative_s"], 11)
        self.assertEqual(events[0]["previous_same_source_line"], 1)

    def test_interleaving_types_does_not_hide_duplicates(self):
        counts, _ = audit_packets([packet(10), packet(11, kind="ATTITUDE"), packet(10)])
        self.assertEqual(counts["GLOBAL_POSITION_INT"]["exact_duplicate"], 1)

    def test_old_exact_payload_reappearing_is_rollback(self):
        counts, events = audit_packets([packet(10), packet(20), packet(10), packet(15)])
        self.assertEqual(counts["GLOBAL_POSITION_INT"]["rollback"], 2)
        self.assertEqual(counts["GLOBAL_POSITION_INT"]["exact_duplicate"], 0)
        self.assertTrue(events[0]["previous_same_source_payload_equal"])

    def test_source_host_and_invalid_are_separate(self):
        counts, _ = audit_packets([packet(0, host=102), packet(None, host=103),
                                  packet(True, host=104), packet(1, host=101)])
        row = counts["GLOBAL_POSITION_INT"]
        self.assertEqual(row["advancing"], 2)
        self.assertEqual(row["invalid_source_timestamp"], 2)
        self.assertEqual(row["rollback"], 0)
        self.assertEqual(row["host_rollback"], 1)

    def test_conflict_does_not_replace_first_payload(self):
        counts, _ = audit_packets([packet(10), packet(10, 2), packet(10)])
        row = counts["GLOBAL_POSITION_INT"]
        self.assertEqual((row["advancing"], row["timestamp_conflict"], row["exact_duplicate"]), (1, 1, 1))

    def test_unix_zero_is_unavailable_not_boot_invalid(self):
        rows = [packet(10, kind="SYSTEM_TIME"), packet(20, kind="SYSTEM_TIME")]
        rows[0]["message"]["time_unix_usec"] = 0
        rows[1]["message"]["time_unix_usec"] = 1000
        counts, _ = audit_packets(rows)
        self.assertEqual(counts["SYSTEM_TIME"]["zero_unix_time"], 1)
        self.assertEqual(counts["SYSTEM_TIME"]["invalid_source_timestamp"], 0)

    def test_missing_stream_is_counted_as_absent_not_valid(self):
        counts, _ = audit_packets([])
        self.assertEqual(counts["SYSTEM_TIME"]["total"], 0)

    def test_parameter_send_times_remain_unrecorded(self):
        events = [dict(event="connected", t=2, agent_id="a"),
                  dict(event="firmware_parameters_read", t=13, agent_id="a")]
        result = parameter_alignment([], events, dict(run_epoch_monotonic_s=100), "a", [], True)
        self.assertIsNone(result["request_send_times_s"])
        self.assertTrue(result["missing_index_retry_excluded_by_5s_control_flow"])
        uncertain = parameter_alignment([], events, dict(run_epoch_monotonic_s=100), "a", [], False)
        self.assertFalse(uncertain["missing_index_retry_excluded_by_5s_control_flow"])

    def test_malformed_raw_record_fails_with_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.jsonl"
            path.write_text(json.dumps(packet(1)) + "\nnot json\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r":2: invalid raw record"):
                list(read_packets(path))

    def test_output_refuses_overwrite_and_non_tmp_location(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            output = project / "tmp_v04" / "review"
            output.mkdir(parents=True)
            marker = output / "keep.txt"
            marker.write_text("original")
            with self.assertRaises(FileExistsError):
                audit(project, output)
            self.assertEqual(marker.read_text(), "original")
            with self.assertRaisesRegex(ValueError, "under this project's tmp_v04"):
                audit(project, project / "runs")


if __name__ == "__main__":
    unittest.main()
