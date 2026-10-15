"""Finite annular-sector survey candidates, separate from the frozen slice."""
from copy import deepcopy
from collections import Counter, defaultdict
import math

import numpy as np

from task_v07.geometry import geometry_facts
from task_v07.planning import clean_route, joined_path
from task_v07.survey import sector_area, sector_clear, lateral_bounds
from .contracts import RouteBundle
from .formation_role_planners import Context
from .formation_corridors import shared_reference_corridor, offset_polyline, start_line


def balanced_partitions(lengths, count):
    """Minimax contiguous partition of actual strip lengths; each member works."""
    n = len(lengths)
    if not 1 <= count <= n:
        raise ValueError("Not enough nonempty strips for the group")
    prefix = np.r_[0., np.cumsum(lengths)]
    costs = np.full((count + 1, n + 1), np.inf)
    cuts = np.zeros((count + 1, n + 1), int)
    costs[0, 0] = 0.
    for k in range(1, count + 1):
        for end in range(k, n + 1):
            choices = [(max(costs[k - 1, begin], prefix[end] - prefix[begin]), begin)
                       for begin in range(k - 1, end)]
            costs[k, end], cuts[k, end] = min(choices)
    result = []
    end = n
    for k in range(count, 0, -1):
        begin = int(cuts[k, end])
        result.append(list(range(begin, end)))
        end = begin
    return list(reversed(result))


def planned_core_distance(points, scan_geometry):
    """First geometric scan entry along the entire planned approach."""
    distance = 0.
    for a, b in zip(points, points[1:]):
        length = float(np.linalg.norm(b - a))
        if length < 1e-9:
            continue
        intervals = geometry_facts(scan_geometry, a, line_direction=(b - a) / length)["line_intervals_m"]
        starts = [max(0., lo) for lo, hi in intervals if hi >= 0 and lo <= length]
        if starts:
            return distance + min(starts)
        distance += length
    return None


def heading_before_distance(points, distance):
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cumulative = np.r_[0., np.cumsum(lengths)]
    def at(d):
        i = min(int(np.searchsorted(cumulative, d, side="right") - 1), len(lengths) - 1)
        return points[i] + (d - cumulative[i]) / lengths[i] * (points[i + 1] - points[i])
    if distance is None or distance < 100:
        return None
    delta = at(distance) - at(distance - 100.)
    return math.degrees(math.atan2(delta[1], delta[0])) % 360


