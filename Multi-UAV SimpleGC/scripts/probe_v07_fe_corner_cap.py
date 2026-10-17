"""D0 isolated solo probes; production files and frozen criteria remain untouched."""
import argparse,copy,json,math,subprocess,sys,time,traceback
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
import numpy as np
PROJECT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PROJECT))
from scripts.qc_v07_fe_corner_dwell import OUT,DATA,BASE,read,save,sha,digest,require,verify_manifest,corner_kind
from scripts.qc_v07_fe_speed_profile import analyse_member
from task_v07.execution import execute,frozen_config
from task_v07.criteria import load_criteria
from task_v07.detectors import dwell,work_mask
from task_v07.geometry import geometry_facts
from swarm_sim.fast_dynamics.route_tracker import RouteTracker,_curvature_bounds
ORIGINAL_BUILD=RouteTracker._build
CAP_LOG={}
MARKER='EXPERIMENTAL_REFERENCE_NOT_FROZEN'

def tracker_geometry(tracker):
    return {'points':tracker.points.tolist(),'gates':tracker.gates.tolist(),'short_continuations':sorted(tracker.short_continuations),'primitives':[{'start':q.start.tolist(),'end':q.end.tolist(),'length':q.length,'stop':q.stop,'node_index':q.node_index,'control':None if q.control is None else q.control.tolist()} for q in tracker.primitives]}

def experimental_build(self):
    ORIGINAL_BUILD(self)
    before=tracker_geometry(self);changes=[]
    for i,q in enumerate(self.primitives):
        if q.control is None:continue
        n=q.node_index;u=self.points[n,:2]-self.points[n-1,:2];w=self.points[n+1,:2]-self.points[n,:2]
        angle=math.acos(float(np.clip((u/np.linalg.norm(u))@(w/np.linalg.norm(w)),-1,1)))
        require(corner_kind(angle)=='CURVE','Unexpected non-CURVE control primitive')
        k,ks=_curvature_bounds(q.derivatives);old=q.cap
        q.cap=min(self.speed,math.sqrt(self.profile.max_accel_xy_m_s2/(2*k)),(self.profile.max_jerk_m_s3/(2*(k*k+ks)))**(1/3))
        d=min(self.reference.corner_cut_max_m,self.reference.corner_leg_fraction*np.linalg.norm(u),self.reference.corner_leg_fraction*np.linalg.norm(w))
        h=self.controller.velocity_response_time_s+self.profile.response_time_s
        changes.append({'primitive_index':i,'node_index':n,'angle_deg':math.degrees(angle),'old_cap_m_s':old,'new_cap_m_s':q.cap,'horizon_cap_m_s':float(d/h),'horizon_dominant':abs(old-d/h)<=1e-12,'curvature_bound':k,'curvature_derivative_bound':ks})
    for i,q in enumerate(self.primitives):
        q.exit_cap=(0. if q.stop or i==len(self.primitives)-1 else self.primitives[i+1].cap if self.primitives[i+1].control is not None else self.speed) if q.control is None else q.cap
    require(tracker_geometry(self)==before,'Patch changed geometry or stop semantics')
    require(type(self) is RouteTracker,'P0 tracker type identity changed')
    CAP_LOG[id(self)]=changes

