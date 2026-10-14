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
EXPANSION_LABEL_VERSION="traj2language.labels/0.7-s2x.2"
EVIDENCE_SOURCE="truth.csv:10Hz_half_open_sim_clock"
_LAYER_CODES={"warning":1,"alert":2,"protected":3}

# Approach span: last N metres of trajectory before core event.
APPROACH_HEADING_DISTANCE_M=100.0


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
    if role=="reconnaissance" and skeleton.get("execution_method")=="close_observation":
        return "close_observation"
    if role=="monitoring":
        return "monitoring"
    if role=="feint":
        return "feint"
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


def approach_heading_deg(xy, core_frame, distance_m=APPROACH_HEADING_DISTANCE_M):
    """Mean heading over the last `distance_m` of trajectory before core_frame.

    Returns None if core_frame is None or there is insufficient path to measure.
    Works on 2-D XY positions at 10 Hz.
    """
    if core_frame is None or core_frame < 1:
        return None
    # Walk backwards from core_frame accumulating path length.
    end=min(core_frame,len(xy)-1)
    cum=0.0;start=end
    for k in range(end,0,-1):
        step=float(np.linalg.norm(xy[k]-xy[k-1]))
        cum+=step
        if cum>=distance_m:
            start=k-1;break
    if start==end:
        return None
    # Heading of vector from first to last point in that window.
    delta=xy[end]-xy[start]
    if np.linalg.norm(delta)<1e-9:
        return None
    return float(np.degrees(np.arctan2(delta[1],delta[0]))%360)


def heading_span_deg(headings):
    """Maximum pairwise angular difference among a list of headings (degrees, [0,360)).

    Returns None if any heading is None or the list has fewer than 2 elements.
    Uses the circular distance: min(|a-b|, 360-|a-b|).
    """
    valid=[h for h in headings if h is not None]
    if len(valid)<2:
        return None
    return float(max(min(abs(a-b),360-abs(a-b)) for a,b in combinations(valid,2)))


def _primary_target_from_evidence(facilities, levels, ids, by_id, skeleton):
    """§9.2: primary target from actual trajectory evidence.

    - If all groups share the same assigned target → that facility.
    - Else if base_intent is penetration and exactly one facility was actually
      entered at protected level → that facility.
    - Otherwise None.
    """
    target=skeleton["target_id"]
    # Single-group skeleton: if target is unique (or only group target present), use it.
    # Multi-group: handled by caller.
    return target  # single-group: assigned target is the primary target.


