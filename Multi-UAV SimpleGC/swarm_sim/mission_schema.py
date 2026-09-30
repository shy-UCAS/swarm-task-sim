"""Strict, deterministic normalization for the supported shared MissionSpec v2."""

import copy
import math
import re

from .scenario import number


def _object(value, name, fields, optional=()):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    unknown = set(value) - set(fields)
    missing = set(fields) - set(optional) - set(value)
    if unknown:
        raise ValueError(f"unsupported {name} fields: {sorted(unknown)}")
    if missing:
        raise ValueError(f"missing {name} fields: {sorted(missing)}")
    return value


def _identifier(value, name, maximum=64):
    if not isinstance(value, str) or not re.fullmatch(rf"[A-Za-z0-9_-]{{1,{maximum}}}", value):
        raise ValueError(f"{name} must be a safe identifier")
    return value


def _numeric(obj, key, path, low, high):
    obj[key] = float(number(obj[key], f"{path}.{key}", low, high))
    return obj[key]


def _enum(obj, key, path, choices):
    if not isinstance(obj[key], str) or obj[key] not in choices:
        raise ValueError(f"{path}.{key} must be one of {list(choices)}")


def _bounds(world, key, low, high):
    value = world[key]
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"world.{key} must contain two bounds")
    world[key] = [float(number(x, f"world.{key}", low, high)) for x in value]
    if world[key][0] >= world[key][1]:
        raise ValueError(f"world.{key} bounds must increase")


def within_world(east, north, world):
    return (world["east_bounds_m"][0] <= east <= world["east_bounds_m"][1]
            and world["north_bounds_m"][0] <= north <= world["north_bounds_m"][1])


