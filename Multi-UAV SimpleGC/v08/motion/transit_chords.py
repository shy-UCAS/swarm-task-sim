"""过境穿越弦的有限可行集合、精确弦检查、走廊与只读缓存（V8-16 指令 3.2–3.4、附录裁定 1–2；本项新增）。

坐标：原点 o = 目标中心，u = (cos θ, sin θ)，n = (−sin θ, cos θ)（u 的左法向）。航向 θ = 0, 20, …, 340°，
编组参考线横向偏移 h = 5k m（范围 = 目标 warning 外接框在 n 上的投影），沿线采样 5 m。抽取的是离散格点本身，
不在格内抖动。成员 i 的车道为 o + x u + (h + d_i) n，编组站点 x 处成员在车道坐标 x + l_i（l_i、d_i 来自真实槽位）。

单车道缓存（附录裁定 2）：对每个（目标，航向，车道横向偏移）只算一次：
  - 世界内 35 m 的精确直线区间（凸多边形半平面裁剪）；
  - 沿线 5 m 采样（含区间两端）上 base 约束的距离场下界（lower_clearance，已扣 ε_f）是否 ≥ q = 2.5 m；
    相邻采样点距 ≤ 5 m，任意点到最近采样点 ≤ 2.5 m，1-Lipschitz ⇒ 连续成立；合法集合 = 连续合格采样点的闭区间并；
  - 每个设施 warning 的精确次水平集区间 {sdf ≤ c}，c ∈ {+10, 0, −10, +50}（Circle 二次方程；凸多边形半平面；
    BufferedPolygon 在 c + b > 0 时为多边形 ∪ 各边胶囊（矩形条带 ∪ 顶点圆盘）的并）。
队形检验只做组合：各车道对单车道结果的查表与区间运算，不按人数、队形、二分步长重算几何。门禁：组合与逐车道
直接重算的结果在 5 个目标 × 3 种人数上逐格比对（tools/v08/run_transit_v16.py --stage chord-gate）。

一格可行的条件（全部真实车道）：
  1. 每条车道与目标 warning 恰有一个正长度交区间，且到达 warning 内 10 m（{sdf ≤ −10} 非空）；
  2. 终止站点：从最后车道出圈的编组站点起按 5 m 向前，第一个全员距所有 warning ≥ 50 m 的站点；途中任一成员离开
     自己车道的合法区间即本格没有终点（不在非法区继续穿出后重新取点）；
  3. 集合站点候选 x_c = x_in − D，D ∈ {100, 110, …, 400}（复用监视 _plan_ingress 的 Ds 枚举），x_in 为最早车道入圈的
     编组站点：参考点目标 warning 有符号距离 ∈ [50, 250]、每个成员槽位满足原 collect_phys 组合栅格
     （base + 所有 warning 外 10 m）、每条车道从 min(槽位, 最早入圈前 210 m) 到终点都在同一合法区间内、
     其他设施 warning 在 [槽位, 终点] 上要么整段 |sdf| ≥ 10 要么完整深穿越（≥ 10 m）；
  4. 至少一个候选。
"""
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

from ..scene.exact import GeometryError, _buffer, _circle, _poly, kind_of, signed_distance

THETA_STEP_DEG = 20
H_STEP_M = 5.0
X_STEP_M = 5.0
Q_M = 2.5                         # 5 m 沿线采样的覆盖半径（grid_error_m(5, 5)["sampling_q_m"]）
BAND_M = 10.0
RETREAT_M = 50.0
ALIGN_M = 100.0
PRE_ENTRY_SCAN_M = 210.0          # 100 对齐 + 10 穿越带 + 100 转入预留（U C.1）
COLLECT_DS = tuple(float(d) for d in np.arange(100.0, 401.0, 10.0))   # = monitoring _plan_ingress 的 Ds
COLLECT_BAND = (50.0, 250.0)
Y_STEP_M = 2.0
CACHE_VERSION = "v16-chords-1"
ALIGN_TOL_M = 1e-6                # = connect.NODE_TOL_M：冻结 crossing_analysis 判 100 m 对齐不足时的节点容差


# ---------------------------------------------------------------- 精确直线次水平集区间（批量；标量版调用同一批量函数）

def _disk_many(P0, u, center, r):
    wx, wy = P0[:, 0] - center[0], P0[:, 1] - center[1]
    xm = -(wx * u[0] + wy * u[1])
    d2 = (wx * wx + wy * wy) - xm * xm
    rem = r * r - d2
    ok = rem >= 0.0
    half = np.sqrt(np.where(ok, rem, 0.0))
    return np.where(ok, xm - half, np.nan), np.where(ok, xm + half, np.nan)


