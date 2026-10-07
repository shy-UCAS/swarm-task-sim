"""Resume PP09--PP20 with immutable history and the user-approved r1.2b gates.

Only ``next`` launches one mission. Infrastructure failures stop without retry.
Historical ledgers, analyses and latest pointers are never modified.
"""
import argparse
import copy
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_mission_list import _save_atomic, run_mission_list
from scripts.run_v05c_pp import (INTENT_ORDER, LOGICAL_RUNS, MAX_ATTEMPTS, MAX_EXTRA_RETRIES,
    _description_gate, _event_rows, aggregate_status, assert_hashes, assert_protected, read, terminal_rows, utc)
from scripts.run_v05_r12_pp import pilot_acceptance_gates
from scripts.run_v05_r12_validation import ARTIFACTS, preflight_retry_reason, record_evidence
from swarm_sim.analysis_v3 import analyze_run_v3
from swarm_sim.dataset import build_dataset
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.episode_loader import load_episode, load_public_scene
from swarm_sim.generation import canonical_hash, checked_path, file_hash, save_json, verify_generation
from swarm_sim.language_v0 import describe_dataset
from swarm_sim.protocol import manifest_protocol, semantic_protocol, validate_artifact_protocol
from swarm_sim.run_provenance import verify_preflight_files
from swarm_sim.validation_policy_r12b import VERSION as POLICY_VERSION, assess_run, assess_recent_runs

VERSION = "v05_r12b_pilot_controller_v1"
ROOT_OUTPUT = ROOT / "verification/v05_r12b_pp_20261002"
HISTORY = ROOT / "verification/v05_r12_pp_20261002/control.json"
VALIDATION = ROOT / "verification/v05_r12_validation_20261002/control.json"
PATROL_REVIEW = ROOT / "tmp_v05/r12b/patrol_reanalysis_02/comparison.json"
PROGRESS_VERSION = "ordered_route_progress_v2"
PATROL_VERSION = "perimeter_revisit_v2"
INHERITED = 8


