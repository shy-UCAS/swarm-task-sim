"""V8-14 诊断（指令 4.3、5.1；附录裁定 7）：阶段速度与沿迹偏离、巡逻段裁切重采样。只用 NumPy，不导入 shapely，
不复制冻结核验器；只作诊断，不改标签、段核验窗口或任何门禁。

阶段最低速度（裁定 7）：只在参考速度 ≥ 0.5 m/s 的样本上统计（0.5 m/s 为判据有效观测速度
configs/criteria coverage.effective_speed_min_m_s / revisit.min_speed_m_s），端点起停不计；该阶段没有这样的样本
时比值为 None（原因 no_moving_reference_samples）。全部样本（含起停）的参考最低速度另作诊断字段。
"""
import math

import numpy as np

PHASES = ("collect_ingress", "patrol", "egress")


def _min_reference_speed():
    from task_v07.criteria import load_criteria
    return float(load_criteria()["detectors"]["coverage"]["effective_speed_min_m_s"])


def _speed(v):
    v = np.asarray(v, float)
    return np.hypot(v[:, 0], v[:, 1])


def phase_metrics(t, reference_p, reference_v, optimized_p, optimized_v, measured_p, measured_v, phase_bounds,
                  reference_tangent, *, min_reference_speed_m_s=None):
    """逐阶段：参考/优化/实测最低速度（参考速度 ≥ v_eff 的同一批样本）、优化/实测 ÷ 参考比值，以及
    max_t |(p − p_ref)·t̂_ref| 的一维沿迹投影。phase_bounds[name] = (a, b) 半开 [a, b) 或 (a, b, True) 闭区间。
    optimized_*/measured_* 可为 None（该来源缺测时对应量为 None）。"""
    vmin = _min_reference_speed() if min_reference_speed_m_s is None else float(min_reference_speed_m_s)
    t = np.asarray(t, float)
    rp, rv = np.asarray(reference_p, float), np.asarray(reference_v, float)
    tan = np.asarray(reference_tangent, float)
    tan = tan / np.maximum(np.hypot(tan[:, 0], tan[:, 1]), np.finfo(float).tiny)[:, None]
    src = {"optimized": (optimized_p, optimized_v), "measured": (measured_p, measured_v)}
    out = {}
    rs = _speed(rv)
    for name, bound in phase_bounds.items():
        a, b = float(bound[0]), float(bound[1])
        closed = len(bound) > 2 and bool(bound[2])
        sel = (t >= a) & ((t <= b) if closed else (t < b))
        moving = sel & (rs >= vmin)
        rec = {"n_samples": int(sel.sum()), "n_moving": int(moving.sum()),
               "reference_min_all_samples_m_s": float(rs[sel].min()) if sel.any() else None,
               "reference_min_m_s": float(rs[moving].min()) if moving.any() else None,
               "ratio_reason": None if moving.any() else "no_moving_reference_samples",
               "min_reference_speed_m_s": vmin}
        for key, (p, v) in src.items():
            if p is None or v is None or not sel.any():
                rec[f"{key}_min_m_s"] = None
                rec[f"{key}_ratio"] = None
                rec[f"{key}_along_max_m"] = None
                continue
            p, v = np.asarray(p, float), np.asarray(v, float)
            along = np.abs(np.sum((p[sel] - rp[sel]) * tan[sel], axis=1))
            rec[f"{key}_along_max_m"] = float(along.max())
            k = int(np.argmax(along))
            rec[f"{key}_along_worst_t_s"] = float(t[sel][k])
            if moving.any():
                ms = _speed(v)[moving]
                rec[f"{key}_min_m_s"] = float(ms.min())
                rec[f"{key}_ratio"] = float(ms.min()) / rec["reference_min_m_s"]
            else:
                rec[f"{key}_min_m_s"] = None
                rec[f"{key}_ratio"] = None
        out[name] = rec
    return out


def patrol_resample(reference_s, xy, start_s, end_s, *, spacing_m=5.0):
    """先按 reference_s 裁切到 [start_s, end_s] 并精确插入两端点，再按裁切后折线自身的累计弧长每 spacing_m 采样，
    补尾端点。只为插值去重剔除零长度相邻弦，不裁掉非零路径。"""
    s = np.asarray(reference_s, float)
    p = np.asarray(xy, float)
    if not (start_s < end_s):
        raise ValueError("巡逻段裁切区间为空")
    a = np.array([np.interp(start_s, s, p[:, 0]), np.interp(start_s, s, p[:, 1])])
    b = np.array([np.interp(end_s, s, p[:, 0]), np.interp(end_s, s, p[:, 1])])
    inner = (s > start_s) & (s < end_s)
    pts = np.vstack([a, p[inner], b])
    seg = np.hypot(*np.diff(pts, axis=0).T)
    keep = np.r_[True, seg > 0.0]
    pts = pts[keep]
    if len(pts) < 2:
        return pts.copy()
    cum = np.r_[0.0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
    L = float(cum[-1])
    n = int(math.floor(L / float(spacing_m) + 1e-12))
    st = float(spacing_m) * np.arange(n + 1)
    if st[-1] < L:
        st = np.r_[st, L]
    return np.stack([np.interp(st, cum, pts[:, 0]), np.interp(st, cum, pts[:, 1])], axis=1)


def endpoint_distances(curve_a, curve_b):
    """巡逻段起点距离、终点距离及两者最大值（单独报告，不从 Fréchet 中扣除）。"""
    a, b = np.asarray(curve_a, float), np.asarray(curve_b, float)
    d0 = float(np.hypot(*(a[0] - b[0])))
    d1 = float(np.hypot(*(a[-1] - b[-1])))
    return {"start_m": d0, "end_m": d1, "max_m": max(d0, d1)}
