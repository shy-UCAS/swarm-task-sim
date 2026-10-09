"""v0.6 data provenance and language; four frozen v0.5 loads stay identical."""

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from swarm_sim.dataset import build_dataset
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.episode_loader import FEATURE_COLUMNS, load_episode
from swarm_sim.language_v0 import describe_dataset
from swarm_sim.language_templates_v0 import (
    _WORDINGS, generate_descriptions, template_inventory, validate_description,
)
from swarm_sim.observer_facts_v0 import _channel_facts
from swarm_sim.protocol import (
    PROTOCOL_FIELDS, V06_SEMANTIC_VERSION, semantic_protocol, supported_protocols, task_metadata,
)
from swarm_sim.recording import write_json
from swarm_sim.registry import component_versions, registered_intents
from test_wp_l_templates import _facts
from v3_artifact_fixture import make_run, rehash


ROOT = Path(__file__).resolve().parents[1]
VERSIONS = dict(planner="equal_strip_lawnmower_v1", validator="shared_coverage_v2",
                facts="observer_facts_v06", templates="templates_zh_v06")


def _sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _v06_run(root):
    """Upgrade synthetic contract evidence; no telemetry or simulation is run."""
    run, analysis = make_run(root)
    task = json.loads((analysis / "task.json").read_text())
    task["execution"].update(protocol_version="v0.6", final_hold_s=2.0, firmware_version_timeout_s=10.0)
    task.update(flight_pattern="equal_strip_lawnmower", component_versions=VERSIONS)
    write_json(analysis / "task.json", task)
    protocol = semantic_protocol({"task_spec": task})
    for name in ("manifest.json", "quality.json"):
        item = json.loads((analysis / name).read_text())
        item.update(protocol)
        if name == "manifest.json":
            item.update(task_metadata(task))
        write_json(analysis / name, item)
    for name, key, value in (
            ("semantic_validation.json", "semantic_validation_version", V06_SEMANTIC_VERSION),
            ("execution_constraints.json", "constraint_validation_version", protocol["execution_constraints_version"])):
        item = json.loads((analysis / name).read_text())
        item[key] = value
        write_json(analysis / name, item)
    labels = json.loads((analysis / "labels.json").read_text())
    labels["label_provenance"]["semantic_validation_version"] = V06_SEMANTIC_VERSION
    write_json(analysis / "labels.json", labels)
    rehash(run)
    return run, analysis


def _v06_facts(intent):
    if intent == "rapid_passage":
        conditions = dict.fromkeys(("entered", "opposite_exit", "straight", "no_dwell", "no_loop", "return"), True)
        result = _facts(intent, pattern="direct_passage", conditions=conditions)
    elif intent == "patrol":
        result = _facts(intent, conditions=dict(max_gap=True, **{"return": True}))
    else:
        result = _facts(intent)
    result["facts_version"] = "observer_facts_v06"
    result["provenance"] = {"versions": {"semantic_validation_version": V06_SEMANTIC_VERSION}}
    return result


