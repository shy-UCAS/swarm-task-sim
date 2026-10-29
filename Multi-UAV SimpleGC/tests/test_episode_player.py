"""Offline Qt checks for episode playback and evidence isolation."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PyQt5 import QtCore, QtGui, QtWidgets, QtTest
    from episode_player.window import EpisodePlayer, source
except ImportError:
    EpisodePlayer = None


@unittest.skipIf(EpisodePlayer is None, "optional PyQt5/pyqtgraph dependencies unavailable")
class EpisodePlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        if not QtGui.QFontDatabase().families():
            font = Path("C:/Windows/Fonts/msyh.ttc")
            if font.exists():
                QtGui.QFontDatabase.addApplicationFont(str(font))
        cls.root = source.ROOT / "examples/v05_episodes"

    def setUp(self):
        self.window = EpisodePlayer()
        self.window.show()
        self.addCleanup(self.window.close)

    def wait_read(self):
        deadline = time.monotonic() + 20
        while self.window.reader is not None:
            if time.monotonic() > deadline:
                self.fail("Reader did not finish")
            QtTest.QTest.qWait(10)

    def open_examples(self):
        self.window.open_source(self.root)
        self.wait_read()

    def test_four_examples_play_all_frames_with_no_input_writes(self):
        before = {p: hashlib.sha256(p.read_bytes()).digest() for p in self.root.rglob("*") if p.is_file()}
        self.open_examples()
        self.assertEqual(self.window.list.topLevelItemCount(), 4)
        with patch.object(QtWidgets.QMessageBox, "warning") as warning:
            for row in self.window.rows.values():
                self.window.load_row(row)
                self.wait_read()
                w = self.window
                self.assertTrue(w.play.isEnabled())
                # Traverse every recorded frame through the actual playback clock.
                w.speed.setCurrentIndex(w.speed.findData(20))
                w.set_playing(True)
                anchor, start = w.anchor_clock, w.anchor_t
                for index, stamp in enumerate(w.times):
                    w.tick(anchor + (float(stamp) - start) / 20 + 1e-8)
                    self.assertEqual(w.frame, index)
                    for agent_index, graphic in enumerate(w.graphics.values()):
                        self.assertEqual(graphic["marker"].isVisible(), bool(w.mask[index, agent_index]))
                self.assertFalse(w.playing)
                self.assertEqual(w.frame, len(w.times) - 1)
            warning.assert_not_called()
        after = {p: hashlib.sha256(p.read_bytes()).digest() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_filters_and_controls_work_on_real_episodes(self):
        self.open_examples()
        w = self.window
        w.intent_filter.setCurrentIndex(w.intent_filter.findData("patrol"))
        self.assertEqual(sum(not row.isHidden() for row in w.rows.values()), 2)
        w.family_filter.setCurrentIndex(w.family_filter.findData("scene_6d1987b34d9556dee551"))
        visible = [row for row in w.rows.values() if not row.isHidden()]
        self.assertEqual(len(visible), 1)
        row = visible[0]
        w.list.scrollToItem(row)
        QtTest.QTest.qWait(20)
        rect = w.list.visualItemRect(row)
        QtTest.QTest.mouseClick(w.list.viewport(), QtCore.Qt.LeftButton, pos=rect.center())
        QtTest.QTest.mouseDClick(w.list.viewport(), QtCore.Qt.LeftButton, pos=rect.center())
        self.wait_read()
        self.assertIsNotNone(w.item)
        QtTest.QTest.mouseClick(w.play, QtCore.Qt.LeftButton)
        QtTest.QTest.qWait(140)
        self.assertGreater(w.current_t, w.times[0])
        QtTest.QTest.mouseClick(w.play, QtCore.Qt.LeftButton)
        paused = w.current_t
        QtTest.QTest.qWait(70)
        self.assertEqual(w.current_t, paused)
        w.slider.setValue(25)
        self.assertEqual(w.frame, 25)
        QtTest.QTest.mouseClick(w.next, QtCore.Qt.LeftButton)
        self.assertEqual(w.frame, 26)
        QtTest.QTest.mouseClick(w.previous, QtCore.Qt.LeftButton)
        self.assertEqual(w.frame, 25)
        for speed in (1, 5, 20):
            w.speed.setCurrentIndex(w.speed.findData(speed))
            w.seek(0)
            w.set_playing(True)
            w.tick(w.anchor_clock + 1)
            self.assertAlmostEqual(w.current_t, speed, places=5)
            w.set_playing(False)

    def test_invalid_frame_and_ten_second_tail(self):
        import numpy as np
        n = 122
        data = dict(t_s=[i / 10 for i in range(n)], agent_ids=["uav_01"],
                    x=[[[i, i + 1, 8, 1, 1, 0]] for i in range(n)],
                    mask=[[i != 110] for i in range(n)],
                    targets={"mission_success": False}, metadata={"episode_quality_eligible": False})
        item = dict(path=Path("partial"), data=data, corners=((0, 0), (10, 0), (10, 10), (0, 10)), world={})
        self.window.apply_episode(item)
        w = self.window
        w.seek(11)
        graphic = w.graphics["uav_01"]
        self.assertFalse(graphic["marker"].isVisible())
        self.assertFalse(graphic["label"].isVisible())
        w.seek(12)
        xs, ys = graphic["tail"].getData()
        self.assertEqual(xs[0], 20)  # t=2.0 is exactly ten seconds before t=12.0.
        self.assertEqual(xs[-1], 120)
        self.assertTrue(np.isnan(xs[90]))
        self.assertTrue(graphic["marker"].isVisible())
        self.assertIn("#b22222", w.info.styleSheet())
        self.assertEqual(data["x"][110][0][0], 110)
        self.assertFalse(data["mask"][110][0])

    def test_hash_failure_greys_only_one_row_and_other_episode_still_loads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = source.discover_episodes(self.root)
            for path in paths[:2]:
                shutil.copytree(path, root / path.name)
            damaged = root / paths[0].name
            with (damaged / "observations.csv").open("a", encoding="utf-8") as stream:
                stream.write("\n")
            self.window.open_source(root)
            self.wait_read()
            with patch.object(QtWidgets.QMessageBox, "warning") as warning:
                bad_row = self.window.rows[damaged]
                self.window.load_row(bad_row)
                self.wait_read()
                self.assertIn("episode artifact changed", warning.call_args.args[2])
                self.assertEqual(bad_row.foreground(0).color().name(), "#888888")
                good_row = self.window.rows[root / paths[1].name]
                self.window.load_row(good_row)
                self.wait_read()
                self.assertEqual(self.window.item["path"], root / paths[1].name)
                self.assertTrue(self.window.play.isEnabled())
                self.assertEqual(warning.call_count, 1)


if __name__ == "__main__":
    unittest.main()
