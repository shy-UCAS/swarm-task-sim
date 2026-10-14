"""Entry-point plotting only: actual 10 Hz tracks and paired core-event times."""
from pathlib import Path
import numpy as np


def map_axes(ax,scene):
    from matplotlib.patches import Polygon as PlotPolygon
    from scene_v07.geometry import to_shape
    colors={"warning":"#edf2f6","alert":"#d4e2ee","protected":"#a6c4da"}
    for name in ("warning","alert","protected"):
        for entity in scene["entities"]:
            if entity.get("layer")==name:
                shape=to_shape(entity["geometry"],64)
                ax.add_patch(PlotPolygon(list(shape.exterior.coords),facecolor=colors[name],edgecolor="#6486a0",lw=.7))
    for e in scene["entities"]:
        if e["type"] in ("facility","hard_constraint_obstacle"):
            shape=to_shape(e["geometry"],64)
            ax.add_patch(PlotPolygon(list(shape.exterior.coords),facecolor="#416c86" if e["type"]=="facility" else "#d9c5bd",
                                    edgecolor="#574c49",lw=.8,hatch="///" if e["type"]=="hard_constraint_obstacle" else None))
            if e["type"]=="facility":
                ax.text(shape.centroid.x,shape.centroid.y,e["id"],fontsize=8,ha="center")
        elif e["type"]=="radar":
            ax.scatter(*e["geometry"]["position_m"],marker="D",s=22,color="#aa4f6b")
    for e in scene["entry_zones"]:
        shape=to_shape(e["geometry"])
        ax.add_patch(PlotPolygon(list(shape.exterior.coords),facecolor="#86d7c3",edgecolor="#327765"))
    world=to_shape(scene["world"]["geometry"])
    x0,y0,x1,y1=world.bounds
    ax.set(xlim=(x0-40,x1+40),ylim=(y0-40,y1+40),xlabel="East (m)",ylabel="North (m)",aspect="equal")
    ax.grid(alpha=.12)


def plot_episode(scene,run,labels,path,title,skeleton=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.colors import Normalize
    fig,ax=plt.subplots(figsize=(9,8))
    map_axes(ax,scene)
    survey=None if skeleton is None else skeleton.get("survey")
    if survey is not None and "geometry" in survey:
        from matplotlib.patches import Polygon as PlotPolygon
        from task_v07.geometry import offset_geometry,radial_points_exact
        sector=survey["geometry"];center=sector["center_m"]
        angles=np.linspace(sector["start_angle_rad"],sector["start_angle_rad"]+sector["angle_span_rad"],200)
        inner=radial_points_exact(offset_geometry(sector["base_geometry"],sector["inner_offset_m"]),center,angles)
        outer=radial_points_exact(offset_geometry(sector["base_geometry"],sector["outer_offset_m"]),center,angles)
        ax.add_patch(PlotPolygon(np.concatenate((outer,inner[::-1])),facecolor="#d997ca",edgecolor="#994982",
                                alpha=.32,lw=1.4,label="Declared survey sector"))
        for j,(a,ref) in enumerate(sorted(skeleton["references"].items())):
            ax.scatter(*ref["endpoint_enu_m"][:2],marker="*",s=85,facecolors="none",edgecolors="#ac4868",
                       label="Withdrawal point (plan)" if j==0 else None)
        ax.legend(loc="lower left",fontsize=8)
    norm=Normalize(0,run["time_us"][-1]/1e6)
    for i,a in enumerate(run["agent_ids"]):
        xy=run["p"][:,i,:2]
        segments=np.stack([xy[:-1],xy[1:]],axis=1)
        lc=LineCollection(segments,cmap="viridis",norm=norm,linewidths=1.8)
        lc.set_array(run["time_us"][:-1]/1e6);ax.add_collection(lc)
        ax.scatter(*xy[0],color="#42376e",marker="o",s=18)
        ax.scatter(*xy[-1],color="#e7bd42",marker="x",s=36)
        offsets=[(10,14),(10,-18),(-52,18),(-52,-20)]
        offset=offsets[sorted(run["agent_ids"]).index(a)%len(offsets)]
        ax.annotate(a,xy[-1],xytext=offset,textcoords="offset points",fontsize=8,
                    arrowprops={"arrowstyle":"-","color":"#687683","lw":.6})
    fig.colorbar(lc,ax=ax,pad=.02,label="Common simulation time (s)",shrink=.78)
    group=next(iter(labels["task_groups"].values()));coord=group["observed"]["coordination"]
    event_range="unknown" if coord["event_range_s"] is None else f"{coord['event_range_s']:.1f} s"
    ax.set_title(title+"\n"+f"Observed: {coord['classification']} | event range {event_range} | result {group['result']['status']}",fontsize=11)
    fig.text(.08,.02,"Actual exported truth at 10 Hz; o = initial state, x = final sampled state. Abstract development scene.",fontsize=8)
    if survey is not None and "area_m2" in survey:
        ax.set_title(ax.get_title()+f"\nSurvey {survey['area_m2']/1e6:.3f} km2 | {survey['angle_span_deg']:.1f} deg | {survey['strip_count']} strips",fontsize=10)
    fig.tight_layout(rect=(0,.035,1,1));fig.savefig(path,dpi=135);plt.close(fig)


def plot_pair(rows,path,title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4),sharex=True,sharey=True)
    all_times=[t for row in rows for t in row["event_times_s"].values() if t is not None]
    for ax,row in zip(axes,rows):
        ids=sorted(row["event_times_s"])
        for y,a in enumerate(ids):
            t=row["event_times_s"][a]
            if t is not None:
                ax.hlines(y,0,t,color="#d5dce4",lw=1)
                ax.scatter(t,y,c="#326c9d",s=50);ax.annotate(f"{t:.1f}s",(t,y),xytext=(6,7),textcoords="offset points",fontsize=9)
            else:
                ax.text(.03,y,"unknown (not observed)",transform=ax.get_yaxis_transform(),color="#a34242",va="center")
        ax.set_ylim(-.5,len(ids)-.4)
        ax.set_yticks(range(len(ids)),ids);ax.set_xlabel("Common simulation time (s)")
        event_range="unknown" if row["event_range_s"] is None else f"{row['event_range_s']:.1f} s"
        ax.set_title(f"{row['mode']} -> {row['observed_coordination']}\nrange = {event_range}")
        ax.grid(axis="x",alpha=.2)
    if all_times:
        axes[0].set_xlim(max(0,min(all_times)-30),max(all_times)+35)
    fig.suptitle(title+" | start core operation, measured from 10 Hz truth")
    fig.tight_layout();fig.savefig(path,dpi=135);plt.close(fig)
