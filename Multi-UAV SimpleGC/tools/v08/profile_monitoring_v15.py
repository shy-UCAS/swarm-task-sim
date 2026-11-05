"""V8-15 第 5 部分测量包装（指令 5.1–5.2，附录裁定 3）：单进程、真实 run_contract 的完整链路剖析。

两种运行，互不叠加（附录裁定 3）：
- cprofile：四个合同，每个合同一个独立子进程；只开 cProfile，不加行级跟踪。四个阶段作用域
  （骨架 plan_attempt；优化 optimize_segment；仿真 run_tracking_group；最终核验 stitch/verify_segments/
  visible_track/check_validity）各一个可累计 cProfile.Profile，其余流程与落盘记 orchestration。进入阶段时停用当前
  profiler、启用该阶段 profiler，退出后恢复（同一时刻只有一个 profiler 活动）。
- line：两个中位数合同，sys.settrace 只在进入 optimize_segment 时安装、finally 卸载；只对 Prepared._blocks 与
  Prepared.value_grad 两个 code 对象产生行事件；单合同超过基线 wall_s × 6 或总计超过 40 分钟即停止行级计时，
  保存已采集部分并标"部分采样"。

只从本入口安装探针，结束 finally 恢复全部函数绑定与 profile/trace 钩子；生产入口不导入本模块。本节不提出任何提速方案。

用法（Multi-UAV SimpleGC 目录，conda llm）：
    python -B tools/v08/profile_monitoring_v15.py --select-to <part5/selection.json> --baseline <full_v14c>
    python -B tools/v08/profile_monitoring_v15.py --mode cprofile|line --selection <selection.json> --baseline ...
        --devset ... --data-root ... --cache ... --out <不存在的新目录>
"""
import argparse
import cProfile
import inspect
import io
import json
import math
import os
import pstats
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")
STAGES = ("skeleton", "optimize", "simulation", "verify")
SCOPES = {   # (模块, 属性) → 阶段
    ("v08.motion.plan", "plan_attempt"): "skeleton",
    ("v08.motion.optimize", "optimize_segment"): "optimize",
    ("v08.sim.tracking_batch", "run_tracking_group"): "simulation",
    ("v08.sim.stitch", "stitch"): "verify",
    ("v08.criteria.segment", "verify_segments"): "verify",
    ("v08.criteria.validity", "visible_track"): "verify",
    ("v08.criteria.validity", "check_validity"): "verify",
}
PROFILE_FACTOR = 2.0          # 附录裁定 3：cProfile 放大按 2 倍估计
PROFILE_BUDGET_S = 90 * 60.0  # 附录裁定 3
LINE_FACTOR = 6.0             # 附录裁定 3
LINE_TOTAL_S = 40 * 60.0      # 附录裁定 3
TOP = 25                      # U D.4

# 固定提交 2dbb2a4 行号（指令 5.2）；运行时按语句文本锚点重定位并报告漂移
FIXED_BLOCKS = {"shared_end": 648, "dynamics": (649, 715), "geometry": (716, 726), "separation": (727, 742)}
FIXED_VG = {"blocks_call": 779, "al": (782, 792)}


# ---------------------------------------------------------------- 选样（5.1 + 裁定 3）

def _bk(r):
    return (int(r["order"]), int(r["draw_index"]))


