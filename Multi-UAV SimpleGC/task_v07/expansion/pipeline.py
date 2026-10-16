"""S2 expansion execution steps around the unchanged vertical-slice functions.

descriptor -> RolePlanner -> pre-execution checks -> single-agent timing ->
departure delays -> paired fastsim runs -> labels. Execution, timing, budgets,
labels and export are the vertical-slice functions; core events are detected
only inside task_v07.labels.measure, for single flights and paired runs alike.
"""
from copy import deepcopy
from itertools import combinations
import re

import numpy as np

from task_v07.execution import execute, departure_delays, completion_budget
from task_v07.labels import measure
from task_v07.planning import seed_for
from task_v07.unified.config import stop_fields, load_generator
from .contracts import P0ContractError, validate_route_bundle, validate_family_conditions
from .geometry_checks import check_polyline, check_retreat_point, planning_layer_interval_check
from .role_planners import PlanningInfeasible

PIPELINE_VERSION = "traj2language.s2x_pipeline/0.7.1"
# Identical to the vertical-slice build_skeleton constants.
COMMON_CONSTANTS = {"waypoint_min_spacing_m": 1.0, "tracking_allowance_m": 5.0, "obstacle_clearance_m": 30.0,
                    "initial_settle_s": 20.0, "terminal_hold_s": 2.0, "terminal_radius_m": 1.0,
                    "terminal_speed_m_s": 0.15, "sync_window_s": 10.0, "batch_split_gap_s": 20.0,
                    "timing_jitter_halfwidth_s": 3.0, "sequential_gap_range_s": [40.0, 90.0],
                    "intrusion_endpoint_min_spacing_m": 15.0}


def exclusion_policy(scene, role, target_id, members):
    """Per-ID forbidden facility layer (that layer and every inner layer)."""
    policy = {}
    for f in sorted(e["id"] for e in scene["entities"] if e["type"] == "facility"):
        if f != target_id:
            policy[f] = "alert"           # never another facility's alert/protected zone
        elif role == "intrusion":
            continue                      # target protected zone is the task
        elif role == "feint":
            policy[f] = "protected"       # alert entry allowed, protected never
        else:
            policy[f] = "alert"           # transit/reconnaissance/monitoring
    return {a: dict(policy) for a in sorted(members)}


def forbidden_zone_ids(scene, layers):
    return [e["id"] for e in scene["entities"] if e.get("facility_id") in layers
            and e.get("layer") == layers[e["facility_id"]]]


def role_parameters(descriptor, group):
    match=re.search(r"_ext_(\d+)",descriptor["skeleton_id"])
    slot=descriptor.get("geometry_slot",int(match.group(1)) if match else 0)
    return {"geometry_slot":slot, "column_seed":descriptor["column_seed"],
            "retreat_warning_minimum_m":load_generator()["retreat"]["warning_clearance_m"],
            "candidate_budget":200,
            "collection_range_m":(50.,250.), "target_warning_only":True,
            "planning_interval_warning_m":10.,
            "common_slot":descriptor["common_draw"].get("slot"),
            "geometry_seed":seed_for(descriptor["role_seed"],f"continuous-geometry:{group['group_id']}"),
            "approach_clearance_m":__import__('random').Random(seed_for(descriptor["role_seed"],"approach-clearance")).uniform(35.,70.),
            "family": descriptor["family_conditions"], "cruise_speed_m_s": descriptor["cruise_speed_m_s"],
            "task_altitude_m": descriptor["task_altitude_m"],
            "approach_mode": descriptor["common_draw"]["approach_mode"],
            "planning_seed": seed_for(descriptor["role_seed"], f"route:{group['group_id']}")}


