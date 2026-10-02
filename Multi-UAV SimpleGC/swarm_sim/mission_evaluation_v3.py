"""Generic dual-channel orchestration; success rules belong to registered intents."""

import copy

from .mission_evaluation import execution_windows, _return_result, tri_and
from .observations import finite_number
from .protocol import semantic_protocol
from .registry import get_intent


def _channel(scene, traces, windows, clocks, intent, return_windows=None):
    specific = intent.evaluate_channel(scene, traces, windows, clocks)
    if not isinstance(specific, dict) or set(specific) != {"conditions", "metrics"}:
        raise ValueError("intent evaluate_channel must return conditions and metrics")
    conditions, metrics = specific["conditions"], specific["metrics"]
    if (not isinstance(conditions, dict) or not conditions or not isinstance(metrics, dict)
            or any(not isinstance(name, str) or type(value) not in (bool, type(None)) for name, value in conditions.items())):
        raise ValueError("intent conditions must be named three-valued booleans")
    if "return_to_launch" in conditions or set(metrics) & {"return_to_launch", "mission_success"}:
        raise ValueError("intent result cannot replace generic return or mission success")
    returned = _return_result(scene, traces, windows if return_windows is None else return_windows, clocks)
    conditions = dict(conditions, return_to_launch=returned["success"])
    result = dict(metrics, return_to_launch=returned, mission_success=tri_and(conditions.values()))
    return result, conditions


def evaluate_mission_v3(scene, traces, truth_traces, events, metadata, time_epoch, clocks=None):
    spec = scene["task_spec"]
    if spec.get("schema_version") != 3:
        raise ValueError("v3 mission evaluation requires TaskSpec schema_version 3")
    mode = spec["execution"]["control_mode"]
    if mode not in ("waypoint_barrier_v1", "semantic_phase_route_v1"):
        raise ValueError("unsupported v3 execution control mode")
    clocks = clocks or {}
    intent = get_intent(spec["mission"]["intent"])
    protocol = semantic_protocol(scene)
    if mode == "semantic_phase_route_v1":
        from .route_windows import build_route_windows, route_window_artifact, service_window_view

        channel_windows = {channel: build_route_windows(scene, samples, events, metadata, time_epoch, channel, clocks)
                           for channel, samples in (("truth", truth_traces), ("observation", traces))}
        results = {}
        for channel, samples in (("truth", truth_traces), ("observation", traces)):
            full = channel_windows[channel]
            returned = copy.deepcopy(full)
            # A stationary return phase still needs independent home geometry;
            # its no-op execution marker is never used as proof of success.
            for window in returned:
                if window["role"] == "hold_no_op" and window["semantic_phase"] == "return":
                    window["role"] = "return"
            results[channel] = _channel(scene, samples, service_window_view(full), clocks, intent, returned)
        truth, truth_conditions = results["truth"]
        observation, observation_conditions = results["observation"]
        windows = channel_windows["observation"]
        window_artifact = route_window_artifact(scene, channel_windows, time_epoch)
    else:
        windows = execution_windows(scene, events, metadata, time_epoch)
        truth, truth_conditions = _channel(scene, truth_traces, windows, clocks, intent)
        observation, observation_conditions = _channel(scene, traces, windows, clocks, intent)
    left, right = truth["mission_success"], observation["mission_success"]
    consistency = "unknown" if left is None or right is None else ("agree" if left == right else "disagree")
    if set(truth_conditions) != set(observation_conditions):
        raise ValueError("intent condition identities must be channel independent")
    if any(a is not None and b is not None and a != b for a, b in
           ((truth_conditions[key], observation_conditions[key]) for key in truth_conditions)):
        consistency = "disagree"
    behavior = intent.behavior_labels(scene, truth)
    if not isinstance(behavior, dict) or set(behavior) != {"planned_behaviors", "observed_behaviors"}:
        raise ValueError("behavior_labels must return planned_behaviors and observed_behaviors")
    labels = dict(schema_version=protocol["label_schema_version"], task_kind=protocol["task_kind"],
        requested_intent=intent.name, assigned_intent=intent.name,
        objective=spec["mission"]["intent_params"]["objective"],
        planned_phases=list(dict.fromkeys(w["semantic_phase"] for w in windows)), **behavior,
        unverified_behaviors={"split": "not_evaluated", "merge": "not_evaluated", "formation_change": "not_evaluated"},
        mission_success=left, mission_success_observation=right, semantic_consistency=consistency,
        mission_metrics={"truth": truth, "observation": observation}, run_status=metadata.get("status"),
        label_provenance=dict(requested_intent="TaskSpec author; not inferred hidden intent",
            mission_success="SIM_truth_positions with passive source-clock alignment",
            mission_success_observation="FCU estimated positions; independent intent evidence pass",
            semantic_windows="semantic_route_windows_v1" if mode == "semantic_phase_route_v1" else "execution_events + compiled_semantic_plan",
            semantic_validation_version=protocol["semantic_validation_version"],
            validator_versions={intent.name: intent.validator_version},
            scope="registered intent evidence rules; no inferred tactical intent"))
    validation = dict(schema_version=1, semantic_validation_version=protocol["semantic_validation_version"],
        mission_success=left, mission_success_observation=right, semantic_consistency=consistency,
        truth=truth, observation=observation,
        condition_results={"truth": truth_conditions, "observation": observation_conditions},
        pass_for_eligibility=left is True and right is True and consistency == "agree")
    # Audits stay separate from intent success: a positive monotonic coverage proof
    # can remain true despite gaps, exactly as in v2. Quality owns missingness gates.
    validation["data_validity"] = {channel: {v["id"]: dict(
        sample_count=len(channel_traces.get(v["id"], [])),
        timeline_strict=bool(channel_traces.get(v["id"])) and all(finite_number(t) for t, _ in channel_traces.get(v["id"], [])) and all(
            b[0] > a[0] for a, b in zip(channel_traces.get(v["id"], []), channel_traces.get(v["id"], [])[1:])))
        for v in scene["vehicles"]} for channel, channel_traces in (("truth", truth_traces), ("observation", traces))}
    if mode == "semantic_phase_route_v1":
        return dict(labels=labels, semantic_validation=validation, phase_windows=window_artifact)
    wait_summary = {v["id"]: dict(
        barrier_wait_host_s=sum(w["barrier_wait_host_s"] for w in windows if w["agent_id"] == v["id"] and w["barrier_wait_host_s"] is not None),
        scheduling_wait_host_s=sum(w["scheduling_wait_host_s"] for w in windows if w["agent_id"] == v["id"] and w["scheduling_wait_host_s"] is not None),
        idle_padding_steps=sum(w["agent_id"] == v["id"] and w["role"] == "idle_padding" for w in windows),
        unmeasured_barrier_windows=sum(w["agent_id"] == v["id"] and w["barrier_wait_host_s"] is None for w in windows))
        for v in scene["vehicles"]}
    return dict(labels=labels, semantic_validation=validation,
        phase_windows=dict(schema_version=1, source="execution_events + compiled_semantic_plan",
            time_epoch_host_s=time_epoch, windows=windows, per_agent_wait=wait_summary,
            wait_definitions=dict(barrier_wait_host_s="latest phase_finished among all agents minus this agent phase_finished",
                scheduling_wait_host_s="next phase_start_sent minus this agent task_target_verified; absent at final phase",
                caution="host event timing proxies; not inferred coordination or exact stationary time")))
