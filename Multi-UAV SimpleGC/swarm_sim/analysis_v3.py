"""V3 offline pipeline. Frozen v1/v2 analysis and clock policy are not rerouted."""
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .ac4_timing import (AC4_TIMING_V3_VERSION, ORDERED_ROUTE_PROGRESS_VERSION,
                         evaluate_ac4_timing_v3, terminal_hover_evidence_v3)
from .analysis import aligned_truth_samples, assess_separation, digest
from .execution_constraints import evaluate_execution_constraints
from .execution_metrics import VERSION_V2 as EXECUTION_ARTIFACTS_V2, compute_execution_metrics, compute_execution_metrics_v2
from .mission_evaluation_v3 import evaluate_mission_v3
from .observation_processing import prepare_v3_observations, processing_versions
from .onboard_mission_params import diagnose_onboard_mission_params
from .protocol import semantic_protocol, validate_artifact_protocol
from .quality import invalid_intervals, policy_hash, resolve_policy, summarize_clocks, v3_eligibility
from .recording import resample, write_json
from .route_timing import nominal_arrival_evidence
from .tasks import validate_task_binding
from .truth import percentile, read_truth, write_csv


def _read_packets(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _reference_rows(scene):
    result=[]
    for index,phase in enumerate(scene["phases"]):
        if scene["schema_version"] == 1:
            for agent,target in phase["targets"].items():
                result.append([index,phase["name"],agent,0,*[target[k] for k in ("east_m","north_m","up_m","speed_m_s","hold_s")]])
        else:
            for agent,route in phase["routes"].items():
                for waypoint,target in enumerate(route):
                    result.append([index,phase["name"],agent,waypoint,target["east_m"],target["north_m"],target["up_m"],
                                   phase["speed_m_s"],phase["terminal_hold_s"] if waypoint==len(route)-1 else 0.0])
    return result


def _uses_v05_route_evidence(spec):
    """Optional v0.5 semantics select new diagnostics; old v0.4 tasks stay frozen."""
    execution=spec["execution"]
    return (execution["control_mode"]=="semantic_phase_route_v1" and
            (spec["mission"]["intent"]=="patrol" or "hold_semantics" in execution or
             "max_s" in execution.get("async_timing_tolerance", {})))


def analyze_run_v3(directory, quality_policy=None):
    directory=Path(directory).resolve()
    metadata=json.loads((directory/"metadata.json").read_text(encoding="utf-8"))
    scene=metadata["scenario"]
    scenario_path=directory/"scenario.json"
    if scenario_path.is_file() and json.loads(scenario_path.read_text(encoding="utf-8")) != scene:
        raise ValueError("scenario.json differs from metadata.scenario; run sources are contradictory")
    validate_task_binding(scene)
    spec=scene["task_spec"]
    if spec["schema_version"] != 3:
        raise ValueError("v3 analysis requires TaskSpec schema_version 3")
    policy=resolve_policy(quality_policy)
    versions=processing_versions(); protocol=semantic_protocol(scene)
    lifecycle_epoch=metadata["run_epoch_monotonic_s"]
    lifecycle_end=lifecycle_epoch+metadata["elapsed_s"]
    epoch=metadata.get("flight_epoch_monotonic_s",lifecycle_epoch)
    end=metadata.get("mission_end_monotonic_s",lifecycle_end)
    # flight_epoch is a scheduled release, written before its 0.3 s wait. A
    # bounded phase can fail before that release. Keep the original metadata
    # intact, but export an explicitly unstarted, empty observation interval.
    unstarted="flight_epoch_monotonic_s" in metadata and epoch>lifecycle_end
    if "mission_end_monotonic_s" in metadata and (end<epoch or unstarted):
        raise ValueError("mission end contradicts the scheduled flight window and recorded run lifetime")
    if unstarted:
        end=epoch
    observation_window=dict(status="not_started" if unstarted else
        "complete" if "mission_end_monotonic_s" in metadata else "partial",
        reason="scheduled_release_after_run_end" if unstarted else None,
        scheduled_start_host_s=metadata.get("flight_epoch_monotonic_s"),
        recorded_lifecycle_end_host_s=lifecycle_end,
        recorded_mission_end_host_s=metadata.get("mission_end_monotonic_s"),
        effective_start_host_s=epoch,effective_end_host_s=end)
    count=0 if unstarted else max(0,math.floor((end-epoch)*scene["record_hz"])+1)
    grid=[i/scene["record_hz"] for i in range(count)]
    semantic_grid=grid+[count/scene["record_hz"]] if count else grid
    lifecycle_grid=[i/scene["record_hz"] for i in range(max(0,math.floor(metadata["elapsed_s"]*scene["record_hz"])+1))]
    traces={}; truth_traces={}; semantic_traces={}; semantic_truth_traces={}
    clocks={}; lifecycle_clocks={}; lifecycle_observations={}; lifecycle_truth={}
    filters={}; timeline_errors={}; audits={}; truth_info={}; parameters={}; source_hashes={}; estimate_errors={}
    observation_rows=[]; truth_rows=[]; error_rows=[]; raw_truth_rows=[]
    for vehicle in scene["vehicles"]:
        agent=vehicle["id"]; raw_path=directory/"raw"/f"{agent}.jsonl"
        packets=_read_packets(raw_path)
        if raw_path.exists(): source_hashes[str(raw_path.relative_to(directory))]=digest(raw_path)
        processed=prepare_v3_observations(packets,scene["origin"],policy,epoch,end)
        lifecycle=prepare_v3_observations(packets,scene["origin"],policy,lifecycle_epoch,lifecycle_end)
        model=dict(processed["clock_model"],**versions)
        lifecycle_model=dict(lifecycle["clock_model"],**versions)
        clocks[agent]=model; lifecycle_clocks[agent]=lifecycle_model
        filters[agent]=processed["observation_filter"]; timeline_errors[agent]=processed["timeline_error"]
        audits[agent]=processed["audit"]
        semantic_traces[agent]=resample(processed["samples"],semantic_grid,scene["max_gap_s"])
        traces[agent]=semantic_traces[agent][:count]
        lifecycle_observations[agent]=resample(lifecycle["samples"],lifecycle_grid,scene["max_gap_s"])
        for t,values in traces[agent]:
            observation_rows.append([t,agent,int(values is not None),"passive_piecewise_source_clock_fit_v3" if model["available"] else "unavailable_no_fallback",
                                     *(values or [""]*6)])
        truth,params,info=read_truth(directory,agent,scene["origin"],preserve_invalid=True)
        truth_info[agent]=info; parameters[agent]=params
        if "path" in info: source_hashes[info["path"]]=digest(directory/info["path"])
        for source,values in truth: raw_truth_rows.append([agent,source,*(values if values is not None else [""]*7)])
        semantic_truth_traces[agent]=resample(aligned_truth_samples(truth,model),semantic_grid,scene["max_gap_s"])
        truth_traces[agent]=semantic_truth_traces[agent][:count]
        lifecycle_truth[agent]=resample(aligned_truth_samples(truth,lifecycle_model),lifecycle_grid,scene["max_gap_s"])
        errors=[]
        for (t,actual),(_,estimated) in zip(truth_traces[agent],traces[agent]):
            truth_rows.append([t,agent,int(actual is not None),*(actual or [""]*3)])
            error=math.dist(actual,estimated[:3]) if actual is not None and estimated is not None else None
            if error is not None: errors.append(error)
            error_rows.append([t,agent,int(error is not None),error if error is not None else ""])
        estimate_errors[agent]=dict(samples=len(errors),rms_m=math.sqrt(sum(x*x for x in errors)/len(errors)) if errors else None,
                                   p95_m=percentile(errors,.95),max_m=max(errors) if errors else None)
    fraction={agent:sum(p is not None for _,p in rows)/count if count else 0 for agent,rows in traces.items()}
    truth_fraction={agent:sum(p is not None for _,p in rows)/count if count else 0 for agent,rows in truth_traces.items()}
    observed_separation=assess_separation(traces,scene["min_separation_m"])
    actual_separation=assess_separation(truth_traces,scene["min_separation_m"])
    clock_quality=summarize_clocks(clocks,policy)
    clock_ok=clock_quality["overall"] in ("strict","acceptable")
    context={key:scene[key] for key in ("record_hz","max_gap_s","min_separation_m")}
    context.update(mission=spec["mission"],platform=spec["scenario"]["platform"],world=spec["scenario"]["world"],execution=spec["execution"])
    quality=dict(schema_version=3,**protocol,**versions,frames=count,observation_window=observation_window,observation_valid_fraction=fraction,
        truth_valid_fraction=truth_fraction,timing_diagnostic_pass=clock_ok,clock_quality=clock_quality,
        quality_policy=policy,quality_policy_sha256=policy_hash(policy),evaluation_context=context,
        observation_filter=filters,observation_timeline_errors=timeline_errors,observation_processing_audit=audits,
        invalid_intervals=invalid_intervals(traces,scene["max_gap_s"]),
        timing_residual_threshold_s=policy["clock_acceptable_p95_s"],minimum_separation_m=observed_separation["minimum_m"],
        separation_status=observed_separation["status"],unassessed_pair_intervals=observed_separation["unassessed_pair_intervals"],
        risk_pair_intervals=observed_separation["risk_pair_intervals"],truth_separation=actual_separation,
        data_quality_pass=count>0 and all(v>=policy["min_observation_valid_fraction"] for v in fraction.values()),
        truth_available_pass=count>0 and all(v>=policy["min_truth_valid_fraction"] for v in truth_fraction.values()),
        run_completed=metadata["status"]=="completed",estimation_error=estimate_errors,
        estimation_error_note="FCU vs BIN SIM source-time comparison; internal FCU filtering latency remains; passive fit is not absolute synchronization")
    events=_read_packets(directory/"events.jsonl")
    semantic=evaluate_mission_v3(scene,semantic_traces,semantic_truth_traces,events=events,
                                 metadata=metadata,time_epoch=epoch,clocks=clocks)
    semantic["semantic_validation"]["evaluation_support"]=dict(extra_end_bracket_s=semantic_grid[-1] if len(semantic_grid)>count else None,
        exported_grid_last_s=grid[-1] if grid else None,mission_end_s=None if unstarted else end-epoch,model_input_grid_unchanged=True,
        semantics="one internal boundary-support sample; never exported as an observation; no invalid/gap bridging")
    constraints=evaluate_execution_constraints(scene,lifecycle_observations,lifecycle_truth,events,metadata,lifecycle_epoch,clocks=lifecycle_clocks)
    onboard=diagnose_onboard_mission_params(directory,scene,events,lifecycle_clocks)
    quality.update(onboard_mission_param_check_version=onboard["version"],
                   onboard_mission_param_check_status=onboard["status"],
                   onboard_mission_param_check_required=onboard["required"],
                   onboard_mission_param_check_pass=onboard["pass_gate"])
    labels=semantic["labels"]
    labels["label_provenance"].update(versions)
    quality.update(execution_constraints_pass=constraints["hard_constraints_pass"],mission_success=labels["mission_success"],
                   semantic_consistency=labels["semantic_consistency"])
    quality.update(v3_eligibility(quality,labels))
    nominal=nominal_arrival_evidence(scene,events,metadata,epoch)
    v05_route_evidence=_uses_v05_route_evidence(spec)
    metrics_fn=compute_execution_metrics_v2 if v05_route_evidence else compute_execution_metrics
    metrics=metrics_fn(scene,traces,semantic["phase_windows"],events=events,metadata=metadata,time_epoch=epoch,
                       nominal_arrivals=nominal["records"])
    metrics["nominal_timing_deviation_s"]["assessment"]=nominal
    v05_versions={}
    ac4_report=None
    if v05_route_evidence:
        v05_versions=dict(route_progress_version=ORDERED_ROUTE_PROGRESS_VERSION,
                          ac4_timing_version=AC4_TIMING_V3_VERSION,
                          execution_artifacts_version=EXECUTION_ARTIFACTS_V2)
        releases=[event.get("phase") for event in events if event.get("event")=="phase_release_scheduled"]
        hover_supported=(metadata["status"]=="completed" and "mission_end_monotonic_s" in metadata
                         and all(releases.count(phase["name"])==1 for phase in scene["phases"]))
        ac4_channels={}
        hover_evidence={}
        for channel,channel_traces in (("truth",semantic_truth_traces),("observation",semantic_traces)):
            starts,evidence=(terminal_hover_evidence_v3(scene,channel_traces,events,metadata,epoch,channel,clocks)
                             if hover_supported else ({},[]))
            hover_evidence[channel]=evidence
            ac4_channels[channel]=evaluate_ac4_timing_v3(scene,channel_traces,events,metadata,epoch,
                                                          channel=channel,terminal_hover_starts=starts)
        ac4_report=dict(**v05_versions,**versions,channels=ac4_channels,hover_evidence=hover_evidence,
                        truth_primary=True,observation_crosscheck=True,
                        criterion="per semantic phase D <= tau; no change to nominal timing or arrival_s")
        quality.update(v05_versions)
        quality["ac4_v3_truth_within_tau"]=ac4_channels["truth"]["within_tau"]
        quality["ac4_v3_observation_within_tau"]=ac4_channels["observation"]["within_tau"]
        labels["label_provenance"].update(v05_versions)
    extra={"mission.json":spec["mission"],"shared_scene.json":spec["scenario"],"allocation.json":scene["planning"],
        "semantic_plan.json":scene["semantic_plan"],"semantic_validation.json":dict(semantic["semantic_validation"],**versions),
        "phase_windows.json":dict(semantic["phase_windows"],**versions),"execution_constraints.json":dict(constraints,**versions),
        "lifecycle_clock_models.json":lifecycle_clocks,"execution_metrics.json":dict(metrics,**versions),
        "onboard_mission_param_check.json":onboard,
        "observation_processing.json":dict(**versions,per_agent=audits,raw_evidence_preserved=True)}
    if ac4_report is not None:
        extra["ac4_timing_v3.json"]=ac4_report
    output=directory/("analysis_v"+__version__.replace(".","")+"_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_")+uuid.uuid4().hex[:8])
    output.mkdir()
    fields=["t_s","agent_id","valid"]
    write_csv(output/"observations.csv",fields+["time_basis","east_m","north_m","up_m","ve_m_s","vn_m_s","vu_m_s"],observation_rows)
    write_csv(output/"truth.csv",fields+["east_m","north_m","up_m"],truth_rows)
    write_csv(output/"truth_source.csv",["agent_id","source_boot_s","east_m","north_m","up_m","qw","qx","qy","qz"],raw_truth_rows)
    write_csv(output/"estimation_error.csv",fields+["position_error_m"],error_rows)
    write_csv(output/"reference_waypoints.csv",["phase_index","phase","agent_id","waypoint_index","east_m","north_m","up_m","speed_m_s","hold_s"],_reference_rows(scene))
    for name,value in {"task.json":spec,"labels.json":labels,"quality.json":quality,"clock_models.json":clocks,
                       "truth_provenance.json":truth_info,"logged_parameters.json":parameters,**extra}.items():
        write_json(output/name,value)
    for filename in ("metadata.json","scenario.json","events.jsonl","generation_profile.json","generation_manifest.json","generation_entry.json",
                     "parameter_requests.jsonl","parameter_readback.json","firmware_provenance.json","firmware_parameters.json"):
        if (directory/filename).exists(): source_hashes[filename]=digest(directory/filename)
    manifest=dict(schema_version=3,analysis_version=__version__,analysis_schema_version=3,
        simulator_version=metadata.get("version"),run_id=metadata["run_id"],run_directory=str(directory),run_status=metadata["status"],
        scenario_id=scene["scenario_id"],family_id=spec["family_id"],family_scheme=spec["family_scheme"],
        control_mode=spec["execution"]["control_mode"],intent=spec["mission"]["intent"],**protocol,**versions,**v05_versions,
        quality_policy=policy,quality_policy_sha256=policy_hash(policy),evaluation_context=context,
        partial_window="mission_end_monotonic_s" not in metadata,time_epoch_host_s=epoch,duration_s=end-epoch,
        observation_window=observation_window,
        time_semantics="full-stream strict source times; exact duplicates dropped before passive clock fit; no clock fallback",
        reference_semantics="nominal uniform-speed stage route; diagnostic reference, not a closed-loop timing guarantee",
        observation_contract="cooperative FCU telemetry; known identity; six ENU position/velocity features only",
        source_sha256=source_hashes,analysis_source_sha256={p.name:digest(p) for p in Path(__file__).parent.glob("*.py")},
        benchmark_eligible=quality["benchmark_eligible"],strict_benchmark_eligible=quality["strict_benchmark_eligible"],
        episode_quality_eligible=quality["episode_quality_eligible"],mission_success=labels["mission_success"],
        onboard_mission_param_check_version=onboard["version"],
        onboard_mission_param_check_status=onboard["status"],
        onboard_mission_param_check_required=onboard["required"],
        onboard_mission_param_check_pass=onboard["pass_gate"],
        semantic_consistency=labels["semantic_consistency"],clock_quality=clock_quality,
        agent_ids=sorted(v["id"] for v in scene["vehicles"]),
        artifact_sha256={p.name:digest(p) for p in output.iterdir() if p.is_file()})
    validate_artifact_protocol(manifest,output)
    write_json(output/"manifest.json",manifest)
    write_json(directory/"analysis_latest.json",dict(directory=output.name,manifest_sha256=digest(output/"manifest.json")))
    return output,quality,labels
