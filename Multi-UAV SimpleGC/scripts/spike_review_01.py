"""Offline WP-S review on new copies only. This module never launches SITL."""

import argparse
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from scripts import spike_route_metrics as legacy
from scripts.spike_duplicate_policy import VERSION, filter_exact_duplicates
from scripts.spike_sim_speed_review import compute_sim_speed_review
from swarm_sim.observations import ObservationStream, finite_number
from swarm_sim.quality import resolve_policy, summarize_clocks
from swarm_sim.recording import resample, write_json
from swarm_sim.truth import fit_clock, read_truth

REVIEW_VERSION = "wp_s_offline_review_01"
RUN_NAMES = ("spike_v04_20261001T153235Z_5eddb7ae", "spike_v04_20261001T153806Z_42150c31")
METRIC_KEYS = ("S_a", "S_b", "S_c", "S_d", "S_e", "S_f", "S_g")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def tree_hashes(root):
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(Path(root).rglob("*")) if p.is_file()}


def read_review_channels(directory, scene, metadata, windows):
    """Versioned filtering in memory; copied raw bytes also remain immutable."""
    epoch, end = metadata["run_epoch_monotonic_s"], metadata["run_epoch_monotonic_s"] + metadata["elapsed_s"]
    policy = resolve_policy()
    grid = [i / scene["record_hz"] for i in range(math.ceil((end - epoch) * scene["record_hz"]) + 1)]
    observed, truth, clocks, provenance, raw_packets, errors, metrics, audits = {}, {}, {}, {}, {}, [], {}, {}
    flight = ((metadata["flight_epoch_monotonic_s"], metadata["mission_end_monotonic_s"])
              if "flight_epoch_monotonic_s" in metadata and "mission_end_monotonic_s" in metadata else None)
    for vehicle in scene["vehicles"]:
        agent = vehicle["id"]
        path = directory / "raw" / f"{agent}.jsonl"
        packets = legacy._lines(path) if path.exists() else []
        raw_packets[agent] = packets
        service = [(epoch+w["start_s"], epoch+w["end_s"]) for w in windows
                   if w["agent_id"] == agent and w["service_enabled"] and w["start_s"] is not None]
        retained, audit = filter_exact_duplicates(packets, flight_window=flight, observe_windows=service)
        audit.update(source=str(path), source_sha256=digest(path) if path.exists() else None)
        for detail in audit["details"]:
            host = detail["recv_monotonic_s"]
            detail["run_relative_s"] = host-epoch if finite_number(host) else None
        audits[agent] = audit
        stream, pairs = ObservationStream(scene["origin"], policy, epoch, end), []
        for packet in retained:
            message = packet["message"]
            if message.get("mavpackettype") == "GLOBAL_POSITION_INT":
                stream.append(packet)
            elif message.get("mavpackettype") == "SYSTEM_TIME":
                boot, host = message.get("time_boot_ms"), packet.get("recv_monotonic_s")
                pairs.append((boot/1000 if finite_number(boot) else None, host-epoch if finite_number(host) else None))
        if audit["counts"]["GLOBAL_POSITION_INT"]["timeline_invalid"]:
            stream.timeline_error = "exact_duplicate_drop_v1: conflicting/rollback/invalid observation timeline"
        model = fit_clock(pairs)
        if audit["counts"]["SYSTEM_TIME"]["timeline_invalid"]:
            model.update(available=False, reason="exact_duplicate_drop_v1: conflicting/rollback/invalid SYSTEM_TIME")
        clocks[agent] = model
        samples = stream.samples(model, epoch)
        observed[agent] = resample(samples, grid, scene["max_gap_s"])
        metrics[agent] = resample(samples, grid, min(scene["max_gap_s"], 1.5/scene["record_hz"]))
        try:
            actual, _, info = read_truth(directory, agent, scene["origin"], preserve_invalid=True)
        except Exception as exc:
            actual, info = [], dict(available=False, reason=f"{type(exc).__name__}: {exc}")
        truth[agent] = resample(legacy.aligned_truth_samples(actual, model), grid, scene["max_gap_s"])
        provenance[agent] = dict(info, observation_filter=stream.statistics, observation_timeline_error=stream.timeline_error,
                                observation_time_basis="passive_source_clock" if model.get("available") else "host_receive_fallback")
        if not packets:
            errors.append(f"{agent}: missing raw telemetry")
        if not info.get("available"):
            errors.append(f"{agent}: {info.get('reason', 'SIM truth missing')}")
        if stream.timeline_error:
            errors.append(f"{agent}: {stream.timeline_error}")
        if audit["counts"]["SYSTEM_TIME"]["timeline_invalid"]:
            errors.append(f"{agent}: invalid SYSTEM_TIME timeline")
    return (observed, truth, clocks, provenance, raw_packets, errors, metrics), audits


