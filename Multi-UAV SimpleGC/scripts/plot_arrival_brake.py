"""Render one immutable arrival/BRAKE diagnostic window as an appendix figure."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/"tmp_v04/v06_20261002/arrival_brake_diagnostic_historical_final.json"
OUTPUT = ROOT/"tmp_v04/v06_20261002/arrival_brake_representative_v02r1_uav01_approach_v2.png"
META = OUTPUT.with_suffix(".json")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUTPUT.exists() or META.exists():
        raise FileExistsError("figure output already exists; do not overwrite evidence")
    before = sha(SOURCE)
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    run = next(r for r in data["runs"] if r["run_id"] == "20261002T083751Z_3874072a")
    records = {w["channel"]: w for w in run["windows"] if w["agent_id"] == "uav_01" and w["phase"] == "p00_approach"}
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams.update({"axes.unicode_minus":False, "font.size":11, "axes.spines.top":False,
                         "axes.spines.right":False, "axes.labelcolor":"#253146", "text.color":"#253146"})
    fcu = records["FCU"]
    transition = fcu["transition"]
    lo, hi = fcu["terminal_event_s"]-1.2, transition["next_AUTO_request_marker_s"]+1.0
    figure, axes = plt.subplots(3, 1, figsize=(13.6, 10.6), sharex=True,
                                gridspec_kw={"height_ratios":[2.1,2.1,1.5]})
    figure.subplots_adjust(top=.84, bottom=.205, left=.13, right=.975, hspace=.15)
    colors = {"FCU":"#1767A6", "SIM":"#DB6726"}
    events = [("A", fcu["terminal_event_s"], "末航点到点事件"),
              ("B", fcu["task_target_verified_s"], "1 m几何确认完成"),
              ("C", transition["first_mode_heartbeat_s"], "BRAKE心跳确认"),
              ("D", transition["next_AUTO_request_marker_s"], "下一阶段AUTO请求标记")]
    for ax in axes:
        ax.set_facecolor("#FAFBFC")
        ax.grid(axis="y", color="#DCE1E7", linewidth=.65)
        ax.set_xlim(lo, hi)
        ax.axvspan(transition["operation_started_s"], transition["first_mode_heartbeat_s"], color="#B77517", alpha=.18)
        ax.axvspan(transition["first_mode_heartbeat_s"], transition["next_AUTO_request_marker_s"], color="#E7C460", alpha=.23)
        for _, stamp, _ in events:
            ax.axvline(stamp, color="#566171", linestyle=":" if stamp==fcu["task_target_verified_s"] else "--", linewidth=.9, alpha=.8)
    for channel, row in records.items():
        curve = [r for r in row["speed_distance_curve"] if lo <= r["t_s"] <= hi]
        xs = [r["t_s"] for r in curve]
        axes[0].plot(xs, [r["horizontal_speed_m_s"] for r in curve], color=colors[channel], marker="o", markersize=3.2, linewidth=1.8, label=channel)
        axes[1].plot(xs, [r["distance_3d_m"] for r in curve], color=colors[channel], linewidth=1.8, label=channel+" 三维距离")
        axes[1].plot(xs, [r["horizontal_distance_m"] for r in curve], color=colors[channel], linewidth=1, linestyle=":", label=channel+" 水平距离")
        entry = row["horizontal_2m_entry"]
        if entry["crossing_bracket_s"]:
            a,b = entry["crossing_bracket_s"]
            y = 3 if channel=="FCU" else 2
            axes[2].plot([a,b], [y,y], color=colors[channel], linewidth=7, solid_capstyle="butt")
            axes[2].plot(b, y, marker="v", color=colors[channel], markersize=7)
        stop = row["first_sustained_horizontal_low_speed"]
        y = 1 if channel=="FCU" else 0
        axes[2].plot([stop["start_s"], stop["end_s"]], [y,y], color=colors[channel], linewidth=7, alpha=.8, solid_capstyle="butt")
        axes[2].plot(stop["minimum_duration_confirmed_s"], y, marker="|", markersize=17, markeredgewidth=2, color="#18232E")
        axes[0].plot(stop["start_s"], next(r["horizontal_speed_m_s"] for r in curve if abs(r["t_s"]-stop["start_s"])<1e-8), marker="s", color=colors[channel], markersize=7)
    axes[0].axhline(.3, color="#7B2F46", linestyle=":", linewidth=1.3, label="低速阈值 0.3 m/s")
    axes[0].set_ylabel("水平速度（m/s）")
    axes[0].set_ylim(bottom=0)
    axes[0].legend(loc="upper right", ncol=3, frameon=True, fontsize=10)
    axes[1].axhline(2, color="#746842", linestyle=":", linewidth=1.2)
    axes[1].axhline(1, color="#7B2F46", linestyle=":", linewidth=1.2)
    axes[1].text(hi-.03, 2.05, "2 m：WPNAV_RADIUS（水平）", ha="right", fontsize=9.5)
    axes[1].text(hi-.03, 1.05, "1 m：几何确认容差（三维）", ha="right", fontsize=9.5)
    axes[1].set_ylabel("距当前阶段终点（m）")
    axes[1].set_ylim(bottom=0)
    axes[1].legend(loc="upper right", ncol=2, frameon=True, fontsize=9)
    axes[2].set_yticks([3,2,1,0], ["FCU进入2 m", "SIM进入2 m", "FCU连续低速", "SIM连续低速"])
    axes[2].set_ylim(-.6,3.8)
    axes[2].set_xlabel("运行启动后的主机映射时间（s）；曲线采样间隔 0.1 s")
    for label, stamp, _ in events:
        if label in ("A","D"):
            axes[0].text(stamp, 1.03, label, transform=axes[0].get_xaxis_transform(), ha="center", fontweight="bold", fontsize=12)
    axes[0].text((events[1][1]+events[2][1])/2, 1.03, "B / C", transform=axes[0].get_xaxis_transform(), ha="center", fontweight="bold", fontsize=12)
    figure.suptitle("末点事件之后，减速延续到下一阶段切换", x=.13, y=.978, ha="left", fontsize=19, fontweight="bold")
    figure.text(.13, .916, "代表窗口：V02 第一次 · uav_01 · approach  →  observe", fontsize=13)
    figure.text(.13, .883, "    ".join(f"{label}  {name} {stamp:.3f} s" for label,stamp,name in events), fontsize=9.7)
    notes = [
        f"浅黄：BRAKE心跳已确认至下一AUTO请求；深窄带：upload_started至BRAKE心跳（{transition['operation_started_s']:.3f}–{transition['first_mode_heartbeat_s']:.3f} s）。",
        "下图进入2 m的横条表示首次外/内样本包围区间；连续低速横条表示≤0.3 m/s的样本支持跨度，黑竖线表示已积累0.2 s证据。",
        "FCU低速起点62.200 s在下一AUTO标记之前，但0.2 s证据到62.400 s才齐；SIM低速起点62.300 s已在下一AUTO标记之后。",
        "SIM速度为源时间上的位置差分；FCU为报告速度。被动时钟对齐未消除通信/滤波时延；近标记的细小差异不能视为精确物理顺序。",
        "配置terminal_hold_s=0.5 s，本窗口机载末NAV CMD Prm1=0；外层另有1 m内0.5 s几何确认，无速度条件。图不改变arrival_s或验收。",
    ]
    for i,line in enumerate(notes):
        figure.text(.13, .145-i*.025, line, fontsize=9.0, color="#445061")
    figure.savefig(OUTPUT, dpi=160, facecolor="white")
    plt.close(figure)
    assert sha(SOURCE)==before, "source changed during figure generation"
    info=dict(version="arrival_brake_figure_v1", source=str(SOURCE.relative_to(ROOT)), source_sha256=before,
              run_id=run["run_id"], agent_id="uav_01", phase="p00_approach", diagnostic_only=True,
              source_unchanged=True, matplotlib_version=matplotlib.__version__, figure_sha256=sha(OUTPUT),
              script_sha256=sha(Path(__file__)), source_times_rounded_in_plot=True)
    with META.open("x", encoding="utf-8") as stream:
        json.dump(info, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"figure":str(OUTPUT),"metadata":str(META),"source_unchanged":True},ensure_ascii=False))


if __name__=="__main__":
    main()
