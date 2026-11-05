"""V8-14 第 3 部分：收拢—单车道掉头—接回—展开的整体可行集合与变队形成员映射（指令第 3 节；附录裁定 4）。

整体候选 = A→B 收拢直线（B = A + L t_A）+ 单车道掉头核心（U/斜切/泪滴，左右两侧，半径 R ≥ 1.05 R_min）+
核心末端到 D = E − L t_E 的五次 Bézier 姿态连接（h₀,h₁ ∈ {2Q/5,…,2Q}，Q = |D − 核心末端|；Q 在 NODE_TOL 内且切向
一致时为空连接）+ D→E 展开直线（E 为反向巡逻弧上的 1° 接回点）。整个候选在原完整巡逻走廊内认证后才可抽中；
抽中后直接取记录里的图元，不重新连接。

裁定 4：参数格 = R ∈ {R₀ + 2k ≤ R₀ + W_j} × 接回点（弧长距离 ≤ 2W_j + 2L 的 1° 方位点）× (h₀,h₁) 5×5；
每个（类别×侧向）组合用 connect 流对整个参数格做一次均匀随机排列，按序认证、取第一个通过者（与"全枚举后均匀抽一个"
同分布）；排列走完无通过者即该组合为空。之后在非空组合中等概率选一个。认证谓词按"收拢 → 核心 → 展开 → 曲率 →
采样点 → 全部弦"短路并缓存只依赖部分参数的子结果，只省计算，不改谓词。

变队形（指令 3.3）：q_i(s) = s + l_i(s) 严格递增；成员位置 p_i = c(q) + d̃_i(q) n(q)。d̃ 只在 A→B、D→E 直线上
按 H(x) = 3x² − 2x³ 变化，核心与接回连接上恒为 0；l_i 的收拢段放在 [s_A − l*, s_B − l*]、展开段放在
[s_D + l*, s_E + l*]。纯数值函数导入时不加载 shapely。
"""
import math
from dataclasses import dataclass

import numpy as np

from .monitoring_band import cubic_blend

NODE_TOL_M = 1e-6
KINDS = ("teardrop", "u", "oblique")
SIDES = (+1, -1)
H_GRID = 5                       # 旧 _build_turn 的 connect_poses(grid=5) 分辨率
SWEEP = {"u": math.pi, "oblique": 5.0 * math.pi / 6.0}


# ---------------------------------------------------------------- 纯数值

def column_offsets(n, spacing_m):
    """纵列沿迹位置 l_i^col = j_i·b（j_i = i − (n−1)/2，按槽位顺序 i），与 formation_slots 的 column 一致。"""
    return (np.arange(n) - (n - 1) / 2.0) * float(spacing_m)


def collapse_length_m(offsets, *, spacing_m, speed_max_m_s, command_max_m_s, dynamic_factor, curvature_limit):
    """offsets：按槽位顺序的 (l, d) 数组。L_min = max{3D·v_cmd/(2v⊥*), 1.5Δl*, √(6D/κ*)}，L = 2(1+⌊L_min/2⌋)；
    v⊥* = √((f·v_max)² − v_cmd²)。已是纵列且 Δl = 0 时 L = 0。"""
    off = np.asarray(offsets, float).reshape(-1, 2)
    n = len(off)
    lcol = column_offsets(n, spacing_m)
    D = float(np.max(np.abs(off[:, 1]))) if n else 0.0
    dl = float(np.max(np.abs(lcol - off[:, 0]))) if n else 0.0
    if D == 0.0 and dl == 0.0:
        return 0.0
    v2 = (float(dynamic_factor) * float(speed_max_m_s)) ** 2 - float(command_max_m_s) ** 2
    if not v2 > 0.0:
        raise ValueError("配置前提不相容：f·v_max ≤ v_cmd,max，横向收拢速率无定义")
    v_perp = math.sqrt(v2)
    L_min = max(3.0 * D * float(command_max_m_s) / (2.0 * v_perp), 1.5 * dl, math.sqrt(6.0 * D / float(curvature_limit)))
    return 2.0 * (1.0 + math.floor(L_min / 2.0))


