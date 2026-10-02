"""Read-only endpoint/BRAKE timing diagnosis; never changes arrival_s or a gate."""
import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from swarm_sim.analysis import aligned_truth_samples
from swarm_sim.observation_processing import prepare_v3_observations
from swarm_sim.recording import resample
from swarm_sim.truth import clock_to_host
from scripts.diagnose_v04_arrival_and_segments import source_time

VERSION = "arrival_brake_readonly_diagnostic_v1"
DEFAULT_LEDGER = "verification/v04_ac4_v2_20261002/records.json"
MODES = {3: "AUTO", 9: "LAND", 17: "BRAKE"}


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            value.update(block)
    return value.hexdigest()


def read_jsonl(path):
    with path.open(encoding="utf-8-sig") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def first_event(events, name, agent=None, phase=None):
    return next((e for e in events if e["event"] == name
                 and (agent is None or e.get("agent_id") == agent)
                 and (phase is None or e.get("phase") == phase)), None)


def speeds(rows, channel, model, max_gap):
    result, previous = [], None
    for t, values in rows:
        horizontal = vertical = None
        if values is not None:
            if channel == "FCU":
                horizontal, vertical = math.hypot(*values[3:5]), values[5]
            elif previous is not None:
                before, p = previous
                left, right = source_time(before, model), source_time(t, model)
                if (left is not None and right is not None and
                        0 < t - before <= max_gap and 0 < right - left <= max_gap):
                    horizontal = math.dist(values[:2], p[:2]) / (right - left)
                    vertical = (values[2] - p[2]) / (right - left)
        result.append(dict(t_s=t, position=values[:3] if values is not None else None,
                           horizontal_speed_m_s=horizontal, vertical_speed_m_s=vertical))
        previous = (t, values) if values is not None else None
    return result


def entry(rows, start, end, radius, horizontal=True):
    """First sampled entry, with an enclosing outside/inside bracket, no extrapolation."""
    key = "horizontal_distance_m" if horizontal else "distance_3d_m"
    previous = None
    for row in rows:
        if row["t_s"] < start or row["t_s"] > end:
            continue
        if row[key] is not None and row[key] <= radius:
            bracket = ([previous["t_s"], row["t_s"]] if previous is not None
                       and previous[key] is not None and previous[key] > radius
                       and row["t_s"] - previous["t_s"] <= .10000001 else None)
            return dict(first_inside_s=row["t_s"], crossing_bracket_s=bracket,
                        entry_left_censored=bracket is None, radius_m=radius,
                        metric=key, horizontal_speed_m_s=row["horizontal_speed_m_s"])
        previous = row
    return None


def slow_spans(rows, start, end, threshold=.3, minimum_duration=.2):
    """Continuous sample-supported horizontal low speed; no hidden gap bridging."""
    groups, active = [], []
    for row in rows:
        if not start <= row["t_s"] <= end:
            continue
        ok = row["horizontal_speed_m_s"] is not None and row["horizontal_speed_m_s"] <= threshold + 1e-8
        if ok:
            if active and row["t_s"] - active[-1]["t_s"] > .10000001:
                groups.append(active)
                active = []
            active.append(row)
        elif active:
            groups.append(active)
            active = []
    if active:
        groups.append(active)
    return [dict(start_s=g[0]["t_s"], end_s=g[-1]["t_s"], duration_s=g[-1]["t_s"]-g[0]["t_s"],
                 minimum_duration_confirmed_s=next(r["t_s"] for r in g if r["t_s"]-g[0]["t_s"]>=minimum_duration-1e-8),
                 samples=len(g), maximum_horizontal_speed_m_s=max(r["horizontal_speed_m_s"] for r in g),
                 max_abs_vertical_speed_m_s=max(abs(r["vertical_speed_m_s"]) for r in g if r["vertical_speed_m_s"] is not None),
                 start_horizontal_distance_m=g[0].get("horizontal_distance_m"),
                 start_distance_3d_m=g[0].get("distance_3d_m")) for g in groups
            if g[-1]["t_s"]-g[0]["t_s"] >= minimum_duration-1e-8]


