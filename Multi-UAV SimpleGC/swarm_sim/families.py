"""Versioned physical-scene identity, independent of task/agent naming.

scene_content_v1 uses decimal half-up rounding to 1e-6. Numbers serialize as
floats, -0 becomes +0, and 360 degree heading equals 0. Capability limits are
not geometry: the platform ID, whose definition must be versioned separately,
is the physical platform identity required by the v0.4 contract.
"""

import hashlib
import json
import math
from decimal import Decimal, ROUND_HALF_UP


FAMILY_SCHEME = "scene_content_v1"


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("physical scene numbers must be finite numbers, not booleans")
    rounded = float(Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
    return 0.0 if rounded == 0 else rounded


def _canonical(value):
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, str):
        return value
    return _number(value)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def scene_content(spec_or_scenario):
    """Project a validated v3 task/scenario to canonical physical content only.

    Validation of allowed fields belongs to the task schema. This projection
    intentionally omits all IDs and task/mission/planner/execution settings.
    Position ties use heading rather than IDs, so renumbering never changes it.
    """
    scenario = spec_or_scenario.get("scenario", spec_or_scenario)
    platform_id = scenario["platform"]["id"]
    if not isinstance(platform_id, str) or not platform_id:
        raise ValueError("physical scene platform.id must be a nonempty string")
    vehicles = [dict(east_m=_number(v["east_m"]), north_m=_number(v["north_m"]),
                     heading_deg=_number(_number(v.get("heading_deg", 0)) % 360))
                for v in scenario["vehicles"]]
    # A value rounded to 360 is also physically the zero heading.
    for vehicle in vehicles:
        if vehicle["heading_deg"] == 360:
            vehicle["heading_deg"] = 0.0
    vehicles.sort(key=lambda v: (v["east_m"], v["north_m"], v["heading_deg"]))
    def regions(key):
        values = [_canonical({k: v for k, v in region.items() if k != "id"})
                  for region in scenario[key]]
        return sorted(values, key=_json)
    return dict(origin=_canonical(scenario["origin"]), world=_canonical(scenario["world"]),
                regions=regions("regions"), restricted_regions=regions("restricted_regions"),
                vehicles=vehicles, platform_id=platform_id)


def scene_content_hash(spec_or_scenario):
    return hashlib.sha256(_json(scene_content(spec_or_scenario)).encode("utf-8")).hexdigest()


def scene_family_id(spec_or_scenario):
    return "scene_" + scene_content_hash(spec_or_scenario)[:20]


def family_metadata(spec_or_scenario):
    digest = scene_content_hash(spec_or_scenario)
    return dict(family_id="scene_" + digest[:20], family_scheme=FAMILY_SCHEME, scene_content_sha256=digest)
