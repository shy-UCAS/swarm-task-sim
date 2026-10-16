"""Exact convex-base layout construction; never tessellate offset circles."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from shapely.geometry import Point, Polygon

from .sampling import _move, _radius
from .sampling_s11 import MAP_SIDES_M, SamplingRejected

CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs/scene/scene_s15_layout_r1.json"


def load_layout_config():
    raw = CONFIG_PATH.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def base_distance(a, b):
    """Euclidean separation of closed circle/polygon bases (zero on overlap)."""
    if a["type"] == b["type"] == "Circle":
        return max(0.0, math.dist(a["center_m"], b["center_m"]) - a["radius_m"] - b["radius_m"])
    if a["type"] == "Circle":
        a, b = b, a
    if b["type"] == "Circle":
        return max(0.0, Polygon(a["vertices_m"]).distance(Point(b["center_m"])) - b["radius_m"])
    return Polygon(a["vertices_m"]).distance(Polygon(b["vertices_m"]))


def signed_gap(a, offset_a, b, offset_b):
    return base_distance(a, b) - offset_a - offset_b


def bisect_t(parent, child, theta, target_distance, cfg=None):
    """Smallest positive translation attaining D for two centered convex bases."""
    cfg = cfg if cfg is not None else load_layout_config()[0]
    if target_distance <= 0:
        raise ValueError("Target base distance must be positive")
    lo, hi = 0.0, _radius(parent) + _radius(child) + target_distance + cfg["bisection_bracket_padding_m"]
    ux, uy = math.cos(theta), math.sin(theta)
    for _ in range(cfg["bisection_iterations"]):
        mid = (lo + hi) / 2
        if base_distance(parent, _move(child, [mid * ux, mid * uy])) < target_distance:
            lo = mid
        else:
            hi = mid
    return hi


def warning_bbox(local, centers):
    bounds = []
    for (contour, _, _, d1), center in zip(local, centers):
        geometry = _move(contour, center)
        if geometry["type"] == "Circle":
            x, y = geometry["center_m"]
            radius = geometry["radius_m"] + d1
            bounds.append((x-radius, y-radius, x+radius, y+radius))
        else:
            xs, ys = zip(*geometry["vertices_m"])
            bounds.append((min(xs)-d1, min(ys)-d1, max(xs)+d1, max(ys)+d1))
    return (min(b[0] for b in bounds), min(b[1] for b in bounds),
            max(b[2] for b in bounds), max(b[3] for b in bounds))


def place_layout_s15(rng, local, layout, cfg, *, finalize=None):
    """Place local bases; optional anchor finalizer shares the 128-attempt budget.

    finalize(centers, side, bbox) returns (world placement or None, anchor draws,
    rejected anchor draws). No callback is needed for local geometry tests.
    """
    failures = Counter()
    anchor_draws = anchor_retries = 0
    for attempt in range(1, cfg["layout_attempts"] + 1):
        centers, links, theta_line = [[0.0, 0.0]], [], None
        for k in range(1, len(local)):
            for link_attempt in range(1, cfg["link_direction_attempts"] + 1):
                parent = k-1 if layout == "linear" else rng.randrange(k)
                if layout == "linear":
                    if theta_line is None:
                        theta_line = rng.uniform(*cfg["direction_rad"])
                    theta = theta_line
                else:
                    theta = rng.uniform(*cfg["direction_rad"])
                width = min(local[parent][3]-local[parent][2], local[k][3]-local[k][2])
                if layout == "isolated":
                    upper = float(cfg["isolated_gap_m"][1].split("*")[0]) * width
                    target = rng.uniform(cfg["isolated_gap_m"][0], upper)
                elif layout == "clustered":
                    target = -rng.uniform(*cfg["clustered_overlap_fraction"]) * width
                elif layout == "linear":
                    target = rng.uniform(*(v * width for v in cfg["linear_gap_fraction"]))
                else:
                    raise ValueError("Unknown multi-facility layout")
                distance = target + local[parent][3] + local[k][3]
                t = bisect_t(local[parent][0], local[k][0], theta, distance, cfg)
                center = [centers[parent][0] + t * math.cos(theta), centers[parent][1] + t * math.sin(theta)]
                child = _move(local[k][0], center)
                achieved = signed_gap(_move(local[parent][0], centers[parent]), local[parent][3], child, local[k][3])
                if abs(achieved-target) > cfg["target_gap_tolerance_m"]:
                    raise AssertionError("s15_target_gap_mismatch")
                problem = None
                for j in range(k):
                    base = _move(local[j][0], centers[j])
                    gap = signed_gap(base, local[j][3], child, local[k][3])
                    pair_width = min(local[j][3]-local[j][2], local[k][3]-local[k][2])
                    if gap < -cfg["warning_overlap_max_fraction"] * pair_width:
                        problem = "r2_violation"
                        break
                    if layout == "isolated" and gap < cfg["isolated_gap_m"][0]:
                        problem = "isolated_gap"
                        break
                    # R1 is an implementation assertion only after R2 is met.
                    if (signed_gap(base, local[j][2], child, local[k][3]) <= 0 or
                            signed_gap(child, local[k][2], base, local[j][3]) <= 0):
                        raise AssertionError("s15_inner_layer_intrudes_warning")
                if problem:
                    failures[problem] += 1
                    continue
                centers.append(center)
                links.append({"child": k, "parent": parent, "theta_rad": theta,
                              "target_gap_m": target, "achieved_gap_m": achieved,
                              "overlap_fraction": -achieved / width, "link_attempts": link_attempt})
                break
            else:
                failures["link_direction_exhausted"] += 1
                break
        if len(centers) != len(local):
            continue
        bbox = warning_bbox(local, centers)
        required = max(bbox[2]-bbox[0], bbox[3]-bbox[1]) + 2*cfg["edge_clearance_m"]
        quantum = cfg["map_side_quantum_m"]
        side = max(MAP_SIDES_M[len(local)], math.ceil(required/quantum)*quantum)
        if side > cfg["max_map_side_m"]:
            failures["layout_exceeds_max_map"] += 1
            continue
        placement = None
        if finalize is not None:
            placement, draws, retries = finalize(centers, side, bbox)
            anchor_draws += draws
            anchor_retries += retries
            failures["warning_near_entry"] += retries
            if placement is None:
                failures["anchor_exhausted"] += 1
                continue
        records = {"attempts": attempt, "links": links, "rejected_attempt_reasons": dict(failures),
                   "anchor_attempts": anchor_draws, "anchor_retries": anchor_retries,
                   "map_side_m": side, "exhausted": False}
        if finalize is not None:
            return placement, records
        return centers, records
    records = {"attempts": cfg["layout_attempts"], "links": [], "rejected_attempt_reasons": dict(failures),
               "anchor_attempts": anchor_draws, "anchor_retries": anchor_retries, "exhausted": True}
    raise SamplingRejected("sampling_layout_s15_exhausted", {}, {"layout_s15": records})
