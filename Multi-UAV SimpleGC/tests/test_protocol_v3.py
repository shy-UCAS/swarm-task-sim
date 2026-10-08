import copy
import json
import tempfile
import unittest
from pathlib import Path

from swarm_sim.dataset import build_dataset
from swarm_sim.episode_loader import load_episode
from swarm_sim.protocol import PROTOCOL_FIELDS, semantic_protocol
from swarm_sim.quality import eligibility, episode_quality_eligibility, invalid_intervals, v3_eligibility
from swarm_sim.registry import registered_intents, temporary_registration
from swarm_sim.recording import write_json
from v3_artifact_fixture import fixture_intent, make_run, rehash
import test_mission_data as legacy_fixture

class ProtocolV3Tests(unittest.TestCase):
    def test_g08_protocol_versions_are_distinct_but_intent_mode_are_not_axes(self):
        old=semantic_protocol(dict(task_spec=dict(schema_version=2)))
        new=semantic_protocol(dict(task_spec=dict(schema_version=3)))
        self.assertTrue(all(old[k]!=new[k] for k in PROTOCOL_FIELDS))
        self.assertNotIn("control_mode",new)
        self.assertNotIn("intent",new)

    def test_g08_two_test_intents_share_dataset_and_family_split(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_registration(fixture_intent()):
            root=Path(tmp)
            a,_=make_run(root/"a")
            b,_=make_run(root/"b",intent="test_fixture")
            data=build_dataset([a,b],root/"dataset")
            self.assertEqual(data["counts"]["total"],2)
            self.assertEqual(data["counts"]["episode_quality_eligible"],2)
            self.assertEqual(data["counts"]["eligible"],0)
            self.assertEqual(len({e["family_id"] for e in data["episodes"]}),1)
            self.assertEqual(len({e["split"] for e in data["episodes"]}),1)
            for entry in data["episodes"]:
                loaded=load_episode(root/"dataset"/entry["directory"])
                self.assertEqual(len(loaded["x"][0][0]),6)
                self.assertNotIn(999,loaded["x"][0][0])
                self.assertTrue(loaded["metadata"]["episode_quality_eligible"])
                self.assertFalse(loaded["metadata"]["mission_success"])
        self.assertEqual(registered_intents(),("patrol", "rapid_passage", "reconnaissance"))

    def test_g08_mixed_control_modes_explicit_and_tamper_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); a,_=make_run(root/"a"); b,_=make_run(root/"b",mode="semantic_phase_route_v1")
            with self.assertRaisesRegex(ValueError,"mixed control_mode"):
                build_dataset([a,b],root/"rejected")
            self.assertFalse((root/"rejected").exists())
            data=build_dataset([a,b],root/"accepted",allow_mixed_control_modes=True)
            self.assertTrue(data["mixed_control_modes"])
            self.assertTrue(data["allow_mixed_control_modes"])
            episode=root/"accepted"/data["episodes"][0]["directory"]
            load_episode(episode)
            data["allow_mixed_control_modes"]=False
            write_json(root/"accepted/dataset_manifest.json",data)
            with self.assertRaisesRegex(ValueError,"without explicit permission"): load_episode(episode)

    def test_g08_mixed_v2_v3_protocol_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); a,_=make_run(root/"a")
            b=root/"b"; ep=b/"analysis_fixture"
            legacy_fixture.make_episode(ep)
            manifest=json.loads((ep/"manifest.json").read_text())
            manifest.update(run_id="b",scenario_id="b",clock_quality=dict(overall="acceptable"),
                            analysis_version="0.3.0",run_status="completed",source_sha256={})
            write_json(ep/"manifest.json",manifest); rehash(b)
            with self.assertRaisesRegex(ValueError,"incompatible semantic"):
                build_dataset([a,b],root/"dataset")

    def test_processing_and_validator_versions_checked_even_after_rehash(self):
        for artifact,key,value in (("quality.json","clock_model_version","wrong"),
                                   ("manifest.json","timeline_policy_version","window_only"),
                                   ("labels.json","label_provenance",{})):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                run,ep=make_run(Path(tmp)/"run")
                data=json.loads((ep/artifact).read_text()); data[key]=value; write_json(ep/artifact,data); rehash(run)
                with self.assertRaises(ValueError): load_episode(ep)

    def test_g09_outcome_and_consistency_do_not_control_episode_quality(self):
        quality=dict(run_completed=True,data_quality_pass=True,truth_available_pass=True,timing_diagnostic_pass=True,
                     execution_constraints_pass=True,clock_quality=dict(overall="acceptable"),
                     separation_status="clear_observed",truth_separation=dict(status="clear_observed"))
        for success in (True,False,None):
            for consistency in ("agree","disagree","unknown"):
                data=dict(quality,mission_success=success,semantic_consistency=consistency)
                self.assertTrue(episode_quality_eligibility(data))
                self.assertEqual(eligibility(data,success)["benchmark_eligible"],success is True)
                combined=v3_eligibility(data,dict(mission_success=success,semantic_consistency=consistency,
                                                 mission_success_observation=success))
                self.assertTrue(combined["episode_quality_eligible"])
                self.assertEqual(combined["benchmark_eligible"],success is True and consistency=="agree")
        for key in ("run_completed","data_quality_pass","truth_available_pass","timing_diagnostic_pass","execution_constraints_pass"):
            with self.subTest(key=key): self.assertFalse(episode_quality_eligibility(dict(quality,**{key:False})))

    def test_invalid_intervals_preserve_invalid_samples_gaps_and_quality_flags(self):
        row=[0,0,8,1,0,0]
        traces={"a":[(0,row),(.1,None),(.2,None),(.3,row),(1,row)]}
        result=invalid_intervals(traces,.15,{"a":{.3:"out_of_bounds"}})["a"]
        self.assertEqual(result,[dict(start_s=.1,end_s=.2,reason="invalid_observation"),
                                 dict(start_s=.3,end_s=.3,reason="out_of_bounds"),dict(start_s=.3,end_s=1,reason="sample_gap")])
        with self.assertRaises(ValueError): invalid_intervals({"a":[(0,row),(0,row)]},.15)

    def test_false_eligibility_claim_rejected_after_valid_hash_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            run,ep=make_run(Path(tmp)/"run")
            quality=json.loads((ep/"quality.json").read_text())
            quality["data_quality_pass"]=False
            write_json(ep/"quality.json",quality); rehash(run)
            with self.assertRaisesRegex(ValueError,"eligibility contradicts"): load_episode(ep)

    def test_v3_completion_agent_set_and_clock_evidence_must_agree_after_rehash(self):
        cases = [
            ("manifest.json", "run_status", "failed", "run completion"),
            ("manifest.json", "agent_ids", ["uav_01"], "agent identities"),
            ("manifest.json", "agent_ids", ["uav_01", "uav_01", "uav_02", "uav_03"], "agent identities"),
            ("manifest.json", "clock_quality", {"overall": "strict"}, "clock quality"),
            ("quality.json", "observation_valid_fraction", {"uav_01": 1.0}, "per-agent quality"),
            ("quality.json", "truth_valid_fraction", {"uav_01": True, "uav_02": 1.0, "uav_03": 1.0}, "per-agent quality"),
        ]
        for artifact, key, value, reason in cases:
            with self.subTest(key=key, value=value), tempfile.TemporaryDirectory() as tmp:
                run, ep = make_run(Path(tmp)/"run")
                data=json.loads((ep/artifact).read_text()); data[key]=value
                write_json(ep/artifact,data); rehash(run)
                with self.assertRaisesRegex(ValueError,reason): load_episode(ep)

    def test_v3_dataset_selection_metadata_must_match_episode(self):
        cases = [("intent", "wrong_intent"), ("mission_success", True),
                 ("semantic_consistency", "disagree"), ("run_status", "failed"),
                 ("agent_ids", ["uav_01"]), ("episode_quality_eligible", 1)]
        for key, value in cases:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); run,_=make_run(root/"run")
                dataset=build_dataset([run],root/"dataset")
                entry=dataset["episodes"][0]; entry[key]=value
                write_json(root/"dataset/dataset_manifest.json",dataset)
                with self.assertRaisesRegex(ValueError,"v3 episode metadata disagree"):
                    load_episode(root/"dataset"/entry["directory"])

if __name__=="__main__": unittest.main()
