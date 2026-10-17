"""M3-r3 candidate gates: original metrics and approved reference applicability."""
from swarm_sim.fast_dynamics.calibration import aggregate_pairs
from scripts.tune_fast_dynamics_m3 import tiers


def values(agg):
    return dict(total_duration_abs_relative_median=agg['duration_absolute_relative_error']['task']['median'],
        total_duration_abs_relative_p95=agg['duration_absolute_relative_error']['task']['p95'],
        observe_duration_abs_relative_median=agg['phase_absolute_relative_error'].get('p01_observe',{}).get('task',{}).get('median'),
        turn_min_speed_abs_difference_median=agg['turn_minimum_speed_m_s']['absolute_difference']['task']['median'],
        lateral_task_p95_median_m=agg['lateral_task_p95_m']['task']['median'])


def evaluate(pairs, baseline, *, nonregression=True):
    expected={r['mission_id']:r for r in baseline}
    got={r['mission_id']:r for r in pairs}
    complete=len(pairs)==len(got)==len(expected) and set(got)==set(expected)
    identity=complete and all(got[k]['family_id']==r['family_id'] and got[k]['flight_pattern']==r['flight_pattern']
        and all(got[k]['motion_slots'][c]['reference']==r['motion_slots'][c]['reference'] for c in ('truth','observation'))
        for k,r in expected.items())
    aggregate=aggregate_pairs(pairs); original=tiers(pairs,len(baseline))
    checks=dict(cohort_complete=complete, reference_identity_preserved=identity,
                original_m3_hard=original['hard']['passed'])
    for k in ('success','observation_success'):
        checks[k]=aggregate[k]['all_task_rate'] is not None and aggregate[k]['all_task_rate']>=.995
    for c in ('truth','observation'):
        d=aggregate['motion_reference_known'][c]
        checks[c+'.motion_overall']=d['all_task_rate'] is not None and d['all_task_rate']>=.98
    patterns=[]
    for pattern in sorted({r['flight_pattern'] for r in baseline}):
        a=aggregate_pairs([r for r in baseline if r['flight_pattern']==pattern])
        b=aggregate_pairs([r for r in pairs if r['flight_pattern']==pattern])
        for c in ('truth','observation'):
            original_total=a['motion_reference_known'][c]['total']
            d=b['motion_reference_known'][c]
            # A disappeared formerly known stratum is a data failure, never N/A.
            applicable=original_total>0
            consistent=d['total']==original_total and identity
            passed=None if not applicable and consistent else bool(consistent and d['all_task_rate'] is not None and d['all_task_rate']>=.95)
            status='N/A' if passed is None else 'PASS' if passed else 'FAIL'
            patterns.append(dict(flight_pattern=pattern,channel=c,task_count=a['tasks'],
                reference_known=original_total,candidate_reference_known=d['total'],
                applicable=applicable,passed_check=passed,status=status,all_task_rate=d['all_task_rate']))
            checks[f'{c}.motion.{pattern}']=passed is not False
    baseline_values=values(aggregate_pairs(baseline)); candidate_values=values(aggregate)
    if nonregression:
        for k,v in baseline_values.items():
            checks[k]=v is not None and candidate_values[k] is not None and candidate_values[k]<=v+1e-9
    return dict(status='PASS' if all(checks.values()) else 'FAIL', required_checks=checks,
        patterns=patterns,metrics=candidate_values,r2_metrics=baseline_values,aggregate=aggregate,original_tiers=original)
