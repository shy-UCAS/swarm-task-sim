"""Area-search phases, group reference diagnostics, and production contract adapter."""
import json
import math
import time
import traceback
from pathlib import Path

import numpy as np

PHASES=("ingress","warning_before_split","scan","before_exit","withdrawal")
SCOPE="area_search_warning_entry_to_last_exit_v20"


def member_phase_times(res,mid):
    nom=res["opt"]["maps"][mid]["nominal"]
    phase=res["opt"]["maps"][mid]["phase_s"]
    at=lambda s:float(np.interp(s,nom.curve.s,nom.t_nodes))+nom.release_s
    return (nom.release_s,at(phase["warning_entry_s"]),at(phase["split_s"]),at(phase["scan_end_s"]),
            at(phase["warning_exit_s"]),nom.release_s+nom.travel_s)


def phase_durations(res):
    from ..config import load_config
    sim=load_config("sim").values
    out={}
    for mid in sorted(res["plan"].members):
        times=member_phase_times(res,mid);values=np.diff(times)
        nom=res["opt"]["maps"][mid]["nominal"];phase=res["opt"]["maps"][mid]["phase_s"]
        at=lambda s:float(np.interp(s,nom.curve.s,nom.t_nodes))+nom.release_s
        delay=float(res["plan"].members[mid].release_delay_s)
        out[mid]={name+"_s":float(v) for name,v in zip(PHASES,values)}
        out[mid].update(travel_s=float(times[-1]-times[0]),release_s=float(times[0]),release_delay_s=delay,
            pre_release_hold_s=float(sim["initial_settle_s"]),terminal_hold_s=float(sim["terminal_hold_s"]),
            release_quantization_s=float(times[0]-sim["initial_settle_s"]-delay),
            closure_residual_s=float(sum(values)-(times[-1]-times[0])),
            pure_scan_s=float(at(phase["scan_end_s"])-at(phase["scan_start_s"])))
    return out


def phase_diagnostics(res,ctx):
    from ..diagnostics.monitoring_skeleton import phase_metrics
    from ..motion.skeleton import NominalPVA
    observed=res["measured_area_search"]
    out={}
    for mid in sorted(res["plan"].members):
        nom=res["opt"]["maps"][mid]["nominal"]
        times=member_phase_times(res,mid);tr=res["tracks"][mid]
        tau=np.asarray(tr.tau_us)/1e6
        mask=(tau>=times[0])&(tau<=times[-1]);tt=tau[mask]
        rp,rv,_=NominalPVA(nom)(tt)
        station=np.interp(tt-nom.release_s,nom.t_nodes,nom.curve.s)
        delta=np.diff(nom.curve.xy,axis=0);tangent=delta/np.linalg.norm(delta,axis=1)[:,None]
        ix=np.clip(np.searchsorted(nom.curve.s,station,side="right")-1,0,len(tangent)-1)
        opt=res["opt"]["solution"].references[mid]
        bounds={name:(times[i],times[i+1],i==4) for i,name in enumerate(PHASES)}
        metrics=phase_metrics(tt,rp,rv,opt.evaluate(tt),opt.evaluate(tt,1),
            np.asarray(tr.p)[mask,:2],np.asarray(tr.v)[mask,:2],bounds,tangent[ix])
        measured=observed["members"][mid]
        out[mid]={"phases":metrics,"nominal_times_s":list(map(float,times)),
            "release_offset_s":res["release_us"][mid]/1e6-nom.release_s,
            "max_target_layer":measured["max_target_layer"],"end_target_layer":measured["end_target_layer"]}
    return out


def _operation_window(ctx,res,after):
    from ..motion.connect import crossing_analysis
    from ..motion.skeleton import NominalPVA
    target=res["plan"].witnesses["target_id"]
    warning=ctx.facility_by_id[target].layers["warning"]
    events=[]
    for mid in sorted(res["plan"].members):
        nom=res["opt"]["maps"][mid]["nominal"]
        if after:
            tr=res["opt"]["solution"].references[mid]
            times=np.unique(np.r_[tr.release_s,np.arange(math.ceil(tr.release_s*10),math.floor(tr.end_s*10)+1)/10,tr.end_s])
            xy=tr.evaluate(times,0)
        else:
            xy=np.asarray(nom.curve.xy)
            times=np.asarray(nom.t_nodes)+nom.release_s
        _,crossings=crossing_analysis(xy,{target:warning},target,
            band_m=ctx.params["pre_entry_warning_clearance_m"],align_m=ctx.params["alignment_length_m"])
        selected=[c for c in crossings if c.facility_id==target]
        if [c.direction for c in selected]!=["in","out"]:
            return None,{"na_reason":"member_not_single_crossing","member":mid}
        stations=np.r_[0.,np.cumsum(np.hypot(*np.diff(xy,axis=0).T))]
        for c in selected:
            if after:
                event=float(np.interp(c.s_m,stations,times))
            else:
                event=NominalPVA(nom).time_at_s(c.s_m)
            events.append((c.direction,event))
    lo=min(t for d,t in events if d=="in");hi=max(t for d,t in events if d=="out")
    boundary_times=[t for _,t in events]
    tt=np.unique(np.r_[lo,np.arange(math.ceil(lo*10),math.floor(hi*10)+1)/10,boundary_times,hi])
    return tt,{"window_start_s":float(lo),"window_end_s":float(hi),"boundary_times_s":boundary_times}


