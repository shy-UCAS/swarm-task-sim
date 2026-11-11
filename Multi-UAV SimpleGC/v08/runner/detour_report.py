"""V8-21 迂回：独立运行/保存、保留 P0、检查点、相位与作业段 Fréchet、只骨架批次、原始距离场预建与落盘独立复核
（指令 2.4、4.4–4.6、5–7；裁定 1、4、5）。

复用 JM.run_attempts、JM.attempt_chain、公共 key/metadata 与调度；不走会强读冻结 verdict 的 JM._retained_p0。
合同内只写确定性载荷；计时、traceback、缓存统计只进合同目录外的 telemetry/records。
"""
import json
import math
import time
import traceback
from fractions import Fraction
from pathlib import Path

import numpy as np

SCOPE = "detour_near_entry_to_last_exit_v21"
SKELETON_ALL = tuple(f"o{o:02d}_d{d}" for o in range(1, 41) for d in range(5))
PRIORS_FOR_RETREAT = ("abreast", "echelon", "loose")


# ================================================================ 检查点（指令 5、6、7.1；裁定 5）

def _median(xs):
    v = sorted(float(x) for x in xs)
    n = len(v)
    if not n:
        return None
    return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])


def _size_band(n):
    n = int(n)
    return "1-4" if n <= 4 else ("5-8" if n <= 8 else "9-12")


def skeleton_checkpoint(records, *, wall_s, expected_count=200):
    """严格不等式：成功率 < 90%；任一非空人数档落后总体 > 10 个百分点；成功合同获胜序号中位数 > 3；
    退让比例 > 20%（裁定 5 分母：骨架成功、多机、倾向横排/梯形/松散）；墙钟 > 1800 s。缺/重复记录、异常、未知为未完成。"""
    from ..motion.formation import mapped_start
    rows = list(records)
    ids = [r.get("contract_id") for r in rows]
    complete = len(rows) == expected_count and not any(r.get("error") or r.get("exceptions") or r.get("incomplete")
                                                     for r in rows)
    if any(i is not None for i in ids):
        complete = complete and len(set(ids)) == len(ids)
    if not complete:
        return {"complete": False, "passed": False, "triggered": ["incomplete"], "metrics": None}
    n = len(rows)
    succ = [r for r in rows if r["success"]]
    rate = Fraction(len(succ), n)
    trig = []
    if rate < Fraction(9, 10):
        trig.append("success_rate")
    bands = {}
    for r in rows:
        bands.setdefault(_size_band(r["group_size"]), []).append(bool(r["success"]))
    gaps = {k: {"n": len(v), "success": sum(v), "rate": float(Fraction(sum(v), len(v))),
                "gap_pp": float((rate - Fraction(sum(v), len(v))) * 100)} for k, v in sorted(bands.items())}
    if any(rate - Fraction(sum(v), len(v)) > Fraction(1, 10) for v in bands.values()):
        trig.append("size_band_gap")
    med = _median(r["attempts"] for r in succ)
    if med is not None and med > 3:
        trig.append("attempt_median")
    elig = [r for r in rows if r["group_size"] > 1 and r["formation_prior"] in PRIORS_FOR_RETREAT]
    elig_s = [r for r in elig if r["success"]]
    retreated = [r for r in elig_s if (r.get("formation") or {}).get("realized") != mapped_start(r["formation_prior"])]
    ratio = Fraction(len(retreated), len(elig_s)) if elig_s else None
    if ratio is not None and ratio > Fraction(1, 5):
        trig.append("retreat_ratio")
    if float(wall_s) > 1800.0:
        trig.append("wall")
    metrics = {"contracts": n, "successes": len(succ), "success_rate": float(rate), "size_bands": gaps,
               "success_attempt_median": med, "retreat_eligible_success": len(elig_s),
               "retreat_eligible_total": len(elig), "retreated": len(retreated),
               "retreat_ratio": None if ratio is None else float(ratio),
               "failed_without_realized": sum(1 for r in elig if not r["success"]), "wall_s": float(wall_s),
               "excluded_from_rate": []}
    return {"complete": True, "passed": not trig, "triggered": trig, "metrics": metrics}


def quick_checkpoint(records, *, expected_count=20):
    """快批：成功 < 16/20；成功合同进入优化后失败中位数 > 0；每合同优化耗时中位数 > 60 s（未进入=0，缺计时=未完成）；
    保留 P0 违规 > 0（只引用 0.4 第二条）。"""
    rows = list(records)
    complete = len(rows) == expected_count and not any(r.get("error") or r.get("incomplete") for r in rows)
    succ = [r for r in rows if r.get("success")]
    post = [r.get("post_optimization_failures") for r in succ]
    opt = [r.get("optimization_s") for r in rows]
    complete = complete and not any(p is None for p in post) and not any(o is None for o in opt)
    complete = complete and not any(r.get("unknown_attempts") for r in rows)
    if not complete:
        return {"complete": False, "passed": False, "triggered": ["incomplete"], "metrics": {"contracts": len(rows)}}
    trig = []
    if len(succ) < 16:
        trig.append("success_rate")
    pm = _median(post)
    if pm is not None and pm > 0:
        trig.append("post_optimization_failures")
    om = _median(opt)
    if om is not None and om > 60.0:
        trig.append("optimization_time")
    bad = [r["contract_id"] for r in succ if not r.get("retained_p0_ok")]
    if bad:
        trig.append("retained_p0")
    return {"complete": True, "passed": not trig, "triggered": trig,
            "metrics": {"contracts": len(rows), "successes": len(succ), "post_optimization_failures_median": pm,
                        "optimization_s_median": om, "retained_p0_violations": bad, "excluded_from_rate": []}}


def full_checkpoint(records, frechet_blocks):
    """全量：成功率 < 80%；设施数/初速/人数任一非空档落后 > 20 个百分点；成功合同 post 失败中位数 > 0；
    合并归一 Fréchet 中位数 < 1（0 对为 N/A）。等号不触发。"""
    from . import joint_report as JR
    rows = list(records)
    n = len(rows)
    if not n:
        return {"triggered": ["incomplete"], "metrics": {}}
    rate = Fraction(sum(bool(r["success"]) for r in rows), n)
    trig = []
    if rate < Fraction(80, 100):
        trig.append("success_rate")
    metrics = {"contracts": n, "success_rate": float(rate)}
    for name, key in (("facility_gap", lambda r: int(r["facility_count"])),
                      ("speed_gap", lambda r: JR.speed_bin(r["initial_speed_m_s"])),
                      ("group_gap", lambda r: JR.group_bin(r["group_size"]))):
        bins = {}
        for r in rows:
            bins.setdefault(key(r), []).append(bool(r["success"]))
        metrics[name] = {str(k): {"n": len(v), "rate": float(Fraction(sum(v), len(v)))} for k, v in sorted(bins.items())}
        if any(rate - Fraction(sum(v), len(v)) > Fraction(20, 100) for v in bins.values()):
            trig.append(name)
    succ = [r for r in rows if r["success"]]
    post = [r.get("post_optimization_failures") for r in succ]
    metrics["post_optimization_failures_median"] = None if any(p is None for p in post) else _median(post)
    if metrics["post_optimization_failures_median"] is not None and metrics["post_optimization_failures_median"] > 0:
        trig.append("post_optimization_failures")
    fr = JR.pooled_frechet(frechet_blocks)
    metrics["frechet_pooled_median"] = fr
    metrics["frechet_pairs"] = sum(len(b["distances_m"]) for b in frechet_blocks)
    if fr is not None and fr < 1.0:
        trig.append("frechet")
    metrics["excluded_from_rate"] = []
    return {"triggered": trig, "metrics": metrics}


