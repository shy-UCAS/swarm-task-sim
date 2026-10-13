"""Contour buffers and bounded visibility graphs for independent obstacles."""
import heapq
import math

import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

EPS_M = 1e-7


def expand_geometry(geometry, distance_m):
    """Exact Euclidean Minkowski-sum definition, not a center-radius surrogate."""
    if not math.isfinite(distance_m) or distance_m <= 0:
        raise ValueError("Expansion must be positive")
    if geometry["type"] == "Circle":
        return {"type": "Circle", "center_m": list(geometry["center_m"]),
                "radius_m": geometry["radius_m"] + distance_m}
    if geometry["type"] == "Polygon":
        return {"type": "BufferedPolygon",
                "vertices_m": [list(p) for p in geometry["vertices_m"]],
                "buffer_m": distance_m}
    if geometry["type"] == "BufferedPolygon":
        return {**geometry, "buffer_m": geometry["buffer_m"] + distance_m}
    raise ValueError("Only area contours may be expanded")


def _outer_polygon_buffer(polygon, distance, quad_segs):
    """Intersect exact supporting half-planes of polygon + radius-d disk.

    Uniform directions and every source edge normal bound the angular gaps.
    Each half-plane contains the analytic Minkowski sum, independently of
    GEOS's corner segment rounding. A local origin avoids large cancellations.
    """
    origin = polygon.centroid
    vertices = [(x - origin.x, y - origin.y) for x, y in list(polygon.exterior.coords)[:-1]]
    angles = [i * math.pi / (2 * quad_segs) for i in range(4 * quad_segs)]
    ccw = polygon.exterior.is_ccw
    for a, b in zip(vertices, vertices[1:] + vertices[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        nx, ny = (dy, -dx) if ccw else (-dy, dx)
        angles.append(math.atan2(ny, nx) % (2 * math.pi))
    unique = []
    for angle in sorted(angles):
        if not unique or angle - unique[-1] > 1e-10:
            unique.append(angle)
    if 2 * math.pi - unique[-1] < 1e-10:
        unique.pop()
    normals = [(math.cos(angle), math.sin(angle)) for angle in unique]
    support = [max(x * nx + y * ny for x, y in vertices) + distance for nx, ny in normals]
    points = []
    for i, (ax, ay) in enumerate(normals):
        j = (i + 1) % len(normals)
        bx, by = normals[j]
        determinant = ax * by - ay * bx
        x = (support[i] * by - ay * support[j]) / determinant
        y = (ax * support[j] - support[i] * bx) / determinant
        points.append((x + origin.x, y + origin.y))
    return Polygon(points)


def to_shape(geometry, quad_segs=64, conservative=False):
    """Render arcs or build an enclosing tangent polygon for safe planning.

    Circles use exact apothems. Buffered convex polygons use supporting
    half-planes instead of assuming a GEOS corner arc's segment angle.
    """
    kind = geometry["type"]
    scale = 1 / math.cos(math.pi / (4 * quad_segs)) if conservative else 1.0
    if kind == "Circle":
        return Point(geometry["center_m"]).buffer(
            geometry["radius_m"] * scale, quad_segs=quad_segs)
    if kind == "Point":
        return Point(geometry["position_m"])
    polygon = Polygon(geometry["vertices_m"])
    if kind == "BufferedPolygon":
        if conservative:
            return _outer_polygon_buffer(polygon, geometry["buffer_m"], quad_segs)
        return polygon.buffer(geometry["buffer_m"], quad_segs=quad_segs)
    if kind != "Polygon":
        raise ValueError("Unsupported geometry")
    return polygon


def center_of(geometry):
    if geometry["type"] == "Circle":
        return list(geometry["center_m"])
    center = Polygon(geometry["vertices_m"]).centroid
    return [center.x, center.y]


def radial_boundary(geometry, center, angle_rad):
    direction = (math.cos(angle_rad), math.sin(angle_rad))
    if geometry["type"] == "Circle":
        distance = geometry["radius_m"]
    else:
        ray = LineString([center, [center[0] + 20000 * direction[0],
                                  center[1] + 20000 * direction[1]]])
        segment = ray.intersection(to_shape(geometry))
        distance = max((p[0] - center[0]) * direction[0] +
                       (p[1] - center[1]) * direction[1] for p in segment.coords)
    return [center[0] + distance * direction[0], center[1] + distance * direction[1]]


def polygon_parts(shape):
    if shape.is_empty:
        return []
    if shape.geom_type == "Polygon":
        return [shape]
    if shape.geom_type in ("MultiPolygon", "GeometryCollection"):
        return [part for child in shape.geoms for part in polygon_parts(child)]
    return []


def polyline_length(points):
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


class VisibilityPlanner:
    """Shortest paths on a conservative polygonal visibility graph.

    Only hard_constraint_obstacle entities are inflated. Protection zones are
    deliberately absent. Overlapping buffers are unioned before vertex creation.
    The world is closed; no path can detour through its exterior. Obstacle
    boundaries may be followed, with only 1e-7 m numerical tolerance.
    """
    def __init__(self, scene, margin_m=30.0, quad_segs=8):
        if not math.isfinite(margin_m) or margin_m < 0:
            raise ValueError("Invalid safety margin")
        self.world = to_shape(scene["world"]["geometry"])
        obstacles = [e for e in scene["entities"] if e["type"] == "hard_constraint_obstacle"]
        self.obstacle_shapes = [to_shape(expand_geometry(e["geometry"], margin_m),
                                        quad_segs, conservative=True)
                                if margin_m else to_shape(e["geometry"], quad_segs, True)
                                for e in obstacles]
        self.blocked = unary_union(self.obstacle_shapes)
        self.interior = self.blocked.buffer(-EPS_M)
        points = list(self.world.exterior.coords)[:-1]
        # Do not clip the blocked set: an obstacle spanning the world edge must
        # remain a barrier, not create an artificial traversable boundary seam.
        for polygon in polygon_parts(self.blocked):
            for ring in [polygon.exterior, *polygon.interiors]:
                points.extend(list(ring.coords)[:-1])
        self.vertices = sorted({(float(x), float(y)) for x, y in points if self.free([x, y])})
        self.adjacency = [[] for _ in self.vertices]
        pairs = [(i, j) for i in range(len(self.vertices)) for j in range(i)]
        if pairs:
            coordinates = [[self.vertices[i], self.vertices[j]] for i, j in pairs]
            lines = shapely.linestrings(coordinates)
            visible = shapely.covers(self.world, lines) & ~shapely.intersects(self.interior, lines)
            for (i, j), allowed in zip(pairs, visible):
                if allowed:
                    distance = math.dist(self.vertices[i], self.vertices[j])
                    self.adjacency[i].append((j, distance))
                    self.adjacency[j].append((i, distance))
        self._sources = {}

    def free(self, point):
        p = Point(point)
        return self.world.covers(p) and not self.interior.intersects(p)

    def visible(self, start, finish):
        if not self.free(start) or not self.free(finish):
            return False
        if start == finish:
            return True
        line = LineString([start, finish])
        return self.world.covers(line) and not self.interior.intersects(line)

    def _visible_vertices(self, point):
        if not self.vertices:
            return []
        lines = shapely.linestrings([[point, vertex] for vertex in self.vertices])
        visible = shapely.covers(self.world, lines) & ~shapely.intersects(self.interior, lines)
        return [i for i, allowed in enumerate(visible) if allowed]

    def _source_tree(self, source):
        key = tuple(source)
        if key in self._sources:
            return self._sources[key]
        costs = [math.inf] * len(self.vertices)
        previous = [None] * len(self.vertices)
        heap = []
        for i in self._visible_vertices(source):
            costs[i] = math.dist(source, self.vertices[i])
            heapq.heappush(heap, (costs[i], i))
        while heap:
            cost, i = heapq.heappop(heap)
            if cost > costs[i]:
                continue
            for j, length in self.adjacency[i]:
                proposal = cost + length
                if proposal < costs[j] - 1e-10:
                    costs[j], previous[j] = proposal, i
                    heapq.heappush(heap, (proposal, j))
        self._sources[key] = costs, previous
        return costs, previous

    def path(self, start, finish):
        start, finish = list(start), list(finish)
        if not self.free(start) or not self.free(finish):
            return None
        if self.visible(start, finish):
            return [start, finish] if start != finish else [start]
        costs, previous = self._source_tree(start)
        choices = [(costs[i] + math.dist(self.vertices[i], finish), i)
                   for i in self._visible_vertices(finish) if math.isfinite(costs[i])]
        if not choices:
            return None
        _, last = min(choices)
        chain = []
        while last is not None:
            chain.append(list(self.vertices[last]))
            last = previous[last]
        return [start, *reversed(chain), finish]
