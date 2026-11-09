"""Related unchanged legacy tests after reference/dispatch/identity integration; one or two processes only."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
OUT = ROOT / "run/diagnostics/part3_old_tests_r2"
OUT.mkdir(exist_ok=False)
env = dict(os.environ)
env.update({key: "1" for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "PYTHONDONTWRITEBYTECODE")})
env["V8_15_WORKER_SELECTION"] = str(REPO / "docs/v08/V8-15/part4/worker_choice.json")
for version in (16, 17):
    env[f"V8_{version}_DATA_ROOT"] = str(BASE / "SwarmData")
    env[f"V8_{version}_DEVSET"] = str(REPO / "docs/v08/V8-03/devset_v08.json")
    env[f"V8_{version}_TEST_CACHE"] = str(ROOT / "run/cache/old_tests")
env["V8_18_DATA_ROOT"] = str(BASE / "SwarmData")
env["V8_18_DEVSET"] = str(REPO / "docs/v08/V8-03/devset_v08.json")
env["V8_18_CACHE"] = str(ROOT / "run/cache/old_tests")
env["V8_18_LAZY_TEST_OUT"] = str(ROOT / "run/diagnostics/part3_lazy_process_r2")
baseline = json.loads((REPO / "docs/v08/V8-19/part1/tests_summary.json").read_text(encoding="utf-8"))
rows, begin = [], time.perf_counter()
for item in baseline["latest_jobs"]:
    folder, name = item["folder"], item["file"]
    child_env = dict(env)
    if folder == "V8-18" and name == "test_preset_local_geometry_v18.py":
        child_env["PYTHONPATH"] = str(REPO / "Multi-UAV SimpleGC/tests/v08/V8-18")
        args = ["-m", "unittest", "test_preset_local_geometry_v18.InterfacePreset", "-v"]
    else:
        args = ["-m", "unittest", "discover", "-s", f"tests/v08/{folder}", "-p", name, "-v"]
    started = time.perf_counter()
    proc = subprocess.run([sys.executable, "-B", *args], cwd=REPO / "Multi-UAV SimpleGC", env=child_env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    log = f"{folder}_{name}.log"
    (OUT / log).write_text(proc.stdout + proc.stderr, encoding="utf-8", newline="\n")
    row = {"folder": folder, "file": name, "exit_code": proc.returncode, "wall_s": time.perf_counter() - started, "log": log}
    rows.append(row)
    print(json.dumps(row), flush=True)
result = {"wall_s": time.perf_counter() - begin, "rows": rows, "all_zero_exit": len(rows) == len(baseline["latest_jobs"]) and all(row["exit_code"] == 0 for row in rows),
    "old_scene_gate": "not repeated; accepted V8-18 replacement unchanged"}
(OUT / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"all_zero_exit": result["all_zero_exit"], "files": len(rows), "wall_s": result["wall_s"]}), flush=True)
raise SystemExit(0 if result["all_zero_exit"] else 3)
