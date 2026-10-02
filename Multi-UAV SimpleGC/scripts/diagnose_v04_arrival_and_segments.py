"""Read-only V02 arrival fallback and route timing diagnostics; never a gate.

Replays the stored 10 Hz analysis rows, without modifying arrival_s or requiring
SITL. JSON/Markdown outputs must not exist. All source files are hashed twice.
"""

import argparse
import bisect
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
VERSION = "v04_arrival_and_segment_diagnostics_v1"
RUN = "verification/v04_v1_resume_20261002/runs/recon_shared_demo_3uav_20261002T083751Z_3874072a"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def xyz(point):
    return [point[key] for key in ("east_m", "north_m", "up_m")]


def csv_rows(path, velocity=False):
    result = defaultdict(list)
    keys = ["east_m", "north_m", "up_m"] + (["ve_m_s", "vn_m_s", "vu_m_s"] if velocity else [])
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            values = [float(row[key]) for key in keys] if row["valid"] == "1" else None
            result[row["agent_id"]].append((float(row["t_s"]), values))
    for rows in result.values():
        assert all(b[0] > a[0] for a, b in zip(rows, rows[1:])), "nonmonotonic stored trace"
    return dict(result)


def source_time(host, model):
    if not model.get("available"):
        return None
    knots = model["knots"]
    hosts = [row[1] for row in knots]
    if not hosts[0] <= host <= hosts[-1]:
        return None
    index = max(1, bisect.bisect_left(hosts, host))
    a, b = knots[index - 1:index + 1]
    return a[0] + (b[0] - a[0]) * (host - a[1]) / (b[1] - a[1])


def speed_rows(rows, channel, model, gap):
    result, previous = [], None
    for t, values in rows:
        speed = None
        if values is not None:
            if channel == "observation":
                speed = math.hypot(*values[3:5])
            elif previous is not None:
                before, last = previous
                left = source_time(before, model) if model.get("available") else before
                right = source_time(t, model) if model.get("available") else t
                if (1e-8 < t - before <= gap + 1e-8 and left is not None and right is not None
                        and 1e-8 < right - left <= gap + 1e-8):
                    speed = math.dist(values[:2], last[:2]) / (right - left)
        result.append(dict(t_s=t, position=values, speed_m_s=speed))
        previous = (t, values) if values is not None else None
    return result


def low_speed_intervals(candidates, tolerance=None):
    """Sample-supported spans only; no extrapolation to the phase-end event."""
    groups, current = [], []
    for row in candidates:
        eligible = (row["speed_m_s"] is not None and row["speed_m_s"] <= .3 + 1e-8
                    and (tolerance is None or row["distance_3d_m"] <= tolerance + 1e-8))
        if eligible:
            if current and row["t_s"] - current[-1]["t_s"] > .150000001:
                groups.append(current)
                current = []
            current.append(row)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return [dict(start_s=group[0]["t_s"], end_s=group[-1]["t_s"],
                 duration_s=group[-1]["t_s"]-group[0]["t_s"], sample_count=len(group),
                 minimum_distance_3d_m=min(row["distance_3d_m"] for row in group),
                 maximum_distance_3d_m=max(row["distance_3d_m"] for row in group)) for group in groups]


