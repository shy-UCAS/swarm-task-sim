"""D0 read-only input, saved M1 witness and static reference-cap audit."""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib,json,math,platform,subprocess,sys
from pathlib import Path
import numpy as np
import shapely
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from task_v07.execution import frozen_config,CONFIG_PATH,FROZEN_SHA256
from task_v07.criteria import load_criteria
from task_v07.detectors import dwell,work_mask,runs
from swarm_sim.fast_dynamics.route_tracker import RouteTracker,_curvature_bounds
from scripts.run_v07_s2_expansion import DEFAULT_DATA
from scripts.qc_v07_fe_speed_profile import group_map,V_LOW,V_MOVE,DT_S
BASE='81f804a969192790d89100528e3f802bc06446b1'
DATA=DEFAULT_DATA/'attempt_s15sim_20261017T071447Z'
OUT=PROJECT/'docs/v07/evidence/fe_int/corner_dwell_audit'
FILES=('truth_10hz.npz','frame_labels.npz','labels.json','task.json','public_scene.json')
class AuditError(RuntimeError):pass
def require(ok,message):
    if not ok:raise AuditError(message)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False,default=lambda x: x.item() if isinstance(x,np.generic) else (_ for _ in ()).throw(TypeError(type(x).__name__)))+'\n',encoding='utf-8',newline='\n')
def git(*args):return subprocess.check_output(['git',*args],cwd=PROJECT,text=True).strip()
def distribution(values):
    values=list(values)
    return {'count':len(values),'min':float(np.min(values)) if values else None,'p50':float(np.median(values)) if values else None,'max':float(np.max(values)) if values else None}
def source_hashes():
    names=git('ls-files','task_v07','swarm_sim','configs','tests').splitlines()
    names+=['scripts/qc_v07_fe_pre_freeze.py','scripts/qc_v07_fe_speed_profile.py','docs/v07/evidence/fe_int/quality_check/qc_report.json','docs/v07/evidence/fe_int/quality_check/qc_speed_report.json']
    return {n:sha(PROJECT/n) for n in names}
def validate_arrays(truth,frames,task,labels,label):
    require(all(k in truth for k in ('time_us','p','v','agent_ids')),label+': missing truth field')
    require(all(k in frames for k in ('time_us','agent_ids','region_assigned_target')),label+': missing frame field')
    t=truth['time_us'];ids=list(map(str,truth['agent_ids']));p=truth['p'];v=truth['v']
    require(t.ndim==1 and len(t)>0 and np.issubdtype(t.dtype,np.integer),label+': bad time')
    require(np.all(np.diff(t)==100000),label+': not 10 Hz')
    require(p.shape==v.shape==(len(t),len(ids),3),label+': bad truth dimensions')
    require(np.isfinite(p).all() and np.isfinite(v).all(),label+': nonfinite state')
    require(np.array_equal(t,frames['time_us']) and np.array_equal(truth['agent_ids'],frames['agent_ids']),label+': frame alignment mismatch')
    require(frames['region_assigned_target'].shape==(len(t),len(ids)),label+': bad target dimensions')
    require(len(set(ids))==len(ids) and ids==task['agent_ids'] and set(labels['agents'])==set(ids),label+': member mismatch')
    mapping=group_map(task)
    for a in ids:
        require('points_enu_m' in task['references'][a],label+': missing route')
        points=np.asarray(task['references'][a]['points_enu_m'])
        require(points.ndim==2 and points.shape[1]==3 and len(points)>=2 and np.isfinite(points).all(),label+': invalid route '+a)
        g=mapping[a][1]
        require(np.array_equal(points,np.asarray(g['references'][a]['points_enu_m'])),label+': group/reference mismatch '+a)
    return ids,mapping

