"""FE-INT pre-freeze speed-profile check over the v0.7 s15 simulation attempt.

Read-only diagnostic statistics for low-speed events against route vertices. Reads
truth_10hz.npz, metrics.json, labels.json and task.json; writes qc_speed_report.md and
qc_speed_report.json. The three constants below are diagnostic for this run only, not criteria.
"""
import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]

DEFAULT_DATASET = Path(
    "F:/CASIA/Drone Swarm Situational Awareness Algorithm/SwarmData/v07_dataset/"
    "attempt_s15sim_20261017T071447Z")
DEFAULT_OUT = PROJECT / "docs/v07/evidence/fe_int/quality_check"
MODES = ("synchronous", "sequential")
V_LOW = 1.0
V_MOVE = 1.0
NEAR_VERTEX = 3.0
EPS = 1e-6
DT_S = 0.1


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
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    index = (len(values) - 1) * p
    low = int(index)
    high = min(low + 1, len(values) - 1)
    return float(values[low] + (values[high] - values[low]) * (index - low))


def fmt(value, digits=6):
    return "NA" if value is None else f"{value:.{digits}f}"


def ratio(numerator, denominator):
    if not denominator:
        return "0/0 (NA)"
    return f"{numerator}/{denominator} ({100.0 * numerator / denominator:.2f}%)"


def group_map(task):
    """agent_id -> (group_id, group); each member must belong to exactly one group."""
    mapping = {}
    for group_id, group in task["group_skeletons"].items():
        for agent in group["members"]:
            require(agent not in mapping, f"member {agent} appears in more than one group")
            mapping[agent] = (group_id, group)
    require(set(mapping) == set(task["agent_ids"]),
            "group members do not cover task.json agent_ids")
    return mapping


def vertex_turns(points_xy):
    """Turn at each internal vertex, index-aligned with points_xy[1:-1]."""
    segments = np.diff(points_xy, axis=0)
    lengths = np.linalg.norm(segments, axis=1)
    turns = []
    for index in range(1, len(points_xy) - 1):
        if lengths[index - 1] < EPS or lengths[index] < EPS:
            turns.append(None)
            continue
        u = segments[index - 1] / lengths[index - 1]
        w = segments[index] / lengths[index]
        turns.append(math.degrees(math.acos(float(np.clip(np.dot(u, w), -1.0, 1.0)))))
    return turns


def contiguous_runs(mask):
    runs = []
    start = None
    for index, flag in enumerate(mask):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            runs.append((start, index - 1))
            start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    return runs