def certify_joint_candidates(candidates, certify_whole):
    """小规模穷举：按给定顺序认证全部候选，返回已认证者（不接受 RNG）。"""
    return [c for c in candidates if certify_whole(c)]


def choose_joint_turn(options, rng):
    """在已认证完整记录中：先在非空（类别, 侧向）组合中等概率选一组，再在组内等概率选一条。空表返回 None。"""
    if not options:
        return None
    groups, order = {}, []
    for o in options:
        k = (o["kind"], o["side"])
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(o)
    g = groups[order[int(rng.integers(0, len(order)))]]
    return g[int(rng.integers(0, len(g)))]


# ---------------------------------------------------------------- 变队形成员映射

@dataclass(frozen=True)
class DeformLane:
    member_id: str
    xy: np.ndarray           # 成员车道（不含起点连接）
    s_ref: np.ndarray        # 移位后参考弧长 q（成员几何点在参考上的站点）
    s_group: np.ndarray      # 编组参考弧长 s（q = s + l(s)）
    lateral_m: np.ndarray    # d̃(q)
    turn_mask: np.ndarray    # q 落在掉头核心与接回连接内
    d_m: float
    l_m: float


class LongitudinalSchedule:
    """l(s)：分段常数 + 三次形变；严格保证 1 + l'(s) > 0（由 L ≥ 1.5Δl* 的严格向上取整保证）。"""

    def __init__(self, l0, pieces):
        self.l0 = float(l0)
        self.pieces = [(float(a), float(b), float(x0), float(x1)) for a, b, x0, x1 in pieces if b > a and x0 != x1]

    def __call__(self, s):
        s = np.asarray(s, float)
        out = np.full(s.shape, self.l0)
        cur = self.l0
        for a, b, x0, x1 in self.pieces:
            out = np.where(s >= b, x1, out)
            mid = (s > a) & (s < b)
            out = np.where(mid, x0 + (x1 - x0) * cubic_blend((s - a) / (b - a)), out)
            cur = x1
        return out

    def q(self, s):
        return np.asarray(s, float) + self(s)

    def inverse(self, q, span):
        """q(s) 的反函数（逐元素二分到浮点精度）。"""
        q = np.asarray(q, float)
        lo = q - span - 1.0
        hi = q + span + 1.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            f = self.q(mid) < q
            lo = np.where(f, mid, lo)
            hi = np.where(f, hi, mid)
            if np.all((hi - lo) <= 4.0 * np.finfo(float).eps * np.maximum(1.0, np.abs(q))):
                break
        return 0.5 * (lo + hi)


def lateral_profile(d, schedule):
    """d̃(q)：A→B 上 d(1 − H)，B→D 为 0，D→E 上 d·H，其余为 d。"""
    def f(q):
        q = np.asarray(q, float)
        out = np.full(q.shape, float(d))
        for ev in schedule:
            sA, sB, sD, sE, L = ev["s_A"], ev["s_B"], ev["s_D"], ev["s_E"], ev["L"]
            if L > 0.0:
                m = (q >= sA) & (q <= sB)
                out = np.where(m, d * (1.0 - cubic_blend((q - sA) / L)), out)
                m = (q >= sD) & (q <= sE)
                out = np.where(m, d * cubic_blend((q - sD) / L), out)
            out = np.where((q >= sB) & (q <= sD), 0.0, out)
        return out
    return f


def longitudinal_schedule(l_slot, l_col, schedule, l_star):
    pieces = []
    for ev in schedule:
        pieces.append((ev["s_A"] - l_star, ev["s_B"] - l_star, l_slot, l_col))
        pieces.append((ev["s_D"] + l_star, ev["s_E"] + l_star, l_col, l_slot))
    return LongitudinalSchedule(l_slot, pieces)


