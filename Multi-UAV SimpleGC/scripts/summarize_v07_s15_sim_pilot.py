"""S15 simulation pilot statistics: read-only tables over one pilot attempt.

Reads the pilot attempt, the registered draw selection and the per-episode labels.json, and writes
docs/v07/evidence/s15/s15_sim_pilot_summary.json and s15_sim_pilot_tables.md. Failure stages are
classified only from fields the records already carry; no planner, M1, M2 or fastsim code is touched.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from task_v07.expansion.contracts import P0ContractError
from task_v07.expansion.views import MODES, _paired
from task_v07.io import read_json, save_json, sha

OUT_DIR = PROJECT / "docs/v07/evidence/s15"
INTENTS = ("transit", "reconnaissance", "monitoring", "feint", "penetration")
INFEASIBLE_STAGE = {"geometry_pool_empty": "规划", "rehearsal_failure": "单机预演",
                    "timing_conflict": "时刻叠加间距"}
STAGE_ORDER = ("规划", "单机预演", "时刻叠加间距", "联合执行（超时）", "联合执行（质量）",
               "M1 角色判据", "审计")


def distribution(values):
    values = sorted(value for value in values if value is not None)
    if not values:
        return {"count": 0, "min": None, "p50": None, "p90": None, "max": None}

    def quantile(p):
        index = (len(values) - 1) * p
        low = int(index)
        return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (index - low)

    return {"count": len(values), "min": round(values[0], 6), "p50": round(quantile(.5), 6),
            "p90": round(quantile(.9), 6), "max": round(values[-1], 6)}


def failure_stage(row):
    """Map recorded state/reason fields onto the chain order; nothing is inferred beyond them."""
    if row.get("state") == "infeasible":
        key = row.get("category") or row.get("reason")
        return INFEASIBLE_STAGE.get(key, f"规划层未归类:{key}")
    if row.get("state") == "generation_error":
        return "联合执行（质量）"
    if row.get("execution_status") != "completed":
        return "联合执行（超时）"
    if row.get("all_groups_complete") is not True or row.get("task_result") != "success":
        return "M1 角色判据"
    if row.get("audit_passed") is not True or (row.get("audit") or {}).get("independent_status") != "PASS":
        return "审计"
    return None


def stage_walls(rows, skeleton_root):
    """Per-stage wall clock from the fields that exist.

    planning = group_search_metrics[*].wall_s + combination_search.wall_s (candidate_pool.json);
    the records do not separate solo rehearsal from timing selection, nor M1 judgement from audit,
    so those pairs are reported merged from the row fields that do exist. A skeleton with no episode
    row (not run, or cut off by the wall-clock cap) has no decomposition at all: its interrupted
    candidate_pool.json is not a stage measurement, so every stage stays None.
    """
    if not rows:
        return {"规划": None, "单机预演+时刻安排": None, "联合仿真": None,
                "M1判定+审计+测量+写盘": None, "skeleton_total": None}
    planning = None
    pool = skeleton_root / "candidate_pool.json"
    if pool.exists():
        blob = read_json(pool)
        metrics = blob.get("group_search_metrics") or {}
        planning = sum((value.get("wall_s") or 0.0) for value in metrics.values()) \
            + ((blob.get("combination_search") or {}).get("wall_s") or 0.0)
    setup = sum((row.get("amortized_skeleton_setup_s") or 0.0) for row in rows)
    joint = sum((row.get("simulation_wall_s") or 0.0) for row in rows)
    post = sum((row.get("episode_postprocess_wall_s") or 0.0) for row in rows)
    return {"规划": planning,
            "单机预演+时刻安排": None if planning is None else setup - planning,
            "联合仿真": joint,
            "M1判定+审计+测量+写盘": post,
            "skeleton_total": None if planning is None else setup + joint + post}


def label_facts(labels_path):
    """Dwell and revisit detections exactly as the M1 labels recorded them."""
    if not labels_path.exists():
        return None
    labels = read_json(labels_path)
    dwell = revisit = observation = agents = 0
    for agent in (labels.get("agents") or {}).values():
        contribution = (agent.get("observed") or {}).get("contribution") or {}
        if not contribution:
            continue
        agents += 1
        dwell += int(bool((contribution.get("dwell") or {}).get("detected")))
        revisit += int(bool((contribution.get("revisit") or {}).get("detected")))
        if contribution.get("observation_dwell") is not None:
            observation += int(bool(contribution["observation_dwell"].get("detected")))
    shared = {gid: (group.get("observed") or {}).get("shared_revisit")
              for gid, group in (labels.get("task_groups") or {}).items()}
    return {"agents_with_contribution": agents, "dwell_detected": dwell,
            "revisit_detected": revisit, "observation_dwell_detected": observation,
            "shared_revisit": shared}


def markdown_table(rows, columns, row_label=""):
    lines = ["| " + " | ".join([str(row_label or "-")] + [str(column) for column in columns]) + " |",
             "|" + "---|" * (len(columns) + 1)]
    for key, cells in rows:
        lines.append("| " + " | ".join([str(key)] + [str(cells.get(column, "")) for column in columns]) + " |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    pilot = args.pilot.resolve()
    for required in ("registration.json", "run_result.json"):
        if not (pilot / required).exists():
            raise P0ContractError(f"{pilot} has no {required}; an attempt that has not finished "
                                  "cannot be summarised")
    registration = read_json(pilot / "registration.json")
    run_result = read_json(pilot / "run_result.json")
    selection = read_json(Path(registration["skeletons_file"]))
    draw_of, selection_mode = {}, {}
    for draw in registration["draws"]:
        if draw["draw_key"] in draw_of.values():
            raise P0ContractError(f"Duplicate draw_key in the registration: {draw['draw_key']}")
        for skeleton_id in draw["skeletons"]:
            draw_of[skeleton_id] = draw["draw_key"]
            selection_mode[skeleton_id] = draw["approach_mode"]
    undeclared = sorted(set(registration["selected_skeletons"]) - set(draw_of))
    if undeclared:
        raise P0ContractError(f"The attempt ran skeletons that no registered draw declares: {undeclared}")
    rows = read_json(pilot / "episode_records.json") if (pilot / "episode_records.json").exists() else []
    records, anomalies = [], []
    for skeleton_id in registration["selected_skeletons"]:
        subset = [row for row in rows if row["skeleton_id"] == skeleton_id]
        skeleton_root = pilot / skeleton_id
        ordering = {mode: index for index, mode in enumerate(MODES)}
        subset.sort(key=lambda row: ordering.get(row.get("mode"), 99))
        paired = None
        try:
            paired = _paired(subset)
        except P0ContractError as exc:
            paired = f"P0:{exc}"
            anomalies.append({"kind": "pair_contract_error", "skeleton_id": skeleton_id, "detail": str(exc)})
        rounds = sorted({row.get("single_agent_calibration_rounds") for row in subset
                         if row.get("single_agent_calibration_rounds") is not None})
        failures, reasons = {}, Counter()
        for row in subset:
            stage = failure_stage(row)
            if stage is None:
                continue
            failures[row.get("mode")] = stage
            reasons[f"{row.get('mode')}:{stage}:{row.get('reason') or row.get('category')}"] += 1
        facts = {"dwell_detected": 0, "revisit_detected": 0, "observation_dwell_detected": 0,
                 "agents_with_contribution": 0}
        measured = []
        separations = []
        for row in subset:
            separations.append(row.get("minimum_separation_m"))
            for value in (row.get("measured_approach_by_group") or {}).values():
                measured.append(value)
            if row.get("path"):
                label = label_facts(pilot / row["path"] / "labels.json")
                if label:
                    for key in ("dwell_detected", "revisit_detected", "observation_dwell_detected",
                                "agents_with_contribution"):
                        facts[key] += label[key]
        specified = selection_mode.get(skeleton_id)
        records.append({
            "skeleton_id": skeleton_id, "draw": draw_of.get(skeleton_id),
            "intent": (subset[0]["intent"] if subset else None) or "-",
            "specified_approach_mode": specified,
            "rows": len(subset), "modes": [row.get("mode") for row in subset],
            "states": {row.get("mode"): row.get("state") for row in subset},
            "strict_pair": paired, "calibration_rounds": rounds,
            "failure_stage_by_mode": failures, "failure_reasons": dict(reasons),
            "measured_approaches": measured,
            "measured_approach_matches_spec": [value == specified for value in measured],
            "minimum_separation_m": separations,
            "dwell_detected": facts["dwell_detected"], "revisit_detected": facts["revisit_detected"],
            "observation_dwell_detected": facts["observation_dwell_detected"],
            "agents_with_contribution": facts["agents_with_contribution"],
            "stage_wall_s": stage_walls(subset, skeleton_root),
            "wall_s": run_result["per_skeleton"].get(skeleton_id, {}).get("wall_s")})
    measured_pairs = [record for record in records if record["strict_pair"] is True]
    stage_counter = Counter(record["failure_stage_by_mode"].get(mode) for record in records
                            for mode in MODES if record["failure_stage_by_mode"].get(mode))
    reason_counter = Counter(key for record in records for key in record["failure_reasons"])
    draws = {}
    for draw in registration["draws"]:
        members = [record for record in records if record["draw"] == draw["draw_key"]]
        ran = len(members)
        draws[draw["draw_key"]] = {
            "approach_mode": draw["approach_mode"], "layout": draw["layout"],
            "facility_count": draw["facility_count"], "group_count": draw["group_count"],
            "member_counts": draw["member_counts"], "skeletons": len(draw["skeletons"]),
            "ran": ran,
            "strict_pairs": sum(record["strict_pair"] is True for record in members),
            "all_five_paired": (ran == len(draw["skeletons"])
                                and all(record["strict_pair"] is True for record in members)),
            "failing_intents": sorted(record["intent"] for record in members
                                      if record["rows"] and record["strict_pair"] is not True),
            "failure_stages": sorted({stage for record in members
                                      for stage in record["failure_stage_by_mode"].values()})}
    matches = [value for record in records for value in record["measured_approach_matches_spec"]]
    by_intent = {}
    for intent in INTENTS:
        subset = [record for record in records if record["intent"] == intent]
        by_intent[intent] = {
            "skeletons": len(subset), "strict_pairs": sum(r["strict_pair"] is True for r in subset),
            "agents_with_contribution": sum(r["agents_with_contribution"] for r in subset),
            "dwell_detected": sum(r["dwell_detected"] for r in subset),
            "revisit_detected": sum(r["revisit_detected"] for r in subset),
            "observation_dwell_detected": sum(r["observation_dwell_detected"] for r in subset),
            "calibration_rounds": dict(Counter(round_value for r in subset for round_value in r["calibration_rounds"]))}
    stage_columns = ("规划", "单机预演+时刻安排", "联合仿真", "M1判定+审计+测量+写盘", "skeleton_total")
    summary = {"schema": "traj2language.s15_sim_pilot_summary/1",
               "generated_utc": datetime.now(timezone.utc).isoformat(),
               "provenance": {"pilot": str(pilot), "selection": registration["skeletons_file"],
                              "entry_commit": registration["entry_commit"],
                              "registration_sha256": sha(pilot / "registration.json"),
                              "run_result_sha256": sha(pilot / "run_result.json"),
                              "script_sha256": sha(Path(__file__))},
               "attempt": {"status": run_result["status"], "selected_count": run_result["selected_count"],
                           "completed_count": run_result["completed_count"],
                           "unfinished": run_result["unfinished"], "wall_s": run_result["wall_s"],
                           "wall_limit_s": run_result["wall_limit_s"], "workers": run_result["workers"],
                           "runtime_sha256_stable": run_result["runtime_sha256_stable"],
                           "strict_pairs": sum(record["strict_pair"] is True for record in records)},
               "counts": {"skeletons": len(records), "episode_rows": len(rows),
                          "strict_paired_skeletons": len(measured_pairs),
                          "draws": len(draws), "draws_all_five_paired": sum(v["all_five_paired"] for v in draws.values()),
                          "measured_approach_comparisons": len(matches),
                          "measured_approach_matches": sum(matches)},
               "failure_stage_counts": {stage: stage_counter.get(stage, 0) for stage in STAGE_ORDER},
               "raw_reason_counts": dict(reason_counter),
               "draws": draws, "by_intent": by_intent,
               "minimum_separation_m": distribution([value for record in records
                                                     for value in record["minimum_separation_m"]]),
               "stage_wall_s": {column: distribution([record["stage_wall_s"][column] for record in records])
                                for column in stage_columns}
               | {"口径": "规划取自 candidate_pool.json 的 group_search_metrics[*].wall_s 与 "
                          "combination_search.wall_s；单机预演与时刻安排在记录中未分开，故合并为"
                          "setup 残差；M1 判定与审计、测量、写盘在记录中未分开，故合并取自 "
                          "episode_postprocess_wall_s。均未修改被测代码。"},
               "skeletons": records, "anomalies": anomalies,
               "stage_order_note": "按链路顺序取第一个失败环节；阶段来源仅限记录中已有的 state / "
                                   "reason / category / execution_status / all_groups_complete / "
                                   "task_result / audit_passed / audit.independent_status 字段"}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    save_json(args.out_dir / "s15_sim_pilot_summary.json", summary)
    lines = ["# S1.5 仿真试点统计表（下游链路：规划 → M2 预演/时刻 → 联合 fastsim → M1 → 审计）", "",
             f"- 试点 attempt：`{pilot}`",
             f"- 入口提交：`{registration['entry_commit']}`；运行状态 `{run_result['status']}`；"
             f"完成 {run_result['completed_count']}/{run_result['selected_count']}；"
             f"墙钟 {run_result['wall_s']:.1f} s（上限 {run_result['wall_limit_s']:.0f} s）；"
             f"运行前后指纹一致 {run_result['runtime_sha256_stable']}",
             f"- 严格配对（同步与递次两版都成功）：{len(measured_pairs)}/{len(records)} 个骨架；"
             f"六次抽签中五意图全部配对的 {sum(v['all_five_paired'] for v in draws.values())}/{len(draws)} 次",
             f"- 失败环节计数（按链路顺序取第一个失败环节）：{json.dumps(summary['failure_stage_counts'], ensure_ascii=False)}",
             f"- 实测逼近方式与抽签指定一致：{sum(matches)}/{len(matches)} 次比较", ""]
    lines += ["## P1 逐骨架：严格配对、轮数、失败环节与墙钟", "",
              markdown_table([(record["skeleton_id"],
                               {"draw": record["draw"].split("#")[0][-12:] + "#" + record["draw"].split("#")[1],
                                "intent": record["intent"],
                                "指定方式": record["specified_approach_mode"],
                                "严格配对": record["strict_pair"],
                                "轮数": "/".join(str(v) for v in record["calibration_rounds"]) or "-",
                                "状态": "/".join(f"{m}={s}" for m, s in record["states"].items()),
                                "失败环节": "/".join(f"{m}:{s}" for m, s in record["failure_stage_by_mode"].items()),
                                "墙钟s": None if record["wall_s"] is None else round(record["wall_s"], 3)})
                              for record in records],
                             ["draw", "intent", "指定方式", "严格配对", "轮数", "状态", "失败环节", "墙钟s"],
                             row_label="skeleton_id"), ""]
    lines += ["## P2 原始 reason 计数（未归类前的字面值）", "",
              markdown_table([(key, {"count": value}) for key, value in sorted(reason_counter.items())],
                             ["count"], row_label="mode:stage:reason"), ""]
    lines += ["## P3 按抽签：五个意图是否全部得到严格配对", "",
              markdown_table([(key, {"approach_mode": value["approach_mode"], "layout": value["layout"],
                                     "facility_count": value["facility_count"],
                                     "group_count": value["group_count"],
                                     "member_counts": "/".join(str(v) for v in value["member_counts"]),
                                     "本次运行": f"{value['ran']}/{value['skeletons']}",
                                     "严格配对": (f"{value['strict_pairs']}/{value['ran']}"
                                                  if value["ran"] else "未运行"),
                                     "五意图全配对": (value["all_five_paired"] if value["ran"]
                                                      == value["skeletons"] else "n/a"),
                                     "未配对意图": ", ".join(value["failing_intents"]) or "-",
                                     "失败环节": ", ".join(value["failure_stages"]) or "-"})
                              for key, value in sorted(draws.items())],
                             ["approach_mode", "layout", "facility_count", "group_count", "member_counts",
                              "本次运行", "严格配对", "五意图全配对", "未配对意图", "失败环节"], row_label="family#slot"), ""]
    lines += ["## P4 M1 实测事实：逼近方式一致性与驻留/重访检出", "",
              markdown_table([(intent, {"骨架": value["skeletons"], "严格配对": value["strict_pairs"],
                                        "参与成员": value["agents_with_contribution"],
                                        "驻留检出": value["dwell_detected"],
                                        "重访检出": value["revisit_detected"],
                                        "观察驻留检出": value["observation_dwell_detected"],
                                        "轮数分布": json.dumps(value["calibration_rounds"], ensure_ascii=False)})
                              for intent, value in by_intent.items()],
                             ["骨架", "严格配对", "参与成员", "驻留检出", "重访检出", "观察驻留检出", "轮数分布"],
                             row_label="intent"), "",
              f"- 实测逼近方式与指定一致：{sum(matches)}/{len(matches)} 次（逐骨架见 P1 与 summary JSON 的 "
              "measured_approach_matches_spec）。", ""]
    lines += ["## P5 实测最小机间距（m，取全部 episode 行）", "",
              markdown_table([("all", summary["minimum_separation_m"])],
                             ["count", "min", "p50", "p90", "max"], row_label="范围"), ""]
    lines += ["## P6 每骨架分阶段墙钟（s）", "",
              markdown_table([(record["skeleton_id"],
                               {column: (None if record["stage_wall_s"][column] is None
                                         else round(record["stage_wall_s"][column], 3))
                                for column in stage_columns}) for record in records],
                             list(stage_columns), row_label="skeleton_id"), "",
              "口径：记录未分阶段计时。规划取自 `candidate_pool.json` 的 `group_search_metrics[*].wall_s` 与 "
              "`combination_search.wall_s`；单机预演与时刻安排在记录中不分开，合并为 setup 残差"
              "（各 mode 的 `amortized_skeleton_setup_s` 之和减去规划）；联合仿真取 `simulation_wall_s`；"
              "M1 判定、审计、测量与写盘在记录中不分开，合并取 `episode_postprocess_wall_s`。"
              "未为取得更细的分段而修改被测代码。", ""]
    lines += ["## P7 分阶段分布汇总（s）", "",
              markdown_table([(column, summary["stage_wall_s"][column]) for column in stage_columns],
                             ["count", "min", "p50", "p90", "max"], row_label="阶段"), ""]
    if anomalies:
        lines += ["## 异常记录", "",
                  markdown_table([(item["kind"] + ":" + item["skeleton_id"], {"detail": item["detail"]})
                                  for item in anomalies], ["detail"], row_label="kind"), ""]
    (args.out_dir / "s15_sim_pilot_tables.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print({"skeletons": len(records), "rows": len(rows), "strict_pairs": len(measured_pairs),
           "draws_all_five_paired": sum(v["all_five_paired"] for v in draws.values()),
           "approach_matches": f"{sum(matches)}/{len(matches)}",
           "failure_stages": summary["failure_stage_counts"], "anomalies": len(anomalies)}, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
