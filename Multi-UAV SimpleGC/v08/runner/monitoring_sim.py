"""V8-12 第 5 部分运行器：仿真、拼接、段核验与有效性检查（指令 5.1–5.3；附录裁定 10、11）。

每个合同：第 4 部分已规划成功的计划先被复用（不重新规划）；逐成员、单进程调用 run_guided_segment，
再 stitch、verify_segments、check_validity。候选失败（仿真超时、核验不过、间距/限制区不满足）按共享的
20 次 attempt 预算从 a+1 接着重做，只变形态/连接，不动公共抽签和目标（裁定 10）。只有这些情况才停批次（P0）：
保留段违反 D.5 门禁、时间线不连续、同键复跑不一致、未捕获的异常。跟踪管只作诊断，不触发重做（裁定 11）。

本模块 import 时不读数据、不创建目录；冻结判据、sim 与 criteria 都在函数内导入，保证核心导入链不依赖 shapely。
"""
import hashlib
import json
import math
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..contract.monitoring import Failure, MemberPlan, SegmentPlan, initial_states, monitoring_mission, to_guided
from ..motion.plan import plan_segment
from ..sampler.common import sample_common
from ..sampler.keys import RngKey
from . import monitoring as M

FRAME_US = 100_000
TIMING_KEYS = ("wall_s", "sim_wall_s", "diag_wall_s", "member_wall_s", "seconds", "planned_by", "replan_wall_s")
FIELDS = ("tau_us", "p", "v", "a", "segment_index")


class P0Stop(RuntimeError):
    """批次级停止（指令 0.5、附录裁定 10）：kind 取 timeline_inconsistent / retained_gate_violation /
    rerun_mismatch / uncaught_exception / input_mismatch。"""

    def __init__(self, kind, message, detail=None):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.detail = detail


class WallClock:
    """第 5 部分的 2 小时资源边界（上层 D.9）；used_s 是此前阶段已用的墙钟，两个阶段共用一份预算。"""

    def __init__(self, budget_s, used_s=0.0):
        self.budget_s = float(budget_s)
        self.used_s = float(used_s)
        self._t0 = time.perf_counter()

    def elapsed(self):
        return self.used_s + time.perf_counter() - self._t0

    def exceeded(self):
        return self.elapsed() >= self.budget_s


@dataclass
class SegmentRun:
    status: str                       # retained / failed / interrupted
    attempts: list
    final_attempt: int | None
    plan: object | None
    tracks: dict | None
    failure: Failure | None
    chain: list = field(default_factory=list)
    wall_s: float = 0.0
    sim_wall_s: float = 0.0
    replan_wall_s: float = 0.0


# ---------------------------------------------------------------- 输入与计划重建

def contract_inputs(ctx, draw):
    """与 plan_contract 完全相同的公共抽签、任务和键（branch=None）。"""
    common = sample_common(ctx.family, draw)
    mission = monitoring_mission(ctx, common)
    group, task = mission.groups[0], mission.tasks[0]
    states = initial_states(ctx.family, group.member_ids)
    key = RngKey(ctx.family.family_id, draw, "shape", mission=0, branch=None, group=group.group_id, segment=0)
    return common, mission, group, task, states, key


def load_saved_plan(plan_dir, contract_id):
    base = Path(plan_dir) / "contracts" / contract_id
    rec = json.loads(Path(str(base) + ".json").read_text(encoding="utf-8"))
    if not rec.get("success") or "plan" not in rec:
        raise ValueError(f"{contract_id} 在第 4 部分没有成功计划")
    with np.load(str(base) + ".npz") as z:
        arrays = {k: z[k] for k in z.files}
    return rec, arrays


def plan_from_record(rec, arrays):
    """第 4 部分保存的 JSON + NPZ → SegmentPlan。不重新规划；类型与规划器产出一致（点列/断点为元组）。"""
    p = rec["plan"]
    members = {}
    for m, d in sorted(p["members"].items()):
        xy = arrays[d["curve_xy"]["npz"]]
        members[m] = MemberPlan(
            d["member_id"], int(d["segment_index"]), tuple((float(a), float(b)) for a, b in xy.tolist()),
            float(d["altitude_m"]), float(d["end_s"]), float(d["release_delay_s"]),
            tuple(tuple(float(x) for x in br) for br in d["speed_breaks"]),
            tuple(tuple(float(x) for x in st) for st in d["stops"]))
    return SegmentPlan(members=members, reference_xy=tuple(map(tuple, arrays["reference_xy"].tolist())),
                       nominal_duration_s=float(p["nominal_duration_s"]), anchors=p["anchors"],
                       repairs=tuple(p["repairs"]), failure=None, proposal=p["proposal"], formation=p["formation"],
                       topology=p["topology"], business_key=p["business_key"],
                       member_nominal_s=p["member_nominal_s"], witnesses=p["witnesses"],
                       attempt_log=tuple(rec["attempt_log"]))


def plan_digest(plan):
    """最终接受的计划的摘要：JSON（规范序列化）+ 全部数组字节。复跑比较用。"""
    rec, arrays = M.plan_to_record(plan)
    h = hashlib.sha256(M.canonical_json(rec))
    for k in sorted(arrays):
        a = np.ascontiguousarray(arrays[k])
        h.update(k.encode("utf-8"))
        h.update(a.dtype.str.encode("utf-8"))
        h.update(str(a.shape).encode("utf-8"))
        h.update(a.tobytes())
    return h.hexdigest()


