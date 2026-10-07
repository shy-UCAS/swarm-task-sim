"""Read-only preservation and critical-stop verification after B098; never launches or analyzes a run."""
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
assert len(control["records"]) == 98 and control["active_attempt"] is None
assert control["stopped_reason"] == "infrastructure_execution_completed"
assert control["completed"] is False and control["finalized"] is False
batch.assert_binding(control, root)
# The two files below are changed by the authorized 2026-10-03 stop-rule correction
# itself; they are registered into runtime_sha256 at stop release. Every other
# protected runtime file must still match its recorded hash.
authorized = {p.resolve() for p in [
    ROOT / "scripts/run_v05_batch.py",
    ROOT / "docs/v0.5_当前有效规则.md",
]}
deviating = {Path(name).resolve() for name, old in control["runtime_sha256"].items()
             if batch.file_hash(Path(name)) != old}
assert deviating == authorized, deviating
batch.integrity(control, full_history=True, include_runtime=False)
last = control["records"][-1]
assert last["logical_index"] == 97 and last["attempt_index"] == 0
assert last["run_id"] == "20261003T192955Z_9a223f93"
assert last["mission_id"] == "patrol_0058_v00" and last["intent"] == "patrol"
analysis = Path(last["analysis_directory"])
scene = batch.read(Path(last["run_directory"]) / "metadata.json")["scenario"]
metadata, artifacts = batch.selected_artifacts(last["run_directory"], analysis, scene, control)
assessment = batch.assess_artifacts(scene, metadata, artifacts, control)
# The stored row keeps its historical verdict; under the corrected rule the same
# evidence yields no hard failure while the run stays recorded as not completed.
differing = {key: (last.get(key), value) for key, value in assessment.items() if last.get(key) != value}
assert set(differing) == {"batch_hard_checks", "hard_failures"}, differing
old_checks, new_checks = differing["batch_hard_checks"]
assert differing["hard_failures"] == (["infrastructure_execution_completed"], [])
assert old_checks["infrastructure_execution_completed"] is False
assert new_checks["infrastructure_execution_completed"] is True
assert ({k: v for k, v in old_checks.items() if k != "infrastructure_execution_completed"}
        == {k: v for k, v in new_checks.items() if k != "infrastructure_execution_completed"})
assert assessment["hard_failures"] == []
assert last["run_status"] == "failed" and assessment.get("run_status", "failed") == "failed"
assert last["episode_quality_eligible"] is False
quality = artifacts["quality"]
assert quality["episode_quality_eligible"] is False and quality["mission_success"] is True
manifest = batch.read(analysis / "manifest.json")


def safe(call, default=None):
    try:
        return call()
    except Exception as exc:
        return f"unavailable: {type(exc).__name__}: {exc}"
assert batch.aggregate_status(control["records"]) == control["aggregate"]
assert batch.rolling_status(control) == control["rolling"]
assert batch.file_hash(control_path) == before
verification = dict(control_sha256=before, control_unchanged=True,
    historical_files_verified=len(control["historical_sha256"]),
    runtime_files_verified=len(control["runtime_sha256"]),
    runtime_archive_files_verified=len(control["runtime_archive_sha256"]),
    batch_evidence_files_verified=sum(len(row["evidence_sha256"]) for row in control["records"]),
    protected_files_pass=True, authorized_runtime_deviations=sorted(str(p) for p in deviating),
    independent_assessment_matches=False, reassessed_hard_failures=[],
    reassessed_run_status=last["run_status"], stored_differences={k: list(v) for k, v in differing.items()},
    batch_completed=98, batch_target=240, batch_attempts=98, attempts_limit=264,
    retries=0, retry_limit=24, not_started=142,
    aggregate=control["aggregate"], rolling=control["rolling"],
    last_run_id=last["run_id"], last_analysis=str(analysis),
    quality=dict(frames=quality["frames"], observation_valid_fraction=quality["observation_valid_fraction"],
        truth_valid_fraction=quality["truth_valid_fraction"], clock_quality=quality["clock_quality"],
        truth_separation=quality["truth_separation"],
        onboard_status=quality["onboard_mission_param_check_status"],
        mission_success=quality["mission_success"], semantic_consistency=quality["semantic_consistency"],
        episode_quality_eligible=quality["episode_quality_eligible"]),
    manifest_protocol=safe(lambda: batch.manifest_protocol(manifest)),
    progress_version=safe(lambda: manifest["route_progress_version"]),
    critical_checks=last["batch_hard_checks"], cleanup=safe(lambda: metadata["cleanup"]),
    landed_event_present=safe(lambda: any(
        json.loads(line).get("event") == "landed"
        for line in Path(last["run_directory"]).joinpath("events.jsonl").read_text(
            encoding="utf-8").splitlines())))
batch.save_json(Path(__file__).parent / "verification.json", verification)
print(json.dumps(verification, ensure_ascii=False, indent=1))
