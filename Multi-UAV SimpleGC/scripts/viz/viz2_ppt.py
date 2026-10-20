"""PPT-VIZ2 阶段一缩略图：五意图静态面板与同步/递次时间轴。

只读取已完成的 v0.7 first_edition episode 目录；不写数据目录。
合成数据可视化工具，点质量运动学轨迹，不涉及真实无人机控制。

用法（在项目目录 Multi-UAV SimpleGC 下运行）：
  python -B scripts/viz/viz2_ppt.py s1-thumb --run pilot_f005_020d \
      --family family_s15_5024cb2ccea653ae --slot 1 --out <png>
  python -B scripts/viz/viz2_ppt.py s2-thumb --sync-episode <同步版目录> \
      --seq-episode <递次版目录> --out <png>
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import animate_v07 as av

DATA_ROOT = PROJECT.parents[1] / "SwarmData" / "v07_first_edition"

FONT = ["Microsoft YaHei", "Noto Sans SC", "SimHei", "DejaVu Sans"]
PRIMARY = "#0F6E73"
ACCENT = "#B85A1E"
TEXT = "#16243A"
SECONDARY = "#6B7689"
BACKGROUND = "#F6F5F1"
WAIT = "#D9D9D9"
APPROACH = "#BFE3E3"
RETREAT = "#8C8C8C"
GRID = "#E2DED4"

INTENT_ZH = {"transit": "过境", "reconnaissance": "侦察", "monitoring": "游弋监视",
             "feint": "佯动", "penetration": "突防"}
INTENT_ORDER = ("transit", "reconnaissance", "monitoring", "feint", "penetration")
PHASE_ZH = {"waiting": "等待出发", "approach": "进场", "core": "核心作业", "retreat": "撤离"}


def setup():
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import rcParams
    rcParams["font.sans-serif"] = FONT
    rcParams["axes.unicode_minus"] = False


def read_json(path):
    with open(path, encoding="utf-8-sig") as stream:
        return json.load(stream)


def manifest_entries(run):
    return read_json(DATA_ROOT / run / "manifest.json")["retained_episodes"]


def episode_for(run, family, slot, intent, mode):
    for entry in manifest_entries(run):
        if (entry["family_id"] == family and entry["slot"] == slot
                and entry["intent"] == intent and entry["mode"] == mode):
            return DATA_ROOT / run / entry["path"]
    raise SystemExit(f"未找到 skeleton：{run} {family} slot={slot} {intent} {mode}")


def _facility_bounds(scene, targets):
    from scene_v07.geometry import to_shape
    xs, ys = [], []
    for entity in scene["entities"]:
        if entity.get("type") != "facility" or entity.get("id") not in targets:
            continue
        x0, y0, x1, y1 = to_shape(entity["geometry"], 64).bounds
        xs += [x0, x1]
        ys += [y0, y1]
    return xs, ys


def crop_box(eps):
    """全部轨迹 + 目标设施的外包框，外扩 5%。"""
    targets = {group.get("target") for ep in eps for group in ep["groups"] if group.get("target")}
    xs, ys = [], []
    for ep in eps:
        pts = ep["p"].reshape(-1, 2)
        xs += [float(pts[:, 0].min()), float(pts[:, 0].max())]
        ys += [float(pts[:, 1].min()), float(pts[:, 1].max())]
        fx, fy = _facility_bounds(ep["scene"], targets)
        xs += fx
        ys += fy
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    px = 0.05 * (x1 - x0)
    py = 0.05 * (y1 - y0)
    return x0 - px, x1 + px, y0 - py, y1 + py


def _panel(ax, ep, box, now):
    from matplotlib.lines import Line2D
    ax.set_facecolor(BACKGROUND)
    av.draw_map(ax, ep["scene"], box, show_radar=False)
    t = ep["t"]
    k = int(np.clip(np.searchsorted(t, now, side="right") - 1, 0, len(t) - 1))
    for i, agent in enumerate(ep["ids"]):
        color = ep["color"].get(agent, SECONDARY)
        seg = ep["p"][:k + 1, i]
        if len(seg) > 1:
            step = max(1, len(seg) // 900)
            seg = seg[::step]
            ax.plot(seg[:, 0], seg[:, 1], color=color, lw=1.5, alpha=0.9, zorder=4,
                    solid_capstyle="round")
        ax.scatter([ep["p"][k, i, 0]], [ep["p"][k, i, 1]], s=34, color=color,
                   edgecolors="white", linewidths=0.8, zorder=6)
    ax.set_title(ep.get("title", ""), fontsize=13, color=TEXT, pad=7)


def _legend_cell(ax):
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    ax.set_facecolor(BACKGROUND)
    ax.axis("off")
    handles = [
        Line2D([0], [0], color=av.GROUP_COLORS[0], lw=2.2, label="第1编组"),
        Line2D([0], [0], color=av.GROUP_COLORS[1], lw=2.2, label="第2编组"),
        Line2D([0], [0], color=av.GROUP_COLORS[2], lw=2.2, label="第3编组"),
        Line2D([0], [0], marker="o", ls="", markerfacecolor=SECONDARY,
               markeredgecolor="white", markersize=7, label="中间时刻位置"),
    ]
    handles += [Patch(facecolor=color, edgecolor="#8aa5ba", label=name)
                for _, color, name in av.LAYER_STYLE]
    ax.text(0.5, 0.94, "同一场景 · 同一组起点 · 同一编组划分", ha="center", va="top",
            fontsize=13, color=TEXT, weight="bold", transform=ax.transAxes)
    ax.text(0.5, 0.86, "五种意图共用同一地图与裁切框", ha="center", va="top",
            fontsize=10, color=SECONDARY, transform=ax.transAxes)
    ax.legend(handles=handles, loc="center", bbox_to_anchor=(0.5, 0.46), fontsize=10,
              frameon=False, title="图例", title_fontsize=12, labelcolor=TEXT)


def cmd_s1(args):
    setup()
    import matplotlib.pyplot as plt
    entries = {}
    for entry in manifest_entries(args.run):
        if entry["family_id"] == args.family and entry["slot"] == args.slot and entry["mode"] == args.mode:
            entries[entry["intent"]] = entry
    missing = [intent for intent in INTENT_ORDER if intent not in entries]
    if missing:
        raise SystemExit(f"抽签缺少意图：{missing}")
    eps = []
    for intent in INTENT_ORDER:
        ep = av.load_episode(DATA_ROOT / args.run / entries[intent]["path"])
        ep["title"] = INTENT_ZH[intent]
        eps.append(ep)
    windows = [av.time_window([ep]) for ep in eps]
    t0 = min(w[0] for w in windows)
    t1 = max(w[1] for w in windows)
    now = 0.5 * (t0 + t1)
    box = crop_box(eps)
    fig, axes = plt.subplots(2, 3, figsize=(15, 10), dpi=args.dpi, facecolor=BACKGROUND)
    for ax, ep in zip(axes.flat[:5], eps):
        _panel(ax, ep, box, now)
    _legend_cell(axes.flat[5])
    fig.text(0.995, 0.008, "抽象合成场景", ha="right", va="bottom", fontsize=8, color=SECONDARY)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=args.dpi, facecolor=BACKGROUND)
    plt.close(fig)
    print(f"S1 已输出 {out}（{len(eps)} 格，中间时刻 {now:.1f} s）")


# ---------------------------------------------------------------- 时间轴
def _departure_time(t, p):
    """该机离起点位移首次超过 1 m 的帧（无位移则 None）。"""
    d = np.linalg.norm(p - p[0], axis=1)
    idx = np.flatnonzero(d > 1.0)
    return float(t[idx[0]]) if len(idx) else None


def load_timeline(directory):
    directory = Path(directory)
    with np.load(directory / "truth_10hz.npz", allow_pickle=False) as truth:
        t = truth["time_us"].astype(np.int64) / 1e6
        p = truth["p"][:, :, :2].astype(float)
        ids = [str(a) for a in truth["agent_ids"].tolist()]
    labels = read_json(directory / "labels.json")
    observed = labels["agents"]
    last = float(labels["evidence"]["last_observed_s"])
    groups = []
    for gid, group in sorted(labels.get("task_groups", {}).items()):
        members = list(group["assigned"]["members"])
        rows = []
        for agent in members:
            i = ids.index(agent)
            obs = observed.get(agent, {}).get("observed", {})
            core = obs.get("core_event") or {}
            core_t = float(core["t_s"]) if core.get("status") == "known" and core.get("t_s") is not None else None
            work_end = obs.get("work_end_s")
            work_end = float(work_end) if work_end is not None else None
            retreat = obs.get("retreat_event") or {}
            retreat_t = (float(retreat["t_s"]) if retreat.get("status") == "known"
                         and retreat.get("t_s") is not None else None)
            dep = _departure_time(t, p[:, i])
            phases = []
            if dep is not None:
                phases.append(("waiting", 0.0, dep))
                if core_t is not None and core_t > dep:
                    phases.append(("approach", dep, core_t))
                if core_t is not None and work_end is not None and work_end >= core_t:
                    phases.append(("core", core_t, work_end))
                if work_end is not None and retreat_t is not None and retreat_t > work_end:
                    phases.append(("retreat", work_end, retreat_t))
            rows.append({"agent": agent, "core": core_t, "work_end": work_end,
                         "retreat": retreat_t, "departure": dep, "phases": phases})
        rows.sort(key=lambda r: (r["core"] if r["core"] is not None else 1e18, r["agent"]))
        groups.append({"gid": gid, "members": rows})
    return {"groups": groups, "last": last, "t": t, "p": p, "ids": ids}


def _draw_timeline(ax, data, title):
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    ax.set_facecolor(BACKGROUND)
    y = 0.0
    group_bands = []
    tick_pos, tick_labels = [], []
    for gi, group in enumerate(data["groups"]):
        start_y = y
        for row in group["members"]:
            for phase, a, b in row["phases"]:
                color = {"waiting": WAIT, "approach": APPROACH, "core": PRIMARY, "retreat": RETREAT}[phase]
                ax.broken_barh([(a, b - a)], (y - 0.30, 0.60), facecolors=color,
                               edgecolors="none", zorder=3)
            if row["core"] is not None:
                ax.scatter([row["core"]], [y], marker="^", s=58, color=ACCENT,
                           edgecolors="white", linewidths=0.5, zorder=5)
            tick_pos.append(y)
            tick_labels.append(str(len(tick_pos) - sum(len(g["members"]) for g in data["groups"][:gi])))
            y += 1.0
        end_y = y - 1.0
        group_bands.append((gi, start_y, end_y))
        # 组内最早/最晚开始核心作业
        cores = [r["core"] for r in group["members"] if r["core"] is not None]
        if cores:
            lo, hi = min(cores), max(cores)
            ax.vlines([lo, hi], start_y - 0.45, end_y + 0.45, colors=SECONDARY,
                      linestyles=(0, (3, 3)), lw=1.0, zorder=2)
            ax.text(0.5 * (lo + hi), end_y + 0.72, f"相差 {hi - lo:.1f} 秒", ha="center",
                    va="bottom", fontsize=9, color=ACCENT,
                    bbox={"boxstyle": "round,pad=0.18", "fc": BACKGROUND, "ec": "none", "alpha": 0.88})
        y += 1.1  # 组间留白
    # 组标签与分隔线
    for gi, start_y, end_y in group_bands:
        center = 0.5 * (start_y + end_y)
        ax.text(-0.012, center, f"第{gi + 1}编组（{end_y - start_y + 1:.0f}架）",
                transform=ax.get_yaxis_transform(), ha="right", va="center",
                fontsize=10, color=TEXT, clip_on=False)
        if gi:
            ax.axhline(start_y - 0.40, color=GRID, lw=0.8, zorder=1)
    ax.set_yticks(tick_pos)
    ax.set_yticklabels(tick_labels, fontsize=8, color=SECONDARY)
    ax.set_ylim(-0.8, y - 0.2)
    ax.invert_yaxis()
    ax.set_title(title, loc="left", fontsize=14, color=TEXT, pad=6)
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    handles = [Patch(facecolor=c, label=PHASE_ZH[k]) for k, c in
               (("waiting", WAIT), ("approach", APPROACH), ("core", PRIMARY), ("retreat", RETREAT))]
    handles.append(Line2D([0], [0], marker="^", ls="", color=ACCENT, markersize=7, label="开始核心作业"))
    ax.legend(handles=handles, loc="upper right", fontsize=8, frameon=False, ncol=5,
              labelcolor=TEXT, bbox_to_anchor=(1.0, 1.16))


def cmd_s2(args):
    setup()
    import matplotlib.pyplot as plt
    sync = load_timeline(args.sync_episode)
    seq = load_timeline(args.seq_episode)
    tmax = max([sync["last"], seq["last"]] + [r["retreat"] or 0 for d in (sync, seq)
                                               for g in d["groups"] for r in g["members"]])
    fig, axes = plt.subplots(2, 1, figsize=(18, 9), dpi=args.dpi, sharex=True, facecolor=BACKGROUND)
    _draw_timeline(axes[0], sync, "同步版")
    _draw_timeline(axes[1], seq, "递次版")
    for ax in axes:
        ax.set_xlim(0, tmax)
    axes[0].tick_params(labelbottom=False)
    axes[1].set_xlabel("仿真时间（秒）", fontsize=11, color=TEXT)
    fig.text(0.995, 0.006, "抽象合成场景", ha="right", va="bottom", fontsize=8, color=SECONDARY)
    fig.subplots_adjust(left=0.13, right=0.985, top=0.93, bottom=0.08, hspace=0.42)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=args.dpi, facecolor=BACKGROUND)
    plt.close(fig)
    print(f"S2 已输出 {out}（时间轴 0–{tmax:.1f} s）")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("s1-thumb")
    p.add_argument("--run", required=True)
    p.add_argument("--family", required=True)
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--mode", default="synchronous", choices=("synchronous", "sequential"))
    p.add_argument("--dpi", type=int, default=100)
    p.add_argument("--out", required=True)
    p = sub.add_parser("s2-thumb")
    p.add_argument("--sync-episode", required=True)
    p.add_argument("--seq-episode", required=True)
    p.add_argument("--dpi", type=int, default=100)
    p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    {"s1-thumb": cmd_s1, "s2-thumb": cmd_s2}[args.cmd](args)


if __name__ == "__main__":
    main()