class AreaSearchPlanner:
    legacy_vertical_slice = False

    def plan(self, scene, group, params):
        return self.plan_with_template(scene, group, params)[0]

    def plan_with_template(self, scene, group, params):
        if 'candidate_budget' in params:
            from .candidate_search import plan_continuous_group
            return plan_continuous_group(scene,group,params)
        from .role_planners import PlanningInfeasible
        from .candidate_constraints import bearing_allowed
        ctx = Context(scene, group, params)
        base = ctx.rng.uniform(0., 2 * math.pi)
        angles = [base + k * math.pi / 12 for k in range(24)]
        ctx.rng.shuffle(angles)
        candidates, reasons = [], Counter()
        for angle in angles:
            if not bearing_allowed(angle, params):
                reasons['same_target_work_area_bearing'] += 1
                continue
            # The sector remains in the warning annulus. An inward entry needs
            # room for the same >=100m observable final straight as an outward entry.
            for span in (90., 75., 60., 45., 30.):
                candidate, reason = self.candidate(ctx, angle, span)
                if candidate is None:
                    reasons[reason] += 1
                    continue
                from task_v07.execution import departure_delays
                from .pipeline import COMMON_CONSTANTS
                from .geometry_checks import planning_layer_interval_check
                nominal = {a: 20. + ref["planned_core_distance_m"] / ctx.speed
                           for a, ref in candidate["template"]["references"].items()}
                timing = departure_delays({**COMMON_CONSTANTS, "members": group["members"],
                                          "column_seed": params["column_seed"]}, nominal)
                preview = planning_layer_interval_check(RouteBundle(candidate["routes"], {a: 0. for a in group["members"]}), timing, ctx.speed)
                if any(preview[mode]["below_warning"] for mode in ("synchronous", "sequential")):
                    reasons["nominal_full_route_interval"] += 1
                    continue
                candidate["template"]["planning_nominal_interval"] = preview
                candidates.append(candidate)
                break
            if candidates and ctx.multi:
                break
        if not candidates:
            raise PlanningInfeasible("geometry_infeasible", f"area_search finite candidates: {dict(reasons)}")
        minimum = min(c["length"] for c in candidates)
        pool = candidates if ctx.multi else [c for c in candidates if c["length"] <= 1.15 * minimum]
        selected = ctx.rng.choice(pool)
        template = selected["template"]
        template["formation_split"] = {"numeric_slot": ctx.slot, "members": ctx.split,
                                        "shared_between_timing_versions": True}
        template["direction_selection"] = {
            "minimum_approach_length_m": minimum, "selected_approach_length_m": selected["length"],
            "maximum_ratio": None if ctx.multi else 1.15, "feasible_candidates": len(candidates),
            "eligible_candidates": len(pool), "rejected_candidates": dict(reasons),
            "selection_order": "role constraints -> 115% route-length filter -> private random direction"}
        return RouteBundle(selected["routes"], {a: 0. for a in group["members"]}), template

    def candidate(self, ctx, angle, span_deg, *, area_m2=None, ingress_angle=None):
        from .role_planners import find_clear_retreat
        from .warning_approach import warning_ingress, deploy_inside_warning
        base, center = ctx.geometry, ctx.center
        widths = []
        for stock in ctx.split:
            by_entry = defaultdict(list)
            for a in stock:
                by_entry[ctx.states[a].get("entry_id", "none")].append(a)
            for members in by_entry.values():
                mean = np.mean([ctx.starts[a] for a in members], axis=0)
                inward, _ = start_line(ctx.scene, mean)
                normal = np.array([-inward[1], inward[0]])
                widths.append(max(abs(float((ctx.starts[a] - mean) @ normal)) for a in members))
        # The 100m approach is outside the warning zone; no inner strip must
        # reserve that old approach distance before its scan-start event.
        low = ctx.zones["alert"]["offset_m"] + 35.
        high = ctx.zones["warning"]["offset_m"] - 35.
        if high <= low:
            return None, "annulus_too_narrow"
        extent = base["radius_m"] if base["type"] == "Circle" else float(np.linalg.norm(np.asarray(base["vertices_m"]) - center, axis=1).max())
        bound = extent + high
        span = math.radians(span_deg)
        direction = np.array([math.cos(angle), math.sin(angle)])
        axis = np.array([-direction[1], direction[0]])
        sector = {"type": "ContourAnnularSector", "base_geometry": deepcopy(base), "center_m": center.tolist(),
                  "inner_offset_m": low, "outer_offset_m": high, "start_angle_rad": angle - span / 2,
                  "angle_span_rad": span, "bounding_radius_m": bound}
        area = sector_area(sector)
        if area_m2 is not None:
            if area < area_m2:
                return None, 'sampled_sector_area_does_not_fit_original_band'
            lower, upper = low, high
            for _ in range(32):
                middle = (lower+upper)/2
                sector['outer_offset_m'] = middle
                if sector_area(sector) < area_m2:
                    lower = middle
                else:
                    upper = middle
            sector['outer_offset_m'] = upper
            sector['bounding_radius_m'] = extent+upper
            area = sector_area(sector)
        if not 200000 <= area <= 600000:
            return None, "sector_area"
        fine = sector_area(sector, 32)
        if abs(fine - area) > .1 or not 200000 <= fine <= 600000:
            return None, "sector_quadrature"
        if not sector_clear(ctx.scene, sector, ctx.group["target_id"], 35.):
            return None, "sector_clearance"
        footprint = .5 * ctx.altitude
        spacing = 2 * footprint * (1-getattr(ctx,'strip_overlap_fraction',.2))
        x0, x1 = lateral_bounds(sector, axis)
        count = math.ceil((x1 - x0) / spacing)
        if count < len(ctx.group["members"]):
            return None, "insufficient_strips"
        xs = (x0 + x1) / 2 + (np.arange(count) - (count - 1) / 2) * spacing
        lanes = []
        for x in xs:
            origin = center + x * axis
            intervals = geometry_facts(sector, origin, line_direction=direction)["line_intervals_m"]
            segments = [[origin + (lo + 5.) * direction, origin + (hi - 5.) * direction]
                        for lo, hi in intervals if hi - lo >= 11.]
            if not segments:
                return None, "empty_strip"
            lanes.append(segments)
        lengths = [sum(float(np.linalg.norm(b - a)) for a, b in segments) for segments in lanes]
        partitions = balanced_partitions(lengths, len(ctx.group["members"]))
        allocation = []
        cursor = 0
        for side, stock in enumerate(ctx.split):
            inward, _ = start_line(ctx.scene, np.mean([ctx.starts[a] for a in stock], axis=0))
            first_normal = np.array([-inward[1], inward[0]])
            members = sorted(stock, key=lambda a: (float(ctx.starts[a] @ first_normal), a))
            chunks = partitions[cursor:cursor + len(stock)]
            # Preserve left-to-right lane order as the corridor turns. The two
            # scan entry directions have opposite left normals.
            if side == 0:
                chunks = list(reversed(chunks))
            allocation.extend(zip(members, chunks))
            cursor += len(stock)
        ordered = [a for a, _ in allocation]
        side_by_id = {a: side for side, members in enumerate(ctx.split) for a in members}
        scans, refs, gates = {}, {}, {}
        for a, indices in allocation:
            left = x0 if indices[0] == 0 else (xs[indices[0] - 1] + xs[indices[0]]) / 2
            right = x1 if indices[-1] == count - 1 else (xs[indices[-1]] + xs[indices[-1] + 1]) / 2
            strip = {**sector, "lateral_axis": axis.tolist(), "lateral_interval_m": [float(left), float(right)]}
            scan = []
            for j, index in enumerate(indices):
                inward = (j + side_by_id[a]) % 2 == 0
                segments = list(reversed(lanes[index])) if inward else lanes[index]
                for segment in segments:
                    scan.extend(list(reversed(segment)) if inward else segment)
            velocity = (scan[1] - scan[0]) / np.linalg.norm(scan[1] - scan[0])
            gate = scan[0]
            scans[a] = scan
            gates[a] = gate
            refs[a] = {"scan_geometry": strip, "scan_lane_endpoints_m": [p.tolist() for p in scan],
                       "scan_axis_enu": velocity.tolist(), "scan_strip_count": len(indices),
                       "scan_leg_count": len(scan) // 2, "assigned_scan_length_m": sum(lengths[i] for i in indices),
                       "retreat_required": True, "retreat_warning_clearance_m": ctx.retreat_warning_minimum_m}
        ingress, reason = warning_ingress(ctx, angle if ingress_angle is None else ingress_angle)
        if reason:
            return None, reason
        approaches = {}
        for agent in ordered:
            points = list(ingress['routes'][agent])
            branch = deploy_inside_warning(ctx, points[-1], gates[agent])
            if branch is None:
                return None, 'inside_warning_scan_deployment_unavailable'
            points.extend(branch[1:])
            approaches[agent] = points
            refs[agent]['formation_lane'] = ingress['references'][agent]

        routes, headings, total, retreats = {}, {}, 0., []
        for a in ordered:
            scan = scans[a]
            theta = math.atan2(*(scan[-1] - center)[::-1])
            retreat = None
            for shift in [0., *[sign * step * .05 for step in range(1, 7) for sign in (1, -1)]]:
                point = find_clear_retreat(ctx.scene, theta + shift, center, bound + 35., ctx.planner(),
                                           warning_clearance_m=ctx.retreat_warning_minimum_m)
                if point is not None and all(np.linalg.norm(point - prior) >= 35. for prior in retreats):
                    retreat = point
                    break
            if retreat is None:
                return None, "all_facility_retreat_unavailable"
            try:
                work = joined_path(ctx.planner(), [*scan, retreat])
                points = clean_route([p.tolist() for p in approaches[a]] + work, ctx.planner())
            except ValueError:
                return None, "full_route_invalid"
            points = np.asarray(points)
            if not ctx.route_valid(points):
                return None, "route_clearance"
            distance = planned_core_distance(points, refs[a]["scan_geometry"])
            warning_distance = planned_core_distance(points, ctx.zones['warning']['geometry'])
            heading = heading_before_distance(points, warning_distance)
            if distance is None or heading is None:
                return None, "missing_planned_core"
            headings[a] = heading
            total += distance
            refs[a].update(points_enu_m=[[*p, ctx.altitude] for p in points.tolist()],
                           endpoint_enu_m=[*retreat.tolist(), ctx.altitude], planned_core_distance_m=distance)
            routes[a] = refs[a]["points_enu_m"]
            retreats.append(retreat)
        values = list(headings.values())
        spread = max(min(abs(a - b), 360 - abs(a - b)) for a in values for b in values)
        if ctx.multi and spread < 90.:
            return None, "planned_approach_heading"
        survey = {"geometry": sector, "area_m2": fine, "angle_span_deg": span_deg,
                  "area_quadrature_error_m2": abs(area - fine), "bounds_m": [*(center - bound).tolist(), *(center + bound).tolist()],
                  "model": "ideal_isotropic_horizontal_disk", "footprint_radius_m": footprint, "footprint_height_factor": .5,
                  "strip_spacing_m": spacing, "strip_overlap_factor": .8, "strip_count": count,
                  "grid_spacing_m": min(footprint / 2, math.sqrt(fine) / 50), "required_group_coverage": .9,
                  "effective_speed_min_m_s": .5, "lane_endpoint_radius_m": 5., "planning_margin_m": 35.,
                  "strip_allocation": "minimum maximum contiguous sum of actual strip lengths",
                  "assumptions": "Geometric coverage proxy; no camera, detection or recognition simulation"}
        if hasattr(ctx,'strip_overlap_fraction'):
            survey['strip_overlap_factor']=1-ctx.strip_overlap_fraction
            survey['strip_overlap_fraction']=ctx.strip_overlap_fraction
        return {"routes": routes, "length": total, "template": {"role": "reconnaissance", "execution_method": "area_search",
                "planning_version": "v07_s2x_area_search_v1", "survey": survey, "references": refs,
                "retreat_warning_minimum_m": ctx.retreat_warning_minimum_m,
                "formation": {'blocks': ingress['blocks']},
                "planned_approach_headings_deg": headings, "planned_approach_span_deg": spread,
                "work_area_bearing_deg": math.degrees(angle) % 360}}, None
