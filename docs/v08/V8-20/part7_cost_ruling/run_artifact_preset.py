"""Run the original three artifact tests with their actual complete inputs."""
import re
import datetime
import subprocess
import time
from evidence_utils import *

assert not audit()
a = read(DOC / "acceptance.json")
assert len(a["outputs"]) == 2 and a["rerun"]
assert read(Path(a["rerun"]) / "reproduction.json")["all_equal"]
argv = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/v08/V8-20",
        "-p", "test_preset_local_artifacts_v20.py", "-v"]
env = dict(os.environ, V8_20_ACCEPTANCE=str(DOC / "acceptance.json"))
log = ROOT / "artifact_preset_cost_ruling_r1.log"
out = ROOT / "artifact_preset_cost_ruling_r1.json"
assert not log.exists() and not out.exists()
started = time.perf_counter()
with log.open("x", encoding="utf-8", newline="") as f:
    result = subprocess.Popen(argv, cwd=CODE, env=env, stdout=f, stderr=subprocess.STDOUT)
    job = {"phase": 7, "stage": "artifact_preset", "intent": "area_search", "round": "cost_ruling_r1",
           "workers": 1, "root_pid": result.pid, "wrapper_pid": os.getpid(), "status": "running",
           "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    dump(ROOT / "system_monitor/current_job.json", job)
    result.wait()
wall = time.perf_counter() - started
raw = log.read_text(encoding="utf-8")
match = re.search(r"Ran (\d+) tests? in", raw)
skipped = re.search(r"skipped=(\d+)", raw)
doc = {"exit_code": result.returncode, "tests_run": None if match is None else int(match[1]),
       "skipped": 0 if skipped is None else int(skipped[1]), "wall_s": wall,
       "argv": argv, "acceptance": str(DOC / "acceptance.json"), "raw_log_sha256": sha(log),
       "audit_changes": audit()}
dump(out, doc, exclusive=True)
job.update(status="finished", ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
           exit_code=result.returncode, wall_s=wall)
dump(ROOT / "system_monitor/current_job.json", job)
print(json.dumps(doc, ensure_ascii=False), flush=True)
raise SystemExit(result.returncode if not doc["audit_changes"] else 4)