# ---------------------------------------------------------------- 轨迹摘要与诊断

def _array_digest(a):
    a = np.ascontiguousarray(a)
    return [a.dtype.str, list(a.shape), hashlib.sha256(a.tobytes()).hexdigest()]


def tracks_digest(tracks):
    return {m: {f: _array_digest(getattr(tracks[m], f)) for f in FIELDS} for m in sorted(tracks)}


def _speed_xy(v):
    v = np.asarray(v, float)
    return np.hypot(v[:, 0], v[:, 1])


def tracking_diagnostic(mp, track, release_us, G, tube_m):
    """跟踪管：沿上一进度附近的局部曲线顺序投影（冻结 project，窗口 projection_window_m），不做全局最近点。
    返回 (摘要, 释放后首帧下标, 每帧进度 s, 每帧期望速度档)。"""
    from ..sim.guidance import make_curve, project

    curve = make_curve(mp.curve_xy, max_chord_m=G["max_chord_m"], max_turn_rad=G["max_turn_per_chord_rad"])
    tau = np.asarray(track.tau_us)
    lo = int(np.searchsorted(tau, int(release_us), side="left"))
    P = np.asarray(track.p, float)[lo:, :2]
    n = len(P)
    err = np.empty(n)
    sarr = np.empty(n)
    s_prev = 0.0
    window = G["projection_window_m"]
    for i in range(n):
        _, s_p, q = project(curve, P[i], s_prev, window)
        err[i] = math.hypot(P[i, 0] - q[0], P[i, 1] - q[1])
        sarr[i] = s_p
        s_prev = s_p
    br = np.asarray(mp.speed_breaks, float)
    level = br[np.searchsorted(br[:, 0], sarr, side="right") - 1, 1]
    over = np.flatnonzero(err > tube_m)
    imax = int(np.argmax(err)) if n else 0

    def at(i):
        return {"frame": int(lo + i), "tau_s": float(tau[lo + i] / 1e6), "xy": [float(P[i, 0]), float(P[i, 1])],
                "s_m": float(sarr[i]), "expected_speed_m_s": float(level[i]), "lateral_m": float(err[i])}

    by_level = {}
    for lv in np.unique(level):
        sel = level == lv
        by_level[repr(float(lv))] = {"frames": int(sel.sum()), "over_frames": int((err[sel] > tube_m).sum()),
                                     "max_m": float(err[sel].max())}
    out = {"frames": n, "tube_m": float(tube_m), "max_m": float(err.max()) if n else None,
           "p95_m": float(np.quantile(err, 0.95, method="linear")) if n else None, "over_frames": int(len(over)),
           "first_over": at(int(over[0])) if len(over) else None, "max_at": at(imax) if n else None,
           "over_by_expected_speed": by_level, "curve_length_m": curve.length,
           "end_progress_m": float(sarr[-1]) if n else None}
    return out, lo, sarr, level, curve


def speed_diagnostic(mp, track, lo, sarr):
    """变速冲高：每个参考变速站点到下一站点的区间内，实测水平速度超过相邻两档期望速度最大值的正差；
    另报实际速度极值与相邻帧速度差（全程与站点区间内）。"""
    v = np.asarray(track.v, float)[lo:]
    sp = _speed_xy(v)
    br = np.asarray(mp.speed_breaks, float)
    dsp = np.abs(np.diff(sp)) if len(sp) > 1 else np.zeros(0)
    dvec = np.hypot(*np.diff(v[:, :2], axis=0).T) if len(sp) > 1 else np.zeros(0)
    worst = None
    max_over = 0.0
    in_window_dsp = 0.0
    in_window_dvec = 0.0
    stations = 0
    for k in range(1, len(br)):
        s0 = br[k, 0]
        s1 = br[k + 1, 0] if k + 1 < len(br) else np.inf
        idx = np.flatnonzero((sarr >= s0) & (sarr < s1))
        if not len(idx):
            continue
        stations += 1
        expected = float(max(br[k - 1, 1], br[k, 1]))
        over = float(sp[idx].max() - expected)
        a, b = int(idx[0]), int(idx[-1])
        if b > a:
            in_window_dsp = max(in_window_dsp, float(dsp[a:b].max()))
            in_window_dvec = max(in_window_dvec, float(dvec[a:b].max()))
        if worst is None or over > worst["over_m_s"]:
            f0 = a
            seq = sp[max(0, f0 - 10): f0 + 31]
            worst = {"station": k, "s_m": float(s0), "expected_levels_m_s": [float(br[k - 1, 1]), float(br[k, 1])],
                     "expected_max_m_s": expected, "max_measured_m_s": float(sp[idx].max()), "over_m_s": over,
                     "first_frame": int(lo + f0), "speeds_around_m_s": [float(x) for x in seq]}
        max_over = max(max_over, over)
    return {"stations": stations, "max_positive_over_m_s": max(0.0, max_over),
            "max_over_signed_m_s": None if worst is None else worst["over_m_s"], "worst": worst,
            "speed_max_m_s": float(sp.max()) if len(sp) else None,
            "speed_quantiles_m_s": None if not len(sp) else
            {q: float(np.quantile(sp, p, method="linear")) for q, p in (("p05", 0.05), ("p50", 0.5), ("p95", 0.95))},
            "adjacent_frame": {"max_abs_speed_diff_m_s": float(dsp.max()) if len(dsp) else None,
                               "max_velocity_vector_diff_m_s": float(dvec.max()) if len(dvec) else None,
                               "max_abs_speed_diff_in_station_windows_m_s": in_window_dsp,
                               "max_velocity_vector_diff_in_station_windows_m_s": in_window_dvec}}


