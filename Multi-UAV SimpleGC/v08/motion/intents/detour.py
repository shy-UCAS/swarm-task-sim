"""V8-21 迂回单段：一次 attempt 的骨架构造（指令 3.1–3.6；裁定 1–3）。

抽签顺序（shape 流，只在本分支执行）：0 队形与方位段（无 RNG）→ 1 σ → 2 β_in、β_out → 3 Σ_hi（裁定 1：无 RNG，
min(段跨度 − 2°, 350°)）→ 4 Σ → 5 (段, 起始行) → 6 K、K 个分位数 → 7 进、出额外延长 → 8 成员槽位排列。
connect 流只供冻结 route_to_slot 内部候选，speed 流沿公共速度先验。任何检查失败都原样结束本 attempt（不重抽 β/Σ/
起始行/K、不换队形）；唯一 20 次预算由运行器管理。构造后用 lane_sweep_window 复核全部车道扫角（裁定 1）。
"""
import math
import time
from dataclasses import replace

import numpy as np

from ...config import load_config
from ...contract.monitoring import Failure, MemberPlan, SegmentPlan
from ...sampler.keys import RngKey, rng_for
from ...scene.exact import polyline_clearance, signed_distance
from ...sim.guidance import make_curve, nominal_time, speed_profile
from ...sim.kernel import member_config
from ...sim.types import SimContractError
from .. import detour_numeric as DN
from ..connect import crossing_analysis
from ..detour_config import load_detour_candidate
from ..detour_geometry import (DetourRouteView, band_for, component_containing, detour_constraints,
                               lane_band_violations, lane_sweep_window)
from ..formation import MIN_LATERAL_STEP_M, derive_members, formation_slots, make_reference, mapped_start, \
    retreat_chain
from ..nominal import release_us, sample_nominal
from ..path import PathError, kappa_limit, periodic_radius_derivs, sample_primitives
from ..shared_routes import plan_starts
from ..skeleton import reference_guidance, width_then_build
from ..speed import draw_speed_events, map_speed_events
from .monitoring import _key_dict, _release_delays_ref

NODE_TOL_M = 1e-6
FAR_M = 5.0
STAGES = ("detour_band", "detour_shape", "detour_route")

_LAST_TIMING = {}


def last_attempt_timing():
    """本进程最近一次迂回 propose_and_build 的分阶段墙钟（遥测，不进入确定性载荷）。"""
    return dict(_LAST_TIMING)


def _tick(T, name, t0):
    T[name] = T.get(name, 0.0) + (time.perf_counter() - t0)


def _reject(reason, stage, witness):
    return Failure("candidate_rejected", reason, stage, witness, None)


def _fail(stage, subreason, reason, key, extra=None, proposal=None):
    w = {"stage": stage, "subreason": subreason, "shape_audit_failed": stage == "detour_shape", **(extra or {})}
    return SegmentPlan(members={}, reference_xy=(), nominal_duration_s=math.nan, anchors={}, repairs=(),
                       failure=_reject(reason, stage, w), proposal=proposal,
                       business_key=None if key is None else _key_dict(key))


def final_failure(ctx, group, task, attempt_records):
    """全部 attempt 都是 detour_band（所有允许队形都没有足够方位段）→ approx_empty（有限网格与保守证书，不证明连续
    不可行）；本项没有精确不可能证书，不报 proven_infeasible；其余 budget_exhausted。"""
    stages = {r["stage"] for r in attempt_records}
    n = len(attempt_records)
    if n and stages == {"detour_band"}:
        return Failure("approx_empty", "全部 attempt 在所有允许队形下近距离带都没有足够长的方位段（有限网格与局部证书）；"
                                       "不证明连续可行域为空", "detour_band", {"attempts": n}, None)
    return Failure("budget_exhausted", f"{n} 次随机构造用完预算", "random_construction",
                   {"attempts": n, "stages": sorted(str(s) for s in stages)}, None)


def draw_summary(P, formation):
    d = (P or {}).get("draw") or {}
    return {"intent": "detour", "formation": formation, **{k: d.get(k) for k in (
        "sigma", "sigma_deg", "start_phi_rad", "K", "beta_in_deg", "beta_out_deg", "sigma_hi_deg", "component_id",
        "entry_extra_m", "exit_extra_m", "entry_exit_contribution_deg")}}


def _rng(key, purpose, trace=None):
    r = rng_for(RngKey(key.family_id, key.draw, purpose, mission=key.mission, branch=key.branch, group=key.group,
                       segment=key.segment, attempt=key.attempt))
    return r if trace is None else DN.TraceRng(r, purpose, trace)


def _f(x):
    return None if x is None else float(x)


def _xy(p):
    return None if p is None else [float(p[0]), float(p[1])]


# ---------------------------------------------------------------- 队形（指令 3.1；裁定 3）

def _formation_probe(band, group, fam, order, need, steps):
    def probe(name, step):
        slots = formation_slots(group, fam, None, formation=name, lateral_step_m=step, order=order)
        H = float(slots.max_lateral_m)
        seg = band.segments(H)
        ok = bool(seg["periodic"] or seg["max_span_deg"] >= need)
        steps.append({"formation": name, "lateral_step_m": _f(step), "feasible": ok,
                      "max_arc_deg": float(seg["max_span_deg"])})
        return {"slots": slots, "seg": seg, "H": H, "lateral_step_m": step} if ok else None
    return probe


