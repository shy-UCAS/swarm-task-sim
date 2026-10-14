"""Planning-only geometry smoke; nominal timing is never used as truth or flight timing."""
import sys,json,time,math
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
import numpy as np
from scripts.run_v07_s2_expansion import descriptor_jobs,INFRA_ATTEMPT,new_attempt
from task_v07.expansion.pipeline import plan_group
from task_v07.expansion.role_planners import planner_for,PlanningInfeasible
from task_v07.expansion.formation_role_planners import Context,core_path_length
from task_v07.expansion.geometry_checks import planning_layer_interval_check
from task_v07.execution import departure_delays
from task_v07.labels import heading_span_deg
from task_v07.io import save_json
SKELS=[f'family_s12_{m}_ext_{s:03d}_regular'+('_diag_main_intrusion' if m.startswith('4d13') and s==4 else '')
       for m in ('4d13d93f9171c446','aa4c66be8e85d64d') for s in (1,2,3,4)]


def point_at_distance(points,distance):
    points=np.asarray(points)[:,:2]
    lengths=np.linalg.norm(np.diff(points,axis=0),axis=1);cum=np.r_[0.,np.cumsum(lengths)]
    distance=np.clip(distance,0.,cum[-1]);i=min(int(np.searchsorted(cum,distance,side='right')-1),len(lengths)-1)
    return points[i]+(distance-cum[i])/lengths[i]*(points[i+1]-points[i])


def worker(job):
    started=time.perf_counter();desc=job['descriptor'];group=desc['task_groups'][0]
    root=Path(job['out'])/desc['skeleton_id'];root.mkdir()
    try:
        sk,bundle,pre=plan_group(job['scene'],desc,group,planner_for(group['role'],group['execution_method']))
    except PlanningInfeasible as exc:
        row={'skeleton_id':desc['skeleton_id'],'status':'REJECT','category':exc.category,'detail':exc.detail,
             'diagnostic_only':desc.get('diagnostic_only',False),'source_skeleton_id':desc.get('source_skeleton_id')}
        save_json(root/'planning_rejection.json',row);print(json.dumps(row,ensure_ascii=False),flush=True);return row
    save_json(root/'skeleton.json',sk);save_json(root/'planning_checks.json',pre)
    from task_v07.expansion.pipeline import role_parameters
    ctx=Context(job['scene'],group,role_parameters(desc,group))
    kind='close_observation' if group['execution_method']=='close_observation' else group['role']
    headings={};nominal={}
    for a in group['members']:
        ref=sk['references'][a];points=np.asarray(ref['points_enu_m'])[:,:2]
        if kind=='monitoring':
            entry=np.asarray(ref['planned_orbit_entry_enu_m'][:2])
            index=int(np.argmin(np.linalg.norm(points-entry,axis=1)))
            distance=core_path_length(ctx,points,ref,kind,index)
        else:distance=core_path_length(ctx,points,ref,kind)
        nominal[a]=20.+distance/sk['cruise_speed_m_s']
        delta=point_at_distance(points,distance)-point_at_distance(points,distance-100.)
        headings[a]=float(math.degrees(math.atan2(delta[1],delta[0]))%360)
    nominal_plans=departure_delays(sk,nominal)
    interval=planning_layer_interval_check(bundle,nominal_plans,sk['cruise_speed_m_s'])
    row={'skeleton_id':desc['skeleton_id'],'status':pre['status'],'role':kind,'mode':sk['approach_mode'],
         'diagnostic_only':desc.get('diagnostic_only',False),'source_skeleton_id':desc.get('source_skeleton_id'),
         'plan_headings_deg':headings,'plan_approach_span_deg':heading_span_deg(list(headings.values())),
         'interval':interval,'timing_basis':'nominal path lengths only; real measured delays still require the full-route gate',
         'wall_s':time.perf_counter()-started,'precheck_failures':pre['failures']}
    save_json(root/'planning_smoke.json',row);print(json.dumps(row,ensure_ascii=False),flush=True);return row


def main():
    out=new_attempt('attempt_s2x_planning');print(f'OUTPUT {out}',flush=True)
    jobs=descriptor_jobs(INFRA_ATTEMPT,SKELS,out)
    with ProcessPoolExecutor(max_workers=6) as pool:rows=list(pool.map(worker,jobs))
    save_json(out/'summary.json',{'scope':'planning-only; no execution or truth labels','rows':rows})
    return 0

if __name__=='__main__':raise SystemExit(main())
