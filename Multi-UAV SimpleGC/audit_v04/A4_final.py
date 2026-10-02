"""A4 (最终): 停靠量化
发现: task_target_verified(窗口结束) 早于真实停住, 因为 1m 容差 + 0.5s 驻留
      在减速段即可满足。因此除任务要求的 +/-0.3s 窗口外, 追加 [end-0.3, end+2.0] 窗口。
"""
import csv
import json
import math
import statistics
from pathlib import Path

DATASETS = {
    "v03_pilot_final": Path("verification/v03_pilot_final_20260930/dataset"),
    "v03_integration": Path("verification/v03_integration_20260930/dataset_final"),
}
DT = 0.1
MIN_DWELL_S = 1.0        # 任务书要求
MIN_STOP_S = 0.2         # 附加: 判定"是否停住"的宽松阈值
END_WIN = 0.3            # 任务书要求的 +/-0.3s
EXT_S = 2.0              # 附加: 向后延伸


def pct(v, q):
    if not v:
        return None
    v = sorted(v)
    x = (len(v) - 1) * q
    lo = int(x)
    return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (x - lo)


def load_episodes():
    eps = []
    for name, base in DATASETS.items():
        mf = json.loads((base / "dataset_manifest.json").read_text(encoding="utf-8"))
        for e in mf["episodes"]:
            eps.append(dict(dataset=name, run_id=e["run_id"], scenario_id=e.get("scenario_id"),
                            dir=base / "episodes" / e["run_id"]))
    return eps


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


def leg_geometry(run_dir):
    sc = json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))
    spawn = {v["id"]: (v["east_m"], v["north_m"]) for v in sc["vehicles"]}
    out = {}
    for agent in spawn:
        cur, acc = spawn[agent], {}
        for p in sc["phases"]:
            t = p["targets"][agent]
            nxt = (t["east_m"], t["north_m"])
            d = (nxt[0] - cur[0], nxt[1] - cur[1])
            acc[p["name"]] = (math.hypot(*d), d)
            cur = nxt
        out[agent] = acc
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


E = load_episodes()
print("episode 总数: %d\n" % len(E))

dwell_rows, legrec, zero_legs, sync_rows = [], [], [], []
stationary = {0.3: [], 0.5: []}