# ================================================================ attempt 摘要与结果块

def _plan_draw(plan):
    if plan is None:
        return None
    if plan.failure is None:
        return (plan.proposal or {}).get("draw")
    return (plan.failure.witness or {}).get("draw")


def _plan_witness(w):
    from ..runner.monitoring import jsonable
    if not isinstance(w, dict):
        return None
    keep = ("stage", "subreason", "shape_audit_failed", "need_span_deg", "member", "constraint", "margin_m",
            "chord_index", "lp_status", "near_directions", "target_directions", "facility", "formation_steps", "draw",
            "band", "lp", "end_geometry", "exact_curvature", "intervals", "violation", "lane_sweep")
    return jsonable({k: w[k] for k in keep if k in w})


def attempt_summary(rec, key):
    """确定性 attempt 记录（timing/traceback 另放，保存前剔除）。"""
    from ..runner.monitoring import jsonable
    plan = rec.get("plan")
    stage = rec["stage"]
    s = {"attempt": key.attempt, "ok": bool(rec["ok"]), "stage": stage, "code": rec.get("code"),
         "reason": "implementation_error" if stage == "exception" else rec.get("reason"),
         "optimization_entered": rec.get("optimization_entered"),
         "skeleton_stage": None, "shape_audit_failed": False, "feasible_set": rec.get("feasible_set"),
         "witness": None, "draw": jsonable(_plan_draw(plan)), "optimize": None, "validity": None,
         "candidate_verdict": None, "measured_detour": None, "timing": rec.get("timing") or {}}
    if stage == "skeleton":
        w = rec.get("witness") if isinstance(rec.get("witness"), dict) else {}
        s["skeleton_stage"] = w.get("stage", rec.get("feasible_set"))
        s["shape_audit_failed"] = bool(w.get("shape_audit_failed", False))
        s["witness"] = _plan_witness(w)
    opt = rec.get("opt")
    if opt is not None:
        d = opt["solution"].diagnostics
        o = {k: jsonable(d.get(k)) for k in ("nit", "nfev", "success", "value", "terms", "max_abs_grad",
                                                "reference_deviation", "settings_sha256", "symmetry_break")}
        o["physical_failures"] = jsonable((d.get("physical") or {}).get("failures"))
        sem = opt.get("semantic")
        if sem is not None:
            o["semantic_failures"] = jsonable(sem["failures"])
            o["semantic_members"] = jsonable(sem["nominal_members"])
            o["semantic_boundaries"] = jsonable(sem["boundaries"])
            o["nominal_group"] = jsonable(sem["nominal_group"])
        s["optimize"] = o
        s["timing"] = dict(s["timing"], optimize_message=d.get("message"))
    if rec.get("validity") is not None:
        v = rec["validity"]
        s["validity"] = {"passed": v.passed, "codes": jsonable(v.codes), "min_separation_m": v.min_separation_m}
    if rec.get("candidate_verdict") is not None:
        s["candidate_verdict"] = jsonable(rec["candidate_verdict"])
    if rec.get("measured_detour") is not None:
        s["measured_detour"] = jsonable(rec["measured_detour"])
    if rec.get("traceback"):
        s["traceback"] = rec["traceback"]
    return s


def detour_formation(plan):
    f = plan.formation or {}
    return {"prior": f.get("prior"), "start": f.get("start"), "realized": f.get("realized"),
            "mapped_from_loose": f.get("mapped_from_loose"), "retreated": f.get("realized") != f.get("start"),
            "lateral_step_m": f.get("lateral_step_m"), "spacing_m": None, "order": f.get("order"),
            "offsets": f.get("offsets"), "steps": (plan.witnesses or {}).get("formation_steps")}


MEMBER_KEYS = ("near_entry_count", "near_exit_count", "first_near_entry_us", "last_near_exit_us", "starts_in_band",
               "ends_in_band", "max_span_deg", "best_net_deg", "all_runs", "min_target_warning_distance_m",
               "max_target_layer", "max_other_layer", "terminal_warning_distances_m")


def detour_block(plan, verdict, spacing_m):
    from ..runner.monitoring import jsonable
    form = detour_formation(plan)
    form["spacing_m"] = float(spacing_m)
    return jsonable({"candidate": plan.proposal["candidate"], "draw": plan.proposal["draw"], "formation": form,
                     "members": {m: {k: f[k] for k in MEMBER_KEYS} for m, f in sorted(verdict["member_facts"].items())},
                     "other_facility_sweep_deg": verdict["group_facts"]["other_facility_sweep_deg"]})


def retained_detour_p0(res):
    """独立保留 P0：非空成员集一致、candidate.passed、validity.passed、实测进入均为 1、目标层 0、时间连续。"""
    tracks, release = res.get("tracks") or {}, res.get("release_us") or {}
    cv, meas, valid = res.get("candidate_verdict"), res.get("measured_detour"), res.get("validity")
    if not tracks or set(tracks) != set(release) or cv is None or meas is None or valid is None:
        return False
    if set(cv["member_conditions"]) != set(tracks) or set(meas["members"]) != set(tracks):
        return False
    if not (cv["passed"] and valid.passed and meas["all_single"]):
        return False
    if not all(c["target_layer_zero"] for c in cv["member_conditions"].values()):
        return False
    for tr in tracks.values():
        d = np.diff(np.asarray(tr.tau_us, np.int64))
        if len(d) and not np.all(d == 100_000):
            return False
    return True


# ================================================================ 相位（指令 7.3）

PHASES = ("ingress", "near_band", "withdrawal")


def _member_times(res, mid):
    nom = res["opt"]["maps"][mid]["nominal"]
    mm = res["plan"].witnesses["member_map_detour"][mid]
    at = lambda s: float(np.interp(s, nom.curve.s, nom.t_nodes)) + float(nom.release_s)   # noqa: E731
    return (float(nom.release_s), at(mm["near_entry_s"]), at(mm["near_exit_s"]),
            float(nom.release_s) + float(nom.travel_s)), at