def measure(scene,skeleton,run,mode,planned_batches=None,*,cutoff_s=None,timing_plan=None):
    if 'group_skeletons' in skeleton:
        from .expansion.multi_labels import measure_groups
        return measure_groups(scene,skeleton,run,mode,planned_batches,cutoff_s=cutoff_s,timing_plan=timing_plan)
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
    monitoring_masks={};monitoring_angles={};work_ends={}
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
    # For vertical-slice intrusion: legacy azimuth tracking (entry point relative to facility centre).
    # For expansion skeletons: approach heading tracking (last 100 m before core event).
    expansion="exclusion_policy" in skeleton
    legacy_azimuths=[]         # vertical-slice intrusion only
    approach_headings_deg={}   # expansion skeletons only
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
                legacy_azimuths.append(azimuth)
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
            chord=difference=exit_azimuth=None
            entry_azimuth=round(azimuth_deg(xy[first]-center),6) if first is not None else None
            if last is not None:
                exit_azimuth=round(azimuth_deg(xy[last]-center),6)
                chord=round(float(np.linalg.norm(xy[last]-xy[first])),6)
                difference=round(abs((exit_azimuth-entry_azimuth+180)%360-180),6)
                work_end=float(t[last+1]/1e6)
            settled=last is not None or complete
            behavior=(["crossed_warning_zone"] if last is not None else
                      ["entered_warning_zone"] if first is not None else [])
            contribution={"warning_entry_s":core[a]["t_s"],"warning_exit_s":work_end,
                          "warning_last_inside_frame":last,"warning_visit_duration_s":None if last is None else round((last-first)/10,6),
                          "chord_length_m":chord,"entry_azimuth_deg":entry_azimuth,"exit_azimuth_deg":exit_azimuth,
                          "entry_exit_azimuth_difference_deg":difference,
                          "longest_low_speed_in_warning_s":low_hold,"cumulative_turn_in_warning_deg":cumulative}
            role_conditions={"entered_warning":measurable(first is not None,complete),
                             "exited_warning":measurable(last is not None,complete),
                             "chord_length":measurable(chord is not None and chord>=criteria["minimum_chord_m"],complete),
                             "entry_exit_azimuth_difference":measurable(difference is not None and difference>=criteria["minimum_azimuth_difference_deg"],complete),
                             "no_stop_in_warning":bounded(low_hold>criteria["maximum_low_speed_s"],settled),
                             "no_loop_in_warning":bounded(cumulative>=criteria["maximum_cumulative_turn_deg"],settled)}
        elif kind=="close_observation":
            rules=skeleton["close_observation"]
            obs_radius=rules["observation_radius_m"]
            obs_center=np.array(ref.get("observation_point_enu_m",[skeleton["references"][a]["endpoint_enu_m"][0],skeleton["references"][a]["endpoint_enu_m"][1]])[:2])
            dist_to_obs=np.linalg.norm(xy-obs_center,axis=1)
            inside_obs=dist_to_obs<=obs_radius
            core[a]=event(inside_obs,t,"observation_point_arrival")
            obs_enter=core[a]["frame_index"]
            # Only the observed last in-radius frame defines work completion.
            hits=np.flatnonzero(inside_obs)
            obs_last=int(hits[-1]) if len(hits) else None
            work_end=(float(t[obs_last]/1e6) if obs_last is not None and obs_last<len(t)-1 else None)
            dwell_time=longest_hold(inside_obs)
            obs_exit_frame=None if work_end is None else obs_last+1
            in_alert=np.any(levels[:,i,target_fi]>=2)
            settled_obs=obs_exit_frame is not None or complete
            behavior=(["close_observation_point_reached"] if obs_enter is not None else [])
            contribution={"observation_radius_m":obs_radius,"dwell_s":dwell_time,
                          "observation_enter_s":core[a]["t_s"],"observation_exit_s":work_end,
                          "observation_point_enu_m":obs_center.tolist(),"min_distance_to_obs_m":float(dist_to_obs.min())}
            role_conditions={"reached_observation_point":measurable(obs_enter is not None,complete),
                             "minimum_dwell":measurable(dwell_time>=rules.get("minimum_dwell_s",0),complete),
                             "no_alert_entry":bool(not in_alert)}
        elif kind=="monitoring":
            rules=skeleton["monitoring"]
            orbit_center=np.array(rules["orbit_center_enu_m"][:2])
            orbit_radius=rules["orbit_radius_m"]
            track_tol=rules.get("track_tolerance_m",30.0)
            min_speed=rules.get("effective_speed_min_m_s",0.5)
            on_orbit_dist=np.abs(np.linalg.norm(xy-orbit_center,axis=1)-orbit_radius)
            on_orbit=on_orbit_dist<=track_tol
            # Heading check: within 45 deg of orbit tangent at current position.
            to_center=orbit_center-xy
            tangent=np.stack([-to_center[:,1],to_center[:,0]],axis=1)
            tangent_norm=np.linalg.norm(tangent,axis=1,keepdims=True)
            tangent_norm=np.where(tangent_norm<1e-9,1e-9,tangent_norm)
            tangent_unit=tangent/tangent_norm
            vel_xy=v[:,i,:2];vel_norm=np.linalg.norm(vel_xy,axis=1,keepdims=True)
            vel_norm=np.where(vel_norm<1e-9,1e-9,vel_norm)
            vel_unit=vel_xy/vel_norm
            cos_angle=np.clip(np.sum(vel_unit*tangent_unit,axis=1),-1,1)
            along_orbit=np.abs(np.degrees(np.arccos(np.abs(cos_angle))))<=45.0
            moving=speed>=min_speed
            # Core event: first 5-second run of on_orbit & along_orbit & moving.
            min_frames=max(1,int(math.ceil(rules.get("min_loop_duration_s",5.0)*10))+1)
            valid_frame=on_orbit&along_orbit&moving
            core_frame=None
            run_len=0
            for fi_,ok in enumerate(valid_frame):
                if ok:
                    run_len+=1
                    if run_len>=min_frames:
                        core_frame=fi_-min_frames+1;break
                else:
                    run_len=0
            core[a]=event(np.arange(len(t))==core_frame if core_frame is not None else np.zeros(len(t),bool),t,"first_loop_start")
            # Cumulative angle for lap count.
            angles=np.arctan2(xy[:,1]-orbit_center[1],xy[:,0]-orbit_center[0])
            d_angles=np.diff(angles);d_angles=(d_angles+math.pi)%(2*math.pi)-math.pi
            lap_count=round(abs(float(d_angles[valid_frame[1:]].sum()))/(2*math.pi),3)
            planned_laps=rules.get("planned_laps",1.0)
            in_band=levels[:,i,target_fi]==1
            out_of_band=valid_frame&~in_band
            hits=np.flatnonzero(valid_frame)
            last_valid=int(hits[-1]) if len(hits) else None
            work_end=(float(t[last_valid]/1e6) if last_valid is not None and last_valid<len(t)-1 else None)
            monitoring_masks[a]=valid_frame
            monitoring_angles[a]=angles
            settled_mon=work_end is not None or complete
            behavior=(["orbit_started"] if core_frame is not None else [])
            if lap_count>=0.9*planned_laps:
                behavior.append("planned_laps_completed")
            contribution={"orbit_radius_m":orbit_radius,"track_tolerance_m":track_tol,
                          "lap_count_observed":lap_count,"planned_laps":planned_laps,
                          "first_loop_start_s":core[a]["t_s"],"in_band_fraction":float(in_band.mean())}
            role_conditions={"started_orbit":measurable(core_frame is not None,complete),
                             "completed_laps":measurable(lap_count>=planned_laps-0.25,complete),
                             "stayed_in_band":bounded(bool(out_of_band.any()),settled_mon)}
        elif kind=="feint":
            rules=skeleton["feint"]
            # Core: first entry into alert zone of target.
            in_alert=levels[:,i,target_fi]>=2
            core[a]=event(in_alert,t,"enter_alert_zone")
            first=core[a]["frame_index"]
            # Maximum penetration depth in alert band (not protected).
            in_alert_only=(levels[:,i,target_fi]==2)
            contour_distance=facility_facts[skeleton["target_id"]]["signed_distance_m"][:,i]
            alert_offset=next(e["offset_m"] for e in scene["entities"] if e.get("facility_id")==skeleton["target_id"] and e.get("layer")=="alert")
            max_depth_in_band=(float(np.maximum(alert_offset-contour_distance,0)[in_alert_only].max())
                               if in_alert_only.any() else 0.0)
            entered_protected=bool((levels[:,i,target_fi]>=3).any())
            # Retreat monotonicity uses exact contour distance, after the deepest frame.
            turnaway_s=None;retreat_ok=None;turnaway_frame=None
            maximum_retreat_drop_m=None;retreat_descending_fraction=None
            if first is not None:
                turnaway_frame=first+int(np.argmin(contour_distance[first:]))
                turnaway_s=float(t[turnaway_frame]/1e6)
                outside=np.flatnonzero((levels[:,i,target_fi]==0)&(np.arange(len(t))>turnaway_frame))
                leave_frame=int(outside[0]) if len(outside) else None
                if leave_frame is not None:
                    window=contour_distance[turnaway_frame:leave_frame+1]
                    deficits=np.maximum.accumulate(window)-window
                    maximum_retreat_drop_m=float(deficits.max())
                    retreat_descending_fraction=float(np.count_nonzero(np.diff(window)<0)/max(1,len(window)-1))
                    retreat_ok=bool(maximum_retreat_drop_m<=rules.get("retreat_distance_tolerance_m",5.0)
                                    and retreat_descending_fraction<=rules.get("retreat_drop_fraction_max",0.10))
                    work_end=float(t[leave_frame]/1e6)
            alert_band_thickness=alert_offset-next(e["offset_m"] for e in scene["entities"] if e.get("facility_id")==skeleton["target_id"] and e.get("layer")=="protected")
            depth_frac=max_depth_in_band/alert_band_thickness if alert_band_thickness>0 else 0.0
            settled_feint=(work_end is not None) or complete
            behavior=(["feint_executed"] if first is not None else [])
            contribution={"alert_entry_s":core[a]["t_s"],"max_depth_in_alert_m":round(max_depth_in_band,3),
                          "depth_fraction_in_alert_band":round(depth_frac,3),
                          "turnaway_s":turnaway_s,"retreat_ok":retreat_ok,
                          "turnaway_frame":turnaway_frame,"maximum_retreat_drop_m":maximum_retreat_drop_m,
                          "retreat_descending_fraction":retreat_descending_fraction,
                          "entered_protected":entered_protected,
                          "retreat_tolerance_m":rules.get("retreat_distance_tolerance_m",5.0),
                          "retreat_drop_fraction_max":rules.get("retreat_drop_fraction_max",0.10)}
            role_conditions={"entered_alert":measurable(first is not None,complete),
                             "depth_in_band":measurable(0.3<=depth_frac<=0.7,complete),
                             "no_protected_entry":bool(not entered_protected),
                             "retreat_direction":measurable(retreat_ok,settled_feint)}
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
            work_end=scan_end

        # Approach heading (expansion skeletons only; vertical-slice uses legacy azimuth path).
        if expansion:
            approach_headings_deg[a]=approach_heading_deg(xy,core[a]["frame_index"])

        if expansion and kind=="intrusion":
            work_end=core[a]["t_s"]
        work_ends[a]=work_end
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
        if expansion:
            # Explicit private per-ID policy: the named layer and every inner layer are forbidden.
            forbidden=np.zeros(len(t),bool)
            for fid,layer in skeleton["exclusion_policy"][a].items():
                forbidden|=levels[:,i,[f["id"] for f in facilities].index(fid)]>=_LAYER_CODES[layer]
            role_conditions["exclusion_policy_respected"]=bounded(forbidden.any(),complete)
        if expansion:
            dwell &= np.zeros(len(t),bool) if work_end is None else t/1e6>=work_end
        hold=longest_hold(dwell)
        conditions={**role_conditions,"own_endpoint_hold":measurable(hold>=skeleton["terminal_hold_s"],complete)}
        outcome=observed_conditions_result(conditions,complete)
        phases[:,i]=np.where(speed>.5,1,0)
        if core[a]["frame_index"] is not None:
            phases[core[a]["frame_index"]:,i]=2
        if kind=="area_search" and contribution["scan_pattern_observed"]:
            phases[t/1e6>contribution["ordered_lane_endpoint_times_s"][-1],i]=3
        elif kind in ("transit","feint","close_observation") and work_end is not None:
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
        if expansion:
            per_agent[a]["observed"]["work_end_s"]=work_end
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
    # Multi-direction span condition.
    # Vertical-slice intrusion: legacy azimuth-based angular_span (unchanged for regression).
    # Expansion skeletons: new "last 100 m approach heading" span.
    if not expansion:
        if skeleton.get("approach_mode","multi_direction" if kind=="intrusion" else None)=="multi_direction":
            conditions["multi_direction_span"]=measurable(len(legacy_azimuths)==len(ids) and angular_span(legacy_azimuths)>=90,complete)
    else:
        if skeleton.get("approach_mode")=="multi_direction":
            span=heading_span_deg([approach_headings_deg.get(a) for a in sorted(ids)])
            conditions["multi_direction_span"]=measurable(span is not None and span>=90,complete)
    revisit=None
    if kind=="monitoring":
        known_starts=[e["t_s"] for e in core.values()]
        known_ends=list(work_ends.values())
        if all(v is not None for v in known_starts+known_ends):
            lo=max(known_starts);hi=min(known_ends)
            if hi>lo:
                angles_by_agent=monitoring_angles
                longest=0.0
                # First entry into each 10-degree angular bin is a revisit witness.
                for sector in range(36):
                    visits=[]
                    for a in sorted(ids):
                        bins=np.floor((angles_by_agent[a]%(2*math.pi))*36/(2*math.pi)).astype(int)
                        mask=monitoring_masks[a]&(bins==sector)&(t/1e6>=lo)&(t/1e6<=hi)
                        starts=np.flatnonzero(mask&~np.r_[False,mask[:-1]])
                        visits.extend(float(t[k]/1e6) for k in starts)
                    gaps=np.diff([lo,*sorted(visits),hi])
                    longest=max(longest,float(gaps.max()) if len(gaps) else 0.0)
                perimeter=2*math.pi*skeleton["monitoring"]["orbit_radius_m"]
                allowed=1.5*perimeter/(len(ids)*skeleton["cruise_speed_m_s"])
                revisit={"window_s":[lo,hi],"maximum_interval_s":longest,
                         "allowed_interval_s":allowed,"sector_count":36}
        conditions["shared_revisit"]=measurable(revisit is not None and revisit["maximum_interval_s"]<=revisit["allowed_interval_s"],complete)
    result={"status":observed_conditions_result(conditions,complete),"conditions":conditions}
    observed_targets=sorted({fid for a in per_agent.values() for fid,r in a["observed"]["regions_by_facility"].items()
                             if r["warning"]["entered_observed"]})
    # §9.2 primary_target for single-group skeleton:
    # - All members share the same assigned target → that facility.
    # - (Multi-group handled in caller; here we only have one group.)
    # - But we must not output the assigned target as "observed" primary if
    #   no core events were actually observed.
    all_events_known=all(e["t_s"] is not None for e in core.values()) and len(core)==len(ids)
    primary_target=skeleton["target_id"] if all_events_known else None
    group={"assigned":{"members":sorted(ids),"role":skeleton["role"],"target":skeleton["target_id"],
                       "intent":skeleton["base_intent"],"planned_coordination":mode,
                       "planned_batches":planned_batches or {},"timing":timing_plan},
           "observed":{"members":sorted(ids),"coordination":coord,"timing_diagnostics":timing_diagnostics,"shared_coverage":shared,
                       "approach_span_deg":angular_span(legacy_azimuths) if (not expansion and len(legacy_azimuths)==len(ids)) else None,
                       "members_with_known_core_event":sorted(a for a,e in core.items() if e["t_s"] is not None),
                       "behaviors":sorted({b for a in per_agent.values() for b in a["observed"]["behaviors"]})},
           "result":result}
    if kind=="monitoring":
        group["observed"]["shared_revisit"]=revisit
    if expansion:
        span_val=heading_span_deg([approach_headings_deg.get(a) for a in sorted(ids)])
        group["assigned"].update(execution_method=skeleton["execution_method"],approach_mode=skeleton["approach_mode"])
        group["observed"].update(
            work_area_center_m=center.tolist(),
            approach_headings_deg={a:approach_headings_deg.get(a) for a in sorted(ids)},
            approach_span_deg=span_val,
            approach_span_definition=f"max pairwise angle among per-member mean headings over last {APPROACH_HEADING_DISTANCE_M:.0f} m before core event")
    else:
        # Vertical-slice: legacy approach_span_deg from entry azimuths about facility centre.
        group["observed"]["approach_span_deg"]=(angular_span(legacy_azimuths) if len(legacy_azimuths)==len(ids) else None)
    labels={"schema_version":EXPANSION_LABEL_VERSION if expansion else LABEL_VERSION,"evidence":{"source":EVIDENCE_SOURCE,"last_observed_s":float(t[-1]/1e6),
                "frame_count":len(t),"complete_observation":complete,"future_events_used":False,
                "geometry_version":GEOMETRY_VERSION},
            "agents":per_agent,"task_groups":{skeleton["group_id"]:group},
            "cluster":{"assigned":{"intent":skeleton["base_intent"],
                                   "target_set":[skeleton["target_id"]],
                                   "task_groups":[skeleton["group_id"]],"planned_coordination":mode,"timing_by_group":{skeleton["group_id"]:timing_plan}},
                       "observed":{"related_facilities":observed_targets,
                                   "primary_target":primary_target,
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
