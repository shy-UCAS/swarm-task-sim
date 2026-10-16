"""Read-only M3a strict pairs, independent observed timing and geometry diagnostics."""
from collections import defaultdict
from decimal import Decimal
from itertools import combinations
from pathlib import Path
import sys
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.run_v07_m3_checks import EVIDENCE, integration_evidence
from scripts.run_v07_m3_trial import frozen_check, atomic
from task_v07.io import read_json, sha
from task_v07.expansion.views import _paired, make_views
from task_v07.expansion.contracts import P0ContractError


def distribution(values):
    return {"count": len(values), "minimum": min(values) if values else None,
            "median": float(np.median(values)) if values else None, "maximum": max(values) if values else None}


def shape_statistics(draws):
    return {"draw_count": len(draws), "direction_deg": distribution([d["direction_deg"] for d in draws]),
            "bend_count": sum(d["bend"] for d in draws),
            "bend_angle_deg_when_present": distribution([d["bend_angle_deg"] for d in draws if d["bend"]]),
            "chord_quantile": distribution([s["chord_quantile"] for d in draws for s in d["split_draws"]])}


def q2_parameter_diagnostics():
    q2 = read_json(EVIDENCE/"m3a_q2.json"); out = Path(q2["attempt"]); rows = []
    for skeleton in q2["rows"]:
        sid = skeleton["skeleton_id"]
        pool = read_json(out/sid/"candidate_pool.json")
        selected = read_json(out/sid/"selected_skeleton.json")
        for gid in pool["group_attempt_counts"]:
            records = [r for r in pool["candidates"] if r["group_id"] == gid]
            proposed = []; accepted = []
            for record in records:
                shape = record["draws_by_group"][gid].get("shape")
                if shape:
                    proposed.extend(r["draw"] for r in shape["rejected_shape_attempts"])
                    proposed.append(shape)
                    if record["reason"] is None: accepted.append(shape)
                elif record["rejection"]:
                    proposed.extend(r["draw"] for r in record["rejection"]["geometric_evidence"] if "draw" in r)
            rows.append({"skeleton_id": sid, "group_id": gid, "group_proposals": len(records),
                         "accepted_group_proposals": len(accepted), "proposed_shapes_including_local_retries": shape_statistics(proposed),
                         "accepted_group_shapes": shape_statistics(accepted),
                         "selected_connection_parameters": selected["group_skeletons"][gid]["geometry_provenance"]})
    return {"source_attempt": str(out), "scope": "Proposed local shape draws versus whole-route-accepted group proposals; connection parameters of selected plans",
            "acceptance_bias_is_not_claimed_unbiased": True, "rows": rows}


def observed_timing(labels, gid, mode):
    group = labels["task_groups"][gid]
    ids = group["assigned"]["members"]
    times = {a: labels["agents"][a]["observed"]["core_event"]["t_s"] for a in ids}
    if any(t is None for t in times.values()):
        return {"status": "FAIL", "reason": "missing_observed_event", "times_s": times}
    values = {a: Decimal(str(t)) for a, t in times.items()}
    ordered = sorted(ids, key=lambda a: (values[a], a)); batches = [[ordered[0]]]
    for a in ordered[1:]:
        if values[a]-values[batches[-1][-1]] > Decimal(20): batches.append([])
        batches[-1].append(a)
    spans = [max(values[a] for a in b)-min(values[a] for a in b) for b in batches]
    gaps = [min(values[a] for a in right)-max(values[a] for a in left) for left, right in zip(batches, batches[1:])]
    total = max(values.values())-min(values.values())
    category = "synchronous" if total <= Decimal(10) else "sequential" if len(batches)>1 and all(s<=Decimal(10) for s in spans) else "other"
    published = group["observed"]["coordination"]
    actual_members = [sorted(b) for b in batches]
    if category != published["classification"] or actual_members != [b["members"] for b in published["batches"]]:
        raise P0ContractError("Independent observed event grouping contradicts labels")
    assigned = group["assigned"]["planned_batches"]
    plan_members = [sorted(a for a in ids if assigned[a] == b) for b in sorted(set(assigned.values()))]
    ordered_match = actual_members == plan_members
    return {"status": "PASS" if category == mode and ordered_match else "FAIL", "times_s": times,
            "classification": category, "total_span_s": float(total), "batch_spans_s": [float(s) for s in spans],
            "inter_batch_gaps_s": [float(s) for s in gaps], "actual_batches": actual_members,
            "assigned_batches": plan_members, "batch_members_and_order_match": ordered_match}


