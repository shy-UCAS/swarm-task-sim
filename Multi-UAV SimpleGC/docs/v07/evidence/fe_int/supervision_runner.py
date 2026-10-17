import hashlib,json,math,os,pathlib,subprocess,sys,time,traceback
import psutil
p=pathlib.Path.cwd(); data=p.parent.parent/'SwarmData/v07_dataset'; selection=data/'s15_sim_pilot_selection.json'
started=time.monotonic(); before={x.name for x in data.glob('attempt_s15sim_*')}; attempt=None; seen={}; findings=[]; checks=0
logdir=data/('fe_int_supervision_'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())); logdir.mkdir(exist_ok=False)
def save(name,obj):
    dest=logdir/name; tmp=dest.with_suffix('.tmp'); tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(dest)
def read(path): return json.loads(path.read_text(encoding='utf-8'))
def fingerprints():
    paths=[]
    for folder in ['task_v07','swarm_sim','scripts','tests','configs']:
        paths.extend(x for x in (p/folder).rglob('*') if x.is_file() and x.suffix in ['.py','.json','.yaml','.yml'])
    return {x.relative_to(p).as_posix():hashlib.sha256(x.read_bytes()).hexdigest() for x in paths}
def kill_owned(proc):
    try:
        parent=psutil.Process(proc.pid); children=parent.children(recursive=True)
        for child in reversed(children):
            try: child.terminate()
            except psutil.NoSuchProcess: pass
        parent.terminate(); psutil.wait_procs(children+[parent],timeout=10)
    except psutil.NoSuchProcess: pass
    proc.wait(timeout=20)
def scan():
    global checks
    checks+=1
    current=fingerprints()
    if current!=baseline: return {'reason':'source_fingerprint_changed','paths':sorted(k for k in set(current)|set(baseline) if current.get(k)!=baseline.get(k))}
    if attempt is None:return None
    for f in attempt.glob('*/geometry_*/timing_selection.json'):
        signature=(f.stat().st_size,f.stat().st_mtime_ns)
        if seen.get(str(f))==signature:continue
        try: timing=read(f); sk=read(f.parent/'skeleton.json')
        except (json.JSONDecodeError,PermissionError,FileNotFoundError):continue
        seen[str(f)]=signature
        if timing.get('status')!='rejected':continue
        groups=sk['group_skeletons']; monitoring=any(g.get('base_intent')=='monitoring' or g.get('execution_method')=='monitoring' for g in groups.values())
        owner={a:gid for gid,g in groups.items() for a in g['members']}
        refs={a:r for g in groups.values() for a,r in g['references'].items()}
        for mode in timing['failed_versions']:
            for draw in timing['versions'][mode]['attempts']:
                if draw['status']!='rejected':continue
                a,b=draw['closest_pair']['agents']; ea=refs[a]['endpoint_enu_m']; eb=refs[b]['endpoint_enu_m']; distance=math.dist(ea,eb)
                entry=dict(skeleton_id=sk['skeleton_id'],geometry_round=f.parent.name,mode=mode,draw=draw['draw'],agents=[a,b],groups=[owner[a],owner[b]],same_group=owner[a]==owner[b],monitoring_present=monitoring,endpoint_distance_m=distance,endpoint_xy_distance_m=math.dist(ea[:2],eb[:2]),minimum_spacing_m=draw['minimum_m'],source=str(f))
                findings.append(entry)
                if monitoring and distance<2:return dict(reason='monitoring_timing_conflict_endpoints_below_2m',**entry)
    for f in attempt.glob('*/*/independent_exact_audit.json'):
        try: audit=read(f)
        except (json.JSONDecodeError,PermissionError,FileNotFoundError):continue
        if audit.get('status')!='PASS':return dict(reason='independent_audit_failed',path=str(f),audit=audit)
    result=attempt/'run_result.json'
    if result.exists():
        try:r=read(result)
        except (json.JSONDecodeError,PermissionError):return None
        if r['status'] not in ['completed','TIME_LIMIT_STOP']:return dict(reason='pilot_hard_stop',result=r)
        if any(isinstance(v.get('strict_pair'),str) and v['strict_pair'].startswith('P0:') for v in r.get('per_skeleton',{}).values()):return dict(reason='pair_contract_error',result=r)
    return None
baseline=fingerprints()
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=p).strip()
assert len(read(selection)['skeletons'])==30
save('source_fingerprints_before.json',baseline)
command=[sys.executable,'-B','scripts/run_v07_s15_sim_pilot.py','--skeletons-file',str(selection),'--wall-limit-s','4500']
save('registration.json',dict(command=command,cwd=str(p),scan_interval_s=5,logdir=str(logdir),source_scope=['task_v07','swarm_sim','scripts','tests','configs'],entry_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=p,text=True).strip()))
print('SUPERVISION '+str(logdir),flush=True)
stop=None; last_print=0
with (logdir/'pilot_console.txt').open('w',encoding='utf-8') as log:
    proc=subprocess.Popen(command,cwd=p,stdout=log,stderr=subprocess.STDOUT,env=os.environ.copy())
    try:
        while True:
            if attempt is None:
                found=[x for x in data.glob('attempt_s15sim_*') if x.name not in before and (x/'registration.json').exists()]
                if len(found)>1:raise RuntimeError('Multiple new attempts detected')
                if found:attempt=found[0];print('ATTEMPT '+str(attempt),flush=True)
            stop=scan()
            if stop:
                kill_owned(proc);break
            elapsed=time.monotonic()-started
            if elapsed-last_print>=55:
                progress=read(attempt/'progress.json') if attempt and (attempt/'progress.json').exists() else {}
                state=dict(elapsed_s=round(elapsed,1),attempt=str(attempt),completed=len(progress.get('completed',[])),pending=len(progress.get('pending',[])),remaining_s=progress.get('remaining_s'),source_checks=checks,timing_conflict_draws=len(findings))
                save('progress.json',state); print(json.dumps(state),flush=True);last_print=elapsed
            if proc.poll() is not None:break
            if elapsed>4650:raise RuntimeError('Pilot did not terminate after wall cap plus shutdown allowance')
            time.sleep(5)
    except BaseException as exc:
        stop=dict(reason='supervisor_exception',exception=str(exc),traceback=traceback.format_exc());kill_owned(proc)
    rc=proc.wait()
final=fingerprints();save('source_fingerprints_after.json',final);save('timing_conflicts.json',findings)
summary=dict(status='HARD_STOP' if stop else 'FINISHED',stop=stop,attempt=str(attempt) if attempt else None,pilot_returncode=rc,source_stable=final==baseline,source_checks=checks,elapsed_s=time.monotonic()-started,logdir=str(logdir))
save('supervision_result.json',summary);print(json.dumps(summary),flush=True)
sys.exit(2 if stop else rc)
