"""V8-10 新引导层验证与标定：在软件在环标定后的参数下，用抽象几何航线测量新引导层的跟踪、
掉头驻留误报、停止驻留时长与名义用时误差。

用法（在 Multi-UAV SimpleGC 目录下，单进程）：
    python -B scripts/v08/v8_10_validate.py --stage <smoke|G1|G2|G3|G4|G5|summary>

结果写到仓库根目录 docs/v08/V8-10/。速度一律区分 v_cmd（速度剖面的指令速度）与
v_meas（10 Hz 帧水平速度模长）。弯道减速是新引导层按曲率限速的结果，不代表真实无人机的转弯能力。
"""
import argparse
import csv
import datetime
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
OUT = REPO / "docs" / "v08" / "V8-10"
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from v08.calibration import geometry as G  # noqa: E402
from v08.calibration import metrics as M  # noqa: E402
from v08.config import load_config  # noqa: E402
from v08.sim.guided import GuidedSegmentPlan, run_guided_segment  # noqa: E402
from v08.sim.kernel import member_config  # noqa: E402
from v08.sim.types import MemberBoundaryState  # noqa: E402

GUIDANCE = load_config("guidance")
SIM = load_config("sim").values
A_LAT = GUIDANCE.values["a_lat_m_s2"]
A_LON = GUIDANCE.values["a_lon_m_s2"]
TAU_S = member_config().controller.velocity_response_time_s
TERMINAL_HOLD_S = SIM["terminal_hold_s"]

ALT = 120.0
DS = 0.5
TAU_R = 20_000_000                 # 释放时刻 τ_r = 20 s（同 V8-06）
TERM_R = 40.0                      # 终端区：距最后一点 ≤ 40 m
SAT_A = 3.70                       # 饱和判定；冻结水平加速度上限 3.75 m/s²
TUBE_M = 0.5                       # R1：跟踪管（r3 6.6）
R4_DP = 0.5
R4_DV = TAU_S * A_LON              # 0.475 × a_lon
R4_BUMP = 0.3
STOP_NEAR_M = 30.0                 # G5 接近时长的起点
STOP_MASK_M = 60.0                 # G5 驻留检测只看停止点 60 m 内
HOLD_R = SIM["terminal_radius_m"]  # 1 m
HOLD_V = SIM["terminal_speed_m_s"]  # 0.15 m/s
DWELL_BASE_S = 20.0                # r3 6.3.3 驻留时长下限中的 20 s

V_ALL = (4.0, 6.0, 8.0, 10.0)
G1_R = (10, 15, 20, 30, 40, 60, 100, 200, 400, 1000)
G2_V = (6.0, 10.0)
G2_DPHI = 2 * math.pi + math.pi / 3
G3_R = (5, 8, 10, 15, 20, 25, 30, 40, 50)
G3_SHAPES = ("U", "V150", "teardrop")
G4_R = (20, 60, 200)
G4A_V = (6.0, 10.0)
G4B_V = ((10.0, 4.0), (4.0, 10.0), (10.0, 6.0), (6.0, 10.0))
G5_H = (10.0, 15.0, 18.0, 20.0, 22.0, 25.0)
CODE_FILES = ("scripts/v08/v8_10_validate.py", "configs/v08/guidance.json", "configs/v08/sim.json",
              "v08/sim/guided.py", "v08/sim/guidance.py", "v08/sim/kernel.py",
              "v08/calibration/geometry.py", "v08/calibration/metrics.py")


# ---------------------------------------------------------------- 2.1 公共函数

def densify(prims, ds=DS, return_ends=False):
    """元素表加密为点列：直线 n = max(1, ceil(长度/ds)) 等分，圆弧 n = max(1, ceil(R·|Δθ|/ds)) 等角分；
    依次拼接，丢弃与前一点距离 ≤ 1e-9 的点。return_ends=True 时另返回各元素终点在点列中的下标。"""
    pts, ends = [], []
    for prim in prims:
        if prim[0] == "line":
            p0, p1 = np.asarray(prim[1]), np.asarray(prim[2])
            n = max(1, math.ceil(float(np.hypot(*(p1 - p0))) / ds))
            seg = p0 + (p1 - p0) * (np.arange(n + 1) / n)[:, None]
        else:
            _, c, R, th0, dth = prim
            n = max(1, math.ceil(R * abs(dth) / ds))
            th = th0 + dth * np.arange(n + 1) / n
            seg = np.c_[c[0] + R * np.cos(th), c[1] + R * np.sin(th)]
        for q in seg:
            if pts and math.hypot(q[0] - pts[-1][0], q[1] - pts[-1][1]) <= 1e-9:
                continue
            pts.append((float(q[0]), float(q[1])))
        ends.append(len(pts) - 1)
    P = np.array(pts)
    return (P, ends) if return_ends else P