def group_reference_curves(ctx,group,res):
    from ..motion.skeleton import NominalPVA
    from .transit_report import FRECHET_SPACING_M,_cut_resample
    curves={};info={"scope":SCOPE}
    for name,after in (("before",False),("after",True)):
        times,meta=_operation_window(ctx,res,after)
        if times is None:
            curves[name]=None;info[name]=meta;continue
        before=[];displacements=[]
        for mid in sorted(res["plan"].members):
            nom=res["opt"]["maps"][mid]["nominal"]
            reference=NominalPVA(nom)(times)[0]
            before.append(reference)
            tr=res["opt"]["solution"].references[mid]
            optimized=tr.evaluate(np.clip(times,tr.release_s,tr.end_s),0)
            displacements.append(optimized-reference)
        xy=np.mean(before,axis=0)
        if after:
            xy=xy+np.mean(displacements,axis=0)
        keep=np.r_[True,np.any(np.diff(xy,axis=0)!=0.,axis=1)];xy=xy[keep]
        length=float(np.cumsum(np.hypot(*np.diff(xy,axis=0).T))[-1]) if len(xy)>1 else 0.
        if length==0.:
            curves[name]=None;info[name]={**meta,"na_reason":"zero_group_mean_length"};continue
        curves[name]=_cut_resample(xy,0.,length,FRECHET_SPACING_M)
        info[name]={**meta,"length_m":length,"n_points":len(curves[name]),
                    "start_xy":curves[name][0].tolist(),"end_xy":curves[name][-1].tolist()}
    return {"before":curves["before"],"after":curves["after"],"info":info}


def result_block(plan,measured):
    from .area_search_serialization import RESULT_BLOCK,project
    p=plan.proposal;members={}
    for mid in sorted(plan.members):
        w=plan.witnesses["independent_members"][mid]
        cs=np.asarray(w["curve_s"]);xy=np.asarray(plan.members[mid].curve_xy)
        cut=[float(np.interp(w["split_s"],cs,xy[:,axis])) for axis in (0,1)]
        allowed=("warning_entry_count","warning_exit_count","first_warning_entry_us","first_warning_exit_us",
            "first_effective_frame_index","first_effective_us","effective_frame_count","azimuth_span_deg","max_target_layer",
            "end_target_layer","ended_outside_all_warning","dwell_margin_m","dwell_window_start_us","dwell_window_confirm_us")
        members[mid]={**{k:measured["members"][mid][k] for k in allowed},"block_index":w["block_index"],
            "strip_indices":w["strip_indices"],"strip_count":int(p["c"]),"slot_xy":w["slot_xy"],"split_point_xy":cut}
    out={k:p[k] for k in ("beta_deg","Q","mu_deg","span_deg","c","K")}
    out.update(survey=plan.witnesses["survey"],members=members,coverage=measured["coverage"])
    return project(out,RESULT_BLOCK,"area_search")


