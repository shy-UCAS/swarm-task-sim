"""One single-group and one multiple-group abort, each tied to a measured source."""
from pathlib import Path
import argparse
import sys
import time
import traceback

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT))
from task_v07.io import read_json,save_json
from task_v07.expansion.contracts import P0ContractError
from scripts.run_v07_s2_expansion import new_attempt,descriptor_jobs,INFRA_ATTEMPT
from scripts.run_v07_s2_abort import run_aborts


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',nargs='+',type=Path,required=True)
    args=parser.parse_args()
    out=new_attempt('attempt_s2x_abort_pilot')
    print(f'OUTPUT {out}',flush=True)
    descriptors=read_json(INFRA_ATTEMPT/'private_skeleton_descriptors.json')
    aborts={d['family_id']:d for d in descriptors if d['subset']=='aborted'}
    jobs=[]
    for source in args.sources:
        rows=read_json(source/'episode_records.json')
        row=next(r for r in sorted(rows,key=lambda r:r['episode_id']) if r['mode']=='synchronous'
                 and r['intent']=='penetration' and r['state']=='generated' and r['task_result']=='success')
        job=descriptor_jobs(INFRA_ATTEMPT,[row['skeleton_id']],out)[0]
        jobs.append({'scene':job['scene'],'source_descriptor':job['descriptor'],
                     'descriptor':aborts[row['family_id']],'source_record':row,
                     'source_attempt':str(source),'out':str(out)})
    save_json(out/'registration.json',{'scope':'abort development pilot; every prefix tied to measured regular synchronous source',
                                      'workers':2,'source_episodes':[j['source_record']['episode_id'] for j in jobs],
                                      'source_attempts':[str(p) for p in args.sources]})
    started=time.perf_counter()
    try:
        rows=run_aborts(jobs,2)
    except P0ContractError as exc:
        save_json(out/'P0_STOP.json',{'reason':str(exc),'traceback':traceback.format_exc()})
        raise
    save_json(out/'episode_records.json',rows)
    save_json(out/'summary.json',{'wall_s':time.perf_counter()-started,'episodes':rows})
    for row in rows:
        print({k:row.get(k) for k in ('episode_id','state','reason','task_result','abort_observation_valid',
                                     'main_group_observed_coordination','minimum_separation_m')},flush=True)


if __name__=='__main__':
    main()
