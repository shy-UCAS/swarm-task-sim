"""Bounded v0.5 v05c validation, carrying the failed v05b attempt in budget.

The controller never creates a DR scene. It accepts only the six-case bundle
bound to a passing v05c review, records every new SITL launch, and stops
on the first unknown or failed applicable AV gate. The failed v05b VP1 launch
is immutable historical evidence and consumes one of eight total attempts.
`prepare` is offline;
`next` is the only action that may start SITL.
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_mission_list import _save_atomic, _verify_result, run_mission_list
from scripts.verify_v05_protected import verify_baseline
from swarm_sim.generation import canonical_hash, checked_path, file_hash, verify_generation
from swarm_sim.generation_v2 import normalize_profile
from swarm_sim.quality import policy_hash, resolve_policy
from swarm_sim.run_provenance import PARAMETER_COMPARISON_VERSION, verify_preflight_files


VERSION = "v05c_validation_controller_v1"
CASE_ORDER = ("VP1", "VP2", "VP3", "VP4", "VR1", "VR2")
TOTAL_SITL_BUDGET = 8
HISTORICAL_ATTEMPTS = 1
MAX_ATTEMPTS = TOTAL_SITL_BUDGET - HISTORICAL_ATTEMPTS
MAX_EXTRA_RETRIES = 1
STOP_THRESHOLD = 0.1
HISTORY_CONTROL = ROOT / "verification/v05b_validation_20261002_r2/control.json"
EXPECTED_PROFILE = ROOT / "generation_profiles/dual_intent_v05c.json"
EXPECTED_GENERATED = ROOT / "tmp_v05/dr_v05c/generated_130"
EXPECTED_REVIEW = ROOT / "tmp_v05/dr_v05c/review.json"
EXPECTED_BUNDLE = ROOT / "tmp_v05/validation_v05c/bundle"
EXPECTED_ROOT = ROOT / "verification/v05c_validation_20261002"


def read(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def all_true(value):
    if type(value) is bool:
        return value
    return isinstance(value, dict) and bool(value) and all(all_true(v) for v in value.values())


def assert_hashes(hashes):
    changed = [name for name, expected in hashes.items()
               if not Path(name).is_file() or file_hash(name) != expected]
    if changed:
        raise ValueError("frozen validation input/evidence changed: " + str(changed))


def assert_protected():
    report = verify_baseline()
    if report["unchanged"] is not True:
        raise ValueError("protected v0.4 file hash changed: " + str(report["missing"] + report["changed"]))
    return report["protected_file_count"]


def bind_failed_v05b_attempt(path=HISTORY_CONTROL):
    """Read-only proof that exactly one non-retryable VP1 SITL launch was spent."""
    path = Path(path).resolve()
    if path != HISTORY_CONTROL.resolve():
        raise ValueError("historical validation path differs from the frozen v05b r2 ledger")
    old = read(path)
    records = old.get("records", [])
    if (old.get("version") != "v05b_validation_controller_v1" or
            old.get("max_attempts") != TOTAL_SITL_BUDGET or
            old.get("planned_cases") != list(CASE_ORDER) or
            old.get("completed") is not False or
            old.get("active_attempt") is not None or
            not old.get("stopped_reason") or
            len(records) != HISTORICAL_ATTEMPTS):
        raise ValueError("v05b r2 must contain exactly one stopped SITL attempt")
    record = records[0]
    directory = Path(record.get("run_directory") or "").resolve()
    if (record.get("case_id") != "VP1" or record.get("attempt_index") != 0 or
            record.get("retryable_pre_takeoff") is not False or
            record.get("individual_pass") is not False or
            record.get("flight_epoch_present") is not False or
            record.get("run_status") != "failed" or
            "SIM_PLD_YAW" not in str(record.get("runner_error")) or
            not directory.is_relative_to(path.parent.resolve()) or
            not directory.is_dir()):
        raise ValueError("historical VP1 is not the non-retryable failed preflight")
    metadata = read(directory / "metadata.json")
    parameters = read(directory / "firmware_parameters.json")
    stop = read(path.parent / "stop_review.json")
    events_path = directory / "events.jsonl"
    if not events_path.is_file():
        raise ValueError("historical VP1 event log is missing")
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    if (metadata.get("status") != "failed" or
            "flight_epoch_monotonic_s" in metadata or
            "SIM_PLD_YAW" not in str(metadata.get("error")) or
            not any(item.get("event") == "run_failed" for item in events) or
            any(item.get("event") in {"armed_confirmed", "takeoff_command_sent", "airborne_ready"}
                for item in events) or
            set(parameters) != {"uav_01", "uav_02", "uav_03"} or
            stop.get("sitl_attempts_consumed") != HISTORICAL_ATTEMPTS or
            stop.get("retryable") is not False or
            stop.get("flights_performed") != 0 or
            stop.get("run_id") != metadata.get("run_id")):
        raise ValueError("historical VP1 flight or failure evidence changed")
    if (parameters["uav_01"].get("complete") is not False or
            parameters["uav_01"].get("received_count") != 1105 or
            parameters["uav_01"].get("parameter_count") != 1202):
        raise ValueError("historical uav_01 partial readback changed")
    for agent in ("uav_02", "uav_03"):
        item = parameters[agent]
        if (item.get("complete") is not True or item.get("received_count") != 1202 or
                item.get("parameter_count") != 1202 or
                item.get("parameter_comparison", {}).get("unexplained") != ["SIM_PLD_YAW"]):
            raise ValueError("historical complete readback or SIM_PLD_YAW mismatch changed")
    source_hashes = record.get("evidence_sha256")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("historical VP1 record has no evidence hashes")
    assert_hashes(source_hashes)
    paths = [path, directory / "metadata.json", directory / "firmware_parameters.json",
             events_path, directory / "scenario.json",
             path.parent / "stop_review.json", path.parent / "protected_stop_review.json"]
    for file_path in paths:
        if not file_path.is_file():
            raise ValueError(f"historical VP1 source missing: {file_path}")
    hashes = {str(file_path.resolve()): file_hash(file_path) for file_path in paths}
    hashes.update(source_hashes)
    return dict(source_control=str(path), source_control_sha256=hashes[str(path)],
                source_run_directory=str(directory), source_record=record,
                source_evidence_sha256=hashes, sitl_attempts_consumed=HISTORICAL_ATTEMPTS,
                retryable=False, flight_epoch_present=False,
                disposition="stopped_parameter_mismatch_preserved_not_counted_as_valid_VP1")


def assert_historical_binding(control):
    history = control.get("historical_failed_attempt")
    if (not isinstance(history, dict) or history.get("sitl_attempts_consumed") != 1 or
            history.get("retryable") is not False or
            history.get("flight_epoch_present") is not False or
            history.get("source_control") != str(HISTORY_CONTROL.resolve())):
        raise ValueError("v05b failure is not charged to this validation controller")
    assert_hashes(history["source_evidence_sha256"])
    fresh = bind_failed_v05b_attempt(history["source_control"])
    if fresh != history:
        raise ValueError("historical v05b failure binding changed")


def _bound_inputs(bundle, review_path, profile_path):
    bundle, review_path, profile_path = (Path(path).resolve() for path in
                                         (bundle, review_path, profile_path))
    if (bundle != EXPECTED_BUNDLE.resolve() or
            review_path != EXPECTED_REVIEW.resolve() or
            profile_path != EXPECTED_PROFILE.resolve()):
        raise ValueError("v05c validation inputs must use the new formal bundle, DR and profile paths")
    listing, manifest = verify_generation(bundle / "mission_list.json")
    selection, review = read(bundle / "selection.json"), read(review_path)
    profile = normalize_profile(profile_path)
    source_generation = Path(selection.get("source_generation_directory", "")).resolve()
    if source_generation != EXPECTED_GENERATED.resolve():
        raise ValueError("validation selection does not come from the v05c DR generation root")
    if (selection.get("version") != "v05c_validation_selection_v1"
            or selection.get("case_order") != list(CASE_ORDER)
            or manifest.get("case_order") != list(CASE_ORDER)
            or len(listing["missions"]) != len(CASE_ORDER)
            or [item.get("validation_case_id") for item in listing["missions"]] != list(CASE_ORDER)
            or [item.get("mission_id") for item in listing["missions"]] !=
               [selection["cases"][case]["selected_mission_id"] for case in CASE_ORDER]):
        raise ValueError("validation bundle does not contain the ordered six selected cases")
    expected = dict(source_review_sha256=file_hash(review_path),
                    source_manifest_sha256=file_hash(source_generation / "generation_manifest.json"),
                    source_profile_file_sha256=file_hash(profile_path),
                    source_profile_canonical_sha256=canonical_hash(profile))
    if (any(selection.get(key) != digest for key, digest in expected.items())
            or manifest.get("source_review_sha256") != expected["source_review_sha256"]
            or manifest.get("source_manifest_sha256") != expected["source_manifest_sha256"]
            or manifest.get("profile_sha256") != expected["source_profile_canonical_sha256"]
            or review.get("gate") != selection.get("source_review_gate")
            or review.get("gate", {}).get("v05c_v05b_invariant") is not True
            or not all_true(review.get("gate"))):
        raise ValueError("selection, DR review, profile and generated source are not hash-bound")
    for key in ("generation_manifest_file_sha256", "profile_file_sha256", "profile_canonical_sha256"):
        target = (expected["source_manifest_sha256"] if key.startswith("generation") else
                  expected["source_profile_canonical_sha256"] if key.endswith("canonical_sha256") else
                  expected["source_profile_file_sha256"])
        if review.get(key) != target:
            raise ValueError("DR review has a stale source fingerprint: " + key)
    if (selection.get("accepted_base_count") != 130 or
            selection.get("accepted_by_vehicle_count") != {"2": 44, "3": 43, "4": 43} or
            not finite(selection.get("joint_feasible_fraction")) or
            selection["joint_feasible_fraction"] < .30 or
            review.get("counts", {}).get("accepted_bases") != 130 or
            review.get("accepted_by_n") != {"2": 44, "3": 43, "4": 43} or
            review.get("rates", {}).get("both", {}).get("fraction", 0) < .30):
        raise ValueError("validation selection lacks the v05c DR acceptance gate")
    for entry in listing["missions"]:
        if entry.get("status") != "planned" or entry.get("control_mode") != "semantic_phase_route_v1":
            raise ValueError("selected validation task is not a planned v3 route")
    return selection, listing, manifest


def prepare(root, bundle, review, profile, binary, parameters, quality_policy):
    root, bundle, review, profile = (Path(path).resolve() for path in (root, bundle, review, profile))
    binary, parameters, quality_policy = (Path(path).resolve() for path in (binary, parameters, quality_policy))
    if root != EXPECTED_ROOT.resolve():
        raise ValueError("v05c validation output must use the dedicated new root")
    if root.exists():
        raise ValueError("validation output root already exists; never overwrite a prior ledger")
    selection, listing, _ = _bound_inputs(bundle, review, profile)
    history = bind_failed_v05b_attempt()
    protected_count = assert_protected()
    provenance = verify_preflight_files(binary, parameters)
    policy = resolve_policy(read(quality_policy))
    source_generation = Path(selection["source_generation_directory"])
    frozen = list(bundle.rglob("*.json")) + [profile, review,
        source_generation / "generation_manifest.json", quality_policy, binary, parameters,
        ROOT / "generation_profiles/dual_intent_v05.json",
        ROOT / "tmp_v05/m0/protected_baseline.json",
        ROOT / "docs/v04_spike_go_confirmation.json",
        ROOT / "scripts/run_mission_list.py", ROOT / "scripts/verify_v05_protected.py",
        ROOT / "scripts/select_v05c_validation.py", Path(__file__)] + list((ROOT / "swarm_sim").glob("*.py"))
    hashes = {str(path.resolve()): file_hash(path) for path in frozen}
    control = dict(version=VERSION, prepared_utc=datetime.now(timezone.utc).isoformat(),
        bundle=str(bundle), review=str(review), profile=str(profile), binary=str(binary),
        parameters=str(parameters), quality_policy=policy,
        quality_policy_sha256=policy_hash(policy),
        profile_file_sha256=file_hash(profile),
        profile_canonical_sha256=selection["source_profile_canonical_sha256"],
        source_review_sha256=selection["source_review_sha256"],
        firmware=provenance["actual"]["firmware"], parameters_sha256=file_hash(parameters),
        protected_file_count=protected_count,
        total_sitl_budget=TOTAL_SITL_BUDGET, historical_attempts_consumed=HISTORICAL_ATTEMPTS,
        max_attempts=MAX_ATTEMPTS, planned_cases=list(CASE_ORDER), max_extra_retries=MAX_EXTRA_RETRIES,
        retry_policy="one per case, only proven pre-takeoff startup/connection/partial-readback failure",
        case_to_mission={entry["validation_case_id"]: entry["mission_id"] for entry in listing["missions"]},
        historical_failed_attempt=history,
        frozen_sha256=hashes, records=[], aggregate_av1={}, active_attempt=None,
        stopped_reason=None, completed=False)
    root.mkdir(parents=True, exist_ok=False)
    _save_atomic(root / "control.json", control)
    return control


def zero_length_segments(scene):
    count = 0
    for phase in scene.get("phases", []):
        name = phase.get("name")
        roles = scene.get("semantic_plan", {}).get("execution_phases", {}).get(name, {}).get("agents", {})
        for vehicle in scene.get("vehicles", []):
            agent = vehicle["id"]
            route = phase.get("routes", {}).get(agent)
            start = roles.get(agent, {}).get("start_point")
            if not isinstance(route, list) or not isinstance(start, dict):
                return None
            points = [start, *route]
            for left, right in zip(points, points[1:]):
                try:
                    distance = math.dist([left[key] for key in ("east_m", "north_m", "up_m")],
                                         [right[key] for key in ("east_m", "north_m", "up_m")])
                except (KeyError, TypeError, ValueError):
                    return None
                count += distance <= 1e-9
    return count


def _terminal_prm1_pass(scene, onboard):
    rows = onboard.get("rows", [])
    checked = []
    for phase in scene.get("phases", []):
        for agent, route in phase.get("routes", {}).items():
            if not route:
                continue
            matched = [row for row in rows if row.get("phase") == phase["name"]
                       and row.get("agent_id") == agent and row.get("route_index") == len(route) - 1]
            if len(matched) != 1:
                return False, checked
            row = matched[0]
            values = [record.get("packet", {}).get("Prm1") for record in row.get("onboard_records", [])]
            checked.append(dict(phase=phase["name"], agent_id=agent,
                                uploaded_param1=row.get("uploaded_param1"), onboard_param1=values))
            if (row.get("status") != "pass" or row.get("uploaded_param1") != 1
                    or not values or any(value != 1 for value in values)):
                return False, checked
    return bool(checked), checked


def _ac4_evidence(scene, ac4):
    report = {}
    passed = True
    for channel in ("truth", "observation"):
        data = ac4.get("channels", {}).get(channel, {})
        channel_ok = data.get("complete") is True and data.get("within_tau") is True and data.get("crosscheck_within_tau") is True
        phases = {}
        for phase in scene.get("phases", []):
            name = phase["name"]
            row = data.get("per_phase", {}).get(name, {})
            primary, cross = row.get("primary", {}), row.get("crosscheck", {})
            tau, D = primary.get("tau_s"), primary.get("D_s")
            phase_ok = (row.get("complete") is True and row.get("within_tau") is True
                        and row.get("crosscheck_within_tau") is True
                        and finite(tau) and finite(D) and D <= tau + 1e-9
                        and cross.get("complete") is True and finite(cross.get("D_s"))
                        and finite(cross.get("tau_s")) and cross["D_s"] <= cross["tau_s"] + 1e-9)
            phases[name] = dict(semantic_phase=phase.get("semantic_phase"), D_s=D, tau_s=tau,
                                crosscheck_D_s=cross.get("D_s"), pass_=phase_ok)
            channel_ok &= phase_ok
        report[channel] = dict(complete=data.get("complete"), within_tau=data.get("within_tau"),
                               crosscheck_within_tau=data.get("crosscheck_within_tau"),
                               per_phase=phases, pass_=channel_ok)
        passed &= channel_ok
    return passed, report


def assess_run(case_id, scene, metadata, quality, labels, metrics, ac4, onboard, semantic, control):
    """Treat missing evidence as non-passing. AV-1 is pooled by intent later."""
    agents = [vehicle["id"] for vehicle in scene.get("vehicles", [])]
    phases = {phase.get("semantic_phase") for phase in scene.get("phases", [])}
    phases.discard(None)
    intermediate = metrics.get("intermediate_waypoints", {})
    totals = [intermediate.get(key) for key in ("total_count", "stopped_count", "unknown_count")]
    av1_evidence = (metrics.get("version") == "execution_artifacts_v2" and
                    metrics.get("evidence_complete") is True and
                    all(type(value) is int and value >= 0 for value in totals) and totals[2] == 0 and
                    totals[1] <= totals[0])
    stops = metrics.get("thresholds", {}).get("0.3", {}).get("per_agent", {})
    av2 = bool(phases) and set(stops) == set(agents) and all(
        row.get("evidence_complete") is True and type(row.get("stop_count")) is int and
        row["stop_count"] <= len(phases) + 1 for row in stops.values())
    av3 = (labels.get("mission_success") is True and labels.get("mission_success_observation") is True
           and labels.get("semantic_consistency") == "agree" and
           semantic.get("pass_for_eligibility") is True)
    ac4_pass, timing = _ac4_evidence(scene, ac4)
    separation = quality.get("truth_separation", {})
    minimum, required = separation.get("minimum_m"), scene.get("min_separation_m")
    av4 = (separation.get("status") == "clear_observed" and finite(minimum) and finite(required)
           and minimum + 1e-9 >= required and ac4_pass)
    zero = zero_length_segments(scene)
    av5 = zero == 0 if zero is not None else False
    av6 = onboard.get("required") is True and onboard.get("status") == "pass" and onboard.get("pass_gate") is True
    vp4_param1 = None
    if case_id == "VP4":
        vp4_pass, vp4_param1 = _terminal_prm1_pass(scene, onboard)
        av6 &= vp4_pass
    prov = metadata.get("run_provenance", {})
    readback = prov.get("parameter_evidence", {}).get("per_agent", {})
    binary = metadata.get("binary_firmware", {})
    cleanup = metadata.get("cleanup", {})
    av7 = (metadata.get("status") == "completed" and quality.get("episode_quality_eligible") is True
           and not quality.get("analysis_error") and prov.get("status") == "verified_before_takeoff"
           and prov.get("parameter_comparison_version") == PARAMETER_COMPARISON_VERSION
           and metadata.get("parameter_comparison_version") == PARAMETER_COMPARISON_VERSION
           and binary.get("sha256") == control["firmware"]["sha256"]
           and binary.get("version_string") == control["firmware"]["version_string"]
           and metadata.get("parameters_sha256") == control["parameters_sha256"]
           and set(readback) == set(agents) and all(row.get("complete") is True and
               row.get("status") == "complete" and row.get("received_count") == row.get("parameter_count")
               and row.get("missing_indices") == [] for row in readback.values())
           and set(cleanup) == set(agents) and all(type(cleanup[agent]) is int for agent in agents))
    intent = scene.get("task_spec", {}).get("mission", {}).get("intent")
    laps = scene.get("task_spec", {}).get("mission", {}).get("intent_params", {}).get("laps")
    lap_evidence = {}
    av8 = True
    if intent == "patrol":
        lap_evidence = {channel: labels.get("mission_metrics", {}).get(channel, {}).get("per_agent_laps_observed")
                        for channel in ("truth", "observation")}
        av8 = type(laps) is int and set(lap_evidence.get("truth") or {}) == set(agents) and all(
            isinstance(lap_evidence.get(channel), dict) and
            all(type(lap_evidence[channel].get(agent)) is int and lap_evidence[channel][agent] == laps
                for agent in agents) for channel in ("truth", "observation"))
    checks = {"AV-1": None if av1_evidence else False, "AV-2": av2, "AV-3": av3,
              "AV-4": av4, "AV-5": av5, "AV-6": av6, "AV-7": av7, "AV-8": av8}
    return dict(checks=checks, individual_pass=av1_evidence and all(
        checks[key] is True for key in ("AV-2", "AV-3", "AV-4", "AV-5", "AV-6", "AV-7", "AV-8")),
        av1=dict(total_count=totals[0], stopped_count=totals[1], unknown_count=totals[2],
                 evidence_complete=av1_evidence),
        av2=dict(semantic_phase_count=len(phases), limit=len(phases) + 1, per_agent=stops),
        av3=dict(mission_success=labels.get("mission_success"),
                 mission_success_observation=labels.get("mission_success_observation"),
                 semantic_consistency=labels.get("semantic_consistency")),
        av4=dict(truth_minimum_m=minimum, required_m=required,
                 truth_separation_status=separation.get("status"), timing=timing),
        av5=dict(zero_length_count=zero), av6=dict(onboard_status=onboard.get("status"),
            vp4_terminal_prm1=vp4_param1), av7=dict(provenance_status=prov.get("status"),
            parameter_comparison_version=prov.get("parameter_comparison_version"),
            episode_quality_eligible=quality.get("episode_quality_eligible")),
        av8=dict(intent=intent, planned_laps=laps if intent == "patrol" else None,
                 per_agent_laps_observed=lap_evidence if intent == "patrol" else None,
                 applicable=intent == "patrol"))


def _parameter_evidence_allows_retry(evidence):
    """Only untouched, passed, or demonstrably incomplete readbacks are safe.

    A partial readback still runs the comparator. Its overall ``pass=False``
    reflects missing values; already received conflicting values are a hard
    failure even if another agent's timeout is the top-level error.
    """
    if not isinstance(evidence, dict) or not evidence:
        return False, False
    saw_partial = False
    for row in evidence.values():
        if not isinstance(row, dict):
            return False, False
        comparison = row.get("parameter_comparison")
        if not isinstance(comparison, dict):
            return False, False
        status = row.get("status")
        if status == "not_started":
            if (row.get("complete") is not False or row.get("received_count") != 0 or
                    comparison.get("status") != "not_evaluated"):
                return False, False
            continue
        if status == "complete":
            if (row.get("complete") is not True or comparison.get("status") != "evaluated" or
                    comparison.get("collection_complete") is not True or comparison.get("pass") is not True):
                return False, False
            continue
        if status != "failed" or row.get("complete") is not False or \
                "incomplete parameter readback" not in str(row.get("error", "")).lower():
            return False, False
        count, received = row.get("parameter_count"), row.get("received_count")
        if (type(count) is not int or type(received) is not int or
                count <= 0 or not 0 <= received < count or
                comparison.get("status") != "evaluated" or
                comparison.get("collection_complete") is not False or
                comparison.get("pass") is not False):
            return False, False
        changes = comparison.get("changes")
        fresh = comparison.get("fresh_instance")
        reset = comparison.get("stat_reset")
        if not isinstance(changes, list) or not isinstance(fresh, dict) or not isinstance(reset, dict):
            return False, False
        for change in changes:
            if not isinstance(change, dict):
                return False, False
            if (change.get("observed_value") is not None and
                    (change.get("reference_value") is None or
                     change.get("allowed_instance_difference") is not True)):
                return False, False
        actual = row.get("all_parameters", {})
        if not isinstance(actual, dict):
            return False, False
        if ("SYSID_THISMAV" in actual and row.get("sysid") is not None and
                actual["SYSID_THISMAV"] != row["sysid"]):
            return False, False
        if reset.get("raw_value") is not None and reset.get("pass") is not True:
            return False, False
        for check in fresh.values():
            if (not isinstance(check, dict) or
                    check.get("observed_value") is not None and check.get("pass") is not True):
                return False, False
        saw_partial = True
    return True, saw_partial


def preflight_retry_reason(metadata, parameter_evidence, events):
    """Whitelist a failure proved to precede arm/takeoff; ambiguity never retries."""
    if (not isinstance(events, list) or not events or
            not all(isinstance(event, dict) for event in events) or
            not any(event.get("event") == "run_failed" for event in events)):
        return None
    if metadata.get("status") != "failed" or metadata.get("run_provenance", {}).get("status") == "verified_before_takeoff":
        return None
    if "flight_epoch_monotonic_s" in metadata or any(event.get("event") in
            {"armed_confirmed", "takeoff_command_sent", "airborne_ready"} for event in events):
        return None
    error = str(metadata.get("error", "")).lower()
    if any(term in error for term in ("wp-s", "firmware or parameter template differs", "unexplained parameter",
                                      "parameter table count invalid", "conflicting parameter values",
                                      "duplicate parameter names", "autopilot_version differs")):
        return None
    evidence_safe, has_partial = _parameter_evidence_allows_retry(parameter_evidence)
    if not evidence_safe:
        return None
    if has_partial and any(row.get("status") == "not_started"
                           for row in parameter_evidence.values()):
        return None
    if "incomplete parameter readback" in error and has_partial:
        return "partial_parameter_readback_before_takeoff"
    if any(term in error for term in ("address already in use", "winerror 10048", "port unavailable")):
        return "port_unavailable_before_takeoff"
    if "sitl exited (" in error or "sitl process exit" in error:
        return "sitl_startup_exit_before_takeoff"
    if any(term in error for term in ("connection refused", "winerror 10061", "tcp connection timeout",
                                     "heartbeat timeout", "no heartbeat", "waiting for ['heartbeat']")):
        return "connection_failure_before_takeoff"
    return None


def next_case(control):
    if (control.get("version") != VERSION or control.get("max_attempts") != MAX_ATTEMPTS or
            control.get("total_sitl_budget") != TOTAL_SITL_BUDGET or
            control.get("historical_attempts_consumed") != HISTORICAL_ATTEMPTS or
            control.get("max_extra_retries") != MAX_EXTRA_RETRIES):
        raise ValueError("invalid validation controller version/budget")
    if control.get("stopped_reason") or control.get("completed"):
        raise ValueError("validation is stopped or complete")
    if control.get("active_attempt") is not None:
        raise ValueError("unresolved reserved attempt; manual audit required, no automatic retry")
    records = control["records"]
    if len(records) >= MAX_ATTEMPTS or len(records) + HISTORICAL_ATTEMPTS >= TOTAL_SITL_BUDGET:
        raise ValueError("eight-attempt total SITL budget exhausted; v05b failure consumed one")
    if not records:
        return CASE_ORDER[0], 0
    last = records[-1]
    if last.get("retryable_pre_takeoff"):
        extra = len(records) - len({row["case_id"] for row in records})
        if extra >= MAX_EXTRA_RETRIES or sum(row["case_id"] == last["case_id"] for row in records) >= 2:
            raise ValueError("pre-takeoff retry budget exhausted")
        return last["case_id"], 1
    if last.get("individual_pass") is not True:
        raise ValueError("previous validation case failed or has unknown AV evidence")
    index = CASE_ORDER.index(last["case_id"]) + 1
    if index >= len(CASE_ORDER):
        raise ValueError("all six validation cases already ran")
    previous_intent_done = last["case_id"] == "VP4"
    if previous_intent_done and control.get("aggregate_av1", {}).get("patrol", {}).get("pass") is not True:
        raise ValueError("patrol pooled AV-1 is not accepted")
    return CASE_ORDER[index], 0


def aggregate_av1(records, intent):
    cases = ("VP1", "VP2", "VP3", "VP4") if intent == "patrol" else ("VR1", "VR2")
    selected = [row for row in records if row["case_id"] in cases and row.get("individual_pass") is True]
    if len(selected) != len(cases) or {row["case_id"] for row in selected} != set(cases):
        return dict(pass_=None, status="pending", cases=cases)
    total = sum(row["assessment"]["av1"]["total_count"] for row in selected)
    stopped = sum(row["assessment"]["av1"]["stopped_count"] for row in selected)
    passed = total > 0 and stopped / total <= STOP_THRESHOLD + 1e-12
    return dict(pass_=passed, status="PASS" if passed else "FAIL", cases=cases,
                total_count=total, stopped_count=stopped,
                stop_rate=stopped / total if total else None, limit=STOP_THRESHOLD)


def _run_artifacts(run_directory, scene, entry, control):
    directory = Path(run_directory)
    metadata = read(directory / "metadata.json")
    root_quality = read(directory / "quality.json")
    if not (directory / "analysis_latest.json").is_file():
        return metadata, root_quality, None
    latest = read(directory / "analysis_latest.json")
    analysis = checked_path(directory, latest["directory"])
    bundle = Path(control["bundle"])
    generation = dict(generation_profile=read(bundle / "generation_profile.json"),
                      generation_manifest=read(bundle / "generation_manifest.json"),
                      generation_entry=entry)
    _verify_result(directory, scene, control["quality_policy_sha256"],
                   selected=latest, generation_context=generation)
    artifacts = {name: read(analysis / (name + ".json")) for name in
                 ("quality", "labels", "execution_metrics", "ac4_timing_v3",
                  "onboard_mission_param_check", "semantic_validation")}
    return metadata, root_quality, artifacts


def _event_rows(directory):
    path = Path(directory) / "events.jsonl"
    return ([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if path.is_file() else None)


def run_next(root):
    root = Path(root).resolve()
    control_path = root / "control.json"
    control = read(control_path)
    case_id, attempt_index = next_case(control)
    try:
        assert_historical_binding(control)
        assert_hashes(control["frozen_sha256"])
        for record in control["records"]:
            assert_hashes(record.get("evidence_sha256", {}))
        assert_protected()
    except Exception as exc:
        control["stopped_reason"] = f"pre-run integrity failure: {type(exc).__name__}: {exc}"
        _save_atomic(control_path, control)
        raise
    listing, _ = verify_generation(Path(control["bundle"]) / "mission_list.json")
    entry = next(item for item in listing["missions"] if item["validation_case_id"] == case_id)
    scene = read(checked_path(control["bundle"], entry["scene"]))
    run_root = root / "execution" / case_id / f"attempt_{attempt_index}"
    reservation = dict(case_id=case_id, attempt_index=attempt_index,
                       run_root=str(run_root), reserved_utc=datetime.now(timezone.utc).isoformat())
    control["active_attempt"] = reservation
    _save_atomic(control_path, control)
    row = dict(**reservation, mission_id=entry["mission_id"],
               attempted_utc=reservation["reserved_utc"], evidence_sha256={})
    try:
        ledger = run_mission_list(control["bundle"] + "/mission_list.json",
            max_runs=1, resume=False, output_root=run_root, mission_ids=[entry["mission_id"]],
            binary=control["binary"], parameters=control["parameters"],
            quality_policy=control["quality_policy"], max_environment_retries=0, retryable_errors=())
        attempt = ledger["missions"][0]["attempts"][0]
        row.update(runner_status=attempt["status"], runner_error=attempt.get("error"),
                   run_directory=attempt.get("run_directory"), attempt_directory=attempt["attempt_directory"])
        if not row["run_directory"]:
            row.update(retryable_pre_takeoff=False, individual_pass=False,
                       stopped_reason="runner returned no run directory; takeoff status unproven")
        else:
            directory = Path(row["run_directory"])
            metadata, root_quality, artifacts = _run_artifacts(directory, scene, entry, control)
            row.update(run_id=metadata.get("run_id"), run_status=metadata.get("status"),
                       flight_epoch_present="flight_epoch_monotonic_s" in metadata)
            parameter_path = directory / "firmware_parameters.json"
            parameters = read(parameter_path) if parameter_path.is_file() else {}
            retry_reason = preflight_retry_reason(metadata, parameters, _event_rows(directory))
            row["retryable_pre_takeoff"] = retry_reason is not None
            row["retry_reason"] = retry_reason
            if retry_reason:
                row["individual_pass"] = False
            elif artifacts is None:
                row.update(individual_pass=False,
                           stopped_reason="selected analysis missing; AV evidence unknown")
            else:
                assessment = assess_run(case_id, scene, metadata, artifacts["quality"],
                    artifacts["labels"], artifacts["execution_metrics"], artifacts["ac4_timing_v3"],
                    artifacts["onboard_mission_param_check"], artifacts["semantic_validation"], control)
                row["assessment"] = assessment
                row["individual_pass"] = assessment["individual_pass"]
                if not row["individual_pass"]:
                    failed = [key for key, value in assessment["checks"].items()
                              if value is False]
                    row["stopped_reason"] = "AV gate failed/unknown: " + ", ".join(failed)
            evidence = [directory / name for name in
                        ("metadata.json", "quality.json", "firmware_parameters.json", "analysis_latest.json")]
            if (directory / "analysis_latest.json").is_file():
                latest = read(directory / "analysis_latest.json")
                evidence.append(checked_path(directory, latest["directory"]) / "manifest.json")
            row["evidence_sha256"] = {str(path.resolve()): file_hash(path)
                                      for path in evidence if path.is_file()}
        row["finished_utc"] = datetime.now(timezone.utc).isoformat()
    except BaseException as exc:
        row.update(individual_pass=False, retryable_pre_takeoff=False,
                   stopped_reason=f"unresolved attempt: {type(exc).__name__}: {exc}",
                   finished_utc=datetime.now(timezone.utc).isoformat())
        control["stopped_reason"] = row["stopped_reason"]
        control["records"].append(row)
        control["active_attempt"] = None
        _save_atomic(control_path, control)
        raise
    try:
        assert_historical_binding(control)
        assert_hashes(control["frozen_sha256"])
        assert_protected()
    except Exception as exc:
        row["stopped_reason"] = f"post-run integrity failure: {type(exc).__name__}: {exc}"
        row["retryable_pre_takeoff"] = False
    control["records"].append(row)
    control["active_attempt"] = None
    if row.get("stopped_reason"):
        control["stopped_reason"] = row["stopped_reason"]
    elif row.get("retryable_pre_takeoff"):
        extra = len(control["records"]) - len({item["case_id"] for item in control["records"]})
        if extra >= MAX_EXTRA_RETRIES or sum(item["case_id"] == case_id for item in control["records"]) >= 2:
            control["stopped_reason"] = "pre-takeoff retry allowance exhausted"
    elif case_id in ("VP4", "VR2"):
        intent = "patrol" if case_id == "VP4" else "reconnaissance"
        aggregate = aggregate_av1(control["records"], intent)
        control["aggregate_av1"][intent] = {"pass": aggregate.pop("pass_"), **aggregate}
        if control["aggregate_av1"][intent]["pass"] is not True:
            control["stopped_reason"] = intent + " pooled AV-1 failed or unknown"
    if case_id == "VR2" and not control["stopped_reason"]:
        control["completed"] = True
    _save_atomic(control_path, control)
    return row, control


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "next"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--profile", type=Path, default=ROOT / "generation_profiles/dual_intent_v05c.json")
    parser.add_argument("--sitl", type=Path, default=ROOT / "ArducopterSITL/arducopter.exe")
    parser.add_argument("--parameters", type=Path, default=ROOT / "ArducopterSITL/copter.parm")
    parser.add_argument("--quality-policy", type=Path, default=ROOT / "quality_policies/default_v022.json")
    args = parser.parse_args(argv)
    if args.action == "prepare":
        if args.bundle is None or args.review is None:
            parser.error("prepare requires --bundle and --review")
        control = prepare(args.root, args.bundle, args.review, args.profile,
                          args.sitl, args.parameters, args.quality_policy)
        print(json.dumps(dict(prepared=True, root=str(args.root.resolve()),
                              profile_sha256=control["profile_canonical_sha256"],
                              total_sitl_budget=control["total_sitl_budget"],
                              historical_attempts_consumed=control["historical_attempts_consumed"],
                              remaining_attempts=control["max_attempts"]), ensure_ascii=False))
        return 0
    row, control = run_next(args.root)
    print(json.dumps(dict(case_id=row["case_id"], attempt_index=row["attempt_index"],
                          run_status=row.get("run_status"), individual_pass=row.get("individual_pass"),
                          retryable_pre_takeoff=row.get("retryable_pre_takeoff"),
                          stopped_reason=control.get("stopped_reason"),
                          completed=control["completed"]), ensure_ascii=False))
    return int(bool(control.get("stopped_reason")))


if __name__ == "__main__":
    raise SystemExit(main())