def analyse_member(task, truth, agent, skeleton_id, mode, groups):
    """One member-episode: speed window, low-speed events, route geometry."""
    agent_ids = [str(value) for value in truth["agent_ids"]]
    require(agent in agent_ids, f"agent {agent} missing from truth_10hz.npz")
    index = agent_ids.index(agent)
    speed = np.linalg.norm(truth["v"][:, index, :2], axis=1)
    positions = truth["p"][:, index, :2]
    times = truth["time_us"].astype(float) / 1e6

    group_id, group = groups[agent]
    cruise_path = f"task.json -> group_skeletons[{group_id}] -> cruise_speed_m_s"
    cruise = group.get("cruise_speed_m_s")
    if cruise is None:
        cruise_path = "task.json -> cruise_speed_m_s"
        cruise = task.get("cruise_speed_m_s")
    require(cruise is not None and float(cruise) > 0,
            f"no positive cruise_speed_m_s for {skeleton_id}/{mode}/{agent}")
    cruise = float(cruise)

    reference = task["references"].get(agent)
    require(reference is not None, f"no reference for {skeleton_id}/{mode}/{agent}")
    require("points_enu_m" in reference,
            f"no points_enu_m for {skeleton_id}/{mode}/{agent}")
    route = np.asarray(reference["points_enu_m"], dtype=float)
    require(route.ndim == 2 and route.shape[1] >= 2,
            f"points_enu_m has bad shape for {skeleton_id}/{mode}/{agent}")
    route_xy = route[:, :2]
    inner_vertices = route_xy[1:-1]
    turns = vertex_turns(route_xy)
    route_length_km = float(np.sum(np.linalg.norm(np.diff(route_xy, axis=0), axis=1))) / 1000.0

    above = np.where(speed > V_MOVE)[0]
    record = {
        "skeleton_id": skeleton_id,
        "mode": mode,
        "agent_id": agent,
        "role": group["role"],
        "execution_method": group["execution_method"],
        "cruise_speed_m_s": cruise,
        "cruise_speed_field_path": cruise_path,
        "internal_vertices": int(len(inner_vertices)),
        "route_length_km": route_length_km,
        "motion_window_start_frame": None,
        "motion_window_end_frame": None,
        "motion_window_duration_s": None,
        "range_km": None,
        "low_speed_event_count": None,
        "events_per_km": None,
        "low_speed_time_share": None,
        "speed_over_cruise_p10": None,
        "speed_over_cruise_p50": None,
        "empty_motion_window": False,
        "events": [],
    }
    if len(above) == 0:
        record["empty_motion_window"] = True
        return record

    low = int(above[0])
    high = int(above[-1])
    window = speed[low:high + 1]
    window_positions = positions[low:high + 1]
    window_times = times[low:high + 1]
    record["motion_window_start_frame"] = low
    record["motion_window_end_frame"] = high
    record["motion_window_duration_s"] = float((high - low + 1) * DT_S)
    record["range_km"] = float(
        np.sum(np.linalg.norm(np.diff(window_positions, axis=0), axis=1))) / 1000.0

    low_mask = window < V_LOW
    record["low_speed_time_share"] = float(np.mean(low_mask)) if len(window) else None
    record["speed_over_cruise_p10"] = quantile(list(window / cruise), 0.1)
    record["speed_over_cruise_p50"] = quantile(list(window / cruise), 0.5)

    events = []
    for run_start, run_end in contiguous_runs(low_mask):
        start_time = float(window_times[run_start])
        end_time = float(window_times[run_end] + DT_S)
        offset = int(np.argmin(window[run_start:run_end + 1]))
        minimum_frame = low + run_start + offset
        position = positions[minimum_frame]
        event = {
            "start_s": start_time,
            "end_s": end_time,
            "duration_s": float((run_end - run_start + 1) * DT_S),
            "minimum_frame": int(minimum_frame),
            "minimum_time_s": float(times[minimum_frame]),
            "minimum_speed_m_s": float(speed[minimum_frame]),
            "position_xy_m": [float(position[0]), float(position[1])],
            "nearest_vertex_index": None,
            "distance_to_vertex_m": None,
            "vertex_turn_deg": None,
        }
        if len(inner_vertices):
            distances = np.linalg.norm(inner_vertices - position, axis=1)
            nearest = int(np.argmin(distances))
            event["nearest_vertex_index"] = nearest + 1
            event["distance_to_vertex_m"] = float(distances[nearest])
            event["vertex_turn_deg"] = turns[nearest]
        events.append(event)

    record["events"] = events
    record["low_speed_event_count"] = len(events)
    record["events_per_km"] = (len(events) / record["range_km"]
                               if record["range_km"] > 0 else None)
    return record


def speed_table(member_records):
    grouped = defaultdict(list)
    for record in member_records:
        grouped[(record["role"], record["execution_method"], record["mode"])].append(record)
    table = []
    for key in sorted(grouped, key=lambda item: (
            item[0], item[1], MODES.index(item[2]) if item[2] in MODES else 99)):
        records = grouped[key]
        counts = [r["low_speed_event_count"] for r in records]
        per_km = [r["events_per_km"] for r in records if r["events_per_km"] is not None]
        shares = [r["low_speed_time_share"] for r in records
                  if r["low_speed_time_share"] is not None]
        pooled = np.concatenate([r["_window_over_cruise"] for r in records
                                 if r["_window_over_cruise"] is not None]) \
            if any(r["_window_over_cruise"] is not None for r in records) else np.array([])
        table.append({
            "role": key[0],
            "execution_method": key[1],
            "mode": key[2],
            "members": len(records),
            "event_count_p50": quantile(counts, 0.5),
            "event_count_max": max(counts) if counts else None,
            "events_per_km_p50": quantile(per_km, 0.5),
            "low_time_share_p50": quantile(shares, 0.5),
            "speed_over_cruise_p10": quantile(list(pooled), 0.1),
            "speed_over_cruise_p50": quantile(list(pooled), 0.5),
            "empty_motion_windows": sum(1 for r in records if r["empty_motion_window"]),
            "zero_range_members": sum(1 for r in records if r["range_km"] == 0),
        })
    return table


