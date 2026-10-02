"""Offline v05c HD/PP binding and budget tests; no runner is invoked."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import decide_v05c_hd as hd
from scripts import run_v05c_pp as pp
from swarm_sim.generation import canonical_hash, file_hash
from swarm_sim.generation_v2 import normalize_profile


class V05cHDTests(unittest.TestCase):
    def test_hd_rejects_other_root_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "dedicated v05c"):
                hd.decide(root)
            self.assertFalse((root / "hd_decision.json").exists())

    def test_hd_requires_six_clean_cases_with_historical_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "control.json"
            control = dict(version=hd.VALIDATION_VERSION, completed=True,
                stopped_reason=None, active_attempt=None,
                planned_cases=list(hd.CASE_ORDER),
                total_sitl_budget=hd.TOTAL_SITL_BUDGET,
                historical_attempts_consumed=hd.HISTORICAL_ATTEMPTS,
                max_attempts=hd.MAX_ATTEMPTS,
                max_extra_retries=hd.MAX_EXTRA_RETRIES,
                aggregate_av1={intent: {"pass": True} for intent in
                               ("patrol", "reconnaissance")},
                records=[dict(case_id=case, individual_pass=True,
                              retryable_pre_takeoff=False, run_status="completed",
                              flight_epoch_present=True, run_directory="fixture",
                              evidence_sha256={"fixture": "digest"})
                         for case in hd.CASE_ORDER])
            with patch.object(hd, "EXPECTED_ROOT", root):
                for mutation in (
                    lambda item: item.update(historical_attempts_consumed=0),
                    lambda item: item["records"].pop(),
                    lambda item: item["records"].append(dict(case_id="VR2",
                        individual_pass=False, retryable_pre_takeoff=False)),
                ):
                    bad = copy.deepcopy(control)
                    mutation(bad)
                    path.write_text(json.dumps(bad), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "six validation cases|seven SITL"):
                        hd.decide(root)
                    self.assertFalse((root / "hd_decision.json").exists())

    def test_only_one_proven_preflight_retry_can_extend_six_cases(self):
        records = [dict(case_id=case, individual_pass=True,
                        retryable_pre_takeoff=False, attempt_index=0,
                        run_status="completed", flight_epoch_present=True,
                        run_directory="fixture", evidence_sha256={"fixture": "digest"})
                   for case in hd.CASE_ORDER]
        self.assertTrue(hd.validation_attempts_clean(records))
        retry = dict(case_id="VP1", individual_pass=False,
                     retryable_pre_takeoff=True, attempt_index=0)
        records[0]["attempt_index"] = 1
        self.assertTrue(hd.validation_attempts_clean([retry, *records]))
        retry["case_id"] = "VP2"
        self.assertFalse(hd.validation_attempts_clean([retry, *records]))

    def test_hd_writes_bound_decision_after_six_cases(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            (bundle / "scenes").mkdir(parents=True)
            entries, records = [], []
            for case in hd.CASE_ORDER:
                scene_name = f"scenes/{case}.json"
                (bundle / scene_name).write_text(json.dumps({"max_gap_s": .5,
                    "record_hz": 10, "phases": []}), encoding="utf-8")
                entries.append(dict(validation_case_id=case, scene=scene_name))
                run = root / case
                analysis = run / "analysis"
                analysis.mkdir(parents=True)
                (analysis / "phase_windows.json").write_text("{}", encoding="utf-8")
                (run / "analysis_latest.json").write_text(json.dumps({
                    "directory": "analysis", "manifest_sha256": "a" * 64}), encoding="utf-8")
                assessment = dict(individual_pass=True, checks={"AV-6": True},
                    av6={"vp4_terminal_prm1": [dict(uploaded_param1=1,
                        onboard_param1=[1])]})
                records.append(dict(case_id=case, individual_pass=True,
                    retryable_pre_takeoff=False, run_directory=str(run),
                    run_status="completed", flight_epoch_present=True,
                    evidence_sha256={str((run / "analysis_latest.json").resolve()):
                                     file_hash(run / "analysis_latest.json")},
                    assessment=assessment))
            control = dict(version=hd.VALIDATION_VERSION, completed=True,
                stopped_reason=None, active_attempt=None,
                planned_cases=list(hd.CASE_ORDER),
                total_sitl_budget=hd.TOTAL_SITL_BUDGET,
                historical_attempts_consumed=hd.HISTORICAL_ATTEMPTS,
                max_attempts=hd.MAX_ATTEMPTS,
                max_extra_retries=hd.MAX_EXTRA_RETRIES,
                aggregate_av1={intent: {"pass": True} for intent in
                               ("patrol", "reconnaissance")},
                records=records, frozen_sha256={}, bundle=str(bundle),
                review=str(root / "review.json"), profile=str(hd.ROOT / "generation_profiles/dual_intent_v05c.json"),
                profile_file_sha256="b" * 64, profile_canonical_sha256="c" * 64,
                source_review_sha256="d" * 64,
                historical_failed_attempt={"source_control_sha256": "e" * 64})
            (root / "control.json").write_text(json.dumps(control), encoding="utf-8")
            window = [dict(phase="patrol", agent_id="uav_01")]
            fractions = [dict(window_count=1, stopped_count=0, unknown_count=0,
                              fraction=0.0, windows=window),
                         dict(window_count=1, stopped_count=1, unknown_count=0,
                              fraction=1.0, windows=window)]
            with (patch.object(hd, "EXPECTED_ROOT", root),
                  patch.object(hd, "assert_historical_binding"),
                  patch.object(hd, "assert_protected"),
                  patch.object(hd, "_bound_inputs"),
                  patch.object(hd, "verify_generation", return_value=({"missions": entries}, {})),
                  patch.object(hd, "_run_artifacts", side_effect=[({"run_id": "v1", "elapsed_s": 100}, None, None),
                                                                  ({"run_id": "v4", "elapsed_s": 105}, None, None)]),
                  patch.object(hd, "truth_rows", return_value={}),
                  patch.object(hd, "terminal_fraction", side_effect=fractions)):
                result = hd.decide(root)
            self.assertEqual(result["terminal_hold_s"], 1)
            self.assertEqual(result["total_validation_attempts"], 7)
            self.assertEqual(result["historical_v05b_control_sha256"], "e" * 64)
            self.assertTrue((root / "hd_decision.json").is_file())


class V05cPPTests(unittest.TestCase):
    def test_fixed_zero_profile_and_hold_only_derivation(self):
        source = normalize_profile(pp.DR_PROFILE)
        formal = copy.deepcopy(source)
        for mission in formal["missions"]:
            mission["template_spec"]["execution"]["terminal_hold_s"] = 1.0
        pp._profiles_equal_except_hold(source, formal, 1)
        formal["scene_sampler"]["params"].pop("heading_policy")
        with self.assertRaisesRegex(ValueError, "beyond terminal_hold_s"):
            pp._profiles_equal_except_hold(source, formal, 1)
        old = normalize_profile(pp.ROOT / "generation_profiles/dual_intent_v05b.json")
        with self.assertRaisesRegex(ValueError, "fixed-zero"):
            pp._profiles_equal_except_hold(old, old, 0)

    def test_hold1_materialization_is_new_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "v05c_hd1.json"
            generated = Path(temporary) / "generated_hd1"
            calls = []

            def fake_generate(source, output):
                calls.append((Path(source), Path(output)))
                Path(output).mkdir()

            with (patch.object(pp, "HOLD1_PROFILE", profile),
                  patch.object(pp, "HOLD1_GENERATED", generated),
                  patch.object(pp, "generate_v2", side_effect=fake_generate)):
                pp._materialize_hold1()
                digest = file_hash(profile)
                pp._materialize_hold1()
                self.assertEqual(file_hash(profile), digest)
                self.assertEqual(calls, [(profile, generated)])
                formal = normalize_profile(profile)
                self.assertEqual(formal["scene_sampler"]["params"]["heading_policy"],
                                 "fixed_zero")
                self.assertTrue(all(item["template_spec"]["execution"]["terminal_hold_s"] == 1
                                    for item in formal["missions"]))

    def test_hd_decision_requires_v05c_sources_and_historical_charge(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = pp.DR_PROFILE
            review = root / "review.json"
            review.write_text("{}", encoding="utf-8")
            bundle = root / "bundle"
            bundle.mkdir()
            records = []
            manifests = {}
            for case in pp.CASE_ORDER:
                run = root / case
                run.mkdir()
                row = dict(case_id=case, individual_pass=True,
                           retryable_pre_takeoff=False, run_directory=str(run.resolve()),
                           run_status="completed", flight_epoch_present=True,
                           evidence_sha256={str(review.resolve()): file_hash(review)})
                if case in ("VP1", "VP4"):
                    analysis = run / "analysis"
                    analysis.mkdir()
                    manifest = analysis / "manifest.json"
                    manifest.write_text("{}", encoding="utf-8")
                    digest = file_hash(manifest)
                    (run / "analysis_latest.json").write_text(json.dumps({
                        "directory": "analysis", "manifest_sha256": digest}), encoding="utf-8")
                    row["evidence_sha256"][str(manifest.resolve())] = digest
                    manifests[case] = manifest
                records.append(row)
            validation = dict(version=pp.VALIDATION_VERSION, completed=True,
                stopped_reason=None, active_attempt=None,
                planned_cases=list(pp.CASE_ORDER),
                total_sitl_budget=pp.TOTAL_SITL_BUDGET,
                historical_attempts_consumed=pp.HISTORICAL_ATTEMPTS,
                max_attempts=pp.VALIDATION_MAX_ATTEMPTS,
                max_extra_retries=pp.VALIDATION_MAX_EXTRA_RETRIES,
                aggregate_av1={intent: {"pass": True} for intent in pp.INTENT_ORDER},
                profile_file_sha256=file_hash(profile),
                profile_canonical_sha256=canonical_hash(normalize_profile(profile)),
                source_review_sha256=file_hash(review), bundle=str(bundle.resolve()),
                review=str(review.resolve()), profile=str(profile.resolve()),
                historical_failed_attempt={"source_control_sha256": "a" * 64},
                frozen_sha256={}, records=records)
            control_path = root / "control.json"
            control_path.write_text(json.dumps(validation), encoding="utf-8")
            hd_path = root / "hd_decision.json"
            conditions = dict(onboard_terminal_prm1_is_one=False,
                vp4_stopped_fraction_and_improvement=False,
                vp4_elapsed_within_ten_percent=True, vp4_all_av_pass=True)
            decision = dict(version="v05c_hd_terminal_truth_dwell_v1",
                **{"pass": True}, validation_completed=True, terminal_hold_s=0,
                controller_sha256=file_hash(control_path),
                validation_control_path=str(control_path), validation_bundle=str(bundle.resolve()),
                historical_v05b_control_sha256="a" * 64,
                total_validation_attempts=7,
                profile_file_sha256=validation["profile_file_sha256"],
                profile_canonical_sha256=validation["profile_canonical_sha256"],
                source_review_sha256=validation["source_review_sha256"],
                conditions=conditions,
                evidence_sha256={case: file_hash(path) for case, path in manifests.items()},
                evidence_paths={case: str(path) for case, path in manifests.items()},
                vp1={"run_directory": records[0]["run_directory"]},
                vp4={"run_directory": records[3]["run_directory"]})
            hd_path.write_text(json.dumps(decision), encoding="utf-8")
            with (patch.object(pp, "HD_DECISION", hd_path),
                  patch.object(pp, "EXPECTED_BUNDLE", bundle),
                  patch.object(pp, "DR_REVIEW", review),
                  patch.object(pp, "_bound_inputs"),
                  patch.object(pp, "assert_historical_binding")):
                self.assertEqual(pp._hd_check(hd_path)[1], 0)
                decision["historical_v05b_control_sha256"] = "b" * 64
                hd_path.write_text(json.dumps(decision), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "validation/profile/review"):
                    pp._hd_check(hd_path)
                decision["historical_v05b_control_sha256"] = "a" * 64
                decision["version"] = "v05b_hd_terminal_truth_dwell_v1"
                hd_path.write_text(json.dumps(decision), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "incomplete or unaccepted"):
                    pp._hd_check(hd_path)


if __name__ == "__main__":
    unittest.main()
