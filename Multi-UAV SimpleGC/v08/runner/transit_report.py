"""过境报告辅助（V8-16 指令 7.2–7.4；本项新增）：阶段时长与速度、穿越段编组参考（Fréchet 输入）、监视—过境逐格配对。
只作诊断，不改标签、段核验窗口或任何门禁。不导入 shapely。
"""
import math

import numpy as np

FRECHET_SPACING_M = 5.0          # r5 14.3 / C12 第 7 条
TRANSIT_PHASES = ("transit_ingress", "transit_crossing", "transit_egress")


# ---------------------------------------------------------------- 阶段

def member_phase_times(res, m, *, intent="transit"):
    """成员 m 的 (release_s, t_entry, t_exit, end_s)：entry/exit 为该成员骨架曲线穿越目标 warning 的精确弧长
    （构造时 crossing_analysis 给出、保存在 member_map_transit）映射到名义时间；不是 LP 起止点或中心线入圈时刻。
    V8-17：intent="intrusion" 时返回 (release_s, t_warning_entry, end_s)，入点取 member_map_intrusion。"""
    plan, opt = res["plan"], res["opt"]
    if intent == "intrusion":
        mm = plan.witnesses["member_map_intrusion"]["members"][m]
        maps = opt["maps"][m]
        cs, ta = np.asarray(maps["curve_s"], float), np.asarray(maps["t_abs"], float)
        ref = {r.member_id: r for r in opt["references"]}[m]
        return float(ref.release_s), float(np.interp(float(mm["entry_member_s"]), cs, ta)), float(ref.end_s)
    mm = plan.witnesses["member_map_transit"]["members"][m]
    maps = opt["maps"][m]
    cs, ta = np.asarray(maps["curve_s"], float), np.asarray(maps["t_abs"], float)
    ref = {r.member_id: r for r in opt["references"]}[m]
    t_in = float(np.interp(float(mm["entry_member_s"]), cs, ta))
    t_out = float(np.interp(float(mm["exit_member_s"]), cs, ta))
    return float(ref.release_s), t_in, t_out, float(ref.end_s)


def phase_durations(res, *, intent="transit"):
    """逐成员三段移动时长（相加 = travel_s），另列共同预保持 20 s、成员 release delay、末端保持；合同含保持跨度。
    V8-17：intrusion 为 intrusion_ingress_s（释放→warning 入点）、intrusion_inside_s（入点→移动终点）、travel_s、
    release_s、release_delay_s、closure_residual_s（两段相加减 travel_s，仅浮点舍入量级）。"""
    from ..motion.optimize import physical_limits
    plan = res["plan"]
    out = {}
    if intent == "intrusion":
        for m in sorted(plan.members):
            r, a, e = member_phase_times(res, m, intent=intent)
            out[m] = {"intrusion_ingress_s": a - r, "intrusion_inside_s": e - a, "travel_s": e - r, "release_s": r,
                      "release_delay_s": float(plan.members[m].release_delay_s),
                      "closure_residual_s": (a - r) + (e - a) - (e - r)}
        return out
    for m in sorted(plan.members):
        r, a, b, e = member_phase_times(res, m)
        out[m] = {"transit_ingress_s": a - r, "transit_crossing_s": b - a, "transit_egress_s": e - b,
                  "travel_s": e - r, "release_s": r, "release_delay_s": float(plan.members[m].release_delay_s),
                  "closure_residual_s": (a - r) + (b - a) + (e - b) - (e - r)}
    return out


def phase_diagnostics_transit(res):
    """逐成员 过境进场 / 穿越 / 撤离 三阶段的参考/优化/实测速度与沿迹偏离（复用 phase_metrics 原口径）。
    V8-17：机械提取为 phase_diagnostics(res, intent="transit") 的包装。"""
    return phase_diagnostics(res, intent="transit")


