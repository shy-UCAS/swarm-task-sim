"""Straight passage planning and trajectory-only, phase-local evidence.

Thresholds are provisional for the v0.6 pilot. They use metres and seconds,
never commanded speed, planner waypoints, flight pattern, or intent labels.
"""

import copy
import math

from .mission_schema import _object, _enum, _numeric
from .registry import IntentSpec, PlannerSpec, PlanResult


VALIDATOR_VERSION = "rapid_passage_geometry_v1"
THRESHOLDS = dict(boundary_margin_m=2.0, max_cross_track_m=3.0,
                  low_speed_m_s=0.5, max_low_speed_duration_s=1.0,
                  max_backtrack_m=2.0, max_path_chord_ratio=1.10)
THRESHOLD_BASIS = {
    "boundary_margin_m": "2 m provisional exterior margin exceeds nominal 0.3 m sample displacement at 3 m/s, 10 Hz; arrival tolerance is design allowance, not sensor accuracy; pilot calibration required",
    "max_cross_track_m": "3 m provisional straight-geometry allowance; no measured sensor-accuracy bound claimed; pilot calibration required",
    "low_speed_m_s": "one quarter of 2 m/s minimum shared command speed; measured movement only",
    "max_low_speed_duration_s": "10 samples at 10 Hz and twice the 0.5 s allowed observation gap",
    "max_backtrack_m": "2 m provisional reversal allowance; design tolerance requires pilot calibration",
    "max_path_chord_ratio": "10 percent provisional measured excess path allowance; pilot calibration required",
}
OPPOSITE = dict(north="south", south="north", east="west", west="east")
ECHELON_OFFSET_M = 2.0
ECHELON_OFFSET_BASIS = ("Fixed adjacent longitudinal displacement of 2 m, twice the 1 m design arrival tolerance; "
    "lateral spacing remains the line-abreast spacing and all clearance/world checks are unchanged. "
    "A maximum 6 m group span at four vehicles limits extra exterior footprint; not tuned to candidate outcomes.")


def normalize_params(params):
    result = copy.deepcopy(params)
    _object(result, "rapid_passage intent_params", ("objective",))
    _enum(result, "objective", "rapid_passage intent_params", ("single_straight_crossing",))
    return result


def normalize_planner(params, spec):
    result = copy.deepcopy(params)
    _object(result, "rapid_passage planner.params", ("entry_side", "exit_margin_m", "tracking_margin_m"))
    _enum(result, "entry_side", "rapid_passage planner.params", tuple(OPPOSITE))
    _numeric(result, "exit_margin_m", "rapid_passage planner.params", 4, 30)
    _numeric(result, "tracking_margin_m", "rapid_passage planner.params", 0, 100)
    if spec["execution"].get("control_mode") != "semantic_phase_route_v1":
        raise ValueError("rapid_passage requires semantic_phase_route_v1")
    return result


def _plan(spec, echelon=False):
    scenario, mission, execution = spec["scenario"], spec["mission"], spec["execution"]
    region = next(r for r in scenario["regions"] if r["id"] == mission["target_region_id"])
    params = spec["planner"]["params"]
    side = params["entry_side"]
    longitudinal, lateral = ("north", "east") if side in ("north", "south") else ("east", "north")
    along_size = region["height_m" if longitudinal == "north" else "width_m"]
    cross_size = region["width_m" if lateral == "east" else "height_m"]
    low, cross_low = region[f"min_{longitudinal}_m"], region[f"min_{lateral}_m"]
    sign = -1 if side in ("north", "east") else 1
    entry_boundary = low + along_size if sign < 0 else low
    exit_boundary = low if sign < 0 else low + along_size
    vehicles = sorted(scenario["vehicles"], key=lambda v: (v[f"{lateral}_m"], v["id"]))
    n = len(vehicles)
    routes, assignments = {}, {}
    for index, vehicle in enumerate(vehicles):
        cross = cross_low + cross_size * (index + .5) / n
        # Translate adjacent straight lanes by 2 m along the travel axis.
        # Equal total lengths preserve that offset at constant speed. The
        # leading entry and trailing exit retain the original exterior margin.
        entry_distance = params["exit_margin_m"] + ((n - 1 - index) * ECHELON_OFFSET_M if echelon else 0)
        exit_distance = params["exit_margin_m"] + (index * ECHELON_OFFSET_M if echelon else 0)
        entry = {f"{lateral}_m": cross, f"{longitudinal}_m": entry_boundary - sign * entry_distance}
        terminal = {f"{lateral}_m": cross, f"{longitudinal}_m": exit_boundary + sign * exit_distance}
        agent = vehicle["id"]
        routes[agent] = dict(approach=[entry], transit=[terminal],
            **{"return": [dict(east_m=vehicle["east_m"], north_m=vehicle["north_m"])]
               if mission["return_required"] else []})
        assignments[agent] = f"transit_lane_{index:02d}"
    diagnostics = dict(entry_side=side, exit_side=OPPOSITE[side], exit_margin_m=params["exit_margin_m"],
                       transit_axis=longitudinal, endpoint_semantics="exit is final transit event")
    if echelon:
        diagnostics.update(echelon_offset_m=ECHELON_OFFSET_M, echelon_group_span_m=(n-1)*ECHELON_OFFSET_M,
                           offset_basis=ECHELON_OFFSET_BASIS)
    return PlanResult(routes, assignments, diagnostics)


