"""Read-only r1.2 approach diagnostics and intent/phase soft-gate distributions.

Input JSON: {"runs": [{"case_id": "VP1", "stage": "validation",
"run_directory": "...", "analysis_directory": "..."}]}. Every analysis is
explicit: never choose analysis_latest or launch/reanalyze a run. Write only a
new output directory. The output is a Pause 1 appendix, not its acceptance.
"""

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_sim.execution_metrics import distribution
from swarm_sim.generation import checked_path, file_hash

VERSION = "v05_r12_diagnostic_report_v1"
POLICY_VERSION = "v05_acceptance_r1_2"


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def bind(path, bindings):
    path = Path(path).resolve()
    actual = file_hash(path)
    if str(path) in bindings and bindings[str(path)] != actual:
        raise ValueError("input changed during reporting: " + str(path))
    bindings[str(path)] = actual
    return path


def summarize(values):
    values = list(values)
    return {**distribution(values), "expected_count": len(values),
            "unknown_count": sum(not finite(v) for v in values)}


def csv_rows(path):
    agents = defaultdict(list)
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            parsed = {"valid": row["valid"] == "1"}
            for key, value in row.items():
                if key not in ("agent_id", "valid", "time_basis"):
                    parsed[key] = float(value) if value else None
            agents[row["agent_id"]].append(parsed)
    return dict(agents)


def observed_departure(rows, window):
    """Diagnostic movement onset, distinct from AUTO acknowledgement time."""
    low, high = window.get("phase_release_s"), window.get("arrival_s")
    if not finite(low) or not finite(high) or high < low:
        return None
    start = previous = None
    for row in rows:
        t = row["t_s"]
        if t < low or t > high:
            continue
        velocity = [row.get("ve_m_s"), row.get("vn_m_s")]
        moving = row["valid"] and all(finite(v) for v in velocity) and math.hypot(*velocity) > .3
        if moving:
            if start is None or previous is None or t - previous > .15 + 1e-8:
                start = t
            if t - start >= .2 - 1e-8:
                return start
            previous = t
        else:
            start = previous = None
    return None


def measured_path(rows, window):
    """Sampled horizontal length; gaps produce an unknown, not a short path."""
    low, high = window.get("start_s"), window.get("arrival_s")
    if not finite(low) or not finite(high) or high < low:
        return None
    selected = [r for r in rows if low <= r["t_s"] <= high]
    if (len(selected) < 2 or selected[0]["t_s"] - low > .11 or high - selected[-1]["t_s"] > .11 or
            any(not r["valid"] or not all(finite(r.get(k)) for k in ("east_m", "north_m")) for r in selected) or
            any(b["t_s"] - a["t_s"] > .15 + 1e-8 for a, b in zip(selected, selected[1:]))):
        return None
    return sum(math.hypot(b["east_m"] - a["east_m"], b["north_m"] - a["north_m"])
               for a, b in zip(selected, selected[1:]))


def approach_rows(scene, windows, traces):
    out = []
    vehicles = {v["id"]: v for v in scene["vehicles"]}
    phases = scene["semantic_plan"]["execution_phases"]
    for phase, semantic in phases.items():
        if semantic.get("semantic_phase") != "approach":
            continue
        nominal = scene["planning"]["nominal_phase_timing"][phase]
        for agent, plan in semantic["agents"].items():
            start, end = plan["start_point"], plan["terminal_point"]
            de, dn = end["east_m"] - start["east_m"], end["north_m"] - start["north_m"]
            heading = vehicles[agent]["heading_deg"]
            bearing = math.degrees(math.atan2(de, dn)) % 360 if math.hypot(de, dn) > 0 else None
            turn = (bearing - heading + 180) % 360 - 180 if bearing is not None else None
            channels = {}
            for channel in ("truth", "observation"):
                candidates = [w for w in windows.get("channels", {}).get(channel, [])
                              if w["phase"] == phase and w["agent_id"] == agent]
                if len(candidates) != 1:
                    raise ValueError(f"missing/ambiguous approach window: {agent}/{channel}/{phase}")
                window = candidates[0]
                channels[channel] = {key: window.get(key) for key in
                                     ("start_s", "arrival_s", "arrival_source", "arrival_verified",
                                      "arrival_reason", "phase_release_s", "start_event", "chronology_valid")}
                channels[channel]["sampled_horizontal_path_length_m"] = measured_path(traces[channel].get(agent, []), window)
                if channel == "observation":
                    channels[channel]["motion_departure_s"] = observed_departure(traces[channel].get(agent, []), window)
            out.append(dict(agent_id=agent, phase=phase,
                            planned_path_length_m=nominal["per_agent_path_length_m"][agent],
                            nominal_motion_duration_s=nominal["per_agent_arrival_s"][agent],
                            nominal_completion_duration_s=nominal["per_agent_completion_s"][agent],
                            phase_nominal_duration_s=nominal["duration_s"],
                            initial_heading_deg=heading, entry_bearing_deg=bearing,
                            signed_shortest_turn_deg=turn, absolute_turn_deg=abs(turn) if turn is not None else None,
                            entry_point=end, start_point=start, channels=channels))
    return out


