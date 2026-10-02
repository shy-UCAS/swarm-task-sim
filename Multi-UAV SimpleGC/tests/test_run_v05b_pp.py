"""Offline PP controller tests. They never launch SITL or create a pilot."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_v05b_pp as pp
from swarm_sim.generation import canonical_hash, file_hash
from swarm_sim.generation_v2 import normalize_profile


class PilotControllerTests(unittest.TestCase):
    def control(self, records=None):
        return dict(version=pp.VERSION, max_attempts=pp.MAX_ATTEMPTS,
                    stopped_reason=None, completed=False,
                    active_attempt=None, records=records or [])

    def test_hd_contract_and_hold_only_profile_derivation(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifests = {}
            records = []
            for case in ("VP1", "VP4"):
                run = directory / case
                analysis = run / "analysis"
                analysis.mkdir(parents=True)
                manifest = analysis / "manifest.json"
                manifest.write_text('{"schema_version": 3}', encoding="utf-8")
                digest = file_hash(manifest)
                (run / "analysis_latest.json").write_text(json.dumps({
                    "directory": "analysis", "manifest_sha256": digest}), encoding="utf-8")
                manifests[case] = manifest
                records.append(dict(case_id=case, individual_pass=True,
                                    retryable_pre_takeoff=False, run_directory=str(run.resolve()),
                                    evidence_sha256={str(manifest.resolve()): digest}))
            validation = dict(completed=True, stopped_reason=None, active_attempt=None,
                              aggregate_av1={intent: {"pass": True} for intent in pp.INTENT_ORDER},
                              profile_file_sha256=file_hash(pp.DR_PROFILE),
                              profile_canonical_sha256=canonical_hash(normalize_profile(pp.DR_PROFILE)),
                              source_review_sha256=file_hash(pp.DR_REVIEW), records=records)
            control_file = directory / "control.json"
            control_file.write_text(json.dumps(validation), encoding="utf-8")
            file = directory / "hd.json"
            conditions = dict(onboard_terminal_prm1_is_one=True,
                              vp4_stopped_fraction_and_improvement=True,
                              vp4_elapsed_within_ten_percent=True,
                              vp4_all_av_pass=True)
            hd = dict(pass_=True, validation_completed=True, terminal_hold_s=1,
                      controller_sha256=file_hash(control_file),
                      profile_canonical_sha256=validation["profile_canonical_sha256"],
                      source_review_sha256=validation["source_review_sha256"],
                      evidence_sha256={case: file_hash(manifest) for case, manifest in manifests.items()},
                      evidence_paths={case: str(manifest) for case, manifest in manifests.items()},
                      conditions=conditions,
                      vp1={"run_directory": records[0]["run_directory"]},
                      vp4={"run_directory": records[1]["run_directory"]})
            hd["pass"] = hd.pop("pass_")
            file.write_text(json.dumps(hd), encoding="utf-8")
            self.assertEqual(pp._hd_check(file)[1], 1)
            hd["evidence_sha256"].pop("VP4")
            file.write_text(json.dumps(hd), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fingerprints"):
                pp._hd_check(file)
            hd["evidence_sha256"]["VP4"] = file_hash(manifests["VP4"])
            hd["controller_sha256"] = "0" * 64
            file.write_text(json.dumps(hd), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "validation/profile/review"):
                pp._hd_check(file)
            hd["controller_sha256"] = file_hash(control_file)
            hd["evidence_sha256"]["VP1"] = "0" * 64
            file.write_text(json.dumps(hd), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "analysis manifest"):
                pp._hd_check(file)
            hd["evidence_sha256"]["VP1"] = file_hash(manifests["VP1"])
            hd["terminal_hold_s"] = 0
            file.write_text(json.dumps(hd), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "four registered conditions"):
                pp._hd_check(file)
            hd["conditions"]["vp4_elapsed_within_ten_percent"] = False
            file.write_text(json.dumps(hd), encoding="utf-8")
            self.assertEqual(pp._hd_check(file)[1], 0)
        source = normalize_profile(pp.DR_PROFILE)
        formal = copy.deepcopy(source)
        for mission in formal["missions"]:
            mission["template_spec"]["execution"]["terminal_hold_s"] = 1.0
        pp._profiles_equal_except_hold(source, formal, 1)
        formal["shared_mission_params"]["speeds_m_s"] = [2.0]
        with self.assertRaisesRegex(ValueError, "beyond terminal_hold_s"):
            pp._profiles_equal_except_hold(source, formal, 1)

    def test_retry_limits_and_order(self):
        self.assertEqual(pp.next_mission(self.control()), (0, 0))
        first = dict(logical_index=0, mission_id="m0", intent="reconnaissance",
                     retryable_pre_takeoff=True, attempt_index=0)
        self.assertEqual(pp.next_mission(self.control([first])), (0, 1))
        terminal = dict(first, retryable_pre_takeoff=False, attempt_index=1,
                        qualified=True, mission_success=True)
        self.assertEqual(pp.next_mission(self.control([first, terminal])), (1, 0))
        second_retry = dict(first, retryable_pre_takeoff=True, attempt_index=1)
        with self.assertRaisesRegex(ValueError, "retry budget"):
            pp.next_mission(self.control([first, second_retry]))

    def test_rolling_unknown_and_terminal_quality_denominators(self):
        records = [
            dict(logical_index=0, attempt_index=0, mission_id="r0",
                 intent="reconnaissance", qualified=False,
                 retryable_pre_takeoff=True, timing_unknown=False),
            dict(logical_index=0, attempt_index=1, mission_id="r0",
                 intent="reconnaissance", qualified=True, accepted_for_pp=True, mission_success=True,
                 retryable_pre_takeoff=False, timing_unknown=False),
            dict(logical_index=1, attempt_index=0, mission_id="p0",
                 intent="patrol", qualified=True, accepted_for_pp=False, mission_success=False,
                 retryable_pre_takeoff=False, timing_unknown=True),
        ]
        aggregate = pp.aggregate_status(records)
        self.assertEqual(aggregate["attempts"], 3)
        self.assertEqual(aggregate["logical_completed"], 2)
        self.assertEqual(aggregate["qualified"], 2)
        self.assertEqual(aggregate["pair_qualified"], 1)
        self.assertEqual(aggregate["accepted_for_pp"], 1)
        self.assertEqual(aggregate["pair_accepted_for_pp"], 0)
        self.assertEqual(aggregate["by_intent"]["patrol"]["success_fraction_given_quality"], 0.0)
        self.assertIsNone(aggregate["by_intent"]["patrol"]["success_fraction_given_pp_acceptance"])
        self.assertTrue(pp.rolling_unknown(records)["stop"])

    def test_ac4_violation_is_hard_stop_but_unknown_is_separate(self):
        scene = {"vehicles": [{"id": "uav_01"}], "min_separation_m": 5.0,
                 "phases": [{"name": "p00_approach"}]}
        control = {"firmware": {"sha256": "f", "version_string": "1"},
                   "parameters_sha256": "p"}
        metadata = {"status": "completed",
                    "run_provenance": {"status": "verified_before_takeoff",
                                       "parameter_comparison_version": pp.PARAMETER_COMPARISON_VERSION,
                                       "parameter_evidence": {"per_agent": {
                                           "uav_01": {"complete": True, "status": "complete",
                                                      "received_count": 1, "parameter_count": 1,
                                                      "missing_indices": []}}}},
                    "parameter_comparison_version": pp.PARAMETER_COMPARISON_VERSION,
                    "binary_firmware": {"sha256": "f", "version_string": "1"},
                    "parameters_sha256": "p"}
        primary = {"D_s": 4.0, "tau_s": 3.0, "complete": True}
        phase = {"primary": primary, "crosscheck": dict(primary),
                 "within_tau": False, "crosscheck_within_tau": False,
                 "complete": True}
        channel = {"per_phase": {"p00_approach": phase}, "complete": True,
                   "within_tau": False, "crosscheck_within_tau": False}
        artifacts = {"quality": {"episode_quality_eligible": True,
                                 "truth_separation": {"minimum_m": 7.0}},
                     "labels": {"mission_success": True, "semantic_consistency": "agree"},
                     "ac4_timing_v3": {"channels": {"truth": channel, "observation": channel}},
                     "onboard_mission_param_check": {"required": True, "pass_gate": True,
                                                       "status": "pass"}}
        failed = pp.assess_run(scene, metadata, artifacts, control)
        self.assertIn("AC4 v3 phase D exceeds tau", failed["hard_failures"])
        self.assertTrue(failed["qualified"])
        self.assertFalse(failed["accepted_for_pp"])
        primary["D_s"] = None
        phase["crosscheck"]["D_s"] = None
        phase["within_tau"] = None
        phase["crosscheck_within_tau"] = None
        channel["within_tau"] = None
        channel["crosscheck_within_tau"] = None
        unknown = pp.assess_run(scene, metadata, artifacts, control)
        self.assertTrue(unknown["timing_unknown"])
        self.assertTrue(unknown["qualified"])
        self.assertFalse(unknown["accepted_for_pp"])
        self.assertNotIn("AC4 v3 phase D exceeds tau", unknown["hard_failures"])
        primary["D_s"] = 2.0
        phase["crosscheck"]["D_s"] = 2.0
        phase["within_tau"] = True
        phase["crosscheck_within_tau"] = True
        channel["within_tau"] = True
        channel["crosscheck_within_tau"] = None
        top_unknown = pp.assess_run(scene, metadata, artifacts, control)
        self.assertTrue(top_unknown["timing_unknown"])
        self.assertFalse(top_unknown["accepted_for_pp"])
        channel["crosscheck_within_tau"] = True
        clear = pp.assess_run(scene, metadata, artifacts, control)
        self.assertEqual(clear["timing_status"], "within_tau")
        self.assertTrue(clear["accepted_for_pp"])
        artifacts["onboard_mission_param_check"].update(status="unknown", pass_gate=False)
        onboard_unknown = pp.assess_run(scene, metadata, artifacts, control)
        self.assertFalse(onboard_unknown["accepted_for_pp"])
        self.assertFalse(onboard_unknown["hard_failures"])
        artifacts["onboard_mission_param_check"].update(status="mismatch")
        onboard_mismatch = pp.assess_run(scene, metadata, artifacts, control)
        self.assertIn("onboard mission parameter mismatch", onboard_mismatch["hard_failures"])
        artifacts["onboard_mission_param_check"].update(status="pass", pass_gate=True)
        artifacts["quality"]["truth_separation"]["minimum_m"] = None
        separation_unknown = pp.assess_run(scene, metadata, artifacts, control)
        self.assertFalse(separation_unknown["accepted_for_pp"])
        self.assertFalse(separation_unknown["hard_failures"])
        no_analysis = pp.assess_run(scene, metadata, None, control)
        self.assertTrue(no_analysis["timing_unknown"])
        self.assertFalse(no_analysis["accepted_for_pp"])
        self.assertFalse(no_analysis["hard_failures"])
        bad_metadata = copy.deepcopy(metadata)
        bad_metadata["binary_firmware"]["sha256"] = "wrong"
        no_analysis_bad_firmware = pp.assess_run(scene, bad_metadata, None, control)
        self.assertIn("parameter/firmware/readback gate failed",
                      no_analysis_bad_firmware["hard_failures"])

    def test_post_run_frozen_integrity_detects_input_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "frozen.json"
            file.write_text('{"a": 1}', encoding="utf-8")
            control = {"frozen_sha256": {str(file): file_hash(file)}}
            with patch.object(pp, "assert_protected", return_value=1):
                pp.assert_post_run_integrity(control)
                file.write_text('{"a": 2}', encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "frozen PP input/evidence changed"):
                    pp.assert_post_run_integrity(control)

    def test_final_gates_retain_raw_success_denominator_and_reject_unknown(self):
        aggregate = dict(logical_completed=20, qualified=20, pair_qualified=10,
                         accepted_for_pp=17, pair_accepted_for_pp=8,
                         by_intent={intent: {"success_fraction_given_quality": .9,
                                             "success_fraction_given_pp_acceptance": 1.0}
                                    for intent in pp.INTENT_ORDER})
        episodes = {"episodes": [{} for _ in range(20)]}
        loaded = [{"corner_count": 4, "corner_dimensions": [2, 2, 2, 2]}
                  for _ in range(20)]
        args = (episodes, {"issues": []}, {"consistency_pass": True}, loaded)
        gates = pp.pilot_acceptance_gates(aggregate, *args)
        self.assertTrue(gates["episode_quality_18_of_20"])
        self.assertFalse(gates["strict_accepted_18_of_20"])
        self.assertFalse(gates["paired_strict_accepted_9_of_10"])
        self.assertFalse(gates["pass"])
        aggregate["accepted_for_pp"] = 18
        aggregate["pair_accepted_for_pp"] = 9
        aggregate["by_intent"]["patrol"]["success_fraction_given_quality"] = .89
        gates = pp.pilot_acceptance_gates(aggregate, *args)
        self.assertFalse(gates["patrol_success_given_quality"])
        self.assertFalse(gates["pass"])
        aggregate["by_intent"]["patrol"]["success_fraction_given_quality"] = .90
        self.assertTrue(pp.pilot_acceptance_gates(aggregate, *args)["pass"])


if __name__ == "__main__":
    unittest.main()
