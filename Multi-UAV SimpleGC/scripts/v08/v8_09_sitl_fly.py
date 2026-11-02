"""V8-09 2.3：用 v0.6 的软件在环运行框架 swarm_sim.runner.run_scene 飞标定航线（单机、实时）。

只在调用期间把 swarm_sim.runner.mission_for 换成返回整条航线的函数，finally 中还原；
不改 swarm_sim/、ArducopterSITL/ 下的任何文件。运行目录写在 SwarmData\\v08_sitl_calib\\<飞行编号>\\，
提交到仓库的小文件写在 docs/v08/V8-09/flights/<飞行编号>/。

用法（在 Multi-UAV SimpleGC 目录下）:
    python -B scripts/v08/v8_09_sitl_fly.py v10_a250_dense10 [更多飞行编号 …]
    python -B scripts/v08/v8_09_sitl_fly.py --remaining      # 第 4.1 节的 11 次，按顺序，可续跑
    python -B scripts/v08/v8_09_sitl_fly.py --selftest       # 第 2.5 节的离线检查
"""
import argparse
import glob
import json
import math
import re
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                                       # Multi-UAV SimpleGC
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import swarm_sim.runner as runner  # noqa: E402
from swarm_sim.scenario import enu_to_geo  # noqa: E402
from v08.calibration.geometry import path_length  # noqa: E402

from v8_09_sitl_route import ALT_M, COMMANDS, route, waypoints  # noqa: E402

SWARM_OUT = REPO.parent / "SwarmData" / "v08_sitl_calib"
DOCS = REPO / "docs" / "v08" / "V8-09"
BINARY = ROOT / "ArducopterSITL" / "arducopter.exe"
PARM = ROOT / "ArducopterSITL" / "copter.parm"
SMOKE = "v10_a250_dense10"
REMAINING = ["v10_a250_dense25", "v10_a250_spline25", "v10_a100_dense10", "v10_a100_dense25", "v10_a100_spline25",
             "v6_a250_dense10", "v6_a250_dense25", "v6_a250_spline25", "v6_a100_dense10", "v6_a100_dense25",
             "v6_a100_spline25"]
PARAM_PREFIXES = ("WPNAV_", "PSC_", "ATC_ACCEL", "ANGLE_MAX")
EXTRA_PREFIXES = ("FENCE_",)                                 # 自加记录：确认地理围栏未启用
ENV_ERROR = re.compile(r"OSError|WinError 100(48|13)|address already in use|port", re.IGNORECASE)
BETA_RANGE = (0.95, 1.05)          # V8-09b 改动二 2a：排除时钟源接错（例如误开仿真加速）
WINDOW_S = 30.0                    # 2b：飞行窗口内每 30 s 一窗
WINDOW_TOL = 0.01                  # 2b：各窗斜率与 β 之差上限
VALID_MIN = 0.99
ID_RE = re.compile(r"v(\d+)_a(\d+)_(dense10|dense25|spline25)")


def parse_id(fid):
    m = ID_RE.fullmatch(fid)
    if not m:
        raise ValueError(f"飞行编号 {fid!r} 不符合 v{{v}}_a{{accel}}_{{方式}}")
    return int(m.group(1)), int(m.group(2)), m.group(3)


# ---------------------------------------------------------------- 任务（第 2.3 节，照写）

def mission(points, v, cmd, origin, start):              # points: (K, 3)，第 0 点 = 起点
    home_lat, home_lon = enu_to_geo(start[0], start[1], origin)
    items = [dict(command=16, frame=3, params=[0, 0, 0, 0], lat=home_lat, lon=home_lon, alt=0),
             dict(command=178, frame=2, params=[1, v, -1, 0], lat=0, lon=0, alt=0)]
    for i, q in enumerate(points[1:]):
        last = i == len(points) - 2
        lat, lon = enu_to_geo(q[0], q[1], origin)
        params = ([2 if last else 0, 1, 0, float("nan")] if cmd == 16 else [2 if last else 0, 0, 0, 0])
        items.append(dict(command=cmd, frame=3, params=params, lat=lat, lon=lon, alt=float(q[2])))
    return items


@contextmanager
def route_mission(points, v, cmd):
    """调用期间让 run_scene 上传整条航线；结束时（含异常）还原 swarm_sim.runner.mission_for。"""
    original = runner.mission_for

    def replacement(vehicle, target, origin):
        return mission(points, v, cmd, origin, (vehicle["east_m"], vehicle["north_m"]))

    runner.mission_for = replacement
    try:
        yield
    finally:
        runner.mission_for = original


