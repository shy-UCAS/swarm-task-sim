"""V8-13 运行器（指令 4.2–4.4、5.1）：唯一 20 次全链路预算、快速集选择、端到端、进程调度、确定性输出。

一个合同：固定一次 sample_common(family, draw)、一次 monitoring_mission(ctx, common)；每个 attempt 只递增
RngKey.attempt（没有进程号、墙钟、hash() 或完成顺序参与）。attempt 顺序：
plan_attempt（随机骨架）→ optimize_segment（全体成员固定时间联合求解一次 + 全部语义硬检查）→
每成员 run_tracking_segment 一次（任一超时拒收）→ stitch → verify_segments → visible_track + check_validity。
全部通过才 success；否则记失败码与原始对象进入下一 attempt。20 次预算贯穿上述全链路；不调用 plan_segment，
不嵌套第二层预算，不在优化器内多次求解择优。

本模块导入时不读数据、不建目录、不启动批量任务。
"""
import hashlib
import json
import math
import os
import time
import traceback
from dataclasses import replace
from itertools import combinations
from pathlib import Path

import numpy as np

from . import joint_report as JR
from .monitoring import canonical_json, guard_path, jsonable, load_entries, write_json

BUDGET = 20                 # U D.3.2；geometry.shape_attempts
QUICK_FAMILIES = 10         # U D.3.3
QUICK_PER_FAMILY = 2        # U D.3.3
LOW_SPEED_M_S = 5.5         # U D.3.3：初始指令速度 < 5.5 的合同至少 2 个
DRAWS = 5


# ---------------------------------------------------------------- 唯一预算

def run_attempts(key, attempt_fn, *, budget=BUDGET):
    """attempt_fn(key_with_attempt) -> {"ok":bool, "stage":str, ...}
    返回 {"success":bool, "attempts":int, "records":list, "result":object}；首次成功报告 attempts=1。"""
    records = []
    for a in range(int(budget)):
        rec = attempt_fn(replace(key, attempt=a))
        records.append(rec)
        if rec.get("ok"):
            return {"success": True, "attempts": a + 1, "records": records, "result": rec}
    return {"success": False, "attempts": len(records), "records": records, "result": None}


# ---------------------------------------------------------------- 快速集（公共抽签元数据，不规划选样）

def common_metadata(ctx, entry, draw):
    from ..contract.monitoring import monitoring_mission
    from ..sampler.common import sample_common
    common = sample_common(ctx.family, draw)
    mission = monitoring_mission(ctx, common)
    group = mission.groups[0]
    return {"family_id": entry["family_id"], "order": int(entry["order"]), "draw_index": int(draw),
            "facility_count": int(entry["facility_count"]), "vehicle_count": int(entry["vehicle_count"]),
            "initial_speed_m_s": float(group.speed_profile.initial_speed_m_s),
            "group_size": len(group.member_ids), "target_id": mission.tasks[0].target_id}


def select_quick(entries, common_records):
    """10 族、每族恰 2 个 draw；设施数 1/2/3 各 ≥ 2 合同、含 vehicle_count 最大族（并列取 order 最小）、
    初始指令速度 < 5.5 的合同 ≥ 2。按 order 动态规划，状态（已选族数, 三个设施档合同数各截到 2, 低速数截到 2,
    最大族是否入选），每状态只留 (order, draw) 列表字典序最小者；返回第一个可行列表或 None（覆盖不可满足）。"""
    ordered = sorted(entries, key=lambda e: e["order"])
    largest = min(ordered, key=lambda e: (-e["vehicle_count"], e["order"]))["family_id"]
    by_fam = {}
    for r in common_records:
        by_fam.setdefault(r["family_id"], {})[int(r["draw_index"])] = r
    states = {(0, 0, 0, 0, 0, False): []}
    for e in ordered:
        fid = e["family_id"]
        draws = by_fam.get(fid, {})
        new = dict(states)
        for st, lst in states.items():
            n, f1, f2, f3, low, big = st
            if n >= QUICK_FAMILIES:
                continue
            for a, b in combinations(sorted(draws), QUICK_PER_FAMILY):
                ra, rb = draws[a], draws[b]
                fc = [f1, f2, f3]
                k = int(e["facility_count"]) - 1
                if 0 <= k < 3:
                    fc[k] = min(2, fc[k] + 2)
                lw = min(2, low + sum(float(r["initial_speed_m_s"]) < LOW_SPEED_M_S for r in (ra, rb)))
                ns = (n + 1, fc[0], fc[1], fc[2], lw, big or fid == largest)
                cand = lst + [(int(e["order"]), a), (int(e["order"]), b)]
                if ns not in new or cand < new[ns]:
                    new[ns] = cand
        states = new
    goal = (QUICK_FAMILIES, 2, 2, 2, 2, True)
    return states.get(goal)


