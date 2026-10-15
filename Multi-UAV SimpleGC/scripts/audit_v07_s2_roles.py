"""Independent audit of S2 expansion role episodes.

Imports nothing from task_v07: all facts are recomputed from the exported
truth NPZ and public_scene.json using only numpy/shapely primitives.
"""
from itertools import combinations
from pathlib import Path
import csv
import hashlib
import math

import numpy as np

from scripts.audit_v07_s2_exact import _read, _signed_distance

LAYERS = (("warning", 1), ("alert", 2), ("protected", 3))
FLOAT_TOLERANCE = 1e-6   # labels round chord/azimuth/turn facts to 6 decimals
APPROACH_HEADING_DISTANCE_M = 100.0


# ---------------------------------------------------------------------------
# Shared geometry helpers (no task_v07 imports)
# ---------------------------------------------------------------------------

def _center(geometry):
    if geometry["type"] == "Circle":
        return np.asarray(geometry["center_m"], float)
    v = np.asarray(geometry["vertices_m"], float)
    if np.array_equal(v[0], v[-1]):
        v = v[:-1]
    x, y = v[:, 0], v[:, 1]
    xn, yn = np.roll(x, -1), np.roll(y, -1)
    cross = x * yn - xn * y
    area = cross.sum() / 2
    return np.array([((x + xn) * cross).sum() / (6 * area), ((y + yn) * cross).sum() / (6 * area)])


def _runs(mask):
    """(start, stop) index pairs of True runs."""
    edges = np.flatnonzero(np.diff(np.r_[0, np.asarray(mask, int), 0]))
    return list(zip(edges[::2], edges[1::2]))


def _longest(mask):
    return max([0.0, *[(b - a - 1) / 10 for a, b in _runs(mask)]])


def _azimuth(offset):
    return float(np.degrees(np.arctan2(offset[1], offset[0])) % 360)


def _close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= FLOAT_TOLERANCE


def _approach_heading_deg(xy, core_frame, distance_m=APPROACH_HEADING_DISTANCE_M):
    """Mean heading over the last `distance_m` of 10 Hz trajectory before core_frame.

    Independently recomputes the same quantity as labels.approach_heading_deg
    from raw truth positions, with no task_v07 import.  Returns None when the
    path is too short or core_frame is unavailable.
    """
    if core_frame is None or core_frame < 1:
        return None
    end = min(core_frame, len(xy) - 1)
    points = np.asarray(xy[:end+1], float)
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    backward = np.cumsum(lengths[::-1])
    if not len(backward) or backward[-1] < distance_m:
        return None
    offset = int(np.searchsorted(backward, distance_m, side="left"))
    segment = end - 1 - offset
    previous = 0. if offset == 0 else float(backward[offset-1])
    start = points[segment+1] + ((distance_m-previous)/lengths[segment]) * (points[segment]-points[segment+1])
    delta = points[-1] - start
    if np.linalg.norm(delta) < 1e-9:
        return None
    return float(np.degrees(math.atan2(float(delta[1]), float(delta[0]))) % 360)


def _heading_span_deg(headings):
    """Max pairwise circular angular difference among headings (degrees [0,360)).

    Returns None when any member heading is missing or there are fewer than two.
    """
    valid = [h for h in headings if h is not None]
    if len(valid) < 2 or len(valid) != len(headings):
        return None
    return float(max(min(abs(a - b), 360 - abs(a - b)) for a, b in combinations(valid, 2)))


def _build_levels(scene, xy, fids):
    """shape (T, N, F) int8 — zone level for each frame/agent/facility."""
    T, N = xy.shape[:2]
    levels = np.zeros((T, N, len(fids)), np.int8)
    for fi, fid in enumerate(fids):
        facility = next(e for e in scene["entities"] if e["id"] == fid)
        dist = _signed_distance(facility["geometry"], xy)
        for name, code in LAYERS:
            zone = next(e for e in scene["entities"]
                        if e.get("facility_id") == fid and e.get("layer") == name)
            levels[:, :, fi][dist <= zone["offset_m"]] = code
    return levels