def run_contract(ctx,entry,draw,*,settings,branch=None,out_dir=None,should_stop=None,keep=None):
    from . import joint_monitoring as JM,joint_report as JR
    from .joint_intent import _intent_attempt_summary
    from .area_search_serialization import project_attempt,validate_survey
    from ..contract.monitoring import initial_states
    from ..contract.single_intent import area_search_mission
    from ..motion.intents import area_search as A
    from ..motion.area_search_checks import measured_area_search
    from ..sampler.common import sample_common
    from ..sampler.keys import RngKey
    mission=area_search_mission(ctx,sample_common(ctx.family,int(draw)))
    group,task=mission.groups[0],mission.tasks[0]
    states=initial_states(ctx.family,group.member_ids)
    key0=RngKey(ctx.family.family_id,int(draw),"shape",mission=0,branch=branch,group=group.group_id,segment=0)
    summaries=[]
    def attempt(key):
        _attempt_progress(out_dir,JM.contract_id(entry,draw,branch),key.attempt,"starting")
        try:
            rec=JM.attempt_chain(ctx,group,task,states,key,settings)
        except Exception:
            _attempt_progress(out_dir,JM.contract_id(entry,draw,branch),key.attempt,"implementation_exception",traceback.format_exc())
            raise
        s=_intent_attempt_summary(rec,key,"area_search")
        plan=rec.get("plan")
        if plan is not None and plan.proposal:
            formation=(plan.formation or {}).get("realized")
            if formation is None and plan.proposal.get("formation_steps"):
                formation=plan.proposal["formation_steps"][-1]["formation"]
            s["draw"]=A.draw_summary(plan.proposal,formation)
        opt=rec.get("opt")
        if opt is not None and opt.get("semantic") is not None:
            sem=opt["semantic"]
            s["optimize"].update(semantic_members=sem["nominal_members"],semantic_boundaries=sem["boundaries"],
                nominal_group=sem["nominal_group"],optimized_nominal_screen=sem["optimized_nominal_screen"])
        if rec.get("measured_area_search") is not None:
            s["measured_area_search"]=rec["measured_area_search"]
        summaries.append(project_attempt(s))
        _attempt_progress(out_dir,JM.contract_id(entry,draw,branch),key.attempt,rec["stage"])
        return rec
    outcome=JM.run_attempts(key0,attempt,should_stop=should_stop)
    counters=JR.attempt_counters(summaries)
    failure=None
    if outcome.get("incomplete"):
        failure={"code":"incomplete_deadline","reason":"cooperative_budget","feasible_set":None,"witness":{"attempts_done":outcome["attempts"]}}
    elif not outcome["success"]:
        stages=[{"stage":s.get("skeleton_stage") if s["stage"]=="skeleton" else s["stage"]} for s in summaries]
        f=A.final_failure(ctx,group,task,stages)
        failure={"code":f.code,"reason":f.reason,"feasible_set":f.feasible_set,"witness":f.witness}
    selected=outcome["result"] if outcome["success"] else None
    survey,survey_attempt=_formed_survey(outcome["records"])
    if survey is not None:
        survey=validate_survey(survey)
    rec={"contract_id":JM.contract_id(entry,draw,branch),"intent":"area_search","family_id":ctx.family.family_id,
        "order":int(entry["order"]),"draw_index":int(draw),"branch":branch,"facility_count":int(entry["facility_count"]),
        "vehicle_count":int(ctx.family.vehicle_count),"lateral_spacing_m":float(ctx.family.lateral_spacing_m),
        "group_id":group.group_id,"member_ids":sorted(group.member_ids),"group_size":len(group.member_ids),"target_id":task.target_id,
        "initial_speed_m_s":float(group.speed_profile.initial_speed_m_s),"formation_prior":group.formation_prior,
        "success":bool(outcome["success"]),"attempts":outcome["attempts"],"failure":failure,"attempt_log":summaries,
        "settings_sha256":settings.get("_sha256"),"release_us":None,"retained_p0_ok":False,
        "incomplete":bool(outcome.get("incomplete",False)),"optimization_s":float(sum(s["timing"].get("optimize_s",0.) for s in summaries)),
        "post_optimization_failures":counters["post_optimization_failures"],"skeleton_failures":counters["skeleton_failures"],
        "unknown_attempts":counters["unknown_attempts"],"shape_audit_failed_attempts":sum(bool(s.get("shape_audit_failed")) for s in summaries),
        "draws":[s.get("draw") for s in summaries],"survey":survey,"survey_attempt":survey_attempt,"area_search":None}
    rec["stage_timing"]={k:float(sum(s["timing"].get(k,0.) for s in summaries)) for k in ("skeleton_s","optimize_s","simulation_s","verify_s")}
    if selected is not None:
        plan=selected["plan"]
        measured=measured_area_search(ctx,selected["tracks"],selected["release_us"],task.target_id,survey)
        selected["measured_area_search"]=measured
        rec.update(release_us={m:int(v) for m,v in sorted(selected["release_us"].items())},
            retained_p0_ok=bool(JM._retained_p0(selected) and measured["passed"]),
            area_search=result_block(plan,measured),deviation=JM.member_deviation(selected),tracking=JM.tracking_stats(selected),
            phase_metrics=phase_diagnostics(selected,ctx),phase_durations=phase_durations(selected),nominal_duration_s=float(plan.nominal_duration_s),
            formation={k:plan.formation.get(k) for k in ("prior","start","realized","mapped_from_loose","lateral_step_m")},
            topology={"final":"area_search"})
        if keep is not None:
            keep["result"]=selected
    if out_dir is not None:
        last=outcome["records"][-1] if outcome["records"] and not outcome["success"] else None
        save_contract(Path(out_dir),rec,selected,last_failed=last)
    return rec


