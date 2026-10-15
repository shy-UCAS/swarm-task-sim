"""Revision-only distribution diagnostics. Run only after all 960 cross checks."""
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import sys
import numpy as np

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from task_v07.io import read_json, save_json, sha
from scripts.v07_s2_revision_diagnostics import collect, INTENTS, NAMES
from scripts.write_v07_s2_final_report import table, link, percent, number


NUMERIC_PARAMETERS=('approach_obstacle_clearance_m','collection_clearance_m','feint_group_depth_fraction',
    'intrusion_endpoint_depth_m','intrusion_feasible_max_depth_m','observation_alert_clearance_m',
    'planned_observation_dwell_s','orbit_radius_m','sector_angle_deg','sector_area_m2','strip_overlap_fraction',
    'transit_chord_position_fraction')
CATEGORICAL_PARAMETERS=('observation_dwell_method','monitoring_laps','monitoring_rotation_sign')


def sampling_unit(stage,key):
    if stage=='measured_retained_episodes':
        return '保留轨迹中的单机（同步/递次分别计）'
    candidate=stage=='all_attempted_draws'
    if key=='approach_obstacle_clearance_m':
        return '候选组记录（同骨架共用净空值）' if candidate else '组记录（同骨架共用净空值）'
    member=key in ('feint_member_depth_fraction','transit_chord_length_m',
                   'transit_entry_exit_azimuth_difference_deg','transit_lateral_offset_m')
    if member:return '候选中的单机计划值' if candidate else '骨架中的单机计划值'
    return '候选中的任务组参数记录' if candidate else '骨架中的任务组参数记录'


def summarize(values):
    values=[float(v) for v in values if v is not None and np.isfinite(v)]
    return {'n':len(values),'unique':len(set(values)), 'minimum':min(values) if values else None,
            'p10':float(np.percentile(values,10)) if values else None,
            'median':float(np.median(values)) if values else None,
            'p90':float(np.percentile(values,90)) if values else None,
            'maximum':max(values) if values else None,
            'spread_status':'unmeasured' if not values else 'insufficient_n' if len(values)<2 else
                            'single_value' if len(set(values))==1 else 'noncollapsed'}


def retained(records):
    return [r for r in records if not r.get('aborted') and not r.get('diagnostic_only')
            and r['state']=='generated' and r.get('quality_valid') and r.get('audit_passed')]


def proportions(records):
    result=[]
    for intent in INTENTS:
        counts=Counter(r['approach_mode'] for r in retained(records) if r['intent']==intent)
        total=sum(counts.values())
        result.append({'intent':intent,'n':total,'same':counts['same_direction'],'multi':counts['multi_direction'],
                       'same_fraction':counts['same_direction']/total if total else None})
    return result