# ---------------------------------------------------------------- 单个 attempt

def _member_reference(tr):
    from ..sim.tracking import TimeReference
    return TimeReference(tr.member_id, float(tr.release_s), float(tr.end_s), float(tr.altitude_m), tr.pva)


def _fail(stage, t, **kw):
    return {"ok": False, "stage": stage, "timing": t, **kw}


def attempt_chain(ctx, group, task, states, key, settings):
    """一次全链路 attempt；返回 dict（ok/stage/timing/各阶段原始对象）。未捕获异常由调用方记录 traceback。"""
    from ..criteria.segment import SegmentTask, verify_segments
    from ..criteria.validity import check_validity, visible_track
    from ..motion.optimize import optimize_segment
    from ..motion.plan import plan_attempt
    from ..sim.stitch import stitch
    from ..sim.tracking import run_tracking_segment
    t = {"skeleton_s": 0.0, "optimize_s": 0.0, "simulation_s": 0.0, "verify_s": 0.0}
    t0 = time.perf_counter()
    plan = plan_attempt(ctx, group, task, states, (), key)
    t["skeleton_s"] = time.perf_counter() - t0
    if plan.failure is not None:
        f = plan.failure
        return _fail("skeleton", t, plan=plan, code=f.code, reason=f.reason, feasible_set=f.feasible_set,
                     witness=f.witness)
    t0 = time.perf_counter()
    opt = optimize_segment(ctx, plan, key, settings)
    t["optimize_s"] = time.perf_counter() - t0
    diag = opt["solution"].diagnostics
    t["nit"], t["nfev"] = diag.get("nit"), diag.get("nfev")
    if not opt["ok"]:
        return _fail(opt["stage"], t, plan=plan, opt=opt, code="candidate_rejected", reason=opt["reason"])
    t0 = time.perf_counter()
    results, timeouts = [], []
    for m in sorted(opt["solution"].references):
        res = run_tracking_segment(_member_reference(opt["solution"].references[m]), states[m], final=True)
        results.append(res)
        if res.status != "ok":
            timeouts.append(m)
    t["simulation_s"] = time.perf_counter() - t0
    if timeouts:
        return _fail("simulation", t, plan=plan, opt=opt, results=results, code="candidate_rejected",
                     reason="sim_timeout", members=timeouts)
    t0 = time.perf_counter()
    tracks = stitch(results)
    release = {m: int(r.pieces[0].release_us) for m, r in zip(sorted(opt["solution"].references), results)}
    verdicts = verify_segments(ctx.scene, tracks, release, [SegmentTask(0, "monitoring", task.target_id)])
    seg_ok = all(v.passed for v in verdicts)
    visible = [visible_track(tracks[m], release[m]) for m in sorted(tracks)]
    valid = check_validity(ctx.scene, visible)
    t["verify_s"] = time.perf_counter() - t0
    out = {"plan": plan, "opt": opt, "results": results, "tracks": tracks, "release_us": release,
           "verdicts": verdicts, "validity": valid, "timing": t}
    if not seg_ok:
        return {"ok": False, "stage": "verify_segments", "code": "candidate_rejected",
                "reason": "segment_verification", **out}
    if not valid.passed:
        return {"ok": False, "stage": "validity", "code": "candidate_rejected", "reason": "validity", **out}
    return {"ok": True, "stage": "verified", **out}


