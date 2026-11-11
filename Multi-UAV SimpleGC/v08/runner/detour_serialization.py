"""V8-21 迂回合同的逐层字段白名单（指令 4.5；裁定 1、3、4 的字段变更）。

只读复用 V19 的 DATA/MAP/SEQ/project/assert_no_runtime 与 V19 报告中的公共表（复制到新常量，不改旧常量）。所有新字段
只经 detour 分支；未知字段抛 ValueError（不静默过滤）。primitive 是定长分支 line/arc/spline_arc，逐元素校验。
"""
import math

from ..motion.intents.close_observation import DATA, MAP, SEQ, assert_no_runtime, project
from . import close_observation_report as _R

D = DATA
fields = lambda *names: dict.fromkeys(names, D)      # noqa: E731

from ..motion.detour_checks import GROUP_CONDITIONS, MEMBER_CONDITIONS   # noqa: E402

PHASES = ("ingress", "near_band", "withdrawal")
CANDIDATE = fields("near_band_width_m", "min_sweep_deg", "max_sweep_deg_exclusive", "sweep_measure", "criteria_sha256",
                   "generation_sha256")
DRAW = {**fields("attempt", "sigma", "sigma_deg", "start_phi_rad", "K", "logit_quantiles", "beta_in_deg", "beta_out_deg",
                 "fillet_radius_m", "sigma_hi_deg", "entry_exit_contribution_deg", "entry_extra_m", "exit_extra_m",
                 "component_id", "row_ids", "member_slot_order"), "lane_sweep_deg": MAP(D)}
FORMATION_STEP = fields("formation", "lateral_step_m", "feasible", "max_arc_deg")
DETOUR_FORMATION = {**fields("prior", "start", "realized", "mapped_from_loose", "retreated", "lateral_step_m", "spacing_m",
                             "order"), "offsets": MAP(D), "steps": SEQ(FORMATION_STEP)}
RUN = fields("start_index", "stop_index", "entry_us", "exit_us", "span_deg", "net_deg")
MEMBER = {**fields("near_entry_count", "near_exit_count", "first_near_entry_us", "last_near_exit_us", "starts_in_band",
                   "ends_in_band", "max_span_deg", "best_net_deg", "min_target_warning_distance_m", "max_target_layer",
                   "max_other_layer"), "all_runs": SEQ(RUN), "terminal_warning_distances_m": MAP(D)}
DETOUR = {"candidate": CANDIDATE, "draw": DRAW, "formation": DETOUR_FORMATION, "members": MAP(MEMBER),
          "other_facility_sweep_deg": MAP(D)}
CONDITIONS = fields(*MEMBER_CONDITIONS)
MEMBER_FACTS = {**MEMBER, **fields("frames", "dwell_detected", "revisit_detected"), "first_layers": MAP(D),
                "last_layers": MAP(D)}
GROUP_CONDITION = fields(*GROUP_CONDITIONS)
GROUP_FACTS = {"other_facility_sweep_deg": MAP(D)}
SCREEN = {"passed": D, "member_conditions": MAP(CONDITIONS), "member_facts": MAP(MEMBER_FACTS),
          "group_conditions": GROUP_CONDITION, "group_facts": GROUP_FACTS, "failures": D}
CANDIDATE_VERDICT = {**SCREEN, "criteria_sha256": D}
BAND = fields("center_xy", "r_star_m", "q_m", "eta_m", "half_span_m", "component_id", "row_ids", "raw_lo_m", "raw_hi_m",
              "tube_lo_m", "tube_hi_m", "A_m", "B_m", "threshold_m")
EXACT_CURVATURE = fields("ok", "kappa_max_abs", "at_phi", "samples", "turn_violations", "lane_violations", "min_radius_m")
LP = {**fields("controls", "kappa_max", "status", "objective", "rho0_m", "coefficients_m"),
      "max_residual": fields("corridor_m", "curvature_per_m"), "exact_curvature": EXACT_CURVATURE}
END = fields("point_xy", "tangent_xy", "line_direction_xy", "fillet_center_xy", "fillet_start_xy", "fillet_end_xy",
             "turn_angle_rad", "straight_m", "primitives")
