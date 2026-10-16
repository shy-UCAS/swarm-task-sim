"""Read-only original-radius patrol arc diagnostic; no proposal search or simulation."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import math
from pathlib import Path
import random
import subprocess
import sys
import time

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.run_v07_m3_checks import EVIDENCE
from scripts.run_v07_m3_trial import atomic, frozen_check
from scripts.run_v07_s2_expansion import descriptor_jobs
from task_v07.geometry import geometry_facts
from task_v07.io import read_json, sha
from task_v07.unified.free_space import free_space, TOL
from task_v07.unified.geometry_config import load_geometry
from task_v07.unified.patrol_shape import common_arcs, parallel_paths
from task_v07.unified.route import GeometryRejected
from task_v07.unified.spec import build_spec, proposal_seed

SID = "family_s12_4d13d93f9171c446_ext_007_regular"
GID = "task_group_02"
TAU = 2 * math.pi


def distribution(values):
    return {"count": len(values), "min": min(values) if values else None,
            "median": float(np.median(values)) if values else None,
            "max": max(values) if values else None}


def cyclic_intervals(breaks, valid):
    """Return canonical components, joining a component through the 0/360 seam."""
    arcs = []
    for a, b, good in zip(breaks[:-1], breaks[1:], valid):
        if not good: continue
        if arcs and abs(arcs[-1][1] - a) < 1e-12: arcs[-1][1] = b
        else: arcs.append([a, b])
    if len(arcs) > 1 and arcs[0][0] == 0. and arcs[-1][1] == TAU:
        arcs = [[arcs[-1][0], arcs[0][1] + TAU], *arcs[1:-1]]
    return arcs


def discrete_arcs(good, step):
    if np.all(good): return [[0., TAU]]
    if not np.any(good): return []
    count = len(good); first_bad = int(np.flatnonzero(~good)[0]); arcs = []; start = None
    for k in range(1, count + 1):
        i = (first_bad + k) % count; angle = (first_bad + k) * step
        if good[i] and start is None: start = angle
        if not good[i] and start is not None:
            if angle - step > start: arcs.append([start, angle-step])
            start = None
    return arcs


def span(arcs):
    return max((b-a for a, b in arcs), default=0.)


class CircleArcAudit:
    """Analytic root enumeration for this registered circle/rectangle scene only."""
    def __init__(self, spec, free):
        self.spec, self.free = spec, free
        base = free.target["geometry"]
        if base["type"] != "Circle" or any(c["geometry"]["type"] != "Circle" for c in free.constraints):
            raise ValueError("This diagnostic only handles the verified circle scene")
        world = np.asarray(free.world["vertices_m"], float)
        if len(np.unique(world[:, 0])) != 2 or len(np.unique(world[:, 1])) != 2:
            raise ValueError("This diagnostic requires the registered rectangular world")
        self.center = np.asarray(base["center_m"])
        self.base_radius = base["radius_m"]
        self.beta = np.asarray(spec["public_split"]["relative_bearings_rad"])
        self.world_bounds = [world.min(axis=0), world.max(axis=0)]

    def lanes(self, blocks, sides=None):
        sides = range(len(blocks)) if sides is None else sides
        return [(s, j, float(rho)) for s in sides for j, rho in enumerate(blocks[s])]

    def points(self, phases, lanes):
        phases = np.asarray(phases, float).reshape(-1)
        angles = phases[:, None] + np.asarray([self.beta[s] for s, _, _ in lanes])[None, :]
        radii = np.asarray([self.base_radius + rho for _, _, rho in lanes])
        return self.center + radii[None, :, None] * np.stack((np.cos(angles), np.sin(angles)), axis=-1)

    def valid(self, phases, lanes):
        points = self.points(phases, lanes); flat = points.reshape(-1, 2)
        good = geometry_facts(self.free.world, flat)["signed_distance_m"] <= -self.free.cfg["world_margin_m"] + TOL
        for c in self.free.constraints:
            good &= geometry_facts(c["geometry"], flat)["signed_distance_m"] >= c["margin_m"] - TOL
        return good.reshape(len(points), len(lanes)).all(axis=1)

    def critical_phases(self, lanes):
        roots = [0., TAU]
        for side, _, rho in lanes:
            radius = self.base_radius + rho; beta = self.beta[side]
            for c in self.free.constraints:
                other = c["geometry"]; delta = np.asarray(other["center_m"]) - self.center
                distance = float(np.linalg.norm(delta))
                if distance == 0.: continue
                inflated = other["radius_m"] + c["margin_m"] - TOL
                cosine = (radius*radius + distance*distance - inflated*inflated)/(2*radius*distance)
                if not -1. < cosine < 1.: continue
                bearing = math.atan2(delta[1], delta[0]); half = math.acos(cosine)
                roots.extend(((bearing-half-beta) % TAU, (bearing+half-beta) % TAU))
            low = self.world_bounds[0] + self.free.cfg["world_margin_m"] - TOL
            high = self.world_bounds[1] - self.free.cfg["world_margin_m"] + TOL
            for axis in (0, 1):
                for boundary in (low[axis], high[axis]):
                    ratio = (boundary-self.center[axis])/radius
                    if not -1. < ratio < 1.: continue
                    if axis == 0:
                        angle = math.acos(ratio); candidates = [angle, -angle]
                    else:
                        angle = math.asin(ratio); candidates = [angle, math.pi-angle]
                    roots.extend((angle-beta) % TAU for angle in candidates)
        return sorted(set(roots))

    def exact_arcs(self, lanes):
        roots = self.critical_phases(lanes)
        middle = (np.asarray(roots[:-1]) + roots[1:])/2
        return cyclic_intervals(roots, self.valid(middle, lanes))

    def blockers(self, phase, lanes):
        points = self.points([phase], lanes)[0]; issues = []
        for lane, point in zip(lanes, points):
            point_issues = []
            world_clearance = -float(geometry_facts(self.free.world, point)["signed_distance_m"])
            if world_clearance < self.free.cfg["world_margin_m"]-TOL:
                point_issues.append({"code": "world_margin", "entity_id": "world",
                                     "clearance_m": world_clearance, "required_m": self.free.cfg["world_margin_m"]})
            for constraint in self.free.constraints:
                clearance = float(geometry_facts(constraint["geometry"], point)["signed_distance_m"])
                if clearance < constraint["margin_m"]-TOL:
                    point_issues.append({"code": "constraint_clearance", "entity_id": constraint["id"],
                        "kind": constraint["kind"], "clearance_m": clearance, "required_m": constraint["margin_m"]})
            for issue in point_issues:
                issues.append({"split_index": lane[0], "lane_index_in_split": lane[1],
                    "offset_m": lane[2], "absolute_angle_deg": math.degrees(phase+self.beta[lane[0]]) % 360,
                    "point_m": point.tolist(), **issue})
        return issues

    def refine_boundaries(self, arc, lanes):
        """Bisection invokes original geometry_facts validity; no interpolated feasibility claim."""
        if abs(arc[1]-arc[0]-TAU) < 1e-10: return {"full_circle": True}
        result = []
        for end, boundary in enumerate(arc):
            epsilon = 1e-5
            left, right = boundary-epsilon, boundary+epsilon
            lv, rv = bool(self.valid([left], lanes)[0]), bool(self.valid([right], lanes)[0])
            if lv == rv: raise AssertionError("Analytic transition does not bracket original geometry validity")
            original = [left, right]
            for _ in range(48):
                mid = (left+right)/2
                if bool(self.valid([mid], lanes)[0]) == lv: left = mid
                else: right = mid
            inside = right if end == 0 else left
            outside = left if end == 0 else right
            result.append({"endpoint": "start" if end == 0 else "end",
                "analytic_phase_deg": math.degrees(boundary),
                "initial_bracket_phase_deg": list(map(math.degrees, original)),
                "last_valid_phase_deg": math.degrees(inside), "first_invalid_phase_deg": math.degrees(outside),
                "final_bracket_width_deg": math.degrees(right-left),
                "blocking_witness_phase_deg": math.degrees(boundary + (-epsilon if end == 0 else epsilon)),
                "blocking_witnesses": self.blockers(boundary + (-epsilon if end == 0 else epsilon), lanes)})
        return {"full_circle": False, "boundaries": result,
                "bisected_span_deg": result[1]["last_valid_phase_deg"]-result[0]["last_valid_phase_deg"]}


def verify_paths(audit, blocks, start, sweep, *, keep_points=False):
    evidence = []; paths_out = []; checked = 0
    for side, block in enumerate(blocks):
        try:
            paths, _, _ = parallel_paths(audit.free.target["geometry"], block, (block[0]+block[-1])/2,
                start+audit.beta[side], sweep, audit.free.cfg["chord_error_m"])
        except GeometryRejected as exc:
            return {"status": "REJECT", "construction_reason": exc.reason,
                    "evidence": exc.evidence, "segments_checked": checked}
        for j, path in enumerate(paths):
            for i, (a, b) in enumerate(zip(path, path[1:])):
                checked += 1
                evidence.extend({"split_index": side, "lane_index_in_split": j, "segment": i,
                    "start_m": np.asarray(a).tolist(), "end_m": np.asarray(b).tolist(), **issue}
                    for issue in audit.free.segment_issues(a, b))
            if keep_points: paths_out.append({"split_index": side, "lane_index_in_split": j,
                "offset_m": block[j], "points_m": [np.asarray(p).tolist() for p in path]})
    return {"status": "PASS" if not evidence else "REJECT", "segments_checked": checked,
        "issues": evidence, "paths": paths_out,
        "scope": "One forward work polyline per member; arc return traversals reuse the same geometric edges in reverse without lane exchange. This does not validate ingress, connection, a full route, or measured revisit."}


def analyze_draw(audit, blocks):
    radius = audit.base_radius + max(r for block in blocks for r in block)
    count = max(8, math.ceil(TAU/(2*math.acos(1-min(1., audit.free.cfg["chord_error_m"]/radius)))))
    step = TAU/count; phases = np.arange(count)*step
    side_good = [audit.valid(phases, audit.lanes(blocks, [s])) for s in range(len(blocks))]
    coarse = discrete_arcs(np.logical_and.reduce(side_good), step)
    exact = audit.exact_arcs(audit.lanes(blocks))
    split_exact = [audit.exact_arcs(audit.lanes(blocks, [s])) for s in range(len(blocks))]
    lane_max = [[math.degrees(span(audit.exact_arcs([(s, j, rho)]))) for j, rho in enumerate(block)]
                for s, block in enumerate(blocks)]
    return {"grid_count": count, "grid_step_deg": math.degrees(step),
        "coarse_common_intervals_phase_rad": coarse, "coarse_max_deg": math.degrees(span(coarse)),
        "refined_common_intervals_phase_rad": exact, "refined_max_deg": math.degrees(span(exact)),
        "split_intervals_shared_phase_rad": split_exact,
        "split_longest_deg": [math.degrees(span(a)) for a in split_exact],
        "individual_lane_longest_deg": lane_max,
        "common_intersection_reduction_deg": min(math.degrees(span(a)) for a in split_exact)-math.degrees(span(exact))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-proposals", type=int, default=200,
                        help="Diagnostic dry run only; full report requires 200. Does not increase any production budget.")
    args = parser.parse_args()
    if not 1 <= args.limit_proposals <= 200: parser.error("1..200 proposals required")
    start_time = time.perf_counter(); stamp = datetime.now(timezone.utc).isoformat()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()
    script_hash = sha(Path(__file__))
    summary = read_json(EVIDENCE/"m3b_fix_q2.json"); source = Path(summary["attempt"])
    reg = read_json(source/"registration.json"); frozen_check(reg)
    if sha(Path(reg["descriptor_attempt"])/"private_skeleton_descriptors.json") != reg["descriptor_sha256"]:
        raise AssertionError("Registered descriptor changed")
    pool_path = source/SID/"candidate_pool.json"; pool = read_json(pool_path)
    source_sha = {"pool": sha(pool_path), "registration": sha(source/"registration.json"),
                  "official_config": sha(PROJECT/"configs/generator/geometry_v07_r1.json")}
    production = {str(p.relative_to(PROJECT)): sha(p) for p in (PROJECT/"task_v07").rglob("*.py")}
    config = load_geometry(); config_before = deepcopy(config)
    if config["monitoring"]["arc_min_deg"] != 150: raise ValueError("Official 150 degree parameter changed")
    job = descriptor_jobs(Path(reg["descriptor_attempt"]), [SID], EVIDENCE)[0]
    group = next(g for g in job["descriptor"]["task_groups"] if g["group_id"] == GID)
    spec = build_spec(job["descriptor"], group); free = free_space(job["scene"], spec)
    audit = CircleArcAudit(spec, free)
    records = [r for r in pool["candidates"] if r["group_id"] == GID][:args.limit_proposals]
    rows = []; validations = []; compare_count = 0
    n = len(spec["members"]); spacing = spec["family"]["lateral_spacing_m"]
    low = free.offsets["alert"] + spec["params"]["alert_clearance_m"]
    high = free.offsets["warning"] - spec["params"]["warning_inset_m"] - (n-1)*spacing
    for record in records:
        index = record["candidate_index"]; seed = proposal_seed(spec, index)
        if seed != record["draws_by_group"][GID]["proposal_seed"]: raise AssertionError("Seed changed")
        rng = random.Random(seed)
        attempts = record["rejection"]["geometric_evidence"]
        if len(attempts) != 20: raise AssertionError("Expected all 20 saved local attempts")
        for saved in attempts:
            theta = rng.uniform(*spec["params"]["direction_deg"])
            if theta != saved["draw"]["direction_deg"]: raise AssertionError("Saved RNG direction mismatch")
            rho = rng.uniform(low, high); blocks = []; cursor = 0
            for stock in spec["public_split"]["members"]:
                blocks.append([rho+(cursor+j)*spacing for j in range(len(stock))]); cursor += len(stock)
            result = analyze_draw(audit, blocks)
            # This registered scene has no full-circle work domain. These calls
            # exactly preserve original local-draw RNG consumption before rejection.
            if result["coarse_max_deg"] >= 360-1e-9: raise AssertionError("Unexpected full-circle RNG branch")
            sign = rng.choice((-1, 1)); traversals = rng.choice(spec["params"]["traversals"])
            maximum = math.radians(result["coarse_max_deg"])
            if saved["reason"] == "patrol_arc_too_short":
                saved_max = saved["evidence"][0]["available_deg"]
                if abs(saved_max-result["coarse_max_deg"]) > 1e-8: raise AssertionError("Saved coarse arc mismatch")
            elif saved["reason"] == "ingress_line_blocked":
                if result["coarse_max_deg"] < 150: raise AssertionError("Saved ingress branch lacked 150 degree work domain")
                rng.uniform(math.radians(150), maximum); rng.random()
            else: raise AssertionError("Unexpected saved local outcome; RNG replay not established")
            if saved["draw"]["shape_attempt"] == 0:
                original, _ = common_arcs(spec, free, blocks)
                if abs(span(original)-span(result["coarse_common_intervals_phase_rad"])) > 1e-10:
                    raise AssertionError("Independent grid reconstruction differs from production")
                compare_count += 1
            row = {"candidate_index": index, "shape_attempt": saved["draw"]["shape_attempt"],
                   "proposal_seed": seed, "saved_reason": saved["reason"], "proposed_direction_deg": theta,
                   "innermost_offset_m": rho, "member_offsets_by_split_m": blocks,
                   "original_rotation_sign": sign, "original_traversals": traversals, **result}
            if result["refined_max_deg"] >= 150:
                trials = []
                for a, b in result["refined_common_intervals_phase_rad"]:
                    if b-a < math.radians(150): continue
                    for fraction in (.5, .25, .75, .1, .9):
                        begin = a + fraction*(b-a-math.radians(150))
                        proof = verify_paths(audit, blocks, begin, math.radians(150))
                        trials.append({"start_shared_phase_deg": math.degrees(begin), "span_deg": 150.,
                                       "status": proof["status"], "segments_checked": proof["segments_checked"],
                                       "construction_reason": proof.get("construction_reason"),
                                       "issues": proof.get("issues", [])})
                        if proof["status"] == "PASS": break
                    if any(t["status"] == "PASS" for t in trials): break
                row["exact_150_work_polyline"] = {"status": "PASS" if any(t["status"] == "PASS" for t in trials) else "NO_VERIFIED_PLACEMENT",
                    "trials": trials, "meaning": "Actual five-member 150 degree work polylines checked; no ingress or full candidate claim"}
            else:
                row["exact_150_work_polyline"] = {"status": "POINTWISE_COMMON_DOMAIN_BELOW_150"}
            rows.append(row)
        if (index+1) % 10 == 0:
            print(f"B arc diagnostic: {index+1} proposals / {len(rows)} saved radii", flush=True)
    # Retain full geometric witnesses for the old maximum-below-150, refined best,
    # near-threshold transition, and representative worst/intersection case.
    keys = set()
    eligible_below = [r for r in rows if r["coarse_max_deg"] < 150]
    old_max_value = max(r["coarse_max_deg"] for r in eligible_below)
    old_max_rows = [r for r in eligible_below if abs(r["coarse_max_deg"]-old_max_value) < 1e-8]
    for collection, key, reverse in ((eligible_below, "coarse_max_deg", True), (eligible_below, "refined_max_deg", True),
                                     (old_max_rows, "refined_max_deg", True), (rows, "refined_max_deg", True),
                                     (rows, "common_intersection_reduction_deg", True), (rows, "refined_max_deg", False)):
        if collection:
            r = sorted(collection, key=lambda r: r[key], reverse=reverse)[0]; keys.add((r["candidate_index"], r["shape_attempt"]))
    near = sorted(rows, key=lambda r: abs(r["refined_max_deg"]-150))[:4]
    keys.update((r["candidate_index"], r["shape_attempt"]) for r in near)
    for row in rows:
        if (row["candidate_index"], row["shape_attempt"]) not in keys: continue
        blocks = row["member_offsets_by_split_m"]; details = []
        for sides, arcs in ((None, row["refined_common_intervals_phase_rad"]),
                           *[([s], arcs) for s, arcs in enumerate(row["split_intervals_shared_phase_rad"])]):
            longest = max(arcs, key=lambda ab: ab[1]-ab[0]); lanes = audit.lanes(blocks, sides)
            details.append({"split_indices": list(range(len(blocks))) if sides is None else sides,
                "coordinate": "shared phase phi; absolute theta_s = phi + beta_s",
                "longest_interval_shared_phase_deg": list(map(math.degrees, longest)),
                "absolute_intervals_by_split_deg": {str(s): [math.degrees(x+audit.beta[s]) for x in longest]
                                                     for s in (range(len(blocks)) if sides is None else sides)},
                "boundary_refinement": audit.refine_boundaries(longest, lanes)})
        grid = row["grid_step_deg"]
        coarse = [{"last_valid_start_phase_deg": math.degrees(a), "preceding_first_invalid_phase_deg": math.degrees(a)-grid,
                   "last_valid_end_phase_deg": math.degrees(b), "following_first_invalid_phase_deg": math.degrees(b)+grid}
                  for a,b in row["coarse_common_intervals_phase_rad"]]
        grid_points = []
        lanes = audit.lanes(blocks)
        for component in coarse:
            samples = []
            for name, degrees in component.items():
                phase = math.radians(degrees)
                samples.append({"kind": name, "shared_phase_deg": degrees,
                    "valid_all_members": bool(audit.valid([phase], lanes)[0]),
                    "members": [{"split_index": lane[0], "lane_index_in_split": lane[1], "offset_m": lane[2],
                        "absolute_angle_deg": degrees+math.degrees(audit.beta[lane[0]]), "point_m": point.tolist()}
                        for lane, point in zip(lanes, audit.points([phase], lanes)[0])],
                    "blocking_constraints": audit.blockers(phase, lanes)})
            grid_points.append(samples)
        longest = max(row["refined_common_intervals_phase_rad"], key=lambda ab: ab[1]-ab[0])
        full = verify_paths(audit, blocks, longest[0], longest[1]-longest[0], keep_points=True)
        verified = next((t for t in row["exact_150_work_polyline"].get("trials", []) if t["status"] == "PASS"), None)
        proof = None if verified is None else verify_paths(audit, blocks, math.radians(verified["start_shared_phase_deg"]), math.radians(150), keep_points=True)
        validations.append({"candidate_index": row["candidate_index"], "shape_attempt": row["shape_attempt"],
            "coarse_neighbors": coarse, "grid_boundary_points": grid_points, "refined_boundaries": details,
            "longest_pointwise_interval_actual_polyline": full, "verified_150_actual_polyline": proof})
    unchanged = production == {str(p.relative_to(PROJECT)): sha(p) for p in (PROJECT/"task_v07").rglob("*.py")}
    if not unchanged or config_before != load_geometry() or source_sha["official_config"] != sha(PROJECT/"configs/generator/geometry_v07_r1.json"):
        raise AssertionError("Production code/config changed during diagnostic")
    if head != subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip() or script_hash != sha(Path(__file__)):
        raise AssertionError("HEAD or diagnostic script changed during diagnostic")
    rescued = [r for r in rows if r["coarse_max_deg"] < 150 and r["exact_150_work_polyline"]["status"] == "PASS"]
    report = {"schema": "m3b-patrol-arc-analysis/1", "started_utc": stamp,
        "finished_utc": datetime.now(timezone.utc).isoformat(), "entry_commit": head, "head_unchanged_during_run": True,
        "diagnostic_script_sha256": script_hash, "production_source_sha256": production,
        "skeleton_id": SID, "group_id": GID, "source_attempt": str(source), "source_sha256": source_sha,
        "descriptor_sha256": reg["descriptor_sha256"], "source_scene_assets": reg["source_assets"],
        "public_split": spec["public_split"], "target_geometry": free.target["geometry"], "constraints": free.constraints,
        "world": free.world, "official_arc_min_deg": 150, "production_config_modified": False,
        "production_sources_unchanged_during_run": unchanged, "frozen_check": frozen_check(reg),
        "simulation_count": 0, "production_proposals_run": 0, "saved_proposals_reconstructed": len(records),
        "saved_local_draws_reconstructed": len(rows), "independent_grid_compared_to_production_count": compare_count,
        "radius_interval_m": [low, high], "group_width_m": (n-1)*spacing, "family_spacing_m": spacing,
        "coordinate_method": "theta_s = shared phase phi + frozen public beta_s. Every member in a split is tested at its own radius. Independent split intervals are shifted back by -beta_s before intersection; absolute-angle intervals are never intersected directly.",
        "boundary_method": "For the registered circular target, circular constraints and rectangular world, enumerate all exact original-primitive angular roots including unchanged geometric margins/tolerance. Classify every interval by geometry_facts at its midpoint. Key boundaries are independently bisected with geometry_facts; actual work polylines use unchanged parallel_paths and free.segment_issues.",
        "grid_endpoint_conservatism": "Production uses first valid and last valid grid samples. For a matched real connected component each side can lose less than one grid step, hence up to two steps across that component; measured longest-component differences are in each row. This is a pointwise-domain statement, not a proof that the discretized polyline is valid or that a coarse grid cannot miss a narrow invalid component.",
        "contract_review": {"explicit_frozen_contract": "M3 plan section 3 preserves public split and relative bearings; design 3.2/4.3 preserves multi-direction approach; design 3.3/4.1/4.4 requires each patrol path inside free space and arc >=150 degrees.",
            "implementation_choice": "common_arcs and patrol_shape use one shared start, sign and sweep across split-specific concentric lines. The design does not separately state a common full-work-phase interval or equal sweep as an explicit hard criterion. Preserving relative ingress phase plus this common-sweep construction leads to the current intersection.",
            "decision": "No public relative bearing or phase coupling is relaxed in this diagnostic. Whether to allow independent work spans/starts beyond the current construction requires user judgment; this report does not authorize it."},
        "summary": {"coarse_max_deg": distribution([r["coarse_max_deg"] for r in rows]),
            "coarse_max_among_saved_arc_too_short_deg": distribution([r["coarse_max_deg"] for r in rows if r["saved_reason"] == "patrol_arc_too_short"]),
            "refined_max_among_saved_arc_too_short_deg": distribution([r["refined_max_deg"] for r in rows if r["saved_reason"] == "patrol_arc_too_short"]),
            "same_147_857_coarse_max_samples": {"coarse_deg": old_max_value, "count": len(old_max_rows),
                "refined_max_deg": distribution([r["refined_max_deg"] for r in old_max_rows]),
                "actual_150_work_polyline_pass_count": sum(r["exact_150_work_polyline"]["status"] == "PASS" for r in old_max_rows)},
            "sampled_innermost_offset_m": distribution([r["innermost_offset_m"] for r in rows]),
            "rescued_innermost_offset_m": distribution([r["innermost_offset_m"] for r in rescued]),
            "grid_step_deg": distribution([r["grid_step_deg"] for r in rows]),
            "refined_max_deg": distribution([r["refined_max_deg"] for r in rows]),
            "refinement_gain_deg": distribution([r["refined_max_deg"]-r["coarse_max_deg"] for r in rows]),
            "split_longest_deg": [distribution([r["split_longest_deg"][s] for r in rows]) for s in range(len(audit.beta))],
            "common_intersection_reduction_deg": distribution([r["common_intersection_reduction_deg"] for r in rows]),
            "coarse_reaches_150": sum(r["coarse_max_deg"] >= 150 for r in rows),
            "refined_pointwise_reaches_150": sum(r["refined_max_deg"] >= 150 for r in rows),
            "verified_actual_150_work_polylines": sum(r["exact_150_work_polyline"]["status"] == "PASS" for r in rows),
            "originally_below_150_but_verified_actual_150": sum(r["coarse_max_deg"] < 150 and r["exact_150_work_polyline"]["status"] == "PASS" for r in rows)},
        "rows": rows, "key_witnesses": validations,
        "unresolved": ["Work-arc feasibility does not establish legal ingress, retreat, a complete group candidate, an episode combination, or measured M1 revisit. Those are separate counterfactual/runtime checks.",
                       "A failed finite set of tested 150-degree polyline placements is not a proof of global infeasibility."],
        "diagnostic_script_repairs": ["The first diagnostic run requested boundary point witnesses through a zero-length footprint segment, causing a Shapely distance warning. Replaced that witness-only calculation with direct original geometry_facts point distances and reran all 4000 saved draws. Actual nonzero work-polyline segment_issues validation was unchanged; no production code or criterion changed."],
        "wall_s": time.perf_counter()-start_time}
    destination = EVIDENCE/("m3b_patrol_arc_analysis.json" if len(records)==200 else "m3b_patrol_arc_analysis_dry_run.json")
    atomic(destination, report)
    print({"output": str(destination), "summary": report["summary"], "wall_s": report["wall_s"]}, flush=True)


if __name__ == "__main__": main()
