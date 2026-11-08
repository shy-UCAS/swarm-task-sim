"""佯动入口格与按需判空（2026-11-08 裁定优先于原预建协议）。

坐标、航向/偏移网格、单车道解析与沿线采样直接调用 transit_chords（intent="feint" 时 base/缓存身份按意图参数化）；
不复制解析几何。实际成员入口车道 o + (x + l_i) u + (h + d_i) n，单车道按真实浮点 h + d_i 查询（不舍入）。

格级（cell_entry；只求集合，不计 attempt）：
  - 每条成员车道目标 warning 一次正长度穿越且能深进 10 m（Lane.target_status），入圈点所在合法 run；
  - x_in = min_i(e_i − l_i)；集合候选 x_c = x_in − D_c，D_c ∈ {100, …, 400}：参考点目标 warning SDF ∈ [50, 250]、
    每个槽位过原 collect_phys（feint base + 全部 warning 外 10）、预留起点 min(x_c, x_in − 210) + l_i 不早于该 run；
  - A 网格：中心线 line_sublevel(alert, o + h n, u, −10) 内的全局 5 m 倍数（数学 ceil/floor 端点）。
A 级（entry_at_A）：成员实际支撑起点 X_i = A + l_i − l* 在该车道 alert −10 区间内且不越过入圈 run；B = A + L 在中心线
  alert −10 区间内；其他设施 warning 在 [x_c + l_i, X_i] 上整段离带或完整深穿（transit_chords._band_ok），逐 D 过滤。
生产先求廉价入口候选表，以 shape 流排列，按固定 first_feasible 谓词取首个非空格。
存在性结果只在单合同内存中复用；冷热不改变排列、谓词或业务载荷。旧全格 API 仅供历史诊断，生产不调用，
不读写已有 cache/feint_v18 文件。单车道、距离场等几何缓存沿用。
"""
import hashlib
import json
import math
import time
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np

from . import feint_turn as FT
from . import monitoring_turn as MT
from . import transit_chords as TC

CACHE_VERSION = "v18-feint-cells-1"
INTENT = "feint"
CERT_MODE = "screened"            # 裁定 1：门禁通过后生产预建与 worker 认证显式用 screened（缓存身份记录）
CERT_PRUNE = True                 # 裁定 3(a)
GATE_MAX_CELLS = 24               # 裁定 3(b)
GATE_A_EVERY = 4
STATS = {"cache_hits": 0, "cache_misses_computed": 0}
LAZY_VERSION = "v18-feint-lazy-1"


def begin_contract(ctx, key):
    """限定逐格存在性 memo 的生命周期；attempt 不在合同身份中。"""
    identity = (key.family_id, key.draw, key.mission, key.branch, key.group, key.segment)
    mem = ctx.extra.get("feint_lazy_contract")
    if mem is None or mem["identity"] != identity:
        ctx.extra["feint_lazy_contract"] = {"identity": identity, "cells": {}}


def candidate_cells(ctx, target_id, slots):
    """只做既有廉价入口检查；规范 θ/h 顺序，不调用任何掉头认证。"""
    offsets, spacing = request_for(slots)
    qid, _ = query_identity(ctx, target_id, offsets, spacing)
    mem = ctx.extra.setdefault("feint_entry_candidates", {})
    if qid not in mem:
        cells, reasons, total = [], {}, 0
        for ti, th in enumerate(TC.thetas()):
            hs = TC.h_values(ctx, target_id, th)
            TC.get_lanes(ctx, target_id, ti, [h + d for h in hs for _, d in offsets], intent=INTENT)
            for h in hs:
                total += 1
                ce, why = cell_entry(ctx, target_id, offsets, ti, h)
                if ce is None:
                    reasons[why] = reasons.get(why, 0) + 1
                else:
                    cells.append(_cell_doc(ti, h, ce))
        mem[qid] = {"schema": LAZY_VERSION, "query_id": qid, "cells": cells, "n_cells": total,
                    "reasons": dict(sorted(reasons.items()))}
    return mem[qid]


def first_nonempty(cells, certify, rng):
    """一次均匀排列，逐格确定性判空。返回 (规范下标, 见证, 已走格下标)，全空时前两项 None。"""
    walked = []
    for index in rng.permutation(len(cells)):
        index = int(index)
        walked.append(index)
        witness = certify(cells[index])
        if witness is not None:
            return index, witness, walked
    return None, None, walked


