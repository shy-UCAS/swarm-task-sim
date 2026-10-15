"""Read-only probes of saved S2 evidence; does not run or edit the generator."""
from pathlib import Path
import sys, json, math, hashlib, time
from collections import Counter
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.run_v07_s2_expansion import descriptor_jobs, INFRA_ATTEMPT
from task_v07.expansion.pipeline import role_parameters
from task_v07.expansion.formation_role_planners import Context
from task_v07.expansion.monitoring_phases import shared_phase_candidates
from task_v07.execution import departure_delays
from task_v07.planning import seed_for

DATA = ROOT.parents[1] / 'SwarmData/v07_dataset'
ATTEMPT = DATA / 'attempt_s2x_final_20261015T053115Z_a3b834e8'
OUTPUT = Path(__file__).with_name('evidence.json')

def read(p):
    return json.loads(p.read_text(encoding='utf-8'))

def minimum(p, times, ids):
    result = {'minimum_m': float('inf')}
    for i in range(len(ids)):
        for j in range(i+1, len(ids)):
            d = np.linalg.norm(p[:, i]-p[:, j], axis=1)
            k = int(d.argmin())
            if float(d[k]) < result['minimum_m']:
                result = {'minimum_m': float(d[k]), 'pair': [ids[i], ids[j]], 'time_s': float(times[k])/1e6}
    return result

def phase_score(ctx, radius, phases):
    ids = sorted(ctx.group['members'])
    plan = departure_delays({'members': ids, 'column_seed': ctx.params['column_seed'], 'sync_window_s': 10.}, {a: 0. for a in ids})
    times = np.array([[plan[m]['target_event_times_s'][a] for a in ids] for m in ('synchronous','sequential')])
    times -= times.min(axis=1)[:,None]
    nominal = 2*math.pi*radius/ctx.speed
    periods = nominal*1.10*np.array([.975,1.,1.025])
    rotation = 1. if seed_for(ctx.family.get('sampling_seed',0),f'monitoring-clock-slot:{ctx.slot}')%2 else -1.
    values = np.array([phases[a] for a in ids])
    phase = np.sort((values[None,None,:]-rotation*2*math.pi*times[:,None,:]/periods[None,:,None])%(2*math.pi),axis=-1)
    gaps = np.diff(np.concatenate([phase,phase[...,:1]+2*math.pi],axis=-1),axis=-1)
    maximum = float((gaps*periods[None,:,None]/(2*math.pi)).max())
    min_arc = float(gaps.min()*radius)
    return {'max_interval_s': maximum, 'min_arc_spacing_m': min_arc, 'score_s': maximum+max(0.,20.-min_arc)*10., 'allowed_s': 1.5*nominal/len(ids)}

