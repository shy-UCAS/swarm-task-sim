"""按时间跟踪（V8-13 第 2 部分，指令 2.1）：参考是绝对时钟上的连续 p/v/a，不是弧长曲线。

引导律（U C.2）：u_xy = v_ref(t) + tau·a_ref(t) + k_pos·(p_ref(t) − p_xy)，u_z = k_pos·(h − p_z)。
每个 20 ms 积分步都按该时刻求参考；释放前与移动结束后参考为起点/终点、零 v/a，于是同一式子即"拉回"。
冻结核心（InjectableEngine，无扰动、无每机参数覆盖）负责速度/加速度/jerk 限制，本层不裁剪 u。

完成判定沿用旧 guided：参考移动结束（t ≥ end_s）后，首次满足冻结终止半径/速度条件才开始 2 s 保持，
保持结束即 ok；预算 B = 1.1·(T − r) + 30 + r + 2（r = 释放时刻，T = 移动结束时刻），向上取整到输出帧，
超预算为 sim_timeout。这不是编组 1800 s 拒绝。

本模块导入时不读配置、不读场景、不建目录；不导入 shapely。
"""
import math
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from swarm_sim.fast_dynamics.contracts import PlantState

from ..config import load_config
from .guided import ALT_TOL_M, FIRST_START_TOL_M, GRID_TOL
from .kernel import InjectableEngine, member_config
from .types import FRAME_US, MemberSegmentResult, SimContractError

US = 1_000_000


@dataclass(frozen=True)
class TimeReference:
    member_id: str
    release_s: float            # 编组统一时钟
    end_s: float                # 移动参考结束；不包含末端保持
    altitude_m: float
    pva: object                 # pva(t_abs_s) -> (p_xy, v_xy, a_xy)，支持标量与数组


@dataclass(frozen=True)
class TrackingRecord:
    """本段诊断记录（放在 MemberSegmentResult.pieces 中，不改 MemberSegmentResult 本身）。

    step_* 为每个 20 ms 积分步起点（本段局部 µs）处的量；frame_* 为 10 Hz 输出帧处的量。
    位置误差为水平 |p_ref − p_xy|，速度误差为水平向量差的范数。jerk 为 plant.last_jerk 的水平范数。"""
    tau_start_us: int
    tau_end_us: int
    release_us: int
    motion_end_s: float
    hold_start_us: Optional[int]
    budget_s: float
    end_p: tuple
    end_v: tuple
    end_a: tuple
    max_step_pos_err_m: float
    max_step_vel_err_m_s: float
    max_frame_pos_err_m: float
    max_frame_vel_err_m_s: float
    accel_saturated_fraction: float
    jerk_saturated_fraction: float
    step_t_us: np.ndarray
    step_pos_err_m: np.ndarray
    step_vel_err_m_s: np.ndarray
    step_jerk_xy: np.ndarray
    step_accel_xy: np.ndarray
    frame_pos_err_m: np.ndarray
    frame_vel_err_m_s: np.ndarray
    wall_s: float


def _on_tenth_grid(x):
    return abs(x * 10.0 - round(x * 10.0)) <= GRID_TOL


def _pva(reference, t_abs_s):
    p, v, a = reference.pva(t_abs_s)
    return (np.asarray(p, float).reshape(2), np.asarray(v, float).reshape(2), np.asarray(a, float).reshape(2))


def reference_velocity(reference, time_us, snapshot, *, tau, k_pos):
    """time_us 为统一时钟绝对微秒；返回 shape=(1,3) 的期望速度，直接交 InjectableEngine.step。"""
    p_ref, v_ref, a_ref = _pva(reference, time_us / US)
    x = np.asarray(snapshot.p, float).reshape(-1, 3)[0]
    return _command(p_ref, v_ref, a_ref, x, float(reference.altitude_m), tau, k_pos)


def _command(p_ref, v_ref, a_ref, x, alt, tau, k_pos):
    u = np.empty(3)
    u[0] = v_ref[0] + tau * a_ref[0] + k_pos * (p_ref[0] - x[0])
    u[1] = v_ref[1] + tau * a_ref[1] + k_pos * (p_ref[1] - x[1])
    u[2] = k_pos * (alt - x[2])
    return u[None]


