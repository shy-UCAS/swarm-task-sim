"""V8-19: retain the transit geometry and append one sampled dwell on the selected member curves.

No search follows an empty dwell set. Only the existing shape stream's two final integer draws are added.
Runtime costs and original exception text stay in transit's process-local telemetry, outside contracts.
"""
import math
import re
import time
from dataclasses import replace

import numpy as np

from ...contract.monitoring import Failure
from ...scene.exact import signed_distance
from ...sim.types import SimContractError
from .. import transit_chords as TC
from ..close_observation_numeric import dwell_condition_masks, dwell_grid, draw_dwell
from ..dwell_nominal import member_nominal_with_dwell
from ..nominal import member_nominal
from ..nominal_checks import screen_close_observation_member
from ..skeleton import reference_guidance, semantic_lines
from . import transit as T

INTENT = "close_observation"


def propose_and_build(ctx, group, task, states, key):
    if task.intent != INTENT:
        raise ValueError("close observation builder requires its explicit task intent")
    return project_plan(T.propose_and_build(ctx, group, task, states, key))


def last_attempt_timing():
    return T.last_attempt_timing()


def final_failure(ctx, group, task, attempt_records):
    return T.final_failure(ctx, group, task, attempt_records)


def draw_summary(P, formation):
    out = T.draw_summary(P, formation)
    out["intent"] = INTENT
    out["dwell"] = project((P or {}).get("dwell"), DWELL, "draw.dwell")
    return out


def _margins(base, points):
    out = {}
    for c in base:
        sdf = np.asarray(signed_distance(c.geometry, points), float)
        if c.sense == 1:
            value = sdf - c.minimum_m
        elif c.sense == -1:
            value = -sdf - c.minimum_m
        elif c.sense == 0:
            value = np.abs(sdf) - c.minimum_m
        else:
            raise ValueError("unsupported clearance sense")
        out[c.name] = value
    return out


