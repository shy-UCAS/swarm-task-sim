"""Solo execution and observable M1 criteria, without geometry or label repairs."""
from pathlib import Path
import numpy as np
from task_v07.execution import execute
from task_v07.labels import measure
from task_v07.detectors import coverage
from task_v07.criteria import load_criteria
from task_v07.io import read_json
from task_v07.expansion.contracts import P0ContractError


def groups_of(skeleton):
    return skeleton.get("group_skeletons", {skeleton.get("group_id"): skeleton})


def evaluate_solos(scene, skeleton, solos):
    """Also used for offline replay; no simulator calls and no shared time padding."""
    if set(solos) != set(skeleton["members"]):
        raise P0ContractError("Rehearsal solo identities differ from skeleton members")
    cfg = load_criteria()
    agents, groups, failures, core, finished = {}, {}, [], {}, {}
    for gid, group in groups_of(skeleton).items():
        footprints = []
        for agent in sorted(group["members"]):
            run = solos[agent]
            if list(run["agent_ids"]) != [agent]:
                raise P0ContractError("Rehearsal input must contain exactly its registered agent")
            labels, frame = measure(scene, group, run, "unassigned_measurement")
            value = labels["agents"][agent]
            core[agent] = value["observed"]["core_event"]["t_s"]
            finished[agent] = float(run["time_us"][-1] / 1e6) if run["execution_status"] == "completed" else None
            conditions = [name for name, passed in value["result"]["conditions"].items() if passed is not True]
            if core[agent] is None: conditions.append("core_event_missing")
            if value["result"]["status"] != "success" and not conditions: conditions.append("result_not_success")
            if conditions:
                failures.append({"group_id": gid, "agent_id": agent, "conditions": conditions})
            agents[agent] = {"group_id": gid, "result": value["result"], "core_event": value["observed"]["core_event"],
                             "execution_status": run["execution_status"], "completion_time_s": finished[agent],
                             "last_sample_s": float(run["time_us"][-1] / 1e6)}
            if group["execution_method"] == "area_search":
                observed = coverage(run["p"][:, 0, :2], np.linalg.norm(run["v"][:, 0], axis=1),
                    frame["region_assigned_target"][:, 0], frame["inside_hard_obstacle"][:, 0], group["survey"], cfg)
                footprints.append(observed["covered_mask"])
        shared = None
        if footprints:
            union = np.logical_or.reduce(footprints)
            shared = {"covered_grid_point_count": int(union.sum()), "grid_point_count": len(union),
                      "coverage_fraction": float(union.mean()) if len(union) else 0.,
                      "required_fraction": cfg["detectors"]["coverage"]["min_group_fraction"]}
            if shared["coverage_fraction"] < shared["required_fraction"]:
                failures.append({"group_id": gid, "agent_id": None, "members": sorted(group["members"]),
                                 "conditions": ["shared_coverage"], "evidence": shared})
        groups[gid] = {"core_times_s": {a: core[a] for a in group["members"]}, "shared_coverage": shared,
                       "status": "failure" if any(f["group_id"] == gid for f in failures) else "success"}
    return {"status": "rejected" if failures else "passed", "category": "rehearsal_failure" if failures else None,
            "agents": agents, "groups": groups, "failures": failures,
            "core_times_s": core, "completion_times_s": finished,
            "completion_budget_basis": "measured" if all(v is not None for v in finished.values()) else "conservative"}


def rehearse(scene, skeleton):
    solos = {}
    for group in groups_of(skeleton).values():
        for agent in sorted(group["members"]):
            solos[agent] = execute(group, {a: 0. for a in group["members"]}, only_agent=agent)
    return evaluate_solos(scene, skeleton, solos), solos


def load_saved_rehearsal(directory, skeleton):
    """Old NPZs lack status; old calibration records distinguish completed/timeout."""
    directory = Path(directory)
    calibration = read_json(directory / "timing_calibration.json")
    finishes = calibration.get("completed_hold_times_s", calibration.get("completion_times_s"))
    if not isinstance(finishes, dict) or set(finishes) != set(skeleton["members"]):
        raise P0ContractError("Saved solo completion metadata is missing or misaligned")
    result = {}
    for agent in skeleton["members"]:
        with np.load(directory / f"single_agent_{agent}.npz", allow_pickle=False) as stored:
            run = {key: stored[key].copy() for key in ("time_us", "p", "v")}
            run["agent_ids"] = stored["agent_ids"].tolist()
            status = str(stored["execution_status"].item()) if "execution_status" in stored.files else (
                "completed" if finishes[agent] is not None else "timeout")
        run["execution_status"] = status
        result[agent] = run
    return result