def phase_durations(res):
    from ..config import load_config
    sim = load_config("sim").values
    out = {}
    turns = res["plan"].witnesses["turn_ranges"]
    for mid in sorted(res["plan"].members):
        times, at = _member_times(res, mid)
        vals = np.diff(times)
        mm = res["plan"].witnesses["member_map_detour"][mid]
        a, b = mm["near_entry_s"], mm["near_exit_s"]
        fillet = arc = 0.0
        for kind, sa, sb, _ in turns[mid]:
            lo, hi = max(a, sa), min(b, sb)
            if hi > lo:
                dt = at(hi) - at(lo)
                if kind == "detour_arc":
                    arc += dt
                else:
                    fillet += dt
        delay = float(res["plan"].members[mid].release_delay_s)
        d = {p + "_s": float(v) for p, v in zip(PHASES, vals)}
        d.update(near_band_line_s=float(vals[1] - fillet - arc), near_band_fillet_s=float(fillet),
                 near_band_arc_s=float(arc), travel_s=float(times[-1] - times[0]), release_s=float(times[0]),
                 release_delay_s=delay, closure_residual_s=float(sum(vals) - (times[-1] - times[0])),
                 pre_release_hold_s=float(sim["initial_settle_s"]), terminal_hold_s=float(sim["terminal_hold_s"]),
                 release_quantization_s=float(times[0] - sim["initial_settle_s"] - delay))
        out[mid] = d
    return out


def phase_diagnostics(res):
    from ..diagnostics.monitoring_skeleton import phase_metrics
    from ..motion.skeleton import NominalPVA
    facts = res["candidate_verdict"]["member_facts"]
    out = {}
    for mid in sorted(res["plan"].members):
        nom = res["opt"]["maps"][mid]["nominal"]
        times, _ = _member_times(res, mid)
        tr = res["tracks"][mid]
        tau = np.asarray(tr.tau_us) / 1e6
        mask = (tau >= times[0]) & (tau <= times[-1])
        tt = tau[mask]
        rp, rv, _ = NominalPVA(nom)(tt)
        station = np.interp(tt - nom.release_s, nom.t_nodes, nom.curve.s)
        delta = np.diff(nom.curve.xy, axis=0)
        tangent = delta / np.linalg.norm(delta, axis=1)[:, None]
        ix = np.clip(np.searchsorted(nom.curve.s, station, side="right") - 1, 0, len(tangent) - 1)
        opt = res["opt"]["solution"].references[mid]
        bounds = {name: (times[i], times[i + 1], i == 2) for i, name in enumerate(PHASES)}
        m = phase_metrics(tt, rp, rv, opt.evaluate(tt), opt.evaluate(tt, 1), np.asarray(tr.p)[mask, :2],
                          np.asarray(tr.v)[mask, :2], bounds, tangent[ix])
        out[mid] = {"phases": m, "nominal_times_s": [float(x) for x in times],
                    "release_offset_s": res["release_us"][mid] / 1e6 - float(nom.release_s),
                    "max_target_layer": facts[mid]["max_target_layer"],
                    "near_entry_us": facts[mid]["first_near_entry_us"], "near_exit_us": facts[mid]["last_near_exit_us"]}
    return out


# ================================================================ 作业段 Fréchet（指令 7.2）

