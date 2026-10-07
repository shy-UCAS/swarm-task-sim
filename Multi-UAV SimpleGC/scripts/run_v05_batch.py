"""Bounded v0.5 batch continuation: one authorized SITL mission per ``next``.

Reuse DR bases 10--129, retain PP01--PP20, and export all 260 selected analyses.
Infrastructure failures stop for review; this controller never retries or clears
a stop automatically. Execution diagnostics never change quality eligibility.
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
from scripts.run_v05c_pp import (DR_GENERATED, DR_PROFILE, DR_REVIEW, INTENT_ORDER,
    _description_gate, _dr_inputs, _event_rows, assert_hashes, assert_protected, read,
    terminal_rows, utc)
from scripts.run_v05_r12b_pp import hash_tree, integrity as pilot_integrity
from scripts.run_v05_r12_validation import ARTIFACTS, preflight_retry_reason
from swarm_sim.analysis_v3 import analyze_run_v3
from swarm_sim.dataset import build_dataset
from swarm_sim.dataset_audit import audit_dataset
from swarm_sim.episode_loader import load_episode, load_public_scene
from swarm_sim.generation import canonical_hash, checked_path, file_hash, save_json, verify_generation
from swarm_sim.language_v0 import describe_dataset
from swarm_sim.protocol import manifest_protocol, semantic_protocol, validate_artifact_protocol
from swarm_sim.run_provenance import verify_preflight_files
from swarm_sim.validation_policy import finite
from swarm_sim.validation_policy_r12b import VERSION as POLICY_VERSION, assess_run, assess_recent_runs

VERSION = "v05_batch_controller_v1"
ROOT_OUTPUT = ROOT / "verification/v05_batch_20261002"
PILOT_CONTROL = ROOT / "verification/v05_r12b_pp_20261002/control.json"
RETURN_AUDIT = ROOT / "tmp_v05/batch_return_check_20261002/audit.json"
PROGRESS_VERSION = "ordered_route_progress_v2"
PATROL_VERSION = "perimeter_revisit_v2"
LOGICAL_RUNS, MAX_ATTEMPTS, MAX_EXTRA_RETRIES = 240, 264, 24
TOTAL_RUNS, TOTAL_BASES = 260, 130


def aggregate_status(records):
    rows = terminal_rows(records)
    by_base = {}
    for row in rows:
        by_base.setdefault(row["base_index"], {})[row["intent"]] = row
    paired = sum(set(pair) == set(INTENT_ORDER) and all(
        r.get("episode_quality_eligible") is True for r in pair.values()) for pair in by_base.values())
    by_intent = {}
    for intent in INTENT_ORDER:
        subset = [r for r in rows if r["intent"] == intent]
        eligible = [r for r in subset if r.get("episode_quality_eligible") is True]
        success = sum(r.get("mission_success") is True for r in eligible)
        by_intent[intent] = dict(attempted=len(subset), qualified=len(eligible),
            success_given_quality=success,
            success_fraction_given_quality=success / len(eligible) if eligible else None)
    return dict(logical_completed=len(rows), attempts=len(records),
        qualified=sum(r.get("episode_quality_eligible") is True for r in rows),
        pair_qualified=paired, by_intent=by_intent)


def combined_records(control):
    """Use a local combined index without rewriting either source ledger."""
    batch = [dict(r, logical_index=r["logical_index"] + 20) for r in control["records"]]
    return [*control["pilot_records"], *batch]


def integrity(control, *, full_history=False, include_runtime=True):
    assert_hashes(control["bundle_sha256"])
    assert_hashes(control["runtime_archive_sha256"])
    if include_runtime:
        assert_hashes(control["runtime_sha256"])
    # The pilot/source ledger bindings remain checked on every invocation. The
    # full raw history and accumulated batch outputs are checked at both ends.
    assert_hashes(control["source_bindings_sha256"])
    if full_history:
        assert_hashes(control["historical_sha256"])
        for row in control["records"]:
            assert_hashes(row.get("evidence_sha256", {}))
    assert_protected()


def assert_binding(control, root):
    if (Path(root).resolve() != ROOT_OUTPUT.resolve() or control.get("version") != VERSION
            or control.get("stage") != "batch" or control.get("acceptance_policy") != POLICY_VERSION
            or control.get("max_attempts") != MAX_ATTEMPTS
            or control.get("max_extra_retries") != MAX_EXTRA_RETRIES
            or control.get("hold_s") != 0 or type(control.get("hold_s")) is not int
            or control.get("progress_mapping_version") != PROGRESS_VERSION
            or control.get("patrol_validator_version") != PATROL_VERSION
            or Path(control.get("bundle", "")).resolve() != (ROOT_OUTPUT / "bundle").resolve()
            or Path(control.get("pilot_control", "")).resolve() != PILOT_CONTROL.resolve()
            or len(control.get("planned_missions", [])) != LOGICAL_RUNS
            or len(set(control.get("planned_missions", []))) != LOGICAL_RUNS):
        raise ValueError("invalid batch root, protocol, hold or budget binding")
    pilot = read(PILOT_CONTROL)
    if control["pilot_records"] != pilot["records"] or len(control["pilot_records"]) != 20:
        raise ValueError("pilot source records changed")


def next_mission(control):
    if (control.get("version") != VERSION or control.get("stopped_reason") or control.get("completed")
            or control.get("active_attempt") is not None):
        raise ValueError("batch is stopped, complete, invalid or has an unresolved attempt")
    if control.get("max_attempts") != MAX_ATTEMPTS or control.get("max_extra_retries") != MAX_EXTRA_RETRIES:
        raise ValueError("batch attempt budget changed")
    rows = control["records"]
    if len(rows) >= MAX_ATTEMPTS:
        raise ValueError("264-attempt batch budget exhausted")
    if [r.get("logical_index") for r in rows] != list(range(len(rows))):
        raise ValueError("batch records do not follow the frozen order")
    if any(r.get("attempt_index") != 0 or r.get("retryable_pre_takeoff") for r in rows):
        raise ValueError("infrastructure attempt requires an explicit recovery decision")
    for row in rows:
        if not row.get("hard_failures"):
            continue
        if not row.get("run_directory") or not row.get("analysis_directory"):
            raise ValueError("unresolved infrastructure attempt requires an explicit recovery decision")
        # Historical dispositions remain unchanged. After an authorized resume,
        # apply the current stop rule to existing evidence, without reanalysis.
        metadata = read(Path(row["run_directory"]) / "metadata.json")
        _, artifacts = selected_artifacts(row["run_directory"], row["analysis_directory"],
                                           metadata["scenario"], control)
        if assess_artifacts(metadata["scenario"], metadata, artifacts, control)["hard_failures"]:
            raise ValueError("previous batch attempt has a currently confirmed hard failure")
    if len(rows) >= LOGICAL_RUNS:
        raise ValueError("all 240 batch missions attempted")
    return len(rows), 0


def rolling_status(control):
    return assess_recent_runs([dict(run_id=r["run_id"], stage="batch", assessment=r["assessment"])
        for r in control["records"] if r.get("assessment")], stage="batch")


def disk_status(control, *, initial=False):
    remaining = max(0, LOGICAL_RUNS - len(terminal_rows(control["records"])))
    estimate = control["storage_estimate"]
    required = remaining * (estimate["max_run_bytes"] + estimate["max_analysis_bytes"])
    required += TOTAL_RUNS * (estimate["max_episode_bytes"] + estimate["language_bytes_per_episode"])
    multiplier = 2.0 if initial else 1.5
    free = shutil.disk_usage(ROOT_OUTPUT.parent).free
    return dict(free_bytes=free, required_remaining_bytes=required, remaining_runs=remaining,
        required_multiplier=multiplier, basis="largest_pilot_run_analysis_episode_and_language",
        pass_gate=free >= required * multiplier)


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
    if artifacts["quality"].get("validation_policy", {}).get("stage") != "batch":
        raise ValueError("selected analysis acceptance stage differs")
    return metadata, artifacts


def assess_artifacts(scene, metadata, artifacts, control):
    quality, labels = artifacts["quality"], artifacts["labels"]
    assessment = assess_run(scene, metadata, quality, labels, artifacts["execution_metrics"],
        artifacts["ac4_timing_v3"], artifacts["onboard_mission_param_check"], stage="batch")
    if assessment != quality["validation_policy"]:
        raise ValueError("stored policy assessment differs from independent recomputation")
    firmware = metadata.get("binary_firmware", {})
    agents = {v["id"] for v in scene["vehicles"]}
    cleanup = metadata.get("cleanup", {})
    separation = quality.get("truth_separation", {})
    minimum, required = separation.get("minimum_m"), scene.get("min_separation_m")
    separation_check = None
    if finite(minimum) and finite(required):
        if minimum < required:
            separation_check = False
        elif separation.get("status") == "clear_observed":
            separation_check = True
    onboard = artifacts["onboard_mission_param_check"]
    mismatch_count = onboard.get("counts", {}).get("mismatch_count")
    onboard_check = None
    if onboard.get("status") == "mismatch" or finite(mismatch_count) and mismatch_count > 0:
        onboard_check = False
    elif onboard.get("pass_gate") is True and onboard.get("status") == "pass":
        onboard_check = True
    # These are the latest user-authorized batch checks. Keep the stored r1.2b
    # assessment unchanged. Unknown evidence remains null, not a false pass;
    # single-run quality ineligibility contributes only to the rolling rule.
    # 2026-10-03 authorized stop-rule correction (B098): a run whose metadata
    # status is not "completed" no longer stops the batch by itself. Its stored
    # quality verdict keeps it ineligible and the rolling rule counts it, while
    # metadata["status"] is still recorded in run_status. Only missing or failed
    # analysis evidence stays an immediate hard failure. The check key keeps its
    # historical name for ledger compatibility; its value now means "the run
    # ended in a state whose analysis evidence exists".
    checks = dict(assessment["hard_checks"],
        onboard_mission_parameters=onboard_check,
        truth_separation=separation_check,
        frozen_firmware_and_parameters=firmware.get("sha256") == control["firmware"]["sha256"]
            and firmware.get("version_string") == control["firmware"]["version_string"]
            and metadata.get("parameters_sha256") == control["parameters_sha256"],
        infrastructure_cleanup_complete=set(cleanup) == agents and all(type(cleanup[a]) is int for a in agents),
        infrastructure_execution_completed=not quality.get("analysis_error"))
    return dict(qualified=quality.get("episode_quality_eligible") is True,
        episode_quality_eligible=quality.get("episode_quality_eligible"),
        mission_success=labels.get("mission_success"), mission_success_observation=labels.get("mission_success_observation"),
        semantic_consistency=labels.get("semantic_consistency"), run_status=metadata.get("status"),
        batch_hard_checks=checks, hard_failures=[key for key, value in checks.items() if value is False],
        soft_flags=assessment["soft_flags"], semantic_flags=assessment.get("semantic_flags", []),
        new_anomalies=assessment.get("new_anomalies", []), assessment=assessment)


def analyze_selected(directory, output, scene, control):
    analyze_run_v3(directory, control["quality_policy"], progress_mapping_version=PROGRESS_VERSION,
        patrol_validator_version=PATROL_VERSION, acceptance_policy=POLICY_VERSION,
        acceptance_stage="batch", output_directory=output, update_latest=False)
    metadata, artifacts = selected_artifacts(directory, output, scene, control)
    return assess_artifacts(scene, metadata, artifacts, control)


def _size(directory):
    return sum(p.stat().st_size for p in Path(directory).rglob("*") if p.is_file())


def _write_bundle(root, listing, manifest, by_base):
    bundle = root / "bundle"
    (bundle / "missions").mkdir(parents=True)
    (bundle / "scenes").mkdir()
    shutil.copyfile(DR_GENERATED / "generation_profile.json", bundle / "generation_profile.json")
    plan = []
    for base in range(10, TOTAL_BASES):
        if set(by_base.get(base, {})) != set(INTENT_ORDER):
            raise ValueError("accepted batch base lacks its two-intent pair")
        for intent in INTENT_ORDER:
            original = by_base[base][intent]
            if original["candidate_id"] != manifest["bases"][base]["selected_candidate"]:
                raise ValueError("batch entry differs from accepted DR candidate")
            entry = copy.deepcopy(original)
            entry.update(batch_index=len(plan), task=f"missions/{entry['mission_id']}.json",
                         scene=f"scenes/{entry['mission_id']}.json")
            for key in ("task", "scene"):
                shutil.copyfile(checked_path(DR_GENERATED, original[key]), bundle / entry[key])
                entry[key + "_sha256"] = file_hash(bundle / entry[key])
            plan.append(entry)
    subset = dict(listing, missions=plan)
    save_json(bundle / "mission_list.json", subset)
    candidates = [c for c in manifest["candidates"] if c["base_index"] >= 10]
    save_json(bundle / "generation_manifest.json", dict(schema_version=2,
        generator_version=VERSION, source_generation_manifest_sha256=file_hash(DR_GENERATED / "generation_manifest.json"),
        profile_sha256=manifest["profile_sha256"], bases=manifest["bases"][10:], candidates=candidates,
        counts=dict(base_scenes=120, accepted_bases=120, candidates=len(candidates),
            accepted_candidates=sum(c["status"] == "accepted" for c in candidates), planned_missions=LOGICAL_RUNS),
        artifact_sha256={p.relative_to(bundle).as_posix(): file_hash(p) for p in sorted(bundle.rglob("*.json"))}))
    verify_generation(bundle / "mission_list.json")
    return plan


def prepare(root=ROOT_OUTPUT, *, source_commit):
    root = Path(root).resolve()
    if root != ROOT_OUTPUT.resolve() or root.exists() or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("new dedicated batch root and full source commit required")
    pilot = read(PILOT_CONTROL)
    if (not pilot.get("completed") or not pilot.get("finalized") or not pilot.get("final_gate_pass")
            or pilot.get("stopped_reason") or pilot.get("active_attempt") is not None
            or len(pilot["records"]) != 20 or pilot.get("hold_s") != 0):
        raise ValueError("pilot is not the accepted completed 20-run handoff")
    pilot_integrity(pilot, include_runtime=False)
    return_audit = read(RETURN_AUDIT)
    if (return_audit.get("result") != "PASS"
            or return_audit.get("dataset_manifest_sha256") != file_hash(PILOT_CONTROL.parent / "dataset/dataset_manifest.json")):
        raise ValueError("optional-return description audit did not pass for the accepted pilot dataset")
    assert_hashes({str(checked_path(ROOT, name)): digest
                   for name, digest in return_audit["source_sha256"].items()})
    assert_hashes({str(checked_path(ROOT, name)): digest
                   for name, digest in return_audit["original_sha256"].items()})
    source_profile, source_generated, source_review = [p.resolve() for p in (DR_PROFILE, DR_GENERATED, DR_REVIEW)]
    listing, manifest, _, _, by_base = _dr_inputs(source_profile, source_generated, source_review,
                                               source_profile, source_generated, 0)
    provenance = verify_preflight_files(pilot["binary"], pilot["parameters"])
    if provenance["actual"]["firmware"] != pilot["firmware"]:
        raise ValueError("firmware differs from accepted pilot")
    historical = dict(pilot["historical_sha256"])
    for folder in (PILOT_CONTROL.parent, ROOT / "tmp_v05/r12b_resume", ROOT / "tmp_v05/r12b_pause1"):
        historical.update(hash_tree(folder))
    for path in (ROOT / "docs/v0.5_r1.2b_pause1_report.md",
                 ROOT.parent / ".claude/progress/progress_20261002_220113.md"):
        historical[str(path.resolve())] = file_hash(path)
    root.mkdir(parents=True)
    (root / "analyses").mkdir()
    plan = _write_bundle(root, listing, manifest, by_base)
    runtime_files = list((ROOT / "swarm_sim").glob("*.py")) + list((ROOT / "scripts").glob("*.py"))
    runtime_files += [ROOT / "docs/v0.5_当前有效规则.md", ROOT / "docs/v0.5_r1.2_addendum.md",
        ROOT / "docs/data_contract_v0.md", ROOT.parent / "CLAUDE.md", Path(pilot["binary"]),
        Path(pilot["parameters"]), ROOT / "quality_policies/default_v022.json"]
    for source in runtime_files:
        if source.suffix not in (".py", ".md", ".json"):
            continue
        target = root / "runtime_snapshot" / source.resolve().relative_to(ROOT.parent.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    bindings = [PILOT_CONTROL, PILOT_CONTROL.parent / "acceptance.json", RETURN_AUDIT, DR_PROFILE,
        DR_REVIEW, DR_GENERATED / "generation_manifest.json", ROOT / "tmp_v05/m0/protected_baseline.json"]
    pilot_dataset = PILOT_CONTROL.parent / "dataset"
    episodes = read(pilot_dataset / "dataset_manifest.json")["episodes"]
    estimate = dict(max_run_bytes=max(_size(r["run_directory"]) for r in pilot["records"]),
        max_analysis_bytes=max(_size(r["analysis_directory"]) for r in pilot["records"]),
        max_episode_bytes=max(_size(checked_path(pilot_dataset, e["directory"])) for e in episodes),
        language_bytes_per_episode=_size(PILOT_CONTROL.parent / "dataset_language_zh_v0") / len(episodes))
    control = dict(version=VERSION, stage="batch", acceptance_policy=POLICY_VERSION,
        progress_mapping_version=PROGRESS_VERSION, patrol_validator_version=PATROL_VERSION,
        prepared_utc=utc(), source_commit=source_commit, bundle=str(root / "bundle"),
        formal_profile=str(DR_PROFILE.resolve()), formal_generation=str(DR_GENERATED.resolve()),
        pilot_control=str(PILOT_CONTROL.resolve()), pilot_records=copy.deepcopy(pilot["records"]),
        hold_s=0, hold_encoding="integer_seconds_v1", binary=pilot["binary"], parameters=pilot["parameters"],
        firmware=pilot["firmware"], parameters_sha256=pilot["parameters_sha256"], quality_policy=pilot["quality_policy"],
        quality_policy_sha256=pilot["quality_policy_sha256"], historical_sha256=historical,
        source_bindings_sha256={str(p.resolve()): file_hash(p) for p in bindings},
        runtime_sha256={str(p.resolve()): file_hash(p) for p in runtime_files},
        runtime_archive_sha256=hash_tree(root / "runtime_snapshot"), bundle_sha256=hash_tree(root / "bundle"),
        planned_missions=[e["mission_id"] for e in plan], records=[], active_attempt=None,
        stopped_reason=None, completed=False, finalized=False, max_attempts=MAX_ATTEMPTS,
        max_extra_retries=MAX_EXTRA_RETRIES, storage_estimate=estimate)
    _save_atomic(root / "control.json", control)
    try:
        integrity(control, full_history=True)
        assert_binding(control, root)
        control["aggregate"] = aggregate_status([])
        control["rolling"] = rolling_status(control)
        control["initial_disk_check"] = disk_status(control, initial=True)
        if not control["initial_disk_check"]["pass_gate"]:
            stop(control, root, "insufficient_disk_space")
        _save_atomic(root / "control.json", control)
    except BaseException as exc:
        stop(control, root, f"batch preparation integrity/infrastructure failure: {type(exc).__name__}: {exc}")
        _save_atomic(root / "control.json", control)
        raise
    return control


def stop(control, root, reason):
    control["stopped_reason"] = reason
    cause = reason.removeprefix("infrastructure_or_integrity_failure: ").removeprefix(
        "batch preparation integrity/infrastructure failure: ")
    if "episode_quality" in reason:
        impact = "将本次未通过质量门禁的 episode 计为合格，会使数据集质量合格率及有效模型输入数量错误。"
        # Read the already-computed quality evidence once; do not repair or
        # recalculate metrics as part of stopping. Detailed review stays offline.
        last = control["records"][-1] if control["records"] else {}
        quality_path = Path(last.get("analysis_directory", "")) / "quality.json"
        if quality_path.is_file():
            quality = read(quality_path)
            failures = {key: quality.get(key) for key in ("run_completed", "data_quality_pass",
                "truth_available_pass", "timing_diagnostic_pass", "execution_constraints_pass")
                if quality.get(key) is not True}
            for key, value, passed in (
                ("clock_quality.overall", quality.get("clock_quality", {}).get("overall"),
                 quality.get("clock_quality", {}).get("overall") in ("strict", "acceptable")),
                ("separation_status", quality.get("separation_status"), quality.get("separation_status") == "clear_observed"),
                ("truth_separation.status", quality.get("truth_separation", {}).get("status"),
                 quality.get("truth_separation", {}).get("status") == "clear_observed"),
                ("onboard_mission_param_check_pass", quality.get("onboard_mission_param_check_pass"),
                 not quality.get("onboard_mission_param_check_required") or quality.get("onboard_mission_param_check_pass") is True)):
                if not passed:
                    failures[key] = value
            impact += " 未通过字段：" + json.dumps(failures, ensure_ascii=False) + "；证据：" + str(quality_path)
    elif "truth_separation" in reason:
        impact = "真值最小间距已确认低于场景最小安全间距，不能将该轨迹判为满足机间安全约束的样本。"
    elif any(word in cause for word in ("parameter", "firmware", "integrity", "frozen", "hash", "protected")):
        impact = "运行配置或证据来源未通过冻结核对，任务执行与标签的对应关系及可复现性不能成立。"
    elif "rolling" in reason:
        impact = "异常运行数已达到批准的停止阈值，继续生成不能被表述为通过该批量验收规则。"
    elif "final_acceptance" in reason:
        impact = "最终质量、配对、成功率或导出审计验收未通过，不能宣布数据集达到规定研究使用条件。"
    else:
        impact = "本次未完成规定的运行或导出证据；若计为完整样本会使 episode 数量及覆盖率错误，不据此断言已有轨迹损坏。"
    control["research_impact"] = impact
    control["stopped_utc"] = utc()
    path = Path(root) / "stop_report.md"
    if not path.exists():
        path.write_text("\n".join(["# v0.5 批量生成停止报告", "", "结论：停止，未自动重试。", "",
            "异常：" + reason, "此问题会导致的研究结果错误：" + impact, "",
            f"已记账尝试 {len(control['records'])}/{MAX_ATTEMPTS}；计划任务 {LOGICAL_RUNS} 次。",
            "证据位置：同目录 control.json、execution/、analyses/；原运行和既有判定均保留。", ""]), encoding="utf-8")


def complete_record(control, row, root=ROOT_OUTPUT):
    control["records"].append(row)
    control["active_attempt"] = None
    control["aggregate"] = aggregate_status(control["records"])
    control["rolling"] = rolling_status(control)
    if row.get("hard_failures"):
        stop(control, root, "; ".join(row["hard_failures"]))
    elif control["rolling"]["stop"]:
        stop(control, root, "rolling_anomalous_runs_at_least_5")
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
        listing, _ = verify_generation(Path(control["bundle"]) / "mission_list.json")
        entry = listing["missions"][logical]
        if (entry["mission_id"] != control["planned_missions"][logical]
                or entry["base_index"] != logical // 2 + 10 or entry["intent"] != INTENT_ORDER[logical % 2]):
            raise ValueError("batch mission order changed")
        scene = read(checked_path(control["bundle"], entry["scene"]))
    except BaseException as exc:
        stop(control, root, f"pre-run hard gate: {type(exc).__name__}: {exc}")
        _save_atomic(path, control)
        raise
    run_root = root / "execution" / f"{logical:03d}_{entry['intent']}" / "attempt_0"
    row = dict(logical_index=logical, attempt_index=attempt_index, run_root=str(run_root),
        reserved_utc=utc(), mission_id=entry["mission_id"], base_index=entry["base_index"], intent=entry["intent"],
        evidence_sha256={}, retryable_pre_takeoff=False)
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
        analysis = root / "analyses" / f"B{logical+1:03d}_attempt_0"
        row.update(analyze_selected(directory, analysis, scene, control), analysis_directory=str(analysis))
        if reason:
            row["hard_failures"].append("infrastructure_pre_takeoff_failure")
        row["evidence_sha256"] = dict(hash_tree(run_root), **hash_tree(analysis))
        assert_hashes(row["evidence_sha256"])
        integrity(control)
        row["finished_utc"] = utc()
    except BaseException as exc:
        row.update(qualified=False,
            hard_failures=[f"infrastructure_or_integrity_failure: {type(exc).__name__}: {exc}"], finished_utc=utc())
        row["evidence_sha256"].update(hash_tree(run_root))
        complete_record(control, row, root)
        _save_atomic(path, control)
        raise
    complete_record(control, row, root)
    _save_atomic(path, control)
    return row, control


def acceptance_gates(aggregate, manifest, audit, descriptions, loaded):
    gates = dict(terminal_runs_260=aggregate["logical_completed"] == TOTAL_RUNS,
        episode_quality_at_least_90_percent=aggregate["qualified"] / TOTAL_RUNS >= .90,
        paired_quality_at_least_85_percent=aggregate["pair_qualified"] / TOTAL_BASES >= .85,
        dataset_export_260_episodes=len(manifest["episodes"]) == TOTAL_RUNS,
        dataset_audit_no_unexplained_issues=not audit.get("issues"),
        descriptions_complete_and_consistent=descriptions["consistency_pass"],
        loader_reads_all_episodes=len(loaded) == TOTAL_RUNS and all(
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
    assert_binding(control, root)
    if control.get("stopped_reason") or not control.get("completed") or control.get("finalized") or control.get("active_attempt"):
        raise ValueError("batch is not complete/clean or was already finalized")
    try:
        integrity(control, full_history=True)
        records = combined_records(control)
        rows = terminal_rows(records)
        if len(rows) != TOTAL_RUNS or [r["logical_index"] for r in rows] != list(range(TOTAL_RUNS)):
            raise ValueError("260 ordered terminal runs including pilot required")
        selections = {str(Path(r["run_directory"]).resolve()): dict(directory=r["analysis_directory"],
            manifest_sha256=file_hash(Path(r["analysis_directory"]) / "manifest.json")) for r in rows}
        save_json(root / "analysis_selections.json", selections)
        audit_ledger = root / "audit_attempt_ledger.json"
        save_json(audit_ledger, dict(schema_version=1, source=VERSION, missions=[dict(mission_id=r["mission_id"],
            attempts=[dict(run_directory=a.get("run_directory"), run_status=a.get("run_status"),
                status=a.get("runner_status"), intent=a["intent"], episode_quality_eligible=a.get("episode_quality_eligible"))
                for a in records if a["mission_id"] == r["mission_id"]]) for r in rows]))
        dataset, language = root / "dataset", root / "dataset_language_zh_v0"
        manifest = build_dataset([r["run_directory"] for r in rows], dataset, analysis_selections=selections)
        audit = audit_dataset(dataset, generation_manifest=DR_GENERATED / "generation_manifest.json", attempt_ledger=audit_ledger)
        save_json(root / "dataset_audit.json", audit)
        describe_dataset(dataset, language)
        descriptions = _description_gate(dataset, language)
        loaded = []
        for entry in manifest["episodes"]:
            episode_path = checked_path(dataset, entry["directory"])
            episode, corners = load_episode(episode_path, verify_hashes=True), load_public_scene(episode_path)
            loaded.append(dict(run_id=entry["run_id"], frames=len(episode["t_s"]), agents=len(episode["agent_ids"]),
                corner_count=len(corners), corner_dimensions=[len(c) for c in corners]))
        aggregate = aggregate_status(records)
        gates = acceptance_gates(aggregate, manifest, audit, descriptions, loaded)
        result = dict(version=VERSION, gate=gates, aggregate=aggregate,
            description_check=descriptions, loaded=loaded, rolling=control["rolling"],
            dataset_manifest_sha256=file_hash(dataset / "dataset_manifest.json"),
            audit_sha256=file_hash(root / "dataset_audit.json"),
            language_manifest_sha256=file_hash(language / "language_manifest.json"), audit_issues=audit.get("issues", []),
            source_control_sha256=file_hash(path), completed_utc=utc())
        integrity(control, full_history=True)
        save_json(root / "acceptance.json", result)
        control.update(finalized=True, final_gate_pass=gates["pass"])
        if not gates["pass"]:
            stop(control, root, "r1_section_13_final_acceptance_failed")
        _save_atomic(path, control)
        return result
    except BaseException as exc:
        stop(control, root, f"batch finalization infrastructure failure: {type(exc).__name__}: {exc}")
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
