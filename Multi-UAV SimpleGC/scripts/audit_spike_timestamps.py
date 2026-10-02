"""Read-only WP-S timestamp audit; never imports a simulator or production analysis.

Raw files are immutable evidence. The only writes are to a new output directory.
Primary categories are per (run, agent, message type) in JSONL receive order.
They use time_boot_ms, not host receive time or SYSTEM_TIME Unix time. A source
timestamp below the high-water mark is rollback even if its payload appeared
before; this prevents delayed old packets from being silently deduplicated.
"""

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
AUDIT_VERSION = "wp_s_timestamp_audit_v1"
TYPES = ("GLOBAL_POSITION_INT", "SYSTEM_TIME")
MANIFESTS = (
    "verification/v03_integration_20260930/dataset_final/dataset_manifest.json",
    "verification/v03_pilot_final_20260930/dataset/dataset_manifest.json",
)
SPIKES = ("runs/spike_v04_20261001T153235Z_5eddb7ae",
          "runs/spike_v04_20261001T153806Z_42150c31")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def valid_boot(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 2**32


def audit_packets(packets, epoch=None):
    """Classify mutually exclusive anomalies; retain first payload at high water.

    Host anomalies are independent supplementary counters. Missing/invalid values
    are explicit and do not advance the source high-water mark. Nonadjacent raw
    lines are compared within their message type, never across message types.
    """
    states = {kind: dict(counts=Counter(total=0, advancing=0, exact_duplicate=0,
              timestamp_conflict=0, rollback=0, invalid_source_timestamp=0,
              invalid_host_timestamp=0, host_equal=0, host_rollback=0,
              zero_unix_time=0, invalid_unix_time=0, unix_rollback=0),
              high=None, first=None, seen={}, host=None, unix=None) for kind in TYPES}
    anomalies = []
    for line_number, packet in enumerate(packets, 1):
        message = packet.get("message", {})
        kind = message.get("mavpackettype")
        if kind not in states:
            continue
        state = states[kind]
        counts = state["counts"]
        counts["total"] += 1
        host = packet.get("recv_monotonic_s")
        if not valid_number(host):
            counts["invalid_host_timestamp"] += 1
        else:
            if state["host"] is not None:
                counts["host_equal"] += host == state["host"]
                counts["host_rollback"] += host < state["host"]
            state["host"] = host
        if kind == "SYSTEM_TIME":
            unix = message.get("time_unix_usec")
            if not isinstance(unix, int) or isinstance(unix, bool) or unix < 0:
                counts["invalid_unix_time"] += 1
            elif unix == 0:
                counts["zero_unix_time"] += 1
            else:
                counts["unix_rollback"] += state["unix"] is not None and unix < state["unix"]
                state["unix"] = max(unix, state["unix"] or unix)
        source = message.get("time_boot_ms")
        if not valid_boot(source):
            category = "invalid_source_timestamp"
        elif state["high"] is not None and source < state["high"]:
            category = "rollback"
        elif source == state["high"]:
            category = "exact_duplicate" if message == state["first"]["message"] else "timestamp_conflict"
        else:
            category = "advancing"
            state["high"] = source
            state["first"] = dict(line_number=line_number, host=host, message=message)
        counts[category] += 1
        if category != "advancing":
            prior = state["seen"].get(source) if valid_boot(source) else None
            anomalies.append(dict(message_type=kind, category=category, line_number=line_number,
                source_time_boot_ms=source, recv_monotonic_s=host,
                recv_run_relative_s=host-epoch if valid_number(host) and valid_number(epoch) else None,
                high_water_time_boot_ms=state["high"],
                previous_same_source_line=prior["line_number"] if prior else None,
                previous_same_source_receive_s=prior["host"] if prior else None,
                previous_same_source_payload_equal=message == prior["message"] if prior else None,
                message=message))
        if valid_boot(source):
            state["seen"].setdefault(source, dict(line_number=line_number, host=host, message=message))
    return {kind: dict(state["counts"]) for kind, state in states.items()}, anomalies


def read_packets(path):
    with Path(path).open(encoding="utf-8-sig") as handle:
        for number, line in enumerate(handle, 1):
            try:
                packet = json.loads(line)
                if not isinstance(packet, dict) or not isinstance(packet.get("message"), dict):
                    raise ValueError("expected packet object with message object")
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{path}:{number}: invalid raw record: {exc}") from exc
            yield packet


def parameter_alignment(packets, events, metadata, agent, anomalies, source_matches):
    """Align observable RX/events; do not invent unrecorded request send times."""
    epoch = metadata["run_epoch_monotonic_s"]
    indexed = []
    invalid_indices = []
    acks = []
    versions = []
    for number, packet in enumerate(packets, 1):
        message = packet["message"]
        kind = message["mavpackettype"]
        t = packet["recv_monotonic_s"] - epoch
        if kind == "PARAM_VALUE":
            row = dict(line_number=number, t_s=t, index=message.get("param_index"),
                       name=message.get("param_id"), count=message.get("param_count"))
            if isinstance(row["index"], int) and 0 <= row["index"] < row["count"]:
                indexed.append(row)
            else:
                invalid_indices.append(row)
        elif kind == "COMMAND_ACK" and message.get("command") == 520:
            acks.append(dict(line_number=number, t_s=t, result=message.get("result")))
        elif kind == "AUTOPILOT_VERSION":
            versions.append(dict(line_number=number, t_s=t))
    completed = [event for event in events if event.get("agent_id") == agent and
                 event["event"] == "firmware_parameters_read"]
    connected = [event["t"] for event in events if event["event"] == "connected"]
    # In the hashed source, inspect runs only after every connect completes. An
    # unavailable AUTOPILOT_VERSION consumes a 10 s wait before request_list.
    # Thus this lower bound is conservative; it is NOT a measured TX timestamp.
    lower = max(connected) + 10 if connected and not versions and source_matches else None
    upper = indexed[0]["t_s"] if indexed else None
    completed_t = completed[0]["t"] if completed else None
    retry_excluded = (lower is not None and completed_t is not None and completed_t - lower < 5)
    tail = indexed[-1] if indexed else None
    near_tail = []
    if tail:
        for number, packet in enumerate(packets, 1):
            message = packet["message"]
            t = packet["recv_monotonic_s"] - epoch
            if message["mavpackettype"] in TYPES and abs(t-tail["t_s"]) <= 0.4:
                near_tail.append(dict(line_number=number, t_s=t,
                    message_type=message["mavpackettype"], time_boot_ms=message.get("time_boot_ms")))
    positioned = []
    for anomaly in anomalies:
        t = anomaly["recv_run_relative_s"]
        positioned.append(dict(anomaly,
            delta_last_indexed_parameter_s=t-tail["t_s"] if tail and t is not None else None,
            delta_readback_complete_s=t-completed_t if completed_t is not None and t is not None else None))
    # All timestamped message kinds at a duplicate GPI source sample are useful
    # evidence that the issue involves a telemetry batch, not just position.
    target_times = {a["source_time_boot_ms"] for a in anomalies
                    if a["message_type"] == "GLOBAL_POSITION_INT" and a["category"] == "exact_duplicate"}
    batches = []
    for source in sorted(target_times):
        rows = [(i+1, packet) for i, packet in enumerate(packets)
                if packet["message"].get("time_boot_ms") == source]
        by_kind = {}
        for number, packet in rows:
            by_kind.setdefault(packet["message"]["mavpackettype"], []).append((number, packet))
        batches.append(dict(time_boot_ms=source, messages={kind: dict(count=len(items),
            lines=[i for i, _ in items], all_fields_equal=all(p["message"] == items[0][1]["message"]
                for _, p in items)) for kind, items in by_kind.items()}))
    indices = Counter(row["index"] for row in indexed)
    return dict(agent_id=agent, request_send_times_recorded=False,
        request_send_times_s=None, missing_index_request_send_times_s=None,
        all_connected_t_s=max(connected) if connected else None, autopilot_520_ack=acks,
        autopilot_version_responses=versions,
        request_list_send_bound_s=[lower, upper] if lower is not None and upper is not None else None,
        request_list_bound_kind="control-flow lower bound and first-response upper bound, not measured TX",
        missing_index_retry_excluded_by_5s_control_flow=retry_excluded,
        exclusion_depends_on_recorded_source_hash_match=source_matches,
        readback_complete=completed,
        indexed_parameter_count=len(indexed), unique_index_count=len(indices),
        repeated_indices={str(k): v for k, v in indices.items() if v > 1},
        indexed_parameter_first=indexed[0] if indexed else None, indexed_parameter_last=tail,
        non_table_parameter_count=len(invalid_indices),
        non_table_parameter_index_counts=dict(Counter(row["index"] for row in invalid_indices)),
        nearby_telemetry=near_tail, anomalies=positioned, repeated_timestamp_batches=batches,
        causal_conclusion="association with full parameter-table completion; firmware/transport scheduling cause unproven")


def collect_runs(project):
    runs = []
    for relative in MANIFESTS:
        manifest_path = project / relative
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        for entry in manifest["episodes"]:
            runs.append(("v03", Path(entry["source_run"]), manifest_path))
    runs.extend(("spike", project / relative, None) for relative in SPIKES)
    if len(runs) != 17 or len({path.resolve() for _, path, _ in runs}) != 17:
        raise ValueError("expected 15 unique historical runs and 2 unique spike runs")
    return runs


def audit(project, output):
    project, output = Path(project).resolve(), Path(output).resolve()
    if not output.is_relative_to(project / "tmp_v04"):
        raise ValueError("audit output must be under this project's tmp_v04")
    output.mkdir(parents=True, exist_ok=False)
    rows, details, alignments, hashes = [], [], [], {}
    sources = (project / "scripts/spike_continuous_route.py", project / "swarm_sim/vehicle.py")
    for source in sources:
        hashes[str(source)] = sha256(source)
    for cohort, run, manifest_path in collect_runs(project):
        meta_path = run / "metadata.json"
        metadata = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        hashes[str(meta_path)] = sha256(meta_path)
        if manifest_path:
            hashes[str(manifest_path)] = sha256(manifest_path)
        event_path = run / "events.jsonl"
        events = [json.loads(line) for line in event_path.read_text(encoding="utf-8-sig").splitlines()]
        hashes[str(event_path)] = sha256(event_path)
        agents = [vehicle["id"] for vehicle in metadata["scenario"]["vehicles"]]
        matches = all(metadata.get("source_sha256", {}).get(str(source.relative_to(project)).replace("\\", "/"))
                      == hashes[str(source)] for source in sources)
        for agent in agents:
            raw = run / "raw" / f"{agent}.jsonl"
            hashes[str(raw)] = sha256(raw)
            packets = list(read_packets(raw)) if cohort == "spike" else read_packets(raw)
            counts, anomalies = audit_packets(packets, metadata.get("run_epoch_monotonic_s"))
            for kind in TYPES:
                rows.append(dict(cohort=cohort, run_id=metadata["run_id"], run_path=str(run),
                    agent_id=agent, message_type=kind, availability="present" if counts[kind]["total"] else "no_messages",
                    **counts[kind], raw_sha256=hashes[str(raw)]))
            details.extend(dict(cohort=cohort, run_id=metadata["run_id"], agent_id=agent,
                                raw_path=str(raw), **anomaly) for anomaly in anomalies)
            if cohort == "spike":
                alignment = parameter_alignment(packets, events, metadata, agent, anomalies, matches)
                alignments.append(dict(run_id=metadata["run_id"], run_path=str(run), **alignment))
    changed = [path for path, digest in hashes.items() if sha256(path) != digest]
    if changed:
        raise RuntimeError(f"source evidence changed while auditing: {changed}")
    with (output / "timestamp_counts.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    totals = {}
    keys = list(TYPES)
    for cohort in ("v03", "spike"):
        totals[cohort] = {kind: dict(sum((Counter({k: r[k] for k in r if isinstance(r[k], int)})
                             for r in rows if r["cohort"] == cohort and r["message_type"] == kind), Counter()))
                         for kind in keys}
    result = dict(audit_version=AUDIT_VERSION, created_utc=datetime.now(timezone.utc).isoformat(),
        source_time="time_boot_ms per run/agent/type; 0 boot ms is valid; SYSTEM_TIME Unix=0 is separately flagged unavailable",
        scope="entire raw capture, file receive order; primary categories mutually exclusive; rollback takes precedence over prior payload equality",
        comparison="all JSON message fields, excludes outer host receive time; interleaved types do not break adjacency within type",
        host_policy="host timestamp anomalies separately counted; never substitute host time for source time",
        raw_wire_limitation="JSON captures decoded payload and source sysid but no MAVLink packet sequence/component/wire bytes",
        runs=17, historical_runs=15, spike_runs=2, agent_run_count=len(rows)//2,
        no_message_streams=[{k:r[k] for k in ("run_id", "agent_id", "message_type")} for r in rows if r["total"] == 0],
        totals=totals, anomalies=details, parameter_alignment=alignments,
        source_hashes=hashes, source_hashes_unchanged_after_scan=True,
        audit_script_sha256=sha256(Path(__file__)), source_production_code_modified=False,
        simulator_started=False)
    with (output / "timestamp_diagnostics.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / "tmp_v04/spike_review_01/diagnostics")
    args = parser.parse_args(argv)
    result = audit(PROJECT, args.output)
    print(json.dumps({"runs": result["runs"], "agent_run_count": result["agent_run_count"],
                      "totals": result["totals"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