def boundary_diagnostic(levels, planned_crossings):
    """实测 warning 边界进出次数（所有设施），与计划中的穿越次数比较；超出的部分是抖动候选。"""
    lv = np.asarray(levels)
    trans = enters = alert = 0
    for j in range(lv.shape[1]):
        w = (lv[:, j] >= 1).astype(np.int8)
        d = np.diff(w)
        trans += int(np.count_nonzero(d))
        enters += int(np.count_nonzero(d > 0))
        alert += int(np.count_nonzero(np.diff((lv[:, j] >= 2).astype(np.int8))))
    return {"warning_transitions": trans, "warning_entries": enters, "planned_crossings": int(planned_crossings),
            "excess": trans - int(planned_crossings), "alert_transitions": alert}


def dwell_detail(plan, mp, track, verdict, member, lo, sarr, curve, criteria, mon_cfg):
    """全窗口驻留拒绝的细节：检测窗口、位置、速度、半径与是否仍满足预置最小半径；称"疑似误报"，不自行宣布检测器错。"""
    win = verdict.windows[member]
    d = win.dwell_anywhere
    if not d["detected"]:
        return None
    rules = criteria["detectors"]["dwell"]
    size = round(rules["window_s"] * 10) + 1
    w_lo = verdict.window_frames[member][0]
    i0 = w_lo + int(d["frame_index"])
    seg = np.asarray(track.p, float)[i0:i0 + size, :2]
    center = seg.mean(axis=0)
    dev = float(np.hypot(*(seg - center).T).max())
    spd = _speed_xy(np.asarray(track.v, float)[i0:i0 + size])
    j0, j1 = max(0, i0 - lo), min(len(sarr) - 1, i0 + size - 1 - lo)
    s_a, s_b = float(sarr[j0]), float(sarr[j1])
    k0 = int(np.searchsorted(curve.s, s_a, side="left"))
    k1 = int(np.searchsorted(curve.s, s_b, side="right"))
    kmax = float(np.max(np.abs(curve.kappa[k0:max(k1, k0 + 1)])))
    radius = None if kmax < 1e-9 else 1.0 / kmax
    anchors = plan.anchors or {}
    mid = 0.5 * (s_a + s_b)
    phase = ("collection" if mid < anchors.get("collect_s", -1) else "ingress" if mid < anchors.get("patrol_start_s", -1)
             else "patrol" if mid < anchors.get("patrol_end_s", -1) else "egress" if mid < anchors.get("terminal_s", -1)
             else "terminal")
    kind = (plan.proposal or {}).get("turn_kind")
    req = {"teardrop": mon_cfg["turn_teardrop_min_m"], "u": mon_cfg["turn_u_min_m"],
           "oblique": mon_cfg["turn_oblique_min_m"]}.get(str(kind).lower()) if kind else None
    topo = (plan.topology or {}).get("final")
    return {"member": member, "window_start_frame": int(i0), "window_frames": int(size),
            "t_start_s": float(np.asarray(track.tau_us)[i0] / 1e6), "centroid_xy": [float(center[0]), float(center[1])],
            "max_deviation_m": dev, "rule_radius_m": float(rules["radius_m"]), "rule_window_s": float(rules["window_s"]),
            "rule_max_start_end_m": float(rules["max_start_end_m"]), "speed_mean_m_s": float(spd.mean()),
            "speed_min_m_s": float(spd.min()), "speed_max_m_s": float(spd.max()), "s_range_m": [s_a, s_b],
            "planned_min_curve_radius_m": radius, "phase_by_reference_anchors": phase, "topology": topo,
            "turn_kind": kind, "preset_min_radius_m": req,
            "meets_preset_min_radius": None if (req is None or radius is None) else bool(radius >= req),
            "union_total_duration_s": float(d["total_duration_s"]),
            "note": "疑似误报：窗口内 20 s 的位置都在 30 m 内且起止相距不超过 30 m；是否为检测器问题由审查方判断"}


# ---------------------------------------------------------------- 单个 attempt 的仿真链

def _primary_code(codes):
    order = ("timeline_inconsistent", "sim_timeout", "semantic_ambiguous", "constraint_violation",
             "separation_violation", "segment_semantic_failed")
    for c in order:
        if c in codes:
            return c
    return codes[0] if codes else None


