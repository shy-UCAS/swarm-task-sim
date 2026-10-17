"""Append-only R1 revalidation under the user's G-1 through G-5 amendment.

No production policy, old tests, historical gates, or datasets are edited.
"""
import argparse, copy, hashlib, json, math, os, re, shutil, subprocess, sys, time, traceback, zipfile
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
import numpy as np
from scripts.audit_m3_r3_r0 import read,digest,atomic,REPORT,DATA,BASE,CONFIG_SHA
from scripts.run_m3_r3_r1 import PLAN,code_hashes,capture
from scripts.m3_r3_support import d0b_oracle
OLD=DATA/'fast_dynamics/m3/m3_r3_r1_attempt01'
OUT=DATA/'fast_dynamics/m3/m3_r3_r1_revalidate01'
AUDIT=REPORT/'R1_revalidation'
GATE=REPORT/'R1_revalidated_gate.json'


def parse_log(text):
    outcomes={}
    matches=list(re.finditer(r'^test\S+ \(([^)]+)\) \.\.\. ',text,re.M))
    for i,m in enumerate(matches):
        chunk=text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)]
        found=re.search(r'^(ok|FAIL|ERROR|skipped[^\n]*)(?:\n|$)',chunk,re.M)
        if found:outcomes[m[1]]=found[1]
        else:
            sub=re.findall(r'^  test[^\n]+ \.\.\. (FAIL|ERROR|skipped[^\n]*)$',chunk,re.M)
            if not sub:raise ValueError('No test outcome: '+m[1])
            outcomes[m[1]]='ERROR' if 'ERROR' in sub else 'FAIL' if 'FAIL' in sub else sub[0]
    errors={}
    for m in re.finditer(r'^(FAIL|ERROR): test\S+ \(([^)]+)\)([^\n]*)\n-+\n(.*?)(?=\n={10,}|\n-{10,}\nRan |\Z)',text,re.M|re.S):
        detail=(m[3].strip()+'\n' if m[3].strip() else '')+m[4].strip()
        if m[2] in errors:errors[m[2]]['traceback']+='\n'+detail
        else:errors[m[2]]=dict(kind=m[1],traceback=detail)
    count=re.search(r'^Ran (\d+) tests? in',text,re.M)
    if not count or int(count[1])!=len(outcomes):raise ValueError('Missing/duplicate test IDs')
    return dict(count=len(outcomes),outcomes=outcomes,failures=errors)


def normalized(trace):
    # Only checkout identity differs; line numbers, exceptions, messages are exact.
    for name in ('Simulation-fe-int','Simulation-fe-m3r3'):
        trace=trace.replace(name,'CHECKOUT')
    trace=re.sub(r'[^\n\"]*baseline_checkout[\\/]+Multi-UAV SimpleGC',r'F:\\CASIA\\Drone Swarm Situational Awareness Algorithm\\CHECKOUT\\Multi-UAV SimpleGC',trace)
    return trace


def regression(candidate,baseline,whitelist):
    expected=set(baseline['outcomes']); new=set(candidate['outcomes'])-expected
    failures=[];known=[]
    for key,value in candidate['outcomes'].items():
        if value=='ok':
            if key in whitelist:failures.append(dict(test_id=key,reason='Whitelisted failure no longer reproduced; review required'))
        elif key in whitelist and key in baseline['failures'] and key in candidate['failures'] and candidate['failures'][key]['kind']==baseline['failures'][key]['kind'] and normalized(candidate['failures'][key]['traceback'])==normalized(baseline['failures'][key]['traceback']):
            known.append(key)
        else:failures.append(dict(test_id=key,reason=value,details=candidate['failures'].get(key)))
    for key in expected-set(candidate['outcomes']):failures.append(dict(test_id=key,reason='MISSING'))
    return dict(name='R1_REGRESSION_DELTA_ZERO',status='PASS' if not failures and set(known)==set(whitelist) else 'FAIL',
        executed=candidate['count'],passed=sum(v=='ok' for v in candidate['outcomes'].values()),baseline_known_failure=len(known),
        new_failure_count=len(failures),failures=failures,new_tests=sorted(new),
        per_test=[dict(test_id=k,baseline=baseline['outcomes'].get(k,'NEW_R3_TEST'),candidate=v,
                      classification='BASELINE_KNOWN_FAILURE' if k in known else 'PASS' if v=='ok' else 'NEW_REGRESSION') for k,v in candidate['outcomes'].items()])


