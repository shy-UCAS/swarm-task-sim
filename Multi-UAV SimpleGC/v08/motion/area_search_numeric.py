"""V8-20 deterministic numeric protocol. No scene I/O, shapely or RNG at import."""
import math
from fractions import Fraction
from numbers import Integral

import numpy as np

INNER_STEP_M = 0.5  # Appendix ruling 2.


def strip_angles(mu_deg, span_deg, n, c):
    if not isinstance(n, Integral) or isinstance(n, bool) or n < 1:
        raise ValueError("member count must be a positive integer")
    if not isinstance(c, Integral) or isinstance(c, bool) or c < 2 or c % 2:
        raise ValueError("strips per member must be even and at least two")
    if not math.isfinite(mu_deg) or not math.isfinite(span_deg) or not 0 < span_deg <= 360:
        raise ValueError("invalid sector angles")
    k = int(n) * int(c)
    return np.radians(float(mu_deg) - float(span_deg)/2 + (np.arange(k) + .5)*float(span_deg)/k)


def first_grid_inner(inner_lower_m, inner_upper_m, outer_xy, points_at_offset, *, min_gap_m=40., min_length_m=60.):
    """First 0.5 m grid offset satisfying the actual endpoint inequalities."""
    lo, hi = float(inner_lower_m), float(inner_upper_m)
    if not np.isfinite([lo, hi]).all() or hi < lo:
        raise ValueError("empty inner offset interval")
    outer = np.asarray(outer_xy, float)
    if outer.ndim != 2 or outer.shape[1] != 2 or len(outer) < 2 or not np.isfinite(outer).all():
        raise ValueError("invalid strip endpoints")
    count = math.floor((hi-lo)/INNER_STEP_M)
    for tick in range(count+1):
        offset = lo + tick*INNER_STEP_M
        if offset > hi:
            break
        inner = np.asarray(points_at_offset(offset), float)
        if inner.shape != outer.shape or not np.isfinite(inner).all():
            raise ValueError("invalid inner contour endpoints")
        gaps = np.linalg.norm(np.diff(inner, axis=0), axis=1)
        lengths = np.linalg.norm(outer-inner, axis=1)
        if np.all(gaps >= min_gap_m) and np.all(lengths >= min_length_m):
            return offset
    raise ValueError("no feasible inner offset on the prescribed grid")


def circle_strip_geometry(base_radius, outer_offset, inner_lower, mu_deg, span_deg, n, c):
    angles = strip_angles(mu_deg, span_deg, n, c)
    if not np.isfinite([base_radius, outer_offset, inner_lower]).all() or base_radius <= 0:
        raise ValueError("invalid circle")
    unit = np.c_[np.cos(angles), np.sin(angles)]
    outer = (float(base_radius)+float(outer_offset))*unit
    points = lambda offset: (float(base_radius)+offset)*unit
    inner = first_grid_inner(inner_lower, float(outer_offset)-60., outer, points)
    return {"inner_offset_m": inner, "inner_xy": points(inner), "outer_xy": outer, "angles_rad": angles}


def scan_vertices(inner, outer, indices):
    inner, outer = np.asarray(inner, float), np.asarray(outer, float)
    ids = list(indices)
    if inner.shape != outer.shape or inner.ndim != 2 or inner.shape[1] != 2:
        raise ValueError("invalid strip endpoints")
    if len(ids) < 2 or len(ids) % 2 or any(not isinstance(k, Integral) for k in ids):
        raise ValueError("a block must have an even number of strips")
    if ids != list(range(ids[0], ids[0]+len(ids))) or ids[0] < 0 or ids[-1] >= len(inner):
        raise ValueError("strip block must be consecutive")
    return np.asarray([p for j,k in enumerate(ids) for p in ((outer[k], inner[k]) if j%2 == 0 else (inner[k], outer[k]))])


def assign_blocks(offsets, slot_order, first_outer, u, formation):
    u = np.asarray(u, float)
    if u.shape != (2,) or not np.isfinite(u).all() or not math.isclose(float(np.linalg.norm(u)), 1.):
        raise ValueError("unit entry direction required")
    order = tuple(slot_order)
    if len(order) != len(set(order)) or set(order) != set(offsets):
        raise ValueError("complete slot identity required")
    first = np.asarray(first_outer, float)
    if first.shape != (len(order), 2):
        raise ValueError("one block per member required")
    n = np.array([-u[1],u[0]])
    blocks = sorted(range(len(order)), key=lambda k: (float(first[k] @ n), k))
    rank = {m: i for i,m in enumerate(order)}
    if formation == "column":
        members = sorted(order, key=lambda m: (-float(offsets[m][0]), rank[m]))
    elif formation in ("abreast", "echelon"):
        members = sorted(order, key=lambda m: (float(offsets[m][1]), float(offsets[m][0]), rank[m]))
    else:
        raise ValueError("loose must first use the existing formation mapping")
    return dict(zip(members, blocks))


def entry_beta_ok(q, center, u):
    radial = np.asarray(center, float)-np.asarray(q, float)
    u = np.asarray(u, float)
    if radial.shape != (2,) or u.shape != (2,) or not np.isfinite([radial,u]).all() or np.linalg.norm(radial) == 0:
        return False
    beta = math.atan2(float(u[0]*radial[1]-u[1]*radial[0]), float(u @ radial))
    return bool(abs(beta) <= math.pi/4)


def draw_hierarchy(entries, rng):
    if not entries:
        raise ValueError("empty area search entry set")
    if any(not sectors or any(not cs for _,cs in sectors) for _,sectors in entries):
        raise ValueError("entries must contain only nonempty conditional sets")
    chord, sectors = entries[int(rng.integers(len(entries)))]
    sector, cs = sectors[int(rng.integers(len(sectors)))]
    c = cs[int(rng.integers(len(cs)))]
    return chord, sector, c


def skeleton_checkpoint_values(success, group_size, attempts, wall_s):
    success, group_size, attempts = list(success), list(group_size), list(attempts)
    if not success or len(success) != len(group_size) or len(success) != len(attempts):
        raise ValueError("complete aligned records required")
    if any(type(x) is not bool for x in success) or any(not isinstance(x, Integral) or x <= 0 for x in attempts):
        raise ValueError("unknown success or attempt count")
    rate = Fraction(sum(success),len(success))
    triggered = []
    if rate < Fraction(95,100):
        triggered.append("success_rate")
    bins = {}
    for lo,hi in ((1,4),(5,8),(9,12)):
        ids = [i for i,n in enumerate(group_size) if lo <= n <= hi]
        if ids:
            bins[f"{lo}-{hi}"] = Fraction(sum(success[i] for i in ids),len(ids))
    if any(rate-f > Fraction(1,10) for f in bins.values()):
        triggered.append("group_gap")
    selected = [a for a,ok in zip(attempts,success) if ok]
    median = float(np.median(selected)) if selected else None
    if median is not None and median > 1:
        triggered.append("attempt_median")
    if wall_s is None or not math.isfinite(wall_s):
        raise ValueError("wall measurement required")
    if wall_s > 1800:
        triggered.append("wall")
    return {"triggered": triggered, "success_rate": float(rate),
            "group_rates": {k:float(v) for k,v in bins.items()}, "attempt_median": median}
