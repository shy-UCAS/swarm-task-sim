"""Read retained results for tracking/event/cost diagnostics; no additional acceptance thresholds."""
import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
sys.path.insert(0, str(BASE / "Simulation-v08/Multi-UAV SimpleGC"))
from v08.runner.skeleton_monitoring import _distribution

read = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
round_ = sys.argv[1] if len(sys.argv) > 1 else "r1"
assert round_ in ("r1", "r2")
full, out = ROOT / "run/out/full_r1", ROOT / f"run/diagnostics/analysis_{round_}/supplemental.json"
assert out.parent.exists() and not out.exists()
stats, ticks, bins, count_audit, stages = {}, Counter(), {}, [], Counter()
def add(key, value):
    if value is not None:
        stats.setdefault(key, []).append(value)
for label, folder in (("main", full), ("diversity", full / "diversity")):
    rows = read(folder / "records.json")
    bins[label] = {"contracts": len(rows), "successes": sum(r["success"] for r in rows), "attempts": sum(r["attempts"] for r in rows)}
    for row in rows:
        result = read(folder / "contracts" / row["contract_id"] / "result.json")
        assert all(isinstance(a.get("optimization_entered"), bool) for a in result["attempt_log"])
        post = sum(a["optimization_entered"] and not a["ok"] for a in result["attempt_log"])
        assert post == result["post_optimization_failures"] == row["post_optimization_failures"]
        count_audit.append({"contract_id": row["contract_id"], "post_failures": post, "attempts": row["attempts"]})
        for a in result["attempt_log"]:
            stages[a.get("skeleton_stage") or a["stage"]] += 1
        add(label + "_optimization_s_all_attempts", row["optimization_s"])
        add(label + "_contract_wall_s", row["wall_s"])
        if not result["success"]:
            continue
        ticks[result["close_observation"]["duration_ticks"]] += 1
        for mid, m in result["close_observation"]["members"].items():
            nominal = result["phase_metrics"][mid]["nominal_times_s"]
            add("measured_warning_entry_minus_nominal_entry_s", m["first_warning_entry_us"] / 1e6 - nominal[1])
            add("measured_warning_exit_minus_nominal_exit_s", m["first_warning_exit_us"] / 1e6 - nominal[4])
            add("first_warning_entry_us", m["first_warning_entry_us"])
            add("first_warning_exit_us", m["first_warning_exit_us"])
            for k, v in result["tracking"][mid].items():
                if k == "tube_exceeded_0p5":
                    bins.setdefault("tracking", {}).setdefault(k, 0)
                    bins["tracking"][k] += int(v)
                else:
                    add("tracking_" + k, v)
            add("optimized_reference_deviation_max_m", result["deviation"][mid]["max_m"])
disk = read(full / "disk_verification.json")
for label, values in disk.items():
    for row in values["results"]:
        add(label + "_measured_min_separation_m", row.get("min_separation_m"))
doc = {"scope": "main200 plus diversity100; successful members for measured distributions", "counts": bins,
       "duration_ticks_histogram": dict(sorted(ticks.items())), "attempt_stages_including_success": dict(stages),
       "all_attempt_flags_known_and_post_counts_recomputed": True, "post_count_audit": count_audit,
       "distributions": {k: _distribution(v) for k, v in stats.items()},
       "note": "Arrival span, detection timing, tracking and distances are diagnostics with no added thresholds."}
out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"counts": bins, "known_flags": True, "distributions": len(stats)}))
