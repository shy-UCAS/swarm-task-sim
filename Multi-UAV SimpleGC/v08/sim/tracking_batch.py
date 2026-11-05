"""按时间跟踪的编组批量版（V8-14c 裁定 3.1–3.2）：与 tracking.run_tracking_segment 逐行对应，只把
"每成员一个 N=1 引擎"改成"一个编组一个 N 行引擎"。冻结核心（InjectableEngine：控制器、对象、采样）按行运算，
各行互不影响；本模块不改 v08/sim/ 已有文件，不改任何引导律、预算、完成判定或输出口径。

逐成员对应关系：
- 结束判定在每步开头：先 t ≥ budget → sim_timeout，否则 holding 且 t ≥ hold_end → ok。单机版先由
  while engine.time_us < budget_us 退出、再在循环内判保持结束，二者同时成立时是 sim_timeout，故批量版按此顺序
  （裁定 3.1.4(a) 文字顺序相反，以"与单机等价"为准）；终态取该时刻 engine.state 第 i 行的拷贝。
- 保持开始判定、逐步诊断量用 math.hypot（与 tracking.py 同一表达式与比较），不改用 np.hypot。
- 期望速度用 NumPy 逐元素计算，运算顺序同 _command：v + tau·a + k·(p_ref − x)，z 为 k·(h − x_z)。
- 成员输出：engine.samples 中 t_us < end_us_i 的帧取第 i 行；记录字段口径同单机；wall_s 为编组总耗时 / 成员数
  （均摊值，TrackingRecord 不加字段，均摊性质由 GROUP_WALL_NOTE 与运行器遥测说明）。
- 参考值：每成员在 20 ms 步网格上一次性对时间数组求 reference.pva，并与逐点标量 _pva 全长 np.array_equal 核验；
  通过才用预计算，否则循环内逐成员标量调用（仍逐位一致）。所用方式与两种耗时记在 LAST_GROUP_STATS。

本模块导入时不读配置、不读场景、不建目录；不导入 shapely。
"""
import math
import time

import numpy as np

from swarm_sim.fast_dynamics.contracts import PlantState

from ..config import load_config
from .kernel import InjectableEngine, member_config
from .tracking import US, TrackingRecord, _check, _pva
from .types import FRAME_US, MemberSegmentResult, SimContractError

GROUP_WALL_NOTE = "wall_s = 编组总耗时 / 成员数（均摊值）"
LAST_GROUP_STATS = {}


def _precompute(reference, grid_us):
    """在步网格（统一时钟 µs）上一次性求 pva，并与逐点标量 _pva 全长逐位核验。返回 (P, V, A) 或 None。"""
    t = grid_us / US
    p, v, a = reference.pva(t)
    P = np.asarray(p, float).reshape(-1, 2)
    V = np.asarray(v, float).reshape(-1, 2)
    A = np.asarray(a, float).reshape(-1, 2)
    for k in range(len(grid_us)):
        ps, vs, as_ = _pva(reference, grid_us[k] / US)
        if not (np.array_equal(ps, P[k]) and np.array_equal(vs, V[k]) and np.array_equal(as_, A[k])):
            return None
    return P, V, A


