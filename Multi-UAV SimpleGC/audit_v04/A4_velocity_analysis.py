"""A4 (重做): 基于 observations.csv 的 |v_xy| 量化停靠"""
import csv
import json
import math
import statistics
from pathlib import Path

DATASETS = {
    "v03_pilot_final": Path("verification/v03_pilot_final_20260930/dataset"),
    "v03_integration": Path("verification/v03_integration_20260930/dataset_final"),
}
DT = 0.1                  # record_hz = 10
DWELL_THRESHOLDS = (0.3, 0.5)
MIN_DWELL_S = 1.0
END_WINDOW_S = 0.3


def pct(values, q):
    if not values:
        return None
    v = sorted(values)
    x = (len(v) - 1) * q
    lo = int(x)
    return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (x - lo)


def load_episodes():
    eps = []
    for name, base in DATASETS.items():
        mf = json.loads((base / "dataset_manifest.json").read_text(encoding="utf-8"))
        for e in mf["episodes"]:
            d = base / "episodes" / e["run_id"]
            eps.append(dict(dataset=name, run_id=e["run_id"],
                            scenario_id=e.get("scenario_id"), dir=d))
    return eps


def read_obs(path):
    """-> {agent: [(t, speed)]} 只保留 valid=1 的行"""
    per = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["valid"] != "1":
                continue
            ve, vn = float(row["ve_m_s"]), float(row["vn_m_s"])
            per.setdefault(row["agent_id"], []).append((float(row["t_s"]), math.hypot(ve, vn)))
    for a in per:
        per[a].sort()
    return per


def dwell_segments(samples, threshold):
    """极大连续区间: speed < threshold 且 duration >= MIN_DWELL_S"""
    segs, run = [], []
    for t, s in samples:
        if s < threshold:
            if run and t - run[-1][0] > 1.5 * DT:
                segs.append(run)
                run = []
            run.append((t, s))
        else:
            if run:
                segs.append(run)
                run = []
    if run:
        segs.append(run)
    return [(r[0][0], r[-1][0]) for r in segs if r[-1][0] - r[0][0] >= MIN_DWELL_S]


def leg_lengths(run_dir):
    """-> {agent: {phase_name: (length_m, (dE, dN))}} 用 spawn 作为 leg_000 的前驱"""
    sc = json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))
    phases = sc["phases"]
    spawn = {v["id"]: (v["east_m"], v["north_m"]) for v in sc["vehicles"]}
    out = {}
    for agent in spawn:
        cur = spawn[agent]
        out[agent] = {}
        for p in phases:
            t = p["targets"][agent]
            nxt = (t["east_m"], t["north_m"])
            delta = (nxt[0] - cur[0], nxt[1] - cur[1])
            out[agent][p["name"]] = (math.hypot(*delta), delta)
            cur = nxt
    return out


def classify(semantic, role, length, delta, axis):
    if role == "idle_padding":
        return "空转填充"
    if semantic in ("approach", "return"):
        return "进近/返航"
    if semantic == "observe":
        if length < 0.1:
            return "零长度"
        sweep = abs(delta[0]) if axis == "north" else abs(delta[1])
        cross = abs(delta[1]) if axis == "north" else abs(delta[0])
        return "扫描线" if sweep >= cross else "换线"
    return "其他"


episodes = load_episodes()
print("episode 总数: %d\n" % len(episodes))

summary_rows = []
end_mins = []
zero_length_legs = []
per_episode_sync = []
stationary_fracs = {th: [] for th in DWELL_THRESHOLDS}