def _terminal_decel(t_nodes, v_nodes, t0):
    """名义末端减速段（诊断）：从末节点向前，取连续严格递减至终点 0 速度的最后一段节点区间；前一个非递减区间终止
    扫描。返回 {t_start_s, t_end_s, duration_s, v_start_m_s, n_nodes}，不存在时 None。"""
    v = np.asarray(v_nodes, float)
    if len(v) < 2 or v[-1] != 0.0:
        return None
    k = len(v) - 1
    while k - 1 >= 0 and v[k - 1] > v[k]:
        k -= 1
    if k == len(v) - 1:
        return None
    tn = np.asarray(t_nodes, float) + float(t0)
    return {"t_start_s": float(tn[k]), "t_end_s": float(tn[-1]), "duration_s": float(tn[-1] - tn[k]),
            "v_start_m_s": float(v[k]), "n_nodes": int(len(v) - k)}


def _brake_start(t, speed):
    """优化/实测样本上从末端向前的最后一段严格递减速度区间起点（诊断，不是全部制动的定义）。"""
    s = np.asarray(speed, float)
    if len(s) < 2:
        return None
    k = len(s) - 1
    while k - 1 >= 0 and s[k - 1] > s[k]:
        k -= 1
    return None if k == len(s) - 1 else int(k)


def phase_diagnostics(res, *, intent="transit", ctx=None):
    """逐成员阶段速度与沿迹偏离（复用 phase_metrics 原口径）。transit：进场 / 穿越 / 撤离；V8-17 intrusion：
    ingress（释放→warning 入点）/ inside（入点→移动终点，闭）及终端减速诊断（名义末端严格递减段；优化与实测制动开始
    所在圈层与到保护边界的有符号距离，供核查附录裁定 1 的推论，不设门槛）。"""
    from ..diagnostics.monitoring_skeleton import phase_metrics
    plan, opt = res["plan"], res["opt"]
    refs = {r.member_id: r for r in opt["references"]}
    sol = opt["solution"].references
    out = {}
    for m in sorted(sol):
        maps = opt["maps"][m]
        nom = maps["nominal"]
        cs, ta = np.asarray(maps["curve_s"], float), np.asarray(maps["t_abs"], float)
        ref = refs[m]
        if intent == "intrusion":
            r, t_in, e = member_phase_times(res, m, intent=intent)
        else:
            r, t_in, t_out, e = member_phase_times(res, m)
        tr = res["tracks"][m]
        t = np.asarray(tr.tau_us, np.int64) / 1e6
        sel = (t >= ref.release_s - 1e-9) & (t <= ref.end_s + 1e-9)
        t = t[sel]
        rp, rv, _ = ref.pva(t)
        rp, rv = np.asarray(rp, float).reshape(-1, 2), np.asarray(rv, float).reshape(-1, 2)
        s_now = np.interp(t, ta, cs)
        tan_c = np.asarray(nom.curve.tangent, float)
        idx = np.clip(np.searchsorted(cs, s_now, side="right") - 1, 0, len(tan_c) - 1)
        sp = np.hypot(rv[:, 0], rv[:, 1])
        tan = np.where((sp > 0.0)[:, None], rv / np.maximum(sp, np.finfo(float).tiny)[:, None], tan_c[idx])
        op, ov = sol[m].evaluate(t, 0), sol[m].evaluate(t, 1)
        mpv, mvv = np.asarray(tr.p, float)[sel, :2], np.asarray(tr.v, float)[sel, :2]
        if intent == "intrusion":
            bounds = {"intrusion_ingress": (r, t_in), "intrusion_inside": (t_in, e, True)}
            got = phase_metrics(t, rp, rv, op, ov, mpv, mvv, bounds, tan)
            out[m] = {"phases": got, "t_entry_s": t_in,
                      "release_offset_s": float(res["release_us"][m]) / 1e6 - float(ref.release_s),
                      "terminal_deceleration": _terminal_deceleration(ctx, plan, nom, t, op, ov, mpv, mvv)}
            continue
        bounds = {"transit_ingress": (r, t_in), "transit_crossing": (t_in, t_out), "transit_egress": (t_out, e, True)}
        got = phase_metrics(t, rp, rv, op, ov, mpv, mvv, bounds, tan)
        out[m] = {"phases": got, "t_entry_s": t_in, "t_exit_s": t_out,
                  "release_offset_s": float(res["release_us"][m]) / 1e6 - float(ref.release_s)}
    return out


