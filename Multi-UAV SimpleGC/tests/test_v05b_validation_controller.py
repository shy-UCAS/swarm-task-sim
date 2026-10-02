"""Offline validation-controller gates; no test starts SITL."""

import copy
import unittest

from scripts.run_v05b_validation import (CASE_ORDER, VERSION, aggregate_av1,
    assess_run, next_case, preflight_retry_reason)


def retry_reason(metadata, parameters, events=None):
    return preflight_retry_reason(metadata, parameters,
        [dict(event="run_failed"), *(events or [])])


def fixture(case_id="VP1"):
    agents = ["uav_01", "uav_02"]
    phases = [dict(name="approach", semantic_phase="approach",
                   routes={agent: [dict(east_m=10, north_m=0, up_m=5)] for agent in agents}),
              dict(name="patrol", semantic_phase="patrol",
                   routes={agent: [dict(east_m=20, north_m=0, up_m=5)] for agent in agents})]
    scene = dict(vehicles=[dict(id=agent) for agent in agents], phases=phases,
        min_separation_m=5, task_spec=dict(mission=dict(intent="patrol", intent_params=dict(laps=2))),
        semantic_plan=dict(execution_phases={phase["name"]: dict(agents={agent: dict(
            start_point=dict(east_m=0 if phase["name"] == "approach" else 10,
                             north_m=0, up_m=5)) for agent in agents}) for phase in phases}))
    metadata = dict(status="completed", run_provenance=dict(status="verified_before_takeoff",
        parameter_comparison_version="wp_s_parameter_comparison_v2",
        parameter_evidence=dict(per_agent={agent: dict(complete=True, status="complete",
            received_count=1200, parameter_count=1200, missing_indices=[]) for agent in agents})),
        parameter_comparison_version="wp_s_parameter_comparison_v2",
        binary_firmware=dict(sha256="binary", version_string="ArduCopter V4.4"),
        parameters_sha256="template", cleanup={agent: 0 for agent in agents})
    quality = dict(episode_quality_eligible=True,
                   truth_separation=dict(status="clear_observed", minimum_m=7))
    metrics = dict(version="execution_artifacts_v2", evidence_complete=True,
        intermediate_waypoints=dict(total_count=10, stopped_count=1, unknown_count=0),
        thresholds={"0.3": dict(per_agent={agent: dict(evidence_complete=True, stop_count=2)
                                           for agent in agents})})
    labels = dict(mission_success=True, mission_success_observation=True,
        semantic_consistency="agree", mission_metrics={channel: dict(
            per_agent_laps_observed={agent: 2 for agent in agents})
            for channel in ("truth", "observation")})
    phase_report = {phase["name"]: dict(complete=True, within_tau=True,
        crosscheck_within_tau=True, primary=dict(complete=True, D_s=1.0, tau_s=2.0),
        crosscheck=dict(complete=True, D_s=1.1, tau_s=2.0)) for phase in phases}
    ac4 = dict(channels={channel: dict(complete=True, within_tau=True,
        crosscheck_within_tau=True, per_phase=copy.deepcopy(phase_report))
        for channel in ("truth", "observation")})
    onboard = dict(required=True, status="pass", pass_gate=True, rows=[])
    for phase in phases:
        for agent in agents:
            onboard["rows"].append(dict(phase=phase["name"], agent_id=agent, route_index=0,
                status="pass", uploaded_param1=1 if case_id == "VP4" else 0,
                onboard_records=[dict(packet=dict(Prm1=1 if case_id == "VP4" else 0))]))
    semantic = dict(pass_for_eligibility=True)
    control = dict(firmware=dict(sha256="binary", version_string="ArduCopter V4.4"),
                   parameters_sha256="template")
    return [scene, metadata, quality, labels, metrics, ac4, onboard, semantic, control]


