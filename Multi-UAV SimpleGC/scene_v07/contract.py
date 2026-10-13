"""S1 configuration and a closed, model-visible vector scene contract."""
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

SCHEMA_VERSION = "traj2language.public_scene/0.7-s1.1"
GENERATOR_VERSION = "traj2language.scene_sampler/0.7-s1.2"
UNITS = {"length": "m", "angle": "rad", "speed": "m/s", "acceleration": "m/s^2"}


@dataclass(frozen=True)
class SceneConfig:
    map_side_m: float = 4000.0
    safety_margin_m: float = 30.0
    approach_standoff_m: float = 30.0
    angle_step_deg: int = 5
    planning_quad_segs: int = 8
    checking_quad_segs: int = 64
    # Not prescribed in r4: provisional engineering choices, not frozen values.
    altitude_min_m: float = 100.0
    altitude_max_m: float = 150.0
    entry_width_m: float = 360.0
    entry_depth_m: float = 100.0

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Invalid configuration: {name}")
        if not isinstance(self.angle_step_deg, int) or 360 % self.angle_step_deg:
            raise ValueError("angle_step_deg must divide 360")
        if not isinstance(self.planning_quad_segs, int) or self.planning_quad_segs < 4:
            raise ValueError("planning_quad_segs must be an integer >= 4")
        if not isinstance(self.checking_quad_segs, int) or self.checking_quad_segs < 16:
            raise ValueError("checking_quad_segs must be an integer >= 16")
        if self.altitude_max_m < self.altitude_min_m:
            raise ValueError("Inverted altitude range")
        if max(self.entry_width_m, self.entry_depth_m) >= self.map_side_m:
            raise ValueError("Entry zone cannot fill the map")


def canonical_json(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False,
                       sort_keys=True, indent=2) + "\n").encode("utf-8")


def _keys(value, expected, context):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"Closed public contract violated at {context}")


def _number(value, positive=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError("Geometry must contain numbers")
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError("Non-finite or non-positive geometry")


def _point(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("Expected [east, north]")
    for item in value:
        _number(item)


def validate_geometry(geometry):
    if not isinstance(geometry, dict):
        raise ValueError("Expected geometry object")
    kind = geometry.get("type")
    if kind == "Circle":
        _keys(geometry, ["type", "center_m", "radius_m"], "Circle")
        _point(geometry["center_m"])
        _number(geometry["radius_m"], positive=True)
    elif kind in ("Polygon", "BufferedPolygon"):
        fields = ["type", "vertices_m"]
        if kind == "BufferedPolygon":
            fields.append("buffer_m")
            _number(geometry.get("buffer_m"), positive=True)
        _keys(geometry, fields, kind)
        vertices = geometry["vertices_m"]
        if not isinstance(vertices, list) or len(vertices) < 3:
            raise ValueError("Polygon needs at least three vertices")
        for vertex in vertices:
            _point(vertex)
        # Polygon rings are open in this format; closing edge is implicit.
        from shapely.geometry import Polygon
        polygon = Polygon(vertices)
        if not polygon.is_valid or polygon.area <= 0:
            raise ValueError("Invalid polygon")
        if not polygon.equals(polygon.convex_hull):
            raise ValueError("Only convex source contours are supported")
    elif kind == "Point":
        _keys(geometry, ["type", "position_m"], "Point")
        _point(geometry["position_m"])
    else:
        raise ValueError("Unsupported geometry")


def validate_public_scene(scene):
    """Strict whitelist at every level, including geometry and associations.

    Audit seeds, family IDs, routes and arbitrary extension fields cannot leak.
    Facility-to-zone associations describe the public map, not task selection.
    """
    _keys(scene, ["schema_version", "coordinate_system", "units", "world",
                  "entry_zones", "entities"], "scene")
    if scene["schema_version"] != SCHEMA_VERSION or scene["coordinate_system"] != "ENU":
        raise ValueError("Unsupported scene version or coordinates")
    if scene["units"] != UNITS:
        raise ValueError("Unsupported units")
    _keys(scene["world"], ["id", "geometry"], "world")
    if scene["world"]["id"] != "world" or scene["world"]["geometry"].get("type") != "Polygon":
        raise ValueError("Invalid world")
    validate_geometry(scene["world"]["geometry"])
    if not isinstance(scene["entities"], list) or not isinstance(scene["entry_zones"], list):
        raise ValueError("Expected entity/entry arrays")
    identifiers = {"world"}
    for entry in scene["entry_zones"]:
        _keys(entry, ["id", "geometry"], "entry zone")
        if entry["geometry"].get("type") != "Polygon":
            raise ValueError("Entry zones must be polygons")
        validate_geometry(entry["geometry"])
    facilities = {e.get("id") for e in scene["entities"] if e.get("type") == "facility"}
    layers = {facility: [] for facility in facilities}
    for entity in scene["entities"]:
        fields = ["id", "type", "geometry"]
        kind = entity.get("type")
        if kind == "protection_zone":
            fields += ["facility_id", "layer", "offset_m"]
            if entity.get("facility_id") not in facilities:
                raise ValueError("Dangling facility association")
            if entity.get("layer") not in ("protected", "alert", "warning"):
                raise ValueError("Invalid protection layer")
            _number(entity.get("offset_m"), positive=True)
            layers[entity["facility_id"]].append(entity["layer"])
        elif kind not in ("facility", "hard_constraint_obstacle", "radar"):
            raise ValueError("Unsupported entity type")
        _keys(entity, fields, "entity")
        validate_geometry(entity["geometry"])
        shape = entity["geometry"]["type"]
        allowed = {"radar": ("Point",), "protection_zone": ("Circle", "BufferedPolygon"),
                   "facility": ("Circle", "Polygon"),
                   "hard_constraint_obstacle": ("Circle", "Polygon")}[kind]
        if shape not in allowed:
            raise ValueError("Geometry incompatible with entity type")
    for record in scene["entry_zones"] + scene["entities"]:
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError("Duplicate or invalid entity ID")
        identifiers.add(identifier)
    if not 1 <= len(facilities) <= 3 or not 1 <= len(scene["entry_zones"]) <= 2:
        raise ValueError("Invalid facility/entry count")
    for kind in ("hard_constraint_obstacle", "radar"):
        if not 1 <= sum(e["type"] == kind for e in scene["entities"]) <= 3:
            raise ValueError("Invalid obstacle/radar count")
    if any(sorted(values) != ["alert", "protected", "warning"] for values in layers.values()):
        raise ValueError("Each facility needs exactly three layers")
    return scene


def schema_path():
    return Path(__file__).with_name("public_scene.schema.json")
