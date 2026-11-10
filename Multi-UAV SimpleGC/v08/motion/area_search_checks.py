"""Area-search group coverage and independent nominal/measured facts."""
import math

import numpy as np

CONDITIONS=("started_outside_target_warning","single_warning_visit","max_target_layer_one",
            "other_layers_within_limit","no_dwell_window","azimuth_span_ok","no_revisit_window",
            "ended_outside_all_warning","effective_observation")


def screen_area_search(scene,facilities,target_id,samples,survey,criteria=None):
    # The frozen detector remains authoritative, including footprint and obstacle boundaries.
    from task_v07 import detectors
    from task_v07.criteria import load_criteria
    from task_v07.geometry import geometry_facts
    from task_v07.survey import survey_grid
    from .nominal_checks import layer_levels
    cfg=criteria if criteria is not None else load_criteria()
    facilities=list(facilities)
    target=next(f for f in facilities if f.id==target_id)
    member_conditions,member_facts={},{}
    grid=survey_grid(survey)
    union=np.zeros(len(grid),bool)
    for mid,sample in sorted(samples.items()):
        times=np.asarray(sample["time_us"])
        p,v=np.asarray(sample["p"],float),np.asarray(sample["v"],float)
        n=len(times)
        if times.ndim!=1 or not np.issubdtype(times.dtype,np.integer) or p.shape!=(n,3) or v.shape!=(n,3):
            raise ValueError("integer 10Hz time_us and (T,3) p/v required")
        if (n>1 and np.any(np.diff(times)!=100000)) or not (np.isfinite(p).all() and np.isfinite(v).all()):
            raise ValueError("nonfinite or non-10Hz samples")
        xy=p[:,:2]
        levels=np.column_stack([layer_levels(f,xy)[0] for f in facilities]) if facilities else np.zeros((n,0),np.int8)
        ti=next(j for j,f in enumerate(facilities) if f.id==target_id)
        tl=levels[:,ti]
        inside=tl>=1
        prior=np.r_[False,inside[:-1]] if n else np.zeros(0,bool)
        starts=np.flatnonzero(inside&~prior);exits=np.flatnonzero(~inside&prior)
        later=exits[exits>starts[0]] if len(starts) else np.zeros(0,int)
        selected=np.flatnonzero(inside)
        span=detectors.azimuth_coverage(xy[selected[0]:selected[-1]+1],np.asarray(target.center)) if len(selected) else 0.
        full=np.ones(n,bool)
        dwell=detectors.dwell(xy,times,full,cfg) if n else {"detected":False}
        revisit=detectors.revisit(xy,v,times,tl,full,np.asarray(target.center),cfg) if n else {"detected":False}
        restricted=np.zeros(n,bool)
        for entity in scene["entities"]:
            if entity["type"]=="hard_constraint_obstacle":
                restricted|=geometry_facts(entity["geometry"],xy)["inside"]
        cov=detectors.coverage(xy,np.linalg.norm(v,axis=1),tl,restricted,survey,cfg)
        if len(cov["covered_mask"])!=len(union):
            raise ValueError("members must use exactly the shared survey grid")
        union|=cov["covered_mask"]
        effective=np.flatnonzero(cov["effective_mask"])
        other=[j for j in range(len(facilities)) if j!=ti]
        max_other=int(levels[:,other].max()) if n and other else 0
        cond={"started_outside_target_warning":bool(n and tl[0]==0),
              "single_warning_visit":bool(n and len(starts)==1),
              "max_target_layer_one":bool(n and int(tl.max())==1),
              "other_layers_within_limit":bool(max_other<=1),
              "no_dwell_window":not bool(dwell["detected"]),
              "azimuth_span_ok":bool(len(selected) and span<=110.),
              "no_revisit_window":not bool(revisit["detected"]),
              "ended_outside_all_warning":bool(n and np.all(levels[-1]==0)),
              "effective_observation":bool(len(effective))}
        member_conditions[mid]=cond
        member_facts[mid]={"frames":int(n),"visits":int(len(starts)),"max_target_layer":int(tl.max()) if n else None,
            "max_other_layer":max_other,"azimuth_span_deg":float(span),"effective_frame_count":int(len(effective)),
            "first_effective_frame_index":int(effective[0]) if len(effective) else None,
            "first_effective_us":int(times[effective[0]]) if len(effective) else None,
            "first_warning_entry_us":int(times[starts[0]]) if len(starts) else None,
            "first_warning_exit_us":int(times[later[0]]) if len(later) else None}
    fraction=float(np.count_nonzero(union)/len(union)) if len(union) else 0.
    required=float(cfg["detectors"]["coverage"]["min_group_fraction"])
    group_conditions={"shared_coverage":bool(len(union) and fraction>=required)}
    return {"passed":bool(member_conditions and all(all(c.values()) for c in member_conditions.values()) and all(group_conditions.values())),
            "member_conditions":member_conditions,"member_facts":member_facts,"group_conditions":group_conditions,
            "group_facts":{"grid_point_count":int(len(union)),"covered_grid_point_count":int(np.count_nonzero(union)),
                           "coverage_fraction":fraction,"required_fraction":required}}


