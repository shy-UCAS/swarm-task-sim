"""Archive actual formal skeleton evidence; never rerun or select contracts."""
import collections
import shutil
from evidence_utils import *

out = DOC / "part5_cost_ruling"
assert not out.exists()
pwroot = ROOT / "prewarm/area_cost_ruling_r1"
bone = ROOT / "skeleton/area_cost_ruling_r1"
pw = read(pwroot / "prewarm.json")
summary = read(bone / "summary.json")
rows = read(bone / "records.json")
changes = audit()
assert not changes, changes
assert pw["complete"] and pw["wall_s"] <= 2700.
assert len(rows) == 200 and len({r["contract_id"] for r in rows}) == 200
from v08.runner.area_search_serialization import assert_contract_payload
geometry = []
attempts = []
queries = {}
audit_entered = audit_failed = 0
for row in rows:
    cid = row["contract_id"]
    attempts.extend({"contract_id": cid, **a} for a in row.get("attempt_log", []))
    for p in (bone / "contracts" / cid).glob("*.json"):
        assert_contract_payload(read(p))
    telemetry = read(bone / "telemetry" / (cid + ".json"))
    for t in telemetry["attempts"]:
        audit_entered += bool(t.get("shape_audit_entered"))
        audit_failed += bool(t.get("shape_audit_failed"))
        for q in t.get("entry_queries", []):
            key = q["chord_query_id"], q["sector_query_id"]
            fact = {k: q[k] for k in ("original_cells", "filtered_cells", "entry_filtered_ratio")}
            if key in queries:
                assert queries[key]["fact"] == fact, (cid, key)
                queries[key]["uses"] += 1
            else:
                queries[key] = {"chord_query_id": key[0], "sector_query_id": key[1], "fact": fact, "uses": 1}
    if row["success"]:
        plan = read(bone / "contracts" / cid / "skeleton.json")
        p = plan["proposal"]
        w = plan["witnesses"]
        geometry.append({"contract_id": cid, "group_size": row["group_size"],
            "group_bin": "1-4" if row["group_size"] <= 4 else "5-8" if row["group_size"] <= 8 else "9-12",
            "formation": plan["formation"]["realized"],
            **{k: p[k] for k in ("beta_deg", "span_deg", "c", "K", "inner_offset_m")},
            "area_m2": w["survey"]["area_m2"], "strip_lengths_m": w["area_geometry"]["strip_lengths_m"]})


def distribution(items):
    return {**{k: quantiles(r[k] for r in items) for k in
        ("beta_deg", "span_deg", "c", "K", "inner_offset_m", "area_m2")},
        "strip_lengths_m": quantiles(x for r in items for x in r["strip_lengths_m"]),
        "c_counts": dict(sorted(collections.Counter(str(r["c"]) for r in items).items())),
        "span_counts": dict(sorted(collections.Counter(str(r["span_deg"]) for r in items).items()))}

