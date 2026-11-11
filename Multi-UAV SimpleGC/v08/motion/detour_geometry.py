"""V8-21 迂回：独立约束、近距离带极坐标方位段、图元碰带、车道扫角窗口、直线可行域、进场只读代理与路由视图
（指令 2.2、3.1、3.4、3.5；裁定 1、3）。

不调用 layer_limits / constraints_for_task / TC.transit_base / TransitSetup；只读调用 constraints_identity。
不原地修改 ctx、facilities、layers、scene。导入时不读配置、不读场景。
"""
import math
import hashlib
import time
from types import SimpleNamespace

import numpy as np

VERSION = "detour-v21-lp-arcs-r1"
NEAR_PREFIX = "__crossing__"


# ---------------------------------------------------------------- 独立约束（指令 2.2）

def _candidate(candidate):
    if candidate is None:
        from .detour_config import load_detour_candidate
        return load_detour_candidate()
    return candidate


def near_key_for(target_id, existing):
    k = f"{NEAR_PREFIX}{target_id}::near"
    while k in existing:
        k += "#"
    return k


def detour_constraints(ctx, task, candidate=None):
    """返回 base、warnings、crossing_boundaries、near_key、near_geometry、arc_only（确定性顺序）。
    base：world 内 world_margin_m；障碍外 obstacle_margin_m（原序）；设施（原序）：目标 warning 外 forbidden_margin_m
    （目标层上限 0）；非目标按冻结 criteria_segment.max_other_facility_layer（=1）取 alert 外 forbidden_margin_m。
    crossing_boundaries = dict(warnings) 后追加 near（目标 warning 外扩 D）。arc_only 只用于弧带构造。"""
    from ..config import load_config
    from ..scene.exact import expand
    from ..scene.field import Clearance
    if getattr(task, "intent", None) != "detour":
        raise ValueError(f"detour_constraints 只接受 detour 任务：{getattr(task, 'intent', None)!r}")
    C = _candidate(candidate)
    D = float(C.values["near_band_width_m"])
    P = ctx.params
    seg = load_config("criteria_segment").values
    other = seg["max_other_facility_layer"]
    if float(other) != 1.0:
        raise ValueError(f"冻结 max_other_facility_layer 应为 1：{other!r}")
    target_id = task.target_id
    fac = {f.id: f for f in ctx.facilities}
    if target_id not in fac:
        raise ValueError(f"目标设施不存在：{target_id!r}")
    base = [Clearance("world", ctx.world, -1, P["world_margin_m"])]
    base += [Clearance("obstacle:" + i, g, 1, P["obstacle_margin_m"]) for i, g in ctx.obstacles]
    for f in ctx.facilities:
        if f.id == target_id:
            base.append(Clearance("warning:" + f.id, f.layers["warning"], 1, P["forbidden_margin_m"]))
        else:
            base.append(Clearance("alert:" + f.id, f.layers["alert"], 1, P["forbidden_margin_m"]))
    warnings = {f.id: f.layers["warning"] for f in ctx.facilities}
    crossing = dict(warnings)
    near_key = near_key_for(target_id, crossing)
    near = expand(fac[target_id].layers["warning"], D)
    crossing[near_key] = near
    band = P["pre_entry_warning_clearance_m"]
    arc_only = [Clearance("near_inner:" + target_id, near, -1, band)]
    arc_only += [Clearance("arc_warning:" + f.id, f.layers["warning"], 1, band) for f in ctx.facilities if f.id != target_id]
    return {"base": base, "warnings": warnings, "crossing_boundaries": crossing, "near_key": near_key,
            "near_geometry": near, "arc_only": arc_only, "target_id": target_id,
            "candidate_sha256": C.sha256, "near_band_width_m": D}


# ---------------------------------------------------------------- 图元与近距离带（指令 3.4 第 4 条）

