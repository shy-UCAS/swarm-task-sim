"""Compile one fixed synthetic patrol without starting SITL."""

import json
import math
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "tests"))

from test_wp_p_planning import patrol_task
from swarm_sim.generation import canonical_hash
from swarm_sim.mission_v3 import compile_mission_v3
from swarm_sim.protocol import semantic_protocol
from swarm_sim.registry import get_intent, get_planner
from swarm_sim.route_planning import MAX_ROUTE_WAYPOINTS, ZERO_LENGTH_EPSILON_M


scene = compile_mission_v3(patrol_task())
spec, planning = scene["task_spec"], scene["planning"]
zero_length = 0
waypoint_counts = {}
for phase in scene["phases"]:
    phase_counts = {}
    for agent, route in phase["routes"].items():
        previous = scene["semantic_plan"]["execution_phases"][phase["name"]]["agents"][agent]["start_point"]
        for point in route:
            zero_length += math.dist(tuple(previous[key] for key in ("east_m", "north_m", "up_m")),
                                     tuple(point[key] for key in ("east_m", "north_m", "up_m"))) < ZERO_LENGTH_EPSILON_M
            previous = point
        phase_counts[agent] = len(route)
    waypoint_counts[phase["name"]] = phase_counts

intent = get_intent("patrol")
result = dict(task_normalized_sha256=canonical_hash(spec), compiled_scene_schema_version=scene["schema_version"],
    control_mode=scene["control_mode"], semantic_phases=[phase["semantic_phase"] for phase in scene["phases"]],
    registered_intent=intent.name, validator_version=intent.validator_version,
    registered_planner=get_planner(spec["planner"]["name"]).version,
    semantic_protocol=semantic_protocol(scene), required_audit_metrics=list(intent.required_audit_metrics),
    topology_signature=intent.topology_signature(spec, planning),
    total_zero_length_segments=zero_length, per_phase_waypoint_counts=waypoint_counts,
    max_phase_waypoint_count=max(count for row in waypoint_counts.values() for count in row.values()),
    waypoint_limit=MAX_ROUTE_WAYPOINTS, direction=planning["patrol_direction"],
    laps=planning["laps"], perimeter_m=planning["perimeter_m"],
    entry_spacing_arc_m=planning["entry_spacing_arc_m"],
    nominal_revisit_interval_s=planning["nominal_revisit_interval_s"],
    prefilter=planning["patrol_spacing_prefilter"],
    candidate_assignment_count=planning["candidate_assignment_count"],
    feasible_assignment_count=planning["feasible_assignment_count"],
    selected_phase_clearance={phase: dict(tau_s=report["tau_s"],
        nominal_min_clearance_m=report["nominal_min_clearance_m"],
        required_clearance_m=report["required_clearance_m"])
        for phase, report in planning["selected_assignment_phase_clearance"].items()})
assert result["compiled_scene_schema_version"] == 2
assert result["total_zero_length_segments"] == 0
assert result["max_phase_waypoint_count"] <= MAX_ROUTE_WAYPOINTS
assert result["prefilter"]["passed"] is True
assert set(result["selected_phase_clearance"]) == {"approach", "patrol", "return"}
assert result["required_audit_metrics"] == ["min_segment_visits", "max_revisit_gap_s", "loop_segment_coverage"]
with (Path(__file__).parent / "synthetic_compilation.json").open("x", encoding="utf-8") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps(result, ensure_ascii=False))