def position_stage(stamp, transition):
    if stamp is None:
        return "no_supported_low_speed_span"
    begin, hb = transition["operation_started_s"], transition["first_mode_heartbeat_s"]
    if stamp < begin:
        return "before_transition_operation"
    if hb is None or stamp < hb:
        return "operation_started_before_mode_heartbeat"
    if transition["type"] == "final_LAND":
        return "after_LAND_heartbeat_horizontal_only"
    if stamp < transition["next_AUTO_request_marker_s"]:
        return "confirmed_BRAKE_before_next_AUTO"
    return "after_next_AUTO_request_marker"


def transition_evidence(events, heartbeats, phase, following, agent, elapsed):
    if following:
        begin = first_event(events, "phase_upload_started", agent, following)
        complete = first_event(events, "phase_upload_complete", agent, following)
        auto = first_event(events, "phase_start_sent", agent, following)
        auto_hb = first_event(events, "phase_auto_confirmed", agent, following)
        target = 17
        result = dict(type="next_phase_BRAKE", next_phase=following,
                      operation_started_s=begin["t"], upload_complete_s=complete["t"],
                      next_AUTO_request_marker_s=auto["t"], next_AUTO_confirmed_s=auto_hb["t"],
                      search_end_s=min(elapsed, auto["t"]+2))
    else:
        begin = first_event(events, "landing_started", agent)
        target = 9
        result = dict(type="final_LAND", next_phase=None, operation_started_s=begin["t"],
                      upload_complete_s=None, next_AUTO_request_marker_s=None, next_AUTO_confirmed_s=None,
                      search_end_s=min(elapsed, begin["t"]+5))
    hb = next((row for row in heartbeats if row["t_s"] >= begin["t"] and row["custom_mode"] == target), None)
    result.update(requested_mode=MODES[target], first_mode_heartbeat_s=hb["t_s"] if hb else None,
                  exact_SET_MODE_TX_available=False,
                  SET_MODE_TX_bound_s=[begin["t"], hb["t_s"]] if hb else None,
                  command_bound_note="Code calls mode() inside this operation, then waits for a new matching heartbeat; TX itself is not logged. Heartbeat RX confirms mode by this time, not the exact transition instant.")
    return result


def bin_command_modes(run, agent, model):
    """Read actual onboard CMD and MODE fields; no executable firmware inference."""
    from pymavlink import DFReader
    paths = sorted((run/"sitl"/agent/"logs").glob("*.BIN"))
    if len(paths) != 1:
        raise ValueError("one fresh BIN per agent required")
    reader = DFReader.DFReader_binary(str(paths[0]))
    result = []
    try:
        while (message := reader.recv_match(type=["CMD", "MODE"])) is not None:
            packet = message.to_dict()
            source = packet["TimeUS"]/1e6
            if model["source_range_s"][0] <= source <= model["source_range_s"][1]:
                result.append(dict(packet=packet, source_boot_s=source,
                                   mapped_run_time_s=clock_to_host(source, model)))
    finally:
        reader.close()
    return result


