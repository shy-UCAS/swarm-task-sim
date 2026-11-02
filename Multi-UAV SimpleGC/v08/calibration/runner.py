"""标定运行器（V8-06 2.4）：通过 V8-04 适配层调用冻结仿真器。

allow_continuation_extension() 只在 with 块内临时放开"延伸段必须共线"的检查，
用于测量沿实际后续航线延伸的效果；只用于本任务的标定，不进入生产代码。
"""
import dataclasses
from contextlib import contextmanager

import numpy as np

import v08.sim.adapter as _adapter
from v08.config import load_config
from v08.sim.adapter import ALT_TOL_M, append_extension, run_member_segment
from v08.sim.types import MemberBoundaryState, MemberPiece, MemberSegmentPlan, SimContractError

MEMBER = "m"


def config_with(**over):
    base = load_config("sim")
    unknown = set(over) - set(base.values)
    if unknown:
        raise KeyError(f"sim 配置中没有参数 {sorted(unknown)}")
    return dataclasses.replace(base, values={**base.values, **{k: float(v) for k, v in over.items()}})


def _points(W):
    return tuple(tuple(float(x) for x in p) for p in W)


def _initial_state(W):
    return MemberBoundaryState(MEMBER, 0, 0, W[0], (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


def fly(W, speed, *, config=None):
    W = _points(W)
    plan = MemberSegmentPlan(MEMBER, 0, (MemberPiece(W, len(W) - 1, speed),))
    return run_member_segment(plan, _initial_state(W), final=True, config=config)


def _leg(a, b):
    return float(np.hypot(b[0] - a[0], b[1] - a[1]))


def continuation_piece_waypoints(W, E, ext_len):
    W = _points(W)
    acc = 0.0
    for k in range(E + 1, len(W)):
        acc += _leg(W[k - 1], W[k])
        if acc >= ext_len - 1e-9:
            return W[:k + 1]
    return append_extension(W, ext_len - acc)


@contextmanager
def allow_continuation_extension():
    original = _adapter._check_piece

    def check(j, piece, needs_extension, cfg):
        if not needs_extension:
            return original(j, piece, needs_extension, cfg)
        W = piece.waypoints
        e = piece.end_index
        n = len(W)
        if isinstance(e, bool) or not isinstance(e, (int, np.integer)) or not 1 <= e <= n - 2:
            raise SimContractError(f"小段 {j}: end_index {e} 不在 [1, {n - 2}]（需要延伸段）")
        original(j, MemberPiece(append_extension(W[:e + 1], cfg["extension_length_m"]), e, piece.speed_m_s),
                 True, cfg)
        w = np.asarray(W, dtype=float)
        tail = w[e:]
        if not np.all(np.isfinite(tail)):
            raise SimContractError(f"小段 {j}: 延伸段含非有限值")
        if float(w[:, 2].max() - w[:, 2].min()) > ALT_TOL_M:
            raise SimContractError(f"小段 {j}: 高度不恒定")
        legs = np.linalg.norm(np.diff(tail[:, :2], axis=0), axis=1)
        if np.any(legs == 0.0):
            raise SimContractError(f"小段 {j}: 延伸段有平面长度为 0 的腿")
        if float(legs.sum()) < cfg["extension_length_m"] - 1e-9:
            raise SimContractError(f"小段 {j}: 延伸段总长 {float(legs.sum())} m 小于 {cfg['extension_length_m']} m")

    _adapter._check_piece = check
    try:
        yield
    finally:
        _adapter._check_piece = original


def fly_split(W, E, v1, v2, *, mode, config=None):
    cfg = config if config is not None else load_config("sim")
    W = _points(W)
    L_e = cfg.values["extension_length_m"]
    if mode == "straight":
        first = append_extension(W[:E + 1], L_e)
    elif mode == "continuation":
        first = continuation_piece_waypoints(W, E, L_e)
    else:
        raise ValueError(f"mode 应为 straight 或 continuation，实际 {mode!r}")
    rest = W[E:]
    plan = MemberSegmentPlan(MEMBER, 0, (MemberPiece(first, E, v1), MemberPiece(rest, len(rest) - 1, v2)))
    if mode == "continuation":
        with allow_continuation_extension():
            return run_member_segment(plan, _initial_state(W), final=True, config=cfg)
    return run_member_segment(plan, _initial_state(W), final=True, config=cfg)


def compare_runs(a, b, tau_from_us, tau_to_us):
    ta = np.asarray(a.tau_us)
    sel = (ta >= tau_from_us) & (ta <= tau_to_us)
    common, ia, ib = np.intersect1d(ta[sel], np.asarray(b.tau_us), return_indices=True)
    if len(common) == 0:
        return None
    ia = np.flatnonzero(sel)[ia]
    dp = np.linalg.norm(np.asarray(a.p)[ia, :2] - np.asarray(b.p)[ib, :2], axis=1)
    dv = np.linalg.norm(np.asarray(a.v)[ia, :2] - np.asarray(b.v)[ib, :2], axis=1)
    return {"dp_max": float(dp.max()), "dv_max": float(dv.max()),
            "dp_first": float(dp[0]), "dv_first": float(dv[0])}
