"""Append-only AC4 v2 acceptance evidence; never runs SITL or rewrites analyses."""
import argparse
import copy
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import verify_v04_v1 as legacy
from swarm_sim.ac4_timing import evaluate_ac4_timing
from swarm_sim.analysis import aligned_truth_samples, digest
from swarm_sim.observation_processing import prepare_v3_observations
from swarm_sim.recording import resample
from swarm_sim.route_planning import sample_route
from swarm_sim.route_windows import _speed_rows
from swarm_sim.truth import read_truth

VERSION = "ac4_relative_nominal_progress_v2"
ADAPTER_VERSION = "ac4_evidence_adapter_v1"
SPIKES = ("spike_v04_20261001T153235Z_5eddb7ae", "spike_v04_20261001T153806Z_42150c31")
PRIOR = ROOT / "verification/v04_v1_resume_20261002/records.json"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def guarded_tree(directory):
    return {str(path.resolve()): digest(path) for path in directory.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts}


def v3_channels(directory, metadata, scene):
    epoch = metadata["flight_epoch_monotonic_s"]
    end = metadata["mission_end_monotonic_s"]
    count = math.floor((end - epoch) * scene["record_hz"]) + 1
    # Same extra endpoint used by the production semantic-window analysis.
    # It is supported by raw samples; no extrapolation beyond recorded data.
    grid = [i / scene["record_hz"] for i in range(count + 1)]
    channels = {"truth": {}, "observation": {}}
    clocks, provenance = {}, {}
    for vehicle in scene["vehicles"]:
        agent = vehicle["id"]
        packets = lines(directory / "raw" / (agent + ".jsonl"))
        processed = prepare_v3_observations(packets, scene["origin"], metadata["quality_policy"], epoch, end)
        clocks[agent] = processed["clock_model"]
        channels["observation"][agent] = resample(processed["samples"], grid, scene["max_gap_s"])
        truth, _, info = read_truth(directory, agent, scene["origin"], preserve_invalid=True)
        channels["truth"][agent] = resample(aligned_truth_samples(truth, clocks[agent]), grid, scene["max_gap_s"])
        provenance[agent] = dict(clock_available=clocks[agent]["available"],
            timeline_error=processed["timeline_error"], truth=info,
            observation_processing_version="v3_observation_v1",
            duplicate_policy_version="exact_duplicate_drop_v1", timeline_policy_version="full_stream_strict_v1")
    return channels, clocks, epoch, provenance


def spike_channels(directory, metadata, scene, events):
    from scripts.spike_review_01 import read_review_channels
    from scripts.spike_route_metrics import phase_windows
    plan = read(directory / "spike_plan.json")
    windows = phase_windows(plan, events, metadata["elapsed_s"],
                            metadata["mission_end_monotonic_s"] - metadata["run_epoch_monotonic_s"])
    (observations, truth, clocks, provenance, _, errors, _), audits = read_review_channels(directory, scene, metadata, windows)
    if errors:
        raise ValueError("WP-S read-only trajectory evidence errors: " + str(errors))
    return {"observation": observations, "truth": truth}, clocks, metadata["run_epoch_monotonic_s"], dict(
        agents=provenance, duplicate_counts={a: r["dropped_count"] for a, r in audits.items()},
        observation_processing_version="wp_s_exact_duplicate_drop_v1_review")


def adapt_spike(directory, metadata, original_scene, events):
    """Reconstruct the unchanged uniform-speed model for a pre-v3 WP-S plan."""
    plan = read(directory / "spike_plan.json")
    # The approved v3 timing policy, unchanged; bind its source in the report.
    reference_path = ROOT / "verification/v04_v1_resume_20261002/plans/V02_r1.scene.json"
    reference = read(reference_path)
    tolerance = reference["planning"]["nominal_phase_timing"]["p00_approach"]["timing_tolerance"]
    scene = copy.deepcopy(original_scene)
    scene["phases"] = copy.deepcopy(plan["phases"])
    timing = {}
    execution = scene["task_spec"]["execution"]
    for phase in scene["phases"]:
        arrivals = {a: sample_route(phase["start_positions"][a], route, phase["speed_m_s"])[1]
                    for a, route in phase["routes"].items()}
        finish = {a: seq[-1] if seq else 0. for a, seq in arrivals.items()}
        duration = max(finish.values()) + phase["terminal_hold_s"] + execution["confirmation_dwell_s"]
        timing[phase["name"]] = dict(per_agent_waypoint_arrival_s=arrivals, per_agent_arrival_s=finish,
            duration_s=duration, tau_s=max(tolerance["min_s"], tolerance["fraction_of_phase"] * duration),
            timing_tolerance=tolerance, reconstruction="same bound uniform-speed distance/speed plus terminal hold and confirmation")
    scene["planning"] = dict(nominal_phase_timing=timing)
    # Spike raw MISSION_ITEM_REACHED receipt assignments were retained independently.
    adapted_events = list(events) + [dict(event="waypoint_reached", agent_id=e["agent_id"],
        phase=e["phase"], seq=e["seq"], t=e["t_s"], recv_monotonic_s=e["recv_monotonic_s"])
        for e in read(directory / "waypoint_events.json") if e.get("phase") is not None]
    return scene, adapted_events, dict(version="wp_s_nominal_model_reconstruction_v1",
        timing_policy_source=str(reference_path), timing_policy_sha256=digest(reference_path),
        policy=tolerance, historical_ac4_record_present=False, original_wp_s_verdict_unchanged=True)


