"""Read-only audit of legacy paths; never silently reinterpret frame indices as seconds."""

import math
import statistics

import loadWaypoint


def audit_paths(path, time_unit="index"):
    tasks = loadWaypoint.load_mission_tasks(path)
    routes, all_speeds = [], []
    for task in tasks:
        points = task["waypoints"]
        length = 0
        speeds = []
        for before, after in zip(points, points[1:]):
            if not all(key in p for p in (before, after) for key in ("lat", "lng")):
                raise ValueError(f"{task['agent_id']}: missing latitude/longitude")
            lat1, lat2 = map(math.radians, (before["lat"], after["lat"]))
            delta_lon = math.radians(after["lng"] - before["lng"])
            hav = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
            distance = 6371000 * 2 * math.asin(min(1, math.sqrt(hav)))
            length += distance
            dt = after.get("t", 0) - before.get("t", 0)
            if dt > 0:
                speeds.append(distance / dt)
        all_speeds.extend(speeds)
        routes.append(dict(agent_id=task["agent_id"], points=len(points), path_length_m=length,
                           max_distance_per_time_unit=max(speeds, default=0)))
    return dict(agents=len(tasks), points=sum(len(t["waypoints"]) for t in tasks), time_unit=time_unit,
                median_distance_per_time_unit=statistics.median(all_speeds) if all_speeds else None,
                maximum_distance_per_time_unit=max(all_speeds, default=0), routes=routes,
                warning=("Values are metres per input time unit, not m/s until the source time unit is verified."
                         if time_unit == "index" else "Time treated as seconds by explicit request; verify speed and acceleration feasibility."),
                imported_for_execution=False)
