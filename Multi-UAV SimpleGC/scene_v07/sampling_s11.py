"""S1.1 conditional geometry sampling; original acceptance gates stay intact."""
from collections import Counter
from dataclasses import asdict, dataclass, replace
import math
import random

from shapely.geometry import LineString, Point

from .contract import SCHEMA_VERSION, UNITS, SceneConfig, validate_public_scene
from .geometry import center_of, expand_geometry, radial_boundary, to_shape
from .sampling import _contour, _entries, _move, _radius, _rectangle

GENERATOR_VERSION = "traj2language.scene_sampler/0.7-s1.3"
MAP_SIDES_M = {1: 4000.0, 2: 5000.0, 3: 6000.0}


@dataclass(frozen=True)
class SamplingPolicy:
    facility_attempts: int = 128
    obstacle_attempts: int = 48
    radar_attempts: int = 80

    def __post_init__(self):
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in asdict(self).values()):
            raise ValueError("Placement budgets must be positive integers")


class SamplingRejected(ValueError):
    """An exhausted candidate proposal, never an invalid public scene export."""
    def __init__(self, code, scene, family):
        super().__init__(code)
        self.code, self.scene, self.family = code, scene, family


def facility_count(rng):
    value = rng.random()
    return 1 if value < .4 else (2 if value < .75 else 3)


def _layout_offsets(rng, local, layout):
    count = len(local)
    if count == 1:
        return [[0.0, 0.0]]
    extent = [_radius(g) + (d1 if layout == "isolated" else d2) for g, _, d2, d1 in local]
    if layout == "linear":
        positions = [0.0]
        for i in range(1, count):
            positions.append(positions[-1] + extent[i-1] + extent[i] + rng.uniform(40, 200))
        offsets = [[x, 0.0] for x in positions]
    else:
        distance = extent[0] + extent[1] + rng.uniform(40, 160)
        offsets = [[0.0, 0.0], [distance, 0.0]]
        if count == 3:
            da = extent[0] + extent[2] + rng.uniform(40, 160)
            db = extent[1] + extent[2] + rng.uniform(40, 160)
            x = (da*da + distance*distance - db*db) / (2*distance)
            offsets.append([x, math.sqrt(max(0.0, da*da - x*x))])
    angle = rng.uniform(0, 2*math.pi)
    cosine, sine = math.cos(angle), math.sin(angle)
    return [[x*cosine-y*sine, x*sine+y*cosine] for x,y in offsets]


def _place_facilities(rng, local, layout, entries, config, policy):
    q = config.checking_quad_segs
    warning_shapes = [to_shape(expand_geometry(g, d1), q, True) for g, _, _, d1 in local]
    entry_shapes = [to_shape(e["geometry"]) for e in entries]
    failures, last = Counter(), None
    for attempt in range(1, policy.facility_attempts + 1):
        offsets = _layout_offsets(rng, local, layout)
        low_x = max(-w.bounds[0]-c[0] for w,c in zip(warning_shapes, offsets))
        high_x = min(config.map_side_m-w.bounds[2]-c[0] for w,c in zip(warning_shapes, offsets))
        low_y = max(-w.bounds[1]-c[1] for w,c in zip(warning_shapes, offsets))
        high_y = min(config.map_side_m-w.bounds[3]-c[1] for w,c in zip(warning_shapes, offsets))
        if low_x >= high_x or low_y >= high_y:
            failures["layout_has_no_complete_warning_fit"] += 1
            continue
        anchor = [rng.uniform(low_x, high_x), rng.uniform(low_y, high_y)]
        centers = [[anchor[j]+offset[j] for j in range(2)] for offset in offsets]
        last = centers
        warnings = [to_shape(expand_geometry(_move(g,c), d1),q,True)
                    for (g,_,_,d1),c in zip(local,centers)]
        if any(w.distance(e) <= config.safety_margin_m for w in warnings for e in entry_shapes):
            failures["warning_near_entry"] += 1
            continue
        alerts = [to_shape(expand_geometry(_move(g,c),d2),q,True)
                  for (g,_,d2,_),c in zip(local,centers)]
        if any(a.intersects(b) for i,a in enumerate(alerts) for b in alerts[:i]):
            failures["alert_overlap"] += 1
            continue
        if layout == "isolated" and any(a.intersects(b) for i,a in enumerate(warnings) for b in warnings[:i]):
            failures["isolated_warning_overlap"] += 1
            continue
        if layout == "clustered":
            seen = {0}
            for _ in warnings:
                for i,a in enumerate(warnings):
                    for j,b in enumerate(warnings):
                        if i in seen and a.intersects(b):
                            seen.add(j)
            if len(seen) != len(warnings):
                failures["cluster_warning_disconnected"] += 1
                continue
        return centers, {"attempts": attempt, "rejected_attempt_reasons": dict(failures), "exhausted": False}
    # A draft is retained for rejected-candidate visualization, never published
    # under the public-scene schema if construction did not complete.
    if last is None:
        last = [[config.map_side_m/2, config.map_side_m/2] for _ in local]
    return last, {"attempts": policy.facility_attempts, "rejected_attempt_reasons": dict(failures), "exhausted": True}


