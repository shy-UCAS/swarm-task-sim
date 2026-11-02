"""V8-09 2.4：逐航段实测量（只测量，不拟合、不标定新引导层）。

读 docs/v08/V8-09/flights/<飞行编号>/processed.csv 与 check.json，写 arcs.csv、straights.csv、flights.csv、summary.md。
v_meas 为飞控估计的水平速度 √(ve² + vn²)；加速度由速度中心差分得到。

用法（在 Multi-UAV SimpleGC 目录下）:
    python -B scripts/v08/v8_09_sitl_analyze.py [--flights 编号 …]
    python -B scripts/v08/v8_09_sitl_analyze.py --selftest
"""
import argparse
import csv
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from v08.calibration.geometry import arc_relative_angle, distance_to_path  # noqa: E402
from v08.calibration.metrics import arc_steady_mask  # noqa: E402

from v8_09_sitl_route import elements, route  # noqa: E402
from v8_09_sitl_fly import ID_RE, parse_id  # noqa: E402

DOCS = REPO / "docs" / "v08" / "V8-09"
MOVING_M_S = 1.0
STEADY_MARGIN_DEG = 15.0
NEAR_M = 10.0                       # arc_steady_mask 的 max_dist；也用于停留时间与直线中段的横向范围
TERMINAL_EXCLUDE_M = 40.0
FRAME_S = 0.1
DENSE_M = 0.5                       # 进度跟踪用的航线加密间距
PROGRESS_BACK_M = 30.0              # 进度窗口：向后 30 m，向前 30 m + 15 m/s × 帧间隔
PROGRESS_SPEED_M_S = 15.0

ARC_FIELDS = ["flight", "v_cmd", "accel_cm_s2", "mode", "valid_flight", "element", "R_m", "dtheta_deg",
              "steady_frames", "v_meas_median", "v_meas_p05", "v_meas_p95", "a_lat_median", "a_lat_p95",
              "dev_max_m", "dev_median_m", "time_on_arc_s"]
STRAIGHT_FIELDS = ["flight", "v_cmd", "accel_cm_s2", "mode", "valid_flight", "element", "length_m", "mid_frames",
                   "v_meas_median", "v_meas_max"]
FLIGHT_FIELDS = ["flight", "v_cmd", "accel_cm_s2", "mode", "valid_flight", "check_params", "WPNAV_SPEED",
                 "WPNAV_ACCEL", "check_timebase", "timebase_slope", "check_valid", "valid_fraction",
                 "check_status", "status", "elapsed_s", "frames", "t90_s", "start_a_lon_p95",
                 "brake_duration_s", "brake_decel_p95", "dev_max_nonterminal_m", "a_lat_p99", "a_lat_max",
                 "a_lon_abs_p99", "a_lon_abs_max"]


def read_processed(path):
    rows = []
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["valid"] != "1":
                continue
            rows.append([float(r[k]) for k in ("t", "east_m", "north_m", "ve_m_s", "vn_m_s")])
    a = np.asarray(rows, dtype=float).reshape(-1, 5)
    return a[:, 0], a[:, 1:3], a[:, 3:5]


def derive(t, vel):
    """v_meas、中心差分加速度，以及 v_meas > 1 m/s 的帧上的 a_lat、a_lon（其余为 NaN）。"""
    n = len(t)
    speed = np.hypot(vel[:, 0], vel[:, 1])
    acc = np.full((n, 2), np.nan)
    if n >= 3:
        acc[1:-1] = (vel[2:] - vel[:-2]) / (t[2:] - t[:-2])[:, None]
    ok = (speed > MOVING_M_S) & np.isfinite(acc[:, 0])
    a_lat = np.full(n, np.nan)
    a_lon = np.full(n, np.nan)
    ve, vn, ae, an = vel[ok, 0], vel[ok, 1], acc[ok, 0], acc[ok, 1]
    a_lat[ok] = np.abs(ve * an - vn * ae) / speed[ok]
    a_lon[ok] = (ve * ae + vn * an) / speed[ok]
    return speed, a_lat, a_lon


