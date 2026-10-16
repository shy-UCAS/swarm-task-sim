"""Bounded complete Q2 and two-stage Q3; immutable registered runtime sources."""
import argparse
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
from datetime import datetime,timezone
from pathlib import Path
import json
import subprocess
import sys
import time
import traceback
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from scripts.run_v07_m3_checks import EVIDENCE
from scripts.run_v07_m3_trial import atomic,frozen_check,planning_job
from scripts.run_v07_s2_expansion import descriptor_jobs,DEFAULT_DATA
from scripts.run_v07_s2_episode_batch import run_episode_job
from task_v07.io import read_json,save_json,sha
from task_v07.expansion.views import _paired
from task_v07.expansion.contracts import P0ContractError


def runtime_hashes():
    paths=list((PROJECT/"task_v07").rglob("*.py"))+list((PROJECT/"scripts").glob("*.py"))+list((PROJECT/"configs").rglob("*.json"))
    return {p.relative_to(PROJECT).as_posix():sha(p) for p in paths}


def q2_gate(registration,rows):
    by_id={r["skeleton_id"]:r for r in rows}; cells={}; missing_fixed=[]
    for r in registration["selected"]:
        passed=by_id.get(r["skeleton_id"],{}).get("whole_route_pass",False)
        key=r["intent"]+"/"+r["approach_mode"]
        cells[key]=cells.get(key,False) or passed
        if r["q3"] and not passed: missing_fixed.append(r["skeleton_id"])
    return {"passed":len(rows)==20 and all(cells.values()) and not missing_fixed,
            "cells":cells,"fixed_q3_without_candidate":missing_fixed}