def parameter_distributions(attempt,descriptors,records):
    numeric=defaultdict(list); categorical=defaultdict(Counter); raw=[]
    def add(stage,role,draw,sid,gid):
        for key in NUMERIC_PARAMETERS:
            if key in draw:numeric[(stage,role,key)].append(draw[key])
        for key in CATEGORICAL_PARAMETERS:
            if key in draw:categorical[(stage,role,key)][str(draw[key])]+=1
        for value in draw.get('feint_depth_fraction_by_agent',{}).values():
            numeric[(stage,role,'feint_member_depth_fraction')].append(value)
        raw.append({'stage':stage,'role':role,'skeleton_id':sid,'group_id':gid,'values':draw})
    kept={r['skeleton_id'] for r in retained(records)}
    search_rows=[]
    for d in descriptors:
        sid=d['skeleton_id'];root=attempt/sid
        search=read_json(root/'candidate_search.json')
        search_rows.append({'skeleton_id':sid,'attempted':search['attempted_candidates'],
            'calibration_rounds':search.get('actual_single_agent_calibration_rounds',0),
            'solo_flights':search['solo_flights_run'],'rejection_reasons':search['rejection_reasons']})
        methods={g['group_id']:g['execution_method'] for g in d['task_groups']}
        for candidate in search['candidates']:
            for gid,draw in candidate['draws_by_group'].items():
                add('all_attempted_draws',methods[gid],draw,sid,gid)
        if not (root/'skeleton.json').exists():continue
        skeleton=read_json(root/'skeleton.json')
        for gid,g in skeleton['group_skeletons'].items():
            role=g['execution_method'];draw=g.get('continuous_geometry_draw',{})
            add('selected_for_execution',role,draw,sid,gid)
            if sid in kept:add('retained_skeletons_once',role,draw,sid,gid)
            for ref in g['references'].values():
                chord=ref.get('planned_chord')
                if chord:
                    for field in ('chord_length_m','entry_exit_azimuth_difference_deg','lateral_offset_m'):
                        numeric[('selected_for_execution',role,'transit_'+field)].append(chord[field])
    for row in retained(records):
        labels=read_json(attempt/row['path']/'labels.json')
        for a in labels['agents'].values():
            role=a['assigned']['execution_method'];c=a['observed']['contribution']
            for field in ('depth_fraction_in_alert_band','maximum_protected_depth_m','dwell_s','lap_count_observed',
                          'chord_length_m','entry_exit_azimuth_difference_deg'):
                if field in c:numeric[('measured_retained_episodes',role,field)].append(c[field])
    expected={
        'transit':(('transit_chord_position_fraction',),(),('chord_length_m','entry_exit_azimuth_difference_deg')),
        'close_observation':(('observation_alert_clearance_m','planned_observation_dwell_s'),('observation_dwell_method',),('dwell_s',)),
        'monitoring':(('orbit_radius_m',),('monitoring_laps','monitoring_rotation_sign'),('lap_count_observed',)),
        'area_search':(('sector_angle_deg','sector_area_m2','strip_overlap_fraction'),(),()),
        'feint':(('feint_group_depth_fraction','feint_member_depth_fraction'),(),('depth_fraction_in_alert_band',)),
        'intrusion':(('intrusion_endpoint_depth_m','intrusion_feasible_max_depth_m'),(),('maximum_protected_depth_m',))}
    for role,(numbers,categories,measured) in expected.items():
        for stage in ('all_attempted_draws','selected_for_execution','retained_skeletons_once'):
            for key in ('approach_obstacle_clearance_m',*numbers):numeric.setdefault((stage,role,key),[])
            for key in categories:categorical.setdefault((stage,role,key),Counter())
        for key in measured:numeric.setdefault(('measured_retained_episodes',role,key),[])
    return {'numeric':[{'stage':stage,'role':role,'parameter':key,'sampling_unit':sampling_unit(stage,key),**summarize(values)}
                        for (stage,role,key),values in sorted(numeric.items())],
            'categorical':[{'stage':stage,'role':role,'parameter':key,'sampling_unit':sampling_unit(stage,key),'counts':dict(counts),'unique':len(counts),
                            'spread_status':'unmeasured' if not counts else 'insufficient_n' if sum(counts.values())<2
                                            else 'single_value' if len(counts)==1 else 'noncollapsed'}
                           for (stage,role,key),counts in sorted(categorical.items())],
            'raw_draws':raw,'candidate_search':search_rows}


def spans(records):
    groups=defaultdict(list)
    for row in retained(records):
        for g in row['groups'].values():
            groups[(g['execution_method'],row['approach_mode'],g['formation_split_count'])].append(g['approach_span_deg'])
    return [{'role':role,'approach':approach,'stock_count':stocks,**summarize(values)}
            for (role,approach,stocks),values in sorted(groups.items())]


def targets(after):
    result=[]
    for intent in INTENTS:
        rows=[s for s in after['skeletons'] if s['intent']==intent]
        rate=sum(r['success'] for r in rows)/len(rows)
        modes={c['value']:c for c in after['matrices']['approach_mode'] if c['intent']==intent}
        same,multi=(modes[m]['fraction'] for m in ('same_direction','multi_direction'))
        gap=None if same is None or multi is None else abs(same-multi)*100
        both=all(modes[m]['successful']>0 for m in ('same_direction','multi_direction'))
        result.append({'intent':intent,'success_fraction':rate,'same':same,'multi':multi,'gap_pp':gap,
                       'both_have_success':both,'rate_target_met':rate>=.6,
                       'gap_target_met':gap is not None and gap<=20})
    return result


