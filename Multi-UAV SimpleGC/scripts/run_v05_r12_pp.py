"""r1.2 pilot: first ten v05c scenes, alternating intents, then pause 1.

The hold is formally zero; there is no HD decision or regenerated profile.
Only ``next`` starts SITL. Final acceptance is exactly r1 section 11.3.
"""

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_mission_list import _save_atomic, run_mission_list
from scripts.run_v05c_pp import (
    BINARY, PARAMETERS, QUALITY_POLICY, DR_PROFILE, DR_GENERATED, DR_REVIEW,
    INTENT_ORDER, LOGICAL_RUNS, MAX_ATTEMPTS, MAX_EXTRA_RETRIES,
    _dr_inputs, _description_gate, _event_rows, aggregate_status,
    assert_hashes, assert_protected,
    terminal_rows, read, utc,
)
from scripts.run_v05_r12_validation import (
    VERSION as VALIDATION_VERSION, EXPECTED_ROOT as VALIDATION_ROOT,
    POLICY_VERSION, PROGRESS_VERSION, CASE_ORDER, NEW_CASE_ORDER,
    analysis_artifacts, assess_artifacts, assert_integrity as assert_validation_integrity,
    preflight_retry_reason, record_evidence, validation_attempts_clean,
)
from swarm_sim.analysis_v3 import analyze_run_v3
from swarm_sim.dataset import build_dataset
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.episode_loader import load_episode, load_public_scene
from swarm_sim.generation import canonical_hash, checked_path, file_hash, save_json, verify_generation
from swarm_sim.generation_v2 import normalize_profile
from swarm_sim.language_v0 import describe_dataset
from swarm_sim.quality import policy_hash, resolve_policy
from swarm_sim.run_provenance import verify_preflight_files

VERSION = "v05_r12_pilot_controller_v1"
ROOT_OUTPUT = ROOT / "verification/v05_r12_pp_20261002"


def validation_check(path):
    path = Path(path).resolve()
    if path != (VALIDATION_ROOT / "control.json").resolve():
        raise ValueError("pilot requires the dedicated r1.2 validation controller")
    control = read(path)
    if (control.get("version") != VALIDATION_VERSION or control.get("completed") is not True or
            control.get("stopped_reason") or control.get("active_attempt") is not None or
            control.get("planned_cases") != list(CASE_ORDER) or
            control.get("planned_new_cases") != list(NEW_CASE_ORDER) or
            control.get("terminal_hold_s") != 0 or control.get("historical_attempts_consumed") != 2 or
            control.get("vp1_reassessment", {}).get("individual_pass") is not True or
            not validation_attempts_clean(control)):
        raise ValueError("r1.2 validation has not passed all five cases within budget")
    assert_validation_integrity(control)
    return control


def assert_controller_binding(control, root):
    root = Path(root).resolve()
    if (root != ROOT_OUTPUT.resolve() or control.get("version") != VERSION or
            control.get("stage") != "pilot" or control.get("acceptance_policy") != POLICY_VERSION or
            control.get("progress_mapping_version") != PROGRESS_VERSION or
            Path(control.get("bundle", "")).resolve() != (root / "bundle").resolve() or
            Path(control.get("validation_control", "")).resolve() != (VALIDATION_ROOT / "control.json").resolve() or
            Path(control.get("formal_profile", "")).resolve() != DR_PROFILE.resolve() or
            Path(control.get("formal_generation", "")).resolve() != DR_GENERATED.resolve() or
            control.get("max_attempts") != MAX_ATTEMPTS or
            control.get("max_extra_retries") != MAX_EXTRA_RETRIES or
            type(control.get("hold_s")) is not int or control["hold_s"] != 0 or
            len(control.get("planned_missions", [])) != LOGICAL_RUNS or
            len(set(control.get("planned_missions", []))) != LOGICAL_RUNS):
        raise ValueError("pilot controller is not bound to the r1.2 plan and hold=0")


