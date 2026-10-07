"""Reanalyze seven frozen patrols under r1.2b into new external directories.

This command never starts SITL, changes latest pointers or resumes a controller.
Changed semantic outcomes are reported, not treated as a stop gate.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_v05c_validation import assert_protected
from swarm_sim.analysis_v3 import analyze_run_v3
from swarm_sim.protocol import validate_artifact_protocol

VALIDATION = ROOT / "verification/v05_r12_validation_20261002/control.json"
PILOT = ROOT / "verification/v05_r12_pp_20261002/control.json"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def cases():
    validation, pilot = read(VALIDATION), read(PILOT)
    if (validation.get("completed") is not True or validation.get("sitl_attempts_consumed") != 6
            or pilot.get("stopped_reason") != "known_consistent_labels"
            or pilot.get("active_attempt") is not None or len(pilot["records"]) != 8):
        raise ValueError("historical controllers no longer match the authorized r1.2b inputs")
    selected = [dict(case_id="VP1", stage="validation", **{
        key: validation["vp1_reassessment"][key]
        for key in ("run_id", "run_directory", "analysis_directory")})]
    selected += [dict(case_id=row["case_id"], stage="validation", **{
        key: row[key] for key in ("run_id", "run_directory", "analysis_directory")})
        for row in validation["records"] if row["case_id"] in ("VP2", "VP3")]
    selected += [dict(case_id=f"PP{row['logical_index'] + 1:02d}", stage="pilot", **{
        key: row[key] for key in ("run_id", "run_directory", "analysis_directory")})
        for row in pilot["records"] if row["logical_index"] in (1, 3, 5, 7)]
    if [item["case_id"] for item in selected] != ["VP1", "VP2", "VP3", "PP02", "PP04", "PP06", "PP08"]:
        raise ValueError("unexpected patrol input selection")
    return selected


def evidence_files(selected):
    roots = [ROOT / "tmp_v05/r12", ROOT / "tmp_v05/r12_progress", ROOT / "tmp_v05/r12a",
             ROOT / "verification/v05_r12_validation_20261002",
             ROOT / "verification/v05_r12_pp_20261002",
             ROOT / "verification/v05c_validation_20261002",
             ROOT / "tmp_v05/dr_v05c"]
    roots += [Path(item[key]) for item in selected for key in ("run_directory", "analysis_directory")]
    files = {path.resolve() for root in roots for path in root.rglob("*")
             if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}
    files.update((ROOT.parent / ".claude/progress").glob("progress_*.md"))
    files.update(ROOT / name for name in (
        "docs/v0.5_r1.2_offline_stop_01.md", "docs/v0.5_r1.2a_pilot_stop_01.md",
        "docs/v0.5c_validation_stop_01.md", "generation_profiles/dual_intent_v05c.json",
        "swarm_sim/ac4_timing.py"))
    return sorted(files)


def summary(analysis):
    analysis = Path(analysis)
    labels, quality, manifest = [read(analysis / name) for name in
                                  ("labels.json", "quality.json", "manifest.json")]
    validate_artifact_protocol(manifest, analysis)
    for name, expected in manifest["artifact_sha256"].items():
        if sha256(analysis / name) != expected:
            raise ValueError(f"analysis artifact hash mismatch: {analysis / name}")
    metrics = labels["mission_metrics"]
    return dict(analysis_directory=str(analysis), manifest_sha256=sha256(analysis / "manifest.json"),
        semantic_validation_version=manifest["semantic_validation_version"],
        route_progress_version=manifest.get("route_progress_version"),
        mission_success_truth=labels["mission_success"],
        mission_success_observation=labels["mission_success_observation"],
        semantic_consistency=labels["semantic_consistency"],
        episode_quality_eligible=quality["episode_quality_eligible"],
        channels={channel: {key: metrics[channel]["perimeter_revisit"].get(key) for key in (
            "version", "required_visits_per_segment", "min_segment_visits", "visits_pass",
            "max_revisit_gap_s", "allowed_gap_s", "max_gap_pass", "patrol_success",
            "per_agent_laps_observed", "evidence_complete", "group_segment_visit_counts")}
            for channel in ("truth", "observation")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "tmp_v05/r12b/patrol_reanalysis_01")
    parser.add_argument("--source-commit", required=True, help="Full baseline HEAD, read by git in the repository-root shell")
    args = parser.parse_args()
    if len(args.source_commit) != 40 or any(char not in "0123456789abcdef" for char in args.source_commit):
        raise ValueError("source commit must be a full lowercase Git SHA1")
    output = args.output.resolve()
    if output.exists():
        raise ValueError("output already exists; use a fresh directory, never overwrite evidence")
    selected = cases()
    protected_before = assert_protected()
    old_hashes = {str(path): sha256(path) for path in evidence_files(selected)}
    output.mkdir(parents=True, exist_ok=False)
    source_paths = list((ROOT / "swarm_sim").glob("*.py")) + [Path(__file__).resolve()]
    source_hashes = {str(path): sha256(path) for path in source_paths}
    write_new(output / "input_preservation.json", dict(
        version="v05_r12b_patrol_preservation_v1", protected_file_count=protected_before,
        source_code_sha256=source_hashes, old_evidence_sha256=old_hashes,
        source_commit=args.source_commit,
        selected_cases=selected))
    rows = []
    try:
        for case in selected:
            old = summary(case["analysis_directory"])
            original_analyses = [summary(path) for path in sorted(Path(case["run_directory"]).glob("analysis_*"))
                                 if path.is_dir() and (path / "manifest.json").is_file()]
            new_directory = output / case["case_id"]
            policy = read(Path(case["analysis_directory"]) / "quality.json")["quality_policy"]
            analyze_run_v3(case["run_directory"], policy,
                progress_mapping_version="ordered_route_progress_v2",
                patrol_validator_version="perimeter_revisit_v2",
                output_directory=new_directory, update_latest=False)
            new = summary(new_directory)
            old_labels = read(Path(case["analysis_directory"]) / "labels.json")
            new_labels = read(new_directory / "labels.json")
            preserved_metrics = {}
            for channel in ("truth", "observation"):
                old_detail = old_labels["mission_metrics"][channel]["perimeter_revisit"]
                new_detail = new_labels["mission_metrics"][channel]["perimeter_revisit"]
                preserved_metrics[channel] = {key: old_detail.get(key) == new_detail.get(key) for key in (
                    "segments", "group_segment_visit_counts", "per_agent_laps_observed",
                    "max_revisit_gap_s", "allowed_gap_s", "per_agent_progress")}
            byte_equal = {name: sha256(Path(case["analysis_directory"]) / name) == sha256(new_directory / name)
                          for name in ("truth.csv", "observations.csv", "phase_windows.json", "ac4_timing_v3.json")}
            row = dict(case_id=case["case_id"], run_id=case["run_id"], old=old, new=new,
                original_run_analyses=original_analyses, unchanged_diagnostics=preserved_metrics,
                unchanged_input_products=byte_equal,
                verdict_changed=any(old[key] != new[key] for key in (
                    "mission_success_truth", "mission_success_observation", "semantic_consistency")))
            rows.append(row)
            write_new(output / f"{case['case_id']}_comparison.json", row)
            print(json.dumps(dict(case_id=case["case_id"], old=[old["mission_success_truth"], old["mission_success_observation"]],
                new=[new["mission_success_truth"], new["mission_success_observation"]]), ensure_ascii=False), flush=True)
    finally:
        changed = [path for path, expected in old_hashes.items()
                   if not Path(path).is_file() or sha256(path) != expected]
        changed_code = [path for path, expected in source_hashes.items() if sha256(path) != expected]
        protected_after = assert_protected()
        preservation = dict(old_evidence_files=len(old_hashes), old_evidence_unchanged=not changed,
            changed_old_evidence=changed, analysis_source_unchanged=not changed_code,
            changed_analysis_source=changed_code, protected_file_count=protected_after,
            protected_files_unchanged=protected_before == protected_after,
            new_sitl_runs=0, original_controllers_and_latest_preserved=not changed)
        write_new(output / "preservation_result.json", preservation)
        if changed or changed_code:
            raise ValueError("source/evidence changed during offline analysis; inspect preservation_result.json")
    result = dict(version="v05_r12b_patrol_comparison_v1", generated_utc=datetime.now(timezone.utc).isoformat(),
        comparison_only=True, semantic_changes_are_not_stop_conditions=True,
        acceptance_policy_evaluation="not_applied; PP09+ rules are documented only in this turn",
        total_runs=len(rows), rows=rows, preservation=preservation,
        verdict_changed_count=sum(row["verdict_changed"] for row in rows))
    write_new(output / "comparison.json", result)
    report = ["# r1.2b 已完成巡逻离线判定对照", "",
        "本次仅对照语义结果，不据新旧判定变化停止，不占 SITL 预算。旧运行、分析、latest 指针和控制台账保留。",
        "新分析显式使用 `perimeter_revisit_v2` / `multi_intent_validation_v3`，有序映射保持 `ordered_route_progress_v2`。",
        "本轮不重评或执行 PP09 起的新停止策略。新分析不附加旧 r1.2 门禁作为新门禁判定。", "",
        "| 运行 | 原真值 / 观察 | 新真值 / 观察 | 原 / 新语义一致性 | 原 / 新质量资格 |",
        "| --- | --- | --- | --- | --- |"]
    for row in rows:
        old, new = row["old"], row["new"]
        report.append(f"| {row['case_id']} | {old['mission_success_truth']} / {old['mission_success_observation']} | "
                      f"{new['mission_success_truth']} / {new['mission_success_observation']} | "
                      f"{old['semantic_consistency']} / {new['semantic_consistency']} | "
                      f"{old['episode_quality_eligible']} / {new['episode_quality_eligible']} |")
    report += ["", f"结果变化 {result['verdict_changed_count']}/{len(rows)}。逐通道访问次数、间隔、圈数和原运行内各版分析见 [comparison.json](comparison.json)。",
        "此处“原”以最新已封存的有序映射 v2 分析作比较基准；VP1 原 r1 FAIL、PP08 原 v1/v2 分歧及停止判定仍分别保留。",
        "", f"旧证据 {len(old_hashes)} 个文件及受保护 {protected_after} 个文件全部保持，见 [保存性核对](preservation_result.json)。",
        "[输入与源码哈希](input_preservation.json)绑定本次离线输入与实现。新目录中的数据是重分析附件，未导出为新数据集。"]
    (output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    write_new(output / "output_manifest.json", {str(path.relative_to(output)): sha256(path)
               for path in output.rglob("*") if path.is_file()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
