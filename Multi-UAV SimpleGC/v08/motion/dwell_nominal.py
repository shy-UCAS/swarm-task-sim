"""V8-19: piecewise nominal movement with one stationary interval; frozen nominal code is only called."""
from dataclasses import dataclass, replace
from types import SimpleNamespace

import numpy as np

from .nominal import member_nominal
from ..sim.guidance import MIN_CHORD_M


def _duration_ticks(value):
    value = float(value)
    if not np.isfinite(value):
        raise ValueError("dwell duration must be finite")
    ticks = round(value * 10)
    if not 200 <= ticks <= 1200 or value != ticks / 10:
        raise ValueError("dwell duration must be one of 200..1200 integer tenths")
    return ticks


def normalized_end(release_s, incoming_s, dwell_s, outgoing_s):
    """The reference end equals Prepared.decode's r + (end-r), without weakening fixed_time."""
    r, first, dwell, last = map(float, (release_s, incoming_s, dwell_s, outgoing_s))
    if not np.isfinite([r, first, dwell, last]).all() or min(first, last) <= 0:
        raise ValueError("nonfinite or degenerate nominal duration")
    duration_sum = (first + dwell) + last
    end = r + duration_sum
    travel = end - r
    if not np.isfinite([end, travel]).all() or end != r + travel:
        raise ValueError("nominal end does not survive exact optimizer decoding")
    return end, travel


def split_member_plan(member_plan, s_d):
    """Split at the exact complete-member arc station; preserve geometry and right-continuous speed events."""
    xy = np.asarray(member_plan.curve_xy, float)
    if xy.ndim != 2 or xy.shape[1] != 2 or len(xy) < 2 or not np.isfinite(xy).all():
        raise ValueError("invalid member geometry")
    delta = np.diff(xy, axis=0)
    chord = np.hypot(delta[:, 0], delta[:, 1])
    if np.any(chord <= MIN_CHORD_M):
        raise ValueError("member geometry contains a frozen-minimum chord")
    stations = np.r_[0.0, np.cumsum(chord)]
    station = float(s_d)
    if not np.isfinite(station) or not 0.0 < station < stations[-1]:
        raise ValueError("dwell station must lie strictly inside the complete member curve")
    right_index = int(np.searchsorted(stations, station, side="left"))
    if stations[right_index] == station:
        left_xy = xy[:right_index + 1]
        right_xy = xy[right_index:]
    else:
        point = np.array([np.interp(station, stations, xy[:, axis]) for axis in (0, 1)])
        left_xy = np.vstack((xy[:right_index], point))
        right_xy = np.vstack((point, xy[right_index:]))
    for points in (left_xy, right_xy):
        edges = np.diff(points, axis=0)
        if len(points) < 2 or np.any(np.hypot(edges[:, 0], edges[:, 1]) <= MIN_CHORD_M):
            raise ValueError(f"dwell split violates MIN_CHORD_M at original station {station!r}")
    breaks = tuple(member_plan.speed_breaks)
    at = [row for row in breaks if float(row[0]) <= station]
    if not at:
        raise ValueError("speed profile has no right-continuous value at dwell station")
    left_breaks = tuple(row for row in breaks if float(row[0]) < station)
    right_breaks = ((0.0, float(at[-1][1])),) + tuple((float(s) - station, v) for s, v in breaks if float(s) > station)
    left = replace(member_plan, curve_xy=tuple(map(tuple, left_xy)), end_s=station,
                   speed_breaks=left_breaks, stops=())
    right = replace(member_plan, curve_xy=tuple(map(tuple, right_xy)), end_s=float(stations[-1] - station),
                    speed_breaks=right_breaks, stops=())
    return left, right


@dataclass(frozen=True)
class DwellReference:
    incoming: object
    outgoing: object
    dwell_s: float
    release_s: float
    arrival_s: float
    departure_s: float
    end_s: float
    travel_s: float
    hold_s: float
    altitude_m: float
    dwell_station_m: float
    dwell_point_xy: tuple
    curve: object
    t_nodes: np.ndarray
    duration_sum: float
    duration_roundoff_s: float
    _incoming_pva: object
    _outgoing_pva: object

    def pva(self, t_abs):
        original = np.asarray(t_abs, float)
        scalar = original.ndim == 0
        t = original.reshape(-1)
        p = np.broadcast_to(self.dwell_point_xy, (len(t), 2)).copy()
        v = np.zeros_like(p)
        a = np.zeros_like(p)
        incoming = t <= self.arrival_s
        outgoing = t >= self.departure_s
        if incoming.any():
            p[incoming], v[incoming], a[incoming] = self._incoming_pva(t[incoming])
        if outgoing.any():
            p[outgoing], v[outgoing], a[outgoing] = self._outgoing_pva(t[outgoing] - self.departure_s)
        before, after = t < self.release_s, t > self.end_s
        p[before], p[after] = self.curve.xy[0], self.curve.xy[-1]
        v[before | after], a[before | after] = 0.0, 0.0
        for boundary, point in ((self.release_s, self.curve.xy[0]), (self.end_s, self.curve.xy[-1]),
                                (self.arrival_s, self.dwell_point_xy), (self.departure_s, self.dwell_point_xy)):
            select = t == boundary
            p[select], v[select] = point, 0.0
        shape = original.shape + (2,)
        if scalar:
            return p[0], v[0], a[0]
        return p.reshape(shape), v.reshape(shape), a.reshape(shape)

    def time_at_s(self, station):
        values = np.asarray(station, float)
        incoming_stations = self.curve.s[:len(self.incoming.t_nodes)]
        incoming = np.interp(values, incoming_stations, self.incoming.t_nodes) + self.release_s
        outgoing = np.interp(values - self.dwell_station_m, self.outgoing.curve.s,
                             self.outgoing.t_nodes) + self.departure_s
        out = np.where(values <= self.dwell_station_m, incoming, outgoing)
        return float(out) if out.ndim == 0 else out


