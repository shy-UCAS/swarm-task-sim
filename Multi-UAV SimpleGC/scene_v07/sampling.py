"""Intent-independent, one-shot family candidates with stable seed streams."""
from dataclasses import asdict
import hashlib
import math
import random

from shapely.geometry import MultiPoint

from .contract import GENERATOR_VERSION, SCHEMA_VERSION, UNITS, SceneConfig, validate_public_scene
from .geometry import center_of, expand_geometry, radial_boundary


def family_seed(master_seed, candidate_index):
    if isinstance(master_seed, bool) or not isinstance(master_seed, int) or master_seed < 0:
        raise ValueError("master_seed must be a nonnegative integer")
    if isinstance(candidate_index, bool) or not isinstance(candidate_index, int) or candidate_index < 0:
        raise ValueError("candidate_index must be a nonnegative integer")
    data = f"v07_scene_s1:{master_seed}:{candidate_index}".encode("ascii")
    return int.from_bytes(hashlib.sha256(data).digest()[:8], "big")


def _polygon(rng, diameter):
    count = rng.randint(3, 7)
    phase, stretch = rng.uniform(0, 2 * math.pi), rng.uniform(.7, 1)
    vertices = []
    for i in range(count):
        angle = phase + 2 * math.pi * i / count + rng.uniform(-.12, .12)
        vertices.append([diameter / 2 * math.cos(angle),
                         diameter / 2 * stretch * math.sin(angle)])
    hull = MultiPoint(vertices).convex_hull
    center = hull.centroid
    vertices = [[x - center.x, y - center.y] for x, y in list(hull.exterior.coords)[:-1]]
    # Circumscribed diameter is the declared sampled size (not an area proxy).
    radius = max(math.hypot(x, y) for x, y in vertices)
    vertices = [[x * diameter / (2 * radius), y * diameter / (2 * radius)] for x, y in vertices]
    return {"type": "Polygon", "vertices_m": vertices}


def _contour(rng, facility):
    if rng.random() < .5:
        return {"type": "Circle", "center_m": [0.0, 0.0],
                "radius_m": rng.uniform(20, 60) if facility else rng.uniform(100, 400)}
    return _polygon(rng, rng.uniform(100, 400) if facility else rng.uniform(200, 800))


def _radius(geometry):
    if geometry["type"] == "Circle":
        return geometry["radius_m"]
    return max(math.hypot(x, y) for x, y in geometry["vertices_m"])


def _move(geometry, point):
    if geometry["type"] == "Circle":
        return {**geometry, "center_m": list(point)}
    return {**geometry, "vertices_m": [[x + point[0], y + point[1]]
                                       for x, y in geometry["vertices_m"]]}


def _rectangle(x0, y0, x1, y1):
    return {"type": "Polygon", "vertices_m": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}


def _entries(rng, config):
    side, width, depth = config.map_side_m, config.entry_width_m, config.entry_depth_m
    result, normals = [], {}
    for i, edge in enumerate(rng.sample(["west", "east", "south", "north"], rng.randint(1, 2))):
        along = rng.uniform(width, side - width)
        low, high = along - width / 2, along + width / 2
        values = {"west": ((0, low, depth, high), (1, 0)),
                  "east": ((side - depth, low, side, high), (-1, 0)),
                  "south": ((low, 0, high, depth), (0, 1)),
                  "north": ((low, side - depth, high, side), (0, -1))}
        bounds, normal = values[edge]
        identifier = f"entry_{i + 1:02d}"
        result.append({"id": identifier, "geometry": _rectangle(*bounds)})
        normals[identifier] = normal
    return result, normals


