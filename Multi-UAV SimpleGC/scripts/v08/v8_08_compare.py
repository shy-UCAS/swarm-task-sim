"""V8-08 第 6 部分：新引导层与冻结跟踪器的耗时、速度对照（只记录，不设门禁）。

速度一律写 v_cmd（期望）或 v_meas（实测）；冻结跟踪器的弯道减速是冻结仿真器的跟踪与限速特性，
新引导层的弯道速度由 a_lat 待测初值决定（V8-09 标定），都不代表真实无人机能力。

用法（在 Multi-UAV SimpleGC 目录下）:
    python -B scripts/v08/v8_08_compare.py
"""
import csv
import math
import sys
import time
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))

from v08.calibration.geometry import build_waypoints, distance_to_path, line, shape_turn  # noqa: E402
from v08.calibration.metrics import arc_steady_mask, speed_xy  # noqa: E402
from v08.calibration.runner import fly  # noqa: E402
from v08.sim.guided import GuidedSegmentPlan, run_guided_segment  # noqa: E402
from v08.sim.types import MemberBoundaryState  # noqa: E402

OUT = PROJECT.parent / "docs" / "v08" / "V8-08" / "compare.csv"
ALT = 120.0
DS = 0.5
FIELDS = ["case", "method", "geometry", "v_cmd_m_s", "spacing_m", "status", "wall_s", "sim_s", "wall_per_sim",
          "steady_frames", "v_meas_median_m_s", "v_meas_p05_m_s", "v_meas_p95_m_s", "steady_dev_max_m"]


def densify(prims, ds=DS):
    """直线等分为 ceil(长/ds) 段；圆弧按 ceil(R·|Δθ|/ds) 等角分段；去掉相邻重合点。"""
    pts = []
    for prim in prims:
        if prim[0] == "line":
            a, b = np.asarray(prim[1]), np.asarray(prim[2])
            n = max(1, math.ceil(float(np.hypot(*(b - a))) / ds - 1e-9))
            seg = a + np.linspace(0.0, 1.0, n + 1)[:, None] * (b - a)
        else:
            _, c, R, th0, dth = prim
            n = max(1, math.ceil(R * abs(dth) / ds - 1e-9))
            th = th0 + dth * np.arange(n + 1) / n
            seg = np.c_[c[0] + R * np.cos(th), c[1] + R * np.sin(th)]
        for q in seg:
            if pts and math.hypot(q[0] - pts[-1][0], q[1] - pts[-1][1]) <= 1e-9:
                continue
            pts.append((float(q[0]), float(q[1])))
    return np.asarray(pts)


def run_guided(prims, v_cmd):
    P = densify(prims)
    L = float(np.sum(np.hypot(*np.diff(P, axis=0).T)))
    plan = GuidedSegmentPlan("m", 0, tuple(map(tuple, P.tolist())), ALT, ((0.0, float(v_cmd)),), L)
    state = MemberBoundaryState("m", 0, 0, (float(P[0, 0]), float(P[0, 1]), ALT), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    t0 = time.perf_counter()
    r = run_guided_segment(plan, state, final=True)
    return r, time.perf_counter() - t0


def run_frozen(prims, v_cmd, spacing):
    W = build_waypoints(prims, spacing, ALT)
    t0 = time.perf_counter()
    r = fly(W, float(v_cmd))
    return r, time.perf_counter() - t0


def steady_mask(case, r):
    if case["R"] is None:                                    # 直线：取 100–200 m 段作稳态帧
        return (r.p[:, 0] > 100.0) & (r.p[:, 0] < 200.0)
    R = case["R"]
    return arc_steady_mask(r.p[:, :2], (0.0, R), R, -math.pi / 2, math.radians(case["dtheta_deg"]))


def row(case, method, spacing, r, wall):
    m = steady_mask(case, r)
    sp = speed_xy(r.v)[m]
    sim_s = len(r.tau_us) * 0.1
    dev = distance_to_path(r.p[m, :2], case["prims"]) if m.any() else np.array([])
    q = (lambda p: float(np.percentile(sp, p))) if len(sp) else (lambda p: None)
    return dict(case=case["name"], method=method, geometry=case["geometry"], v_cmd_m_s=case["v_cmd"],
                spacing_m=spacing, status=r.status, wall_s=round(wall, 3), sim_s=round(sim_s, 1),
                wall_per_sim=round(wall / sim_s, 5), steady_frames=int(m.sum()),
                v_meas_median_m_s=q(50), v_meas_p05_m_s=q(5), v_meas_p95_m_s=q(95),
                steady_dev_max_m=float(dev.max()) if len(dev) else None)


def main():
    cases = [
        dict(name="a", geometry="直线 300 m", prims=[line((0.0, 0.0), (300.0, 0.0))], v_cmd=8.0, spacing=None,
             R=None, dtheta_deg=None),
        dict(name="b", geometry="shape_turn(20, 120, 100, 100)", prims=shape_turn(20, 120, 100, 100), v_cmd=10.0,
             spacing=8.0, R=20.0, dtheta_deg=120.0),
        dict(name="c", geometry="shape_turn(240, 120, 100, 100)", prims=shape_turn(240, 120, 100, 100),
             v_cmd=10.0, spacing=24.0, R=240.0, dtheta_deg=120.0),
    ]
    rows = []
    for c in cases:
        r, w = run_guided(c["prims"], c["v_cmd"])
        rows.append(row(c, "guided", DS, r, w))
        sp = c["spacing"] if c["spacing"] is not None else 300.0      # 直线：两个航点
        r, w = run_frozen(c["prims"], c["v_cmd"], sp)
        rows.append(row(c, "frozen_tracker", c["spacing"], r, w))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        wr = csv.DictWriter(fh, FIELDS)
        wr.writeheader()
        wr.writerows(rows)
    fmt = lambda x: "—" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))  # noqa: E731
    print("| " + " | ".join(FIELDS) + " |")
    print("|" + "---|" * len(FIELDS))
    for r in rows:
        print("| " + " | ".join(fmt(r[k]) for k in FIELDS) + " |")
    print(f"写出 {OUT}")


if __name__ == "__main__":
    main()
