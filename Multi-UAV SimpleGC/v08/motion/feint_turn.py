"""佯动整体掉头：参数格、完整候选认证、距离场粗筛与组合抽样（V8-18 指令 3.1–3.4、3.6；附录裁定 1–4；本项新增）。

只调用监视数值构件（monitoring_turn：_core、collapse_length_m、column_offsets、derive_deforming_members、
choose_joint_turn），不修改它。一个候选 = 入口格 cell（θ、h、x_in、集合距离预检列表）× (A_m, kind, side, R)：
入口直线到 A = o + A_m u + h n；收拢 A → B = A + L u；MT._core(kind, B, θ, R, side) 得核心与 D、出向；
展开 D → E = D + L u_out；此后全程直线到出口终点。L 由 MT.collapse_length_m 按 S _turns_v14 的参数算出。

认证谓词（certify_candidate；三种路径结论逐个相同，见裁定 3(b) 门禁）：
  1. 入口（格级，解析精确，与模式无关）：各成员车道目标 warning 一次正长度穿越且深 10 m、入圈点所在合法 run、
     集合距离预检（feint_chords）；A 级：成员实际支撑起点 X = A + l_i − l*（车道坐标）在该车道 alert −10 区间内、
     不越过入圈合法 run，B 在中心线 alert −10 区间内，其他 warning 在 [集合槽位, 支撑起点] 上整段离带或完整深穿。
  2. 出口（解析精确）：成员支撑终点 X = l* + l_i（出口车道坐标）在 alert −10 内、protected +10 外；出口车道的
     合法 run（与 transit_chords 同一 5 m 采样/距离场下界规则）、最后成员出目标 warning 的编组站点 s0 起每 5 m
     的离散首个终点（全员距所有 warning ≥ 50 m、未离开本条合法 run、x ≥ l* 即展开完成），终点精确 SDF 复核。
  3. 完整（模式只影响 clearance 的求法）：MT.derive_deforming_members 派生实际成员车道（支撑窗口），拼接入口/出口
     直线段（≤ 5 m 弦）；全部收拢/展开支撑之并与整个核心在 alert −10 内、protected +10 外，支撑对全部 crossing
     boundaries 满足 |sdf| ≥ 10；全成员折线 feint base；完整 crossing_analysis（不传 skip_ranges），目标 warning、
     alert 方向各恰为 ["in", "out"]；各相容 D_c 的入口延长弦 base 精确。
  剪枝（prune=True，裁定 3(a)）：完整认证前先查核心的必要条件——核心关键点解析区间（alert −10 内、protected +10 外）、
  中心线核心采样点精确 SDF、base 距离场上界 < 0 确定拒绝。只省计算，不改变可行集合。

clearance_passes：mode="exact" 对每项约束逐弦精确（polyline_clearance, fast_far_m=None）；mode="screened"（裁定 1）
沿折线 ≤ 5 m 取覆盖点、覆盖半径 q = 2.5 m：下界 ℓ ≥ q 直接通过覆盖段，点上界 u = ℓ + 2ε_f < 0 直接拒绝，其余覆盖段
调用同一精确函数。两种直接判定都可靠，结论与 exact 逐个相同。upper_literal 不实现（裁定 1）。
"""
import math
from collections import OrderedDict
from types import SimpleNamespace as NS

import numpy as np

from . import monitoring_turn as MT

VERSION = "v18-feint-turn-1"
MODES = ("exact", "screened")
SCREEN_Q_M = 2.5                  # 5 m 覆盖点间距的覆盖半径（TC.Q_M）
SCREEN_STEP_M = 5.0
BAND_M = 10.0                     # alert 内 / protected 外 / 全部边界带（指令 3.3）
A_STEP_M = 5.0                    # A 沿弦 5 m 全局倍数（U D.3）
R_STEP_M = 2.0                    # R = 1.05 R_min + 2k（MT.sample_joint_turn 同一下界与步长）
R_FACTOR = 1.05
STRAIGHT_STEP_M = 5.0             # 认证折线的入口/出口直线段弦长上限（直线几何精确；见 _member_polyline）
WINDOW_PAD_M = 5.0                # 派生窗口在支撑两端外留出的直线
KEYPOINTS = 13                    # 核心关键点数（剪枝用；只是必要条件的取样数，不是阈值）
_CERT_MEMO = 8


# ---------------------------------------------------------------- 距离场粗筛与精确谓词

def _exact_chords(c, P, idx):
    from ..scene.exact import chord_sdf_range, margin_from_range
    lo, hi, _ = chord_sdf_range(c.geometry, P[idx], P[idx + 1])
    return margin_from_range(lo, hi, sense=c.sense, minimum_m=c.minimum_m)