def _halfplanes_many(P0, u, a, d, length, shift):
    """凸多边形（逆时针 a, d）内收 shift（≥ 0）的半平面交：cross(d, p − a)/|d| ≥ shift。"""
    N = len(P0)
    lo, hi = np.full(N, -np.inf), np.full(N, np.inf)
    empty = np.zeros(N, bool)
    for k in range(len(a)):
        c0 = d[k, 0] * (P0[:, 1] - a[k, 1]) - d[k, 1] * (P0[:, 0] - a[k, 0])
        c1 = float(d[k, 0] * u[1] - d[k, 1] * u[0])
        rhs = shift * float(length[k])
        if c1 == 0.0:
            empty |= c0 < rhs
            continue
        x = (rhs - c0) / c1
        if c1 > 0:
            lo = np.maximum(lo, x)
        else:
            hi = np.minimum(hi, x)
    bad = empty | ~(lo <= hi)
    return np.where(bad, np.nan, lo), np.where(bad, np.nan, hi)


def _capsule_many(P0, u, A, B, r):
    """线段 AB ⊕ 圆盘 r 与直线的交区间（各起点一条线）。"""
    ex, ey = float(B[0] - A[0]), float(B[1] - A[1])
    L = math.hypot(ex, ey)
    tx, ty = ex / L, ey / L
    nx, ny = -ty, tx
    wx, wy = P0[:, 0] - A[0], P0[:, 1] - A[1]
    N = len(P0)
    lo, hi = np.full(N, -np.inf), np.full(N, np.inf)
    empty = np.zeros(N, bool)
    for c0, c1, lo_v, hi_v in ((nx * wx + ny * wy, nx * u[0] + ny * u[1], -r, r),
                               (tx * wx + ty * wy, tx * u[0] + ty * u[1], 0.0, L)):
        c1 = float(c1)
        if c1 == 0.0:
            empty |= ~((lo_v <= c0) & (c0 <= hi_v))
            continue
        x1, x2 = (lo_v - c0) / c1, (hi_v - c0) / c1
        lo, hi = np.maximum(lo, np.minimum(x1, x2)), np.minimum(hi, np.maximum(x1, x2))
    bad = empty | ~(lo <= hi)
    parts = [(np.where(bad, np.nan, lo), np.where(bad, np.nan, hi)),
             _disk_many(P0, u, A, r), _disk_many(P0, u, B, r)]
    return parts


def sublevel_many(geometry, P0, u, c):
    """多条平行直线 P0[k] + x u 上 {x : sdf ≤ c} 的精确闭区间（凸形状 ⇒ 单一区间）；返回 (lo, hi)，空为 nan。
    Circle：二次方程；凸 Polygon：半平面裁剪；BufferedPolygon：c + b ≤ 0 时内收半平面，否则多边形 ∪ 各边胶囊
    （矩形条带 ∪ 顶点圆盘）的并（凸集的 Minkowski 和与直线的交为单一区间，取各部分端点的最小/最大）。"""
    P0 = np.asarray(P0, float).reshape(-1, 2)
    u = np.asarray(u, float)
    t = kind_of(geometry)
    if t == "Circle":
        center, r = _circle(geometry)
        if r + c < 0.0:
            return np.full(len(P0), np.nan), np.full(len(P0), np.nan)
        return _disk_many(P0, u, center, r + c)
    a, d, _len2, length = _poly(geometry)
    cc = float(c) + _buffer(geometry)
    if cc <= 0.0:
        return _halfplanes_many(P0, u, a, d, length, -cc)
    parts = [_halfplanes_many(P0, u, a, d, length, 0.0)]
    for k in range(len(a)):
        parts.extend(_capsule_many(P0, u, a[k], a[(k + 1) % len(a)], cc))
    los = np.stack([p[0] for p in parts])
    his = np.stack([p[1] for p in parts])
    allnan = np.all(np.isnan(los), axis=0)
    lo = np.where(allnan, np.nan, np.nanmin(np.where(np.isnan(los), np.inf, los), axis=0))
    hi = np.where(allnan, np.nan, np.nanmax(np.where(np.isnan(his), -np.inf, his), axis=0))
    return lo, hi


def line_sublevel(geometry, p0, u, c):
    """单条直线 p0 + x u 上 {x : sdf ≤ c} 的精确闭区间，空则 None（与 sublevel_many 同一计算）。"""
    lo, hi = sublevel_many(geometry, np.asarray(p0, float)[None, :2], u, c)
    if np.isnan(lo[0]):
        return None
    return (float(lo[0]), float(hi[0]))


# ---------------------------------------------------------------- 约束与组合栅格

