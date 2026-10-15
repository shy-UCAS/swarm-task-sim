"""Reconstruct an interrupted quick-B report from completed evidence only; no flights."""
from collections import Counter,defaultdict
from pathlib import Path
import argparse,json,sys
import numpy as np
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from task_v07.io import read_json,save_json,sha
from task_v07.geometry import geometry_facts
from scripts.run_v07_s2_expansion import INFRA_ATTEMPT,DEFAULT_DATA
from scripts.run_v07_s2_episode_batch import rejected
from scripts.v07_s2_revision_diagnostics import successful_pair,NAMES


def feint_plan_witness(root,group,scene):
    facility=next(e for e in scene['entities'] if e['id']==group['target_id'])
    zones={e['layer']:e for e in scene['entities'] if e.get('facility_id')==group['target_id'] and e.get('layer')}
    alert,protected=(zones[k]['offset_m'] for k in ('alert','protected'))
    result=[]
    for agent in group['members']:
        points=np.asarray(group['references'][agent]['points_enu_m'])[:,:2]
        sampled=np.concatenate([a+np.linspace(0,1,max(2,int(np.ceil(np.linalg.norm(b-a)))+1))[:,None]*(b-a) for a,b in zip(points,points[1:])])
        distance=geometry_facts(facility['geometry'],sampled)['signed_distance_m']
        inside=(distance<=alert)&(distance>protected)
        fraction=float((alert-distance[inside]).max()/(alert-protected)) if inside.any() else 0.
        result.append({'agent_id':agent,'sampled_planned_maximum_depth_fraction':fraction,
            'planned_station_fraction':group['continuous_geometry_draw']['feint_depth_fraction_by_agent'][agent],
            'path_sampling_max_spacing_m':1.,'basis':'read-only interpolation of saved planned polylines, not a new simulation'})
    return result


