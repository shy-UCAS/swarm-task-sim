"""V8-17 第 5 部分只读统计（指令 5.2–5.3 的"另报"各项）。不规划、不写输入目录。
用法：python -B skeleton_stats.py <skeleton 输出根> <out.json>"""
import json
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path


def frac(a, b):
    if not b:
        return None
    f = Fraction(a, b)
    return f"{f.numerator}/{f.denominator}"


def main():
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    rows = json.loads((root / "records.json").read_text(encoding="utf-8"))
    summ = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    pw = json.loads((root / "prewarm.json").read_text(encoding="utf-8"))
    succ = [r for r in rows if r.get("success")]
    logs = [a for r in rows for a in (r.get("attempt_log") or [])]
    doc = {"contracts": len(rows), "successes": len(succ)}
    doc["known_infeasible"] = [{k: r.get(k) for k in ("contract_id", "success", "attempts", "group_size", "target_id",
                                                     "lateral_spacing_m")} | {"failure_code": (r.get("failure") or {}).get("code")}
                               for r in rows if r["contract_id"] == "o34_d3"]
    doc["certificates_outside_list"] = [r["contract_id"] for r in rows if r["contract_id"] != "o34_d3"
                                        and (r.get("failure") or {}).get("code") == "proven_infeasible"]
    edge = []
    for r in rows:
        if r["contract_id"] in ("o17_d1", "o17_d4"):
            st = [s for a in r.get("attempt_log") or [] for s in a.get("formation_steps") or []][:3]
            edge.append({"contract_id": r["contract_id"], "success": r["success"], "attempts": r["attempts"],
                         "group_size": r["group_size"], "first_stages": [a["stage"] for a in r["attempt_log"]][:20],
                         "formation_steps": st, "failure": r.get("failure")})
    doc["edge"] = edge
    doc["prior_to_realized"] = dict(sorted(Counter(f"{(r.get('formation') or {}).get('prior')}->"
                                                   f"{(r.get('formation') or {}).get('realized')}" for r in succ).items()))
    sig = Counter()
    by_form = {}
    for r in succ:
        f = (r.get("formation") or {}).get("realized")
        s = r.get("sigma")
        sig[str(s)] += 1
        by_form.setdefault(f, []).append(s)
    doc["sigma_hist"] = dict(sorted(sig.items(), key=lambda kv: -float(kv[0]) if kv[0] != "None" else 9))
    doc["sigma_lt1_by_formation"] = {f: {"n": len(v), "sigma_lt_1": sum(1 for s in v if s is not None and s < 1.0),
                                         "fraction": frac(sum(1 for s in v if s is not None and s < 1.0), len(v))}
                                     for f, v in sorted(by_form.items())}
    term = [t for r in succ for t in (r.get("terminal") or {}).values()]
    doc["terminal"] = {"members": len(term),
                       "contour_le_45": sum(t["contour_sdf_m"] <= 45.0 for t in term),
                       "protected_le_m10": sum(t["protected_sdf_m"] <= -10.0 for t in term),
                       "not_beyond_deepest": sum(t["terminal_x"] <= t["deepest_x"] for t in term),
                       "negative_contour": sum(t["contour_sdf_m"] < 0.0 for t in term),
                       "contour_min_max": [min((t["contour_sdf_m"] for t in term), default=None),
                                           max((t["contour_sdf_m"] for t in term), default=None)]}
    ed = [d for r in succ for d in (r.get("endpoint_distances_m") or [])]
    doc["endpoint_pair_distance_min_m"] = min(ed) if ed else None
    scr = [v for r in succ for v in (r.get("nominal_screen") or {}).values()]
    doc["nominal_screen_passed_members"] = [sum(1 for v in scr if v.get("passed")), len(scr)]
    doc["shape_draws_per_attempt"] = dict(Counter(str((a.get("intrusion") or {}).get("shape_draws")) for a in logs))
    doc["lp_calls_per_attempt"] = dict(Counter(str((a.get("intrusion") or {}).get("lp_calls")) for a in logs))
    doc["downstream_retreats"] = sum(1 for a in logs for rp in (a.get("repairs") or [])
                                     if isinstance(rp, dict) and rp.get("forced_by") not in (None, "width"))
    doc["retreat_kinds"] = dict(Counter(f"{rp.get('kind')}:{rp.get('forced_by')}" for a in logs
                                        for rp in (a.get("repairs") or []) if isinstance(rp, dict)))
    doc["exceptions"] = sum(1 for a in logs if a["stage"] == "exception")
    doc["errors"] = [r["contract_id"] for r in rows if r.get("error")]
    doc["attempt_stages"] = summ.get("attempt_stages")
    doc["failure_codes"] = dict(Counter(str((r.get("failure") or {}).get("code")) for r in rows if not r.get("success")))
    doc["missing_marks_success"] = [r["contract_id"] for r in succ if r.get("sigma") is None or r.get("terminal") is None
                                    or r.get("curved") is None]
    doc["prewarm"] = {k: pw.get(k) for k in ("families", "wall_s", "queries_total", "queries_written", "query_build_s")}
    fam = sorted(((p["order"], p["wall_s"], len(p["queries"])) for p in pw["per_family"]), key=lambda x: -x[1])
    doc["prewarm_slowest_families"] = fam[:5]
    doc["chord_cache"] = summ.get("chord_cache")
    doc["route_queries"] = summ.get("route_queries")
    doc["timing"] = summ.get("timing")
    doc["wall_s"], doc["dispatch_wall_s"] = summ.get("wall_s"), summ.get("dispatch_wall_s")
    doc["contract_wall_s"] = summ.get("contract_wall_s")
    doc["checkpoint"] = summ.get("checkpoint")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("contracts", "successes", "prior_to_realized", "sigma_lt1_by_formation",
                                          "terminal", "downstream_retreats", "exceptions", "failure_codes",
                                          "shape_draws_per_attempt", "lp_calls_per_attempt", "chord_cache")},
                     ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
