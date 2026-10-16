"""Candidate free domains; exact primitive queries remain authoritative."""
from copy import deepcopy
from dataclasses import dataclass, field
import math

import numpy as np
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from task_v07.geometry import geometry_facts, offset_geometry, radial_boundary_exact
from task_v07.visibility import ExactVisibilityPlanner
from task_v07.expansion.contracts import PlannerUnavailable
from .geometry_config import load_geometry

TOL = 1e-6  # Same numerical tolerance as the existing planning checks, not a margin.


def polygon_of(geometry):
    """Search approximation only; never used to accept a final segment."""
    if geometry["type"] == "Circle":
        return Point(geometry["center_m"]).buffer(geometry["radius_m"], quad_segs=64)
    return Polygon(geometry["vertices_m"]).buffer(geometry.get("buffer_m", 0.), quad_segs=64)


def arc_points(center, radius, start, sweep, error=1.):
    if radius <= 0 or error <= 0:
        raise ValueError("Positive radius and chord error required")
    step = 2 * math.acos(max(-1., 1. - min(error, radius) / radius))
    count = max(1, math.ceil(abs(sweep) / step))
    return [np.asarray(center) + radius * np.array([math.cos(start + sweep*i/count),
                                                   math.sin(start + sweep*i/count)]) for i in range(count+1)]


def offset_curve(geometry, rho, error=1.):
    """Exact offset points: polygon edge parallels joined by true vertex arcs."""
    if rho < 0:
        raise ValueError("This boundary constructor requires a nonnegative offset")
    if geometry["type"] == "Circle":
        return arc_points(geometry["center_m"], geometry["radius_m"] + rho, 0., 2*math.pi, error)
    vertices = np.asarray(geometry["vertices_m"], float)
    if np.array_equal(vertices[0], vertices[-1]):
        vertices = vertices[:-1]
    following = np.roll(vertices, -1, axis=0)
    if np.sum(vertices[:, 0]*following[:, 1] - vertices[:, 1]*following[:, 0]) < 0:
        vertices = vertices[::-1]
    radius = rho + geometry.get("buffer_m", 0.)
    if radius == 0:
        return [*vertices, vertices[0]]
    edges = np.roll(vertices, -1, axis=0) - vertices
    normals = np.c_[edges[:, 1], -edges[:, 0]] / np.linalg.norm(edges, axis=1)[:, None]
    result = []
    for i, point in enumerate(vertices):
        start = math.atan2(normals[i-1, 1], normals[i-1, 0])
        finish = math.atan2(normals[i, 1], normals[i, 0])
        result.extend(arc_points(point, radius, start, (finish-start) % (2*math.pi), error))
    return [*result, result[0]]


def subtract_intervals(intervals, blocked):
    result = list(intervals)
    for low, high in sorted(blocked):
        next_result = []
        for a, b in result:
            if high <= a or low >= b:
                next_result.append((a, b))
            else:
                if a < low: next_result.append((a, low))
                if high < b: next_result.append((high, b))
        result = next_result
    return result


def quantile_interval(intervals, q):
    if not 0 <= q <= 1 or not intervals:
        raise ValueError("Nonempty intervals and quantile in [0,1] required")
    value = q * sum(b-a for a, b in intervals)
    for a, b in intervals:
        if value <= b-a:
            return a + value
        value -= b-a
    return intervals[-1][1]


