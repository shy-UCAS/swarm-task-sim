"""One-time frozen/default comparison on r2 internal references after tuning."""
from __future__ import annotations
import argparse, contextlib, json, sys, time, traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from swarm_sim.fast_dynamics.calibration import (
 evaluation_tasks,final_attempts,reference_summary,fast_summary,paired_metrics,aggregate_pairs,read_json,sha256)
from swarm_sim.fast_dynamics.contracts import M2Config
from swarm_sim.fast_dynamics.output_policy import resolve_output_root,assert_new_attempt_path,assert_created_within
from scripts.baseline_fast_dynamics_m3 import save
from scripts.tune_fast_dynamics_m3 import SPLIT_SHA,tiers,config_values

def fallback_decision(frozen_pass,default_pass):
 return bool(not frozen_pass and default_pass)

def execute(job):
 from swarm_sim.fast_dynamics.mission_executor import run_mission
 from swarm_sim.fast_dynamics.artifacts import write_episode
 from swarm_sim.fast_dynamics.adapter import reuse_semantics
 split,row,freeze,config,root=job
 name=row["task"]["mission_id"];dest=Path(root)/name;dest.mkdir(exist_ok=False)
 started=time.perf_counter()
 with (dest/"commands.log").open("x",encoding="utf-8") as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
  try:
   ref,scene,task_path=reference_summary(row,split,split["source_roots"]["r2"],group="internal_holdout",freeze_record=freeze)
   save(dest/"sitl_r2.json",ref)
   if ref["status"]!="COMPLETE":
    outcome=dict(status="REFERENCE_NOT_COMPARABLE",reason=ref["status"],mission_id=name)
   else:
    task=read_json(task_path);(dest/"input_task.json").write_bytes(task_path.read_bytes())
    results={};runs={};same=config==M2Config().to_dict()
    for label,raw in (("frozen",config),("default",M2Config().to_dict())):
     if label=="default" and same:
      results[label]=results["frozen"];runs[label]=runs["frozen"]
      save(dest/"default_reuse.json",dict(reason="frozen and default configurations exactly equal",run=runs["frozen"]))
      continue
     cfg=M2Config.from_dict(raw)
     with reuse_semantics():
      result=run_mission(task,cfg)
      if result.scene!=scene:raise ValueError("P0: compiled planning differs from reference")
      write_episode(scene,result,dest/label,run_id=name,input_hashes={str(task_path):sha256(task_path)},config=cfg.to_dict(),seed=task["seed"])
     candidate=fast_summary(dest/label,name);paired=paired_metrics(ref,candidate)
     paired.update(intent=row["task"]["intent"],flight_pattern=row["task"]["flight_pattern"])
     save(dest/(label+"_fast.json"),candidate);save(dest/(label+"_paired.json"),paired)
     results[label]=paired;runs[label]=str(dest/label)
    outcome=dict(status="COMPLETE",mission_id=name,pairs=results,runs=runs,
        identical_config_reused=same,elapsed_wall_s=time.perf_counter()-started)
  except Exception as exc:
   outcome=dict(status="P0_STOP",mission_id=name,error=repr(exc),traceback=traceback.format_exc())
  save(dest/"outcome.json",outcome)
  return outcome