def select(baseline, path):
    import numpy as np
    rows = json.loads((Path(baseline) / "records.json").read_text(encoding="utf-8"))
    st = lambda r, k: float((r.get("stage_timing") or {}).get(k) or 0.0)
    chosen, why = [], {}
    a = sorted(rows, key=lambda r: (-st(r, "skeleton_s"), _bk(r)))[0]
    chosen.append(a)
    why[a["contract_id"]] = "skeleton_s 最大"
    b = next(r for r in sorted(rows, key=lambda r: (-st(r, "optimize_s"), _bk(r))) if r not in chosen)
    chosen.append(b)
    why[b["contract_id"]] = "optimize_s 最大（未选键）"
    med = float(np.median([float(r["wall_s"]) for r in rows]))
    for r in sorted(rows, key=lambda r: (abs(float(r["wall_s"]) - med), _bk(r))):
        if len(chosen) >= 4:
            break
        if r not in chosen:
            chosen.append(r)
            why[r["contract_id"]] = f"|wall_s − 中位数 {med:.3f}| 最小"
    est = sum(float(r["wall_s"]) for r in chosen) * PROFILE_FACTOR
    doc = {"median_wall_s": med, "initial": [_row(r, why[r["contract_id"]]) for r in chosen],
           "estimate_s": est, "budget_s": PROFILE_BUDGET_S, "replaced": False}
    if est > PROFILE_BUDGET_S:
        k = int(math.floor(0.9 * (len(rows) - 1)))
        mids = chosen[2:]
        sk = [r for r in sorted(rows, key=lambda r: (st(r, "skeleton_s"), _bk(r))) if r not in mids][k]
        op = [r for r in sorted(rows, key=lambda r: (st(r, "optimize_s"), _bk(r))) if r not in mids and r is not sk][k]
        new = [sk, op] + list(mids)
        doc["replaced"] = True
        doc["replacement_rule"] = f"按 skeleton_s、optimize_s 升序第 floor(0.9×(n−1)) = {k} 位（并列按业务键）"
        why[sk["contract_id"]] = "skeleton_s p90 位置（替换）"
        why[op["contract_id"]] = "optimize_s p90 位置（替换）"
        chosen = new
        doc["estimate_after_s"] = sum(float(r["wall_s"]) for r in chosen) * PROFILE_FACTOR
    doc["final"] = [_row(r, why[r["contract_id"]]) for r in chosen]
    doc["line_keys"] = [x["contract_id"] for x in doc["final"][2:]]
    doc["most_expensive_by_baseline"] = max(doc["final"], key=lambda x: x["wall_s"])["contract_id"]
    Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return doc


def _row(r, why):
    return {"contract_id": r["contract_id"], "order": int(r["order"]), "draw_index": int(r["draw_index"]),
            "success": r.get("success"), "wall_s": float(r["wall_s"]), "stage_timing": r.get("stage_timing"),
            "attempts": r.get("attempts"), "why": why}


# ---------------------------------------------------------------- cProfile 作用域

class ScopedProfiles:
    """每阶段一个可累计 Profile；栈式切换，同一时刻只有一个 profiler 活动。阶段墙钟按互斥口径累计。"""

    def __init__(self):
        self.prof = {s: cProfile.Profile() for s in ("orchestration",) + STAGES}
        self.excl = defaultdict(float)
        self.calls = defaultdict(int)
        self.stack = []
        self.originals = []

    def _wrap(self, stage, fn):
        me = self

        def wrapped(*a, **k):
            prev = me.stack[-1] if me.stack else None
            if prev is not None:
                me.prof[prev[0]].disable()
                prev[2] += time.perf_counter() - prev[1]
            fr = [stage, time.perf_counter(), 0.0]
            me.stack.append(fr)
            me.calls[stage] += 1
            me.prof[stage].enable()
            try:
                return fn(*a, **k)
            finally:
                me.prof[stage].disable()
                fr[2] += time.perf_counter() - fr[1]
                me.excl[stage] += fr[2]
                me.stack.pop()
                if prev is not None:
                    prev[1] = time.perf_counter()
                    me.prof[prev[0]].enable()
        wrapped.__wrapped__ = fn
        return wrapped

    def install(self):
        import importlib
        for (mod, attr), stage in SCOPES.items():
            m = importlib.import_module(mod)
            orig = getattr(m, attr)
            self.originals.append((m, attr, orig))
            setattr(m, attr, self._wrap(stage, orig))
        self.stack.append(["orchestration", time.perf_counter(), 0.0])
        self.prof["orchestration"].enable()

    def uninstall(self):
        fr = self.stack.pop() if self.stack else None
        self.prof["orchestration"].disable()
        if fr is not None:
            fr[2] += time.perf_counter() - fr[1]
            self.excl["orchestration"] += fr[2]
        for m, attr, orig in reversed(self.originals):
            setattr(m, attr, orig)
        self.originals.clear()


