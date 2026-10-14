"""Entry-point plotting for S2 expansion role episodes (actual 10 Hz tracks only)."""
import numpy as np

from scripts.v07_s2_plotting import map_axes


def plot_role_episode(scene, run, labels, skeleton, path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.colors import Normalize
    fig, ax = plt.subplots(figsize=(9, 8))
    map_axes(ax, scene)
    norm = Normalize(0, run["time_us"][-1] / 1e6)
    t = run["time_us"]
    for j, a in enumerate(run["agent_ids"]):
        xy = run["p"][:, j, :2]
        lc = LineCollection(np.stack([xy[:-1], xy[1:]], axis=1), cmap="viridis", norm=norm, linewidths=1.6)
        lc.set_array(t[:-1] / 1e6); ax.add_collection(lc)
        ax.scatter(*xy[0], color="#42376e", marker="o", s=16)
        ref = skeleton["references"][a]
        ax.scatter(*ref["endpoint_enu_m"][:2], marker="*", s=70, facecolors="none", edgecolors="#ac4868",
                   label="Own endpoint (plan)" if j == 0 else None)
        planned=np.asarray(ref["points_enu_m"])[:,:2]
        ax.plot(planned[:,0],planned[:,1],ls="--",lw=.6,color="#7c7c7c",alpha=.5,
                label="Planned route" if j==0 else None)
        station=(ref.get("observation_point_enu_m") or ref.get("planned_depth_point_enu_m")
                 or ref.get("planned_orbit_entry_enu_m")
                 or (ref["endpoint_enu_m"] if skeleton["role"]=="intrusion" else None))
        if station is not None:
            ax.scatter(*station[:2],marker="D",s=36,facecolors="none",edgecolors="#236bb2",
                       label="Independent work station (plan)" if j==0 else None)
        chord = ref.get("planned_chord")
        if chord:
            ax.plot(*np.array([chord["entry_m"], chord["exit_m"]]).T, ls=":", lw=.8, color="#994982",
                    label="Planned chord" if j == 0 else None)
        contribution = labels["agents"][a]["observed"]["contribution"]
        core = labels["agents"][a]["observed"]["core_event"]["frame_index"]
        if core is not None:
            ax.scatter(*xy[core], marker="^", s=34, color="#d1495b", label="Observed core event" if j == 0 else None, zorder=5)
        last = contribution.get("warning_last_inside_frame")
        if last is not None:
            ax.scatter(*xy[last], marker="s", s=24, color="#edae49", label="Observed warning exit" if j == 0 else None, zorder=5)
        ax.annotate(a, xy[-1], xytext=(6, 6), textcoords="offset points", fontsize=7)
    fig.colorbar(lc, ax=ax, pad=.02, label="Common simulation time (s)", shrink=.78)
    group = next(iter(labels["task_groups"].values())); coord = group["observed"]["coordination"]
    span = group["observed"]["approach_span_deg"]
    event_range = "unknown" if coord["event_range_s"] is None else f"{coord['event_range_s']:.1f} s"
    ax.set_title(title + "\n" + f"Observed: {coord['classification']} | event range {event_range} | "
                 f"approach span {'n/a' if span is None else f'{span:.0f} deg'} | result {group['result']['status']}", fontsize=10)
    ax.legend(loc="lower left", fontsize=7)
    fig.text(.08, .02, "Actual exported truth at 10 Hz; o = initial state. Abstract synthetic scene.", fontsize=8)
    fig.tight_layout(rect=(0, .035, 1, 1)); fig.savefig(path, dpi=135); plt.close(fig)
