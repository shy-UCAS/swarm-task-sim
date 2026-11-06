"""V8-17 第 5.1 / 6 部分 smoke 核对（只读）：对 smoke 输出的每个合同，核对
1) 终点公式：相邻槽位终点距离 = sqrt([σ(l_i − l_j)]² + (d_i − d_j)²)（纵列 σb、横排 b、梯形 sqrt((σb)² + b_lat²)），
   对骨架 skeleton.json 的成员曲线末点实测；
2) 事件键：member_map_intrusion 含 layer_entry_member_s 三层、terminal_member_s、terminal_x；三层 warning<alert<protected；
3) 一次抽样：每个 attempt 的 shape_draws = 1、lp_calls ∈ {0, 1}；
4) 合同目录 JSON 无计时类键（递归）。
用法：python -B verify_smoke.py <smoke 输出根> <out.json>"""
import json
import math
import sys
from pathlib import Path

TIMER_KEYS = {"seconds", "wall_s", "wall_time", "elapsed_s", "elapsed_seconds", "prepare_s", "solve_s", "check_s",
              "optimization_s", "timing", "stage_timing", "skeleton_detail", "build_seconds", "attempt_wall_s",
              "skeleton_s", "optimize_s", "simulation_s", "verify_s", "lp_s", "chord_set_s", "chord_exact_s",
              "corridor_s", "route_s", "candidate_s", "cache_hits", "cache_misses_computed", "traceback", "tracebacks",
              "pid"}


def keys(v, path, out):
    if isinstance(v, dict):
        for k, x in v.items():
            if k in TIMER_KEYS:
                out.append(f"{path}/{k}")
            keys(x, f"{path}/{k}", out)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            keys(x, f"{path}/{i}", out)
    return out


def main():
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    rows = []
    for d in sorted((root / "contracts").iterdir()):
        res = json.loads((d / "result.json").read_text(encoding="utf-8"))
        timers = []
        for f in sorted(d.rglob("*.json")):
            keys(json.loads(f.read_text(encoding="utf-8")), f.relative_to(d).as_posix(), timers)
        row = {"contract_id": d.name, "success": res.get("success"), "attempts": res.get("attempts"),
               "timer_keys": timers}
        att = res.get("attempt_log") or []
        row["shape_draws"] = [((a.get("intrusion") or {}).get("shape_draws")) for a in att]
        row["lp_calls"] = [((a.get("intrusion") or {}).get("lp_calls")) for a in att]
        sk = d / "skeleton.json"
        if sk.exists():
            plan = json.loads(sk.read_text(encoding="utf-8"))
            w = plan.get("witnesses") or {}
            P = plan.get("proposal") or {}
            form = plan.get("formation") or {}
            sigma = float(w["sigma"])
            order = form["order"]
            offs = form["offsets"]
            ends = {m: plan["arrays"][plan["members"][m]["curve_xy"]["npz"]][-1] for m in order}
            checks = []
            for a, b in zip(order, order[1:]):
                (la, da), (lb, db) = offs[a], offs[b]
                want = math.hypot(sigma * (la - lb), da - db)
                got = math.dist(ends[a], ends[b])
                checks.append({"pair": [a, b], "formula_m": want, "measured_m": got, "abs_err_m": abs(got - want)})
            row["sigma"] = sigma
            row["formation"] = form.get("realized")
            row["spacing_b_m"] = None
            row["adjacent_endpoint_distance"] = checks
            row["max_endpoint_formula_err_m"] = max((c["abs_err_m"] for c in checks), default=0.0)
            mm = w["member_map_intrusion"]["members"]
            ev = []
            for m in order:
                le = mm[m]["layer_entry_member_s"]
                ev.append(bool(le["warning"] < le["alert"] < le["protected"] < mm[m]["terminal_member_s"]))
            row["event_keys_ok"] = all(ev) and all(
                {"layer_entry_member_s", "terminal_member_s", "terminal_x", "entry_member_s"} <= set(mm[m]) for m in order)
            row["terminal"] = w.get("terminal")
            row["terminal_ok"] = all(t["protected_sdf_m"] <= -10.0 and t["contour_sdf_m"] <= 45.0
                                     and t["terminal_x"] <= t["deepest_x"] for t in w["terminal"].values())
            row["nominal_screen_passed"] = {m: v["passed"] for m, v in sorted((w.get("screen") or {}).items())}
            row["curved"] = P.get("curved")
        rows.append(row)
    doc = {"root": str(root.resolve()), "rows": rows,
           "all_timer_free": all(not r["timer_keys"] for r in rows),
           "all_single_draw": all(all(x in (1, None) for x in r["shape_draws"]) for r in rows),
           "all_lp_le_1": all(all(x in (0, 1, None) for x in r["lp_calls"]) for r in rows)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"n": len(rows), "timer_free": doc["all_timer_free"], "single_draw": doc["all_single_draw"],
                      "lp_le_1": doc["all_lp_le_1"],
                      "endpoint_err": [r.get("max_endpoint_formula_err_m") for r in rows],
                      "events": [r.get("event_keys_ok") for r in rows],
                      "terminal": [r.get("terminal_ok") for r in rows]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