for ep in E:
    need = ["observations.csv", "phase_windows.json", "allocation.json", "manifest.json"]
    if not all((ep["dir"] / n).exists() for n in need):
        print("跳过 %s" % ep["run_id"]); continue
    obs = read_obs(ep["dir"] / "observations.csv")
    pw = json.loads((ep["dir"] / "phase_windows.json").read_text(encoding="utf-8"))
    alloc = json.loads((ep["dir"] / "allocation.json").read_text(encoding="utf-8"))
    man = json.loads((ep["dir"] / "manifest.json").read_text(encoding="utf-8"))
    geom = leg_geometry(Path(man["run_directory"]))
    axis = alloc["partition_axis"]
    pc = alloc["execution_phase_count"]

    W = [w for w in pw["windows"] if w["start_s"] is not None and w["end_s"] is not None]
    if not W:
        print("跳过 %s: 无可用窗口" % ep["run_id"]); continue
    m0, m1 = min(w["start_s"] for w in W), max(w["end_s"] for w in W)
    mdur = m1 - m0

    # (a) 停靠段
    dw = {}
    for th in (0.3, 0.5):
        dw[th] = {}
        for strict in (True, False):
            ms = MIN_DWELL_S if strict else MIN_STOP_S
            dw[th][strict] = {a: runs_below(obs.get(a, []), th, ms) for a in obs}
    dwell_rows.append(dict(episode=ep["run_id"], dataset=ep["dataset"], agents=len(obs),
                           execution_phase_count=pc, window_s=mdur,
                           strict03={a: len(dw[0.3][True][a]) for a in obs},
                           strict05={a: len(dw[0.5][True][a]) for a in obs},
                           loose03={a: len(dw[0.3][False][a]) for a in obs},
                           loose05={a: len(dw[0.5][False][a]) for a in obs}))

    # (c) 静止占比（各机停靠时间之和 / (窗口 * 机数)）
    for th in (0.3, 0.5):
        tot = 0.0
        for a in obs:
            for (x, y) in dw[th][True][a]:
                lo, hi = max(x, m0), min(y, m1)
                if hi > lo:
                    tot += hi - lo
        den = mdur * len(obs)
        stationary[th].append(tot / den if den > 0 else 0.0)

    # (b) 航段窗口结束前后最低速度
    for w in W:
        ag, ph = w["agent_id"], w["phase"]
        samp = obs.get(ag, [])
        lit = [(t, s) for t, s in samp if w["end_s"] - END_WIN <= t <= w["end_s"] + END_WIN]
        ext = [(t, s) for t, s in samp if w["end_s"] - END_WIN <= t <= w["end_s"] + EXT_S]
        L, d = geom.get(ag, {}).get(ph, (None, (0.0, 0.0)))
        cls = classify(w["semantic_phase"], w["role"], L if L is not None else 0.0, d, axis)
        rec = dict(cls=cls, episode=ep["run_id"], agent=ag, phase=ph,
                   semantic=w["semantic_phase"], role=w["role"], leg_length_m=L,
                   end_s=w["end_s"],
                   literal_min=min((s for _, s in lit), default=None),
                   extended_min=min((s for _, s in ext), default=None))
        if ext:
            tb, _ = min(ext, key=lambda x: x[1])
            rec["min_lag_s"] = tb - w["end_s"]
        legrec.append(rec)
        if cls == "零长度":
            sem = sorted(x["phase"] for x in W if x["agent_id"] == ag and x["semantic_phase"] == "observe")
            zero_legs.append(dict(episode=ep["run_id"], agent=ag, phase=ph,
                                  idx_in_observe=sem.index(ph)))

    # (d) 全机同步停靠（宽松阈值 0.3，因为停住仅约 0.3-0.7s）
    agents = sorted(obs)
    iv = {a: dw[0.3][False][a] for a in agents}
    n = int(round(mdur / DT)) + 1
    both = sum(1 for i in range(n)
               if all(any(x <= m0 + i * DT <= y for (x, y) in iv[a]) for a in agents))
    alliv = sorted(v for a in agents for v in iv[a])
    merged = []
    for x, y in alliv:
        if merged and x <= merged[-1][1] + 1e-9:
            merged[-1][1] = max(merged[-1][1], y)
        else:
            merged.append([x, y])
    common = 0
    for lo, hi in merged:
        ilo, ihi = lo, hi
        ok = True
        for a in agents:
            hit = [(max(x, lo), min(y, hi)) for (x, y) in iv[a] if min(y, hi) > max(x, lo)]
            if not hit:
                ok = False; break
            ilo = max(ilo, min(h[0] for h in hit))
            ihi = min(ihi, max(h[1] for h in hit))
        if ok and ihi > ilo:
            common += 1
    sync_rows.append(dict(episode=ep["run_id"], agents=len(agents),
                          sync_frac=both / n if n else 0.0,
                          fleet_events=len(merged), common_events=common,
                          stops_per_agent={a: len(iv[a]) for a in agents}))

for nm, obj in (("A4_dwell.json", dwell_rows), ("A4_legs.json", legrec),
                ("A4_zero_len.json", zero_legs), ("A4_sync.json", sync_rows)):
    Path("audit_v04/" + nm).write_text(json.dumps(obj, indent=2), encoding="utf-8")

