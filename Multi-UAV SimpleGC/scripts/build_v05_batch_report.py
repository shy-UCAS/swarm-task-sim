"""Read existing batch evidence and write a new final, partial or stop report.

No simulator, reanalysis, export, audit or ledger mutation is performed. Timing
statistics use one primary AC4 value per run and declared patrol phase/channel.
"""

import argparse
import json
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_v05_pause1_report import verify_manifest
from swarm_sim.generation import checked_path, file_hash

INTENTS = ("reconnaissance", "patrol")
CHANNELS = ("truth", "observation")
BATCH = ROOT / "verification/v05_batch_20261002"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def bind(path, bindings):
    path = Path(path).resolve()
    actual = file_hash(path)
    if str(path) in bindings and bindings[str(path)] != actual:
        raise ValueError("report source changed: " + str(path))
    bindings[str(path)] = actual
    return path


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def fraction(numerator, denominator):
    return dict(numerator=numerator, denominator=denominator,
                fraction=numerator / denominator if denominator else None)


def primary_distribution(records):
    """Unknown comparisons are not successful, zero-valued or denominator rows."""
    known = [r for r in records if r.get("complete") is True
             and finite(r.get("D_s")) and finite(r.get("tau_s"))]
    values = [r["D_s"] for r in known]
    return dict(expected=len(records), known=len(known), unknown=len(records) - len(known),
                median_s=statistics.median(values) if values else None,
                max_s=max(values) if values else None,
                thresholds_s=sorted({r["tau_s"] for r in known}),
                exceeded=fraction(sum(r["D_s"] > r["tau_s"] for r in known), len(known)),
                denominator="complete primary comparisons with finite D_s and tau_s; unknown excluded and counted separately")


def patrol_timing(rows):
    records = []
    for row in rows:
        if row["intent"] != "patrol":
            continue
        phases = [(name, value) for name, value in row.get("semantic_plan", {}).get("execution_phases", {}).items()
                  if value.get("semantic_phase") == "patrol"]
        # A stopped run without analysis remains visible as unknown, never zero.
        if not phases:
            phases = [("unavailable", {})]
        for phase, _ in phases:
            for channel in CHANNELS:
                primary = row.get("ac4", {}).get("channels", {}).get(channel, {}).get("per_phase", {}).get(phase, {}).get("primary", {})
                records.append(dict(run_id=row.get("run_id"), case_id=row.get("case_id"),
                    stage=row["stage"], phase=phase, semantic_phase="patrol", channel=channel,
                    source="primary", **{key: primary.get(key) for key in ("D_s", "tau_s", "complete", "within_tau")}))
    groups = []
    for scope in ("batch", "pilot_and_batch"):
        members = [r for r in records if scope == "pilot_and_batch" or r["stage"] == "batch"]
        for channel in CHANNELS:
            groups.append(dict(scope=scope, channel=channel, **primary_distribution([r for r in members if r["channel"] == channel])))
    return dict(groups=groups, records=records,
        basis="semantic_plan.execution_phases[phase].semantic_phase == patrol; ac4_timing_v3.channels[channel].per_phase[phase].primary; one group phase per run, no per-agent or crosscheck duplication; descriptive only")