def _window(ctx, res, after):
    from ..motion.connect import crossing_analysis
    from ..motion.skeleton import NominalPVA
    w = res["plan"].witnesses
    near_key = w["near_key"]
    from ..contract.monitoring import TaskSpec
    from ..motion.detour_geometry import detour_constraints
    near = detour_constraints(ctx, TaskSpec("task0", "detour", w["target_id"]))["near_geometry"]
    events = []
    for mid in sorted(res["plan"].members):
        nom = res["opt"]["maps"][mid]["nominal"]
        if after:
            tr = res["opt"]["solution"].references[mid]
            times = np.unique(np.r_[tr.release_s, np.arange(math.ceil(tr.release_s * 10),
                                                              math.floor(tr.end_s * 10) + 1) / 10, tr.end_s])
            xy = tr.evaluate(times, 0)
        else:
            xy = np.asarray(nom.curve.xy)
            times = np.asarray(nom.t_nodes) + nom.release_s
        _, cross = crossing_analysis(xy, {near_key: near}, near_key, band_m=ctx.params["pre_entry_warning_clearance_m"],
                                     align_m=ctx.params["alignment_length_m"])
        sel = [c for c in cross if c.facility_id == near_key]
        if [c.direction for c in sel] != ["in", "out"]:
            return None, {"na_reason": "member_not_single_near_crossing", "member": mid}
        st = np.r_[0.0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
        for c in sel:
            ev = float(np.interp(c.s_m, st, times)) if after else NominalPVA(nom).time_at_s(c.s_m)
            events.append((c.direction, ev))
    lo = min(t for d, t in events if d == "in")
    hi = max(t for d, t in events if d == "out")
    bt = [t for _, t in events]
    tt = np.unique(np.r_[lo, np.arange(math.ceil(lo * 10), math.floor(hi * 10) + 1) / 10, bt, hi])
    tt = tt[(tt >= lo) & (tt <= hi)]
    return tt, {"window_start_s": float(lo), "window_end_s": float(hi), "boundary_times_s": bt}


def group_reference_curves(ctx, group, res):
    """before = 共同绝对时刻成员名义位置均值（V20 同口径的名义中心参考）；after = before + (1/N)Σ(p_opt − p_nom)。
    窗口 = 本版本 [min_i t_in, max_i t_out]（各成员 near 唯一入/出的几何交点插值时间）；按各自几何弧长 5 m 重采样。"""
    from ..motion.skeleton import NominalPVA
    from .transit_report import FRECHET_SPACING_M, _cut_resample
    curves, info = {}, {"scope": SCOPE}
    for name, after in (("before", False), ("after", True)):
        times, meta = _window(ctx, res, after)
        if times is None:
            curves[name], info[name] = None, meta
            continue
        before, disp = [], []
        for mid in sorted(res["plan"].members):
            nom = res["opt"]["maps"][mid]["nominal"]
            ref = NominalPVA(nom)(times)[0]
            before.append(ref)
            tr = res["opt"]["solution"].references[mid]
            disp.append(tr.evaluate(np.clip(times, tr.release_s, tr.end_s), 0) - ref)
        xy = np.mean(before, axis=0)
        if after:
            xy = xy + np.mean(disp, axis=0)
        keep = np.r_[True, np.any(np.diff(xy, axis=0) != 0.0, axis=1)]
        xy = xy[keep]
        length = float(np.cumsum(np.hypot(*np.diff(xy, axis=0).T))[-1]) if len(xy) > 1 else 0.0
        if length == 0.0:
            curves[name], info[name] = None, {**meta, "na_reason": "zero_group_mean_length"}
            continue
        curves[name] = _cut_resample(xy, 0.0, length, FRECHET_SPACING_M)
        info[name] = {**meta, "length_m": length, "n_points": len(curves[name])}
    return {"before": curves["before"], "after": curves["after"], "info": info}


# ================================================================ 单合同运行与保存（指令 2.4、4.4、4.5）

def _last_formed_verdict(records):
    for a, r in reversed(list(enumerate(records))):
        if r.get("candidate_verdict") is not None:
            return r["candidate_verdict"], a
    return None, None


def run_contract(ctx, entry, draw, *, settings, branch=None, out_dir=None, should_stop=None, keep=None):
    from . import joint_monitoring as JM
    from . import joint_report as JR
    from .monitoring import jsonable
    from ..contract.monitoring import initial_states
    from ..contract.single_intent import detour_mission
    from ..motion.intents import detour as DT
    from ..sampler.common import sample_common
    from ..sampler.keys import RngKey
    mission = detour_mission(ctx, sample_common(ctx.family, int(draw)))
    group, task = mission.groups[0], mission.tasks[0]
    states = initial_states(ctx.family, group.member_ids)
    key0 = RngKey(ctx.family.family_id, int(draw), "shape", mission=0, branch=branch, group=group.group_id, segment=0)
    summaries = []
    query_telemetry = []

    def attempt(k):
        flag = {}
        try:
            rec = JM.attempt_chain(ctx, group, task, states, k, settings, entry_flag=flag)
        except Exception:
            rec = {"ok": False, "stage": "exception", "code": "implementation_error", "reason": "implementation_error",
                   "traceback": traceback.format_exc(), "timing": {},
                   "optimization_entered": flag.get("optimization_entered")}
        summaries.append(attempt_summary(rec, k))
        query_telemetry.append(DT.last_attempt_timing())
        return rec

    outcome = JM.run_attempts(key0, attempt, should_stop=should_stop)
    cnt = JR.attempt_counters(summaries)
    failure = None
    if outcome.get("incomplete"):
        failure = {"code": "incomplete_deadline", "reason": "cooperative_budget", "feasible_set": None,
                   "witness": {"attempts_done": outcome["attempts"]}}
    elif not outcome["success"]:
        stages = [{"stage": s["skeleton_stage"] if s["stage"] == "skeleton" else s["stage"]} for s in summaries]
        f = DT.final_failure(ctx, group, task, stages)
        failure = {"code": f.code, "reason": f.reason, "feasible_set": f.feasible_set, "witness": jsonable(f.witness)}
    missing = any(not s["ok"] and not isinstance(s.get("optimization_entered"), bool) for s in summaries)
    rec = {"contract_id": JM.contract_id(entry, draw, branch), "intent": "detour", "family_id": ctx.family.family_id,
           "order": int(entry["order"]), "draw_index": int(draw), "branch": branch,
           "facility_count": int(entry["facility_count"]), "vehicle_count": int(ctx.family.vehicle_count),
           "lateral_spacing_m": float(ctx.family.lateral_spacing_m), "group_id": group.group_id,
           "member_ids": sorted(group.member_ids), "group_size": len(group.member_ids), "target_id": task.target_id,
           "initial_speed_m_s": float(group.speed_profile.initial_speed_m_s), "formation_prior": group.formation_prior,
           "success": bool(outcome["success"]), "attempts": outcome["attempts"], "failure": failure,
           "attempt_log": summaries, "settings_sha256": settings.get("_sha256"), "release_us": None,
           "retained_p0_ok": False, "incomplete": bool(outcome.get("incomplete", False)),
           "post_optimization_failures": None if missing else cnt["post_optimization_failures"],
           "skeleton_failures": cnt["skeleton_failures"], "unknown_attempts": cnt["unknown_attempts"],
           "shape_audit_failed_attempts": sum(bool(s.get("shape_audit_failed")) for s in summaries),
           "optimization_s": float(sum((s["timing"] or {}).get("optimize_s", 0.0) for s in summaries)),
           "verdict_source": "detour_candidate", "candidate_verdict": None, "detour": None,
           "nominal_duration_s": None, "deviation": None, "tracking": None, "formation": None, "topology": None,
           "phase_metrics": None, "phase_durations": None}
    rec["stage_timing"] = {k: float(sum((s["timing"] or {}).get(k, 0.0) for s in summaries))
                           for k in ("skeleton_s", "optimize_s", "simulation_s", "verify_s")}
    selected = outcome["result"] if outcome["success"] else None
    if selected is not None:
        plan = selected["plan"]
        rec.update(release_us={m: int(v) for m, v in sorted(selected["release_us"].items())},
                   retained_p0_ok=bool(retained_detour_p0(selected)),
                   candidate_verdict=jsonable(selected["candidate_verdict"]),
                   detour=detour_block(plan, selected["candidate_verdict"], ctx.family.lateral_spacing_m),
                   deviation=JM.member_deviation(selected), tracking=JM.tracking_stats(selected),
                   phase_metrics=jsonable(phase_diagnostics(selected)), phase_durations=phase_durations(selected),
                   nominal_duration_s=float(plan.nominal_duration_s),
                   formation={k: plan.formation.get(k) for k in ("prior", "start", "realized", "mapped_from_loose",
                                                                  "lateral_step_m")},
                   topology={"final": "detour"})
        if keep is not None:
            keep["result"] = selected
    else:
        cv, _a = _last_formed_verdict(outcome["records"])
        rec["candidate_verdict"] = jsonable(cv)
    if out_dir is not None:
        last = outcome["records"][-1] if outcome["records"] and not outcome["success"] else None
        save_contract(Path(out_dir), rec, selected, last_failed=last, last_attempt=len(outcome["records"]) - 1,
                      query_telemetry=query_telemetry)
    rec["lp_diagnostics"] = query_diagnostics(query_telemetry)
    return rec


def _json_bytes(obj):
    from .monitoring import canonical_json
    return canonical_json(obj) + b"\n"


def save_contract(out, rec, result, last_failed=None, last_attempt=None, *, query_telemetry=None):
    from .detour_serialization import project_document
    from .monitoring import jsonable, plan_to_record

    def encoded(value, document):
        return _json_bytes(project_document(jsonable(value), document))

    contract = {k: rec[k] for k in ("contract_id", "intent", "family_id", "order", "draw_index", "branch",
                                    "facility_count", "vehicle_count", "group_id", "member_ids", "group_size",
                                    "target_id", "initial_speed_m_s", "formation_prior")}
    result_doc = {k: rec.get(k) for k in ("intent", "success", "attempts", "failure", "release_us", "settings_sha256",
                                          "retained_p0_ok", "incomplete", "post_optimization_failures",
                                          "skeleton_failures", "unknown_attempts", "shape_audit_failed_attempts",
                                          "nominal_duration_s", "deviation", "tracking", "formation", "topology",
                                          "phase_metrics", "phase_durations", "verdict_source", "candidate_verdict",
                                          "detour")}
    result_doc["attempt_log"] = [{k: v for k, v in s.items() if k not in ("timing", "traceback")}
                                 for s in rec["attempt_log"]]
    payloads = {"contract.json": encoded(contract, "contract"), "result.json": encoded(result_doc, "result")}
    if result is not None:
        prec, arrays = plan_to_record(result["plan"])
        for v in arrays.values():
            if np.asarray(v).dtype.hasobject or not np.issubdtype(np.asarray(v).dtype, np.number):
                raise ValueError("nonnumeric plan array")
        prec["arrays"] = {k: np.asarray(v).tolist() for k, v in sorted(arrays.items())}
        payloads["skeleton.json"] = encoded(prec, "skeleton")
        sol = result["opt"]["solution"]
        diag = {k: jsonable(sol.diagnostics.get(k)) for k in ("nit", "nfev", "value", "terms", "max_abs_grad",
                                                                 "reference_deviation", "symmetry_break",
                                                                 "settings_sha256", "success")}
        opt_doc = {"members": {m: {"release_s": t.release_s, "end_s": t.end_s, "altitude_m": t.altitude_m,
                                   "knots": t.knots, "controls": t.controls} for m, t in sorted(sol.references.items())},
                   "lines": jsonable(result["opt"]["lines"]), "lines_raw": jsonable(result["opt"].get("lines_raw")),
                   "diagnostics": diag,
                   "optimized_nominal_screen": jsonable(result["opt"]["semantic"]["optimized_nominal_screen"])}
        payloads["optimized.json"] = encoded(opt_doc, "optimized")
    if last_failed is not None:
        payloads["failure_witness.json"] = encoded(failure_witness(last_failed, last_attempt), "failure_witness")
    folder = out / "contracts" / rec["contract_id"]
    folder.mkdir(parents=True, exist_ok=False)
    for name, data in payloads.items():
        (folder / name).write_bytes(data)
    if result is not None:
        for mid, tr in sorted(result["tracks"].items()):
            td = folder / "tracks" / mid
            td.mkdir(parents=True, exist_ok=False)
            for name in ("tau_us", "p", "v", "a", "segment_index"):
                arr = np.ascontiguousarray(getattr(tr, name))
                if arr.dtype.hasobject or not np.issubdtype(arr.dtype, np.number):
                    raise ValueError("nonnumeric measured array")
                np.save(td / f"{name}.npy", arr, allow_pickle=False)
    tele = out / "telemetry"
    tele.mkdir(exist_ok=True)
    (tele / f"{rec['contract_id']}.json").write_bytes(_json_bytes(jsonable(
        {"timing": [s.get("timing") for s in rec["attempt_log"]], "optimization_s": rec["optimization_s"],
         "tracebacks": [s["traceback"] for s in rec["attempt_log"] if s.get("traceback")],
         "query_telemetry": query_telemetry})))


def failure_witness(last, attempt):
    from .monitoring import jsonable
    plan = last.get("plan")
    w = (plan.failure.witness or {}) if (plan is not None and plan.failure is not None) else {}
    doc = {"stage": last.get("stage") if last.get("stage") != "skeleton" else w.get("stage"),
           "reason": "implementation_error" if last.get("stage") == "exception" else last.get("reason"),
           "attempt": attempt, "draw": _plan_draw(plan),
           "member": w.get("member"), "constraint": w.get("constraint"), "margin_m": w.get("margin_m"),
           "chord_index": w.get("chord_index"), "intervals": w.get("intervals"), "lp_status": w.get("lp_status"),
           "exact_curvature": w.get("exact_curvature"), "physical_failures": None, "semantic_failures": None,
           "candidate_failures": None, "measured_detour": last.get("measured_detour")}
    opt = last.get("opt")
    if opt is not None:
        doc["physical_failures"] = (opt["solution"].diagnostics.get("physical") or {}).get("failures")
        if opt.get("semantic") is not None:
            doc["semantic_failures"] = opt["semantic"]["failures"]
    if last.get("candidate_verdict") is not None:
        doc["candidate_failures"] = last["candidate_verdict"]["failures"]
    return jsonable(doc)


# ================================================================ 只骨架（指令 5）

def run_skeleton_contract(ctx, entry, draw, *, out_dir=None):
    from . import joint_monitoring as JM
    from .detour_serialization import project_document
    from .monitoring import jsonable, plan_to_record
    from ..contract.monitoring import initial_states
    from ..contract.single_intent import detour_mission
    from ..motion.intents import detour as DT
    from ..sampler.common import sample_common
    from ..sampler.keys import RngKey
    started = time.perf_counter()
    mission = detour_mission(ctx, sample_common(ctx.family, int(draw)))
    group, task = mission.groups[0], mission.tasks[0]
    states = initial_states(ctx.family, group.member_ids)
    key = RngKey(ctx.family.family_id, int(draw), "shape", mission=0, branch=None, group=group.group_id, segment=0)
    logs, tele = [], []

    def attempt(k):
        plan = DT.propose_and_build(ctx, group, task, states, k)
        tele.append(DT.last_attempt_timing())
        f = plan.failure
        w = (f.witness or {}) if f is not None else {}
        stage = "skeleton_ok" if f is None else w.get("stage", f.feasible_set)
        row = {"attempt": k.attempt, "ok": f is None, "stage": stage, "code": None if f is None else f.code,
               "reason": None if f is None else f.reason, "feasible_set": None if f is None else f.feasible_set,
               "shape_audit_failed": bool(w.get("shape_audit_failed", False)), "subreason": w.get("subreason"),
               "draw": _plan_draw(plan),
               "formation_steps": (plan.witnesses or {}).get("formation_steps") if f is None else w.get("formation_steps"),
               "witness": _plan_witness(w) if f is not None else None,
               "bone_nominal_screen": (plan.witnesses or {}).get("bone_nominal_screen") if f is None else None}
        logs.append(jsonable(row))
        return {"ok": f is None, "stage": stage, "plan": plan}

    exceptions = 0
    try:
        outcome = JM.run_attempts(key, attempt)
    except Exception:
        exceptions = 1
        outcome = {"success": False, "attempts": len(logs), "records": [], "result": None,
                   "traceback": traceback.format_exc()}
    failure = None
    if not outcome["success"] and not exceptions:
        f = DT.final_failure(ctx, group, task, [{"stage": r["stage"]} for r in logs])
        failure = {"code": f.code, "reason": f.reason, "feasible_set": f.feasible_set, "witness": jsonable(f.witness)}
    rec = {"contract_id": JM.contract_id(entry, draw), "intent": "detour", "family_id": ctx.family.family_id,
           "order": int(entry["order"]), "draw_index": int(draw), "branch": None,
           "facility_count": int(entry["facility_count"]), "vehicle_count": int(ctx.family.vehicle_count),
           "lateral_spacing_m": float(ctx.family.lateral_spacing_m), "group_id": group.group_id,
           "member_ids": sorted(group.member_ids), "group_size": len(group.member_ids), "target_id": task.target_id,
           "initial_speed_m_s": float(group.speed_profile.initial_speed_m_s), "formation_prior": group.formation_prior,
           "success": bool(outcome["success"]), "attempts": int(outcome["attempts"]), "failure": failure,
           "attempt_log": logs, "shape_audit_failed_attempts": sum(r["shape_audit_failed"] for r in logs),
           "exceptions": exceptions, "verdict_source": "detour_candidate", "formation": None, "topology": None,
           "detour_formation": None, "bone_nominal_screen": None, "nominal_duration_s": None}
    if outcome.get("traceback"):
        rec["traceback"] = outcome["traceback"]
    if outcome["success"]:
        plan = outcome["result"]["plan"]
        df = detour_formation(plan)
        df["spacing_m"] = float(ctx.family.lateral_spacing_m)
        rec.update(formation={k: plan.formation.get(k) for k in ("prior", "start", "realized", "mapped_from_loose",
                                                                  "retreat_chain", "order", "offsets",
                                                                  "lateral_step_m")},
                   topology={"final": "detour"}, detour_formation=jsonable(df),
                   bone_nominal_screen=jsonable(plan.witnesses["bone_nominal_screen"]),
                   nominal_duration_s=float(plan.nominal_duration_s))
    rec["lp_diagnostics"] = query_diagnostics(tele)
    if out_dir is not None:
        folder = Path(out_dir) / "contracts" / rec["contract_id"]
        folder.mkdir(parents=True, exist_ok=False)
        contract = {k: rec[k] for k in ("contract_id", "intent", "family_id", "order", "draw_index", "branch",
                                        "facility_count", "vehicle_count", "group_id", "member_ids", "group_size",
                                        "target_id", "initial_speed_m_s", "formation_prior")}
        res = {k: rec[k] for k in ("intent", "success", "attempts", "failure", "attempt_log",
                                   "shape_audit_failed_attempts", "exceptions", "verdict_source", "formation",
                                   "topology", "detour_formation", "bone_nominal_screen", "nominal_duration_s")}
        payloads = {"contract.json": project_document(jsonable(contract), "contract"),
                    "result.json": project_document(jsonable(res), "skeleton_result")}
        if outcome["success"]:
            prec, arrays = plan_to_record(outcome["result"]["plan"])
            prec["arrays"] = {k: np.asarray(v).tolist() for k, v in sorted(arrays.items())}
            payloads["skeleton.json"] = project_document(jsonable(prec), "skeleton")
        for name, value in payloads.items():
            (folder / name).write_bytes(_json_bytes(value))
        td = Path(out_dir) / "telemetry"
        td.mkdir(exist_ok=True)
        (td / f"{rec['contract_id']}.json").write_bytes(_json_bytes(jsonable(
            {"attempts": tele, "wall_s": time.perf_counter() - started, "traceback": rec.get("traceback")})))
    return rec


def _skeleton_worker(task):
    from ..scene.context import load_context
    entry, draw, data_root, cache_dir, out_dir = task
    started = time.perf_counter()
    try:
        ctxs = globals().setdefault("_DETOUR_SKELETON_CONTEXTS", {})
        if entry["order"] not in ctxs:
            while len(ctxs) >= 3:
                ctxs.pop(next(iter(ctxs)))
            ctxs[entry["order"]] = load_context(entry, data_root=Path(data_root), cache_dir=Path(cache_dir))
        rec = run_skeleton_contract(ctxs[entry["order"]], entry, draw, out_dir=Path(out_dir))
        return {**rec, "wall_s": time.perf_counter() - started}
    except Exception as exc:
        return {"contract_id": f"o{int(entry['order']):02d}_d{draw}", "order": int(entry["order"]), "draw_index": draw,
                "success": False, "attempts": None, "error": repr(exc), "traceback": traceback.format_exc()}


def run_skeleton_batch(entries, *, data_root, cache_dir, out_dir, workers, sizes, log=print):
    from .area_search_report import _bounded_dispatch, _durable_json
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=False)
    keys = [(e, d) for e in entries for d in range(5)]
    keys.sort(key=lambda it: (-sizes[f"{int(it[0]['order'])}:{it[1]}"] * float(it[0]["map_side_m"]),
                              int(it[0]["order"]), it[1]))
    _durable_json(out / "dispatch_order.json", [{"order": int(e["order"]), "draw": d} for e, d in keys])
    tasks = [(e, d, str(data_root), str(cache_dir), str(out)) for e, d in keys]
    rows, timing = _bounded_dispatch(_skeleton_worker, tasks, workers=workers, out=out, wall_limit=1800.0, log=log)
    rows.sort(key=lambda r: r["contract_id"])
    _durable_json(out / "records.json", rows)
    chk = skeleton_checkpoint(rows, wall_s=timing["wall_s"])
    if timing["hard_stop"] and "wall" not in chk["triggered"]:
        chk["triggered"].append("wall")
        chk["passed"] = False
    summary = {"intent": "detour", "stage": "skeleton", "workers": workers, "expected_count": 200,
               "completed": len(rows), "dispatch_wall_s": timing["wall_s"], "hard_stop": timing["hard_stop"],
               "checkpoint": chk, "diagnostics": skeleton_diagnostics(rows), "p0": []}
    _durable_json(out / "summary.json", summary)
    return summary