def _ikey(name, intent, target_id):
    """进程内缓存键：transit 沿用原键 ("transit_<name>", target)；其他意图用独立键（V8-17 指令 3.3）。"""
    return ("transit_" + name, target_id) if intent == "transit" else (f"{intent}_{name}", target_id)


def transit_base(ctx, target_id, *, intent="transit"):
    """过境 base 约束（进程内按目标缓存；调用方不得修改返回的列表）。V8-17：intent 参数化，intrusion 分支调用
    constraints_for_task 的 intrusion base 并用独立缓存键；transit 分支执行原语句、用原缓存键。"""
    key = _ikey("base", intent, target_id)
    if key not in ctx.extra:
        from ..contract.monitoring import TaskSpec
        from .layer_limits import constraints_for_task
        ctx.extra[key] = constraints_for_task(ctx, TaskSpec("task0", intent, target_id))
    return ctx.extra[key]


def base_field(ctx, target_id, *, intent="transit"):
    key = _ikey("base_field", intent, target_id)
    if key not in ctx.extra:
        from .layer_limits import constraints_identity
        base = tuple(transit_base(ctx, target_id, intent=intent)["base"])
        ctx.extra[key] = (ctx.field(("route", intent, constraints_identity(base)), list(base)), base)
    return ctx.extra[key]


def collect_phys_grid(ctx, target_id, *, intent="transit"):
    key = _ikey("collect_phys", intent, target_id)
    if key in ctx.extra:
        return ctx.extra[key]
    from ..scene.field import Clearance
    from .layer_limits import constraints_identity
    base = list(transit_base(ctx, target_id, intent=intent)["base"])
    P = ctx.params
    phys = base + [Clearance("out_warning:" + f.id, f.layers["warning"], 1, P["pre_entry_warning_clearance_m"])
                   for f in ctx.facilities]
    ctx.extra[key] = ctx.combined(("collect_phys", intent, constraints_identity(phys)), phys)
    return ctx.extra[key]


def entry_planner(ctx, target_id, delta_m):
    """可视图骨架规划器（过境首次入圈前）：world 内缩 35 + Δ，障碍外扩 35 + Δ，所有设施 alert 外扩 10 + Δ，
    再加目标 warning 外扩 10 + Δ（指令 3.1：图搜索本身绕过目标 warning）。缓存键含目标、Δ 与有序 blockers 身份。"""
    from ..scene.exact import expand
    from ..scene.field import geometry_key
    from ..scene.visibility import build_planner
    P = ctx.params
    tgt = ctx.facility_by_id[target_id]
    blockers = [("obstacle:" + i, expand(g, P["obstacle_margin_m"] + delta_m)) for i, g in ctx.obstacles]
    blockers += [("alert:" + f.id, expand(f.layers["alert"], P["forbidden_margin_m"] + delta_m)) for f in ctx.facilities]
    blockers += [("preentry_warning:" + target_id,
                  expand(tgt.layers["warning"], P["pre_entry_warning_clearance_m"] + delta_m))]
    ident = tuple((n, geometry_key(g)) for n, g in blockers)
    key = ("transit_entry", target_id, float(delta_m), ident)
    if key not in ctx.extra:
        with ctx.cold_build():
            ctx.extra[key] = build_planner(ctx.world, blockers, world_margin_m=P["world_margin_m"] + delta_m)
    return ctx.extra[key]


# ---------------------------------------------------------------- 单车道

def thetas():
    return [math.radians(k) for k in range(0, 360, THETA_STEP_DEG)]


def frame(theta):
    return np.array([math.cos(theta), math.sin(theta)]), np.array([-math.sin(theta), math.cos(theta)])


def h_values(ctx, target_id, theta):
    from ..scene.exact import bounding_box
    tgt = ctx.facility_by_id[target_id]
    o = np.asarray(tgt.center, float)
    _, n = frame(theta)
    x0, y0, x1, y1 = bounding_box(tgt.layers["warning"])
    proj = [float(n @ (np.array([x, y]) - o)) for x in (x0, x1) for y in (y0, y1)]
    k0, k1 = int(math.ceil(min(proj) / H_STEP_M - 1e-12)), int(math.floor(max(proj) / H_STEP_M + 1e-12))
    return [H_STEP_M * k for k in range(k0, k1 + 1)]


def _ykey(y):
    """单车道缓存键 = 精确浮点横向偏移（不舍入）：组合检验取到的车道与逐车道直接重算在同一 y 上计算，逐位相同。
    （首版按 1e-9 舍入作键并在舍入值上计算，裁定 2 门禁 chord_gate 发现 n > 1 时逐格不一致，已改。）"""
    return float(y)