def legacy_audit():
    attribution=read(REPORT/'R1/baseline_attribution.json')
    for p,h in attribution['evidence_sha256'].items():assert digest(p)==h,p
    for p,h in attribution['identical_source_files'].items():
        actual=subprocess.check_output(['git','show',BASE+':Multi-UAV SimpleGC/'+p],cwd=PROJECT)
        assert hashlib.sha256(actual).hexdigest()==h['fixed_base']==digest(PROJECT/p)
    a=parse_log((OLD/'R1_fixed_base_attribution.txt').read_text())
    b=parse_log((OLD/'unit_tests.txt').read_text())
    assert len(a['failures'])==len(b['failures'])==4 and a['failures'].keys()==b['failures'].keys()
    rows=[]
    notes={
      'test_115_percent_filter_then_seeded_order':'Old literal 1.15 conflicts with the unchanged FE generator configuration 1.30; candidate selection preference, not physics/safety.',
      'test_each_group_has_its_own_115_percent_bound':'Same stale 1.15 preference; current per-group ratio comes from unchanged generator configuration 1.30.',
      'test_five_calibration_round_limit_and_zero_flights_for_empty_pool':'unittest.mock fails before running calibration/spacing assertions: old calibrate_episode patch target is absent in both revisions. Safety-related downstream assertions are NOT proven by this failed test.',
      'test_variable_observation_dwell_preserves_eighty_percent_criterion':'KeyError reading obsolete minimum_dwell condition in the current criteria-r1 label schema. This test also contains a P0 audit assertion, which is unreached; do NOT claim its contract verified.'}
    for key,failure in a['failures'].items():
        same=failure['kind']==b['failures'][key]['kind'] and normalized(failure['traceback'])==normalized(b['failures'][key]['traceback'])
        assert same,key
        safety=key.endswith(('test_variable_observation_dwell_preserves_eighty_percent_criterion','test_five_calibration_round_limit_and_zero_flights_for_empty_pool'))
        rows.append(dict(test_id=key,status='BASELINE_REPRODUCED',kind=failure['kind'],baseline=failure,candidate=b['failures'][key],
             identical_failure_signature=same,old_source_unchanged=True,reason=notes[key.split('.')[-1]],
             r3_strategy_or_r2_compatibility_test=False,safety_related_unreached_assertions=safety,
             authorization='G-1 and G-5 take precedence over earlier R1a scope exclusion; only exact baseline signature is accepted, safety contracts are not waived' if safety else 'R1a and G-5'))
    record=dict(status='PASS',baseline_commit=BASE,environment=dict(python=sys.version,numpy=np.__version__),
        invocation='python -B -m unittest -v <modules>; original same llm environment, deterministic inline fixtures',
        prior_source_verification=attribution['identical_source_files'],evidence_sha256=attribution['evidence_sha256'],failures=rows)
    atomic(AUDIT/'R1_legacy_failures.json',record)
    lines=['# R1 历史回归故障核实','', '保留原 R1 FAIL；只使用已锁定日志及 Git 对象逐项复核。四项故障机制相同。',
           '', '注意：后两项含尚未执行到的间距/驻留审计断言，不能称其完全不涉及安全合同。最终 G-1/G-5 优先，允许登记精确历史故障；这不证明这些断言已通过，也不豁免物理、航点或独立审计硬门禁。']
    for r in rows:
        lines += ['', '## '+r['test_id'], '',r['status']+' / '+r['kind'],r['reason'],'','固定 FE 基线：','```',r['baseline']['traceback'],'```','当前候选原 R1：','```',r['candidate']['traceback'],'```']
    (AUDIT/'R1_legacy_failures.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (AUDIT/'legacy_test_debt.md').write_text('# 历史测试债务（本任务不修）\n\n'+'\n\n'.join('`'+r['test_id']+'`\n\n'+r['reason'] for r in rows)+'\n\n保留原断言与生产合同；后续单独确认现行合同并恢复测试覆盖。\n',encoding='utf-8')
    return a,[r['test_id'] for r in rows]


def phase_metrics(run,group,agent,metrics,distances):
    t=np.asarray(run['time_us']); pts=np.asarray(group['references'][agent]['points_enu_m'])
    witness=metrics['original_node_witnesses']; end=next(e['t_us'] for e in witness if e['node_index']==len(pts)-1)
    masks={'approach':t<end,'dwell':np.zeros(len(t),bool),'departure':np.zeros(len(t),bool),'terminal_stop':t>=end}
    dw=group['references'][agent].get('intermediate_dwell')
    boundaries=dict(terminal_stop_us=end)
    if dw:
        idx=dw['waypoint_index']; arrival=next(e['t_us'] for e in witness if e['node_index']==idx)
        good=(t>=arrival)&(np.linalg.norm(run['p'][:,0]-pts[idx],axis=1)<=1.)&(np.linalg.norm(run['v'][:,0],axis=1)<=.15)
        duration=math.ceil(float(dw['duration_s'])*10)*100000; start=None; finish=None
        for j,ok in enumerate(good):
            if not ok:start=None
            elif start is None:start=int(t[j])
            elif t[j]-start>=duration:finish=int(t[j]);break
        if finish is None:raise ValueError('Cannot reconstruct exact exported-sample hold interval')
        masks=dict(approach=t<start,dwell=(t>=start)&(t<finish),departure=(t>=finish)&(t<end),terminal_stop=t>=end)
        boundaries.update(hold_start_us=start,hold_end_us=finish)
    return dict(boundaries=boundaries,phases={k:dict(frames=int(m.sum()),max_m=float(distances[m].max()) if m.any() else None,p99_m=float(np.quantile(distances[m],.99)) if m.any() else None) for k,m in masks.items()})


def array_diff(actual,saved):
    if actual.shape!=saved.shape or actual.dtype!=saved.dtype:return dict(shape=[list(actual.shape),list(saved.shape)],dtype=[str(actual.dtype),str(saved.dtype)])
    if actual.tobytes()==saved.tobytes():return None
    x=actual.reshape(-1).view(np.dtype((np.void,actual.dtype.itemsize)));y=saved.reshape(-1).view(np.dtype((np.void,saved.dtype.itemsize)))
    flat=int(np.flatnonzero(x!=y)[0]);idx=np.unravel_index(flat,actual.shape)
    return dict(index=list(map(int,idx)),actual=str(actual[idx]),historical=str(saved[idx]),actual_bytes=actual[idx].tobytes().hex(),historical_bytes=saved[idx].tobytes().hex())


def probe_worker(pid,version,out):
    out.mkdir(parents=True,exist_ok=False)
    try:
        probe=next(p for p in read(PLAN)['R1']['probes'] if p['probe_id']==pid)
        group=copy.deepcopy(read(Path(probe['episode'])/'task.json')['group_skeletons'][probe['group_id']])
        oracle=d0b_oracle();input_sha=oracle.digest(group)
        run,snapshots,witnesses=capture(group,probe['agent_id'],version)
        metrics,distances,segments,_=oracle.metrics(run,group,probe['agent_id'],read(Path(probe['episode'])/'public_scene.json'),snapshots,witnesses,probe)
        history=Path(probe['historical_arms']['A' if version=='r2' else 'B2']);old=read(history/'result.json')
        arrays={k:np.asarray(run[k]) for k in ('time_us','p','v','a','agent_ids','execution_status')}
        with np.load(history/'run.npz',allow_pickle=False) as saved:diffs={k:array_diff(v,saved[k]) for k,v in arrays.items()}
        np.savez_compressed(out/'run.npz',**arrays)
        np.savez_compressed(out/'tracking_frames.npz',time_us=run['time_us'],distance_m=distances,nearest_segment_index=segments)
        geometry=lambda x:[{k:s[k] for k in ('original_node_offset','geometry','curves','primitive_caps')} for s in x]
        checks=dict(input_hash=input_sha==old['input_group_sha256']==oracle.digest(group),bitwise_arrays=not any(diffs.values()),
            geometry_and_caps_exact=geometry(snapshots)==geometry(old['tracker_snapshots']),physical=metrics['physical_status']=='PASS',
            ordered_nodes=metrics['tracking']['all_waypoints_witnessed'],no_scene_violation=not metrics['scene']['violation'],
            witnesses_exact=metrics['original_node_witnesses']==old['original_node_witnesses'],dwell_exact=metrics['dwell']==old['dwell'],
            observation_exact=metrics['observation_dwell']==old['observation_dwell'],low_speed_exact=metrics['low_speed']==old['low_speed'],tracking_exact=metrics['tracking']==old['tracking'])
        phase=phase_metrics(run,group,probe['agent_id'],metrics,distances)
        precision=dict(absolute_status='PASS' if distances.max()<=.5 else 'FAIL',max_m=float(distances.max()),p99_m=float(np.quantile(distances,.99)),threshold_m=.5,phase=phase)
        if version=='r3':
            base=read(out.parent/'r2/result.json');bt=base['precision']
            if bt['absolute_status']=='PASS':checks['precision']=precision['absolute_status']=='PASS'
            else:
                comparisons={k:dict(baseline=b,candidate=phase['phases'][k],passed=(b['max_m'] is None and phase['phases'][k]['max_m'] is None) or (b['max_m'] is not None and phase['phases'][k]['max_m'] is not None and phase['phases'][k]['max_m']<=b['max_m']+1e-9 and phase['phases'][k]['p99_m']<=b['p99_m']+1e-9)) for k,b in bt['phase']['phases'].items()}
                precision['relative_by_phase']=comparisons;checks['precision']=all(x['passed'] for x in comparisons.values())
            precision['gate_mode']='ABSOLUTE' if bt['absolute_status']=='PASS' else 'G2_PHASE_NONREGRESSION'
        result=dict(probe_id=pid,version=version,status='PASS' if all(checks.values()) else 'FAIL',checks=checks,first_array_differences=diffs,metrics=metrics,precision=precision,input_group_sha256=input_sha,historical_result=str(history/'result.json'))
        atomic(out/'result.json',result)
        return 0 if result['status']=='PASS' else 2
    except Exception as e:
        atomic(out/'error.json',dict(status='BLOCKED',type=type(e).__name__,message=str(e),traceback=traceback.format_exc()));return 3


def tests(project,modules,log,deadline):
    env=dict(os.environ);env['PYTHONPATH']=str(project)+os.pathsep+str(project/'tests');env['PYTHONSAFEPATH']='1'
    with log.open('x',encoding='utf-8') as f:
        p=subprocess.run([sys.executable,'-B','-m','unittest','-v',*modules],cwd=project,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=max(1,deadline-time.monotonic()))
    result=parse_log(log.read_text());result['returncode']=p.returncode;return result


def validate_inputs(plan):
    mutable={str(PROJECT/'swarm_sim'/'fast_dynamics'/n) for n in ('route_tracker.py','contracts.py')}
    for f in plan['input_files']:
        if f['path'] not in mutable:assert digest(f['path'])==f['sha256'],f['path']
    return dict(input_files=len(plan['input_files']),mutable_paths=sorted(mutable))


def export_baseline(archive,destination):
    subprocess.run(['git','-C',str(PROJECT.parent),'archive','--format=zip','--output',str(archive),BASE,'Multi-UAV SimpleGC','.github'],cwd=PROJECT,check=True)
    with zipfile.ZipFile(archive) as z:z.extractall(destination)
    # Standalone temporary Git metadata: reads shared immutable objects only;
    # no worktree registration and no writes to the source repository.
    subprocess.run(['git','init','--quiet',str(destination)],cwd=PROJECT,check=True)
    common=Path(subprocess.check_output(['git','rev-parse','--path-format=absolute','--git-common-dir'],cwd=PROJECT,text=True).strip())
    (destination/'.git/objects/info/alternates').write_text((common/'objects').as_posix()+'\n',encoding='utf-8',newline='\n')
    (destination/'.git/HEAD').write_text(BASE+'\n',encoding='ascii',newline='\n')
    subprocess.run(['git','-C',str(destination),'read-tree',BASE],cwd=PROJECT,check=True)
    fixture=Path('v07_dataset/attempt_20261014T014017Z_15a6bf38/family_s12_b0c036776dcaff71_s2r3_sk00/skeleton.json')
    source=DATA/fixture;target=destination.parent/'SwarmData'/fixture
    before=digest(source);target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():assert digest(target)==before
    else:shutil.copyfile(source,target)
    assert digest(source)==digest(target)==before
    atomic(destination/'baseline_environment.json',dict(commit=BASE,source_object_directory=str(common/'objects'),fixture_source=str(source),fixture_copy=str(target),fixture_sha256=before))
    return destination/'Multi-UAV SimpleGC'


def startup(expected_head=None):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT,text=True).strip()
    if expected_head is not None:assert head==expected_head
    assert subprocess.check_output(['git','branch','--show-current'],cwd=PROJECT,text=True).strip()=='fe/m3-r3-p2-candidate'
    assert not subprocess.check_output(['git','diff','c9955ca8d5408309556f5942b88916ca3eb9cd7c','--','swarm_sim','task_v07','configs'],cwd=PROJECT)
    plan=read(PLAN);assert digest(PLAN)==read(REPORT/'R0_revalidated_gate.json')['input_sha256']
    result=validate_inputs(plan)
    return dict(status='DRY_RUN_PASS',head=head,**result)


