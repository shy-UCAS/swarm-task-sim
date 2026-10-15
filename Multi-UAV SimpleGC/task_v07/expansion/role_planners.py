"""Scripted role waypoint arrangements for the S2 expansion (abstract geometry only).

Every planner returns per-agent ENU waypoints (RouteBundle) plus a private check
template for the label criteria. Routes are shortest exact visibility paths
around abstract constraints; nothing is optimized against any defence and no
task effect is evaluated. Speed and altitude are copied from the family.
"""
from copy import deepcopy
import math
import random

import numpy as np

from scene_v07.geometry import center_of
from task_v07.geometry import geometry_facts, offset_geometry
from task_v07.planning import build_skeleton, clean_route, role_planner, angular_span
from task_v07.visibility import ExactVisibilityPlanner
from .contracts import RouteBundle
from .geometry_checks import check_retreat_point, check_polyline
from .formation_corridors import offset_polyline, start_line, shared_reference_corridor

PLANNING_MARGIN_M = 35.0          # 30 m obstacle clearance + 5 m M3 tracking allowance
RETREAT_WARNING_CLEARANCE_M = 210.0  # >=200 m requirement plus 10 m planning margin
TRANSIT_VERSION = "v07_s2x_transit_v2"
ENTRY_AZIMUTH_DEFINITION = ("azimuth of each member's first entry into the work area, measured "
                            "from the work-area centre; multi-direction requires span >= 90 deg")


class PlanningInfeasible(ValueError):
    """Skeleton-level rejection; category is geometry_infeasible or kinematic_infeasible."""

    def __init__(self, category, detail):
        super().__init__(f"{category}: {detail}")
        self.category = category
        self.detail = detail


def zones_of(scene, facility_id):
    facility = next(e for e in scene["entities"] if e["id"] == facility_id)
    zones = {e["layer"]: e for e in scene["entities"] if e.get("facility_id") == facility_id}
    return facility, zones


def blocked_planner(scene, zone_ids, margin=PLANNING_MARGIN_M):
    """Exact visibility planner treating the listed zone entities as obstacles."""
    copy = deepcopy(scene)
    for entity in copy["entities"]:
        if entity["id"] in zone_ids:
            entity["type"] = "hard_constraint_obstacle"
    return ExactVisibilityPlanner(copy, margin)


def azimuth_deg(offset):
    return math.degrees(math.atan2(offset[1], offset[0])) % 360


def azimuth_difference_deg(a, b):
    return abs((b - a + 180) % 360 - 180)


def ray_point_at_clearance(geometry, origin, direction, clearance):
    """First point on the ray with exact signed distance >= clearance (convex region)."""
    def slack(s):
        return float(geometry_facts(geometry, origin + s * direction)["signed_distance_m"]) - clearance
    lo, hi = 0.0, clearance + 1.0
    if slack(lo) >= 0:
        return np.array(origin, float)
    while slack(hi) < 0:
        hi *= 2
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if slack(mid) < 0 else (lo, mid)
    return origin + hi * direction




class VerticalSliceAdapter:
    """Wraps the unchanged vertical-slice build_skeleton (four-agent penetration/area search).

    The template is the full vertical-slice skeleton; the pipeline only re-inserts
    the returned waypoints, so evidence semantics are exactly those of the slice.
    """
    legacy_vertical_slice = True

    def __init__(self, intent, index, *, recorded_template=None):
        self.intent, self.index = intent, index
        self.recorded_template = deepcopy(recorded_template)
        self.legacy_vertical_slice = recorded_template is None

    def plan_with_template(self, scene, task_group, role_parameters):
        family = role_parameters["family"]
        skeleton = (deepcopy(self.recorded_template) if self.recorded_template is not None else
                    build_skeleton(scene, family, self.intent, self.index, task_group["target_id"]))
        if sorted(skeleton["members"]) != sorted(task_group["members"]):
            raise ValueError("Vertical-slice skeleton members differ from the task group")
        bundle = RouteBundle({a: deepcopy(skeleton["references"][a]["points_enu_m"]) for a in task_group["members"]},
                             {a: 0.0 for a in task_group["members"]})
        # Keep points_enu_m in place (key order => byte-identical task.json); the
        # pipeline overwrites its value with the returned bundle waypoints.
        return bundle, deepcopy(skeleton)

    def plan(self, scene, task_group, role_parameters):
        return self.plan_with_template(scene, task_group, role_parameters)[0]


