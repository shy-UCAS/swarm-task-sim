"""Read-only Pause 1 report from completed r1.2a validation/pilot evidence.

No simulator, reanalysis, re-export, or acceptance mutation is performed. A new
output directory is required; the Markdown report is written only after all
source bindings and completed controller gates have been verified.
"""

import argparse
import json
import math
import shutil
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.report_v05_r12 import build_report, finite, summarize
from scripts.run_v05_r12_validation import assert_integrity, validation_attempts_clean
from scripts.run_v05_r12_pp import integrity, terminal_rows
from swarm_sim.generation import checked_path, file_hash

VERSION = "v05_pause1_report_r12a_v1"
VAL = ROOT / "verification/v05_r12_validation_20261002"
PP = ROOT / "verification/v05_r12_pp_20261002"
BASELINE = ["docs/v05_m0_baseline.md", "tmp_v05/m0/seed_dependency_review.json",
            "tmp_v05/m0/protected_baseline.json", "tmp_v05/m0/baseline_tests.log",
            "tmp_v05/r/wp_r_evidence.json", "tmp_v05/wp_m/m04_artifacts_regression.json",
            "tmp_v05/r12_progress/m03_history_regression_all_phases.json",
            "tmp_v05/r12_progress/regression_sample_quantization.json",
            "tmp_v05/r12/vp1_r1_r12_comparison.json", "tmp_v05/r12a/offline_readiness.json",
            "tmp_v05/r12a/review.json",
            "docs/v0.5_r1.2_addendum.md", "docs/v0.5_r1.2_offline_stop_01.md"] + [
            f"docs/v0.5_wp_{k}_offline_report.md" for k in "hrtmpl"]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fmt(value, places=3):
    return f"{value:.{places}f}" if finite(value) else "null"


def dist(value, quantile="p90"):
    return (f"{fmt(value.get('median'))} / {fmt(value.get(quantile))} / {fmt(value.get('max'))}"
            f"（已知 {value.get('count', 0)} / 未知 {value.get('missing_values', value.get('unknown_count', 0))}）")


def verify_manifest(root, path, bindings):
    manifest = read(path)
    bindings[str(path.resolve())] = file_hash(path)
    for relative, expected in manifest.get("artifact_sha256", {}).items():
        source = checked_path(root, relative)
        if file_hash(source) != expected:
            raise ValueError("manifest artifact changed: " + str(source))
        bindings[str(source.resolve())] = expected
    return manifest


def wilson(successes, count, confidence=1-.05/6):
    if not count:
        return [None, None]
    z = statistics.NormalDist().inv_cdf((1+confidence)/2)
    p, denom = successes/count, 1+z*z/count
    center = (p+z*z/(2*count))/denom
    radius = z*math.sqrt(p*(1-p)/count+z*z/(4*count*count))/denom
    return [center-radius, center+radius]


def numbering(manifest):
    candidates = {c["candidate_id"]: c for c in manifest["candidates"]}
    groups, rows = defaultdict(list), []
    for base in manifest["bases"]:
        c = candidates[base["selected_candidate"]]
        p = c["sampled_parameters"]
        axes = ("east_m", "north_m") if p["entry_side"] in ("north", "south") else ("north_m", "east_m")
        vehicles = sorted(p["spatial_slots"], key=lambda v: (v[axes[0]], v[axes[1]], v["heading_deg"]))
        n = len(vehicles)
        row = dict(base_index=base["base_index"], candidate_id=c["candidate_id"], vehicle_count=n,
                   spatial_ids=[v["id"] for v in vehicles], first_rank_match=vehicles[0]["id"] == "uav_01",
                   full_permutation_match=[v["id"] for v in vehicles] == [f"uav_{i:02d}" for i in range(1,n+1)])
        rows.append(row)
        groups[n].append(row)
    output = []
    for n, values in sorted(groups.items()):
        item = dict(vehicle_count=n, scene_count=len(values))
        for key, baseline in (("first_rank_match", 1/n), ("full_permutation_match", 1/math.factorial(n))):
            hits = sum(v[key] for v in values)
            item[key] = dict(hits=hits, fraction=hits/len(values), baseline=baseline,
                             confidence=1-.05/6, wilson_interval=wilson(hits,len(values)))
        output.append(item)
    return dict(groups=output, scenes=rows, rank_rule="N/S:east,north,heading; E/W:north,east,heading; never ID",
                denominator="one selected candidate per physical base scene, never duplicate by intent",
                interval="two-sided Wilson; six-comparison Bonferroni confidence=99.1667%; descriptive only")


