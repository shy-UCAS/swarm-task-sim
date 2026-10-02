"""WP-S experiment only: continuous AUTO routes, without changing the v2 backend.

Run twice and inspect the measurements before implementing WP-G/WP-E. This
script creates isolated spike_v04_* directories; it never exports a dataset.
"""

import argparse
import copy
import hashlib
import importlib.metadata
import json
import math
import platform
import re
import sys
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from swarm_sim import __version__
from swarm_sim.processes import SITLProcesses
from swarm_sim.quality import policy_hash, resolve_policy
from swarm_sim.recording import Recorder, write_json
from swarm_sim.scenario import enu_to_geo
from swarm_sim.tasks import compile_task, validate_task_binding
from swarm_sim.vehicle import Vehicle

SPIKE_VERSION = "continuous_route_spike_v1"


def build_spike_plan(scene, lane_end_overshoot_m=0):
    """Use the frozen planner's routes, removing only the repeated observe start.

    Deduplication compares planned phase endpoints, not a new online replanner.
    Optional lane-end extension is the sole experiment allowed after coverage
    alone fails. It is applied consistently to approach and observe endpoints.
    """
    validate_task_binding(scene)
    spec = scene["task_spec"]
    if spec["schema_version"] != 2 or spec["mission"]["intent"] != "reconnaissance":
        raise ValueError("WP-S requires a frozen v2 reconnaissance task")
    radius = spec["mission"]["observation_model"]["radius_m"]
    if (isinstance(lane_end_overshoot_m, bool) or not isinstance(lane_end_overshoot_m, (int, float))
            or not math.isfinite(lane_end_overshoot_m) or not 0 <= lane_end_overshoot_m <= radius):
        raise ValueError("lane-end extension must be finite, nonnegative and no larger than observation radius")
    source = copy.deepcopy(scene["planning"]["per_agent_reference_routes"])
    axis = scene["planning"]["sweep_axis"]
    region = next(r for r in spec["scenario"]["regions"] if r["id"] == spec["mission"]["target_region_id"])
    low = region[f"min_{axis}_m"]
    high = low + region["height_m" if axis == "north" else "width_m"]
    altitude = scene["takeoff_alt_m"]
    if lane_end_overshoot_m:
        for routes in source.values():
            for point in routes["observe"]:
                point[f"{axis}_m"] += -lane_end_overshoot_m if abs(point[f"{axis}_m"] - low) < 1e-8 else lane_end_overshoot_m
            routes["approach"] = [copy.deepcopy(routes["observe"][0])]
    previous = {v["id"]: {"east_m": v["east_m"], "north_m": v["north_m"], "up_m": altitude}
                for v in scene["vehicles"]}
    phases = []
    for index, semantic in enumerate(("approach", "observe", "return")):
        phase = dict(name=f"p{index:02d}_{semantic}", semantic_phase=semantic, routes={},
                     start_positions=copy.deepcopy(previous), speed_m_s=spec["execution"]["speed_m_s"],
                     terminal_hold_s=0.5, removed_duplicate_starts={})
        for agent, routes in source.items():
            points = [dict(point, up_m=altitude) for point in routes[semantic]]
            removed = 0
            if semantic == "observe" and points and math.dist(
                    [points[0][k] for k in ("east_m", "north_m", "up_m")],
                    [previous[agent][k] for k in ("east_m", "north_m", "up_m")]) < 0.05:
                points = points[1:]
                removed = 1
            if not points:
                raise ValueError("WP-S expects nonempty approach, observe and return routes")
            for point in points:
                for coordinate in ("east", "north"):
                    lower, upper = spec["scenario"]["world"][f"{coordinate}_bounds_m"]
                    if not lower <= point[f"{coordinate}_m"] <= upper:
                        raise ValueError("lane-end extension leaves world bounds")
            phase["routes"][agent] = points
            phase["removed_duplicate_starts"][agent] = removed
            previous[agent] = copy.deepcopy(points[-1])
        phases.append(phase)
    return dict(schema_version=1, experiment_version=SPIKE_VERSION, phases=phases,
                lane_end_overshoot_m=lane_end_overshoot_m,
                reference_task_id=spec["task_id"],
                note="WP-S evidence only; scenario.json remains the unmodified v2 reference, spike_plan.json is executed")


