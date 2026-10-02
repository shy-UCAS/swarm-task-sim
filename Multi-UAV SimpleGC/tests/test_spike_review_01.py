"""Offline integration checks; no simulator or external service is used."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_spike_route_metrics as fixtures
from scripts import spike_review_01 as review


class SpikeReviewTests(unittest.TestCase):
    def channels(self, root, change):
        scene = fixtures.SpikeMetricsTests()._write_fixture(root)
        metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
        raw = root / "raw/a.jsonl"
        packets = review.legacy._lines(raw)
        change(packets)
        raw.write_text("\n".join(json.dumps(p) for p in packets), encoding="utf-8")
        before = review.digest(raw)
        with patch("scripts.spike_review_01.read_truth", return_value=([], {}, dict(available=False))):
            channels, audits = review.read_review_channels(root, scene, metadata, [])
        self.assertEqual(review.digest(raw), before)
        return channels, audits

    def test_duplicate_recovers_fcu_without_changing_raw(self):
        def duplicate(rows):
            rows.insert(2, json.loads(json.dumps(rows[1])))
        with tempfile.TemporaryDirectory() as tmp:
            channels, audits = self.channels(Path(tmp), duplicate)
        observed, _, clocks, provenance, _, _, _ = channels
        self.assertEqual(audits["a"]["dropped_count"], 1)
        self.assertIsNone(provenance["a"]["observation_timeline_error"])
        self.assertTrue(clocks["a"]["available"])
        self.assertTrue(any(value is not None for _, value in observed["a"]))

    def test_conflicting_system_time_disables_clock(self):
        def conflict(rows):
            copy = json.loads(json.dumps(rows[0]))
            copy["message"]["time_unix_usec"] = 123
            rows.insert(1, copy)
        with tempfile.TemporaryDirectory() as tmp:
            channels, audits = self.channels(Path(tmp), conflict)
        self.assertFalse(channels[2]["a"]["available"])
        self.assertEqual(audits["a"]["counts"]["SYSTEM_TIME"]["conflicts"], 1)
        self.assertEqual(audits["a"]["dropped_count"], 0)
        self.assertIn("a: invalid SYSTEM_TIME timeline", channels[5])

    def test_conflict_outside_flight_still_invalidates_whole_fcu(self):
        def conflict(rows):
            copy = json.loads(json.dumps(rows[1]))
            copy["message"]["vx"] = 1
            rows.insert(2, copy)
        with tempfile.TemporaryDirectory() as tmp:
            channels, audits = self.channels(Path(tmp), conflict)
        self.assertTrue(channels[3]["a"]["observation_timeline_error"])
        self.assertFalse(any(value is not None for _, value in channels[0]["a"]))
        self.assertIs(audits["a"]["details"][0]["inside_flight_window"], False)

    def test_destination_guard_preserves_existing_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            root = project / "tmp_v04/review"
            (root / "inputs").mkdir(parents=True)
            marker = root / "inputs/keep.txt"
            marker.write_text("original", encoding="utf-8")
            with patch.object(review, "PROJECT", project):
                with self.assertRaises(ValueError):
                    review.run_review(project / "outside")
                with self.assertRaises(FileExistsError):
                    review.run_review(root)
            self.assertEqual(marker.read_text(encoding="utf-8"), "original")


if __name__ == "__main__":
    unittest.main()
