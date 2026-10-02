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


_SAMPLERS = {"strip_aligned_v1": SamplerSpec("strip_aligned_v1", False, normalize_strip_params, sample_strip_scene)}


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
