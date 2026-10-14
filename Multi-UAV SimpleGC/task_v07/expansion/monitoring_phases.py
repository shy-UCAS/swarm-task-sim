"""Finite common-geometry candidates for both immutable timing patterns.

The period range is a planning estimate only.  Solo calibration, full-route
spacing checks and actual 10 Hz revisit measurements remain authoritative.
No split, batch, departure delay, family speed or acceptance limit is changed.
"""
import math
import numpy as np
from task_v07.execution import departure_delays
from task_v07.planning import seed_for


def shared_phase_candidates(ctx,radius):
    ids=sorted(ctx.group['members']);n=len(ids)
    skeleton={'members':ids,'column_seed':ctx.params.get('column_seed',ctx.params['planning_seed']),
              'sync_window_s':10.}
    plans=departure_delays(skeleton,{a:0. for a in ids})
    times=np.array([[plans[mode]['target_event_times_s'][a] for a in ids]
                    for mode in ('synchronous','sequential')])
    times-=times.min(axis=1)[:,None]
    nominal=2*math.pi*radius/ctx.speed
    # Frozen M3 diagnostic: 24-chord orbit takes about 1.10 nominal periods.
    # This is candidate scoring, never substituted for an observed duration.
    periods=nominal*1.10*np.array([.975,1.,1.025])
    rotation=1. if seed_for(ctx.family.get('sampling_seed',0),f'monitoring-clock-slot:{ctx.slot}')%2 else -1.
    rng=np.random.default_rng(seed_for(ctx.params.get('geometry_seed',ctx.params['planning_seed']),
                                     f'monitoring-common-phases:{radius:.6f}'))
    def evaluate(values):
        phase=np.sort((values[:,None,None,:]-rotation*2*math.pi*times[None,:,None,:]
                       /periods[None,None,:,None])%(2*math.pi),axis=-1)
        gaps=np.diff(np.concatenate([phase,phase[...,:1]+2*math.pi],axis=-1),axis=-1)
        maximum=(gaps*periods[None,None,:,None]/(2*math.pi)).max(axis=(1,2,3))
        # Keep station phases apart in both patterns, including period uncertainty.
        minimum=gaps.min(axis=(1,2,3))*radius
        return maximum+np.maximum(0.,20.-minimum)*10.
    results=[]
    for restart in range(4):
        population=rng.uniform(0.,2*math.pi,(192,n));cost=evaluate(population)
        for _ in range(900):
            best=population[cost.argmin()]
            a=population[rng.integers(len(population),size=len(population))]
            b=population[rng.integers(len(population),size=len(population))]
            mutant=(best+.7*(a-b))%(2*math.pi)
            trial=np.where(rng.random(population.shape)<.8,mutant,population)
            trial_cost=evaluate(trial);take=trial_cost<cost
            population[take]=trial[take];cost[take]=trial_cost[take]
        index=int(cost.argmin());phases=population[index]-population[index,0]
        results.append({'phases':dict(zip(ids,phases.tolist())),
            'estimated_max_interval_s':float(cost[index]),'estimated_period_range_s':periods.tolist(),
            'allowed_interval_s':1.5*nominal/n,'basis':'planning estimate only; measured 10 Hz audit is required'})
    return sorted(results,key=lambda item:item['estimated_max_interval_s'])