def run_attempt(ctx, group, task, states, plan, *, attempt, planned_by):
    """一次完整的仿真链。候选失败返回 accepted=False 的记录；时间线/保留门禁问题抛 P0Stop。"""
    from task_v07.criteria import load_criteria
    from ..config import load_config
    from ..criteria.segment import SegmentTask, verify_segments
    from ..criteria.validity import check_validity, visible_track
    from ..sim.guided import run_guided_segment
    from ..sim.stitch import stitch
    from ..sim.types import TimelineInconsistent

    S = load_config("sim").values
    G = load_config("guidance").values
    mon_cfg = load_config("monitoring").values
    tube_m = ctx.params["tracking_tube_m"]
    members = sorted(group.member_ids)
    rec = {"attempt": int(attempt), "planned_by": planned_by, "plan_nominal_duration_s": plan.nominal_duration_s}
    results, member_wall = [], {}
    t0 = time.perf_counter()
    for m in members:
        tm = time.perf_counter()
        r = run_guided_segment(to_guided(plan.members[m]), states[m], final=True, vehicle_overrides=None,
                               disturbance=None)
        member_wall[m] = time.perf_counter() - tm
        results.append(r)
        if r.status != "ok":                       # 一个成员超时即整个 attempt 作废，不再仿真其余成员
            break
    rec["sim_wall_s"] = time.perf_counter() - t0
    rec["member_wall_s"] = member_wall
    bad = [r.member_id for r in results if r.status != "ok"]
    if bad:
        rec.update(accepted=False, codes=["sim_timeout"], failures=[[m, "sim_status", "sim_timeout"] for m in bad],
                   primary_code="sim_timeout", members_simulated=len(results), diag_wall_s=0.0)
        return rec, None
    try:
        tracks = stitch(results)
    except TimelineInconsistent as exc:
        raise P0Stop("timeline_inconsistent", str(exc), {"attempt": attempt}) from None
    t1 = time.perf_counter()
    release_us = {m: int(round((S["initial_settle_s"] + plan.members[m].release_delay_s) * 10)) * 100_000
                  for m in members}
    verdict = verify_segments(ctx.scene, tracks, release_us, [SegmentTask(0, "monitoring", task.target_id)])[0]
    visible = [visible_track(tracks[m], release_us[m], offset_us=0) for m in members]
    valid = check_validity(ctx.scene, visible)
    clean = all(bool(np.all(np.diff(tracks[m].tau_us) == FRAME_US)) for m in members)
    from ..criteria.window import scene_geometry
    geom = scene_geometry(ctx.scene)
    ti = geom.facility_ids.index(task.target_id)
    other = [j for j in range(len(geom.facility_ids)) if j != ti]

    nontarget = {}
    for m in members:
        lv = verdict.windows[m].levels
        nontarget[m] = {"max_level_nontarget": int(lv[:, other].max()) if other else 0,
                        "frames_ge2_nontarget": int((lv[:, other] >= 2).sum()) if other else 0,
                        "max_level_target": int(lv[:, ti].max()), "frames_ge2_target": int((lv[:, ti] >= 2).sum())}
    gates = {"stitch_clean": clean, "segment_passed": bool(verdict.passed), "validity_passed": bool(valid.passed),
             "nontarget_layer_le_1": all(v["max_level_nontarget"] <= 1 for v in nontarget.values())}
    accepted = all(gates.values())
    failures = [list(f) for f in verdict.failures] + [list(f) for f in valid.failures]
    codes = sorted({f[2] for f in failures})
    if not gates["stitch_clean"]:
        raise P0Stop("timeline_inconsistent", "stitch 之后的轨迹不是 10 Hz 整数网格", {"attempt": attempt})

    criteria = load_criteria()
    crossings = (plan.witnesses or {}).get("crossings", {})
    diag, dwell = {}, []
    for m in members:
        mp = plan.members[m]
        tube, lo, sarr, level, curve = tracking_diagnostic(mp, tracks[m], release_us[m], G, tube_m)
        diag[m] = {"tracking": tube, "speed": speed_diagnostic(mp, tracks[m], lo, sarr),
                   "boundary": boundary_diagnostic(verdict.windows[m].levels, len(crossings.get(m, ()))),
                   "release_us": release_us[m]}
        if any(f[0] == m and f[1] == "no_dwell_window" for f in failures):
            det = dwell_detail(plan, mp, tracks[m], verdict, m, lo, sarr, curve, criteria, mon_cfg)
            if det is not None:
                dwell.append(det)
    cond_false = {m: sorted(k for k, ok in c.items() if ok is not True) for m, c in verdict.member_conditions.items()}
    rec.update(
        accepted=bool(accepted), codes=codes, primary_code=_primary_code(codes), failures=failures, gates=gates,
        members_simulated=len(results), tau_end_s=float(max(int(tracks[m].tau_us[-1]) for m in members) / 1e6),
        frames={m: int(len(tracks[m].tau_us)) for m in members},
        verdict={"passed": bool(verdict.passed), "codes": list(verdict.codes), "conditions_false": cond_false,
                 "group_conditions": {k: v for k, v in verdict.group_conditions.items()},
                 "window_frames": {m: list(map(int, v)) for m, v in verdict.window_frames.items()}},
        validity={"passed": bool(valid.passed), "min_separation_m": valid.min_separation_m,
                  "closest_pair": None if valid.closest_pair is None else list(valid.closest_pair),
                  "interp_min_separation_m": valid.interp_min_separation_m,
                  "interp_closest_pair": None if valid.interp_closest_pair is None else list(valid.interp_closest_pair),
                  "restricted_frames": dict(valid.restricted_frames), "outside_world_frames": dict(valid.outside_world_frames),
                  "codes": list(valid.codes)},
        nontarget=nontarget, members=diag, dwell=dwell, tracks_sha256=tracks_digest(tracks))
    rec["diag_wall_s"] = time.perf_counter() - t1
    if accepted:                                   # 保留段必须真的满足全部门禁；否则是核验器或流程代码错误
        ok = (not verdict.failures and not valid.failures and valid.restricted_ok
              and (valid.min_separation_m is None or valid.min_separation_m >= criteria["quality"]["min_separation_error_m"])
              and all(v["max_level_nontarget"] <= 1 and v["max_level_target"] <= 1 for v in nontarget.values()))
        if not ok:
            raise P0Stop("retained_gate_violation", "保留的段与门禁记录不一致", {"attempt": attempt, "gates": gates})
    return rec, tracks


