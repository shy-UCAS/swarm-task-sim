"""r1.2 validation: immutable VP1 reassessment plus four new bounded runs.

Only ``next`` launches SITL. The original r1 ledgers/analyses are never written.
Two historical launches plus four planned launches leave two preflight retries.
"""

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_mission_list import _save_atomic, run_mission_list
from scripts.run_v05c_validation import (
    EXPECTED_BUNDLE, EXPECTED_PROFILE, EXPECTED_REVIEW, _bound_inputs,
    _event_rows, assert_hashes, assert_protected, bind_failed_v05b_attempt,
    preflight_retry_reason, read,
)
from swarm_sim.analysis_v3 import analyze_run_v3
from swarm_sim.generation import canonical_hash, checked_path, file_hash, verify_generation
from swarm_sim.protocol import manifest_protocol, semantic_protocol, validate_artifact_protocol
from swarm_sim.quality import policy_hash, resolve_policy
from swarm_sim.run_provenance import verify_preflight_files
from swarm_sim.validation_policy import assess_run

VERSION = "v05_r12_validation_controller_v1"
POLICY_VERSION = "v05_acceptance_r1_2"
PROGRESS_VERSION = "ordered_route_progress_v2"
CASE_ORDER = ("VP1", "VP2", "VP3", "VR1", "VR2")
NEW_CASE_ORDER = CASE_ORDER[1:]
TOTAL_SITL_BUDGET = 8
HISTORICAL_ATTEMPTS = 2
MAX_ATTEMPTS = 6
MAX_EXTRA_RETRIES = 2
EXPECTED_ROOT = ROOT / "verification/v05_r12_validation_20261002"
HISTORY_VP1 = ROOT / "verification/v05c_validation_20261002/control.json"
OFFLINE_READINESS = ROOT / "tmp_v05/r12a/offline_readiness.json"
ARTIFACTS = ("quality", "labels", "execution_metrics", "ac4_timing_v3",
             "onboard_mission_param_check", "semantic_validation")


def utc():
    return datetime.now(timezone.utc).isoformat()


def offline_readiness():
    if not OFFLINE_READINESS.is_file():
        raise ValueError("r1.2 offline readiness is missing; M01/M02/M03 must pass before any launch")
    report = read(OFFLINE_READINESS)
    if (report.get("version") != "v05_r12_offline_readiness_v1" or
            report.get("route_progress_version") != PROGRESS_VERSION or
            set(report.get("gates", {})) != {"M01", "M02", "M03"} or
            any(value is not True for value in report["gates"].values())):
        raise ValueError("r1.2 offline readiness failed: M01/M02/M03 must all pass before any launch")
    hashes = {str(OFFLINE_READINESS.resolve()): file_hash(OFFLINE_READINESS)}
    for key in ("evidence_sha256", "analysis_source_sha256"):
        if not isinstance(report.get(key), dict) or not report[key]:
            raise ValueError("offline readiness lacks bound tests/regression/source evidence")
        assert_hashes(report[key])
        hashes.update(report[key])
    return dict(report=str(OFFLINE_READINESS.resolve()), gates=report["gates"], evidence_sha256=hashes)


def bind_history():
    failed = bind_failed_v05b_attempt()
    old = read(HISTORY_VP1)
    rows = old.get("records", [])
    if (old.get("version") != "v05c_validation_controller_v1" or
            old.get("completed") is not False or old.get("active_attempt") is not None or
            not old.get("stopped_reason") or len(rows) != 1):
        raise ValueError("original v05c VP1 is not the single preserved stopped attempt")
    row = rows[0]
    directory = Path(row.get("run_directory", "")).resolve()
    if (row.get("case_id") != "VP1" or row.get("individual_pass") is not False or
            row.get("retryable_pre_takeoff") is not False or
            row.get("flight_epoch_present") is not True or row.get("run_status") != "completed" or
            not directory.is_relative_to(HISTORY_VP1.parent.resolve())):
        raise ValueError("original VP1 flight/disposition changed")
    assert_hashes(row["evidence_sha256"])
    # Original source hash maps describe their original code. Their files and
    # evidence remain bound; current r1.2 source is intentionally a new version.
    hashes = {str(p.resolve()): file_hash(p) for p in directory.rglob("*") if p.is_file()}
    hashes.update({str(HISTORY_VP1.resolve()): file_hash(HISTORY_VP1)})
    return dict(sitl_attempts_consumed=2, v05b=failed,
                v05c=dict(source_control=str(HISTORY_VP1.resolve()), source_record=copy.deepcopy(row),
                          original_r1_disposition="FAIL", original_stopped_reason=old["stopped_reason"],
                          source_evidence_sha256=hashes))