def save_contract(out,rec,result,last_failed=None):
    from . import joint_monitoring as JM
    from .monitoring import jsonable,plan_to_record
    from .area_search_serialization import assert_contract_payload
    def encoded(value):
        value=jsonable(value);assert_contract_payload(value)
        return JM._json_bytes(value)
    contract={k:rec[k] for k in ("contract_id","intent","family_id","order","draw_index","branch","facility_count","vehicle_count",
        "group_id","member_ids","group_size","target_id","initial_speed_m_s","formation_prior","survey","survey_attempt")}
    result_doc={k:rec.get(k) for k in ("intent","success","attempts","failure","release_us","settings_sha256","retained_p0_ok","incomplete",
        "post_optimization_failures","skeleton_failures","unknown_attempts","shape_audit_failed_attempts","deviation","tracking",
        "nominal_duration_s","formation","topology","phase_metrics","phase_durations","survey","survey_attempt","area_search")}
    result_doc["attempt_log"]=[{k:v for k,v in row.items() if k not in ("timing","traceback")} for row in rec["attempt_log"]]
    payloads={"contract.json":encoded(contract),"result.json":encoded(result_doc)}
    if result is not None:
        prec,arrays=plan_to_record(result["plan"])
        for value in arrays.values():
            if np.asarray(value).dtype.hasobject or not np.issubdtype(np.asarray(value).dtype,np.number):
                raise ValueError("nonnumeric plan array")
        prec["arrays"]={k:np.asarray(v).tolist() for k,v in sorted(arrays.items())}
        payloads["skeleton.json"]=encoded(prec)
        sol=result["opt"]["solution"]
        turns=result["opt"]["problem"].turns
        ranges=result["plan"].witnesses["turn_ranges"]
        if len(turns)!=sum(len(items) for items in ranges.values()) or any(not any(t[0]==mid for t in turns) for mid in ranges):
            raise ValueError("U constraints were lost before saving")
        optimized={"members":{m:{"release_s":tr.release_s,"end_s":tr.end_s,"altitude_m":tr.altitude_m,"knots":tr.knots,"controls":tr.controls}
                      for m,tr in sorted(sol.references.items())},"turns":jsonable(turns),"lines":jsonable(result["opt"]["lines"]),"lines_raw":jsonable(result["opt"].get("lines_raw")),
            "diagnostics":{k:jsonable(sol.diagnostics.get(k)) for k in ("nit","nfev","message","value","terms","max_abs_grad","reference_deviation","symmetry_break","settings_sha256")}}
        payloads["optimized.json"]=encoded(optimized)
    if last_failed is not None and last_failed.get("plan") is not None and last_failed["plan"].failure is None:
        failed={"stage":last_failed.get("stage"),"reason":last_failed.get("reason"),
            "survey":rec["survey"],"survey_attempt":rec["survey_attempt"],
            "skeleton_members":{m:np.asarray(mp.curve_xy).tolist() for m,mp in sorted(last_failed["plan"].members.items())}}
        opt=last_failed.get("opt")
        if opt is not None:
            failed["optimized"]={m:{"release_s":tr.release_s,"end_s":tr.end_s,"knots":tr.knots,"controls":tr.controls} for m,tr in sorted(opt["solution"].references.items())}
            failed["physical_failures"]=(opt["solution"].diagnostics.get("physical") or {}).get("failures")
            if opt.get("semantic") is not None:
                failed["semantic_failures"]=opt["semantic"]["failures"]
        if last_failed.get("measured_area_search") is not None:
            failed["measured_area_search"]=last_failed["measured_area_search"]
        if last_failed.get("tracks") is not None:
            failed["tracks_p"]={m:np.asarray(tr.p)[:,:2].tolist() for m,tr in sorted(last_failed["tracks"].items())}
        if last_failed.get("validity") is not None:
            failed["validity_codes"]=last_failed["validity"].codes
        if last_failed.get("verdicts") is not None:
            failed["segment_failures"]=[v.failures for v in last_failed["verdicts"]]
        payloads["failure_witness.json"]=encoded(failed)
    folder=out/"contracts"/rec["contract_id"];folder.mkdir(parents=True,exist_ok=False)
    for name,data in payloads.items():
        (folder/name).write_bytes(data)
    if result is not None:
        for mid,track in sorted(result["tracks"].items()):
            target=folder/"tracks"/mid;target.mkdir(parents=True,exist_ok=False)
            for name in ("tau_us","p","v","a","segment_index"):
                array=np.ascontiguousarray(getattr(track,name))
                if array.dtype.hasobject or not np.issubdtype(array.dtype,np.number):
                    raise ValueError("nonnumeric measured array")
                np.save(target/(name+".npy"),array,allow_pickle=False)
    telemetry=out/"telemetry";telemetry.mkdir(exist_ok=True)
    (telemetry/(rec["contract_id"]+".json")).write_bytes(JM._json_bytes({"timing":[s.get("timing") for s in rec["attempt_log"]],
        "optimization_s":rec["optimization_s"],"tracebacks":[s["traceback"] for s in rec["attempt_log"] if s.get("traceback")]}))


