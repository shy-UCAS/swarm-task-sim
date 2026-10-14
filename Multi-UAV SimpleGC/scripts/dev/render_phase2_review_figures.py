"""Full-map and work-area views of the four selected real 10 Hz trajectories."""
import sys,json
from pathlib import Path
import numpy as np
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from scripts.v07_s2_plotting import map_axes


def render(source,output,title):
    scene=json.loads((source/'public_scene.json').read_text());sk=json.loads((source.parent/'skeleton.json').read_text());labels=json.loads((source/'labels.json').read_text());metrics=json.loads((source/'metrics.json').read_text())
    with np.load(source/'truth_10hz.npz') as truth:
        t=truth['time_us']/1e6;positions=truth['p'];ids=truth['agent_ids'].tolist()
    stations={}
    for a in ids:
        ref=sk['references'][a];stations[a]=np.array(ref.get('observation_point_enu_m') or ref.get('planned_depth_point_enu_m') or ref.get('planned_orbit_entry_enu_m') or ref['endpoint_enu_m'])[:2]
    fig,(full,zoom)=plt.subplots(1,2,figsize=(15,7.5),gridspec_kw={'width_ratios':[1.25,1.]})
    norm=Normalize(0,t[-1]);station_points=np.array(list(stations.values()));lo=station_points.min(axis=0);hi=station_points.max(axis=0);mid=(lo+hi)/2;half=max(180.,.65*float((hi-lo).max()))
    for ax in (full,zoom):
        map_axes(ax,scene)
        for txt in ax.texts:txt.set_clip_on(True)
        for j,a in enumerate(ids):
            xy=positions[:,j,:2];ref=sk['references'][a];planned=np.array(ref['points_enu_m'])[:,:2]
            ax.plot(planned[:,0],planned[:,1],ls='--',lw=.7,c='#6f6f6f',alpha=.65,label='Planned route' if j==0 else None)
            lc=LineCollection(np.stack([xy[:-1],xy[1:]],axis=1),cmap='viridis',norm=norm,linewidths=1.35);lc.set_array(t[:-1]);ax.add_collection(lc)
            ax.scatter(*xy[0],s=14,c='#44375e',zorder=4)
            ax.scatter(*ref['endpoint_enu_m'][:2],s=55,marker='*',facecolors='none',edgecolors='#ac4868',zorder=5,label='Own endpoint (plan)' if j==0 else None)
            ax.scatter(*stations[a],s=42,marker='D',facecolors='none',edgecolors='#1464bd',zorder=6,label='Work station (plan)' if j==0 else None)
            k=labels['agents'][a]['observed']['core_event']['frame_index']
            if k is not None:ax.scatter(*xy[k],s=25,marker='^',c='#d1495b',zorder=5,label='Core event (measured)' if j==0 else None)
            if ax is zoom:ax.annotate(a[-2:],stations[a],xytext=(5,8 if j%2==0 else -12),textcoords='offset points',fontsize=8,fontweight='bold',color='#18324f',clip_on=True)
        ax.set_aspect('equal');ax.tick_params(labelsize=8)
    full.set_title('Full map',fontsize=11);zoom.set_title('Work area: numbers are UAV IDs',fontsize=11)
    zoom.set_xlim(mid[0]-half,mid[0]+half);zoom.set_ylim(mid[1]-half,mid[1]+half)
    full.legend(loc='lower left',fontsize=7,framealpha=.95)
    group=next(iter(labels['task_groups'].values()));coord=group['observed']['coordination']
    fig.suptitle(f"{title} | actual {coord['classification']} | result {group['result']['status']}\nMinimum actual separation {metrics['minimum_separation_m']:.3f} m; 10 Hz exported truth",fontsize=12)
    fig.colorbar(lc,ax=zoom,pad=.03,shrink=.75,label='Common simulation time (s)')
    fig.subplots_adjust(top=.87,bottom=.10,left=.055,right=.97,wspace=.20)
    fig.text(.055,.025,'Solid colour = actual trajectory; dashed = plan; diamonds = independent planned stations. Abstract synthetic scenes.',fontsize=8)
    fig.savefig(output,dpi=150);plt.close(fig)


def main():
    base,monitor,observation=map(Path,sys.argv[1:4]);out=observation/'review_figures';out.mkdir(exist_ok=False)
    selected=[('close_observation',observation/'family_s12_4d13d93f9171c446_ext_001_regular/synchronous','Close observation'),('monitoring',monitor/'family_s12_aa4c66be8e85d64d_ext_002_regular/synchronous','Monitoring'),('feint',base/'family_s12_aa4c66be8e85d64d_ext_003_regular/synchronous','Feint'),('intrusion',base/'family_s12_aa4c66be8e85d64d_ext_004_regular/synchronous','Intrusion')]
    for name,source,title in selected:
        render(source,out/(name+'.png'),title);print(str(out/(name+'.png')),flush=True)
    (out/'sources.json').write_text(json.dumps({name:str(source) for name,source,title in selected},indent=2),encoding='utf-8')
if __name__=='__main__':main()