def skeleton_diagnostics(rows):
    """σ/Σ/β/起始方位/K/倾向与实际队形/可用弧分布；band/shape/route 按已完成尝试与按合同两列；sweep_window 比例。"""
    attempts = [a for r in rows for a in (r.get("attempt_log") or [])]
    stages = ("detour_band", "detour_shape", "detour_route")
    by_attempt = {s: sum(1 for a in attempts if a.get("stage") == s) for s in stages}
    by_contract = {s: sum(1 for r in rows if any(a.get("stage") == s for a in (r.get("attempt_log") or []))) for s in stages}
    sub = {}
    for a in attempts:
        if not a.get("ok"):
            k = f"{a.get('stage')}:{a.get('subreason')}"
            sub[k] = sub.get(k, 0) + 1
    win = [a for r in rows if r.get("success") for a in (r.get("attempt_log") or []) if a.get("ok")]
    dr = [a.get("draw") or {} for a in win]

    def q(vals):
        vals = [float(v) for v in vals if v is not None]
        return None if not vals else [float(x) for x in np.quantile(vals, [0, .1, .5, .9, 1.0])]
    contrib = [d.get("entry_exit_contribution_deg") for d in dr]
    avail = [max((s.get("max_arc_deg") or -1) for s in (a.get("formation_steps") or [{}])) for a in win]
    forms = {}
    for r in rows:
        if r.get("success"):
            k = f"{r['formation_prior']}->{(r.get('formation') or {}).get('realized')}"
            forms[k] = forms.get(k, 0) + 1
    query = [r.get("lp_diagnostics") or {} for r in rows]
    return {"attempts_completed": len(attempts), "failures_by_attempt": by_attempt, "failures_by_contract": by_contract,
            "lp_calls": sum(q.get("lp_calls", 0) for q in query),
            "unknown_status_count": sum(q.get("unknown_status_count", 0) for q in query),
            "unknown_rejected_probe_contracts": sum(q.get("unknown_rejected_probe", False) for q in query),
            "rescued_parent_queries": sum(q.get("rescued_parent_queries", 0) for q in query),
            "rescued_periodic_queries": sum(q.get("rescued_periodic_queries", 0) for q in query),
            "selected_lp_span_deg_q": q([v for z in query for v in z.get("selected_lp_spans", [])]),
            "selected_geometric_span_deg_q": q([v for z in query for v in z.get("selected_geometric_spans", [])]),
            "failure_subreasons": dict(sorted(sub.items())),
            "sweep_window_rate_of_attempts": (sub.get("detour_route:sweep_window", 0) / len(attempts)) if attempts else None,
            "sigma_counts": {str(s): sum(1 for d in dr if d.get("sigma") == s) for s in (-1, 1)},
            "Sigma_deg_q": q(d.get("sigma_deg") for d in dr), "beta_in_deg_q": q(d.get("beta_in_deg") for d in dr),
            "beta_out_deg_q": q(d.get("beta_out_deg") for d in dr),
            "start_phi_deg_q": q(None if d.get("start_phi_rad") is None else math.degrees(d["start_phi_rad"]) for d in dr),
            "K_counts": {str(k): sum(1 for d in dr if d.get("K") == k) for k in range(4, 9)},
            "entry_exit_contribution_deg_q": q(contrib), "available_arc_deg_q": q(avail),
            "prior_to_realized": dict(sorted(forms.items())),
            "bone_nominal_screen_failed_contracts": sum(1 for r in rows if r.get("success") and
                                                        not (r.get("bone_nominal_screen") or {}).get("passed", False)),
            "win_attempt_q": q(r.get("attempts") for r in rows if r.get("success"))}