def _chord_band_hits(xy, kappa, geometry, band_m):
    from ..scene.exact import chord_sdf_range
    a, b = xy[:-1], xy[1:]
    lo, hi, _ = chord_sdf_range(geometry, a, b)
    c = np.hypot(*(b - a).T)
    k = np.maximum(np.abs(kappa[:-1]), np.abs(kappa[1:]))
    sag = 1.01 * k * c * c / 8.0 + 1e-9          # 弦到真实曲线的偏差上界（小转角下 κc²/8）
    return (lo - sag < band_m) & (hi + sag > -band_m)


def arc_band_violations(primitives, geometry, band_m, spacing_m=0.5):
    """与边界 ±band_m 带相交的非 line 图元下标（检查图元内部全部弦及弦—曲线偏差，不只端点）。"""
    from .path import sample_primitives
    out = []
    for i, prim in enumerate(primitives):
        if prim[0] == "line":
            continue
        smp = sample_primitives([prim], spacing_m)
        if np.any(_chord_band_hits(smp.xy, smp.kappa, geometry, band_m)):
            out.append(i)
    return out


def lane_band_violations(xy, kappa, station, line_mask_fn, geometry, band_m):
    """成员曲线上与带相交、且所在参考站点不属于 line 图元的弦下标（用于全部车道复核）。"""
    hits = _chord_band_hits(np.asarray(xy, float), np.asarray(kappa, float), geometry, band_m)
    st = 0.5 * (np.asarray(station[:-1], float) + np.asarray(station[1:], float))
    bad = hits & ~line_mask_fn(st)
    return np.flatnonzero(bad)


# ---------------------------------------------------------------- 构造后车道扫角窗口（裁定 1）

def lane_sweep_window(lanes_xy, center, warning, candidate, generation):
    """每条车道折线（0.5 m 采样）按 sweep_series 计算对目标的近距离带扫角；时间 = 采样序号 × 100000 μs。
    ok ⇔ 所有车道最大扫角 ≥ Θ + nominal_sweep_margin_deg，且所有车道所有区间 < construction_sweep_cap_deg。"""
    from ..scene.exact import signed_distance
    from .detour_numeric import sweep_series
    Cv = candidate.values if hasattr(candidate, "values") and not isinstance(candidate, dict) else candidate
    Gv = generation.values if hasattr(generation, "values") and not isinstance(generation, dict) else generation
    lo = float(Cv["min_sweep_deg"]) + float(Gv["nominal_sweep_margin_deg"])
    cap = float(Gv["construction_sweep_cap_deg"])
    D = float(Cv["near_band_width_m"])
    c = np.asarray(center, float)
    spans, runs_ok, all_runs = {}, True, {}
    for mid in sorted(lanes_xy):
        xy = np.asarray(lanes_xy[mid], float)
        sd = np.asarray(signed_distance(warning, xy), float)
        ang = np.arctan2(xy[:, 1] - c[1], xy[:, 0] - c[0])
        s = sweep_series(np.arange(len(xy), dtype=np.int64) * 100000, sd, ang, D)
        spans[mid] = float(s["max_span_deg"])
        all_runs[mid] = [float(r["span_deg"]) for r in s["runs"]]
        if not all(x < cap for x in all_runs[mid]):
            runs_ok = False
    ok = bool(spans and runs_ok and all(v >= lo for v in spans.values()))
    return {"spans_deg": spans, "ok": ok, "run_spans_deg": all_runs, "lower_deg": lo, "cap_deg": cap}


# ---------------------------------------------------------------- 近距离带方位段（指令 3.1；裁定 3）

