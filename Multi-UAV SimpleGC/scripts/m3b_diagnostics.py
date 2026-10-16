"""Read-only diagnostics; phase localization is geometric, never tracker state."""
from collections import defaultdict
from pathlib import Path
import math
import numpy as np
from scene_v07.geometry import center_of
from task_v07.geometry import geometry_facts,offset_geometry
from task_v07.unified.checks import warning_visits
from task_v07.unified.timing import episode_plan
from task_v07.execution import completion_budget
from task_v07.io import read_json
from scripts.summarize_v07_m3 import distribution


def groups(sk): return sk.get("group_skeletons",{sk.get("group_id"):sk})


def projection(points,point):
    points=np.asarray(points,float)[:,:2]; point=np.asarray(point)[:2]
    legs=np.diff(points,axis=0); lengths=np.linalg.norm(legs,axis=1)
    f=np.clip(np.sum((point-points[:-1])*legs,axis=1)/(lengths*lengths),0,1)
    distance=np.linalg.norm(points[:-1]+f[:,None]*legs-point,axis=1)
    i=int(distance.argmin())
    return float(lengths[:i].sum()+f[i]*lengths[i]),float(distance[i]),i


def stage_at(ref,point):
    points=np.asarray(ref["points_enu_m"]); work=ref.get("work_points_enu_m",[])
    if not work: return {"phase":"unknown","reason":"work anchors absent"}
    start=np.flatnonzero(np.linalg.norm(points-np.asarray(work[0]),axis=1)<1e-6)
    end=np.flatnonzero(np.linalg.norm(points-np.asarray(work[-1]),axis=1)<1e-6)
    # Collinear join removal may remove an anchor: use its exact line projection.
    lengths=np.linalg.norm(np.diff(points[:,:2],axis=0),axis=1); cumulative=np.r_[0.,np.cumsum(lengths)]
    begin=float(cumulative[start[0]]) if len(start) else projection(points,work[0])[0]
    finish=float(cumulative[end[-1]]) if len(end) else projection(points,work[-1])[0]
    collect=projection(points,ref.get("collection_point_enu_m",points[0]))[0]
    legs=np.diff(points[:,:2],axis=0); p=np.asarray(point)[:2]
    fractions=np.clip(np.sum((p-points[:-1,:2])*legs,axis=1)/(lengths*lengths),0,1)
    distances=np.linalg.norm(points[:-1,:2]+fractions[:,None]*legs-p,axis=1)
    candidates=np.flatnonzero(distances<=distances.min()+1e-6)
    phases=[]
    for i in candidates:
        progress=cumulative[i]+fractions[i]*lengths[i]
        phases.append("collection" if progress<collect else "approach" if progress<begin else "work" if progress<=finish else "retreat")
    possible=sorted(set(phases))
    return {"phase":possible[0] if len(possible)==1 else "ambiguous","possible_phases":possible,
        "nearest_planned_segments":candidates.tolist(),"distance_to_plan_m":float(distances.min()),
        "method":"nearest exact planned segment, source work/collection anchors; ties retained; not tracker state"}


def approach_rows(scene,sk):
    result=[]
    for gid,group in groups(sk).items():
        target=next(e for e in scene["entities"] if e["id"]==group["target_id"])
        warning=next(e["geometry"] for e in scene["entities"] if e.get("facility_id")==target["id"] and e.get("layer")=="warning")
        center=np.asarray(center_of(target["geometry"]))
        for agent,ref in group["references"].items():
            points=np.asarray(ref["points_enu_m"])[:,:2]; _,entry=warning_visits(points,warning)
            if entry is None: continue
            length=float(np.linalg.norm(np.diff(points[:entry["segment"]+1],axis=0),axis=1).sum()+entry["distance_on_segment_m"])
            direct=float(np.linalg.norm(np.asarray(entry["point"])-points[0])); toward=center-points[0]
            heading=np.asarray(entry["direction"])
            angle=math.degrees(math.acos(float(np.clip(heading@toward/np.linalg.norm(toward),-1,1))))
            result.append({"group_id":gid,"agent_id":agent,"execution_method":group["execution_method"],
                "approach_length_m":length,"start_to_warning_entry_straight_m":direct,"detour_ratio":length/direct if direct else None,
                "ingress_relative_to_start_bearing_deg":angle,"first_warning_entry":entry,
                "monitoring":group.get("geometry_provenance",{}).get("shape") if group["execution_method"]=="monitoring" else None})
    return result


def proposed_directions(pool):
    by_group=defaultdict(lambda:{"proposed":[],"accepted":[],"accepted_original_proposal":[],"whole_route_rejections":defaultdict(int)})
    for record in pool.get("candidates",[]):
        gid=record["group_id"]; item=by_group[gid]
        shape=record.get("draws_by_group",{}).get(gid,{}).get("shape")
        rejected=shape.get("rejected_shape_attempts",[]) if shape else (record.get("rejection") or {}).get("geometric_evidence",[])
        for r in rejected:
            if "direction_deg" in r.get("draw",{}): item["proposed"].append(r["draw"]["direction_deg"])
        if shape:
            item["proposed"].append(shape["direction_deg"])
            if record.get("whole_route_checks",{}).get("status")=="PASS":
                item["accepted"].append(shape.get("accepted_start_direction_deg",shape["direction_deg"]))
                item["accepted_original_proposal"].append(shape["direction_deg"])
        if record.get("reason"): item["whole_route_rejections"][record["reason"]]+=1
    return dict(by_group)


