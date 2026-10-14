"""Evaluator callback for evaluation.truncation_check / cross_negation.

The private check template is a task-group skeleton; the verdict is that group's
result from task_v07.labels.measure on the supplied evidence only. Nothing is
copied from the template's planned values into facts.
"""
import numpy as np

from task_v07.labels import measure
from .evaluation import Evaluation


def group_evaluator(scene, template, evidence):
    members = list(template["members"])
    columns = [list(evidence.agent_ids).index(a) for a in members]
    run = {"agent_ids": members, "time_us": np.array(evidence.time_us),
           "p": np.array(evidence.p)[:, columns], "v": np.array(evidence.v)[:, columns],
           "execution_status": "completed" if evidence.complete else "evidence_prefix"}
    labels, _ = measure(scene, template, run, "unassigned_measurement")
    group = labels["task_groups"][template["group_id"]]
    status = group["result"]["status"]
    verdict = {"success": "yes", "failure": "no"}.get(status, "unknown")
    frames = {a: labels["agents"][a]["observed"]["core_event"]["frame_index"] for a in members}
    facts = {"group_result": status, "group_conditions": group["result"]["conditions"],
             "agent_results": {a: labels["agents"][a]["result"]["status"] for a in members},
             "last_observed_s": labels["evidence"]["last_observed_s"]}
    return Evaluation(verdict, facts, frames, f"group result {status}")