def vertex_table(member_records):
    """S2: near-vertex event share and turn bins, plus vertices per route km."""
    grouped = defaultdict(lambda: {
        "events": 0, "near": 0,
        "bins": {"<10": 0, "10-45": 0, "45-90": 0, ">=90": 0},
        "turn_missing": 0,
        "member_records": [],
    })
    for record in member_records:
        key = (record["role"], record["execution_method"])
        bucket = grouped[key]
        bucket["member_records"].append(record)
        for event in record["events"]:
            bucket["events"] += 1
            distance = event["distance_to_vertex_m"]
            if distance is None or distance > NEAR_VERTEX:
                continue
            bucket["near"] += 1
            turn = event["vertex_turn_deg"]
            if turn is None:
                bucket["turn_missing"] += 1
            elif turn < 10.0:
                bucket["bins"]["<10"] += 1
            elif turn < 45.0:
                bucket["bins"]["10-45"] += 1
            elif turn < 90.0:
                bucket["bins"]["45-90"] += 1
            else:
                bucket["bins"][">=90"] += 1
    table = []
    for key in sorted(grouped):
        bucket = grouped[key]
        densities = []
        for record in bucket["member_records"]:
            if record["route_length_km"] > 0:
                densities.append(record["internal_vertices"] / record["route_length_km"])
        table.append({
            "role": key[0],
            "execution_method": key[1],
            "events": bucket["events"],
            "near_vertex_events": bucket["near"],
            "near_vertex_ratio": (bucket["near"] / bucket["events"]
                                  if bucket["events"] else None),
            "turn_bins": bucket["bins"],
            "turn_missing": bucket["turn_missing"],
            "vertices_per_km_p50": quantile(densities, 0.5),
        })
    return table


def dwell_table(member_records, labels_by_episode):
    """S3: M1 dwell fields and whether t_s falls inside an event or within +/-20 s."""
    grouped = defaultdict(lambda: {
        "members": 0, "detected": 0, "not_detected": 0,
        "durations": [], "duration_missing": 0,
        "t_s_valid": 0, "t_s_missing": 0, "t_s_matched": 0,
        "label_missing": 0,
    })
    for record in member_records:
        key = (record["role"], record["execution_method"])
        bucket = grouped[key]
        bucket["members"] += 1
        labels = labels_by_episode[(record["skeleton_id"], record["mode"])]
        agent = labels.get("agents", {}).get(record["agent_id"])
        if agent is None:
            bucket["label_missing"] += 1
            continue
        dwell = ((agent.get("observed") or {}).get("contribution") or {}).get("dwell")
        if not isinstance(dwell, dict) or "detected" not in dwell:
            bucket["label_missing"] += 1
            continue
        detected = bool(dwell["detected"])
        if detected:
            bucket["detected"] += 1
            duration = dwell.get("total_duration_s")
            if duration is None:
                bucket["duration_missing"] += 1
            else:
                bucket["durations"].append(float(duration))
            t_s = dwell.get("t_s")
            if t_s is None:
                bucket["t_s_missing"] += 1
            else:
                bucket["t_s_valid"] += 1
                matched = any(
                    event["start_s"] - 20.0 <= float(t_s) <= event["end_s"] + 20.0
                    for event in record["events"])
                bucket["t_s_matched"] += int(matched)
        else:
            bucket["not_detected"] += 1
    table = []
    for key in sorted(grouped):
        bucket = grouped[key]
        table.append({
            "role": key[0],
            "execution_method": key[1],
            "members": bucket["members"],
            "detected": bucket["detected"],
            "not_detected": bucket["not_detected"],
            "label_missing": bucket["label_missing"],
            "detected_duration_p50": quantile(bucket["durations"], 0.5),
            "detected_duration_max": max(bucket["durations"]) if bucket["durations"] else None,
            "detected_duration_missing": bucket["duration_missing"],
            "t_s_valid": bucket["t_s_valid"],
            "t_s_missing": bucket["t_s_missing"],
            "t_s_within_event_pm20s": bucket["t_s_matched"],
            "t_s_within_event_pm20s_ratio": (bucket["t_s_matched"] / bucket["t_s_valid"]
                                             if bucket["t_s_valid"] else None),
        })
    return table