def obstacle_candidate(rng, placement, facilities, layers, entries, margin_m=30.0):
    shape = _contour(rng, False)
    record = {"placement": placement}
    if placement == "entry_blocking":
        entry, facility = rng.choice(entries), rng.choice(facilities)
        source, center = center_of(entry["geometry"]), center_of(facility["geometry"])
        dx,dy = center[0]-source[0], center[1]-source[1]
        distance = math.hypot(dx,dy)
        ux,uy = dx/distance, dy/distance
        ray = LineString([source,center])
        inside_entry = ray.intersection(to_shape(entry["geometry"]))
        entry_exit = max((x-source[0])*ux+(y-source[1])*uy for x,y in inside_entry.coords)
        angle = math.atan2(-dy,-dx)
        warning = radial_boundary(layers[facility["id"]]["warning"]["geometry"],center,angle)
        near_warning = distance-math.dist(center,warning)
        extent = _radius(shape)
        # Keep the complete obstacle beyond the entry's unchanged safety
        # margin, and before the complete warning contour.
        low,high = entry_exit+extent+margin_m+10, near_warning-extent-10
        if low >= high:
            return None, record, "entry_warning_gap_too_short"
        along = rng.uniform(low,high)
        point = [source[0]+along*ux, source[1]+along*uy]
        record.update(entry_id=entry["id"],reference_facility_id=facility["id"])
    elif placement == "facility_side":
        facility = rng.choice(facilities)
        center = center_of(facility["geometry"])
        angle = rng.uniform(0,2*math.pi)
        boundary = radial_boundary(layers[facility["id"]]["warning"]["geometry"],center,angle)
        distance = math.dist(center,boundary)+rng.uniform(-.6,.6)*_radius(shape)
        point = [center[0]+distance*math.cos(angle),center[1]+distance*math.sin(angle)]
        record.update(reference_facility_id=facility["id"])
    elif placement == "between_facilities":
        pair = rng.sample(facilities,2)
        a,b = [center_of(f["geometry"]) for f in pair]
        dx,dy = b[0]-a[0],b[1]-a[1]
        distance,angle = math.hypot(dx,dy),math.atan2(dy,dx)
        wa = math.dist(a,radial_boundary(layers[pair[0]["id"]]["warning"]["geometry"],a,angle))
        wb = math.dist(b,radial_boundary(layers[pair[1]["id"]]["warning"]["geometry"],b,angle+math.pi))
        if wa+wb < distance:
            low,high = wa,distance-wb
            position_kind = "warning_gap"
        else:
            low,high = max(0,distance-wb),min(distance,wa)
            position_kind = "warning_overlap"
        along = rng.uniform(low,high)
        point = [a[0]+along*dx/distance,a[1]+along*dy/distance]
        record.update(reference_facility_ids=[f["id"] for f in pair],position_kind=position_kind)
    else:
        raise ValueError("Unknown obstacle placement")
    return _move(shape,point), record, None