class ValidationAssessmentTests(unittest.TestCase):
    def assess(self, case_id="VP1", values=None):
        return assess_run(case_id, *(values or fixture(case_id)))

    def test_complete_passing_patrol_and_vp4_param1(self):
        for case_id in ("VP1", "VP4"):
            result = self.assess(case_id)
            self.assertTrue(result["individual_pass"])
            self.assertIsNone(result["checks"]["AV-1"])
            self.assertTrue(all(result["checks"][name] is True for name in
                                ("AV-2", "AV-3", "AV-4", "AV-5", "AV-6", "AV-7", "AV-8")))
        values = fixture("VP4")
        values[6]["rows"][0]["onboard_records"][0]["packet"]["Prm1"] = 0
        result = self.assess("VP4", values)
        self.assertIs(result["checks"]["AV-6"], False)

    def test_timing_unknown_and_exceeded_both_stop(self):
        values = fixture()
        values[5]["channels"]["truth"]["per_phase"]["patrol"]["primary"]["D_s"] = 3.0
        self.assertIs(self.assess(values=values)["checks"]["AV-4"], False)
        values = fixture()
        values[5]["channels"]["truth"]["per_phase"]["patrol"]["primary"]["D_s"] = None
        self.assertIs(self.assess(values=values)["checks"]["AV-4"], False)
        values = fixture()
        values[2]["truth_separation"]["minimum_m"] = 4.9
        self.assertIs(self.assess(values=values)["checks"]["AV-4"], False)

    def test_missing_stops_laps_and_provenance_cannot_pass(self):
        values = fixture()
        values[4]["intermediate_waypoints"]["unknown_count"] = 1
        self.assertFalse(self.assess(values=values)["individual_pass"])
        values = fixture()
        values[3]["mission_metrics"]["observation"]["per_agent_laps_observed"]["uav_02"] = 1
        self.assertIs(self.assess(values=values)["checks"]["AV-8"], False)
        values = fixture()
        values[1]["run_provenance"]["status"] = "failed"
        self.assertIs(self.assess(values=values)["checks"]["AV-7"], False)

    def test_av1_is_pooled_by_intent(self):
        rows = [dict(case_id=case, individual_pass=True,
                     assessment=dict(av1=dict(total_count=10, stopped_count=1)))
                for case in CASE_ORDER]
        self.assertTrue(aggregate_av1(rows, "patrol")["pass_"])
        rows[0]["assessment"]["av1"]["stopped_count"] = 2
        self.assertFalse(aggregate_av1(rows, "patrol")["pass_"])
        self.assertTrue(aggregate_av1(rows, "reconnaissance")["pass_"])