def _sim_chain_record(a, rec):
    return {"attempt": int(a), "ok": False, "seconds": rec["sim_wall_s"] + rec["diag_wall_s"], "stage": "simulation",
            "code": rec["primary_code"], "reason": "仿真/核验失败：" + ",".join(rec["codes"]),
            "feasible_set": "simulation", "witness": {"codes": rec["codes"], "failures": rec["failures"][:20]},
            "repairs": [], "built_candidate": True}


def save_tracks(out_dir, contract_id, attempt, tracks):
    sub = Path(out_dir) / "contracts"
    sub.mkdir(parents=True, exist_ok=True)
    arrays = {f"{m}.{f}": np.asarray(getattr(tracks[m], f)) for m in sorted(tracks) for f in FIELDS}
    np.savez_compressed(str(sub / f"{contract_id}.a{attempt:02d}.npz"), **arrays)


def try_segment(ctx, mission, initial_plan, *, attempt_start, quick, out_dir, clock=None, log=None):
    """复用 initial_plan（第 a=attempt_start 次规划成功）；仿真链不过则从 a+1 接着用共享的 20 次预算。
    quick 只影响调用方对 P0 的处理；候选失败两个阶段都照常重试，但每个失败 attempt 都完整记录，不隐藏。"""
    group, task = mission.groups[0], mission.tasks[0]
    states = initial_states(ctx.family, group.member_ids)
    key0 = RngKey(mission.family_id, mission.draw_index, "shape", mission=0, branch=None, group=group.group_id,
                  segment=0)
    budget = int(ctx.params["shape_attempts"])
    t_all = time.perf_counter()
    plan, a, planned_by = initial_plan, int(attempt_start), "saved"
    chain = list(initial_plan.attempt_log)
    attempts, sim_wall, replan_wall = [], 0.0, 0.0
    contract_id = (getattr(mission, "business_key", None) or {}).get("contract_id") \
        or f"{mission.family_id}_d{mission.draw_index}"
    while True:
        rec, tracks = run_attempt(ctx, group, task, states, plan, attempt=a, planned_by=planned_by)
        attempts.append(rec)
        sim_wall += rec["sim_wall_s"] + rec["diag_wall_s"]
        if tracks is not None and out_dir is not None:
            save_tracks(out_dir, contract_id, a, tracks)
        if rec["accepted"]:
            return SegmentRun("retained", attempts, a, plan, tracks, None, chain, time.perf_counter() - t_all,
                              sim_wall, replan_wall)
        chain.append(_sim_chain_record(a, rec))
        if log:
            log(f"    attempt {a} 候选失败 {rec['codes']} sim={rec['sim_wall_s']:.0f}s")
        if clock is not None and clock.exceeded():
            return SegmentRun("interrupted", attempts, None, None, None, None, chain, time.perf_counter() - t_all,
                              sim_wall, replan_wall)
        a += 1
        if a >= budget:
            break
        t1 = time.perf_counter()
        nxt = plan_segment(ctx, group, task, states, (), key0, attempt_start=a, prior_log=chain)
        replan_wall += time.perf_counter() - t1
        if nxt.failure is not None:
            chain = list(nxt.attempt_log)
            fail = Failure("budget_exhausted", f"{len(chain)} 次 attempt（规划 + 仿真）用完预算，保留每次底层原因",
                           "random_construction_and_simulation",
                           {"attempts": len(chain), "last_planning_failure": nxt.failure.code,
                            "underlying_codes": _underlying(chain)}, None)
            return SegmentRun("failed", attempts, None, None, None, fail, chain, time.perf_counter() - t_all,
                              sim_wall, replan_wall)
        plan, a, planned_by = nxt, last_attempt(nxt.attempt_log), "replan"
        chain = list(nxt.attempt_log)
    fail = Failure("budget_exhausted", f"{budget} 次 attempt（规划 + 仿真）用完预算，保留每次底层原因",
                   "random_construction_and_simulation",
                   {"attempts": budget, "underlying_codes": _underlying(chain)}, None)
    return SegmentRun("failed", attempts, None, None, None, fail, chain, time.perf_counter() - t_all, sim_wall,
                      replan_wall)


def last_attempt(log):
    """日志最后一条记录的 attempt 序号。仿真失败记录与同一次规划成功记录共用序号，不能用日志长度推算。"""
    return int(log[-1]["attempt"])


def _underlying(chain):
    return [{"attempt": r.get("attempt"), "stage": r.get("stage"), "code": r.get("code")} for r in chain
            if not r.get("ok")]


# ---------------------------------------------------------------- 复跑比较

def strip_timing(x):
    if isinstance(x, dict):
        return {k: strip_timing(v) for k, v in x.items() if k not in TIMING_KEYS}
    if isinstance(x, (list, tuple)):
        return [strip_timing(v) for v in x]
    return x


