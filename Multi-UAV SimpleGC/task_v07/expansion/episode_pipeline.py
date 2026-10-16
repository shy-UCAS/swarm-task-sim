"""Episode-wide geometry, group calibration and shared-clock delay composition."""
from copy import deepcopy
import numpy as np

from task_v07.planning import seed_for
from task_v07.unified.config import stop_fields
from .contracts import RouteBundle, P0ContractError
from .pipeline import plan_group, single_agent_timing, timing_plans, COMMON_CONSTANTS
from .role_planners import planner_for, PlanningInfeasible
from .sampling import derive_intent
from .geometry_checks import planning_layer_interval_check


class ConstrainedPlanner:
    legacy_vertical_slice = False

    def __init__(self, planner, excluded, variant, radius_first=False):
        self.planner, self.excluded, self.variant = planner, excluded, variant
        self.radius_first = radius_first

    def plan_with_template(self, scene, group, parameters):
        parameters = deepcopy(parameters)
        parameters["excluded_work_area_bearings_deg"] = list(self.excluded)
        parameters["minimum_group_bearing_difference_deg"] = 60.
        parameters["monitor_radius_start_index"] = 2 * self.variant
        if self.variant and not (self.radius_first and self.variant == 1):
            for key in ("geometry_seed", "planning_seed"):
                parameters[key] = seed_for(parameters[key], f"shared-geometry-variant:{self.variant}")
        return self.planner.plan_with_template(scene, group, parameters)


def assemble_episode(descriptor, groups, bundles, variant=0):
    """Merge already checked group geometries without resampling public fields."""
    ids = descriptor["agent_ids"]
    paths = {a: bundle.waypoints_by_agent[a] for bundle in bundles.values() for a in bundle.waypoints_by_agent}
    if len(paths) != len(ids) or set(paths) != set(ids):
        raise P0ContractError("Merged groups do not partition registered physical IDs")
    family = descriptor["family_conditions"]
    skeleton = {"schema_version": "traj2language.skeleton/0.7-s2x.groups.1", **COMMON_CONSTANTS, **stop_fields(),
                "skeleton_id": descriptor["skeleton_id"], "family_id": descriptor["family_id"], "map_id": descriptor["map_id"],
                "base_intent": descriptor["base_intent"], "members": sorted(ids), "agent_ids": list(ids),
                "column_seed": descriptor["column_seed"], "cruise_speed_m_s": family["cruise_speed_m_s"],
                "task_altitude_m": family["task_altitude_m"], "initial_states": deepcopy(family["initial_states"]),
                "group_skeletons": {g: groups[g] for g in sorted(groups)}, "planning_geometry_variant": variant,
                "references": {a: deepcopy(group["references"][a]) for group in groups.values() for a in group["members"]},
                "exclusion_policy": {a: deepcopy(group["exclusion_policy"][a]) for group in groups.values() for a in group["members"]},
                "main_unit_id": descriptor["main_unit_id"],
                "main_group_id": next((g["group_id"] for g in descriptor["task_groups"] if descriptor["main_unit_id"] in g["source_units"]), None),
                "approach_mode": descriptor["common_draw"]["approach_mode"], "common_slot": descriptor["common_draw"]["slot"]}
    skeleton["planning_interval_warning_m"]=max(g.get("planning_interval_warning_m",6.) for g in groups.values())
    return skeleton, RouteBundle(paths, {a: 0. for a in ids})


def plan_episode(scene, descriptor, variant=0):
    from .candidate_search import episode_candidate_pool
    candidates, report = episode_candidate_pool(scene, descriptor)
    if variant >= len(candidates):
        raise PlanningInfeasible('geometry_infeasible', f"continuous candidate pool exhausted: {report['rejection_reasons']}")
    chosen = candidates[variant]
    return chosen['skeleton'], chosen['bundle'], chosen['checks']


def compose_timing_plans(skeleton, measured_by_group):
    plans = {mode: {"schema_version": "v07_group_timing_plan_v1", "by_group": {}, "departure_delays_s": {},
                    "batch_by_agent": {}, "basis": "per-group single-agent measured events plus registered private group offsets"}
             for mode in ("synchronous", "sequential")}
    for gid, group in skeleton["group_skeletons"].items():
        group_plans = timing_plans(group, measured_by_group[gid])
        offset = group["between_group_offset_s"]
        for mode, plan in group_plans.items():
            plan = deepcopy(plan)
            for key in ("target_event_times_s", "target_event_times_grid_s", "departure_delays_s"):
                plan[key] = {a: round(value + offset, 10) for a, value in plan[key].items()}
            plan["batch_centers_s"] = [value + offset for value in plan["batch_centers_s"]]
            plan["between_group_offset_s"] = offset
            plans[mode]["by_group"][gid] = plan
            plans[mode]["departure_delays_s"].update(plan["departure_delays_s"])
            plans[mode]["batch_by_agent"].update(plan["batch_by_agent"])
    return plans


def calibrate_episode(scene, skeleton):
    measured_by_group, measured, finished, solo = {}, {}, {}, {}
    for gid, group in skeleton["group_skeletons"].items():
        times, ends, runs = single_agent_timing(scene, group)
        measured_by_group[gid] = times
        measured.update(times)
        finished.update(ends)
        solo.update(runs)
    if any(value is None for value in [*measured.values(), *finished.values()]):
        return measured, finished, solo, None
    return measured, finished, solo, compose_timing_plans(skeleton, measured_by_group)


def episode_interval_check(skeleton, bundle, plans):
    # The initial settle is common but included in witness times. All aircraft
    # remain present, including before release and after their route ends.
    gate_plans = deepcopy(plans)
    for plan in gate_plans.values():
        plan["departure_delays_s"] = {a: value + skeleton["initial_settle_s"]
                                      for a, value in plan["departure_delays_s"].items()}
    report = planning_layer_interval_check(bundle, gate_plans, skeleton["cruise_speed_m_s"],
        warning_m=skeleton.get("planning_interval_warning_m",6.),
        dwells_by_agent={a:r['intermediate_dwell'] for a,r in skeleton.get('references',{}).items() if 'intermediate_dwell' in r})
    report["scope"] = "all agents across all groups, entire episode, both timing versions"
    report["includes_registered_group_offsets"] = True
    report["includes_initial_settle_s"] = skeleton["initial_settle_s"]
    return report