def _outside(point, region, margin):
    x, y = point[:2]
    west, south = region["min_east_m"], region["min_north_m"]
    east, north = west + region["width_m"], south + region["height_m"]
    hits = [side for side, passed in (("west", x <= west-margin), ("east", x >= east+margin),
             ("south", y <= south-margin), ("north", y >= north+margin)) if passed]
    return hits[0] if len(hits) == 1 else None


def _crossed_side(a, b, region):
    """Side hit by the adjacent measured crossing segment, never a prior side.

    Corner crossings have no unique side and deliberately remain unknown.
    Boundary points are not interior; a segment may start/end on the side.
    """
    west, south = region["min_east_m"], region["min_north_m"]
    east, north = west+region["width_m"], south+region["height_m"]
    hits = []
    for side, axis, bound, other_low, other_high in (("west", 0, west, south, north),
            ("east", 0, east, south, north), ("south", 1, south, west, east), ("north", 1, north, west, east)):
        delta = b[axis]-a[axis]
        if abs(delta) <= 1e-12:
            continue
        ratio = (bound-a[axis])/delta
        other = a[1-axis] + ratio*(b[1-axis]-a[1-axis])
        if -1e-9 <= ratio <= 1+1e-9 and other_low-1e-9 <= other <= other_high+1e-9:
            hits.append(side)
    return hits[0] if len(hits) == 1 else None


def measure_passage(rows, region, *, max_gap_s=.5, start_s=None, end_s=None, complete_window=True):
    """Measure one real trajectory; missing evidence never becomes a plan value."""
    from .mission_evaluation import window_evidence
    from .observations import finite_number

    empty = dict(version=VALIDATOR_VERSION, success=None, entry_side=None, exit_side=None, crossed=None,
        inside_dwell_s=None, max_cross_track_m=None, backtrack_m=None, turning_rad=None,
        path_chord_ratio=None, interior_excursions=None, evidence_complete=False,
        conditions={k: None for k in ("entered", "opposite_exit", "straight", "no_dwell", "no_loop")}, issues=[])
    if not rows:
        return dict(empty, issues=["missing_trajectory"])
    start = rows[0][0] if start_s is None else start_s
    end = rows[-1][0] if end_s is None else end_s
    if not all(finite_number(v) for v in (start, end)) or end <= start:
        return dict(empty, issues=["invalid_or_empty_window"])
    evidence = window_evidence(rows, start, end, max_gap_s)
    points = sorted({t: xyz for t, xyz in evidence["points"]}.items())
    if not evidence["complete"] or not complete_window or len(points) < 3:
        return dict(empty, issues=["incomplete_transit_trajectory_or_window"])
    west, south = region["min_east_m"], region["min_north_m"]
    east, north = west + region["width_m"], south + region["height_m"]
    inside = lambda p: west < p[0] < east and south < p[1] < north
    interior_indices = [i for i, (_, p) in enumerate(points) if inside(p)]
    conditions = {key: False for key in empty["conditions"]}
    if not interior_indices:
        return dict(empty, evidence_complete=True, success=False, crossed=False, conditions=conditions,
                    interior_excursions=0, issues=["no_measured_region_entry"])
    first, last = interior_indices[0], interior_indices[-1]
    entry_candidates = [_outside(p, region, THRESHOLDS["boundary_margin_m"]) for _, p in points[:first]]
    exit_candidates = [_outside(p, region, THRESHOLDS["boundary_margin_m"]) for _, p in points[last+1:]]
    entry_crossing = _crossed_side(points[first-1][1], points[first][1], region) if first else None
    exit_crossing = _crossed_side(points[last][1], points[last+1][1], region) if last+1 < len(points) else None
    entry = entry_crossing if entry_crossing in entry_candidates else None
    exit_side = exit_crossing if exit_crossing in exit_candidates else None
    conditions["entered"] = entry is not None
    conditions["opposite_exit"] = entry is not None and exit_side == OPPOSITE[entry]
    if entry is None:
        return dict(empty, evidence_complete=True, success=False, crossed=False, conditions=conditions,
                    exit_side=exit_side, issues=["no_exterior_entry_evidence"])
    axis, sign = (0, 1) if entry == "west" else (0, -1) if entry == "east" else (1, 1) if entry == "south" else (1, -1)
    selected = points[first:last+1]
    a, b = selected[0][1], selected[-1][1]
    chord = math.dist(a[:2], b[:2])
    distance = sum(math.dist(p[:2], q[:2]) for (_, p), (_, q) in zip(selected, selected[1:]))
    cross = (max(abs((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))/chord for _, p in selected)
             if chord > 1e-9 else float("inf"))
    backtrack = sum(max(0., -sign*(q[axis]-p[axis])) for (_, p), (_, q) in zip(selected, selected[1:]))
    ratio = distance/chord if chord > 1e-9 else None
    current_dwell = max_dwell = 0.0
    for (ta, p), (tb, q) in zip(selected, selected[1:]):
        if inside(p) and inside(q) and math.dist(p[:2], q[:2])/(tb-ta) < THRESHOLDS["low_speed_m_s"]:
            current_dwell += tb-ta
            max_dwell = max(max_dwell, current_dwell)
        else:
            current_dwell = 0.0
    excursions = 1 + sum(not inside(points[i-1][1]) and inside(points[i][1]) for i in range(first+1, last+1))
    # Heading turns are diagnostic and measured after 1 m spatial decimation.
    coarse = [selected[0][1]]
    for _, point in selected[1:]:
        if math.dist(coarse[-1][:2], point[:2]) >= 1.0:
            coarse.append(point)
    headings = [math.atan2(q[1]-p[1], q[0]-p[0]) for p, q in zip(coarse, coarse[1:])]
    turning = sum(abs(math.atan2(math.sin(q-p), math.cos(q-p))) for p, q in zip(headings, headings[1:]))
    conditions["straight"] = cross <= THRESHOLDS["max_cross_track_m"] and ratio is not None and ratio <= THRESHOLDS["max_path_chord_ratio"]
    conditions["no_dwell"] = max_dwell <= THRESHOLDS["max_low_speed_duration_s"]
    conditions["no_loop"] = excursions == 1 and backtrack <= THRESHOLDS["max_backtrack_m"]
    return dict(empty, success=all(conditions.values()), entry_side=entry, exit_side=exit_side, crossed=conditions["entered"] and conditions["opposite_exit"],
        inside_dwell_s=max_dwell, max_cross_track_m=cross if math.isfinite(cross) else None,
        backtrack_m=backtrack, turning_rad=turning, path_chord_ratio=ratio, interior_excursions=excursions,
        evidence_complete=True, conditions=conditions, issues=[])


