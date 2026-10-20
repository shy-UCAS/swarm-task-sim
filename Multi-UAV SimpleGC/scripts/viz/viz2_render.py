"""PPT-VIZ2 阶段二正式图：A 规划器分步、B 五意图、C 同步/递次、D 校准对照。

只读取已完成的 v0.7 first_edition episode 与 M3 r3 校准证据；不写数据目录。
合成数据可视化工具，点质量运动学轨迹，不涉及真实无人机控制。
"""
import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import animate_v07 as av
import viz2_ppt as vp

DATA_ROOT = PROJECT.parents[1] / "SwarmData" / "v07_first_edition"
M3_ROOT = PROJECT.parents[1] / "SwarmData" / "fast_dynamics" / "m3"
OUT_ROOT = PROJECT.parents[1] / "SwarmData" / "ppt_media" / "ppt_v2"

PRIMARY, ACCENT, TEXT, SECONDARY, BACKGROUND = (
    vp.PRIMARY, vp.ACCENT, vp.TEXT, vp.SECONDARY, vp.BACKGROUND)
INTENT_ZH = vp.INTENT_ZH
INTENT_ORDER = vp.INTENT_ORDER
GROUP_COLORS = av.GROUP_COLORS
PLANNING_MARGIN_M = 35.0
SITL_GRAY = "#4A4A4A"

# 阶段二固定样例
B_RUN, B_FAMILY, B_SLOT = "pilot_f005_020d", "family_s15_5024cb2ccea653ae", 1
C_SKELETON = "family_s15_5024cb2ccea653ae_ext_005_regular"
D_TASKS = (
    ("reconnaissance_0092_v00", "往返扫描", "equal_strip_lawnmower", -0.01680753437056476),
    ("patrol_0081_v00", "闭合环线", "staggered_same_loop", -0.018045300946957724),
    ("rapid_passage_0149_v00", "带折返", "line_abreast", -0.01716523071383718),
)


def read_json(path):
    with open(path, encoding="utf-8-sig") as stream:
        return json.load(stream)


def save(fig, path, dpi=100):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, facecolor=BACKGROUND)
    print(f"已输出 {path}")


def style_axes(ax):
    ax.set_facecolor(BACKGROUND)
    for spine in ax.spines.values():
        spine.set_color("#C5CED6")