def _densify_rows(xy, cols, limit):
    ch = np.hypot(*np.diff(xy, axis=0).T)
    if not np.any(ch > limit):
        return xy, cols
    out_xy = [xy[0]]
    out_c = [[c[0]] for c in cols]
    for i in range(len(ch)):
        k = int(math.ceil(ch[i] / limit))
        if k > 1:
            f = np.arange(1, k) / k
            out_xy.extend(xy[i] + f[:, None] * (xy[i + 1] - xy[i]))
            for c, oc in zip(cols, out_c):
                oc.extend(c[i] + f * (c[i + 1] - c[i]))
        out_xy.append(xy[i + 1])
        for c, oc in zip(cols, out_c):
            oc.append(c[i + 1])
    return np.array(out_xy), [np.array(oc) for oc in out_c]


def derive_deforming_members(reference, slots, schedule, s_range, *, spacing_m, marks=(), max_chord_m=0.9):
    """返回 ({成员: DeformLane}, {成员: LongitudinalSchedule}, l*)。schedule 为每次掉头的
    {"s_A","s_B","s_D","s_E","L"}（参考弧长）；s_range = (s_c, s_t) 为编组站点范围。
    成员 i 的 q 域 = [s_c + l_i, s_t + l_i]（l(s_c) = l(s_t) = 槽位 l_i）。超出参考范围抛 ValueError。"""
    R = reference
    s_c, s_t = (float(x) for x in s_range)
    n = len(slots.order)
    lcol = column_offsets(n, slots.spacing_m)
    l_star = max([max(abs(slots.offsets[m][0]), abs(lcol[i])) for i, m in enumerate(slots.order)] or [0.0])
    lanes, scheds = {}, {}
    ev_q = sorted({float(ev[k]) for ev in schedule for k in ("s_A", "s_B", "s_D", "s_E")})
    for i, m in enumerate(slots.order):
        l_i, d_i = (float(v) for v in slots.offsets[m])
        ls = longitudinal_schedule(l_i, float(lcol[i]), schedule, l_star) if schedule else LongitudinalSchedule(l_i, [])
        a, b = s_c + l_i, s_t + l_i
        if a < -1e-9 or b > R.s[-1] + 1e-9:
            raise ValueError(f"成员 {m} 的站点范围 [{a}, {b}] 超出参考 [0, {R.s[-1]}]")
        a, b = max(a, 0.0), min(b, float(R.s[-1]))
        special_s = [s_c, s_t] + [float(x) for x in marks] + [p for pc in ls.pieces for p in pc[:2]]
        special_s = [x for x in special_s if s_c <= x <= s_t]
        special_q = ls.q(np.array(special_s)) if special_s else np.zeros(0)
        nodes = np.concatenate([[a, b], R.s[(R.s > a) & (R.s < b)], [x for x in ev_q if a < x < b], special_q])
        nodes = np.unique(np.clip(nodes, a, b))
        keep = np.r_[True, np.diff(nodes) > 1e-9]
        q = nodes[keep]
        s = ls.inverse(q, l_star + abs(l_i)) if ls.pieces else q - l_i
        # 特殊站点用定义值（避免二分舍入），起终点精确
        for sv, qv in zip(special_s, special_q.tolist()):
            k = int(np.argmin(np.abs(q - qv)))
            if abs(q[k] - qv) <= 1e-9:
                s[k] = sv
        cx, cy = np.interp(q, R.s, R.xy[:, 0]), np.interp(q, R.s, R.xy[:, 1])
        th = np.interp(q, R.s, R.theta)
        nrm = np.stack([-np.sin(th), np.cos(th)], axis=1)
        dl = lateral_profile(d_i, schedule)(q) if schedule else np.full(len(q), d_i)
        xy = np.stack([cx, cy], axis=1) + dl[:, None] * nrm
        mask = np.zeros(len(q), bool)
        for ev in schedule:
            mask |= (q >= ev["s_B"]) & (q <= ev["s_D"])
        xy, (q, s, dl, mk) = _densify_rows(xy, [q, s, dl, mask.astype(float)], max_chord_m)
        mask = mk >= 1.0 - 1e-12
        for name, col in (("s_ref", q), ("s_group", s)):
            if not np.all(np.diff(col) > 0.0):
                raise ValueError(f"成员 {m} 的 {name} 不严格递增")
        if not np.all(np.hypot(*np.diff(xy, axis=0).T) > 0.0):
            raise ValueError(f"成员 {m} 的车道出现零长度弦")
        lanes[m] = DeformLane(m, xy, q, s, dl, mask, d_i, l_i)
        scheds[m] = ls
    return lanes, scheds, l_star


