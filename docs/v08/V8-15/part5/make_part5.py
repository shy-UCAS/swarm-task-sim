"""V8-15 第 5 部分汇总：cProfile 四合同 + 行级两合同 → summary.json 与 top25.md（只读外部输出）。
用法：make_part5.py <out/profile> <out/profile_line> <本目录>"""
import hashlib
import json
import sys
from pathlib import Path

prof, line, dst = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sel = json.loads((dst / "selection.json").read_text(encoding="utf-8"))
base = {x["contract_id"]: x for x in sel["final"]}
STAGES = ("orchestration", "skeleton", "optimize", "simulation", "verify")
out = {"cprofile": [], "line": [], "runs": {}}
md = ["# V8-15 第 5 部分：四阶段 cProfile 双 Top25", "",
      "每个合同一个独立进程；同一时刻只有一个阶段 profiler 活动。cumtime 有包含关系，不能逐行相加；"
      "表中 `capture` 是本项为保存 AL 轮次而加在 optimize_segment 外层的只读包装。", ""]
for name in ("runs.json",):
    for root, key in ((prof, "cprofile"), (line, "line")):
        p = root / name
        out["runs"][key] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
for x in sel["final"]:
    cid = x["contract_id"]
    p = prof / cid / "result.json"
    if not p.exists():
        out["cprofile"].append({"contract_id": cid, "status": "缺结果"})
        continue
    r = json.loads(p.read_text(encoding="utf-8"))
    det = r["details"]
    opt = det.get("optimize") or {}
    vg = opt.get("value_grad") or {}
    rounds = []
    for k, d in enumerate(r["al_rounds_per_optimize_call"]):
        rounds.append({"optimize_call": k, "outer_rounds": d.get("outer_rounds"), "nit_total": d.get("nit"),
                       "nfev_total": d.get("nfev"), "success": d.get("success"), "solve_s": d.get("solve_s"),
                       "check_s": d.get("check_s"), "prepare_s": d.get("prepare_s"), "nvar": d.get("nvar"),
                       "rounds": [{kk: rr.get(kk) for kk in ("round", "nit", "nfev", "message", "scipy_success", "rho",
                                                             "value", "max_violation", "hard_passed", "max_abs_grad")}
                                  | {"hard_failure_kinds": sorted({f.get("kind") for f in rr.get("hard_failures") or []})}
                                  for rr in d.get("rounds") or []]})
    lbfgs_calls = sum(v["ncalls"] for k, v in (vg.get("callers") or {}).items() if "_compute_if_needed" in k)
    out["cprofile"].append({
        "contract_id": cid, "why": x["why"], "success": r["success"], "attempts": r["attempts"],
        "baseline_wall_s": x["wall_s"], "baseline_stage_timing": x["stage_timing"],
        "profiled_wall_s": r["profiled_wall_s"], "profile_factor": r["profiled_wall_s"] / x["wall_s"],
        "stage_exclusive_wall_s": r["stage_exclusive_wall_s"], "stage_calls": r["stage_calls"],
        "peak_working_set_gib": (r["memory"].get("peak_working_set_bytes") or 0) / 2 ** 30,
        "bytes_equal_to_baseline": r.get("bytes_equal_to_baseline"),
        "skeleton_detail": det.get("skeleton"), "lp_basis_cache": det.get("lp_basis_cache"),
        "value_grad": {"ncalls_all": vg.get("ncalls"), "ncalls_lbfgs_callback": lbfgs_calls,
                       "ncalls_other": (vg.get("ncalls") or 0) - lbfgs_calls, "mean_cumtime_s": vg.get("mean_cumtime_s"),
                       "cumtime_s": vg.get("cumtime_s"), "callers": vg.get("callers")},
        "nfev_sum_over_rounds": sum(rr["nfev"] or 0 for d in rounds for rr in d["rounds"]),
        "_blocks": opt.get("_blocks"), "optimizer_functions": {k: opt.get(k) for k in (
            "minimize", "_minimize_lbfgsb", "check_physical", "check_monitoring", "prepare_problem", "solve_joint")},
        "al": rounds,
        "prof_sha256": {s: hashlib.sha256((prof / cid / f"{s}.prof").read_bytes()).hexdigest()
                        for s in STAGES + ("merged",) if (prof / cid / f"{s}.prof").exists()}})
    md += [f"## {cid}（{x['why']}；基线 wall {x['wall_s']:.1f} s，剖析 wall {r['profiled_wall_s']:.1f} s）", ""]
    for s in STAGES:
        t = (r["top"] or {}).get(s)
        if not t:
            md += [f"### {s}：无调用", ""]
            continue
        for key in ("cumulative", "tottime"):
            md += [f"### {s} — 按 {key}（互斥墙钟 {r['stage_exclusive_wall_s'][s]:.2f} s）", "",
                   "| # | 函数 | 位置 | ncalls | tottime (s) | cumtime (s) |", "|---|---|---|---|---|---|"]
            for i, row in enumerate(t[key], 1):
                loc = row["file"].replace("\\", "/").split("/Multi-UAV SimpleGC/")[-1].split("site-packages/")[-1]
                md.append(f"| {i} | `{row['function']}` | {loc}:{row['line']} | {row['ncalls']} | "
                          f"{row['tottime_s']:.3f} | {row['cumtime_s']:.3f} |")
            md.append("")
for cid in sel["line_keys"]:
    p = line / cid / "result.json"
    if not p.exists():
        out["line"].append({"contract_id": cid, "status": "缺结果"})
        continue
    r = json.loads(p.read_text(encoding="utf-8"))
    out["line"].append({k: r.get(k) for k in (
        "contract_id", "success", "attempts", "wall_s", "optimize_traced_wall_s", "partial", "stop_reason",
        "line_limit_s", "line_map", "line_drift_vs_fixed", "events", "calls", "scope_total_s", "by_scope_category_s",
        "value_grad_total_s", "value_grad_attributed_s", "attribution_gap_s", "value_grad_category_s",
        "value_grad_share_direct", "value_grad_share_upper_bound", "negative_categories",
        "trace_overhead_ns_per_event", "bytes_equal_to_baseline")} | {"baseline_wall_s": base[cid]["wall_s"]})
(dst / "summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
(dst / "top25.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print(json.dumps([{k: c.get(k) for k in ("contract_id", "baseline_wall_s", "profiled_wall_s", "stage_exclusive_wall_s",
                                         "bytes_equal_to_baseline")} for c in out["cprofile"]], ensure_ascii=False))