def language_evidence(language, bindings):
    manifest = verify_manifest(language, language/"language_manifest.json", bindings)
    descriptions = read(language/"descriptions.json")["descriptions"]
    facts = {p.stem:read(p) for p in sorted((language/"facts").glob("*.json"))}
    counts, checked = Counter(), Counter()
    records, special = [], []
    for run_id, fact in facts.items():
        fields = fact["channel_check"]["fields_checked"]
        checked.update(str(f) for f in fields)
        disagreements = fact["channel_check"]["disagreements"]
        counts.update(d["field"] for d in disagreements)
        is_special = fact["labels"]["mission_result"]["success"] is not True or fact["observed"].get("observed_pattern") in (None,"unclear")
        if is_special:
            special.append(run_id)
        records.append(dict(run_id=run_id,intent=fact["labels"]["assigned_intent"],
             mission_success=fact["labels"]["mission_result"]["success"], observed_pattern=fact["observed"].get("observed_pattern"),
             fields_checked=len(fields), disagreement_count=len(disagreements), disagreements=disagreements))
    selected = []
    for intent in ("patrol","reconnaissance"):
        for partition in ("train","test"):
            choice = next(d for d in descriptions if d["template_partition"] == partition and
                          facts[d["episode_id"]]["labels"]["assigned_intent"] == intent)
            selected.append(choice)
    choice = next((d for d in descriptions if d["episode_id"] in special and d not in selected), None)
    if choice is None:
        choice = next(d for d in descriptions if d not in selected and d["episode_id"] not in {s["episode_id"] for s in selected})
    selected.append(choice)
    return dict(manifest=manifest, sample_descriptions=selected, exceptional_episode_ids=special,
                records=records, disagreements_by_field=dict(counts), checked_by_field=dict(checked),
                total_field_checks=sum(checked.values()), total_disagreements=sum(counts.values()),
                episodes_with_disagreements=sum(bool(r["disagreement_count"]) for r in records))


def bytes_in(path):
    return sum(p.stat().st_size for p in Path(path).rglob("*") if p.is_file())


def resources(rows, dataset, language):
    raw = [bytes_in(r["run_directory"]) for r in rows]
    attempts = [(datetime.fromisoformat(r["finished_utc"])-datetime.fromisoformat(r["reserved_utc"])).total_seconds() for r in rows]
    sizes = dict(run_directories=sum(raw), dataset=bytes_in(dataset), descriptions=bytes_in(language))
    mean = sum(sizes.values())/len(rows)
    elapsed = sum(attempts)/len(attempts)
    free = shutil.disk_usage(ROOT).free
    return dict(per_run_directory_bytes=summarize(raw), per_attempt_wall_s=summarize(attempts),
                current_pilot_bytes=sizes, total_pilot_bytes=sum(sizes.values()), remaining_runs=240,
                estimate_remaining_bytes=mean*240, estimate_remaining_hours=elapsed*240/3600,
                conservative_remaining_bytes=(max(raw)+(sizes["dataset"]+sizes["descriptions"])/len(rows))*240,
                conservative_remaining_hours=max(attempts)*240/3600, free_bytes=free,
                two_times_estimate_available=free>=2*mean*240,
                basis="20 completed pilot runs; run directories include original and r1.2 analyses; dataset/language copies included; attempt wall time includes launch, collection and analysis, excludes future interruptions/retries")


