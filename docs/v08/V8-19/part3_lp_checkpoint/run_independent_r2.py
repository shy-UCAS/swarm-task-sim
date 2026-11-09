"""Independent checks remain runnable after the selected-curve checkpoint failure."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
CODE = BASE / "Simulation-v08/Multi-UAV SimpleGC"
OUT = BASE / "_handoff/2026-11-08_V8-19_close_observation/run/diagnostics/part3_independent_tests_r2"
OUT.mkdir(exist_ok=False)
env = dict(os.environ)
env.update({k: "1" for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "PYTHONDONTWRITEBYTECODE")})
rows, start = [], time.perf_counter()
for name in ("test_preset_numeric_v19.py", "test_preset_local_geometry_v19.py", "test_extra_dwell_reference_v19.py"):
    assert (CODE / "tests/v08/V8-19" / name).is_file(), name
    begin = time.perf_counter()
    result = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/v08/V8-19", "-p", name, "-v"],
                            cwd=CODE, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (OUT / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8", newline="\n")
    rows.append({"file": name, "exit_code": result.returncode, "wall_s": time.perf_counter() - begin, "log": name + ".log"})
    print(json.dumps(rows[-1]), flush=True)
    if result.returncode:
        break
doc = {"wall_s": time.perf_counter() - start, "rows": rows, "all_zero_exit": len(rows) == 3 and all(r["exit_code"] == 0 for r in rows)}
(OUT / "summary.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
raise SystemExit(0 if doc["all_zero_exit"] else 3)
