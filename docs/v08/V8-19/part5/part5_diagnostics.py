"""Read-only part5 diagnostic reduction; does not change production acceptance rules."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
CODE = BASE / "Simulation-v08/Multi-UAV SimpleGC"
sys.path.insert(0, str(CODE))
from v08.runner.skeleton_monitoring import _distribution

read = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
folder = ROOT / "run/out/skeleton_r1"
rows, summary = read(folder / "records.json"), read(folder / "summary.json")
manifest = read(BASE / "Simulation-v08/docs/v08/V8-19/manifest.json")
assert len(rows) == 200 and {r["contract_id"] for r in rows} == set(manifest["keys"]["full200"])
stats, stages, conditions, selected_violations, screen_violations = {}, Counter(), Counter(), [], []
selected = []
def add(name, value):
    if value is not None:
        stats.setdefault(name, []).append(value)
for r in rows:
    for a in r["attempt_log"]:
        stages[a["stage"]] += 1
        diag = a.get("dwell_diagnostics") or {}
        if diag:
            add("all_scanned_set_size", diag["set_size"])
            conditions.update(diag["rejected_by_condition"])
        if a.get("dwell"):
            d = a["dwell"]
            add("all_selected_duration_ticks", d["duration_ticks"])
            add("all_selected_set_size", d["set_size"])
            for mid, m in diag["members"].items():
                checks = {"warning": m["warning_sdf_m"] <= -12.5, "alert": m["alert_sdf_m"] >= 12.5,
                          "base": m["base_min_margin_m"] >= 0., "endpoint": m["endpoint_distance_m"] >= 62.5,
                          "semantic": not any(lo <= m["member_station_m"] <= hi for lo, hi in m["semantic_ranges_m"])}
                if not all(checks.values()):
                    selected_violations.append({"contract_id": r["contract_id"], "attempt": a["attempt"], "member": mid, "checks": checks})
    if not r["success"]:
        continue
    diag, d = r["dwell_diagnostics"], r["dwell"]
    add("successful_set_size", diag["set_size"])
    add("successful_duration_ticks", d["duration_ticks"])
    add("member_arrival_span_s", diag["member_arrival_span_s"])
    add("pd_min_pair_distance_m", diag["pd_min_pair_distance_m"])
    assert isinstance(d["duration_ticks"], int) and 200 <= d["duration_ticks"] <= 1200
    members = {}
    for mid, m in diag["members"].items():
        members[mid] = {k: m[k] for k in ("member_station_m", "point_xy", "warning_sdf_m", "alert_sdf_m", "base_min_margin_m", "endpoint_distance_m", "nominal_arrival_s", "duration_s", "duration_roundoff_s")}
        for k, v in members[mid].items():
            if k != "point_xy":
                add(k, v)
        screen = r["nominal_screen"][mid]
        if not screen["passed"] or screen["counts"]["visits"] != 1:
            screen_violations.append({"contract_id": r["contract_id"], "member": mid, "screen": screen})
    selected.append({"contract_id": r["contract_id"], "dwell": d, "members": members})
costs = {}
for p in (folder / "telemetry").glob("*.json"):
    for timing in read(p)["timing"]:
        for k, v in (timing or {}).items():
            if isinstance(v, (float, int)) and k.endswith("_s"):
                costs.setdefault(k, []).append(v)
watch = read(ROOT / "run/diagnostics/skeleton_r1/watchdog.json")
assert watch["source_sha256"] == read(ROOT / "run/diagnostics/gates_4_r1/feint/watchdog.json")["source_sha256"]
doc = {"complete": summary["complete"], "checkpoint": summary["checkpoint"], "contracts": len(rows),
       "successes": sum(r["success"] for r in rows), "attempts_total": sum(r["attempts"] for r in rows),
       "empty_set_attempts": stages.get("close_obs_dwell_set", 0), "attempt_stages": dict(stages),
       "candidate_condition_rejections_overlapping": dict(conditions),
       "distributions": {k: _distribution(v) for k, v in stats.items()},
       "timing_distributions_s": {k: _distribution(v) for k, v in costs.items()},
       "selected_point_violations": selected_violations, "nominal_screen_violations": screen_violations,
       "straight_fallback_diagnostic_only": summary["checkpoint"]["fallback"],
       "special_keys": [{k: r[k] for k in ("contract_id", "success", "attempts", "group_size", "target_id", "failure")}
                        for r in rows if r["contract_id"] in ("o17_d1", "o17_d4", "o34_d3")],
       "selected": selected, "same_source_as_second_gate": True,
       "note": "Diagnostic observations do not introduce new spacing, arrival-span or fallback gates."}
out = ROOT / "run/diagnostics/part5_diagnostics_r1.json"
assert not out.exists()
out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({k: doc[k] for k in ("contracts", "successes", "attempts_total", "empty_set_attempts", "selected_point_violations", "nominal_screen_violations", "same_source_as_second_gate")}, ensure_ascii=False))