SUB_LEVELS = (BAND_M, 0.0, -BAND_M, RETREAT_M)


class Lane:
    """一条单车道的缓存结果。x 为车道坐标（o + y n 起沿 u）。解析部分（世界区间、各设施次水平集区间）立即计算；
    沿线采样（距离场下界）按需批量计算（只对通过目标穿越检查的车道），runs 为 None 表示尚未采样。"""
    __slots__ = ("theta_idx", "y", "p0", "world", "sub", "xs", "ok", "runs")

    def legal_run(self, x):
        for a, b in self.runs:
            if a - 1e-9 <= x <= b + 1e-9:
                return (a, b)
        return None

    def target_status(self, target_id):
        st = self.sub[target_id]
        if st[0.0] is None or not st[0.0][1] > st[0.0][0]:
            return "no_target_crossing"
        if st[-BAND_M] is None:
            return "target_depth_lt_10"
        return None


def _analytic_lanes(ctx, target_id, theta_idx, ys):
    th = thetas()[theta_idx]
    u, n = frame(th)
    o = np.asarray(ctx.facility_by_id[target_id].center, float)
    ys = np.asarray(ys, float)
    P0 = o[None] + ys[:, None] * n[None]
    wlo, whi = sublevel_many(ctx.world, P0, u, -float(ctx.params["world_margin_m"]))
    subs = {f.id: {c: sublevel_many(f.layers["warning"], P0, u, c) for c in SUB_LEVELS} for f in ctx.facilities}
    out = []
    for k, y in enumerate(ys):
        L = Lane()
        L.theta_idx, L.y, L.p0 = theta_idx, float(y), P0[k]
        L.world = None if np.isnan(wlo[k]) else (float(wlo[k]), float(whi[k]))
        L.sub = {fid: {c: (None if np.isnan(v[0][k]) else (float(v[0][k]), float(v[1][k]))) for c, v in d.items()}
                 for fid, d in subs.items()}
        L.xs = L.ok = L.runs = None
        out.append(L)
    return out


def _sample_lanes(ctx, target_id, lanes, *, intent="transit"):
    """批量沿线采样：x = 5 m 倍数 ∪ 世界区间两端；base 约束距离场下界的最小值 ≥ q 为合格；连续合格段为合法区间。
    采样逐点计算，批量与逐车道单独采样逐位相同。V8-17：base 按 intent 选取（Lane 对象按意图分开缓存）。"""
    todo = [L for L in lanes if L.runs is None]
    if not todo:
        return
    field, base = base_field(ctx, target_id, intent=intent)
    names = [c.name for c in base]
    u, _ = frame(thetas()[todo[0].theta_idx])
    chunks, spans = [], []
    for L in todo:
        w = L.world
        if w is None or w[1] - w[0] <= 0.0:
            spans.append(None)
            continue
        k0, k1 = math.ceil(w[0] / X_STEP_M), math.floor(w[1] / X_STEP_M)
        xs = np.unique(np.r_[w[0], X_STEP_M * np.arange(k0, k1 + 1), w[1]])
        xs = xs[(xs >= w[0]) & (xs <= w[1])]
        spans.append(xs)
        chunks.append(L.p0[None] + xs[:, None] * u[None])
    vals = field.min_lower_clearance(np.vstack(chunks), names) if chunks else np.zeros(0)
    pos = 0
    for L, xs in zip(todo, spans):
        if xs is None:
            L.xs, L.ok, L.runs = np.zeros(0), np.zeros(0, bool), []
            continue
        ok = vals[pos:pos + len(xs)] >= Q_M
        pos += len(xs)
        L.xs, L.ok = xs, ok
        edges = np.flatnonzero(np.diff(np.r_[False, ok, False].astype(np.int8)))
        L.runs = [(float(xs[a]), float(xs[b - 1])) for a, b in zip(edges[::2], edges[1::2])]


def get_lanes(ctx, target_id, theta_idx, ys, *, memo=True, intent="transit"):
    """按 (目标, 航向, 横向偏移) 的进程内缓存取单车道（解析部分）；memo=False 时逐车道直接重算（裁定 2 的门禁对照）。
    V8-17：不同意图的 base 采样结果不同，Lane 按意图分开缓存（transit 用原键）。"""
    if not memo:
        return _analytic_lanes(ctx, target_id, theta_idx, ys)
    store = ctx.extra.setdefault(_ikey("lanes", intent, target_id), {})
    need = sorted({_ykey(y) for y in ys if (theta_idx, _ykey(y)) not in store})
    if need:
        for L in _analytic_lanes(ctx, target_id, theta_idx, need):
            store[(theta_idx, _ykey(L.y))] = L
    return [store[(theta_idx, _ykey(y))] for y in ys]


