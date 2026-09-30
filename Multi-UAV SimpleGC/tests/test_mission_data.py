"""B01-B05 / D02,D06-D08: generation, resume evidence and feature isolation."""

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swarm_sim.dataset import build_dataset, family_split
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.episode_loader import FEATURE_COLUMNS, load_episode
from swarm_sim.generation import canonical_hash, file_hash, generate, save_json, verify_generation
from swarm_sim.quality import policy_hash, resolve_policy
from swarm_sim.protocol import semantic_protocol

ROOT = Path(__file__).resolve().parents[1]
runner_spec = importlib.util.spec_from_file_location("mission_list_runner", ROOT / "scripts/run_mission_list.py")
batch = importlib.util.module_from_spec(runner_spec)
runner_spec.loader.exec_module(batch)


def profile(count=2, variants=None):
    return dict(schema_version=1, master_seed=927, base_scene_count=count, max_candidates_per_base=2,
        template_spec=json.loads((ROOT / "missions/recon_shared_3uav.json").read_text(encoding="utf-8")),
        vehicle_counts=[2], partition_axes=["east"], strip_width_m=[12, 12], sweep_length_m=[8, 8],
        region_east_m=[-20, 0], region_north_m=[-20, 0], entry_distance_m=[10, 10],
        entry_sides=["low"], speeds_m_s=[2], return_required=[True], variant_speed_factors=variants or [1.0])