def selected_rows(pilot, batch, bindings):
    output = []
    for stage, sources in (("pilot", pilot), ("batch", batch)):
        for source in sources:
            row = {key: source.get(key) for key in ("logical_index", "base_index", "run_id", "mission_id", "intent",
                "run_directory", "analysis_directory", "mission_success", "mission_success_observation",
                "semantic_consistency", "episode_quality_eligible", "hard_failures", "soft_flags", "semantic_flags", "new_anomalies")}
            row.update(stage=stage, case_id=source.get("case_id") or source.get("mission_id"))
            if not row["analysis_directory"]:
                row["analysis_unavailable"] = True
                output.append(row)
                continue
            analysis = Path(row["analysis_directory"]).resolve()
            expected = source.get("evidence_sha256", {}).get(str(analysis / "manifest.json"))
            if not expected or file_hash(analysis / "manifest.json") != expected:
                raise ValueError("selected analysis manifest differs from attempt evidence")
            manifest = verify_manifest(analysis, analysis / "manifest.json", bindings)
            if manifest.get("run_id") != row["run_id"]:
                raise ValueError("selected analysis belongs to another run")
            labels = read(analysis / "labels.json")
            quality = read(analysis / "quality.json")
            for key in ("mission_success", "mission_success_observation", "semantic_consistency"):
                if key in source and source[key] != labels.get(key):
                    raise ValueError("ledger/selected labels differ: " + key)
                row[key] = labels.get(key)
            if source.get("episode_quality_eligible") != quality.get("episode_quality_eligible"):
                raise ValueError("ledger/selected quality differs")
            policy = quality.get("validation_policy", {})
            for key in ("soft_flags", "semantic_flags", "new_anomalies"):
                row[key] = policy.get(key, [])
            row["strict_benchmark_eligible"] = quality.get("strict_benchmark_eligible")
            row["quality_evidence"] = {key: quality[key] for key in (
                "analysis_error", "episode_quality_eligible", "eligibility_reasons", "reasons", "observation_window",
                "run_completed", "data_quality_pass", "truth_available_pass", "timing_diagnostic_pass", "execution_constraints_pass",
                "onboard_mission_param_check_required", "onboard_mission_param_check_pass", "separation_status",
                "observation_valid_fraction", "truth_valid_fraction", "truth_separation", "clock_quality") if key in quality}
            row["semantic_plan"] = read(analysis / "semantic_plan.json")
            row["ac4"] = read(analysis / "ac4_timing_v3.json")
            row["analysis_manifest_sha256"] = file_hash(analysis / "manifest.json")
            output.append(row)
    return output


def outcomes(rows):
    out = {}
    for intent in INTENTS:
        members = [r for r in rows if r["intent"] == intent]
        qualified = [r for r in members if r["episode_quality_eligible"] is True]
        channels = {}
        for channel, key in (("truth", "mission_success"), ("observation", "mission_success_observation")):
            channels[channel] = dict(success=sum(r[key] is True for r in members),
                failure=sum(r[key] is False for r in members), unknown=sum(type(r[key]) is not bool for r in members), denominator=len(members))
        out[intent] = dict(total=len(members), quality=fraction(len(qualified), len(members)),
            success_given_quality=fraction(sum(r["mission_success"] is True for r in qualified), len(qualified)),
            disagreement=fraction(sum(r["semantic_consistency"] == "disagree" for r in members), len(members)), **channels)
    return out


def soft_rates(rows):
    result = []
    for intent in INTENTS:
        members = [r for r in rows if r["intent"] == intent]
        for code in ("AV-1", "AV-2", "AC4", "AV-8"):
            flags = [(r["case_id"], f) for r in members for f in (r.get("soft_flags") or []) if f.get("code") == code]
            result.append(dict(intent=intent, code=code, **fraction(len({run for run, _ in flags}), len(members)),
                statuses={status: len({run for run, flag in flags if flag.get("status") == status}) for status in ("exceeded", "unknown")},
                flag_records=len(flags), applicable=code != "AV-8" or intent == "patrol"))
    return result


