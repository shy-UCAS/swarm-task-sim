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
                    incoming = direction
                    straight = low
                    if low <= TOL and i > 0:
                        previous = a-points[i-1]
                        straight = float(np.linalg.norm(previous))
                        incoming = previous/straight
                    entry = {"segment": i, "distance_on_segment_m": low, "point": (a+low*direction).tolist(),
                             "direction": incoming.tolist(), "straight_before_warning_m": straight}
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
        kind = spec["execution_method"]
        if kind == "intrusion":
            value=float(geometry_facts(free.target["geometry"],points[-1])["signed_distance_m"])
            low,high=spec["params"]["endpoint_distance_m"]
            if not low-TOL <= value <= high+TOL:
                local.append({"code":"intrusion_endpoint_distance","measured_m":value})
        if kind == "feint":
            alert_visits, _ = warning_visits(points, offset_geometry(free.target["geometry"],free.offsets["alert"]))
            if len(alert_visits) != 1:
                local.append({"code":"alert_visit_count","count":len(alert_visits),"required":1})
        if kind == "transit" and len(visits) != 1:
            local.append({"code": "warning_visit_count", "count": len(visits), "required": 1, "intervals_route_m": visits})
        if entry is None or entry["straight_before_warning_m"] < free.cfg["alignment_length_m"]-TOL:
            local.append({"code": "alignment_length", "measured_m": None if entry is None else entry["straight_before_warning_m"],
                          "required_m": free.cfg["alignment_length_m"]})
        if kind in ("transit", "feint") and reference.get("intermediate_dwell"):
            local.append({"code": "transit_planned_dwell"})
        legs = np.diff(points, axis=0); directions = legs/np.linalg.norm(legs, axis=1)[:, None]
        if kind in ("transit", "feint") and any(float(a@b) <= -1.+1e-10 for a, b in zip(directions, directions[1:])):
            local.append({"code": "immediate_reversal"})
        clearances = {e["id"]: float(geometry_facts(e["geometry"], points[-1])["signed_distance_m"])
                      for e in scene["entities"] if e.get("layer") == "warning"}
        if kind != "intrusion" and min(clearances.values()) < minimum-TOL:
            local.append({"code": "retreat_warning_clearance", "clearances_m": clearances, "required_m": minimum})
        target_clearance = float(geometry_facts(warning, points[-1])["signed_distance_m"])
        if kind != "intrusion" and target_clearance > free.cfg["retreat_clearance_max_m"]+TOL:
            local.append({"code": "retreat_clearance_max", "measured_m": target_clearance})
        collection = reference.get("collection_point_enu_m")
        if collection is not None:
            distance = float(geometry_facts(warning, collection[:2])["signed_distance_m"])
            lo, hi = free.cfg["collection_clearance_m"]
            if distance < lo-TOL or distance > hi+TOL or not free.point_valid(collection[:2]):
                local.append({"code": "collection_clearance", "measured_m": distance, "range_m": [lo, hi]})
        if kind == "close_observation":
            dwell = reference.get("intermediate_dwell", {})
            index = dwell.get("waypoint_index", -1)
            if not 0 < index < len(points)-1 or not spec["params"]["duration_s"][0] <= dwell.get("duration_s", 0) <= spec["params"]["duration_s"][1]:
                local.append({"code": "observation_dwell_contract"})
            else:
                clearance = float(geometry_facts(free.target["geometry"], points[index])["signed_distance_m"])-free.offsets["alert"]
                if clearance < spec["params"]["clearance_min_m"]-TOL:
                    local.append({"code": "observation_alert_clearance", "measured_m": clearance})
                if not np.allclose(points3[index], reference["observation_point_enu_m"], atol=1e-8, rtol=0):
                    raise P0ContractError("Dwell index differs from the actual observation point")
        if kind == "monitoring":
            rho = reference["patrol_offset_m"]
            distances = geometry_facts(free.target["geometry"], np.asarray(reference["work_points_enu_m"])[:, :2])["signed_distance_m"]
            if np.max(np.abs(distances-rho)) > 1e-6:
                local.append({"code": "patrol_lane_changed", "offset_m": rho})
            if not free.offsets["alert"]+spec["params"]["alert_clearance_m"]-TOL <= rho <= free.offsets["warning"]-spec["params"]["warning_inset_m"]+TOL:
                local.append({"code": "patrol_offset_outside_band", "offset_m": rho})
        if entry:
            by_split.setdefault(reference["split_index"], []).append(entry["direction"])
        members[agent] = {"status": "REJECT" if local else "PASS", "issues": local,
                          "warning_intervals_route_m": visits, "first_warning_entry": entry,
                          "retreat_clearances_m": clearances, "segment_count": len(points)-1}
        issues.extend({"agent_id": agent, **issue} for issue in local)
    if spec["execution_method"] == "area_search":
        from .operation_shapes import nominal_coverage
        fraction, size = nominal_coverage(template["survey"], [r["work_points_enu_m"] for r in template["references"].values()])
        if fraction < spec["params"]["nominal_coverage_min"]:
            issues.append({"code": "nominal_coverage_shortfall", "fraction": fraction, "grid_points": size})
    if spec["execution_method"] == "intrusion":
        ends=[np.asarray(r["endpoint_enu_m"]) for r in template["references"].values()]
        spacing=min((float(np.linalg.norm(a-b)) for a,b in combinations(ends,2)),default=float("inf"))
        if spacing < spec["family"]["lateral_spacing_m"]-TOL:
            issues.append({"code":"intrusion_endpoint_spacing","measured_m":spacing})
    if spec["execution_method"] == "monitoring":
        refs = list(template["references"].values())
        radii = sorted(r["patrol_offset_m"] for r in refs)
        if any(b-a < spec["family"]["lateral_spacing_m"]-TOL for a,b in zip(radii,radii[1:])):
            issues.append({"code": "patrol_lines_not_group_unique", "offsets_m": radii})
        if template["monitoring"]["form"] == "full" and len({r["patrol_rotation_sign"] for r in refs}) != 1:
            issues.append({"code": "patrol_rotation_inconsistent"})
    averages = [np.mean(v, axis=0) for _, v in sorted(by_split.items())]
    angle = heading_difference(averages) if spec["approach_mode"] == "multi_direction" else None
    return {"status": "REJECT" if issues else "PASS", "issues": issues, "members": members,
            "scope": "all segments against original primitives; no nominal-spacing gate",
            "multi_max_pairwise_ingress_heading_deg": angle,
            "heading_aim_deg_diagnostic_only": free.cfg["multi_heading_aim_deg"],
            "observed_minimum_separation_m": None, "observed_spacing_reason": "planning_only_no_simulation"}