def route_mission_for(vehicle, route, speed_m_s, terminal_hold_s, origin):
    if not route or len(route) > 100:
        raise ValueError("WP-S route must contain 1 to 100 NAV_WAYPOINT items")
    home_lat, home_lon = enu_to_geo(vehicle["east_m"], vehicle["north_m"], origin)
    mission = [dict(command=16, frame=3, params=[0, 0, 0, 0], lat=home_lat, lon=home_lon, alt=0),
               dict(command=178, frame=2, params=[1, speed_m_s, -1, 0], lat=0, lon=0, alt=0)]
    for index, point in enumerate(route):
        lat, lon = enu_to_geo(point["east_m"], point["north_m"], origin)
        mission.append(dict(command=16, frame=3,
                            params=[terminal_hold_s if index == len(route) - 1 else 0, 1, 0, float("nan")],
                            lat=lat, lon=lon, alt=point["up_m"]))
    return mission


def read_firmware_parameters(client, timeout=30, binary_firmware=None):
    """Read (never set) firmware identity and the complete parameter table.

    Observe the existing sequence-numbered inbox. There is no second MAVLink
    receiver. Completeness of count/indices is required before claiming all
    WPNAV parameters have been read; missing indices are requested explicitly.
    """
    cursor = client.cursor()
    client.send("command_long_send", client.sysid, client.target_component, 520, 0, 1, 0, 0, 0, 0, 0, 0)
    try:
        version = client.wait_message(["AUTOPILOT_VERSION"], after=cursor, timeout=min(timeout, 10))
    except TimeoutError:
        if not binary_firmware:
            raise
        version = None
    cursor = client.cursor()
    client.send("param_request_list_send", client.sysid, client.target_component)
    deadline = time.perf_counter() + timeout
    next_retry = time.perf_counter() + 5
    values, count = {}, None
    while time.perf_counter() < deadline:
        client.check()
        with client.condition:
            batch = [(seq, message) for seq, kind, message in client.inbox if seq > cursor and kind == "PARAM_VALUE"]
            cursor = client.sequence
        for _, message in batch:
            reported = int(message.param_count)
            if count is not None and count != reported:
                raise ValueError("parameter table count changed during readback")
            count = reported
            index = int(message.param_index)
            name = message.param_id
            if isinstance(name, bytes):
                name = name.decode("ascii")
            name = name.rstrip("\x00")
            if not 0 <= index < count or not math.isfinite(message.param_value):
                raise ValueError("invalid parameter index/value in readback")
            values[index] = dict(name=name, value=float(message.param_value), type=int(message.param_type))
        if count and set(values) == set(range(count)):
            parameters = {entry["name"]: entry["value"] for entry in values.values()}
            wpnav = {name: value for name, value in sorted(parameters.items()) if name.startswith("WPNAV_")}
            if len(parameters) != count or not wpnav:
                raise ValueError("parameter names are duplicated or no WPNAV parameters were returned")
            firmware = dict(binary_metadata=binary_firmware, autopilot_version_available=version is not None)
            if version is not None:
                number = int(version.flight_sw_version)
                firmware.update(version.to_dict())
                firmware["version_string"] = f"{number >> 24}.{(number >> 16) & 255}.{(number >> 8) & 255} (type {number & 255})"
            else:
                firmware["version_string"] = binary_firmware["version_string"]
            return dict(firmware=firmware, complete=True, parameter_count=count, received_count=len(values),
                        wpnav=wpnav, all_parameters=parameters,
                        method="AUTOPILOT_VERSION or recorded binary metadata + complete PARAM_VALUE indices; read-only")
        if time.perf_counter() >= next_retry:
            if count is None:
                client.send("param_request_list_send", client.sysid, client.target_component)
            else:
                for index in sorted(set(range(count)) - set(values))[:100]:
                    client.send("param_request_read_send", client.sysid, client.target_component, b"", index)
            next_retry = time.perf_counter() + 5
        client.cancel.wait(0.05)
    raise TimeoutError(f"{client.id}: incomplete parameter readback ({len(values)}/{count})")


