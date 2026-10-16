"""Read-only Q-D evidence collection, including approved offline end-boundary diagnostics."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.run_v07_s2_expansion import descriptor_jobs
from task_v07.execution import completion_budget
from task_v07.geometry import geometry_facts
from task_v07.io import read_json, sha
from task_v07.planning import scene_parts
from task_v07.unified.outcome import FAILURE_CATEGORIES

EVIDENCE = PROJECT / "docs/v07/evidence/m2"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: json.dumps(row[key], ensure_ascii=False, separators=(",", ":"))
                         if isinstance(row.get(key), (dict, list)) else row.get(key) for key in fields} for row in rows)


def end_diagnostics(directory, skeleton, rehearsal, scene):
    result = []
    for agent, value in rehearsal["agents"].items():
        if value["result"]["conditions"].get("ended_outside_warning") is not False:
            continue
        group = skeleton["group_skeletons"][value["group_id"]]
        budget = completion_budget(group, {member: 0. for member in group["members"]})
        solo_path = directory / f"single_agent_{agent}.npz"
        with np.load(solo_path, allow_pickle=False) as data:
            if data["agent_ids"].tolist() != [agent]:
                raise ValueError("Diagnostic solo identity differs from rehearsal")
            last_s = float(data["time_us"][-1] / 1e6)
            if last_s != value["last_sample_s"]:
                raise ValueError("Diagnostic solo duration contradicts rehearsal")
            point = data["p"][-1, 0, :2].copy()
        _, zones = scene_parts(scene, group["target_id"])
        facts = geometry_facts(zones["warning"]["geometry"], point)
        signed = float(facts["signed_distance_m"])
        if not bool(facts["inside"]):
            raise ValueError("ended_outside_warning=False contradicts the recorded final position")
        relative = directory.name
        result.append({"skeleton_id": skeleton["skeleton_id"], "round": int(relative[-2:]) + 1,
            "group_id": value["group_id"], "agent_id": agent, "target_id": group["target_id"],
            "execution_status": value["execution_status"], "solo_observed_duration_s": value["last_sample_s"],
            "conservative_budget_s": budget["max_duration_s"], "warning_boundary_distance_m": abs(signed),
            "warning_boundary_signed_distance_m": signed, "last_frame_inside_warning": True,
            "status_source": f"{relative}/rehearsal.json:agents.{agent}.execution_status",
            "duration_source": f"{relative}/rehearsal.json:agents.{agent}.last_sample_s",
            "budget_source": f"{relative}/skeleton.json:group_skeletons.{value['group_id']} -> completion_budget(group, zero_delays)",
            "distance_source": f"{relative}/single_agent_{agent}.npz:p[-1,0,:2] + registered scene warning geometry -> geometry_facts",
            "source_sha256": {name: sha(directory / name) for name in
                ("rehearsal.json", "skeleton.json", f"single_agent_{agent}.npz")}})
    return result


def update_report(summary, ended, inconsistencies):
    def short_id(sid):
        parts = sid.split("_")
        return f"{parts[2][:4]}…/ext_{parts[4]}"

    def number(value):
        return "—" if value is None else f"{value:.6g}"

    def pair_values(row, get):
        return "；".join(f"{tag}:{get(row['episodes'][mode])}" for mode, tag in
            (("synchronous", "S"), ("sequential", "Q")) if mode in row["episodes"]) or "—"

    lines = ["", f"结果：**{summary['status']}**。固定 10 个骨架、8 进程，一次运行，墙钟 {summary['wall_s']:.2f} s"
             f"（{summary['wall_s']/60:.2f} 分钟），硬上限 60 分钟。输出：`{Path(summary['attempt']).name}`。",
             "", f"结果计数：`{summary['counts']}`。单机仿真 {summary['solo_simulations']} 次"
             + ("（精确计数）" if summary["solo_count_exact"] else "（已保存轮次的下界，未完成内存轨迹可能未写盘）")
             + f"；预演 {summary['rehearsal_rounds']} 轮；联合 episode {summary['joint_episodes']} 条；审计差异 {summary['audit_differences']}。",
             "", "S 为同步，Q 为递次；最后列为结果状态不一致的机次。分段误差单位 m，定义为"
             r" \(d_{\mathrm{pred}}-d_{\mathrm{actual}}\)，每版按“单机记录结束前／后”列出。通过轮次的类别为 `null`。"
             "结束前指机对两成员均未超出各自平移后的单飞末帧，结束后指至少一成员超出。— 表示未产生或未接受。",
             "", "| 骨架简写 | 意图／登记逼近方式 | 结果 | 轮数 | 每轮类别 | 接受 draw | 执行状态 | 实测最小间距 m | 分段预测误差 m（前／后） | 预演不一致 |",
             "|---|---|---|---:|---|---|---|---|---|---:|"]
    for row in summary["rows"]:
        result = row["result"] + ("；" + pair_values(row, lambda e: e["task_result"]) if row["episodes"] else "")
        categories = "；".join(f"{r['round']}:{r['category'] or ('null' if r['status']=='passed' else '未完成')}" for r in row["rounds"])
        draws = "；".join(f"{r['round']}:S{r['synchronous'] if r['synchronous'] is not None else '—'}/"
                          f"Q{r['sequential'] if r['sequential'] is not None else '—'}" for r in row["accepted_draws_by_round"])
        error = lambda e: "/".join(number(e["prediction_error"]["segments"][segment]["minimum_error_predicted_minus_actual_m"])
                                   for segment in ("before_solo_end", "after_solo_end"))
        intent = {"transit": "过境", "reconnaissance": "侦察", "monitoring": "监视", "feint": "佯动", "penetration": "突防"}[row["intent"]]
        approach = {"same_direction": "同向", "multi_direction": "多向"}[row["registered_approach_mode"]]
        lines.append("| " + " | ".join([short_id(row["skeleton_id"]), f"{intent}／{approach}", result, str(row["round_count"]), categories or "—",
            draws or "—", pair_values(row, lambda e: e["execution_status"]),
            pair_values(row, lambda e: number(e["minimum_separation_m"])), pair_values(row, error),
            pair_values(row, lambda e: str(e["rehearsal_inconsistency_count"]))]) + " |")
    lines += ["", "完整骨架 ID、逐轮成员／条件、接受时刻参数、两段误差及实测证据见"
              " [qd_summary.json](../evidence/m2/qd_summary.json) 和 [qd_skeletons.csv](../evidence/m2/qd_skeletons.csv)。",
              "", f"预演结果状态不一致共 {summary['rehearsal_status_disagreements']} 机次，条件不一致共 "
              f"{summary['rehearsal_condition_disagreements']} 机次；逐条条件变化见"
              " [qd_rehearsal_inconsistencies.json](../evidence/m2/qd_rehearsal_inconsistencies.json)。"]
    for item in inconsistencies:
        lines.append(f"- `{item['skeleton_id']}/{item['mode']}/{item['agent_id']}`："
                     f"{item['solo_result']} → {item['joint_result']}；条件变化 `{json.dumps(item['conditions'], ensure_ascii=False)}`。")
    lines += ["", "### ended_outside_warning 成员诊断", "",
              "状态、观测时长来自同轮 `rehearsal.json` 的 `execution_status`、`last_sample_s`；"
              "时长为从 0 起的末个 10 Hz 观测时刻。预算按用户批准，从同轮 `skeleton.json` 的组骨架和全员零延迟调用 "
              "`completion_budget` 恢复保守估计。距离按用户批准，由同轮单机 NPZ 末帧 EN 坐标与注册场景的目标预警区，"
              "通过 `geometry_facts` 计算；表内为边界距离绝对值，另列内／外。未改生成器、未补仿真。",
              "", "逐列来源和未取绝对值的有符号距离见 [CSV](../evidence/m2/qd_ended_outside_warning.csv)，"
              "源文件 SHA256 见 [JSON](../evidence/m2/qd_ended_outside_warning.json)。",
              "", "| 骨架简写 | 轮次 | 成员 | 单飞状态 | 单飞观测时长 s | 保守预算 s | 距预警区边界 m | 终帧位置 |",
              "|---|---:|---|---|---:|---:|---:|---|"]
    for item in ended:
        lines.append(f"| {short_id(item['skeleton_id'])} | {item['round']} | {item['agent_id']} | {item['execution_status']} | "
                     f"{item['solo_observed_duration_s']:.1f} | {item['conservative_budget_s']:.1f} | "
                     f"{item['warning_boundary_distance_m']:.6f} | {'内' if item['last_frame_inside_warning'] else '外'} |")
    if not ended:
        lines += ["", "本次已保存轮次中没有该条件失败的成员。"]
    path = PROJECT / "docs/v07/m2/M2_report.md"
    before, remainder = path.read_text(encoding="utf-8").split("## Q-D\n", 1)
    _, after = remainder.split("## 异常与未决\n", 1)
    path.write_text(before + "## Q-D\n" + "\n".join(lines) + "\n\n## 异常与未决\n" + after,
                    encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--update-report", action="store_true")
    args = parser.parse_args()
    attempt = args.attempt
    registration = read_json(attempt / "registration.json")
    trial = read_json(attempt / "trial_result.json")
    selected = registration["selected"]
    if len(selected) != 10 or len(set(selected)) != 10 or selected != trial["selected"]:
        raise ValueError("Trial selection differs from its registration")
    source = Path(registration["source_attempt"])
    if sha(source / "registration.json") != registration["source_registration_sha256"]:
        raise ValueError("Original quick-B registration changed")
    source_selection = read_json(source / "registration.json")["selected"]
    if selected != [row["skeleton_id"] for row in source_selection]:
        raise ValueError("Trial did not use the fixed quick-B ten")
    registered_approaches = {row["skeleton_id"]: row["approach_mode"] for row in source_selection}
    jobs = {j["descriptor"]["skeleton_id"]: j for j in
            descriptor_jobs(Path(registration["descriptor_attempt"]), selected, attempt)}
    records = read_json(attempt / "episode_records.json")
    skeleton_rows, ended, inconsistencies, audits = [], [], [], []
    for sid in selected:
        root = attempt / sid
        rounds = []
        saved_solos = 0
        for directory in sorted(p for p in root.glob("geometry_[0-9][0-9]") if p.is_dir()):
            rejection = read_json(directory / "planning_rejection.json") if (directory / "planning_rejection.json").exists() else None
            rehearsal = read_json(directory / "rehearsal.json") if (directory / "rehearsal.json").exists() else None
            timing = read_json(directory / "timing_selection.json") if (directory / "timing_selection.json").exists() else None
            category = rejection["category"] if rejection else None
            if category is not None and category not in FAILURE_CATEGORIES:
                raise ValueError("Trial round category outside C11")
            rounds.append({"round": int(directory.name[-2:]) + 1, "category": category,
                "status": "rejected" if rejection else "passed" if timing and timing["status"] == "passed" else "unfinished",
                "rehearsal_status": rehearsal["status"] if rehearsal else None,
                "failures": rehearsal["failures"] if rehearsal else [],
                "timing_versions": timing["versions"] if timing else None})
            saved_solos += len(list(directory.glob("single_agent_*.npz")))
            if rehearsal:
                ended.extend(end_diagnostics(directory, read_json(directory / "skeleton.json"), rehearsal, jobs[sid]["scene"]))
        pair = [r for r in records if r["skeleton_id"] == sid]
        final = "unfinished" if sid not in trial["completed"] else (
            "paired" if len(pair) == 2 and all(r["path"] for r in pair) else "rejected")
        episodes = {}
        for row in pair:
            if not row["path"]:
                continue
            episode = attempt / row["path"]
            receipt = read_json(episode / "independent_exact_audit.json")
            differences = sum(receipt.get(key, 0) for key in
                ("region_difference_count", "target_difference_count", "event_or_metric_difference_count"))
            audit = {"episode": row["episode_id"], "status": receipt["status"], "differences": differences,
                     "input_whitelist_passed": row["audit"]["input_whitelist_passed"]}
            audits.append(audit)
            if receipt["status"] != "PASS" or differences or not audit["input_whitelist_passed"]:
                raise ValueError("Stored Q-D audit or whitelist failed")
            discrepancy = row["rehearsal_inconsistency"]
            inconsistencies.extend({"skeleton_id": sid, "mode": row["mode"], **a} for a in discrepancy["agents"])
            error = row["solo_overlay_prediction_error"]
            episodes[row["mode"]] = {
                "state": row["state"], "task_result": row["task_result"], "quality_valid": row["quality_valid"],
                "execution_status": row["execution_status"], "duration_s": row["duration_s"],
                "minimum_separation_m": row["minimum_separation_m"], "condition_digest": row["condition_digest"],
                "timing": row["timing_diagnostics"], "prediction_error": error,
                "rehearsal_inconsistency_count": discrepancy["agent_count"],
                "rehearsal_condition_difference_count": discrepancy["condition_difference_agent_count"]}
        if final == "paired" and episodes["synchronous"]["condition_digest"] != episodes["sequential"]["condition_digest"]:
            raise ValueError("Stored pair condition digests differ")
        skeleton_rows.append({"skeleton_id": sid, "intent": jobs[sid]["descriptor"]["base_intent"],
            "registered_approach_mode": registered_approaches[sid],
            "result": final, "round_count": len(rounds), "rounds": rounds,
            "round_categories": [r["category"] for r in rounds], "saved_solo_simulations": saved_solos,
            "accepted_draws_by_round": [{"round": r["round"], **{mode: r["timing_versions"][mode]["accepted_draw"]
                for mode in ("synchronous", "sequential")}} for r in rounds if r["timing_versions"] is not None],
            "final_category": pair[0].get("category") if final == "rejected" else None,
            "exhausted": pair[0].get("exhausted", False) if final == "rejected" else False,
            "episodes": episodes})
    completed = trial["status"] == "completed" and len(trial["completed"]) == 10
    summary = {"status": "PASS" if completed else trial["status"], "attempt": str(attempt),
        "entry_commit": registration["commit"], "workers": registration["workers"], "wall_s": trial["wall_s"],
        "wall_limit_s": registration["wall_limit_s"], "skeleton_count": len(selected),
        "counts": dict(Counter(r["result"] for r in skeleton_rows)),
        "rehearsal_rounds": sum(r["rehearsal_status"] is not None for row in skeleton_rows for r in row["rounds"]),
        "solo_simulations": sum(r["saved_solo_simulations"] for r in skeleton_rows),
        "solo_count_exact": completed, "solo_count_note": "exact completed solo runs" if completed else "lower bound from saved complete rounds; interrupted in-memory solos may not be saved",
        "joint_episodes": len(audits), "audit_differences": sum(a["differences"] for a in audits),
        "rehearsal_status_disagreements": sum(a["status_changed"] for a in inconsistencies),
        "rehearsal_condition_disagreements": sum(bool(a["conditions"]) for a in inconsistencies),
        "ended_outside_warning_failures": len(ended), "rows": skeleton_rows, "audits": audits,
        "provenance": {"source_registration_sha256": registration["source_registration_sha256"],
            "entry_script_sha256": registration["entry_script_sha256"],
            "frozen_config_sha256": registration["config_sha256"],
            "generator_config_sha256": registration["generator_config_sha256"],
            "attempt_file_sha256": {name: sha(attempt / name) for name in
                ("registration.json", "trial_result.json", "episode_records.json")}},
        "diagnostic_sources": {"status_duration": "rehearsal.json (duration is the last exported 10 Hz sample time, from zero)",
            "budget": "same-round group skeleton -> completion_budget(group, all member delays zero), same conservative fallback used by solo execution",
            "boundary_distance": "same-round single_agent NPZ last EN position and registered scene warning geometry -> geometry_facts; distance=abs(signed), signed<0 inside",
            "approval": "User explicitly approved these offline source supplements; no generator changes or extra simulation"},
        "stop": trial["stop"]}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    write_json(EVIDENCE / "qd_summary.json", summary)
    write_json(EVIDENCE / "qd_rehearsal_inconsistencies.json", inconsistencies)
    write_json(EVIDENCE / "qd_ended_outside_warning.json", ended)
    write_csv(EVIDENCE / "qd_skeletons.csv", skeleton_rows,
              ["skeleton_id", "intent", "registered_approach_mode", "result", "round_count", "round_categories", "accepted_draws_by_round",
               "saved_solo_simulations", "final_category", "exhausted", "episodes"])
    write_csv(EVIDENCE / "qd_ended_outside_warning.csv", ended, ["skeleton_id", "round", "group_id", "agent_id", "target_id",
        "execution_status", "solo_observed_duration_s", "conservative_budget_s", "warning_boundary_distance_m",
        "warning_boundary_signed_distance_m", "last_frame_inside_warning", "status_source", "duration_source", "budget_source", "distance_source"])
    if args.update_report:
        update_report(summary, ended, inconsistencies)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("rows", "audits", "diagnostic_sources")}, ensure_ascii=False), flush=True)
    return 0 if completed else 1


if __name__ == "__main__":
    raise SystemExit(main())
