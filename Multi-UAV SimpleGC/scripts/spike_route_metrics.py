"""WP-S diagnostics only; never export or relabel a production dataset.

All times in metric tables are host-monotonic seconds relative to run_epoch.
FCU/SIM positions use the existing passive SYSTEM_TIME mapping. That mapping
does not identify transport delay, so event lag is a receive-time diagnostic.
"""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swarm_sim.analysis import aligned_truth_samples, assess_separation
from swarm_sim.mission_evaluation import _evaluate_channel, _grid, _segment_distance, window_evidence
from swarm_sim.observations import ObservationStream, finite_number
from swarm_sim.quality import resolve_policy, summarize_clocks
from swarm_sim.recording import resample, write_json
from swarm_sim.truth import fit_clock, percentile, read_truth, write_csv

VERSION = "spike_route_metrics_v1"
EPS = 1e-8


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _lines(path):
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _xyz(point):
    return [point[k] for k in ("east_m", "north_m", "up_m")]


def distribution(values):
    values = [v for v in values if finite_number(v)]
    return dict(count=len(values), minimum=min(values) if values else None,
                p10=percentile(values, 0.1), median=percentile(values, 0.5),
                p90=percentile(values, 0.9), maximum=max(values) if values else None)


def stop_intervals(rows, target, max_gap_s, speed_threshold=0.3, minimum_duration=0.2):
    """Require every consecutive sample to be slow AND inside the 1 m disk.

    Duration is last timestamp minus first, with no extra sample-width credit.
    Invalid values, nonmonotonic time and sampling gaps break a stopped run.
    """
    intervals, start, previous = [], None, None
    for t, values in rows:
        valid = (values is not None and len(values) >= 5 and
                 all(finite_number(x) for x in [t, *values[:5]]))
        slow = (valid and math.hypot(values[3], values[4]) < speed_threshold and
                math.dist(values[:2], target[:2]) <= 1.0 + EPS)
        contiguous = previous is not None and EPS < t - previous <= max_gap_s + EPS
        if start is not None and (not slow or not contiguous):
            if previous - start + EPS >= minimum_duration:
                intervals.append([start, previous])
            start = None
        if slow and start is None:
            start = t
        previous = t
    if start is not None and previous - start + EPS >= minimum_duration:
        intervals.append([start, previous])
    return intervals


def assign_waypoint_events(packets_by_agent, events, phases, epoch, run_end):
    """Keep every raw receipt, including duplicates, non-NAV and unassigned.

    seq numbers restart at every upload. Assignment is agent/phase bounded by
    AUTO send and the next upload start, not by the later AUTO confirmation.
    """
    assigned = []
    for agent, packets in packets_by_agent.items():
        bounds = []
        uploads = [e["t"] for e in events if e.get("event") == "spike_phase_upload_start"
                   and e.get("agent_id") == agent and finite_number(e.get("t"))]
        for phase in phases:
            starts = [e["t"] for e in events if e.get("event") == "phase_start_sent"
                      and e.get("phase") == phase["name"] and e.get("agent_id") == agent
                      and finite_number(e.get("t"))]
            if len(starts) == 1:
                start = starts[0]
                bounds.append((phase["name"], start, min([t for t in uploads if t > start] or [run_end])))
        for packet in packets:
            msg = packet.get("message", {})
            if msg.get("mavpackettype") != "MISSION_ITEM_REACHED":
                continue
            host = packet.get("recv_monotonic_s")
            stamp = host - epoch if finite_number(host) else None
            matches = [name for name, start, end in bounds if stamp is not None and start <= stamp < end]
            assigned.append(dict(agent_id=agent, phase=matches[0] if len(matches) == 1 else None,
                                 seq=msg.get("seq"), t_s=stamp, recv_monotonic_s=host,
                                 assignment="unique_phase_interval" if len(matches) == 1 else "unassigned",
                                 source="raw_MISSION_ITEM_REACHED"))
    return assigned


