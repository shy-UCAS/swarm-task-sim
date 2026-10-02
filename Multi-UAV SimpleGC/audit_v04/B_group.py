"""B1-B5: 样本协议与模型输入"""
import csv
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATASETS = {
    "v03_pilot_final": ROOT / "verification/v03_pilot_final_20260930/dataset",
    "v03_integration": ROOT / "verification/v03_integration_20260930/dataset_final",
}
GEN = ROOT / "generated/recon_pilot_v03_20260930"
OUT = ROOT / "audit_v04"


def fnum(x):
    return float(x) if x not in (None, "") else None


def pct(v, q):
    if not v:
        return None
    v = sorted(v)
    x = (len(v) - 1) * q
    lo = int(x)
    return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (x - lo)


def write_csv(name, header, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print("  -> %s (%d 行)" % (name, len(rows)))


def episodes():
    eps = []
    for name, base in DATASETS.items():
        mf = json.loads((base / "dataset_manifest.json").read_text(encoding="utf-8"))
        for e in mf["episodes"]:
            d = base / "episodes" / e["run_id"]
            if (d / "observations.csv").exists():
                eps.append(dict(dataset=name, run_id=e["run_id"],
                                scenario=e.get("scenario_id"), dir=d))
    return eps


EPS = episodes()
print("episode 总数: %d\n" % len(EPS))

# =====================================================================
print("=" * 104)
print("B1 观测窗口覆盖范围")
print("=" * 104)
b1_rows, b1 = [], []
for ep in EPS:
    man = json.loads((ep["dir"] / "manifest.json").read_text(encoding="utf-8"))
    meta = json.loads((Path(man["run_directory"]) / "metadata.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader(open(ep["dir"] / "observations.csv", newline="", encoding="utf-8")))
    t_all = sorted({float(r["t_s"]) for r in rows})
    first = min((r for r in rows if float(r["t_s"]) == t_all[0]),
                key=lambda r: r["agent_id"])
    last = min((r for r in rows if float(r["t_s"]) == t_all[-1]),
               key=lambda r: r["agent_id"])
    pw = json.loads((ep["dir"] / "phase_windows.json").read_text(encoding="utf-8"))
    W = [w for w in pw["windows"] if w["start_s"] is not None and w["end_s"] is not None]
    if not W:
        print("  [跳过窗口列] %s: phase_windows 无可用窗口 (run_status=%s)"
              % (ep["run_id"], man.get("run_status")))
        b1_rows.append([ep["run_id"], ep["dataset"], "%.3f" % t_all[0], "%.3f" % t_all[-1],
                        "%.2f" % (t_all[-1] - t_all[0]), len(t_all),
                        first["up_m"] or "n/a", last["up_m"] or "n/a",
                        "n/a", "n/a", "n/a", "n/a",
                        "%.2f" % meta["elapsed_s"],
                        "%.4f" % ((t_all[-1] - t_all[0]) / meta["elapsed_s"])])
        continue
    w0, w1 = min(w["start_s"] for w in W), max(w["end_s"] for w in W)
    obs_span = t_all[-1] - t_all[0]
    b1.append(dict(episode=ep["run_id"], dataset=ep["dataset"],
                   obs_first_t=t_all[0], obs_last_t=t_all[-1], obs_span=obs_span, frames=len(t_all),
                   first_up=fnum(first["up_m"]), last_up=fnum(last["up_m"]),
                   win_first_start=w0, win_last_end=w1,
                   gap_head=w0 - t_all[0], gap_tail=t_all[-1] - w1,
                   elapsed=meta.get("elapsed_s"),
                   boundary_semantics=meta.get("clock")))
    b1_rows.append([ep["run_id"], ep["dataset"], "%.3f" % t_all[0], "%.3f" % t_all[-1],
                    "%.2f" % obs_span, len(t_all),
                    "n/a" if b1[-1]["first_up"] is None else "%.4f" % b1[-1]["first_up"],
                    "n/a" if b1[-1]["last_up"] is None else "%.4f" % b1[-1]["last_up"],
                    "%.3f" % w0, "%.3f" % w1,
                    "%.3f" % b1[-1]["gap_head"], "%.3f" % b1[-1]["gap_tail"],
                    "%.2f" % meta["elapsed_s"], "%.4f" % (obs_span / meta["elapsed_s"])])

write_csv("B1_window_edges.csv",
          ["run_id", "dataset", "obs_first_t_s", "obs_last_t_s", "obs_span_s", "frames",
           "first_row_up_m", "last_row_up_m", "window_first_start_s", "window_last_end_s",
           "gap_head_s", "gap_tail_s", "elapsed_s", "obs_span_over_elapsed"],
          b1_rows)
gh = [x["gap_head"] for x in b1 if isinstance(x["gap_head"], float)]
gt = [x["gap_tail"] for x in b1 if isinstance(x["gap_tail"], float)]
ratio = [x["obs_span"] / x["elapsed"] for x in b1]
fu = [x["first_up"] for x in b1 if x["first_up"] is not None]
lu = [x["last_up"] for x in b1 if x["last_up"] is not None]
print("观测首行 t_s - 首个阶段窗口 start_s : 中位 %.4f s  范围 [%.4f, %.4f]" %
      (statistics.median(gh), min(gh), max(gh)))
print("最后阶段窗口 end_s - 观测末行 t_s : 中位 %.4f s  范围 [%.4f, %.4f]" %
      (statistics.median(gt), min(gt), max(gt)))
print("观测跨度 / elapsed_s            : 中位 %.4f  范围 [%.4f, %.4f]" %
      (statistics.median(ratio), min(ratio), max(ratio)))
print("首行 up_m: 中位 %.3f  范围 [%.3f, %.3f]  (takeoff_alt_m = 8.0)" %
      (statistics.median(fu), min(fu), max(fu)))
print("末行 up_m: 中位 %.3f  范围 [%.3f, %.3f]" %
      (statistics.median(lu), min(lu), max(lu)))

# =====================================================================
print()
print("=" * 104)
print("B2 时间网格")
print("=" * 104)
b2_rows = []
for ep in EPS:
    rows = list(csv.DictReader(open(ep["dir"] / "observations.csv", newline="", encoding="utf-8")))
    by_t = Counter(float(r["t_s"]) for r in rows)
    agents = sorted({r["agent_id"] for r in rows})
    n = len(by_t)
    full = sum(1 for c in by_t.values() if c == len(agents))
    zero = sum(1 for r in rows if r["valid"] == "0")
    stamps = sorted(by_t)
    steps = sorted({round(b - a, 6) for a, b in zip(stamps, stamps[1:])})
    b2_rows.append([ep["run_id"], len(agents), n, full, "%d/%d" % (full, n),
                    zero, len(rows), "%.5f" % (zero / len(rows)),
                    ";".join("%.3f" % s for s in steps)])
write_csv("B2_time_grid.csv",
          ["run_id", "agents", "distinct_t", "t_with_all_agents", "coverage",
           "mask_false_rows", "total_rows", "mask_false_fraction", "t_step_set"],
          b2_rows)
ok = [r for r in b2_rows if int(r[6]) > 0]
allc = [r[3] / r[2] for r in ok]
print("每 t_s 对所有 agent 都有行的比例: %d/%d episode 均为 1.0000 %s" %
      (sum(1 for c in allc if c == 1.0), len(allc),
       "(确认)" if all(c == 1.0 for c in allc) else "(存在例外)"))
print("不同 t 步长集合: %s" % sorted({r[8] for r in ok}))
bad = [r for r in b2_rows if float(r[7]) > 0]
print("含 mask=false 的 episode: %d/%d" % (len(bad), len(b2_rows)))
for r in bad:
    print("    %s: %s 行 (%s)" % (r[0], r[5], r[7]))
print("总行数 = %d, 其中 mask=false = %d" %
      (sum(int(r[6]) for r in b2_rows), sum(int(r[5]) for r in b2_rows)))

# =====================================================================
print()
print("=" * 104)
print("B3 坐标与零填充")
print("=" * 104)
b3_rows = []
for ep in EPS:
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for r in csv.DictReader(open(ep["dir"] / "observations.csv", newline="", encoding="utf-8")):
        if r["valid"] != "1":
            continue
        for k, c in enumerate(("east_m", "north_m", "up_m")):
            v = float(r[c])
            lo[k] = min(lo[k], v)
            hi[k] = max(hi[k], v)
    b3_rows.append([ep["run_id"], "%.3f" % lo[0], "%.3f" % hi[0], "%.3f" % lo[1], "%.3f" % hi[1],
                    "%.3f" % lo[2], "%.3f" % hi[2],
                    "是" if lo[0] <= 0 <= hi[0] else "否",
                    "是" if lo[1] <= 0 <= hi[1] else "否",
                    "是" if lo[2] <= 0 <= hi[2] else "否"])
write_csv("B3_coordinate_ranges.csv",
          ["run_id", "east_min", "east_max", "north_min", "north_max",
           "up_min", "up_max", "zero_in_east", "zero_in_north", "zero_in_up"],
          b3_rows)
print("up_m 下界: 全部 episode 的最小值 = %.3f m" % min(float(r[5]) for r in b3_rows))
N3 = len(b3_rows)
print("0 落在 east 范围内的 episode: %d/%d" % (sum(1 for r in b3_rows if r[7] == "是"), N3))
print("0 落在 north 范围内的 episode: %d/%d" % (sum(1 for r in b3_rows if r[8] == "是"), N3))
print("0 落在 up 范围内的 episode: %d/%d" % (sum(1 for r in b3_rows if r[9] == "是"), N3))
print("up 下界中位 %.3f  上界中位 %.3f" %
      (statistics.median(float(r[5]) for r in b3_rows),
       statistics.median(float(r[6]) for r in b3_rows)))
print("三角同时落在范围 (即 (0,0,0) 与合法位置混淆) 的 episode: %d/%d" %
      (sum(1 for r in b3_rows if r[7] == "是" and r[8] == "是" and r[9] == "是"), N3))
_e0 = [float(r[1]) for r in b3_rows]; _e1 = [float(r[2]) for r in b3_rows]
_n0 = [float(r[3]) for r in b3_rows]; _n1 = [float(r[4]) for r in b3_rows]
print("east  全局范围: [%.3f, %.3f]" % (min(_e0), max(_e1)))
print("north 全局范围: [%.3f, %.3f]" % (min(_n0), max(_n1)))
print("east  每 episode 跨度 中位 %.3f  north 中位 %.3f" %
      (statistics.median([b-a for a,b in zip(_e0,_e1)]),
       statistics.median([b-a for a,b in zip(_n0,_n1)])))

from swarm_sim.episode_loader import load_episode, FEATURE_COLUMNS
sample = load_episode(EPS[0]["dir"])
import itertools
flat = list(itertools.chain.from_iterable(f for f in sample["x"]))
print()
print("load_episode 输出: x 形状 = T x N x %d, mask 形状 = T x N" % len(sample["x"][0][0]))
print("  metadata['normalized'] = %r" % sample["metadata"]["normalized"])
print("  归一化检查: 样本 x 中 valid=1 的坐标是否与 observations.csv 原值一致 -> ", end="")
src = {}
for r in csv.DictReader(open(EPS[0]["dir"] / "observations.csv", newline="", encoding="utf-8")):
    src[(float(r["t_s"]), r["agent_id"])] = r
ok = True
for ti, t in enumerate(sample["t_s"]):
    for ai, a in enumerate(sample["agent_ids"]):
        if not sample["mask"][ti][ai]:
            continue
        r = src[(t, a)]
        if abs(sample["x"][ti][ai][0] - float(r["east_m"])) > 1e-12:
            ok = False
print("一致" if ok else "不一致")

# =====================================================================
print()
print("=" * 104)
print("B4 智能体顺序是否携带空间角色")
print("=" * 104)
b4_rows = []
agree_strip = agree_coord = total = 0
for fp in sorted((GEN / "scenes").glob("*.json")):
    s = json.loads(fp.read_text(encoding="utf-8"))
    ts = s["task_spec"]
    axis = s["planning"]["partition_axis"]
    ag2p = s["planning"]["agent_to_partition"]
    parts = [p["id"] for p in s["planning"]["region_partitions"]]
    veh = {v["id"]: v for v in ts["scenario"]["vehicles"]}
    ids = sorted(veh)
    coord = sorted(ids, key=lambda a: (veh[a][f"{axis}_m"], a))
    total += 1
    by_strip = [ag2p[a] == parts[k] for k, a in enumerate(ids)]
    by_coord = [ids[k] == coord[k] for k in range(len(ids))]
    if all(by_strip):
        agree_strip += 1
    if all(by_coord):
        agree_coord += 1
    b4_rows.append([fp.stem, len(ids), axis,
                    "1" if all(by_strip) else "0", "1" if all(by_coord) else "0",
                    "|".join(ag2p[a] for a in ids),
                    "|".join(coord)])
write_csv("B4_agent_order.csv",
          ["mission_id", "agents", "axis", "id_order_eq_strip_order",
           "id_order_eq_coord_order", "strip_by_id_order", "coord_order"],
          b4_rows)
print("已生成任务: k 号飞机(ID 序) == 第 k 条带 : %d/%d = %.4f" %
      (agree_strip, total, agree_strip / total))
print("已生成任务: k 号飞机(ID 序) == 剖分轴坐标第 k 位 : %d/%d = %.4f" %
      (agree_coord, total, agree_coord / total))

b4b_rows = []
for ep in EPS:
    man = json.loads((ep["dir"] / "manifest.json").read_text(encoding="utf-8"))
    sc = json.loads((Path(man["run_directory"]) / "scenario.json").read_text(encoding="utf-8"))
    ts = sc["task_spec"]
    axis = sc["planning"]["partition_axis"]
    parts = [p["id"] for p in sc["planning"]["region_partitions"]]
    ag2p = sc["planning"]["agent_to_partition"]
    veh = {v["id"]: v for v in ts["scenario"]["vehicles"]}
    ids = sorted(veh)
    coord = sorted(ids, key=lambda a: (veh[a][f"{axis}_m"], a))
    b4b_rows.append([ep["run_id"], len(ids), axis,
                     "1" if all(ag2p[a] == parts[k] for k, a in enumerate(ids)) else "0",
                     "1" if ids == coord else "0"])
write_csv("B4_agent_order_episodes.csv",
          ["run_id", "agents", "axis", "id_order_eq_strip_order", "id_order_eq_coord_order"],
          b4b_rows)
NB = len(b4b_rows)
print("实测 episode: 两项一致率 = %d/%d, %d/%d" %
      (sum(1 for r in b4b_rows if r[3] == "1"), NB,
       sum(1 for r in b4b_rows if r[4] == "1"), NB))

print()
print("加载器 agent 排序规则: episode_loader.py:58-68 -> expected = sorted(expected)")
print("  先取 manifest['agent_ids'] (缺则取 task.json 的 vehicles), 去重校验后 **按字符串升序排序**")
print("  帧内顺序即该排序; 与 scenario 中的物理坐标无关。")
print("规划器条带分配规则: mission_planning.py:128 -> ordering = sorted(vehicles, key=(axis 坐标, id))")
print("  即先按剖分轴坐标、坐标并列时按 id 排序; 因此 ID 升序与坐标升序在本生成器下重合。")

# =====================================================================
print()
print("=" * 104)
print("B5 序列长度分布")
print("=" * 104)
b5_rows = []
for ep in EPS:
    rows = list(csv.DictReader(open(ep["dir"] / "observations.csv", newline="", encoding="utf-8")))
    T = len({float(r["t_s"]) for r in rows})
    man = json.loads((ep["dir"] / "manifest.json").read_text(encoding="utf-8"))
    sc = json.loads((Path(man["run_directory"]) / "scenario.json").read_text(encoding="utf-8"))
    ts = sc["task_spec"]
    ex = ts["execution"]
    axis = sc["planning"]["partition_axis"]
    parts = sc["planning"]["region_partitions"]
    strip = parts[0]
    cross = strip["width_m"] if axis == "east" else strip["height_m"]
    lanes = max(1, math.ceil(cross / ts["planner"]["lane_spacing_m"]))
    b5_rows.append([ep["run_id"], len(sc["vehicles"]), T, ts["mission"]["return_required"],
                    lanes, sc["planning"]["execution_phase_count"],
                    "%.1f" % ex["speed_m_s"], "%.1f" % ex["record_hz"],
                    "%.2f" % man["duration_s"], "%.1f" % (T / ex["record_hz"])])
write_csv("B5_sequence_length.csv",
          ["run_id", "agents", "frames_T", "return_required", "lanes",
           "execution_phase_count", "speed_m_s", "record_hz", "duration_s", "T_over_hz"],
          b5_rows)
Ts = [int(r[2]) for r in b5_rows]
print("T 范围 [%d, %d], 中位 %d" % (min(Ts), max(Ts), statistics.median(Ts)))
by_key = {}
for r in b5_rows:
    by_key.setdefault((r[1], r[3], r[4]), []).append(int(r[2]))
print()
print("%-28s %s" % ("(飞机数, return_required, lanes)", "T 取值"))
for k in sorted(by_key, key=lambda x: (x[0], str(x[1]), x[2])):
    v = by_key[k]
    print("  %-28s n=%d  T 中位 %d  范围 [%d, %d]  T/(2*lanes+1+ret) 中位 %.1f"
          % (str(k), len(v), statistics.median(v), min(v), max(v),
             statistics.median(v) / (2 * k[2] + 1 + int(k[1]))))
print()
print("T 与 duration_s*record_hz 的关系: %s" %
      ("T = floor(duration*10)+1  (见 analysis.py:72-73)"))
