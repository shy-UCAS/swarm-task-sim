"""V3 lifecycle with WP-S-bound preflight and semantic route phase barriers."""

import hashlib
import importlib.metadata
import json
import platform
import sys
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .processes import SITLProcesses
from .quality import policy_hash, resolve_policy
from .recording import Recorder, write_json
from .run_provenance import (PARAMETER_COMPARISON_VERSION, PROVENANCE_VERSION, compare_parameter_readback, digest,
                             read_firmware_parameters, verify_preflight_files)
from .scenario import mission_for, validate
from .tasks import target_confirmation, validate_task_binding
from .vehicle import Vehicle


RUNNER_VERSION = "v3_phase_runner_v1"


def phase_time_budget(scenario, phase, remaining_s):
    if scenario["schema_version"] == 2:
        nominal = scenario["planning"]["nominal_phase_timing"][phase["name"]]["duration_s"]
    else:
        nominal = next(row["estimated_s"] for row in scenario["planning"]["feasibility_checks"]
                       ["nominal_budget"]["stage_estimates"] if row["phase"] == phase["name"])
    original = min(remaining_s, 3 * nominal + 30)
    override = scenario["task_spec"]["execution"].get("phase_timeout_override_s")
    return dict(nominal_duration_s=nominal, multiplier=3.0, allowance_s=30.0,
                scenario_remaining_s=remaining_s, phase_timeout_override_s=override,
                effective_timeout_s=min(original, override) if override is not None else original,
                scope="upload through terminal geometric confirmation; no automatic phase retry")


def execute_phases(scenario, clients, parallel, event, metadata, epoch, deadline, persist):
    """No per-waypoint synchronization: one upload/execute/confirm per phase."""
    from .scenario import route_mission_for

    route_mode = scenario["schema_version"] == 2
    metadata["phase_timing"] = {}
    for phase in scenario["phases"]:
        started = time.perf_counter()
        budget = phase_time_budget(scenario, phase, deadline - started)
        phase_deadline = started + budget["effective_timeout_s"]
        timing = dict(budget, started_monotonic_s=started, status="running", operations={})
        metadata["phase_timing"][phase["name"]] = timing
        roles = scenario["semantic_plan"]["execution_phases"][phase["name"]]["agents"]
        plans = {}
        for vehicle in scenario["vehicles"]:
            agent = vehicle["id"]
            if route_mode:
                route = phase["routes"][agent]
                if route:
                    plans[agent] = route_mission_for(vehicle, route, phase["speed_m_s"],
                                                      phase["terminal_hold_s"], scenario["origin"])
            else:
                plans[agent] = mission_for(vehicle, phase["targets"][agent], scenario["origin"])

        def operation(name, function):
            begin = time.perf_counter()
            row = timing["operations"][name] = dict(started_monotonic_s=begin, complete=False)
            if name == "execute":
                timing["release_wait_s"] = max(0.0, timing["release_monotonic_s"] - begin)
            try:
                parallel(function, deadline_override=phase_deadline, context=f"phase {phase['name']} {name}")
                row["complete"] = True
            finally:
                row["finished_monotonic_s"] = time.perf_counter()
                row["duration_s"] = row["finished_monotonic_s"] - begin

        try:
            event("phase_budget", phase=phase["name"], **budget)

            def upload(client, vehicle):
                if client.id not in plans:
                    event("phase_upload_skipped", client.id, phase=phase["name"], reason="hold_no_op")
                    return
                begin = time.perf_counter()
                event("phase_upload_started", client.id, phase=phase["name"], mission_item_count=len(plans[client.id]))
                client.upload(plans[client.id], timeout=max(.001, phase_deadline - begin))
                event("phase_upload_complete", client.id, phase=phase["name"], duration_s=time.perf_counter() - begin)

            operation("upload", upload)
            release = time.perf_counter() + .3
            if "flight_epoch_monotonic_s" not in metadata:
                metadata["flight_epoch_monotonic_s"] = release
            timing["release_monotonic_s"] = release
            start_delays = phase.get("start_delays_s", {})
            if start_delays:
                timing["agent_release_monotonic_s"] = {
                    client.id: release + start_delays.get(client.id, 0.0) for client in clients}
            persist()
            event("phase_release_scheduled", phase=phase["name"], release_t=release - epoch)

            def execute(client, vehicle):
                agent_release = release + start_delays.get(client.id, 0.0)
                if client.id in plans:
                    client.execution_waypoint_indices = roles[client.id].get("waypoint_planner_indices")
                    client.execute(agent_release, len(plans[client.id]), max(.001, phase_deadline - time.perf_counter()), phase["name"])
                else:
                    while time.perf_counter() < agent_release:
                        client.check()
                        client.cancel.wait(min(.01, max(0, agent_release - time.perf_counter())))
                    event("phase_no_op_started", client.id, phase=phase["name"], role="hold_no_op", service_enabled=False)

            operation("execute", execute)

            def confirm(client, vehicle):
                requirement = target_confirmation(scenario, phase, client.id)
                target = roles[client.id]["terminal_point"] if route_mode else phase["targets"][client.id]
                dwell = requirement["dwell_s"]
                client.confirm_target(target, scenario["origin"], requirement["tolerance_m"], dwell, phase["name"],
                    timeout=min(dwell + 20, max(.001, phase_deadline - time.perf_counter())),
                    max_gap=scenario["max_gap_s"], quality_policy=metadata["quality_policy"])
                if roles[client.id]["role"] == "hold_no_op":
                    event("phase_no_op_ready", client.id, phase=phase["name"], role="hold_no_op", service_enabled=False)

            operation("confirm", confirm)
            timing["status"] = "completed"
        except BaseException as exc:
            timing.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            timing["finished_monotonic_s"] = time.perf_counter()
            timing["total_duration_s"] = timing["finished_monotonic_s"] - started
            for row in timing["operations"].values():
                row["fraction_of_phase"] = row["duration_s"] / timing["total_duration_s"] if timing["total_duration_s"] > 0 else None
            duration = lambda name: timing["operations"].get(name, {}).get("duration_s")
            timing.update(upload_duration_s=duration("upload"), confirmation_duration_s=duration("confirm"),
                          execute_including_release_wait_s=duration("execute"))
            if all(timing.get(key) is not None for key in ("upload_duration_s", "confirmation_duration_s", "release_wait_s")):
                overhead = timing["upload_duration_s"] + timing["confirmation_duration_s"] + timing["release_wait_s"]
                timing["upload_release_confirmation_overhead_s"] = overhead
                timing["upload_release_confirmation_fraction"] = overhead / timing["total_duration_s"]
                timing["execution_duration_s"] = max(0.0, timing["execute_including_release_wait_s"] - timing["release_wait_s"])
            persist()


