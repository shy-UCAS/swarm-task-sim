"""逐成员分段仿真（V8-07；V8-08 第 4 部分）：新引导层沿加密曲线逐 20 ms 求期望速度，
交给冻结的速度控制器与点质量模型（经 InjectableEngine）。结果放到编组统一时钟上，
与 V8-04 的 MemberSegmentResult/stitch 约定一致：非最后一段的越过帧不在本段帧中，是下一段的首帧。
"""
import math
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from swarm_sim.fast_dynamics.contracts import PlantState
from swarm_sim.fast_dynamics.engine import seconds_to_us

from ..config import load_config
from .guidance import desired_velocity, make_curve, node_index, nominal_time, speed_profile
from .kernel import InjectableEngine, member_config
from .types import FRAME_US, MemberBoundaryState, MemberSegmentResult, SimContractError

FIRST_START_TOL_M = 1e-6
ALT_TOL_M = 1e-9
TAIL_TOL_M = 1e-9
GRID_TOL = 1e-7


@dataclass(frozen=True)
class GuidedSegmentPlan:
    """一个成员一段：curve_xy 为加密曲线点，end_s_m 为段末点弧长（须在节点上），
    stops 为 (弧长, 停留秒) 元组；出发延迟只用于第 0 段。"""
    member_id: str
    segment_index: int
    curve_xy: tuple
    altitude_m: float
    speed_breaks: tuple
    end_s_m: float
    stops: tuple = ()
    release_delay_s: float = 0.0


@dataclass(frozen=True)
class GuidedRecord:
    """本段诊断记录；crossing_local_frame 为越过帧的本段帧号（最后一段或超时为 None）。"""
    tau_start_us: int
    tau_end_us: int
    crossing_local_frame: Optional[int]
    progress_end_m: float
    nominal_time_s: float
    budget_s: float
    stops_done: int
    wall_s: float


def _on_tenth_grid(x):
    return abs(x * 10.0 - round(x * 10.0)) <= GRID_TOL


# ---------------------------------------------------------------- 输入检查

def _check_header(plan, state):
    if plan.member_id != state.member_id or plan.segment_index != state.segment_index:
        raise SimContractError("plan 与 state 的成员或段号不一致")
    tau = state.tau_us
    if isinstance(tau, bool) or not isinstance(tau, (int, np.integer)) or tau < 0 or tau % FRAME_US:
        raise SimContractError(f"state.tau_us={tau} 不是非负的 {FRAME_US} µs 整数倍")
    if plan.segment_index == 0 and tau != 0:
        raise SimContractError("第 0 段必须从 tau_us=0 开始")
    d = float(plan.release_delay_s)
    if plan.segment_index != 0 and d != 0.0:
        raise SimContractError("非第 0 段不得有出发延迟")
    if not math.isfinite(d) or d < 0.0 or not _on_tenth_grid(d):
        raise SimContractError(f"出发延迟 {d} 无效或不在 10 Hz 网格上")


def _check_end(curve, plan, final, G):
    iE = node_index(curve, plan.end_s_m)
    if final and iE != len(curve.s) - 1:
        raise SimContractError(f"最后一段的段末点须为曲线终点（段末节点 {iE}，曲线共 {len(curve.s)} 点）")
    if not final and curve.length - float(plan.end_s_m) < G["tail_min_m"] - TAIL_TOL_M:
        raise SimContractError(f"段末点之后的曲线长 {curve.length - float(plan.end_s_m)} m < {G['tail_min_m']} m")
    return iE


def _check_stops(plan):
    prev = 0.0
    for k, item in enumerate(plan.stops):
        if len(item) != 2:
            raise SimContractError(f"停止点 {k} 应为 (弧长, 停留秒)")
        s, dur = float(item[0]), float(item[1])
        if not (math.isfinite(s) and prev < s < float(plan.end_s_m)):
            raise SimContractError(f"停止点 {k} 弧长 {s} 不在 ({prev}, {plan.end_s_m}) 内（须严格递增）")
        if not (math.isfinite(dur) and dur > 0.0 and _on_tenth_grid(dur)):
            raise SimContractError(f"停止点 {k} 停留时长 {dur} 须为正且为 0.1 s 的整数倍")
        prev = s


def _check_start(curve, plan, state, S):
    dist = float(np.hypot(curve.xy[0, 0] - float(state.p[0]), curve.xy[0, 1] - float(state.p[1])))
    tol = FIRST_START_TOL_M if plan.segment_index == 0 else S["join_max_distance_m"]
    if dist > tol:
        raise SimContractError(f"曲线起点与当前位置平面距离 {dist} m > {tol} m")
    if abs(float(state.p[2]) - float(plan.altitude_m)) > ALT_TOL_M:
        raise SimContractError(f"当前高度 {state.p[2]} 与段高度 {plan.altitude_m} 不一致")


# ---------------------------------------------------------------- 执行

