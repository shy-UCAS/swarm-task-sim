"""One-time, user-authorized B001 offline completion; no flight or new attempt."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import run_v05_batch as batch

root = batch.ROOT_OUTPUT
path = root / "control.json"
control = batch.read(path)
assert len(control["records"]) == 1 and control["active_attempt"] is None
assert "FileNotFoundError" in control["stopped_reason"]
assert "B001_attempt_0" in control["stopped_reason"]
row = control["records"][0]
assert row["run_id"] == "20261003T065823Z_e1d05fa0"
assert row["attempt_index"] == 0 and row["run_status"] == "completed"
batch.assert_binding(control, root)
batch.integrity(control, full_history=True, include_runtime=False)
old_evidence = dict(row["evidence_sha256"])
old_row = copy.deepcopy(row)
original_bytes = path.read_bytes()
archive = root / "control_B001_stop.json"
with archive.open("xb") as stream:
    stream.write(original_bytes)
assert archive.read_bytes() == original_bytes
stop_path = root / "stop_report.md"
stop_digest = batch.file_hash(stop_path)
(root / "analyses").mkdir(exist_ok=True)
analysis = root / "analyses/B001_attempt_0"
scene = batch.read(Path(row["run_directory"]) / "metadata.json")["scenario"]
result = batch.analyze_selected(row["run_directory"], analysis, scene, control)
batch.assert_hashes(old_evidence)
assert result["hard_failures"] == [] and result["episode_quality_eligible"] is True, result
row.update(result, analysis_directory=str(analysis))
row["evidence_sha256"].update(batch.hash_tree(analysis))
for key in ("run_id", "run_directory", "mission_id", "base_index", "logical_index",
            "attempt_index", "reserved_utc", "finished_utc"):
    assert row[key] == old_row[key]
assert all(row["evidence_sha256"][key] == value for key, value in old_evidence.items())
control.setdefault("history_notes", []).append(dict(
    recorded_utc=batch.utc(), run_id=row["run_id"],
    note="用户授权修复 analyses 目录遗漏；使用 B001 原始数据完成 progress v2 / 统一语义 v3 离线分析，全部关键门禁通过，计为已完成。不重飞、不新增尝试；原 STOP 和初报保留。",
    original_control=str(archive), original_control_sha256=batch.file_hash(archive),
    original_stop_reason=control["stopped_reason"], original_stop_report_sha256=stop_digest))
control["historical_sha256"].update({str(archive): batch.file_hash(archive), str(stop_path): stop_digest})
control.update(stopped_reason=None, aggregate=batch.aggregate_status(control["records"]))
control["rolling"] = batch.rolling_status(control)
control.pop("research_impact", None)
control.pop("stopped_utc", None)
assert batch.next_mission(control) == (1, 0)
assert len(control["records"]) == 1 and not control["rolling"]["stop"]
batch.integrity(control, full_history=True, include_runtime=False)
assert batch.file_hash(stop_path) == stop_digest
batch._save_atomic(path, control)
quality = batch.read(analysis / "quality.json")
report = dict(run_id=row["run_id"], no_refly=True, attempts=1, attempt_limit=264,
    completed=1, planned=240, original_raw_files_verified=len(old_evidence),
    original_control_sha256=batch.file_hash(archive), original_stop_report_sha256=stop_digest,
    result=result, truth_separation=quality["truth_separation"], rolling=control["rolling"],
    manifest_sha256=batch.file_hash(analysis / "manifest.json"))
batch.save_json(Path(__file__).parent / "recovery.json", report)
print(__import__("json").dumps(report, ensure_ascii=False))