def ac4_sources(diagnostics, bindings):
    groups = defaultdict(list)
    for run in diagnostics["runs"]:
        path = Path(run["analysis_directory"])/"ac4_timing_v3.json"
        bindings[str(path.resolve())] = file_hash(path)
        ac4 = read(path)
        semantic = {p["phase"]:p["semantic_phase"] for p in run["phase_metrics"]}
        for channel, obj in ac4["channels"].items():
            for phase, values in obj["per_phase"].items():
                for source in ("primary","crosscheck"):
                    groups[run["stage"],run["intent"],semantic[phase],channel,source].append(values.get(source,{}))
    out = []
    for key, rows in sorted(groups.items()):
        out.append(dict(stage=key[0],intent=key[1],phase=key[2],channel=key[3],source=key[4],
            count=len(rows),D_s=summarize(r.get("D_s") for r in rows),
            exceeds=sum(finite(r.get("D_s")) and finite(r.get("tau_s")) and r["D_s"]>r["tau_s"] for r in rows),
            unknown=sum(not finite(r.get("D_s")) or r.get("complete") is not True for r in rows)))
    return out


def dr_evidence(bindings):
    output = {}
    for name, folder in (("v05","dr"),("v05b","dr_v05b"),("v05c","dr_v05c")):
        root = ROOT/"tmp_v05"/folder
        review = read(root/"review.json")
        generation = read(root/"generated_130/generation_manifest.json")
        for p in (root/"review.json",root/"generated_130/generation_manifest.json"):
            bindings[str(p.resolve())] = file_hash(p)
        prefilter, full = Counter(), Counter()
        for c in generation["candidates"]:
            for a in c.get("attempts",[]):
                reason = a.get("reason","")
                if "patrol_spacing_prefilter" in reason:
                    prefilter[a["intent"]]+=1
                elif "time-aware" in reason:
                    full[a["intent"]]+=1
        output[name] = dict(review=review, prefilter_rejections=dict(prefilter), full_checker_rejections=dict(full))
    return output


BASELINE_TEXT = r"""## 1. M0 与离线验收

M0 开工 HEAD 为 `c204d1d013cdc668aa1979c66687d58c6a551da6`，430 项基线测试通过，建立 11,307 个受保护文件清单。已知问题 6 **有条件成立**：旧规则未显式给 `template_id` 时，默认 ID 来自整个模板（含 execution），改变驻留会改变任务种子；V06 显式固定 ID，种子不变。WP-R 的 `task_semantics_only_v1` 将种子绑定到 mission/planner 语义，R06 验证执行参数变化不改变任务种子和物理场景，旧 V06 33/33 个 JSON 保持哈希。详见 [M0](v05_m0_baseline.md)、[种子核查](../tmp_v05/m0/seed_dependency_review.md)和 [WP-R](v0.5_wp_r_offline_report.md)。

| 工作包 | 已完成离线门禁 | 证据 |
| --- | --- | --- |
| H | H01–H03；整数秒、16 个旧例兼容、上传与 BIN 项逐机逐阶段核对 | [H](v0.5_wp_h_offline_report.md) |
| R | R01–R06；1000 样本约束/编号、自动轴、种子解耦及旧数据哈希 | [R](v0.5_wp_r_offline_report.md) |
| T | T01–T02；有上限的时序容差、绕角反例、预筛选和完整间距检查分开 | [T](v0.5_wp_t_offline_report.md) |
| M | M01/M02 和新增“后一圈更近”测试通过；M04 的 14 份历史执行伪影逐字段回放一致；M03 按 r1.2a 72 项判定一致，最大 \(|\Delta D|=0.065599628\,\mathrm{s}<0.2\,\mathrm{s}\) | [原 M](v0.5_wp_m_offline_report.md)、[新就绪门禁](../tmp_v05/r12a/offline_readiness.json) |
| P | P01–P08；巡逻规划/判据、双通道三值语义、统一协议和混版拒绝 | [P](v0.5_wp_p_offline_report.md) |
| L | L01–L07；事实/标签/模型指标分离、双通道逐事实核对、模板划分、描述一致性与绑定 | [L](v0.5_wp_l_offline_report.md) |

原 M03 的 4 项大于 \(0.05\,\mathrm{s}\) 记录及量化原因、原 r1.2 离线 FAIL、原 VP1 r1 FAIL 均保留。r1.2a 仅修订采样回归口径；`ordered_route_progress_v2` 实现不改。历史工作包报告中关于 VP4、HD、AC4 运行硬门禁的旧文字以 [r1.2/r1.2a](v0.5_r1.2_addendum.md)为准。旧日志是已绑定历史证据，不能称为本轮重新执行的测试。

## 2. DR、拒绝原因和选择偏差

v05、v05b、v05c 的 profile 与 DR 均保留。v05c 与 v05b 逐项核对 206 个候选、412 个候选任务、260 个接受场景，除固定零航向和派生 family/哈希外，采样、接受、种子和规划结果相同；完整 JSON 同本报告附件绑定。
"""