def phase_windows(plan, events, run_end, mission_end=None):
    windows = []
    for phase in plan["phases"]:
        for agent in phase["routes"]:
            selected = [e for e in events if e.get("agent_id") == agent and e.get("phase") == phase["name"]]
            starts = [e["t"] for e in selected if e.get("event") == "phase_auto_confirmed" and finite_number(e.get("t"))]
            ends = [e["t"] for e in selected if e.get("event") == "task_target_verified" and finite_number(e.get("t"))]
            complete = len(starts) == 1 and len(ends) == 1 and starts[0] <= ends[0]
            start = starts[0] if len(starts) == 1 else None
            later_uploads = [e["t"] for e in events if e.get("event") == "spike_phase_upload_start"
                             and e.get("agent_id") == agent and e.get("phase") != phase["name"]
                             and finite_number(e.get("t")) and start is not None and e["t"] > start]
            later_motion = [e["t"] for e in events if e.get("event") == "phase_start_sent"
                            and e.get("agent_id") == agent and e.get("phase") != phase["name"]
                            and finite_number(e.get("t")) and start is not None and e["t"] > start]
            landing = [e["t"] for e in events if e.get("event") == "landing_started" and e.get("agent_id") == agent
                       and finite_number(e.get("t")) and start is not None and e["t"] > start]
            fallback = mission_end if finite_number(mission_end) else run_end
            end = min(later_uploads) if later_uploads else fallback
            physical_end = min(later_motion) if later_motion else min(landing) if landing else fallback
            complete = complete and start <= ends[0] <= physical_end
            windows.append(dict(agent_id=agent, phase=phase["name"], semantic_phase=phase["semantic_phase"],
                                role=phase["semantic_phase"], service_enabled=phase["semantic_phase"] == "observe",
                                start_s=start, end_s=end, diagnostic_end_s=physical_end,
                                coverage_end_event="next_upload_start" if later_uploads else "mission_end_or_run_end",
                                diagnostic_end_event="next_phase_start_sent" if later_motion else "landing_started" if landing else "mission_end_or_run_end",
                                confirmation_s=ends[0] if len(ends) == 1 else None,
                                complete_execution_window=complete))
    return windows


def waypoint_metrics(plan, windows, traces, reached, record_hz, max_gap_s):
    """S-a..S-d on observed FCU trajectories, independently of reached events."""
    rows, deviations = [], []
    # Match the corrected audit: at 10 Hz, >0.15 s breaks a stopped run.
    stop_gap = min(max_gap_s, 1.5 / record_hz)
    for phase in plan["phases"]:
        for agent, route in phase["routes"].items():
            window = next(w for w in windows if w["phase"] == phase["name"] and w["agent_id"] == agent)
            start, end = window["start_s"], window.get("diagnostic_end_s", window["end_s"])
            evidence = (window_evidence(traces.get(agent, []), start, end, max_gap_s)
                        if start is not None else dict(points=[], segments=[], complete=False))
            selected = [(t, p) for t, p in traces.get(agent, []) if start is not None and start <= t <= end]
            complete = window["complete_execution_window"] and evidence["complete"]
            polyline = [_xyz(phase["start_positions"][agent]), *map(_xyz, route)]
            offsets = [min(_segment_distance(p, a, b) for a, b in zip(polyline, polyline[1:]))
                       for _, p in evidence["points"]] if len(polyline) > 1 else []
            deviations.append(dict(phase=phase["name"], agent_id=agent,
                                   maximum_cross_track_m=max(offsets) if offsets else None,
                                   evidence_complete=complete,
                                   method="maximum at measured/clipped sample positions to planned horizontal polyline"))
            for index, target in enumerate(route):
                xyz, seq = _xyz(target), index + 2
                candidates = [(math.dist(p[:2], xyz[:2]), t) for t, p in evidence["points"]]
                for left, right, a, b in evidence["segments"]:
                    delta = [b[k] - a[k] for k in range(2)]
                    norm = sum(x*x for x in delta)
                    f = max(0., min(1., sum((xyz[k]-a[k])*delta[k] for k in range(2))/norm)) if norm else 0.
                    candidates.append((math.hypot(*(a[k] + f*delta[k]-xyz[k] for k in range(2))), left+f*(right-left)))
                nearest, nearest_t = min(candidates) if candidates else (None, None)
                speeds = [math.hypot(p[3], p[4]) for _, p in selected if p is not None and len(p) >= 5
                          and math.dist(p[:2], xyz[:2]) <= 2.0 + EPS]
                stops = stop_intervals(selected, xyz, stop_gap)
                matches = [e for e in reached if e["agent_id"] == agent and e["phase"] == phase["name"]
                           and e["seq"] == seq and finite_number(e["t_s"])]
                event_t = min(e["t_s"] for e in matches) if matches else None
                stopped = True if stops else (False if complete else None)
                rows.append(dict(phase=phase["name"], semantic_phase=phase["semantic_phase"], agent_id=agent,
                                 seq=seq, route_index=index, terminal=index == len(route)-1,
                                 east_m=xyz[0], north_m=xyz[1], stopped=stopped, stop_intervals_s=stops,
                                 minimum_speed_within_2m_m_s=min(speeds) if speeds else None,
                                 nearest_horizontal_m=nearest, nearest_t_s=nearest_t,
                                 reached_t_s=event_t, reached_event_count=len(matches),
                                 event_lag_s=event_t-nearest_t if event_t is not None and nearest_t is not None else None,
                                 evidence_complete=complete))
    intermediates = [r for r in rows if not r["terminal"]]
    unknown = sum(r["stopped"] is None for r in intermediates)
    stopped_count = sum(r["stopped"] is True for r in intermediates)
    return dict(waypoints=rows, cross_track=deviations,
                S_a=dict(stopped_count=stopped_count, intermediate_count=len(intermediates), unknown_count=unknown,
                         stop_rate=stopped_count/len(intermediates) if intermediates and not unknown else None,
                         threshold_speed_m_s=0.3, minimum_duration_s=0.2, radius_m=1.0, maximum_sample_gap_s=stop_gap),
                S_b=distribution([r["minimum_speed_within_2m_m_s"] for r in intermediates]),
                S_c=dict(nearest_horizontal_m=distribution([r["nearest_horizontal_m"] for r in intermediates]),
                         maximum_cross_track_m=distribution([r["maximum_cross_track_m"] for r in deviations])),
                S_d=distribution([r["event_lag_s"] for r in rows]))


