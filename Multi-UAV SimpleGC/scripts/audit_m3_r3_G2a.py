"""G-2a gate inventory and read-only replay of already available evidence."""
import json,sys,subprocess
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PROJECT))
from scripts.audit_m3_r3_r0 import REPORT,DATA,read,digest,atomic,CONFIG_SHA
from scripts.run_m3_r3_r1 import PLAN
from scripts.tune_fast_dynamics_m3 import tiers
from scripts.m3_r3_gates import evaluate,values
from swarm_sim.fast_dynamics.calibration import aggregate_pairs
ATTEMPT=DATA/'fast_dynamics/m3/m3_r3_r1_revalidate04'


def classify_probe(result):
    checks=dict(result['checks']);diagnostics={}
    if result['probe_id']=='probe_05':
        if 'precision' in checks:diagnostics['precision']=checks.pop('precision')
        diagnostics['absolute_precision']=result['precision']['absolute_status']
        diagnostics['relative_by_phase']=result['precision'].get('relative_by_phase')
    return dict(status='PASS' if all(checks.values()) else 'FAIL',hard_checks=checks,diagnostics=diagnostics)


def inventory():
    rows=[]
    def add(stage,id,category,rule,source,disposition='HARD',reason=None):
        rows.append(dict(stage=stage,original_gate_id=id,category=category,disposition=disposition,rule=rule,source=source,reason=reason))
    source='scripts/revalidate_m3_r3_r1.py::probe_worker'
    for id,rule in [('input_hash','Input group hash equals frozen history; execution cannot mutate input'),('physical','Original physical_checks all true; limits unchanged'),('ordered_nodes','All internal original node indices witnessed exactly once and in order'),('no_scene_violation','No original sampled forbidden/obstacle/world violation')]:add('R1',id,'a',rule,source)
    for version,category in [('r2','b'),('r3','c')]:
        for id in ('bitwise_arrays','geometry_and_caps_exact','witnesses_exact','dwell_exact','observation_exact','low_speed_exact','tracking_exact'):
            add('R1',version+'.'+id,category,'Exact comparison with historical '+('A' if version=='r2' else 'B2')+'; no tolerance added',source)
    add('R1','precision.absolute.probe_01_02_03_04_06_07','a','Original reference tracking tube <= 0.5 m, no threshold change',source)
    for phase in ('approach','dwell','departure','terminal_stop'):
        for metric in ('max_m','p99_m'):
            add('R1','precision.probe_05.'+phase+'.'+metric,None,'r3 <= r2 + 1e-9 m',source,'DIAGNOSTIC','G-2a.1: changed corner geometry invalidates r2 numerical nonregression as acceptance; report all values')
    add('R1','precision.absolute.probe_05',None,'Absolute tracking tube 0.5 m; both arms historically exceed','R1_validation_plan_amended.json','KNOWN_LIMITATION','Explicit G-2a.1 exclusion; preserve measured ~1.785 m and absolute FAIL')
    for id,rule in [('R1_REGRESSION_DELTA_ZERO','All original 209 tests execute; exact four known signatures only; any other failure/error/skip blocks'),('NEW_GATE_TESTS','All additional harness tests pass'),('legacy_audit','Exact legacy IDs and source/log hashes, no module wildcard'),('source_unchanged','Registered source hashes stable during execution'),('old_fail_evidence_unchanged','Historical FAIL/BLOCKED evidence hashes unchanged'),('r2_config','Frozen r2 config retains '+CONFIG_SHA),('all14','Seven prescribed r2 and seven r3 results complete and satisfy their applicable checks')]:
        add('R1',id,'a',rule,'scripts/revalidate_m3_r3_r1.py::launch')
    add('R1','version_and_compatibility','a','Explicit selector, artifact identity, original geometry and dwell API contracts','tests/test_m3_r3_reference.py')
    add('R2','tiers().hard.passed','d','Original M3 tiers, exact applicable/N/A semantics unchanged','scripts/tune_fast_dynamics_m3.py::tiers')
    pairs=read(DATA/'fast_dynamics/m3/m3_r3_r0_revalidate01/baseline_pairs.json')
    for check in tiers(pairs,282)['hard']['checks']:
        add('R2','tiers.hard.'+check['name'],'d',dict(minimum=check['minimum'],applicable=check['applicable'],zero_known='N/A only for frozen reference-known total zero'),'scripts/tune_fast_dynamics_m3.py::tiers')
    for id,rule in [('cohort_complete','All fixed 282 task identities present and comparable; original 70-task functionality subset first'),('reference_identity_preserved','Mission/family/pattern and SITL reference identity/hash unchanged; cannot disguise missing known references as N/A'),('no_P0','No P0ContractError or invalid physical/export contract'),('source_unchanged','Registered code/config/input fingerprints stable')]:add('R2',id,'a',rule,'R0_validation_plan_amended.json; original task sections 3/5/8')
    for id in values(aggregate_pairs(pairs)):
        add('R2',id,None,'Original r3 metric <= r2 + 1e-9 comparison retained numerically','scripts/m3_r3_gates.py::evaluate','DIAGNOSTIC','G-3 and G-2a: report values and worst 10 deteriorated tasks per metric; not acceptance')
    for id,rule in [('candidate_version_provenance','Record distinct candidate version/config/source hashes; r2 identity unchanged'),('P2_scope','P2 algorithm change limited to construction.py::ingress_issues as authorized'),('integration_regression','Run frozen 49-module P0/P1/P2/r3 integration suite; preserve exact known-test treatment'),('source_unchanged','Source/config fingerprints stable in each validation run')]:add('R3',id,'a',rule,'Original task section 6; R0_validation_plan_amended.json.R3')
    add('R3','default_r2_replay','b','Default r2 still reproduces historical archives exactly','Original task section 6.7')
    for id,rule in [('original30_strict_pairs','All original 30 skeletons meet existing synchronous/sequential strict pair contracts and required M1 outcomes'),('no_P0ContractError','No P0ContractError'),('independent_audit','All existing independent audits pass'),('minimum_separation','Every retained episode >= 2 m'),('no_forbidden_violation','No original forbidden-region violation'),('M1_required_role_conditions','Preserve original role-specific M1 criteria and thresholds'),('source_unchanged','Registered source/config fingerprint stable during run')]:add('R4',id,'a',rule,'Original task section 7; G-4; task_v07/expansion/contracts.py::validate_pair')
    add('R4','recovered8_strict_pairs',None,'Report each of eight recovered P2 skeletons and first failed stage/reason','G-4','DIAGNOSTIC','Previously authorized G-4 keeps additional eight outcomes as measurement')
    return rows,pairs