def run_guided_segment(plan, state, *, final, guidance=None, sim=None, vehicle_overrides=None, disturbance=None):
    G = (guidance if guidance is not None else load_config("guidance")).values
    S = (sim if sim is not None else load_config("sim")).values
    _check_header(plan, state)
    curve = make_curve(plan.curve_xy, max_chord_m=G["max_chord_m"], max_turn_rad=G["max_turn_per_chord_rad"])
    _check_end(curve, plan, final, G)
    _check_stops(plan)
    _check_start(curve, plan, state, S)

    m, k_seg = plan.member_id, plan.segment_index
    alt = float(plan.altitude_m)
    end_s = float(plan.end_s_m)
    L = curve.length
    tau0 = int(state.tau_us)
    cfg = member_config(vehicle_overrides)
    tau = cfg.controller.velocity_response_time_s
    k = G["k_pos_per_s"]
    v0 = 0.0 if k_seg == 0 else float(np.hypot(state.v[0], state.v[1]))
    queue = [(float(s), float(d)) for s, d in plan.stops]
    if final:
        queue.append((L, S["terminal_hold_s"]))
    stop_xy = {s: curve.xy[node_index(curve, s)] for s, _ in queue}
    vp = speed_profile(curve, plan.speed_breaks, a_lat=G["a_lat_m_s2"], a_lon=G["a_lon_m_s2"],
                       v_max=cfg.vehicle_profile.max_speed_xy_m_s, v0=v0, v_end=0.0 if final else None,
                       stops=tuple(s for s, _ in queue))
    t_nom = nominal_time(curve, vp, 0.0, end_s)
    pre = S["initial_settle_s"] + float(plan.release_delay_s) if k_seg == 0 else 0.0
    release_us = seconds_to_us(round(pre, 1))
    budget_s = t_nom * (1.0 + G["budget_factor"]) + G["budget_const_s"] + sum(d for _, d in queue) + pre
    budget_us = math.ceil(budget_s * 10.0) * FRAME_US
    p0, v0_, a0 = (np.asarray(x, dtype=float) for x in (state.p, state.v, state.a))
    engine = InjectableEngine(cfg, PlantState(p0[None], v0_[None], a0[None]), disturbance, tau0)

    def pull(q, x):
        return np.array([k * (q[0] - x[0]), k * (q[1] - x[1]), k * (alt - x[2])])

    status = "sim_timeout"
    crossing = None
    s_prev = 0.0
    holding = False
    hold_end_us = None
    stops_done = 0
    started = time.perf_counter()
    while engine.time_us < budget_us:
        t = engine.time_us
        x = engine.state
        xp, xv = x.p[0], x.v[0]
        if t < release_us:
            vdes = pull(curve.xy[0], xp)
            s_p = s_prev
        else:
            guide = True
            if holding:
                if t >= hold_end_us:
                    holding = False
                    stops_done += 1
                    queue.pop(0)
                    if final and not queue:
                        status = "ok"
                        break
                else:
                    vdes = pull(stop_xy[queue[0][0]], xp)
                    s_p = s_prev
                    guide = False
            if guide:
                s_limit = queue[0][0] if queue else L
                vdes, s_p = desired_velocity(curve, vp, xp, s_prev, tau=tau, k_pos=k, lookahead_m=G["lookahead_m"],
                                             slope_half_m=G["slope_half_window_m"], s_limit=s_limit,
                                             window_m=G["projection_window_m"], altitude=alt)
                if queue:
                    s_stop, dur = queue[0]
                    q = stop_xy[s_stop]
                    if s_stop - s_p <= G["stop_approach_m"]:
                        vdes = pull(q, xp)
                    if (math.hypot(q[0] - xp[0], q[1] - xp[1]) <= S["terminal_radius_m"]
                            and math.hypot(xv[0], xv[1]) <= S["terminal_speed_m_s"]):
                        holding = True
                        hold_end_us = t + seconds_to_us(dur)
                        vdes = pull(q, xp)
        if t % FRAME_US == 0 and not final and t >= release_us and not holding and s_p >= end_s:
            status = "ok"
            crossing = t // FRAME_US
            break
        s_prev = s_p
        engine.step(vdes[None])
    wall = time.perf_counter() - started

    samples = engine.samples
    tau_us = tau0 + np.array([sv.t_us for sv in samples], dtype=np.int64)
    p = np.array([sv.p[0] for sv in samples], dtype=float).reshape(-1, 3)
    v = np.array([sv.v[0] for sv in samples], dtype=float).reshape(-1, 3)
    a = np.array([sv.a[0] for sv in samples], dtype=float).reshape(-1, 3)
    tau_end = tau0 + engine.time_us
    end_state = switch = None
    if not final and status == "ok":
        xs = engine.state
        end_state = MemberBoundaryState(m, k_seg + 1, tau_end, tuple(float(c) for c in xs.p[0]),
                                        tuple(float(c) for c in xs.v[0]), tuple(float(c) for c in xs.a[0]))
        switch = tau_end
    record = GuidedRecord(tau0, tau_end, crossing, float(s_prev), t_nom, budget_s, stops_done, wall)
    return MemberSegmentResult(m, k_seg, bool(final), status, tau_us, p, v, a, end_state, switch, (record,))
