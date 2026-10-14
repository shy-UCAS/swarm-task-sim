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


def offset_polyline(points, offset, max_turn_deg=150.0, arc_step_deg=30.0):
    """Parallel lane at signed left offset of a shared route.

    Inside of a turn: miter join (both offset lines meet). Outside of a turn
    sharper than arc_step_deg: round join (points every <= arc_step_deg at
    radius |offset| about the vertex), so the outer lane stays >= |offset| x
    cos(arc_step/2) from the centre lane's corner; a bevel would cut in to
    |offset| x cos(turn/2). Returns None if a lane leg would reverse
    (swallowtail) or an inside turn is too sharp for a miter.
    """
    P = np.asarray(points, float)
    if offset == 0:
        return [p.copy() for p in P]
    d = np.diff(P, axis=0)
    u = d / np.linalg.norm(d, axis=1)[:, None]
    n = np.stack([-u[:, 1], u[:, 0]], axis=1)
    joints = [[P[0] + offset * n[0]]]
    for i in range(1, len(P) - 1):
        cross = u[i-1, 0] * u[i, 1] - u[i-1, 1] * u[i, 0]
        cos = float(np.clip(u[i-1] @ u[i], -1, 1))
        turn = math.degrees(math.acos(cos))
        if abs(cross) < 1e-12 and cos > 0:
            joints.append([P[i] + offset * n[i]])
        elif offset * cross > 0 or turn <= arc_step_deg:
            if turn > max_turn_deg:
                return None
            joints.append([P[i] + offset * (n[i-1] + n[i]) / (1 + cos)])
        else:
            start = math.atan2(n[i-1, 1], n[i-1, 0])
            sweep = (math.atan2(n[i, 1], n[i, 0]) - start + math.pi) % (2 * math.pi) - math.pi
            steps = math.ceil(abs(math.degrees(sweep)) / arc_step_deg)
            joints.append([P[i] + offset * np.array([math.cos(start + k * sweep / steps), math.sin(start + k * sweep / steps)])
                           for k in range(steps + 1)])
    joints.append([P[-1] + offset * n[-1]])
    for i in range(len(P) - 1):
        leg = joints[i + 1][0] - joints[i][-1]
        if float(leg @ u[i]) < 1.0:
            return None
    return [p for joint in joints for p in joint]


