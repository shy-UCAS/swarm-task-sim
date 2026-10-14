"""Facility-scaled annular sectors and parallel strip surveys (private tasks)."""
from copy import deepcopy
import math
import random

import numpy as np

from .geometry import geometry_facts, offset_geometry, radial_points_exact


def sector_area(geometry, order=16):
    """Polar quadrature over exact contours; never used for membership."""
    start=geometry["start_angle_rad"];span=geometry["angle_span_rad"]
    edges=np.linspace(start,start+span,math.ceil(math.degrees(span)/2)+1)
    nodes,weights=np.polynomial.legendre.leggauss(order)
    angles=((edges[:-1,None]+edges[1:,None])/2+np.diff(edges)[:,None]/2*nodes).ravel()
    center=np.array(geometry["center_m"]);base=geometry["base_geometry"]
    inner=radial_points_exact(offset_geometry(base,geometry["inner_offset_m"]),center,angles)-center
    outer=radial_points_exact(offset_geometry(base,geometry["outer_offset_m"]),center,angles)-center
    integrand=(np.sum(outer*outer,axis=1)-np.sum(inner*inner,axis=1))/2
    return float(np.sum(integrand.reshape(-1,order)*weights*np.diff(edges)[:,None]/2))


def sector_clear(scene, sector, target_id, margin):
    """Conservative clearance proof using 1-Lipschitz bounds on exact queries.

    Whole boxes are accepted only if all of their points are clear. No sampled
    polygon represents the sector; unresolved boxes are rejected, never accepted.
    """
    constraints=[e["geometry"] for e in scene["entities"] if
                 e["type"]=="hard_constraint_obstacle" or
                 (e.get("layer")=="alert" and e.get("facility_id")!=target_id)]
    center=np.array(sector["center_m"]);radius=sector["bounding_radius_m"]
    pending=[(center,radius)]
    cells=0
    while pending:
        point,half=pending.pop();radius_box=math.sqrt(2)*half;cells+=1
        facts=geometry_facts(sector,point)
        if facts["constraint_slack_m"] < -radius_box:
            continue
        clearances=[-float(geometry_facts(scene["world"]["geometry"],point)["signed_distance_m"])-margin]
        clearances += [float(geometry_facts(g,point)["signed_distance_m"])-margin for g in constraints]
        if min(clearances)>=radius_box:
            continue
        if facts["inside"] and min(clearances)<0:
            return False
        if half<.01 or cells>100000:
            return False
        pending.extend((point+np.array([x,y])*half/2,half/2) for x,y in ((-1,-1),(-1,1),(1,-1),(1,1)))
    return True


def lateral_bounds(sector, axis):
    center=np.array(sector["center_m"]);base=sector["base_geometry"]
    outer=offset_geometry(base,sector["outer_offset_m"])
    angles=[sector["start_angle_rad"],sector["start_angle_rad"]+sector["angle_span_rad"]]
    candidates=list(radial_points_exact(outer,center,angles))
    for direction in (axis,-axis):
        if outer["type"]=="Circle":
            supports=[np.array(outer["center_m"])+outer["radius_m"]*direction]
        else:
            vertices=np.array(outer["vertices_m"]);projection=vertices@direction
            supports=vertices[projection>=projection.max()-1e-10]+outer["buffer_m"]*direction
        candidates.extend(p for p in supports if geometry_facts(sector,p)["inside"])
    values=(np.array(candidates)-center)@axis
    return float(values.min()),float(values.max())


def survey_grid(survey):
    geometry=survey.get("geometry",{"type":"Polygon","vertices_m":survey.get("vertices_m",[])})
    if "bounds_m" in survey:
        x0,y0,x1,y1=survey["bounds_m"]
    else:
        vertices=np.array(survey["vertices_m"]);x0,y0=vertices.min(axis=0);x1,y1=vertices.max(axis=0)
    step=survey["grid_spacing_m"]
    xx,yy=np.meshgrid(np.arange(x0+step/2,x1,step),np.arange(y0+step/2,y1,step))
    grid=np.c_[xx.ravel(),yy.ravel()]
    return grid[geometry_facts(geometry,grid)["inside"]]