def prepare(root=ROOT_OUTPUT, validation_path=VALIDATION_ROOT / "control.json",
            binary=BINARY, parameters=PARAMETERS, quality_policy=QUALITY_POLICY):
    root, validation_path = Path(root).resolve(), Path(validation_path).resolve()
    binary, parameters, quality_policy = [Path(p).resolve() for p in (binary, parameters, quality_policy)]
    if root != ROOT_OUTPUT.resolve() or root.exists():
        raise ValueError("pilot requires its dedicated, previously unused r1.2 root")
    validation = validation_check(validation_path)
    protected_count = assert_protected()
    source_profile, source_generated, source_review = [p.resolve() for p in (DR_PROFILE, DR_GENERATED, DR_REVIEW)]
    listing, manifest, formal_review, invariance, by_base = _dr_inputs(
        source_profile, source_generated, source_review, source_profile, source_generated, 0)
    provenance = verify_preflight_files(binary, parameters)
    policy = resolve_policy(read(quality_policy))
    root.mkdir(parents=True, exist_ok=False)
    bundle = root / "bundle"
    (bundle / "missions").mkdir(parents=True)
    (bundle / "scenes").mkdir()
    (bundle / "generation_profile.json").write_bytes((source_generated / "generation_profile.json").read_bytes())
    save_json(root / "formal_dr_review.json", formal_review)
    plan = []
    for base in range(10):
        for intent in INTENT_ORDER:
            original = by_base[base][intent]
            entry = copy.deepcopy(original)
            if entry["candidate_id"] != manifest["bases"][base]["selected_candidate"]:
                raise ValueError("pilot entry differs from original selected v05c candidate")
            entry.update(pilot_index=len(plan), task=f"missions/{entry['mission_id']}.json",
                         scene=f"scenes/{entry['mission_id']}.json")
            for name in ("task", "scene"):
                (bundle / entry[name]).write_bytes(checked_path(source_generated, original[name]).read_bytes())
                entry[name + "_sha256"] = file_hash(bundle / entry[name])
            plan.append(entry)
    selection = dict(version=VERSION, hold_s=0, hold_encoding="integer_seconds_v1", prepared_utc=utc(),
        source_profile_file_sha256=file_hash(source_profile),
        source_profile_canonical_sha256=canonical_hash(normalize_profile(source_profile)),
        source_manifest_sha256=file_hash(source_generated / "generation_manifest.json"),
        source_review_sha256=file_hash(source_review), validation_control_sha256=file_hash(validation_path),
        candidate_invariance=invariance,
        accepted_first_ten=[dict(base_index=i, candidate_id=manifest["bases"][i]["selected_candidate"],
                                 family_id=manifest["bases"][i]["family_id"]) for i in range(10)],
        order=[{k: e[k] for k in ("pilot_index", "base_index", "intent", "mission_id")} for e in plan])
    save_json(bundle / "selection.json", selection)
    subset = copy.deepcopy(listing)
    subset["missions"] = plan
    save_json(bundle / "mission_list.json", subset)
    candidates = [c for c in manifest["candidates"] if c["base_index"] < 10]
    subset_manifest = dict(schema_version=2, generator_version="v05_r12_pilot_bundle_v1",
        source_generation_manifest_sha256=selection["source_manifest_sha256"],
        source_dr_review_sha256=selection["source_review_sha256"],
        validation_control_sha256=selection["validation_control_sha256"],
        profile_sha256=selection["source_profile_canonical_sha256"],
        bases=manifest["bases"][:10], candidates=candidates,
        counts=dict(base_scenes=10, accepted_bases=10, candidates=len(candidates),
                    accepted_candidates=sum(c["status"] == "accepted" for c in candidates), planned_missions=20),
        artifact_sha256={p.relative_to(bundle).as_posix(): file_hash(p) for p in sorted(bundle.rglob("*.json"))})
    save_json(bundle / "generation_manifest.json", subset_manifest)
    verify_generation(bundle / "mission_list.json")
    frozen = list(bundle.rglob("*.json")) + [root / "formal_dr_review.json", validation_path,
        source_profile, source_generated / "generation_manifest.json", source_review,
        quality_policy, binary, parameters, ROOT / "tmp_v05/m0/protected_baseline.json",
        ROOT / "docs/v0.5_r1.2_addendum.md", ROOT / "scripts/run_mission_list.py",
        ROOT / "scripts/run_v05_r12_validation.py", ROOT / "scripts/run_v05c_pp.py", Path(__file__)
    ] + list((ROOT / "swarm_sim").glob("*.py"))
    hashes = {str(p.resolve()): file_hash(p) for p in frozen}
    for history in validation["history"].values():
        if isinstance(history, dict):
            hashes.update(history["source_evidence_sha256"])
    hashes.update(validation["vp1_reassessment"]["evidence_sha256"])
    for row in validation["records"]:
        hashes.update(row["evidence_sha256"])
    control = dict(version=VERSION, stage="pilot", acceptance_policy=POLICY_VERSION,
        progress_mapping_version=PROGRESS_VERSION, prepared_utc=utc(), bundle=str(bundle),
        formal_profile=str(source_profile), formal_generation=str(source_generated),
        validation_control=str(validation_path), validation_control_sha256=file_hash(validation_path),
        hold_s=0, hold_encoding="integer_seconds_v1", binary=str(binary), parameters=str(parameters),
        firmware=provenance["actual"]["firmware"], parameters_sha256=file_hash(parameters),
        quality_policy=policy, quality_policy_sha256=policy_hash(policy),
        protected_file_count=protected_count, frozen_sha256=hashes,
        planned_missions=[e["mission_id"] for e in plan], records=[], active_attempt=None,
        stopped_reason=None, completed=False, finalized=False,
        max_attempts=MAX_ATTEMPTS, max_extra_retries=MAX_EXTRA_RETRIES)
    _save_atomic(root / "control.json", control)
    return control