def run():
    target=REPORT/'gate_audit_G2a.json'
    if target.exists():raise FileExistsError('Audit already exists; do not overwrite')
    old_files=[REPORT/'R1_revalidated_gate_attempt04.json',REPORT/'R1_revalidation_attempt04_report.md',ATTEMPT/'summary.json']
    protected={str(p):digest(p) for p in old_files};rows,pairs=inventory();plan=read(PLAN)
    r1=[];r2_self=[];pending=[]
    for probe in plan['R1']['probes']:
        a=read(ATTEMPT/probe['probe_id']/'r2/result.json')
        # r2-to-r2: exact byte equality of all recorded arrays is already established
        # by attempt04 versus historical A; each contract is re-applied below.
        r2_self.append(dict(probe_id=probe['probe_id'],result=classify_probe(a),evidence=str(ATTEMPT/probe['probe_id']/'r2/result.json')))
        for version in ('r2','r3'):
            path=ATTEMPT/probe['probe_id']/version/'result.json'
            if not path.exists():pending.append(dict(stage='R1',probe_id=probe['probe_id'],version=version,reason='Not executed after prior authorized stop'));continue
            result=read(path);r1.append(dict(probe_id=probe['probe_id'],version=version,evaluation=classify_probe(result),evidence=str(path),sha256=digest(path)))
    original_gate=read(ATTEMPT/'summary.json')
    r2=tiers(pairs,282);identity=evaluate(pairs,pairs,nonregression=False)
    fe=read(PROJECT/'docs/v07/evidence/fe_int/sim_pilot/s15_sim_pilot_summary.json')
    original_ids={x['skeleton_id'] for x in plan['R4']['skeletons'] if 'FE_INT_30' in x['sources']}
    fe_rows=[x for x in fe['skeletons'] if x['skeleton_id'] in original_ids]
    r4checks=dict(original30_complete=len(fe_rows)==30 and {x['skeleton_id'] for x in fe_rows}==original_ids,
        original30_strict_pairs=all(x['strict_pair'] for x in fe_rows),
        minimum_separation=all(len(x['minimum_separation_m'])==2 and min(x['minimum_separation_m'])>=2 for x in fe_rows),
        independent_audit=fe['failure_stage_counts']['审计']==0,
        M1_role_conditions=fe['failure_stage_counts']['M1 角色判据']==0,
        source_unchanged=fe['attempt']['runtime_sha256_stable'])
    failures=[dict(stage='R1',probe_id=x['probe_id'],version=x['version'],failed=[k for k,v in x['evaluation']['hard_checks'].items() if not v]) for x in r1 if x['evaluation']['status']=='FAIL']
    if not r2['hard']['passed']:failures.append(dict(stage='R2',checks=r2['hard']))
    if not all(identity['required_checks'].values()):failures.append(dict(stage='R2',checks=identity['required_checks']))
    if not all(r4checks.values()):failures.append(dict(stage='R4',checks=r4checks))
    if original_gate['regression']['status']!='PASS':failures.append(dict(stage='R1',gate='regression'))
    for key in ('source_unchanged','old_fail_evidence_unchanged','r2_config'):
        if not original_gate['required_checks'][key]:failures.append(dict(stage='R1',gate=key))
    for p,h in protected.items():assert digest(p)==h
    result=dict(schema='m3_r3_gate_audit_G2a_v1',status='FAIL' if failures else 'PASS',scope='Gate classification and dry run of AVAILABLE frozen evidence; not future R1/R2/R3/R4 acceptance',
        current_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT,text=True).strip(),
        parent_plan_sha256=digest(PLAN),previous_rules_sha256=digest(REPORT/'R1_validation_plan_amended.json'),
        allowed_hard_categories={'a':'absolute physical/API/data/provenance/audit/role contracts; regression tests enforce those existing contracts','b':'r2 historical exact compatibility','c':'r3 fixed B2 probe exact reproduction','d':'original M3 tiers().hard with original N/A'},
        gates=rows,ambiguities=[],hard_failures=failures,
        dryrun=dict(r2_against_r2=r2_self,attempt04=r1,R1_tests=original_gate['regression'],R2_original_tiers=r2,R2_reference_identity=identity['required_checks'],R4_existing_r2_30=r4checks,
                    R3='No integrated candidate exists yet; use available R1 r2 compatibility and contract regression evidence for dry run, actual P2 integration tests remain pending',pending=pending),
        execution_controls=dict(existing_budgets={k:plan[k]['wall_limit_s'] for k in ('R1','R2','R3','R4')},
            no_new_sitl=True,no_holdout_access=True,no_production_freeze=True,stop_on_merge_conflict=True,
            scope='Existing execution/authorization controls preserved; not numerical acceptance gates'),
        original_fail_files_sha256=protected,remaining_R1_harness_repairs_new_authorization=2,
        complete_inputs=dict(R1_probes=plan['R1']['probes'],R1_modules=plan['R1']['unit_modules'],R2=plan['R2'],R3=plan['R3'],R4_skeletons=plan['R4']['skeletons']))
    atomic(target,result)
    print(json.dumps(dict(status=result['status'],gates=len(rows),diagnostics=sum(x['disposition']!='HARD' for x in rows),hard_failures=failures,pending=pending)),flush=True)
    return 0 if result['status']=='PASS' else 2

if __name__=='__main__':raise SystemExit(run())
