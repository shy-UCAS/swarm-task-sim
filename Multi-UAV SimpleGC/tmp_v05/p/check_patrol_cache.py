"""Offline evidence: permutation cache versus full patrol-phase checker."""

import copy
import itertools
import json
import math
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_wp_p_planning import patrol_task  # noqa: E402
from swarm_sim.mission_v3 import normalize_v3  # noqa: E402
from swarm_sim.patrol import _lap_route, _phase_check, _ring, plan_routes  # noqa: E402
from swarm_sim.route_planning import clean_route  # noqa: E402


def main():
    spec = normalize_v3(patrol_task())
    plan = plan_routes(spec).diagnostics
    corners, marks = _ring(spec["scenario"]["regions"][0], plan["patrol_direction"])
    vehicles = sorted(spec["scenario"]["vehicles"], key=lambda item: item["id"])
    altitude = spec["execution"]["takeoff_alt_m"]
    clearance = (spec["execution"]["min_separation_m"]
                 + 2 * spec["planner"]["params"]["tracking_margin_m"])
    full_reports, approach_distances = [], []
    for assignment in itertools.permutations(range(len(vehicles))):
        starts, routes = {}, {}
        for vehicle, entry_index in zip(vehicles, assignment):
            entry = dict(plan["entry_points"][entry_index], up_m=altitude)
            starts[vehicle["id"]] = entry
            routes[vehicle["id"]] = clean_route(entry,
                _lap_route(corners, marks, plan["entry_arcs_m"][entry_index], 2), altitude)[0]
        report = _phase_check(starts, routes, spec["execution"], clearance)
        full_reports.append(dict(assignment=assignment, tau_s=report["tau_s"],
            minimum_clearance_m=report["nominal_min_clearance_m"],
            duration_s=report["duration_s"], checked_point_pairs=report["checked_point_pairs"]))
        approach_distances.append(sum(math.dist(
            (vehicle["east_m"], vehicle["north_m"]),
            (plan["entry_points"][index]["east_m"], plan["entry_points"][index]["north_m"]))
            for vehicle, index in zip(vehicles, assignment)))
    values = [(row["tau_s"], row["minimum_clearance_m"], row["duration_s"],
               row["checked_point_pairs"]) for row in full_reports]
    if len(set(values)) != 1:
        raise AssertionError("patrol checker differs between permutations")
    chosen = tuple(plan["chosen_assignment_entry_indices"][vehicle["id"]] for vehicle in vehicles)
    expected = min(itertools.permutations(range(len(vehicles))),
                   key=lambda assignment: (approach_distances[
                       list(itertools.permutations(range(len(vehicles)))).index(assignment)], assignment))
    if chosen != expected:
        raise AssertionError("assignment ranking differs from exact distance ordering")
    fallback = copy.deepcopy(spec)
    fallback["scenario"]["vehicles"][0]["east_m"] = plan["entry_points"][0]["east_m"] + .01
    fallback["scenario"]["vehicles"][0]["north_m"] = plan["entry_points"][0]["north_m"]
    with patch("swarm_sim.patrol._phase_check", return_value={"tau_s": 5.}):
        fallback_cache = plan_routes(fallback).diagnostics["patrol_checker_cache"]
    if fallback_cache["eligible"] or fallback_cache["patrol_cache_reuses"]:
        raise AssertionError("near-entry no-op did not disable patrol cache")
    result = dict(version="patrol_cache_offline_comparison_v1", status="pass",
        full_reports=full_reports,
        approach_distances_m=approach_distances,
        chosen_assignment=chosen,
        normal_cache=plan["patrol_checker_cache"],
        near_entry_fallback_cache=fallback_cache,
        equivalent_metrics=["tau_s", "minimum_clearance_m", "duration_s", "checked_point_pairs"])
    output = Path(__file__).with_name("patrol_cache_comparison.json")
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
