"""S1.5 first_edition pre-diagnosis (read-only).

D1 monitoring/timing conflict, D2 multi-direction area search, D3 downstream profile.

Reads existing attempts only. Does not modify task_v07/, configs/ or scene_v07/, does not add
instrumentation, and does not propose or implement any fix. A missing field is reported and the
affected item stops instead of being guessed.
"""
import argparse
import cProfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import pstats
import shutil
import sys
import tempfile
import time

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scene_v07.geometry import center_of
from scripts.run_v07_s2_expansion import DEFAULT_DATA, descriptor_jobs
from scripts.run_v07_s2_episode_batch import run_episode_job
from task_v07.expansion.solo_spacing import solo_interval_check
from task_v07.expansion.views import MODES
from task_v07.io import read_json, sha
from task_v07.unified.timing import episode_plan

OUT_DIR = PROJECT / "docs/v07/evidence/s15/diagnosis"
DESCRIPTOR_ATTEMPT = DEFAULT_DATA / "attempt_s15desc_20261016T154909Z"
YIELD_ATTEMPTS = (DEFAULT_DATA / "attempt_s15yield_20261016T154921Z",
                  DEFAULT_DATA / "attempt_s15yield_20261016T163901Z")
D1_CONFLICT = ("family_s15_79c93b22d09e8a7a_ext_002_regular", "family_s15_79c93b22d09e8a7a_ext_004_regular",
               "family_s15_aa4c66be8e85d64d_ext_002_regular")
D1_UNFINISHED = ("family_s15_1b876e6b8b6f70c6_ext_007_regular", "family_s15_38bedc9d791d547b_ext_007_regular",
                 "family_s15_c713f51898e81011_ext_002_regular")
D1_CONTROL = ("family_s15_1c267d4d7000043d_ext_005_regular",)
D3_TARGET = "family_s15_1c267d4d7000043d_ext_005_regular"
ROUND_FILES = ("skeleton.json", "planning_checks.json", "rehearsal.json", "timing_selection.json",
               "timing_calibration.json", "planning_rejection.json")
STRUCTURAL_MIN = 15
D3_WALL_LIMIT_S = 900


def distribution(values):
    values = sorted(value for value in values if value is not None)
    if not values:
        return {"count": 0, "min": None, "p50": None, "max": None}

    def quantile(p):
        index = (len(values) - 1) * p
        low = int(index)
        return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (index - low)

    return {"count": len(values), "min": round(values[0], 6), "p50": round(quantile(.5), 6),
            "max": round(values[-1], 6)}


def markdown_table(rows, columns, row_label=""):
    lines = ["| " + " | ".join([str(row_label or "-")] + [str(column) for column in columns]) + " |",
             "|" + "---|" * (len(columns) + 1)]
    for key, cells in rows:
        lines.append("| " + " | ".join([str(key)] + [str(cells.get(column, "")) for column in columns]) + " |")
    return "\n".join(lines)


def scene_map():
    registration = read_json(DESCRIPTOR_ATTEMPT / "registration.json")
    candidates = {row["candidate_index"]: row
                  for row in read_json(Path(registration["source_attempt"]) / "candidates.json")}
    return {row["family_id"]: read_json(Path(candidates[row["candidate_index"]]["directory"]) / "public_scene.json")
            for row in registration["selected"]}


def sim_attempts():
    found = sorted(path for path in DEFAULT_DATA.glob("attempt_s15sim_*") if path.is_dir())
    if len(found) < 2:
        raise SystemExit(f"Expected at least two attempt_s15sim_* directories, found {len(found)}")
    return found


def attempt_of(skeleton_id, attempts):
    for path in attempts:
        if (path / skeleton_id).exists():
            return path
    return None


def rounds_of(skeleton_root):
    return sorted(path for path in skeleton_root.iterdir()
                  if path.is_dir() and path.name.startswith("geometry_"))


