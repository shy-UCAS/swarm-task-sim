"""V8-20 single-attempt independent radial-strip skeleton. No downstream resampling."""
import math
import re
import sys
import time
from dataclasses import replace

import numpy as np

from ...config import load_config
from ...contract.monitoring import Failure,MemberPlan,SegmentPlan
from ...sampler.keys import RngKey
from ...scene.exact import signed_distance
from ...sim.guidance import make_curve,nominal_time,speed_profile
from ...sim.kernel import member_config
from .. import transit_chords as TC
from ..area_search_geometry import (feasible_sector_cells,filter_entry_cells,make_survey,
    radial_record,audit_complete_curve)
from ..area_search_numeric import assign_blocks,draw_hierarchy,scan_vertices
from ..connect import crossing_analysis,fillet_route
from ..formation import formation_slots,mapped_start,retreat_chain
from ..nominal import member_nominal,release_us
from ..path import sample_primitives
from ..shared_routes import plan_starts,route_to_slot
from ..skeleton import reference_guidance,width_then_build
from ..speed import draw_speed_events,map_speed_events
from . import transit as T
from .monitoring import _key_dict,_release_delays_ref

INTENT="area_search"
_LAST_TIMING={}


def last_attempt_timing():
    import copy
    return copy.deepcopy(_LAST_TIMING)


def draw_summary(proposal,formation):
    p=proposal or {}
    keys=("theta_idx","theta_deg","h_m","cell_index","cells_feasible","filtered_cells","collect_D_m","mu_deg","span_deg","c","K","beta_deg","Q")
    return {"intent":INTENT,"formation":formation,**{k:p[k] for k in keys if k in p}}


def final_failure(ctx,group,task,attempt_records):
    stages=[r.get("stage") for r in attempt_records]
    empty=bool(stages) and all(s=="area_search_entry" for s in stages)
    return Failure("approx_empty" if empty else "budget_exhausted",
        "area_search_entry_empty" if empty else "area_search_attempt_budget",
        "area_search_entry" if empty else "random_construction",{"attempts":len(stages),"stages":stages},None)


def _failure(stage,key,proposal=None,witnesses=None,members=None,detail=None):
    return SegmentPlan(members=members or {},reference_xy=(),nominal_duration_s=None,anchors={},repairs=(),
        failure=Failure("candidate_rejected",stage,stage,{"stage":stage,**(detail or {})},None),proposal=proposal,
        formation=None,topology={"final":INTENT},business_key=_key_dict(key),witnesses=witnesses)


def _route_with_vertices(S,p0,slot,u,rng,target_id,captured):
    """Observe the frozen fillet call's exact arguments; construct the route only once.

    The per-thread profile is restored even on error. No function or RNG is replaced.
    This retains original unsampled start-route vertices, which route_to_slot does
    not include in its return metadata.
    """
    import v08.motion.shared_routes as shared
    pending={};records=[];previous=sys.getprofile()
    code=shared.fillet_route.__code__
    def observe(frame,event,arg):
        if previous is not None:
            previous(frame,event,arg)
        if frame.f_code is code:
            if event=="call":
                pending[id(frame)]=(np.asarray(frame.f_locals["points"],float).tolist(),list(frame.f_locals["radii"]))
            elif event=="return":
                data=pending.pop(id(frame),None)
                if data is not None and arg is not None:
                    records.append((arg,data))
    sys.setprofile(observe)
    try:
        prims,delta=route_to_slot(S,p0,slot,u,rng,
            planner_factory=lambda ctx,d:TC.entry_planner(ctx,target_id,d))
    finally:
        sys.setprofile(previous)
    if prims is not None:
        data=next(data for result,data in reversed(records) if result is prims)
        captured.append({"vertices":data[0],"radii":data[1],"slot":np.asarray(slot).tolist(),"primitives":prims})
    return prims,delta