def compute_metrics(directory, policy_version):
    """Use the frozen WP-S geometry, windows and thresholds under either rule."""
    directory = Path(directory)
    scene, plan, metadata = (legacy._json(directory/name) for name in ("scenario.json", "spike_plan.json", "metadata.json"))
    if metadata.get("run_kind") != "wp_s_spike" or metadata["scenario"] != scene:
        raise ValueError("review requires a consistent WP-S copy")
    epoch, elapsed = metadata["run_epoch_monotonic_s"], metadata["elapsed_s"]
    events = legacy._lines(directory/"events.jsonl")
    end = metadata.get("mission_end_monotonic_s")
    windows = legacy.phase_windows(plan, events, elapsed, end-epoch if finite_number(end) else None)
    if policy_version == "strict_original_v1":
        channels, audits = legacy._read_channels(directory, scene, metadata), {}
    elif policy_version == VERSION:
        channels, audits = read_review_channels(directory, scene, metadata, windows)
    else:
        raise ValueError("unknown review policy")
    observed, truth, clocks, provenance, packets, errors, metric_traces = channels
    reached = legacy.assign_waypoint_events(packets, events, plan["phases"], epoch, elapsed)
    metrics = legacy.waypoint_metrics(plan, windows, metric_traces, reached, scene["record_hz"], scene["max_gap_s"])
    coverage = legacy._coverage(scene, observed, truth, windows, clocks)
    clock_quality = summarize_clocks(clocks, resolve_policy())
    clock_known = clock_quality["overall"] in ("strict", "acceptable")
    start, end = metadata.get("flight_epoch_monotonic_s"), metadata.get("mission_end_monotonic_s")
    separation = dict(status="unknown", minimum_m=None, reason="missing flight boundaries")
    if finite_number(start) and finite_number(end) and end > start:
        start, end = start-epoch, end-epoch
        grid = [start+i/scene["record_hz"] for i in range(math.floor((end-start)*scene["record_hz"])+1)]
        if not grid or grid[-1] < end-legacy.EPS:
            grid.append(end)
        separation = legacy.assess_separation({a: resample(rows, grid, scene["max_gap_s"]) for a, rows in truth.items()},
                                             scene["min_separation_m"])
        separation.update(start_s=start, end_s=end, scope="flight_epoch_to_mission_end")
    arrivals, uploads = [], []
    for phase in plan["phases"]:
        for index in range(max(len(route) for route in phase["routes"].values())):
            times = {r["agent_id"]: r["reached_t_s"] for r in metrics["waypoints"]
                     if r["phase"] == phase["name"] and r["route_index"] == index}
            complete = len(times) == len(scene["vehicles"]) and all(finite_number(t) for t in times.values())
            arrivals.append(dict(phase=phase["name"], route_index=index, seq=index+2, times_s=times,
                                 spread_s=max(times.values())-min(times.values()) if complete else None))
        for agent, route in phase["routes"].items():
            matches = [e for e in events if e.get("event") == "spike_phase_upload_end"
                       and e.get("phase") == phase["name"] and e.get("agent_id") == agent]
            record = matches[0] if len(matches) == 1 else {}
            duration = record.get("duration_s")
            complete = finite_number(duration) and duration >= 0 and record.get("mission_item_count") == len(route)+2
            uploads.append(dict(phase=phase["name"], agent_id=agent, nav_waypoint_count=len(route),
                                mission_item_count=len(route)+2, duration_s=duration if complete else None, complete=complete))
    rate = metrics["S_a"]["stop_rate"]
    coverage_known = clock_known and all(p.get("available") for p in provenance.values()) and all(v["evidence_complete"] for v in coverage.values())
    coverage_pass = (all(v["global_coverage_ratio"]+legacy.EPS >= .9 for v in coverage.values())
                     if coverage_known and all(w["complete_execution_window"] for w in windows) else None)
    separation_pass = (False if separation["status"] == "risk" else
                       True if separation["status"] == "clear_observed" and clock_known else None)
    execution_pass = metadata.get("status") == "completed" and all(u["complete"] for u in uploads) and all(w["complete_execution_window"] for w in windows)
    criteria = dict(intermediate_stop_rate=rate <= .1+legacy.EPS if rate is not None else None,
                    dual_channel_coverage=coverage_pass, truth_separation=separation_pass, execution_completed=execution_pass)
    previous = legacy._json(directory/"spike_metrics.json")
    result = dict(review_version=REVIEW_VERSION, duplicate_policy=policy_version, directory=str(directory.resolve()),
                  clock_quality=clock_quality, clock_models=clocks, truth_provenance=provenance, errors=errors,
                  phase_windows=windows, **metrics,
                  S_e=dict(channels=coverage, threshold=.9, baseline=previous["S_e"]["baseline"],
                           window_definition=previous["S_e"]["window_definition"]),
                  S_f=dict(truth_separation=separation, waypoint_arrival_spreads=arrivals,
                           spread_distribution_s=legacy.distribution([r["spread_s"] for r in arrivals])),
                  S_g=dict(uploads=uploads, duration_s=legacy.distribution([u["duration_s"] for u in uploads])),
                  criteria=criteria, verdict=legacy._verdict(criteria), duplicate_audit=audits,
                  no_new_sitl=True, production_path_modified=False)
    if policy_version == "strict_original_v1":
        differences = [key for key in (*METRIC_KEYS, "criteria", "verdict") if result[key] != previous[key]]
        result["matches_original_unknown_report"] = not differences
        result["original_comparison_differences"] = differences
        if differences:
            raise ValueError(f"strict replay differs from original result: {differences}")
    return result, (scene, plan, windows, clocks)