def _terminal_deceleration(ctx, plan, nom, t, op, ov, mp, mv):
    nominal = _terminal_decel(nom.t_nodes, nom.v, nom.release_s)
    out = {"nominal": nominal, "scope": "诊断：名义末端严格递减段；优化/实测为 10 Hz 样本末端严格递减段起点"}
    tgt = None if ctx is None else ctx.facility_by_id[plan.witnesses["target_id"]]
    for name, p, v in (("optimized", op, ov), ("measured", mp, mv)):
        if p is None or v is None:
            out[name] = None
            continue
        p, v = np.asarray(p, float), np.asarray(v, float)
        k = _brake_start(t, np.hypot(v[:, 0], v[:, 1]))
        if k is None:
            out[name] = None
            continue
        rec = {"t_start_s": float(t[k]), "duration_s": float(t[-1] - t[k]), "v_start_m_s": float(np.hypot(*v[k])),
               "xy": [float(p[k, 0]), float(p[k, 1])]}
        if tgt is not None:
            from ..motion.nominal_checks import layer_levels
            lv, sd = layer_levels(tgt, p[k][None])
            rec["layer"] = int(np.asarray(lv).reshape(-1)[0])
            rec["protected_signed_m"] = float(np.asarray(sd).reshape(-1)[0]) - float(tgt.offsets["protected"])
        out[name] = rec
    return out


# ---------------------------------------------------------------- 穿越段编组参考（Fréchet）

