"""V8-17 第 6 部分只读统计：名单、止损指标、逐合同 optimization_s、子原因、队形/σ、实测进入事件、终端减速诊断
（附录裁定 1：优化制动开始所在圈层与到保护边界的有符号距离，P2，无门槛）、缓存与计时。
用法：python -B quick_stats.py <quick 输出根> <manifest.json> <out.json>"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np


def qd(xs):
    xs = sorted(float(x) for x in xs if x is not None)
    if not xs:
        return None
    q = np.quantile(xs, [0.0, 0.1, 0.5, 0.9, 1.0])
    return {"n": len(xs), "min": float(q[0]), "p10": float(q[1]), "median": float(q[2]), "p90": float(q[3]),
            "max": float(q[4])}


def main():
    root, man, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    rows = json.loads((root / "records.json").read_text(encoding="utf-8"))
    summ = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    keys = json.loads(man.read_text(encoding="utf-8"))["keys"]["quick20"]
    doc = {"keys_equal_manifest": sorted(r["contract_id"] for r in rows) == sorted(keys),
           "checkpoint": summ["checkpoint"], "complete": summ["complete"],
           "retained_p0_violations": summ["retained_p0_violations"], "wall_s": summ["wall_s"],
           "dispatch_wall_s": summ["dispatch_wall_s"], "prewarm_wall_s": summ["prewarm_wall_s"],
           "chord_cache": summ["chord_cache"], "stage_cpu_s": summ["stage_cpu_s"]}
    doc["per_contract"] = [{k: r.get(k) for k in ("contract_id", "success", "attempts", "group_size", "formation_prior",
                                                  "post_optimization_failures", "optimization_s", "wall_s")}
                           | {"realized": (r.get("formation") or {}).get("realized"),
                              "sigma": (r.get("topology") or {}).get("sigma"),
                              "curved": (r.get("topology") or {}).get("curved")} for r in rows]
    doc["optimization_s"] = qd(r["optimization_s"] for r in rows)
    doc["optimization_s_nonzero_contracts"] = sum(1 for r in rows if r["optimization_s"] > 0)
    fails = [a for r in rows for a in r.get("attempt_log") or [] if not a["ok"]]
    doc["failed_attempts"] = len(fails)
    doc["failed_stage"] = dict(Counter(a["stage"] for a in fails))
    doc["semantic_kinds"] = dict(Counter(f["kind"] for a in fails
                                         for f in ((a.get("optimize") or {}).get("semantic_failures") or [])))
    br_layer, br_signed, nom_dur = Counter(), [], []
    for r in rows:
        for m, v in (r.get("phase_metrics") or {}).items():
            td = (v or {}).get("terminal_deceleration") if isinstance(v, dict) else None
            if not td:
                continue
            o = td.get("optimized")
            if o:
                br_layer[str(o.get("layer"))] += 1
                br_signed.append(o.get("protected_signed_m"))
            if td.get("nominal"):
                nom_dur.append(td["nominal"]["duration_s"])
    doc["optimized_brake_start_layer"] = dict(br_layer)
    doc["optimized_brake_start_protected_signed_m"] = qd(br_signed)
    doc["nominal_terminal_decel_duration_s"] = qd(nom_dur)
    pdur = [v for r in rows for v in (r.get("phase_durations") or {}).values() if isinstance(v, dict)]
    doc["phase_durations"] = {k: qd(v[k] for v in pdur) for k in ("intrusion_ingress_s", "intrusion_inside_s",
                                                                    "travel_s", "release_delay_s")}
    doc["closure_residual_abs_max_s"] = max((abs(v["closure_residual_s"]) for v in pdur), default=None)
    ph = {}
    for r in rows:
        for v in (r.get("phase_metrics") or {}).values():
            for name, rec in ((v or {}).get("phases") or {}).items():
                ph.setdefault(name, []).append(rec)
    doc["phase_speed"] = {n: {k: qd(x.get(k) for x in recs) for k in ("reference_min_m_s", "optimized_ratio",
                                                                      "measured_ratio", "optimized_along_max_m",
                                                                      "measured_along_max_m")}
                          for n, recs in sorted(ph.items())}
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("keys_equal_manifest", "complete", "optimization_s", "failed_attempts",
                                          "optimized_brake_start_layer", "optimized_brake_start_protected_signed_m",
                                          "phase_durations", "closure_residual_abs_max_s", "chord_cache", "wall_s",
                                          "prewarm_wall_s", "dispatch_wall_s")}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