def _read_channels(directory, scene, metadata):
    epoch = metadata["run_epoch_monotonic_s"]
    # Preserve post-confirmation evidence up to landing; individual diagnostic,
    # service and separation windows below clip this full recorded lifecycle.
    end = epoch + metadata["elapsed_s"]
    policy = resolve_policy()
    clocks, observed, truth, provenance, packets_by_agent, errors, metric_traces = {}, {}, {}, {}, {}, [], {}
    grid = [i / scene["record_hz"] for i in range(math.ceil((end-epoch)*scene["record_hz"])+1)]
    for vehicle in scene["vehicles"]:
        agent = vehicle["id"]
        path = directory / "raw" / f"{agent}.jsonl"
        packets = _lines(path) if path.exists() else []
        packets_by_agent[agent] = packets
        stream, pairs = ObservationStream(scene["origin"], policy, epoch, end), []
        for packet in packets:
            message = packet["message"]
            if message.get("mavpackettype") == "SYSTEM_TIME":
                boot, host = message.get("time_boot_ms"), packet.get("recv_monotonic_s")
                pairs.append((boot/1000 if finite_number(boot) else None,
                              host-epoch if finite_number(host) else None))
            elif message.get("mavpackettype") == "GLOBAL_POSITION_INT":
                stream.append(packet)
        model = fit_clock(pairs)
        clocks[agent] = model
        samples = stream.samples(model, epoch)
        observed[agent] = resample(samples, grid, scene["max_gap_s"])
        metric_traces[agent] = resample(samples, grid, min(scene["max_gap_s"], 1.5/scene["record_hz"]))
        try:
            actual, _, info = read_truth(directory, agent, scene["origin"], preserve_invalid=True)
        except Exception as exc:
            actual, info = [], dict(available=False, reason=f"{type(exc).__name__}: {exc}")
        provenance[agent] = dict(info, observation_filter=stream.statistics, observation_timeline_error=stream.timeline_error,
                                observation_time_basis="passive_source_clock" if model.get("available") else "host_receive_fallback")
        truth[agent] = resample(aligned_truth_samples(actual, model), grid, scene["max_gap_s"])
        if not packets:
            errors.append(f"{agent}: missing raw telemetry")
        if not info.get("available"):
            errors.append(f"{agent}: {info.get('reason', 'SIM truth missing')}")
        if stream.timeline_error:
            errors.append(f"{agent}: {stream.timeline_error}")
    return observed, truth, clocks, provenance, packets_by_agent, errors, metric_traces


def _coverage(scene, observed, truth, windows, clocks):
    spec, mission = scene["task_spec"], scene["task_spec"]["mission"]
    region = next(r for r in spec["scenario"]["regions"] if r["id"] == mission["target_region_id"])
    centers, grid = _grid(region, mission["observation_model"]["grid_m"])
    return {name: _evaluate_channel(scene, traces, windows, centers, grid, clocks)["coverage"]
            for name, traces in (("observation", observed), ("truth", truth))}


