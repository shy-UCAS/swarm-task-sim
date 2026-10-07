"""One-off authorized ledger note and stop release for B098; never launches or analyzes a run."""
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import run_v05_batch as batch

HERE = Path(__file__).resolve().parent
root = batch.ROOT_OUTPUT
path = root / "control.json"
original_bytes = path.read_bytes()
old_hash = hashlib.sha256(original_bytes).hexdigest()
control = json.loads(original_bytes.decode("utf-8"))
original = copy.deepcopy(control)

verification = batch.read(ROOT / "tmp_v05/batch_stop_20261003_03/verification.json")
assert old_hash == verification["control_sha256"], (old_hash, verification["control_sha256"])
assert len(control["records"]) == 98 and control["active_attempt"] is None
assert control["stopped_reason"] == "infrastructure_execution_completed"
assert control["completed"] is False and control["finalized"] is False
last = control["records"][-1]
assert last["logical_index"] == 97 and last["attempt_index"] == 0
assert last["run_id"] == "20261003T192955Z_9a223f93" and last["run_status"] == "failed"
assert last["hard_failures"] == ["infrastructure_execution_completed"]
assert last["episode_quality_eligible"] is False
assert control["rolling"]["anomaly_count"] == 2 and control["rolling"]["window_count"] == 20
assert control["rolling"]["stop"] is False
test_log = (HERE / "full_tests.log").read_text(encoding="utf-8-sig").replace("\r\n", "\n")
assert "\nOK\n" in test_log, "full test suite did not report OK"
batch.assert_binding(control, root)
batch.integrity(control, full_history=True, include_runtime=False)

# Only the files changed by the authorized 2026-10-03 stop-rule correction may
# deviate from the recorded runtime hashes; they are re-registered below.
allowed = {p.resolve() for p in [ROOT / "scripts/run_v05_batch.py",
                                ROOT / "docs/v0.5_当前有效规则.md"]}
changed = {}
for name, recorded in control["runtime_sha256"].items():
    current = batch.file_hash(Path(name))
    if current != recorded:
        assert Path(name).resolve() in allowed, name
        changed[name] = dict(old_sha256=recorded, new_sha256=current)
assert {Path(name).resolve() for name in changed} == allowed, sorted(changed)

archive = root / "control_B098_stop.json"
with archive.open("xb") as stream:
    stream.write(original_bytes)
assert batch.file_hash(archive) == old_hash
snapshot = root / "runtime_snapshot_b098_correction_20261003"
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
    run_id=last["run_id"],
    note="用户决定：B098 降落阶段心跳看门狗超时导致运行未完成，停止来自更正前的停机判定。"
         "停机判定已按授权更正为“状态未完成但分析齐全不再计入硬失败、不触发单次立即停止”；"
         "B098 保留为质量不合格样本、计入滚动窗口异常，不重飞、不重新分析、不回改任何历史记录，"
         "原运行目录、分析产物、台账与哈希全部保留。解除当前停止，异常窗口不重置；本轮不启动批量循环。",
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
control["historical_sha256"].update(batch.hash_tree(ROOT / "tmp_v05/batch_stop_20261003_03"))
report_path = ROOT / "docs/v0.5_batch_stop_20261003_03.md"
control["historical_sha256"][str(report_path)] = batch.file_hash(report_path)

assert control["records"] == original["records"]
assert batch.aggregate_status(control["records"]) == control["aggregate"] == original["aggregate"]
assert batch.rolling_status(control) == control["rolling"] == original["rolling"]
assert batch.next_mission(control) == (98, 0)
batch.assert_binding(control, root)
batch.integrity(control, full_history=True)
batch._save_atomic(path, control)
saved = batch.read(path)
assert saved == control and saved["records"] == original["records"]
assert batch.next_mission(saved) == (98, 0)

report = dict(
    control_sha256_before=old_hash,
    control_sha256_after=batch.file_hash(path),
    records_unchanged=True, records=len(saved["records"]),
    stopped_reason_before=original["stopped_reason"],
    stopped_reason_after=saved["stopped_reason"],
    stopped_utc_before=original["stopped_utc"],
    released_utc=batch.utc(),
    b098_run_id=last["run_id"], b098_logical_index=last["logical_index"],
    b098_stored_hard_failures=last["hard_failures"],
    b098_episode_quality_eligible=last["episode_quality_eligible"],
    b098_reassessed_hard_failures=[], b098_reassessed_infrastructure_execution_completed=True,
    next_mission=list(batch.next_mission(saved)), next_display_id="B099",
    no_run_launched=True, aggregate=saved["aggregate"], rolling=saved["rolling"],
    archived_control=str(archive), archived_control_sha256=old_hash,
    authorized_runtime_changes=changed, snapshot=str(snapshot),
    history_notes=len(saved["history_notes"]),
    stop_verification=str(ROOT / "tmp_v05/batch_stop_20261003_03/verification.json"),
    stop_verification_sha256=batch.file_hash(ROOT / "tmp_v05/batch_stop_20261003_03/verification.json"),
    test_log=str(HERE / "full_tests.log"), test_log_sha256=batch.file_hash(HERE / "full_tests.log"),
    report_document=str(report_path), report_document_sha256=batch.file_hash(report_path),
)
batch.save_json(HERE / "verification.json", report)
print(json.dumps(report, ensure_ascii=False, indent=1))
