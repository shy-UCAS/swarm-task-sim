"""V8-06 仿真器标定脚本：用合成几何航线测量冻结点质量仿真器的执行情况。

用法（在 Multi-UAV SimpleGC 目录下）：
    python -B scripts/v08/v8_06_calibration.py --stage <smoke|A|D|derive1|B|C|E|H|derive2> [--workers N]

结果写到仓库根目录 docs/v08/V8-06/。速度一律区分 v_cmd（交给仿真器的期望巡航速度）与
v_meas（10 Hz 帧水平速度模长）。弯道上的减速是冻结仿真器的跟踪与限速特性，不代表真实无人机的转弯能力。
"""
import argparse
import csv
import datetime
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
import types
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
OUT = REPO / "docs" / "v08" / "V8-06"
TRACES = OUT / "traces"
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from v08.calibration import geometry as G  # noqa: E402
from v08.calibration import metrics as M  # noqa: E402
from v08.calibration import runner  # noqa: E402

ALT = 120.0
TAU_R = 20_000_000
TERM_R = 40.0
TUBE_M = 0.5                       # r3 6.6 跟踪管 reference.tracking_tube_m
CONT_DV = 0.005                    # 续跑误差门槛（m/s）
CONT_DP = 0.005                    # （m）
V_ALL = (4.0, 6.0, 8.0, 10.0)
A_R = (10, 15, 20, 25, 30, 40, 50, 60, 80, 100, 120, 160, 240, 360, 480, 720, 1000, 1500, 2500)
A_S = (2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 32, 48, 64)
D_LE = (2, 4, 6, 8, 10, 12, 15, 20, 30)
D_CHANGE = ((4.0, 10.0), (10.0, 4.0), (6.0, 8.0), (8.0, 6.0))
C_R = (10, 15, 20, 25, 30, 40, 50, 60, 80, 100)
EA_R = (30, 60, 120, 240, 480, 1000)
EA_V = ((10.0, 10.0), (4.0, 4.0), (10.0, 4.0), (4.0, 10.0))
EA_Q = (0.3, 0.5, 0.7)
EB_R = (30, 60, 120, 240)
EB_SA = (0, 5, 10, 20, 40, 60)
B_DPHI = 2 * math.pi + math.pi / 3
PART4_SIM_S = 190_000.0
CODE_FILES = ("v08/calibration/geometry.py", "v08/calibration/metrics.py", "v08/calibration/runner.py",
              "scripts/v08/v8_06_calibration.py", "v08/sim/adapter.py", "configs/v08/sim.json")


def default_workers():
    return max(1, min(12, (os.cpu_count() or 1) - 2))


# ================================================================ 几何

def prims_A(R):
    return G.shape_turn(R, 120.0, 100.0, 60.0)


def prims_C(shape, R):
    if shape == "U":
        return G.shape_turn(R, 180.0, 150.0, 150.0)
    if shape == "V150":
        return G.shape_turn(R, 150.0, 150.0, 150.0)
    if shape == "teardrop":
        return G.shape_teardrop(R, 150.0)
    raise ValueError(shape)


def prims_Ea(R):
    return G.shape_turn(R, 120.0, 100.0, 200.0)


def prims_Eb(R, s_a):
    prims = [G.line((-300.0, 0.0), (0.0, 0.0))]
    if s_a > 0:
        prims.append(G.line((0.0, 0.0), (s_a, 0.0)))
    prims += [G.arc((s_a, R), R, -math.pi / 2, math.pi / 2), G.line((s_a + R, R), (s_a + R, R + 200.0))]
    return prims


D_W = np.array([[-300.0, 0.0, ALT], [0.0, 0.0, ALT], [300.0, 0.0, ALT]])


def ea_E(W, q):
    n = len(W) - 3
    return 1 + math.floor(q * n + 0.5)


def polar_W(rho0, harmonics, spacing, table=None):
    if spacing == "adaptive":
        R_m, s_m = table
        P, _ = G.polar_loop_points_adaptive(rho0, harmonics, 0.0, B_DPHI,
                                            lambda R: float(G.interp_log(R, R_m, s_m)))
    else:
        P, _ = G.polar_loop_points(rho0, harmonics, 0.0, B_DPHI, float(spacing))
    return np.c_[P, np.full(len(P), ALT)]


def harmonics_json(h):
    return json.dumps([[float(a), int(k), float(psi)] for a, k, psi in h])


def harmonics_from_json(s):
    return [(float(a), int(k), float(psi)) for a, k, psi in json.loads(s)]


# ================================================================ 单次仿真的分析（在工作进程中执行）

def _pct(x, q):
    return float(np.percentile(x, q)) if len(x) else math.nan


def _stats(v):
    if len(v) == 0:
        return dict(v_meas_med=math.nan, v_meas_p05=math.nan, v_meas_p95=math.nan, v_meas_min=math.nan,
                     v_meas_max=math.nan, ripple=math.nan)
    med = _pct(v, 50)
    p05, p95 = _pct(v, 5), _pct(v, 95)
    return dict(v_meas_med=med, v_meas_p05=p05, v_meas_p95=p95, v_meas_min=float(v.min()),
                v_meas_max=float(v.max()), ripple=(p95 - p05) / med if med > 0 else math.nan)


def _max(x):
    return float(np.max(x)) if len(x) else math.nan


def _common(res, W):
    p = np.asarray(res.p)[:, :2]
    tau = np.asarray(res.tau_us)
    rel = tau >= TAU_R
    nonterm = M.away_from(p, np.asarray(W)[-1, :2], TERM_R)
    return p, tau, rel, nonterm, M.speed_xy(res.v)


def analyze_arc_A(res, job):
    W, prims, R = np.asarray(job["W"]), job["prims"], job["R"]
    p, tau, rel, nonterm, spd = _common(res, W)
    steady = rel & M.arc_steady_mask(p, (0.0, R), R, -math.pi / 2, 2 * math.pi / 3)
    dc = G.distance_to_path(p[steady], prims)
    out = dict(n_steady=int(steady.sum()), **_stats(spd[steady]))
    out.update(dev_curve_max=_max(dc), dev_curve_p99=_pct(dc, 99),
               dev_poly_max=_max(G.distance_to_polyline(p[steady], W)),
               dev_path_max=_max(G.distance_to_path(p[rel & nonterm], prims)),
               dwell=M.dwell_detected(p, tau, TAU_R, extra_mask=nonterm),
               T_active_s=(int(tau[-1]) - TAU_R) / 1e6)
    return out


def analyze_line_D(res, job):
    p, tau, rel, nonterm, spd = _common(res, job["W"])

    def first(mask):
        idx = np.flatnonzero(rel & mask)
        return (int(tau[idx[0]]) - TAU_R) / 1e6 if len(idx) else math.nan

    return dict(t_x0_s=first(p[:, 0] >= 0.0), t_x250_s=first(p[:, 0] >= 250.0),
                T_active_s=(int(tau[-1]) - TAU_R) / 1e6,
                overshoot_m=M.overshoot_along(p[rel], (300.0, 0.0), (1.0, 0.0)))


def _polar_dense(rho0, h):
    Pd, phid = G.polar_loop_points(rho0, h, 0.0, B_DPHI, 0.5)
    return Pd, phid


