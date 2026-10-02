"""Read-only 7.5 arrival diagnostic for V01; never rewrite legacy windows.

Only the existing FCU observation grid is sampled. No interpolation, clock fit,
SIM substitution, planner trajectory synthesis, or new model feature is used.
The planned target supplies a distance reference, never a measured position.
"""

import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path


VERSION = "barrier_arrival_report_only_v1"
FEATURES = ("east_m", "north_m", "up_m", "ve_m_s", "vn_m_s", "vu_m_s")


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def distribution(values):
    values = sorted(value for value in values if finite(value))
    def quantile(fraction):
        if not values:
            return None
        offset = (len(values) - 1) * fraction
        left = int(offset)
        return values[left] + (values[min(left + 1, len(values) - 1)] - values[left]) * (offset - left)
    return dict(count=len(values), min=min(values) if values else None, p10=quantile(.1),
                median=quantile(.5), p90=quantile(.9), max=max(values) if values else None)


def load_fcu_grid(path, agents):
    """Retain original order, invalid rows and invalid timestamps as barriers."""
    traces = {agent: [] for agent in agents}
    if not path.is_file():
        return traces
    def number(value):
        try:
            value = float(value)
            return value if finite(value) else None
        except (TypeError, ValueError):
            return None
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            agent = row.get("agent_id")
            if agent in traces:
                values = [number(row.get(key)) for key in FEATURES]
                valid = row.get("valid") == "1" and all(finite(v) for v in values)
                traces[agent].append((number(row.get("t_s")), values if valid else None))
    return traces


def source_validity(agents, processing, clocks, quality):
    """Use the existing, hash-bound full-stream audit without changing its rule."""
    result = {}
    for agent in agents:
        audit = processing.get("per_agent", {}).get(agent, {})
        counts = audit.get("counts", {})
        reason = None
        if audit.get("timeline_policy_version") != "full_stream_strict_v1":
            reason = "full_stream_audit_missing_or_unsupported"
        elif any(counts.get(kind, {}).get("timeline_invalid") is not False
                 for kind in ("GLOBAL_POSITION_INT", "SYSTEM_TIME")):
            reason = "invalid_or_unknown_full_stream_source_timeline"
        elif clocks.get(agent, {}).get("available") is not True:
            reason = "source_clock_unavailable"
        elif agent not in quality.get("observation_timeline_errors", {}):
            reason = "observation_timeline_evidence_missing"
        elif quality["observation_timeline_errors"][agent] is not None:
            reason = "observation_timeline_invalid"
        result[agent] = dict(valid=reason is None, reason=reason,
                             evidence="hash-bound observation_processing + clock_models + quality full-stream audit")
    return result


