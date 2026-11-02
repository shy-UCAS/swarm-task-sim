"""标定度量（V8-06 2.3）：速度、稳态帧掩码、冲出距离、极坐标进度与冻结驻留检测器的调用。"""
import math

import numpy as np

from task_v07.detectors import dwell

from .geometry import arc_relative_angle


def speed_xy(v):
    return np.linalg.norm(np.asarray(v, dtype=float)[:, :2], axis=1)


def arc_steady_mask(xy, center, R, theta0, dtheta, margin_deg=15.0, max_dist=2.0):
    xy = np.asarray(xy, dtype=float)[:, :2]
    rel = arc_relative_angle(xy, center, theta0, dtheta)
    m = math.radians(margin_deg)
    in_arc = (rel >= m) & (rel <= abs(dtheta) - m)
    near = np.abs(np.linalg.norm(xy - np.asarray(center, dtype=float), axis=1) - R) <= max_dist
    return in_arc & near


def overshoot_along(xy, end_point, direction):
    xy = np.asarray(xy, dtype=float)[:, :2]
    u = np.asarray(direction, dtype=float)
    u = u / np.linalg.norm(u)
    return max(0.0, float(np.max((xy - np.asarray(end_point, dtype=float)) @ u)))


def polar_progress(xy, phi0):
    xy = np.asarray(xy, dtype=float)[:, :2]
    ang = np.unwrap(np.arctan2(xy[:, 1], xy[:, 0])) - phi0
    return ang - 2.0 * math.pi * round(float(ang[0]) / (2.0 * math.pi))


def away_from(xy, point, radius):
    xy = np.asarray(xy, dtype=float)[:, :2]
    return np.linalg.norm(xy - np.asarray(point, dtype=float)[:2], axis=1) > radius


def dwell_result(xy, time_us, release_us, extra_mask=None):
    """冻结检测器 criteria/0.7-r1 的完整返回值；只看释放后（且满足附加掩码）的帧。"""
    time_us = np.asarray(time_us)
    frames = time_us >= release_us
    if extra_mask is not None:
        frames = frames & np.asarray(extra_mask, dtype=bool)
    return dwell(np.asarray(xy, dtype=float)[:, :2], time_us, frames)


def dwell_detected(xy, time_us, release_us, extra_mask=None):
    return bool(dwell_result(xy, time_us, release_us, extra_mask)["detected"])
