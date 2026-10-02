"""Explicit scene-sampler capabilities; temporary registrations are test scoped."""

import copy
import math
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SamplerSpec:
    name: str
    intent_agnostic: bool
    normalize_params: Callable
    sample_scene: Callable
    base_index_dependent: bool = False


def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def normalize_strip_params(params):
    allowed = {"vehicle_counts", "partition_axes", "entry_sides", "strip_width_m",
               "sweep_length_m", "entry_distance_m", "region_east_m", "region_north_m"}
    if not isinstance(params, dict) or set(params) - allowed:
        raise ValueError("unknown strip_aligned_v1 sampler params")
    params = copy.deepcopy(params)
    for key, default, valid in (
            ("vehicle_counts", [2, 3, 6], lambda v: type(v) is int and 2 <= v <= 6),
            ("partition_axes", ["east", "north"], lambda v: isinstance(v, str) and v in ("east", "north")),
            ("entry_sides", ["low"], lambda v: isinstance(v, str) and v in ("low", "high"))):
        values = params.setdefault(key, default)
        if not isinstance(values, list) or not 1 <= len(values) <= 20 or not all(valid(v) for v in values):
            raise ValueError(f"invalid sampler choices: {key}")
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate sampler choices: {key}")
    for key, default, positive in (("strip_width_m", [12.0, 18.0], True),
                                  ("sweep_length_m", [8.0, 14.0], True),
                                  ("entry_distance_m", [10.0, 16.0], True),
                                  ("region_east_m", [-20.0, 10.0], False),
                                  ("region_north_m", [-20.0, 10.0], False)):
        values = params.setdefault(key, default)
        if (not isinstance(values, list) or len(values) != 2 or not all(_finite(v) for v in values)
                or values[0] > values[1] or (positive and values[0] <= 0)):
            raise ValueError(f"invalid sampler range: {key}")
        params[key] = [float(v) for v in values]
    return params


def sample_strip_scene(template_scenario, params, rng):
    """Retain the v0.3 strip geometry distribution, but use a scene-only RNG."""
    count = rng.choice(params["vehicle_counts"])
    axis = rng.choice(params["partition_axes"])
    side = rng.choice(params["entry_sides"])
    strip = rng.uniform(*params["strip_width_m"])
    sweep = rng.uniform(*params["sweep_length_m"])
    east, north = (rng.uniform(*params[key]) for key in ("region_east_m", "region_north_m"))
    entry = rng.uniform(*params["entry_distance_m"])
    width, height = (count * strip, sweep) if axis == "east" else (sweep, count * strip)
    vehicles = []
    for index in range(count):
        lane = (index + 0.5) * strip
        outside = -entry if side == "low" else sweep + entry
        e, n = (east + lane, north + outside) if axis == "east" else (east + outside, north + lane)
        vehicles.append(dict(id=f"uav_{index+1:02d}", sysid=index+1, east_m=e, north_m=n, heading_deg=0.0))
    scenario = copy.deepcopy(template_scenario)
    scenario.update(regions=[dict(id="R1", type="rectangle", min_east_m=east, min_north_m=north,
                                 width_m=width, height_m=height)], vehicles=vehicles, restricted_regions=[])
    return scenario, dict(vehicle_count=count, partition_axis=axis, entry_side=side,
        strip_width_m=strip, sweep_length_m=sweep, region_east_m=east, region_north_m=north,
        entry_distance_m=entry, planner_hints={"reconnaissance": {"partition_axis": axis}})


_RANDOM_SPAWN_V1_PARAMS = {
    "vehicle_counts": [2, 3, 4],
    "region_width_m": [30.0, 50.0],
    "region_height_m": [20.0, 35.0],
    "region_center_east_m": [-10.0, 10.0],
    "region_center_north_m": [-10.0, 10.0],
    "entry_sides": ["north", "east", "south", "west"],
    "entry_distance_m": [10.0, 20.0],
    "entry_lateral_offset_fraction": [-0.3, 0.3],
    "formations": ["line", "cluster"],
    "line_spacing_m": [8.0, 12.0],
    "line_rotation_deg": [-20.0, 20.0],
    "cluster_radius_m": [8.0, 15.0],
}
_RANDOM_SPAWN_V2_PARAMS = {
    "vehicle_counts": [2, 3, 4],
    "region_unit_width_m": [11.0, 16.0],
    "region_unit_height_m": [11.0, 16.0],
    "region_center_east_m": [-10.0, 10.0],
    "region_center_north_m": [-10.0, 10.0],
    "entry_sides": ["north", "east", "south", "west"],
    "entry_distance_m": [10.0, 20.0],
    "entry_lateral_offset_fraction": [-0.3, 0.3],
    "formations": ["line"],
    "line_spacing_m": [8.0, 12.0],
    "line_rotation_deg": [-20.0, 20.0],
}
_MIN_RANDOM_SPAWN_SEPARATION_M = 8.0


