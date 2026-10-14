"""Standalone diagnostic flight: never adds a dataset episode or view."""
import sys,json,math
from pathlib import Path
import numpy as np
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
from scripts.run_v07_s2_expansion import descriptor_jobs,INFRA_ATTEMPT,new_attempt
from task_v07.expansion.formation_role_planners import Context,MonitoringPlanner
from task_v07.expansion.pipeline import role_parameters
from task_v07.execution import execute
from task_v07.labels import measure
from task_v07.io import save_json

def main():
    source=Path(sys.argv[1]);old=json.loads((source/'skeleton.json').read_text())
    out=new_attempt('attempt_s2x_monitor_probe');print(f'OUTPUT {out}',flush=True)
    job=descriptor_jobs(INFRA_ATTEMPT,[old['skeleton_id']],out)[0]
    group=job['descriptor']['task_groups'][0];ctx=Context(job['scene'],group,role_parameters(job['descriptor'],group))
    lead=np.array(old['formation']['blocks'][0]['collection_point_enu_m'][:2])-ctx.center
    angle=math.atan2(lead[1],lead[0]);r=old['monitoring']['orbit_radius_m'];g=ctx.geometry
    extent=g['radius_m'] if g['type']=='Circle' else np.linalg.norm(np.array(g['vertices_m'])-ctx.center,axis=1).max()
    index=round((r-extent-ctx.zones['alert']['offset_m']-10.)/20.)
    result,reason=MonitoringPlanner()._attempt_radius(ctx,angle,index)
    if result is None:print(reason);return 1
    sk={**old,**result['template']};sk['diagnostic_only']=True
    for a,points in result['routes'].items():sk['references'][a]['points_enu_m']=points
    save_json(out/'skeleton.json',sk)
    agent=sorted(sk['members'])[0];run=execute(sk,{a:0. for a in sk['members']},only_agent=agent)
    labels,_=measure(job['scene'],sk,run,'unassigned_measurement')
    np.savez_compressed(out/'truth_10hz.npz',**{k:run[k] for k in ('time_us','p','v','a','agent_ids')})
    obs=labels['agents'][agent]['observed'];core=obs['core_event']['frame_index'];c=np.array(sk['monitoring']['orbit_center_enu_m']);phi=np.unwrap(np.arctan2(run['p'][:,0,1]-c[1],run['p'][:,0,0]-c[0]));t=run['time_us']/1e6
    mask=(t>t[core]+20)&(t<obs['work_end_s']-20)
    rate=np.polyfit(t[mask],phi[mask],1)[0]
    report={'diagnostic_only':True,'source_attempt':str(source),'agent':agent,'execution':run['execution_status'],'period_s':2*math.pi/abs(rate),'nominal_period_s':2*math.pi*r/sk['cruise_speed_m_s'],'core_phase_deg':float(np.degrees(phi[core])%360),'planned_phase_deg':float(np.degrees(sk['references'][agent]['planned_orbit_phase_rad'])%360),'observed':obs}
    save_json(out/'diagnosis.json',report);print(json.dumps(report,ensure_ascii=False),flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