@dataclass
class FreeSpace:
    world: dict
    constraints: list
    target: dict
    offsets: dict
    cfg: dict
    candidate: object
    _planners: dict = field(default_factory=dict)

    def point_valid(self, point):
        return (float(geometry_facts(self.world, point)["signed_distance_m"]) <= -self.cfg["world_margin_m"] + TOL
                and all(float(geometry_facts(c["geometry"], point)["signed_distance_m"]) >= c["margin_m"] - TOL
                        for c in self.constraints))

    def segment_issues(self, a, b):
        points = np.asarray([a, b], float)[:, :2]
        issues = []
        world_clearance = -float(np.max(geometry_facts(self.world, points)["signed_distance_m"]))
        if world_clearance < self.cfg["world_margin_m"] - TOL:
            issues.append({"code": "world_margin", "entity_id": "world", "clearance_m": world_clearance,
                           "required_m": self.cfg["world_margin_m"]})
        for c in self.constraints:
            clearance = geometry_facts(c["geometry"], points, footprint=True)["clearance_m"]
            if clearance < c["margin_m"] - TOL:
                issues.append({"code": "constraint_clearance", "entity_id": c["id"], "clearance_m": clearance,
                               "required_m": c["margin_m"], "kind": c["kind"]})
        return issues

    def planner(self, half_width=0., exterior=False):
        """Private primitive view with margins applied once, planner.margin=0."""
        key = (float(half_width), bool(exterior))
        if key in self._planners:
            return self._planners[key]
        inset = polygon_of(self.world).buffer(-(self.cfg["world_margin_m"] + half_width), join_style=2)
        if inset.is_empty or inset.geom_type != "Polygon":
            self._planners[key] = None
            return None
        entities = []
        for c in self.constraints:
            margin = (self.cfg["obstacle_margin_m"] + self.cfg["corridor_half_width_factor"]*half_width
                      + self.cfg["corridor_pad_m"] if c["kind"] == "obstacle" and half_width > 0
                      else c["margin_m"] + half_width)
            entities.append({"id": c["id"], "type": "hard_constraint_obstacle",
                             "geometry": offset_geometry(c["geometry"], margin)})
        if exterior:
            entities.append({"id": "target_warning", "type": "hard_constraint_obstacle",
                             "geometry": offset_geometry(self.target["geometry"], self.offsets["warning"] + half_width)})
        view = {"world": {"geometry": {"type": "Polygon", "vertices_m": list(inset.exterior.coords)[:-1]}},
                "entities": entities}
        self._planners[key] = ExactVisibilityPlanner(view, margin_m=0.)
        return self._planners[key]

    def feasible_arcs(self, rho):
        """Finite candidate angular components; final routes still checked exactly."""
        base = self.target["geometry"]
        center = np.asarray(base.get("center_m", np.mean(base.get("vertices_m", [[0., 0.]]), axis=0)))
        contour = offset_geometry(base, rho)
        radius = max(np.linalg.norm(p-center) for p in offset_curve(base, rho, self.cfg["chord_error_m"]))
        count = max(4, math.ceil(2*math.pi / (2*math.acos(1-min(1., self.cfg["chord_error_m"]/radius)))))
        step = 2*math.pi/count
        good = [self.point_valid(radial_boundary_exact(contour, center, i*step)) for i in range(count)]
        if all(good): return [(0., 2*math.pi)]
        if not any(good): return []
        begin = next(i for i in range(count) if not good[i])
        arcs = []; start = None
        for k in range(1, count+1):
            i = (begin+k) % count
            angle = (begin+k)*step
            if good[i] and start is None: start = angle
            if not good[i] and start is not None:
                arcs.append((start, angle-step)); start = None
        return [(a, b) for a, b in arcs if b > a]


def free_space(scene, spec, config=None):
    if spec["execution_method"] != "transit" or spec["role"] != "transit":
        raise PlannerUnavailable("M3a unified geometry supports transit only; select legacy explicitly for regression")
    cfg = load_geometry() if config is None else deepcopy(config)
    target = next(e for e in scene["entities"] if e["id"] == spec["target_id"] and e["type"] == "facility")
    offsets = {e["layer"]: e["offset_m"] for e in scene["entities"] if e.get("facility_id") == target["id"]}
    constraints = []
    for entity in scene["entities"]:
        if entity["type"] == "hard_constraint_obstacle" or entity.get("layer") == "alert":
            kind = "obstacle" if entity["type"] == "hard_constraint_obstacle" else "forbidden_layer"
            constraints.append({"id": entity["id"], "geometry": deepcopy(entity["geometry"]), "kind": kind,
                                "margin_m": cfg["obstacle_margin_m"] if kind == "obstacle" else cfg["forbidden_margin_m"]})
    world = deepcopy(scene["world"]["geometry"])
    candidate = polygon_of(world).buffer(-cfg["world_margin_m"], join_style=2)
    candidate = candidate.difference(unary_union([polygon_of(offset_geometry(c["geometry"], c["margin_m"])) for c in constraints]))
    return FreeSpace(world, constraints, deepcopy(target), offsets, cfg, candidate)


def work_region(scene, spec, free):
    return free.candidate.intersection(polygon_of(offset_geometry(free.target["geometry"], free.offsets["warning"])))


def projection_range(geometry, normal):
    if geometry["type"] == "Circle":
        center = float(np.asarray(geometry["center_m"]) @ normal)
        return center-geometry["radius_m"], center+geometry["radius_m"]
    values = np.asarray(geometry["vertices_m"]) @ normal
    margin = geometry.get("buffer_m", 0.)
    return float(values.min()-margin), float(values.max()+margin)


def chord_intervals(free, direction, half_width):
    """Lateral intervals of complete warning chords avoiding forbidden primitives.

    Other obstacles are clipped to the warning for proposal projection only.
    Exact checks decide whether each selected full segment is actually legal.
    """
    normal = np.array([-direction[1], direction[0]])
    warning = offset_geometry(free.target["geometry"], free.offsets["warning"])
    lo, hi = projection_range(warning, normal)
    blocked = []
    warning_polygon = polygon_of(warning)
    for c in free.constraints:
        inflated = offset_geometry(c["geometry"], c["margin_m"])
        if c["id"] == free.target["id"] + "_alert" or (c["kind"] == "forbidden_layer" and c["geometry"] == offset_geometry(free.target["geometry"], free.offsets["alert"])):
            blocked.append(projection_range(inflated, normal))
        else:
            clipped = polygon_of(inflated).intersection(warning_polygon)
            if not clipped.is_empty:
                components = list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped]
                for component in components:
                    if component.geom_type == "Polygon":
                        values = np.asarray(component.exterior.coords) @ normal
                        blocked.append((float(values.min()), float(values.max())))
    return [(a+half_width, b-half_width) for a, b in subtract_intervals([(lo, hi)], blocked) if b-a > 2*half_width]