def markdown(report, output):
    val, pp, acceptance = report["validation"],report["pilot"],report["pilot_acceptance"]
    diag = report["diagnostics"]
    relative = "../"+output.relative_to(ROOT).as_posix()
    out = ["# v0.5 暂停 1 合并报告（r1.2a）", "",
        "**结论：验证与试生产通过，已到暂停 1，等待用户确认后才可执行剩余 240 次批量生成。**",
        f"验证累计 {val['sitl_attempts_consumed']}/8；试生产 {pp['aggregate']['logical_completed']}/20 次完成，尝试 {pp['aggregate']['attempts']}/22。VP1 复用原始运行，新旧结论并列；软标记不改变质量资格。", "",
        f"本报告的完整分母、逐运行数值及输入 SHA256 见[报告 JSON]({relative}/report.json)，[进场与软指标逐项附件]({relative}/diagnostics/report.md)及其 [JSON]({relative}/diagnostics/report.json)。", "", BASELINE_TEXT,
        "| Profile | 接受 / 候选 | 联合接受率 | 接受 N=2 / 3 / 4 | 弧长预筛选拒绝 | 通用检查拒绝（巡逻 / 侦察） |",
        "| --- | --- | ---: | --- | ---: | --- |"]
    for name, dr in report["dr"].items():
        r=dr["review"]
        counts=r.get("accepted_by_n") or {n:d["count"] for n,d in r["selection_bias"]["accepted_scenes"]["discrete"]["vehicle_count"].items()}
        out.append(f"| {name} | {r['counts']['accepted_bases']} / {r['counts']['candidates']} | {r['rates']['both']['fraction']:.2%} | "+" / ".join(str(counts[str(n)]) for n in (2,3,4))+f" | {sum(dr['prefilter_rejections'].values())} | {dr['full_checker_rejections'].get('patrol',0)} / {dr['full_checker_rejections'].get('reconnaissance',0)} |")
    out += ["", "候选可同时被两个意图拒绝，逐意图拒绝数不能相加当作候选数。v05 的 N=4 占比从抽取 28.5% 降为接受 3.1%，N=2 从 38.6% 升为 81.5%；v05b/c 按 N 分层接受 44/43/43，编队仅 line。v05b/c 的进场方向偏移较小，速度 3 m/s 的比例从抽取 28.2% 降为接受 23.1%，区域宽/高均值从 42.02/42.51 m 降为 39.85/40.14 m；同 N 层尺寸差异小。接受序列是条件性重抽，不视作独立同分布总体成功率。完整离散、连续及分层偏差见 [v05](v0.5_dr_review.md)、[v05b](v0.5b_dr_review.md)、[v05c](v0.5c_dr_review.md)。", "",
        "## 3. 验证验收、驻留决定与预算", "",
        "| 用例 | 运行 ID | r1.2 硬门禁 | 双通道任务成功 | 质量资格 | 软标记数 |", "| --- | --- | --- | --- | --- | ---: |"]
    for run in [r for r in diag["runs"] if r["stage"]=="validation"]:
        quality=run["validation_policy"]
        labels=read(Path(run["analysis_directory"])/"labels.json")
        out.append(f"| {run['case_id']} | `{run['run_id']}` | {'PASS' if quality['individual_pass'] else 'FAIL'} | {labels['mission_success']} / {labels.get('mission_success_observation')} | {run['episode_quality_eligible']} | {len(quality['soft_flags'])} |")
    out += ["", "VP1 原 r1 FAIL 保留，复核 r1.2 PASS 不增加 SITL 次数；v05b 失败 VP1 与原 v05c VP1 已占 2 次。后续 VP2、VP3、VR1、VR2 按 r1.1 冻结选例执行，未按进场距离差重选。两次剩余额度仅用于起飞前基础设施故障重试。参数/固件、机载项、真值最小间距、零长度航段、双通道任务/语义和已知圈数维持硬门禁。", "",
        r"**驻留决定：** VP4 和 HD 取消，正式 `terminal_hold_s=0`、`integer_seconds_v1`。依据是 v0.4 实际按 0 执行；阶段边界约 \(1\,\mathrm{s}\) 的精度继续作为已知限制。起始航向固定为 \(0^\circ\)。", "",
        "## 4. 试生产验收", "", "| r1 §11.3 门禁 | 结果 |", "| --- | --- |"]
    for gate, passed in acceptance["gate"].items():
        if gate!="pass":out.append(f"| {gate} | {'PASS' if passed else 'FAIL'} |")
    agg=pp["aggregate"]
    out += ["",f"质量合格 {agg['qualified']}/20；双意图均质量合格 {agg['pair_qualified']}/10。"]
    for intent, row in agg["by_intent"].items():
        out.append(f"{intent} 在质量合格运行中的任务成功率为 {row['success_fraction_given_quality']:.1%}。")
    out += ["", "| 试生产 / 基础场景 | 意图 | 运行 ID | 质量合格 | 任务成功 | 硬门禁 | 软标记数 |",
            "| --- | --- | --- | --- | --- | --- | ---: |"]
    for r in terminal_rows(pp["records"]):
        out.append(f"| PP{r['logical_index']+1:02d} / {r['base_index']} | {r['intent']} | `{r['run_id']}` | {r['qualified']} | {r['mission_success']} | {'PASS' if not r['hard_failures'] else 'FAIL'} | {len(r['soft_flags'])} |")
    out += ["", "试生产严格使用前 10 个被接受场景并交替运行两种意图。导出、审计、describe、加载结果均来自冻结的真实运行；质量合格失败样本不会因失败被删除。", "",
        "## 5. 按意图的执行分布", "",
        "以下为试生产的描述统计，三项数值依次为中位数 / P95 / 最大值；括号给出已知与未知数量。时长按 episode、停靠数和路径长度按飞机、过点速度按中间航点计数。停靠阈值 0.3 m/s；同步停靠比例按原采样时刻口径。", "",
        "| 指标 | patrol | reconnaissance |", "| --- | --- | --- |"]
    groups={g["intent"]:g for g in report["dataset_audit"]["groups"]}
    for label, metric in (("时长 s","episode_duration_s"),("每机停靠数","execution_stop_count"),("同步停靠比例","execution_synchronized_time_fraction"),("静止时间占比","execution_stationary_time_fraction"),("实测路径长度 m","executed_path_length_m")):
        out.append(f"| {label} | {dist(groups['patrol']['metrics'][metric], 'p95')} | {dist(groups['reconnaissance']['metrics'][metric], 'p95')} |")
    out.append(f"| 中间航点最小过点速度 m/s | {dist(report['passing_speed']['patrol'], 'p95')} | {dist(report['passing_speed']['reconnaissance'], 'p95')} |")
    out += ["", "## 6. 软门禁分布与进场诊断", "",
        "软标记仅记录，不停止，也不改变 `episode_quality_eligible`。下表分验证/试生产、意图、阶段统计；AV-1 为停靠/中间节点/未知，AV-2 为每机阶段内停靠起点计数的中位/P90/最大。AV-2 正式阈值仍作用于整段运行，未新增阶段阈值。", "",
        "| 阶段组 | 运行数 | AV-1 停靠 / 节点 / 未知 | AV-2 阶段次数分布 |", "| --- | ---: | --- | --- |"]
    for g in diag["aggregate"]["by_intent_and_phase"]:
        a=g["AV1"]
        out.append(f"| {g['stage']} / {g['intent']} / {g['semantic_phase']} | {g['run_count']} | {a['stopped_count']} / {a['waypoint_count']} / {a['unknown_count']} | {dist(g['AV2_stop_onset_count'])} |")
    out += ["", "AC4 同时列位置主值和事件交叉核对；分母为对应组内运行数，未知单独统计。圈数只对巡逻适用，每机每通道计一次。", "",
        "| 阶段组 / 通道 / 来源 | 已知 / 总数 | D 中位 / P90 / 最大 s | 超限 / 未知 |", "| --- | --- | --- | --- |"]
    for g in report["ac4_source_distributions"]:
        out.append(f"| {g['stage']} / {g['intent']} / {g['phase']} / {g['channel']} / {g['source']} | {g['D_s']['count']} / {g['count']} | {dist(g['D_s'])} | {g['exceeds']} / {g['unknown']} |")
    out += ["", "| 巡逻圈数组 | 已知 / 总数 | 未知 | 中位 / P90 / 最大 |", "| --- | --- | ---: | --- |"]
    for g in diag["aggregate"]["by_intent_and_phase"]:
        if g["semantic_phase"]=="patrol":
            for channel,t in g["channels"].items():
                d=t["lap_counts"]
                out.append(f"| {g['stage']} / {channel} | {d['count']} / {d['expected_count']} | {t['laps_unknown_count']} | {dist(d)} |")
    out += ["", "全部实际触发和未知软标记（含 AV-2 整段阈值）分布。数量按标记记录计，不等同于运行数；AV-2 可每机一条，AC4 可每通道/阶段/来源一条，同次运行可多次计数。适用运行和逐机分母见上表及 JSON，未触发不替代未知证据。", "",
        "| 组别 / 阶段 / 通道 | 代码 / 状态 / 来源 | 标记数 |", "| --- | --- | ---: |"]
    for f in diag["aggregate"]["soft_flag_counts"]:
        out.append(f"| {f['stage']} / {f['intent']} / {f['phase']} / {f['channel']} | {f['code']} / {f['status']} / {f['source']} | {f['count']} |")
    out += ["", f"所有 {len(diag['runs'])} 次运行的逐机进场航程、名义运动/完成时长、AUTO 出发、实测运动出发、双通道到达及起始航向/入环方向/转角见[完整进场表]({relative}/diagnostics/report.md)。JSON 另存实测采样航程、到达来源和证据完整性。时间零点为各运行 `phase_windows.time_epoch_host_s` 的单调时钟，非 UTC；未知不填 0。", "",
        "## 7. 编号审计", "",
        r"先按进场边切向坐标排序：南/北用 east，东/西用 north，另一坐标与航向破同值；单编号事件固定为 uav_01 位于空间第 1 名，全排列事件为编号顺序完全匹配空间顺序。每个场景只计一次，双意图不重复加样本。按 \(N\) 分组，采用六项 Bonferroni 校正的双侧 99.1667% Wilson 区间；随机基准分别是 \(1/N\)、\(1/N!\)。", "",
        "| 范围 / N | 场景数 | 单编号命中 / 比例 / 区间；基准 | 全排列命中 / 比例 / 区间；基准 |", "| --- | ---: | --- | --- |"]
    for scope,data in report["numbering"].items():
        for g in data["groups"]:
            cells=[]
            for key in ("first_rank_match","full_permutation_match"):
                v=g[key];lo,hi=v["wilson_interval"]
                cells.append(f"{v['hits']} / {v['fraction']:.2%} / [{lo:.2%}, {hi:.2%}]；{v['baseline']:.2%}")
            out.append(f"| {scope} / {g['vehicle_count']} | {g['scene_count']} | {' | '.join(cells)} |")
    out += ["", "原 WP-R 1000 个固定种子检验的六个校正区间均包含随机基准。试生产每层仅 3–4 个场景，区间很宽；此处只报告观察值，不将其作为新门禁，也不能据此声称编号与空间完全独立。", "",
        "## 8. 五条描述样例与事实层核对", ""]
    language=report["language"]
    facts_by_run={r["run_id"]:r for r in language["records"]}
    for i,d in enumerate(language["sample_descriptions"],1):
        f=facts_by_run[d["episode_id"]]
        out += [f"{i}. `{d['episode_id']}`；{f['intent']}；episode split={d['episode_split']}；模板组={d['template_partition']}；结果={f['mission_success']}；模式={f['observed_pattern']}。", "","> "+d["text"],""]
    out += [f"失败或模式不明确 episode 共 {len(language['exceptional_episode_ids'])} 个；"+("已在样例中优先纳入。" if language['exceptional_episode_ids'] else "当前可描述试生产样本中不存在，未编造失败样例。"), "",
        f"事实层共检查 {language['total_field_checks']} 个字段，分歧 {language['total_disagreements']} 项，涉及 {language['episodes_with_disagreements']}/{len(language['records'])} 个 episode。分歧字段从描述中省略；任务指定意图、任务子条件与理想模型覆盖指标仍各自分栏。", "",
        "| 分歧字段 | 分歧数 / 检查数 |", "| --- | --- |"]
    for field,count in sorted(language["disagreements_by_field"].items()):
        out.append(f"| {field} | {count} / {language['checked_by_field'].get(field,0)} |")
    if not language["disagreements_by_field"]:out.append("| 无 | 0 / 全部已检查字段 |")
    r=report["resources"]
    out += ["", "## 9. 批量磁盘和耗时估算", "",
        f"20 次试生产运行目录、导出副本和描述合计 {r['total_pilot_bytes']/2**30:.3f} GiB；当前可用空间 {r['free_bytes']/2**30:.2f} GiB。按本次实测均值外推剩余 240 次，新增约 {r['estimate_remaining_bytes']/2**30:.2f} GiB、{r['estimate_remaining_hours']:.2f} h；以最慢/最大运行外推约 {r['conservative_remaining_bytes']/2**30:.2f} GiB、{r['conservative_remaining_hours']:.2f} h。当前满足估算空间两倍的开工要求：{r['two_times_estimate_available']}。", "",
        "耗时取每次控制台账 reserved→finished，含启动、采集与分析；磁盘含运行中原分析和 r1.2 分析及导出副本，未删除证据。估算不包含未来故障重试、人工中断或额外留存，正式批量前仍需重新核对可用空间，运行中保留原磁盘/质量/基础设施停止条件。", "",
        "本次授权止于暂停 1。没有启动剩余 240 次批量生成，没有增加 profile、规划器、映射算法或其他改进项。", ""]
    return "\n".join(out)