def _ticks(release_s,end_s,hold_s):
    start=int(round(release_s*10))*100000
    stop=int(math.floor((end_s+hold_s)*10+1e-9))*100000
    return np.arange(start,stop+1,100000,dtype=np.int64)


def skeleton_screen(ctx,plan,settings=None):
    from .area_search_reference import references_area_search
    from .optimize import load_settings,physical_limits
    from .skeleton import NominalPVA
    _,_,maps=references_area_search(plan)
    hold=physical_limits(load_settings() if settings is None else settings)["hold_s"]
    samples={}
    for mid,item in sorted(maps.items()):
        nom=item["nominal"]
        times=_ticks(nom.release_s,nom.release_s+nom.travel_s,hold)
        xy,vv,_=NominalPVA(nom)(times/1e6)
        p=np.c_[xy,np.full(len(times),nom.altitude_m)]
        v=np.c_[vv,np.zeros(len(times))]
        samples[mid]={"time_us":times,"p":p,"v":v}
    return screen_area_search(ctx.scene,ctx.facilities,plan.witnesses["target_id"],samples,plan.witnesses["survey"])


def check_area_search(ctx,skeleton,trajectories,settings):
    from ..config import load_config
    from ..scene.exact import signed_distance
    from .connect import crossing_analysis
    from .layer_limits import constraints_for_task
    from ..contract.single_intent import AreaSearchTaskSpec
    from .optimize import physical_limits
    from .optimize_checks import _grid_times
    target=skeleton.witnesses["target_id"]
    survey=skeleton.witnesses["survey"]
    cons=constraints_for_task(ctx,AreaSearchTaskSpec("task0","area_search",target,survey=survey))
    hold=physical_limits(settings)["hold_s"]
    clearance=load_config("monitoring").values["retreat_clearance_m"]
    failures=[];boundaries={};samples={}
    for mid,tr in sorted(trajectories.items()):
        xy=tr.evaluate(_grid_times(tr)+tr.release_s,0)
        violations,crossings=crossing_analysis(xy,cons["crossing_boundaries"],target,
            band_m=ctx.params["pre_entry_warning_clearance_m"],align_m=ctx.params["alignment_length_m"])
        boundaries[mid]={"violations":violations,"crossings":[(c.facility_id,c.direction,float(c.s_m)) for c in crossings]}
        if violations:
            failures.append({"kind":"boundary_crossing","member":mid,"first":violations[0],"count":len(violations)})
        directions=[c.direction for c in crossings if c.facility_id==target]
        if directions!=["in","out"]:
            failures.append({"kind":"target_single_crossing","member":mid,"directions":directions})
        for fid,geometry in cons["warnings"].items():
            distance=float(signed_distance(geometry,tr.evaluate(tr.end_s,0)))
            if distance<clearance:
                failures.append({"kind":"terminal_clearance","member":mid,"facility":fid,"signed_m":distance})
        times=_ticks(tr.release_s,tr.end_s,hold)
        samples[mid]={"time_us":times,"p":np.c_[tr.evaluate(times/1e6,0),np.full(len(times),tr.altitude_m)],
                      "v":np.c_[tr.evaluate(times/1e6,1),np.zeros(len(times))]}
    screen=screen_area_search(ctx.scene,ctx.facilities,target,samples,survey)
    for mid,conditions in screen["member_conditions"].items():
        bad=[k for k in CONDITIONS if not conditions[k]]
        if bad:
            failures.append({"kind":"area_search_nominal","member":mid,"conditions":bad})
    if not screen["group_conditions"]["shared_coverage"]:
        failures.append({"kind":"area_search_nominal","member":"group","conditions":["shared_coverage"]})
    return {"passed":not failures,"failures":failures,"boundaries":boundaries,
            "nominal_members":{m:{"conditions":screen["member_conditions"][m],"counts":screen["member_facts"][m]} for m in sorted(samples)},
            "nominal_group":{"conditions":screen["group_conditions"],"facts":screen["group_facts"]},
            "optimized_nominal_screen":screen}


