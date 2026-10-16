"""Read-only full M3b acceptance, approach/style distributions and stop evidence."""
from collections import defaultdict,Counter
from pathlib import Path
import argparse
import json
import sys
import numpy as np
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from scripts.run_v07_m3_checks import EVIDENCE
from scripts.run_v07_m3_trial import atomic,frozen_check
from scripts.run_v07_s2_expansion import descriptor_jobs
from scripts.summarize_v07_m3 import observed_timing,distribution
from scripts.m3b_diagnostics import approach_rows,proposed_directions,round_evidence,locate_pair,groups
from task_v07.io import read_json,sha
from task_v07.expansion.views import _paired,make_views
from task_v07.expansion.solo_spacing import minimum_spacing
from task_v07.expansion.contracts import P0ContractError


def pool_path(root):
    return root/("candidate_search.json" if (root/"candidate_search.json").exists() else "candidate_pool.json")


def selected_retreat_diagnostics(sk):
    """Actual selected-plan direction choices; no inferred zero for absent provenance."""
    rows=[]
    for gid,group in groups(sk).items():
        selected=group.get("geometry_provenance",{}).get("retreat_by_agent",{})
        for agent,ref in group["references"].items():
            choice=selected.get(agent)
            rows.append({"group_id":gid,"agent_id":agent,"role":group["role"],
                "execution_method":group["execution_method"],
                "retreat_required":bool(ref.get("retreat_required",group["role"]!="intrusion")),
                "rotation_deg":None if choice is None else choice["rotation_deg"],
                "retreat_choice":choice,"source":"selected_skeleton.json/group_skeletons/geometry_provenance/retreat_by_agent",
                "missing_reason":None if choice is not None else "intrusion_has_no_retreat" if group["role"]=="intrusion" else "rotation_not_recorded_for_this_backend_path"})
    return rows


def q2_summary(reg,scenes,*,source_name="m3b_q2.json",output_name="m3b_q2_diagnostics.json"):
    raw=read_json(EVIDENCE/source_name); out=Path(raw["attempt"]); results=[]; approaches=[]; directions=[]; retreats=[]
    by_id={r["skeleton_id"]:r for r in raw["rows"]}
    for fixed in reg["selected"]:
        sid=fixed["skeleton_id"]; root=out/sid
        row={**fixed,**by_id.get(sid,raw.get("unfinished_evidence",{}).get(sid,{"status":"not_started"}))}
        if (root/"selected_skeleton.json").exists():
            sk=read_json(root/"selected_skeleton.json")
            approaches.extend({**fixed,**r} for r in approach_rows(scenes[sid],sk))
            retreats.extend({**fixed,**r} for r in selected_retreat_diagnostics(sk))
        if pool_path(root).exists():
            pool=read_json(pool_path(root)); direction=proposed_directions(pool)
            directions.extend({**fixed,"group_id":gid,**value} for gid,value in direction.items())
            row["group_candidate_counts"]={gid:m["feasible_candidates"] for gid,m in pool.get("group_search_metrics",{}).items()}
            row["group_planning_wall_s"]={gid:m["wall_s"] for gid,m in pool.get("group_search_metrics",{}).items()}
            row["combination_rejections"]=pool.get("combination_rejection_reasons")
            # Full closest proposal retained in its attempt; compact report keeps exact issues.
            if row.get("status")!="PASS":
                detailed=Counter()
                def collect(value):
                    if isinstance(value,dict):
                        for k in ("code","reason"):
                            if isinstance(value.get(k),str): detailed[value[k]]+=1
                        for child in value.values(): collect(child)
                    elif isinstance(value,list):
                        for child in value: collect(child)
                for record in pool.get("candidates",[]): collect(record.get("rejection"))
                row["nested_rejection_reason_counts"]=dict(detailed)
        results.append(row)
    grouped={}
    for key in sorted({(r["intent"],r["approach_mode"]) for r in reg["selected"]}):
        members=[r for r in approaches if (r["intent"],r["approach_mode"])==key]
        draws=[r for r in directions if (r["intent"],r["approach_mode"])==key]
        proposed=[x for r in draws for x in r["proposed"]]; accepted=[x for r in draws for x in r["accepted"]]
        grouped["/".join(key)]={"members":len(members),
            **{k:distribution([r[k] for r in members if r[k] is not None]) for k in ("approach_length_m","detour_ratio","ingress_relative_to_start_bearing_deg")},
            "proposed_direction_30deg_bins":np.histogram(proposed,bins=np.arange(0,361,30))[0].tolist(),
            "whole_route_accepted_direction_30deg_bins":np.histogram(accepted,bins=np.arange(0,361,30))[0].tolist(),
            "accepted_original_proposed_direction_30deg_bins":np.histogram([x for r in draws for x in r["accepted_original_proposal"]],bins=np.arange(0,361,30))[0].tolist(),
            "proposed_count":len(proposed),"accepted_count":len(accepted)}
    retreat_by_role={}
    for role in sorted({r["role"] for r in retreats}):
        values=[r for r in retreats if r["role"]==role]
        choices=[r["rotation_deg"] for r in values if r["rotation_deg"] is not None]
        retreat_by_role[role]={"selected_groups":len({(r["skeleton_id"],r["group_id"]) for r in values}),
            "selected_member_records":len(values),"retreat_required_members":sum(r["retreat_required"] for r in values),
            "rotation_recorded_members":len(choices),"rotation_deg_counts":dict(sorted(Counter(str(x) for x in choices).items())),
            "rotation_deg_distribution":distribution(choices),
            "method":"One selected eligible episode plan per nonempty skeleton; each physical group member counted once, not all proposals or episode-combination occurrences. Missing provenance is not treated as zero rotation."}
    result={**{k:v for k,v in raw.items() if k not in ("rows","unfinished_evidence")},"rows":results,
        "selected_plan_approach_members":approaches,"directions_by_group":directions,"by_intent_specified_approach":grouped,
        "selected_plan_retreat_members":retreats,"selected_retreat_by_role":retreat_by_role,
        "method":"selected eligible candidate 0; exact polyline start-to-first-warning length; incoming heading vs vector from start to target center; local shape direction proposals vs whole-route accepted actual shape direction (patrol feasible-arc start may differ, original proposal also retained); empty cells explicitly included",
        "diagnostics_are_gates":False}
    atomic(EVIDENCE/output_name,result)
    return result


