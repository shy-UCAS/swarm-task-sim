"""Incremental host-clock samples plus conservative offline position resampling."""

import bisect
import csv
import json
import math
import threading
import time
from itertools import combinations

from .observations import ObservationStream, finite_number, live_observation
from .quality import policy_hash, resolve_policy


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


class Recorder:
    def __init__(self, directory, vehicles, origin, epoch, hz, max_age, quality_policy=None):
        self.directory, self.vehicles, self.origin = directory, vehicles, origin
        self.epoch, self.hz, self.max_age = epoch, hz, max_age
        self.policy = resolve_policy(quality_policy)
        self.stop = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, name="swarm-recorder", daemon=True)

    def start(self):
        self.thread.start()

    def _run(self):
        fields = ["t", "agent_id", "valid_position", "position_invalid_reason", "valid_attitude", "position_age_s",
                  "attitude_age_s", "position_boot_ms", "attitude_boot_ms", "east_m", "north_m", "up_m",
                  "ve_m_s", "vn_m_s", "vu_m_s", "lat", "lon", "alt_msl_m", "relative_alt_m",
                  "roll_rad", "pitch_rad", "yaw_rad", "p_rad_s", "q_rad_s", "r_rad_s", "armed", "mode"]
        try:
            with (self.directory / "samples.csv").open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fields)
                writer.writeheader()
                tick = time.perf_counter()
                flush_at = tick
                while not self.stop.is_set():
                    now = time.perf_counter()
                    if now < tick:
                        self.stop.wait(min(0.1, tick - now))
                        continue
                    for vehicle in self.vehicles:
                        state = vehicle.snapshot()
                        row = dict(t=now - self.epoch, agent_id=vehicle.id, valid_position=0, valid_attitude=0)
                        for kind, prefix in (("GLOBAL_POSITION_INT", "position"), ("ATTITUDE", "attitude")):
                            if kind not in state:
                                continue
                            received, message = state[kind]
                            age = now - received if finite_number(received) and received >= 0 else None
                            row[f"{prefix}_age_s"] = age if age is not None else ""
                            row[f"{prefix}_boot_ms"] = getattr(message, "time_boot_ms", "")
                            row[f"valid_{prefix}"] = int(age is not None and age <= self.max_age)
                            if prefix == "position":
                                values, reason = live_observation(message, received, now, self.max_age, self.origin, self.policy)
                                row["valid_position"] = int(values is not None)
                                row["position_invalid_reason"] = reason or ""
                                if values is None:
                                    continue
                            if age is None or age > self.max_age:
                                continue
                            if prefix == "position":
                                east, north, up = values[:3]
                                row.update(east_m=east, north_m=north, up_m=up, ve_m_s=message.vy / 100,
                                           vn_m_s=message.vx / 100, vu_m_s=-message.vz / 100,
                                           lat=message.lat / 1e7, lon=message.lon / 1e7,
                                           alt_msl_m=message.alt / 1000, relative_alt_m=message.relative_alt / 1000)
                            else:
                                row.update(roll_rad=message.roll, pitch_rad=message.pitch, yaw_rad=message.yaw,
                                           p_rad_s=message.rollspeed, q_rad_s=message.pitchspeed, r_rad_s=message.yawspeed)
                        if "HEARTBEAT" in state:
                            heartbeat = state["HEARTBEAT"][1]
                            row.update(armed=int(bool(heartbeat.base_mode & 128)), mode=heartbeat.custom_mode)
                        writer.writerow(row)
                    if now >= flush_at:
                        file.flush()
                        flush_at = now + 1
                    # Never manufacture a burst of backfilled samples after a scheduler delay.
                    tick = max(tick + 1 / self.hz, now + 0.001)
        except Exception as exc:
            self.error = exc

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)


def interpolate(samples, stamps, stamp, max_gap):
    index = bisect.bisect_left(stamps, stamp)
    if index < len(stamps) and abs(stamps[index] - stamp) < 1e-8:
        return samples[index][1]
    if index == 0 or index == len(stamps):
        return None
    a, b = samples[index - 1], samples[index]
    gap = b[0] - a[0]
    if a[1] is None or b[1] is None or gap <= 0 or gap > max_gap:
        return None
    weight = (stamp - a[0]) / gap
    return [x + weight * (y - x) for x, y in zip(a[1], b[1])]