def terminal_hover_evidence(scene, traces, events, metadata, epoch, channel, clocks):
    """Grant optional interval relaxation only to a measured stable terminal suffix.

    This is independent evidence, never an edit of arrival_s. No eligible suffix
    keeps the conservative singleton extension, not an automatic timing failure.
    """
    shift = metadata["run_epoch_monotonic_s"] - epoch
    releases = {e["phase"]: e["release_t"] + shift for e in events if e.get("event") == "phase_release_scheduled"}
    starts, evidence = {}, []
    for index, phase in enumerate(scene["phases"]):
        name = phase["name"]
        end = releases[scene["phases"][index + 1]["name"]] if index + 1 < len(scene["phases"]) else metadata["mission_end_monotonic_s"] - epoch
        starts[name] = {}
        for agent, route in phase["routes"].items():
            role = scene.get("semantic_plan", {}).get("execution_phases", {}).get(name, {}).get("agents", {}).get(agent, {})
            point = route[-1] if route else role.get("start_point", phase.get("start_positions", {}).get(agent))
            if not point:
                continue  # Core still requires no-op start/ready and full coverage.
            target = [point[k] for k in ("east_m", "north_m", "up_m")]
            rows, speed_version, _ = _speed_rows(traces[agent], channel, clocks.get(agent), scene["max_gap_s"])
            selected = [r for r in rows if releases[name] <= r[0] <= end]
            after = next((r for r in rows if r[0] >= end), None)
            end_supported = bool(after and after[1] is not None and after[2] is not None
                and after[2] <= .3 + 1e-8 and after[0] - end <= scene["max_gap_s"]
                and math.dist(after[1][:3], target) <= scene["task_spec"]["execution"]["arrival_tolerance_m"] + 1e-8)
            suffix = []
            for row in reversed(selected):
                t, position, speed, _ = row
                if (position is None or speed is None or speed > .3 + 1e-8
                        or math.dist(position[:3], target) > scene["task_spec"]["execution"]["arrival_tolerance_m"] + 1e-8):
                    break
                if suffix and suffix[-1][0] - t > scene["max_gap_s"]:
                    break
                suffix.append(row)
            duration = suffix[0][0] - suffix[-1][0] if suffix else 0.
            established = bool(end_supported and len(suffix) >= 2 and duration >= .2
                               and end - suffix[0][0] <= 1 / scene["record_hz"] + 1e-8)
            if not route:
                before = next((r for r in reversed(rows) if r[0] <= releases[name]), None)
                start_supported = bool(before and before[1] is not None and before[2] is not None
                    and before[2] <= .3 + 1e-8 and releases[name] - before[0] <= scene["max_gap_s"]
                    and math.dist(before[1][:3], target) <= scene["task_spec"]["execution"]["arrival_tolerance_m"] + 1e-8)
                established = bool(established and start_supported and len(suffix) == len(selected))
            if established:
                starts[name][agent] = suffix[-1][0] if route else releases[name]
            evidence.append(dict(phase=name, agent_id=agent, channel=channel,
                version="terminal_hover_measured_suffix_v1", speed_processing_version=speed_version,
                threshold_m_s=.3, distance_tolerance_m=scene["task_spec"]["execution"]["arrival_tolerance_m"],
                minimum_measured_duration_s=.2, measured_duration_s=duration, end_support_error_s=end-selected[-1][0] if selected else None,
                terminal_suffix_supported_through_end=end_supported,
                established=established, start_s=starts[name].get(agent),
                when_not_established="retain conservative terminal singleton; no arrival_s rewrite"))
    return starts, evidence


