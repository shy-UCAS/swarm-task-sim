"""Accepted timing distributions and solo/joint discrepancies are observations."""


def accepted_timing(plan, selection):
    return {"mode": plan["mode"], "accepted_draw": selection["accepted_draw"],
            "rejected_count": selection["rejected_count"],
            "by_group": {gid: {key: group[key] for key in
                ("draw", "random_seed", "jitter_span_s", "batch_count", "batch_spans_s", "inter_batch_gaps_s")}
                for gid, group in plan["by_group"].items()}}


def rehearsal_discrepancies(rehearsal, labels, run):
    changes = []
    for agent, solo in rehearsal["agents"].items():
        actual = labels["agents"][agent]["result"]
        before = solo["result"]
        differing = {key: {"solo": before["conditions"].get(key), "joint": actual["conditions"].get(key)}
                     for key in sorted(set(before["conditions"]) | set(actual["conditions"]))
                     if before["conditions"].get(key) != actual["conditions"].get(key)}
        if differing or before["status"] != actual["status"]:
            changes.append({"agent_id": agent, "solo_result": before["status"], "joint_result": actual["status"],
                            "status_changed": before["status"] != actual["status"], "conditions": differing,
                            "solo_execution_status": solo["execution_status"], "joint_execution_status": run["execution_status"],
                            "solo_last_sample_s": solo["last_sample_s"], "joint_last_sample_s": float(run["time_us"][-1] / 1e6)})
    return {"agent_count": sum(item["status_changed"] for item in changes),
            "condition_difference_agent_count": sum(bool(item["conditions"]) for item in changes), "agents": changes}
