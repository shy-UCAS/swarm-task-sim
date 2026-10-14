"""One authoritative exact geometry query for all v0.7 task predicates.

Circles are analytic; convex polygons use projection to their original edges.
No arc tessellation is used for membership, distance, depth or route visibility.
"""
import math

import numpy as np
from shapely.geometry import LineString, Point, Polygon

GEOMETRY_VERSION = "exact_contour_and_sector_v2"
_LAYER_CODES = {"warning": 1, "alert": 2, "protected": 3}


def geometry_facts(geometry, xy, *, layer_offsets=None, footprint=False, line_direction=None):
    """Return exact signed distance, membership and optional facility layer.

    Negative distance is inside the filled contour. BufferedPolygon means the
    exact Euclidean offset of the original convex polygon, not a rendered arc.
    The closed-boundary convention is <= with no geometric tolerance inflation.
    For a convex polygon/segment footprint, clearance_m is its distance from the
    filled original primitive minus the exact radius/offset. Zero means contact.
    """
    xy = np.asarray(xy, dtype=float)
    if xy.ndim < 1 or xy.shape[-1] != 2 or not np.isfinite(xy).all():
        raise ValueError("Geometry queries require finite (..., 2) EN coordinates")
    kind = geometry["type"]
    if line_direction is not None:
        if xy.shape != (2,) or footprint or layer_offsets is not None:
            raise ValueError("Line query requires one origin")
        return {"line_intervals_m": _line_intervals(geometry, xy, np.asarray(line_direction, float))}
    if kind == "ContourAnnularSector":
        if footprint or layer_offsets is not None:
            raise ValueError("Sector supports exact point membership and line intervals")
        base = geometry_facts(geometry["base_geometry"], xy)["signed_distance_m"]
        relative = xy-np.asarray(geometry["center_m"])
        start = geometry["start_angle_rad"]
        end = start+geometry["angle_span_rad"]
        if not 0 < geometry["angle_span_rad"] <= math.pi:
            raise ValueError("Sector angle must be in (0, pi]")
        slacks = [base-geometry["inner_offset_m"], geometry["outer_offset_m"]-base,
                  -math.sin(start)*relative[..., 0]+math.cos(start)*relative[..., 1],
                  math.sin(end)*relative[..., 0]-math.cos(end)*relative[..., 1]]
        if "lateral_interval_m" in geometry:
            lateral = relative@np.asarray(geometry["lateral_axis"])
            low, high = geometry["lateral_interval_m"]
            slacks.extend((lateral-low, high-lateral))
        slack = np.minimum.reduce(slacks)
        # Each constraint is 1-Lipschitz. This is NOT Euclidean sector distance.
        return {"inside": slack >= 0, "constraint_slack_m": slack,
                "contour_signed_distance_m": base}
    if kind == "Circle":
        center = np.asarray(geometry["center_m"], dtype=float)
        signed = np.linalg.norm(xy-center, axis=-1)-geometry["radius_m"]
        base = None
        dilation = geometry["radius_m"]
    elif kind in ("Polygon", "BufferedPolygon"):
        vertices = np.asarray(geometry["vertices_m"], dtype=float)
        if np.array_equal(vertices[0], vertices[-1]):
            vertices = vertices[:-1]
        edges = np.roll(vertices, -1, axis=0)-vertices
        lengths2 = np.sum(edges*edges, axis=1)
        if len(vertices) < 3 or np.any(lengths2 == 0):
            raise ValueError("Nondegenerate convex contour required")
        delta = xy[..., None, :]-vertices
        fraction = np.clip(np.sum(delta*edges, axis=-1)/lengths2, 0, 1)
        closest = vertices+fraction[..., None]*edges
        distance = np.linalg.norm(xy[..., None, :]-closest, axis=-1).min(axis=-1)
        cross = edges[:, 0]*delta[..., 1]-edges[:, 1]*delta[..., 0]
        inside = np.all(cross >= 0, axis=-1) | np.all(cross <= 0, axis=-1)
        signed = np.where(inside, -distance, distance)-geometry.get("buffer_m", 0.0)
        base = vertices
        dilation = geometry.get("buffer_m", 0.0)
    else:
        raise ValueError("Only circle, convex polygon and exact polygon offset are areas")
    result = {"signed_distance_m": signed, "inside": signed <= 0,
              "distance_to_contour_m": np.maximum(signed, 0)}
    if layer_offsets is not None:
        if set(layer_offsets) != set(_LAYER_CODES):
            raise ValueError("Expected protected, alert and warning offsets")
        if not 0 < layer_offsets["protected"] < layer_offsets["alert"] < layer_offsets["warning"]:
            raise ValueError("Invalid nested layer offsets")
        level = np.zeros(np.shape(signed), np.int8)
        for layer in ("warning", "alert", "protected"):
            level = np.where(signed <= layer_offsets[layer], _LAYER_CODES[layer], level)
        result["layer"] = level
        # This is also exact inside the source contour: offset - signed distance.
        result["protected_depth_m"] = np.maximum(layer_offsets["protected"]-signed, 0)
    if footprint:
        if xy.ndim != 2 or not len(xy):
            raise ValueError("Footprint must be a point, segment, or convex polygon")
        query = Point(xy[0]) if len(xy) == 1 else LineString(xy) if len(xy) == 2 else Polygon(xy)
        primitive = Point(geometry["center_m"]) if kind == "Circle" else Polygon(base)
        result["clearance_m"] = float(primitive.distance(query)-dilation)
    return result


