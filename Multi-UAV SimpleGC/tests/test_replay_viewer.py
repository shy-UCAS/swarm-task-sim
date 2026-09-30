"""Replay evidence boundaries and optional Qt playback interaction tests."""
import csv
import json
import math
import os
import tempfile
import unittest
from pathlib import Path

from replay_viewer.data import Sample, Track, load_replay

ROOT = Path(__file__).resolve().parents[1]


class ReplayFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scene = load_replay(ROOT / "missions/recon_smoke_3uav.json").scene
        self.write("scenario.json", self.scene)
        self.write("metadata.json", dict(scenario=self.scene, status="completed", elapsed_s=4))

    def write(self, name, data):
        (self.root / name).write_text(json.dumps(data), encoding="utf-8")

    def samples(self, rows):
        with (self.root / "samples.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["t", "agent_id", "valid_position", "east_m", "north_m", "up_m"])
            writer.writerows(rows)


class ReplayDataTests(ReplayFixture):
    def test_invalid_and_stale_samples_do_not_reuse_or_interpolate_position(self):
        self.samples([[0, "uav_01", 1, 1, 2, 3], [.1, "uav_01", 0, 8, 8, 8],
                      [.2, "uav_01", 1, "nan", 3, 4], [2, "uav_01", 1, 5, 6, 7]])
        d = load_replay(self.root)
        track = d.tracks["uav_01"]
        self.assertEqual(track.at(.05, .5).xyz, (1, 2, 3))
        for t in (.1, .15, .2, 1, 2.6):
            self.assertIsNone(track.at(t, .5))
        self.assertEqual(track.at(2, .5).xyz, (5, 6, 7))
        self.assertTrue(d.warnings)

    def test_plot_breaks_long_gap_even_when_endpoints_are_valid(self):
        track = Track([Sample(0, True, (1, 2, 3), None, "", ""),
                       Sample(2, True, (4, 5, 6), None, "", "")], [0, 2])
        times, x, _, _ = track.plot_points(.5)
        self.assertEqual(times, [0, 0, 2])
        self.assertTrue(math.isnan(x[1]))

    def test_duplicate_reversed_and_unknown_agent_rejected(self):
        for last in ([0, "uav_01", 1, 2, 3, 4], [-1, "uav_01", 1, 2, 3, 4],
                     [1, "uav_999", 1, 2, 3, 4]):
            self.samples([[0, "uav_01", 1, 1, 2, 3], last])
            with self.assertRaises(ValueError):
                load_replay(self.root)

    def test_host_run_time_is_preserved_with_missing_initial_data(self):
        self.samples([[2, "uav_01", 1, 1, 2, 3]])
        (self.root / "events.jsonl").write_text(json.dumps(dict(t=2.5, event="phase_start_sent")) + "\n", encoding="utf-8")
        d = load_replay(self.root)
        self.assertEqual(d.duration, 4)
        self.assertEqual(d.mission_start, 2.5)
        self.assertIsNone(d.tracks["uav_01"].at(0, .5))
        self.assertEqual(d.tracks["uav_01"].times, [2])

    def test_running_or_conflicting_scene_rejected(self):
        self.write("metadata.json", dict(scenario=self.scene, status="running"))
        with self.assertRaises(ValueError):
            load_replay(self.root)
        self.write("metadata.json", dict(scenario={}, status="failed"))
        with self.assertRaises(ValueError):
            load_replay(self.root)

    def test_failed_run_without_samples_retains_plan_and_error(self):
        self.write("metadata.json", dict(scenario=self.scene, status="failed", error="startup failure"))
        d = load_replay(self.root)
        self.assertTrue(d.is_run)
        self.assertEqual(d.metadata["error"], "startup failure")
        self.assertTrue(d.warnings)
        self.assertEqual(d.duration, 0)

    def test_escaping_analysis_path_is_not_read(self):
        self.write("analysis_latest.json", dict(directory="../outside"))
        d = load_replay(self.root)
        self.assertFalse(d.analysis_name)
        self.assertTrue(any("分析路径" in warning for warning in d.warnings))

    def test_loading_never_changes_evidence(self):
        self.samples([[0, "uav_01", 1, 1, 2, 3]])
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        load_replay(self.root)
        after = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.assertEqual(before, after)

    def test_malformed_optional_report_does_not_break_trajectory_loading(self):
        self.samples([[0, "uav_01", 1, 1, 2, 3]])
        (self.root / "analysis").mkdir()
        self.write("analysis_latest.json", dict(directory="analysis"))
        self.write("analysis/quality.json", [])
        self.write("analysis/labels.json", {})
        d = load_replay(self.root)
        self.assertFalse(d.analysis_name)
        self.assertEqual(d.tracks["uav_01"].at(0, .5).xyz, (1, 2, 3))
        self.assertTrue(any("JSON 对象" in warning for warning in d.warnings))


try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5 import QtCore, QtWidgets, QtTest
    from replay_viewer.window import ReplayWindow
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE, "Optional PyQt5/pyqtgraph not installed")
class ReplayGuiTests(ReplayFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_playback_controls_visibility_and_plan_switch(self):
        self.samples([[0, "uav_01", 1, 1, 2, 3], [.1, "uav_01", 1, 2, 3, 4],
                      [3, "uav_01", 1, 5, 6, 7]])
        w = ReplayWindow()
        self.addCleanup(w.close)
        w.apply_data(load_replay(self.root))
        self.assertTrue(w.play.isEnabled())
        QtTest.QTest.mouseClick(w.play, QtCore.Qt.LeftButton)
        QtTest.QTest.qWait(100)
        self.assertGreater(w.current_t, 0)
        QtTest.QTest.mouseClick(w.play, QtCore.Qt.LeftButton)
        paused = w.current_t
        QtTest.QTest.qWait(60)
        self.assertEqual(w.current_t, paused)
        w.slider.setValue(7500)
        self.assertEqual(w.current_t, 3)
        self.assertTrue(w.graphics["uav_01"]["marker"].isVisible())
        w.seek(2)
        self.assertFalse(w.graphics["uav_01"]["marker"].isVisible())
        w.seek(3)
        w.agent_list.item(0).setCheckState(QtCore.Qt.Unchecked)
        self.assertFalse(w.graphics["uav_01"]["marker"].isVisible())
        self.assertFalse(w.graphics["uav_01"]["altitude"].isVisible())
        w.set_playing(True)
        w.seek(4)
        self.assertFalse(w.playing)
        w.seek(0)
        w.speed.setCurrentIndex(w.speed.findData(2))
        w.set_playing(True)
        w.last_tick -= .5
        w.tick()
        self.assertAlmostEqual(w.current_t, 1, delta=.05)
        w.set_playing(False)
        w.apply_data(load_replay(ROOT / "missions/recon_smoke_3uav.json"))
        self.assertFalse(w.play.isEnabled())
        self.assertFalse(w.graphics["uav_01"]["marker"].isVisible())
        self.assertEqual(w.event_list.count(), 0)


if __name__ == "__main__":
    unittest.main()