def run_review(output_root):
    root = Path(output_root).resolve()
    allowed = (PROJECT/"tmp_v04").resolve()
    if not root.is_relative_to(allowed) or root == allowed:
        raise ValueError("review output must be a fresh subdirectory of project tmp_v04")
    root.mkdir(parents=True, exist_ok=True)  # Independent read-only diagnostics may already exist here.
    copies = root/"inputs"
    outputs = root/"recomputed"
    if copies.exists() or outputs.exists():
        raise FileExistsError("review inputs/results already exist; choose a new review directory")
    originals = [PROJECT/"runs"/name for name in RUN_NAMES]
    guards = [PROJECT/"docs"/name for name in ("v04_spike_continuous_route.md", "v04_spike_summary.json", "v04_baseline_check.md")]
    guards += sorted((PROJECT/"swarm_sim").glob("*.py"))
    guards += [PROJECT/"scripts"/name for name in ("spike_continuous_route.py", "spike_route_metrics.py")]
    before = {str(p.relative_to(PROJECT)): digest(p) for p in guards}
    trees = {p.name: tree_hashes(p) for p in originals}
    write_json(root/"preservation_before.json", dict(files=before, runs=trees))
    copies.mkdir()
    outputs.mkdir()
    for source in originals:
        destination = copies/source.name
        shutil.copytree(source, destination)
        if tree_hashes(destination) != trees[source.name]:
            raise RuntimeError("copy differs from original evidence")
    results, rows = [], []
    try:
        for source in originals:
            copied = copies/source.name
            result_dir = outputs/source.name
            result_dir.mkdir()
            strict, _ = compute_metrics(copied, "strict_original_v1")
            write_json(result_dir/"strict_original_v1.json", strict)
            revised, context = compute_metrics(copied, VERSION)
            write_json(result_dir/(VERSION+".json"), revised)
            scene, plan, windows, clocks = context
            auxiliary = compute_sim_speed_review(copied, plan, windows, clocks)
            write_json(result_dir/"sim_position_speed_review.json", auxiliary)
            results.append(revised)
            rows.append(dict(run_id=source.name, strict={k: strict[k] for k in (*METRIC_KEYS, "criteria", "verdict")},
                             revised={k: revised[k] for k in (*METRIC_KEYS, "criteria", "verdict")},
                             duplicate_audit=revised["duplicate_audit"], sim_auxiliary=auxiliary,
                             strict_matches_original=strict["matches_original_unknown_report"]))
        summary = dict(review_version=REVIEW_VERSION, duplicate_policy=VERSION, runs=rows,
                       pooled=legacy.summarize_spikes(results), no_new_sitl=True,
                       source_and_copy_raw_bytes_unchanged=None,
                       code_sha256={p.relative_to(PROJECT).as_posix(): digest(p)
                                    for p in [Path(__file__), PROJECT/"scripts/spike_duplicate_policy.py",
                                              PROJECT/"scripts/spike_sim_speed_review.py", PROJECT/"scripts/spike_route_metrics.py"]})
    finally:
        after = {str(p.relative_to(PROJECT)): digest(p) for p in guards}
        after_trees = {p.name: tree_hashes(p) for p in originals}
        copy_trees = {p.name: tree_hashes(copies/p.name) for p in originals}
        preserved = before == after and trees == after_trees and trees == copy_trees
        write_json(root/"preservation_after.json", dict(files=after, runs=after_trees, copies=copy_trees, unchanged=preserved))
        if not preserved:
            raise RuntimeError("evidence preservation check failed")
    # Publish the preservation claim only after the comparison has succeeded.
    summary["source_and_copy_raw_bytes_unchanged"] = True
    write_json(root/"review_summary.json", summary)
    print(json.dumps(summary["pooled"], ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=PROJECT/"tmp_v04/spike_review_01")
    args = parser.parse_args()
    run_review(args.output_root)