def make_episode(root, rows=None, extra_columns=()):
    root.mkdir(parents=True)
    rows = rows if rows is not None else [[0, "uav_01", 1, *range(1, 7)],
                                         [1, "uav_01", 1, *range(11, 17)],
                                         [0, "uav_02", 0, *([""] * 6)]]
    with (root / "observations.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["t_s", "agent_id", "valid", *FEATURE_COLUMNS, *extra_columns])
        writer.writerows(rows)
    protocol = semantic_protocol({"task_spec": {"schema_version": 2}})
    save_json(root / "labels.json", dict(requested_intent="reconnaissance", mission_success=True,
        schema_version=protocol["label_schema_version"], task_kind=protocol["task_kind"],
        label_provenance=dict(semantic_validation_version=protocol["semantic_validation_version"]),
        observed_behaviors=[dict(rule_version=protocol["semantic_validation_version"])]))
    save_json(root / "quality.json", protocol)
    save_json(root / "semantic_validation.json", dict(semantic_validation_version=protocol["semantic_validation_version"]))
    save_json(root / "execution_constraints.json", dict(constraint_validation_version=protocol["execution_constraints_version"]))
    save_json(root / "truth.json", dict(east_m=999999, mission_success=True))
    save_json(root / "manifest.json", dict(run_id=root.name, family_id="family_alpha", agent_ids=["uav_02", "uav_01"],
        benchmark_eligible=True, duration_s=1.0, quality_policy=resolve_policy(), quality_policy_sha256=policy_hash(None),
        **protocol, artifact_sha256={path.name: file_hash(path) for path in root.iterdir() if path.is_file()}))


def fake_run(scene, output, binary, parameters, base_port, policy, generation_context=None, status="completed", success=True, error=None):
    root = output / "synthetic_run"
    root.mkdir()
    metadata = dict(scenario=scene, status=status, quality_policy_sha256=policy_hash(policy), error=error)
    protocol = semantic_protocol(scene)
    quality = dict(mission_success=success, benchmark_eligible=status == "completed" and success is True,
                   strict_benchmark_eligible=False, usable=status == "completed" and success is True, **protocol)
    save_json(root / "metadata.json", metadata)
    save_json(root / "scenario.json", scene)
    for name, value in (generation_context or {}).items():
        save_json(root / (name + ".json"), value)
    analysis = root / "analysis_test"
    analysis.mkdir()
    save_json(analysis / "quality.json", quality)
    save_json(analysis / "labels.json", dict(mission_success=success, schema_version=protocol["label_schema_version"],
        task_kind=protocol["task_kind"], label_provenance=dict(semantic_validation_version=protocol["semantic_validation_version"]),
        observed_behaviors=[dict(rule_version=protocol["semantic_validation_version"])]))
    save_json(analysis / "semantic_validation.json", dict(semantic_validation_version=protocol["semantic_validation_version"]))
    save_json(analysis / "execution_constraints.json", dict(constraint_validation_version=protocol["execution_constraints_version"]))
    save_json(analysis / "manifest.json", dict(quality_policy_sha256=policy_hash(policy), **semantic_protocol(scene),
        artifact_sha256={path.name: file_hash(path) for path in analysis.iterdir() if path.is_file()},
        source_sha256={path.name: file_hash(path) for path in root.glob("*.json")}))
    save_json(root / "analysis_latest.json", dict(directory=analysis.name, manifest_sha256=file_hash(analysis / "manifest.json")))
    return root, metadata, quality


class GenerationTests(unittest.TestCase):
    def test_b01_same_profile_seed_produces_identical_frozen_bundles(self):
        with tempfile.TemporaryDirectory() as temp:
            left, right = Path(temp) / "left", Path(temp) / "right"
            generate(profile(), left)
            generate(profile(), right)
            left_files = {p.relative_to(left).as_posix(): p.read_bytes() for p in left.rglob("*.json")}
            right_files = {p.relative_to(right).as_posix(): p.read_bytes() for p in right.rglob("*.json")}
            self.assertEqual(left_files, right_files)
            listing, manifest = verify_generation(left / "mission_list.json")
            self.assertEqual(manifest["counts"]["accepted_bases"], 2)
            self.assertEqual(len({m["family_id"] for m in listing["missions"]}), 2)

    def test_d02_d08_variants_share_base_family_but_independent_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "out"
            generate(profile(2, [1.0, 1.1]), output)
            listing, _ = verify_generation(output / "mission_list.json")
            a, b, c, d = listing["missions"]
            self.assertEqual(a["family_id"], b["family_id"])
            self.assertNotEqual(a["family_id"], c["family_id"])
            self.assertEqual(c["family_id"], d["family_id"])
            self.assertNotEqual(a["task_sha256"], b["task_sha256"])
            self.assertEqual(a["base_scene_sha256"], b["base_scene_sha256"])
            self.assertEqual(family_split(a["family_id"]), family_split(b["family_id"]))

    def test_b02_rejected_candidates_are_finite_and_preserved(self):
        with tempfile.TemporaryDirectory() as temp, patch("swarm_sim.tasks.compile_task", side_effect=ValueError("unsafe approach")) as compiler:
            output = Path(temp) / "out"
            report = generate(profile(3), output)
            self.assertEqual(compiler.call_count, 6)
            self.assertEqual(report["counts"]["rejected_candidates"], 6)
            self.assertEqual(report["counts"]["planned_missions"], 0)
            self.assertTrue(all("unsafe approach" in c["reason"] for c in report["candidates"]))
            self.assertEqual(len(list((output / "candidates").glob("*.json"))), 6)

    def test_generation_integrity_and_profile_bounds(self):
        with tempfile.TemporaryDirectory() as temp:
            for changes in (dict(base_scene_count=True), dict(max_candidates_per_base=11),
                            dict(speeds_m_s=[float("nan")]), dict(entry_sides=["unknown"]), dict(unused=True)):
                data = profile()
                data.update(changes)
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    generate(data, Path(temp) / "bad")
            output = Path(temp) / "out"
            generate(profile(1), output)
            listing, _ = verify_generation(output / "mission_list.json")
            task = output / listing["missions"][0]["task"]
            task.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "generation artifact changed"):
                verify_generation(output / "mission_list.json")