def dwell_candidates(ctx, plan):
    """Compute the finite set once on the LP's complete, already connected member curves."""
    target = plan.witnesses["target_id"]
    cons = TC.transit_base(ctx, target, intent=INTENT)
    f = ctx.facility_by_id[target]
    stations = dwell_grid(plan.anchors["collect_s"], plan.anchors["terminal_s"])
    mapping = plan.witnesses["member_map_transit"]["members"]
    if not plan.members or set(mapping) != set(plan.members):
        raise ValueError("complete member map is required for dwell candidates")
    member_s, points, ranges, domains = {}, {}, {}, {}
    domain = np.ones(len(stations), bool)
    guidance = reference_guidance()
    for mid in sorted(plan.members):
        mp = plan.members[mid]
        mr = mapping[mid]
        rs, ms = np.asarray(mr["reference_s"], float), np.asarray(mr["member_s"], float)
        if rs.ndim != 1 or len(rs) < 2 or ms.shape != rs.shape or not np.isfinite([rs, ms]).all():
            raise ValueError("invalid member station map")
        if np.any(np.diff(rs) <= 0.0) or np.any(np.diff(ms) <= 0.0):
            raise ValueError("member station map must be strictly increasing")
        domain &= (stations >= rs[0]) & (stations <= rs[-1])
        domains[mid] = (float(rs[0]), float(rs[-1]))
        member_s[mid] = np.interp(stations, rs, ms)
        xy = np.asarray(mp.curve_xy, float)
        cs = np.r_[0.0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
        domain &= (member_s[mid] >= cs[0]) & (member_s[mid] <= cs[-1])
        points[mid] = np.column_stack([np.interp(member_s[mid], cs, xy[:, k]) for k in (0, 1)])
        nominal = member_nominal(mp, guidance=guidance)
        lines = semantic_lines(mid, nominal, cons["crossing_boundaries"], target,
                               band_m=ctx.params["pre_entry_warning_clearance_m"],
                               align_m=ctx.params["alignment_length_m"])
        ranges[mid] = tuple((float(line[5]["s_from_m"]), float(line[5]["s_to_m"])) for line in lines)
    masks = dwell_condition_masks(stations, member_s, points, ranges, f.layers["warning"], f.layers["alert"], cons["base"])
    masks["mapping_domain"] = domain
    mask = np.logical_and.reduce(list(masks.values()))
    return {"stations": stations, "mask": mask, "member_s": member_s, "points": points,
            "ranges": ranges, "domains": domains, "masks": masks,
            "warning": f.layers["warning"], "alert": f.layers["alert"], "base": cons["base"]}


def _ordinary_failure(plan, stage, diagnostics, error_type=None):
    extra = {"stage": stage, "shape_audit_failed": False, "dwell_diagnostics": diagnostics}
    if error_type is not None:
        extra["error_type"] = error_type
    failure = Failure("candidate_rejected", stage, stage, extra, None)
    return project_plan(replace(plan, failure=failure, witnesses={**(plan.witnesses or {}),
                                                               "dwell_diagnostics": diagnostics}))


def add_dwell(ctx, plan, rng):
    t0 = time.perf_counter()
    diagnostics = {"candidate_count": 0, "set_size": 0, "rejected_by_condition": {},
                   "rejection_counts_overlap": True, "members": {}}
    try:
        c = dwell_candidates(ctx, plan)
        T._LAST_TIMING["dwell_set_s"] = time.perf_counter() - t0
        feasible = c["stations"][c["mask"]]
        diagnostics.update(candidate_count=int(len(c["stations"])), set_size=int(len(feasible)),
                           rejected_by_condition={name: int(np.count_nonzero(~value)) for name, value in c["masks"].items()})
        if not len(feasible):
            return _ordinary_failure(plan, "close_obs_dwell_set", diagnostics)
        # This is the same shape Generator held by transit._build_with_cells; no stream restart.
        station, duration = draw_dwell(feasible, rng)
        index = int(np.searchsorted(feasible, station))
        raw_index = int(np.searchsorted(c["stations"], station))
        choice = {"reference_station_m": station, "set_size": int(len(feasible)),
                  "index": index, "duration_ticks": round(duration * 10)}
        plan = replace(plan, proposal={**plan.proposal, "dwell": choice})
        windows, nominals, screens = {}, {}, {}
        t_ref = time.perf_counter()
        for mid in sorted(plan.members):
            sd = float(c["member_s"][mid][raw_index])
            pd = tuple(map(float, c["points"][mid][raw_index]))
            nom = member_nominal_with_dwell(plan.members[mid], (sd, duration), guidance=reference_guidance())
            if not np.array_equal(pd, nom.dwell_point_xy):
                raise ValueError("dwell split point differs from the selected member interpolation")
            windows[mid] = (sd, duration, pd)
            nominals[mid] = nom
            margins = _margins(c["base"], np.asarray(pd))
            diagnostics["members"][mid] = {
                "member_station_m": sd, "point_xy": pd,
                "warning_sdf_m": float(signed_distance(c["warning"], pd)),
                "alert_sdf_m": float(signed_distance(c["alert"], pd)),
                "base_min_margin_m": min((float(v) for v in margins.values()), default=math.inf),
                "base_margins_m": {name: float(value) for name, value in margins.items()},
                "semantic_ranges_m": c["ranges"][mid], "mapping_domain_m": c["domains"][mid],
                "nominal_arrival_s": nom.arrival_s, "nominal_departure_s": nom.departure_s,
                "duration_s": duration, "nominal_end_s": nom.end_s,
                "duration_sum_s": nom.duration_sum, "duration_roundoff_s": nom.duration_roundoff_s,
                "endpoint_distance_m": float(np.hypot(*(nom.curve.xy[-1] - np.asarray(pd))))}
            f0 = math.ceil(nom.release_s * 10 - 1e-9)
            f1 = math.floor((nom.end_s + nom.hold_s) * 10 + 1e-9)
            time_us = np.arange(f0, f1 + 1, dtype=np.int64) * 100_000
            p, v, _ = nom.pva(time_us / 1e6)
            scr = screen_close_observation_member(ctx.facilities, plan.witnesses["target_id"], time_us, p, v)
            screens[mid] = {name: scr[name] for name in ("passed", "conditions", "counts")}
        T._LAST_TIMING["dwell_reference_s"] = time.perf_counter() - t_ref
        arrivals = [n.arrival_s for n in nominals.values()]
        pd = [np.asarray(windows[m][2]) for m in sorted(windows)]
        pairs = [float(np.hypot(*(pd[i] - pd[j]))) for i in range(len(pd)) for j in range(i + 1, len(pd))]
        diagnostics["member_arrival_span_s"] = float(max(arrivals) - min(arrivals))
        diagnostics["pd_min_pair_distance_m"] = min(pairs) if pairs else None
        total = float(max(n.end_s + n.hold_s for n in nominals.values()) - min(n.release_s for n in nominals.values()))
        witnesses = {**plan.witnesses, "intent": INTENT, "dwell_windows": windows, "dwell_diagnostics": diagnostics,
                     "turn_ranges": {}, "screen": screens, "nominal_duration_s": total}
        return project_plan(replace(plan, witnesses=witnesses, nominal_duration_s=total,
                                    member_nominal_s={m: n.travel_s for m, n in nominals.items()},
                                    topology={**(plan.topology or {}), "final": INTENT}))
    except (ValueError, SimContractError) as exc:
        T._LAST_TIMING["dwell_exception"] = {"error_type": type(exc).__name__, "reason": str(exc)}
        return _ordinary_failure(plan, "close_obs_reference", diagnostics, type(exc).__name__)


# Each dictionary has a declared shape. MAP allows member/constraint identifiers, never arbitrary fields.
DATA = object()  # scalar or a sequence of scalars/sequences; dictionaries are not permitted
MAP = lambda shape: ("map", shape)
SEQ = lambda shape: ("sequence", shape)
DWELL = dict.fromkeys(("reference_station_m", "set_size", "index", "duration_ticks"), DATA)
CORRIDOR = dict.fromkeys(("available", "reason", "D", "inset_interval", "rows_total", "certified_rows", "run",
                          "certified_length_m", "inset_length_m"), DATA)
LP = dict.fromkeys(("feasible", "fallback_reason", "lp_status", "lp_message", "lp_nit", "objective", "max_residual",
                    "kappa_max", "slope_max", "n_controls"), DATA)
LP["max_residual"] = dict.fromkeys(("slope", "curvature_per_m", "corridor_m"), DATA)
CURVE_AUDIT = {**dict.fromkeys(("ok", "kappa_max_abs", "at_x", "min_den", "slope_max", "turn_ok", "lane_ok", "slope_ok",
                               "candidates"), DATA), "lane": MAP(DATA)}
CHORD_ERROR = dict.fromkeys(("lane", "constraint", "margin_m", "check", "interval", "required_m", "straight_m", "facility",
                             "signed_m"), DATA)
CHORD_AUDIT = {"feasible": DATA, "first_error": CHORD_ERROR, "margins": MAP(DATA)}
FORMATION_STEP = {**dict.fromkeys(("formation", "lateral_step_m", "feasible_cells", "n_cells", "query_id"), DATA),
                  "reasons": MAP(DATA)}
REPAIR = dict.fromkeys(("kind", "from", "to", "forced_by", "from_m", "to_m"), DATA)
PROPOSAL = dict.fromkeys(("intent", "theta_idx", "theta_deg", "h_m", "origin_xy", "u", "n", "cell_index", "cells_feasible",
                          "chord_query_id", "x_c", "x_t", "x_in", "collect_D_m", "collect_candidates", "K",
                          "logit_quantiles", "logit_coefficients", "member_slot_order", "formation", "lateral_step_m",
                          "x_entry_ref", "x_exit_ref", "curved", "fallback_reason", "collection_xy", "terminal_xy"), DATA)
PROPOSAL.update(repairs=SEQ(REPAIR), formation_steps=SEQ(FORMATION_STEP), chord_audit=CHORD_AUDIT, corridor=CORRIDOR,
                lp=LP, curve_audit=CURVE_AUDIT, curve=dict.fromkeys(("knots_m", "controls_m", "x_range", "target_m"), DATA),
                start_connections=MAP(DATA), starts=MAP(dict.fromkeys(("skeleton_delta_m", "primitives"), DATA)),
                speed_events=dict.fromkeys(("times_s", "speeds_m_s"), DATA), dwell=DWELL)
CONDITIONS = dict.fromkeys(("started_outside_target_warning", "entered_warning", "single_warning_visit", "max_target_layer_one",
                            "other_layers_within_limit", "observation_dwell", "no_revisit_window",
                            "ended_outside_all_warning", "single_transit_window", "no_dwell_window"), DATA)
SCREEN = {"passed": DATA, "conditions": CONDITIONS,
          "counts": dict.fromkeys(("frames", "visits", "max_target_layer", "max_other_layer"), DATA)}
MEMBER_MAP = dict.fromkeys(("reference_s", "shifted_reference_s", "member_s", "lateral_m", "longitudinal_m",
                            "entry_member_s", "exit_member_s", "collect_member_s"), DATA)
DWELL_MEMBER = {**dict.fromkeys(("member_station_m", "point_xy", "warning_sdf_m", "alert_sdf_m", "base_min_margin_m",
                                "semantic_ranges_m", "mapping_domain_m", "nominal_arrival_s", "nominal_departure_s",
                                "duration_s", "nominal_end_s", "duration_sum_s", "duration_roundoff_s", "endpoint_distance_m"), DATA),
                "base_margins_m": MAP(DATA)}
DWELL_DIAGNOSTICS = {**dict.fromkeys(("candidate_count", "set_size", "rejection_counts_overlap", "member_arrival_span_s",
                                     "pd_min_pair_distance_m"), DATA),
                     "rejected_by_condition": dict.fromkeys(("finite", "semantic", "warning", "alert", "base", "mapping_domain"), DATA),
                     "members": MAP(DWELL_MEMBER)}
WITNESSES = {**dict.fromkeys(("intent", "target_id", "separation", "required_separation_m", "nominal_duration_s"), DATA),
             "turn_ranges": MAP(DATA), "constraints": MAP(MAP(DATA)), "crossings": MAP(DATA), "screen": MAP(SCREEN),
             "speed": dict.fromkeys(("errors_s", "dropped", "events", "T_upper_s", "times_s", "speeds_m_s"), DATA),
             "delays_s": MAP(DATA), "travel_to_collection_s": MAP(DATA), "chord": CHORD_AUDIT, "corridor": CORRIDOR,
             "lp": LP, "curve_audit": CURVE_AUDIT, "member_map_transit": {"schema": DATA, "members": MAP(MEMBER_MAP)},
             "dwell_windows": MAP(DATA), "dwell_diagnostics": DWELL_DIAGNOSTICS}
DRAW = {**dict.fromkeys(("intent", "formation", "theta_deg", "h_m", "cell_index", "cells_feasible", "collect_D_m", "K",
                         "logit_quantiles", "curved", "fallback_reason"), DATA), "dwell": DWELL}
FAILURE_WITNESS = {**dict.fromkeys(("stage", "shape_audit_failed", "member", "constraint", "margin_m", "chord_index", "point",
                                    "facility", "kind", "s_m", "max_residual_m", "straight_m", "n_violations", "directions",
                                    "signed_start_m", "signed_end_m", "vertex_range", "max_deviation_m", "point_start", "point_end",
                                    "signed_m", "required_m", "start", "initial", "route_end", "slot", "error", "error_type"), DATA),
                   "audit": CHORD_AUDIT, "curve_audit": CURVE_AUDIT, "draw": DRAW, "formations": SEQ(FORMATION_STEP),
                   "route_stats": MAP(DATA), "all_violations": MAP(DATA), "dwell_diagnostics": DWELL_DIAGNOSTICS}
FORBIDDEN = {"seconds", "wall_s", "wall_time", "elapsed_s", "elapsed_seconds", "cpu_s", "timing", "stage_timing",
             "skeleton_detail", "build_seconds", "attempt_wall_s", "attempt_s", "skeleton_s", "optimize_s", "simulation_s",
             "verify_s", "lp_s", "chord_set_s", "chord_exact_s", "corridor_s", "route_s", "candidate_s", "prewarm_s",
             "cache_hits", "cache_misses_computed", "cache_hit", "cache_miss", "pid", "traceback", "tracebacks",
             "path", "filepath", "filename", "directory"}


def assert_no_runtime(value, where="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            name = str(key).lower()
            if name in FORBIDDEN or name.endswith(("_path", "_dir")):
                raise ValueError(f"forbidden contract field at {where}.{key}")
            assert_no_runtime(child, f"{where}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_no_runtime(child, f"{where}[{index}]")
    elif isinstance(value, str):
        if re.search(r"[A-Za-z]:[\\/]|\\\\|(?:^|\s)/(?:[^\s/]+/)+|\.\.?[\\/]|[^\s]+\.(?:json|npy|npz|csv|py|log)(?:$|\s)", value):
            raise ValueError(f"filesystem string at {where}")


def project(value, schema, where):
    if value is None:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if schema is DATA:
        if isinstance(value, (list, tuple)):
            out = [project(child, DATA, f"{where}[{i}]") for i, child in enumerate(value)]
            return tuple(out) if isinstance(value, tuple) else out
        if not isinstance(value, (str, bool, int, float)):
            raise ValueError(f"unexpected non-scalar contract value at {where}")
        assert_no_runtime(value, where)
        return value
    if isinstance(schema, dict):
        if not isinstance(value, dict):
            raise ValueError(f"expected contract object at {where}")
        unknown = set(value) - set(schema)
        if unknown:
            raise ValueError(f"unknown contract field at {where}.{sorted(unknown, key=str)[0]}")
        return {k: project(v, schema[k], f"{where}.{k}") for k, v in value.items()}
    if schema[0] == "map":
        if not isinstance(value, dict):
            raise ValueError(f"expected identifier map at {where}")
        return {k: project(v, schema[1], f"{where}.{k}") for k, v in value.items()}
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"expected contract sequence at {where}")
    out = [project(v, schema[1], f"{where}[{i}]") for i, v in enumerate(value)]
    return tuple(out) if isinstance(value, tuple) else out


def project_plan(plan):
    proposal = project(plan.proposal, PROPOSAL, "plan.proposal")
    witnesses = project(plan.witnesses, WITNESSES, "plan.witnesses")
    failure = plan.failure
    if failure is not None:
        raw_witness = dict(failure.witness or {})
        # Exceptions are diagnostic text, not a reproducible business reason.
        if raw_witness.get("error") is not None:
            T._LAST_TIMING["construction_error"] = raw_witness.pop("error")
            raw_witness["error_type"] = "construction_error"
            failure = replace(failure, reason="close_observation_construction_error")
        if "route_stats" in raw_witness:
            T._LAST_TIMING["route_stats"] = raw_witness.pop("route_stats")
        if "draw" in raw_witness:
            raw_witness["draw"] = draw_summary(proposal, (proposal or {}).get("formation"))
        witness = project(raw_witness, FAILURE_WITNESS, "plan.failure.witness")
        failure = replace(failure, witness=witness)
    out = replace(plan, proposal=proposal, witnesses=witnesses, failure=failure)
    for value in (proposal, witnesses, None if failure is None else failure.witness):
        assert_no_runtime(value)
    return out
