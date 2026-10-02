"""A4 独立交叉验证: 每个检测到的"停住"是否发生在规划航点上
方法: 对每次停住(区间内最低速采样), 取该时刻位置, 计算到该机全部规划航点的
      最近距离。若停住确实发生在航点上, 该距离应 <= arrival_tolerance_m (1.0m)。
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


def read_obs_full(path):
    per = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["valid"] != "1":
                continue
            per.setdefault(r["agent_id"], []).append(
                (float(r["t_s"]),
                 (float(r["east_m"]), float(r["north_m"]), float(r["up_m"])),
                 math.hypot(float(r["ve_m_s"]), float(r["vn_m_s"]))))
    for a in per:
        per[a].sort()
    return per


def stops(samples, th, min_s):
    segs, run = [], []
    for s in samples:
        if s[2] < th:
            if run and s[0] - run[-1][0] > 1.5 * DT:
                segs.append(run); run = []
            run.append(s)
        else:
            if run:
                segs.append(run); run = []
    if run:
        segs.append(run)
    return [r for r in segs if r[-1][0] - r[0][0] >= min_s]


def pct(v, q):
    v = sorted(v); x = (len(v) - 1) * q; lo = int(x)
    return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (x - lo)


eps = []
for name, base in DATASETS.items():
    mf = json.loads((base / "dataset_manifest.json").read_text(encoding="utf-8"))
    for e in mf["episodes"]:
        d = base / "episodes" / e["run_id"]
        if (d / "observations.csv").exists() and (d / "manifest.json").exists():
            eps.append(dict(run_id=e["run_id"], dir=d))

dists, n_stops, n_wp_ok = [], 0, 0
per_ep = []
for ep in eps:
    man = json.loads((ep["dir"] / "manifest.json").read_text(encoding="utf-8"))
    sc = json.loads((Path(man["run_directory"]) / "scenario.json").read_text(encoding="utf-8"))
    tol = sc["task_spec"]["execution"]["arrival_tolerance_m"]
    wps = {v["id"]: [] for v in sc["vehicles"]}
    for p in sc["phases"]:
        for a, t in p["targets"].items():
            wps[a].append((t["east_m"], t["north_m"], t["up_m"]))
    obs = read_obs_full(ep["dir"] / "observations.csv")
    ep_d = []
    for a in sorted(obs):
        for seg in stops(obs[a], 0.3, 0.2):
            tmin = min(seg, key=lambda s: s[2])
            pos = tmin[1]
            d = min(math.dist(pos, w) for w in wps[a]) if wps[a] else None
            if d is None:
                continue
            ep_d.append(d)
            dists.append(d)
            n_stops += 1
            n_wp_ok += int(d <= tol)
    per_ep.append((ep["run_id"], len(ep_d),
                   statistics.median(ep_d) if ep_d else None,
                   max(ep_d) if ep_d else None))

print("=" * 104)
print("停住点位置 -> 最近规划航点距离 (tol = arrival_tolerance_m = 1.0 m)")
print("=" * 104)
print("%-24s %7s %10s %10s" % ("episode", "停住数", "中位距离", "最大距离"))
for rid, n, md, mx in per_ep:
    print("%-24s %7d %10s %10s" %
          (rid, n, ("%.3f" % md) if md is not None else "n/a",
           ("%.3f" % mx) if mx is not None else "n/a"))

print()
print("汇总: 停住点总数 = %d" % n_stops)
print("  距离中位数 = %.4f m" % statistics.median(dists))
print("  距离均值   = %.4f m" % statistics.mean(dists))
print("  P90        = %.4f m" % pct(dists, 0.90))
print("  P99        = %.4f m" % pct(dists, 0.99))
print("  最大       = %.4f m" % max(dists))
print("  <= 1.0 m   = %d/%d (%.2f%%)" % (n_wp_ok, n_stops, 100.0 * n_wp_ok / n_stops))
for t in (0.5, 1.0, 2.0, 3.0):
    k = sum(d <= t for d in dists)
    print("  <= %.1f m   = %d/%d (%.2f%%)" % (t, k, n_stops, 100.0 * k / n_stops))