def query_diagnostics(telemetry):
    """Contract-external statistics; cache hits do not re-count solver work or statuses.

    unknown_rejected_probe marks possible influence, not a proved counterfactual outcome:
    a rejected formation query included unknown statuses. Geometry/infeasibility may also
    have contributed. It is diagnostic only, as required by repair ruling 1.
    """
    probes = [p for t in telemetry for p in t.get("lp_query", [])]
    cold = [p for p in probes if not p["cache_hit"]]
    return {"lp_calls": sum(p["lp_calls"] for p in cold),
            "unknown_status_count": sum(p["unknown_status_count"] for p in cold),
            "unknown_rejected_probe": any(not p["feasible"] and p["unknown_status_count"] for p in probes),
            "rescued_parent_queries": sum(int(p["rescued_parents"]) for p in cold),
            "rescued_periodic_queries": sum(int(p["rescued_periodic"]) for p in cold),
            "selected_lp_spans": [t["selected_arc"]["selected_lp_max_span_deg"] for t in telemetry if "selected_arc" in t],
            "selected_geometric_spans": [t["selected_arc"]["selected_geometric_max_span_deg"]
                                         for t in telemetry if "selected_arc" in t]}


# ================================================================ 原始距离场预建（单族单进程，worker 只读）

def _prewarm_family(task):
    from ..contract.monitoring import TaskSpec
    from ..contract.single_intent import detour_mission
    from ..motion.detour_geometry import DetourRouteView, band_for, detour_constraints
    from ..motion.layer_limits import constraints_identity
    from ..sampler.common import sample_common
    from ..scene.context import load_context
    entry, draws, data_root, cache_dir = task
    started = time.perf_counter()
    try:
        ctx = load_context(entry, data_root=Path(data_root), cache_dir=Path(cache_dir))
        sizes, targets = {}, []
        for d in draws:
            m = detour_mission(ctx, sample_common(ctx.family, int(d)))
            sizes[f"{int(entry['order'])}:{d}"] = len(m.groups[0].member_ids)
            if m.tasks[0].target_id not in targets:
                targets.append(m.tasks[0].target_id)
        for t in targets:
            cons = detour_constraints(ctx, TaskSpec("task0", "detour", t))
            band_for(ctx, cons)
            DetourRouteView(ctx, cons, {})
            base = list(cons["base"])
            ctx.field(("route", "detour", constraints_identity(base)), base)
        return {"order": int(entry["order"]), "family_id": entry["family_id"], "sizes": sizes, "targets": targets,
                "raw_cache": ctx.cache_stats(), "wall_s": time.perf_counter() - started}
    except Exception as exc:
        return {"order": int(entry["order"]), "error": repr(exc), "traceback": traceback.format_exc(),
                "wall_s": time.perf_counter() - started}