def radial_boundary_exact(geometry, center, angle):
    """Locate a ray/contour intersection using only the authoritative query."""
    center = np.asarray(center, float)
    direction = np.array([math.cos(angle), math.sin(angle)])
    if not geometry_facts(geometry, center)["inside"]:
        raise ValueError("Radial origin must be inside")
    lo, hi = 0.0, 1.0
    while geometry_facts(geometry, center+hi*direction)["inside"]:
        hi *= 2
    for _ in range(56):
        mid = (lo+hi)/2
        if geometry_facts(geometry, center+mid*direction)["inside"]:
            lo = mid
        else:
            hi = mid
    return (center+(lo+hi)/2*direction).tolist()


def offset_geometry(base, distance):
    """Construct an exact parallel contour; no sampled boundary."""
    if base["type"] == "Circle":
        return {**base, "radius_m": base["radius_m"]+distance}
    return {**base, "type": "BufferedPolygon", "buffer_m": base.get("buffer_m", 0)+distance}


def _clip_interval(interval, coefficient, constant):
    """Intersect with constant + coefficient*t >= 0."""
    lo, hi = interval
    if abs(coefficient) < 1e-14:
        return None if constant < 0 else (lo, hi)
    boundary = -constant/coefficient
    lo, hi = (max(lo, boundary), hi) if coefficient > 0 else (lo, min(hi, boundary))
    return (lo, hi) if lo <= hi else None


def _polygon_line(vertices, origin, direction):
    vertices = np.asarray(vertices, float)
    edges = np.roll(vertices, -1, axis=0)-vertices
    area = np.sum(vertices[:, 0]*np.roll(vertices[:, 1], -1)-vertices[:, 1]*np.roll(vertices[:, 0], -1))
    orientation = 1 if area > 0 else -1
    interval = (-math.inf, math.inf)
    for point, edge in zip(vertices, edges):
        delta = origin-point
        interval = _clip_interval(interval, orientation*(edge[0]*direction[1]-edge[1]*direction[0]),
                                  orientation*(edge[0]*delta[1]-edge[1]*delta[0]))
        if interval is None:
            break
    return interval


def _circle_line(center, radius, origin, direction):
    delta = origin-np.asarray(center)
    aa = float(direction@direction)
    bb = float(delta@direction)
    disc = bb*bb-aa*(float(delta@delta)-radius*radius)
    return None if disc < 0 else ((-bb-math.sqrt(disc))/aa, (-bb+math.sqrt(disc))/aa)


def _line_intervals(g, origin, direction):
    """Analytic line intersections of disks, exact offset capsules and sectors."""
    if np.linalg.norm(direction) == 0:
        raise ValueError("Nonzero line direction required")
    kind = g["type"]
    if kind == "ContourAnnularSector":
        outer = geometry_facts(offset_geometry(g["base_geometry"], g["outer_offset_m"]),
                               origin, line_direction=direction)["line_intervals_m"]
        if not outer:
            return []
        interval = outer[0]
        relative = origin-np.array(g["center_m"])
        start, end = g["start_angle_rad"], g["start_angle_rad"]+g["angle_span_rad"]
        halfplanes = [(np.array([-math.sin(start), math.cos(start)]), 0),
                      (np.array([math.sin(end), -math.cos(end)]), 0)]
        if "lateral_interval_m" in g:
            axis = np.array(g["lateral_axis"]);low, high = g["lateral_interval_m"]
            halfplanes += [(axis, -low), (-axis, high)]
        for normal, offset in halfplanes:
            interval = _clip_interval(interval, float(normal@direction), float(normal@relative)+offset)
            if interval is None:
                return []
        inner = geometry_facts(offset_geometry(g["base_geometry"], g["inner_offset_m"]),
                               origin, line_direction=direction)["line_intervals_m"]
        if not inner or inner[0][1] <= interval[0] or inner[0][0] >= interval[1]:
            return [interval]
        lo, hi = interval;a, b = inner[0]
        return [(x,y) for x,y in ((lo,min(a,hi)),(max(b,lo),hi)) if y > x]
    if kind == "Circle":
        result = _circle_line(g["center_m"], g["radius_m"], origin, direction)
        return [] if result is None else [result]
    vertices = np.asarray(g["vertices_m"], float)
    if np.array_equal(vertices[0], vertices[-1]):
        vertices = vertices[:-1]
    radius = g.get("buffer_m", 0)
    candidates = [_polygon_line(vertices, origin, direction)]
    if radius > 0:
        # Minkowski sum = original polygon union exact edge rectangles and disks.
        for a, b in zip(vertices, np.roll(vertices,-1,axis=0)):
            edge = b-a;normal = np.array([-edge[1],edge[0]])/np.linalg.norm(edge)*radius
            candidates.extend((_polygon_line([a+normal,b+normal,b-normal,a-normal],origin,direction),
                               _circle_line(a,radius,origin,direction)))
    candidates = [c for c in candidates if c is not None]
    return [(min(c[0] for c in candidates),max(c[1] for c in candidates))] if candidates else []


def radial_points_exact(geometry, center, angles):
    """Batched ray boundary coordinates, queried through geometry_facts."""
    center = np.asarray(center, float);angles = np.asarray(angles,float)
    direction = np.stack((np.cos(angles),np.sin(angles)),axis=-1)
    lo = np.zeros(angles.shape);hi = np.ones(angles.shape)
    while np.any(geometry_facts(geometry,center+hi[...,None]*direction)["inside"]):
        hi *= 2
    for _ in range(54):
        mid = (lo+hi)/2
        inside = geometry_facts(geometry,center+mid[...,None]*direction)["inside"]
        lo,hi = np.where(inside,mid,lo),np.where(inside,hi,mid)
    return center+((lo+hi)/2)[...,None]*direction