def _baseline(directory):
    if directory is None:
        return dict(available=False, reason="no baseline supplied")
    directory = Path(directory)
    if (directory / "analysis_latest.json").exists():
        directory = directory / _json(directory / "analysis_latest.json")["directory"]
    path = directory / "semantic_validation.json"
    if not path.exists():
        return dict(available=False, reason="baseline semantic_validation.json missing", directory=str(directory))
    report = _json(path)
    return dict(available=True, directory=str(directory), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                coverage={channel: report[channel]["coverage"]["global_coverage_ratio"] for channel in ("truth", "observation")})


def analyze_spike(directory, baseline_directory=None):
    """Analyze a NEW WP-S run; return report and write standalone diagnostics.

    Existing historical runs are never accepted without spike_plan.json, and no
    analysis_latest, labels, quality or dataset manifests are produced.
    """
    directory = Path(directory).resolve()
    scene, plan, metadata = (_json(directory/name) for name in ("scenario.json", "spike_plan.json", "metadata.json"))
    if plan.get("schema_version") != 1 or not plan.get("phases"):
        raise ValueError("expected WP-S spike_plan schema_version 1 with phases")
    if metadata.get("scenario") != scene:
        raise ValueError("scenario.json and metadata.scenario differ")
    epoch, elapsed = metadata["run_epoch_monotonic_s"], metadata["elapsed_s"]
    events = _lines(directory / "events.jsonl")
    observed, truth, clocks, provenance, packets, errors, metric_traces = _read_channels(directory, scene, metadata)
    reached = assign_waypoint_events(packets, events, plan["phases"], epoch, elapsed)
    mission_end = metadata.get("mission_end_monotonic_s")
    windows = phase_windows(plan, events, elapsed, mission_end-epoch if finite_number(mission_end) else None)
    metrics = waypoint_metrics(plan, windows, metric_traces, reached, scene["record_hz"], scene["max_gap_s"])
    coverage = _coverage(scene, observed, truth, windows, clocks)
    clock_quality = summarize_clocks(clocks, resolve_policy())
    clock_known = clock_quality["overall"] in ("strict", "acceptable")
    # Source mapping is required for cross-agent SIM distances; do not substitute FCU.
    flight_start = metadata.get("flight_epoch_monotonic_s")
    flight_end = metadata.get("mission_end_monotonic_s")
    separation = dict(status="unknown", minimum_m=None, reason="missing flight boundaries")
    if finite_number(flight_start) and finite_number(flight_end) and flight_end > flight_start:
        start, end = flight_start-epoch, flight_end-epoch
        local_grid = [start + i/scene["record_hz"] for i in range(math.floor((end-start)*scene["record_hz"])+1)]
        if not local_grid or local_grid[-1] < end-EPS:
            local_grid.append(end)
        separation = assess_separation({a: resample(rows, local_grid, scene["max_gap_s"]) for a, rows in truth.items()},
                                       scene["min_separation_m"])
        separation.update(start_s=start, end_s=end, scope="flight_epoch_to_mission_end")
    arrivals = []
    for phase in plan["phases"]:
        for index in range(max(len(route) for route in phase["routes"].values())):
            times = {r["agent_id"]: r["reached_t_s"] for r in metrics["waypoints"]
                     if r["phase"] == phase["name"] and r["route_index"] == index}
            available = len(times) == len(scene["vehicles"]) and all(finite_number(t) for t in times.values())
            arrivals.append(dict(phase=phase["name"], route_index=index, seq=index+2, times_s=times,
                                 spread_s=max(times.values())-min(times.values()) if available else None))
    uploads = []
    for phase in plan["phases"]:
        for agent, route in phase["routes"].items():
            matches = [e for e in events if e.get("event") == "spike_phase_upload_end"
                       and e.get("phase") == phase["name"] and e.get("agent_id") == agent]
            event = matches[0] if len(matches) == 1 else {}
            duration = event.get("duration_s")
            complete = (finite_number(duration) and duration >= 0 and event.get("mission_item_count") == len(route)+2)
            uploads.append(dict(phase=phase["name"], agent_id=agent, nav_waypoint_count=len(route),
                                mission_item_count=len(route)+2, duration_s=duration if complete else None,
                                complete=complete))
    rate = metrics["S_a"]["stop_rate"]
    coverage_known = (clock_known and all(provenance[a].get("available") for a in provenance)
                      and all(v["evidence_complete"] for v in coverage.values()))
    coverage_pass = (all(v["global_coverage_ratio"] + EPS >= 0.9 for v in coverage.values())
                     if coverage_known and all(w["complete_execution_window"] for w in windows) else None)
    separation_pass = (False if separation["status"] == "risk" else
                       True if separation["status"] == "clear_observed" and clock_known else None)
    execution_pass = (metadata.get("status") == "completed" and all(u["complete"] for u in uploads)
                      and all(w["complete_execution_window"] for w in windows))
    criteria = dict(intermediate_stop_rate=rate <= 0.1 + EPS if rate is not None else None,
                    dual_channel_coverage=coverage_pass, truth_separation=separation_pass,
                    execution_completed=execution_pass)
    result = dict(schema_version=1, metrics_version=VERSION, directory=str(directory),
                  status="diagnostic_only_not_a_production_dataset", time_epoch_host_s=epoch,
                  time_semantics="passive source-to-host-receive mapping; no absolute synchronization guarantee",
                  event_lag_semantics="raw event receive time minus closest horizontal piecewise-linear position time",
                  errors=errors, clock_quality=clock_quality, clock_models=clocks, truth_provenance=provenance,
                  phase_windows=windows, **metrics,
                  S_e=dict(channels=coverage, threshold=0.9, baseline=_baseline(baseline_directory),
                           window_definition="AUTO confirmation through next upload start; includes terminal barrier wait, excludes upload; WP-S diagnostic only"),
                  S_f=dict(truth_separation=separation, waypoint_arrival_spreads=arrivals,
                           spread_distribution_s=distribution([r["spread_s"] for r in arrivals])),
                  S_g=dict(uploads=uploads, duration_s=distribution([u["duration_s"] for u in uploads])),
                  criteria=criteria, verdict=_verdict(criteria), gate=dict(criteria=criteria, verdict=_verdict(criteria)))
    sources = [directory/name for name in ("scenario.json", "spike_plan.json", "metadata.json", "events.jsonl", "samples.csv", "firmware_parameters.json")]
    sources += list((directory/"raw").glob("*.jsonl")) + list((directory/"sitl").glob("*/logs/*.BIN"))
    result["source_sha256"] = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources if p.is_file()}
    code_paths = [Path(__file__).resolve(), *sorted((Path(__file__).resolve().parents[1]/"swarm_sim").glob("*.py"))]
    result["analysis_source_sha256"] = {str(p.relative_to(Path(__file__).resolve().parents[1])): hashlib.sha256(p.read_bytes()).hexdigest() for p in code_paths}
    write_json(directory/"spike_metrics.json", result)
    write_json(directory/"waypoint_events.json", reached)
    event_fields = ["agent_id", "phase", "seq", "t_s", "recv_monotonic_s", "assignment", "source"]
    write_csv(directory/"waypoint_events.csv", event_fields, [[r.get(k) for k in event_fields] for r in reached])
    fields = ["phase", "semantic_phase", "agent_id", "seq", "route_index", "terminal", "east_m", "north_m", "stopped",
              "minimum_speed_within_2m_m_s", "nearest_horizontal_m", "nearest_t_s", "reached_t_s", "event_lag_s", "reached_event_count", "evidence_complete"]
    write_csv(directory/"spike_waypoints.csv", fields, [[r.get(k) for k in fields] for r in metrics["waypoints"]])
    return result