def _normalise(points,radii,labels):
    points=[np.asarray(p,float) for p in points]
    full=[None,*radii,None]
    keep=list(range(len(points)))
    changed=True
    while changed:
        changed=False
        for j in range(1,len(keep)-1):
            a,b,c=(points[keep[k]] for k in (j-1,j,j+1))
            x,y=b-a,c-b
            if np.linalg.norm(x)==0. or np.linalg.norm(y)==0.:
                keep.pop(j);changed=True;break
            angle=math.atan2(abs(float(x[0]*y[1]-x[1]*y[0])),float(x@y))
            if angle<1e-9:  # Same no-turn condition used by frozen fillet_route.
                keep.pop(j);changed=True;break
    pts=[points[k] for k in keep];rs=[full[k] for k in keep[1:-1]];tags=[labels[k] for k in keep]
    if any(r is None for r in rs):
        raise RuntimeError("noncollinear area_search vertex has no explicit radius")
    return pts,rs,tags


def _head(C,split,inner,outer,indices,exit_xy):
    scan=scan_vertices(inner,outer,indices)
    radii=[None]*len(scan)
    tags=[]
    for j in range(len(scan)):
        tags.append("first_outer" if j==0 else f"scan{j}")
    for j in range(1,len(scan)-1,2):
        radius=.5*(float(np.linalg.norm(scan[j+1]-scan[j]))-6.5)/1.10
        if radius<15.:
            raise ValueError("U radius below frozen minimum")
        radii[j]=radii[j+1]=radius
    last_error=None
    for kind,first_radius,omit in (("30_30",30.,False),("30_15",15.,False),("omit_first_outer",None,True)):
        points=[C,split,*scan[1 if omit else 0:],exit_xy]
        labels=["collect","split_vertex",*tags[1 if omit else 0:],"terminal"]
        rr=[30.,*(radii[1:] if omit else [first_radius,*radii[1:]])]
        # Last outer is explicitly redundant along the radial exit, not a sharp corner.
        points.pop(-2);labels.pop(-2);rr.pop(-1)
        pts,rs,normal_labels=_normalise(points,rr,labels)
        try:
            prims=list(fillet_route(pts,rs))
        except ValueError as error:
            last_error=error
            match=re.match(r"第 (\d+) 条边放不下圆角",str(error))
            if match is None:
                raise
            edge=int(match[1])
            if kind=="30_30" and edge<=2:
                continue
            if kind=="30_15" and normal_labels[edge:edge+2]==["split_vertex","first_outer"]:
                continue
            raise
        # Retain the physical final outer anchor as a line endpoint, without a corner.
        last=prims[-1]
        if last[0]!="line":
            raise ValueError("radial terminal line missing")
        a,b=np.asarray(last[1]),np.asarray(last[2]);q=scan[-1]
        if not np.array_equal(q,a) and not np.array_equal(q,b):
            if not 0.<float((q-a)@(b-a))<float((b-a)@(b-a)):
                raise ValueError("final outer anchor outside radial terminal line")
            prims[-1:]=[("line",last[1],tuple(q)),("line",tuple(q),last[2])]
        arc_tags=iter(normal_labels[1:-1]);mapping={}
        for i,p in enumerate(prims):
            if p[0]=="arc":
                mapping[next(arc_tags)]=i
        return {"primitives":tuple(prims),"vertices":pts,"radii":rs,"mapping":mapping,"kind":kind,"omitted":omit,
                "last_outer":scan[-1],"indices":list(indices)}
    raise last_error


def _slot_deviation(plan,maps):
    from ..skeleton import NominalPVA
    mids=sorted(plan.members)
    if len(mids)<2:
        return None
    times={m:{k:float(np.interp(v,maps[m]["nominal"].curve.s,maps[m]["nominal"].t_nodes))+maps[m]["nominal"].release_s
              for k,v in maps[m]["phase_s"].items()} for m in mids}
    low=max(t["collect_s"] for t in times.values());high=min(t["split_s"] for t in times.values())
    if high<low:
        return None
    t=np.unique(np.r_[low,np.arange(math.ceil(low*10),math.floor(high*10)+1)/10,high])
    pos={m:NominalPVA(maps[m]["nominal"])(t)[0] for m in mids}
    u,n=np.asarray(plan.proposal["u"]),np.asarray(plan.proposal["n"])
    offsets=plan.formation["offsets"]
    worst=0.
    for i,m in enumerate(mids):
        for other in mids[:i]:
            wanted=(offsets[m][0]-offsets[other][0])*u+(offsets[m][1]-offsets[other][1])*n
            worst=max(worst,float(np.linalg.norm(pos[m]-pos[other]-wanted,axis=1).max()))
    return worst


