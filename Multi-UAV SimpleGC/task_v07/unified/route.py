"""Shared finite connections and truthful RouteBundle metadata."""
from collections import defaultdict
import math

import numpy as np

from task_v07.geometry import geometry_facts, offset_geometry
from task_v07.expansion.contracts import RouteBundle
from task_v07.expansion.formation_corridors import start_line
from .assign import assign
from .free_space import arc_points, TOL
from .config import load_generator


class GeometryRejected(Exception):
    def __init__(self, reason, evidence=None):
        super().__init__(reason)
        self.reason = reason
        self.evidence = list(evidence or [])


def line_interval(geometry, origin, direction):
    intervals = geometry_facts(geometry, np.asarray(origin), line_direction=np.asarray(direction))["line_intervals_m"]
    return intervals[0] if intervals else None


def clean_joints(points):
    """Remove exact duplicates/forward-collinear joins, never a meaningful bend."""
    result = []
    for value in points:
        point = np.asarray(value, float)
        if result and np.linalg.norm(point-result[-1]) < 1e-8:
            continue
        while len(result) >= 2:
            a, b = result[-1]-result[-2], point-result[-1]
            if float(a @ b) > 0 and abs(float(a[0]*b[1]-a[1]*b[0])) <= 1e-8*np.linalg.norm(a)*np.linalg.norm(b):
                result.pop()
            else:
                break
        result.append(point)
    if len(result) < 2 or np.any(np.linalg.norm(np.diff(result, axis=0), axis=1) < 1.-TOL):
        raise GeometryRejected("sub_metre_semantic_join", [{"points": [p.tolist() for p in result],
            "segment_lengths_m": np.linalg.norm(np.diff(result, axis=0), axis=1).tolist()}])
    return result


def offset_lane(points, offset, error=1.):
    """Parallel line offsets, exact miters inside and <=1 m sagitta arcs outside."""
    points = np.asarray(points, float)
    if abs(offset) < 1e-8:
        return list(points)
    legs = np.diff(points, axis=0)
    if np.any(np.linalg.norm(legs, axis=1) < 1.):
        raise GeometryRejected("reference_short_segment")
    directions = legs / np.linalg.norm(legs, axis=1)[:, None]
    normals = np.c_[-directions[:, 1], directions[:, 0]]
    joints = [[points[0]+offset*normals[0]]]
    for i in range(1, len(points)-1):
        before, after = directions[i-1], directions[i]
        cosine = float(np.clip(before @ after, -1., 1.))
        cross = float(before[0]*after[1]-before[1]*after[0])
        if cosine <= -1.+1e-10:
            raise GeometryRejected("reference_reversal")
        if offset*cross >= 0 or abs(cross) < 1e-10:
            joints.append([points[i] + offset*(normals[i-1]+normals[i])/(1.+cosine)])
        else:
            begin = math.atan2(offset*normals[i-1, 1], offset*normals[i-1, 0])
            sweep = math.atan2(cross, cosine)
            # A sub-metre outer arc cannot export both endpoints. Its tangent
            # intersection retains the connector turn with bounded arc error;
            # work-shape bends are never processed by this lane discretizer.
            tangent_error = abs(offset)*(1/math.cos(abs(sweep)/2)-1)
            if 2*abs(offset)*math.sin(abs(sweep)/2) < 1. and tangent_error <= error:
                joints.append([points[i]+offset*(normals[i-1]+normals[i])/(1.+cosine)])
            else:
                joints.append(arc_points(points[i], abs(offset), begin, sweep, error))
    joints.append([points[-1]+offset*normals[-1]])
    for i, direction in enumerate(directions):
        if float((joints[i+1][0]-joints[i][-1]) @ direction) < 1.:
            raise GeometryRejected("lane_swallowtail")
    return clean_joints([p for joint in joints for p in joint])


