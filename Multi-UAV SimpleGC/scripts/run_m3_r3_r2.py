"""R2 fixed tuning-only fastsim run; original metrics/tiers and G-2a diagnostics."""
import argparse,copy,json,os,subprocess,sys,time,traceback
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PROJECT))
from scripts.audit_m3_r3_r0 import DATA,REPORT,BASELINE,TUNING,read,digest,atomic,CONFIG_SHA
from scripts.run_m3_r3_r1 import PLAN,code_hashes
from scripts.revalidate_m3_r3_r1 import validate_inputs
from scripts.tune_fast_dynamics_m3 import candidate_job,tiers,measurement_changes
from scripts.m3_r3_gates import evaluate,values
from swarm_sim.fast_dynamics.calibration import aggregate_pairs
from swarm_sim.fast_dynamics.reference_r3 import candidate_config,CONFIG_SHA256

BASE_PAIRS=DATA/'fast_dynamics/m3/m3_r3_r0_revalidate01/baseline_pairs.json'


def task_metrics(row):
    duration=row['duration_relative_error'];observe=row['phase_duration_relative_error'].get('p01_observe')
    turn=row['turn_minimum_speed_m_s']
    return dict(total_duration_abs_relative_median=None if duration is None else abs(duration),
        total_duration_abs_relative_p95=None if duration is None else abs(duration),
        observe_duration_abs_relative_median=None if observe is None else abs(observe),
        turn_min_speed_abs_difference_median=None if None in turn else abs(turn[1]-turn[0]),
        lateral_task_p95_median_m=row['lateral_m']['p95'])


def numerical_report(pairs,baseline):
    base={r['mission_id']:r for r in baseline};data={k:[] for k in values(aggregate_pairs(baseline))}
    for row in pairs:
        a=task_metrics(base[row['mission_id']]);b=task_metrics(row)
        for k in data:
            data[k].append(dict(mission_id=row['mission_id'],flight_pattern=row['flight_pattern'],r2=a[k],r3=b[k],delta=None if a[k] is None or b[k] is None else b[k]-a[k]))
    result={}
    for k,items in data.items():
        worse=sorted((r for r in items if r['delta'] is not None and r['delta']>1e-9),key=lambda r:(-r['delta'],r['mission_id']))
        result[k]=dict(disposition='DIAGNOSTIC_ONLY_G3_G2a',worsened_count=len(worse),worst10=worse[:10],all_tasks=items)
    return result


def gate_from_pairs(pairs,baseline):
    # Same original M3 hard contract, reference identities and applicability.
    # Never evaluate the five numerical nonregression diagnostics as hard gates.
    answer=evaluate(pairs,baseline,nonregression=False)
    answer['numerical_diagnostics']=numerical_report(pairs,baseline)
    answer['expected_tasks']=len(baseline);answer['completed_pairs']=len(pairs)
    return answer


def worker(name,out):
    registration=read(out/'registration.json')
    assert name in registration['mission_ids']
    assert registration['source_sha256']==code_hashes()
    assert digest(PLAN)==registration['input_plan_sha256']
    task=BASELINE/name/'input_task.json';assert digest(task)==registration['task_sha256'][name]
    result=candidate_job((name,str(BASELINE),str(out/'runs'),candidate_config().to_dict()))
    if result['status']=='COMPLETE':
        dest=out/'runs'/name
        old=TUNING/'config_020_full'/name/'run/analysis/labels.json'
        atomic(dest/'frozen_r2_label_changes.json',measurement_changes(read(old),read(dest/'run/analysis/labels.json')))
    return 0 if result['status']=='COMPLETE' else 2


def execute_batch(names,out,deadline,hashes,workers=4):
    pending=list(names);active={};completed=[];stop=None;last_hash=0
    try:
        while pending or active:
            now=time.monotonic()
            if now>=deadline:stop=dict(status='TIME_LIMIT_STOP',reason='R2 28800s budget');break
            if now-last_hash>=5:
                if code_hashes()!=hashes:stop=dict(status='FAIL',reason='SOURCE_FINGERPRINT_CHANGED');break
                last_hash=now
            while pending and len(active)<workers:
                name=pending.pop(0);log=(out/'logs'/f'{name}.txt').open('x',encoding='utf-8')
                proc=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',name,'--output',str(out)],cwd=PROJECT,stdout=log,stderr=subprocess.STDOUT)
                active[name]=(proc,log)
            for name,(proc,log) in list(active.items()):
                code=proc.poll()
                if code is None:continue
                log.close();del active[name]
                path=out/'runs'/name/'outcome.json'
                row=read(path) if path.exists() else dict(status='HARNESS_ERROR',mission_id=name,returncode=code,log=str(out/'logs'/f'{name}.txt'))
                if code or row['status']!='COMPLETE':stop=dict(status='FAIL' if row['status']=='P0_STOP' else 'BLOCKED',reason=row['status'],details=row);break
                completed.append(name)
                pair=row['paired']
                if pair['candidate_status']!='completed' or pair['candidate_quality'] is not True:
                    stop=dict(status='FAIL',reason='ORIGINAL_COMPLETE_AND_QUALITY_CONTRACT',mission_id=name,paired=pair);break
                print(json.dumps(dict(batch_completed=len(completed),batch_total=len(names),mission_id=name,status=row['status'])),flush=True)
            atomic(out/'batch_progress.json',dict(completed=completed,pending=pending,running=list(active),stop=stop))
            if stop:break
            time.sleep(.25)
    finally:
        for proc,log in active.values():
            if proc.poll() is None:proc.kill()
            proc.wait();log.close()
    return dict(completed=completed,stop=stop,unfinished=[n for n in names if n not in completed])


