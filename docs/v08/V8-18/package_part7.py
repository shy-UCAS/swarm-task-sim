"""Copy run evidence, excluding raw curves/tracks; leave the run tree read-only."""
import hashlib
import json
import shutil
from pathlib import Path

BASE = Path(r"F:\CASIA\Drone Swarm Situational Awareness Algorithm")
PREP = BASE / "_handoff/2026-11-06_V8-18_feint/resume_20261108"
RUN = BASE / "_handoff/2026-11-06_V8-18_feint/run"
DOC = PREP / "docs/v08/V8-18"
DEST = DOC / "part7"
DEST.mkdir(exist_ok=False)
index = []


def identity(path):
    return {"source": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size}


def copy(source, name):
    target = DEST / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    index.append({**identity(source), "evidence": name, "transformation": "none"})


def strip_curves(value):
    if isinstance(value, dict):
        return {key: strip_curves(val) for key, val in value.items() if key not in ("curve_before", "curve_after")}
    if isinstance(value, list):
        return [strip_curves(val) for val in value]
    return value


for stage, label in (("full_lazy_r1", "full"), ("rerun_lazy_r1", "rerun")):
    for name in ("records.json", "summary.json", "reproduction.json", "rerun_keys.json", "prewarm.json", "dispatch_order.json"):
        source = RUN / "out" / stage / name
        if source.exists():
            copy(source, f"{label}_{name}")
    for name in ("stdout.log", "stderr.log", "watchdog.json", "resource_samples.jsonl"):
        source = RUN / "diagnostics" / stage / name
        if source.exists():
            copy(source, f"{label}_{name}")

source = RUN / "out/full_lazy_r1/diversity/records.json"
rows = json.loads(source.read_text(encoding="utf-8"))
trimmed = strip_curves(rows)
(DEST / "diversity_records_metadata.json").write_text(json.dumps(trimmed, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
index.append({**identity(source), "evidence": "diversity_records_metadata.json", "records": len(rows),
              "transformation": "recursively omit curve_before/curve_after; original remains at source"})

for source_name, target in (
    ("full_disk_validation_r1.json", "disk_validation.json"),
    ("validation_metrics_r1.json", "validation_metrics.json"),
    ("acceptance_lazy_r1.json", "acceptance.json"),
    ("test_preset_local_artifacts_lazy_r1.log", "test_preset_local_artifacts.log"),
    ("analyze_feint_lazy_r1.log", "analyze_feint.log"),
):
    copy(RUN / "diagnostics" / source_name, target)
for folder in ("four_intent_lazy_r1", "observables_paired_lazy_r1"):
    for source in sorted((RUN / "diagnostics" / folder).iterdir()):
        if source.is_file():
            copy(source, source.name)

(DEST / "source_index.json").write_text(json.dumps({
    "scope": "执行方第7部分原运行证据；原始轨迹、NPY、曲线和缓存留在run，不搬入Git",
    "production_source_commit": "8e22f064899cd8fd832f90558da282fb319eed05",
    "run_start_document_commit": "59606dcd088803c6d8687558706de396652eb63a",
    "sources": index,
}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
for helper in ("run_bounded.ps1", "validation_metrics.py", "export_feint_observables.py", "package_part7.py"):
    shutil.copyfile(PREP / helper, DOC / helper)
print(json.dumps({"files": len(index), "destination": str(DEST), "bytes": sum(p.stat().st_size for p in DEST.rglob("*") if p.is_file())}))