def _q(x, q):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    return float(np.percentile(x, q)) if len(x) else None


def _max(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    return float(x.max()) if len(x) else None


def _line_frame(xy, prim):
    a, b = np.asarray(prim[1]), np.asarray(prim[2])
    d = b - a
    L = float(np.hypot(*d))
    u = d / L
    rel = xy - a
    s = rel @ u
    lat = np.abs(rel[:, 0] * u[1] - rel[:, 1] * u[0])
    return s / L, lat, L


def _dense_route(ds=DENSE_M):
    pts, elem = [], []
    for k, p in elements():
        if p[0] == "line":
            a, b = np.asarray(p[1]), np.asarray(p[2])
            n = max(1, math.ceil(float(np.hypot(*(b - a))) / ds))
            seg = a + np.linspace(0.0, 1.0, n, endpoint=False)[:, None] * (b - a)
        else:
            _, c, R, th0, dth = p
            n = max(1, math.ceil(R * abs(dth) / ds))
            th = th0 + dth * np.arange(n) / n
            seg = np.c_[c[0] + R * np.cos(th), c[1] + R * np.sin(th)]
        pts.append(seg)
        elem += [k] * len(seg)
    last = np.asarray(route()[-1][2])[None, :]
    P = np.vstack(pts + [last])
    elem.append(elem[-1])
    s = np.r_[0.0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    return P, s, np.asarray(elem)


def assign_elements(t, xy):
    """按时间顺序沿航线跟踪进度：每帧只在上一进度附近的弧长窗口内找最近点，得到所属元素编号。
    航线自身有接触点（#14 掉头最低点落在 #9 直线上），只按几何归属会把两处混在一起。"""
    P, s, elem = _dense_route()
    out = np.zeros(len(t), dtype=int)
    s_prev, t_prev = 0.0, (t[0] if len(t) else 0.0)
    for i in range(len(t)):
        ahead = PROGRESS_BACK_M + PROGRESS_SPEED_M_S * max(float(t[i] - t_prev), FRAME_S)
        lo = np.searchsorted(s, s_prev - PROGRESS_BACK_M)
        hi = np.searchsorted(s, s_prev + ahead, side="right")
        j = lo + int(np.argmin(np.hypot(P[lo:hi, 0] - xy[i, 0], P[lo:hi, 1] - xy[i, 1])))
        out[i] = elem[j]
        s_prev, t_prev = max(s_prev, float(s[j])), float(t[i])
    return out


def analyze_flight(t, xy, vel, v_cmd):
    prims = route()
    speed, a_lat, a_lon = derive(t, vel)
    owner = assign_elements(t, xy)
    arcs, straights = [], []
    for k, prim in elements():
        if prim[0] == "arc":
            _, c, R, th0, dth = prim
            on = arc_steady_mask(xy, c, R, th0, dth, margin_deg=0.0, max_dist=NEAR_M) & (owner == k)
            if not on.any():
                continue
            st = arc_steady_mask(xy, c, R, th0, dth, margin_deg=STEADY_MARGIN_DEG, max_dist=NEAR_M) & (owner == k)
            dev = distance_to_path(xy[st], prims) if st.any() else np.array([])
            arcs.append(dict(element=k, R_m=R, dtheta_deg=round(math.degrees(dth), 3), steady_frames=int(st.sum()),
                             v_meas_median=_q(speed[st], 50), v_meas_p05=_q(speed[st], 5),
                             v_meas_p95=_q(speed[st], 95), a_lat_median=_q(a_lat[st], 50),
                             a_lat_p95=_q(a_lat[st], 95), dev_max_m=_max(dev), dev_median_m=_q(dev, 50),
                             time_on_arc_s=round(int(on.sum()) * FRAME_S, 1)))
        else:
            frac, lat, L = _line_frame(xy, prim)
            mid = (frac >= 0.25) & (frac <= 0.75) & (lat <= NEAR_M) & (owner == k)
            if not mid.any():
                continue
            straights.append(dict(element=k, length_m=round(L, 3), mid_frames=int(mid.sum()),
                                  v_meas_median=_q(speed[mid], 50), v_meas_max=_max(speed[mid])))
    fl = dict(frames=int(len(t)))
    # 起步：从 t = 0 起 v_meas 首次 ≥ 0.9 v 的时刻
    hit = np.flatnonzero((t >= 0) & (speed >= 0.9 * v_cmd))
    if len(hit):
        t90 = float(t[hit[0]])
        fl.update(t90_s=round(t90, 2), start_a_lon_p95=_q(a_lon[(t >= 0) & (t <= t90)], 95))
    # 刹停：最后一段直线上 v_meas 最后一次 ≥ 0.9 v 起，到首次 < 0.5 m/s 止
    last = prims[-1]
    frac, lat, _ = _line_frame(xy, last)
    on_last = (frac >= 0.0) & (frac <= 1.0 + TERMINAL_EXCLUDE_M / 200.0) & (lat <= NEAR_M) & (owner == len(prims))
    fast = np.flatnonzero(on_last & (speed >= 0.9 * v_cmd))
    if len(fast):
        i0 = int(fast[-1])
        slow = np.flatnonzero((np.arange(len(t)) > i0) & (speed < 0.5))
        if len(slow):
            i1 = int(slow[0])
            seg = slice(i0, i1 + 1)
            fl.update(brake_duration_s=round(float(t[i1] - t[i0]), 2), brake_decel_p95=_q(-a_lon[seg], 95))
    end = np.asarray(last[2])
    nonterm = np.hypot(xy[:, 0] - end[0], xy[:, 1] - end[1]) > TERMINAL_EXCLUDE_M
    if nonterm.any():
        fl["dev_max_nonterminal_m"] = _max(distance_to_path(xy[nonterm], prims))
    fl.update(a_lat_p99=_q(a_lat, 99), a_lat_max=_max(a_lat), a_lon_abs_p99=_q(np.abs(a_lon), 99),
              a_lon_abs_max=_max(np.abs(a_lon)))
    return arcs, straights, fl


def _fmt(x):
    if x is None:
        return ""
    if isinstance(x, float):
        return f"{x:.4g}"
    return x


def write_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: _fmt(r.get(k)) for k in fields})


