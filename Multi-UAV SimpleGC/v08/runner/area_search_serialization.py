"""V8-20 private task/survey whitelist. Shared V8-19 schemas remain unchanged."""
import copy
import math

from ..motion.intents.close_observation import DATA, MAP, SEQ, project, assert_no_runtime

SURVEY_KEYS = {"geometry","bounds_m","footprint_radius_m","grid_spacing_m","strip_count","strips_per_member","area_m2"}
SECTOR_KEYS = {"type","base_geometry","center_m","inner_offset_m","outer_offset_m","start_angle_rad","angle_span_rad","bounding_radius_m"}
BASE_KEYS = {"Circle": {"type","center_m","radius_m"}, "Polygon": {"type","vertices_m"},
             "BufferedPolygon": {"type","vertices_m","buffer_m"}}


def _finite(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError("finite physical scalar required")
    return value


def _point(value):
    if not isinstance(value,(list,tuple)) or len(value) != 2:
        raise ValueError("xy pair required")
    for v in value:
        _finite(v)


def validate_survey(survey):
    assert_no_runtime(survey,"survey")
    if not isinstance(survey,dict) or set(survey) != SURVEY_KEYS:
        raise ValueError("survey requires its exact seven-key schema")
    sector = survey["geometry"]
    if not isinstance(sector,dict) or set(sector) != SECTOR_KEYS or sector["type"] != "ContourAnnularSector":
        raise ValueError("exact ContourAnnularSector schema required")
    base = sector["base_geometry"]
    if not isinstance(base,dict) or base.get("type") not in BASE_KEYS or set(base) != BASE_KEYS[base["type"]]:
        raise ValueError("unsupported or polluted base geometry")
    if base["type"] == "Circle":
        _point(base["center_m"])
        if _finite(base["radius_m"]) <= 0:
            raise ValueError("positive base radius required")
    else:
        vertices = base["vertices_m"]
        if not isinstance(vertices,(list,tuple)) or len(vertices) < 3:
            raise ValueError("polygon vertices required")
        for p in vertices:
            _point(p)
        if base["type"] == "BufferedPolygon" and _finite(base["buffer_m"]) < 0:
            raise ValueError("nonnegative base buffer required")
    _point(sector["center_m"])
    for k in ("inner_offset_m","outer_offset_m","start_angle_rad","angle_span_rad","bounding_radius_m"):
        _finite(sector[k])
    if not sector["inner_offset_m"] < sector["outer_offset_m"] or not 0 < sector["angle_span_rad"] <= 2*math.pi or sector["bounding_radius_m"] <= 0:
        raise ValueError("invalid sector extent")
    bounds = survey["bounds_m"]
    if not isinstance(bounds,(list,tuple)) or len(bounds) != 4:
        raise ValueError("four survey bounds required")
    for value in bounds:
        _finite(value)
    if not bounds[0] < bounds[2] or not bounds[1] < bounds[3]:
        raise ValueError("positive survey bounds required")
    for k in ("footprint_radius_m","grid_spacing_m","area_m2"):
        if _finite(survey[k]) <= 0:
            raise ValueError("positive survey scale required")
    c,k = survey["strips_per_member"],survey["strip_count"]
    if type(c) is not int or c < 2 or c%2 or type(k) is not int or k < c or k%c:
        raise ValueError("even c and complete member strip blocks required")
    return copy.deepcopy(survey)


def task_record(task):
    """Keep the original five TaskSpec fields and append only a formed private survey."""
    survey = getattr(task,"survey",None)
    if task.intent != "area_search" and survey is not None:
        raise ValueError("survey is private to area_search")
    out = {k:getattr(task,k) for k in ("task_id","intent","target_id","switch_mode","final")}
    if task.intent == "area_search" and survey is not None:
        out["survey"] = validate_survey(survey)
    return out


# Part 4: every new dictionary has an explicit shape; V8-19 tables stay untouched.
from dataclasses import replace
from ..motion.intents import close_observation as _C
from . import close_observation_report as _R

fields=lambda *names:dict.fromkeys(names,DATA)
CONDITION_SCHEMA=fields("started_outside_target_warning","single_warning_visit","max_target_layer_one",
    "other_layers_within_limit","no_dwell_window","azimuth_span_ok","no_revisit_window",
    "ended_outside_all_warning","effective_observation")
FACT_SCHEMA=fields("frames","visits","max_target_layer","max_other_layer","azimuth_span_deg","effective_frame_count",
    "first_effective_frame_index","first_effective_us","first_warning_entry_us","first_warning_exit_us")
COVERAGE_SCHEMA=fields("grid_point_count","covered_grid_point_count","coverage_fraction","required_fraction")
GROUP_CONDITIONS={"shared_coverage":DATA}
SCREEN_SCHEMA={"passed":DATA,"member_conditions":MAP(CONDITION_SCHEMA),"member_facts":MAP(FACT_SCHEMA),
               "group_conditions":GROUP_CONDITIONS,"group_facts":COVERAGE_SCHEMA}
BASE_SCHEMA=fields("type","center_m","radius_m","vertices_m","buffer_m")
SECTOR_SCHEMA={**fields("type","center_m","inner_offset_m","outer_offset_m","start_angle_rad","angle_span_rad","bounding_radius_m"),
               "base_geometry":BASE_SCHEMA}
SURVEY_SCHEMA={**fields("bounds_m","footprint_radius_m","grid_spacing_m","strip_count","strips_per_member","area_m2"),"geometry":SECTOR_SCHEMA}
PROPOSAL_SCHEMA=fields("intent","theta_idx","theta_deg","h_m","origin_xy","u","n","x_c","collect_D_m",
    "chord_query_id","cell_index","cells_feasible","filtered_cells","mu_deg","span_deg","c","K","beta_deg","Q",
    "inner_offset_m","outer_offset_m","sector_count","c_count","member_slot_order")
PROPOSAL_SCHEMA.update(formation_steps=SEQ(_C.FORMATION_STEP),speed_events=fields("times_s","speeds_m_s"))
INDEPENDENT_SCHEMA=fields("vertices_xy","radii_m","primitives","curve_s","collect_s","split_s","scan_start_s","scan_end_s",
    "warning_entry_s","warning_exit_s","terminal_s","block_index","strip_indices","first_outer_omitted","slot_xy","head_kind")
AREA_GEOMETRY={**fields("sector_cells","entry_cells_before","entry_cells_after","inner_gaps_m","outer_gaps_m","strip_lengths_m","base_min_margin_m"),
    "rejected_by_condition":fields("radial_corridor","radial_band","turn_cut_depth","fillet_placement","warning_crossing","base")}
WITNESSES_SCHEMA={**fields("intent","target_id","nominal_duration_s"),"survey":SURVEY_SCHEMA,
    "independent_members":MAP(INDEPENDENT_SCHEMA),"turn_ranges":MAP(DATA),"bone_nominal_screen":SCREEN_SCHEMA,
    "formation_steps":SEQ(_C.FORMATION_STEP),"area_geometry":AREA_GEOMETRY}
DRAW_SCHEMA={**fields("intent","formation","theta_idx","theta_deg","h_m","cell_index","cells_feasible","filtered_cells",
    "collect_D_m","mu_deg","span_deg","c","K","beta_deg","Q")}
FAILURE_PLAN_SCHEMA={**fields("stage","member","constraint","margin_m","chord_index","rays","minimum_m","shallow_members","shape_audit_failed"),
    "formations":SEQ(_C.FORMATION_STEP),"split_depths_m":MAP(DATA)}
SEMANTIC_MEMBER={"conditions":CONDITION_SCHEMA,"counts":FACT_SCHEMA}
NOMINAL_GROUP={"conditions":GROUP_CONDITIONS,"facts":COVERAGE_SCHEMA}
OPT_ATTEMPT={**_R.OPT_ATTEMPT,"semantic_members":MAP(SEMANTIC_MEMBER),"nominal_group":NOMINAL_GROUP,
    "optimized_nominal_screen":SCREEN_SCHEMA}
MEASURED_MEMBER=fields("warning_entry_count","warning_exit_count","first_warning_entry_us","first_warning_exit_us",
    "first_effective_frame_index","first_effective_us","effective_frame_count","azimuth_span_deg","max_target_layer","end_target_layer",
    "ended_outside_all_warning","dwell_margin_m","dwell_window_start_us","dwell_window_confirm_us","dwell_A_m","dwell_B_m")
MEASURED={"passed":DATA,"members":MAP(MEASURED_MEMBER),"screen":SCREEN_SCHEMA,"coverage":COVERAGE_SCHEMA}
ATTEMPT={**{k:v for k,v in _R.ATTEMPT.items() if k!="measured_close_observation_entries"},
    "witness":FAILURE_PLAN_SCHEMA,"draw":DRAW_SCHEMA,"optimize":OPT_ATTEMPT,"measured_area_search":MEASURED}
RESULT_MEMBER={**{k:v for k,v in MEASURED_MEMBER.items() if k not in ("dwell_A_m","dwell_B_m")},
    **fields("block_index","strip_indices","strip_count","slot_xy","split_point_xy")}
RESULT_BLOCK={**fields("beta_deg","Q","mu_deg","span_deg","c","K"),"survey":SURVEY_SCHEMA,
    "members":MAP(RESULT_MEMBER),"coverage":COVERAGE_SCHEMA}
PHASES=("ingress","warning_before_split","scan","before_exit","withdrawal")
PHASE_DURATION=fields(*(p+"_s" for p in PHASES),"travel_s","release_s","release_delay_s","closure_residual_s",
    "pre_release_hold_s","terminal_hold_s","release_quantization_s","pure_scan_s")
PHASE_MEMBER={**fields("nominal_times_s","release_offset_s","max_target_layer","end_target_layer"),"phases":dict.fromkeys(PHASES,_R.PHASE_METRIC)}
CONTRACT={**_R.CONTRACT,"survey":SURVEY_SCHEMA,"survey_attempt":DATA}
RESULT={**{k:v for k,v in _R.RESULT.items() if k!="close_observation"},"area_search":RESULT_BLOCK,
    "survey":SURVEY_SCHEMA,"survey_attempt":DATA,"attempt_log":SEQ(ATTEMPT),"phase_metrics":MAP(PHASE_MEMBER),"phase_durations":MAP(PHASE_DURATION)}
SKELETON={**_R.SKELETON,"proposal":PROPOSAL_SCHEMA,"witnesses":WITNESSES_SCHEMA,"anchors":{}}
OPTIMIZED={**_R.OPTIMIZED,"turns":DATA}
FAILURE_WITNESS={**{k:v for k,v in _R.FAILURE_WITNESS.items() if k!="measured_close_observation"},
    "measured_area_search":MEASURED,"survey":SURVEY_SCHEMA,"survey_attempt":DATA}
SKEL_ATTEMPT={**{k:v for k,v in _R.SKEL_ATTEMPT.items() if k not in ("dwell","dwell_diagnostics","nominal_screen")},
    "draw":DRAW_SCHEMA,"bone_nominal_screen":SCREEN_SCHEMA,"split_depths_m":MAP(DATA),"split_depth_rejected":DATA,
    "witness":FAILURE_PLAN_SCHEMA}
SKEL_RESULT={**{k:v for k,v in _R.SKEL_RESULT.items() if k not in ("dwell","dwell_diagnostics","nominal_screen")},
    "attempt_log":SEQ(SKEL_ATTEMPT),"survey":SURVEY_SCHEMA,"survey_attempt":DATA,"bone_nominal_screen":SCREEN_SCHEMA,
    "area_search":RESULT_BLOCK}


def project_area_plan(plan):
    from .monitoring import jsonable
    proposal=project(jsonable(plan.proposal),PROPOSAL_SCHEMA,"plan.proposal")
    witnesses=project(jsonable(plan.witnesses),WITNESSES_SCHEMA,"plan.witnesses")
    if witnesses is not None and witnesses.get("survey") is not None:
        validate_survey(witnesses["survey"])
    failure=plan.failure
    if failure is not None:
        failure=replace(failure,witness=project(jsonable(failure.witness),FAILURE_PLAN_SCHEMA,"plan.failure.witness"))
    if witnesses is not None:
        validate_turn_ranges(witnesses.get("turn_ranges",{}))
    for value in (proposal,witnesses,None if failure is None else failure.witness):
        assert_no_runtime(value)
    return replace(plan,proposal=proposal,witnesses=witnesses,failure=failure)


def project_attempt(value):
    runtime={k:value[k] for k in ("timing","traceback") if k in value}
    payload={k:v for k,v in value.items() if k not in runtime}
    if payload.get("stage")=="exception":
        payload["reason"]="implementation_error"
    result=project(payload,ATTEMPT,"attempt")
    assert_no_runtime(result)
    return {**result,**runtime}


def assert_contract_payload(value):
    assert_no_runtime(value)
    extra={"optimization_s","prepare_s","solve_s","check_s","sector_set_s","coverage_s","reference_solve_s","selected_inner_scan_s"}
    def visit(x):
        if isinstance(x,dict):
            if extra.intersection(x):
                raise ValueError("runtime field in area-search contract")
            for key,child in x.items():
                if key=="survey" and child is not None:
                    validate_survey(child)
                visit(child)
        elif isinstance(x,(list,tuple)):
            for child in x:
                visit(child)
    visit(value)
    if "proposal" in value and "members" in value:
        shape=SKELETON
    elif "lines" in value and "members" in value:
        validate_optimizer_turns(value.get("turns"))
        value=dict(value)
        for key in ("lines","lines_raw"):
            for i,line in enumerate(value.pop(key,None) or []):
                if len(line)!=6:
                    raise ValueError("semantic line must have six elements")
                project(line[:5],DATA,f"{key}[{i}]")
                project(line[5],_R.LINE_META,f"{key}[{i}].metadata")
        shape=OPTIMIZED
    elif "skeleton_members" in value:
        shape=FAILURE_WITNESS
    elif "exceptions" in value and "success" in value:
        shape=SKEL_RESULT
    elif "success" in value and "attempt_log" in value:
        shape=RESULT
    elif "contract_id" in value and "member_ids" in value:
        shape=CONTRACT
        if value.get("intent")!="area_search" or not {"survey","survey_attempt"}<=set(value):
            raise ValueError("explicit area-search contract and survey ownership required")
        if (value["survey"] is None)!=(value["survey_attempt"] is None):
            raise ValueError("survey and survey_attempt must both be null or both formed")
        if value["survey_attempt"] is not None and (type(value["survey_attempt"]) is not int or not 0<=value["survey_attempt"]<20):
            raise ValueError("survey_attempt outside the frozen budget")
    else:
        raise ValueError("unknown area-search contract document shape")
    project(value,shape,"$")
    return True


def validate_turn_ranges(ranges):
    if not isinstance(ranges,dict):
        raise ValueError("member turn-range map required")
    for member,items in ranges.items():
        for row in items:
            if len(row)!=4 or not isinstance(row[0],str) or row[3]!="turn_u_min_m":
                raise ValueError("U range must use the frozen four-element protocol")
            if not 0.<=_finite(row[1])<_finite(row[2]):
                raise ValueError("invalid geometric U range")


def validate_optimizer_turns(turns):
    if not isinstance(turns,(list,tuple)):
        raise ValueError("saved optimizer U constraints required")
    for row in turns:
        if len(row)!=4 or not isinstance(row[0],str) or not _finite(row[1])<_finite(row[2]) or not _finite(row[3])>0.:
            raise ValueError("optimizer U constraint must be (member,t0,t1,radius)")


def area_plan_from_record(record):
    from ..contract.monitoring import MemberPlan,SegmentPlan
    members={}
    for mid,data in record["members"].items():
        values=dict(data)
        values["curve_xy"]=tuple(map(tuple,record["arrays"][values["curve_xy"]["npz"]]))
        values["speed_breaks"]=tuple(map(tuple,values["speed_breaks"]))
        values["stops"]=tuple(values["stops"])
        members[mid]=MemberPlan(**values)
    return SegmentPlan(members=members,reference_xy=tuple(map(tuple,record["arrays"][record["reference_xy"]["npz"]])),
        nominal_duration_s=record["nominal_duration_s"],anchors=record["anchors"],repairs=tuple(record["repairs"]),
        proposal=record["proposal"],formation=record["formation"],topology=record["topology"],business_key=record["business_key"],
        member_nominal_s=record["member_nominal_s"],witnesses=record["witnesses"])


def _map_identifiers(value,schema):
    import re
    if value is None or schema is DATA:
        return
    if isinstance(schema,dict):
        if isinstance(value,dict):
            for key,child in value.items():
                if key in schema:_map_identifiers(child,schema[key])
        return
    if schema[0]=="map":
        if isinstance(value,dict):
            for key,child in value.items():
                if not isinstance(key,str) or re.fullmatch(r"[A-Za-z0-9_:.@-]+",key) is None:
                    raise ValueError("MAP keys must be member or constraint identifiers")
                _map_identifiers(child,schema[1])
    elif isinstance(value,(list,tuple)):
        for child in value:_map_identifiers(child,schema[1])


def project(value,schema,where):
    _map_identifiers(value,schema)
    return _C.project(value,schema,where)
