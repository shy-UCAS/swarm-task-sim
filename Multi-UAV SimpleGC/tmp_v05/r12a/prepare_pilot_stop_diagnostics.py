"""Freeze a read-only partial diagnostic appendix after the PP hard stop."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.build_v05_pause1_report import *
from scripts.run_v05c_validation import assert_protected

output = ROOT / "tmp_v05/r12a/pilot_stop_01"
output.mkdir(parents=True, exist_ok=True)
if (output / "partial_diagnostics").exists():
    raise ValueError("partial output exists; keep the existing evidence")
control_paths = (VAL / "control.json", PP / "control.json")
initial_control_hashes = {str(p.resolve()): file_hash(p) for p in control_paths}
val, pp = [read(p) for p in control_paths]
if not val["completed"] or val["stopped_reason"] or val["sitl_attempts_consumed"] != 6:
    raise ValueError("validation completion or budget differs")
if (pp["stopped_reason"] != "known_consistent_labels" or pp["active_attempt"] is not None
        or pp["completed"] or pp.get("finalized") or len(pp["records"]) != 8
        or pp["records"][-1]["run_id"] != "20261002T202309Z_ef48c8bb"):
    raise ValueError("pilot stop differs from the requested evidence scope")
assert_integrity(val)
integrity(pp)
protected_count = assert_protected()
vr = [val["vp1_reassessment"]] + [r for r in val["records"] if not r.get("retryable_pre_takeoff")]
pr = terminal_rows(pp["records"])
entries = [dict(case_id=r["case_id"], stage="validation", run_directory=r["run_directory"],
                analysis_directory=r["analysis_directory"]) for r in vr]
entries += [dict(case_id=f"PP{r['logical_index']+1:02d}", stage="pilot",
                 run_directory=r["run_directory"], analysis_directory=r["analysis_directory"]) for r in pr]
save(output / "partial_diagnostic_inputs.json", dict(runs=entries))
diagnostics = build_report(output / "partial_diagnostic_inputs.json", output / "partial_diagnostics")
source_groups = ac4_sources(diagnostics, {})
save(output / "partial_ac4_source_distributions.json", source_groups)
cases = []
for r in diagnostics["runs"]:
    labels = read(Path(r["analysis_directory"]) / "labels.json")
    cases.append(dict(case_id=r["case_id"], run_id=r["run_id"], stage=r["stage"], intent=r["intent"],
        episode_quality_eligible=r["episode_quality_eligible"],
        individual_hard_pass=r["validation_policy"]["individual_pass"],
        hard_failures=r["validation_policy"]["hard_failures"],
        mission_success_truth=labels["mission_success"],
        mission_success_observation=labels["mission_success_observation"],
        semantic_consistency=labels["semantic_consistency"],
        soft_flag_count=len(r["validation_policy"]["soft_flags"]),
        soft_flags=r["validation_policy"]["soft_flags"]))
fallbacks = [dict(case_id=r["case_id"], agent_id=x["agent_id"], channel=c,
    arrival_s=w["arrival_s"], source=w["arrival_source"], verified=w["arrival_verified"],
    reason=w.get("arrival_reason")) for r in diagnostics["runs"] for x in r["approach"]
    for c,w in x["channels"].items() if w["arrival_source"] != "trajectory_stop"]
missing = [dict(case_id=r["case_id"], agent_id=x["agent_id"], channel=c, field=k)
    for r in diagnostics["runs"] for x in r["approach"] for c,w in x["channels"].items()
    for k in ("start_s", "arrival_s", "sampled_horizontal_path_length_m") if w.get(k) is None]
pending = ["PP09-PP20: 12 logical runs have not been started",
    "20-run and 10-pair pilot final acceptance has not been performed",
    "pilot dataset export, audit, describe and loader finalization not performed",
    "five actual pilot description examples and fact-channel disagreement summary not available",
    "full 20-run execution distributions, 25-run combined diagnostics and production estimates pending",
    "Pause 1 consolidated acceptance report not generated; current state is a hard stop before Pause 1",
    "remaining 240-run batch not authorized or started"]
hashes = {str(p.resolve()): file_hash(p) for p in [*control_paths,
    output / "partial_diagnostic_inputs.json", output / "partial_diagnostics/report.json",
    output / "partial_diagnostics/report.md", output / "partial_ac4_source_distributions.json", Path(__file__)]}
for path, expected in initial_control_hashes.items():
    if file_hash(path) != expected:
        raise ValueError("controller changed during read-only report")
review = dict(version="v05_r12a_partial_pilot_stop_diagnostics_v1",
    scope="five validation cases plus eight completed pilot attempts including the hard-failed eighth; not Pause 1 acceptance",
    validation_budget_consumed=6, validation_budget_total=8,
    pilot_attempts=8, pilot_completed_logical_runs=8, pilot_planned_logical_runs=20,
    pilot_quality_eligible=8, pilot_pairs_quality_eligible=4,
    warning="quality eligibility counts do not override the eighth run's hard semantic-consistency failure",
    pilot_stopped_reason=pp["stopped_reason"], active_attempt=None,
    ninth_run_started=any(r["logical_index"] >= 8 for r in pp["records"]),
    partial_intent_task_success=pp["aggregate"]["by_intent"],
    integrity=dict(pass_gate=True, protected_file_count=protected_count,
        validation_frozen_hash_count=len(val["frozen_sha256"]),
        pilot_frozen_hash_count=len(pp["frozen_sha256"]),
        validation_attempt_evidence_hash_counts={r["case_id"]:len(r["evidence_sha256"]) for r in vr},
        pilot_attempt_evidence_hash_counts={f"PP{r['logical_index']+1:02d}":len(r["evidence_sha256"]) for r in pr},
        diagnostic_input_hash_count=len(diagnostics["source_sha256"]),
        control_hashes_unchanged=True,
        checks=["validation assert_integrity", "pilot integrity", "assert_protected",
                "each selected analysis manifest and artifact hashes", "controllers unchanged before/after reporting"]),
    cases=cases,
    approach_agents=sum(len(r["approach"]) for r in diagnostics["runs"]),
    approach_channel_rows=sum(len(x["channels"]) for r in diagnostics["runs"] for x in r["approach"]),
    all_initial_headings_zero=all(x["initial_heading_deg"]==0 for r in diagnostics["runs"] for x in r["approach"]),
    missing_approach_numeric=missing, approach_arrival_fallbacks=fallbacks,
    soft_flag_counts=diagnostics["aggregate"]["soft_flag_counts"],
    pending=pending, source_sha256=hashes)
save(output / "partial_integrity_and_pending.json", review)
lines = ["# 试生产停止 01：已完成运行的部分诊断附件", "",
    "本附件只含 5 项验证与已经完成的 8 次试生产，包含第 8 次的硬门禁失败证据；不是暂停 1 合并报告，也不是试生产验收通过。", "",
    "验证预算 6/8；试生产完成 8/20，尝试 8/22，PP09 尚未启动。数据质量资格为 8/8、已完成双意图场景为 4/4；这些计数不覆盖 PP08 的 `known_consistent_labels` 硬失败。", "",
    "| 用例 | 意图 | 真值 / 观测任务成功 | 语义一致性 | 硬门禁 | 质量资格 | 软标记数 |", "| --- | --- | --- | --- | --- | --- | ---: |"]
for r in cases:
    lines.append(f"| {r['case_id']} | {r['intent']} | {r['mission_success_truth']} / {r['mission_success_observation']} | {r['semantic_consistency']} | {'PASS' if r['individual_hard_pass'] else 'FAIL'} | {r['episode_quality_eligible']} | {r['soft_flag_count']} |")
lines += ["",f"进场共 {review['approach_agents']} 架次、{review['approach_channel_rows']} 条通道记录；起始航向全部为 0，航程/出发/到达数值缺失 {len(missing)} 条。到达使用最近距离兜底的 {len(fallbacks)} 条另列，不视作已验证停稳到达。", "",
    "逐机航程、名义时长、AUTO/运动出发、双通道到达与转角见 [进场表](partial_diagnostics/report.md)，完整来源、兜底及软指标分母见 [JSON](partial_diagnostics/report.json)。主值和事件交叉核对分布另见 [AC4 来源表](partial_ac4_source_distributions.json)。", "",
    "## 软门禁部分分布", "", "| 组别 / 阶段 / 通道 | 代码 / 状态 / 来源 | 标记数 |", "| --- | --- | ---: |"]
for r in review["soft_flag_counts"]:
    lines.append(f"| {r['stage']} / {r['intent']} / {r['phase']} / {r['channel']} | {r['code']} / {r['status']} / {r['source']} | {r['count']} |")
lines += ["", "按标记记录计数；同次运行可有多个标记，不等同于运行数。AV-1/AV-2 按意图与阶段的数值、未知分母保存在诊断 JSON；不填补未知，不将部分分布当作 20 次总体。", "",
    "## 进场到达兜底", "", "| 用例 / 飞机 / 通道 | 到达 s | 来源 | 已验证停稳 |", "| --- | ---: | --- | --- |"]
for r in fallbacks:
    lines.append(f"| {r['case_id']} / {r['agent_id']} / {r['channel']} | {r['arrival_s']} | {r['source']} | {r['verified']} |")
lines += ["", "## 完整性与尚缺证据", "",
    f"受保护文件 {protected_count} 个均通过，验证和试生产冻结输入及逐次证据哈希通过，两个控制台账在只读汇总前后未变。具体计数和 SHA256 见 [完整性清单](partial_integrity_and_pending.json)。", ""]
lines += ["- "+item for item in pending]
lines.append("")
(output / "partial_review.md").write_text("\n".join(lines), encoding="utf-8")
save(output / "partial_output_manifest.json",dict(version=review["version"],
    source_sha256=hashes, output_sha256={str(p.resolve()):file_hash(p) for p in [
    output / "partial_review.md", output / "partial_integrity_and_pending.json"]}))
print(json.dumps(dict(output=str(output),runs=len(cases),approach_agents=review["approach_agents"],
    fallback_count=len(fallbacks),protected_file_count=protected_count,
    soft_counts={r["case_id"]:r["soft_flag_count"] for r in cases}),ensure_ascii=False))