def verify_saved_outputs(root,entries,data_root,cache):
    """Reload tracks and independently invoke frozen geometry, verifier and coverage."""
    from task_v07.detectors import azimuth_coverage
    from ..criteria.segment import SegmentTask,verify_segments
    from ..criteria.validity import check_validity,visible_track
    from ..scene.context import load_context
    from ..scene.exact import signed_distance
    from ..sim.types import MemberTrack
    from .area_search_serialization import assert_contract_payload
    root=Path(root);rows=json.loads((root/"records.json").read_text(encoding="utf-8"))
    by={e["family_id"]:e for e in entries};contexts={};results=[];errors=[]
    for row in rows:
        cid=row["contract_id"];folder=root/"contracts"/cid
        for p in folder.rglob("*.json"):
            assert_contract_payload(json.loads(p.read_text(encoding="utf-8")))
        saved=json.loads((folder/"result.json").read_text(encoding="utf-8"))
        contract=json.loads((folder/"contract.json").read_text(encoding="utf-8"))
        if saved["success"]!=row["success"] or contract["survey"]!=saved["survey"] or contract["survey_attempt"]!=saved["survey_attempt"]:
            errors.append({"contract_id":cid,"reason":"saved_status_or_survey_mismatch"})
        if not row["success"]:
            continue
        if row["family_id"] not in contexts:
            contexts.clear();contexts[row["family_id"]]=load_context(by[row["family_id"]],data_root=Path(data_root),cache_dir=Path(cache))
        ctx=contexts[row["family_id"]];target=ctx.facility_by_id[row["target_id"]]
        tracks={};good=True
        for mid in row["member_ids"]:
            arrays={k:np.load(folder/"tracks"/mid/(k+".npy"),allow_pickle=False) for k in ("tau_us","p","v","a","segment_index")}
            tracks[mid]=MemberTrack(mid,arrays["tau_us"],arrays["p"],arrays["v"],arrays["a"],arrays["segment_index"],())
            good=good and np.issubdtype(arrays["tau_us"].dtype,np.integer) and bool(np.all(np.diff(arrays["tau_us"])==100000))
            good=good and bool(np.all(arrays["segment_index"]==0)) and all(np.isfinite(arrays[k]).all() for k in ("p","v","a"))
        verdicts=verify_segments(ctx.scene,tracks,saved["release_us"],[SegmentTask(0,"area_search",row["target_id"],survey=contract["survey"])])
        validity=check_validity(ctx.scene,[visible_track(tracks[m],saved["release_us"][m]) for m in sorted(tracks)])
        good=good and all(v.passed for v in verdicts) and validity.passed and saved["retained_p0_ok"]
        from .area_search_serialization import area_plan_from_record
        from ..motion.area_search_reference import references_area_search
        from ..motion.optimize import turns_from_skeleton
        from ..config import load_config
        plan_record=json.loads((folder/"skeleton.json").read_text(encoding="utf-8"))
        restored=area_plan_from_record(plan_record)
        _,_,maps=references_area_search(restored)
        expected_turns=turns_from_skeleton(restored,maps,load_config("monitoring").values)
        optimized=json.loads((folder/"optimized.json").read_text(encoding="utf-8"))
        from .monitoring import jsonable
        good=good and optimized["turns"]==jsonable(expected_turns)
        verdict=verdicts[0]
        good=good and saved["area_search"]["survey"]==contract["survey"] and saved["area_search"]["coverage"]==verdict.group["shared_coverage"]
        for mid,track in tracks.items():
            mask=(track.tau_us>=saved["release_us"][mid])&(track.segment_index==0)
            times=track.tau_us[mask];xy=track.p[mask,:2]
            inside=np.asarray(signed_distance(target.geometry,xy))<=target.offsets["warning"]
            starts=np.flatnonzero(inside&~np.r_[False,inside[:-1]])
            exits=np.flatnonzero(~inside&np.r_[False,inside[:-1]])
            info=saved["area_search"]["members"][mid]
            good=good and len(starts)==1 and len(exits)==1 and not bool(inside[0])
            if len(starts)==1 and len(exits)==1:
                good=good and info["warning_entry_count"]==1 and info["warning_exit_count"]==1
                good=good and info["first_warning_entry_us"]==int(times[starts[0]]) and info["first_warning_exit_us"]==int(times[exits[0]])
            good=good and info["azimuth_span_deg"]==azimuth_coverage(xy[inside],target.center)
            for facility in ctx.facilities:
                good=good and float(signed_distance(facility.geometry,xy[-1]))>facility.offsets["warning"]
            window=verdict.windows[mid];effective=np.flatnonzero(window.coverage["effective_mask"])
            good=good and len(effective)>0 and info["effective_frame_count"]==len(effective)
            if len(effective):
                good=good and info["first_effective_frame_index"]==int(effective[0]) and info["first_effective_us"]==int(window.time_us[effective[0]])
        results.append({"contract_id":cid,"passed":bool(good),"min_separation_m":validity.min_separation_m})
        if not good:
            errors.append({"contract_id":cid,"reason":"retained_disk_reverification_failed"})
    return {"passed":not errors,"all_checked":len(rows),"checked_successes":len(results),"results":results,"p0_violations":errors}


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
        row["split_depth_below_10"]=shallow
        write_json(folder/"query.json",row,indent=1)
        rows.append(row)
        write_json(out/"records.json",rows,indent=1)
        print(json.dumps({k:row.get(k) for k in ("order","draw","status","wall_s","split_depths_m","split_depth_below_10")},ensure_ascii=False),flush=True)
        if row["status"]=="implementation_exception":
            summary={"complete":False,"stage":"smoke","intent":"area_search","rows":len(rows),"planned":len(keys),
                     "wall_s":time.perf_counter()-started,"checkpoint":{"triggered":["implementation_exception"]},"p0":[]}
            write_json(out/"summary.json",summary,indent=1)
            return summary
    summary={"complete":True,"stage":"smoke","intent":"area_search","rows":len(rows),"planned":len(keys),
             "wall_s":time.perf_counter()-started,"checkpoint":{"triggered":[]},"p0":[]}
    write_json(out/"summary.json",summary,indent=1)
    return summary


def _durable_json(path,value):
    import os
    from .monitoring import jsonable
    path=Path(path)
    with path.open("w",encoding="utf-8",newline="\n") as f:
        json.dump(jsonable(value),f,ensure_ascii=False,indent=1);f.write("\n");f.flush();os.fsync(f.fileno())


def _bounded_dispatch(worker,tasks,*,workers,out,wall_limit=None,log=print):
    """One task per work item; only this task's pool is terminated at a hard stop."""
    import multiprocessing as mp
    tasks=list(tasks);rows=[];started=time.perf_counter();stopped=False
    pool=mp.get_context("spawn").Pool(processes=workers)
    try:
        iterator=pool.imap_unordered(worker,tasks,chunksize=1)
        while len(rows)<len(tasks):
            if wall_limit is not None and time.perf_counter()-started>wall_limit:
                stopped=True;pool.terminate();break
            try:
                row=iterator.next(timeout=1.)
            except mp.TimeoutError:
                continue
            rows.append(row)
            _durable_json(Path(out)/"partial_records.json",rows)
            log(f"[{len(rows)}/{len(tasks)}] {row.get('contract_id',row.get('order'))}: success={row.get('success')} wall={row.get('wall_s')} error={row.get('error')}",flush=True)
        if not stopped:
            pool.close()
    except BaseException:
        pool.terminate()
        raise
    finally:
        pool.join()
    return rows,{"wall_s":time.perf_counter()-started,"hard_stop":stopped,"wall_limit_s":wall_limit}


