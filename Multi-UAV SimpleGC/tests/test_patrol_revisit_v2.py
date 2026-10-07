"""r1.2b: count diagnostics cannot decide patrol v2 outcomes or language."""

import json
import tempfile
import unittest
from pathlib import Path

from swarm_sim.analysis import digest
from swarm_sim.analysis_v3 import analyze_run_v3
from swarm_sim.dataset import build_dataset
from swarm_sim.episode_loader import load_episode
from swarm_sim.language_v0 import describe_dataset
from swarm_sim.language_templates_v0 import generate_descriptions, validate_description
from swarm_sim.mission_evaluation_v3 import _channel
from swarm_sim.patrol_validation import evaluate_channel
from swarm_sim.protocol import V05_R12B_SEMANTIC_VERSION, semantic_protocol
from swarm_sim.recording import write_json
from swarm_sim.registry import get_intent
from swarm_sim.tasks import compile_task
from test_wp_p_validation import _case
from test_wp_l_templates import _facts


ROOT = Path(__file__).resolve().parents[1]
V2 = "perimeter_revisit_v2"


class PatrolRevisitV2Tests(unittest.TestCase):
    def test_count_shortfall_is_diagnostic_only(self):
        scene, traces, windows = _case(actual_laps=(1, 2))
        old = evaluate_channel(scene, traces, windows, {})
        new = evaluate_channel(scene, traces, windows, {}, validator_version=V2)
        self.assertFalse(old["conditions"]["visits"])
        self.assertTrue(old["conditions"]["max_gap"])
        self.assertEqual(new["conditions"], {"max_gap": True})
        before, after = old["metrics"]["perimeter_revisit"], new["metrics"]["perimeter_revisit"]
        self.assertFalse(before["patrol_success"])
        self.assertTrue(after["patrol_success"])
        for field in ("segments", "group_segment_visit_counts", "visits_pass", "min_segment_visits"):
            self.assertEqual(before[field], after[field])
        self.assertEqual(after["visit_count_role"], "diagnostic_only")

    def test_gap_failure_and_missing_evidence_still_propagate(self):
        for kwargs, expected in (({"end": 160.}, False), ({"missing_gap": True}, None)):
            with self.subTest(kwargs=kwargs):
                scene, traces, windows = _case(**kwargs)
                result = evaluate_channel(scene, traces, windows, {}, validator_version=V2)
                self.assertIs(result["conditions"]["max_gap"], expected)
                self.assertIs(result["metrics"]["perimeter_revisit"]["patrol_success"], expected)

    def test_real_return_geometry_failure_still_fails_mission(self):
        scene, traces, windows = _case()
        scene["task_spec"]["mission"]["return_required"] = True
        scene["task_spec"]["execution"].update(takeoff_alt_m=8., confirmation_dwell_s=0.,
            record_hz=4., max_gap_s=1., arrival_tolerance_m=1.)
        for vehicle in scene["vehicles"]:
            vehicle.update(east_m=-100., north_m=-100.)
        for window in windows:
            window["role"] = "patrol"
        returned = [dict(agent_id=a, role="return", start_s=79., end_s=80.,
                         complete_execution_window=True) for a in traces]
        metrics, conditions = _channel(scene, traces, windows, {}, get_intent("patrol"), returned,
                                       patrol_validator_version=V2)
        self.assertTrue(metrics["perimeter_revisit"]["patrol_success"])
        self.assertEqual(conditions, {"max_gap": True, "return_to_launch": False})
        self.assertFalse(metrics["mission_success"])

    def test_new_analysis_protocol_and_original_pointer_are_preserved(self):
        for intent in ("patrol", "reconnaissance"):
            with self.subTest(intent=intent), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                name = "patrol" if intent == "patrol" else "recon"
                task = json.loads((ROOT / f"missions/v3/{name}_route_v05.json").read_text(encoding="utf-8"))
                scene = compile_task(task)
                run = root / "run"
                run.mkdir()
                write_json(run / "scenario.json", scene)
                write_json(run / "metadata.json", dict(version="0.5.0-dev", run_id="fixture", scenario=scene,
                    status="failed", run_epoch_monotonic_s=100., elapsed_s=.1))
                (run / "events.jsonl").write_text("", encoding="utf-8")
                old, _, _ = analyze_run_v3(run)
                original = {p.name: digest(p) for p in run.iterdir() if p.is_file()}
                output, quality, labels = analyze_run_v3(run, patrol_validator_version=V2,
                    progress_mapping_version="ordered_route_progress_v2", output_directory=root / "new_analysis",
                    update_latest=False)
                self.assertEqual(original, {p.name: digest(p) for p in run.iterdir() if p.is_file()})
                self.assertEqual(load_episode(old)["metadata"]["semantic_validation_version"], "multi_intent_validation_v2")
                self.assertEqual(load_episode(output)["metadata"]["semantic_validation_version"], V05_R12B_SEMANTIC_VERSION)
                self.assertEqual(quality["semantic_validation_version"], V05_R12B_SEMANTIC_VERSION)
                if intent == "patrol":
                    self.assertEqual(labels["label_provenance"]["validator_versions"], {"patrol": V2})
                    self.assertEqual(labels["observed_behaviors"][0]["rule_version"], V2)
                # This fixture may advance its own pointer; production reanalysis above cannot.
                analyze_run_v3(run, patrol_validator_version=V2,
                    progress_mapping_version="ordered_route_progress_v2")
                dataset = root / "dataset"
                build_dataset([run], dataset)
                language = describe_dataset(dataset)
                self.assertEqual(language["semantic_validation_version"], V05_R12B_SEMANTIC_VERSION)
                self.assertEqual(language["input_episodes"], 1)
                self.assertEqual(language["skipped_episodes"], 1)

    def test_v2_templates_use_gap_and_return_only(self):
        for gap, returned in ((True, True), (False, True), (True, False)):
            with self.subTest(gap=gap, returned=returned):
                facts = _facts("patrol", conditions={"max_gap": gap, "return": returned})
                facts["provenance"] = {"versions": {"semantic_validation_version": V05_R12B_SEMANTIC_VERSION}}
                descriptions = generate_descriptions(facts, "new_patrol", "train", 42)
                self.assertEqual(len(descriptions), 4)
                for description in descriptions:
                    self.assertNotIn("经过次数", description["text"])
                    self.assertFalse(any("visits" in s["template_id"] for s in description["sentences"]))
                    self.assertTrue(validate_description(description, facts)[0])
                facts["labels"]["mission_result"]["conditions"]["visits"] = False
                with self.assertRaisesRegex(ValueError, "cannot use visits"):
                    generate_descriptions(facts, "bad_patrol", "train", 42)

    def test_explicit_version_selection_rejects_unknown_or_old_contract(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            semantic_protocol({}, patrol_validator_version="future")
        with self.assertRaisesRegex(ValueError, "v0.5"):
            semantic_protocol({}, patrol_validator_version=V2)


if __name__ == "__main__":
    unittest.main()