class _Context:
    """Per-group exact geometry and lazily built planners (cached by margin)."""

    def __init__(self, scene, target, retreat_warning_minimum_m=200.):
        self.scene = scene
        self.retreat_warning_minimum_m = float(retreat_warning_minimum_m)
        self.facility, self.zones = zones_of(scene, target)
        self.center = np.array(center_of(self.facility["geometry"]))
        self.warning = self.zones["warning"]["geometry"]
        self.alert_keep = offset_geometry(self.facility["geometry"], self.zones["alert"]["offset_m"] + PLANNING_MARGIN_M)
        self.blocked = [e["id"] for e in scene["entities"] if e.get("layer") == "alert"] + [self.zones["warning"]["id"]]
        self.chord_planner = role_planner(scene, survey=True)   # obstacles + every alert zone, 35 m
        self._planners = {}

    def approach_planner(self, margin):
        key = math.ceil(margin)
        if key not in self._planners:
            self._planners[key] = blocked_planner(self.scene, self.blocked, float(key))
        return self._planners[key]


class TransitPlanner:
    """Straight warning-zone chords flown as laterally offset lanes of shared routes.

    Same direction: one side, all members on parallel chords spaced by the
    family lateral spacing. Multi direction: two antiparallel sides on opposite
    sides of the facility (entry azimuths ~180 deg apart); chords never cross.
    Members of one side from one entry zone share a route planned with margin
    35 m + 1.5 x the block half-width + 2 m after a forced form-up leg
    perpendicular to the start line, and each flies its offset lane, so
    lanes do not converge on the same obstacle corner. Approach legs avoid the
    target warning zone, so the single observed warning visit is the chord.
    """
    legacy_vertical_slice = False
    criteria = {"minimum_chord_m": 400.0, "minimum_azimuth_difference_deg": 90.0,
                "maximum_low_speed_s": 2.0, "low_speed_threshold_m_s": 0.5,
                "maximum_cumulative_turn_deg": 180.0}
    planned = {"minimum_chord_m": 430.0, "minimum_azimuth_difference_deg": 95.0,
               "run_out_clearance_m": PLANNING_MARGIN_M + 5.0, "offset_scan_step_m": 1.0,
               "direction_candidates": 36, "shared_route_margin": "35 m + 1.5 x half-width + 2 m", "form_up_depths_m": [100.0, 60.0, 150.0, 200.0],
               "lead_in_clearance": "shared margin + 4 x half-width + 20 m"}

    def plan(self, scene, task_group, role_parameters):
        return self.plan_with_template(scene, task_group, role_parameters)[0]

    def plan_with_template(self, scene, task_group, role_parameters):
        family = role_parameters["family"]
        members = sorted(task_group["members"])
        if 'candidate_budget' in role_parameters:
            from .candidate_search import plan_continuous_group
            return plan_continuous_group(scene,task_group,role_parameters)
        from .candidate_constraints import bearing_allowed
        from .area_search import planned_core_distance
        multi = role_parameters["approach_mode"] == "multi_direction"
        spacing = float(family["lateral_spacing_m"])
        altitude = family["task_altitude_m"]
        states = {s["agent_id"]: s for s in family["initial_states"]}
        start = {a: np.array(states[a]["position_enu_m"][:2], float) for a in members}
        ctx = _Context(scene, task_group["target_id"], role_parameters.get("retreat_warning_minimum_m",200.))
        geometry = ctx.facility["geometry"]
        extent = (geometry["radius_m"] if geometry["type"] == "Circle" else
                  float(np.linalg.norm(np.array(geometry["vertices_m"]) - ctx.center, axis=1).max()))
        bound = extent + ctx.zones["warning"]["offset_m"]
        rng = random.Random(role_parameters["planning_seed"])
        base = rng.uniform(0, 2 * math.pi)
        thetas = [base + k * 2 * math.pi / self.planned["direction_candidates"]
                  for k in range(self.planned["direction_candidates"])]
        rng.shuffle(thetas)
        reasons, candidates = {}, []
        for theta in thetas:
            for sigma in rng.sample([1.0, -1.0], 2):
                result, failure = self._attempt(ctx, members, start, states, theta, sigma, multi, spacing, bound)
                if failure is None:
                    first_side = [r["chord"] for r in result["routes"].values() if r["side"] == 0]
                    midpoint = np.mean([(c["entry"] + c["exit"]) / 2 for c in first_side], axis=0)
                    bearing = math.atan2(*(midpoint - ctx.center)[::-1])
                    if not bearing_allowed(bearing, role_parameters):
                        reasons['same_target_work_area_bearing'] = reasons.get('same_target_work_area_bearing', 0) + 1
                        continue
                    bundle, template = self._package(ctx, members, result, altitude, spacing, multi, task_group["target_id"])
                    template['work_area_bearing_deg'] = math.degrees(bearing) % 360
                    score = sum(planned_core_distance(np.asarray(r['points']), ctx.warning) for r in result['routes'].values())
                    candidates.append((score, bundle, template))
                    if multi:
                        return bundle, template
                    continue
                reasons[failure] = reasons.get(failure, 0) + 1
        if candidates:
            minimum = min(c[0] for c in candidates)
            pool = [c for c in candidates if c[0] <= 1.15 * minimum]
            score, bundle, template = rng.choice(pool)
            template['direction_selection'] = {'minimum_approach_length_m': minimum,
                'selected_approach_length_m': score, 'maximum_ratio': 1.15,
                'feasible_candidates': len(candidates), 'eligible_candidates': len(pool),
                'selection_order': 'role constraints -> 115% route-length filter -> private random direction'}
            return bundle, template
        raise PlanningInfeasible("geometry_infeasible", f"transit chords/lanes: {dict(sorted(reasons.items()))}")

    def _chord(self, ctx, direction, normal, h):
        origin = ctx.center + h * normal
        if geometry_facts(ctx.alert_keep, origin, line_direction=direction)["line_intervals_m"]:
            return None
        intervals = geometry_facts(ctx.warning, origin, line_direction=direction)["line_intervals_m"]
        if not intervals:
            return None
        lo, hi = intervals[0]
        entry, exit_ = origin + lo * direction, origin + hi * direction
        a_in, a_out = azimuth_deg(entry - ctx.center), azimuth_deg(exit_ - ctx.center)
        difference = azimuth_difference_deg(a_in, a_out)
        if hi - lo < self.planned["minimum_chord_m"] or difference < self.planned["minimum_azimuth_difference_deg"]:
            return None
        return {"origin": origin, "entry": entry, "exit": exit_, "length": hi - lo, "entry_az": a_in,
                "exit_az": a_out, "difference": difference, "offset": h}

    def _offsets(self, ctx, direction, normal, sigma, count, spacing, bound):
        steps = np.arange(0.0, bound + 1.0, self.planned["offset_scan_step_m"])
        good = [h for h in steps if self._chord(ctx, direction, normal, sigma * h) is not None]
        if not good or (count - 1) * spacing > max(good) - min(good):
            return None
        first = (min(good) + max(good)) / 2 - (count - 1) * spacing / 2
        chords = [self._chord(ctx, direction, normal, sigma * (first + j * spacing)) for j in range(count)]
        return None if any(c is None for c in chords) else sorted(chords, key=lambda c: c["offset"])

    def _point_on_line(self, ctx, origin, direction, clearance, sign, planner):
        """Point on the chord line outside the warning zone with the requested clearance."""
        for distance in np.arange(20.0, 4000.0, 20.0):
            candidate = origin + sign * distance * direction
            if (float(geometry_facts(ctx.warning, candidate)["signed_distance_m"]) >= clearance
                    and (planner is None or planner.free(candidate.tolist()))):
                return candidate
        return None

    def _attempt(self, ctx, members, start, states, theta, sigma, multi, spacing, bound):
        d = np.array([math.cos(theta), math.sin(theta)])
        n = np.array([-d[1], d[0]])
        sides = [(d, n)] if not multi else [(d, n), (-d, -n)]
        # Members ordered by entry zone (nearest the -d end first), then along their start line,
        # so every side/entry-zone block is contiguous on the start line.
        zones = {}
        for a in members:
            zones.setdefault(states[a].get("entry_id", "none"), []).append(a)
        sequence = []
        for entry_id, agents in sorted(zones.items(), key=lambda item: (float(np.mean([start[a] for a in item[1]], axis=0) @ d), item[0])):
            tangent = self._start_line(ctx, np.mean([start[a] for a in agents], axis=0))[1]
            sequence += sorted(agents, key=lambda a: (float(start[a] @ tangent), a))
        counts = [len(members)] if not multi else [math.ceil(len(members) / 2), len(members) // 2]
        side_members = [sequence] if not multi else [sequence[:counts[0]], sequence[counts[0]:]]
        routes, blocks = {}, []
        for side, ((direction, normal), agents) in enumerate(zip(sides, side_members)):
            chords = self._offsets(ctx, direction, normal, sigma, len(agents), spacing, bound)
            if chords is None:
                return None, "no_valid_parallel_chord_block"
            # Entry-zone sub-blocks take contiguous lanes, ordered across the side normal.
            sub = {}
            for a in agents:
                sub.setdefault(states[a].get("entry_id", "none"), []).append(a)
            ordered = sorted(sub.items(), key=lambda item: (float(np.mean([start[a] for a in item[1]], axis=0) @ normal), item[0]))
            cursor = 0
            for entry_id, block_agents in ordered:
                lane_chords = chords[cursor:cursor + len(block_agents)]
                cursor += len(block_agents)
                block, failure = self._block(ctx, block_agents, lane_chords, start, direction, normal, side, entry_id)
                if failure is not None:
                    return None, failure
                routes.update(block.pop("routes"))
                blocks.append(block)
        return {"routes": routes, "blocks": blocks}, None

    @staticmethod
    def _start_line(ctx, point):
        """Inward normal and tangent of the world edge nearest to a start position."""
        vertices = np.asarray(ctx.scene["world"]["geometry"]["vertices_m"], float)
        if np.array_equal(vertices[0], vertices[-1]):
            vertices = vertices[:-1]
        best = None
        for a, b in zip(vertices, np.roll(vertices, -1, axis=0)):
            edge = b - a
            s = np.clip((point - a) @ edge / (edge @ edge), 0, 1)
            distance = float(np.linalg.norm(point - (a + s * edge)))
            if best is None or distance < best[0]:
                best = (distance, edge / np.linalg.norm(edge), a)
        _, tangent, a = best
        inward = np.array([-tangent[1], tangent[0]])
        if (vertices.mean(axis=0) - a) @ inward < 0:
            inward = -inward
        return inward, tangent

    def _block(self, ctx, agents, chords, start, direction, normal, side, entry_id):
        h_center = float(np.mean([c["offset"] for c in chords]))
        half = max(abs(c["offset"] - h_center) for c in chords)
        margin = getattr(ctx,'approach_clearance_m',PLANNING_MARGIN_M) + 1.5 * half + 2.0
        planner = ctx.approach_planner(margin)
        origin = ctx.center + h_center * normal
        lead = self._point_on_line(ctx, origin, direction, math.ceil(margin) + 4 * half + 20.0, -1, planner)
        run_out = self._point_on_line(ctx, origin, direction, self.planned["run_out_clearance_m"], 1, None)
        if lead is None or run_out is None:
            return None, "lead_in_or_run_out_unavailable"
        corridor, failure = shared_reference_corridor(ctx.scene, agents, start, lead, run_out,
                                                      planner, ctx.chord_planner)
        if failure is not None:
            return None, failure
        centre = corridor["reference"]
        approach = corridor["approach"]
        first_normal = corridor["first_normal"]
        # Lane offsets are applied along the first leg's left normal, so lanes in
        # ascending offset take members in ascending start position across it.
        lanes = sorted(chords, key=lambda c: c["offset"])
        joiners = sorted(agents, key=lambda a: (float(start[a] @ first_normal), a))
        routes = {}
        for a, c in zip(joiners, lanes):
            lane = offset_polyline(centre, c["offset"] - h_center)
            if lane is None:
                return None, "lane_offset_swallowtail"
            # Each lane leaves the zone on its own chord line (inner lanes exit later).
            lane[-1] = self._point_on_line(ctx, ctx.center + c["offset"] * normal, direction,
                                           self.planned["run_out_clearance_m"], 1, None)
            if lane[-1] is None or float((lane[-1] - lane[-2]) @ direction) < c["length"]:
                return None, "lane_run_out_unavailable"
            exit_point = lane[-1]
            retreat = ray_point_at_clearance(ctx.warning, exit_point, direction, ctx.retreat_warning_minimum_m+10.)
            if not (check_retreat_point(ctx.scene, retreat,warning_clearance_m=ctx.retreat_warning_minimum_m)["valid"] and ctx.chord_planner.free(retreat.tolist())):
                return None, "retreat_point_invalid"
            raw = [start[a], *lane, retreat]
            chord_leg = len(raw) - 3            # segment lane[-2] -> lane[-1]
            for k in range(len(raw) - 1):
                if k == chord_leg or np.linalg.norm(raw[k + 1] - raw[k]) < 1e-9:
                    continue   # chord leg enters by design; zero legs are dropped by clean_route
                clearance = geometry_facts(ctx.warning, np.array([raw[k], raw[k + 1]]), footprint=True)["clearance_m"]
                if clearance < PLANNING_MARGIN_M - 1e-6:
                    return None, "lane_enters_warning_outside_chord"
            try:
                points = clean_route([p.tolist() for p in raw], ctx.chord_planner)
            except ValueError:
                return None, "lane_route_check"
            routes[a] = {"points": points, "retreat": retreat, "chord": c, "side": side,
                         "direction": direction, "entry_id": entry_id, "lane_offset_m": c["offset"] - h_center}
        return {"routes": routes, "side": side, "entry_id": entry_id, "members": sorted(agents),
                "center_offset_m": h_center, "half_width_m": half, "shared_route_margin_m": float(math.ceil(margin)),
                "shared_route_waypoints": len(approach), "travel_direction_deg": azimuth_deg(direction)}, None

    def _package(self, ctx, members, result, altitude, spacing, multi, target):
        routes = result["routes"]
        references, entries = {}, {}
        for a in members:
            r = routes[a]; c = r["chord"]
            entries[a] = c["entry_az"]
            references[a] = {
                "endpoint_enu_m": [*np.asarray(r["retreat"]).tolist(), altitude],
                "retreat_required": True, "retreat_warning_clearance_m": ctx.retreat_warning_minimum_m+10.,
                "planned_entry_azimuth_deg": c["entry_az"],
                "planned_chord": {"entry_m": c["entry"].tolist(), "exit_m": c["exit"].tolist(),
                                  "chord_length_m": c["length"], "entry_azimuth_deg": c["entry_az"],
                                  "exit_azimuth_deg": c["exit_az"], "entry_exit_azimuth_difference_deg": c["difference"],
                                  "lateral_offset_m": c["offset"], "side": r["side"],
                                  "travel_direction_deg": azimuth_deg(r["direction"])},
                "formation_lane": {"entry_id": r["entry_id"], "lane_offset_m": r["lane_offset_m"]}}
        bundle = RouteBundle({a: [[*p, altitude] for p in routes[a]["points"]] for a in members}, {a: 0.0 for a in members})
        template = {"role": "transit", "execution_method": "transit", "target_id": target,
                    "planning_version": TRANSIT_VERSION, "retreat_warning_minimum_m": ctx.retreat_warning_minimum_m,
                    "transit": {**self.criteria, "planning": dict(self.planned), "lateral_spacing_m": spacing,
                                "side_count": 2 if multi else 1},
                    "approach_geometry": {"work_area": "target_warning_zone",
                                          "work_area_center_m": ctx.center.tolist(),
                                          "entry_azimuth_definition": ENTRY_AZIMUTH_DEFINITION,
                                          "planned_entry_azimuth_deg": entries,
                                          "planned_entry_span_deg": angular_span(list(entries.values())),
                                          "required_entry_span_deg": 90.0 if multi else None},
                    "formation": {"lateral_spacing_m": spacing, "blocks": result["blocks"]},
                    "references": references}
        return bundle, template



PLANNERS = {
    ("transit", "transit"): TransitPlanner,
    ("intrusion", "polygon_visit"): None,  # filled below
    ("reconnaissance", "close_observation"): None,
    ("monitoring", "monitoring"): None,
    ("feint", "feint"): None,
    ("reconnaissance", "area_search"): None,
}


# ---------------------------------------------------------------------------
# Shared helpers for candidate-based planners with 115% approach selection
# ---------------------------------------------------------------------------

def approach_route_length(waypoints, core_waypoint_index):
    """Sum of segment lengths from start up to and including core_waypoint_index."""
    pts = np.asarray(waypoints, float)
    if core_waypoint_index <= 0 or len(pts) < 2:
        return 0.0
    end = min(core_waypoint_index, len(pts) - 1)
    return float(np.sum(np.linalg.norm(np.diff(pts[:end + 1], axis=0), axis=1)))


def select_candidate(candidates, rng, *, key_fn):
    """From a list of scored candidates, keep those within 115% of the minimum
    key_fn value, then pick uniformly using rng.  Returns None if empty."""
    if not candidates:
        return None
    scores = [key_fn(c) for c in candidates]
    threshold = min(scores) * 1.15
    pool = [c for c, s in zip(candidates, scores) if s <= threshold]
    return rng.choice(pool)


def find_clear_retreat(scene, from_angle, center, warn_r, approach_pl, *, warning_clearance_m=200.):
    """Return a retreat point near from_angle that clears ALL facility warning zones.

    Scans 36 directions centred on from_angle (interleaved ±step increments) and four
    candidate distances; calls check_retreat_point, which enforces >=200 m clearance
    from every facility warning zone, not just the target facility.  Returns None only
    when no candidate passes.
    """
    n = 36
    step = 2 * math.pi / n
    offsets = [0] + [v for k in range(1, n // 2 + 1) for v in (k * step, -k * step)]
    distances = [warn_r + warning_clearance_m + d for d in (20, 100, 200, 300)]
    for off in offsets:
        direction = np.array([math.cos(from_angle + off), math.sin(from_angle + off)])
        for dist in distances:
            candidate = center + dist * direction
            if (float(geometry_facts(scene["world"]["geometry"], candidate)["signed_distance_m"])
                    <= -PLANNING_MARGIN_M
                    and check_retreat_point(scene, candidate.tolist(),warning_clearance_m=warning_clearance_m)["valid"]):
                return candidate
    return None


# ---------------------------------------------------------------------------
# Close-observation planner
# ---------------------------------------------------------------------------

# Fill the PLANNERS registry
# ---------------------------------------------------------------------------

from .formation_role_planners import (CloseObservationPlanner, MonitoringPlanner, FeintPlanner, IntrusionPlanner)
from .area_search import AreaSearchPlanner

PLANNERS = {
    ("transit", "transit"): TransitPlanner,
    ("intrusion", "polygon_visit"): IntrusionPlanner,
    ("intrusion", "intrusion"): IntrusionPlanner,     # descriptor execution_method
    ("reconnaissance", "close_observation"): CloseObservationPlanner,
    ("reconnaissance", "area_search"): AreaSearchPlanner,
    ("monitoring", "monitoring"): MonitoringPlanner,
    ("feint", "feint"): FeintPlanner,
}


def planner_for(role, execution_method):
    try:
        return PLANNERS[(role, execution_method)]()
    except KeyError:
        raise PlanningInfeasible("planner_not_implemented", f"{role}/{execution_method}") from None