def polar_time_model(rho0, h, v_cmd, table_R, table_v, phi_lo, phi_hi):
    """0.5 m 加密曲线上 φ ∈ [phi_lo, phi_hi] 的各小段长度 ÷ 小段起点处 v_model 之和；另返回该段弧长。"""
    Pd, phid = _polar_dense(rho0, h)
    seg = (phid[:-1] >= phi_lo) & (phid[1:] <= phi_hi)
    lens = np.linalg.norm(np.diff(Pd, axis=0), axis=1)[seg]
    k = np.abs(G.polar_curvature(rho0, h, phid[:-1][seg]))
    vm = np.minimum(v_cmd, G.interp_log(1.0 / np.maximum(k, 1e-12), table_R, table_v))
    return float(np.sum(lens / vm)), float(np.sum(lens))


def analyze_polar_B(res, job):
    W, rho0, h, v = np.asarray(job["W"]), job["rho0"], job["harmonics"], job["v"]
    p, tau, rel, nonterm, spd = _common(res, W)
    prog = M.polar_progress(p, 0.0)
    steady = rel & (prog >= math.pi / 3) & (prog <= 2 * math.pi)
    Pd, _ = _polar_dense(rho0, h)
    dc = G.distance_to_polyline(p[steady], Pd)
    phi_grid = np.linspace(0.0, 2 * math.pi, 20001)
    Rloc = 1.0 / np.maximum(np.abs(G.polar_curvature(rho0, h, phi_grid)), 1e-12)
    out = dict(R_local_min_m=float(Rloc.min()), R_local_max_m=float(Rloc.max()), **_stats(spd[steady]))
    out.update(dev_curve_max=_max(dc), dev_curve_p99=_pct(dc, 99),
               dev_poly_max=_max(G.distance_to_polyline(p[steady], W)),
               dwell=M.dwell_detected(p, tau, TAU_R, extra_mask=nonterm),
               T_active_s=(int(tau[-1]) - TAU_R) / 1e6,
               ratio_med=math.nan, ratio_p05=math.nan, ratio_p95=math.nan,
               T_meas_s=math.nan, T_model_s=math.nan, T_naive_s=math.nan)
    if job["spacing"] == "adaptive":
        tR, tv = job["v_table"]
        k = np.abs(G.polar_curvature(rho0, h, prog[steady]))
        vm = np.minimum(v, G.interp_log(1.0 / np.maximum(k, 1e-12), tR, tv))
        ratio = spd[steady] / vm
        out.update(ratio_med=_pct(ratio, 50), ratio_p05=_pct(ratio, 5), ratio_p95=_pct(ratio, 95))
        i0 = np.flatnonzero(rel & (prog >= math.pi / 3))
        i1 = np.flatnonzero(rel & (prog >= 2 * math.pi))
        if len(i0) and len(i1):
            out["T_meas_s"] = (int(tau[i1[0]]) - int(tau[i0[0]])) / 1e6
        T_model, length = polar_time_model(rho0, h, v, tR, tv, math.pi / 3, 2 * math.pi)
        out.update(T_model_s=T_model, T_naive_s=length / v)
    return out


def analyze_turn_C(res, job):
    W, prims = np.asarray(job["W"]), job["prims"]
    p, tau, rel, nonterm, spd = _common(res, W)
    d = M.dwell_result(p, tau, TAU_R, extra_mask=nonterm)
    late = (tau >= TAU_R + 10_000_000) & nonterm
    return dict(dwell=bool(d["detected"]), dwell_t_s=d["t_s"] if d["t_s"] is not None else math.nan,
                v_meas_min=float(spd[late].min()) if late.any() else math.nan,
                dev_path_max=_max(G.distance_to_path(p[rel & nonterm], prims)),
                T_active_s=(int(tau[-1]) - TAU_R) / 1e6)


def analyze_window_E(res, job):
    W, prims = np.asarray(job["W"]), job["prims"]
    p, tau, rel, nonterm, spd = _common(res, W)
    out = dict(T_active_s=(int(tau[-1]) - TAU_R) / 1e6)
    if job["kind"] != "split":
        return out
    te = int(res.pieces[0].tau_end_us)
    win = (tau >= te - 10_000_000) & (tau <= te + 20_000_000) & nonterm
    if job.get("arc") is not None:
        c, R, th0, dth = job["arc"]
        sel = win & M.arc_steady_mask(p, c, R, th0, dth, margin_deg=0.0, max_dist=10.0)
    else:
        sel = win
    out.update(tau_E_s=te / 1e6, dev_curve_max=_max(G.distance_to_path(p[win], prims)),
               v_meas_min=float(spd[sel].min()) if sel.any() else math.nan,
               v_meas_max=float(spd[sel].max()) if sel.any() else math.nan)
    return out


def analyze_none(res, job):
    return dict(T_active_s=(int(np.asarray(res.tau_us)[-1]) - TAU_R) / 1e6)


ANALYSES = {"A": analyze_arc_A, "D": analyze_line_D, "B": analyze_polar_B, "C": analyze_turn_C,
            "E": analyze_window_E, "none": analyze_none}


def execute_job(job):
    """一次仿真：只有仿真本身计入 wall_s；仿真抛异常时 status 记为 error:<异常类名>。"""
    cfg = runner.config_with(extension_length_m=job["L_e"]) if job.get("L_e") is not None else None
    W = np.asarray(job["W"], dtype=float)
    t0 = time.perf_counter()
    try:
        if job["kind"] == "fly":
            res = runner.fly(W, job["v"], config=cfg)
        else:
            res = runner.fly_split(W, job["E"], job["v1"], job["v2"], mode=job["mode"], config=cfg)
        status = res.status
    except Exception as exc:  # noqa: BLE001 — 记录后继续其余仿真
        res, status = None, f"error:{type(exc).__name__}"
    wall = time.perf_counter() - t0
    out = {"id": job["id"], "status": status, "wall_s": wall, "sim_s": math.nan, "metrics": {}}
    if res is not None:
        out.update(sim_s=int(res.tau_us[-1]) / 1e6, tau_us=np.asarray(res.tau_us),
                   p=np.asarray(res.p)[:, :2].copy(), v=np.asarray(res.v)[:, :2].copy(),
                   tau_E_us=int(res.pieces[0].tau_end_us) if job["kind"] == "split" else None)
        out["metrics"] = ANALYSES[job["analysis"]](res, job)
    return out


def run_jobs(jobs, workers, label):
    started = time.perf_counter()
    results = {}
    if workers <= 1:
        for i, job in enumerate(jobs, 1):
            results[job["id"]] = execute_job(job)
            print(f"[{label}] {i}/{len(jobs)} {job['id']} {results[job['id']]['status']}", file=sys.stderr, flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(execute_job, job): job["id"] for job in jobs}
            for i, fut in enumerate(as_completed(futs), 1):
                r = fut.result()
                results[r["id"]] = r
                if i % 20 == 0 or i == len(jobs):
                    print(f"[{label}] {i}/{len(jobs)}", file=sys.stderr, flush=True)
    return results, time.perf_counter() - started


# ================================================================ 输入输出

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