def launch(out):
    if out.exists():raise FileExistsError('new external attempt required')
    assert read(REPORT/'R1_revalidated_gate_attempt05.json')['status']=='PASS'
    assert read(REPORT/'gate_audit_G2a.json')['status']=='PASS'
    plan=read(PLAN);spec=plan['R2'];names=spec['mission_ids'];subset=spec['functionality_mission_ids']
    assert len(names)==len(set(names))==282 and len(subset)==70 and set(subset)<=set(names)
    out.mkdir();(out/'runs').mkdir();(out/'logs').mkdir()
    evidence=REPORT/'R2'/out.name;evidence.mkdir(parents=True,exist_ok=False)
    start=time.monotonic();deadline=start+spec['wall_limit_s'];hashes=code_hashes();baseline=read(BASE_PAIRS);stop=None
    atomic(out/'registration.json',dict(stage='R2',mission_ids=names,functionality_mission_ids=subset,input_plan_sha256=digest(PLAN),
        G2a_sha256=digest(REPORT/'gate_audit_G2a.json'),R1_gate_sha256=digest(REPORT/'R1_revalidated_gate_attempt05.json'),
        baseline_pairs_sha256=digest(BASE_PAIRS),source_sha256=hashes,config_sha256=CONFIG_SHA256,wall_limit_s=spec['wall_limit_s'],
        code_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT,text=True).strip(),
        task_sha256={n:digest(BASELINE/n/'input_task.json') for n in names},workers=spec['workers']))
    try:
        validate_inputs(plan)
        dryrun=gate_from_pairs(baseline,baseline);atomic(evidence/'baseline_gate_dryrun.json',dryrun)
        if not (REPORT/'R2/baseline_gate_dryrun.json').exists():atomic(REPORT/'R2/baseline_gate_dryrun.json',dryrun)
        assert dryrun['status']=='PASS'
        first=execute_batch(subset,out,deadline,hashes,spec['workers']);atomic(evidence/'functionality_run.json',first)
        stop=first['stop']
        if not stop:
            # The fixed 70 are reused exactly once; remaining 212 finish the 282 cohort.
            rest=execute_batch([n for n in names if n not in set(subset)],out,deadline,hashes,spec['workers'])
            atomic(evidence/'remaining_run.json',rest);stop=rest['stop']
    except Exception as exc:stop=dict(status='BLOCKED',reason=repr(exc),traceback=traceback.format_exc())
    pairs=[];outcomes=[]
    for n in names:
        path=out/'runs'/n/'outcome.json'
        if path.exists():
            row=read(path);outcomes.append(row)
            if row.get('status')=='COMPLETE':pairs.append(row['paired'])
    input_hashes_unchanged=True
    try:validate_inputs(plan)
    except Exception as exc:
        input_hashes_unchanged=False;stop=dict(status='FAIL',reason='LOCKED_INPUT_CHANGED',details=repr(exc))
    result=gate_from_pairs(pairs,baseline)
    result['required_checks']['input_hashes_unchanged']=input_hashes_unchanged
    result['required_checks'].update(source_unchanged=code_hashes()==hashes,r2_config_unchanged=digest(PROJECT/'configs/fast_dynamics/m3_r2_20261013_v1.json')==CONFIG_SHA,
        input_plan_unchanged=digest(PLAN)==read(out/'registration.json')['input_plan_sha256'])
    result['status']='PASS' if all(result['required_checks'].values()) and not stop else (stop or {}).get('status','FAIL')
    result.update(stage='R2',stop=stop,elapsed_wall_s=time.monotonic()-start,unfinished=[n for n in names if n not in {p['mission_id'] for p in pairs}],
                  evidence_paths=[str(out),str(evidence)],next_stage='R3' if result['status']=='PASS' else None)
    atomic(out/'paired_results.json',pairs);atomic(out/'outcomes.json',outcomes);atomic(out/'gate.json',result);atomic(evidence/'gate.json',result)
    atomic(REPORT/'R2_gate.json',result)
    state=read(REPORT/'pipeline_state.json');atomic(evidence/'previous_pipeline_state.json',state)
    state.update(status=result['status'],current_stage='R2',next_stage=result['next_stage']);state['stages']['R2']=dict(status=result['status'],executed=True,gate=str(evidence/'gate.json'))
    if result['status']=='PASS':state['last_pass_stage']='R2'
    else:
        for s in ('R3','R4'):state['stages'][s]=dict(status='BLOCKED',executed=False,reason='R2_NOT_PASS')
    atomic(REPORT/'pipeline_state.json',state)
    print(json.dumps(dict(stage='R2',status=result['status'],completed=len(pairs),expected=282,stop=stop,elapsed_s=result['elapsed_wall_s'])),flush=True)
    return 0 if result['status']=='PASS' else 2

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--worker');args=p.parse_args()
    raise SystemExit(worker(args.worker,args.output) if args.worker else launch(args.output))
