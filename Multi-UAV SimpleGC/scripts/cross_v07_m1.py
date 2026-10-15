"""Design 2.7 cross-negation on the same observed group and target."""
from copy import deepcopy
from pathlib import Path
import numpy as np
from scripts.audit_v07_m1 import independently_measure
from scripts.audit_v07_s2_exact import _read

KINDS = ("transit", "area_search", "close_observation", "monitoring", "feint", "intrusion")
NON_REQUIRED = {("area_search", "transit"), ("area_search", "close_observation")}
NOT_APPLICABLE = {("transit", "area_search"), ("close_observation", "area_search")}


def role_kind(group):
    return ("close_observation" if group["execution_method"] == "close_observation" else "area_search") if group["role"] == "reconnaissance" else group["role"]


def cross_group(scene, group, run, *, source_success=True):
    source = role_kind(group)
    rows = []
    cache = {}
    for destination in KINDS:
        if destination == source: continue
        expectation = "not_required" if (source, destination) in NON_REQUIRED else "not_applicable" if (source, destination) in NOT_APPLICABLE else "no"
        row = {"source_role": source, "criterion_role": destination, "expected": expectation}
        if not source_success or group.get("abort_observation"):
            rows.append({**row, "verdict": "not_run", "status": "not_run", "reason": "source role not successful or explicitly aborted"}); continue
        if expectation == "not_applicable":
            rows.append({**row, "verdict": "not_applicable", "status": "not_applicable"}); continue
        template = deepcopy(group)
        template["role"] = "reconnaissance" if destination in ("area_search", "close_observation") else destination
        template["execution_method"] = destination
        template["base_intent"] = "penetration" if destination == "intrusion" else template["role"]
        if destination == "area_search" and "survey" not in template:
            # Monitoring -> search is excluded by its observed revisit regardless
            # of any possible declared search region. Never fabricate a region.
            if source == "monitoring":
                original = independently_measure(scene, group, run, True, detector_cache=cache)
                excluded = all(a["contribution"]["revisit"]["detected"] for a in original["agents"].values())
                rows.append({**row, "verdict": "no" if excluded else "unknown", "status": "PASS" if excluded else "INCOMPLETE", "reason": "observed patrol revisit violates search negative predicate"})
            else:
                original = independently_measure(scene, group, run, True, detector_cache=cache)
                # Successful feint/intrusion already witnesses an alert entry,
                # which every reconnaissance role forbids.
                excluded = source in ("feint", "intrusion") and all(
                    a["core_event"]["t_s"] is not None for a in original["agents"].values())
                rows.append({**row, "verdict": "no" if excluded else "not_applicable", "status": "PASS" if excluded else "not_applicable", "reason": "target alert/protected entry excludes reconnaissance"})
            continue
        expected = independently_measure(scene, template, run, True, detector_cache=cache)
        status = expected["groups"][template["group_id"]]["result"]["status"]
        verdict = {"success": "yes", "failure": "no", "unknown": "unknown"}[status]
        rows.append({**row, "verdict": verdict, "status": "FAIL" if expectation == "no" and verdict == "yes" else "PASS",
            "group_conditions": expected["groups"][template["group_id"]]["result"]["conditions"],
            "agent_conditions": {a: value["result"]["conditions"] for a, value in expected["agents"].items()}})
    return rows


def criteria_cross_report(attempt):
    attempt = Path(attempt); rows = []
    for root in sorted(p.parent for p in attempt.glob("**/labels.json")):
        labels = _read(root / "labels.json")
        if labels.get("evidence", {}).get("criteria_version") != "criteria/0.7-r1": continue
        task, scene = _read(root / "task.json"), _read(root / "public_scene.json")
        with np.load(root / "truth_10hz.npz", allow_pickle=False) as saved:
            ids = saved["agent_ids"].tolist()
            run = {key: saved[key].copy() for key in ("time_us", "p", "v")}
        for gid, group in task.get("group_skeletons", {task.get("group_id"): task}).items():
            columns = [i for i, a in enumerate(ids) if a in group["members"]]
            sub = {**run, "agent_ids": [ids[i] for i in columns], "p": run["p"][:, columns], "v": run["v"][:, columns]}
            success = labels["task_groups"][gid]["result"]["status"] == "success" and labels["generation_quality"]["retained"]
            rows.extend({"path": root.relative_to(attempt).as_posix(), "group_id": gid, **row}
                        for row in cross_group(scene, group, sub, source_success=success))
    affirmative = [r for r in rows if r["status"] == "FAIL"]
    return {"schema_version": "criteria/0.7-r1.cross", "status": "FAIL" if affirmative else "PASS",
            "scope": "same successful observed group, target and declared region; only design 2.7 no cells are gates",
            "counts": {s: sum(r["status"] == s for r in rows) for s in ("PASS", "FAIL", "not_run", "not_applicable", "INCOMPLETE")},
            "affirmative_group_count": len(affirmative), "affirmative_witnesses": affirmative, "rows": rows}
