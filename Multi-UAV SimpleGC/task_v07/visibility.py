"""Finite visibility graph whose every point/edge predicate is exact geometry."""
import heapq
import math

import numpy as np

from .geometry import geometry_facts


def _support_nodes(geometry, margin, directions=32):
    """Exact supporting-line intersections; these are waypoint candidates only."""
    if geometry["type"] == "Circle":
        origin = np.array(geometry["center_m"])
        vertices = np.zeros((1, 2))
        offset = geometry["radius_m"]+margin
        edge_angles = []
    else:
        original = np.array(geometry["vertices_m"])
        origin = original.mean(axis=0)
        vertices = original-origin
        edges = np.roll(vertices, -1, axis=0)-vertices
        area = np.sum(vertices[:, 0]*np.roll(vertices[:, 1], -1)-vertices[:, 1]*np.roll(vertices[:, 0], -1))
        edge_angles = [math.atan2(-e[0], e[1])%(2*math.pi) if area>0 else math.atan2(e[0], -e[1])%(2*math.pi) for e in edges]
        offset = geometry.get("buffer_m", 0)+margin
    angles = sorted(set(round(a, 12) for a in [i*2*math.pi/directions for i in range(directions)]+edge_angles))
    normals = np.array([[math.cos(a), math.sin(a)] for a in angles])
    support = (normals@vertices.T).max(axis=1)+offset
    nodes = []
    for i in range(len(angles)):
        j = (i+1)%len(angles)
        matrix = normals[[i,j]]
        if abs(np.linalg.det(matrix)) > 1e-10:
            nodes.append((np.linalg.solve(matrix, support[[i,j]])+origin).tolist())
    return nodes


class ExactVisibilityPlanner:
    def __init__(self, scene, margin_m=35.0):
        self.world = scene["world"]["geometry"]
        self.obstacles = [e["geometry"] for e in scene["entities"] if e["type"]=="hard_constraint_obstacle"]
        self.margin = margin_m
        self._free_cache = {}
        self._visible_cache = {}
        nodes = list(self.world["vertices_m"])
        for obstacle in self.obstacles:
            nodes.extend(_support_nodes(obstacle, margin_m))
        self.vertices = sorted({tuple(p) for p in nodes if self.free(p)})
        self.adjacency = [[] for _ in self.vertices]
        for i,a in enumerate(self.vertices):
            for j,b in enumerate(self.vertices[:i]):
                if self.visible(a,b):
                    length = math.dist(a,b)
                    self.adjacency[i].append((j,length))
                    self.adjacency[j].append((i,length))
        self._sources = {}

    def free(self, point):
        key=tuple(point)
        if key in self._free_cache:
            return self._free_cache[key]
        answer=bool(geometry_facts(self.world, point)["signed_distance_m"] <= 1e-8) and all(
            geometry_facts(g, point)["signed_distance_m"] >= self.margin-1e-8 for g in self.obstacles)
        self._free_cache[key]=answer
        return answer

    def visible(self, start, finish):
        key=tuple(sorted((tuple(start),tuple(finish))))
        if key not in self._visible_cache:
            self._visible_cache[key]=self._visible_uncached(start,finish)
        return self._visible_cache[key]

    def _visible_uncached(self, start, finish):
        # World is convex; endpoint containment implies whole-segment containment.
        if not self.free(start) or not self.free(finish):
            return False
        if tuple(start) == tuple(finish):
            return True
        return all(geometry_facts(g,[start,finish],footprint=True)["clearance_m"] >= self.margin-1e-8
                   for g in self.obstacles)

    def path(self, start, finish):
        start,finish = list(start),list(finish)
        if not self.free(start) or not self.free(finish):
            return None
        if self.visible(start,finish):
            return [start,finish] if start!=finish else [start]
        key = tuple(start)
        if key not in self._sources:
            cost = [math.inf]*len(self.vertices)
            previous = [None]*len(self.vertices)
            queue = []
            for i,v in enumerate(self.vertices):
                if self.visible(start,v):
                    cost[i] = math.dist(start,v)
                    heapq.heappush(queue,(cost[i],i))
            while queue:
                distance,i = heapq.heappop(queue)
                if distance>cost[i]:
                    continue
                for j,length in self.adjacency[i]:
                    if distance+length<cost[j]-1e-10:
                        cost[j],previous[j] = distance+length,i
                        heapq.heappush(queue,(cost[j],j))
            self._sources[key] = cost,previous
        cost,previous = self._sources[key]
        choices = [(cost[i]+math.dist(v,finish),i) for i,v in enumerate(self.vertices)
                   if math.isfinite(cost[i]) and self.visible(v,finish)]
        if not choices:
            return None
        _,last = min(choices)
        chain = []
        while last is not None:
            chain.append(list(self.vertices[last]))
            last = previous[last]
        return [start,*reversed(chain),finish]