def _field_has(field, c):
    return field is not None and getattr(field, "_by_name", {}).get(c.name) == c


def _screened_one(c, P, field, stats=None):
    """单约束的 screened 判定（裁定 1）。P 至少两点。返回 bool。"""
    seg = np.hypot(*np.diff(P, axis=0).T)
    s = np.r_[0.0, np.cumsum(seg)]
    S = float(s[-1])
    st = np.unique(np.r_[np.arange(0.0, S, SCREEN_STEP_M), S])
    pts = np.stack([np.interp(st, s, P[:, 0]), np.interp(st, s, P[:, 1])], axis=1)
    lo = field.lower_clearance(pts, [c.name])[c.name]
    fin = np.isfinite(lo)
    up = lo + 2.0 * field.eps
    if stats is not None:
        stats["cover_points"] = stats.get("cover_points", 0) + len(st)
    if np.any(fin & (up < 0.0)):
        if stats is not None:
            stats["direct_reject"] = stats.get("direct_reject", 0) + 1
        return False
    unc = ~(lo >= SCREEN_Q_M)
    nseg = len(seg)
    if stats is not None:
        stats["chords"] = stats.get("chords", 0) + nseg
    if not unc.any():
        return True
    a, b = st[unc] - SCREEN_Q_M, st[unc] + SCREEN_Q_M
    j0 = np.clip(np.searchsorted(s, a, side="right") - 1, 0, nseg - 1)
    j1 = np.clip(np.searchsorted(s, b, side="left"), 0, nseg - 1)
    mark = np.zeros(nseg + 1, np.int64)
    np.add.at(mark, j0, 1)
    np.add.at(mark, j1 + 1, -1)
    idx = np.flatnonzero(np.cumsum(mark)[:nseg] > 0)
    if stats is not None:
        stats["exact_chords"] = stats.get("exact_chords", 0) + len(idx)
    return bool(np.all(_exact_chords(c, P, idx) >= 0.0))


def clearance_passes(constraints, xy, *, mode="exact", field=None, stats=None):
    """真实折线对每项约束余量 ≥ 0。mode="exact"：polyline_clearance(fast_far_m=None) 逐弦（权威谓词）；单点用精确
    SDF；空路径拒绝。mode="screened"：见模块说明（field 中缺少同名同几何的约束时该项走 exact）。"""
    from ..scene.exact import clearance_values, polyline_clearance
    if mode not in MODES:
        raise ValueError(f"未知 clearance 模式：{mode!r}（upper_literal 依裁定 1 不实现）")
    P = np.asarray(xy, float).reshape(-1, 2) if len(xy) else np.zeros((0, 2))
    if len(P) == 0:
        return False
    for c in constraints:
        if len(P) == 1:
            if mode == "screened" and _field_has(field, c):
                lo = float(field.lower_clearance(P, [c.name])[c.name][0])
                if math.isfinite(lo) and lo + 2.0 * field.eps < 0.0:
                    return False                              # 点上界 < 0：确定拒绝
                if lo >= SCREEN_Q_M:
                    continue                                  # 下界 ≥ q：确定通过
            if not float(clearance_values(c.geometry, P, sense=c.sense, minimum_m=c.minimum_m)[0]) >= 0.0:
                return False
            continue
        if mode == "screened" and _field_has(field, c):
            if not _screened_one(c, P, field, stats):
                return False
            continue
        m = polyline_clearance(c.geometry, P, sense=c.sense, minimum_m=c.minimum_m, fast_far_m=None)
        if not float(np.min(m)) >= 0.0:
            return False
    return True


# ---------------------------------------------------------------- 形变支撑（真实成员折线）

def _t_interval(arr, a, b):
    """严格递增数组 arr 上 {arr ∈ [a, b]} 的下标空间区间（分数下标）；与成员域不交时 None。"""
    if b < arr[0] or a > arr[-1] or b < a:
        return None
    k = np.arange(len(arr), dtype=float)
    return float(np.interp(max(a, arr[0]), arr, k)), float(np.interp(min(b, arr[-1]), arr, k))


def _union(iv):
    iv = sorted(x for x in iv if x is not None)
    out = []
    for a, b in iv:
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _clip(xy, t0, t1):
    """按分数下标裁切真实折线（端点在弦上线性插值，即折线本身上的点）。"""
    n = len(xy)

    def at(t):
        i = min(int(math.floor(t)), n - 2) if n > 1 else 0
        f = t - i
        return xy[i] if n == 1 else xy[i] * (1.0 - f) + xy[i + 1] * f
    i0, i1 = int(math.ceil(t0)), int(math.floor(t1))
    mid = [xy[i] for i in range(i0, i1 + 1) if t0 < i < t1]
    pts = [at(t0)] + mid + ([at(t1)] if t1 > t0 else [])
    out = [pts[0]]
    for p in pts[1:]:
        if not (p[0] == out[-1][0] and p[1] == out[-1][1]):
            out.append(p)
    return np.asarray(out, float)


