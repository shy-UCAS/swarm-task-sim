"""One explicitly requested legacy gate; immutable task outputs, no exclusions."""
import ast
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE=Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO=BASE/"Simulation-v08"
CODE=REPO/"Multi-UAV SimpleGC"
ROOT=BASE/"_handoff/2026-11-09_V8-20_area_search/run"
DOC=REPO/"docs/v08/V8-20"


def read(p):
    return json.loads(p.read_text(encoding="utf-8"))


def dump(p,obj):
    with p.open("w",encoding="utf-8",newline="\n") as f:
        f.write(json.dumps(obj,ensure_ascii=False,indent=1)+"\n")
        f.flush()
        os.fsync(f.fileno())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def audit(manifest):
    changed=[]
    for name,h in manifest["frozen_files"].items():
        if sha(Path(name))!=h:
            changed.append(name)
    for row in manifest["frozen_symbols"]:
        p=Path(row["path"])
        text=p.read_text(encoding="utf-8")
        node=next(n for n in ast.parse(text).body if getattr(n,"name",None)==row["qualname"])
        h=hashlib.sha256(ast.get_source_segment(text,node).encode("utf-8")).hexdigest()
        if h!=row["sha256"]:
            changed.append(row["path"]+":"+row["qualname"])
    for name,fact in manifest["owners"].items():
        p=Path(name)
        if sha(p)!=fact["sha256"] or p.stat().st_mtime_ns!=fact["mtime_ns"]:
            changed.append(name)
    for name,fact in manifest["preset_files"].items():
        if sha(Path(name))!=fact["sha256"]:
            changed.append(name)
    return changed


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("intent")
    parser.add_argument("phase",type=int)
    parser.add_argument("--round",default="r1")
    args=parser.parse_args()
    intent,phase=args.intent,args.phase
    round_name=args.round
    assert round_name.isalnum()
    assert phase in (2,4)
    m=read(DOC/"manifest.json")
    assert intent in m["baselines"]
    assert read(ROOT/"part2/old_tests_r1/results.json")["passed"]
    changes=audit(m)
    if changes:
        print(json.dumps({"preflight_failed":changes}),flush=True)
        return 2
    out=ROOT/f"gate_p{phase}"/intent/round_name
    diag=ROOT/f"gate_p{phase}"/intent/f"diagnostics_{round_name}"
    assert not out.exists() and not diag.exists()
    diag.mkdir(parents=True)
    specs={
      "monitoring":("tools/v08/run_separation_v15.py",["--mode","production-quick"],"run"),
      "transit":("tools/v08/run_transit_v16.py",["--stage","quick"],""),
      "intrusion":("tools/v08/run_intrusion_v17.py",["--stage","quick"],""),
      "feint":("tools/v08/run_feint_v18.py",["--stage","quick"],""),
      "close_observation":("tools/v08/run_close_observation_v19.py",["--stage","quick"],""),
    }
    script,stage,suffix=specs[intent]
    baseline=Path(m["baselines"][intent]["path"])
    argv=[sys.executable,"-B",script,*stage,"--workers","24","--devset",m["devset"],"--data-root",m["data_root"],
          "--cache",m["cache"],"--out",str(out)]
    if intent=="monitoring":
        argv += ["--baseline",str(baseline)]
    env=dict(os.environ)
    env.update(dict.fromkeys(("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS","PYTHONDONTWRITEBYTECODE"),"1"))
    source_hashes={str(p.relative_to(CODE)):sha(p) for root in (CODE/"v08",CODE/"tools/v08") for p in root.rglob("*.py")}
    begin=time.perf_counter()
    run={"intent":intent,"phase":phase,"round":round_name,"workers":24,"command":argv,"start_epoch_s":time.time(),
         "source_sha256":source_hashes,"baseline":str(baseline),"repeat":str(out/suffix),"exclusions":[],"status":"running"}
    dump(diag/"watchdog.json",run)
    print(f"START phase={phase} intent={intent} workers=24",flush=True)
    with (diag/"stdout.log").open("w",encoding="utf-8") as stdout,(diag/"stderr.log").open("w",encoding="utf-8") as stderr:
        proc=subprocess.Popen(argv,cwd=CODE,env=env,stdout=stdout,stderr=stderr)
        monitor_root=ROOT/"system_monitor"
        monitor_root.mkdir(exist_ok=True)
        job={"intent":intent,"phase":phase,"round":round_name,"root_pid":proc.pid,"wrapper_pid":os.getpid(),
             "start_epoch_s":run["start_epoch_s"],"status":"running","diagnostics":str(diag)}
        dump(monitor_root/"current_job.json",job)
        run["root_pid"]=proc.pid
        dump(diag/"watchdog.json",run)
        proc.wait()
        job.update(status="finished",exit_code=proc.returncode,end_epoch_s=time.time())
        dump(monitor_root/"current_job.json",job)
    run.update(exit_code=proc.returncode,wall_s=time.perf_counter()-begin,end_epoch_s=time.time(),status="finished")
    dump(diag/"watchdog.json",run)
    print(f"END phase={phase} intent={intent} exit={proc.returncode} wall_s={run['wall_s']:.6f}",flush=True)
    repeat=out/suffix
    keys=m["lists"]["quick"]
    rows=read(repeat/"records.json") if (repeat/"records.json").is_file() else []
    comparisons=[]
    for cid in keys:
        left,right=baseline/"contracts"/cid,repeat/"contracts"/cid
        a={p.relative_to(left).as_posix():p for p in left.rglob("*") if p.is_file()}
        b={p.relative_to(right).as_posix():p for p in right.rglob("*") if p.is_file()}
        differing=[n for n in sorted(a.keys()&b.keys()) if a[n].read_bytes()!=b[n].read_bytes()]
        only_a,only_b=sorted(a.keys()-b.keys()),sorted(b.keys()-a.keys())
        same=bool(a) and "contract.json" in a and "contract.json" in b and not differing and not only_a and not only_b
        comparisons.append({"contract_id":cid,"files":len(a),"equal":same,"differing":differing,"only_baseline":only_a,"only_repeat":only_b})
    comparison={"intent":intent,"phase":phase,"baseline":str(baseline),"repeat":str(repeat),"exclusions":[],
        "records_keys_equal":len(rows)==20 and sorted(r["contract_id"] for r in rows)==sorted(keys),
        "equal_count":sum(r["equal"] for r in comparisons),"total":20,"comparisons":comparisons,
        "different_file_count":sum(len(r["differing"])+len(r["only_baseline"])+len(r["only_repeat"]) for r in comparisons),
        "source_unchanged_during_gate":all(sha(CODE/p)==h for p,h in source_hashes.items()),"post_audit_changes":audit(m)}
    comparison["all_equal"]=comparison["equal_count"]==20 and comparison["records_keys_equal"]
    dump(diag/"comparison.json",comparison)
    print(json.dumps({k:comparison[k] for k in ("intent","phase","equal_count","total","different_file_count","all_equal")}),flush=True)
    if not comparison["all_equal"]:
        return 4
    if comparison["post_audit_changes"] or not comparison["source_unchanged_during_gate"]:
        return 2
    return proc.returncode


if __name__=="__main__":
    raise SystemExit(main())
