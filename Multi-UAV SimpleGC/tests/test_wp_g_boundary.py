import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swarm_sim.analysis import analyze_run
from swarm_sim.runner import run_scene
from swarm_sim.tasks import compile_task

ROOT = Path(__file__).resolve().parents[1]


class WPGPauseBoundaryTests(unittest.TestCase):
    def test_v3_cannot_launch_with_firmware_outside_confirmed_wp_s(self):
        for mode in ("barrier", "route"):
            scene = compile_task(json.loads((ROOT / f"missions/v3/recon_shared_3uav_{mode}.json").read_text(encoding="utf-8")))
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp, \
                    patch("swarm_sim.runner_v3.verify_preflight_files", side_effect=ValueError("changed firmware requires a new WP-S GO")), \
                    patch("swarm_sim.runner_v3.SITLProcesses") as process, patch("builtins.print"):
                root = Path(tmp)
                directory, metadata, quality = run_scene(scene, root / "runs", root / "binary", root / "params")
                process.assert_not_called()
                self.assertEqual(metadata["status"], "failed")
                self.assertIn("WP-S GO", metadata["error"])
                self.assertFalse(quality["episode_quality_eligible"])
                self.assertTrue((directory / "metadata.json").exists())
                self.assertNotIn("analysis_error", quality)

    def test_v3_analysis_dispatches_to_its_versioned_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"metadata.json").write_text(json.dumps(dict(scenario=dict(task_spec=dict(schema_version=3)))),encoding="utf-8")
            with patch("swarm_sim.analysis_v3.analyze_run_v3", return_value="v3 result") as analyze:
                self.assertEqual(analyze_run(root), "v3 result")
                analyze.assert_called_once()