def resample(samples, grid, max_gap):
    """Conservative mask also breaks unsafe spans between output grid ticks.

    A rejected packet at 0.05 s must break the 0.0 -> 0.1 s segment even when
    both grid endpoints coincide with good packets. No downstream dwell,
    coverage or distance validator may reconnect that interval.
    """
    stamps = [sample[0] for sample in samples]
    if any(b <= a for a, b in zip(stamps, stamps[1:])):
        return [(t, None) for t in grid]
    unsafe = [(a[0], b[0]) for a, b in zip(samples, samples[1:])
              if a[1] is None or b[1] is None or b[0] - a[0] > max_gap]
    result, cursor, previous = [], 0, None
    for t in grid:
        values = interpolate(samples, stamps, t, max_gap)
        if previous is not None:
            while cursor < len(unsafe) and unsafe[cursor][1] <= previous:
                cursor += 1
            if cursor < len(unsafe) and unsafe[cursor][0] < t and unsafe[cursor][1] > previous:
                values = None
        result.append((t, values))
        previous = t
    return result


def segment_distance(left0, right0, left1, right1):
    """Minimum distance under piecewise-linear relative motion within one interval."""
    r = [a - b for a, b in zip(left0[:3], right0[:3])]
    delta = [(a - b) - c for a, b, c in zip(left1[:3], right1[:3], r)]
    norm = sum(x * x for x in delta)
    fraction = max(0, min(1, -sum(a * b for a, b in zip(r, delta)) / norm)) if norm else 0
    return math.sqrt(sum((a + fraction * b) ** 2 for a, b in zip(r, delta)))


def export_dataset(directory, metadata, quality_policy=None):
    scenario = metadata["scenario"]
    policy = resolve_policy(quality_policy)
    epoch = metadata.get("flight_epoch_monotonic_s")
    end = metadata.get("mission_end_monotonic_s")
    if epoch is None or end is None or end <= epoch:
        return {"available": False, "reason": "no completed flight window"}
    data, filters, timeline_errors = {}, {}, {}
    for vehicle in scenario["vehicles"]:
        agent = vehicle["id"]
        stream = ObservationStream(scenario["origin"], policy, epoch, end)
        with (directory / "raw" / f"{agent}.jsonl").open(encoding="utf-8") as file:
            for line in file:
                packet = json.loads(line)
                message = packet["message"]
                if message.get("mavpackettype") == "GLOBAL_POSITION_INT":
                    stream.append(packet)
        data[agent] = stream.samples()
        filters[agent] = stream.statistics
        timeline_errors[agent] = stream.timeline_error
    ids = list(data)
    count = math.floor((end - epoch) * scenario["record_hz"]) + 1
    grid = [epoch + tick / scenario["record_hz"] for tick in range(count)]
    data = {agent: resample(samples, grid, scenario["max_gap_s"]) for agent, samples in data.items()}
    missing = {agent: 0 for agent in ids}
    minimum = None
    risk_intervals = 0
    previous = None
    with (directory / "processed.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["t", "agent_id", "valid", "east_m", "north_m", "up_m", "ve_m_s", "vn_m_s", "vu_m_s"])
        for tick in range(count):
            t = tick / scenario["record_hz"]
            row = {}
            for agent in ids:
                values = data[agent][tick][1]
                row[agent] = values
                missing[agent] += int(values is None)
                writer.writerow([t, agent, int(values is not None), *(values or [""] * 6)])
            for left, right in combinations(ids, 2):
                if row[left] is None or row[right] is None:
                    continue
                distance = math.dist(row[left][:3], row[right][:3])
                if previous and previous[left] is not None and previous[right] is not None:
                    distance = min(distance, segment_distance(previous[left], previous[right], row[left], row[right]))
                minimum = distance if minimum is None else min(minimum, distance)
                risk_intervals += int(distance < scenario["min_separation_m"])
            previous = row
    return dict(available=True, time_basis="host_receive_monotonic; not source-clock synchronized",
                frames=count, vehicles=len(ids), features=6, missing_by_agent=missing,
                valid_fraction={agent: 1 - missing[agent] / count for agent in ids},
                quality_policy=policy, quality_policy_sha256=policy_hash(policy),
                observation_filter=filters, observation_timeline_errors=timeline_errors,
                minimum_separation_m=minimum, collision_risk=bool(risk_intervals),
                risk_pair_intervals=risk_intervals,
                separation_check="piecewise-linear approximation; missing intervals unassessed")