# ---------------------------------------------------------------- 队形格检验（组合）

def _band_ok(sub_f, s0, s1):
    """其他设施：路径 [s0, s1] 上该 warning 要么整段 |sdf| ≥ 10，要么完整深穿越。s0 可为数组。"""
    B = sub_f[BAND_M]
    s0 = np.asarray(s0, float)
    if B is None:
        return np.ones(s0.shape, bool)
    away = (s1 <= B[0]) | (s0 >= B[1])
    if sub_f[-BAND_M] is None:          # 浅：−10 < min sdf < 10，带内必有切触
        return away
    return away | ((s0 <= B[0]) & (s1 >= B[1]))


def assess_cell(ctx, target_id, theta_idx, h, offsets, *, memo=True, field_grids=None, lanes=None):
    """offsets：((l_i, d_i), …)。可行返回 dict（x_t、x_in、候选 D 列表、各车道入/出圈），否则 (None, 原因)。"""
    if lanes is None:
        lanes = get_lanes(ctx, target_id, theta_idx, [h + d for _, d in offsets], memo=memo)
    tgt = target_id
    for L in lanes:
        why = L.target_status(tgt)
        if why is not None:
            return None, why
    _sample_lanes(ctx, tgt, lanes)
    E, X, runs = [], [], []
    for (l, d), L in zip(offsets, lanes):
        e, f = L.sub[tgt][0.0]
        R = L.legal_run(e)
        if R is None or not (R[0] <= f <= R[1]):
            return None, "lane_blocked_in_target"
        E.append(e - l)
        X.append(f - l)
        runs.append(R)
    ls = np.array([l for l, _ in offsets], float)
    rhi = np.array([R[1] for R in runs], float)
    # 终止站点：从最后车道出圈的编组站点起每 5 m 一站，第一个全员距所有 warning ≥ 50 m 的站点；
    # 任一成员超出自己车道的合法区间之前没有找到即无终点（不在非法区穿出后重取）
    x0 = max(X)
    room = rhi - ls - x0
    k_max = int(math.floor(float(np.min(room)) / X_STEP_M + 1e-9)) if np.all(room >= -1e-9) else -1
    xt = None
    if k_max >= 0:
        xg = x0 + X_STEP_M * np.arange(k_max + 1)
        good = np.ones(len(xg), bool)
        for (l, _), L in zip(offsets, lanes):
            m = xg + l
            for f in ctx.facilities:
                r50 = L.sub[f.id][RETREAT_M]
                if r50 is not None:
                    good &= ~((r50[0] < m) & (m < r50[1]))
        hit = np.flatnonzero(good)
        if len(hit):
            xt = float(xg[hit[0]])
    if xt is None:
        return None, "no_terminal"
    # 集合站点候选（D 向量化）
    o = np.asarray(ctx.facility_by_id[tgt].center, float)
    u, n = frame(thetas()[theta_idx])
    x_in = min(E)
    phys = field_grids if field_grids is not None else collect_phys_grid(ctx, tgt)
    warn_t = ctx.facility_by_id[tgt].layers["warning"]
    others = [f.id for f in ctx.facilities if f.id != tgt]
    Ds = np.asarray(COLLECT_DS, float)
    xcs = x_in - Ds
    C = o[None] + xcs[:, None] * u[None] + (h * n)[None]
    sd = np.asarray(signed_distance(warn_t, C), float)
    keep = (COLLECT_BAND[0] <= sd) & (sd <= COLLECT_BAND[1])
    slots = np.stack([o[None] + (xcs + l)[:, None] * u[None] + ((h + d) * n)[None] for l, d in offsets], axis=1)
    keep &= np.all(phys.ok(slots), axis=1)
    for (l, d), L, R in zip(offsets, lanes, runs):
        s0 = np.minimum(xcs, x_in - PRE_ENTRY_SCAN_M) + l
        keep &= ~(s0 < R[0] - 1e-9)
        for fid in others:
            keep &= _band_ok(L.sub[fid], xcs + l, xt + l)
    cands = [float(D) for D, k in zip(Ds, keep) if k]
    if not cands:
        return None, "no_collect_candidate"
    return {"x_t": float(xt), "x_in": float(x_in), "D": cands, "E": [float(v) for v in E],
            "X": [float(v) for v in X]}, None