def execute_final_hold(scenario, clients, parallel, event, metadata, deadline, persist):
    """Observe the final endpoint continuously before recording mission end.

    This is independent of the normal 0.5 s arrival confirmation and NAV item
    terminal_hold_s. It adds no mission item and therefore changes no onboard
    parameter comparison. Legacy tasks omit final_hold_s and do nothing here.
    """
    hold = scenario["task_spec"]["execution"].get("final_hold_s", 0.0)
    if not hold:
        return
    phase = scenario["phases"][-1]
    roles = scenario["semantic_plan"]["execution_phases"][phase["name"]]["agents"]
    timing = metadata["final_hold"] = dict(duration_s=hold, phase=phase["name"],
        started_monotonic_s=time.perf_counter(), status="running")
    event("final_hold_started", phase=phase["name"], duration_s=hold)
    persist()

    def hold_endpoint(client, vehicle):
        requirement = target_confirmation(scenario, phase, client.id)
        target = (roles[client.id]["terminal_point"] if scenario["schema_version"] == 2
                  else phase["targets"][client.id])
        client.confirm_target(target, scenario["origin"], requirement["tolerance_m"], hold,
            phase["name"], timeout=min(hold + 20, max(.001, deadline - time.perf_counter())),
            max_gap=scenario["max_gap_s"], quality_policy=metadata["quality_policy"])

    try:
        parallel(hold_endpoint, deadline_override=deadline, context="final endpoint hold")
        timing["status"] = "completed"
        event("final_hold_complete", phase=phase["name"], duration_s=hold)
    except BaseException as exc:
        timing.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        timing["finished_monotonic_s"] = time.perf_counter()
        persist()


