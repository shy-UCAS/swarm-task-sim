"""Independent full-clock group/cluster audit. No task_v07 imports."""
from copy import deepcopy
from itertools import combinations
from pathlib import Path
import hashlib
import numpy as np

from scripts.audit_v07_s2_exact import _read
from scripts.audit_v07_s2_roles import _load_truth, _build_levels, _check_separation
from scripts.audit_v07_s2_conditions import audit_conditions, _equal, _outcome


def independent_coordination(events, window, gap):
    if len(events) < 2:
        return "not_applicable", []
    if any(value is None for value in events.values()):
        return "unknown", []
    ordered = sorted(events, key=lambda a: (events[a], a))
    blocks = [[ordered[0]]]
    for a in ordered[1:]:
        if events[a] - events[blocks[-1][-1]] > gap:
            blocks.append([])
        blocks[-1].append(a)
    spreads = [max(events[a] for a in b) - min(events[a] for a in b) for b in blocks]
    classification = ("synchronous" if max(events.values()) - min(events.values()) <= window else
                      "sequential" if len(blocks) >= 2 and all(s <= window for s in spreads) else "other")
    return classification, [sorted(b) for b in blocks]


def audit_groups(root):
    root = Path(root)
    task, scene, labels = (_read(root / name) for name in ("task.json", "public_scene.json", "labels.json"))
    if labels.get("evidence", {}).get("criteria_version") == "criteria/0.7-r1":
        from scripts.audit_v07_m1 import audit_episode
        return audit_episode(root)
    ids, t, p, v = _load_truth(root)
    with np.load(root / "frame_labels.npz", allow_pickle=False) as loaded:
        stored = {key: loaded[key].copy() for key in loaded.files}
    from scripts.audit_v07_m1 import compare_value, attach_diagnostics
    errors, diagnostics, reports, facts, condition_map = [], [], {}, {}, {}
    complete = labels["evidence"]["complete_observation"]
    def compare(field, left, right):
        compare_value(field, left, right, errors, diagnostics)
    for gid, group in task["group_skeletons"].items():
        indices = [i for i, a in enumerate(ids) if a in group["members"]]
        members = [ids[i] for i in indices]
        subset_p, subset_v = p[:, indices], v[:, indices]
        subset_frame = {key: value[:, indices] if key in ("region_all_facilities", "region_assigned_target", "phase", "inside_hard_obstacle") else value
                        for key, value in stored.items()}
        subset_frame["agent_ids"] = np.array(members)
        subset_labels = deepcopy(labels)
        subset_labels["agents"] = {a: deepcopy(labels["agents"][a]) for a in members}
        subset_labels["task_groups"] = {gid: deepcopy(labels["task_groups"][gid])}
        # Role audit needs a single-group receipt. Global separation is checked
        # against the original full episode below, never against this receipt.
        local_min = min((float(np.linalg.norm(subset_p[:, i] - subset_p[:, j], axis=1).min())
                         for i, j in combinations(range(len(indices)), 2)), default=None)
        subset_labels["cluster"]["observed"]["minimum_separation_m"] = local_min
        subset_labels["cluster"]["result"] = deepcopy(labels["task_groups"][gid]["result"])
        subset_labels["generation_quality"]["retained"] = local_min is None or local_min >= 2.
        report = audit_conditions(root, data={"scene": scene, "task": group, "labels": subset_labels,
                                 "ids": members, "t": t, "p": subset_p, "v": subset_v, "frame": subset_frame})
        reports[gid] = report
        facts.update(report["independent_role_facts"])
        condition_map[gid] = report["condition_audit_map"]
        events = {a: None if report["independent_role_facts"][a]["core_event_frame"] is None else
                  float(t[report["independent_role_facts"][a]["core_event_frame"]] / 1e6) for a in members}
        classification, batches = independent_coordination(events, group["sync_window_s"], group["batch_split_gap_s"])
        saved = labels["task_groups"][gid]["observed"]["coordination"]
        compare(f"{gid}.coordination.classification", saved["classification"], classification)
        compare(f"{gid}.coordination.event_times_s", saved["event_times_s"], events)
        compare(f"{gid}.coordination.batch_members", [b["members"] for b in saved["batches"]], batches)
        compare(f"{gid}.coordination.event_range_s", saved["event_range_s"], None if None in events.values() else round(max(events.values()) - min(events.values()), 6))
    facilities = sorted(e["id"] for e in scene["entities"] if e["type"] == "facility")
    levels = _build_levels(scene, p[:, :, :2], facilities)
    expected_in_order = levels[:, :, [facilities.index(f) for f in stored["facility_ids"].tolist()]]
    region_diff = int(np.count_nonzero(expected_in_order != stored["region_all_facilities"]))
    targets_by_id = {a: g["target_id"] for g in task["group_skeletons"].values() for a in g["members"]}
    target_levels = np.stack([levels[:, i, facilities.index(targets_by_id[a])] for i, a in enumerate(ids)], axis=1)
    target_diff = int(np.count_nonzero(target_levels != stored["region_assigned_target"]))
    target_set = sorted(set(targets_by_id.values()))
    intrusion_members = {a for group in task["group_skeletons"].values() if group["role"] == "intrusion" for a in group["members"]}
    entered = sorted(f for j, f in enumerate(facilities)
                     if any((levels[:, i, j] == 3).any() for i, a in enumerate(ids) if a in intrusion_members))
    roles = {g["role"] for g in task["group_skeletons"].values()}
    single_role_intents = {"transit": "transit", "reconnaissance": "reconnaissance", "monitoring": "monitoring", "feint": "feint"}
    derived = (single_role_intents.get(next(iter(roles))) if len(roles) == 1 and "intrusion" not in roles else
               "penetration" if "intrusion" in roles and roles <= {"intrusion", "monitoring", "feint"} else None)
    primary = target_set[0] if len(target_set) == 1 else entered[0] if derived == "penetration" and len(entered) == 1 else None
    cluster = labels["cluster"]
    compare("cluster.assigned.intent_from_role_composition", cluster["assigned"]["intent_from_role_composition"], derived)
    compare("cluster.assigned.target_set", cluster["assigned"]["target_set"], target_set)
    compare("cluster.observed.primary_target", cluster["observed"]["primary_target"], primary)
    compare("cluster.observed.protected_facilities_entered_by_intrusion_groups", cluster["observed"]["protected_facilities_entered_by_intrusion_groups"], entered)
    related = [f for j, f in enumerate(facilities) if (levels[:, :, j] >= 1).any()]
    compare("cluster.observed.related_facilities", cluster["observed"]["related_facilities"], related)
    statuses = [r["independent_group_status"] for r in reports.values()]
    checks = {"all_task_groups_complete": False if "failure" in statuses else None if "unknown" in statuses else True,
              "assigned_role_composition_matches": derived == task["base_intent"]}
    cluster_map = {"all_task_groups_complete": ["independent per-group condition outcomes"],
                   "assigned_role_composition_matches": ["independent composition of registered roles and assigned intent"]}
    for key in set(cluster["result"]["conditions"]) - set(checks):
        errors.append({"scope": "cluster", "uncovered_condition": key})
    for key, value in checks.items():
        compare(f"cluster.condition.{key}", cluster["result"]["conditions"].get(key), value)
    compare("cluster.result.status", cluster["result"]["status"], _outcome(list(checks.values()), complete))
    for relation in cluster["observed"]["between_group_timing"]:
        ga, gb = relation["group_ids"]
        intervals = {}
        for gid in (ga, gb):
            times = [None if facts[a]["core_event_frame"] is None else float(t[facts[a]["core_event_frame"]] / 1e6)
                     for a in task["group_skeletons"][gid]["members"]]
            intervals[gid] = None if None in times else [min(times), max(times)]
        if any(value is None for value in intervals.values()):
            intervals = {ga: None, gb: None}
            classification = "unknown"
        else:
            classification = "first_before_second" if intervals[ga][1] < intervals[gb][0] else "second_before_first" if intervals[gb][1] < intervals[ga][0] else "event_intervals_overlap"
        compare(f"between_groups.{ga}.{gb}.intervals", relation["event_intervals_s"], intervals)
        compare(f"between_groups.{ga}.{gb}.relation", relation["observed_relation"], classification)
    errors.extend(_check_separation(labels, p, ids))
    for i, a in enumerate(ids):
        minimum = min((float(np.linalg.norm(p[:, i] - p[:, j], axis=1).min()) for j in range(len(ids)) if j != i), default=None)
        compare(f"{a}.minimum_separation_m", labels["agents"][a]["observed"]["minimum_separation_m"], minimum)
    uncovered = [e for e in errors if "uncovered_condition" in e] + [e for r in reports.values() for e in r["uncovered_conditions"]]
    group_errors = sum(r["event_or_metric_difference_count"] for r in reports.values())
    passed = not (errors or uncovered or region_diff or target_diff) and all(r["status"] == "PASS" for r in reports.values())
    result = {"directory": str(root), "status": "PASS" if passed else "P0_STOP", "frames": len(t), "agents": len(ids),
            "facilities": len(facilities), "all_facility_frame_comparisons": int(levels.size),
            "region_difference_count": region_diff, "target_difference_count": target_diff,
            "event_or_metric_difference_count": len(errors) + group_errors, "event_or_metric_witnesses": errors[:50],
            "group_audits": reports, "condition_audit_map": {"task_groups": condition_map, "cluster": cluster_map},
            "uncovered_conditions": uncovered, "independent_role_facts": facts,
            "truth_csv_sha256": hashlib.sha256((root / "truth.csv").read_bytes()).hexdigest(),
            "method": "independent per-group role evidence, analytic/GEOS regions and full-clock cluster recomposition"}
    return attach_diagnostics(result, diagnostics)