# ---------------------------------------------------------------- 整体掉头可行集合（场景几何惰性）

def _exact_ok(cons, xy, margin=0.0):
    from ..scene.exact import polyline_clearance
    for c in cons:
        m = polyline_clearance(c.geometry, xy, sense=c.sense, minimum_m=c.minimum_m, fast_far_m=5.0 + margin)
        if not float(np.min(m)) >= margin:
            return False
    return True


def _points_ok(cons, pts):
    from ..scene.exact import clearance_values
    ok = np.ones(pts.shape[:-1], bool)
    flat = pts.reshape(-1, 2)
    for c in cons:
        ok &= (clearance_values(c.geometry, flat, sense=c.sense, minimum_m=c.minimum_m) >= 0.0).reshape(ok.shape)
    return ok


def _unit(h):
    return np.array([math.cos(h), math.sin(h)])


def _deform_line_points(P0, t, L, d, rising, spacing):
    """直线 P0 → P0 + L t 上横向偏移 d·(1−H) 或 d·H 的成员车道（参考节点同一采样）。"""
    from .path import _line
    xy, _, _ = _line(P0, P0 + L * t, spacing)
    x = np.linalg.norm(xy - P0[None], axis=1) / L
    w = cubic_blend(x) if rising else 1.0 - cubic_blend(x)
    nrm = np.array([-t[1], t[0]])
    return xy + (d * w)[:, None] * nrm[None]


class TurnSetup:
    """一次掉头的固定输入（来自已构造的巡逻曲线与队形）。"""

    def __init__(self, *, center, rho0, coef, phi_end, direction, phi_other, L, width_m, lateral_offsets, cons,
                 r_min, spacing_m, facility_center, min_true_deg, l_star, kappa_guidance):
        self.c = np.asarray(center, float)
        self.rho0, self.coef = float(rho0), np.asarray(coef, float)
        self.phi_end, self.dir, self.phi_other = float(phi_end), float(direction), float(phi_other)
        self.L, self.W = float(L), float(width_m)
        self.offsets = sorted({float(d) for d in lateral_offsets})
        self.cons = list(cons)
        self.r_min = dict(r_min)
        self.spacing = float(spacing_m)
        self.fc = np.asarray(facility_center, float)
        self.min_true = float(min_true_deg)
        self.l_star = float(l_star)
        self.kappa_guidance = float(kappa_guidance)


def _pose(T, phi, direction):
    from .intents.monitoring import _loop_pose
    return _loop_pose(T.c, T.rho0, T.coef, phi, direction)


def _arc_length(T, phi_a, phi_b, steps_per_deg=8):
    from .path import periodic_radius
    n = max(2, int(abs(phi_b - phi_a) * 180.0 / math.pi * steps_per_deg) + 1)
    ph = np.linspace(phi_a, phi_b, n)
    r = periodic_radius(ph, T.rho0, T.coef)
    xy = T.c[None] + r[:, None] * np.stack([np.cos(ph), np.sin(ph)], axis=1)
    return float(np.hypot(*np.diff(xy, axis=0).T).sum())


