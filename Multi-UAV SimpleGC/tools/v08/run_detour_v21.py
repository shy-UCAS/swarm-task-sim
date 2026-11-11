"""V8-21 迂回单段 CLI（指令第 8 节）：每个 stage 显式 intent="detour"，沿 V20 参数与原调度。

  --stage prewarm   只建 detour 新几何的原始距离场并登记人数（单族单进程；不预建任何形状/路径组合）
  --stage smoke     第 3 部分最大查询与真实诊断键（单进程；冷/热墙钟、内存）
  --stage skeleton  只骨架 200（无优化/仿真；1800 s 硬上限即检查点）
  --stage quick     固定 20 快批全链
  --stage full      主批 200 + 多样性 100（一次派发）
  --stage rerun     --keys --compare-to，1 进程逐字节复跑
quick/full 之后对保存产物做独立磁盘复核（disk_verification.json）。
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parents[2]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))
QUICK_KEYS = tuple((o, d) for o in (*range(1, 10), 11) for d in (0, 1))
SMOKE_KEYS = ((17, 1), (28, 2))


def build_parser():
    from v08.runner.runtime_defaults import DEFAULT_WORKERS
    ap = argparse.ArgumentParser(description="V8-21 迂回单段（只验证构造）")
    ap.add_argument("--stage", required=True, choices=("smoke", "prewarm", "skeleton", "quick", "full", "rerun"))
    for key in ("devset", "data-root", "cache", "out"):
        ap.add_argument("--" + key, required=True)
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--keys")
    ap.add_argument("--compare-to")
    ap.add_argument("--prewarm-from", help="detour prewarm.json（只含原始距离场与人数）")
    ap.add_argument("--contract-keys", help="smoke：额外登记键 oNN_dN,…")
    return ap


def status_code(summary):
    if summary.get("retained_p0_violations"):
        return 4
    if not summary.get("complete", True) or not summary.get("diversity_complete", True):
        return 3
    if (summary.get("checkpoint") or {}).get("triggered"):
        return 2
    return 0


def smoke(entries, *, data_root, cache_dir, out, extra_keys):
    """最大查询：登记 200 合同中实际第 0 组人数最大的键（并列按 order/draw）；其目标上最长可用弧；冷/热两次。"""
    import tracemalloc
    from v08.contract.monitoring import initial_states
    from v08.contract.single_intent import detour_mission
    from v08.motion.intents import detour as DT
    from v08.runner.monitoring import jsonable, write_json
    from v08.sampler.common import sample_common
    from v08.sampler.keys import RngKey
    from v08.scene.context import load_context
    by = {int(e["order"]): e for e in entries}
    meta = []
    for e in sorted(entries, key=lambda x: x["order"]):
        ctx = load_context(e, data_root=data_root, cache_dir=cache_dir)
        for d in range(5):
            m = detour_mission(ctx, sample_common(ctx.family, d))
            meta.append({"order": int(e["order"]), "draw": d, "group_size": len(m.groups[0].member_ids),
                         "target_id": m.tasks[0].target_id, "map_side_m": float(e["map_side_m"])})
    big = max(meta, key=lambda r: (r["group_size"], -r["order"], -r["draw"]))
    keys = [(big["order"], big["draw"])] + [k for k in SMOKE_KEYS] + list(extra_keys)
    rows = []
    for o, d in keys:
        e = by[o]
        for phase in ("cold", "hot"):
            tracemalloc.start()
            t0 = time.perf_counter()
            ctx = load_context(e, data_root=data_root, cache_dir=cache_dir) if phase == "cold" or rows[-1]["order"] != o else ctx
            mission = detour_mission(ctx, sample_common(ctx.family, d))
            g, task = mission.groups[0], mission.tasks[0]
            st = initial_states(ctx.family, g.member_ids)
            atts = []
            for a in range(20):
                k = RngKey(ctx.family.family_id, d, "shape", mission=0, branch=None, group=g.group_id, segment=0, attempt=a)
                plan = DT.propose_and_build(ctx, g, task, st, k)
                tm = DT.last_attempt_timing()
                f = plan.failure
                atts.append({"attempt": a, "ok": f is None,
                             "stage": None if f is None else (f.witness or {}).get("stage"),
                             "subreason": None if f is None else (f.witness or {}).get("subreason"),
                             "timing": {kk: v for kk, v in tm.items() if isinstance(v, float)},
                             "draw": jsonable((plan.proposal or {}).get("draw") if f is None else (f.witness or {}).get("draw")),
                             "formation_steps": jsonable((plan.witnesses or {}).get("formation_steps") if f is None
                                                          else (f.witness or {}).get("formation_steps"))})
                if f is None:
                    break
            cur, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            rows.append({"order": o, "draw": d, "phase": phase, "group_size": len(g.member_ids),
                         "target_id": task.target_id, "wall_s": time.perf_counter() - t0, "peak_traced_mb": peak / 2 ** 20,
                         "success": bool(atts and atts[-1]["ok"]), "winning_attempt": len(atts) if atts[-1]["ok"] else None,
                         "attempts": atts, "cold_build_s": ctx.timings.get("cold_s")})
            print(json.dumps({k: rows[-1][k] for k in ("order", "draw", "phase", "group_size", "wall_s", "success",
                                                       "winning_attempt")}), flush=True)
    doc = {"stage": "smoke", "intent": "detour", "largest_query": big, "keys": keys, "rows": rows,
           "group_size_distribution": meta, "complete": True}
    write_json(out / "smoke.json", doc, indent=1)
    return doc


def main(argv=None):
    args = build_parser().parse_args(argv)
    from v08.runner import detour_report as DR
    from v08.runner import joint_intent as JI
    from v08.runner.monitoring import PathRejected, guard_path, load_entries, write_json
    try:
        data = Path(args.data_root)
        cache = guard_path(args.cache, label="缓存", data_root=data)
        out = guard_path(args.out, label="输出", data_root=data, must_not_exist=True)
        if args.workers < 1:
            raise ValueError("positive workers required")
        entries = load_entries(args.devset)
        pw = None if args.prewarm_from is None else json.loads(Path(args.prewarm_from).read_text(encoding="utf-8"))
        if pw is not None and (pw.get("intent") != "detour" or not pw.get("complete")
                               or {(int(r["order"]), r["family_id"]) for r in pw["per_family"]}
                               != {(int(e["order"]), e["family_id"]) for e in entries}):
            raise ValueError("detour prewarm identity/checkpoint mismatch")
        if args.stage == "prewarm":
            out.mkdir(parents=True, exist_ok=False)
            pw = DR.prewarm_all(entries, data_root=data, cache_dir=cache, workers=args.workers, out_dir=out)
            summary = {"stage": "prewarm", "intent": "detour", "complete": pw["complete"], "workers": args.workers,
                       "wall_s": pw["wall_s"]}
            write_json(out / "summary.json", summary, indent=1)
            print(json.dumps(summary), flush=True)
            return status_code(summary)
        if args.stage == "smoke":
            if args.workers != 1:
                raise ValueError("smoke must use one process")
            extra = []
            if args.contract_keys:
                ms = [re.fullmatch(r"o(\d+)_d(\d+)", x.strip()) for x in args.contract_keys.split(",")]
                if not all(ms):
                    raise ValueError("invalid smoke keys")
                extra = [(int(m[1]), int(m[2])) for m in ms]
            out.mkdir(parents=True, exist_ok=False)
            doc = smoke(entries, data_root=data, cache_dir=cache, out=out, extra_keys=extra)
            return 0 if doc["complete"] else 3
        if args.stage == "rerun":
            if not args.keys or not args.compare_to:
                raise ValueError("rerun requires --keys and --compare-to")
            out.mkdir(parents=True, exist_ok=False)
            summary = JI.rerun_stage(entries, data_root=data, cache_dir=cache, out_dir=out, keys_path=args.keys,
                                     compare_to=args.compare_to, intent="detour")
            return 0 if summary["all_equal"] else 4
        if pw is None:
            raise ValueError("skeleton/quick/full require --prewarm-from（预建与正式计时分开）")
        if args.stage == "skeleton":
            sizes = pw["group_size"]
            summary = DR.run_skeleton_batch(entries, data_root=data, cache_dir=cache, out_dir=out, workers=args.workers,
                                            sizes=sizes)
            summary["complete"] = summary["checkpoint"]["complete"]
        else:
            out.mkdir(parents=True, exist_ok=False)
            if args.stage == "quick":
                write_json(out / "selection.json", {"keys": QUICK_KEYS, "rule": "registered fixed20; no exclusions"},
                           indent=1)
                summary = JI.run_selected(entries, QUICK_KEYS, intent="detour", data_root=data, cache_dir=cache,
                                          out_dir=out, workers=args.workers, stage="quick", prewarm_doc=pw)
                summary["complete"] = bool(summary["complete"] and (summary.get("checkpoint") or {}).get("complete"))
            else:
                summary = JI.full_stage(entries, data_root=data, cache_dir=cache, out_dir=out, workers=args.workers,
                                        intent="detour", prewarm_doc=pw)
        code = status_code(summary)
        if args.stage in ("quick", "full"):
            cand = PROJ / "configs" / "v08" / "criteria_detour_candidate.json"
            ver = {"main": DR.verify_saved_outputs(out, entries, data, cache, cand)}
            if args.stage == "full":
                ver["diversity"] = DR.verify_saved_outputs(out / "diversity", entries, data, cache, cand)
            write_json(out / "disk_verification.json", ver, indent=1)
            if any(v["p0_violations"] for v in ver.values()):
                code = 4
        print(json.dumps({"stage": args.stage, "complete": summary.get("complete"),
                          "checkpoint": summary.get("checkpoint"), "exit_code": code}, default=str), flush=True)
        return code
    except (PathRejected, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
