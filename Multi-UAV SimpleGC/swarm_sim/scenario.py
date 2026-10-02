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
    if data.get("schema_version") == 2:
        return validate_route_scene(data)
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


def route_mission_for(vehicle, route, speed_m_s, terminal_hold_s, origin):
    """One AUTO upload: HOME, speed, zero-hold interior NAVs, held endpoint.

    Acceptance params 2/3 preserve the legacy values (1/0). WP-S proved
    continuous flight, not which acceptance-radius input the firmware obeys;
    the actual WPNAV_RADIUS is read and recorded, never changed here.
    Empty routes are handled as no-ops by the runner and must not be uploaded.
    """
    if not isinstance(route, list) or not 1 <= len(route) <= 100:
        raise ValueError("route mission requires 1 to 100 waypoints; empty routes are no-ops")
    number(speed_m_s, "speed_m_s", .5, 15)
    number(terminal_hold_s, "terminal_hold_s", 0, 60)
    home_lat, home_lon = enu_to_geo(vehicle["east_m"], vehicle["north_m"], origin)
    mission = [dict(command=16, frame=3, params=[0, 0, 0, 0], lat=home_lat, lon=home_lon, alt=0),
               dict(command=178, frame=2, params=[1, speed_m_s, -1, 0], lat=0, lon=0, alt=0)]
    for index, point in enumerate(route):
        _route_point(point, "mission route point")
        lat, lon = enu_to_geo(point["east_m"], point["north_m"], origin)
        mission.append(dict(command=16, frame=3,
            params=[terminal_hold_s if index == len(route) - 1 else 0, 1, 0, float("nan")],
            lat=lat, lon=lon, alt=point["up_m"]))
    return mission


def _route_point(point, name):
    from .mission_schema import _object
    _object(point, name, ("east_m", "north_m", "up_m"))
    for key, low, high in (("east_m", -2000, 2000), ("north_m", -2000, 2000), ("up_m", 3, 100)):
        number(point[key], f"{name}.{key}", low, high)
    return point