entry = [a for a in attempts if a["stage"] == "area_search_entry"]
failed = [a for a in attempts if not a["ok"]]
depths = [float(d) for a in attempts for d in a.get("split_depths_m", {}).values()]
winning_depths = [float(d) for r in rows if r["success"] for d in r["attempt_log"][-1].get("split_depths_m", {}).values()]
stats = {
    "complete_contracts": len(rows), "success_contracts": sum(r["success"] for r in rows),
    "completed_attempts": len(attempts), "failed_attempts": len(failed),
    "area_search_entry_attempts": len(entry), "area_search_entry_attempt_rate": len(entry) / len(attempts) if attempts else None,
    "area_search_entry_contracts": len({a["contract_id"] for a in entry}),
    "area_search_entry_contract_rate": len({a["contract_id"] for a in entry}) / 200,
    "entry_queries": list(queries.values()), "entry_query_count": len(queries),
    "entry_filtered_ratio": quantiles(q["fact"]["entry_filtered_ratio"] for q in queries.values()
                                      if q["fact"]["entry_filtered_ratio"] is not None),
    "empty_original_queries_na": sum(q["fact"]["original_cells"] == 0 for q in queries.values()),
    "shape_audit_entered_candidates": audit_entered, "shape_audit_failed_candidates": audit_failed,
    "shape_audit_failure_rate": audit_failed / audit_entered if audit_entered else None,
    "split_depths_all_observed_members_m": quantiles(depths), "split_depths_winning_members_m": quantiles(winning_depths),
    "split_depth_rejected_attempts": sum(bool(a.get("split_depth_rejected")) for a in attempts),
    "failed_attempt_primary_stage": dict(collections.Counter(a["stage"] for a in failed)),
    "failed_attempt_constraints": dict(collections.Counter(str((a.get("witness") or {}).get("constraint")) for a in failed)),
    "all": distribution(geometry),
    "by_group_bin": {key: distribution([r for r in geometry if r["group_bin"] == key]) for key in ("1-4", "5-8", "9-12")},
    "by_formation": {key: distribution([r for r in geometry if r["formation"] == key]) for key in sorted({r["formation"] for r in geometry})},
    "by_group_bin_and_formation": {key: distribution([r for r in geometry if r["group_bin"] + "/" + r["formation"] == key])
        for key in sorted({r["group_bin"] + "/" + r["formation"] for r in geometry})},
    "geometry_rows": geometry, "excluded_from_rate": [],
    "bone_screen_failed_diagnostic_only": summary["checkpoint"]["diagnostics"]["bone_nominal_screen_failed_contracts"],
    "bone_shared_coverage_failed_contracts": sum(r["success"] and not r["bone_nominal_screen"]["group_conditions"]["shared_coverage"] for r in rows),
    "bone_member_condition_failed_members": dict(collections.Counter(k for r in rows if r["success"]
        for conditions in r["bone_nominal_screen"]["member_conditions"].values() for k, value in conditions.items() if not value)),
    "selected_draws_all_attempts": [{"contract_id": a["contract_id"], "attempt": a["attempt"], "ok": a["ok"], "draw": a["draw"]} for a in attempts],
    "distribution_population": "successful winning skeletons; all selected/failed attempt draws retained separately; unavailable failed geometry is NA",
}
sector_timings = [{"order": r["order"], **q} for r in pw["rows"] for q in r["sector_queries"]]
stats["prewarm_query_worker_seconds_not_wall"] = {
    "chord_sum_s": sum(q["seconds"] for r in pw["rows"] for q in r["queries"]),
    "sector_sum_s": sum(q["seconds"] for q in sector_timings),
    "sector_query_distribution_s": quantiles(q["seconds"] for q in sector_timings),
    "sector_by_actual_n": {str(n): quantiles(q["seconds"] for q in sector_timings if q["members"] == n)
                           for n in sorted({q["members"] for q in sector_timings})},
    "slowest_sector_queries": sorted(sector_timings, key=lambda q: -q["seconds"])[:10]}
out.mkdir()
dump(out / "distributions.json", stats)
dump(out / "checkpoint.json", {"part": 5, "prewarm": {k: pw[k] for k in
    ("complete", "wall_s", "hard_stop", "wall_limit_s", "chord_queries", "sector_queries", "scope")},
    "skeleton": summary, "audit_changes": changes, "contract_exclusions": [],
    "runtime_reestimate": read(ROOT / "smoke/prewarm_runtime_max_r1/result.json")})
for source in (pwroot / "prewarm.json", pwroot / "summary.json", bone / "summary.json", bone / "records.json"):
    name = ("prewarm_" if source.parent == pwroot else "skeleton_") + source.name
    shutil.copyfile(source, out / name)
dump(out / "evidence_index.json", index(pwroot) + index(bone) + index(ROOT / "smoke/prewarm_runtime_max_r1"))
for name in ("evidence_utils.py", "precheck_formal.py", "run_formal_stage.py", "finish_part5.py"):
    shutil.copyfile(TASK / name, out / name)
