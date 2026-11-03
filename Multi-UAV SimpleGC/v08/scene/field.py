"""距离场与保守可行集合（V8-12 第 2 部分；r4 6.4）。

每个约束的有符号距离在 spacing_m 栅格的顶点上精确计算（exact.py），点上的值用双线性插值。
有符号距离是 1-Lipschitz 的，双线性插值误差不超过半对角线 eps = hypot(h, h) / 2，
因此"插值值 − eps ≥ 0"只会保守地收缩可行集合。栅格外的点一律不可行，不外推。
只用 NumPy。
"""
import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from .exact import SENSES, GeometryError, clearance_values, signed_distance

_BLOCK = 200_000


@dataclass(frozen=True)
class Clearance:
    name: str
    geometry: dict
    sense: int                 # +1 要在外部，-1 要在内部，0 要离边界至少 minimum_m
    minimum_m: float


def geometry_key(geometry):
    text = json.dumps(geometry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _transform(raw, sense, minimum_m):
    if sense == 0:
        return np.abs(raw) - minimum_m
    return sense * raw - minimum_m


def sdf_grid(geometry, xs, ys):
    """在顶点网格 (len(ys), len(xs)) 上精确计算有符号距离。"""
    X, Y = np.meshgrid(xs, ys)
    pts = np.stack([X.ravel(), Y.ravel()], axis=1)
    out = np.empty(len(pts))
    for lo in range(0, len(pts), _BLOCK):
        out[lo:lo + _BLOCK] = signed_distance(geometry, pts[lo:lo + _BLOCK])
    return out.reshape(len(ys), len(xs))


class _Values(Mapping):
    def __init__(self, field):
        self._f = field

    def __getitem__(self, name):
        c = self._f._by_name[name]
        return _transform(self._f._raw[geometry_key(c.geometry)], c.sense, c.minimum_m)

    def __iter__(self):
        return iter(self._f._by_name)

    def __len__(self):
        return len(self._f._by_name)


class DistanceField:
    def __init__(self, constraints, x0, y0, spacing_m, nx, ny, raw):
        self.constraints = tuple(constraints)
        names = [c.name for c in self.constraints]
        if len(set(names)) != len(names):
            raise GeometryError("约束名重复")
        for c in self.constraints:
            if c.sense not in SENSES:
                raise GeometryError(f"约束 {c.name} 的 sense 非法：{c.sense!r}")
        self._by_name = {c.name: c for c in self.constraints}
        self.x0, self.y0, self.spacing_m, self.nx, self.ny = float(x0), float(y0), float(spacing_m), int(nx), int(ny)
        self._raw = raw
        self.eps = math.hypot(self.spacing_m, self.spacing_m) / 2.0
        self.values = _Values(self)

    # -------------------------------------------------------- 点查询
    def _select(self, names):
        if names is None:
            return self.constraints
        return tuple(self._by_name[n] for n in names)

    def _locate(self, pts):
        gx = (pts[:, 0] - self.x0) / self.spacing_m
        gy = (pts[:, 1] - self.y0) / self.spacing_m
        inside = (gx >= 0) & (gx <= self.nx - 1) & (gy >= 0) & (gy <= self.ny - 1)
        ix = np.clip(np.floor(gx).astype(np.int64), 0, self.nx - 2)
        iy = np.clip(np.floor(gy).astype(np.int64), 0, self.ny - 2)
        fx = np.clip(gx - ix, 0.0, 1.0)
        fy = np.clip(gy - iy, 0.0, 1.0)
        return inside, ix, iy, fx, fy

    def lower_clearance(self, xy, names=None):
        """各约束的双线性值减半对角线，返回 {约束名: 数组}；栅格外为 −inf。"""
        pts = np.asarray(xy, dtype=float)
        shape = pts.shape[:-1]
        pts = pts.reshape(-1, pts.shape[-1])[:, :2]
        inside, ix, iy, fx, fy = self._locate(pts)
        out = {}
        for c in self._select(names):
            g = self._raw[geometry_key(c.geometry)]
            v00 = _transform(g[iy, ix], c.sense, c.minimum_m)
            v10 = _transform(g[iy, ix + 1], c.sense, c.minimum_m)
            v01 = _transform(g[iy + 1, ix], c.sense, c.minimum_m)
            v11 = _transform(g[iy + 1, ix + 1], c.sense, c.minimum_m)
            val = (v00 * (1 - fx) * (1 - fy) + v10 * fx * (1 - fy) + v01 * (1 - fx) * fy + v11 * fx * fy) - self.eps
            out[c.name] = np.where(inside, val, -np.inf).reshape(shape)
        return out

    def min_lower_clearance(self, xy, names=None):
        parts = list(self.lower_clearance(xy, names).values())
        if not parts:
            pts = np.asarray(xy, dtype=float)
            return np.full(pts.shape[:-1], np.inf)
        return np.min(np.stack(parts), axis=0)

    def feasible(self, xy, names=None):
        return self.min_lower_clearance(xy, names) >= 0.0

    # -------------------------------------------------------- 单元级
    def corner_values(self, constraint, extra_margin_m=0.0):
        return _transform(self._raw[geometry_key(constraint.geometry)], constraint.sense,
                          constraint.minimum_m) - extra_margin_m

    def _cell_bounds(self, names, extra_margin_m):
        vmin = vmax = None
        for c in self._select(names):
            v = self.corner_values(c, extra_margin_m)
            corners = np.stack([v[:-1, :-1], v[:-1, 1:], v[1:, :-1], v[1:, 1:]])
            lo, hi = corners.min(axis=0), corners.max(axis=0)
            vmin = lo if vmin is None else np.minimum(vmin, lo)
            vmax = hi if vmax is None else np.minimum(vmax, hi)   # 取各约束最大角值的最小者：任一约束上界为负即剪枝
        return vmin, vmax

    def certified_cell_mask(self, names=None, extra_margin_m=0.0):
        """整格可证可行：各约束四个角值的最小值都 ≥ eps（双线性在格内的最小值在角上）。"""
        vmin, _ = self._cell_bounds(names, extra_margin_m)
        if vmin is None:
            return np.ones((self.ny - 1, self.nx - 1), bool)
        return vmin >= self.eps


class CombinedGrid:
    """若干约束取最小值得到的单一栅格。min 仍是 1-Lipschitz，所以"双线性 − eps ≥ extra"依然保守。
    比逐约束插值快得多，用来在极坐标/射线上批量判可行；最终仍由精确弦检查验收。"""

    def __init__(self, field, names=None):
        self.field = field
        grid = None
        for c in field._select(names):
            v = field.corner_values(c)
            grid = v if grid is None else np.minimum(grid, v)
        self.grid = grid

    def value(self, xy):
        """双线性值（不减 eps）；栅格外为 −inf。"""
        f = self.field
        pts = np.asarray(xy, dtype=float)
        shape = pts.shape[:-1]
        pts = pts.reshape(-1, pts.shape[-1])[:, :2]
        inside, ix, iy, fx, fy = f._locate(pts)
        g = self.grid
        val = (g[iy, ix] * (1 - fx) * (1 - fy) + g[iy, ix + 1] * fx * (1 - fy) + g[iy + 1, ix] * (1 - fx) * fy
               + g[iy + 1, ix + 1] * fx * fy)
        return np.where(inside, val, -np.inf).reshape(shape)

    def ok(self, xy, extra_margin_m=0.0):
        return self.value(xy) - self.field.eps >= extra_margin_m


def build_distance_field(constraints, bounds_xyxy, *, spacing_m, raw_cache=None):
    """覆盖 bounds 的距离场，端点扩至完整栅格。raw_cache 是 {geometry_key: 数组} 形式的可写映射，
    用来在不同阶段的约束集之间复用同一几何的精确距离（也可由调用方落盘）。"""
    x0, y0, x1, y1 = (float(t) for t in bounds_xyxy)
    h = float(spacing_m)
    if not (math.isfinite(h) and h > 0 and x1 > x0 and y1 > y0):
        raise GeometryError("栅格间距须为正，边界框须非空")
    nx = int(math.ceil((x1 - x0) / h - 1e-9)) + 1
    ny = int(math.ceil((y1 - y0) / h - 1e-9)) + 1
    xs = x0 + h * np.arange(nx)
    ys = y0 + h * np.arange(ny)
    raw = {} if raw_cache is None else raw_cache
    local = {}
    for c in constraints:
        k = geometry_key(c.geometry)
        if k not in local:
            g = raw.get(k) if hasattr(raw, "get") else None
            if g is None or g.shape != (ny, nx):
                g = sdf_grid(c.geometry, xs, ys)
                try:
                    raw[k] = g
                except TypeError:
                    pass
            local[k] = g
    return DistanceField(constraints, x0, y0, h, nx, ny, local)


# ---------------------------------------------------------------- 保守单元集合

class CellSet:
    """若干轴对齐正方形 (x0, y0, size) 的并，互不重叠；按面积加权均匀抽点。"""

    def __init__(self, x0, y0, size):
        self.x0 = np.asarray(x0, dtype=float)
        self.y0 = np.asarray(y0, dtype=float)
        self.size = np.asarray(size, dtype=float)
        self._cum = np.cumsum(self.size ** 2)

    def __len__(self):
        return len(self.size)

    @property
    def area(self):
        return float(self._cum[-1]) if len(self) else 0.0

    def sample(self, rng, k=1):
        """面积加权选格、格内均匀取点，返回 (k, 2)。集合为空时抛 ValueError。"""
        if not len(self):
            raise ValueError("空集合无法抽点")
        u = rng.random(k) * self._cum[-1]
        idx = np.minimum(np.searchsorted(self._cum, u, side="right"), len(self) - 1)
        off = rng.random((k, 2))
        return np.stack([self.x0[idx] + off[:, 0] * self.size[idx], self.y0[idx] + off[:, 1] * self.size[idx]], axis=1)

    def contains(self, xy):
        p = np.asarray(xy, dtype=float).reshape(-1, 2)
        out = np.zeros(len(p), bool)
        for lo in range(0, len(p), 256):
            q = p[lo:lo + 256]
            out[lo:lo + len(q)] = np.any((q[:, 0:1] >= self.x0[None]) & (q[:, 0:1] <= (self.x0 + self.size)[None])
                                         & (q[:, 1:2] >= self.y0[None]) & (q[:, 1:2] <= (self.y0 + self.size)[None]), axis=1)
        return out

    def centers(self):
        return np.stack([self.x0 + self.size / 2, self.y0 + self.size / 2], axis=1)


def conservative_cells(field, *, names=None, extra_margin_m=0.0, min_cell_m=None):
    """用误差界裁出保守集合：整格可证可行的格直接并入；不确定的格四分，
    子格在中心点用**精确**距离和当前格半对角线（1-Lipschitz）判定，直到子格小于 min_cell_m。
    仍不确定的最小格不纳入集合（宁漏勿错）。"""
    cons = field._select(names)
    h = field.spacing_m
    if min_cell_m is None:
        min_cell_m = h / 10.0
    levels = max(0, int(math.ceil(math.log2(h / min_cell_m))))
    vmin, vmax = field._cell_bounds(names, extra_margin_m)
    X = field.x0 + h * np.arange(field.nx - 1)
    Y = field.y0 + h * np.arange(field.ny - 1)
    if vmin is None:
        gx, gy = np.meshgrid(X, Y)
        return CellSet(gx.ravel(), gy.ravel(), np.full(gx.size, h))
    cert = vmin >= field.eps
    prune = vmax + field.eps < 0.0
    unc = ~cert & ~prune
    gx, gy = np.meshgrid(X, Y)
    cx, cy, cs = [gx[cert]], [gy[cert]], [np.full(int(cert.sum()), h)]
    ux, uy = gx[unc], gy[unc]
    size = h
    for _ in range(levels):
        if not len(ux):
            break
        size /= 2.0
        half = size * math.sqrt(2.0) / 2.0
        kx = np.concatenate([ux, ux + size, ux, ux + size])
        ky = np.concatenate([uy, uy, uy + size, uy + size])
        center = np.stack([kx + size / 2, ky + size / 2], axis=1)
        ok = np.ones(len(center), bool)
        bad = np.zeros(len(center), bool)
        for c in cons:
            f = clearance_values(c.geometry, center, sense=c.sense, minimum_m=c.minimum_m) - extra_margin_m
            ok &= f >= half
            bad |= f + half < 0.0
        cx.append(kx[ok]); cy.append(ky[ok]); cs.append(np.full(int(ok.sum()), size))
        keep = ~ok & ~bad
        ux, uy = kx[keep], ky[keep]
    return CellSet(np.concatenate(cx), np.concatenate(cy), np.concatenate(cs))
