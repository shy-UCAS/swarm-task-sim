"""Deterministic index-only dataset views; pending work is never a success."""
from collections import Counter, defaultdict
from pathlib import PurePosixPath

from .contracts import P0ContractError
from .sampling import INTENTS
from task_v07.planning import seed_for

MODES = ("synchronous", "sequential")
STATES = ("pending", "generated", "infeasible", "generation_error")


def _usable(row):
    return (row["state"] == "generated" and row.get("quality_valid") is True
            and row.get("audit_passed") is True and row.get("task_result") == "success")


def _paired(rows):
    if len(rows) != 2 or {r["mode"] for r in rows} != set(MODES) or not all(_usable(r) for r in rows):
        return False
    if not all(r.get("coordination_by_group") and all(v == r["mode"] for v in r["coordination_by_group"].values()) for r in rows):
        return False
    if set(rows[0]["coordination_by_group"]) != set(rows[1]["coordination_by_group"]):
        raise P0ContractError("Paired episodes have different group identities")
    keys = ("condition_digest", "agent_ids", "scene_digest")
    if any(not rows[0].get(k) or rows[0][k] != rows[1].get(k) for k in keys):
        raise P0ContractError("Claimed successful pair changed non-time conditions")
    return True


def make_views(records, seed=0):
    records = [r for r in records if not r.get("diagnostic_only", False)]
    ids = [r["episode_id"] for r in records]
    if len(ids) != len(set(ids)):
        raise P0ContractError("Duplicate episode ID")
    for row in records:
        if row["intent"] not in INTENTS or row["mode"] not in MODES or row["state"] not in STATES:
            raise ValueError("Unknown record category")
        path = row.get("path")
        if path is not None:
            p = PurePosixPath(path)
            if p.is_absolute() or ".." in p.parts or "\\" in path or ":" in path:
                raise P0ContractError("View paths must stay relative to the attempt")
        if row["state"] == "generated" and not path:
            raise P0ContractError("Generated episode has no artifact path")
    by_skeleton = defaultdict(list)
    for row in records:
        if not row.get("aborted", False):
            by_skeleton[(row["family_id"], row["skeleton_id"])].append(row)
    pairs = defaultdict(lambda: defaultdict(list))
    for (family, skeleton), rows in by_skeleton.items():
        if len({r["intent"] for r in rows}) != 1:
            raise P0ContractError("One skeleton assigned multiple base intents")
        if len(rows) > 2 or len({r["mode"] for r in rows}) != len(rows):
            raise P0ContractError("Duplicate timing variant")
        if _paired(rows):
            pairs[family][rows[0]["intent"]].append((skeleton, rows))
    primary_ids = set()
    balance = []
    for family in sorted({r["family_id"] for r in records}):
        counts = {intent: len(pairs[family][intent]) for intent in INTENTS}
        limit = min(counts.values())
        balance.append({"family_id": family, "successful_pairs_by_intent": counts, "pairs_per_intent": limit})
        for intent in INTENTS:
            ordered = sorted(pairs[family][intent], key=lambda pair: (seed_for(seed, pair[0]), pair[0]))
            for _, rows in ordered[:limit]:
                primary_ids.update(r["episode_id"] for r in rows)
    views = {k: [] for k in ("primary", "extended", "aborted", "failed", "pending")}
    for row in sorted(records, key=lambda r: r["episode_id"]):
        if row["state"] == "pending":
            key = "pending"
        elif row.get("aborted", False):
            key = "aborted"
        elif row["episode_id"] in primary_ids:
            key = "primary"
        elif _usable(row):
            key = "extended"
        else:
            key = "failed"
        views[key].append({k: row.get(k) for k in ("episode_id", "family_id", "skeleton_id", "intent", "mode",
                                                   "path", "state", "reason", "task_result")})
    return {"schema_version": "traj2language.views/0.7-s2-infrastructure", "index_only": True,
            "views": views, "family_balance": balance, "counts": {k: len(v) for k, v in views.items()}}


def diagnostic_summary(descriptors, records):
    descriptors = [d for d in descriptors if not d.get("diagnostic_only", False)]
    records = [r for r in records if not r.get("diagnostic_only", False)]
    regular = [d for d in descriptors if d["subset"] == "regular"]
    distributions = {}
    for intent in INTENTS:
        chosen = [d for d in regular if d["base_intent"] == intent]
        distributions[intent] = {
            "candidate_count": len(chosen),
            "approach_mode": dict(sorted(Counter(d["common_draw"]["approach_mode"] for d in chosen).items())),
            "initial_unit_count": dict(sorted(Counter(str(d["common_draw"]["actual_unit_count"]) for d in chosen).items())),
            "merged_group_count": dict(sorted(Counter(str(len(d["task_groups"])) for d in chosen).items())),
            "target_set_size": dict(sorted(Counter(str(len({g["target_id"] for g in d["task_groups"]})) for d in chosen).items()))}
    generated = [r for r in records if r["state"] == "generated" and not r.get("aborted", False)]
    classified = [r for r in generated if r.get("coordination_by_group") and
                  all(v in ("synchronous", "sequential", "other") for v in r["coordination_by_group"].values())]
    failed = [r for r in generated if r.get("task_result") == "failure"]
    return {"distributions_by_intent": distributions,
            "state_counts": dict(Counter(r["state"] for r in records)),
            "execution_metrics": {
                "regular_episode_requests": sum(not r.get("aborted", False) for r in records),
                "abort_episode_requests": sum(r.get("aborted", False) for r in records),
                "generated_regular_episodes": len(generated),
                "nondesigned_failure_fraction": len(failed) / len(generated) if generated else None,
                "timing_classifiable_count": len(classified),
                "timing_agreement_fraction": (sum(all(v == r["mode"] for v in r["coordination_by_group"].values())
                                                   for r in classified) / len(classified)) if classified else None,
                "missing_reason": "role planners/evaluators not supplied" if not generated else None},
            "rejection_reason_counts": dict(Counter(r.get("reason") or "unspecified" for r in records
                                                   if r["state"] in ("infeasible", "generation_error")))}