def sample_cell(ctx, task, slots, rng):
    """每个 probe 各走一次 shape 排列；逐格存在性谓词/规范顺序保持原样。"""
    doc = candidate_cells(ctx, task.target_id, slots)
    cells, qid = doc["cells"], doc["query_id"]
    memo = ctx.extra["feint_lazy_contract"]["cells"]
    stats = {}
    t0 = time.perf_counter()

    def certify(cell):
        identity = (qid, cell["theta_idx"], cell["h_m"])
        if identity in memo:
            STATS["cache_hits"] += 1
            return memo[identity]
        rec = first_feasible(ctx, task, slots, cell, mode=CERT_MODE, prune=CERT_PRUNE, stats=stats)
        witness = None if rec is None else {k: rec[k] for k in (
            "A_m", "kind", "side", "radius_m", "collect_D_compatible", "terminal_x")}
        memo[identity] = witness
        STATS["cache_misses_computed"] += 1
        return witness

    index, witness, walked = first_nonempty(cells, certify, rng)
    # 业务摘要只含确定性字段；计时、完整走格记录与认证计数另交给目录外遥测。
    summary = {"query_id": qid, "n_cells": doc["n_cells"], "candidate_cells": len(cells),
               "cells_examined": len(walked), "nonempty_position": None if index is None else len(walked),
               "cell_index": index, "reasons": doc["reasons"]}
    telemetry = {**summary, "visited_cell_indices": walked, "stats": stats,
                 "seconds": time.perf_counter() - t0}
    return {"cell": None if index is None else cells[index], "witness": witness,
            "summary": summary, "telemetry": telemetry}


# ---------------------------------------------------------------- 格级

def centerline_A(ctx, target_id, theta_idx, h):
    key = ("feint_v18_A", target_id, int(theta_idx), float(h))
    if key not in ctx.extra:
        tgt = ctx.facility_by_id[target_id]
        th = TC.thetas()[int(theta_idx)]
        u, n = TC.frame(th)
        o = np.asarray(tgt.center, float)
        I = TC.line_sublevel(tgt.layers["alert"], o + float(h) * n, u, -FT.BAND_M)
        if I is None:
            ctx.extra[key] = np.zeros(0)
        else:
            k0, k1 = math.ceil(I[0] / FT.A_STEP_M), math.floor(I[1] / FT.A_STEP_M)
            ctx.extra[key] = FT.A_STEP_M * np.arange(k0, k1 + 1, dtype=float)
    return ctx.extra[key]


def _offs(slots):
    return [(float(slots.offsets[m][0]), float(slots.offsets[m][1])) for m in slots.order]


