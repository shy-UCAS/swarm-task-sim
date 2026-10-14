"""Role-neutral evaluator hooks and honest pending/truncation/cross-negation reports."""
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

import numpy as np

from task_v07.labels import validate_grid
from .contracts import P0ContractError
from .sampling import INTENTS


@dataclass(frozen=True)
class Evidence:
    agent_ids: tuple
    time_us: np.ndarray
    p: np.ndarray
    v: np.ndarray
    complete: bool


def exported_evidence(run, cutoff_s=None):
    ids = tuple(run["agent_ids"])
    t, p, v = (np.asarray(run[k]) for k in ("time_us", "p", "v"))
    validate_grid(t, p, v, ids)
    if cutoff_s is not None and (not np.isfinite(cutoff_s) or cutoff_s <= 0):
        raise ValueError("Positive finite half-open cutoff required")
    select = np.ones(len(t), bool) if cutoff_s is None else t < round(cutoff_s * 1e6)
    if not select.any():
        raise ValueError("Empty evidence prefix")
    arrays = [a[select].copy() for a in (t, p, v)]
    for a in arrays:
        a.flags.writeable = False
    complete = cutoff_s is None and run.get("execution_status") in ("completed", "timeout")
    return Evidence(ids, *arrays, complete)


@dataclass(frozen=True)
class Evaluation:
    verdict: str
    facts: dict
    event_frames: dict
    reason: str = ""


Evaluator = Callable[[dict, dict, Evidence], Evaluation]


def evaluate(callback, scene, template, evidence):
    if callback is None:
        return Evaluation("unknown", {}, {}, "evaluator_not_implemented")
    result = callback(deepcopy(scene), deepcopy(template), evidence)
    if not isinstance(result, Evaluation) or result.verdict not in ("yes", "no", "unknown"):
        raise P0ContractError("Evaluator must return yes/no/unknown with separate facts")
    for frame in result.event_frames.values():
        if frame is not None and (isinstance(frame, bool) or not isinstance(frame, (int, np.integer))
                                  or not 0 <= frame < len(evidence.time_us)):
            raise P0ContractError("Evaluator cites an unobserved/future event frame")
    return result


def truncation_check(callback, scene, template, run, cutoff_s):
    """Caller supplies the midpoint of the measured work interval, not a plan."""
    if callback is None:
        return {"status": "not_run", "reason": "evaluator_not_implemented", "prefix_verdict": "unknown"}
    full = evaluate(callback, scene, template, exported_evidence(run))
    prefix = evaluate(callback, scene, template, exported_evidence(run, cutoff_s))
    return {"status": "FAIL" if prefix.verdict == "yes" else "PASS", "full_verdict": full.verdict,
            "prefix_verdict": prefix.verdict, "cutoff_s": cutoff_s, "protocol": "offline_half_work_truncation",
            "prefix_event_frames": prefix.event_frames}


def cross_negation(templates, episodes, evaluators):
    """A templates judge B evidence. B's labels/intent are never passed to callback.

    Evidence role overlap is not base-intent exclusivity. Missing callbacks/runs
    are NOT counted as verified negative results.
    """
    rows = []
    for template in sorted(templates, key=lambda x: x["template_id"]):
        for episode in sorted(episodes, key=lambda x: x["episode_id"]):
            if template["family_id"] != episode["family_id"] or template["intent"] == episode["intent"]:
                continue
            callback = evaluators.get(template["intent"])
            pending = callback is None or episode.get("run") is None or template.get("parameters") is None
            result = Evaluation("unknown", {}, {}, "missing_template_evaluator_or_trajectory") if pending else evaluate(
                callback, episode["scene"], template["parameters"], exported_evidence(episode["run"]))
            rows.append({"family_id": template["family_id"], "template_id": template["template_id"],
                         "template_intent": template["intent"], "episode_id": episode["episode_id"],
                         "trajectory_intent": episode["intent"], "verdict": result.verdict,
                         "status": "not_run" if pending else "FAIL" if result.verdict == "yes" else "PASS",
                         "reason": result.reason, "facts": result.facts})
    combinations = []
    for a in INTENTS:
        for b in INTENTS:
            if a == b:
                continue
            chosen = [r for r in rows if r["template_intent"] == a and r["trajectory_intent"] == b]
            combinations.append({"template_intent": a, "trajectory_intent": b,
                                 "planned": len(chosen), "tested": sum(r["status"] != "not_run" for r in chosen),
                                 "unexpected_yes": sum(r["status"] == "FAIL" for r in chosen),
                                 "no": sum(r["status"] == "PASS" and r["verdict"] == "no" for r in chosen),
                                 "unknown_tested": sum(r["status"] == "PASS" and r["verdict"] == "unknown" for r in chosen),
                                 "pending": sum(r["status"] == "not_run" for r in chosen)})
    return {"combinations": combinations, "rows": rows,
            "status": "FAIL" if any(r["status"] == "FAIL" for r in rows) else
                      "pending" if not rows or any(r["status"] == "not_run" for r in rows) else "PASS"}
