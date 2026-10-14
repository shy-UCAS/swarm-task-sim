"""Compose independently measured task groups on one shared episode clock."""
from copy import deepcopy
from itertools import combinations
import numpy as np

from .contracts import P0ContractError
from .sampling import derive_intent


def measure_groups(scene, skeleton, run, mode, planned_batches=None, *, cutoff_s=None, timing_plan=None):
    # The sole role/core-event implementation remains labels.measure.
    from task_v07.labels import measure, observed_conditions_result
    ids = list(run["agent_ids"])
    by_id = {a: i for i, a in enumerate(ids)}
    templates = skeleton["group_skeletons"]
    if set(ids) != set(skeleton["members"]):
        raise P0ContractError("Episode measurement requires the complete registered member set")
    assigned_intent = derive_intent([{"role": group["role"]} for group in templates.values()])
    if assigned_intent != skeleton["base_intent"]:
        raise P0ContractError("Assigned group composition disagrees with the cluster intent")
    agents, groups, frames = {}, {}, {}
    for gid, group in templates.items():
        columns = [by_id[a] for a in ids if a in group["members"]]
        subset = {**run, "agent_ids": [ids[i] for i in columns],
                  "p": run["p"][:, columns], "v": run["v"][:, columns]}
        if "a" in run:
            subset["a"] = run["a"][:, columns]
        plan = None if timing_plan is None else timing_plan["by_group"][gid]
        batches = None if plan is None else plan["batch_by_agent"]
        measured, frame = measure(scene, group, subset, mode, batches, cutoff_s=cutoff_s, timing_plan=plan)
        agents.update(measured["agents"])
        groups.update(measured["task_groups"])
        frames[gid] = frame
    prototype = measured
    t = next(iter(frames.values()))["time_us"]
    position = run["p"][:len(t)]
    minimum, closest = None, None
    agent_min = {a: None for a in ids}
    for a, b in combinations(sorted(ids), 2):
        distance = np.linalg.norm(position[:, by_id[a]] - position[:, by_id[b]], axis=1)
        k = int(np.argmin(distance))
        value = float(distance[k])
        if minimum is None or value < minimum:
            minimum, closest = value, {"agents": [a, b], "t_s": float(t[k] / 1e6), "frame_index": k}
        for member in (a, b):
            agent_min[member] = value if agent_min[member] is None else min(agent_min[member], value)
    for a in ids:
        agents[a]["observed"]["minimum_separation_m"] = agent_min[a]
    facilities = next(iter(frames.values()))["facility_ids"]
    n, nf = len(ids), len(facilities)
    frame = {"time_us": t, "agent_ids": np.array(ids), "facility_ids": facilities,
             "region_all_facilities": np.zeros((len(t), n, nf), np.int8),
             "region_assigned_target": np.zeros((len(t), n), np.int8),
             "phase": np.zeros((len(t), n), np.int8), "inside_hard_obstacle": np.zeros((len(t), n), bool)}
    for gid, part in frames.items():
        if not np.array_equal(part["time_us"], t) or not np.array_equal(part["facility_ids"], facilities):
            raise P0ContractError("Task-group time/facility axes differ")
        columns = [by_id[a] for a in part["agent_ids"].tolist()]
        for key in ("region_all_facilities", "region_assigned_target", "phase", "inside_hard_obstacle"):
            frame[key][:, columns] = part[key]
    targets = sorted({group["target_id"] for group in templates.values()})
    related = sorted({fid for a in agents.values() for fid, facts in a["observed"]["regions_by_facility"].items()
                      if facts["warning"]["entered_observed"]})
    entered = sorted({fid for a in agents.values() if a["assigned"]["role"] == "intrusion"
                      for fid, facts in a["observed"]["regions_by_facility"].items() if facts["protected"]["entered_observed"]})
    primary = targets[0] if len(targets) == 1 else entered[0] if assigned_intent == "penetration" and len(entered) == 1 else None
    relationships = []
    for ga, gb in combinations(sorted(groups), 2):
        ca, cb = (groups[g]["observed"]["coordination"]["event_times_s"] for g in (ga, gb))
        known = all(value is not None for value in [*ca.values(), *cb.values()])
        intervals = {g: None if not known else [min(c.values()), max(c.values())] for g, c in ((ga, ca), (gb, cb))}
        relation = "unknown"
        if known:
            relation = "first_before_second" if max(ca.values()) < min(cb.values()) else "second_before_first" if max(cb.values()) < min(ca.values()) else "event_intervals_overlap"
        relationships.append({"scope": "between_task_groups", "group_ids": [ga, gb],
                              "event_types": [next(iter(agents[a]["observed"]["core_event"]["raw_event_type"]
                                                       for a in templates[g]["members"])) for g in (ga, gb)],
                              "event_intervals_s": intervals, "observed_relation": relation,
                              "interpretation": "event order only; no cross-role coordination or causal claim"})
    statuses = [group["result"]["status"] for group in groups.values()]
    conditions = {"all_task_groups_complete": False if "failure" in statuses else None if "unknown" in statuses else True,
                  "assigned_role_composition_matches": assigned_intent == skeleton["base_intent"]}
    complete = prototype["evidence"]["complete_observation"]
    quality = deepcopy(prototype["generation_quality"])
    error = minimum is not None and minimum < 2.
    quality.update(status="generation_error" if error else "valid", retained=not error,
                   exclusion_reasons=["minimum_separation_below_2m"] if error else [], minimum_separation_m=minimum,
                   hard_obstacle_sample_count=int(frame["inside_hard_obstacle"].sum()),
                   outside_world_sample_count=sum(a["observed"]["outside_world_sample_count"] for a in agents.values()))
    labels = {"schema_version": "traj2language.labels/0.7-s2x.groups.1", "evidence": prototype["evidence"],
              "agents": {a: agents[a] for a in sorted(agents)}, "task_groups": {g: groups[g] for g in sorted(groups)},
              "cluster": {"assigned": {"intent": skeleton["base_intent"], "intent_from_role_composition": assigned_intent,
                            "target_set": targets, "task_groups": sorted(groups), "planned_coordination": mode,
                            "timing_by_group": None if timing_plan is None else timing_plan["by_group"]},
                          "observed": {"related_facilities": related, "primary_target": primary,
                            "primary_target_basis": "all groups share target" if len(targets) == 1 else "unique protected entry by intrusion role" if primary is not None else "no unique primary target",
                            "protected_facilities_entered_by_intrusion_groups": entered,
                            "group_coordination": [{"group_id": g, **groups[g]["observed"]["coordination"]} for g in sorted(groups)],
                            "between_group_timing": relationships, "minimum_separation_m": minimum, "closest_pair": closest},
                          "result": {"status": observed_conditions_result(conditions, complete), "conditions": conditions}},
              "frame_labels": {**prototype["frame_labels"], "agent_ids": ids}, "generation_quality": quality}
    return labels, frame
