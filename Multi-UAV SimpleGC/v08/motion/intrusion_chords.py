"""突入的有限可行集合：格组合、终点集合与缓存适配（V8-17 指令 3.3；本项新增）。

坐标、航向/偏移网格、单车道解析与沿线采样直接调用 transit_chords（intent="intrusion" 时 base/缓存身份按意图
参数化）。本模块只做突入特有的部分：
  - 每条实际车道（按真实浮点 h + d_i，不舍入）一次：目标 alert/protected 的 0 次水平集区间、I_p、I_c、x_*、E_i
    （intrusion_numeric.endpoint_interval），包装原 Lane（不向其动态挂属性）；
  - 一格：x_in = min_i(e_i − l_i)；对每个 D_c ∈ {100, …, 400}：参考集合点目标 warning SDF ∈ [50, 250]、全部槽位过原
    collect_phys（intrusion base + 全部 warning 外 10）、预留起点 min(x_c, x_in − 210) + l_i 与入圈点在同一合法 run；
    E_i 截到该 run；其他设施 warning 用前缀区间并（prefix_endpoint_set）限制终点；对每个 σ 把各成员集合平移
    −σ l_i 求交得 J_{D,σ}，再对 D 求并（规范化合并重叠）得 J_σ。
缓存 payload：可行格的 theta_idx、h_m、x_in、choices=[{sigma, intervals, by_collect_D=[[D_c, intervals], …]}]，
按航向、h、σ 降序、D_c 升序稳定排列；无可行 σ 的格不进入 cells。中间运算可用 ±inf 哨兵，写盘只有有限端点。
"""
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

from . import intrusion_numeric as IN
from . import transit_chords as TC

CACHE_VERSION = "v17-intrusion-chords-1"
INTENT = "intrusion"


# ---------------------------------------------------------------- 单车道（包装原 Lane）

class IntrusionLane:
    """突入按车道缓存记录：包装 transit_chords.Lane（intent="intrusion" 的 base 采样），另存
    protected_interval（I_p）、contour45_interval（I_c）、deepest_x（x_*）、endpoint_interval（E_i）、
    target_layer_intervals（目标 warning/alert/protected 的 0 次水平集）。"""
    __slots__ = ("lane", "protected_interval", "contour45_interval", "deepest_x", "endpoint_interval",
                 "target_layer_intervals")


STATS = {"cache_hits": 0, "cache_misses_computed": 0, "lanes_computed": 0, "lane_seconds": 0.0}


def _wrap(ctx, target_id, lanes):
    """一批同航向车道：次水平集区间用批量 sublevel_many（与单车道 line_sublevel 同一逐元素计算），最深点逐车道解析。"""
    tgt = ctx.facility_by_id[target_id]
    if not lanes:
        return []
    u, _ = TC.frame(TC.thetas()[lanes[0].theta_idx])
    t0 = time.perf_counter()
    P0 = np.stack([np.asarray(L.p0, float) for L in lanes])

    def batch(geom, c):
        lo, hi = TC.sublevel_many(geom, P0, u, c)
        return [None if np.isnan(a) else (float(a), float(b)) for a, b in zip(lo, hi)]
    Ip = batch(tgt.layers["protected"], -IN.PROTECTED_DEPTH_M)
    Ic = batch(tgt.geometry, IN.CONTOUR_SKELETON_M)
    Ia0 = batch(tgt.layers["alert"], 0.0)
    Ip0 = batch(tgt.layers["protected"], 0.0)
    out = []
    for k, L in enumerate(lanes):
        r = IntrusionLane()
        r.lane = L
        r.protected_interval, r.contour45_interval = Ip[k], Ic[k]
        # 与 endpoint_interval 同一计算（I_p 或 I_c 为空时不求最深点，E 为空）
        if r.protected_interval is None or r.contour45_interval is None:
            r.deepest_x, r.endpoint_interval = None, None
        else:
            r.deepest_x = IN.deepest_station(tgt.geometry, L.p0, u)
            r.endpoint_interval = IN.endpoint_from_parts(r.protected_interval, r.contour45_interval, r.deepest_x)
        r.target_layer_intervals = {"warning": L.sub[target_id][0.0], "alert": Ia0[k], "protected": Ip0[k]}
        out.append(r)
    STATS["lanes_computed"] += len(lanes)
    STATS["lane_seconds"] += time.perf_counter() - t0
    return out