def next_mission(control):
    if (control.get("version") != VERSION or control.get("max_attempts") != MAX_ATTEMPTS or
            control.get("max_extra_retries") != MAX_EXTRA_RETRIES or control.get("stopped_reason") or
            control.get("completed") or control.get("active_attempt") is not None):
        raise ValueError("pilot is stopped, complete, invalid or has an unresolved attempt")
    rows = control["records"]
    if len(rows) >= MAX_ATTEMPTS:
        raise ValueError("22-attempt pilot budget exhausted")
    logical, attempt, retries = 0, 0, 0
    for row in rows:
        if row.get("logical_index") != logical or row.get("attempt_index") != attempt:
            raise ValueError("pilot attempts do not follow the frozen order")
        if row.get("hard_failures"):
            raise ValueError("previous pilot attempt failed a hard gate")
        if row.get("retryable_pre_takeoff") is True:
            if attempt:
                raise ValueError("one preflight retry per mission exhausted")
            attempt = 1
        else:
            retries += attempt
            logical += 1
            attempt = 0
    if logical >= LOGICAL_RUNS:
        raise ValueError("all twenty pilot missions were attempted")
    if attempt and retries >= MAX_EXTRA_RETRIES:
        raise ValueError("two preflight retry allowance exhausted")
    return logical, attempt


def assess_run(scene, metadata, artifacts, control):
    if artifacts is None:
        return dict(qualified=False, accepted_for_pp=False, episode_quality_eligible=None,
            mission_success=None, semantic_consistency=None, run_status=metadata.get("status"),
            hard_failures=["analysis missing; trajectory/label correctness unknown"], soft_flags=[])
    assessment = assess_artifacts(scene, metadata, artifacts, control)
    quality, labels = artifacts["quality"], artifacts["labels"]
    eligible = quality.get("episode_quality_eligible") is True
    return dict(qualified=eligible, accepted_for_pp=eligible,
        episode_quality_eligible=quality.get("episode_quality_eligible"),
        mission_success=labels.get("mission_success"), mission_success_observation=labels.get("mission_success_observation"),
        semantic_consistency=labels.get("semantic_consistency"), run_status=metadata.get("status"),
        hard_failures=assessment["hard_failures"], soft_flags=assessment["soft_flags"], assessment=assessment)


def integrity(control):
    assert_hashes(control["frozen_sha256"])
    for row in control["records"]:
        assert_hashes(row.get("evidence_sha256", {}))
    assert_protected()