def payload_components(plan_sha, accepted_digest, run):
    """复跑逐位比较的各组件（耗时、路径、日志时间戳排除）。"""
    return {
        "plan_chain_sha256": plan_sha,
        "accepted_plan_digest": accepted_digest,
        "attempts_json_sha256": hashlib.sha256(M.canonical_json(strip_timing(run.attempts))).hexdigest(),
        "tracks": None if run.tracks is None else tracks_digest(run.tracks),
        "verdict_json_sha256": hashlib.sha256(M.canonical_json(
            [strip_timing({k: a.get(k) for k in ("verdict", "validity", "codes", "failures", "gates", "nontarget")})
             for a in run.attempts])).hexdigest(),
    }


def compare_components(first, second):
    """返回不一致的组件名列表（空 = 逐位一致）。"""
    bad = []
    for k in sorted(set(first) | set(second)):
        if first.get(k) != second.get(k):
            bad.append(k)
    return bad


# ---------------------------------------------------------------- 快速 10 合同的确定性选择

def select_quick(successes, count):
    """先含设施数 1/2/3 各一合同，再含全族 vehicle_count 最大合同和第 0 组人数最大合同（可重合），其余按 order/draw 补足。
    successes：第 4 部分成功合同的记录。同值取 (order, draw) 最小，不重新抽公共条件。"""
    ordered = sorted(successes, key=lambda r: (r["order"], r["draw_index"]))
    chosen, why = [], {}

    def add(r, reason):
        if r is not None and r["contract_id"] not in why:
            chosen.append(r)
            why[r["contract_id"]] = [reason]
        elif r is not None:
            why[r["contract_id"]].append(reason)

    for fc in (1, 2, 3):
        add(next((r for r in ordered if r["facility_count"] == fc), None), f"设施数 {fc} 中 order/draw 最早")
    if ordered:
        mv = max(r["vehicle_count"] for r in ordered)
        add(next(r for r in ordered if r["vehicle_count"] == mv), f"全族 vehicle_count 最大（{mv}）")
        mg = max(r["group_size"] for r in ordered)
        add(next(r for r in ordered if r["group_size"] == mg), f"第 0 组人数最大（{mg}）")
    for r in ordered:
        if len(chosen) >= count:
            break
        add(r, "按 order/draw 补足")
    chosen = chosen[:count]
    info = {"max_vehicle_count": max((r["vehicle_count"] for r in ordered), default=None),
            "max_group_size": max((r["group_size"] for r in ordered), default=None),
            "reasons": {r["contract_id"]: why[r["contract_id"]] for r in chosen}}
    return [r["contract_id"] for r in chosen], info


def full_queue(successes, quick_ids):
    """全量阶段：第 4 部分成功集合去掉快速已完成者。受 2 小时边界限制，按 (draw_index, order) 轮转取，
    这样中途截止时覆盖的是各族而不是前几个族。"""
    q = set(quick_ids)
    rest = [r for r in successes if r["contract_id"] not in q]
    return [r["contract_id"] for r in sorted(rest, key=lambda r: (r["draw_index"], r["order"]))]


# ---------------------------------------------------------------- 单合同与批次

def _record_head(rec4, ctx, plan):
    return {"contract_id": rec4["contract_id"], "family_id": rec4["family_id"], "order": rec4["order"],
            "draw_index": rec4["draw_index"], "facility_count": rec4["facility_count"],
            "group_size": rec4["group_size"], "vehicle_count": rec4["vehicle_count"],
            "n_restricted_zones": len(ctx.obstacles), "target_id": rec4["target_id"],
            "lateral_spacing_m": rec4["lateral_spacing_m"], "map_side_m": rec4.get("map_side_m"),
            "topology": rec4["metrics"]["topology"], "formation_prior": rec4["metrics"]["formation_prior"],
            "formation_realized": rec4["metrics"]["formation_realized"],
            "initial_speed_m_s": rec4["speed_profile"]["initial_speed_m_s"],
            "change_rate_per_min": rec4["speed_profile"]["change_rate_per_min"],
            "plan_nominal_duration_s": plan.nominal_duration_s, "part4_plan_sha256": rec4["plan_sha256"],
            "part4_attempts": rec4["attempts"]}