def _prewarm_family(task):
    from ..contract.single_intent import area_search_mission
    from ..motion import transit_chords as TC
    from ..motion.area_search_geometry import write_sector_cache,sector_identity
    from ..motion.intents.transit import formation_probe_sequence
    from ..sampler.common import sample_common
    from ..sampler.keys import RngKey
    from ..scene.context import load_context
    entry,draws,data_root,cache_dir=task[:4]
    started=time.perf_counter()
    ctx=load_context(entry,data_root=Path(data_root),cache_dir=Path(cache_dir))
    reqs=[];seen=set();sector_rows=[];sector_seen=set();sizes={};probes={}
    for draw in draws:
        mission=area_search_mission(ctx,sample_common(ctx.family,int(draw)))
        group,spec=mission.groups[0],mission.tasks[0]
        sizes[f"{int(entry['order'])}:{draw}"]=len(group.member_ids)
        key=RngKey(ctx.family.family_id,int(draw),"shape",mission=0,branch=None,group=group.group_id,segment=0)
        seq=formation_probe_sequence(ctx,group,spec,key,chord_intent="area_search")
        probes[int(draw)]={"target":spec.target_id,"probes":[[name,step,None] for name,step,_ in seq]}
        for _,_,offsets in seq:
            qid,_=TC.query_identity(ctx,spec.target_id,offsets,intent="area_search")
            if qid not in seen:
                seen.add(qid);reqs.append((spec.target_id,offsets))
        qid,_=sector_identity(ctx,spec.target_id,len(group.member_ids),ctx.family.task_altitude_m)
        if qid not in sector_seen:
            sector_seen.add(qid);begin=time.perf_counter()
            row=write_sector_cache(ctx,spec.target_id,len(group.member_ids),ctx.family.task_altitude_m)
            sector_rows.append({**row,"seconds":time.perf_counter()-begin,"target":spec.target_id,"members":len(group.member_ids)})
    chords=TC.prewarm_transit(ctx,reqs,cache_dir,intent="area_search")
    return {"order":int(entry["order"]),"family_id":entry["family_id"],"wall_s":time.perf_counter()-started,
            "queries":chords,"sector_queries":sector_rows,"raw_cache":ctx.cache_stats(),"sizes":sizes,"probes":probes}


def _prewarm_worker(task):
    try:
        return _prewarm_family(task)
    except Exception as error:
        return {"order":int(task[0]["order"]),"error":type(error).__name__,"traceback":traceback.format_exc()}


def prewarm_all(entries,*,data_root,cache_dir,workers,out_dir,draws=range(5),log=print):
    from ..motion.area_search_geometry import SECTOR_RULE
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=False)
    draws=tuple(draws)
    tasks=[(entry,draws,str(data_root),str(cache_dir),"area_search") for entry in sorted(entries,key=lambda e:e["order"])]
    rows,timing=_bounded_dispatch(_prewarm_worker,tasks,workers=workers,out=out,wall_limit=2700.,log=log)
    rows.sort(key=lambda r:r["order"])
    sizes={key:value for row in rows for key,value in row.get("sizes",{}).items()}
    result={"intent":"area_search","sector_rule":SECTOR_RULE,"cache_root":str(Path(cache_dir).resolve()),"data_root":str(Path(data_root).resolve()),
            "workers":workers,"wall_s":timing["wall_s"],"rows":rows,"group_size":sizes,
            "complete":len(rows)==len(tasks) and len(sizes)==len(entries)*len(draws) and not timing["hard_stop"] and not any(r.get("error") for r in rows),
            "hard_stop":timing["hard_stop"],"wall_limit_s":2700.,"scope":"raw_fields_chord_sets_and_sector_tables_only",
            "chord_queries":sum(len(r.get("queries",[])) for r in rows),"sector_queries":sum(len(r.get("sector_queries",[])) for r in rows)}
    _durable_json(out/"prewarm.json",result)
    return result


def _formed_survey(records):
    for attempt,record in reversed(list(enumerate(records))):
        plan=record.get("plan")
        if plan is not None and (plan.witnesses or {}).get("survey") is not None:
            return plan.witnesses["survey"],attempt
    return None,None