def _echelon(probe, group, b):
    got = probe("echelon", b)
    if got is not None:
        return got
    n = len(group.member_ids)
    if n < 2:
        return None
    best = probe("echelon", MIN_LATERAL_STEP_M)
    if best is None:
        return None
    lo, hi = MIN_LATERAL_STEP_M, b
    tol = 2.0 / (n - 1)
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        res = probe("echelon", mid)
        if res is not None:
            lo, best = mid, res
        else:
            hi = mid
    return best


# ---------------------------------------------------------------- 主入口

def propose_and_build(ctx, group, task, states, key, *, trace=None):
    T = {}
    _LAST_TIMING.clear()
    t_all = time.perf_counter()
    try:
        return _propose(ctx, group, task, states, key, T, trace)
    finally:
        T["attempt_s"] = time.perf_counter() - t_all
        _LAST_TIMING.update(T)


def _propose(ctx, group, task, states, key, T, trace):
    C = load_detour_candidate()
    G = load_config("detour").values
    M = load_config("monitoring").values
    Cv = C.values
    t0 = time.perf_counter()
    cons = detour_constraints(ctx, task, C)
    band = band_for(ctx, cons)
    _tick(T, "band_s", t0)
    fam = ctx.family
    order0 = tuple(sorted(group.member_ids))
    b = float(fam.lateral_spacing_m)
    need = float(Cv["min_sweep_deg"]) + float(G["sweep_margin_deg"]) + float(G["arc_edge_guard_deg"])
    steps = []
    probe = _formation_probe(band, group, fam, order0, need, steps)
    chain = retreat_chain(mapped_start(group.formation_prior))
    t0 = time.perf_counter()

    def width_probe(name):
        if name == "echelon":
            return _echelon(probe, group, b)
        return probe(name, None)

    holder = {}

    def build(name, payload):
        holder["payload"] = payload
        return payload

    width_then_build(chain, width_probe, build)
    _tick(T, "formation_s", t0)
    if "payload" not in holder:
        return _fail("detour_band", "detour_band", "所有允许队形下近距离带都没有足够长的方位段（approx_empty 查询）", key,
                     {"formation_steps": steps, "need_span_deg": need})
    return _build(ctx, group, task, states, key, T, trace, C, G, M, cons, band, holder["payload"], steps, b)


