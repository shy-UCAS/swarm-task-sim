import argparse
import csv
import json
import math
import time
from pathlib import Path

import loadWaypoint
import main as telemetry


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONNECTION_CONFIG = BASE_DIR / "ArducopterSITL" / "TCP -local.port"
DEFAULT_OUTPUT_DIR = BASE_DIR / "saveData"
RECORD_HZ = 10
CSV_FIELDNAMES = [
    "t",
    "pos.lat",
    "pos.lng",
    "pos.alt",
    "vel.vx",
    "vel.vy",
    "vel.vz",
    "vel.ground_speed",
    "orientation.quat.x",
    "orientation.quat.y",
    "orientation.quat.z",
    "orientation.quat.w",
    "angular_vel.p",
    "angular_vel.q",
    "angular_vel.r",
]


def build_mission_plan(task):
    waypoints = [
        waypoint
        for waypoint in task.get("waypoints", [])
        if waypoint.get("lat") is not None and waypoint.get("lng") is not None
    ]
    if not waypoints:
        return []

    first = waypoints[0]
    mission_plan = [
        {
            "command": "home",
            "lat": first["lat"],
            "lng": first["lng"],
            "alt": 0,
        },
        {
            "command": "takeoff",
            "lat": first["lat"],
            "lng": first["lng"],
            "alt": first.get("alt", loadWaypoint.DEFAULT_RELATIVE_ALT_M),
        }
    ]
    for waypoint in waypoints:
        mission_plan.append(
            {
                "command": "waypoint",
                "lat": waypoint["lat"],
                "lng": waypoint["lng"],
                "alt": waypoint.get("alt", loadWaypoint.DEFAULT_RELATIVE_ALT_M),
            }
        )
    return mission_plan


def get_start_mission_seq(mission_plan):
    for index, item in enumerate(mission_plan):
        if item.get("command") != "home":
            return index
    return 0


def build_status_frame(messages, elapsed_time):
    position = messages.get("GLOBAL_POSITION_INT")
    attitude = messages.get("ATTITUDE")
    if position is None and attitude is None:
        return None

    frame = {"t": elapsed_time}
    if position is not None:
        vx = position.vx / 100.0
        vy = position.vy / 100.0
        vz = position.vz / 100.0
        frame["pos"] = {
            "lat": position.lat / 1e7,
            "lng": position.lon / 1e7,
            "alt": position.relative_alt / 1000.0,
        }
        frame["vel"] = {
            "vx": vx,
            "vy": vy,
            "vz": vz,
            "ground_speed": math.sqrt(vx * vx + vy * vy),
        }

    if attitude is not None:
        frame["orientation"] = {
            "quat": euler_to_quaternion(attitude.roll, attitude.pitch, attitude.yaw)
        }
        frame["angular_vel"] = {
            "p": attitude.rollspeed,
            "q": attitude.pitchspeed,
            "r": attitude.yawspeed,
        }

    return frame


def euler_to_quaternion(roll, pitch, yaw):
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)

    return {
        "x": sr * cp * cy - cr * sp * sy,
        "y": cr * sp * cy + sr * cp * sy,
        "z": cr * cp * sy - sr * sp * cy,
        "w": cr * cp * cy + sr * sp * sy,
    }


def build_record_document(agent_id, frames):
    return {
        "meta": {
            "format_version": "2.0",
            "dt": 1.0 / RECORD_HZ,
            "case_id": agent_id,
        },
        "trajectories": {
            agent_id: {
                "frames": frames,
            }
        },
    }


def save_task_record(agent_id, frames, output_dir=DEFAULT_OUTPUT_DIR):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    file_path = output_path / f"{agent_id}.csv"
    with file_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for frame in frames:
            writer.writerow(flatten_frame_for_csv(frame))
    return file_path