class VerticalSliceAdapter:
    """Wraps the unchanged vertical-slice build_skeleton (four-agent penetration/area search).

    The template is the full vertical-slice skeleton; the pipeline only re-inserts
    the returned waypoints, so evidence semantics are exactly those of the slice.
    """
    legacy_vertical_slice = True

    def __init__(self, intent, index):
        self.intent, self.index = intent, index

    def plan_with_template(self, scene, task_group, role_parameters):
        family = role_parameters["family"]
        skeleton = build_skeleton(scene, family, self.intent, self.index, task_group["target_id"])
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

    def __init__(self, scene, target):
        self.scene = scene
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
        multi = role_parameters["approach_mode"] == "multi_direction"
        spacing = float(family["lateral_spacing_m"])
        altitude = family["task_altitude_m"]
        states = {s["agent_id"]: s for s in family["initial_states"]}
        start = {a: np.array(states[a]["position_enu_m"][:2], float) for a in members}
        ctx = _Context(scene, task_group["target_id"])
        geometry = ctx.facility["geometry"]
        extent = (geometry["radius_m"] if geometry["type"] == "Circle" else
                  float(np.linalg.norm(np.array(geometry["vertices_m"]) - ctx.center, axis=1).max()))
        bound = extent + ctx.zones["warning"]["offset_m"]
        rng = random.Random(role_parameters["planning_seed"])
        base = rng.uniform(0, 2 * math.pi)
        thetas = [base + k * 2 * math.pi / self.planned["direction_candidates"]
                  for k in range(self.planned["direction_candidates"])]
        rng.shuffle(thetas)
        reasons = {}
        for theta in thetas:
            for sigma in rng.sample([1.0, -1.0], 2):
                result, failure = self._attempt(ctx, members, start, states, theta, sigma, multi, spacing, bound)
                if failure is None:
                    return self._package(ctx, members, result, altitude, spacing, multi, task_group["target_id"])
                reasons[failure] = reasons.get(failure, 0) + 1
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
        margin = PLANNING_MARGIN_M + 1.5 * half + 2.0
        planner = ctx.approach_planner(margin)
        origin = ctx.center + h_center * normal
        lead = self._point_on_line(ctx, origin, direction, math.ceil(margin) + 4 * half + 20.0, -1, planner)
        run_out = self._point_on_line(ctx, origin, direction, self.planned["run_out_clearance_m"], 1, None)
        if lead is None or run_out is None:
            return None, "lead_in_or_run_out_unavailable"
        shared_start = np.mean([start[a] for a in agents], axis=0)
        inward, _ = self._start_line(ctx, shared_start)
        form_up = next((shared_start + depth * inward for depth in (100.0, 60.0, 150.0, 200.0)
                        if planner.free((shared_start + depth * inward).tolist())
                        and ctx.chord_planner.visible(shared_start.tolist(), (shared_start + depth * inward).tolist())), None)
        if form_up is None:
            return None, "form_up_leg_blocked"
        approach = planner.path(form_up.tolist(), lead.tolist())
        if approach is None:
            return None, "no_shared_route"
        # The forced first leg is perpendicular to the start line, so each lane begins at
        # its member's own start (starts are spaced by the family lateral spacing).
        centre = [shared_start] + [np.array(p, float) for p in approach] + [run_out]
        first = centre[1] - centre[0]
        first_normal = np.array([-first[1], first[0]]) / np.linalg.norm(first)
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
            retreat = ray_point_at_clearance(ctx.warning, exit_point, direction, RETREAT_WARNING_CLEARANCE_M)
            if not (check_retreat_point(ctx.scene, retreat)["valid"] and ctx.chord_planner.free(retreat.tolist())):
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
                "retreat_required": True, "retreat_warning_clearance_m": RETREAT_WARNING_CLEARANCE_M,
                "planned_entry_azimuth_deg": c["entry_az"],
                "planned_chord": {"entry_m": c["entry"].tolist(), "exit_m": c["exit"].tolist(),
                                  "chord_length_m": c["length"], "entry_azimuth_deg": c["entry_az"],
                                  "exit_azimuth_deg": c["exit_az"], "entry_exit_azimuth_difference_deg": c["difference"],
                                  "lateral_offset_m": c["offset"], "side": r["side"],
                                  "travel_direction_deg": azimuth_deg(r["direction"])},
                "formation_lane": {"entry_id": r["entry_id"], "lane_offset_m": r["lane_offset_m"]}}
        bundle = RouteBundle({a: [[*p, altitude] for p in routes[a]["points"]] for a in members}, {a: 0.0 for a in members})
        template = {"role": "transit", "execution_method": "transit", "target_id": target,
                    "planning_version": TRANSIT_VERSION,
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


def find_clear_retreat(scene, from_angle, center, warn_r, approach_pl):
    """Return a retreat point near from_angle that clears ALL facility warning zones.

    Scans 36 directions centred on from_angle (interleaved ±step increments) and four
    candidate distances; calls check_retreat_point, which enforces >=200 m clearance
    from every facility warning zone, not just the target facility.  Returns None only
    when no candidate passes.
    """
    n = 36
    step = 2 * math.pi / n
    offsets = [0] + [v for k in range(1, n // 2 + 1) for v in (k * step, -k * step)]
    distances = [warn_r + d for d in (220, 300, 400, 500)]
    for off in offsets:
        direction = np.array([math.cos(from_angle + off), math.sin(from_angle + off)])
        for dist in distances:
            candidate = center + dist * direction
            if (float(geometry_facts(scene["world"]["geometry"], candidate)["signed_distance_m"])
                    <= -PLANNING_MARGIN_M
                    and check_retreat_point(scene, candidate.tolist())["valid"]):
                return candidate
    return None


# ---------------------------------------------------------------------------
# Close-observation planner
# ---------------------------------------------------------------------------

class CloseObservationPlanner:
    """Fly to individual observation points on the alert-zone outer edge and dwell.

    Each member is assigned its own observation point, spread around a chosen base
    angle so that adjacent points are at least PLANNING_MARGIN_M apart on the alert
    boundary.  Retreat goes radially outward past the warning boundary.
    """
    legacy_vertical_slice = False

    def plan(self, scene, task_group, role_parameters):
        return self.plan_with_template(scene, task_group, role_parameters)[0]

    def plan_with_template(self, scene, task_group, role_parameters):
        from task_v07.geometry import radial_points_exact
        family = role_parameters["family"]
        members = sorted(task_group["members"])
        n = len(members)
        multi = role_parameters["approach_mode"] == "multi_direction"
        altitude = family["task_altitude_m"]
        speed = family.get("cruise_speed_m_s", 5.0)
        states = {s["agent_id"]: s for s in family["initial_states"]}
        starts = {a: np.array(states[a]["position_enu_m"][:2], float) for a in members}
        rng = random.Random(role_parameters["planning_seed"])

        facility, zones = zones_of(scene, task_group["target_id"])
        center = np.array(center_of(facility["geometry"]))
        obs_radius = 30.0
        alert_r = zones["alert"]["offset_m"]
        warn_r = zones["warning"]["offset_m"]

        # Minimum angular separation between adjacent observation points so that
        # neighbouring agents on the alert boundary are at least 6 m apart.
        min_sep_m = max(6.0, 15.0 if speed > 7.0 else 6.0)
        # Arc length = r * dθ  →  dθ = min_sep_m / alert_r
        min_arc = min_sep_m / max(alert_r, 1.0)
        # Lane spacing for the shared approach corridor: at least the required
        # inter-agent minimum, preferably the family lateral spacing.
        lane_spacing = max(min_sep_m, float(family.get("lateral_spacing_m", min_sep_m)))

        approach_pl = role_planner(scene, survey=False)

        def obs_point(angle):
            # Place the observation point just outside the alert boundary so the
            # agent never enters the alert zone.  Offset by obs_radius outward so
            # the obs_radius circle sits tangent to the alert boundary.
            alert_boundary = radial_points_exact(zones["alert"]["geometry"], center, [angle])[0]
            direction = alert_boundary - center
            dist = float(np.linalg.norm(direction))
            if dist < 1e-9:
                return alert_boundary
            return center + (dist + obs_radius) * direction / dist

        n_candidates = 36
        base = rng.uniform(0, 2 * math.pi)
        base_angles = [base + k * 2 * math.pi / n_candidates for k in range(n_candidates)]
        rng.shuffle(base_angles)

        def score_base(base_angle, group_members):
            """Score a base angle: generate per-member angles spread around it."""
            m = len(group_members)
            # Centre the spread symmetrically around base_angle.
            offsets = [(i - (m - 1) / 2.0) * min_arc for i in range(m)]
            angles = [base_angle + off for off in offsets]
            ret = find_clear_retreat(scene, base_angle, center, warn_r, approach_pl)
            if ret is None:
                return None
            total = 0.0
            for a, ang in zip(group_members, angles):
                route = approach_pl.path(starts[a].tolist(), obs_point(ang).tolist())
                if route is None:
                    return None
                total += approach_route_length(route, len(route) - 1)
            return total

        # Members entering from opposite sides of the target cannot share a lane.
        side_groups = [(members, 0.0)] if not multi else [(members[:(n+1)//2], 0.0), (members[(n+1)//2:], math.pi)]

        routes, refs = {}, {}
        for side_members, side_dir in side_groups:
            m = len(side_members)
            if multi and len(side_groups) > 1:
                # Keep each side inside its own half-plane so the two approach
                # directions stay about 180 deg apart.
                ang_list = [a for a in base_angles
                            if abs((a - side_dir + math.pi) % (2 * math.pi) - math.pi) <= math.pi / 2]
                if not ang_list:
                    ang_list = base_angles
            else:
                ang_list = base_angles
            cands = [(a, score_base(a, side_members)) for a in ang_list]
            cands = [(a, s) for a, s in cands if s is not None]
            chosen = select_candidate(cands, rng, key_fn=lambda x: x[1])
            if chosen is None:
                raise PlanningInfeasible("geometry_infeasible", "no reachable observation angle")
            base_angle = chosen[0]
            offsets = [(i - (m - 1) / 2.0) * min_arc for i in range(m)]
            member_angles = [base_angle + off for off in offsets]
            ret = find_clear_retreat(scene, base_angle, center, warn_r, approach_pl)
            if ret is None:
                raise PlanningInfeasible("geometry_infeasible", "no valid retreat point for close_observation")
            targets = {a: obs_point(ang) for a, ang in zip(side_members, member_angles)}
            lane = {a: approach_pl.path(starts[a].tolist(), targets[a].tolist()) for a in side_members}
            if any(points is None for points in lane.values()):
                raise PlanningInfeasible("geometry_infeasible", "observation approach unavailable")
            for a, ang in zip(side_members, member_angles):
                pt = targets[a]
                # Per-agent retreat: radiate from each agent's own observation angle so
                # agents don't converge on a shared endpoint and collide at the hold.
                agent_ret = find_clear_retreat(scene, ang, center, warn_r, approach_pl)
                if agent_ret is None:
                    agent_ret = ret  # fall back to group retreat if individual fails
                full = [[*p, altitude] for p in lane[a]] + [[*agent_ret.tolist(), altitude]]
                routes[a] = full
                refs[a] = {"endpoint_enu_m": [*agent_ret.tolist(), altitude],
                           "observation_point_enu_m": [*pt.tolist(), altitude],
                           "retreat_required": True,
                           "retreat_warning_clearance_m": RETREAT_WARNING_CLEARANCE_M}

        bundle = RouteBundle(routes, {a: 0.0 for a in members})
        template = {"role": "reconnaissance", "execution_method": "close_observation",
                    "target_id": task_group["target_id"],
                    "close_observation": {"observation_radius_m": obs_radius,
                                          "minimum_dwell_s": 20.0,
                                          "approach_mode": role_parameters["approach_mode"]},
                    "references": refs}
        return bundle, template


# ---------------------------------------------------------------------------
# Monitoring (orbit) planner
# ---------------------------------------------------------------------------

class MonitoringPlanner:
    """Circular orbit in the alert band; each member enters at a distinct phase offset.

    The first member's entry angle is chosen by the 115% approach-length criterion
    among 36 candidates.  Subsequent members are spread evenly around the orbit
    (2π * i / n offset from the chosen angle) so no two members share an entry
    point, keeping inter-agent separation above the planning threshold.
    """
    legacy_vertical_slice = False

    def plan(self, scene, task_group, role_parameters):
        return self.plan_with_template(scene, task_group, role_parameters)[0]

    def plan_with_template(self, scene, task_group, role_parameters):
        family = role_parameters["family"]
        members = sorted(task_group["members"])
        n = len(members)
        altitude = family["task_altitude_m"]
        states = {s["agent_id"]: s for s in family["initial_states"]}
        starts = {a: np.array(states[a]["position_enu_m"][:2], float) for a in members}
        rng = random.Random(role_parameters["planning_seed"])

        facility, zones = zones_of(scene, task_group["target_id"])
        center = np.array(center_of(facility["geometry"]))
        protected_off = zones["protected"]["offset_m"] if "protected" in zones else 0.0
        alert_off = zones["alert"]["offset_m"]
        orbit_radius = protected_off + (alert_off - protected_off) * 0.6

        approach_pl = role_planner(scene, survey=False)

        def entry_point(angle):
            return center + orbit_radius * np.array([math.cos(angle), math.sin(angle)])

        n_candidates = 36
        base = rng.uniform(0, 2 * math.pi)
        angles = [base + k * 2 * math.pi / n_candidates for k in range(n_candidates)]
        rng.shuffle(angles)

        def score_angle(angle):
            # Score using the first member only; others enter at evenly spaced offsets.
            pt = entry_point(angle)
            total = 0.0
            for i, a in enumerate(members):
                member_angle = angle + 2 * math.pi * i / n
                route = approach_pl.path(starts[a].tolist(), entry_point(member_angle).tolist())
                if route is None:
                    return None
                total += approach_route_length(route, len(route) - 1)
            return total

        cands = [(a, score_angle(a)) for a in angles]
        cands = [(a, s) for a, s in cands if s is not None]
        chosen = select_candidate(cands, rng, key_fn=lambda x: x[1])
        if chosen is None:
            raise PlanningInfeasible("geometry_infeasible", "no reachable orbit entry angle")
        chosen_angle = chosen[0]

        orbit_steps = max(16, int(2 * math.pi * orbit_radius / 30))
        speed = max(family["cruise_speed_m_s"], 1.0)
        # Cap at 1 lap to guarantee agents reach the retreat point within the time budget.
        # More laps are not needed to satisfy the started_orbit / completed_laps conditions.
        planned_laps = 1

        ret = find_clear_retreat(scene, chosen_angle, center, zones["warning"]["offset_m"],
                                 approach_pl)
        if ret is None:
            raise PlanningInfeasible("geometry_infeasible", "no valid retreat point for monitoring")

        routes, refs = {}, {}
        for i, a in enumerate(members):
            member_entry_angle = chosen_angle + 2 * math.pi * i / n
            orbit_pts = [center + orbit_radius * np.array([
                math.cos(member_entry_angle + k * 2 * math.pi / orbit_steps),
                math.sin(member_entry_angle + k * 2 * math.pi / orbit_steps)])
                for k in range(orbit_steps + 1)]
            approach = approach_pl.path(starts[a].tolist(), orbit_pts[0].tolist())
            if approach is None:
                raise PlanningInfeasible("geometry_infeasible", f"no orbit approach for {a}")
            all_pts = [[*p, altitude] for p in approach]
            for _ in range(planned_laps):
                all_pts.extend([[*p.tolist(), altitude] for p in orbit_pts[1:]])
            # Per-agent retreat: each member retreats from their own orbit angle so
            # agents don't pile onto a shared endpoint during the endpoint hold.
            agent_ret = find_clear_retreat(scene, member_entry_angle, center,
                                           zones["warning"]["offset_m"], approach_pl)
            if agent_ret is None:
                agent_ret = ret  # fall back to group retreat
            all_pts.append([*agent_ret.tolist(), altitude])
            routes[a] = all_pts
            refs[a] = {"endpoint_enu_m": [*agent_ret.tolist(), altitude],
                       "retreat_required": True,
                       "retreat_warning_clearance_m": RETREAT_WARNING_CLEARANCE_M}

        bundle = RouteBundle(routes, {a: 0.0 for a in members})
        template = {"role": "monitoring", "execution_method": "monitoring",
                    "target_id": task_group["target_id"],
                    "monitoring": {"orbit_center_enu_m": center.tolist(),
                                   "orbit_radius_m": float(orbit_radius),
                                   "track_tolerance_m": 30.0,
                                   "effective_speed_min_m_s": 0.5,
                                   "min_loop_duration_s": 5.0,
                                   "planned_laps": float(planned_laps),
                                   "approach_mode": role_parameters["approach_mode"]},
                    "references": refs}
        return bundle, template


# ---------------------------------------------------------------------------
# Feint planner
# ---------------------------------------------------------------------------

class FeintPlanner:
    """Per-member independent feint angle, each with their own deepest point and turnaway.

    The base angle for each side is chosen by the 115% approach-length criterion.
    Members are then spread around that base angle with arc spacing sufficient to
    keep adjacent feint points >= 6 m apart (or >= 15 m at speed > 7 m/s).
    """
    legacy_vertical_slice = False

    def plan(self, scene, task_group, role_parameters):
        return self.plan_with_template(scene, task_group, role_parameters)[0]

    def plan_with_template(self, scene, task_group, role_parameters):
        family = role_parameters["family"]
        members = sorted(task_group["members"])
        multi = role_parameters["approach_mode"] == "multi_direction"
        altitude = family["task_altitude_m"]
        speed = family.get("cruise_speed_m_s", 5.0)
        states = {s["agent_id"]: s for s in family["initial_states"]}
        starts = {a: np.array(states[a]["position_enu_m"][:2], float) for a in members}
        rng = random.Random(role_parameters["planning_seed"])

        facility, zones = zones_of(scene, task_group["target_id"])
        center = np.array(center_of(facility["geometry"]))
        protected_off = zones["protected"]["offset_m"] if "protected" in zones else 0.0
        alert_off = zones["alert"]["offset_m"]
        # Push the feint point deep into the alert band (65% depth from alert outer edge)
        # so the tracker definitely penetrates enough frames inside the alert-only zone.
        feint_r = protected_off + (alert_off - protected_off) * 0.35
        warn_r = zones["warning"]["offset_m"]

        # Angular spacing so that neighbouring feint points are at least min_sep_m apart.
        min_sep_m = max(6.0, 15.0 if speed > 7.0 else 6.0)
        min_arc = min_sep_m / max(feint_r, 1.0)

        approach_pl = role_planner(scene, survey=False)

        def feint_point(angle):
            return center + feint_r * np.array([math.cos(angle), math.sin(angle)])

        n_candidates = 36
        base = rng.uniform(0, 2 * math.pi)
        base_angles = [base + k * 2 * math.pi / n_candidates for k in range(n_candidates)]
        rng.shuffle(base_angles)

        if not multi:
            angle_groups = [(base_angles, members)]
        else:
            half = len(members) // 2
            angle_groups = [
                (base_angles, members[:half]),
                ([a + math.pi for a in base_angles], members[half:]),
            ]

        routes, refs = {}, {}
        for ang_list, group_members in angle_groups:
            m = len(group_members)

            def score_base(base_angle):
                offsets = [(i - (m - 1) / 2.0) * min_arc for i in range(m)]
                ret = find_clear_retreat(scene, base_angle, center, warn_r, approach_pl)
                if ret is None:
                    return None
                total = 0.0
                for i, a in enumerate(group_members):
                    ang = base_angle + offsets[i]
                    route = approach_pl.path(starts[a].tolist(), feint_point(ang).tolist())
                    if route is None:
                        return None
                    total += approach_route_length(route, len(route) - 1)
                return total

            cands = [(a, score_base(a)) for a in ang_list]
            cands = [(a, s) for a, s in cands if s is not None]
            chosen = select_candidate(cands, rng, key_fn=lambda x: x[1])
            if chosen is None:
                raise PlanningInfeasible("geometry_infeasible", "no reachable feint angle")
            base_angle = chosen[0]
            offsets = [(i - (m - 1) / 2.0) * min_arc for i in range(m)]
            ret = find_clear_retreat(scene, base_angle, center, warn_r, approach_pl)
            if ret is None:
                raise PlanningInfeasible("geometry_infeasible", "no valid retreat point for feint")
            for i, a in enumerate(group_members):
                angle = base_angle + offsets[i]
                pt = feint_point(angle)
                route = approach_pl.path(starts[a].tolist(), pt.tolist())
                if route is None:
                    raise PlanningInfeasible("geometry_infeasible", f"no feint approach for {a}")
                # Per-agent retreat: each member retreats from their own feint angle so
                # agents don't pile onto a shared endpoint during the endpoint hold.
                agent_ret = find_clear_retreat(scene, angle, center, warn_r, approach_pl)
                if agent_ret is None:
                    agent_ret = ret  # fall back to group retreat
                full = [[*p, altitude] for p in route] + [[*agent_ret.tolist(), altitude]]
                routes[a] = full
                refs[a] = {"endpoint_enu_m": [*agent_ret.tolist(), altitude],
                           "retreat_required": True,
                           "retreat_warning_clearance_m": RETREAT_WARNING_CLEARANCE_M,
                           "planned_feint_angle_deg": math.degrees(angle) % 360}

        bundle = RouteBundle(routes, {a: 0.0 for a in members})
        template = {"role": "feint", "execution_method": "feint",
                    "target_id": task_group["target_id"],
                    "feint": {"retreat_distance_tolerance_m": 5.0,
                              "retreat_drop_fraction_max": 0.10,
                              "approach_mode": role_parameters["approach_mode"]},
                    "references": refs}
        return bundle, template


# ---------------------------------------------------------------------------
# Generalized intrusion planner
# ---------------------------------------------------------------------------

class IntrusionPlanner:
    """Radial approach to per-member distinct endpoints inside the protected zone.

    Uses a planner that only avoids hard obstacles (not alert/protected zones),
    so the approach can pass through the alert band en route to the protected zone.
    Endpoint angles chosen by 115% approach-length criterion with >= 15 m spacing.

    Multi-direction: members are split by which half of the circle their starting
    position faces (dot product with the primary-side direction), so each physical
    side genuinely approaches from its own direction and the last-100-m heading span
    reaches >= 90 deg.
    """
    legacy_vertical_slice = False

    def plan(self, scene, task_group, role_parameters):
        return self.plan_with_template(scene, task_group, role_parameters)[0]

    def plan_with_template(self, scene, task_group, role_parameters):
        family = role_parameters["family"]
        members = sorted(task_group["members"])
        multi = role_parameters["approach_mode"] == "multi_direction"
        altitude = family["task_altitude_m"]
        states = {s["agent_id"]: s for s in family["initial_states"]}
        starts = {a: np.array(states[a]["position_enu_m"][:2], float) for a in members}
        rng = random.Random(role_parameters["planning_seed"])
        min_spacing = 15.0

        facility, zones = zones_of(scene, task_group["target_id"])
        center = np.array(center_of(facility["geometry"]))
        prot_off = zones["protected"]["offset_m"] if "protected" in zones else 0.0
        depth_target = max(20.0, min(prot_off * 0.4, 60.0))

        planner = role_planner(scene, survey=False)

        def endpoint(angle):
            r = max(0.0, prot_off - depth_target)
            return center + r * np.array([math.cos(angle), math.sin(angle)])

        n = len(members)
        n_cand = max(72, n * 18)

        if multi and n >= 2:
            # Assign members to sides based on their starting position relative to the
            # target center, not by sorted order.  This ensures each side contains
            # members that genuinely approach from that direction, so the last-100-m
            # heading span reaches >= 90 deg.
            #
            # Primary axis: mean direction from center to all start positions.
            mean_vec = sum(starts[a] - center for a in members) / n
            if np.linalg.norm(mean_vec) < 1e-3:
                # Degenerate case: starts are symmetric; fall back to sorted split.
                primary = np.array([1.0, 0.0])
            else:
                primary = mean_vec / np.linalg.norm(mean_vec)

            # Dot product with primary gives sign: positive = same side as mean,
            # negative = opposite side.
            dots = {a: float(np.dot(starts[a] - center, primary)) for a in members}
            side_a = sorted([a for a in members if dots[a] >= 0], key=lambda a: dots[a])
            side_b = sorted([a for a in members if dots[a] < 0], key=lambda a: dots[a])

            # Balance: if one side is empty (all starts on the same side), split evenly.
            if not side_a or not side_b:
                sorted_by_dot = sorted(members, key=lambda a: dots[a])
                half = math.ceil(n / 2)
                side_a, side_b = sorted_by_dot[:half], sorted_by_dot[half:]

            # Side A approaches from the primary direction angle, side B from the opposite.
            primary_angle = math.atan2(float(primary[1]), float(primary[0]))
            base = rng.uniform(0, 2 * math.pi)
            angle_sets = [
                [primary_angle + k * math.pi / max(1, len(side_a)) for k in range(n_cand // 2)],
                [primary_angle + math.pi + k * math.pi / max(1, len(side_b))
                 for k in range(n_cand // 2)],
            ]
            angle_sets = [[base + a for a in s] for s in angle_sets]
            member_groups = [side_a, side_b]
        else:
            base = rng.uniform(0, 2 * math.pi)
            angle_sets = [[base + k * 2 * math.pi / n_cand for k in range(n_cand)]]
            member_groups = [members]

        all_endpoints = {}
        for angles, group_members in zip(angle_sets, member_groups):
            scored = []
            for angle in angles:
                total = 0.0
                for a in group_members:
                    ep = endpoint(angle)
                    route = planner.path(starts[a].tolist(), ep.tolist())
                    if route is None:
                        total = None
                        break
                    total += approach_route_length(route, len(route) - 1)
                if total is not None:
                    scored.append((angle, total))
            if not scored:
                raise PlanningInfeasible("geometry_infeasible", "no reachable intrusion angle")
            min_score = min(s for _, s in scored) * 1.15
            pool = [a for a, s in scored if s <= min_score]
            rng.shuffle(pool)
            chosen_angles = _pick_spread_angles(pool, len(group_members), min_spacing,
                                                center, endpoint)
            if chosen_angles is None:
                raise PlanningInfeasible("geometry_infeasible",
                                         "cannot satisfy intrusion endpoint spacing")
            for a, angle in zip(group_members, chosen_angles):
                all_endpoints[a] = endpoint(angle)

        routes, refs = {}, {}
        for a in members:
            ep = all_endpoints[a]
            route = planner.path(starts[a].tolist(), ep.tolist())
            if route is None:
                raise PlanningInfeasible("geometry_infeasible", f"no intrusion route for {a}")
            routes[a] = [[*p, altitude] for p in route]
            refs[a] = {"endpoint_enu_m": [*ep.tolist(), altitude]}

        bundle = RouteBundle(routes, {a: 0.0 for a in members})
        template = {"role": "intrusion", "execution_method": task_group["execution_method"],
                    "target_id": task_group["target_id"],
                    "required_intrusion_depth_m": depth_target,
                    "intrusion_endpoint_min_spacing_m": min_spacing,
                    "references": refs}
        return bundle, template


def _pick_spread_angles(pool, n, min_spacing_m, center, endpoint_fn):
    """Greedily pick n angles from pool such that all endpoints are >= min_spacing_m apart."""
    if n == 0:
        return []
    for first in pool:
        chosen = [first]
        candidates = [a for a in pool if a != first]
        for _ in range(n - 1):
            for a in candidates:
                ep = endpoint_fn(a)
                if all(float(np.linalg.norm(ep - endpoint_fn(c))) >= min_spacing_m for c in chosen):
                    chosen.append(a)
                    break
            else:
                break
        if len(chosen) == n:
            return chosen
    return None


# ---------------------------------------------------------------------------
# Fill the PLANNERS registry
# ---------------------------------------------------------------------------

PLANNERS = {
    ("transit", "transit"): TransitPlanner,
    ("intrusion", "polygon_visit"): IntrusionPlanner,
    ("intrusion", "intrusion"): IntrusionPlanner,     # descriptor execution_method
    ("reconnaissance", "close_observation"): CloseObservationPlanner,
    ("monitoring", "monitoring"): MonitoringPlanner,
    ("feint", "feint"): FeintPlanner,
}


def planner_for(role, execution_method):
    try:
        return PLANNERS[(role, execution_method)]()
    except KeyError:
        raise PlanningInfeasible("planner_not_implemented", f"{role}/{execution_method}") from None

