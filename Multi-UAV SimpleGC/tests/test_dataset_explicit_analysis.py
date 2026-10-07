"""Explicit external analysis selection binds source runs without pointer edits."""

import json
import tempfile
import unittest
from pathlib import Path

from swarm_sim.analysis import digest
from swarm_sim.analysis_v3 import analyze_run_v3
from swarm_sim.dataset import build_dataset
from test_wp_p_protocol import _analyzed_failed_run


def _selection(run, analysis):
    return {str(run.resolve()): dict(directory=str(analysis.resolve()),
                                    manifest_sha256=digest(analysis / "manifest.json"))}


class ExplicitAnalysisTests(unittest.TestCase):
    def test_external_new_protocol_export_preserves_original_latest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run, old = _analyzed_failed_run(root / "run", v05=True)
            before = (run / "analysis_latest.json").read_bytes()
            analysis, _, _ = analyze_run_v3(run, patrol_validator_version="perimeter_revisit_v2",
                progress_mapping_version="ordered_route_progress_v2", output_directory=root / "external", update_latest=False)
            result = build_dataset([run], root / "dataset", analysis_selections=_selection(run, analysis))
            self.assertEqual((run / "analysis_latest.json").read_bytes(), before)
            self.assertEqual(json.loads(before)["directory"], old.name)
            self.assertEqual(result["semantic_protocol"]["semantic_validation_version"], "multi_intent_validation_v3")
            entry = result["episodes"][0]
            self.assertEqual(entry["source_analysis_path"], str(analysis))
            self.assertEqual(entry["analysis_selection_mode"], "explicit_manifest_binding")

    def test_wrong_run_binding_unknown_key_manifest_and_source_hash_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left, analysis = _analyzed_failed_run(root / "left", v05=True)
            right, _ = _analyzed_failed_run(root / "right", v05=True)
            with self.assertRaisesRegex(ValueError, "different source run"):
                build_dataset([right], root / "wrong_binding", analysis_selections=_selection(right, analysis))
            with self.assertRaisesRegex(ValueError, "unknown or duplicate"):
                build_dataset([left], root / "unknown_key", analysis_selections=_selection(right, analysis))
            selection = _selection(left, analysis)
            selection[str(left)]["manifest_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "manifest changed"):
                build_dataset([left], root / "wrong_hash", analysis_selections=selection)
            manifest_path = analysis / "manifest.json"
            original_manifest = manifest_path.read_bytes()
            changed_manifest = json.loads(original_manifest)
            changed_manifest["run_id"] = "wrong_run_id"
            manifest_path.write_text(json.dumps(changed_manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "run_id differs"):
                build_dataset([left], root / "wrong_identity", analysis_selections=_selection(left, analysis))
            manifest_path.write_bytes(original_manifest)
            (left / "events.jsonl").write_text("\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "run source changed"):
                build_dataset([left], root / "changed_source", analysis_selections=_selection(left, analysis))
            for name in ("wrong_binding", "unknown_key", "wrong_hash", "wrong_identity", "changed_source"):
                self.assertFalse((root / name).exists())


if __name__ == "__main__":
    unittest.main()