def read_json(name):
    path = OUT / name
    if not path.exists():
        sys.exit(f"缺少前序阶段的输出 {path}，请先运行对应阶段")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(_jsonable(obj), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if math.isnan(float(x)) else float(x)
    return x


def save_trace(name, r):
    TRACES.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(TRACES / f"{name}.npz", tau_us=np.asarray(r["tau_us"], dtype=np.float32),
                        p_xy=np.asarray(r["p"], dtype=np.float32), v_xy=np.asarray(r["v"], dtype=np.float32))


def cpu_name():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
    except Exception:  # noqa: BLE001
        return platform.processor()


def git_head():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def code_hashes():
    return {f: hashlib.sha256((PROJECT / f).read_bytes()).hexdigest() for f in CODE_FILES}


def write_timing(stage, workers, results, wall_total, started_iso, extra=None):
    per = [{"id": k, "status": r["status"], "wall_s": r["wall_s"], "sim_s": r["sim_s"]}
           for k, r in sorted(results.items())]
    doc = {"stage": stage, "started": started_iso, "finished": datetime.datetime.now().isoformat(timespec="seconds"),
           "workers": workers, "cpu": cpu_name(), "cpu_count": os.cpu_count(), "python": sys.version.split()[0],
           "numpy": np.__version__, "git_head": git_head(), "code_sha256": code_hashes(),
           "n_sims": len(results), "total_sim_s": float(np.nansum([r["sim_s"] for r in results.values()])),
           "total_wall_s": wall_total, "per_sim": per}
    if extra:
        doc.update(extra)
    write_json(f"timing_{stage}.json", doc)


def ns(r):
    return types.SimpleNamespace(tau_us=r["tau_us"], p=r["p"], v=r["v"])


def compare(split, ref, lo, hi):
    if "tau_us" not in split or "tau_us" not in ref:
        return None
    return runner.compare_runs(ns(split), ns(ref), lo, hi)


def split_vs_ref(split, ref):
    """口径同实验 D：越过帧的第一帧值，以及窗口 [τ_E − 10 s, τ_E + 20 s] 的最大值。"""
    out = dict(dv_at=math.nan, dp_at=math.nan, dv_win=math.nan, dp_win=math.nan)
    te = split.get("tau_E_us")
    if te is None:
        return out
    at = compare(split, ref, te, te)
    win = compare(split, ref, te - 10_000_000, te + 20_000_000)
    if at:
        out.update(dv_at=at["dv_first"], dp_at=at["dp_first"])
    if win:
        out.update(dv_win=win["dv_max"], dp_win=win["dp_max"])
    return out


# ================================================================ 任务构造

def job_A(R, s, v, jid=None):
    prims = prims_A(R)
    W = G.build_waypoints(prims, s, ALT)
    return dict(id=jid or f"A_R{R}_s{s}_v{v:g}", kind="fly", W=W, v=v, analysis="A", prims=prims, R=float(R),
                params=dict(R_m=R, spacing_m=s, v_cmd=v, n_waypoints=len(W)))


def job_D(kind, v1, v2, L_e, jid):
    if kind == "unsplit":
        return dict(id=jid, kind="fly", W=D_W, v=v1, analysis="D", params=dict(kind=kind, v1=v1, v2=v2, L_e_m=None))
    return dict(id=jid, kind="split", W=D_W, E=1, v1=v1, v2=v2, mode="straight", L_e=L_e, analysis="D",
                params=dict(kind=kind, v1=v1, v2=v2, L_e_m=L_e))


def job_B(set_, rho0, h, v, spacing, table, v_table, jid):
    W = polar_W(rho0, h, spacing, table)
    return dict(id=jid, kind="fly", W=W, v=v, analysis="B", rho0=float(rho0), harmonics=h, spacing=spacing,
                v_table=v_table,
                params=dict(set=set_, rho0_m=rho0, harmonics=harmonics_json(h), v_cmd=v, spacing=spacing,
                            n_waypoints=len(W)))


def job_C(shape, R, s, v, jid=None):
    prims = prims_C(shape, R)
    W = G.build_waypoints(prims, s, ALT)
    return dict(id=jid or f"C_{shape}_R{R}_v{v:g}", kind="fly", W=W, v=v, analysis="C", prims=prims,
                params=dict(shape=shape, R_m=R, spacing_m=s, v_cmd=v))


def job_Ea(R, s, q, v1, v2, mode, jid):
    prims = prims_Ea(R)
    W = G.build_waypoints(prims, s, ALT)
    arc_ = ((0.0, float(R)), float(R), -math.pi / 2, 2 * math.pi / 3)
    if mode == "unsplit":
        return dict(id=jid, kind="fly", W=W, v=v1, analysis="E", prims=prims, arc=arc_,
                    params=dict(R_m=R, spacing_m=s, q=None, E=None, v1=v1, v2=v2, mode=mode))
    E = ea_E(W, q)
    return dict(id=jid, kind="split", W=W, E=E, v1=v1, v2=v2, mode=mode, analysis="E", prims=prims, arc=arc_,
                params=dict(R_m=R, spacing_m=s, q=q, E=E, v1=v1, v2=v2, mode=mode))


def job_Eb(R, s_a, s, v, unsplit, jid):
    prims = prims_Eb(R, s_a)
    W = G.build_waypoints(prims, s, ALT)
    base = dict(id=jid, W=W, analysis="E", prims=prims, arc=None,
                params=dict(R_m=R, s_a_m=s_a, spacing_m=s, v=v, mode="unsplit" if unsplit else "straight"))
    if unsplit:
        return dict(base, kind="fly", v=v)
    return dict(base, kind="split", E=1, v1=v, v2=v, mode="straight")


def load_curve_table():
    ct = read_json("curve_table.json")
    return ct


def best_s_of(ct):
    return {float(R): float(s) for R, s in zip(ct["R_m"], ct["best_spacing_m"])}


def v_curve_of(ct, R):
    return float(G.interp_log(R, ct["R_m"], ct["v_curve_m_s"]))


# ================================================================ 阶段：smoke

SMOKE_REF = [
    (1, "A", "R=240, s=24, v_cmd=10", {"v_meas_med": 5.681, "v_meas_p05": 5.680, "v_meas_p95": 6.357,
                                       "dev_curve_max": 0.303, "dev_poly_max": 0.248, "dwell": False}),
    (2, "A", "R=60, s=12, v_cmd=4", {"v_meas_med": 3.608, "dev_curve_max": 0.276, "dev_poly_max": 0.232,
                                     "dwell": False}),
    (3, "B", "rho0=300, [(30,2,0)], s=32, v_cmd=10", {"v_meas_med": 6.591, "v_meas_p05": 4.799,
                                                      "v_meas_p95": 9.053, "dev_curve_max": 0.539, "dwell": False}),
    (4, "C", "U, R=10, s=6, v_cmd=4", {"dwell": True}),
    (5, "C", "U, R=20, s=10, v_cmd=4", {"dwell": False}),
    (6, "D", "L_e=5, v=10", {"dv_at": 2.001, "dp_at": 0.556}),
    (7, "D", "L_e=30, v=10", {"dv_at": 0.0, "dp_at": 0.0, "dv_win": 0.0, "dp_win": 0.0}),
    (8, "E-a", "R=60, s=12, (10,10), q=0.3 (E=4), straight", {"dv_at": 3.866, "dev_curve_max": 1.222}),
    (9, "E-a", "R=60, s=12, (10,10), q=0.3 (E=4), continuation", {"dv_at": 0.0, "dp_at": 0.0,
                                                                   "dev_curve_max": 0.277}),
    (10, "E-b", "R=60, s_a=5, s=12, v=10", {"dv_win": 2.843, "dev_curve_max": 0.294}),
    (11, "E-b", "R=60, s_a=60, s=12, v=10", {"dv_win": 0.0, "dp_win": 0.0}),
]


def stage_smoke(workers):
    started = datetime.datetime.now().isoformat(timespec="seconds")
    jobs = [job_A(240, 24, 10.0, "s01_A"), job_A(60, 12, 4.0, "s02_A"),
            job_B("smoke", 300.0, [(30.0, 2, 0.0)], 10.0, 32, None, None, "s03_B"),
            job_C("U", 10, 6, 4.0, "s04_C"), job_C("U", 20, 10, 4.0, "s05_C"),
            job_D("unsplit", 10.0, 10.0, None, "s06_ref"), job_D("split", 10.0, 10.0, 5.0, "s06_split"),
            job_D("unsplit", 10.0, 10.0, None, "s07_ref"), job_D("split", 10.0, 10.0, 30.0, "s07_split"),
            job_Ea(60, 12, None, 10.0, 10.0, "unsplit", "s08_ref"),
            job_Ea(60, 12, 0.3, 10.0, 10.0, "straight", "s08_split"),
            job_Ea(60, 12, None, 10.0, 10.0, "unsplit", "s09_ref"),
            job_Ea(60, 12, 0.3, 10.0, 10.0, "continuation", "s09_split"),
            job_Eb(60, 5, 12, 10.0, True, "s10_ref"), job_Eb(60, 5, 12, 10.0, False, "s10_split"),
            job_Eb(60, 60, 12, 10.0, True, "s11_ref"), job_Eb(60, 60, 12, 10.0, False, "s11_split")]
    assert jobs[10]["E"] == 4 and jobs[12]["E"] == 4
    res, wall = run_jobs(jobs, workers, "smoke")
    for jid, r in res.items():
        if "tau_us" in r:
            save_trace(f"smoke_{jid}", r)

    def measured(case):
        tag = f"s{case:02d}"
        single = [k for k in res if k.startswith(tag)]
        statuses = {k: res[k]["status"] for k in single}
        if len(single) == 1:
            return statuses, dict(res[single[0]]["metrics"])
        split, ref = res[f"{tag}_split"], res[f"{tag}_ref"]
        m = dict(split["metrics"])
        m.update(split_vs_ref(split, ref))
        return statuses, m

    rows, ok_all = [], True
    for case, exp, desc, refs in SMOKE_REF:
        statuses, m = measured(case)
        st_ok = all(s == "ok" for s in statuses.values())
        ok_all &= st_ok
        rows.append(dict(case=case, experiment=exp, description=desc, metric="status",
                         value=";".join(f"{k}={v}" for k, v in sorted(statuses.items())), reference="ok",
                         tolerance="", passed=st_ok))
        for key, ref in refs.items():
            val = m.get(key)
            if isinstance(ref, bool):
                passed, tol = (val is not None and bool(val) == ref), "equal"
            elif ref == 0.0:
                passed, tol = (val is not None and not math.isnan(val) and abs(val) <= 1e-6), "<=1e-6"
            else:
                passed, tol = (val is not None and not math.isnan(val) and abs(val - ref) <= 0.05), "0.05"
            ok_all &= passed
            rows.append(dict(case=case, experiment=exp, description=desc, metric=key, value=val, reference=ref,
                             tolerance=tol, passed=passed))
    write_csv("smoke.csv", ["case", "experiment", "description", "metric", "value", "reference", "tolerance",
                            "passed"], rows)
    ratio = max(r["wall_s"] / r["sim_s"] for r in res.values() if r["sim_s"] and not math.isnan(r["sim_s"]))
    w4 = default_workers()
    proj = ratio * 1.2 * PART4_SIM_S / w4
    verdict = ok_all and proj <= 3 * 3600
    write_timing("smoke", workers, res, wall, started,
                 {"projection": {"max_wall_over_sim": ratio, "part4_sim_s": PART4_SIM_S, "part4_workers": w4,
                                 "projected_part4_wall_s": proj, "limit_s": 3 * 3600},
                  "checks_all_passed": ok_all, "smoke_passed": verdict})
    print(json.dumps({"checks_all_passed": ok_all, "max_wall_over_sim": ratio,
                      "projected_part4_wall_h": proj / 3600, "smoke_passed": verdict}, ensure_ascii=False))
    for r in rows:
        if not r["passed"]:
            print("未通过:", r, file=sys.stderr)


# ================================================================ 阶段：A、D、derive1

A_COLS = ["R_m", "spacing_m", "v_cmd", "n_waypoints", "status", "n_steady", "v_meas_med", "v_meas_p05",
          "v_meas_p95", "v_meas_min", "v_meas_max", "ripple", "dev_curve_max", "dev_curve_p99", "dev_poly_max",
          "dev_path_max", "dwell", "T_active_s", "wall_s"]


def a_grid():
    return [(R, s) for R in A_R for s in A_S if 0.5 * math.sqrt(R) <= s <= 3 * math.sqrt(R) and s <= math.pi * R / 6]


def stage_A(workers):
    started = datetime.datetime.now().isoformat(timespec="seconds")
    jobs = [job_A(R, s, v) for R, s in a_grid() for v in V_ALL]
    res, wall = run_jobs(jobs, workers, "A")
    rows = [dict(j["params"], status=res[j["id"]]["status"], wall_s=res[j["id"]]["wall_s"], **res[j["id"]]["metrics"])
            for j in jobs]
    write_csv("A_runs.csv", A_COLS, rows)
    write_timing("A", workers, res, wall, started)


D_COLS = ["kind", "v1", "v2", "L_e_m", "status", "tau_E_s", "dv_at", "dp_at", "dv_win", "dp_win", "c_s", "h_s",
          "overshoot_m", "penalty_s", "wall_s"]


def stage_D(workers):
    started = datetime.datetime.now().isoformat(timespec="seconds")
    jobs = [job_D("unsplit", v, v, None, f"D_unsplit_v{v:g}") for v in V_ALL]
    jobs += [job_D("split", v, v, float(L), f"D_split_v{v:g}_L{L}") for v in V_ALL for L in D_LE]
    jobs += [job_D("change", v1, v2, None, f"D_change_{v1:g}_{v2:g}") for v1, v2 in D_CHANGE]
    res, wall = run_jobs(jobs, workers, "D")
    c = {}
    rows = []
    for j in jobs:
        r, P = res[j["id"]], j["params"]
        m = r["metrics"]
        row = dict(P, status=r["status"], wall_s=r["wall_s"])
        if P["kind"] == "unsplit" and m:
            cv = m["t_x0_s"] - 300.0 / P["v1"]
            c[P["v1"]] = cv
            row.update(c_s=cv, h_s=m["T_active_s"] - 600.0 / P["v1"] - cv, overshoot_m=m["overshoot_m"])
        rows.append(row)
    for j, row in zip(jobs, rows):
        r, P = res[j["id"]], j["params"]
        if P["kind"] == "unsplit":
            continue
        row["tau_E_s"] = r["tau_E_us"] / 1e6 if r.get("tau_E_us") is not None else None
        if P["kind"] == "split":
            row.update(split_vs_ref(r, res[f"D_unsplit_v{P['v1']:g}"]))
        elif r["metrics"]:
            row["penalty_s"] = (r["metrics"]["t_x250_s"] - 300.0 / P["v1"] - 250.0 / P["v2"]
                                - c.get(P["v1"], math.nan))
    write_csv("D_runs.csv", D_COLS, rows)
    write_timing("D", workers, res, wall, started)


def _ok(r):
    return r["status"] == "ok"


def _max_present(values):
    vals = [v for v in values if v is not None]
    return max(vals) if vals else None


def _min_tail_ok(keys_sorted, good):
    """网格中最小的值，使它和所有更大的值都满足 good；没有则 None。"""
    best = None
    for k in reversed(keys_sorted):
        if good(k):
            best = k
        else:
            break
    return best


def stage_derive1():
    A = read_csv("A_runs.csv")
    D = read_csv("D_runs.csv")
    by = {(r["R_m"], r["spacing_m"], r["v_cmd"]): r for r in A}
    table = dict(R_m=[], best_spacing_m=[], v_curve_m_s=[], ripple_at_best=[], dev_curve_max_at_best_m=[],
                 dev_poly_max_at_best_m=[], v_meas_med_at_best_raw_m_s=[], usable_spacings_m=[])
    excluded = []
    for R in A_R:
        R = float(R)
        usable = [r for r in A if r["R_m"] == R and r["v_cmd"] == 10.0 and _ok(r)
                  and r["dev_curve_max"] is not None and r["dev_curve_max"] <= TUBE_M]
        if not usable:
            excluded.append(R)
            continue
        top = max(r["v_meas_p05"] for r in usable)
        s = min(r["spacing_m"] for r in usable if r["v_meas_p05"] >= top - 0.01)
        best = by[(R, s, 10.0)]
        rows_v = [by[(R, s, v)] for v in V_ALL]
        table["R_m"].append(R)
        table["best_spacing_m"].append(s)
        table["v_meas_med_at_best_raw_m_s"].append(best["v_meas_med"])
        table["v_curve_m_s"].append(10.0 if best["v_meas_med"] >= 9.9 else best["v_meas_med"])
        table["ripple_at_best"].append(best["ripple"])
        table["dev_curve_max_at_best_m"].append(_max_present(r["dev_curve_max"] for r in rows_v))
        table["dev_poly_max_at_best_m"].append(_max_present(r["dev_poly_max"] for r in rows_v))
        table["usable_spacings_m"].append(sorted(r["spacing_m"] for r in usable))
    vc = dict(zip(table["R_m"], table["v_curve_m_s"]))
    check = []
    for R, s in zip(table["R_m"], table["best_spacing_m"]):
        for v in (4.0, 6.0, 8.0):
            r = by[(R, s, v)]
            med = r["v_meas_med"]
            check.append(dict(R_m=R, spacing_m=s, v_cmd=v, status=r["status"], v_meas_med=med,
                              v_model=min(v, vc[R]), err=None if med is None else med - min(v, vc[R])))
    unsplit = {r["v1"]: r for r in D if r["kind"] == "unsplit"}
    L_e_min = {}
    for v in V_ALL:
        rows = {r["L_e_m"]: r for r in D if r["kind"] == "split" and r["v1"] == v}
        L_e_min[v] = _min_tail_ok(sorted(rows), lambda L: _ok(rows[L]) and rows[L]["dv_win"] is not None
                                  and rows[L]["dv_win"] <= CONT_DV and rows[L]["dp_win"] <= CONT_DP)
    doc = dict(table)
    doc.update(
        excluded_R_m=excluded,
        selection_rule="usable: v_cmd=10, status ok, dev_curve_max<=0.5 m; best_s=max v_meas_p05 (ties within "
                       "0.01 m/s -> smaller s); v_curve=v_meas_med at (R,best_s,v_cmd=10), >=9.9 -> 10. "
                       "dev_*_at_best = max over v_cmd 4/6/8/10",
        min_model_check=dict(max_abs_err_m_s=_max_present(abs(r["err"]) for r in check if r["err"] is not None),
                             rows=check),
        c_s_by_v={f"{v:g}": unsplit[v]["c_s"] for v in V_ALL},
        h_s_by_v={f"{v:g}": unsplit[v]["h_s"] for v in V_ALL},
        overshoot_m_by_v={f"{v:g}": unsplit[v]["overshoot_m"] for v in V_ALL},
        speed_change_penalty_s={f"{r['v1']:g}->{r['v2']:g}": r["penalty_s"] for r in D if r["kind"] == "change"},
        L_e_min_m_by_v={f"{v:g}": L_e_min[v] for v in V_ALL},
    )
    write_json("curve_table.json", doc)
    print(json.dumps({"R": table["R_m"], "best_s": table["best_spacing_m"], "v_curve": table["v_curve_m_s"],
                      "excluded": excluded, "L_e_min": doc["L_e_min_m_by_v"],
                      "min_model_max_abs_err": doc["min_model_check"]["max_abs_err_m_s"]}, ensure_ascii=False))


# ================================================================ 阶段：B、C、E、H

B_COLS = ["set", "rho0_m", "harmonics", "R_local_min_m", "R_local_max_m", "v_cmd", "spacing", "n_waypoints",
          "status", "v_meas_med", "v_meas_p05", "v_meas_p95", "v_meas_min", "v_meas_max", "ripple", "dev_curve_max",
          "dev_curve_p99", "dev_poly_max", "dwell", "ratio_med", "ratio_p05", "ratio_p95", "T_meas_s", "T_model_s",
          "T_naive_s", "T_active_s", "wall_s"]


def b_validation_curves():
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


def b_main_harmonics(rho0):
    return ([(0.10 * rho0, 2, 0.0)], [(0.25 * rho0, 3, 0.0)])


def stage_B(workers):
    started = datetime.datetime.now().isoformat(timespec="seconds")
    ct = load_curve_table()
    table = (ct["R_m"], ct["best_spacing_m"])
    v_table = (ct["R_m"], ct["v_curve_m_s"])
    jobs = []
    for rho0 in (300.0, 600.0):
        for hi, h in enumerate(b_main_harmonics(rho0)):
            for v in (6.0, 10.0):
                for sp in (16, 32, 48, "adaptive"):
                    jobs.append(job_B("main", rho0, h, v, sp, table, v_table, f"B_main_r{rho0:g}_h{hi}_v{v:g}_s{sp}"))
    curves, redraws = b_validation_curves()
    for ci, (rho0, h) in enumerate(curves):
        for v in (6.0, 10.0):
            jobs.append(job_B("validation", rho0, h, v, "adaptive", table, v_table, f"B_val{ci}_v{v:g}"))
    res, wall = run_jobs(jobs, workers, "B")
    rows = [dict(j["params"], status=res[j["id"]]["status"], wall_s=res[j["id"]]["wall_s"], **res[j["id"]]["metrics"])
            for j in jobs]
    write_csv("B_runs.csv", B_COLS, rows)
    for j in jobs:
        if j["params"]["set"] == "main" and j["spacing"] == "adaptive" and "tau_us" in res[j["id"]]:
            save_trace(j["id"], res[j["id"]])
    write_timing("B", workers, res, wall, started, {"validation_redraws": redraws})


C_COLS = ["shape", "R_m", "spacing_m", "v_cmd", "status", "dwell", "dwell_t_s", "v_meas_min", "dev_path_max",
          "T_active_s", "wall_s"]


def stage_C(workers):
    started = datetime.datetime.now().isoformat(timespec="seconds")
    bs = best_s_of(load_curve_table())
    jobs, skipped = [], []
    for shape in ("U", "V150", "teardrop"):
        for v in V_ALL:
            for R in C_R:
                if float(R) not in bs:
                    skipped.append(dict(shape=shape, R_m=R, v_cmd=v))
                    continue
                jobs.append(job_C(shape, R, bs[float(R)], v))
    res, wall = run_jobs(jobs, workers, "C")
    rows = [dict(j["params"], status=res[j["id"]]["status"], wall_s=res[j["id"]]["wall_s"], **res[j["id"]]["metrics"])
            for j in jobs]
    write_csv("C_runs.csv", C_COLS, rows)
    write_timing("C", workers, res, wall, started, {"skipped_no_curve_table_R": skipped})


EA_COLS = ["R_m", "spacing_m", "q", "E", "v1", "v2", "mode", "status", "tau_E_s", "v_target1", "v_target2",
           "dev_curve_max", "v_meas_min", "v_meas_max", "bump", "dip", "dv_at", "dp_at", "dv_win", "dp_win", "wall_s",
           "T_active_s"]
EB_COLS = ["R_m", "s_a_m", "spacing_m", "v", "mode", "status", "tau_E_s", "dv_win", "dp_win", "dev_curve_max",
           "v_meas_min", "v_meas_max", "wall_s", "T_active_s"]


def stage_E(workers):
    started = datetime.datetime.now().isoformat(timespec="seconds")
    ct = load_curve_table()
    bs = best_s_of(ct)
    jobs, skipped = [], []
    for R in EA_R:
        if float(R) not in bs:
            skipped.append(dict(exp="E-a", R_m=R))
            continue
        s = bs[float(R)]
        for v in (10.0, 4.0):
            jobs.append(job_Ea(R, s, None, v, v, "unsplit", f"Ea_ref_R{R}_v{v:g}"))
        for v1, v2 in EA_V:
            for mode in ("straight", "continuation"):
                for q in EA_Q:
                    jobs.append(job_Ea(R, s, q, v1, v2, mode, f"Ea_R{R}_{v1:g}_{v2:g}_{mode}_q{q}"))
    for R in EB_R:
        if float(R) not in bs:
            skipped.append(dict(exp="E-b", R_m=R))
            continue
        s = bs[float(R)]
        for s_a in EB_SA:
            for v in (6.0, 10.0):
                jobs.append(job_Eb(R, s_a, s, v, True, f"Eb_ref_R{R}_sa{s_a}_v{v:g}"))
                jobs.append(job_Eb(R, s_a, s, v, False, f"Eb_R{R}_sa{s_a}_v{v:g}"))
    res, wall = run_jobs(jobs, workers, "E")
    ea_rows, eb_rows = [], []
    for j in jobs:
        r, P = res[j["id"]], j["params"]
        row = dict(P, status=r["status"], wall_s=r["wall_s"], **r["metrics"])
        if j["id"].startswith("Ea"):
            vc = v_curve_of(ct, P["R_m"])
            row.update(v_target1=min(P["v1"], vc), v_target2=min(P["v2"], vc))
            if P["mode"] != "unsplit":
                if row.get("v_meas_max") is not None and not math.isnan(row["v_meas_max"]):
                    row["bump"] = row["v_meas_max"] - max(row["v_target1"], row["v_target2"])
                    row["dip"] = min(row["v_target1"], row["v_target2"]) - row["v_meas_min"]
                if P["v1"] == P["v2"]:
                    row.update(split_vs_ref(r, res[f"Ea_ref_R{P['R_m']}_v{P['v1']:g}"]))
            ea_rows.append(row)
        else:
            if P["mode"] != "unsplit":
                cmp_ = split_vs_ref(r, res[f"Eb_ref_R{P['R_m']}_sa{P['s_a_m']}_v{P['v']:g}"])
                row.update(dv_win=cmp_["dv_win"], dp_win=cmp_["dp_win"])
            eb_rows.append(row)
    write_csv("Ea_runs.csv", EA_COLS, ea_rows)
    write_csv("Eb_runs.csv", EB_COLS, eb_rows)
    splits = [j for j in jobs if j["id"].startswith("Ea_R") and res[j["id"]]["metrics"].get("dev_curve_max") is not None]
    splits.sort(key=lambda j: -np.nan_to_num(res[j["id"]]["metrics"]["dev_curve_max"], nan=-1.0))
    top = splits[:3]
    for j in top:
        save_trace(j["id"], res[j["id"]])
    write_timing("E", workers, res, wall, started,
                 {"skipped_no_curve_table_R": skipped, "traces_top_dev_curve": [j["id"] for j in top]})


H_COLS = ["case", "dp_max", "t_first_over_5cm_s", "nearest_waypoint", "turn_angle_deg", "wall_s"]


def r_safe_table(C):
    out = {}
    for shape in ("U", "V150", "teardrop"):
        out[shape] = {}
        for v in V_ALL:
            rows = {r["R_m"]: r for r in C if r["shape"] == shape and r["v_cmd"] == v}
            out[shape][f"{v:g}"] = _min_tail_ok(sorted(rows), lambda R: _ok(rows[R]) and rows[R]["dwell"] is False)
    return out


def _turn_angle(W, i):
    if i <= 0 or i >= len(W) - 1:
        return math.nan
    a, b = W[i] - W[i - 1], W[i + 1] - W[i]
    c = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def stage_H(workers):
    started = datetime.datetime.now().isoformat(timespec="seconds")
    ct = load_curve_table()
    bs = best_s_of(ct)
    rs = r_safe_table(read_csv("C_runs.csv"))
    cases = []
    for R in (60, 240):
        cases.append((f"A_R{R}", job_A(R, bs[float(R)], 10.0)))
    cases.append(("B_r300_h75k3_adaptive",
                  job_B("H", 300.0, [(75.0, 3, 0.0)], 10.0, "adaptive", (ct["R_m"], ct["best_spacing_m"]),
                        (ct["R_m"], ct["v_curve_m_s"]), "x")))
    for shape in ("U", "teardrop"):
        R = rs[shape]["10"] if rs[shape]["10"] is not None else 100.0
        cases.append((f"C_{shape}_R{R:g}", job_C(shape, int(R), bs[float(R)], 10.0)))
    jobs = []
    for name, j in cases:
        j0 = dict(j, id=f"H_{name}_orig", analysis="none")
        W1 = np.array(j["W"], dtype=float)
        W1[0, 1] += 0.001
        j1 = dict(j, id=f"H_{name}_pert", analysis="none", W=W1)
        jobs += [j0, j1]
    res, wall = run_jobs(jobs, workers, "H")
    rows = []
    for name, j in cases:
        a, b = res[f"H_{name}_orig"], res[f"H_{name}_pert"]
        row = dict(case=name, wall_s=a["wall_s"] + b["wall_s"])
        if "tau_us" in a and "tau_us" in b:
            W = np.asarray(j["W"], dtype=float)[:, :2]
            common, ia, ib = np.intersect1d(a["tau_us"], b["tau_us"], return_indices=True)
            keep = (common >= TAU_R) & M.away_from(a["p"][ia], W[-1], TERM_R)
            ia, ib, tt = ia[keep], ib[keep], common[keep]
            d = np.linalg.norm(a["p"][ia] - b["p"][ib], axis=1)
            row["dp_max"] = float(d.max()) if len(d) else math.nan
            over = np.flatnonzero(d > 0.05)
            if len(over):
                k = over[0]
                wi = int(np.argmin(np.linalg.norm(W - a["p"][ia[k]], axis=1)))
                row.update(t_first_over_5cm_s=int(tt[k]) / 1e6, nearest_waypoint=wi, turn_angle_deg=_turn_angle(W, wi))
        rows.append(row)
        for tag in ("orig", "pert"):
            if "tau_us" in res[f"H_{name}_{tag}"]:
                save_trace(f"H_{name}_{tag}", res[f"H_{name}_{tag}"])
    write_csv("H_runs.csv", H_COLS, rows)
    write_timing("H", workers, res, wall, started,
                 {"cases": [dict(case=n, **{k: j["params"].get(k) for k in ("R_m", "spacing_m", "shape", "rho0_m")})
                            for n, j in cases],
                  "statuses": {k: r["status"] for k, r in res.items()},
                  "note": "t_first_over_5cm_s 为编组统一时钟 τ/1e6（含释放前 20 s）"})


# ================================================================ 阶段：derive2

def _dist(x):
    x = np.asarray([v for v in x if v is not None and not math.isnan(v)], dtype=float)
    if not len(x):
        return dict(n=0)
    return dict(n=int(len(x)), median=float(np.median(x)), p95=_pct(x, 95), min=float(x.min()), max=float(x.max()))


def _elements_T(prims, v, ct):
    T = 0.0
    for p in prims:
        if p[0] == "line":
            T += math.hypot(p[2][0] - p[1][0], p[2][1] - p[1][1]) / v
        else:
            T += p[2] * abs(p[4]) / min(v, v_curve_of(ct, p[2]))
    return T


def stage_derive2():
    ct = load_curve_table()
    A, B, C = read_csv("A_runs.csv"), read_csv("B_runs.csv"), read_csv("C_runs.csv")
    D, Ea, Eb, H = read_csv("D_runs.csv"), read_csv("Ea_runs.csv"), read_csv("Eb_runs.csv"), read_csv("H_runs.csv")
    c = {float(k): v for k, v in ct["c_s_by_v"].items()}
    h = {float(k): v for k, v in ct["h_s_by_v"].items()}
    bs = best_s_of(ct)

    # ---- 1. 时间模型（实验 I）
    tm = {"A": [], "B": [], "C": [], "E": []}

    def add(exp, T_active, T_model_path, length, v, ident):
        T_model = T_model_path + c[v] + h[v]
        tm[exp].append(dict(id=ident, T_active_s=T_active, T_model_s=T_model, T_naive_s=length / v,
                            model_minus_1=T_active / T_model - 1.0, active_over_naive=T_active / (length / v)))

    for r in A:
        if _ok(r) and bs.get(r["R_m"]) == r["spacing_m"]:
            pr = prims_A(r["R_m"])
            add("A", r["T_active_s"], _elements_T(pr, r["v_cmd"], ct), G.path_length(pr), r["v_cmd"],
                f"R{r['R_m']:g}_v{r['v_cmd']:g}")
    for r in C:
        if _ok(r):
            pr = prims_C(r["shape"], r["R_m"])
            add("C", r["T_active_s"], _elements_T(pr, r["v_cmd"], ct), G.path_length(pr), r["v_cmd"],
                f"{r['shape']}_R{r['R_m']:g}_v{r['v_cmd']:g}")
    for r in Ea:
        if r["mode"] == "unsplit" and _ok(r):
            pr = prims_Ea(r["R_m"])
            add("E", r["T_active_s"], _elements_T(pr, r["v1"], ct), G.path_length(pr), r["v1"],
                f"Ea_R{r['R_m']:g}_v{r['v1']:g}")
    for r in Eb:
        if r["mode"] == "unsplit" and _ok(r):
            pr = prims_Eb(r["R_m"], r["s_a_m"])
            add("E", r["T_active_s"], _elements_T(pr, r["v"], ct), G.path_length(pr), r["v"],
                f"Eb_R{r['R_m']:g}_sa{r['s_a_m']:g}_v{r['v']:g}")
    for r in B:
        if r["spacing"] == "adaptive" and _ok(r):
            hh = harmonics_from_json(r["harmonics"])
            T_path, length = polar_time_model(r["rho0_m"], hh, r["v_cmd"], ct["R_m"], ct["v_curve_m_s"],
                                              -1.0, B_DPHI + 1.0)
            add("B", r["T_active_s"], T_path, length, r["v_cmd"], f"{r['set']}_r{r['rho0_m']:g}_v{r['v_cmd']:g}")
    time_model_error = {k: {"model_minus_1": _dist([x["model_minus_1"] for x in v]),
                            "active_over_naive": _dist([x["active_over_naive"] for x in v]), "rows": v}
                        for k, v in tm.items()}

    # ---- 2. 跟踪偏差汇总
    tracking = {
        "A_at_best_by_R": [dict(R_m=R, best_spacing_m=s, dev_curve_max_m=dc, dev_poly_max_m=dp)
                           for R, s, dc, dp in zip(ct["R_m"], ct["best_spacing_m"], ct["dev_curve_max_at_best_m"],
                                                   ct["dev_poly_max_at_best_m"])],
        "B_dev_curve_max": _dist([r["dev_curve_max"] for r in B if _ok(r)]),
        "B_adaptive_dev_curve_max": _dist([r["dev_curve_max"] for r in B if _ok(r) and r["spacing"] == "adaptive"]),
        "C_dev_path_max": _dist([r["dev_path_max"] for r in C if _ok(r)]),
        "Ea_split_dev_curve_max": _dist([r["dev_curve_max"] for r in Ea if r["mode"] != "unsplit"]),
        "Eb_split_dev_curve_max": _dist([r["dev_curve_max"] for r in Eb if r["mode"] != "unsplit"]),
    }

    # ---- 3. E 的结论表
    by_R_mode = []
    for R in sorted({r["R_m"] for r in Ea}):
        for mode in ("straight", "continuation"):
            rr = [r for r in Ea if r["R_m"] == R and r["mode"] == mode]

            def mx(key):
                vals = [r[key] for r in rr if r[key] is not None]
                return max(vals) if vals else None

            by_R_mode.append(dict(R_m=R, mode=mode, n=len(rr), dev_curve_max_m=mx("dev_curve_max"),
                                  bump_max_m_s=mx("bump"), dip_max_m_s=mx("dip"), dv_at_max_m_s=mx("dv_at"),
                                  n_dev_curve_over_tube=sum(1 for r in rr if r["dev_curve_max"] is not None
                                                            and r["dev_curve_max"] > TUBE_M)))
    conn = {}
    for v in (6.0, 10.0):
        conn[f"{v:g}"] = {}
        for R in sorted({r["R_m"] for r in Eb}):
            rows = {r["s_a_m"]: r for r in Eb if r["R_m"] == R and r["v"] == v and r["mode"] != "unsplit"}
            best = _min_tail_ok(sorted(rows), lambda sa: _ok(rows[sa]) and rows[sa]["dv_win"] is not None
                                and rows[sa]["dv_win"] <= CONT_DV and rows[sa]["dp_win"] <= CONT_DP)
            conn[f"{v:g}"][f"{R:g}"] = best if best is not None else "> 60"

    # ---- 掉头 R_safe、延伸段
    r_safe = r_safe_table(C)
    le = ct["L_e_min_m_by_v"]
    if any(v is None for v in le.values()):
        proposed, proposed_note = None, "某个 v 在网格内没有满足条件的 L_e，未给出"
    else:
        mx_le = max(le.values())
        larger = [L for L in D_LE if L > mx_le]
        proposed, proposed_note = (float(larger[0]), "网格中严格大于 max_v L_e,min(v) 的最小值") if larger \
            else (30.0, "max_v L_e,min(v) 已是 30 m，取 30，无余量")

    # ---- 红旗
    flags = []
    for shape, d in r_safe.items():
        for v, R in d.items():
            if R is None:
                flags.append(dict(id="F1", category="系统性破坏意图判据", source="C",
                                  detail=f"{shape} v_cmd={v}: R≤100 m 内没有 R_safe", data="C_runs.csv"))
    for r in B:
        if r["dwell"]:
            flags.append(dict(id="F1", category="系统性破坏意图判据", source="B",
                              detail=f"B {r['set']} rho0={r['rho0_m']:g} v_cmd={r['v_cmd']:g} spacing={r['spacing']} 判为驻留",
                              data="B_runs.csv"))
    for r in A:
        if r["R_m"] >= 60 and r["dwell"]:
            flags.append(dict(id="F1", category="系统性破坏意图判据", source="A",
                              detail=f"A R={r['R_m']:g} s={r['spacing_m']:g} v_cmd={r['v_cmd']:g} 判为驻留",
                              data="A_runs.csv"))
    for name, rows, rkey in (("A", A, "R_m"), ("C", C, "R_m"), ("Ea", Ea, "R_m"), ("Eb", Eb, "R_m"), ("B", B, None)):
        for r in rows:
            if not _ok(r) and (rkey is None or r[rkey] >= 15):
                flags.append(dict(id="F2", category="严重生成失败", source=name,
                                  detail=f"{name} 行 status={r['status']}: " + json.dumps(
                                      {k: r[k] for k in list(r)[:8]}, ensure_ascii=False), data=f"{name}_runs.csv"))
    for r in Ea:
        if r["mode"] == "continuation" and r["dev_curve_max"] is not None and r["dev_curve_max"] > TUBE_M:
            flags.append(dict(id="F2", category="严重生成失败", source="Ea",
                              detail=f"E-a continuation R={r['R_m']:g} q={r['q']} ({r['v1']:g},{r['v2']:g}) "
                                     f"dev_curve_max={r['dev_curve_max']:.4f} m > 0.5", data="Ea_runs.csv"))
    for R in ct["excluded_R_m"]:
        if R >= 15:
            flags.append(dict(id="F3", category="数据质量不达标", source="A",
                              detail=f"A R={R:g} 没有可用间距", data="A_runs.csv"))

    # ---- 需要负责人决定的事项（非红旗）
    cont = [r for r in Ea if r["mode"] == "continuation"]
    decisions = {
        "Ea_continuation_bump_m_s": _dist([r["bump"] for r in cont]),
        "Ea_continuation_dip_m_s": _dist([r["dip"] for r in cont]),
        "Ea_straight_bump_m_s": _dist([r["bump"] for r in Ea if r["mode"] == "straight"]),
        "Ea_straight_dip_m_s": _dist([r["dip"] for r in Ea if r["mode"] == "straight"]),
        "best_s_ripple_over_0.05": [dict(R_m=R, ripple=x) for R, x in zip(ct["R_m"], ct["ripple_at_best"])
                                    if x is not None and x > 0.05],
        "min_model_abs_err_over_0.1": [r for r in ct["min_model_check"]["rows"]
                                       if r["err"] is None or abs(r["err"]) > 0.1],
        "B_T_meas_over_T_model_outside_10pct": [
            dict(set=r["set"], rho0_m=r["rho0_m"], harmonics=r["harmonics"], v_cmd=r["v_cmd"],
                 ratio_minus_1=r["T_meas_s"] / r["T_model_s"] - 1.0)
            for r in B if r["spacing"] == "adaptive" and r["T_meas_s"] and r["T_model_s"]
            and abs(r["T_meas_s"] / r["T_model_s"] - 1.0) > 0.10],
    }

    result = {
        "schema": "v8-06-calibration-v1",
        "source_commit": git_head(),
        "curve_table": {k: ct[k] for k in ("R_m", "best_spacing_m", "v_curve_m_s", "ripple_at_best",
                                           "dev_curve_max_at_best_m", "dev_poly_max_at_best_m")},
        "min_model_check": ct["min_model_check"],
        "turnaround_R_safe_m": r_safe,
        "straight": {"c_s_by_v": ct["c_s_by_v"], "h_s_by_v": ct["h_s_by_v"], "overshoot_m_by_v": ct["overshoot_m_by_v"],
                     "speed_change_penalty_s": ct["speed_change_penalty_s"], "L_e_min_m_by_v": le},
        "proposed_extension_length_m": proposed,
        "proposed_extension_length_note": proposed_note,
        "boundary_on_arc": {"by_R_mode": by_R_mode},
        "connection_straight_min_m": conn,
        "time_model_error": {k: {kk: vv for kk, vv in v.items() if kk != "rows"} for k, v in time_model_error.items()},
        "perturbation": H,
        "red_flags": flags,
        "decision_items": decisions,
        "tracking_deviation": tracking,
        "excluded_R_m": ct["excluded_R_m"],
    }
    # 红旗涉及的实验不据此推出规则：对应项写"红旗：未给出"，测量值另存
    affects = {"A": ("curve_table", "min_model_check"), "C": ("turnaround_R_safe_m",),
               "Ea": ("boundary_on_arc",), "Eb": ("connection_straight_min_m",), "B": ("time_model_error",)}
    for key in sorted({k for f in flags for k in affects.get(f["source"], ())}):
        result[f"{key}_measured_red_flag"] = result[key]
        result[key] = "红旗：未给出"
    write_json("calibration_result.json", result)
    write_json("time_model_rows.json", {k: v["rows"] for k, v in time_model_error.items()})
    print(json.dumps({"red_flags": len(flags), "flags": [f["detail"] for f in flags][:20],
                      "proposed_extension_length_m": proposed, "r_safe": r_safe, "conn": conn,
                      "time_model": result["time_model_error"] if isinstance(result["time_model_error"], dict) else None},
                     ensure_ascii=False, indent=1))


# ================================================================ 入口

STAGES = {"smoke": stage_smoke, "A": stage_A, "D": stage_D, "derive1": stage_derive1, "B": stage_B, "C": stage_C,
          "E": stage_E, "H": stage_H, "derive2": stage_derive2}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stage", required=True, choices=list(STAGES))
    ap.add_argument("--workers", type=int, default=default_workers())
    args = ap.parse_args()
    fn = STAGES[args.stage]
    if args.stage.startswith("derive"):
        fn()
    else:
        fn(max(1, args.workers))


if __name__ == "__main__":
    main()
