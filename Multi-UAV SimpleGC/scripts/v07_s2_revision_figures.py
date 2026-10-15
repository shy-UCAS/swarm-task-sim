"""Revision figure requirements, using only the new attempt's exported truth."""
from pathlib import Path
import numpy as np
from task_v07.io import read_json, save_json
from task_v07.geometry import geometry_facts
from task_v07.expansion.sampling import INTENTS
from scripts.v07_s2_final_figures import load, draw_track, topdown, paired_timing


def deployment_figure(attempt,row,output):
    import matplotlib.pyplot as plt
    truth,scene,task,labels=load(attempt,row)
    fig,ax=plt.subplots(figsize=(10,9))
    draw_track(ax,truth,scene,task,labels)
    for group in task['group_skeletons'].values():
        if group['role']!='monitoring':continue
        zone=next(e for e in scene['entities'] if e.get('facility_id')==group['target_id'] and e.get('layer')=='warning')
        for index,a in enumerate(group['members']):
            xy=truth['p'][:,truth['agent_ids'].index(a),:2]
            hit=np.flatnonzero(geometry_facts(zone['geometry'],xy)['inside'])
            core=labels['agents'][a]['observed']['core_event']['frame_index']
            if not len(hit) or core is None:continue
            first=int(hit[0])
            ax.scatter(*xy[first],marker='s',s=32,facecolors='none',edgecolors='#b3277d',zorder=8,
                       label='First warning entry' if index==0 else None)
            ax.plot(xy[first:core+1,0],xy[first:core+1,1],color='#e07a21',lw=2.0,alpha=.8,
                    label='Measured deployment after entry' if index==0 else None)
        orbit=group['monitoring']
        angles=np.linspace(0,2*np.pi,361);center=np.asarray(orbit['orbit_center_enu_m'][:2])
        circle=center+orbit['orbit_radius_m']*np.c_[np.cos(angles),np.sin(angles)]
        ax.plot(circle[:,0],circle[:,1],color='#303030',ls=':',lw=1.,label='Shared planned orbit')
    ax.legend(fontsize=7,loc='best')
    ax.set_title('Same-direction monitoring: shared-side warning entry, then phase deployment\n'+row['skeleton_id'],fontsize=10)
    fig.tight_layout();fig.savefig(output,dpi=160);plt.close(fig)


def stock_figure(attempt,row,output):
    import matplotlib.pyplot as plt
    from scripts.v07_s2_plotting import map_axes
    truth,scene,task,labels=load(attempt,row)
    fig,ax=plt.subplots(figsize=(10,9));map_axes(ax,scene)
    colors=('#007f86','#bc4b51','#8055a6')
    for gid,group in task['group_skeletons'].items():
        stocks=group.get('formation_split',{}).get('members',[group['members']])
        for i,members in enumerate(stocks):
            for j,a in enumerate(members):
                xy=truth['p'][:,truth['agent_ids'].index(a),:2]
                ax.plot(xy[:,0],xy[:,1],color=colors[i%3],lw=1.,alpha=.85,
                        label=f'{gid} / stock {i+1}: '+','.join(members) if j==0 else None)
                ax.scatter(*xy[0],color=colors[i%3],s=12)
    ax.legend(fontsize=7,loc='best')
    ax.set_title('Three-stock multidirectional example: exported 10 Hz truth\n'+row['skeleton_id'],fontsize=10)
    fig.tight_layout();fig.savefig(output,dpi=160);plt.close(fig)