def normalize_random_spawn_params(params):
    """The version name fixes the v0.5 sampling distribution."""
    if not isinstance(params, dict) or set(params) - set(_RANDOM_SPAWN_V1_PARAMS):
        raise ValueError("unknown random_spawn_v1 sampler params")
    normalized = copy.deepcopy(_RANDOM_SPAWN_V1_PARAMS)
    for key, supplied in params.items():
        expected = normalized[key]
        if not isinstance(supplied, list) or len(supplied) != len(expected):
            raise ValueError(f"invalid random_spawn_v1 sampler params: {key}")
        if all(type(value) is str for value in expected):
            if supplied != expected:
                raise ValueError(f"random_spawn_v1 distribution changed: {key}")
        elif key == "vehicle_counts":
            if any(type(value) is not int for value in supplied) or supplied != expected:
                raise ValueError(f"random_spawn_v1 distribution changed: {key}")
        else:
            if not all(_finite(value) for value in supplied) or supplied != expected:
                raise ValueError(f"random_spawn_v1 distribution changed: {key}")
    return normalized


def normalize_random_spawn_v2_params(params):
    """Lock the r1.1 stratified, line-only distribution to this sampler version."""
    if not isinstance(params, dict) or set(params) - (set(_RANDOM_SPAWN_V2_PARAMS) | {"heading_policy"}):
        raise ValueError("unknown random_spawn_v2 sampler params")
    normalized = copy.deepcopy(_RANDOM_SPAWN_V2_PARAMS)
    for key, supplied in params.items():
        if key == "heading_policy":
            if supplied != "fixed_zero":
                raise ValueError("invalid random_spawn_v2 heading_policy")
            normalized[key] = supplied
            continue
        expected = normalized[key]
        if not isinstance(supplied, list) or len(supplied) != len(expected):
            raise ValueError(f"invalid random_spawn_v2 sampler params: {key}")
        if all(type(value) is str for value in expected):
            if supplied != expected:
                raise ValueError(f"random_spawn_v2 distribution changed: {key}")
        elif key == "vehicle_counts":
            if any(type(value) is not int for value in supplied) or supplied != expected:
                raise ValueError(f"random_spawn_v2 distribution changed: {key}")
        elif not all(_finite(value) for value in supplied) or supplied != expected:
            raise ValueError(f"random_spawn_v2 distribution changed: {key}")
    return normalized


def _cluster_positions(center, count, radius, rng):
    # Restart a whole draw if an earlier point left too little room for later
    # vehicles. Every accepted point is still sampled inside the declared disk.
    for _ in range(64):
        positions = []
        for _ in range(count):
            for _ in range(500):
                distance = radius * math.sqrt(rng.random())
                angle = rng.random() * 2 * math.pi
                point = (center[0] + distance * math.cos(angle),
                         center[1] + distance * math.sin(angle))
                if all(math.dist(point, other) + 1e-12 >= _MIN_RANDOM_SPAWN_SEPARATION_M
                       for other in positions):
                    positions.append(point)
                    break
            else:
                break
        if len(positions) == count:
            return positions
    raise ValueError("random_spawn_v1 cluster rejection limit exceeded")


