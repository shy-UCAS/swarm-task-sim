"""V8-19 measured events, five nominal phases, acceptance wrappers and strict contract schemas."""
import json
from fractions import Fraction
from pathlib import Path

import numpy as np

from ..motion.intents import close_observation as C

PHASES = ("close_ingress", "warning_before_dwell", "dwell", "warning_after_dwell", "close_egress")


def skeleton_checkpoint(records, *, expected_count=200):
    from .skeleton_monitoring import skeleton_checkpoint as base
    records = list(records)
    out = base(records, expected_count=expected_count)
    out["complete"] = bool(out["complete"] and not any(r.get("exceptions") or r.get("error") for r in records))
    out["metrics"]["excluded_from_rate"] = []
    return out


def full_checkpoint(records, frechet_blocks):
    from .joint_report import full_checkpoint as base
    records = list(records)
    out = base(records, frechet_blocks)
    out["metrics"]["excluded_from_rate"] = []
    out["metrics"]["frechet_pairs"] = sum(len(b["distances_m"]) for b in frechet_blocks)
    if records:
        f = Fraction(sum(bool(r["success"]) for r in records), len(records))
        out["metrics"]["success_rate_fraction"] = f"{f.numerator}/{f.denominator}"
    return out


def measured_members(ctx, tracks, release_us, target_id):
    from task_v07.criteria import load_criteria
    from task_v07.detectors import dwell
    from ..motion.nominal_checks import layer_levels
    from ..scene.exact import signed_distance
    target = ctx.facility_by_id[target_id]
    cfg = load_criteria()
    members = {}
    for mid in sorted(set(tracks) & set(release_us)):
        tr = tracks[mid]
        mask = (np.asarray(tr.tau_us) >= release_us[mid]) & (np.asarray(tr.segment_index) == 0)
        times = np.asarray(tr.tau_us)[mask]
        xy = np.asarray(tr.p, float)[mask, :2]
        sdf = np.asarray(signed_distance(target.geometry, xy), float) if len(xy) else np.zeros(0)
        inside = sdf <= target.offsets["warning"]
        prev = np.r_[False, inside[:-1]] if len(inside) else np.zeros(0, bool)
        starts = np.flatnonzero(inside & ~prev)
        exits = np.flatnonzero(~inside & prev)
        after = exits[exits > starts[0]] if len(starts) else np.zeros(0, int)
        levels = layer_levels(target, xy)[0] if len(xy) else np.zeros(0, int)
        observed = dwell(xy, times, levels == 1, cfg) if len(xy) else {"detected": False}
        detected = bool(observed["detected"])
        end_out = bool(len(xy)) and all(float(signed_distance(f.geometry, xy[-1])) > f.offsets["warning"] for f in ctx.facilities)
        members[mid] = {"frames": int(len(times)), "warning_entry_count": int(len(starts)), "warning_exit_count": int(len(exits)),
            "first_warning_entry_us": int(times[starts[0]]) if len(starts) else None,
            "first_warning_exit_us": int(times[after[0]]) if len(after) else None,
            "observation_detected": detected,
            "observation_first_start_us": int(times[observed["frame_index"]]) if detected else None,
            "observation_first_confirm_us": int(times[observed["confirm_frame_index"]]) if detected else None,
            "started_outside_target_warning": bool(len(inside) and not inside[0]),
            "ended_outside_all_warning": end_out,
            "max_target_layer": int(np.max(levels)) if len(levels) else None,
            "end_target_layer": int(levels[-1]) if len(levels) else None}
    all_single = bool(members) and set(tracks) == set(release_us) == set(members) and all(
        m["frames"] > 0 and m["warning_entry_count"] == 1 and m["warning_exit_count"] == 1
        and m["started_outside_target_warning"] and m["ended_outside_all_warning"] and m["observation_detected"]
        for m in members.values())
    return {"members": members, "all_single": bool(all_single)}


