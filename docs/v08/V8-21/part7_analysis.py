"""V8-21 第 7.3 节：七意图配对与完整诊断（只读已保存产物；输出写入全新目录）。

用法（代码工作目录）：python -B ../docs/v08/V8-21/part7_analysis.py <detour_full_dir> <out_dir>
"""
import json
import math
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
SIX = {
    "monitoring": BASE / "_handoff/2026-11-10_V8-22_monitoring_entry/run/full",
    "transit": BASE / "_handoff/2026-11-05_V8-16_transit/run/out/full_transit_r2",
    "intrusion": BASE / "_handoff/2026-11-06_V8-17_intrusion/run/out/full/full_r1",
    "feint": BASE / "_handoff/2026-11-06_V8-18_feint/run/out/full_lazy_r1",
    "close_observation": BASE / "_handoff/2026-11-08_V8-19_close_observation/run/out/full_r1",
    "area_search": BASE / "_handoff/2026-11-09_V8-20_area_search/run/full/area_cost_ruling_r1",
}
COMMON = ("family_id", "order", "draw_index", "facility_count", "vehicle_count", "group_id", "member_ids", "group_size",
          "target_id", "initial_speed_m_s", "formation_prior")
MAIN = [f"o{o:02d}_d{d}" for o in range(1, 41) for d in range(5)]


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def q(vals):
    v = [float(x) for x in vals if x is not None]
    return None if not v else {f"P{p}": float(np.percentile(v, p)) for p in (0, 10, 50, 90, 100)} | {"n": len(v)}


def pairing(detour_dir):
    out, diffs = {}, []
    for cid in MAIN:
        d = read(Path(detour_dir) / "contracts" / cid / "contract.json")
        for intent, root in SIX.items():
            c = read(root / "contracts" / cid / "contract.json")
            bad = [k for k in COMMON if c.get(k) != d.get(k)]
            if bad:
                diffs.append({"contract_id": cid, "intent": intent, "fields": bad})
    out["common_fields"] = list(COMMON)
    out["differences"] = diffs
    out["difference_count"] = len(diffs)
    tr = []
    for cid in MAIN:
        a = read(SIX["transit"] / "contracts" / cid / "result.json")
        b = read(Path(detour_dir) / "contracts" / cid / "result.json")
        tr.append({"contract_id": cid, "transit_success": a["success"], "detour_success": b["success"],
                   "transit_formation": (a.get("formation") or {}).get("realized"),
                   "detour_formation": (b.get("formation") or {}).get("realized")})
    out["detour_transit"] = {"both_success": sum(r["transit_success"] and r["detour_success"] for r in tr),
                             "detour_only": sum(r["detour_success"] and not r["transit_success"] for r in tr),
                             "transit_only": sum(r["transit_success"] and not r["detour_success"] for r in tr),
                             "same_realized_formation_given_both": sum(
                                 r["transit_formation"] == r["detour_formation"] for r in tr
                                 if r["transit_success"] and r["detour_success"]), "rows": tr}
    return out


def min_separation(folder, con, res):
    tracks = {}
    for m in con["member_ids"]:
        tau = np.load(folder / "tracks" / m / "tau_us.npy")
        p = np.load(folder / "tracks" / m / "p.npy")
        keep = tau >= int(res["release_us"][m])
        tracks[m] = (tau[keep], p[keep, :2])
    if len(tracks) < 2:
        return None
    best = None
    for a, b in combinations(sorted(tracks), 2):
        ta, pa = tracks[a]
        tb, pb = tracks[b]
        ct, ia, ib = np.intersect1d(ta, tb, return_indices=True)
        if not len(ct):
            continue
        d = np.hypot(*(pa[ia] - pb[ib]).T)
        k = int(np.argmin(d))
        if best is None or d[k] < best["min_m"]:
            best = {"min_m": float(d[k]), "pair": [a, b], "frame_us": int(ct[k])}
    if best is None:
        return None
    mem = res["detour"]["members"]

    def phase(m, t):
        e, x = mem[m]["first_near_entry_us"], mem[m]["last_near_exit_us"]
        if e is None or t < e:
            return "ingress"
        if x is None or t < x:
            return "near_band"
        return "withdrawal"
    pa, pb = (phase(m, best["frame_us"]) for m in best["pair"])
    best["phase"] = pa if pa == pb else f"{pa}/{pb}"
    return best