def _top(stats, key, n=TOP):
    s = io.StringIO()
    ps = pstats.Stats(stats, stream=s)
    ps.sort_stats(key).print_stats(n)
    rows = []
    for func, (cc, nc, tt, ct, callers) in sorted(ps.stats.items(), key=lambda kv: -(kv[1][3] if key == "cumulative"
                                                                                       else kv[1][2]))[:n]:
        rows.append({"file": func[0], "line": func[1], "function": func[2], "ncalls": nc, "primitive_calls": cc,
                     "tottime_s": tt, "cumtime_s": ct})
    return rows


def _find(ps, file_part, name):
    out = []
    for func, (cc, nc, tt, ct, callers) in ps.stats.items():
        if func[2] == name and file_part in func[0].replace("\\", "/"):
            out.append((func, (cc, nc, tt, ct, callers)))
    return out


def detail_skeleton(ps):
    """骨架细项（指令 5.2）：按固定源码定位；LP 构造独占 = shape_lp 累计 − 其调用的 linprog 累计（调用树实际上下文）。"""
    def one(file_part, name):
        got = _find(ps, file_part, name)
        if not got:
            return None
        (f, (cc, nc, tt, ct, callers)) = got[0]
        return {"path": f"{f[0]}:{f[1]}", "function": name, "ncalls": nc, "tottime_s": tt, "cumtime_s": ct}
    out = {"sample_joint_turn": one("v08/motion/monitoring_turn.py", "sample_joint_turn"),
           "lp_feasible_pairs": one("v08/motion/monitoring_band.py", "lp_feasible_pairs"),
           "_arc_feasible": one("v08/motion/monitoring_band.py", "_arc_feasible"),
           "shape_lp": one("v08/motion/monitoring_band.py", "shape_lp"),
           "linprog": one("scipy/optimize/_linprog.py", "linprog"),
           "BandGeometry.__init__": one("v08/motion/monitoring_band.py", "__init__"),
           "radial_margins": one("v08/motion/monitoring_band.py", "radial_margins"),
           "_lp_basis": one("v08/motion/monitoring_band.py", "_lp_basis")}
    for name in ("clearance_values", "chord_sdf_range", "signed_distance", "polyline_clearance"):
        out["scene.exact." + name] = one("v08/scene/exact.py", name)
    for name in ("build_distance_field", "certified_cell_mask"):
        out["scene.field." + name] = one("v08/scene/field.py", name)
    lin = _find(ps, "scipy/optimize/_linprog.py", "linprog")
    shp = _find(ps, "v08/motion/monitoring_band.py", "shape_lp")
    if lin and shp:
        shape_func = shp[0][0]
        callers = lin[0][1][4]
        from_shape = callers.get(shape_func)
        ct_from = from_shape[3] if from_shape else 0.0
        out["lp_construct_exclusive_s"] = shp[0][1][3] - ct_from
        out["linprog_cumtime_from_shape_lp_s"] = ct_from
    return out


def detail_optimize(ps):
    got = _find(ps, "v08/motion/optimize.py", "value_grad")
    blocks = _find(ps, "v08/motion/optimize.py", "_blocks")
    out = {}
    if got:
        f, (cc, nc, tt, ct, callers) = got[0]
        out["value_grad"] = {"ncalls": nc, "tottime_s": tt, "cumtime_s": ct, "mean_cumtime_s": ct / nc if nc else None,
                             "callers": {f"{k[0]}:{k[1]}:{k[2]}": {"ncalls": v[1], "cumtime_s": v[3]}
                                         for k, v in callers.items()}}
    if blocks:
        f, (cc, nc, tt, ct, callers) = blocks[0]
        out["_blocks"] = {"ncalls": nc, "tottime_s": tt, "cumtime_s": ct,
                          "callers": {k[2]: {"ncalls": v[1], "cumtime_s": v[3]} for k, v in callers.items()}}
    for name in ("minimize", "_minimize_lbfgsb"):
        g = _find(ps, "scipy/optimize", name)
        if g:
            out[name] = {"ncalls": g[0][1][1], "cumtime_s": g[0][1][3]}
    for name in ("check_physical", "check_monitoring", "prepare_problem", "solve_joint"):
        g = [x for x in ps.stats.items() if x[0][2] == name]
        if g:
            out[name] = {"ncalls": g[0][1][1], "cumtime_s": g[0][1][3], "path": f"{g[0][0][0]}:{g[0][0][1]}"}
    return out


