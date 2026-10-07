"""One-off authorized ledger note and stop release; never launches or analyzes a run."""
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import run_v05_batch as batch

root = batch.ROOT_OUTPUT
path = root / "control.json"
original_bytes = path.read_bytes()
old_hash = hashlib.sha256(original_bytes).hexdigest()
control = json.loads(original_bytes)
original = copy.deepcopy(control)
verification = batch.read(ROOT / "tmp_v05/batch_stop_20261003_02/verification.json")
assert old_hash == verification["control_sha256"]
assert len(control["records"]) == 37 and control["active_attempt"] is None
assert control["stopped_reason"] == "onboard_mission_parameters; truth_separation; episode_quality"
assert control["completed"] is False and control["finalized"] is False
b037 = control["records"][36]
assert b037["run_id"] == "20261003T105214Z_fc0da71d"
assert b037["episode_quality_eligible"] is False
assert control["rolling"]["anomaly_count"] == 1 and control["rolling"]["window_count"] == 20
test_log = Path(__file__).parent / "full_tests.log"
test_text = test_log.read_text(encoding="utf-8-sig")
assert "\nOK\n" in test_text.replace("\r\n", "\n")
batch.assert_binding(control, root)
batch.integrity(control, full_history=True, include_runtime=False)

allowed = {p.resolve() for p in [
    ROOT / "scripts/run_v05_batch.py",
    ROOT / "docs/v0.5_当前有效规则.md",
]}
changed = {}
for name, old in control["runtime_sha256"].items():
    source = Path(name)
    current = batch.file_hash(source)
    if current != old:
        assert source.resolve() in allowed, name
        changed[name] = dict(old_sha256=old, new_sha256=current)
assert {Path(name).resolve() for name in changed} == allowed
loop = (ROOT / "scripts/run_v05_batch_loop.ps1").resolve()
assert str(loop) not in control["runtime_sha256"]
changed[str(loop)] = dict(old_sha256=None, new_sha256=batch.file_hash(loop))

archive = root / "control_B037_stop.json"
with archive.open("xb") as stream:
    stream.write(original_bytes)
assert batch.file_hash(archive) == old_hash
snapshot = root / "runtime_snapshot_gate_correction_20261003"
for name, hashes in changed.items():
    source = Path(name)
    target = snapshot / source.resolve().relative_to(ROOT.parent.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(source.read_bytes())
    hashes["snapshot"] = str(target)
    control["runtime_sha256"][name] = hashes["new_sha256"]
control["runtime_archive_sha256"].update(batch.hash_tree(snapshot))

control["history_notes"].append(dict(
    recorded_utc=batch.utc(),
    run_id=b037["run_id"],
    note="用户更正门禁口径：B037 停止发生于本次更正前。原质量不合格、未知项、全部运行和分析及原判定保留；不重飞、不重新分析。按更正口径解除当前停止，异常窗口不重置。本轮不启动 B038。",
    original_control=str(archive),
    original_control_sha256=old_hash,
    original_stop_reason=control["stopped_reason"],
    original_stopped_utc=control["stopped_utc"],
    original_research_impact=control["research_impact"],
    authorized_runtime_changes=changed,
))
control["stopped_reason"] = None
control.pop("stopped_utc")
control.pop("research_impact")
control["historical_sha256"][str(archive)] = old_hash
control["historical_sha256"].update(batch.hash_tree(ROOT / "tmp_v05/batch_stop_20261003_02"))
report_path = ROOT / "docs/v0.5_batch_stop_20261003_02.md"
control["historical_sha256"][str(report_path)] = batch.file_hash(report_path)
assert control["records"] == original["records"]
assert batch.aggregate_status(control["records"]) == control["aggregate"] == original["aggregate"]
assert batch.rolling_status(control) == control["rolling"] == original["rolling"]
assert batch.next_mission(control) == (37, 0)
batch.assert_binding(control, root)
batch.integrity(control, full_history=True)
batch._save_atomic(path, control)
saved = batch.read(path)
assert saved == control and saved["records"] == original["records"]

report = dict(
    recorded_utc=batch.utc(), original_control=str(archive), original_control_sha256=old_hash,
    current_control_sha256=batch.file_hash(path), records_unchanged=True,
    original_stop_history_preserved=True, b037_quality_eligible=False,
    b037_run_id=b037["run_id"], b037_evidence_files_verified=len(b037["evidence_sha256"]),
    historical_files_verified=len(control["historical_sha256"]),
    runtime_files_verified=len(control["runtime_sha256"]),
    runtime_archive_files_verified=len(control["runtime_archive_sha256"]),
    batch_evidence_files_verified=sum(len(r["evidence_sha256"]) for r in control["records"]),
    protected_files_pass=True, stopped_reason=control["stopped_reason"],
    next_mission=[37, 0], next_display_id="B038", no_run_launched=True,
    aggregate=control["aggregate"], rolling=control["rolling"], authorized_runtime_changes=changed,
    test_log=str(test_log), test_log_sha256=batch.file_hash(test_log),
)
batch.save_json(Path(__file__).parent / "verification.json", report)
print(json.dumps(report, ensure_ascii=False))