shutil.copyfile(ROOT / "precheck_skeleton_cost_ruling_r1.json", out / "precheck.json")
passed = summary["checkpoint"]["passed"]
p = DOC / "acceptance.json"
a = read(p)
a["part5_checkpoint"] = str(out / "checkpoint.json")
a["status"] = "part5_passed_quick_pending" if passed else "part5_failed_dependent_quick_full_not_run"
dump(p, a)
with (DOC / "REPORT.md").open("a", encoding="utf-8", newline="\n") as f:
    f.write("\n\n## 第 5 部分：合并预建与只骨架 200——" + ("通过" if passed else "检查点未过，停止依赖的快批和全量") + "\n\n")
    f.write(f"合并预建墙钟 {pw['wall_s']:.6f} s，40 场景族、200 个实际第 0 组人数，弦查询 {pw['chord_queries']}、扇区表 {pw['sector_queries']}；只含原字段、弦集合和扇区表，不预计算全路线/优化。45 分钟上限未触发。原 8 分钟估计偏低，长尾来自完整预建实测；中途按最大 12 机×完整 90° 角格重新实测冷查询 10.262529 s，指定外推 64.568412 s≤1800 s。该查询与正在预建并行，不能冒充隔离测量或全预建墙钟。\n\n")
    f.write(f"只骨架正式派发墙钟 {summary['dispatch_wall_s']:.6f} s（不含预建），完成 {len(rows)}/200，成功 {stats['success_contracts']}/200；检查点 {json.dumps(summary['checkpoint'], ensure_ascii=False)}。所有普通失败与原 20 次预算均保留，无剔除，骨架名义表不拒绝几何候选。\n\n")
    f.write(f"切入深度全部已观察成员分布 {json.dumps(stats['split_depths_all_observed_members_m'], ensure_ascii=False)}；成功获胜成员分布 {json.dumps(stats['split_depths_winning_members_m'], ensure_ascii=False)}。不足 10 m 普通失败 {stats['split_depth_rejected_attempts']} 次，占全部失败 {len(failed)} 次；多数标志为 {summary['checkpoint']['diagnostics']['split_depth_majority_of_failures']}，按裁定保留供审查，不修改规则。\n\n")
    f.write(f"entry 失败 {len(entry)}/{len(attempts)} 已完成尝试，涉及 {stats['area_search_entry_contracts']}/200 合同；唯一形状查询 {len(queries)}，原集合空计 N/A {stats['empty_original_queries_na']} 条。精确形状复核失败 {audit_failed}/{audit_entered}，只作诊断。名义覆盖/互斥表失败合同 {stats['bone_screen_failed_diagnostic_only']}，仍只作骨架诊断。三种分母独立，未套用旧过境回退或 5% 止损。\n\n")
    f.write(f"骨架共享覆盖诊断失败 {stats['bone_shared_coverage_failed_contracts']} 合同，逐项成员失败另列。成功获胜骨架的完整 β/φ/c/K/面积/最小 inner 偏移/逐条长度分布、按人数档与队形交叉分布、全部已选尝试摘要、逐查询筛除率、所有切入深度和原始产物 SHA 索引见 part5_cost_ruling/；失败且未形成的几何为 N/A。冻结/owner/输入/预置/配置及门禁后源码散列差异 0；24 进程预建与骨架均已前后通知，后台资源监控继续运行。\n")
with (DOC / "RUNNING.md").open("a", encoding="utf-8", newline="\n") as f:
    f.write(f"\n第 5 部分完成：预建 {pw['wall_s']:.6f} s，骨架 {summary['dispatch_wall_s']:.6f} s，检查点 passed={passed}；正式输出见 acceptance.part5_checkpoint，使用同一 prewarm.json 分隔两项计时。\n")
print(json.dumps({"part": 5, "passed": passed, "prewarm_wall_s": pw["wall_s"],
                  "skeleton_wall_s": summary["dispatch_wall_s"], "success": stats["success_contracts"],
                  "depths": stats["split_depths_winning_members_m"], "shallow_rejections": stats["split_depth_rejected_attempts"]}, ensure_ascii=False), flush=True)