def _verdict(criteria):
    return "NO-GO" if False in criteria.values() else ("UNKNOWN" if None in criteria.values() else "GO")


def summarize_spikes(results):
    """Pool the two ORIGINAL repeat runs; an overshoot run is reported separately."""
    total = sum(r["S_a"]["intermediate_count"] for r in results)
    stopped = sum(r["S_a"]["stopped_count"] for r in results)
    unknown = sum(r["S_a"]["unknown_count"] for r in results)
    rate = stopped/total if total and not unknown else None
    def all_known(name):
        values = [r["criteria"][name] for r in results]
        return False if False in values else None if None in values else True
    criteria = dict(two_original_runs=len(results) == 2,
                    intermediate_stop_rate=rate <= 0.1 + EPS if rate is not None else None,
                    dual_channel_coverage=all_known("dual_channel_coverage"),
                    truth_separation=all_known("truth_separation"), execution_completed=all_known("execution_completed"))
    return dict(run_count=len(results), stopped_count=stopped, intermediate_count=total, unknown_count=unknown,
                pooled_stop_rate=rate, criteria=criteria, verdict=_verdict(criteria))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--baseline-directory", type=Path)
    args = parser.parse_args()
    report = analyze_spike(args.directory, args.baseline_directory)
    print(json.dumps(dict(directory=str(args.directory), verdict=report["verdict"], criteria=report["criteria"]), indent=2))