def _check(reference, state, S):
    if reference.member_id != state.member_id:
        raise SimContractError("reference 与 state 的成员不一致")
    if state.segment_index != 0:
        raise SimContractError("本项只支持第 0 段")
    tau = state.tau_us
    if isinstance(tau, bool) or not isinstance(tau, (int, np.integer)) or tau != 0:
        raise SimContractError("第 0 段必须从 tau_us=0 开始")
    r, e = float(reference.release_s), float(reference.end_s)
    if not (math.isfinite(r) and math.isfinite(e) and e >= r):
        raise SimContractError(f"release_s={r}、end_s={e} 无效")
    if not _on_tenth_grid(r):
        raise SimContractError(f"释放时刻 {r} 不在 100000 µs 网格上")
    delay = r - S["initial_settle_s"]
    if delay < -GRID_TOL or not _on_tenth_grid(delay):
        raise SimContractError(f"释放时刻 {r} 与 initial_settle_s + 出发延迟（0.1 s 网格）不一致")
    p0, v0, a0 = _pva(reference, r)
    dist = float(np.hypot(p0[0] - float(state.p[0]), p0[1] - float(state.p[1])))
    if dist > FIRST_START_TOL_M:
        raise SimContractError(f"参考起点与当前位置平面距离 {dist} m > {FIRST_START_TOL_M} m")
    if abs(float(state.p[2]) - float(reference.altitude_m)) > ALT_TOL_M:
        raise SimContractError(f"当前高度 {state.p[2]} 与参考高度 {reference.altitude_m} 不一致")