def _approaches(scene, spec, mapping, states, free, clearance):
    approaches = {}; metadata = {}
    blocks = defaultdict(list)
    for agent, slot in mapping.items():
        blocks[(slot["split_index"], states[agent].get("entry_id", "none"))].append(agent)
    warning = offset_geometry(free.target["geometry"], free.offsets["warning"])
    exterior = free.planner(exterior=True)
    for (side, entry_id), agents in sorted(blocks.items()):
        direction = np.asarray(mapping[agents[0]]["direction"])
        normal = np.array([-direction[1], direction[0]])
        entries = {a: np.asarray(mapping[a]["entry"]) for a in agents}
        lateral = {a: float(entries[a] @ normal) for a in agents}
        middle = (min(lateral.values())+max(lateral.values()))/2
        offsets = {a: value-middle for a, value in lateral.items()}
        half = max(abs(x) for x in offsets.values())
        origin = middle*normal
        interval = line_interval(offset_geometry(warning, clearance), origin, direction)
        if interval is None:
            raise GeometryRejected("collection_line_unavailable")
        collection = origin+interval[0]*direction
        lead_t = min(interval[0], min(float(p @ direction) for p in entries.values())-free.cfg["alignment_length_m"])
        lead = origin+lead_t*direction
        starts = {a: np.asarray(states[a]["position_enu_m"][:2]) for a in agents}
        mean = np.mean(list(starts.values()), axis=0)
        inward, _ = start_line(scene, mean)
        planner = free.planner(half, exterior=True)
        if planner is None or exterior is None:
            raise GeometryRejected("empty_connection_domain")
        form = None
        for depth in (max(100., 2*half+50.), 100., 150., 200., 60.):
            point = mean+depth*inward
            if planner.free(point.tolist()) and exterior.visible(mean.tolist(), point.tolist()):
                form = point; break
        if form is None:
            raise GeometryRejected("form_up_unavailable", [{"split_index": side, "entry_id": entry_id}])
        path = planner.path(form.tolist(), lead.tolist())
        if path is None:
            raise GeometryRejected("no_exterior_connection", [{"split_index": side, "entry_id": entry_id,
                                                                "from": form.tolist(), "to": lead.tolist()}])
        entry_center = origin+float(np.mean([p @ direction for p in entries.values()]))*direction
        reference = clean_joints([mean, *path, entry_center])
        for agent in sorted(agents):
            lane = offset_lane(reference, offsets[agent], free.cfg["chord_error_m"])
            # Physical starts are immutable; only the join to the formed lane is new.
            points = clean_joints([starts[agent], *lane[1:-1], entries[agent]])
            if any(geometry_facts(warning, np.asarray([a, b]), footprint=True)["clearance_m"] < -TOL
                   for a, b in zip(points[:-2], points[1:-1])):
                raise GeometryRejected("warning_visit_before_alignment", [{"agent_id": agent}])
            approaches[agent] = points
            own_collection = collection+offsets[agent]*normal
            metadata[agent] = {"split_index": side, "slot_id": mapping[agent]["slot_id"],
                "collection_point_enu_m": [*own_collection.tolist(), spec["family"]["task_altitude_m"]],
                "alignment_point_enu_m": [*(lead+offsets[agent]*normal).tolist(), spec["family"]["task_altitude_m"]],
                "warning_entry_enu_m": [*entries[agent].tolist(), spec["family"]["task_altitude_m"]],
                "ingress_direction": direction.tolist(), "lane_offset_m": offsets[agent],
                "reference_obstacle_margin_m": free.cfg["obstacle_margin_m"] + free.cfg["corridor_half_width_factor"]*half + free.cfg["corridor_pad_m"]}
    return approaches, metadata


def route_group(scene, spec, shape, free, initial_states, rng):
    states = {s["agent_id"]: s for s in initial_states}
    starts = {a: states[a]["position_enu_m"] for a in spec["members"]}
    mapping = assign(spec["members"], starts, shape["slots"], spec["public_split"])
    warning = offset_geometry(free.target["geometry"], free.offsets["warning"])
    minimum = load_generator()["retreat"]["warning_clearance_m"]
    failures = []
    for attempt in range(free.cfg["connection_attempts"]):
        collection = rng.uniform(*free.cfg["collection_clearance_m"])
        retreat = rng.uniform(minimum, free.cfg["retreat_clearance_max_m"])
        try:
            approaches, references = _approaches(scene, spec, mapping, states, free, collection)
            routes = {}; cost = 0.
            for agent in sorted(spec["members"]):
                slot = mapping[agent]
                exit_point = np.asarray(slot["work"][-1])
                out_direction = np.asarray(slot["exit_direction"])
                interval = line_interval(offset_geometry(warning, retreat), exit_point, out_direction)
                if interval is None or interval[1] <= 0:
                    raise GeometryRejected("retreat_ray_unavailable", [{"agent_id": agent}])
                endpoint = exit_point+interval[1]*out_direction
                clearances = {e["id"]: float(geometry_facts(e["geometry"], endpoint)["signed_distance_m"])
                              for e in scene["entities"] if e.get("layer") == "warning"}
                if min(clearances.values()) < minimum-TOL or not free.point_valid(endpoint):
                    raise GeometryRejected("retreat_outside_available_domain", [{"agent_id": agent, "clearances_m": clearances,
                                                                                 "point": endpoint.tolist()}])
                cost += float(np.linalg.norm(np.diff(approaches[agent], axis=0), axis=1).sum())
                points = clean_joints([*approaches[agent], *slot["work"][1:], endpoint])
                routes[agent] = [[*p.tolist(), spec["family"]["task_altitude_m"]] for p in points]
                references[agent].update(endpoint_enu_m=routes[agent][-1], retreat_required=True,
                    retreat_warning_clearance_m=minimum, retreat_actual_clearances_m=clearances,
                    work_points_enu_m=[[*p, spec["family"]["task_altitude_m"]] for p in slot["work"]])
            center = np.asarray(free.target["geometry"].get("center_m", np.mean(free.target["geometry"].get("vertices_m", [[0., 0.]]), axis=0)))
            work_center = np.mean([p for slot in shape["slots"] for p in slot["work"]], axis=0)
            bearing = math.degrees(math.atan2(*(work_center-center)[::-1])) % 360.
            template = {"planning_version": "v07_m3a_unified_geometry_r1", "geometry_seed": spec["geometry_seed"],
                "references": references, "source_units": spec["source_units"], "common_slot": spec["common_slot"],
                "retreat_warning_minimum_m": minimum, "work_area_bearing_deg": bearing,
                "public_approach_shape": spec["public_split"], "formation_split": spec["public_split"],
                "geometry_provenance": {"shape": shape["draw"],
                    "connection_attempt": attempt, "collection_clearance_m": collection, "retreat_clearance_m": retreat,
                    "connection_rejections": failures}, "approach_length_m": cost}
            return RouteBundle(routes, {a: 0. for a in spec["members"]}), template
        except GeometryRejected as exc:
            failures.append({"attempt": attempt, "reason": exc.reason, "evidence": exc.evidence,
                             "collection_clearance_m": collection, "retreat_clearance_m": retreat})
    raise GeometryRejected("connection_search_budget_exhausted", failures)
