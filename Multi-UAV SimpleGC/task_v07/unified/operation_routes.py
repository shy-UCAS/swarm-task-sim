"""Shared connections for work shapes, with source-derived phase anchors."""
from copy import deepcopy
import math
import numpy as np
from scene_v07.geometry import center_of
from task_v07.geometry import geometry_facts, offset_geometry
from task_v07.expansion.contracts import RouteBundle
from .assign import assign
from .route import _approaches, clean_joints, GeometryRejected, line_interval
from .operation_shapes import round_corners
from .config import load_generator
from .free_space import TOL
from .construction import retreat_endpoint


def connect(planner, points):
    result = [np.asarray(points[0])]
    for target in points[1:]:
        if np.linalg.norm(result[-1]-target) < 1e-8: continue
        path = planner.path(result[-1].tolist(), np.asarray(target).tolist())
        if path is None: raise GeometryRejected("no_interior_connection")
        result.extend(np.asarray(path)[1:])
    return clean_joints(result)


def route_operation(scene, spec, shape, free, initial_states, rng):
    states = {s["agent_id"]: s for s in initial_states}
    mapping = assign(spec["members"], {a: states[a]["position_enu_m"] for a in spec["members"]},
                     shape["slots"], spec["public_split"])
    planner = free.planner(); altitude = spec["family"]["task_altitude_m"]
    if planner is None: raise GeometryRejected("empty_connection_domain")
    minimum = load_generator()["retreat"]["warning_clearance_m"]
    warning = offset_geometry(free.target["geometry"], free.offsets["warning"])
    radius = spec["family"]["lateral_spacing_m"]/2; failures = []
    for attempt in range(free.cfg["connection_attempts"]):
        clearance = rng.uniform(*free.cfg["collection_clearance_m"])
        retreat = rng.uniform(minimum, free.cfg["retreat_clearance_max_m"])
        try:
            approaches, refs = _approaches(scene, spec, mapping, states, free, clearance)
            routes = {}; cost = 0.
            for agent, slot in sorted(mapping.items()):
                work = np.asarray(slot["work"], float); gate = np.asarray(slot["entry"])
                heading = np.asarray(slot["direction"])
                if slot.get("entry_to_work") in ("shared_tangent_parallel_lane", "straight_parallel_lane"):
                    incoming = [gate,work[0]]
                else:
                    inner = gate+free.cfg["alignment_length_m"]*heading
                    if not free.point_valid(inner): raise GeometryRejected("inner_alignment_blocked")
                    tangent = work[1]-work[0] if len(work)>1 else heading.copy()
                    tangent /= np.linalg.norm(tangent)
                    lead = work[0]-spec["family"]["lateral_spacing_m"]*tangent
                    incoming = connect(planner, [gate, inner, lead, work[0]])
                    incoming = round_corners(incoming, radius, free.cfg["chord_error_m"])
                outgoing = []
                if spec["role"] != "intrusion":
                    endpoint, retreat_check = retreat_endpoint(free, slot, retreat)
                    direction = np.asarray(slot["exit_direction"])
                    tail_direction = work[-1]-work[-2] if len(work)>1 else direction
                    tail_direction /= np.linalg.norm(tail_direction)
                    tail = work[-1]+spec["family"]["lateral_spacing_m"]*tail_direction
                    outgoing = round_corners(connect(planner, [work[-1], tail, endpoint]), radius, free.cfg["chord_error_m"])
                else:
                    endpoint = work[-1]
                points = clean_joints([*approaches[agent], *incoming[1:], *work[1:], *outgoing[1:]])
                routes[agent] = [[*p.tolist(), altitude] for p in points]
                refs[agent].update(deepcopy(slot.get("reference_fields", {})))
                refs[agent].update(endpoint_enu_m=[*endpoint.tolist(), altitude],
                    retreat_required=spec["role"] != "intrusion", retreat_warning_clearance_m=minimum,
                    work_points_enu_m=[[*p.tolist(), altitude] for p in work],
                    stage_geometry={"collection": refs[agent]["collection_point_enu_m"],
                        "warning_entry": [*gate.tolist(), altitude], "work_start": [*work[0].tolist(), altitude],
                        "work_end": [*work[-1].tolist(), altitude], "endpoint": [*endpoint.tolist(), altitude]})
                if "dwell_s" in slot:
                    indices = [i for i,p in enumerate(points) if np.linalg.norm(p-work[0]) < 1e-8]
                    if len(indices) != 1: raise GeometryRejected("dwell_anchor_lost")
                    refs[agent]["intermediate_dwell"] = {"waypoint_index": indices[0], "duration_s": slot["dwell_s"]}
                cost += float(np.linalg.norm(np.diff(approaches[agent], axis=0), axis=1).sum())
            center = np.asarray(center_of(free.target["geometry"]))
            mean = np.mean([p for s in shape["slots"] for p in s["work"]], axis=0)
            template = {"planning_version": "v07_m3b_unified_geometry_r1", "geometry_seed": spec["geometry_seed"],
                "references": refs, "source_units": spec["source_units"], "common_slot": spec["common_slot"],
                "retreat_warning_minimum_m": minimum, "work_area_bearing_deg": math.degrees(math.atan2(*(mean-center)[::-1]))%360,
                "public_approach_shape": spec["public_split"], "formation_split": spec["public_split"],
                "geometry_provenance": {"shape": shape["draw"], "connection_attempt": attempt,
                    "collection_clearance_m": clearance, "retreat_clearance_m": retreat, "connection_rejections": failures},
                "approach_length_m": cost, **deepcopy(shape.get("template_fields", {}))}
            return RouteBundle(routes, {a: 0. for a in spec["members"]}), template
        except GeometryRejected as exc:
            failures.append({"attempt": attempt, "reason": exc.reason, "evidence": exc.evidence})
    raise GeometryRejected("connection_search_budget_exhausted", failures)