def evaluate_channel(scene, traces, windows, clocks):
    del clocks
    from .mission_evaluation import tri_and
    spec = scene["task_spec"]
    region = next(r for r in spec["scenario"]["regions"] if r["id"] == spec["mission"]["target_region_id"])
    per_agent = {}
    for vehicle in scene["vehicles"]:
        agent = vehicle["id"]
        matching = [w for w in windows if w["agent_id"] == agent and w["semantic_phase"] == "transit" and w["service_enabled"]]
        window = matching[0] if len(matching) == 1 else {}
        valid_bounds = window.get("start_s") is not None and window.get("end_s") is not None
        per_agent[agent] = measure_passage(traces.get(agent, []) if valid_bounds else [], region,
            max_gap_s=scene["max_gap_s"], start_s=window.get("start_s"), end_s=window.get("end_s"),
            complete_window=window.get("complete_execution_window") is True)
    conditions = {key: tri_and([item["conditions"][key] for item in per_agent.values()])
                  for key in ("entered", "opposite_exit", "straight", "no_dwell", "no_loop")}
    details = dict(version=VALIDATOR_VERSION, success=tri_and(list(conditions.values())),
        evidence_complete=all(item["evidence_complete"] for item in per_agent.values()),
        thresholds=THRESHOLDS, per_agent=per_agent)
    return dict(conditions=conditions, metrics={"rapid_passage": details})


def behavior_labels(scene, truth):
    success = truth.get("rapid_passage", {}).get("success")
    return dict(planned_behaviors=["direct_passage"], observed_behaviors=[dict(name="direct_passage",
        agent_ids=[v["id"] for v in scene["vehicles"]], status="verified" if success is True else "failed" if success is False else "unknown",
        evidence_basis="SIM_truth_positions_transit_window", rule_version=VALIDATOR_VERSION)])


intent_spec = IntentSpec("rapid_passage", ("single_straight_crossing",), ("approach", "transit", "return"),
    frozenset({"transit"}), normalize_params, ("line_abreast_v1",), evaluate_channel,
    VALIDATOR_VERSION, behavior_labels, ("rapid_passage",))
planner_specs = (PlannerSpec("line_abreast_v1", "line_abreast_v1", normalize_planner, _plan),)
echelon_candidate_planner = PlannerSpec("echelon_v1", "echelon_v1", normalize_planner, lambda spec: _plan(spec, echelon=True))


def echelon_candidate_registration():
    """Scope an offline candidate compile; echelon is not a production choice."""
    from .registry import temporary_candidate_planner
    return temporary_candidate_planner("rapid_passage", "echelon", echelon_candidate_planner)
