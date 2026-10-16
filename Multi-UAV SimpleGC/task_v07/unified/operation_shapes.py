"""Role work shapes; the public split and family conditions are immutable."""
from copy import deepcopy
import math
import numpy as np
from scene_v07.geometry import center_of
from task_v07.geometry import geometry_facts, offset_geometry
from task_v07.survey import sector_area, lateral_bounds, survey_grid
from task_v07.expansion.contracts import PlannerUnavailable
from .route import GeometryRejected, line_interval, clean_joints
from .free_space import arc_points, TOL


def round_corners(points, radius, error=1.):
    """Tangent circular connectors; no angle-based acceptance threshold."""
    points = np.asarray(clean_joints(points)); result = [points[0]]
    for a, p, b in zip(points, points[1:], points[2:]):
        u, v = p-a, b-p; before, after = np.linalg.norm(u), np.linalg.norm(v)
        u /= before; v /= after
        cosine = float(np.clip(u@v, -1, 1)); cross = float(u[0]*v[1]-u[1]*v[0])
        if abs(cross) < 1e-8 or cosine < -1+1e-8:
            result.append(p); continue
        angle = math.acos(cosine)
        tangent = min(radius*math.tan(angle/2), .4*before, .4*after)
        r = tangent/math.tan(angle/2)
        start, finish = p-tangent*u, p+tangent*v
        normal = np.array([-u[1], u[0]])*np.sign(cross)
        center = start+r*normal
        sweep = math.copysign(angle, cross)
        arc = arc_points(center, r, math.atan2(*(start-center)[::-1]), sweep, error)
        if min(np.linalg.norm(np.diff(arc, axis=0), axis=1)) < 1:
            result.append(p)
        else:
            result.extend([start, *arc[1:-1], finish])
    return clean_joints([*result, points[-1]])


def gate_slots(spec, free, theta):
    center = np.asarray(center_of(free.target["geometry"]))
    warning = offset_geometry(free.target["geometry"], free.offsets["warning"])
    spacing = spec["family"]["lateral_spacing_m"]; slots = []
    for side, stock in enumerate(spec["public_split"]["members"]):
        angle = math.radians(theta)+spec["public_split"]["relative_bearings_rad"][side]
        direction = -np.array([math.cos(angle), math.sin(angle)])
        normal = np.array([-direction[1], direction[0]])
        for j in range(len(stock)):
            origin = center+(j-(len(stock)-1)/2)*spacing*normal
            hit = line_interval(warning, origin, direction)
            if hit is None: raise GeometryRejected("warning_gate_unavailable")
            entry = origin+hit[0]*direction
            slots.append({"split_index": side, "slot_id": f"{side}:{j}", "entry": entry.tolist(),
                          "direction": direction.tolist(), "member_lane": j})
    return slots


def nominal_coverage(survey, paths):
    """Exact sector-clipped straight segments with the existing disk/grid model."""
    grid = survey_grid(survey); covered = np.zeros(len(grid), bool)
    geometry = survey["geometry"]; radius2 = survey["footprint_radius_m"]**2
    for path in paths:
        planar = np.asarray(path)[:, :2]
        for a, b in zip(planar, planar[1:]):
            length = float(np.linalg.norm(b-a))
            if length < 1e-8: continue
            direction = (b-a)/length
            intervals = geometry_facts(geometry, a, line_direction=direction)["line_intervals_m"]
            for low, high in intervals:
                low, high = max(0, low), min(length, high)
                if high <= low: continue
                remaining = np.flatnonzero(~covered)
                if not len(remaining): return 1., len(grid)
                p = grid[remaining]; t = np.clip((p-a)@direction, low, high)
                covered[remaining] |= np.sum((p-a-t[:, None]*direction)**2, axis=1) <= radius2
    return (float(covered.mean()) if len(grid) else 0.), len(grid)