def propose_and_build(ctx,group,task,states,key):
    if task.intent!=INTENT:
        raise ValueError("area_search builder requires its explicit intent")
    _LAST_TIMING.clear();all_start=time.perf_counter()
    try:
        S=T.TransitSetup(ctx,group,task,states,key)
        rng,crng=S.rng("shape"),S.rng("connect")
        chain=retreat_chain(mapped_start(group.formation_prior));b=float(ctx.family.lateral_spacing_m)
        fkey=RngKey(key.family_id,key.draw,"formation",mission=key.mission,branch=key.branch,group=key.group,segment=key.segment,attempt=key.attempt)
        order=formation_slots(group,ctx.family,fkey,formation=chain[0]).order
        steps=[]
        def probe(name,step):
            slots=formation_slots(group,ctx.family,fkey,formation=name,lateral_step_m=step,order=order)
            doc=TC.load_chord_set(ctx,task.target_id,slots,ctx.cache_dir,intent=INTENT)
            steps.append({"formation":name,"lateral_step_m":step,"feasible_cells":len(doc["cells"]),"n_cells":doc["n_cells"],"query_id":doc.get("query_id"),"reasons":doc.get("reasons")})
            return {"slots":slots,"doc":doc} if doc["cells"] else None
        payload=width_then_build(chain,lambda name:T._echelon_payload(probe,group,b,steps) if name=="echelon" else probe(name,None),lambda name,p:p)
        if payload is None:
            return _failure("area_search_entry",key,detail={"formations":steps})
        slots,doc=payload["slots"],payload["doc"]
        H=float(ctx.family.task_altitude_m);rho=.4*H
        ao=float(S.tgt.offsets["warning"])-12.5-rho
        start=time.perf_counter();sectors=feasible_sector_cells(ctx,task.target_id,len(group.member_ids),H)
        _LAST_TIMING["sector_set_s"]=time.perf_counter()-start
        entries=filter_entry_cells(ctx,task.target_id,doc["cells"],sectors,ao,offsets=slots.offsets)
        _LAST_TIMING.update(entry_cells_before=len(doc["cells"]),entry_cells_after=len(entries),sector_cells=len(sectors))
        if not entries:
            return _failure("area_search_entry",key,detail={"formations":steps})
        chord,sector,c=draw_hierarchy(entries,rng)
        ti,h,xt,xin,Ds=chord["cell"]
        D=float(Ds[int(rng.integers(len(Ds)))]);xc=float(xin)-D
        u,n=TC.frame(TC.thetas()[int(ti)]);origin=np.asarray(S.tgt.center,float)
        P={"intent":INTENT,"theta_idx":int(ti),"theta_deg":float(ti*TC.THETA_STEP_DEG),"h_m":float(h),"origin_xy":origin.tolist(),"u":u.tolist(),"n":n.tolist(),
           "x_c":xc,"collect_D_m":D,"chord_query_id":doc.get("query_id"),"cell_index":int(chord["cell_index"]),"cells_feasible":len(doc["cells"]),"filtered_cells":len(entries),
           "mu_deg":sector["mu_deg"],"span_deg":sector["span_deg"],"c":int(c),"K":int(len(group.member_ids)*c),"beta_deg":chord["beta_deg"],"Q":chord["Q"].tolist(),
           "inner_offset_m":sector["choices"][c]["inner_offset_m"],"outer_offset_m":ao,"sector_count":len(sectors),"c_count":len(sector["choices"]),"formation_steps":steps,"member_slot_order":list(slots.order)}
        survey=make_survey(S.tgt.geometry,S.tgt.center,ao,P["mu_deg"],P["span_deg"],len(group.member_ids),c,sector["choices"][c],H)
        witnesses={"intent":INTENT,"target_id":task.target_id,"survey":survey,"independent_members":{},"turn_ranges":{},"bone_nominal_screen":None,"nominal_duration_s":None,"formation_steps":steps,
            "area_geometry":{"sector_cells":len(sectors),"entry_cells_before":len(doc["cells"]),"entry_cells_after":len(entries),"rejected_by_condition":{},"inner_gaps_m":sector["choices"][c]["inner_gaps_m"],"outer_gaps_m":sector["choices"][c]["outer_gaps_m"],"strip_lengths_m":sector["choices"][c]["strip_lengths_m"],"base_min_margin_m":None}}
        C=origin+xc*u+float(h)*n;captured=[]
        starts,meta=plan_starts(S,slots,C,u,crng,route_fn=lambda s,p,slot,d,r:_route_with_vertices(s,p,slot,d,r,task.target_id,captured))
        if starts is None:
            return _failure("start_route",key,P,witnesses,detail={"member":meta})
        captured={mid:data for mid,data in zip(slots.order,captured)}
        choice=sector["choices"][c];inner,outer=np.asarray(choice["inner_xy"]),np.asarray(choice["outer_xy"])
        blocks=assign_blocks(slots.offsets,slots.order,outer[np.arange(len(group.member_ids))*c],u,slots.realized)
        curves,heads,collect_indices,samples={},{},{},{}
        for mid in slots.order:
            indices=list(range(blocks[mid]*c,(blocks[mid]+1)*c));last=indices[-1]
            record=radial_record(ctx,task.target_id,choice["angles_rad"][last],ao,rho,outer_xy=outer[last])
            if not record["corridor_ok"]:
                return _failure("area_search_route",key,P,witnesses,detail={"member":mid,"constraint":"radial_exit"})
            try:
                head=_head(captured[mid]["slot"],chord["splits"][mid],inner,outer,indices,record["exit_xy"])
                prims=tuple(starts[mid])+head["primitives"]
                sample=sample_primitives(prims,ctx.params["curve_spacing_m"])
            except ValueError as error:
                _LAST_TIMING["route_error_type"]=type(error).__name__
                return _failure("area_search_route",key,P,witnesses,detail={"member":mid,"constraint":"fillet_placement"})
            cs=np.r_[0.,np.cumsum(np.hypot(*np.diff(sample.xy,axis=0).T))]
            first_arc=next(i for i,p in enumerate(head["primitives"]) if p[0]=="arc")
            split_index=sample.intervals[len(starts[mid])+first_arc][0]
            collect_index=sample.intervals[len(starts[mid])-1][1]
            final_index=sample.intervals[-1][0]
            _LAST_TIMING.setdefault("split_depths_m",{})[mid]=float(S.tgt.offsets["warning"]-signed_distance(S.tgt.geometry,sample.xy[split_index]))
            mapping={label:(sample.intervals[len(starts[mid])+i]) for label,i in head["mapping"].items()}
            turns=[]
            for j in range(1,2*c-1,2):
                a,bidx=mapping[f"scan{j}"][0],mapping[f"scan{j+1}"][1]
                turns.append((f"u{(j-1)//2}",float(cs[a]),float(cs[bidx]),"turn_u_min_m"))
            raw=captured[mid]
            witnesses["independent_members"][mid]={"vertices_xy":[*raw["vertices"],*[np.asarray(p).tolist() for p in head["vertices"][1:]]],
                "radii_m":[*raw["radii"],None,*head["radii"]],"primitives":prims,"curve_s":cs.tolist(),
                "collect_s":float(cs[collect_index]),"split_s":float(cs[split_index]),
                "scan_start_s":float(cs[mapping["first_outer"][1]]) if "first_outer" in mapping else float(cs[split_index]),
                "scan_end_s":float(cs[final_index]),"warning_entry_s":None,"warning_exit_s":None,"terminal_s":float(cs[-1]),
                "block_index":int(blocks[mid]),"strip_indices":indices,"first_outer_omitted":head["omitted"],"slot_xy":chord["splits"][mid].tolist(),"head_kind":head["kind"]}
            witnesses["turn_ranges"][mid]=turns
            curves[mid]=sample.xy;heads[mid]=prims;collect_indices[mid]=collect_index;samples[mid]=sample
        # Geometric checks only. No separation or nominal coverage rejection here.
        for mid in slots.order:
            audit=audit_complete_curve(S.base,curves[mid],heads[mid])
            if not audit["passed"]:
                return _failure("area_search_route",key,P,witnesses,detail={"member":mid,"constraint":audit["constraint"],"margin_m":audit["margin_m"],"chord_index":audit["chord_index"]})
            value=min(audit["minima"].values())
            old=witnesses["area_geometry"]["base_min_margin_m"]
            witnesses["area_geometry"]["base_min_margin_m"]=value if old is None else min(old,value)
            violations,crossings=crossing_analysis(curves[mid],S.warn,task.target_id,band_m=S.band,align_m=S.align)
            target=[x for x in crossings if x.facility_id==task.target_id]
            if violations or [x.direction for x in target]!=["in","out"]:
                return _failure("area_search_route",key,P,witnesses,detail={"member":mid,"constraint":"warning_crossing"})
            w=witnesses["independent_members"][mid]
            w["warning_entry_s"],w["warning_exit_s"]=(float(x.s_m) for x in target)
        guidance=reference_guidance();G=guidance.values;M=load_config("monitoring").values
        tails={m:make_curve(curves[m][collect_indices[m]:],max_chord_m=G["max_chord_m"],max_turn_rad=G["max_turn_per_chord_rad"]) for m in slots.order}
        horizon=max(float(nominal_time(curve,speed_profile(curve,((0.,float(M["speed_min_m_s"])),),a_lat=G["a_lat_m_s2"],a_lon=G["a_lon_m_s2"],v_max=member_config().vehicle_profile.max_speed_xy_m_s,v0=0.,v_end=0.,stops=(curve.length,)),0.,curve.length)) for curve in tails.values())
        event=draw_speed_events(group.speed_profile,RngKey(key.family_id,key.draw,"speed",mission=key.mission,branch=key.branch,group=key.group,segment=key.segment,attempt=key.attempt),horizon_s=horizon)
        P["speed_events"]={"times_s":tuple(event.times_s),"speeds_m_s":tuple(event.speeds_m_s)}
        v0=float(group.speed_profile.initial_speed_m_s);breaks={}
        for mid in slots.order:
            mapped=map_speed_events(tails[mid],event.times_s,event.speeds_m_s,(),guidance,initial_speed_m_s=v0)
            base=witnesses["independent_members"][mid]["collect_s"]
            breaks[mid]=tuple([(0.,v0),*[(base+float(s),float(v)) for s,v in mapped.breaks[1:]]])
        collect={m:witnesses["independent_members"][m]["collect_s"] for m in slots.order}
        delays,_,nom0=_release_delays_ref(curves,collect,breaks,guidance)
        members={m:MemberPlan(m,0,tuple(map(tuple,curves[m])),float(states[m].p[2]),float(nom0[m].curve.length),float(delays[m]),breaks[m],()) for m in slots.order}
        nominals={m:member_nominal(members[m],guidance=guidance) for m in slots.order}
        duration=max(n.release_s+n.travel_s for n in nominals.values())-min(n.release_s for n in nominals.values())
        witnesses["nominal_duration_s"]=float(duration)
        formation={"prior":slots.prior,"start":slots.start,"realized":slots.realized,"mapped_from_loose":slots.mapped_from_loose,"retreat_chain":list(chain),"order":list(slots.order),"offsets":{m:list(v) for m,v in slots.offsets.items()},"lateral_step_m":slots.lateral_step_m}
        plan=SegmentPlan(members,(),float(duration),{},(),proposal=P,formation=formation,topology={"final":INTENT},business_key=_key_dict(key),member_nominal_s={m:float(n.travel_s) for m,n in nominals.items()},witnesses=witnesses)
        from ..area_search_reference import references_area_search
        _,_,maps=references_area_search(plan)
        _LAST_TIMING["slot_deviation_m"]=_slot_deviation(plan,maps)
        return plan
    finally:
        _LAST_TIMING["attempt_s"]=time.perf_counter()-all_start