def build(output, document):
    output,document=Path(output).resolve(),Path(document).resolve()
    if output.exists() or document.exists():raise ValueError("new report output and document required")
    val,pp=read(VAL/"control.json"),read(PP/"control.json")
    acceptance=read(PP/"acceptance.json")
    if not val.get("completed") or val.get("stopped_reason") or not validation_attempts_clean(val):
        raise ValueError("validation not complete and passed")
    if not pp.get("finalized") or pp.get("stopped_reason") or not acceptance["gate"].get("pass"):
        raise ValueError("pilot not finalized and passed")
    assert_integrity(val);integrity(pp)
    bindings={str((ROOT/p).resolve()):file_hash(ROOT/p) for p in BASELINE}
    for p in (VAL/"control.json",PP/"control.json",PP/"acceptance.json",PP/"dataset_audit.json",Path(__file__)):
        bindings[str(p.resolve())]=file_hash(p)
    rows=terminal_rows(pp["records"])
    valrows=[val["vp1_reassessment"]]+[r for r in val["records"] if not r.get("retryable_pre_takeoff")]
    entries=[dict(case_id=r["case_id"],stage="validation",run_directory=r["run_directory"],analysis_directory=r["analysis_directory"]) for r in valrows]
    entries += [dict(case_id=f"PP{r['logical_index']+1:02d}",stage="pilot",run_directory=r["run_directory"],analysis_directory=r["analysis_directory"]) for r in rows]
    output.mkdir(parents=True)
    save(output/"diagnostic_inputs.json",dict(runs=entries))
    diagnostics=build_report(output/"diagnostic_inputs.json",output/"diagnostics")
    bindings.update(diagnostics["source_sha256"])
    dataset,language=PP/"dataset",PP/"dataset_language_zh_v0"
    manifest=read(dataset/"dataset_manifest.json")
    bindings[str((dataset/"dataset_manifest.json").resolve())]=file_hash(dataset/"dataset_manifest.json")
    for e in manifest["episodes"]:
        root=checked_path(dataset,e["directory"])
        if file_hash(root/"manifest.json") != e["analysis_manifest_sha256"]:raise ValueError("dataset analysis manifest changed")
        verify_manifest(root,root/"manifest.json",bindings)
    passing=defaultdict(list)
    for r in diagnostics["runs"]:
        if r["stage"]=="pilot":
            e=read(Path(r["analysis_directory"])/"execution_metrics.json")
            passing[r["intent"]].extend(v.get("minimum_passing_speed_m_s") for v in e["intermediate_waypoints"]["records"])
    bundle=read(PP/"bundle/generation_manifest.json")
    formal=read(ROOT/"tmp_v05/dr_v05c/generated_130/generation_manifest.json")
    report=dict(version=VERSION,created_utc=datetime.now(timezone.utc).isoformat(),
        stage="pause_1",validation=val,pilot=pp,pilot_acceptance=acceptance,
        diagnostics=diagnostics,dataset_audit=read(PP/"dataset_audit.json"),
        passing_speed={k:dict(**summarize(v), p95=(sorted(x for x in v if finite(x))[max(0,math.ceil(sum(finite(x) for x in v)*.95)-1)] if any(finite(x) for x in v) else None)) for k,v in passing.items()},
        dr=dr_evidence(bindings),numbering=dict(pilot_first_10=numbering(bundle),formal_accepted_130=numbering(formal)),
        language=language_evidence(language,bindings),resources=resources(rows,dataset,language),
        ac4_source_distributions=ac4_sources(diagnostics,bindings),source_sha256=bindings)
    for path,digest in bindings.items():
        if file_hash(path)!=digest:raise ValueError("source changed during report: "+path)
    text=markdown(report,output)
    save(output/"report.json",report)
    document.write_text(text,encoding="utf-8")
    save(output/"output_manifest.json",dict(version=VERSION,source_count=len(bindings),
        artifact_sha256={str(p.resolve()):file_hash(p) for p in [document,output/"report.json",output/"diagnostics/report.json",output/"diagnostics/report.md",output/"diagnostic_inputs.json"]}))
    return dict(report=str(document),output=str(output),run_count=len(entries),source_count=len(bindings))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"tmp_v05/r12a/pause1")
    parser.add_argument("--document",type=Path,default=ROOT/"docs/v0.5_pause1_report.md")
    args=parser.parse_args()
    print(json.dumps(build(args.output,args.document),ensure_ascii=False))


if __name__=="__main__":main()
