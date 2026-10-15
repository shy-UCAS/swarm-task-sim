"""Registered 60-skeleton planning checks for search revision steps 2--5."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import subprocess,sys,time,json
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from scripts.run_v07_s2_expansion import INFRA_ATTEMPT,descriptor_jobs,new_attempt
from scripts.run_v07_s2_revision_smoke import worker,matrices
from scripts.v07_s2_revision_diagnostics import collect,NAMES
from task_v07.io import read_json,save_json,sha


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--step',type=int,choices=(2,3,4,5),required=True)
    parser.add_argument('--workers',type=int,default=8,choices=(6,7,8))
    args=parser.parse_args()
    started=time.perf_counter()
    descriptors=[d for d in read_json(INFRA_ATTEMPT/'private_skeleton_descriptors.json') if d['subset']=='regular' and not d.get('diagnostic_only')]
    if len(descriptors)!=60:raise ValueError('Expected 60 registered skeletons')
    out=new_attempt(f'attempt_s2_search_step{args.step}_planning')
    print('OUTPUT',str(out),flush=True)
    files=sorted((PROJECT/'task_v07/expansion').glob('*.py'))+[Path(__file__)]
    registration={'step':args.step,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT,text=True).strip(),
        'source_sha256':{str(p.relative_to(PROJECT)):sha(p) for p in files},'workers':args.workers,
        'source_attempt':str(INFRA_ATTEMPT),'source_descriptor_sha256':sha(INFRA_ATTEMPT/'private_skeleton_descriptors.json'),
        'registered_skeletons':60,'single_agent_calibration':False,'joint_simulation':False}
    save_json(out/'registration.json',registration)
    jobs=descriptor_jobs(INFRA_ATTEMPT,[d['skeleton_id'] for d in descriptors],out)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        records=[f.result() for f in as_completed([pool.submit(worker,j) for j in jobs])]
    records.sort(key=lambda r:r['skeleton_id'])
    for row in records:
        search=read_json(out/row['skeleton_id']/'candidate_search.json')
        row.update(rejection_class_counts=search.get('rejection_class_counts',{}),
                   group_search_metrics=search.get('group_search_metrics',{}),termination=search.get('termination'))
    if len(records)!=60 or any(r['attempted_candidates']<200 or r['solo_flights_run'] for r in records):raise ValueError('Incomplete smoke')
    if any(sha(PROJECT/k)!=v for k,v in registration['source_sha256'].items()):raise ValueError('Source changed during smoke')
    current=matrices(records)
    zeros=[c for c in current['approach_mode'] if c['successful']==0]
    old=collect(INFRA_ATTEMPT.parent/'attempt_s2x_final_20261014T164338Z_4f85aaa3')
    previous=collect(INFRA_ATTEMPT.parent/'attempt_s2x_final_20261015T053115Z_a3b834e8')
    data={**registration,'source_attempt':str(out),'skeletons':records,'matrices':current,
          'total_wall_s':time.perf_counter()-started,'simulation_runs':0,'zero_cells':zeros,
          'stop_required':args.step==5 and bool(zeros),
          'historical_measured_matrices':{'before':old['matrices'],'previous':previous['matrices']}}
    save_json(out/'diagnostics.json',data)
    lines=[f'## 第 {args.step} 步后快速检查 A','',f"证据 `{out}`；源提交 `{registration['source_commit']}`，另保存所有规划源码 SHA256。",
           f"纯规划可行 {sum(r['success'] for r in records)}/60；墙钟 {data['total_wall_s']:.3f} s；仿真 0。历史列为实测完整成功配对，本轮列为规划可行。",'',
           '| 意图 | 逼近方式 | 修订前实测 | 上一轮实测 | 本轮规划 |','|---|---|---:|---:|---:|']
    for cell in current['approach_mode']:
        prior=[next(c for c in v['matrices']['approach_mode'] if c['intent']==cell['intent'] and c['value']==cell['value']) for v in (old,previous)]
        lines.append(f"| {NAMES[cell['intent']]} | {cell['value']} | {prior[0]['successful']}/{cell['registered']} | {prior[1]['successful']}/{cell['registered']} | {cell['successful']}/{cell['registered']} |")
    lines+=['',f"第 5 步停止条件触发：{data['stop_required']}。",'']
    report=PROJECT/'docs/v07/S2_search_revision_report.md'
    with report.open('a',encoding='utf-8',newline='\n') as f:f.write('\n'+'\n'.join(lines))
    print(json.dumps({'output':str(out),'feasible':sum(r['success'] for r in records),'wall_s':data['total_wall_s'],'stop_required':data['stop_required'],'zero_cells':[(c['intent'],c['value']) for c in zeros]}),flush=True)

if __name__=='__main__':main()