def arrival_diagnostics(window, speeds, tolerance):
    target = xyz(window["terminal_point"])
    start, end = window["terminal_waypoint_reached_s"], window["end_s"]
    candidates = [dict(row, distance_3d_m=math.dist(row["position"][:3], target),
                       distance_horizontal_m=math.dist(row["position"][:2], target[:2]),
                       vertical_error_m=abs(row["position"][2]-target[2]))
                  for row in speeds if start <= row["t_s"] <= end and row["position"] is not None]
    within = [row for row in candidates if row["distance_3d_m"] <= tolerance + 1e-8]
    slow = [row for row in candidates if row["speed_m_s"] is not None and row["speed_m_s"] <= .3 + 1e-8]
    joint = [row for row in within if row["speed_m_s"] is not None and row["speed_m_s"] <= .3 + 1e-8]
    closest = min(candidates, key=lambda row: (row["distance_3d_m"], row["t_s"]))
    fastest_low = min((row for row in candidates if row["speed_m_s"] is not None), key=lambda row: row["speed_m_s"])
    replay_source = "trajectory_stop" if joint else "trajectory_min_distance"
    replay_arrival = joint[0]["t_s"] if joint else closest["t_s"]
    assert replay_source == window["arrival_source"] and abs(replay_arrival-window["arrival_s"]) < 1e-8
    if not within:
        reason = "outside_1m_tolerance_throughout_search"
    elif not slow:
        reason = "speed_threshold_never_met_within_search"
    elif not joint:
        reason = "distance_and_speed_satisfied_at_different_times_only"
    else:
        reason = "verified_joint_sample_present"
    intervals = low_speed_intervals(candidates)
    sustained = [row for row in intervals if row["duration_s"] >= .2-1e-8]
    ending = next((row for row in reversed(intervals) if abs(row["end_s"]-candidates[-1]["t_s"]) < 1e-8), None)
    near_speeds = [row["speed_m_s"] for row in within if row["speed_m_s"] is not None]
    return dict(channel=window["channel"], agent_id=window["agent_id"], phase=window["phase"],
        arrival_source=window["arrival_source"], stored_arrival_s=window["arrival_s"],
        reproduced_exactly=True, search_interval_s=[start,end], search_duration_s=end-start,
        sampled_interval_s=[candidates[0]["t_s"], candidates[-1]["t_s"]],
        unobserved_tail_to_phase_end_s=end-candidates[-1]["t_s"],
        candidate_count=len(candidates), within_1m_count=len(within), speed_le_0p3_count=len(slow),
        jointly_eligible_count=len(joint), minimum_distance_sample=closest,
        minimum_speed_sample=fastest_low, minimum_speed_within_1m_m_s=min(near_speeds,default=None),
        speed_only_intervals=intervals, speed_only_sustained_intervals=sustained,
        speed_only_sustained_total_s=sum(row["duration_s"] for row in sustained),
        speed_only_final_contiguous_s=ending["duration_s"] if ending else 0.0,
        jointly_eligible_intervals=low_speed_intervals(candidates,tolerance),
        explanation=reason,
        duration_requirement_note="Original arrival_s needs one joint sample, not any minimum dwell; short phase tail can censor a later stop, but is not a failing dwell rule.",
        speed_noise_causality="SIM position-difference noise cannot be inferred from threshold failure alone; independent FCU comparison is diagnostic only, never substituted.")


def nearest(rows, target, start, end):
    selected = [(t,p) for t,p in rows if start <= t <= end and p is not None]
    t,p = min(selected, key=lambda row:(math.dist(row[1][:3],target),row[0]))
    return dict(t_s=t, distance_3d_m=math.dist(p[:3],target), position=p[:3])


def near_interval(rows, target, radius, anchor, start, end):
    selected = [(t,p) for t,p in rows if start <= t <= end]
    hit = [index for index,(t,p) in enumerate(selected) if abs(t-anchor) < 1e-8]
    if not hit:
        return None
    index = hit[0]
    def valid(i):
        return selected[i][1] is not None and math.dist(selected[i][1][:3],target) <= radius
    if not valid(index):
        return None
    lo = hi = index
    while lo and valid(lo-1) and selected[lo][0]-selected[lo-1][0] <= .150000001:
        lo -= 1
    while hi+1 < len(selected) and valid(hi+1) and selected[hi+1][0]-selected[hi][0] <= .150000001:
        hi += 1
    return [selected[lo][0],selected[hi][0]]


