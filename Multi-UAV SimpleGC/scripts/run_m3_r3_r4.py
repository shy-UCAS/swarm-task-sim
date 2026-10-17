"""Fixed R4 pilot: original production pipeline, explicit r3 in isolated workers."""
import argparse
import copy
import json
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
import numpy as np
from scripts.audit_m3_r3_r0 import read, digest, atomic, REPORT, CONFIG_SHA
from scripts.run_m3_r3_r1 import PLAN, code_hashes
from scripts.revalidate_m3_r3_r1 import tests, validate_inputs
from scripts.m3_r3_g5a import load_amendment, regression_g5a
from scripts.run_m3_r3_r3 import git
from swarm_sim.fast_dynamics.reference_r3 import CONFIG_SHA256
from task_v07.expansion.contracts import P0ContractError
from task_v07.expansion.views import _paired


@contextmanager
def r3_execution(calls, executor=None):
    import scripts.run_v07_s2_episode_batch as batch
    import task_v07.unified.rehearsal as rehearsal
    from task_v07.execution import execute
    original = executor or execute
    def selected(*args, **kwargs):
        if 'reference_version' in kwargs and kwargs['reference_version'] != 'r3':
            raise P0ContractError('R4 worker requested another reference version')
        kwargs['reference_version'] = 'r3'
        run = original(*args, **kwargs)
        if run['config_sha256'] != CONFIG_SHA256:
            raise P0ContractError('R4 execution config is not registered r3')
        calls.append(dict(only_agent=kwargs.get('only_agent'), config_sha256=run['config_sha256'],
                          execution_status=run['execution_status']))
        return run
    with patch.object(batch, 'execute', selected), patch.object(rehearsal, 'execute', selected):
        yield


def episode_checks(root, row, config_sha):
    labels = read(root/'labels.json')
    source = read(root/'source.json')
    exact = read(root/'independent_exact_audit.json')
    geometry = read(root/'policy_geometry_audit.json')
    infrastructure = geometry['infrastructure_report']
    quality = labels['generation_quality']
    checks = dict(
        independent_audits=exact['status']=='PASS' and geometry['independent']['status']=='PASS',
        retained_minimum_separation=(not quality['retained'] or quality['minimum_separation_m']>=2.0),
        no_forbidden=infrastructure['forbidden_policy_checked'] is True and infrastructure['forbidden_region_sample_count']==0,
        no_obstacle_or_world_violation=infrastructure['hard_obstacle_sample_count']==0 and infrastructure['outside_world_sample_count']==0,
        registered_config=source['config_sha256']==config_sha,
    )
    return dict(episode_id=row['episode_id'], checks=checks, passed=all(checks.values()),
                minimum_separation_m=quality['minimum_separation_m'],
                retained=quality['retained'], execution_status=source['execution_status'],
                M1=labels['cluster']['result'], groups=labels['task_groups'],
                measured_approach_by_group=row.get('measured_approach_by_group'),
                artifact_sha256={name:digest(root/name) for name in ('source.json','task.json','labels.json','metrics.json','truth_10hz.npz','independent_exact_audit.json','policy_geometry_audit.json')})


def pair_result(out, sid, rows, config_sha):
    paired = _paired(rows)
    checks = [episode_checks(out/r['path'], r, config_sha) for r in rows if r.get('path')]
    first = None
    if not paired:
        for r in rows:
            if r.get('state') != 'generated':
                history = r.get('geometry_attempts', [])
                first = dict(stage=r.get('category',r.get('state')), reason=r.get('reason'),
                             first_attempt=history[0] if history else None,
                             final_detail=r.get('rejection_detail'))
                break
            if r.get('execution_status') != 'completed':
                first = dict(stage='execution', reason=r.get('execution_status')); break
            if r.get('all_groups_complete') is not True:
                first = dict(stage='M1', reason=r.get('groups')); break
        if first is None:
            first = dict(stage='strict_pair', reason=[{k:r.get(k) for k in ('mode','state','quality_valid','audit_passed','task_result','coordination_by_group')} for r in rows])
    return dict(skeleton_id=sid, paired=paired, episodes=checks,
                hard_physical_audit_passed=all(c['passed'] for c in checks), first_failure=first)


def qc_episode(root, sid, mode):
    from scripts.qc_v07_fe_speed_profile import group_map, analyse_member
    task = read(root/'task.json'); labels = read(root/'labels.json'); groups = group_map(task)
    members = []
    with np.load(root/'truth_10hz.npz', allow_pickle=False) as truth:
        for agent in sorted(groups):
            record = analyse_member(task, truth, agent, sid, mode, groups)
            record['M1_observed'] = labels['agents'][agent]['observed']
            members.append(record)
    return dict(skeleton_id=sid, mode=mode, members=members,
                reference_sha256=__import__('hashlib').sha256(json.dumps(task['references'],sort_keys=True,separators=(',',':')).encode()).hexdigest())


