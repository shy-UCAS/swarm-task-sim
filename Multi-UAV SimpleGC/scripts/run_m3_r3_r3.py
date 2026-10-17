"""R3 candidate-only P2 integration, exact baseline regression and default-r2 replay."""
import argparse,ast,copy,json,os,subprocess,sys,time,traceback
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PROJECT))
import numpy as np
from scripts.audit_m3_r3_r0 import read,digest,atomic,REPORT,DATA,BASE,CONFIG_SHA
from scripts.run_m3_r3_r1 import PLAN,code_hashes
from scripts.revalidate_m3_r3_r1 import export_baseline,tests,regression,normalized,validate_inputs,array_diff
from swarm_sim.fast_dynamics.reference_r3 import CONFIG_SHA256
from scripts.m3_r3_g5a import load_amendment,regression_g5a
P2='fa7518b7fa850771c9d863b23d8893b27a343d5f'
CONSTRUCTION='task_v07/unified/construction.py'


def git(*args):return subprocess.check_output(['git',*args],cwd=PROJECT,text=True).strip()


def function_scope(old,new):
    a=ast.parse(old);b=ast.parse(new)
    def split(tree):
        selected=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='ingress_issues']
        if len(selected)!=1:raise ValueError('ingress_issues identity is not unique')
        tree.body.remove(selected[0]);return ast.dump(tree),ast.dump(selected[0])
    x,fx=split(a);y,fy=split(b)
    return dict(outside_function_unchanged=x==y,function_changed=fx!=fy)


def default_worker(pid,out):
    from task_v07.execution import execute
    out.mkdir(parents=True,exist_ok=False)
    try:
        probe=next(p for p in read(PLAN)['R1']['probes'] if p['probe_id']==pid)
        group=copy.deepcopy(read(Path(probe['episode'])/'task.json')['group_skeletons'][probe['group_id']])
        run=execute(group,{a:0. for a in group['members']},only_agent=probe['agent_id'])
        arrays={k:np.asarray(run[k]) for k in ('time_us','p','v','a','agent_ids','execution_status')}
        history=Path(probe['historical_arms']['A'])/'run.npz'
        with np.load(history,allow_pickle=False) as saved:diffs={k:array_diff(v,saved[k]) for k,v in arrays.items()}
        np.savez_compressed(out/'run.npz',**arrays)
        checks=dict(default_config_r2=run['config_sha256']==CONFIG_SHA,bitwise_historical=not any(diffs.values()))
        result=dict(status='PASS' if all(checks.values()) else 'FAIL',probe_id=pid,checks=checks,first_differences=diffs,historical_sha256=digest(history),new_sha256=digest(out/'run.npz'))
    except Exception as exc:result=dict(status='BLOCKED',reason=repr(exc),traceback=traceback.format_exc())
    atomic(out/'result.json',result);return 0 if result['status']=='PASS' else 2