def compose_dwell(incoming, outgoing, dwell_s, *, station_m=None):
    from .skeleton import NominalPVA
    ticks = _duration_ticks(dwell_s)
    duration = ticks / 10.0
    first, last = float(incoming.travel_s), float(outgoing.travel_s)
    r = float(incoming.release_s)
    end, travel = normalized_end(r, first, duration, last)
    first_length, last_length = float(incoming.curve.s[-1]), float(outgoing.curve.s[-1])
    if min(first_length, last_length) <= 0.0:
        raise ValueError("both dwell legs need positive geometric length")
    if not np.array_equal(incoming.curve.xy[-1], outgoing.curve.xy[0]):
        raise ValueError("dwell legs have different join points")
    # V8-19 station-anchor ruling: retain the selected station, never alter either frozen leg.
    anchor = first_length if station_m is None else float(station_m)
    if not np.isfinite(anchor) or anchor <= 0.0:
        raise ValueError("dwell station anchor must be positive and finite")
    if abs(first_length - anchor) > 1e-9 * max(1.0, anchor):
        raise ValueError("incoming geometry length differs from the selected dwell station")
    incoming_stations = np.asarray(incoming.curve.s, float).copy()
    incoming_stations[-1] = anchor
    xy = np.vstack((incoming.curve.xy, outgoing.curve.xy[1:]))
    stations = np.r_[incoming_stations, anchor + outgoing.curve.s[1:]]
    if not np.isfinite(stations).all() or np.any(np.diff(stations) <= 0.0):
        raise ValueError("composite station table must be strictly increasing")
    prefix = first + duration
    times = np.r_[incoming.t_nodes, prefix + outgoing.t_nodes[1:]]
    point = tuple(map(float, incoming.curve.xy[-1]))
    curve = SimpleNamespace(xy=xy, s=stations, length=float(stations[-1]))
    arrival = r + first
    departure = arrival + duration
    total = prefix + last
    return DwellReference(incoming, outgoing, duration, r, arrival, departure, end, travel,
                          float(incoming.hold_s), float(incoming.altitude_m), anchor, point, curve, times,
                          total, travel - total, NominalPVA(incoming), NominalPVA(replace(outgoing, release_s=0.0)))


def member_nominal_with_dwell(member_plan, dwell, *, guidance=None, sim=None):
    station, duration = map(float, dwell)
    _duration_ticks(duration)
    left, right = split_member_plan(member_plan, station)
    incoming = member_nominal(left, guidance=guidance, sim=sim)
    outgoing = member_nominal(right, guidance=guidance, sim=sim)
    return compose_dwell(incoming, outgoing, duration, station_m=station)


def references_with_dwell(skeleton, *, warnings=None, target_id=None, band_m=None, align_m=None):
    """The new-only branch; the old references_from_skeleton body is retained verbatim."""
    from ..sim.tracking import TimeReference
    from .skeleton import reference_guidance, semantic_lines
    windows = skeleton.witnesses["dwell_windows"]
    if set(windows) != set(skeleton.members):
        raise ValueError("dwell table must have exactly one row for every member")
    refs, lines, maps = [], [], {}
    for mid in sorted(skeleton.members):
        row = windows[mid]
        if len(row) != 3:
            raise ValueError(f"invalid dwell row for {mid}")
        station, duration, point = row
        point = np.asarray(point, float)
        if point.shape != (2,) or not np.isfinite(point).all():
            raise ValueError(f"invalid dwell point for {mid}")
        nom = member_nominal_with_dwell(skeleton.members[mid], (station, duration), guidance=reference_guidance())
        if not np.array_equal(point, nom.dwell_point_xy):
            raise ValueError(f"dwell point differs from exact member split for {mid}")
        refs.append(TimeReference(mid, nom.release_s, nom.end_s, nom.altitude_m, nom.pva))
        maps[mid] = {"curve_s": np.asarray(nom.curve.s, float), "t_abs": nom.t_nodes + nom.release_s,
                     "nominal": nom, "dwell_reference": nom}
        if warnings is not None:
            lines.extend(semantic_lines(mid, nom.incoming, warnings, target_id, band_m=band_m, align_m=align_m))
            for line in semantic_lines(mid, nom.outgoing, warnings, target_id, band_m=band_m, align_m=align_m):
                meta = dict(line[5])
                for key in ("s_from_m", "s_to_m", "s_cross_m"):
                    if key in meta:
                        meta[key] = float(meta[key]) + nom.dwell_station_m
                shift = nom.departure_s - float(nom.outgoing.release_s)
                lines.append((line[0], float(line[1]) + shift, float(line[2]) + shift, line[3], line[4], meta))
    return tuple(refs), tuple(lines), maps


def dwell_lines_from_skeleton(skeleton, maps):
    windows = (getattr(skeleton, "witnesses", None) or {}).get("dwell_windows") or {}
    out = []
    for mid in sorted(windows):
        station, duration, point = windows[mid]
        _duration_ticks(duration)
        nom = maps[mid]["nominal"]
        arrival = float(np.interp(float(station), nom.curve.s, nom.t_nodes)) + float(nom.release_s)
        for axis, tangent in (("x", (1.0, 0.0)), ("y", (0.0, 1.0))):
            out.append((mid, arrival, arrival + float(duration), tuple(map(float, point)), tangent,
                        {"kind": "dwell", "axis": axis, "s_d_m": float(station), "duration_s": float(duration)}))
    return tuple(out)
