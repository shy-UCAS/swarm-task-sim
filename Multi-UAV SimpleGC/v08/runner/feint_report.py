"""佯动统计、检查点包装、实测事件、作业段与四意图配对（V8-18 指令 4.2–4.3、5.2、6、7.2–7.3；本项新增）。

检查点直接复用既有实现：只骨架 = skeleton_monitoring.skeleton_checkpoint（预期 200，不排除合同）；全量 =
joint_report.full_checkpoint（不排除合同）。**不调用** intrusion_report 的排除名单或直线回退阈值（指令 12.7）。
模块导入只依赖标准库与 NumPy；场景几何在函数内部惰性导入。
"""
from fractions import Fraction
from statistics import median

import numpy as np

LAYERS = ("warning", "alert")


def _frac(f):
    return None if f is None else f"{f.numerator}/{f.denominator}"


# ---------------------------------------------------------------- 检查点

def skeleton_checkpoint(records, *, expected_count=200):
    """包装 skeleton_monitoring.skeleton_checkpoint：全部 200 合同进入分母、无预登记排除、无直线回退门槛。"""
    from .skeleton_monitoring import skeleton_checkpoint as base
    out = base(list(records), expected_count=expected_count)
    out["metrics"]["excluded_from_rate"] = []
    return out


def full_checkpoint(records, frechet_blocks):
    """包装 joint_report.full_checkpoint：不排除合同；另报成功率分数与 Fréchet 有效对数。"""
    from .joint_report import full_checkpoint as base
    rows = list(records)
    out = base(rows, frechet_blocks)
    if rows:
        out["metrics"]["success_rate_fraction"] = _frac(Fraction(sum(bool(r["success"]) for r in rows), len(rows)))
    out["metrics"]["frechet_pairs"] = sum(len(b["distances_m"]) for b in frechet_blocks)
    out["metrics"]["excluded_from_rate"] = []
    return out


# ---------------------------------------------------------------- 实测成员事件（指令 4.2）

def measured_members(ctx, tracks, release_us, target_id):
    """每成员释放后第 0 段实测窗口（tau_us ≥ release 且 segment_index == 0）10 Hz 帧：用冻结圈层同义的 contour SDF ≤
    偏移判层，独立复算 warning/alert 进入与退出事件（进入 inside & ~prev，退出 ~inside & prev；首次退出 = 首次进入后
    第一个 False 帧）、末帧全部设施层、最深 protected SDF（整窗 signed_distance(protected).min()）。
    all_single：全体成员两层进入、退出次数均为 1。帧口径，不声称连续精确穿越时刻。"""
    from ..scene.exact import signed_distance
    tgt = ctx.facility_by_id[target_id]
    out = {}
    for m in sorted(tracks):
        tr = tracks[m]
        tau = np.asarray(tr.tau_us, np.int64)
        mask = (tau >= int(release_us[m])) & (np.asarray(tr.segment_index) == 0)
        times = tau[mask]
        xy = np.asarray(tr.p, float)[mask, :2]
        sd = np.asarray(signed_distance(tgt.geometry, xy), float).reshape(-1) if len(xy) else np.zeros(0)
        counts, exits, first_in, first_out = {}, {}, {}, {}
        for layer in LAYERS:
            inside = sd <= tgt.offsets[layer]
            prev = np.r_[False, inside[:-1]]
            starts = np.flatnonzero(inside & ~prev)
            ends = np.flatnonzero(~inside & prev)
            counts[layer], exits[layer] = int(len(starts)), int(len(ends))
            first_in[layer] = int(times[starts[0]]) if len(starts) else None
            after = ends[ends > starts[0]] if len(starts) else np.zeros(0, np.int64)
            first_out[layer] = int(times[after[0]]) if len(after) else None
        sp = np.asarray(signed_distance(tgt.layers["protected"], xy), float).reshape(-1) if len(xy) else np.zeros(0)
        end_out = bool(len(xy)) and all(float(signed_distance(f.geometry, xy[-1])) > f.offsets["warning"]
                                        for f in ctx.facilities)
        out[m] = {"entry_counts": counts, "exit_counts": exits, "first_entry_us": first_in,
                  "first_exit_us": first_out, "min_protected_sdf_m": float(sp.min()) if len(sp) else None,
                  "ended_outside_all_warning": end_out, "frames": int(mask.sum())}
    all_single = bool(out) and all(all(r["entry_counts"][k] == 1 and r["exit_counts"][k] == 1 for k in LAYERS)
                                   for r in out.values())
    return {"members": out, "all_single": all_single}