def main():
    raw = read_json(EVIDENCE/"m3a_trial.json"); out = Path(raw["attempt"])
    input_registration = read_json(EVIDENCE/"m3_inputs.json")
    frozen = frozen_check(input_registration)
    rows = raw["rows"]; by_skeleton = defaultdict(list)
    for row in rows: by_skeleton[row["skeleton_id"]].append(row)
    summaries = []; group_results = []; styles = []
    for requested in [r for r in input_registration["selected"] if r["q3"]]:
        sid = requested["skeleton_id"]; root = out/sid; records = by_skeleton[sid]
        search_path = root/"candidate_search.json"
        if not search_path.exists(): search_path = root/"candidate_pool.json"
        search = read_json(search_path) if search_path.exists() else {}
        history = read_json(root/"geometry_history.json") if (root/"geometry_history.json").exists() else []
        if not history:
            history = [read_json(p/"planning_rejection.json") for p in sorted(root.glob("geometry_[0-9][0-9]")) if (p/"planning_rejection.json").exists()]
        paired = _paired(records)
        skeleton_row = {"skeleton_id": sid, "approach_mode": requested["approach_mode"], "strict_pair": paired,
                        "planning_wall_s": sum(v["wall_s"] for v in search.get("group_search_metrics", {}).values())+search.get("combination_search", {}).get("wall_s", 0.),
                        "attempted_proposals": search.get("attempted_candidates"),
                        "solo_flights": search.get("solo_flights_run", 0), "round_count": search.get("actual_single_agent_calibration_rounds", 0),
                        "rounds": [{"variant": h.get("geometry_variant"), "candidate_index": h.get("candidate_index"),
                                    "category": h.get("category"), "detail": h.get("detail"),
                                    "failures": h.get("failed_members_and_conditions", [])} for h in history],
                        "episodes": [], "observed_minimum_separation_m": None,
                        "multi_max_pairwise_ingress_heading_deg": None}
        for row in records:
            if not row.get("path"): continue
            directory = out/row["path"]; labels = read_json(directory/"labels.json")
            timing = {gid: observed_timing(labels, gid, row["mode"]) for gid in labels["task_groups"]}
            group_results.extend({"episode_id": row["episode_id"], "group_id": gid, **value} for gid, value in timing.items())
            with np.load(directory/"truth_10hz.npz", allow_pickle=False) as truth:
                positions = truth["p"]
                minimum = min(float(np.linalg.norm(positions[:, i]-positions[:, j], axis=1).min())
                              for i, j in combinations(range(positions.shape[1]), 2))
            if abs(minimum-row["minimum_separation_m"]) > 1e-8:
                raise P0ContractError("Saved truth minimum separation contradicts published metric")
            angles = {gid: value["observed"]["approach_span_deg"] for gid, value in labels["task_groups"].items()}
            audit = read_json(directory/"independent_exact_audit.json")
            if (audit["status"] == "PASS") != row["audit_passed"]:
                raise P0ContractError("Independent audit receipt contradicts published audit status")
            episode = {"mode": row["mode"], "status": row["task_result"], "execution_status": row["execution_status"],
                       "quality_valid": row["quality_valid"], "all_groups_complete": row["all_groups_complete"],
                       "audit_status": audit["status"], "minimum_separation_m": minimum,
                       "observed_heading_by_group_deg": angles,
                       "coordination_pass": all(r["status"] == "PASS" for r in timing.values()),
                       "rehearsal_inconsistency": row["rehearsal_inconsistency"],
                       "solo_overlay_prediction_error": row["solo_overlay_prediction_error"],
                       "labels_sha256": sha(directory/"labels.json"), "truth_sha256": sha(directory/"truth_10hz.npz")}
            skeleton_row["episodes"].append(episode)
            for agent, value in labels["agents"].items():
                contribution = value["observed"]["contribution"]
                styles.append({"episode_id": row["episode_id"], "agent_id": agent,
                    "dwell": contribution["dwell"], "revisit": contribution["revisit"],
                    "work_reversal_count": contribution.get("work_reversal_count"),
                    "result": value["result"]["status"]})
        if skeleton_row["episodes"]:
            skeleton_row["observed_minimum_separation_m"] = min(e["minimum_separation_m"] for e in skeleton_row["episodes"])
            if requested["approach_mode"] == "multi_direction":
                skeleton_row["multi_max_pairwise_ingress_heading_deg"] = max(a for e in skeleton_row["episodes"] for a in e["observed_heading_by_group_deg"].values() if a is not None)
        summaries.append(skeleton_row)
    views = make_views(rows)
    success = raw["status"] == "completed" and len(summaries) == 2 and all(s["strict_pair"] for s in summaries)
    success &= all(r["status"] == "PASS" for r in group_results)
    success &= all(e["rehearsal_inconsistency"]["agent_count"] == 0 and e["rehearsal_inconsistency"]["condition_difference_agent_count"] == 0
                   for s in summaries for e in s["episodes"])
    result = {"status": "PASS" if success else "NOT_PASSED", "attempt": str(out), "wall_s": raw["wall_s"],
              "wall_limit_s": raw["wall_limit_s"], "strict_pairs": sum(s["strict_pair"] for s in summaries),
              "requested_pairs": 2, "rows": summaries, "frozen_check": frozen, "view_counts": views["counts"],
              "family_balance": views["family_balance"], "observed_group_checks": group_results,
              "style_diagnostics": styles,
              "style_counts": {"member_episode_count": len(styles), "dwell_detected": sum(s["dwell"]["detected"] for s in styles),
                               "revisit_detected": sum(s["revisit"]["detected"] for s in styles),
                               "work_reversal_count": sum(s["work_reversal_count"] or 0 for s in styles)},
              "method": "Independent Decimal event grouping; actual exported truth spacing; original _paired and make_views",
              "primary_note": "counts.primary is the episode count in views.primary; zero is allowed for transit-only families"}
    atomic(EVIDENCE/"m3a_geometry_parameters.json", q2_parameter_diagnostics())
    atomic(EVIDENCE/"m3a_acceptance.json", result)
    atomic(out/"m3a_acceptance.json", result)
    checks_path = EVIDENCE/"m3a_checks.json"
    if checks_path.exists():
        checks = read_json(checks_path)
        checks["actual_frozen_fastsim_integration"] = integration_evidence()
        atomic(checks_path, checks)
    print({k: result[k] for k in ("status", "strict_pairs", "view_counts", "style_counts")})
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