def run_next(root=ROOT_OUTPUT):
    root = Path(root).resolve()
    path = root / "control.json"
    control = read(path)
    assert_controller_binding(control, root)
    logical, attempt_index = next_mission(control)
    try:
        integrity(control)
    except Exception as exc:
        control["stopped_reason"] = f"pre-run integrity failure: {type(exc).__name__}: {exc}"
        _save_atomic(path, control)
        raise
    listing, _ = verify_generation(Path(control["bundle"]) / "mission_list.json")
    entry = listing["missions"][logical]
    if entry["mission_id"] != control["planned_missions"][logical]:
        raise ValueError("pilot mission order changed")
    scene = read(checked_path(control["bundle"], entry["scene"]))
    run_root = root / "execution" / f"{logical:02d}_{entry['intent']}" / f"attempt_{attempt_index}"
    row = dict(logical_index=logical, attempt_index=attempt_index, run_root=str(run_root),
        reserved_utc=utc(), mission_id=entry["mission_id"], base_index=entry["base_index"],
        intent=entry["intent"], evidence_sha256={})
    control["active_attempt"] = copy.deepcopy(row)
    _save_atomic(path, control)
    try:
        ledger = run_mission_list(Path(control["bundle"]) / "mission_list.json", max_runs=1, resume=False,
            output_root=run_root, mission_ids=[entry["mission_id"]], binary=control["binary"],
            parameters=control["parameters"], quality_policy=control["quality_policy"],
            max_environment_retries=0, retryable_errors=())
        attempt = ledger["missions"][0]["attempts"][0]
        row.update(runner_status=attempt["status"], runner_error=attempt.get("error"),
                   run_directory=attempt.get("run_directory"))
        if not row["run_directory"]:
            raise ValueError("runner returned no directory; takeoff status unproven")
        directory = Path(row["run_directory"])
        metadata = read(directory / "metadata.json")
        param_evidence = read(directory / "firmware_parameters.json")
        reason = preflight_retry_reason(metadata, param_evidence, _event_rows(directory))
        row.update(retryable_pre_takeoff=reason is not None, retry_reason=reason,
                   run_id=metadata.get("run_id"), run_status=metadata.get("status"))
        if reason:
            row.update(qualified=False, accepted_for_pp=False, hard_failures=[], soft_flags=[])
            row["evidence_sha256"] = {str(p.resolve()): file_hash(p) for p in directory.rglob("*") if p.is_file()}
        else:
            analyze_run_v3(directory, control["quality_policy"], progress_mapping_version=PROGRESS_VERSION,
                           acceptance_policy=POLICY_VERSION, acceptance_stage="pilot", update_latest=True)
            latest = read(directory / "analysis_latest.json")
            analysis = checked_path(directory, latest["directory"])
            if file_hash(analysis / "manifest.json") != latest["manifest_sha256"]:
                raise ValueError("selected analysis manifest changed")
            metadata, artifacts = analysis_artifacts(directory, analysis, scene, control)
            row.update(analysis_directory=str(analysis), **assess_run(scene, metadata, artifacts, control))
            row["evidence_sha256"] = record_evidence(directory, analysis)
        row["evidence_sha256"][str((run_root / "attempt_ledger.json").resolve())] = file_hash(run_root / "attempt_ledger.json")
        integrity(control)
        row["finished_utc"] = utc()
    except BaseException as exc:
        row.update(qualified=False, accepted_for_pp=False, retryable_pre_takeoff=False,
                   hard_failures=[f"unresolved attempt: {type(exc).__name__}: {exc}"], finished_utc=utc())
        control.update(stopped_reason=row["hard_failures"][0], active_attempt=None)
        control["records"].append(row)
        _save_atomic(path, control)
        raise
    control["records"].append(row)
    control["active_attempt"] = None
    aggregate = aggregate_status(control["records"])
    control["aggregate"] = aggregate
    if row["hard_failures"]:
        control["stopped_reason"] = "; ".join(row["hard_failures"])
    elif aggregate["logical_completed"] - aggregate["qualified"] > 2:
        control["stopped_reason"] = "18/20 quality gate is no longer attainable"
    elif (sum(all(i in {r["logical_index"] for r in terminal_rows(control["records"])}
                   for i in (2 * b, 2 * b + 1)) for b in range(10)) - aggregate["pair_qualified"] > 1):
        control["stopped_reason"] = "9/10 two-intent quality gate is no longer attainable"
    elif aggregate["logical_completed"] == LOGICAL_RUNS:
        control["completed"] = True
    else:
        try:
            next_mission(control)
        except ValueError as exc:
            control["stopped_reason"] = str(exc)
    _save_atomic(path, control)
    return row, control


def pilot_acceptance_gates(aggregate, dataset_manifest, audit, descriptions, loaded):
    gates = dict(twenty_terminal_runs=aggregate["logical_completed"] == LOGICAL_RUNS,
        episode_quality_18_of_20=aggregate["qualified"] >= 18,
        paired_quality_9_of_10=aggregate["pair_qualified"] >= 9,
        dataset_export_twenty_episodes=len(dataset_manifest["episodes"]) == 20,
        dataset_audit_no_issues=not audit.get("issues"),
        descriptions_complete_and_consistent=descriptions["consistency_pass"],
        loader_reads_all_episodes=len(loaded) == 20 and all(
            r["corner_count"] == 4 and r["corner_dimensions"] == [2, 2, 2, 2] for r in loaded),
        protected_files_intact=True)
    for intent in INTENT_ORDER:
        rate = aggregate["by_intent"][intent]["success_fraction_given_quality"]
        gates[intent + "_success_given_quality"] = rate is not None and rate >= .90
    gates["pass"] = all(gates.values())
    return gates


