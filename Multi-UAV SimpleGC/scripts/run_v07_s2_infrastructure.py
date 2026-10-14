"""Prepare S2 descriptors, audit existing truth, and write index-only views.

Does not call fastsim, generate role routes, execute episodes or evaluate role
success. Pending requests remain pending until external implementations exist.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scene_v07.contract import canonical_json
from task_v07.io import read_json, save_json, sha, load_episode
from task_v07.expansion.sampling import INTENTS, ROLES, sample_family_descriptors
from task_v07.expansion.contracts import (P0ContractError, validate_family_conditions,
                                         validate_model_input, permute_input, condition_digest)
from task_v07.expansion.geometry_checks import exact_frame_geometry
from task_v07.expansion.evaluation import cross_negation
from task_v07.expansion.views import make_views, diagnostic_summary
from scripts.audit_v07_s2_infrastructure import audit_geometry

DEFAULT_DATA = PROJECT.parent.parent / "SwarmData" / "v07_dataset"


def select_maps(source):
    source = Path(source).resolve()
    candidates = read_json(source / "candidates.json")
    selected = []
    for count in (1, 2, 3):
        pool = [r for r in candidates if r["accepted"] and r["facility_count"] == count and r["vehicle_count"] >= 6]
        def blocked(row):
            return any(d.get("straight_blocked_by_obstacle", False) for d in row["route_diagnostics"])
        # Development sample, intentionally enriched for blocked lines; no success filtering.
        pool.sort(key=lambda r: (not blocked(r), r["candidate_index"]))
        if len(pool) < 2:
            raise ValueError("Insufficient accepted maps with >=6 agents")
        for row in pool[:2]:
            directory = Path(row["directory"]).resolve()
            if not directory.is_relative_to(source):
                raise ValueError("Candidate directory escaped source attempt")
            scene = read_json(directory / "public_scene.json")
            family = read_json(directory / "family_initial.json")
            selected.append({"candidate": row, "scene": scene, "family": family,
                             "straight_blocked": blocked(row),
                             "source_sha256": {name: sha(directory / name) for name in ("public_scene.json", "family_initial.json")}})
    if sum(r["straight_blocked"] for r in selected) < 2:
        raise ValueError("Selection needs at least two independently obstructed straight routes")
    return selected


def prepare(selected, workers=1):
    payloads = [(r["scene"], r["family"], 2) for r in selected]
    if workers < 1:
        raise ValueError("Positive worker count required")
    if workers == 1:
        blocks = list(map(sample_family_descriptors, payloads))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            blocks = list(pool.map(sample_family_descriptors, payloads))
    records = sorted([d for block in blocks for d in block], key=lambda d: d["skeleton_id"])
    families = {r["family"]["family_id"]: r["family"] for r in selected}
    for descriptor in records:
        validate_family_conditions(descriptor, families[descriptor["family_id"]])
    return records


def requests_for(descriptors):
    requests = []
    for d in descriptors:
        modes = ("synchronous",) if d["subset"] == "aborted" else ("synchronous", "sequential")
        for mode in modes:
            requests.append({"episode_id": f"{d['skeleton_id']}_{mode}", "family_id": d["family_id"],
                             "skeleton_id": d["skeleton_id"], "intent": d["base_intent"], "mode": mode,
                             "aborted": d["subset"] == "aborted", "state": "pending", "path": None,
                             "reason": "role_planner_not_implemented", "quality_valid": None,
                             "audit_passed": None, "task_result": None, "condition_digest": condition_digest(d),
                             "agent_ids": d["agent_ids"], "scene_digest": None, "coordination_by_group": {}})
    return requests


def audit_existing(attempt):
    if attempt is None:
        return {"status": "not_run", "reason": "no prior attempt supplied"}
    roots = sorted(Path(attempt).glob("*/*/manifest.json"))
    if not roots:
        raise ValueError("No existing episodes to audit")
    rows = []
    for manifest in roots:
        root = manifest.parent
        model = load_episode(root)
        validate_model_input(model)
        other = permute_input(model, list(reversed(model["agent_ids"])))
        if not np.array_equal(other["x"], model["x"][:, ::-1]) or not np.array_equal(other["mask"], model["mask"][:, ::-1]):
            raise P0ContractError("Input ID permutation mismatch")
        with np.load(root / "truth_10hz.npz", allow_pickle=False) as data:
            run = {k: data[k] for k in ("time_us", "p", "v")}
            run["agent_ids"] = data["agent_ids"].tolist()
        with np.load(root / "frame_labels.npz", allow_pickle=False) as data:
            saved = {k: data[k] for k in ("time_us", "agent_ids", "facility_ids", "region_all_facilities",
                                         "region_assigned_target", "inside_hard_obstacle")}
        labels = read_json(root / "labels.json")
        targets = {a: labels["agents"][a]["assigned"]["target"] for a in run["agent_ids"]}
        frame, report = exact_frame_geometry(model["scene"], run, targets)
        for key in saved:
            if not np.array_equal(saved[key], frame[key]):
                raise P0ContractError(f"Saved/new frame facts disagree: {root.name}/{key}")
        minimum = labels["cluster"]["observed"]["minimum_separation_m"]
        if abs(minimum - report["minimum_separation_m"]) > 1e-9:
            raise P0ContractError("Saved minimum separation mismatch")
        independent = audit_geometry(model["scene"], run, frame, report, targets)
        if independent["status"] != "PASS":
            raise P0ContractError(f"Independent geometry audit failed: {independent}")
        rows.append({"episode": str(root), **independent, "default_input_whitelist": "PASS",
                     "id_aligned_input_permutation": "PASS"})
    return {"status": "PASS", "episodes": rows, "episode_count": len(rows),
            "facility_frame_comparisons": sum(r["facility_frame_comparisons"] for r in rows),
            "differences": sum(r["differences"] + r["target_differences"] for r in rows),
            "scope": "existing accepted slice only, not new role execution"}


def report_markdown(summary, registration, audit, cross, out):
    names = {"transit": "过境", "reconnaissance": "侦察", "monitoring": "游弋监视",
             "feint": "佯动", "penetration": "突防"}
    lines = ["# S2 通用基础设施运行报告", "",
             "本轮完成通用抽样、契约、几何审计及视图框架。角色航线和新增角色判据由项目方接入；没有新增实际 episode。",
             "", "## 选择与抽样", "",
             "地图按设施数各选两张，至少 6 架；优先选择已有直线路径被限制区阻挡的候选，不按速度或任务成功率筛选。",
             "", "| 候选序号 | 设施数 | 机数 | family 速度 m/s | 直线受阻 |",
             "|---|---:|---:|---:|---|"]
    for row in registration["selected"]:
        lines.append(f"| {row['candidate_index']} | {row['facility_count']} | {row['vehicle_count']} | {row['cruise_speed_m_s']:.6f} | {row['straight_blocked']} |")
    lines += ["", "公共候选对五种意图采用相同随机数，边际分布一致且有限批次逐项一致；这不是五组独立抽样。",
              "单位数先均匀抽 1–3，再按每单元至少两架截顶；首目标均匀抽取，后续以 0.5 概率相同，否则在其余设施中均匀抽取。",
              "同向/多向各 0.5；多向至少 90° 只登记为接口约束，本轮未验证实际航线方位。",
              "合并按目标与角色；执行方式和组间偏移沿用首个单元。所有参数与种子仅在私有描述中。",
              "", "| 意图 | 骨架候选数 | 同向 | 多向 | 单元数 1/2/3 | 合并后组数 1/2/3 |",
              "|---|---:|---:|---:|---|---|"]
    for intent, row in summary["distributions_by_intent"].items():
        units = "/".join(str(row["initial_unit_count"].get(str(i), 0)) for i in (1, 2, 3))
        groups = "/".join(str(row["merged_group_count"].get(str(i), 0)) for i in (1, 2, 3))
        lines.append(f"| {names[intent]} | {row['candidate_count']} | {row['approach_mode'].get('same_direction', 0)} | {row['approach_mode'].get('multi_direction', 0)} | {units} | {groups} |")
    lines += ["", "常规 60 个私有骨架描述对应 120 个时序请求；另有 6 个中止子集请求。中止只是私有指定，本轮未生成中止行为事实。",
              "66 个描述在 1/2 进程下 canonical JSON 逐字节一致。不同进程的计时字段不参与比较。",
              "", "## 几何和数据复核", ""]
    if audit["status"] == "PASS":
        lines.append(f"只读复核已通过竖切的 {audit['episode_count']} 个 episode：{audit['facility_frame_comparisons']:,} 个设施圈层比较，圈层与目标圈层差异总数 {audit['differences']}。")
        lines.append("生产检查调用唯一权威精确几何函数；独立审计使用原始轮廓 GEOS 距离和解析圆。旧保存标签、默认输入白名单及按 ID 列置换均通过。")
    else:
        lines.append("未提供已执行样例，本次几何全帧复核未运行。")
    lines += ["", "## 索引与待接入项目", "",
              "主对照按 family 内五类最少成功配对数平衡；合格的其余数据进入扩展索引；失败、中止分开列索引，不复制数据。",
              "当前 primary / extended / aborted / failed 为 0，pending 为 126。待接入不计为失败，也不计为成功。",
              "角色航线、实测时序、角色事实、运动学可行性、任务成败、实际多向跨度和新增任务图件均未运行，相关率为 null。",
              "新增截断测试验证通用回调只能看到已观测前缀；不代表缺失的角色判据已经通过半程截断验收。",
              "", "## 交叉否定完整组合", "",
              "A 的模板检查 B 的轨迹；B 的指定标签不传给回调。缺模板、判据或轨迹为 not_run，不能用 unknown 冒充已验证的否定。",
              "", "| 模板 A | 轨迹 B | 计划组合数 | 实测数 | 待接入 |", "|---|---|---:|---:|---:|"]
    for row in cross["combinations"]:
        lines.append(f"| {names[row['template_intent']]} | {names[row['trajectory_intent']]} | {row['planned']} | {row['tested']} | {row['pending']} |")
    lines += ["", "## 耗时", "",
              f"- 抽样（含两种进程数比较）：{summary['sampling_seconds_including_serial_comparison']:.3f} s。",
              f"- 旧样例几何和数据审计：{summary['existing_audit_seconds']:.3f} s。",
              f"- 本次入口全流程：{summary['total_wall_s']:.3f} s；不含测试、开发及本报告写入时间。",
              "- 新 episode 单条执行耗时与画图耗时：未运行。", "",
              f"输出目录：{out.resolve().as_posix()}", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-attempt", type=Path, required=True)
    parser.add_argument("--audit-existing", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if args.output_root.resolve() != DEFAULT_DATA.resolve():
        raise ValueError("Output must be in external SwarmData/v07_dataset")
    started = time.perf_counter()
    out = args.output_root / ("attempt_s2infra_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    print(f"OUTPUT {out}", flush=True)
    try:
        selected = select_maps(args.scene_attempt)
        save_json(out / "registration.json", {
            "scope": "S2 generic infrastructure only; role planners/evaluators supplied by owner",
            "facts_source": "exported 10 Hz grid", "workers": args.workers,
            "selection": "two each of 1/2/3 facilities, N>=6, obstruction enriched; no feasibility/speed filtering",
            "source_attempt": str(args.scene_attempt), "selected": [
                {"candidate_index": r["candidate"]["candidate_index"], "family_id": r["family"]["family_id"],
                 "facility_count": r["candidate"]["facility_count"], "vehicle_count": r["family"]["vehicle_count"],
                 "cruise_speed_m_s": r["family"]["cruise_speed_m_s"], "straight_blocked": r["straight_blocked"],
                 "source_sha256": r["source_sha256"]} for r in selected]})
        sampling_started = time.perf_counter()
        descriptors = prepare(selected, args.workers)
        serial = prepare(selected, 1)
        if canonical_json(descriptors) != canonical_json(serial):
            raise P0ContractError("Worker count changed sampling output")
        sampling_s = time.perf_counter() - sampling_started
        save_json(out / "private_skeleton_descriptors.json", descriptors)
        records = requests_for(descriptors)
        save_json(out / "episode_requests.json", records)
        views = make_views(records)
        save_json(out / "views.json", views)
        templates = [{"family_id": d["family_id"], "intent": d["base_intent"],
                      "template_id": d["skeleton_id"], "parameters": None}
                     for d in descriptors if d["subset"] == "regular"]
        subjects = [{"family_id": r["family_id"], "intent": r["intent"], "episode_id": r["episode_id"], "run": None}
                    for r in records if not r["aborted"]]
        cross = cross_negation(templates, subjects, {})
        save_json(out / "cross_negation.json", cross)
        save_json(out / "role_check_status.json", {
            "roles": [{"role": role, "route_planner": "not_implemented", "criterion": "not_implemented",
                       "half_work_truncation": "not_run"} for role in ROLES],
            "reconnaissance_methods": ["area_search", "close_observation"],
            "role_specific_new_fact_audit": "not_run; requires owner implementations and actual trajectories"})
        audit_started = time.perf_counter()
        audit = audit_existing(args.audit_existing)
        audit_s = time.perf_counter() - audit_started
        save_json(out / "existing_geometry_audit.json", audit)
        summary = diagnostic_summary(descriptors, records)
        summary.update({"status": "infrastructure_complete_role_execution_pending", "views": views["counts"],
                        "descriptor_count": len(descriptors), "generated_episode_count": 0,
                        "sampling_seconds_including_serial_comparison": sampling_s, "existing_audit_seconds": audit_s,
                        "total_wall_s": time.perf_counter() - started,
                        "process_count_reproducibility": {"status": "PASS", "workers": [1, args.workers],
                                                        "canonical_sha256": hashlib.sha256(canonical_json(descriptors)).hexdigest()},
                        "cross_negation": {"status": cross["status"], "ordered_intent_combinations": len(cross["combinations"]),
                                           "comparisons_pending": len(cross["rows"])}})
        save_json(out / "summary.json", summary)
        registration = read_json(out / "registration.json")
        with (out / "report.md").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(report_markdown(summary, registration, audit, cross, out))
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    except P0ContractError as exc:
        save_json(out / "P0_STOP.json", {"error": str(exc), "preserve_attempt": True})
        raise


if __name__ == "__main__":
    main()