def sample_random_spawn_scene(template_scenario, params, rng):
    """Sample only physical geometry; neither intent nor planner enters the RNG."""
    count = rng.choice(params["vehicle_counts"])
    width = rng.uniform(*params["region_width_m"])
    height = rng.uniform(*params["region_height_m"])
    center_east = rng.uniform(*params["region_center_east_m"])
    center_north = rng.uniform(*params["region_center_north_m"])
    side = rng.choice(params["entry_sides"])
    entry_distance = rng.uniform(*params["entry_distance_m"])
    lateral_fraction = rng.uniform(*params["entry_lateral_offset_fraction"])
    formation = rng.choice(params["formations"])
    side_length = width if side in ("north", "south") else height
    lateral_offset = lateral_fraction * side_length
    if side == "north":
        formation_center = (center_east + lateral_offset, center_north + height / 2 + entry_distance)
    elif side == "south":
        formation_center = (center_east + lateral_offset, center_north - height / 2 - entry_distance)
    elif side == "east":
        formation_center = (center_east + width / 2 + entry_distance, center_north + lateral_offset)
    else:
        formation_center = (center_east - width / 2 - entry_distance, center_north + lateral_offset)

    sampled = dict(vehicle_count=count, region_width_m=width, region_height_m=height,
        region_center_east_m=center_east, region_center_north_m=center_north,
        entry_side=side, entry_distance_m=entry_distance,
        entry_lateral_offset_fraction=lateral_fraction, entry_lateral_offset_m=lateral_offset,
        formation=formation, formation_center_east_m=formation_center[0],
        formation_center_north_m=formation_center[1],
        sampler_params=copy.deepcopy(params))
    if formation == "line":
        spacing = rng.uniform(*params["line_spacing_m"])
        angle_deg = rng.uniform(*params["line_rotation_deg"])
        angle = math.radians(angle_deg)
        tangent = (1.0, 0.0) if side in ("north", "south") else (0.0, 1.0)
        direction = (tangent[0] * math.cos(angle) - tangent[1] * math.sin(angle),
                     tangent[0] * math.sin(angle) + tangent[1] * math.cos(angle))
        positions = [(formation_center[0] + (i - (count - 1) / 2) * spacing * direction[0],
                      formation_center[1] + (i - (count - 1) / 2) * spacing * direction[1])
                     for i in range(count)]
        sampled.update(line_spacing_m=spacing, line_rotation_deg=angle_deg)
    else:
        radius = rng.uniform(*params["cluster_radius_m"])
        positions = _cluster_positions(formation_center, count, radius, rng)
        sampled["cluster_radius_m"] = radius

    headings = [rng.random() * 360.0 for _ in range(count)]
    numbering = list(range(1, count + 1))
    rng.shuffle(numbering)
    vehicles = [dict(id=f"uav_{numbering[i]:02d}", sysid=numbering[i],
                     east_m=east, north_m=north, heading_deg=headings[i])
                for i, (east, north) in enumerate(positions)]
    world = template_scenario["world"]
    if not (world["east_bounds_m"][0] <= center_east - width / 2
            and center_east + width / 2 <= world["east_bounds_m"][1]
            and world["north_bounds_m"][0] <= center_north - height / 2
            and center_north + height / 2 <= world["north_bounds_m"][1]):
        raise ValueError("random_spawn_v1 region outside world bounds")
    if any(not (world["east_bounds_m"][0] <= v["east_m"] <= world["east_bounds_m"][1]
                    and world["north_bounds_m"][0] <= v["north_m"] <= world["north_bounds_m"][1])
           for v in vehicles):
        raise ValueError("random_spawn_v1 vehicle outside world bounds")
    if any(math.dist((left["east_m"], left["north_m"]),
                     (right["east_m"], right["north_m"])) + 1e-12
           < _MIN_RANDOM_SPAWN_SEPARATION_M
           for i, left in enumerate(vehicles) for right in vehicles[i + 1:]):
        raise ValueError("random_spawn_v1 initial separation below 8 m")
    sampled["spatial_slots"] = [dict(east_m=east, north_m=north,
                                      heading_deg=headings[i], id=vehicles[i]["id"],
                                      sysid=vehicles[i]["sysid"])
                                for i, (east, north) in enumerate(positions)]
    scenario = copy.deepcopy(template_scenario)
    scenario.update(regions=[dict(id="R1", type="rectangle", min_east_m=center_east - width / 2,
                                  min_north_m=center_north - height / 2,
                                  width_m=width, height_m=height)],
                    vehicles=sorted(vehicles, key=lambda v: v["id"]), restricted_regions=[])
    return scenario, sampled