def final_evidence(root, acceptance, rows, bindings):
    dataset, language = root / "dataset", root / "dataset_language_zh_v0"
    paths = {"dataset_manifest_sha256": dataset / "dataset_manifest.json", "audit_sha256": root / "dataset_audit.json",
             "language_manifest_sha256": language / "language_manifest.json"}
    for key, path in paths.items():
        if file_hash(bind(path, bindings)) != acceptance[key]:
            raise ValueError("final acceptance binding differs: " + key)
    manifest, audit = read(paths["dataset_manifest_sha256"]), read(paths["audit_sha256"])
    selected = {r["run_id"]: r for r in rows}
    if len(selected) != 260 or len(manifest["episodes"]) != 260 or {e["run_id"] for e in manifest["episodes"]} != set(selected):
        raise ValueError("final dataset does not contain the selected twenty pilot and 240 batch runs")
    for entry in manifest["episodes"]:
        row = selected[entry["run_id"]]
        if (entry.get("analysis_selection_mode") != "explicit_manifest_binding"
                or Path(entry.get("source_analysis_path", "")).resolve() != Path(row["analysis_directory"]).resolve()
                or entry.get("analysis_manifest_sha256") != row["analysis_manifest_sha256"]
                or file_hash(bind(checked_path(dataset, entry["directory"]) / "manifest.json", bindings)) != row["analysis_manifest_sha256"]):
            raise ValueError("final export lost its selected analysis binding")
    lang = verify_manifest(language, paths["language_manifest_sha256"], bindings)
    if lang["dataset_manifest_sha256"] != acceptance["dataset_manifest_sha256"]:
        raise ValueError("description layer bound to different dataset")
    descriptions = read(language / "descriptions.json")["descriptions"]
    facts = {p.stem: read(p) for p in (language / "facts").glob("*.json")}
    splits, families = Counter(), defaultdict(set)
    for entry in manifest["episodes"]:
        split = entry.get("split") or "unassigned"
        splits[split] += 1
        if entry.get("family_id"):
            families[split].add(entry["family_id"])
    examples = []
    for intent in INTENTS:
        for partition in ("train", "test"):
            sample = next((d for d in descriptions if d["template_partition"] == partition
                           and facts[d["episode_id"]]["labels"]["assigned_intent"] == intent), None)
            if sample:
                examples.append(sample)
    sample = next((d for d in descriptions if d not in examples), None)
    if sample:
        examples.append(sample)
    return dict(dataset_manifest=manifest, audit=audit, language_manifest=lang,
        splits={key: dict(episodes=value, families=len(families[key])) for key, value in splits.items()},
        family_count=len(set().union(*families.values())) if families else 0,
        description_by_intent={intent: dict(descriptions=sum(facts[d["episode_id"]]["labels"]["assigned_intent"] == intent for d in descriptions),
            episodes=len({d["episode_id"] for d in descriptions if facts[d["episode_id"]]["labels"]["assigned_intent"] == intent})) for intent in INTENTS},
        template_counts=dict(Counter(s["template_id"] for d in descriptions for s in d["sentences"])),
        fact_disagreements=sum(len(f["channel_check"]["disagreements"]) for f in facts.values()),
        fact_fields_checked=sum(len(f["channel_check"]["fields_checked"]) for f in facts.values()),
        examples=examples)


def number(value):
    return f"{value:.3f}" if finite(value) else "null"


def rate(item):
    value = item["fraction"]
    return f"{item['numerator']}/{item['denominator']}" + (f"（{value:.1%}）" if value is not None else "（未知）")


def link(path, document):
    return os.path.relpath(Path(path).resolve(), document.parent).replace("\\", "/")