def _exact_crossings(xy, geom):
    """折线与凸 warning 的精确交点：在顶点有符号距离变号的线段上用精确直线次水平集求交。返回 [(s, 方向)]。"""
    from ..motion.transit_chords import line_sublevel
    from ..scene.exact import signed_distance
    P = np.asarray(xy, float)
    sd = np.asarray(signed_distance(geom, P), float)
    cum = np.r_[0.0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    out = []
    for k in np.flatnonzero((sd[:-1] > 0) != (sd[1:] > 0)):
        a, b = P[k], P[k + 1]
        L = float(np.hypot(*(b - a)))
        if L <= 0.0:
            continue
        u = (b - a) / L
        iv = line_sublevel(geom, a, u, 0.0)
        if iv is None:
            continue
        x = iv[0] if sd[k] > 0 else iv[1]
        x = min(max(x, 0.0), L)
        out.append((float(cum[k] + x), "in" if sd[k] > 0 else "out"))
    return out, cum


def _cut_resample(xy, s_in, s_out, spacing):
    from ..diagnostics.monitoring_skeleton import patrol_resample
    cum = np.r_[0.0, np.cumsum(np.hypot(*np.diff(np.asarray(xy, float), axis=0).T))]
    return patrol_resample(cum, xy, s_in, s_out, spacing_m=spacing)


def group_reference_curves(ctx, group, res, *, intent="transit"):
    """c_after(s) = c_before(s) + (1/N)Σ_i[p_i^opt(t_i(s)) − p_i^ref(t_i(s))]（沿用 joint_monitoring.group_reference_curves
    的编组位移定义；t_i(s) 由保存的 member_map_transit（reference_s → member_s）与该成员名义弧长—时间给出）。
    先在完整 collect → terminal 编组曲线上构造 before/after，各自与目标 warning 精确求交、截出唯一的单次穿越段，
    再分别按自身几何弧长 5 m 重采样。返回 {"before", "after", "info"}；不能唯一截出时 before/after 为 None 并给原因。
    V8-17 指令 7.3：intrusion 用 member_map_intrusion（成员域外取端点值，与 np.interp 边界行为一致），唯一目标 warning
    入点（方向只 ["in"]）至编组曲线末端截出作业段。"""
    from ..motion.nominal import member_nominal
    from ..motion.skeleton import NominalPVA, reference_guidance
    plan = res["plan"]
    tgt = plan.witnesses["target_id"]
    geom = ctx.facility_by_id[tgt].layers["warning"]
    ref_xy = np.asarray(plan.reference_xy, float)
    S = float(plan.anchors["collect_s"]) + np.r_[0.0, np.cumsum(np.hypot(*np.diff(ref_xy, axis=0).T))]
    mm = plan.witnesses["member_map_intrusion" if intent == "intrusion" else "member_map_transit"]["members"]
    G = reference_guidance()
    disp = np.zeros_like(ref_xy)
    opt = res["opt"]["solution"].references
    for m in sorted(plan.members):
        mp = mm[m]
        sm = np.interp(S, np.asarray(mp["reference_s"], float), np.asarray(mp["member_s"], float))
        nom = member_nominal(plan.members[m], guidance=G)
        f = NominalPVA(nom)
        t = np.interp(sm, nom.curve.s, nom.t_nodes) + nom.release_s
        disp += opt[m].evaluate(t) - np.asarray(f(t)[0])
    after = ref_xy + disp / len(plan.members)
    info = {}
    curves = {}
    for name, xy in (("before", ref_xy), ("after", after)):
        cr, cum = _exact_crossings(xy, geom)
        dirs = [d for _, d in cr]
        info[name] = {"crossings": dirs, "length_m": float(cum[-1])}
        if dirs != (["in"] if intent == "intrusion" else ["in", "out"]):
            info[name]["na_reason"] = f"not_single_crossing:{dirs}"
            curves[name] = None
            continue
        s_in, s_out = (cr[0][0], float(cum[-1])) if intent == "intrusion" else (cr[0][0], cr[1][0])
        seg = _cut_resample(xy, s_in, s_out, FRECHET_SPACING_M)
        curves[name] = seg
        info[name].update(cut_length_m=float(s_out - s_in), start_xy=seg[0].tolist(), end_xy=seg[-1].tolist(),
                          n_points=int(len(seg)))
    return {"before": curves["before"], "after": curves["after"], "info": info}


def frechet_blocks(div_rows, key="curve_after", *, intent="transit"):
    """每族成功且可比较的 branch 两两离散 Fréchet；之后由 joint_report.pooled_frechet 除以横向间距合并取中位数。"""
    from ..diagnostics.diversity import discrete_frechet
    from ..diagnostics.monitoring_skeleton import endpoint_distances
    fam = {}
    for r in div_rows:
        fam.setdefault(r["family_id"], []).append(r)
    blocks = []
    for fid, rs in sorted(fam.items()):
        rs = sorted(rs, key=lambda x: x["branch"])
        ok = [np.asarray(r[key], float) for r in rs if r.get("success") and r.get(key) is not None]
        pairs = [(i, j) for i in range(len(ok)) for j in range(i + 1, len(ok))]
        blocks.append({"family_id": fid, "spacing_m": float(rs[0].get("lateral_spacing_m") or 0.0) or 1.0,
                       "distances_m": [float(discrete_frechet(ok[i], ok[j])) for i, j in pairs],
                       "attempted": len(rs), "success": sum(bool(r.get("success")) for r in rs),
                       "comparable": len(ok), "endpoint_m": [endpoint_distances(ok[i], ok[j]) for i, j in pairs],
                       "na_reasons": [r.get("frechet_na") for r in rs if r.get("success") and r.get(key) is None],
                       "scope": "intrusion_warning_to_terminal_v17" if intent == "intrusion"
                       else "transit_crossing_v16"})
    return blocks


# ---------------------------------------------------------------- 监视—过境逐格配对

COMMON_FIELDS = ("group_id", "member_ids", "target_id", "initial_speed_m_s", "formation_prior", "group_size",
                 "facility_count")


def paired_rows(monitor_skeleton, transit_skeleton, monitor_full, transit_full):
    """以 (family_id, draw_index) 做 200 键外连接（branch=None），不只内连接双方成功者。缺基线字段记 None 并列缺项。"""
    from .joint_report import group_bin, speed_bin

    def idx(rows):
        return {(r["family_id"], int(r["draw_index"])): r for r in rows or [] if r.get("branch") is None}
    ms, ts, mf, tf = idx(monitor_skeleton), idx(transit_skeleton), idx(monitor_full), idx(transit_full)
    keys = sorted(set(ms) | set(ts) | set(mf) | set(tf), key=lambda k: (k[0], k[1]))
    out = []
    for k in keys:
        a, b, c, d = ms.get(k), ts.get(k), mf.get(k), tf.get(k)
        base = c or a or d or b
        row = {"family_id": k[0], "draw_index": k[1], "contract_id": base.get("contract_id"),
               "monitor_skeleton_success": None if a is None else bool(a.get("success")),
               "transit_skeleton_success": None if b is None else bool(b.get("success")),
               "monitor_full_success": None if c is None else bool(c.get("success")),
               "transit_full_success": None if d is None else bool(d.get("success")),
               "monitor_skeleton_attempts": None if a is None else a.get("attempts"),
               "transit_skeleton_attempts": None if b is None else b.get("attempts"),
               "monitor_full_attempts": None if c is None else c.get("attempts"),
               "transit_full_attempts": None if d is None else d.get("attempts"),
               "monitor_post_opt_failures": None if c is None else c.get("post_optimization_failures"),
               "transit_post_opt_failures": None if d is None else d.get("post_optimization_failures"),
               "monitor_first_failed_stage": _first_fail(c), "transit_first_failed_stage": _first_fail(d),
               "monitor_nominal_duration_s": None if c is None else c.get("nominal_duration_s"),
               "transit_nominal_duration_s": None if d is None else d.get("nominal_duration_s")}
        src = base
        row["group_size"] = src.get("group_size")
        row["facility_count"] = src.get("facility_count")
        row["initial_speed_m_s"] = src.get("initial_speed_m_s")
        row["group_bin"] = None if src.get("group_size") is None else group_bin(src["group_size"])
        row["speed_bin"] = None if src.get("initial_speed_m_s") is None else speed_bin(src["initial_speed_m_s"])
        diffs, missing = [], []
        for f in COMMON_FIELDS:
            mv = (c or a or {}).get(f)
            tv = (d or b or {}).get(f)
            if mv is None or tv is None:
                missing.append(f)
            elif mv != tv:
                diffs.append(f)
        row["common_field_diffs"] = diffs
        row["missing_fields"] = missing
        out.append(row)
    return out


def _first_fail(r):
    if r is None:
        return None
    for a in r.get("attempt_log") or []:
        if not a.get("ok"):
            st = a.get("stage")
            if st == "skeleton" and a.get("skeleton_stage"):
                return f"skeleton:{a['skeleton_stage']}"
            return st
    return None


def four_cell(rows, key_m="monitor_full_success", key_t="transit_full_success", by=None):
    """四格计数（总 n、两边成功、仅监视、仅过境、两边失败）；by 为分档字段名。"""
    groups = {}
    for r in rows:
        g = "all" if by is None else r.get(by)
        groups.setdefault(g, []).append(r)
    out = {}
    for g, rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
        both = sum(1 for r in rs if r[key_m] and r[key_t])
        only_m = sum(1 for r in rs if r[key_m] and r[key_t] is False)
        only_t = sum(1 for r in rs if r[key_m] is False and r[key_t])
        neither = sum(1 for r in rs if r[key_m] is False and r[key_t] is False)
        out[str(g)] = {"n": len(rs), "both": both, "only_monitor": only_m, "only_transit": only_t, "neither": neither,
                       "unknown": len(rs) - both - only_m - only_t - neither}
    return out
