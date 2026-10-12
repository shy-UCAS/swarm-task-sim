"""Immutable local run artifacts for the explicit fast_dynamics_v1 contract."""

import csv
import json
import math
import platform
import re
from pathlib import Path

import numpy as np

from .adapter import ADAPTER_VERSION, analyze_semantics, checked_samples, result_value, traces_from_samples
from .contracts import (CONTROLLER_VERSION, ENGINE_VERSION, INTEGRATOR_VERSION, OBSERVER_VERSION,
                        PLANT_VERSION, FastDynamicsConfig)
from ..execution_constraints import _channel_limits, _lifecycle_separation
from ..families import family_metadata
from ..generation import canonical_hash, file_hash
from ..mission_evaluation import tri_and
from ..protocol import FAST_DYNAMICS_PROTOCOL, fast_dynamics_protocol, manifest_protocol
from ..recording import write_json
from ..tasks import compile_task

FACTS_VERSION = "observer_facts_fast_dynamics_v1"
QUALITY_VERSION = "fast_dynamics_quality_v1"
TIME_POLICY = dict(version="integer_sim_clock_half_open_v1", time_base="sim_clock",
                   tick_unit="microsecond", record_hz=10, output_period_us=100_000,
                   endpoint_policy="[0,end_us)", duration_source="actual_end_us")
FEATURES = ("east_m", "north_m", "up_m", "ve_m_s", "vn_m_s", "vu_m_s")
CAPABILITIES = dict(position=True, velocity=True, net_acceleration=True, attitude=False,
                    body_rates=False, imu=False, motors=False, takeoff=False, landing=False)
SOURCE_DECLARATIONS = dict(coordinate_frame="ENU", feature_schema="enu_position_velocity_6_v1",
    controller_state_source="truth", observation_dependency="ideal observation derived from plant; no independent sensor/estimator")


def resolve_quality_policy(policy=None):
    result = dict(version=QUALITY_VERSION, min_observation_valid_fraction=1.0,
                  min_truth_valid_fraction=1.0, numerical_tolerance=1e-7,
                  zero_duration_eligible=False, lifecycle_scope="airborne_mission")
    if policy is not None:
        if not isinstance(policy, dict) or set(policy) != set(result):
            raise ValueError("unsupported fast dynamics quality policy fields")
        result.update(policy)
    if result != dict(version=QUALITY_VERSION, min_observation_valid_fraction=1.0,
                      min_truth_valid_fraction=1.0, numerical_tolerance=1e-7,
                      zero_duration_eligible=False, lifecycle_scope="airborne_mission"):
        raise ValueError("unsupported fast dynamics quality policy values")
    return result


def _csv(path, agents, times, positions, velocities, accelerations=None):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("t_s", "agent_id", "valid", *FEATURES,
                         *(("ae_m_s2", "an_m_s2", "au_m_s2") if accelerations is not None else ())))
        for k, stamp in enumerate(times):
            for i, agent in enumerate(agents):
                writer.writerow((format(int(stamp) / 1e6, ".6f"), agent, 1,
                                 *positions[k, i].tolist(), *velocities[k, i].tolist(),
                                 *(accelerations[k, i].tolist() if accelerations is not None else ())))


def _read_support(path, agents):
    records = {agent: [] for agent in agents}
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("agent_id") not in records or row.get("valid") != "1":
                raise ValueError("invalid support agent or mask")
            stamp = float(row["t_s"])
            tick = round(stamp * 1e6)
            if not math.isfinite(stamp) or abs(stamp - tick / 1e6) > 1e-10:
                raise ValueError("support time is not an integer microsecond")
            values = [float(row[key]) for key in (*FEATURES, "ae_m_s2", "an_m_s2", "au_m_s2")]
            if not all(math.isfinite(value) for value in values):
                raise ValueError("nonfinite support state")
            records[row["agent_id"]].append((tick, values))
    times = [tick for tick, _ in records[agents[0]]]
    if any([tick for tick, _ in records[a]] != times for a in agents) or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("support time grids disagree or do not increase")
    values = np.asarray([[records[a][k][1] for a in agents] for k in range(len(times))], dtype=float).reshape((-1, len(agents), 9))
    return np.asarray(times, dtype=np.int64), values[..., :3], values[..., 3:6], values[..., 6:9]


