"""V8-11 预置测试的合成场景与轨迹（规划审查方编写，实现方不得修改或删除）。

只用圆形设施与圆形限制区（几何查询为解析式，不依赖 shapely 的几何运算）。
设施 A（目标）：圆心 (0, 0)、轮廓半径 100 m；保护 / 警戒 / 预警偏移 50 / 200 / 450 m，
  即到圆心距离 ≤ 150 为保护层、≤ 300 为警戒层、≤ 550 为预警层。
设施 B（非目标）：圆心 (1600, 0)、轮廓半径 80 m；偏移 40 / 150 / 350 m，即 ≤ 120 / 230 / 430。
限制区：圆心 (0, −1500)、半径 100 m。地图：边长 6000 m 的正方形，中心在原点。
轨迹：恒定高度 120 m，按分段（直线、圆弧、停留）以恒定速度精确采样到 10 Hz，速度取解析值。
"""
import math

import numpy as np

ALT = 120.0
FRAME_US = 100_000


def scene():
    def fac(fid, center, radius, offsets):
        out = [{"id": fid, "type": "facility", "geometry": {"type": "Circle", "center_m": list(center), "radius_m": radius}}]
        for layer, off in zip(("protected", "alert", "warning"), offsets):
            out.append({"id": f"{fid}_{layer}", "type": "protection_zone", "facility_id": fid, "layer": layer,
                        "offset_m": off,
                        "geometry": {"type": "Circle", "center_m": list(center), "radius_m": radius + off}})
        return out
    ents = fac("fac_a", (0.0, 0.0), 100.0, (50.0, 200.0, 450.0)) + fac("fac_b", (1600.0, 0.0), 80.0, (40.0, 150.0, 350.0))
    ents.append({"id": "obs_1", "type": "hard_constraint_obstacle",
                 "geometry": {"type": "Circle", "center_m": [0.0, -1500.0], "radius_m": 100.0}})
    ents.append({"id": "radar_1", "type": "radar", "geometry": {"type": "Point", "position_m": [0.0, -2500.0]}})
    world = {"type": "Polygon", "vertices_m": [[-3000.0, -3000.0], [3000.0, -3000.0], [3000.0, 3000.0], [-3000.0, 3000.0]]}
    return {"schema_version": "synthetic", "coordinate_system": "ENU", "units": {}, "world": {"id": "world", "geometry": world},
            "entry_zones": [], "entities": ents}


def survey(x0=-150.0, x1=150.0, y0=340.0, y1=500.0, footprint=60.0, spacing=20.0):
    """侦察区域：矩形 [x0, x1] × [y0, y1]，整块位于 A 的预警层内（到圆心 340–522 m）。"""
    v = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    return {"model": "synthetic", "assumptions": [], "geometry": {"type": "Polygon", "vertices_m": v},
            "vertices_m": v, "footprint_radius_m": footprint, "grid_spacing_m": spacing,
            "area_m2": (x1 - x0) * (y1 - y0), "strip_count": 2, "lane_endpoint_radius_m": 5.0}