def result_block(plan, maps, measured):
    choice = plan.proposal["dwell"]
    out = {k: choice[k] for k in ("reference_station_m", "set_size", "duration_ticks")}
    out["members"] = {}
    for mid in sorted(plan.members):
        d = plan.witnesses["dwell_diagnostics"]["members"][mid]
        nom = maps[mid]["dwell_reference"]
        m = measured["members"][mid]
        out["members"][mid] = {k: d[k] for k in ("member_station_m", "point_xy", "warning_sdf_m", "alert_sdf_m", "base_min_margin_m")}
        out["members"][mid].update(nominal_arrival_s=float(nom.arrival_s), duration_s=float(nom.dwell_s))
        out["members"][mid].update({k: m[k] for k in ("warning_entry_count", "first_warning_entry_us", "first_warning_exit_us",
            "observation_first_start_us", "observation_first_confirm_us", "ended_outside_all_warning")})
    return C.project(out, RESULT_BLOCK, "close_observation")


def member_phase_times(res, mid):
    nom = res["opt"]["maps"][mid]["dwell_reference"]
    mm = res["plan"].witnesses["member_map_transit"]["members"][mid]
    return (nom.release_s, nom.time_at_s(mm["entry_member_s"]), nom.arrival_s, nom.departure_s,
            nom.time_at_s(mm["exit_member_s"]), nom.end_s)


def phase_durations(res):
    from ..config import load_config
    sim = load_config("sim").values
    out = {}
    for mid in sorted(res["plan"].members):
        times = member_phase_times(res, mid)
        values = np.diff(times)
        out[mid] = {name + "_s": float(v) for name, v in zip(PHASES, values)}
        out[mid].update(travel_s=float(times[-1] - times[0]), release_s=float(times[0]),
                        release_delay_s=float(res["plan"].members[mid].release_delay_s),
                        pre_release_hold_s=float(sim["initial_settle_s"]), terminal_hold_s=float(sim["terminal_hold_s"]),
                        release_quantization_s=float(times[0] - sim["initial_settle_s"] - res["plan"].members[mid].release_delay_s),
                        closure_residual_s=float(sum(values) - (times[-1] - times[0])))
    return out


def phase_diagnostics(res, ctx):
    from task_v07.criteria import load_criteria
    from ..diagnostics.monitoring_skeleton import phase_metrics
    cfg = load_criteria()
    observed = measured_members(ctx, res["tracks"], res["release_us"], res["plan"].witnesses["target_id"])
    out = {}
    for mid in sorted(res["plan"].members):
        nom = res["opt"]["maps"][mid]["dwell_reference"]
        times = member_phase_times(res, mid)
        track = res["tracks"][mid]
        tau = np.asarray(track.tau_us) / 1e6
        mask = (tau >= nom.release_s) & (tau <= nom.end_s)
        t = tau[mask]
        rp, rv, _ = nom.pva(t)
        s_in = np.interp(t - nom.release_s, nom.incoming.t_nodes, nom.curve.s[:len(nom.incoming.t_nodes)])
        s_out = nom.dwell_station_m + np.interp(t - nom.departure_s, nom.outgoing.t_nodes, nom.outgoing.curve.s)
        s_now = np.where(t <= nom.arrival_s, s_in, np.where(t < nom.departure_s, nom.dwell_station_m, s_out))
        delta = np.diff(nom.curve.xy, axis=0)
        tangent = delta / np.hypot(*delta.T)[:, None]
        ids = np.clip(np.searchsorted(nom.curve.s, s_now, side="right") - 1, 0, len(tangent) - 1)
        bounds = {name: (times[i], times[i + 1], i == 4) for i, name in enumerate(PHASES)}
        trj = res["opt"]["solution"].references[mid]
        phases = phase_metrics(t, rp, rv, trj.evaluate(t), trj.evaluate(t, 1),
                               np.asarray(track.p)[mask, :2], np.asarray(track.v)[mask, :2], bounds, tangent[ids])
        measured = observed["members"][mid]
        start, confirm = measured["observation_first_start_us"], measured["observation_first_confirm_us"]
        in_dwell = (tau >= nom.arrival_s) & (tau <= nom.departure_s)
        dwell_times = np.asarray(track.tau_us)[in_dwell]
        dwell_xy = np.asarray(track.p)[in_dwell, :2]
        separation = []
        for other_mid, other in res["tracks"].items():
            if other_mid == mid:
                continue
            visible = (np.asarray(other.tau_us) >= res["release_us"][other_mid]) & (np.asarray(other.segment_index) == 0)
            common, ia, ib = np.intersect1d(dwell_times, np.asarray(other.tau_us)[visible], return_indices=True)
            if len(common):
                delta = dwell_xy[ia] - np.asarray(other.p)[visible, :2][ib]
                separation.append(float(np.hypot(*delta.T).min()))
        out[mid] = {"phases": phases, "nominal_times_s": list(map(float, times)),
            "observation_start_minus_arrival_s": None if start is None else start / 1e6 - nom.arrival_s,
            "observation_confirm_minus_arrival_plus_window_s": None if confirm is None else confirm / 1e6 - (nom.arrival_s + cfg["detectors"]["dwell"]["window_s"]),
            "observation_confirm_minus_departure_s": None if confirm is None else confirm / 1e6 - nom.departure_s,
            "measured_endpoint_distance_m": float(np.hypot(*(np.asarray(track.p)[-1, :2] - np.asarray(nom.dwell_point_xy)))),
            "member_arrival_span_s": res["plan"].witnesses["dwell_diagnostics"]["member_arrival_span_s"],
            "release_offset_s": res["release_us"][mid] / 1e6 - nom.release_s,
            "max_target_layer": measured["max_target_layer"], "end_target_layer": measured["end_target_layer"]}
        out[mid]["measured_min_separation_during_member_dwell_m"] = min(separation) if separation else None
        out[mid]["measured_dwell_point_max_error_m"] = float(np.hypot(*(dwell_xy - nom.dwell_point_xy).T).max()) if len(dwell_xy) else None
    return out