def get_intrusion_lanes(ctx, target_id, theta_idx, ys, *, memo=True):
    """memo=True：按 (航向, 精确浮点 y) 的进程内缓存；memo=False：解析车道与终点量全部直算，不读取任何车道/终点缓存。"""
    if not memo:
        return _wrap(ctx, target_id, TC.get_lanes(ctx, target_id, theta_idx, ys, memo=False, intent=INTENT))
    store = ctx.extra.setdefault(("intrusion_lane_records", target_id), {})
    need = sorted({TC._ykey(y) for y in ys if (theta_idx, TC._ykey(y)) not in store})
    if need:
        base_lanes = TC.get_lanes(ctx, target_id, theta_idx, need, memo=True, intent=INTENT)
        for r in _wrap(ctx, target_id, base_lanes):
            store[(theta_idx, TC._ykey(r.lane.y))] = r
    return [store[(theta_idx, TC._ykey(y))] for y in ys]


# ---------------------------------------------------------------- 格组合

def _status(r, target_id):
    """目标三个层 0 次水平集为单一区间（凸 ⇒ 单区间或空），warning 正长度且能深进 10 m；终点集合非空。"""
    why = r.lane.target_status(target_id)
    if why is not None:
        return why
    if r.endpoint_interval is None:
        return "no_endpoint"
    return None


def assess_cell(ctx, target_id, theta_idx, h, offsets, *, memo=True, sigmas, field_grids=None, ilanes=None):
    """返回 (cell, None) 或 (None, reason)。cell 含各 sigma 的终点区间并及按 D 的子集合。"""
    if ilanes is None:
        ilanes = get_intrusion_lanes(ctx, target_id, theta_idx, [h + d for _, d in offsets], memo=memo)
    tgt = target_id
    for r in ilanes:
        why = _status(r, tgt)
        if why is not None:
            return None, why
    TC._sample_lanes(ctx, tgt, [r.lane for r in ilanes], intent=INTENT)
    entries, runs, E = [], [], []
    for (l, d), r in zip(offsets, ilanes):
        e = r.lane.sub[tgt][0.0][0]
        R = r.lane.legal_run(e)
        if R is None:
            return None, "lane_blocked_in_target"
        # E_i 截到包含入圈点的同一合法 run（不穿过非法段再在后面找终点）
        lo, hi = max(r.endpoint_interval[0], R[0]), min(r.endpoint_interval[1], R[1])
        if not lo <= hi:
            return None, "endpoint_blocked"
        entries.append(e)
        runs.append(R)
        E.append((float(lo), float(hi)))
    ls = [float(l) for l, _ in offsets]
    x_in = min(e - l for e, l in zip(entries, ls))
    o = np.asarray(ctx.facility_by_id[tgt].center, float)
    u, n = TC.frame(TC.thetas()[theta_idx])
    phys = field_grids if field_grids is not None else TC.collect_phys_grid(ctx, tgt, intent=INTENT)
    warn_t = ctx.facility_by_id[tgt].layers["warning"]
    others = [f.id for f in ctx.facilities if f.id != tgt]
    Ds = np.asarray(TC.COLLECT_DS, float)
    xcs = x_in - Ds
    C = o[None] + xcs[:, None] * u[None] + (h * n)[None]
    from ..scene.exact import signed_distance
    sd = np.asarray(signed_distance(warn_t, C), float)
    keep = (TC.COLLECT_BAND[0] <= sd) & (sd <= TC.COLLECT_BAND[1])
    slots = np.stack([o[None] + (xcs + l)[:, None] * u[None] + ((h + d) * n)[None] for l, d in offsets], axis=1)
    keep &= np.all(phys.ok(slots), axis=1)
    for (l, d), R in zip(offsets, runs):
        s0 = np.minimum(xcs, x_in - TC.PRE_ENTRY_SCAN_M) + l          # 预留起点：最早编组入圈站点前 210 m，再加成员 l
        keep &= ~(s0 < R[0] - 1e-9)
    if not keep.any():
        return None, "no_collect_candidate"
    # 每个可用 D：各成员终点集合 F_i(D) = E_i ∩ ⋂_f prefix(其他设施 f, 槽位 x_c + l_i)
    per_D = {}
    variant_cache = {}
    for k in np.flatnonzero(keep):
        D = float(Ds[k])
        F = []
        for (l, d), r, Ei in zip(offsets, ilanes, E):
            a = float(xcs[k]) + float(l)
            cur = (Ei,)
            for fid in others:
                sub = r.lane.sub[fid]
                pre = IN.prefix_endpoint_set({10.0: sub[TC.BAND_M], -10.0: sub[-TC.BAND_M]}, a)
                cur = IN.intersect_two(cur, pre)
                if not cur:
                    break
            F.append(cur)
        key = tuple(F)
        if key not in variant_cache:
            variant_cache[key] = {s: IN.intersect_endpoint_sets(F, ls, s) for s in sigmas}
        per_D[D] = variant_cache[key]
    choices = []
    for s in sigmas:
        byD = [[D, [list(iv) for iv in per_D[D][s]]] for D in sorted(per_D) if per_D[D][s]]
        if not byD:
            continue
        J = IN.normalize_intervals([tuple(iv) for _, ivs in byD for iv in ivs])
        choices.append({"sigma": float(s), "intervals": [list(iv) for iv in J], "by_collect_D": byD})
    if not choices:
        return None, "no_sigma_endpoint"
    return {"theta_idx": int(theta_idx), "h_m": float(h), "x_in": float(x_in), "choices": choices}, None


