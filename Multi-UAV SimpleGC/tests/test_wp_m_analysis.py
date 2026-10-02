"""WP-M analysis routing keeps v0.4 artifacts frozen and versions v0.5 evidence."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from swarm_sim.analysis import analyze_run
from swarm_sim.recording import write_json
from swarm_sim.tasks import compile_task


ROOT = Path(__file__).resolve().parents[1]


class AnalysisRouteEvidenceTests(unittest.TestCase):
    def _analyze_failed(self, root, spec):
        scene = compile_task(spec)
        run = root / spec["task_id"]
        run.mkdir()
        write_json(run / "scenario.json", scene)
        write_json(run / "metadata.json", dict(version="0.5.0-dev", run_id=spec["task_id"],
                scenario=scene, status="failed", run_epoch_monotonic_s=100., elapsed_s=.1))
        (run / "events.jsonl").write_text("", encoding="utf-8")
        output, quality, labels = analyze_run(run)
        return output, quality, labels

    def test_v05_optional_timing_field_selects_versioned_evidence_only_for_new_task(self):
        old = json.loads((ROOT / "missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8"))
        new = copy.deepcopy(old)
        new["task_id"] += "_v05_analysis"
        new["execution"]["async_timing_tolerance"]["max_s"] = 30.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_output, old_quality, old_labels = self._analyze_failed(root, old)
            new_output, new_quality, new_labels = self._analyze_failed(root, new)
            old_metrics = json.loads((old_output / "execution_metrics.json").read_text(encoding="utf-8"))
            new_metrics = json.loads((new_output / "execution_metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(old_metrics["version"], "execution_artifacts_v1")
            self.assertEqual(new_metrics["version"], "execution_artifacts_v2")
            self.assertFalse((old_output / "ac4_timing_v3.json").exists())
            self.assertTrue((new_output / "ac4_timing_v3.json").exists())
            self.assertNotIn("route_progress_version", old_quality)
            self.assertNotIn("route_progress_version", old_labels["label_provenance"])
            report = json.loads((new_output / "ac4_timing_v3.json").read_text(encoding="utf-8"))
            manifest = json.loads((new_output / "manifest.json").read_text(encoding="utf-8"))
            for artifact in (new_quality, new_labels["label_provenance"], report, manifest):
                self.assertEqual(artifact["route_progress_version"], "ordered_route_progress_v1")
                self.assertEqual(artifact["ac4_timing_version"], "ac4_relative_progress_timing_v3")
                self.assertEqual(artifact["execution_artifacts_version"], "execution_artifacts_v2")
            self.assertIsNone(report["channels"]["truth"]["within_tau"])
            self.assertIsNone(report["channels"]["observation"]["within_tau"])

    def test_v05_integer_hold_in_barrier_mode_has_no_route_only_ac4_attachment(self):
        task = json.loads((ROOT / "missions/v3/recon_shared_3uav_barrier.json").read_text(encoding="utf-8"))
        task["task_id"] += "_v05_integer_hold"
        task["execution"]["waypoint_hold_s"] = 0.
        task["execution"]["hold_semantics"] = "integer_seconds_v1"
        with tempfile.TemporaryDirectory() as temp:
            output, quality, _ = self._analyze_failed(Path(temp), task)
            self.assertFalse((output / "ac4_timing_v3.json").exists())
            metrics = json.loads((output / "execution_metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["version"], "execution_artifacts_v1")
            self.assertEqual(quality["semantic_validation_version"], "multi_intent_validation_v2")
            self.assertEqual(quality["execution_constraints_version"], "multi_intent_execution_limits_v2")


if __name__ == "__main__":
    unittest.main()