def locate_pair(sk,positions,ids,closest):
    if closest is None: return None
    refs={a:r for g in groups(sk).values() for a,r in g["references"].items()}
    frame=closest["frame_index"]
    return {**closest,"members":{a:{"position_enu_m":positions[frame,ids.index(a)].tolist(),
        **stage_at(refs[a],positions[frame,ids.index(a)])} for a in closest["agents"]}}


def round_evidence(scene,directory):
    sk=read_json(directory/"skeleton.json"); rehearsal=read_json(directory/"rehearsal.json")
    solos={}
    for a in sk["members"]:
        with np.load(directory/f"single_agent_{a}.npz",allow_pickle=False) as saved:
            solos[a]={k:saved[k].copy() for k in ("time_us","p","v")}
    rows=[]; refs={a:r for g in groups(sk).values() for a,r in g["references"].items()}
    for gid,g in groups(sk).items():
        target=next(e for e in scene["entities"] if e["id"]==g["target_id"])
        warning=next(e["geometry"] for e in scene["entities"] if e.get("facility_id")==target["id"] and e.get("layer")=="warning")
        budget=completion_budget(g,{a:0. for a in g["members"]})
        for a in g["members"]:
            run=solos[a]; ref=refs[a]; value=rehearsal["agents"][a]
            row={"agent_id":a,"group_id":gid,"execution_status":value["execution_status"],"solo_duration_s":value["last_sample_s"],
                "budget":budget,"last_warning_signed_distance_m":float(geometry_facts(warning,run["p"][-1,0,:2])["signed_distance_m"]),
                "result":value["result"],"source":{"status_duration":"rehearsal.json","budget":"skeleton.json via frozen completion_budget (conservative)",
                "boundary_distance":"single_agent NPZ last frame + original scene via geometry_facts"}}
            if g["execution_method"]=="monitoring":
                _,entry=warning_visits(np.asarray(ref["points_enu_m"])[:,:2],warning)
                entry_s=None if entry is None else projection(ref["points_enu_m"],entry["point"])[0]
                work_s=projection(ref["points_enu_m"],ref["work_points_enu_m"][0])[0]
                core=value["core_event"]["t_s"]
                # First local closest approach to the actual work-start anchor after warning entry.
                distance=np.linalg.norm(run["p"][:,0]-ref["work_points_enu_m"][0],axis=1)
                begin=0 if core is None else int(np.searchsorted(run["time_us"],round(core*1e6)))
                local=np.flatnonzero((distance[1:-1]<=distance[:-2]) & (distance[1:-1]<distance[2:]))+1
                local=local[local>=begin]
                arrival=int(local[0]) if len(local) else None
                row["warning_to_patrol"]={"planned_distance_m":None if entry_s is None else work_s-entry_s,
                    "warning_entry_s":core,"first_anchor_pass_s":None if arrival is None else float(run["time_us"][arrival]/1e6),
                    "elapsed_s":None if arrival is None or core is None else float(run["time_us"][arrival]/1e6-core),
                    "anchor_miss_distance_m":None if arrival is None else float(distance[arrival]),
                    "method":"first local distance minimum to planned work-start after measured warning event; geometric passage estimate, not tracker state"}
            rows.append(row)
    conflicts=[]; timing_path=directory/"timing_selection.json"
    if timing_path.exists():
        timing=read_json(timing_path)
        for mode,version in timing["versions"].items():
            for attempt in version["attempts"]:
                pair=attempt["closest_pair"]; plan=episode_plan(sk,rehearsal["core_times_s"],mode,attempt["draw"])
                members={}
                for a in pair["agents"]:
                    run=solos[a]; local=(pair["t_s"]-plan["departure_delays_s"][a])*1e6
                    point=np.array([np.interp(local,run["time_us"],run["p"][:,0,i]) for i in range(3)])
                    members[a]={"position_enu_m":point.tolist(),"solo_time_s":local/1e6,**stage_at(refs[a],point)}
                conflicts.append({"mode":mode,"draw":attempt["draw"],"status":attempt["status"],"minimum_m":attempt["minimum_m"],
                    "pair":pair,"members":members,"source":"frozen full-clock M2 overlay (prediction, not joint collision)"})
    rejection=read_json(directory/"planning_rejection.json") if (directory/"planning_rejection.json").exists() else {}
    return {"round":directory.name,"category":rejection.get("category"),"failures":rehearsal["failures"],"members":rows,
            "overlay_attempts":conflicts,"monitoring_shape":[g.get("geometry_provenance",{}).get("shape") for g in groups(sk).values() if g["execution_method"]=="monitoring"],
            "closest_score":[len(rehearsal["failures"]),-max((r["minimum_m"] for r in conflicts),default=0.)]}
