"""Bounded V01-V05 runner. One explicit attempt per invocation; never runs V06."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from swarm_sim.analysis import digest
from swarm_sim.recording import write_json
from swarm_sim.tasks import compile_task, validate_task_binding

DEFAULT_ROOT=ROOT/"verification/v04_v1_20261001"
JOBS=[("V01",1,"recon_shared_3uav_barrier"),("V02",1,"recon_shared_3uav_route"),
      ("V02",2,"recon_shared_3uav_route"),("V03",1,"recon_smoke_2uav_north_route"),
      ("V04",1,"recon_smoke_6uav_route"),("V05",1,"recon_shared_3uav_route")]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def historical_evidence(path,expected_sha256=None):
    path=Path(path).resolve()
    if expected_sha256 and digest(path)!=expected_sha256:
        raise ValueError("historical failed ledger changed")
    history=read(path)
    records=history.get("records",[])
    if (history.get("attempts_started")!=1 or history.get("new_sitl_runs")!=1 or len(records)!=1
            or records[0].get("validation_id")!="V01" or records[0].get("state")!="finished"
            or records[0].get("run_status")!="failed" or records[0].get("exit_code")!=1):
        raise ValueError("resume authorization covers exactly the preserved failed V01 attempt")
    record=records[0]
    for name in ("metadata","quality"):
        if digest(Path(record["run_directory"])/(name+".json"))!=record[name+"_sha256"]:
            raise ValueError("historical failed run changed")
    return dict(path=str(path),sha256=digest(path),attempts_started=1,new_sitl_runs=1,
                run_ids=[record["run_id"]],status="preserved_failed_not_reclassified")


def prepare(root,prior_records=None,offline_gate=None):
    history=historical_evidence(prior_records) if prior_records else None
    root.mkdir(parents=True,exist_ok=False)
    plans=root/"plans"; plans.mkdir()
    jobs=[]
    for validation,repeat,template in JOBS:
        key=f"{validation}_r{repeat}"
        task=read(ROOT/"missions/v3"/(template+".json"))
        if validation=="V05":
            task["task_id"]="recon_controlled_phase_timeout_v05"
            task["execution"]["phase_timeout_override_s"]=.01
        scene=compile_task(task); validate_task_binding(scene)
        task_path=plans/(key+".task.json"); scene_path=plans/(key+".scene.json")
        write_json(task_path,scene["task_spec"]); write_json(scene_path,scene)
        jobs.append(dict(key=key,validation_id=validation,repeat=repeat,task=str(task_path),scene=str(scene_path),
                         task_sha256=digest(task_path),scene_sha256=digest(scene_path)))
    write_json(root/"records.json",dict(schema_version=2 if history else 1,budget=7 if history else 6,
        historical_evidence=history,attempts_started=0,new_sitl_runs=0,
        offline_gate=str(Path(offline_gate).resolve()) if offline_gate else str(ROOT/"tmp_v04/wp_e/offline_acceptance.json"),
        authorization="2026-10-02 user confirmation: parameter comparison v2; prior failed V01 counts; total 7 attempts; restart full V01-V05; stop on failure; no V06" if history else
                      "WP-G user confirmation; E1-E3 PASS before V01-V05; stop at V05; V06 not authorized",
        prepared_utc=datetime.now(timezone.utc).isoformat(),jobs=jobs,records=[]))
    print(json.dumps(dict(prepared=str(root),jobs=[j["key"] for j in jobs],new_sitl_runs=0)))


def check_offline_gate(gate_path):
    gate_path=Path(gate_path)
    gate=read(gate_path)
    required=[f"E{i:02d}" for i in range(1,11)]+[f"R{i:02d}" for i in range(1,7)]
    if gate.get("status")!="PASS" or any(gate.get("checks",{}).get(k)!="PASS" for k in required):
        raise ValueError("E1-E3 offline acceptance incomplete/failed: SITL is forbidden")
    tests_path=ROOT/gate["tests_path"]
    if digest(tests_path)!=gate["tests_sha256"]:
        raise ValueError("offline test evidence changed")
    tests=read(tests_path)
    if tests.get("status")!="PASS" or tests["R01"]["status"]!="PASS":
        raise ValueError("offline tests are not passing")
    changed=[name for name,expected in tests["source_sha256"].items() if digest(ROOT/name)!=expected]
    if changed:
        raise ValueError("tested source changed; revalidate before SITL: "+", ".join(changed))
    return dict(path=str(gate_path),sha256=digest(gate_path),tests_sha256=digest(tests_path))


def run_one(root,key):
    path=root/"records.json"; ledger=read(path)
    if ledger.get("stopped_reason"):
        raise ValueError("validation stopped: "+ledger["stopped_reason"])
    gate=check_offline_gate(ledger.get("offline_gate",ROOT/"tmp_v04/wp_e/offline_acceptance.json"))
    history=ledger.get("historical_evidence")
    if history:
        historical_evidence(history["path"],history["sha256"])
        if ledger["budget"]!=7:
            raise ValueError("resumed V1 authorization is exactly seven cumulative attempts")
    prior_attempts=history["attempts_started"] if history else 0
    index=ledger["attempts_started"]
    if index+prior_attempts>=ledger["budget"] or index>=6 or index>=len(ledger["jobs"]):
        raise ValueError("V01-V05 budget exhausted; V06 requires user confirmation")
    job=ledger["jobs"][index]
    if key!=job["key"]:
        raise ValueError("next authorized bounded attempt is "+job["key"])
    if any(r["state"]!="finished" for r in ledger["records"]):
        raise ValueError("previous attempt has no finished evidence; do not retry silently")
    if ledger["records"]:
        from scripts.verify_v04_v1 import verify_records
        review=verify_records(path)
        problems=[]
        if not review["source_files_unchanged"]:
            problems.append("evidence changed during review")
        for row in review["records"]:
            if row["validation_id"]=="V05":
                continue
            if (row["run_status"]!="completed" or row["exit_code"]!=0
                    or not row["cleanup"]["complete"] or not row["evidence_integrity_pass"] or row["issues"]):
                problems.append(row["run_id"]+": run/cleanup/integrity failed")
            if row["validation_id"] in ("V02","V03","V04"):
                problems.extend(row["run_id"]+": "+criterion+"="+str(value)
                                for criterion,value in row["criteria"].items()
                                if criterion!="AC1" and value is not True)
        if review["ac1_pooled"]["matrix_complete"] and review["observed_route_criteria"]["AC1"] is not True:
            problems.append("pooled AC1="+str(review["observed_route_criteria"]["AC1"]))
        if problems:
            ledger["stopped_reason"]="; ".join(problems)
            ledger["stop_review"]=review
            write_json(path,ledger)
            raise ValueError("validation stopped; no further SITL: "+ledger["stopped_reason"])
    for filename in ("task","scene"):
        if digest(Path(job[filename]))!=job[filename+"_sha256"]:
            raise ValueError("prepared input changed")
    scene=read(Path(job["scene"])); validate_task_binding(scene)
    record=dict(job,state="started",started_utc=datetime.now(timezone.utc).isoformat(),offline_gate=gate)
    ledger["records"].append(record); ledger["attempts_started"]+=1
    write_json(path,ledger)
    from swarm_sim.runner import run_scene
    try:
        run,metadata,quality=run_scene(scene,root/"runs",ROOT/"ArducopterSITL/arducopter.exe",ROOT/"ArducopterSITL/copter.parm")
    except BaseException as exc:
        record.update(state="interrupted_without_final_result",error=f"{type(exc).__name__}: {exc}")
        write_json(path,ledger)
        raise
    code=0 if quality.get("usable") else 1
    launched=bool(metadata.get("sitl",{}).get("instances"))
    ledger["new_sitl_runs"]+=int(launched)
    record.update(state="finished",run_directory=str(run),run_id=metadata["run_id"],exit_code=code,
                  run_status=metadata["status"],launched_sitl=launched,
                  finished_utc=datetime.now(timezone.utc).isoformat(),metadata_sha256=digest(run/"metadata.json"),
                  quality_sha256=digest(run/"quality.json"))
    write_json(path,ledger)
    from scripts.verify_v04_v1 import verify_records
    review=verify_records(path)
    latest=review["records"][-1]
    failures=[]
    if not review["source_files_unchanged"] or not latest["cleanup"]["complete"] or not latest["evidence_integrity_pass"] or latest["issues"]:
        failures.append("cleanup/evidence integrity failed or incomplete")
    if key.startswith("V05"):
        if not latest["expected_failure"] or latest["expected_failure"].get("as_expected") is not True:
            failures.append("V05 controlled phase timeout not verified")
    else:
        if metadata["status"]!="completed" or code!=0:
            failures.append("run or quality acceptance failed")
        if latest["validation_id"] in ("V02","V03","V04"):
            failures.extend(k+"="+str(v) for k,v in latest["criteria"].items() if k!="AC1" and v is not True)
        if review["ac1_pooled"]["matrix_complete"] and review["observed_route_criteria"]["AC1"] is not True:
            failures.append("pooled AC1="+str(review["observed_route_criteria"]["AC1"]))
    if failures:
        ledger["stopped_reason"]=key+": "+"; ".join(failures)
        ledger["stop_review"]=review
        write_json(path,ledger)
    print(json.dumps(dict(validation=key,run_directory=str(run),run_status=metadata["status"],exit_code=code,
                         validation_exit_code=1 if failures else code,
                         new_sitl_runs=ledger["new_sitl_runs"],
                         cumulative_sitl_runs=ledger["new_sitl_runs"]+(history["new_sitl_runs"] if history else 0),
                         budget=ledger["budget"],stopped_reason=ledger.get("stopped_reason"))))
    return 1 if failures else code


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare",action="store_true")
    action.add_argument("--run")
    parser.add_argument("--output",type=Path,default=DEFAULT_ROOT)
    parser.add_argument("--prior-records",type=Path,help="preserved failed V01 ledger; authorizes 7 cumulative attempts")
    parser.add_argument("--offline-gate",type=Path,help="new, separately recorded offline acceptance")
    args=parser.parse_args()
    root=args.output.resolve()
    if args.prepare:
        prepare(root,args.prior_records,args.offline_gate); return 0
    return run_one(root,args.run)


if __name__=="__main__": sys.exit(main())
