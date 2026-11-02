"""逐成员分段仿真（r3 8.2–8.3）：把一个成员一段内的速度小段依次交给冻结的单机仿真器，
小段之间从 (p, v, a) 续跑，结果放到编组统一时钟上。只调用冻结仿真器，不改它的任何文件。
"""
import math
import time
from contextlib import contextmanager

import numpy as np

import task_v07.execution as _execution
from swarm_sim.fast_dynamics.route_tracker import RouteTracker

from ..config import load_config
from .types import (FRAME_US, MemberBoundaryState, MemberSegmentResult, PieceRecord, SimContractError,
                    TimelineInconsistent)

MAX_SPEED_XY_M_S = 12.0   # r3 配置 max_speed_xy_m_s
ALT_TOL_M = 1e-9
FIRST_START_TOL_M = 1e-6
DIRECTION_TOL = 1e-12
REFERENCE_VERSION = "r3"


# ---------------------------------------------------------------- 4.1 记录跟踪器的经过时刻

class _RecordingRouteTracker(RouteTracker):
    """与冻结 RouteTracker 唯一的区别：构造后把自己登记到 registry。"""
    registry = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if _RecordingRouteTracker.registry is not None:
            _RecordingRouteTracker.registry.append(self)


@contextmanager
def recording_trackers():
    """调用期间把 task_v07.execution.RouteTracker 换成记录子类，结束时无条件还原。"""
    if _execution.RouteTracker is not RouteTracker:
        raise RuntimeError("task_v07.execution.RouteTracker 不是冻结的 RouteTracker（不允许嵌套使用）")
    registry = []
    try:
        _RecordingRouteTracker.registry = registry
        _execution.RouteTracker = _RecordingRouteTracker
        yield registry
    finally:
        _execution.RouteTracker = RouteTracker
        _RecordingRouteTracker.registry = None


def execute_recorded(skeleton, delays_s, *, only_agent):
    with recording_trackers() as registry:
        run = _execution.execute(skeleton, delays_s, only_agent=only_agent, reference_version=REFERENCE_VERSION)
    if len(registry) != 1:
        raise RuntimeError(f"应登记恰好 1 个跟踪器，实际 {len(registry)} 个")
    return run, [dict(w) for w in registry[0].witnesses]


# ---------------------------------------------------------------- 4.2 延伸段

def _unit_xy(a, b):
    d = np.asarray(b[:2], dtype=float) - np.asarray(a[:2], dtype=float)
    n = float(np.linalg.norm(d))
    return d / n if n > 0.0 else None


def append_extension(waypoints, length_m):
    pts = [tuple(float(x) for x in p) for p in waypoints]
    u = _unit_xy(pts[-2], pts[-1])
    if u is None:
        raise SimContractError("最后一条腿长度为 0，无法延伸")
    last = pts[-1]
    pts.append((last[0] + length_m * float(u[0]), last[1] + length_m * float(u[1]), last[2]))
    return tuple(pts)


# ---------------------------------------------------------------- 4.3 输入检查