def flatten_frame_for_csv(frame):
    quat = frame.get("orientation", {}).get("quat", {})
    return {
        "t": frame.get("t", ""),
        "pos.lat": frame.get("pos", {}).get("lat", ""),
        "pos.lng": frame.get("pos", {}).get("lng", ""),
        "pos.alt": frame.get("pos", {}).get("alt", ""),
        "vel.vx": frame.get("vel", {}).get("vx", ""),
        "vel.vy": frame.get("vel", {}).get("vy", ""),
        "vel.vz": frame.get("vel", {}).get("vz", ""),
        "vel.ground_speed": frame.get("vel", {}).get("ground_speed", ""),
        "orientation.quat.x": quat.get("x", ""),
        "orientation.quat.y": quat.get("y", ""),
        "orientation.quat.z": quat.get("z", ""),
        "orientation.quat.w": quat.get("w", ""),
        "angular_vel.p": frame.get("angular_vel", {}).get("p", ""),
        "angular_vel.q": frame.get("angular_vel", {}).get("q", ""),
        "angular_vel.r": frame.get("angular_vel", {}).get("r", ""),
    }


def build_task_completion_message(current_agent_id, frame_count, next_agent_id):
    if next_agent_id:
        return (
            f"当前任务{current_agent_id}已完成，记录数据{frame_count}帧，"
            f"开始下一个任务{next_agent_id}，"
        )
    return f"当前任务{current_agent_id}已完成，记录数据{frame_count}帧，所有任务已完成。"


def build_record_progress_message(
    agent_id,
    current_waypoint,
    total_waypoints,
    frame_count,
    flight_mode="unknown",
    armed=False,
    lat=None,
    lng=None,
    alt=None,
):
    arm_text = "已解锁" if armed else "未解锁"
    position_text = (
        f"高度{alt:.2f}m，经纬度{lat:.4f},{lng:.4f}"
        if lat is not None and lng is not None and alt is not None
        else "高度unknown，经纬度unknown"
    )
    return (
        f"\r当前任务{agent_id}，当前飞行航点{current_waypoint}，"
        f"总航点数{total_waypoints}，已记录数据{frame_count}帧，"
        f"模式{flight_mode}，ARM{arm_text}，{position_text}"
    )


def get_flight_mode(heartbeat):
    if heartbeat is None:
        return "unknown"
    try:
        from pymavlink import mavutil
    except ImportError:
        return "unknown"
    return mavutil.mode_string_v10(heartbeat)


def get_position_for_progress(position):
    if position is None:
        return None, None, None
    return position.lat / 1e7, position.lon / 1e7, position.relative_alt / 1000.0


def connect_first_vehicle(config_path=DEFAULT_CONNECTION_CONFIG):
    connection_url = telemetry.get_connection_url(config_path, index=1)
    master = telemetry.connect_mavlink(connection_url)
    print(f"Connecting to {connection_url} ...")
    master.wait_heartbeat(timeout=30)
    print(
        f"Heartbeat received: system={master.target_system}, "
        f"component={master.target_component}"
    )
    telemetry.request_data_stream(master, RECORD_HZ)
    return master


