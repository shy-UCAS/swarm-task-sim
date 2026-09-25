"""Strict, small-area ENU scenarios. No implicit retiming of imported paths."""

import copy
import json
import math
import re
from pathlib import Path


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite and in [{low}, {high}]")
    return value


def radii(lat):
    sine = math.sin(math.radians(lat))
    base = 1 - 0.00669437999014 * sine * sine
    return 6378137 * (1 - 0.00669437999014) / base ** 1.5, 6378137 / math.sqrt(base)


def enu_to_geo(east, north, origin):
    """WGS84 local linear projection, deliberately limited to 2 km scenarios."""
    meridian, prime = radii(origin["lat"])
    return (origin["lat"] + math.degrees(north / meridian),
            origin["lon"] + math.degrees(east / (prime * math.cos(math.radians(origin["lat"])))))


def geo_to_enu(lat, lon, alt_msl, origin):
    meridian, prime = radii(origin["lat"])
    return (math.radians(lon - origin["lon"]) * prime * math.cos(math.radians(origin["lat"])),
            math.radians(lat - origin["lat"]) * meridian, alt_msl - origin["alt_msl_m"])


def validate(data):
    data = copy.deepcopy(data)
    if data.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", data.get("scenario_id", "")):
        raise ValueError("scenario_id must be a safe filename identifier")
    origin = data["origin"]
    for key, low, high in (("lat", -80, 80), ("lon", -179, 179), ("alt_msl_m", -400, 8000)):
        number(origin[key], f"origin.{key}", low, high)
    vehicles = data["vehicles"]
    if not 1 <= len(vehicles) <= 6:
        raise ValueError("v1 supports 1 to 6 vehicles per scenario")
    ids, sysids = set(), set()
    for vehicle in vehicles:
        agent = vehicle["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", agent) or agent in ids:
            raise ValueError("vehicle IDs must be unique safe identifiers")
        ids.add(agent)
        sysid = vehicle["sysid"]
        number(sysid, "sysid", 1, 250)
        if not isinstance(sysid, int) or sysid in sysids:
            raise ValueError("sysid must be a unique integer")
        sysids.add(sysid)
        for key in ("east_m", "north_m"):
            number(vehicle[key], f"{agent}.{key}", -2000, 2000)
        number(vehicle.setdefault("heading_deg", 0), "heading_deg", 0, 360)
    number(data.setdefault("takeoff_alt_m", 8), "takeoff_alt_m", 3, 100)
    number(data.setdefault("record_hz", 10), "record_hz", 1, 50)
    number(data.setdefault("min_separation_m", 5), "min_separation_m", 0.1, 1000)
    number(data.setdefault("timeout_s", 180), "timeout_s", 10, 3600)
    number(data.setdefault("ready_timeout_s", 90), "ready_timeout_s", 10, 300)
    number(data.setdefault("max_gap_s", 0.5), "max_gap_s", 0.05, 5)
    if not data.get("phases") or len(data["phases"]) > 100:
        raise ValueError("provide 1 to 100 phases")
    phase_names = set()
    for phase in data["phases"]:
        if not isinstance(phase.get("name"), str) or phase["name"] in phase_names:
            raise ValueError("phase names must be unique strings")
        phase_names.add(phase["name"])
        if set(phase["targets"]) != ids:
            raise ValueError(f"phase {phase['name']} must target every vehicle exactly once")
        for agent, target in phase["targets"].items():
            for key in ("east_m", "north_m"):
                number(target[key], f"{agent}.{key}", -2000, 2000)
            number(target["up_m"], "up_m", 3, 100)
            number(target.setdefault("speed_m_s", 4), "speed_m_s", 0.5, 15)
            number(target.setdefault("hold_s", 1), "hold_s", 0, 60)
    # Ground spawn geometry is meaningful even before telemetry exists.
    for i, left in enumerate(vehicles):
        for right in vehicles[i + 1:]:
            distance = math.hypot(left["east_m"] - right["east_m"], left["north_m"] - right["north_m"])
            if distance < data["min_separation_m"]:
                raise ValueError(f"Initial separation too small: {left['id']}/{right['id']}: {distance:.2f} m")
    return data


def load(path):
    return validate(json.loads(Path(path).read_text(encoding="utf-8-sig")))


def mission_for(vehicle, target, origin):
    """Home placeholder, speed, and one reached-and-held waypoint per phase."""
    home_lat, home_lon = enu_to_geo(vehicle["east_m"], vehicle["north_m"], origin)
    lat, lon = enu_to_geo(target["east_m"], target["north_m"], origin)
    return [
        dict(command=16, frame=3, params=[0, 0, 0, 0], lat=home_lat, lon=home_lon, alt=0),
        dict(command=178, frame=2, params=[1, target["speed_m_s"], -1, 0], lat=0, lon=0, alt=0),
        dict(command=16, frame=3, params=[target["hold_s"], 1, 0, float("nan")], lat=lat, lon=lon, alt=target["up_m"]),
    ]