def q3_summary(reg,scenes):
    raw=read_json(EVIDENCE/"m3b_trial.json"); out=Path(raw["attempt"]); all_rows=raw["rows"]
    results=[]; styles=[]; timing_checks=[]; ingress=[]
    for fixed in (r for r in reg["selected"] if r["q3"]):
        sid=fixed["skeleton_id"]; root=out/sid; records=[r for r in all_rows if r["skeleton_id"]==sid]
        rounds=[round_evidence(scenes[sid],p) for p in sorted(root.glob("geometry_[0-9][0-9]"))
                if p.is_dir() and (p/"rehearsal.json").exists()]
        search=read_json(pool_path(root)) if pool_path(root).exists() else {}
        row={**fixed,"strict_pair":_paired(records),"rounds":rounds,"round_count":len(rounds),
            "closest_round":min(rounds,key=lambda r:r["closest_score"])["round"] if rounds else None,
            "status":"not_started" if not records and not rounds else "passed" if _paired(records) else "rejected",
            "attempted_proposals":search.get("attempted_candidates"),
            "planning_wall_s":sum(m["wall_s"] for m in search.get("group_search_metrics",{}).values())+search.get("combination_search",{}).get("wall_s",0.),
            "directions_by_group":proposed_directions(search),"episodes":[]}
        if (root/"skeleton.json").exists():
            sk=read_json(root/"skeleton.json")
            ingress.extend({**fixed,**r} for r in approach_rows(scenes[sid],sk))
        for record in records:
            if not record.get("path"): continue
            directory=out/record["path"]; labels=read_json(directory/"labels.json")
            sk=read_json(root/"skeleton.json")
            with np.load(directory/"truth_10hz.npz",allow_pickle=False) as truth:
                times=truth["time_us"]; positions=truth["p"]; ids=truth["agent_ids"].tolist()
            spacing=minimum_spacing(times,positions,ids)
            if abs(spacing["minimum_m"]-record["minimum_separation_m"])>1e-8: raise P0ContractError("Truth spacing disagrees with published result")
            timing={gid:observed_timing(labels,gid,record["mode"]) for gid in labels["task_groups"]}
            timing_checks.extend({"episode_id":record["episode_id"],"group_id":gid,**value} for gid,value in timing.items())
            audit=read_json(directory/"independent_exact_audit.json")
            if (audit["status"]=="PASS")!=record["audit_passed"]: raise P0ContractError("Audit receipt mismatch")
            episode={k:record[k] for k in ("episode_id","mode","task_result","quality_valid","execution_status","all_groups_complete",
                "rehearsal_inconsistency","solo_overlay_prediction_error","measured_approach_by_group")}
            episode.update(minimum_separation_m=spacing["minimum_m"],closest_pair=locate_pair(sk,positions,ids,spacing["closest_pair"]),
                audit_status=audit["status"],coordination_pass=all(r["status"]=="PASS" for r in timing.values()),
                truth_sha256=sha(directory/"truth_10hz.npz"),labels_sha256=sha(directory/"labels.json"),
                observed_heading_by_group_deg={gid:value["observed"]["approach_span_deg"] for gid,value in labels["task_groups"].items()})
            row["episodes"].append(episode)
            for a,value in labels["agents"].items():
                c=value["observed"]["contribution"]
                styles.append({"episode_id":record["episode_id"],"skeleton_id":sid,"intent":fixed["intent"],"approach_mode":fixed["approach_mode"],
                    "agent_id":a,"dwell":c["dwell"],"revisit":c["revisit"],"work_reversal_count":c.get("work_reversal_count"),
                    "work_reversal_start_frames":c.get("work_reversal_start_frames"),"quality_valid":record["quality_valid"]})
        row["observed_minimum_separation_m"]=min((e["minimum_separation_m"] for e in row["episodes"]),default=None)
        row["multi_max_pairwise_ingress_heading_deg"]=max((v for e in row["episodes"] for v in e["observed_heading_by_group_deg"].values() if v is not None),default=None) if fixed["approach_mode"]=="multi_direction" else None
        results.append(row)
    by_intent={}
    for intent in sorted({r["intent"] for r in styles}):
        sample=[r for r in styles if r["intent"]==intent]; episodes=[e for r in results if r["intent"]==intent for e in r["episodes"]]
        approach=[(r["approach_mode"],m) for r in results if r["intent"]==intent for e in r["episodes"] for m in e["measured_approach_by_group"].values()]
        by_intent[intent]={"member_episode_count":len(sample),"episode_count":len(episodes),"quality_valid_episodes":sum(e["quality_valid"] for e in episodes),
            "dwell_detected":sum(s["dwell"]["detected"] for s in sample),"dwell_duration_when_detected_s":distribution([s["dwell"]["total_duration_s"] for s in sample if s["dwell"]["detected"]]),
            "revisit_detected":sum(s["revisit"]["detected"] for s in sample),"reversal_count":distribution([s["work_reversal_count"] or 0 for s in sample]),
            "approach_consistent_groups":sum(a==b for a,b in approach),"approach_group_denominator":len(approach),
            "joint_min_separation_m":distribution([e["minimum_separation_m"] for e in episodes]),"quality_threshold_m":2.}
    views=make_views(all_rows); passed=raw["status"]=="completed" and len(results)==10 and all(r["strict_pair"] for r in results)
    passed &= all(t["status"]=="PASS" for t in timing_checks)
    passed &= all(e["rehearsal_inconsistency"]["agent_count"]==0 and e["rehearsal_inconsistency"]["condition_difference_agent_count"]==0 for r in results for e in r["episodes"])
    result={"status":"PASS" if passed else "NOT_PASSED","raw_status":raw["status"],"attempt":str(out),"rows":results,
        "wall_s":raw["wall_s"],"stages":raw["stages"],"strict_pairs":sum(r["strict_pair"] for r in results),"requested_pairs":10,
        "observed_group_checks":timing_checks,"selected_plan_approach_members":ingress,"style_diagnostics":styles,"style_by_intent":by_intent,
        "feint_dwell_counterexamples":[s for s in styles if s["intent"]=="feint" and s["dwell"]["detected"]],
        "multi_direction_minima":[{"skeleton_id":r["skeleton_id"],"episodes":[{"episode_id":e["episode_id"],"minimum_m":e["minimum_separation_m"],"closest_pair":e["closest_pair"]} for e in r["episodes"]]} for r in results if r["approach_mode"]=="multi_direction"],
        "view_counts":views["counts"],"family_balance":views["family_balance"],"frozen_check":frozen_check(reg)}
    atomic(EVIDENCE/"m3b_acceptance.json",result); atomic(out/"m3b_acceptance.json",result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix-q2",action="store_true",help="Only summarize repair Q2 into new evidence names; never summarize or run Q3")
    args=parser.parse_args()
    reg=read_json(EVIDENCE/"m3b_inputs.json"); frozen_check(reg)
    jobs=descriptor_jobs(Path(reg["descriptor_attempt"]),[r["skeleton_id"] for r in reg["selected"]],EVIDENCE)
    scenes={j["descriptor"]["skeleton_id"]:j["scene"] for j in jobs}
    q2=q2_summary(reg,scenes,**({"source_name":"m3b_fix_q2.json","output_name":"m3b_fix_q2_diagnostics.json"} if args.fix_q2 else {})); print(json.dumps({"q2":q2["status"],"gate":q2["q2_gate"]},ensure_ascii=False))
    if not args.fix_q2 and (EVIDENCE/"m3b_trial.json").exists():
        q3=q3_summary(reg,scenes); print(json.dumps({"q3":q3["status"],"strict_pairs":q3["strict_pairs"]},ensure_ascii=False))


if __name__=="__main__": main()