def _attempt_summary(rec, key):
    t = rec.get("timing", {})
    s = {"attempt": key.attempt, "ok": bool(rec["ok"]), "stage": rec["stage"], "code": rec.get("code"),
         "reason": rec.get("reason"), "timing": t}
    if "feasible_set" in rec:
        s["feasible_set"] = rec["feasible_set"]
        s["witness"] = jsonable(rec.get("witness"))
    opt = rec.get("opt")
    if opt is not None:
        d = opt["solution"].diagnostics
        s["optimize"] = {k: jsonable(d.get(k)) for k in ("nit", "nfev", "message", "success", "value", "terms",
                                                       "max_abs_grad", "reference_deviation", "settings_sha256")}
        s["optimize"]["physical_failures"] = jsonable((d.get("physical") or {}).get("failures"))
        if opt.get("monitoring") is not None:
            s["optimize"]["monitoring_failures"] = jsonable(opt["monitoring"]["failures"])
    if rec.get("verdicts") is not None:
        s["segment_failures"] = jsonable([v.failures for v in rec["verdicts"]])
    if rec.get("validity") is not None:
        v = rec["validity"]
        s["validity"] = {"passed": v.passed, "codes": jsonable(v.codes), "min_separation_m": v.min_separation_m}
    if rec.get("traceback"):
        s["traceback"] = rec["traceback"]
    return s


# ---------------------------------------------------------------- 单合同

def contract_id(entry, draw, branch=None):
    return f"o{int(entry['order']):02d}_d{int(draw)}" + ("" if branch is None else f"_b{int(branch)}")


def run_contract(ctx, entry, draw, *, settings, branch=None, out_dir=None):
    """一个合同的完整链路与唯一 20 次预算。out_dir 给出时写 contracts/<id>/ 的确定性载荷。返回记录 dict。"""
    from ..contract.monitoring import initial_states, monitoring_mission
    from ..motion.plan import final_failure
    from ..sampler.common import sample_common
    from ..sampler.keys import RngKey
    common = sample_common(ctx.family, draw)
    mission = monitoring_mission(ctx, common)
    group, task = mission.groups[0], mission.tasks[0]
    states = initial_states(ctx.family, group.member_ids)
    key0 = RngKey(ctx.family.family_id, int(draw), "shape", mission=0, branch=branch, group=group.group_id, segment=0)
    summaries = []

    def attempt_fn(k):
        try:
            rec = attempt_chain(ctx, group, task, states, k, settings)
        except Exception as exc:                    # 实现异常不伪装成正常随机失败：保存 traceback
            rec = {"ok": False, "stage": "exception", "code": "implementation_error", "reason": repr(exc),
                   "traceback": traceback.format_exc(), "timing": {}}
        summaries.append(_attempt_summary(rec, k))
        return rec

    out = run_attempts(key0, attempt_fn)
    opt_s = float(sum((s["timing"] or {}).get("optimize_s", 0.0) for s in summaries))
    cid = contract_id(entry, draw, branch)
    failure = None
    if not out["success"]:
        log = []
        for s in summaries:
            stage = s["stage"]
            if stage == "skeleton":
                w = s.get("witness") if isinstance(s.get("witness"), dict) else {}
                stage = w.get("stage", s.get("feasible_set"))
            log.append({"stage": stage})
        f = final_failure(ctx, group, task, log)
        failure = {"code": f.code, "reason": f.reason, "feasible_set": f.feasible_set, "witness": jsonable(f.witness)}
    rec = {"contract_id": cid, "family_id": ctx.family.family_id, "order": int(entry["order"]),
           "draw_index": int(draw), "branch": branch, "facility_count": int(entry["facility_count"]),
           "vehicle_count": int(ctx.family.vehicle_count), "lateral_spacing_m": float(ctx.family.lateral_spacing_m),
           "group_id": group.group_id, "member_ids": sorted(group.member_ids), "group_size": len(group.member_ids),
           "target_id": task.target_id, "initial_speed_m_s": float(group.speed_profile.initial_speed_m_s),
           "formation_prior": group.formation_prior, "success": bool(out["success"]), "attempts": out["attempts"],
           "optimization_s": opt_s, "failure": failure, "attempt_log": summaries,
           "settings_sha256": settings.get("_sha256"),
           "release_us": None, "retained_p0_ok": True}
    if out["success"]:
        res = out["result"]
        rec["release_us"] = {m: int(v) for m, v in sorted(res["release_us"].items())}
        rec["retained_p0_ok"] = _retained_p0(res)
    if out_dir is not None:
        save_contract(Path(out_dir), rec, out["result"])
    return rec


