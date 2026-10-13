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

def target_rank(evaluation):
 a=evaluation["tiers"]["aggregate"]
 def value(x):return float("inf") if x is None else x
 return (value(a["duration_absolute_relative_error"]["task"]["median"]),
         value(a["phase_absolute_relative_error"].get("p01_observe",{}).get("task",{}).get("median")))

def rank(evaluation,values):
 a=evaluation["tiers"]["aggregate"]
 turn=a["turn_minimum_speed_m_s"]["absolute_difference"]["task"]["median"]
 default=config_values(M2Config().to_dict())
 distance=sum(((v-d)/(hi-lo))**2 for v,d,(_,_,lo,hi) in zip(values,default,PARAMETERS))
 return (not evaluation["tiers"]["hard"]["passed"],*target_rank(evaluation),
         float("inf") if turn is None else turn,distance,*values)

def classify_evaluation(rows,expected):
 """A rejected configuration does not stop the search; a contract P0 does."""
 if any(r["status"]=="P0_STOP" for r in rows):return dict(status="P0_STOP",rows=rows)
 result=tiers([r["paired"] for r in rows],expected)
 return dict(status="ELIGIBLE" if result["hard"]["passed"] else "REJECTED",rows=rows,tiers=result)

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
  # write_episode validates labels against the executed physical trajectory.
  # Measurement changes under different parameters are expected and recorded.
  outcome=dict(status="COMPLETE",mission_id=name,paired=pair,elapsed_wall_s=time.perf_counter()-start)
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
   if row["status"]=="P0_STOP":
    stop=True
    for f in futures:f.cancel()
   save(output/"progress.json",dict(rows=results,stopped=stop))
   print(json.dumps(dict(config=output.name,done=len(results),total=len(names),mission=row["mission_id"],status=row["status"])),flush=True)
 return classify_evaluation(results,len(names))

