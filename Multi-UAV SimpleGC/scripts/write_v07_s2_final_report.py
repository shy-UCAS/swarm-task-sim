"""Write the second-stage report from final-run evidence, without inventing missing results."""
from pathlib import Path
import argparse
import json
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from task_v07.io import read_json
from task_v07.expansion.sampling import INTENTS
from scripts.v07_s2_final_figures import render_all

NAMES={'transit':'过境','reconnaissance':'侦察','monitoring':'游弋监视','feint':'佯动','penetration':'突防'}


def number(value):
    return '未测得' if value is None else f'{value:.3f}' if isinstance(value,float) else str(value)


def percent(value):
    return '无可用分母' if value is None else f'{100*value:.2f}%'


def ratios(counts):
    total=sum(counts.values())
    return '；'.join(f'{name}: {count}/{total} ({percent(count/total)})' for name,count in sorted(counts.items())) if total else '无可用样本'


def link(path,label):
    return f'[{label}](<{Path(path).resolve().as_posix()}>)'


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join('---' for _ in headers)+'|',
                      *['| '+' | '.join(str(x).replace('|',' / ').replace('\n',' ') for x in row)+' |' for row in rows]])+'\n'


def write_yes_appendix(path,cross,*,revision=False):
    lines=[f'# S2 {"修订轮" if revision else "第二段"}交叉否定：逐条“是”见证','',
           '每一项保留模板与轨迹、任务组对应、实际取交集的成员，以及使模板成立的组级和单机判据。'
           '同一模板几何在两个 A 时序槽位中的重复请求按 960 项登记保留，不去重。','']
    for i,row in enumerate(cross['affirmative_witnesses'],1):
        lines += [f'## {i}. {row["template_episode_id"]} → {row["trajectory_episode_id"]}','',
                  f'模板组 `{row["template_group_id"]}`（{row["execution_method"]}，目标 `{row["target_id"]}`）作用于轨迹组 '
                  f'`{row["trajectory_group_id"]}`；对应方式 `{row["membership_match"]}`；判定成员：'+', '.join(row['evaluated_members'])+'。','',
                  '触发判据：模板组条件全部成立，所评估成员的全部贡献条件成立。数值事实和各判据如下：','',
                  '```json',json.dumps(row['facts'],ensure_ascii=False,indent=2),'```','']
    if not cross['affirmative_witnesses']:
        lines += ['本次已执行项中没有“是”；未执行项仍按 not_run 统计，不据此宣称全部否定成立。','']
    path.write_text('\n'.join(lines),encoding='utf-8',newline='\n')