END_GEOMETRY = {"entry": END, "exit": END}
PROPOSAL = {"candidate": CANDIDATE, "draw": DRAW, "band": BAND, "lp": LP, "end_geometry": END_GEOMETRY}
MEMBER_MAP = fields("reference_s", "member_s", "collect_s", "arc_start_s", "arc_end_s", "near_entry_s", "near_exit_s",
                    "terminal_s")
WITNESSES = {**fields("intent", "target_id", "near_key", "nominal_duration_s"), "candidate": CANDIDATE, "band": BAND,
             "draw": DRAW, "end_geometry": END_GEOMETRY, "formation_steps": SEQ(FORMATION_STEP),
             "member_map_detour": MAP(MEMBER_MAP), "turn_ranges": MAP(D), "bone_nominal_screen": SCREEN}
FORMATION = {**fields("prior", "start", "realized", "mapped_from_loose", "retreat_chain", "order", "lateral_step_m"),
             "offsets": MAP(D)}
TOPOLOGY = fields("final")
ARRAY_REF = fields("npz", "shape", "dtype")
PLAN_MEMBER = {**fields("member_id", "segment_index", "altitude_m", "end_s", "release_delay_s", "speed_breaks", "stops"),
               "curve_xy": ARRAY_REF}
REPAIR = fields("kind", "from", "to", "forced_by", "from_m", "to_m")
SKELETON = {"members": MAP(PLAN_MEMBER), "reference_xy": ARRAY_REF, "arrays": MAP(D), "nominal_duration_s": D,
            "anchors": fields("collect_s", "arc_start_s", "arc_end_s", "terminal_s"), "repairs": SEQ(REPAIR),
            "proposal": PROPOSAL, "formation": FORMATION, "topology": TOPOLOGY,
            "business_key": fields("family_id", "draw", "purpose", "mission", "branch", "group", "segment", "attempt"),
            "member_nominal_s": MAP(D), "witnesses": WITNESSES}
INTERVAL = fields("lane_m", "near_in", "outer_band", "inner_band")
PLAN_WITNESS = {**fields("stage", "subreason", "shape_audit_failed", "need_span_deg", "member", "constraint", "margin_m",
                         "chord_index", "lp_status", "near_directions", "target_directions", "facility"),
                "formation_steps": SEQ(FORMATION_STEP), "draw": DRAW, "band": BAND, "lp": LP,
                "end_geometry": END_GEOMETRY, "exact_curvature": EXACT_CURVATURE, "intervals": SEQ(INTERVAL),
                "violation": fields("facility", "kind", "s_m"), "lane_sweep": MAP(D)}
OPT_DIAG = {**fields("nit", "nfev", "success", "value", "max_abs_grad", "settings_sha256"),
            "terms": fields("ref", "smooth", "alm"), "reference_deviation": SEQ(fields("member", "rms_m", "max_m")),
            "symmetry_break": {**fields("applied", "obstacle_points"),
                               "pairs": SEQ(fields("pair", "frames", "normal", "max_gap_m"))}}
CROSSING_VIOLATION = _R.CROSSING_VIOLATION
SEMANTIC_FAILURE = {**fields("kind", "member", "count", "directions", "facility", "signed_m", "conditions"),
                    "first": CROSSING_VIOLATION}
PHYSICAL_FAILURE = {**fields("kind", "member", "bound", "residual", "quantity", "value", "cap", "t_abs_s", "constraint",
                             "margin_m", "pair", "min_m", "t_s", "min_radius_m", "required_m"),
                    "errors": fields("start_p", "start_v", "start_a", "end_p", "end_v", "end_a")}
SEMANTIC_MEMBER = {"conditions": CONDITIONS, "counts": MEMBER_FACTS}
OPT_ATTEMPT = {**OPT_DIAG, "physical_failures": SEQ(PHYSICAL_FAILURE), "semantic_failures": SEQ(SEMANTIC_FAILURE),
               "semantic_members": MAP(SEMANTIC_MEMBER),
               "semantic_boundaries": MAP({"violations": SEQ(CROSSING_VIOLATION), "crossings": D}),
               "nominal_group": {"conditions": GROUP_CONDITION, "facts": GROUP_FACTS}}