def _build(ctx, group, task, states, key, T, trace, C, G, M, cons, band, payload, steps, b):
    from .. import monitoring_band as MB
    Cv = C.values
    fam = ctx.family
    P = ctx.params
    spacing = P["curve_spacing_m"]
    slots0, seg, H = payload["slots"], payload["seg"], payload["H"]
    rng = _rng(key, "shape", trace)
    crng = _rng(key, "connect", trace)
    draw = {"attempt": int(key.attempt)}
    base_extra = {"formation_steps": steps}

    def fail(stage, sub, reason, extra=None):
        return _fail(stage, sub, reason, key, {**base_extra, "draw": dict(draw), **(extra or {})},
                     proposal={"candidate": _cand(C), "draw": dict(draw)})

    # 1–2：方向与两个 β
    sigma = (-1, 1)[int(rng.integers(0, 2))]
    draw["sigma"] = int(sigma)
    beta_in = float(rng.uniform(0.0, float(G["beta_max_deg"])))
    beta_out = float(rng.uniform(0.0, float(G["beta_max_deg"])))
    draw.update(beta_in_deg=beta_in, beta_out_deg=beta_out)
    # 3：Σ_hi（无 RNG；裁定 1）
    periodic = bool(seg["periodic"])
    s_hi = DN.sigma_upper(seg["max_span_deg"], G, periodic=periodic)
    s_lo = float(Cv["min_sweep_deg"]) + float(G["sweep_margin_deg"])
    draw["sigma_hi_deg"] = float(s_hi)
    if not s_hi >= s_lo:
        return fail("detour_band", "detour_band", f"Σ 可行区间为空：[{s_lo}, {s_hi}]")
    # 4：Σ
    Sigma = float(rng.uniform(s_lo, s_hi))
    draw["sigma_deg"] = Sigma
    # 5：(段, 起始行)
    L = DN.rows_needed(Sigma)
    starts = DN.start_candidates(seg["segments"], L, periodic=periodic)
    if not starts:
        return fail("detour_band", "detour_band", f"没有放得下 Σ={Sigma:.3f}° 的起始行")
    sid, k0 = starts[int(rng.integers(0, len(starts)))]
    rows = np.arange(k0, k0 + L)
    phi0_deg = float(k0) if sigma > 0 else float(k0 + L - 1)
    phi1_deg = phi0_deg + sigma * Sigma
    phi0, phi1 = math.radians(phi0_deg), math.radians(phi1_deg)
    draw.update(start_phi_rad=phi0, component_id=int(sid), row_ids=[int(r) for r in rows])
    # 6：K 与分位数
    K = int(rng.integers(int(M["spline_basis_min"]), int(M["spline_basis_max"]) + 1))
    v = rng.random(K)
    z = MB.logit_from_quantiles(v)
    draw.update(K=K, logit_quantiles=[float(x) for x in v])
    # 弧证书与 LP（A_curv = A；裁定 12.2 接受）
    m = rows % 360
    A, B = MB._clamped_windows(seg["tl"][m], seg["tu"][m], False)
    kappa_star = kappa_limit(spacing, load_config("guidance").values["max_turn_per_chord_rad"])
    r_turn = float(load_config("joint_opt").values["buffer_turn_factor"]) * float(M["turn_u_min_m"])
    kmax = MB.kappa_max(H, kappa_star, r_turn)
    tgt, _ = MB.lp_targets(rows, A, B, z)
    t0 = time.perf_counter()
    lp = MB.shape_lp(rows, A, B, A, kmax=kmax, periodic=False, target=tgt, M=MB.LP_CONTROLS)
    _tick(T, "lp_s", t0)
    band_rec = {"center_xy": _xy(band.center), "r_star_m": band.r_star, "q_m": band.q, "eta_m": band.eta,
                "half_span_m": float(H), "component_id": int(sid), "row_ids": [int(r) for r in rows],
                "raw_lo_m": [_f(band.lo[j]) for j in m], "raw_hi_m": [_f(band.hi[j]) for j in m],
                "tube_lo_m": [_f(seg["tl"][j]) for j in m], "tube_hi_m": [_f(seg["tu"][j]) for j in m],
                "A_m": [float(x) for x in A], "B_m": [float(x) for x in B], "threshold_m": float(seg["threshold_m"])}
    lp_rec = {"controls": MB.LP_CONTROLS, "kappa_max": float(kmax), "status": lp["status"], "objective": lp["objective"],
              "rho0_m": None, "coefficients_m": None, "max_residual": None, "exact_curvature": None}
    T["lp_message"] = lp["message"]
    base_extra.update(band=band_rec)
    if not lp["feasible"]:
        return fail("detour_shape", "lp_infeasible", f"弧上曲率 LP 无解（status={lp['status']}）",
                    {"lp_status": lp["status"], "lp": lp_rec})
    curve = MB.construct_band_lp(lp, z)
    rho0, coef = float(curve.rho0_m), tuple(float(x) for x in curve.coefficients_m)
    lp_rec.update(rho0_m=rho0, coefficients_m=list(coef), max_residual=_lp_residual(rows, A, B, rho0, coef, kmax))
    review = MB.exact_curvature_review(rho0, coef, phi0, phi1, H, kappa_star=kappa_star, r_turn_m=r_turn,
                                       per_circle=1440)
    lp_rec["exact_curvature"] = review
    base_extra.update(lp=lp_rec)
    if not review["ok"]:
        return fail("detour_shape", "exact_curvature", "弧精确曲率复核未通过",
                    {"lp_status": lp["status"], "exact_curvature": review, "lp": lp_rec})
    c = band.center
    rr, d1, _ = periodic_radius_derivs(np.array([phi0, phi1]), rho0, np.asarray(coef))
    e0 = DN.polar_endpoint(c, rr[0], d1[0], phi0, sigma)
    e1 = DN.polar_endpoint(c, rr[1], d1[1], phi1, sigma)
    P0, T0 = e0["point_xy"], e0["tangent_xy"]
    P1, T1 = e1["point_xy"], e1["tangent_xy"]
    # 进出图元（裁定 2：β 相对实际切向）
    Rf = DN.fillet_radius(H, G, M["turn_u_min_m"])
    draw["fillet_radius_m"] = float(Rf)
    u_in, _ = DN.oblique_direction(T0, P0, c, math.radians(beta_in), True)
    u_out, _ = DN.oblique_direction(T1, P1, c, math.radians(beta_out), False)
    try:
        f_in = DN.fillet_from_pose(P0, T0, u_in, Rf, G["tangent_straight_m"], True)
        f_out = DN.fillet_from_pose(P1, T1, u_out, Rf, G["tangent_straight_m"], False)
    except ValueError as exc:
        return fail("detour_route", "entry_fillet", f"圆角无法构造：{exc}")
    offsets = [slots0.offsets[mm] for mm in slots0.order]
    near = cons["near_geometry"]
    band_m = P["pre_entry_warning_clearance_m"]
    t0 = time.perf_counter()
    ent = _entry_domain(cons, f_in, offsets, near, band_m, P["alignment_length_m"], G)
    ext = _exit_domain(cons, f_out, offsets, near, band_m, G, M)
    _tick(T, "end_domain_s", t0)
    if ent.get("fail"):
        return fail("detour_route", ent["fail"], ent["reason"], {"intervals": ent.get("intervals")})
    if ext.get("fail"):
        return fail("detour_route", ext["fail"], ext["reason"], {"intervals": ext.get("intervals")})
    # 7：进、出额外延长（各一次 uniform；先 in 后 out）
    e_in = float(rng.uniform(0.0, ent["extra_max"]))
    e_out = float(rng.uniform(0.0, ext["extra_max"]))
    draw.update(entry_extra_m=e_in, exit_extra_m=e_out)
    # 8：成员槽位排列
    members = tuple(sorted(group.member_ids))
    perm = rng.permutation(len(members))
    order = tuple(members[int(i)] for i in perm)
    draw["member_slot_order"] = list(order)
    slots = formation_slots(group, fam, None, formation=slots0.realized,
                            lateral_step_m=payload["lateral_step_m"], order=order)
    x_C = ent["x_max"] - e_in
    x_T = ext["x_min"] + e_out
    end_geometry = {"entry": _end_record(f_in), "exit": _end_record(f_out)}
    proposal = {"candidate": _cand(C), "draw": draw, "band": band_rec, "lp": lp_rec, "end_geometry": end_geometry}
    base_extra.update(end_geometry=end_geometry)
    t0 = time.perf_counter()
    got = _reference(f_in, f_out, c, rho0, coef, phi0, phi1, x_C, x_T, slots, spacing)
    _tick(T, "reference_s", t0)
    if isinstance(got, str):
        return fail("detour_route", "base", f"参考构造失败：{got}")
    ref, marks, line_mask, prims = got
    try:
        lanes = derive_members(ref, slots, (ref.marks["collect"], ref.marks["terminal"]), spacing_m=spacing)
    except ValueError as exc:
        return fail("detour_route", "base", f"车道派生失败：{exc}")
    view = DetourRouteView(ctx, cons, states)
    C_xy = np.asarray(f_in["fillet_start_xy"], float) + x_C * np.asarray(u_in, float)
    t0 = time.perf_counter()
    starts, meta = plan_starts(view, slots, C_xy, np.asarray(u_in, float), crng, route_fn=view.route_fn)
    _tick(T, "route_s", t0)
    T["route_queries"] = dict(view.stats)
    if starts is None:
        return fail("detour_route", "entry_route", f"成员 {meta} 没有可用的起点路由", {"member": meta})
    return _assemble(ctx, group, task, states, key, T, C, G, M, cons, band, slots, slots0, payload, steps, b, draw,
                     proposal, ref, marks, line_mask, prims, lanes, starts, meta, f_in, f_out, view, H, Rf, Sigma, fail)