def arclen(P):
    return np.r_[0.0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]


def start_state(P):
    return MemberBoundaryState("m", 0, 0, (float(P[0, 0]), float(P[0, 1]), ALT), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


def fly(P, breaks, *, stops=(), final=True, state=None, k=0, end_s=None):
    """单段仿真；默认从 P[0] 静止起飞、第 0 段、段末为曲线终点。"""
    P = np.asarray(P, dtype=float)
    L = float(arclen(P)[-1])
    plan = GuidedSegmentPlan("m", k, tuple(map(tuple, P.tolist())), ALT, tuple(breaks),
                             L if end_s is None else float(end_s), tuple(stops))
    return run_guided_segment(plan, state if state is not None else start_state(P), final=final)


def _common(res, P_last):
    p = np.asarray(res.p)[:, :2]
    tau = np.asarray(res.tau_us)
    rel = tau >= TAU_R
    nonterm = M.away_from(p, np.asarray(P_last)[:2], TERM_R)
    spd = M.speed_xy(res.v)
    acc = np.linalg.norm(np.asarray(res.a)[:, :2], axis=1)
    return p, tau, rel, nonterm, spd, acc


def _max(x):
    return float(np.max(x)) if len(x) else math.nan


def _pct(x, q):
    return float(np.percentile(x, q)) if len(x) else math.nan


def _sat(acc, rel):
    a = acc[rel]
    return _max(a), (float(np.mean(a >= SAT_A)) if len(a) else math.nan)


def _timed(fn, *a, **kw):
    t0 = time.perf_counter()
    r = fn(*a, **kw)
    return r, time.perf_counter() - t0


def _T_active(tau):
    return (int(tau[-1]) - TAU_R) / 1e6


def prims_turn(shape, R):
    if shape == "U":
        return G.shape_turn(R, 180, 150, 150)
    if shape == "V150":
        return G.shape_turn(R, 150, 150, 150)
    if shape == "teardrop":
        return G.shape_teardrop(R, 150)
    raise ValueError(shape)


# ---------------------------------------------------------------- 输出

def _fmt(x):
    if x is None:
        return ""
    if isinstance(x, (bool, np.bool_)):
        return "true" if x else "false"
    if isinstance(x, (float, np.floating)):
        return "" if math.isnan(x) else f"{float(x):.10g}"
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    return str(x)


def write_csv(name, columns, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(columns)
        for r in rows:
            w.writerow([_fmt(r.get(c)) for c in columns])


def _parse(s):
    if s == "":
        return None
    if s in ("true", "false"):
        return s == "true"
    try:
        return float(s)
    except ValueError:
        return s


def read_csv(name):
    path = OUT / name
    if not path.exists():
        sys.exit(f"缺少前序阶段的输出 {path}，请先运行对应阶段")
    with open(path, newline="", encoding="utf-8") as f:
        return [{k: _parse(v) for k, v in row.items()} for row in csv.DictReader(f)]


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if math.isnan(float(x)) else float(x)
    return x


def write_json(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(_jsonable(obj), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_head():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def write_timing(stage, rows, wall_total, started_iso):
    doc = {"stage": stage, "started": started_iso, "finished": datetime.datetime.now().isoformat(timespec="seconds"),
           "python": sys.version.split()[0], "numpy": np.__version__, "git_head": git_head(),
           "guidance_sha256": GUIDANCE.sha256,
           "code_sha256": {f: hashlib.sha256((PROJECT / f).read_bytes()).hexdigest() for f in CODE_FILES},
           "params": {"a_lat_m_s2": A_LAT, "a_lon_m_s2": A_LON, "velocity_response_time_s": TAU_S},
           "n_sims": len(rows), "total_wall_s": wall_total,
           "sim_wall_s": float(np.nansum([r.get("wall_s", math.nan) for r in rows]))}
    write_json(f"timing_{stage}.json", doc)


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- G1 定半径圆弧

def run_G1(R, v):
    prims = G.shape_turn(R, 120, 100, 100)
    P = densify(prims)
    res, wall = _timed(fly, P, ((0.0, v),))
    p, tau, rel, nonterm, spd, acc = _common(res, P[-1])
    steady = rel & M.arc_steady_mask(p, (0.0, R), R, -math.pi / 2, 2 * math.pi / 3)
    vs = spd[steady]
    v_model = min(v, math.sqrt(A_LAT * R))
    med = _pct(vs, 50)
    a_max, sat = _sat(acc, rel)
    return dict(R_m=R, v_cmd=v, status=res.status, v_meas_med=med, v_meas_p05=_pct(vs, 5), v_meas_p95=_pct(vs, 95),
                v_model=v_model, err=med - v_model,
                dev_max=_max(G.distance_to_path(p[rel & nonterm], prims)),
                a_max=a_max, sat_frac=sat, T_active_s=_T_active(tau), nominal_s=res.pieces[0].nominal_time_s,
                wall_s=wall, dev_steady_max=_max(G.distance_to_path(p[steady], prims)), n_steady=int(steady.sum()))


G1_COLS = ["R_m", "v_cmd", "status", "v_meas_med", "v_meas_p05", "v_meas_p95", "v_model", "err", "dev_max",
           "a_max", "sat_frac", "T_active_s", "nominal_s", "wall_s", "dev_steady_max", "n_steady"]


def stage_G1():
    return [run_G1(float(R), v) for R in G1_R for v in V_ALL], "G1.csv", G1_COLS


# ---------------------------------------------------------------- G2 变曲率闭合曲线

def g2_validation_curves():
    """V8-06 指令 4.4 的抽取规则：种子 20261102，最小曲率半径 < 15 m 整条重抽，直到 8 条。"""
    rng = np.random.default_rng(20261102)
    phi = np.linspace(0.0, 2 * math.pi, 20001)
    curves, redraws = [], 0
    while len(curves) < 8:
        rho0 = float(rng.uniform(200, 800))
        k1, k2 = (int(k) for k in rng.choice(np.arange(2, 7), 2, replace=False))
        e1, e2 = (float(x) for x in rng.uniform(0, 0.12, 2))
        p1, p2 = (float(x) for x in rng.uniform(0, 2 * math.pi, 2))
        h = [(e1 * rho0, k1, p1), (e2 * rho0, k2, p2)]
        Rmin = float((1.0 / np.maximum(np.abs(G.polar_curvature(rho0, h, phi)), 1e-12)).min())
        if Rmin < 15.0:
            redraws += 1
            continue
        curves.append((rho0, h))
    return curves, redraws


def g2_curves():
    out = [("main", float(rho0), h) for rho0 in (300.0, 600.0)
           for h in ([(0.10 * rho0, 2, 0.0)], [(0.25 * rho0, 3, 0.0)])]
    val, redraws = g2_validation_curves()
    return out + [("validation", rho0, h) for rho0, h in val], redraws


def run_G2(set_, rho0, h, v):
    P, _ = G.polar_loop_points(rho0, h, 0.0, G2_DPHI, DS)
    res, wall = _timed(fly, P, ((0.0, v),))
    p, tau, rel, nonterm, spd, acc = _common(res, P[-1])
    prog = M.polar_progress(p, 0.0)
    steady = rel & (prog >= math.pi / 3) & (prog <= 2 * math.pi)        # V8-06 4.4 的稳态帧
    phi_grid = np.linspace(0.0, 2 * math.pi, 20001)
    Rloc = 1.0 / np.maximum(np.abs(G.polar_curvature(rho0, h, phi_grid)), 1e-12)
    a_max, sat = _sat(acc, rel)
    return dict(set=set_, rho0_m=rho0, harmonics=json.dumps([[float(a), int(k), float(s)] for a, k, s in h]),
                R_local_min_m=float(Rloc.min()), v_cmd=v, status=res.status,
                dev_max=_max(G.distance_to_polyline(p[rel & nonterm], P)), a_max=a_max, sat_frac=sat,
                v_meas_med=_pct(spd[steady], 50), T_active_s=_T_active(tau),
                nominal_s=res.pieces[0].nominal_time_s, wall_s=wall)


G2_COLS = ["set", "rho0_m", "harmonics", "R_local_min_m", "v_cmd", "status", "dev_max", "a_max", "sat_frac",
           "v_meas_med", "T_active_s", "nominal_s", "wall_s"]


def stage_G2():
    curves, redraws = g2_curves()
    print(f"G2 验证集重抽次数 {redraws}")
    write_json("G2_validation_draw.json", {"seed": 20261102, "redraws": redraws,
                                           "curves": [{"set": s, "rho0_m": r, "harmonics": h} for s, r, h in curves]})
    return [run_G2(s, r, h, v) for s, r, h in curves for v in G2_V], "G2.csv", G2_COLS


# ---------------------------------------------------------------- G3 掉头驻留误报

def run_G3(shape, R, v):
    prims = prims_turn(shape, R)
    P = densify(prims)
    res, wall = _timed(fly, P, ((0.0, v),))
    p, tau, rel, nonterm, spd, acc = _common(res, P[-1])
    d = M.dwell_result(p, tau, TAU_R, extra_mask=nonterm)
    late = (tau >= TAU_R + 10_000_000) & nonterm
    return dict(shape=shape, R_m=R, v_cmd=v, status=res.status, dwell=bool(d["detected"]),
                dwell_t_s=d["t_s"] if d["t_s"] is not None else math.nan,
                v_meas_min_turn=float(spd[late].min()) if late.any() else math.nan,
                dev_max=_max(G.distance_to_path(p[rel & nonterm], prims)), wall_s=wall,
                T_active_s=_T_active(tau), nominal_s=res.pieces[0].nominal_time_s)


G3_COLS = ["shape", "R_m", "v_cmd", "status", "dwell", "dwell_t_s", "v_meas_min_turn", "dev_max", "wall_s",
           "T_active_s", "nominal_s"]


def stage_G3():
    return [run_G3(s, float(R), v) for s in G3_SHAPES for v in V_ALL for R in G3_R], "G3.csv", G3_COLS


# ---------------------------------------------------------------- G4 段边界与弯道中途变速

def _window_compare(split_tau, split_p, split_v, un, lo, hi):
    iu = {int(t): i for i, t in enumerate(un.tau_us)}
    a, b = [], []
    for i, t in enumerate(split_tau):
        t = int(t)
        if lo <= t <= hi and t in iu:
            a.append(i)
            b.append(iu[t])
    if not a:
        return math.nan, math.nan, 0
    dp = np.linalg.norm(split_p[a, :2] - np.asarray(un.p)[b, :2], axis=1)
    dv = np.linalg.norm(split_v[a, :2] - np.asarray(un.v)[b, :2], axis=1)
    return float(dp.max()), float(dv.max()), len(a)


def run_G4a(R, boundary, v):
    prims = G.shape_turn(R, 90, 100, 150)
    P, ends = densify(prims, return_ends=True)
    iA = ends[1]                                    # 圆弧终点（接直线）
    iE = iA if boundary == "arc_end" else iA + int(round(50.0 / DS))
    s = arclen(P)
    sE = float(s[iE])
    br = ((0.0, v),)
    t0 = time.perf_counter()
    un = fly(P, br)
    r0 = fly(P[:iE + 11], br, final=False, end_s=sE)
    r1 = None
    if r0.status == "ok":
        P1 = P[iE:]
        r1 = fly(P1, br, state=r0.end_state, k=1)
    wall = time.perf_counter() - t0
    st = {"whole": un.status, "seg0": r0.status, "seg1": r1.status if r1 is not None else "not_run"}
    status = "ok" if all(x == "ok" for x in st.values()) else ";".join(f"{k}={x}" for k, x in st.items())
    out = dict(R_m=R, boundary=boundary, v_cmd=v, status=status, iE=iE, s_E_m=sE, wall_s=wall)
    p_un, tau_un, rel_un, nt_un, _, _ = _common(un, P[-1])
    out["dev_max_whole"] = _max(G.distance_to_path(p_un[rel_un & nt_un], prims))
    if r1 is None:
        return out
    tau_E = int(r0.end_state.tau_us)
    sp_tau = np.r_[np.asarray(r0.tau_us), np.asarray(r1.tau_us)]
    sp_p = np.r_[np.asarray(r0.p), np.asarray(r1.p)]
    sp_v = np.r_[np.asarray(r0.v), np.asarray(r1.v)]
    dp, dv, n = _window_compare(sp_tau, sp_p, sp_v, un, tau_E - 10_000_000, tau_E + 20_000_000)
    p = sp_p[:, :2]
    keep = (sp_tau >= TAU_R) & M.away_from(p, P[-1], TERM_R)
    out.update(dp_max=dp, dv_max=dv, dev_max=_max(G.distance_to_path(p[keep], prims)),
               tau_E_s=tau_E / 1e6, n_window=n)
    return out


G4A_COLS = ["R_m", "boundary", "v_cmd", "status", "dp_max", "dv_max", "dev_max", "wall_s",
            "dev_max_whole", "tau_E_s", "iE", "s_E_m", "n_window"]


def run_G4b(R, v1, v2):
    prims = G.shape_turn(R, 120, 100, 100)
    P, ends = densify(prims, return_ends=True)
    i0, i1 = ends[0], ends[1]
    n = i1 - i0
    s_change = float(arclen(P)[i0 + n // 2])
    res, wall = _timed(fly, P, ((0.0, v1), (s_change, v2)))
    p, tau, rel, nonterm, spd, acc = _common(res, P[-1])
    vt1, vt2 = min(v1, math.sqrt(A_LAT * R)), min(v2, math.sqrt(A_LAT * R))
    on = rel & M.arc_steady_mask(p, (0.0, R), R, -math.pi / 2, 2 * math.pi / 3, margin_deg=0, max_dist=10)
    vs = spd[on]
    return dict(R_m=R, v1=v1, v2=v2, status=res.status,
                bump=(_max(vs) - max(vt1, vt2)) if len(vs) else math.nan,
                dip=(min(vt1, vt2) - float(vs.min())) if len(vs) else math.nan,
                dev_max=_max(G.distance_to_path(p[rel & nonterm], prims)), wall_s=wall,
                v_target1=vt1, v_target2=vt2, s_change_m=s_change, n_on_arc=int(on.sum()),
                T_active_s=_T_active(tau), nominal_s=res.pieces[0].nominal_time_s)


G4B_COLS = ["R_m", "v1", "v2", "status", "bump", "dip", "dev_max", "wall_s", "v_target1", "v_target2",
            "s_change_m", "n_on_arc", "T_active_s", "nominal_s"]


def stage_G4():
    a = [run_G4a(float(R), b, v) for R in G4_R for b in ("arc_end", "line_50m") for v in G4A_V]
    write_csv("G4a.csv", G4A_COLS, a)
    b = [run_G4b(float(R), v1, v2) for R in G4_R for v1, v2 in G4B_V]
    return (a, b), "G4b.csv", G4B_COLS


# ---------------------------------------------------------------- G5 停止与驻留

def g5_geometry(geom):
    if geom == "straight":
        prims = [G.line((0.0, 0.0), (300.0, 0.0))]
        P = densify(prims)
        i_stop = int(round(150.0 / DS))
    else:
        prims = G.shape_turn(60, 120, 100, 100)
        P, ends = densify(prims, return_ends=True)
        i_stop = ends[0] + (ends[1] - ends[0]) // 2       # 弧中点（弧上弦数为偶数时恰在正中）
    return prims, P, i_stop


def run_G5(geom, v, H):
    prims, P, i_stop = g5_geometry(geom)
    s_stop = float(arclen(P)[i_stop])
    q = P[i_stop]
    res, wall = _timed(fly, P, ((0.0, v),), stops=((s_stop, H),))
    p, tau, rel, nonterm, spd, acc = _common(res, P[-1])
    dist = np.linalg.norm(p - q, axis=1)
    out = dict(geometry=geom, v_cmd=v, H_s=H, status=res.status, wall_s=wall, s_stop_m=s_stop,
               stop_x=float(q[0]), stop_y=float(q[1]), T_active_s=_T_active(tau),
               nominal_s=res.pieces[0].nominal_time_s, stops_done=res.pieces[0].stops_done)
    near = np.flatnonzero(rel & (dist <= STOP_NEAR_M))
    if len(near):
        i_in = near[0]
        held = np.flatnonzero((np.arange(len(tau)) >= i_in) & (dist <= HOLD_R) & (spd <= HOLD_V))
        if len(held):
            i_h = held[0]
            out["approach_s"] = (int(tau[i_h]) - int(tau[i_in])) / 1e6
            out["hold_start_s"] = int(tau[i_h]) / 1e6
            hold = (tau >= tau[i_h]) & (tau < tau[i_h] + int(round(H * 1e6)))
            out["hold_spread_m"] = _max(dist[hold])
    d = M.dwell_result(p, tau, TAU_R, extra_mask=dist <= STOP_MASK_M)
    out["dwell"] = bool(d["detected"])
    out["dwell_t_s"] = d["t_s"] if d["t_s"] is not None else math.nan
    out["dwell_total_s"] = d["total_duration_s"]
    return out


G5_COLS = ["geometry", "v_cmd", "H_s", "status", "approach_s", "hold_spread_m", "dwell", "wall_s",
           "hold_start_s", "dwell_t_s", "dwell_total_s", "s_stop_m", "stop_x", "stop_y", "stops_done",
           "T_active_s", "nominal_s"]


def stage_G5():
    return [run_G5(g, v, H) for g in ("straight", "arc60") for v in V_ALL for H in G5_H], "G5.csv", G5_COLS


# ---------------------------------------------------------------- 冒烟

SMOKE = [
    (1, "G1 R=20 v=10", "G1", (20.0, 10.0), {"v_meas_med": 7.803, "dev_steady_max": 0.114}),
    (2, "G1 R=60 v=4", "G1", (60.0, 4.0), {"v_meas_med": 4.001, "dev_steady_max": 0.001}),
    (3, "G1 R=240 v=10", "G1", (240.0, 10.0), {"v_meas_med": 10.001, "dev_steady_max": 0.002}),
    (4, "G3 U R=5 v=4", "G3", ("U", 5.0, 4.0), {"dwell": True}),
    (5, "G3 U R=10 v=4", "G3", ("U", 10.0, 4.0), {"dwell": True}),
    (6, "G3 U R=10 v=10", "G3", ("U", 10.0, 10.0), {"dwell": False}),
    (7, "G3 teardrop R=10 v=4", "G3", ("teardrop", 10.0, 4.0), {"dwell": True}),
    (8, "G3 teardrop R=20 v=4", "G3", ("teardrop", 20.0, 4.0), {"dwell": False}),
    (9, "straight 300 m v=8", "line", (8.0,), {"nominal_s": 41.5, "T_active_s": 43.9}),
]
SMOKE_TOL = {"v_meas_med": 0.05, "dev_steady_max": 0.05, "nominal_s": 0.3, "T_active_s": 0.3}


def run_line(v):
    P = densify([G.line((0.0, 0.0), (300.0, 0.0))])
    res, wall = _timed(fly, P, ((0.0, v),))
    return dict(status=res.status, nominal_s=res.pieces[0].nominal_time_s, T_active_s=_T_active(res.tau_us),
                wall_s=wall)


def stage_smoke():
    started = _now()
    t0 = time.perf_counter()
    rows, lines, all_ok = [], [], True
    for num, name, kind, args, ref in SMOKE:
        m = {"G1": run_G1, "G3": run_G3, "line": run_line}[kind](*args)
        ok_case = m["status"] == "ok"
        checks = []
        for key, want in ref.items():
            got = m[key]
            if isinstance(want, bool):
                ok = got is want
                checks.append(f"{key} 实测 {got} 参照 {want} {'✓' if ok else '✗'}")
            else:
                ok = abs(got - want) <= SMOKE_TOL[key]
                checks.append(f"{key} 实测 {got:.4f} 参照 {want} 容差 ±{SMOKE_TOL[key]} {'✓' if ok else '✗'}")
            ok_case &= ok
        all_ok &= ok_case
        rows.append({"case": num, "name": name, "status": m["status"], "pass": ok_case,
                     "measured": {k: m[k] for k in ref}, "reference": ref, "wall_s": m["wall_s"]})
        lines.append(f"{num}. {name}: status={m['status']}; " + "; ".join(checks) + f" → {'通过' if ok_case else '不通过'}")
    wall = time.perf_counter() - t0
    lines.append(f"冒烟检查：{'通过' if all_ok else '不通过'}（{sum(r['pass'] for r in rows)}/{len(rows)}），墙钟 {wall:.1f} s")
    text = "\n".join(lines)
    print(text)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "smoke.txt").write_text(f"# V8-10 冒烟检查 {started}，a_lat={A_LAT} a_lon={A_LON} τ={TAU_S}\n"
                                   "# 第 1–3 条 dev 只算稳态帧（arc_steady_mask 且 τ ≥ τ_r）\n" + text + "\n",
                                   encoding="utf-8")
    write_json("smoke.json", {"pass": all_ok, "params": {"a_lat": A_LAT, "a_lon": A_LON, "tau_s": TAU_S},
                              "tolerance": SMOKE_TOL, "cases": rows, "wall_s": wall, "git_head": git_head()})
    return 0 if all_ok else 1


# ---------------------------------------------------------------- 汇总

def _ok(r):
    return r["status"] == "ok"


def _min_tail_ok(keys_sorted, good):
    """网格中最小的值，使它和所有更大的值都满足 good；没有则 None。"""
    best = None
    for k in reversed(keys_sorted):
        if good(k):
            best = k
        else:
            break
    return best


def _vk(v):
    return f"{v:g}"


def _stats(x):
    x = np.asarray([v for v in x if v is not None and not math.isnan(v)], dtype=float)
    if not len(x):
        return {"n": 0}
    return {"n": int(len(x)), "median": float(np.median(x)), "p95": float(np.percentile(x, 95)),
            "max": float(x.max()), "min": float(x.min())}


def _maxv(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return max(vals) if vals else None


def stage_summary():
    g1, g2, g3 = read_csv("G1.csv"), read_csv("G2.csv"), read_csv("G3.csv")
    g4a, g4b, g5 = read_csv("G4a.csv"), read_csv("G4b.csv"), read_csv("G5.csv")
    flags = []

    # R2：任何一次 status ≠ ok
    for name, rows in (("G1", g1), ("G2", g2), ("G3", g3), ("G4a", g4a), ("G4b", g4b), ("G5", g5)):
        for r in rows:
            if not _ok(r):
                flags.append({"flag": "R2", "exp": name, "row": r})

    # R1：G1、G2、G4 跟踪偏离 > 0.5 m
    for name, rows, keys in (("G1", g1, ("dev_max",)), ("G2", g2, ("dev_max",)),
                             ("G4a", g4a, ("dev_max", "dev_max_whole")), ("G4b", g4b, ("dev_max",))):
        for r in rows:
            for key in keys:
                if r.get(key) is not None and r[key] > TUBE_M:
                    flags.append({"flag": "R1", "exp": name, "key": key, "value": r[key], "row": r})

    # R3：R_safe
    R_safe = {}
    for shape in G3_SHAPES:
        R_safe[shape] = {}
        for v in V_ALL:
            rows = {r["R_m"]: r for r in g3 if r["shape"] == shape and r["v_cmd"] == v}
            R_safe[shape][_vk(v)] = _min_tail_ok(sorted(rows), lambda R: _ok(rows[R]) and rows[R]["dwell"] is False)
            if R_safe[shape][_vk(v)] is None:
                flags.append({"flag": "R3", "shape": shape, "v_cmd": v})

    # R4：段边界与变速
    for r in g4a:
        if (r.get("dp_max") is not None and r["dp_max"] > R4_DP) or (r.get("dv_max") is not None and r["dv_max"] > R4_DV):
            flags.append({"flag": "R4", "exp": "G4a", "dp_max": r.get("dp_max"), "dv_max": r.get("dv_max"), "row": r})
    for r in g4b:
        if (r.get("bump") is not None and r["bump"] > R4_BUMP) or (r.get("dip") is not None and r["dip"] > R4_BUMP):
            flags.append({"flag": "R4", "exp": "G4b", "bump": r.get("bump"), "dip": r.get("dip"), "row": r})

    # H_min 与 Δ
    H_min = {}
    for geom in ("straight", "arc60"):
        H_min[geom] = {}
        for v in V_ALL:
            rows = {r["H_s"]: r for r in g5 if r["geometry"] == geom and r["v_cmd"] == v}
            H_min[geom][_vk(v)] = _min_tail_ok(sorted(rows), lambda H: _ok(rows[H]) and rows[H]["dwell"] is True)
    hs = [h for d in H_min.values() for h in d.values()]
    delta = (max(hs) - DWELL_BASE_S) if hs and all(h is not None for h in hs) else None

    # G6：名义用时误差
    # err_s = T_active − nominal − 各停留时长之和（G5 的中途停留 H + 终点保持 2 s）
    g6, all_err, all_rel = {}, [], []
    for name, rows in (("G1", g1), ("G2", g2), ("G3", g3), ("G4b", g4b), ("G5", g5)):
        err, rel = [], []
        for r in rows:
            if not _ok(r):
                continue
            e = r["T_active_s"] - r["nominal_s"] - TERMINAL_HOLD_S - (r["H_s"] if name == "G5" else 0.0)
            err.append(e)
            rel.append(e / r["nominal_s"])
        g6[name] = {"err_s": _stats(err), "rel": _stats(rel)}
        all_err += err
        all_rel += rel
    g6["all"] = {"err_s": _stats(all_err), "rel": _stats(all_rel)}

    def finite_abs_max(rows, key):
        vals = [abs(r[key]) for r in rows if r.get(key) is not None]
        return max(vals) if vals else None

    result = {
        "params": {"a_lat": A_LAT, "a_lon": A_LON, "velocity_response_time_s": TAU_S,
                   "guidance_sha256": GUIDANCE.sha256},
        "G1": {"max_abs_err": finite_abs_max(g1, "err"), "dev_max": _maxv(g1, "dev_max"),
               "sat_frac_max": _maxv(g1, "sat_frac"), "a_max": _maxv(g1, "a_max")},
        "G2": {"dev_max": _maxv(g2, "dev_max"), "a_max": _maxv(g2, "a_max"), "sat_frac_max": _maxv(g2, "sat_frac")},
        "R_safe_m": R_safe,
        "G4": {"dp_max": _maxv(g4a, "dp_max"), "dv_max": _maxv(g4a, "dv_max"), "bump_max": _maxv(g4b, "bump"),
               "dip_max": _maxv(g4b, "dip"), "dev_max_split": _maxv(g4a, "dev_max"),
               "dev_max_whole": _maxv(g4a, "dev_max_whole"), "dev_max_G4b": _maxv(g4b, "dev_max")},
        "H_min_s": H_min,
        "delta_s": delta,
        "G6": g6,
        "red_flags": flags,
        "git_head": git_head(),
    }
    write_json("result.json", result)
    print(json.dumps(_jsonable({k: v for k, v in result.items() if k != "red_flags"}), ensure_ascii=False, indent=1))
    print(f"红旗 {len(flags)} 条：" + ", ".join(sorted({f['flag'] for f in flags})))
    return 0


# ---------------------------------------------------------------- 入口

STAGES = {"G1": stage_G1, "G2": stage_G2, "G3": stage_G3, "G4": stage_G4, "G5": stage_G5}


def run_stage(name):
    started = _now()
    t0 = time.perf_counter()
    rows, csv_name, cols = STAGES[name]()
    wall = time.perf_counter() - t0
    if name == "G4":
        a, b = rows
        write_csv(csv_name, cols, b)
        rows = a + b
    else:
        write_csv(csv_name, cols, rows)
    write_timing(name, rows, wall, started)
    bad = [r for r in rows if r["status"] != "ok"]
    print(f"{name}: {len(rows)} 次，非 ok {len(bad)} 次，墙钟 {wall:.1f} s")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stage", required=True, choices=["smoke", *STAGES, "summary"])
    args = ap.parse_args()
    if args.stage == "smoke":
        return stage_smoke()
    if args.stage == "summary":
        return stage_summary()
    return run_stage(args.stage)


if __name__ == "__main__":
    sys.exit(main())