def group_reference_curves(ctx, group, res):
    from .transit_report import FRECHET_SPACING_M, _cut_resample, _exact_crossings
    plan = res["plan"]
    geom = ctx.facility_by_id[plan.witnesses["target_id"]].layers["warning"]
    reference = np.asarray(plan.reference_xy, float)
    stations = float(plan.anchors["collect_s"]) + np.r_[0., np.cumsum(np.hypot(*np.diff(reference, axis=0).T))]
    displacement = np.zeros_like(reference)
    for mid in sorted(plan.members):
        mm = plan.witnesses["member_map_transit"]["members"][mid]
        member_s = np.interp(stations, mm["reference_s"], mm["member_s"])
        nom = res["opt"]["maps"][mid]["dwell_reference"]
        t = nom.time_at_s(member_s)
        displacement += res["opt"]["solution"].references[mid].evaluate(t) - nom.pva(t)[0]
    after = reference + displacement / len(plan.members)
    curves, info = {}, {}
    for name, xy in (("before", reference), ("after", after)):
        crossings, cum = _exact_crossings(xy, geom)
        directions = [direction for _, direction in crossings]
        info[name] = {"crossings": directions, "length_m": float(cum[-1])}
        if directions != ["in", "out"]:
            curves[name] = None
            info[name]["na_reason"] = f"not_single_crossing:{directions}"
            continue
        a, b = crossings[0][0], crossings[1][0]
        curves[name] = _cut_resample(xy, a, b, FRECHET_SPACING_M)
        info[name].update(cut_length_m=float(b - a), n_points=len(curves[name]),
                          start_xy=curves[name][0].tolist(), end_xy=curves[name][-1].tolist())
    return {"before": curves["before"], "after": curves["after"], "info": info}


# Every dictionary entering the new contract tree has a declared child shape.
D, MAP, SEQ = C.DATA, C.MAP, C.SEQ
fields = lambda *names: dict.fromkeys(names, D)
RESULT_MEMBER = fields("member_station_m", "point_xy", "nominal_arrival_s", "duration_s", "warning_sdf_m", "alert_sdf_m",
    "base_min_margin_m", "warning_entry_count", "first_warning_entry_us", "first_warning_exit_us", "observation_first_start_us",
    "observation_first_confirm_us", "ended_outside_all_warning")
RESULT_BLOCK = {**fields("reference_station_m", "set_size", "duration_ticks"), "members": MAP(RESULT_MEMBER)}
MEASURED_MEMBER = fields("frames", "warning_entry_count", "warning_exit_count", "first_warning_entry_us", "first_warning_exit_us",
    "observation_detected", "observation_first_start_us", "observation_first_confirm_us", "started_outside_target_warning",
    "ended_outside_all_warning", "max_target_layer", "end_target_layer")
