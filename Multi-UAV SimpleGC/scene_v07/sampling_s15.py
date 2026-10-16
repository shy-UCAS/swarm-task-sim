"""S1.5 layout assembly; non-layout construction copied from S1.2 unchanged."""
from dataclasses import asdict, replace
import math
import random

from shapely.geometry import Point

from .contract import SCHEMA_VERSION, UNITS, SceneConfig, validate_public_scene
from .geometry import center_of, expand_geometry, radial_boundary, to_shape
from .sampling import _contour, _entries, _move, _rectangle
from .sampling_s11 import MAP_SIDES_M, SamplingPolicy, SamplingRejected, facility_count, place_obstacles_s12
from .layout_s15 import load_layout_config, place_layout_s15

GENERATOR_VERSION = "traj2language.scene_sampler/0.7-s1.5"


def _place_in_world(rng, local, layout, config, cfg, seed, policy, config_sha):
    def anchor(centers, side, bbox):
        resized = replace(config, map_side_m=side)
        entries, normals = _entries(rng, resized)
        edge = cfg["edge_clearance_m"]
        entry_shapes = [to_shape(e["geometry"]) for e in entries]
        for attempt in range(1, cfg["anchor_attempts"]+1):
            offset = [rng.uniform(edge-bbox[0], side-edge-bbox[2]),
                      rng.uniform(edge-bbox[1], side-edge-bbox[3])]
            world_centers = [[c[0]+offset[0], c[1]+offset[1]] for c in centers]
            warnings = [to_shape(expand_geometry(_move(g, c), d1), resized.checking_quad_segs, True)
                        for (g, _, _, d1), c in zip(local, world_centers)]
            if any(w.distance(e) <= resized.safety_margin_m for w in warnings for e in entry_shapes):
                continue
            return (world_centers, entries, normals, resized), attempt, attempt-1
        return None, cfg["anchor_attempts"], cfg["anchor_attempts"]

    try:
        return place_layout_s15(rng, local, layout, cfg, finalize=anchor)
    except SamplingRejected as failure:
        # Incomplete geometry is retained only as a draft, never public schema.
        draft = {"world": {"id": "world", "geometry": _rectangle(0, 0, config.map_side_m, config.map_side_m)},
                 "entry_zones": [], "entities": []}
        family = {"family_id": f"family_s15_{seed:016x}", "map_id": f"map_s15_{seed:016x}",
                  "generator_version": GENERATOR_VERSION, "sampling_revision": "s1.5", "sampling_seed": seed,
                  "config": asdict(config), "sampling_policy": asdict(policy), "layout": layout,
                  "requested_facility_count": len(local), "map_side_m": config.map_side_m,
                  "layout_s15": failure.family["layout_s15"], "layout_config_sha256": config_sha,
                  "obstacle_placements": [], "radar_placements": [], "initial_states": [],
                  "vehicle_count": 0, "task_altitude_m": config.altitude_min_m, "cruise_speed_m_s": 0}
        raise SamplingRejected(failure.code, draft, family) from failure