def render(data,output):
    registered={intent: next(c['registered'] for c in data['after']['matrices']['approach_mode']
                            if c['intent']==intent and c['value']=='same_direction') /
                        sum(c['registered'] for c in data['after']['matrices']['approach_mode'] if c['intent']==intent)
                for intent in INTENTS}
    lines=['## 任务 I 后：修订前—规划—修订后对照与捷径诊断','',
           '四维分母均为 60；多组骨架规模按最大组分档。规划可行率与实飞成功配对率含义不同，三列并列只用于定位淘汰阶段。','']
    for dimension,before in data['before']['matrices'].items():
        smoke={(c['intent'],c['value']):c for c in data['planning']['matrices'][dimension]}
        after={(c['intent'],c['value']):c for c in data['after']['matrices'][dimension]}
        lines += [f'### {dimension}','',table(['意图','条件','修订前成功/登记','G 规划可行/登记','修订后成功/登记'],
            [[NAMES[c['intent']],c['value'],f"{c['successful']}/{c['registered']}",
              f"{smoke[(c['intent'],c['value'])]['successful']}/{c['registered']}",
              f"{after[(c['intent'],c['value'])]['successful']}/{c['registered']}"] for c in before]),'']
    lines += ['### 修订后已登记但零成功的组合','',
              '候选计数与单机校时轮次属于不同层次，均保留来源，不能当作独立骨架数或无解证明。','',
              table(['意图','维度/条件','成功/登记','最终类别','前三项保存的拒绝原因'],
                [[NAMES[c['intent']],f"{c['dimension']}/{c['value']}",f"0/{c['registered']}",
                  str(c['failure_categories']),'; '.join(f'{k}: {v}' for k,v in list(c['candidate_reason_counts'].items())[:3])
                  or '无规划拒绝；见质量或任务条件失败'] for c in data['after']['zero_success_combinations']]),'']
    lines += ['### 目标对照（仅诊断，不作为停机门槛）','',
        table(['意图','骨架成功率','达到 60%','同向成功率','多向成功率','绝对差/百分点','两方式均有成功','差值不超过 20'],
            [[NAMES[t['intent']],percent(t['success_fraction']),t['rate_target_met'],percent(t['same']),percent(t['multi']),
              number(t['gap_pp']),t['both_have_success'],t['gap_target_met']] for t in data['targets']]),'',
        '### 保留轨迹的逼近方式比例','',table(['意图','登记同向占比','修订前同向/总数','修订前同向占比','修订后同向/总数','修订后同向占比','修订后相对登记偏差/百分点'],
        [[NAMES[a['intent']],percent(registered[a['intent']]),f"{a['same']}/{a['n']}",percent(a['same_fraction']),f"{b['same']}/{b['n']}",percent(b['same_fraction']),
          number(None if b['same_fraction'] is None else (b['same_fraction']-registered[b['intent']])*100)]
         for a,b in zip(data['proportions_before'],data['proportions_after'])]),'',
        '### 实测进入预警区前 100 m 航向跨度','',
        '以下以保留常规轨迹中的任务组为单位，同步/递次分别计数；缺失事件不补值。','',
        table(['角色','逼近方式','股数','N','最小','中位','P90','最大'],
            [[s['role'],s['approach'],s['stock_count'],s['n'],*[number(s[k]) for k in ('minimum','median','p90','maximum')]] for s in data['spans']]),'',
        '### 作业参数实际取值与塌缩诊断','',
        'all_attempted_draws 为候选尝试（后续组可能因前组拒绝而未抽样）；selected_for_execution 为完成校时后实际选中的骨架；'
        'retained_skeletons_once 为至少保留一个时序版本的骨架。这两个阶段去除了同步/递次重复，组级参数每组一次，'
        '佯攻成员扰动和过境计划弦指标按每机展开。接近净空按骨架抽样，保存到各组及候选的值会重复，N 不是独立随机抽样次数。'
        'measured_retained_episodes 为真实轨迹单机事实，包含两个时序版本；各行明确计数单位。'
        'sample 数为 0/1 时不能证明未塌缩。角色结果条件均未因这些分布调整。监视圈数/方向保留原有随机规则。','',
        table(['阶段','角色','参数','计数单位','N/不同值数','最小/P10/中位/P90/最大','诊断'],
            [[v['stage'],v['role'],v['parameter'],v['sampling_unit'],f"{v['n']}/{v['unique']}",
              ' / '.join(number(v[k]) for k in ('minimum','p10','median','p90','maximum')),v['spread_status']]
             for v in data['parameters']['numeric']]),'',
        table(['阶段','角色','参数','计数单位','取值计数','不同值数','诊断'],
            [[v['stage'],v['role'],v['parameter'],v['sampling_unit'],str(v['counts']),v['unique'],v['spread_status']] for v in data['parameters']['categorical']]),'',
        '### 两项 family 留一捷径检查','',
        '固定深度 2、叶节点至少 3 样本的浅层决策树，不调参。同步/递次同属一个 family 留出折。'
        '时长是仿真时间轴，不是墙钟；监视时长只作测量，不作为优化目标。五类均匀随机参考 20%，另报告训练折多数类基线。','',
        '保留样本类别数：'+str({NAMES[i]:data['retained_class_counts'].get(i,0) for i in INTENTS})+'。'
        +'缺失类别：'+str([NAMES[i] for i in INTENTS if not data['retained_class_counts'].get(i,0)])+'。'
        +'缺少类别时，20% 仅为理论五类参考，所得准确率不能解释为完整五类泛化性能。','']
    if data['shortcuts']['status']=='completed':
        lines += [table(['特征','准确率','宏平均召回率','family 平均准确率','多数类基线','随机参考'],
            [[name,*[percent(v[k]) for k in ('accuracy','balanced_accuracy','family_macro_accuracy','majority_baseline_accuracy')],'20%']
             for name,v in data['shortcuts']['results'].items()]),'']
        for name,v in data['shortcuts']['results'].items():
            lines += [f'#### {name}：逐折','',table(['留出 family','训练/测试','准确率','多数类基线'],
                [[f['held_out_family'],f"{f['train_n']}/{f['test_n']}",percent(f['accuracy']),percent(f['majority_baseline_accuracy'])] for f in v['folds']]),'']
    else:lines += [data['shortcuts']['reason'],'']
    lines += ['### 主对照与交叉否定覆盖变化','',table(['项目','修订前','修订后'],data['coverage_comparison']),'',
        '所有比例与捷径结果只作诊断；不足样本、单值参数、低成功率和未执行项如实保留。'
        '不得将缺失样本视为通过，也不得根据此检查缩短监视时长或放松角色条件。','',
        link(output/'diagnostics.json','完整数值、逐候选参数、逐折预测与来源')+'。','']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt',type=Path,required=True)
    parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--planning',type=Path,required=True)
    parser.add_argument('--report',type=Path,default=PROJECT/'docs/v07/S2_revision_report.md')
    args=parser.parse_args()
    attempt=args.attempt.resolve()
    cross=read_json(attempt/'cross_negation.json')
    if sum(cross['counts'].values())!=960:raise ValueError('Task I must first account for all 960 requests')
    before=read_json(args.before);planning=read_json(args.planning)
    old=Path(before['source_attempt'])
    records=read_json(attempt/'episode_records.json')
    registration=read_json(attempt/'registration.json');infra=Path(registration['source_attempt'])
    descriptors=[d for d in read_json(infra/'private_skeleton_descriptors.json') if d['subset']=='regular' and not d.get('diagnostic_only')]
    facilities={r['family_id']:r['facility_count'] for r in read_json(infra/'registration.json')['selected']}
    valid=retained(records)
    if len({r['family_id'] for r in valid})>=2:
        from scripts.analyze_v07_s2_sampling_bias import shortcut_cv
        shortcut={'status':'completed','results':shortcut_cv(valid,facilities)}
    else:shortcut={'status':'not_run','reason':'不足两个有保留轨迹的 family，无法进行 family 留一训练/测试。'}
    old_cross=read_json(old/'cross_negation.json')
    data={'before':before,'planning':planning,'after':collect(attempt),
          'proportions_before':proportions(read_json(old/'episode_records.json')),
          'proportions_after':proportions(records),'spans':spans(records),
          'parameters':parameter_distributions(attempt,descriptors,records),'shortcuts':shortcut,
          'retained_episode_count':len(valid),'retained_class_counts':dict(Counter(r['intent'] for r in valid)),
          'coverage_comparison':[
            ['主对照条数',read_json(old/'view_index.json')['counts']['primary'],read_json(attempt/'view_index.json')['counts']['primary']],
            ['交叉否定实际执行项',960-old_cross['counts']['not_run'],960-cross['counts']['not_run']],
            ['交叉否定 not_run',old_cross['counts']['not_run'],cross['counts']['not_run']]],
          'sources':{str(path):sha(path) for path in (attempt/'episode_records.json',attempt/'cross_negation.json',args.before,args.planning)}}
    data['targets']=targets(data['after'])
    output=attempt/'revision_diagnostics';output.mkdir()
    save_json(output/'diagnostics.json',data)
    report=args.report.read_text(encoding='utf-8')
    marker='<!-- revision-post-I-diagnostics -->'
    if marker in report:raise ValueError('Post-I diagnostics already recorded')
    args.report.write_text(report+'\n'+marker+'\n'+render(data,output),encoding='utf-8',newline='\n')
    print(output/'diagnostics.json',flush=True)


if __name__=='__main__':main()