def cell_entry(ctx, target_id, offsets, theta_idx, h, *, lanes=None):
    """返回 (dict, None) 或 (None, 原因)。dict：x_in、D_pre（升序）、各车道入圈 e、run、alert −10 区间、Lane 对象。"""
    offsets = [(float(l), float(d)) for l, d in offsets]
    key = ("feint_v18_cell", target_id, tuple((l.hex(), d.hex()) for l, d in offsets), int(theta_idx), float(h))
    if key in ctx.extra:
        return ctx.extra[key]
    tgt = ctx.facility_by_id[target_id]
    if lanes is None:
        lanes = TC.get_lanes(ctx, target_id, int(theta_idx), [float(h) + d for _, d in offsets], intent=INTENT)
    out = None
    for L in lanes:
        why = L.target_status(target_id)
        if why is not None:
            out = (None, why)
            break
    if out is None:
        TC._sample_lanes(ctx, target_id, lanes, intent=INTENT)
        E, runs = [], []
        for (l, d), L in zip(offsets, lanes):
            e = L.sub[target_id][0.0][0]
            R = L.legal_run(e)
            if R is None:
                out = (None, "lane_blocked_in_target")
                break
            E.append(float(e))
            runs.append(R)
    if out is None:
        u, n = TC.frame(TC.thetas()[int(theta_idx)])
        o = np.asarray(tgt.center, float)
        x_in = min(e - l for e, (l, _) in zip(E, offsets))
        P0 = np.stack([np.asarray(L.p0, float) for L in lanes])
        alo, ahi = TC.sublevel_many(tgt.layers["alert"], P0, u, -FT.BAND_M)
        phys = TC.collect_phys_grid(ctx, target_id, intent=INTENT)
        from ..scene.exact import signed_distance
        Ds = np.asarray(TC.COLLECT_DS, float)
        xcs = x_in - Ds
        C = o[None] + xcs[:, None] * u[None] + (float(h) * n)[None]
        sd = np.asarray(signed_distance(tgt.layers["warning"], C), float)
        keep = (TC.COLLECT_BAND[0] <= sd) & (sd <= TC.COLLECT_BAND[1])
        slots_xy = np.stack([o[None] + (xcs + l)[:, None] * u[None] + ((float(h) + d) * n)[None] for l, d in offsets],
                            axis=1)
        keep &= np.all(phys.ok(slots_xy), axis=1)
        for (l, d), R in zip(offsets, runs):
            s0 = np.minimum(xcs, x_in - TC.PRE_ENTRY_SCAN_M) + l
            keep &= ~(s0 < R[0] - 1e-9)
        Dpre = [float(D) for D, k in zip(Ds, keep) if k]
        if not Dpre:
            out = (None, "no_collect_candidate")
        elif not len(centerline_A(ctx, target_id, theta_idx, h)):
            out = (None, "no_alert_depth")
        else:
            out = ({"x_in": float(x_in), "D_pre": Dpre, "E": E, "runs": runs, "lanes": lanes,
                    "alert_iv": [(None if np.isnan(a) else (float(a), float(b))) for a, b in zip(alo, ahi)]}, None)
    ctx.extra[key] = out
    return out


def entry_at_A(ctx, target_id, slots, cell, A_m, L, l_star):
    """A 级入口检查（解析精确，与认证模式无关）。返回 {"reason", "D_list", "A_list", "X_ss"}。"""
    offsets = _offs(slots)
    key = ("feint_v18_entryA", target_id, tuple((l.hex(), d.hex()) for l, d in offsets), int(cell["theta_idx"]),
           float(cell["h_m"]), float(A_m))
    if key in ctx.extra:
        return ctx.extra[key]
    As = centerline_A(ctx, target_id, cell["theta_idx"], cell["h_m"])
    res = {"reason": None, "D_list": [], "A_list": As, "X_ss": None}
    ce, why = cell_entry(ctx, target_id, offsets, cell["theta_idx"], cell["h_m"])
    if ce is None:
        res["reason"] = why
    elif not len(As) or not _B_inside(ctx, target_id, cell, float(A_m) + float(L)):
        res["reason"] = "collapse_end_outside_alert"        # B 是每个成员折线上的点（横向偏移 0）
    else:
        X = [float(A_m) + l - float(l_star) for l, _ in offsets]
        res["X_ss"] = X
        for (l, d), x, iv, R, e in zip(offsets, X, ce["alert_iv"], ce["runs"], ce["E"]):
            if iv is None or not (iv[0] <= x <= iv[1]):
                res["reason"] = "collapse_start_outside_alert"
                break
            if not (e <= x <= R[1] + 1e-9):
                res["reason"] = "entry_run_ends_before_support"
                break
        if res["reason"] is None:
            # q = s_A 处成员点 A + d_i n（成员折线上的精确节点，支撑起点之一）须在 alert −10 内、protected +10 外
            from ..scene.exact import signed_distance
            tgt = ctx.facility_by_id[target_id]
            u, n = TC.frame(TC.thetas()[int(cell["theta_idx"])])
            o = np.asarray(tgt.center, float)
            pa = np.array([o + float(A_m) * u + (float(cell["h_m"]) + d) * n for _, d in offsets])
            if not (np.all(np.asarray(signed_distance(tgt.layers["alert"], pa)) <= -FT.BAND_M)
                    and np.all(np.asarray(signed_distance(tgt.layers["protected"], pa)) >= FT.BAND_M)):
                res["reason"] = "support_corner_outside_band"
        if res["reason"] is None:
            others = [f.id for f in ctx.facilities if f.id != target_id]
            Dl = []
            for D in cell["collect_D_candidates"]:
                xc = float(cell["x_in"]) - float(D)
                ok = True
                for (l, d), x, Ln in zip(offsets, X, ce["lanes"]):
                    for fid in others:
                        if not bool(TC._band_ok(Ln.sub[fid], xc + l, x)):
                            ok = False
                            break
                    if not ok:
                        break
                if ok:
                    Dl.append(float(D))
            if not Dl:
                res["reason"] = "no_collect_for_A"
            res["D_list"] = Dl
    ctx.extra[key] = res
    return res