def sample_family_s15(seed, config=None, policy=None):
    if isinstance(seed,bool) or not isinstance(seed,int) or seed < 0:
        raise ValueError("Family seed must be a nonnegative integer")
    policy = policy or SamplingPolicy()
    rng = random.Random(seed)
    count = facility_count(rng)
    config = replace(config or SceneConfig(),map_side_m=MAP_SIDES_M[count])
    layout = "single" if count==1 else rng.choice(["isolated","clustered","linear"])
    local = []
    for _ in range(count):
        contour = _contour(rng,True)
        d3 = rng.uniform(50,150)
        d2 = d3+rng.uniform(150,400)
        d1 = d2+rng.uniform(300,800)
        local.append((contour,d3,d2,d1))
    cfg, config_sha = load_layout_config()
    placement, facility_sampling = _place_in_world(rng, local, layout, config, cfg, seed, policy, config_sha)
    centers, entries, normals, config = placement
    entities,facilities,layers = [],[],{}
    for i,((contour,d3,d2,d1),center) in enumerate(zip(local,centers)):
        identifier = f"facility_{i+1:02d}"
        facility = {"id": identifier,"type": "facility","geometry": _move(contour,center)}
        entities.append(facility)
        facilities.append(facility)
        layers[identifier] = {}
        for layer,offset in [("protected",d3),("alert",d2),("warning",d1)]:
            zone = {"id": f"{identifier}_{layer}","type": "protection_zone","facility_id": identifier,
                    "layer": layer,"offset_m": offset,"geometry": expand_geometry(facility["geometry"],offset)}
            entities.append(zone)
            layers[identifier][layer] = zone
    world_geometry = _rectangle(0,0,config.map_side_m,config.map_side_m)
    obstacles, placements, obstacle_sampling = place_obstacles_s12(
        rng,facilities,layers,entries,to_shape(world_geometry),config,policy)
    entities.extend(obstacles)
    radar_placements = []
    for i in range(rng.randint(1,3)):
        placement = rng.choice(["facility_side","forward"])
        for attempt in range(1,policy.radar_attempts+1):
            facility = rng.choice(facilities)
            center = center_of(facility["geometry"])
            angle = rng.uniform(0,2*math.pi)
            layer = "alert" if placement=="facility_side" else "warning"
            boundary = radial_boundary(layers[facility["id"]][layer]["geometry"],center,angle)
            fraction = rng.uniform(.15,.75) if placement=="facility_side" else rng.uniform(.92,1.06)
            point = [center[j]+fraction*(boundary[j]-center[j]) for j in range(2)]
            if to_shape(world_geometry).covers(Point(point)):
                break
        else:
            # The full warning contour is inside the world, so its boundary is
            # a legal final forward draw; side draws use the facility center.
            point = boundary if placement=="forward" else center
        radar_id = f"radar_{i+1:02d}"
        entities.append({"id": radar_id,"type": "radar","geometry": {"type": "Point","position_m": point}})
        radar_placements.append({"radar_id": radar_id,"placement": placement,
                                 "reference_facility_id": facility["id"],"placement_attempts": attempt})
    scene = {"schema_version": SCHEMA_VERSION,"coordinate_system": "ENU","units": dict(UNITS),
             "world": {"id": "world","geometry": world_geometry},"entry_zones": entries,"entities": entities}
    vehicle_count = rng.randint(4,12)
    altitude = rng.uniform(config.altitude_min_m,config.altitude_max_m)
    speed,spacing = rng.uniform(4,10),rng.uniform(15,25)
    allocations = [i%len(entries) for i in range(vehicle_count)]
    rng.shuffle(allocations)
    per_entry = [allocations.count(i) for i in range(len(entries))]
    occupied = [0]*len(entries)
    states = []
    for index in allocations:
        entry = entries[index]
        center = center_of(entry["geometry"])
        normal = normals[entry["id"]]
        offset = (occupied[index]-(per_entry[index]-1)/2)*spacing
        occupied[index] += 1
        point = [center[0]-normal[1]*offset,center[1]+normal[0]*offset]
        angle = math.atan2(normal[1],normal[0])+rng.uniform(-.15,.15)
        initial_speed = rng.uniform(0,.25*speed)
        states.append({"entry_id": entry["id"],"position_enu_m": [*point,altitude],
                       "velocity_enu_m_s": [initial_speed*math.cos(angle),initial_speed*math.sin(angle),0.0],
                       "acceleration_enu_m_s2": [0.0,0.0,0.0]})
    handles = [f"uav_{i+1:02d}" for i in range(vehicle_count)]
    rng.shuffle(handles)
    for state,handle in zip(states,handles):
        state["agent_id"] = handle
    rng.shuffle(states)
    family = {"schema_version": "traj2language.family_initial/0.7-s1.2","generator_version": GENERATOR_VERSION,
              "sampling_revision": "s1.5","sampling_policy": asdict(policy),
              "family_id": f"family_s15_{seed:016x}","map_id": f"map_s15_{seed:016x}",
              "sampling_seed": seed,"config": asdict(config),"layout": layout,
              "facility_sampling": facility_sampling,"obstacle_sampling": obstacle_sampling,
              "obstacle_placements": placements,"radar_placements": radar_placements,
              "vehicle_count": vehicle_count,"task_altitude_m": altitude,"cruise_speed_m_s": speed,
              "lateral_spacing_m": spacing,"initial_states": states,
              "observation_profile": {"position_sigma0_m": rng.uniform(.2,.5),
                                      "position_slope_m_per_km": rng.uniform(.1,.3),
                                      "velocity_sigma0_m_s": rng.uniform(.03,.08),
                                      "velocity_slope_m_s_per_km": rng.uniform(.01,.03)}}
    family.update(layout_s15=facility_sampling, layout_config_sha256=config_sha, map_side_m=config.map_side_m)
    if not obstacles:
        raise SamplingRejected("sampling_no_obstacle_placed",scene,family)
    validate_public_scene(scene)
    return scene,family