# ---------------------------------------------------------------- 行级计时（裁定 3：只在 optimize_segment 内）

def _anchor(lines, start, text):
    for i, l in enumerate(lines):
        if l.strip().startswith(text):
            return start + i
    raise LookupError(text)


def line_map():
    """按语句文本锚点生成行号→类别表，并与固定提交行号比较。"""
    from v08.motion.optimize import Prepared
    bl, b0 = inspect.getsourcelines(Prepared._blocks)
    vl, v0 = inspect.getsourcelines(Prepared.value_grad)
    a_dyn = _anchor(bl, b0, "s = np.hypot(V[:, 0], V[:, 1])")
    a_geo = _anchor(bl, b0, "# 几何")
    a_sep = _anchor(bl, b0, "Pf.append(m.Bf @ C + m.p0)")
    a_ret = _anchor(bl, b0, "return out")
    a_call = _anchor(vl, v0, "blocks = self._blocks(Cs, True)")
    a_al0 = _anchor(vl, v0, "lam = self.mult.get(k)")
    a_al1 = _anchor(vl, v0, "bp(rho * act)")
    got = {"blocks_def": b0, "dynamics": (a_dyn, a_geo - 1), "geometry": (a_geo, a_sep - 1),
           "separation": (a_sep, a_ret - 1), "value_grad_def": v0, "blocks_call": a_call, "al": (a_al0, a_al1)}
    fixed = {"dynamics": FIXED_BLOCKS["dynamics"], "geometry": FIXED_BLOCKS["geometry"],
             "separation": FIXED_BLOCKS["separation"], "blocks_call": FIXED_VG["blocks_call"], "al": FIXED_VG["al"]}
    drift = {k: {"fixed": fixed[k], "runtime": got[k]} for k in fixed if tuple(np_tuple(got[k])) != tuple(np_tuple(fixed[k]))}
    return got, drift, Prepared._blocks.__code__, Prepared.value_grad.__code__


def np_tuple(x):
    return x if isinstance(x, tuple) else (x,)


def _blocks_cat(lm, line):
    for c in ("dynamics", "geometry", "separation"):
        lo, hi = lm[c]
        if lo <= line <= hi:
            return c
    return "shared"


def _key_cat(k):
    if not isinstance(k, tuple) or not k:
        return "shared"
    return {"sep": "separation", "geo": "geometry"}.get(k[0], "dynamics" if k[0] in ("v", "t", "n", "j", "turn")
                                                          else "shared")


