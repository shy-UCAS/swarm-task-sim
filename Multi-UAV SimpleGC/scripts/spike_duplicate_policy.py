"""Explicit, fail-closed duplicate handling for WP-S offline review only."""

import json
import math

VERSION = "exact_duplicate_drop_v1"
KINDS = ("GLOBAL_POSITION_INT", "SYSTEM_TIME")


def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _membership(stamp, windows):
    if windows is None or not _finite(stamp):
        return None
    return any(start <= stamp <= end for start, end in windows)


def filter_exact_duplicates(packets, *, flight_window=None, observe_windows=None):
    """Retain first exact payload at a source tick; never hide clock failures.

    Compare every field of the message dictionary, including mavpackettype;
    receive time is deliberately not part of payload equality. JSON numeric
    representations remain type-sensitive (1 is not 1.0 or true). Source time
    must equal the current high-water tick: a late replay of an older tick is
    a rollback, even when its payload was seen previously. State is separate
    per (sysid, message kind). No window clipping is performed.

    Invalid timestamps, conflicts or receive-time reversal latch invalidity.
    Subsequent packets remain visible rather than being filtered to recover a
    timeline. Callers must propagate invalidity to the entire affected stream.
    """
    counts = {kind: dict(total=0, kept=0, exact_duplicates=0, dropped=0,
                        conflicts=0, rollbacks=0, invalid=0, host_errors=0,
                        timeline_invalid=False) for kind in KINDS}
    states, kept, details = {}, [], []
    for line, packet in enumerate(packets, 1):
        message = packet.get("message", {})
        kind = message.get("mavpackettype")
        if kind not in KINDS:
            kept.append(packet)
            continue
        stats = counts[kind]
        stats["total"] += 1
        key = (packet.get("sysid"), kind)
        state = states.setdefault(key, dict(source=None, payload=None, first_line=None,
                                            first_recv=None, host=None, invalid=False))
        source, host = message.get("time_boot_ms"), packet.get("recv_monotonic_s")
        valid = _finite(source) and source >= 0 and _finite(host) and host >= 0
        try:
            payload = json.dumps(message, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError):
            payload, valid = None, False
        host_backwards = _finite(host) and state["host"] is not None and host < state["host"]
        if host_backwards:
            stats["host_errors"] += 1
            state["invalid"] = True
        classification, drop = None, False
        if not valid:
            classification = "invalid_timestamp_or_payload"
            stats["invalid"] += 1
            state["invalid"] = True
        elif state["source"] is not None and source < state["source"]:
            classification = "time_rollback"
            stats["rollbacks"] += 1
            state["invalid"] = True
        elif state["source"] is not None and source == state["source"]:
            if payload == state["payload"]:
                classification = "exact_duplicate"
                stats["exact_duplicates"] += 1
                drop = not state["invalid"]
            else:
                classification = "same_time_conflict"
                stats["conflicts"] += 1
                state["invalid"] = True
        else:
            state.update(source=source, payload=payload, first_line=line, first_recv=host)
        if _finite(host):
            state["host"] = max(host, state["host"]) if state["host"] is not None else host
        if classification or host_backwards:
            details.append(dict(raw_line=line, kind=kind, sysid=packet.get("sysid"),
                                source_time_boot_ms=source, recv_monotonic_s=host,
                                first_line=state["first_line"], first_recv_monotonic_s=state["first_recv"],
                                classification=classification or "receive_time_rollback", dropped=drop,
                                host_time_rollback=host_backwards,
                                inside_flight_window=_membership(host, [flight_window] if flight_window else None),
                                inside_observe_window=_membership(host, observe_windows)))
        if drop:
            stats["dropped"] += 1
        else:
            kept.append(packet)
            stats["kept"] += 1
        stats["timeline_invalid"] |= state["invalid"]
    return kept, dict(version=VERSION, scope="WP-S offline metrics only; no window clipping",
                      equality="all message fields; type-sensitive canonical JSON; receive stamp excluded",
                      counts=counts, details=details,
                      dropped_count=sum(s["dropped"] for s in counts.values()))