def main():
    output = {'scope': 'Offline evidence probes only. No flights, route modification, label changes, or external evidence writes.',
              'source_attempt': str(ATTEMPT), 'phase_probe_selection': 'First saved nominal_revisit_geometry_infeasible candidate of the first monitoring skeleton in each family, in sorted skeleton order. No selection by optimizer outcome.',
              'phase_probe_limit': 'Passing the unchanged nominal phase screen proves only phase-screen feasibility at this saved radius; it does not establish route or actual episode success.',
              'solo_probe_limit': 'Time-shifted solo positions approximate joint execution; shared engine event boundaries can cause residual differences. Actual joint audit remains authoritative.'}
    ids = sorted(p.name for p in ATTEMPT.glob('*_regular') if p.is_dir())
    jobs = {j['descriptor']['skeleton_id']: j for j in descriptor_jobs(INFRA_ATTEMPT, ids, Path(__file__).parent)}
    rows, phase_jobs, seen = [], [], set()
    for sid in ids:
        desc = jobs[sid]['descriptor']; search = read(ATTEMPT/sid/'candidate_search.json')
        groups = desc['task_groups']
        eligible = search['selection']['eligible_candidates']; feasible = search['selection']['feasible_candidates']
        rows.append({'skeleton_id':sid, 'intent':desc['base_intent'], 'approach':desc['common_draw']['approach_mode'],
                     'group_count':len(groups), 'group_attempt_counts':search['group_attempt_counts'],
                     'attempted_candidates':search['attempted_candidates'], 'feasible':feasible, 'eligible':eligible,
                     'rejection_reasons':search['rejection_reasons'],
                     'actual_calibration_rounds':search.get('actual_single_agent_calibration_rounds'),
                     'group_roles':{g['group_id']:g['role'] for g in groups},
                     'group_sizes':{g['group_id']:len(g['members']) for g in groups}})
        if desc['family_id'] not in seen:
            for c in search['candidates']:
                if c.get('reason') == 'nominal_revisit_geometry_infeasible':
                    gid = c['stage'].split(':')[-1]
                    group = next(g for g in groups if g['group_id'] == gid)
                    phase_jobs.append((sid, group, c['candidate_index'], c['draws_by_group'][gid]))
                    seen.add(desc['family_id']); break
    output['candidate_search_rows'] = rows
    output['candidate_summary'] = {'skeleton_count':len(rows),
        'feasible_but_zero_eligible':[r['skeleton_id'] for r in rows if r['feasible']>0 and r['eligible']==0],
        'by_group_count':{str(n):{'bones':sum(r['group_count']==n for r in rows),
            'at_least_one_eligible':sum(r['group_count']==n and r['eligible']>0 for r in rows),
            'group_attempts':[r['group_attempt_counts'] for r in rows if r['group_count']==n]} for n in sorted({r['group_count'] for r in rows})}}
    print('CANDIDATES', json.dumps(output['candidate_summary'],ensure_ascii=False), flush=True)
    output['solo_alignment'] = []
    for sid in ids:
        directory = ATTEMPT/sid
        if not (directory/'timing_calibration.json').is_file(): continue
        timing = read(directory/'timing_calibration.json')
        geom = directory/f"geometry_{timing.get('calibration_round',0):02d}"
        # The selected calibration has the same skeleton saved at root and geometry_NN.
        matches = [p for p in directory.glob('geometry_*') if (p/'timing_calibration.json').is_file() and read(p/'timing_calibration.json') == timing]
        if len(matches) != 1:
            raise RuntimeError(f'Cannot unambiguously match selected calibration {sid}: {matches}')
        geom = matches[0]
        for mode in ('synchronous','sequential'):
            truth = directory/mode/'truth_10hz.npz'
            if not truth.is_file(): continue
            with np.load(truth) as z:
                times,p,agent_ids = z['time_us'],z['p'],z['agent_ids'].tolist()
            delays = timing['timing_plans'][mode]['departure_delays_s']
            solos = {}
            predicted_end_us = 0
            for i,a in enumerate(agent_ids):
                with np.load(geom/f'single_agent_{a}.npz') as z:
                    if z['agent_ids'].tolist()!=[a]: raise RuntimeError('Agent mismatch')
                    solo_t,solo_p = z['time_us'],z['p'][:,0]
                solos[a] = (solo_t,solo_p)
                predicted_end_us = max(predicted_end_us,int(solo_t[-1])+round(delays[a]*1e6))
            grid = np.arange(0,predicted_end_us+1,100000,dtype=np.int64)
            projected = np.empty((len(grid),len(agent_ids),3))
            projected_at_actual = np.empty_like(p)
            for i,a in enumerate(agent_ids):
                solo_t,solo_p = solos[a]
                shifted = grid-round(delays[a]*1e6)
                for d in range(3):
                    projected[:,i,d] = np.interp(shifted, solo_t, solo_p[:,d])
                    projected_at_actual[:,i,d] = np.interp(times-round(delays[a]*1e6),solo_t,solo_p[:,d])
            error = np.linalg.norm(projected_at_actual-p,axis=2)
            row = {'skeleton_id':sid,'mode':mode,'calibration_directory':geom.name,
                'prediction_grid_basis':'10 Hz from zero to max(solo end + departure delay); independent of joint trajectory and labels',
                'predicted_end_s':float(predicted_end_us)/1e6, 'actual_end_s':float(times[-1])/1e6,
                'projected_minimum':minimum(projected,grid,agent_ids), 'actual_minimum':minimum(p,times,agent_ids),
                'position_error_p95_m':float(np.percentile(error,95)), 'position_error_max_m':float(error.max())}
            output['solo_alignment'].append(row)
    align = output['solo_alignment']
    output['solo_alignment_summary'] = {'episodes':len(align), 'actual_under_2m':sum(r['actual_minimum']['minimum_m']<2 for r in align),
        'projected_under_2m':sum(r['projected_minimum']['minimum_m']<2 for r in align),
        'projected_under_10m':sum(r['projected_minimum']['minimum_m']<10 for r in align),
        'actual_under_10m':sum(r['actual_minimum']['minimum_m']<10 for r in align),
        'maximum_position_error_m':max(r['position_error_max_m'] for r in align),
        'maximum_pair_minimum_error_m':max(abs(r['actual_minimum']['minimum_m']-r['projected_minimum']['minimum_m']) for r in align)}
    print('SOLO_SUMMARY',json.dumps(output['solo_alignment_summary']),flush=True)
    print('COLLISION',json.dumps([r for r in align if r['actual_minimum']['minimum_m']<2]),flush=True)
    output['phase_witnesses'] = []
    for sid, group, candidate, draw in phase_jobs:
        ctx = Context(jobs[sid]['scene'],group,role_parameters(jobs[sid]['descriptor'],group))
        radius = draw['orbit_radius_m']; start = time.perf_counter()
        old = phase_score(ctx,radius,draw['orbit_phases_rad'])
        result = shared_phase_candidates(ctx,radius)[0]
        new = phase_score(ctx,radius,result['phases'])
        row = {'skeleton_id':sid,'group_id':group['group_id'],'candidate_index':candidate,'radius_m':radius,
            'original':old,'optimized':new,'passes_unchanged_phase_gate':new['score_s']<=new['allowed_s'],
            'optimized_phases_rad':result['phases'],'wall_s':time.perf_counter()-start}
        output['phase_witnesses'].append(row)
        print('PHASE',json.dumps({k:v for k,v in row.items() if k!='optimized_phases_rad'}),flush=True)
    output['source_code_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
        [ROOT/'task_v07/expansion/monitoring_phases.py',ROOT/'task_v07/expansion/continuous_geometry.py',Path(__file__)]}
    OUTPUT.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('OUTPUT',str(OUTPUT),flush=True)

if __name__=='__main__': main()
