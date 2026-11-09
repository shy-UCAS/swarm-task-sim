"""V8-20 reporting dispatch. Production reports are completed in execution part 4."""


def phase_durations(res):
    raise NotImplementedError("V8-20 phase reports: execution part 4 not completed")


def phase_diagnostics(res, ctx):
    raise NotImplementedError("V8-20 phase diagnostics: execution part 4 not completed")


def group_reference_curves(ctx, group, res):
    raise NotImplementedError("V8-20 group-mean Frechet: execution part 4 not completed")


"""Part-3 geometry smoke: registered draws only; no optimization or tracking."""
import hashlib
import json
import os
import time
import traceback
from pathlib import Path


def smoke_geometry(entries,*,keys,data_root,cache_dir,out_dir):
    from ..contract.monitoring import initial_states
    from ..contract.single_intent import area_search_mission
    from ..motion.area_search_geometry import VERSION,sector_identity,write_sector_cache
    from ..motion.intents import area_search as A
    from ..sampler.common import sample_common
    from ..sampler.keys import RngKey
    from ..scene.context import load_context
    from .monitoring import jsonable,write_json
    out=Path(out_dir);by={int(e["order"]):e for e in entries}
    rows=[];started=time.perf_counter()
    code=Path(__file__).resolve().parents[2]
    write_json(out/"source_sha256.json",{str(p.relative_to(code)):hashlib.sha256(p.read_bytes()).hexdigest()
        for root in (code/"v08",code/"tools/v08") for p in root.rglob("*.py")},indent=1)
    for order,draw in keys:
        entry=by[int(order)];folder=out/f"o{order:02d}_d{draw}"
        folder.mkdir()
        start=time.perf_counter();ctx=None;key=None;plan=None
        row={"order":int(order),"draw":int(draw),"attempt":0,"group_size":None,"status":"running","failure":None,"split_depths_m":{}}
        write_json(folder/"query.json",row,indent=1)
        try:
            ctx=load_context(entry,data_root=Path(data_root),cache_dir=Path(cache_dir))
            mission=area_search_mission(ctx,sample_common(ctx.family,draw));group,task=mission.groups[0],mission.tasks[0]
            key=RngKey(ctx.family.family_id,int(draw),"shape",mission=0,branch=None,group=group.group_id,segment=0,attempt=0)
            row.update(group_size=len(group.member_ids),formation_prior=group.formation_prior,target_id=task.target_id,
                       altitude_m=ctx.family.task_altitude_m)
            print(f"START smoke o{order:02d}_d{draw}: N={len(group.member_ids)} prior={group.formation_prior}",flush=True)
            plan=A.propose_and_build(ctx,group,task,initial_states(ctx.family,group.member_ids),key)
            row.update(status="skeleton_ok" if plan.failure is None else "ordinary_candidate_failure",
                       failure=None if plan.failure is None else jsonable(plan.failure),telemetry=A.last_attempt_timing(),
                       split_depths_m=A.last_attempt_timing().get("split_depths_m",{}),proposal=jsonable(plan.proposal))
            write_json(folder/"plan.json",jsonable(plan),indent=1)
        except Exception as error:
            row.update(status="implementation_exception",error_type=type(error).__name__,traceback=traceback.format_exc(),
                       telemetry=A.last_attempt_timing(),split_depths_m=A.last_attempt_timing().get("split_depths_m",{}))
        if ctx is not None and row["group_size"] is not None:
            qid,_=sector_identity(ctx,task.target_id,len(group.member_ids),ctx.family.task_altitude_m)
            cache_key=(VERSION,"sectors",qid)
            if cache_key in ctx.extra:
                row["pure_sector_cache"]=write_sector_cache(ctx,task.target_id,len(group.member_ids),ctx.family.task_altitude_m)
                row["maximum_feasible_span_deg"]=max((c["span_deg"] for c in ctx.extra[cache_key]),default=None)
        row["wall_s"]=time.perf_counter()-start
        shallow={m:d for m,d in row["split_depths_m"].items() if d<10.}
        row["split_depth_stop"]=shallow
        write_json(folder/"query.json",row,indent=1)
        rows.append(row)
        write_json(out/"records.json",rows,indent=1)
        print(json.dumps({k:row.get(k) for k in ("order","draw","status","wall_s","split_depths_m","split_depth_stop")},ensure_ascii=False),flush=True)
        if shallow or row["status"]=="implementation_exception":
            summary={"complete":False,"stage":"smoke","intent":"area_search","rows":len(rows),"planned":len(keys),
                     "wall_s":time.perf_counter()-started,"checkpoint":{"triggered":["split_start_depth_below_10"] if shallow else ["implementation_exception"]},"p0":[]}
            write_json(out/"summary.json",summary,indent=1)
            return summary
    summary={"complete":True,"stage":"smoke","intent":"area_search","rows":len(rows),"planned":len(keys),
             "wall_s":time.perf_counter()-started,"checkpoint":{"triggered":[]},"p0":[]}
    write_json(out/"summary.json",summary,indent=1)
    return summary
