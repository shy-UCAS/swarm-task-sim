"""Ten preregistered intent/approach cells, one paired skeleton each."""
import argparse,json,subprocess,sys,time,traceback
from collections import defaultdict
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from task_v07.io import read_json,save_json,sha
from task_v07.execution import FROZEN_SHA256
from task_v07.expansion.contracts import P0ContractError
from scripts.run_v07_s2_expansion import INFRA_ATTEMPT,new_attempt,descriptor_jobs
from scripts.run_v07_s2_episode_batch import run_jobs
from scripts.v07_s2_revision_diagnostics import INTENTS,NAMES,successful_pair


def choose_bones(planning):
    selected=[]
    for intent in INTENTS:
        for mode in ('same_direction','multi_direction'):
            candidates=[r for r in planning['skeletons'] if r['success'] and r['intent']==intent and r['approach_mode']==mode]
            if not candidates:raise ValueError('Quick A stop condition requires stopping before any flight')
            selected.append(min(candidates,key=lambda r:(int(r['group_count'])==1,r['skeleton_id'])))
    return selected


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--planning',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=8,choices=(6,7,8))
    args=parser.parse_args()
    planning=read_json(args.planning/'diagnostics.json')
    if planning['step']!=5 or planning['stop_required']:raise ValueError('Need completed passing step 5 quick A')
    if any(sha(PROJECT/k)!=v for k,v in planning['source_sha256'].items()):
        raise ValueError('Planner changed after quick A')
    selected=choose_bones(planning)
    out=new_attempt('attempt_s2_search_quick_b')
    print('OUTPUT',str(out),flush=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT,text=True).strip()
    registration={'source_attempt':str(INFRA_ATTEMPT),'source_planning':str(args.planning),
        'commit':commit,'config_sha256':FROZEN_SHA256,'workers':args.workers,
        'selection_rule':'prefer multi-task-group skeletons, then ascending skeleton ID; no outcome-dependent replacement',
        'selected':selected,'requests':20,'reused_flights':False}
    save_json(out/'registration.json',registration)
    start=time.perf_counter()
    try:rows=run_jobs(descriptor_jobs(INFRA_ATTEMPT,[r['skeleton_id'] for r in selected],out),args.workers)
    except P0ContractError as exc:
        save_json(out/'P0_STOP.json',{'reason':str(exc),'traceback':traceback.format_exc()})
        raise
    save_json(out/'episode_records.json',rows)
    by_bone=defaultdict(list)
    for row in rows:by_bone[row['skeleton_id']].append(row)
    cells=[];prediction_rows=[]
    for item in selected:
        sid=item['skeleton_id'];pair=by_bone[sid];search=read_json(out/sid/'candidate_search.json')
        failures=[]
        for row in pair:
            if row['path']:
                labels=read_json(out/row['path']/'labels.json')
                for gid,group in labels['task_groups'].items():
                    false=[k for k,v in group['result'].get('conditions',{}).items() if v is False]
                    if false:failures.append({'mode':row['mode'],'group_id':gid,'failed_conditions':false})
                if row.get('solo_overlay_prediction_error'):
                    prediction_rows.append({'skeleton_id':sid,'mode':row['mode'],**row['solo_overlay_prediction_error']})
            elif row.get('geometry_attempts'):
                failures.append({'mode':row['mode'],'rejections':row['geometry_attempts']})
        cells.append({'intent':item['intent'],'approach_mode':item['approach_mode'],'skeleton_id':sid,
            'group_count':int(item['group_count']),'complete_successful_pair':successful_pair(pair),
            'states':{r['mode']:{k:r.get(k) for k in ('state','task_result','quality_valid','audit_passed','reason')} for r in pair},
            'failures':failures,'solo_overlay_rejections':search.get('solo_overlay_rejections',0),
            'additional_overlay_rejections':search.get('additional_overlay_rejections',0)})
    data={'registration':registration,'cells':cells,'prediction_errors':prediction_rows,'wall_s':time.perf_counter()-start,
          'complete_pairs':sum(c['complete_successful_pair'] for c in cells),
          'stop_required':any(not c['complete_successful_pair'] for c in cells)}
    save_json(out/'diagnostics.json',data)
    lines=['## 快速检查 B：每个意图 × 逼近方式一对','',f'证据 `{out}`；选择已在试飞前登记。优先多任务组，其次骨架编号升序，不因结果失败更换样本。',
        f"完整成功配对 {data['complete_pairs']}/10；停止条件触发：{data['stop_required']}。",'',
        '| 意图 | 方式 | 骨架 | 任务组 | 完整成功配对 | 叠加新增拒绝组合数 |',
        '|---|---|---|---:|---|---:|']
    for c in cells:
        lines.append(f"| {NAMES[c['intent']]} | {c['approach_mode']} | {c['skeleton_id']} | {c['group_count']} | {c['complete_successful_pair']} | {c['additional_overlay_rejections']} |")
    lines+=['','| 骨架/时序 | 预测最小间距/m | 实测最小间距/m | 预测减实测/m | 最大位置误差/m |','|---|---:|---:|---:|---:|']
    for r in prediction_rows:
        lines.append(f"| {r['skeleton_id']}/{r['mode']} | {r['prediction']['minimum_m']:.6f} | {r['actual']['minimum_m']:.6f} | {r['minimum_error_predicted_minus_actual_m']:+.6f} | {r['position_error_max_m']:.6f} |")
    lines+=['','失败条件及各轮拒绝完整保存在上述 diagnostics.json；预检通过不替代实测审计。','']
    with (PROJECT/'docs/v07/S2_search_revision_report.md').open('a',encoding='utf-8',newline='\n') as f:f.write('\n'+'\n'.join(lines))
    print(json.dumps({'output':str(out),'complete_pairs':data['complete_pairs'],'stop_required':data['stop_required']}),flush=True)


if __name__=='__main__':main()