def run_scene_v3(scenario, output_root, binary, parameters, base_port=19100, quality_policy=None, generation_context=None):
    scenario = validate(scenario)
    validate_task_binding(scenario)
    if scenario["task_spec"]["schema_version"] != 3:
        raise ValueError("v3 runner requires a bound TaskSpec v3")
    policy = resolve_policy(quality_policy)
    if generation_context is not None and (not isinstance(generation_context, dict) or set(generation_context) != {
            "generation_profile", "generation_manifest", "generation_entry"}):
        raise ValueError("generation context must contain exactly profile, manifest and entry evidence")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    directory = Path(output_root).resolve() / f"{scenario['scenario_id']}_{run_id}"
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "raw").mkdir()
    for name, content in (generation_context or {}).items():
        write_json(directory / (name + ".json"), content)
    epoch = time.perf_counter()
    deadline = epoch + scenario["timeout_s"]
    cancel, event_lock = threading.Event(), threading.Lock()
    events = []
    event_file = (directory / "events.jsonl").open("w", encoding="utf-8", buffering=1)

    def event(kind, agent=None, **fields):
        stamp = fields["recv_monotonic_s"] if kind == "waypoint_reached" else time.perf_counter()
        packet = dict(event=kind, agent_id=agent, t=stamp - epoch, **fields)
        with event_lock:
            events.append(packet)
            event_file.write(json.dumps(packet, ensure_ascii=False) + "\n")
        print(f"[{packet['t']:7.2f}s] {agent or 'swarm'}: {kind} {fields or ''}", flush=True)

    metadata = dict(schema_version=1, version=__version__, runner_version=RUNNER_VERSION, run_id=run_id,
        parameter_comparison_version=PARAMETER_COMPARISON_VERSION,
        scenario=scenario, quality_policy=policy, quality_policy_sha256=policy_hash(policy), status="running",
        host=platform.platform(), python=sys.version, pymavlink=importlib.metadata.version("pymavlink"),
        run_epoch_monotonic_s=epoch, started_utc=datetime.now(timezone.utc).isoformat(),
        scenario_sha256=hashlib.sha256(json.dumps(scenario, sort_keys=True).encode()).hexdigest(),
        clock="host perf_counter; speedup=1; phase_auto_confirmed=received AUTO heartbeat confirmation; waypoint_reached=raw receive time",
        source_sha256={p.name: digest(p) for p in Path(__file__).parent.glob("*.py")},
        run_provenance=dict(version=PROVENANCE_VERSION,
                           parameter_comparison_version=PARAMETER_COMPARISON_VERSION, status="pending"))
    persist = lambda: write_json(directory / "metadata.json", metadata)
    persist()
    write_json(directory / "scenario.json", scenario)
    processes, clients, recorder = None, [], None
    parameter_evidence = {vehicle["id"]: dict(status="not_started", complete=False, parameter_count=None,
                          parameter_comparison_version=PARAMETER_COMPARISON_VERSION,
                          parameter_comparison={"version": PARAMETER_COMPARISON_VERSION,
                                                "status": "not_evaluated", "pass": False},
                          received_count=0, missing_indices=None, requests=[]) for vehicle in scenario["vehicles"]}
    executor = ThreadPoolExecutor(max_workers=len(scenario["vehicles"]), thread_name_prefix="v3-control")

    def parallel(function, deadline_override=None, context="scenario"):
        operation_deadline = min(deadline, deadline_override) if deadline_override is not None else deadline
        if time.perf_counter() >= operation_deadline:
            raise TimeoutError(f"{context} timeout")
        futures = {executor.submit(function, client, vehicle) for client, vehicle in zip(clients, scenario["vehicles"])}
        while futures:
            if time.perf_counter() >= operation_deadline:
                raise TimeoutError(f"{context} timeout")
            processes.check()
            if recorder and recorder.error:
                raise RuntimeError(f"recorder failed: {recorder.error}")
            for client in clients:
                client.check()
            done, futures = wait(futures, timeout=min(.1, max(.001, operation_deadline - time.perf_counter())),
                                 return_when=FIRST_COMPLETED)
            for future in done:
                future.result()
        if time.perf_counter() > operation_deadline:
            raise TimeoutError(f"{context} timeout")

    try:
        provenance = verify_preflight_files(binary, parameters)
        metadata["run_provenance"] = {key: value for key, value in provenance.items() if key != "baseline"}
        metadata["binary_firmware"] = provenance["actual"]["firmware"]
        metadata["parameters_sha256"] = provenance["actual"]["parameters_sha256"]
        persist()
        processes = SITLProcesses(binary, parameters, directory, scenario, base_port)
        instances = processes.start()
        metadata["sitl"] = processes.metadata()
        # Detect a binary change between initial verification and process launch.
        if metadata["sitl"]["sha256"] != metadata["binary_firmware"]["sha256"] or digest(parameters) != metadata["parameters_sha256"]:
            raise ValueError("firmware/template changed during launch; a new WP-S GO is required")
        persist()
        clients = [Vehicle(instance, directory / "raw" / f"{instance['id']}.jsonl", cancel, event, record_lifecycle=True)
                   for instance in instances]
        parallel(lambda client, vehicle: client.connect())
        recorder = Recorder(directory, clients, scenario["origin"], epoch, scenario["record_hz"], scenario["max_gap_s"], policy)
        recorder.start()

        def read_parameters(client, vehicle):
            try:
                execution = scenario["task_spec"]["execution"]
                options = ({"version_timeout_s": execution["firmware_version_timeout_s"]}
                           if "firmware_version_timeout_s" in execution else {})
                result = read_firmware_parameters(client, metadata["binary_firmware"], parameter_evidence[client.id], **options)
            except BaseException:
                # Also record the version and any available STAT_RESET evidence
                # on cancellation/partial RX, without masking the original error.
                try:
                    compare_parameter_readback(parameter_evidence[client.id], provenance["baseline"], client.sysid,
                                               run_started_utc=metadata["started_utc"])
                except ValueError:
                    pass
                raise
            compare_parameter_readback(result, provenance["baseline"], client.sysid,
                                       run_started_utc=metadata["started_utc"])

        parallel(read_parameters, context="preflight parameter readback")
        metadata["run_provenance"]["status"] = "verified_before_takeoff"
        metadata["run_provenance"]["verified_monotonic_s"] = time.perf_counter()
        write_json(directory / "firmware_parameters.json", parameter_evidence)
        metadata["run_provenance"]["parameter_evidence"] = dict(path="firmware_parameters.json", sha256=digest(directory / "firmware_parameters.json"))
        persist()
        event("preflight_verified", version=PROVENANCE_VERSION,
              parameter_comparison_version=PARAMETER_COMPARISON_VERSION)
        parallel(lambda client, vehicle: client.prepare_airborne(scenario["takeoff_alt_m"], scenario["ready_timeout_s"]))
        execute_phases(scenario, clients, parallel, event, metadata, epoch, deadline, persist)
        execute_final_hold(scenario, clients, parallel, event, metadata, deadline, persist)
        metadata["mission_end_monotonic_s"] = time.perf_counter()
        parallel(lambda client, vehicle: client.land())
        cancel.wait(2)
        metadata["status"] = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        metadata.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                        error=f"{type(exc).__name__}: {exc}")
        if metadata["run_provenance"]["status"] != "verified_before_takeoff":
            metadata["run_provenance"].update(status="failed", error=metadata["error"])
        event("run_failed", error=metadata["error"])
    finally:
        cancel.set()
        executor.shutdown(wait=True, cancel_futures=True)
        if recorder:
            recorder.close()
            if recorder.error:
                metadata.update(status="failed", error=f"recorder: {recorder.error}")
        for client in clients:
            client.close()
        if processes:
            processes.close()
        event_file.close()
        write_json(directory / "firmware_parameters.json", parameter_evidence)
        metadata["run_provenance"]["parameter_evidence"] = dict(path="firmware_parameters.json",
            sha256=digest(directory / "firmware_parameters.json"),
            per_agent={agent: {key: record.get(key) for key in ("complete", "status", "parameter_count", "received_count", "missing_indices")}
                       for agent, record in parameter_evidence.items()})
        metadata["elapsed_s"] = time.perf_counter() - epoch
        metadata["cleanup"] = ({v["id"]: p.poll() for v, p in zip(processes.instances, processes.processes)} if processes else {})
        metadata["phase_start_spread_s"] = {}
        for phase in scenario["phases"]:
            starts = [e["t"] for e in events if e["event"] in ("phase_start_sent", "phase_no_op_started") and e.get("phase") == phase["name"]]
            if len(starts) == len(scenario["vehicles"]):
                metadata["phase_start_spread_s"][phase["name"]] = max(starts) - min(starts)
        persist()
    quality = dict(run_status=metadata["status"], usable=False, available=False, benchmark_eligible=False,
                   strict_benchmark_eligible=False, episode_quality_eligible=False,
                   quality_policy=policy, quality_policy_sha256=policy_hash(policy))
    write_json(directory / "quality.json", quality)
    try:
        from .analysis import analyze_run
        analysis_path, analysis_quality, labels = analyze_run(directory, policy)
        quality.update(analysis_quality, analysis_directory=analysis_path.name,
                       mission_success=labels["mission_success"],
                       mission_success_observation=labels["mission_success_observation"],
                       semantic_consistency=labels["semantic_consistency"],
                       usable=analysis_quality["benchmark_eligible"],
                       available="flight_epoch_monotonic_s" in metadata and "mission_end_monotonic_s" in metadata)
    except Exception as exc:
        quality["analysis_error"] = f"{type(exc).__name__}: {exc}"
    write_json(directory / "quality.json", quality)
    print(f"Result: {metadata['status']}; usable: {quality['usable']}; data: {directory}", flush=True)
    return directory, metadata, quality
