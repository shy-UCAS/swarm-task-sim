"""Generic polygon visits and strip surveys for the two S2 development tasks."""
from copy import deepcopy
import hashlib
import math
import random

import numpy as np

from scene_v07.geometry import center_of
from .geometry import radial_boundary_exact
from .visibility import ExactVisibilityPlanner
from .survey import build_survey

PLANNING_VERSION = "v07_s2_annular_survey_v3"
MIN_INTRUSION_ENDPOINT_SEPARATION_M = 15.0


def seed_for(seed, purpose):
    return int.from_bytes(hashlib.sha256(f"v07s2:{seed}:{purpose}".encode()).digest()[:8], "big")


def scene_parts(scene, target_id):
    facility = next(e for e in scene["entities"] if e["id"] == target_id)
    zones = {e["layer"]: e for e in scene["entities"] if e.get("facility_id") == target_id}
    return facility, zones


def role_planner(scene, survey=False):
    copy = deepcopy(scene)
    if survey:
        for e in copy["entities"]:
            if e.get("layer") == "alert":
                e["type"] = "hard_constraint_obstacle"
    # Original 30 m obstacle clearance plus 5 m tracking allowance from M3.
    return ExactVisibilityPlanner(copy, 35.0)


def clean_route(points, planner):
    result = [list(points[0])]
    for point in points[1:]:
        if math.dist(result[-1], point) < 1:
            if len(result) == 1:
                continue
            if not planner.visible(result[-2], point):
                raise ValueError("No legal removal of sub-metre waypoint")
            result[-1] = list(point)
        else:
            result.append(list(point))
    if len(result) < 2 or any(math.dist(a,b)<1 for a,b in zip(result,result[1:])):
        raise ValueError("Route requires >=1 m adjacent waypoints")
    if not all(planner.visible(a,b) for a,b in zip(result,result[1:])):
        raise ValueError("Reference route crosses inflated constraint")
    return result


def joined_path(planner, stops):
    points = [list(stops[0])]
    for stop in stops[1:]:
        part = planner.path(points[-1],stop)
        if part is None:
            raise ValueError("No path for task geometry")
        points.extend(part[1:])
    return clean_route(points,planner)


def angular_span(degrees):
    ordered=sorted(float(x)%360 for x in degrees)
    if len(ordered)<2:
        return 0.0
    return 360-max(b-a for a,b in zip(ordered,ordered[1:]+[ordered[0]+360]))


def build_skeleton(scene, family, intent, index, target_id):
    if family["vehicle_count"] != 4:
        raise ValueError("This development slice requires an unchanged four-agent family")
    if intent not in ("penetration","reconnaissance"):
        raise ValueError("Only the requested two abstract task definitions are implemented")
    ids=sorted(s["agent_id"] for s in family["initial_states"])
    states={s["agent_id"]:s for s in family["initial_states"]}
    # Draw before constructing semantics; independent seed purpose excludes intent/target.
    column_seed=seed_for(family["sampling_seed"],f"column:{index}")
    order=ids[:]
    random.Random(column_seed).shuffle(order)
    facility,zones=scene_parts(scene,target_id)
    center=np.array(center_of(facility["geometry"]))
    planner=role_planner(scene,intent=="reconnaissance")
    altitude=family["task_altitude_m"]
    references={}
    common={"schema_version":"traj2language.skeleton/0.7-s2.3","skeleton_id":f"{family['family_id']}_s2r3_sk{index:02d}",
            "family_id":family["family_id"],"map_id":family["map_id"],"base_intent":intent,
            "target_id":target_id,"group_id":"task_group_01","members":ids,
            "role":"intrusion" if intent=="penetration" else "reconnaissance",
            "execution_method":"polygon_visit" if intent=="penetration" else "annular_sector_lawnmower",
            "agent_ids":order,"column_seed":column_seed,"cruise_speed_m_s":family["cruise_speed_m_s"],
            "intrusion_endpoint_min_spacing_m":MIN_INTRUSION_ENDPOINT_SEPARATION_M,"waypoint_min_spacing_m":1.0,
            "tracking_allowance_m":5.0,"obstacle_clearance_m":30.0,"initial_settle_s":20.0,
            "terminal_hold_s":2.0,"terminal_radius_m":1.0,"terminal_speed_m_s":0.15,
            "required_intrusion_depth_m":20.0,"sync_window_s":10.0,"batch_split_gap_s":20.0,
            "timing_jitter_halfwidth_s":3.0,"sequential_gap_range_s":[40.0,90.0],"planning_version":PLANNING_VERSION,
            "initial_states":deepcopy(family["initial_states"])}
    if intent=="penetration":
        # Generic radial visit handles: attach nearest angular stations by geometry.
        bearings={a:math.atan2(*(np.array(states[a]["position_enu_m"][:2])-center)[::-1]) for a in ids}
        origin=math.atan2(*(np.mean([states[a]["position_enu_m"][:2] for a in ids],axis=0)-center)[::-1])
        best=None
        import itertools
        for rotation in (0,30,-30,60,-60,90,-90,120,-120,180):
            angles=[origin+math.radians(rotation+x) for x in (-60,-20,20,60)]
            points=[]; ends=[]
            for theta in angles:
                unit=np.array([math.cos(theta),math.sin(theta)])
                boundary=np.array(radial_boundary_exact(zones["warning"]["geometry"],center,theta))
                points.append(boundary+60*unit)
                inner=np.array(radial_boundary_exact(zones["protected"]["geometry"],center,theta))
                ends.append(inner-40*unit)
            if not all(planner.visible(p.tolist(),e.tolist()) and planner.free(p.tolist()) for p,e in zip(points,ends)):
                continue
            if min(math.dist(a,b) for a,b in itertools.combinations(ends,2)) < MIN_INTRUSION_ENDPOINT_SEPARATION_M:
                continue
            for assignment in itertools.permutations(range(4)):
                routes={}
                try:
                    for a,j in zip(ids,assignment):
                        routes[a]=joined_path(planner,[states[a]["position_enu_m"][:2],points[j],ends[j]])
                except ValueError:
                    continue
                score=max(sum(math.dist(a,b) for a,b in zip(p,p[1:])) for p in routes.values())
                if best is None or score<best[0]:
                    best=(score,routes,assignment,angles,ends)
        if best is None:
            raise ValueError("No four distinct radial visits at >=90 degrees")
        _,routes,assignment,angles,ends=best
        for a,j in zip(ids,assignment):
            references[a]={"points_enu_m":[[*p,altitude] for p in routes[a]],
                           "endpoint_enu_m":[*ends[j].tolist(),altitude],
                           "approach_azimuth_deg":math.degrees(angles[j])%360}
        common["planned_approach_span_deg"]=angular_span([r["approach_azimuth_deg"] for r in references.values()])
    else:
        common["survey"],references=build_survey(scene,family,facility,zones,planner,joined_path,
                                                   seed_for(family["sampling_seed"],f"annular_survey:{index}"))
    common["role_geometry_parameters"]={
        "basis":"exact facility contour offsets",
        "planning_margin_m":planner.margin,
        "warning_band_offset_range_m":[zones["alert"]["offset_m"]+planner.margin,
                                       zones["warning"]["offset_m"]-planner.margin],
        "future_roles_not_implemented":{
            "monitoring_contour_offset_m":(zones["alert"]["offset_m"]+zones["warning"]["offset_m"])/2,
            "close_observation_offset_range_m":[zones["alert"]["offset_m"]+planner.margin,
                                                zones["alert"]["offset_m"]+2*planner.margin],
            "transit_minimum_warning_chord_m":400.0}}
    common["references"]=references
    return common