def _source_hashes():
    paths = list((PROJECT / "swarm_sim").glob("*.py")) + list((PROJECT / "scripts").glob("spike*.py"))
    return {str(path.relative_to(PROJECT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths}


def run_spike(mission_path, output_root, binary, parameters, base_port=20100, lane_end_overshoot_m=0):
    """One owned local SITL run; always close resources and retain failures."""
    mission_path = Path(mission_path)
    scene = compile_task(json.loads(mission_path.read_text(encoding="utf-8-sig")))
    plan = build_spike_plan(scene, lane_end_overshoot_m)
    output_root = Path(output_root).resolve()
    previous_runs = list(output_root.glob("spike_v04_*/metadata.json"))
    if len(previous_runs) >= 3:
        raise ValueError("WP-S maximum of 3 runs reached in this output root; stop and report")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    directory = output_root / f"spike_v04_{run_id}"
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "raw").mkdir()
    epoch = time.perf_counter()
    deadline = epoch + scene["timeout_s"]
    policy = resolve_policy(None)
    cancel, event_lock = threading.Event(), threading.Lock()
    event_file = (directory / "events.jsonl").open("w", encoding="utf-8", buffering=1)

    def event(kind, agent=None, **fields):
        packet = dict(event=kind, agent_id=agent, t=time.perf_counter() - epoch, **fields)
        with event_lock:
            event_file.write(json.dumps(packet, ensure_ascii=False) + "\n")
        print(f"[{packet['t']:7.2f}s] {agent or 'swarm'}: {kind} {fields or ''}", flush=True)

    metadata = dict(schema_version=1, version=__version__, experiment_version=SPIKE_VERSION,
                    run_kind="wp_s_spike", run_id=run_id, scenario=scene, status="running",
                    executed_plan="spike_plan.json", dataset_exported=False,
                    host=platform.platform(), python=sys.version, pymavlink=importlib.metadata.version("pymavlink"),
                    started_utc=datetime.now(timezone.utc).isoformat(), run_epoch_monotonic_s=epoch,
                    quality_policy=policy, quality_policy_sha256=policy_hash(policy), source_sha256=_source_hashes(),
                    mission_file_sha256=hashlib.sha256(mission_path.read_bytes()).hexdigest(),
                    scenario_sha256=hashlib.sha256(json.dumps(scene, sort_keys=True).encode()).hexdigest(),
                    spike_plan_sha256=hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest(),
                    clock="host perf_counter; speedup=1; semantic phase barriers; no lockstep")
    write_json(directory / "metadata.json", metadata)
    write_json(directory / "scenario.json", scene)
    write_json(directory / "spike_plan.json", plan)
    processes = SITLProcesses(binary, parameters, directory, scene, base_port)
    clients, recorder = [], None
    evidence = {}
    executor = ThreadPoolExecutor(max_workers=len(scene["vehicles"]), thread_name_prefix="spike-control")

    def parallel(function):
        futures = {executor.submit(function, client, vehicle)
                   for client, vehicle in zip(clients, scene["vehicles"])}
        while futures:
            if time.perf_counter() > deadline:
                raise TimeoutError("WP-S total scenario timeout")
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
        binary_content = Path(binary).read_bytes()
        matches = list(re.finditer(rb"ArduCopter V[0-9][\x20-\x7e]*", binary_content))
        binary_firmware = (dict(version_string=matches[0].group().decode("ascii"),
                                offset_bytes=matches[0].start(), sha256=metadata["sitl"]["sha256"])
                           if len(matches) == 1 else None)
        metadata["binary_firmware"] = binary_firmware
        metadata["parameters_sha256"] = hashlib.sha256(Path(parameters).read_bytes()).hexdigest()
        write_json(directory / "metadata.json", metadata)
        for instance in instances:
            clients.append(Vehicle(instance, directory / "raw" / f"{instance['id']}.jsonl",
                                   cancel, event, record_lifecycle=True))
        parallel(lambda client, vehicle: client.connect())
        recorder = Recorder(directory, clients, scene["origin"], epoch, scene["record_hz"], scene["max_gap_s"], policy)
        recorder.start()

        def inspect(client, vehicle):
            evidence[client.id] = read_firmware_parameters(client, binary_firmware=binary_firmware)
            event("firmware_parameters_read", client.id, parameter_count=evidence[client.id]["parameter_count"],
                  wpnav_count=len(evidence[client.id]["wpnav"]), version=evidence[client.id]["firmware"]["version_string"])
        parallel(inspect)
        write_json(directory / "firmware_parameters.json", evidence)
        parallel(lambda client, vehicle: client.prepare_airborne(scene["takeoff_alt_m"], scene["ready_timeout_s"]))
        for phase in plan["phases"]:
            missions = {v["id"]: route_mission_for(v, phase["routes"][v["id"]], phase["speed_m_s"],
                         phase["terminal_hold_s"], scene["origin"]) for v in scene["vehicles"]}

            def upload(client, vehicle):
                started = time.perf_counter()
                event("spike_phase_upload_start", client.id, phase=phase["name"])
                client.upload(missions[client.id])
                event("spike_phase_upload_end", client.id, phase=phase["name"],
                      duration_s=time.perf_counter() - started, mission_item_count=len(missions[client.id]))
            parallel(upload)
            release = time.perf_counter() + 0.3
            if "flight_epoch_monotonic_s" not in metadata:
                metadata["flight_epoch_monotonic_s"] = release
                write_json(directory / "metadata.json", metadata)
            event("phase_release_scheduled", phase=phase["name"], release_t=release - epoch)
            parallel(lambda client, vehicle: client.execute(release, len(missions[client.id]),
                                                            max(1, deadline - time.perf_counter()), phase["name"]))
            execution = scene["task_spec"]["execution"]
            parallel(lambda client, vehicle: client.confirm_target(
                phase["routes"][client.id][-1], scene["origin"], execution["arrival_tolerance_m"],
                execution["confirmation_dwell_s"], phase["name"],
                timeout=min(20 + execution["confirmation_dwell_s"], max(1, deadline - time.perf_counter())),
                max_gap=scene["max_gap_s"], quality_policy=policy))
        metadata["mission_end_monotonic_s"] = time.perf_counter()
        parallel(lambda client, vehicle: client.land())
        cancel.wait(2)
        metadata["status"] = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        metadata["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        metadata["error"] = f"{type(exc).__name__}: {exc}"
        event("run_failed", error=metadata["error"])
    finally:
        cancel.set()
        executor.shutdown(wait=True, cancel_futures=True)
        cleanup_errors = []
        if recorder:
            try:
                recorder.close()
                if recorder.error:
                    cleanup_errors.append(f"recorder: {recorder.error}")
            except Exception as exc:
                cleanup_errors.append(f"recorder close: {exc}")
        for client in clients:
            try:
                client.close()
            except Exception as exc:
                cleanup_errors.append(f"{client.id} close: {exc}")
        try:
            processes.close()
        except Exception as exc:
            cleanup_errors.append(f"SITL close: {exc}")
        metadata["elapsed_s"] = time.perf_counter() - epoch
        metadata["cleanup"] = {instance["id"]: process.poll()
                               for instance, process in zip(processes.instances, processes.processes)}
        if any(value is None for value in metadata["cleanup"].values()):
            cleanup_errors.append("owned process still running")
        if cleanup_errors:
            metadata.update(status="failed", cleanup_errors=cleanup_errors)
        if evidence:
            write_json(directory / "firmware_parameters.json", evidence)
        event_file.close()
        write_json(directory / "metadata.json", metadata)
    print(f"WP-S result: {metadata['status']}; evidence: {directory}", flush=True)
    return directory, metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mission", type=Path, default=PROJECT / "missions/recon_shared_3uav.json")
    parser.add_argument("--output-root", type=Path, default=PROJECT / "runs")
    parser.add_argument("--binary", type=Path, default=PROJECT / "ArducopterSITL/arducopter.exe")
    parser.add_argument("--parameters", type=Path, default=PROJECT / "ArducopterSITL/copter.parm")
    parser.add_argument("--base-port", type=int, default=20100)
    parser.add_argument("--lane-end-overshoot-m", type=float, default=0)
    parser.add_argument("--analyze-only", type=Path, help="Analyze an existing WP-S run without launching SITL")
    parser.add_argument("--baseline-directory", type=Path)
    args = parser.parse_args(argv)
    from scripts.spike_route_metrics import analyze_spike
    if args.analyze_only:
        directory = args.analyze_only.resolve()
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        if metadata.get("run_kind") != "wp_s_spike":
            parser.error("--analyze-only accepts WP-S evidence only, never historical v0.3 runs")
    else:
        directory, metadata = run_spike(args.mission, args.output_root, args.binary, args.parameters,
                                        args.base_port, args.lane_end_overshoot_m)
    try:
        result = analyze_spike(directory, baseline_directory=args.baseline_directory)
        print(json.dumps({"verdict": result["verdict"], "criteria": result["criteria"]}, ensure_ascii=False), flush=True)
    except Exception as exc:
        write_json(directory / "spike_analysis_error.json", {"error": f"{type(exc).__name__}: {exc}"})
        print(f"WP-S analysis failed: {exc}", file=sys.stderr)
        return 2
    return 0 if metadata["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
