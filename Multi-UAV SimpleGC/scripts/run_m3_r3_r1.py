"""R1 fixed probes and programmatic gate. Never patches production geometry."""
import argparse,copy,json,math,os,re,subprocess,sys,time,traceback
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PROJECT))
import numpy as np
from scripts.audit_m3_r3_r0 import read,digest,atomic,REPORT,DATA
from scripts.m3_r3_support import d0b_oracle
from task_v07.execution import execute,frozen_config
from swarm_sim.fast_dynamics.route_tracker import RouteTracker
from swarm_sim.fast_dynamics.reference_r3 import candidate_config

PLAN=REPORT/'R0_validation_plan_amended.json'

def code_hashes():
    files=[]
    for directory in ('swarm_sim','task_v07','configs','scripts','tests'):
        files.extend(p for p in (PROJECT/directory).rglob('*') if p.is_file() and p.suffix in ('.py','.json') and '__pycache__' not in p.parts)
    return {str(p):digest(p) for p in sorted(files)}

def capture(group,agent,version):
    captured=[];code=RouteTracker.__init__.__code__;previous=sys.gettrace()
    def trace(frame,event,arg):
        if event=='call' and frame.f_code is code:
            frame.f_trace_lines=False;return on_return
    def on_return(frame,event,arg):
        if event=='return':captured.append(frame.f_locals['self'])
        return on_return
    try:
        sys.settrace(trace)
        run=execute(group,{a:0. for a in group['members']},only_agent=agent,reference_version=version)
    finally:sys.settrace(previous)
    oracle=d0b_oracle();points=np.asarray(group['references'][agent]['points_enu_m'])
    intermediate=group['references'][agent].get('intermediate_dwell')
    if intermediate:
        n=intermediate['waypoint_index'];assert len(captured)==3
        assert np.array_equal(captured[0].points,points) and not captured[0].witnesses
        assert np.array_equal(captured[1].points,points[:n+1]) and np.array_equal(captured[2].points,points[n:])
        active=[(0,captured[1]),(n,captured[2])]
    else:
        assert len(captured)==1 and np.array_equal(captured[0].points,points);active=[(0,captured[0])]
    snapshots=[];witnesses=[]
    cfg=frozen_config()
    for offset,t in active:
        original=RouteTracker(t.points,t.speed,cfg.vehicle_profile,cfg.controller,cfg.reference,cfg.engine.step_us)
        geometry=oracle.validate_geometry(t,original) if version=='r3' else dict(status='PASS')
        snapshots.append(dict(original_node_offset=offset,geometry=oracle.d0.tracker_geometry(t),diagnostics=t.diagnostics,
            curves=oracle.curve_facts(t,'B2' if version=='r3' else 'A',offset),B2_geometry_check=geometry,
            primitive_caps=[dict(cap=q.cap if math.isfinite(q.cap) else None,exit_cap=q.exit_cap) for q in t.primitives]))
        for e in t.witnesses:
            if offset and e['node_index']==0:continue
            witnesses.append({**e,'node_index':offset+e['node_index']})
    return run,snapshots,witnesses

def worker(probe_id,version,out):
    plan=read(PLAN);probe=next(p for p in plan['R1']['probes'] if p['probe_id']==probe_id)
    out.mkdir(parents=True,exist_ok=False)
    try:
        task=read(Path(probe['episode'])/'task.json');group=copy.deepcopy(task['group_skeletons'][probe['group_id']])
        run,snapshots,witnesses=capture(group,probe['agent_id'],version)
        oracle=d0b_oracle();metrics,distances,segments,scene_frames=oracle.metrics(run,group,probe['agent_id'],
            read(Path(probe['episode'])/'public_scene.json'),snapshots,witnesses,probe)
        arm='A' if version=='r2' else 'B2';history=Path(probe['historical_arms'][arm]);old=read(history/'result.json')
        arrays={k:np.asarray(run[k]) for k in ('time_us','p','v','a','agent_ids','execution_status')}
        with np.load(history/'run.npz',allow_pickle=False) as saved:
            exact={k:arrays[k].shape==saved[k].shape and arrays[k].dtype==saved[k].dtype and arrays[k].tobytes()==saved[k].tobytes() for k in arrays}
        np.savez_compressed(out/'run.npz',**arrays)
        np.savez_compressed(out/'tracking_frames.npz',time_us=run['time_us'],distance_m=distances,nearest_segment_index=segments)
        checks=dict(bitwise_arrays=all(exact.values()),physical=metrics['physical_status']=='PASS',
            all_ordered_nodes=metrics['tracking']['all_waypoints_witnessed'],no_scene_violations=not metrics['scene']['violation'],
            witness_evidence_exact=metrics['original_node_witnesses']==old['original_node_witnesses'],
            dwell_exact=metrics['dwell']==old['dwell'],observation_dwell_exact=metrics['observation_dwell']==old['observation_dwell'],
            geometry_pass=all(s['B2_geometry_check']['status']=='PASS' for s in snapshots))
        result=dict(status='PASS' if all(checks.values()) else 'FAIL',probe_id=probe_id,version=version,checks=checks,array_equality=exact,
            metrics=metrics,historical_result=str(history/'result.json'),raw_sha256={f:digest(out/f) for f in ('run.npz','tracking_frames.npz')})
        atomic(out/'result.json',result)
        return 0 if result['status']=='PASS' else 2
    except BaseException as exc:
        atomic(out/'error.json',dict(status='P0_STOP',error=repr(exc),traceback=traceback.format_exc()));raise