def scenario_for(fid, v, points):
    end = points[-1]
    return dict(schema_version=1, scenario_id=fid,
                origin=dict(lat=37.50505899, lon=122.1660365, alt_msl_m=12),   # 取自仓库 scenarios/demo_1uav.json
                takeoff_alt_m=30, record_hz=10, min_separation_m=5, max_gap_s=0.5,
                timeout_s=1800, ready_timeout_s=120,
                vehicles=[dict(id="uav_01", sysid=1, east_m=-900.0, north_m=-900.0, heading_deg=90)],
                phases=[dict(name="calib", targets={"uav_01": dict(east_m=float(end[0]), north_m=float(end[1]),
                                                                   up_m=30, speed_m_s=v, hold_s=2)})])


def write_template(out_root, v, accel):
    path = out_root / "copter_v8_09.parm"
    path.write_text(PARM.read_text(encoding="utf-8") + f"\nWPNAV_SPEED {100 * v}\nWPNAV_ACCEL {accel}\n",
                    encoding="utf-8")
    return path


# ---------------------------------------------------------------- 续跑与飞行

def _load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def completed_run(out_root):
    """输出目录下最新一个 status = completed 且有 processed.csv 的运行目录。"""
    found = []
    for meta in sorted(out_root.glob("*/metadata.json")):
        try:
            m = _load_json(meta)
        except (OSError, ValueError):
            continue
        if m.get("status") == "completed" and (meta.parent / "processed.csv").is_file():
            found.append(meta.parent)
    return found[-1] if found else None


def fly(fid):
    v, accel, mode = parse_id(fid)
    out_root = SWARM_OUT / fid
    run_dir = completed_run(out_root) if out_root.is_dir() else None
    attempts = []
    if run_dir is not None:
        print(f"[{fid}] 已有完成的运行 {run_dir.name}，跳过飞行", flush=True)
        attempts.append(dict(run_dir=run_dir.name, status="completed", skipped=True))
    else:
        out_root.mkdir(parents=True, exist_ok=True)
        template = write_template(out_root, v, accel)
        points = waypoints(mode)
        for attempt in (1, 2):
            started = time.perf_counter()
            print(f"[{fid}] 第 {attempt} 次尝试，航点 {len(points)} 个，命令 {COMMANDS[mode]}", flush=True)
            with route_mission(points, v, COMMANDS[mode]):
                directory, metadata, quality = runner.run_scene(scenario_for(fid, v, points), out_root, BINARY,
                                                                template)
            run_dir = Path(directory)
            attempts.append(dict(run_dir=run_dir.name, status=metadata.get("status"), error=metadata.get("error"),
                                 analysis_error=quality.get("analysis_error"),
                                 wall_s=round(time.perf_counter() - started, 1)))
            if metadata.get("status") == "completed":
                break
            if attempt == 1 and ENV_ERROR.search(str(metadata.get("error", ""))):
                print(f"[{fid}] 环境错误，重试一次：{metadata.get('error')}", flush=True)
                continue
            break
    check = check_run(fid, run_dir, v, accel, attempts)
    export_small(fid, run_dir, check)
    print(f"[{fid}] 检查 {'通过' if check['all_pass'] else '未通过'}：{json.dumps(check['summary'], ensure_ascii=False)}",
          flush=True)
    return check


# ---------------------------------------------------------------- 每次飞行后的检查（第 2.3 节）

def read_bin_params(run_dir):
    from pymavlink.DFReader import DFReader_binary
    bins = sorted(glob.glob(str(run_dir / "sitl" / "uav_01" / "logs" / "*.BIN")))
    if len(bins) != 1:
        return dict(bin_files=[Path(b).name for b in bins], error=f"应恰好 1 个 BIN，实际 {len(bins)} 个")
    log = DFReader_binary(bins[0])
    params, firmware = {}, None
    while True:
        m = log.recv_match(type=["PARM", "MSG"])
        if m is None:
            break
        if m.get_type() == "PARM":
            params[m.Name] = float(m.Value)
        elif firmware is None and "ArduCopter" in str(m.Message):
            firmware = str(m.Message)
    keep = {k: params[k] for k in sorted(params) if k.startswith(PARAM_PREFIXES)}
    extra = {k: params[k] for k in sorted(params) if k.startswith(EXTRA_PREFIXES)}
    return dict(bin_files=[Path(bins[0]).name], bin_bytes=Path(bins[0]).stat().st_size, firmware=firmware,
                params=keep, extra_params=extra, param_count=len(params))