def sample_family(seed, config=None):
    """A candidate is drawn once; invalid geometry is retained, never retried.

    Public map and generator-side family state are separate return values. No
    task units, groups, roles, selected facilities or timing labels are sampled.
    """
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("Family seed must be a nonnegative integer")
    config = config or SceneConfig()
    rng = random.Random(seed)
    count = rng.randint(1, 3)
    layout = "single" if count == 1 else rng.choice(["isolated", "clustered", "linear"])
    local = []
    for _ in range(count):
        contour = _contour(rng, True)
        d3 = rng.uniform(50, 150)
        d2 = d3 + rng.uniform(150, 400)
        d1 = d2 + rng.uniform(300, 800)
        local.append((contour, d3, d2, d1))
    anchor = [config.map_side_m / 2 + rng.uniform(-180, 180),
              config.map_side_m / 2 + rng.uniform(-180, 180)]
    direction = rng.uniform(0, 2 * math.pi)
    if count == 1:
        centers = [anchor]
    elif layout == "linear":
        spacing = 2 * max(_radius(g) + d2 for g, _, d2, _ in local) * rng.uniform(1.03, 1.18)
        centers = [[anchor[0] + (i - (count - 1) / 2) * spacing * math.cos(direction),
                    anchor[1] + (i - (count - 1) / 2) * spacing * math.sin(direction)] for i in range(count)]
    else:
        extents = [_radius(g) + (d1 if layout == "isolated" else d2) for g, _, d2, d1 in local]
        pair_distance = 2 * max(extents) * rng.uniform(1.03, 1.18)
        ring_radius = pair_distance / (2 * math.sin(math.pi / count))
        centers = [[anchor[0] + ring_radius * math.cos(direction + i * 2 * math.pi / count),
                    anchor[1] + ring_radius * math.sin(direction + i * 2 * math.pi / count)] for i in range(count)]
    entities, facilities, layers = [], [], {}
    for i, ((contour, d3, d2, d1), center) in enumerate(zip(local, centers)):
        identifier = f"facility_{i + 1:02d}"
        facility = {"id": identifier, "type": "facility", "geometry": _move(contour, center)}
        entities.append(facility)
        facilities.append(facility)
        layers[identifier] = {}
        for layer, offset in [("protected", d3), ("alert", d2), ("warning", d1)]:
            zone = {"id": f"{identifier}_{layer}", "type": "protection_zone",
                    "facility_id": identifier, "layer": layer, "offset_m": offset,
                    "geometry": expand_geometry(facility["geometry"], offset)}
            entities.append(zone)
            layers[identifier][layer] = zone
    entries, normals = _entries(rng, config)
    placements = []
    for i in range(rng.randint(1, 3)):
        shape = _contour(rng, False)
        types = ["entry_blocking", "facility_side"] + (["between_facilities"] if count > 1 else [])
        placement = rng.choice(types)
        facility = rng.choice(facilities)
        center = center_of(facility["geometry"])
        record = {"obstacle_id": f"obstacle_{i + 1:02d}", "placement": placement}
        if placement == "entry_blocking":
            entry = rng.choice(entries)
            source = center_of(entry["geometry"])
            fraction = rng.uniform(.25, .55)
            dx, dy = center[0] - source[0], center[1] - source[1]
            length = math.hypot(dx, dy)
            lateral = rng.uniform(-.5, .5) * _radius(shape)
            point = [source[0] + fraction * dx - lateral * dy / length,
                     source[1] + fraction * dy + lateral * dx / length]
            record.update(entry_id=entry["id"], reference_facility_id=facility["id"])
        elif placement == "facility_side":
            angle = rng.uniform(0, 2 * math.pi)
            alert = radial_boundary(layers[facility["id"]]["alert"]["geometry"], center, angle)
            warning = radial_boundary(layers[facility["id"]]["warning"]["geometry"], center, angle)
            distance = math.dist(center, alert) + rng.uniform(.55, .95) * math.dist(alert, warning)
            point = [center[0] + distance * math.cos(angle), center[1] + distance * math.sin(angle)]
            record.update(reference_facility_id=facility["id"])
        else:
            pair = rng.sample(facilities, 2)
            a, b = [center_of(item["geometry"]) for item in pair]
            fraction = rng.uniform(.4, .6)
            point = [a[j] + fraction * (b[j] - a[j]) + rng.uniform(-50, 50) for j in range(2)]
            record.update(reference_facility_ids=[item["id"] for item in pair])
        entities.append({"id": record["obstacle_id"], "type": "hard_constraint_obstacle",
                         "geometry": _move(shape, point)})
        placements.append(record)
    radar_placements = []
    for i in range(rng.randint(1, 3)):
        facility = rng.choice(facilities)
        center = center_of(facility["geometry"])
        angle = rng.uniform(0, 2 * math.pi)
        placement = rng.choice(["facility_side", "forward"])
        layer = "alert" if placement == "facility_side" else "warning"
        boundary = radial_boundary(layers[facility["id"]][layer]["geometry"], center, angle)
        fraction = rng.uniform(.15, .75) if placement == "facility_side" else rng.uniform(.92, 1.06)
        point = [center[j] + fraction * (boundary[j] - center[j]) for j in range(2)]
        radar_id = f"radar_{i + 1:02d}"
        entities.append({"id": radar_id, "type": "radar", "geometry": {"type": "Point", "position_m": point}})
        radar_placements.append({"radar_id": radar_id, "placement": placement,
                                 "reference_facility_id": facility["id"]})
    public = {"schema_version": SCHEMA_VERSION, "coordinate_system": "ENU", "units": dict(UNITS),
              "world": {"id": "world", "geometry": _rectangle(0, 0, config.map_side_m, config.map_side_m)},
              "entry_zones": entries, "entities": entities}
    validate_public_scene(public)
    vehicle_count = rng.randint(4, 12)
    altitude = rng.uniform(config.altitude_min_m, config.altitude_max_m)
    speed, spacing = rng.uniform(4, 10), rng.uniform(15, 25)
    states = []
    # Assign physical slots independently of the shuffled association handles.
    allocations = [i % len(entries) for i in range(vehicle_count)]
    rng.shuffle(allocations)
    per_entry = [allocations.count(i) for i in range(len(entries))]
    occupied = [0] * len(entries)
    for index in allocations:
        entry = entries[index]
        center = center_of(entry["geometry"])
        normal = normals[entry["id"]]
        offset = (occupied[index] - (per_entry[index] - 1) / 2) * spacing
        occupied[index] += 1
        point = [center[0] - normal[1] * offset, center[1] + normal[0] * offset]
        angle = math.atan2(normal[1], normal[0]) + rng.uniform(-.15, .15)
        initial_speed = rng.uniform(0, .25 * speed)
        states.append({"entry_id": entry["id"], "position_enu_m": [*point, altitude],
                       "velocity_enu_m_s": [initial_speed * math.cos(angle), initial_speed * math.sin(angle), 0.0],
                       "acceleration_enu_m_s2": [0.0, 0.0, 0.0]})
    handles = [f"uav_{i + 1:02d}" for i in range(vehicle_count)]
    rng.shuffle(handles)
    for state, handle in zip(states, handles):
        state["agent_id"] = handle
    rng.shuffle(states)
    private = {"schema_version": "traj2language.family_initial/0.7-s1.1",
               "generator_version": GENERATOR_VERSION, "family_id": f"family_{seed:016x}",
               "map_id": f"map_{seed:016x}", "sampling_seed": seed, "config": asdict(config),
               "layout": layout, "obstacle_placements": placements, "radar_placements": radar_placements,
               "vehicle_count": vehicle_count, "task_altitude_m": altitude, "cruise_speed_m_s": speed,
               "lateral_spacing_m": spacing, "initial_states": states,
               "observation_profile": {"position_sigma0_m": rng.uniform(.2, .5),
                                       "position_slope_m_per_km": rng.uniform(.1, .3),
                                       "velocity_sigma0_m_s": rng.uniform(.03, .08),
                                       "velocity_slope_m_s_per_km": rng.uniform(.01, .03)}}
    return public, private
