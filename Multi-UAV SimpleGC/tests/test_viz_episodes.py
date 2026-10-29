"""Plot contract checks; optional matplotlib, no SITL or archive dependency."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import viz_episodes as viz

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    plt = None


@unittest.skipIf(plt is None, "optional matplotlib is unavailable")
class EpisodePlotTests(unittest.TestCase):
    def test_masked_zero_fill_never_becomes_a_point_or_bridges_a_gap(self):
        data = dict(x=[[[10, 20, 0, 0, 0, 0]], [[0] * 6], [[30, 40, 0, 0, 0, 0]]],
                    mask=[[True], [False], [True]], agent_ids=["uav_01"],
                    targets={}, metadata={})
        original = copy.deepcopy(data)
        item = dict(data=data, corners=((5, 5), (50, 5), (50, 50), (5, 50)),
                    world={}, restricted_regions=[])
        figure, ax = plt.subplots()
        self.addCleanup(plt.close, figure)
        viz.plot_episode(ax, item, {"uav_01": "blue"})
        line = next(line for line in ax.lines if line.get_label() == "uav_01")
        segments = list(line.get_path().iter_segments(remove_nans=True))
        # A new MOVETO is required after the missing sample; no connecting LINETO.
        self.assertEqual([code for points, code in segments], [1, 1])
        self.assertEqual([tuple(points) for points, code in segments], [(10, 20), (30, 40)])
        self.assertEqual(data, original)
        self.assertEqual(ax.get_aspect(), 1)

    def test_four_examples_and_family_render_without_changing_source(self):
        paths = viz.discover_episodes(viz.ROOT / "examples/v05_episodes")
        self.assertEqual(len(paths), 4)
        files = [f for p in paths for f in p.iterdir() if f.is_file()]
        before = {p: hashlib.sha256(p.read_bytes()).digest() for p in files}
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            items = [viz.load_plot_episode(p) for p in paths]
            for item in items:
                self.assertIsNone(item["data"]["metadata"]["flight_pattern"])
                self.assertIn("plan=—", viz.title(item))
                viz.render([item], out / f"{item['path'].name}.png", "Example")
            members = [item for item in items if item["data"]["metadata"]["family_id"] == "scene_6d1987b34d9556dee551"]
            self.assertEqual(len(members), 2)
            with patch.object(plt, "close") as close:
                viz.render(members, out / "family.png", "Family")
                figure = close.call_args.args[0]
                self.assertEqual(figure.axes[0].get_xlim(), figure.axes[1].get_xlim())
                self.assertEqual(figure.axes[0].get_ylim(), figure.axes[1].get_ylim())
                self.assertTrue(all(ax.get_aspect() == 1 for ax in figure.axes))
            plt.close(figure)
            self.assertEqual(len(list(out.glob("*.png"))), 5)
            self.assertTrue(all(p.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for p in out.glob("*.png")))
            with self.assertRaises(FileExistsError):
                viz.render(members, out / "family.png", "Family")
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).digest() for p in files})

    def test_output_cannot_point_to_source_or_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "dataset"
            with patch.object(viz, "VIZ_ROOT", base / "SwarmData/viz"):
                with self.assertRaises(ValueError):
                    viz.check_output(source, source / "pictures")
                good = base / "SwarmData/viz/examples"
                self.assertEqual(viz.check_output(source, good), good.resolve())
                with self.assertRaises(ValueError):
                    viz.check_output(good, good / "pictures")
                with self.assertRaises(ValueError):
                    viz.check_output(source, viz.ROOT / "pictures")


if __name__ == "__main__":
    unittest.main()