class DetourBand:
    """目标设施本体中心为圆心的 360 行 × 2 m 径向网格；约束 = base + arc_only（同一组合场取 ε_f）。
    每行两次 intervals_from_margins：threshold 0 的最长区间，再在其内取 threshold T_H = H + q + η 的最长管区间。"""

    def __init__(self, ctx, cons):
        from ..scene.exact import bounding_box, center_of_geometry
        from .layer_limits import constraints_identity
        from . import monitoring_band as MB
        tid = cons["target_id"]
        fac = ctx.facility_by_id[tid]
        self.center = np.asarray(center_of_geometry(fac.geometry), float)
        x0, y0, x1, y1 = bounding_box(cons["near_geometry"])
        c = self.center
        self.r_star = float(max(math.hypot(x - c[0], y - c[1]) for x in (x0, x1) for y in (y0, y1)))
        self.rs = np.arange(MB.R_STEP_M, self.r_star + MB.R_STEP_M, MB.R_STEP_M)
        self.cons = list(cons["base"]) + list(cons["arc_only"])
        self.names = [k.name for k in self.cons]
        self.cg = ctx.combined(("detour_band", tid, constraints_identity(self.cons)), self.cons)
        self.eps = float(self.cg.field.eps)
        self.eta = 2.0 * self.eps
        self.q = MB.grid_error_m(self.r_star)
        phis = 2.0 * math.pi * np.arange(MB.PHI_ROWS) / MB.PHI_ROWS
        e = np.stack([np.cos(phis), np.sin(phis)], axis=1)
        pts = c[None, None, :] + self.rs[None, :, None] * e[:, None, :]
        allowed = self.cg.ok(pts)
        self.pm, self.cm = MB.radial_margins(self.cons, c, self.rs, allowed_mask=allowed)
        self.lo, self.hi = MB.intervals_from_margins(self.pm, self.cm, self.rs, 0.0)
        self._seg = {}
        self._lp = {}
        self._identity = (VERSION, tid, cons["candidate_sha256"], constraints_identity(self.cons))

    def segments(self, H):
        """返回 {periodic, segments:[{id,rows,A,B}], tl, tu, threshold_m, max_span_deg}。rows 为展开递增整数行。"""
        from . import monitoring_band as MB
        key = float(H).hex()
        if key in self._seg:
            return self._seg[key]
        thr = float(H) + self.q + self.eta
        tl, tu = MB.intervals_from_margins(self.pm, self.cm, self.rs, thr, (self.lo, self.hi))
        ok = np.isfinite(tl) & np.isfinite(tu)
        segs, periodic = [], False
        if ok.all():
            A, B = MB._clamped_windows(tl, tu, True)
            good = A <= B
            if good.all():
                periodic = True
                segs.append({"id": 0, "rows": np.arange(360), "A": A, "B": B})
            else:
                rot = int(np.flatnonzero(~good)[0])
                idx = (np.arange(360) + rot) % 360
                g = good[idx]
                d = np.diff(np.r_[0, g.astype(int), 0])
                for s, e in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1):
                    rows = rot + np.arange(s, e + 1)
                    m = rows % 360
                    segs.append({"rows": rows, "A": A[m], "B": B[m]})
        elif ok.any():
            rot = int(np.flatnonzero(~ok)[0])
            idx = (np.arange(360) + rot) % 360
            o = ok[idx]
            d = np.diff(np.r_[0, o.astype(int), 0])
            for s, e in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1):
                rows = rot + np.arange(s, e + 1)
                m = rows % 360
                A, B = MB._clamped_windows(tl[m], tu[m], False)
                good = A <= B
                dd = np.diff(np.r_[0, good.astype(int), 0])
                for a, b in zip(np.flatnonzero(dd == 1), np.flatnonzero(dd == -1) - 1):
                    segs.append({"rows": rows[a:b + 1], "A": A[a:b + 1], "B": B[a:b + 1]})
        segs.sort(key=lambda sg: int(sg["rows"][0]) % 360)
        for i, sg in enumerate(segs):
            sg["id"] = i
            sg["rows"] = np.asarray(sg["rows"], int) - 360 * (int(sg["rows"][0]) // 360)
        span = 360.0 if periodic else max((float(len(sg["rows"]) - 1) for sg in segs), default=-1.0)
        out = {"periodic": periodic, "segments": segs, "tl": tl, "tu": tu, "threshold_m": thr, "max_span_deg": span}
        self._seg[key] = out
        return out

    def lp_arcs(self, H, *, need_deg, nominal_sweep_lo_deg, kmax):
        """Certified subset with fixed parent curvature A; review repair rulings 1,2,5,6.

        Unknown solver returns are unverified upper bounds, never feasible lower bounds.
        Each parent stores only max_end[s]; its shorter subarcs inherit a feasible witness.
        Geometry and the shared solver are unchanged. All returned arrays are read-only.
        """
        from . import monitoring_band as MB
        seg = self.segments(H)
        digest = hashlib.sha256()
        for name in ("tl", "tu"):
            digest.update(np.asarray(seg[name], dtype="<f8").tobytes())
        for p in seg["segments"]:
            digest.update(np.asarray(p["rows"], dtype="<i8").tobytes())
        key = (self._identity, digest.hexdigest(), float(H).hex(), float(kmax).hex(), MB.LP_CONTROLS,
               float(need_deg).hex(), float(nominal_sweep_lo_deg).hex(), MB.PHI_ROWS, MB.NEIGHBOR_HALF)
        if key in self._lp:
            return {**self._lp[key], "cache_hit": True}
        t0 = time.perf_counter()
        m = int(math.ceil(float(nominal_sweep_lo_deg)))
        parents = []
        stats = {"lp_calls": 0, "unknown_status_count": 0, "unknown_pruned_count": 0,
                 "status_counts": {}, "lp_seconds": [], "unknown_details": []}

        def solve(ids, Ap, Bp, Ac, periodic):
            before = time.perf_counter()
            stats["lp_calls"] += 1
            try:
                lp = MB.shape_lp(ids, Ap, Bp, Ac, kmax=kmax, periodic=periodic, M=MB.LP_CONTROLS)
                status = lp["status"]
                controls = lp.get("controls")
                certified = bool(status == 0 and lp["feasible"] and controls is not None
                                 and len(controls) == MB.LP_CONTROLS and np.all(np.isfinite(controls)))
                unknown = not certified and status not in (2, "empty_interval")
                message = lp.get("message")
            except Exception as exc:
                status, certified, unknown, message = "exception", False, True, repr(exc)
            stats["lp_seconds"].append(time.perf_counter() - before)
            st = str(status)
            stats["status_counts"][st] = stats["status_counts"].get(st, 0) + 1
            if unknown:
                stats["unknown_status_count"] += 1
                stats["unknown_details"].append({"status": st, "first_row": int(ids[0]),
                                                  "last_row": int(ids[-1]), "periodic": bool(periodic),
                                                  "message": message})
            return certified, status, unknown

        for sg in seg["segments"]:
            wrapping = bool(seg["periodic"])
            base = np.asarray(sg["rows"], int)
            if len(base) - 1 < m and not wrapping:
                continue
            if wrapping:
                ids = np.arange(2 * MB.PHI_ROWS - 1)
                fin = np.isfinite(seg["tl"]) & np.isfinite(seg["tu"])
                lower = np.where(fin, seg["tl"], -np.inf)
                Ac360 = MB._clamped_windows(lower, lower, True)[0]
                Ap, Bp = MB._clamped_windows(seg["tl"], seg["tu"], True)
                whole, status, _ = solve(np.arange(MB.PHI_ROWS), Ap, Bp, Ac360, True)
                Ac = Ac360[ids % MB.PHI_ROWS]
                tlu, tuu = seg["tl"][ids % MB.PHI_ROWS], seg["tu"][ids % MB.PHI_ROWS]
                nstarts, limit = MB.PHI_ROWS, MB.PHI_ROWS - 1
            else:
                ids = base.copy()
                tlu, tuu = seg["tl"][ids % MB.PHI_ROWS], seg["tu"][ids % MB.PHI_ROWS]
                fin = np.isfinite(tlu) & np.isfinite(tuu)
                lower = np.where(fin, tlu, -np.inf)
                Ac = MB._clamped_windows(lower, lower, False)[0]
                Ap, Bp = MB._clamped_windows(tlu, tuu, False)
                whole, status, _ = solve(ids, Ap, Bp, Ac, False)
                nstarts, limit = max(0, len(ids) - m), len(ids) - 1

            def test(s, e):
                rid, A, B, C = MB.arc_lp_inputs(ids, tlu, tuu, Ac, s, e)
                ok, _status, unknown = solve(rid, A, B, C, False)
                stats["unknown_pruned_count"] += int(unknown)
                return ok

            max_end = _lp_feasible_pairs_checked(len(ids), nstarts, m, limit, test, whole_feasible=whole)
            parent = {"id": int(sg["id"]), "ids": ids, "tl": np.asarray(tlu), "tu": np.asarray(tuu),
                      "A_curv": np.asarray(Ac), "max_end": max_end, "start_count": nstarts,
                      "whole_feasible": bool(whole), "whole_status": status, "periodic": wrapping,
                      "geometric_span_deg": 360.0 if wrapping else float(len(base)-1)}
            for name in ("ids", "tl", "tu", "A_curv", "max_end"):
                parent[name].setflags(write=False)
            parents.append(parent)
        full = any(p["periodic"] and p["whole_feasible"] for p in parents)
        span = 360.0 if full else max((float(e-s) for p in parents for s, e in enumerate(p["max_end"])
                                      if e >= s + m), default=-1.0)
        stats.update(query_s=time.perf_counter()-t0,
                     certified_pairs=sum(max(0, int(e)-s-m+1) for p in parents for s,e in enumerate(p["max_end"])),
                     rescued_parents=sum(not p["whole_feasible"] and np.any(p["max_end"] >= 0) for p in parents),
                     rescued_periodic=sum(p["periodic"] and not p["whole_feasible"] and np.any(p["max_end"] >= 0)
                                          for p in parents))
        out = {"complete": True, "feasible": bool(span >= need_deg), "parents": parents,
               "whole_circle_feasible": full, "max_span_deg": span, "kmax": float(kmax), "M": MB.LP_CONTROLS,
               "geometric_max_span_deg": float(seg["max_span_deg"]), "min_span_rows": m,
               "diagnostics": stats, "input_digest": digest.hexdigest(), "cache_hit": False}
        self._lp[key] = out
        return out


def _lp_feasible_pairs_checked(n, nstarts, min_span, max_span, test, *, whole_feasible=False):
    """Ruling 2: compressed certified endpoints, with inherited feasible lower bounds.

    test returns True only for certified feasible. False includes unverified numeric states
    under ruling 1; they may prune but cannot become a lower-bound witness.
    """
    ends = np.full(nstarts, -1, dtype=int)
    known = -1
    for s in range(nstarts):
        first, upper = s + min_span, min(n-1, s+max_span)
        if first > upper:
            continue
        if whole_feasible:
            ends[s] = upper
            continue
        lo = known if first <= known <= upper else -1
        if lo < 0:
            if not test(s, first):
                continue
            lo = first
        if upper > lo:
            if test(s, upper):
                lo = upper
            else:
                hi = upper
                while hi-lo > 1:
                    mid = (lo+hi)//2
                    if test(s, mid):
                        lo = mid
                    else:
                        hi = mid
        ends[s] = known = lo
    return ends


def band_for(ctx, cons):
    from .layer_limits import constraints_identity
    key = (VERSION, "band", cons["target_id"], cons["candidate_sha256"],
           constraints_identity(list(cons["base"]) + list(cons["arc_only"])))
    if key not in ctx.extra:
        ctx.extra[key] = DetourBand(ctx, cons)
    return ctx.extra[key]


# ---------------------------------------------------------------- 直线上的解析可行域（指令 3.4 第 1–3 条）

def line_excluded(constraints, p0, u):
    """直线 p0 + x u 上被各约束排除的开区间与 world 允许闭区间（凸几何精确求交）。返回 (allowed_lo, allowed_hi, [(a,b)])。"""
    from .transit_chords import line_sublevel
    lo_w, hi_w, excl = -math.inf, math.inf, []
    for c in constraints:
        if c.sense == -1:
            iv = line_sublevel(c.geometry, p0, u, -float(c.minimum_m))
            if iv is None:
                return None
            lo_w, hi_w = max(lo_w, iv[0]), min(hi_w, iv[1])
        elif c.sense == 1:
            iv = line_sublevel(c.geometry, p0, u, float(c.minimum_m))
            if iv is not None:
                excl.append(iv)
        else:
            raise ValueError("直线可行域只支持 sense ±1")
    if lo_w > hi_w:
        return None
    return lo_w, hi_w, excl


def component_containing(constraints, p0, u, x_lo, x_hi):
    """直线上可行集合中包含整段 [x_lo, x_hi] 的连通分量 [a, b]；不存在返回 None。
    排除区间为开区间 {sdf < m} 的闭包近似：边界点 sdf = m 视为可行（余量恰为 0）。"""
    got = line_excluded(constraints, p0, u)
    if got is None:
        return None
    a, b, excl = got
    if x_lo < a - 1e-9 or x_hi > b + 1e-9:
        return None
    for lo, hi in excl:
        if lo < x_hi and hi > x_lo:
            return None
        if hi <= x_lo:
            a = max(a, hi)
        elif lo >= x_hi:
            b = min(b, lo)
    return a, b


# ---------------------------------------------------------------- 进场只读代理与路由视图（指令 3.5）

class _FacilityView:
    def __init__(self, f, warning):
        self.id, self.geometry, self.center, self.offsets = f.id, f.geometry, f.center, f.offsets
        self.layers = {**f.layers, "warning": warning}


class EntryContext:
    """只在 facility_by_id[target].layers["warning"] 暴露 near；其余透传。extra 为 detour 私有缓存字典。"""

    def __init__(self, ctx, target_id, near):
        self._ctx = ctx
        self._target = target_id
        key = (VERSION, "entry_extra")
        if key not in ctx.extra:
            ctx.extra[key] = {}
        self.extra = ctx.extra[key]
        self.facilities = [(_FacilityView(f, near) if f.id == target_id else f) for f in ctx.facilities]

    @property
    def facility_by_id(self):
        return {f.id: f for f in self.facilities}

    def __getattr__(self, name):
        if name in ("extra", "facilities", "facility_by_id"):
            raise AttributeError(name)
        return getattr(self._ctx, name)


class DetourRouteView:
    """route_to_slot/plan_starts 所需的最小接口：cg_route = base + near 外 pre_entry_warning_clearance_m；
    warn = 全部 crossing_boundaries（含 near），使冻结路由检查也看 near。不实例化 TransitSetup。"""

    def __init__(self, ctx, cons, states):
        from ..config import load_config
        from ..scene.field import Clearance
        from .layer_limits import constraints_identity
        P = ctx.params
        tid = cons["target_id"]
        self.ctx, self.states, self.target = ctx, states, tid
        self.M = load_config("monitoring").values
        self.G = load_config("guidance").values
        self.v_cap = self.M["speed_max_m_s"]
        self.band = P["pre_entry_warning_clearance_m"]
        self.align = P["alignment_length_m"]
        self.warn = dict(cons["crossing_boundaries"])
        pre = Clearance("preentry_near:" + tid, cons["near_geometry"], 1, P["pre_entry_warning_clearance_m"])
        self.route_constraints = list(cons["base"]) + [pre]
        self.cg_route = ctx.combined(("route", "detour_preentry", constraints_identity(self.route_constraints)),
                                     self.route_constraints)
        self.stats = {}
        self.entry_ctx = EntryContext(ctx, tid, cons["near_geometry"])

    def planner_factory(self, ctx, delta):
        from . import transit_chords as TC
        return TC.entry_planner(self.entry_ctx, self.target, delta)

    def route_fn(self, S, p0, slot, u, rng):
        from .shared_routes import route_to_slot
        return route_to_slot(S, p0, slot, u, rng, planner_factory=self.planner_factory)


def ns(**kw):
    return SimpleNamespace(**kw)
