"""Summarize finished Q1 evidence and retain raw trajectory witnesses for new failures."""
from collections import Counter, defaultdict
from pathlib import Path
import csv
import hashlib
import json
import sys
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.audit_v07_s2_exact import _signed_distance


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    root = PROJECT / "docs/v07/evidence/m1"
    summary = read(root / "q1_summary.json")
    if summary["status"] != "PASS": raise ValueError("Q1 must finish successfully before review")
    episodes = {(e["attempt"], e["episode_id"]): e for e in summary["episodes"]}
    with (root / "q1_changes.csv").open(encoding="utf-8", newline="") as stream:
        changes = list(csv.DictReader(stream))
    transitions, recovered_conditions = Counter(), Counter()
    proofs = {}; changed_groups = []; aborts = []; reference = []
    threshold = read(PROJECT / "configs/criteria/criteria_v07_r1.json")["roles"]["intrusion"]["max_contour_distance_m"]
    for row in changes:
        transitions[(row["collection"], row["scope"], row["role"], row["old_result"], row["new_result"])] += 1
        if row["old_result"] == "failure" and row["new_result"] == "success":
            for name, values in json.loads(row["changed_conditions"]).items():
                if values["old"] is False:
                    recovered_conditions[(row["scope"], row["role"], name)] += 1
        if row["new_result"] != "failure": continue
        episode = episodes[row["attempt"], row["episode_id"]]; directory = Path(episode["destination"])
        receipt = read(directory / "independent_exact_audit.json")
        assert receipt["status"] == "PASS"
        witness = json.loads(row["evidence"])
        members = {row["entity_id"]: witness} if row["scope"] == "agent" else witness["members"]
        failed = [a for a, value in members.items() if value["failed_conditions"]]
        if row["scope"] == "task_group":
            changed_groups.append({"attempt": row["attempt"], "episode_id": row["episode_id"], "group": row["entity_id"], "failed_members": failed})
        for agent in failed:
            key = (row["attempt"], row["episode_id"], agent)
            if key in proofs: continue
            value = members[agent]; independent = receipt["independent_role_facts"][agent]
            assert set(value["failed_conditions"]) == {k for k, v in independent["result"]["conditions"].items() if v is False}
            proof = {"attempt": row["attempt"], "episode_id": row["episode_id"], "agent": agent,
                     "failed_conditions": value["failed_conditions"], "independent_conditions": independent["result"]["conditions"]}
            # Every newly failed agent in this corpus is checked against its full
            # stored trajectory, with an independent geometry implementation.
            if set(value["failed_conditions"]) != {"near_facility_contour"}:
                raise ValueError("Additional trajectory witness review required: " + str(key))
            labels = read(directory / "labels.json"); scene = read(directory / "public_scene.json")
            target = labels["agents"][agent]["assigned"]["target"]
            geometry = next(e["geometry"] for e in scene["entities"] if e["id"] == target)
            with np.load(directory / "truth_10hz.npz", allow_pickle=False) as truth:
                i = truth["agent_ids"].tolist().index(agent)
                distance = _signed_distance(geometry, truth["p"][:, i, :2])
                frame = int(np.argmin(distance)); minimum = float(distance[frame])
                assert minimum > threshold
                assert abs(minimum - value["minimum_contour_distance_m"]) < 1e-6
                assert frame == value["minimum_contour_distance_frame"]
                proof.update(minimum_contour_distance_m=minimum, threshold_m=threshold, frame=frame,
                             time_s=float(truth["time_us"][frame] / 1e6), position_m=truth["p"][frame, i].tolist(),
                             facility_geometry=geometry)
            proofs[key] = proof
    for episode in episodes.values():
        directory = Path(episode["destination"])
        if episode["aborted"]:
            labels, task = read(directory / "labels.json"), read(directory / "task.json")
            group = labels["task_groups"][task["main_group_id"]]
            members = group["assigned"]["members"]
            missing = all(labels["agents"][a]["observed"]["core_event"]["t_s"] is None and
                          labels["agents"][a]["observed"]["core_event"]["t_confirm"] is None for a in members)
            assert missing
            aborts.append({"attempt": episode["attempt"], "episode_id": episode["episode_id"],
                          "withdrawal_observed": group["result"]["conditions"]["abort_group_withdrawal_observed"],
                          "core_events_missing": missing, "assigned_task_result": group["result"]["status"]})
        if "quick_b" in episode["attempt"] and "family_s12_4d13d93f9171c446_ext_009_regular" in episode["episode_id"]:
            labels, old = read(directory / "labels.json"), read(Path(episode["source"]) / "labels.json")
            for gid, group in labels["task_groups"].items():
                agents = group["assigned"]["members"]
                if labels["agents"][agents[0]]["assigned"]["role"] == "feint":
                    reference.append({"episode_id": episode["episode_id"], "group": gid,
                                      "old_result": old["task_groups"][gid]["result"]["status"], "new_result": group["result"]["status"],
                                      "depth_fractions": {a: labels["agents"][a]["observed"]["contribution"]["depth_fraction_in_alert_band"] for a in agents}})
    approach = defaultdict(Counter)
    for row in read(root / "q1_approach.json"):
        if row["collection"] == "main":
            for key in ("total", "matches"): approach[row["intent"]][key] += row[key]
    main_episodes = [e for e in episodes.values() if e["collection"] == "main"]
    review = {"status": "PASS", "new_failure_agent_witnesses": list(proofs.values()), "new_failure_groups": changed_groups,
              "transitions": [dict(collection=c, scope=s, role=r, old=o, new=n, count=v) for (c, s, r, o, n), v in sorted(transitions.items())],
              "recovered_old_failed_conditions": [dict(scope=s, role=r, condition=k, count=v) for (s, r, k), v in sorted(recovered_conditions.items())],
              "aborted": aborts, "quick_b_reference": reference,
              "main_cluster_transitions": dict(Counter(e["old_result"] + "->" + e["new_result"] for e in main_episodes)),
              "main_quality_counts": dict(Counter(e["quality_status"] for e in main_episodes)),
              "main_execution_counts": dict(Counter(e["execution_status"] for e in main_episodes)),
              "main_approach_by_intent": {i: {**c, "agreement_fraction": c["matches"] / c["total"]} for i, c in approach.items()},
              "implementation_sha256": {p: hashlib.sha256((PROJECT / p).read_bytes()).hexdigest() for p in
                   ("configs/criteria/criteria_v07_r1.json", "task_v07/criteria_labels.py", "task_v07/detectors.py",
                    "scripts/audit_v07_m1.py", "scripts/audit_v07_m1_detectors.py", "scripts/cross_v07_m1.py", "scripts/relabel_v07_m1.py")}}
    (root / "q1_review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in review.items() if k not in ("new_failure_agent_witnesses", "new_failure_groups", "implementation_sha256")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