def phase_metrics(scene, windows, execution, ac4):
    rows = []
    records = execution.get("intermediate_waypoints", {}).get("records", [])
    per_agent = execution.get("thresholds", {}).get("0.3", {}).get("per_agent", {})
    for phase, semantic in scene["semantic_plan"]["execution_phases"].items():
        name = semantic["semantic_phase"]
        intermediate = [r for r in records if r.get("semantic_phase") == name]
        unknown = sum(r.get("stopped") is None for r in intermediate)
        stopped = sum(r.get("stopped") is True for r in intermediate)
        counts = {}
        for agent, metrics in per_agent.items():
            window = next((w for w in windows["windows"] if w["phase"] == phase and w["agent_id"] == agent), {})
            low, high = window.get("phase_release_s"), window.get("end_s")
            counts[agent] = (sum(low <= stop["start_s"] < high for stop in metrics.get("stops", []))
                             if metrics.get("evidence_complete") is True and finite(low) and finite(high) else None)
        timings = {}
        for channel in ("truth", "observation"):
            phase_timing = ac4.get("channels", {}).get(channel, {}).get("per_phase", {}).get(phase, {})
            primary = phase_timing.get("primary", {})
            timings[channel] = {key: primary.get(key) for key in ("D_s", "tau_s", "complete", "within_tau")}
            timings[channel]["per_agent_laps_observed"] = phase_timing.get("per_agent_laps_observed", {}) if name == "patrol" else {}
        rows.append(dict(phase=phase, semantic_phase=name,
                         AV1=dict(total_count=len(intermediate), stopped_count=stopped, unknown_count=unknown,
                                  stop_rate=stopped / len(intermediate) if intermediate and not unknown else None,
                                  applicable=bool(intermediate)),
                         AV2_stop_onset_count_by_agent=counts, AC4=timings))
    return rows


def read_run(entry, bindings):
    run = Path(entry["run_directory"]).resolve()
    analysis = Path(entry["analysis_directory"]).resolve()
    metadata = read(bind(run / "metadata.json", bindings))
    manifest = read(bind(analysis / "manifest.json", bindings))
    if metadata["run_id"] != manifest["run_id"]:
        raise ValueError("analysis/run identity mismatch")
    for name, expected in manifest["artifact_sha256"].items():
        if file_hash(bind(checked_path(analysis, name), bindings)) != expected:
            raise ValueError("analysis artifact hash mismatch: " + name)
    source_metadata = manifest.get("source_sha256", {}).get("metadata.json")
    if source_metadata is not None and source_metadata != file_hash(run / "metadata.json"):
        raise ValueError("analysis source metadata hash mismatch")
    quality = read(analysis / "quality.json")
    policy = quality.get("validation_policy", {})
    if policy.get("version") != POLICY_VERSION:
        raise ValueError("explicit r1.2 quality attachment required: " + str(analysis))
    scene = metadata["scenario"]
    windows = read(analysis / "phase_windows.json")
    execution = read(analysis / "execution_metrics.json")
    ac4 = read(analysis / "ac4_timing_v3.json")
    traces = {key: csv_rows(analysis / name) for key, name in
              (("truth", "truth.csv"), ("observation", "observations.csv"))}
    labels = read(analysis / "labels.json")
    return dict(case_id=entry.get("case_id"), stage=entry["stage"], run_id=metadata["run_id"],
                run_directory=str(run), analysis_directory=str(analysis),
                time_epoch_host_s=windows.get("time_epoch_host_s"),
                intent=scene["task_spec"]["mission"]["intent"], elapsed_s=metadata.get("elapsed_s"),
                episode_quality_eligible=quality.get("episode_quality_eligible"),
                mission_success=labels.get("mission_success"),
                semantic_consistency=labels.get("semantic_consistency"), validation_policy=policy,
                approach=approach_rows(scene, windows, traces),
                phase_metrics=phase_metrics(scene, windows, execution, ac4),
                AV2_episode=dict(limit=len(scene["phases"]) + 1,
                                 per_agent={a: m.get("stop_count") if m.get("evidence_complete") is True else None
                                            for a, m in execution.get("thresholds", {}).get("0.3", {}).get("per_agent", {}).items()}),
                execution_fractions={k: execution.get("thresholds", {}).get("0.3", {}).get(k)
                                     for k in ("stationary_time_fraction", "synchronized_time_fraction")})


