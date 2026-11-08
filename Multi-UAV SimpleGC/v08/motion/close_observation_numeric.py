"""Pure numerical V8-19 dwell stations and discrete sampling; no shapely dependency."""
import math

import numpy as np

from ..scene.exact import signed_distance

DWELL_STEP_M = 5.0
DWELL_LAYER_MARGIN_M = 12.5


def dwell_grid(s_from, s_to):
    start, end = float(s_from), float(s_to)
    if not np.isfinite([start, end]).all():
        raise ValueError("station interval must be finite")
    if end < start:
        return np.zeros(0, float)
    count = math.floor((end - start) / DWELL_STEP_M) + 1
    out = start + DWELL_STEP_M * np.arange(count)
    return out[out <= end]


def dwell_condition_masks(stations, member_s, points, semantic_ranges, warning, alert, base):
    stations = np.asarray(stations, float)
    if stations.ndim != 1 or not np.isfinite(stations).all():
        raise ValueError("stations must be a finite one-dimensional array")
    if not member_s or set(member_s) != set(points):
        raise ValueError("dwell candidates require the complete identical member set")
    n = len(stations)
    conditions = {name: np.ones(n, bool) for name in ("finite", "semantic", "warning", "alert", "base")}
    for mid in sorted(member_s):
        ss, xy = np.asarray(member_s[mid], float), np.asarray(points[mid], float)
        if ss.shape != (n,) or xy.shape != (n, 2):
            raise ValueError(f"candidate array shape differs for {mid}")
        conditions["finite"] &= np.isfinite(ss) & np.isfinite(xy).all(axis=1)
        for lower, upper in semantic_ranges.get(mid, ()):
            conditions["semantic"] &= ~((ss >= float(lower)) & (ss <= float(upper)))
        conditions["warning"] &= signed_distance(warning, xy) <= -DWELL_LAYER_MARGIN_M
        conditions["alert"] &= signed_distance(alert, xy) >= DWELL_LAYER_MARGIN_M
        for constraint in base:
            sdf = np.asarray(signed_distance(constraint.geometry, xy), float)
            sense, minimum = int(constraint.sense), float(constraint.minimum_m)
            if sense == 1:
                margin = sdf - minimum
            elif sense == -1:
                margin = -sdf - minimum
            elif sense == 0:
                margin = np.abs(sdf) - minimum
            else:
                raise ValueError("unsupported clearance sense")
            conditions["base"] &= margin >= 0.0
    return conditions


def admissible_dwell_mask(stations, member_s, points, semantic_ranges, warning, alert, base):
    conditions = dwell_condition_masks(stations, member_s, points, semantic_ranges, warning, alert, base)
    return np.logical_and.reduce(list(conditions.values()))


def draw_dwell(stations, rng):
    stations = np.asarray(stations, float)
    if stations.ndim != 1 or not len(stations) or not np.isfinite(stations).all() or np.any(np.diff(stations) <= 0.0):
        raise ValueError("dwell station set must be finite, nonempty, unique and sorted")
    index = int(rng.integers(0, len(stations)))
    ticks = int(rng.integers(200, 1201))
    return float(stations[index]), ticks / 10.0
