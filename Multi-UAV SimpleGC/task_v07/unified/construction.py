"""Shape-stage connection checks using the same free space as final checks."""
from copy import deepcopy
import numpy as np

from task_v07.geometry import geometry_facts, offset_geometry
from .config import load_generator
from .free_space import TOL
from .route import GeometryRejected, line_interval


def ingress_issues(spec, free, slots):
    """Check the complete reserved ingress, including both sides of the gate."""
    evidence = []
    for side in sorted({s["split_index"] for s in slots}):
        block = [s for s in slots if s["split_index"] == side]
        heading = np.asarray(block[0]["direction"], float)
        normal = np.array([-heading[1], heading[0]])
        lateral = np.asarray([s["entry"] for s in block]) @ normal
        half = float(np.ptp(lateral))/2
        for slot in block:
            gate = np.asarray(slot["entry"], float)
            direction = np.asarray(slot["direction"], float)
            start = gate-(free.cfg["alignment_length_m"]+half+50.)*direction
            for phase, a, b in (("ingress_line_outside_entry", start, gate),
                                ("entry_to_work_start", gate, slot["work"][0])):
                for issue in free.segment_issues(a, b):
                    evidence.append(dict(slot=slot["slot_id"], phase=phase,
                                         start_m=a.tolist(), end_m=np.asarray(b).tolist(), **issue))
    return evidence


def retreat_endpoint(free, slot, clearance):
    """Return a legal endpoint or reject before connecting the route."""
    minimum = load_generator()["retreat"]["warning_clearance_m"]
    direction = np.asarray(slot["exit_direction"], float)
    work_end = np.asarray(slot["work"][-1], float)
    warning = offset_geometry(free.target["geometry"], free.offsets["warning"])
    interval = line_interval(offset_geometry(warning, clearance), work_end, direction)
    if interval is None or interval[1] <= 0:
        raise GeometryRejected("retreat_endpoint_invalid", [{"slot": slot["slot_id"], "reason": "ray_unavailable"}])
    endpoint = work_end+interval[1]*direction
    clearances = {name: float(geometry_facts(g, endpoint)["signed_distance_m"])
                  for name, g in free.warning_geometries.items()}
    valid = free.point_valid(endpoint) and all(v >= minimum-TOL for v in clearances.values())
    evidence = {"slot": slot["slot_id"], "rotation_deg": 0., "endpoint_m": endpoint.tolist(),
                "clearances_m": clearances, "required_m": minimum, "point_valid": free.point_valid(endpoint)}
    if not valid: raise GeometryRejected("retreat_endpoint_invalid", [evidence])
    return endpoint, evidence


def precheck_operation(spec, free, shape, rng):
    issues = ingress_issues(spec, free, shape["slots"])
    if issues: raise GeometryRejected("ingress_line_blocked", issues)
    if spec["role"] == "intrusion": return
    # Preview the existing first connection draw without adding or consuming a draw.
    # route_operation draws the same collection/retreat pair and rechecks each retry.
    preview = deepcopy(rng)
    preview.uniform(*free.cfg["collection_clearance_m"])
    clearance = preview.uniform(load_generator()["retreat"]["warning_clearance_m"],
                                free.cfg["retreat_clearance_max_m"])
    endpoints = {s["slot_id"]: retreat_endpoint(free, s, clearance)[1] for s in shape["slots"]}
    shape["draw"]["connection_precheck"] = {"retreat_clearance_m": clearance, "endpoints": endpoints,
        "sampling": "preview of existing first connection draw; no additional random draws"}
