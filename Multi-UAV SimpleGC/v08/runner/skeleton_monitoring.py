"""V8-14 第 6 部分：只构造骨架的批次与 U D.5 止损检查点（指令 6.1–6.3）。

每合同沿用 joint_monitoring.run_attempts（唯一预算 20），attempt_fn 只调用一次 plan_attempt：不优化、不仿真，
不以名义判据、间距或时长拒绝。骨架成功 = 完整 SegmentPlan.failure is None（起点路由、入/出圈、变队形与完整几何
构造全部完成）。同族 5 合同在同一 worker 顺序执行，跨族并行（沿用 V8-13 的同族串行修复）。

检查点阈值（U D.5，严格比较，Fraction）：骨架合同成功率 < 95%；任一人数档成功率比总体低 > 10 个百分点；
成功合同骨架尝试次数中位数 > 1；形状复核失败率（分母为全部骨架 attempt）> 5%。
本模块导入时不读数据、不建目录。
"""
import json
import time
import traceback
from fractions import Fraction
from pathlib import Path
from statistics import median

SUCCESS_FLOOR = Fraction(95, 100)        # U D.5
GROUP_GAP = Fraction(10, 100)            # U D.5：10 个百分点
ATTEMPT_MEDIAN = 1                       # U D.5
SHAPE_AUDIT_RATE = Fraction(5, 100)      # U D.5
TRIGGERS = ("success_rate", "group_gap", "attempts", "shape_audit")
EXPECTED = 200


def _group_bin(n):
    from .joint_report import group_bin
    return group_bin(n)


def skeleton_checkpoint(records, *, expected_count=EXPECTED):
    """records 每行至少含 contract_id, success, attempts, group_size, facility_count, initial_speed_m_s,
    shape_audit_failed_attempts。返回 {"complete", "triggered", "metrics"}；未完成/缺记录/实现异常保留在 complete。"""
    from .joint_report import group_bin, speed_bin
    rows = list(records)
    ids = [r.get("contract_id") for r in rows]
    incomplete = [r.get("contract_id") for r in rows if r.get("incomplete") or r.get("error")]
    complete = (len(rows) == int(expected_count) and len(set(ids)) == len(ids) and not incomplete)
    n = len(rows)
    succ = [r for r in rows if r.get("success")]
    trig = []
    metrics = {"contracts": n, "expected": int(expected_count), "successes": len(succ), "incomplete": incomplete}
    if n:
        rate = Fraction(len(succ), n)
        metrics["success_rate"] = float(rate)
        metrics["success_rate_fraction"] = f"{rate.numerator}/{rate.denominator}"
        if rate < SUCCESS_FLOOR:
            trig.append("success_rate")
        for name, key in (("group", lambda r: group_bin(r["group_size"])),
                          ("facility", lambda r: int(r["facility_count"])),
                          ("speed", lambda r: speed_bin(r["initial_speed_m_s"]))):
            bins = {}
            for r in rows:
                bins.setdefault(key(r), []).append(r)
            out, worst = {}, None
            for b, rs in sorted(bins.items()):
                br = Fraction(sum(bool(x.get("success")) for x in rs), len(rs))
                gap = rate - br
                att = [x["attempts"] for x in rs if x.get("success")]
                out[str(b)] = {"n": len(rs), "successes": sum(bool(x.get("success")) for x in rs),
                               "rate": float(br), "gap": float(gap),
                               "success_attempts_median": median(att) if att else None,
                               "attempts_total": sum(int(x.get("attempts") or 0) for x in rs)}
                worst = gap if worst is None or gap > worst else worst
            metrics[f"{name}_bins"] = out
            if name == "group" and worst is not None and worst > GROUP_GAP:
                trig.append("group_gap")
    att = [r["attempts"] for r in succ]
    med = median(att) if att else None
    metrics["success_attempts_median"] = med
    if med is not None and med > ATTEMPT_MEDIAN:
        trig.append("attempts")
    total_attempts = sum(int(r.get("attempts") or 0) for r in rows)
    shape = sum(int(r.get("shape_audit_failed_attempts") or 0) for r in rows)
    metrics["skeleton_attempts_total"] = total_attempts
    metrics["shape_audit_failed_attempts"] = shape
    if total_attempts:
        sr = Fraction(shape, total_attempts)
        metrics["shape_audit_rate"] = float(sr)
        if sr > SHAPE_AUDIT_RATE:
            trig.append("shape_audit")
    else:
        metrics["shape_audit_rate"] = None
    return {"complete": bool(complete), "triggered": trig, "metrics": metrics}
