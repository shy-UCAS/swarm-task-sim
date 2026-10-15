"""960 registered same-family/same-common-slot cross-template checks."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import argparse
import sys
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from task_v07.io import read_json, save_json
from task_v07.expansion.evaluation import exported_evidence, evaluate, Evaluation
from task_v07.labels import measure
from task_v07.expansion.sampling import INTENTS
from scripts.run_v07_s2_expansion import INFRA_ATTEMPT

MODES = ("synchronous", "sequential")


def detailed_group_evaluator(scene, template, evidence):
    members = list(template['members'])
    columns = [list(evidence.agent_ids).index(a) for a in members]
    run = {'agent_ids': members, 'time_us': np.asarray(evidence.time_us),
           'p': np.asarray(evidence.p)[:, columns], 'v': np.asarray(evidence.v)[:, columns],
           'execution_status': 'completed' if evidence.complete else 'evidence_prefix'}
    labels, _ = measure(scene, template, run, 'unassigned_measurement')
    group = labels['task_groups'][template['group_id']]
    status = group['result']['status']
    frames = {a: labels['agents'][a]['observed']['core_event']['frame_index'] for a in members}
    facts = {'group_result': status, 'group_conditions': group['result']['conditions'],
             'agent_results': {a: labels['agents'][a]['result']['status'] for a in members},
             'agent_conditions': {a: labels['agents'][a]['result']['conditions'] for a in members},
             'agent_contributions': {a: labels['agents'][a]['observed']['contribution'] for a in members},
             'last_observed_s': labels['evidence']['last_observed_s']}
    return Evaluation({'success': 'yes', 'failure': 'no'}.get(status, 'unknown'), facts, frames)


def corresponding_groups(template, trajectory):
    matches = []
    for ga, a in sorted(template["group_skeletons"].items()):
        members = set(a["members"])
        exact = [(gb, b) for gb, b in trajectory["group_skeletons"].items() if set(b["members"]) == members]
        choices = exact or [(gb, b) for gb, b in trajectory["group_skeletons"].items() if members & set(b["members"])]
        for gb, b in sorted(choices):
            common = sorted(members & set(b["members"]))
            scoped = deepcopy(a)
            scoped["members"] = common
            scoped["agent_ids"] = [agent for agent in a["agent_ids"] if agent in common]
            scoped["references"] = {agent: a["references"][agent] for agent in common}
            scoped["exclusion_policy"] = {agent: a["exclusion_policy"][agent] for agent in common}
            matches.append({"template_group_id": ga, "trajectory_group_id": gb,
                            "membership_match": "exact" if exact else "intersection",
                            "template_members": sorted(members), "trajectory_members": sorted(b["members"]),
                            "evaluated_members": common, "parameters": scoped})
    return matches


def cross_report(attempt):
    attempt = Path(attempt)
    # New labels use role-level exclusions, not the obsolete universal 960-cell gate.
    first_label = next(attempt.glob("**/labels.json"), None)
    if first_label is not None and read_json(first_label).get("evidence", {}).get("criteria_version") == "criteria/0.7-r1":
        from scripts.cross_v07_m1 import criteria_cross_report
        return criteria_cross_report(attempt)
    descriptors = [d for d in read_json(INFRA_ATTEMPT / "private_skeleton_descriptors.json")
                   if d["subset"] == "regular" and not d.get("diagnostic_only", False)]
    records = {r["episode_id"]: r for r in read_json(attempt / "episode_records.json")
               if not r.get("diagnostic_only", False) and not r.get("aborted", False)}
    slots = {}
    for d in descriptors:
        slots.setdefault((d["family_id"], d["common_draw"]["slot"]), {})[d["base_intent"]] = d
    def generated_pair(d):
        pair = [records.get(f"{d['skeleton_id']}_{mode}", {}) for mode in MODES]
        return all(r.get("state") == "generated" and r.get("quality_valid") is True
                   and r.get("audit_passed") is True and r.get("task_result") == 'success' for r in pair)
    @lru_cache(maxsize=2)
    def trajectory(path):
        directory = attempt / path
        with np.load(directory / "truth_10hz.npz", allow_pickle=False) as loaded:
            run = {key: loaded[key].copy() for key in ("time_us", "p", "v")}
            run["agent_ids"] = loaded["agent_ids"].tolist()
        run["execution_status"] = read_json(directory / "source.json")["execution_status"]
        return exported_evidence(run), read_json(directory / "public_scene.json")
    rows, affirmative = [], []
    for (family, slot), intents in sorted(slots.items()):
        for ia in INTENTS:
            for ib in INTENTS:
                if ia == ib:
                    continue
                a, b = intents[ia], intents[ib]
                available = generated_pair(a) and generated_pair(b)
                if available:
                    template = read_json(attempt / a["skeleton_id"] / "skeleton.json")
                    target = read_json(attempt / b["skeleton_id"] / "skeleton.json")
                    matches = corresponding_groups(template, target)
                for ma in MODES:
                    for mb in MODES:
                        row = {"family_id": family, "common_slot": slot, "template_intent": ia, "trajectory_intent": ib,
                               "template_episode_id": f"{a['skeleton_id']}_{ma}", "trajectory_episode_id": f"{b['skeleton_id']}_{mb}"}
                        if not available:
                            rows.append({**row, "status": "not_run", "verdict": None,
                                         "reason": {"template_pair_generated": generated_pair(a), "trajectory_pair_generated": generated_pair(b)},
                                         "group_checks": []})
                            continue
                        evidence, scene = trajectory(records[row["trajectory_episode_id"]]["path"])
                        checks = []
                        for match in matches:
                            scoped = match["parameters"]
                            result = evaluate(detailed_group_evaluator, scene, scoped, evidence)
                            item = {key: value for key, value in match.items() if key != "parameters"}
                            item.update(verdict=result.verdict, facts=result.facts, event_frames=result.event_frames,
                                        template_role=scoped["role"], execution_method=scoped["execution_method"],
                                        target_id=scoped["target_id"])
                            checks.append(item)
                            if result.verdict == "yes":
                                affirmative.append({**row, **item,
                                                    "trigger": "all evaluated member contributions and all template group conditions true"})
                        verdicts = [item["verdict"] for item in checks]
                        verdict = "no" if "no" in verdicts else "unknown" if not verdicts or "unknown" in verdicts else "yes"
                        # Group-level yes witnesses are retained as requested;
                        # they need not establish a whole-cluster base intent.
                        rows.append({**row, "status": "FAIL" if "yes" in verdicts else "PASS", "verdict": verdict,
                                     "group_checks": checks, "any_group_affirmative": "yes" in verdicts})
    expected = len(slots) * len(INTENTS) * (len(INTENTS) - 1) * len(MODES) ** 2
    if len(rows) != expected or expected != 960:
        raise ValueError(f"Registered cross-check grid is {len(rows)}, expected 960")
    counts = {state: sum(row["status"] == state for row in rows) for state in ("PASS", "FAIL", "not_run")}
    return {"scope": "same family and common slot, directed different intents, both A and B timing variants",
            "expected_items": expected, "counts": counts, "status": "FAIL" if affirmative else "INCOMPLETE" if counts["not_run"] else "PASS",
            "availability_rule": "both timing episodes generated with valid quality, passed audit and successful task results; failed/absent A or B skeleton pairs count as not_run",
            "group_rule": "exact member set; otherwise every nonempty intersection is evaluated and explicitly identified",
            "acceptance_rule": "each group-level yes is listed as an acceptance failure; partial role overlap does not establish the entire base intent",
            "affirmative_group_count": len(affirmative), "affirmative_witnesses": affirmative, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempt", type=Path)
    args = parser.parse_args()
    report = cross_report(args.attempt)
    save_json(args.attempt / "cross_negation.json", report)
    print({key: report.get(key) for key in ("expected_items", "counts", "status", "affirmative_group_count")})


if __name__ == "__main__":
    main()