def _obstacle_problem(geometry, record, facilities, layers, entries, world, config):
    q = config.checking_quad_segs
    raw = to_shape(geometry,q,True)
    if not world.covers(raw):
        return "outside_world"
    for facility in facilities:
        if raw.intersects(to_shape(layers[facility["id"]]["alert"]["geometry"],q,True)):
            return "intersects_alert"
    safe = to_shape(expand_geometry(geometry,config.safety_margin_m),config.planning_quad_segs,True)
    if any(safe.intersects(to_shape(entry["geometry"])) for entry in entries):
        return "entry_or_margin_overlap"
    if record["placement"] == "facility_side":
        shape = to_shape(geometry,q)
        warning = to_shape(layers[record["reference_facility_id"]]["warning"]["geometry"],q)
        if not (shape.intersection(warning).area > 0 and shape.difference(warning).area > 0
                and warning.difference(shape).area > 0):
            return "not_partial_warning_overlap"
    elif record["placement"] == "entry_blocking":
        facility = next(f for f in facilities if f["id"] == record["reference_facility_id"])
        entry = next(e for e in entries if e["id"] == record["entry_id"])
        line = LineString([center_of(entry["geometry"]),center_of(facility["geometry"])])
        if not to_shape(geometry,q).buffer(-1e-7).intersects(line):
            return "does_not_block_straight_line"
        if raw.intersects(to_shape(layers[facility["id"]]["warning"]["geometry"],q,True)):
            return "not_between_entry_and_warning"
    return None


def place_obstacles(rng, facilities, layers, entries, world, config, policy, requested=None):
    requested = rng.randint(1,3) if requested is None else requested
    obstacles, placements, slots = [], [], []
    types = ["entry_blocking","facility_side"] + (["between_facilities"] if len(facilities)>1 else [])
    for index in range(requested):
        placement = rng.choice(types)
        failures = Counter()
        for attempt in range(1,policy.obstacle_attempts+1):
            geometry, record, problem = obstacle_candidate(rng,placement,facilities,layers,entries,config.safety_margin_m)
            if problem is None:
                problem = _obstacle_problem(geometry,record,facilities,layers,entries,world,config)
            if problem:
                failures[problem] += 1
                continue
            identifier = f"obstacle_{index+1:02d}"
            obstacles.append({"id": identifier,"type": "hard_constraint_obstacle","geometry": geometry})
            record.update(obstacle_id=identifier,placement_attempts=attempt)
            placements.append(record)
            break
        else:
            attempt = policy.obstacle_attempts
        slots.append({"slot": index+1,"placement": placement,"attempts": attempt,
                      "placed": len(obstacles)>0 and obstacles[-1]["id"]==f"obstacle_{index+1:02d}",
                      "rejected_attempt_reasons": dict(failures)})
    return obstacles, placements, {"requested_count": requested,"placed_count": len(obstacles),
                                    "skipped_count": requested-len(obstacles),"slots": slots}


def sample_family_s11(seed, config=None, policy=None):
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
    entries,normals = _entries(rng,config)
    centers, facility_sampling = _place_facilities(rng,local,layout,entries,config,policy)
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
    obstacles, placements, obstacle_sampling = place_obstacles(
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
              "sampling_revision": "s1.1","sampling_policy": asdict(policy),
              "family_id": f"family_s11_{seed:016x}","map_id": f"map_s11_{seed:016x}",
              "sampling_seed": seed,"config": asdict(config),"layout": layout,
              "facility_sampling": facility_sampling,"obstacle_sampling": obstacle_sampling,
              "obstacle_placements": placements,"radar_placements": radar_placements,
              "vehicle_count": vehicle_count,"task_altitude_m": altitude,"cruise_speed_m_s": speed,
              "lateral_spacing_m": spacing,"initial_states": states,
              "observation_profile": {"position_sigma0_m": rng.uniform(.2,.5),
                                      "position_slope_m_per_km": rng.uniform(.1,.3),
                                      "velocity_sigma0_m_s": rng.uniform(.03,.08),
                                      "velocity_slope_m_s_per_km": rng.uniform(.01,.03)}}
    if facility_sampling["exhausted"]:
        raise SamplingRejected("sampling_facility_placement_exhausted",scene,family)
    if not obstacles:
        raise SamplingRejected("sampling_no_obstacle_placed",scene,family)
    validate_public_scene(scene)
    return scene,family
