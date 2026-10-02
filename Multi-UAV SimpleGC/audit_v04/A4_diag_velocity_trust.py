"""A4 诊断: 核对 observations.csv 中 FCU 速度字段是否可信
用位置有限差分速度与上报速度比对, 并打印航段边界附近的原始轨迹"""
import csv
import json
import math
from pathlib import Path

EP = Path("verification/v03_pilot_final_20260930/dataset/episodes/20260930T153623Z_af3f4fcd")
AGENT = "uav_01"

rows = []
with open(EP / "observations.csv", newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["agent_id"] != AGENT:
            continue
        rows.append(dict(t=float(r["t_s"]), valid=int(r["valid"]),
                         e=float(r["east_m"]) if r["east_m"] else None,
                         n=float(r["north_m"]) if r["north_m"] else None,
                         ve=float(r["ve_m_s"]) if r["ve_m_s"] else None,
                         vn=float(r["vn_m_s"]) if r["vn_m_s"] else None))
rows.sort(key=lambda x: x["t"])

print("agent=%s  行数=%d  时间范围=[%.2f, %.2f]" % (AGENT, len(rows), rows[0]["t"], rows[-1]["t"]))

# --- 1. 上报速度 vs 位置差分速度 ---
print()
print("=" * 100)
print("1) 上报 |v_xy| 与位置差分速度对比 (仅 valid=1)")
print("=" * 100)
rep, fd, both_zero, disagree = [], [], 0, 0
for a, b in zip(rows, rows[1:]):
    if a["valid"] != 1 or b["valid"] != 1:
        continue
    if a["e"] is None or b["e"] is None:
        continue
    dt = b["t"] - a["t"]
    if dt <= 0 or dt > 0.25:
        continue
    v_rep = math.hypot(a["ve"], a["vn"])
    v_fd = math.hypot(b["e"] - a["e"], b["n"] - a["n"]) / dt
    rep.append(v_rep)
    fd.append(v_fd)
    if v_rep < 0.1 and v_fd < 0.1:
        both_zero += 1
    if abs(v_rep - v_fd) > 0.5:
        disagree += 1

n = len(rep)
print("样本对: %d" % n)
print("上报速度    : 中位数=%.4f  均值=%.4f  最大=%.4f" % (sorted(rep)[n//2], sum(rep)/n, max(rep)))
print("差分速度    : 中位数=%.4f  均值=%.4f  最大=%.4f" % (sorted(fd)[n//2], sum(fd)/n, max(fd)))
print("两者都<0.1 m/s 的样本对: %d/%d" % (both_zero, n))
print("|上报-差分|>0.5 m/s 的样本对: %d/%d" % (disagree, n))

# --- 2. 上报速度的分布 (是否长期低值) ---
print()
print("=" * 100)
print("2) 上报 |v_xy| 的分布")
print("=" * 100)
vs = sorted(math.hypot(r["ve"], r["vn"]) for r in rows if r["valid"] == 1)
m = len(vs)
for q, lbl in ((0.0, "min"), (0.05, "P05"), (0.25, "P25"), (0.5, "中位数"),
               (0.75, "P75"), (0.90, "P90"), (0.95, "P95"), (1.0, "max")):
    print("  %-6s = %.4f" % (lbl, vs[min(m - 1, int(q * (m - 1)))]))
print("  <0.3 m/s 占比 = %.4f" % (sum(v < 0.3 for v in vs) / m))
print("  <0.5 m/s 占比 = %.4f" % (sum(v < 0.5 for v in vs) / m))
print("  <1.0 m/s 占比 = %.4f" % (sum(v < 1.0 for v in vs) / m))

# --- 3. 航段边界附近的原始轨迹 ---
print()
print("=" * 100)
print("3) 航段边界附近原始轨迹 (±0.8s)")
print("=" * 100)
pw = json.loads((EP / "phase_windows.json").read_text(encoding="utf-8"))
wins = sorted([w for w in pw["windows"]
               if w["agent_id"] == AGENT and w["start_s"] is not None],
              key=lambda w: w["start_s"])

for w in wins[:6]:
    lo, hi = w["end_s"] - 0.8, w["end_s"] + 0.8
    print()
    print("--- %s (%s/%s) 窗口=[%.2f, %.2f] 时长=%.2fs ---"
          % (w["phase"], w["semantic_phase"], w["role"], w["start_s"], w["end_s"],
             w["end_s"] - w["start_s"]))
    print("      t_s    |v_xy|     v_fd      east_m     north_m")
    prev = None
    for r in rows:
        if not (lo <= r["t"] <= hi):
            continue
        v = math.hypot(r["ve"], r["vn"]) if r["valid"] == 1 else None
        if prev is not None and r["e"] is not None and prev["e"] is not None:
            dt = r["t"] - prev["t"]
            vfd = math.hypot(r["e"] - prev["e"], r["n"] - prev["n"]) / dt if dt > 0 else float("nan")
        else:
            vfd = float("nan")
        mark = "  <== 窗口结束" if abs(r["t"] - w["end_s"]) < 0.05 else ""
        print("  %7.2f  %s  %8.4f  %10.4f  %10.4f%s"
              % (r["t"], ("%7.4f" % v) if v is not None else "   n/a ",
                 vfd, r["e"] if r["e"] is not None else float("nan"),
                 r["n"] if r["n"] is not None else float("nan"), mark))
        prev = r
