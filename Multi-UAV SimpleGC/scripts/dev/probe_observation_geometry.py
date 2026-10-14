"""Diagnostic only: reduce observation polygon vertices without changing its station."""
import sys,json,math
from pathlib import Path
import numpy as np
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
from scripts.run_v07_s2_expansion import new_attempt
from task_v07.execution import execute
from task_v07.labels import measure
from task_v07.io import save_json

def main():
    source=Path(sys.argv[1]);steps=int(sys.argv[2]);sk=json.loads((source/'skeleton.json').read_text());scene=json.loads((source/'synchronous/public_scene.json').read_text())
    out=new_attempt('attempt_s2x_observation_probe');print(f'OUTPUT {out}',flush=True)
    speed=sk['cruise_speed_m_s'];radius=max(12.,1.1*max(speed**2/3.75,math.sqrt(speed**3/14.)))
    for a,ref in sk['references'].items():
        station=np.array(ref['observation_point_enu_m'][:2]);points=np.array(ref['points_enu_m']);indices=np.flatnonzero(np.isclose(np.linalg.norm(points[:,:2]-station,axis=1),radius,atol=1e-6,rtol=0))
        assert np.all(np.diff(indices)==1),(a,indices)
        first,last=int(indices[0]),int(indices[-1]);laps=int(sys.argv[3]) if len(sys.argv)>3 else round((last-first)/48);alpha=math.atan2(*(points[first,:2]-station)[::-1]);angles=alpha+np.arange(steps*laps+1)*2*math.pi/steps
        ring=np.c_[station+radius*np.c_[np.cos(angles),np.sin(angles)],np.full(len(angles),points[0,2])]
        ref['points_enu_m']=np.vstack([points[:first],ring,points[last+1:]]).tolist()
    sk['diagnostic_only']=True;save_json(out/'skeleton.json',sk)
    agent=sorted(sk['members'])[0];run=execute(sk,{a:0. for a in sk['members']},only_agent=agent);labels,_=measure(scene,sk,run,'unassigned_measurement')
    np.savez_compressed(out/'truth_10hz.npz',**{k:run[k] for k in ('time_us','p','v','a','agent_ids')})
    report={'diagnostic_only':True,'source':str(source),'steps_per_lap':steps,'laps':laps,'result':labels['agents'][agent],'execution':run['execution_status']}
    save_json(out/'diagnosis.json',report);print(json.dumps(report,ensure_ascii=False),flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
