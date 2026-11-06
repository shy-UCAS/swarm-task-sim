"""突入统计、名单口径、实测事件（V8-17 指令 4.3、5.2、7.2–7.4；本项新增）。

名单（指令 5.2/7.2）：预登记不可行名单只有 o34_d3，**只**从成功率与人数/设施/初速档差的分母中排除（199）；
attempts 中位数、形状审计失败率、直线回退率、完成性、配对、失败类型与计时按各自对象重算，不整表过滤。
模块导入只依赖标准库与 NumPy；场景几何在函数内部惰性导入。
"""
from fractions import Fraction
from statistics import median

import numpy as np

KNOWN_INFEASIBLE = ("o34_d3",)
FALLBACK_MAX = Fraction(1, 2)            # C16 裁定 1 / 指令 5.3：成功骨架直线回退比例 > 50% 触发
LAYERS = ("warning", "alert", "protected")


def _frac(f):
    return None if f is None else f"{f.numerator}/{f.denominator}"


# ---------------------------------------------------------------- 只骨架检查点（指令 5.2–5.3）

def skeleton_checkpoint(records, *, expected_count=200, excluded=KNOWN_INFEASIBLE):
    """返回 {"complete", "triggered", "metrics"}。complete 按原始结果数量与唯一键判定（proven_infeasible 是已完成结果）。
    复用 skeleton_monitoring.skeleton_checkpoint 的统计算法，仅对成功率与人数档差使用排除名单后的行；
    attempts 中位数（全部成功骨架合同）、形状审计失败率（全部实际骨架 attempt；证书 attempts=0 不产生虚构 attempt）、
    直线回退率（全部成功骨架合同 curved=False）按原始行重算。等号不触发；比率用 Fraction；缺分母为 None。"""
    from .skeleton_monitoring import ATTEMPT_MEDIAN, SHAPE_AUDIT_RATE
    from .skeleton_monitoring import skeleton_checkpoint as base_checkpoint
    rows = list(records)
    excl = set(excluded)
    ids = [r.get("contract_id") for r in rows]
    incomplete = [r.get("contract_id") for r in rows if r.get("incomplete") or r.get("error")]
    complete = len(rows) == int(expected_count) and len(set(ids)) == len(ids) and not incomplete
    rate_rows = [r for r in rows if r.get("contract_id") not in excl]
    base = base_checkpoint(rate_rows, expected_count=len(rate_rows))
    trig = [t for t in base["triggered"] if t in ("success_rate", "group_gap")]
    bm = base["metrics"]
    metrics = {"contracts": len(rows), "expected": int(expected_count), "incomplete": incomplete,
               "excluded_from_rate": sorted(excl & set(ids)),
               "rate_denominator": len(rate_rows), "successes_rate_rows": bm.get("successes"),
               "success_rate": bm.get("success_rate"), "success_rate_fraction": bm.get("success_rate_fraction"),
               "group_bins": bm.get("group_bins"), "facility_bins": bm.get("facility_bins"),
               "speed_bins": bm.get("speed_bins")}
    succ_raw = [r for r in rows if r.get("success")]
    metrics["successes_raw"] = len(succ_raw)
    metrics["success_rate_raw_fraction"] = _frac(Fraction(len(succ_raw), len(rows))) if rows else None
    att = [int(r["attempts"]) for r in succ_raw]
    med = median(att) if att else None
    metrics["success_attempts_median"] = med
    if med is not None and med > ATTEMPT_MEDIAN:
        trig.append("attempts")
    total = sum(int(r.get("attempts") or 0) for r in rows)
    shape = sum(int(r.get("shape_audit_failed_attempts") or 0) for r in rows)
    metrics["skeleton_attempts_total"] = total
    metrics["shape_audit_failed_attempts"] = shape
    if total:
        sr = Fraction(shape, total)
        metrics["shape_audit_rate"] = float(sr)
        metrics["shape_audit_rate_fraction"] = _frac(sr)
        if sr > SHAPE_AUDIT_RATE:
            trig.append("shape_audit")
    else:
        metrics["shape_audit_rate"] = None
        metrics["shape_audit_rate_fraction"] = None
    straight = [r for r in succ_raw if not r.get("curved")]
    reasons = {}
    for r in straight:
        reasons[str(r.get("fallback_reason"))] = reasons.get(str(r.get("fallback_reason")), 0) + 1
    fb = {"successes": len(succ_raw), "straight": len(straight), "reasons": dict(sorted(reasons.items())),
          "rate": None, "rate_fraction": None}
    if succ_raw:
        fr = Fraction(len(straight), len(succ_raw))
        fb.update(rate=float(fr), rate_fraction=_frac(fr))
        if fr > FALLBACK_MAX:
            trig.append("straight_fallback")
    metrics["fallback"] = fb
    return {"complete": bool(complete), "triggered": trig, "metrics": metrics}