def diagnostics(detour_dir):
    root = Path(detour_dir)
    cand = None
    rows, fails_attempt, fails_first, sep, durations = [], {}, {}, [], []
    for cid in MAIN:
        folder = root / "contracts" / cid
        con, res = read(folder / "contract.json"), read(folder / "result.json")
        first = "none"
        for a in res["attempt_log"]:
            if a["ok"]:
                continue
            stage = a.get("skeleton_stage") if a["stage"] == "skeleton" else a["stage"]
            sub = ((a.get("witness") or {}).get("subreason") if a["stage"] == "skeleton" else None)
            key = f"{stage}:{sub}" if sub else stage
            fails_attempt[key] = fails_attempt.get(key, 0) + 1
            if first == "none":
                first = key
        fails_first[first] = fails_first.get(first, 0) + 1
        if not res["success"]:
            rows.append({"contract_id": cid, "success": False, "failure": res["failure"]["code"]})
            continue
        cand = res["detour"]["candidate"]
        mem = res["detour"]["members"]
        theta, upper = cand["min_sweep_deg"], cand["max_sweep_deg_exclusive"]
        lower = min(m["max_span_deg"] for m in mem.values())
        top = max(max([r["span_deg"] for r in m["all_runs"]] or [0.0]) for m in mem.values())
        d = res["detour"]["draw"]
        f = res["detour"]["formation"]
        rows.append({"contract_id": cid, "success": True, "group_size": con["group_size"],
                     "target_min_sweep_deg": lower, "lower_margin_deg": lower - theta, "upper_margin_deg": upper - top,
                     "min_target_warning_m": min(m["min_target_warning_distance_m"] for m in mem.values()),
                     "entry_counts": sorted({m["near_entry_count"] for m in mem.values()}),
                     "exit_counts": sorted({m["near_exit_count"] for m in mem.values()}),
                     "ends_in_band": any(m["ends_in_band"] for m in mem.values()),
                     "prior": f["prior"], "realized": f["realized"], "retreated": f["retreated"],
                     "sigma": d["sigma"], "Sigma_deg": d["sigma_deg"], "beta_in_deg": d["beta_in_deg"],
                     "beta_out_deg": d["beta_out_deg"], "contribution_deg": d["entry_exit_contribution_deg"],
                     "other_G_f": res["detour"]["other_facility_sweep_deg"]})
        s = min_separation(folder, con, res)
        if s is not None:
            sep.append({"contract_id": cid, **s})
        for m, ph in (res.get("phase_durations") or {}).items():
            durations.append({"contract_id": cid, "member": m, **{k: ph[k] for k in ph}})
    ok = [r for r in rows if r["success"]]
    others = [v for r in ok for v in r["other_G_f"].values()]
    phases = {}
    for s in sep:
        phases[s["phase"]] = phases.get(s["phase"], 0) + 1
    return {"candidate": cand, "contracts": len(rows), "successes": len(ok),
            "target_min_sweep_deg": q(r["target_min_sweep_deg"] for r in ok),
            "lower_margin_deg": q(r["lower_margin_deg"] for r in ok), "upper_margin_deg": q(r["upper_margin_deg"] for r in ok),
            "min_target_warning_m": q(r["min_target_warning_m"] for r in ok),
            "entry_count_values": sorted({c for r in ok for c in r["entry_counts"]}),
            "exit_count_values": sorted({c for r in ok for c in r["exit_counts"]}),
            "contracts_ending_in_band": sum(r["ends_in_band"] for r in ok),
            "other_G_f_deg": q(others),
            "durations": {k: q(d[k] for d in durations) for k in ("ingress_s", "near_band_s", "withdrawal_s",
                                                                  "near_band_line_s", "near_band_fillet_s",
                                                                  "near_band_arc_s", "closure_residual_s")},
            "min_separation_m": q(s["min_m"] for s in sep), "min_separation_phase": phases,
            "min_separation_rows": sep,
            "failure_table_attempts": dict(sorted(fails_attempt.items())),
            "failure_table_first_per_contract": dict(sorted(fails_first.items())),
            "sigma_counts": {str(k): sum(r["sigma"] == k for r in ok) for k in (-1, 1)},
            "Sigma_deg": q(r["Sigma_deg"] for r in ok), "beta_in_deg": q(r["beta_in_deg"] for r in ok),
            "beta_out_deg": q(r["beta_out_deg"] for r in ok), "contribution_deg": q(r["contribution_deg"] for r in ok),
            "formation": {f"{p}->{r_}": sum(1 for r in ok if r["prior"] == p and r["realized"] == r_)
                          for p in ("abreast", "column", "echelon", "loose")
                          for r_ in ("abreast", "echelon", "column")},
            "rows": rows}


def main():
    full, out = Path(sys.argv[1]), Path(sys.argv[2])
    assert not out.exists()
    out.mkdir(parents=True)
    pr = pairing(full)
    dg = diagnostics(full)
    for name, doc in (("pairing.json", pr), ("diagnostics.json", dg)):
        with (out / name).open("w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"pairing_differences": pr["difference_count"], "detour_transit": {k: v for k, v in pr["detour_transit"].items() if k != "rows"},
                      "successes": dg["successes"], "lower_margin": dg["lower_margin_deg"], "upper_margin": dg["upper_margin_deg"],
                      "min_target_warning_m": dg["min_target_warning_m"], "other_G_f": dg["other_G_f_deg"],
                      "min_sep_phase": dg["min_separation_phase"], "first_fail": dg["failure_table_first_per_contract"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