def launch(expected_head):
    assert not OUT.exists() and not GATE.exists()
    assert expected_head is not None
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT,text=True).strip()==expected_head
    plan=read(PLAN);assert digest(PLAN)==read(REPORT/'R0_revalidated_gate.json')['input_sha256']
    OUT.mkdir();AUDIT.mkdir(parents=True);start=time.monotonic();deadline=start+plan['R1']['wall_limit_s']
    protected={str(p):digest(p) for p in (REPORT/'R1_report.md',REPORT/'R1_gate.json',REPORT/'R1/gate.json')}
    hashes=code_hashes();results=[];reg=None;stop=None;baseline_dryrun={}
    amended=dict(schema='m3-r3-user-gates-g1-g5-v1',parent_plan_sha256=digest(PLAN),baseline_commit=BASE,
        R1=dict(original_test_count=209,baseline_test_count=200,additional_test_modules=['test_m3_r3_r1_revalidation'],whitelist='R1_legacy_failures.json exact IDs and exact normalized traces only',
                phase_definition='Original-node witness defines terminal-stop start; DwellRouteTracker original 1m/.15m/s exported-frame continuous planned hold defines dwell; remaining portions approach/departure. No dwell => N/A dwell/departure.',
                precision='Absolute .5m if r2 passes; otherwise each phase max and p99 <= same-input r2 + 1e-9',
                absolute_hard=['r2 bitwise','r3 B2 bitwise','input hashes','ordered nodes','physical limits','curve geometry/caps','no new regression']),
        R2=dict(hard=['original tiers().hard.passed','282 tasks complete and comparable'],numerical_nonregression='REPORT_ONLY; per-metric worst 10 regressions'),
        R3='Original integration requirements; G-1 dry run and exact baseline delta',
        R4=dict(hard=['original30 strict pairs','no P0ContractError','independent audits','retained episode separation >=2m','no forbidden violations','source hashes unchanged'],additional8='REPORT_ONLY first failure stage/reason'),
        budgets={s:plan[s].get('wall_limit_s') for s in ('R1','R2','R3','R4')})
    assert read(REPORT/'R1_validation_plan_amended.json')==amended
    atomic(OUT/'registration.json',dict(parent_commit=expected_head,plan_sha256=digest(REPORT/'R1_validation_plan_amended.json'),source_sha256=hashes,old_evidence_sha256=protected,probes=plan['R1']['probes'],wall_limit_s=plan['R1']['wall_limit_s']))
    try:
        oldbaseline,white=legacy_audit()
        startup(expected_head)
        # An immutable Git archive is a temporary isolated checkout, not another worktree.
        archive=OUT/'baseline.zip'
        baseline_root=OUT/'baseline_checkout'
        baseproject=export_baseline(archive,baseline_root)
        baseline=tests(baseproject,[m for m in plan['R1']['unit_modules'] if m!='test_m3_r3_reference'],OUT/'baseline_tests.txt',deadline)
        # Archive absolute roots normalized using explicit replacement, no stack frames removed.
        for f in baseline['failures'].values():
            f['traceback']=f['traceback'].replace(str(baseproject),str(PROJECT)).replace(str(baseproject).replace('\\','\\\\'),str(PROJECT).replace('\\','\\\\'))
        assert baseline['count']==200 and set(baseline['failures'])==set(white)
        assert all(normalized(baseline['failures'][k]['traceback'])==normalized(oldbaseline['failures'][k]['traceback']) for k in white)
        atomic(OUT/'baseline_test_results.json',baseline)
        baseline_dryrun=dict(stage='R1',status='BASELINE_EVALUATED',test_results=str(OUT/'baseline_test_results.json'),legacy_failures=white,tests=200,probes=[],hard_checks=dict(frozen_r2_sha=digest(PROJECT/'configs/fast_dynamics/m3_r2_20261013_v1.json')==CONFIG_SHA),unexecuted_candidate_only=['r3 B2 equality','r3 selector tests'],policy='G1/G2 baseline failure switches to relative criterion; absolute values retained')
        # All r2 replays precede r3, so the dry run is complete before candidate evaluation.
        for version in ('r2','r3'):
            if version=='r3':
                atomic(AUDIT/'baseline_gate_dryrun.json',baseline_dryrun)
                candidate=tests(PROJECT,plan['R1']['unit_modules'],OUT/'unit_tests.txt',deadline)
                reg=regression(candidate,baseline,white);atomic(AUDIT/'regression_delta.json',reg)
                extra=tests(PROJECT,['test_m3_r3_r1_revalidation'],OUT/'gate_unit_tests.txt',deadline)
                atomic(AUDIT/'gate_unit_tests.json',extra)
                if extra['returncode'] or any(v!='ok' for v in extra['outcomes'].values()):
                    stop=dict(status='FAIL',reason='NEW_GATE_TESTS');break
                print(json.dumps({k:reg[k] for k in ('status','executed','passed','baseline_known_failure','new_failure_count')}),flush=True)
                if reg['status']!='PASS':stop=dict(status='FAIL',reason='R1_REGRESSION_DELTA_ZERO');break
            for probe in plan['R1']['probes']:
                pid=probe['probe_id'];dest=OUT/pid/version
                with (OUT/(pid+'_'+version+'.log')).open('x',encoding='utf-8') as f:
                    p=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',pid,'--version',version,'--output',str(dest)],cwd=PROJECT,stdout=f,stderr=subprocess.STDOUT,timeout=max(1,deadline-time.monotonic()))
                result=read(dest/'result.json') if (dest/'result.json').exists() else read(dest/'error.json')
                results.append(result);print(json.dumps(dict(probe=pid,version=version,status=result['status'],checks=result.get('checks'))),flush=True)
                if version=='r2':baseline_dryrun['probes'].append(dict(probe_id=pid,checks=result.get('checks'),precision=result.get('precision')))
                atomic(OUT/'progress.json',dict(results=results,elapsed_s=time.monotonic()-start))
                if p.returncode:stop=dict(status=result['status'],reason='PROBE_REQUIRED_CHECK',probe_id=pid,version=version,details=result);break
            if stop:break
    except subprocess.TimeoutExpired:stop=dict(status='TIME_LIMIT_STOP',reason='R1 7200s budget')
    except Exception as e:stop=dict(status='BLOCKED',reason=repr(e),traceback=traceback.format_exc())
    stable=hashes==code_hashes();historical_unchanged=all(digest(p)==h for p,h in protected.items())
    checks=dict(legacy_audit=(REPORT/'R1_legacy_failures.json').exists(),regression=reg is not None and reg['status']=='PASS',all14=len(results)==14 and all(r['status']=='PASS' for r in results),source_unchanged=stable,old_fail_evidence_unchanged=historical_unchanged,r2_config=digest(PROJECT/'configs/fast_dynamics/m3_r2_20261013_v1.json')==CONFIG_SHA)
    status='PASS' if all(checks.values()) and not stop else (stop or {}).get('status','FAIL')
    gate=dict(stage='R1',status=status,result='R1_REVALIDATED_PASS' if status=='PASS' else 'R1_REVALIDATION_'+status,required_checks=checks,regression=reg,
        stop=stop,probes=[{k:r[k] for k in ('probe_id','version','status','checks','precision') if k in r} for r in results],
        elapsed_wall_s=time.monotonic()-start,plan_sha256=digest(REPORT/'R1_validation_plan_amended.json'),evidence_paths=[str(OUT),str(AUDIT)],next_stage='R2' if status=='PASS' else None)
    atomic(OUT/'summary.json',gate);atomic(GATE,gate)
    if not (AUDIT/'baseline_gate_dryrun.json').exists():
        baseline_dryrun.update(status='INCOMPLETE',stop=stop);atomic(AUDIT/'baseline_gate_dryrun.json',baseline_dryrun)
    state=read(REPORT/'pipeline_state.json');atomic(AUDIT/'previous_pipeline_state.json',state)
    state.update(status=status,current_stage='R1',next_stage=gate['next_stage']);state['stages']['R1']=dict(status=status,executed=True,gate=str(GATE))
    if status=='PASS':state['last_pass_stage']='R1'
    atomic(REPORT/'pipeline_state.json',state)
    print(json.dumps(dict(status=status,stop=stop and {k:v for k,v in stop.items() if k!='details'},elapsed=gate['elapsed_wall_s'])),flush=True)
    return 0 if status=='PASS' else 2

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker');p.add_argument('--version');p.add_argument('--output',type=Path)
    p.add_argument('--attempt',type=int);p.add_argument('--expected-head');p.add_argument('--dry-run',action='store_true');a=p.parse_args()
    if a.dry_run:
        print(json.dumps(startup(a.expected_head)),flush=True);raise SystemExit(0)
    if a.worker:raise SystemExit(probe_worker(a.worker,a.version,a.output))
    if a.attempt is None or a.attempt<2:p.error('new attempt >= 2 required')
    OUT=DATA/f'fast_dynamics/m3/m3_r3_r1_revalidate{a.attempt:02d}'
    AUDIT=REPORT/f'R1_revalidation/attempt{a.attempt:02d}'
    GATE=REPORT/f'R1_revalidated_gate_attempt{a.attempt:02d}.json'
    raise SystemExit(launch(a.expected_head))
