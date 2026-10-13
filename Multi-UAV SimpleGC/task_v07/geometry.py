"""One authoritative exact geometry query for all v0.7 task predicates.

Circles are analytic; convex polygons use projection to their original edges.
No arc tessellation is used for membership, distance, depth or route visibility.
"""
import math

import numpy as np
from shapely.geometry import LineString, Point, Polygon

GEOMETRY_VERSION = "exact_convex_contour_distance_v1"
_LAYER_CODES = {"warning": 1, "alert": 2, "protected": 3}


def geometry_facts(geometry, xy, *, layer_offsets=None, footprint=False):
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