def segment_diagnostics(scene, windows, traces):
    segments, turns, endpoints = [], [], []
    for phase in scene["phases"]:
        name = phase["name"]
        nominal = scene["planning"]["nominal_phase_timing"][name]
        semantic = phase["semantic_phase"]
        for agent, route in phase["routes"].items():
            role = scene["semantic_plan"]["execution_phases"][name]["agents"][agent]
            previous = xyz(role["start_point"])
            for channel, channel_rows in traces.items():
                window = next(row for row in windows[channel] if row["agent_id"] == agent and row["phase"] == name)
                release,end = window["phase_release_s"],window["end_s"]
                nodes = [nearest(channel_rows[agent],xyz(point),release,end) for point in route]
                assert all(b["t_s"] > a["t_s"] for a,b in zip(nodes,nodes[1:])), "ambiguous waypoint closest ordering"
                event_times = {row["route_index"]:row["t_s"] for row in window["waypoint_events"]}
                waypoint_nominal = nominal["per_agent_waypoint_arrival_s"][agent]
                last_point, last_actual, last_event, last_nominal = previous, release, release, 0.0
                for index, (point,node,nominal_time) in enumerate(zip(route,nodes,waypoint_nominal)):
                    target = xyz(point)
                    planner_index = role["waypoint_planner_indices"][index]
                    category = ("scan" if planner_index%2 == 1 else "lane_change") if semantic == "observe" else semantic
                    length = math.dist(last_point,target)
                    actual, event = node["t_s"],event_times[index]
                    segments.append(dict(channel=channel,phase=name,agent_id=agent,route_index=index,seq=index+2,
                        planner_index=planner_index,primary_category=category,length_m=length,
                        nominal_duration_s=nominal_time-last_nominal,
                        actual_closest_duration_s=actual-last_actual,actual_event_duration_s=event-last_event,
                        excess_closest_duration_s=(actual-last_actual)-(nominal_time-last_nominal),
                        excess_event_duration_s=(event-last_event)-(nominal_time-last_nominal),
                        closest_interval_s=[last_actual,actual],event_interval_s=[last_event,event],
                        nominal_interval_s=[last_nominal,nominal_time],
                        closest_target_distance_3d_m=node["distance_3d_m"]))
                    if index < len(route)-1:
                        following = xyz(route[index+1])
                        incoming=[a-b for a,b in zip(target,last_point)]
                        outgoing=[a-b for a,b in zip(following,target)]
                        angle=math.degrees(math.acos(max(-1,min(1,sum(a*b for a,b in zip(incoming,outgoing))/(math.dist(target,last_point)*math.dist(following,target))))))
                        bounds=near_interval(channel_rows[agent],target,2.0,actual,last_actual,nodes[index+1]["t_s"])
                        turns.append(dict(channel=channel,phase=name,agent_id=agent,route_index=index,seq=index+2,
                            turn_angle_deg=angle,waypoint_radius_m=2.0,actual_sampled_interval_s=bounds,
                            actual_sampled_duration_s=bounds[1]-bounds[0] if bounds else None,
                            nominal_local_duration_s=(min(2.0,length)+min(2.0,math.dist(following,target)))/phase["speed_m_s"],
                            additive=False,note="Radius-2m neighbourhood around closest passage; overlaps adjoining primary segments and is not an independent causal turn penalty."))
                    else:
                        bounds=near_interval(channel_rows[agent],target,5.0,actual,last_actual,actual)
                        endpoints.append(dict(channel=channel,phase=name,agent_id=agent,
                            endpoint_radius_m=5.0,actual_sampled_interval_s=bounds,
                            actual_sampled_duration_s=bounds[1]-bounds[0] if bounds else None,
                            nominal_local_duration_s=min(5.0,length)/phase["speed_m_s"],
                            closest_to_phase_end_s=end-actual,event_to_phase_end_s=end-event,
                            additive=False,note="Final 5m neighbourhood is a deceleration proxy, not an acceleration-fit result; barrier/hold tail is separate."))
                    last_point,last_actual,last_event,last_nominal=target,actual,event,nominal_time
    groups=defaultdict(list)
    for row in segments:
        groups[(row["channel"],row["primary_category"])].append(row)
    summaries=[dict(channel=key[0],category=key[1],segment_count=len(rows),
        nominal_total_s=sum(row["nominal_duration_s"] for row in rows),
        closest_total_s=sum(row["actual_closest_duration_s"] for row in rows),
        event_total_s=sum(row["actual_event_duration_s"] for row in rows)) for key,rows in sorted(groups.items())]
    return dict(segments=segments,turn_neighbourhoods=turns,endpoint_deceleration_neighbourhoods=endpoints,primary_category_summary=summaries)


def fmt(value):
    return "—" if value is None else f"{value:.3f}" if isinstance(value,(int,float)) else str(value)


