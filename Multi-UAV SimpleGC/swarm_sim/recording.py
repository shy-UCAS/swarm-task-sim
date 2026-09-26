"""Incremental host-clock samples plus conservative offline position resampling."""

import bisect
import csv
import json
import math
import threading
import time
from itertools import combinations

from .scenario import geo_to_enu


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


class Recorder:
    def __init__(self, directory, vehicles, origin, epoch, hz, max_age):
        self.directory, self.vehicles, self.origin = directory, vehicles, origin
        self.epoch, self.hz, self.max_age = epoch, hz, max_age
        self.stop = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, name="swarm-recorder", daemon=True)

    def start(self):
        self.thread.start()

    def _run(self):
        fields = ["t", "agent_id", "valid_position", "valid_attitude", "position_age_s",
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
                            age = now - received
                            row[f"{prefix}_age_s"] = age
                            row[f"{prefix}_boot_ms"] = message.time_boot_ms
                            row[f"valid_{prefix}"] = int(age <= self.max_age)
                            if age > self.max_age:
                                continue
                            if prefix == "position":
                                east, north, up = geo_to_enu(message.lat / 1e7, message.lon / 1e7,
                                                            message.alt / 1000, self.origin)
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
    if gap <= 0 or gap > max_gap:
        return None
    weight = (stamp - a[0]) / gap
    return [x + weight * (y - x) for x, y in zip(a[1], b[1])]


def segment_distance(left0, right0, left1, right1):
    """Minimum distance under piecewise-linear relative motion within one interval."""
    r = [a - b for a, b in zip(left0[:3], right0[:3])]
    delta = [(a - b) - c for a, b, c in zip(left1[:3], right1[:3], r)]
    norm = sum(x * x for x in delta)
    fraction = max(0, min(1, -sum(a * b for a, b in zip(r, delta)) / norm)) if norm else 0
    return math.sqrt(sum((a + fraction * b) ** 2 for a, b in zip(r, delta)))


def export_dataset(directory, metadata):
    scenario = metadata["scenario"]
    epoch = metadata.get("flight_epoch_monotonic_s")
    end = metadata.get("mission_end_monotonic_s")
    if epoch is None or end is None or end <= epoch:
        return {"available": False, "reason": "no completed flight window"}
    data, stamps = {}, {}
    dropped_unreasonable = {agent: 0 for agent in (v["id"] for v in scenario["vehicles"])}
    for vehicle in scenario["vehicles"]:
        agent = vehicle["id"]
        samples = []
        with (directory / "raw" / f"{agent}.jsonl").open(encoding="utf-8") as file:
            for line in file:
                packet = json.loads(line)
                message = packet["message"]
                if message.get("mavpackettype") == "GLOBAL_POSITION_INT":
                    enu = geo_to_enu(message["lat"] / 1e7, message["lon"] / 1e7,
                                     message["alt"] / 1000, scenario["origin"])
                    velocities = [message["vy"] / 100, message["vx"] / 100, -message["vz"] / 100]
                    # Deep defense: reject physically unreasonable velocities
                    horizontal_speed = math.sqrt(velocities[0]**2 + velocities[1]**2)
                    if horizontal_speed > 50 or abs(velocities[2]) > 30:
                        dropped_unreasonable[agent] += 1
                        continue
                    samples.append((packet["recv_monotonic_s"], [*enu, *velocities]))
        data[agent] = samples
        stamps[agent] = [s[0] for s in samples]
    ids = list(data)
    count = math.floor((end - epoch) * scenario["record_hz"]) + 1
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
                values = interpolate(data[agent], stamps[agent], epoch + t, scenario["max_gap_s"])
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
                dropped_unreasonable_velocity=dropped_unreasonable,
                minimum_separation_m=minimum, collision_risk=bool(risk_intervals),
                risk_pair_intervals=risk_intervals,
                separation_check="piecewise-linear approximation; missing intervals unassessed")
