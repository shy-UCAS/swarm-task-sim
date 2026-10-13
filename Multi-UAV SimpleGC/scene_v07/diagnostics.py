"""Route diagnostics only: raw/margin blockers and cross-track departure."""
import math
from shapely.geometry import LineString, Point, Polygon


def blocks_straight(geometry, line):
    if geometry["type"] == "Circle":
        return line.distance(Point(geometry["center_m"])) < geometry["radius_m"] - 1e-7
    return Polygon(geometry["vertices_m"]).buffer(-1e-7).intersects(line)


def max_lateral_deviation(points, start, finish):
    if points is None:
        return None
    dx,dy = finish[0]-start[0],finish[1]-start[1]
    length = math.hypot(dx,dy)
    if length == 0:
        return 0.0
    # Absolute cross-track distance is piecewise linear on each path segment;
    # therefore its maximum is attained at one of the saved path vertices.
    return max((abs(dx*(p[1]-start[1])-dy*(p[0]-start[0]))/length for p in points),default=0.0)


def route_diagnostics(scene, family, planner, start, finish, points):
    line = LineString([start,finish])
    ids = [e["id"] for e in scene["entities"]
           if e["type"] == "hard_constraint_obstacle" and blocks_straight(e["geometry"],line)]
    entry_blockers = {p["obstacle_id"] for p in family["obstacle_placements"] if p["placement"] == "entry_blocking"}
    return {"straight_blocked_by_obstacle": bool(ids), "blocking_obstacle_ids": ids,
            "straight_blocked_by_entry_blocker": bool(set(ids)&entry_blockers),
            "straight_blocked_with_margin": planner.interior.intersects(line),
            "max_lateral_deviation_m": max_lateral_deviation(points,start,finish)}