MEASURED = {"members": MAP(MEASURED_MEMBER), "all_single": D}
COUNTS = fields("frames", "visits", "max_target_layer", "max_other_layer")
DETECTOR_DWELL = fields("detected", "frame_index", "confirm_frame_index", "t_s", "t_confirm", "total_duration_s", "union_frame_intervals")
DETECTOR_REVISIT = fields("detected", "frame_index", "confirm_frame_index", "t1", "t2", "t_confirm", "distance_m",
    "departure_m", "heading_difference_deg", "azimuth_coverage_deg")
SEMANTIC_MEMBER = {"passed": D, "conditions": C.CONDITIONS, "counts": COUNTS, "levels": D,
    "observation_dwell": DETECTOR_DWELL, "revisit": DETECTOR_REVISIT, "revisit_work": DETECTOR_REVISIT}
CROSSING_VIOLATION = fields("facility", "kind", "s_m", "signed_start_m", "signed_end_m", "vertex_range", "max_deviation_m", "point_start", "point_end")
SEMANTIC_FAILURE = {**fields("kind", "member", "count", "directions", "facility", "signed_m", "conditions"), "first": CROSSING_VIOLATION}
PHYSICAL_FAILURE = {**fields("kind", "member", "bound", "residual", "quantity", "value", "cap", "t_abs_s", "constraint", "margin_m",
    "pair", "min_m", "t_s", "min_radius_m", "required_m"), "errors": fields("start_p", "start_v", "start_a", "end_p", "end_v", "end_a")}
DEVIATION = MAP(fields("max_m", "mean_m"))
TRACKING = MAP(fields("max_step_pos_err_m", "max_frame_pos_err_m", "tube_exceeded_0p5", "max_core_accel_xy", "max_core_jerk_xy", "max_10hz_diff_jerk_xy"))
OPT_DIAG = {**fields("nit", "nfev", "message", "success", "value", "max_abs_grad", "settings_sha256"),
    "terms": fields("ref", "smooth", "alm"), "reference_deviation": SEQ(fields("member", "rms_m", "max_m")),
    "symmetry_break": {**fields("applied", "obstacle_points"), "pairs": SEQ(fields("pair", "frames", "normal", "max_gap_m"))}}
OPT_ATTEMPT = {**OPT_DIAG, "physical_failures": SEQ(PHYSICAL_FAILURE), "semantic_failures": SEQ(SEMANTIC_FAILURE),
    "semantic_members": MAP(SEMANTIC_MEMBER), "semantic_boundaries": MAP({"violations": SEQ(CROSSING_VIOLATION), "crossings": D})}
ATTEMPT = {**fields("attempt", "ok", "stage", "code", "reason", "optimization_entered", "skeleton_stage", "shape_audit_failed", "feasible_set", "segment_failures"),
    "witness": C.FAILURE_WITNESS, "draw": C.DRAW, "optimize": OPT_ATTEMPT,
    "validity": fields("passed", "codes", "min_separation_m"), "measured_close_observation_entries": MAP(D)}
FAILURE = {**fields("code", "reason", "feasible_set"), "witness": fields("attempts", "stages", "attempts_done")}
PHASE_METRIC = fields("n_samples", "n_moving", "reference_min_all_samples_m_s", "reference_min_m_s", "ratio_reason", "min_reference_speed_m_s",
    "optimized_min_m_s", "optimized_ratio", "optimized_along_max_m", "optimized_along_worst_t_s",
    "measured_min_m_s", "measured_ratio", "measured_along_max_m", "measured_along_worst_t_s")
PHASE_MEMBER = {**fields("nominal_times_s", "observation_start_minus_arrival_s", "observation_confirm_minus_arrival_plus_window_s",
    "observation_confirm_minus_departure_s", "measured_endpoint_distance_m", "member_arrival_span_s", "release_offset_s", "max_target_layer", "end_target_layer"),
    "phases": dict.fromkeys(PHASES, PHASE_METRIC)}