def assert_historical_binding(control):
    history = control.get("history", {})
    if history.get("sitl_attempts_consumed") != HISTORICAL_ATTEMPTS:
        raise ValueError("two historical SITL launches must remain charged")
    for key in ("v05b", "v05c"):
        assert_hashes(history[key]["source_evidence_sha256"])
    if history != bind_history():
        raise ValueError("historical evidence binding changed")


def analysis_artifacts(directory, analysis, scene, control):
    """Validate either an external VP1 analysis or a new run's selected analysis."""
    directory, analysis = Path(directory).resolve(), Path(analysis).resolve()
    metadata = read(directory / "metadata.json")
    manifest = read(analysis / "manifest.json")
    if (canonical_hash(metadata.get("scenario")) != canonical_hash(scene) or
            metadata.get("quality_policy_sha256") != control["quality_policy_sha256"] or
            manifest.get("quality_policy_sha256") != control["quality_policy_sha256"] or
            manifest.get("route_progress_version") != PROGRESS_VERSION or
            manifest_protocol(manifest) != semantic_protocol(scene)):
        raise ValueError("analysis source scene/protocol/quality-policy binding changed")
    for name, digest in manifest["artifact_sha256"].items():
        if file_hash(checked_path(analysis, name)) != digest:
            raise ValueError("analysis artifact changed: " + name)
    for name, digest in manifest["source_sha256"].items():
        if file_hash(checked_path(directory, name)) != digest:
            raise ValueError("analysis source changed: " + name)
    validate_artifact_protocol(manifest, analysis)
    artifacts = {name: read(analysis / (name + ".json")) for name in ARTIFACTS}
    if artifacts["ac4_timing_v3"].get("route_progress_version") != PROGRESS_VERSION:
        raise ValueError("AC4 analysis does not use ordered_route_progress_v2")
    policy = artifacts["quality"].get("validation_policy", {})
    if policy.get("version") != POLICY_VERSION or policy.get("stage") != control.get("stage", "validation"):
        raise ValueError("selected analysis does not contain the r1.2 policy for this stage")
    return metadata, artifacts


def assess_artifacts(scene, metadata, artifacts, control):
    assessment = assess_run(scene, metadata, artifacts["quality"], artifacts["labels"],
        artifacts["execution_metrics"], artifacts["ac4_timing_v3"],
        artifacts["onboard_mission_param_check"], stage=control.get("stage", "validation"))
    binary = metadata.get("binary_firmware", {})
    bound = (binary.get("sha256") == control["firmware"]["sha256"] and
             binary.get("version_string") == control["firmware"]["version_string"] and
             metadata.get("parameters_sha256") == control["parameters_sha256"])
    assessment["hard_checks"]["frozen_firmware_and_parameters"] = bound
    if not bound:
        assessment["hard_failures"].append("frozen_firmware_and_parameters")
        assessment["individual_pass"] = False
    agents = {vehicle["id"] for vehicle in scene.get("vehicles", [])}
    cleanup = metadata.get("cleanup", {})
    cleanup_ok = bool(agents) and set(cleanup) == agents and all(type(cleanup[a]) is int for a in agents)
    assessment["hard_checks"]["infrastructure_cleanup_complete"] = cleanup_ok
    if not cleanup_ok:
        assessment["hard_failures"].append("infrastructure_cleanup_complete")
        assessment["individual_pass"] = False
    return assessment


def record_evidence(directory, analysis):
    paths = [p for p in Path(directory).iterdir() if p.is_file()]
    paths += [p for p in Path(analysis).rglob("*") if p.is_file()]
    return {str(p.resolve()): file_hash(p) for p in paths}


