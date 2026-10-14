"""Evidence-only semantics on the exported 10 Hz truth grid, with causal prefixes."""
from itertools import combinations
import math

import numpy as np

from scene_v07.geometry import center_of
from .geometry import geometry_facts, GEOMETRY_VERSION
from .planning import angular_span, scene_parts
from .survey import survey_grid

LABEL_VERSION="traj2language.labels/0.7-s2.3"
# Expansion task groups (explicit exclusion policy, new roles) use a new schema.
EXPANSION_LABEL_VERSION="traj2language.labels/0.7-s2x.1"
EVIDENCE_SOURCE="truth.csv:10Hz_half_open_sim_clock"
_LAYER_CODES={"warning":1,"alert":2,"protected":3}


def role_kind(skeleton):
    """Criterion branch of one task group; vertical-slice skeletons map unchanged."""
    role=skeleton.get("role",{"penetration":"intrusion","reconnaissance":"reconnaissance"}.get(skeleton["base_intent"]))
    if role=="intrusion":
        return "intrusion"
    if role=="reconnaissance" and skeleton.get("execution_method")!="close_observation":
        # All historical strip methods (annular/equal-strip lawnmower, area_search).
        return "area_search"
    if role=="transit":
        return "transit"
    raise ValueError(f"No evidence criterion implemented for role {role!r}")


def azimuth_deg(offset):
    return math.degrees(math.atan2(offset[1],offset[0]))%360


def bounded(violated,settled):
    """Absence condition: an observed violation is final, absence needs settled evidence."""
    return False if violated else (True if settled else None)


def validate_grid(t_us,p,v,ids):
    t_us=np.asarray(t_us)
    if t_us.ndim!=1 or not len(t_us) or t_us[0]!=0 or np.any(np.diff(t_us)!=100000):
        raise ValueError("Labels require the complete common 10 Hz export grid from t=0")
    if p.shape!=(len(t_us),len(ids),3) or v.shape!=p.shape or len(set(ids))!=len(ids):
        raise ValueError("ID/grid/state dimensions disagree")
    if not np.isfinite(p).all() or not np.isfinite(v).all():
        raise ValueError("Nonfinite exported state")


def event(mask,t_us,raw_type):
    found=np.flatnonzero(mask)
    return {"raw_event_type":raw_type,"role_core_event":"start_core_operation",
            "t_s":float(t_us[found[0]]/1e6) if len(found) else None,
            "frame_index":int(found[0]) if len(found) else None,
            "status":"known" if len(found) else "unknown","source":EVIDENCE_SOURCE,
            "resolution_s":0.1}


def coordination(events, sync_window_s=10., batch_split_gap_s=20.):
    known={a:e["t_s"] for a,e in events.items() if e["t_s"] is not None}
    result={"scope":"task_group","event_type":"start_core_operation","source":EVIDENCE_SOURCE,
            "sync_window_s":sync_window_s,"batch_split_gap_s":batch_split_gap_s,
            "event_times_s":{a:events[a]["t_s"] for a in sorted(events)},
            "event_range_s":None,"batches":[]}
    if len(events)<2:
        result["classification"]="not_applicable"
    elif len(known)!=len(events):
        result["classification"]="unknown"
    else:
        ordered=sorted(known,key=lambda a:(known[a],a))
        result["event_range_s"]=round(max(known.values())-min(known.values()),6)
        batches=[[ordered[0]]]
        for a in ordered[1:]:
            if known[a]-known[batches[-1][-1]]>batch_split_gap_s:
                batches.append([])
            batches[-1].append(a)
        result["batches"]=[{"batch_index":i,"members":sorted(batch),
                           "start_s":min(known[a] for a in batch),"end_s":max(known[a] for a in batch),
                           "span_s":round(max(known[a] for a in batch)-min(known[a] for a in batch),6)}
                          for i,batch in enumerate(batches)]
        result["classification"]=("synchronous" if result["event_range_s"]<=sync_window_s else
                                  "sequential" if len(batches)>1 and all(b["span_s"]<=sync_window_s for b in result["batches"])
                                  else "other")
    return result


def longest_hold(mask):
    best=run=0
    for ok in mask:
        run=run+1 if ok else 0
        best=max(best,run)
    return max(0,best-1)/10.


def observed_conditions_result(conditions, complete):
    if any(v is False for v in conditions.values()):
        return "failure"
    if all(v is True for v in conditions.values()):
        return "success"
    return "failure" if complete else "unknown"


def measurable(ok,complete):
    return True if ok else (False if complete else None)