def _source_hashes():
    from .provenance import source_snapshot
    return source_snapshot()


def _git_revision():
    """Read a Git baseline without launching any external process."""
    project = Path(__file__).resolve().parents[2]
    entry = next((directory / ".git" for directory in (project, *project.parents)
                  if (directory / ".git").exists()), None)
    if entry is None:
        raise ValueError("cannot find source Git baseline")
    gitdir = entry
    if entry.is_file():
        pointer = entry.read_text(encoding="utf-8").strip()
        if not pointer.startswith("gitdir: "):
            raise ValueError("invalid Git directory pointer")
        gitdir = (entry.parent / pointer[8:]).resolve()
    head = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
    revision = head
    if head.startswith("ref: "):
        name = head[5:]
        common = gitdir
        if (gitdir / "commondir").is_file():
            common = (gitdir / (gitdir / "commondir").read_text(encoding="utf-8").strip()).resolve()
        ref = next((directory / name for directory in (gitdir, common) if (directory / name).is_file()), None)
        if ref is not None:
            revision = ref.read_text(encoding="utf-8").strip()
        elif (common / "packed-refs").is_file():
            revision = next((line.split()[0] for line in (common / "packed-refs").read_text(encoding="utf-8").splitlines()
                             if len(line.split()) == 2 and line.split()[1] == name), "")
    if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
        raise ValueError("cannot determine source Git baseline")
    return revision


def _eligibility(quality, labels):
    qualified = all(quality.get(key) is True for key in (
        "run_completed", "nonempty", "numerical_valid", "data_quality_pass", "truth_available_pass",
        "execution_constraints_pass", "vehicle_capability_pass", "time_grid_pass")) and quality.get("separation_status") == "clear_observed"
    benchmark = qualified and labels["mission_success"] is True and labels["mission_success_observation"] is True and labels["semantic_consistency"] == "agree"
    return dict(episode_quality_eligible=qualified, benchmark_eligible=benchmark,
                strict_benchmark_eligible=False)


def _validate_execution_events(events, status, end, windows):
    """Bind runtime outcome to actual terminal evidence and all phase windows."""
    if status not in ("completed", "timeout") or not isinstance(events, list):
        raise ValueError("invalid execution outcome or event evidence")
    if end == 0 and status == "timeout" and not events:
        return  # Explicit empty, ineligible synthetic boundary case.
    agents = {window["agent_id"] for window in windows["channels"]["truth"]}
    phases = {window["phase"] for window in windows["channels"]["truth"]}
    for event in events:
        tick = event.get("t_us")
        if (isinstance(tick, bool) or not isinstance(tick, (int, np.integer)) or not 0 <= tick <= end
                or event.get("agent_id") is not None and event["agent_id"] not in agents
                or event.get("phase") is not None and event["phase"] not in phases
                or "t_s" in event and (not isinstance(event["t_s"], (float, int))
                    or not math.isfinite(event["t_s"]) or abs(event["t_s"] - tick / 1e6) > 1e-9)):
            raise ValueError("invalid actual execution event identity or simulation time")
    terminals = [event for event in events if event.get("event") in
                 ("airborne_mission_completed", "airborne_mission_timeout")]
    expected = "airborne_mission_completed" if status == "completed" else "airborne_mission_timeout"
    if len(terminals) != 1 or terminals[0]["event"] != expected or terminals[0]["t_us"] != end:
        raise ValueError("execution status or end_us disagrees with actual terminal event")
    if status == "completed" and (any(event.get("event") == "phase_timeout" for event in events)
            or any(window.get("complete_execution_window") is not True
                   for channel in windows["channels"].values() for window in channel)):
        raise ValueError("completed execution requires every actual phase window to be complete")