def prewarm_all(entries, *, data_root, cache_dir, workers, out_dir=None, draws=range(5), log=print):
    """只建 detour 所需原始距离场（近距离带等新几何）并登记人数；不预建任何形状/路径组合。"""
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor
    t0 = time.time()
    tasks = [(e, list(draws), str(data_root), str(cache_dir)) for e in sorted(entries, key=lambda e: e["order"])]
    rows = []
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
        for r in ex.map(_prewarm_family, tasks):
            rows.append(r)
            log(f"预建 o{r['order']:02d}: {r.get('wall_s', 0):.0f}s err={r.get('error')}", flush=True)
    sizes = {}
    for r in rows:
        sizes.update(r.get("sizes") or {})
    doc = {"intent": "detour", "families": len(rows), "wall_s": time.time() - t0, "per_family": rows,
           "group_size": sizes, "complete": len(sizes) == len(entries) * len(list(draws)) and not any(r.get("error") for r in rows),
           "scope": "raw_distance_fields_only"}
    if out_dir is not None:
        from .monitoring import write_json
        write_json(Path(out_dir) / "prewarm.json", doc, indent=1)
    return doc


# ================================================================ 落盘独立复核（指令 4.5 末段）

def independent_sweep(t, xy, warning, center, D):
    """独立逐帧状态机（不导入 detour_numeric）：返回 sd、各区间 span、最佳 span/net、入/出时刻。"""
    from task_v07.geometry import geometry_facts
    sd = np.asarray(geometry_facts(warning, xy)["signed_distance_m"], float)
    angle = np.unwrap(np.arctan2(xy[:, 1] - center[1], xy[:, 0] - center[0]))
    active, begin, iv, entries, exits = False, None, [], [], []
    for k in range(len(t)):
        inside = bool(0 < sd[k] <= D)
        if inside and not active:
            begin = k
            entries.append(int(t[k]))
        if active and not inside:
            a = angle[begin:k]
            iv.append((float(np.degrees(a.max() - a.min())), float(np.degrees(abs(a[-1] - a[0])))))
            exits.append(int(t[k]))
        active = inside
    if active:
        a = angle[begin:]
        iv.append((float(np.degrees(a.max() - a.min())), float(np.degrees(abs(a[-1] - a[0])))))
    best = max(range(len(iv)), key=lambda j: iv[j][0]) if iv else None
    return {"sd": sd, "spans": [x[0] for x in iv], "span": 0.0 if best is None else iv[best][0],
            "net": 0.0 if best is None else iv[best][1], "entries": entries, "exits": exits}