def _window_slopes(b, h, start, end):
    """飞行窗口 [start, end]（主机时刻）内每 30 s 一窗的斜率；不足 30 s 的尾窗并入前一窗。"""
    edges = list(np.arange(start, end, WINDOW_S)) + [end]
    if len(edges) > 2 and edges[-1] - edges[-2] < WINDOW_S:
        del edges[-2]
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (h >= lo) & (h <= hi)
        if sel.sum() >= 3:
            out.append(dict(host_from_s=float(lo - start), host_to_s=float(hi - start), packets=int(sel.sum()),
                            slope=float(np.polyfit(b[sel], h[sel], 1)[0])))
    return out


def timebase_slope(run_dir, meta):
    """全程拟合 host = α + β·boot（V8-09 2.3 第 2 条的斜率即 β），以及飞行窗口内的分窗斜率（V8-09b 改动二）。"""
    boot, host = [], []
    with open(run_dir / "raw" / "uav_01.jsonl", encoding="utf-8") as fh:
        for line in fh:
            pkt = json.loads(line)
            msg = pkt["message"]
            if msg.get("mavpackettype") == "GLOBAL_POSITION_INT":
                boot.append(msg["time_boot_ms"] / 1000.0)
                host.append(pkt["recv_monotonic_s"])
    if len(boot) < 2:
        return dict(packets=len(boot), slope=None, windows=[])
    b, h = np.asarray(boot), np.asarray(host)
    slope, icpt = np.polyfit(b, h, 1)
    resid = h - (slope * b + icpt)
    res = dict(packets=len(boot), slope=float(slope), intercept=float(icpt),
               resid_p95_s=float(np.percentile(np.abs(resid), 95)), resid_max_s=float(np.abs(resid).max()),
               boot_span_s=float(b[-1] - b[0]), windows=[])
    start, end = meta.get("flight_epoch_monotonic_s"), meta.get("mission_end_monotonic_s")
    if start is not None and end is not None and end > start:
        res["windows"] = _window_slopes(b, h, start, end)
    return res