def measure(scene,skeleton,run,mode,planned_batches=None,*,cutoff_s=None,timing_plan=None):
    ids=list(run["agent_ids"])
    t=run["time_us"];p=run["p"];v=run["v"]
    complete=cutoff_s is None and run["execution_status"] in ("completed","timeout")
    if cutoff_s is not None:
        take=t<round(cutoff_s*1e6)
        t,p,v=t[take],p[take],v[take]
    validate_grid(t,p,v,ids)
    by_id={a:i for i,a in enumerate(ids)}
    facilities=sorted([e for e in scene["entities"] if e["type"]=="facility"],key=lambda e:e["id"])
    levels=np.zeros((len(t),len(ids),len(facilities)),np.int8)
    all_events={};per_agent={};core={};coverages={};effective_masks={}
    obstacle_inside=np.zeros((len(t),len(ids)),bool)
    for obstacle in (e for e in scene["entities"] if e["type"]=="hard_constraint_obstacle"):
        obstacle_inside|=geometry_facts(obstacle["geometry"],p[:,:,:2])["inside"]
    world_inside=geometry_facts(scene["world"]["geometry"],p[:,:,:2])["inside"]
    minimum=None;closest=None;by_agent_min={a:None for a in ids}
    for a,b in combinations(sorted(ids),2):
        distance=np.linalg.norm(p[:,by_id[a]]-p[:,by_id[b]],axis=1)
        k=int(np.argmin(distance));d=float(distance[k])
        if minimum is None or d<minimum:
            minimum,closest=d,{"agents":[a,b],"t_s":float(t[k]/1e6),"frame_index":k}
        for member in (a,b):
            by_agent_min[member]=d if by_agent_min[member] is None else min(d,by_agent_min[member])
    facility_facts={}
    for fi,f in enumerate(facilities):
        _,zones=scene_parts(scene,f["id"])
        offsets={layer:zones[layer]["offset_m"] for layer in ("protected","alert","warning")}
        facts=geometry_facts(f["geometry"],p[:,:,:2],layer_offsets=offsets)
        facility_facts[f["id"]]=facts
        levels[:,:,fi]=facts["layer"]
    target_fi=next(i for i,f in enumerate(facilities) if f["id"]==skeleton["target_id"])
    center=np.array(center_of(facilities[target_fi]["geometry"]))
    kind=role_kind(skeleton)
    grid=None
    if kind=="area_search":
        grid=survey_grid(skeleton["survey"])
    phases=np.zeros((len(t),len(ids)),np.int8)
    azimuths=[]
    for a in sorted(ids):
        i=by_id[a];ref=skeleton["references"][a];xy=p[:,i,:2];speed=np.linalg.norm(v[:,i],axis=1)
        region_facts={}
        for fi,f in enumerate(facilities):
            region_facts[f["id"]]={}
            for name,level in (("warning",1),("alert",2),("protected",3)):
                ev=event(levels[:,i,fi]>=level,t,f"enter_{name}_zone")
                region_facts[f["id"]][name]={"entered_observed":ev["t_s"] is not None,
                                              "first_entry_s":ev["t_s"],"sample_count":int(np.sum(levels[:,i,fi]>=level))}
        work_end=None
        if kind=="intrusion":
            core[a]=event(levels[:,i,target_fi]==3,t,"enter_protected_zone")
            inside=levels[:,i,target_fi]==3
            depth=float(facility_facts[skeleton["target_id"]]["protected_depth_m"][:,i].max())
            if core[a]["frame_index"] is not None:
                point=xy[core[a]["frame_index"]]-center
                azimuth=math.degrees(math.atan2(point[1],point[0]))%360
                azimuths.append(azimuth)
            else:
                azimuth=None
            behavior=["entered_protected_zone"] if inside.any() else []
            contribution={"maximum_protected_depth_m":depth,"entry_azimuth_deg":azimuth}
            role_conditions={"entered_protected":measurable(inside.any(),complete),
                             "required_depth":measurable(depth>=skeleton["required_intrusion_depth_m"],complete)}
        elif kind=="transit":
            # One continuous visit of the target warning region (closed boundary).
            criteria=skeleton["transit"]
            inside=levels[:,i,target_fi]>=1
            core[a]=event(inside,t,"enter_warning_zone")
            first=core[a]["frame_index"];last=None
            if first is not None:
                outside=np.flatnonzero(~inside[first:])
                last=first+int(outside[0])-1 if len(outside) else None
            visit=np.zeros(len(t),bool)
            if first is not None:
                visit[first:len(t) if last is None else last+1]=True
            moving=speed>=criteria["low_speed_threshold_m_s"]
            low_hold=longest_hold(visit&~moving)
            heading=np.arctan2(v[:,i,1],v[:,i,0])
            step=visit[1:]&visit[:-1]&moving[1:]&moving[:-1]
            turn=np.abs((np.diff(heading)+math.pi)%(2*math.pi)-math.pi)
            cumulative=round(float(np.degrees(turn[step].sum())),6)
            azimuth=exit_azimuth=chord=difference=None
            if first is not None:
                azimuth=round(azimuth_deg(xy[first]-center),6)
                azimuths.append(azimuth)
            if last is not None:
                exit_azimuth=round(azimuth_deg(xy[last]-center),6)
                chord=round(float(np.linalg.norm(xy[last]-xy[first])),6)
                difference=round(abs((exit_azimuth-azimuth+180)%360-180),6)
                work_end=float(t[last+1]/1e6)
            settled=last is not None or complete
            behavior=(["crossed_warning_zone"] if last is not None else
                      ["entered_warning_zone"] if first is not None else [])
            contribution={"warning_entry_s":core[a]["t_s"],"warning_exit_s":work_end,
                          "warning_last_inside_frame":last,"warning_visit_duration_s":None if last is None else round((last-first)/10,6),
                          "chord_length_m":chord,"entry_azimuth_deg":azimuth,"exit_azimuth_deg":exit_azimuth,
                          "entry_exit_azimuth_difference_deg":difference,
                          "longest_low_speed_in_warning_s":low_hold,"cumulative_turn_in_warning_deg":cumulative}
            role_conditions={"entered_warning":measurable(first is not None,complete),
                             "exited_warning":measurable(last is not None,complete),
                             "chord_length":measurable(chord is not None and chord>=criteria["minimum_chord_m"],complete),
                             "entry_exit_azimuth_difference":measurable(difference is not None and difference>=criteria["minimum_azimuth_difference_deg"],complete),
                             "no_stop_in_warning":bounded(low_hold>criteria["maximum_low_speed_s"],settled),
                             "no_loop_in_warning":bounded(cumulative>=criteria["maximum_cumulative_turn_deg"],settled)}
        else:
            strip=ref.get("scan_geometry",{"type":"Polygon","vertices_m":ref.get("scan_vertices_m",[])})
            expected_visits=len(ref["scan_lane_endpoints_m"])
            cursor=0;visits=[]
            for point in ref["scan_lane_endpoints_m"]:
                found=np.flatnonzero(np.linalg.norm(xy[cursor:]-point,axis=1)<=skeleton["survey"]["lane_endpoint_radius_m"])
                if not len(found):
                    break
                cursor+=int(found[0]);visits.append(float(t[cursor]/1e6))
            scan_complete=len(visits)==expected_visits
            effective=geometry_facts(strip,xy)["inside"]&(speed>=skeleton["survey"]["effective_speed_min_m_s"])
            effective&=(levels[:,i,target_fi]==1)&~obstacle_inside[:,i]
            if scan_complete:
                effective &= t/1e6<=visits[-1]
            effective_masks[a]=effective
            core[a]=event(effective,t,"scan_start")
            coverage=np.zeros(len(grid),bool)
            for chunk in np.array_split(xy[effective],max(1,int(effective.sum())//200)):
                if len(chunk):
                    remaining=np.flatnonzero(~coverage)
                    coverage[remaining]|=np.any(np.linalg.norm(grid[remaining,None,:]-chunk[None,:,:],axis=2)<=skeleton["survey"]["footprint_radius_m"],axis=1)
            coverages[a]=coverage
            behavior=(["effective_area_observation"] if effective.any() else [])
            if scan_complete:
                behavior.append("ordered_lawnmower_scan")
            scan_end=visits[-1] if scan_complete else None
            duration=round(scan_end-core[a]["t_s"],6) if scan_end is not None and core[a]["t_s"] is not None else None
            contribution={"covered_group_grid_points":int(coverage.sum()),"group_grid_point_count":len(grid),
                          "ordered_lane_endpoint_times_s":visits,"scan_pattern_observed":scan_complete,
                          "expected_lane_endpoint_count":expected_visits,"planned_strip_count":ref.get("scan_strip_count",expected_visits//2),
                          "scan_end_s":scan_end,"scan_segment_duration_s":duration,
                          "effective_observation_duration_s":round(float(effective.sum())/10,6)}
            no_alert=not np.any(levels[:,i,:]>=2)
            role_conditions={"effective_observation":measurable(effective.any(),complete),
                             "scan_lane_evidence":measurable(scan_complete,complete),
                             "no_alert_entry":bool(no_alert)}
            azimuth=None
            work_end=scan_end
        end_distance=np.linalg.norm(p[:,i]-ref["endpoint_enu_m"],axis=1)
        dwell=(end_distance<=skeleton["terminal_radius_m"])&(speed<=skeleton["terminal_speed_m_s"])
        retreat_event=None
        if kind!="intrusion" and ref.get("retreat_required",False):
            after_work=np.zeros(len(t),bool) if work_end is None else t/1e6>=work_end
            retreat_event=event((end_distance<=skeleton["terminal_radius_m"])&after_work,t,"retreat_point_arrival")
            retreat_event.pop("role_core_event")
            retreat_event["planned_warning_clearance_m"]=ref["retreat_warning_clearance_m"]
            retreat_event["minimum_observed_endpoint_distance_m"]=float(end_distance.min())
            role_conditions["reached_retreat_point"]=measurable(retreat_event["t_s"] is not None,complete)
            dwell &= after_work
        if "exclusion_policy" in skeleton:
            # Explicit private per-ID policy: the named layer and every inner layer are forbidden.
            forbidden=np.zeros(len(t),bool)
            for fid,layer in skeleton["exclusion_policy"][a].items():
                forbidden|=levels[:,i,[f["id"] for f in facilities].index(fid)]>=_LAYER_CODES[layer]
            role_conditions["exclusion_policy_respected"]=bounded(forbidden.any(),complete)
        hold=longest_hold(dwell)
        conditions={**role_conditions,"own_endpoint_hold":measurable(hold>=skeleton["terminal_hold_s"],complete)}
        outcome=observed_conditions_result(conditions,complete)
        phases[:,i]=np.where(speed>.5,1,0)
        if core[a]["frame_index"] is not None:
            phases[core[a]["frame_index"]:,i]=2
        if kind=="area_search" and contribution["scan_pattern_observed"]:
            phases[t/1e6>contribution["ordered_lane_endpoint_times_s"][-1],i]=3
        elif kind=="transit" and work_end is not None:
            phases[t/1e6>=work_end,i]=3
        phases[dwell,i]=4
        per_agent[a]={"assigned":{"intent":skeleton["base_intent"],"role":skeleton["role"],
                                  "target":skeleton["target_id"],"task_group":skeleton["group_id"],
                                  "execution_method":skeleton["execution_method"],"planned_coordination":mode,
                                  "timing":None if timing_plan is None else {key:timing_plan[key][a] for key in ("target_event_times_s","target_event_times_grid_s","jitter_s","departure_delays_s","batch_by_agent")}},
                      "observed":{"behaviors":behavior,"regions_by_facility":region_facts,
                                  "core_event":core[a],"contribution":contribution,"retreat_event":retreat_event,
                                  "endpoint_min_distance_m":float(end_distance.min()),"endpoint_hold_s":hold,
                                  "minimum_separation_m":by_agent_min[a],"batch_index":None,
                                  "hard_obstacle_sample_count":int(obstacle_inside[:,i].sum()),
                                  "outside_world_sample_count":int((~world_inside[:,i]).sum())},
                      "result":{"status":outcome,"conditions":{k:(bool(v) if v is not None else None) for k,v in conditions.items()}}}
    coord=coordination(core,skeleton["sync_window_s"],skeleton["batch_split_gap_s"])
    for batch in coord["batches"]:
        for a in batch["members"]:
            per_agent[a]["observed"]["batch_index"]=batch["batch_index"]
    shared=None
    if grid is not None:
        covered=np.logical_or.reduce(list(coverages.values()))
        shared={"model":skeleton["survey"]["model"],"assumptions":skeleton["survey"]["assumptions"],
                "footprint_radius_m":skeleton["survey"]["footprint_radius_m"],
                "grid_spacing_m":skeleton["survey"]["grid_spacing_m"],"grid_point_count":len(grid),
                "covered_grid_point_count":int(covered.sum()),"coverage_fraction":float(covered.mean()),
                "required_fraction":skeleton["survey"]["required_group_coverage"],
                "declared_region_area_m2":skeleton["survey"].get("area_m2"),
                "planned_strip_count":skeleton["survey"].get("strip_count")}
    statuses=[v["result"]["status"] for v in per_agent.values()]
    conditions={"member_contributions_complete":False if "failure" in statuses else (None if "unknown" in statuses else True)}
    timing_diagnostics={"coordination_matches_assignment":None if coord["classification"]=="unknown" else coord["classification"]==mode,
                        "batch_members_match_assignment":None}
    if planned_batches is not None and coord["classification"] not in ("unknown", "not_applicable"):
        observed_partition={frozenset(b["members"]) for b in coord["batches"]}
        expected_partition={frozenset(a for a,b in planned_batches.items() if b==index)
                            for index in set(planned_batches.values())}
        timing_diagnostics["batch_members_match_assignment"]=observed_partition==expected_partition
    if shared:
        conditions["shared_coverage"]=measurable(shared["coverage_fraction"]>=shared["required_fraction"],complete)
    # Vertical-slice intrusion skeletons carry no approach field and were always multi-direction.
    if skeleton.get("approach_mode","multi_direction" if kind=="intrusion" else None)=="multi_direction":
        conditions["multi_direction_span"]=measurable(len(azimuths)==len(ids) and angular_span(azimuths)>=90,complete)
    result={"status":observed_conditions_result(conditions,complete),"conditions":conditions}
    observed_targets=sorted({fid for a in per_agent.values() for fid,r in a["observed"]["regions_by_facility"].items()
                             if r["warning"]["entered_observed"]})
    group={"assigned":{"members":sorted(ids),"role":skeleton["role"],"target":skeleton["target_id"],
                       "intent":skeleton["base_intent"],"planned_coordination":mode,
                       "planned_batches":planned_batches or {},"timing":timing_plan},
           "observed":{"members":sorted(ids),"coordination":coord,"timing_diagnostics":timing_diagnostics,"shared_coverage":shared,
                       "approach_span_deg":angular_span(azimuths) if len(azimuths)==len(ids) else None,
                       "members_with_known_core_event":sorted(a for a,e in core.items() if e["t_s"] is not None),
                       "behaviors":sorted({b for a in per_agent.values() for b in a["observed"]["behaviors"]})},
           "result":result}
    expansion="exclusion_policy" in skeleton
    if expansion:
        group["assigned"].update(execution_method=skeleton["execution_method"],approach_mode=skeleton["approach_mode"])
        # Unified multi-direction measure: entry azimuth into the work area about its centre.
        group["observed"].update(work_area_center_m=center.tolist(),
                                 entry_azimuths_deg={a:per_agent[a]["observed"]["contribution"].get("entry_azimuth_deg") for a in sorted(ids)})
    labels={"schema_version":EXPANSION_LABEL_VERSION if expansion else LABEL_VERSION,"evidence":{"source":EVIDENCE_SOURCE,"last_observed_s":float(t[-1]/1e6),
                "frame_count":len(t),"complete_observation":complete,"future_events_used":False,
                "geometry_version":GEOMETRY_VERSION},
            "agents":per_agent,"task_groups":{skeleton["group_id"]:group},
            "cluster":{"assigned":{"intent":skeleton["base_intent"],"target_set":[skeleton["target_id"]],
                                   "task_groups":[skeleton["group_id"]],"planned_coordination":mode,"timing_by_group":{skeleton["group_id"]:timing_plan}},
                       "observed":{"related_facilities":observed_targets,
                                   "primary_target":skeleton["target_id"] if len(core)==len(ids) and all(e["t_s"] is not None for e in core.values()) else None,
                                   "group_coordination":[{"group_id":skeleton["group_id"],**coord}],
                                   "minimum_separation_m":minimum,"closest_pair":closest},
                       "result":dict(result)},
            "frame_labels":{"file":"frame_labels.npz","source":EVIDENCE_SOURCE,"agent_ids":ids,
                            "facility_ids":[f["id"] for f in facilities],
                            "region_codes":{"0":"outside","1":"warning","2":"alert","3":"protected"},
                            "phase_codes":{"0":"low_speed","1":"approach_motion","2":"after_core_start","3":"withdrawal","4":"at_own_endpoint"}}}
    generation_error=minimum is not None and minimum<2.0
    labels["generation_quality"]={"status":"generation_error" if generation_error else "valid",
        "retained":not generation_error,"exclusion_reasons":["minimum_separation_below_2m"] if generation_error else [],
        "minimum_separation_m":minimum,"separation_error_threshold_m":2.0,
        "separation_affects_task_result":False,"hard_obstacle_sample_count":int(obstacle_inside.sum()),
        "outside_world_sample_count":int((~world_inside).sum())}
    frame={"time_us":t,"agent_ids":np.array(ids),"facility_ids":np.array([f["id"] for f in facilities]),
           "region_all_facilities":levels,"region_assigned_target":levels[:,:,target_fi],
           "phase":phases,"inside_hard_obstacle":obstacle_inside}
    return labels,frame
