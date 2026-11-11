"""V8-21 迂回：编组名义预筛 screen_detour、优化后检查 check_detour、实测候选核验 verify_detour_candidate
（指令 4.1–4.4；裁定 4 增加 ended_outside_near_band）。不放入冻结 criteria 包，不经过 verify_segments。

名义口径（nominal=True）：层值用 nominal_checks.layer_levels（与冻结规则相同的最内层优先），驻留/重访用冻结检测器的
原样抽取函数；扫角下限 Θ + nominal_sweep_margin_deg、上限 < nominal_max_sweep_deg_exclusive。
候选口径（verify_detour_candidate）：几何直接取场景显式 facility/protection_zone，冻结 task_v07.geometry_facts 求层，
task_v07.detectors 求驻留/重访；扫角下限 Θ、上限 < max_sweep_deg_exclusive。
"""
import math

import numpy as np

MEMBER_CONDITIONS = ("started_outside_all_warning", "target_layer_zero", "other_layers_within_limit", "no_dwell_window",
                     "no_revisit_window", "single_near_visit", "min_sweep", "max_sweep", "ended_outside_all_warning",
                     "ended_outside_near_band", "terminal_clearance")
GROUP_CONDITIONS = ("other_sweep_below_threshold",)


def _cand(candidate):
    if candidate is None:
        from .detour_config import load_detour_candidate
        return load_detour_candidate()
    return candidate


def _check_samples(mid, t, p, v):
    n = len(t)
    if n == 0:
        raise ValueError(f"成员 {mid} 的窗口为空（结构错误）")
    if t.ndim != 1 or not np.issubdtype(t.dtype, np.integer) or p.shape != (n, 3) or v.shape != (n, 3):
        raise ValueError(f"成员 {mid}：需要整数 10 Hz time_us 与 (T,3) p/v")
    if (n > 1 and np.any(np.diff(t) != 100000)) or not (np.isfinite(p).all() and np.isfinite(v).all()):
        raise ValueError(f"成员 {mid}：非 10 Hz 或含非有限值")


def _evaluate(members, fac_ids, target_id, layers_fn, sd_fn, center_of, D, lo, hi, retreat, dwell_fn, revisit_fn,
              max_other):
    """members[mid] = (t, xy, v)。返回逐成员 conditions/facts 与编组 G_f。"""
    from .detour_numeric import group_sweep, sweep_series
    mc, mf, maxima = {}, {}, {}
    ti = fac_ids.index(target_id)
    for mid in sorted(members):
        t, xy, v = members[mid]
        n = len(t)
        levels = np.column_stack([layers_fn(f, xy) for f in fac_ids]).astype(np.int8)
        tl = levels[:, ti]
        other = [j for j in range(len(fac_ids)) if j != ti]
        max_oth = int(levels[:, other].max()) if other else 0
        series = {}
        for f in fac_ids:
            c = np.asarray(center_of(f), float)
            series[f] = sweep_series(t, sd_fn(f, xy), np.arctan2(xy[:, 1] - c[1], xy[:, 0] - c[0]), D)
        s = series[target_id]
        maxima[mid] = {f: float(series[f]["max_span_deg"]) for f in fac_ids}
        ones = np.ones(n, bool)
        dw = dwell_fn(xy, t, ones)
        rv = revisit_fn(xy, v, t, tl, ones, np.asarray(center_of(target_id), float))
        sd_t = np.asarray(sd_fn(target_id, xy), float)
        term = {f: float(sd_fn(f, xy[-1:])[0]) for f in fac_ids}
        cond = {"started_outside_all_warning": bool(int(levels[0].max()) == 0),
                "target_layer_zero": bool(int(tl.max()) == 0),
                "other_layers_within_limit": bool(max_oth <= max_other),
                "no_dwell_window": not bool(dw["detected"]),
                "no_revisit_window": not bool(rv["detected"]),
                "single_near_visit": bool(s["entry_count"] == 1),
                "min_sweep": bool(float(s["max_span_deg"]) >= lo),
                "max_sweep": bool(all(float(r["span_deg"]) < hi for r in s["runs"])),
                "ended_outside_all_warning": bool(int(levels[-1].max()) == 0),
                "ended_outside_near_band": bool(float(sd_t[-1]) > D),
                "terminal_clearance": bool(all(x >= retreat for x in term.values()))}
        mc[mid] = cond
        mf[mid] = {"near_entry_count": int(s["entry_count"]), "near_exit_count": int(s["exit_count"]),
                   "first_near_entry_us": s["first_entry_us"], "last_near_exit_us": s["last_exit_us"],
                   "starts_in_band": bool(s["starts_in_band"]), "ends_in_band": bool(s["ends_in_band"]),
                   "max_span_deg": float(s["max_span_deg"]), "best_net_deg": float(s["best_net_deg"]),
                   "all_runs": s["runs"], "min_target_warning_distance_m": float(sd_t.min()),
                   "max_target_layer": int(tl.max()), "max_other_layer": max_oth,
                   "terminal_warning_distances_m": term, "frames": int(n),
                   "dwell_detected": bool(dw["detected"]), "revisit_detected": bool(rv["detected"]),
                   "first_layers": {f: int(levels[0, j]) for j, f in enumerate(fac_ids)},
                   "last_layers": {f: int(levels[-1, j]) for j, f in enumerate(fac_ids)}}
    g = group_sweep(maxima)
    others = {f: float(g["by_facility"][f]) for f in fac_ids if f != target_id}
    return mc, mf, others


