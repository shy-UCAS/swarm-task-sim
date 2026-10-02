"""Reproduce the WP-T timing cap and corner counterexample without SITL."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from swarm_sim.generation import canonical_hash
from swarm_sim.mission_v3 import normalize_v3
from swarm_sim.route_planning import patrol_spacing_prefilter, time_aware_phase_clearance
from swarm_sim.tasks import compile_task


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tmp_v05/m0/v04_compatibility_baseline.json"


def point(east, north=0):
    return dict(east_m=float(east), north_m=float(north), up_m=8.0)


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    normalized = {}
    for name, expected in baseline["normalized_task_sha256"].items():
        spec = json.loads((ROOT / name).read_text(encoding="utf-8-sig"))
        actual = canonical_hash(normalize_v3(spec))
        normalized[name] = dict(expected_sha256=expected, actual_sha256=actual, match=actual == expected)
    generated = {}
    for name, expected in baseline["v06_generated_file_sha256"].items():
        actual = file_hash(ROOT / name)
        generated[name] = dict(expected_sha256=expected, actual_sha256=actual, match=actual == expected)

    spec = json.loads((ROOT / "missions/v3/recon_shared_3uav_route.json").read_text(encoding="utf-8"))
    legacy = compile_task(spec)
    capped_spec = json.loads(json.dumps(spec))
    capped_spec["execution"]["async_timing_tolerance"]["max_s"] = 5
    capped = compile_task(capped_spec)
    phases = {}
    for name, old in legacy["planning"]["nominal_phase_timing"].items():
        new = capped["planning"]["nominal_phase_timing"][name]
        phases[name] = dict(duration_s=new["duration_s"], old_tau_s=old["tau_s"],
                            capped_tau_s=new["tau_s"], timing_tolerance=new["timing_tolerance"],
                            tau_basis=new["tau_basis"],
                            duration_unchanged=old["duration_s"] == new["duration_s"],
                            formula_pass=new["tau_s"] == max(3, min(.2 * new["duration_s"], 5)))

    corners = [(0, 0), (20, 0), (20, 20), (0, 20)]
    starts = {f"uav_{i + 1:02d}": point(*corners[i]) for i in range(4)}
    routes = {f"uav_{i + 1:02d}": [point(*corners[(i + k) % 4]) for k in range(1, 5)]
              for i in range(4)}
    passed_screen = patrol_spacing_prefilter(80, 4, 1, 3, 14.5)
    failed_screen = patrol_spacing_prefilter(80, 4, 1, 3, 16)
    full_check_reason = None
    try:
        time_aware_phase_clearance(starts, routes, 1, 14.5,
                                   dict(min_s=3, fraction_of_phase=0, max_s=5))
    except ValueError as exc:
        full_check_reason = str(exc)
    corner = dict(square_side_m=20, perimeter_m=80, agent_count=4, speed_m_s=1,
                  tau_s=3, required_clearance_m=14.5, minimum_initial_separation_m=20,
                  chord_at_corner_m=math.sqrt(200), prefilter_pass=passed_screen,
                  prefilter_rejection=failed_screen,
                  full_check_rejection_reason=full_check_reason)
    checks = dict(
        all_legacy_normalization_hashes_match=len(normalized) == 16 and all(x["match"] for x in normalized.values()),
        all_v06_generated_file_hashes_match=len(generated) == 33 and all(x["match"] for x in generated.values()),
        capped_phase_formula_matches=all(p["formula_pass"] and p["duration_unchanged"] for p in phases.values()),
        observe_cap_5_s=phases["p01_observe"]["capped_tau_s"] == 5,
        prefilter_passes_corner_counterexample=passed_screen["passed"] and passed_screen["rejection_reason"] is None,
        full_check_rejects_corner_counterexample=(full_check_reason is not None and
                                                  full_check_reason.startswith("time-aware nominal routes too close")),
        distinct_prefilter_rejection=(not failed_screen["passed"] and
                                      failed_screen["rejection_reason"] == "patrol_spacing_prefilter"),
        corner_start_safe=20 >= 14.5 and math.sqrt(200) < 14.5)
    return dict(version="wp_t_offline_review_v1", checks=checks, passed=all(checks.values()),
                baseline=str(BASELINE.relative_to(ROOT)), normalized_tasks=normalized,
                generated_files=generated, phase_timings=phases, corner_counterexample=corner,
                t02_scope="pure prefilter and full-clearance counterexample; planner rejection routing is WP-P")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(dict(output=str(args.output), passed=result["passed"], checks=result["checks"])))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
