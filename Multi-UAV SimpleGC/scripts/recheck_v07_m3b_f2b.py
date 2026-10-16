"""Only the registered 5024/ext_006 group_01 proposals 0..199; no simulation."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys
import time

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from scripts.run_v07_m3_checks import EVIDENCE
from scripts.run_v07_m3_trial import atomic, frozen_check
from scripts.run_v07_s2_expansion import descriptor_jobs
from task_v07.io import read_json, sha
from task_v07.unified.adapter import build_unified_pool
from task_v07.unified.spec import build_spec, proposal_seed

BASELINE="7e67fa232c1a3c2a2540dd612d85797bb56276c9"
SID="family_s12_5024cb2ccea653ae_ext_006_regular"
GID="task_group_01"
OUTPUT=EVIDENCE/"m3b_f2b_recheck.json"


def summary(records):
    stages=Counter(); reasons=Counter(); local=Counter(); issues=Counter(); passed=[]
    for r in records:
        stages[r["stage"]]+=1
        if r.get("reason"): reasons[r["reason"]]+=1
        else: passed.append(r["candidate_index"])
        shape=r.get("draws_by_group",{}).get(GID,{}).get("shape",{})
        attempts=(r.get("rejection") or {}).get("geometric_evidence",[]) if r["stage"]=="shape" else shape.get("rejected_shape_attempts",[])
        for trial in attempts:
            if isinstance(trial,dict) and trial.get("reason"): local[trial["reason"]]+=1
        for issue in r.get("whole_route_checks",{}).get("issues",[]): issues[issue["code"]]+=1
    return {"completed_proposals":len(records),"feasible_group_candidates":len(passed),"accepted_indices":passed,
        "stage_counts":dict(stages),"proposal_rejection_reasons":dict(reasons),
        "rejected_local_shape_reasons":dict(local),"whole_route_issue_counts":dict(issues)}


def main():
    reg=read_json(EVIDENCE/"m3b_inputs.json"); frozen_check(reg)
    current=read_json(EVIDENCE/"m3b_fix_q2.json"); historic=read_json(EVIDENCE/"m3b_q2.json")
    pools=[Path(r["attempt"])/SID/"candidate_pool.json" for r in (historic,current)]
    old=[r for r in read_json(pools[0])["candidates"] if r["group_id"]==GID]
    before=[r for r in read_json(pools[1])["candidates"] if r["group_id"]==GID]
    assert sorted(r["candidate_index"] for r in before)==list(range(200))
    evidence=read_json(OUTPUT)
    if evidence.get("tests",{}).get("status")!="PASS":
        raise RuntimeError("F2b tests must pass before the registered proposal rerun")
    production={p.relative_to(PROJECT).as_posix():sha(p) for root in ("task_v07","configs")
                for p in (PROJECT/root).rglob("*") if p.suffix in (".py",".json")}
    tracked=subprocess.check_output(["git","ls-files","docs/v07/evidence/m3"],cwd=PROJECT,text=True).splitlines()
    old_hashes={p:sha(PROJECT/p) for p in tracked if Path(p).name not in (OUTPUT.name,)}
    job=descriptor_jobs(Path(reg["descriptor_attempt"]),[SID],EVIDENCE)[0]
    group=next(g for g in job["descriptor"]["task_groups"] if g["group_id"]==GID)
    spec=build_spec(job["descriptor"],group)
    for r in before:
        assert r["draws_by_group"][GID]["proposal_seed"]==proposal_seed(spec,r["candidate_index"])
    start=time.perf_counter(); stamp=datetime.now(timezone.utc).isoformat(); records=[]
    def progress(record):
        records.append(record)
        if len(records)%10==0:
            evidence["fixed_proposals"]={"status":"running","started_utc":stamp,"summary":summary(records),
                "wall_s":time.perf_counter()-start,"records":records}
            atomic(OUTPUT,evidence)
            print(json.dumps({"completed":len(records),"feasible":sum(r["reason"] is None for r in records),
                              "wall_s":time.perf_counter()-start}),flush=True)
    pool,report=build_unified_pool(job["scene"],job["descriptor"],group,200,on_record=progress)
    assert len(records)==200 and records==report["records"]
    assert all(c["checks"]["status"]=="PASS" and c["checks"]["existing_precheck"]["status"]=="PASS" for c in pool)
    assert all(sha(PROJECT/p)==h for p,h in production.items())
    assert all(sha(PROJECT/p)==h for p,h in old_hashes.items())
    after=summary(records); prior=summary(before)
    before_map={r["candidate_index"]:r for r in before}; old_indices=set(summary(old)["accepted_indices"])
    evidence.update(original_commit=BASELINE,
        new_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=PROJECT,text=True).strip(),
        new_commit_note="F2b source commit at fixed-proposal launch; production_sha256 identifies executed bytes",
        before_formula="gate - (alignment_length_m + half + 50) * direction",
        after_formula="gate - (alignment_length_m + half) * direction",
        skeleton_id=SID,group_id=GID,source_descriptor_sha256=reg["descriptor_sha256"],
        source_pools=[{"path":str(p),"sha256":sha(p)} for p in pools],production_sha256=production,
        frozen_check=frozen_check(reg),historical_evidence_unchanged=True,simulation_count=0,
        historical_pre_F1_F4=summary(old),before_F2b=prior,
        fixed_proposals={"status":"COMPLETE","started_utc":stamp,"finished_utc":datetime.now(timezone.utc).isoformat(),
            "wall_s":time.perf_counter()-start,"summary":after,"records":records,
            "comparison":[{"candidate_index":r["candidate_index"],"original_seed":proposal_seed(spec,r["candidate_index"]),
                "historical_26_member":r["candidate_index"] in old_indices,
                "before_stage":before_map[r["candidate_index"]]["stage"],"before_reason":before_map[r["candidate_index"]]["reason"],
                "after_stage":r["stage"],"after_reason":r["reason"]} for r in records],
            "accepted_candidates":[{"candidate_index":c["index"],"checks":c["checks"],"skeleton":c["skeleton"],
                "waypoints_by_agent":c["bundle"].waypoints_by_agent} for c in pool],
            "newly_observed_rejected_whole_route_issue_codes":sorted(set(after["whole_route_issue_counts"])-set(prior["whole_route_issue_counts"])),
            "exported_candidates_with_constraint_violations":0,
            "comparison_note":"Historical 26 used the pre-F1-F4 chain; before_F2b uses the latest Q2. Same seed identifies the proposal, not identical later draws after local rejection branches change. Counts are observations, never optimization targets."})
    atomic(OUTPUT,evidence)
    print(json.dumps({"before":prior,"after":after,"historical":summary(old)["feasible_group_candidates"]},ensure_ascii=False),flush=True)


if __name__=="__main__": main()
