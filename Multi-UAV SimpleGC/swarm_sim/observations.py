"""Shared GLOBAL_POSITION_INT decoding and per-message rejection accounting."""

import math

from .scenario import geo_to_enu


REASONS = ("missing_fields", "invalid_type", "non_finite", "invalid_timestamp", "position_out_of_bounds",
           "horizontal_speed_out_of_bounds", "vertical_speed_out_of_bounds")


def field(message, name):
    return message[name] if isinstance(message, dict) else getattr(message, name)


def finite_number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def decode_observation(message, origin, policy):
    """Return ENU position/velocity or one primary rejection reason, in fixed order."""
    try:
        lat, lon, alt, vx, vy, vz, boot = [field(message, k) for k in
                                          ("lat", "lon", "alt", "vx", "vy", "vz", "time_boot_ms")]
    except (KeyError, AttributeError):
        return None, "missing_fields"
    raw = [lat, lon, alt, vx, vy, vz, boot]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in raw):
        return None, "invalid_type"
    if not all(math.isfinite(v) for v in raw):
        return None, "non_finite"
    if boot < 0:
        return None, "invalid_timestamp"
    if not -900000000 <= lat <= 900000000 or not -1800000000 <= lon <= 1800000000:
        return None, "position_out_of_bounds"
    east, north, up = geo_to_enu(lat / 1e7, lon / 1e7, alt / 1000, origin)
    values = [east, north, up, vy / 100, vx / 100, -vz / 100]
    if (max(abs(east), abs(north)) > policy["horizontal_position_bound_m"] or
            not policy["min_up_m"] <= up <= policy["max_up_m"]):
        return None, "position_out_of_bounds"
    if math.hypot(values[3], values[4]) > policy["horizontal_velocity_sanity_m_s"]:
        return None, "horizontal_speed_out_of_bounds"
    if abs(values[5]) > policy["vertical_velocity_sanity_m_s"]:
        return None, "vertical_speed_out_of_bounds"
    return values, None


def live_observation(message, received, now, max_age, origin, policy):
    values, reason = decode_observation(message, origin, policy)
    # Snapshot receive time can be slightly later than the recorder's tick.
    if not finite_number(received) or received < 0:
        return None, timestamp_rejection(reason)
    if reason is None and now - received > max_age:
        return None, "stale"
    return values, reason


def timestamp_rejection(reason):
    """Merge a bad receive timestamp with content errors in the documented order."""
    if reason is None or REASONS.index(reason) > REASONS.index("invalid_timestamp"):
        return "invalid_timestamp"
    return reason


def new_counts():
    return dict(total_messages=0, accepted=0, rejected=0, dropped={reason: 0 for reason in REASONS})


class ObservationStream:
    """Counts raw packets once; timestamps survive invalid content as None barriers.

    Unplaceable timestamps or a clock reset invalidate the agent timeline rather
    than silently deleting records. Counts describe content acceptance separately.
    """
    def __init__(self, origin, policy, start, end):
        self.origin, self.policy = origin, policy
        self.start, self.end = start, end
        self.records = []
        self.timeline_error = None
        self.statistics = dict(message_type="GLOBAL_POSITION_INT", counting_unit="raw_message",
            rejection_reason_order=list(REASONS), primary_reason_only=True,
            whole_run=new_counts(), evaluation_window=new_counts(),
            evaluation_window_host_receive_s=[start, end])

    def append(self, packet):
        message = packet["message"]
        values, reason = decode_observation(message, self.origin, self.policy)
        host, boot = packet.get("recv_monotonic_s"), message.get("time_boot_ms")
        timestamps_ok = finite_number(host) and host >= 0 and finite_number(boot) and boot >= 0
        if not timestamps_ok:
            self.timeline_error = "unplaceable observation timestamp"
            reason = timestamp_rejection(reason)
            values = None
        scopes = [self.statistics["whole_run"]]
        if finite_number(host) and self.start <= host <= self.end:
            scopes.append(self.statistics["evaluation_window"])
        for counts in scopes:
            counts["total_messages"] += 1
            counts["accepted" if reason is None else "rejected"] += 1
            if reason is not None:
                counts["dropped"][reason] += 1
        if timestamps_ok:
            source = boot / 1000
            if self.records and (source <= self.records[-1][0] or host < self.records[-1][1]):
                self.timeline_error = "duplicate/nonmonotonic observation timestamps"
            self.records.append((source, host, values))

    def samples(self, model=None, epoch=0):
        if self.timeline_error:
            return []
        if model is not None and model.get("available"):
            from .truth import clock_to_host
            low, high = model["source_range_s"]
            return [(clock_to_host(source, model), values) for source, _, values in self.records if low <= source <= high]
        return [(host - epoch, values) for _, host, values in self.records]