def _constraints(scene, traces, end_s, config):
    spec = scene["task_spec"]
    execution, scenario = spec["execution"], spec["scenario"]
    agents = sorted(traces)
    threshold = max(execution["min_separation_m"], config["quality"]["min_separation_m"])
    sep = _lifecycle_separation(traces, agents, 0., end_s, threshold, execution["max_gap_s"], 0., end_s > 0)
    sep["scope"] = "airborne_mission [0, actual_end_s]; takeoff/landing unsupported"
    per_agent = {}
    for agent in agents:
        bounds = _channel_limits(traces[agent], 0., end_s, 0., end_s,
                                 scenario["world"], scenario["platform"], execution["max_gap_s"], 0.)
        # All M1 samples are already airborne; these are interval boundaries,
        # not manufactured airborne_ready/landing events.
        bounds.pop("transition_events_complete", None)
        bounds["transition_lower_bound"] = "airborne_mission lower altitude bound applies throughout"
        duration_limit = scenario["platform"]["max_airborne_time_s"] - scenario["platform"]["reserve_time_s"]
        per_agent[agent] = dict(truth=bounds, observation=dict(bounds),
            world_bounds_pass=bounds["world_bounds_pass"], path_length_pass=bounds["path_length_pass"],
            mission_time_pass=end_s <= duration_limit if end_s > 0 else None,
            mission_duration_s=end_s, lifecycle_scope="airborne_mission")
    passed = tri_and([sep["passed"], *[value[key] for value in per_agent.values()
                     for key in ("world_bounds_pass", "path_length_pass", "mission_time_pass")]])
    return dict(constraint_validation_version=fast_dynamics_protocol()["execution_constraints_version"],
        pass_for_eligibility=passed, per_agent=per_agent, separation=sep,
        lifecycle_scope="airborne_mission", time_base="sim_clock",
        limitation="piecewise-linear support geometry; no whole-flight takeoff/landing or contact physics evidence")


def _numerics(result, streams, config):
    times, p, v = streams["support_"]
    a = np.asarray(result_value(result, "support_accelerations"), dtype=float)
    if a.shape != p.shape or not np.isfinite(a).all():
        raise ValueError("invalid support accelerations are an engine error")
    profile = config["vehicle_profile"]
    if not len(times):
        return dict(passed=False, reason="empty_trajectory")
    tol = 1e-7
    acceleration_pass = bool(np.all(np.linalg.norm(a[..., :2], axis=-1) <= profile["max_accel_xy_m_s2"] + tol)
        and np.all(a[..., 2] <= profile["max_accel_up_m_s2"] + tol)
        and np.all(a[..., 2] >= -profile["max_accel_down_m_s2"] - tol))
    if len(times) < 2:
        return dict(passed=False, reason="no_integration_interval")
    dt = np.diff(times)[:, None, None] / 1e6
    jerk = np.diff(a, axis=0) / dt
    expected_v = v[:-1] + a[:-1] * dt + .5 * jerk * dt**2
    expected_p = p[:-1] + v[:-1] * dt + .5 * a[:-1] * dt**2 + jerk * dt**3 / 6
    residual = max(float(np.max(np.abs(expected_v - v[1:]))), float(np.max(np.abs(expected_p - p[1:]))))
    jerk_pass = bool(np.all(np.linalg.norm(jerk, axis=-1) <= profile["max_jerk_m_s3"] + tol))
    if not acceleration_pass or not jerk_pass or residual > tol:
        raise ValueError("state violates declared acceleration/jerk/integration contract; engine error")
    speed_tol = config["quality"]["max_speed_tolerance_m_s"]
    speed_pass = bool(np.all(np.linalg.norm(v[..., :2], axis=-1) <= profile["max_speed_xy_m_s"] + speed_tol)
        and np.all(v[..., 2] <= profile["max_speed_up_m_s"] + speed_tol)
        and np.all(v[..., 2] >= -profile["max_speed_down_m_s"] - speed_tol))
    return dict(passed=True, acceleration_pass=acceleration_pass, jerk_pass=jerk_pass,
                integration_max_abs_residual=residual, speed_capability_pass=speed_pass,
                speed_capability_is_numerical_error=False)


