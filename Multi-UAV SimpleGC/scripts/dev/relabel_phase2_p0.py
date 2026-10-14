"""Recompute labels from saved truth into a fresh diagnostic attempt."""
from pathlib import Path
import sys,json,shutil
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT))
import numpy as np
from scripts.run_v07_s2_expansion import new_attempt
from scripts.audit_v07_s2_roles import audit_role_episode
from task_v07.labels import measure
from task_v07.io import save_json,sha

SOURCE=PROJECT.parent.parent/'SwarmData/v07_dataset/attempt_s2x_p1_20261014T093058Z_5860b099'


def main():
    out=new_attempt('attempt_s2x_p0_relabel');print(f'OUTPUT {out}',flush=True)
    rows=[]
    for source in sorted(SOURCE.glob('*/*/truth_10hz.npz')):
        src=source.parent
        old=json.loads((src/'labels.json').read_text(encoding='utf-8'))
        task=json.loads((src/'task.json').read_text(encoding='utf-8'))
        scene=json.loads((src/'public_scene.json').read_text(encoding='utf-8'))
        metrics=json.loads((src/'metrics.json').read_text(encoding='utf-8'))
        group=next(iter(old['task_groups'].values()));mode=group['assigned']['planned_coordination']
        plan=group['assigned']['timing']
        with np.load(source,allow_pickle=False) as truth:
            run={k:truth[k].copy() for k in ('time_us','p','v')}
            run['agent_ids']=truth['agent_ids'].tolist()
        run['execution_status']=metrics['execution_status']
        labels,frame=measure(scene,task,run,mode,group['assigned']['planned_batches'],timing_plan=plan)
        dest=out/src.relative_to(SOURCE);dest.mkdir(parents=True)
        for name in ('truth_10hz.npz','truth.csv','public_scene.json','task.json'):
            shutil.copy2(src/name,dest/name)
        save_json(dest/'labels.json',labels)
        np.savez_compressed(dest/'frame_labels.npz',**frame)
        audit=audit_role_episode(dest);save_json(dest/'independent_exact_audit.json',audit)
        facts={a:{'depth_m':ob['observed']['contribution'].get('max_depth_in_alert_m'),
                  'hold_s':ob['observed']['endpoint_hold_s'],'work_end_s':ob['observed']['work_end_s']}
               for a,ob in labels['agents'].items()}
        rows.append({'source':str(src),'path':dest.relative_to(out).as_posix(),'role':task['role'],
                     'method':task['execution_method'],'mode':mode,'audit_status':audit['status'],
                     'region_difference_count':audit['region_difference_count'],
                     'target_difference_count':audit['target_difference_count'],
                     'fact_difference_count':audit['event_or_metric_difference_count'],
                     'uncovered_conditions':audit['uncovered_conditions'],'facts':facts,
                     'source_truth_sha256':sha(source),'copied_truth_sha256':sha(dest/'truth_10hz.npz')})
        if audit['status']!='PASS':
            save_json(out/'summary.json',{'status':'P0_STOP','rows':rows})
            print(json.dumps({'status':'P0_STOP','episode':str(dest),'witnesses':audit['event_or_metric_witnesses']},ensure_ascii=False),flush=True)
            return 1
    summary={'status':'PASS','source_attempt':str(SOURCE),'episodes':len(rows),'rows':rows,
             'audit_difference_count':sum(r['fact_difference_count']+r['region_difference_count']+r['target_difference_count'] for r in rows),
             'hold_witness_correction':'prior diagnostic counted frames/10; consistent exported-time duration is (frames-1)/10, 0.1s lower',
             'training_eligible':False,'scope':'relabelled saved truth, no new execution and no source overwrite'}
    save_json(out/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'},ensure_ascii=False,indent=1),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
