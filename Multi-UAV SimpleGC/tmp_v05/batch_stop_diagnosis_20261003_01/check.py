"""One read-only impact check for the B001 analysis-directory failure."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.run_v05_batch import ROOT_OUTPUT, integrity
from swarm_sim.generation import file_hash, checked_path

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

output = Path(__file__).parent / "diagnosis.json"
if output.exists():
    raise ValueError("Refusing to overwrite evidence")
control_path = ROOT_OUTPUT / "control.json"
before = file_hash(control_path)
control = read(control_path)
assert len(control["records"]) == 1 and control["active_attempt"] is None
assert "FileNotFoundError" in control["stopped_reason"]
integrity(control, full_history=True)
row = control["records"][0]
directory = Path(row["run_directory"])
metadata = read(directory / "metadata.json")
latest = read(directory / "analysis_latest.json")
analysis = checked_path(directory, latest["directory"])
manifest = read(analysis / "manifest.json")
assert file_hash(analysis / "manifest.json") == latest["manifest_sha256"]
bindings = {str(control_path): before}
for parent, key in ((directory, "source_sha256"), (analysis, "artifact_sha256")):
    for name, expected in manifest[key].items():
        path = checked_path(parent, name)
        assert file_hash(path) == expected
        bindings[str(path)] = expected
quality, labels, onboard = [read(analysis / (name + ".json")) for name in
                            ("quality", "labels", "onboard_mission_param_check")]
for path in (directory / "analysis_latest.json", analysis / "manifest.json",
             ROOT / "scripts/run_v05_batch.py", ROOT / "swarm_sim/analysis_v3.py",
             ROOT / "tmp_v05/batch_execution_20261002/B001.log",
             ROOT_OUTPUT / "stop_report.md", Path(__file__)):
    bindings[str(path)] = file_hash(path)
assert file_hash(control_path) == before
result = dict(
    reason="batch prepare omitted analyses parent; analyze_run_v3 output.mkdir requires existing parent",
    root_cause_owner="new_batch_controller_implementation",
    simulation_started_by_check=False, reanalysis_performed=False, evidence_modified=False,
    run_id=row["run_id"], run_directory=str(directory),
    pipeline_status="stopped_after_successful_flight_before_selected_analysis",
    metadata_status=metadata["status"], cleanup=metadata["cleanup"],
    batch_attempts=1, max_attempts=264, batch_flights=1, planned_batch_flights=240,
    batch_selected_analyses=0, retries=0, max_retries=24,
    batch_patrol_flights=0, planned_batch_patrol_flights=120,
    source_bindings_intact=True, historical_files_checked=len(control["historical_sha256"]),
    runtime_files_checked=len(control["runtime_sha256"]),
    new_run_files_checked=len(row["evidence_sha256"]),
    default_analysis=dict(directory=str(analysis),
        semantic_validation_version=manifest.get("semantic_validation_version"),
        route_progress_version=manifest.get("route_progress_version"),
        acceptance_policy_version=manifest.get("acceptance_policy_version"),
        episode_quality_eligible=quality.get("episode_quality_eligible"),
        frames=quality.get("frames"),
        observation_valid_fraction=quality.get("observation_valid_fraction"),
        truth_valid_fraction=quality.get("truth_valid_fraction"),
        truth_separation=quality.get("truth_separation"),
        required_min_separation_m=metadata["scenario"]["min_separation_m"],
        onboard_status=onboard.get("status"), onboard_pass=onboard.get("pass_gate"),
        mission_success=labels.get("mission_success"),
        mission_success_observation=labels.get("mission_success_observation"),
        semantic_consistency=labels.get("semantic_consistency"),
        provenance_status=metadata.get("run_provenance", {}).get("status")),
    analyses_parent_exists=(ROOT_OUTPUT / "analyses").exists(),
    actual_impact="No trajectory or label-fact corruption was established. Required progress-v2/unified-v3 selected analysis is absent; claiming this run already has that analysis or exporting its automatic v1/v2 analysis as that protocol would be incorrect. Existing raw data can be reused offline without another flight.",
    automatic_stop_impact_correction="The automatic statement alleging frozen configuration/source failure is not supported: frozen and source hashes pass. qualified=false in the exception row is a pipeline disposition, not evidence that the default quality evaluation was false.",
    source_sha256=bindings)
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: result[k] for k in ("run_id", "historical_files_checked", "runtime_files_checked", "new_run_files_checked", "actual_impact")}, ensure_ascii=False))