class LineTimer:
    """只观察的行事件计时：前一行到下一行事件的 perf_counter_ns 差计入前一行类别；嵌套 _blocks 从父间隔扣除。"""

    def __init__(self, lm, blocks_code, vg_code, deadline):
        self.lm, self.bc, self.vc, self.deadline = lm, blocks_code, vg_code, deadline
        self.acc = defaultdict(int)            # (scope, category) → ns
        self.total = defaultdict(int)          # scope → ns（call→return）
        self.calls = defaultdict(int)
        self.events = 0
        self.stack = []
        self.stopped = False
        self.stop_reason = None

    def _scope(self, frame):
        if frame.f_code is self.vc:
            return "value_grad:" + ("terms" if frame.f_locals.get("terms") else "lbfgs")
        parent = frame.f_back.f_code.co_name if frame.f_back is not None else "?"
        return "blocks_in_value_grad" if parent == "value_grad" else "blocks_from:" + parent

    def global_trace(self, frame, event, arg):
        if self.stopped:
            return None
        if time.perf_counter() > self.deadline:
            self.stopped, self.stop_reason = True, "deadline"
            sys.settrace(None)
            return None
        code = frame.f_code
        if code is not self.bc and code is not self.vc:
            return None
        now = time.perf_counter_ns()
        scope = self._scope(frame)
        self.calls[scope] += 1
        self.stack.append({"frame": frame, "scope": scope, "start": now, "t": now, "line": None, "cat": "shared",
                           "child": 0})
        return self.local_trace

    def _close(self, st, now):
        dt = now - st["t"] - st["child"]
        self.acc[(st["scope"], st["cat"])] += dt
        st["child"] = 0

    def local_trace(self, frame, event, arg):
        now = time.perf_counter_ns()
        self.events += 1
        if not self.stack or self.stack[-1]["frame"] is not frame:
            return self.local_trace
        st = self.stack[-1]
        if event == "line":
            self._close(st, now)
            st["t"] = now
            ln = frame.f_lineno
            st["line"] = ln
            if frame.f_code is self.bc:
                st["cat"] = _blocks_cat(self.lm, ln)
            else:
                lo, hi = self.lm["al"]
                st["cat"] = _key_cat(frame.f_locals.get("k")) if lo <= ln <= hi else "shared"
            if self.stopped:
                return None
        elif event in ("return", "exception"):
            self._close(st, now)
            st["t"] = now
            if event == "return":
                self.stack.pop()
                dur = now - st["start"]
                self.total[st["scope"]] += dur
                if self.stack:
                    self.stack[-1]["child"] += dur
        return self.local_trace


def trace_overhead_ns(n=200000):
    """微基准：一次空 local_trace 调用的平均耗时（报告计时开销用，不从结果中扣除）。"""
    lt = LineTimer({"al": (0, 0), "dynamics": (0, 0), "geometry": (0, 0), "separation": (0, 0)}, None, None, 1e18)
    t0 = time.perf_counter_ns()
    for _ in range(n):
        lt.local_trace(None, "line", None)
    return (time.perf_counter_ns() - t0) / n


# ---------------------------------------------------------------- 单合同子进程

def profile_contract(ctx, entry, draw, *, settings, out_dir):
    """单进程执行一次真实run_contract，保存阶段prof、互斥项计时、内存和实际原始结果。"""
    import v15_memory as VM
    from v08.motion.monitoring_band import _LP_BASIS
    from v08.runner import joint_monitoring as JM
    from v08.runner.monitoring import jsonable
    import v08.motion.optimize as OPT
    out = Path(out_dir)
    sp = ScopedProfiles()
    rounds = []
    orig_opt = OPT.optimize_segment

    def capture(*a, **k):
        r = orig_opt(*a, **k)
        d = r["solution"].diagnostics
        rounds.append(jsonable({kk: v for kk, v in d.items() if kk not in ("ls_controls", "init_controls")}))
        return r
    OPT.optimize_segment = capture
    t0 = time.perf_counter()
    try:
        sp.install()
        try:
            rec = JM.run_contract(ctx, entry, draw, settings=settings, out_dir=out / "run")
        finally:
            sp.uninstall()
    finally:
        OPT.optimize_segment = orig_opt
    wall = time.perf_counter() - t0
    for s, p in sp.prof.items():
        p.dump_stats(str(out / f"{s}.prof"))
    merged = None
    for s in ("orchestration",) + STAGES:
        f = str(out / f"{s}.prof")
        if (out / f"{s}.prof").stat().st_size == 0:
            continue
        try:
            merged = pstats.Stats(f) if merged is None else (merged.add(f) or merged)
        except TypeError:
            continue
    if merged is not None:
        merged.dump_stats(str(out / "merged.prof"))
    tops, details = {}, {}
    for s in ("orchestration",) + STAGES:
        try:
            ps = pstats.Stats(str(out / f"{s}.prof"))
        except (TypeError, EOFError):
            tops[s] = None
            continue
        tops[s] = {"cumulative": _top(str(out / f"{s}.prof"), "cumulative"),
                   "tottime": _top(str(out / f"{s}.prof"), "tottime"), "total_tt_s": ps.total_tt}
        if s == "skeleton":
            details["skeleton"] = detail_skeleton(ps)
        if s == "optimize":
            details["optimize"] = detail_optimize(ps)
    details["lp_basis_cache"] = {"entries_after_run": len(_LP_BASIS),
                                 "note": "新进程首次 _lp_basis 为未命中；命中数 = _lp_basis 调用数 − entries_after_run"}
    mem = VM.process_memory()
    stage_excl = {s: sp.excl.get(s, 0.0) for s in ("orchestration",) + STAGES}
    return {"contract_id": rec["contract_id"], "success": rec["success"], "attempts": rec["attempts"],
            "profiled_wall_s": wall, "stage_exclusive_wall_s": stage_excl,
            "stage_sum_check_s": sum(stage_excl.values()), "stage_calls": dict(sp.calls),
            "run_contract_stage_timing": rec.get("stage_timing"), "top": tops, "details": details,
            "al_rounds_per_optimize_call": rounds, "memory": mem}