def sample_random_spawn_v2_scene(template_scenario, params, rng, *, base_index):
    """Cycle N by base scene; draw the remaining physical geometry by scene seed."""
    if type(base_index) is not int or base_index < 0:
        raise ValueError("random_spawn_v2 requires a nonnegative integer base_index")
    count = params["vehicle_counts"][base_index % len(params["vehicle_counts"])]
    unit_width = rng.uniform(*params["region_unit_width_m"])
    unit_height = rng.uniform(*params["region_unit_height_m"])
    width, height = count * unit_width, count * unit_height
    center_east = rng.uniform(*params["region_center_east_m"])
    center_north = rng.uniform(*params["region_center_north_m"])
    side = rng.choice(params["entry_sides"])
    entry_distance = rng.uniform(*params["entry_distance_m"])
    lateral_fraction = rng.uniform(*params["entry_lateral_offset_fraction"])
    side_length = width if side in ("north", "south") else height
    lateral_offset = lateral_fraction * side_length
    if side == "north":
        formation_center = (center_east + lateral_offset, center_north + height / 2 + entry_distance)
    elif side == "south":
        formation_center = (center_east + lateral_offset, center_north - height / 2 - entry_distance)
    elif side == "east":
        formation_center = (center_east + width / 2 + entry_distance, center_north + lateral_offset)
    else:
        formation_center = (center_east - width / 2 - entry_distance, center_north + lateral_offset)

    spacing = rng.uniform(*params["line_spacing_m"])
    angle_deg = rng.uniform(*params["line_rotation_deg"])
    angle = math.radians(angle_deg)
    tangent = (1.0, 0.0) if side in ("north", "south") else (0.0, 1.0)
    direction = (tangent[0] * math.cos(angle) - tangent[1] * math.sin(angle),
                 tangent[0] * math.sin(angle) + tangent[1] * math.cos(angle))
    positions = [(formation_center[0] + (i - (count - 1) / 2) * spacing * direction[0],
                  formation_center[1] + (i - (count - 1) / 2) * spacing * direction[1])
                 for i in range(count)]
    headings = [rng.random() * 360.0 for _ in range(count)]
    if params.get("heading_policy") == "fixed_zero":
        # Consume the same draws as the original distribution so every later
        # random choice (including vehicle numbering) remains identical.
        headings = [0.0] * count
    numbering = list(range(1, count + 1))
    rng.shuffle(numbering)
    vehicles = [dict(id=f"uav_{numbering[i]:02d}", sysid=numbering[i],
                     east_m=east, north_m=north, heading_deg=headings[i])
                for i, (east, north) in enumerate(positions)]
    world = template_scenario["world"]
    if not (world["east_bounds_m"][0] <= center_east - width / 2
            and center_east + width / 2 <= world["east_bounds_m"][1]
            and world["north_bounds_m"][0] <= center_north - height / 2
            and center_north + height / 2 <= world["north_bounds_m"][1]):
        raise ValueError("random_spawn_v2 region outside world bounds")
    if any(not (world["east_bounds_m"][0] <= v["east_m"] <= world["east_bounds_m"][1]
                    and world["north_bounds_m"][0] <= v["north_m"] <= world["north_bounds_m"][1])
           for v in vehicles):
        raise ValueError("random_spawn_v2 vehicle outside world bounds")
    if any(math.dist((left["east_m"], left["north_m"]),
                     (right["east_m"], right["north_m"])) + 1e-12
           < _MIN_RANDOM_SPAWN_SEPARATION_M
           for i, left in enumerate(vehicles) for right in vehicles[i + 1:]):
        raise ValueError("random_spawn_v2 initial separation below 8 m")

    sampled = dict(base_index=base_index, vehicle_count=count,
        region_unit_width_m=unit_width, region_unit_height_m=unit_height,
        region_width_m=width, region_height_m=height,
        region_center_east_m=center_east, region_center_north_m=center_north,
        entry_side=side, entry_distance_m=entry_distance,
        entry_lateral_offset_fraction=lateral_fraction, entry_lateral_offset_m=lateral_offset,
        formation="line", formation_center_east_m=formation_center[0],
        formation_center_north_m=formation_center[1], line_spacing_m=spacing,
        line_rotation_deg=angle_deg, sampler_params=copy.deepcopy(params),
        spatial_slots=[dict(east_m=east, north_m=north, heading_deg=headings[i],
                            id=vehicles[i]["id"], sysid=vehicles[i]["sysid"])
                       for i, (east, north) in enumerate(positions)])
    scenario = copy.deepcopy(template_scenario)
    scenario.update(regions=[dict(id="R1", type="rectangle", min_east_m=center_east - width / 2,
                                  min_north_m=center_north - height / 2,
                                  width_m=width, height_m=height)],
                    vehicles=sorted(vehicles, key=lambda v: v["id"]), restricted_regions=[])
    return scenario, sampled


_SAMPLERS = {
    "strip_aligned_v1": SamplerSpec("strip_aligned_v1", False, normalize_strip_params, sample_strip_scene),
    "random_spawn_v1": SamplerSpec("random_spawn_v1", True, normalize_random_spawn_params,
                                   sample_random_spawn_scene),
    "random_spawn_v2": SamplerSpec("random_spawn_v2", True, normalize_random_spawn_v2_params,
                                   sample_random_spawn_v2_scene, base_index_dependent=True),
}


def get_sampler(name):
    if not isinstance(name, str) or name not in _SAMPLERS:
        raise ValueError(f"unregistered scene sampler: {name}")
    return _SAMPLERS[name]


def registered_samplers():
    return tuple(sorted(_SAMPLERS))


@contextmanager
def temporary_sampler(spec):
    if not isinstance(spec, SamplerSpec) or type(spec.intent_agnostic) is not bool:
        raise ValueError("temporary sampler must declare a boolean intent_agnostic capability")
    if not spec.name or spec.name in _SAMPLERS:
        raise ValueError("temporary sampler cannot replace an existing sampler")
    _SAMPLERS[spec.name] = spec
    try:
        yield spec
    finally:
        del _SAMPLERS[spec.name]