def support_pieces(lane, schedule):
    """[(名称, 折线)]：每次掉头的收拢支撑（s_ref ∈ [s_A, s_B] 或 s_group ∈ [s_A − l*, s_B − l*]）、展开支撑
    （s_ref ∈ [s_D, s_E] 或 s_group ∈ [s_D + l*, s_E + l*]）及核心（s_ref ∈ [s_B, s_D]）。端点插入后裁切。"""
    out = []
    for k, ev in enumerate(schedule):
        ls = float(ev["l_star"])
        for name, ref_iv, grp_iv in (("collapse", (ev["s_A"], ev["s_B"]), (ev["s_A"] - ls, ev["s_B"] - ls)),
                                     ("expand", (ev["s_D"], ev["s_E"]), (ev["s_D"] + ls, ev["s_E"] + ls))):
            for t0, t1 in _union([_t_interval(lane.s_ref, *ref_iv), _t_interval(lane.s_group, *grp_iv)]):
                out.append((f"{name}{k}", _clip(lane.xy, t0, t1)))
        iv = _t_interval(lane.s_ref, ev["s_B"], ev["s_D"])
        if iv is not None:
            out.append((f"core{k}", _clip(lane.xy, *iv)))
    return out


def support_constraints(alert, protected, boundaries, band_m):
    from ..scene.field import Clearance
    inside = [Clearance("feint_support_alert", alert, -1, float(band_m)),
              Clearance("feint_support_protected", protected, 1, float(band_m))]
    bands = [Clearance("feint_band:" + k, g, 0, float(band_m)) for k, g in boundaries.items()]
    return inside, bands


def deformation_passes(lanes, schedule, alert, protected, boundaries, *, band_m, mode="exact", field=None,
                       detail=False, stats=None):
    """实际成员的收拢/展开支撑之并须在 alert SDF ≤ −band、protected SDF ≥ band，并对全部 crossing boundaries
    满足 sense=0、minimum=band；整个核心在 alert 内侧 band、protected 外侧 band。detail=True 返回 (bool, 首个失败)。"""
    inside, bands = support_constraints(alert, protected, boundaries, band_m)
    for m in sorted(lanes):
        for name, xy in support_pieces(lanes[m], schedule):
            cons = inside if name.startswith("core") else inside + bands
            if not clearance_passes(cons, xy, mode=mode, field=field, stats=stats):
                return (False, {"member": m, "piece": name}) if detail else False
    return (True, None) if detail else True


# ---------------------------------------------------------------- 抽样协议（C14 / 指令 3.4）

def sample_turn_grid(grids, certify, rng):
    """按 MT KINDS × SIDES 顺序：每个有候选的组合 rng.permutation(n) 一次，依排列认证，取首个通过记录（遍历完无
    通过者该组合为空）；没有候选的组合跳过、不调用 RNG。再直接调用 MT.choose_joint_turn 在非空组合中等概率选一组、
    组内选一条。空返回 None。"""
    records = []
    for kind in MT.KINDS:
        for side in MT.SIDES:
            cand = grids.get((kind, side)) or []
            if not len(cand):
                continue
            for i in rng.permutation(len(cand)).tolist():
                rec = certify(cand[int(i)])
                if rec is not None:
                    records.append(rec)
                    break
    return MT.choose_joint_turn(records, rng)


# ---------------------------------------------------------------- 目标与队形参数（进程内缓存）