def solo_trajectories(round_root, agents):
    solos = {}
    for agent in sorted(agents):
        path = round_root / f"single_agent_{agent}.npz"
        if not path.exists():
            return None
        with np.load(path, allow_pickle=False) as stored:
            solos[agent] = {key: stored[key].copy() for key in ("time_us", "p", "agent_ids")}
    return solos


def stage_of(tau, core, completion, last_frame):
    if tau < 0:
        return "起飞前等待"
    if tau < core:
        return "进场"
    if tau <= completion:
        return "作业"
    if tau <= last_frame:
        return "撤离"
    return "终点保持"


def d1(out_dir, scenes):
    attempts = sim_attempts()
    lines = ["# D1 监视/时刻冲突诊断", "", "数据源：", *[f"- `{path}`" for path in attempts], "",
             "## 字段原始定义（取自源码）", "",
             "- `core_times_s[a]`：`task_v07/unified/rehearsal.py::evaluate_solos` 取 "
             "`labels[\"agents\"][a][\"observed\"][\"core_event\"][\"t_s\"]`，即 M1 在该单机预演轨迹上测得的"
             "**单机核心事件时刻**（事件按角色取名：transit/monitoring → `enter_warning_zone`，"
             "area_search → `scan_start`，close_observation → `observation_point_arrival`，"
             "feint → `enter_alert_zone`，intrusion → `enter_protected_zone`）。",
             "- `completion_times_s[a]`：同一函数取 `run[\"time_us\"][-1] / 1e6`（`execution_status == "
             "\"completed\"` 时，否则 null），即**单机预演轨迹的末帧时间**。",
             "- 所以\"撤离\"区间 `completion_time < τ ≤ 末帧` 按定义宽度为 0，实际只可能出现前三个与"
             "\"终点保持\"，下文的分阶段计数会直接显示这一点。",
             "- `closest_pair.t_s` 与 `frame_index` 来自 "
             "`task_v07/expansion/solo_spacing.py::minimum_spacing`，网格 10 Hz、`times` 为**联合时钟**；"
             "本机时刻 `τ = t_s − departure_delays_s[a]`，`τ<0` 段 `np.interp` 取首帧位形（起飞前等待）。", ""]
    anomalies, conclusion, evidence = [], [], []
    for skeleton_id in D1_CONFLICT + D1_UNFINISHED + D1_CONTROL:
        attempt = attempt_of(skeleton_id, attempts)
        if attempt is None:
            anomalies.append(f"{skeleton_id}: 两个 attempt 下都没有该目录，D1 该项停止")
            lines += [f"## {skeleton_id}", "", "**缺目录：两个 attempt 下都没有该骨架，本骨架停止。**", ""]
            continue
        root = attempt / skeleton_id
        rounds = rounds_of(root)
        lines += [f"## {skeleton_id}", "", f"- attempt：`{attempt}`", f"- 轮数：{len(rounds)}", ""]
        if not rounds:
            anomalies.append(f"{skeleton_id}: 没有 geometry_XX 目录，本骨架停止")
            lines += ["**没有 geometry_XX 目录，本骨架停止。**", ""]
            continue
        rows, round_meta = [], []
        for round_root in rounds:
            rejection = round_root / "planning_rejection.json"
            category = read_json(rejection).get("category") if rejection.exists() else None
            calibration = round_root / "timing_calibration.json"
            candidate_index = None
            for name in ("timing_calibration.json", "planning_rejection.json", "candidate_search_progress.json"):
                path = round_root / name
                if path.exists() and read_json(path).get("candidate_index") is not None:
                    candidate_index = read_json(path)["candidate_index"]
                    break
            stamps = {name: (round_root / name).stat().st_mtime for name in ROUND_FILES
                      if (round_root / name).exists()}
            rehearsal_s = (stamps["rehearsal.json"] - stamps["planning_checks.json"]
                           if {"rehearsal.json", "planning_checks.json"} <= set(stamps) else None)
            timing_s = (stamps["timing_selection.json"] - stamps["rehearsal.json"]
                        if {"timing_selection.json", "rehearsal.json"} <= set(stamps) else None)
            rows.append((round_root.name, {"candidate_index": candidate_index,
                                           "rehearsal.json": (round_root / "rehearsal.json").exists(),
                                           "timing_selection.json": (round_root / "timing_selection.json").exists(),
                                           "category": category,
                                           "预演耗时(mtime估)": "—" if rehearsal_s is None else round(rehearsal_s, 3),
                                           "时刻耗时(mtime估)": "—" if timing_s is None else round(timing_s, 3)}))
            round_meta.append({"dir": round_root, "category": category, "candidate_index": candidate_index,
                               "rehearsal_s": rehearsal_s, "timing_s": timing_s})
        lines += [markdown_table(rows, ["candidate_index", "rehearsal.json", "timing_selection.json", "category",
                                        "预演耗时(mtime估)", "时刻耗时(mtime估)"], row_label="轮"), "",
                  "> 预演耗时 = mtime(rehearsal.json) − mtime(planning_checks.json)；时刻耗时 = "
                  "mtime(timing_selection.json) − mtime(rehearsal.json)。这是 **mtime 估计**，不是被测代码的埋点。", ""]
        if skeleton_id in D1_UNFINISHED:
            last = rounds[-1]
            present = [name for name in ROUND_FILES if (last / name).exists()]
            absent = [name for name in ROUND_FILES if not (last / name).exists()]
            lines += [f"- **未跑完**：停在 `{last.name}`。该轮已写出 {present}，缺 {absent}。", ""]
        if skeleton_id in D1_CONTROL:
            lines += ["- 对照组（严格配对成功），不进入被拒 draw 的分阶段统计。", ""]
            continue
        conflict_rows = []
        pair_round = {}
        for meta in round_meta:
            round_root = meta["dir"]
            selection_file = round_root / "timing_selection.json"
            if not selection_file.exists():
                continue
            selection = read_json(selection_file)
            # A round cut off before planning_rejection.json still records its rejected timing.
            if meta["category"] != "timing_conflict" and selection.get("status") != "rejected":
                continue
            need = ("rehearsal.json", "skeleton.json")
            if not all((round_root / name).exists() for name in need):
                anomalies.append(f"{skeleton_id}/{round_root.name}: 缺 {need}，跳过该轮")
                continue
            rehearsal = read_json(round_root / "rehearsal.json")
            skeleton = read_json(round_root / "skeleton.json")
            core, completion = rehearsal["core_times_s"], rehearsal["completion_times_s"]
            solos = solo_trajectories(round_root, skeleton["agent_ids"])
            if solos is None:
                anomalies.append(f"{skeleton_id}/{round_root.name}: 缺 single_agent_*.npz，跳过该轮")
                continue
            last_frame = {agent: float(run["time_us"][-1]) / 1e6 for agent, run in solos.items()}
            groups = {agent: group["group_id"] for group in skeleton["group_skeletons"].values()
                      for agent in group["members"]}
            targets = {gid: group["target_id"] for gid, group in skeleton["group_skeletons"].items()}
            scene = scenes[skeleton["family_id"]]
            centres = {entity["id"]: center_of(entity["geometry"])
                       for entity in scene["entities"] if entity["type"] == "facility"}
            for mode in MODES:
                version = (selection.get("versions") or {}).get(mode)
                if version is None:
                    anomalies.append(f"{skeleton_id}/{round_root.name}/{mode}: timing_selection 缺该版本")
                    continue
                for attempt_row in version["attempts"]:
                    draw = attempt_row["draw"]
                    plan = episode_plan(skeleton, core, mode, draw)
                    overlay = solo_interval_check(solos, {mode: plan})[mode]
                    if (abs(overlay["minimum_m"] - attempt_row["minimum_m"]) > 1e-12
                            or overlay["closest_pair"] != attempt_row["closest_pair"]
                            or abs(overlay["predicted_end_s"] - attempt_row["predicted_end_s"]) > 1e-9):
                        raise SystemExit(f"P0: {skeleton_id}/{round_root.name}/{mode}/draw{draw} "
                                         "episode_plan + solo_interval_check 复算与 timing_selection 不一致")
                    agents = list(attempt_row["closest_pair"]["agents"])
                    t_s = attempt_row["closest_pair"]["t_s"]
                    delays = plan["departure_delays_s"]
                    tau = {agent: round(t_s - delays[agent], 6) for agent in agents}
                    stages = {agent: stage_of(tau[agent], core[agent], completion[agent], last_frame[agent])
                              for agent in agents}
                    point = []
                    for agent in agents:
                        local = round(t_s * 1e6) - round(delays[agent] * 1e6)
                        point.append([float(np.interp(local, solos[agent]["time_us"], solos[agent]["p"][:, 0, axis]))
                                      for axis in range(3)])
                    midpoint = np.mean(point, axis=0)
                    link = {agent: math.dist(midpoint[:2], centres[targets[groups[agent]]])
                            for agent in agents}
                    conflict_rows.append({"round": round_root.name, "mode": mode, "draw": draw,
                                          "agents": tuple(agents), "stages": tuple(stages[a] for a in agents),
                                          "tau": tau, "stage": stages, "minimum_m": attempt_row["minimum_m"],
                                          "t_s": t_s, "same_group": groups[agents[0]] == groups[agents[1]],
                                          "target_distance": link, "core": core, "completion": completion,
                                          "last_frame": last_frame})
                    pair_round.setdefault(tuple(agents), round_root)
        if not conflict_rows:
            lines += ["- 该骨架没有 timing_conflict 轮的行可分析。", ""]
            anomalies.append(f"{skeleton_id}: 没有可分析的 timing_conflict 行")
            continue
        evidence.append({"skeleton": skeleton_id, "rows": len(conflict_rows),
                         "stage_histogram": dict(Counter("+".join(row["stages"]) for row in conflict_rows)),
                         "tau_sample": conflict_rows[0]["tau"]})
        lines += ["### 每次被拒 draw 的机对与阶段", "",
                  "| 轮 | mode | draw | 机对 | minimum_m | t_s | τ（本机） | 阶段 | 同组 | 到各自组目标中心 m |",
                  "|---|---|---:|---|---:|---:|---|---|---|---|"]
        for row in conflict_rows:
            tau_text = "；".join(f"{a}={row['tau'][a]:.1f}" for a in row["agents"])
            stage_text = "/".join(row["stages"])
            target_text = "；".join(f"{a}={row['target_distance'][a]:.1f}" for a in row["agents"])
            lines.append(f"| {row['round']} | {row['mode']} | {row['draw']} | {'+'.join(row['agents'])} | "
                         f"{row['minimum_m']:.6f} | {row['t_s']:.1f} | {tau_text} | {stage_text} | "
                         f"{row['same_group']} | {target_text} |")
        lines += ["", "> 阶段判定：τ<0 起飞前等待；0≤τ<core_time 进场；core_time≤τ≤completion_time 作业；"
                  "completion_time<τ≤末帧 撤离；τ>末帧 终点保持。core/completion 取自 `rehearsal.json`。"
                  "冲突点取两机在 t_s 处位移后位置的**中点**，距离按场景平面（ENU 的 x、y）计算。", ""]
        by_round_mode = defaultdict(list)
        for row in conflict_rows:
            by_round_mode[(row["round"], row["mode"])].append(row)
        lines += ["### 每轮 × 每 mode 的主导组合", "",
                  "| 轮 | mode | draw 数 | 主导（机对 → 阶段组合） | 次数 | 判定 |", "|---|---|---:|---|---:|---|"]
        for (round_name, mode), group in sorted(by_round_mode.items()):
            counter = Counter((row["agents"], row["stages"]) for row in group)
            combo, count = counter.most_common(1)[0]
            verdict = "结构性（与时刻无关）" if count >= STRUCTURAL_MIN else "分散"
            lines.append(f"| {round_name} | {mode} | {len(group)} | {'+'.join(combo[0])} → "
                         f"{'+'.join(combo[1])} | {count}/{len(group)} | {verdict} |")
            conclusion.append({"skeleton": skeleton_id, "round": round_name, "mode": mode,
                               "agents": "+".join(combo[0]), "stages": "+".join(combo[1]),
                               "count": count, "of": len(group), "structural": count >= STRUCTURAL_MIN,
                               "same_group": all(row["same_group"] for row in group
                                                 if row["agents"] == combo[0])})
        lines += ["", f"> 判定规则：同一机对 + 同一阶段组合在 20 次 draw 中出现 ≥{STRUCTURAL_MIN} 次记为结构性。", ""]
        lines += ["### 冲突机对的空间量（不含时间）", "",
                  "| 轮 | 机对 | 两轨迹空间最近距离 m | 起点间距 m | 终点间距 m | 同组 |", "|---|---|---:|---:|---:|---|"]
        for pair, round_root in sorted(pair_round.items()):
            solos = solo_trajectories(round_root, pair)
            if solos is None:
                anomalies.append(f"{skeleton_id}/{round_root.name}: 机对 {pair} 缺 npz")
                continue
            first = solos[pair[0]]["p"][:, 0, :2][::5]
            second = solos[pair[1]]["p"][:, 0, :2][::5]
            best = math.inf
            for index in range(0, len(first), 256):
                block = first[index:index + 256]
                best = min(best, float(np.linalg.norm(block[:, None, :] - second[None, :, :], axis=2).min()))
            start_gap = math.dist(solos[pair[0]]["p"][0, 0, :2], solos[pair[1]]["p"][0, 0, :2])
            end_gap = math.dist(solos[pair[0]]["p"][-1, 0, :2], solos[pair[1]]["p"][-1, 0, :2])
            skeleton = read_json(round_root / "skeleton.json")
            groups = {agent: group["group_id"] for group in skeleton["group_skeletons"].values()
                      for agent in group["members"]}
            lines.append(f"| {round_root.name} | {pair[0]}+{pair[1]} | {best:.6f} | {start_gap:.3f} | "
                         f"{end_gap:.3f} | {groups[pair[0]] == groups[pair[1]]} |")
        lines += ["", "> 三条量均按 10 Hz 帧、两轨迹各取 5 帧降采样后在降采样点集上取最小值。", ""]
    lines += ["## 结论表", "",
              "| 骨架 | 轮 | mode | 主导机对 | 主导阶段组合 | 同组/跨组 | 结构性/分散 |", "|---|---|---|---|---|---|---|"]
    for item in conclusion:
        lines.append(f"| {item['skeleton']} | {item['round']} | {item['mode']} | {item['agents']} | "
                     f"{item['stages']} | {'同组' if item['same_group'] else '跨组'} | "
                     f"{'结构性' if item['structural'] else '分散'} |")
    lines += ["", "**3 个未跑完的骨架均为 monitoring。**", ""]
    (out_dir / "d1_monitoring_timing.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return anomalies, conclusion, evidence


def _summarizer():
    spec = importlib.util.spec_from_file_location(
        "s15_yield_summary", PROJECT / "scripts" / "summarize_v07_s15_yield.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def key_paths(node, path="", counter=None):
    """Every key path under a rejection subtree, with its occurrence count."""
    counter = counter if counter is not None else Counter()
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            counter[here] += 1
            key_paths(value, here, counter)
    elif isinstance(node, list):
        for item in node:
            key_paths(item, f"{path}[]", counter)
    return counter


def d2(out_dir):
    module = _summarizer()
    registration = read_json(DESCRIPTOR_ATTEMPT / "registration.json")
    descriptors = {record["skeleton_id"]: record
                   for record in read_json(DESCRIPTOR_ATTEMPT / "private_skeleton_descriptors.json")}
    candidates = {row["candidate_index"]: row
                  for row in read_json(Path(registration["source_attempt"]) / "candidates.json")}
    rows_of = {}
    for attempt in YIELD_ATTEMPTS:
        if not attempt.exists():
            continue
        for skeleton_id in registration["skeleton_ids"]:
            # Only the attempt that completed the skeleton owns its proposals.jsonl: a batch that
            # hit its wall-clock cap leaves a truncated journal behind.
            if skeleton_id in rows_of or not (attempt / skeleton_id / "planning_result.json").exists():
                continue
            journal = attempt / skeleton_id / "proposals.jsonl"
            if journal.exists():
                rows_of[skeleton_id] = read_json_lines(journal)
    anomalies = []
    by_mode = defaultdict(lambda: {"proposals": 0, "accepted": 0, "reasons": Counter(), "categories": Counter(),
                                   "target_facility": [], "clearances": [], "required": []})
    missing = []
    for skeleton_id in registration["skeleton_ids"]:
        descriptor = descriptors[skeleton_id]
        groups = {group["group_id"]: group for group in descriptor["task_groups"]}
        if not any(group["role"] == "reconnaissance" and group["execution_method"] == "area_search"
                   for group in groups.values()):
            continue
        if skeleton_id not in rows_of:
            missing.append(skeleton_id)
            continue
        selected_row = next(row for row in registration["selected"]
                            if row["family_id"] == descriptor["family_id"])
        directory = Path(candidates[selected_row["candidate_index"]]["directory"])
        placements = {row["obstacle_id"]: row["placement"]
                      for row in read_json(directory / "family_initial.json")["obstacle_placements"]}
        mode = descriptor["common_draw"]["approach_mode"]
        bucket = by_mode[mode]
        for record in rows_of[skeleton_id]:
            group = groups.get(record["group_id"])
            if group is None or group["role"] != "reconnaissance" or group["execution_method"] != "area_search":
                continue
            bucket["proposals"] += 1
            if record["reason"] is None:
                bucket["accepted"] += 1
                continue
            bucket["reasons"][record["reason"]] += 1
            entities = set()
            module.collect_entities(record["rejection"], entities)
            categories = ({module.classify(entity, group["target_id"], placements, anomalies) for entity in entities}
                          if entities else {f"unattributed:{record['reason']}"})
            for category in categories:
                bucket["categories"][category] += 1
            if "target_facility" in categories:
                bucket["target_facility"].append({**record, "_target_id": group["target_id"]})
                collect_clearance(record["rejection"], bucket["clearances"], bucket["required"])
    lines = ["# D2 多向区域搜索（role=reconnaissance, execution_method=area_search）", "",
             "数据源：", *[f"- `{path}`" for path in YIELD_ATTEMPTS if path.exists()],
             f"- 描述目录：`{DESCRIPTOR_ATTEMPT}`", ""]
    if missing:
        anomalies.append(f"D2: {len(missing)} 个含 area_search 的骨架没有 proposals.jsonl：{missing}")
        lines += [f"> 缺 proposals.jsonl 的骨架 {len(missing)} 个，已跳过并如实列出。", ""]
    columns = sorted(by_mode)
    lines += ["## 提案接受率与 reason/归因计数", "",
              markdown_table([(label, {mode: (f"{by_mode[mode]['accepted']}/{by_mode[mode]['proposals']}"
                                             if by_mode[mode]["proposals"] else "0/0")
                                      for mode in columns})
                              for label in ("接受/提案",)],
                             columns, row_label="指标"), ""]
    for mode in columns:
        bucket = by_mode[mode]
        lines += [f"### approach_mode = {mode}", "",
                  f"- 提案 {bucket['proposals']} 条，接受 {bucket['accepted']} 条，"
                  f"接受率 {(bucket['accepted'] / bucket['proposals']) if bucket['proposals'] else 0:.4f}", "",
                  "reason 字面值计数：", "",
                  markdown_table([(key, {"count": value}) for key, value in sorted(bucket["reasons"].items())],
                                 ["count"], row_label="reason"), "",
                  "归因类别计数（多标签，复用 summarize_v07_s15_yield.py 的 collect_entities/classify）：", "",
                  markdown_table([(key, {"count": value}) for key, value in sorted(bucket["categories"].items())],
                                 ["count"], row_label="类别"), ""]
        rows = bucket["target_facility"]
        lines += [f"### target_facility 归因的提案（{len(rows)} 条）", ""]
        if not rows:
            lines += ["- 该 approach_mode 没有 target_facility 归因的被拒提案。", ""]
            continue
        paths = Counter()
        layers = Counter()
        target_id = rows[0]["_target_id"]
        for record in rows:
            key_paths(record["rejection"], counter=paths)
            for entity in sorted(set(_iter_entity_ids(record["rejection"]))):
                # Only the group's own target and its layers, matching the target_facility rule.
                if entity != target_id and not entity.startswith(target_id + "_"):
                    continue
                layers["base（设施基底）" if entity == target_id else entity[len(target_id) + 1:]] += 1
        lines += ["出现最多的前 20 条键路径：", "",
                  markdown_table([(key, {"count": value}) for key, value in paths.most_common(20)],
                                 ["count"], row_label="键路径"), "",
                  "侵入的目标圈层（按实体 ID 后缀）：", "",
                  markdown_table([(key, {"count": value}) for key, value in sorted(layers.items())],
                                 ["count"], row_label="圈层"), "",
                  f"- `clearances_m` 数值分布：{json.dumps(distribution(bucket['clearances']), ensure_ascii=False)}",
                  f"- `required_m` 数值分布：{json.dumps(distribution(bucket['required']), ensure_ascii=False)}", ""]
    lines += ["> 本节只记录分布与圈层归属，不推测原因。area_search 的证据条目实际是标量 "
              "`clearance_m` + `required_m`；另有 `clearances_m` 字典形式出现在别处，两种形态都收集。"
              "任务书写作 clearance_m，与实际字段一致。", ""]
    (out_dir / "d2_area_search.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return anomalies


def _iter_entity_ids(node):
    if isinstance(node, dict):
        value = node.get("entity_id")
        if isinstance(value, str):
            yield value
        for child in node.values():
            yield from _iter_entity_ids(child)
    elif isinstance(node, list):
        for child in node:
            yield from _iter_entity_ids(child)


def collect_clearance(node, clearances, required):
    """Both evidence shapes: a scalar clearance_m/required_m pair, and the clearances_m dict form."""
    if isinstance(node, dict):
        need = node.get("required_m")
        scalar = node.get("clearance_m")
        values = node.get("clearances_m")
        if isinstance(need, (int, float)) and not isinstance(need, bool):
            if isinstance(scalar, (int, float)) and not isinstance(scalar, bool):
                clearances.append(float(scalar))
                required.append(float(need))
            elif isinstance(values, dict):
                required.append(float(need))
                for value in values.values():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        clearances.append(float(value))
        for child in node.values():
            collect_clearance(child, clearances, required)
    elif isinstance(node, list):
        for child in node:
            collect_clearance(child, clearances, required)


def read_json_lines(path):
    records = []
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                records.append(json.loads(line))
    return records


def top_functions(stats, limit):
    rows = []
    for (filename, lineno, name), (cc, nc, tt, ct, _) in stats.stats.items():
        rows.append((name, filename, lineno, nc, tt, ct))
    rows.sort(key=lambda row: -row[5])
    return rows[:limit]


def cumulative_of(stats, name):
    hits = []
    for (filename, lineno, func), (cc, nc, tt, ct, _) in stats.stats.items():
        if func == name:
            hits.append({"file": os.path.basename(filename), "line": lineno,
                         "ncalls": nc, "tottime_s": round(tt, 3), "cumtime_s": round(ct, 3)})
    return sorted(hits, key=lambda item: -item["cumtime_s"])


def d3(out_dir):
    started = time.monotonic()
    temporary = Path(tempfile.mkdtemp(prefix="s15_d3_"))
    anomalies = []
    try:
        jobs = descriptor_jobs(DESCRIPTOR_ATTEMPT, [D3_TARGET], temporary)
        if len(jobs) != 1:
            raise SystemExit(f"expected one job for {D3_TARGET}, got {len(jobs)}")
        profiler = cProfile.Profile()
        profiler.enable()
        rows = run_episode_job(jobs[0])
        profiler.disable()
        stats = pstats.Stats(profiler, stream=io.StringIO())
        stats.strip_dirs().sort_stats("cumulative")
        elapsed = time.monotonic() - started
        lines = ["# D3 下游耗时剖析（cProfile）", "",
                 f"- 对象：`{D3_TARGET}`（试点中 setup 约 64 s、仿真约 92 s）",
                 f"- 方式：对 `scripts/run_v07_s2_episode_batch.py::run_episode_job` 跑一次 cProfile",
                 f"- 输出目录：临时目录 `{temporary}`，跑完删除",
                 f"- 观测墙钟：{elapsed:.1f} s（上限 {D3_WALL_LIMIT_S} s）",
                 f"- 结果：{len(rows)} 行 episode 记录，状态 "
                 f"{[row.get('state') for row in rows]}", ""]
        if elapsed > D3_WALL_LIMIT_S:
            anomalies.append(f"D3: 超过 {D3_WALL_LIMIT_S} s 上限（{elapsed:.1f} s）")
            lines += [f"> **超过 {D3_WALL_LIMIT_S} s 上限，按任务书停止。**", ""]
        lines += ["## cumtime 前 40 项", "", "| # | 函数 | 文件:行 | ncalls | tottime s | cumtime s |",
                  "|---:|---|---|---:|---:|---:|"]
        for index, (name, filename, lineno, ncalls, tottime, cumtime) in enumerate(
                top_functions(stats, 40), start=1):
            lines.append(f"| {index} | {name} | {os.path.basename(filename)}:{lineno} | {ncalls} | "
                         f"{tottime:.3f} | {cumtime:.3f} |")
        lines += ["", "## 指定函数的累计时间", "",
                  markdown_table([(name, {"累计": "；".join(f"{hit['file']}:{hit['line']}={hit['cumtime_s']:.3f} s"
                                                          f"（ncalls {hit['ncalls']}）" for hit in cumulative_of(stats, name))
                                           or "未出现在 profile 中"})
                                  for name in ("rehearse", "select_timing", "solo_interval_check", "execute")],
                                 ["累计"], row_label="函数"), ""]
        (out_dir / "d3_profile.txt").write_text("\n".join(lines), encoding="utf-8", newline="\n")
        return anomalies
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("d1", "d2", "d3"), action="append",
                        help="Run only the listed items; default is all three")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    items = args.only or ["d1", "d2", "d3"]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    scenes = scene_map()
    summary = {"generated_utc": datetime.now(timezone.utc).isoformat(),
               "descriptor_attempt": str(DESCRIPTOR_ATTEMPT),
               "descriptor_attempt_sha256": sha(DESCRIPTOR_ATTEMPT / "private_skeleton_descriptors.json"),
               "items": {}}
    if "d1" in items:
        anomalies, conclusion, evidence = d1(args.out_dir, scenes)
        summary["items"]["d1"] = {"anomalies": anomalies, "conclusion": conclusion, "evidence": evidence}
        print(json.dumps({"d1": {"rows": len(conclusion), "anomalies": len(anomalies)}}, ensure_ascii=False))
    if "d2" in items:
        anomalies = d2(args.out_dir)
        summary["items"]["d2"] = {"anomalies": anomalies}
        print(json.dumps({"d2": {"anomalies": len(anomalies)}}, ensure_ascii=False))
    if "d3" in items:
        anomalies = d3(args.out_dir)
        summary["items"]["d3"] = {"anomalies": anomalies}
        print(json.dumps({"d3": {"anomalies": len(anomalies)}}, ensure_ascii=False))
    (args.out_dir / "diagnosis_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    raise SystemExit(main())
