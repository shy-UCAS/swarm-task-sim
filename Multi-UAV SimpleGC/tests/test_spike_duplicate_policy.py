import copy
import unittest

from scripts.spike_duplicate_policy import filter_exact_duplicates


def packet(source, host, kind="GLOBAL_POSITION_INT", **fields):
    return dict(sysid=1, recv_monotonic_s=host,
                message=dict(mavpackettype=kind, time_boot_ms=source, **fields))


class ExactDuplicatePolicyTests(unittest.TestCase):
    def test_keep_first_full_payload_and_audit_window_membership_without_mutation(self):
        rows = [packet(100, 1, lat=30), packet(100, 1.001, lat=30), packet(200, 2, lat=31),
                packet(200, 2.001, lat=31), packet(300, 3, lat=32)]
        before = copy.deepcopy(rows)
        kept, audit = filter_exact_duplicates(rows, flight_window=(1.5, 4), observe_windows=[(2, 2.5)])
        self.assertEqual(kept, [rows[0], rows[2], rows[4]])
        self.assertEqual(rows, before)
        self.assertEqual(audit["dropped_count"], 2)
        self.assertEqual([r["raw_line"] for r in audit["details"]], [2, 4])
        self.assertEqual([r["first_line"] for r in audit["details"]], [1, 3])
        self.assertEqual([r["inside_flight_window"] for r in audit["details"]], [False, True])
        self.assertEqual([r["inside_observe_window"] for r in audit["details"]], [False, True])

    def test_interleaved_kinds_and_other_messages_are_independent(self):
        rows = [packet(100, 1), packet(100, 1.01, "SYSTEM_TIME", time_unix_usec=10),
                packet(100, 1.02, "PARAM_VALUE"), packet(100, 1.03),
                packet(100, 1.04, "SYSTEM_TIME", time_unix_usec=10)]
        kept, audit = filter_exact_duplicates(rows)
        self.assertEqual(kept, rows[:3])
        self.assertEqual(audit["counts"]["GLOBAL_POSITION_INT"]["dropped"], 1)
        self.assertEqual(audit["counts"]["SYSTEM_TIME"]["dropped"], 1)

    def test_conflict_is_retained_and_latches_invalidity(self):
        rows = [packet(100, 1, lat=30), packet(100, 2, lat=31), packet(100, 3, lat=30)]
        kept, audit = filter_exact_duplicates(rows)
        self.assertEqual(kept, rows)
        self.assertEqual(audit["dropped_count"], 0)
        self.assertEqual(audit["counts"]["GLOBAL_POSITION_INT"]["conflicts"], 1)
        self.assertTrue(audit["counts"]["GLOBAL_POSITION_INT"]["timeline_invalid"])

    def test_old_exact_replay_is_rollback_not_duplicate_drop(self):
        rows = [packet(100, 1, lat=30), packet(200, 2, lat=31), packet(100, 3, lat=30)]
        kept, audit = filter_exact_duplicates(rows)
        self.assertEqual(kept, rows)
        self.assertEqual(audit["counts"]["GLOBAL_POSITION_INT"]["rollbacks"], 1)
        self.assertEqual(audit["dropped_count"], 0)

    def test_system_time_unix_field_conflict_is_not_ignored(self):
        rows = [packet(100, 1, "SYSTEM_TIME", time_unix_usec=10),
                packet(100, 2, "SYSTEM_TIME", time_unix_usec=11)]
        _, audit = filter_exact_duplicates(rows)
        self.assertTrue(audit["counts"]["SYSTEM_TIME"]["timeline_invalid"])
        self.assertEqual(audit["counts"]["SYSTEM_TIME"]["conflicts"], 1)

    def test_invalid_or_backwards_receive_time_cannot_be_hidden_by_equality(self):
        for host in (-1, float("nan"), .9):
            rows = [packet(100, 1, lat=30), packet(100, host, lat=30)]
            with self.subTest(host=host):
                kept, audit = filter_exact_duplicates(rows)
                self.assertEqual(len(kept), 2)
                self.assertTrue(audit["counts"]["GLOBAL_POSITION_INT"]["timeline_invalid"])

    def test_nonfinite_payload_and_boolean_source_are_not_duplicates(self):
        for fields in ({"lat": float("nan")}, {"lat": float("inf")}):
            _, audit = filter_exact_duplicates([packet(100, 1, **fields), packet(100, 2, **fields)])
            self.assertEqual(audit["dropped_count"], 0)
            self.assertTrue(audit["counts"]["GLOBAL_POSITION_INT"]["timeline_invalid"])
        _, audit = filter_exact_duplicates([packet(True, 1), packet(True, 2)])
        self.assertEqual(audit["counts"]["GLOBAL_POSITION_INT"]["invalid"], 2)

    def test_type_and_all_message_fields_participate_in_equality(self):
        for alternate in (True, 1.0, 2):
            _, audit = filter_exact_duplicates([packet(100, 1, lat=1), packet(100, 2, lat=alternate)])
            self.assertEqual(audit["counts"]["GLOBAL_POSITION_INT"]["conflicts"], 1)
        _, audit = filter_exact_duplicates([packet(100, 1, lat=1), packet(100, 2, lat=1, extension=0)])
        self.assertEqual(audit["dropped_count"], 0)


if __name__ == "__main__":
    unittest.main()