def launch(out):
    assert read(REPORT/'R2_gate.json')['status']=='PASS'
    assert git('branch','--show-current')=='fe/m3-r3-p2-candidate'
    assert not git('status','--porcelain')
    assert not out.exists()
    plan=read(PLAN);validate_inputs(plan)
    out.mkdir();ev=REPORT/'R3'/out.name;ev.mkdir(parents=True,exist_ok=False)
    start=time.monotonic();deadline=start+plan['R3']['wall_limit_s'];before=git('rev-parse','HEAD')
    initial=code_hashes();hashes=initial;stop=None;reg=None;replays=[];checks={};scope=None
    locks={f['path']:digest(f['path']) for f in plan['input_files']}
    atomic(out/'registration.json',dict(stage='R3',parent_commit=before,P2=P2,source_sha256=initial,input_plan_sha256=digest(PLAN),G2a_sha256=digest(REPORT/'gate_audit_G2a.json'),G5a_sha256=digest(REPORT/'G5a_gate_amendment.json'),R2_gate_sha256=digest(REPORT/'R2_gate.json'),wall_limit_s=plan['R3']['wall_limit_s'],modules=plan['R3']['regression_modules'],probe_ids=[p['probe_id'] for p in plan['R1']['probes']]))
    dry=dict(stage='R3',status='INCOMPLETE',checks={})
    try:
        amendment=load_amendment();baseline=read(amendment['baseline_results_path'])
        modules=plan['R3']['regression_modules'];known=amendment['known_signatures'];roots=amendment['checkout_roots']
        atomic(out/'baseline_results.json',baseline)
        dry=regression_g5a(baseline,baseline,known,roots)
        dry.update(stage='R3',baseline_commit=BASE,baseline_source=amendment['baseline_results_path'],G5a_sha256=digest(REPORT/'G5a_gate_amendment.json'),reuse='Verified saved full 476-test FE baseline; no tests omitted',r2_replay_evidence=str(REPORT/'R1_revalidated_gate_attempt05.json'))
        atomic(ev/'baseline_gate_dryrun.json',dry)
        atomic(REPORT/'R3/baseline_gate_dryrun_G5a.json',dry)
        print(json.dumps(dict(stage='R3_baseline_G5a',status=dry['status'],tests=baseline['count'],known=dry['baseline_known_failure'])),flush=True)
        if dry['status']!='PASS':stop=dict(status='FAIL',reason='BASELINE_G5a_SIGNATURE_MISMATCH',details=dry)
        if not stop:
            with (out/'P2_merge.txt').open('x',encoding='utf-8') as f:
                merged=subprocess.run(['git','merge','--no-ff','-m','# merge(m3-r3): 集成已验收 P2 到候选分支',P2],cwd=PROJECT,stdout=f,stderr=subprocess.STDOUT,timeout=max(1,deadline-time.monotonic()))
            if merged.returncode:stop=dict(status='BLOCKED',reason='P2_MERGE_REJECTED_OR_CONFLICT',output=(out/'P2_merge.txt').read_text(encoding='utf-8'))
        if not stop:
            changed=git('diff','--name-only',before,'HEAD','--','task_v07','swarm_sim','configs').splitlines()
            old=git('show',before+':Multi-UAV SimpleGC/'+CONSTRUCTION)
            current=(PROJECT/CONSTRUCTION).read_text(encoding='utf-8')
            accepted=git('show',P2+':Multi-UAV SimpleGC/'+CONSTRUCTION)
            scope=function_scope(old,current);scope.update(production_changed_files=changed,only_allowed_file=changed==['Multi-UAV SimpleGC/'+CONSTRUCTION],accepted_P2_file=current.strip()==accepted.strip())
            atomic(ev/'P2_scope.json',scope)
            checks['P2_scope']=all(scope[k] for k in ('outside_function_unchanged','function_changed','only_allowed_file','accepted_P2_file'))
            if not checks['P2_scope']:stop=dict(status='FAIL',reason='P2_SCOPE',details=scope)
            hashes=code_hashes()
            freeze=dict(status='CANDIDATE_ONLY',formal_freeze=False,merge_commit=git('rev-parse','HEAD'),P2=P2,r2_sha256=CONFIG_SHA,r3_sha256=CONFIG_SHA256,source_sha256=hashes,R2_gate_sha256=digest(REPORT/'R2_gate.json'),input_plan_sha256=digest(PLAN))
            atomic(ev/'candidate_freeze_record.json',freeze);atomic(out/'post_merge_source.json',hashes)
        if not stop:
            candidate=tests(PROJECT,modules,out/'integration_tests.txt',deadline)
            atomic(out/'integration_results.json',candidate)
            reg=regression_g5a(candidate,baseline,known,roots);reg['name']='R3_REGRESSION_DELTA_ZERO_G5a';atomic(ev/'regression_delta.json',reg)
            extras=sorted(p.stem for p in (PROJECT/'tests').glob('test_m3_r3*.py') if p.stem not in modules)
            added=tests(PROJECT,extras,out/'harness_tests.txt',deadline);atomic(ev/'harness_tests.json',added)
            checks.update(integration_regression=reg['status']=='PASS',harness_tests=added['returncode']==0 and all(v=='ok' for v in added['outcomes'].values()))
            print(json.dumps(dict(stage='R3_tests',executed=reg['executed'],passed=reg['passed'],known=reg['baseline_known_failure'],new_failures=reg['new_failure_count'])),flush=True)
            if not all(checks.values()):stop=dict(status='FAIL',reason='INTEGRATION_REGRESSION_OR_HARNESS_TEST')
        if not stop:
            for probe in plan['R1']['probes']:
                pid=probe['probe_id'];dest=out/pid
                with (out/(pid+'.txt')).open('x',encoding='utf-8') as f:
                    process=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',pid,'--output',str(dest)],cwd=PROJECT,stdout=f,stderr=subprocess.STDOUT,timeout=max(1,deadline-time.monotonic()))
                result=read(dest/'result.json');replays.append(result)
                print(json.dumps(dict(stage='R3_default_r2',probe_id=pid,status=result['status'])),flush=True)
                if process.returncode:stop=dict(status=result['status'],reason='DEFAULT_R2_REPLAY',details=result);break
    except subprocess.TimeoutExpired:stop=dict(status='TIME_LIMIT_STOP',reason='R3 7200s budget')
    except Exception as exc:stop=dict(status='BLOCKED',reason=repr(exc),traceback=traceback.format_exc())
    if not (ev/'baseline_gate_dryrun.json').exists():atomic(ev/'baseline_gate_dryrun.json',dry)
    changed_inputs=[p for p,h in locks.items() if digest(p)!=h and p!=str(PROJECT/CONSTRUCTION)]
    checks.update(default_r2_replay=len(replays)==7 and all(r['status']=='PASS' for r in replays),source_unchanged=code_hashes()==hashes,input_hashes_unchanged=not changed_inputs,r2_config_unchanged=digest(PROJECT/'configs/fast_dynamics/m3_r2_20261013_v1.json')==CONFIG_SHA,r3_config_unchanged=digest(PROJECT/'configs/fast_dynamics/m3_r3_candidate_v1.json')==CONFIG_SHA256)
    status='PASS' if all(checks.values()) and not stop else (stop or {}).get('status','FAIL')
    result=dict(stage='R3',status=status,required_checks=checks,stop=stop,regression=reg,default_r2_replays=replays,changed_inputs=changed_inputs,elapsed_wall_s=time.monotonic()-start,evidence_paths=[str(out),str(ev)],code_commit=git('rev-parse','HEAD'),next_stage='R4' if status=='PASS' else None)
    atomic(out/'gate.json',result);atomic(ev/'gate.json',result);atomic(REPORT/'R3_gate.json',result)
    state=read(REPORT/'pipeline_state.json');atomic(ev/'previous_pipeline_state.json',state)
    state.update(status=status,current_stage='R3',next_stage=result['next_stage']);state['stages']['R3']=dict(status=status,executed=True,gate=str(ev/'gate.json'))
    if status=='PASS':state['last_pass_stage']='R3'
    else:state['stages']['R4']=dict(status='BLOCKED',executed=False,reason='R3_NOT_PASS')
    atomic(REPORT/'pipeline_state.json',state)
    print(json.dumps(dict(stage='R3',status=status,stop=stop,elapsed_s=result['elapsed_wall_s'])),flush=True)
    return 0 if status=='PASS' else 2

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--worker');args=p.parse_args()
    raise SystemExit(default_worker(args.worker,args.output) if args.worker else launch(args.output))