print("=" * 96)
print("(a) 每机停靠段数量 vs execution_phase_count")
print("=" * 96)
for r in dwell_rows:
    print("%s [%s] agents=%d  phases=%d  window=%.1fs" %
          (r["episode"], r["dataset"], r["agents"], r["execution_phase_count"], r["window_s"]))
    print("   >=1.0s@0.3: %-58s 合计=%d" % (str(r["strict03"]), sum(r["strict03"].values())))
    print("   >=0.2s@0.3: %-58s 合计=%d" % (str(r["loose03"]), sum(r["loose03"].values())))
    print("   >=0.2s@0.5: %-58s 合计=%d" % (str(r["loose05"]), sum(r["loose05"].values())))

print()
print("=" * 96)
print("(b) 航段窗口结束附近最低 |v_xy|")
print("=" * 96)
for key, lbl in (("literal_min", "任务书口径: 窗口结束 +/-0.3s"),
                 ("extended_min", "附加口径: 窗口结束 -0.3s ~ +2.0s")):
    byc = {}
    for r in legrec:
        if r.get(key) is not None:
            byc.setdefault(r["cls"], []).append(r[key])
    print()
    print("--- %s ---" % lbl)
    print("%-10s %5s %9s %9s %9s %9s %9s %9s" %
          ("类别", "n", "中位数", "均值", "P10", "P90", "最小", "最大"))
    for c in ["扫描线", "换线", "零长度", "进近/返航", "空转填充", "其他"]:
        if c not in byc:
            continue
        v = byc[c]
        print("%-10s %5d %9.4f %9.4f %9.4f %9.4f %9.4f %9.4f" %
              (c, len(v), statistics.median(v), statistics.mean(v),
               pct(v, .1), pct(v, .9), min(v), max(v)))
    allv = [r[key] for r in legrec if r.get(key) is not None]
    print("%-10s %5d %9.4f %9.4f %9.4f %9.4f %9.4f %9.4f" %
          ("全部", len(allv), statistics.median(allv), statistics.mean(allv),
           pct(allv, .1), pct(allv, .9), min(allv), max(allv)))

lags = [r["min_lag_s"] for r in legrec if r.get("min_lag_s") is not None]
if lags:
    print()
    print("最低速度相对窗口结束的滞后: 中位数=%.2fs  P10=%.2fs  P90=%.2fs  范围=[%.2f, %.2f]"
          % (statistics.median(lags), pct(lags, .1), pct(lags, .9), min(lags), max(lags)))
ex = [r["extended_min"] for r in legrec if r.get("extended_min") is not None]
print("附加口径下 extended_min < 0.3 m/s 的航段: %d/%d" %
      (sum(v < 0.3 for v in ex), len(ex)))
print("附加口径下 extended_min < 0.2 m/s 的航段: %d/%d" %
      (sum(v < 0.2 for v in ex), len(ex)))

print()
print("=" * 96)
print("(c) 静止时间占任务窗口比例")
print("=" * 96)
for th in (0.3, 0.5):
    f = stationary[th]
    print("  阈值%.1f (>=1.0s): 中位数=%.4f 均值=%.4f 范围=[%.4f, %.4f] n=%d" %
          (th, statistics.median(f), statistics.mean(f), min(f), max(f), len(f)))

print()
print("=" * 96)
print("(d) 全机同步停靠 (阈值 0.3 m/s, >=0.2s)")
print("=" * 96)
for s in sync_rows:
    print("  %s agents=%d 同步时间占比=%.4f 停靠事件=%d 全机共同重叠=%d 各机停靠数=%s" %
          (s["episode"], s["agents"], s["sync_frac"], s["fleet_events"],
           s["common_events"], s["stops_per_agent"]))

print()
print("=" * 96)
print("(e) 零长度航段")
print("=" * 96)
cnt = {}
for z in zero_legs:
    cnt[z["idx_in_observe"]] = cnt.get(z["idx_in_observe"], 0) + 1
print("总数=%d  按 observe 内序号分布=%s  全部为序号0? %s" %
      (len(zero_legs), dict(sorted(cnt.items())),
       all(z["idx_in_observe"] == 0 for z in zero_legs)))