def write_episode(scene, result, output, *, run_id, input_hashes, config, seed):
    """Write a new run; return its manifest. Public build_dataset consumes output.

    A completion pointer is written last, after hashes and protocol validation.
    Exceptions leave an explicitly incomplete new directory, never a valid run.
    """
    root = Path(output).resolve()
    if root.exists():
        raise ValueError("fast dynamics output already exists; choose a new attempt directory")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id):
        raise ValueError("invalid run_id")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if not isinstance(input_hashes, dict) or not input_hashes or any(not isinstance(key, str) or
            not re.fullmatch(r"[0-9a-f]{64}", value) for key, value in input_hashes.items()):
        raise ValueError("nonempty input bundle SHA256 mapping required")
    config = config.to_dict() if hasattr(config, "to_dict") else config
    config = FastDynamicsConfig.from_dict(config).to_dict()
    runtime_config = result_value(result, "config")
    runtime_config = runtime_config.to_dict() if hasattr(runtime_config, "to_dict") else runtime_config
    if config != runtime_config:
        raise ValueError("artifact configuration differs from actual runtime configuration")
    if scene != result_value(result, "scene") or scene["task_spec"] != result_value(result, "task"):
        raise ValueError("artifact scene or task differs from actual runtime input")
    executed_source = result_value(result, "diagnostics").get("executed_source_sha256")
    if executed_source != _source_hashes():
        raise ValueError("source files changed since execution; run a fresh attempt before exporting")
    if compile_task(scene["task_spec"]) != scene:
        raise ValueError("compiled scene differs from its frozen TaskSpec")
    agents, end, streams = checked_samples(result)
    if agents != sorted(v["id"] for v in scene["vehicles"]):
        raise ValueError("engine agent identities differ from the task")
    events = result_value(result, "events")
    for event in events:
        stamp = event.get("t_us")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, np.integer)) or not 0 <= stamp <= end:
            raise ValueError("events must have integer simulation times inside the mission")
        if event.get("agent_id") is not None and event["agent_id"] not in agents:
            raise ValueError("event has unknown agent")
        if "t_s" in event and abs(event["t_s"] - stamp / 1e6) > 1e-9:
            raise ValueError("event seconds disagree with integer simulation clock")
    raw_status = result_value(result, "status")
    if raw_status not in ("completed", "complete", "timeout"):
        raise ValueError("unsupported mission status; generator errors cannot be task failures")
    status = "completed" if raw_status in ("completed", "complete") else "timeout"
    traces = traces_from_samples(agents, *streams["support_"])
    labels, semantic, windows = analyze_semantics(scene, traces, events, end / 1e6, status)
    _validate_execution_events(events, status, end, windows)
    constraints = _constraints(scene, traces, end / 1e6, config)
    numerical = _numerics(result, streams, config)
    policy = resolve_quality_policy()
    from ..quality import policy_hash
    protocol = fast_dynamics_protocol()
    clock_quality = dict(overall="exact_sim_clock", time_base="sim_clock",
                         evidence="single integer simulation scheduler", alignment_fit="not_applicable")
    quality = dict(**protocol, quality_policy=policy, quality_policy_sha256=policy_hash(policy),
        time_base="sim_clock", lifecycle_scope="airborne_mission", clock_quality=clock_quality,
        run_completed=status == "completed", nonempty=end > 0, numerical_valid=numerical["passed"],
        data_quality_pass=end > 0, truth_available_pass=end > 0, time_grid_pass=True,
        execution_constraints_pass=constraints["pass_for_eligibility"] is True,
        vehicle_capability_pass=numerical.get("speed_capability_pass", False),
        separation_status=constraints["separation"]["status"], truth_separation=constraints["separation"],
        observation_valid_fraction={a: 1.0 if end else None for a in agents},
        truth_valid_fraction={a: 1.0 if end else None for a in agents},
        parameter_firmware_check=dict(status="not_applicable", reason="no FCU or firmware backend"),
        numerical=numerical, invalid_intervals={a: [] for a in agents})
    eligibility = _eligibility(quality, labels)
    quality.update(eligibility)
    source = dict(simulation_backend="fast_dynamics", engine_version=ENGINE_VERSION,
        plant_model=PLANT_VERSION, controller_version=CONTROLLER_VERSION, observer_version=OBSERVER_VERSION,
        integrator_version=INTEGRATOR_VERSION, task_adapter_version="frozen_compiled_v3_v1",
        semantic_adapter_version=ADAPTER_VERSION, lifecycle_scope="airborne_mission", time_base="sim_clock",
        **SOURCE_DECLARATIONS, capabilities=CAPABILITIES,
        source_sha256=executed_source, input_sha256=dict(input_hashes),
        git_commit=_git_revision(), git_identity_scope="baseline only; source_sha256 binds uncommitted implementation contents",
        task_sha256=canonical_hash(scene["task_spec"]), config=config, config_sha256=canonical_hash(config),
        seed=seed, rng=dict(algorithm="PCG64", consumed=False, reason="M1 deterministic; disturbances disabled"),
        execution_environment=dict(python=platform.python_version(), numpy=np.__version__, platform=platform.platform()),
        end_us=end, time_policy=TIME_POLICY, status=status, diagnostics=result_value(result, "diagnostics"),
        calibration_status="uncalibrated_M1_baseline", intended_use="local_development")
    root.mkdir(parents=True)
    analysis = root / "analysis"
    analysis.mkdir()
    write_json(root / "metadata.json", dict(run_id=run_id, status=status, source=source))
    write_json(root / "input_task.json", scene["task_spec"])
    objects = {"task.json": scene["task_spec"], "compiled_scene.json": scene, "source.json": source,
        "events.json": dict(time_base="sim_clock", events=events), "labels.json": labels,
        "semantic_validation.json": semantic, "phase_windows.json": windows,
        "execution_constraints.json": constraints, "quality.json": quality,
        "allocation.json": scene.get("allocation", scene.get("semantic_plan", {}).get("allocation", {}))}
    for name, obj in objects.items():
        write_json(analysis / name, obj)
    for name, key in (("truth.csv", ""), ("observations.csv", ""),
                      ("support_truth.csv", "support_"), ("support_observations.csv", "support_")):
        _csv(analysis / name, agents, *streams[key],
             np.asarray(result_value(result, "support_accelerations")) if key else None)
    source_hashes = {path.name: file_hash(path) for path in root.iterdir() if path.is_file()}
    manifest = dict(**protocol, **family_metadata(scene["task_spec"]), **eligibility,
        protocol_version=FAST_DYNAMICS_PROTOCOL, analysis_version=ADAPTER_VERSION,
        simulation_backend="fast_dynamics", simulator_version=ENGINE_VERSION,
        run_id=run_id, scenario_id=scene["task_spec"]["scenario"]["scene_id"], run_directory=str(root),
        agent_ids=agents, run_status=status, control_mode=scene["task_spec"]["execution"]["control_mode"],
        intent=scene["task_spec"]["mission"]["intent"], flight_pattern=scene["task_spec"].get("flight_pattern", "line_abreast"),
        component_versions=dict(scene["task_spec"].get("component_versions", {}), facts=FACTS_VERSION),
        mission_success=labels["mission_success"], semantic_consistency=labels["semantic_consistency"],
        clock_quality=clock_quality, quality_policy=policy, quality_policy_sha256=policy_hash(policy),
        duration_s=end / 1e6, end_us=end, record_hz=10, frames=(end + 99_999) // 100_000,
        time_base="sim_clock", time_policy=TIME_POLICY, lifecycle_scope="airborne_mission",
        evaluation_context="local_development_uncalibrated_M1", training_eligible=False,
        training_eligibility_reason="calibration and independent validation not completed",
        source_sha256=source_hashes, artifact_sha256={p.name: file_hash(p) for p in analysis.iterdir()})
    write_json(analysis / "manifest.json", manifest)
    validate_episode(manifest, analysis)
    pointer = root / "analysis_latest.json.tmp"
    write_json(pointer, dict(directory="analysis", manifest_sha256=file_hash(analysis / "manifest.json")))
    pointer.replace(root / "analysis_latest.json")
    return manifest