def diagnose(scene, traces, events, metadata, time_epoch, sources):
    """Return sampled first joint-condition arrival or a labelled closest fallback.

    Each old execution phase is a separate target. Its search ends at the next
    scheduled phase release (or mission end for the final phase). Observations
    are never searched before the terminal raw-receive event. Missing or invalid
    stream/window evidence stays unknown; event-only fallback is not an arrival.
    """
    spec = scene.get("task_spec", {})
    mode = spec.get("execution", {}).get("control_mode")
    if mode != "waypoint_barrier_v1" or scene.get("schema_version") != 1:
        raise ValueError("report-only arrival diagnostic requires a bound barrier scene")
    tolerance = spec["execution"]["arrival_tolerance_m"]
    dt = 1 / scene["record_hz"]
    shift = metadata["run_epoch_monotonic_s"] - time_epoch
    mapping = scene.get("semantic_plan", {}).get("execution_phases", {})
    records = []
    phases = scene["phases"]
    for index, phase in enumerate(phases):
        name = phase["name"]
        if index + 1 < len(phases):
            releases = [e["release_t"] + shift for e in events
                        if e.get("event") == "phase_release_scheduled" and e.get("phase") == phases[index + 1]["name"]
                        and finite(e.get("release_t"))]
            end = releases[0] if len(releases) == 1 else None
            end_source = "next_phase_release"
        else:
            end = metadata["mission_end_monotonic_s"] - time_epoch if finite(metadata.get("mission_end_monotonic_s")) else None
            end_source = "mission_end"
        for vehicle in scene["vehicles"]:
            agent = vehicle["id"]
            starts = [e["t"] + shift for e in events if e.get("event") == "phase_auto_confirmed"
                      and e.get("phase") == name and e.get("agent_id") == agent and finite(e.get("t"))]
            start = starts[0] if len(starts) == 1 else None
            target = phase.get("targets", {}).get(agent, {})
            xyz = [target.get(key) for key in FEATURES[:3]]
            row = dict(agent_id=agent, phase=name, semantic_phase=mapping.get(name, {}).get("semantic_phase"),
                       start_s=start, end_s=end, end_source=end_source, arrival_s=None,
                       terminal_event_s=None, lag_s=None, arrival_source="unknown", arrival_verified=False,
                       unknown_reason=None, target=target, source_validity=sources.get(agent))
            records.append(row)
            if sources.get(agent, {}).get("valid") is not True:
                row["unknown_reason"] = sources.get(agent, {}).get("reason", "full_stream_validity_unknown")
                continue
            samples = traces.get(agent, [])
            if (not samples or any(not finite(t) for t, _ in samples)
                    or any(right[0] <= left[0] for left, right in zip(samples, samples[1:]))):
                row["unknown_reason"] = "missing_or_non_strict_exported_timeline"
                continue
            if start is None or end is None or end < start or not all(finite(value) for value in xyz):
                row["unknown_reason"] = "missing_or_invalid_phase_bounds_or_target"
                continue
            # Require the actual receive timestamp recorded by the single RX
            # owner; task_target_verified/phase_finished cannot anchor arrival.
            terminals = [event["recv_monotonic_s"] - time_epoch for event in events
                         if event.get("event") == "waypoint_reached" and event.get("phase") == name
                         and event.get("agent_id") == agent and type(event.get("seq")) is int and event["seq"] == 2
                         and event.get("terminal") is True and event.get("time_source") == "single_rx_host_receive"
                         and finite(event.get("recv_monotonic_s"))
                         and start <= event["recv_monotonic_s"] - time_epoch <= end]
            if not terminals:
                row["unknown_reason"] = "missing_raw_terminal_waypoint_event"
                continue
            terminal = min(terminals)
            row["terminal_event_s"] = terminal
            selected = [(t, values) for t, values in samples if terminal <= t <= end]
            complete = (bool(selected) and selected[0][0] - terminal <= 1.5 * dt + 1e-9
                        and end - selected[-1][0] <= 1.5 * dt + 1e-9
                        and all(values is not None and len(values) == 6 and all(finite(v) for v in values)
                                for _, values in selected)
                        and all(b[0] - a[0] <= 1.5 * dt + 1e-9 for a, b in zip(selected, selected[1:])))
            if not complete:
                row["unknown_reason"] = "missing_or_invalid_post_event_grid_evidence"
                continue
            stops = [(t, values) for t, values in selected
                     if math.dist(values[:3], xyz) <= tolerance + 1e-9 and math.hypot(*values[3:5]) <= .3 + 1e-9]
            if stops:
                row.update(arrival_s=stops[0][0], arrival_source="trajectory_stop", arrival_verified=True)
            else:
                nearest = min(selected, key=lambda item: (math.dist(item[1][:3], xyz), item[0]))
                row.update(arrival_s=nearest[0], arrival_source="trajectory_min_distance", arrival_verified=False)
            row["lag_s"] = terminal - row["arrival_s"]
    valid = [row for row in records if row["arrival_s"] is not None]
    return dict(version=VERSION, report_only=True, production_artifacts_changed=False,
                channel="FCU positions and reported horizontal velocity", units="s",
                source="independent sampled plan 7.5 diagnostic over existing observations.csv and raw receive events",
                difference_from_original="original barrier execution_metrics has no arrival_s; this report-only diagnostic does not replace it or its windows",
                limitation="per old execution phase, unlike route metrics per semantic phase; no interpolation; closest fallback does not prove a stop",
                lag_definition="raw terminal waypoint receive event_s minus independently sampled arrival_s",
                time_epoch_host_s=time_epoch, available=bool(valid), total_count=len(records), valid_count=len(valid),
                unknown_count=len(records) - len(valid), verified_stop_count=sum(row["arrival_verified"] for row in records),
                distribution=distribution(row["lag_s"] for row in valid), records=records)


