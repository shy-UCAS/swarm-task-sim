"""FE-INT pre-freeze data quality check over the v0.7 s15 simulation attempt.

Read-only: reads truth_10hz.npz, metrics.json, labels.json and task.json under each
<skeleton>/<mode>/ directory and writes qc_report.md / qc_report.json. It does not import or
touch the planner, the simulator, configs, tests or any task_v07 source; it only calls
task_v07.criteria.load_criteria() to read the frozen dwell detector values verbatim.
"""
import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from task_v07.criteria import load_criteria

DEFAULT_DATASET = Path(
    "F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/"
    "attempt_s15sim_20261017T071447Z")
DEFAULT_OUT = PROJECT / "docs/v07/evidence/fe_int/quality_check"
MODES = ("synchronous", "sequential")
INTENTS = ("transit", "reconnaissance", "monitoring", "feint", "penetration")
EPS = 1e-6


class QCError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise QCError(message)


def read_json(path):
    require(path.exists(), f"missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quantile(values, p):
    """Linear interpolation on a 0-based index, same rule as summarize_v07_s15_sim_pilot.py."""
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    index = (len(values) - 1) * p
    low = int(index)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (index - low)


def fmt(value, digits=6):
    return "NA" if value is None else f"{value:.{digits}f}"


def ratio(numerator, denominator):
    if not denominator:
        return "0/0 (NA)"
    return f"{numerator}/{denominator} ({100.0 * numerator / denominator:.2f}%)"


def member_roles(task):
    """agent_id -> (role, execution_method) from the task group that contains the agent."""
    mapping = {}
    for group_id, group in task["group_skeletons"].items():
        key = (group["role"], group["execution_method"])
        for agent in group["members"]:
            require(agent in task["references"], f"member {agent} of {group_id} has no reference")
            require(agent not in mapping, f"member {agent} appears in more than one group")
            mapping[agent] = key
    require(set(mapping) == set(task["agent_ids"]),
            "group members do not cover task.json agent_ids")
    return mapping


def episode_rows(dataset):
    require(dataset.is_dir(), f"dataset root not found: {dataset}")
    skeletons = sorted(p for p in dataset.iterdir() if p.is_dir() and p.name.startswith("family_"))
    require(skeletons, f"no family_* skeleton directories under {dataset}")
    rows = []
    for skeleton in skeletons:
        for mode in MODES:
            episode = skeleton / mode
            require(episode.is_dir(), f"missing episode directory: {episode}")
            for name in ("truth_10hz.npz", "metrics.json", "labels.json", "task.json"):
                require((episode / name).exists(), f"missing file: {episode / name}")
            rows.append({"skeleton_id": skeleton.name, "mode": mode, "dir": episode})
    return skeletons, rows


def check_integrity(skeletons, rows):
    """Structural checks whose failures stop the run; counts are reported with denominators."""
    counts = Counter(row["mode"] for row in rows)
    checks = {
        "skeletons": len(skeletons),
        "episodes": len(rows),
        "episodes_by_mode": {mode: counts.get(mode, 0) for mode in MODES},
        "skeletons_with_both_modes": sum(
            1 for skeleton in skeletons
            if all((skeleton / mode).is_dir() for mode in MODES)),
        "agent_count_mismatches": [],
        "npz_id_order_mismatches": [],
        "labels_agent_mismatches": [],
        "scene_digest_mismatches": [],
    }
    for row in rows:
        episode = row["dir"]
        task = read_json(episode / "task.json")
        metrics = read_json(episode / "metrics.json")
        labels = read_json(episode / "labels.json")
        truth = np.load(episode / "truth_10hz.npz", allow_pickle=False)
        label = f"{row['skeleton_id']}/{row['mode']}"
        if truth["p"].shape[1] != len(task["agent_ids"]):
            checks["agent_count_mismatches"].append(label)
        if list(truth["agent_ids"]) != list(task["agent_ids"]):
            checks["npz_id_order_mismatches"].append(label)
        if set((labels.get("agents") or {})) != set(task["agent_ids"]):
            checks["labels_agent_mismatches"].append(label)
        if metrics.get("skeleton_id") != row["skeleton_id"] or metrics.get("mode") != row["mode"]:
            checks["scene_digest_mismatches"].append(label)
    return checks


def dwell_blocker(criteria, rows):
    """Q1 needs two thresholds named explicitly in detectors.dwell; report instead of choosing."""
    dwell = criteria["detectors"]["dwell"]
    keys = list(dwell)
    velocity_keys = [key for key in keys
                     if "speed" in key.lower() or "velocity" in key.lower()]
    duration_keys = [key for key in keys
                     if "duration" in key.lower() or "hold" in key.lower()]
    blocker = {
        "status": "blocked",
        "criteria_source": 'task_v07.criteria.load_criteria()["detectors"]["dwell"]',
        "dwell_config": dwell,
        "dwell_keys": keys,
        "velocity_threshold_key": velocity_keys[0] if len(velocity_keys) == 1 else None,
        "velocity_threshold_candidates": velocity_keys,
        "duration_threshold_key": duration_keys[0] if len(duration_keys) == 1 else None,
        "duration_threshold_candidates": duration_keys,
        "reason": "detectors.dwell 中无明确的速度阈值字段，也无最短持续时间字段；"
                  "未选取任何数值",
    }

    # Target geometry must come from task.json by instruction; record its absence there without
    # substituting another file.
    geometry = {"status": "not_found_in_task_json", "checked_field": "center_m / vertices_m",
                "groups": []}
    for row in rows:
        task = read_json(row["dir"] / "task.json")
        for group_id, group in task["group_skeletons"].items():
            target_id = group.get("target_id")
            found = None
            for key in ("geometry", "target_geometry", "facility_geometry"):
                value = group.get(key)
                if isinstance(value, dict) and ("center_m" in value or "vertices_m" in value):
                    found = value
                    break
            geometry["groups"].append({
                "skeleton_id": row["skeleton_id"], "mode": row["mode"],
                "group_id": group_id, "target_id": target_id,
                "geometry_found": found is not None})
    geometry["groups_with_geometry"] = sum(1 for g in geometry["groups"] if g["geometry_found"])
    geometry["groups_checked"] = len(geometry["groups"])
    blocker["target_geometry"] = geometry
    blocker["computed"] = False
    blocker["table"] = None

    # The task files carry stop_speed_m_s / stop_hold_s, but they are not the criteria source the
    # task names; record them as unused so the absence is auditable rather than implicit.
    unused = []
    for key in ("stop_speed_m_s", "stop_hold_s"):
        values = sorted({read_json(row["dir"] / "task.json").get(key) for row in rows},
                        key=lambda value: (value is None, value))
        unused.append({"key": key, "values_across_60_episodes": values,
                       "source": "task.json (not criteria detectors.dwell)",
                       "used_for_q1": False})
    blocker["unused_task_fields"] = unused
    return blocker


def m1_dwell(rows, roles_by_episode):
    """M1 dwell detection from labels.json, same field path as summarize_v07_s15_sim_pilot.py."""
    by_role = defaultdict(lambda: {"members": 0, "detected": 0, "not_detected": 0})
    missing = []
    for row in rows:
        labels = read_json(row["dir"] / "labels.json")
        for agent, (role, method) in roles_by_episode[(row["skeleton_id"], row["mode"])].items():
            observed = (labels.get("agents", {}).get(agent) or {}).get("observed") or {}
            contribution = observed.get("contribution") or {}
            dwell = contribution.get("dwell")
            if not isinstance(dwell, dict) or "detected" not in dwell:
                missing.append({"skeleton_id": row["skeleton_id"], "mode": row["mode"],
                                "agent_id": agent})
                continue
            key = f"{role} / {method}"
            by_role[key]["members"] += 1
            if bool(dwell["detected"]):
                by_role[key]["detected"] += 1
            else:
                by_role[key]["not_detected"] += 1
    return {
        "field_path": "labels.json -> agents[agent_id] -> observed -> contribution -> dwell -> "
                      "detected",
        "reference": "scripts/summarize_v07_s15_sim_pilot.py:label_facts()",
        "status": "partial: M1 column only; the Q1 column is blocked",
        "by_role": [{"role_execution_method": key, **value}
                    for key, value in sorted(by_role.items())],
        "missing_fields": missing,
    }


def q2_routes(skeletons):
    """Heading turn per internal vertex; task.json is byte-identical across modes for every
    skeleton in this attempt, so routes are counted once per skeleton member."""
    per_member = []
    cross_mode_identical = 0
    for skeleton in skeletons:
        task_path = skeleton / MODES[0] / "task.json"
        other_path = skeleton / MODES[1] / "task.json"
        task = read_json(task_path)
        if task_path.read_bytes() == other_path.read_bytes():
            cross_mode_identical += 1
        else:
            raise QCError(
                f"task.json differs between modes for {skeleton.name}; Q2 dedup would be invalid")
        roles = member_roles(task)
        for agent in task["agent_ids"]:
            points = np.asarray(task["references"][agent]["points_enu_m"], dtype=float)
            require(points.ndim == 2 and points.shape[1] >= 2,
                    f"points_enu_m has bad shape for {skeleton.name}/{agent}")
            xy = points[:, :2]
            segments = np.diff(xy, axis=0)
            lengths = np.linalg.norm(segments, axis=1)
            angles = []
            for index in range(1, len(xy) - 1):
                if lengths[index - 1] < EPS or lengths[index] < EPS:
                    continue
                u = segments[index - 1] / lengths[index - 1]
                w = segments[index] / lengths[index]
                cosine = float(np.clip(np.dot(u, w), -1.0, 1.0))
                angles.append(math.degrees(math.acos(cosine)))
            role, method = roles[agent]
            per_member.append({
                "skeleton_id": skeleton.name, "agent_id": agent,
                "role": role, "execution_method": method,
                "internal_vertices": int(len(xy) - 2),
                "valid_vertices": len(angles),
                "max_turn_deg": max(angles) if angles else None,
            })
    grouped = defaultdict(list)
    for item in per_member:
        grouped[f"{item['role']} / {item['execution_method']}"].append(item)
    table = []
    for key in sorted(grouped):
        items = grouped[key]
        values = [item["max_turn_deg"] for item in items if item["max_turn_deg"] is not None]
        table.append({
            "role_execution_method": key,
            "members": len(items),
            "members_with_valid_vertices": len(values),
            "max_turn_min": quantile(values, 0.0),
            "max_turn_p50": quantile(values, 0.5),
            "max_turn_max": quantile(values, 1.0),
            "ge_90": sum(1 for value in values if value >= 90.0),
            "ge_90_ratio": (sum(1 for value in values if value >= 90.0) / len(values))
            if values else None,
            "ge_150": sum(1 for value in values if value >= 150.0),
            "ge_150_ratio": (sum(1 for value in values if value >= 150.0) / len(values))
            if values else None,
        })
    return {
        "status": "ok",
        "method": {
            "source": "task.json references[agent_id].points_enu_m 的前两维",
            "turn_degrees": "每个内部顶点 θ = arccos(clip(u·w, −1, 1))，单位度",
            "zero_length_segments": "长度 < 1e-6 m 的段跳过",
            "aggregation": "每成员取最大转角，再跨成员取 min/p50/max",
            "deduplication": f"{cross_mode_identical}/{len(skeletons)} 骨架的 task.json 在 "
                             "synchronous 与 sequential 间逐字节一致；按骨架去重，"
                             "每个骨架成员计一次",
            "p50": "线性插值分位（0 基索引）",
        },
        "members_total": len(per_member),
        "members_total_if_counted_per_episode": len(per_member) * len(MODES),
        "members_without_valid_vertices": sum(
            1 for item in per_member if item["max_turn_deg"] is None),
        "table": table,
        "per_member": per_member,
    }


def recompute_min_separation(episode):
    truth = np.load(episode / "truth_10hz.npz", allow_pickle=False)
    positions = truth["p"]
    times = truth["time_us"]
    agent_ids = truth["agent_ids"]
    best = None
    count = positions.shape[1]
    for first in range(count):
        for second in range(first + 1, count):
            distances = np.linalg.norm(positions[:, first, :] - positions[:, second, :], axis=1)
            index = int(np.argmin(distances))
            if best is None or distances[index] < best["value_m"]:
                best = {
                    "value_m": float(distances[index]),
                    "agent_a": str(agent_ids[first]),
                    "agent_b": str(agent_ids[second]),
                    "frame_index": index,
                    "time_s": float(times[index]) / 1e6,
                }
    return best


def q3_separation(rows):
    grouped = defaultdict(list)
    all_rows = []
    for row in rows:
        metrics = read_json(row["dir"] / "metrics.json")
        value = metrics.get("minimum_separation_m")
        require(value is not None, f"metrics.json has no minimum_separation_m: {row['dir']}")
        record = {
            "skeleton_id": row["skeleton_id"],
            "mode": row["mode"],
            "intent": metrics.get("intent"),
            "minimum_separation_m": float(value),
        }
        grouped[(record["intent"], record["mode"])].append(record)
        all_rows.append(record)
    table = []
    for intent in INTENTS:
        for mode in MODES:
            values = [r["minimum_separation_m"] for r in grouped.get((intent, mode), [])]
            table.append({
                "intent": intent, "mode": mode, "episodes": len(values),
                "min": min(values) if values else None,
                "p10": quantile(values, 0.1),
                "p50": quantile(values, 0.5),
                "max": max(values) if values else None,
                "below_3m": sum(1 for value in values if value < 3.0),
            })
    unknown = sorted({(r["intent"], r["mode"]) for r in all_rows
                      if r["intent"] not in INTENTS or r["mode"] not in MODES})
    lowest = sorted(all_rows, key=lambda r: r["minimum_separation_m"])[:3]
    for record in lowest:
        episode = next(row["dir"] for row in rows
                       if row["skeleton_id"] == record["skeleton_id"]
                       and row["mode"] == record["mode"])
        recomputed = recompute_min_separation(episode)
        record["recomputed"] = recomputed
        record["delta_m"] = abs(recomputed["value_m"] - record["minimum_separation_m"])
        record["flagged_over_1e_6"] = record["delta_m"] > EPS
    return {
        "status": "ok",
        "method": {
            "field": "metrics.json minimum_separation_m（episode 级）",
            "percentiles": "线性插值分位（0 基索引）",
            "below_3m": "严格小于 3.0 m",
            "recomputation": "truth_10hz.npz 全部帧与全部机对的 3D 欧氏距离全局最小值",
        },
        "episodes_total": len(all_rows),
        "unknown_intent_mode": [list(pair) for pair in unknown],
        "table": table,
        "lowest_three": lowest,
    }


def render_markdown(report):
    lines = []
    add = lines.append
    add("# FE-INT 冻结前数据质量快检（只读统计）")
    add("")
    add(f"- 数据根：`{report['dataset_root']}`")
    add(f"- 骨架：{report['integrity']['skeletons']}；episode："
        f"{report['integrity']['episodes']}（synchronous "
        f"{report['integrity']['episodes_by_mode']['synchronous']}，sequential "
        f"{report['integrity']['episodes_by_mode']['sequential']}）")
    add(f"- 脚本：`scripts/qc_v07_fe_pre_freeze.py`")
    add(f"- 脚本 SHA256：`{report['script_sha256']}`")
    add("- 范围：只读 `truth_10hz.npz`、`metrics.json`、`labels.json`、`task.json`；"
        "未运行规划或仿真，未修改任何既有源码、配置或测试。")
    add("")

    add("## Q1 停顿事件（按 role/execution_method × mode）")
    add("")
    blocker = report["q1"]
    add(f"状态：**{blocker['status'].upper()}**。Q1 表未计算。")
    add("")
    add("口径：按要求读取 `task_v07.criteria.load_criteria()[\"detectors\"][\"dwell\"]`，"
        "键值原样如下。")
    add("")
    add("```json")
    add(json.dumps(blocker["dwell_config"], ensure_ascii=False, indent=2))
    add("```")
    add("")
    add(f"- 配置键：{', '.join('`' + key + '`' for key in blocker['dwell_keys'])}。")
    add(f"- 速度阈值字段：{blocker['velocity_threshold_key'] or '未找到'}。")
    add(f"- 最短持续时间字段：{blocker['duration_threshold_key'] or '未找到'}。")
    add("- 字段语义：`window_s` 为窗口长度，`radius_m` / `max_start_end_m` 为距离；"
        "三者均不是速度阈值，也不是最短持续时间阈值。")
    add(f"- 原因：{blocker['reason']}。")
    add("- 未采用的同名字段（不在指定配置源中）："
        + "；".join(f"`{item['key']}` = {item['values_across_60_episodes']}"
                   for item in blocker["unused_task_fields"]) + "。")
    add("")
    geometry = blocker["target_geometry"]
    add(f"- 目标几何：在 `task.json` 中检查 "
        f"{geometry['groups_checked']} 个 episode-group 记录的 `center_m` / `vertices_m`，"
        f"找到 {geometry['groups_with_geometry']} 个（状态 `{geometry['status']}`）。")
    add("- 按“找不到明确的速度或时长字段，停下报告字段清单，不要自选数值”执行；"
        "未选取任何阈值，未从其他文件替代取值。")
    add("")
    add("Q1 表：BLOCKED（无阈值字段，无目标几何）。")
    add("")

    add("### M1 驻留检出（部分）")
    add("")
    add("口径：字段路径 `labels.json -> agents[agent_id] -> observed -> contribution -> dwell -> "
        "detected`，与 `scripts/summarize_v07_s15_sim_pilot.py` 的 `label_facts()` 一致；"
        "单位为 agent-episode。")
    add("")
    add("| role / execution_method | 成员数 | M1 驻留检出=是 | M1 驻留检出=否 |")
    add("|---|---|---|---|")
    for row in report["q1"]["m1_dwell"]["by_role"]:
        add(f"| {row['role_execution_method']} | {row['members']} | {row['detected']} | "
            f"{row['not_detected']} |")
    add("")
    add(f"缺失 `dwell.detected` 字段的 agent-episode："
        f"{len(report['q1']['m1_dwell']['missing_fields'])}。")
    add("Q1 列为 BLOCKED，故请求的 2×2 交叉计数未产出；上表仅为 M1 边际计数。")
    add("")

    add("## Q2 航线转角（按 role/execution_method）")
    add("")
    method = report["q2"]["method"]
    add(f"口径：取 `task.json` 的 `references[agent_id].points_enu_m` 前两维；"
        f"每个内部顶点的航向转角 θ = arccos(clip(u·w, −1, 1))，单位度，u、w 为相邻两段单位"
        f"方向向量；长度 < 1e-6 m 的段跳过；每成员取最大转角。"
        f"去重口径：{method['deduplication']}；比例分母为有 ≥1 个有效内部顶点的成员数；"
        f"分位数采用{method['p50']}。")
    add("")
    add("| role / execution_method | 成员数 | 有效成员数 | 最大转角 min (°) | p50 (°) | max (°) | "
        "≥90° | ≥150° |")
    add("|---|---|---|---|---|---|---|---|")
    for row in report["q2"]["table"]:
        add(f"| {row['role_execution_method']} | {row['members']} | "
            f"{row['members_with_valid_vertices']} | {fmt(row['max_turn_min'])} | "
            f"{fmt(row['max_turn_p50'])} | {fmt(row['max_turn_max'])} | "
            f"{ratio(row['ge_90'], row['members_with_valid_vertices'])} | "
            f"{ratio(row['ge_150'], row['members_with_valid_vertices'])} |")
    add("")
    add(f"无有效内部顶点的成员：{report['q2']['members_without_valid_vertices']}"
        f"/{report['q2']['members_total']}。")
    add(f"若按 60 个 episode 逐个成员计，成员数为 "
        f"{report['q2']['members_total_if_counted_per_episode']}；因 task.json 逐字节一致，"
        f"转角分布与上表相同。")
    add("")

    add("## Q3 最小机间距（按 intent × mode）")
    add("")
    method = report["q3"]["method"]
    add(f"口径：`metrics.json` 的 `minimum_separation_m`（episode 级）；分位数采用"
        f"{method['percentiles']}；`< 3 m` 为严格小于；每个 intent × mode 行为 6 条 episode。")
    add("")
    add("| intent | mode | episode 数 | min (m) | p10 (m) | p50 (m) | max (m) | < 3 m |")
    add("|---|---|---|---|---|---|---|---|")
    for row in report["q3"]["table"]:
        add(f"| {row['intent']} | {row['mode']} | {row['episodes']} | {fmt(row['min'])} | "
            f"{fmt(row['p10'])} | {fmt(row['p50'])} | {fmt(row['max'])} | {row['below_3m']} |")
    add("")
    add("### 全部 episode 中最小机间距最小的 3 条")
    add("")
    add(f"口径：`metrics.json` 数值排序；重算用 `truth_10hz.npz` 的全部帧与全部机对，"
        f"取 3D 欧氏距离全局最小值；差值 > 1e-6 m 标注。")
    add("")
    add("| skeleton_id | mode | metrics (m) | 重算 (m) | 机对 | 时刻 (s) | 差值 (m) | 标注 |")
    add("|---|---|---|---|---|---|---|---|")
    for row in report["q3"]["lowest_three"]:
        recomputed = row["recomputed"]
        flag = "差值 > 1e-6 m" if row["flagged_over_1e_6"] else "一致"
        add(f"| {row['skeleton_id']} | {row['mode']} | "
            f"{fmt(row['minimum_separation_m'])} | {fmt(recomputed['value_m'])} | "
            f"{recomputed['agent_a']} / {recomputed['agent_b']} | "
            f"{recomputed['time_s']:.6f} | {row['delta_m']:.3e} | {flag} |")
    add("")

    add("## 数据完整性检查")
    add("")
    add("口径：逐 episode 核对文件存在、成员覆盖、`truth_10hz.npz` 的 agent 顺序与数量、"
        "`labels.json` 的 agent 集合、`metrics.json` 的 skeleton/mode 标识；只读。")
    add("")
    integrity = report["integrity"]
    add("| 检查项 | 结果 |")
    add("|---|---|")
    add(f"| 骨架数 | {integrity['skeletons']} |")
    add(f"| episode 数 | {integrity['episodes']} |")
    add(f"| 同时具备两 mode 的骨架数 | {integrity['skeletons_with_both_modes']} |")
    add(f"| agent 数量不一致 | {len(integrity['agent_count_mismatches'])} |")
    add(f"| npz agent 顺序不一致 | {len(integrity['npz_id_order_mismatches'])} |")
    add(f"| labels agent 集合不一致 | {len(integrity['labels_agent_mismatches'])} |")
    add(f"| metrics skeleton/mode 标识不一致 | {len(integrity['scene_digest_mismatches'])} |")
    add("")

    add("## 来源与键名")
    add("")
    add("- 配置键：`task_v07.criteria.load_criteria()[\"detectors\"][\"dwell\"]` → "
        + "、".join(f"`{key}`" for key in blocker["dwell_keys"]) + "（原样读取；未用于选值）。")
    add(f"- 数据路径：`{report['dataset_root']}`，"
        "每骨架下 `synchronous/`、`sequential/` 的 `truth_10hz.npz`、`metrics.json`、"
        "`labels.json`、`task.json`。")
    add(f"- 脚本 SHA256：`{report['script_sha256']}`。")
    add("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET,
                        help="v0.7 s15 simulation attempt root")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT,
                        help="directory for qc_report.md and qc_report.json")
    args = parser.parse_args()

    skeletons, rows = episode_rows(args.dataset)
    integrity = check_integrity(skeletons, rows)
    roles_by_episode = {
        (row["skeleton_id"], row["mode"]): member_roles(read_json(row["dir"] / "task.json"))
        for row in rows
    }
    criteria = load_criteria()
    q1 = dwell_blocker(criteria, rows)
    q1["m1_dwell"] = m1_dwell(rows, roles_by_episode)
    q2 = q2_routes(skeletons)
    q3 = q3_separation(rows)

    report = {
        "schema_version": "fe_int.qc_v07/1",
        "dataset_root": str(args.dataset),
        "script_path": "scripts/qc_v07_fe_pre_freeze.py",
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "integrity": integrity,
        "q1": q1,
        "q2": q2,
        "q3": q3,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "qc_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.out_dir / "qc_report.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {args.out_dir / 'qc_report.md'}")
    print(f"wrote {args.out_dir / 'qc_report.json'}")
    print(f"Q1={q1['status']} Q2={q2['status']} Q3={q3['status']}")


if __name__ == "__main__":
    main()
