"""V8-18 佯动单段薄 CLI（指令第 8 部分；本项新增）。只调用已有运行器（joint_intent / skeleton_transit），内部显式传
intent="feint"；不另写进程池以外的求解链、预算或重试（turn-gate / cost-check 的诊断进程池只并行独立的门禁/预建任务）。

用法（在 Multi-UAV SimpleGC 目录下，conda llm，先设 OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1）：
    python -B tools/v08/run_feint_v18.py --stage skeleton|quick|full|turn-gate|cost-check|smoke|queries
        --devset <devset_v08.json> --data-root <SwarmData> --cache <缓存目录> --out <不存在的新目录> [--workers N]
        [--smoke-level skeleton|chain]
    python -B tools/v08/run_feint_v18.py --stage rerun ... --keys <full 输出/rerun_keys.json> --compare-to <full 输出>
--workers 缺省 = v08/runner/runtime_defaults.DEFAULT_WORKERS（24）；rerun 固定单进程 1。
turn-gate：裁定 3(b) 的确定性门禁子集上比较 exact、screened、剪枝 + screened 三条路径（两两逐个相同）。
cost-check：裁定 3(c) 先预建前 5 个登记族，按族机数加权外推全部 40 族预建墙钟（24 进程）。
退出码：0 完成且未触发；1 参数/路径错误；2 止损/成本检查点触发；3 未完成；4 三项 P0（保留违规、复跑不一致）；
5 粗筛/剪枝三路对照不一致。
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parents[2]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

STAGES = ("skeleton", "quick", "full", "rerun", "turn-gate", "cost-check", "prewarm", "smoke", "queries")
INTENT = "feint"
PROTOTYPE_KEYS = ((1, 0), (2, 0), (11, 1))         # U C 三个原型键
SMOKE_CHAIN_KEYS = ((1, 0), (1, 1), (2, 0), (11, 0))
EDGE_KEYS = ((17, 1), (17, 4))
COST_LIMIT_S = 45 * 60                              # 裁定 3(c)
COST_FAMILIES = 5
PREWARM_LIMIT_S = 90 * 60                           # 成本检查点裁定 §1：主批预建墙钟上限


def build_parser():
    from v08.runner.runtime_defaults import DEFAULT_WORKERS
    ap = argparse.ArgumentParser(description="V8-18 佯动单段")
    ap.add_argument("--stage", choices=STAGES, required=True)
    ap.add_argument("--devset", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--keys")
    ap.add_argument("--compare-to")
    ap.add_argument("--smoke-level", choices=("skeleton", "chain"), default="skeleton")
    return ap


# ---------------------------------------------------------------- 三路对照门禁（裁定 1、3(b)）

def gate_groups(entries, data_root, cache):
    """前 5 个登记族 draw 0 目标；人数 {1, ⌈N/2⌉, N} 纵列（主对照 15 组，与预置测试 9.2 同一构造）；另补全部人数
    横排与最小步长梯形。返回 [(kind, order, n, formation, step)]。"""
    from v08.scene.context import load_context
    out = []
    for e in sorted(entries, key=lambda x: x["order"])[:5]:
        ctx = load_context(e, data_root=data_root, cache_dir=cache)
        N = len(ctx.family.initial_states)
        for n in (1, (N + 1) // 2, N):
            out.append(("preset", int(e["order"]), n, "column", None))
        out.append(("extra", int(e["order"]), N, "abreast", None))
        out.append(("extra", int(e["order"]), N, "echelon", 3.0))
    return out


def _gate_setup(entry, data_root, cache, n, formation, step):
    from v08.contract.monitoring import GroupSpec
    from v08.contract.single_intent import feint_mission
    from v08.motion.formation import formation_slots
    from v08.sampler.common import sample_common
    from v08.sampler.keys import RngKey
    from v08.scene.context import load_context
    ctx = load_context(entry, data_root=Path(data_root), cache_dir=Path(cache))
    mission = feint_mission(ctx, sample_common(ctx.family, 0))
    g0, task = mission.groups[0], mission.tasks[0]
    ids = sorted(ctx.family.initial_states)
    group = GroupSpec(g0.group_id, tuple(ids[:n]), g0.speed_profile, formation)
    key = RngKey(ctx.family.family_id, 0, "formation", mission=0, group=g0.group_id, segment=0)
    slots = formation_slots(group, ctx.family, key, formation=formation, lateral_step_m=step)
    return ctx, task, slots


def _gate_task(t):
    """一组 × 一格：全部门禁子集候选三路认证（exact、screened、剪枝 + screened）；只返回计数与首个差异。"""
    import time as _t
    from v08.motion import feint_chords as FC
    from v08.motion import feint_turn as FT
    from v08.runner.monitoring import jsonable
    kind, entry, n, formation, step, cell_pos, data_root, cache = t
    g = globals().setdefault("_GCTX", {})
    k = (int(entry["order"]), n, formation, step)
    if k not in g:
        g.clear()
        g[k] = _gate_setup(entry, data_root, cache, n, formation, step)
    ctx, task, slots = g[k]
    t0 = _t.perf_counter()
    cells = FC.gate_cells(ctx, task, slots)
    row = {"kind": kind, "order": int(entry["order"]), "n": n, "formation": formation, "lateral_step_m": step,
           "cell_pos": cell_pos, "cells_in_group": len(cells), "candidates": 0,
           "feasible": {"exact": 0, "screened": 0, "pruned_screened": 0}, "mismatch": {"exact_vs_screened": 0,
                                                                                    "exact_vs_pruned": 0,
                                                                                    "screened_vs_pruned": 0},
           "first_difference": None, "reasons_exact": {}, "screen_stats": {}}
    if cell_pos >= len(cells):
        row["wall_s"] = _t.perf_counter() - t0
        return row
    ti, h = cells[cell_pos]
    row["cell"] = [ti, h]
    for cell, cand in FC.iter_certification_cases(ctx, task, slots):
        if (cell["theta_idx"], cell["h_m"]) != (ti, h):
            continue
        st = {}
        ex = FT.certify_candidate(ctx, task, slots, cell, cand, mode="exact")
        sc = FT.certify_candidate(ctx, task, slots, cell, cand, mode="screened", stats=st)
        pr = FT.certify_candidate(ctx, task, slots, cell, cand, mode="screened", prune=True)
        for kk, v in st.items():
            if kk in ("cover_points", "chords", "exact_chords", "direct_reject"):
                row["screen_stats"][kk] = row["screen_stats"].get(kk, 0) + v
        row["candidates"] += 1
        f = {"exact": bool(ex["feasible"]), "screened": bool(sc["feasible"]), "pruned_screened": bool(pr["feasible"])}
        for name, v in f.items():
            row["feasible"][name] += int(v)
        row["reasons_exact"][str(ex["reason"])] = row["reasons_exact"].get(str(ex["reason"]), 0) + 1
        bad = {"exact_vs_screened": f["exact"] != f["screened"], "exact_vs_pruned": f["exact"] != f["pruned_screened"],
               "screened_vs_pruned": f["screened"] != f["pruned_screened"]}
        for name, v in bad.items():
            row["mismatch"][name] += int(v)
        if any(bad.values()) and row["first_difference"] is None:
            row["first_difference"] = jsonable({"cell": cell, "candidate": cand, "exact": ex, "screened": sc,
                                                "pruned_screened": pr})
    row["wall_s"] = _t.perf_counter() - t0
    return row


def turn_gate(entries, data_root, cache, out, workers):
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor
    from v08.motion.feint_chords import GATE_MAX_CELLS
    from v08.runner.monitoring import write_json
    by = {int(e["order"]): e for e in entries}
    groups = gate_groups(entries, data_root, cache)
    # 派发前单进程预热各族的原始距离场（screened 场、feint base 场、collect_phys），避免多个 worker 并发写同一磁盘缓存
    from v08.motion import feint_turn as FT
    from v08.motion import transit_chords as TC
    for o in sorted({g[1] for g in groups}):
        ctx, task, _ = _gate_setup(by[o], data_root, cache, 1, "column", None)
        FT.screen_field(ctx, FT.turn_context(ctx, task.target_id))
        TC.base_field(ctx, task.target_id, intent="feint")
        TC.collect_phys_grid(ctx, task.target_id, intent="feint")
    tasks = [(kind, by[o], n, f, s, c, str(data_root), str(cache)) for kind, o, n, f, s in groups
             for c in range(GATE_MAX_CELLS)]
    t0 = time.time()
    rows = []
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
        for r in ex.map(_gate_task, tasks, chunksize=1):
            rows.append(r)
            if r["candidates"]:
                print(f"[{len(rows)}/{len(tasks)}] o{r['order']:02d} n{r['n']} {r['formation']} cell{r['cell_pos']} "
                      f"cand={r['candidates']} feas={r['feasible']['exact']} mis={sum(r['mismatch'].values())} "
                      f"{r['wall_s']:.0f}s", flush=True)
    tot = {"candidates": sum(r["candidates"] for r in rows)}
    for k in ("exact", "screened", "pruned_screened"):
        tot["feasible_" + k] = sum(r["feasible"][k] for r in rows)
    for k in ("exact_vs_screened", "exact_vs_pruned", "screened_vs_pruned"):
        tot["mismatch_" + k] = sum(r["mismatch"][k] for r in rows)
    ss = {}
    for r in rows:
        for k, v in r["screen_stats"].items():
            ss[k] = ss.get(k, 0) + v
    per_group = {}
    for r in rows:
        gk = f"{r['kind']}|o{r['order']:02d}|n{r['n']}|{r['formation']}|{r['lateral_step_m']}"
        g = per_group.setdefault(gk, {"cells": 0, "candidates": 0, "feasible_exact": 0, "mismatch": 0,
                                      "cells_with_feasible": 0, "wall_s": 0.0})
        g["cells"] += int(r["candidates"] > 0)
        g["candidates"] += r["candidates"]
        g["feasible_exact"] += r["feasible"]["exact"]
        g["cells_with_feasible"] += int(r["feasible"]["exact"] > 0)
        g["mismatch"] += sum(r["mismatch"].values())
        g["wall_s"] += r["wall_s"]
    first = next((r["first_difference"] for r in rows if r["first_difference"] is not None), None)
    doc = {"rule": "裁定 1/3(b)：exact、screened、剪枝 + screened 在确定性门禁子集上两两逐个相同（差异须为 0）",
           "groups": [list(g) for g in groups], "totals": tot, "screen_stats": ss, "per_group": per_group,
           "all_identical": all(tot["mismatch_" + k] == 0 for k in ("exact_vs_screened", "exact_vs_pruned",
                                                                    "screened_vs_pruned")) and tot["candidates"] > 0,
           "first_difference": first, "wall_s": time.time() - t0, "workers": workers, "rows": rows}
    write_json(out / "turn_gate.json", doc, indent=1)
    print(json.dumps({"totals": tot, "all_identical": doc["all_identical"], "wall_s": doc["wall_s"]},
                     ensure_ascii=False))
    return doc


# ---------------------------------------------------------------- 成本检查点（裁定 3(c)）

def cost_check(entries, data_root, cache, out, workers):
    """前 5 个登记族在 24 进程中各一个预建任务（与生产 prewarm_all 同一函数）；按族机数加权外推 40 族，
    以最长处理时间优先（LPT）在 workers 个进程上排布得外推墙钟；> 45 分钟即触发（退出码 2）。"""
    from v08.runner.joint_intent import prewarm_all
    from v08.runner.monitoring import write_json
    ordered = sorted(entries, key=lambda e: e["order"])
    first = ordered[:COST_FAMILIES]
    t0 = time.time()
    pw = prewarm_all(first, data_root=data_root, cache_dir=cache, workers=workers, intent=INTENT)
    wall = time.time() - t0
    fams = []
    for r in pw["per_family"]:
        e = next(x for x in first if int(x["order"]) == r["order"])
        cells = sum(q.get("n_cells") or 0 for q in r["queries"])
        feas = sum(q.get("feasible") or 0 for q in r["queries"])
        st = {}
        for q in r["queries"]:
            for k, v in (q.get("stats") or {}).items():
                st[k] = st.get(k, 0) + v
        fams.append({"order": r["order"], "family_id": r["family_id"], "vehicle_count": int(e["vehicle_count"]),
                     "wall_s": r["wall_s"], "queries": len(r["queries"]), "cells": cells, "feasible_cells": feas,
                     "empty_fraction": None if not cells else 1.0 - feas / cells,
                     "per_cell_s": None if not cells else r["wall_s"] / cells, "stats": st})
    rate = sum(f["wall_s"] for f in fams) / sum(f["vehicle_count"] for f in fams)
    est = sorted((rate * int(e["vehicle_count"]) for e in ordered), reverse=True)
    loads = [0.0] * workers
    for w in est:
        i = loads.index(min(loads))
        loads[i] += w
    makespan = max(loads)
    st_all = {}
    for f in fams:
        for k, v in f["stats"].items():
            st_all[k] = st_all.get(k, 0) + v
    kp = st_all.get("keypoint_pruned", 0)
    cert = st_all.get("certified", 0)
    doc = {"rule": "裁定 3(c)：前 5 族预建，按族机数加权外推 40 族预建墙钟（24 进程）；> 45 分钟停在检查点",
           "families": fams, "measured_wall_s": wall, "rate_s_per_vehicle": rate,
           "extrapolated_total_cpu_s": sum(est), "extrapolated_wall_s": makespan,
           "extrapolated_wall_lower_bound_s": max(sum(est) / workers, max(est)), "limit_s": COST_LIMIT_S,
           "triggered": bool(makespan > COST_LIMIT_S), "workers": workers,
           "prune": {"keypoint_pruned": kp, "certified": cert,
                     "keypoint_prune_rate": None if (kp + cert) == 0 else kp / (kp + cert), "stats": st_all},
           "prewarm": {k: pw[k] for k in ("families", "wall_s", "queries_total", "queries_written", "query_build_s")}}
    write_json(out / "cost_check.json", doc, indent=1)
    write_json(out / "prewarm.json", pw, indent=1)
    print(json.dumps({k: doc[k] for k in ("measured_wall_s", "extrapolated_wall_s", "limit_s", "triggered")},
                     ensure_ascii=False))
    return doc


# ---------------------------------------------------------------- smoke / 查询

def _load(entries, data_root, cache, order):
    from v08.scene.context import load_context
    e = {int(x["order"]): x for x in entries}[order]
    return e, load_context(e, data_root=data_root, cache_dir=cache)


def smoke_skeleton(entries, data_root, cache, out):
    """U C 三个原型键的单骨架 smoke（单进程、不优化不仿真）。"""
    from v08.runner.monitoring import jsonable, write_json
    from v08.runner.skeleton_transit import run_intent_skeleton_contract
    rows = []
    for o, d in PROTOTYPE_KEYS:
        e, ctx = _load(entries, data_root, cache, o)
        t0 = time.perf_counter()
        rec = run_intent_skeleton_contract(ctx, e, d, intent=INTENT, out_dir=out)
        rec["wall_s"] = time.perf_counter() - t0
        rows.append(jsonable({k: v for k, v in rec.items() if k != "_timing"}))
        print(rec["contract_id"], rec["success"], rec["attempts"], (rec.get("feint_turn") or {}).get("turn"),
              rec.get("curved"), f"{rec['wall_s']:.1f}s", flush=True)
    write_json(out / "records.json", rows, indent=1)
    return rows


def queries(entries, data_root, cache, out):
    """o17_d1/d4 与三个原型键的集合诊断：每个 probe 的格数、可行格数、原因；首个可行格的非空组合。"""
    from v08.contract.single_intent import feint_mission
    from v08.motion import feint_chords as FC
    from v08.motion import feint_turn as FT
    from v08.motion.formation import formation_slots
    from v08.motion.intents.feint import formation_probe_sequence
    from v08.runner.monitoring import jsonable, write_json
    from v08.sampler.common import sample_common
    from v08.sampler.keys import RngKey
    rows = []
    for o, d in EDGE_KEYS + PROTOTYPE_KEYS:
        e, ctx = _load(entries, data_root, cache, o)
        m = feint_mission(ctx, sample_common(ctx.family, d))
        g, task = m.groups[0], m.tasks[0]
        tgt = ctx.facility_by_id[task.target_id]
        row = {"contract_id": f"o{o:02d}_d{d}", "family_id": e["family_id"], "target_id": task.target_id,
               "group_size": len(g.member_ids), "formation_prior": g.formation_prior,
               "lateral_spacing_m": float(ctx.family.lateral_spacing_m),
               "target_geometry_type": tgt.geometry.get("type"), "offsets": tgt.offsets, "probes": []}
        key = RngKey(ctx.family.family_id, d, "shape", mission=0, branch=None, group=g.group_id, segment=0)
        t0 = time.perf_counter()
        seq = formation_probe_sequence(ctx, g, task, key)
        for name, step, offs, sp in seq:
            qid, _ = FC.query_identity(ctx, task.target_id, offs, sp)
            doc = ctx.extra[("feint_chord_sets", task.target_id)][qid]
            row["probes"].append({"formation": name, "lateral_step_m": step, "n_cells": doc["n_cells"],
                                  "feasible_cells": len(doc["cells"]), "reasons": doc["reasons"], "query_id": qid,
                                  "L_m": doc.get("L_m"), "l_star_m": doc.get("l_star_m"),
                                  "witness_kinds": _count([c["witness"]["kind"] for c in doc["cells"]])})
        row["query_s"] = time.perf_counter() - t0
        last = seq[-1] if seq else None
        doc = ctx.extra[("feint_chord_sets", task.target_id)][FC.query_identity(ctx, task.target_id, last[2],
                                                                                 last[3])[0]] if last else None
        if doc and doc["cells"]:
            fkey = RngKey(ctx.family.family_id, d, "formation", mission=0, group=g.group_id, segment=0)
            order = formation_slots(g, ctx.family, fkey).order
            slots = formation_slots(g, ctx.family, fkey, formation=last[0], lateral_step_m=last[1], order=order)
            cell = {k: doc["cells"][0][k] for k in ("theta_idx", "h_m", "x_in", "collect_D_candidates")}
            combos = []
            grids = FT.candidate_grid(ctx, task, slots, cell)
            for (kind, side), cands in grids.items():
                hit = None
                for c in cands:
                    got = FT.certify_candidate(ctx, task, slots, cell, c, mode="screened", prune=True)
                    if got["feasible"]:
                        hit = {k: got["record"][k] for k in ("A_m", "radius_m", "collect_D_compatible", "terminal_x")}
                        break
                combos.append({"kind": kind, "side": side, "grid": len(cands), "first_feasible": hit})
            row["first_cell"] = {"cell": cell, "combos": combos}
        rows.append(jsonable(row))
        print(row["contract_id"], [(p["formation"], p["feasible_cells"], p["n_cells"]) for p in row["probes"]],
              f"{row['query_s']:.0f}s", flush=True)
    write_json(out / "queries.json", rows, indent=1)
    return rows


def _count(xs):
    out = {}
    for x in xs:
        out[str(x)] = out.get(str(x), 0) + 1
    return dict(sorted(out.items()))


# ---------------------------------------------------------------- 主入口

def main(argv=None):
    args = build_parser().parse_args(argv)
    from v08.runner.monitoring import PathRejected, guard_path, load_entries, write_json
    try:
        data_root = Path(args.data_root)
        cache = guard_path(args.cache, label="缓存", data_root=data_root)
        out = guard_path(args.out, label="输出", data_root=data_root, must_not_exist=True)
    except PathRejected as exc:
        print(f"路径被拒绝：{exc}", file=sys.stderr)
        return 1
    if args.stage == "rerun" and not (args.keys and args.compare_to):
        print("rerun 需要 --keys 与 --compare-to", file=sys.stderr)
        return 1
    entries = load_entries(args.devset)
    out.mkdir(parents=True, exist_ok=False)
    if args.stage == "turn-gate":
        doc = turn_gate(entries, data_root, cache, out, args.workers)
        return 0 if doc["all_identical"] else 5
    if args.stage == "cost-check":
        doc = cost_check(entries, data_root, cache, out, args.workers)
        return 2 if doc["triggered"] else 0
    if args.stage == "prewarm":
        # 成本检查点裁定（2026-11-07）：40 族一次性主批预建（与生产同一 prewarm_all），墙钟上限 90 分钟由执行方监视
        from v08.runner.joint_intent import prewarm_all
        t0 = time.time()
        pw = prewarm_all(entries, data_root=data_root, cache_dir=cache, workers=args.workers, intent=INTENT)
        write_json(out / "prewarm.json", pw, indent=1)
        doc = {"wall_s": time.time() - t0, "limit_s": PREWARM_LIMIT_S, "families": pw["families"],
               "queries_total": pw["queries_total"], "queries_written": pw["queries_written"],
               "query_build_s": pw["query_build_s"], "triggered": bool(time.time() - t0 > PREWARM_LIMIT_S)}
        write_json(out / "prewarm_summary.json", doc, indent=1)
        print(json.dumps(doc, ensure_ascii=False))
        return 2 if doc["triggered"] else 0
    if args.stage == "queries":
        queries(entries, data_root, cache, out)
        return 0
    if args.stage == "smoke":
        if args.smoke_level == "skeleton":
            smoke_skeleton(entries, data_root, cache, out)
            return 0
        from v08.runner.joint_intent import run_selected
        s = run_selected(entries, list(SMOKE_CHAIN_KEYS), intent=INTENT, data_root=data_root, cache_dir=cache,
                         out_dir=out, workers=min(args.workers, len(SMOKE_CHAIN_KEYS)), stage="smoke")
        print("佯动四键全链路 smoke：", json.dumps({k: s[k] for k in ("complete", "retained_p0_violations", "errors")},
                                             ensure_ascii=False))
        if s["retained_p0_violations"]:
            return 4
        return 0 if s["complete"] else 3
    if args.stage == "skeleton":
        from v08.runner.skeleton_transit import run_intent_skeleton_batch
        s = run_intent_skeleton_batch(entries, intent=INTENT, data_root=data_root, cache_dir=cache, out_dir=out,
                                      workers=args.workers)
        chk = s["checkpoint"]
        m = chk["metrics"]
        print("佯动骨架检查点（指令 5.2）：", json.dumps(
            {"complete": chk["complete"], "triggered": chk["triggered"], "rate": m.get("success_rate_fraction"),
             "attempts_median": m.get("success_attempts_median"), "shape_audit": m.get("shape_audit_rate"),
             "fallback_diagnostic": chk.get("fallback")}, ensure_ascii=False))
        if not chk["complete"]:
            return 3
        return 2 if chk["triggered"] else 0
    if args.stage == "quick":
        from run_transit_v16 import quick_keys          # 同目录既有脚本（select_quick 协议）
        from v08.runner.joint_intent import run_selected
        from v08.runner.joint_monitoring import contract_id
        sel, meta = quick_keys(entries, data_root, cache)
        write_json(out / "quick_selection.json", {"selection": sel, "keys": [contract_id({"order": o}, d)
                                                                             for o, d in (sel or [])],
                                                  "common_metadata": meta,
                                                  "rule": "joint_monitoring.select_quick（字典序最小可行列表）"}, indent=1)
        if sel is None:
            return 3
        s = run_selected(entries, sel, intent=INTENT, data_root=data_root, cache_dir=cache, out_dir=out,
                         workers=args.workers, stage="quick")
        print("佯动快批检查点（指令第 6 部分）：", json.dumps({"complete": s["complete"], "checkpoint": s["checkpoint"],
                                                   "retained_p0_violations": s["retained_p0_violations"]},
                                                  ensure_ascii=False))
        if s["retained_p0_violations"]:
            return 4
        if not s["complete"]:
            return 3
        return 2 if s["checkpoint"]["triggered"] else 0
    if args.stage == "full":
        from v08.runner.joint_intent import full_stage
        s = full_stage(entries, data_root=data_root, cache_dir=cache, out_dir=out, workers=args.workers, intent=INTENT)
        print("佯动全量检查点（指令 7.1）：", json.dumps({"complete": s["complete"], "checkpoint": s["checkpoint"],
                                                 "frechet_after_pooled": s["frechet_after_pooled"],
                                                 "diversity_complete": s.get("diversity_complete"),
                                                 "retained_p0_violations": s["retained_p0_violations"]},
                                                ensure_ascii=False, default=str))
        if s["retained_p0_violations"]:
            return 4
        if not (s["complete"] and s.get("diversity_complete")):
            return 3
        return 2 if (s["checkpoint"] or {}).get("triggered") else 0
    from v08.runner.joint_intent import rerun_stage
    doc = rerun_stage(entries, data_root=data_root, cache_dir=cache, out_dir=out, keys_path=args.keys,
                      compare_to=args.compare_to, intent=INTENT)
    return 0 if doc["all_equal"] else 4


if __name__ == "__main__":
    sys.exit(main())