def run_skeleton_contract(ctx,entry,draw,*,out_dir=None):
    from ..contract.monitoring import initial_states
    from ..contract.single_intent import area_search_mission
    from ..motion.intents import area_search as A
    from ..sampler.common import sample_common
    from ..sampler.keys import RngKey
    from . import joint_monitoring as JM
    from .monitoring import jsonable,plan_to_record
    from .area_search_serialization import SKEL_ATTEMPT,project,assert_contract_payload
    started=time.perf_counter()
    mission=area_search_mission(ctx,sample_common(ctx.family,int(draw)));group,task=mission.groups[0],mission.tasks[0]
    states=initial_states(ctx.family,group.member_ids)
    key=RngKey(ctx.family.family_id,int(draw),"shape",mission=0,branch=None,group=group.group_id,segment=0)
    logs=[];telemetry=[]
    def attempt(k):
        _attempt_progress(out_dir,JM.contract_id(entry,draw),k.attempt,"starting")
        try:
            plan=A.propose_and_build(ctx,group,task,states,k)
        except Exception:
            _attempt_progress(out_dir,JM.contract_id(entry,draw),k.attempt,"implementation_exception",traceback.format_exc())
            raise
        timing=A.last_attempt_timing();telemetry.append(timing)
        failure=plan.failure
        stage="skeleton_ok" if failure is None else (failure.witness or {}).get("stage",failure.feasible_set)
        row={"attempt":k.attempt,"ok":failure is None,"stage":stage,"code":None if failure is None else failure.code,
            "reason":None if failure is None else failure.reason,"feasible_set":None if failure is None else failure.feasible_set,
            "shape_audit_failed":bool((failure.witness or {}).get("shape_audit_failed",False)) if failure is not None else False,"draw":A.draw_summary(plan.proposal,(plan.formation or {}).get("realized")),
            "formation_steps":(plan.proposal or {}).get("formation_steps",(failure.witness or {}).get("formations",[]) if failure else []),
            "bone_nominal_screen":(plan.witnesses or {}).get("bone_nominal_screen"),"split_depths_m":timing.get("split_depths_m",{}),
            "split_depth_rejected":bool(timing.get("split_depth_rejected",False)),"witness":None if failure is None else failure.witness}
        logs.append(project(jsonable(row),SKEL_ATTEMPT,"skeleton_attempt"))
        _attempt_progress(out_dir,JM.contract_id(entry,draw),k.attempt,stage)
        return {"ok":failure is None,"stage":stage,"plan":plan}
    outcome=JM.run_attempts(key,attempt)
    failure=None
    if not outcome["success"]:
        f=A.final_failure(ctx,group,task,[{"stage":r["stage"]} for r in logs])
        failure={"code":f.code,"reason":f.reason,"feasible_set":f.feasible_set,"witness":f.witness}
    survey,survey_attempt=_formed_survey(outcome["records"])
    rec={"contract_id":JM.contract_id(entry,draw),"intent":"area_search","family_id":ctx.family.family_id,
        "order":int(entry["order"]),"draw_index":int(draw),"branch":None,"facility_count":int(entry["facility_count"]),
        "vehicle_count":int(ctx.family.vehicle_count),"lateral_spacing_m":float(ctx.family.lateral_spacing_m),
        "group_id":group.group_id,"member_ids":sorted(group.member_ids),"group_size":len(group.member_ids),"target_id":task.target_id,
        "initial_speed_m_s":float(group.speed_profile.initial_speed_m_s),"formation_prior":group.formation_prior,
        "success":bool(outcome["success"]),"attempts":int(outcome["attempts"]),"failure":failure,
        "attempt_log":logs,"shape_audit_failed_attempts":sum(row["shape_audit_failed"] for row in logs),"exceptions":0,"survey":survey,"survey_attempt":survey_attempt,
        "bone_nominal_screen":None,"area_search":None}
    if outcome["success"]:
        plan=outcome["result"]["plan"]
        rec.update(formation=plan.formation,topology=plan.topology,nominal_duration_s=plan.nominal_duration_s,
            bone_nominal_screen=plan.witnesses["bone_nominal_screen"])
    if out_dir is not None:
        folder=Path(out_dir)/"contracts"/rec["contract_id"];folder.mkdir(parents=True,exist_ok=False)
        contract={k:rec[k] for k in ("contract_id","intent","family_id","order","draw_index","branch","facility_count","vehicle_count",
            "group_id","member_ids","group_size","target_id","initial_speed_m_s","formation_prior","survey","survey_attempt")}
        result={k:rec[k] for k in ("intent","success","attempts","failure","attempt_log","shape_audit_failed_attempts","exceptions",
            "survey","survey_attempt","bone_nominal_screen","area_search")}
        for k in ("formation","topology","nominal_duration_s"):
            if k in rec:result[k]=rec[k]
        payloads={"contract.json":contract,"result.json":result}
        if outcome["success"]:
            prec,arrays=plan_to_record(outcome["result"]["plan"])
            prec["arrays"]={k:np.asarray(v).tolist() for k,v in sorted(arrays.items())};payloads["skeleton.json"]=prec
        for name,value in payloads.items():
            value=jsonable(value);assert_contract_payload(value);(folder/name).write_bytes(JM._json_bytes(value))
        tele=Path(out_dir)/"telemetry";tele.mkdir(exist_ok=True)
        _durable_json(tele/(rec["contract_id"]+".json"),{"attempts":telemetry,"wall_s":time.perf_counter()-started})
    return rec


def _skeleton_worker(task):
    from ..scene.context import load_context
    entry,draw,data_root,cache_dir,out_dir=task
    started=time.perf_counter()
    try:
        contexts=globals().setdefault("_AREA_SKELETON_CONTEXTS",{})
        if entry["order"] not in contexts:
            while len(contexts)>=3:contexts.pop(next(iter(contexts)))
            contexts[entry["order"]]=load_context(entry,data_root=Path(data_root),cache_dir=Path(cache_dir))
        rec=run_skeleton_contract(contexts[entry["order"]],entry,draw,out_dir=Path(out_dir))
        return {**rec,"wall_s":time.perf_counter()-started}
    except Exception as error:
        return {"contract_id":f"o{int(entry['order']):02d}_d{draw}","order":int(entry["order"]),"draw_index":draw,
                "success":False,"attempts":None,"error":type(error).__name__,"traceback":traceback.format_exc()}


def skeleton_checkpoint(records,*,wall_s,expected_count=200):
    from ..motion.area_search_numeric import skeleton_checkpoint_values
    rows=list(records)
    complete=len(rows)==expected_count and len({r["contract_id"] for r in rows})==expected_count and not any(r.get("error") or r.get("exceptions") for r in rows)
    if expected_count==200:
        complete=complete and {r["contract_id"] for r in rows}=={f"o{o:02d}_d{d}" for o in range(1,41) for d in range(5)}
    metrics=None;triggered=[]
    if complete:
        metrics=skeleton_checkpoint_values([r["success"] for r in rows],[r["group_size"] for r in rows],[r["attempts"] for r in rows],wall_s)
        triggered=list(metrics["triggered"])
    else:
        triggered=["incomplete"]
    depths=[depth for r in rows for a in r.get("attempt_log",[]) for depth in a.get("split_depths_m",{}).values()]
    attempts=[a for r in rows for a in r.get("attempt_log",[])]
    failed=[a for a in attempts if not a["ok"]];shallow=sum(bool(a.get("split_depth_rejected")) for a in failed)
    diagnostics={"split_depth_quantiles_m":None if not depths else np.quantile(depths,[0,.25,.5,.75,1.]).tolist(),
        "split_depth_observed_members":len(depths),"split_depth_rejected_attempts":shallow,"failed_attempts":len(failed),
        "split_depth_majority_of_failures":bool(failed and shallow>len(failed)/2),
        "bone_nominal_screen_failed_contracts":sum(r.get("success") and not (r.get("bone_nominal_screen") or {}).get("passed",False) for r in rows),
        "excluded_from_rate":[]}
    return {"complete":complete,"passed":complete and not triggered,"triggered":triggered,"metrics":metrics,"diagnostics":diagnostics}


