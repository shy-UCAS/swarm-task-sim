"""Read-only evidence figures for the search revision and its stopping gates."""
import argparse
from pathlib import Path
import sys
import numpy as np
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from task_v07.io import read_json,save_json,sha
from scripts.v07_s2_revision_diagnostics import NAMES


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smokes',type=Path,nargs='+',required=True)
    parser.add_argument('--witness',type=Path,required=True)
    parser.add_argument('--pilot',type=Path)
    parser.add_argument('--output',type=Path,default=PROJECT/'docs/v07/S2_search_revision_assets')
    args=parser.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font=Path('C:/Windows/Fonts/msyh.ttc')
    if font.is_file():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams['font.family']=font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams['axes.unicode_minus']=False
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    source_files=[p/'diagnostics.json' for p in args.smokes]+[args.witness/'diagnostics.json']
    if args.pilot:source_files += [args.pilot/'diagnostics.json',args.pilot/'episode_records.json']
    hashes={str(p):sha(p) for p in source_files}
    smokes=sorted([read_json(p/'diagnostics.json') for p in args.smokes],key=lambda d:d['step'])
    cells=smokes[0]['matrices']['approach_mode']
    values=np.array([[d['matrices']['approach_mode'][i]['fraction'] for d in smokes] for i in range(len(cells))])
    fig,ax=plt.subplots(figsize=(9,8))
    image=ax.imshow(values,vmin=0,vmax=1,cmap='YlGnBu',aspect='auto')
    for i in range(len(cells)):
        for j,d in enumerate(smokes):
            cell=d['matrices']['approach_mode'][i]
            ax.text(j,i,f"{cell['successful']}/{cell['registered']}",ha='center',va='center',color='white' if values[i,j]>.55 else '#17212b')
    ax.set_yticks(range(len(cells)),[NAMES[c['intent']]+' / '+('同向' if c['value']=='same_direction' else '多向') for c in cells])
    ax.set_xticks(range(len(smokes)),[f"第 {d['step']} 步\n{sum(r['success'] for r in d['skeletons'])}/60" for d in smokes])
    ax.set_title('登记的 60 骨架：各修订步骤后的纯规划可行数')
    fig.colorbar(image,ax=ax,label='规划可行比例')
    fig.tight_layout();fig.savefig(out/'planning_coverage.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4))
    elapsed=[d['total_wall_s']/60 for d in smokes]
    bars=ax.bar([f"第 {d['step']} 步" for d in smokes],elapsed,color='#007f86')
    ax.bar_label(bars,labels=[f'{v:.2f}' for v in elapsed],padding=3)
    ax.set_ylim(0,max(elapsed)*1.2);ax.set_ylabel('墙钟时间 / 分钟')
    ax.set_title('完整 60 骨架规划检查的耗时（均 8 进程）')
    ax.spines[['top','right']].set_visible(False)
    fig.tight_layout();fig.savefig(out/'planning_wall_time.png',dpi=160);plt.close(fig)
    witness=read_json(args.witness/'diagnostics.json')
    errors=[{'skeleton_id':'archived_8412_ext001','mode':m,'source':'archive',**r} for m,r in witness['prediction_errors'].items()]
    if args.pilot:
        errors += [{'source':'quick_b',**r} for r in read_json(args.pilot/'diagnostics.json')['prediction_errors']]
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for source,color,label in (('archive','#bc4b51','存档反例配对'),('quick_b','#007f86','本轮快速 B')):
        rows=[r for r in errors if r['source']==source]
        if not rows:continue
        x=[r['actual']['minimum_m'] for r in rows];y=[r['prediction']['minimum_m'] for r in rows]
        axes[0].scatter(x,y,color=color,label=label,s=35,alpha=.8)
        axes[1].scatter(x,[r['minimum_error_predicted_minus_actual_m'] for r in rows],color=color,label=label,s=35,alpha=.8)
    maximum=max(max(r['actual']['minimum_m'],r['prediction']['minimum_m']) for r in errors)*1.08
    axes[0].plot([0,maximum],[0,maximum],ls='--',color='#888888',lw=1)
    axes[0].axhline(10,color='#a98534',ls=':');axes[0].axvline(10,color='#a98534',ls=':')
    axes[0].set(xlabel='实测最小间距 / m',ylabel='预测最小间距 / m',title='整航线最小间距；点为各时序版本')
    axes[1].axhline(0,color='#888888',ls='--',lw=1)
    axes[1].set(xlabel='实测最小间距 / m',ylabel='预测 − 实测 / m',title='叠加预测误差')
    for ax in axes:ax.legend(fontsize=9);ax.grid(alpha=.15)
    fig.tight_layout();fig.savefig(out/'solo_overlay_prediction.png',dpi=160);plt.close(fig)
    receipts={'sources':hashes,'figures':['planning_coverage.png','planning_wall_time.png','solo_overlay_prediction.png'],'trajectory_figures':[]}
    planning_cells=[]
    for cell in cells:
        item={'intent':cell['intent'],'approach_mode':cell['value'],'stages':[]}
        for data in smokes:
            chosen=[r for r in data['skeletons'] if r['intent']==cell['intent'] and r['approach_mode']==cell['value']]
            item['stages'].append({'step':data['step'],'registered':len(chosen),
                'feasible':sum(r['success'] for r in chosen),
                'sum_worker_planning_wall_s':sum(r['planning_wall_s'] for r in chosen),
                'attempted_group_proposals':sum(r['attempted_candidates'] for r in chosen)})
        planning_cells.append(item)
    receipts['planning_cells']=planning_cells
    if args.pilot:
        from scripts.v07_s2_final_figures import topdown,paired_timing
        records=read_json(args.pilot/'episode_records.json')
        generated=[r for r in records if r.get('path')]
        for row in generated:
            if row['mode']!='synchronous':continue
            name=f"quick_b_{row['intent']}_{row['approach_mode']}.png"
            topdown(args.pilot,row,out/name)
            receipts['trajectory_figures'].append({'figure':name,'episode_id':row['episode_id'],'task_result':row['task_result']})
        pairs=[[r for r in generated if r['skeleton_id']==sid] for sid in sorted({r['skeleton_id'] for r in generated})]
        pairs=sorted([p for p in pairs if len(p)==2],key=lambda p:(p[0]['group_count']<=1,p[0]['skeleton_id']))
        for i,pair in enumerate(pairs[:2]):
            name=f'quick_b_timing_{i+1}.png';paired_timing(args.pilot,pair,out/name)
            receipts['trajectory_figures'].append({'figure':name,'skeleton_id':pair[0]['skeleton_id']})
    if hashes!={str(p):sha(p) for p in source_files}:raise ValueError('Evidence changed while plotting')
    save_json(out/'figure_sources.json',receipts)
    lines=['## 快速检查 A 的组合耗时明细','',
        '各单元格为“可行/登记；累计工作进程秒”。累计耗时包含成功与失败骨架，不能当作并行墙钟时间。','',
        '| 意图 | 逼近方式 | '+' | '.join(f"第 {d['step']} 步" for d in smokes)+' |',
        '|---|---|'+''.join('---:|' for _ in smokes)]
    for cell in planning_cells:
        lines.append('| '+NAMES[cell['intent']]+' | '+cell['approach_mode']+' | '+
            ' | '.join(f"{v['feasible']}/{v['registered']}；{v['sum_worker_planning_wall_s']:.2f} s" for v in cell['stages'])+' |')
    lines += ['', '## 本轮图件','', '规划图仅表示规划可行；实测图使用导出的 10 Hz 轨迹，图题保留实际成功/失败结果。','']
    for name in receipts['figures']+[r['figure'] for r in receipts['trajectory_figures']]:
        lines += [f'![{name}](<{(out/name).resolve().as_posix()}>)','']
    with (PROJECT/'docs/v07/S2_search_revision_report.md').open('a',encoding='utf-8',newline='\n') as f:f.write('\n'+'\n'.join(lines))
    print({'output':str(out),'figures':len(receipts['figures'])+len(receipts['trajectory_figures'])})


if __name__=='__main__':main()
