"""Complete independent condition audit on exported 10 Hz evidence.

No task_v07 imports. Circle distances are analytic; polygon distances use GEOS
original contours. Missing condition coverage is an audit failure.
"""
from pathlib import Path
from itertools import combinations
import math
import hashlib
from contextlib import nullcontext
import numpy as np

from scripts.audit_v07_s2_exact import _read, _signed_distance, _inside
from scripts.audit_v07_s2_roles import (_load_truth, _build_levels, _center, _runs,
    _longest, _azimuth, _approach_heading_deg, _heading_span_deg,
    _check_region_facts, _check_separation)

TOLERANCE=1e-6


def _first(mask):
    hits=np.flatnonzero(mask)
    return int(hits[0]) if len(hits) else None


def _positive(ok, complete):
    return True if ok else False if complete else None


def _absence(violated, settled):
    return False if violated else True if settled else None


def _outcome(values, complete):
    return 'failure' if False in values else 'success' if all(v is True for v in values) else 'failure' if complete else 'unknown'


def _equal(left, right):
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left)==set(right) and all(_equal(left[k],right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left)==len(right) and all(_equal(a,b) for a,b in zip(left,right))
    if left is None or right is None: return left is None and right is None
    if isinstance(left,(bool,np.bool_)) or isinstance(right,(bool,np.bool_)): return bool(left)==bool(right)
    if isinstance(left,(int,float,np.number)) and isinstance(right,(int,float,np.number)):
        return abs(float(left)-float(right))<=TOLERANCE
    return left==right


def audit_conditions(root, *, data=None):
    root=Path(root)
    if data is None:
        scene,labels,task=(_read(root/name) for name in ('public_scene.json','labels.json','task.json'))
        ids,t,p,v=_load_truth(root)
    else:
        scene,labels,task=(data[key] for key in ('scene','labels','task'))
        ids,t,p,v=(data[key] for key in ('ids','t','p','v'))
    seconds=t/1e6;xy=p[:,:,:2]
    facilities=sorted((e for e in scene['entities'] if e['type']=='facility'),key=lambda e:e['id'])
    fids=[e['id'] for e in facilities];target=fids.index(task['target_id'])
    levels=_build_levels(scene,xy,fids)
    facility=facilities[target];center=_center(facility['geometry'])
    offsets={e['layer']:e['offset_m'] for e in scene['entities'] if e.get('facility_id')==task['target_id']}
    signed=_signed_distance(facility['geometry'],xy)
    kind=task['role']
    if kind=='reconnaissance': kind='close_observation' if task['execution_method']=='close_observation' else 'area_search'
    complete=bool(labels['evidence']['complete_observation'])
    errors=[];facts={};coverage={};core_frames={};work_ends={};statuses=[]
    mon_masks={};mon_angles={};coverage_masks=[]
    abort_member_conditions=[]
    region_diff=target_diff=0
    with (np.load(root/'frame_labels.npz',allow_pickle=False) if data is None else nullcontext(data['frame'])) as frame:
        if frame['agent_ids'].tolist()!=ids or not np.array_equal(frame['time_us'],t):
            raise ValueError('P0: label axes differ from truth')
        stored_ids=frame['facility_ids'].tolist()
        expected_in_order=levels[:,:,[fids.index(a) for a in stored_ids]]
        region_diff=int(np.count_nonzero(expected_in_order!=frame['region_all_facilities']))
        target_diff=int(np.count_nonzero(levels[:,:,target]!=frame['region_assigned_target']))
    errors+=_check_region_facts(labels,ids,levels,t,fids)
    obstacles=np.zeros(xy.shape[:2],bool)
    for entity in scene['entities']:
        if entity['type']=='hard_constraint_obstacle': obstacles|=_inside(entity['geometry'],xy)
    grid=None
    if kind=='area_search':
        survey=task['survey'];x0,y0,x1,y1=survey['bounds_m'];step=survey['grid_spacing_m']
        gx,gy=np.meshgrid(np.arange(x0+step/2,x1,step),np.arange(y0+step/2,y1,step))
        grid=np.c_[gx.ravel(),gy.ravel()]
        grid=grid[_inside(survey['geometry'],grid)]
    def compare(agent, field, stored, actual):
        if not _equal(stored,actual):
            errors.append({'agent_id':agent,'field':field,'label':stored,'independent':actual})
    for i,a in enumerate(ids):
        ob=labels['agents'][a]['observed'];ref=task['references'][a];con=ob['contribution']
        speed=np.linalg.norm(v[:,i],axis=1);track=xy[:,i]
        core=None;end=None;metrics={};checks={};basis={}
        def condition(name,value,*sources):
            checks[name]=value;basis[name]=list(sources)
        if kind=='intrusion':
            mask=levels[:,i,target]==3;core=_first(mask)
            depth=float(np.maximum(offsets['protected']-signed[:,i],0).max())
            metrics['maximum_protected_depth_m']=depth
            condition('entered_protected',_positive(core is not None,complete),'core_event_s','protected_membership')
            condition('required_depth',_positive(depth>=task['required_intrusion_depth_m'],complete),'maximum_protected_depth_m')
            end=None if core is None else float(seconds[core])
        elif kind=='transit':
            rules=task['transit'];inside=levels[:,i,target]>=1;core=_first(inside)
            visits=_runs(inside)
            last=int(visits[0][1])-1 if visits and visits[0][1]<len(t) else None
            visit=np.zeros(len(t),bool)
            if core is not None: visit[core:len(t) if last is None else last+1]=True
            moving=speed>=rules['low_speed_threshold_m_s']
            heading=np.arctan2(v[:,i,1],v[:,i,0])
            turn=round(float(np.degrees(np.abs(np.angle(np.exp(1j*np.diff(heading)))))[visit[1:]&visit[:-1]&moving[1:]&moving[:-1]].sum()),6)
            low=_longest(visit&~moving)
            entry=None if core is None else round(_azimuth(track[core]-center),6)
            exit_angle=chord=difference=None
            if last is not None:
                exit_angle=round(_azimuth(track[last]-center),6)
                chord=round(float(np.linalg.norm(track[last]-track[core])),6)
                difference=round(min(abs(exit_angle-entry),360-abs(exit_angle-entry)),6)
                end=float(seconds[last+1])
            metrics.update(warning_entry_s=None if core is None else float(seconds[core]),
                warning_exit_s=end,warning_last_inside_frame=last,chord_length_m=chord,
                entry_azimuth_deg=entry,exit_azimuth_deg=exit_angle,
                entry_exit_azimuth_difference_deg=difference,longest_low_speed_in_warning_s=low,
                cumulative_turn_in_warning_deg=turn)
            condition('entered_warning',_positive(core is not None,complete),'warning_entry_s')
            condition('exited_warning',_positive(last is not None,complete),'warning_exit_s')
            condition('chord_length',_positive(chord is not None and chord>=rules['minimum_chord_m'],complete),'chord_length_m')
            condition('entry_exit_azimuth_difference',_positive(difference is not None and difference>=rules['minimum_azimuth_difference_deg'],complete),'entry_exit_azimuth_difference_deg')
            condition('no_stop_in_warning',_absence(low>rules['maximum_low_speed_s'],last is not None or complete),'longest_low_speed_in_warning_s')
            condition('no_loop_in_warning',_absence(turn>=rules['maximum_cumulative_turn_deg'],last is not None or complete),'cumulative_turn_in_warning_deg')
        elif kind=='close_observation':
            rules=task['close_observation'];obs=np.asarray(ref['observation_point_enu_m'][:2])
            distances=np.linalg.norm(track-obs,axis=1);inside=distances<=rules['observation_radius_m']
            core=_first(inside);hits=np.flatnonzero(inside)
            last=int(hits[-1]) if len(hits) else None
            end=float(seconds[last]) if last is not None and last<len(t)-1 else None
            dwell=_longest(inside)
            metrics.update(dwell_s=dwell,observation_enter_s=None if core is None else float(seconds[core]),
                observation_exit_s=end,min_distance_to_obs_m=float(distances.min()))
            condition('reached_observation_point',_positive(core is not None,complete),'observation_enter_s')
            condition('minimum_dwell',_positive(dwell>=rules['minimum_dwell_s'],complete),'dwell_s')
            condition('no_alert_entry',not bool((levels[:,i,target]>=2).any()),'target_zone_membership')
        elif kind=='monitoring':
            rules=task['monitoring'];oc=np.asarray(rules['orbit_center_enu_m'][:2]);radius=rules['orbit_radius_m']
            radial=track-oc;norm=np.linalg.norm(radial,axis=1)
            vel=v[:,i,:2];vn=np.linalg.norm(vel,axis=1)
            tang=np.c_[radial[:,1],-radial[:,0]]
            cosine=np.sum(tang*vel,axis=1)/np.maximum(norm*vn,1e-18)
            along=np.degrees(np.arccos(np.clip(np.abs(cosine),0,1)))<=45.
            mask=(np.abs(norm-radius)<=rules['track_tolerance_m'])&along&(speed>=rules['effective_speed_min_m_s'])
            duration_frames=int(math.ceil(rules['min_loop_duration_s']*10))+1
            runs=_runs(mask);core=next((int(begin) for begin,stop in runs if stop-begin>=duration_frames),None)
            angles=np.arctan2(radial[:,1],radial[:,0]);delta=np.angle(np.exp(1j*np.diff(angles)))
            laps=round(abs(float(delta[mask[1:]].sum()))/(2*math.pi),3)
            last=int(np.flatnonzero(mask)[-1]) if mask.any() else None
            end=float(seconds[last]) if last is not None and last<len(t)-1 else None
            band=levels[:,i,target]==1
            metrics.update(lap_count_observed=laps,first_loop_start_s=None if core is None else float(seconds[core]),
                           in_band_fraction=float(band.mean()))
            condition('started_orbit',_positive(core is not None,complete),'first_loop_start_s')
            condition('completed_laps',_positive(laps>=rules['planned_laps']-.25,complete),'lap_count_observed')
            condition('stayed_in_band',_absence(bool((mask&~band).any()),end is not None or complete),'patrol_frame_band_membership')
            mon_masks[a]=mask;mon_angles[a]=angles
        elif kind=='feint':
            rules=task['feint'];distance=signed[:,i]
            core=_first(levels[:,i,target]>=2)
            band=levels[:,i,target]==2
            depth=float(np.maximum(offsets['alert']-distance,0)[band].max()) if band.any() else 0.
            fraction=depth/(offsets['alert']-offsets['protected'])
            entered=bool((levels[:,i,target]==3).any())
            turn=None if core is None else core+int(np.argmin(distance[core:]))
            turn_s=None if turn is None else float(seconds[turn])
            leave=None if turn is None else _first((np.arange(len(t))>turn)&(levels[:,i,target]==0))
            drop=descending=retreat=None
            if leave is not None:
                window=distance[turn:leave+1]
                high=np.maximum.accumulate(window);drop=float((high-window).max())
                descending=float(np.count_nonzero(np.diff(window)<0)/max(1,len(window)-1))
                retreat=drop<=rules['retreat_distance_tolerance_m'] and descending<=rules['retreat_drop_fraction_max']
                end=float(seconds[leave])
            metrics.update(max_depth_in_alert_m=round(depth,3),depth_fraction_in_alert_band=round(fraction,3),
                alert_entry_s=None if core is None else float(seconds[core]),entered_protected=entered,
                turnaway_s=turn_s,turnaway_frame=turn,maximum_retreat_drop_m=drop,
                retreat_descending_fraction=descending,retreat_ok=retreat)
            condition('entered_alert',_positive(core is not None,complete),'alert_entry_s')
            condition('depth_in_band',_positive(.3<=fraction<=.7,complete),'max_depth_in_alert_m','depth_fraction_in_alert_band')
            condition('no_protected_entry',not entered,'protected_membership')
            condition('retreat_direction',_positive(bool(retreat),end is not None or complete),'turnaway_s','maximum_retreat_drop_m','retreat_descending_fraction','work_end_s')
        elif kind=='area_search':
            survey=task['survey'];effective=_inside(ref['scan_geometry'],track)&(speed>=survey['effective_speed_min_m_s'])&(levels[:,i,target]==1)&~obstacles[:,i]
            cursor=0;visits=[]
            for q in ref['scan_lane_endpoints_m']:
                found=np.flatnonzero(np.linalg.norm(track[cursor:]-q,axis=1)<=survey['lane_endpoint_radius_m'])
                if not len(found): break
                cursor+=int(found[0]);visits.append(float(seconds[cursor]))
            done=len(visits)==len(ref['scan_lane_endpoints_m']);end=visits[-1] if done else None
            if end is not None: effective&=seconds<=end
            core=_first(effective)
            covered=np.zeros(len(grid),bool)
            if effective.any():
                for begin in range(0,len(grid),64):
                    block=grid[begin:begin+64]
                    covered[begin:begin+64]=np.min(np.sum((block[:,None]-track[effective][None])**2,axis=2),axis=1)<=survey['footprint_radius_m']**2
            coverage_masks.append(covered)
            metrics.update(ordered_lane_endpoint_times_s=visits,scan_pattern_observed=done,scan_end_s=end,
                covered_group_grid_points=int(covered.sum()),group_grid_point_count=len(grid),
                scan_segment_duration_s=None if end is None or core is None else round(end-seconds[core],6),
                effective_observation_duration_s=round(float(effective.sum())/10,6))
            condition('effective_observation',_positive(bool(effective.any()),complete),'effective_observation_duration_s')
            condition('scan_lane_evidence',_positive(done,complete),'ordered_lane_endpoint_times_s','scan_pattern_observed')
            condition('no_alert_entry',not bool((levels[:,i]>=2).any()),'all_facility_zone_membership')
        else: raise ValueError(f'No independent conditions for {kind}')
        if task.get('abort_observation'):
            from scripts.audit_v07_abort_facts import independent_abort
            abort_facts,abort_conditions=independent_abort(t,p[:,i],signed[:,i],levels[:,i,target],
                ref['endpoint_enu_m'],task['terminal_radius_m'],complete)
            metrics['abort_observation']=abort_facts
            abort_member_conditions.extend(abort_conditions.values())
            for name,value in abort_conditions.items():
                condition(name,value,'independent alert/protected membership','observed minimum-contour turn',
                          'post-turn warning exit','post-exit endpoint arrival')
            compare(a,'abort_behavior','approached_then_withdrew' in ob['behaviors'],abort_facts['approached_then_withdrew'])
            end=abort_facts['warning_exit_after_turn_s']
        core_frames[a]=core;work_ends[a]=end
        compare(a,'core_event_s',ob['core_event']['t_s'],None if core is None else float(seconds[core]))
        compare(a,'core_event_frame',ob['core_event']['frame_index'],core)
        for key,value in metrics.items():
            compare(a,key,con.get(key),value)
        compare(a,'work_end_s',ob.get('work_end_s'),end)
        end_distance=np.linalg.norm(p[:,i]-ref['endpoint_enu_m'],axis=1)
        after=np.zeros(len(t),bool) if end is None else seconds>=end
        arrival=_first((end_distance<=task['terminal_radius_m'])&after)
        hold=_longest((end_distance<=task['terminal_radius_m'])&(speed<=task['terminal_speed_m_s'])&after)
        compare(a,'endpoint_hold_s',ob['endpoint_hold_s'],hold)
        if (kind!='intrusion' or task.get('abort_observation')) and ref.get('retreat_required'):
            compare(a,'retreat_point_arrival',ob['retreat_event']['t_s'],None if arrival is None else float(seconds[arrival]))
            condition('reached_retreat_point',_positive(arrival is not None,complete),'work_end_s','retreat_point_arrival')
        condition('own_endpoint_hold',_positive(hold>=task['terminal_hold_s'],complete),'work_end_s','endpoint_hold_s')
        forbidden=np.zeros(len(t),bool)
        for fid,layer in task.get('exclusion_policy',{}).get(a,{}).items():
            forbidden|=levels[:,i,fids.index(fid)]>={'warning':1,'alert':2,'protected':3}[layer]
        if 'exclusion_policy' in task:
            condition('exclusion_policy_respected',_absence(bool(forbidden.any()),complete),'all_facility_zone_membership')
        stored=labels['agents'][a]['result']['conditions']
        missing=set(stored)-set(checks)
        for key in missing: errors.append({'agent_id':a,'uncovered_condition':key})
        for key,value in checks.items(): compare(a,'condition:'+key,stored.get(key),value)
        outcome=_outcome(list(checks.values()),complete)
        compare(a,'result.status',labels['agents'][a]['result']['status'],outcome);statuses.append(outcome)
        coverage[a]=basis
        facts[a]={'core_event_frame':core,'work_end_s':end,'endpoint_hold_s':hold,
                  'retreat_arrival_s':None if arrival is None else float(seconds[arrival]),**metrics}
    group=next(iter(labels['task_groups'].values()))
    group_checks={'member_contributions_complete':False if 'failure' in statuses else None if 'unknown' in statuses else True}
    group_basis={'member_contributions_complete':['independent per-agent conditions/status']}
    if task.get('abort_observation'):
        aborted=False if False in abort_member_conditions else None if None in abort_member_conditions else True
        group_checks['abort_group_withdrawal_observed']=aborted
        group_basis['abort_group_withdrawal_observed']=['all independently recomputed member abort predicates']
        compare(None,'abort_group_behavior','approached_then_withdrew' in group['observed']['behaviors'],aborted is True)
    warning_frames={}
    for i,a in enumerate(ids):
        hits=np.flatnonzero(levels[:,i,fids.index(task['target_id'])]>=1)
        warning_frames[a]=int(hits[0]) if len(hits) else None
    headings={a:_approach_heading_deg(xy[:,ids.index(a)],warning_frames[a]) for a in ids}
    if task.get('approach_mode')=='multi_direction':
        span=_heading_span_deg(list(headings.values()))
        group_checks['multi_direction_span']=_positive(span is not None and span>=90.,complete)
        group_basis['multi_direction_span']=['independent first target-warning entry frames','exact 100m path backtrack with interpolation','maximum pairwise displacement-heading angle; any missing member makes span unknown']
    if 'exclusion_policy' in task:
        for a in ids:
            compare(a,'approach_heading_deg',group['observed']['approach_headings_deg'][a],headings[a])
        compare(None,'approach_span_deg',group['observed']['approach_span_deg'],_heading_span_deg(list(headings.values())))
    if coverage_masks:
        covered=np.logical_or.reduce(coverage_masks)
        fraction=float(covered.mean())
        shared=group['observed']['shared_coverage']
        compare(None,'shared_coverage.grid_point_count',shared['grid_point_count'],len(grid))
        compare(None,'shared_coverage.covered_grid_point_count',shared['covered_grid_point_count'],int(covered.sum()))
        compare(None,'shared_coverage.coverage_fraction',shared['coverage_fraction'],fraction)
        group_checks['shared_coverage']=_positive(fraction>=task['survey']['required_group_coverage'],complete)
        group_basis['shared_coverage']=['independent strip endpoint order','effective observation masks','independent footprint/grid union']
    if kind=='monitoring':
        revisit=None
        starts=[None if core_frames[a] is None else float(seconds[core_frames[a]]) for a in ids]
        ends=list(work_ends.values())
        if None not in starts+ends:
            lo=max(starts);hi=min(ends)
            if hi>lo:
                maximum=0.
                for sector in range(36):
                    times=[]
                    for a in ids:
                        bins=(np.mod(mon_angles[a],2*math.pi)*36/(2*math.pi)).astype(int)
                        active=mon_masks[a]&(bins==sector)&(seconds>=lo)&(seconds<=hi)
                        times.extend(float(seconds[start]) for start,stop in _runs(active))
                    maximum=max(maximum,max(np.diff([lo,*sorted(times),hi]),default=0.))
                allowed=1.5*(2*math.pi*task['monitoring']['orbit_radius_m'])/(len(ids)*task['cruise_speed_m_s'])
                revisit={'window_s':[lo,hi],'maximum_interval_s':maximum,'allowed_interval_s':allowed,'sector_count':36}
        compare(None,'shared_revisit',group['observed'].get('shared_revisit'),revisit)
        group_checks['shared_revisit']=_positive(revisit is not None and revisit['maximum_interval_s']<=revisit['allowed_interval_s'],complete)
        group_basis['shared_revisit']=['last joint on-orbit window','independent angular-sector revisit intervals']
    for key in set(group['result']['conditions'])-set(group_checks):
        errors.append({'uncovered_condition':key,'scope':'task_group'})
    for key,value in group_checks.items():
        compare(None,'group_condition:'+key,group['result']['conditions'].get(key),value)
        compare(None,'cluster_condition:'+key,labels['cluster']['result']['conditions'].get(key),value)
    compare(None,'group_result.status',group['result']['status'],_outcome(list(group_checks.values()),complete))
    errors+=_check_separation(labels,p,ids)
    result={'directory':str(root),'status':'PASS' if not (errors or region_diff or target_diff) else 'P0_STOP',
            'frames':len(t),'agents':len(ids),'facilities':len(fids),'all_facility_frame_comparisons':int(levels.size),
            'region_difference_count':region_diff,'target_difference_count':target_diff,
            'event_or_metric_difference_count':len(errors),'event_or_metric_witnesses':errors[:50],
            'independent_role_facts':facts,'condition_audit_map':{'agents':coverage,'task_group':group_basis},
            'uncovered_conditions':[e for e in errors if 'uncovered_condition' in e],
            'float_tolerance':TOLERANCE,'method':'analytic circles / GEOS original contours, independent conditions and work-end facts',
            'truth_csv_sha256':hashlib.sha256((root/'truth.csv').read_bytes()).hexdigest()}
    if data is not None:
        result['independent_group_status']=_outcome(list(group_checks.values()),complete)
        result['independent_group_conditions']=group_checks
    return result