def hash_tree(root):
    return {str(p.resolve()): file_hash(p) for p in sorted(Path(root).rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def integrity(control, *, include_runtime=True):
    assert_hashes(control["historical_sha256"])
    assert_hashes(control["bundle_sha256"])
    assert_hashes(control.get("runtime_archive_sha256", {}))
    if include_runtime:
        assert_hashes(control["runtime_sha256"])
    for row in control["records"]:
        assert_hashes(row.get("evidence_sha256", {}))
    assert_protected()


def assert_binding(control, root):
    if (Path(root).resolve() != ROOT_OUTPUT.resolve() or control.get("version") != VERSION
            or control.get("stage") != "pilot" or control.get("acceptance_policy") != POLICY_VERSION
            or control.get("max_attempts") != MAX_ATTEMPTS or control.get("max_extra_retries") != MAX_EXTRA_RETRIES
            or control.get("rolling_start_logical_index") != INHERITED
            or control.get("hold_s") != 0 or type(control.get("hold_s")) is not int
            or control.get("progress_mapping_version") != PROGRESS_VERSION
            or control.get("patrol_validator_version") != PATROL_VERSION
            or Path(control.get("bundle", "")).resolve() != (ROOT_OUTPUT / "bundle").resolve()
            or len(control.get("planned_missions", [])) != 20
            or len(set(control.get("planned_missions", []))) != 20):
        raise ValueError("invalid r1.2b pilot binding")
    old = read(HISTORY)
    if control["inherited_records"] != old["records"] or len(control["inherited_records"]) != INHERITED:
        raise ValueError("inherited attempts differ from immutable history")
    if control["planned_missions"] != old["planned_missions"]:
        raise ValueError("frozen mission order changed")
    for index, source in enumerate(control["inherited_records"]):
        if control["records"][index].get("source_record") != source:
            raise ValueError("derived record lost its original evidence or disposition")


def next_mission(control):
    if (control.get("version") != VERSION or control.get("stopped_reason") or control.get("completed")
            or control.get("active_attempt") is not None):
        raise ValueError("pilot is stopped, complete, invalid or has an unresolved attempt")
    if control.get("max_attempts") != MAX_ATTEMPTS or control.get("max_extra_retries") != MAX_EXTRA_RETRIES:
        raise ValueError("pilot attempt budget changed")
    rows = control["records"]
    if len(rows) >= MAX_ATTEMPTS:
        raise ValueError("22-attempt budget exhausted")
    # This continuation never clears a stop or automatically schedules a retry.
    # Proven pre-takeoff failures retain their retry eligibility for a user decision.
    if len(rows) < INHERITED or [r.get("logical_index") for r in rows] != list(range(len(rows))):
        raise ValueError("pilot records no longer follow inherited then PP09--PP20 order")
    if any(r.get("attempt_index") != 0 or r.get("retryable_pre_takeoff") for r in rows):
        raise ValueError("infrastructure attempt requires an explicit recovery decision")
    if any(r.get("hard_failures") for r in rows[INHERITED:]):
        raise ValueError("new attempt failed a hard gate")
    if len(rows) >= LOGICAL_RUNS:
        raise ValueError("all twenty missions attempted")
    return len(rows), 0


def rolling_status(control):
    return assess_recent_runs([dict(run_id=r["run_id"], stage="pilot", assessment=r["assessment"])
        for r in control["records"] if r["logical_index"] >= INHERITED and r.get("assessment")], stage="pilot")


def disk_status(control):
    remaining = max(0, LOGICAL_RUNS - len(terminal_rows(control["records"])))
    estimate = control["storage_estimate"]
    # Largest measured historical run includes its raw data and automatic analysis;
    # allow one new explicit analysis per remaining run and all twenty exports.
    required = remaining * (estimate["max_run_bytes"] + estimate["max_analysis_bytes"])
    required += LOGICAL_RUNS * estimate["max_analysis_bytes"]
    free = shutil.disk_usage(ROOT_OUTPUT.parent).free
    return dict(free_bytes=free, required_remaining_bytes=required, remaining_runs=remaining,
                basis="largest_PP01_PP08_run_plus_explicit_analysis_and_twenty_exports", pass_gate=free >= required)


def selected_artifacts(directory, analysis, scene, control):
    directory, analysis = Path(directory), Path(analysis)
    metadata, manifest = read(directory / "metadata.json"), read(analysis / "manifest.json")
    if (canonical_hash(metadata.get("scenario")) != canonical_hash(scene)
            or metadata.get("run_id") != manifest.get("run_id")
            or Path(manifest.get("run_directory", "")).resolve() != directory.resolve()
            or metadata.get("quality_policy_sha256") != control["quality_policy_sha256"]
            or manifest.get("quality_policy_sha256") != control["quality_policy_sha256"]
            or manifest.get("route_progress_version") != PROGRESS_VERSION
            or manifest_protocol(manifest) != semantic_protocol(scene, patrol_validator_version=PATROL_VERSION)
            or manifest.get("acceptance_policy_version") != POLICY_VERSION):
        raise ValueError("selected analysis source/protocol/policy mismatch")
    assert_hashes({str(checked_path(analysis, k)): v for k, v in manifest["artifact_sha256"].items()})
    assert_hashes({str(checked_path(directory, k)): v for k, v in manifest["source_sha256"].items()})
    validate_artifact_protocol(manifest, analysis)
    artifacts = {name: read(analysis / (name + ".json")) for name in ARTIFACTS}
    if artifacts["quality"].get("validation_policy", {}).get("stage") != "pilot":
        raise ValueError("selected analysis acceptance stage differs")
    return metadata, artifacts


def assess_artifacts(scene, metadata, artifacts, control):
    quality, labels = artifacts["quality"], artifacts["labels"]
    assessment = assess_run(scene, metadata, quality, labels, artifacts["execution_metrics"],
        artifacts["ac4_timing_v3"], artifacts["onboard_mission_param_check"], stage="pilot")
    if assessment != quality["validation_policy"]:
        raise ValueError("stored policy assessment differs from independent recomputation")
    firmware = metadata.get("binary_firmware", {})
    bound = (firmware.get("sha256") == control["firmware"]["sha256"]
        and firmware.get("version_string") == control["firmware"]["version_string"]
        and metadata.get("parameters_sha256") == control["parameters_sha256"])
    agents = {v["id"] for v in scene["vehicles"]}
    cleanup = metadata.get("cleanup", {})
    clean = set(cleanup) == agents and all(type(cleanup[a]) is int for a in agents)
    checks = dict(frozen_firmware_and_parameters=bound, infrastructure_cleanup_complete=clean,
                  infrastructure_execution_completed=metadata.get("status") == "completed")
    assessment["hard_checks"].update(checks)
    assessment["hard_failures"].extend(k for k, v in checks.items() if not v)
    assessment["individual_pass"] = not assessment["hard_failures"]
    return dict(qualified=quality.get("episode_quality_eligible") is True,
        accepted_for_pp=quality.get("episode_quality_eligible") is True,
        episode_quality_eligible=quality.get("episode_quality_eligible"),
        mission_success=labels.get("mission_success"), mission_success_observation=labels.get("mission_success_observation"),
        semantic_consistency=labels.get("semantic_consistency"), run_status=metadata.get("status"),
        hard_failures=assessment["hard_failures"], soft_flags=assessment["soft_flags"],
        semantic_flags=assessment.get("semantic_flags", []), new_anomalies=assessment.get("new_anomalies", []),
        assessment=assessment)


def analyze_selected(directory, output, scene, control):
    analyze_run_v3(directory, control["quality_policy"], progress_mapping_version=PROGRESS_VERSION,
        patrol_validator_version=PATROL_VERSION, acceptance_policy=POLICY_VERSION,
        acceptance_stage="pilot", output_directory=output, update_latest=False)
    metadata, artifacts = selected_artifacts(directory, output, scene, control)
    return assess_artifacts(scene, metadata, artifacts, control)


def prepare(root=ROOT_OUTPUT, *, source_commit):
    root = Path(root).resolve()
    if root != ROOT_OUTPUT.resolve() or root.exists() or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("new dedicated continuation root and full source commit required")
    old, validation = read(HISTORY), read(VALIDATION)
    if (old.get("stopped_reason") != "known_consistent_labels" or old.get("active_attempt") is not None
            or len(old["records"]) != INHERITED or old.get("completed") or old.get("finalized")
            or not validation.get("completed") or validation.get("sitl_attempts_consumed") != 6
            or validation.get("stopped_reason") or validation.get("active_attempt") is not None
            or [r["logical_index"] for r in old["records"]] != list(range(INHERITED))
            or any(r["attempt_index"] or r.get("retryable_pre_takeoff") for r in old["records"])):
        raise ValueError("historical ledgers differ from accepted handoff")
    inventory = read(ROOT / "tmp_v05/r12b/input_inventory.json")
    assert_hashes(inventory["immutable_pre_sha256"])
    protected = assert_protected()
    provenance = verify_preflight_files(old["binary"], old["parameters"])
    if provenance["actual"]["firmware"] != old["firmware"]:
        raise ValueError("firmware identity differs from pilot history")
    historical = dict(inventory["immutable_pre_sha256"])
    for folder in (HISTORY.parent, VALIDATION.parent, ROOT / "tmp_v05/r12b"):
        historical.update(hash_tree(folder))
    historical[str((ROOT.parent / ".claude/progress/progress_20261002_202310.md").resolve())] = file_hash(
        ROOT.parent / ".claude/progress/progress_20261002_202310.md")
    runtime_files = list((ROOT / "swarm_sim").glob("*.py")) + list((ROOT / "scripts").glob("*.py"))
    runtime_files += [ROOT / "docs/v0.5_当前有效规则.md", ROOT / "docs/v0.5_r1.2_addendum.md",
                     ROOT / "docs/data_contract_v0.md", ROOT.parent / "CLAUDE.md",
                     Path(old["binary"]), Path(old["parameters"])]
    runtime = {str(p.resolve()): file_hash(p) for p in runtime_files}
    root.mkdir(parents=True)
    shutil.copytree(old["bundle"], root / "bundle")
    # Archive the exact authorized source/rules, including documents that will
    # later receive final budgets. Never rewrite a historical hash declaration.
    for source in runtime_files:
        if source.suffix not in (".py", ".md"):
            continue
        target = root / "runtime_snapshot" / source.resolve().relative_to(ROOT.parent.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    listing, _ = verify_generation(root / "bundle/mission_list.json")
    sizes = [sum(p.stat().st_size for p in Path(r["run_directory"]).rglob("*") if p.is_file()) for r in old["records"]]
    analysis_sizes = [sum(p.stat().st_size for p in Path(r["analysis_directory"]).iterdir() if p.is_file()) for r in old["records"]]
    control = dict(version=VERSION, stage="pilot", acceptance_policy=POLICY_VERSION,
        progress_mapping_version=PROGRESS_VERSION, patrol_validator_version=PATROL_VERSION,
        prepared_utc=utc(), source_commit=source_commit, bundle=str(root / "bundle"),
        formal_profile=old["formal_profile"], formal_generation=old["formal_generation"],
        validation_control=str(VALIDATION), history_control=str(HISTORY), history_control_sha256=file_hash(HISTORY),
        prior_patrol_comparison=str(PATROL_REVIEW), prior_patrol_comparison_sha256=file_hash(PATROL_REVIEW),
        inherited_records=copy.deepcopy(old["records"]), inherited_attempt_count=INHERITED,
        original_stopped_reason=old["stopped_reason"], hold_s=0, hold_encoding="integer_seconds_v1",
        binary=old["binary"], parameters=old["parameters"], firmware=old["firmware"],
        parameters_sha256=old["parameters_sha256"], quality_policy=old["quality_policy"],
        quality_policy_sha256=old["quality_policy_sha256"], protected_file_count=protected,
        historical_sha256=historical, runtime_sha256=runtime,
        runtime_archive_sha256=hash_tree(root / "runtime_snapshot"), bundle_sha256=hash_tree(root / "bundle"),
        planned_missions=copy.deepcopy(old["planned_missions"]), records=[], active_attempt=None,
        stopped_reason=None, completed=False, finalized=False, max_attempts=MAX_ATTEMPTS,
        max_extra_retries=MAX_EXTRA_RETRIES, rolling_start_logical_index=INHERITED,
        storage_estimate=dict(max_run_bytes=max(sizes), max_analysis_bytes=max(analysis_sizes)))
    _save_atomic(root / "control.json", control)
    try:
        (root / "analyses").mkdir()
        for source in old["records"]:
            index = source["logical_index"]
            scene = read(checked_path(root / "bundle", listing["missions"][index]["scene"]))
            analysis = root / "analyses" / f"PP{index+1:02d}_inherited"
            result = analyze_selected(Path(source["run_directory"]), analysis, scene, control)
            row = copy.deepcopy(source)
            row.update(result, source_record=copy.deepcopy(source), inherited=True,
                analysis_directory=str(analysis), evidence_sha256=record_evidence(source["run_directory"], analysis))
            control["records"].append(row)
            _save_atomic(root / "control.json", control)
        integrity(control)
        assert_binding(control, root)
        control["aggregate"] = aggregate_status(control["records"])
        control["rolling"] = rolling_status(control)
        control["initial_disk_check"] = disk_status(control)
        if not control["initial_disk_check"]["pass_gate"]:
            control["stopped_reason"] = "insufficient_disk_space"
        _save_atomic(root / "control.json", control)
    except BaseException as exc:
        control["stopped_reason"] = f"continuation preparation infrastructure failure: {type(exc).__name__}: {exc}"
        _save_atomic(root / "control.json", control)
        raise
    return control


def complete_record(control, row):
    control["records"].append(row)
    control["active_attempt"] = None
    control["aggregate"] = aggregate_status(control["records"])
    control["rolling"] = rolling_status(control)
    if row.get("hard_failures"):
        control["stopped_reason"] = "; ".join(row["hard_failures"])
    elif control["rolling"]["stop"]:
        control["stopped_reason"] = "rolling_anomalous_runs_at_least_5"
    elif len(terminal_rows(control["records"])) == LOGICAL_RUNS:
        control["completed"] = True


def run_next(root=ROOT_OUTPUT):
    root = Path(root).resolve()
    path = root / "control.json"
    control = read(path)
    assert_binding(control, root)
    logical, attempt_index = next_mission(control)
    try:
        integrity(control)
        verify_preflight_files(control["binary"], control["parameters"])
        disk = disk_status(control)
        control.setdefault("disk_checks", []).append(dict(logical_index=logical, checked_utc=utc(), **disk))
        if not disk["pass_gate"]:
            raise OSError("insufficient_disk_space")
    except BaseException as exc:
        control["stopped_reason"] = f"pre-run hard gate: {type(exc).__name__}: {exc}"
        _save_atomic(path, control)
        raise
    listing, _ = verify_generation(Path(control["bundle"]) / "mission_list.json")
    entry = listing["missions"][logical]
    if entry["mission_id"] != control["planned_missions"][logical]:
        raise ValueError("pilot mission order changed")
    scene = read(checked_path(control["bundle"], entry["scene"]))
    run_root = root / "execution" / f"{logical:02d}_{entry['intent']}" / "attempt_0"
    row = dict(logical_index=logical, attempt_index=attempt_index, run_root=str(run_root),
        reserved_utc=utc(), mission_id=entry["mission_id"], base_index=entry["base_index"], intent=entry["intent"],
        inherited=False, evidence_sha256={}, retryable_pre_takeoff=False)
    control["active_attempt"] = copy.deepcopy(row)
    _save_atomic(path, control)
    try:
        ledger = run_mission_list(Path(control["bundle"]) / "mission_list.json", max_runs=1, resume=False,
            output_root=run_root, mission_ids=[entry["mission_id"]], binary=control["binary"],
            parameters=control["parameters"], quality_policy=control["quality_policy"],
            max_environment_retries=0, retryable_errors=())
        attempt = ledger["missions"][0]["attempts"][0]
        row.update(runner_status=attempt["status"], runner_error=attempt.get("error"), run_directory=attempt.get("run_directory"))
        if not row["run_directory"]:
            raise RuntimeError("runner infrastructure failure: no run directory")
        directory = Path(row["run_directory"])
        metadata = read(directory / "metadata.json")
        reason = preflight_retry_reason(metadata, read(directory / "firmware_parameters.json"), _event_rows(directory))
        row.update(run_id=metadata.get("run_id"), retryable_pre_takeoff=reason is not None,
                   retry_reason=reason, run_status=metadata.get("status"))
        analysis = root / "analyses" / f"PP{logical+1:02d}_attempt_0"
        row.update(analyze_selected(directory, analysis, scene, control), analysis_directory=str(analysis))
        if reason:
            row["hard_failures"].append("infrastructure_pre_takeoff_failure")
        row["evidence_sha256"] = hash_tree(run_root)
        row["evidence_sha256"].update(hash_tree(analysis))
        integrity(control)
        row["finished_utc"] = utc()
    except BaseException as exc:
        row.update(qualified=False, accepted_for_pp=False,
            hard_failures=[f"infrastructure_or_integrity_failure: {type(exc).__name__}: {exc}"], finished_utc=utc())
        row["evidence_sha256"].update(hash_tree(run_root))
        complete_record(control, row)
        _save_atomic(path, control)
        raise
    complete_record(control, row)
    _save_atomic(path, control)
    return row, control


def finalize(root=ROOT_OUTPUT):
    root = Path(root).resolve()
    path = root / "control.json"
    control = read(path)
    assert_binding(control, root)
    if control.get("stopped_reason") or not control.get("completed") or control.get("finalized") or control.get("active_attempt"):
        raise ValueError("pilot is not complete/clean or was already finalized")
    try:
        integrity(control)
        rows = terminal_rows(control["records"])
        if len(rows) != 20 or [r["logical_index"] for r in rows] != list(range(20)):
            raise ValueError("twenty terminal runs required")
        selections = {str(Path(r["run_directory"]).resolve()): dict(directory=r["analysis_directory"],
            manifest_sha256=file_hash(Path(r["analysis_directory"]) / "manifest.json")) for r in rows}
        save_json(root / "analysis_selections.json", selections)
        audit_ledger = root / "audit_attempt_ledger.json"
        save_json(audit_ledger, dict(schema_version=1, source=VERSION, missions=[dict(mission_id=mission_id,
            attempts=[dict(run_directory=r.get("run_directory"), run_status=r.get("run_status"),
                status=r.get("runner_status"), intent=r["intent"], episode_quality_eligible=r.get("episode_quality_eligible"))
                for r in control["records"] if r["mission_id"] == mission_id]) for mission_id in control["planned_missions"]]))
        dataset, language = root / "dataset", root / "dataset_language_zh_v0"
        manifest = build_dataset([r["run_directory"] for r in rows], dataset, analysis_selections=selections)
        audit = audit_dataset(dataset, generation_manifest=Path(control["bundle"]) / "generation_manifest.json", attempt_ledger=audit_ledger)
        save_json(root / "dataset_audit.json", audit)
        describe_dataset(dataset, language)
        descriptions = _description_gate(dataset, language)
        loaded = []
        for entry in manifest["episodes"]:
            episode_path = checked_path(dataset, entry["directory"])
            episode, corners = load_episode(episode_path, verify_hashes=True), load_public_scene(episode_path)
            loaded.append(dict(run_id=entry["run_id"], frames=len(episode["t_s"]), agents=len(episode["agent_ids"]),
                corner_count=len(corners), corner_dimensions=[len(c) for c in corners]))
        aggregate = aggregate_status(control["records"])
        gates = pilot_acceptance_gates(aggregate, manifest, audit, descriptions, loaded)
        result = dict(version="v05_r12b_pilot_acceptance_v1", gate=gates, aggregate=aggregate,
            description_check=descriptions, loaded=loaded, rolling=control["rolling"],
            soft_flags_by_run=[dict(run_id=r["run_id"], intent=r["intent"], soft_flags=r["soft_flags"]) for r in rows],
            dataset_manifest_sha256=file_hash(dataset / "dataset_manifest.json"), audit_sha256=file_hash(root / "dataset_audit.json"),
            language_manifest_sha256=file_hash(language / "language_manifest.json"), audit_issues=audit.get("issues", []),
            source_control_sha256=file_hash(path), completed_utc=utc())
        integrity(control)
        save_json(root / "acceptance.json", result)
        control.update(finalized=True, final_gate_pass=gates["pass"])
        if not gates["pass"]:
            control["stopped_reason"] = "r1_section_11_3_final_acceptance_failed"
        _save_atomic(path, control)
        return result
    except BaseException as exc:
        control["stopped_reason"] = f"pilot finalization infrastructure failure: {type(exc).__name__}: {exc}"
        _save_atomic(path, control)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "next", "finalize"))
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    if args.action == "prepare":
        control = prepare(source_commit=args.source_commit or "")
    elif args.action == "next":
        _, control = run_next()
    else:
        result = finalize()
        print(json.dumps(dict(gate=result["gate"], aggregate=result["aggregate"]), ensure_ascii=False))
        return int(not result["gate"]["pass"])
    print(json.dumps({k: control.get(k) for k in ("version", "completed", "stopped_reason", "aggregate", "rolling")}, ensure_ascii=False))
    return int(bool(control.get("stopped_reason")))


if __name__ == "__main__":
    raise SystemExit(main())
