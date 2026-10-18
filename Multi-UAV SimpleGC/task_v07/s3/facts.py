"""Observed/result facts with concrete JSON Pointer provenance."""
import math
import re
from statistics import median

from ._common import P0ContractError, pointer

SECTORS = ("东", "东北", "北", "西北", "西", "西南", "南", "东南")


def from_sector(headings, members):
    # In same_direction, missing headings violate the current label contract.
    if not members or any(a not in headings or headings[a] is None for a in members):
        raise P0ContractError("same_direction has a missing/None member heading")
    angles = [math.radians(headings[a]) for a in members]
    if not all(math.isfinite(a) for a in angles):
        raise P0ContractError("Nonfinite member heading")
    theta = math.degrees(math.atan2(sum(math.sin(a) for a in angles),
                                   sum(math.cos(a) for a in angles))) % 360
    phi = (theta + 180) % 360
    return SECTORS[int(((phi + 22.5) % 360) // 45)]


def extract_facts(labels, public_scene):
    agents = labels["agents"]
    groups = labels["task_groups"]
    facts = {
        "n_agents": len(agents), "n_groups": len(groups),
        "cluster_intent": labels["cluster"]["assigned"]["intent"],
        "cluster_status": labels["cluster"]["result"]["status"],
        "fact_refs": {"n_agents": ["/agents"], "n_groups": ["/task_groups"],
                      "cluster_intent": ["/cluster/assigned/intent"],
                      "cluster_status": ["/cluster/result/status"]},
        "groups": [],
    }
    facility_ids = {e["id"] for e in public_scene["entities"] if e["type"] == "facility"}
    deepest = 0
    layer_refs, exit_refs, exits = [], [], []
    for index, gid in enumerate(sorted(groups), 1):
        group = groups[gid]
        assigned, observed = group["assigned"], group["observed"]
        members = observed["members"]
        target, role = assigned["target"], assigned["role"]
        match = re.fullmatch(r"facility_(\d+)", target)
        if not match or target not in facility_ids:
            raise P0ContractError(f"Invalid/unregistered target facility: {target}")
        gp = pointer("task_groups", gid)
        ref = {
            "group_id": [gp], "index": ["/task_groups"],
            "n_members": [gp + "/observed/members"],
            "role": [gp + "/assigned/role"],
            "execution_method": [gp + "/assigned/execution_method"],
            "target_id": [gp + "/assigned/target"],
            "facility_no": [gp + "/assigned/target"],
            "approach_class": [gp + "/observed/approach_classification"],
            "coordination": [gp + "/observed/coordination/classification"],
            "batch_count": [gp + "/observed/coordination/batches"],
            "group_status": [gp + "/result/status"],
        }
        entry_refs = [pointer("agents", a, "observed", "regions_by_facility",
                              target, "warning", "entered_observed") for a in members]
        entry = [agents[a]["observed"]["regions_by_facility"][target]["warning"]["entered_observed"]
                 for a in members]
        approach = observed["approach_classification"]
        sector = from_sector(observed["approach_headings_deg"], members) if approach == "same_direction" else None
        ref["entered_warning_all"] = entry_refs
        ref["from_sector"] = [gp + "/observed/approach_classification"] + [
            gp + "/observed/approach_headings_deg/" + a for a in members]
        method = assigned["execution_method"]
        coverage = None
        ref["coverage_pct"] = [gp + "/assigned/execution_method"]
        if method == "area_search":
            coverage = round(observed["shared_coverage"]["coverage_fraction"] * 100 / 5) * 5
            ref["coverage_pct"].append(gp + "/observed/shared_coverage/coverage_fraction")
        dwell = None
        ref["dwell_s"] = [gp + "/assigned/execution_method"]
        if method == "close_observation":
            durations = [agents[a]["observed"]["contribution"]["observation_dwell"]["total_duration_s"]
                         for a in members]
            dwell = max(10, round(median(durations) / 10) * 10)
            ref["dwell_s"] += [pointer("agents", a, "observed", "contribution",
                                      "observation_dwell", "total_duration_s") for a in members]
        exit_state = None
        ref["exit_state"] = [gp + "/assigned/role"]
        if role != "intrusion":
            values = [agents[a]["result"]["conditions"]["ended_outside_warning"] for a in members]
            exit_state = ("all_outside" if all(v is True for v in values)
                          else "all_inside" if all(v is False for v in values) else "mixed")
            paths = [pointer("agents", a, "result", "conditions", "ended_outside_warning") for a in members]
            ref["exit_state"] += paths
            exit_refs += paths
            exits += values
        for a in members:
            for level, name in enumerate(("warning", "alert", "protected"), 1):
                path = pointer("agents", a, "observed", "regions_by_facility", target, name, "entered_observed")
                layer_refs.append(path)
                if agents[a]["observed"]["regions_by_facility"][target][name]["entered_observed"] is True:
                    deepest = max(deepest, level)
        coord = observed["coordination"]["classification"]
        facts["groups"].append({
            "group_id": gid, "index": index, "n_members": len(members),
            "role": role, "execution_method": method, "target_id": target,
            "facility_no": int(match[1]), "entered_warning_all": all(v is True for v in entry),
            "approach_class": approach, "from_sector": sector, "coordination": coord,
            "batch_count": len(observed["coordination"]["batches"]) if coord == "sequential" else None,
            "group_status": group["result"]["status"], "coverage_pct": coverage,
            "dwell_s": dwell, "exit_state": exit_state, "fact_refs": ref,
        })
    classes = [g["approach_class"] for g in facts["groups"]]
    coords = [g["coordination"] for g in facts["groups"]]
    slots = {
        "n_agents": facts["n_agents"], "n_groups": facts["n_groups"],
        "approach_mode_cluster": ("same" if all(c == "same_direction" for c in classes)
                                  else "multi" if "multi_direction" in classes else "unknown"),
        "from_sector": facts["groups"][0]["from_sector"] if len(groups) == 1 else None,
        "deepest_layer": deepest,
        "coordination_cluster": coords[0] if coords and len(set(coords)) == 1 else "mixed",
        "exit_cluster": "all_outside" if all(v is True for v in exits) else "other",
        "intent": facts["cluster_intent"],
    }
    facts["slot_refs"] = {
        "n_agents": ["/agents"], "n_groups": ["/task_groups"],
        "approach_mode_cluster": [p for g in facts["groups"] for p in g["fact_refs"]["approach_class"]],
        "from_sector": ["/task_groups"] + [p for g in facts["groups"] for p in g["fact_refs"]["from_sector"]],
        "deepest_layer": layer_refs,
        "coordination_cluster": [p for g in facts["groups"] for p in g["fact_refs"]["coordination"]],
        "exit_cluster": exit_refs + [p for g in facts["groups"] for p in g["fact_refs"]["role"]],
        "intent": ["/cluster/assigned/intent"],
    }
    return {"facts": facts, "slots": slots}
