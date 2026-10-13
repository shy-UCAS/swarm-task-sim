"""Bounded, deterministic tuning of the frozen r2 tuning cohort only."""
from __future__ import annotations
import argparse, copy, hashlib, json, math, os, sys, time, traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
PROJECT=Path(os.environ.get("FAST_DYNAMICS_PROJECT",Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(PROJECT))
from swarm_sim.fast_dynamics.calibration import read_json,sha256,tuning_tasks,aggregate_pairs,fast_summary,paired_metrics
from swarm_sim.fast_dynamics.contracts import M2Config
from swarm_sim.fast_dynamics.output_policy import resolve_output_root,assert_new_attempt_path,assert_created_within
from scripts.baseline_fast_dynamics_m3 import save
PARAMETERS=(("vehicle_profile","max_accel_xy_m_s2",1.5,4.5),
 ("vehicle_profile","max_jerk_m_s3",4.,16.),
 ("vehicle_profile","response_time_s",.10,.50),
 ("controller","velocity_response_time_s",.15,.80))
SPLIT_SHA="b7e33d09e3f6f15deb6ce9f98f90b74b6253c1bc5b0625c75eee1d16592a2e46"

def config_values(config):return tuple(config[g][k] for g,k,_,_ in PARAMETERS)
def configured(values):
 result=M2Config().to_dict()
 for (g,k,lo,hi),value in zip(PARAMETERS,values):
  if not lo<=value<=hi:raise ValueError("search parameter outside approved bounds")
  result[g][k]=float(value)
 return M2Config.from_dict(result).to_dict()

def select_subset(pairs,families):
 """Only identities/pattern/agent count affect selection, never outcomes."""
 by_family={f:[r for r in pairs if r["family_id"]==f] for f in families}
 available=[f for f in families if by_family[f]]
 cells={(r["flight_pattern"],r["agents"]) for r in pairs}
 selected=[]; covered=set()
 for f in available:
  new={(r["flight_pattern"],r["agents"]) for r in by_family[f]}-covered
  if new:
   selected.append(f);covered|=new
  if covered==cells:break
 if len(selected)>24 or len(available)<24:raise ValueError("24-family coverage subset unavailable")
 selected += [f for f in available if f not in selected][:24-len(selected)]
 return dict(families=selected,mission_ids=sorted(r["mission_id"] for r in pairs if r["family_id"] in selected),
             covered_cells=sorted(map(list,cells)),selection="family rank frozen by split seed 2026101205; first family covering an uncovered pattern/agent cell, then fill in rank order; all eligible tasks")

def tiers(pairs,expected):
 agg=aggregate_pairs(pairs);checks=[]
 def check(name,value,limit,applicable=True):
  checks.append(dict(name=name,value=value,minimum=limit,applicable=applicable,
                     passed=None if not applicable else value is not None and value>=limit))
 check("complete_and_quality_count",sum(r["candidate_quality"] is True and r["candidate_status"]=="completed" for r in pairs),expected)
 check("cohort_count",int(len(pairs)==expected),1)
 for k in ("success","observation_success"):check(k,agg[k]["all_task_rate"],.995)
 for c in ("truth","observation"):
  for name,data in agg["conditions"][c].items():check(c+".condition."+name,data["all_task_rate"],.995)
  data=agg["motion_reference_known"][c];check(c+".motion",data["all_task_rate"],.98)
  for pattern in sorted({r["flight_pattern"] for r in pairs}):
   subset=[r for r in pairs if r["flight_pattern"]==pattern]
   data=aggregate_pairs(subset)["motion_reference_known"][c]
   check(c+".motion."+pattern,data["all_task_rate"],.95,data["total"]>0)
 targets=[]
 for name,data,limits in [("total",agg["duration_absolute_relative_error"],(.05,.15,.30))]+[
   (phase,data,(.10,.20,.35)) for phase,data in agg["phase_absolute_relative_error"].items()]:
  values=[data["task"][k] for k in ("median","p95","maximum")]
  targets.append(dict(name=name,values=values,maximum_allowed=limits,missing=data["missing"],
                      passed=data["missing"]==0 and all(v is not None and v<=l for v,l in zip(values,limits))))
 return dict(hard=dict(passed=all(r["passed"] is not False for r in checks),checks=checks),
             targets=targets,diagnostics_only=True,aggregate=agg)

def rank(evaluation,values):
 t=evaluation["tiers"]; a=t["aggregate"]
 hard=sum(r["passed"] is False for r in t["hard"]["checks"])
 exceed=sum(max(0,v/l-1) if v is not None else 1e6 for r in t["targets"] for v,l in zip(r["values"],r["maximum_allowed"]))
 timing=sum(v/l if v is not None else 1e6 for r in t["targets"] for v,l in zip(r["values"],r["maximum_allowed"]))
 # Diagnostics are a final secondary preference, never a freeze gate.
 turn=a["turn_minimum_speed_m_s"]["absolute_difference"]["task"]["median"]
 lateral=a["lateral_task_p95_m"]["task"]["median"]
 diagnostic=(turn/.3 if turn is not None else 0)+(lateral/.5 if lateral is not None else 0)
 default=config_values(M2Config().to_dict())
 distance=sum(((v-d)/(hi-lo))**2 for v,d,(_,_,lo,hi) in zip(values,default,PARAMETERS))
 return (hard,exceed,timing,diagnostic,distance,*values)

def categorical_signature(analysis):
 """Measurement values are not categorical labels. Coverage cell counts are."""
 labels=read_json(analysis/"labels.json");semantics=read_json(analysis/"semantic_validation.json")
 counts={}
 def visit(x,path=""):
  if isinstance(x,dict):
   for k,v in x.items():
    if k in ("cells","covered_cells","repeated_cells","nx","ny") and isinstance(v,int):counts[path+"."+k]=v
    visit(v,path+"."+k)
  elif isinstance(x,list):
   for i,v in enumerate(x):visit(v,f"{path}[{i}]")
 visit(labels.get("mission_metrics",{}))
 return dict(labels={k:v for k,v in labels.items() if k!="mission_metrics" and k!="observed_behaviors"},
   behavior_statuses=[(b.get("name"),b.get("status"),b.get("agent_ids")) for b in labels.get("observed_behaviors",[])],
   conditions=semantics["condition_results"],coverage_counts=counts,
   quality=read_json(analysis/"quality.json")["episode_quality_eligible"],
   phase_count=len(read_json(analysis/"compiled_scene.json")["phases"]),
   event_kinds=sorted({e["event"] for e in read_json(analysis/"events.json")["events"]}))

def measurement_changes(a,b,path=""):
 if type(a)!=type(b):return [dict(field=path,before=a,after=b)]
 if isinstance(a,dict):return [x for k in sorted(set(a)|set(b)) for x in measurement_changes(a.get(k),b.get(k),path+"."+k)]
 if isinstance(a,list):
  return [dict(field=path,before=a,after=b)] if len(a)!=len(b) else [x for i,(c,d) in enumerate(zip(a,b)) for x in measurement_changes(c,d,f"{path}[{i}]")]
 return [] if a==b else [dict(field=path,before=a,after=b)]

def candidate_job(job):
 from swarm_sim.fast_dynamics.mission_executor import run_mission
 from swarm_sim.fast_dynamics.artifacts import write_episode
 from swarm_sim.fast_dynamics.adapter import reuse_semantics
 name,baseline,output,config=job
 base=Path(baseline)/name;dest=Path(output)/name;dest.mkdir(exist_ok=False)
 start=time.perf_counter()
 try:
  task=read_json(base/"input_task.json");ref=read_json(base/"sitl_r2.json")
  cfg=M2Config.from_dict(config)
  with reuse_semantics():
   result=run_mission(task,cfg)
   if result.scene!=read_json(base/"run/analysis/compiled_scene.json"):raise ValueError("compiled planning changed")
   write_episode(result.scene,result,dest/"run",run_id=name,input_hashes={str(base/"input_task.json"):sha256(base/"input_task.json")},config=cfg.to_dict(),seed=task["seed"])
  fast=fast_summary(dest/"run",name); pair=paired_metrics(ref,fast)
  original=read_json(base/"paired.json")
  pair.update(intent=original["intent"],flight_pattern=original["flight_pattern"])
  save(dest/"fast.json",fast);save(dest/"paired.json",pair)
  save(dest/"measurement_changes.json",measurement_changes(read_json(base/"run/analysis/labels.json"),read_json(dest/"run/analysis/labels.json")))
  invariant=categorical_signature(base/"run/analysis")==categorical_signature(dest/"run/analysis")
  outcome=dict(status="COMPLETE" if invariant else "HARD_GATE_STOP",mission_id=name,paired=pair,
               invariant_match=invariant,elapsed_wall_s=time.perf_counter()-start)
  if not invariant:
   save(dest/"invariant_difference.json",dict(before=categorical_signature(base/"run/analysis"),after=categorical_signature(dest/"run/analysis")))
 except Exception as exc:
  outcome=dict(status="P0_STOP",mission_id=name,error=repr(exc),traceback=traceback.format_exc())
 save(dest/"outcome.json",outcome)
 return outcome

def evaluate(names,baseline,output,config,workers):
 output.mkdir(exist_ok=False);save(output/"config.json",config)
 results=[]
 with ProcessPoolExecutor(max_workers=workers) as pool:
  futures=[pool.submit(candidate_job,(name,str(baseline),str(output),config)) for name in sorted(names)]
  stop=False
  for future in as_completed(futures):
   if future.cancelled():continue
   row=future.result();results.append(row);results.sort(key=lambda x:x["mission_id"])
   if row["status"]!="COMPLETE":
    stop=True
    for f in futures:f.cancel()
   save(output/"progress.json",dict(rows=results,stopped=stop))
   print(json.dumps(dict(config=output.name,done=len(results),total=len(names),mission=row["mission_id"],status=row["status"])),flush=True)
 if stop:return dict(status="HARD_GATE_STOP",rows=results)
 return dict(status="COMPLETE",rows=results,tiers=tiers([r["paired"] for r in results],len(names)))

def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument("--split",type=Path,required=True);parser.add_argument("--baseline",type=Path,required=True)
 parser.add_argument("--output",type=Path,required=True);parser.add_argument("--workers",type=int,default=4)
 args=parser.parse_args(argv)
 if args.workers not in range(1,5):parser.error("workers must be 1..4")
 if sha256(args.split)!=SPLIT_SHA:parser.error("immutable r2 split hash mismatch")
 split=read_json(args.split); allowed={r["mission_id"] for r in tuning_tasks(split)}
 report=read_json(args.baseline/"baseline.json")
 names=sorted(r["mission_id"] for r in report["rows"])
 if len(names)!=282 or set(names)-allowed or any(r["status"]!="COMPLETE" for r in report["rows"]):parser.error("require complete repaired 282-task baseline")
 pairs=[read_json(args.baseline/name/"paired.json") for name in names]
 out=assert_new_attempt_path(args.output,resolve_output_root()["root"],kind="M3 tuning")
 out.mkdir();assert_created_within(out,resolve_output_root()["root"])
 subset=select_subset(pairs,split["groups"]["tuning"])
 registration=dict(split_sha256=SPLIT_SHA,subset=subset,parameters=PARAMETERS,max_configurations=25,
   method="one finite-difference pair per coordinate, then bounded coordinate descent with range/4 steps; halve steps after no improvement, stop below range/16 or at 25 unique configs",
   rank="hard failure count; normalized target exceedance; normalized total/phase timing error; turn/lateral diagnostics; normalized distance from default; parameter tuple",
   hard_and_targets=tiers(pairs,282),internal_holdout_used=False)
 save(out/"registration.json",registration)
 if not registration["hard_and_targets"]["hard"]["passed"]:
  save(out/"STOP.json",dict(reason="repaired baseline hard gate",tiers=registration["hard_and_targets"]));return 2
 default=config_values(M2Config().to_dict());cache={}
 subset_pairs=[r for r in pairs if r["mission_id"] in subset["mission_ids"]]
 cache[default]=dict(id="config_000",values=default,status="COMPLETE",tiers=tiers(subset_pairs,len(subset_pairs)),source="repaired default baseline")
 save(out/"config_000.json",cache[default])
 def trial(values):
  values=tuple(round(v,12) for v in values)
  if values in cache:return cache[values]
  cid=f"config_{len(cache):03d}"
  row=evaluate(subset["mission_ids"],args.baseline,out/cid,configured(values),args.workers)
  row.update(id=cid,values=values)
  save(out/cid/"evaluation.json",row);cache[values]=row
  if row["status"]!="COMPLETE":
   save(out/"STOP.json",dict(reason="candidate invariant or execution gate",config=cid));raise RuntimeError("candidate gate stop; retain all results")
  if not row["tiers"]["hard"]["passed"]:
   save(out/"STOP.json",dict(reason="candidate hard gate",config=cid,tiers=row["tiers"]));raise RuntimeError("candidate hard gate stop")
  save(out/"search_history.json",list(cache.values()))
  return row
 steps=[(hi-lo)/4 for _,_,lo,hi in PARAMETERS]
 for i,(_,_,lo,hi) in enumerate(PARAMETERS):
  for sign in (-1,1):
   candidate=list(default);candidate[i]=min(hi,max(lo,default[i]+sign*steps[i]))
   trial(candidate)
 while len(cache)<25:
  best=min(cache,key=lambda v:rank(cache[v],v));improved=False
  for i,(_,_,lo,hi) in enumerate(PARAMETERS):
   for sign in (-1,1):
    candidate=list(best);candidate[i]=min(hi,max(lo,best[i]+sign*steps[i]))
    if len(cache)>=25:break
    trial(candidate)
   winner=min(cache,key=lambda v:rank(cache[v],v))
   if rank(cache[winner],winner)<rank(cache[best],best):best=winner;improved=True
  if not improved:
   steps=[s/2 for s in steps]
   if all(s<(hi-lo)/16 for s,(_,_,lo,hi) in zip(steps,PARAMETERS)):break
 top=sorted(cache,key=lambda v:rank(cache[v],v))[:3]; finals=[]
 save(out/"top_three.json",[cache[v]["id"] for v in top])
 for values in top:
  cid=cache[values]["id"];evaluation=evaluate(names,args.baseline,out/(cid+"_full"),configured(values),args.workers)
  evaluation.update(id=cid,values=values);save(out/(cid+"_full")/"evaluation.json",evaluation);finals.append(evaluation)
  if evaluation["status"]!="COMPLETE" or not evaluation["tiers"]["hard"]["passed"]:
   save(out/"STOP.json",dict(reason="full-cohort hard gate",config=cid));return 2
 winner=min(finals,key=lambda e:rank(e,e["values"]))
 configpath=out/"frozen_m3_v1.json";save(configpath,configured(winner["values"]))
 save(out/"freeze_record.json",dict(status="FROZEN",split_sha256=SPLIT_SHA,config_path=str(configpath),config_sha256=sha256(configpath),
  candidate=winner["id"],eligible_tasks=282,tiers=winner["tiers"],searched_configurations=len(cache),top_three=[r["id"] for r in finals],
  internal_holdout_used=False,method="user approved bounded coordinate search; no post-freeze tuning"))
 print(json.dumps(dict(status="FROZEN",candidate=winner["id"],config=configured(winner["values"]))),flush=True)
 return 0

if __name__=="__main__":raise SystemExit(main())