def turn_context(ctx, target_id):
    key = ("feint_v18_turnctx", target_id)
    if key in ctx.extra:
        return ctx.extra[key]
    from ..config import load_config
    from ..scene.exact import bounding_box
    from ..scene.field import Clearance
    from . import transit_chords as TC
    from .layer_limits import constraints_identity, crossing_layer_keys
    tgt = ctx.facility_by_id[target_id]
    cons = TC.transit_base(ctx, target_id, intent="feint")
    M = load_config("monitoring").values
    x0, y0, x1, y1 = bounding_box(tgt.layers["alert"])
    D_a = math.hypot(x1 - x0, y1 - y0)
    rmin = {"u": float(M["turn_u_min_m"]), "oblique": float(M["turn_oblique_min_m"]),
            "teardrop": float(M["turn_teardrop_min_m"])}
    rmax = {"u": D_a / 2.0, "teardrop": D_a / 2.0, "oblique": D_a / (2.0 * math.sin(5.0 * math.pi / 12.0))}
    radii = {}
    for kind in MT.KINDS:
        R0 = R_FACTOR * rmin[kind]
        kmax = int(math.floor((rmax[kind] - R0) / R_STEP_M + 1e-12))
        radii[kind] = np.array([R0 + R_STEP_M * k for k in range(max(kmax + 1, 0))], float)
    lk = crossing_layer_keys(cons)
    alert_key = next(k for k, layer in lk.items() if layer == "alert")
    inside, bands = support_constraints(tgt.layers["alert"], tgt.layers["protected"], cons["crossing_boundaries"],
                                        BAND_M)
    allc = list(cons["base"]) + inside + bands
    T = NS(target=target_id, tgt=tgt, o=np.asarray(tgt.center, float), cons=cons, base=list(cons["base"]),
           cross=dict(cons["crossing_boundaries"]), warnings=dict(cons["warnings"]), alert_key=alert_key,
           alert=tgt.layers["alert"], prot=tgt.layers["protected"], warn=tgt.layers["warning"], D_a=D_a,
           rmin=rmin, rmax=rmax, radii=radii, screen_cons=allc, screen_name=("feint_screen", target_id,
                                                                           constraints_identity(allc)),
           params=ctx.params, retreat=float(M["retreat_clearance_m"]), keypoints={})
    for kind in MT.KINDS:
        for side in MT.SIDES:
            T.keypoints[(kind, side)] = _keypoints(kind, side, radii[kind], ctx.params["curve_spacing_m"])
    ctx.extra[key] = T
    return T


def screen_field(ctx, T):
    """screened 模式的距离场（base + 支撑 + 边界带，名字唯一；原始距离按几何键共享磁盘缓存）。"""
    return ctx.field(T.screen_name, T.screen_cons)


def _keypoints(kind, side, radii, spacing):
    """局部坐标（B = 原点、航向 0）的核心关键点 (a, b)：均匀取 KEYPOINTS 个采样点 + 横向/前向极值点。"""
    from .path import sample_primitives
    a_all, b_all = [], []
    for R in radii:
        prims, _, _ = MT._core(kind, np.zeros(2), 0.0, float(R), side)
        xy = sample_primitives(prims, spacing).xy
        idx = np.unique(np.r_[np.linspace(0, len(xy) - 1, KEYPOINTS).round().astype(int),
                              np.argmax(xy[:, 0]), np.argmax(xy[:, 1]), np.argmin(xy[:, 1])])
        sel = xy[idx]
        pad = KEYPOINTS + 3 - len(sel)
        if pad > 0:
            sel = np.vstack([sel, np.repeat(sel[-1:], pad, axis=0)])
        a_all.append(sel[:, 0]), b_all.append(sel[:, 1])
    if not len(radii):
        return np.zeros((0, KEYPOINTS + 3)), np.zeros((0, KEYPOINTS + 3))
    return np.array(a_all), np.array(b_all)


_FP_MEMO = {}


def formation_params(slots):
    """S _turns_v14 的参数：L = collapse_length_m(...)，l* = max(|l_i|, |l_i^col|)。按偏移/间距身份缓存（纯函数）。"""
    k = _offs_key(slots)
    if k not in _FP_MEMO:
        _FP_MEMO[k] = _formation_params(slots)
    return _FP_MEMO[k]


def _formation_params(slots):
    from ..config import load_config
    from ..sim.kernel import member_config
    from ..scene.context import context_params
    from .path import kappa_limit
    G = load_config("guidance").values
    M = load_config("monitoring").values
    offs = np.array([slots.offsets[m] for m in slots.order], float).reshape(-1, 2)
    # 曲率界 = kappa_limit(ctx.params["curve_spacing_m"], guidance.max_turn_per_chord_rad)（context_params 与 ctx.params 同源）
    kap = kappa_limit(context_params()["curve_spacing_m"], G["max_turn_per_chord_rad"])
    L = MT.collapse_length_m(offs, spacing_m=slots.spacing_m,
                             speed_max_m_s=float(member_config().vehicle_profile.max_speed_xy_m_s),
                             command_max_m_s=M["speed_max_m_s"],
                             dynamic_factor=float(load_config("joint_opt").values["buffer_dynamic_factor"]),
                             curvature_limit=kap)
    lcol = MT.column_offsets(len(offs), slots.spacing_m)
    l_star = float(max(np.max(np.abs(offs[:, 0])), np.max(np.abs(lcol)))) if len(offs) else 0.0
    return float(L), l_star, offs


# ---------------------------------------------------------------- 候选网格

