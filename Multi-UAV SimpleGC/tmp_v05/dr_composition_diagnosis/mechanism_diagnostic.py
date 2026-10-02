"""Read-only exhaustive clearance diagnosis for the frozen v0.5 DR candidates.

This deliberately duplicates the complete comparison set of
route_planning.time_aware_phase_clearance, but does not stop at its first
violating sample. It creates only temporary diagnostic evidence.
"""

import hashlib
import json
import math
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from swarm_sim.reconnaissance import plan_routes
from swarm_sim.registry import get_intent
from swarm_sim.route_planning import compile_route_phases, sample_route
from swarm_sim.generation import canonical_hash
from swarm_sim.generation_v2 import normalize_profile


GENERATED = ROOT / "tmp_v05/dr/generated_130"
OUT = Path(__file__).with_name("mechanism_diagnostic.json")
REQUIRED = 7.0
EPSILON = 1e-9


def _candidate_phase_minima(starts, routes, speed, timing_tolerance, hold, dwell):
    sampled = {}
    motion = {}
    completion = {}
    for agent in sorted(starts):
        points, _waypoint_times, length = sample_route(starts[agent], routes[agent], speed)
        sampled[agent] = np.asarray([[t, *xyz] for t, xyz in points], dtype=np.float64)
        motion[agent] = length / speed
        completion[agent] = motion[agent] + (hold if routes[agent] else 0.0) + dwell
    duration = max(completion.values())
    tau = max(timing_tolerance["min_s"], min(
        timing_tolerance["fraction_of_phase"] * duration,
        timing_tolerance.get("max_s", math.inf)))

    by_pair = []
    for left, right in combinations(sorted(starts), 2):
        a, b = sampled[left], sampled[right]
        best = (math.inf, None)

        def record(distance_sq, at, bt, kind):
            nonlocal best
            if distance_sq < best[0]:
                best = (float(distance_sq), dict(
                    agents=[left, right], nominal_times_s=[float(at), float(bt)],
                    kind=kind))

        # Every sampled moving pair whose nominal timestamps differ by <=tau.
        # The first source sample is also the phase start point, matching the
        # production checker exactly.
        for start in range(0, len(a), 192):
            block = a[start:start + 192]
            time_allowed = np.abs(block[:, 0, None] - b[None, :, 0]) <= tau + 1e-12
            if not np.any(time_allowed):
                continue
            delta = block[:, None, 1:] - b[None, :, 1:]
            squares = np.einsum("ijk,ijk->ij", delta, delta)
            squares[~time_allowed] = np.inf
            index = np.unravel_index(np.argmin(squares), squares.shape)
            record(squares[index], block[index[0], 0], b[index[1], 0], "moving_sample_pair")

        # Endpoint/no-op occupancy, twice with the stationary agent reversed.
        for stationary, moving in ((a, b), (b, a)):
            begin = stationary[-1, 0]
            allowed = (moving[:, 0] >= begin - tau - 1e-12) & (
                moving[:, 0] <= duration + tau + 1e-12)
            if not np.any(allowed):
                continue
            relevant = moving[allowed]
            squares = np.einsum("ij,ij->i", relevant[:, 1:] - stationary[-1, 1:],
                                relevant[:, 1:] - stationary[-1, 1:])
            index = np.argmin(squares)
            occupied = min(duration, max(begin, relevant[index, 0]))
            if stationary is a:
                record(squares[index], occupied, relevant[index, 0], "terminal_or_no_op_interval")
            else:
                record(squares[index], relevant[index, 0], occupied, "terminal_or_no_op_interval")

        # Both at their endpoints through the common phase barrier.
        delta = a[-1, 1:] - b[-1, 1:]
        record(float(np.dot(delta, delta)), duration, duration, "both_stationary")
        info = best[1]
        info["distance_m"] = math.sqrt(best[0])
        info["violates"] = info["distance_m"] + EPSILON < REQUIRED
        by_pair.append(info)

    minimum = min(by_pair, key=lambda info: info["distance_m"])
    return dict(tau_s=tau, duration_s=duration, nominal_min_distance_m=minimum["distance_m"],
                nominal_min_pair=minimum["agents"], nominal_min_kind=minimum["kind"],
                violating_pairs=[item for item in by_pair if item["violates"]],
                pair_minima=by_pair)