def run_contract(entry, rec4, *, plan_dir, data_root, cache_dir, out_dir, quick, clock, do_rerun=True, log=None):
    """第 4 部分已成功的一个合同：首次执行（复用计划）+ 同键重新执行（含重新规划）。返回可序列化的结果记录。"""
    from ..scene.context import load_context

    t_all = time.perf_counter()
    cid = rec4["contract_id"]
    ctx = load_context(entry, data_root=data_root, cache_dir=cache_dir)
    common, mission, group, task, states, key = contract_inputs(ctx, rec4["draw_index"])
    if (M.jsonable(rec4["common_groups"]) != M.jsonable([
            {"group_id": g.group_id, "member_ids": list(g.member_ids),
             "initial_speed_m_s": g.speed_profile.initial_speed_m_s,
             "change_rate_per_min": g.speed_profile.change_rate_per_min, "formation_prior": g.formation_prior}
            for g in common.groups]) or rec4["target_id"] != task.target_id):
        raise P0Stop("input_mismatch", f"{cid}: 第 4 部分记录的公共抽签/目标与重新计算的不一致")
    rec4_loaded, arrays = load_saved_plan(plan_dir, cid)
    plan0 = plan_from_record(rec4_loaded, arrays)
    roundtrip = M.canonical_json(M.plan_to_record(plan0)[0]) == M.canonical_json(rec4_loaded["plan"])
    if not roundtrip:
        raise P0Stop("input_mismatch", f"{cid}: 由 JSON/NPZ 重建的计划与保存的计划记录不一致")
    mission = _with_contract_id(mission, cid, rec4["order"])
    t_load = time.perf_counter() - t_all
    a0 = last_attempt(plan0.attempt_log)
    first = try_segment(ctx, mission, plan0, attempt_start=a0, quick=quick, out_dir=out_dir, clock=clock, log=log)
    out = _record_head(rec4, ctx, plan0)
    out.update(stage="quick" if quick else "full", status=first.status, attempt_start=a0,
               attempts=first.attempts, final_attempt=first.final_attempt,
               failure=M.failure_record(first.failure), plan_reload_roundtrip_ok=bool(roundtrip),
               timing={"load_s": t_load, "first_run_wall_s": first.wall_s, "sim_wall_s": first.sim_wall_s,
                       "replan_wall_s": first.replan_wall_s})
    out["rerun"] = {"status": "not_applicable" if first.status != "retained" else "pending", "wall_s": 0.0}
    if first.status == "retained":
        accepted_plan_first = first.plan
        digest_first = plan_digest(accepted_plan_first)
        first_comp = payload_components(rec4["plan_sha256"], digest_first, first)
        out["accepted_plan_digest"] = digest_first
        if not do_rerun:
            out["rerun"] = {"status": "pending", "wall_s": 0.0, "reason": "not_selected_by_rerun_policy"}
        elif clock.exceeded():
            out["rerun"] = {"status": "pending", "wall_s": 0.0, "reason": "wall_budget"}
        else:
            out["rerun"] = rerun_contract(entry, rec4, first_comp, a0, mission_id=(cid, rec4["order"]),
                                          data_root=data_root, cache_dir=cache_dir, quick=quick, log=log)
        if out["rerun"]["status"] == "mismatch":
            raise P0Stop("rerun_mismatch", f"{cid}: 同键复跑不一致：{out['rerun']['mismatches']}",
                         {"record": out})
    out["timing"]["total_wall_s"] = time.perf_counter() - t_all
    return out


def _with_contract_id(mission, cid, order):
    from dataclasses import replace

    return replace(mission, business_key={**mission.business_key, "contract_id": cid, "order": order})


def rerun_contract(entry, rec4, first_components, a0, *, mission_id, data_root, cache_dir, quick, log=None):
    """从键重新执行整条链（读场景 → 公共抽签 → 规划 → 仿真 → 拼接 → 核验），与首次执行逐位比较。"""
    from ..scene.context import load_context

    t0 = time.perf_counter()
    cid, order = mission_id
    ctx = load_context(entry, data_root=data_root, cache_dir=cache_dir)
    rec2, plan2 = M.plan_contract(ctx, entry, rec4["draw_index"])
    M.finalize_record(rec2, plan2)
    mismatches = []
    if plan2.failure is not None:
        mismatches.append("replan_failed")
        return {"status": "mismatch", "wall_s": time.perf_counter() - t0, "mismatches": mismatches,
                "detail": {"replan_failure": M.failure_record(plan2.failure)}}
    common_ok = (M.jsonable(rec2["common_groups"]) == M.jsonable(rec4["common_groups"])
                 and rec2["target_id"] == rec4["target_id"]
                 and M.jsonable(rec2["mission_business_key"]) == M.jsonable(rec4["mission_business_key"]))
    if not common_ok:
        mismatches.append("common_draw_or_target")
    if rec2["plan_sha256"] != rec4["plan_sha256"]:
        mismatches.append("part4_plan_sha256")
    _, mission2, *_ = contract_inputs(ctx, rec4["draw_index"])
    mission2 = _with_contract_id(mission2, cid, order)
    second = try_segment(ctx, mission2, plan2, attempt_start=last_attempt(plan2.attempt_log), quick=quick,
                         out_dir=None,
                         clock=None, log=log)
    if second.status != "retained":
        mismatches.append(f"rerun_status_{second.status}")
        return {"status": "mismatch", "wall_s": time.perf_counter() - t0, "mismatches": mismatches,
                "detail": {"rerun_failure": M.failure_record(second.failure)}}
    comp2 = payload_components(rec2["plan_sha256"], plan_digest(second.plan), second)
    bad = compare_components(first_components, comp2)
    mismatches += [f"component:{k}" for k in bad]
    return {"status": "mismatch" if mismatches else "equal", "wall_s": time.perf_counter() - t0,
            "mismatches": mismatches,
            "compared": sorted(comp2), "tracks_members": sorted(second.tracks), "common_draw_equal": common_ok,
            "plan_chain_sha256": rec2["plan_sha256"], "attempts_rerun": len(second.attempts)}