def candidate_grid(ctx, task, slots, cell):
    """{(kind, side): [candidate, …]}，规范顺序 A 升序、R 升序（A 为中心线 alert −10 区间内的全局 5 m 倍数）。"""
    from .feint_chords import centerline_A
    T = turn_context(ctx, task.target_id)
    As = centerline_A(ctx, task.target_id, int(cell["theta_idx"]), float(cell["h_m"]))
    out = {}
    for kind in MT.KINDS:
        for side in MT.SIDES:
            out[(kind, side)] = [{"A_m": float(a), "kind": kind, "side": int(side), "radius_m": float(r)}
                                 for a in As for r in T.radii[kind]]
    return out


def _frame(ti):
    from . import transit_chords as TC
    th = TC.thetas()[int(ti)]
    u, n = TC.frame(th)
    return th, u, n


def keypoint_mask(ctx, task, slots, cell, kind, side):
    """裁定 3(a) 剪枝的解析部分（格 × 组合，向量化于全部 (A, R)）：核心关键点 B + a u + b n 在 alert −10 次水平集内、
    protected +10 次水平集外（端点合法）。返回 bool (nA, nR)。核心全员在单车道上，关键点是每个成员折线上的点。"""
    from . import transit_chords as TC
    from .feint_chords import centerline_A
    key = ("feint_v18_kpmask", task.target_id, _offs_key(slots), int(cell["theta_idx"]), float(cell["h_m"]), kind,
           int(side))
    memo = ctx.extra.setdefault(("feint_v18_kpmask_store",), OrderedDict())
    if key in memo:
        return memo[key]
    T = turn_context(ctx, task.target_id)
    L, _, _ = formation_params(slots)
    As = np.asarray(centerline_A(ctx, task.target_id, int(cell["theta_idx"]), float(cell["h_m"])), float)
    a, b = T.keypoints[(kind, side)]
    nR = len(T.radii[kind])
    if not len(As) or not nR:
        mask = np.zeros((len(As), nR), bool)
    else:
        th, u, n = _frame(cell["theta_idx"])
        h = float(cell["h_m"])
        P0 = T.o[None] + (h + b.reshape(-1))[:, None] * n[None]
        lo, hi = TC.sublevel_many(T.alert, P0, u, -BAND_M)
        plo, phi = TC.sublevel_many(T.prot, P0, u, BAND_M)
        shift = (L + a.reshape(-1))
        xa = As[:, None] + shift[None, :]                          # (nA, nR·k) 关键点沿弦坐标
        ok = (xa >= lo[None]) & (xa <= hi[None])                   # nan → False
        bad_p = (xa > plo[None]) & (xa < phi[None])                # 开区间内 sdf < 10
        ok &= ~bad_p
        mask = ok.reshape(len(As), nR, -1).all(axis=2)
    memo[key] = mask
    while len(memo) > 64:
        memo.popitem(last=False)
    return mask


def _offs_key(slots):
    return (tuple((float(slots.offsets[m][0]).hex(), float(slots.offsets[m][1]).hex()) for m in slots.order),
            float(slots.spacing_m).hex())


# ---------------------------------------------------------------- 出口（解析）

