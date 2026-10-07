"""Read-only preservation and critical-stop verification after B037."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import run_v05_batch as batch

root = batch.ROOT_OUTPUT
control_path = root / "control.json"
before = batch.file_hash(control_path)
control = batch.read(control_path)
assert len(control["records"]) == 37 and control["active_attempt"] is None
assert control["stopped_reason"] == "onboard_mission_parameters; truth_separation; episode_quality"
batch.assert_binding(control, root)
batch.integrity(control, full_history=True)
last = control["records"][-1]
assert last["logical_index"] == 36 and last["attempt_index"] == 0
analysis = Path(last["analysis_directory"])
scene = batch.read(Path(last["run_directory"]) / "metadata.json")["scenario"]
metadata, artifacts = batch.selected_artifacts(last["run_directory"], analysis, scene, control)
assessment = batch.assess_artifacts(scene, metadata, artifacts, control)
for key, value in assessment.items():
    assert last[key] == value, key
quality = artifacts["quality"]
manifest = batch.read(analysis / "manifest.json")
assert batch.aggregate_status(control["records"]) == control["aggregate"]
assert batch.rolling_status(control) == control["rolling"]
assert batch.file_hash(control_path) == before
recovery = batch.read(ROOT / "tmp_v05/batch_repair_20261003/recovery.json")
assert batch.file_hash(root / "control_B001_stop.json") == recovery["original_control_sha256"]
assert batch.file_hash(root / "stop_report.md") == recovery["original_stop_report_sha256"]
verification = dict(control_sha256=before, control_unchanged=True,
    original_b001_stop_unchanged=True,
    historical_files_verified=len(control["historical_sha256"]),
    runtime_files_verified=len(control["runtime_sha256"]),
    runtime_archive_files_verified=len(control["runtime_archive_sha256"]),
    batch_evidence_files_verified=sum(len(row["evidence_sha256"]) for row in control["records"]),
    protected_files_pass=True, independent_assessment_matches=True,
    batch_completed=37, batch_target=240, batch_attempts=37, attempts_limit=264,
    retries=0, retry_limit=24, not_started=203,
    aggregate=control["aggregate"], rolling=control["rolling"],
    last_run_id=last["run_id"], last_analysis=str(analysis),
    quality=dict(frames=quality["frames"], observation_valid_fraction=quality["observation_valid_fraction"],
        truth_valid_fraction=quality["truth_valid_fraction"], clock_quality=quality["clock_quality"],
        truth_separation=quality["truth_separation"],
        onboard_status=quality["onboard_mission_param_check_status"],
        episode_quality_eligible=quality["episode_quality_eligible"]),
    manifest_protocol=batch.manifest_protocol(manifest), progress_version=manifest["route_progress_version"],
    critical_checks=last["batch_hard_checks"], cleanup=metadata["cleanup"])
batch.save_json(Path(__file__).parent / "verification.json", verification)
print(json.dumps(verification, ensure_ascii=False))