def run_skeleton_batch(entries,*,data_root,cache_dir,out_dir,workers,prewarm_doc,log=print):
    out=Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise ValueError("skeleton output must be new or empty")
    out.mkdir(parents=True,exist_ok=True)
    if not prewarm_doc["complete"] or prewarm_doc["wall_s"]>2700.:
        raise ValueError("area-search combined prewarm checkpoint not passed")
    keys=[(entry,draw) for entry in entries for draw in range(5)]
    sizes=prewarm_doc["group_size"]
    keys.sort(key=lambda item:(-sizes[f"{int(item[0]['order'])}:{item[1]}"]*float(item[0]["map_side_m"]),int(item[0]["order"]),item[1]))
    _durable_json(out/"dispatch_order.json",[{"order":int(e["order"]),"draw":d} for e,d in keys])
    tasks=[(entry,draw,str(data_root),str(cache_dir),str(out)) for entry,draw in keys]
    rows,timing=_bounded_dispatch(_skeleton_worker,tasks,workers=workers,out=out,wall_limit=1800.,log=log)
    rows.sort(key=lambda r:r["contract_id"])
    _durable_json(out/"records.json",rows)
    checkpoint=skeleton_checkpoint(rows,wall_s=timing["wall_s"])
    if timing["hard_stop"] and "wall" not in checkpoint["triggered"]:
        checkpoint["triggered"].append("wall");checkpoint["passed"]=False
    summary={"intent":"area_search","stage":"skeleton","workers":workers,"complete":checkpoint["complete"],
        "expected_count":200,"completed":len(rows),"dispatch_wall_s":timing["wall_s"],"prewarm_wall_s":prewarm_doc["wall_s"],
        "checkpoint":checkpoint,"hard_stop":timing["hard_stop"],"p0":[]}
    _durable_json(out/"summary.json",summary)
    return summary


def quick_checkpoint(records):
    from .joint_report import quick_checkpoint as original
    rows=list(records);result=original(rows)
    # Only retained successes are in the P0 denominator. Failed contracts retain
    # their honest False flag and remain in every success/time denominator.
    bad=[r["contract_id"] for r in rows if r.get("success") and not r.get("retained_p0_ok")]
    result["triggered"]=[x for x in result["triggered"] if x!="retained_p0"]
    if bad:result["triggered"].append("retained_p0")
    result["metrics"]["retained_p0_violations"]=bad
    result["metrics"]["excluded_from_rate"]=[]
    return result


def full_checkpoint(records,frechet_blocks):
    from .joint_report import full_checkpoint as original
    result=original(list(records),frechet_blocks)
    result["metrics"]["frechet_pairs"]=sum(len(b["distances_m"]) for b in frechet_blocks)
    result["metrics"]["excluded_from_rate"]=[]
    return result


def chord_gate(entries,*,data_root,cache_dir,out_dir):
    from ..contract.single_intent import area_search_mission
    from ..motion import transit_chords as TC
    from ..motion.formation import formation_slots,mapped_start,retreat_chain
    from ..sampler.common import sample_common
    from ..sampler.keys import RngKey
    from ..scene.context import load_context
    from .monitoring import jsonable
    entry=next((e for e in entries if int(e["order"])==34),sorted(entries,key=lambda e:e["order"])[0])
    draw=3 if int(entry["order"])==34 else 0
    ctx=load_context(entry,data_root=Path(data_root),cache_dir=Path(cache_dir))
    mission=area_search_mission(ctx,sample_common(ctx.family,draw));group,task=mission.groups[0],mission.tasks[0]
    key=RngKey(ctx.family.family_id,draw,"formation",mission=0,branch=None,group=group.group_id,segment=0)
    slots=formation_slots(group,ctx.family,key,formation=retreat_chain(mapped_start(group.formation_prior))[0])
    offsets=[slots.offsets[m] for m in slots.order]
    a=TC.assess_formation(ctx,task.target_id,offsets,intent="area_search")
    b=TC.assess_formation(ctx,task.target_id,offsets,memo=False,intent="area_search")
    fields=("cells","reasons","n_cells")
    same=jsonable({k:a[k] for k in fields})==jsonable({k:b[k] for k in fields})
    result={"intent":"area_search","complete":True,"passed":same,"order":int(entry["order"]),"draw":draw,
            "checkpoint":{"triggered":[] if same else ["combined_direct_mismatch"]},"exclusions":[]}
    _durable_json(Path(out_dir)/"chord_gate.json",result)
    return result


def _attempt_progress(out_dir,contract_id,attempt,stage,error=None):
    if out_dir is None:
        return
    from ..motion.intents.area_search import last_attempt_timing
    folder=Path(out_dir)/"telemetry";folder.mkdir(parents=True,exist_ok=True)
    value={"attempt":int(attempt),"stage":stage,"last_geometry":last_attempt_timing()}
    if error is not None:value["traceback"]=error
    _durable_json(folder/(contract_id+".current_attempt.json"),value)