def evaluate_directory(directory, *, spike=False):
    directory = Path(directory).resolve()
    hashes = guarded_tree(directory)
    metadata, scene, events = read(directory / "metadata.json"), read(directory / "scenario.json"), lines(directory / "events.jsonl")
    adaptation = None
    if spike:
        channels, clocks, epoch, provenance = spike_channels(directory, metadata, scene, events)
        scene, events, adaptation = adapt_spike(directory, metadata, scene, events)
    else:
        channels, clocks, epoch, provenance = v3_channels(directory, metadata, scene)
    dependencies = [Path(__file__), ROOT / "swarm_sim/ac4_timing.py"]
    if spike:
        dependencies.extend(ROOT / "scripts" / name for name in
                            ("spike_review_01.py", "spike_route_metrics.py", "spike_duplicate_policy.py"))
        dependencies.append(Path(adaptation["timing_policy_source"]))
    hashes.update({str(p.resolve()): digest(p) for p in dependencies})
    reports, hover = {}, {}
    for channel, traces in channels.items():
        starts, hover[channel] = terminal_hover_evidence(scene, traces, events, metadata, epoch, channel, clocks)
        reports[channel] = evaluate_ac4_timing(scene, traces, events, metadata, epoch,
                                              channel=channel, terminal_hover_starts=starts)
    changed = [p for p, sha in hashes.items() if digest(Path(p)) != sha]
    return dict(acceptance_policy_version=VERSION, adapter_version=ADAPTER_VERSION,
        run_id=metadata["run_id"], run_directory=str(directory), channels=reports, hover_evidence=hover,
        truth_primary=True, observation_crosscheck=True, provenance=provenance,
        model_adaptation=adaptation, time_epoch_host_s=epoch, input_sha256=hashes,
        source_files_unchanged=not changed, changed_sources=changed,
        within_tau=reports["truth"]["within_tau"],
        crosscheck_within_tau=reports["observation"]["within_tau"],
        original_analysis_modified=False)


def verify_records_v2(path):
    report = legacy.verify_records(path)
    report["legacy_verification_version"] = report["version"]
    report["version"] = "v04_v1_independent_verification_v2"
    report["acceptance_policy_version"] = VERSION
    for row in report["records"]:
        row["criteria_v1_diagnostic"] = copy.deepcopy(row["criteria"])
        row["acceptance_policy_version"] = VERSION
        if not row["acceptance_criteria_applicable"]:
            continue
        timing = evaluate_directory(row["run_directory"])
        distance = row["truth_minimum_separation_m"]
        required = row["minimum_separation_required_m"]
        spatial = distance >= required if legacy.finite(distance) and legacy.finite(required) else None
        if spatial is True and row["truth_separation"].get("status") != "clear_observed":
            spatial = None
        row["ac4_v2"] = timing
        row["criteria"]["AC4"] = legacy.conjunction([spatial, timing["within_tau"]])
        row["criteria_status"]["AC4"] = legacy.status(row["criteria"]["AC4"])
        if not timing["source_files_unchanged"]:
            row["issues"].append("AC4 source changed")
        report["input_sha256"].update(timing["input_sha256"])
    route = [r for r in report["records"] if r["acceptance_criteria_applicable"]]
    report["observed_route_criteria"]["AC4"] = legacy.conjunction(r["criteria"]["AC4"] for r in route)
    value = report["observed_route_criteria"]["AC4"]
    report["final_route_criteria"]["AC4"] = value if value is False or report["ac1_pooled"]["matrix_complete"] else None
    for file in (Path(__file__), ROOT / "swarm_sim/ac4_timing.py"):
        report["input_sha256"][str(file.resolve())] = digest(file)
    report["changed_sources"] = [p for p, sha in report["input_sha256"].items() if digest(Path(p)) != sha]
    report["source_files_unchanged"] = not report["changed_sources"]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=PRIOR)
    parser.add_argument("--spikes", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify_records_v2(args.records)
    if args.spikes:
        report["wp_s_offline_reviews"] = [evaluate_directory(ROOT / "runs" / name, spike=True) for name in SPIKES]
    write_new(args.output, report)
    print(json.dumps(dict(output=str(args.output), acceptance_policy_version=VERSION,
        observed_route_criteria=report["observed_route_criteria"],
        runs=[dict(id=r["run_id"], validation=r["validation_id"], criteria=r["criteria_status"]) for r in report["records"]],
        spikes=[dict(id=r["run_id"], v2=r["within_tau"]) for r in report.get("wp_s_offline_reviews", [])])))


if __name__ == "__main__":
    main()
