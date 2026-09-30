"""One receive owner per link. Control consumers observe a sequence-numbered inbox."""

import json
import math
import threading
import time
from collections import deque

from pymavlink import mavutil

from .scenario import geo_to_enu


class ManagedTCP(mavutil.mavtcp):
    """Turn peer closure into a failure instead of pymavlink's EOF busy loop."""

    def handle_eof(self):
        raise ConnectionError("SITL closed the TCP connection")

    def handle_disconnect(self):
        raise ConnectionError("SITL reset the TCP connection")


class Vehicle:
    def __init__(self, instance, raw_path, cancel, event, record_lifecycle=False):
        self.instance = instance
        self.id = instance["id"]
        self.sysid = instance["sysid"]
        self.cancel = cancel
        self.event = event
        self.master = None
        self.condition = threading.Condition()
        self.send_lock = threading.Lock()
        self.stop = threading.Event()
        self.latest = {}
        self.inbox = deque(maxlen=4096)
        self.sequence = 0
        self.error = None
        self.thread = None
        self.raw_path = raw_path
        self.target_component = 1
        self.record_lifecycle = record_lifecycle

    def lifecycle_event(self, kind):
        if not self.record_lifecycle:
            return
        sample = self.snapshot().get("GLOBAL_POSITION_INT")
        fields = {}
        if sample:
            fields = dict(source_boot_s=sample[1].time_boot_ms / 1000,
                          source_sample_age_s=time.perf_counter() - sample[0])
        self.event(kind, self.id, **fields)

    def connect(self, timeout=40):
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            self.check()
            try:
                self.master = ManagedTCP(self.instance["url"].removeprefix("tcp:"), source_system=255,
                                         source_component=190, autoreconnect=False, retries=1)
                break
            except OSError:
                self.cancel.wait(0.2)
        if self.master is None:
            raise TimeoutError(f"{self.id}: TCP connection timeout")
        self.thread = threading.Thread(target=self._receive, name=f"rx-{self.id}", daemon=True)
        self.thread.start()
        heartbeat = self.wait_message(["HEARTBEAT"], timeout=max(1, deadline - time.perf_counter()))
        self.target_component = heartbeat.get_srcComponent()
        self.send("request_data_stream_send", self.sysid, self.target_component, 0, 10, 1)
        self.event("connected", self.id, sysid=self.sysid)

    def _receive(self):
        try:
            with self.raw_path.open("w", encoding="utf-8") as raw:
                next_heartbeat = next_flush = 0.0
                while not self.stop.is_set():
                    now = time.perf_counter()
                    if now >= next_heartbeat:
                        self.send("heartbeat_send", mavutil.mavlink.MAV_TYPE_GCS,
                                  mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
                        next_heartbeat = now + 1
                    message = self.master.recv_match(blocking=True, timeout=0.05)
                    if message is not None:
                        received = time.perf_counter()
                        kind = message.get_type()
                        if kind == "BAD_DATA":
                            continue
                        if message.get_srcSystem() != self.sysid:
                            if kind == "HEARTBEAT":
                                raise RuntimeError(f"{self.id}: expected sysid {self.sysid}, got {message.get_srcSystem()}")
                            continue
                        raw.write(json.dumps({"recv_monotonic_s": received, "sysid": self.sysid,
                                              "message": message.to_dict()}, default=str) + "\n")
                        with self.condition:
                            self.sequence += 1
                            self.latest[kind] = (received, message)
                            self.inbox.append((self.sequence, kind, message))
                            self.condition.notify_all()
                    if now >= next_flush:
                        raw.flush()
                        next_flush = now + 1
        except Exception as exc:
            if not self.stop.is_set():
                with self.condition:
                    self.error = exc
                    self.condition.notify_all()

    def check(self):
        if self.cancel.is_set():
            raise RuntimeError(f"{self.id}: run cancelled")
        if self.error is not None:
            raise RuntimeError(f"{self.id}: receiver failed: {self.error}") from self.error
        with self.condition:
            heartbeat = self.latest.get("HEARTBEAT")
        if heartbeat and time.perf_counter() - heartbeat[0] > 5:
            raise TimeoutError(f"{self.id}: heartbeat stale for more than 5 s")

    def cursor(self):
        with self.condition:
            return self.sequence

    def snapshot(self):
        with self.condition:
            return dict(self.latest)

    def send(self, method, *args):
        with self.send_lock:
            getattr(self.master.mav, method)(*args)

    def wait_message(self, kinds, predicate=lambda m: True, after=0, timeout=10):
        deadline = time.perf_counter() + timeout
        cursor = after
        with self.condition:
            while True:
                self.check()
                for seq, kind, message in self.inbox:
                    if seq > cursor and kind in kinds and predicate(message):
                        return message
                cursor = self.sequence
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    text = self.latest.get("STATUSTEXT")
                    detail = text[1].text if text else "no status text"
                    raise TimeoutError(f"{self.id}: waiting for {kinds}; {detail}")
                self.condition.wait(min(remaining, 0.1))

    def wait_state(self, predicate, timeout, description):
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            self.check()
            state = self.snapshot()
            if predicate(state):
                return state
            self.cancel.wait(0.05)
        text = self.snapshot().get("STATUSTEXT")
        raise TimeoutError(f"{self.id}: {description}; {text[1].text if text else 'no status text'}")

    def command(self, command, *params, timeout=10):
        cursor = self.cursor()
        values = list(params) + [0] * (7 - len(params))
        self.send("command_long_send", self.sysid, self.target_component, command, 0, *values)
        ack = self.wait_message(["COMMAND_ACK"], lambda m: m.command == command and m.result != 5,
                                after=cursor, timeout=timeout)
        if ack.result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
            raise RuntimeError(f"{self.id}: command {command} rejected, result={ack.result}")

    def mode(self, name, timeout=10):
        mapping = self.master.mode_mapping()
        if name not in mapping:
            raise ValueError(f"{self.id}: unsupported mode {name}")
        cursor = self.cursor()
        self.send("set_mode_send", self.sysid, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mapping[name])
        self.wait_message(["HEARTBEAT"], lambda m: m.custom_mode == mapping[name], after=cursor, timeout=timeout)

    def prepare_airborne(self, altitude, timeout):
        def ready(state):
            gps, ekf, position = (state.get(k) for k in ("GPS_RAW_INT", "EKF_STATUS_REPORT", "GLOBAL_POSITION_INT"))
            return (gps and ekf and position and gps[1].fix_type >= 3 and
                    ekf[1].flags & 1 and ekf[1].flags & 16 and
                    all(time.perf_counter() - sample[0] < 2 for sample in (gps, ekf, position)))
        self.wait_state(ready, timeout, "GPS/EKF not ready")
        self.mode("GUIDED")
        # The readiness flags can precede the complete pre-arm settling checks.
        deadline = time.perf_counter() + min(timeout, 30)
        while True:
            try:
                self.command(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
                break
            except RuntimeError:
                self.check()
                if time.perf_counter() >= deadline:
                    raise
                self.cancel.wait(1)
        self.wait_state(lambda s: "HEARTBEAT" in s and s["HEARTBEAT"][1].base_mode & 128,
                        10, "arming was not confirmed")
        self.lifecycle_event("armed_confirmed")
        self.lifecycle_event("takeoff_command_sent")
        self.command(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, altitude)
        stable_since = None
        def airborne(state):
            nonlocal stable_since
            sample = state.get("GLOBAL_POSITION_INT")
            valid = (sample and time.perf_counter() - sample[0] < 1 and
                     abs(sample[1].relative_alt / 1000 - altitude) < 0.6 and
                     abs(sample[1].vz / 100) < 0.4)
            if not valid:
                stable_since = None
                return False
            if stable_since is None:
                stable_since = time.perf_counter()
            return time.perf_counter() - stable_since >= 1
        self.wait_state(airborne, timeout, "takeoff did not stabilize")
        self.mode("BRAKE" if self.record_lifecycle else "LOITER")
        self.event("airborne_ready", self.id)

    def upload(self, mission, timeout=20):
        self.mode("BRAKE" if self.record_lifecycle else "LOITER")
        cursor = self.cursor()
        self.send("mission_clear_all_send", self.sysid, self.target_component)
        ack = self.wait_message(["MISSION_ACK"], after=cursor, timeout=5)
        if ack.type != 0:
            raise RuntimeError(f"{self.id}: clear mission rejected ({ack.type})")
        cursor = self.cursor()
        self.send("mission_count_send", self.sysid, self.target_component, len(mission))
        deadline = time.perf_counter() + timeout
        sent = set()
        # Repeated requests are legal. Completion requires ACK and every unique seq.
        while time.perf_counter() < deadline:
            message = self.wait_message(["MISSION_REQUEST", "MISSION_REQUEST_INT", "MISSION_ACK"],
                                        after=cursor, timeout=max(0.01, deadline - time.perf_counter()))
            # Capture the sequence of THIS message, not the current receive tail.
            with self.condition:
                cursor = next(seq for seq, _, msg in self.inbox if msg is message)
            if message.get_type() == "MISSION_ACK":
                if message.type != 0 or len(sent) != len(mission):
                    raise RuntimeError(f"{self.id}: invalid mission ACK {message.type}, sent={sorted(sent)}")
                break
            if not 0 <= message.seq < len(mission):
                raise RuntimeError(f"{self.id}: invalid mission request {message.seq}")
            item = mission[message.seq]
            args = [self.sysid, self.target_component, message.seq, item["frame"], item["command"],
                    int(message.seq == 0), 1, *item["params"]]
            if message.get_type() == "MISSION_REQUEST_INT":
                # GLOBAL_RELATIVE_ALT_INT for coordinate-bearing items, MISSION for DO.
                args[3] = 6 if item["frame"] == 3 else item["frame"]
                self.send("mission_item_int_send", *args, round(item["lat"] * 1e7), round(item["lon"] * 1e7), item["alt"])
            else:
                self.send("mission_item_send", *args, item["lat"], item["lon"], item["alt"])
            sent.add(message.seq)
        else:
            raise TimeoutError(f"{self.id}: mission upload timed out")
        cursor = self.cursor()
        self.send("mission_set_current_send", self.sysid, self.target_component, 1)
        self.wait_message(["MISSION_CURRENT"], lambda m: m.seq == 1, after=cursor, timeout=10)

    def execute(self, epoch, mission_count, timeout, phase):
        while time.perf_counter() < epoch:
            self.check()
            self.cancel.wait(min(0.01, max(0, epoch - time.perf_counter())))
        cursor = self.cursor()
        self.event("phase_start_sent", self.id, phase=phase)
        self.mode("AUTO")
        # AUTO starts the preselected mission. Avoid a second MISSION_START that
        # could restart a short route after the mode-confirmation heartbeat.
        self.event("phase_auto_confirmed", self.id, phase=phase)
        self.wait_message(["MISSION_ITEM_REACHED"], lambda m: m.seq == mission_count - 1,
                          after=cursor, timeout=timeout)
        self.event("phase_finished", self.id, phase=phase)
        # Shared missions keep the AUTO waypoint controller active until the
        # independent geometric dwell succeeds. LOITER accepts pilot throttle;
        # SITL's default low throttle would descend during a scheduling barrier.
        if not self.record_lifecycle:
            self.mode("LOITER")

    def land(self, timeout=60):
        self.lifecycle_event("landing_started")
        self.mode("LAND")
        self.wait_state(lambda s: "HEARTBEAT" in s and not (s["HEARTBEAT"][1].base_mode & 128),
                        timeout, "landing/disarming timed out")
        self.event("landed", self.id)

    def confirm_target(self, target, origin, tolerance, dwell_s, phase, timeout=20, max_gap=0.5, quality_policy=None):
        """After AUTO/LOITER, require fresh geometric evidence in FCU source time.

        This deliberately adds a verification dwell; the mission ACK alone does
        not provide task completion evidence. Any invalid interval restarts it.
        """
        deadline = time.perf_counter() + timeout
        cursor = self.cursor()
        since = previous = None
        position = [target[k] for k in ("east_m", "north_m", "up_m")]
        while time.perf_counter() < deadline:
            message = self.wait_message(["GLOBAL_POSITION_INT"], after=cursor,
                                        timeout=max(0.01, deadline - time.perf_counter()))
            with self.condition:
                # Use the latest stamped sample, not an older inbox item with a
                # newer sample's receive timestamp during a receive burst.
                cursor = self.sequence
                received, message = self.latest["GLOBAL_POSITION_INT"]
            source = message.time_boot_ms / 1000
            actual = geo_to_enu(message.lat / 1e7, message.lon / 1e7, message.alt / 1000, origin)
            content_valid = True
            if quality_policy is not None:
                from .observations import live_observation
                values, _ = live_observation(message, received, time.perf_counter(), max_gap, origin, quality_policy)
                content_valid = values is not None
            inside = content_valid and math.dist(actual, position) <= tolerance and time.perf_counter() - received <= max_gap
            continuous = previous is not None and 0 < source - previous <= max_gap
            if not inside:
                since = None
            elif since is None or not continuous:
                since = source
            if inside and since is not None and source - since + 1e-8 >= dwell_s:
                self.event("task_target_verified", self.id, phase=phase, source_dwell_s=source - since,
                           tolerance_m=tolerance, position_error_m=math.dist(actual, position))
                return
            previous = source
        raise TimeoutError(f"{self.id}: geometric target/dwell confirmation timed out")

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
        if self.master is not None:
            self.master.close()