def assemble_skeleton(descriptor, group, bundle, template, legacy):
    """Descriptor-owned fields win; a planner may not change them (P0)."""
    family = descriptor["family_conditions"]
    owned = {"skeleton_id": descriptor["skeleton_id"], "family_id": descriptor["family_id"],
             "map_id": descriptor["map_id"], "base_intent": descriptor["base_intent"],
             "target_id": group["target_id"], "group_id": group["group_id"], "members": sorted(group["members"]),
             "role": group["role"], "agent_ids": list(descriptor["agent_ids"]),
             "column_seed": descriptor["column_seed"], "cruise_speed_m_s": descriptor["cruise_speed_m_s"],
             "initial_states": deepcopy(family["initial_states"])}
    skeleton = deepcopy(template)
    if legacy:
        for key, value in owned.items():
            if skeleton.get(key) != value:
                raise P0ContractError(f"Vertical-slice template disagrees with request field {key}")
    else:
        skeleton = {"schema_version": "traj2language.skeleton/0.7-s2x.1", **owned, **COMMON_CONSTANTS,
                    "execution_method": group["execution_method"],
                    "approach_mode": descriptor["common_draw"]["approach_mode"],
                    "task_altitude_m": descriptor["task_altitude_m"],
                    "pipeline_version": PIPELINE_VERSION, **skeleton}
        for key, value in owned.items():
            if skeleton[key] != value:
                raise P0ContractError(f"Planner template changed request field {key}")
        skeleton["exclusion_policy"] = None  # filled by caller with the explicit policy
        skeleton.update(stop_fields())
    if set(skeleton["references"]) != set(group["members"]):
        raise P0ContractError("Template references do not cover exactly the group")
    for a in group["members"]:
        skeleton["references"][a]["points_enu_m"] = deepcopy(bundle.waypoints_by_agent[a])
    return skeleton


def precheck(scene, skeleton, bundle, policy):
    """Planning-layer checks before any flight; returns a report, never repairs routes.

    The 35 m polyline clearance is enforced only against hard_constraint_obstacle
    entities (independent limit regions, etc.).  Protection zones are semantic
    regions whose labeling criteria are checked at label time; requiring 35 m
    clearance from them here would make roles that intentionally enter those zones
    (close_observation, monitoring, feint, intrusion) always reject.
    """
    members = skeleton["members"]
    report = {"route_bundle": "PASS", "polylines": {}, "retreat_points": {}, "endpoint_spacing": None,
              "policy": policy}
    validate_route_bundle(bundle, members)
    for a in members:
        report["polylines"][a] = check_polyline(scene, bundle.waypoints_by_agent[a],
                                                forbidden_regions=[],   # protection zones checked at label time
                                                margin_m=35.0)
    if skeleton["role"] != "intrusion":
        for a in members:
            report["retreat_points"][a] = check_retreat_point(scene, skeleton["references"][a]["endpoint_enu_m"][:2],
                warning_clearance_m=skeleton.get("retreat_warning_minimum_m", 200.))
    else:
        ends = [np.array(skeleton["references"][a]["endpoint_enu_m"]) for a in members]
        spacing = min(float(np.linalg.norm(x - y)) for x, y in combinations(ends, 2))
        report["endpoint_spacing"] = {"minimum_m": spacing,
                                      "required_m": skeleton["intrusion_endpoint_min_spacing_m"],
                                      "valid": spacing >= skeleton["intrusion_endpoint_min_spacing_m"]}
    failures = [f"polyline:{a}:{issue['code']}" for a, r in report["polylines"].items() for issue in r["issues"]]
    failures += [f"retreat:{a}" for a, r in report["retreat_points"].items() if not r["valid"]]
    if report["endpoint_spacing"] is not None and not report["endpoint_spacing"]["valid"]:
        failures.append("intrusion_endpoint_spacing")
    if "exclusion_policy" in skeleton:
        report["semantic_polylines"]={}
        for a in members:
            semantic=check_polyline(scene,bundle.waypoints_by_agent[a],
                forbidden_regions=forbidden_zone_ids(scene,policy[a]),margin_m=0.)
            report["semantic_polylines"][a]=semantic
            failures += [f"semantic_polyline:{a}:{issue['code']}" for issue in semantic["issues"]]
    report["failures"] = failures
    report["status"] = "PASS" if not failures else "REJECT"
    return report