def wait_until_takeoff_ready(master, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        heartbeat = master.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if heartbeat is None:
            continue

        gps = master.recv_match(type="GPS_RAW_INT", blocking=False)
        if gps is None or getattr(gps, "fix_type", 0) >= 3:
            print("Vehicle is ready for takeoff.")
            return

    raise TimeoutError("Vehicle was not ready for takeoff before timeout.")


def upload_mission(master, mission_plan, verbose=True):
    mavutil = _mavutil()
    master.mav.mission_clear_all_send(master.target_system, master.target_component)
    master.mav.mission_count_send(
        master.target_system,
        master.target_component,
        len(mission_plan),
    )
    if verbose:
        print(f"Mission count sent, waiting for {len(mission_plan)} item request(s).")

    sent = 0
    while sent < len(mission_plan):
        request = master.recv_match(
            type=["MISSION_REQUEST", "MISSION_REQUEST_INT"],
            blocking=True,
            timeout=10,
        )
        if request is None:
            raise TimeoutError(
                f"Timed out waiting for mission item request {sent}/{len(mission_plan)}."
            )

        seq = request.seq
        if seq < 0 or seq >= len(mission_plan):
            raise ValueError(f"Vehicle requested invalid mission seq {seq}.")

        item = mission_plan[seq]
        command = (
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF
            if item["command"] == "takeoff"
            else mavutil.mavlink.MAV_CMD_NAV_WAYPOINT
        )
        if request.get_type() == "MISSION_REQUEST_INT":
            master.mav.mission_item_int_send(
                master.target_system,
                master.target_component,
                seq,
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                command,
                1 if seq == 0 else 0,
                1,
                0,
                0,
                0,
                float("nan"),
                int(item["lat"] * 1e7),
                int(item["lng"] * 1e7),
                item["alt"],
            )
        else:
            master.mav.mission_item_send(
                master.target_system,
                master.target_component,
                seq,
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                command,
                1 if seq == 0 else 0,
                1,
                0,
                0,
                0,
                float("nan"),
                item["lat"],
                item["lng"],
                item["alt"],
            )
        sent += 1
        if verbose:
            print(
                f"\rMission upload progress: {sent}/{len(mission_plan)}",
                end="",
                flush=True,
            )

    ack = master.recv_match(type="MISSION_ACK", blocking=True, timeout=10)
    if verbose:
        print()
    if ack is None:
        raise TimeoutError("Timed out waiting for mission upload ACK.")
    start_seq = get_start_mission_seq(mission_plan)
    master.mav.mission_set_current_send(
        master.target_system, master.target_component, start_seq
    )
    if verbose:
        print(f"Mission upload ACK received. Mission current item set to {start_seq}.")


def start_mission(master, start_seq=0, arm_mode="GUIDED", mission_mode="AUTO"):
    print(f"Switching vehicle to {arm_mode} mode for arming ...")
    master.set_mode(arm_mode)
    print("Sending arm command ...")
    master.arducopter_arm()
    wait_until_armed(master, timeout=30)
    print("Vehicle armed.")
    set_current_mission(master, seq=start_seq, timeout=10)
    print(f"Switching vehicle to {mission_mode} mode ...")
    master.set_mode(mission_mode)
    wait_until_mode(master, mission_mode, timeout=10)
    send_mission_start(master, start_seq=start_seq)
    print(f"Vehicle switched to {mission_mode} mode and mission start requested.")


def wait_until_armed(master, timeout=30, verbose=True):
    deadline = time.monotonic() + timeout
    last_status_text = None
    while time.monotonic() < deadline:
        if master.motors_armed():
            return
        message = master.recv_match(
            type=["HEARTBEAT", "STATUSTEXT"],
            blocking=True,
            timeout=1,
        )
        if message is not None and message.get_type() == "STATUSTEXT":
            last_status_text = message.text
            if verbose:
                print(f"Vehicle status: {last_status_text}")

    detail = f" Last vehicle status: {last_status_text}" if last_status_text else ""
    raise TimeoutError(f"Timed out waiting for vehicle to arm.{detail}")


def wait_until_mode(master, expected_mode, timeout=10):
    deadline = time.monotonic() + timeout
    last_mode = "unknown"
    while time.monotonic() < deadline:
        message = master.recv_match(
            type=["HEARTBEAT", "STATUSTEXT"],
            blocking=True,
            timeout=1,
        )
        if message is None:
            continue
        if message.get_type() == "STATUSTEXT":
            print(f"Vehicle status: {message.text}")
            continue
        last_mode = get_flight_mode(message)
        if last_mode == expected_mode:
            return
    raise TimeoutError(
        f"Timed out waiting for vehicle mode {expected_mode}. Last mode: {last_mode}"
    )


def set_current_mission(master, seq=0, timeout=10, verbose=True):
    master.mav.mission_set_current_send(master.target_system, master.target_component, seq)
    if verbose:
        print(f"Setting mission current item to {seq} ...")

    deadline = time.monotonic() + timeout
    last_seq = None
    while time.monotonic() < deadline:
        message = master.recv_match(
            type=["MISSION_CURRENT", "STATUSTEXT"],
            blocking=True,
            timeout=1,
        )
        if message is None:
            continue
        if message.get_type() == "STATUSTEXT":
            if verbose:
                print(f"Vehicle status: {message.text}")
            continue

        last_seq = message.seq
        if last_seq == seq:
            if verbose:
                print(f"Mission current item confirmed: {seq}.")
            return

    raise TimeoutError(
        f"Timed out waiting for mission current item {seq}. Last mission current: {last_seq}"
    )


def send_mission_start(master, start_seq=0):
    mavutil = _mavutil()
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_MISSION_START,
        start_seq,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )


def fly_task(master, task, output_dir=DEFAULT_OUTPUT_DIR):
    mission_plan = build_mission_plan(task)
    if not mission_plan:
        print(f"Skipping {task['agent_id']}: no valid waypoints.")
        return None

    print(f"Uploading task {task['agent_id']} with {len(mission_plan)} mission item(s).")
    upload_mission(master, mission_plan)
    start_mission(master, start_seq=get_start_mission_seq(mission_plan))
    frames = record_until_mission_done(master, task["agent_id"], len(mission_plan))
    file_path = save_task_record(task["agent_id"], frames, output_dir)
    print(f"当前任务{task['agent_id']}记录完成，记录文件：{file_path}")
    return file_path, len(frames)


def record_until_mission_done(master, agent_id, mission_count):
    frames = []
    latest_messages = {}
    start_time = time.monotonic()
    next_record_time = start_time
    last_reached_seq = -1
    current_mission_seq = 0
    message_types = [
        "GLOBAL_POSITION_INT",
        "ATTITUDE",
        "HEARTBEAT",
        "MISSION_ITEM_REACHED",
        "MISSION_CURRENT",
    ]

    while True:
        message = master.recv_match(type=message_types, blocking=True, timeout=0.01)
        now = time.monotonic()

        if message is not None:
            message_type = message.get_type()
            if message_type in ("GLOBAL_POSITION_INT", "ATTITUDE", "HEARTBEAT"):
                latest_messages[message_type] = message
            elif message_type == "MISSION_ITEM_REACHED":
                last_reached_seq = max(last_reached_seq, message.seq)
            elif message_type == "MISSION_CURRENT":
                current_mission_seq = message.seq
                last_reached_seq = max(last_reached_seq, message.seq - 1)

        if now >= next_record_time:
            frame = build_status_frame(latest_messages, elapsed_time=now - start_time)
            if frame is not None:
                frames.append(frame)
                lat, lng, alt = get_position_for_progress(
                    latest_messages.get("GLOBAL_POSITION_INT")
                )
                print(
                    build_record_progress_message(
                        agent_id=agent_id,
                        current_waypoint=current_mission_seq,
                        total_waypoints=mission_count,
                        frame_count=len(frames),
                        flight_mode=get_flight_mode(latest_messages.get("HEARTBEAT")),
                        armed=master.motors_armed(),
                        lat=lat,
                        lng=lng,
                        alt=alt,
                    ),
                    end="",
                    flush=True,
                )
            next_record_time += 1.0 / RECORD_HZ

        if last_reached_seq >= mission_count - 1:
            print()
            return frames


def run(
    task_file=loadWaypoint.DEFAULT_DATA_FILE,
    output_dir=DEFAULT_OUTPUT_DIR,
    config_path=DEFAULT_CONNECTION_CONFIG,
):
    tasks = loadWaypoint.load_mission_tasks(task_file)
    loadWaypoint.print_task_summary(tasks)

    master = connect_first_vehicle(config_path)
    wait_until_takeoff_ready(master)

    saved_files = []
    for index, task in enumerate(tasks):
        result = fly_task(master, task, output_dir)
        if result is not None:
            file_path, frame_count = result
            saved_files.append(file_path)
            next_task = tasks[index + 1] if index + 1 < len(tasks) else None
            next_agent_id = next_task["agent_id"] if next_task else None
            print(
                build_task_completion_message(
                    task["agent_id"], frame_count, next_agent_id
                )
            )
    return saved_files


def _mavutil():
    try:
        from pymavlink import mavutil
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: pymavlink. Install it in this conda env with "
            "`conda run -n whqgc pip install pymavlink`."
        ) from exc
    return mavutil


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Fly loaded waypoint tasks in mission mode.")
    parser.add_argument(
        "--task-file",
        default=str(loadWaypoint.DEFAULT_DATA_FILE),
        help="Waypoint task JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for recorded flight JSON files.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONNECTION_CONFIG),
        help="TCP connection config file.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    run(task_file=args.task_file, output_dir=args.output_dir, config_path=args.config)


if __name__ == "__main__":
    main()