def measured_area_search(ctx,tracks,release_us,target_id,survey):
    """Full visible measured window; 110-degree nominal gate is not a measured rule."""
    from task_v07 import detectors
    from task_v07.criteria import load_criteria
    from .nominal_checks import layer_levels
    samples={}
    for mid,tr in sorted(tracks.items()):
        mask=(np.asarray(tr.tau_us)>=release_us[mid])&(np.asarray(tr.segment_index)==0)
        samples[mid]={"time_us":np.asarray(tr.tau_us)[mask],"p":np.asarray(tr.p)[mask],"v":np.asarray(tr.v)[mask]}
    screen=screen_area_search(ctx.scene,ctx.facilities,target_id,samples,survey)
    target=ctx.facility_by_id[target_id];members={}
    cfg=load_criteria();size=round(cfg["detectors"]["dwell"]["window_s"]*10)+1
    for mid,sample in sorted(samples.items()):
        times=sample["time_us"];xy=sample["p"][:,:2];n=len(times)
        levels=layer_levels(target,xy)[0]
        inside=levels>=1;previous=np.r_[False,inside[:-1]] if n else np.zeros(0,bool)
        starts=np.flatnonzero(inside&~previous);exits=np.flatnonzero(~inside&previous)
        facts=screen["member_facts"][mid];conditions=screen["member_conditions"][mid]
        closest=None
        for offset in range(0,max(0,n-size+1),512):
            starts_block=np.arange(offset,min(offset+512,n-size+1))
            windows=xy[starts_block[:,None]+np.arange(size)]
            aa=np.linalg.norm(windows-windows.mean(axis=1,keepdims=True),axis=2).max(axis=1)-cfg["detectors"]["dwell"]["radius_m"]
            bb=np.linalg.norm(windows[:,-1]-windows[:,0],axis=1)-cfg["detectors"]["dwell"]["max_start_end_m"]
            values=np.maximum(aa,bb);j=int(np.argmin(values));value=float(values[j])
            if closest is None or value<closest[0]:
                closest=(value,int(starts_block[j]),float(aa[j]),float(bb[j]))
        members[mid]={"warning_entry_count":int(len(starts)),"warning_exit_count":int(len(exits)),
            **{k:facts[k] for k in ("first_warning_entry_us","first_warning_exit_us","first_effective_frame_index","first_effective_us","effective_frame_count","azimuth_span_deg","max_target_layer")},
            "end_target_layer":int(levels[-1]) if n else None,
            "ended_outside_all_warning":conditions["ended_outside_all_warning"],
            "dwell_margin_m":None if closest is None else closest[0],
            "dwell_window_start_us":None if closest is None else int(times[closest[1]]),
            "dwell_window_confirm_us":None if closest is None else int(times[closest[1]+size-1]),
            "dwell_A_m":None if closest is None else closest[2],"dwell_B_m":None if closest is None else closest[3]}
    # Actual acceptance also has the independent frozen verify_segments/validity gates.
    measured_conditions={m:{k:v for k,v in values.items() if k!="azimuth_span_ok"} for m,values in screen["member_conditions"].items()}
    return {"passed":bool(members and set(members)==set(tracks)==set(release_us) and
                          all(all(c.values()) for c in measured_conditions.values()) and screen["group_conditions"]["shared_coverage"]),
            "members":members,"screen":screen,"coverage":screen["group_facts"]}