def finalize(root=ROOT_OUTPUT):
    root = Path(root).resolve()
    path = root / "control.json"
    control = read(path)
    assert_controller_binding(control, root)
    if (control.get("stopped_reason") or control.get("completed") is not True or
            control.get("finalized") or control.get("active_attempt") is not None or
            (root / "acceptance.json").exists()):
        raise ValueError("pilot is not clean/complete, or finalization already exists")
    try:
        integrity(control)
        terminal = terminal_rows(control["records"])
        if len(terminal) != 20 or [r["logical_index"] for r in terminal] != list(range(20)):
            raise ValueError("pilot must contain twenty terminal mission attempts")
        audit_ledger = root / "audit_attempt_ledger.json"
        missions = []
        for mission_id in control["planned_missions"]:
            attempts = [dict(run_directory=r.get("run_directory"), run_status=r.get("run_status"),
                status=r.get("runner_status"), intent=r["intent"],
                episode_quality_eligible=r.get("episode_quality_eligible"))
                for r in control["records"] if r["mission_id"] == mission_id]
            missions.append(dict(mission_id=mission_id, attempts=attempts))
        save_json(audit_ledger, dict(schema_version=1, source=VERSION, missions=missions))
        dataset = root / "dataset"
        build_dataset([r["run_directory"] for r in terminal], dataset)
        audit = audit_dataset(dataset, generation_manifest=Path(control["bundle"]) / "generation_manifest.json",
                              attempt_ledger=audit_ledger)
        save_json(root / "dataset_audit.json", audit)
        language = root / "dataset_language_zh_v0"
        describe_dataset(dataset, language)
        descriptions = _description_gate(dataset, language)
        manifest = read(dataset / "dataset_manifest.json")
        loaded = []
        for entry in manifest["episodes"]:
            episode_path = checked_path(dataset, entry["directory"])
            episode = load_episode(episode_path, verify_hashes=True)
            corners = load_public_scene(episode_path)
            loaded.append(dict(run_id=entry["run_id"], frames=len(episode["t_s"]),
                agents=len(episode["agent_ids"]), corner_count=len(corners),
                corner_dimensions=[len(c) for c in corners]))
        aggregate = aggregate_status(control["records"])
        gates = pilot_acceptance_gates(aggregate, manifest, audit, descriptions, loaded)
        result = dict(version="v05_r12_pilot_acceptance_v1", gate=gates, aggregate=aggregate,
            description_check=descriptions, loaded=loaded,
            soft_flags_by_run=[dict(run_id=r["run_id"], intent=r["intent"], soft_flags=r.get("soft_flags", [])) for r in terminal],
            dataset_manifest_sha256=file_hash(dataset / "dataset_manifest.json"),
            audit_sha256=file_hash(root / "dataset_audit.json"),
            language_manifest_sha256=file_hash(language / "language_manifest.json"),
            audit_issues=audit.get("issues", []), source_control_sha256=file_hash(path), completed_utc=utc())
        save_json(root / "acceptance.json", result)
        summary = ["# v0.5 r1.2 试生产验收", "", f"结论：**{'PASS' if gates['pass'] else 'FAIL'}**。",
            f"质量合格 {aggregate['qualified']}/20；双意图均合格 {aggregate['pair_qualified']}/10；",
            f"SITL 尝试 {aggregate['attempts']}/22。软门禁只记录，不进入质量或试生产验收门槛。", "",
            "| 门禁 | 判定 |", "| --- | --- |"]
        summary += [f"| {name} | {'PASS' if passed else 'FAIL'} |" for name, passed in gates.items() if name != "pass"]
        (root / "pp_report.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
        control.update(finalized=True, final_gate_pass=gates["pass"])
        if not gates["pass"]:
            control["stopped_reason"] = "r1.2 pilot final acceptance failed"
        _save_atomic(path, control)
        return result
    except BaseException as exc:
        control["stopped_reason"] = f"pilot finalization stopped: {type(exc).__name__}: {exc}"
        _save_atomic(path, control)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "next", "finalize"))
    parser.add_argument("--root", type=Path, default=ROOT_OUTPUT)
    parser.add_argument("--validation-control", type=Path, default=VALIDATION_ROOT / "control.json")
    parser.add_argument("--sitl", type=Path, default=BINARY)
    parser.add_argument("--parameters", type=Path, default=PARAMETERS)
    parser.add_argument("--quality-policy", type=Path, default=QUALITY_POLICY)
    args = parser.parse_args(argv)
    if args.action == "finalize":
        result = finalize(args.root)
        print(json.dumps(dict(gate=result["gate"], aggregate=result["aggregate"]), ensure_ascii=False))
        return int(not result["gate"]["pass"])
    if args.action == "prepare":
        control = prepare(args.root, args.validation_control, args.sitl, args.parameters, args.quality_policy)
    else:
        _, control = run_next(args.root)
    print(json.dumps({k: control.get(k) for k in ("version", "completed", "stopped_reason", "aggregate")}, ensure_ascii=False))
    return int(bool(control.get("stopped_reason")))


if __name__ == "__main__":
    raise SystemExit(main())