PHASE_MEMBER.update(fields("measured_min_separation_during_member_dwell_m", "measured_dwell_point_max_error_m"))
PHASE_DURATION = fields(*(name + "_s" for name in PHASES), "travel_s", "release_s", "release_delay_s", "closure_residual_s",
    "pre_release_hold_s", "terminal_hold_s", "release_quantization_s")
FORMATION = {**fields("prior", "start", "realized", "mapped_from_loose", "retreat_chain", "order", "lateral_step_m"), "offsets": MAP(D)}
TOPOLOGY = fields("final", "curved", "fallback_reason")
CONTRACT = fields("contract_id", "intent", "family_id", "order", "draw_index", "branch", "facility_count", "vehicle_count", "group_id",
    "member_ids", "group_size", "target_id", "initial_speed_m_s", "formation_prior")
RESULT = {**fields("intent", "success", "attempts", "release_us", "settings_sha256", "retained_p0_ok", "incomplete",
    "post_optimization_failures", "skeleton_failures", "unknown_attempts", "shape_audit_failed_attempts", "nominal_duration_s"),
    "release_us": MAP(D), "failure": FAILURE, "attempt_log": SEQ(ATTEMPT), "deviation": DEVIATION, "tracking": TRACKING,
    "formation": FORMATION, "topology": TOPOLOGY, "phase_metrics": MAP(PHASE_MEMBER), "phase_durations": MAP(PHASE_DURATION), "close_observation": RESULT_BLOCK}
ARRAY_REF = fields("npz", "shape", "dtype")
MEMBER = {**fields("member_id", "segment_index", "altitude_m", "end_s", "release_delay_s", "speed_breaks", "stops"), "curve_xy": ARRAY_REF}
SKELETON = {"members": MAP(MEMBER), "reference_xy": ARRAY_REF, "arrays": MAP(D), "nominal_duration_s": D, "anchors": fields("collect_s", "terminal_s", "transit_entry_s", "transit_exit_s"),
    "repairs": SEQ(C.REPAIR), "proposal": C.PROPOSAL, "formation": FORMATION, "topology": TOPOLOGY,
    "business_key": fields("family_id", "draw", "purpose", "mission", "branch", "group", "segment", "attempt"),
    "member_nominal_s": MAP(D), "witnesses": C.WITNESSES}
OPT_MEMBER = fields("release_s", "end_s", "altitude_m", "knots", "controls")
OPTIMIZED = {"members": MAP(OPT_MEMBER), "diagnostics": OPT_DIAG}
LINE_BASE = fields("facility", "direction", "s_from_m", "s_to_m", "s_cross_m", "kind", "axis", "s_d_m", "duration_s")
LINE_META = {**LINE_BASE, **fields("merged_intervals", "merged_gaps_s", "max_collinear_residual_m"), "merged_from": SEQ(LINE_BASE)}
FAILURE_WITNESS = {**fields("stage", "reason", "validity_codes", "segment_failures"), "skeleton_members": MAP(D),
    "optimized": MAP(OPT_MEMBER), "physical_failures": SEQ(PHYSICAL_FAILURE), "semantic_failures": SEQ(SEMANTIC_FAILURE),
    "tracks_p": MAP(D), "measured_close_observation": MEASURED}
SKEL_ATTEMPT = {**fields("attempt", "ok", "stage", "code", "reason", "feasible_set", "shape_audit_failed", "curved", "fallback_reason",
    "theta_deg", "h_m", "cells_feasible", "collect_D_m", "K", "lateral_deviation_m"), "draw": C.DRAW,
    "formation_steps": SEQ(C.FORMATION_STEP), "corridor": C.CORRIDOR, "lp": C.LP, "curve_audit": C.CURVE_AUDIT,
    "repairs": SEQ(C.REPAIR), "dwell": C.DWELL, "dwell_diagnostics": C.DWELL_DIAGNOSTICS, "nominal_screen": MAP(C.SCREEN)}