MEASURED_DETOUR = {"members": MAP(fields("near_entry_count", "first_near_entry_us")), "all_single": D}
ATTEMPT = {**fields("attempt", "ok", "stage", "code", "reason", "optimization_entered", "skeleton_stage",
                    "shape_audit_failed", "feasible_set"),
           "witness": PLAN_WITNESS, "draw": DRAW, "optimize": OPT_ATTEMPT,
           "validity": fields("passed", "codes", "min_separation_m"), "candidate_verdict": CANDIDATE_VERDICT,
           "measured_detour": MEASURED_DETOUR}
FAILURE = {**fields("code", "reason", "feasible_set"), "witness": fields("attempts", "stages", "attempts_done")}
PHASE_METRIC = _R.PHASE_METRIC
PHASE_MEMBER = {**fields("nominal_times_s", "release_offset_s", "max_target_layer", "near_entry_us", "near_exit_us"),
                "phases": dict.fromkeys(PHASES, PHASE_METRIC)}
PHASE_DURATION = fields(*(p + "_s" for p in PHASES), "near_band_line_s", "near_band_fillet_s", "near_band_arc_s",
                        "travel_s", "release_s", "release_delay_s", "closure_residual_s", "pre_release_hold_s",
                        "terminal_hold_s", "release_quantization_s")
DEVIATION = MAP(fields("max_m", "mean_m"))
TRACKING = _R.TRACKING
CONTRACT = fields("contract_id", "intent", "family_id", "order", "draw_index", "branch", "facility_count",
                  "vehicle_count", "group_id", "member_ids", "group_size", "target_id", "initial_speed_m_s",
                  "formation_prior")
RESULT = {**fields("intent", "success", "attempts", "settings_sha256", "retained_p0_ok", "incomplete",
                   "post_optimization_failures", "skeleton_failures", "unknown_attempts", "shape_audit_failed_attempts",
                   "nominal_duration_s", "verdict_source"),
          "release_us": MAP(D), "failure": FAILURE, "attempt_log": SEQ(ATTEMPT), "deviation": DEVIATION,
          "tracking": TRACKING, "formation": FORMATION, "topology": TOPOLOGY, "phase_metrics": MAP(PHASE_MEMBER),
          "phase_durations": MAP(PHASE_DURATION), "candidate_verdict": CANDIDATE_VERDICT, "detour": DETOUR}
OPT_MEMBER = fields("release_s", "end_s", "altitude_m", "knots", "controls")
OPTIMIZED = {"members": MAP(OPT_MEMBER), "diagnostics": OPT_DIAG, "optimized_nominal_screen": SCREEN}
LINE_META = _R.LINE_META
FAILURE_WITNESS = {**fields("stage", "reason", "attempt", "member", "constraint", "margin_m", "chord_index", "lp_status"),
                   "draw": DRAW, "intervals": SEQ(INTERVAL), "exact_curvature": EXACT_CURVATURE,
                   "physical_failures": SEQ(PHYSICAL_FAILURE), "semantic_failures": SEQ(SEMANTIC_FAILURE),
                   "candidate_failures": D, "measured_detour": MEASURED_DETOUR}
SKEL_ATTEMPT = {**fields("attempt", "ok", "stage", "code", "reason", "feasible_set", "shape_audit_failed", "subreason"),
                "draw": DRAW, "formation_steps": SEQ(FORMATION_STEP), "witness": PLAN_WITNESS,
                "bone_nominal_screen": SCREEN}
SKEL_RESULT = {**fields("intent", "success", "attempts", "shape_audit_failed_attempts", "exceptions", "nominal_duration_s",
                        "verdict_source"),
               "failure": FAILURE, "attempt_log": SEQ(SKEL_ATTEMPT), "formation": FORMATION, "topology": TOPOLOGY,
               "detour_formation": DETOUR_FORMATION, "bone_nominal_screen": SCREEN}

DOCUMENTS = {"contract": CONTRACT, "result": RESULT, "skeleton": SKELETON, "optimized": OPTIMIZED,
             "failure_witness": FAILURE_WITNESS, "skeleton_result": SKEL_RESULT}