def historical(path):
    rows=read_json(path/'episode_records.json');regular=[r for r in rows if not r.get('aborted') and not r.get('diagnostic_only')]
    ids=sorted({r['skeleton_id'] for r in regular})
    valid=[r for r in regular if r['state']=='generated' and r.get('quality_valid') and r.get('audit_passed')]
    return {'regular_skeletons':len(ids),'regular_requests':len(regular),
        'generated_regular':sum(r['state'] in ('generated','generation_error') for r in regular),
        'retained_regular':len(valid),'complete_pairs':sum(successful_pair([r for r in regular if r['skeleton_id']==sid]) for sid in ids),
        'retained_task_failures':sum(r['task_result']=='failure' for r in valid),
        'generation_errors':sum(r['state']=='generation_error' for r in regular),
        'planning_rejected_requests':sum(r['state']=='infeasible' for r in regular),
        'abort_requests':sum(bool(r.get('aborted')) for r in rows)}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--attempt',type=Path,required=True)
    args=parser.parse_args();out=args.attempt
    stop=read_json(out/'FAST_B_STOP.json');registration=read_json(out/'registration.json')
    if stop['status']!='QUICK_B_STOP':raise ValueError('Expected explicit quick-B stopping receipt')
    if (out/'episode_records.json').exists() or (out/'diagnostics.json').exists():raise FileExistsError('Never overwrite aggregate evidence')
    descriptors={d['skeleton_id']:d for d in read_json(INFRA_ATTEMPT/'private_skeleton_descriptors.json')}
    rows=[];cells=[];prediction_rows=[];all_rounds=[];sources={str(out/'FAST_B_STOP.json'):sha(out/'FAST_B_STOP.json')}
    for selected in registration['selected']:
        sid=selected['skeleton_id'];root=out/sid;descriptor=descriptors[sid]
        final=read_json(root/'planning_rejection.json') if (root/'planning_rejection.json').exists() else None
        rejected_rows=rejected(descriptor,final['history']) if final else []
        saved_rounds=[];additional=0;failures=[];plans=[]
        for directory in sorted(root.glob('geometry_*')):
            timing_path=directory/'timing_calibration.json'
            if not timing_path.is_file():continue
            timing=read_json(timing_path);sources[str(timing_path)]=sha(timing_path)
            item={'skeleton_id':sid,'geometry_directory':directory.name,'calibration_round':timing['calibration_round'],
                  'candidate_index':timing['candidate_index'],
                  'unobserved_core_agents':[a for a,v in timing['core_times_s'].items() if v is None],
                  'unfinished_hold_agents':[a for a,v in timing['completed_hold_times_s'].items() if v is None]}
            for filename,key in (('planning_rejection.json','rejection'),('planning_layer_interval.json','old_interval'),('solo_overlay_interval.json','overlay')):
                if (directory/filename).is_file():
                    item[key]=read_json(directory/filename);sources[str(directory/filename)]=sha(directory/filename)
            old_pass='old_interval' in item and all(not item['old_interval'][m]['below_warning'] for m in ('synchronous','sequential'))
            item['additional_overlay_rejection']=old_pass and 'overlay' in item and any(item['overlay'][m]['below_warning'] for m in ('synchronous','sequential'))
            additional+=int(item['additional_overlay_rejection']);saved_rounds.append(item)
        all_rounds.extend(saved_rounds)
        pair=[]
        for mode in ('synchronous','sequential'):
            metrics=root/mode/'metrics.json'
            if metrics.is_file():
                row=read_json(metrics);sources[str(metrics)]=sha(metrics)
                labels=read_json(root/mode/'labels.json');sources[str(root/mode/'labels.json')]=sha(root/mode/'labels.json')
                if not row.get('audit_passed'):raise ValueError('A saved metrics row is not audited')
                for agent,data in labels['agents'].items():
                    false=[key for key,value in data['result']['conditions'].items() if value is False]
                    if false:failures.append({'mode':mode,'agent_id':agent,'assigned':data['assigned'],
                        'failed_conditions':false,'observed_contribution':data['observed']['contribution']})
                prediction_rows.append({'skeleton_id':sid,'mode':mode,**row['solo_overlay_prediction_error']})
            elif final:
                row=next(r for r in rejected_rows if r['mode']==mode)
                row.update(reason=final.get('category',row['reason']),rejection_detail=final.get('detail',row['rejection_detail']))
            else:
                row={'episode_id':sid+'_'+mode,'skeleton_id':sid,'family_id':descriptor['family_id'],'intent':descriptor['base_intent'],
                    'mode':mode,'approach_mode':descriptor['common_draw']['approach_mode'],'group_count':len(descriptor['task_groups']),
                    'state':'pending','reason':'interrupted_by_quick_B_stop','path':None,'task_result':None,'quality_valid':None,'audit_passed':None,
                    'partial_raw_directory':str(root/mode) if (root/mode).exists() else None,'aborted':False,'diagnostic_only':False}
            pair.append(row);rows.append(row)
        complete=successful_pair(pair)
        definite_failure=any(r['state'] in ('infeasible','generation_error') or (r.get('audit_passed') and r.get('task_result')=='failure') for r in pair)
        state='successful_pair' if complete else 'confirmed_failure' if definite_failure else 'interrupted_incomplete'
        if failures and (root/'skeleton.json').exists():
            skeleton=read_json(root/'skeleton.json')
            scene=read_json(next((root/m/'public_scene.json') for m in ('synchronous','sequential') if (root/m/'metrics.json').is_file()))
            failed_groups={r['assigned']['task_group'] for r in failures}
            for gid in failed_groups:
                group=skeleton['group_skeletons'][gid]
                if group['role']=='feint':plans.extend(feint_plan_witness(root,group,scene))
        cell={'intent':selected['intent'],'approach_mode':selected['approach_mode'],'skeleton_id':sid,
            'group_count':int(selected['group_count']),'complete_successful_pair':complete,'status':state,
            'states':{r['mode']:{k:r.get(k) for k in ('state','task_result','quality_valid','audit_passed','reason')} for r in pair},
            'completed_calibration_rounds':len(saved_rounds),'started_calibration_rounds':len(list(root.glob('geometry_*/skeleton.json'))),
            'additional_overlay_rejections':additional,'solo_overlay_rejections':additional,
            'failures':failures,'final_rejection':final,'planned_feint_depth_witnesses':plans}
        cells.append(cell)
    generated=[r for r in rows if r.get('audit_passed')]
    summary={'registered_cells':10,'registered_requests':20,'completed_audited_joint_episodes':len(generated),
        'complete_successful_pairs':sum(c['complete_successful_pair'] for c in cells),
        'confirmed_failed_cells':sum(c['status']=='confirmed_failure' for c in cells),
        'interrupted_incomplete_cells':sum(c['status']=='interrupted_incomplete' for c in cells),
        'interrupted_requests':sum(r['state']=='pending' for r in rows),
        'final_rejected_requests':sum(r['state']=='infeasible' for r in rows),
        'completed_calibration_rounds':len(all_rounds),'additional_overlay_rejections':sum(c['additional_overlay_rejections'] for c in cells),
        'observed_generation_errors':sum(r['state']=='generation_error' for r in rows),
        'maximum_absolute_minimum_prediction_error_m':max(abs(r['minimum_error_predicted_minus_actual_m']) for r in prediction_rows),
        'mean_absolute_minimum_prediction_error_m':float(np.mean([abs(r['minimum_error_predicted_minus_actual_m']) for r in prediction_rows])),
        'maximum_position_error_m':max(r['position_error_max_m'] for r in prediction_rows),
        'ten_metre_classification_matches':sum(r['ten_metre_classification_matches'] for r in prediction_rows)}
    data={'registration':registration,'stop_receipt':stop,'partial_after_explicit_stop':True,'summary':summary,
        'cells':cells,'prediction_errors':prediction_rows,'calibration_rounds':all_rounds,
        'complete_pairs':summary['complete_successful_pairs'],'stop_required':True,
        'source_sha256':sources,'counting_policy':'Only saved audited metrics count as joint results; interrupted requests are pending, not task failures.'}
    if sources!={p:sha(Path(p)) for p in sources}:raise ValueError('Evidence changed while reconstructing')
    save_json(out/'episode_records.json',sorted(rows,key=lambda r:r['episode_id']))
    save_json(out/'diagnostics.json',data)
    old=historical(DEFAULT_DATA/'attempt_s2x_final_20261014T164338Z_4f85aaa3')
    previous=historical(DEFAULT_DATA/'attempt_s2x_final_20261015T053115Z_a3b834e8')
    save_json(out/'historical_full_comparison.json',{'before':old,'previous':previous,'current_full':None,'reason':'quick B stopping condition'})
    lines=['## 快速检查 B：停止报告','',f'证据 `{out}`；停止收据 `FAST_B_STOP.json`。',
        '多向佯动 4d13/ext_008 在第 5 轮后没有完整成功配对，触发用户指定的快速 B 停止条件。仅终止已核实的本批主进程及其 8 个子进程，在途请求按中止记录；没有继续第 6/7 步。','',
        f"登记 10 个组合、20 个请求；完成审计的联合轨迹 {len(generated)} 条；完整成功配对 {summary['complete_successful_pairs']} 个，确定失败组合 {summary['confirmed_failed_cells']} 个，中止未完成组合 {summary['interrupted_incomplete_cells']} 个。中止项不计任务失败；本次部分结果不能当作全 20 请求的无删失成功率。",'',
        '| 意图 | 方式 | 骨架 | 组数 | 结果 | 已完成/已启动测时轮数 | 叠加新增拒绝组合 |',
        '|---|---|---|---:|---|---:|---:|']
    labels={'successful_pair':'完整成功配对','confirmed_failure':'确定失败','interrupted_incomplete':'中止未完成'}
    for c in cells:lines.append(f"| {NAMES[c['intent']]} | {c['approach_mode']} | {c['skeleton_id']} | {c['group_count']} | {labels[c['status']]} | {c['completed_calibration_rounds']}/{c['started_calibration_rounds']} | {c['additional_overlay_rejections']} |")
    lines+=['','### 触发停止与其他已确认失败','',
        '多向佯动：前 4 轮为实际延迟恒速间距预筛拒绝；第 5 轮单机核心事件/完成停留未观测。最终性质是 5 轮搜索预算耗尽，没有整体几何无解证明。',
        '多向突防 4d13/ext_009 的两版已完成且任务失败：佯攻组 task_group_02 的 uav_01/uav_05 实测最大深入比例均为 0.881，违反原范围 \\(0.3\\leq d\\leq0.7\\)。标签与独立审计一致，保持失败结论。','']
    for c in cells:
        for witness in c['planned_feint_depth_witnesses']:
            lines.append(f"- {c['skeleton_id']} / {witness['agent_id']}：计划作业点深入比例 {witness['planned_station_fraction']:.6f}，保存的完整规划折线按不超过 1 m 步长取样，最大深入比例约 {witness['sampled_planned_maximum_depth_fraction']:.6f}。")
    lines+=['','上述对照只读取已有折线，没有新增仿真；说明检查计划作业点深度不能替代检查完整航线的最大深入程度。本轮不修改角色判据或作业参数。','',
        '### 叠加预检与实测误差','',f"本次小试完成 {summary['completed_calibration_rounds']} 轮单机测时，新增拦截 {summary['additional_overlay_rejections']} 个原预筛已通过的组合。被拦截组合没有联合实测，不能据此统计误报率。",
        f"在 {len(prediction_rows)} 条已审计联合轨迹上，最小间距预测绝对误差：均值 {summary['mean_absolute_minimum_prediction_error_m']:.6f} m，最大 {summary['maximum_absolute_minimum_prediction_error_m']:.6f} m；最大逐机位置误差 {summary['maximum_position_error_m']:.6f} m；10 m 分类一致 {summary['ten_metre_classification_matches']}/{len(prediction_rows)}。",'',
        '| 骨架/时序 | 预测最小间距/m | 实测最小间距/m | 预测减实测/m |','|---|---:|---:|---:|']
    for r in prediction_rows:lines.append(f"| {r['skeleton_id']}/{r['mode']} | {r['prediction']['minimum_m']:.6f} | {r['actual']['minimum_m']:.6f} | {r['minimum_error_predicted_minus_actual_m']:+.6f} |")
    lines+=['','### 全量统计的三轮对照','', '本轮全量未启动；小试和规划结果不填入全量分母。','', '| 项目 | 修订前 | 上一轮 | 本轮全量 |','|---|---:|---:|---|']
    for key,title in [('regular_skeletons','常规骨架'),('regular_requests','常规请求'),('generated_regular','生成常规轨迹'),('retained_regular','质量与审计通过的常规轨迹'),('complete_pairs','完整成功配对'),('retained_task_failures','保留轨迹中的任务失败'),('generation_errors','生成质量错误'),('planning_rejected_requests','规划拒绝请求'),('abort_requests','中止请求')]:
        lines.append(f'| {title} | {old[key]} | {previous[key]} | 未运行 |')
    lines+=['','### 未执行项与边界','',
        '- 第 6 步三阶段参数分布统计未执行；提出候选和可选候选的原始取值已在候选池中留存，但尚无本轮全量最终保留骨架。',
        '- 第 7 步 22 条固定模板回放、全部测试、冻结后全量 120+6 请求、960 项交叉否定与 1/2 进程比较均未执行。',
        '- 任务 I 后的时长捷径检查及每类召回率、平衡准确率未执行。监视时长、圈数、半径范围及角色参数保持原要求。',
        '- 本轮各实施步骤的 S2 测试均通过，最后一次为 164/164。已完成审计的输出未发现 P0；未完成的请求不据此宣称审计通过。',
        '- 外层兼容状态仍有 geometry_infeasible / planning_spacing_rejection 等名称；本轮三类原因以 search_rejection、group_terminations 和 calibration_termination 的作用域及见证为准。','']
    with (PROJECT/'docs/v07/S2_search_revision_report.md').open('a',encoding='utf-8',newline='\n') as f:f.write('\n'+'\n'.join(lines))
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