def run_tracking_group(references, states, *, final=True, guidance=None, sim=None, use_precomputed_reference=None):
    """references、states 一一对应（同一编组、第 0 段、统一时钟）。返回与输入顺序一致的 MemberSegmentResult 列表，
    每个元素与 run_tracking_segment 的返回同构。use_precomputed_reference：None = 核验通过才用；False = 一律标量；
    True = 要求使用预计算（核验不过则抛 SimContractError）。"""
    if not final:
        raise SimContractError("本项只支持 final=True")
    refs, sts = list(references), list(states)
    if len(refs) != len(sts) or not refs:
        raise SimContractError("references 与 states 须一一对应且非空")
    G = (guidance if guidance is not None else load_config("guidance")).values
    S = (sim if sim is not None else load_config("sim")).values
    for ref, st in zip(refs, sts):
        _check(ref, st, S)
    n = len(refs)
    cfg = member_config()
    tau = cfg.controller.velocity_response_time_s
    k = G["k_pos_per_s"]
    a_cap = cfg.vehicle_profile.max_accel_xy_m_s2
    j_cap = cfg.vehicle_profile.max_jerk_m_s3
    step_us = int(cfg.engine.step_us)
    tau0 = 0
    hold_s = S["terminal_hold_s"]
    hold_us = int(round(hold_s * 10.0)) * FRAME_US
    rel_us, T, budget_s, budget_us, alt = [], [], [], [], []
    for ref in refs:
        r = float(ref.release_s)
        Ti = float(ref.end_s)
        bs = (Ti - r) * (1.0 + G["budget_factor"]) + G["budget_const_s"] + r + hold_s
        rel_us.append(int(round(r * 10.0)) * FRAME_US)
        T.append(Ti)
        budget_s.append(bs)
        budget_us.append(math.ceil(bs * 10.0) * FRAME_US)
        alt.append(float(ref.altitude_m))
    P0 = np.array([np.asarray(st.p, dtype=float) for st in sts]).reshape(n, 3)
    V0 = np.array([np.asarray(st.v, dtype=float) for st in sts]).reshape(n, 3)
    A0 = np.array([np.asarray(st.a, dtype=float) for st in sts]).reshape(n, 3)
    engine = InjectableEngine(cfg, PlantState(P0, V0, A0), None, tau0)

    # 3.2 参考值：预计算 + 全长逐位核验
    t_pre = time.perf_counter()
    pre = [None] * n
    mode = "scalar"
    if use_precomputed_reference is not False:
        ok_all = True
        for i, ref in enumerate(refs):
            grid = np.arange(0, budget_us[i], step_us, dtype=np.int64)
            got = _precompute(ref, grid)
            if got is None:
                ok_all = False
                pre = [None] * n
                break
            pre[i] = got
        if ok_all:
            mode = "precomputed"
        elif use_precomputed_reference is True:
            raise SimContractError("预计算参考与逐点 _pva 不逐位一致")
    precompute_s = time.perf_counter() - t_pre

    alt_v = np.asarray(alt, float)
    step_t = [[] for _ in range(n)]
    step_pe = [[] for _ in range(n)]
    step_ve = [[] for _ in range(n)]
    step_a = [[] for _ in range(n)]
    step_j = [[] for _ in range(n)]
    status = ["sim_timeout"] * n
    holding = [False] * n
    hold_end = [None] * n
    hold_start = [None] * n
    done = [False] * n
    end_us = [None] * n
    end_state = [None] * n
    bmax = max(budget_us)
    Pr = np.empty((n, 2))
    Vr = np.empty((n, 2))
    Ar = np.empty((n, 2))
    started = time.perf_counter()
    while engine.time_us < bmax:
        t = engine.time_us
        x = engine.state
        for i in range(n):
            if done[i]:
                continue
            if t >= budget_us[i]:                       # 单机 while engine.time_us < budget_us 先判
                status[i], done[i] = "sim_timeout", True
            elif holding[i] and t >= hold_end[i]:
                status[i], done[i] = "ok", True
            if done[i]:
                end_us[i] = t
                end_state[i] = (x.p[i].copy(), x.v[i].copy(), x.a[i].copy())
        if all(done):
            break
        t_abs_us = tau0 + t
        kk = t // step_us
        for i in range(n):
            if done[i]:
                continue                                 # 已结束成员：沿用上一步参考（命令照算、不输出）
            if pre[i] is not None:
                Pr[i], Vr[i], Ar[i] = pre[i][0][kk], pre[i][1][kk], pre[i][2][kk]
            else:
                Pr[i], Vr[i], Ar[i] = _pva(refs[i], t_abs_us / US)
        for i in range(n):
            if done[i]:
                continue
            xp, xv = x.p[i], x.v[i]
            p_ref, v_ref = Pr[i], Vr[i]
            step_t[i].append(t)
            step_pe[i].append(math.hypot(p_ref[0] - xp[0], p_ref[1] - xp[1]))
            step_ve[i].append(math.hypot(v_ref[0] - xv[0], v_ref[1] - xv[1]))
            step_a[i].append(math.hypot(x.a[i][0], x.a[i][1]))
            if (not holding[i] and t_abs_us / US >= T[i]
                    and math.hypot(p_ref[0] - xp[0], p_ref[1] - xp[1]) <= S["terminal_radius_m"]
                    and math.hypot(xv[0], xv[1]) <= S["terminal_speed_m_s"]):
                holding[i] = True
                hold_start[i] = t_abs_us
                hold_end[i] = t + hold_us
        xs_p = np.asarray(x.p, float)
        U = np.empty((n, 3))
        U[:, 0] = Vr[:, 0] + tau * Ar[:, 0] + k * (Pr[:, 0] - xs_p[:, 0])
        U[:, 1] = Vr[:, 1] + tau * Ar[:, 1] + k * (Pr[:, 1] - xs_p[:, 1])
        U[:, 2] = k * (alt_v - xs_p[:, 2])
        engine.step(U)
        lj = engine.last_jerk
        for i in range(n):
            if not done[i]:
                step_j[i].append(math.hypot(lj[i][0], lj[i][1]))
    for i in range(n):          # 循环因到达 bmax 退出：尚未结束的成员按单机 while 条件超时
        if not done[i]:
            x = engine.state
            status[i], done[i], end_us[i] = "sim_timeout", True, engine.time_us
            end_state[i] = (x.p[i].copy(), x.v[i].copy(), x.a[i].copy())
    wall = time.perf_counter() - started
    LAST_GROUP_STATS.clear()
    LAST_GROUP_STATS.update(reference_mode=mode, precompute_s=precompute_s, loop_s=wall, members=n,
                            steps=int(engine.time_us // step_us))

    samples = engine.samples
    s_t = np.array([sv.t_us for sv in samples], dtype=np.int64)
    out = []
    for i, ref in enumerate(refs):
        sel = np.flatnonzero(s_t < end_us[i])
        tau_us = tau0 + s_t[sel]
        p = np.array([samples[j].p[i] for j in sel], dtype=float).reshape(-1, 3)
        v = np.array([samples[j].v[i] for j in sel], dtype=float).reshape(-1, 3)
        a = np.array([samples[j].a[i] for j in sel], dtype=float).reshape(-1, 3)
        fp, fv, _ = ref.pva(tau_us / US)
        fp = np.asarray(fp, float).reshape(-1, 2)
        fv = np.asarray(fv, float).reshape(-1, 2)
        frame_pe = np.hypot(fp[:, 0] - p[:, 0], fp[:, 1] - p[:, 1])
        frame_ve = np.hypot(fv[:, 0] - v[:, 0], fv[:, 1] - v[:, 1])
        sj = np.asarray(step_j[i][:len(step_t[i])], float)
        sa = np.asarray(step_a[i], float)
        ep, ev, ea = end_state[i]
        rec = TrackingRecord(
            tau_start_us=tau0, tau_end_us=tau0 + end_us[i], release_us=rel_us[i], motion_end_s=T[i],
            hold_start_us=hold_start[i], budget_s=budget_s[i],
            end_p=tuple(float(c) for c in ep), end_v=tuple(float(c) for c in ev), end_a=tuple(float(c) for c in ea),
            max_step_pos_err_m=float(max(step_pe[i])) if step_pe[i] else 0.0,
            max_step_vel_err_m_s=float(max(step_ve[i])) if step_ve[i] else 0.0,
            max_frame_pos_err_m=float(frame_pe.max()) if len(frame_pe) else 0.0,
            max_frame_vel_err_m_s=float(frame_ve.max()) if len(frame_ve) else 0.0,
            accel_saturated_fraction=float(np.mean(sa >= a_cap * (1.0 - 1e-9))) if len(sa) else 0.0,
            jerk_saturated_fraction=float(np.mean(sj >= j_cap * (1.0 - 1e-9))) if len(sj) else 0.0,
            step_t_us=np.asarray(step_t[i], dtype=np.int64), step_pos_err_m=np.asarray(step_pe[i], float),
            step_vel_err_m_s=np.asarray(step_ve[i], float), step_jerk_xy=sj, step_accel_xy=sa,
            frame_pos_err_m=frame_pe, frame_vel_err_m_s=frame_ve, wall_s=wall / n)
        out.append(MemberSegmentResult(ref.member_id, 0, True, status[i], tau_us, p, v, a, None, None, (rec,)))
    return out