def line_contract(ctx, entry, draw, *, settings, out_dir, deadline):
    import v15_memory as VM
    from v08.runner import joint_monitoring as JM
    import v08.motion.optimize as OPT
    out = Path(out_dir)
    lm, drift, bc, vc = line_map()
    lt = LineTimer(lm, bc, vc, deadline)
    orig = OPT.optimize_segment
    traced_s = [0.0]

    def traced(*a, **k):
        t1 = time.perf_counter()
        if not lt.stopped:
            sys.settrace(lt.global_trace)
        try:
            return orig(*a, **k)
        finally:
            sys.settrace(None)
            traced_s[0] += time.perf_counter() - t1
    OPT.optimize_segment = traced
    t0 = time.perf_counter()
    try:
        rec = JM.run_contract(ctx, entry, draw, settings=settings, out_dir=out / "run")
    finally:
        OPT.optimize_segment = orig
        sys.settrace(None)
    wall = time.perf_counter() - t0
    acc = defaultdict(dict)
    for (scope, cat), ns in lt.acc.items():
        acc[scope][cat] = ns / 1e9
    vg_scopes = [s for s in lt.total if s.startswith("value_grad")]
    vg_total = sum(lt.total[s] for s in vg_scopes) / 1e9
    cats = defaultdict(float)
    for s in vg_scopes + ["blocks_in_value_grad"]:
        for c, v in acc.get(s, {}).items():
            cats[c] += v
    attributed = sum(cats.values())
    shares = {c: (v / vg_total if vg_total else None) for c, v in cats.items()}
    upper = {c: ((cats[c] + cats.get("shared", 0.0)) / vg_total if vg_total else None)
             for c in ("separation", "geometry", "dynamics") if c in cats}
    neg = {f"{s}/{c}": v for s, d in acc.items() for c, v in d.items() if v < 0}
    return {"contract_id": rec["contract_id"], "success": rec["success"], "attempts": rec["attempts"],
            "wall_s": wall, "optimize_traced_wall_s": traced_s[0], "partial": lt.stopped,
            "stop_reason": lt.stop_reason, "line_map": {k: list(np_tuple(v)) for k, v in lm.items()},
            "line_drift_vs_fixed": drift, "events": lt.events, "calls": dict(lt.calls),
            "scope_total_s": {s: v / 1e9 for s, v in lt.total.items()}, "by_scope_category_s": acc,
            "value_grad_total_s": vg_total, "value_grad_attributed_s": attributed,
            "attribution_gap_s": vg_total - attributed, "value_grad_category_s": dict(cats),
            "value_grad_share_direct": shares, "value_grad_share_upper_bound": upper,
            "negative_categories": neg, "trace_overhead_ns_per_event": trace_overhead_ns(),
            "memory": VM.process_memory(),
            "note": "占比口径：可直接归属的 sep/geo/dynamics + shared（共享 P/V/A/J 求值、梯度投影、预条件等）；"
                    "上界 = 直接 + shared；blocks_from:* 为 constraint_values/max_violation/update_multipliers 触发，"
                    "不进 value_grad 分子分母"}