def aggregate(runs):
    groups = defaultdict(list)
    for run in runs:
        for phase in run["phase_metrics"]:
            groups[(run["stage"], run["intent"], phase["semantic_phase"])].append((run, phase))
    result = []
    for (stage, intent, phase), rows in sorted(groups.items()):
        per_channel = {}
        for channel in ("truth", "observation"):
            timings = [p["AC4"][channel] for _, p in rows]
            laps = [v for t in timings for v in t["per_agent_laps_observed"].values()]
            per_channel[channel] = dict(
                D_s=summarize(t["D_s"] for t in timings), tau_s=summarize(t["tau_s"] for t in timings),
                D_exceeds_tau_count=sum(finite(t["D_s"]) and finite(t["tau_s"]) and t["D_s"] > t["tau_s"] for t in timings),
                timing_unknown_count=sum(not finite(t["D_s"]) or t["complete"] is not True for t in timings),
                lap_counts=summarize(laps), laps_unknown_count=sum(v is None for v in laps))
        result.append(dict(stage=stage, intent=intent, semantic_phase=phase, run_count=len(rows),
                           AV1=dict(stop_rate=summarize(p["AV1"]["stop_rate"] for _, p in rows if p["AV1"]["applicable"]),
                                    waypoint_count=sum(p["AV1"]["total_count"] for _, p in rows),
                                    stopped_count=sum(p["AV1"]["stopped_count"] for _, p in rows),
                                    unknown_count=sum(p["AV1"]["unknown_count"] for _, p in rows)),
                           AV2_stop_onset_count=summarize(v for _, p in rows for v in p["AV2_stop_onset_count_by_agent"].values()),
                           channels=per_channel))
    flags = Counter((r["stage"], r["intent"], f.get("phase"), f.get("channel"), f["code"], f["status"], f.get("source"))
                    for r in runs for f in r["validation_policy"]["soft_flags"])
    return dict(by_intent_and_phase=result, soft_flag_counts=[dict(stage=k[0], intent=k[1], phase=k[2], channel=k[3],
                code=k[4], status=k[5], source=k[6], count=v) for k, v in sorted(flags.items(), key=lambda kv: str(kv[0]))])


