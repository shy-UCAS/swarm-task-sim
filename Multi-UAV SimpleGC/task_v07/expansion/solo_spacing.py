"""Pre-execution whole-episode spacing from saved solo 10 Hz positions."""
from pathlib import Path
from itertools import combinations
import numpy as np
from .contracts import P0ContractError
from task_v07.unified.config import load_generator

MODES=('synchronous','sequential')
STEP_US=100000
WARNING_M=load_generator()["overlay"]["min_separation_m"]


def load_saved_solos(directory,agent_ids):
    result={}
    for agent in agent_ids:
        with np.load(Path(directory)/f'single_agent_{agent}.npz',allow_pickle=False) as saved:
            result[agent]={k:saved[k].copy() for k in ('time_us','p','agent_ids')}
    validate_solos(result)
    return result


def validate_solos(solos):
    if len(solos)<2:raise P0ContractError('Spacing prediction requires at least two registered agents')
    for agent,run in solos.items():
        times=np.asarray(run['time_us']);points=np.asarray(run['p'])
        ids=np.asarray(run['agent_ids']).tolist()
        if (ids!=[agent] or times.ndim!=1 or len(times)<2 or times[0]!=0
            or not np.all(np.diff(times)==STEP_US) or points.shape!=(len(times),1,3)
            or not np.isfinite(points).all()):
            raise P0ContractError(f'Invalid saved solo trajectory for {agent}')


def shifted_positions(solos,delays,times=None):
    """Use solo settle/dwell/terminal data as saved; add only release delay."""
    ids=sorted(solos)
    if set(delays)!=set(ids):raise P0ContractError('Solo delay IDs differ from trajectory IDs')
    shift={}
    for agent,delay in delays.items():
        if not np.isfinite(delay) or delay<0 or abs(delay*10-round(delay*10))>1e-7:
            raise P0ContractError('Departure delay is not on the nonnegative 10 Hz grid')
        shift[agent]=round(delay*1e6)
    if times is None:
        end=max(int(solos[a]['time_us'][-1])+shift[a] for a in ids)
        times=np.arange(0,end+1,STEP_US,dtype=np.int64)
    positions=np.empty((len(times),len(ids),3))
    for col,agent in enumerate(ids):
        run=solos[agent]
        for axis in range(3):
            positions[:,col,axis]=np.interp(times-shift[agent],run['time_us'],run['p'][:,0,axis])
    return np.asarray(times),positions,ids


def minimum_spacing(times,positions,ids):
    result={'minimum_m':None,'closest_pair':None,'frames_checked':len(times)}
    for i,j in combinations(range(len(ids)),2):
        distances=np.linalg.norm(positions[:,i]-positions[:,j],axis=1)
        frame=int(distances.argmin());distance=float(distances[frame])
        if result['minimum_m'] is None or distance<result['minimum_m']:
            result.update(minimum_m=distance,closest_pair={'agents':[ids[i],ids[j]],
                'frame_index':frame,'t_s':float(times[frame])/1e6})
    result['below_warning']=result['minimum_m'] is not None and result['minimum_m']<WARNING_M
    return result


def solo_interval_check(solos,plans):
    validate_solos(solos)
    result={'warning_threshold_m':WARNING_M,'sample_hz':10.,
        'method':'saved solo 10 Hz trajectories shifted by true departure delays',
        'scope':'all agents, all groups, from time zero through latest shifted solo end; initial/final positions held',
        'initial_settle_added_again':False}
    for mode in plans:
        t,p,ids=shifted_positions(solos,plans[mode]['departure_delays_s'])
        result[mode]={**minimum_spacing(t,p,ids),'predicted_end_s':float(t[-1])/1e6}
    return result


def prediction_error(solos,plan,actual,prediction):
    times,projected,ids=shifted_positions(solos,plan['departure_delays_s'],np.asarray(actual['time_us']))
    if set(actual['agent_ids'])!=set(ids):raise P0ContractError('Joint run IDs differ from solo prediction')
    actual_p=np.asarray(actual['p'])[:,[actual['agent_ids'].index(a) for a in ids]]
    observed=minimum_spacing(times,actual_p,ids)
    error=np.linalg.norm(projected-actual_p,axis=2)
    return {'prediction':prediction,'actual':observed,
        'minimum_error_predicted_minus_actual_m':prediction['minimum_m']-observed['minimum_m'],
        'position_error_p95_m':float(np.percentile(error,95)),
        'position_error_max_m':float(error.max()),
        'actual_end_s':float(times[-1])/1e6,
        'ten_metre_classification_matches':prediction['below_warning']==observed['below_warning']}