def _check_piece(j, piece, needs_extension, cfg):
    w = np.asarray(piece.waypoints, dtype=float)
    if w.ndim != 2 or w.shape[0] < 2 or w.shape[1] != 3:
        raise SimContractError(f"小段 {j}: waypoints 形状应为 (n>=2, 3)，实际 {w.shape}")
    if not np.all(np.isfinite(w)):
        raise SimContractError(f"小段 {j}: waypoints 含非有限值")
    if float(w[:, 2].max() - w[:, 2].min()) > ALT_TOL_M:
        raise SimContractError(f"小段 {j}: 高度不恒定")
    legs = np.linalg.norm(np.diff(w[:, :2], axis=0), axis=1)
    if np.any(legs == 0.0):
        raise SimContractError(f"小段 {j}: 有平面长度为 0 的腿")
    speed = piece.speed_m_s
    if isinstance(speed, bool) or not math.isfinite(speed) or not 0.0 < speed <= MAX_SPEED_XY_M_S:
        raise SimContractError(f"小段 {j}: 速度 {speed} 不在 (0, {MAX_SPEED_XY_M_S}]")
    n = w.shape[0]
    e = piece.end_index
    if not isinstance(e, (int, np.integer)) or not 1 <= e <= n - 1:
        raise SimContractError(f"小段 {j}: end_index {e} 不在 [1, {n - 1}]")
    if not needs_extension:
        if e != n - 1:
            raise SimContractError(f"小段 {j}: 不需要延伸段时 end_index 应为 {n - 1}")
        return
    if e > n - 2:
        raise SimContractError(f"小段 {j}: 缺少延伸段（end_index={e}，航点数 {n}）")
    u = _unit_xy(w[e - 1], w[e])
    for i in range(e, n - 1):
        if float(np.dot(_unit_xy(w[i], w[i + 1]), u)) < 1.0 - DIRECTION_TOL:
            raise SimContractError(f"小段 {j}: 延伸段腿 {i}->{i + 1} 与来向不共线")
    if float(legs[e:].sum()) < cfg["extension_length_m"] - 1e-9:
        raise SimContractError(f"小段 {j}: 延伸段总长 {float(legs[e:].sum())} m 小于 {cfg['extension_length_m']} m")


def _check_inputs(plan, state, final, cfg):
    if plan.member_id != state.member_id or plan.segment_index != state.segment_index:
        raise SimContractError("plan 与 state 的成员或段号不一致")
    if not plan.pieces:
        raise SimContractError("plan.pieces 为空")
    tau = state.tau_us
    if isinstance(tau, bool) or not isinstance(tau, (int, np.integer)) or tau < 0 or tau % FRAME_US:
        raise SimContractError(f"state.tau_us={tau} 不是非负的 {FRAME_US} µs 整数倍")
    if plan.segment_index == 0 and tau != 0:
        raise SimContractError("第 0 段必须从 tau_us=0 开始")
    d = float(plan.release_delay_s)
    if plan.segment_index != 0 and d != 0.0:
        raise SimContractError("非第 0 段不得有出发延迟")
    if not math.isfinite(d) or d < 0.0 or abs(d * 10.0 - round(d * 10.0)) > 1e-7:
        raise SimContractError(f"出发延迟 {d} 无效或不在 10 Hz 网格上")
    last = len(plan.pieces) - 1
    for j, piece in enumerate(plan.pieces):
        _check_piece(j, piece, not (final and j == last), cfg)


def _piece_route(j, piece, p, first_of_sample, cfg):
    """返回本小段交给仿真器的航线；续跑小段把第 0 点平面坐标换成当前位置。"""
    w = np.asarray(piece.waypoints, dtype=float).copy()
    dist = float(np.linalg.norm(w[0, :2] - np.asarray(p[:2], dtype=float)))
    if first_of_sample:
        if dist > FIRST_START_TOL_M:
            raise SimContractError(f"小段 {j}: 起点与初始位置平面距离 {dist} m")
        return w
    if dist > cfg["join_max_distance_m"]:
        raise SimContractError(f"小段 {j}: 续跑起点与计划起点相距 {dist} m > {cfg['join_max_distance_m']} m")
    w[0, :2] = np.asarray(p[:2], dtype=float)
    if float(np.linalg.norm(w[1, :2] - w[0, :2])) == 0.0:
        raise SimContractError(f"小段 {j}: 替换起点后第一条腿长度为 0")
    return w


# ---------------------------------------------------------------- 4.3 执行

