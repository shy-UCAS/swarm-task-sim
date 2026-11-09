"""Compare the final read-only snapshot with registration; no production rules are changed."""
import ast
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
REPO = BASE / "Simulation-v08"
CODE = REPO / "Multi-UAV SimpleGC"
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
DOC = REPO / "docs/v08/V8-19"
DIAG = ROOT / "run/diagnostics"
read = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
initial, final = read(DOC / "snapshot_part1.json"), read(DIAG / "snapshot_final.json")
manifest = read(DOC / "manifest.json")
whole_equal = ("inputs", "frozen_worktrees", "v07_dirs", "whole_frozen_files", "preserved_feint_existence_cache", "preserved_owner_files")
for key in whole_equal:
    assert initial[key] == final[key], key
for key in ("old_preset_tests", "v16_preset_tests", "v17_preset_tests", "v18_preset_tests"):
    assert all(final[key].get(k) == v for k, v in initial[key].items()), key
for k, v in initial["fine_invariants"].items():
    assert final["fine_invariants"][k]["sha256"] == v["sha256"], k
for row in manifest["frozen_symbols"]:
    text = Path(row["path"]).read_text(encoding="utf-8")
    node = next(n for n in ast.parse(text).body if getattr(n, "name", None) == row["qualname"])
    assert hashlib.sha256(ast.get_source_segment(text, node).encode()).hexdigest() == row["sha256"], row
for path, expected in manifest["frozen_files"].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
for name, row in manifest["presets"].items():
    assert hashlib.sha256((CODE / "tests/v08/V8-19" / name).read_bytes()).hexdigest() == row["sha256"], name
allowed = {
    "v08/motion/skeleton.py", "v08/motion/optimize.py", "v08/motion/intents/transit.py", "v08/motion/transit_chords.py",
    "v08/motion/nominal_checks.py", "v08/motion/optimize_checks.py", "v08/contract/single_intent.py", "v08/motion/intent_dispatch.py",
    "v08/runner/joint_monitoring.py", "v08/runner/joint_intent.py", "v08/runner/skeleton_transit.py", "v08/runner/transit_report.py",
}
allowed_new = {"v08/motion/dwell_nominal.py", "v08/motion/close_observation_numeric.py", "v08/motion/intents/close_observation.py",
               "v08/runner/close_observation_report.py", "tools/v08/run_close_observation_v19.py", "tools/v08/analyze_close_observation_v19.py"}
changed = [k for k, v in initial["modules"].items() if final["modules"].get(k) != v]
added = sorted(set(final["modules"]) - set(initial["modules"]))
assert set(changed) <= allowed, changed
assert all(k in allowed_new or k.startswith("tests/v08/V8-19/") for k in added), added
source = {str(p.relative_to(CODE)): hashlib.sha256(p.read_bytes()).hexdigest()
          for sub in ("v08", "tools/v08") for p in (CODE / sub).rglob("*.py")}
gate_source = read(DIAG / "gates_4_r1/feint/watchdog.json")["source_sha256"]
fix = read(DIAG / "analysis_r2/arrival_span_fix.json")
only = fix["changed_dedicated_analysis_file"]
assert {k for k in source if source[k] != gate_source[k]} == {only}
assert source[only] == fix["source_sha_after"] and gate_source[only] == fix["source_sha_before"]
assert fix["all_runtime_source_unchanged"] and fix["all_other_diagnostics_identical"]
for stage in ("prewarm_r1", "skeleton_r1", "quick_r1", "full_r1", "rerun_r1"):
    assert read(DIAG / stage / "watchdog.json")["source_sha256"] == gate_source, stage
    assert read(DIAG / stage / "watchdog.json")["exit_code"] == 0, stage
branch = subprocess.check_output(["git", "-C", str(REPO), "branch", "--show-current"], text=True).strip()
assert branch == "review/v08/V8-19-close-observation"
status = subprocess.check_output(["git", "-C", str(REPO), "status", "--porcelain"], text=True)
for version in ("V8-17", "V8-18"):
    assert f"?? docs/v08/{version}/owner_rerun.json" in status, status
doc = {"complete": True, "checked_utc": datetime.now(timezone.utc).isoformat(), "branch": branch,
       "inputs_equal": len(final["inputs"]), "frozen_worktrees": final["frozen_worktrees"], "v07_dirs_equal": len(final["v07_dirs"]),
       "frozen_files_equal": len(manifest["frozen_files"]), "frozen_symbols_equal": len(manifest["frozen_symbols"]),
       "fine_invariants_equal": len(initial["fine_invariants"]), "old_presets_unchanged": True, "v19_presets_unchanged": True,
       "preserved_feint_cache_files_equal": len(final["preserved_feint_existence_cache"]), "owners_equal_and_untracked": True,
       "old_modules_changed_only_in_allowlist": changed, "added_modules_only_in_allowlist": added,
       "all_production_stages_match_second_gate_source": True, "analysis_only_fix": fix, "git_status_before_final_commit": status,
       "contract_comparison_exclusions": [], "p0_triggered": []}
out = DIAG / "final_audit.json"
assert not out.exists()
out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(doc, ensure_ascii=False))