def search_shape(spec, free, rng, draw):
    p = spec["params"]; center = np.asarray(center_of(free.target["geometry"]))
    span = math.radians(rng.uniform(*p["span_deg"]))
    area = rng.uniform(*p["area_km2"])*1e6; overlap = rng.uniform(*p["overlap"])
    low, high = free.offsets["alert"]+free.cfg["forbidden_margin_m"], free.offsets["warning"]-free.cfg["world_margin_m"]
    sector = {"type": "ContourAnnularSector", "base_geometry": deepcopy(free.target["geometry"]),
              "center_m": center.tolist(), "inner_offset_m": low, "outer_offset_m": high,
              "start_angle_rad": math.radians(draw["direction_deg"])-span/2, "angle_span_rad": span}
    base = free.target["geometry"]
    bound = (base["radius_m"] if base["type"] == "Circle" else np.linalg.norm(np.asarray(base["vertices_m"])-center, axis=1).max())+high
    sector["bounding_radius_m"] = float(bound)
    draw.update(span_deg=math.degrees(span), area_m2=area, overlap=overlap)
    def area_at(inner):
        if base["type"] == "Circle": return .5*span*((base["radius_m"]+high)**2-(base["radius_m"]+inner)**2)
        return sector_area({**sector, "inner_offset_m": inner})
    if high <= low or area_at(low) < area: raise GeometryRejected("survey_area_unavailable", [draw.copy()])
    left, right = low, high
    for _ in range(32):
        middle = (left+right)/2
        if area_at(middle) > area: left = middle
        else: right = middle
    sector["inner_offset_m"] = (left+right)/2
    angle = math.radians(draw["direction_deg"])
    direction = np.array([math.cos(angle), math.sin(angle)]); axis = np.array([-direction[1], direction[0]])
    x0, x1 = lateral_bounds(sector, axis)
    footprint = .5*spec["family"]["task_altitude_m"]; spacing = 2*footprint*(1-overlap)
    count = math.ceil((x1-x0)/spacing)
    if count < len(spec["members"]): raise GeometryRejected("survey_insufficient_strips", [{"strip_count": count}])
    xs = (x0+x1)/2+(np.arange(count)-(count-1)/2)*spacing; lanes = []
    for x in xs:
        origin = center+x*axis
        hits = geometry_facts(sector, origin, line_direction=direction)["line_intervals_m"]
        if len(hits) != 1 or hits[0][1]-hits[0][0] < 1: raise GeometryRejected("survey_strip_unavailable")
        lanes.append([origin+hits[0][0]*direction, origin+hits[0][1]*direction])
    slots = gate_slots(spec, free, draw["direction_deg"])
    for slot, indices in zip(slots, np.array_split(np.arange(count), len(slots))):
        work = [point for j, index in enumerate(indices) for point in (lanes[index][::-1] if j%2 == 0 else lanes[index])]
        work = round_corners(work, spacing/2, free.cfg["chord_error_m"])
        outgoing = work[-1]-center; outgoing /= np.linalg.norm(outgoing)
        slot.update(work=[p.tolist() for p in work], exit_direction=outgoing.tolist(), reference_fields={
            "scan_geometry": sector, "scan_lane_endpoints_m": [p.tolist() for p in work],
            "scan_axis_enu": direction.tolist(), "scan_strip_count": len(indices),
            "scan_leg_count": len(indices), "scan_endpoint_definition": "actual rounded scan polyline vertices"})
    survey = {"geometry": sector, "area_m2": area_at(sector["inner_offset_m"]), "angle_span_deg": math.degrees(span),
              "bounds_m": [*(center-bound).tolist(), *(center+bound).tolist()],
              "model": "ideal_isotropic_horizontal_disk", "footprint_radius_m": footprint,
              "footprint_height_factor": .5, "strip_spacing_m": spacing, "strip_overlap_fraction": overlap,
              "strip_count": count, "grid_spacing_m": min(footprint/2, math.sqrt(area)/50),
              "lane_endpoint_radius_m": 5., "assumptions": "Geometric disk footprint; no detection/effect model"}
    fraction, size = nominal_coverage(survey, [slot["work"] for slot in slots])
    draw.update(nominal_group_coverage=fraction, grid_point_count=size)
    if fraction < p["nominal_coverage_min"]: raise GeometryRejected("nominal_coverage_shortfall", [draw.copy()])
    return {"kind": "area_search", "slots": slots, "template_fields": {"survey": survey}, "draw": draw}


def observation_shape(spec, free, rng, draw):
    from task_v07.criteria import load_criteria
    p = spec["params"]; maximum = min(p["clearance_max_m"], p["band_fraction_max"]*(free.offsets["warning"]-free.offsets["alert"]))
    if maximum < p["clearance_min_m"]: raise GeometryRejected("observation_band_empty")
    clearance = rng.uniform(p["clearance_min_m"], maximum); duration = rng.uniform(*p["duration_s"])
    curve = offset_geometry(free.target["geometry"], free.offsets["alert"]+clearance)
    slots = gate_slots(spec, free, draw["direction_deg"])
    for slot in slots:
        direction = np.asarray(slot["direction"]); origin = np.asarray(slot["entry"])
        hit = line_interval(curve, origin, direction)
        if hit is None or hit[0] < 0: raise GeometryRejected("observation_station_unavailable")
        point = origin+hit[0]*direction
        if not free.point_valid(point): raise GeometryRejected("observation_station_blocked")
        slot.update(work=[point.tolist()], exit_direction=(-direction).tolist(), dwell_s=duration,
                    reference_fields={"observation_point_enu_m": [*point.tolist(), spec["family"]["task_altitude_m"]]})
    points = np.asarray([s["work"][0] for s in slots])
    spacing = spec["family"]["lateral_spacing_m"]
    if any(np.linalg.norm(a-b) < spacing-TOL for i,a in enumerate(points) for b in points[i+1:]):
        raise GeometryRejected("observation_station_spacing")
    draw.update(observation_alert_clearance_m=clearance, dwell_s=duration)
    return {"kind": "close_observation", "slots": slots, "draw": draw,
            "template_fields": {"close_observation": {"observation_radius_m": load_criteria()["detectors"]["dwell"]["radius_m"],
                                                       "planned_dwell_s": duration}}}


def draw_operation(spec, region, rng, free):
    from .patrol_shape import patrol_shape
    builders = {"area_search": search_shape, "close_observation": observation_shape, "monitoring": patrol_shape}
    if spec["execution_method"] not in builders: raise PlannerUnavailable("Unified role not implemented")
    if region.is_empty: raise GeometryRejected("empty_work_region")
    rejected = []
    for index in range(free.cfg["shape_attempts"]):
        draw = {"direction_deg": rng.uniform(*spec["params"]["direction_deg"]), "shape_attempt": index}
        try:
            result = builders[spec["execution_method"]](spec, free, rng, draw)
            evidence = [dict(slot=slot["slot_id"], segment=i, **issue) for slot in result["slots"]
                        for i, (a,b) in enumerate(zip(slot["work"], slot["work"][1:])) for issue in free.segment_issues(a,b)]
            if evidence: raise GeometryRejected("work_segment_clearance", evidence)
            draw["rejected_shape_attempts"] = rejected
            return result
        except GeometryRejected as exc:
            if exc.reason == "patrol_band_too_narrow": raise
            rejected.append({"draw": draw.copy(), "reason": exc.reason, "evidence": exc.evidence})
    raise GeometryRejected("shape_search_budget_exhausted", rejected)