class LoaderTests(unittest.TestCase):
    def test_d06_feature_whitelist_targets_separate_and_missing_agents_masked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "episode"
            make_episode(root, [[0, "uav_01", 1, 1, 2, 3, 4, 5, 6, "reconnaissance", 999],
                                [1, "uav_01", 1, 11, 12, 13, 14, 15, 16, "reconnaissance", 999],
                                [0, "uav_02", 0, "", "", "", "", "", "", "reconnaissance", 999]],
                         ("requested_intent", "truth_east_m"))
            result = load_episode(root)
            self.assertEqual(result["agent_ids"], ["uav_01", "uav_02"])
            self.assertEqual(result["t_s"], [0.0, 1.0])
            self.assertEqual(result["x"], [[[1., 2., 3., 4., 5., 6.], [0.] * 6],
                                           [[11., 12., 13., 14., 15., 16.], [0.] * 6]])
            self.assertEqual(result["mask"], [[True, False], [True, False]])
            self.assertEqual(result["targets"]["requested_intent"], "reconnaissance")
            self.assertFalse(result["metadata"]["normalized"])

    def test_d07_duplicate_unknown_time_and_numeric_corruption_fail(self):
        normal = [0, "uav_01", 1, 1, 2, 3, 4, 5, 6]
        cases = {
            "duplicate": [normal, normal],
            "unknown": [[0, "uav_03", 1, 1, 2, 3, 4, 5, 6]],
            "nonmonotonic": [[1, *normal[1:]], normal],
            "invalid observation time": [["nan", *normal[1:]]],
            "nonfinite": [[0, "uav_01", 1, "inf", 2, 3, 4, 5, 6]],
            "invalid east_m": [[0, "uav_01", 1, "", 2, 3, 4, 5, 6]],
            "invalid observation mask": [[0, "uav_01", "true", 1, 2, 3, 4, 5, 6]],
        }
        for name, rows in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "episode"
                make_episode(root, rows)
                with self.assertRaisesRegex(ValueError, name):
                    load_episode(root)

    def test_d07_missing_feature_columns_and_modified_artifact_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "episode"
            make_episode(root)
            text = (root / "observations.csv").read_text(encoding="utf-8")
            (root / "observations.csv").write_text(text.replace("ve_m_s", "hidden_label"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact changed"):
                load_episode(root)
            with self.assertRaisesRegex(ValueError, "missing or duplicate"):
                load_episode(root, verify_hashes=False)

    def test_b05_audit_has_explicit_denominators_and_flags_family_leak(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entries = []
            for index, split in enumerate(("train", "test")):
                episode = root / "episodes" / f"run_{index}"
                make_episode(episode)
                entries.append(dict(run_id=episode.name, directory=f"episodes/{episode.name}", family_id="family_alpha",
                    split=split, analysis_manifest_sha256=file_hash(episode / "manifest.json"), run_status="completed",
                    benchmark_eligible=index == 0, strict_benchmark_eligible=False))
            save_json(root / "dataset_manifest.json", dict(episodes=entries))
            report = audit_dataset(root)
            self.assertEqual(report["rates"]["default_eligible"]["numerator"], 1)
            self.assertEqual(report["rates"]["default_eligible"]["denominator"], 2)
            self.assertEqual(report["rates"]["planning"]["fraction"], None)
            self.assertEqual(report["family_split_leaks"], {"family_alpha": ["test", "train"]})
            self.assertNotIn("accuracy", report)

    def test_loader_rejects_incompatible_or_partial_semantic_protocol(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "episode"
            make_episode(root)
            path = root / "manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["semantic_validation_version"] = "unsupported_future_semantics"
            save_json(path, manifest)
            with self.assertRaisesRegex(ValueError, "unsupported semantic protocol"):
                load_episode(root)
            del manifest["ontology_version"]
            save_json(path, manifest)
            with self.assertRaisesRegex(ValueError, "incomplete semantic protocol"):
                load_episode(root)

    def test_D05_rehashed_cross_artifact_protocol_conflicts_rejected_by_all_consumers(self):
        from swarm_sim import __version__
        from swarm_sim.analysis import analyze_run
        from swarm_sim.tasks import compile_task

        cases = (("labels.json", lambda value: value["label_provenance"].update(semantic_validation_version="shared_coverage_old")),
                 ("labels.json", lambda value: value["observed_behaviors"][0].update(rule_version="shared_coverage_old")),
                 ("labels.json", lambda value: value.update(schema_version=1)),
                 ("quality.json", lambda value: value.update(semantic_validation_version="shared_coverage_old")),
                 ("semantic_validation.json", lambda value: value.update(semantic_validation_version="shared_coverage_old")),
                 ("execution_constraints.json", lambda value: value.update(constraint_validation_version="execution_limits_old")))
        for filename, mutate in cases:
            with self.subTest(file=filename), tempfile.TemporaryDirectory() as temp:
                run = Path(temp) / "run"
                run.mkdir()
                (run / "raw").mkdir()
                scene = compile_task(profile(1)["template_spec"])
                save_json(run / "metadata.json", dict(version=__version__, run_id="conflict", scenario=scene, status="failed",
                    quality_policy_sha256=policy_hash(None), run_epoch_monotonic_s=100.0, elapsed_s=1.0))
                save_json(run / "scenario.json", scene)
                (run / "events.jsonl").write_text("", encoding="utf-8")
                output, _, _ = analyze_run(run)
                # Recompute both hashes deliberately: content hashes alone cannot
                # detect a producer that wrote mutually inconsistent version claims.
                value = json.loads((output / filename).read_text(encoding="utf-8"))
                mutate(value)
                save_json(output / filename, value)
                manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
                manifest["artifact_sha256"][filename] = file_hash(output / filename)
                save_json(output / "manifest.json", manifest)
                save_json(run / "analysis_latest.json", dict(directory=output.name,
                    manifest_sha256=file_hash(output / "manifest.json")))
                with self.assertRaisesRegex(ValueError, "inconsistent semantic protocol"):
                    load_episode(output)
                with self.assertRaisesRegex(ValueError, "inconsistent semantic protocol"):
                    build_dataset([run], Path(temp) / "export")
                self.assertFalse((Path(temp) / "export").exists())
                with self.assertRaisesRegex(ValueError, "inconsistent semantic protocol"):
                    batch._verify_result(run, scene, policy_hash(None))


class BatchResumeTests(unittest.TestCase):
    def setup_bundle(self, root, count=2):
        generated = root / "generated"
        generate(profile(count), generated)
        binary, parameters = root / "binary", root / "parameters"
        binary.write_bytes(b"test executable, not launched")
        parameters.write_bytes(b"test parameters")
        return dict(mission_list_path=generated / "mission_list.json", binary=binary, parameters=parameters)

    def test_b03_success_skipped_after_validation_and_interrupted_attempt_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.setup_bundle(Path(temp))
            calls = 0

            def interrupted_second(*positional, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise KeyboardInterrupt()
                return fake_run(*positional, **kwargs)

            with patch.object(batch, "run_scene", side_effect=interrupted_second):
                first = batch.run_mission_list(**args, max_runs=2)
            self.assertEqual([m["status"] for m in first["missions"]], ["succeeded", "interrupted"])
            with patch.object(batch, "run_scene", side_effect=fake_run) as run:
                result = batch.run_mission_list(**args, resume=True, max_runs=2)
            self.assertEqual(run.call_count, 1)
            self.assertEqual([len(m["attempts"]) for m in result["missions"]], [1, 2])
            old, new = result["missions"][1]["attempts"]
            self.assertNotEqual(old["attempt_id"], new["attempt_id"])
            self.assertEqual(old["family_id"], new["family_id"])
            self.assertEqual(old["task_sha256"], new["task_sha256"])
            self.assertTrue(Path(old["attempt_directory"]).is_dir())

    def test_b04_corrupted_success_never_silently_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.setup_bundle(Path(temp), 1)
            with patch.object(batch, "run_scene", side_effect=fake_run):
                ledger = batch.run_mission_list(**args, max_runs=1)
            attempt = ledger["missions"][0]["attempts"][0]
            (Path(attempt["run_directory"]) / "analysis_test/labels.json").write_text("{}", encoding="utf-8")
            with patch.object(batch, "run_scene") as run, self.assertRaisesRegex(ValueError, "artifact changed"):
                batch.run_mission_list(**args, resume=True)
            run.assert_not_called()

    def test_b04_running_directory_without_evidence_is_recovered_not_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.setup_bundle(Path(temp), 1)
            with patch.object(batch, "run_scene", side_effect=KeyboardInterrupt):
                batch.run_mission_list(**args, max_runs=1)
            ledger_path = args["mission_list_path"].parent / "execution/attempt_ledger.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger["missions"][0]["status"] = "running"
            ledger["missions"][0]["attempts"][0]["status"] = "running"
            save_json(ledger_path, ledger)
            with patch.object(batch, "run_scene", side_effect=fake_run) as run:
                result = batch.run_mission_list(**args, resume=True, max_runs=1)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(len(result["missions"][0]["attempts"]), 2)
            self.assertTrue(result["missions"][0]["attempts"][0]["recovered"])

    def test_policy_config_change_rejected_and_semantic_failure_not_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.setup_bundle(Path(temp), 1)
            with patch.object(batch, "run_scene", side_effect=lambda *p, **kw: fake_run(*p, **kw, success=False)):
                ledger = batch.run_mission_list(**args, max_runs=3)
            self.assertEqual(ledger["missions"][0]["status"], "semantic_failed")
            with patch.object(batch, "run_scene") as run:
                batch.run_mission_list(**args, resume=True, max_runs=3)
            run.assert_not_called()
            with self.assertRaisesRegex(ValueError, "configuration changed"):
                batch.run_mission_list(**args, resume=True, quality_policy=dict(clock_acceptable_p95_s=.06))
            with self.assertRaisesRegex(ValueError, "max_runs"):
                batch.run_mission_list(**args, max_runs=100)

    def test_b03_recovery_uses_frozen_analysis_not_new_latest_pointer(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.setup_bundle(Path(temp), 1)
            with patch.object(batch, "run_scene", side_effect=fake_run):
                ledger = batch.run_mission_list(**args, max_runs=1)
            run_root = Path(ledger["missions"][0]["attempts"][0]["run_directory"])
            save_json(run_root / "analysis_latest.json", dict(directory="nonexistent", manifest_sha256="invalid"))
            with patch.object(batch, "run_scene") as run:
                result = batch.run_mission_list(**args, resume=True, max_runs=1)
            self.assertEqual(result["last_invocation"]["launched_attempts"], 0)
            run.assert_not_called()

    def test_only_configured_environment_failure_retries_with_new_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.setup_bundle(Path(temp), 1)

            def failure(*positional, **kwargs):
                return fake_run(*positional, **kwargs, status="failed", success=None,
                                error="OSError: [WinError 10048] address already in use")

            with patch.object(batch, "run_scene", side_effect=failure) as run:
                ledger = batch.run_mission_list(**args, max_runs=10, max_environment_retries=1,
                                               retryable_errors=("port_unavailable",))
            self.assertEqual(run.call_count, 2)
            attempts = ledger["missions"][0]["attempts"]
            self.assertEqual(len(attempts), 2)
            self.assertNotEqual(attempts[0]["attempt_id"], attempts[1]["attempt_id"])
            self.assertEqual(attempts[0]["family_id"], attempts[1]["family_id"])

    def test_selected_subset_keeps_list_order_and_requires_same_resume_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.setup_bundle(Path(temp), 4)
            selected = ["recon_0003_v00", "recon_0001_v00"]
            with patch.object(batch, "run_scene", side_effect=fake_run) as run:
                ledger = batch.run_mission_list(**args, mission_ids=selected, max_runs=1)
            self.assertEqual(run.call_count, 1)
            self.assertEqual([m["mission_id"] for m in ledger["missions"]], ["recon_0001_v00", "recon_0003_v00"])
            self.assertEqual(ledger["execution_context"]["selected_mission_ids"], ["recon_0001_v00", "recon_0003_v00"])
            with patch.object(batch, "run_scene", side_effect=fake_run) as run:
                resumed = batch.run_mission_list(**args, mission_ids=list(reversed(selected)), resume=True, max_runs=1)
            self.assertEqual(run.call_count, 1)
            self.assertTrue(all(m["status"] == "succeeded" for m in resumed["missions"]))
            with patch.object(batch, "run_scene") as run, self.assertRaisesRegex(ValueError, "configuration changed"):
                batch.run_mission_list(**args, mission_ids=["recon_0001_v00"], resume=True)
            run.assert_not_called()
            with self.assertRaisesRegex(ValueError, "configuration changed"):
                batch.run_mission_list(**args, resume=True)

    def test_selection_rejects_unknown_duplicate_and_empty_ids_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.setup_bundle(Path(temp), 1)
            for selection in (["unknown"], ["recon_0000_v00", "recon_0000_v00"], [], "recon_0000_v00"):
                with self.subTest(selection=selection), patch.object(batch, "run_scene") as run, self.assertRaises(ValueError):
                    batch.run_mission_list(**args, mission_ids=selection)
                run.assert_not_called()
            self.assertFalse((args["mission_list_path"].parent / "execution").exists())


if __name__ == "__main__":
    unittest.main()