def valid_fraction(run_dir):
    import csv
    n = ok = 0
    with open(run_dir / "processed.csv", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            n += 1
            ok += row["valid"] == "1"
    return dict(rows=n, valid_rows=ok, fraction=ok / n if n else None)


def check_run(fid, run_dir, v, accel, attempts):
    meta = _load_json(run_dir / "metadata.json") if (run_dir / "metadata.json").is_file() else {}
    res = dict(flight=fid, run_dir=str(run_dir), attempts=attempts)
    try:
        prm = read_bin_params(run_dir)
    except Exception as exc:                                              # 读不了 BIN：记为未通过
        prm = dict(error=f"{type(exc).__name__}: {exc}")
    p = prm.get("params", {})
    res["params"] = dict(expected=dict(WPNAV_SPEED=100 * v, WPNAV_ACCEL=accel),
                         actual=dict(WPNAV_SPEED=p.get("WPNAV_SPEED"), WPNAV_ACCEL=p.get("WPNAV_ACCEL")),
                         error=prm.get("error"),
                         pass_=p.get("WPNAV_SPEED") == 100 * v and p.get("WPNAV_ACCEL") == accel)
    try:
        tb = timebase_slope(run_dir, meta)
    except Exception as exc:
        tb = dict(error=f"{type(exc).__name__}: {exc}", slope=None, windows=[])
    beta = tb.get("slope")
    tb["beta"] = beta
    tb["pass_2a"] = beta is not None and BETA_RANGE[0] <= beta <= BETA_RANGE[1]
    ws = [w["slope"] for w in tb.get("windows", [])]
    tb["window_slope_min"] = min(ws) if ws else None
    tb["window_slope_max"] = max(ws) if ws else None
    tb["window_max_abs_diff"] = max(abs(s - beta) for s in ws) if ws and beta is not None else None
    tb["pass_2b"] = tb["window_max_abs_diff"] is not None and tb["window_max_abs_diff"] <= WINDOW_TOL
    tb["pass_"] = tb["pass_2a"] and tb["pass_2b"]
    res["timebase"] = tb
    try:
        vf = valid_fraction(run_dir)
    except Exception as exc:
        vf = dict(error=f"{type(exc).__name__}: {exc}", fraction=None)
    vf["pass_"] = vf.get("fraction") is not None and vf["fraction"] >= VALID_MIN
    res["valid"] = vf
    res["status"] = dict(value=meta.get("status"), error=meta.get("error"), pass_=meta.get("status") == "completed")
    res["all_pass"] = all(res[k]["pass_"] for k in ("params", "timebase", "valid", "status"))
    res["summary"] = dict(params=res["params"]["pass_"], beta=beta, pass_2a=tb["pass_2a"],
                          window_max_abs_diff=tb["window_max_abs_diff"], pass_2b=tb["pass_2b"],
                          valid=vf.get("fraction"), status=meta.get("status"))
    res["_bin"] = prm
    res["_meta"] = meta
    return res


def export_small(fid, run_dir, check):
    out = DOCS / "flights" / fid
    out.mkdir(parents=True, exist_ok=True)
    if (run_dir / "processed.csv").is_file():
        shutil.copyfile(run_dir / "processed.csv", out / "processed.csv")
    prm, meta = check.pop("_bin"), check.pop("_meta")
    (out / "check.json").write_text(json.dumps(check, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "params.json").write_text(json.dumps(prm, ensure_ascii=False, indent=1), encoding="utf-8")
    sitl = meta.get("sitl", {})
    excerpt = dict(status=meta.get("status"), error=meta.get("error"), elapsed_s=meta.get("elapsed_s"),
                   flight_epoch_monotonic_s=meta.get("flight_epoch_monotonic_s"),
                   mission_end_monotonic_s=meta.get("mission_end_monotonic_s"),
                   sitl=dict(binary=sitl.get("binary"), sha256=sitl.get("sha256")))
    (out / "metadata_excerpt.json").write_text(json.dumps(excerpt, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- 第 2.5 节离线检查

def selftest():
    ok = True

    def report(name, passed, detail):
        nonlocal ok
        ok &= bool(passed)
        print(f"[{'通过' if passed else '未通过'}] {name}: {detail}", flush=True)

    prims = route()
    L = path_length(prims)
    report("航线长度 2762 ± 1 m", abs(L - 2762) <= 1, f"{L:.3f} m，{len(prims)} 个元素")
    origin = dict(lat=37.50505899, lon=122.1660365, alt_msl_m=12)
    for mode, expect in (("dense10", 129), ("dense25", 60), ("spline25", 60)):
        pts = waypoints(mode)
        items = mission(pts, 10, COMMANDS[mode], origin, (-900.0, -900.0))
        cmds = {it["command"] for it in items[2:]}
        report(f"{mode} 任务条数 2 + {expect}", len(items) == 2 + expect and cmds == {COMMANDS[mode]},
               f"{len(items)} 条，航点命令 {sorted(cmds)}，终点停留 {items[-1]['params'][0]}")
    pts = waypoints("dense10")
    xy = np.asarray(pts)[:, :2]
    report("坐标范围在 ±2000 m 内", np.abs(xy).max() < 2000,
           f"east {xy[:, 0].min():.1f}…{xy[:, 0].max():.1f}，north {xy[:, 1].min():.1f}…{xy[:, 1].max():.1f}")
    original = runner.mission_for
    try:
        with route_mission(pts, 10, 16):
            if runner.mission_for is original:
                raise AssertionError("上下文内未替换")
            raise RuntimeError("自测：上下文内抛出的异常")
    except RuntimeError:
        pass
    report("异常后还原 swarm_sim.runner.mission_for", runner.mission_for is original,
           f"还原后为 {runner.mission_for.__module__}.{runner.mission_for.__qualname__}")
    sc = scenario_for(SMOKE, 10, pts)
    from swarm_sim.scenario import validate
    validate(sc)
    report("schema 1 场景通过 validate", True, f"目标 ({sc['phases'][0]['targets']['uav_01']['east_m']:.1f}, "
           f"{sc['phases'][0]['targets']['uav_01']['north_m']:.1f})")
    tmpl = PARM.read_text(encoding="utf-8") + "\nWPNAV_SPEED 1000\nWPNAV_ACCEL 250\n"
    report("参数模板 = copter.parm + 两行", tmpl.endswith("\nWPNAV_SPEED 1000\nWPNAV_ACCEL 250\n"),
           f"{len(tmpl.splitlines())} 行")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("flights", nargs="*")
    ap.add_argument("--remaining", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--max-invalid", type=int, default=3)
    args = ap.parse_args()
    if args.selftest:
        sys.exit(0 if selftest() else 1)
    flights = (REMAINING if args.remaining else []) + list(args.flights)
    for fid in flights:
        parse_id(fid)
    invalid = []
    for fid in flights:
        check = fly(fid)
        if not check["all_pass"]:
            invalid.append(fid)
            print(f"[{fid}] 标记为无效（累计 {len(invalid)} 次）", flush=True)
            if len(invalid) >= args.max_invalid:
                print(f"累计 {len(invalid)} 次无效，停止：{invalid}", flush=True)
                sys.exit(2)
    print(f"完成 {len(flights)} 次；无效 {invalid}", flush=True)


if __name__ == "__main__":
    main()