def _cand(C):
    return {"near_band_width_m": float(C.values["near_band_width_m"]), "min_sweep_deg": float(C.values["min_sweep_deg"]),
            "max_sweep_deg_exclusive": float(C.values["max_sweep_deg_exclusive"]),
            "sweep_measure": C.values["sweep_measure"], "criteria_sha256": C.sha256,
            "generation_sha256": load_config("detour").sha256}


def _lp_residual(rows, A, B, rho0, coef, kmax):
    ph = np.radians(np.r_[rows, rows[:-1] + 0.5])
    r, _, d2 = periodic_radius_derivs(ph, rho0, np.asarray(coef))
    lo = np.r_[A, np.maximum(A[:-1], A[1:])]
    hi = np.r_[B, np.minimum(B[:-1], B[1:])]
    ac = np.r_[A, np.maximum(A[:-1], A[1:])]
    corridor = float(max(0.0, np.max(lo - r), np.max(r - hi)))
    curv = float(max(0.0, np.max(np.abs(r - d2) - kmax * ac * ac)))
    return {"corridor_m": corridor, "curvature_per_m": curv}


def _end_record(f):
    return {"point_xy": _xy(f["point_xy"]), "tangent_xy": _xy(f["tangent_xy"]),
            "line_direction_xy": _xy(f["line_direction_xy"]), "fillet_center_xy": _xy(f["fillet_center_xy"]),
            "fillet_start_xy": _xy(f["fillet_start_xy"]), "fillet_end_xy": _xy(f["fillet_end_xy"]),
            "turn_angle_rad": float(f["turn_angle_rad"]), "straight_m": float(f["straight_m"]),
            "primitives": [_prim_record(p) for p in f["primitives"]]}


def _prim_record(p):
    if p[0] == "line":
        return ["line", _xy(p[1]), _xy(p[2])]
    if p[0] == "arc":
        return ["arc", _xy(p[1]), float(p[2]), float(p[3]), float(p[4])]
    return ["spline_arc", _xy(p[1]), float(p[2]), [float(x) for x in p[3]], float(p[4]), float(p[5])]


# ---------------------------------------------------------------- 进出直线的解析域（指令 3.4 第 1–3 条）

def _lane_line(p, u, d):
    from ..detour_numeric import J
    return np.asarray(p, float) + float(d) * J(u)


def _entry_domain(cons, f_in, offsets, near, band_m, align_m, G):
    from ..transit_chords import line_sublevel
    A = np.asarray(f_in["fillet_start_xy"], float)
    u = np.asarray(f_in["line_direction_xy"], float)
    xs, info = [], []
    for l, d in offsets:
        p = _lane_line(A, u, d)
        iv0 = line_sublevel(near, p, u, 0.0)
        ivo = line_sublevel(near, p, u, band_m)
        ivi = line_sublevel(near, p, u, -band_m)
        info.append({"lane_m": float(d), "near_in": None if iv0 is None else list(iv0),
                     "outer_band": None if ivo is None else list(ivo), "inner_band": None if ivi is None else list(ivi)})
        if iv0 is None or ivo is None or ivi is None or ivi[0] > 0.0 or iv0[0] > 0.0:
            return {"fail": "crossing", "reason": "进场直线在圆角前没有完整穿过近距离带 ±10 m", "intervals": info}
        xs.append(min(ivo[0], iv0[0] - align_m) - l)
    x_max = float(min(xs))
    lows = []
    for l, d in offsets:
        p = _lane_line(A, u, d)
        comp = component_containing(cons["base"], p, u, x_max + l, 0.0)
        if comp is None:
            return {"fail": "base", "reason": "进场直线（集合槽位至圆角）违反 base 约束", "intervals": info}
        lows.append(x_max + l - comp[0])
    extra_max = float(min(float(G["extension_max_m"]), min(lows)))
    return {"x_max": x_max, "extra_max": max(0.0, extra_max), "intervals": info}