def run(flights_dir, out_dir, only=None):
    arc_rows, straight_rows, flight_rows = [], [], []
    dirs = sorted(d for d in Path(flights_dir).iterdir() if d.is_dir() and ID_RE.fullmatch(d.name))
    for d in dirs:
        fid = d.name
        if only and fid not in only:
            continue
        v, accel, mode = parse_id(fid)
        base = dict(flight=fid, v_cmd=v, accel_cm_s2=accel, mode=mode)
        chk = json.loads((d / "check.json").read_text(encoding="utf-8")) if (d / "check.json").is_file() else {}
        meta = (json.loads((d / "metadata_excerpt.json").read_text(encoding="utf-8"))
                if (d / "metadata_excerpt.json").is_file() else {})
        valid = bool(chk.get("all_pass"))
        base["valid_flight"] = int(valid)
        fr = dict(base, check_params=int(bool(chk.get("params", {}).get("pass_"))),
                  WPNAV_SPEED=chk.get("params", {}).get("actual", {}).get("WPNAV_SPEED"),
                  WPNAV_ACCEL=chk.get("params", {}).get("actual", {}).get("WPNAV_ACCEL"),
                  check_timebase=int(bool(chk.get("timebase", {}).get("pass_"))),
                  timebase_slope=chk.get("timebase", {}).get("slope"),
                  check_valid=int(bool(chk.get("valid", {}).get("pass_"))),
                  valid_fraction=chk.get("valid", {}).get("fraction"),
                  check_status=int(bool(chk.get("status", {}).get("pass_"))),
                  status=chk.get("status", {}).get("value"), elapsed_s=meta.get("elapsed_s"))
        if (d / "processed.csv").is_file():
            t, xy, vel = read_processed(d / "processed.csv")
            arcs, straights, fl = analyze_flight(t, xy, vel, v)
            arc_rows += [dict(base, **r) for r in arcs]
            straight_rows += [dict(base, **r) for r in straights]
            fr.update(fl)
        flight_rows.append(fr)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "arcs.csv", ARC_FIELDS, arc_rows)
    write_csv(out / "straights.csv", STRAIGHT_FIELDS, straight_rows)
    write_csv(out / "flights.csv", FLIGHT_FIELDS, flight_rows)
    (out / "summary.md").write_text(summary(arc_rows, flight_rows), encoding="utf-8")
    return arc_rows, straight_rows, flight_rows