def analyze_run(run):
    metadata, scene = load(run/"metadata.json"), load(run/"scenario.json")
    if metadata["status"] != "completed":
        return dict(run_id=metadata["run_id"], skipped="run not completed; no complete endpoint diagnosis")
    analysis = run/load(run/"analysis_latest.json")["directory"]
    epoch, elapsed = metadata["run_epoch_monotonic_s"], metadata["elapsed_s"]
    mission_offset = metadata["flight_epoch_monotonic_s"]-epoch
    events = read_jsonl(run/"events.jsonl")
    windows = load(analysis/"phase_windows.json")["channels"]
    parameters = load(analysis/"logged_parameters.json")
    truths = defaultdict(list)
    with (analysis/"truth_source.csv").open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            values = [float(row[k]) for k in ("east_m", "north_m", "up_m")] if row["east_m"] else None
            truths[row["agent_id"]].append((float(row["source_boot_s"]), values))
    grid = [i/10 for i in range(math.floor(elapsed*10)+1)]
    records, audits = [], {}
    for vehicle in scene["vehicles"]:
        agent = vehicle["id"]
        packets = read_jsonl(run/"raw"/(agent+".jsonl"))
        prepared = prepare_v3_observations(packets, scene["origin"], metadata["quality_policy"], epoch, epoch+elapsed)
        model = prepared["clock_model"]
        assert model["available"] and prepared["timeline_error"] is None, (agent, "invalid lifecycle clock")
        audits[agent] = dict(clock_model=model, timeline_error=prepared["timeline_error"],
                             duplicate_count=prepared["audit"]["dropped_count"])
        onboard = bin_command_modes(run, agent, model)
        heartbeats = [dict(t_s=p["recv_monotonic_s"]-epoch, custom_mode=p["message"]["custom_mode"],
                          mode=MODES.get(p["message"]["custom_mode"], str(p["message"]["custom_mode"])))
                      for p in packets if p["message"]["mavpackettype"] == "HEARTBEAT"]
        samples = {"FCU": prepared["samples"], "SIM": aligned_truth_samples(truths[agent], model)}
        curves = {channel: speeds(resample(rows, grid, scene["max_gap_s"]), channel, model, scene["max_gap_s"])
                  for channel, rows in samples.items()}
        for phase_index, phase in enumerate(scene["phases"]):
            name = phase["name"]
            if not phase["routes"][agent]:
                records.append(dict(agent_id=agent, phase=name, skipped="hold_no_op has no endpoint waypoint"))
                continue
            following = scene["phases"][phase_index+1]["name"] if phase_index+1 < len(scene["phases"]) else None
            transition = transition_evidence(events, heartbeats, name, following, agent, elapsed)
            target_mode = 17 if following else 9
            bin_modes = [item for item in onboard if item["packet"]["mavpackettype"] == "MODE"
                         and item["packet"]["ModeNum"] == target_mode
                         and transition["operation_started_s"]-.2 <= item["mapped_run_time_s"]
                         <= transition["first_mode_heartbeat_s"]+.2]
            transition["onboard_MODE_evidence"] = bin_modes
            transition["onboard_MODE_note"] = "MODE has a logged FCU source time; host time is passively fitted, not a transmit timestamp or exact physical synchronization."
            reached = next(e for e in events if e["event"] == "waypoint_reached" and e.get("agent_id") == agent
                           and e.get("phase") == name and e.get("terminal"))
            verified = first_event(events, "task_target_verified", agent, name)
            release = first_event(events, "phase_release_scheduled", phase=name)["release_t"]
            prior = [e["t"] for e in events if e["event"] == "waypoint_reached" and e.get("agent_id") == agent
                     and e.get("phase") == name and e.get("route_index") is not None and not e.get("terminal")]
            entry_search_start = max(prior, default=release)
            upload_begin = first_event(events, "phase_upload_started", agent, name)["t"]
            terminal_cmds = [item for item in onboard if item["packet"]["mavpackettype"] == "CMD"
                and item["packet"]["CId"] == 16 and item["packet"]["CTot"] == len(phase["routes"][agent])+2
                and item["packet"]["CNum"] == len(phase["routes"][agent])+1
                and upload_begin-.2 <= item["mapped_run_time_s"] <= reached["t"]]
            logged_holds = sorted(set(item["packet"]["Prm1"] for item in terminal_cmds))
            terminal = scene["semantic_plan"]["execution_phases"][name]["agents"][agent]["terminal_point"]
            target = [terminal[k] for k in ("east_m", "north_m", "up_m")]
            lower = max(entry_search_start-.2, reached["t"]-5)
            for channel, curve in curves.items():
                selected = [dict(row,
                    distance_3d_m=math.dist(row["position"], target) if row["position"] is not None else None,
                    horizontal_distance_m=math.dist(row["position"][:2], target[:2]) if row["position"] is not None else None)
                    for row in curve if lower <= row["t_s"] <= transition["search_end_s"]]
                horizontal_entry = entry(selected, entry_search_start, verified["t"], 2.0)
                spatial_entry = entry(selected, entry_search_start, verified["t"], 2.0, False)
                spans = slow_spans(selected, reached["t"], transition["search_end_s"])
                first = spans[0] if spans else None
                stored = next(w for w in windows["truth" if channel == "SIM" else "observation"]
                              if w["agent_id"] == agent and w["phase"] == name)
                original_end = stored["end_s"]+mission_offset
                original_spans = slow_spans(selected, reached["t"], original_end)
                hold = phase["terminal_hold_s"]
                event_minus_hold = reached["t"]-hold
                record = dict(agent_id=agent, phase=name, semantic_phase=phase["semantic_phase"], channel=channel,
                    WPNAV_RADIUS_cm=parameters[agent].get("WPNAV_RADIUS"), terminal_hold_s=hold,
                    confirmation_dwell_s=scene["task_spec"]["execution"]["confirmation_dwell_s"],
                    confirmation_tolerance_m=scene["task_spec"]["execution"]["arrival_tolerance_m"],
                    onboard_terminal_CMD_records=terminal_cmds, onboard_terminal_CMD_Prm1_values=logged_holds,
                    configured_hold_matches_onboard_CMD=bool(logged_holds) and logged_holds==[phase["terminal_hold_s"]],
                    hold_interpretation="Prm1 is directly observed in the onboard CMD log; this diagnostic does not infer a specific firmware conversion function or treat configured fractional seconds as verified effective dwell.",
                    endpoint=target, terminal_event_s=reached["t"], task_target_verified_s=verified["t"],
                    target_verification_evidence={k:verified[k] for k in ("source_dwell_s", "tolerance_m", "position_error_m")},
                    endpoint_hold_start_proxy_s=event_minus_hold,
                    endpoint_hold_start_proxy_note="Terminal event RX minus CONFIGURED NAV hold, a counterfactual proxy only if onboard CMD disagrees. Not a logged firmware timer start; never assume a fractional hold was honored.",
                    entry_search_start_s=entry_search_start, horizontal_2m_entry=horizontal_entry, spatial_2m_entry=spatial_entry,
                    entry_to_terminal_event_s=reached["t"]-horizontal_entry["first_inside_s"] if horizontal_entry else None,
                    proxy_minus_2m_entry_s=event_minus_hold-horizontal_entry["first_inside_s"] if horizontal_entry else None,
                    transition=transition, first_sustained_horizontal_low_speed=first,
                    first_low_speed_context=position_stage(first["start_s"] if first else None, transition),
                    first_sustained_evidence_confirmed_context=position_stage(first["minimum_duration_confirmed_s"] if first else None, transition),
                    sustained_horizontal_low_speed_spans=spans,
                    original_arrival_source=stored["arrival_source"], original_arrival_s_run_relative=stored["arrival_s"]+mission_offset,
                    original_search_interval_s=[reached["t"], original_end],
                    sustained_low_speed_in_original_window=original_spans,
                    first_stop_after_original_window_s=first["start_s"]-original_end if first else None,
                    speeds_at_event_nearest_samples={label:min(selected, key=lambda row:abs(row["t_s"]-stamp))
                        for label,stamp in (("terminal_event", reached["t"]), ("target_verified", verified["t"]),
                                           ("transition_operation", transition["operation_started_s"]),
                                           ("mode_heartbeat", transition["first_mode_heartbeat_s"]))},
                    mode_heartbeat_timeline=[h for h in heartbeats if lower <= h["t_s"] <= transition["search_end_s"]],
                    speed_distance_curve=selected)
                records.append(record)
    complete = [row for row in records if "skipped" not in row]
    summary = {}
    for channel in ("SIM", "FCU"):
        rows = [r for r in complete if r["channel"] == channel]
        summary[channel] = dict(windows=len(rows), fallback_windows=sum(r["original_arrival_source"]=="trajectory_min_distance" for r in rows),
            low_speed_context_counts=dict(Counter(r["first_low_speed_context"] for r in rows)),
            interphase_context_counts=dict(Counter(r["first_low_speed_context"] for r in rows if r["transition"]["type"]=="next_phase_BRAKE")),
            original_windows_with_sustained_low_speed=sum(bool(r["sustained_low_speed_in_original_window"]) for r in rows),
            first_stop_after_original_window_count=sum(r["first_stop_after_original_window_s"] is not None and r["first_stop_after_original_window_s"]>0 for r in rows),
            configured_hold_onboard_CMD_mismatch_count=sum(not r["configured_hold_matches_onboard_CMD"] for r in rows),
            terminal_CMD_missing_count=sum(not r["onboard_terminal_CMD_records"] for r in rows),
            terminal_event_minus_2m_entry_range_s=[min(r["entry_to_terminal_event_s"] for r in rows if r["entry_to_terminal_event_s"] is not None),
                                                max(r["entry_to_terminal_event_s"] for r in rows if r["entry_to_terminal_event_s"] is not None)])
    return dict(run_id=metadata["run_id"], cohort="V06" if "v04_v06_" in str(run) else "V1_historical",
                run_directory=str(run.relative_to(PROJECT)),
                analysis_directory=str(analysis.relative_to(PROJECT)), clock_audits=audits, summary=summary, windows=records)