def _retained_p0(res):
    """保留段 P0 门禁（指令 5.2）：段核验通过、实测间距 ≥ 2 m 与限制区（check_validity）、时间线无重复/空洞。"""
    if not all(v.passed for v in res["verdicts"]):
        return False
    if not res["validity"].passed:
        return False
    for tr in res["tracks"].values():
        d = np.diff(np.asarray(tr.tau_us, np.int64))
        if len(d) and not np.all(d == 100_000):
            return False
    return True


# ---------------------------------------------------------------- 确定性输出

def _json_bytes(obj):
    return canonical_json(obj) + b"\n"


def save_contract(out, rec, result):
    """contracts/<id>/{contract.json,result.json}；成功另存 skeleton.json、optimized.json 与 tracks/<m>/*.npy。
    墙钟等遥测写在合同目录外的 telemetry/<id>.json，不参与确定性载荷。"""
    d = out / "contracts" / rec["contract_id"]
    d.mkdir(parents=True, exist_ok=False)
    contract = {k: rec[k] for k in ("contract_id", "family_id", "order", "draw_index", "branch", "facility_count",
                                    "vehicle_count", "group_id", "member_ids", "group_size", "target_id",
                                    "initial_speed_m_s", "formation_prior")}
    (d / "contract.json").write_bytes(_json_bytes(contract))
    det_attempts = []
    for s in rec["attempt_log"]:
        s2 = {k: v for k, v in s.items() if k not in ("timing", "traceback")}
        det_attempts.append(s2)
    result_doc = {"success": rec["success"], "attempts": rec["attempts"], "failure": rec["failure"],
                  "attempt_log": det_attempts, "release_us": rec["release_us"], "settings_sha256": rec["settings_sha256"],
                  "retained_p0_ok": rec["retained_p0_ok"]}
    (d / "result.json").write_bytes(_json_bytes(result_doc))
    if result is not None and result.get("ok"):
        plan = result["plan"]
        from .monitoring import plan_to_record
        prec, arrays = plan_to_record(plan)
        prec["arrays"] = {k: np.asarray(v).tolist() for k, v in sorted(arrays.items())}
        (d / "skeleton.json").write_bytes(_json_bytes(prec))
        sol = result["opt"]["solution"]
        opt_doc = {"members": {m: {"release_s": t.release_s, "end_s": t.end_s, "altitude_m": t.altitude_m,
                                   "knots": t.knots, "controls": t.controls}
                               for m, t in sorted(sol.references.items())},
                   "lines": jsonable(result["opt"]["lines"]),
                   "diagnostics": {k: jsonable(sol.diagnostics.get(k)) for k in
                                   ("nit", "nfev", "message", "value", "terms", "max_abs_grad", "reference_deviation",
                                    "symmetry_break", "settings_sha256")}}
        (d / "optimized.json").write_bytes(_json_bytes(opt_doc))
        for m, tr in sorted(result["tracks"].items()):
            td = d / "tracks" / m
            td.mkdir(parents=True, exist_ok=False)
            for name in ("tau_us", "p", "v", "a", "segment_index"):
                np.save(td / f"{name}.npy", np.ascontiguousarray(getattr(tr, name)), allow_pickle=False)
    tele = out / "telemetry"
    tele.mkdir(exist_ok=True)
    (tele / f"{rec['contract_id']}.json").write_bytes(_json_bytes(
        {"timing": [s.get("timing") for s in rec["attempt_log"]], "optimization_s": rec["optimization_s"],
         "tracebacks": [s.get("traceback") for s in rec["attempt_log"] if s.get("traceback")]}))


# ---------------------------------------------------------------- 批次

def _record_row(rec):
    keys = ("contract_id", "family_id", "draw_index", "branch", "facility_count", "initial_speed_m_s", "group_size",
            "success", "attempts", "optimization_s", "retained_p0_ok", "member_ids", "target_id", "release_us",
            "failure", "order", "vehicle_count")
    return {k: rec.get(k) for k in keys}