def g0():
    require(not (OUT/'D0_source_manifest.json').exists(),'Refuse to overwrite G0 manifest')
    require(git('rev-parse','HEAD')==BASE and git('branch','--show-current')=='fe/corner-dwell-audit','Wrong base/branch')
    require(not git('diff','92068b9',BASE,'--','task_v07','swarm_sim','configs'),'Algorithm differs from P0+P1')
    require((platform.python_version(),np.__version__,shapely.__version__)==('3.12.3','2.5.3','2.0.7'),'Version mismatch')
    require(DEFAULT_DATA.resolve()==PROJECT.parents[1]/'SwarmData/v07_dataset' and DEFAULT_DATA.is_dir(),'Wrong DEFAULT_DATA')
    cfg=frozen_config();require(sha(CONFIG_PATH)==FROZEN_SHA256,'Frozen config changed')
    require(load_criteria()['detectors']['dwell']=={'window_s':20.0,'radius_m':30.0,'max_start_end_m':30.0},'Dwell rules changed')
    skeletons=sorted(p for p in DATA.iterdir() if p.is_dir() and p.name.startswith('family_'))
    require(len(skeletons)==30,'Expected 30 skeletons');episodes=[];unique={};count=0
    for s in skeletons:
        for mode in ('synchronous','sequential'):
            d=s/mode;label=s.name+'/'+mode
            require(all((d/f).is_file() for f in FILES),label+': missing input file')
            task=read(d/'task.json');labels=read(d/'labels.json')
            with np.load(d/'truth_10hz.npz',allow_pickle=False) as truth,np.load(d/'frame_labels.npz',allow_pickle=False) as frames:
                ids,mapping=validate_arrays(truth,frames,task,labels,label)
                row={'skeleton_id':s.name,'mode':mode,'directory':str(d),'agent_ids':ids,'frames':len(truth['time_us']),'base_intent':task['base_intent'],'family_id':task['family_id'],'sha256':{f:sha(d/f) for f in FILES}}
            for a in ids:
                key=s.name+'/'+a;h=digest(task['references'][a]['points_enu_m'])
                require(key not in unique or unique[key]==h,'Different paired-mode route: '+key);unique[key]=h
            count+=len(ids);episodes.append(row)
    require(len(episodes)==60 and count==480 and len(unique)==240,'Count mismatch')
    output=DEFAULT_DATA/('fe_corner_dwell_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));output.mkdir(exist_ok=False)
    result={'status':'PASS','base_commit':BASE,'branch':git('branch','--show-current'),'startup_clean_verified_before_new_script':True,'environment':{'python':platform.python_version(),'numpy':np.__version__,'shapely':shapely.__version__},'DEFAULT_DATA':str(DEFAULT_DATA.resolve()),'dataset':str(DATA),'external_output':str(output),'frozen_config_sha256':FROZEN_SHA256,'protected_source_sha256':source_hashes(),'skeletons':30,'episodes':episodes,'agent_episodes':count,'unique_route_members':len(unique),'route_sha256':unique,'dwell_criteria':load_criteria()['detectors']['dwell']}
    save(OUT/'D0_source_manifest.json',result);save(output/'source_manifest.json',result)
    print(json.dumps({k:result[k] for k in ('status','skeletons','agent_episodes','unique_route_members','external_output')}),flush=True)

def verify_manifest():
    m=read(OUT/'D0_source_manifest.json')
    require(m['status']=='PASS' and source_hashes()==m['protected_source_sha256'],'Protected source changed')
    for r in m['episodes']:
        for f,h in r['sha256'].items():require(sha(Path(r['directory'])/f)==h,'Input changed: '+r['directory']+'/'+f)
    return m

def witness_facts(xy,velocity,time_us,levels,saved):
    if not saved['detected']:return None
    b=saved['frame_index'];e=saved['confirm_frame_index']
    require(isinstance(b,int) and isinstance(e,int) and 0<=b<=e<len(time_us),'Invalid witness indices')
    require(e-b==200,'Witness is not closed 201-frame window')
    require(float(time_us[b]/1e6)==saved['t_s'] and float(time_us[e]/1e6)==saved['t_confirm'],'Witness timestamp mismatch')
    require(time_us[e]-time_us[b]==20000000,'Witness duration not 20 seconds')
    require(work_mask(levels)[b:e+1].all(),'Witness outside original work_mask')
    window=xy[b:e+1];speed=np.linalg.norm(velocity[b:e+1,:2],axis=1)
    displacement=float(np.linalg.norm(window[-1]-window[0]));radius=float(np.linalg.norm(window-window.mean(axis=0),axis=1).max())
    require(displacement<=30. and radius<=30.,'Saved positive violates original spatial dwell criteria')
    intervals=runs(speed<V_LOW);minimum=b+int(np.argmin(speed))
    union=saved['union_frame_intervals'];require(all(0<=x<=y<len(time_us) for x,y in union),'Bad union interval')
    require(abs(sum(float(time_us[y]-time_us[x])/1e6 for x,y in union)-saved['total_duration_s'])<=1e-9,'Union duration mismatch')
    return {'begin':b,'end':e,'frames':201,'duration_s':20.,'start_end_m':displacement,'radius_about_mean_m':radius,'path_length_m':float(np.linalg.norm(np.diff(window,axis=0),axis=1).sum()),'speed_min_m_s':float(speed.min()),'speed_p10_m_s':float(np.quantile(speed,.1)),'speed_p50_m_s':float(np.median(speed)),'speed_max_m_s':float(speed.max()),'low_speed_frame_share':float(np.mean(speed<V_LOW)),'minimum_frame':minimum,'minimum_time_s':float(time_us[minimum]/1e6),'position_xy_at_min':xy[minimum].tolist(),'low_intervals_closed':[[b+x,b+y-1] for x,y in intervals],'low_event_count':len(intervals),'low_total_duration_s':sum((y-x)*DT_S for x,y in intervals),'low_max_duration_s':max(((y-x)*DT_S for x,y in intervals),default=0.)}

def g1():
    require(not (OUT/'D0_m1_witness_analysis.json').exists(),'Refuse to overwrite G1')
    m=verify_manifest();rows=[]
    for ep in m['episodes']:
        root=Path(ep['directory']);task=read(root/'task.json');labels=read(root/'labels.json');groups=group_map(task)
        with np.load(root/'truth_10hz.npz',allow_pickle=False) as z,np.load(root/'frame_labels.npz',allow_pickle=False) as f:
            for i,a in enumerate(ep['agent_ids']):
                gid,g=groups[a];contribution=labels['agents'][a]['observed']['contribution'];saved=contribution['dwell']
                rows.append({'skeleton_id':ep['skeleton_id'],'mode':ep['mode'],'agent_id':a,'group_id':gid,'family_id':ep['family_id'],'base_intent':ep['base_intent'],'role':g['role'],'execution_method':g['execution_method'],'episode':str(root),'stored_dwell':saved,'observation_dwell':contribution.get('observation_dwell'),'witness':witness_facts(z['p'][:,i,:2],z['v'][:,i],z['time_us'],f['region_assigned_target'][:,i],saved)})
    rows.sort(key=lambda r:(r['skeleton_id'],r['mode'],r['agent_id']))
    samples=[]
    for name,predicate in [('feint_positive',lambda r:r['base_intent']=='feint' and r['stored_dwell']['detected']),('transit_negative',lambda r:r['execution_method']=='transit' and not r['stored_dwell']['detected']),('close_observation_positive',lambda r:r['execution_method']=='close_observation' and r['stored_dwell']['detected'])]:
        selected=[r for r in rows if predicate(r)][:2];require(len(selected)==2,'Missing detector validation samples: '+name)
        for r in selected:
            root=Path(r['episode'])
            with np.load(root/'truth_10hz.npz',allow_pickle=False) as z,np.load(root/'frame_labels.npz',allow_pickle=False) as f:
                i=list(z['agent_ids']).index(r['agent_id']);actual=dwell(z['p'][:,i,:2],z['time_us'],work_mask(f['region_assigned_target'][:,i]),load_criteria())
            require(all(actual[k]==r['stored_dwell'][k] for k in ('detected','frame_index','confirm_frame_index','union_frame_intervals')),'Detector recomputation mismatch '+str(r))
            samples.append({'category':name,'skeleton_id':r['skeleton_id'],'mode':r['mode'],'agent_id':r['agent_id'],'status':'EXACT_MATCH','recomputed':actual})
    result={'status':'PASS','criteria':m['dwell_criteria'],'diagnostic_speed_threshold_m_s':V_LOW,'window_closed_frames':201,'agent_episodes':len(rows),'positive_windows':sum(r['witness'] is not None for r in rows),'detector_validation_samples':samples,'members':rows}
    save(OUT/'D0_m1_witness_analysis.json',result);print(json.dumps({k:result[k] for k in ('status','agent_episodes','positive_windows')}),flush=True)

def corner_kind(angle):
    return 'STRAIGHT' if angle<=1e-8 else 'EXPLICIT_STOP' if angle>=math.radians(175) else 'CURVE'
def angle_bin(angle):
    kind=corner_kind(angle);degrees=math.degrees(angle)
    return kind if kind=='STRAIGHT' else 'EXPLICIT_STOP_175_PLUS' if kind=='EXPLICIT_STOP' else 'CURVE_LT_45' if degrees<45 else 'CURVE_45_TO_90' if degrees<90 else 'CURVE_90_TO_175'
def static_route(points,speed):
    cfg=frozen_config();rc=cfg.reference
    require(rc.corner_cut_max_m==.25 and rc.corner_leg_fraction==.1,'Unexpected reference cut parameters')
    horizon=cfg.controller.velocity_response_time_s+cfg.vehicle_profile.response_time_s
    require(abs(horizon-.575)<1e-12,'Unexpected response horizon')
    tracker=RouteTracker(points,speed,cfg.vehicle_profile,cfg.controller,rc,cfg.engine.step_us)
    points=np.asarray(points,float);legs=np.diff(points[:,:2],axis=0);lengths=np.linalg.norm(legs,axis=1);directions=legs/lengths[:,None]
    curves={q.node_index:q for q in tracker.primitives if q.control is not None};stops={q.node_index:q for q in tracker.primitives if q.stop}
    rows=[]
    for i in range(1,len(points)-1):
        angle=math.acos(float(np.clip(directions[i-1]@directions[i],-1,1)));kind=corner_kind(angle)
        row={'node_index':i,'point_xy':points[i,:2].tolist(),'angle_rad':angle,'angle_deg':math.degrees(angle),'kind':kind,'angle_bin':angle_bin(angle),'actual_curve_cap_m_s':None,'horizon_cap_m_s':None,'curve_length_m':None,'stop_exit_cap_m_s':None}
        if kind=='CURVE':
            require(i in curves,'Curve absent at raw node '+str(i));q=curves[i];d=min(rc.corner_cut_max_m,rc.corner_leg_fraction*lengths[i-1],rc.corner_leg_fraction*lengths[i]);k,ks=_curvature_bounds(q.derivatives)
            accel=math.sqrt(cfg.vehicle_profile.max_accel_xy_m_s2/(2*k));jerk=(cfg.vehicle_profile.max_jerk_m_s3/(2*(k*k+ks)))**(1/3)
            require(q.cap==min(tracker.speed,d/horizon,accel,jerk),'Static formula mismatch')
            require(q.cap<=d/horizon+1e-9 and d/horizon<=.435,'Horizon bound violated')
            row.update(cut_distance_m=float(d),response_horizon_s=horizon,horizon_cap_m_s=float(d/horizon),actual_curve_cap_m_s=q.cap,actual_cap_over_cruise=q.cap/speed,curve_length_m=q.length,curvature_bound=k,curvature_derivative_bound=ks,acceleration_cap_m_s=accel,jerk_cap_m_s=jerk,horizon_dominant=abs(q.cap-d/horizon)<=1e-12)
        elif kind=='EXPLICIT_STOP':
            require(i in stops and stops[i].exit_cap==0.,'Explicit stop missing or nonzero exit cap');row['stop_exit_cap_m_s']=0.
        else:require(i not in curves and i not in stops,'Straight node has bend or stop')
        rows.append(row)
    return rows

def match_window(xy,velocity,witness,vertices):
    if witness is None:return None
    b=witness['begin'];e=witness['end'];window=xy[b:e+1];low=np.linalg.norm(velocity[b:e+1,:2],axis=1)<V_LOW
    hits=[];low_hits=[];score=np.zeros(len(window),bool)
    for v in vertices:
        distances=np.linalg.norm(window-np.asarray(v['point_xy']),axis=1);minimum=float(distances.min())
        item={k:v[k] for k in ('node_index','angle_deg','kind','angle_bin','actual_curve_cap_m_s','horizon_cap_m_s')}
        if minimum<=3.:hits.append({**item,'minimum_distance_m':minimum})
        if low.any() and float(distances[low].min())<=3.:
            low_hits.append({**item,'minimum_distance_m':float(distances[low].min()),'matching_low_frames':int(np.sum(low&(distances<=3.)))})
            if v['kind']=='CURVE':score|=low&(distances<=3.)
    types={v['angle_bin'] for v in hits}
    return {'all_frame_matches':hits,'low_frame_matches':low_hits,'match_count':len(hits),'multiple_vertex_matches':len(hits)>1,'category':'NO_VERTEX_WITHIN_3M' if not hits else next(iter(types)) if len(types)==1 else 'MULTIPLE_TYPES','minimum_vertex_distance_m':min((h['minimum_distance_m'] for h in hits),default=None),'eligible_curve_low_frame_score':int(score.sum())}

def summarize_members(members):
    s1=[]
    for key in sorted({(r['role'],r['execution_method']) for r in members}):
        cells=[r for r in members if (r['role'],r['execution_method'])==key];positive=[r['vertex_attribution'] for r in cells if r['witness']]
        s1.append({'role':key[0],'execution_method':key[1],'agent_episodes':len(cells),'unique_route_members':len({(r['skeleton_id'],r['agent_id']) for r in cells}),'M1_positive':len(positive),'M1_positive_rate':len(positive)/len(cells),'ordinary_curve_matches':sum(any(v['kind']=='CURVE' for v in r['all_frame_matches']) for r in positive),'explicit_stop_matches':sum(any(v['kind']=='EXPLICIT_STOP' for v in r['all_frame_matches']) for r in positive),'no_vertex':sum(not r['all_frame_matches'] for r in positive),'multiple_types':sum(r['category']=='MULTIPLE_TYPES' for r in positive),'multiple_vertex_matches':sum(r['multiple_vertex_matches'] for r in positive)})
    return s1

def g2():
    require(not (OUT/'D0_corner_cap_analysis.json').exists(),'Refuse to overwrite G2')
    manifest=verify_manifest();g1r=read(OUT/'D0_m1_witness_analysis.json');require(g1r['status']=='PASS','G1 not passed')
    routes={};members=[]
    for index,ep in enumerate(manifest['episodes']):
        root=Path(ep['directory']);task=read(root/'task.json');groups=group_map(task)
        for a in ep['agent_ids']:
            key=ep['skeleton_id']+'/'+a
            if key not in routes:
                gid,g=groups[a];speed=g.get('cruise_speed_m_s',task.get('cruise_speed_m_s'));require(speed is not None,'Missing cruise speed')
                routes[key]={'skeleton_id':ep['skeleton_id'],'agent_id':a,'role':g['role'],'execution_method':g['execution_method'],'cruise_speed_m_s':speed,'cruise_source':'group.cruise_speed_m_s' if 'cruise_speed_m_s' in g else 'task.cruise_speed_m_s','vertices':static_route(task['references'][a]['points_enu_m'],speed)}
        with np.load(root/'truth_10hz.npz',allow_pickle=False) as z:
            for r in (r for r in g1r['members'] if r['skeleton_id']==ep['skeleton_id'] and r['mode']==ep['mode']):
                i=list(z['agent_ids']).index(r['agent_id']);members.append({**r,'vertex_attribution':match_window(z['p'][:,i,:2],z['v'][:,i],r['witness'],routes[r['skeleton_id']+'/'+r['agent_id']]['vertices'])})
        print(json.dumps({'g2_episodes':index+1,'routes':len(routes)}),flush=True)
    require(len(routes)==240 and len(members)==480,'G2 cardinality mismatch')
    s1=summarize_members(members)
    vertices=[v for r in routes.values() for v in r['vertices']];s2=[]
    for kind in sorted({v['angle_bin'] for v in vertices}):
        cells=[v for v in vertices if v['angle_bin']==kind];caps=[v['actual_curve_cap_m_s'] for v in cells if v['actual_curve_cap_m_s'] is not None];horizon=[v['horizon_cap_m_s'] for v in cells if v['horizon_cap_m_s'] is not None]
        s2.append({'angle_bin':kind,'vertices':len(cells),'curve_cap_m_s':distribution(caps),'horizon_cap_m_s':distribution(horizon),'curve_cap_below_1_fraction':sum(v<1. for v in caps)/len(caps) if caps else None,'explicit_stop_exit_cap_m_s':0. if kind=='EXPLICIT_STOP_175_PLUS' else None})
    result={'status':'PASS','unique_routes':len(routes),'agent_episodes':len(members),'reference_cap_not_actual_speed':True,'S1_role_method':s1,'S2_angle_bin':s2,'S3_positive_witnesses':[r for r in members if r['witness']],'routes':routes,'members':members,'attribution_limit':'Geometric proximity retains all node indices; no claim that nearest node is active primitive.'}
    save(OUT/'D0_corner_cap_analysis.json',result)
    select_probes(result,manifest)
    print(json.dumps({'status':'PASS','routes':len(routes),'vertices':len(vertices),'S1':s1,'S2':s2}),flush=True)

def select_probes(result,manifest):
    rows=[r for r in result['members'] if r['mode']=='synchronous'];eligible=[r for r in rows if r['base_intent']=='feint' and r['witness'] and r['vertex_attribution']['eligible_curve_low_frame_score']>0]
    eligible.sort(key=lambda r:(-r['vertex_attribution']['eligible_curve_low_frame_score'],r['skeleton_id'],r['agent_id']))
    chosen=[];families=set()
    for r in eligible:
        if r['family_id'] not in families and len(chosen)<3:chosen.append(r);families.add(r['family_id'])
    for r in eligible:
        if len(chosen)<3 and r not in chosen:chosen.append(r)
    status='LOCKED' if len(chosen)>=2 else 'INSUFFICIENT_FEINT_PROBES'
    selected=[{'probe_kind':'feint',**r} for r in chosen]
    for name,predicate,n in [('transit_control',lambda r:r['execution_method']=='transit' and not r['stored_dwell']['detected'],1),('observation_control',lambda r:r['execution_method']=='close_observation' and r['observation_dwell'] and r['observation_dwell']['detected'],1),('monitoring',lambda r:r['base_intent']=='monitoring',2)]:
        candidates=sorted((r for r in rows if predicate(r)),key=lambda r:(r['skeleton_id'],r['agent_id']));require(len(candidates)>=n,'Missing fixed control '+name)
        selected.extend({'probe_kind':name,**r} for r in candidates[:n])
    for index,r in enumerate(selected):
        r['probe_id']=f'probe_{index+1:02d}';r['input_sha256']=next(e['sha256'] for e in manifest['episodes'] if e['directory']==r['episode'])
        r['score']=r['vertex_attribution']['eligible_curve_low_frame_score'] if r['vertex_attribution'] else None
    selection={'status':status,'locked_before_AB':True,'selection_rule':'R2: synchronous; feint positive with low-speed frames <=3m from any CURVE, score descending then skeleton/agent; distinct families first. Controls and monitoring sorted by skeleton/agent. No post-outcome reselection.','eligible_feint_count':len(eligible),'probes':selected,'G3_total_wall_limit_s':1800,'execution_order':'feint pairs first, transit control, observation control, monitoring pairs last','production_base':BASE}
    require(not (OUT/'D0_probe_selection.json').exists(),'Selection already exists')
    save(OUT/'D0_probe_selection.json',selection);external=Path(manifest['external_output']);save(external/'D0_probe_selection.json',selection);save(external/'selection_lock.json',{'sha256':sha(OUT/'D0_probe_selection.json')})

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['g0','g1','g2'],required=True);args=parser.parse_args()
    {'g0':g0,'g1':g1,'g2':g2}[args.stage]()
if __name__=='__main__':main()