def _B_inside(ctx, target_id, cell, xB):
    tgt = ctx.facility_by_id[target_id]
    u, n = TC.frame(TC.thetas()[int(cell["theta_idx"])])
    o = np.asarray(tgt.center, float)
    I = TC.line_sublevel(tgt.layers["alert"], o + float(cell["h_m"]) * n, u, -FT.BAND_M)
    return I is not None and I[0] <= xB <= I[1]


def _cell_doc(ti, h, ce):
    return {"theta_idx": int(ti), "h_m": float(h), "x_in": float(ce["x_in"]),
            "collect_D_candidates": [float(x) for x in ce["D_pre"]]}


# ---------------------------------------------------------------- 队形存在性

def _slots_from(offsets, spacing_m):
    order = tuple(f"slot{i:02d}" for i in range(len(offsets)))
    return NS(order=order, offsets={m: (float(l), float(d)) for m, (l, d) in zip(order, offsets)},
              spacing_m=float(spacing_m))


def first_feasible(ctx, task, slots, cell, *, mode=CERT_MODE, prune=CERT_PRUNE, stats=None):
    """规范顺序 KINDS × SIDES × A 升序 × R 升序的首个完整可行候选（找到即停）；无解返回 None。"""
    T = FT.turn_context(ctx, task.target_id)
    As = centerline_A(ctx, task.target_id, cell["theta_idx"], cell["h_m"])
    st = stats if stats is not None else {}
    L, l_star, _ = FT.formation_params(slots)
    # A 级入口检查与组合无关（certify_candidate 首先调用同一函数）：先算一次，只跳过必然被它拒绝的 A
    a_ok = np.array([entry_at_A(ctx, task.target_id, slots, cell, float(a), L, l_star)["reason"] is None for a in As],
                    bool)
    st["A_rejected"] = st.get("A_rejected", 0) + int((~a_ok).sum())
    for kind in MT.KINDS:
        for side in MT.SIDES:
            R = T.radii[kind]
            if prune:
                mask = FT.keypoint_mask(ctx, task, slots, cell, kind, side) & a_ok[:, None]
                flat = np.flatnonzero(mask.reshape(-1))
                st["keypoint_pruned"] = st.get("keypoint_pruned", 0) + int(mask.size - len(flat))
            else:
                flat = np.flatnonzero(np.repeat(a_ok, len(R)))
            for f in flat.tolist():
                ia, ir = divmod(int(f), len(R))
                cand = {"A_m": float(As[ia]), "kind": kind, "side": int(side), "radius_m": float(R[ir])}
                st["certified"] = st.get("certified", 0) + 1
                got = FT.certify_candidate(ctx, task, slots, cell, cand, mode=mode, prune=prune, stats=st)
                if got["feasible"]:
                    return got["record"]
    return None