def prepare(root, vp1_analysis, binary, parameters, quality_policy):
    root, vp1_analysis = Path(root).resolve(), Path(vp1_analysis).resolve()
    binary, parameters, quality_policy = map(lambda p: Path(p).resolve(),
                                             (binary, parameters, quality_policy))
    if root != EXPECTED_ROOT.resolve() or root.exists():
        raise ValueError("r1.2 requires its dedicated, previously unused validation root")
    readiness = offline_readiness()
    selection, listing, _ = _bound_inputs(EXPECTED_BUNDLE, EXPECTED_REVIEW, EXPECTED_PROFILE)
    history = bind_history()
    original = history["v05c"]["source_record"]
    if vp1_analysis.is_relative_to(Path(original["run_directory"]).resolve()):
        raise ValueError("VP1 reanalysis must be outside the preserved original run")
    protected_count = assert_protected()
    provenance = verify_preflight_files(binary, parameters)
    policy = resolve_policy(read(quality_policy))
    entries = {e["validation_case_id"]: e for e in listing["missions"]}
    for case in CASE_ORDER:
        scene = read(checked_path(EXPECTED_BUNDLE, entries[case]["scene"]))
        if not scene.get("phases") or any(phase.get("terminal_hold_s") != 0 for phase in scene["phases"]):
            raise ValueError("all r1.2 validation cases must have zero terminal hold")
    control = dict(version=VERSION, stage="validation", acceptance_policy=POLICY_VERSION,
        progress_mapping_version=PROGRESS_VERSION, prepared_utc=utc(),
        bundle=str(EXPECTED_BUNDLE.resolve()), review=str(EXPECTED_REVIEW.resolve()),
        profile=str(EXPECTED_PROFILE.resolve()), binary=str(binary), parameters=str(parameters),
        quality_policy=policy, quality_policy_sha256=policy_hash(policy),
        firmware=provenance["actual"]["firmware"], parameters_sha256=file_hash(parameters),
        profile_file_sha256=file_hash(EXPECTED_PROFILE),
        profile_canonical_sha256=selection["source_profile_canonical_sha256"],
        source_review_sha256=file_hash(EXPECTED_REVIEW), protected_file_count=protected_count,
        total_sitl_budget=TOTAL_SITL_BUDGET, historical_attempts_consumed=HISTORICAL_ATTEMPTS,
        max_attempts=MAX_ATTEMPTS, max_extra_retries=MAX_EXTRA_RETRIES,
        planned_cases=list(CASE_ORDER), planned_new_cases=list(NEW_CASE_ORDER),
        terminal_hold_s=0, hold_encoding="integer_seconds_v1", history=history,
        offline_readiness=readiness,
        case_to_mission={case: entries[case]["mission_id"] for case in CASE_ORDER},
        records=[], active_attempt=None, stopped_reason=None, completed=False)
    scene = read(checked_path(EXPECTED_BUNDLE, entries["VP1"]["scene"]))
    metadata, artifacts = analysis_artifacts(original["run_directory"], vp1_analysis, scene, control)
    assessment = assess_artifacts(scene, metadata, artifacts, control)
    control["vp1_reassessment"] = dict(case_id="VP1", run_directory=original["run_directory"],
        run_id=metadata["run_id"], analysis_directory=str(vp1_analysis),
        original_r1_disposition="FAIL", r12_disposition="PASS" if assessment["individual_pass"] else "FAIL",
        individual_pass=assessment["individual_pass"], assessment=assessment,
        evidence_sha256=record_evidence(original["run_directory"], vp1_analysis),
        additional_sitl_attempts=0)
    frozen = list(EXPECTED_BUNDLE.rglob("*.json")) + [EXPECTED_PROFILE, EXPECTED_REVIEW,
        binary, parameters, quality_policy, ROOT / "tmp_v05/m0/protected_baseline.json",
        ROOT / "docs/v0.5_r1.2_addendum.md", ROOT / "scripts/run_mission_list.py",
        ROOT / "scripts/run_v05c_validation.py", Path(__file__)] + list((ROOT / "swarm_sim").glob("*.py"))
    control["frozen_sha256"] = {str(p.resolve()): file_hash(p) for p in frozen}
    if not assessment["individual_pass"]:
        control["stopped_reason"] = "VP1 r1.2 hard gate failed: " + ", ".join(assessment["hard_failures"])
    root.mkdir(parents=True, exist_ok=False)
    _save_atomic(root / "control.json", control)
    return control


