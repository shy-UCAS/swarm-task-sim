"""Recheck measured group work intervals on immutable exported pilot trajectories."""
from pathlib import Path
import argparse
import sys
import numpy as np

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT))
from task_v07.io import read_json,save_json
from scripts.run_v07_s2_expansion import new_attempt
from scripts.run_v07_s2_episode_batch import group_truncations


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('attempts',nargs='+',type=Path)
    args=parser.parse_args()
    out=new_attempt('attempt_s2x_truncation_recheck')
    print(f'OUTPUT {out}',flush=True)
    results=[]
    for attempt in args.attempts:
        for row in read_json(attempt/'episode_records.json'):
            if row['path'] is None:
                continue
            root=attempt/row['path']
            with np.load(root/'truth_10hz.npz',allow_pickle=False) as loaded:
                run={key:loaded[key].copy() for key in ('time_us','p','v')}
                run['agent_ids']=loaded['agent_ids'].tolist()
            run['execution_status']=read_json(root/'source.json')['execution_status']
            checks=group_truncations(read_json(root/'public_scene.json'),read_json(root/'task.json'),run,read_json(root/'labels.json'))
            results.append({'episode_id':row['episode_id'],'source':str(root),'checks':checks})
    counts={state:sum(check['status']==state for row in results for check in row['checks'].values())
            for state in ('PASS','FAIL','not_run')}
    save_json(out/'recheck.json',{'episodes':len(results),'counts':counts,'rows':results})
    print(counts,flush=True)


if __name__=='__main__':
    main()