def fmt(value):
    return "—" if value is None else f"{value:.3f}" if isinstance(value, (float, int)) else str(value)


def summarize_cohorts(runs):
    results = {}
    for cohort in sorted(set(run.get("cohort", "skipped") for run in runs)):
        selected = [run for run in runs if run.get("cohort") == cohort and "skipped" not in run]
        windows = [row for run in selected for row in run["windows"] if "skipped" not in row]
        by_channel = {}
        for channel in ("SIM", "FCU"):
            rows = [row for row in windows if row["channel"] == channel]
            inter = [row for row in rows if row["transition"]["type"] == "next_phase_BRAKE"]
            final = [row for row in rows if row["transition"]["type"] == "final_LAND"]
            entry_deltas = [row["entry_to_terminal_event_s"] for row in rows if row["entry_to_terminal_event_s"] is not None]
            by_channel[channel] = dict(windows=len(rows), interphase_windows=len(inter), final_windows=len(final),
                interphase_low_speed_context=dict(Counter(row["first_low_speed_context"] for row in inter)),
                interphase_sustained_evidence_confirmed_context=dict(Counter(row["first_sustained_evidence_confirmed_context"] for row in inter)),
                final_low_speed_context=dict(Counter(row["first_low_speed_context"] for row in final)),
                original_windows_with_sustained_horizontal_low_speed=sum(bool(row["sustained_low_speed_in_original_window"]) for row in rows),
                configured_hold_values_s=sorted(set(row["terminal_hold_s"] for row in rows)),
                onboard_CMD_Prm1_values=sorted(set(value for row in rows for value in row["onboard_terminal_CMD_Prm1_values"])),
                onboard_CMD_missing=sum(not row["onboard_terminal_CMD_records"] for row in rows),
                terminal_event_minus_2m_entry_range_s=[min(entry_deltas), max(entry_deltas)] if entry_deltas else None)
        fcu, sim = by_channel["FCU"], by_channel["SIM"]
        fcu_brake = fcu["interphase_low_speed_context"].get("confirmed_BRAKE_before_next_AUTO", 0)
        sim_brake = sim["interphase_low_speed_context"].get("confirmed_BRAKE_before_next_AUTO", 0)
        conclusion = (f"{len(selected)} 次运行、每通道 {fcu['windows']} 个飞机×阶段窗口独立统计。阶段间窗口中，"
            f"FCU {fcu_brake}/{fcu['interphase_windows']}、SIM {sim_brake}/{sim['interphase_windows']} 的首次连续水平低速开始于已确认 BRAKE、下一 AUTO 请求标记之前；"
            f"SIM 的其他分类为 {sim['interphase_low_speed_context']}。这是低速区间的起点分类；≥0.2 s证据积累完成的分类另记在JSON，不能断言整段均处于BRAKE。"
            "这支持减速延续到阶段切换的解释，但不证明 BRAKE 是唯一原因。"
            f"最终阶段分类为 FCU {fcu['final_low_speed_context']}、SIM {sim['final_low_speed_context']}，不可称为BRAKE悬停或三维停稳。"
            f"配置 terminal_hold_s={fcu['configured_hold_values_s']}，实际末 NAV CMD Prm1={fcu['onboard_CMD_Prm1_values']}（缺失 {fcu['onboard_CMD_missing']}）。"
            "因此必须将配置驻留、机载CMD记录、外层1 m几何确认分开描述；不能断言进入2 m后真的计满配置的0.5 s。未改 arrival_s 或任何参数。")
        results[cohort] = dict(run_count=len(selected), by_channel=by_channel, conclusion=conclusion)
    return results


