"""D1-D3: 多样性与近重复"""
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_sim.dataset import family_split

GEN = ROOT / "generated/recon_pilot_v03_20260930"
OUT = ROOT / "audit_v04"
LANE_SPACING = 4.0


def write_csv(name, header, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print("  -> %s (%d 行)" % (name, len(rows)))


def pct(v, q):
    if not v:
        return None
    v = sorted(v)
    x = (len(v) - 1) * q
    lo = int(x)
    return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (x - lo)


# ---- 载入 100 个已规划任务 ----
listing = json.loads((GEN / "mission_list.json").read_text(encoding="utf-8"))
missions = listing["missions"]
print("mission_list 条目数: %d\n" % len(missions))

recs = []
for m in missions:
    sp = m["sampled_parameters"]
    scene = json.loads((GEN / m["scene"]).read_text(encoding="utf-8"))
    plan = scene["planning"]
    axis = plan["partition_axis"]
    parts = plan["region_partitions"]
    strip = parts[0]
    cross = strip["width_m"] if axis == "east" else strip["height_m"]
    lanes_calc = max(1, math.ceil(cross / LANE_SPACING))
    obs = len(plan["semantic_to_execution_phase_map"]["observe"])
    lanes_actual = obs / 2
    ts = scene["task_spec"]
    recs.append(dict(
        mission_id=m["mission_id"], family=m["family_id"], base=m["base_scene_id"],
        agents=sp["vehicle_count"], axis=axis, lanes=lanes_calc, lanes_actual=lanes_actual,
        obs_phases=obs, ret=sp["return_required"], side=sp["entry_side"],
        strip_m=sp["strip_width_m"], sweep_m=sp["sweep_length_m"],
        region_e=sp["region_east_m"], region_n=sp["region_north_m"],
        entry_m=sp["entry_distance_m"], speed=sp["speed_m_s"],
        phase_count=plan["execution_phase_count"],
        phase_count_expected=1 + 2 * lanes_calc + int(sp["return_required"]),
    ))

# =====================================================================
print("=" * 104)
print("D1 拓扑签名分布")
print("=" * 104)
print("签名定义: (飞机数, partition_axis, lanes, return_required), lanes = ceil(条带横向宽度 / %.1f)" % LANE_SPACING)
print()
mismatch = [r for r in recs if r["lanes"] != r["lanes_actual"]]
print("lanes 核对: ceil(条带宽/4.0) 与 实际 observe 阶段数/2 不一致的 mission: %d/%d"
      % (len(mismatch), len(recs)))
for r in mismatch[:10]:
    print("    %s: 计算 lanes=%s, 实际 observe/2=%s" % (r["mission_id"], r["lanes"], r["lanes_actual"]))
pc_bad = [r for r in recs if r["phase_count"] != r["phase_count_expected"]]
print("阶段数核对: execution_phase_count == 1+2*lanes+return 不成立的 mission: %d/%d"
      % (len(pc_bad), len(recs)))

sig = Counter((r["agents"], r["axis"], r["lanes"], r["ret"]) for r in recs)
print()
print("不同签名数: %d (n=%d)" % (len(sig), len(recs)))
print("%-30s %6s %8s" % ("(飞机数, 轴, lanes, return)", "频数", "占比"))
for k, v in sorted(sig.items(), key=lambda kv: (-kv[1], kv[0])):
    print("  %-28s %6d %7.1f%%" % (str(k), v, 100 * v / len(recs)))

sig_eq = Counter((r["agents"], r["lanes"], r["ret"]) for r in recs)
print()
print("轴等价签名 (飞机数, lanes, return_required) —— 把 east/north 视为同一拓扑:")
print("  不同签名数: %d" % len(sig_eq))
for k, v in sorted(sig_eq.items(), key=lambda kv: (-kv[1], kv[0])):
    print("  %-28s %6d %7.1f%%" % (str(k), v, 100 * v / len(recs)))

sig_eq2 = Counter((r["agents"], r["lanes"]) for r in recs)
print()
print("进一步合并 return_required 后的签名 (飞机数, lanes): 不同签名数 = %d" % len(sig_eq2))

write_csv("D1_signatures.csv",
          ["mission_id", "family_id", "agents", "partition_axis", "lanes",
           "lanes_from_observe_phases", "observe_phases", "return_required", "entry_side",
           "signature", "signature_axis_equivalent", "execution_phase_count"],
          [[r["mission_id"], r["family"], r["agents"], r["axis"], r["lanes"], r["lanes_actual"],
            r["obs_phases"], r["ret"], r["side"],
            "%d|%s|%d|%s" % (r["agents"], r["axis"], r["lanes"], r["ret"]),
            "%d|%d|%s" % (r["agents"], r["lanes"], r["ret"]), r["phase_count"]] for r in recs])

write_csv("D1_signature_frequency.csv",
          ["signature", "count", "fraction"],
          [["%d|%s|%d|%s" % k, v, "%.4f" % (v / len(recs))] for k, v in
           sorted(sig.items(), key=lambda kv: (-kv[1], kv[0]))] +
          [["AXIS_EQ %d|%d|%s" % k, v, "%.4f" % (v / len(recs))] for k, v in
           sorted(sig_eq.items(), key=lambda kv: (-kv[1], kv[0]))])

# =====================================================================
print()
print("=" * 104)
print("D2 跨 split 的签名重叠")
print("=" * 104)
for r in recs:
    r["split"] = family_split(r["family"])
    r["sig"] = (r["agents"], r["axis"], r["lanes"], r["ret"])
    r["sig_eq"] = (r["agents"], r["lanes"], r["ret"])

split_fam = defaultdict(set)
split_sig = defaultdict(set)
for r in recs:
    split_fam[r["split"]].add(r["family"])
    split_sig[r["split"]].add(r["sig"])

print("family 数 = %d, 分布: %s" % (len({r['family'] for r in recs}),
      {k: len(v) for k, v in split_fam.items()}))
print("episode 分布: %s" % dict(Counter(r["split"] for r in recs)))
print()
train_sig = split_sig.get("train", set())
train_sig_eq = {r["sig_eq"] for r in recs if r["split"] == "train"}
for name in ("test", "validation"):
    sel = [r for r in recs if r["split"] == name]
    if not sel:
        print("%s: 0 个 episode" % name)
        continue
    seen = [r for r in sel if r["sig"] in train_sig]
    seen_eq = [r for r in sel if r["sig_eq"] in train_sig_eq]
    print("%s: %d episode (来自 %d 个 family)" % (name, len(sel), len({r['family'] for r in sel})))
    print("    拓扑签名在 train 出现过的 episode: %d/%d = %.4f" % (len(seen), len(sel), len(seen) / len(sel)))
    print("    轴等价签名在 train 出现过的 episode: %d/%d = %.4f" % (len(seen_eq), len(sel), len(seen_eq) / len(sel)))
    print("    %s 的签名集合: %s" % (name, sorted(split_sig[name])))
print()
print("train 的签名集合 (%d 个): %s" % (len(train_sig), sorted(train_sig)))

write_csv("D2_split_signature_overlap.csv",
          ["mission_id", "family_id", "split", "topology_signature", "signature_in_train"],
          [[r["mission_id"], r["family"], r["split"],
            "%d|%s|%d|%s" % r["sig"], "1" if r["sig"] in train_sig else "0"] for r in recs])

# =====================================================================
print()
print("=" * 104)
print("D3 连续参数抖动幅度")
print("=" * 104)
FIELDS = [("strip_m", "条带宽度 strip_width_m"), ("sweep_m", "扫描长度 sweep_length_m"),
          ("entry_m", "进入距离 entry_distance_m"), ("region_e", "区域位置 region_east_m"),
          ("region_n", "区域位置 region_north_m"), ("speed", "速度 speed_m_s")]
d3_rows = []
print("%-26s %10s %10s %10s %10s" % ("参数", "最小值", "最大值", "极差", "相对标准差"))
for key, label in FIELDS:
    v = [r[key] for r in recs]
    m = statistics.mean(v)
    sd = statistics.pstdev(v)
    d3_rows.append([label, "%.4f" % min(v), "%.4f" % max(v), "%.4f" % (max(v) - min(v)),
                    "%.4f" % (sd / m if m else 0)])
    print("%-26s %10.4f %10.4f %10.4f %10.5f" % (label, min(v), max(v), max(v) - min(v), sd / m if m else 0))

print()
print("同一拓扑签名内的相对标准差 (仅列出样本数 >= 5 的签名):")
print("%-30s %5s %12s %12s %12s %12s" %
      ("签名", "n", "条带宽 RSD", "扫描长 RSD", "进入距 RSD", "速度 RSD"))
grouped = defaultdict(list)
for r in recs:
    grouped[r["sig"]].append(r)
d3b_rows = []
for k in sorted(grouped, key=lambda x: (-len(grouped[x]), x)):
    g = grouped[k]
    if len(g) < 5:
        continue
    rsd = {}
    for key, _ in FIELDS:
        v = [x[key] for x in g]
        m = statistics.mean(v)
        rsd[key] = statistics.pstdev(v) / m if m else 0
    print("%-30s %5d %12.5f %12.5f %12.5f %12.5f" %
          (str(k), len(g), rsd["strip_m"], rsd["sweep_m"], rsd["entry_m"], rsd["speed"]))
    d3b_rows.append(["%s|%s|%s|%s" % k, len(g), "%.5f" % rsd["strip_m"], "%.5f" % rsd["sweep_m"],
                     "%.5f" % rsd["entry_m"], "%.5f" % rsd["speed"],
                     "%.5f" % rsd["region_e"], "%.5f" % rsd["region_n"]])

write_csv("D3_parameter_spread.csv", ["parameter", "min", "max", "range", "relative_sd"], d3_rows)
write_csv("D3_within_signature_rsd.csv",
          ["signature", "n", "strip_rsd", "sweep_rsd", "entry_rsd", "speed_rsd",
           "region_east_rsd", "region_north_rsd"], d3b_rows)

print()
print("各签名内的速度取值集合:")
for k in sorted(grouped, key=lambda x: (-len(grouped[x]), x)):
    g = grouped[k]
    c = Counter(x["speed"] for x in g)
    print("  %-30s %s" % (str(k), dict(sorted(c.items()))))
print()
print("entry_side 分布: %s" % dict(Counter(r["side"] for r in recs)))
print("注意: 本 profile 的 variant_speed_factors = [1.0], 故 speed 仅取 speeds_m_s 的 3 个离散值")
