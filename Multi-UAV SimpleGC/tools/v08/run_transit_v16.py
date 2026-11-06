"""V8-16 过境单段入口（指令 9.1；本项新增）。

用法（在 Multi-UAV SimpleGC 目录下，conda llm，先设 OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1）：
    python -B tools/v08/run_transit_v16.py --stage skeleton|quick|full --devset <devset_v08.json> --data-root <SwarmData>
        --cache <缓存目录> --out <不存在的新目录> [--workers N]
    python -B tools/v08/run_transit_v16.py --stage rerun --devset ... --data-root ... --cache ... --out <新目录>
        --keys <full 输出/rerun_keys.json> --compare-to <full 输出>        （固定单进程）
    python -B tools/v08/run_transit_v16.py --stage chord-gate ...       （附录裁定 2：组合 vs 逐车道直接重算逐格比对）
--workers 缺省 = v08/runner/runtime_defaults.DEFAULT_WORKERS（24）；rerun 固定 1。
退出码：0 完成且未触发；2 诊断检查点触发；3 未完成；4 保留段 P0 违规或复跑字节不一致；1 参数/路径错误。
"""
import argparse
import json
import sys
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parents[2]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

STAGES = ("skeleton", "quick", "full", "rerun", "chord-gate")


def build_parser():
    from v08.runner.runtime_defaults import DEFAULT_WORKERS
    ap = argparse.ArgumentParser(description="V8-16 过境单段")
    ap.add_argument("--stage", choices=STAGES, required=True)
    ap.add_argument("--devset", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--keys")
    ap.add_argument("--compare-to")
    return ap


def quick_keys(entries, data_root, cache):
    """沿用 joint_monitoring.select_quick 的既有协议（公共抽签元数据，不按过境结果挑选）。"""
    from v08.runner.joint_monitoring import DRAWS, common_metadata, select_quick
    from v08.scene.context import load_context
    meta = []
    for e in entries:
        ctx = load_context(e, data_root=data_root, cache_dir=cache)
        for d in range(DRAWS):
            meta.append(common_metadata(ctx, e, d))
    return select_quick(entries, meta), meta


def chord_gate(entries, data_root, cache, out):
    """附录裁定 2 门禁：5 个目标 × 3 种人数（横排 1、⌈n/2⌉、n 机），单车道缓存组合 vs 逐车道直接重算，逐格比对。"""
    from v08.contract.single_intent import transit_mission
    from v08.contract.monitoring import GroupSpec
    from v08.motion import transit_chords as TC
    from v08.motion.formation import formation_slots
    from v08.runner.monitoring import write_json
    from v08.sampler.common import sample_common
    from v08.sampler.keys import RngKey
    from v08.scene.context import load_context
    rows = []
    for e in sorted(entries, key=lambda x: x["order"])[:5]:
        ctx = load_context(e, data_root=data_root, cache_dir=cache)
        m = transit_mission(ctx, sample_common(ctx.family, 0))
        g0, task = m.groups[0], m.tasks[0]
        ids = sorted(ctx.family.initial_states)
        for n in sorted({1, (len(ids) + 1) // 2, len(ids)}):
            g = GroupSpec(g0.group_id, tuple(ids[:n]), g0.speed_profile, "abreast")
            fk = RngKey(ctx.family.family_id, 0, "formation", mission=0, group=g.group_id, segment=0)
            slots = formation_slots(g, ctx.family, fk, formation="abreast")
            offs = [slots.offsets[k] for k in slots.order]
            t0 = time.perf_counter()
            a = TC.assess_formation(ctx, task.target_id, offs, memo=True)
            t1 = time.perf_counter()
            b = TC.assess_formation(ctx, task.target_id, offs, memo=False)
            t2 = time.perf_counter()
            same = json.dumps(a["cells"]) == json.dumps(b["cells"]) and a["reasons"] == b["reasons"]
            rows.append({"order": int(e["order"]), "target": task.target_id, "n": n, "cells_combined": len(a["cells"]),
                         "cells_direct": len(b["cells"]), "n_cells": a["n_cells"], "identical": bool(same),
                         "combined_s": t1 - t0, "direct_s": t2 - t1})
            print(rows[-1], flush=True)
    doc = {"rows": rows, "all_identical": all(r["identical"] for r in rows),
           "rule": "附录裁定 2：组合检验与逐车道直接重算逐格相同才使用组合；不同即退回直接计算"}
    write_json(out / "chord_gate.json", doc, indent=1)
    return doc


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
    entries = load_entries(args.devset)
    out.mkdir(parents=True, exist_ok=False)
    if args.stage == "skeleton":
        from v08.runner.skeleton_transit import run_transit_skeleton_batch
        s = run_transit_skeleton_batch(entries, data_root=data_root, cache_dir=cache, out_dir=out, workers=args.workers)
        chk = s["checkpoint"]
        m = chk["metrics"]
        print("过境骨架检查点（指令第 5 部分 + 附录裁定 1）：", json.dumps(
            {"complete": chk["complete"], "triggered": chk["triggered"], "successes": m.get("successes"),
             "success_rate": m.get("success_rate_fraction"), "success_attempts_median": m.get("success_attempts_median"),
             "shape_audit": [m.get("shape_audit_failed_attempts"), m.get("skeleton_attempts_total")],
             "fallback": chk["fallback"]}, ensure_ascii=False))
        if not chk["complete"]:
            return 3
        return 2 if chk["triggered"] else 0
    if args.stage == "quick":
        from v08.runner.joint_intent import run_selected
        sel, meta = quick_keys(entries, data_root, cache)
        from v08.runner.joint_monitoring import contract_id
        write_json(out / "quick_selection.json", {"selection": sel, "keys": [contract_id({"order": o}, d)
                                                                             for o, d in (sel or [])],
                                                  "common_metadata": meta,
                                                  "rule": "joint_monitoring.select_quick（字典序最小可行列表）"}, indent=1)
        if sel is None:
            return 3
        s = run_selected(entries, sel, intent="transit", data_root=data_root, cache_dir=cache, out_dir=out,
                         workers=args.workers, stage="quick")
        print("过境快批检查点：", json.dumps({"complete": s["complete"], "checkpoint": s["checkpoint"],
                                         "retained_p0_violations": s["retained_p0_violations"]}, ensure_ascii=False))
        if s["retained_p0_violations"]:
            return 4
        if not s["complete"]:
            return 3
        return 2 if s["checkpoint"]["triggered"] else 0
    if args.stage == "full":
        from v08.runner.joint_intent import full_stage
        s = full_stage(entries, data_root=data_root, cache_dir=cache, out_dir=out, workers=args.workers)
        print("过境全量诊断：", json.dumps({"complete": s["complete"], "checkpoint": s["checkpoint"],
                                         "frechet_after_pooled": s["frechet_after_pooled"],
                                         "retained_p0_violations": s["retained_p0_violations"]}, ensure_ascii=False))
        if s["retained_p0_violations"]:
            return 4
        if not s["complete"]:
            return 3
        return 2 if (s["checkpoint"] or {}).get("triggered") else 0
    if args.stage == "rerun":
        if not (args.keys and args.compare_to):
            print("rerun 需要 --keys 与 --compare-to", file=sys.stderr)
            return 1
        from v08.runner.joint_intent import rerun_stage
        doc = rerun_stage(entries, data_root=data_root, cache_dir=cache, out_dir=out, keys_path=args.keys,
                          compare_to=args.compare_to)
        return 0 if doc["all_equal"] else 4
    doc = chord_gate(entries, data_root, cache, out)
    return 0 if doc["all_identical"] else 4


if __name__ == "__main__":
    sys.exit(main())
