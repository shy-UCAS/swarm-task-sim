"""Record one already-authorized formal invocation with independent resource job labels."""
import argparse
import datetime
import subprocess
import time
from evidence_utils import *

ap = argparse.ArgumentParser()
ap.add_argument("stage", choices=("skeleton", "quick", "full", "rerun"))
args = ap.parse_args()
stage = args.stage
assert not audit()
if stage != "rerun":
    assert read(ROOT / ("precheck_" + stage + "_cost_ruling_r1.json"))["passed"]
folder = {"skeleton": "skeleton", "quick": "quick", "full": "full", "rerun": "rerun"}[stage]
out = ROOT / folder / "area_cost_ruling_r1"
assert not out.exists(), out
workers = 1 if stage == "rerun" else 24
argv = [sys.executable, "-B", "tools/v08/run_area_search_v20.py", "--stage", stage,
        "--devset", str(REPO / "docs/v08/V8-03/devset_v08.json"), "--data-root", str(BASE / "SwarmData"),
        "--cache", str(ROOT / "cache"), "--out", str(out), "--workers", str(workers),
        "--prewarm-from", str(ROOT / "prewarm/area_cost_ruling_r1/prewarm.json")]
if stage == "rerun":
    argv += ["--keys", str(ROOT / "full/area_cost_ruling_r1/rerun_keys.json"),
             "--compare-to", str(ROOT / "full/area_cost_ruling_r1")]
watchpath = ROOT / (stage + "_watchdog_cost_ruling_r1.json")
watch = {"stage": stage, "workers": workers, "argv": argv, "out": str(out), "status": "running",
         "source_binding": read(ROOT / "part5_source_binding.json"),
         "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
dump(watchpath, watch, exclusive=True)
started = time.perf_counter()
with (ROOT / (stage + "_area_cost_ruling_r1.log")).open("x", encoding="utf-8", newline="") as log:
    proc = subprocess.Popen(argv, cwd=CODE, env=dict(os.environ), stdout=log, stderr=subprocess.STDOUT)
    job = {"phase": {"skeleton": 5, "quick": 6, "full": 7, "rerun": 7}[stage], "stage": stage,
           "intent": "area_search", "round": "cost_ruling_r1", "workers": workers,
           "out": str(out), "root_pid": proc.pid, "wrapper_pid": os.getpid(),
           "started_utc": watch["started_utc"], "status": "running"}
    watch["root_pid"] = proc.pid
    dump(watchpath, watch)
    dump(ROOT / "system_monitor/current_job.json", job)
    print(json.dumps({"started": stage, "workers": workers, "pid": proc.pid, "out": str(out)}), flush=True)
    code = proc.wait()
wall = time.perf_counter() - started
changes = audit()
watch.update(status="finished", exit_code=code, wall_s=wall,
             ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), audit_changes=changes)
dump(watchpath, watch)
job.update(status="finished", exit_code=code, wall_s=wall, ended_utc=watch["ended_utc"])
dump(ROOT / "system_monitor/current_job.json", job)
print(json.dumps({"finished": stage, "exit_code": code, "wall_s": wall, "audit_changes": changes}), flush=True)
raise SystemExit(code if not changes else 4)