def simulate_devset(plan_dir, *, stage, quick_dir, out_dir, entries, data_root, cache_dir, devset_path=None,
                    contracts=None, wall_budget_s=None, quick_count=None, rerun_every=1, log=print):
    """第 5 部分：stage = quick（10 合同）或 full（第 4 部分成功集合的其余合同；快速 10 条直接计入）。"""
    from ..config import load_config

    cfg = load_config("monitoring").values
    budget = float(wall_budget_s if wall_budget_s is not None else cfg["simulation_wall_budget_s"])
    qn = int(quick_count if quick_count is not None else cfg["quick_contract_count"])
    plan_dir = Path(plan_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=False)
    logf = (out / "progress.log").open("a", encoding="utf-8", newline="\n")

    def say(s):
        logf.write(s + "\n")
        logf.flush()
        log(s)

    by_family = {e["family_id"]: e for e in entries}
    succ = []
    for p in sorted((plan_dir / "contracts").glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        if r.get("success"):
            succ.append(r)
    succ.sort(key=lambda r: (r["order"], r["draw_index"]))
    plan_summary_path = plan_dir / "summary.json"
    quick_ids, quick_results, used_s = [], [], 0.0
    selection = None
    if stage == "quick":
        quick_ids, selection = select_quick(succ, qn)
        queue = quick_ids
    else:
        qs = json.loads((Path(quick_dir) / "summary.json").read_text(encoding="utf-8"))
        if qs.get("p0_stop") or qs.get("incomplete"):
            raise ValueError("快速检查未完整通过（有 P0 停止或未完成合同），不得进入全量")
        quick_ids = list(qs["queue"])
        used_s = float(qs["wall_s"])
        for cid in quick_ids:
            quick_results.append(json.loads((Path(quick_dir) / "contracts" / f"{cid}.json").read_text(encoding="utf-8")))
        queue = full_queue(succ, quick_ids)
    subset = wall_budget_s is not None or quick_count is not None
    if contracts:
        wanted = [c for c in contracts]
        queue = [c for c in queue if c in set(wanted)] if stage == "full" else [c for c in wanted]
        subset = True
    by_id = {r["contract_id"]: r for r in succ}
    clock = WallClock(budget, used_s)
    say(f"阶段 {stage}：队列 {len(queue)} 个合同；已用 {used_s:.0f} s / 预算 {budget:.0f} s")
    results, not_run, p0 = [], [], None
    for i, cid in enumerate(queue):
        if clock.exceeded():
            not_run = queue[i:]
            say(f"墙钟 {clock.elapsed():.0f} s 达到预算 {budget:.0f} s，在已完成处停止；未运行 {len(not_run)} 个")
            break
        rec4 = by_id[cid]
        entry = by_family[rec4["family_id"]]
        say(f"[{i + 1}/{len(queue)}] {cid} 设施{rec4['facility_count']} n={rec4['group_size']} "
            f"拓扑={rec4['metrics']['topology']} 计划 {rec4['plan']['nominal_duration_s']:.0f}s  累计 {clock.elapsed():.0f}s")
        try:
            res = run_contract(entry, rec4, plan_dir=plan_dir, data_root=data_root, cache_dir=cache_dir, out_dir=out,
                               quick=(stage == "quick"), clock=clock, do_rerun=(i % int(rerun_every) == 0), log=say)
        except P0Stop as exc:
            p0 = {"kind": exc.kind, "message": str(exc), "contract_id": cid, "detail": M.jsonable(exc.detail)}
            say(f"P0 停止：{exc}")
            not_run = queue[i:]
            res = (exc.detail or {}).get("record") if isinstance(exc.detail, dict) else None
            if res is not None:
                res["status"] = "p0_stop"
                results.append(res)
                M.write_json(out / "contracts" / f"{cid}.json", res)
                not_run = queue[i + 1:]
            break
        except Exception as exc:                                             # 未捕获的异常：停批次，保留现场
            p0 = {"kind": "uncaught_exception", "message": repr(exc), "contract_id": cid,
                  "trace": traceback.format_exc()}
            say(f"未捕获异常，停止：{exc!r}")
            not_run = queue[i:]
            break
        M.write_json(out / "contracts" / f"{cid}.json", res)
        results.append(res)
        t = res["timing"]
        say(f"    -> {res['status']} attempts={len(res['attempts'])} 首次 {t['first_run_wall_s']:.0f}s "
            f"复跑 {res['rerun']['status']} {res['rerun'].get('wall_s', 0):.0f}s")
        if res["status"] == "interrupted":
            not_run = queue[i + 1:]
            say("合同在重试之间到达墙钟预算，已保存此前的 attempt")
            break
    from . import monitoring_sim_report as SR

    summary = SR.build_sim_summary(rerun_every=int(rerun_every), stage=stage, queue=queue, results=results, not_run=not_run, p0=p0,
                                   quick_results=quick_results, selection=selection, successes=succ,
                                   wall_s=clock.elapsed(), budget_s=budget, subset=subset)
    summary["meta"] = {"plan_dir": str(plan_dir), "plan_summary_sha256": M._sha256_file(plan_summary_path)
                       if plan_summary_path.exists() else None,
                       "devset_path": None if devset_path is None else str(devset_path),
                       "data_root": str(data_root), "cache_dir": str(cache_dir), "out_dir": str(out),
                       "quick_dir": None if quick_dir is None else str(quick_dir), "environment": M.environment_report(),
                       "argv": __import__("sys").argv}
    M.write_json(out / "summary.json", summary, indent=2)
    logf.close()
    return summary