def sample_path(start, pieces, speed, *, t0_us=0, min_frames=None):
    """start=(x, y)；pieces 为 ("line", (x, y)) / ("arc", (cx, cy), 扫角度数，正为逆时针) / ("hold", 秒)。
    返回 (time_us, p, v)，time_us = t0_us + k·100000，k = 0..N；N = floor(总时长 / 0.1)，
    min_frames 给出时在末尾按末点静止补齐到该帧数。"""
    segs = []
    cur = np.asarray(start, float)
    for pc in pieces:
        if pc[0] == "line":
            end = np.asarray(pc[1], float)
            L = float(np.linalg.norm(end - cur))
            segs.append(("line", cur.copy(), end, L / speed))
            cur = end
        elif pc[0] == "arc":
            c = np.asarray(pc[1], float)
            r = float(np.linalg.norm(cur - c))
            a0 = math.atan2(cur[1] - c[1], cur[0] - c[0])
            sweep = math.radians(pc[2])
            segs.append(("arc", c, (r, a0, sweep), r * abs(sweep) / speed))
            cur = c + r * np.array([math.cos(a0 + sweep), math.sin(a0 + sweep)])
        elif pc[0] == "hold":
            segs.append(("hold", cur.copy(), None, float(pc[1])))
        else:
            raise ValueError(pc[0])
    total = sum(s[3] for s in segs)
    n = int(math.floor(total * 10 + 1e-9))
    P, V = [], []
    for k in range(n + 1):
        t = k / 10.0
        acc = 0.0
        for i, (kind, a, b, d) in enumerate(segs):
            if t < acc + d or i == len(segs) - 1:
                u = min(max(t - acc, 0.0), d)
                if kind == "line":
                    dirv = (b - a) / max(np.linalg.norm(b - a), 1e-12)
                    P.append(a + dirv * speed * u)
                    V.append(dirv * speed)
                elif kind == "arc":
                    r, a0, sweep = b
                    sgn = 1.0 if sweep >= 0 else -1.0
                    ang = a0 + sgn * speed * u / r
                    P.append(a + r * np.array([math.cos(ang), math.sin(ang)]))
                    V.append(sgn * speed * np.array([-math.sin(ang), math.cos(ang)]))
                else:
                    P.append(a.copy())
                    V.append(np.zeros(2))
                break
            acc += d
    P, V = np.array(P), np.array(V)
    if min_frames is not None and len(P) < min_frames:
        extra = min_frames - len(P)
        P = np.vstack([P, np.repeat(P[-1:], extra, axis=0)])
        V = np.vstack([V, np.zeros((extra, 2))])
    T = len(P)
    p = np.c_[P, np.full(T, ALT)]
    v = np.c_[V, np.zeros(T)]
    t_us = t0_us + np.arange(T, dtype=np.int64) * FRAME_US
    return t_us, p, v


def common_grid(paths):
    """把若干条从 0 开始的轨迹补齐到同一帧数（末点静止）。"""
    n = max(len(t) for t, _, _ in paths)
    out = []
    for t, p, v in paths:
        extra = n - len(t)
        out.append((np.arange(n, dtype=np.int64) * FRAME_US,
                    np.vstack([p, np.repeat(p[-1:], extra, axis=0)]),
                    np.vstack([v, np.zeros((extra, 3))])))
    return out


def stitched(member_id, start, segment_pieces, speed, *, settle_s=20.0):
    """构造一个拼接好的成员轨迹（v08.sim.types.MemberTrack 的字段），编组时钟从 0 起：
    先在起点静止 settle_s（释放前），再依次飞各段；第 k 段的帧标为 k。
    段 k（k ≥ 1）的第一帧是上一段的"越过帧"，与 V8-04 拼接约定一致。
    返回 (tau_us, p, v, a, segment_index, executed_switch_tau_us, release_us)。"""
    pieces = [("hold", settle_s)]
    bounds = []
    for seg in segment_pieces:
        pieces += seg
        bounds.append(len(pieces))
    t, p, v = sample_path(start, pieces, speed)
    # 每段结束时刻 = 累计时长
    durations = []
    cur = np.asarray(start, float)
    for pc in pieces:
        if pc[0] == "line":
            durations.append(float(np.linalg.norm(np.asarray(pc[1]) - cur)) / speed)
            cur = np.asarray(pc[1], float)
        elif pc[0] == "arc":
            c = np.asarray(pc[1], float)
            r = float(np.linalg.norm(cur - c))
            a0 = math.atan2(cur[1] - c[1], cur[0] - c[0])
            durations.append(r * abs(math.radians(pc[2])) / speed)
            cur = c + r * np.array([math.cos(a0 + math.radians(pc[2])), math.sin(a0 + math.radians(pc[2]))])
        else:
            durations.append(float(pc[1]))
    ends = np.cumsum(durations)
    seg_end_s = [ends[b - 1] for b in bounds[:-1]]
    # 越过帧 = 第一个 t ≥ 段末时刻的帧
    switch_frames = [int(math.ceil(e * 10 - 1e-9)) for e in seg_end_s]
    seg = np.zeros(len(t), np.int64)
    for k, f in enumerate(switch_frames, start=1):
        seg[f:] = k
    a = np.zeros_like(p)
    release_us = int(round(settle_s * 10)) * FRAME_US
    return t, p, v, a, seg, tuple(int(t[f]) for f in switch_frames), release_us