def run_batch(entries, *, stage, data_root, cache_dir, out_dir, workers=8, keys=None, settings=None, log=print):
    """keys: [(order, draw)]（快速集或复跑集）；None 表示全部 entries × draw 0..4。单进程顺序执行
    （workers>1 的进程池由第 5 部分接入）。按业务 key 排序写 records.json 与 summary.json。"""
    from ..motion.optimize import load_settings
    from ..scene.context import load_context
    out = Path(out_dir)
    settings = settings if settings is not None else load_settings()
    by_order = {int(e["order"]): e for e in entries}
    if keys is None:
        keys = [(int(e["order"]), d) for e in sorted(entries, key=lambda x: x["order"]) for d in range(DRAWS)]
    keys = sorted((int(o), int(d)) for o, d in keys)
    records = []
    ctx_cache = {}
    t0 = time.perf_counter()
    for o, d in keys:
        e = by_order[o]
        if o not in ctx_cache:
            ctx_cache.clear()
            ctx_cache[o] = load_context(e, data_root=data_root, cache_dir=cache_dir)
        rec = run_contract(ctx_cache[o], e, d, settings=settings, out_dir=out)
        records.append(rec)
        log(f"{rec['contract_id']}: success={rec['success']} attempts={rec['attempts']} "
            f"opt={rec['optimization_s']:.1f}s fail={(rec['failure'] or {}).get('code')}")
    rows = [_record_row(r) for r in sorted(records, key=lambda r: r["contract_id"])]
    write_json(out / "records.json", rows, indent=1)
    chk = JR.quick_checkpoint(rows) if stage == "quick" else None
    summary = {"stage": stage, "expected_count": len(keys), "completed": len(rows),
               "wall_s": time.perf_counter() - t0, "checkpoint": chk, "settings_sha256": settings.get("_sha256")}
    write_json(out / "summary.json", summary, indent=1)
    return summary


# ---------------------------------------------------------------- CLI 驱动

def cli(args, out):
    """quick：选快速集写 quick_selection.json，再跑完整链路；前提（权重配置）未完成时写前提状态并返回 3。"""
    import sys
    from ..motion.optimize import SettingsIncomplete, load_settings
    from ..scene.context import load_context
    if not (args.devset and args.data_root and args.cache):
        print("quick/full/diversity/rerun 需要 --devset --data-root --cache", file=sys.stderr)
        return 1
    data_root = Path(args.data_root)
    cache = guard_path(args.cache, label="缓存", data_root=data_root)
    entries = load_entries(args.devset)
    out.mkdir(parents=True, exist_ok=False)
    if args.stage == "quick":
        meta = []
        for e in entries:
            ctx = load_context(e, data_root=data_root, cache_dir=cache)
            for d in range(DRAWS):
                meta.append(common_metadata(ctx, e, d))
        sel = select_quick(entries, meta)
        doc = {"selection": sel, "keys": [contract_id({"order": o}, d) for o, d in (sel or [])],
               "common_metadata": meta, "rule": "指令 4.3 动态规划（字典序最小可行列表）"}
        write_json(out / "quick_selection.json", doc, indent=1)
        if sel is None:
            print("登记抽签本身不满足快速集覆盖（不生成第 6 个 draw 补足）", file=sys.stderr)
            return 3
        try:
            settings = load_settings()
        except SettingsIncomplete as exc:
            write_json(out / "summary.json", {"stage": "quick", "expected_count": len(sel), "completed": 0,
                                              "precondition": "incomplete", "reason": str(exc)}, indent=1)
            print(f"前提未完成：{exc}", file=sys.stderr)
            return 3
        summary = run_batch(entries, stage="quick", data_root=data_root, cache_dir=cache, out_dir=out, workers=1,
                            keys=sel, settings=settings)
        chk = summary["checkpoint"]
        print("检查点 2：", json.dumps(chk, ensure_ascii=False))
        return 2 if chk["triggered"] else 0
    print(f"--stage {args.stage} 属于第 5 部分，需两个检查点均通过后接入；本次未实现运行路径", file=sys.stderr)
    return 3