def series_for_member(task, truth, agent, mode, groups):
    agent_ids = [str(value) for value in truth["agent_ids"]]
    require(agent in agent_ids, f"agent {agent} missing from truth_10hz.npz")
    index = agent_ids.index(agent)
    speed = np.linalg.norm(truth["v"][:, index, :2], axis=1)
    positions = truth["p"][:, index, :2]
    times = truth["time_us"].astype(float) / 1e6
    sampled = np.where(np.mod(truth["time_us"].astype(np.int64), 1_000_000) == 0)[0]
    require(len(sampled) > 0, f"no 1 s samples for {agent}")
    group_id, group = groups[agent]
    reference = task["references"][agent]
    route_xy = np.asarray(reference["points_enu_m"], dtype=float)[:, :2]
    arrivals = []
    for vertex_offset, vertex in enumerate(route_xy[1:-1]):
        distances = np.linalg.norm(positions - vertex, axis=1)
        frame = int(np.argmin(distances))
        arrivals.append({
            "vertex_index": vertex_offset + 1,
            "vertex_xy_m": [float(vertex[0]), float(vertex[1])],
            "arrival_frame": frame,
            "arrival_time_s": float(times[frame]),
            "distance_m": float(distances[frame]),
        })
    return {
        "mode": mode,
        "group_id": group_id,
        "role": group["role"],
        "execution_method": group["execution_method"],
        "cruise_speed_m_s": float(group.get("cruise_speed_m_s",
                                            task.get("cruise_speed_m_s"))),
        "sample_interval_s": 1.0,
        "time_s": [float(times[frame]) for frame in sampled],
        "speed_m_s": [float(speed[frame]) for frame in sampled],
        "vertex_arrivals": arrivals,
    }


def select_series_members(skeletons):
    """First (skeleton_id, agent_id) for each of the feint and monitoring roles."""
    candidates = {"feint": [], "monitoring": []}
    for skeleton in skeletons:
        task = read_json(skeleton / MODES[0] / "task.json")
        groups = group_map(task)
        for agent, (_, group) in groups.items():
            role = group["role"]
            if role in candidates:
                candidates[role].append((skeleton.name, agent))
    selected = {}
    for role, items in candidates.items():
        require(items, f"no member with role {role} found")
        selected[role] = sorted(set(items))[0]
    return selected


