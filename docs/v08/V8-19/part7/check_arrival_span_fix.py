"""Integration check: one group-span observation per successful contract, all other diagnostics identical."""
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
CODE = BASE / "Simulation-v08/Multi-UAV SimpleGC"
sys.path.insert(0, str(CODE))
from v08.runner.skeleton_monitoring import _distribution

read = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
diag = ROOT / "run/diagnostics"
before, after = read(diag / "analysis_r1/diagnostics.json"), read(diag / "analysis_r2/diagnostics.json")
old, new = copy.deepcopy(before), copy.deepcopy(after)
old_span = old["retained_distributions"].pop("member_arrival_span_s")
new_span = new["retained_distributions"].pop("member_arrival_span_s")
assert old == new, "unrelated diagnostics changed"
assert read(diag / "analysis_r1/five_intent_pairs.json") == read(diag / "analysis_r2/five_intent_pairs.json")
expected, members = [], 0
for folder in (ROOT / "run/out/full_r1", ROOT / "run/out/full_r1/diversity"):
    for row in read(folder / "records.json"):
        if not row["success"]:
            continue
        result = read(folder / "contracts" / row["contract_id"] / "result.json")
        times = [m["nominal_arrival_s"] for m in result["close_observation"]["members"].values()]
        expected.append(max(times) - min(times))
        members += len(times)
assert len(expected) == 300 and old_span["n"] == len(expected) + members and new_span == _distribution(expected)
gate_source = read(diag / "gates_4_r1/feint/watchdog.json")["source_sha256"]
source = {str(p.relative_to(CODE)): hashlib.sha256(p.read_bytes()).hexdigest()
          for sub in ("v08", "tools/v08") for p in (CODE / sub).rglob("*.py")}
changed = [k for k in source if source[k] != gate_source[k]]
only = str(Path("tools/v08/analyze_close_observation_v19.py"))
assert changed == [only], changed
doc = {"complete": True, "authority": "第3部分检查点裁定第4节：新增代码实现错误的无歧义修正",
       "phenomenon": "contract-level arrival span was added once per contract and again once per member",
       "correction": "exclude member_arrival_span_s from per-member metrics aggregation; keep the contract observation",
       "before": old_span, "after": new_span, "contract_samples": len(expected), "member_samples": members,
       "independent_expected_from_saved_member_arrival_times": _distribution(expected), "all_other_diagnostics_identical": True,
       "five_intent_pairs_identical": True, "changed_dedicated_analysis_file": only,
       "source_sha_before": gate_source[only], "source_sha_after": source[only], "all_runtime_source_unchanged": True,
       "production_artifacts_not_modified": True, "checked_utc": datetime.now(timezone.utc).isoformat()}
out = diag / "analysis_r2/arrival_span_fix.json"
assert not out.exists()
out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(doc, ensure_ascii=False))
