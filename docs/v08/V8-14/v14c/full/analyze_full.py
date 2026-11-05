"""V8-14b 第 7 部分全量结果分析（只读 out/full 产物）。"""
import json, sys
from collections import Counter
from pathlib import Path

out = Path(sys.argv[1])
s = json.loads((out / "summary.json").read_text(encoding="utf-8"))
recs = json.loads((out / "records.json").read_text(encoding="utf-8"))
div = json.loads((out / "diversity" / "records.json").read_text(encoding="utf-8"))
P = print


def q(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    pk = lambda p: xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]
    return {"n": len(xs), "min": round(xs[0], 4), "p10": round(pk(.1), 4), "p50": round(pk(.5), 4),
            "p90": round(pk(.9), 4), "max": round(xs[-1], 4)}


P("complete", s["complete"], "completed", s["completed"], "/", s["expected_count"], "unsent", len(s["unsent"]),
  "incomplete", s["incomplete"], "errors", s["errors"], "wall", round(s["wall_s"]))
P("diversity", s["diversity_completed"], "/", s["diversity_expected"])
chk = s["checkpoint"]
P("checkpoint triggered", chk["triggered"])
m = chk["metrics"]
P("success_rate", m["success_rate"], "post median", m["post_optimization_failures_median"], "undetermined",
  m["attempts_undetermined"], "frechet", m["frechet_pooled_median"])
for k in ("facility_gap", "speed_gap", "group_gap"):
    P(k, json.dumps(m.get(k), ensure_ascii=False))
P("frechet after/before pooled", s["frechet_after_pooled"], s["frechet_before_pooled"])
ends = [e["max_m"] for b in s["frechet_blocks_after"] for e in b.get("endpoint_m", [])]
P("patrol endpoint max distance (after)", q(ends))
P("frechet blocks", [(b["family_id"][-6:], b["success"], b["attempted"], len(b["distances_m"])) for b in s["frechet_blocks_after"]])
D = s["distributions"]
P("deviation max", D["deviation_max_m"], "worst", D["deviation_worst"])
P("final failures", D["final_failures"], "attempt stages", D["attempt_stages"])
P("post failures dist", D["post_optimization_failures"], "success attempts", D["success_attempts_diagnostic"])
P("formation_vs_prior", json.dumps(s["formation_vs_prior"], ensure_ascii=False))
P("lp seconds per attempt", s["lp_seconds_per_attempt"])
P("skeleton bias drawn_vs_kept", json.dumps(s["skeleton_bias"]["drawn_vs_kept"]), s["skeleton_bias"]["counts"])
P("retained p0", D["retained_p0_violations"], "tracking", json.dumps(D["tracking"]))
P("timing", json.dumps(D["timing_s"]))
P("nominal duration over 1800", D["nominal_duration_over_legacy_1800s"])
# 阶段诊断
ph = {k: {"mr": [], "or": [], "ma": [], "oa": [], "na": 0} for k in ("collect_ingress", "patrol", "egress")}
worst = {}
for r in recs:
    for mem, v in (r.get("phase_metrics") or {}).items():
        if not isinstance(v, dict) or "phases" not in v:
            continue
        for k, x in v["phases"].items():
            d = ph[k]
            if x["measured_ratio"] is None:
                d["na"] += 1
            d["mr"].append(x["measured_ratio"]); d["or"].append(x["optimized_ratio"])
            d["ma"].append(x["measured_along_max_m"]); d["oa"].append(x["optimized_along_max_m"])
            for key in ("measured_ratio",):
                if x[key] is not None and (k not in worst or x[key] < worst[k][2]):
                    worst[k] = (r["contract_id"], mem, x[key], x.get("measured_along_worst_t_s"))
for k, d in ph.items():
    P("phase", k, "measured_ratio", q(d["mr"]), "optimized_ratio", q(d["or"]), "measured_along", q(d["ma"]),
      "optimized_along", q(d["oa"]), "N/A", d["na"], "worst ratio", worst.get(k))
o18 = next((r for r in recs if r["contract_id"] == "o18_d0"), None)
if o18:
    P("o18_d0 success", o18["success"], "deviation uav_03", (o18.get("deviation") or {}).get("uav_03"))
    pm = (o18.get("phase_metrics") or {}).get("uav_03")
    P("o18_d0 uav_03 phases", json.dumps(pm, ensure_ascii=False)[:1500])
    P("o18_d0 max deviation by member", {k: round(v["max_m"], 2) for k, v in (o18.get("deviation") or {}).items()})