def _child(args):
    for k in THREAD_VARS:
        os.environ[k] = "1"
    from v08.motion.optimize import load_settings
    from v08.runner.monitoring import load_entries, write_json
    from v08.scene.context import load_context
    entries = {int(e["order"]): e for e in load_entries(args.devset)}
    o, d = (int(x) for x in args.one.split(":"))
    e = entries[o]
    ctx = load_context(e, data_root=Path(args.data_root), cache_dir=Path(args.cache))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    settings = load_settings()
    if args.mode == "cprofile":
        doc = profile_contract(ctx, e, d, settings=settings, out_dir=out)
    else:
        doc = line_contract(ctx, e, d, settings=settings, out_dir=out,
                            deadline=time.perf_counter() + float(args.deadline))
        doc["line_limit_s"] = float(args.deadline)
    from v15_metrics import compare_contracts
    cid = doc["contract_id"]
    c = compare_contracts(Path(args.baseline) / "contracts" / cid, out / "run" / "contracts" / cid)
    doc["bytes_equal_to_baseline"] = c["bytes_equal"]
    doc["differing"] = c["differing"]
    write_json(out / "result.json", doc, indent=1)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--select-to")
    ap.add_argument("--mode", choices=("cprofile", "line"))
    ap.add_argument("--selection")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--devset")
    ap.add_argument("--data-root")
    ap.add_argument("--cache")
    ap.add_argument("--out")
    ap.add_argument("--one", help=argparse.SUPPRESS)
    ap.add_argument("--deadline", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.select_to:
        doc = select(args.baseline, args.select_to)
        print(json.dumps({k: doc[k] for k in ("estimate_s", "replaced", "line_keys")}, ensure_ascii=False))
        print(json.dumps([(x["contract_id"], x["wall_s"], x["why"]) for x in doc["final"]], ensure_ascii=False))
        return 0
    if args.one:
        return _child(args)
    from v08.runner.monitoring import PathRejected, guard_path, write_json
    try:
        out = guard_path(args.out, label="输出", data_root=Path(args.data_root), must_not_exist=True)
        guard_path(args.cache, label="缓存", data_root=Path(args.data_root))
    except PathRejected as exc:
        print(f"路径被拒绝：{exc}", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=False)
    sel = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    rows = sel["final"] if args.mode == "cprofile" else [x for x in sel["final"] if x["contract_id"] in sel["line_keys"]]
    env = dict(os.environ, **{k: "1" for k in THREAD_VARS})
    t_start = time.time()
    total_deadline = time.perf_counter() + LINE_TOTAL_S
    runs = []
    for r in rows:
        cmd = [sys.executable, "-B", str(Path(__file__).resolve()), "--mode", args.mode, "--baseline", args.baseline,
               "--devset", args.devset, "--data-root", args.data_root, "--cache", args.cache,
               "--out", str(out / r["contract_id"]), "--one", f"{r['order']}:{r['draw_index']}"]
        if args.mode == "line":
            # 子进程 perf_counter 与父进程不同源：传"自子进程启动起的秒数"由子进程换算
            remain = total_deadline - time.perf_counter()
            limit = min(LINE_FACTOR * float(r["wall_s"]), max(0.0, remain))
            cmd += ["--deadline", f"{limit}"]
        t0 = time.perf_counter()
        p = subprocess.run(cmd, env=env, capture_output=True, text=True)
        runs.append({"contract_id": r["contract_id"], "exit": p.returncode, "process_wall_s": time.perf_counter() - t0,
                     "stderr_tail": p.stderr[-4000:]})
        print(f"{r['contract_id']} exit={p.returncode} {time.perf_counter() - t0:.0f}s", flush=True)
    write_json(out / "runs.json", {"mode": args.mode, "runs": runs, "wall_s": time.time() - t_start}, indent=1)
    return 0 if all(x["exit"] == 0 for x in runs) else 3


if __name__ == "__main__":
    sys.exit(main())