def validate_episode(manifest, root):
    """Backend-specific cross-artifact checks, separate from the SITL gates."""
    from ..quality import policy_hash
    if manifest_protocol(manifest) != fast_dynamics_protocol():
        raise ValueError("inconsistent fast dynamics semantic protocol")
    required = {"task.json", "compiled_scene.json", "source.json", "labels.json", "quality.json", "events.json",
                "semantic_validation.json", "phase_windows.json", "execution_constraints.json",
                "observations.csv", "truth.csv", "support_truth.csv", "support_observations.csv"}
    if not required <= manifest.get("artifact_sha256", {}).keys():
        raise ValueError("fast dynamics required evidence is not manifest-bound")
    for name, digest in manifest["artifact_sha256"].items():
        path = (root / name).resolve()
        if path.parent != root.resolve() or file_hash(path) != digest:
            raise ValueError(f"fast dynamics artifact changed: {name}")
    objects = {name: json.loads((root / name).read_text(encoding="utf-8")) for name in required if name.endswith(".json")}
    source, quality, task = objects["source.json"], objects["quality.json"], objects["task.json"]
    labels, semantic = objects["labels.json"], objects["semantic_validation.json"]
    end = manifest.get("end_us")
    if type(end) is not int or end < 0 or manifest.get("duration_s") != end / 1e6 or manifest.get("frames") != (end + 99_999) // 100_000:
        raise ValueError("inconsistent actual duration or half-open frame count")
    if (manifest.get("simulation_backend") != "fast_dynamics" or manifest.get("time_base") != "sim_clock"
            or manifest.get("time_policy") != TIME_POLICY or source.get("time_policy") != TIME_POLICY
            or source.get("end_us") != end or source.get("time_base") != "sim_clock"
            or source.get("simulation_backend") != "fast_dynamics" or source.get("lifecycle_scope") != "airborne_mission"
            or manifest.get("lifecycle_scope") != "airborne_mission"):
        raise ValueError("inconsistent fast dynamics source/time contract")
    code_hashes = source.get("source_sha256", {})
    if not code_hashes or not source.get("input_sha256") or any(not isinstance(d, str) or not re.fullmatch(r"[0-9a-f]{64}", d)
                                                             for d in [*code_hashes.values(), *source["input_sha256"].values()]):
        raise ValueError("missing source-content or input hashes")
    config = FastDynamicsConfig.from_dict(source["config"]).to_dict()
    if config != source["config"] or source["config_sha256"] != canonical_hash(config) or source["task_sha256"] != canonical_hash(task):
        raise ValueError("inconsistent frozen configuration/task hashes")
    if compile_task(task) != objects["compiled_scene.json"] or any(manifest.get(k) != value for k, value in family_metadata(task).items()):
        raise ValueError("compiled input or source family identity changed")
    for key, value in dict(engine_version=ENGINE_VERSION, plant_model=PLANT_VERSION,
            controller_version=CONTROLLER_VERSION, observer_version=OBSERVER_VERSION,
            integrator_version=INTEGRATOR_VERSION, semantic_adapter_version=ADAPTER_VERSION).items():
        if source.get(key) != value:
            raise ValueError("unsupported fast dynamics implementation identity")
    if (any(source.get(key) != value for key, value in SOURCE_DECLARATIONS.items())
            or source.get("capabilities") != CAPABILITIES
            or type(source.get("seed")) is not int or source["seed"] < 0
            or not re.fullmatch(r"[0-9a-f]{40,64}", source.get("git_commit", ""))
            or source.get("rng") != dict(algorithm="PCG64", consumed=False, reason="M1 deterministic; disturbances disabled")):
        raise ValueError("inconsistent or unsupported source capabilities, units, seed or code identity")
    if any(name in manifest["artifact_sha256"] for name in ("clock_models.json", "lifecycle_clock_models.json")):
        raise ValueError("fast dynamics must not claim passive FCU clock evidence")
    if (manifest_protocol(quality) != fast_dynamics_protocol()
            or policy_hash(resolve_quality_policy(manifest["quality_policy"])) != manifest["quality_policy_sha256"]
            or quality.get("quality_policy") != manifest["quality_policy"]
            or quality.get("quality_policy_sha256") != manifest["quality_policy_sha256"]
            or manifest.get("clock_quality") != quality.get("clock_quality")
            or quality.get("clock_quality", {}).get("overall") != "exact_sim_clock"
            or quality.get("parameter_firmware_check", {}).get("status") != "not_applicable"):
        raise ValueError("inconsistent backend-specific quality evidence")
    for key, value in _eligibility(quality, labels).items():
        if quality.get(key) is not value or manifest.get(key) is not value:
            raise ValueError("fast dynamics eligibility disagrees with evidence")
    for key in ("mission_success", "mission_success_observation", "semantic_consistency"):
        if labels.get(key) != semantic.get(key):
            raise ValueError("labels and semantic validation disagree")
    if manifest["mission_success"] is not labels["mission_success"] or manifest["semantic_consistency"] != labels["semantic_consistency"]:
        raise ValueError("manifest and labels disagree")
    if source["status"] != manifest["run_status"] or labels["run_status"] != manifest["run_status"]:
        raise ValueError("source and run status disagree")
    if (quality.get("run_completed") is not (manifest["run_status"] == "completed")
            or any(quality.get(key) is not (end > 0) for key in ("nonempty", "data_quality_pass", "truth_available_pass"))
            or quality.get("time_grid_pass") is not True or manifest.get("training_eligible") is not False):
        raise ValueError("quality or training qualification disagrees with M1 scope")
    if (semantic.get("semantic_validation_version") != fast_dynamics_protocol()["semantic_validation_version"]
            or labels.get("label_provenance", {}).get("semantic_validation_version") != semantic["semantic_validation_version"]
            or objects["execution_constraints.json"].get("constraint_validation_version") != fast_dynamics_protocol()["execution_constraints_version"]):
        raise ValueError("inconsistent semantic/constraint rule identities")
    expected_agents = sorted(v["id"] for v in task["scenario"]["vehicles"])
    if manifest.get("agent_ids") != expected_agents:
        raise ValueError("manifest agent identities differ from task")
    from ..observer_facts_v0 import _traces
    for name in ("observations.csv", "truth.csv"):
        rows = _traces(root / name, expected_agents)
        expected_t = [stamp / 1e6 for stamp in range(0, end, 100_000)]
        if any([t for t, _ in rows[a]] != expected_t or any(p is None for _, p in rows[a]) for a in expected_agents):
            raise ValueError("inconsistent half-open stream grid or ideal observation validity")
    if file_hash(root / "truth.csv") != file_hash(root / "observations.csv") or file_hash(root / "support_truth.csv") != file_hash(root / "support_observations.csv"):
        raise ValueError("M1 ideal observation must match plant truth")
    support_t, support_p, support_v, support_a = _read_support(root / "support_truth.csv", expected_agents)
    if end > 0 and (len(support_t) < 2 or support_t[0] != 0 or support_t[-1] != end):
        raise ValueError("support trajectory is missing an actual mission boundary")
    if len(support_t) and (support_t[0] < 0 or support_t[-1] > end):
        raise ValueError("support trajectory extends outside mission time")
    traces = traces_from_samples(expected_agents, support_t, support_p, support_v)
    expected_labels, expected_semantic, expected_windows = analyze_semantics(objects["compiled_scene.json"], traces,
        objects["events.json"]["events"], end / 1e6, manifest["run_status"])
    _validate_execution_events(objects["events.json"]["events"], manifest["run_status"], end, expected_windows)
    if labels != expected_labels or semantic != expected_semantic or objects["phase_windows.json"] != expected_windows:
        raise ValueError("semantic claims disagree with actual support trajectory and events")
    numerical = _numerics(dict(support_accelerations=support_a), {"support_": (support_t, support_p, support_v)}, config)
    if numerical != quality["numerical"] or quality["numerical_valid"] is not numerical["passed"]:
        raise ValueError("numerical claims disagree with support states")
    if quality.get("vehicle_capability_pass") is not numerical.get("speed_capability_pass", False):
        raise ValueError("vehicle capability claims disagree with measured speed")
    constraints = _constraints(objects["compiled_scene.json"], traces, end / 1e6, config)
    if (objects["execution_constraints.json"] != constraints
            or quality["execution_constraints_pass"] is not (constraints["pass_for_eligibility"] is True)
            or quality["separation_status"] != constraints["separation"]["status"]):
        raise ValueError("constraint claims disagree with support states")
    # Ideal observation exports must be the identical states at shared times;
    # source agreement alone cannot conceal a separately fabricated 10 Hz view.
    output_rows = _traces(root / "observations.csv", expected_agents)
    lookup = {int(t): k for k, t in enumerate(support_t)}
    for i, agent in enumerate(expected_agents):
        for stamp, position in output_rows[agent]:
            k = lookup.get(round(stamp * 1e6))
            if k is None or position != support_p[k, i].tolist():
                raise ValueError("exported positions disagree with support evidence")
    with (root / "observations.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            k = lookup[round(float(row["t_s"]) * 1e6)]
            i = expected_agents.index(row["agent_id"])
            if [float(row[key]) for key in FEATURES[3:]] != support_v[k, i].tolist():
                raise ValueError("exported velocities disagree with support evidence")