for ep in episodes:
    obs_path = ep["dir"] / "observations.csv"
    pw_path = ep["dir"] / "phase_windows.json"
    alloc_path = ep["dir"] / "allocation.json"
    man_path = ep["dir"] / "manifest.json"
    if not (obs_path.exists() and pw_path.exists() and alloc_path.exists() and man_path.exists()):
        print("跳过 %s: 缺少产物" % ep["run_id"])
        continue

    obs = read_obs(obs_path)
    pw = json.loads(pw_path.read_text(encoding="utf-8"))
    alloc = json.loads(alloc_path.read_text(encoding="utf-8"))
    man = json.loads(man_path.read_text(encoding="utf-8"))
    run_dir = Path(man["run_directory"])
    lengths = leg_lengths(run_dir)
    axis = alloc["partition_axis"]
    phase_count = alloc["execution_phase_count"]

    windows = [w for w in pw["windows"] if w["start_s"] is not None and w["end_s"] is not None]
    if not windows:
        print("跳过 %s: phase_windows 无可用窗口" % ep["run_id"])
        continue
    m_start = min(w["start_s"] for w in windows)
    m_end = max(w["end_s"] for w in windows)
    m_dur = m_end - m_start

    per_agent_dwell = {}
    for th in DWELL_THRESHOLDS:
        per_agent_dwell[th] = {a: dwell_segments(obs.get(a, []), th) for a in obs}

    for th in DWELL_THRESHOLDS:
        total = 0.0
        for ag in obs:
            for (a, b) in per_agent_dwell[th][ag]:
                lo, hi = max(a, m_start), min(b, m_end)
                if hi > lo:
                    total += hi - lo
        denom = m_dur * len(obs)
        stationary_fracs[th].append(total / denom if denom > 0 else 0.0)

    for w in windows:
        ag, ph = w["agent_id"], w["phase"]
        lo_end, hi_end = w["end_s"] - END_WINDOW_S, w["end_s"] + END_WINDOW_S
        cand = [s for t, s in obs.get(ag, []) if lo_end <= t <= hi_end]
        if not cand:
            continue
        L, delta = lengths.get(ag, {}).get(ph, (None, (0.0, 0.0)))
        cls = classify(w["semantic_phase"], w["role"], L if L is not None else 0.0, delta, axis)
        end_mins.append(dict(cls=cls, speed=min(cand), episode=ep["run_id"], agent=ag,
                             phase=ph, semantic=w["semantic_phase"], role=w["role"],
                             leg_length_m=L, end_s=w["end_s"]))
        if cls == "零长度":
            sem_phases = sorted(x["phase"] for x in windows
                                if x["agent_id"] == ag and x["semantic_phase"] == "observe")
            zero_length_legs.append(dict(episode=ep["run_id"], agent=ag, phase=ph,
                                         idx_in_observe=sem_phases.index(ph),
                                         leg_length_m=L, end_s=w["end_s"]))

    for th in DWELL_THRESHOLDS:
        agents = sorted(obs)
        intervals = {a: per_agent_dwell[th][a] for a in agents}
        n = int(round(m_dur / DT)) + 1
        both = 0
        for i in range(n):
            t = m_start + i * DT
            if all(any(a <= t <= b for (a, b) in intervals[ag]) for ag in agents):
                both += 1
        frac = both / n if n else 0.0
        all_iv = sorted(iv for ag in agents for iv in intervals[ag])
        merged = []
        for a, b in all_iv:
            if merged and a <= merged[-1][1] + 1e-9:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        common = 0
        for lo, hi in merged:
            inter_lo, inter_hi = lo, hi
            ok = True
            for ag in agents:
                hit = [(max(a, lo), min(b, hi)) for (a, b) in intervals[ag]
                       if min(b, hi) > max(a, lo)]
                if not hit:
                    ok = False
                    break
                inter_lo = max(inter_lo, min(h[0] for h in hit))
                inter_hi = min(inter_hi, max(h[1] for h in hit))
            if ok and inter_hi > inter_lo:
                common += 1
        if abs(th - 0.3) < 1e-9:
            per_episode_sync.append(dict(episode=ep["run_id"], agents=len(agents),
                                         sync_time_frac=frac, fleet_events=len(merged),
                                         common_overlap_events=common, window_s=m_dur))

    summary_rows.append(dict(
        dataset=ep["dataset"], episode=ep["run_id"], scenario=ep["scenario_id"],
        agents=len(obs), execution_phase_count=phase_count, window_s=m_dur,
        dwell_03={a: len(per_agent_dwell[0.3][a]) for a in obs},
        dwell_05={a: len(per_agent_dwell[0.5][a]) for a in obs},
    ))

