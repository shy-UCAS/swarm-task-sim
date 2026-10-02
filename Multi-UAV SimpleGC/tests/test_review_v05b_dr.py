"""Pure offline checks for the v05b DR review; no generation or SITL."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from swarm_sim.generation import file_hash

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "review_v05b_dr", ROOT / "scripts/review_v05b_dr.py")
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


class V05bReviewTests(unittest.TestCase):
    def test_observe_geometry_uses_actual_lanes_and_production_crosscheck(self):
        candidate = {"candidate_id": "example", "base_index": 0}
        row = {"vehicle_count": 3, "region_width_m": 36.0,
               "region_height_m": 50.0, "resolved_axis": "east",
               "entry_side": "south", "inferred_entry_side": "south"}
        scene = {
            "task_spec": {"planner": {"params": {"lane_spacing_m": 4.0}}},
            "planning": {
                "partition_axis": "east",
                "partition_axis_resolution": {"inferred_entry_side": "south"},
                "feasibility_checks": {"nominal_phase_timing": {
                    "p01_observe": {"nominal_min_clearance_m": 8.0,
                                    "required_clearance_m": 7.0}}}}}
        good = review.observe_geometry(candidate, row, scene)
        self.assertEqual(good["lanes_per_strip"], 3)
        self.assertEqual(good["actual_scanline_spacing_m"], 4.0)
        self.assertEqual(good["geometric_min_m"], 8.0)
        self.assertTrue(good["geometry_pass"] and good["crosscheck_pass"])
        scene["planning"]["feasibility_checks"]["nominal_phase_timing"]["p01_observe"][
            "nominal_min_clearance_m"] = 7.9
        self.assertFalse(review.observe_geometry(candidate, row, scene)["crosscheck_pass"])
        row["region_width_m"] = 30.0
        scene["planning"]["feasibility_checks"]["nominal_phase_timing"]["p01_observe"][
            "nominal_min_clearance_m"] = 20.0 / 3.0
        narrow = review.observe_geometry(candidate, row, scene)
        self.assertFalse(narrow["geometry_pass"])
        self.assertTrue(narrow["crosscheck_pass"])

    def test_composition_and_distribution_preserve_draw_denominator(self):
        base = dict(vehicle_count=2, entry_side="south", resolved_axis="east",
                    line_rotation_deg=0.0, region_width_m=24.0, region_height_m=30.0,
                    region_unit_width_m=12.0, region_unit_height_m=15.0, speed_m_s=2.5)
        rows = [dict(base, accepted=False), dict(base, accepted=True)]
        table = review.composition(rows)
        self.assertEqual(len(table), 24)
        cell = next(row for row in table if row["vehicle_count"] == 2
                    and row["entry_side"] == "south" and row["resolved_axis"] == "east")
        self.assertEqual((cell["candidate_draws"], cell["accepted_scenes"]), (2, 1))
        self.assertEqual(review.selection(rows)["histograms"]["line_rotation_deg"][2]["count"], 2)

    def test_artifact_integrity_rejects_changed_and_unregistered_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "task.json"
            artifact.write_text(json.dumps({"a": 1}), encoding="utf-8")
            manifest = {"artifact_sha256": {"task.json": file_hash(artifact)}}
            self.assertTrue(review.artifact_integrity(root, manifest)["pass_gate"])
            artifact.write_text(json.dumps({"a": 2}), encoding="utf-8")
            self.assertEqual(review.artifact_integrity(root, manifest)["changed"], ["task.json"])
            (root / "extra.json").write_text("{}", encoding="utf-8")
            self.assertEqual(review.artifact_integrity(root, manifest)["unregistered"],
                             ["extra.json"])


if __name__ == "__main__":
    unittest.main()