class V06DataContractTests(unittest.TestCase):
    def test_four_frozen_v05_examples_preserve_all_features_targets_and_old_metadata(self):
        baseline = json.loads((ROOT / "tests/fixtures/v05_example_loader_baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(baseline["baseline_commit"], "4d37ebd")
        self.assertEqual(len(baseline["episodes"]), 4)
        for expected in baseline["episodes"]:
            with self.subTest(run_id=expected["run_id"]):
                root = ROOT / "examples/v05_episodes" / expected["run_id"]
                loaded = load_episode(root)
                for field, digest in expected["sha256"].items():
                    self.assertEqual(_sha(loaded[field]), digest, field)
                metadata = loaded["metadata"]
                self.assertEqual({key: metadata[key] for key in expected["metadata"]}, expected["metadata"])
                self.assertEqual(metadata["source_directory"], str(root.resolve()))
                self.assertIsNone(metadata["flight_pattern"])
                self.assertIsNone(metadata["protocol_version"])
                self.assertEqual(metadata["component_versions"], {})
                self.assertEqual(metadata["feature_columns"], list(FEATURE_COLUMNS))

    def test_v06_protocol_distinct_supported_and_v05_v06_mix_rejected(self):
        old = semantic_protocol({"task_spec": {"schema_version": 3, "mission": {"intent": "patrol"}}},
                                patrol_validator_version="perimeter_revisit_v2")
        new = semantic_protocol({"task_spec": {"schema_version": 3, "execution": {"protocol_version": "v0.6"}}})
        self.assertNotEqual(old, new)
        self.assertIn(tuple(new[key] for key in PROTOCOL_FIELDS), supported_protocols())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            a, _ = make_run(root / "old")
            b, _ = _v06_run(root / "new")
            with self.assertRaisesRegex(ValueError, "incompatible semantic"):
                build_dataset([a, b], root / "rejected")

    def test_export_load_new_metadata_never_enters_six_observation_features(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run, _ = _v06_run(root / "new")
            dataset = build_dataset([run], root / "dataset")
            entry = dataset["episodes"][0]
            episode = root / "dataset" / entry["directory"]
            loaded = load_episode(episode)
            for key in ("flight_pattern", "component_versions", "protocol_version"):
                self.assertEqual(loaded["metadata"][key], entry[key])
            self.assertEqual(loaded["metadata"]["component_versions"], VERSIONS)
            self.assertEqual(loaded["x"][0][0], [1., 2., 8., 3., 0., 0.])
            self.assertEqual(loaded["metadata"]["feature_columns"], list(FEATURE_COLUMNS))
            entry["flight_pattern"] = "interleaved_lanes"
            write_json(root / "dataset/dataset_manifest.json", dataset)
            with self.assertRaisesRegex(ValueError, "metadata disagree"):
                load_episode(episode)

    def test_v06_missing_or_contradictory_component_metadata_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            run, analysis = _v06_run(Path(temporary) / "new")
            item = json.loads((analysis / "manifest.json").read_text())
            item["component_versions"]["templates"] = "wrong"
            write_json(analysis / "manifest.json", item)
            rehash(run)
            with self.assertRaisesRegex(ValueError, "v0.6 task metadata"):
                load_episode(analysis)

    def test_actual_analysis_export_audit_and_language_preserve_three_intent_v06_contract(self):
        from swarm_sim.analysis import analyze_run
        from swarm_sim.tasks import compile_task

        with tempfile.TemporaryDirectory() as temporary:
            root, runs = Path(temporary), []
            for intent, pattern in (("reconnaissance", "equal_strip_lawnmower"),
                                    ("patrol", "staggered_same_loop"), ("rapid_passage", "line_abreast")):
                template = "patrol_route_v05.json" if intent == "patrol" else "recon_route_v05.json"
                task = json.loads((ROOT / "missions/v3" / template).read_text(encoding="utf-8"))
                task.update(task_id=intent, flight_pattern=pattern, component_versions=component_versions(intent, pattern))
                task["execution"].update(protocol_version="v0.6", final_hold_s=2., firmware_version_timeout_s=10.)
                if intent == "rapid_passage":
                    task["mission"].update(intent=intent, intent_params=dict(objective="single_straight_crossing"))
                    task["planner"] = dict(name="line_abreast_v1", params=dict(entry_side="south", exit_margin_m=5., tracking_margin_m=1.))
                scene = compile_task(task)
                run = root / intent
                run.mkdir()
                write_json(run / "scenario.json", scene)
                write_json(run / "metadata.json", dict(version="0.5.0-dev", run_id=intent, scenario=scene,
                    status="failed", run_epoch_monotonic_s=100., elapsed_s=.1))
                (run / "events.jsonl").write_text("", encoding="utf-8")
                analysis, _, labels = analyze_run(run)
                self.assertIsNot(labels["mission_success"], True)
                loaded = load_episode(analysis)
                self.assertEqual(loaded["metadata"]["semantic_validation_version"], V06_SEMANTIC_VERSION)
                self.assertEqual(loaded["metadata"]["flight_pattern"], pattern)
                runs.append(run)
            dataset = build_dataset(runs, root / "dataset")
            self.assertEqual(dataset["counts"]["total"], 3)
            audit = audit_dataset(root / "dataset")
            self.assertEqual(len(audit["flight_pattern_groups"]), 3)
            language = describe_dataset(root / "dataset", root / "language")
            self.assertEqual(language["skipped_episodes"], 3)
            self.assertEqual(language["descriptions"], 0)
            self.assertEqual(language["facts_version"], "observer_facts_v06")
            self.assertEqual(language["templates_version"], "templates_zh_v06")

    def test_all_registered_intents_have_three_train_one_test_disjoint_wordings(self):
        self.assertEqual(set(registered_intents()), {"reconnaissance", "patrol", "rapid_passage"})
        for key, partitions in template_inventory().items():
            self.assertEqual(len(partitions["train"]), 3)
            self.assertEqual(len(partitions["test"]), 1)
            self.assertFalse(set(partitions["train"]) & set(partitions["test"]))
            self.assertNotIn(_WORDINGS[key][3], _WORDINGS[key][:3])
        for intent in registered_intents():
            with self.subTest(intent=intent):
                facts = _v06_facts(intent)
                descriptions = generate_descriptions(facts, intent, "validation", 11)
                self.assertEqual([d["template_partition"] for d in descriptions], ["train"] * 3 + ["test"])
                train_sentences = {s["text"] for d in descriptions[:3] for s in d["sentences"]}
                self.assertTrue(all(s["text"] not in train_sentences for s in descriptions[3]["sentences"]))
                for item in descriptions:
                    self.assertTrue(validate_description(item, facts)[0])
                    self.assertEqual(item["template_version"], "templates_zh_v06")
                    for forbidden in ("更快", "横队", "纵队", "分道", "飞法"):
                        self.assertNotIn(forbidden, item["text"])

    def test_rapid_failed_or_unknown_conditions_never_emit_success_claim(self):
        for value in (False, None):
            facts = _v06_facts("rapid_passage")
            facts["observed"]["observed_pattern"] = "unclear"
            facts["labels"]["mission_result"]["conditions"]["opposite_exit"] = value
            facts["labels"]["mission_result"]["success"] = value
            for item in generate_descriptions(facts, "truncated", "test", 11):
                self.assertFalse(any(s["template_id"].startswith(("T3.passage_pass", "T2.direct", "T5.rapid_match"))
                                     for s in item["sentences"]))

    def test_transit_facts_depend_on_measured_complete_trajectory_not_pattern_metadata(self):
        region = dict(min_east_m=0., min_north_m=0., width_m=40., height_m=30.)
        task = dict(mission=dict(intent="rapid_passage"), execution=dict(
            protocol_version="v0.6", max_gap_s=.5, record_hz=10.))
        traces = {"a": [(index / 10, [-5 + index / 2, 15., 10.]) for index in range(101)]}
        windows = [dict(agent_id="a", semantic_phase="approach", start_s=0., arrival_s=0., complete_execution_window=True),
                   dict(agent_id="a", semantic_phase="transit", start_s=0., arrival_s=10., complete_execution_window=True)]
        measure = lambda value, rows=traces: _channel_facts(rows, windows, value, region, dict(duration_s=10.), {}, ["a"])
        facts = measure(task)
        self.assertEqual(facts["observed_pattern"], "direct_passage")
        self.assertEqual(facts["entry_side"], "west")
        self.assertEqual(facts["exit_side"], "east")
        self.assertTrue(facts["crossed"])
        changed = copy.deepcopy(task)
        changed["flight_pattern"] = "column"
        self.assertEqual(measure(changed), facts)
        truncated = measure(task, {"a": traces["a"][:51]})
        self.assertNotEqual(truncated["observed_pattern"], "direct_passage")
        self.assertIsNone(truncated["crossed"])
        self.assertIsNone(truncated["exit_side"])


if __name__ == "__main__":
    unittest.main()
