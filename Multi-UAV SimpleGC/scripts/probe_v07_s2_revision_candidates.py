"""Six role examples for task C integration; not the all-60 task G smoke."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json
import sys
import time

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from scripts.run_v07_s2_expansion import INFRA_ATTEMPT, descriptor_jobs, new_attempt
from task_v07.expansion.candidate_search import episode_candidate_pool
from task_v07.io import read_json, save_json


def probe(job):
    start=time.perf_counter()
    pool,report=episode_candidate_pool(job['scene'],job['descriptor'])
    root=Path(job['out'])/job['descriptor']['skeleton_id']
    root.mkdir()
    save_json(root/'candidate_search.json',report)
    if pool:save_json(root/'selected_skeleton.json',pool[0]['skeleton'])
    result={'skeleton_id':job['descriptor']['skeleton_id'],'roles':[(g['role'],g['execution_method']) for g in job['descriptor']['task_groups']],
            'candidates':report['attempted_candidates'],'eligible':len(pool),'reasons':report['rejection_reasons'],
            'wall_s':time.perf_counter()-start}
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result


def main():
    descriptors=[d for d in read_json(INFRA_ATTEMPT/'private_skeleton_descriptors.json') if d['subset']=='regular']
    chosen=[]
    for role,method in [('transit','transit'),('reconnaissance','close_observation'),('reconnaissance','area_search'),
                        ('monitoring','monitoring'),('feint','feint'),('intrusion','intrusion')]:
        matches=[d for d in descriptors if any(g['role']==role and g['execution_method']==method for g in d['task_groups'])]
        if not matches:raise ValueError(f'Missing registered role: {role}/{method}')
        chosen.append(min(matches,key=lambda d:(len(d['task_groups']),len(d['agent_ids']),d['skeleton_id']))['skeleton_id'])
    out=new_attempt('attempt_s2_revision_C_geometry_probe')
    print('OUTPUT',out,flush=True)
    jobs=descriptor_jobs(INFRA_ATTEMPT,sorted(set(chosen)),out)
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows=list(pool.map(probe,jobs))
    save_json(out/'probe_summary.json',{'scope':__doc__,'rows':rows})


if __name__=='__main__':main()