def _exit_domain(cons, f_out, offsets, near, band_m, G, M):
    from ..transit_chords import line_sublevel
    Bp = np.asarray(f_out["fillet_end_xy"], float)
    u = np.asarray(f_out["line_direction_xy"], float)
    term = float(M["retreat_clearance_m"]) + float(G["terminal_extra_m"])
    lows, excluded, info = [], [], []
    for l, d in offsets:
        p = _lane_line(Bp, u, d)
        ivi = line_sublevel(near, p, u, -band_m)
        ivo = line_sublevel(near, p, u, band_m)
        info.append({"lane_m": float(d), "inner_band": None if ivi is None else list(ivi),
                     "outer_band": None if ivo is None else list(ivo)})
        if ivi is None or not (ivi[0] <= 0.0 <= ivi[1]) or ivo is None:
            return {"fail": "crossing", "reason": "离开直线在圆角后没有完整穿出近距离带 ±10 m", "intervals": info}
        lows.append(ivo[1] - l)
        for fid, W in cons["warnings"].items():
            iv = line_sublevel(W, p, u, term)
            if iv is not None and iv[1] > -l:
                excluded.append((iv[0] - l, iv[1] - l))
    x = max(lows)
    for a, bb in sorted(excluded):
        if a < x < bb:
            x = bb
        elif a >= x:
            continue
    changed = True
    while changed:
        changed = False
        for a, bb in excluded:
            if a < x < bb:
                x, changed = bb, True
    x_min = float(x)
    upper = math.inf
    for a, bb in excluded:
        if a >= x_min:
            upper = min(upper, a)
    for l, d in offsets:
        p = _lane_line(Bp, u, d)
        comp = component_containing(cons["base"], p, u, 0.0, x_min + l)
        if comp is None:
            return {"fail": "terminal", "reason": "离开直线（圆角至终点）违反 base 约束或终点出界", "intervals": info}
        upper = min(upper, comp[1] - l)
    extra_max = float(min(float(G["extension_max_m"]), upper - x_min))
    return {"x_min": x_min, "extra_max": max(0.0, extra_max), "intervals": info}


# ---------------------------------------------------------------- 参考曲线

def _reference(f_in, f_out, c, rho0, coef, phi0, phi1, x_C, x_T, slots, spacing):
    A = np.asarray(f_in["fillet_start_xy"], float)
    u_in = np.asarray(f_in["line_direction_xy"], float)
    Bo = np.asarray(f_out["fillet_end_xy"], float)
    u_out = np.asarray(f_out["line_direction_xy"], float)
    ext = slots.max_longitudinal_m
    ext = 0.0 if ext == 0.0 else ext + 1.0
    Cp = A + x_C * u_in
    Tp = Bo + x_T * u_out
    prims = []
    if ext > 0.0:
        prims.append(("line", tuple(Cp - ext * u_in), tuple(Cp)))
    i_collect = len(prims)
    prims.append(("line", tuple(Cp), tuple(A)))
    prims.extend(f_in["primitives"])
    i_arc = len(prims)
    prims.append(("spline_arc", (float(c[0]), float(c[1])), float(rho0), tuple(coef), float(phi0), float(phi1)))
    prims.extend(f_out["primitives"])
    i_term = len(prims)
    prims.append(("line", tuple(Bo), tuple(Tp)))
    if ext > 0.0:
        prims.append(("line", tuple(Tp), tuple(Tp + ext * u_out)))
    try:
        smp = sample_primitives(prims, spacing)
    except PathError as exc:
        return str(exc)
    iv = smp.intervals
    marks = {"collect": iv[i_collect][0], "arc_start": iv[i_arc][0], "arc_end": iv[i_arc][1],
             "terminal": iv[i_term][1]}
    ref = make_reference(smp, marks, (("ingress", marks["collect"], marks["arc_start"]),
                                      ("arc", marks["arc_start"], marks["arc_end"]),
                                      ("withdrawal", marks["arc_end"], marks["terminal"])))
    s = ref.s
    line_iv = [(float(s[a]), float(s[b])) for (a, b), p in zip(iv, prims) if p[0] == "line"]
    curve_iv = [(p[0], float(s[a]), float(s[b])) for (a, b), p in zip(iv, prims) if p[0] != "line"]

    def line_mask(st):
        st = np.asarray(st, float)
        out = np.zeros(st.shape, bool)
        for a, b in line_iv:
            out |= (st >= a - 1e-9) & (st <= b + 1e-9)
        for _, a, b in curve_iv:
            out &= ~((st > a + 1e-9) & (st < b - 1e-9))
        return out
    return ref, marks, line_mask, {"prims": prims, "intervals": iv, "curve_intervals": curve_iv}


# ---------------------------------------------------------------- 组装与检查