def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument("--split",type=Path,required=True);parser.add_argument("--freeze-record",type=Path,required=True)
 parser.add_argument("--output",type=Path,required=True);parser.add_argument("--workers",type=int,default=4)
 args=parser.parse_args(argv)
 if not 1<=args.workers<=4:parser.error("workers must be 1..4")
 if sha256(args.split)!=SPLIT_SHA:parser.error("frozen r2 split changed")
 split=read_json(args.split)
 allowed=evaluation_tasks(split,group="internal_holdout",freeze_record=args.freeze_record)
 freeze=read_json(args.freeze_record);config=read_json(freeze["config_path"]);M2Config.from_dict(config)
 root=resolve_output_root()["root"]
 output=assert_new_attempt_path(args.output,root,kind="one-time internal holdout")
 r2=Path(split["source_roots"]["r2"])
 if sha256(r2/"plan.json")!=split["plan_sha256"]["r2"]:parser.error("r2 plan changed")
 marker=args.freeze_record.parent/"internal_holdout_started.json"
 with marker.open("x",encoding="utf-8") as stream:
  json.dump(dict(output=str(output),freeze_record=str(args.freeze_record),config_sha256=freeze["config_sha256"],
                 default_also_evaluated=True,one_time=True),stream)
 output.mkdir();assert_created_within(output,root);save(output/"frozen_config.json",config)
 save(output/"default_config.json",M2Config().to_dict())
 selection=final_attempts(split,r2,group="internal_holdout",freeze_record=args.freeze_record)
 save(output/"reference_selection.json",selection)
 eligible=[r for r in selection if r["status"]=="ELIGIBLE"]
 report=dict(status="RUNNING",qualification="internal holdout, not a strict blind test",
  families=len(split["groups"]["internal_holdout"]),planned_tasks=len(allowed),eligible_references=len(eligible),
  initial_config_sha256=freeze["config_sha256"],rows=[],m2_02b_accessed=False,sitl_launched=False,retuning_allowed=False)
 save(output/"report.json",report)
 with ProcessPoolExecutor(max_workers=args.workers) as pool:
  futures=[pool.submit(execute,(split,r,str(args.freeze_record),config,str(output))) for r in eligible]
  for future in as_completed(futures):
   if future.cancelled():continue
   row=future.result();report["rows"].append(row);report["rows"].sort(key=lambda r:r["mission_id"])
   if row["status"]=="P0_STOP":
    report["status"]="P0_STOP"
    for f in futures:f.cancel()
   save(output/"report.json",report)
   print(json.dumps(dict(done=len(report["rows"]),total=len(eligible),mission=row["mission_id"],status=row["status"])),flush=True)
 if report["status"]=="P0_STOP":return 2
 comparable=[r for r in report["rows"] if r["status"]=="COMPLETE"]
 report["comparable_references"]=len(comparable)
 layers={}
 for label in ("frozen","default"):
  pairs=[r["pairs"][label] for r in comparable]
  layers[label]=tiers(pairs,len(comparable));save(output/(label+"_tiers.json"),layers[label])
  save(output/(label+"_groups.json"),dict(
   by_pattern={p:aggregate_pairs([r for r in pairs if r["flight_pattern"]==p]) for p in sorted({r["flight_pattern"] for r in pairs})},
   by_agents={str(n):aggregate_pairs([r for r in pairs if r["agents"]==n]) for n in sorted({r["agents"] for r in pairs})}))
 fallback=fallback_decision(layers["frozen"]["hard"]["passed"],layers["default"]["hard"]["passed"])
 final_config=M2Config().to_dict() if fallback else config
 final_path=output/"frozen_m3_final.json";save(final_path,final_config)
 final=dict(freeze)
 final.update(config_path=str(final_path),config_sha256=sha256(final_path),freeze_revision=2 if fallback else 1,
  previous_freeze_record=str(args.freeze_record),internal_holdout_used=True,internal_default_fallback=fallback,
  internal_hard_pass=layers["default" if fallback else "frozen"]["hard"]["passed"],
  reason="user-authorized default fallback, no retuning" if fallback else "retain pre-holdout frozen configuration",
  candidate="config_000" if fallback else freeze["candidate"])
 if fallback:
  # The default's tuning proof was recorded before holdout, never fitted here.
  final["tiers"]=read_json(args.freeze_record.parent/"default_full_evaluation.json")["tiers"]
 save(output/"final_freeze_record.json",final)
 report.update(status="FALLBACK_DEFAULT" if fallback else "COMPLETE",config_sha256=final["config_sha256"],
  final_freeze_record=str(output/"final_freeze_record.json"),
  candidate_pass=layers["frozen"]["hard"]["passed"],default_pass=layers["default"]["hard"]["passed"],
  default_fallback=fallback,comparative_evaluation_count=1)
 save(output/"report.json",report)
 print(json.dumps(dict(status=report["status"],comparable=len(comparable),fallback=fallback)),flush=True)
 return 0

if __name__=="__main__":raise SystemExit(main())
