"""One native diversity task before the expensive full batch; diagnostic output only."""
import json
import sys
import time
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
sys.path.insert(0, str(REPO / "Multi-UAV SimpleGC"))
import numpy as np
from v08.runner import joint_intent as JI
from v08.runner.close_observation_report import verify_saved_outputs
from v08.runner.monitoring import load_entries, write_json

entries = load_entries(REPO / "docs/v08/V8-03/devset_v08.json")
entry = next(e for e in entries if int(e["order"]) == 2)
out = ROOT / "run/diagnostics/part7_diversity_probe_r1"
out.mkdir(exist_ok=False)
start = time.perf_counter()
row = JI._pool_task(("diversity", entry, 0, 0, str(BASE / "SwarmData"), str(ROOT / "run/cache"), str(out), None, "close_observation"))
write_json(out / "row.json", row, indent=1)
assert not row.get("error"), row.get("error")
assert row["success"], "normal failure; report probe without entering the expensive batch"
for field in ("curve_before", "curve_after"):
    a = np.asarray(row[field], float)
    assert a.ndim == 2 and a.shape[1] == 2 and len(a) > 1 and np.isfinite(a).all(), field
write_json(out / "records.json", [row], indent=1)
disk = verify_saved_outputs(out, entries, BASE / "SwarmData", ROOT / "run/cache")
write_json(out / "disk_verification.json", disk, indent=1)
assert disk["passed"] and not disk["p0_violations"]
doc = {"complete": True, "diagnostic_only": True, "workers": 1, "contract_id": row["contract_id"],
       "group_size": row["group_size"], "wall_s": time.perf_counter() - start,
       "curve_before_points": len(row["curve_before"]), "curve_after_points": len(row["curve_after"]),
       "frechet_info": row["frechet_info"], "disk_verification": disk}
write_json(out / "summary.json", doc, indent=1)
print(json.dumps(doc), flush=True)
