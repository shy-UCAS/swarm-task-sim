"""Supplemental geometry-only probes; does not execute flights or edit sources."""
from probe import *
from task_v07.geometry import geometry_facts
from task_v07.expansion.continuous_geometry import draw_role
from task_v07.expansion.monitoring_deployment import monitoring_candidate

def main():
    evidence=read(OUTPUT)
    ids=[r['skeleton_id'] for r in evidence['candidate_search_rows'] if r['intent']=='游弋监视']
    # Descriptor intent strings are recorded verbatim; role presence is the robust lookup.
    if len(ids)!=12:
        ids=[r['skeleton_id'] for r in evidence['candidate_search_rows'] if r['skeleton_id'].split('_ext_')[-1][:3] in ('002','007')]
    jobs={j['descriptor']['skeleton_id']:j for j in descriptor_jobs(INFRA_ATTEMPT,ids,Path(__file__).parent)}
    output={'scope':'Geometry-only probes. Original proposals and role criteria remain unchanged.',
            'ring_limit':'Separate the original combined rejection by target annulus versus the remaining original route clearance/policy gate. This is not a proof of global infeasibility.',
            'rings':[], 'phase_followup':[]}
    for sid in ids:
        job=jobs[sid]; groups=job['descriptor']['task_groups']
        contexts={g['group_id']:Context(job['scene'],g,role_parameters(job['descriptor'],g)) for g in groups if g['role']=='monitoring'}
        counts=Counter(); observed={}
        search=read(ATTEMPT/sid/'candidate_search.json')
        for c in search['candidates']:
            for gid,draw in c['draws_by_group'].items():
                if gid not in contexts or 'orbit_radius_m' not in draw: continue
                ctx=contexts[gid]; radius=draw['orbit_radius_m']
                samples=ctx.center+radius*np.c_[np.cos(np.linspace(0,2*math.pi,129)),np.sin(np.linspace(0,2*math.pi,129))]
                distance=geometry_facts(ctx.geometry,samples)['signed_distance_m']
                inner=bool(np.any(distance<=ctx.zones['alert']['offset_m']+5.))
                outer=bool(np.any(distance>=ctx.zones['warning']['offset_m']-5.))
                if inner or outer:
                    bucket='target_annulus_'+('inner_and_outer' if inner and outer else 'inner' if inner else 'outer')
                    if c['reason']!='closed_orbit_cannot_clear_exact_restrictions_and_alert_policy': raise RuntimeError('Gate mismatch')
                elif c['reason']=='closed_orbit_cannot_clear_exact_restrictions_and_alert_policy':
                    bucket='remaining_route_clearance_or_forbidden_policy'
                else: bucket='passed_ring_gate'
                counts[bucket]+=1
                observed.setdefault(bucket,[]).append(radius)
        row={'skeleton_id':sid,'counts':dict(counts),'radius_min_max_by_bucket':{k:[min(v),max(v)] for k,v in observed.items()}}
        output['rings'].append(row)
        print('RING',json.dumps(row),flush=True)
    for witness in evidence['phase_witnesses']:
        sid=witness['skeleton_id']; job=jobs[sid]
        group=next(g for g in job['descriptor']['task_groups'] if g['group_id']==witness['group_id'])
        ctx=Context(job['scene'],group,role_parameters(job['descriptor'],group))
        result,reason,draw=draw_role(ctx,witness['candidate_index'])
        if reason!='nominal_revisit_geometry_infeasible': raise RuntimeError(f'Original draw replay mismatch: {sid} {reason}')
        start=time.perf_counter()
        phase={'phases':witness['optimized_phases_rad'],'estimated_max_interval_s':witness['optimized']['score_s'],
               'allowed_interval_s':witness['optimized']['allowed_s'],'basis':'offline unchanged prior phase search witness'}
        result,reason=monitoring_candidate(ctx,draw['entry_rotation_rad'],draw['orbit_radius_m'],phase_diagnostic=phase)
        row={'skeleton_id':sid,'candidate_index':witness['candidate_index'],'original_reason':'nominal_revisit_geometry_infeasible',
             'next_reason_after_only_phase_change':reason,'role_geometry_constructed':result is not None,'wall_s':time.perf_counter()-start}
        output['phase_followup'].append(row)
        print('FOLLOWUP',json.dumps(row),flush=True)
    output['ring_totals']=dict(sum((Counter(r['counts']) for r in output['rings']),Counter()))
    output['script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    path=Path(__file__).with_name('geometry_evidence.json')
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('TOTALS',json.dumps(output['ring_totals']),flush=True)
    print('OUTPUT',str(path),flush=True)

if __name__=='__main__': main()