def markdown(report):
    out = ["# r1.2 进场与软门禁诊断附件", "", "本附件只读已有分析，不构成暂停 1 的完整验收。",
           "时间均为相对 `phase_windows.time_epoch_host_s` 的秒。出发事件是 AUTO 确认；运动出发另用 FCU 水平速度超过 0.3 m/s 且连续至少 0.2 s 的首样本定义。到达保留原窗口及兜底来源。", "",
           "| 运行 | 意图 | 飞机 | 规划航程 m | 名义运动 s | AUTO 出发 s | 运动出发 s | 到达 s（FCU / SIM） | 起始航向 / 方向 / 转角 ° |",
           "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |"]
    def fmt(value):
        return f"{value:.3f}" if finite(value) else "null"
    for run in report["runs"]:
        for row in run["approach"]:
            obs, truth = row["channels"]["observation"], row["channels"]["truth"]
            out.append(f"| {run['case_id'] or run['run_id']} | {run['intent']} | {row['agent_id']} | "
                       f"{fmt(row['planned_path_length_m'])} | {fmt(row['nominal_motion_duration_s'])} | "
                       f"{fmt(obs['start_s'])} | {fmt(obs['motion_departure_s'])} | "
                       f"{fmt(obs['arrival_s'])} / {fmt(truth['arrival_s'])} | "
                       f"{fmt(row['initial_heading_deg'])} / {fmt(row['entry_bearing_deg'])} / {fmt(row['absolute_turn_deg'])} |")
    out += ["", "## 按意图和阶段的软门禁分布", "", "| 组别 / 阶段 / 通道 | 运行数 | D 中位 / 最大 s | D 超限 / 未知 | 圈数未知 |", "| --- | ---: | --- | --- | ---: |"]
    for group in report["aggregate"]["by_intent_and_phase"]:
        for channel, timing in group["channels"].items():
            out.append(f"| {group['stage']} / {group['intent']} / {group['semantic_phase']} / {channel} | "
                       f"{group['run_count']} | {fmt(timing['D_s']['median'])} / {fmt(timing['D_s']['max'])} | "
                       f"{timing['D_exceeds_tau_count']} / {timing['timing_unknown_count']} | {timing['laps_unknown_count']} |")
    out += ["", "AV-1 的逐航点数量/停靠/未知及停靠率分布、AV-2 的逐阶段停靠起点计数与整段门槛、全部软标记和输入哈希见 `report.json`。AV-2 的阶段计数仅作分布，不另设阶段门槛。", ""]
    return "\n".join(out)


def build_report(specification, output):
    specification, output = Path(specification).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("output must be a new directory")
    bindings = {}
    entries = read(bind(specification, bindings))["runs"]
    if not entries:
        raise ValueError("no explicitly selected analyses")
    for entry in entries:
        for key in ("run_directory", "analysis_directory"):
            if output.is_relative_to(Path(entry[key]).resolve()):
                raise ValueError("report must be outside original run/analysis directories")
    runs = [read_run(e, bindings) for e in entries]
    identities = [(r["run_id"], r["analysis_directory"]) for r in runs]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate run/analysis selection")
    report = dict(version=VERSION, diagnostic_only=True, model_feature_eligible=False,
                  policy_version=POLICY_VERSION, runs=runs, aggregate=aggregate(runs),
                  definitions=dict(time_basis="seconds relative to each phase_windows.time_epoch_host_s; not UTC",
                    departure_event="phase_windows.start_s, actual phase_auto_confirmed host event",
                    motion_departure="first FCU horizontal speed >0.3 m/s sample in approach release-to-arrival window, sustained >=0.2 s; >0.15s gaps break evidence",
                    arrival="unchanged phase_windows.arrival_s and arrival_source/arrival_verified; fallback is not verified stationary arrival",
                    nominal_duration="planning.nominal_phase_timing.per_agent_arrival_s; completion includes confirmation dwell; phase max separately supplied",
                    planned_path="planning.nominal_phase_timing.per_agent_path_length_m",
                    sampled_path="horizontal adjacent valid 10Hz samples in [start_s,arrival_s], no extrapolation; gaps => null",
                    heading="configured 0 degrees, north=0 clockwise; bearing atan2(deltaEast,deltaNorth); signed shortest turn in [-180,180)",
                    AV2_phase="count stop starts in [phase_release_s,end_s); phase counts are diagnostic only; AV2 threshold applies to full episode",
                    unknown="nulls excluded from numeric quantiles and counted separately; no imputation"),
                  source_sha256=bindings)
    for name, expected in bindings.items():
        if file_hash(name) != expected:
            raise ValueError("input changed during report: " + name)
    output.mkdir(parents=True, exist_ok=False)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "report.md").write_text(markdown(report), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = build_report(args.input, args.output)
    print(json.dumps(dict(version=VERSION, run_count=len(result["runs"]), output=str(args.output.resolve())), ensure_ascii=False))


if __name__ == "__main__":
    main()