def assess_formation(ctx, target_id, offsets, *, memo=True):
    """全部 (θ, h) 格按 θ、h 升序；返回 {"cells": [[θ_idx, h, x_t, x_in, [D…]], …], "reasons": {原因: 格数}, "n_cells",
    "seconds"}。每个航向先批量取解析车道，再对通过目标穿越检查的格批量采样。"""
    t0 = time.perf_counter()
    phys = collect_phys_grid(ctx, target_id)
    cells, reasons, total = [], {}, 0
    for ti, th in enumerate(thetas()):
        hs = h_values(ctx, target_id, th)
        if memo:
            get_lanes(ctx, target_id, ti, [h + d for h in hs for _, d in offsets])
        lane_sets = [get_lanes(ctx, target_id, ti, [h + d for _, d in offsets], memo=memo) for h in hs]
        need = {}
        for lanes in lane_sets:
            if all(L.target_status(target_id) is None for L in lanes):
                for L in lanes:
                    if L.runs is None:
                        need[id(L)] = L
        if need:
            _sample_lanes(ctx, target_id, list(need.values()))
        for h, lanes in zip(hs, lane_sets):
            total += 1
            got, why = assess_cell(ctx, target_id, ti, h, offsets, memo=memo, field_grids=phys, lanes=lanes)
            if got is None:
                reasons[why] = reasons.get(why, 0) + 1
                continue
            cells.append([ti, float(h), got["x_t"], got["x_in"], list(got["D"])])
    return {"cells": cells, "reasons": dict(sorted(reasons.items())), "n_cells": total,
            "seconds": time.perf_counter() - t0}


# ---------------------------------------------------------------- 只读缓存

def query_identity(ctx, target_id, offsets, *, intent="transit"):
    offs = sorted((round(float(l), 9), round(float(d), 9)) for l, d in offsets)
    doc = {"version": CACHE_VERSION, "context": ctx.cache_key, "target": target_id, "offsets": offs,
           "theta_step_deg": THETA_STEP_DEG, "h_step_m": H_STEP_M, "x_step_m": X_STEP_M, "q_m": Q_M,
           "collect_ds": list(COLLECT_DS), "collect_band": list(COLLECT_BAND), "pre_entry_m": PRE_ENTRY_SCAN_M,
           "retreat_m": RETREAT_M, "band_m": BAND_M}
    if intent == "close_observation":
        doc["version"] = "close_observation-v19"
        doc["intent"] = intent
    elif intent != "transit":
        raise ValueError(f"unsupported chord query intent: {intent!r}")
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32], doc


def _cache_path(cache_dir, ctx, target_id, qid):
    return Path(cache_dir) / "transit_v16" / ctx.cache_key / f"{target_id}_{qid}.json"


STATS = {"cache_hits": 0, "cache_misses_computed": 0}


def load_chord_set(ctx, target_id, slots, cache_dir):
    """worker 只读：命中预建文件直接读；缺失时进程内计算（不写回、计数 cache_misses_computed），结果与预建相同。"""
    offsets = [slots.offsets[m] for m in slots.order]
    qid, _ = query_identity(ctx, target_id, offsets)
    mem = ctx.extra.setdefault(("transit_chord_sets", target_id), {})
    if qid in mem:
        return mem[qid]
    p = None if cache_dir is None else _cache_path(cache_dir, ctx, target_id, qid)
    if p is not None and p.exists():
        doc = json.loads(p.read_text(encoding="utf-8"))
        STATS["cache_hits"] += 1
    else:
        doc = assess_formation(ctx, target_id, offsets)
        doc["query_id"] = qid
        STATS["cache_misses_computed"] += 1
    mem[qid] = doc
    return doc