MORE_FORBIDDEN = {"optimization_s", "prepare_s", "solve_s", "check_s", "wall_s", "seconds", "cache_hit", "cache_miss",
                  "message", "lp_message", "survey", "verify_segments_passed"}
PRIM_LEN = {"line": 3, "arc": 5, "spline_arc": 6}


def _finite_or_none(x, where):
    if x is None:
        return
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError(f"finite number required at {where}")


def _check_primitive(p, where):
    if not isinstance(p, (list, tuple)) or not p or p[0] not in PRIM_LEN or len(p) != PRIM_LEN[p[0]]:
        raise ValueError(f"fixed-shape primitive required at {where}")
    pts = {"line": (1, 2), "arc": (1,), "spline_arc": (1,)}[p[0]]
    for i in range(1, len(p)):
        if i in pts:
            if not isinstance(p[i], (list, tuple)) or len(p[i]) != 2:
                raise ValueError(f"xy pair required at {where}[{i}]")
            for v in p[i]:
                _finite_or_none(v, f"{where}[{i}]")
        elif p[0] == "spline_arc" and i == 3:
            for v in p[i]:
                _finite_or_none(v, f"{where}[{i}]")
        else:
            _finite_or_none(p[i], f"{where}[{i}]")


def _scan_forbidden(x, where="$"):
    if isinstance(x, dict):
        for k, v in x.items():
            if str(k).lower() in MORE_FORBIDDEN:
                raise ValueError(f"forbidden contract field at {where}.{k}")
            _scan_forbidden(v, f"{where}.{k}")
    elif isinstance(x, (list, tuple)):
        for i, v in enumerate(x):
            _scan_forbidden(v, f"{where}[{i}]")
    elif isinstance(x, float) and not math.isfinite(x):
        raise ValueError(f"non-finite float at {where}")


def _check_end_geometry(eg, where):
    if eg is None:
        return
    for side in ("entry", "exit"):
        e = eg.get(side) if isinstance(eg, dict) else None
        if e is None:
            continue
        for i, p in enumerate(e.get("primitives") or []):
            _check_primitive(p, f"{where}.{side}.primitives[{i}]")


def project_document(value, document):
    """严格投影并扫描运行时信息；返回投影后的值（未知字段在此抛错）。"""
    if document not in DOCUMENTS:
        raise ValueError(f"unknown detour document {document!r}")
    assert_no_runtime(value)
    _scan_forbidden(value)
    if document == "optimized":
        value = dict(value)
        lines = {k: value.pop(k, None) for k in ("lines", "lines_raw")}
        out = project(value, OPTIMIZED, "optimized")
        for key, seq in lines.items():
            for i, line in enumerate(seq or []):
                if len(line) != 6:
                    raise ValueError(f"expected six-element semantic line at {key}[{i}]")
                project(list(line[:5]), D, f"{key}[{i}]")
                project(line[5], LINE_META, f"{key}[{i}].metadata")
            out[key] = seq
        return out
    out = project(value, DOCUMENTS[document], document)
    if document == "skeleton":
        _check_end_geometry((out.get("proposal") or {}).get("end_geometry"), "skeleton.proposal.end_geometry")
        _check_end_geometry((out.get("witnesses") or {}).get("end_geometry"), "skeleton.witnesses.end_geometry")
    if document in ("result", "skeleton_result"):
        for i, a in enumerate(out.get("attempt_log") or []):
            _check_end_geometry((a.get("witness") or {}).get("end_geometry"), f"attempt_log[{i}].witness.end_geometry")
    return out


def assert_contract_payload(value, *, document=None):
    """预置测试接口：按文档类型严格校验；未给类型时按顶层字段推断。"""
    if document is None:
        if "contract_id" in value:
            document = "contract"
        elif "proposal" in value and "members" in value:
            document = "skeleton"
        elif "diagnostics" in value and "members" in value:
            document = "optimized"
        elif "exceptions" in value:
            document = "skeleton_result"
        elif "attempt_log" in value:
            document = "result"
        else:
            document = "failure_witness"
    project_document(value, document)
    return True