def markdown(report, output, document):
    status, budget = report["status"], report["budget"]
    conclusion = {"final": "批量与最终数据集验收通过，已到暂停 2。", "stopped": "批量已停止，尚未完成最终数据集验收。", "partial": "批量尚未完成；本报告只汇总当前证据。"}[status]
    lines = ["# v0.5 双意图数据集报告", "", "**结论：" + conclusion + "**", "",
        f"批量完成 {budget['batch_terminal']}/240 次，尝试 {budget['batch_attempts']}/264 次；试生产已完成 20/20 次。数据集仅用于算法链路开发，不能用于报告意图识别准确率。", "",
        "## 异常与研究结果影响", ""]
    if report["stopped_reason"]:
        lines += [f"停止原因：`{report['stopped_reason']}`。", "", "对研究结果的具体影响：" + report["research_impact"], ""]
    else:
        lines += ["未触发停止。执行指标仅作诊断，未知保持未知。", ""]
    anomalies = report["anomalies"]
    lines += [f"记录异常 {len(anomalies)}/{len(report['rows'])} 次；原始标记、质量证据和全部来源见[报告 JSON]({link(output/'report.json', document)})。", "",
        "## 实现与测试", "",
        f"批量控制与断点台账：[run_v05_batch.py]({link(ROOT/'scripts/run_v05_batch.py', document)})；只读汇总：[build_v05_batch_report.py]({link(__file__, document)})；描述生成与一致性：[language_v0.py]({link(ROOT/'swarm_sim/language_v0.py', document)})。", ""]
    tests = report["tests"]
    if tests["count"] is not None:
        lines += [f"本轮完整测试已执行 {tests['count']}/{tests['count']} 项，全部通过：{tests['passed']}；[日志]({link(tests['path'], document)})。", ""]
    else:
        lines += [f"本轮完整测试日志尚未包含可确认的通过结果；[预定日志位置]({link(tests['path'], document)})。", ""]
    if report["optional_return_report"]:
        lines += [f"试生产非必需返航描述核对、修复及重生成证据直接引用[只读核对报告]({link(report['optional_return_report'], document)})；没有重飞。", ""]
    lines += [
        "## 验收与数据集概况", "", "| 意图 | 质量合格 / 已执行 | 合格内真值成功 | 真值成功 / 失败 / 未知 | 标签不一致 |", "| --- | --- | --- | --- | --- |"]
    for intent, item in report["outcomes"].items():
        truth = item["truth"]
        lines.append(f"| {intent} | {rate(item['quality'])} | {rate(item['success_given_quality'])} | " + " / ".join(f"{truth[k]}/{truth['denominator']}" for k in ("success", "failure", "unknown")) + f" | {rate(item['disagreement'])} |")
    lines += ["", "最终验收要求：全部质量合格至少 90%；双意图均合格场景至少 85%；质量合格内各意图任务成功至少 90%；可描述 episode 覆盖 100% 且一致性全部通过；审计 issues 为空或逐项解释。", ""]
    lines += [f"当前全量质量合格 {rate(report['quality'])}；双意图均质量合格场景 {rate(report['paired_quality'])}。", ""]
    final = report.get("final_evidence")
    if final:
        manifest, language = final["dataset_manifest"], final["language_manifest"]
        acceptance = report["acceptance"]
        lines += [f"导出 {len(manifest['episodes'])}/260 个 episode，family {final['family_count']}/130；加载 {len(acceptance.get('loaded', []))}/{len(manifest['episodes'])}。",
            f"描述覆盖 {language['eligible_agree_episodes']}/{language['eligible_agree_episodes']} 个可描述 episode；描述 {language['descriptions']} 条；事实通道分歧 {final['fact_disagreements']}/{final['fact_fields_checked']} 项。",
            f"审计 issues：{json.dumps(final['audit'].get('issues', []), ensure_ascii=False)}。完整逐项验收见[acceptance.json]({link(Path(report['root'])/'acceptance.json', document)})。", "",
            "| 划分 | episode / 全部 | family / 全部 |", "| --- | --- | --- |"]
        for split, value in final["splits"].items():
            lines.append(f"| {split} | {value['episodes']}/{len(manifest['episodes'])} | {value['families']}/{final['family_count']} |")
    else:
        lines += ["尚无通过的最终导出/审计/描述/加载验收；不将当前完成部分表述为完整数据集。"]
    lines += ["", "## 巡逻阶段时序进度差", "",
        r"仅统计巡逻群阶段的 primary 值；truth 与 observation 分列，不按单机/机对重复计数，也不混入 event crosscheck。完整且 \(D\)、\(\tau\) 均有限才计入已知分母；超限定义为 \(D>\tau\)。中位数、最大值只取已知值，未知单列。本表仅供以后改进规划安全估算，不是本轮门禁。", "",
        "| 范围 | 通道 | D 中位数 s | D 最大值 s | 超限 / 已知 | 未知 / 全部阶段 | 已执行巡逻 / 计划 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for group in report["patrol_timing"]["groups"]:
        scope = group["scope"]
        patrol_count = sum(r["intent"] == "patrol" and (scope == "pilot_and_batch" or r["stage"] == "batch") for r in report["rows"])
        lines.append(f"| {scope} | {group['channel']} | {number(group['median_s'])} | {number(group['max_s'])} | {rate(group['exceeded'])} | {group['unknown']}/{group['expected']} | {patrol_count}/{120 if scope == 'batch' else 130} |")
    lines += ["", "## 软标记与执行分布", "", "软标记按运行去重；同一运行可出现多项，不能相加作为异常运行数。", "",
        "| 意图 | 标记 | 发生运行 / 该意图运行 | exceeded / unknown |", "| --- | --- | --- | --- |"]
    for item in report["soft_rates"]:
        if item["applicable"]:
            lines.append(f"| {item['intent']} | {item['code']} | {rate(item)} | {item['statuses']['exceeded']}/{item['denominator']}；{item['statuses']['unknown']}/{item['denominator']} |")
    if final:
        lines += ["", "两种意图的执行指标仅作描述对照，中位数 / 最大值按审计现有统计口径；完整分布与分母见审计。", "", "| 意图 | 指标 | 中位数 / 最大值 | 已知 / 全部 |", "| --- | --- | --- | --- |"]
        for group in final["audit"].get("groups", []):
            for key, value in group.get("metrics", {}).items():
                if key in ("episode_duration_s", "execution_stop_count", "execution_synchronized_time_fraction", "execution_stationary_time_fraction", "executed_path_length_m"):
                    lines.append(f"| {group['intent']} | {key} | {number(value.get('median'))} / {number(value.get('max'))} | {value.get('count', 0)}/{value.get('expected_values', value.get('count', 0) + value.get('missing_values', 0))} |")
        lines += ["", "## 描述层与样例", ""]
        for intent, item in final["description_by_intent"].items():
            lines.append(f"- {intent}：有描述 {item['episodes']}/{report['outcomes'][intent]['total']} 个 episode，共 {item['descriptions']}/{final['language_manifest']['descriptions']} 条描述。")
        lines += ["", "模板使用次数和逐事实通道分歧写入报告 JSON。非必需返航任务不输出返航条件达标句，是否回到起点仅据轨迹事实。", ""]
        for index, item in enumerate(final["examples"], 1):
            lines += [f"{index}. `{item['episode_id']}`；episode split={item['episode_split']}；模板组={item['template_partition']}。", "", "> " + item["text"].replace("\n", "\n> "), ""]
    lines += ["", "## 证据位置与已知限制", "",
        f"控制台账：[control.json]({link(Path(report['root'])/'control.json', document)})；完整报告及来源哈希：[report.json]({link(output/'report.json', document)})。",
        f"历史离线门禁、DR、验证和试生产结果引用[暂停 1 报告]({link(ROOT/'docs/v0.5_r1.2b_pause1_report.md', document)})及其附件；终点驻留为 0，VP4/HD 已取消。当前数据契约：[data_contract_v0.md]({link(ROOT/'docs/data_contract_v0.md', document)})。", "",
        "已知限制：每种意图只有一种执行策略；内部扫描与边界巡逻的空间差异可能成为强线索；两类时长未均衡；场景较小；无分布外划分或近重复检测；arrival_s 兜底与约 1 s 阶段边界精度保留；时序容差上限依赖经验；覆盖率采用理想观察模型；运动模式检测为启发式；描述来自规则模板。严格时钟资格比例见报告 JSON。不能用本数据集报告意图识别准确率。", ""]
    return "\n".join(lines)


def build(root, output, document=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    bindings = {}
    control = read(bind(root / "control.json", bindings))
    # The controller owns attempt selection and does not include pilot attempts
    # in the batch window or budget. Failed pre-takeoff retries remain in JSON.
    from scripts.run_v05_batch import terminal_rows
    pilot = control["pilot_records"]
    batch = terminal_rows(control["records"])
    acceptance_path = root / "acceptance.json"
    acceptance = read(bind(acceptance_path, bindings)) if acceptance_path.is_file() else None
    final = bool(control.get("completed") and control.get("finalized") and not control.get("stopped_reason")
                 and control.get("active_attempt") is None and acceptance and acceptance.get("gate", {}).get("pass") is True)
    status = "final" if final else "stopped" if control.get("stopped_reason") else "partial"
    document = Path(document).resolve() if document else (ROOT / "docs/v0.5_dual_intent_dataset_report.md" if final else output / "report.md")
    if output.exists() or document.exists():
        raise ValueError("new report directory and document required; old evidence is never overwritten")
    rows = selected_rows(pilot, batch, bindings)
    evidence = final_evidence(root, acceptance, rows, bindings) if final else None
    pairs = defaultdict(dict)
    for row in rows:
        pairs[row["base_index"]][row["intent"]] = row["episode_quality_eligible"]
    anomalies = [{k: r.get(k) for k in ("case_id", "stage", "hard_failures", "semantic_flags", "new_anomalies", "quality_evidence")}
                 for r in rows if r.get("hard_failures") or r.get("semantic_flags") or r.get("new_anomalies") or r["episode_quality_eligible"] is False]
    impact = control.get("research_impact") or control.get("stop_research_impact")
    if not impact:
        impact = "现有停止台账未给出已定位的具体研究结果影响；本报告仅保留停止原因和质量原始字段，不据此断言轨迹或标签已经错误。"
    test_path = ROOT / "tmp_v05/batch_repair_20261003/full_tests.log"
    tests = dict(path=str(test_path), count=None, passed=None)
    if test_path.is_file():
        test_log = bind(test_path, bindings).read_text(encoding="utf-8-sig")
        matches = re.findall(r"Ran (\d+) tests? in", test_log)
        tests.update(count=int(matches[-1]) if matches else None,
                     passed=bool(re.search(r"^OK\s*$", test_log, re.MULTILINE)) and not bool(re.search(r"^FAILED", test_log, re.MULTILINE)))
    optional_return = ROOT / "tmp_v05/batch_return_check_20261002/report.md"
    for path in (ROOT / "scripts/run_v05_batch.py", ROOT / "swarm_sim/language_v0.py", ROOT / "docs/data_contract_v0.md"):
        if path.is_file():
            bind(path, bindings)
    if optional_return.is_file():
        bind(optional_return, bindings)
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(), root=str(root), status=status,
        stopped_reason=control.get("stopped_reason"), research_impact=impact, active_attempt=control.get("active_attempt"),
        budget=dict(batch_terminal=len(batch), batch_attempts=len(control["records"]), pilot_runs=len(pilot)),
        rolling=control.get("rolling"), acceptance=acceptance, final_evidence=evidence, anomalies=anomalies,
        quality=fraction(sum(r["episode_quality_eligible"] is True for r in rows), len(rows)),
        paired_quality=fraction(sum(all(values.get(intent) is True for intent in INTENTS) for values in pairs.values()), len(pairs)),
        tests=tests, optional_return_report=str(optional_return) if optional_return.is_file() else None,
        outcomes=outcomes(rows), soft_rates=soft_rates(rows), patrol_timing=patrol_timing(rows),
        strict_clock=fraction(sum(r.get("quality_evidence", {}).get("clock_quality", {}).get("overall") == "strict" for r in rows), len(rows)),
        rows=[{k: v for k, v in r.items() if k not in ("ac4", "semantic_plan")} for r in rows], source_sha256=bindings)
    bind(__file__, bindings)
    body = markdown(report, output, document)
    for path, expected in bindings.items():
        if file_hash(path) != expected:
            raise ValueError("source changed during report build: " + path)
    output.mkdir(parents=True, exist_ok=False)
    document.parent.mkdir(parents=True, exist_ok=True)
    with (output / "report.json").open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    with document.open("x", encoding="utf-8") as handle:
        handle.write(body)
    with (output / "output_manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(dict(source_count=len(bindings), artifact_sha256={str(path): file_hash(path) for path in (output / "report.json", document)}), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return dict(status=status, document=str(document), output=str(output), source_count=len(bindings))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=BATCH)
    parser.add_argument("--output", type=Path, default=ROOT / "tmp_v05/batch_report_20261002")
    parser.add_argument("--document", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.root, args.output, args.document), ensure_ascii=False))


if __name__ == "__main__":
    main()