def next_case(control):
    if (control.get("version") != VERSION or control.get("max_attempts") != MAX_ATTEMPTS or
            control.get("historical_attempts_consumed") != HISTORICAL_ATTEMPTS or
            control.get("total_sitl_budget") != TOTAL_SITL_BUDGET or
            control.get("max_extra_retries") != MAX_EXTRA_RETRIES or
            control.get("planned_cases") != list(CASE_ORDER) or
            control.get("planned_new_cases") != list(NEW_CASE_ORDER)):
        raise ValueError("invalid r1.2 controller version/budget/plan")
    if control.get("stopped_reason") or control.get("completed"):
        raise ValueError("validation is stopped or complete")
    if control.get("active_attempt") is not None:
        raise ValueError("unresolved reserved attempt; manual audit required")
    if control.get("vp1_reassessment", {}).get("individual_pass") is not True:
        raise ValueError("VP1 r1.2 hard gates have not passed")
    rows = control["records"]
    if len(rows) >= MAX_ATTEMPTS:
        raise ValueError("eight-attempt total validation budget exhausted")
    completed, retry_count = [], 0
    expected_attempt = 0
    for row in rows:
        if (len(completed) >= len(NEW_CASE_ORDER) or row.get("case_id") != NEW_CASE_ORDER[len(completed)] or
                row.get("attempt_index") != expected_attempt):
            raise ValueError("validation attempts do not follow the frozen order")
        if row.get("retryable_pre_takeoff") is True:
            if expected_attempt != 0 or row.get("individual_pass") is not False:
                raise ValueError("only one proven preflight retry is allowed per case")
            expected_attempt = 1
        elif row.get("individual_pass") is True:
            retry_count += expected_attempt
            completed.append(row["case_id"])
            expected_attempt = 0
        else:
            raise ValueError("previous validation case failed its hard gates")
    if len(completed) == len(NEW_CASE_ORDER):
        raise ValueError("all four new validation cases already ran")
    if expected_attempt and retry_count >= MAX_EXTRA_RETRIES:
        raise ValueError("pre-takeoff retry budget exhausted")
    return NEW_CASE_ORDER[len(completed)], expected_attempt


def validation_attempts_clean(control):
    rows = control.get("records", [])
    if not 4 <= len(rows) <= MAX_ATTEMPTS:
        return False
    probe = copy.deepcopy(control)
    probe.update(completed=False, stopped_reason=None, active_attempt=None, records=[])
    for row in rows:
        try:
            expected = next_case(probe)
        except ValueError:
            return False
        if (row.get("case_id"), row.get("attempt_index")) != expected:
            return False
        if row.get("retryable_pre_takeoff") is not True and (row.get("individual_pass") is not True or
                row.get("run_status") != "completed" or row.get("flight_epoch_present") is not True):
            return False
        probe["records"].append(row)
    return [r["case_id"] for r in rows if r.get("individual_pass") is True] == list(NEW_CASE_ORDER)


def assert_integrity(control):
    if control.get("offline_readiness") != offline_readiness():
        raise ValueError("offline M01/M02/M03 readiness binding changed")
    assert_historical_binding(control)
    assert_hashes(control["frozen_sha256"])
    assert_hashes(control["vp1_reassessment"]["evidence_sha256"])
    for row in control["records"]:
        assert_hashes(row.get("evidence_sha256", {}))
    assert_protected()