def write_report(attempt, *, revision=False):
    attempt=Path(attempt).resolve()
    registration=read_json(attempt/'registration.json')
    records=read_json(attempt/'episode_records.json')
    stats=read_json(attempt/'statistics.json')
    views=read_json(attempt/'view_index.json')
    cross=read_json(attempt/'cross_negation.json')
    process=read_json(attempt/'process_comparison.json')
    execution=read_json(attempt/'execution_summary.json')
    figures_path=attempt/'figures'/'figure_coverage.json'
    if revision:
        from scripts.v07_s2_revision_figures import render_revision
        renderer=render_revision
    else:renderer=render_all
    figures=read_json(figures_path) if figures_path.exists() else renderer(attempt,records)
    stamp=attempt.name.removeprefix('attempt_s2x_final_')
    report=PROJECT/'docs'/'v07'/f'{"S2_revision_full_report" if revision else "S2_phase2_final_report"}_{stamp}.md'
    yes=report.with_name(f'{"S2_revision_cross_yes" if revision else "S2_phase2_cross_yes"}_{stamp}.md')
    if report.exists() or yes.exists():
        raise FileExistsError('Final reports already exist; preserve original evidence')
    write_yes_appendix(yes,cross,revision=revision)
    lines=['# Traj2Language v0.7 S2 修订轮全量统计' if revision else '# Traj2Language v0.7 S2 第二段总报告','',
        f'全量 attempt：`{attempt.name}`。冻结生成代码提交 `{registration["commit"]}`，工作进程 {registration["workers"]}。'
        f'登记 60 个常规骨架（120 个时序请求）及 6 个中止请求，记录 {execution["record_count"]} 项，未复用试点结果。','',
        '本项目输出防御方意图识别研究用的带标签合成轨迹。地图为随机抽象几何，执行后端为冻结的平动点质量模型；'
        '航点编排不针对真实地点或防御部署，不包含武器、电子压制、雷达规避或任务效果优化。','',
        f'配置 SHA256：`{registration["config_sha256"]}`。抽样描述符 SHA256：`{registration["descriptor_sha256"]}`。'
        '运行期间未修改生成代码；固定回归与分步记录见 '+link(PROJECT/('docs/v07/S2_revision_report.md' if revision else 'docs/v07/S2_phase2_continuation_record.md'),'执行记录')+'。','',
        '## 1. 骨架成功率与拒绝','',
        '成功骨架要求两种时序均生成、质量有效、独立审计通过且任务成功。几何候选搜索是有限预算，拒绝不宣称地图在数学上无解。','',
        table(['意图','登记骨架','成功配对','成功率','几何拒绝','运动学拒绝','规划间距拒绝'],
              [[NAMES[i],s['registered_skeletons'],s['successful_pairs'],percent(s['skeleton_success_fraction']),
                s['final_rejection_categories'].get('geometry_infeasible',0),s['final_rejection_categories'].get('kinematic_infeasible',0),
                s['final_rejection_categories'].get('planning_spacing_rejection',0)] for i,s in stats['by_intent'].items()]),
        '逐次几何尝试、拒绝细节和最后原因保存在 '+link(attempt/'statistics.json','统计证据')+' 及各骨架的 `geometry_*/planning_rejection.json`。','',
        '## 2. 非设计失败、质量错误与时序','',
        '下表非设计失败率以质量有效且审计通过的常规 episode 为分母；生成质量错误另列。时序一致率以保留常规轨迹中的全部任务组为分母，未知时序不被删除以抬高一致率。','',
        table(['意图','实飞条数','质量有效条数','非设计失败数','非设计失败率','时序一致组/总组','一致率'],
              [[NAMES[i],s['generated_episodes'],s['retained_valid_episodes'],s['non_designed_task_failures'],percent(s['non_designed_failure_fraction']),
                f'{s["timing_group_matches"]}/{s["timing_groups"]}',percent(s['timing_group_agreement_fraction'])] for i,s in stats['by_intent'].items()]),
        '失败判据逐意图统计：','',
        table(['意图','单机失败判据计数','任务组失败判据计数'],[[NAMES[i],json.dumps(s['failed_agent_conditions'],ensure_ascii=False),
              json.dumps(s['failed_group_conditions'],ensure_ascii=False)] for i,s in stats['by_intent'].items()]),
        '规划采用实际单机测时得到的延迟和登记组间偏移，对全体飞机、整航线及两个时序版本按定速 10 Hz 检查；'
        +(r'小于 \(10\,\mathrm{m}\) 的计划被拦截（名义预筛与真实延迟检查均适用，含中途悬停）。' if revision else r'小于 \(6\,\mathrm{m}\) 的计划被拦截。')
        +r'该估计不保证实飞间距，实测小于 \(2\,\mathrm{m}\) 一律作为生成错误剔除，不修改任务判据。','',
        table(['排除类别','条数'],views['exclusion_counts'].items()),
        '## 3. 中止配对','',
        '同步中止继承引用常规骨架的全部公共条件和延迟。核心事件仍为进入禁飞区；只有主编组的四项实测撤离事实均满足，才标记“抵近后撤离”。'
        +('其他组继续原路线。原引用规划失败时，按骨架编号升序尝试同地图的其他常规突防骨架，全部规划失败记 not_run；替换关系保存在 abort_pairing_registration.json。' if revision else
         '其他组继续原路线。引用轨迹未生成时记 not_run，不换用另一个骨架。'),'',
        table(['中止请求','引用常规 episode','状态/原因','撤离事实','主组时序','前缀相同帧'],
              [[r['episode_id'],r.get('source_episode_id'),r['state']+': '+str(r.get('reason') or r.get('task_result')),
                r.get('abort_observation_valid'),r.get('main_group_observed_coordination'),r.get('exact_prefix_comparison',{}).get('prefix_frames')]
               for r in stats['abort_records']]),
        '## 4. 交叉否定 960 项','',
        f'结果 `{cross["status"]}`；PASS {cross["counts"]["PASS"]}，出现“是”的请求 {cross["counts"]["FAIL"]}，'
        f'not_run {cross["counts"]["not_run"]}；组级“是”见证共 {cross["affirmative_group_count"]} 项。','',
        '同 family、同公共骨架槽位内，A 模板判 B 轨迹；任务组先按完全相同的成员集合对应，否则逐个非空交集判定并注明。'
        'A 或 B 未形成任务成功且质量/审计有效的完整配对时记 not_run。任一组级“是”按本轮要求列为验收不通过项，其他请求继续执行。'
        '部分共享角色成立不解释为整个集群基础意图相同。','',
        link(yes,'逐条“是”：模板、轨迹、成员对应与触发判据')+'；'+link(attempt/'cross_negation.json','全部 960 项原始结果')+'。','',
        '## 5. 独立审计、截断、进程无关性与视图','',
        table(['独立审计项','数量'],stats['audit'].items()),
        f'截断检查：`{json.dumps(stats["truncation"],ensure_ascii=False)}`。突击组的半程以自身实测终点保持完成为界，其他角色以实测作业结束为界，'
        '不把其他组继续执行的时间当成本组工作。缺失作业区间记 not_run。','',
        '全部新增条件及独立来源见 '+link(PROJECT/'docs/v07/S2_phase2_condition_audit_map.md','条件 → 审计项')+'。审计不导入生产侧 `task_v07`，'
        '圈层、接近航向、角色事实、组内时序、跨组距离和主要目标均从 10 Hz 真值重算。','',
        f'1/2 进程对比结果：`{process["status"]}`，骨架 `{process.get("skeleton_ids",[])}`；'
        f'内容差异 {process.get("content_difference_count","未执行")}。对比重新执行，不计入 126 个请求或训练视图。'
        +link(attempt/'process_comparison.json','完整比较')+'。'
        +(f" 实际轨迹比较 {process.get('generated_episode_comparisons',0)} 对；"
          f"仅规划输出比较 {len(process.get('planning_only_comparisons',[]))} 项。"
          "仅规划一致不证明实际轨迹一致；以下未生成项的实测进程对比未覆盖："
          +json.dumps(process.get('planning_only_comparisons',[]),ensure_ascii=False) if revision else ''),'',
        table(['视图','条数','索引'],[[key,count,link(attempt/'views'/f'{key}.csv',key+'.csv')] for key,count in views['counts'].items()]),
        '主对照按 family 五意图的成功配对数最小值平衡；其余可用成功轨迹进入扩展表。中止、非设计任务失败独立成表。'
        '规划拒绝、生成质量错误、未执行和未通过审计项均不进入训练视图，诊断样本排除。','',
        '## 6. 诊断分布（不设门槛）','',
        table(['角色/方法','含该角色骨架拒绝/登记','拒绝率','多向航向跨度 N/中位/P90/最大','分股数分布'],
              [[role,f'{s["rejected_skeletons_containing_role"]}/{s["registered_skeletons_containing_role"]}',
                percent(s['rejection_fraction_for_skeletons_containing_role']),
                ' / '.join(number(s['multi_direction_last_100m_heading_span_deg'][k]) for k in ('n','median','p90','maximum')),
                json.dumps(s['formation_split_count_distribution'],ensure_ascii=False)] for role,s in stats['role_diagnostics'].items()]),
        '角色拒绝率的分母为含该角色的登记骨架；整骨架拒绝可能来自其他组或跨组冲突，不能解释为该角色单独不可行率。'
        '航向和耗时诊断包括全部已仿真的常规轨迹（含单列剔除的生成错误），跨度只统计实际可测值。','',
        table(['意图','墙钟仿真时长：N/中位/P90/最大(s)','仿真时间轴：N/中位/P90/最大(s)'],
              [[NAMES[i],' / '.join(number(s['simulation_wall_seconds'][k]) for k in ('n','median','p90','maximum')),
                ' / '.join(number(s['simulated_duration_seconds'][k]) for k in ('n','median','p90','maximum'))] for i,s in stats['by_intent'].items()]),
        table(['意图','登记同向/多向比例','保留轨迹同向/多向比例','登记合并后任务组数分布','保留轨迹任务组数分布'],
              [[NAMES[i],ratios(s['approach_mode']),ratios(stats['by_intent'][i]['retained_approach_mode']),
                json.dumps(s['merged_group_count'],ensure_ascii=False),json.dumps(stats['by_intent'][i]['retained_group_count'],ensure_ascii=False)]
               for i,s in stats['public_sampling_diagnostics']['distributions_by_intent'].items()]),
        '## 7. 实测图表与未满足项','',
        '所有曲线均为本次全量导出的实际轨迹；未生成的骨架不以规划预览替代实测图。完整来源及覆盖情况见 '
        +link(figures_path,'图表覆盖清单')+'。','']
    for item in [*figures['topdowns'],*figures.get('special_examples',[]),*figures['abort_pairs'],*figures['timing_pairs']]:
        file=attempt/'figures'/item['figure']
        lines += [f'![{item["figure"]}](<{file.as_posix()}>)','']
    if figures['missing_requirements']:
        lines += ['缺失的图表要求：','',*[f'- {json.dumps(item,ensure_ascii=False)}' for item in figures['missing_requirements']],'']
    lines += ['验收解释：交叉否定出现“是”属于不通过项；not_run 表示未覆盖，不计为通过。图表缺失如实列明。'
              '诊断分布和骨架成功率不擅自增加门槛。原始失败、排除项和每次几何尝试均保留。','',
              '可复核证据：'+link(attempt/'registration.json','运行登记')+'；'+link(attempt/'execution_summary.json','执行汇总')+'；'
              +link(attempt/'statistics.json','完整统计')+'；'+link(attempt/'view_index.json','视图索引')+'。','']
    report.write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    return report,yes


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('attempt',type=Path)
    parser.add_argument('--revision',action='store_true')
    args=parser.parse_args()
    for path in write_report(args.attempt,revision=args.revision):
        print(path,flush=True)