# ---------------------------------------------------------------- 实测成员事件（指令 4.2–4.3）

def measured_members(ctx, tracks, release_us, target_id):
    """每成员释放后第 0 段实测窗口（tau_us ≥ release 且 segment_index == 0）的 10 Hz 帧：几何层内 = 目标 contour SDF ≤
    该层偏移；三层进入次数 = False→True 次数（首帧 True 也计一次）；首次进入时刻 = 第一个 True 的整数微秒。
    end_contour_m / min_contour_m 为该窗口末帧/最小 contour SDF。帧口径，不声称连续精确穿越时刻。"""
    from ..scene.exact import signed_distance
    tgt = ctx.facility_by_id[target_id]
    out = {}
    for m in sorted(tracks):
        tr = tracks[m]
        tau = np.asarray(tr.tau_us, np.int64)
        mask = (tau >= int(release_us[m])) & (np.asarray(tr.segment_index) == 0)
        times = tau[mask]
        xy = np.asarray(tr.p, float)[mask, :2]
        sdf = np.asarray(signed_distance(tgt.geometry, xy), float).reshape(-1) if len(xy) else np.zeros(0)
        counts, first = {}, {}
        for layer in LAYERS:
            inside = sdf <= tgt.offsets[layer]
            starts = np.flatnonzero(inside & ~np.r_[False, inside[:-1]])
            counts[layer] = int(len(starts))
            first[layer] = int(times[starts[0]]) if len(starts) else None
        out[m] = {"entry_counts": counts, "first_entry_us": first,
                  "end_contour_m": float(sdf[-1]) if len(sdf) else None,
                  "min_contour_m": float(sdf.min()) if len(sdf) else None, "frames": int(mask.sum())}
    all_single = bool(out) and all(all(c == 1 for c in r["entry_counts"].values()) for r in out.values())
    return {"members": out, "all_single": all_single}


# ---------------------------------------------------------------- 全量检查点（指令 7.2）

def full_checkpoint(records, frechet_blocks, *, excluded=KNOWN_INFEASIBLE):
    """保留 joint_report.full_checkpoint 的数学口径；**仅**成功率与人数/设施/初速档差使用排除名单后的行（199）。
    post 失败中位数（全部主合同成功项）、Fréchet（多样性可比较成功对）不按名单过滤；另报原始 200 口径的成功率。"""
    from .joint_report import full_checkpoint as base_full, _median_or_none, _post_median
    rows = list(records)
    excl = set(excluded)
    rate_rows = [r for r in rows if r.get("contract_id") not in excl]
    base = base_full(rate_rows, frechet_blocks)
    trig = [t for t in base["triggered"] if t in ("success_rate", "facility_gap", "speed_gap", "group_gap", "frechet")]
    metrics = dict(base["metrics"])
    metrics["rate_denominator"] = len(rate_rows)
    metrics["excluded_from_rate"] = sorted(excl & {r.get("contract_id") for r in rows})
    if rate_rows:
        f = Fraction(sum(bool(r["success"]) for r in rate_rows), len(rate_rows))
        metrics["success_rate_fraction"] = _frac(f)
    if rows:
        metrics["success_rate_raw_fraction"] = _frac(Fraction(sum(bool(r["success"]) for r in rows), len(rows)))
    succ = [r for r in rows if r["success"]]
    att, undetermined = _post_median(succ)
    metrics["post_optimization_failures_median"] = att
    metrics["attempts_undetermined"] = undetermined
    metrics["success_attempts_median_diagnostic"] = _median_or_none(r["attempts"] for r in succ)
    if att is not None and att > 0:
        trig.append("attempts")
    metrics["frechet_pairs"] = sum(len(b["distances_m"]) for b in frechet_blocks)
    return {"triggered": trig, "metrics": metrics}
