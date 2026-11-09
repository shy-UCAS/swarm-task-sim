"""Compare unchanged transit identity against the exact 7b16f96 function, without planning or cache writes."""
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
sys.path.insert(0, str(REPO / "Multi-UAV SimpleGC"))
from v08.motion import transit_chords as TC

source = subprocess.check_output(["git", "show", "7b16f96:Multi-UAV SimpleGC/v08/motion/transit_chords.py"], cwd=REPO, text=True, encoding="utf-8")
node = next(node for node in ast.parse(source).body if getattr(node, "name", None) == "query_identity")
namespace = dict(vars(TC))
exec(compile(ast.Module(body=[node], type_ignores=[]), "7b16f96-query_identity", "exec"), namespace)
old = namespace["query_identity"]
sets = [[(0., 0.)], [(0.1234567895, -0.1234567895)]]
for n in range(1, 13):
    sets.append([(float(i * 22.), float((i - n // 2) * 17.)) for i in range(n)])
rows = []
for context in ("fixture", "5db1c15759d7db1db8e46083087e2656"):
    for offsets in sets:
        ctx = SimpleNamespace(cache_key=context)
        baseline = old(ctx, "facility_01", offsets)
        default = TC.query_identity(ctx, "facility_01", offsets)
        explicit = TC.query_identity(ctx, "facility_01", offsets, intent="transit")
        new = TC.query_identity(ctx, "facility_01", offsets, intent="close_observation")
        rows.append({"context": context, "offsets": offsets,
            "transit_default_and_explicit_equal_baseline": baseline == default == explicit,
            "transit_qid": baseline[0], "close_qid": new[0],
            "close_identity_isolated": new[0] != baseline[0] and new[1]["intent"] == "close_observation" and new[1]["version"] == "close_observation-v19"})
result = {"baseline_commit": "7b16f96b39c6aae58e20c2a653321b67e156b1bf",
    "baseline_function_sha256": hashlib.sha256(ast.get_source_segment(source, node).encode("utf-8")).hexdigest(),
    "cases": len(rows), "all_legacy_equal": all(row["transit_default_and_explicit_equal_baseline"] for row in rows),
    "all_new_isolated": all(row["close_identity_isolated"] for row in rows), "rows": rows}
out = BASE / "_handoff/2026-11-08_V8-19_close_observation/run/diagnostics/part3_identity_audit_r1.json"
if out.exists():
    raise FileExistsError(out)
out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({key: result[key] for key in ("cases", "all_legacy_equal", "all_new_isolated")}))
raise SystemExit(0 if result["all_legacy_equal"] and result["all_new_isolated"] else 3)