def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument("--split",type=Path,required=True);parser.add_argument("--baseline",type=Path,required=True)
 parser.add_argument("--output",type=Path,required=True);parser.add_argument("--workers",type=int,default=4)
 parser.add_argument("--resume",type=Path,required=True,help="prior search evidence; reuse only complete configurations 001-004")
 args=parser.parse_args(argv)
 if args.workers not in range(1,5):parser.error("workers must be 1..4")
 if sha256(args.split)!=SPLIT_SHA:parser.error("immutable r2 split hash mismatch")
 split=read_json(args.split);allowed={r["mission_id"] for r in tuning_tasks(split)}
 report=read_json(args.baseline/"baseline.json");names=sorted(r["mission_id"] for r in report["rows"])
 if len(names)!=282 or set(names)-allowed or any(r["status"]!="COMPLETE" for r in report["rows"]):parser.error("require complete repaired 282-task baseline")
 pairs=[read_json(args.baseline/name/"paired.json") for name in names]
 subset=select_subset(pairs,split["groups"]["tuning"])
 previous=read_json(args.resume/"registration.json")
 if previous["subset"]!=subset or previous["split_sha256"]!=SPLIT_SHA:parser.error("cannot change the registered subset")
 out=assert_new_attempt_path(args.output,resolve_output_root()["root"],kind="M3 tuning continuation")
 out.mkdir();assert_created_within(out,resolve_output_root()["root"])
 registration=dict(split_sha256=SPLIT_SHA,subset=subset,parameters=PARAMETERS,max_configurations=25,
  rule_revision="20261013_user_candidate_rejection_v2",previous_search=str(args.resume),
  method=previous["method"],rank="eligible first; total absolute relative duration median; observe absolute relative duration median; turn minimum speed absolute difference median; normalized default distance; parameter tuple",
  target_improvement="lexicographic improvement in (total duration median, observe duration median); all p95/max targets reported, not additional gates",
  measurement_changes_are_not_gates=True,conditions_reported_not_extra_rejection_gate=True,
  internal_holdout_used=False,config_005_policy="rerun all 70, never rank its historical partial results")
 save(out/"registration.json",registration)
 default=config_values(M2Config().to_dict());cache={}
 default_full=dict(id="config_000",values=default,tiers=tiers(pairs,282),source=str(args.baseline))
 save(out/"default_full_evaluation.json",default_full)
 if not default_full["tiers"]["hard"]["passed"]:raise ValueError("P0: approved repaired default baseline no longer passes")
 subset_pairs=[r for r in pairs if r["mission_id"] in subset["mission_ids"]]
 cache[default]=dict(id="config_000",values=default,status="ELIGIBLE",tiers=tiers(subset_pairs,len(subset_pairs)),source=str(args.baseline))
 save(out/"config_000.json",cache[default])
 for cid in ("config_001","config_002","config_003","config_004"):
  old=read_json(args.resume/cid/"evaluation.json")
  if old["status"]!="COMPLETE" or sorted(r["mission_id"] for r in old["rows"])!=subset["mission_ids"]:raise ValueError("P0: incomplete carry-forward cohort")
  values=tuple(old["values"])
  if config_values(read_json(args.resume/cid/"config.json"))!=values:raise ValueError("P0: carry-forward configuration mismatch")
  row=classify_evaluation(old["rows"],len(subset_pairs));row.update(id=cid,values=values,source=str(args.resume/cid))
  cache[values]=row;save(out/(cid+"_reused.json"),row)
 save(out/"search_history.json",list(cache.values()))
 def trial(values):
  values=tuple(round(v,12) for v in values)
  if values in cache:return cache[values]
  if len(cache)>=25:raise ValueError("configuration budget exhausted")
  cid=f"config_{len(cache):03d}"
  row=evaluate(subset["mission_ids"],args.baseline,out/cid,configured(values),args.workers)
  row.update(id=cid,values=values);save(out/cid/"evaluation.json",row);cache[values]=row
  save(out/"search_history.json",list(cache.values()))
  if row["status"]=="P0_STOP":
   save(out/"STOP.json",dict(reason="P0 candidate contract/trajectory-label failure",config=cid));raise RuntimeError("P0 stop; retain evidence")
  print(json.dumps(dict(config=cid,classification=row["status"],rank=rank(row,values))),flush=True)
  return row
 steps=[(hi-lo)/4 for _,_,lo,hi in PARAMETERS]
 for i,(_,_,lo,hi) in enumerate(PARAMETERS):
  for sign in (-1,1):
   candidate=list(default);candidate[i]=min(hi,max(lo,default[i]+sign*steps[i]));trial(candidate)
 while len(cache)<25:
  best=min(cache,key=lambda v:rank(cache[v],v));improved=False
  for i,(_,_,lo,hi) in enumerate(PARAMETERS):
   for sign in (-1,1):
    if len(cache)>=25:break
    candidate=list(best);candidate[i]=min(hi,max(lo,best[i]+sign*steps[i]));trial(candidate)
   winner=min(cache,key=lambda v:rank(cache[v],v))
   if rank(cache[winner],winner)<rank(cache[best],best):best=winner;improved=True
  if not improved:
   steps=[s/2 for s in steps]
   if all(s<(hi-lo)/16 for s,(_,_,lo,hi) in zip(steps,PARAMETERS)):break
 top=sorted((v for v in cache if cache[v]["status"]=="ELIGIBLE"),key=lambda v:rank(cache[v],v))[:3]
 save(out/"top_three.json",[cache[v]["id"] for v in top])
 finals=[]
 for values in top:
  cid=cache[values]["id"]
  evaluation=evaluate(names,args.baseline,out/(cid+"_full"),configured(values),args.workers)
  evaluation.update(id=cid,values=values);save(out/(cid+"_full")/"evaluation.json",evaluation);finals.append(evaluation)
  if evaluation["status"]=="P0_STOP":
   save(out/"STOP.json",dict(reason="P0 full cohort",config=cid));return 2
 eligible=[r for r in finals if r["status"]=="ELIGIBLE"]
 better=[r for r in eligible if target_rank(r)<target_rank(default_full)]
 winner=min(better,key=lambda e:rank(e,e["values"])) if better else default_full
 configpath=out/"frozen_m3_v1.json";save(configpath,configured(winner["values"]))
 record=dict(status="FROZEN",schema_version=1,split_sha256=SPLIT_SHA,config_path=str(configpath),config_sha256=sha256(configpath),
  candidate=winner["id"],eligible_tasks=282,tiers=winner["tiers"],searched_configurations=len(cache),
  top_three=[r["id"] for r in finals],full_cohort_results=[dict(id=r["id"],status=r["status"],tiers=r["tiers"]) for r in finals],
  internal_holdout_used=False,default_fallback=not better,reason="best eligible target-improving candidate" if better else "no eligible full-cohort target improvement; default frozen",
  method="user revised elimination and ranking; no holdout used")
 save(out/"freeze_record.json",record)
 print(json.dumps(dict(status="FROZEN",candidate=winner["id"],config=configured(winner["values"]))),flush=True)
 return 0

if __name__=="__main__":raise SystemExit(main())
