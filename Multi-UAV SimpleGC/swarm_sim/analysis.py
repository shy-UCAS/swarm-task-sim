"""Versioned offline exports; never overwrite original run evidence."""

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from . import __version__
from .evaluation import evaluate_task
from .recording import resample, segment_distance, write_json
from .observations import ObservationStream, finite_number
from .quality import eligibility, policy_hash, resolve_policy, summarize_clocks
from .tasks import validate_task_binding
from .truth import clock_to_host, fit_clock, percentile, read_truth, write_csv


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def assess_separation(traces, threshold):
    count = len(next(iter(traces.values()), []))
    minimum, unassessed, risks = None, 0, 0
    for left, right in combinations(traces, 2):
        for index in range(max(0, count - 1)):
            poses = [traces[agent][i][1] for i in (index, index + 1) for agent in (left, right)]
            if any(p is None for p in poses):
                unassessed += 1
                continue
            distance = segment_distance(*poses)
            minimum = distance if minimum is None else min(minimum, distance)
            risks += int(distance < threshold)
    status = "risk" if risks else ("unknown" if unassessed or (len(traces) > 1 and count < 2) else "clear_observed")
    return dict(status=status, minimum_m=minimum, unassessed_pair_intervals=unassessed, risk_pair_intervals=risks,
                method="piecewise-linear relative motion on passively aligned positions")


