"""M3a transit work shapes sampled from feasible lateral chord intervals."""
import math
import numpy as np

from task_v07.geometry import offset_geometry
from task_v07.expansion.contracts import PlannerUnavailable
from .free_space import chord_intervals, quantile_interval, TOL
from .route import GeometryRejected, line_interval


def draw_shape(spec, region, rng, free):
    if spec["execution_method"] in ("area_search", "close_observation", "monitoring", "feint"):
        from .operation_shapes import draw_operation
        return draw_operation(spec, region, rng, free)
    if spec["role"] != "transit" or spec["execution_method"] != "transit":
        raise PlannerUnavailable("M3a has no unified shape for this execution method")
    if region.is_empty:
        raise GeometryRejected("empty_work_region", [{"scope": "candidate_work_domain", "empty": True}])
    warning = offset_geometry(free.target["geometry"], free.offsets["warning"])
    attempts = []
    for attempt in range(free.cfg["shape_attempts"]):
        theta = rng.uniform(*spec["params"]["direction_deg"])
        bend = rng.random() < spec["params"]["bend_probability"]
        bend_deg = rng.uniform(*spec["params"]["bend_angle_deg"]) if bend else 0.
        sign = rng.choice((-1, 1)) if bend else 1
        draw = {"direction_deg": theta, "bend": bend, "bend_angle_deg": bend_deg, "bend_sign": sign,
                "split_draws": [], "shape_attempt": attempt}
        slots = []
        try:
            for side, stock in enumerate(spec["public_split"]["members"]):
                angle = math.radians(theta)+spec["public_split"]["relative_bearings_rad"][side]
                direction = np.array([math.cos(angle), math.sin(angle)])
                normal = np.array([-direction[1], direction[0]])
                spacing = spec["family"]["lateral_spacing_m"]; half = spacing*(len(stock)-1)/2
                intervals = chord_intervals(free, direction, half)
                q = rng.uniform(*spec["params"]["chord_quantile"])
                draw["split_draws"].append({"split_index": side, "chord_quantile": q, "feasible_lateral_intervals_m": intervals})
                if not intervals:
                    raise GeometryRejected("no_feasible_chord_interval", [{"split_index": side, "half_width_m": half}])
                lateral = quantile_interval(intervals, q)
                draw["split_draws"][-1]["accepted_lateral_m"] = lateral
                for j in range(len(stock)):
                    origin = (lateral+(j-(len(stock)-1)/2)*spacing)*normal
                    interval = line_interval(warning, origin, direction)
                    if interval is None or interval[1]-interval[0] < 1.:
                        raise GeometryRejected("warning_chord_too_short")
                    low, high = interval
                    entry = origin+low*direction
                    exit_direction = direction
                    work = [entry]
                    if bend:
                        pivot = origin+(low+high)/2*direction
                        rotation = math.radians(sign*bend_deg)
                        exit_direction = np.array([math.cos(angle+rotation), math.sin(angle+rotation)])
                        outgoing = line_interval(warning, pivot, exit_direction)
                        if outgoing is None or outgoing[1] < 1.:
                            raise GeometryRejected("bent_chord_exit_unavailable")
                        work.extend([pivot, pivot+outgoing[1]*exit_direction])
                    else:
                        work.append(origin+high*direction)
                    evidence = [dict(segment=k, **issue) for k, (a, b) in enumerate(zip(work, work[1:]))
                                for issue in free.segment_issues(a, b)]
                    if evidence:
                        raise GeometryRejected("work_segment_clearance", evidence)
                    slots.append({"split_index": side, "slot_id": f"{side}:{j}", "entry": entry.tolist(),
                                  "direction": direction.tolist(), "exit_direction": exit_direction.tolist(),
                                  "work": [p.tolist() for p in work]})
            draw["rejected_shape_attempts"] = attempts
            return {"kind": "transit", "slots": slots, "draw": draw}
        except GeometryRejected as exc:
            attempts.append({"draw": draw, "reason": exc.reason, "evidence": exc.evidence})
    raise GeometryRejected("shape_search_budget_exhausted", attempts)