class ValidationControlTests(unittest.TestCase):
    def control(self):
        return dict(version=VERSION, max_attempts=8, stopped_reason=None,
                    completed=False, active_attempt=None, records=[], aggregate_av1={})

    def test_only_whitelisted_proven_preflight_failures_retry(self):
        metadata = dict(status="failed", run_provenance=dict(status="failed"),
                        error="TimeoutError: uav_01: incomplete parameter readback (1105/1202)")
        params = {"uav_01": dict(status="failed", complete=False,
            error="TimeoutError: uav_01: incomplete parameter readback (1105/1202)",
            received_count=1105, parameter_count=1202,
            parameter_comparison=dict(status="evaluated", collection_complete=False,
                pass_=False, changes=[], stat_reset=dict(raw_value=None, pass_=False),
                fresh_instance={}))}
        params["uav_01"]["parameter_comparison"]["pass"] = False
        self.assertEqual(retry_reason(metadata, params),
                         "partial_parameter_readback_before_takeoff")
        self.assertIsNone(retry_reason(metadata, params, [dict(event="armed_confirmed")]))
        metadata["flight_epoch_monotonic_s"] = 100.0
        self.assertIsNone(retry_reason(metadata, params))
        metadata.pop("flight_epoch_monotonic_s")
        metadata["error"] = "ValueError: unexplained parameter readback differences: WPNAV_SPEED"
        self.assertIsNone(retry_reason(metadata, params))
        metadata["error"] = "OSError: address already in use"
        self.assertEqual(retry_reason(metadata, params),
                         "port_unavailable_before_takeoff")
        metadata["error"] = "TimeoutError: uav_01: TCP connection timeout"
        self.assertEqual(retry_reason(metadata, params),
                         "connection_failure_before_takeoff")
        metadata["error"] = "TimeoutError: uav_02: waiting for ['HEARTBEAT']; no status text"
        self.assertEqual(retry_reason(metadata, params),
                         "connection_failure_before_takeoff")
        self.assertIsNone(preflight_retry_reason(metadata, params, None))
        self.assertIsNone(preflight_retry_reason(metadata, params, []))
        metadata["run_provenance"]["status"] = "verified_before_takeoff"
        self.assertIsNone(retry_reason(metadata, params))

    def test_parallel_readback_never_hides_explicit_other_agent_mismatch(self):
        metadata = dict(status="failed", run_provenance=dict(status="failed"),
                        error="TimeoutError: uav_01: incomplete parameter readback (1105/1202)")
        partial = dict(status="failed", complete=False,
            error="TimeoutError: uav_01: incomplete parameter readback (1105/1202)",
            received_count=1105, parameter_count=1202,
            parameter_comparison=dict(status="evaluated", collection_complete=False,
                changes=[], stat_reset={"raw_value": None, "pass": False},
                fresh_instance={}, **{"pass": False}))
        passed = dict(status="complete", complete=True, received_count=1202,
            parameter_count=1202, parameter_comparison=dict(status="evaluated",
                collection_complete=True, **{"pass": True}))
        params = {"uav_01": partial, "uav_02": passed}
        self.assertEqual(retry_reason(metadata, params),
                         "partial_parameter_readback_before_takeoff")
        mismatched = copy.deepcopy(params)
        mismatched["uav_02"]["parameter_comparison"]["pass"] = False
        self.assertIsNone(retry_reason(metadata, mismatched))
        mismatched = copy.deepcopy(params)
        mismatched["uav_01"]["parameter_comparison"]["changes"].append(dict(
            name="WPNAV_SPEED", reference_value=1000, observed_value=1200,
            allowed_instance_difference=False))
        self.assertIsNone(retry_reason(metadata, mismatched))
        mismatched = copy.deepcopy(params)
        mismatched["uav_01"]["parameter_comparison"]["changes"].append(dict(
            name="NEW_PARAM", reference_value=None, observed_value=1,
            allowed_instance_difference=False))
        self.assertIsNone(retry_reason(metadata, mismatched))
        mismatched = copy.deepcopy(params)
        mismatched["uav_01"].update(sysid=1, all_parameters={"SYSID_THISMAV": 2})
        self.assertIsNone(retry_reason(metadata, mismatched))
        mismatched = copy.deepcopy(params)
        mismatched["uav_01"]["parameter_comparison"]["fresh_instance"]["STAT_BOOTCNT"] = dict(
            observed_value=2, **{"pass": False})
        self.assertIsNone(retry_reason(metadata, mismatched))
        mismatched = copy.deepcopy(params)
        mismatched["uav_01"]["parameter_comparison"]["stat_reset"] = dict(
            raw_value=120000, **{"pass": False})
        self.assertIsNone(retry_reason(metadata, mismatched))
        mismatched = copy.deepcopy(params)
        mismatched["uav_02"]["parameter_comparison"]["status"] = "not_evaluated"
        self.assertIsNone(retry_reason(metadata, mismatched))
        mismatched = copy.deepcopy(params)
        mismatched["uav_02"] = dict(status="not_started", complete=False,
            received_count=0, parameter_comparison=dict(status="not_evaluated", **{"pass": False}))
        self.assertIsNone(retry_reason(metadata, mismatched))
        metadata["error"] = "TimeoutError: uav_01: TCP connection timeout"
        untouched = {agent: dict(status="not_started", complete=False, received_count=0,
            parameter_comparison=dict(status="not_evaluated", **{"pass": False}))
            for agent in ("uav_01", "uav_02")}
        self.assertEqual(retry_reason(metadata, untouched),
                         "connection_failure_before_takeoff")
        self.assertIsNone(retry_reason(metadata, {}))
        self.assertIsNone(retry_reason(metadata, mismatched))

    def test_one_case_retry_and_global_two_retry_limit(self):
        control = self.control()
        self.assertEqual(next_case(control), ("VP1", 0))
        control["records"].append(dict(case_id="VP1", retryable_pre_takeoff=True,
                                       individual_pass=False))
        self.assertEqual(next_case(control), ("VP1", 1))
        control["records"].append(dict(case_id="VP1", retryable_pre_takeoff=False,
                                       individual_pass=True))
        self.assertEqual(next_case(control), ("VP2", 0))
        control["active_attempt"] = dict(case_id="VP2")
        with self.assertRaisesRegex(ValueError, "manual audit"):
            next_case(control)
        control["active_attempt"] = None
        control["records"].append(dict(case_id="VP2", retryable_pre_takeoff=True,
                                       individual_pass=False))
        self.assertEqual(next_case(control), ("VP2", 1))
        control["records"].append(dict(case_id="VP2", retryable_pre_takeoff=True,
                                       individual_pass=False))
        with self.assertRaisesRegex(ValueError, "retry budget"):
            next_case(control)


if __name__ == "__main__":
    unittest.main()
