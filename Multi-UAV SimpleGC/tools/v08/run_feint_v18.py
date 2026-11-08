"""V8-18 佯动单段薄 CLI（指令第 8 部分；本项新增）。只调用已有运行器（joint_intent / skeleton_transit），内部显式传
intent="feint"；不另写进程池以外的求解链、预算或重试（turn-gate 的诊断进程池只并行独立门禁任务）。

用法（在 Multi-UAV SimpleGC 目录下，conda llm，先设 OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1）：
    python -B tools/v08/run_feint_v18.py --stage skeleton|quick|full|turn-gate|smoke|queries
        --devset <devset_v08.json> --data-root <SwarmData> --cache <缓存目录> --out <不存在的新目录> [--workers N]
        [--smoke-level skeleton|chain]
    python -B tools/v08/run_feint_v18.py --stage rerun ... --keys <full 输出/rerun_keys.json> --compare-to <full 输出>
--workers 缺省 = v08/runner/runtime_defaults.DEFAULT_WORKERS（24）；rerun 固定单进程 1。
turn-gate：裁定 3(b) 的确定性门禁子集上比较 exact、screened、剪枝 + screened 三条路径（两两逐个相同）。
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

STAGES = ("skeleton", "quick", "full", "rerun", "turn-gate", "smoke", "queries")
INTENT = "feint"
PROTOTYPE_KEYS = ((1, 0), (2, 0), (11, 1))         # U C 三个原型键
SMOKE_CHAIN_KEYS = ((1, 0), (1, 1), (2, 0), (11, 0))
EDGE_KEYS = ((17, 1), (17, 4))


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
    ap.add_argument("--contract-keys", help="仅 smoke/queries：逗号分隔业务键（默认仍为登记键）")
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


# ---------------------------------------------------------------- smoke / 查询

def _load(entries, data_root, cache, order):
    from v08.scene.context import load_context
    e = {int(x["order"]): x for x in entries}[order]
    return e, load_context(e, data_root=data_root, cache_dir=cache)


def smoke_skeleton(entries, data_root, cache, out, keys=PROTOTYPE_KEYS):
    """U C 三个原型键的单骨架 smoke（单进程、不优化不仿真）。"""
    from v08.runner.monitoring import jsonable, write_json
    from v08.runner.skeleton_transit import run_intent_skeleton_contract
    rows = []
    for o, d in keys:
        e, ctx = _load(entries, data_root, cache, o)
        t0 = time.perf_counter()
        rec = run_intent_skeleton_contract(ctx, e, d, intent=INTENT, out_dir=out)
        rec["wall_s"] = time.perf_counter() - t0
        rows.append(jsonable({k: v for k, v in rec.items() if k != "_timing"}))
        write_json(out / "records.json", rows, indent=1)
        print(rec["contract_id"], rec["success"], rec["attempts"], (rec.get("feint_turn") or {}).get("turn"),
              rec.get("curved"), f"{rec['wall_s']:.1f}s", flush=True)
    write_json(out / "records.json", rows, indent=1)
    return rows


def queries(entries, data_root, cache, out, keys=EDGE_KEYS):
    """与生产相同的 shape 排列/按需判空；逐 probe 报走格数、首个非空格位置和结果。"""
    from v08.contract.single_intent import feint_mission
    from v08.motion import feint_chords as FC
    from v08.motion import feint_turn as FT
    from v08.motion.intents.feint import select_formation
    from v08.runner.monitoring import jsonable, write_json
    from v08.sampler.common import sample_common
    from v08.sampler.keys import RngKey, rng_for
    rows = []
    for o, d in keys:
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
        telemetry = []
        selected = select_formation(ctx, g, task, key, rng_for(key), row["probes"], telemetry)
        row["probe_telemetry"] = telemetry
        row["query_s"] = time.perf_counter() - t0
        if selected is not None:
            slots, cell = selected["slots"], selected["selection"]["cell"]
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
            row["selected_cell"] = {"cell": cell, "combos": combos}
        row["success"] = selected is not None
        row["query_s"] = time.perf_counter() - t0
        rows.append(jsonable(row))
        write_json(out / "queries.json", rows, indent=1)
        print(row["contract_id"], [(p["formation"], p["cells_examined"], p["nonempty_position"], p["candidate_cells"])
                                    for p in row["probes"]],
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
    if args.stage == "queries":
        keys = _parse_keys(args.contract_keys) if args.contract_keys else EDGE_KEYS
        queries(entries, data_root, cache, out, keys)
        return 0
    if args.stage == "smoke":
        if args.smoke_level == "skeleton":
            keys = _parse_keys(args.contract_keys) if args.contract_keys else PROTOTYPE_KEYS
            smoke_skeleton(entries, data_root, cache, out, keys)
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


def _parse_keys(text):
    import re
    keys = []
    for value in text.split(","):
        match = re.fullmatch(r"o(\d{2})_d(\d+)", value.strip())
        if match is None:
            raise ValueError(f"无效合同键：{value!r}")
        keys.append(tuple(map(int, match.groups())))
    return keys


if __name__ == "__main__":
    sys.exit(main())
