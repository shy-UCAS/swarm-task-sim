import argparse
import json
from pathlib import Path


DEFAULT_DATA_FILE = Path(__file__).resolve().parent / "loadData" / "uav_trajectories_persistent_20260213_164652.json"
DEFAULT_RELATIVE_ALT_M = 20


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def load_mission_tasks(path=DEFAULT_DATA_FILE):
    data = load_json(path)

    if "trajectories" in data:
        return _tasks_from_trajectories(data["trajectories"])

    if "uavs_coords_raw" in data:
        return _tasks_from_raw_coordinates(data["uavs_coords_raw"])

    if "uavs_coords_str" in data:
        return _tasks_from_raw_coordinates(data["uavs_coords_str"])

    raise ValueError(
        "Unsupported waypoint file format: expected 'trajectories', "
        "'uavs_coords_raw', or 'uavs_coords_str'."
    )


def _tasks_from_trajectories(trajectories):
    tasks = []
    for agent_id in sorted(trajectories):
        frames = trajectories[agent_id].get("frames", [])
        waypoints = [_waypoint_from_frame(frame) for frame in frames]
        tasks.append(
            {
                "agent_id": agent_id,
                "waypoints": _sort_waypoints_by_time(waypoints),
            }
        )
    return tasks


def _waypoint_from_frame(frame):
    pos = frame.get("pos", {})
    waypoint = {
        "t": frame.get("t"),
        "lat": pos.get("lat"),
        "lng": pos.get("lng"),
        "alt": pos.get("alt", DEFAULT_RELATIVE_ALT_M),
    }

    for key in ("pos_utm", "vel", "acc", "orientation", "angular_vel"):
        if key in frame:
            waypoint[key] = frame[key]

    return _drop_none_values(waypoint)


def _tasks_from_raw_coordinates(agents):
    tasks = []
    for agent_id in sorted(agents):
        agent = agents[agent_id]
        lats = agent.get("lats", [])
        lngs = agent.get("lngs", [])
        times = agent.get("ts", [])
        alts = agent.get("alts", [])
        extras = agent.get("extras", [])

        waypoints = []
        count = min(len(lats), len(lngs))
        for index in range(count):
            waypoint = {
                "t": times[index] if index < len(times) else index,
                "lat": lats[index],
                "lng": lngs[index],
                "alt": alts[index] if index < len(alts) else DEFAULT_RELATIVE_ALT_M,
                "extra": extras[index] if index < len(extras) else None,
            }
            waypoints.append(_drop_none_values(waypoint))

        tasks.append(
            {
                "agent_id": agent_id,
                "waypoints": _sort_waypoints_by_time(waypoints),
            }
        )
    return tasks


def _sort_waypoints_by_time(waypoints):
    return sorted(
        waypoints,
        key=lambda waypoint: waypoint["t"] if waypoint.get("t") is not None else 0,
    )


def _drop_none_values(values):
    return {key: value for key, value in values.items() if value is not None}


def print_task_summary(tasks):
    print(f"Loaded {len(tasks)} mission task(s).")
    for task in tasks:
        print(f"{task['agent_id']}: {len(task['waypoints'])} waypoint(s)")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Load UAV waypoint mission tasks.")
    parser.add_argument(
        "path",
        nargs="?",
        default=str(DEFAULT_DATA_FILE),
        help="Path to waypoint JSON file. Default: saveData/data_example.json",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    tasks = load_mission_tasks(args.path)
    print_task_summary(tasks)
    return tasks


if __name__ == "__main__":
    main()