def replay_with_capture(group,agent,arm):
    """Read-only Python return-event tracing captures live trackers without patching A.

    Held object references preserve committed witness lists after transaction rollback.
    No observe_segment wrapper: tentative events must never be counted as committed.
    """
    captured=[];code=RouteTracker.__init__.__code__;previous=sys.gettrace()
    def trace(frame,event,arg):
        if event=='call' and frame.f_code is code:
            frame.f_trace_lines=False
            return on_return
        return None
    def on_return(frame,event,arg):
        if event=='return':captured.append(frame.f_locals['self'])
        return on_return
    require(arm in ('A','B'),'Bad arm');context=patch.object(RouteTracker,'_build',experimental_build) if arm=='B' else nullcontext()
    try:
        with context:
            sys.settrace(trace)
            run=execute(group,{a:0. for a in group['members']},only_agent=agent)
    finally:
        sys.settrace(previous)
    require(RouteTracker._build is ORIGINAL_BUILD,'Patch failed to restore original method')
    points=np.asarray(group['references'][agent]['points_enu_m']);intermediate=group['references'][agent].get('intermediate_dwell')
    if intermediate:
        n=intermediate['waypoint_index'];require(len(captured) in (2,3),'Unexpected dwell tracker construction sequence')
        require(np.array_equal(captured[0].points,points) and not captured[0].witnesses,'Unexpected unused full-route tracker activity')
        active=[(0,captured[1])]
        require(np.array_equal(captured[1].points,points[:n+1]),'Wrong dwell approach route')
        if len(captured)==3:
            require(np.array_equal(captured[2].points,points[n:]),'Wrong dwell departure route');active.append((n,captured[2]))
    else:
        require(len(captured)==1 and np.array_equal(captured[0].points,points),'Unexpected tracker sequence');active=[(0,captured[0])]
    snapshots=[];witnesses=[]
    for offset,t in active:
        snapshots.append({'original_node_offset':offset,'geometry_sha256':digest(tracker_geometry(t)),'geometry':tracker_geometry(t),'diagnostics':t.diagnostics,'cap_changes':CAP_LOG.get(id(t),[]),'primitive_caps':[{'cap':q.cap if math.isfinite(q.cap) else None,'exit_cap':q.exit_cap} for q in t.primitives]})
        for event in t.witnesses:
            # A dwell departure's node zero reacquires the already witnessed hold node.
            # It is separately retained in diagnostics, not counted as another raw route node.
            if offset and event['node_index']==0:continue
            witnesses.append({**event,'node_index':offset+event['node_index']})
    return run,snapshots,witnesses

def polyline_deviations(xy,points):
    points=np.asarray(points,float)[:,:2];starts=points[:-1];legs=np.diff(points,axis=0);den=np.sum(legs*legs,axis=1)
    require(np.all(den>0),'Zero-length reference segment')
    distances=[];segments=[]
    for offset in range(0,len(xy),256):
        block=xy[offset:offset+256];delta=block[:,None,:]-starts[None,:,:]
        t=np.clip(np.sum(delta*legs[None,:,:],axis=2)/den[None,:],0,1)
        d=np.linalg.norm(delta-t[:,:,None]*legs[None,:,:],axis=2);index=np.argmin(d,axis=1)
        distances.extend(d[np.arange(len(block)),index]);segments.extend(index)
    return np.asarray(distances),np.asarray(segments,dtype=int)

def baseline_compare(run,archive):
    require(archive.is_file(),'Missing historical solo archive '+str(archive));differences=[]
    with np.load(archive,allow_pickle=False) as old:
        for key in ('time_us','p','v'):
            if old[key].shape!=run[key].shape:differences.append({'field':key,'old_shape':list(old[key].shape),'new_shape':list(run[key].shape)});continue
            # Exact exported values AND underlying bytes, including signed-zero bits.
            if old[key].dtype!=run[key].dtype or old[key].tobytes()!=run[key].tobytes():
                unequal=np.argwhere(old[key]!=run[key]);index=tuple(unequal[0]) if len(unequal) else None
                differences.append({'field':key,'first_index':None if index is None else list(map(int,index)),'historical_value':None if index is None else float(old[key][index]),'new_value':None if index is None else float(run[key][index]),'bitwise_equal':False})
        if str(old['execution_status'].item())!=run['execution_status']:differences.append({'field':'execution_status','old':str(old['execution_status'].item()),'new':run['execution_status']})
    return {'status':'BITWISE_IDENTICAL' if not differences else 'MISMATCH','archive':str(archive),'archive_sha256':sha(archive),'differences':differences}