def assess_formation(ctx, target_id, offsets, *, spacing_m, memo=True, detail=False):
    """全部 (θ, h) 格按 θ、h 升序；返回 {"schema","cells","reasons","n_cells","stats","seconds"}。
    cells 只含存在完整可行掉头的格，并附首个可行 candidate（存在性见证，含其相容 D_c）。detail=True 另给 per_cell。"""
    from ..contract.monitoring import TaskSpec
    t0 = time.perf_counter()
    offsets = [(float(l), float(d)) for l, d in offsets]
    slots = _slots_from(offsets, spacing_m)
    task = TaskSpec("task0", INTENT, target_id)
    tgt_cells, reasons, total, per_cell = [], {}, 0, []
    st = {}
    cell_times = []
    for ti, th in enumerate(TC.thetas()):
        hs = TC.h_values(ctx, target_id, th)
        if memo:
            TC.get_lanes(ctx, target_id, ti, [h + d for h in hs for _, d in offsets], intent=INTENT)
        for h in hs:
            total += 1
            tc0 = time.perf_counter()
            ce, why = cell_entry(ctx, target_id, offsets, ti, h)
            rec = None
            if ce is not None:
                rec = first_feasible(ctx, task, slots, _cell_doc(ti, h, ce), stats=st)
                if rec is None:
                    why = "no_feasible_turn"
            cell_times.append(time.perf_counter() - tc0)
            if detail:
                per_cell.append([ti, float(h), why])
            if rec is None:
                reasons[why] = reasons.get(why, 0) + 1
                continue
            doc = _cell_doc(ti, h, ce)
            doc["witness"] = {k: rec[k] for k in ("A_m", "kind", "side", "radius_m", "collect_D_compatible",
                                                  "terminal_x")}
            tgt_cells.append(doc)
    L, l_star, _ = FT.formation_params(slots)
    out = {"schema": CACHE_VERSION, "cells": tgt_cells, "reasons": dict(sorted(reasons.items())), "n_cells": total,
           "L_m": L, "l_star_m": l_star, "stats": st, "seconds": time.perf_counter() - t0,
           "cell_seconds": {"max": max(cell_times) if cell_times else 0.0, "sum": float(sum(cell_times))}}
    if detail:
        out["per_cell"] = per_cell
    return out


# ---------------------------------------------------------------- 只读缓存

def request_for(slots):
    return [tuple(map(float, slots.offsets[m])) for m in slots.order], float(slots.spacing_m)


def query_identity(ctx, target_id, offsets, spacing_m):
    from ..scene.field import geometry_key
    from .layer_limits import constraints_identity
    tgt = ctx.facility_by_id[target_id]
    cons = TC.transit_base(ctx, target_id, intent=INTENT)
    T = FT.turn_context(ctx, target_id)
    L, l_star, _ = FT.formation_params(_slots_from(offsets, spacing_m))
    doc = {"version": CACHE_VERSION, "turn_version": FT.VERSION, "intent": INTENT, "context": ctx.cache_key,
           "target": target_id, "target_geometry": geometry_key(tgt.geometry),
           "layers": {k: geometry_key(g) for k, g in sorted(tgt.layers.items())},
           "all_layers": [[f.id, {k: geometry_key(g) for k, g in sorted(f.layers.items())}] for f in ctx.facilities],
           "base": [list(map(str, c)) for c in constraints_identity(cons["base"])],
           "crossing": [[k, geometry_key(g)] for k, g in cons["crossing_boundaries"].items()],
           "offsets": [[float(l).hex(), float(d).hex()] for l, d in offsets], "spacing_m": float(spacing_m).hex(),
           "L_m": float(L).hex(), "l_star_m": float(l_star).hex(),
           "theta_step_deg": TC.THETA_STEP_DEG, "h_step_m": TC.H_STEP_M, "x_step_m": TC.X_STEP_M, "q_m": TC.Q_M,
           "collect_ds": list(TC.COLLECT_DS), "collect_band": list(TC.COLLECT_BAND),
           "pre_entry_m": TC.PRE_ENTRY_SCAN_M, "band_m": FT.BAND_M, "retreat_m": T.retreat,
           "a_step_m": FT.A_STEP_M, "r_step_m": FT.R_STEP_M, "r_factor": FT.R_FACTOR,
           "r_min": T.rmin, "r_max": {k: float(v).hex() for k, v in T.rmax.items()},
           "kinds": list(MT.KINDS), "sides": list(MT.SIDES), "screen_q_m": FT.SCREEN_Q_M,
           "screen_step_m": FT.SCREEN_STEP_M, "straight_step_m": FT.STRAIGHT_STEP_M, "window_pad_m": FT.WINDOW_PAD_M,
           "keypoints": FT.KEYPOINTS, "mode": CERT_MODE, "prune": CERT_PRUNE}
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32], doc


def _cache_path(cache_dir, ctx, target_id, qid):
    return Path(cache_dir) / "feint_v18" / ctx.cache_key / f"{target_id}_{qid}.json"