def _assemble(mc, mf, others, theta, sha):
    gc = {"other_sweep_below_threshold": bool(all(x < theta for x in others.values()))}
    failures = []
    for k in MEMBER_CONDITIONS:
        for mid in sorted(mc):
            if not mc[mid][k]:
                failures.append([mid, k, "failed"])
    for k in GROUP_CONDITIONS:
        if not gc[k]:
            failures.append(["group", k, "failed"])
    passed = bool(mc and all(all(c.values()) for c in mc.values()) and all(gc.values()))
    out = {"passed": passed, "member_conditions": mc, "member_facts": mf, "group_conditions": gc,
           "group_facts": {"other_facility_sweep_deg": others}, "failures": failures}
    if sha is not None:
        out["criteria_sha256"] = sha
    return out


def screen_detour(scene, facilities, target_id, samples, *, candidate=None, nominal=True, criteria=None):
    """编组名义预筛。samples[mid] = {"time_us": int64[T], "p": float[T,3], "v": float[T,3]}（释放起至移动结束 + 冻结末端
    hold）。facilities 为 v08 场景设施（geometry/layers/offsets）。"""
    from task_v07.criteria import load_criteria
    from ..config import load_config
    from ..scene.exact import center_of_geometry, signed_distance
    from .nominal_checks import dwell, layer_levels, revisit
    C = _cand(candidate)
    Cv = C.values
    Gd = load_config("detour").values
    M = load_config("monitoring").values
    seg = load_config("criteria_segment").values
    cfg = criteria if criteria is not None else load_criteria()
    if not samples:
        raise ValueError("成员集为空")
    facs = {f.id: f for f in facilities}
    fac_ids = [f.id for f in facilities]
    if target_id not in facs:
        raise ValueError("目标设施不存在")
    members = {}
    for mid, s in samples.items():
        t = np.asarray(s["time_us"])
        p, v = np.asarray(s["p"], float), np.asarray(s["v"], float)
        _check_samples(mid, t, p, v)
        members[mid] = (t, p[:, :2], v)
    if nominal:
        lo = float(Cv["min_sweep_deg"]) + float(Gd["nominal_sweep_margin_deg"])
        hi = float(Gd["nominal_max_sweep_deg_exclusive"])
    else:
        lo, hi = float(Cv["min_sweep_deg"]), float(Cv["max_sweep_deg_exclusive"])
    mc, mf, others = _evaluate(
        members, fac_ids, target_id,
        lambda f, xy: layer_levels(facs[f], xy)[0],
        lambda f, xy: np.asarray(signed_distance(facs[f].layers["warning"], xy), float),
        lambda f: center_of_geometry(facs[f].geometry), float(Cv["near_band_width_m"]), lo, hi,
        float(M["retreat_clearance_m"]),
        lambda xy, t, fr: dwell(xy, t, fr, cfg),
        lambda xy, v, t, lv, fr, c: revisit(xy, v, t, lv, fr, c, cfg),
        int(seg["max_other_facility_layer"]))
    return _assemble(mc, mf, others, float(Cv["min_sweep_deg"]), None)


