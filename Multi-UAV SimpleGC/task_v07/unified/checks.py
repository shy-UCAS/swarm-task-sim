"""Whole-route exact checks with witnesses; no constant-speed spacing gate."""
import math
from itertools import combinations
import numpy as np

from task_v07.geometry import geometry_facts, offset_geometry
from task_v07.expansion.contracts import P0ContractError, validate_route_bundle
from .config import load_generator
from .free_space import TOL, free_space
from .route import line_interval


def warning_visits(points, warning):
    intervals = []; offset = 0.; entry = None
    for i, (a, b) in enumerate(zip(points, points[1:])):
        length = float(np.linalg.norm(b-a)); direction = (b-a)/length
        hit = line_interval(warning, a, direction)
        if hit is not None:
            low, high = max(0., hit[0]), min(length, hit[1])
            if high-low > TOL:
                if entry is None:
                    entry = {"segment": i, "distance_on_segment_m": low, "point": (a+low*direction).tolist(),
                             "direction": direction.tolist(), "straight_before_warning_m": low}
                begin, end = offset+low, offset+high
                if intervals and begin <= intervals[-1][1]+TOL:
                    intervals[-1][1] = end
                else:
                    intervals.append([begin, end])
        offset += length
    return intervals, entry


def heading_difference(directions):
    return max((math.degrees(math.acos(float(np.clip(np.dot(a, b)/(np.linalg.norm(a)*np.linalg.norm(b)), -1., 1.))))
                for a, b in combinations(directions, 2)), default=0.)


def plan_checks(scene, spec, bundle, template, free=None, initial_states=None):
    free = free_space(scene, spec) if free is None else free
    if set(template["references"]) != set(spec["members"]):
        raise P0ContractError("Geometry template reference identities differ")
    validate_route_bundle(bundle, spec["members"])
    starts = None if initial_states is None else {s["agent_id"]: s["position_enu_m"] for s in initial_states}
    warning = offset_geometry(free.target["geometry"], free.offsets["warning"])
    minimum = load_generator()["retreat"]["warning_clearance_m"]
    issues = []; members = {}; by_split = {}
    for agent in sorted(spec["members"]):
        points3 = np.asarray(bundle.waypoints_by_agent[agent]); points = points3[:, :2]
        reference = template["references"][agent]; local = []
        if reference["endpoint_enu_m"] != bundle.waypoints_by_agent[agent][-1]:
            raise P0ContractError("Endpoint metadata differs from actual final waypoint")
        if starts is not None and not np.array_equal(points3[0], starts[agent]):
            raise P0ContractError("Route changed registered initial position")
        if not np.all(points3[:, 2] == spec["family"]["task_altitude_m"]) or bundle.departure_delays_s[agent] != 0:
            raise P0ContractError("Geometry changed altitude or introduced timing")
        for i, (a, b) in enumerate(zip(points, points[1:])):
            local.extend({"segment": i, **issue} for issue in free.segment_issues(a, b))
        visits, entry = warning_visits(points, warning)
        if len(visits) != 1:
            local.append({"code": "warning_visit_count", "count": len(visits), "required": 1, "intervals_route_m": visits})
        if entry is None or entry["straight_before_warning_m"] < free.cfg["alignment_length_m"]-TOL:
            local.append({"code": "alignment_length", "measured_m": None if entry is None else entry["straight_before_warning_m"],
                          "required_m": free.cfg["alignment_length_m"]})
        if reference.get("intermediate_dwell"):
            local.append({"code": "transit_planned_dwell"})
        legs = np.diff(points, axis=0); directions = legs/np.linalg.norm(legs, axis=1)[:, None]
        if any(float(a@b) <= -1.+1e-10 for a, b in zip(directions, directions[1:])):
            local.append({"code": "immediate_reversal"})
        clearances = {e["id"]: float(geometry_facts(e["geometry"], points[-1])["signed_distance_m"])
                      for e in scene["entities"] if e.get("layer") == "warning"}
        if min(clearances.values()) < minimum-TOL:
            local.append({"code": "retreat_warning_clearance", "clearances_m": clearances, "required_m": minimum})
        target_clearance = float(geometry_facts(warning, points[-1])["signed_distance_m"])
        if target_clearance > free.cfg["retreat_clearance_max_m"]+TOL:
            local.append({"code": "retreat_clearance_max", "measured_m": target_clearance})
        collection = reference.get("collection_point_enu_m")
        if collection is not None:
            distance = float(geometry_facts(warning, collection[:2])["signed_distance_m"])
            lo, hi = free.cfg["collection_clearance_m"]
            if distance < lo-TOL or distance > hi+TOL or not free.point_valid(collection[:2]):
                local.append({"code": "collection_clearance", "measured_m": distance, "range_m": [lo, hi]})
        if entry:
            by_split.setdefault(reference["split_index"], []).append(entry["direction"])
        members[agent] = {"status": "REJECT" if local else "PASS", "issues": local,
                          "warning_intervals_route_m": visits, "first_warning_entry": entry,
                          "retreat_clearances_m": clearances, "segment_count": len(points)-1}
        issues.extend({"agent_id": agent, **issue} for issue in local)
    averages = [np.mean(v, axis=0) for _, v in sorted(by_split.items())]
    angle = heading_difference(averages) if spec["approach_mode"] == "multi_direction" else None
    return {"status": "REJECT" if issues else "PASS", "issues": issues, "members": members,
            "scope": "all segments against original primitives; no nominal-spacing gate",
            "multi_max_pairwise_ingress_heading_deg": angle,
            "heading_aim_deg_diagnostic_only": free.cfg["multi_heading_aim_deg"],
            "observed_minimum_separation_m": None, "observed_spacing_reason": "planning_only_no_simulation"}