def run_next(root=EXPECTED_ROOT):
    root = Path(root).resolve()
    if root != EXPECTED_ROOT.resolve():
        raise ValueError("invalid r1.2 validation root")
    path = root / "control.json"
    control = read(path)
    case, attempt_index = next_case(control)
    try:
        assert_integrity(control)
    except Exception as exc:
        control["stopped_reason"] = f"pre-run integrity failure: {type(exc).__name__}: {exc}"
        _save_atomic(path, control)
        raise
    listing, _ = verify_generation(Path(control["bundle"]) / "mission_list.json")
    entry = next(e for e in listing["missions"] if e["validation_case_id"] == case)
    scene = read(checked_path(control["bundle"], entry["scene"]))
    run_root = root / "execution" / case / f"attempt_{attempt_index}"
    row = dict(case_id=case, attempt_index=attempt_index, run_root=str(run_root),
               mission_id=entry["mission_id"], reserved_utc=utc(), evidence_sha256={})
    control["active_attempt"] = copy.deepcopy(row)
    _save_atomic(path, control)
    try:
        ledger = run_mission_list(Path(control["bundle"]) / "mission_list.json", max_runs=1,
            resume=False, output_root=run_root, mission_ids=[entry["mission_id"]],
            binary=control["binary"], parameters=control["parameters"],
            quality_policy=control["quality_policy"], max_environment_retries=0, retryable_errors=())
        result = ledger["missions"][0]["attempts"][0]
        row.update(runner_status=result["status"], runner_error=result.get("error"),
                   run_directory=result.get("run_directory"))
        if not row["run_directory"]:
            raise ValueError("runner returned no directory; takeoff status unproven")
        directory = Path(row["run_directory"])
        metadata = read(directory / "metadata.json")
        parameters = read(directory / "firmware_parameters.json")
        row.update(run_id=metadata.get("run_id"), run_status=metadata.get("status"),
                   flight_epoch_present="flight_epoch_monotonic_s" in metadata)
        reason = preflight_retry_reason(metadata, parameters, _event_rows(directory))
        row.update(retryable_pre_takeoff=reason is not None, retry_reason=reason, individual_pass=False)
        if reason:
            row["evidence_sha256"] = {str(p.resolve()): file_hash(p) for p in directory.rglob("*") if p.is_file()}
        else:
            analyze_run_v3(directory, control["quality_policy"], progress_mapping_version=PROGRESS_VERSION,
                           acceptance_policy=POLICY_VERSION, acceptance_stage="validation", update_latest=True)
            latest = read(directory / "analysis_latest.json")
            analysis = checked_path(directory, latest["directory"])
            if file_hash(analysis / "manifest.json") != latest["manifest_sha256"]:
                raise ValueError("selected r1.2 analysis manifest changed")
            metadata, artifacts = analysis_artifacts(directory, analysis, scene, control)
            assessment = assess_artifacts(scene, metadata, artifacts, control)
            row.update(analysis_directory=str(analysis), assessment=assessment,
                       individual_pass=assessment["individual_pass"],
                       evidence_sha256=record_evidence(directory, analysis))
            if not row["individual_pass"]:
                row["stopped_reason"] = "r1.2 hard gate failed: " + ", ".join(assessment["hard_failures"])
        assert_integrity(control)
        row["finished_utc"] = utc()
    except BaseException as exc:
        row.update(individual_pass=False, retryable_pre_takeoff=False,
                   stopped_reason=f"unresolved attempt: {type(exc).__name__}: {exc}", finished_utc=utc())
        control.update(stopped_reason=row["stopped_reason"], active_attempt=None)
        control["records"].append(row)
        _save_atomic(path, control)
        raise
    control["records"].append(row)
    control["active_attempt"] = None
    if row.get("stopped_reason"):
        control["stopped_reason"] = row["stopped_reason"]
    elif case == "VR2" and row["individual_pass"]:
        control["completed"] = True
    else:
        try:
            next_case(control)
        except ValueError as exc:
            control["stopped_reason"] = str(exc)
    control["sitl_attempts_consumed"] = HISTORICAL_ATTEMPTS + len(control["records"])
    _save_atomic(path, control)
    return row, control


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "next"))
    parser.add_argument("--root", type=Path, default=EXPECTED_ROOT)
    parser.add_argument("--vp1-analysis", type=Path)
    parser.add_argument("--sitl", type=Path, default=ROOT / "ArducopterSITL/arducopter.exe")
    parser.add_argument("--parameters", type=Path, default=ROOT / "ArducopterSITL/copter.parm")
    parser.add_argument("--quality-policy", type=Path, default=ROOT / "quality_policies/default_v022.json")
    args = parser.parse_args(argv)
    if args.action == "prepare":
        if args.vp1_analysis is None:
            parser.error("prepare requires --vp1-analysis")
        control = prepare(args.root, args.vp1_analysis, args.sitl, args.parameters, args.quality_policy)
    else:
        _, control = run_next(args.root)
    print(json.dumps({key: control.get(key) for key in ("version", "completed", "stopped_reason",
        "historical_attempts_consumed", "sitl_attempts_consumed", "planned_new_cases")}, ensure_ascii=False))
    return int(bool(control.get("stopped_reason")))


if __name__ == "__main__":
    raise SystemExit(main())