def summary(arc_rows, flight_rows):
    keys = [(e, r[0], round(r[1])) for e, r in ((k, (p[2], math.degrees(p[4]))) for k, p in elements() if p[0] == "arc")]
    head = ["v_cmd", "WPNAV_ACCEL", "方式", "有效"] + [f"#{e} R{R:g}/{d}°" for e, R, d in keys]
    lines = ["# V8-09 弯道实测汇总", "",
             "每格为该元素稳态帧的 v_meas 中位数 / a_lat 中位数（m/s / m/s²）；稳态帧 = 弧内（两端各去 15°）、"
             "距设计圆弧 ≤ 10 m。v_meas 是飞控估计的速度；速度单位 m/s，加速度 m/s²。只记录，不作结论。", "",
             "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    by = {(r["flight"], r["element"]): r for r in arc_rows}
    for f in sorted(flight_rows, key=lambda r: (-r["v_cmd"], -r["accel_cm_s2"], r["mode"])):
        cells = [str(f["v_cmd"]), str(f["accel_cm_s2"]), f["mode"], "是" if f["valid_flight"] else "否"]
        for e, _, _ in keys:
            r = by.get((f["flight"], e))
            if r is None or r["v_meas_median"] is None:
                cells.append("—")
            else:
                al = r["a_lat_median"]
                cells.append(f"{r['v_meas_median']:.2f} / {al:.2f}" if al is not None else f"{r['v_meas_median']:.2f} / —")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def selftest():
    """读一份手写的 5 行 processed.csv：应输出空表、不报错。"""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "flights" / "v10_a250_dense10"
        d.mkdir(parents=True)
        (d / "processed.csv").write_text(
            "t,agent_id,valid,east_m,north_m,up_m,ve_m_s,vn_m_s,vu_m_s\n"
            "0.0,uav_01,1,-900.0,-900.0,30.0,0.0,0.0,0.0\n"
            "0.1,uav_01,1,-899.99,-900.0,30.0,0.2,0.0,0.0\n"
            "0.2,uav_01,0,,,,,,\n"
            "0.3,uav_01,1,-899.9,-900.0,30.0,0.6,0.0,0.0\n"
            "0.4,uav_01,1,-899.8,-900.0,30.0,0.9,0.0,0.0\n", encoding="utf-8")
        arcs, straights, flights = run(Path(tmp) / "flights", Path(tmp) / "out")
        text = (Path(tmp) / "out" / "summary.md").read_text(encoding="utf-8")
    ok = len(arcs) == 0 and len(straights) == 0 and len(flights) == 1 and flights[0]["frames"] == 4
    print(f"[{'通过' if ok else '未通过'}] 5 行 processed.csv：arcs {len(arcs)} 行、straights {len(straights)} 行、"
          f"flights {len(flights)} 行（有效帧 {flights[0].get('frames')}）、summary {len(text.splitlines())} 行", flush=True)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flights", nargs="*")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(0 if selftest() else 1)
    arcs, straights, flights = run(DOCS / "flights", DOCS, set(args.flights) if args.flights else None)
    print(f"写出 {DOCS}：arcs {len(arcs)} 行、straights {len(straights)} 行、flights {len(flights)} 行", flush=True)


if __name__ == "__main__":
    main()