def _exit_terminal(ctx, T, E, u_out, n_out, offs, l_star):
    """出口局部坐标：成员 i 车道 E + d_i n_out + X u_out，编组站点 x ↔ X = x + l_i。返回 (dict, None) 或 (None, 原因)。"""
    from . import transit_chords as TC
    P = ctx.params
    ls = offs[:, 0]
    P0 = E[None] + offs[:, 1][:, None] * n_out[None]
    Xse = l_star + ls
    pts = P0 + Xse[:, None] * u_out[None]
    from ..scene.exact import signed_distance
    if not (np.all(np.asarray(signed_distance(T.alert, pts)) <= -BAND_M)
            and np.all(np.asarray(signed_distance(T.prot, pts)) >= BAND_M)):
        return None, "expand_end_outside_band"
    wlo, whi = TC.sublevel_many(T.warn, P0, u_out, 0.0)
    if np.any(np.isnan(wlo)) or np.any(Xse < wlo) or np.any(Xse > whi):
        return None, "exit_no_warning"
    x0 = float(np.max(whi - ls))
    # 出口车道合法 run：与 transit_chords._sample_lanes 同一规则（5 m 倍数 ∪ 世界区间两端，base 场下界 ≥ q）
    field, base = TC.base_field(ctx, T.target, intent="feint")
    names = [c.name for c in base]
    glo, ghi = TC.sublevel_many(ctx.world, P0, u_out, -float(P["world_margin_m"]))
    runs = []
    for i in range(len(offs)):
        if np.isnan(glo[i]) or not ghi[i] > glo[i]:
            return None, "exit_world"
        k0, k1 = math.ceil(glo[i] / TC.X_STEP_M), math.floor(ghi[i] / TC.X_STEP_M)
        xs = np.unique(np.r_[glo[i], TC.X_STEP_M * np.arange(k0, k1 + 1), ghi[i]])
        xs = xs[(xs >= glo[i]) & (xs <= ghi[i])]
        ok = field.min_lower_clearance(P0[i][None] + xs[:, None] * u_out[None], names) >= TC.Q_M
        edges = np.flatnonzero(np.diff(np.r_[False, ok, False].astype(np.int8)))
        R = None
        for a, b in zip(edges[::2], edges[1::2]):
            if float(xs[a]) - 1e-9 <= Xse[i] <= float(xs[b - 1]) + 1e-9:
                R = (float(xs[a]), float(xs[b - 1]))
        if R is None:
            return None, "exit_blocked"
        runs.append(R)
    rhi = np.array([r[1] for r in runs])
    r50 = {f.id: TC.sublevel_many(f.layers["warning"], P0, u_out, TC.RETREAT_M) for f in ctx.facilities}
    xt = None
    k = 0
    while True:
        x = x0 + TC.X_STEP_M * k
        X = x + ls
        if np.any(X > rhi + 1e-9):
            break
        if x >= l_star - 1e-9:
            good = True
            for lo, hi in r50.values():
                inside = ~np.isnan(lo) & (lo < X) & (X < hi)
                if inside.any():
                    good = False
                    break
            if good:
                xt = float(x)
                break
        k += 1
    if xt is None:
        return None, "no_terminal"
    Tp = P0 + (xt + ls)[:, None] * u_out[None]
    for f in ctx.facilities:
        sd = np.asarray(signed_distance(f.layers["warning"], Tp))
        if not np.all(sd >= T.retreat):
            return None, "terminal_clearance"
    return {"x0": x0, "x_t": xt, "runs": runs, "terminal_points": Tp}, None


# ---------------------------------------------------------------- 认证

def _geometry(T, cell, cand, L):
    th, u, n = _frame(cell["theta_idx"])
    h = float(cell["h_m"])
    A = T.o + float(cand["A_m"]) * u + h * n
    B = A + L * u
    core, Dp, h_out = MT._core(cand["kind"], B, th, float(cand["radius_m"]), int(cand["side"]))
    u_out = np.array([math.cos(h_out), math.sin(h_out)])
    n_out = np.array([-u_out[1], u_out[0]])
    E = np.asarray(Dp, float) + L * u_out
    return NS(theta=th, u=u, n=n, h=h, A=A, B=B, core=list(core), D=np.asarray(Dp, float), h_out=float(h_out),
              u_out=u_out, n_out=n_out, E=E)


def turn_primitives(g, L):
    prims = [("line", tuple(map(float, g.A)), tuple(map(float, g.B)))] if L > 0.0 else []
    prims += list(g.core)
    if L > 0.0:
        prims.append(("line", tuple(map(float, g.D)), tuple(map(float, g.E))))
    return prims


def window_reference(g, L, l_star, spacing):
    """支撑窗口参考：入口直线 [A − (2l* + pad + 1), A] → 收拢 → 核心 → 展开 → 出口直线 [E, E + 2l* + pad + 1]。
    返回 (Reference, schedule 事件 dict, s_range)。弧长 schedule 从本参考的图元接点下标计算。"""
    from .formation import make_reference
    from .path import sample_primitives
    ext = 2.0 * l_star + WINDOW_PAD_M + 1.0
    prims = [("line", tuple(map(float, g.A - ext * g.u)), tuple(map(float, g.A)))] + turn_primitives(g, L)
    prims.append(("line", tuple(map(float, g.E)), tuple(map(float, g.E + ext * g.u_out))))
    smp = sample_primitives(prims, spacing)
    iv = smp.intervals
    nturn = len(turn_primitives(g, L))
    iA = iv[0][1]
    iB = iv[1][1] if L > 0.0 else iA
    iE = iv[nturn][1]
    iD = iv[nturn - 1][1] if L > 0.0 else iE
    ref = make_reference(smp, {"feint_A": iA, "feint_B": iB, "feint_D": iD, "feint_E": iE}, ())
    ev = {"s_A": ref.marks["feint_A"], "s_B": ref.marks["feint_B"], "s_D": ref.marks["feint_D"],
          "s_E": ref.marks["feint_E"], "L": float(L)}
    s_range = (ev["s_A"] - l_star - WINDOW_PAD_M, ev["s_E"] + l_star + WINDOW_PAD_M)
    return ref, ev, s_range