SKEL_RESULT = {**fields("intent", "success", "attempts", "shape_audit_failed_attempts", "exceptions", "curved", "fallback_reason", "lateral_deviation_m", "nominal_duration_s"),
    "failure": FAILURE, "attempt_log": SEQ(SKEL_ATTEMPT), "formation": FORMATION, "topology": TOPOLOGY,
    "dwell": C.DWELL, "dwell_diagnostics": C.DWELL_DIAGNOSTICS, "nominal_screen": MAP(C.SCREEN)}


def project_attempt(value):
    runtime = {k: value[k] for k in ("timing", "traceback") if k in value}
    payload = {k: v for k, v in value.items() if k not in runtime}
    if payload.get("stage") == "exception":
        payload["reason"] = "implementation_error"
    projected = C.project(payload, ATTEMPT, "attempt")
    C.assert_no_runtime(projected)
    return {**projected, **runtime}


def assert_contract_payload(value):
    C.assert_no_runtime(value)
    more_forbidden = {"optimization_s", "prepare_s", "solve_s", "check_s", "dwell_set_s", "dwell_reference_s"}
    def scan(x, where="$"):
        if isinstance(x, dict):
            for k, v in x.items():
                if str(k).lower() in more_forbidden:
                    raise ValueError(f"forbidden contract field at {where}.{k}")
                scan(v, f"{where}.{k}")
        elif isinstance(x, (tuple, list)):
            for i, v in enumerate(x):
                scan(v, f"{where}[{i}]")
    scan(value)
    if "proposal" in value and "members" in value:
        shape = SKELETON
    elif "lines" in value and "members" in value:
        value = dict(value)
        for key in ("lines", "lines_raw"):
            for i, line in enumerate(value.pop(key, None) or []):
                if len(line) != 6:
                    raise ValueError(f"expected six-element semantic line at {key}[{i}]")
                C.project(line[:5], D, f"{key}[{i}]")
                C.project(line[5], LINE_META, f"{key}[{i}].metadata")
        shape = OPTIMIZED
    elif "skeleton_members" in value:
        shape = FAILURE_WITNESS
    elif "exceptions" in value and "success" in value:
        shape = SKEL_RESULT
    elif "success" in value and "attempt_log" in value:
        shape = RESULT
    elif "contract_id" in value and "member_ids" in value:
        shape = CONTRACT
    else:
        raise ValueError("unknown contract document shape at $")
    C.project(value, shape, "$")
    return True


def five_intent_pairs(roots):
    from .transit_report import COMMON_FIELDS
    names = ("monitoring", "transit", "intrusion", "feint", "close_observation")
    tables = {name: {r["contract_id"]: r for r in json.loads((Path(roots[name]) / "records.json").read_text(encoding="utf-8"))} for name in names}
    keys = sorted(set().union(*(set(t) for t in tables.values())))
    rows, differences = [], []
    for cid in keys:
        records = {name: tables[name].get(cid) for name in names}
        present = [r for r in records.values() if r is not None]
        diff = {key: {name: records[name].get(key) if records[name] else None for name in names}
                for key in COMMON_FIELDS if any(r.get(key) != present[0].get(key) for r in present[1:])}
        differences.extend({"contract_id": cid, "field": k, "values": v} for k, v in diff.items())
        rows.append({"contract_id": cid, "common_differences": diff,
                     "intents": {name: None if r is None else {k: r.get(k) for k in ("success", "attempts", "failure", *COMMON_FIELDS)} for name, r in records.items()}})
    return {"rows": rows, "contracts": len(rows), "common_differences": differences,
            "missing_by_intent": {name: [k for k in keys if k not in tables[name]] for name in names},
            "outer_join": True, "excluded": []}