def load_chord_set(ctx, target_id, slots, cache_dir):
    """返回 {"schema","query_id","cells","n_cells","reasons"}（只读预建文件；缺失仅进程内算，不由 worker 写回）。"""
    offsets, spacing = request_for(slots)
    qid, _ = query_identity(ctx, target_id, offsets, spacing)
    mem = ctx.extra.setdefault(("feint_chord_sets", target_id), {})
    if qid in mem:
        return mem[qid]
    p = None if cache_dir is None else _cache_path(cache_dir, ctx, target_id, qid)
    if p is not None and p.exists():
        doc = json.loads(p.read_text(encoding="utf-8"))
        STATS["cache_hits"] += 1
    else:
        doc = assess_formation(ctx, target_id, offsets, spacing_m=spacing)
        doc["query_id"] = qid
        STATS["cache_misses_computed"] += 1
    mem[qid] = doc
    return doc


def prewarm_feint(ctx, requests, cache_dir):
    """requests = [(target_id, offsets 按槽位顺序, spacing_m)]；按完整查询身份去重。已存在文件先验身份与散列、不覆盖。"""
    rows, seen = [], set()
    for target_id, offsets, spacing in requests:
        qid, ident = query_identity(ctx, target_id, offsets, spacing)
        if qid in seen:
            continue
        seen.add(qid)
        p = _cache_path(cache_dir, ctx, target_id, qid)
        if p.exists():
            raw = p.read_bytes()
            doc = json.loads(raw.decode("utf-8"))
            if doc.get("identity") != json.loads(json.dumps(ident)):
                raise ValueError(f"预建文件身份不符：{p}")
            rows.append({"target": target_id, "query_id": qid, "existing": True, "n_cells": doc["n_cells"],
                         "feasible": len(doc["cells"]), "seconds": 0.0, "stats": doc.get("stats"),
                         "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
            continue
        mem = ctx.extra.get(("feint_chord_sets", target_id), {})
        doc = dict(mem[qid]) if qid in mem else assess_formation(ctx, target_id, offsets, spacing_m=spacing)
        doc["query_id"] = qid
        doc["identity"] = ident
        p.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(raw)
        tmp.replace(p)
        rows.append({"target": target_id, "query_id": qid, "existing": False, "n_cells": doc["n_cells"],
                     "feasible": len(doc["cells"]), "seconds": doc["seconds"], "stats": doc.get("stats"),
                     "reasons": doc.get("reasons"), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    return rows


# ---------------------------------------------------------------- 等价门禁子集（裁定 3(b)）

def _gate_radius_index(n):
    ks, k = [0], 1
    while k < n:
        ks.append(k)
        k *= 2
    return [k for k in ks if k < n]


def gate_cells(ctx, task, slots):
    """规范顺序中 A 网格非空的格，按等间隔取至多 GATE_MAX_CELLS 个（含可行与空格）。"""
    cells = []
    for ti, th in enumerate(TC.thetas()):
        for h in TC.h_values(ctx, task.target_id, th):
            if len(centerline_A(ctx, task.target_id, ti, h)):
                cells.append((ti, float(h)))
    if len(cells) > GATE_MAX_CELLS:
        idx = np.unique(np.linspace(0, len(cells) - 1, GATE_MAX_CELLS).round().astype(int))
        cells = [cells[i] for i in idx]
    return cells


def iter_certification_cases(ctx, task, slots):
    """逐个产生 (cell, candidate)（裁定 3(b) 的确定性门禁子集：至多 24 格 × 6 组合 × 每第 4 个 A × R 的 k ∈
    {0, 1, 2, 4, 8, …}）；不在首个可行者处短路，包括后来被拒绝的候选。cell 的 collect_D_candidates 用格级预检；
    格级预检失败的格以空列表给出（认证会如实拒绝）。"""
    T = FT.turn_context(ctx, task.target_id)
    offsets = _offs(slots)
    for ti, h in gate_cells(ctx, task, slots):
        ce, _ = cell_entry(ctx, task.target_id, offsets, ti, h)
        cell = {"theta_idx": ti, "h_m": h, "x_in": float(ce["x_in"]) if ce else float("nan"),
                "collect_D_candidates": list(ce["D_pre"]) if ce else []}
        As = centerline_A(ctx, task.target_id, ti, h)
        for kind in MT.KINDS:
            R = T.radii[kind]
            for side in MT.SIDES:
                for ia in range(0, len(As), GATE_A_EVERY):
                    for ir in _gate_radius_index(len(R)):
                        yield cell, {"A_m": float(As[ia]), "kind": kind, "side": int(side), "radius_m": float(R[ir])}