def qc_summary(episodes):
    buckets = {}
    for ep in episodes:
        for member in ep['members']:
            key = (member['role'],member['execution_method'],member['mode'])
            b = buckets.setdefault(key, dict(members=0, low_speed_events=0, distance_km=0., motion_time_s=0., low_speed_time_s=0., dwell_positive=0, dwell_evaluable=0, empty_motion_windows=0, near_corner_events=0))
            b['members'] += 1
            b['empty_motion_windows'] += int(member['empty_motion_window'])
            b['low_speed_events'] += member['low_speed_event_count'] or 0
            b['distance_km'] += member['range_km'] or 0.
            duration = member['motion_window_duration_s'] or 0.
            b['motion_time_s'] += duration
            b['low_speed_time_s'] += duration*(member['low_speed_time_share'] or 0.)
            b['near_corner_events'] += sum(e['distance_to_vertex_m'] is not None and e['distance_to_vertex_m']<=3. for e in member['events'])
            dwell = member['M1_observed'].get('contribution',{}).get('dwell')
            if isinstance(dwell,dict) and 'detected' in dwell:
                b['dwell_evaluable'] += 1; b['dwell_positive'] += int(dwell['detected'])
    rows=[]
    for key,b in sorted(buckets.items()):
        rows.append(dict(role=key[0],execution_method=key[1],mode=key[2],**b,
                         events_per_km=b['low_speed_events']/b['distance_km'] if b['distance_km'] else None,
                         low_speed_time_share=b['low_speed_time_s']/b['motion_time_s'] if b['motion_time_s'] else None))
    return rows


def baseline_dryrun(plan, amendment, out):
    baseline = read(amendment['baseline_results_path'])
    reg = regression_g5a(baseline,baseline,amendment['known_signatures'],amendment['checkout_roots'])
    pairs=[]; qc=[]; unavailable=[]
    for skeleton in plan['R4']['skeletons']:
        sid=skeleton['skeleton_id']
        if 'FE_INT_30' not in skeleton['sources']:
            unavailable.append(dict(skeleton_id=sid,status='N/A',reason='No historical full r2 episode; P2 pair outcome is diagnostic under G-4'))
            continue
        root=Path(skeleton['historical_attempt'])
        rows=[read(root/sid/mode/'metrics.json') for mode in plan['R4']['modes']]
        pairs.append(pair_result(root,sid,rows,CONFIG_SHA))
        for row in rows:qc.append(qc_episode(root/row['path'],sid,row['mode']))
    atomic(out/'baseline_qc_members.json',qc)
    result=dict(stage='R4',status='PASS' if reg['status']=='PASS' and len(pairs)==30 and all(p['paired'] and p['hard_physical_audit_passed'] for p in pairs) else 'FAIL',
                regression=reg, original_pairs=pairs, recovered_8=unavailable,
                qc_summary=qc_summary(qc), source_immutability_evidence=str(REPORT/'R3_gate.json'),
                note='Historical r2 artifacts are locked in R0 inputs; no new r2/SITL or holdout simulation')
    atomic(out/'baseline_gate_dryrun.json',result)
    return result


def worker(sid, out):
    from scripts.run_v07_s2_episode_batch import run_episode_job
    started=time.monotonic(); calls=[]
    job=next(j for j in read(out/'registration.json')['jobs'] if j['descriptor']['skeleton_id']==sid)
    result=dict(skeleton_id=sid,status='INCOMPLETE')
    try:
        with r3_execution(calls):rows=run_episode_job(job)
        result=pair_result(out,sid,rows,CONFIG_SHA256)
        result.update(status='PASS' if result['hard_physical_audit_passed'] else 'FAIL',rows=rows)
        qc=[qc_episode(out/r['path'],sid,r['mode']) for r in rows if r.get('path')]
        atomic(out/'qc'/f'{sid}.json',qc)
    except P0ContractError as exc:
        result.update(status='P0_STOP',reason=str(exc),traceback=traceback.format_exc())
    except Exception as exc:
        result.update(status='BLOCKED',reason=repr(exc),traceback=traceback.format_exc())
    result.update(execute_calls=calls,elapsed_wall_s=time.monotonic()-started)
    atomic(out/'results'/f'{sid}.json',result)
    return 0 if result['status']=='PASS' else 2


