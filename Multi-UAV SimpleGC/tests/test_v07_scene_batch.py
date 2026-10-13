"""External attempt/summary integration checks without plotting imports."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from scene_v07 import SceneConfig, canonical_json, sample_family
from scene_v07.batch import REPOSITORY_ROOT, generate_attempt, new_attempt, select_representatives, summarize


class BatchTests(unittest.TestCase):
    def test_attempts_never_overwrite_existing_content(self):
        with tempfile.TemporaryDirectory() as root:
            first = new_attempt(root, "attempt_first")
            sentinel = first / "sentinel.txt"
            sentinel.write_text("preserve", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                new_attempt(root, "attempt_first")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")
            self.assertNotEqual(new_attempt(root), new_attempt(root))

    def test_attempt_rejects_traversal_and_repository_output(self):
        for name in ("../outside", "attempt_../outside", "attempt_foo\\bar", "anything"):
            with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError):
                new_attempt(root, name)
        with self.assertRaises(ValueError):
            new_attempt(REPOSITORY_ROOT / "new_scene_output")

    def test_saved_json_reconstructs_byte_for_byte_from_family_seed(self):
        with tempfile.TemporaryDirectory() as root:
            config = SceneConfig(angle_step_deg=30)
            summary = generate_attempt(3, 2026101307, root, "attempt_test", config)
            attempt = Path(summary["attempt_directory"])
            records = json.loads((attempt / "candidates.json").read_text(encoding="utf-8"))
            self.assertEqual(len(records), 3)
            self.assertEqual(summary["plot_count"], 0)
            for record in records:
                directory = Path(record["directory"])
                public, family = sample_family(record["sampling_seed"], config)
                self.assertEqual((directory / "public_scene.json").read_bytes(), canonical_json(public))
                self.assertEqual((directory / "family_initial.json").read_bytes(), canonical_json(family))
                saved = json.loads((directory / "check_results.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["accepted"], record["accepted"])
            self.assertEqual(summary["candidate_count"], summary["accepted_count"] + summary["rejected_count"])
            self.assertFalse(summary["angle_span_used_as_rejection_gate"])

    def test_single_seed_rebuild_uses_a_new_attempt(self):
        with tempfile.TemporaryDirectory() as root:
            config = SceneConfig(angle_step_deg=30)
            result = generate_attempt(1, 1, root, "attempt_rebuild", config, single_family_seed=42)
            scene, family = sample_family(42, config)
            directory = Path(result["attempt_directory"]) / family["family_id"]
            self.assertEqual((directory / "public_scene.json").read_bytes(), canonical_json(scene))
            with self.assertRaises(ValueError):
                generate_attempt(2, 1, root, single_family_seed=42)

    def test_renderer_callback_and_timing_accounting(self):
        with tempfile.TemporaryDirectory() as root:
            calls = []
            def fake_plotter(scene, family, checks, path, index):
                calls.append(index)
                with path.open("xb") as stream:
                    stream.write(b"fixture")
            result = generate_attempt(2, 17, root, "attempt_renderer", SceneConfig(angle_step_deg=90), fake_plotter)
            self.assertEqual(calls, [0, 1])
            self.assertEqual(result["plot_count"], 2)
            timing = result["timing_s"]
            self.assertGreaterEqual(timing["plotting"], 0)
            self.assertAlmostEqual(timing["sampling_and_plotting"], timing["plotting"] + timing["sampling_and_checks"])
            self.assertGreaterEqual(timing["total_wall"], timing["sampling_and_plotting"])

    def test_rejection_counts_deduplicate_family_reason_and_accepted_stats_only(self):
        accepted = {"accepted": True, "geometry_issue_codes": [], "connectivity_issue_codes": [], "issue_codes": [],
                    "facility_count": 1, "facility_shapes": ["Circle"], "obstacle_count": 1,
                    "obstacle_placements": ["entry_blocking"], "radar_count": 1, "layout": "single",
                    "vehicle_count": 4, "detour_ratios": [1, 1.2], "approach_spans_deg": [30]}
        rejected = deepcopy(accepted)
        rejected.update(accepted=False, geometry_issue_codes=["bad"], issue_codes=["bad"], detour_ratios=[5])
        result = summarize([accepted, rejected])
        self.assertEqual(result["geometry_rejection_rate"], .5)
        self.assertEqual(result["rejection_reason_counts"], {"bad": 1})
        self.assertEqual(result["accepted_route_detour_ratio"]["max"], 1.2)
        self.assertEqual(result["accepted_facilities_below_60deg"], 1)
        self.assertEqual(result["accepted_distributions"]["families"], 1)

    def test_bad_budget_does_not_create_attempt(self):
        with tempfile.TemporaryDirectory() as root:
            for count in (0, -1, True):
                with self.assertRaises(ValueError):
                    generate_attempt(count, output_root=root)
            self.assertEqual(list(Path(root).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
