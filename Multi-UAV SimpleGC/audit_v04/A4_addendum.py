"""A4 补充: (c) 宽松口径静止占比 + (f) 速度曲线图"""
import csv
import json
import math
import statistics
from pathlib import Path

DT = 0.1
DATASETS = {
    "v03_pilot_final": Path("verification/v03_pilot_final_20260930/dataset"),
    "v03_integration": Path("verification/v03_integration_20260930/dataset_final"),
}


def read_obs(path):
    per = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["valid"] != "1":
                continue
            per.setdefault(row["agent_id"], []).append(
                (float(row["t_s"]), math.hypot(float(row["ve_m_s"]), float(row["vn_m_s"]))))
    for a in per:
        per[a].sort()
    return per


def runs_below(samples, threshold, min_s):
    segs, run = [], []
    for t, s in samples:
        if s < threshold:
            if run and t - run[-1][0] > 1.5 * DT:
                segs.append(run); run = []
            run.append((t, s))
        else:
            if run:
                segs.append(run); run = []
    if run:
        segs.append(run)
    return [(r[0][0], r[-1][0]) for r in segs if r[-1][0] - r[0][0] >= min_s]


eps = []
for name, base in DATASETS.items():
    mf = json.loads((base / "dataset_manifest.json").read_text(encoding="utf-8"))
    for e in mf["episodes"]:
        d = base / "episodes" / e["run_id"]
        if (d / "observations.csv").exists() and (d / "phase_windows.json").exists():
            eps.append(dict(dataset=name, run_id=e["run_id"], scenario=e.get("scenario_id"), dir=d))

print("=" * 92)
print("(c) 静止时间占任务窗口比例 —— 两种口径")
print("=" * 92)
print("%-34s %8s %8s %8s %8s %8s" % ("口径", "中位数", "均值", "最小", "最大", "n"))
res = {}
for th, ms, lbl in ((0.3, 1.0, "0.3 m/s, >=1.0s (任务书口径)"),
                    (0.5, 1.0, "0.5 m/s, >=1.0s (任务书对照)"),
                    (0.3, 0.2, "0.3 m/s, >=0.2s (匹配真实停住)"),
                    (0.5, 0.2, "0.5 m/s, >=0.2s (匹配真实停住)")):
    vals = []
    for ep in eps:
        obs = read_obs(ep["dir"] / "observations.csv")
        pw = json.loads((ep["dir"] / "phase_windows.json").read_text(encoding="utf-8"))
        W = [w for w in pw["windows"] if w["start_s"] is not None and w["end_s"] is not None]
        if not W:
            continue
        m0, m1 = min(w["start_s"] for w in W), max(w["end_s"] for w in W)
        tot = 0.0
        for a in obs:
            for (x, y) in runs_below(obs[a], th, ms):
                lo, hi = max(x, m0), min(y, m1)
                if hi > lo:
                    tot += hi - lo
        den = (m1 - m0) * len(obs)
        vals.append(tot / den if den > 0 else 0.0)
    res[lbl] = vals
    print("%-34s %8.4f %8.4f %8.4f %8.4f %8d" %
          (lbl, statistics.median(vals), statistics.mean(vals), min(vals), max(vals), len(vals)))

# 每机分别的静止占比（宽松口径）
print()
print("每机静止占比 (0.3 m/s, >=0.2s):")
for ep in eps:
    obs = read_obs(ep["dir"] / "observations.csv")
    pw = json.loads((ep["dir"] / "phase_windows.json").read_text(encoding="utf-8"))
    W = [w for w in pw["windows"] if w["start_s"] is not None and w["end_s"] is not None]
    if not W:
        continue
    m0, m1 = min(w["start_s"] for w in W), max(w["end_s"] for w in W)
    dur = m1 - m0
    per = {a: sum(min(y, m1) - max(x, m0) for (x, y) in runs_below(obs[a], 0.3, 0.2)
                  if min(y, m1) > max(x, m0)) / dur for a in obs}
    print("  %s: %s" % (ep["run_id"], {a: round(v, 4) for a, v in per.items()}))

# ---------- (f) 绘图 ----------
PICK = None
for ep in eps:
    if ep["run_id"] == "20260930T155457Z_200822e7":
        PICK = ep
        break
if PICK is None:
    for ep in eps:
        obs = read_obs(ep["dir"] / "observations.csv")
        if len(obs) == 3:
            PICK = ep
            break

print()
print("=" * 92)
print("(f) 绘图 episode: %s (%s)" % (PICK["run_id"], PICK["scenario"]))
print("=" * 92)

obs = read_obs(PICK["dir"] / "observations.csv")
pw = json.loads((PICK["dir"] / "phase_windows.json").read_text(encoding="utf-8"))
W = [w for w in pw["windows"] if w["start_s"] is not None and w["end_s"] is not None]

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(17, 7))
    colors = {"uav_01": "#1f77b4", "uav_02": "#d62728", "uav_03": "#2ca02c"}
    for a in sorted(obs):
        ts = [t for t, _ in obs[a]]
        vs = [v for _, v in obs[a]]
        ax.plot(ts, vs, lw=1.1, label=a, color=colors.get(a))
    m0 = min(w["start_s"] for w in W)
    for i, w in enumerate(sorted(W, key=lambda x: x["start_s"])):
        ax.axvline(w["end_s"], color="gray", ls="--", lw=0.5, alpha=0.55)
    ax.axvline(m0, color="black", ls="-", lw=1.0, alpha=0.75)
    ax.axhline(0.3, color="orange", ls=":", lw=1.2)
    ax.text(0.995, 0.3, " 0.3 m/s", transform=ax.get_yaxis_transform(),
            va="bottom", ha="right", fontsize=8, color="orange")
    ax.set_xlabel("t_s (host receive time, s)")
    ax.set_ylabel(r"$|v_{xy}|$ (m/s)")
    ax.set_title("%s  |v_xy| vs time  (dashed = phase window end events, n=%d)"
                 % (PICK["run_id"], len(W)))
    ax.legend(loc="upper right")
    ax.grid(alpha=0.25)
    out = Path("audit_v04/speed_profile_%s.png" % PICK["run_id"])
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    print("已保存: %s" % out)
except ImportError:
    out = Path("audit_v04/speed_profile_%s.csv" % PICK["run_id"])
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "agent_id", "v_xy_m_s"])
        for a in sorted(obs):
            for t, v in obs[a]:
                w.writerow([t, a, v])
    print("无 matplotlib, 已改为 CSV: %s" % out)
    print("阶段窗口边界(供文字描述):")
    for w in sorted(W, key=lambda x: (x["agent_id"], x["start_s"])):
        print("  %s %s [%.2f, %.2f]" % (w["agent_id"], w["phase"], w["start_s"], w["end_s"]))