def _line_points(p0, u, xa, xb, *, include_a, include_b):
    k = max(1, int(math.ceil((xb - xa) / STRAIGHT_STEP_M - 1e-12)))
    xs = np.linspace(xa, xb, k + 1)
    if not include_a:
        xs = xs[1:]
    if not include_b:
        xs = xs[:-1]
    return p0[None] + xs[:, None] * u[None]


def _cert_memo(ctx):
    return ctx.extra.setdefault(("feint_v18_cert_memo",), OrderedDict())


def certify_candidate(ctx, task, slots, cell, candidate, *, mode="exact", prune=False, stats=None):
    """返回 {"feasible": bool, "reason": 首因, "record": 完整记录或 None}。record 含 theta_idx/h_m/x_in/
    collect_D_candidates/A_m/kind/side/radius_m/primitives/landmarks_xy/collect_D_compatible/terminal_xy/
    terminal_x/schedule/certificate。只含确定性业务数据（无计时）。"""
    from .connect import crossing_analysis
    from .feint_chords import entry_at_A
    if mode not in MODES:
        raise ValueError(f"未知认证模式：{mode!r}")
    T = turn_context(ctx, task.target_id)
    L, l_star, offs = formation_params(slots)
    st = stats if stats is not None else {}

    def no(reason, **kw):
        st[reason] = st.get(reason, 0) + 1
        return {"feasible": False, "reason": reason, "record": None, **({"detail": kw} if kw else {})}
    ent = entry_at_A(ctx, task.target_id, slots, cell, float(candidate["A_m"]), L, l_star)
    if ent["reason"] is not None:
        return no(ent["reason"])
    kind, side = candidate["kind"], int(candidate["side"])
    if prune:
        As = ent["A_list"]
        ia = int(np.searchsorted(As, float(candidate["A_m"])))
        ir = int(np.argmin(np.abs(T.radii[kind] - float(candidate["radius_m"]))))
        if not keypoint_mask(ctx, task, slots, cell, kind, side)[ia, ir]:
            return no("prune_keypoints")
    g = _geometry(T, cell, candidate, L)
    # 支撑角点（成员折线上的精确节点：q = s_A 处 A + d_i n、q = s_E 处 E + d_i n_out）须在 alert −10 内、protected +10 外
    from ..scene.exact import signed_distance as _sd
    corners = np.vstack([g.A[None] + offs[:, 1][:, None] * g.n[None], g.E[None] + offs[:, 1][:, None] * g.n_out[None]])
    if not (np.all(np.asarray(_sd(T.alert, corners)) <= -BAND_M) and np.all(np.asarray(_sd(T.prot, corners)) >= BAND_M)):
        return no("support_corner_outside_band")
    if prune:
        from ..scene.exact import signed_distance
        from .path import sample_primitives
        cxy = sample_primitives(g.core, ctx.params["curve_spacing_m"]).xy
        if not (np.all(np.asarray(signed_distance(T.alert, cxy)) <= -BAND_M)
                and np.all(np.asarray(signed_distance(T.prot, cxy)) >= BAND_M)):
            return no("prune_core_exact")
        from . import transit_chords as TC
        bf, base = TC.base_field(ctx, T.target, intent="feint")
        lo = bf.min_lower_clearance(cxy, [c.name for c in base])
        if np.any(np.isfinite(lo) & (lo + 2.0 * bf.eps < 0.0)):
            return no("prune_core_base_upper")
    ex, why = _exit_terminal(ctx, T, g.E, g.u_out, g.n_out, offs, l_star)
    if ex is None:
        return no(why)
    field = screen_field(ctx, T) if mode == "screened" else None
    # 支撑窗口派生（与模式无关，按候选键做小 LRU，只省重复计算）
    mkey = (task.target_id, _offs_key(slots), int(cell["theta_idx"]), float(cell["h_m"]), float(candidate["A_m"]),
            kind, side, float(candidate["radius_m"]))
    memo = _cert_memo(ctx)
    if mkey in memo:
        ref, ev, lanes = memo[mkey]
    else:
        ref, ev, s_range = window_reference(g, L, l_star, ctx.params["curve_spacing_m"])
        wslots = NS(order=tuple(slots.order), offsets=dict(slots.offsets), spacing_m=slots.spacing_m)
        lanes, _, ls_mt = MT.derive_deforming_members(ref, wslots, [ev], s_range,
                                                      spacing_m=ctx.params["curve_spacing_m"])
        if abs(ls_mt - l_star) > 1e-9:
            raise ValueError(f"l* 不一致：{ls_mt} vs {l_star}")
        ev = {**ev, "l_star": float(ls_mt)}
        memo[mkey] = (ref, ev, lanes)
        while len(memo) > _CERT_MEMO:
            memo.popitem(last=False)
    ok, first = deformation_passes(lanes, [ev], T.alert, T.prot, T.cross, band_m=BAND_M, mode=mode, field=field,
                                   detail=True, stats=st)
    if not ok:
        st["deformation_piece:" + first["piece"]] = st.get("deformation_piece:" + first["piece"], 0) + 1
        return no("deformation_support", **first)
    Ds = list(ent["D_list"])
    D0 = float(Ds[0])
    xc0 = float(cell["x_in"]) - D0
    order = list(slots.order)
    polys = {}
    for i, m in enumerate(order):
        l_i, d_i = (float(v) for v in slots.offsets[m])
        lane = lanes[m]
        p_in = T.o + (g.h + d_i) * g.n
        # 窗口起点的车道坐标：q0 = s_w0 + l_i ↔ X = A_m + (q0 − s_A)
        Xw0 = float(candidate["A_m"]) + (float(lane.s_ref[0]) - ev["s_A"])
        Xc = xc0 + l_i
        if not Xc < Xw0 - 1e-9:
            return no("window_overlap_entry")
        pre = _line_points(p_in, g.u, Xc, Xw0, include_a=True, include_b=False)
        p_out = g.E + d_i * g.n_out
        Xw1 = float(lane.s_ref[-1]) - ev["s_E"]
        Xt = ex["x_t"] + l_i
        if not Xt > Xw1 + 1e-9:
            return no("window_overlap_exit")
        post = _line_points(p_out, g.u_out, Xw1, Xt, include_a=False, include_b=True)
        polys[m] = np.vstack([pre, lane.xy, post])
    for m in order:
        if not clearance_passes(T.base, polys[m], mode=mode, field=field, stats=st):
            return no("base_clearance", member=m)
    band, align = ctx.params["pre_entry_warning_clearance_m"], ctx.params["alignment_length_m"]
    crossings = {}
    for m in order:
        viol, cross = crossing_analysis(polys[m], T.cross, T.target, band_m=band, align_m=align)
        if viol:
            return no("boundary_crossing", member=m, kind=viol[0]["kind"], facility=viol[0]["facility"])
        for key in (T.target, T.alert_key):
            dirs = [c.direction for c in cross if c.facility_id == key]
            if dirs != ["in", "out"]:
                return no("target_layer_crossing", member=m, boundary=key, directions=dirs)
        crossings[m] = [(c.facility_id, c.direction) for c in cross]
    # 相容集合距离：最小 D 的折线已全检；更大 D 只多一段入口延长弦（同一直线、格级已查带/槽位），逐成员 base 精确
    comp = [D0]
    for D in Ds[1:]:
        xc = float(cell["x_in"]) - float(D)
        good = True
        for m in order:
            l_i, d_i = (float(v) for v in slots.offsets[m])
            p_in = T.o + (g.h + d_i) * g.n
            seg = np.array([p_in + (xc + l_i) * g.u, p_in + (xc0 + l_i) * g.u])
            if not clearance_passes(T.base, seg, mode=mode, field=field, stats=st):
                good = False
                break
        if good:
            comp.append(float(D))
    st["feasible"] = st.get("feasible", 0) + 1
    prims = turn_primitives(g, L)
    term_ref = g.E + ex["x_t"] * g.u_out
    rec = {"theta_idx": int(cell["theta_idx"]), "h_m": float(cell["h_m"]), "x_in": float(cell["x_in"]),
           "collect_D_candidates": [float(x) for x in cell["collect_D_candidates"]],
           "A_m": float(candidate["A_m"]), "kind": kind, "side": side, "radius_m": float(candidate["radius_m"]),
           "L_m": float(L), "l_star_m": float(l_star), "primitives": [list(p) for p in prims],
           "landmarks_xy": {k: [float(v[0]), float(v[1])] for k, v in
                            (("A", g.A), ("B", g.B), ("D", g.D), ("E", g.E), ("terminal", term_ref))},
           "exit_heading_rad": float(g.h_out), "terminal_x": float(ex["x_t"]), "exit_s0_x": float(ex["x0"]),
           "terminal_xy": [float(term_ref[0]), float(term_ref[1])],
           "collect_D_compatible": comp,
           "schedule": {k: float(ev[k]) for k in ("s_A", "s_B", "s_D", "s_E", "L", "l_star")},
           "certificate": {"mode": mode, "prune": bool(prune), "version": VERSION, "crossings": crossings}}
    return {"feasible": True, "reason": None, "record": rec}