def render_markdown(report):
    lines = []
    add = lines.append
    add("# FE-INT 冻结前速度剖面快检（只读统计）")
    add("")
    add(f"- 数据根：`{report['dataset_root']}`")
    add(f"- 骨架：{report['integrity']['skeletons']}；episode："
        f"{report['integrity']['episodes']}")
    add("- 诊断常数：V_LOW = 1.0 m/s；V_MOVE = 1.0 m/s；NEAR_VERTEX = 3.0 m；"
        "仅用于本次统计，不是判据。")
    add(f"- 脚本：`scripts/qc_v07_fe_speed_profile.py`")
    add(f"- 脚本 SHA256：`{report['script_sha256']}`")
    add("- 范围：只读 `truth_10hz.npz`、`metrics.json`、`labels.json`、`task.json`；"
        "未运行规划或仿真，未修改任何既有源码、配置或测试。")
    add("")

    add("## S1 低速事件与速度水平（按 role/execution_method × mode）")
    add("")
    add("口径：运动窗为第一个 s > V_MOVE 的帧到最后一个 s > V_MOVE 的帧（含端点）；"
        "低速事件为运动窗内连续 s < V_LOW 的帧段，不设最短时长，时长 = 帧数 × 0.1 s；"
        "L = 运动窗内 Σ‖Δp_xy‖（km）；s/c 为组内所有成员运动窗内全部 10 Hz 帧合并后的"
        "分位（线性插值，0 基索引）；其余列为每成员先算指标再跨成员取 p50/max。"
        "逐成员、逐事件的记录（含位置、d_v、最近顶点转角）见 "
        "`qc_speed_report.json` 的 `s1.per_member`。")
    add("")
    add("| role / execution_method | mode | 成员数 | 事件数 p50 | 事件数 max | 事件数/L p50 (次/km) | "
        "s<V_LOW 时间占比 p50 | s/c p10 | s/c p50 |")
    add("|---|---|---|---|---|---|---|---|---|")
    for row in report["s1"]["table"]:
        add(f"| {row['role']} / {row['execution_method']} | {row['mode']} | {row['members']} | "
            f"{fmt(row['event_count_p50'])} | {fmt(row['event_count_max'], 0)} | "
            f"{fmt(row['events_per_km_p50'])} | {fmt(row['low_time_share_p50'])} | "
            f"{fmt(row['speed_over_cruise_p10'])} | {fmt(row['speed_over_cruise_p50'])} |")
    add("")
    add(f"空运动窗：{sum(r['empty_motion_windows'] for r in report['s1']['table'])}；"
        f"L = 0 的成员：{sum(r['zero_range_members'] for r in report['s1']['table'])}。")
    add("")

    add("## S2 顶点附近低速事件（按 role/execution_method，合并两个 mode）")
    add("")
    add("口径：d_v 为事件内最低速帧位置到最近内部顶点的水平距离；顶点附近事件为 "
        "d_v ≤ 3.0 m；比例分母为该角色全部低速事件（两个 mode 合并，每成员计两次）；"
        "转角定义与上一轮 Q2 相同（相邻两段单位方向向量的 arccos，度）；"
        "分档为 < 10°、10–45°、45–90°、≥ 90°（含下界、不含上界）；"
        "内部顶点数/航线长度使用完整航线（非运动窗航程），每成员先算比值再取 p50。")
    add("")
    add("| role / execution_method | 全部低速事件 | 顶点附近事件 | 比例 | <10° | 10–45° | 45–90° | "
        "≥90° | 转角缺失 | 内部顶点数/航线长度 p50 (个/km) |")
    add("|---|---|---|---|---|---|---|---|---|---|")
    for row in report["s2"]["table"]:
        bins = row["turn_bins"]
        add(f"| {row['role']} / {row['execution_method']} | {row['events']} | "
            f"{row['near_vertex_events']} | "
            f"{ratio(row['near_vertex_events'], row['events'])} | "
            f"{bins['<10']} | {bins['10-45']} | {bins['45-90']} | {bins['>=90']} | "
            f"{row['turn_missing']} | {fmt(row['vertices_per_km_p50'])} |")
    add("")

    add("## S3 M1 驻留字段与低速事件的时间对应（按 role/execution_method）")
    add("")
    add("口径：字段路径 `labels.json -> agents[agent_id] -> observed -> contribution -> dwell`，"
        "取 `detected`、`t_s`、`total_duration_s`；合并两个 mode，每成员计两次；"
        "`detected=True` 的 `total_duration_s` 取 p50/max；`t_s` 按 round(t_s × 10) 对应帧，"
        "若该时刻落在任一低速事件的 [start − 20 s, end + 20 s] 内则计为对应；"
        "比例分母为 `detected=True` 且 `t_s` 非空的 agent-episode 数。")
    add("")
    add("| role / execution_method | 成员数 | detected=True | detected=False | "
        "total_duration_s p50 | max | t_s 有效 | t_s 对应 ±20 s | 比例 |")
    add("|---|---|---|---|---|---|---|---|---|")
    for row in report["s3"]["table"]:
        add(f"| {row['role']} / {row['execution_method']} | {row['members']} | "
            f"{row['detected']} | {row['not_detected']} | "
            f"{fmt(row['detected_duration_p50'])} | {fmt(row['detected_duration_max'])} | "
            f"{row['t_s_valid']} | {row['t_s_within_event_pm20s']} | "
            f"{ratio(row['t_s_within_event_pm20s'], row['t_s_valid'])} |")
    add("")

    add("## 时间序列（JSON）")
    add("")
    add("口径：按 (skeleton_id, agent_id) 排序后，佯动与监视角色各取第一个成员；"
        "每 1 s 取一帧速度值；内部顶点到达时刻取整段轨迹中距该顶点最近的一帧；"
        "详细序列见 `qc_speed_report.json` 的 `time_series`，不在此表展开。")
    add("")

    add("## 来源与键名")
    add("")
    add("- 巡航速度字段：`task.json -> group_skeletons[group_id] -> cruise_speed_m_s`；"
        "顶层 `task.json -> cruise_speed_m_s` 在 60/60 episode 中与 group 值相同。")
    add("- 驻留字段：`labels.json -> agents[agent_id] -> observed -> contribution -> dwell` "
        "的 `detected`、`t_s`、`total_duration_s`。")
    add(f"- 数据路径：`{report['dataset_root']}`，每骨架下 `synchronous/`、`sequential/` 的 "
        "`truth_10hz.npz`、`labels.json`、`task.json`。")
    add(f"- 脚本 SHA256：`{report['script_sha256']}`。")
    add("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    require(args.dataset.is_dir(), f"dataset root not found: {args.dataset}")
    skeletons = sorted(p for p in args.dataset.iterdir()
                       if p.is_dir() and p.name.startswith("family_"))
    require(skeletons, f"no family_* skeleton directories under {args.dataset}")

    member_records = []
    labels_by_episode = {}
    episodes = 0
    for skeleton in skeletons:
        for mode in MODES:
            episode = skeleton / mode
            require(episode.is_dir(), f"missing episode directory: {episode}")
            for name in ("truth_10hz.npz", "metrics.json", "labels.json", "task.json"):
                require((episode / name).exists(), f"missing file: {episode / name}")
            episodes += 1
            task = read_json(episode / "task.json")
            labels = read_json(episode / "labels.json")
            truth = np.load(episode / "truth_10hz.npz", allow_pickle=False)
            groups = group_map(task)
            labels_by_episode[(skeleton.name, mode)] = labels
            for agent in task["agent_ids"]:
                record = analyse_member(task, truth, agent, skeleton.name, mode, groups)
                record["_window_over_cruise"] = None
                if not record["empty_motion_window"]:
                    index = [str(v) for v in truth["agent_ids"]].index(agent)
                    speed = np.linalg.norm(truth["v"][:, index, :2], axis=1)
                    record["_window_over_cruise"] = (
                        speed[record["motion_window_start_frame"]:
                              record["motion_window_end_frame"] + 1]
                        / record["cruise_speed_m_s"])
                member_records.append(record)

    s1 = {"status": "ok", "table": speed_table(member_records),
          "per_member": member_records}
    s2 = {"status": "ok", "table": vertex_table(member_records)}
    s3 = {"status": "ok", "table": dwell_table(member_records, labels_by_episode)}

    selected = select_series_members(skeletons)
    series = []
    for role, (skeleton_id, agent_id) in selected.items():
        entry = {"role": role, "skeleton_id": skeleton_id, "agent_id": agent_id,
                 "selection_rule": "按 (skeleton_id, agent_id) 排序后的第一个", "modes": {}}
        for mode in MODES:
            episode = args.dataset / skeleton_id / mode
            task = read_json(episode / "task.json")
            truth = np.load(episode / "truth_10hz.npz", allow_pickle=False)
            entry["modes"][mode] = series_for_member(
                task, truth, agent_id, mode, group_map(task))
        series.append(entry)

    for record in member_records:
        record.pop("_window_over_cruise", None)

    report = {
        "schema_version": "fe_int.qc_v07_speed/1",
        "dataset_root": str(args.dataset),
        "script_path": "scripts/qc_v07_fe_speed_profile.py",
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "constants": {"V_LOW": V_LOW, "V_MOVE": V_MOVE, "NEAR_VERTEX": NEAR_VERTEX,
                      "note": "diagnostic for this run only, not criteria"},
        "integrity": {
            "skeletons": len(skeletons),
            "episodes": episodes,
            "episodes_by_mode": {},
        },
        "s1": s1,
        "s2": s2,
        "s3": s3,
        "time_series": {"selection_rule": "按 (skeleton_id, agent_id) 排序后的第一个",
                        "members": series},
    }
    report["integrity"]["episodes_by_mode"] = {
        mode: sum(1 for skeleton in skeletons
                  if (args.dataset / skeleton.name / mode).is_dir())
        for mode in MODES}

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "qc_speed_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.out_dir / "qc_speed_report.md").write_text(
        render_markdown(report), encoding="utf-8")
    print(f"wrote {args.out_dir / 'qc_speed_report.md'}")
    print(f"wrote {args.out_dir / 'qc_speed_report.json'}")
    print(f"members={len(member_records)} s1={len(s1['table'])} "
          f"s2={len(s2['table'])} s3={len(s3['table'])}")


if __name__ == "__main__":
    main()
