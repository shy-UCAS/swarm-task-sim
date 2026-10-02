"""E3 production-pipeline tests with hand-constructed telemetry, no SITL."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swarm_sim.analysis import analyze_run, digest
from swarm_sim.dataset import build_dataset
from swarm_sim.episode_loader import load_episode
from swarm_sim.mission_v3 import from_v2
from swarm_sim.observation_processing import processing_versions
from swarm_sim.recording import write_json
from swarm_sim.tasks import compile_task
import test_v03_integration as legacy_fixtures


class AnalysisV3Tests(unittest.TestCase):
    def evidence(self, root, condition="control", mutation=None, v3=True):
        helper=legacy_fixtures.FinalEligibilityTests()
        def analyze(path):
            if mutation:
                raw=path/"raw/uav_01.jsonl"
                packets=[json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines()]
                mutation(packets)
                raw.write_text("\n".join(json.dumps(p) for p in packets),encoding="utf-8")
            return analyze_run(path)
        def compiler(spec):
            return compile_task(from_v2(spec) if v3 else spec)
        with patch("test_v03_integration.compile_task",side_effect=compiler),patch("test_v03_integration.analyze_run",side_effect=analyze):
            return helper.analyze_handmade_evidence(root,condition)

    def test_e3_full_v3_analysis_exports_and_loads_versioned_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); run=root/"run"
            output,quality,labels=self.evidence(run)
            self.assertTrue(quality["episode_quality_eligible"])
            self.assertTrue(quality["benchmark_eligible"])
            self.assertEqual(labels["label_provenance"]["validator_versions"],{"reconnaissance":"shared_coverage_v2"})
            versions=processing_versions()
            for name in ("manifest.json","quality.json","semantic_validation.json","phase_windows.json","execution_metrics.json","observation_processing.json"):
                data=json.loads((output/name).read_text(encoding="utf-8"))
                self.assertEqual({key:data[key] for key in versions},versions,name)
            clocks=json.loads((output/"clock_models.json").read_text(encoding="utf-8"))
            self.assertEqual({key:clocks["uav_01"][key] for key in versions},versions)
            dataset=build_dataset([run],root/"dataset")
            loaded=load_episode(root/"dataset"/dataset["episodes"][0]["directory"])
            self.assertEqual(len(loaded["x"][0][0]),6)
            self.assertTrue(loaded["metadata"]["episode_quality_eligible"])

    def test_e3_exact_duplicates_drop_before_clock_fit_but_conflict_or_rollback_fail_full_stream(self):
        def duplicate(packets):
            packets[2:2]=copy.deepcopy(packets[:2])
        def conflict(packets):
            packet=copy.deepcopy(packets[1]); packet["message"]["vx"]=1
            packets.insert(2,packet)
        def rollback(packets):
            packets.append(copy.deepcopy(packets[1]))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            _,control,_=self.evidence(root/"control")
            output,duped,_=self.evidence(root/"duplicate",condition="duplicate",mutation=duplicate)
            self.assertTrue(duped["episode_quality_eligible"])
            self.assertEqual(duped["observation_valid_fraction"],control["observation_valid_fraction"])
            audit=json.loads((output/"observation_processing.json").read_text(encoding="utf-8"))["per_agent"]["uav_01"]
            self.assertEqual(audit["counts"]["GLOBAL_POSITION_INT"]["dropped"],1)
            self.assertEqual(audit["counts"]["SYSTEM_TIME"]["dropped"],1)
            for name,mutator in (("conflict",conflict),("rollback",rollback)):
                with self.subTest(case=name):
                    _,quality,_=self.evidence(root/name,condition=name,mutation=mutator)
                    self.assertFalse(quality["episode_quality_eligible"])
                    self.assertEqual(quality["observation_valid_fraction"]["uav_01"],0)

    def test_e3_failed_quality_retained_with_mission_result_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); run=root/"run"
            _,quality,labels=self.evidence(run,condition="missing")
            self.assertTrue(labels["mission_success"])
            self.assertFalse(quality["episode_quality_eligible"])
            self.assertFalse(quality["benchmark_eligible"])
            result=build_dataset([run],root/"dataset")
            self.assertEqual(result["counts"]["total"],1)
            self.assertEqual(result["counts"]["episode_quality_eligible"],0)

    def test_e3_v2_before_and_after_optional_metrics_mix_without_protocol_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            old_run,new_run=root/"old",root/"new"
            old,_,_=self.evidence(old_run,condition="before",v3=False)
            new,_,_=self.evidence(new_run,condition="after",v3=False)
            # A synthetic pre-WP-G v2 episode omits only the optional diagnostic
            # attachment and carries its original analysis version. No sources
            # or privileged features are rewritten to make a different protocol.
            (old/"execution_metrics.json").unlink()
            manifest=json.loads((old/"manifest.json").read_text(encoding="utf-8"))
            manifest["artifact_sha256"].pop("execution_metrics.json")
            manifest["analysis_version"]="0.3.0"
            write_json(old/"manifest.json",manifest)
            write_json(old_run/"analysis_latest.json",dict(directory=old.name,manifest_sha256=digest(old/"manifest.json")))
            expected=load_episode(old)
            dataset=build_dataset([old_run,new_run],root/"mixed")
            self.assertEqual(dataset["counts"]["total"],2)
            episodes={e["run_id"]:root/"mixed"/e["directory"] for e in dataset["episodes"]}
            a,b=load_episode(episodes["before"]),load_episode(episodes["after"])
            self.assertEqual(a["x"],b["x"])
            self.assertEqual(a["mask"],expected["mask"])
            self.assertEqual(a["targets"]["mission_success"],b["targets"]["mission_success"])
            self.assertFalse((episodes["before"]/"execution_metrics.json").exists())
            self.assertTrue((episodes["after"]/"execution_metrics.json").exists())

    def test_e3_contradictory_scenario_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"run"; self.evidence(root)
            pointer=(root/"analysis_latest.json").read_bytes(); directories=set(root.glob("analysis_*"))
            data=json.loads((root/"scenario.json").read_text(encoding="utf-8")); data["scenario_id"]="contradictory"
            write_json(root/"scenario.json",data)
            with self.assertRaisesRegex(ValueError,"scenario.json differs"): analyze_run(root)
            self.assertEqual((root/"analysis_latest.json").read_bytes(),pointer)
            self.assertEqual(set(root.glob("analysis_*")),directories)

    def test_e3_schema2_failed_before_takeoff_keeps_unknown_evidence_and_exports(self):
        project=Path(__file__).resolve().parents[1]
        task=json.loads((project/"missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8"))
        scene=compile_task(task)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); run=root/"failed"; run.mkdir()
            write_json(run/"scenario.json",scene)
            write_json(run/"metadata.json",dict(version="0.4.0-dev",run_id="failed_route",scenario=scene,
                       status="failed",run_epoch_monotonic_s=100,elapsed_s=.1))
            (run/"events.jsonl").write_text("",encoding="utf-8")
            output,quality,labels=analyze_run(run)
            self.assertFalse(quality["episode_quality_eligible"])
            self.assertIsNone(labels["mission_success"])
            windows=json.loads((output/"phase_windows.json").read_text(encoding="utf-8"))
            self.assertEqual(windows["schema_version"],2)
            self.assertEqual(set(windows["channels"]),{"truth","observation"})
            self.assertTrue(all(w["arrival_s"] is None for w in windows["windows"]))
            metrics=json.loads((output/"execution_metrics.json").read_text(encoding="utf-8"))
            self.assertIsNone(metrics["nominal_timing_deviation_s"]["assessment"]["within_tau"])
            dataset=build_dataset([run],root/"dataset")
            loaded=load_episode(root/"dataset"/dataset["episodes"][0]["directory"])
            self.assertFalse(any(any(mask) for mask in loaded["mask"]))

    def test_e3_cross_artifact_processing_versions_rejected_after_rehash(self):
        with tempfile.TemporaryDirectory() as temp:
            output,_,_=self.evidence(Path(temp)/"run")
            baseline_manifest=json.loads((output/"manifest.json").read_text(encoding="utf-8"))
            for name in ("semantic_validation.json","phase_windows.json","execution_constraints.json",
                         "execution_metrics.json","observation_processing.json","clock_models.json",
                         "lifecycle_clock_models.json","labels.json"):
                with self.subTest(artifact=name):
                    path=output/name; saved=path.read_bytes(); artifact=json.loads(saved)
                    target=artifact["uav_01"] if "clock_models" in name else artifact["label_provenance"] if name=="labels.json" else artifact
                    target["timeline_policy_version"]="window_only_invalid_policy"
                    write_json(path,artifact)
                    manifest=copy.deepcopy(baseline_manifest); manifest["artifact_sha256"][name]=digest(path)
                    write_json(output/"manifest.json",manifest)
                    with self.assertRaisesRegex(ValueError,"processing versions"): load_episode(output)
                    path.write_bytes(saved)
            write_json(output/"manifest.json",baseline_manifest)

    def test_e3_future_release_after_timeout_exports_explicit_empty_nonnegative_window(self):
        project=Path(__file__).resolve().parents[1]
        task=json.loads((project/"missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8"))
        scene=compile_task(task)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); run=root/"timeout_before_release"; run.mkdir()
            metadata=dict(version="0.4.0-dev",run_id="future_release",scenario=scene,status="failed",
                run_epoch_monotonic_s=100.,elapsed_s=.03,flight_epoch_monotonic_s=100.3)
            write_json(run/"scenario.json",scene)
            write_json(run/"metadata.json",metadata)
            original=(run/"metadata.json").read_bytes()
            (run/"events.jsonl").write_text(json.dumps(dict(event="phase_release_scheduled",phase="p00_approach",
                t=0.,release_t=.3))+"\n"+json.dumps(dict(event="run_failed",t=.03,error="phase timeout")),encoding="utf-8")
            output,quality,labels=analyze_run(run)
            manifest=json.loads((output/"manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["duration_s"],0.)
            self.assertTrue(manifest["partial_window"])
            self.assertEqual(manifest["observation_window"],quality["observation_window"])
            window=manifest["observation_window"]
            self.assertEqual(window["status"],"not_started")
            self.assertEqual(window["reason"],"scheduled_release_after_run_end")
            self.assertEqual(window["recorded_lifecycle_end_host_s"],100.03)
            self.assertEqual(window["effective_start_host_s"],window["effective_end_host_s"])
            self.assertEqual(quality["frames"],0)
            self.assertFalse(quality["episode_quality_eligible"])
            self.assertFalse(quality["benchmark_eligible"])
            self.assertIsNone(labels["mission_success"])
            self.assertEqual(len((output/"observations.csv").read_text(encoding="utf-8").splitlines()),1)
            self.assertEqual((run/"metadata.json").read_bytes(),original)
            dataset=build_dataset([run],root/"dataset")
            loaded=load_episode(root/"dataset"/dataset["episodes"][0]["directory"])
            self.assertEqual(loaded["x"],[])
            self.assertEqual(loaded["mask"],[])
            self.assertFalse(loaded["metadata"]["episode_quality_eligible"])

    def test_e3_explicit_mission_end_before_flight_epoch_is_rejected_before_export(self):
        project=Path(__file__).resolve().parents[1]
        task=json.loads((project/"missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8"))
        scene=compile_task(task)
        with tempfile.TemporaryDirectory() as temp:
            run=Path(temp)
            write_json(run/"metadata.json",dict(version="0.4.0-dev",run_id="invalid_bounds",scenario=scene,status="failed",
                run_epoch_monotonic_s=100.,elapsed_s=5.,flight_epoch_monotonic_s=102.,mission_end_monotonic_s=101.))
            with self.assertRaisesRegex(ValueError,"mission end contradicts"):
                analyze_run(run)
            self.assertFalse(list(run.glob("analysis_*")))


if __name__=="__main__": unittest.main()