def run_stage(phase,jobs,out,deadline,completed,rows):
    pool=ProcessPoolExecutor(max_workers=8)
    futures={pool.submit(planning_job if phase=="q2" else run_episode_job,job):job["descriptor"]["skeleton_id"] for job in jobs}
    pending=set(futures); last=0.
    try:
        while pending:
            remaining=deadline-time.monotonic()
            if remaining<=0: raise TimeoutError("Registered stage wall-clock cap reached")
            done,pending=wait(pending,timeout=min(1.,remaining),return_when=FIRST_COMPLETED)
            for future in done:
                result=future.result()
                if phase=="q2": rows.append(result)
                else: rows.extend(result)
                completed.append(futures[future])
                atomic(out/("planning_records.json" if phase=="q2" else "episode_records.json"),rows)
                print(json.dumps({"completed":futures[future],"remaining_s":deadline-time.monotonic()}),flush=True)
            if time.monotonic()-last>=20:
                atomic(out/"progress.json",{"phase":phase,"completed":completed,"pending":[futures[f] for f in pending],"remaining_s":deadline-time.monotonic()})
                last=time.monotonic()
        if time.monotonic()>deadline: raise TimeoutError("Result collection exceeded stage wall-clock cap")
    except BaseException:
        for future in futures: future.cancel()
        for process in list(pool._processes.values()):
            if process.is_alive(): process.terminate()
        raise
    finally: pool.shutdown(wait=True,cancel_futures=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("phase",choices=("q2","q3"))
    parser.add_argument("--origin",type=Path,help="Repairs retain the original phase clock, never reset it")
    args=parser.parse_args(); reg=read_json(EVIDENCE/"m3b_inputs.json"); frozen=frozen_check(reg)
    hashes=runtime_hashes()
    if args.phase=="q3":
        q2=read_json(EVIDENCE/"m3b_q2.json")
        if q2["status"]!="PASS" or not q2_gate(reg,q2["rows"])["passed"]: raise ValueError("Q2 gate prevents Q3")
        q2reg=read_json(Path(q2["attempt"])/"registration.json")
        # All geometry, wiring and configuration must be the same final sources.
        changed=[p for p,h in q2reg["runtime_sha256"].items() if not p.startswith("scripts/") and hashes.get(p)!=h]
        if changed: raise ValueError(f"Full Q2 must rerun after geometry/wiring/config changes: {changed}")
        dirty=subprocess.check_output(["git","status","--porcelain","--untracked-files=all"],cwd=PROJECT,text=True)
        if dirty.strip(): raise ValueError("Q3 requires a completely committed working tree")
    stamp=datetime.now(timezone.utc); start=time.monotonic(); cap=reg[args.phase+"_wall_limit_s"]
    origin=stamp.isoformat()
    if args.origin:
        original=read_json(args.origin/"registration.json")
        if original["phase"]!=args.phase: raise ValueError("Wrong budget origin phase")
        origin=original["budget_origin_utc"]
    # Also prevent accidentally restarting a phase window without --origin.
    previous=EVIDENCE/("m3b_q2.json" if args.phase=="q2" else "m3b_trial.json")
    if previous.exists() and not args.origin:
        raise ValueError("Existing phase attempt: explicitly use its origin to retain the clock")
    elapsed=(stamp-datetime.fromisoformat(origin)).total_seconds(); remaining=cap-elapsed
    if remaining<=0: raise TimeoutError("Original phase window expired; no rerun authorized")
    out=DEFAULT_DATA/f"attempt_m3b_{args.phase}_{stamp.strftime('%Y%m%dT%H%M%S%fZ')}"; out.mkdir(exist_ok=False)
    selected=[r["skeleton_id"] for r in reg["selected"] if args.phase=="q2" or r["q3"]]
    save_json(out/"registration.json",{**reg,"phase":args.phase,"started_utc":stamp.isoformat(),"budget_origin_utc":origin,
        "workers":8,"selected_skeletons":selected,"entry_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=PROJECT,text=True).strip(),
        "runtime_sha256":hashes,"entry_sha256":sha(Path(__file__)),"backend":"unified","available_wall_s":remaining})
    print(f"OUTPUT {out}",flush=True)
    rows=[]; completed=[]; stages=[]; status="completed"; stop=None
    try:
        jobs=descriptor_jobs(Path(reg["descriptor_attempt"]),selected,out)
        deadline=start+remaining
        if args.phase=="q2": run_stage("q2",jobs,out,deadline,completed,rows)
        else:
            first=set(reg["q3_step1_skeletons"]); first_deadline=min(deadline,start+reg["q3_step1_wall_limit_s"]-elapsed)
            run_stage("q3",[j for j in jobs if j["descriptor"]["skeleton_id"] in first],out,first_deadline,completed,rows)
            accepted={sid:_paired([r for r in rows if r["skeleton_id"]==sid]) for sid in sorted(first)}
            stages.append({"stage":1,"wall_s":time.monotonic()-start,"strict_pairs":accepted})
            atomic(out/"step1_result.json",stages[-1])
            if not all(accepted.values()): status="Q3_STEP1_STOP"
            else:
                run_stage("q3",[j for j in jobs if j["descriptor"]["skeleton_id"] not in first],out,deadline,completed,rows)
                stages.append({"stage":2,"cumulative_wall_s":time.monotonic()-start})
        if runtime_hashes()!=hashes: raise P0ContractError("Runtime source changed during registered trial")
    except BaseException as exc:
        status="TIME_LIMIT_STOP" if isinstance(exc,TimeoutError) else "P0_STOP" if isinstance(exc,P0ContractError) else "ERROR_STOP"
        stop={"reason":str(exc),"exception_type":type(exc).__name__,"traceback":traceback.format_exc()}
    gate=q2_gate(reg,rows) if args.phase=="q2" else None
    if status=="completed":
        if args.phase=="q2": status="PASS" if gate["passed"] else "Q2_NOT_PASSED"
        else: status="completed" if all(_paired([r for r in rows if r["skeleton_id"]==sid]) for sid in selected) else "Q3_NOT_PASSED"
    unfinished=sorted(set(selected)-set(completed))
    summary={"phase":args.phase,"status":status,"attempt":str(out),"rows":rows,"completed":completed,"unfinished":unfinished,
        "wall_s":time.monotonic()-start,"cumulative_wall_s":elapsed+time.monotonic()-start,"wall_limit_s":cap,
        "stop":stop,"frozen_check":frozen_check(reg),"q2_gate":gate,"stages":stages}
    if args.phase=="q2": summary["unfinished_evidence"]={sid:read_json(out/sid/"progress.json") for sid in unfinished if (out/sid/"progress.json").exists()}
    save_json(out/"trial_result.json",summary); atomic(previous,summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ("rows","unfinished_evidence")},ensure_ascii=False),flush=True)
    return 0 if status in ("PASS","completed") else 1


if __name__=="__main__": raise SystemExit(main())