def verify_saved_outputs(root, entries, data_root, cache, candidate_path):
    """从磁盘重建 tracks/release/场景与候选配置，独立调用冻结 check_validity/geometry_facts/dwell/revisit，并以独立
    扫角状态机复算全部成员/非目标指标与事件，逐项对照 result/candidate_verdict。不调用候选函数自证。"""
    import hashlib
    from task_v07.criteria import load_criteria
    from task_v07.detectors import dwell, revisit
    from task_v07.geometry import geometry_facts
    from ..criteria.validity import check_validity, visible_track
    from ..scene.context import load_context
    from ..scene.exact import center_of_geometry
    from ..sim.types import MemberTrack
    from .detour_serialization import project_document
    root = Path(root)
    raw = json.loads(Path(candidate_path).read_text(encoding="utf-8"))
    Cv = {k: v["value"] for k, v in raw["parameters"].items()}
    csha = hashlib.sha256(Path(candidate_path).read_bytes()).hexdigest()
    retreat = 50.0
    cfg = load_criteria()
    by = {e["family_id"]: e for e in entries}
    rows = json.loads((root / "records.json").read_text(encoding="utf-8"))
    results, errors = [], []
    ctxs = {}
    for row in rows:
        cid = row["contract_id"]
        folder = root / "contracts" / cid
        for name, doc in (("contract.json", "contract"), ("result.json", "result"), ("skeleton.json", "skeleton"),
                          ("optimized.json", "optimized"), ("failure_witness.json", "failure_witness")):
            p = folder / name
            if p.is_file():
                try:
                    project_document(json.loads(p.read_text(encoding="utf-8")), doc)
                except ValueError as exc:
                    errors.append({"contract_id": cid, "reason": f"schema:{name}:{exc}"})
        saved = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        con = json.loads((folder / "contract.json").read_text(encoding="utf-8"))
        if saved["verdict_source"] != "detour_candidate" or saved["success"] != row["success"]:
            errors.append({"contract_id": cid, "reason": "verdict_source_or_status"})
        if not saved["success"]:
            continue
        if row["family_id"] not in ctxs:
            ctxs.clear()
            ctxs[row["family_id"]] = load_context(by[row["family_id"]], data_root=Path(data_root), cache_dir=Path(cache))
        scene = ctxs[row["family_id"]].scene
        ent = scene["entities"]
        fac = {e["id"]: e["geometry"] for e in ent if e["type"] == "facility"}
        layers = {f: {} for f in fac}
        for e in ent:
            if e["type"] == "protection_zone":
                layers[e["facility_id"]][e["layer"]] = e["geometry"]
        target, D = con["target_id"], float(Cv["near_band_width_m"])
        good, problems, per_fac, tracks = True, [], {f: [] for f in fac}, {}
        for mid in con["member_ids"]:
            arr = {k: np.load(folder / "tracks" / mid / (k + ".npy"), allow_pickle=False)
                   for k in ("tau_us", "p", "v", "a", "segment_index")}
            tr = MemberTrack(mid, arr["tau_us"], arr["p"], arr["v"], arr["a"], arr["segment_index"], ())
            tracks[mid] = tr
            keep = (tr.tau_us >= saved["release_us"][mid]) & (tr.segment_index == 0)
            t, xy, vel = tr.tau_us[keep], tr.p[keep, :2], tr.v[keep]
            if not len(t) or not np.all(np.diff(t) == 100000):
                problems.append(f"{mid}:time")
                continue
            lv = {}
            sw = {}
            for f, g in fac.items():
                level = np.zeros(len(t), np.int8)
                for nm, code in (("warning", 1), ("alert", 2), ("protected", 3)):
                    level = np.where(geometry_facts(layers[f][nm], xy)["inside"], code, level)
                lv[f] = level
                sw[f] = independent_sweep(t, xy, layers[f]["warning"], center_of_geometry(g), D)
                per_fac[f].append(sw[f]["span"])
                if int(level[0]) != 0 or int(level[-1]) != 0 or float(sw[f]["sd"][-1]) < retreat:
                    problems.append(f"{mid}:{f}:start_end")
            q = sw[target]
            if int(lv[target].max()) != 0:
                problems.append(f"{mid}:target_layer")
            if len(q["entries"]) != 1 or not q["span"] >= float(Cv["min_sweep_deg"]):
                problems.append(f"{mid}:entries_or_min_sweep")
            if not all(s < float(Cv["max_sweep_deg_exclusive"]) for s in q["spans"]):
                problems.append(f"{mid}:max_sweep")
            if not float(q["sd"][-1]) > D:
                problems.append(f"{mid}:ended_in_near")
            for f in fac:
                if f != target and int(lv[f].max()) > 1:
                    problems.append(f"{mid}:{f}:other_layer")
            ones = np.ones(len(t), bool)
            if dwell(xy, t, ones, cfg)["detected"] or revisit(xy, vel, t, lv[target], ones,
                                                              np.asarray(center_of_geometry(fac[target])), cfg)["detected"]:
                problems.append(f"{mid}:dwell_or_revisit")
            sm = saved["detour"]["members"][mid]
            exp = {"near_entry_count": len(q["entries"]), "near_exit_count": len(q["exits"]),
                   "first_near_entry_us": q["entries"][0] if q["entries"] else None,
                   "last_near_exit_us": q["exits"][-1] if q["exits"] else None}
            for k, v in exp.items():
                if sm[k] != v:
                    problems.append(f"{mid}:{k}")
            for k, v in (("max_span_deg", q["span"]), ("best_net_deg", q["net"]),
                         ("min_target_warning_distance_m", float(q["sd"].min()))):
                if abs(float(sm[k]) - v) > 1e-9:
                    problems.append(f"{mid}:{k}:{float(sm[k]) - v:.3e}")
        visible = [visible_track(tracks[m], saved["release_us"][m]) for m in sorted(tracks)]
        valid = check_validity(scene, visible)
        if not valid.passed:
            problems.append("validity")
        for f, vals in per_fac.items():
            if f != target and vals:
                gf = min(vals)
                if not gf < float(Cv["min_sweep_deg"]):
                    problems.append(f"{f}:other_sweep")
                if abs(float(saved["detour"]["other_facility_sweep_deg"][f]) - gf) > 1e-9:
                    problems.append(f"{f}:other_sweep_saved")
        if not (saved["retained_p0_ok"] and saved["candidate_verdict"]["passed"]):
            problems.append("saved_flags")
        if saved["detour"]["candidate"]["criteria_sha256"] != csha:
            problems.append("criteria_sha")
        good = not problems
        results.append({"contract_id": cid, "passed": good, "problems": problems,
                        "min_separation_m": valid.min_separation_m})
        if not good:
            errors.append({"contract_id": cid, "reason": "retained_disk_reverification_failed", "problems": problems})
    return {"passed": not errors, "all_checked": len(rows), "checked_successes": len(results), "results": results,
            "p0_violations": errors, "criteria_sha256": csha}
