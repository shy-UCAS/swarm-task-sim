"""Local kernel benchmark: synthetic airborne control, integration and memory output.

This is NOT end-to-end dataset throughput: mission compilation, geometric
analysis, labels, descriptions, hashes and file writing are outside its timing.
Each agent count runs in a fresh Python process. The first episode is cold with
respect to this process's episode execution; imports and OS cache flushing are
not timed. Remaining episodes are warm repeats in that same process.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from swarm_sim.fast_dynamics import FastDynamicsConfig, PlantState, SynchronousEngine, model_versions
from swarm_sim.fast_dynamics.engine import seconds_to_us


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _source_identity():
    paths = [ROOT / "scripts/benchmark_fast_dynamics.py"]
    paths.extend(ROOT / f"swarm_sim/fast_dynamics/{name}.py" for name in
                 ("__init__", "contracts", "controllers", "engine", "observations", "plants"))
    result = [{"path": path.relative_to(ROOT).as_posix(),
               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths]
    return {"files": result, "list_sha256": hashlib.sha256(_json_bytes(result)).hexdigest(),
            "method": "actual local source contents; no clean Git checkout assumed"}


def _system_snapshot():
    """Read-only Windows host counters, with explicit unavailable fallback."""
    result = {"status": "unavailable", "cpu_times_100ns": None,
              "physical_total_bytes": None, "physical_available_bytes": None,
              "commit_total_bytes": None, "commit_limit_bytes": None, "commit_peak_bytes": None}
    if os.name != "nt":
        result["reason"] = "Windows native host counters are unavailable on this platform"
        return result

    class FileTime(ctypes.Structure):
        _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_uint32), ("memory_load", ctypes.c_uint32),
                    ("total_phys", ctypes.c_uint64), ("avail_phys", ctypes.c_uint64),
                    ("total_page", ctypes.c_uint64), ("avail_page", ctypes.c_uint64),
                    ("total_virtual", ctypes.c_uint64), ("avail_virtual", ctypes.c_uint64),
                    ("avail_extended", ctypes.c_uint64)]

    class PerformanceInfo(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_uint32)] + [
            (name, ctypes.c_size_t) for name in
            ("commit_total", "commit_limit", "commit_peak", "physical_total", "physical_available",
             "system_cache", "kernel_total", "kernel_paged", "kernel_nonpaged", "page_size")
        ] + [(name, ctypes.c_uint32) for name in ("handle_count", "process_count", "thread_count")]

    unavailable = []
    idle, kernel, user = FileTime(), FileTime(), FileTime()
    if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        result["cpu_times_100ns"] = {name: (value.high << 32) + value.low
                                     for name, value in (("idle", idle), ("kernel", kernel), ("user", user))}
    else:
        unavailable.append("GetSystemTimes failed")
    memory = MemoryStatus(length=ctypes.sizeof(MemoryStatus))
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        result.update(physical_total_bytes=int(memory.total_phys), physical_available_bytes=int(memory.avail_phys))
    else:
        unavailable.append("GlobalMemoryStatusEx failed")
    performance = PerformanceInfo(cb=ctypes.sizeof(PerformanceInfo))
    if ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(performance), performance.cb):
        for name in ("commit_total", "commit_limit", "commit_peak"):
            result[f"{name}_bytes"] = int(getattr(performance, name) * performance.page_size)
    else:
        unavailable.append("GetPerformanceInfo failed")
    result["status"] = "available" if not unavailable else "partially_available"
    if unavailable:
        result["reason"] = "; ".join(unavailable)
    return result


def _cpu_busy_fraction(before, after):
    first, last = before["cpu_times_100ns"], after["cpu_times_100ns"]
    if first is None or last is None:
        return None
    total = (last["kernel"] - first["kernel"]) + (last["user"] - first["user"])
    if total <= 0:
        return None
    return 1 - (last["idle"] - first["idle"]) / total


def _hardware():
    processor = platform.processor()
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                processor = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    return {"cpu": processor, "logical_cpu_count": os.cpu_count(),
            "architecture": platform.machine(), "platform": platform.platform(),
            "initial_host_snapshot": _system_snapshot()}


def _simulate(config, agent_count, duration_us):
    positions = np.zeros((agent_count, 3))
    positions[:, 0] = np.arange(agent_count) * 10.0
    positions[:, 2] = 15.0
    engine = SynchronousEngine(config, PlantState(positions, np.zeros_like(positions), np.zeros_like(positions)))
    east = np.tile([5., 0., 0.], (agent_count, 1))
    north = np.tile([0., 5., 0.], (agent_count, 1))
    stopped = np.zeros_like(positions)
    while engine.time_us < duration_us:
        desired = east if engine.time_us * 3 < duration_us else (
            north if engine.time_us * 3 < duration_us * 2 else stopped)
        engine.step(desired, dt_us=min(config.engine.step_us, duration_us - engine.time_us))
    return engine


def _worker(agent_count, duration, repeats):
    config = FastDynamicsConfig()
    duration_us = seconds_to_us(duration)
    runs = []
    for repeat in range(repeats):
        gc.collect()
        before = _system_snapshot()
        cpu_started = time.process_time()
        started = time.perf_counter()
        engine = _simulate(config, agent_count, duration_us)
        elapsed = time.perf_counter() - started
        cpu_elapsed = time.process_time() - cpu_started
        after = _system_snapshot()
        canonical = np.concatenate((engine.state.p.ravel(), engine.state.v.ravel(), engine.state.a.ravel()))
        runs.append({"repeat_index": repeat, "temperature": "first_episode_in_fresh_process" if repeat == 0 else "warm",
                     "wall_time_s": elapsed, "process_cpu_time_s": cpu_elapsed,
                     "episode_real_time_factor": duration / elapsed,
                     "output_frames": len(engine.samples),
                     "end_us": engine.time_us,
                     "terminal_state_sha256": hashlib.sha256(canonical.tobytes()).hexdigest(),
                     "host_cpu_busy_fraction": _cpu_busy_fraction(before, after),
                     "host_before": before, "host_after": after})
        del engine
    warm = runs[1:]
    warm_wall = [run["wall_time_s"] for run in warm]
    warm_rtf = [run["episode_real_time_factor"] for run in warm]
    return {"agent_count": agent_count, "simulation_duration_s": duration, "runs": runs,
            "warm_summary": {"sample_count": len(warm), "wall_time_median_s": statistics.median(warm_wall),
                             "wall_time_p95_s": float(np.percentile(warm_wall, 95)),
                             "episode_real_time_factor_median": statistics.median(warm_rtf),
                             "episode_real_time_factor_p05": float(np.percentile(warm_rtf, 5)),
                             "episode_real_time_factor_p95": float(np.percentile(warm_rtf, 95)),
                             "percentile_method": "NumPy linear interpolation; four warm samples at default repeats=5"},
            "repeatability_pass": len({run["terminal_state_sha256"] for run in runs}) == 1}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=300., help="simulation seconds per episode (default 300)")
    parser.add_argument("--repeats", type=int, default=5, help="one first/cold episode plus warm repeats (default 5)")
    parser.add_argument("--agents", type=int, nargs="+", default=[2, 4, 8, 16])
    parser.add_argument("--output", type=Path, help="write JSON after all timed runs; stdout when omitted")
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not np.isfinite(args.duration) or args.duration <= 0:
        parser.error("--duration must be finite and positive")
    seconds_to_us(args.duration)
    if args.repeats < 2:
        parser.error("--repeats must be at least 2 to report warm statistics")
    if not args.agents or any(count < 1 for count in args.agents) or len(set(args.agents)) != len(args.agents):
        parser.error("--agents must contain unique positive counts")
    if args._worker:
        if len(args.agents) != 1:
            parser.error("internal worker requires one agent count")
        print(json.dumps(_worker(args.agents[0], args.duration, args.repeats), allow_nan=False))
        return

    config = FastDynamicsConfig().to_dict()
    identity = _source_identity()
    results = []
    started_utc = datetime.now(timezone.utc).isoformat()
    hardware = _hardware()
    for count in args.agents:
        command = [sys.executable, "-B", str(Path(__file__).resolve()), "--_worker", "--duration", str(args.duration),
                   "--repeats", str(args.repeats), "--agents", str(count)]
        completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        results.append(json.loads(completed.stdout))
    if identity != _source_identity():
        raise RuntimeError("benchmark source changed during measurements; rerun against one source snapshot")
    report = {"schema": "fast_dynamics_kernel_benchmark_v1", "started_utc": started_utc,
              "completed_utc": datetime.now(timezone.utc).isoformat(),
              "hardware": hardware,
              "runtime": {"python": sys.version, "python_executable": sys.executable, "numpy": np.__version__},
              "model_versions": model_versions(), "config": config,
              "config_sha256": hashlib.sha256(_json_bytes(config)).hexdigest(), "source_identity": identity,
              "measurement_contract": {
                  "scope": "synthetic control/plant kernel plus 10 Hz in-memory output; not dataset throughput",
                  "included": ["episode initialization", "velocity reference selection", "velocity controller",
                               "bounded constant-jerk integration", "synchronous array commit", "10 Hz state recording in memory"],
                  "excluded": ["Python process startup and imports", "episode teardown", "task compilation",
                               "semantic/quality analysis", "export", "audit", "facts/descriptions", "file writes", "source hashing"],
                  "episode_real_time_factor": "episode simulation seconds divided by timed wall-clock seconds; not agent-seconds",
                  "cold_definition": "first episode in a fresh worker process per count; imports excluded; OS cache not flushed",
                  "execution": "one worker at a time; shared non-exclusive host; no SITL and no host sleep",
                  "memory": "Windows commit is host committed memory, not process RSS; sampled before and after each timed run",
                  "cpu_load": "host-wide busy fraction from GetSystemTimes delta; not exclusive benchmark utilization",
                  "limitations": "four warm repeats give only a small-sample empirical p95; no production throughput claim"},
              "results": results}
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(json.dumps({"output": str(args.output.resolve()),
                          "warm_median_episode_rtf": {str(row["agent_count"]): row["warm_summary"]["episode_real_time_factor_median"]
                                                      for row in results}}, ensure_ascii=False))
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
