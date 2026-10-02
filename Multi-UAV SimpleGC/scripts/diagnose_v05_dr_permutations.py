"""Read-only counterfactual: enumerate reconnaissance strip assignments in frozen DR.

This script does not write a task, scene, profile, or production artifact.  It
reuses the production phase compiler and full time-aware clearance unchanged.
"""

from __future__ import annotations

import copy
import itertools
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swarm_sim.generation import file_hash
from swarm_sim.mission_planning import lawnmower_route
from swarm_sim.reconnaissance import plan_routes
from swarm_sim.registry import PlanResult, get_intent, get_planner
from swarm_sim.route_planning import (
    compile_continuous_mission,
    compile_route_phases,
    time_aware_phase_clearance,
)
from swarm_sim.tasks import compile_task


DATASET = ROOT / "tmp_v05" / "dr" / "generated_130"
OUTPUT = ROOT / "tmp_v05" / "dr_composition_diagnosis" / "permutation_counterfactual.json"


def _permuted_plan(spec: dict, original: PlanResult, partition_order: tuple[dict, ...]) -> PlanResult:
    """Assign strips to vehicle IDs, preserving each vehicle's own return start."""
    agents = sorted(v["id"] for v in spec["scenario"]["vehicles"])
    vehicles = {v["id"]: v for v in spec["scenario"]["vehicles"]}
    axis = original.diagnostics["partition_axis"]
    spacing = spec["planner"]["params"]["lane_spacing_m"]
    cross_width = partition_order[0]["width_m" if axis == "east" else "height_m"]
    lanes = max(1, math.ceil(cross_width / spacing))
    routes = {}
    assignments = {}
    for agent, partition in zip(agents, partition_order):
        scan = lawnmower_route(partition, axis, lanes)
        home = vehicles[agent]
        routes[agent] = {
            "approach": [copy.deepcopy(scan[0])],
            "observe": copy.deepcopy(scan),
            "return": ([{"east_m": home["east_m"], "north_m": home["north_m"]}]
                       if spec["mission"]["return_required"] else []),
        }
        assignments[agent] = partition["id"]
    diagnostics = copy.deepcopy(original.diagnostics)
    return PlanResult(routes, assignments, diagnostics)


def _evaluate_assignment(spec: dict, plan: PlanResult) -> dict:
    intent = get_intent("reconnaissance")
    planner = get_planner(spec["planner"]["name"])
    try:
        phases, semantic, _, _, _ = compile_route_phases(spec, plan, intent)
    except (ValueError, TypeError, KeyError) as exc:
        return {"feasible": False, "failure_stage": "route_compile", "reason": str(exc)}
    required = spec["execution"]["min_separation_m"] + 2 * spec["planner"]["params"].get("tracking_margin_m", 0)
    reports = {}
    for phase in phases:
        starts = {agent: role["start_point"] for agent, role in
                  semantic["execution_phases"][phase["name"]]["agents"].items()}
        try:
            reports[phase["semantic_phase"]] = time_aware_phase_clearance(
                starts, phase["routes"], phase["speed_m_s"], required,
                spec["execution"]["async_timing_tolerance"],
                phase["terminal_hold_s"], spec["execution"]["confirmation_dwell_s"])
        except (ValueError, TypeError, KeyError) as exc:
            return {"feasible": False, "failure_stage": phase["semantic_phase"],
                    "reason": str(exc)}
    try:
        compiled = compile_continuous_mission(spec, plan, intent, planner)
    except (ValueError, TypeError, KeyError) as exc:
        return {"feasible": False, "failure_stage": "other_full_gate", "reason": str(exc)}
    minima = {name: report["nominal_min_clearance_m"] for name, report in reports.items()}
    return {"feasible": True, "failure_stage": None, "nominal_min_clearance_m":
            compiled["planning"]["nominal_min_clearance_m"],
            "phase_min_clearance_m": minima}


def main() -> None:
    manifest_path = DATASET / "generation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = [record for record in manifest["candidates"]
            if record["sampled_parameters"]
            and record["sampled_parameters"]["vehicle_count"] == 4
            and record["sampled_parameters"]["formation"] == "cluster"]
    assert len(rows) == 64, len(rows)
    results = []
    global_failures = Counter()
    for index, record in enumerate(rows, 1):
        attempt = next(a for a in record["attempts"] if a["intent"] == "reconnaissance")
        task_file = DATASET / attempt["task"]
        assert file_hash(task_file) == attempt["task_sha256"]
        spec = json.loads(task_file.read_text(encoding="utf-8"))
        original = plan_routes(spec)
        agents = sorted(v["id"] for v in spec["scenario"]["vehicles"])
        partitions = tuple(original.diagnostics["region_partitions"])
        original_assignment = [original.assignments[agent] for agent in agents]
        permutations = []
        for assignment in itertools.permutations(partitions):
            plan = _permuted_plan(spec, original, assignment)
            verdict = _evaluate_assignment(spec, plan)
            key = verdict["failure_stage"] if not verdict["feasible"] else "feasible"
            global_failures[key] += 1
            permutations.append({"agent_to_partition": plan.assignments, **verdict})
        assert len(permutations) == 24
        default = next(p for p in permutations if [p["agent_to_partition"][a] for a in agents] == original_assignment)
        assert not default["feasible"], record["candidate_id"]
        assert attempt["reason"] == f"ValueError: {default['reason']}", record["candidate_id"]
        feasible = [p for p in permutations if p["feasible"]]
        results.append({"candidate_id": record["candidate_id"],
                        "task_sha256": attempt["task_sha256"],
                        "original_assignment": original.assignments,
                        "original_failure_stage": default["failure_stage"],
                        "original_reason": attempt["reason"],
                        "permutations_evaluated": 24,
                        "feasible_permutations": len(feasible),
                        "failure_stage_counts": dict(Counter(p["failure_stage"] for p in permutations if not p["feasible"])),
                        "permutations": permutations})
        if index % 8 == 0:
            print(f"checked {index}/64 candidates", flush=True)
    output = {"method": "all 4! bijections between four fixed vehicles and four fixed reconnaissance strips; "
                "each vehicle retains its own return-to-start target; production compile_route_phases, "
                "time_aware_phase_clearance, and compile_continuous_mission run without changed parameters",
              "source_generation_manifest_sha256": file_hash(manifest_path),
              "candidates": len(results),
              "permutations_per_candidate": 24,
              "permutations_total": sum(r["permutations_evaluated"] for r in results),
              "phase_clearance_pass_count": (global_failures["feasible"] +
                    global_failures["other_full_gate"]),
              "candidate_feasible_count": sum(r["feasible_permutations"] > 0 for r in results),
              "feasible_permutation_count": global_failures["feasible"],
              "original_assignments_exact_reason_reproduced": len(results),
              "permutation_first_failure_stage_counts": dict(global_failures),
              "details": results}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: output[key] for key in ("candidates", "permutations_total",
          "phase_clearance_pass_count", "candidate_feasible_count", "feasible_permutation_count",
          "original_assignments_exact_reason_reproduced", "permutation_first_failure_stage_counts")},
          ensure_ascii=False))


if __name__ == "__main__":
    main()
