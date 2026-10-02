"""Synthetic artifact contracts for tests only; never a production dataset source."""
import copy
import csv
import json
from pathlib import Path
from dataclasses import replace

from swarm_sim.analysis import digest
from swarm_sim.mission_v3 import from_v2, normalize_v3
from swarm_sim.observation_processing import processing_versions
from swarm_sim.protocol import semantic_protocol
from swarm_sim.quality import resolve_policy, policy_hash, episode_quality_eligibility, eligibility
from swarm_sim.registry import get_intent
from swarm_sim.recording import write_json

PROJECT=Path(__file__).resolve().parents[1]

def task_v3(mode="waypoint_barrier_v1",intent="reconnaissance"):
    task=json.loads((PROJECT/"missions/recon_shared_3uav.json").read_text(encoding="utf-8"))
    task=from_v2(task,control_mode=mode)
    task["mission"]["intent"]=intent
    return normalize_v3(task)

def fixture_intent():
    return replace(get_intent("reconnaissance"),name="test_fixture",validator_version="fixture_validation_v1",
                   required_audit_metrics=("fixture_marker",),topology_signature=None)

def rehash(root):
    analysis=root/"analysis_fixture"
    manifest=json.loads((analysis/"manifest.json").read_text(encoding="utf-8"))
    manifest["artifact_sha256"]={p.name:digest(p) for p in analysis.iterdir() if p.is_file() and p.name!="manifest.json"}
    write_json(analysis/"manifest.json",manifest)
    write_json(root/"analysis_latest.json",dict(directory=analysis.name,manifest_sha256=digest(analysis/"manifest.json")))

def make_run(root,mode="waypoint_barrier_v1",intent="reconnaissance",success=False):
    root=Path(root)
    analysis=root/"analysis_fixture"
    analysis.mkdir(parents=True)
    task=task_v3(mode,intent)
    agents=[v["id"] for v in task["scenario"]["vehicles"]]
    protocol=semantic_protocol(dict(task_spec=task))
    versions=processing_versions()
    validator=get_intent(intent).validator_version
    quality=dict(**protocol,**versions,run_completed=True,data_quality_pass=True,truth_available_pass=True,
        timing_diagnostic_pass=True,execution_constraints_pass=True,clock_quality=dict(overall="acceptable"),
        separation_status="clear_observed",truth_separation=dict(status="clear_observed"),
        mission_success=success,semantic_consistency="agree",invalid_intervals={a:[] for a in agents},
        observation_valid_fraction={a:1.0 for a in agents},truth_valid_fraction={a:1.0 for a in agents})
    quality["episode_quality_eligible"]=episode_quality_eligibility(quality)
    quality.update(eligibility(quality,success))
    labels=dict(schema_version=3,task_kind="mission_v3",requested_intent=intent,assigned_intent=intent,
                mission_success=success,semantic_consistency="agree",mission_success_observation=success,
                observed_behaviors=[dict(name="synthetic_fixture",rule_version=validator)],
                label_provenance=dict(semantic_validation_version=protocol["semantic_validation_version"],validator_versions={intent:validator},**versions))
    truth_metric=dict(coverage=dict(global_coverage_ratio=0.5,repeated_coverage_cell_ratio=0.1)) if intent=="reconnaissance" else dict(fixture_marker=1)
    labels["mission_metrics"]=dict(truth=truth_metric,observation=copy.deepcopy(truth_metric))
    for name,value in (("task.json",task),("labels.json",labels),("quality.json",quality),
                       ("semantic_validation.json",dict(semantic_validation_version=protocol["semantic_validation_version"],truth=truth_metric,**versions)),
                       ("execution_constraints.json",dict(constraint_validation_version=protocol["execution_constraints_version"],per_agent={},**versions)),
                       ("phase_windows.json",dict(windows=[dict(phase="observe",barrier_wait_host_s=0,scheduling_wait_host_s=0)],**versions))):
        write_json(analysis/name,value)
    with (analysis/"observations.csv").open("w",encoding="utf-8",newline="") as f:
        writer=csv.writer(f)
        writer.writerow(["t_s","agent_id","valid","east_m","north_m","up_m","ve_m_s","vn_m_s","vu_m_s","privileged_execution_stop_count"])
        for t in (0,0.1,0.2):
            for agent in agents: writer.writerow([t,agent,1,1,2,8,3,0,0,999])
    write_json(root/"source_fixture.json",dict(purpose="synthetic protocol test, no flight"))
    write_json(analysis/"manifest.json",dict(schema_version=3,analysis_version="0.4.0-dev",run_id=root.name,
        scenario_id=task["task_id"],family_id=task["family_id"],family_scheme=task["family_scheme"],control_mode=mode,
        intent=intent,agent_ids=agents,**protocol,**versions,episode_quality_eligible=quality["episode_quality_eligible"],
        mission_success=success,semantic_consistency="agree",benchmark_eligible=quality["benchmark_eligible"],
        strict_benchmark_eligible=quality["strict_benchmark_eligible"],clock_quality=quality["clock_quality"],
        run_status="completed",duration_s=.2,quality_policy=resolve_policy(),quality_policy_sha256=policy_hash(None),
        source_sha256={"source_fixture.json":digest(root/"source_fixture.json")}))
    rehash(root)
    return root,analysis