def markdown(report):
    lines = ["# arrival_s 与阶段切换的只读诊断", "", f"版本：`{VERSION}`。不改变 arrival_s、控制器、参数或任何验收判定。", "",
        "末航点 NAV 驻留与外层几何确认是两个环节：前者配置 terminal_hold_s；后者在 1 m 三维容差内连续 confirmation_dwell_s，但均没有由 Python 检查速度。WPNAV_RADIUS 从实测参数读出。特别要区分配置的 NAV 驻留与固件实际 CMD 记录：本诊断逐阶段读取 BIN CMD 的 Prm1；末点事件不是内部计时器开始消息，不能仅凭配置假定固件实际驻留了相同时间。", "",
        "下一阶段 upload() 先请求 BRAKE 并等待新 HEARTBEAT 确认，然后传航线；最终阶段直接 LAND。历史包未记录 SET_MODE TX，所以 upload_started/landing_started 到首个对应心跳仅是发送时刻的包含区间，心跳接收不是精确模式切换时刻。JSON另保留 BIN MODE 源时间及其被动映射时间，不能与精确TX混淆。", "",
        "SIM 为原 BIN SIM 全生命周期源位置（已导出 truth_source.csv）的差分速度，FCU 为 GLOBAL_POSITION_INT 速度；沿原 v3 全流去重和时钟模型独立对齐到 10 Hz。连续低速仅作诊断：水平速度≤0.3 m/s、连续样本跨度≥0.2 s，缺样断开。记录低速区间起点与0.2 s证据完成时刻，前者可能在BRAKE而后者已跨入AUTO。它不等于三维静止，特别是 LAND 期间。原 arrival_s 仍只需单个距离/速度同时合格样本。", "",
        "时间均为运行启动后的主机秒数。2 m 进入是采样区间估计；若 BIN CMD 与配置不一致，事件减配置驻留更不能解释为内部计时起点。数据只能检验时间关系，不能直接读取固件内部计时器或证明 BRAKE 是停止的唯一原因。", ""]
    for cohort, result in report["cohort_summary"].items():
        lines += [f"## {cohort} 结论", "", result["conclusion"], ""]
    for run in report["runs"]:
        lines += [f"## {run['run_id']}", ""]
        if "skipped" in run:
            lines += [run["skipped"], ""]
            continue
        lines += ["| 通道 | 窗口数 | arrival 兜底 | 原窗口内有连续低速 | 首次低速晚于原窗口 |", "|---|---:|---:|---:|---:|"]
        for channel, summary in run["summary"].items():
            lines.append(f"| {channel} | {summary['windows']} | {summary['fallback_windows']} | {summary['original_windows_with_sustained_low_speed']} | {summary['first_stop_after_original_window_count']} |")
        lines += ["", "| 通道/飞机/阶段 | 2 m进入 | 末点事件 | 几何确认 | 上传/LAND开始 | BRAKE/LAND心跳 | 下阶段AUTO标记 | 连续水平低速开始 | 位置关系 |", "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
        for row in run["windows"]:
            if "skipped" in row:
                continue
            transition, stop = row["transition"], row["first_sustained_horizontal_low_speed"]
            lines.append("| "+f"{row['channel']}/{row['agent_id']}/{row['phase']} | "+" | ".join(fmt(v) for v in (
                row["horizontal_2m_entry"]["first_inside_s"] if row["horizontal_2m_entry"] else None,
                row["terminal_event_s"], row["task_target_verified_s"], transition["operation_started_s"],
                transition["first_mode_heartbeat_s"], transition["next_AUTO_request_marker_s"],
                stop["start_s"] if stop else None, row["first_low_speed_context"]))+" |")
        lines += [""]
    lines += ["完整 JSON 包含逐窗口原 arrival_s、进入区间、事件减驻留代理、模式心跳、速度/距离曲线、连续低速区间、时钟模型及输入 SHA256。", "",
              f"输入文件 {len(report['source_sha256'])} 个，执行前后 SHA256 一致：{report['inputs_unchanged']}。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", action="append", default=[])
    parser.add_argument("--run", action="append", default=[])
    parser.add_argument("--output", default="tmp_v04/v06_20261002/arrival_brake_diagnostic")
    args = parser.parse_args()
    ledger_paths = [PROJECT/p for p in (args.ledger or [DEFAULT_LEDGER])]
    runs = [PROJECT/p for p in args.run]
    for path in ledger_paths:
        ledger = load(path)
        for row in ledger["records"]:
            if (row.get("validation_id") in ("V02", "V03", "V04", "V06") or path.name != "records.json") and row.get("run_directory"):
                runs.append(Path(row["run_directory"]))
    runs = sorted(set(path.resolve() for path in runs))
    if not runs:
        raise ValueError("no runs found")
    output = (PROJECT/args.output).resolve()
    if not output.is_relative_to(PROJECT/"tmp_v04"):
        raise ValueError("output must be under tmp_v04")
    paths = [output.with_suffix(".json"), output.with_suffix(".md")]
    if any(path.exists() for path in paths):
        raise FileExistsError("use a new output basename; old reports are immutable")
    sources = sorted(set([*ledger_paths, Path(__file__), PROJECT/"scripts/diagnose_v04_arrival_and_segments.py",
                          *list((PROJECT/"swarm_sim").glob("*.py")),
                          *(p for run in runs for p in run.rglob("*") if p.is_file())]))
    hashes = {str(path.relative_to(PROJECT)):digest(path) for path in sources}
    results = [analyze_run(run) for run in runs]
    changed = [str(path.relative_to(PROJECT)) for path in sources if digest(path) != hashes[str(path.relative_to(PROJECT))]]
    assert not changed, changed
    report = dict(version=VERSION, created_utc=datetime.now(timezone.utc).isoformat(), read_only=True, gate=False,
                  arrival_definition_unchanged=True, continuous_stop_diagnostic_only=True,
                  sampling_hz=10, low_horizontal_speed_threshold_m_s=.3, minimum_sampled_duration_s=.2,
                  source_sha256=hashes, inputs_unchanged=True, changed_inputs=[], runs=results)
    report["cohort_summary"] = summarize_cohorts(results)
    output.parent.mkdir(parents=True, exist_ok=True)
    for path, content in zip(paths, (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), markdown(report))):
        with path.open("x", encoding="utf-8") as stream:
            stream.write(content)
    print(json.dumps(dict(outputs=[str(p.relative_to(PROJECT)) for p in paths], run_count=len(results),
                         input_count=len(hashes), summary={r["run_id"]:r.get("summary", r.get("skipped")) for r in results}), ensure_ascii=False))


if __name__ == "__main__":
    main()
