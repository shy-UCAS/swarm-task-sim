"""监视单段规划（V8-12 第 3 部分；指令 3.9）：一次随机构造 = 一个 attempt，20 次预算贯穿规划和仿真。

失败口径（r4 6.5）：
- proven_infeasible：只在精确必要条件证书成立时报（同心圆环 / 同一凸基轮廓的平行 buffer 的单车道必要条件），
  证书从原几何重算，不是非空 dict；
- approx_empty：距离场保守集或极坐标可行带为空，精确复核无证书；
- budget_exhausted：随机构造/连接/名义判据/间距用完 20 次，只说明预算耗尽，保留各 attempt 原因；
V8-13（指令 4.1）：删除按名义时长下界判"近似为空"的分支；只保留有几何依据的空集分类。V8-13 runner 只调用
plan_attempt 并自管唯一的 20 次全链路预算；plan_segment 仅留作历史入口，不被 V8-13 调用。
- 单个 attempt 的失败是 candidate_rejected（原始数值见证在 attempt_log 里）。
规划不动公共抽签和目标：重试只加 attempt。
"""
import time
from dataclasses import replace

import numpy as np

from ..contract.monitoring import Failure, SegmentPlan
from ..sampler.keys import RngKey
from .feasible import certificate_valid, classify_empty, prove_concentric_band_empty


def _attempt_record(a, plan, seconds):
    f = plan.failure
    return {"attempt": a, "ok": f is None, "seconds": seconds,
            "stage": None if f is None else (f.witness or {}).get("stage", f.feasible_set),
            "code": None if f is None else f.code, "reason": None if f is None else f.reason,
            "feasible_set": None if f is None else f.feasible_set,
            "witness": None if f is None else f.witness,
            "repairs": list(plan.repairs) if f is None else list((plan.proposal or {}).get("repairs", ())),
            "built_candidate": bool(plan.proposal is not None)}


def plan_attempt(ctx, group, task, states, occupied, key):
    """一次随机构造，返回 SegmentPlan（失败时 failure 非空）。"""
    from .intents.monitoring import propose_and_build

    return propose_and_build(ctx, group, task, states, key)


def _band_certificate(ctx, group, task):
    tgt = ctx.facility_by_id[task.target_id]
    mon = ctx.params["monitoring"]
    return prove_concentric_band_empty(tgt.layers["alert"], tgt.layers["warning"],
                                       alert_clearance_m=mon["alert_clearance_m"],
                                       warning_inset_m=mon["warning_inset_m"],
                                       member_count=len(group.member_ids), formation="column")


EXACT_RECHECK_STEP_M = 0.5
EXACT_RECHECK_MAX_WITNESSES = 3


def exact_patrol_witnesses(ctx, task, step_m=EXACT_RECHECK_STEP_M, limit=EXACT_RECHECK_MAX_WITNESSES):
    """在目标警戒圈外接框上按 step_m 取点，用精确有符号距离复核"单车道巡逻约束"是否有可行点。
    返回 (可行点列表, 检查点数)。只用于近似为空后的复核，不参与生成。"""
    from ..scene.exact import bounding_box, clearance_values
    from .intents.monitoring import monitoring_constraints

    cons = monitoring_constraints(ctx, task.target_id)
    cs = cons["base"] + cons["patrol"]
    x0, y0, x1, y1 = bounding_box(ctx.facility_by_id[task.target_id].layers["warning"])
    xs = np.arange(x0, x1 + step_m, step_m)
    found, checked = [], 0
    for y in np.arange(y0, y1 + step_m, step_m):
        pts = np.stack([xs, np.full_like(xs, y)], axis=1)
        ok = np.ones(len(xs), bool)
        for c in cs:
            ok &= clearance_values(c.geometry, pts, sense=c.sense, minimum_m=c.minimum_m) >= 0.0
        checked += len(xs)
        for i in np.flatnonzero(ok)[:limit - len(found)]:
            found.append((float(pts[i, 0]), float(pts[i, 1])))
        if len(found) >= limit:
            break
    return found, checked