def prewarm_transit(ctx, requests, cache_dir):
    """主进程预建：requests = [(target_id, offsets), …]（由确定性的选队形 probe 序列给出）。已存在的文件不覆盖。
    返回每个查询的身份、格数、可行格数、构建耗时与文件散列。"""
    rows = []
    for target_id, offsets in requests:
        qid, ident = query_identity(ctx, target_id, offsets)
        p = _cache_path(cache_dir, ctx, target_id, qid)
        if p.exists():
            raw = p.read_bytes()
            doc = json.loads(raw.decode("utf-8"))
            rows.append({"target": target_id, "query_id": qid, "existing": True, "n_cells": doc["n_cells"],
                         "feasible": len(doc["cells"]), "seconds": 0.0,
                         "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
            continue
        mem = ctx.extra.get(("transit_chord_sets", target_id), {})
        doc = dict(mem[qid]) if qid in mem else assess_formation(ctx, target_id, offsets)
        doc["query_id"] = qid
        doc["identity"] = ident
        p.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(raw)
        tmp.replace(p)
        rows.append({"target": target_id, "query_id": qid, "existing": False, "n_cells": doc["n_cells"],
                     "feasible": len(doc["cells"]), "seconds": doc["seconds"],
                     "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    return rows


# ---------------------------------------------------------------- 精确弦检查

def assess_straight_bundle(base, warnings, target_id, origin_xy, direction_xy, offsets, x_lo, x_hi, *, band_m, align_m,
                           retreat_m):
    """精确检查器：成员 i 走直线 origin + (x + l_i) u + d_i n，x ∈ [x_lo, x_hi]。
    返回 {"feasible", "target_intervals"（按 offsets 顺序的 (x_entry, x_exit)，车道坐标），"margins"（每约束最小余量），
    "first_error"}。base 用 polyline_clearance 逐弦精确；目标恰一次正长度穿越、深入 ≥ band_m、入圈前 ≥ align_m 直线；
    其他设施整段 |sdf| ≥ band_m 或完整深穿越；终点离所有 warning ≥ retreat_m。"""
    from ..scene.exact import polyline_clearance
    o = np.asarray(origin_xy, float)
    u = np.asarray(direction_xy, float)
    u = u / float(np.hypot(*u))
    n = np.array([-u[1], u[0]])
    margins, intervals, errors = {}, [], []
    for l, d in offsets:
        p0 = o + float(d) * n
        a, b = float(x_lo) + float(l), float(x_hi) + float(l)
        seg = np.array([p0 + a * u, p0 + b * u])
        for c in base:
            m = float(polyline_clearance(c.geometry, seg, sense=c.sense, minimum_m=c.minimum_m)[0])
            margins[c.name] = min(margins.get(c.name, math.inf), m)
            if m < 0.0:
                errors.append({"lane": (l, d), "constraint": c.name, "margin_m": m})
        for fid, g in warnings.items():
            sub = {c: line_sublevel(g, p0, u, c) for c in (band_m, 0.0, -band_m)}
            if fid == target_id:
                I0 = sub[0.0]
                if I0 is None or not I0[1] > I0[0] or not (a < I0[0] and I0[1] < b):
                    errors.append({"lane": (l, d), "check": "target_single_crossing", "interval": I0})
                    intervals.append(I0)
                    continue
                intervals.append(I0)
                if sub[-band_m] is None:
                    errors.append({"lane": (l, d), "check": "target_depth", "required_m": band_m})
                # 与冻结 crossing_analysis 同一比较（s_c < align_m − NODE_TOL_M 才算不足）；首版用严格 < align_m，
                # 在 D = 100 m 的边界候选上把 99.99999999999966 m 判为不足（第 5 部分 3 次 chord_exact_audit）。
                if I0[0] - a < align_m - ALIGN_TOL_M:
                    errors.append({"lane": (l, d), "check": "align", "straight_m": I0[0] - a})
            elif not _band_ok({BAND_M: sub[band_m], -BAND_M: sub[-band_m]}, a, b):
                errors.append({"lane": (l, d), "check": "other_band", "facility": fid})
            for name, pt in (("start", seg[0]), ("end", seg[1])):
                sd = float(signed_distance(g, pt))
                if abs(sd) < band_m:
                    errors.append({"lane": (l, d), "check": f"{name}_in_band", "facility": fid, "signed_m": sd})
            sd_end = float(signed_distance(g, seg[1]))
            if sd_end < retreat_m:
                errors.append({"lane": (l, d), "check": "terminal_retreat", "facility": fid, "signed_m": sd_end})
    return {"feasible": not errors, "target_intervals": intervals, "margins": margins,
            "first_error": errors[0] if errors else None, "errors": errors[:20]}


# ---------------------------------------------------------------- 走廊（附录裁定 1）

def corridor_rows(ctx, task, chord, slots):
    """chord = {"theta_idx", "h"}。返回 {"available", "reason", "x", "lo", "hi", "D", "inset_interval", "rows_total",
    "certified_rows", "run": (首, 末下标), "certified_length_m", "inset_length_m"}。
    行：x = 5 m 网格上、条带 [x − 2.5, x + 2.5] 完全落在中心线目标 warning 内缩 10 + D 区间内的行；列：y = h + 2k；
    单元中心用 field 下界 ≥ q_cell = sqrt(2.5² + 1²)（ε_f 已扣，不重复）。某行包含 h 的单元（k = 0）通过即"已认证行"；
    其所在连续已认证单元的并给出该行 [lo, hi]。曲线范围取已认证行组成的最长连续段（等长取靠前）；
    段长（首末行中心距）< 80 m 记 curve_range_short；没有已认证行记 corridor_unavailable。"""
    from ..scene.field import Clearance
    from .layer_limits import constraints_identity
    P = ctx.params
    tgt = ctx.facility_by_id[task.target_id]
    D = max((abs(float(d)) for _, d in slots.offsets.values()), default=0.0)
    th = thetas()[int(chord["theta_idx"])]
    u, n = frame(th)
    o = np.asarray(tgt.center, float)
    h = float(chord["h"])
    m = BAND_M + D
    I = line_sublevel(tgt.layers["warning"], o + h * n, u, -m)
    I_a = None
    if task.intent in ("intrusion", "feint"):         # V8-18 指令 3.5：feint 入口沿用突入同一范围
        # V8-17 指令 3.5：I = I_w ∩ (−∞, I_a^lo]，I_a = {alert SDF ≤ +(10 + D)}（正次水平集；不用 0 交点再减 10 + D）；
        # 任一区间缺失或交为空记 corridor_unavailable，不改弦
        I_a = line_sublevel(tgt.layers["alert"], o + h * n, u, m)
        if I is not None:
            I = None if (I_a is None or not min(I[1], I_a[0]) >= I[0]) else (I[0], min(I[1], I_a[0]))
    out = {"available": False, "reason": None, "D": D, "inset_interval": I, "x": [], "lo": [], "hi": [],
           "rows_total": 0, "certified_rows": 0, "run": None, "certified_length_m": 0.0,
           "inset_length_m": 0.0 if I is None else float(I[1] - I[0])}
    if task.intent in ("intrusion", "feint"):
        out["alert_interval"] = I_a
    if I is None:
        out["reason"] = "corridor_unavailable"
        return out
    k0 = math.ceil((I[0] + 2.5) / X_STEP_M - 1e-12)
    k1 = math.floor((I[1] - 2.5) / X_STEP_M + 1e-12)
    xs = X_STEP_M * np.arange(k0, k1 + 1, dtype=float)
    out["rows_total"] = int(len(xs))
    if not len(xs):
        out["reason"] = "corridor_unavailable"
        return out
    cons = [Clearance("c_target_inside", tgt.layers["warning"], -1, m)]
    cons += [Clearance("c_alert:" + f.id, f.layers["alert"], 1, m) for f in ctx.facilities]
    cons += [Clearance("c_warning_edge:" + f.id, f.layers["warning"], 0, m) for f in ctx.facilities if f.id != tgt.id]
    cons += [Clearance("c_obstacle:" + i, g, 1, float(P["obstacle_margin_m"]) + D) for i, g in ctx.obstacles]
    cons += [Clearance("c_world", ctx.world, -1, float(P["world_margin_m"]) + D)]
    field = ctx.field(("transit_corridor", task.target_id, constraints_identity(cons)), cons)
    q_cell = math.sqrt(2.5 ** 2 + 1.0 ** 2)
    from ..scene.exact import bounding_box
    x0b, y0b, x1b, y1b = bounding_box(tgt.layers["warning"])
    half = 0.5 * math.hypot(x1b - x0b, y1b - y0b) + 10.0
    ks = np.arange(-int(math.ceil(half / Y_STEP_M)), int(math.ceil(half / Y_STEP_M)) + 1)
    ys = h + Y_STEP_M * ks
    pts = o[None, None] + xs[:, None, None] * u[None, None] + ys[None, :, None] * n[None, None]
    ok = field.min_lower_clearance(pts) >= q_cell
    z = int(np.flatnonzero(ks == 0)[0])
    cert = ok[:, z]
    lo = np.full(len(xs), np.nan)
    hi = np.full(len(xs), np.nan)
    for r in np.flatnonzero(cert):
        a = z
        while a - 1 >= 0 and ok[r, a - 1]:
            a -= 1
        b = z
        while b + 1 < len(ks) and ok[r, b + 1]:
            b += 1
        lo[r], hi[r] = ys[a] - 1.0, ys[b] + 1.0
    out["certified_rows"] = int(cert.sum())
    edges = np.flatnonzero(np.diff(np.r_[False, cert, False].astype(np.int8)))
    runs = list(zip(edges[::2].tolist(), (edges[1::2] - 1).tolist()))
    if not runs:
        out["reason"] = "corridor_unavailable"
        return out
    best = max(runs, key=lambda ab: (ab[1] - ab[0], -ab[0]))
    a, b = best
    out.update(run=(int(a), int(b)), certified_length_m=float(xs[b] - xs[a]),
               x=xs[a:b + 1].tolist(), lo=lo[a:b + 1].tolist(), hi=hi[a:b + 1].tolist())
    if xs[b] - xs[a] < 80.0:
        out["reason"] = "curve_range_short"
        return out
    out["available"] = True
    return out
