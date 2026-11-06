"""V8-17 突入单段薄 CLI（指令第 8 部分；本项新增）。只调用已有运行器（joint_intent / skeleton_transit），内部显式传
intent="intrusion"；不另写进程池、重试或求解链。

用法（在 Multi-UAV SimpleGC 目录下，conda llm，先设 OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1）：
    python -B tools/v08/run_intrusion_v17.py --stage skeleton|quick|full|chord-gate|smoke|queries --devset <devset_v08.json>
        --data-root <SwarmData> --cache <缓存目录> --out <不存在的新目录> [--workers N] [--smoke-level skeleton|chain]
    python -B tools/v08/run_intrusion_v17.py --stage rerun ... --keys <full 输出/rerun_keys.json> --compare-to <full 输出>
--workers 缺省 = v08/runner/runtime_defaults.DEFAULT_WORKERS（24）；rerun 固定单进程 1；smoke 只运行 U C.3 四键，
不能替代固定快批。
退出码：0 完成且未触发；2 止损检查点触发；3 未完成；4 保留 P0 违规或复跑/门禁字节不一致；1 参数/路径错误；
5 组合加速对照（chord-gate）不一致（加速正确性前提，不冒充保留数据 P0）。
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

STAGES = ("skeleton", "quick", "full", "rerun", "chord-gate", "smoke", "queries")
INTENT = "intrusion"
SMOKE_KEYS = ((1, 0), (1, 1), (2, 0), (11, 0))         # U C.3 四种规模/队形
EDGE_KEYS = ((17, 1), (17, 4))
KNOWN_KEYS = ((34, 3),)


def build_parser():
    from v08.runner.runtime_defaults import DEFAULT_WORKERS
    ap = argparse.ArgumentParser(description="V8-17 突入单段")
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


# ---------------------------------------------------------------- 组合一致性门禁（指令 5.1 / U D.8）

def chord_gate(entries, data_root, cache, out):
    """沿用 V8-16 chord_gate 的前 5 个登记族及 draw 0 目标；人数 {1, ⌈N/2⌉, N}，纵列实际偏移，σ ∈ {1, 0.5, min Σ}，
    共 5×3×3 组；另以横排 σ=1、梯形最小横向步长 σ=min Σ 自加覆盖。逐格比较存在性、原因、D 子集、终点区间端点与
    规范顺序：memo=True（单车道/终点缓存组合）vs memo=False（逐车道直算，不读取车道/终点缓存）。"""
    from v08.contract.monitoring import GroupSpec
    from v08.contract.single_intent import intrusion_mission
    from v08.motion import intrusion_chords as IC
    from v08.motion import intrusion_numeric as IN
    from v08.motion.formation import MIN_LATERAL_STEP_M, formation_slots
    from v08.runner.monitoring import write_json
    from v08.sampler.common import sample_common
    from v08.sampler.keys import RngKey
    from v08.scene.context import load_context
    rows = []
    for e in sorted(entries, key=lambda x: x["order"])[:5]:
        ctx = load_context(e, data_root=data_root, cache_dir=cache)
        m = intrusion_mission(ctx, sample_common(ctx.family, 0))
        g0, task = m.groups[0], m.tasks[0]
        ids = sorted(ctx.family.initial_states)
        b = float(ctx.family.lateral_spacing_m)
        smin = min(IN.sigma_values(b, "column"))
        combos = []
        for n in sorted({1, (len(ids) + 1) // 2, len(ids)}):
            for s in (1.0, 0.5, smin):
                combos.append(("preset", n, "column", None, s))
        combos.append(("extra", len(ids), "abreast", None, 1.0))
        combos.append(("extra", len(ids), "echelon", MIN_LATERAL_STEP_M, smin))
        for kind, n, form, step, s in combos:
            g = GroupSpec(g0.group_id, tuple(ids[:n]), g0.speed_profile, form)
            fk = RngKey(ctx.family.family_id, 0, "formation", mission=0, group=g.group_id, segment=0)
            slots = formation_slots(g, ctx.family, fk, formation=form, lateral_step_m=step)
            offs = [slots.offsets[k] for k in slots.order]
            t0 = time.perf_counter()
            a = IC.assess_formation(ctx, task.target_id, offs, sigmas=(s,), memo=True, detail=True)
            t1 = time.perf_counter()
            d = IC.assess_formation(ctx, task.target_id, offs, sigmas=(s,), memo=False, detail=True)
            t2 = time.perf_counter()
            ja, jd = json.dumps(a["per_cell"]), json.dumps(d["per_cell"])
            same = (ja == jd and json.dumps(a["cells"]) == json.dumps(d["cells"]) and a["reasons"] == d["reasons"]
                    and a["n_cells"] == d["n_cells"])
            first = None
            if not same:
                for x, y in zip(a["per_cell"], d["per_cell"]):
                    if x != y:
                        first = {"combined": x, "direct": y}
                        break
            rows.append({"kind": kind, "order": int(e["order"]), "family_id": e["family_id"], "target": task.target_id,
                         "vehicle_count": len(ids), "n": n, "formation": form, "lateral_step_m": step, "sigma": s,
                         "n_cells": a["n_cells"], "cells_combined": len(a["cells"]), "cells_direct": len(d["cells"]),
                         "reasons": a["reasons"], "identical": bool(same), "first_difference": first,
                         "combined_s": t1 - t0, "direct_s": t2 - t1})
            print({k: rows[-1][k] for k in ("kind", "order", "n", "formation", "sigma", "n_cells", "cells_combined",
                                            "identical")}, f"{t1 - t0:.1f}s/{t2 - t1:.1f}s", flush=True)
    preset = [r for r in rows if r["kind"] == "preset"]
    doc = {"rows": rows, "preset_combos": len(preset), "preset_identical": sum(r["identical"] for r in preset),
           "all_identical": all(r["identical"] for r in rows), "lane_stats": dict(IC.STATS),
           "rule": "指令 5.1：memo=True 与 memo=False 同浮点输入逐格完全相同；不同即保留两路证据、修复组合实现后重过"}
    write_json(out / "chord_gate.json", doc, indent=1)
    return doc


# ---------------------------------------------------------------- smoke / 查询

def _load(entries, data_root, cache, order):
    from v08.scene.context import load_context
    e = {int(x["order"]): x for x in entries}[order]
    return e, load_context(e, data_root=data_root, cache_dir=cache)


def smoke_skeleton(entries, data_root, cache, out):
    """U C.3 四键骨架 smoke（单进程、不优化不仿真）：核对终点公式、事件键、一次抽样、无计时污染。"""
    from v08.runner.monitoring import jsonable, write_json
    from v08.runner.skeleton_transit import run_intent_skeleton_contract
    rows = []
    for o, d in SMOKE_KEYS:
        e, ctx = _load(entries, data_root, cache, o)
        t0 = time.perf_counter()
        rec = run_intent_skeleton_contract(ctx, e, d, intent=INTENT, out_dir=out)
        rec["wall_s"] = time.perf_counter() - t0
        rows.append(jsonable({k: v for k, v in rec.items() if k != "_timing"}))
        print(rec["contract_id"], rec["success"], rec["attempts"], rec.get("sigma"), rec.get("curved"),
              f"{rec['wall_s']:.1f}s", flush=True)
    write_json(out / "records.json", rows, indent=1)
    return rows


def queries(entries, data_root, cache, out):
    """o34_d3 的证书查询与 o17_d1/d4 的集合查询（指令 5.1）；另给四键的单格查询日志（每个 probe 的格数/原因）。"""
    from v08.contract.single_intent import intrusion_mission
    from v08.motion import intrusion_chords as IC
    from v08.motion.intents.intrusion import formation_probe_sequence, infeasibility_certificate
    from v08.runner.monitoring import jsonable, write_json
    from v08.sampler.common import sample_common
    from v08.sampler.keys import RngKey
    rows = []
    for o, d in KNOWN_KEYS + EDGE_KEYS + SMOKE_KEYS:
        e, ctx = _load(entries, data_root, cache, o)
        m = intrusion_mission(ctx, sample_common(ctx.family, d))
        g, task = m.groups[0], m.tasks[0]
        cert = infeasibility_certificate(ctx, g, task)
        tgt = ctx.facility_by_id[task.target_id]
        row = {"contract_id": f"o{o:02d}_d{d}", "family_id": e["family_id"], "target_id": task.target_id,
               "group_size": len(g.member_ids), "formation_prior": g.formation_prior,
               "lateral_spacing_m": float(ctx.family.lateral_spacing_m),
               "target_geometry_type": tgt.geometry.get("type"), "contour": tgt.geometry,
               "protected": tgt.layers["protected"],
               "certificate": None if cert is None else jsonable(cert.witness), "probes": []}
        if cert is None:
            key = RngKey(ctx.family.family_id, d, "shape", mission=0, branch=None, group=g.group_id, segment=0)
            t0 = time.perf_counter()
            seq = formation_probe_sequence(ctx, g, task, key)
            for name, step, offs, sig in seq:
                qid, _ = IC.query_identity(ctx, task.target_id, offs, sig)
                doc = ctx.extra[("intrusion_chord_sets", task.target_id)][qid]
                row["probes"].append({"formation": name, "lateral_step_m": step, "sigmas": list(sig),
                                      "n_cells": doc["n_cells"], "feasible_cells": len(doc["cells"]),
                                      "reasons": doc["reasons"], "query_id": qid,
                                      "sigma_cells": {str(s): sum(any(c["sigma"] == s for c in cell["choices"])
                                                                  for cell in doc["cells"]) for s in sig}})
            row["query_s"] = time.perf_counter() - t0
        rows.append(row)
        print(row["contract_id"], "cert" if cert else [(p["formation"], p["feasible_cells"], p["n_cells"])
                                                         for p in row["probes"]], flush=True)
    write_json(out / "queries.json", rows, indent=1)
    return rows


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
    if args.stage == "chord-gate":
        doc = chord_gate(entries, data_root, cache, out)
        return 0 if doc["all_identical"] else 5
    if args.stage == "queries":
        queries(entries, data_root, cache, out)
        return 0
    if args.stage == "smoke":
        if args.smoke_level == "skeleton":
            smoke_skeleton(entries, data_root, cache, out)
            return 0
        from v08.runner.joint_intent import run_selected
        s = run_selected(entries, list(SMOKE_KEYS), intent=INTENT, data_root=data_root, cache_dir=cache, out_dir=out,
                         workers=min(args.workers, len(SMOKE_KEYS)), stage="smoke")
        print("突入四键全链路 smoke：", json.dumps({k: s[k] for k in ("complete", "retained_p0_violations", "errors")},
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
        print("突入骨架检查点（指令 5.3）：", json.dumps(
            {"complete": chk["complete"], "triggered": chk["triggered"], "rate": m.get("success_rate_fraction"),
             "rate_raw": m.get("success_rate_raw_fraction"), "attempts_median": m.get("success_attempts_median"),
             "shape_audit": m.get("shape_audit_rate_fraction"), "fallback": m.get("fallback")}, ensure_ascii=False))
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
        print("突入快批检查点（指令第 6 部分）：", json.dumps({"complete": s["complete"], "checkpoint": s["checkpoint"],
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
        print("突入全量检查点（指令 7.2）：", json.dumps({"complete": s["complete"], "checkpoint": s["checkpoint"],
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