def assess_formation(ctx, target_id, offsets, *, sigmas, memo=True, detail=False):
    """按 theta_idx、h 升序遍历全部格；返回 cells/reasons/n_cells。detail=True 另给逐格 per_cell
    [[theta_idx, h, 原因或 None], …]（门禁比较用，不写入缓存 payload）。"""
    t0 = time.perf_counter()
    offsets = [(float(l), float(d)) for l, d in offsets]
    sigmas = tuple(float(s) for s in sigmas)
    phys = TC.collect_phys_grid(ctx, target_id, intent=INTENT)
    cells, reasons, total, per_cell = [], {}, 0, []
    for ti, th in enumerate(TC.thetas()):
        hs = TC.h_values(ctx, target_id, th)
        if memo:
            get_intrusion_lanes(ctx, target_id, ti, [h + d for h in hs for _, d in offsets])
        sets = [get_intrusion_lanes(ctx, target_id, ti, [h + d for _, d in offsets], memo=memo) for h in hs]
        need = {}
        for rs in sets:
            if all(_status(r, target_id) is None for r in rs):
                for r in rs:
                    if r.lane.runs is None:
                        need[id(r.lane)] = r.lane
        if need:
            TC._sample_lanes(ctx, target_id, list(need.values()), intent=INTENT)
        for h, rs in zip(hs, sets):
            total += 1
            got, why = assess_cell(ctx, target_id, ti, h, offsets, memo=memo, sigmas=sigmas, field_grids=phys,
                                   ilanes=rs)
            if detail:
                per_cell.append([ti, float(h), why])
            if got is None:
                reasons[why] = reasons.get(why, 0) + 1
                continue
            cells.append(got)
    out = {"cells": cells, "reasons": dict(sorted(reasons.items())), "n_cells": total,
           "seconds": time.perf_counter() - t0}
    if detail:
        out["per_cell"] = per_cell
    return out


# ---------------------------------------------------------------- 只读缓存（独立身份 intrusion_v17/）