def run_tracking_segment(reference, state, *, final=True, guidance=None, sim=None):
    """返回原 MemberSegmentResult；本项只支持 segment_index=0、final=True。"""
    if not final:
        raise SimContractError("本项只支持 final=True")
    G = (guidance if guidance is not None else load_config("guidance")).values
    S = (sim if sim is not None else load_config("sim")).values
    _check(reference, state, S)
    cfg = member_config()
    tau = cfg.controller.velocity_response_time_s
    k = G["k_pos_per_s"]
    a_cap = cfg.vehicle_profile.max_accel_xy_m_s2
    j_cap = cfg.vehicle_profile.max_jerk_m_s3
    m = reference.member_id
    tau0 = int(state.tau_us)
    r = float(reference.release_s)
    T = float(reference.end_s)
    hold_s = S["terminal_hold_s"]
    release_us = int(round(r * 10.0)) * FRAME_US
    budget_s = (T - r) * (1.0 + G["budget_factor"]) + G["budget_const_s"] + r + hold_s
    budget_us = math.ceil(budget_s * 10.0) * FRAME_US
    hold_us = int(round(hold_s * 10.0)) * FRAME_US
    alt = float(reference.altitude_m)
    p0, v0, a0 = (np.asarray(x, dtype=float) for x in (state.p, state.v, state.a))
    engine = InjectableEngine(cfg, PlantState(p0[None], v0[None], a0[None]), None, tau0)

    step_t, step_pe, step_ve, step_j, step_a = [], [], [], [], []
    status = "sim_timeout"
    holding = False
    hold_end_us = None
    hold_start = None
    started = time.perf_counter()
    while engine.time_us < budget_us:
        t = engine.time_us
        t_abs_us = tau0 + t
        if holding and t >= hold_end_us:
            status = "ok"
            break
        x = engine.state
        xp, xv = x.p[0], x.v[0]
        p_ref, v_ref, a_ref = _pva(reference, t_abs_us / US)
        step_t.append(t)
        step_pe.append(math.hypot(p_ref[0] - xp[0], p_ref[1] - xp[1]))
        step_ve.append(math.hypot(v_ref[0] - xv[0], v_ref[1] - xv[1]))
        step_a.append(math.hypot(x.a[0][0], x.a[0][1]))
        if (not holding and t_abs_us / US >= T
                and math.hypot(p_ref[0] - xp[0], p_ref[1] - xp[1]) <= S["terminal_radius_m"]
                and math.hypot(xv[0], xv[1]) <= S["terminal_speed_m_s"]):
            holding = True
            hold_start = t_abs_us
            hold_end_us = t + hold_us
        vdes = _command(p_ref, v_ref, a_ref, xp, alt, tau, k)       # 与 reference_velocity 同一式子
        engine.step(vdes)
        lj = engine.last_jerk[0]
        step_j.append(math.hypot(lj[0], lj[1]))
    wall = time.perf_counter() - started

    samples = engine.samples
    tau_us = tau0 + np.array([sv.t_us for sv in samples], dtype=np.int64)
    p = np.array([sv.p[0] for sv in samples], dtype=float).reshape(-1, 3)
    v = np.array([sv.v[0] for sv in samples], dtype=float).reshape(-1, 3)
    a = np.array([sv.a[0] for sv in samples], dtype=float).reshape(-1, 3)
    fp, fv, _ = reference.pva(tau_us / US)
    fp = np.asarray(fp, float).reshape(-1, 2)
    fv = np.asarray(fv, float).reshape(-1, 2)
    frame_pe = np.hypot(fp[:, 0] - p[:, 0], fp[:, 1] - p[:, 1])
    frame_ve = np.hypot(fv[:, 0] - v[:, 0], fv[:, 1] - v[:, 1])
    step_j = np.asarray(step_j[:len(step_t)], float)
    step_a = np.asarray(step_a, float)
    xs = engine.state
    rec = TrackingRecord(
        tau_start_us=tau0, tau_end_us=tau0 + engine.time_us, release_us=release_us, motion_end_s=T,
        hold_start_us=hold_start, budget_s=budget_s,
        end_p=tuple(float(c) for c in xs.p[0]), end_v=tuple(float(c) for c in xs.v[0]),
        end_a=tuple(float(c) for c in xs.a[0]),
        max_step_pos_err_m=float(max(step_pe)) if step_pe else 0.0,
        max_step_vel_err_m_s=float(max(step_ve)) if step_ve else 0.0,
        max_frame_pos_err_m=float(frame_pe.max()) if len(frame_pe) else 0.0,
        max_frame_vel_err_m_s=float(frame_ve.max()) if len(frame_ve) else 0.0,
        accel_saturated_fraction=float(np.mean(step_a >= a_cap * (1.0 - 1e-9))) if len(step_a) else 0.0,
        jerk_saturated_fraction=float(np.mean(step_j >= j_cap * (1.0 - 1e-9))) if len(step_j) else 0.0,
        step_t_us=np.asarray(step_t, dtype=np.int64), step_pos_err_m=np.asarray(step_pe, float),
        step_vel_err_m_s=np.asarray(step_ve, float), step_jerk_xy=step_j, step_accel_xy=step_a,
        frame_pos_err_m=frame_pe, frame_vel_err_m_s=frame_ve, wall_s=wall)
    return MemberSegmentResult(m, 0, True, status, tau_us, p, v, a, None, None, (rec,))


def select_jerk_plan(rows, *, tube_m=0.5):
    """完整合格的测量 rows: [{"jerk":J,"max_error_m":e,"complete":True},...]
    返回 {"triggered":bool,"j_plan":float|None,"reason":str}。

    检查点 1（U D.1.4）：J=2 的最大误差 > tube_m 即触发；恰等于合格。不假设误差随 J 单调：
    J_plan = max{J : e(J) ≤ tube_m}。任一行未完成、或缺 J=2 行，返回 incomplete（不是通过）。"""
    rows = list(rows)
    if not rows or any(not bool(r.get("complete")) for r in rows):
        return {"triggered": False, "j_plan": None, "reason": "incomplete"}
    for r in rows:
        e = r.get("max_error_m")
        if e is None or not math.isfinite(float(e)):
            return {"triggered": False, "j_plan": None, "reason": "incomplete"}
    base = [r for r in rows if float(r["jerk"]) == 2.0]
    if len(base) != 1:
        return {"triggered": False, "j_plan": None, "reason": "incomplete"}
    if float(base[0]["max_error_m"]) > tube_m:
        return {"triggered": True, "j_plan": None, "reason": "j2_exceeds_tube"}
    ok = [float(r["jerk"]) for r in rows if float(r["max_error_m"]) <= tube_m]
    return {"triggered": False, "j_plan": max(ok), "reason": "selected"}