def self_check():
    """Two hand calculations plus missing/full-stream-invalid negative evidence."""
    target = dict(east_m=2.0, north_m=0.0, up_m=1.0)
    scene = dict(schema_version=1, record_hz=10.0, vehicles=[dict(id="a")],
        task_spec=dict(execution=dict(control_mode="waypoint_barrier_v1", arrival_tolerance_m=.2)),
        phases=[dict(name="first", targets={"a": target}), dict(name="last", targets={"a": target})])
    metadata = dict(run_epoch_monotonic_s=100.0, mission_end_monotonic_s=102.0)
    events = [dict(event="phase_auto_confirmed", phase="first", agent_id="a", t=0.0),
              dict(event="waypoint_reached", phase="first", agent_id="a", t=.2,
                   recv_monotonic_s=100.2, seq=2, terminal=True, time_source="single_rx_host_receive"),
              dict(event="phase_release_scheduled", phase="last", release_t=1.0),
              dict(event="phase_auto_confirmed", phase="last", agent_id="a", t=1.0),
              dict(event="waypoint_reached", phase="last", agent_id="a", t=1.2,
                   recv_monotonic_s=101.2, seq=2, terminal=True, time_source="single_rx_host_receive")]
    # Explicit measured points are independent of any compiled route. First:
    # .2 too far, .3 too fast, .4 joint condition first. Last: speed stays 1,
    # nearest distance is at 1.5 -> unverified fallback. Lag = -.2 / -.3 s.
    positions = [1.9, 1.9, 1.7, 1.9, 1.9, 2.0, 2.0, 2.0, 2.0, 2.0, 1.7,
                 1.7, 1.7, 1.8, 1.9, 2.0, 1.9, 1.8, 1.7, 1.6, 1.5]
    speeds = [.0, .0, .1, .31, .3, .0, .0, .0, .0, .0, 1., 1., 1., 1., 1., 1., 1., 1., 1., 1., 1.]
    traces = {"a": [(i / 10, [x, 0., 1., speeds[i], 0., 0.]) for i, x in enumerate(positions)]}
    sources = {"a": dict(valid=True, reason=None)}
    measured = diagnose(scene, traces, events, metadata, 100.0, sources)
    first, last = measured["records"]
    checks = [dict(name="first_joint_condition", passed=first["arrival_s"] == .4
                   and abs(first["lag_s"] + .2) < 1e-8 and first["arrival_verified"] is True, actual=first),
              dict(name="post_event_nearest_fallback", passed=last["arrival_s"] == 1.5
                   and abs(last["lag_s"] + .3) < 1e-8 and last["arrival_verified"] is False, actual=last)]
    invalid = diagnose(scene, traces, events, metadata, 100.0, {"a": dict(valid=False, reason="source rollback outside task")})
    checks.append(dict(name="full_stream_invalid_stays_unknown", passed=invalid["valid_count"] == 0, actual=invalid))
    gap = copy.deepcopy(traces); gap["a"][3] = (.3, None)
    missing = diagnose(scene, gap, events, metadata, 100.0, sources)
    checks.append(dict(name="invalid_sample_cannot_prove_first_arrival", passed=missing["records"][0]["arrival_s"] is None, actual=missing))
    return dict(version=VERSION, new_sitl_runs=0, status="PASS" if all(c["passed"] for c in checks) else "FAIL", checks=checks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((Path(__file__).resolve().parents[1] / "tmp_v04").resolve()) or output.exists():
        parser.error("output must be a new directory under project/tmp_v04")
    result = self_check()
    result["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    (output / "barrier_arrival_self_check.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(output=str(output), status=result["status"], checks=len(result["checks"]), new_sitl_runs=0)))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