def metrics(run,group,agent,scene,snapshots,witnesses,probe):
    cfg=frozen_config();xy=run['p'][:,0,:2];speed=np.linalg.norm(run['v'][:,0,:2],axis=1);a=run['a'][:,0];points=np.asarray(group['references'][agent]['points_enu_m'])
    target=next(e for e in scene['entities'] if e['type']=='facility' and e['id']==group['target_id'])
    offsets={e['layer']:e['offset_m'] for e in scene['entities'] if e.get('facility_id')==target['id']}
    levels=geometry_facts(target['geometry'],xy,layer_offsets=offsets)['layer']
    dwelling=dwell(xy,run['time_us'],work_mask(levels),load_criteria())
    observation=dwell(xy,run['time_us'],levels==1,load_criteria()) if group['execution_method']=='close_observation' else None
    qc=analyse_member(group,run,agent,probe['skeleton_id'],'solo_probe',{agent:(group['group_id'],group)})
    deviations,segments=polyline_deviations(xy,points);worst=int(np.argmax(deviations))
    ids=[e['node_index'] for e in witnesses if 0<e['node_index']<len(points)-1];expected=list(range(1,len(points)-1));missing=sorted(set(expected)-set(ids));duplicate=sorted(n for n in set(ids) if ids.count(n)>1)
    position_error=float(np.linalg.norm(run['p'][-1,0]-points[-1]));end_speed=float(np.linalg.norm(run['v'][-1,0]));max_accel=float(np.linalg.norm(a[:,:2],axis=1).max())
    checks={'completed':run['execution_status']=='completed','finite_pva':all(np.isfinite(run[k]).all() for k in ('p','v','a')),'terminal_position':position_error<=group['terminal_radius_m'],'terminal_speed':end_speed<=group['terminal_speed_m_s'],'maximum_speed':float(speed.max())<=cfg.vehicle_profile.max_speed_xy_m_s+cfg.quality.max_speed_tolerance_m_s,'horizontal_acceleration':max_accel<=cfg.vehicle_profile.max_accel_xy_m_s2+1e-10,'vertical_acceleration':float(a[:,2].max())<=cfg.vehicle_profile.max_accel_up_m_s2+1e-10 and float(a[:,2].min())>=-cfg.vehicle_profile.max_accel_down_m_s2-1e-10,'member_id':run['agent_ids']==[agent],'initial_position':np.array_equal(run['p'][0,0],np.asarray(next(s for s in group['initial_states'] if s['agent_id']==agent)['position_enu_m']))}
    tracking={'route_node_witnessed_events':len(ids),'internal_waypoints':len(expected),'event_to_waypoint_ratio':len(ids)/len(expected) if expected else None,'all_waypoints_witnessed':ids==expected,'missing_waypoint_indices':missing,'duplicate_waypoint_indices':duplicate,'max_lateral_deviation_m':float(deviations.max()),'p99_lateral_deviation_m':float(np.quantile(deviations,.99)),'tracking_tube_m':cfg.reference.tracking_tube_m,'maximum_frame_index':worst,'maximum_time_s':float(run['time_us'][worst]/1e6),'maximum_nearest_segment_index':int(segments[worst]),'maximum_segment_vertex_indices':[int(segments[worst]),int(segments[worst])+1],'frames_exceeding_tube':int(np.sum(deviations>cfg.reference.tracking_tube_m)),'classification':'TRACKING_ACCURACY_PRESERVED' if ids==expected and deviations.max()<=cfg.reference.tracking_tube_m else 'TRACKING_ACCURACY_DEGRADED','event_count_note':'Only committed final witness lists; map split dwell trackers to original nodes, exclude departure re-acquisition of already witnessed hold node. Raw subtracker witnesses retained.'}
    return {'marker':MARKER,'scope':'solo_probe','execution_status':run['execution_status'],'dwell':dwelling,'observation_dwell':observation,'low_speed':qc,'motion_total_s':qc['motion_window_duration_s'],'exported_duration_s':float((run['time_us'][-1]-run['time_us'][0])/1e6),'wall_s':run['wall_s'],'maximum_speed_m_s':float(speed.max()),'maximum_acceleration_m_s2':max_accel,'terminal_position_error_m':position_error,'terminal_speed_m_s':end_speed,'terminal_radius_m':group['terminal_radius_m'],'terminal_speed_limit_m_s':group['terminal_speed_m_s'],'physical_checks':checks,'physical_status':'PASS' if all(checks.values()) else 'FAIL','tracking':tracking,'tracker_snapshots':snapshots,'original_node_witnesses':witnesses,'time_budget':run['time_budget'],'continuous_jerk_claim':'Not inferred from 10 Hz acceleration differences. Original continuous integrator unchanged.'},deviations,segments