def merge_candidates(T):
    """反向弧上 1° 接回点：弧长距离 ≤ 2W + 2L；下一次单向穿行的真实目标方位覆盖（端点精确）≥ 120°；
    下一次穿行长度 ≥ 2l*（形变支撑无重叠放置）。返回 [(row, φ_m, E, h_E, 弧长距离)]。"""
    from .monitoring_band import coverage_exact_deg
    from .path import periodic_radius
    step = 2.0 * math.pi / 360.0
    row_end = int(round(T.phi_end / step))
    row_other = int(round(T.phi_other / step))
    lim = 2.0 * T.W + 2.0 * T.L
    out = []
    k = 0
    r_other = float(periodic_radius(np.array([T.phi_other]), T.rho0, T.coef)[0])
    while True:
        row = row_end - int(T.dir) * k
        if (row - row_other) * T.dir <= 0:
            break
        phi_m = row * step
        dist = _arc_length(T, phi_m, T.phi_end) if k else 0.0
        if dist > lim:
            break
        rm = float(periodic_radius(np.array([phi_m]), T.rho0, T.coef)[0])
        if phi_m < T.phi_other:
            cov = coverage_exact_deg(T.c, T.fc, phi_m, rm, T.phi_other, r_other)
        else:
            cov = coverage_exact_deg(T.c, T.fc, T.phi_other, r_other, phi_m, rm)
        nxt = _arc_length(T, phi_m, T.phi_other)
        if abs(cov) >= T.min_true and nxt >= 2.0 * T.l_star:
            E, hE = _pose(T, phi_m, -T.dir)
            out.append((row, phi_m, E, hE, dist))
        k += 1
    return out


def _core(kind, B, hB, R, side):
    from .connect import MIN_STRAIGHT_M
    from .intents.monitoring import _turn_arcs, teardrop_primitives
    if kind == "teardrop":
        prims = teardrop_primitives(B, hB, R, MIN_STRAIGHT_M, side)
        return list(prims), np.asarray(B, float), hB + math.pi
    arc, end, h2 = _turn_arcs(B, hB, R, side, SWEEP[kind])
    return [arc], np.asarray(end, float), h2