def verify_saved_outputs(root, entries, data_root, cache):
    from ..criteria.segment import SegmentTask, verify_segments
    from ..criteria.validity import check_validity, visible_track
    from ..scene.context import load_context
    from ..scene.exact import signed_distance
    from ..sim.types import MemberTrack
    root = Path(root)
    by = {e["family_id"]: e for e in entries}
    rows = json.loads((root / "records.json").read_text(encoding="utf-8"))
    checked, errors = [], []
    contexts = {}
    for row in rows:
        cid = row["contract_id"]
        folder = root / "contracts" / cid
        for path in folder.rglob("*.json"):
            assert_contract_payload(json.loads(path.read_text(encoding="utf-8")))
        saved = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        if saved["success"] != row["success"]:
            errors.append({"contract_id": cid, "reason": "saved_success_mismatch"})
        if not row["success"]:
            continue
        if row["family_id"] not in contexts:
            contexts.clear()
            contexts[row["family_id"]] = load_context(by[row["family_id"]], data_root=Path(data_root), cache_dir=Path(cache))
        ctx = contexts[row["family_id"]]
        tracks = {}
        for mid in row["member_ids"]:
            arrays = {k: np.load(folder / "tracks" / mid / (k + ".npy"), allow_pickle=False) for k in ("tau_us", "p", "v", "a", "segment_index")}
            tracks[mid] = MemberTrack(mid, arrays["tau_us"], arrays["p"], arrays["v"], arrays["a"], arrays["segment_index"], ())
        verdicts = verify_segments(ctx.scene, tracks, saved["release_us"], [SegmentTask(0, "close_observation", row["target_id"])])
        validity = check_validity(ctx.scene, [visible_track(tracks[m], saved["release_us"][m]) for m in sorted(tracks)])
        measured = measured_members(ctx, tracks, saved["release_us"], row["target_id"])
        optimized = json.loads((folder / "optimized.json").read_text(encoding="utf-8"))
        target = ctx.facility_by_id[row["target_id"]]
        good = all(v.passed for v in verdicts) and validity.passed and measured["all_single"] and saved["retained_p0_ok"]
        for mid in tracks:
            a = tracks[mid]
            good = good and np.issubdtype(a.tau_us.dtype, np.integer) and bool(np.all(np.diff(a.tau_us) == 100_000))
            good = good and bool(np.all(a.segment_index == 0)) and all(np.isfinite(getattr(a, k)).all() for k in ("p", "v", "a"))
            info = saved["close_observation"]["members"][mid]
            ticks = saved["close_observation"]["duration_ticks"]
            pd = np.asarray(info["point_xy"], float)
            good = good and isinstance(ticks, int) and 200 <= ticks <= 1200 and info["duration_s"] == ticks / 10.
            good = good and info["warning_sdf_m"] == float(signed_distance(target.layers["warning"], pd))
            good = good and info["alert_sdf_m"] == float(signed_distance(target.layers["alert"], pd))
            good = good and info["warning_sdf_m"] <= -12.5 and info["alert_sdf_m"] >= 12.5 and info["base_min_margin_m"] >= 0.
            lines = [line for line in optimized["lines"] if line[0] == mid and line[5].get("kind") == "dwell"]
            good = good and len(lines) == 2 and {tuple(line[4]) for line in lines} == {(1., 0.), (0., 1.)}
            trj = optimized["members"][mid]
            controls, knots = np.asarray(trj["controls"], float), np.asarray(trj["knots"], float)
            h = knots[4] - knots[3]
            bound = np.sqrt(np.finfo(float).eps) * max(1., float(np.abs(controls).max()))
            for line in lines:
                good = good and line[1] == info["nominal_arrival_s"] and line[2] == line[1] + info["duration_s"]
                js = np.arange(len(controls))
                select = ((js - 3) * h < line[2] - trj["release_s"]) & ((js + 1) * h > line[1] - trj["release_s"])
                good = good and bool(select.any()) and float(np.abs(controls[select] - pd).max()) <= bound
            for k in ("warning_entry_count", "first_warning_entry_us", "first_warning_exit_us", "observation_first_start_us", "observation_first_confirm_us", "ended_outside_all_warning"):
                good = good and info[k] == measured["members"][mid][k]
            window = verdicts[0].windows[mid]
            d = window.observation_dwell
            good = good and bool(d["detected"])
            if d["detected"]:
                good = good and info["observation_first_start_us"] == int(window.time_us[d["frame_index"]])
                good = good and info["observation_first_confirm_us"] == int(window.time_us[d["confirm_frame_index"]])
        checked.append({"contract_id": cid, "passed": bool(good), "min_separation_m": validity.min_separation_m})
        if not good:
            errors.append({"contract_id": cid, "reason": "retained_disk_reverification_failed"})
    return {"checked_successes": len(checked), "all_checked": len(rows), "results": checked, "p0_violations": errors, "passed": not errors}