def _scene_geometry(scene):
    facs, layers = {}, {}
    for e in scene["entities"]:
        if e.get("type") == "facility":
            facs[e["id"]] = e["geometry"]
    for f in facs:
        layers[f] = {}
    for e in scene["entities"]:
        if e.get("type") == "protection_zone":
            layers.setdefault(e["facility_id"], {})[e["layer"]] = e["geometry"]
    return facs, layers


def verify_detour_candidate(scene, tracks, release_us, target_id, *, candidate=None, criteria=None):
    """实测候选核验（独立字典，不是 SegmentVerdict）：非空成员集且与 release 一致；完整窗口
    (tau ≥ release) & (segment_index == 0)；几何取场景显式层；冻结 geometry_facts/dwell/revisit；4.1 扫角。"""
    from task_v07 import detectors
    from task_v07.criteria import load_criteria
    from task_v07.geometry import geometry_facts
    from ..config import load_config
    from ..scene.exact import center_of_geometry
    C = _cand(candidate)
    Cv = C.values
    M = load_config("monitoring").values
    seg = load_config("criteria_segment").values
    cfg = criteria if criteria is not None else load_criteria()
    if not tracks or set(tracks) != set(release_us):
        raise ValueError("实测成员集为空或与 release 成员集不一致")
    facs, layers = _scene_geometry(scene)
    if target_id not in facs:
        raise ValueError("目标设施不存在于场景")
    fac_ids = sorted(facs)
    for f in fac_ids:
        if "warning" not in layers.get(f, {}):
            raise ValueError(f"设施 {f} 缺显式 warning")
    members = {}
    for mid in sorted(tracks):
        tr = tracks[mid]
        tau = np.asarray(tr.tau_us)
        mask = (tau >= int(release_us[mid])) & (np.asarray(tr.segment_index) == 0)
        t = tau[mask].astype(np.int64)
        p, v = np.asarray(tr.p, float)[mask], np.asarray(tr.v, float)[mask]
        _check_samples(mid, t, p, v)
        members[mid] = (t, p[:, :2], v)

    def lv(f, xy):
        out = np.zeros(len(xy), np.int8)
        for name, code in (("warning", 1), ("alert", 2), ("protected", 3)):
            g = layers[f].get(name)
            if g is not None:
                out = np.where(np.asarray(geometry_facts(g, xy)["inside"], bool), code, out)
        return out

    def sd(f, xy):
        return np.asarray(geometry_facts(layers[f]["warning"], np.asarray(xy, float))["signed_distance_m"], float)

    mc, mf, others = _evaluate(
        members, fac_ids, target_id, lv, sd, lambda f: center_of_geometry(facs[f]),
        float(Cv["near_band_width_m"]), float(Cv["min_sweep_deg"]), float(Cv["max_sweep_deg_exclusive"]),
        float(M["retreat_clearance_m"]),
        lambda xy, t, fr: detectors.dwell(xy, t, fr, cfg),
        lambda xy, v, t, lvl, fr, c: detectors.revisit(xy, v, t, lvl, fr, c, cfg),
        int(seg["max_other_facility_layer"]))
    return _assemble(mc, mf, others, float(Cv["min_sweep_deg"]), C.sha256)