Path("audit_v04/A4_velocity_summary.json").write_text(
    json.dumps(summary_rows, indent=2), encoding="utf-8")
Path("audit_v04/A4_end_min_speeds.json").write_text(
    json.dumps(end_mins, indent=2), encoding="utf-8")
Path("audit_v04/A4_zero_length_legs.json").write_text(
    json.dumps(zero_length_legs, indent=2), encoding="utf-8")
Path("audit_v04/A4_sync.json").write_text(
    json.dumps(per_episode_sync, indent=2), encoding="utf-8")

print("=" * 78)
print("(a) 每 episode 停靠段数量 vs execution_phase_count")
print("=" * 78)
for r in summary_rows:
    d3, d5 = r["dwell_03"], r["dwell_05"]
    print("%s [%s] %s" % (r["episode"], r["dataset"], r["scenario"]))
    print("  agents=%d  execution_phase_count=%d  窗口=%.1fs"
          % (r["agents"], r["execution_phase_count"], r["window_s"]))
    print("  停靠段(<0.3m/s,>=1s): %s  合计=%d" % (d3, sum(d3.values())))
    print("  停靠段(<0.5m/s,>=1s): %s  合计=%d" % (d5, sum(d5.values())))

print()
print("=" * 78)
print("(b) 航段窗口结束时刻 +/-0.3s 内 |v_xy| 最小值")
print("=" * 78)
by_cls = {}
for e in end_mins:
    by_cls.setdefault(e["cls"], []).append(e["speed"])
order = ["扫描线", "换线", "零长度", "进近/返航", "空转填充", "其他"]
hdr = "%-10s %5s %9s %9s %9s %9s %9s %9s" % ("类别", "n", "中位数", "均值", "P10", "P90", "最小", "最大")
print(hdr)
for cls in order:
    if cls not in by_cls:
        continue
    v = by_cls[cls]
    print("%-10s %5d %9.4f %9.4f %9.4f %9.4f %9.4f %9.4f"
          % (cls, len(v), statistics.median(v), statistics.mean(v),
             pct(v, 0.10), pct(v, 0.90), min(v), max(v)))
allv = [e["speed"] for e in end_mins]
print("%-10s %5d %9.4f %9.4f %9.4f %9.4f %9.4f %9.4f"
      % ("全部", len(allv), statistics.median(allv), statistics.mean(allv),
         pct(allv, 0.10), pct(allv, 0.90), min(allv), max(allv)))

print()
print("=" * 78)
print("(c) 静止时间占任务窗口比例")
print("=" * 78)
for th in DWELL_THRESHOLDS:
    f = stationary_fracs[th]
    print("  阈值%.1f m/s: 中位数=%.4f  均值=%.4f  范围=[%.4f, %.4f]  n=%d"
          % (th, statistics.median(f), statistics.mean(f), min(f), max(f), len(f)))

print()
print("=" * 78)
print("(d) 全机同步停靠 (阈值0.3 m/s)")
print("=" * 78)
for s in per_episode_sync:
    print("  %s: agents=%d 同步时间占比=%.4f 停靠事件=%d 全机共同重叠=%d"
          % (s["episode"], s["agents"], s["sync_time_frac"],
             s["fleet_events"], s["common_overlap_events"]))

print()
print("=" * 78)
print("(e) 零长度航段核对")
print("=" * 78)
print("零长度航段总数: %d" % len(zero_length_legs))
idx_counter = {}
for z in zero_length_legs:
    idx_counter[z["idx_in_observe"]] = idx_counter.get(z["idx_in_observe"], 0) + 1
print("按 observe 语义内序号分布: %s" % dict(sorted(idx_counter.items())))
print("全部 idx_in_observe == 0 ? %s" % all(z["idx_in_observe"] == 0 for z in zero_length_legs))
lens = [z["leg_length_m"] for z in zero_length_legs if z["leg_length_m"] is not None]
if lens:
    print("长度范围: [%.9f, %.9f] m" % (min(lens), max(lens)))
print("逐条清单见 audit_v04/A4_zero_length_legs.json")
