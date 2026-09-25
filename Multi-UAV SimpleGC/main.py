import argparse
import math
import sys
import time
from pathlib import Path


DEFAULT_CONFIG = Path(__file__).resolve().parent / "ArducopterSITL" / "TCP -local.port"


def normalize_connection_url(url):
    value = url.strip()
    if value.startswith("tcp://"):
        return "tcp:" + value[len("tcp://") :]
    return value


def read_connection_urls(config_path):
    path = Path(config_path)
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value:
            urls.append(normalize_connection_url(value))
    return urls


def get_connection_url(config_path=DEFAULT_CONFIG, index=1):
    urls = read_connection_urls(config_path)
    if not urls:
        raise ValueError(f"No connection URLs found in {config_path}")
    if index < 1 or index > len(urls):
        raise ValueError(f"Connection index must be between 1 and {len(urls)}")
    return urls[index - 1]


def build_telemetry_snapshot(messages):
    position = messages.get("GLOBAL_POSITION_INT")
    attitude = messages.get("ATTITUDE")
    if position is None or attitude is None:
        return None

    return {
        "lat_deg": position.lat / 1e7,
        "lon_deg": position.lon / 1e7,
        "relative_alt_m": position.relative_alt / 1000.0,
        "vx_m_s": position.vx / 100.0,
        "vy_m_s": position.vy / 100.0,
        "vz_m_s": position.vz / 100.0,
        "roll_deg": math.degrees(attitude.roll),
        "pitch_deg": math.degrees(attitude.pitch),
        "yaw_deg": math.degrees(attitude.yaw),
        "roll_rate_deg_s": math.degrees(attitude.rollspeed),
        "pitch_rate_deg_s": math.degrees(attitude.pitchspeed),
        "yaw_rate_deg_s": math.degrees(attitude.yawspeed),
    }


def format_telemetry(snapshot):
    return (
        f"lat={snapshot['lat_deg']:.7f} deg, "
        f"lon={snapshot['lon_deg']:.7f} deg, "
        f"alt={snapshot['relative_alt_m']:.2f} m | "
        f"vel=[vx={snapshot['vx_m_s']:.2f}, "
        f"vy={snapshot['vy_m_s']:.2f}, "
        f"vz={snapshot['vz_m_s']:.2f}] m/s | "
        f"att=[roll={snapshot['roll_deg']:.2f}, "
        f"pitch={snapshot['pitch_deg']:.2f}, "
        f"yaw={snapshot['yaw_deg']:.2f}] deg | "
        f"rate=[roll={snapshot['roll_rate_deg_s']:.2f}, "
        f"pitch={snapshot['pitch_rate_deg_s']:.2f}, "
        f"yaw={snapshot['yaw_rate_deg_s']:.2f}] deg/s"
    )


def print_inline(text):
    print(f"\r{text}", end="", flush=True)


def request_data_stream(master, rate_hz):
    master.mav.request_data_stream_send(
        master.target_system,
        master.target_component,
        0,
        rate_hz,
        1,
    )


def connect_mavlink(connection_url, baud=115200):
    try:
        from pymavlink import mavutil
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: pymavlink. Use the project environment in .conda-env."
        ) from exc

    return mavutil.mavlink_connection(connection_url, baud=baud)


def run(connection_url, rate_hz=5, print_hz=1, once=False):
    master = connect_mavlink(connection_url)
    print(f"Connecting to {connection_url} ...")
    master.wait_heartbeat(timeout=30)
    print(
        f"Heartbeat received: system={master.target_system}, "
        f"component={master.target_component}"
    )
    request_data_stream(master, rate_hz)

    latest_messages = {}
    next_print_time = 0.0
    message_types = ["GLOBAL_POSITION_INT", "ATTITUDE"]

    while True:
        message = master.recv_match(type=message_types, blocking=True, timeout=2)
        if message is None:
            print_inline("Waiting for telemetry ...")
            continue

        latest_messages[message.get_type()] = message
        snapshot = build_telemetry_snapshot(latest_messages)
        if snapshot is None:
            continue

        now = time.monotonic()
        if once or now >= next_print_time:
            print_inline(format_telemetry(snapshot))
            next_print_time = now + (1.0 / print_hz)

        if once:
            break


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Connect to ArduCopter/PX4 SITL over MAVLink and print telemetry."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to the TCP connection config file.",
    )
    parser.add_argument(
        "--index",
        type=int,
        default=1,
        help="One-based connection index from the config file. Default: 1.",
    )
    parser.add_argument(
        "--connect",
        help="MAVLink connection URL. Overrides --config and --index.",
    )
    parser.add_argument(
        "--rate-hz",
        type=int,
        default=5,
        help="Requested MAVLink telemetry stream rate. Default: 5.",
    )
    parser.add_argument(
        "--print-hz",
        type=float,
        default=1.0,
        help="Console print rate. Default: 1.0.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print one complete telemetry snapshot and exit.",
    )
    return parser.parse_args(argv)


def telemetry_main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    connection_url = (
        normalize_connection_url(args.connect)
        if args.connect
        else get_connection_url(args.config, args.index)
    )
    run(connection_url, rate_hz=args.rate_hz, print_hz=args.print_hz, once=args.once)


def main(argv=None):
    # The original single-vehicle flow remains explicit via python flyControl.py.
    from swarm import main as swarm_main
    return swarm_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