def render_revision(attempt,records):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    attempt=Path(attempt);out=attempt/'figures';out.mkdir(exist_ok=True)
    valid=[r for r in records if r['state']=='generated' and r.get('quality_valid') and r.get('audit_passed')]
    regular=[r for r in valid if not r.get('aborted')]
    receipts={'topdowns':[],'timing_pairs':[],'abort_pairs':[],'special_examples':[],'missing_requirements':[]}
    for intent in INTENTS:
        pool=sorted([r for r in regular if r['intent']==intent],
                    key=lambda r:(r['task_result']!='success',r['group_count']<=1,r['mode']!='synchronous',r['skeleton_id']))
        chosen=[]
        for mode in ('same_direction','multi_direction'):
            row=next((r for r in pool if r['approach_mode']==mode),None)
            if row is not None:chosen.append(row)
            else:receipts['missing_requirements'].append({'intent':intent,'requirement':mode+' topdown','reason':'no retained generated example'})
        if not any(r['group_count']>1 for r in chosen):
            row=next((r for r in pool if r['group_count']>1 and r not in chosen),None)
            if row is not None:chosen.append(row)
            else:receipts['missing_requirements'].append({'intent':intent,'requirement':'multiple-group topdown','reason':'no retained generated example'})
        # Still supply two actual trajectories when one approach category is
        # missing; the missing category remains explicit in the coverage receipt.
        remaining=sorted([r for r in pool if r not in chosen],
                         key=lambda r:(r['skeleton_id'] in {c['skeleton_id'] for c in chosen},r['episode_id']))
        chosen.extend(remaining[:max(0,2-len(chosen))])
        if len(chosen)<2:
            receipts['missing_requirements'].append({'intent':intent,'requirement':'two topdowns','reason':'fewer than two retained trajectories'})
        for index,row in enumerate(chosen):
            name=f'{intent}_{index+1}.png';topdown(attempt,row,out/name)
            receipts['topdowns'].append({'figure':name,'episode_id':row['episode_id'],
                'multiple_groups':row['group_count']>1,'multi_direction':row['approach_mode']=='multi_direction',
                'same_direction':row['approach_mode']=='same_direction','task_result':row['task_result']})
    predicates=[('same_direction_monitoring_deployment.png',lambda r:r['approach_mode']=='same_direction' and
                    any(g['role']=='monitoring' for g in r['groups'].values()),deployment_figure),
                ('three_stock_multidirection.png',lambda r:r['approach_mode']=='multi_direction' and
                    any(g['formation_split_count']==3 for g in r['groups'].values()),stock_figure)]
    for name,predicate,renderer in predicates:
        row=next((r for r in sorted(regular,key=lambda r:(r['task_result']!='success',r['episode_id'])) if predicate(r)),None)
        if row is None:
            receipts['missing_requirements'].append({'requirement':name,'reason':'no retained generated example'})
        else:
            renderer(attempt,row,out/name);receipts['special_examples'].append({'figure':name,'episode_id':row['episode_id'],'task_result':row['task_result']})
    pairs=[[r for r in regular if r['skeleton_id']==sid] for sid in sorted({r['skeleton_id'] for r in regular})]
    pairs=[p for p in pairs if len(p)==2 and {r['mode'] for r in p}=={'synchronous','sequential'}]
    pairs.sort(key=lambda p:(p[0]['group_count']<=1,any(r['task_result']!='success' for r in p),p[0]['skeleton_id']))
    for i,pair in enumerate(pairs[:2]):
        name=f'paired_timing_{i+1}.png';paired_timing(attempt,pair,out/name)
        receipts['timing_pairs'].append({'figure':name,'skeleton_id':pair[0]['skeleton_id'],'group_count':pair[0]['group_count']})
    if len(pairs)<2:receipts['missing_requirements'].append({'requirement':'two timing pairs','reason':'fewer than two retained pairs'})
    regular_by_episode={r['episode_id']:r for r in regular}
    aborted=next((r for r in valid if r.get('aborted') and r.get('abort_observation_valid')
                  and r.get('source_episode_id') in regular_by_episode),None)
    source=regular_by_episode.get(aborted.get('source_episode_id')) if aborted else None
    if source:
        fig,axes=plt.subplots(1,2,figsize=(16,8))
        for ax,row,title in zip(axes,[source,aborted],['Referenced regular synchronous episode','Observed withdrawal branch']):
            draw_track(ax,*load(attempt,row));ax.set_title(title,fontsize=11)
        fig.tight_layout();fig.savefig(out/'abort_vs_regular.png',dpi=160);plt.close(fig)
        receipts['abort_pairs'].append({'figure':'abort_vs_regular.png','regular':source['episode_id'],'aborted':aborted['episode_id']})
    else:receipts['missing_requirements'].append({'requirement':'abort and referenced regular side by side','reason':'no retained pair'})
    save_json(out/'figure_coverage.json',receipts)
    return receipts
