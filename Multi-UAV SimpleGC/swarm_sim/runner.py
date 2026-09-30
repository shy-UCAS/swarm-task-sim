"""Bounded scene lifecycle: launch, prepare, shared phases, land, close, export."""

import hashlib
import importlib.metadata
import json
import platform
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .processes import SITLProcesses
from .recording import Recorder, export_dataset, write_json
from .scenario import mission_for, validate
from .vehicle import Vehicle
from .tasks import target_confirmation, validate_task_binding
from .quality import policy_hash, resolve_policy


def run_scene(scenario, output_root, binary, parameters, base_port=19100, quality_policy=None, generation_context=None):
    scenario = validate(scenario)
    validate_task_binding(scenario)
    policy = resolve_policy(quality_policy)
    shared_mission = scenario.get("task_spec", {}).get("schema_version") == 2
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    directory = Path(output_root).resolve() / f"{scenario['scenario_id']}_{run_id}"
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "raw").mkdir()
    if generation_context is not None:
        if not isinstance(generation_context, dict) or set(generation_context) != {"generation_profile", "generation_manifest", "generation_entry"}:
            raise ValueError("generation context must contain exactly profile, manifest and entry evidence")
        for name, content in generation_context.items():
            write_json(directory / (name + ".json"), content)
    epoch = time.perf_counter()
    deadline = epoch + scenario["timeout_s"]
    cancel = threading.Event()
    event_lock = threading.Lock()
    events = []
    event_file = (directory / "events.jsonl").open("w", encoding="utf-8", buffering=1)

    def event(kind, agent=None, **fields):
        packet = dict(event=kind, agent_id=agent, t=time.perf_counter() - epoch, **fields)
        with event_lock:
            events.append(packet)
            event_file.write(json.dumps(packet, ensure_ascii=False) + "\n")
        print(f"[{packet['t']:7.2f}s] {agent or 'swarm'}: {kind} {fields or ''}", flush=True)

    metadata = dict(schema_version=1, version=__version__, run_id=run_id, scenario=scenario,
                    quality_policy=policy, quality_policy_sha256=policy_hash(policy),
                    status="running", host=platform.platform(), python=sys.version,
                    pymavlink=importlib.metadata.version("pymavlink"), run_epoch_monotonic_s=epoch,
                    started_utc=datetime.now(timezone.utc).isoformat(),
                    scenario_sha256=hashlib.sha256(json.dumps(scenario, sort_keys=True).encode()).hexdigest(),
                    clock="host time.perf_counter (monotonic); speedup=1; phase release barrier, no lockstep",
                    source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in Path(__file__).parent.glob("*.py")})
    write_json(directory / "metadata.json", metadata)
    write_json(directory / "scenario.json", scenario)
    processes = SITLProcesses(binary, parameters, directory, scenario, base_port)
    clients = []
    recorder = None
    executor = ThreadPoolExecutor(max_workers=len(scenario["vehicles"]), thread_name_prefix="control")

    def parallel(function):
        futures = {executor.submit(function, client, vehicle) for client, vehicle in zip(clients, scenario["vehicles"])}
        while futures:
            if time.perf_counter() > deadline:
                raise TimeoutError("scenario total timeout")
            processes.check()
            if recorder and recorder.error:
                raise RuntimeError(f"recorder failed: {recorder.error}")
            for client in clients:
                client.check()
            done, futures = wait(futures, timeout=0.1, return_when=FIRST_COMPLETED)
            for future in done:
                future.result()

    try:
        instances = processes.start()
        metadata["sitl"] = processes.metadata()
        write_json(directory / "metadata.json", metadata)
        clients = [Vehicle(instance, directory / "raw" / f"{instance['id']}.jsonl", cancel, event,
                           record_lifecycle=shared_mission)
                   for instance in instances]
        parallel(lambda client, vehicle: client.connect())
        recorder = Recorder(directory, clients, scenario["origin"], epoch,
                            scenario["record_hz"], scenario["max_gap_s"], policy)
        recorder.start()
        parallel(lambda client, vehicle: client.prepare_airborne(scenario["takeoff_alt_m"], scenario["ready_timeout_s"]))
        for phase in scenario["phases"]:
            plans = {v["id"]: mission_for(v, phase["targets"][v["id"]], scenario["origin"])
                     for v in scenario["vehicles"]}
            parallel(lambda client, vehicle: client.upload(plans[client.id]))
            release = time.perf_counter() + 0.3
            if "flight_epoch_monotonic_s" not in metadata:
                metadata["flight_epoch_monotonic_s"] = release
                write_json(directory / "metadata.json", metadata)
            event("phase_release_scheduled", phase=phase["name"], release_t=release - epoch)
            parallel(lambda client, vehicle: client.execute(release, len(plans[client.id]),
                                                            max(1, deadline - time.perf_counter()), phase["name"]))
            if "task_spec" in scenario:
                def confirm(client, vehicle):
                    requirement = target_confirmation(scenario, phase, client.id)
                    options = dict(max_gap=scenario["max_gap_s"], quality_policy=policy) if shared_mission else {}
                    client.confirm_target(phase["targets"][client.id], scenario["origin"],
                        requirement["tolerance_m"], requirement["dwell_s"], phase["name"],
                        timeout=min(requirement["dwell_s"] + 20, max(1, deadline - time.perf_counter())), **options)
                parallel(confirm)
        metadata["mission_end_monotonic_s"] = time.perf_counter()
        parallel(lambda client, vehicle: client.land())
        if shared_mission:
            # Record a short disarmed tail so passive clock knots bracket landing.
            cancel.wait(2)
        metadata["status"] = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        metadata["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        metadata["error"] = f"{type(exc).__name__}: {exc}"
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
        processes.close()
        event_file.close()
        metadata["elapsed_s"] = time.perf_counter() - epoch
        metadata["cleanup"] = {v["id"]: p.poll() for v, p in zip(processes.instances, processes.processes)}
        metadata["phase_start_spread_s"] = {}
        for phase in scenario["phases"]:
            starts = [e["t"] for e in events if e["event"] == "phase_start_sent" and e.get("phase") == phase["name"]]
            if len(starts) == len(scenario["vehicles"]):
                metadata["phase_start_spread_s"][phase["name"]] = max(starts) - min(starts)
        write_json(directory / "metadata.json", metadata)
    try:
        quality = export_dataset(directory, metadata, policy)
    except Exception as exc:
        quality = dict(available=False, error=f"{type(exc).__name__}: {exc}")
        metadata.update(status="failed", error=f"dataset export failed: {exc}")
        write_json(directory / "metadata.json", metadata)
    quality["run_status"] = metadata["status"]
    quality["usable"] = (metadata["status"] == "completed" and quality.get("available", False)
                         and not quality.get("collision_risk", True)
                         and all(value >= policy["min_observation_valid_fraction"] for value in quality.get("valid_fraction", {}).values()))
    quality.update(quality_policy=policy, quality_policy_sha256=policy_hash(policy), strict_benchmark_eligible=False)
    write_json(directory / "quality.json", quality)
    # Offline analysis runs only after all owned SITL processes and log writers close.
    try:
        from .analysis import analyze_run
        analysis_path, analysis_quality, labels = analyze_run(directory, policy)
        quality["analysis_directory"] = analysis_path.name
        quality["benchmark_eligible"] = analysis_quality["benchmark_eligible"]
        quality["strict_benchmark_eligible"] = analysis_quality["strict_benchmark_eligible"]
        quality["clock_quality"] = analysis_quality["clock_quality"]
        quality["mission_success"] = labels["mission_success"]
        if shared_mission:
            quality["mission_success_observation"] = labels["mission_success_observation"]
            quality["semantic_consistency"] = labels["semantic_consistency"]
            quality["execution_constraints_pass"] = analysis_quality["execution_constraints_pass"]
        if "task_spec" in scenario:
            quality["usable"] = analysis_quality["benchmark_eligible"]
    except Exception as exc:
        quality["analysis_error"] = f"{type(exc).__name__}: {exc}"
        quality["benchmark_eligible"] = False
        if "task_spec" in scenario:
            quality["usable"] = False
    write_json(directory / "quality.json", quality)
    print(f"Result: {metadata['status']}; usable: {quality['usable']}; "
          f"mission_success: {quality.get('mission_success')}; data: {directory}", flush=True)
    if "analysis_error" in quality:
        print(f"Analysis error: {quality['analysis_error']}", flush=True)
    return directory, metadata, quality