def query_identity(ctx, target_id, offsets, sigmas):
    from ..scene.field import geometry_key
    from .layer_limits import constraints_identity
    tgt = ctx.facility_by_id[target_id]
    base = TC.transit_base(ctx, target_id, intent=INTENT)["base"]
    doc = {"version": CACHE_VERSION, "intent": INTENT, "context": ctx.cache_key, "target": target_id,
           "target_geometry": geometry_key(tgt.geometry),
           "layers": {k: geometry_key(g) for k, g in sorted(tgt.layers.items())},
           "all_layers": [[f.id, {k: geometry_key(g) for k, g in sorted(f.layers.items())}] for f in ctx.facilities],
           "base": [list(map(str, c)) for c in constraints_identity(base)],
           "offsets": [[float(l).hex(), float(d).hex()] for l, d in offsets],
           "sigmas": [float(s).hex() for s in sigmas],
           "contour_m": IN.CONTOUR_SKELETON_M, "protected_depth_m": IN.PROTECTED_DEPTH_M,
           "sigma_min_spacing_m": IN.SIGMA_MIN_SPACING_M, "sigma_den": IN.SIGMA_DEN,
           "theta_step_deg": TC.THETA_STEP_DEG, "h_step_m": TC.H_STEP_M, "x_step_m": TC.X_STEP_M, "q_m": TC.Q_M,
           "collect_ds": list(TC.COLLECT_DS), "collect_band": list(TC.COLLECT_BAND),
           "pre_entry_m": TC.PRE_ENTRY_SCAN_M, "band_m": TC.BAND_M}
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32], doc


def _cache_path(cache_dir, ctx, target_id, qid):
    return Path(cache_dir) / "intrusion_v17" / ctx.cache_key / f"{target_id}_{qid}.json"


def request_for(slots):
    offsets = [tuple(map(float, slots.offsets[m])) for m in slots.order]
    return offsets, IN.sigma_values(slots.spacing_m, slots.realized)


def load_chord_set(ctx, target_id, slots, cache_dir):
    """读取突入独立身份的缓存；缺失仅进程内算，不由 worker 写回。"""
    offsets, sigmas = request_for(slots)
    qid, _ = query_identity(ctx, target_id, offsets, sigmas)
    mem = ctx.extra.setdefault(("intrusion_chord_sets", target_id), {})
    if qid in mem:
        return mem[qid]
    p = None if cache_dir is None else _cache_path(cache_dir, ctx, target_id, qid)
    if p is not None and p.exists():
        doc = json.loads(p.read_text(encoding="utf-8"))
        STATS["cache_hits"] += 1
    else:
        doc = assess_formation(ctx, target_id, offsets, sigmas=sigmas)
        doc["query_id"] = qid
        STATS["cache_misses_computed"] += 1
    mem[qid] = doc
    return doc


