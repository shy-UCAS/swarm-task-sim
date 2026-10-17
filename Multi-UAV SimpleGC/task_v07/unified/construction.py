"""Shape-stage connection checks using the same free space as final checks."""
from copy import deepcopy
import math
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
            start = gate-(free.cfg["alignment_length_m"]+half)*direction
            for phase, a, b in (("ingress_line_outside_entry", start, gate),
                                ("entry_to_work_start", gate, slot["work"][0])):
                for issue in free.segment_issues(a, b):
                    evidence.append(dict(slot=slot["slot_id"], phase=phase,
                                         start_m=a.tolist(), end_m=np.asarray(b).tolist(), **issue))
    return evidence


def retreat_endpoint(free, slot, clearance):
    """Use the first legal direction in the approved deterministic sequence."""
    minimum = load_generator()["retreat"]["warning_clearance_m"]
    nominal = np.asarray(slot["exit_direction"], float)
    outward = slot.get("exit_outward_normal")
    outward = None if outward is None else np.asarray(outward, float)
    work_end = np.asarray(slot["work"][-1], float)
    warning = offset_geometry(free.target["geometry"], free.offsets["warning"])
    rejected=[]
    for degrees in (0.,30.,-30.,60.,-60.,90.,-90.):
        angle=math.radians(degrees); c,s=math.cos(angle),math.sin(angle)
        direction=np.array([c*nominal[0]-s*nominal[1],s*nominal[0]+c*nominal[1]])
        if outward is not None and float(direction @ outward) < -TOL:
            rejected.append({"slot": slot["slot_id"], "rotation_deg": degrees, "reason": "inward_rotation_skipped"})
            continue
        interval = line_interval(offset_geometry(warning, clearance), work_end, direction)
        if interval is None or interval[1] <= 0:
            rejected.append({"slot":slot["slot_id"],"rotation_deg":degrees,"reason":"ray_unavailable"})
            continue
        endpoint = work_end+interval[1]*direction
        clearances = {name: float(geometry_facts(g, endpoint)["signed_distance_m"])
                      for name, g in free.warning_geometries.items()}
        point_valid=free.point_valid(endpoint)
        evidence = {"slot": slot["slot_id"], "rotation_deg": degrees, "endpoint_m": endpoint.tolist(),
                    "clearances_m": clearances, "required_m": minimum, "point_valid": point_valid,
                    "direction":direction.tolist()}
        if point_valid and all(v >= minimum-TOL for v in clearances.values()):
            return endpoint, {**evidence,"rejected_directions":rejected}
        rejected.append(evidence)
    raise GeometryRejected("retreat_endpoint_invalid", rejected)


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