def run_processes(jobs,root,deadline,workers=4):
    pending=list(jobs);active={};done=[];stop=None
    while pending or active:
        while pending and len(active)<workers and not stop:
            name,command,dest=pending.pop(0);stream=(root/(name+'.log')).open('x',encoding='utf-8')
            proc=subprocess.Popen(command,cwd=PROJECT,stdout=stream,stderr=subprocess.STDOUT)
            active[name]=(proc,stream,dest)
        for name,(proc,stream,dest) in list(active.items()):
            code=proc.poll()
            if code is None:continue
            stream.close();del active[name]
            if code!=0:
                stop=dict(status='FAIL',job=name,returncode=code,error=read(dest/'error.json') if (dest/'error.json').exists() else None)
                break
            done.append(name);print(json.dumps(dict(done=len(done),total=len(jobs),job=name)),flush=True)
        if time.monotonic()>=deadline:stop=dict(status='TIME_LIMIT_STOP')
        if stop:
            for proc,stream,dest in active.values():proc.kill();proc.wait();stream.close()
            break
        time.sleep(.25)
    return dict(completed=done,stop=stop,unfinished=[name for name,_,_ in jobs if name not in done])

def launch(out,unit_log=None):
    if out.exists():raise ValueError('new attempt required')
    gate=read(REPORT/'R0_revalidated_gate.json');assert gate['status']=='PASS' and digest(PLAN)==gate['input_sha256']
    plan=read(PLAN);out.mkdir(parents=True,exist_ok=False);start=time.monotonic();deadline=start+plan['R1']['wall_limit_s']
    hashes=code_hashes()
    atomic(out/'registration.json',dict(plan_sha256=digest(PLAN),code_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT,text=True).strip(),source_sha256=hashes,
        probes=plan['R1']['probes'],wall_limit_s=plan['R1']['wall_limit_s']))
    # Revalidate immutable plan inputs, except the two production files explicitly changed by R1.
    mutable={str(PROJECT/'swarm_sim/fast_dynamics/route_tracker.py'),str(PROJECT/'swarm_sim/fast_dynamics/contracts.py')}
    for item in plan['input_files']:
        if item['path'] not in mutable:assert digest(item['path'])==item['sha256'],item['path']
    if unit_log is None:
        env=dict(os.environ);env['PYTHONPATH']=str(PROJECT)+os.pathsep+str(PROJECT/'tests')
        with (out/'unit_tests.txt').open('x',encoding='utf-8') as stream:
            proc=subprocess.run([sys.executable,'-B','-m','unittest','-v',*plan['R1']['unit_modules']],cwd=PROJECT,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=max(1,deadline-time.monotonic()))
        test_code=proc.returncode
    else:
        # A preflight is reusable only under the same registered production/test hashes.
        raise ValueError('preflight reuse disabled; full registered tests required')
    text=(out/'unit_tests.txt').read_text();count=re.search(r'Ran (\d+) tests?',text)
    tests_ok=test_code==0 and count is not None and '\nOK' in text and 'skipped=' not in text
    batch=dict(completed=[],unfinished=[p['probe_id']+'/'+v for p in plan['R1']['probes'] for v in ('r2','r3')],stop=None)
    if tests_ok:
        jobs=[(p['probe_id']+'_'+v,[sys.executable,'-B',str(Path(__file__).resolve()),'--worker',p['probe_id'],'--version',v,'--output',str(out/p['probe_id']/v)],out/p['probe_id']/v)
              for p in plan['R1']['probes'] for v in ('r2','r3')]
        batch=run_processes(jobs,out,deadline)
    results=[read(p) for p in sorted(out.glob('probe_*/r*/result.json'))]
    checks=dict(all_registered_tests=tests_ok,all_fourteen_replays=len(results)==14,
        all_replay_checks=len(results)==14 and all(r['status']=='PASS' for r in results),source_hashes_unchanged=hashes==code_hashes(),
        r2_config_unchanged=digest(PROJECT/'configs/fast_dynamics/m3_r2_20261013_v1.json')=='94822513045c434dc2f713070728f1f99d18bcbea3933f8f092b85c5e4d78193')
    status='PASS' if all(checks.values()) else batch['stop']['status'] if batch['stop'] else 'FAIL'
    summary=dict(stage='R1',status=status,input_sha256=digest(PLAN),code_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT,text=True).strip(),
        required_checks=checks,metrics=dict(unit_tests=int(count[1]) if count else 0, failures=int(re.search(r'failures=(\d+)',text)[1]) if re.search(r'failures=(\d+)',text) else 0, errors=int(re.search(r'errors=(\d+)',text)[1]) if re.search(r'errors=(\d+)',text) else 0, replays=len(results),elapsed_wall_s=time.monotonic()-start),
        evidence_paths=[str(out),str(out/'unit_tests.txt'),str(out/'registration.json')],next_stage='R2' if status=='PASS' else None,unfinished=batch['unfinished'],stop=batch['stop'])
    atomic(out/'summary.json',summary);atomic(REPORT/'R1/gate.json',summary);atomic(REPORT/'R1_gate.json',summary)
    state=read(REPORT/'pipeline_state.json');state.update(status=status,current_stage='R1',next_stage=summary['next_stage'])
    if status=='PASS':state['last_pass_stage']='R1'
    state['stages']['R1']=dict(status=status,executed=True,gate=str(REPORT/'R1/gate.json'))
    if status!='PASS':
        for later in ('R2','R3','R4'):state['stages'][later]=dict(status='BLOCKED',executed=False,reason='R1_NOT_PASS')
    atomic(REPORT/'pipeline_state.json',state);print(json.dumps(summary),flush=True)
    return 0 if status=='PASS' else 2

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker');p.add_argument('--version',choices=['r2','r3']);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    raise SystemExit(worker(a.worker,a.version,a.output) if a.worker else launch(a.output))