def launch(out):
    assert read(REPORT/'R3_gate.json')['status']=='PASS'
    assert git('branch','--show-current')=='fe/m3-r3-p2-candidate'
    assert not git('status','--porcelain')
    assert not out.exists()
    plan=read(PLAN); validate_inputs(plan); amendment=load_amendment()
    out.mkdir(); ev=REPORT/'R4'/out.name; ev.mkdir(parents=True,exist_ok=False)
    for folder in ('logs','results','qc'):(out/folder).mkdir()
    start=time.monotonic(); deadline=start+plan['R4']['wall_limit_s']; hashes=code_hashes()
    jobs=copy.deepcopy(plan['R4']['jobs'])
    for job in jobs:job['out']=str(out)
    identities={s['skeleton_id']:s for s in plan['R4']['skeletons']}
    atomic(out/'registration.json',dict(stage='R4',jobs=jobs,skeletons=plan['R4']['skeletons'],workers=plan['R4']['workers'],wall_limit_s=plan['R4']['wall_limit_s'],source_sha256=hashes,input_plan_sha256=digest(PLAN),G5a_sha256=digest(REPORT/'G5a_gate_amendment.json'),code_commit=git('rev-parse','HEAD'),r3_config_sha256=CONFIG_SHA256))
    stop=None; completed={}; active={}; queue=[j['descriptor']['skeleton_id'] for j in jobs]; checks={}; reg=None; dry=None
    try:
        dry=baseline_dryrun(plan,amendment,out); atomic(ev/'baseline_gate_dryrun.json',dry)
        checks['baseline_gate_dryrun']=dry['status']=='PASS'
        print(json.dumps(dict(stage='R4_baseline',status=dry['status'],original_pairs=sum(p['paired'] for p in dry['original_pairs']))),flush=True)
        if not checks['baseline_gate_dryrun']:stop=dict(status='FAIL',reason='BASELINE_DRYRUN_FAILED')
        if not stop:
            baseline=read(amendment['baseline_results_path']); modules=plan['R3']['regression_modules']
            candidate=tests(PROJECT,modules,out/'integration_tests.txt',deadline); atomic(out/'integration_results.json',candidate)
            reg=regression_g5a(candidate,baseline,amendment['known_signatures'],amendment['checkout_roots']); atomic(ev/'regression_delta.json',reg)
            extras=sorted(p.stem for p in (PROJECT/'tests').glob('test_m3_r3*.py') if p.stem not in modules)
            added=tests(PROJECT,extras,out/'harness_tests.txt',deadline); atomic(ev/'harness_tests.json',added)
            checks.update(regression_delta_zero=reg['status']=='PASS',harness_tests=added['returncode']==0 and all(v=='ok' for v in added['outcomes'].values()))
            print(json.dumps(dict(stage='R4_tests',status=reg['status'],executed=reg['executed'],passed=reg['passed'],known=reg['baseline_known_failure'],harness=added['count'])),flush=True)
            if not all(checks.values()):stop=dict(status='FAIL',reason='REGRESSION_OR_HARNESS_TEST')
        while (queue or active) and not stop:
            if time.monotonic()>=deadline:stop=dict(status='TIME_LIMIT_STOP',reason='R4 21600s wall budget');break
            if code_hashes()!=hashes:stop=dict(status='P0_STOP',reason='SOURCE_FINGERPRINT_CHANGED');break
            while queue and len(active)<plan['R4']['workers']:
                sid=queue.pop(0); log=(out/'logs'/f'{sid}.txt').open('x',encoding='utf-8')
                process=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--output',str(out),'--worker',sid],cwd=PROJECT,stdout=log,stderr=subprocess.STDOUT)
                active[sid]=(process,log)
            for sid,(process,log) in list(active.items()):
                if process.poll() is None:continue
                log.close(); del active[sid]
                file=out/'results'/f'{sid}.json'
                result=read(file) if file.exists() else dict(skeleton_id=sid,status='BLOCKED',reason='WORKER_EXIT_WITHOUT_RESULT',returncode=process.returncode)
                completed[sid]=result
                if result['status']!='PASS':stop=dict(status=result['status'],reason='WORKER_OR_PHYSICAL_AUDIT',skeleton_id=sid,details=result)
                elif 'FE_INT_30' in identities[sid]['sources'] and not result['paired']:stop=dict(status='FAIL',reason='ORIGINAL_30_STRICT_PAIR_FAILED',skeleton_id=sid,details=result['first_failure'])
                print(json.dumps(dict(stage='R4_job',skeleton_id=sid,status=result['status'],paired=result.get('paired'),completed=len(completed),total=38)),flush=True)
                if stop:break
            atomic(out/'progress.json',dict(completed=list(completed),active=list(active),pending=queue,elapsed_wall_s=time.monotonic()-start,stop=stop))
            if not stop and (queue or active):time.sleep(5)
    except subprocess.TimeoutExpired:stop=dict(status='TIME_LIMIT_STOP',reason='R4 21600s wall budget')
    except Exception as exc:stop=dict(status='BLOCKED',reason=repr(exc),traceback=traceback.format_exc())
    finally:
        for process,log in active.values():
            if process.poll() is None:process.kill()
            process.wait();log.close()
    # Always preserve partial outcomes and the full original denominator.
    for file in (out/'results').glob('*.json'):
        result=read(file);completed[result['skeleton_id']]=result
    unfinished=[sid for sid in identities if sid not in completed]
    candidate_qc=[]
    for file in (out/'qc').glob('*.json'):candidate_qc.extend(read(file))
    original_qc=[q for q in candidate_qc if 'FE_INT_30' in identities[q['skeleton_id']]['sources']]
    recovered_qc=[q for q in candidate_qc if 'FE_INT_30' not in identities[q['skeleton_id']]['sources']]
    baseline_qc=read(out/'baseline_qc_members.json') if (out/'baseline_qc_members.json').exists() else []
    baseline_map={(q['skeleton_id'],q['mode']):q for q in baseline_qc}
    comparisons=[dict(skeleton_id=q['skeleton_id'],mode=q['mode'],reference_geometry_identical=q['reference_sha256']==baseline_map[(q['skeleton_id'],q['mode'])]['reference_sha256']) for q in original_qc]
    diagnostics=dict(original_r2=qc_summary(baseline_qc),original_r3=qc_summary(original_qc),recovered_r3=qc_summary(recovered_qc),geometry_comparisons=comparisons,
                     note='Low speed: V_LOW=V_MOVE=1 m/s, no minimum duration. M1 spatial dwell is not a hover label. Different selected geometry prevents pure r3 attribution.')
    atomic(out/'quality_diagnostics.json',diagnostics);atomic(ev/'quality_diagnostics.json',diagnostics)
    original=[completed.get(sid,{}) for sid,s in identities.items() if 'FE_INT_30' in s['sources']]
    recovered=[dict(skeleton_id=sid,**{k:completed.get(sid,{}).get(k) for k in ('status','paired','first_failure','elapsed_wall_s')}) for sid,s in identities.items() if 'FE_INT_30' not in s['sources']]
    checks.update(original_30_strict_pairs=len(original)==30 and all(r.get('paired') is True for r in original),
                  physical_and_audits=all(r.get('hard_physical_audit_passed') is True for r in completed.values()),
                  no_P0=not any(r['status']=='P0_STOP' for r in completed.values()) and (stop or {}).get('status')!='P0_STOP',
                  source_unchanged=code_hashes()==hashes,
                  all_registered_jobs_accounted=len(completed)==38 and not unfinished and all(r['status']=='PASS' for r in completed.values()))
    try:validate_inputs(plan);checks['input_hashes_unchanged']=True
    except Exception as exc:checks['input_hashes_unchanged']=False;stop=stop or dict(status='P0_STOP',reason='INPUT_CHANGED',details=repr(exc))
    if time.monotonic()>deadline:stop=stop or dict(status='TIME_LIMIT_STOP',reason='R4 21600s wall budget')
    status='PASS' if not stop and all(checks.values()) else (stop or {}).get('status','FAIL')
    result=dict(stage='R4',status=status,required_checks=checks,stop=stop,original_pairs=sum(r.get('paired') is True for r in original),original_denominator=30,recovered_pairs=sum(r.get('paired') is True for r in recovered),recovered_denominator=8,recovered_results=recovered,completed_skeletons=len(completed),unfinished=unfinished,regression=reg,elapsed_wall_s=time.monotonic()-start,code_commit=git('rev-parse','HEAD'),evidence_paths=[str(out),str(ev)],next_stage=None,formal_freeze=False)
    atomic(out/'episode_records.json',[row for r in completed.values() for row in r.get('rows',[])])
    atomic(out/'gate.json',result);atomic(ev/'gate.json',result);atomic(REPORT/'R4_gate.json',result)
    state=read(REPORT/'pipeline_state.json');atomic(ev/'previous_pipeline_state.json',state)
    state.update(status=status,current_stage='R4',next_stage=None);state['stages']['R4']=dict(status=status,executed=True,gate=str(ev/'gate.json'))
    if status=='PASS':state['last_pass_stage']='R4'
    atomic(REPORT/'pipeline_state.json',state)
    print(json.dumps(dict(stage='R4',status=status,stop=stop,completed=len(completed),elapsed_wall_s=result['elapsed_wall_s'])),flush=True)
    return 0 if status=='PASS' else 2


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--worker')
    args=parser.parse_args();raise SystemExit(worker(args.worker,args.output) if args.worker else launch(args.output))