def _check_region_facts(labels, ids, expected, t, fids):
    """Compare stored region entry times / counts to independently computed ones."""
    errors = []
    for i, a in enumerate(ids):
        observed = labels["agents"][a]["observed"]
        for j, fid in enumerate(fids):
            for name, code in LAYERS:
                hits = np.flatnonzero(expected[:, i, j] >= code)
                saved = observed["regions_by_facility"][fid][name]
                stored_t = saved["first_entry_s"]
                expected_t = float(t[hits[0]] / 1e6) if len(hits) else None
                if stored_t != expected_t or saved["sample_count"] != len(hits):
                    errors.append({"agent_id": a, "facility_id": fid, "layer": name})
    return errors


def _check_approach_span(labels, ids, xy, core_frames):
    """Independently recompute approach_span_deg and compare to stored value.

    core_frames: {agent_id: frame_index or None}
    Returns list of error dicts (empty = PASS).
    """
    errors = []
    group = next(iter(labels["task_groups"].values()))
    stored_span = group["observed"].get("approach_span_deg")
    stored_headings = group["observed"].get("approach_headings_deg", {})

    indep_headings = {}
    for i, a in enumerate(ids):
        h = _approach_heading_deg(xy[:, i], core_frames.get(a))
        indep_headings[a] = h
        # Check per-agent stored heading
        stored_h = stored_headings.get(a)
        if not _close(stored_h, h):
            errors.append({"field": "approach_headings_deg", "agent_id": a,
                           "label": stored_h, "independent": h})

    indep_span = _heading_span_deg(list(indep_headings.values()))
    if not _close(stored_span, indep_span):
        errors.append({"field": "approach_span_deg",
                       "label": stored_span, "independent": indep_span})

    # Also verify the multi_direction_span condition flag is consistent
    stored_cond = group["result"]["conditions"].get("multi_direction_span")
    if stored_cond is not None and indep_span is not None:
        if stored_cond != (indep_span >= 90):
            errors.append({"field": "multi_direction_span_condition",
                           "label": stored_cond, "independent_span": indep_span})
    return errors


def _check_separation(labels, p, ids):
    errors = []
    n = len(ids)
    if n < 2:
        return errors
    minimum = min(float(np.sqrt(np.sum((p[:, i] - p[:, j]) ** 2, axis=1)).min())
                  for i, j in combinations(range(n), 2))
    if not _close(minimum, labels["cluster"]["observed"]["minimum_separation_m"]):
        errors.append({"field": "minimum_separation_m",
                       "label": labels["cluster"]["observed"]["minimum_separation_m"],
                       "independent": minimum})
    if labels["generation_quality"]["retained"] != (minimum >= 2):
        errors.append({"field": "separation_quality_policy"})
    return errors


def _load_truth(root):
    """Returns ids, t, p, v from truth_10hz.npz, validated against truth.csv."""
    root = Path(root)
    with np.load(root / "truth_10hz.npz", allow_pickle=False) as data:
        ids = data["agent_ids"].tolist()
        t = data["time_us"].copy()
        p = data["p"].copy()
        v = data["v"].copy()
    columns = ("east_m", "north_m", "up_m", "ve_m_s", "vn_m_s", "vu_m_s")
    with (root / "truth.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != len(t) * len(ids):
        raise ValueError("P0: truth CSV row count mismatch")
    for count, row in enumerate(rows):
        k, i = divmod(count, len(ids))
        if row["agent_id"] != ids[i] or row["valid"] != "1" or float(row["t_s"]) != t[k] / 1e6:
            raise ValueError("P0: truth CSV time/ID mismatch")
        if not np.array_equal([float(row[c]) for c in columns], np.r_[p[k, i], v[k, i]]):
            raise ValueError("P0: truth CSV/NPZ state mismatch")
    return ids, t, p, v


# ---------------------------------------------------------------------------
# Complete role condition audits.

def audit_role_episode(root):
    if _read(Path(root) / "labels.json").get("evidence", {}).get("criteria_version") == "criteria/0.7-r1":
        from scripts.audit_v07_m1 import audit_episode
        return audit_episode(root)
    from scripts.audit_v07_s2_conditions import audit_conditions
    return audit_conditions(root)

audit_transit_episode = audit_role_episode
audit_close_observation_episode = audit_role_episode
audit_monitoring_episode = audit_role_episode
audit_feint_episode = audit_role_episode
audit_intrusion_episode = audit_role_episode
