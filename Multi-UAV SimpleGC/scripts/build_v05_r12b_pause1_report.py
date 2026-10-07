"""Build the seven-item r1.2b Pause 1 report from finalized pilot evidence.

Read-only: no SITL, reanalysis, export, audit recomputation or ledger mutation.
Both output paths must be new. Historical diagnostic reports are only cited.
"""

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_v05_pause1_report import bytes_in, language_evidence, verify_manifest
from scripts.run_v05_r12b_pp import assert_binding, integrity, terminal_rows
from swarm_sim.dataset_audit import _distribution
from swarm_sim.generation import checked_path, file_hash
from swarm_sim.protocol import validate_artifact_protocol

VERSION = "v05_pause1_report_r12b_v1"
PP = ROOT / "verification/v05_r12b_pp_20261002"
INTENTS = ("reconnaissance", "patrol")
SOFT_CODES = ("AV-1", "AV-2", "AC4", "AV-8")
REFERENCES = ["docs/v05_m0_baseline.md", "docs/v0.5c_dr_review.md",
              "docs/v0.5_r1.2a_pilot_stop_01.md", "docs/v0.5_r1.2_addendum.md",
              "docs/v0.5_当前有效规则.md", "tmp_v05/r12b/patrol_reanalysis_02/report.md"] + [
              f"docs/v0.5_wp_{key}_offline_report.md" for key in "hrtmpl"]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save_new(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def bind(path, bindings):
    path = Path(path).resolve()
    digest = file_hash(path)
    if str(path) in bindings and bindings[str(path)] != digest:
        raise ValueError("source changed while reporting: " + str(path))
    bindings[str(path)] = digest
    return path


def summary(values):
    values = list(values)
    result = _distribution(values)
    return dict(result, expected_values=len(values), missing_values=len(values)-result["count"])


def fraction(numerator, denominator):
    return dict(numerator=numerator, denominator=denominator,
                fraction=numerator/denominator if denominator else None)


def outcome_counts(values):
    values = list(values)
    return dict(success=sum(v is True for v in values), failure=sum(v is False for v in values),
                unknown=sum(type(v) is not bool for v in values), denominator=len(values))


def pilot_rows(control, bindings):
    rows = terminal_rows(control["records"])
    if len(rows) != 20 or [r["logical_index"] for r in rows] != list(range(20)):
        raise ValueError("twenty ordered terminal pilot runs required")
    if len({r["run_id"] for r in rows}) != 20 or Counter(r["intent"] for r in rows) != Counter(dict.fromkeys(INTENTS, 10)):
        raise ValueError("pilot must have twenty unique runs and ten of each intent")
    output = []
    for row in rows:
        run, analysis = Path(row["run_directory"]).resolve(), Path(row["analysis_directory"]).resolve()
        manifest = verify_manifest(analysis, analysis/"manifest.json", bindings)
        if (manifest.get("run_id") != row["run_id"] or Path(manifest.get("run_directory", "")).resolve() != run
                or manifest.get("semantic_validation_version") != "multi_intent_validation_v3"
                or manifest.get("acceptance_policy_version") != control["acceptance_policy"]):
            raise ValueError("explicit analysis has wrong run, protocol or policy")
        validate_artifact_protocol(manifest, analysis)
        for relative, expected in manifest.get("source_sha256", {}).items():
            if file_hash(bind(checked_path(run, relative), bindings)) != expected:
                raise ValueError("analysis source binding changed")
        labels, quality = read(analysis/"labels.json"), read(analysis/"quality.json")
        policy = quality.get("validation_policy", {})
        if policy.get("version") != control["acceptance_policy"] or policy.get("stage") != "pilot":
            raise ValueError("current pilot policy attachment required")
        for key in ("mission_success", "mission_success_observation", "semantic_consistency"):
            if row.get(key) != labels.get(key):
                raise ValueError("ledger/analysis label differs: " + key)
        if (row.get("episode_quality_eligible") != quality.get("episode_quality_eligible")
                or row.get("soft_flags") != policy.get("soft_flags")
                or row.get("semantic_flags") != policy.get("semantic_flags")):
            raise ValueError("ledger/analysis quality or diagnostic flags differ")
        output.append(dict(logical_index=row["logical_index"], run_id=row["run_id"], intent=row["intent"],
            run_directory=str(run), analysis_directory=str(analysis), reserved_utc=row["reserved_utc"],
            finished_utc=row["finished_utc"], episode_quality_eligible=quality["episode_quality_eligible"],
            mission_success=labels.get("mission_success"), mission_success_observation=labels.get("mission_success_observation"),
            semantic_consistency=labels.get("semantic_consistency"), soft_flags=policy["soft_flags"],
            semantic_flags=policy.get("semantic_flags", []), new_anomalies=policy.get("new_anomalies", []),
            aggregate_anomaly=policy.get("aggregate_anomaly"), aggregate_anomaly_reasons=policy.get("aggregate_anomaly_reasons", [])))
    return output


def intent_evidence(rows):
    results, soft, semantic = {}, [], []
    for intent in INTENTS:
        members = [r for r in rows if r["intent"] == intent]
        count = len(members)
        results[intent] = dict(truth=outcome_counts(r["mission_success"] for r in members),
            observation=outcome_counts(r["mission_success_observation"] for r in members),
            disagreement=fraction(sum(r["semantic_consistency"] == "disagree" for r in members), count),
            consistency_unknown=fraction(sum(r["semantic_consistency"] not in ("agree", "disagree") for r in members), count),
            quality_ineligible=fraction(sum(r["episode_quality_eligible"] is False for r in members), count))
        for code in SOFT_CODES:
            matched = [(r["run_id"], f) for r in members for f in r["soft_flags"] if f.get("code") == code]
            statuses = sorted({f["status"] for _, f in matched} | {"exceeded", "unknown"})
            soft.append(dict(intent=intent, code=code, **fraction(len({run for run, _ in matched}), count),
                flag_records=len(matched), status_run_counts={status: len({run for run, flag in matched if flag["status"] == status}) for status in statuses},
                status_record_counts=dict(Counter(f["status"] for _, f in matched)),
                run_ids=sorted({run for run, _ in matched}),
                applicability="patrol only" if code == "AV-8" else "all runs; unassessable evidence remains flagged"))
        for category in ("semantic_flags", "new_anomalies"):
            codes = sorted({f["code"] for r in members for f in r[category]})
            for code in codes:
                matches = [(r["run_id"], f) for r in members for f in r[category] if f["code"] == code]
                semantic.append(dict(intent=intent, category=category, code=code,
                    **fraction(len({run for run, _ in matches}), count), flag_records=len(matches),
                    run_ids=sorted({run for run, _ in matches})))
    return results, soft, semantic


def resource_estimate(rows, dataset, language):
    raw, external, elapsed = [], [], []
    for row in rows:
        run, analysis = Path(row["run_directory"]), Path(row["analysis_directory"])
        raw.append(bytes_in(run))
        external.append(0 if analysis.is_relative_to(run) else bytes_in(analysis))
        seconds = (datetime.fromisoformat(row["finished_utc"])-datetime.fromisoformat(row["reserved_utc"])).total_seconds()
        if seconds < 0:
            raise ValueError("negative recorded attempt duration")
        elapsed.append(seconds)
    copies = dict(dataset=bytes_in(dataset), language=bytes_in(language))
    storage = [a+b for a, b in zip(raw, external)]
    mean_storage = (sum(storage)+sum(copies.values()))/len(rows)
    mean_elapsed = sum(elapsed)/len(rows)
    free = shutil.disk_usage(ROOT).free
    return dict(denominator_runs=len(rows), remaining_runs=240, run_directory_bytes=raw,
        external_selected_analysis_bytes=external, attempt_wall_s=elapsed, copy_bytes=copies,
        total_pilot_bytes=sum(storage)+sum(copies.values()), free_bytes=free,
        estimate_remaining_bytes=mean_storage*240, estimate_remaining_hours=mean_elapsed*240/3600,
        conservative_remaining_bytes=(max(storage)+sum(copies.values())/len(rows))*240,
        conservative_remaining_hours=max(elapsed)*240/3600,
        two_times_estimate_available=free >= 2*mean_storage*240,
        basis="20 completed pilot runs; reserved_utc to finished_utc; original run directories plus external selected analyses and export/language copies; excludes future retries, interruptions and additional archives")


def number(value):
    return "null" if value is None else f"{value:.3f}"


def show_distribution(value):
    expected = value.get("expected_values", value["count"]+value.get("missing_values", 0))
    return " / ".join(number(value.get(key)) for key in ("median", "p95", "max")) + f"（已知 {value['count']}/{expected}；未知 {value.get('missing_values', 0)}/{expected}）"


def relative_link(path, document):
    return os.path.relpath(Path(path).resolve(), document.parent).replace("\\", "/")


def markdown(report, output, document):
    rel = relative_link(output/"report.json", document)
    acc, agg = report["acceptance"], report["acceptance"]["aggregate"]
    lines = ["# v0.5 暂停 1 合并报告（r1.2b）", "",
        "**结论：试生产通过 r1 第 11.3 节验收，已到暂停 1，等待用户确认后才能开始剩余 240 次批量生成。**",
        f"试生产完成 {agg['logical_completed']}/20 次，尝试 {agg['attempts']}/22 次；验证仍为 6/8 次。PP01–PP08 原运行、原分析和 PP08 原停止判定保留。",
        f"异常与逐运行证据见下表及[完整报告 JSON]({rel})；滚动异常仅从 PP09 起计，不追溯计入 PP01–PP08。", "",
        "## 1. 试生产验收表", "", "| 验收项 | 结果 / 分母 | 要求 | 判定 |", "| --- | --- | --- | --- |",
        f"| episode 质量 | {agg['qualified']}/20 | 至少 18/20 | PASS |",
        f"| 双意图质量均合格场景 | {agg['pair_qualified']}/10 | 至少 9/10 | PASS |"]
    for intent in INTENTS:
        item = agg["by_intent"][intent]
        lines.append(f"| {intent} 质量合格内真值任务成功 | {item['success_given_quality']}/{item['qualified']} | 至少 90% | PASS |")
    desc = acc["description_check"]
    lines += [f"| 导出 / 加载 | {report['dataset_episode_count']}/20；{len(acc['loaded'])}/20 | 全部通过 | PASS |",
        f"| 审计 | {report['dataset_episode_count']}/20 episode；issues={len(report['audit_issues'])} | issues 为空 | PASS |",
        f"| 可描述 episode 覆盖 | {report['language']['described_episode_count']}/{desc['expected_eligible_agree']} | 100% | PASS |",
        f"| 描述一致性与绑定 | {desc['descriptions']}/{desc['descriptions']} 条 | 全部通过 | PASS |", "",
        "全部门禁字段、显式分析路径及哈希见报告 JSON 的 acceptance 和 source_sha256；未用任务成功代替质量资格。", "",
        "## 2. 两种意图的任务结果和标签分歧", "",
        "| 意图 | 真值成功 / 失败 / 未知 | 观察成功 / 失败 / 未知 | 标签不一致 | 一致性未知 | 质量不合格 |",
        "| --- | --- | --- | --- | --- | --- |"]
    for intent, item in report["outcomes"].items():
        cells = [" / ".join(f"{item[channel][name]}/{item[channel]['denominator']}" for name in ("success", "failure", "unknown")) for channel in ("truth", "observation")]
        cells += [f"{item[name]['numerator']}/{item[name]['denominator']}" for name in ("disagreement", "consistency_unknown", "quality_ineligible")]
        lines.append(f"| {intent} | " + " | ".join(cells) + " |")
    rolling = report["rolling"]
    lines += ["", f"当前生效窗口异常 {rolling['anomaly_count']}/{rolling['window_count']}，停止阈值为 5 次；同一运行触发任务失败、标签不一致或质量不合格多项时去重。", "",
        "语义标记和新异常单独列出，不混入软标记发生率：", "",
        "| 意图 / 类别 | 代码 | 涉及运行 / 该意图运行 | 原始标记条数 |", "| --- | --- | --- | --- |"]
    for item in report["semantic_flags"]:
        lines.append(f"| {item['intent']} / {item['category']} | {item['code']} | {item['numerator']}/{item['denominator']} | {item['flag_records']} |")
    if not report["semantic_flags"]:
        lines.append("| 两种意图 | 无 | 0/20 | 0 |")
    lines += ["", "## 3. 软标记按意图的发生率", "",
        "按运行去重；同一运行可触发不同代码或不同状态，因此各行及状态数不能相加当作异常运行数。AV-8 仅适用于巡逻，侦察行展示为不适用。", "",
        "| 意图 | 代码 | 标记运行 / 分母 | 发生率 | exceeded / unknown 运行数 | 标记条数 |",
        "| --- | --- | --- | --- | --- | --- |"]
    for item in report["soft_rates"]:
        rates = "不适用" if item["code"] == "AV-8" and item["intent"] == "reconnaissance" else f"{item['fraction']:.1%}"
        statuses = item["status_run_counts"]
        lines.append(f"| {item['intent']} | {item['code']} | {item['numerator']}/{item['denominator']} | {rates} | {statuses.get('exceeded', 0)}/{item['denominator']}；{statuses.get('unknown', 0)}/{item['denominator']} | {item['flag_records']} |")
    lines += ["", "## 4. 有描述的 episode 数量", "", "| 意图 | 有描述 / 全部 | 有描述 / 可描述 | 跳过 / 全部 | 描述条数 |", "| --- | --- | --- | --- | --- |"]
    for intent, item in report["language"]["by_intent"].items():
        lines.append(f"| {intent} | {item['described']}/{item['total']} | {item['described']}/{item['eligible_agree']} | {item['skipped']}/{item['total']} | {item['descriptions']} |")
    lines += ["", "## 5. 两种意图的执行指标分布", "",
        "只做描述对照，不作分类准确率或因果结论。数值依次为中位数 / P95 / 最大值，未知保持为空。时长与比例按 episode、停靠数和路径长度按飞机、过点速度按中间航点统计；停靠阈值为 0.3 m/s。", "",
        "| 指标 | reconnaissance | patrol |", "| --- | --- | --- |"]
    for label, key in (("时长 s", "episode_duration_s"), ("每机停靠数", "execution_stop_count"),
                       ("同步停靠比例", "execution_synchronized_time_fraction"), ("静止时间占比", "execution_stationary_time_fraction"),
                       ("实测路径长度 m", "executed_path_length_m"), ("中间航点最小过点速度 m/s", "minimum_passing_speed_m_s")):
        lines.append(f"| {label} | " + " | ".join(show_distribution(report["execution_distributions"][intent][key]) for intent in INTENTS) + " |")
    lines += ["", "## 6. 五条描述样例", ""]
    facts = {r["run_id"]: r for r in report["language"]["records"]}
    for index, item in enumerate(report["language"]["sample_descriptions"], 1):
        lines += [f"{index}. `{item['episode_id']}`；{facts[item['episode_id']]['intent']}；episode split={item['episode_split']}；模板组={item['template_partition']}。", "", "> " + item["text"].replace("\n", "\n> "), ""]
    r = report["resources"]
    lines += ["## 7. 批量生成的耗时与磁盘估算", "",
        f"以 {r['denominator_runs']}/20 次实跑为基数，运行目录、新外部分析、导出副本与描述合计 {r['total_pilot_bytes']/2**30:.3f} GiB。外推剩余 240 次约 {r['estimate_remaining_bytes']/2**30:.2f} GiB、{r['estimate_remaining_hours']:.2f} h；按最大目录和最慢运行外推约 {r['conservative_remaining_bytes']/2**30:.2f} GiB、{r['conservative_remaining_hours']:.2f} h。",
        f"当前可用 {r['free_bytes']/2**30:.2f} GiB，满足估算需求两倍：{r['two_times_estimate_available']}。耗时取台账 reserved→finished；不包含未来故障重试、中断或额外存档，正式批量前仍须核对磁盘。", "",
        "其余既有项目直接引用，不重复计算：[M0](v05_m0_baseline.md)、[H](v0.5_wp_h_offline_report.md)、[R](v0.5_wp_r_offline_report.md)、[P](v0.5_wp_p_offline_report.md)、[T](v0.5_wp_t_offline_report.md)、[M](v0.5_wp_m_offline_report.md)、[L](v0.5_wp_l_offline_report.md)、[DR](v0.5c_dr_review.md)、[已存验证与进场诊断](v0.5_r1.2a_pilot_stop_01.md)。", ""]
    return "\n".join(lines)


def build(root, output, document):
    root, output, document = (Path(path).resolve() for path in (root, output, document))
    if output.exists() or document.exists():
        raise ValueError("new output directory and new report document required")
    bindings = {}
    control = read(bind(root/"control.json", bindings))
    acceptance = read(bind(root/"acceptance.json", bindings))
    if (not control.get("completed") or not control.get("finalized") or control.get("stopped_reason")
            or control.get("active_attempt") is not None or acceptance.get("gate", {}).get("pass") is not True):
        raise ValueError("pilot must be finalized, complete and passing")
    assert_binding(control, root)
    integrity(control, include_runtime=False)
    for relative in REFERENCES + ["scripts/build_v05_pause1_report.py", "scripts/report_v05_r12.py", "scripts/run_v05_r12b_pp.py"]:
        bind(ROOT/relative, bindings)
    bind(__file__, bindings)
    rows = pilot_rows(control, bindings)
    dataset, language = root/"dataset", root/"dataset_language_zh_v0"
    dataset_manifest = read(bind(dataset/"dataset_manifest.json", bindings))
    audit = read(bind(root/"dataset_audit.json", bindings))
    for path, key in ((dataset/"dataset_manifest.json", "dataset_manifest_sha256"),
                      (root/"dataset_audit.json", "audit_sha256"), (language/"language_manifest.json", "language_manifest_sha256")):
        if file_hash(bind(path, bindings)) != acceptance[key]:
            raise ValueError("final acceptance source changed: " + key)
    if len(dataset_manifest["episodes"]) != 20 or {e["run_id"] for e in dataset_manifest["episodes"]} != {r["run_id"] for r in rows}:
        raise ValueError("exported episode set differs from twenty pilot runs")
    by_id = {r["run_id"]: r for r in rows}
    for entry in dataset_manifest["episodes"]:
        episode = checked_path(dataset, entry["directory"])
        if (entry.get("analysis_selection_mode") != "explicit_manifest_binding"
                or Path(entry.get("source_analysis_path", "")).resolve() != Path(by_id[entry["run_id"]]["analysis_directory"])
                or file_hash(episode/"manifest.json") != entry["analysis_manifest_sha256"]):
            raise ValueError("dataset lost its explicit selected analysis")
        verify_manifest(episode, episode/"manifest.json", bindings)
    lang = language_evidence(language, bindings)
    if lang["manifest"]["dataset_manifest_sha256"] != file_hash(dataset/"dataset_manifest.json"):
        raise ValueError("language dataset binding differs")
    payload = read(language/"descriptions.json")
    described = {d["episode_id"] for d in payload["descriptions"]}
    lang["described_episode_count"] = len(described)
    lang["by_intent"] = {}
    for intent in INTENTS:
        members = [r for r in rows if r["intent"] == intent]
        ids = {r["run_id"] for r in members}
        lang["by_intent"][intent] = dict(total=len(ids), described=len(ids & described),
            eligible_agree=sum(r["episode_quality_eligible"] is True and r["semantic_consistency"] == "agree" for r in members),
            skipped=sum(s["episode_id"] in ids for s in payload["skipped"]),
            descriptions=sum(d["episode_id"] in ids for d in payload["descriptions"]))
    groups = {group["intent"]: group for group in audit["groups"]}
    if len(groups) != len(audit["groups"]) or set(groups) != set(INTENTS):
        raise ValueError("one audit control-mode group per intent required")
    distributions = {intent: dict(groups[intent]["metrics"]) for intent in INTENTS}
    for intent in INTENTS:
        passing = [r.get("minimum_passing_speed_m_s") for row in rows if row["intent"] == intent
                   for r in read(Path(row["analysis_directory"])/"execution_metrics.json")["intermediate_waypoints"]["records"]]
        distributions[intent]["minimum_passing_speed_m_s"] = summary(passing)
    outcomes, soft, semantic = intent_evidence(rows)
    report = dict(version=VERSION, created_utc=datetime.now(timezone.utc).isoformat(), stage="pause_1",
        control_path=str(root/"control.json"), acceptance=acceptance, dataset_episode_count=20,
        audit_issues=audit.get("issues", []), rows=rows, outcomes=outcomes, soft_rates=soft,
        semantic_flags=semantic, rolling=control["rolling"], execution_distributions=distributions,
        language=lang, resources=resource_estimate(rows, dataset, language), references=REFERENCES,
        integrity=dict(include_runtime=False, historical_and_protected_verified=True,
            reason="post-finalization documents may change; immutable history, source evidence, runtime archive and protected files remain checked"),
        source_sha256=bindings)
    for path, expected in bindings.items():
        if file_hash(path) != expected:
            raise ValueError("source changed during report build: " + path)
    integrity(control, include_runtime=False)
    body = markdown(report, output, document)
    output.mkdir(parents=True, exist_ok=False)
    save_new(output/"report.json", report)
    with document.open("x", encoding="utf-8") as handle:
        handle.write(body)
    save_new(output/"output_manifest.json", dict(version=VERSION, source_count=len(bindings),
        artifact_sha256={str(path): file_hash(path) for path in (output/"report.json", document)}))
    return dict(document=str(document), output=str(output), run_count=20, source_count=len(bindings))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PP)
    parser.add_argument("--output", type=Path, default=ROOT/"tmp_v05/r12b_pause1")
    parser.add_argument("--document", type=Path, default=ROOT/"docs/v0.5_r1.2b_pause1_report.md")
    args = parser.parse_args()
    print(json.dumps(build(args.root, args.output, args.document), ensure_ascii=False))


if __name__ == "__main__":
    main()
