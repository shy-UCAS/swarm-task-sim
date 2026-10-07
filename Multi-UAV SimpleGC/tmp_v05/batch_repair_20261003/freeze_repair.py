"""Freeze only the authorized repair changes while retaining all old bindings."""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import run_v05_batch as batch

root = batch.ROOT_OUTPUT
control = batch.read(root / "control.json")
assert batch.next_mission(control) == (1, 0)
assert control["records"][0]["episode_quality_eligible"] is True
batch.integrity(control, full_history=True, include_runtime=False)
allowed = {p.resolve() for p in [ROOT / "scripts/run_v05_batch.py",
    ROOT / "scripts/build_v05_batch_report.py", ROOT / "docs/v0.5_当前有效规则.md",
    ROOT / "docs/v0.5_r1.2_addendum.md", ROOT.parent / "CLAUDE.md"]}
changed = {}
for name, old in control["runtime_sha256"].items():
    source = Path(name)
    current = batch.file_hash(source)
    if current == old:
        continue
    assert source.resolve() in allowed, (name, old, current)
    target = root / "runtime_snapshot_repair_20261003" / source.resolve().relative_to(ROOT.parent.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(source.read_bytes())
    changed[name] = dict(old_sha256=old, new_sha256=current, snapshot=str(target))
    control["runtime_sha256"][name] = current
control["runtime_archive_sha256"].update(batch.hash_tree(root / "runtime_snapshot_repair_20261003"))
control["history_notes"][-1]["authorized_runtime_changes"] = changed
batch.assert_binding(control, root)
batch.integrity(control, full_history=True)
batch._save_atomic(root / "control.json", control)
report = dict(changed=changed, next_mission=batch.next_mission(control),
    aggregate=control["aggregate"], rolling=control["rolling"],
    historical_files=len(control["historical_sha256"]),
    runtime_files=len(control["runtime_sha256"]),
    runtime_archive_files=len(control["runtime_archive_sha256"]),
    old_stop_sha256=batch.file_hash(root / "stop_report.md"),
    new_control_sha256=batch.file_hash(root / "control.json"))
batch.save_json(Path(__file__).parent / "frozen_repair.json", report)
print(json.dumps(report, ensure_ascii=False))
