"""Revalidate all R0 evidence under the explicitly authorized N/A amendment."""
import argparse, json, subprocess, sys, time, platform
from pathlib import Path
from datetime import datetime, timezone
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from scripts.audit_m3_r3_r0 import read,digest,atomic,DATA,TUNING,BASELINE,REPORT,CONFIG_SHA
from scripts.m3_r3_gates import evaluate
from swarm_sim.fast_dynamics.calibration import paired_metrics,tuning_tasks
from scripts.tune_fast_dynamics_m3 import SPLIT_SHA

START='37919b04ff6f4caafb1dcf8e4554a36235b28b80'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    out=args.output.resolve()
    if out.exists() or not out.is_relative_to((DATA/'fast_dynamics/m3').resolve()):raise ValueError('new external attempt required')
    if (REPORT/'R0_revalidated_gate.json').exists():raise ValueError('revalidation already recorded')
    git=lambda *a:subprocess.check_output(['git',*a],cwd=PROJECT,text=True).strip()
    assert git('rev-parse','HEAD')==START and git('branch','--show-current')=='fe/m3-r3-p2-candidate'
    out.mkdir(parents=True,exist_ok=False);started=time.monotonic()
    old_paths=[REPORT/x for x in ('R0/gate.json','R0_report.md','R0_validation_plan.json','R0/execution_log.txt','pipeline_state.json')]
    history={str(p):digest(p) for p in old_paths}; old=read(REPORT/'R0_validation_plan.json')
    inventory={}
    def bind(p,expected=None):
        p=Path(p).resolve();d=digest(p)
        if expected is not None and d!=expected:raise ValueError('hash mismatch: '+str(p))
        inventory[str(p)]=dict(path=str(p),sha256=d,bytes=p.stat().st_size)
        return d
    def load(p,expected=None):bind(p,expected);return read(p)
    for i,r in enumerate(old['input_files'],1):
        bind(r['path'],r['sha256'])
        if i%2000==0:print(json.dumps(dict(rehashed=i,total=len(old['input_files']))),flush=True)
    split=load(read(PROJECT/'verification/fast_dynamics_m3/r2_split_index.json')['external_split'],SPLIT_SHA)
    allowed={r['mission_id']:r for r in tuning_tasks(split)}
    frozen=load(TUNING/'freeze_record.json'); config=load(TUNING/'frozen_m3_v1.json',CONFIG_SHA)
    load(PROJECT/'configs/fast_dynamics/m3_r2_20261013_v1.json',CONFIG_SHA)
    names=sorted(r['mission_id'] for r in load(TUNING/'config_020_full/evaluation.json')['rows'])
    assert len(names)==len(set(names))==282 and not set(names)-allowed.keys()
    assert set(names)=={r['mission_id'] for r in load(BASELINE/'baseline.json')['rows']}
    pairs=[]
    for name in names:
        r=allowed[name];task=load(BASELINE/name/'input_task.json',r['task_sha256'])
        a=load(BASELINE/name/'sitl_r2.json');b=load(TUNING/'config_020_full'/name/'fast.json')
        assert task['task_id']==name and task['family_id']==r['family_id']
        assert all(x['mission_id']==name and x['family_id']==r['family_id'] for x in (a,b))
        assert a['input_task_sha256']==r['task_sha256'] and a['status']=='COMPLETE'
        assert a['quality_eligible'] is True and a['run_status']=='completed'
        am=load(Path(a['source']['analysis'])/'manifest.json')
        assert am['run_id']==a['source']['run_id'] and am['family_id']==r['family_id']
        ra=TUNING/'config_020_full'/name/'run/analysis';rm=load(ra/'manifest.json');src=load(ra/'source.json')
        assert rm['run_id']==name and rm['family_id']==r['family_id'] and src['config']==config
        assert r['task_sha256'] in src['input_sha256'].values()
        p=paired_metrics(a,b);p.update(intent=r['intent'],flight_pattern=r['flight_pattern'])
        assert p==load(TUNING/'config_020_full'/name/'paired.json');pairs.append(p)
    check=evaluate(pairs,pairs)
    check['required_checks']['frozen_aggregate_exact']=check['aggregate']==frozen['tiers']['aggregate']
    check['required_checks']['all_282_identity_and_hash_verified']=len(pairs)==282
    sibling=PROJECT.parents[1]
    d0=sibling/'Simulation-fe-corner-audit/Multi-UAV SimpleGC'
    d0out=d0/'docs/v07/evidence/fe_int/corner_dwell_audit'
    manifest=load(d0out/'D0b_source_manifest.json');root=Path(manifest['external_output'])
    probe_inputs=[]
    for p in manifest['probes']:
        for f,h in p['input_sha256'].items():bind(Path(p['episode'])/f,h)
        entry={k:p[k] for k in ('probe_id','episode','group_id','agent_id','skeleton_id','probe_kind')}
        entry['historical_arms']={}
        for arm in ('A','B2'):
            result=load(root/p['probe_id']/arm/'result.json')
            for f,h in result['raw_sha256'].items():bind(root/p['probe_id']/arm/f,h)
            entry['historical_arms'][arm]=str(root/p['probe_id']/arm)
        probe_inputs.append(entry)
    assert len(probe_inputs)==7
    for f in ('probe_v07_fe_corner_fillet.py','probe_v07_fe_corner_cap.py','qc_v07_fe_corner_dwell.py'):bind(d0/'scripts'/f)
    bind(d0out/'D0_probe_selection.json',manifest['selection_sha256'])
    fe=load(PROJECT/'docs/v07/evidence/fe_int/sim_pilot/s15_sim_pilot_summary.json')
    original=[x for x in fe['skeletons'] if x['strict_pair']]; assert len(original)==30
    p2=load(sibling/'Simulation-fe-as/Multi-UAV SimpleGC/docs/v07/evidence/fe/p2_ab_comparison.json')
    recovered=[x for x in p2['public_draw_skeleton_detail'] if not x['a']['success'] and x['b']['success']
               and x['b']['approach_mode']=='multi_direction' and 'area_search' in x['methods']]
    assert len(recovered)==8
    desc=Path(p2['b_registration']['descriptors']);descriptors=load(desc/'private_skeleton_descriptors.json',p2['b_registration']['descriptors_sha256'])
    dr=load(desc/'registration.json');r4={}
    candidates=load(Path(dr['source_attempt'])/'candidates.json')
    by_index={x['candidate_index']:x for x in candidates}
    for row in dr['selected']:
        directory=Path(by_index[row['candidate_index']]['directory'])
        for f,h in row['source_sha256'].items():bind(directory/f,h)
    for x in original:
        sid=x['skeleton_id'];parent=Path(x['attempt'])/sid
        bind(parent/'skeleton.json')
        for mode in ('synchronous','sequential'):
            for f in ('task.json','public_scene.json','labels.json','truth_10hz.npz'):bind(parent/mode/f)
        r4[sid]=dict(skeleton_id=sid,sources=['FE_INT_30'],historical_attempt=x['attempt'])
    for x in recovered:
        sid=x['skeleton_id'];reg=p2['b_registration']['skeletons'][sid]
        for f,h in reg['file_sha256'].items():bind(Path(reg['directory'])/f,h)
        r4.setdefault(sid,dict(skeleton_id=sid,sources=[]))['sources'].append('P2_RECOVERED_8')
    chosen=set(r4);ds=[d for d in descriptors if d['skeleton_id'] in chosen]
    assert len(ds)==len(chosen)
    # Freeze the same descriptor_jobs source/scene bindings as the existing pipeline.
    from scripts.run_v07_s2_expansion import descriptor_jobs
    jobs=descriptor_jobs(desc,sorted(chosen),out/'R4_NOT_EXECUTED')
    for job in jobs:
        for value in job.values():
            if isinstance(value,(str,Path)) and Path(str(value)).is_file():bind(value)
    unit_modules=sorted(p.stem for p in (PROJECT/'tests').glob('test_fast_dynamics*.py'))
    unit_modules+=['test_v07_perf_tracker_snapshot','test_v07_m2_timing_rehearsal','test_v07_s2_revision_continuous','test_m3_r3_reference']
    for module in unit_modules:
        p=PROJECT/'tests'/f'{module}.py'
        if p.exists():bind(p)
    plan=dict(schema='m3_r3_amended_validation_plan_v1',status='FROZEN',baseline_commit=old['code_commit'],amendment_parent=START,
        previous_plan_sha256=history[str(REPORT/'R0_validation_plan.json')],input_files=list(inventory.values()),
        tuning_mission_ids=names,r2_baseline=check['metrics'],baseline_patterns=check['patterns'],
        rules=dict(original_tiers=True,total_tasks=282,success_minimum=.995,observation_success_minimum=.995,
            motion_overall_minimum=.98,motion_pattern_minimum=.95,na_rule='N/A only for original reference-known total == 0',
            preserve_reference_identities=True,numeric_tolerance=1e-9,non_regression_metrics=list(check['metrics'])),
        R1=dict(probes=probe_inputs,unit_modules=unit_modules,wall_limit_s=7200,
            required=['r2 arrays bitwise equal historical A','r3 arrays bitwise equal D0b B2','ordered original witnesses',
            'physical limits','curve geometry and primitive order','DwellRouteTracker observation hold','all registered tests','version and compatibility']),
        R2=dict(mission_ids=names,functionality_mission_ids=load(TUNING/'registration.json')['subset']['mission_ids'],
            wall_limit_s=28800,reuse_functionality_results_in_full_cohort=True,workers=4),
        R3=dict(p2_commit='fa7518b7fa850771c9d863b23d8893b27a343d5f',wall_limit_s=7200,
            regression_modules=sorted(set(unit_modules+[p.stem for p in (PROJECT/'tests').glob('test_v07*.py')] + ['test_v07_fe_area_search_precheck']))),
        R4=dict(skeletons=[r4[s] for s in sorted(r4)],descriptors=str(desc),jobs=jobs,original_count=30,recovered_count=8,
            distinct_count=len(r4),modes=['synchronous','sequential'],wall_limit_s=21600,min_separation_m=2.,workers=8),
        no_new_sitl=True,no_holdout_runs=True)
    check['required_checks']['fixed_downstream_inputs_registered']=len(probe_inputs)==7 and len(original)==30 and len(recovered)==8 and len(jobs)==len(chosen)
    import numpy,shapely
    env=dict(python=platform.python_version(),numpy=numpy.__version__,shapely=shapely.__version__)
    check['required_checks']['frozen_environment']=env==dict(python='3.12.3',numpy='2.5.3',shapely='2.0.7')
    import io,unittest
    sys.path.insert(0,str(PROJECT/'tests'));stream=io.StringIO()
    suite=unittest.defaultTestLoader.loadTestsFromNames(['test_m3_r3_r0_audit','test_m3_r3_gate_amendment'])
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (out/'unit_tests.txt').write_text(stream.getvalue(),encoding='utf-8')
    check['required_checks']['amendment_unit_tests']=result.wasSuccessful() and result.testsRun==10 and not result.skipped
    check['status']='PASS' if all(check['required_checks'].values()) else 'FAIL'
    amendment=dict(status='AUTHORIZED',reason='New all-pattern gate conflicted with original M3 applicability, not calibration data error',
        scope='Only original reference-known zero denominators are N/A; preserve all 282 tasks and all other gates',
        old_evidence_sha256=history,rule='total == 0: applicable=False, passed_check=None, status=N/A; otherwise all_task_rate>=0.95',
        overall=.98,success=.995,observation_success=.995,non_regression_tolerance=1e-9)
    for p,h in history.items():assert digest(p)==h
    atomic(out/'revalidated_audit.json',dict(check,environment=env,elapsed_wall_s=time.monotonic()-started,files=len(inventory)))
    atomic(out/'baseline_pairs.json',pairs)
    atomic(REPORT/'R0_gate_amendment.json',amendment)
    atomic(REPORT/'R0_validation_plan_amended.json',plan)
    plan_sha=digest(REPORT/'R0_validation_plan_amended.json')
    gate=dict(stage='R0',status=check['status'],result='R0_REVALIDATED_PASS' if check['status']=='PASS' else check['status'],
        input_sha256=plan_sha,code_commit=START,required_checks=check['required_checks'],metrics=check['metrics'],patterns=check['patterns'],
        evidence_paths=[str(out/'revalidated_audit.json'),str(out/'baseline_pairs.json')],
        evidence_sha256={str(out/f):digest(out/f) for f in ('revalidated_audit.json','baseline_pairs.json')},next_stage='R1' if check['status']=='PASS' else None)
    atomic(REPORT/'R0_revalidated_gate.json',gate)
    atomic(REPORT/'pipeline_state_R0_blocked.json',read(REPORT/'pipeline_state.json'))
    state=read(REPORT/'pipeline_state.json');state.update(status=check['status'],last_pass_stage='R0' if check['status']=='PASS' else None,
        current_stage='R0',next_stage=gate['next_stage'],plan_sha256=plan_sha,plan_path=str(REPORT/'R0_validation_plan_amended.json'))
    state['stages']['R0']=dict(status=check['status'],executed=True,gate=str(REPORT/'R0_revalidated_gate.json'))
    for s in ('R1','R2','R3','R4'):state['stages'][s]=dict(status='PENDING',executed=False)
    atomic(REPORT/'pipeline_state.json',state)
    print(json.dumps(dict(status=gate['result'],pairs=len(pairs),files=len(inventory),patterns=check['patterns'],r4=len(jobs))),flush=True)
    return 0 if check['status']=='PASS' else 2
if __name__=='__main__':raise SystemExit(main())
