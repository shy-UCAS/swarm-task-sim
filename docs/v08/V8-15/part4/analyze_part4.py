"""V8-15 第 4 部分：三档进程数结果 → 逐合同耗时比、吞吐量、内存、P0-3、选定值与全量预测。
用法：analyze_part4.py <运行根 out 目录> <本目录>。只读三档输出。"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "Multi-UAV SimpleGC" / "tools" / "v08"))
from v15_metrics import choose_workers   # noqa: E402

OUT, DST = Path(sys.argv[1]), Path(sys.argv[2])
TIERS = (8, 16, 24)
FULL_CPU_S = 28273.0   # U C.3：全量 200 + 多样性 100 分阶段 perf_counter 墙钟之和（原报告称 CPU）
EFF = 0.9              # U D.3.6
sel = json.loads((DST / "selection.json").read_text(encoding="utf-8"))
keys = [f"o{o:02d}_d{d}" for o, d in sel["keys"]]
data = {}
for w in TIERS:
    d = OUT / f"workers_{w}"
    if not (d / "summary.json").exists():
        data[w] = None
        continue
    s = json.loads((d / "summary.json").read_text(encoding="utf-8"))
    rows = {r["contract_id"]: r for r in json.loads((d / "records.json").read_text(encoding="utf-8"))}
    comps = {c["contract_id"]: c for c in json.loads((d / "comparisons.json").read_text(encoding="utf-8"))}
    data[w] = {"summary": s, "rows": rows, "comps": comps}
paired, table = [], {}
for w in TIERS:
    if data[w] is None or data[8] is None:
        table[w] = {"workers": w, "status": "未运行或缺数据"}
        continue
    rs, ok = [], True
    for k in keys:
        a, b = data[8]["rows"].get(k), data[w]["rows"].get(k)
        if a is None or b is None or a.get("wall_s") is None or b.get("wall_s") is None:
            ok = False
            continue
        rs.append(b["wall_s"] / a["wall_s"])
    s = data[w]["summary"]
    comps = data[w]["comps"]
    p03 = (len(comps) == len(keys) and all(comps[k]["bytes_equal"] for k in keys if k in comps)
           and set(comps) == set(keys))
    complete = ok and len(rs) == len(keys) and not s["missing"] and not s["errors"] and not s["incomplete"]
    infl = float(np.median(rs)) if rs else None
    table[w] = {"workers": w, "complete_pairs": len(rs), "complete": complete,
                "inflation_median": infl if complete else None,
                "inflation_p90": float(np.quantile(rs, 0.9, method="linear")) if rs else None,
                "throughput": (w / infl) if (complete and infl) else None,
                "peak_memory_fraction": (s["system_memory"] or {}).get("peak_fraction"),
                "memory_samples": (s["system_memory"] or {}).get("samples"),
                "worker_peak_max_gib": (s["worker_peak_max_bytes"] or 0) / 2 ** 30,
                "workers_observed": len(s["worker_peak_working_set_bytes"]),
                "p0_3_ok": p03, "bytes_equal": sum(1 for k in keys if comps.get(k, {}).get("bytes_equal")),
                "dispatch_wall_s": s["dispatch_wall_s"], "wall_with_prewarm_s": s["wall_with_prewarm_s"],
                "prewarm_s": s["prewarm_s"], "contract_busy_s": s["contract_busy_s"],
                "parallel_efficiency": s["parallel_efficiency"],
                "cache_write_during_workers": s["cache_write_during_workers"]}
for k in keys:
    row = {"contract_id": k}
    for w in TIERS:
        r = (data[w] or {}).get("rows", {}).get(k) if data[w] else None
        row[f"wall_{w}"] = None if r is None else r.get("wall_s")
        row[f"bytes_equal_{w}"] = None if not data[w] else data[w]["comps"].get(k, {}).get("bytes_equal")
        if w != 8 and r is not None and row.get("wall_8"):
            row[f"ratio_{w}"] = r["wall_s"] / row["wall_8"]
    paired.append(row)
meas = [{"workers": w, "inflation_median": t["inflation_median"], "peak_memory_fraction": t["peak_memory_fraction"],
         "p0_3_ok": t["p0_3_ok"]} for w, t in table.items() if t.get("complete") is not None]
choice = choose_workers(meas)
eligible = [m for m in meas if m["p0_3_ok"] and m["inflation_median"] is not None]
doc = {"selected": choice["selected"],
       "measurements": [{"workers": m["workers"], "inflation_median": m["inflation_median"],
                         "peak_memory_fraction": m["peak_memory_fraction"]} for m in eligible],
       "selection_path": str((DST / "selection.json").resolve()), "basis": choice}
(DST / "worker_choice.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
pred = None
if choice["selected"] is not None:
    W = choice["selected"]
    I = table[W]["inflation_median"]
    pred = {"W": W, "I_W": I, "T_estimate_s": FULL_CPU_S * I / (W * EFF),
            "formula": "28273 × I_W / (W × 0.9)", "note": "预测，不据此跑全量；40 个中等耗时合同的膨胀比不证明长尾同比"}
(DST / "part4_table.json").write_text(json.dumps({"tiers": table, "full_prediction": pred,
                                                   "all_tier_predictions": {w: FULL_CPU_S * t["inflation_median"] / (w * EFF)
                                                                            for w, t in table.items()
                                                                            if t.get("inflation_median")}},
                                                  ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
with open(DST / "paired_wall.csv", "w", encoding="utf-8", newline="") as fh:
    w_ = csv.DictWriter(fh, fieldnames=list(paired[0].keys()) + [c for c in ("ratio_16", "ratio_24")
                                                                 if c not in paired[0]])
    w_.writeheader()
    for r in paired:
        w_.writerow(r)
print(json.dumps({"tiers": {w: {k: t.get(k) for k in ("inflation_median", "inflation_p90", "throughput",
                                                       "peak_memory_fraction", "p0_3_ok", "dispatch_wall_s")}
                            for w, t in table.items()}, "selected": choice["selected"], "pred": pred},
                 ensure_ascii=False, indent=1))