def markdown(report):
    lines=["# V02 arrival_s 兜底与航段耗时只读诊断", "", f"版本：`{VERSION}`；运行：`{report['run_id']}`。", "",
        "本报告不改变 arrival_s、名义模型、τ、验收门禁或任何旧产物。全部 18 个双通道窗口已逐一复现原 arrival_s；表中只展开 11 个兜底窗口。", "",
        "## 口径", "",
        "原定义在终点 waypoint_reached 接收事件至阶段结束之间搜索，以三维终点距离 ≤1 m 且水平速度 ≤0.3 m/s 的首个样本作为 arrival_s；没有最短悬停持续时间要求。SIM 速度来自 10 Hz 对齐位置的后向差分，分母为时钟模型反演后的源时间差。FCU 用其报告的水平速度。两者独立计算，不相互替代。", "",
        "下表的低速持续时长仅累加至少 0.2 s 的连续样本跨度（≤0.3 m/s），不施加 1 m 距离限制；因此可识别在容差外的低速停留。最后一个采样到阶段结束不足 0.1 s 的尾段不外推。此值是 sampled evidence，不能证明整个尾段一直静止。", "",
        "## 兜底窗口逐项结果", "",
        "| 通道/飞机/阶段 | 搜索区间 s | 最小三维距离 m | 最低速度 m/s | 距离内/低速/同时满足样本 | 低速持续总时长 s | 直接原因 |",
        "|---|---|---:|---:|---|---:|---|"]
    explanations={"outside_1m_tolerance_throughout_search":"全搜索区间均在 1 m 容差外", "speed_threshold_never_met_within_search":"搜索区间没有 ≤0.3 m/s 样本", "distance_and_speed_satisfied_at_different_times_only":"距离与速度在不同时刻满足"}
    for row in report["fallback_windows"]:
        lines.append(f"| {row['channel']}/{row['agent_id']}/{row['phase']} | {fmt(row['search_interval_s'][0])}–{fmt(row['search_interval_s'][1])} | {fmt(row['minimum_distance_sample']['distance_3d_m'])} | {fmt(row['minimum_speed_sample']['speed_m_s'])} | {row['within_1m_count']}/{row['speed_le_0p3_count']}/{row['jointly_eligible_count']} | {fmt(row['speed_only_sustained_total_s'])} | {explanations[row['explanation']]} |")
    lines += ["", "原因仅按可观测条件分类；阈值未通过本身不能证明差分噪声。JSON 还保存最小距离/速度所在时刻、该时刻的另外一个量、低速区间端点及其距离范围、最终连续低速时长和未采样尾长。不能把短观察尾段解释成原定义中不存在的最短悬停要求。", "", "## 航段主分类（加总为三机累计，非阶段墙钟时长）", "", "| 通道 | 类别 | 航段数 | 名义合计 s | 最近点合计 s | 事件合计 s |", "|---|---|---:|---:|---:|---:|"]
    for row in report["segment_timing"]["primary_category_summary"]:
        lines.append("| "+" | ".join(fmt(row[key]) for key in ("channel","category","segment_count","nominal_total_s","closest_total_s","event_total_s"))+" |")
    lines += ["", "实际最近点按各阶段内 10 Hz 三维距离最小样本确定，同距取首个样本，33 个节点在每个通道内均顺序单调。每段用相邻最近点的时间差（首段从阶段放行）计算；事件通道用相邻原始到点事件差。扫描/换线按原规划点索引分组。这里的采样与姿态/时钟误差不允许把小于约 0.1 s 的差异解释成精确动力学效应。", "", "## 每个航段", "", "| 通道/飞机/阶段 | seq | 类别 | 长度 m | 名义 s | 最近点 s | 事件 s | 最近点增量 s |", "|---|---:|---|---:|---:|---:|---:|---:|"]
    for row in report["segment_timing"]["segments"]:
        lines.append(f"| {row['channel']}/{row['agent_id']}/{row['phase']} | {row['seq']} | {row['primary_category']} | {fmt(row['length_m'])} | {fmt(row['nominal_duration_s'])} | {fmt(row['actual_closest_duration_s'])} | {fmt(row['actual_event_duration_s'])} | {fmt(row['excess_closest_duration_s'])} |")
    lines += ["", "## 转角与终点减速邻域（覆盖层，不与主分类相加）", "", "转角取内部航点周围 2 m 的连续三维邻域，名义时间取相邻两段各 2 m（受段长截断）除以名义速度；终点减速取最后航段终点周围 5 m 至最近点。这只是局部耗时诊断，不把整段增量归因于转弯或减速。覆盖层跨越相邻段，不能再加到上表总耗时。终点最近点至阶段结束的尾长单独保留，也不能全部声称为悬停。", "", "| 通道/飞机/阶段 | 转角 seq | 角度 ° | 邻域实际 s | 邻域名义 s |", "|---|---:|---:|---:|---:|"]
    for row in report["segment_timing"]["turn_neighbourhoods"]:
        lines.append(f"| {row['channel']}/{row['agent_id']}/{row['phase']} | {row['seq']} | {fmt(row['turn_angle_deg'])} | {fmt(row['actual_sampled_duration_s'])} | {fmt(row['nominal_local_duration_s'])} |")
    lines += ["", "| 通道/飞机/阶段 | 末端 5 m 实际 s | 名义 s | 最近点至阶段结束 s |", "|---|---:|---:|---:|"]
    for row in report["segment_timing"]["endpoint_deceleration_neighbourhoods"]:
        lines.append(f"| {row['channel']}/{row['agent_id']}/{row['phase']} | {fmt(row['actual_sampled_duration_s'])} | {fmt(row['nominal_local_duration_s'])} | {fmt(row['closest_to_phase_end_s'])} |")
    lines += ["", f"输入保护：{len(report['source_sha256'])} 个文件前后 SHA256 一致；旧运行及其分析目录未写入。", ""]
    return "\n".join(lines)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--run",default=RUN)
    parser.add_argument("--output",default="tmp_v04/ac4_v2_20261002")
    args=parser.parse_args()
    run=(PROJECT/args.run).resolve()
    output=(PROJECT/args.output).resolve()
    if not output.is_relative_to(PROJECT/"tmp_v04"):
        raise ValueError("output must be below tmp_v04")
    paths=[output/"arrival_and_segments.json",output/"arrival_and_segments.md"]
    if any(path.exists() for path in paths):
        raise FileExistsError("diagnostic output already exists; use a new output directory")
    sources=[path for path in run.rglob("*") if path.is_file()]
    hashes={str(path.relative_to(PROJECT)):digest(path) for path in sources}
    analysis=run/load(run/"analysis_latest.json")["directory"]
    scene=load(run/"scenario.json")
    metadata=load(run/"metadata.json")
    clocks=load(analysis/"clock_models.json")
    windows=load(analysis/"phase_windows.json")["channels"]
    traces={"truth":csv_rows(analysis/"truth.csv"),"observation":csv_rows(analysis/"observations.csv",True)}
    records=[]
    for channel, channel_windows in windows.items():
        for window in channel_windows:
            agent=window["agent_id"]
            speeds=speed_rows(traces[channel][agent],channel,clocks[agent],scene["max_gap_s"])
            records.append(arrival_diagnostics(window,speeds,scene["task_spec"]["execution"]["arrival_tolerance_m"]))
    fallback=[row for row in records if row["arrival_source"]=="trajectory_min_distance"]
    report=dict(version=VERSION,created_utc=datetime.now(timezone.utc).isoformat(),run_id=metadata["run_id"],
        analysis_directory=str(analysis.relative_to(PROJECT)),read_only=True,gate=False,
        arrival_definition_unchanged=True,all_windows=records,fallback_windows=fallback,
        fallback_count=dict(Counter(row["channel"] for row in fallback)),
        fallback_explanation_count=dict(Counter(row["explanation"] for row in fallback)),
        segment_timing=segment_diagnostics(scene,windows,traces),
        input_precision_note="10 Hz stored position grid; host/source clock alignment is passive and does not identify transport delay.",
        source_sha256=hashes)
    changed=[str(path.relative_to(PROJECT)) for path in sources if digest(path)!=hashes[str(path.relative_to(PROJECT))]]
    report["inputs_unchanged"]=not changed
    report["changed_inputs"]=changed
    assert not changed
    assert report["fallback_count"]=={"truth":7,"observation":4}
    output.mkdir(parents=True,exist_ok=True)
    with paths[0].open("x",encoding="utf-8") as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
    with paths[1].open("x",encoding="utf-8") as stream:
        stream.write(markdown(report))
    print(json.dumps(dict(version=VERSION,outputs=[str(path.relative_to(PROJECT)) for path in paths],
        fallback_count=report["fallback_count"],reasons=report["fallback_explanation_count"],
        replayed_windows=len(records),input_files=len(sources),inputs_unchanged=not changed),ensure_ascii=False))


if __name__ == "__main__":
    main()
