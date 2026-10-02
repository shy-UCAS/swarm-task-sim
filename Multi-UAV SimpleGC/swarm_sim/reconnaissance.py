"""v3 adapter for the frozen v2 reconnaissance geometry and evidence rules."""

import copy
import math

from .mission_schema import _object, _enum, _numeric
from .registry import IntentSpec, PlannerSpec, PlanResult


def normalize_params(params):
    params = copy.deepcopy(params)
    _object(params, "intent_params", ("objective", "coverage_required", "observation_model"))
    _enum(params, "objective", "intent_params", ("area_coverage",))
    _numeric(params, "coverage_required", "intent_params", 0.01, 1)
    model = _object(params["observation_model"], "observation_model", (
        "type", "radius_m", "height_tolerance_m", "grid_m", "activation"))
    _enum(model, "type", "observation_model", ("ideal_horizontal_disk",))
    _enum(model, "activation", "observation_model", ("observe_phase_only",))
    for key, low, high in (("radius_m", .01, 1000), ("height_tolerance_m", .01, 20), ("grid_m", .01, 4000)):
        _numeric(model, key, "observation_model", low, high)
    return params


def normalize_planner(params, spec):
    params = copy.deepcopy(params)
    _object(params, "planner.params", ("partition_axis", "assignment", "lane_spacing_m", "tracking_margin_m",
                                      "lane_end_overshoot_m"), optional=("lane_end_overshoot_m",))
    _enum(params, "partition_axis", "planner.params", ("east", "north"))
    _enum(params, "assignment", "planner.params", ("monotone_entry_order",))
    _numeric(params, "lane_spacing_m", "planner.params", .01, 4000)
    _numeric(params, "tracking_margin_m", "planner.params", 0, 100)
    params.setdefault("lane_end_overshoot_m", 0.0)
    model = spec["mission"]["intent_params"]["observation_model"]
    _numeric(params, "lane_end_overshoot_m", "planner.params", 0, model["radius_m"])
    if params["lane_end_overshoot_m"] != 0:
        raise ValueError("nonzero lane_end_overshoot_m requires measured coverage evidence and WP-E implementation")
    if params["lane_spacing_m"] > 2 * model["radius_m"]:
        raise ValueError("lane spacing exceeds ideal observation footprint diameter")
    region = next(r for r in spec["scenario"]["regions"] if r["id"] == spec["mission"]["target_region_id"])
    if model["grid_m"] > min(region["width_m"], region["height_m"]):
        raise ValueError("observation_model.grid_m exceeds target region dimensions")
    if math.ceil(region["width_m"] / model["grid_m"]) * math.ceil(region["height_m"] / model["grid_m"]) > 10000:
        raise ValueError("shared coverage grid exceeds 10000 cells")
    return params


def legacy_view(spec):
    """Internal read-only shape adapter, not a v2 task migration or normalization."""
    view = copy.deepcopy(spec)
    view["schema_version"] = 2
    view.pop("family_scheme", None)
    view["platform"] = view["scenario"].pop("platform", {})
    mission = view["mission"]
    mission.update(mission.pop("intent_params"))
    planner = view["planner"]
    planner.update(planner.pop("params"))
    planner.pop("lane_end_overshoot_m", None)
    view["execution"].pop("control_mode", None)
    return view


def plan_routes(spec):
    from .mission_planning import lawnmower_route, nominal_coverage, partition_region

    scenario, mission, planner = spec["scenario"], spec["mission"], spec["planner"]["params"]
    region = next(r for r in scenario["regions"] if r["id"] == mission["target_region_id"])
    axis = planner["partition_axis"]
    partitions = partition_region(region, len(scenario["vehicles"]), axis)
    cross_width = region["width_m" if axis == "east" else "height_m"] / len(partitions)
    if cross_width <= 2 * spec["execution"]["arrival_tolerance_m"]:
        raise ValueError("responsibility strip too small for declared arrival tolerance")
    lanes = max(1, math.ceil(cross_width / planner["lane_spacing_m"]))
    if spec["execution"]["control_mode"] == "waypoint_barrier_v1" and 1 + 2 * lanes + int(mission["return_required"]) > 100:
        raise ValueError("shared route exceeds backend limit of 100 execution phases")
    ordering = sorted(scenario["vehicles"], key=lambda v: (v[f"{axis}_m"], v["id"]))
    assignments, routes = {}, {}
    for vehicle, partition in zip(ordering, partitions):
        agent = vehicle["id"]
        assignments[agent] = partition["id"]
        scan = lawnmower_route(partition, axis, lanes)
        routes[agent] = {"approach": [copy.deepcopy(scan[0])], "observe": scan,
                         "return": [{"east_m": vehicle["east_m"], "north_m": vehicle["north_m"]}]
                         if mission["return_required"] else []}
    routes = {agent: routes[agent] for agent in sorted(routes)}
    assignments = {agent: assignments[agent] for agent in sorted(assignments)}
    params = mission["intent_params"]
    coverage = nominal_coverage(region, routes, params["observation_model"])
    if coverage["ratio"] + 1e-12 < params["coverage_required"]:
        raise ValueError(f"nominal global coverage {coverage['ratio']:.6f} below required coverage")
    return PlanResult(routes, assignments, dict(
        allocation_method=planner["assignment"], partition_axis=axis,
        sweep_axis="north" if axis == "east" else "east", region_partitions=partitions,
        nominal_global_coverage=coverage))


def evaluate_channel(scene, traces, windows, clocks):
    from .mission_evaluation import _evaluate_channel, _grid

    view = dict(scene, task_spec=legacy_view(scene["task_spec"]))
    mission = view["task_spec"]["mission"]
    region = next(r for r in view["task_spec"]["scenario"]["regions"] if r["id"] == mission["target_region_id"])
    centers, info = _grid(region, mission["observation_model"]["grid_m"])
    coverage = _evaluate_channel(view, traces, windows, centers, info, clocks)["coverage"]
    return dict(conditions={"coverage": coverage["success"]}, metrics={"coverage": coverage})


def behavior_labels(scene, truth):
    passed = truth["coverage"]["success"]
    return dict(planned_behaviors=["area_scan"], observed_behaviors=[dict(
        name="coverage", agent_ids=[v["id"] for v in scene["vehicles"]],
        status="verified" if passed is True else ("failed" if passed is False else "unknown"),
        evidence_basis="SIM_truth_positions", rule_version="shared_coverage_v2")])


def topology_signature(spec, planning):
    routes = planning["per_agent_reference_routes"]
    return (len(spec["scenario"]["vehicles"]), spec["planner"]["params"]["partition_axis"],
            tuple(len(routes[agent]["observe"]) // 2 for agent in sorted(routes)), spec["mission"]["return_required"])


intent_spec = IntentSpec(
    "reconnaissance", ("area_coverage",), ("approach", "observe", "return"), frozenset({"observe"}),
    normalize_params, ("equal_strip_lawnmower_v1",), evaluate_channel, "shared_coverage_v2", behavior_labels,
    ("global_coverage_ratio", "repeated_coverage_cell_ratio", "leave_one_out_coverage_drop"), topology_signature)
planner_spec = PlannerSpec("equal_strip_lawnmower_v1", "equal_strip_lawnmower_v1", normalize_planner, plan_routes)