# ---------------------------------------------------------------- 优化后检查（指令 4.3）

def _ticks(release_s, end_s, hold_s):
    r_us = int(round(release_s * 10)) * 100_000
    e_us = int(math.floor((end_s + hold_s) * 10 + 1e-9)) * 100_000
    return np.arange(r_us, e_us + 1, 100_000, dtype=np.int64)


def check_detour(ctx, skeleton, trajectories, settings):
    """优化后检查：crossing_analysis（crossing_boundaries，target=near_key，不传 skip_ranges）要求 near 恰 [in, out]、
    真实目标 warning 无穿越；末点对所有真实 warning ≥ retreat；名义帧沿 check_transit 口径后调用 screen_detour。"""
    from ..config import load_config
    from ..contract.monitoring import TaskSpec
    from ..scene.exact import signed_distance
    from .connect import crossing_analysis
    from .detour_geometry import detour_constraints
    from .optimize import physical_limits
    from .optimize_checks import _grid_times
    hold = physical_limits(settings)["hold_s"]
    M = load_config("monitoring").values
    target = skeleton.witnesses["target_id"]
    cons = detour_constraints(ctx, TaskSpec("task0", "detour", target))
    near_key = cons["near_key"]
    failures, boundaries, samples = [], {}, {}
    for mid in sorted(trajectories):
        tr = trajectories[mid]
        xy = tr.evaluate(_grid_times(tr) + tr.release_s, 0)
        viol, cross = crossing_analysis(xy, cons["crossing_boundaries"], near_key,
                                        band_m=ctx.params["pre_entry_warning_clearance_m"],
                                        align_m=ctx.params["alignment_length_m"])
        boundaries[mid] = {"violations": viol, "crossings": [(c.facility_id, c.direction, float(c.s_m)) for c in cross]}
        if viol:
            failures.append({"kind": "boundary_crossing", "member": mid, "first": viol[0], "count": len(viol)})
        nd = [c.direction for c in cross if c.facility_id == near_key]
        if nd != ["in", "out"]:
            failures.append({"kind": "near_single_crossing", "member": mid, "directions": nd})
        td = [c.direction for c in cross if c.facility_id == target]
        if td:
            failures.append({"kind": "target_warning_crossing", "member": mid, "directions": td})
        end = tr.evaluate(tr.end_s, 0)
        for fid, geom in cons["warnings"].items():
            d = float(signed_distance(geom, end))
            if not d >= M["retreat_clearance_m"]:
                failures.append({"kind": "terminal_clearance", "member": mid, "facility": fid, "signed_m": d})
        t_us = _ticks(tr.release_s, tr.end_s, hold)
        tt = t_us / 1e6
        p = np.zeros((len(tt), 3))
        v = np.zeros((len(tt), 3))
        p[:, :2] = tr.evaluate(tt, 0)
        v[:, :2] = tr.evaluate(tt, 1)
        p[:, 2] = tr.altitude_m
        samples[mid] = {"time_us": t_us, "p": p, "v": v}
    screen = screen_detour(ctx.scene, ctx.facilities, target, samples)
    for mid in sorted(screen["member_conditions"]):
        bad = [k for k in MEMBER_CONDITIONS if not screen["member_conditions"][mid][k]]
        if bad:
            failures.append({"kind": "detour_nominal", "member": mid, "conditions": bad})
    gbad = [k for k in GROUP_CONDITIONS if not screen["group_conditions"][k]]
    if gbad:
        failures.append({"kind": "detour_nominal", "member": "group", "conditions": gbad})
    return {"passed": bool(screen["passed"] and not failures), "failures": failures, "boundaries": boundaries,
            "nominal_members": {m: {"conditions": screen["member_conditions"][m], "counts": screen["member_facts"][m]}
                                for m in sorted(samples)},
            "nominal_group": {"conditions": screen["group_conditions"], "facts": screen["group_facts"]},
            "optimized_nominal_screen": screen}