def empty_query(ctx, group, task):
    """一次"可行集合查询"：巡逻带（单车道）的距离场保守集是否为空，并做精确复核。
    返回 (记录, Failure 或 None)。保守集非空时返回 (记录, None)——此时失败来自环/弧的构造而非集合为空。"""
    from .intents.monitoring import monitoring_constraints

    cons = monitoring_constraints(ctx, task.target_id)
    cs = cons["base"] + cons["patrol"]
    field = ctx.field(("patrol", task.target_id), cs)
    names = [c.name for c in cs]
    cells_nonempty = bool(np.any(field.certified_cell_mask(names=names)))
    rec = {"query_id": f"{ctx.family.family_id}/{task.target_id}/patrol_band", "field_empty": not cells_nonempty,
           "exact_recheck_executed": False, "exact_nonempty": None, "exact_points_checked": 0}
    if cells_nonempty:
        return rec, None
    witnesses, checked = exact_patrol_witnesses(ctx, task)
    rec.update(exact_recheck_executed=True, exact_points_checked=checked, exact_nonempty=bool(witnesses))
    cert = _band_certificate(ctx, group, task)
    failure = classify_empty(field, cs, exact_witnesses=witnesses, certificate=cert)
    if failure is not None and failure.code == "approx_empty" and failure.exact_nonempty is None and not witnesses:
        # 精确复核在 0.5 m 采样点上没有找到可行点，但这不是证明；保持"未知"，不当作证明为空
        rec["exact_nonempty"] = None
    return rec, failure


def final_failure(ctx, group, task, log):
    """r4 13.4 的最终失败分类（V8-13 runner 复用）：log 为各 attempt 记录，需含 stage。"""
    return _final_failure(ctx, group, task, log)


def _final_failure(ctx, group, task, log):
    stages = {r["stage"] for r in log}
    if stages == {"patrol_region"}:
        rec, failure = empty_query(ctx, group, task)
        if failure is not None:
            return Failure(failure.code, failure.reason, failure.feasible_set,
                           {**(failure.witness or {}), "query": rec, "attempts": len(log)}, failure.exact_nonempty)
        return Failure("approx_empty", "全部 attempt 在所有队形下都找不到满足条件的环/弧（极坐标可行带为空）；"
                                       "单车道距离场保守集非空",
                       "patrol_ring", {"attempts": len(log), "query": rec}, None)
    return Failure("budget_exhausted", f"{len(log)} 次随机构造用完预算", "random_construction",
                   {"attempts": len(log), "stages": sorted(str(s) for s in stages)}, None)


def plan_segment(ctx, group, task, states, occupied, rng):
    """rng 是该合同的不可变 RngKey（attempt=0），不是共享的可变 Generator。"""
    key0 = rng
    cert = _band_certificate(ctx, group, task)
    if cert is not None and certificate_valid(cert):
        return SegmentPlan(members={}, reference_xy=(), nominal_duration_s=float("nan"), anchors={}, repairs=(),
                           failure=cert, business_key={"family_id": key0.family_id, "draw": key0.draw},
                           attempt_log=())
    budget = int(ctx.params["shape_attempts"])
    log = []
    for a in range(budget):
        key = RngKey(key0.family_id, key0.draw, key0.purpose, mission=key0.mission, branch=key0.branch,
                     group=key0.group, segment=key0.segment, attempt=a)
        t0 = time.perf_counter()
        plan = plan_attempt(ctx, group, task, states, occupied, key)
        rec = _attempt_record(a, plan, time.perf_counter() - t0)
        log.append(rec)
        if plan.failure is None:
            return replace(plan, attempt_log=tuple(log))
    return SegmentPlan(members={}, reference_xy=(), nominal_duration_s=float("nan"), anchors={}, repairs=(),
                       failure=_final_failure(ctx, group, task, log),
                       business_key={"family_id": key0.family_id, "draw": key0.draw}, attempt_log=tuple(log))