def sample_joint_turn(T, rng, *, kinds=KINDS):
    """裁定 4：每组合一次随机排列取第一个通过者；返回 (每个非空组合的记录列表, 统计)。"""
    import time
    from .path import _bezier_batch, bezier5_controls, sample_primitives
    t0 = time.perf_counter()
    stats = {"combos": [], "collapse_ok": None}
    A, hA = _pose(T, T.phi_end, T.dir)
    tA = _unit(hA)
    B = A + T.L * tA
    delta = 0.0
    if T.L > 0.0:
        Dmax = max((abs(d) for d in T.offsets), default=0.0)
        delta = (6.0 * Dmax / T.L ** 2) * T.spacing ** 2 / 8.0     # 弦的拱高上界（插入节点时的偏差）
    collapse = [("line", tuple(A), tuple(B))] if T.L > 0.0 else []
    if T.L > 0.0:
        ok = all(_exact_ok(T.cons, _deform_line_points(A, tA, T.L, d, False, T.spacing), delta) for d in T.offsets)
        stats["collapse_ok"] = bool(ok)
        if not ok:
            stats["seconds"] = time.perf_counter() - t0
            return [], stats
    merges = merge_candidates(T)
    stats["merge_points"] = len(merges)
    expand_cache = {}

    def expand_ok(iM):
        if iM not in expand_cache:
            _, _, E, hE, _ = merges[iM]
            tE = _unit(hE)
            Dp = E - T.L * tE
            ok = True
            if T.L > 0.0:
                ok = all(_exact_ok(T.cons, _deform_line_points(Dp, tE, T.L, d, True, T.spacing), delta)
                         for d in T.offsets)
            expand_cache[iM] = (ok, Dp, tE)
        return expand_cache[iM]

    records = []
    for kind in kinds:
        R0 = 1.05 * float(T.r_min[kind])
        kmax = int(math.floor(T.W / 2.0 + 1e-12))
        radii = [R0 + 2.0 * k for k in range(kmax + 1)]
        kap_turn = 1.0 / R0
        for side in SIDES:
            nR, nM = len(radii), len(merges)
            N = nR * nM * H_GRID * H_GRID
            st = {"kind": kind, "side": side, "grid_total": N, "visited": 0, "core_pruned": 0, "expand_pruned": 0,
                  "connector_pruned": 0, "full_certified": 0, "feasible_found": False}
            stats["combos"].append(st)
            if N == 0:
                continue
            perm = rng.permutation(N)
            core_cache, conn_cache = {}, {}
            found = None
            for idx in perm.tolist():
                st["visited"] += 1
                iR, rem = divmod(idx, nM * H_GRID * H_GRID)
                iM, ih = divmod(rem, H_GRID * H_GRID)
                if iR not in core_cache:
                    prims, P1, h1 = _core(kind, B, hA, radii[iR], side)
                    try:
                        smp = sample_primitives(prims, T.spacing)
                        okc = _exact_ok(T.cons, smp.xy)
                    except ValueError:
                        okc = False
                    core_cache[iR] = (okc, prims, P1, h1)
                okc, prims, P1, h1 = core_cache[iR]
                if not okc:
                    st["core_pruned"] += 1
                    continue
                oke, Dp, tE = expand_ok(iM)
                if not oke:
                    st["expand_pruned"] += 1
                    continue
                key = (iR, iM)
                if key not in conn_cache:
                    t1 = _unit(h1)
                    Q = float(np.hypot(*(Dp - P1)))
                    if Q <= NODE_TOL_M:
                        same = abs(float(t1 @ tE) - 1.0) <= NODE_TOL_M
                        conn_cache[key] = ("empty", np.full(H_GRID * H_GRID, same), None, Q)
                    else:
                        hs = Q * np.linspace(0.0, 2.0, H_GRID + 1)[1:]
                        Ps = np.array([bezier5_controls(P1, t1, Dp, tE, a, b) for a in hs for b in hs], float)
                        n_t = int(min(max(math.ceil(3.0 * Q / 2.0) + 2, 60), 600))
                        pos, _, kp = _bezier_batch(Ps, n_t)
                        lim = min(kap_turn, T.kappa_guidance)
                        okk = np.max(np.abs(kp), axis=1) <= lim
                        okp = np.zeros(len(Ps), bool)
                        if okk.any():
                            okp[okk] = np.all(_points_ok(T.cons, pos[okk]), axis=1)
                        conn_cache[key] = ("bezier", okk & okp, Ps, Q)
                ctype, okv, Ps, Q = conn_cache[key]
                if not okv[ih]:
                    st["connector_pruned"] += 1
                    continue
                conn = []
                if ctype == "bezier":
                    bz = ("bezier5", tuple(map(tuple, Ps[ih])))
                    try:
                        smp = sample_primitives([bz], T.spacing)
                        okf = _exact_ok(T.cons, smp.xy)
                    except ValueError:
                        okf = False
                    if not okf:
                        okv[ih] = False
                        st["connector_pruned"] += 1
                        continue
                    conn = [bz]
                st["full_certified"] += 1
                row, phi_m, E, hE, dist = merges[iM]
                expand = [("line", tuple(Dp), tuple(E))] if T.L > 0.0 else []
                h0 = h1v = None
                if ctype == "bezier":
                    hs = Q * np.linspace(0.0, 2.0, H_GRID + 1)[1:]
                    h0, h1v = float(hs[ih // H_GRID]), float(hs[ih % H_GRID])
                found = {"kind": kind, "side": side, "radius_m": float(radii[iR]), "merge_phi": float(phi_m),
                         "merge_row": int(row), "merge_distance_m": float(dist), "h0_m": h0, "h1_m": h1v,
                         "primitives": tuple(collapse) + tuple(prims) + tuple(conn) + tuple(expand),
                         "parts": {"collapse": len(collapse), "core": len(prims), "connector": len(conn),
                                   "expand": len(expand)},
                         "schedule": {"L": T.L, "A": tuple(map(float, A)), "B": tuple(map(float, B)),
                                      "D": tuple(map(float, Dp)), "E": tuple(map(float, E))},
                         "certificate": {"grid_index": int(idx), "visited": st["visited"], "grid_total": N,
                                         "delta_m": delta}}
                st["feasible_found"] = True
                break
            if found is not None:
                records.append(found)
    stats["seconds"] = time.perf_counter() - t0
    return records, stats