def normalize_mission(spec):
    """Return a canonical deep copy; reject unsupported input rather than ignoring it.

    All v2 configuration sections are explicit. Heading alone has a documented
    default of zero. Agent/region ordering is canonical by ID, numeric fields use
    floats, and identity/version/seed fields retain integers.
    """
    spec = copy.deepcopy(spec)
    _object(spec, "TaskSpec v2", (
        "schema_version", "task_id", "family_id", "seed", "scenario", "mission",
        "planner", "platform", "execution"))
    if type(spec["schema_version"]) is not int or spec["schema_version"] != 2:
        raise ValueError("TaskSpec schema_version must be integer 2")
    for key in ("task_id", "family_id"):
        _identifier(spec[key], key)
    if type(spec["seed"]) is not int or not 0 <= spec["seed"] <= 2**63 - 1:
        raise ValueError("seed must be an integer in [0, 2**63 - 1]")

    scenario = _object(spec["scenario"], "scenario", (
        "scene_id", "origin", "world", "regions", "restricted_regions", "vehicles"))
    _identifier(scenario["scene_id"], "scenario.scene_id")
    origin = _object(scenario["origin"], "origin", ("lat", "lon", "alt_msl_m"))
    for key, low, high in (("lat", -80, 80), ("lon", -179, 179), ("alt_msl_m", -400, 8000)):
        _numeric(origin, key, "origin", low, high)
    world = _object(scenario["world"], "world", (
        "east_bounds_m", "north_bounds_m", "flight_up_bounds_m"))
    for key in ("east_bounds_m", "north_bounds_m"):
        _bounds(world, key, -2000, 2000)
    _bounds(world, "flight_up_bounds_m", 3, 100)
    if not isinstance(scenario["restricted_regions"], list) or scenario["restricted_regions"]:
        raise ValueError("restricted_regions must be empty; obstacle routing is not supported")
    regions = scenario["regions"]
    if not isinstance(regions, list) or len(regions) != 1:
        raise ValueError("v2 supports exactly one shared rectangle region")
    region = _object(regions[0], "region", (
        "id", "type", "min_east_m", "min_north_m", "width_m", "height_m"))
    _identifier(region["id"], "region.id")
    _enum(region, "type", "region", ("rectangle",))
    for key in ("min_east_m", "min_north_m"):
        _numeric(region, key, "region", -2000, 2000)
    for key in ("width_m", "height_m"):
        _numeric(region, key, "region", 0.01, 4000)
    if not (within_world(region["min_east_m"], region["min_north_m"], world)
            and within_world(region["min_east_m"] + region["width_m"],
                             region["min_north_m"] + region["height_m"], world)):
        raise ValueError("shared region extends outside world/backend bounds")
    vehicles = scenario["vehicles"]
    if not isinstance(vehicles, list) or not 1 <= len(vehicles) <= 6:
        raise ValueError("v2 supports 1 to 6 vehicles")
    identities, sysids = set(), set()
    for vehicle in vehicles:
        _object(vehicle, "vehicle", ("id", "sysid", "east_m", "north_m", "heading_deg"),
                optional=("heading_deg",))
        agent = _identifier(vehicle["id"], "vehicle.id", 48)
        if agent in identities:
            raise ValueError("duplicate vehicle ID")
        identities.add(agent)
        if type(vehicle["sysid"]) is not int or not 1 <= vehicle["sysid"] <= 250:
            raise ValueError("vehicle.sysid must be an integer in [1, 250]")
        if vehicle["sysid"] in sysids:
            raise ValueError("duplicate vehicle sysid")
        sysids.add(vehicle["sysid"])
        for key in ("east_m", "north_m"):
            _numeric(vehicle, key, "vehicle", -2000, 2000)
        vehicle.setdefault("heading_deg", 0.0)
        _numeric(vehicle, "heading_deg", "vehicle", 0, 360)
        if not within_world(vehicle["east_m"], vehicle["north_m"], world):
            raise ValueError(f"vehicle {agent} starts outside world bounds")
    scenario["vehicles"] = sorted(vehicles, key=lambda v: v["id"])
    scenario["regions"] = sorted(regions, key=lambda r: r["id"])

    mission = _object(spec["mission"], "mission", (
        "intent", "objective", "target_region_id", "coverage_required", "return_required", "observation_model"))
    _enum(mission, "intent", "mission", ("reconnaissance",))
    _enum(mission, "objective", "mission", ("area_coverage",))
    if mission["target_region_id"] != region["id"]:
        raise ValueError("mission references an unknown target_region_id")
    _numeric(mission, "coverage_required", "mission", 0.01, 1)
    if type(mission["return_required"]) is not bool:
        raise ValueError("mission.return_required must be boolean")
    model = _object(mission["observation_model"], "observation_model", (
        "type", "radius_m", "height_tolerance_m", "grid_m", "activation"))
    _enum(model, "type", "observation_model", ("ideal_horizontal_disk",))
    _enum(model, "activation", "observation_model", ("observe_phase_only",))
    _numeric(model, "radius_m", "observation_model", 0.01, 1000)
    _numeric(model, "height_tolerance_m", "observation_model", 0.01, 20)
    _numeric(model, "grid_m", "observation_model", 0.01, min(region["width_m"], region["height_m"]))
    if math.ceil(region["width_m"] / model["grid_m"]) * math.ceil(region["height_m"] / model["grid_m"]) > 10000:
        raise ValueError("shared coverage grid exceeds 10000 cells")

    planner = _object(spec["planner"], "planner", (
        "name", "partition_axis", "assignment", "lane_spacing_m", "tracking_margin_m"))
    _enum(planner, "name", "planner", ("equal_strip_lawnmower_v1",))
    _enum(planner, "partition_axis", "planner", ("east", "north"))
    _enum(planner, "assignment", "planner", ("monotone_entry_order",))
    _numeric(planner, "lane_spacing_m", "planner", 0.01, 4000)
    _numeric(planner, "tracking_margin_m", "planner", 0, 100)
    if planner["lane_spacing_m"] > 2 * model["radius_m"]:
        raise ValueError("lane spacing exceeds ideal observation footprint diameter")

    platform = _object(spec["platform"], "platform", (
        "id", "max_speed_m_s", "max_climb_rate_m_s", "max_horizontal_accel_m_s2",
        "max_path_length_m", "max_airborne_time_s", "reserve_time_s", "dynamics_validation"))
    _enum(platform, "id", "platform", ("basic_multirotor_nominal_v1",))
    _enum(platform, "dynamics_validation", "platform", ("execution_proxy_only",))
    for key, low, high in (
            ("max_speed_m_s", 0.5, 100), ("max_climb_rate_m_s", 0.01, 100),
            ("max_horizontal_accel_m_s2", 0.01, 1000), ("max_path_length_m", 0.01, 1000000),
            ("max_airborne_time_s", 0.01, 1000000), ("reserve_time_s", 0, 1000000)):
        _numeric(platform, key, "platform", low, high)
    if platform["reserve_time_s"] >= platform["max_airborne_time_s"]:
        raise ValueError("reserve_time_s must be less than max_airborne_time_s")

    execution = _object(spec["execution"], "execution", (
        "backend", "takeoff_alt_m", "speed_m_s", "waypoint_hold_s", "arrival_tolerance_m",
        "confirmation_dwell_s", "record_hz", "max_gap_s", "min_separation_m", "timeout_s", "ready_timeout_s"))
    _enum(execution, "backend", "execution", ("AUTO",))
    for key, low, high in (
            ("takeoff_alt_m", 3, 100), ("speed_m_s", 0.5, 15), ("waypoint_hold_s", 0, 60),
            ("arrival_tolerance_m", 0.2, 5), ("confirmation_dwell_s", 0, 60), ("record_hz", 1, 50),
            ("max_gap_s", 0.05, 5), ("min_separation_m", 0.1, 1000),
            ("timeout_s", 10, 3600), ("ready_timeout_s", 10, 300)):
        _numeric(execution, key, "execution", low, high)
    if execution["speed_m_s"] > platform["max_speed_m_s"]:
        raise ValueError("command speed exceeds platform max_speed_m_s")
    if not world["flight_up_bounds_m"][0] <= execution["takeoff_alt_m"] <= world["flight_up_bounds_m"][1]:
        raise ValueError("takeoff altitude outside flight_up_bounds_m")
    if min(region["width_m"], region["height_m"]) <= 2 * execution["arrival_tolerance_m"]:
        raise ValueError("region too small for declared arrival tolerance")
    return spec