def analyze_run(directory, quality_policy=None):
    directory = Path(directory).resolve()
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    scene = metadata["scenario"]
    validate_task_binding(scene)
    policy = resolve_policy(quality_policy)
    epoch = metadata.get("flight_epoch_monotonic_s", metadata["run_epoch_monotonic_s"])
    end = metadata.get("mission_end_monotonic_s", metadata["run_epoch_monotonic_s"] + metadata["elapsed_s"])
    output = directory / ("analysis_v" + __version__.replace(".", "") + "_" +
                          datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8])
    output.mkdir()
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    traces, truth_traces, clocks, truth_info, parameters, source_hashes = {}, {}, {}, {}, {}, {}
    count = max(0, math.floor((end - epoch) * scene["record_hz"]) + 1)
    grid = [i / scene["record_hz"] for i in range(count)]
    observation_rows, truth_rows, error_rows = [], [], []
    raw_truth_rows = []
    estimate_errors = {}
    filters, timeline_errors = {}, {}
    for vehicle in scene["vehicles"]:
        agent = vehicle["id"]
        raw_path = directory / "raw" / f"{agent}.jsonl"
        pairs = []
        stream = ObservationStream(scene["origin"], policy, epoch, end)
        invalid_clock_messages = 0
        if raw_path.exists():
            source_hashes[str(raw_path.relative_to(directory))] = digest(raw_path)
            with raw_path.open(encoding="utf-8") as file:
                for line in file:
                    packet = json.loads(line)
                    message = packet["message"]
                    host = packet.get("recv_monotonic_s")
                    kind = message.get("mavpackettype")
                    if kind == "SYSTEM_TIME":
                        boot = message.get("time_boot_ms")
                        if not finite_number(host) or host < 0:
                            invalid_clock_messages += 1
                        elif epoch - 2 <= host <= end + 2:
                            if finite_number(boot) and boot >= 0:
                                pairs.append((boot / 1000, host - epoch))
                            else:
                                invalid_clock_messages += 1
                    elif kind == "GLOBAL_POSITION_INT":
                        stream.append(packet)
        model = fit_clock(pairs)
        model["invalid_clock_messages"] = invalid_clock_messages
        if invalid_clock_messages:
            model.update(available=False, reason="invalid clock message in fit evidence")
        clocks[agent] = model
        filters[agent], timeline_errors[agent] = stream.statistics, stream.timeline_error
        samples = stream.samples(model, epoch)
        basis = "passive_piecewise_source_clock_fit" if model["available"] else "host_receive_fallback"
        traces[agent] = resample(samples, grid, scene["max_gap_s"])
        for t, values in traces[agent]:
            observation_rows.append([t, agent, int(values is not None), basis, *(values or [""] * 6)])
        truth, params, info = read_truth(directory, agent, scene["origin"])
        truth_info[agent], parameters[agent] = info, params
        if "path" in info:
            source_hashes[info["path"]] = digest(directory / info["path"])
        for source, values in truth:
            raw_truth_rows.append([agent, source, *values])
        aligned_truth = []
        if model["available"]:
            aligned_truth = [(clock_to_host(source, model), values[:3]) for source, values in truth
                             if model["source_range_s"][0] <= source <= model["source_range_s"][1]]
        truth_traces[agent] = resample(aligned_truth, grid, scene["max_gap_s"])
        errors = []
        for (t, actual), (_, estimated) in zip(truth_traces[agent], traces[agent]):
            truth_rows.append([t, agent, int(actual is not None), *(actual or [""] * 3)])
            error = math.dist(actual, estimated[:3]) if actual is not None and estimated is not None else None
            if error is not None:
                errors.append(error)
            error_rows.append([t, agent, int(error is not None), error if error is not None else ""])
        estimate_errors[agent] = dict(samples=len(errors), rms_m=math.sqrt(sum(x * x for x in errors) / len(errors)) if errors else None,
                                      p95_m=percentile(errors, 0.95), max_m=max(errors) if errors else None)
    missing = {agent: sum(p is None for _, p in rows) for agent, rows in traces.items()}
    fraction = {agent: 1 - n / count if count else 0 for agent, n in missing.items()}
    truth_fraction = {agent: sum(p is not None for _, p in rows) / count if count else 0 for agent, rows in truth_traces.items()}
    observed_separation = assess_separation(traces, scene["min_separation_m"])
    actual_separation = assess_separation(truth_traces, scene["min_separation_m"])
    separation = observed_separation["status"]
    clock_quality = summarize_clocks(clocks, policy)
    clock_ok = clock_quality["overall"] in ("strict", "acceptable")
    context = {key: scene[key] for key in ("record_hz", "max_gap_s", "min_separation_m")}
    quality = dict(schema_version=2, frames=count, observation_valid_fraction=fraction,
                   truth_valid_fraction=truth_fraction, timing_diagnostic_pass=clock_ok,
                   clock_quality=clock_quality, quality_policy=policy, quality_policy_sha256=policy_hash(policy),
                   evaluation_context=context, observation_filter=filters, observation_timeline_errors=timeline_errors,
                   timing_residual_threshold_s=policy["clock_acceptable_p95_s"], minimum_separation_m=observed_separation["minimum_m"],
                   separation_status=separation, unassessed_pair_intervals=observed_separation["unassessed_pair_intervals"],
                   risk_pair_intervals=observed_separation["risk_pair_intervals"], truth_separation=actual_separation,
                   data_quality_pass=count > 0 and all(v >= policy["min_observation_valid_fraction"] for v in fraction.values()),
                   truth_available_pass=count > 0 and all(v >= policy["min_truth_valid_fraction"] for v in truth_fraction.values()),
                   run_completed=metadata["status"] == "completed", estimation_error=estimate_errors,
                   estimation_error_note="FCU vs BIN SIM source-time comparison; internal FCU filtering latency remains; passive fit is not absolute synchronization")
    labels = evaluate_task(scene, traces, events, metadata, epoch, clocks)
    quality.update(eligibility(quality, labels["mission_success"]))
    fields = ["t_s", "agent_id", "valid"]
    write_csv(output / "observations.csv", fields + ["time_basis", "east_m", "north_m", "up_m", "ve_m_s", "vn_m_s", "vu_m_s"], observation_rows)
    write_csv(output / "truth.csv", fields + ["east_m", "north_m", "up_m"], truth_rows)
    write_csv(output / "truth_source.csv", ["agent_id", "source_boot_s", "east_m", "north_m", "up_m", "qw", "qx", "qy", "qz"], raw_truth_rows)
    write_csv(output / "estimation_error.csv", fields + ["position_error_m"], error_rows)
    reference = [[i, phase["name"], agent, *[target[k] for k in ("east_m", "north_m", "up_m", "speed_m_s", "hold_s")]]
                 for i, phase in enumerate(scene["phases"]) for agent, target in phase["targets"].items()]
    write_csv(output / "reference_waypoints.csv", ["phase_index", "phase", "agent_id", "east_m", "north_m", "up_m", "speed_m_s", "hold_s"], reference)
    for name, value in (("task.json", scene.get("task_spec")), ("labels.json", labels), ("quality.json", quality),
                        ("clock_models.json", clocks), ("truth_provenance.json", truth_info), ("logged_parameters.json", parameters)):
        write_json(output / name, value)
    for filename in ("metadata.json", "scenario.json", "events.jsonl"):
        if (directory / filename).exists():
            source_hashes[filename] = digest(directory / filename)
    manifest = dict(schema_version=2, analysis_version=__version__, run_id=metadata["run_id"],
                    simulator_version=metadata.get("version"), analysis_schema_version=2,
                    quality_policy=policy, quality_policy_sha256=policy_hash(policy), evaluation_context=context,
                    scenario_id=scene["scenario_id"], family_id=scene.get("family_id"),
                    run_directory=str(directory), run_status=metadata["status"],
                    partial_window="mission_end_monotonic_s" not in metadata,
                    time_epoch_host_s=epoch, duration_s=end - epoch,
                    time_semantics="per-agent passive piecewise source-to-host-receive fit; affine trend and heldout residuals audited; fallback marked",
                    reference_semantics="event-driven waypoints, not a timed reference trajectory",
                    observation_contract="cooperative FCU telemetry with known identity; no radar/camera detection, occlusion, clutter or identity uncertainty",
                    source_sha256=source_hashes,
                    analysis_source_sha256={p.name: digest(p) for p in Path(__file__).parent.glob("*.py")},
                    benchmark_eligible=quality["benchmark_eligible"],
                    strict_benchmark_eligible=quality["strict_benchmark_eligible"], clock_quality=clock_quality)
    manifest["artifact_sha256"] = {p.name: digest(p) for p in output.iterdir() if p.is_file()}
    write_json(output / "manifest.json", manifest)
    write_json(directory / "analysis_latest.json", dict(directory=output.name, manifest_sha256=digest(output / "manifest.json")))
    return output, quality, labels
