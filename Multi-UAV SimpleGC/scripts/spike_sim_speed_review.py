"""Read-only SIM-position-derived speed cross-check for the WP-S review.

The recorded firmware has no velocity fields in SIM. This is deliberately an
auxiliary finite-difference estimate, never a direct truth-velocity assertion
and never a replacement for the FCU acceptance gate. No simulator is launched
and no output file is written by this module.
"""

import hashlib
import json
import math
from pathlib import Path

from scripts.spike_route_metrics import distribution, waypoint_metrics
from swarm_sim.observations import finite_number
from swarm_sim.recording import resample
from swarm_sim.scenario import geo_to_enu
from swarm_sim.truth import clock_to_host, read_truth


VERSION = "sim_position_backward_difference_v1"
EPS = 1e-8


def differentiate_sim_positions(samples, max_gap_s):
    """Differentiate positions before clock mapping; preserve invalid barriers.

    Velocity at the right endpoint is the mean displacement over the preceding
    source-time interval. Never differentiate through an invalid point/gap, or
    return any derivative when the full source time axis is nonmonotonic.
    """
    info = dict(source_samples=len(samples), velocity_samples=0, invalid_positions=0,
                gap_count=0, available=False, source_time_error=None)
    if any(not finite_number(t) or t < 0 for t, _ in samples):
        return [], dict(info, source_time_error="invalid SIM source timestamp")
    if any(b[0] <= a[0] for a, b in zip(samples, samples[1:])):
        return [], dict(info, source_time_error="SIM source timestamp reset/duplicate")
    result, previous = [], None
    intervals = []
    for source, pose in samples:
        valid = pose is not None and len(pose) >= 3 and all(finite_number(v) for v in pose[:3])
        if not valid:
            info["invalid_positions"] += 1
        velocity = None
        if previous is not None:
            last_time, last_pose = previous
            delta = source-last_time
            intervals.append(delta)
            if delta > max_gap_s + EPS:
                info["gap_count"] += 1
            elif valid and last_pose is not None:
                velocity = [(pose[k]-last_pose[k])/delta for k in range(3)]
        result.append((source, [*pose[:3], *velocity] if velocity is not None else None))
        previous = (source, pose[:3] if valid else None)
    info["velocity_samples"] = sum(value is not None for _, value in result)
    info["available"] = info["velocity_samples"] > 0
    info["source_interval_s"] = distribution(intervals)
    return result, info


def map_sim_speed_samples(samples, model):
    """Map only timestamps to the WP-S host epoch; keep source-time velocity."""
    if not model or not model.get("available") or len(model.get("knots", [])) < 2:
        return []
    result = []
    for source, values in samples:
        if model["knots"][0][0] <= source <= model["knots"][-1][0]:
            result.append((clock_to_host(source, model), values))
    if any(b[0] <= a[0] for a, b in zip(result, result[1:])):
        return []
    return result


def inspect_sim_formats(directory, agent):
    from pymavlink import DFReader
    paths = sorted((Path(directory)/"sitl"/agent/"logs").glob("*.BIN"))
    if len(paths) != 1:
        return dict(available=False, reason=f"expected one BIN, found {len(paths)}")
    reader = DFReader.DFReader_binary(str(paths[0]))
    try:
        formats = {fmt.name: dict(fields=list(fmt.columns), format=fmt.format)
                   for fmt in reader.formats.values() if fmt.name.startswith("SIM")}
    finally:
        reader.close()
    return dict(available=True, path=str(paths[0].relative_to(directory)), formats=formats,
                sha256=hashlib.sha256(paths[0].read_bytes()).hexdigest())


def compute_sim_speed_review(directory, plan, windows, clocks):
    """Return S-a/S-b estimated from BIN SIM only; never write source evidence."""
    directory = Path(directory)
    scene = json.loads((directory/"scenario.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory/"metadata.json").read_text(encoding="utf-8"))
    hz = scene["record_hz"]
    stop_gap = min(scene["max_gap_s"], 1.5/hz)
    grid = [i/hz for i in range(math.ceil(metadata["elapsed_s"]*hz)+1)]
    traces, agents = {}, {}
    for vehicle in scene["vehicles"]:
        agent = vehicle["id"]
        try:
            source, _, provenance = read_truth(directory, agent, scene["origin"], preserve_invalid=True)
            source_rows, derivative = differentiate_sim_positions(source, stop_gap)
            formats = inspect_sim_formats(directory, agent)
        except Exception as exc:
            source_rows, derivative, formats = [], {}, {}
            provenance = dict(available=False, reason=f"{type(exc).__name__}: {exc}")
        mapped = map_sim_speed_samples(source_rows, clocks.get(agent))
        traces[agent] = resample(mapped, grid, stop_gap)
        # Lat/Lng use signed integer 1e-7 degree storage (format 'L') in
        # the inspected firmware. This bound covers rounding only, not
        # curvature, clock alignment, dynamics, or finite-difference error.
        quantization = None
        sim_format = formats.get("formats", {}).get("SIM", {})
        fields, codes = sim_format.get("fields", []), sim_format.get("format", "")
        storage = dict(zip(fields, codes))
        if storage.get("Lat") == storage.get("Lng") == "L":
            origin = scene["origin"]
            q = geo_to_enu(origin["lat"]+1e-7, origin["lon"]+1e-7, origin["alt_msl_m"], origin)
            minimum_dt = derivative.get("source_interval_s", {}).get("minimum")
            quantization = dict(coordinate_step_degrees=1e-7,
                displacement_rounding_bound_m=math.hypot(q[0], q[1]),
                velocity_rounding_bound_m_s=math.hypot(q[0], q[1])/minimum_dt if minimum_dt else None,
                scope="global minimum source interval; rounding component only, not total error bound")
        agents[agent] = dict(truth_provenance=provenance, binary_formats=formats,
            derivative=derivative, clock_available=bool(clocks.get(agent, {}).get("available")),
            mapped_samples=len(mapped), quantization=quantization)
    metrics = waypoint_metrics(plan, windows, traces, [], hz, stop_gap)
    retained = ["phase", "semantic_phase", "agent_id", "seq", "route_index", "terminal", "east_m", "north_m",
                "stopped", "stop_intervals_s", "minimum_speed_within_2m_m_s", "evidence_complete"]
    return dict(version=VERSION, status="auxiliary_estimate_not_FCU_gate", source="onboard_BIN_SIM_position",
        direct_truth_velocity_available=False,
        derivative="backward ENU displacement / SIM TimeUS difference; assigned to right endpoint",
        speed_time_basis="SIM source seconds, before mapping; no host receive-time differentiation",
        evaluation_time_basis="same passive source-to-host mapping and 10 Hz WP-S diagnostic grid",
        maximum_source_gap_s=stop_gap, agents=agents,
        limitations=["SIM has no directly logged velocity in these runs; this is an interval-mean estimate",
            "Position quantization, right-endpoint timing, and turn chord length can affect estimated speed",
            "No smoothing; invalid poses or source gaps break differentiation and stop evidence",
            "Passive clock mapping does not identify absolute transport delay",
            "Auxiliary S-a/S-b corroboration only; does not replace FCU gate or instantaneous truth velocity"],
        S_a=metrics["S_a"], S_b=metrics["S_b"],
        waypoints=[{key: row[key] for key in retained} for row in metrics["waypoints"]])