def _assemble(ctx, group, task, states, key, T, C, G, M, cons, band, slots, slots0, payload, steps, b, draw, proposal,
              ref, marks, line_mask, prims, lanes, starts, meta, f_in, f_out, view, H, Rf, Sigma, fail):
    Cv = C.values
    P = ctx.params
    spacing = P["curve_spacing_m"]
    target = task.target_id
    near_key, near = cons["near_key"], cons["near_geometry"]
    band_m = P["pre_entry_warning_clearance_m"]
    s_c, s_t = ref.marks["collect"], ref.marks["terminal"]
    s_a0, s_a1 = ref.marks["arc_start"], ref.marks["arc_end"]
    curves, coll_idx, kap, stations = {}, {}, {}, {}
    for mid in slots.order:
        try:
            sb = sample_primitives(list(starts[mid]), spacing)
        except PathError as exc:
            return fail("detour_route", "entry_route", f"成员 {mid} 起点连接图元非法：{exc}", {"member": mid})
        p_init = np.asarray(states[mid].p[:2], float)
        lane = lanes[mid]
        if float(np.hypot(*(sb.xy[0] - p_init))) > NODE_TOL_M or float(np.hypot(*(sb.xy[-1] - lane.xy[0]))) > NODE_TOL_M:
            return fail("detour_route", "entry_route", f"成员 {mid} 起点连接端点与初始位置/槽位不符", {"member": mid})
        curves[mid] = np.vstack([sb.xy, lane.xy[1:]])
        coll_idx[mid] = len(sb.xy) - 1
        lk = np.interp(lane.s_ref, ref.s, ref.kappa) / np.maximum(1.0 - np.interp(lane.s_ref, ref.s, ref.kappa) * lane.d_m, 1e-9)
        kap[mid] = np.r_[sb.kappa, lk[1:]]
        stations[mid] = np.r_[np.full(len(sb.xy) - 1, -1.0), lane.s_ref]
    cum = {m: np.r_[0.0, np.cumsum(np.hypot(*np.diff(curves[m], axis=0).T))] for m in curves}
    # 形状：弧车道对 base + arc_only 精确余量；圆角真实车道半径（指令 3.4）
    t0 = time.perf_counter()
    r_lane_min = float(load_config("joint_opt").values["buffer_turn_factor"]) * float(M["turn_u_min_m"])
    for mid in slots.order:
        st = stations[mid]
        on_arc = np.flatnonzero((st >= s_a0 - 1e-9) & (st <= s_a1 + 1e-9))
        if len(on_arc) >= 2:
            seg = curves[mid][on_arc[0]:on_arc[-1] + 1]
            for cn in list(cons["base"]) + list(cons["arc_only"]):
                mg = polyline_clearance(cn.geometry, seg, sense=cn.sense, minimum_m=cn.minimum_m, fast_far_m=FAR_M)
                k = int(np.argmin(mg))
                if mg[k] < 0.0:
                    return fail("detour_shape", "arc_clearance", f"成员 {mid} 的弧车道违反 {cn.name}",
                                {"member": mid, "constraint": cn.name, "margin_m": float(mg[k]),
                                 "chord_index": int(on_arc[0] + k)})
        d_i = float(slots.offsets[mid][1])
        for f in (f_in, f_out):
            eps = math.copysign(1.0, f["turn_angle_rad"]) if f["turn_angle_rad"] != 0.0 else 0.0
            if eps != 0.0 and not (Rf - eps * d_i >= r_lane_min):
                which = "entry_fillet" if f is f_in else "exit_fillet"
                return fail("detour_route", which, f"成员 {mid} 圆角车道半径 {Rf - eps * d_i:.3f} m 不足",
                            {"member": mid, "margin_m": float(Rf - eps * d_i - r_lane_min)})
    _tick(T, "shape_check_s", t0)
    # 路由与穿越：base、进场前缀、near 带只与直线相交、冻结 crossing_analysis、终点
    t0 = time.perf_counter()
    retreat = float(M["retreat_clearance_m"])
    entry_exit = {}
    for mid in slots.order:
        xy = curves[mid]
        for cn in cons["base"]:
            mg = polyline_clearance(cn.geometry, xy, sense=cn.sense, minimum_m=cn.minimum_m, fast_far_m=FAR_M)
            k = int(np.argmin(mg))
            if mg[k] < 0.0:
                return fail("detour_route", "base", f"成员 {mid} 违反 {cn.name}",
                            {"member": mid, "constraint": cn.name, "margin_m": float(mg[k]), "chord_index": k})
        pre = xy[:coll_idx[mid] + 1]
        if len(pre) >= 2:
            mg = polyline_clearance(near, pre, sense=1, minimum_m=band_m, fast_far_m=FAR_M)
            k = int(np.argmin(mg))
            if mg[k] < 0.0:
                return fail("detour_route", "entry_route", f"成员 {mid} 进场路由在集合槽位前进入近距离带外 10 m",
                            {"member": mid, "constraint": "preentry_near", "margin_m": float(mg[k]), "chord_index": k})
        bad = lane_band_violations(xy, kap[mid], stations[mid], line_mask, near, band_m)
        if len(bad):
            st = float(stations[mid][bad[0]])
            which = "entry_fillet" if st < s_a0 else ("exit_fillet" if st > s_a1 else "crossing")
            return fail("detour_route", which, f"成员 {mid} 非直线图元与近距离带 ±10 m 相交",
                        {"member": mid, "chord_index": int(bad[0])})
        viol, cross = crossing_analysis(xy, cons["crossing_boundaries"], near_key, band_m=band_m,
                                        align_m=P["alignment_length_m"])
        if viol:
            v = viol[0]
            return fail("detour_route", "crossing", f"成员 {mid} 边界穿越不合规：{v['kind']}（{v['facility']}）",
                        {"member": mid, "violation": {k: v.get(k) for k in ("facility", "kind", "s_m")}})
        nd = [cc.direction for cc in cross if cc.facility_id == near_key]
        td = [cc.direction for cc in cross if cc.facility_id == target]
        if nd != ["in", "out"] or td:
            return fail("detour_route", "crossing", f"成员 {mid} near 穿越 {nd}、真实目标 warning 穿越 {td}",
                        {"member": mid, "near_directions": nd, "target_directions": td})
        nc = [cc for cc in cross if cc.facility_id == near_key]
        entry_exit[mid] = (float(nc[0].s_m), float(nc[1].s_m))
        end = xy[-1]
        for fid, geom in cons["warnings"].items():
            sd = float(signed_distance(geom, end))
            if not sd >= retreat:
                return fail("detour_route", "terminal", f"成员 {mid} 终点离 {fid} 预警圈 {sd:.3f} m",
                            {"member": mid, "facility": fid, "margin_m": sd - retreat})
        if not float(signed_distance(near, end)) >= band_m:
            return fail("detour_route", "terminal", f"成员 {mid} 终点未离开近距离带外 10 m", {"member": mid})
    _tick(T, "route_check_s", t0)
    # 裁定 1：构造后车道扫角窗口
    t0 = time.perf_counter()
    win = lane_sweep_window(curves, band.center, ctx.facility_by_id[target].layers["warning"], C, G)
    _tick(T, "sweep_window_s", t0)
    draw["lane_sweep_deg"] = {m: float(v) for m, v in sorted(win["spans_deg"].items())}
    draw["entry_exit_contribution_deg"] = float(max(win["spans_deg"].values()) - Sigma)
    if not win["ok"]:
        return fail("detour_route", "sweep_window", "构造后车道扫角越界（下限 Θ+5 或上限 350）",
                    {"lane_sweep": {m: float(v) for m, v in sorted(win["spans_deg"].items())}})
    # 速度、释放与成员计划（与过境同一算法）
    return _finish(ctx, group, task, states, key, T, C, G, M, cons, slots, slots0, payload, steps, b, draw, proposal,
                   ref, marks, lanes, curves, coll_idx, cum, stations, entry_exit, f_in, f_out, H, fail)