def diagnose_candidate(candidate):
    task = GENERATED / next(attempt["task"] for attempt in candidate["attempts"]
                            if attempt["intent"] == "reconnaissance")
    spec = json.loads(task.read_text(encoding="utf-8"))
    sampled = candidate["sampled_parameters"]
    region = spec["scenario"]["regions"][0]
    planner = spec["planner"]["params"]
    plan = plan_routes(spec)
    phases, semantic, _by_semantic, _no_ops, _removed = compile_route_phases(
        spec, plan, get_intent("reconnaissance"))
    axis = plan.diagnostics["partition_axis"]
    n = len(spec["scenario"]["vehicles"])
    width = region["width_m" if axis == "east" else "height_m"] / n
    lanes = max(1, math.ceil(width / planner["lane_spacing_m"]))
    actual_lane_spacing = width / lanes
    starts = {v["id"]: dict(east_m=v["east_m"], north_m=v["north_m"],
                            up_m=spec["execution"]["takeoff_alt_m"])
              for v in spec["scenario"]["vehicles"]}
    phase_info = {}
    for phase in phases:
        semantic_phase = phase["semantic_phase"]
        stage_starts = {agent: role["start_point"] for agent, role in
                        semantic["execution_phases"][phase["name"]]["agents"].items()}
        phase_info[semantic_phase] = _candidate_phase_minima(
            stage_starts, phase["routes"], phase["speed_m_s"],
            spec["execution"]["async_timing_tolerance"], phase["terminal_hold_s"],
            spec["execution"]["confirmation_dwell_s"])
    # Phases are checked in approach-observe-return order by production code.
    violations = [name for name, item in phase_info.items() if item["violating_pairs"]]
    attempt = next(a for a in candidate["attempts"] if a["intent"] == "reconnaissance")
    first_violation = violations[0] if violations else None
    if (attempt["status"] == "planned") != (first_violation is None):
        raise AssertionError(f"planner disagreement: {candidate['candidate_id']}")
    result = dict(candidate_id=candidate["candidate_id"], base_index=candidate["base_index"],
                  n=n, formation=sampled["formation"], entry_side=sampled["entry_side"],
                  joint_status=candidate["status"], recon_status=attempt["status"],
                  original_reason=attempt.get("reason"),
                  resolved_axis=axis, strip_width_m=width,
                  configured_lane_spacing_m=planner["lane_spacing_m"],
                  actual_lane_spacing_m=actual_lane_spacing, lanes_per_strip=lanes,
                  strip_width_minus_configured_spacing_m=width - planner["lane_spacing_m"],
                  strip_width_minus_actual_spacing_m=width - actual_lane_spacing,
                  nearest_adjacent_strip_lane_center_spacing_m=actual_lane_spacing,
                  assignments=plan.assignments, violating_phases=violations,
                  first_violation_phase=first_violation, phases=phase_info)
    return result


def main():
    manifest_file = GENERATED / "generation_manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    profile_file = ROOT / "generation_profiles/dual_intent_v05.json"
    if canonical_hash(normalize_profile(profile_file)) != manifest["profile_sha256"]:
        raise AssertionError("frozen profile fingerprint differs from DR manifest")
    # "Rejected N=3 candidates" refers to joint dual-intent rejection. This
    # includes 14 candidates whose recon plan passed but patrol plan failed;
    # retaining them records explicitly that recon had no spacing violation.
    candidates = [c for c in manifest["candidates"] if c["sampled_parameters"] is not None
                  and (c["sampled_parameters"]["vehicle_count"] == 4 or
                       c["sampled_parameters"]["vehicle_count"] == 3 and
                       c["status"] == "planning_rejected")]
    rows = []
    for index, candidate in enumerate(candidates, 1):
        rows.append(diagnose_candidate(candidate))
        if index % 20 == 0:
            print(f"diagnosed {index}/{len(candidates)}", flush=True)
    if len(rows) != 215:
        raise AssertionError(f"expected 109 N4 and 106 jointly rejected N3; saw {len(rows)}")
    result = dict(version="read_only_exhaustive_recon_clearance_diagnostic_v1",
                  source_manifest="tmp_v05/dr/generated_130/generation_manifest.json",
                  source_manifest_file_sha256=hashlib.sha256(manifest_file.read_bytes()).hexdigest(),
                  source_profile_canonical_sha256=manifest["profile_sha256"],
                  source_profile_file_sha256=hashlib.sha256(profile_file.read_bytes()).hexdigest(),
                  sampling_step_m=0.5, required_clearance_m=7.0,
                  rows=rows)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ; {len(rows)} candidate rows", flush=True)


if __name__ == "__main__":
    main()