def worker(probe_id,arm,out):
    manifest=read(OUT/'D0_source_manifest.json');selection=read(OUT/'D0_probe_selection.json');lock=read(Path(manifest['external_output'])/'selection_lock.json')
    require(sha(OUT/'D0_probe_selection.json')==lock['sha256'],'Selection changed')
    probe=next(p for p in selection['probes'] if p['probe_id']==probe_id);root=Path(probe['episode'])
    require(all(sha(root/f)==h for f,h in probe['input_sha256'].items()),'Probe input changed')
    task=read(root/'task.json');group=copy.deepcopy(task['group_skeletons'][probe['group_id']]);before=digest(group)
    require('cruise_speed_m_s' in group,'Solo execute group missing cruise speed')
    out.mkdir(parents=True,exist_ok=False)
    try:
        run,snapshots,witnesses=replay_with_capture(group,probe['agent_id'],arm)
        require(digest(group)==before,'Replay changed group input')
        np.savez_compressed(out/'run.npz',**{k:run[k] for k in ('time_us','p','v','a','agent_ids','execution_status')})
        result,distances,segments=metrics(run,group,probe['agent_id'],read(root/'public_scene.json'),snapshots,witnesses,probe)
        np.savez_compressed(out/'tracking_distances.npz',time_us=run['time_us'],distance_m=distances,nearest_segment_index=segments)
        if arm=='A':
            cal=read(root.parent/'timing_calibration.json');archive=root.parent/f"geometry_{cal['calibration_round']-1:02d}"/f"single_agent_{probe['agent_id']}.npz"
            result['baseline_reproduction']=baseline_compare(run,archive)
        result.update(probe_id=probe_id,arm=arm,input_group_sha256=before,patch_restored=RouteTracker._build is ORIGINAL_BUILD,status='COMPLETE')
        save(out/'result.json',result)
    except Exception as exc:
        save(out/'error.json',{'status':'ERROR','type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()});raise

def launch():
    manifest=verify_manifest();require(read(OUT/'D0_corner_cap_analysis.json')['status']=='PASS','G2 failed')
    selection=read(OUT/'D0_probe_selection.json');require(selection['status']=='LOCKED','INSUFFICIENT_FEINT_PROBES')
    root=Path(manifest['external_output']);require(not (root/'G3_registration.json').exists(),'G3 already started')
    lock=read(root/'selection_lock.json');require(sha(OUT/'D0_probe_selection.json')==lock['sha256'],'Selection modified')
    registration={'base':BASE,'selection_sha256':lock['sha256'],'script_sha256':sha(__file__),'analysis_sha256':sha(PROJECT/'scripts/qc_v07_fe_corner_dwell.py'),'total_wall_limit_s':1800,'marker':MARKER,'policy':'R1: remove only d/H for all CURVE primitives; retain acceleration/jerk/cruise caps and EXPLICIT_STOP; no scan.'};save(root/'G3_registration.json',registration)
    start=time.monotonic();deadline=start+1800;results=[];stop=None
    for probe in selection['probes']:
        item={'probe_id':probe['probe_id'],'probe_kind':probe['probe_kind'],'skeleton_id':probe['skeleton_id'],'agent_id':probe['agent_id'],'arms':{},'valid_pair':False};results.append(item)
        for arm in ('A','B'):
            remaining=deadline-time.monotonic()
            if remaining<=0:stop={'status':'TIME_LIMIT_STOP','probe_id':probe['probe_id'],'arm':arm};break
            destination=root/probe['probe_id']/arm;log=root/(probe['probe_id']+'_'+arm+'.log')
            with log.open('w',encoding='utf-8') as stream:
                proc=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',probe['probe_id'],'--arm',arm,'--out',str(destination)],cwd=PROJECT,stdout=stream,stderr=subprocess.STDOUT)
                try:code=proc.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    proc.kill();proc.wait();stop={'status':'TIME_LIMIT_STOP','probe_id':probe['probe_id'],'arm':arm,'partial_directory':str(destination)};break
            if code!=0:stop={'status':'EXPERIMENT_INVALID','probe_id':probe['probe_id'],'arm':arm,'worker_error':read(destination/'error.json') if (destination/'error.json').exists() else {'log':str(log)}};break
            actual=read(destination/'result.json');item['arms'][arm]=actual
            if arm=='A' and actual['baseline_reproduction']['status']!='BITWISE_IDENTICAL':stop={'status':'EXPERIMENT_INVALID','reason':'baseline_not_bitwise_identical','probe_id':probe['probe_id'],'details':actual['baseline_reproduction']};break
            if actual['physical_status']!='PASS':stop={'status':'EXPERIMENT_INVALID','reason':'physical_check_failed','probe_id':probe['probe_id'],'arm':arm,'checks':actual['physical_checks']};break
            if arm=='B':
                require([s['geometry_sha256'] for s in item['arms']['A']['tracker_snapshots']]==[s['geometry_sha256'] for s in actual['tracker_snapshots']],'A/B primitive geometry mismatch')
                item['valid_pair']=True
            print(json.dumps({'probe':probe['probe_id'],'arm':arm,'status':actual['physical_status'],'dwell':actual['dwell']['detected'],'tracking':actual['tracking']['classification'],'remaining_s':round(deadline-time.monotonic(),1)}),flush=True)
            save(root/'G3_progress.json',{'results':results,'elapsed_s':time.monotonic()-start})
        if stop:break
    completed={x['probe_id'] for x in results if x['valid_pair']};unfinished=[p['probe_id'] for p in selection['probes'] if p['probe_id'] not in completed]
    valid=[x for x in results if x['valid_pair']];changed=[x['probe_id'] for x in valid if x['probe_kind']=='feint' and x['arms']['A']['dwell']['detected']!=x['arms']['B']['dwell']['detected']]
    effect='EXPERIMENT_INVALID' if stop and stop['status']=='EXPERIMENT_INVALID' else 'CORNER_CAP_EFFECT_OBSERVED' if changed else 'CORNER_CAP_EFFECT_NOT_OBSERVED'
    b_results=[x for x in results if 'B' in x['arms']]
    tracking='TRACKING_ACCURACY_DEGRADED' if any(x['arms']['B']['tracking']['classification']=='TRACKING_ACCURACY_DEGRADED' for x in b_results) else 'TRACKING_ACCURACY_PRESERVED' if b_results else None
    verify_manifest()
    final={'status':effect,'technical_status':'D0_TECHNICAL_PASS' if not stop else 'INCOMPLETE' if stop['status']=='TIME_LIMIT_STOP' else 'EXPERIMENT_INVALID','tracking_classification':tracking,'tracking_scope':'Executed B arms only; not evaluable if none executed.','marker':MARKER,'valid_pairs':len(valid),'unfinished_probes':unfinished,'stop':stop,'changed_feint_probes':changed,'elapsed_wall_s':time.monotonic()-start,'selection_sha256':lock['sha256'],'results':results,'production_and_inputs_unchanged':True}
    save(root/'probe_results.json',final);save(OUT/'D0_probe_results.json',final)
    print(json.dumps({k:v for k,v in final.items() if k!='results'},indent=2),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--worker');p.add_argument('--arm',choices=['A','B']);p.add_argument('--out',type=Path);p.add_argument('--run',action='store_true');a=p.parse_args()
    if a.worker:worker(a.worker,a.arm,a.out)
    elif a.run:launch()
    else:p.error('choose --run or --worker')
if __name__=='__main__':main()
