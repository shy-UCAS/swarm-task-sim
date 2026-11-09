import hashlib
import json
import shutil
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
ROOT = BASE / "_handoff/2026-11-08_V8-19_close_observation"
RUN = ROOT / "run"
DOC = BASE / "Simulation-v08/docs/v08/V8-19"
OUT = DOC / "part7"
read = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
native, disk = read(RUN / "out/full_r1/summary.json"), read(RUN / "out/full_r1/disk_verification.json")
rerun = read(RUN / "out/rerun_r1/reproduction.json")
analysis = read(RUN / "diagnostics/analysis_r2/diagnostics.json")
pairs = read(RUN / "diagnostics/analysis_r2/five_intent_pairs.json")
supp = read(RUN / "diagnostics/analysis_r2/supplemental.json")
analysis_fix = read(RUN / "diagnostics/analysis_r2/arrival_span_fix.json")
assert analysis_fix["complete"] and analysis_fix["all_other_diagnostics_identical"] and analysis_fix["all_runtime_source_unchanged"]
watch = read(RUN / "diagnostics/full_r1/watchdog.json")
repeat_watch = read(RUN / "diagnostics/rerun_r1/watchdog.json")
manifest = read(DOC / "manifest.json")
assert native["complete"] and native["diversity_complete"] and not native["checkpoint"]["triggered"]
assert not native["retained_p0_violations"] and not native["errors"] and not native["unsent"]
for label, key in (("main", "full200"), ("diversity", "diversity100")):
    folder = RUN / "out/full_r1" / ("diversity" if label == "diversity" else "")
    rows = read(folder / "records.json")
    assert len(rows) == len(manifest["keys"][key]) and {r["contract_id"] for r in rows} == set(manifest["keys"][key])
    assert disk[label]["passed"] and disk[label]["all_checked"] == len(rows) and not disk[label]["p0_violations"]
assert rerun["all_equal"] and len(rerun["comparisons"]) == 5 and rerun["exclusions"] == []
assert {r["contract_id"] for r in rerun["comparisons"]} == set(manifest["keys"]["rerun5"])
assert all(r["file_sets_equal"] and r["bytes_equal"] for r in rerun["comparisons"])
assert pairs["contracts"] == 200 and not pairs["common_differences"] and not analysis["same_attempt_geometry_differences"]
metrics = native["checkpoint"]["metrics"]
blocks = native["frechet_blocks_after"]
assert all(b["scope"] == "close_observation_warning_entry_to_exit_v19" for b in blocks)
normalized = [float(v) / float(b["spacing_m"]) for b in blocks for v in b["distances_m"]]
assert len(normalized) == metrics["frechet_pairs"] and statistics.median(normalized) == metrics["frechet_pooled_median"]
assert watch["source_sha256"] == repeat_watch["source_sha256"] == read(RUN / "diagnostics/gates_4_r1/feint/watchdog.json")["source_sha256"]
OUT.mkdir(exist_ok=False)
for stage in ("full_r1", "rerun_r1"):
    target = OUT / stage
    target.mkdir()
    folder = RUN / "out" / stage
    for filename in ("summary.json", "records.json", "prewarm.json", "rerun_keys.json", "dispatch_order.json", "disk_verification.json", "reproduction.json"):
        if (folder / filename).exists():
            shutil.copyfile(folder / filename, target / filename)
    for filename in ("watchdog.json", "stdout.log", "stderr.log"):
        shutil.copyfile(RUN / "diagnostics" / stage / filename, target / filename)
div = read(RUN / "out/full_r1/diversity/records.json")
(OUT / "diversity_records_summary.json").write_text(json.dumps([{k: v for k, v in r.items() if k not in ("curve_before", "curve_after")} for r in div], ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
shutil.copytree(RUN / "diagnostics/analysis_r2", OUT / "analysis")
shutil.copytree(RUN / "diagnostics/analysis_r1", OUT / "analysis_before_fix")
for filename in ("analysis_r1.log", "analysis_r1_watch.json", "analysis_r2.log", "analysis_r2_watch.json", "part7_diversity_probe_r1.log"):
    shutil.copyfile(RUN / "diagnostics" / filename, OUT / filename)
shutil.copyfile(RUN / "diagnostics/part7_diversity_probe_r1/summary.json", OUT / "diversity_probe_summary.json")
for filename in ("package_part7.py", "run_final_analysis.ps1", "part7_probe.py", "part7_supplement.py", "check_arrival_span_fix.py"):
    shutil.copyfile(ROOT / filename, OUT / filename)
index = []
for stage in ("full_r1", "rerun_r1"):
    for p in (RUN / "out" / stage).rglob("*"):
        if p.is_file():
            h = hashlib.sha256()
            with p.open("rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    h.update(block)
            index.append({"path": str(p), "bytes": p.stat().st_size, "sha256": h.hexdigest()})
(OUT / "raw_evidence_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
classifications = Counter(r["classification"] for r in analysis["geometry_pairs"])
summary = {"part": 7, "complete": True, "native_checkpoint": native["checkpoint"], "main_successes": supp["counts"]["main"]["successes"],
           "diversity_successes": supp["counts"]["diversity"]["successes"], "full_watchdog_wall_s": watch["wall_s"],
           "rerun_watchdog_wall_s": repeat_watch["wall_s"], "rerun_equal": 5, "rerun_exclusions": [], "paired_keys": 200,
           "common_differences": [], "same_attempt_geometry_differences": [], "geometry_classifications": dict(classifications),
           "runtime_source_matches_second_gate": True, "analysis_only_fix": analysis_fix, "p0_triggered": [], "checked_utc": datetime.now(timezone.utc).isoformat()}
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
manifest["execution_status_at_part6"] = manifest.pop("execution_status")
manifest["execution_status"] = {"part": 7, "status": "complete", "evidence": "part7/summary.json", "next": "artifact preset9.3, final freeze snapshot and delivery"}
(DOC / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
# The report reduction is kept separate so diagnostic raw values are always visible.
exec((ROOT / "report_part7.py").read_text(encoding="utf-8"))
shutil.copyfile(ROOT / "report_part7.py", OUT / "report_part7.py")
print(json.dumps(summary, ensure_ascii=False))