def _skeleton(member, route, p, v, a, speed, settle_s, cfg):
    return {
        "agent_ids": [member],
        "initial_states": [{"agent_id": member,
                            "position_enu_m": [float(x) for x in p],
                            "velocity_enu_m_s": [float(x) for x in v],
                            "acceleration_enu_m_s2": [float(x) for x in a]}],
        "references": {member: {"points_enu_m": [[float(x) for x in q] for q in route]}},
        "cruise_speed_m_s": float(speed),
        "initial_settle_s": float(settle_s),
        "terminal_radius_m": cfg["terminal_radius_m"],
        "terminal_speed_m_s": cfg["terminal_speed_m_s"],
        "terminal_hold_s": cfg["terminal_hold_s"],
    }


def run_member_segment(plan, state, *, final, config=None):
    cfg = (config if config is not None else load_config("sim")).values
    _check_inputs(plan, state, final, cfg)
    m = plan.member_id
    p, v, a = state.p, state.v, state.a
    tau0 = int(state.tau_us)
    last = len(plan.pieces) - 1
    status = "ok"
    taus, ps, vs, as_, records = [], [], [], [], []
    crossing_tau = None
    for j, piece in enumerate(plan.pieces):
        first_of_sample = plan.segment_index == 0 and j == 0
        route = _piece_route(j, piece, p, first_of_sample, cfg)
        sk = _skeleton(m, route, p, v, a, piece.speed_m_s, cfg["initial_settle_s"] if first_of_sample else 0.0, cfg)
        delays = {m: float(plan.release_delay_s) if first_of_sample else 0.0}
        started = time.perf_counter()
        run, witnesses = execute_recorded(sk, delays, only_agent=m)
        wall = time.perf_counter() - started
        t = np.asarray(run["time_us"], dtype=np.int64)
        rp = np.asarray(run["p"], dtype=float)[:, 0]
        rv = np.asarray(run["v"], dtype=float)[:, 0]
        ra = np.asarray(run["a"], dtype=float)[:, 0]
        exec_status = run["execution_status"]
        t_w = k_star = None
        stop = False
        if final and j == last:
            keep = len(t)
            if exec_status != "completed":
                status = "sim_timeout"
        else:
            e = piece.end_index
            hits = [w["t_us"] for w in witnesses if w["node_index"] == e]
            if hits:
                t_w = int(hits[0])
                u = _unit_xy(route[e - 1], route[e])
                ahead = (rp[:, :2] - route[e, :2]) @ u >= 0.0
                cand = np.flatnonzero((t >= t_w) & ahead)
                if len(cand):
                    k_star = int(cand[0])
            if k_star is None:
                if exec_status != "timeout":
                    raise TimelineInconsistent(
                        f"成员 {m} 第 {plan.segment_index} 段小段 {j}：仿真状态 {exec_status}，"
                        f"但找不到经过记录或越过帧（t_w={t_w}）")
                status = "sim_timeout"
                keep = len(t)
                stop = True
            else:
                keep = k_star
        taus.append(tau0 + t[:keep])
        ps.append(rp[:keep])
        vs.append(rv[:keep])
        as_.append(ra[:keep])
        tau_end = tau0 + int(t[k_star]) if k_star is not None else (tau0 + int(t[keep - 1]) if keep else tau0)
        records.append(PieceRecord(float(piece.speed_m_s), tau0, tau_end, t_w, k_star, exec_status,
                                   int(len(t) - keep), wall))
        if stop:
            break
        if k_star is not None:
            p, v, a = (tuple(float(x) for x in arr[k_star]) for arr in (rp, rv, ra))
            tau0 = tau_end
            crossing_tau = tau_end
    end_state = switch = None
    if not final and status == "ok":
        switch = crossing_tau
        end_state = MemberBoundaryState(m, plan.segment_index + 1, switch, p, v, a)
    return MemberSegmentResult(
        member_id=m, segment_index=plan.segment_index, final=bool(final), status=status,
        tau_us=np.concatenate(taus).astype(np.int64), p=np.concatenate(ps), v=np.concatenate(vs),
        a=np.concatenate(as_), end_state=end_state, executed_switch_tau_us=switch, pieces=tuple(records))
