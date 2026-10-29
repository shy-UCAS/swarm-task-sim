"""v0.7 first_edition 轨迹动图（GIF）渲染：地图 + 编组轨迹逐帧回放。

只读取已生成的 episode 目录（truth_10hz.npz、labels.json、task.json、source.json、
public_scene.json），不调用规划器或仿真器，不写入数据目录。合成数据可视化工具，
点质量运动学轨迹，不涉及真实无人机控制。

用法（在项目目录 Multi-UAV SimpleGC 下运行）：
  python -B scripts/viz/animate_v07.py list   --run pilot_f005_020d
  python -B scripts/viz/animate_v07.py single --episode <episode 目录>
  python -B scripts/viz/animate_v07.py pair   --run pilot_f005_020d --draw <family_id>:<slot> --intent monitoring
  python -B scripts/viz/animate_v07.py five   --run pilot_f005_020d --draw <family_id>:<slot> --mode synchronous
      [--showcase <展示 episode 目录>]   第 6 格改为分阶段突防展示，通用图例移到图底部

公共参数：--out 输出目录（默认 ..\\..\\SwarmData\\ppt_media）、--seconds 动画时长（默认 10）、
--fps（默认 12）、--hold 末帧停留秒数（默认 2）、--dpi、--colors GIF 调色板颜色数（默认 128）、
--full-map 显示整张地图、--no-plan 不画计划航线、--show-radar 显示雷达、--mp4 另存 MP4（需 imageio-ffmpeg）。
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

DATA_ROOT = PROJECT.parents[1] / "SwarmData" / "v07_first_edition"
DEFAULT_OUT = PROJECT.parents[1] / "SwarmData" / "ppt_media"

INTENT_ZH = {"transit": "过境", "reconnaissance": "侦察", "monitoring": "监视",
             "feint": "佯动", "penetration": "突防"}
ROLE_ZH = {"transit": "过境", "reconnaissance": "侦察", "monitoring": "监视",
           "feint": "佯动", "intrusion": "突入"}
METHOD_ZH = {"area_search": "区域搜索", "close_observation": "抵近观察"}
MODE_ZH = {"synchronous": "同步版", "sequential": "递次版"}
INTENT_ORDER = ("transit", "reconnaissance", "monitoring", "feint", "penetration")
GROUP_COLORS = ("#d1495b", "#2e86ab", "#e09f3e")
LAYER_STYLE = (("warning", "#eef3f7", "预警区"), ("alert", "#d6e4ef", "警戒区"), ("protected", "#a9c6dc", "防护区"))


# ---------------------------------------------------------------- 读取
def read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def load_episode(ep_dir):
    ep_dir = Path(ep_dir)
    with np.load(ep_dir / "truth_10hz.npz", allow_pickle=False) as truth:
        t = truth["time_us"].astype(np.int64) / 1e6
        p = truth["p"][:, :, :2].astype(float)
        ids = [str(a) for a in truth["agent_ids"].tolist()]
    labels = read_json(ep_dir / "labels.json")
    task = read_json(ep_dir / "task.json")
    source = read_json(ep_dir / "source.json")
    scene = read_json(ep_dir / "public_scene.json")
    settle = float(task.get("initial_settle_s", 0.0))
    delays = source.get("departure_delays_s") or {}
    speed = np.zeros(p.shape[:2])
    speed[1:] = np.linalg.norm(np.diff(p, axis=0), axis=2) / np.maximum(np.diff(t), 1e-9)[:, None]
    release = {}
    for i, a in enumerate(ids):
        if a in delays:
            release[a] = settle + float(delays[a])
        else:
            moving = np.flatnonzero(speed[:, i] > 1.0)
            release[a] = float(t[moving[0]]) if len(moving) else float(t[0])
    last_move = []
    for i in range(len(ids)):
        moving = np.flatnonzero(speed[:, i] > 0.5)
        last_move.append(float(t[moving[-1]]) if len(moving) else float(t[-1]))
    groups = []
    for k, (gid, group) in enumerate(sorted(labels.get("task_groups", {}).items())):
        assigned = group.get("assigned", {})
        role = assigned.get("role", "")
        method = assigned.get("execution_method", role)
        name = ROLE_ZH.get(role, role)
        if role == "reconnaissance" and method in METHOD_ZH:
            name = METHOD_ZH[method]
        groups.append({"gid": gid, "members": list(assigned.get("members", [])), "role": role,
                       "name": name, "color": GROUP_COLORS[k % len(GROUP_COLORS)],
                       "target": assigned.get("target")})
    member_color = {m: g["color"] for g in groups for m in g["members"]}
    core = {}
    for a in ids:
        event = labels.get("agents", {}).get(a, {}).get("observed", {}).get("core_event", {}) or {}
        core[a] = event.get("frame_index")
    intent = labels.get("cluster", {}).get("assigned", {}).get("intent") or task.get("base_intent", "")
    mode = source.get("planned_coordination", "")
    plan = {}
    for a in ids:
        ref = (task.get("references") or {}).get(a) or {}
        if ref.get("points_enu_m"):
            plan[a] = np.asarray(ref["points_enu_m"], float)[:, :2]
    return {"dir": ep_dir, "t": t, "p": p, "ids": ids, "labels": labels, "scene": scene,
            "release": release, "last_move": last_move, "groups": groups, "color": member_color,
            "core": core, "intent": intent, "mode": mode, "plan": plan}


def time_window(eps):
    start = min(min(e["release"].values()) for e in eps)
    end = max(max(e["last_move"]) for e in eps)
    span = max(end - start, 60.0)
    pad = max(5.0, 0.03 * span)
    return max(0.0, start - pad), end + pad


def view_box(eps, full_map, t0, t1):
    scene = eps[0]["scene"]
    from scene_v07.geometry import to_shape
    wx0, wy0, wx1, wy1 = to_shape(scene["world"]["geometry"]).bounds
    if full_map:
        return wx0 - 40, wx1 + 40, wy0 - 40, wy1 + 40
    pts = []
    for e in eps:
        keep = (e["t"] >= t0) & (e["t"] <= t1)
        pts.append(e["p"][keep].reshape(-1, 2))
    pts = np.concatenate(pts)
    x0, y0 = pts.min(axis=0)
    x1, y1 = pts.max(axis=0)
    size = max(x1 - x0, y1 - y0) * 1.15 + 200
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    x0, x1 = max(wx0 - 40, cx - size / 2), min(wx1 + 40, cx + size / 2)
    y0, y1 = max(wy0 - 40, cy - size / 2), min(wy1 + 40, cy + size / 2)
    return x0, x1, y0, y1


# ---------------------------------------------------------------- 绘制
def setup_fonts():
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import rcParams
    rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC",
                                   "WenQuanYi Micro Hei", "DejaVu Sans"]
    rcParams["axes.unicode_minus"] = False


def draw_map(ax, scene, box, show_radar):
    from matplotlib.patches import Polygon as PlotPolygon
    from scene_v07.geometry import to_shape
    for layer, color, _ in LAYER_STYLE:
        for ent in scene["entities"]:
            if ent.get("layer") == layer:
                shape = to_shape(ent["geometry"], 64)
                ax.add_patch(PlotPolygon(list(shape.exterior.coords), facecolor=color,
                                         edgecolor="#8aa5ba", lw=0.6, zorder=1))
    for ent in scene["entities"]:
        if ent["type"] == "facility":
            shape = to_shape(ent["geometry"], 64)
            ax.add_patch(PlotPolygon(list(shape.exterior.coords), facecolor="#3f6a85",
                                     edgecolor="#2b4658", lw=0.8, zorder=2))
            label = "设施" + str(int(ent["id"].split("_")[-1]))
            ax.text(shape.centroid.x, shape.centroid.y, label, fontsize=9, ha="center", va="center",
                    color="white", zorder=3)
        elif ent["type"] == "hard_constraint_obstacle":
            shape = to_shape(ent["geometry"], 64)
            ax.add_patch(PlotPolygon(list(shape.exterior.coords), facecolor="#ddd0c9", edgecolor="#8a7a72",
                                     lw=0.6, hatch="///", zorder=2))
        elif ent["type"] == "radar" and show_radar:
            ax.scatter(*ent["geometry"]["position_m"][:2], marker="D", s=20, color="#aa4f6b", zorder=3)
    for entry in scene.get("entry_zones", []):
        shape = to_shape(entry["geometry"])
        ax.add_patch(PlotPolygon(list(shape.exterior.coords), facecolor="#b9e6da", edgecolor="#5a9a88",
                                 lw=0.6, zorder=1))
    x0, x1, y0, y1 = box
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#c5ced6")
    # 比例尺
    span = x1 - x0
    bar = 10 ** np.floor(np.log10(span / 4))
    bar = bar * (5 if span / bar > 20 else 2 if span / bar > 8 else 1)
    bx, by = x0 + 0.05 * span, y0 + 0.04 * (y1 - y0)
    ax.plot([bx, bx + bar], [by, by], color="#333333", lw=2, zorder=6)
    ax.text(bx + bar / 2, by + 0.015 * (y1 - y0), f"{bar:.0f} m", ha="center", fontsize=8, zorder=6)


class Panel:
    """一个子图：静态地图 + 每架飞机的尾迹、圆点、核心事件标记。"""

    def __init__(self, ax, ep, box, show_plan, show_radar, title):
        self.ax, self.ep = ax, ep
        draw_map(ax, ep["scene"], box, show_radar)
        if show_plan:
            for a, pts in ep["plan"].items():
                ax.plot(pts[:, 0], pts[:, 1], ls=(0, (3, 3)), lw=0.6, color="#7a7a7a", alpha=0.45, zorder=3)
        self.trails, self.dots, self.cores = {}, {}, {}
        for a in ep["ids"]:
            color = ep["color"].get(a, "#555555")
            (self.trails[a],) = ax.plot([], [], lw=1.8, color=color, alpha=0.85, zorder=4, solid_capstyle="round")
            self.dots[a] = ax.scatter([ep["p"][0, ep["ids"].index(a), 0]], [ep["p"][0, ep["ids"].index(a), 1]],
                                      s=36, zorder=5, facecolors="none", edgecolors="#8a8a8a", linewidths=1.2)
            self.cores[a] = ax.scatter([], [], marker="^", s=46, color="#c0392b", zorder=6)
        ax.set_title(title, fontsize=12, pad=6)
        self.clock = ax.text(0.98, 0.97, "", transform=ax.transAxes, ha="right", va="top", fontsize=10,
                             bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": "#c5ced6", "alpha": 0.9}, zorder=7)

    def update(self, now, trail_s, clock_text):
        ep, t = self.ep, self.ep["t"]
        k = int(np.clip(np.searchsorted(t, now, side="right") - 1, 0, len(t) - 1))
        k0 = int(np.searchsorted(t, now - trail_s, side="left"))
        for i, a in enumerate(ep["ids"]):
            color = ep["color"].get(a, "#555555")
            released = now >= ep["release"][a]
            seg = ep["p"][k0:k + 1, i]
            if released and len(seg) > 1:
                step = max(1, len(seg) // 300)
                seg = seg[::step]
                self.trails[a].set_data(seg[:, 0], seg[:, 1])
            else:
                self.trails[a].set_data([], [])
            dot = self.dots[a]
            dot.set_offsets([ep["p"][k, i]])
            if released:
                dot.set_facecolors([color])
                dot.set_edgecolors(["white"])
            else:
                dot.set_facecolors(["none"])
                dot.set_edgecolors(["#8a8a8a"])
            frame = ep["core"].get(a)
            if frame is not None and frame <= k:
                self.cores[a].set_offsets([ep["p"][frame, i]])
            else:
                self.cores[a].set_offsets(np.empty((0, 2)))
        self.clock.set_text(clock_text)


def legend_handles(ep):
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    handles = []
    for g in ep["groups"]:
        handles.append(Line2D([], [], marker="o", color=g["color"], lw=1.8, markersize=6,
                              label=f"{g['name']}编组（{len(g['members'])} 架）"))
    handles += [Line2D([], [], marker="o", ls="", markerfacecolor="none", markeredgecolor="#8a8a8a",
                       markersize=6, label="等待出发"),
                Line2D([], [], marker="^", ls="", color="#c0392b", markersize=7, label="开始执行任务"),
                Line2D([], [], ls=(0, (3, 3)), color="#7a7a7a", label="计划航线")]
    handles += [Patch(facecolor=c, edgecolor="#8aa5ba", label=n) for _, c, n in LAYER_STYLE]
    return handles


def fmt_clock(seconds):
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# ---------------------------------------------------------------- 输出
def render(fig, panels_and_clocks, n_frames, out_path, args):
    """panels_and_clocks: [(panel, fn(k)->(now, trail_s, clock_text))]"""
    from PIL import Image
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames = []
    for k in range(n_frames):
        for panel, clock_fn in panels_and_clocks:
            panel.update(*clock_fn(k))
        fig.canvas.draw()
        rgba = np.asarray(fig.canvas.buffer_rgba())
        frames.append(Image.fromarray(rgba[:, :, :3].copy()))
    frames[-1].save(out_path.with_suffix(".png"))
    picks = [frames[0], frames[len(frames) // 2], frames[-1]]
    sheet = Image.new("RGB", (picks[0].width, picks[0].height * len(picks)))
    for j, img in enumerate(picks):
        sheet.paste(img, (0, img.height * j))
    palette = sheet.quantize(colors=args.colors, method=Image.Quantize.MEDIANCUT)
    quantized = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    durations = [int(1000 / args.fps)] * n_frames
    durations[-1] = int(args.hold * 1000)
    quantized[0].save(out_path, save_all=True, append_images=quantized[1:], duration=durations,
                      loop=0, optimize=True, disposal=1)
    if args.mp4:
        try:
            import imageio.v3 as iio
            stack = np.stack([np.asarray(f) for f in frames] + [np.asarray(frames[-1])] * int(args.hold * args.fps))
            h, w = stack.shape[1] // 2 * 2, stack.shape[2] // 2 * 2
            iio.imwrite(out_path.with_suffix(".mp4"), stack[:, :h, :w], fps=args.fps, codec="libx264")
        except Exception as exc:  # 可选输出，失败不影响 GIF
            print(f"[提示] 未生成 MP4：{exc}")
    size_mb = out_path.stat().st_size / 2 ** 20
    print(f"已输出 {out_path}（{size_mb:.1f} MB，{n_frames} 帧）及同名 PNG 静态末帧")
    if size_mb > 5:
        print("[提示] GIF 超过 5 MB，可减小 --dpi、--colors 或 --seconds")


def clock_for(ep, t0, t1, n_frames):
    span = t1 - t0
    trail = float(np.clip(0.08 * span, 30, 300))

    def fn(k):
        now = t0 + span * k / max(n_frames - 1, 1)
        return now, trail, f"仿真时间 {fmt_clock(now - t0)}"
    return fn


def speed_note(span, seconds):
    return f"动画约为实际速度的 {span / seconds:.0f} 倍"


def cmd_single(args):
    setup_fonts()
    import matplotlib.pyplot as plt
    ep = load_episode(args.episode)
    t0, t1 = time_window([ep])
    box = view_box([ep], args.full_map, t0, t1)
    fig, ax = plt.subplots(figsize=(8, 8.4), dpi=args.dpi)
    title = f"{INTENT_ZH.get(ep['intent'], ep['intent'])} · {MODE_ZH.get(ep['mode'], ep['mode'])}"
    panel = Panel(ax, ep, box, not args.no_plan, args.show_radar, title)
    ax.legend(handles=legend_handles(ep), loc="lower right", fontsize=8, framealpha=0.9)
    n = int(args.seconds * args.fps)
    fig.text(0.5, 0.012, speed_note(t1 - t0, args.seconds) + " · 合成数据，抽象场景", ha="center", fontsize=9, color="#555555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    name = args.name or f"single_{ep['intent']}_{ep['mode']}"
    render(fig, [(panel, clock_for(ep, t0, t1, n))], n, Path(args.out) / f"{name}.gif", args)


def manifest_entries(run):
    manifest = read_json(DATA_ROOT / run / "manifest.json")
    return manifest["retained_episodes"]


def find_entry(run, draw, intent, mode):
    family, slot = draw.rsplit(":", 1)
    for e in manifest_entries(run):
        if e["family_id"] == family and str(e["slot"]) == slot and e["intent"] == intent and e["mode"] == mode:
            return DATA_ROOT / run / e["path"]
    raise SystemExit(f"未找到：run={run} draw={draw} intent={intent} mode={mode}（只能选 RETAINED 抽签，先用 list 查看）")


def cmd_pair(args):
    """同一骨架的同步版 / 递次版并排，共用一个仿真时钟。"""
    setup_fonts()
    import matplotlib.pyplot as plt
    eps = [load_episode(find_entry(args.run, args.draw, args.intent, m)) for m in ("synchronous", "sequential")]
    t0, t1 = time_window(eps)
    box = view_box(eps, args.full_map, t0, t1)
    fig, axes = plt.subplots(1, 2, figsize=(14, 7.6), dpi=args.dpi)
    n = int(args.seconds * args.fps)
    pairs = []
    for ax, ep in zip(axes, eps):
        title = f"{INTENT_ZH.get(ep['intent'], ep['intent'])} · {MODE_ZH.get(ep['mode'], ep['mode'])}"
        panel = Panel(ax, ep, box, not args.no_plan, args.show_radar, title)
        pairs.append((panel, clock_for(ep, t0, t1, n)))
    axes[1].legend(handles=legend_handles(eps[0]), loc="lower right", fontsize=8, framealpha=0.9)
    fig.text(0.5, 0.012, "左右共用同一仿真时钟 · " + speed_note(t1 - t0, args.seconds) + " · 合成数据，抽象场景",
             ha="center", fontsize=9, color="#555555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    name = args.name or f"pair_{args.intent}"
    render(fig, pairs, n, Path(args.out) / f"{name}.gif", args)


def cmd_five(args):
    """同一抽签（同一地图、同一批飞机）的五种意图，2×3 排布。

    未给 --showcase 时第 6 格放图例；给了 --showcase 时第 6 格改为分阶段突防展示，
    通用图例移到图底部，六格共用同一地图范围。
    """
    setup_fonts()
    import matplotlib.pyplot as plt
    eps = [load_episode(find_entry(args.run, args.draw, i, args.mode)) for i in INTENT_ORDER]
    showcase = load_episode(args.showcase) if args.showcase else None
    all_eps = eps + ([showcase] if showcase else [])
    windows = [time_window([e]) for e in all_eps]
    t0_all = min(w[0] for w in windows)
    t1_all = max(w[1] for w in windows)
    box = view_box(all_eps, args.full_map, t0_all, t1_all)
    height = 10.4 if showcase is None else 11.2
    fig, axes = plt.subplots(2, 3, figsize=(15, height), dpi=args.dpi)
    n = int(args.seconds * args.fps)
    pairs = []
    titles = [INTENT_ZH.get(ep["intent"], ep["intent"]) for ep in eps]
    if showcase is not None:
        titles.append(args.showcase_title)
    for ax, ep, (t0, t1), title in zip(axes.flat, all_eps, windows, titles):
        panel = Panel(ax, ep, box, not args.no_plan, args.show_radar, title)
        ax.legend(handles=legend_handles(ep)[:len(ep["groups"])], loc="upper left", fontsize=8, framealpha=0.85)
        if args.shared_clock:
            pairs.append((panel, clock_for(ep, t0_all, t1_all, n)))
        else:
            pairs.append((panel, clock_for(ep, t0, t1, n)))
    handles = legend_handles(eps[4])[len(eps[4]["groups"]):]
    if showcase is not None:
        # 第 6 格已被展示样例占用：通用图例移到图底部
        fig.legend(handles=handles, loc="lower center", ncol=len(handles), fontsize=10, frameon=False,
                   bbox_to_anchor=(0.5, 0.012))
        note = ("六个子图共用同一仿真时钟" if args.shared_clock else "各子图按自身时长播放")
        note += " · 右下角为分阶段突防展示（监视→佯动→突入，仅用于汇报，不进数据集）"
        fig.text(0.5, 0.072, note, ha="center", fontsize=9.5, color="#555555")
        fig.text(0.5, 0.042, "同一地图、同一批飞机；每个子图的编组颜色见各自图例 · 合成数据，抽象场景",
                 ha="center", fontsize=9, color="#555555")
        fig.tight_layout(rect=(0, 0.10, 1, 1))
    else:
        legend_ax = axes.flat[5]
        legend_ax.axis("off")
        legend_ax.legend(handles=handles, loc="center", fontsize=11, frameon=False,
                         title=MODE_ZH.get(args.mode, ""), title_fontsize=13)
        note = ("五个子图共用同一仿真时钟" if args.shared_clock else "各子图按自身时长播放（监视实际最长）")
        legend_ax.text(0.5, 0.08, note + "\n同一地图、同一批飞机、同一编组划分\n每个子图的编组颜色见各自轨迹",
                       transform=legend_ax.transAxes, ha="center", fontsize=10, color="#555555")
        fig.text(0.5, 0.01, "合成数据，抽象场景", ha="center", fontsize=9, color="#555555")
        fig.tight_layout(rect=(0, 0.025, 1, 1))
    name = args.name or (f"five_six_{args.mode}" if showcase is not None else f"five_{args.mode}")
    render(fig, pairs, n, Path(args.out) / f"{name}.gif", args)


def cmd_list(args):
    """列出 RETAINED 抽签，帮助挑选展示样例。"""
    by_draw = {}
    for e in manifest_entries(args.run):
        by_draw.setdefault((e["family_id"], e["slot"]), {})[(e["intent"], e["mode"])] = e
    rows = []
    for (family, slot), entries in sorted(by_draw.items()):
        pen = entries.get(("penetration", "synchronous"))
        mon = entries.get(("monitoring", "synchronous"))
        if pen is None or mon is None:
            continue
        lab = read_json(DATA_ROOT / args.run / pen["path"] / "labels.json")
        scene = read_json(DATA_ROOT / args.run / pen["path"] / "public_scene.json")
        groups = lab.get("task_groups", {})
        roles = "+".join(ROLE_ZH.get(g["assigned"]["role"], "?") for g in groups.values())
        n_agents = sum(len(g["assigned"]["members"]) for g in groups.values())
        approach = next(iter(groups.values()))["assigned"].get("approach_mode", "")
        n_fac = sum(1 for x in scene["entities"] if x["type"] == "facility")
        mon_t = read_json(DATA_ROOT / args.run / mon["path"] / "labels.json")["evidence"]["last_observed_s"]
        score = len(set(roles.split("+"))) * 2 + (approach == "multi_direction") + (n_fac >= 2)
        rows.append((score, f"{family}:{slot}", n_fac, n_agents, len(groups), roles, approach, mon_t))
    rows.sort(key=lambda r: (-r[0], r[1]))
    print("推荐度 | 抽签（--draw 参数） | 设施数 | 机数 | 突防编组数 | 突防角色 | 进场方式 | 监视原始时长(s)")
    for r in rows[:args.top]:
        print(f"{r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]:.0f}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--out", default=str(DEFAULT_OUT))
        p.add_argument("--name")
        p.add_argument("--seconds", type=float, default=10.0)
        p.add_argument("--fps", type=int, default=12)
        p.add_argument("--hold", type=float, default=2.0)
        p.add_argument("--dpi", type=int, default=100)
        p.add_argument("--colors", type=int, default=128)
        p.add_argument("--full-map", action="store_true")
        p.add_argument("--no-plan", action="store_true")
        p.add_argument("--show-radar", action="store_true")
        p.add_argument("--mp4", action="store_true")

    p = sub.add_parser("list"); p.add_argument("--run", required=True); p.add_argument("--top", type=int, default=15)
    p = sub.add_parser("single"); p.add_argument("--episode", required=True); common(p)
    p = sub.add_parser("pair"); p.add_argument("--run", required=True); p.add_argument("--draw", required=True)
    p.add_argument("--intent", default="monitoring", choices=INTENT_ORDER); common(p)
    p = sub.add_parser("five"); p.add_argument("--run", required=True); p.add_argument("--draw", required=True)
    p.add_argument("--mode", default="synchronous", choices=("synchronous", "sequential"))
    p.add_argument("--shared-clock", action="store_true")
    p.add_argument("--showcase", help="第 6 格放该展示 episode（分阶段突防），通用图例移到图底部")
    p.add_argument("--showcase-title", default="分阶段突防展示（同一设施）")
    common(p)
    args = parser.parse_args(argv)
    {"list": cmd_list, "single": cmd_single, "pair": cmd_pair, "five": cmd_five}[args.cmd](args)


if __name__ == "__main__":
    main()