def validate_route_scene(data):
    """Strict schema-2 shape/value validation; task binding is checked separately.

    Recompilation checks every derived planning/semantic field, so changing a
    route while keeping its original task cannot bypass validate_task_binding.
    """
    from .mission_schema import _object, _identifier, within_world
    from .mission_v3 import normalize_v3
    from .registry import get_intent

    data = copy.deepcopy(data)
    _object(data, "execution schema 2", ("schema_version", "control_mode", "scenario_id", "origin", "vehicles", "phases",
        "takeoff_alt_m", "record_hz", "max_gap_s", "min_separation_m", "timeout_s", "ready_timeout_s",
        "task_spec", "family_id", "family_scheme", "semantic_plan", "planning"))
    if type(data["schema_version"]) is not int or data["schema_version"] != 2:
        raise ValueError("execution schema_version must be integer 2")
    if data["control_mode"] != "semantic_phase_route_v1":
        raise ValueError("schema 2 requires semantic_phase_route_v1")
    _identifier(data["scenario_id"], "scenario_id")
    spec = normalize_v3(data["task_spec"])
    if spec["execution"]["control_mode"] != data["control_mode"]:
        raise ValueError("execution schema/control_mode conflicts with task")
    if data["scenario_id"] != spec["task_id"] or data["family_id"] != spec["family_id"] or data["family_scheme"] != spec["family_scheme"]:
        raise ValueError("execution identity conflicts with task")
    for key in ("origin", "vehicles"):
        if data[key] != spec["scenario"][key]:
            raise ValueError(f"execution {key} conflicts with normalized task")
    _object(data["origin"], "origin", ("lat", "lon", "alt_msl_m"))
    for key, low, high in (("lat", -80, 80), ("lon", -179, 179), ("alt_msl_m", -400, 8000)):
        number(data["origin"][key], f"origin.{key}", low, high)
    for vehicle in data["vehicles"]:
        _object(vehicle, "vehicle", ("id", "sysid", "east_m", "north_m", "heading_deg"))
        if type(vehicle["sysid"]) is not int:
            raise ValueError("vehicle.sysid must be an integer")
        for key, low, high in (("east_m", -2000, 2000), ("north_m", -2000, 2000), ("heading_deg", 0, 360)):
            number(vehicle[key], f"vehicle.{key}", low, high)
    for key, low, high in (("takeoff_alt_m", 3, 100), ("record_hz", 1, 50), ("max_gap_s", .05, 5),
            ("min_separation_m", .1, 1000), ("timeout_s", 10, 3600), ("ready_timeout_s", 10, 300)):
        number(data[key], key, low, high)
        if data[key] != spec["execution"][key]:
            raise ValueError(f"execution {key} conflicts with task")
    phases = data["phases"]
    if not isinstance(phases, list) or not 1 <= len(phases) <= 100:
        raise ValueError("schema 2 requires 1 to 100 semantic phases")
    semantic = _object(data["semantic_plan"], "semantic_plan", ("version", "execution_phases", "service_activation", "window_source", "zero_length_epsilon_m"))
    if semantic["version"] != "semantic_route_plan_v1" or type(semantic["zero_length_epsilon_m"]) is bool or semantic["zero_length_epsilon_m"] != .05:
        raise ValueError("unsupported semantic route plan version/epsilon")
    if not isinstance(semantic["execution_phases"], dict) or not isinstance(data["planning"], dict):
        raise ValueError("semantic/planning metadata must be objects")
    agents = {v["id"] for v in data["vehicles"]}
    intent = get_intent(spec["mission"]["intent"])
    expected_semantics = [p for p in intent.semantic_phases if p != "return" or spec["mission"]["return_required"]]
    if len(phases) != len(expected_semantics):
        raise ValueError("schema 2 must contain exactly one phase per requested semantic phase")
    previous = {v["id"]: dict(east_m=v["east_m"], north_m=v["north_m"], up_m=data["takeoff_alt_m"]) for v in data["vehicles"]}
    names = set()
    for index, phase in enumerate(phases):
        _object(phase, "route phase", ("name", "semantic_phase", "routes", "speed_m_s", "terminal_hold_s"))
        expected_name = f"p{index:02d}_{expected_semantics[index]}"
        if phase["name"] != expected_name or phase["semantic_phase"] != expected_semantics[index]:
            raise ValueError("schema 2 phases must follow registered semantic phase order/names")
        names.add(phase["name"])
        number(phase["speed_m_s"], "phase.speed_m_s", .5, 15)
        number(phase["terminal_hold_s"], "phase.terminal_hold_s", 0, 60)
        if phase["speed_m_s"] != spec["execution"]["speed_m_s"] or phase["terminal_hold_s"] != spec["execution"]["terminal_hold_s"]:
            raise ValueError("phase speed/hold conflicts with task")
        if not isinstance(phase["routes"], dict) or set(phase["routes"]) != agents:
            raise ValueError("phase routes must identify every agent exactly once")
        if phase["name"] not in semantic["execution_phases"]:
            raise ValueError("missing semantic phase mapping")
        mapping = _object(semantic["execution_phases"][phase["name"]], "phase mapping", ("semantic_phase", "agents"))
        if mapping["semantic_phase"] != phase["semantic_phase"] or not isinstance(mapping["agents"], dict) or set(mapping["agents"]) != agents:
            raise ValueError("phase mapping conflicts with route agents/semantic phase")
        for agent, route in phase["routes"].items():
            if not isinstance(route, list) or len(route) > 100:
                raise ValueError("continuous route must contain at most 100 waypoints")
            role = _object(mapping["agents"][agent], "route role", (
                "role", "service_enabled", "partition_id", "waypoint_planner_indices", "start_point", "terminal_point"))
            _route_point(role["start_point"], "route start")
            _route_point(role["terminal_point"], "route terminal")
            if role["start_point"] != previous[agent]:
                raise ValueError("route start must be previous semantic endpoint")
            if role["role"] != (phase["semantic_phase"] if route else "hold_no_op"):
                raise ValueError("empty routes require hold_no_op; nonempty routes require semantic role")
            if type(role["service_enabled"]) is not bool or role["service_enabled"] != (bool(route) and phase["semantic_phase"] in intent.service_phases):
                raise ValueError("service_enabled conflicts with no-op or registered service phase")
            if role["partition_id"] is not None and not isinstance(role["partition_id"], str):
                raise ValueError("partition_id must be a string or null")
            indices = role["waypoint_planner_indices"]
            if (not isinstance(indices, list) or len(indices) != len(route)
                    or any(type(i) is not int or i < 0 for i in indices) or any(b <= a for a, b in zip(indices, indices[1:]))):
                raise ValueError("waypoint_planner_indices must preserve increasing original indices")
            for point in route:
                _route_point(point, "route point")
                world = spec["scenario"]["world"]
                if (not within_world(point["east_m"], point["north_m"], world)
                        or not world["flight_up_bounds_m"][0] <= point["up_m"] <= world["flight_up_bounds_m"][1]):
                    raise ValueError("schema 2 route point outside task world bounds")
                if math.dist([previous[agent][k] for k in ("east_m", "north_m", "up_m")],
                             [point[k] for k in ("east_m", "north_m", "up_m")]) < .05:
                    raise ValueError("schema 2 contains a route segment below epsilon 0.05 m")
                previous[agent] = point
            if role["terminal_point"] != previous[agent]:
                raise ValueError("route terminal does not match final waypoint/no-op start")
    if set(semantic["execution_phases"]) != names:
        raise ValueError("unknown or missing semantic phase mapping")
    data["task_spec"] = spec
    return data