def prewarm_intrusion(ctx, requests, cache_dir):
    """按族预建 requests = [(target_id, offsets, sigmas)]；先读已有文件，不重新计算再宣称命中；已存在不覆盖。"""
    rows = []
    for target_id, offsets, sigmas in requests:
        qid, ident = query_identity(ctx, target_id, offsets, sigmas)
        p = _cache_path(cache_dir, ctx, target_id, qid)
        if p.exists():
            raw = p.read_bytes()
            doc = json.loads(raw.decode("utf-8"))
            rows.append({"target": target_id, "query_id": qid, "existing": True, "n_cells": doc["n_cells"],
                         "feasible": len(doc["cells"]), "seconds": 0.0,
                         "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
            continue
        mem = ctx.extra.get(("intrusion_chord_sets", target_id), {})
        doc = dict(mem[qid]) if qid in mem else assess_formation(ctx, target_id, offsets, sigmas=sigmas)
        doc["query_id"] = qid
        doc["identity"] = ident
        p.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(raw)
        tmp.replace(p)
        rows.append({"target": target_id, "query_id": qid, "existing": False, "n_cells": doc["n_cells"],
                     "feasible": len(doc["cells"]), "seconds": doc["seconds"],
                     "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    return rows


# ---------------------------------------------------------------- 精确弦检查（抽中的唯一格，一次）

def assess_intrusion_bundle(ctx, base, target_id, origin_xy, direction_xy, offsets, x_c, x_e, sigma, *, band_m,
                            align_m):
    """成员 i 走直线 origin + x u + d_i n，x ∈ [x_c + l_i, x_e + σ l_i]（车道坐标）。逐车道精确检查：
    base 逐弦（polyline_clearance）；目标 warning/alert/protected 各恰一次正长度"进入"且终点在内、终点离各边界 ≥ band_m；
    目标 warning 入圈前 ≥ align_m 直线；终点 protected SDF ≤ −10、contour SDF ≤ 45、不越过车道最深点；
    其他设施 warning：起止点离边界 ≥ band_m，终点属于前缀合法区间并。返回 {"feasible", "first_error", "errors",
    "margins", "terminal"}。"""
    from ..scene.exact import polyline_clearance, signed_distance
    from .transit_chords import line_sublevel
    tgt = ctx.facility_by_id[target_id]
    o = np.asarray(origin_xy, float)
    u = np.asarray(direction_xy, float)
    u = u / float(np.hypot(*u))
    n = np.array([-u[1], u[0]])
    margins, errors, terminal = {}, [], []
    for l, d in offsets:
        p0 = o + float(d) * n
        a, b = float(x_c) + float(l), float(x_e) + float(sigma) * float(l)
        seg = np.array([p0 + a * u, p0 + b * u])
        for c in base:
            m = float(polyline_clearance(c.geometry, seg, sense=c.sense, minimum_m=c.minimum_m)[0])
            margins[c.name] = min(margins.get(c.name, math.inf), m)
            if m < 0.0:
                errors.append({"lane": (l, d), "constraint": c.name, "margin_m": m})
        for layer in ("warning", "alert", "protected"):
            g = tgt.layers[layer]
            I0 = line_sublevel(g, p0, u, 0.0)
            if I0 is None or not I0[1] > I0[0] or not (a < I0[0] < b <= I0[1]):
                errors.append({"lane": (l, d), "check": f"target_{layer}_single_entry", "interval": I0})
                continue
            if layer == "warning" and I0[0] - a < align_m - TC.ALIGN_TOL_M:
                errors.append({"lane": (l, d), "check": "align", "straight_m": I0[0] - a})
            sd = float(signed_distance(g, seg[1]))
            if sd > -band_m:
                errors.append({"lane": (l, d), "check": f"end_in_band_{layer}", "signed_m": sd})
        sd_p = float(signed_distance(tgt.layers["protected"], seg[1]))
        sd_c = float(signed_distance(tgt.geometry, seg[1]))
        xs = IN.deepest_station(tgt.geometry, p0, u)
        terminal.append({"lane": (float(l), float(d)), "x_end": b, "protected_sdf_m": sd_p, "contour_sdf_m": sd_c,
                         "deepest_x": xs})
        if sd_p > -IN.PROTECTED_DEPTH_M:
            errors.append({"lane": (l, d), "check": "terminal_protected", "signed_m": sd_p})
        if sd_c > IN.CONTOUR_SKELETON_M:
            errors.append({"lane": (l, d), "check": "terminal_contour", "signed_m": sd_c})
        if b > xs:
            errors.append({"lane": (l, d), "check": "beyond_deepest", "x_end": b, "deepest_x": xs})
        for f in ctx.facilities:
            if f.id == target_id:
                continue
            g = f.layers["warning"]
            for name, pt in (("start", seg[0]), ("end", seg[1])):
                sdv = float(signed_distance(g, pt))
                if abs(sdv) < band_m:
                    errors.append({"lane": (l, d), "check": f"{name}_in_band", "facility": f.id, "signed_m": sdv})
            pre = IN.prefix_endpoint_set({10.0: line_sublevel(g, p0, u, band_m), -10.0: line_sublevel(g, p0, u, -band_m)},
                                         a)
            if not any(lo <= b <= hi for lo, hi in pre):
                errors.append({"lane": (l, d), "check": "other_band", "facility": f.id})
    return {"feasible": not errors, "first_error": errors[0] if errors else None, "errors": errors[:20],
            "margins": margins, "terminal": terminal}
