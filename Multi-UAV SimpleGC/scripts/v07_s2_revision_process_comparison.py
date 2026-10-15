"""Two registered skeletons, including multiple groups, independently at 1/2 workers."""
from pathlib import Path
from task_v07.io import read_json,save_json
from task_v07.expansion.contracts import P0ContractError
from scripts.run_v07_s2_expansion import descriptor_jobs,INFRA_ATTEMPT,compare_episode_dirs
from scripts.run_v07_s2_episode_batch import run_jobs


def choose(descriptors,records):
    by_id={d['skeleton_id']:d for d in descriptors if d['subset']=='regular' and not d.get('diagnostic_only')}
    pairs={sid:[r for r in records if r['skeleton_id']==sid] for sid in by_id}
    def rank(sid):
        pair=pairs[sid]
        kept=len(pair)==2 and all(r['state']=='generated' and r.get('quality_valid') and r.get('audit_passed') for r in pair)
        return not kept,sid
    multi=min((sid for sid,d in by_id.items() if len(d['task_groups'])>1),key=rank)
    singles=[sid for sid,d in by_id.items() if len(d['task_groups'])==1 and sid!=multi]
    second=min(singles or [sid for sid in by_id if sid!=multi],key=rank)
    return [multi,second]


def compare_process_counts(attempt,records):
    attempt=Path(attempt)
    selected=choose(read_json(INFRA_ATTEMPT/'private_skeleton_descriptors.json'),records)
    roots=[];runs=[]
    for workers in (1,2):
        root=attempt/f'process_{workers}';root.mkdir();roots.append(root)
        save_json(root/'registration.json',{'workers':workers,'selected_skeletons':selected,
            'selection':'prefer retained pairs; always one registered multi-group skeleton and one other skeleton'})
        rows=run_jobs(descriptor_jobs(INFRA_ATTEMPT,selected,root),workers);runs.append(rows)
        save_json(root/'episode_records.json',rows)
    differences=[];generated_pairs=0;planning_only=[]
    names=('candidate_pool.json','candidate_search.json','skeleton.json','timing_calibration.json',
           'planning_checks.json','planning_layer_interval.json','geometry_history.json','planning_rejection.json')
    for sid in selected:
        left,right=[root/sid for root in roots]
        existing=[]
        for name in names:
            a,b=(left/name).exists(),(right/name).exists()
            if a!=b:differences.append({'skeleton_id':sid,'file':name,'class':'content','path':'<missing file>'})
            elif a:existing.append(name)
        differences += [{**d,'skeleton_id':sid,'scope':'skeleton'} for d in compare_episode_dirs(left,right,existing,[],[])]
        for mode in ('synchronous','sequential'):
            rows=[next(r for r in run if r['skeleton_id']==sid and r['mode']==mode) for run in runs]
            if tuple(rows[0].get(k) for k in ('state','reason','path')) != tuple(rows[1].get(k) for k in ('state','reason','path')):
                differences.append({'skeleton_id':sid,'mode':mode,'file':'episode_records.json','path':'state/reason/path','class':'content'})
            if any(row.get('path') is None for row in rows):
                planning_only.append({'skeleton_id':sid,'mode':mode,'state':rows[0]['state'],'reason':rows[0].get('reason')})
                continue
            generated_pairs+=1
            diffs=compare_episode_dirs(roots[0]/rows[0]['path'],roots[1]/rows[1]['path'],
                ['task.json','labels.json','prefix_labels.json','source.json','manifest.json','public_scene.json',
                 'independent_exact_audit.json','policy_geometry_audit.json','truncation_check.json'],
                ['truth_10hz.npz','model_input.npz','frame_labels.npz'],['truth.csv','observations.csv'])
            for d in diffs:
                if d['file']=='independent_exact_audit.json' and d['path'].split('.')[-1]=='directory':d['class']='metadata:path'
                differences.append({**d,'skeleton_id':sid,'mode':mode,'scope':'episode'})
    count=sum(d['class']=='content' for d in differences)
    result={'status':'PASS' if count==0 else 'P0_STOP','skeleton_ids':selected,'workers':[1,2],
            'includes_multiple_groups':True,'content_difference_count':count,'differences':differences,
            'generated_episode_comparisons':generated_pairs,'planning_only_comparisons':planning_only,
            'reused_pilot_trajectories':False}
    save_json(attempt/'process_comparison.json',result)
    if count:raise P0ContractError('One/two worker runs changed generated content')
    return result