def result_block(P, meas):
    """result.json["feint"] 的白名单（指令 4.3）。"""
    return {"turn": {k: P["turn"][k] for k in ("kind", "side", "radius_m")},
            "members": {m: {k: v[k] for k in ("entry_counts", "first_entry_us", "first_exit_us",
                                              "min_protected_sdf_m")}
                        for m, v in sorted(meas["members"].items())}}


def formation_block(formation, repairs):
    """formation: {prior, start, realized, lateral_step_m, retreated}；retreated = 发生队形链退让或梯形步长缩减；
    loose → abreast 的映射本身不算宽度退让（mapped_from_loose 单列）。"""
    kinds = {r.get("kind") for r in (repairs or ())}
    return {"prior": formation.get("prior"), "start": formation.get("start"), "realized": formation.get("realized"),
            "lateral_step_m": formation.get("lateral_step_m"), "mapped_from_loose": formation.get("mapped_from_loose"),
            "retreated": bool(kinds & {"formation_retreat", "echelon_lateral_step"})}


def _median(xs):
    xs = [x for x in xs if x is not None]
    return median(xs) if xs else None


# ---------------------------------------------------------------- 可观测量（指令 7.2，诊断，无门槛）

def deformation_observables(ctx, plan, m, maps):
    """成员 m：真实形变支撑开始点的目标 alert SDF（预期 ≤ −10 m）、形变开始至核心开始的名义时长（纵列无形变为 None）、
    横向（A）与纵向支撑开始各自的名义时刻。名义时间用与掉头同一 np.interp(member_s, curve_s, t_abs) 映射。"""
    from ..scene.exact import signed_distance
    mm = plan.witnesses["member_map_feint"]["members"][m]
    sup = mm.get("support_member_s") or {}
    cs, ta = np.asarray(maps["curve_s"], float), np.asarray(maps["t_abs"], float)
    xy = np.asarray(plan.members[m].curve_xy, float)
    cum = np.r_[0.0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
    tgt = plan.witnesses["target_id"]
    alert = ctx.facility_by_id[tgt].layers["alert"]

    def at(s):
        return np.array([np.interp(s, cum, xy[:, 0]), np.interp(s, cum, xy[:, 1])])
    mask = np.asarray(mm["turn_mask"], bool)
    ms = np.asarray(mm["member_s"], float)
    core_s = float(ms[np.flatnonzero(mask)[0]]) if mask.any() else None
    col = sup.get("collapse")
    L = float((plan.proposal or {}).get("L_m") or 0.0)
    l_slot = float(mm.get("slot_longitudinal_m") or 0.0)
    lstar = float((plan.proposal or {}).get("l_star_m") or 0.0)
    no_deform = L == 0.0 and abs(lstar - abs(l_slot)) < 1e-12 and float(mm.get("slot_lateral_m") or 0.0) == 0.0
    out = {"support_start_member_s": None if col is None else col[0],
           "support_start_alert_sdf_m": None if col is None else float(signed_distance(alert, at(col[0]))),
           "core_start_member_s": core_s,
           "deform_to_core_s": None, "lateral_start_t_s": None, "longitudinal_start_t_s": None,
           "no_deformation": bool(no_deform)}
    if col is not None and core_s is not None and not no_deform:
        out["deform_to_core_s"] = float(np.interp(core_s, cs, ta) - np.interp(col[0], cs, ta))
    for k, name in (("collapse_lateral", "lateral_start_t_s"), ("collapse_longitudinal", "longitudinal_start_t_s")):
        v = sup.get(k)
        if v is not None:
            out[name] = float(np.interp(v[0], cs, ta))
    return out