# ---------------------------------------------------------------- 通用地图面板
class MapPanel:
    """静态地图 + 动态全历史尾迹/当前位置/核心事件。"""

    def __init__(self, ax, ep, box, title):
        ax.set_facecolor(BACKGROUND)
        av.draw_map(ax, ep["scene"], box, show_radar=False)
        self.ep = ep
        self.lines, self.dots, self.cores = {}, {}, {}
        for agent in ep["ids"]:
            color = ep["color"].get(agent, SECONDARY)
            line, = ax.plot([], [], color=color, lw=1.7, alpha=0.9, zorder=4,
                            solid_capstyle="round")
            dot = ax.scatter([], [], s=34, color=color, edgecolors="white",
                             linewidths=0.8, zorder=6)
            core = ax.scatter([], [], marker="^", s=52, color=ACCENT,
                              edgecolors="white", linewidths=0.5, zorder=7)
            self.lines[agent], self.dots[agent], self.cores[agent] = line, dot, core
        ax.set_title(title, fontsize=15, color=TEXT, pad=8)
        style_axes(ax)

    def update(self, now):
        ep = self.ep
        t = ep["t"]
        k = int(np.clip(np.searchsorted(t, now, side="right") - 1, 0, len(t) - 1))
        for i, agent in enumerate(ep["ids"]):
            seg = ep["p"][:k + 1, i]
            if len(seg) > 1:
                step = max(1, len(seg) // 700)
                seg = seg[::step]
                self.lines[agent].set_data(seg[:, 0], seg[:, 1])
            else:
                self.lines[agent].set_data([], [])
            self.dots[agent].set_offsets([ep["p"][k, i]])
            frame = ep["core"].get(agent)
            if frame is not None and frame <= k:
                self.cores[agent].set_offsets([ep["p"][frame, i]])
            else:
                self.cores[agent].set_offsets(np.empty((0, 2)))


def animation_window(eps, fraction=0.85):
    """五格共用的公共活动窗口：结束于最早结束的 episode，起点取窗口 80%。

    这样首帧各组都已有轨迹，且整段 GIF 中五格都仍在运动；不会出现
    四个较短意图已经结束、只剩监视在动的静止面板。
    """
    t0 = min(av.time_window([ep])[0] for ep in eps)
    common_end = min(max(ep["last_move"]) for ep in eps)
    release_max = max(max(ep["release"].values()) for ep in eps)
    start = max(release_max + 0.02 * max(common_end - release_max, 1.0),
                t0 + fraction * max(common_end - t0, 1.0))
    return t0, common_end, min(start, common_end - 1e-6)


def render_gif(fig, panels, clock, n_frames, out_path, first_png, fps=12, hold=2.0, colors=64):
    from PIL import Image
    out_path, first_png = Path(out_path), Path(first_png)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames = []
    for k in range(n_frames):
        now = clock(k)
        for panel in panels:
            panel.update(now)
        fig.canvas.draw()
        rgba = np.asarray(fig.canvas.buffer_rgba())
        frames.append(Image.fromarray(rgba[:, :, :3].copy()))
    frames[0].save(first_png)
    picks = [frames[0], frames[len(frames) // 2], frames[-1]]
    sheet = Image.new("RGB", (picks[0].width, picks[0].height * len(picks)))
    for j, image in enumerate(picks):
        sheet.paste(image, (0, image.height * j))
    palette = sheet.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    quantized = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    durations = [int(1000 / fps)] * n_frames
    durations[-1] = int(hold * 1000)
    quantized[0].save(out_path, save_all=True, append_images=quantized[1:],
                      duration=durations, loop=0, optimize=True, disposal=1)
    size_mb = out_path.stat().st_size / 2 ** 20
    print(f"已输出 {out_path}（{n_frames} 帧，{size_mb:.2f} MB）及首帧 {first_png}")
    if size_mb > 8:
        print("[警告] GIF 超过 8 MB")
    if n_frames > 150:
        print("[警告] 帧数超过 150")


# ---------------------------------------------------------------- 图 A
def _buffer_outline(ax, geometry, margin, color=SECONDARY):
    from scene_v07.geometry import to_shape
    shape = to_shape(geometry, 96).buffer(margin)
    if shape.geom_type == "Polygon":
        xs, ys = shape.exterior.xy
    else:
        xs, ys = [], []
        for part in shape.geoms:
            x, y = part.exterior.xy
            xs, ys = list(xs) + list(x) + [None], list(ys) + list(y) + [None]
    ax.plot(xs, ys, color=color, lw=1.2, ls=(0, (5, 4)), zorder=3)


def _draw_scan(ax, ref, color, lw, alpha, zorder):
    pts = np.asarray(ref.get("scan_lane_endpoints_m") or [], float)
    if len(pts) < 2:
        return
    ax.plot(pts[:, 0], pts[:, 1], color=color, lw=lw + 6, alpha=0.14, zorder=zorder,
            solid_capstyle="round")
    ax.plot(pts[:, 0], pts[:, 1], color=color, lw=lw, alpha=alpha, zorder=zorder + 1,
            solid_capstyle="round")


def cmd_a(args):
    vp.setup()
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.patches import Polygon as PlotPolygon
    from task_v07.expansion.role_planners import blocked_planner, zones_of

    ep_dir = DATA_ROOT / args.run / "episodes" / args.skeleton / "synchronous"
    ep = av.load_episode(ep_dir)
    task = read_json(ep_dir / "task.json")
    labels = ep["labels"]
    groups = sorted(labels["task_groups"])
    group_id = args.group if args.group in groups else groups[0]
    members = labels["task_groups"][group_id]["assigned"]["members"]
    agent = args.agent if args.agent in members else sorted(members)[0]
    target = labels["task_groups"][group_id]["assigned"]["target"]
    ref = task["references"][agent]

    pool_path = DATA_ROOT / args.run / "planning" / args.skeleton / "candidate_pool.pkl"
    import pickle
    with pool_path.open("rb") as stream:
        pool = pickle.load(stream)["pool"]
    selected = 0
    actual = np.asarray(ref["points_enu_m"], float)
    for i, candidate in enumerate(pool):
        other = np.asarray(candidate["skeleton"]["references"][agent]["points_enu_m"], float)
        if other.shape == actual.shape and float(np.abs(other - actual).max()) < 1e-9:
            selected = i
            break

    # 裁切：全部 8 架轨迹 + 目标设施 + 5%
    box = vp.crop_box([ep])
    fig, axes = plt.subplots(1, 4, figsize=(24, 10), dpi=args.dpi, facecolor=BACKGROUND)

    # ① 自由空间
    ax = axes[0]
    ax.set_facecolor(BACKGROUND)
    av.draw_map(ax, ep["scene"], box, show_radar=False)
    for entity in ep["scene"]["entities"]:
        if entity.get("type") == "hard_constraint_obstacle":
            _buffer_outline(ax, entity["geometry"], PLANNING_MARGIN_M)
    starts = np.array([s["position_enu_m"][:2] for s in task["initial_states"]], float)
    center = starts.mean(axis=0)
    ax.scatter([center[0]], [center[1]], marker="*", s=220, color=PRIMARY,
               edgecolors="white", linewidths=0.8, zorder=8)
    ax.annotate("共享起点", (center[0], center[1]), xytext=(34, 58),
                textcoords="offset points", fontsize=10, color=PRIMARY,
                weight="bold", zorder=9,
                bbox={"boxstyle": "round,pad=0.2", "fc": BACKGROUND, "ec": "none", "alpha": 0.9},
                arrowprops={"arrowstyle": "-", "color": PRIMARY, "lw": 0.8})
    ax.set_title("自由空间", fontsize=16, color=TEXT, pad=10)
    ax.legend(handles=[Line2D([0], [0], color=SECONDARY, lw=1.2, ls=(0, (5, 4)),
                              label="限制区膨胀边界（35 m）"),
                       Line2D([0], [0], marker="*", ls="", color=PRIMARY, markersize=12,
                              label="共享起点")],
              loc="lower right", fontsize=8, frameon=False, labelcolor=TEXT)
    style_axes(ax)

    # ② 作业模板
    ax = axes[1]
    ax.set_facecolor(BACKGROUND)
    av.draw_map(ax, ep["scene"], box, show_radar=False)
    for i, candidate in enumerate(pool):
        if i == selected:
            continue
        _draw_scan(ax, candidate["skeleton"]["references"][agent], SECONDARY, 0.8, 0.55, 5)
    _draw_scan(ax, ref, PRIMARY, 2.6, 1.0, 7)
    ax.scatter([actual[0, 0]], [actual[0, 1]], s=45, color=PRIMARY,
               edgecolors="white", linewidths=0.7, zorder=9)
    ax.text(0.03, 0.96, f"实际模板（{ref.get('scan_strip_count', '?')} 条扫描带）",
            transform=ax.transAxes, ha="left", va="top", fontsize=9, color=PRIMARY,
            weight="bold", zorder=10,
            bbox={"boxstyle": "round,pad=0.2", "fc": BACKGROUND, "ec": "none", "alpha": 0.9})
    ax.set_title("作业模板", fontsize=16, color=TEXT, pad=10)
    ax.legend(handles=[Line2D([0], [0], color=PRIMARY, lw=2.6, label="实际扫描条带"),
                       Line2D([0], [0], color=SECONDARY, lw=0.8, label="其他候选")],
              loc="lower right", fontsize=8, frameon=False, labelcolor=TEXT)
    style_axes(ax)

    # ③ 可见图最短路
    ax = axes[2]
    ax.set_facecolor(BACKGROUND)
    av.draw_map(ax, ep["scene"], box, show_radar=False)
    alert_ids = [e["id"] for e in ep["scene"]["entities"] if e.get("layer") == "alert"]
    planner = blocked_planner(ep["scene"], alert_ids, PLANNING_MARGIN_M)
    for i, vertex in enumerate(planner.vertices):
        for j, _ in planner.adjacency[i]:
            if j > i:
                other = planner.vertices[j]
                ax.plot([vertex[0], other[0]], [vertex[1], other[1]], color="#B8B8B8",
                        lw=0.35, alpha=0.55, zorder=2)
    path = np.asarray(ref["points_enu_m"], float)
    ax.plot(path[:, 0], path[:, 1], color=PRIMARY, lw=8, alpha=0.14, zorder=5)
    ax.plot(path[:, 0], path[:, 1], color=PRIMARY, lw=2.6, zorder=6)
    points_free = all(planner.free(p.tolist()) for p in path[:, :2])
    segments_visible = all(planner.visible(path[i, :2].tolist(), path[i + 1, :2].tolist())
                           for i in range(len(path) - 1))
    print(f"A 可见图：{len(planner.vertices)} 顶点 / "
          f"{sum(len(a) for a in planner.adjacency) // 2} 边；"
          f"已存路径点自由={points_free}，线段可见={segments_visible}")
    ax.set_title("可见图最短路", fontsize=16, color=TEXT, pad=10)
    ax.legend(handles=[Line2D([0], [0], color="#B8B8B8", lw=0.8, label="可见图边"),
                       Line2D([0], [0], color=PRIMARY, lw=2.6, label="已存规划路径")],
              loc="lower right", fontsize=8, frameon=False, labelcolor=TEXT)
    style_axes(ax)

    # ④ 仿真轨迹
    ax = axes[3]
    ax.set_facecolor(BACKGROUND)
    av.draw_map(ax, ep["scene"], box, show_radar=False)
    handles = []
    for gid, tg in sorted(labels["task_groups"].items()):
        color = GROUP_COLORS[list(sorted(labels["task_groups"])).index(gid) % len(GROUP_COLORS)]
        for member in tg["assigned"]["members"]:
            i = ep["ids"].index(member)
            ax.plot(ep["p"][:, i, 0], ep["p"][:, i, 1], color=color, lw=1.1,
                    alpha=0.75, zorder=4)
            frame = ep["core"].get(member)
            if frame is not None:
                ax.scatter([ep["p"][frame, i, 0]], [ep["p"][frame, i, 1]], marker="^",
                           s=52, color=ACCENT, edgecolors="white", linewidths=0.5, zorder=7)
        handles.append(Line2D([0], [0], color=color, lw=1.6,
                              label=f"第{list(sorted(labels['task_groups'])).index(gid) + 1}编组"))
    handles.append(Line2D([0], [0], marker="^", ls="", color=ACCENT, markersize=7,
                          label="开始执行任务"))
    ax.set_title("仿真轨迹", fontsize=16, color=TEXT, pad=10)
    ax.legend(handles=handles, loc="lower right", fontsize=8, frameon=False, labelcolor=TEXT)
    style_axes(ax)

    fig.text(0.995, 0.008, "抽象合成场景", ha="right", va="bottom", fontsize=9, color=SECONDARY)
    fig.subplots_adjust(left=0.012, right=0.988, top=0.90, bottom=0.025, wspace=0.06)
    save(fig, args.out, args.dpi)
    plt.close(fig)


# ---------------------------------------------------------------- 图 B
def cmd_b(args):
    vp.setup()
    import matplotlib.pyplot as plt
    entries = {}
    for entry in vp.manifest_entries(args.run):
        if entry["family_id"] == args.family and entry["slot"] == args.slot:
            entries[entry["intent"]] = entry
    eps = []
    for intent in INTENT_ORDER:
        ep = av.load_episode(DATA_ROOT / args.run / entries[intent]["path"])
        eps.append(ep)
    box = vp.crop_box(eps)
    t0, t1, start = animation_window(eps, fraction=0.92)
    fig, axes = plt.subplots(2, 3, figsize=(18, 12), dpi=args.dpi, facecolor=BACKGROUND)
    panels = []
    for ax, ep, intent in zip(axes.flat[:5], eps, INTENT_ORDER):
        panels.append(MapPanel(ax, ep, box, INTENT_ZH[intent]))
    vp._legend_cell(axes.flat[5], dot_label="当前位置")
    clock = fig.text(0.5, 0.972, "", ha="center", va="top", fontsize=12, color=TEXT)
    fig.text(0.995, 0.008, "抽象合成场景", ha="right", va="bottom", fontsize=8, color=SECONDARY)
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))

    def now_for(k):
        return start + (t1 - start) * k / max(args.frames - 1, 1)

    def update_clock(k):
        now = now_for(k)
        for panel in panels:
            panel.update(now)
        clock.set_text(f"仿真时间 {av.fmt_clock(now - t0)}")
        return now

    # render_gif 内部会再次 update；这里用包装保持时钟一致
    class ClockPanel:
        def __init__(self):
            self.k = 0
        def update(self, now):
            pass

    n = args.frames
    from PIL import Image
    frames = []
    for k in range(n):
        now = now_for(k)
        clock.set_text(f"仿真时间 {av.fmt_clock(now - t0)}")
        for panel in panels:
            panel.update(now)
        fig.canvas.draw()
        rgba = np.asarray(fig.canvas.buffer_rgba())
        frames.append(Image.fromarray(rgba[:, :, :3].copy()))
    first_png = Path(args.out) / "b_first_frame.png"
    first_png.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(first_png)
    picks = [frames[0], frames[len(frames) // 2], frames[-1]]
    sheet = Image.new("RGB", (picks[0].width, picks[0].height * len(picks)))
    for j, image in enumerate(picks):
        sheet.paste(image, (0, image.height * j))
    palette = sheet.quantize(colors=args.colors, method=Image.Quantize.MEDIANCUT)
    quantized = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    durations = [int(1000 / args.fps)] * n
    durations[-1] = int(args.hold * 1000)
    gif = Path(args.out) / "b_five_intents.gif"
    quantized[0].save(gif, save_all=True, append_images=quantized[1:], duration=durations,
                      loop=0, optimize=True, disposal=1)
    size_mb = gif.stat().st_size / 2 ** 20
    print(f"已输出 {gif}（{n} 帧，{size_mb:.2f} MB）及首帧 {first_png}")
    if size_mb > 8:
        print("[警告] GIF 超过 8 MB")
    if n > 150:
        print("[警告] 帧数超过 150")
    plt.close(fig)


# ---------------------------------------------------------------- 图 C
def _timeline_pointer(ax, now, ymax):
    return ax.axvline(now, color=ACCENT, ls=(0, (4, 3)), lw=1.4, zorder=20)


def cmd_c1(args):
    vp.setup()
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    sync_dir = DATA_ROOT / args.run / "episodes" / args.skeleton / "synchronous"
    seq_dir = DATA_ROOT / args.run / "episodes" / args.skeleton / "sequential"
    sync_ep, seq_ep = av.load_episode(sync_dir), av.load_episode(seq_dir)
    box = vp.crop_box([sync_ep, seq_ep])
    sync_tl, seq_tl = vp.load_timeline(sync_dir), vp.load_timeline(seq_dir)
    tmax = max(sync_tl["last"], seq_tl["last"])
    t0, t1, start = animation_window([sync_ep, seq_ep], fraction=0.80)
    fig = plt.figure(figsize=(18, 11), dpi=args.dpi, facecolor=BACKGROUND)
    gs = fig.add_gridspec(2, 2, height_ratios=(1.45, 1.0), hspace=0.28, wspace=0.08,
                          left=0.06, right=0.985, top=0.95, bottom=0.08)
    map_ax = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])]
    tl_ax = [fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])]
    panels = [MapPanel(map_ax[0], sync_ep, box, "同步版"),
              MapPanel(map_ax[1], seq_ep, box, "递次版")]
    vp._draw_timeline(tl_ax[0], sync_tl, "同步版 · 时间轴")
    vp._draw_timeline(tl_ax[1], seq_tl, "递次版 · 时间轴")
    for ax in tl_ax:
        ax.set_xlim(0, tmax)
        ax.set_xlabel("")
    if tl_ax[0].get_legend():
        tl_ax[0].get_legend().remove()
    if tl_ax[1].get_legend():
        tl_ax[1].get_legend().remove()
    handles = [Patch(facecolor=c, label=label) for c, label in
               ((vp.WAIT, "等待出发"), (vp.APPROACH, "进场"), (vp.PRIMARY, "核心作业"),
                (vp.RETREAT, "撤离"))]
    handles.append(Line2D([0], [0], marker="^", ls="", color=ACCENT, markersize=7,
                          label="开始核心作业"))
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=9, frameon=False,
               labelcolor=TEXT, bbox_to_anchor=(0.5, 0.012))
    fig.text(0.5, 0.045, "仿真时间（秒）", ha="center", fontsize=10, color=TEXT)
    clock = fig.text(0.5, 0.965, "", ha="center", va="top", fontsize=12, color=TEXT)
    fig.text(0.995, 0.006, "抽象合成场景", ha="right", va="bottom", fontsize=8, color=SECONDARY)
    pointers = [_timeline_pointer(ax, start, 0) for ax in tl_ax]

    from PIL import Image
    n = args.frames
    frames = []
    for k in range(n):
        now = start + (t1 - start) * k / max(n - 1, 1)
        for panel in panels:
            panel.update(now)
        for pointer in pointers:
            pointer.set_xdata([now, now])
        clock.set_text(f"仿真时间 {av.fmt_clock(now)}")
        fig.canvas.draw()
        rgba = np.asarray(fig.canvas.buffer_rgba())
        frames.append(Image.fromarray(rgba[:, :, :3].copy()))
    out = Path(args.out)
    first_png = out / "c1_first_frame.png"
    first_png.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(first_png)
    picks = [frames[0], frames[len(frames) // 2], frames[-1]]
    sheet = Image.new("RGB", (picks[0].width, picks[0].height * len(picks)))
    for j, image in enumerate(picks):
        sheet.paste(image, (0, image.height * j))
    palette = sheet.quantize(colors=args.colors, method=Image.Quantize.MEDIANCUT)
    quantized = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    durations = [int(1000 / args.fps)] * n
    durations[-1] = int(args.hold * 1000)
    gif = out / "c1_sync_seq.gif"
    quantized[0].save(gif, save_all=True, append_images=quantized[1:], duration=durations,
                      loop=0, optimize=True, disposal=1)
    size_mb = gif.stat().st_size / 2 ** 20
    print(f"已输出 {gif}（{n} 帧，{size_mb:.2f} MB）及首帧 {first_png}")
    if size_mb > 8:
        print("[警告] GIF 超过 8 MB")
    if n > 150:
        print("[警告] 帧数超过 150")
    plt.close(fig)


def cmd_c2(args):
    vp.setup()
    import matplotlib.pyplot as plt
    sync_dir = DATA_ROOT / args.run / "episodes" / args.skeleton / "synchronous"
    seq_dir = DATA_ROOT / args.run / "episodes" / args.skeleton / "sequential"
    sync_tl, seq_tl = vp.load_timeline(sync_dir), vp.load_timeline(seq_dir)
    tmax = max(sync_tl["last"], seq_tl["last"])
    fig, axes = plt.subplots(2, 1, figsize=(18, 9), dpi=args.dpi, sharex=True, facecolor=BACKGROUND)
    vp._draw_timeline(axes[0], sync_tl, "同步版")
    vp._draw_timeline(axes[1], seq_tl, "递次版")
    for ax in axes:
        ax.set_xlim(0, tmax)
    axes[0].tick_params(labelbottom=False)
    axes[1].set_xlabel("仿真时间（秒）", fontsize=11, color=TEXT)
    fig.text(0.995, 0.006, "抽象合成场景", ha="right", va="bottom", fontsize=8, color=SECONDARY)
    fig.subplots_adjust(left=0.13, right=0.985, top=0.93, bottom=0.08, hspace=0.42)
    save(fig, args.out, args.dpi)
    plt.close(fig)


# ---------------------------------------------------------------- 图 D
def load_series(path):
    agents = defaultdict(list)
    with open(path, encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            if row.get("valid", "1") != "1":
                continue
            agents[row["agent_id"]].append(
                (float(row["t_s"]), float(row["east_m"]), float(row["north_m"])))
    for agent in agents:
        agents[agent].sort()
    return agents


def speed_of(series):
    t = np.array([p[0] for p in series], float)
    x = np.array([p[1] for p in series], float)
    y = np.array([p[2] for p in series], float)
    dt = np.diff(t)
    good = dt > 1e-9
    return t[1:][good], (np.hypot(np.diff(x), np.diff(y))[good] / dt[good])


def mean_curve(curves, n=260):
    tmax = max(t[-1] for t, _ in curves if len(t))
    grid = np.linspace(0, tmax, n)
    values = []
    for t, v in curves:
        if len(t) < 2:
            continue
        values.append(np.interp(grid, t, v))
    return grid, np.mean(values, axis=0)


def sitl_truth_path(task):
    ref = M3_ROOT / "calibration_20261013" / "attempt_02_resume" / "default_baseline" / task / "sitl_r2.json"
    data = read_json(ref)
    paths = [Path(k) for k in data.get("evidence_sha256", {}) if k.endswith("truth.csv")]
    if not paths:
        raise SystemExit(f"SITL truth.csv 未找到：{task}")
    return paths[0]


def cmd_d(args):
    vp.setup()
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    fig = plt.figure(figsize=(20, 8), dpi=args.dpi, facecolor=BACKGROUND)
    top, bottom, gap = 0.90, 0.08, 0.06
    height = (top - bottom - 2 * gap) / 3
    for row, (task, mode_zh, pattern, err) in enumerate(D_TASKS):
        sitl = load_series(sitl_truth_path(task))
        fast = load_series(M3_ROOT / "m3_r3_r2_attempt01" / "runs" / task / "run" / "analysis" / "truth.csv")
        points = []
        for series in (sitl, fast):
            for agent, values in series.items():
                arr = np.array([[p[1], p[2]] for p in values], float)
                points.append(arr)
        pts = np.concatenate(points)
        x0, y0 = pts.min(axis=0)
        x1, y1 = pts.max(axis=0)
        pad = 0.05 * max(x1 - x0, y1 - y0)
        box = (x0 - pad, x1 + pad, y0 - pad, y1 + pad)

        y = bottom + (2 - row) * (height + gap)
        ax = fig.add_axes([0.02, y, 0.16, height])
        ax.set_facecolor(BACKGROUND)
        for agent, values in sitl.items():
            arr = np.array([[p[1], p[2]] for p in values], float)
            ax.plot(arr[:, 0], arr[:, 1], color=SITL_GRAY, lw=1.0, alpha=0.65, zorder=3)
        for agent, values in fast.items():
            arr = np.array([[p[1], p[2]] for p in values], float)
            ax.plot(arr[:, 0], arr[:, 1], color=PRIMARY, lw=1.2, ls=(0, (4, 3)),
                    alpha=0.9, zorder=4)
        ax.set_xlim(box[0], box[1])
        ax.set_ylim(box[2], box[3])
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        fig.text(0.02, y + height + 0.012, f"{mode_zh} · r3 总时长误差 {err * 100:+.2f}%",
                 ha="left", va="bottom", fontsize=12.5, color=TEXT)
        style_axes(ax)

        ax2 = fig.add_axes([0.20, y, 0.78, height])
        ax2.set_facecolor(BACKGROUND)
        sitl_curves = [speed_of(v) for v in sitl.values()]
        fast_curves = [speed_of(v) for v in fast.values()]
        for t, v in sitl_curves:
            ax2.plot(t, v, color=SITL_GRAY, lw=0.7, alpha=0.28)
        for t, v in fast_curves:
            ax2.plot(t, v, color=PRIMARY, lw=0.7, alpha=0.28)
        ts, vs = mean_curve(sitl_curves)
        tf, vf = mean_curve(fast_curves)
        ax2.plot(ts, vs, color=SITL_GRAY, lw=2.0)
        ax2.plot(tf, vf, color=PRIMARY, lw=2.0, ls=(0, (4, 3)))
        ax2.set_xlim(0, max(ts[-1], tf[-1]) * 1.02)
        ax2.set_ylim(0, max(vs.max(), vf.max()) * 1.15)
        ax2.set_xlabel("时间（秒）" if row == 2 else "", fontsize=9, color=TEXT)
        ax2.set_ylabel("速度（m/s）", fontsize=9, color=TEXT)
        ax2.tick_params(labelsize=8, colors=SECONDARY)
        ax2.grid(color="#E2DED4", lw=0.6)
        ax2.set_axisbelow(True)
        for spine in ("top", "right"):
            ax2.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax2.spines[spine].set_color("#C5CED6")
    handles = [Line2D([0], [0], color=SITL_GRAY, lw=2.0, label="真实飞控（SITL）"),
               Line2D([0], [0], color=PRIMARY, lw=2.0, ls=(0, (4, 3)), label="快速仿真（r3）")]
    fig.legend(handles=handles, loc="upper right", ncol=2, fontsize=10, frameon=False,
               labelcolor=TEXT, bbox_to_anchor=(0.985, 0.985))
    fig.text(0.995, 0.008, "抽象合成场景", ha="right", va="bottom", fontsize=8, color=SECONDARY)
    save(fig, args.out, args.dpi)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("a")
    p.add_argument("--run", default=B_RUN)
    p.add_argument("--skeleton", default="family_s15_5024cb2ccea653ae_ext_006_regular")
    p.add_argument("--group", default="task_group_01")
    p.add_argument("--agent", default="uav_01")
    p.add_argument("--dpi", type=int, default=100)
    p.add_argument("--out", required=True)
    p = sub.add_parser("b")
    p.add_argument("--run", default=B_RUN)
    p.add_argument("--family", default=B_FAMILY)
    p.add_argument("--slot", type=int, default=B_SLOT)
    p.add_argument("--dpi", type=int, default=100)
    p.add_argument("--frames", type=int, default=120)
    p.add_argument("--fps", type=int, default=12)
    p.add_argument("--hold", type=float, default=2.0)
    p.add_argument("--colors", type=int, default=64)
    p.add_argument("--out", required=True)
    p = sub.add_parser("c1")
    p.add_argument("--run", default=B_RUN)
    p.add_argument("--skeleton", default=C_SKELETON)
    p.add_argument("--dpi", type=int, default=100)
    p.add_argument("--frames", type=int, default=120)
    p.add_argument("--fps", type=int, default=12)
    p.add_argument("--hold", type=float, default=2.0)
    p.add_argument("--colors", type=int, default=64)
    p.add_argument("--out", required=True)
    p = sub.add_parser("c2")
    p.add_argument("--run", default=B_RUN)
    p.add_argument("--skeleton", default=C_SKELETON)
    p.add_argument("--dpi", type=int, default=100)
    p.add_argument("--out", required=True)
    p = sub.add_parser("d")
    p.add_argument("--dpi", type=int, default=100)
    p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    {"a": cmd_a, "b": cmd_b, "c1": cmd_c1, "c2": cmd_c2, "d": cmd_d}[args.cmd](args)


if __name__ == "__main__":
    main()