def build_survey(scene, family, facility, zones, planner, join_route, seed):
    # Use the same exact source-contour centroid as the rest of the task planner.
    from scene_v07.geometry import center_of
    center=np.array(center_of(facility["geometry"]))
    base=facility["geometry"];margin=planner.margin
    low=zones["alert"]["offset_m"]+margin
    high=zones["warning"]["offset_m"]-margin
    if high<=low:
        raise ValueError("No positive-width warning annulus after margins")
    extent=base["radius_m"] if base["type"]=="Circle" else float(np.linalg.norm(np.array(base["vertices_m"])-center,axis=1).max())
    bound=extent+high
    altitude=family["task_altitude_m"];footprint=.5*altitude;spacing=2*footprint*.8
    ids=sorted(s["agent_id"] for s in family["initial_states"])
    states={s["agent_id"]:s for s in family["initial_states"]}
    rng=random.Random(seed)
    starts=list(np.arange(0,360,10)+rng.uniform(0,10));rng.shuffle(starts)
    spans=[rng.uniform(30,90),90.,75.,60.,45.,30.]
    attempts=0
    for span_deg in spans:
        for midpoint_deg in starts:
            attempts+=1;mid=math.radians(midpoint_deg);span=math.radians(span_deg)
            direction=np.array([math.cos(mid),math.sin(mid)]);axis=np.array([-direction[1],direction[0]])
            sector={"type":"ContourAnnularSector","base_geometry":deepcopy(base),"center_m":center.tolist(),
                    "inner_offset_m":low,"outer_offset_m":high,"start_angle_rad":mid-span/2,
                    "angle_span_rad":span,"bounding_radius_m":bound}
            area=sector_area(sector)
            if not 200000<=area<=600000 or not sector_clear(scene,sector,facility["id"],margin):
                continue
            fine_area=sector_area(sector,32)
            error=abs(fine_area-area)
            if error>.1 or not 200000<=fine_area<=600000:
                continue
            x0,x1=lateral_bounds(sector,axis)
            count=math.ceil((x1-x0)/spacing)
            if count<len(ids):
                continue
            xs=(x0+x1)/2+(np.arange(count)-(count-1)/2)*spacing
            lanes=[]
            for x in xs:
                origin=center+x*axis
                intervals=geometry_facts(sector,origin,line_direction=direction)["line_intervals_m"]
                segments=[]
                for lo,hi in intervals:
                    if hi-lo>=2*5+1:
                        segments.append([origin+(lo+5)*direction,origin+(hi-5)*direction])
                if not segments:
                    break
                lanes.append(segments)
            if len(lanes)!=count:
                continue
            assignment=sorted(ids,key=lambda a:float((np.array(states[a]["position_enu_m"][:2])-center)@axis))
            references={};partitions=np.array_split(np.arange(count),len(ids))
            try:
                for a,indices in zip(assignment,partitions):
                    left=x0 if indices[0]==0 else (xs[indices[0]-1]+xs[indices[0]])/2
                    right=x1 if indices[-1]==count-1 else (xs[indices[-1]]+xs[indices[-1]+1])/2
                    geometry={**sector,"lateral_axis":axis.tolist(),"lateral_interval_m":[float(left),float(right)]}
                    scan=[]
                    for j,index in enumerate(indices):
                        segments=lanes[index]
                        ordered=segments if j%2 else list(reversed(segments))
                        for segment in ordered:
                            scan.extend(segment if j%2 else list(reversed(segment)))
                    # The withdrawal point has exactly 200 m contour clearance,
                    # including for polygon facilities; radial +200 is insufficient.
                    angle=math.atan2(*(scan[-1]-center)[::-1])
                    exit_point=radial_points_exact(offset_geometry(base,zones["warning"]["offset_m"]+200),center,[angle])[0]
                    if not planner.free(exit_point):
                        raise ValueError("Withdrawal point blocked")
                    route=join_route(planner,[states[a]["position_enu_m"][:2],*scan,exit_point])
                    references[a]={"points_enu_m":[[*p,altitude] for p in route],
                                   "endpoint_enu_m":[*exit_point.tolist(),altitude],
                                   "scan_geometry":geometry,"scan_lane_endpoints_m":[p.tolist() for p in scan],
                                   "scan_axis_enu":direction.tolist(),"scan_strip_count":len(indices),
                                   "scan_leg_count":len(scan)//2,"retreat_required":True,
                                   "retreat_warning_clearance_m":200.0}
            except ValueError:
                continue
            grid_spacing=min(footprint/2,math.sqrt(fine_area)/50)
            survey={"geometry":sector,"area_m2":fine_area,"angle_span_deg":span_deg,
                    "area_quadrature_error_m2":error,"area_method":"polar Gauss quadrature on exact contours, 16/32 point check",
                    "bounds_m":[*(center-bound).tolist(),*(center+bound).tolist()],
                    "model":"ideal_isotropic_horizontal_disk","footprint_radius_m":footprint,
                    "footprint_height_factor":.5,"strip_spacing_m":spacing,"strip_overlap_factor":.8,
                    "strip_count":count,"grid_spacing_m":grid_spacing,"grid_scale_divisor":50,
                    "required_group_coverage":.90,"effective_speed_min_m_s":.5,"lane_endpoint_radius_m":5.,
                    "planning_margin_m":margin,"candidate_checks":attempts,
                    "assumptions":"Geometric coverage proxy; no camera, detection or recognition simulation"}
            return survey,references
    raise ValueError("No legal 0.2-0.6 km2, 30-90 degree annular sector")
