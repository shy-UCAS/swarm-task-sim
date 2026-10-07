"""Read-only evidence for report section (c) rolling-window treatment and (d) split audit.

Reads: tmp_v05/batch_execution_20261002/batch_loop.log (rolling snapshots printed per next call),
verification/v05_batch_20261002/control.json, verification/v05_batch_20261002/dataset_audit.json.
Writes tmp_v05/v05_final_20261004/rolling_and_audit_check.json.
"""
import collections
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BATCH = ROOT / "verification/v05_batch_20261002"
LOG = ROOT / "tmp_v05/batch_execution_20261002/batch_loop.log"

IDS = ["20261003T105214Z_fc0da71d", "20261003T183204Z_d8dab159", "20261003T192955Z_9a223f93",
       "20261004T142817Z_6fe3345d", "20261004T151251Z_6cfa3d43", "20261004T165156Z_a0d985eb",
       "20261004T191528Z_e277e726", "20261004T200803Z_7c34aa26"]

snapshots = collections.defaultdict(collections.Counter)
log_lines = 0
json_lines = 0
for line in open(LOG, encoding="utf-8", errors="replace"):
    log_lines += 1
    line = line.strip()
    if not line.startswith("{"):
        continue
    try:
        blob = json.loads(line)
    except ValueError:
        continue
    json_lines += 1
    for r in (blob.get("rolling") or {}).get("runs") or []:
        snapshots[r["run_id"]][json.dumps(r.get("reasons"), ensure_ascii=False)] += 1

control = json.load(open(BATCH / "control.json", encoding="utf-8"))
records = {r["run_id"]: r for r in control["records"]}
audit = json.load(open(BATCH / "dataset_audit.json", encoding="utf-8"))

out = dict(
    log_lines=log_lines,
    rolling_json_snapshots=json_lines,
    ineligible_rolling_reasons={rid: dict(snapshots.get(rid, {})) for rid in IDS},
    final_rolling_summary={k: v for k, v in control["rolling"].items() if k != "runs"},
    final_rolling_runs=control["rolling"]["runs"],
    record_keys=sorted(records[IDS[0]].keys()),
    audit_top_keys=sorted(audit.keys()),
)
out["audit_split_family_blocks"] = {
    k: audit[k] for k in audit
    if any(t in k.lower() for t in ("split", "family", "leak", "issue", "rate", "count"))}
for rid in IDS:
    out.setdefault("record_attempt_notes", {})[rid] = {
        k: v for k, v in records[rid].items() if any(t in k for t in ("roll", "anomal", "quality", "hard"))}

path = HERE / "rolling_and_audit_check.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True))
print("written:", path)