def _finish(ctx, group, task, states, key, T, C, G, M, cons, slots, slots0, payload, steps, b, draw, proposal,
            ref, marks, lanes, curves, coll_idx, cum, stations, entry_exit, f_in, f_out, H, fail):
    Gd = load_config("guidance").values
    G_ref_cfg = reference_guidance()
    G_ref = G_ref_cfg.values
    s_c, s_t = ref.marks["collect"], ref.marks["terminal"]
    v0 = float(group.speed_profile.initial_speed_m_s)
    try:
        ref_curve = make_curve(ref.xy[marks["collect"]:marks["terminal"] + 1], max_chord_m=Gd["max_chord_m"],
                               max_turn_rad=Gd["max_turn_per_chord_rad"])
        v_slow = speed_profile(ref_curve, ((0.0, float(M["speed_min_m_s"])),), a_lat=G_ref["a_lat_m_s2"],
                               a_lon=G_ref["a_lon_m_s2"], v_max=member_config().vehicle_profile.max_speed_xy_m_s,
                               v0=0.0, v_end=0.0, stops=(ref_curve.length,))
    except SimContractError as exc:
        return fail("detour_route", "base", f"参考曲线不满足引导接口：{exc}")
    t_upper = float(nominal_time(ref_curve, v_slow, 0.0, ref_curve.length))
    sev = draw_speed_events(group.speed_profile,
                            RngKey(key.family_id, key.draw, "speed", mission=key.mission, branch=key.branch,
                                   group=key.group, segment=key.segment, attempt=key.attempt), horizon_s=t_upper)
    breaks_ref = ((0.0, v0),)
    if len(sev.times_s):
        try:
            smap = map_speed_events(ref_curve, sev.times_s, sev.speeds_m_s, (), G_ref_cfg, initial_speed_m_s=v0)
        except SimContractError as exc:
            return fail("detour_route", "base", f"速度映射失败：{exc}")
        breaks_ref = smap.breaks
    breaks = {}
    for mid in slots.order:
        lane = lanes[mid]
        l_m = slots.offsets[mid][0]
        lane_cum = np.r_[0.0, np.cumsum(np.hypot(*np.diff(lane.xy, axis=0).T))]
        base_s = cum[mid][coll_idx[mid]]
        out = [(0.0, v0)]
        for s_rel, vv in breaks_ref[1:]:
            s_member = base_s + float(np.interp(s_c + s_rel + l_m, lane.s_ref, lane_cum))
            if s_member > out[-1][0] + 1e-9:
                out.append((s_member, float(vv)))
            else:
                out[-1] = (out[-1][0], float(vv))
        breaks[mid] = tuple(out)
    try:
        delays, _travel, nom0 = _release_delays_ref(curves, {m: float(cum[m][coll_idx[m]]) for m in curves}, breaks,
                                                    G_ref_cfg)
    except SimContractError as exc:
        return fail("detour_route", "base", f"曲线不满足引导接口：{exc}")
    members, nominals = {}, {}
    for mid in slots.order:
        xy = curves[mid]
        members[mid] = MemberPlan(mid, 0, tuple((float(a), float(bb)) for a, bb in xy), float(states[mid].p[2]),
                                  float(nom0[mid].curve.length), float(delays[mid]), breaks[mid], ())
        nominals[mid] = replace(nom0[mid], release_s=release_us(members[mid]) / 1e6)
    order = list(slots.order)
    duration = float(max(nominals[m].end_s for m in order) - min(nominals[m].release_s for m in order))
    # 成员映射与转弯区间（实际采用了 1.05·turn_u_min 半径约束的弧与圆角）
    mm, turns = {}, {}
    curve_iv = [(p[0], a, bb) for p, a, bb in _curve_ivs(ref, f_in, f_out)]
    for mid in order:
        ln = lanes[mid]
        l_m = float(slots.offsets[mid][0])
        ms = np.asarray(cum[mid][coll_idx[mid]:coll_idx[mid] + len(ln.xy)], float)
        at = lambda s: float(np.interp(s + l_m, ln.s_ref, ms))      # noqa: E731
        mm[mid] = {"reference_s": (ln.s_ref - l_m).tolist(), "member_s": ms.tolist(),
                   "collect_s": float(cum[mid][coll_idx[mid]]), "arc_start_s": at(ref.marks["arc_start"]),
                   "arc_end_s": at(ref.marks["arc_end"]), "near_entry_s": entry_exit[mid][0],
                   "near_exit_s": entry_exit[mid][1], "terminal_s": float(cum[mid][-1])}
        rows = []
        for kind, a, bb in curve_iv:
            idx = np.flatnonzero((ln.s_ref >= a - 1e-9) & (ln.s_ref <= bb + 1e-9))
            if len(idx) >= 2:
                rows.append(("detour_" + kind, float(ms[idx[0]]), float(ms[idx[-1]]), "turn_u_min_m"))
        turns[mid] = rows
    # 骨架名义判据表：只诊断（正式预筛在优化后）
    from ..detour_checks import screen_detour
    samples = {}
    for mid in order:
        smp = sample_nominal(members[mid], include_prerelease=False, nominal=nominals[mid])
        samples[mid] = {"time_us": np.asarray(smp.time_us), "p": np.asarray(smp.p), "v": np.asarray(smp.v)}
    try:
        bone = screen_detour(ctx.scene, ctx.facilities, task.target_id, samples, candidate=C)
        bone_rec = {k: bone[k] for k in ("passed", "member_conditions", "member_facts", "group_conditions",
                                         "group_facts", "failures")}
    except ValueError as exc:
        bone_rec = None
        T["bone_screen_error"] = str(exc)
    formation = {"prior": slots.prior, "start": slots.start, "realized": slots.realized,
                 "mapped_from_loose": slots.mapped_from_loose, "retreat_chain": list(retreat_chain(slots.start)),
                 "order": list(slots.order), "offsets": {m: list(v) for m, v in slots.offsets.items()},
                 "lateral_step_m": slots.lateral_step_m}
    repairs = []
    if slots.realized != slots.start:
        repairs.append({"kind": "formation_retreat", "from": slots.start, "to": slots.realized, "forced_by": "width"})
    used = payload.get("lateral_step_m")
    if used is not None and used < b - 1e-9:
        repairs.append({"kind": "echelon_lateral_step", "from_m": b, "to_m": float(used)})
    witnesses = {"intent": "detour", "target_id": task.target_id, "near_key": cons["near_key"],
                 "candidate": proposal["candidate"], "band": proposal["band"], "draw": draw,
                 "end_geometry": proposal["end_geometry"], "formation_steps": steps,
                 "member_map_detour": mm, "turn_ranges": turns, "bone_nominal_screen": bone_rec,
                 "nominal_duration_s": duration}
    anchors = {"collect_s": float(s_c), "arc_start_s": float(ref.marks["arc_start"]),
               "arc_end_s": float(ref.marks["arc_end"]), "terminal_s": float(s_t)}
    ref_xy = tuple((float(a), float(bb)) for a, bb in ref.xy[marks["collect"]:marks["terminal"] + 1])
    return SegmentPlan(members=members, reference_xy=ref_xy, nominal_duration_s=duration, anchors=anchors,
                       repairs=tuple(repairs), failure=None, proposal=proposal, formation=formation,
                       topology={"final": "detour"}, business_key=_key_dict(key),
                       member_nominal_s={m: float(nominals[m].travel_s) for m in order}, witnesses=witnesses)


def _curve_ivs(ref, f_in, f_out):
    """参考上的非直线图元（进场圆角、样条弧、离开圆角）站点区间：按标记与圆角切线长解析给出。"""
    out = []
    a0, a1 = ref.marks["arc_start"], ref.marks["arc_end"]
    if f_in["primitives"][0][0] == "arc":
        ln = abs(f_in["turn_angle_rad"]) * float(f_in["radius_m"])
        e = a0 - float(f_in["straight_m"])
        out.append((("fillet",), e - ln, e))
    out.append((("arc",), a0, a1))
    if f_out["primitives"][-1][0] == "arc":
        ln = abs(f_out["turn_angle_rad"]) * float(f_out["radius_m"])
        s = a1 + float(f_out["straight_m"])
        out.append((("fillet",), s, s + ln))
    return out