def plan_group(scene, descriptor, group, planner):
    if descriptor.get("diagnostic_only") is True:
        source=descriptor["diagnostic_source_descriptor"]
        validate_family_conditions(source,descriptor["family_conditions"])
        primary=next(g for g in source["task_groups"] if source["main_unit_id"] in g["source_units"])
        if (primary["role"]!="intrusion" or descriptor["task_groups"]!=[primary]
            or descriptor["agent_ids"]!=[a for a in source["agent_ids"] if a in primary["members"]]
            or descriptor["source_skeleton_id"]!=source["skeleton_id"]
            or descriptor["skeleton_id"]!=source["skeleton_id"]+"_diag_main_intrusion"
            or any(descriptor[k]!=source[k] for k in ("family_id","map_id","cruise_speed_m_s","task_altitude_m","common_draw","column_seed","family_conditions"))):
            raise P0ContractError("Diagnostic changed source group/family/column conditions")
    else:
        validate_family_conditions(descriptor, descriptor["family_conditions"])
    params = role_parameters(descriptor, group)
    try:
        bundle, template = planner.plan_with_template(scene, group, params)
    except PlanningInfeasible:
        raise
    except ValueError as exc:
        raise PlanningInfeasible("geometry_infeasible", str(exc)) from exc
    legacy = getattr(planner, "legacy_vertical_slice", False)
    skeleton = assemble_skeleton(descriptor, group, bundle, template, legacy)
    policy = exclusion_policy(scene, group["role"], group["target_id"], group["members"])
    if not legacy:
        skeleton["exclusion_policy"] = policy
    for key in ("cruise_speed_m_s",):
        if skeleton[key] != descriptor["family_conditions"][key]:
            raise P0ContractError("Planner changed the family speed")
    altitudes = {round(p[2], 9) for r in bundle.waypoints_by_agent.values() for p in r}
    if altitudes != {round(descriptor["task_altitude_m"], 9)}:
        raise P0ContractError("Planner changed the family task altitude")
    if descriptor.get("diagnostic_only") is True:
        skeleton.update(diagnostic_only=True,source_skeleton_id=descriptor["source_skeleton_id"],
                        diagnostic_scope="source main task group only")
    report = precheck(scene, skeleton, bundle, policy)
    return skeleton, bundle, report


def single_agent_timing(scene, skeleton):
    """Each member flies alone; its core event is read by labels.measure on 10 Hz truth."""
    measured, finished, runs = {}, {}, {}
    for a in skeleton["members"]:
        run = execute(skeleton, {m: 0 for m in skeleton["members"]}, only_agent=a)
        raw, _ = measure(scene, skeleton, run, "unassigned_measurement")
        measured[a] = raw["agents"][a]["observed"]["core_event"]["t_s"]
        finished[a] = float(run["time_us"][-1] / 1e6) if run["execution_status"] == "completed" else None
        runs[a] = run
        if str(skeleton.get("planning_version","")).startswith("v07_s2x_formation"):
            import json
            print(json.dumps({"skeleton":skeleton["skeleton_id"],"stage":"single_calibration",
                              "agent":a,"core_s":measured[a],"finish_s":finished[a]},ensure_ascii=False),flush=True)
    return measured, finished, runs


def paired_run(scene, skeleton, plan, finished, mode):
    run = execute(skeleton, plan["departure_delays_s"],
                  time_budget=completion_budget(skeleton, plan["departure_delays_s"], finished))
    labels, frame = measure(scene, skeleton, run, mode, plan["batch_by_agent"], timing_plan=plan)
    return run, labels, frame


def timing_plans(skeleton, measured):
    return departure_delays(skeleton, measured)
